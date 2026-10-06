import json
import subprocess
import sys
import wave
from types import SimpleNamespace

import pytest

from agent_audio import download_models, runtime, torch_runner
from agent_audio.backends import get_backend


@pytest.mark.parametrize(
    "backend,system,accepted",
    [
        ("cuda", "Windows", True),
        ("cuda", "Linux", True),
        ("cuda", "Darwin", False),
        ("rocm", "Linux", True),
        ("rocm", "Windows", False),
        ("rocm", "Darwin", False),
    ],
)
def test_gpu_platform_guard_before_install(monkeypatch, backend, system, accepted):
    monkeypatch.setattr(runtime.platform, "system", lambda: system)
    monkeypatch.setattr(runtime.platform, "machine", lambda: "x86_64")
    if accepted:
        get_backend(backend).validate_platform()
    else:
        monkeypatch.setattr(
            runtime,
            "ensure_upstream_checkout",
            lambda: pytest.fail("must reject before changes"),
        )
        with pytest.raises(ValueError, match="Use tflite"):
            runtime.install_runtime(backend)


def test_selection_persists_and_preserves_other_settings(tmp_path, monkeypatch):
    monkeypatch.setenv("AGENT_AUDIO_HOME", str(tmp_path))
    monkeypatch.setattr(runtime.platform, "system", lambda: "Windows")
    monkeypatch.setattr(runtime.platform, "machine", lambda: "AMD64")
    monkeypatch.setattr(runtime, "recommended_backend", lambda _: "tflite")
    monkeypatch.setattr(runtime, "detect_environment", lambda: None)
    config = tmp_path / "backend.json"
    config.write_text('{"backend":"tflite", "other":42}')
    runtime._save_backend("cuda")
    assert runtime.selected_backend() == "cuda"
    assert json.loads(config.read_text())["other"] == 42
    assert list(tmp_path.glob("backend.json*.bak"))
    runtime._save_backend("tflite")
    assert runtime.selected_backend() == "tflite"


@pytest.mark.parametrize("backend", ["cuda", "rocm"])
def test_gpu_install_pins_vendor_and_probes_before_models(
    tmp_path, monkeypatch, backend
):
    monkeypatch.setenv("AGENT_AUDIO_HOME", str(tmp_path))
    monkeypatch.setattr(runtime.platform, "system", lambda: "Linux")
    monkeypatch.setattr(runtime.platform, "machine", lambda: "x86_64")
    monkeypatch.setattr(runtime, "ensure_upstream_checkout", lambda: None)
    monkeypatch.setattr(runtime.shutil, "which", lambda _: "uv")
    monkeypatch.setattr(runtime, "backend_ready", lambda _: True)
    calls = []
    monkeypatch.setattr(
        runtime.subprocess, "run", lambda cmd, **kw: calls.append((cmd, kw))
    )
    assert runtime.install_runtime(backend) == backend
    install = next(cmd for cmd, _ in calls if cmd[:3] == ["uv", "pip", "install"])
    assert all(wheel in install for wheel in get_backend(backend).wheel_requirements())
    assert "--extra-index-url" not in install
    probe = next(i for i, (cmd, _) in enumerate(calls) if "--probe" in cmd)
    download = next(
        i
        for i, (cmd, _) in enumerate(calls)
        if any(arg.endswith("download_models.py") for arg in cmd)
    )
    assert probe < download
    assert runtime.selected_backend() == backend
    command, _ = runtime._runtime_command(backend)
    assert command[1] == "-I"
    assert backend in command
    assert "optimized" not in str(runtime._backend_folder(backend))


def test_failed_gpu_probe_does_not_change_selection(tmp_path, monkeypatch):
    monkeypatch.setenv("AGENT_AUDIO_HOME", str(tmp_path))
    monkeypatch.setattr(runtime.platform, "system", lambda: "Windows")
    monkeypatch.setattr(runtime.platform, "machine", lambda: "AMD64")
    runtime._save_backend("tflite")
    monkeypatch.setattr(runtime, "ensure_upstream_checkout", lambda: None)
    monkeypatch.setattr(runtime.shutil, "which", lambda _: "uv")

    def run(cmd, **kwargs):
        if "--probe" in cmd:
            raise subprocess.CalledProcessError(1, cmd)
        assert not any(arg.endswith("download_models.py") for arg in cmd)

    monkeypatch.setattr(runtime.subprocess, "run", run)
    with pytest.raises(subprocess.CalledProcessError):
        runtime.install_runtime("cuda")
    assert runtime.selected_backend() == "tflite"


@pytest.mark.parametrize(
    "backend,hip,available",
    [("cuda", "6.3", True), ("rocm", None, True), ("cuda", None, False)],
)
def test_gpu_runner_refuses_wrong_vendor_or_missing_device(backend, hip, available):
    torch = SimpleNamespace(
        version=SimpleNamespace(hip=hip),
        cuda=SimpleNamespace(is_available=lambda: available),
    )
    with pytest.raises(RuntimeError, match="no CPU fallback"):
        torch_runner.verify_device(torch, backend)


def test_conditioner_is_local_and_original_config_file_unchanged(tmp_path):
    config = {
        "model": {
            "conditioning": {
                "configs": [
                    {
                        "type": "t5gemma",
                        "config": {
                            "repo_id": "remote",
                            "subfolder": "text",
                            "model_name": "google/t5gemma-b-b-ul2",
                        },
                    }
                ]
            }
        }
    }
    path = tmp_path / "model_config.json"
    path.write_text(json.dumps(config))
    original = path.read_bytes()
    torch_runner.local_conditioner(config, tmp_path)
    options = config["model"]["conditioning"]["configs"][0]["config"]
    assert options["model_path"] == str(tmp_path / "t5gemma-b-b-ul2")
    assert "repo_id" not in options and "subfolder" not in options
    assert path.read_bytes() == original
    with pytest.raises(RuntimeError, match="exactly one"):
        torch_runner.local_conditioner({}, tmp_path)


def test_gpu_download_uses_pinned_gated_repo(tmp_path, monkeypatch):
    blob = tmp_path / "blob"
    blob.write_bytes(b"fixture")
    calls = []

    def fetch(repo, filename, **kwargs):
        calls.append((repo, filename, kwargs))
        return str(blob)

    monkeypatch.setitem(
        sys.modules, "huggingface_hub", SimpleNamespace(hf_hub_download=fetch)
    )
    download_models.download("cuda", tmp_path / "runtime", tmp_path / "cache")
    assert {r for r, _, _ in calls} == {download_models.TORCH_MODEL_REPO}
    assert {k["revision"] for _, _, k in calls} == {
        download_models.TORCH_MODEL_REVISION
    }
    assert {f for _, f, _ in calls} == set(download_models.TORCH_FILES)


def test_gated_access_failure_not_bypassed(tmp_path, monkeypatch):
    def fetch(*args, **kwargs):
        raise PermissionError("license/authentication required")

    monkeypatch.setitem(
        sys.modules, "huggingface_hub", SimpleNamespace(hf_hub_download=fetch)
    )
    with pytest.raises(PermissionError):
        download_models.download("rocm", tmp_path / "runtime", tmp_path / "cache")
    assert not (tmp_path / "runtime").exists()


def test_http_fallback_requests_full_range_and_keeps_pin(tmp_path, monkeypatch):
    monkeypatch.setenv("HF_HUB_DISABLE_XET", "1")
    blob = tmp_path / "blob"
    blob.write_bytes(b"fixture")
    calls = []

    def fetch(repo, filename, **kwargs):
        calls.append(kwargs)
        return str(blob)

    monkeypatch.setitem(
        sys.modules, "huggingface_hub", SimpleNamespace(hf_hub_download=fetch)
    )
    download_models.download("cuda", tmp_path / "runtime", tmp_path / "cache")
    assert all(call["headers"] == {"Range": "bytes=0-"} for call in calls)
    assert all(
        call["revision"] == download_models.TORCH_MODEL_REVISION for call in calls
    )


@pytest.mark.parametrize("backend", ["cuda", "rocm"])
def test_gpu_generation_uses_selected_adapter_offline_and_publishes_wav(
    tmp_path, monkeypatch, backend
):
    monkeypatch.setenv("AGENT_AUDIO_HOME", str(tmp_path / "home"))
    monkeypatch.setattr(runtime.platform, "system", lambda: "Linux")
    monkeypatch.setattr(runtime.platform, "machine", lambda: "x86_64")
    runtime._save_backend(backend)
    monkeypatch.setattr(runtime, "backend_ready", lambda _: True)
    monkeypatch.setattr(runtime, "verify_upstream_checkout", lambda _: None)
    calls = []

    def infer(command, cwd, env, timeout, **kwargs):
        calls.append((command, env))
        output = command[command.index("--out") + 1]
        with wave.open(output, "wb") as wav:
            wav.setnchannels(2)
            wav.setsampwidth(2)
            wav.setframerate(44100)
            wav.writeframes(b"\0" * (44100 * 4))

    monkeypatch.setattr(runtime, "run_inference", infer)
    output = tmp_path / "impact.wav"
    assert (
        runtime.generate_audio("-isolated impact", seconds=1, output_path=str(output))
        == output
    )
    command, env = calls[0]
    assert backend in command
    assert "--prompt=-isolated impact" in command
    assert env["HF_HUB_OFFLINE"] == "1"
    assert not list(tmp_path.glob(".agent-audio-render-*"))
    with pytest.raises(FileExistsError):
        runtime.generate_audio("impact", seconds=1, output_path=str(output))
    assert len(calls) == 1

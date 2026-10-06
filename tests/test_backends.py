import subprocess
from pathlib import Path
from types import SimpleNamespace

import pytest

from agent_audio import installer, runtime
from agent_audio.backends import get_backend
from agent_audio.detect import EnvironmentInfo


@pytest.mark.parametrize("backend", ["tflite", "mlx", "cuda", "rocm"])
def test_negative_prompt_rejected_before_readiness_or_inference(backend, monkeypatch):
    monkeypatch.setattr(runtime, "detect_environment", lambda: None)
    monkeypatch.setattr(runtime, "recommended_backend", lambda _: backend)
    monkeypatch.setattr(
        runtime,
        "backend_ready",
        lambda _: pytest.fail("Unsupported input must be rejected before readiness"),
    )
    with pytest.raises(ValueError, match="negative_prompt is unsupported"):
        runtime.generate_audio("impact", seconds=3, negative_prompt="music")


@pytest.mark.parametrize("backend", ["tflite", "mlx"])
def test_adapter_preserves_model_selection_and_explicit_guidance(backend):
    adapter = get_backend(backend)
    args = adapter.generation_arguments("--literal prompt", 3, Path("out.wav"))
    assert args[0] == "--prompt=--literal prompt"
    assert args[args.index("--dit") + 1] == "medium"
    assert args[args.index("--decoder") + 1] == "same-l"
    assert args[args.index("--cfg") + 1] == "1.0"
    adapter.validate_negative_prompt(None)
    adapter.validate_negative_prompt("")


@pytest.mark.parametrize(
    "failure,expected",
    [
        (None, "verified"),
        (RuntimeError("mismatch"), "invalid"),
        (subprocess.TimeoutExpired("git", 60), "invalid"),
    ],
)
def test_diagnostics_do_not_claim_generation_or_integrity(
    tmp_path, monkeypatch, failure, expected
):
    monkeypatch.setenv("AGENT_AUDIO_HOME", str(tmp_path))
    runtime.runtime_paths().upstream.mkdir(parents=True)

    def verify(_):
        if failure:
            raise failure

    monkeypatch.setattr(runtime, "verify_upstream_checkout", verify)
    details = runtime.runtime_details("tflite")
    assert details["capabilities"]["negative_prompt"] is False
    assert details["readiness"] == {
        "scope": "files_and_headers",
        "upstream_checkout": expected,
        "model_checksums": "not_checked",
        "runtime_dependencies": "not_checked",
        "generation": "not_checked",
    }


def test_doctor_existing_checkout_uses_only_local_git_with_network_blocked(
    tmp_path, monkeypatch
):
    import socket

    monkeypatch.setenv("AGENT_AUDIO_HOME", str(tmp_path))
    (runtime.runtime_paths().upstream / ".git").mkdir(parents=True)
    monkeypatch.setattr(
        installer,
        "detect_environment",
        lambda: EnvironmentInfo(
            "Windows", "64bit", "AMD64", False, False, False, False, False, False
        ),
    )
    monkeypatch.setattr(runtime.shutil, "which", lambda _: "git")
    commands = []
    allowed = {
        ("remote", "get-url", "origin"): runtime.UPSTREAM_REPO,
        ("rev-parse", "HEAD"): runtime.UPSTREAM_REVISION,
        ("diff", "--quiet", "--no-ext-diff", "--no-textconv", "HEAD", "--"): "",
    }

    def no_network(*args, **kwargs):
        pytest.fail("doctor attempted network access")

    def local_git(command, **kwargs):
        args = tuple(command[3:])
        assert args in allowed, f"Unexpected subprocess: {command}"
        commands.append(args)
        return SimpleNamespace(returncode=0, stdout=allowed[args], stderr="")

    monkeypatch.setattr(socket, "socket", no_network)
    monkeypatch.setattr(runtime.subprocess, "run", local_git)
    result = installer.doctor()
    assert commands == list(allowed)
    assert result["readiness"]["upstream_checkout"] == "verified"
    assert result["readiness"]["generation"] == "not_checked"

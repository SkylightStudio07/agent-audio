from __future__ import annotations

import json
import math
import os
import platform
import shutil
import subprocess
import sys
import tempfile
import uuid
import wave
from dataclasses import dataclass
from pathlib import Path

from .backends import get_backend
from .detect import detect_environment, recommended_backend
from .download_models import MODEL_REVISION, TORCH_MODEL_REVISION
from .process import run_inference
from .storage import atomic_write, file_lock, read_optional, reject_link

UPSTREAM_REPO = "https://github.com/Stability-AI/stable-audio-3.git"
UPSTREAM_REVISION = "779434a908193105335fd8d833418603625b2859"
GENERATION_TIMEOUT = 540  # Leave room for MCP transport within Codex's 600 seconds.


@dataclass(frozen=True)
class RuntimePaths:
    root: Path
    upstream: Path
    output: Path


def data_root() -> Path:
    custom = os.environ.get("AGENT_AUDIO_HOME")
    return (
        Path(custom).expanduser().absolute() if custom else Path.home() / ".agent-audio"
    )


def runtime_paths() -> RuntimePaths:
    root = data_root()
    return RuntimePaths(root, root / "runtime" / "stable-audio-3", root / "output")


def runtime_environment() -> dict[str, str]:
    env = os.environ.copy()
    # Do not inherit another Python environment or model cache. Keep explicit
    # HF credentials/proxies available; never copy a login from another cache.
    for name in (
        "PYTHONPATH",
        "PYTHONHOME",
        "PYTHONUSERBASE",
        "VIRTUAL_ENV",
        "CONDA_PREFIX",
    ):
        env.pop(name, None)
    cache = data_root() / "cache" / "huggingface"
    env.update(
        {
            "HF_HOME": str(cache),
            "HF_HUB_CACHE": str(cache / "hub"),
            "HUGGINGFACE_HUB_CACHE": str(cache / "hub"),
            "HF_XET_CACHE": str(cache / "xet"),
            "PYTHONNOUSERSITE": "1",
            "PYTHONUTF8": "1",
        }
    )
    return env


def _backend_folder(backend: str) -> Path:
    if get_backend(backend).accelerated:
        return data_root() / "runtimes" / backend
    return runtime_paths().upstream / "optimized" / get_backend(backend).name


def selected_backend(info=None) -> str:
    config = data_root() / "backend.json"
    reject_link(config)
    raw = read_optional(config)
    if raw is not None:
        backend = json.loads(raw)["backend"]
        get_backend(backend).validate_platform()
        return backend
    return recommended_backend(info if info is not None else detect_environment())


def _save_backend(backend: str) -> None:
    config = data_root() / "backend.json"
    with file_lock(config):
        raw = read_optional(config)
        settings = json.loads(raw) if raw is not None else {}
        settings["backend"] = backend
        atomic_write(config, raw, (json.dumps(settings) + "\n").encode())


def runtime_python(backend: str) -> Path:
    folder = _backend_folder(backend) / ".venv"
    return (
        folder / "Scripts" / "python.exe"
        if platform.system() == "Windows"
        else folder / "bin" / "python"
    )


def _model_paths(backend: str) -> list[Path]:
    names = get_backend(backend).model_files
    return [_backend_folder(backend) / "models" / backend / name for name in names]


def runtime_details(backend: str) -> dict[str, object]:
    upstream = runtime_paths().upstream
    provenance = "missing"
    if upstream.exists():
        try:
            verify_upstream_checkout(upstream)
            provenance = "verified"
        except (OSError, RuntimeError, subprocess.SubprocessError):
            provenance = "invalid"
    return {
        "runtime_python": str(runtime_python(backend)),
        "model": "stable-audio-3-medium",
        "model_files": [str(path) for path in _model_paths(backend)],
        "model_cache": runtime_environment()["HF_HUB_CACHE"],
        "runtime_revision": UPSTREAM_REVISION,
        "model_revision": TORCH_MODEL_REVISION
        if get_backend(backend).accelerated
        else MODEL_REVISION,
        "acceleration": {
            "requested": backend if get_backend(backend).accelerated else None,
            "gpu_probe": "not_checked",
            "generation": "not_checked",
        },
        "capabilities": {"negative_prompt": False},
        "readiness": {
            "scope": "files_and_headers",
            "upstream_checkout": provenance,
            "model_checksums": "not_checked",
            "runtime_dependencies": "not_checked",
            "generation": "not_checked",
        },
    }


def _git(repo: Path, *args: str) -> str:
    git = shutil.which("git")
    if not git:
        raise RuntimeError("Git is required to verify the pinned Stable Audio runtime.")
    env = {
        name: value for name, value in os.environ.items() if not name.startswith("GIT_")
    }
    env["GIT_TERMINAL_PROMPT"] = "0"
    result = subprocess.run(
        [git, "-C", str(repo), *args],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        stdin=subprocess.DEVNULL,
        timeout=60,
        env=env,
        check=False,
    )
    if result.returncode:
        raise RuntimeError(
            f"Runtime checkout verification failed: {result.stderr.strip() or 'modified tracked files'}"
        )
    return result.stdout.strip()


def verify_upstream_checkout(repo: Path) -> None:
    reject_link(repo)
    if not (repo / ".git").is_dir():
        raise RuntimeError(
            f"Unmanaged runtime directory: {repo}; preserved. Choose a separate AGENT_AUDIO_HOME."
        )
    if _git(repo, "remote", "get-url", "origin") != UPSTREAM_REPO:
        raise RuntimeError(
            "Runtime origin does not match the official repository; refusing to execute it."
        )
    if _git(repo, "rev-parse", "HEAD") != UPSTREAM_REVISION:
        raise RuntimeError(
            "Runtime revision differs from the tested pin; preserved. Choose a separate AGENT_AUDIO_HOME."
        )
    _git(repo, "diff", "--quiet", "--no-ext-diff", "--no-textconv", "HEAD", "--")


def ensure_upstream_checkout() -> Path:
    paths = runtime_paths()
    if os.path.lexists(paths.upstream):
        verify_upstream_checkout(paths.upstream)
        return paths.upstream
    git = shutil.which("git")
    if not git:
        raise RuntimeError("Git is required for runtime installation.")
    paths.upstream.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(
        prefix=".agent-audio-checkout-", dir=paths.upstream.parent
    ) as temporary:
        stage = Path(temporary) / "runtime"
        stage.mkdir()
        _git(stage, "init")
        _git(stage, "remote", "add", "origin", UPSTREAM_REPO)
        _git(stage, "fetch", "--depth", "1", "origin", UPSTREAM_REVISION)
        _git(stage, "checkout", "--detach", UPSTREAM_REVISION)
        verify_upstream_checkout(stage)
        if os.path.lexists(paths.upstream):
            raise RuntimeError(
                f"Runtime destination appeared during installation: {paths.upstream}"
            )
        stage.rename(paths.upstream)
    return paths.upstream


def _venv_ready(backend: str) -> bool:
    folder = _backend_folder(backend) / ".venv"
    try:
        reject_link(folder)
        config = (folder / "pyvenv.cfg").read_text(encoding="utf-8").lower()
        return (
            runtime_python(backend).is_file()
            and "include-system-site-packages = false" in config
        )
    except (OSError, RuntimeError):
        return False


def install_runtime(backend: str | None = None) -> str:
    backend = backend or selected_backend()
    adapter = get_backend(backend)
    adapter.validate_platform()
    with file_lock(runtime_paths().upstream):
        ensure_upstream_checkout()
        folder = _backend_folder(backend)
        folder.mkdir(parents=True, exist_ok=True)
        venv = folder / ".venv"
        uv = shutil.which("uv")
        if not uv:
            raise RuntimeError(
                "uv is required. Install uv and retry; no existing Python environment was changed."
            )
        env = runtime_environment()
        if os.path.lexists(venv):
            if not _venv_ready(backend):
                raise RuntimeError(f"Conflicting runtime venv: {venv}; preserved.")
        else:
            subprocess.run(
                [uv, "venv", "--python", "3.12", str(venv)],
                env=env,
                stdin=subprocess.DEVNULL,
                stdout=sys.stderr,
                check=True,
                timeout=300,
            )
        python = runtime_python(backend)
        if adapter.accelerated:
            _install_torch_dependencies(backend, uv, python, env)
        else:
            _install_optimized_dependencies(uv, python, folder, env)
        downloader = Path(__file__).with_name("download_models.py")
        subprocess.run(
            [
                str(python),
                "-I",
                str(downloader),
                "--backend",
                backend,
                "--root",
                str(folder),
                "--cache",
                env["HF_HUB_CACHE"],
            ],
            env=env,
            stdin=subprocess.DEVNULL,
            stdout=sys.stderr,
            check=True,
            timeout=3600,
        )
        if not backend_ready(backend):
            raise RuntimeError(
                "Runtime installation finished without all required model files."
            )
        _save_backend(backend)
    return backend


def _install_optimized_dependencies(uv, python, folder, env) -> None:
    subprocess.run(
        [
            uv,
            "pip",
            "install",
            "--python",
            str(python),
            "-r",
            str(folder / "requirements.txt"),
            # HF's HTTP transport needs this extra for inherited SOCKS proxies.
            "socksio>=1,<2",
        ],
        env=env,
        stdin=subprocess.DEVNULL,
        stdout=sys.stderr,
        check=True,
        timeout=600,
    )


def _install_torch_dependencies(backend, uv, python, env) -> None:
    adapter = get_backend(backend)
    variant = "cu128" if backend == "cuda" else "rocm6.3"
    version = f"2.7.1+{variant}"
    # Refuse a pre-existing CPU/wrong-vendor/version distribution, rather than
    # replacing it. An empty venv from an interrupted install can be retried.
    subprocess.run(
        [
            str(python),
            "-I",
            "-c",
            "from importlib.metadata import distributions; "
            "import sys; "
            "bad = [d.metadata['Name'] for d in distributions() "
            f"if d.metadata['Name'].lower() in ('torch', 'torchaudio') and d.version != {version!r}]; "
            "sys.exit('Conflicting GPU runtime packages; preserved: ' + ', '.join(bad)) if bad else None",
        ],
        env=env,
        stdin=subprocess.DEVNULL,
        stdout=sys.stderr,
        check=True,
        timeout=30,
    )
    # Direct vendor wheel references keep PyTorch's index from shadowing newer
    # ordinary dependencies on PyPI under uv's safe first-index resolution.
    subprocess.run(
        [
            uv,
            "pip",
            "install",
            "--python",
            str(python),
            *adapter.wheel_requirements(),
            str(runtime_paths().upstream),
            "socksio>=1,<2",
        ],
        env=env,
        stdin=subprocess.DEVNULL,
        stdout=sys.stderr,
        check=True,
        timeout=1800,
    )
    command, cwd = _runtime_command(backend)
    subprocess.run(
        command + ["--probe"],
        cwd=cwd,
        env=env,
        stdin=subprocess.DEVNULL,
        stdout=sys.stderr,
        check=True,
        timeout=120,
    )


def backend_ready(backend: str | None = None) -> bool:
    backend = backend or selected_backend()
    adapter = get_backend(backend)
    folder = _backend_folder(backend)
    script = (
        Path(__file__).with_name("torch_runner.py")
        if adapter.accelerated
        else folder / "scripts" / adapter.script_name
    )
    if not _venv_ready(backend) or not script.is_file():
        return False
    try:
        for path in _model_paths(backend):
            if not path.is_file() or path.stat().st_size == 0:
                return False
            if path.is_symlink() and not path.resolve().is_relative_to(
                data_root().resolve()
            ):
                return False
            if not adapter.model_header_valid(path):
                return False
    except OSError:
        return False
    # TFLite ships a separate tokenizer.model. MLX embeds tokenizer bytes in
    # t5gemma_f16.npz, so requiring the TFLite file would reject a ready Mac runtime.
    return (
        not adapter.requires_tokenizer
        or (folder / "models" / "tokenizer.model").is_file()
    )


def _runtime_command(backend: str) -> tuple[list[str], Path]:
    folder = _backend_folder(backend)
    if get_backend(backend).accelerated:
        return [
            str(runtime_python(backend)),
            "-I",
            str(Path(__file__).with_name("torch_runner.py")),
            "--backend",
            backend,
            "--models",
            str(folder / "models" / backend),
        ], folder
    # No shell or wrapper fallback. -I excludes user-site/PYTHONPATH and CWD imports.
    return [
        str(runtime_python(backend)),
        "-I",
        str(folder / "scripts" / get_backend(backend).script_name),
    ], folder


def _validate_wav(path: Path, seconds: float) -> None:
    try:
        with wave.open(str(path), "rb") as audio:
            rate, frames = audio.getframerate(), audio.getnframes()
            if rate <= 0 or frames == 0 or abs(frames / rate - seconds) > 1 / rate:
                raise ValueError("WAV has an unexpected duration or no audio frames")
            expected = frames * audio.getnchannels() * audio.getsampwidth()
            # Bound read memory independently of requested duration.
            received = 0
            while block := audio.readframes(65536):
                received += len(block)
            if received != expected:
                raise ValueError("WAV data is truncated")
    except (EOFError, wave.Error, ValueError) as exc:
        raise RuntimeError(f"Runtime did not produce a valid WAV: {exc}") from exc


def generate_audio(
    prompt: str,
    seconds: float = 10.0,
    output_path: str | None = None,
    negative_prompt: str | None = None,
) -> Path:
    if (
        not prompt.strip()
        or "\0" in prompt
        or (negative_prompt and "\0" in negative_prompt)
    ):
        raise ValueError("prompt must be non-empty and prompts must not contain NUL")
    if not math.isfinite(seconds) or seconds <= 0 or seconds > 380:
        raise ValueError("seconds must be finite, > 0 and <= 380")
    backend = selected_backend()
    adapter = get_backend(backend)
    adapter.validate_negative_prompt(negative_prompt)
    if not backend_ready(backend):
        raise RuntimeError(
            f"Stable Audio runtime is not ready for '{backend}'. Run the bootstrap installer first."
        )
    verify_upstream_checkout(runtime_paths().upstream)
    paths = runtime_paths()
    destination = (
        Path(output_path).expanduser().absolute()
        if output_path
        else paths.output / f"agent-audio-{uuid.uuid4().hex}.wav"
    )
    if destination.suffix.lower() != ".wav":
        raise ValueError("output_path must have a .wav extension")
    reject_link(destination)
    if destination.exists():
        raise FileExistsError(
            f"Output already exists; choose a new filename: {destination}"
        )
    destination.parent.mkdir(parents=True, exist_ok=True)
    # Serial inference avoids simultaneous native weight-cache writes and memory spikes.
    with file_lock(paths.root / "generation"):
        with tempfile.TemporaryDirectory(
            prefix=".agent-audio-render-", dir=destination.parent
        ) as stage:
            temporary = Path(stage) / "audio.wav"
            command, cwd = _runtime_command(backend)
            # --flag=value keeps leading '-' prompt text from becoming another option.
            command += adapter.generation_arguments(prompt, seconds, temporary)
            env = runtime_environment()
            env["HF_HUB_OFFLINE"] = (
                "1"  # Generation never silently downloads another revision.
            )
            try:
                run_inference(
                    command,
                    cwd,
                    env,
                    GENERATION_TIMEOUT,
                    log_dir=paths.root / "logs",
                )
            except subprocess.TimeoutExpired as exc:
                log_path = getattr(exc, "log_path", None)
                log_hint = f" See local log {log_path}." if log_path else ""
                raise RuntimeError(
                    f"Stable Audio generation exceeded {GENERATION_TIMEOUT} seconds and was stopped.{log_hint}"
                ) from exc
            if not temporary.is_file():
                raise RuntimeError("Runtime completed without producing a WAV.")
            _validate_wav(temporary, seconds)
            # Same-volume hardlink publishes atomically and fails if another writer
            # created the destination. It never replaces existing files/symlinks.
            os.link(temporary, destination)
    return destination

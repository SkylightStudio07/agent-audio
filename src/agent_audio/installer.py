from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import tomllib
from pathlib import Path

from .detect import detect_environment, recommended_backend
from .runtime import (
    backend_ready,
    data_root,
    install_runtime,
    runtime_details,
    runtime_paths,
    selected_backend,
)
from .storage import atomic_write, file_lock, read_optional, reject_link

SKILL_NAME = "audio-production"
MCP_NAME = "agent-audio"
TOOL_TIMEOUT = 600


def repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _venv_python() -> Path:
    folder = repo_root() / ".venv"
    python = (
        folder / "Scripts" / "python.exe"
        if sys.platform == "win32"
        else folder / "bin" / "python"
    )
    if not python.is_file():
        raise RuntimeError(
            "Agent Audio's virtual environment is missing; run uv sync before registration."
        )
    # POSIX venv interpreters are normally symlinks: do not resolve to base Python.
    return python.absolute()


def _tree_bytes(folder: Path) -> dict[str, bytes]:
    reject_link(folder)
    result = {}
    for path in folder.rglob("*"):
        reject_link(path)
        if path.is_file():
            result[path.relative_to(folder).as_posix()] = path.read_bytes()
        elif not path.is_dir():
            raise RuntimeError(f"Unsupported file in Skill: {path}")
    return result


def _copy_skill(destination_root: Path) -> Path:
    source = repo_root() / "skills" / SKILL_NAME
    destination = destination_root / SKILL_NAME
    reject_link(destination_root.parent)
    reject_link(destination_root)
    with file_lock(destination):
        reject_link(destination)
        if destination.exists():
            if destination.is_dir() and _tree_bytes(destination) == _tree_bytes(source):
                return destination
            raise RuntimeError(
                f"Skill conflict at {destination}; existing files were preserved."
            )
        _tree_bytes(source)
        with tempfile.TemporaryDirectory(
            prefix=".agent-audio-", dir=destination_root
        ) as stage:
            staged = Path(stage) / SKILL_NAME
            shutil.copytree(source, staged)
            if os.path.lexists(destination):
                raise RuntimeError(
                    f"Skill destination appeared during installation: {destination}"
                )
            staged.rename(destination)
    return destination


def install_skills() -> dict[str, dict[str, str]]:
    info = detect_environment()
    clients = (
        ("codex", info.codex_installed, ".agents"),
        ("claude", info.claude_installed, ".claude"),
        ("cursor", info.cursor_installed, ".cursor"),
    )
    outcomes = {}
    for name, installed, folder in clients:
        if not installed:
            outcomes[name] = {"status": "not-installed"}
            continue
        try:
            path = _copy_skill(Path.home() / folder / "skills")
            outcomes[name] = {"status": "installed", "path": str(path)}
        except (OSError, RuntimeError, ValueError, subprocess.SubprocessError) as exc:
            outcomes[name] = {"status": "error", "error": str(exc)}
    return outcomes


def _desired(python: Path) -> dict[str, object]:
    return {
        "command": str(python),
        "args": ["-I", "-m", "agent_audio.mcp_server"],
        "env": {"AGENT_AUDIO_HOME": str(data_root())},
    }


def _check_existing(existing: object, desired: dict[str, object]) -> bool:
    if existing is None:
        return False
    if not isinstance(existing, dict):
        raise RuntimeError("Invalid agent-audio MCP entry; refusing to overwrite it.")
    env = existing.get("env", {})
    same_home = (
        isinstance(env, dict)
        and env.get("AGENT_AUDIO_HOME", str(Path.home() / ".agent-audio"))
        == desired["env"]["AGENT_AUDIO_HOME"]
    )
    if (
        existing.get("command") != desired["command"]
        or existing.get("args") != desired["args"]
        or existing.get("type", "stdio") != "stdio"
        or "url" in existing
        or not same_home
    ):
        raise RuntimeError(
            "An agent-audio MCP entry points to a different installation; existing settings were preserved."
        )
    return True


def _native_add(client: str, binary: str, python: Path) -> dict[str, object]:
    """Run native registration in EMPTY temporary config, then merge our entry.

    Never run mcp list (some clients connect to unrelated servers), or allow
    a native CLI to normalize unrelated settings in the real user config.
    """
    with tempfile.TemporaryDirectory(prefix="agent-audio-register-") as directory:
        stage = Path(directory)
        env = os.environ.copy()
        env.update({"CODEX_HOME": str(stage), "CLAUDE_CONFIG_DIR": str(stage)})
        envarg = f"AGENT_AUDIO_HOME={data_root()}"
        if client == "codex":
            command = [
                binary,
                "mcp",
                "add",
                MCP_NAME,
                "--env",
                envarg,
                "--",
                str(python),
                "-I",
                "-m",
                "agent_audio.mcp_server",
            ]
            config = stage / "config.toml"
        else:
            command = [
                binary,
                "mcp",
                "add",
                "--scope",
                "user",
                MCP_NAME,
                "--env",
                envarg,
                "--",
                str(python),
                "-I",
                "-m",
                "agent_audio.mcp_server",
            ]
            config = stage / ".claude.json"
        completed = subprocess.run(
            command,
            cwd=stage,
            env=env,
            stdin=subprocess.DEVNULL,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=60,
            check=False,
        )
        if completed.returncode:
            raise RuntimeError(
                f"{client} MCP registration failed: {(completed.stderr or completed.stdout).strip()}"
            )
        if not config.is_file():
            raise RuntimeError(
                f"{client} did not write its temporary MCP config; user configuration was not edited."
            )
        raw = config.read_text(encoding="utf-8-sig")
        data = tomllib.loads(raw) if client == "codex" else json.loads(raw)
        entry = data.get("mcp_servers" if client == "codex" else "mcpServers", {}).get(
            MCP_NAME
        )
        if not _check_existing(entry, _desired(python)):
            raise RuntimeError(f"{client} did not register the requested server.")
        return entry


def _codex_config() -> Path:
    return (
        Path(os.environ.get("CODEX_HOME", str(Path.home() / ".codex"))).expanduser()
        / "config.toml"
    )


def _timeout_text(text: str, entry: dict[str, object]) -> str:
    if "tool_timeout_sec" in entry:
        return text
    expected = tomllib.loads(text)
    expected["mcp_servers"][MCP_NAME]["tool_timeout_sec"] = TOOL_TIMEOUT
    pattern = r'(?m)^(\[mcp_servers\.(?:agent-audio|"agent-audio"|\x27agent-audio\x27)\][ \t]*(?:#[^\r\n]*)?)(\r?\n|$)'
    for match in re.finditer(pattern, text):
        newline = match.group(2) or "\n"
        updated = (
            text[: match.end()]
            + ("" if match.group(2) else newline)
            + f"tool_timeout_sec = {TOOL_TIMEOUT}"
            + newline
            + text[match.end() :]
        )
        # A header-looking line can be inside a TOML multiline string. Require
        # the parsed change to affect only our actual timeout, never that string.
        try:
            if tomllib.loads(updated) == expected:
                return updated
        except tomllib.TOMLDecodeError:
            continue
    raise RuntimeError(
        "Cannot safely locate the agent-audio Codex table; set tool_timeout_sec manually."
    )


def _configure_codex_timeout(python: Path) -> None:
    config = _codex_config()
    reject_link(config.parent)
    with file_lock(config):
        raw = read_optional(config)
        if raw is None:
            return
        text = raw.decode("utf-8-sig")
        entry = tomllib.loads(text).get("mcp_servers", {}).get(MCP_NAME)
        if not _check_existing(entry, _desired(python)):
            return
        updated = _timeout_text(text, entry)
        prefix = b"\xef\xbb\xbf" if raw.startswith(b"\xef\xbb\xbf") else b""
        atomic_write(config, raw, prefix + updated.encode("utf-8"))


def _register_codex(python: Path) -> str:
    binary = shutil.which("codex")
    if not binary:
        return "not-installed"
    config = _codex_config()
    reject_link(config.parent)
    with file_lock(config):
        raw = read_optional(config)
        text = (raw or b"").decode("utf-8-sig")
        data = tomllib.loads(text)
        servers = data.get("mcp_servers", {})
        if not isinstance(servers, dict):
            raise RuntimeError(f"Invalid MCP config object; preserved {config}")
        existing = servers.get(MCP_NAME)
        if _check_existing(existing, _desired(python)):
            updated = _timeout_text(text, existing)
            result = "already-registered"
        else:
            entry = _native_add("codex", binary, python)
            newline = "\r\n" if "\r\n" in text else "\n"
            lines = [
                "",
                "[mcp_servers.agent-audio]",
                f"command = {json.dumps(entry['command'], ensure_ascii=False)}",
                f"args = {json.dumps(entry['args'], ensure_ascii=False)}",
                f"tool_timeout_sec = {TOOL_TIMEOUT}",
                "",
                "[mcp_servers.agent-audio.env]",
                f"AGENT_AUDIO_HOME = {json.dumps(str(data_root()), ensure_ascii=False)}",
                "",
            ]
            updated = text + newline + newline.join(lines)
            result = "registered"
        parsed = tomllib.loads(updated)
        _check_existing(parsed["mcp_servers"][MCP_NAME], _desired(python))
        prefix = b"\xef\xbb\xbf" if raw and raw.startswith(b"\xef\xbb\xbf") else b""
        atomic_write(config, raw, prefix + updated.encode("utf-8"))
        return result


def _register_json(
    config: Path, python: Path, native: tuple[str, str] | None = None
) -> str:
    reject_link(config.parent)
    with file_lock(config):
        raw = read_optional(config)
        try:
            data = json.loads(raw) if raw is not None else {}
        except (UnicodeError, json.JSONDecodeError) as exc:
            raise RuntimeError(f"Invalid MCP JSON; preserved {config}") from exc
        if not isinstance(data, dict) or not isinstance(
            data.get("mcpServers", {}), dict
        ):
            raise RuntimeError(f"Invalid MCP config object; preserved {config}")
        servers = data.setdefault("mcpServers", {})
        if MCP_NAME in servers and servers[MCP_NAME] is None:
            raise RuntimeError(f"Invalid null agent-audio entry; preserved {config}")
        if _check_existing(servers.get(MCP_NAME), _desired(python)):
            return "already-registered"
        entry = (
            _native_add(*native, python)
            if native
            else {"type": "stdio", **_desired(python)}
        )
        servers[MCP_NAME] = entry
        atomic_write(
            config,
            raw,
            (json.dumps(data, indent=2, ensure_ascii=False) + "\n").encode("utf-8"),
        )
        return "registered"


def _register_claude(python: Path) -> str:
    binary = shutil.which("claude")
    if not binary:
        return "not-installed"
    custom = os.environ.get("CLAUDE_CONFIG_DIR")
    config = (
        Path(custom).expanduser() / ".claude.json"
        if custom
        else Path.home() / ".claude.json"
    )
    return _register_json(config, python, ("claude", binary))


def _register_cursor(python: Path) -> str:
    if not detect_environment().cursor_installed:
        return "not-installed"
    return _register_json(Path.home() / ".cursor" / "mcp.json", python)


def register_agents() -> dict[str, object]:
    python = _venv_python()
    skills = install_skills()
    mcp = {}
    for name, register in (
        ("codex", _register_codex),
        ("claude", _register_claude),
        ("cursor", _register_cursor),
    ):
        try:
            mcp[name] = {"status": register(python)}
        except (OSError, RuntimeError, ValueError, subprocess.SubprocessError) as exc:
            mcp[name] = {"status": "error", "error": str(exc)}
    return {
        "python": str(python),
        "skills": skills,
        "mcp": mcp,
        "success": all(
            outcome["status"] != "error"
            for group in (skills, mcp)
            for outcome in group.values()
        ),
    }


def doctor() -> dict[str, object]:
    info = detect_environment()
    backend = selected_backend(info)
    return {
        "environment": info.to_dict(),
        "recommended_backend": backend,
        "default_backend": recommended_backend(info),
        "runtime_ready": backend_ready(backend),
        "runtime_path": str(runtime_paths().upstream),
        **runtime_details(backend),
        "warnings": [
            message
            for message in (
                "NVIDIA detected: CPU is the default. Opt in to CUDA with --backend cuda; verify generation separately."
                if info.nvidia_detected and backend == "tflite"
                else "",
                "Intel graphics detected: using CPU; XPU acceleration is not enabled."
                if info.intel_graphics_detected
                else "",
                "AMD detected: ROCm is opt-in on supported Linux GPUs. Windows AMD uses TFLite CPU; no DirectML support is claimed."
                if info.amd_graphics_detected and backend == "tflite"
                else "",
            )
            if message
        ],
    }


def perform_install(
    runtime: bool = True, register: bool = True, backend: str | None = None
) -> dict[str, object]:
    result: dict[str, object] = {"doctor_before": doctor()}
    if runtime:
        result["runtime_backend"] = (
            install_runtime(backend) if backend else install_runtime()
        )
    if register:
        result["registration"] = register_agents()
        result["success"] = result["registration"]["success"]
    result["doctor_after"] = doctor()
    return result

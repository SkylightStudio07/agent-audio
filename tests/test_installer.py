import json
import tomllib
from pathlib import Path
from types import SimpleNamespace

import pytest

from agent_audio import installer


def test_cursor_registration_preserves_existing_servers_and_backup(
    tmp_path, monkeypatch
):
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: tmp_path))
    monkeypatch.setattr(
        installer, "detect_environment", lambda: SimpleNamespace(cursor_installed=True)
    )
    config = tmp_path / ".cursor" / "mcp.json"
    config.parent.mkdir()
    original = {"mcpServers": {"unrelated": {"command": "keep-me"}}, "other": 42}
    config.write_text(json.dumps(original), encoding="utf-8")
    assert installer._register_cursor(tmp_path / "python") == "registered"
    after = json.loads(config.read_text("utf-8"))
    assert after["mcpServers"]["unrelated"] == original["mcpServers"]["unrelated"]
    assert after["other"] == 42
    backup = next(config.parent.glob("mcp.json.agent-audio-*.bak"))
    assert json.loads(backup.read_text("utf-8")) == original


def test_codex_timeout_preserves_other_settings_and_is_idempotent(
    tmp_path, monkeypatch
):
    monkeypatch.delenv("AGENT_AUDIO_HOME", raising=False)
    monkeypatch.setenv("CODEX_HOME", str(tmp_path))
    config = tmp_path / "config.toml"
    original = '[mcp_servers.unrelated]\ncommand = "keep"\n\n[mcp_servers.agent-audio]\ncommand = "python"\nargs = ["-I", "-m", "agent_audio.mcp_server"]\n'
    config.write_text(original, encoding="utf-8")
    installer._configure_codex_timeout(Path("python"))
    updated = config.read_text("utf-8")
    assert updated.replace("tool_timeout_sec = 600\n", "") == original
    assert (
        tomllib.loads(updated)["mcp_servers"]["agent-audio"]["tool_timeout_sec"] == 600
    )
    installer._configure_codex_timeout(Path("python"))
    assert config.read_text("utf-8") == updated


def test_codex_timeout_does_not_change_conflicting_registration(tmp_path, monkeypatch):
    monkeypatch.setenv("CODEX_HOME", str(tmp_path))
    config = tmp_path / "config.toml"
    original = '[mcp_servers.agent-audio]\ncommand = "someone-elses-python"\n'
    config.write_text(original, encoding="utf-8")
    with pytest.raises(RuntimeError, match="different installation"):
        installer._configure_codex_timeout(Path("python"))
    assert config.read_text("utf-8") == original


def test_codex_timeout_ignores_header_inside_multiline_string(tmp_path, monkeypatch):
    monkeypatch.delenv("AGENT_AUDIO_HOME", raising=False)
    monkeypatch.setenv("CODEX_HOME", str(tmp_path))
    config = tmp_path / "config.toml"
    original = (
        'notes = """\n[mcp_servers.agent-audio]\nkeep this text\n"""\n'
        '[mcp_servers."agent-audio"] # real entry\n'
        'command = "python"\nargs = ["-I", "-m", "agent_audio.mcp_server"]\n'
    )
    config.write_text(original, encoding="utf-8")
    installer._configure_codex_timeout(Path("python"))
    updated = tomllib.loads(config.read_text("utf-8"))
    expected = tomllib.loads(original)
    expected["mcp_servers"]["agent-audio"]["tool_timeout_sec"] = 600
    assert updated == expected


def test_codex_registration_supports_non_bmp_paths(tmp_path, monkeypatch):
    monkeypatch.setenv("CODEX_HOME", str(tmp_path))
    home = tmp_path / "audio-\U0001f3b5"
    python = tmp_path / "python-\U0001f40d"
    monkeypatch.setenv("AGENT_AUDIO_HOME", str(home))
    monkeypatch.setattr(installer.shutil, "which", lambda _: "codex")
    monkeypatch.setattr(installer, "_native_add", lambda *a: installer._desired(python))
    assert installer._register_codex(python) == "registered"
    entry = tomllib.loads((tmp_path / "config.toml").read_text("utf-8"))["mcp_servers"][
        "agent-audio"
    ]
    assert entry["command"] == str(python)
    assert entry["env"]["AGENT_AUDIO_HOME"] == str(home)


def test_skill_conflict_is_not_deleted(tmp_path, monkeypatch):
    source = tmp_path / "repo" / "skills" / installer.SKILL_NAME
    source.mkdir(parents=True)
    (source / "SKILL.md").write_text("new skill")
    monkeypatch.setattr(installer, "repo_root", lambda: tmp_path / "repo")
    dest = tmp_path / "skills" / installer.SKILL_NAME
    dest.mkdir(parents=True)
    (dest / "custom.txt").write_text("keep my work")
    with pytest.raises(RuntimeError, match="Skill conflict"):
        installer._copy_skill(dest.parent)
    assert (dest / "custom.txt").read_text() == "keep my work"


def test_skill_reinstall_is_idempotent(tmp_path, monkeypatch):
    source = tmp_path / "repo" / "skills" / installer.SKILL_NAME
    source.mkdir(parents=True)
    (source / "SKILL.md").write_text("same skill")
    monkeypatch.setattr(installer, "repo_root", lambda: tmp_path / "repo")
    dest = installer._copy_skill(tmp_path / "skills")
    stamp = (dest / "SKILL.md").stat().st_mtime_ns
    assert installer._copy_skill(tmp_path / "skills") == dest
    assert (dest / "SKILL.md").stat().st_mtime_ns == stamp


@pytest.mark.parametrize(
    "payload",
    [
        "[]",
        "{",
        '{"mcpServers": []}',
        '{"mcpServers": {"agent-audio": null}}',
        '{"mcpServers": {"agent-audio": {"command": "other"}}}',
    ],
)
def test_json_conflicts_and_invalid_files_preserved(tmp_path, payload):
    config = tmp_path / "mcp.json"
    config.write_text(payload)
    with pytest.raises(RuntimeError):
        installer._register_json(config, Path("python"))
    assert config.read_text() == payload


def test_codex_registration_preserves_exact_prefix_and_custom_home(
    tmp_path, monkeypatch
):
    monkeypatch.setenv("CODEX_HOME", str(tmp_path))
    monkeypatch.setenv("AGENT_AUDIO_HOME", str(tmp_path / "audio home"))
    monkeypatch.setattr(installer.shutil, "which", lambda _: "codex")
    calls = []

    def native(*args):
        calls.append(args)
        return installer._desired(Path("python"))

    monkeypatch.setattr(installer, "_native_add", native)
    config = tmp_path / "config.toml"
    original = b'# keep comments\r\n[mcp_servers.agent-audio-other]\r\ncommand = "keep"\r\nargs = []\r\n'
    config.write_bytes(original)
    assert installer._register_codex(Path("python")) == "registered"
    after = config.read_bytes()
    assert after.startswith(original)
    entry = tomllib.loads(after.decode())["mcp_servers"]["agent-audio"]
    assert entry["env"]["AGENT_AUDIO_HOME"] == str(tmp_path / "audio home")
    assert entry["args"][0] == "-I"
    assert installer._register_codex(Path("python")) == "already-registered"
    assert config.read_bytes() == after
    assert len(calls) == 1


def test_native_codex_cli_uses_empty_temporary_config(tmp_path, monkeypatch):
    monkeypatch.setenv("CODEX_HOME", str(tmp_path / "real"))
    monkeypatch.setenv("AGENT_AUDIO_HOME", str(tmp_path / "audio"))

    def fake_run(command, **kwargs):
        stage = Path(kwargs["env"]["CODEX_HOME"])
        assert stage != tmp_path / "real"
        assert command[1:3] == ["mcp", "add"]
        assert not (stage / "config.toml").exists()
        (stage / "config.toml").write_text(
            '[mcp_servers.agent-audio]\ncommand="python"\nargs=["-I","-m","agent_audio.mcp_server"]\n'
            "[mcp_servers.agent-audio.env]\nAGENT_AUDIO_HOME="
            + json.dumps(str(tmp_path / "audio"))
            + "\n"
        )
        return SimpleNamespace(returncode=0)

    monkeypatch.setattr(installer.subprocess, "run", fake_run)
    assert (
        installer._native_add("codex", "codex", Path("python"))["command"] == "python"
    )
    assert not (tmp_path / "real").exists()


def test_claude_custom_config_directory(tmp_path, monkeypatch):
    monkeypatch.setenv("CLAUDE_CONFIG_DIR", str(tmp_path))
    monkeypatch.setattr(installer.shutil, "which", lambda _: "claude")
    monkeypatch.setattr(
        installer,
        "_native_add",
        lambda *a: {"type": "stdio", **installer._desired(Path("python"))},
    )
    assert installer._register_claude(Path("python")) == "registered"
    assert (
        "agent-audio"
        in json.loads((tmp_path / ".claude.json").read_text())["mcpServers"]
    )


def test_doctor_needs_no_network(tmp_path, monkeypatch):
    import socket

    monkeypatch.setenv("AGENT_AUDIO_HOME", str(tmp_path))

    def no_network(*args, **kwargs):
        pytest.fail("doctor attempted network access")

    monkeypatch.setattr(socket, "socket", no_network)
    result = installer.doctor()
    assert result["runtime_ready"] is False
    assert Path(result["runtime_path"]).is_relative_to(tmp_path)


def test_registration_reports_partial_results_and_continues(tmp_path, monkeypatch):
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: tmp_path))
    monkeypatch.setattr(installer, "_venv_python", lambda: Path("python"))
    monkeypatch.setattr(
        installer,
        "detect_environment",
        lambda: SimpleNamespace(
            codex_installed=True, claude_installed=True, cursor_installed=False
        ),
    )
    calls = []

    def copy(root):
        calls.append(root.parent.name)
        if root.parent.name == ".agents":
            raise RuntimeError("Skill conflict; preserved")
        return root / installer.SKILL_NAME

    def conflict(python):
        raise RuntimeError("MCP conflict; preserved")

    monkeypatch.setattr(installer, "_copy_skill", copy)
    monkeypatch.setattr(installer, "_register_codex", conflict)
    monkeypatch.setattr(installer, "_register_claude", lambda python: "registered")
    monkeypatch.setattr(installer, "_register_cursor", lambda python: "not-installed")
    result = installer.register_agents()
    assert calls == [".agents", ".claude"]
    assert result["success"] is False
    assert result["skills"]["codex"]["status"] == "error"
    assert result["skills"]["claude"]["status"] == "installed"
    assert result["mcp"]["codex"]["error"] == "MCP conflict; preserved"
    assert result["mcp"]["claude"]["status"] == "registered"


@pytest.mark.parametrize("entrypoint", ["cli", "bootstrap"])
def test_registration_entrypoints_print_partial_results_and_fail(
    entrypoint, monkeypatch, capsys
):
    if entrypoint == "cli":
        from agent_audio import cli as module

        arguments = ["agent-audio", "register"]
    else:
        import importlib.util

        spec = importlib.util.spec_from_file_location(
            "bootstrap_test", installer.repo_root() / "install" / "bootstrap.py"
        )
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        arguments = ["bootstrap.py", "--register-only"]
    monkeypatch.setattr(module, "register_agents", lambda: {"success": False})
    monkeypatch.setattr("sys.argv", arguments)
    with pytest.raises(SystemExit) as failure:
        module.main()
    assert failure.value.code == 1
    assert json.loads(capsys.readouterr().out) == {"success": False}


def test_linked_config_directory_preserved(tmp_path):
    real = tmp_path / "real"
    real.mkdir()
    (real / "mcp.json").write_text("{}")
    link = tmp_path / "linked"
    try:
        link.symlink_to(real, target_is_directory=True)
    except OSError:
        pytest.skip("symlink creation privilege unavailable")
    with pytest.raises(RuntimeError, match="link"):
        installer._register_json(link / "mcp.json", Path("python"))
    assert (real / "mcp.json").read_text() == "{}"
    assert sorted(p.name for p in real.iterdir()) == ["mcp.json"]


def test_linked_skill_client_directory_preserved(tmp_path):
    real = tmp_path / "real"
    real.mkdir()
    link = tmp_path / "client"
    try:
        link.symlink_to(real, target_is_directory=True)
    except OSError:
        pytest.skip("symlink creation privilege unavailable")
    with pytest.raises(RuntimeError, match="link"):
        installer._copy_skill(link / "skills")
    assert not list(real.iterdir())


def test_invalid_codex_server_container_preserved(tmp_path, monkeypatch):
    monkeypatch.setenv("CODEX_HOME", str(tmp_path))
    monkeypatch.setattr(installer.shutil, "which", lambda _: "codex")
    config = tmp_path / "config.toml"
    original = 'mcp_servers = ["unexpected"]\n'
    config.write_text(original)
    with pytest.raises(RuntimeError, match="Invalid MCP config object"):
        installer._register_codex(Path("python"))
    assert config.read_text() == original


def test_install_propagates_registration_failure(monkeypatch):
    monkeypatch.setattr(installer, "doctor", lambda: {"runtime_ready": False})
    monkeypatch.setattr(installer, "register_agents", lambda: {"success": False})
    result = installer.perform_install(runtime=False)
    assert result["success"] is False
    assert result["registration"] == {"success": False}
    assert result["doctor_after"] == {"runtime_ready": False}

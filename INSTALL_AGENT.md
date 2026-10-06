# Agent installation guide

This procedure is for AI coding agents installing Agent Audio. Automate the available installation steps while respecting the user's control over licenses, credentials and system changes.

## Required rules

1. Never accept Stability AI, Gemma, Hugging Face or other third-party terms on the user's behalf.
2. Do not expose authentication tokens in chat or logs.
3. Never replace an existing MCP configuration wholesale. Merge safely and create a backup before editing.
4. Do not require ComfyUI or fall back to an existing audio environment. Use dedicated runtime and model paths.
5. Prefer user-local installation. Avoid administrator/root privileges unless genuinely required.
6. If acceleration setup fails, use a fallback supported and verified by the current implementation. Do not assume an unimplemented automatic fallback exists.
7. Report the backend actually installed. Never claim CUDA, XPU or Metal acceleration without verification.
8. Preserve and report conflicting Skills, MCP entries and runtimes. Do not reset or delete existing directories; use a separate `AGENT_AUDIO_HOME` when needed.

## 1. Inspect the repository

Read:

- [README.md](README.md)
- [skills/audio-production/SKILL.md](skills/audio-production/SKILL.md)
- [models/registry.json](models/registry.json)
- [SECURITY.md](SECURITY.md)

## 2. Inspect the environment

Check and record:

- Operating system, CPU architecture and GPU vendor.
- NVIDIA tooling, Apple Silicon and Intel graphics detection.
- Installed agent clients: Codex, Claude Code and Cursor.
- Python, `uv` and Git availability.
- Total and currently available system RAM, and free disk space on the installation volume.

Compare with the [disk and memory guidance](docs/resource-requirements.md) and report possible resource shortages before installation. For the Windows CPU configuration, recommend at least 25 GB of free disk space and a 32 GB class RAM system for planning. These are not verified minimum specs: do not promise success or failure on 8/16 GB systems. The [macOS MLX report](docs/macos-mlx-validation.md) records a short generation on a 24 GiB host and 6.41 GiB of model files, but no peak memory or total installation size measurement. Verify the current host separately. Never delete existing user files, models or caches to free space without authorization.

Do not infer acceleration support from a GPU name alone. Do not start unrelated existing MCP servers during installation.

## 3. Prepare Python tooling

Use Python 3.11+ and `uv` for the MCP application. The separate audio runtime virtual environment uses Python 3.12.

If `uv` is missing, use the platform's normal user-local installation method. Get user approval before any package-manager action that requires administrator privileges.

Run from the repository root:

```text
uv sync --frozen
```

## 4. Run diagnostics

```text
uv run --frozen python install/bootstrap.py --doctor
```

Review the selected backend, actual paths, readiness and warnings. `--doctor` must work without network access.
File readiness is not a generation test. Inspect the separate `readiness`
fields; model checksums, dependency health and inference are not tested by doctor.

## 5. Install the Stable Audio runtime and models

```text
uv run --frozen python install/bootstrap.py --runtime-only
```

The installer fetches Stability AI's official `stable-audio-3` runtime at a pinned commit into the dedicated Agent Audio data directory. The default is `~/.agent-audio`; set `AGENT_AUDIO_HOME` to choose another location. Models also use a pinned revision and a dedicated cache.

The dedicated runtime also installs `socksio` for SOCKS support in current
HTTPX-based Hugging Face clients. Existing proxy settings are preserved; the
installer does not configure or bypass a proxy. This does not add SOCKS support
to older, Requests-based Hugging Face clients retained in an existing venv.

If an earlier Linux installation contains broken model symlinks, choose a new
`AGENT_AUDIO_HOME`. The installer preserves conflicting existing paths rather
than replacing them automatically.

If model access requires authentication or license acceptance, stop at that step and ask the user to complete it. Resume only after the user has acted.

### Backend policy

- Apple Silicon: select the official optimized MLX runtime. Verify real generation separately on that hardware.
- Other systems: use the official TFLite/LiteRT CPU runtime as the default.
- NVIDIA acceleration: not auto-selected. The opt-in adapter requires separate real generation validation on the current OS.
- CUDA is now an opt-in adapter: `uv run --frozen python install/bootstrap.py --runtime-only --backend cuda` on Windows/Linux x86-64.
- AMD ROCm is opt-in: use `--runtime-only --backend rocm` on Linux x86-64 with a ROCm 6.3 supported GPU and OS. Windows AMD remains on CPU; DirectML is not implemented.
- Intel XPU: not currently enabled. Intel systems must remain functional through the CPU backend.

See [GPU backend setup](docs/gpu-backends.md). Successful installation saves the
backend selection for MCP clients, including Claude Code. Each GPU runtime is
separate from the CPU/MLX runtime. A GPU kernel probe runs before gated-model
downloads and does not prove Stable Audio inference. These adapters still need
real generation validation; report that limitation. The default remains CPU
outside Apple Silicon until explicitly selected. Installation failure retains
the previous selection and never silently switches to another model/backend.

## 6. Register MCP and Skill

```text
uv run --frozen python install/bootstrap.py --register-only
```

Use the following user-level Skill destinations for detected clients:

| Client | Skill directory |
|---|---|
| Codex | `~/.agents/skills/audio-production/` |
| Claude Code | `~/.claude/skills/audio-production/` |
| Cursor | `~/.cursor/skills/audio-production/` |

Use the same repository Skill source for every client. Do not maintain divergent client-specific copies.

Register a stdio MCP server named `agent-audio`:

- Codex and Claude Code: run their native CLI registration commands with an empty temporary configuration, then merge only the Agent Audio entry into the actual configuration.
- Cursor: merge into `~/.cursor/mcp.json` while preserving existing entries.
- Use the repository's dedicated `.venv` Python with `-I -m agent_audio.mcp_server`.
- Persist `AGENT_AUDIO_HOME` in new entries. Set a 600-second tool timeout for new Codex entries.

Do not duplicate a matching registration. Legacy entries without `-I`, or entries pointing to a different installation, are reported as conflicts. Review the existing Agent Audio entry and migrate according to the user's instructions. Do not change unrelated settings or Skills.
Read every per-client Skill and MCP outcome. Independent registration continues
after a conflict, but a partial failure returns `success: false` and exit code 1.
Report partial successes and remaining conflicts explicitly.

## 7. Reload clients only when needed

A client may need a fresh session to discover the new MCP server or Skill. Reopen only the relevant client; do not restart unrelated services.

## 8. Verify real generation

First call `audio_status` through MCP and inspect the runtime Python and model paths. Then generate a short asset with the MCP `generate_audio` tool:

```json
{
  "prompt": "A clean cinematic metallic impact, isolated one-shot, no music, no voice.",
  "seconds": 3
}
```

Use the default output folder or a new path in a test directory. Verify WAV existence, nonzero size, duration and actual output path. Do not add test audio to the user's active project unless requested.

Record the MCP client used for the test. A standalone stdio client verifies the
server and generation path; it does not verify tool discovery or invocation in
the registered application's fresh chat. Report those checks separately.
Record sample rate, channel count and sample format. When inspecting samples,
report silence, non-finite values and peak/RMS levels separately from a listening
assessment. Valid WAV data alone does not establish prompt adherence or quality.

## 9. Report completion

Report only verified facts:

- Backend and model actually used for installation and generation.
- Actual runtime, Python, model and cache paths, and readiness.
- MCP and Skill registration results per client, including Skill paths.
- MCP call results and generated WAV path, size and duration.
- Any fallback in use and anything not verified.
- Configuration conflicts and steps requiring manual intervention.
- Agent Audio commit, runtime/model pins, OS, hardware and dependency versions.
- Whether results were observed directly or supplied in an external report.

Keep reproducible test scripts and logs in the user's test directory, and report
their paths. Share only reviewed, sanitized evidence: omit credentials, private
configuration and personal paths from public documentation. Record whether
timings include startup and model loading, and whether caches were warm; if
unknown, say so rather than treating one run as a general performance benchmark.

State unsupported functionality explicitly and preserve the verified working path.
The current MCP exposes text-to-audio generation, not audio editing, inpainting
or continuation. Distinguish those unavailable interfaces from supported
operations whose duration or quality has not yet been tested.

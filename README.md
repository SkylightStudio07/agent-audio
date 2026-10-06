# Agent Audio

**Give your coding agent local audio generation for games and videos.**

Agent Audio provides an MCP server and an Agent Skill, without requiring ComfyUI
or a paid audio-generation API. It installs its own runtime and uses Stable
Audio 3 Medium to generate audio on your computer.

Ask your agent to build or edit something, with useful sound effects handled
as part of the task. The goal is to review the finished result, not manage a
separate audio-production workflow.

**Early preview (v0.1).** Short audio generation has been demonstrated in the
[environments below](#current-status). Automatic use during game/video work and
listening quality still need end-to-end validation.

[Install](#install-with-an-ai-agent) · [Usage](#using-agent-audio) ·
[Support and limits](#current-status) · [Update](#updating-an-existing-installation) ·
[Get help](#troubleshooting-and-help)

For step-by-step commands, including Hugging Face access and Claude Code in
VS Code, go to [manual installation](#manual-developer-setup).

## Before you install

Use a local coding agent with command execution and configuration access.
Codex, Claude Code and Cursor are the initial registration targets. Your agent
can check Git, Python 3.11+ and `uv`; the audio runtime uses Python 3.12.

<a id="disk-space-and-memory"></a>

| Environment | Plan for |
|---|---|
| Windows CPU setup | **25 GB or more free disk space and a 32 GB-class RAM system recommended.** Model downloads are about **7.36 GB**; packages and caches are additional. No dedicated GPU is required. |
| Apple Silicon setup | A short generation is reported on a **24 GiB** Mac, with **6.88 GB** of MLX model files. Total installation size and peak memory have not been measured. |
| CUDA / ROCm setup | Medium checkpoint and bundled encoder/tokenizer downloads total about **10.44 GB**. GPU packages, download caches and interrupted transfers need additional space. A 16 GiB RTX 5060 Ti passed a short Windows generation; this is not a minimum VRAM specification. |

These are planning guidance and observations, **not verified minimum specs**.
Smaller machines and longer generations need separate validation. See
[resource measurements](docs/resource-requirements.md) for the full conditions.

Local generation has **no audio-service subscription or per-generation API fee**.
Agent subscriptions, hardware and electricity are separate. You must accept any
required model terms and complete authentication yourself; see
[licenses](#license). Initial installation downloads the runtime and models.

## Install with an AI agent

Paste this into your coding agent:

```text
Install Agent Audio from https://github.com/AIEGOBOT/agent-audio.
Read INSTALL_AGENT.md first and follow its instructions.
Check my OS, hardware, RAM, disk space, Python, uv and installed agent clients.
Install the dedicated runtime and models, then register the MCP server and
audio-production Skill. Preserve existing settings and report conflicts.
Do not accept model licenses or bypass permissions on my behalf.
Verify a short WAV through MCP and report what worked, what was not tested,
and any remaining steps I need to complete.
```

For an NVIDIA GPU, add: `Use --backend cuda on supported Windows/Linux x86-64.`
For a supported Linux AMD GPU, add: `Use --backend rocm after checking ROCm 6.3
compatibility.` Without an explicit choice, Apple Silicon uses MLX and other
systems default to CPU. Windows AMD acceleration is not implemented.

The agent should report the installed backend, client registration results and
test WAV path. If the client does not discover the new tools or Skill, start a
fresh session. Installation permissions, credentials and license acceptance
remain under your control.

Already installed? See [updating](#updating-an-existing-installation).
Prefer commands? See [manual setup](#manual-developer-setup).

<a id="goal"></a>

## Using Agent Audio

After setup, work in your game or video project and make an ordinary production
request. For example:

**Game task**

> Finish the enemy hit reaction and victory feedback in this small game.
> Keep the existing visual style and make the feature ready to play.

**Video task**

> Edit these clips into a 20-second product teaser with clean transitions and
> a finished end card, using the tools already available in this project.

These are examples of intended use, not validated demos. The Skill guides the
agent to reuse suitable audio, generate missing sounds when useful, and connect
them to the requested work. A separate sound request, audio-plan approval or
candidate-selection step is not the default workflow. Explicit sound requests
also work through the same tools.

The agent needs access to the project and appropriate editing tools to apply
the files. It should respect existing assets, intentional silence and requests
for no audio. The MCP server generates WAVs; it is not a game engine or video
editor, and the Skill does not guarantee that every agent will invoke it.

## Current status

| Environment or client | Current implementation and evidence |
|---|---|
| Windows | TFLite/LiteRT CPU is the default. Independent installation and a 3-second, 44.1 kHz stereo WAV through MCP are documented. |
| Apple Silicon macOS | MLX is selected. A user-provided report dated 2026-10-03 records a 3-second WAV on an M5 Pro with 24 GiB memory via a standalone stdio MCP client. |
| Linux and other CPU environments | The installer selects the CPU path outside Apple Silicon. Linux has model-free CI coverage; this is not verified model inference support. |
| NVIDIA CUDA | Opt-in PyTorch adapter on Windows/Linux x86-64 (`--backend cuda`), using CUDA 12.8 wheels. A 3-second WAV through standalone stdio MCP was verified on Windows with an RTX 5060 Ti; Linux and other GPUs remain unverified. |
| AMD ROCm | Opt-in PyTorch adapter on Linux x86-64 (`--backend rocm`), using ROCm 6.3 wheels. Requires a GPU and OS supported by that ROCm release; real generation has not been validated. Windows AMD uses CPU. |
| Intel graphics | CPU fallback; XPU acceleration is not enabled. |
| Codex / Claude Code / Cursor | MCP and Skill registration are implemented. Registration alone does not establish fresh-session discovery, automatic use or completed project integration. |

See the [Windows CUDA validation](docs/windows-cuda-validation.md),
[Windows CPU measurements](docs/resource-requirements.md) and
[macOS report](docs/macos-mlx-validation.md) for conditions and evidence limits.

### Opt-in GPU installation for Claude Code and other clients

Run from the repository root after `uv sync --frozen`:
Complete the [model access and authentication steps](#3-accept-model-terms-and-authenticate)
first if access is gated. See [manual installation](#manual-developer-setup) for
the full procedure.

```text
# NVIDIA, Windows or Linux x86-64
uv run --frozen python install/bootstrap.py --backend cuda

# AMD, supported ROCm 6.3 GPU on Linux x86-64
uv run --frozen python install/bootstrap.py --backend rocm
```

These commands install a dedicated GPU runtime and register the existing MCP
tools and audio-production Skill with detected clients, including Claude Code.
After successful installation, the selection is saved under `AGENT_AUDIO_HOME`
in `backend.json`; `audio_status` and `generate_audio` use it in subsequent
sessions. Start a fresh Claude Code session and check `audio_status` before a
short generation. Registration is not proof of Claude discovery or generation.

GPU adapters use the official Medium PyTorch checkpoint and its bundled T5Gemma
encoder at a separate immutable revision. Accept the model's license yourself
and provide authorized Hugging Face credentials when required. Existing CPU/MLX
models and environments are retained. Peak GPU memory and listening quality
have not been measured for these adapters; CPU resource measurements do not
apply to them.
See [the GPU setup guide](docs/gpu-backends.md) for prerequisites and limitations.
Model-free CI runs on Windows, macOS and Linux. A valid WAV or passing CI does
not establish listening quality or successful game/video integration; those
remain separate [end-to-end checks](docs/end-to-end-validation.md).

### Known limits

The current interface is **text-to-WAV generation**, not audio-to-audio editing,
inpainting or continuation. Nonempty negative prompts are rejected; describe
the desired sound in the main prompt. Existing output files are not overwritten,
and the output filesystem must support hardlinks.

CPU generation can be slow, and long requests can hit the 540-second inference
timeout. Start with short sounds. Other models, accelerators and client
combinations are directions to validate, not blanket support promises.

## Updating an existing installation

**Updating the Git checkout does not update an installed Skill copy.** Ask your
agent to preserve local changes, update the checkout and compare the complete
installed `audio-production` folder with the repository version.

Review and authorize any Skill replacement. Keep the old copy outside all Skill
discovery folders, preserve customizations, then register the new copy and start
a fresh session. Do not reinstall models just to refresh a Skill. Runtime and
MCP conflicts need separate review, not deletion of existing environments or
unrelated settings. Your agent can follow the
[detailed update procedure](docs/end-to-end-validation.md#existing-installations).

## Troubleshooting and help

| Symptom | First check |
|---|---|
| Tools or Skill are missing | Start a fresh client session and ask the agent to check that client's MCP and Skill registration outcomes. |
| Setup reports a conflict | Review the existing paths and settings. A conflict means they were preserved, not that they should be deleted. See [updating](#updating-an-existing-installation). |
| Models are missing or access is denied | Let the agent identify the missing files or access step. Complete required authentication and model-license acceptance yourself. |
| Generation fails or times out | Try a short request and inspect the reported backend and local error log. `audio_status` reports prerequisites, not a successful generation test. |
| A WAV exists but is not used in the project | Check the agent's access to the project and its editing tools. File generation and final integration are separate steps. |
| PowerShell refuses a `.ps1` login script | Use the inline environment variables and `uv tool run ... hf auth login` commands below. No execution-policy change or administrator terminal is needed. |
| VS Code Claude is installed, but registration says `not-installed` | Check `claude --version` in the terminal running bootstrap. The installer detects the CLI on PATH; the extension alone may not expose it. Follow [client preparation](#1-prepare-tools-and-your-agent-client). |
| Download appears stuck | Open file sizes can update late on Windows. Check transfer activity before cancelling. The optional HTTP retry below preserves authentication and model pins. |
| CUDA / ROCm setup or generation fails | Check driver/device compatibility and the failure log. GPU failure does not silently switch to CPU. Select `--backend tflite` explicitly if you want the CPU path. |

Search [existing issues](https://github.com/AIEGOBOT/agent-audio/issues) or
[report a problem](https://github.com/AIEGOBOT/agent-audio/issues/new). Include OS,
RAM, CPU/GPU, client/version, Agent Audio commit, backend, reproduction steps
and the exact error. State whether setup, generation or integration failed.

Review logs before sharing. **Do not post credentials, full client configuration,
private prompts or personal paths.** Follow [SECURITY.md](SECURITY.md) for security
concerns rather than posting sensitive details publicly.

<a id="model-licenses"></a>

## License

Agent Audio source code is [MIT licensed](LICENSE). Model weights are not
included in this repository. Stable Audio 3 Medium is distributed separately
under Stability AI's Community License, with T5Gemma components subject to Gemma
terms. You must review applicable model terms; the source-code license does not
replace them. See [third-party notices](THIRD_PARTY_NOTICES.md).

## Technical and developer reference

### What this project provides

Agent Audio supplies dedicated setup, MCP/client registration, runtime and file
management, and the audio-production Skill. Stability AI supplies the models and
inference implementations; the MCP Python SDK supplies the protocol framework.
The calling agent and its project tools handle final integration.

This is an integration tool, not a newly trained model. See
[architecture](ARCHITECTURE.md) and [project direction](docs/project-direction.md).

### Manual developer setup

Use a normal user terminal. Run repository commands from the cloned
`agent-audio` directory, not `C:\Windows\System32`. Keep the checkout in a
permanent location: MCP registrations refer to its `.venv`, so moving or deleting
it later breaks that registration. Review [INSTALL_AGENT.md](INSTALL_AGENT.md)
and [SECURITY.md](SECURITY.md) before changing an existing installation.

#### 1. Prepare tools and your agent client

Install [Git](https://git-scm.com/downloads),
[uv](https://docs.astral.sh/uv/getting-started/installation/) and Python 3.11+
using their normal user installation procedures. The isolated audio runtime
uses Python 3.12; uv can download it if it is not already available. Initial
setup needs network access, sufficient disk space and permission to install
user-local packages. Audio generation uses local files afterwards.

Check the terminal can find the tools:

```text
git --version
uv --version
```

For Claude Code, install the
[official CLI](https://code.claude.com/docs/en/setup) and, if desired, its VS Code
extension. **The installer detects `claude` on PATH.** A working extension does
not necessarily make the standalone CLI discoverable. Check:

```text
claude --version
```

On Windows, the native CLI commonly installs to `%USERPROFILE%\.local\bin`.
If that directory is missing from your user PATH, add it and open a new terminal;
VS Code may need reopening to inherit the new PATH. Do not change unrelated PATH
entries. For Codex or Cursor, likewise check the relevant CLI is discoverable.
You do not need to install all three clients.

The VS Code Claude extension and CLI share MCP registration. You can keep using
Claude in VS Code; the standalone CLI here supplies the installer's registration
command. Authenticate in the client you actually use. Hugging Face login below
is a separate account and does not log you in to Claude.

#### 2. Clone and choose the data directory

```bash
git clone https://github.com/AIEGOBOT/agent-audio.git
cd agent-audio
uv sync --frozen
```

Data defaults to `~/.agent-audio`. Choose a private, user-owned directory on a
drive with sufficient space **before authentication, installation and
registration**. Do not point it at an unrelated runtime. The following examples
use `G:\AgentAudio` on Windows and the default location on Linux/macOS; change
the path to suit your machine.

**Windows PowerShell**

```powershell
$env:AGENT_AUDIO_HOME = 'G:\AgentAudio'
$env:HF_HOME = Join-Path $env:AGENT_AUDIO_HOME 'cache\huggingface'
$env:HF_HUB_CACHE = Join-Path $env:HF_HOME 'hub'
$env:HF_XET_CACHE = Join-Path $env:HF_HOME 'xet'
# Optional: keep uv's package cache on the same drive too.
$env:UV_CACHE_DIR = Join-Path $env:AGENT_AUDIO_HOME 'cache\uv'
```

**Linux/macOS shell**

```bash
export AGENT_AUDIO_HOME="$HOME/.agent-audio"
export HF_HOME="$AGENT_AUDIO_HOME/cache/huggingface"
export HF_HUB_CACHE="$HF_HOME/hub"
export HF_XET_CACHE="$HF_HOME/xet"
# Optional:
export UV_CACHE_DIR="$AGENT_AUDIO_HOME/cache/uv"
```

These assignments affect the current terminal. Repeat them when you open
another terminal to resume installation or use the CLI. New MCP registrations
save `AGENT_AUDIO_HOME`, so client calls use that directory without requiring
these assignments in every chat. The runtime sets its own private model cache.
An account logged in under a different HF cache is not automatically reused.

Run diagnostics and inspect the output:

```text
uv run --frozen python install/bootstrap.py --doctor
```

Before installation, `runtime_ready: false` is expected. Doctor reports the
default or previously saved backend, detected clients, paths and warnings.
It does not download models, test inference or prove GPU acceleration.

#### 3. Accept model terms and authenticate

| Backend | Model repository |
|---|---|
| CUDA / ROCm | [stabilityai/stable-audio-3-medium](https://huggingface.co/stabilityai/stable-audio-3-medium), including its bundled T5Gemma encoder |
| TFLite CPU / MLX | [stabilityai/stable-audio-3-optimized](https://huggingface.co/stabilityai/stable-audio-3-optimized) |

In your browser, sign in to Hugging Face and open the repository for your
backend. Read the displayed licenses, complete any required access form and
submit the agreement/access request yourself. Button text can vary, for example
`Agree and access repository` or `Request access`. If access is pending, wait
for approval. Agent Audio cannot approve it or accept the terms for you.

With the private HF environment variables from step 2 still set, run this
command in PowerShell or your Linux/macOS terminal:

```text
uv tool run --from "huggingface-hub>=1,<2" hf auth login --no-add-to-git-credential
```

Follow the browser or token instructions shown by the CLI and use the **same
Hugging Face account that received model access**. This temporary CLI does not
install the audio inference runtime. If you use a token, create one with read
access to the required gated repository; provide it only through the login
prompt. Never paste it into chat, Git, screenshots or a command's `--token`
argument. Login is needed when the chosen repository requires authentication;
public downloads may not need it, but model terms still apply.

This inline procedure avoids running a `.ps1` script, so PowerShell's script
execution policy does not need to be disabled. An HTTP 401/403 during model
download means access or authentication still needs attention; retrying with
another backend is not a substitute for the required agreement.

#### 4. Install one runtime backend

Choose **one** command from this table. GPU support is opt-in; a GPU name alone
does not establish compatibility.

| Your environment | Runtime-only command |
|---|---|
| NVIDIA, Windows/Linux x86-64, CUDA 12.8-compatible driver | `uv run --frozen python install/bootstrap.py --runtime-only --backend cuda` |
| AMD, Linux x86-64, ROCm 6.3-supported GPU/OS/driver | `uv run --frozen python install/bootstrap.py --runtime-only --backend rocm` |
| Windows AMD, Intel graphics, or an explicitly selected CPU path | `uv run --frozen python install/bootstrap.py --runtime-only --backend tflite` |
| Apple Silicon macOS | `uv run --frozen python install/bootstrap.py --runtime-only --backend mlx` |

Omit `--backend` for the default: MLX on Apple Silicon, TFLite CPU elsewhere,
or the backend saved by a previous successful install. **NVIDIA and AMD are not
automatically selected.** See [GPU prerequisites](docs/gpu-backends.md) before
choosing CUDA or ROCm. The installer does not install GPU drivers. Windows AMD
GPU acceleration, DirectML and Intel XPU are not implemented.

The installer verifies the official upstream checkout, creates a separate
runtime venv, installs dependencies and downloads revision-pinned models.
For GPU backends it also runs a native GPU kernel probe before downloading
weights. On success it saves the selection in `backend.json`. A failed install
keeps the previous selection; existing CPU/MLX models and environments remain
intact. A kernel probe is not a successful audio generation test.

If access was denied, complete step 3 and rerun the same command with the same
data/cache variables. If installation reports a conflicting runtime or model,
preserve it and inspect the conflict. Use a separate data directory when
appropriate; do not delete user files to make installation pass.

**Optional HTTP download retry** if the normal transfer fails:

```powershell
# Windows PowerShell; then rerun your runtime-only command.
$env:HF_HUB_DISABLE_XET = '1'
$env:HF_HUB_DOWNLOAD_TIMEOUT = '120'
```

```bash
# Linux/macOS; then rerun your runtime-only command.
export HF_HUB_DISABLE_XET=1
export HF_HUB_DOWNLOAD_TIMEOUT=120
```

This changes the transfer path, not model access or license requirements.
Interrupted downloads can leave temporary cache files. On Windows, an open
file's displayed size may not update immediately; check transfer activity
before cancelling a download. A slow transfer is not proof of failure.

#### 5. Register MCP and the Skill

After runtime installation succeeds, keep the same `AGENT_AUDIO_HOME` and run:

```text
uv run --frozen python install/bootstrap.py --register-only
uv run --frozen python install/bootstrap.py --doctor
```

Read **every client outcome**, not just the final line. `installed`,
`registered` and `already-registered` are successful outcomes. `not-installed`
means that client was not detected; no registration for it was performed.
An error/conflict is preserved and reported, and a partial registration failure
returns `success: false`. Review conflicts before changing them. The installer
merges existing settings and creates backups rather than replacing whole configs.

| Client | Default user-level MCP configuration | Skill destination |
|---|---|---|
| Claude Code, including VS Code extension | `~/.claude.json` | `~/.claude/skills/audio-production/` |
| Codex | `~/.codex/config.toml` | `~/.agents/skills/audio-production/` |
| Cursor | `~/.cursor/mcp.json` | `~/.cursor/skills/audio-production/` |

Custom client configuration directories can change the MCP destination; see
[INSTALL_AGENT.md](INSTALL_AGENT.md). The registered server is named
`agent-audio`, launches this checkout's `.venv` Python with
`-I -m agent_audio.mcp_server`, and saves the chosen data root. Registration
does not prove that a running client has refreshed its tools or used the Skill.

For a combined fresh installation, bootstrap without `--runtime-only` installs
the runtime and then registers clients, for example
`uv run --frozen python install/bootstrap.py --backend cuda`. If the runtime
step fails, registration does not run; complete it or run `--register-only`
separately. Do not add `--backend` to `--register-only` or `--doctor`.

#### 6. Verify Claude Code in VS Code

Open a **new Claude conversation** in VS Code. Enter `/mcp` and look for
`agent-audio`; enable/reconnect it if the client requires that action. CLI
registration and the extension use the same MCP configuration, so do not add a
second duplicate entry. See [Claude's VS Code guide](https://code.claude.com/docs/en/vs-code).

Ask Claude:

```text
Call Agent Audio's audio_status and show the selected backend and readiness.
Then use generate_audio to create a 3-second dry metallic impact, isolated,
with no music or voice. Use a new file in the default test output folder and
report the actual WAV path. Do not add it to my project yet.
```

Check `selected_backend` matches your choice and `runtime_ready` is true.
For CUDA it should say `cuda`; do not infer acceleration from a detected GPU
while the selected backend is `tflite`. Doctor/status keep their inference
checks marked `not_checked` because they do not run or track generation tests.
The separate successful `generate_audio` call is your inference evidence.

Check the returned file exists and is three seconds long, then listen to it.
Valid WAV metadata and nonzero samples do not prove prompt adherence or sound
quality. This explicit smoke test also does not establish automatic Skill use
or final game/video integration.

If you need to isolate a client problem from a runtime problem, the local CLI
can generate a unique test file:

```text
uv run --frozen agent-audio generate "A dry metallic impact, isolated, no music, no voice" --seconds 3
```

The CLI uses the saved backend and the current terminal's `AGENT_AUDIO_HOME`.
Its output goes under that root's `output/`; it does not verify MCP connectivity
or VS Code tool invocation. Existing output files are never overwritten.

#### 7. Keep the installation usable

Keep the checkout and data directory in place. For updates, follow
[the preservation procedure](#updating-an-existing-installation): pulling Git
alone does not refresh installed Skill copies. To deliberately return to CPU,
install with `--runtime-only --backend tflite`; GPU failure does not trigger
an automatic fallback. Preserve failure logs locally and review them before
sharing. Keep model weights, credentials and generated test audio outside Git.

### MCP tools

| Tool | Purpose |
|---|---|
| `audio_status` | Inspect platform, hardware, backend, runtime/model paths and readiness. |
| `generate_audio` | Generate a WAV using the selected Stable Audio backend and return its path. |

Omit `output_path` for a unique default output, or choose a new `.wav` path.
Duration must be greater than zero and at most 380 seconds, subject to the
540-second inference timeout. `runtime_ready` checks files and model headers,
not successful inference. The separate `readiness` object reports checkout
verification and unperformed checksum, dependency-health and generation checks.
`capabilities.negative_prompt` is false under the current CFG 1.0 policy;
nonempty negative prompts are rejected.

```json
{
  "prompt": "Heavy metallic impact, sharp transient, isolated sound effect, no voice, no music",
  "seconds": 3
}
```

### Development checks

These checks do not require model weights; doctor also works offline.

```bash
uv run --frozen ruff check src install tests
uv run --frozen ruff format --check src install tests
uv run --frozen python -m compileall -q src install
uv run --frozen pytest -q
uv run --frozen python install/bootstrap.py --doctor
```

### Documentation and project layout

| Reader | Start here |
|---|---|
| Installing agent | [INSTALL_AGENT.md](INSTALL_AGENT.md) |
| User checking resource needs | [Resource measurements](docs/resource-requirements.md) |
| Contributor | [Repository instructions](AGENTS.md) and [architecture](ARCHITECTURE.md) |
| Maintainer validating real work | [Project direction](docs/project-direction.md) and [end-to-end validation](docs/end-to-end-validation.md) |
| Comparing models | [Small-SFX versus Medium benchmark](benchmarks/sfx_model_compare/README.md) |

Source is in `src/agent_audio/`, setup starts at `install/bootstrap.py`, the
portable Skill is in `skills/audio-production/`, and regression tests are in
`tests/`. Keep generated media and model weights outside Git.

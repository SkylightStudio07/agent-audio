# GPU backend setup

Agent Audio has opt-in `cuda` and `rocm` adapters for the official Stable Audio 3
Medium PyTorch runtime. These implementations have model-free regression
coverage and a [Windows CUDA generation test](windows-cuda-validation.md).
ROCm and Linux CUDA generation remain unverified. They are not
automatically selected based on a GPU name.

| Backend | Platform | PyTorch/torchaudio | Driver prerequisites |
|---|---|---|---|
| cuda | Windows/Linux x86-64 | 2.7.1+cu128 | NVIDIA driver compatible with CUDA 12.8 and a supported GPU |
| rocm | Linux x86-64 | 2.7.1+rocm6.3 | ROCm 6.3 supported GPU, OS and driver stack; device access permissions |
| tflite | Existing CPU path | Not applicable | CPU fallback for Windows AMD and unsupported GPUs |

Consult the [PyTorch wheel matrix](https://pytorch.org/get-started/previous-versions/)
and [AMD ROCm compatibility matrix](https://rocm.docs.amd.com/en/docs-6.3.3/compatibility/compatibility-matrix.html).
An AMD integrated GPU is not automatically a supported ROCm device. Windows
DirectML and Windows ROCm are not implemented. The installer does not install
drivers, grant device permissions or alter system GPU settings.

## Install and select

```text
uv sync --frozen
uv run --frozen python install/bootstrap.py --runtime-only --backend cuda
uv run --frozen python install/bootstrap.py --register-only
uv run --frozen python install/bootstrap.py --doctor
```

Use `rocm` instead of `cuda` for a supported Linux AMD system. Omit
`--runtime-only` to also register detected clients in the same run. Claude Code
uses the same generic `audio_status` and `generate_audio` tools as other clients;
no vendor parameter is needed in its calls.

GPU environments live in `AGENT_AUDIO_HOME/runtimes/cuda` and `runtimes/rocm`.
The pinned upstream checkout is preserved. The official package is installed
from that verified checkout; GPU wheels come from the corresponding PyTorch
index through direct wheel URLs, so vendor-index copies of ordinary packages
cannot shadow newer dependencies on PyPI. Conflicting installed
torch/torchaudio versions are refused rather than
replaced. A small GPU kernel runs during installation before model downloads.
Partial installations can be retried; they do not change backend selection.

After the files are ready, `backend.json` records the selected backend, with a
backup for changes to existing settings. MCP, CLI generation and doctor all
read that selection. Existing CPU and MLX environments/models remain available.
To return to CPU, run the installer with `--runtime-only --backend tflite`.
There is no automatic fallback on GPU failure or out-of-memory errors.

## Models, licenses and offline inference

GPU adapters download `stabilityai/stable-audio-3-medium` at revision
`27b5a21b791b1b033d193a9e1e3ce78493f102f9`, including its bundled T5Gemma
encoder/tokenizer. This is separate from the optimized TFLite/MLX repository.
License acceptance and authentication remain the user's responsibility. An
unauthenticated installation check returned HTTP 401. Download and generation
completed after the user authorized model access and authenticated in the
dedicated cache. No model weights are included in this repository.

Installation compares installed files to the revision-pinned cache content;
there are no independently pinned reference checksums for these PyTorch files.
Inference loads only the local checkpoint and encoder, with Hugging Face
offline mode enabled. It does not use upstream's unpinned `from_pretrained`
download path. The runner changes encoder paths in memory and preserves the
downloaded model configuration. It keeps Medium, eight steps and CFG 1.0;
negative prompts remain rejected under the existing generation policy.

The upstream pin contains PyTorch SDPA attention fallbacks when optional Flash
Attention is unavailable. Their existence does not prove parity, speed, VRAM
requirements or generation success on either vendor. No TensorRT engines or
additional attention kernel packages are installed by Agent Audio.

## Verification and evidence limits

Doctor and `audio_status` inspect files/headers and checkout provenance without
importing PyTorch or using the network. They explicitly mark current GPU probes,
dependencies, model checksums and generation as unchecked. Installation's kernel
probe is a separate check; it does not load the audio model.

In a fresh Claude Code session, inspect `audio_status`, then request a new
three-second WAV through `generate_audio`. Record the selected backend, PyTorch
version, device, driver, runtime/model pins, client, WAV metadata and timings.
Inference logs include device and wheel versions; successful logs are deleted
under the existing policy. A failure keeps its private local log. Assess actual
listening quality separately. Follow [end-to-end validation](end-to-end-validation.md)
for implicit Skill use and final project integration.

No GPU minimum VRAM figure is established. Long requests can exhaust memory or
hit the existing 540-second timeout. The CPU benchmark does not characterize
GPU performance. On 2026-10-06, installation, a native GPU kernel probe and a
three-second Medium WAV through standalone stdio MCP succeeded on Windows with
an RTX 5060 Ti with 16 GiB VRAM. The call took 31.22 seconds including startup
and model loading. Skill and MCP registration completed for Claude Code and
Codex; installed Skill files matched the source. The VS Code Claude extension
was present, but its actual tool invocation was not observed. These checks do
not establish implicit Skill use, project integration or listening quality.
See [the validation record](windows-cuda-validation.md). AMD inference remains
unverified because no ROCm Linux environment was available.

For a host that needs the ordinary HTTP transfer path, set
`HF_HUB_DISABLE_XET=1` for installation. The downloader then requests the full
byte range while retaining pinned revisions, authentication and cache checks.
Windows may delay reporting an open download file's size until the writer
closes it; a stale file size alone is not evidence of a stalled transfer.

The VS Code Claude Code extension shares MCP configuration with CLI
registration. Start a new conversation and use `/mcp` to inspect `agent-audio`.
See [Claude's VS Code documentation](https://code.claude.com/docs/en/vs-code).

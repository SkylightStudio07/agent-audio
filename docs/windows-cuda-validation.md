# Windows CUDA validation

Observed directly on 2026-10-06. This is one installation and explicit MCP
generation smoke test, not a GPU benchmark or an implicit Skill-use test.

| Item | Observation |
|---|---|
| Agent Audio source | Base commit `975d804594f515e81cdb8858587af5469cf78ebf` plus local CUDA/ROCm adapter changes |
| Platform | Windows x86-64 |
| GPU | NVIDIA GeForce RTX 5060 Ti, 16 GiB VRAM |
| Driver | 610.88 |
| Runtime | Python 3.12.10, PyTorch/torchaudio 2.7.1+cu128, CUDA 12.8 |
| Other inference dependencies | Transformers 5.18.0, huggingface-hub 1.33.0, safetensors 0.8.0, soundfile 0.14.0 |
| Upstream runtime pin | `779434a908193105335fd8d833418603625b2859` |
| Medium model pin | `27b5a21b791b1b033d193a9e1e3ce78493f102f9` |
| Transport/client | Standalone Python stdio MCP client |
| Selected backend | `cuda`, persisted and reported by `audio_status` |
| Request | A clean cinematic metallic impact, isolated one-shot, no music, no voice; 3 seconds |
| Call time | 31.22 seconds including inference startup and model loading |
| Cache state | First generation, recently downloaded models; OS file cache not controlled |
| WAV | 529,244 bytes, 44.1 kHz, stereo, PCM 16-bit, exactly 3.0 seconds |
| Signal | Nonzero PCM samples; normalized peak 0.65234 and RMS 0.09995 |
| WAV SHA-256 | `b26b88e332770004bb3abb0412c4c194dcdb0c192baee75adc000d935012fda2` |

## Installation and preservation

The installer used a dedicated data directory outside the repository, a
dedicated GPU venv and an official revision-pinned upstream checkout. It
installed CUDA wheels through explicit official URLs; using the PyTorch index
as a general extra index initially caused uv to shadow newer PyPI packages.
That resolver conflict was corrected without replacing another backend's venv.

The native GPU kernel probe succeeded. The first unauthenticated model request
failed with HTTP 401. The user then completed model access and Hugging Face
authentication in the dedicated cache. No license was accepted on their behalf.
The completed installation downloaded the Medium checkpoint, bundled T5Gemma
encoder/tokenizer and configuration files and compared published files against
the revision-pinned cache. These PyTorch files do not have independently pinned
reference checksums in Agent Audio.

Installation used `HF_HUB_DISABLE_XET=1` and the HTTP full-range request path.
Initial retries were influenced by delayed Windows size updates on open files;
process write counters subsequently confirmed active transfer. Interrupted
download files were preserved. This is an assisted host installation, not
evidence that every fresh environment completes without intervention.

## MCP, Skills and client evidence

The standalone client discovered `audio_status` and `generate_audio`, reported
the saved CUDA backend and ready files, and received a new WAV from a real
generation call. The runner checks the CUDA wheel/device, explicitly loads the
model on CUDA and uses local model/encoder paths with Hugging Face offline mode.
Optional Flash Attention was absent; upstream's attention fallback completed
this short request. No peak VRAM measurement was made.

User-level MCP and audio-production Skill registration completed for Codex and
Claude Code and remained idempotent on rerun. Both installed Skill trees matched
the repository source, including the prompt reference file. Native Claude CLI
2.1.285 and VS Code extension 2.1.289 were present. The VS Code extension shares
MCP configuration with CLI registration, but a fresh VS Code Claude conversation's
discovery and tool invocation were not observed in this test.

Model-free checks passed separately: frozen uv sync, Ruff lint and format,
compilation, 108 passing tests and 13 skipped tests, and local doctor. Neither
these checks nor WAV metadata establish listening quality, prompt adherence,
implicit Skill activation or game/video integration. Linux CUDA and AMD ROCm
remain unverified on real models.

The reproducible MCP client, private evidence JSON and WAV were retained in the
host's external validation folder. No generated audio, model weights, account
credentials or private configuration were added to this repository.

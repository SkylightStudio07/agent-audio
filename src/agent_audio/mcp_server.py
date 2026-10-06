from __future__ import annotations

from pathlib import Path

from mcp.server.fastmcp import FastMCP

from .detect import detect_environment
from .runtime import backend_ready, runtime_details, runtime_paths, selected_backend
from .runtime import generate_audio as _generate_audio

mcp = FastMCP("agent-audio")


@mcp.tool()
def audio_status() -> dict[str, object]:
    """Inspect Agent Audio platform, hardware, selected backend and runtime readiness."""
    info = detect_environment()
    backend = selected_backend(info)
    return {
        "environment": info.to_dict(),
        "selected_backend": backend,
        "runtime_ready": backend_ready(backend),
        "runtime_root": str(runtime_paths().upstream),
        **runtime_details(backend),
        "notes": {
            "gpu": "CUDA and Linux ROCm are opt-in backends. File readiness does not prove GPU inference; installation probes a GPU kernel and generation verifies separately. Windows AMD uses CPU.",
            "intel": "Intel graphics are supported through the portable CPU path in v0.1; XPU acceleration is not claimed until validated.",
        },
    }


@mcp.tool()
def generate_audio(
    prompt: str,
    seconds: float = 10.0,
    output_path: str | None = None,
    negative_prompt: str | None = None,
) -> str:
    """Generate local audio from text using Stable Audio 3 Medium and return the WAV path.

    Use for music, sound effects, ambience, UI sounds, transitions and general media audio.
    The caller should choose a meaningful output path when integrating into a project.
    The current backends reject nonempty negative_prompt; use prompt to describe
    the desired sound. audio_status reports capabilities and readiness check scope.
    """
    path: Path = _generate_audio(
        prompt=prompt,
        seconds=seconds,
        output_path=output_path,
        negative_prompt=negative_prompt,
    )
    return str(path)


def main() -> None:
    mcp.run()


if __name__ == "__main__":
    main()

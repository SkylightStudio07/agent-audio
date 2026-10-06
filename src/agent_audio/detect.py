from __future__ import annotations

import os
import platform
import shutil
import subprocess
from dataclasses import asdict, dataclass


@dataclass(frozen=True)
class EnvironmentInfo:
    os: str
    architecture: str
    machine: str
    apple_silicon: bool
    nvidia_detected: bool
    intel_graphics_detected: bool
    codex_installed: bool
    claude_installed: bool
    cursor_installed: bool
    amd_graphics_detected: bool = False

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


def _command_output(command: list[str]) -> str:
    try:
        completed = subprocess.run(
            command,
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return ""
    return f"{completed.stdout}\n{completed.stderr}".strip()


def _detect_nvidia() -> bool:
    if shutil.which("nvidia-smi"):
        return True
    if platform.system() == "Linux":
        return os.path.exists("/proc/driver/nvidia/version")
    return False


def _graphics_output() -> str:
    system = platform.system()
    if system == "Windows":
        output = _command_output(
            [
                "powershell",
                "-NoProfile",
                "-Command",
                "Get-CimInstance Win32_VideoController | Select-Object -ExpandProperty Name",
            ]
        )
    elif system == "Darwin":
        output = _command_output(["system_profiler", "SPDisplaysDataType"])
    else:
        output = _command_output(
            ["sh", "-lc", "lspci 2>/dev/null | grep -Ei 'vga|3d|display'"]
        )
    return output.lower()


def detect_environment() -> EnvironmentInfo:
    system = platform.system()
    machine = platform.machine()
    arch = platform.architecture()[0]
    apple_silicon = system == "Darwin" and machine.lower() in {"arm64", "aarch64"}
    graphics = _graphics_output()

    return EnvironmentInfo(
        os=system,
        architecture=arch,
        machine=machine,
        apple_silicon=apple_silicon,
        nvidia_detected=_detect_nvidia(),
        intel_graphics_detected="intel" in graphics or "arc" in graphics,
        codex_installed=shutil.which("codex") is not None,
        claude_installed=shutil.which("claude") is not None,
        cursor_installed=(
            shutil.which("cursor") is not None or shutil.which("agent") is not None
        ),
        amd_graphics_detected="amd" in graphics or "radeon" in graphics,
    )


def recommended_backend(info: EnvironmentInfo) -> str:
    # v0.1 deliberately chooses only upstream paths that are straightforward
    # to install across the supported OS. Additional accelerated adapters can
    # override this once they are validated on each platform.
    if info.apple_silicon:
        return "mlx"
    return "tflite"

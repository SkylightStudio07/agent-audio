"""Small Stable Audio adapters; no hardware-specific options cross the MCP boundary."""

from __future__ import annotations

import json
import platform
import zipfile
from dataclasses import dataclass
from pathlib import Path

from . import download_models
from .profiles import PROFILES


@dataclass(frozen=True)
class StableAudioBackend:
    name: str
    requires_tokenizer: bool

    @property
    def accelerated(self) -> bool:
        return False

    def validate_platform(self) -> None:
        pass

    @property
    def script_name(self) -> str:
        return f"sa3_{self.name}.py"

    @property
    def model_files(self) -> tuple[str, ...]:
        if self.name == "tflite":
            return tuple(download_models.TFLITE_SHA256)
        return download_models.MLX_FILES

    def model_header_valid(self, path: Path) -> bool:
        if self.name == "tflite":
            with path.open("rb") as model:
                return model.read(8)[4:8] == b"TFL3"
        return zipfile.is_zipfile(path)

    def validate_negative_prompt(self, negative_prompt: str | None) -> None:
        # Both pinned scripts ignore this input with their default CFG of 1.0.
        # Changing guidance requires separate quality/resource validation.
        if negative_prompt:
            raise ValueError(
                f"negative_prompt is unsupported by the current {self.name} backend "
                "generation policy; omit it and describe the desired sound in prompt."
            )

    def generation_arguments(
        self, prompt: str, seconds: float, output: Path
    ) -> list[str]:
        profile = PROFILES["medium"]
        return [
            f"--prompt={prompt}",
            "--dit",
            profile.dit,
            "--decoder",
            profile.decoder,
            "--cfg",
            "1.0",
            "--seconds",
            str(seconds),
            "--out",
            str(output),
        ]


@dataclass(frozen=True)
class TorchBackend(StableAudioBackend):
    """Official PyTorch inference, with separate CUDA and HIP environments."""

    @property
    def accelerated(self) -> bool:
        return True

    @property
    def model_files(self) -> tuple[str, ...]:
        return download_models.TORCH_FILES

    def validate_platform(self) -> None:
        supported = {"Windows", "Linux"} if self.name == "cuda" else {"Linux"}
        if platform.system() not in supported or platform.machine().lower() not in {
            "amd64",
            "x86_64",
        }:
            raise ValueError(
                f"{self.name} requires {'Windows or Linux' if self.name == 'cuda' else 'Linux'} x86-64. "
                "Use tflite for unsupported hardware/OS combinations."
            )

    @property
    def wheel_index(self) -> str:
        variant = "cu128" if self.name == "cuda" else "rocm6.3"
        return f"https://download.pytorch.org/whl/{variant}"

    def wheel_requirements(self) -> list[str]:
        tag = "win_amd64" if platform.system() == "Windows" else "manylinux_2_28_x86_64"
        variant = "cu128" if self.name == "cuda" else "rocm6.3"
        return [
            f"{package} @ {self.wheel_index}/{package}-2.7.1%2B{variant}-cp312-cp312-{tag}.whl"
            for package in ("torch", "torchaudio")
        ]

    def model_header_valid(self, path: Path) -> bool:
        if path.suffix == ".json":
            try:
                return isinstance(json.loads(path.read_text(encoding="utf-8")), dict)
            except (ValueError, UnicodeError):
                return False
        if path.suffix == ".safetensors":
            with path.open("rb") as stream:
                size = int.from_bytes(stream.read(8), "little")
                if not 0 < size <= min(path.stat().st_size - 8, 100_000_000):
                    return False
                try:
                    return isinstance(json.loads(stream.read(size)), dict)
                except (ValueError, UnicodeError):
                    return False
        return path.stat().st_size > 0

    def generation_arguments(
        self, prompt: str, seconds: float, output: Path
    ) -> list[str]:
        return [f"--prompt={prompt}", "--seconds", str(seconds), "--out", str(output)]


BACKENDS = {
    "tflite": StableAudioBackend("tflite", requires_tokenizer=True),
    "mlx": StableAudioBackend("mlx", requires_tokenizer=False),
    "cuda": TorchBackend("cuda", requires_tokenizer=False),
    "rocm": TorchBackend("rocm", requires_tokenizer=False),
}


def get_backend(name: str) -> StableAudioBackend:
    try:
        return BACKENDS[name]
    except KeyError:
        raise ValueError(f"Unsupported backend: {name}") from None

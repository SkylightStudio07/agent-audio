"""Pinned, data-only model downloads. Also runs in the dedicated runtime venv."""

from __future__ import annotations

import argparse
import hashlib
import os
import shutil
import tempfile
from pathlib import Path

MODEL_REPO = "stabilityai/stable-audio-3-optimized"
MODEL_REVISION = "da6edc54ddba10bfd79a077102ded687f80e882b"
TORCH_MODEL_REPO = "stabilityai/stable-audio-3-medium"
TORCH_MODEL_REVISION = "27b5a21b791b1b033d193a9e1e3ce78493f102f9"
TORCH_FILES = (
    "model_config.json",
    "model.safetensors",
    "t5gemma-b-b-ul2/config.json",
    "t5gemma-b-b-ul2/model.safetensors",
    "t5gemma-b-b-ul2/special_tokens_map.json",
    "t5gemma-b-b-ul2/tokenizer.json",
    "t5gemma-b-b-ul2/tokenizer.model",
    "t5gemma-b-b-ul2/tokenizer_config.json",
)
# Values independently checked against a fresh download during the Windows test.
TFLITE_SHA256 = {
    "sa3-m/dit_fp32.tflite": "b811dc7d0135ca48afbc7a7bb7d19bdaaad13cbcb592418b8aa169e0c149daba",
    "same-l/dec_w8a8.tflite": "53dbca41ec9620257834bda4f3008a2cd5072afba564b84906f8ffdfca2647e7",
    "same-l/enc_w8a8.tflite": "9c76149a2fe6bd461fadf2a45b675fcd4bc64a26bd2f1d24810098a169cc41ec",
    "t5gemma/encoder_fp16.tflite": "8530d0b3e6b9b9dcf1239145c2a853fb749708eaddbb472ff8f0802b50059372",
}
TFLITE_BENCHMARK_SHA256 = {
    "sa3-sm-sfx/dit_fp32.tflite": "6060ecfeca34c4ab35bc1912a37e680e8cd7aab6c4bd9de1bc2655414891b8d8",
    "same-s/dec_w8a8.tflite": "90cad5ef81e6b18eb205012aee03bc53ed59e1c17033b79a84a4612674b1e03a",
}
MLX_FILES = (
    "dit_medium_f16.npz",
    "same_l_decoder_f32.npz",
    "same_l_encoder_f32.npz",
    "t5gemma_f16.npz",
)


def digest(path: Path) -> str:
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def download(
    backend: str, root: Path, cache: Path, *, benchmark_small: bool = False
) -> None:
    from huggingface_hub import hf_hub_download

    if backend not in {"tflite", "mlx", "cuda", "rocm"}:
        raise ValueError(f"Unsupported backend: {backend}")
    accelerated = backend in {"cuda", "rocm"}
    manifest = (
        dict.fromkeys(TORCH_FILES)
        if accelerated
        else TFLITE_SHA256
        if backend == "tflite"
        else dict.fromkeys(MLX_FILES)
    )
    repo = TORCH_MODEL_REPO if accelerated else MODEL_REPO
    revision = TORCH_MODEL_REVISION if accelerated else MODEL_REVISION
    if benchmark_small:
        if backend != "tflite":
            raise ValueError("Small-SFX benchmark download currently requires TFLite")
        manifest = TFLITE_BENCHMARK_SHA256
    prefix = "" if accelerated else "tflite/" if backend == "tflite" else "MLX/"
    for name, expected in manifest.items():
        target = root / "models" / backend / name
        # Always resolve via the pinned revision, even when a local model exists.
        # HF snapshots can be relative symlinks. Link the verified blob, not the
        # symlink itself: relocating that symlink can break its relative target.
        cached = Path(
            hf_hub_download(
                repo,
                f"{prefix}{name}",
                revision=revision,
                cache_dir=cache,
                # Some proxies/CDNs buffer a whole large response before sending
                # data. A full-range request permits streaming without changing
                # the pinned file, authentication or cache verification policy.
                **(
                    {"headers": {"Range": "bytes=0-"}}
                    if os.environ.get("HF_HUB_DISABLE_XET", "").lower()
                    in {"1", "true", "yes", "on"}
                    else {}
                ),
            )
        ).resolve(strict=True)
        actual = digest(cached)
        if expected and actual != expected:
            raise RuntimeError(f"Model checksum mismatch: {name}; refusing to install.")
        if os.path.lexists(target):
            # An external link is not independent, even if its contents happen to match.
            if target.is_symlink() and not target.resolve().is_relative_to(
                cache.resolve()
            ):
                raise RuntimeError(f"Model links outside Agent Audio's cache: {target}")
            if not target.is_file() or digest(target) != actual:
                raise RuntimeError(
                    f"Existing model conflicts with pinned weights: {target}; preserved."
                )
            continue
        target.parent.mkdir(parents=True, exist_ok=True)
        try:
            os.link(cached, target)
        except FileExistsError:
            raise RuntimeError(
                f"Model appeared during installation: {target}"
            ) from None
        except OSError:
            # Stage on the target volume: an interrupted copy must never become
            # an existing, conflicting model. Publication remains exclusive.
            fd, temporary = tempfile.mkstemp(
                prefix=".agent-audio-model-", dir=target.parent
            )
            staged = Path(temporary)
            try:
                with os.fdopen(fd, "wb") as destination, cached.open("rb") as source:
                    shutil.copyfileobj(source, destination)
                    destination.flush()
                    os.fsync(destination.fileno())
                if digest(staged) != actual:
                    raise RuntimeError(f"Copied model checksum mismatch: {name}")
                try:
                    os.link(staged, target)
                except FileExistsError:
                    raise RuntimeError(
                        f"Model appeared during installation: {target}"
                    ) from None
            finally:
                staged.unlink(missing_ok=True)
        print(f"Verified {target} ({target.stat().st_size} bytes)", flush=True)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--backend", choices=("tflite", "mlx", "cuda", "rocm"), required=True
    )
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--cache", type=Path, required=True)
    parser.add_argument("--benchmark-small", action="store_true")
    args = parser.parse_args()
    download(args.backend, args.root, args.cache, benchmark_small=args.benchmark_small)


if __name__ == "__main__":
    main()

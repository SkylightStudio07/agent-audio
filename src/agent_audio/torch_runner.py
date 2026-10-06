"""Dedicated-runtime entry point; never imported by status or the MCP host."""

from __future__ import annotations

import argparse
import json
from pathlib import Path


def verify_device(torch, backend: str) -> None:
    hip = bool(getattr(torch.version, "hip", None))
    if hip != (backend == "rocm") or not torch.cuda.is_available():
        raise RuntimeError(
            f"{backend} GPU is unavailable or the wrong PyTorch wheel is installed; no CPU fallback was attempted."
        )
    # Execute a native kernel, rather than treating driver detection as readiness.
    probe = torch.ones(4, device="cuda")
    if probe.sum().item() != 4:
        raise RuntimeError("GPU kernel probe failed")
    torch.cuda.synchronize()


def local_conditioner(config: dict, models: Path) -> None:
    count = 0

    def visit(value):
        nonlocal count
        if isinstance(value, dict):
            if value.get("type") == "t5gemma":
                options = value["config"]
                options["model_path"] = str(models / "t5gemma-b-b-ul2")
                options.pop("repo_id", None)
                options.pop("subfolder", None)
                count += 1
            for child in value.values():
                visit(child)
        elif isinstance(value, list):
            for child in value:
                visit(child)

    visit(config)
    if count != 1:
        raise RuntimeError(
            "Pinned model config must contain exactly one T5Gemma conditioner"
        )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--backend", choices=("cuda", "rocm"), required=True)
    parser.add_argument("--models", type=Path, required=True)
    parser.add_argument("--probe", action="store_true")
    parser.add_argument("--prompt")
    parser.add_argument("--seconds", type=float)
    parser.add_argument("--out", type=Path)
    args = parser.parse_args()
    import torch

    verify_device(torch, args.backend)
    print(
        json.dumps(
            {
                "backend": args.backend,
                "torch": torch.__version__,
                "cuda": torch.version.cuda,
                "hip": torch.version.hip,
                "device": torch.cuda.get_device_name(0),
            }
        ),
        flush=True,
    )
    if args.probe:
        return
    if args.prompt is None or args.seconds is None or args.out is None:
        parser.error("generation requires --prompt, --seconds and --out")
    import soundfile
    from stable_audio_3 import StableAudioModel
    from stable_audio_3.loading_utils import load_diffusion_cond

    config = json.loads((args.models / "model_config.json").read_text(encoding="utf-8"))
    local_conditioner(config, args.models)
    model = load_diffusion_cond(
        config, str(args.models / "model.safetensors"), device="cuda", model_half=True
    )
    model.use_lora = False
    model.lora_names = []
    pipeline = StableAudioModel(model, config, "cuda", True)
    audio = pipeline.generate(
        prompt=args.prompt,
        duration=args.seconds,
        steps=8,
        cfg_scale=1.0,
        batch_size=1,
        sample_size=config["sample_size"],
    )
    samples = audio[0].float().cpu().transpose(0, 1).numpy()
    soundfile.write(str(args.out), samples, model.sample_rate, subtype="PCM_16")


if __name__ == "__main__":
    main()

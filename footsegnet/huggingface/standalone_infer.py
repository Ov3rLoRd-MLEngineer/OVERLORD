#!/usr/bin/env python
# ██████╗ ██╗   ██╗██████╗ ██████╗ ██╗      ██████╗ ██████╗ ██████╗
# ██╔═══██╗██║   ██║╚════██╗██╔══██╗██║     ██╔═══██╗██╔══██╗██╔══██╗
# ██║   ██║██║   ██║ █████╔╝██████╔╝██║     ██║   ██║██████╔╝██║  ██║
# ██║   ██║╚██╗ ██╔╝ ╚═══██╗██╔══██╗██║     ██║   ██║██╔══██╗██║  ██║
# ╚██████╔╝ ╚████╔╝ ██████╔╝██║  ██║███████╗╚██████╔╝██║  ██║██████╔╝
# ╚═════╝   ╚═══╝  ╚═════╝ ╚═╝  ╚═╝╚══════╝ ╚═════╝ ╚═╝  ╚═╝╚═════╝
# Ov3rLoRd -- pipeline de production anime autonome (ComfyUI)
# https://github.com/Ov3rLoRd-MLEngineer
#
"""
standalone_infer.py — FootSegNet minimal inference script

Self-contained script to run FootSegNet (a SAM ViT-B fine-tuned for
foot/shoe segmentation on anime-style illustrations) without any
dependency on the rest of the Ov3rLoRd pipeline. Only needs:

    pip install torch torchvision pillow numpy
    pip install git+https://github.com/facebookresearch/segment-anything.git
    pip install safetensors   # only if loading a .safetensors checkpoint

Download the checkpoint from the HuggingFace model repo (either the
original .pth or the .safetensors conversion both work with this script).

Usage:
    python standalone_infer.py --image photo.png --checkpoint footsegnet_vit_b_best.safetensors --output mask.png
    python standalone_infer.py --image photo.png --checkpoint footsegnet_vit_b_best.pth --box 259,1049,200,409 --output mask.png

Output convention (this script): standard ML convention —
    WHITE (255) = foot/shoe (detected object)
    BLACK (0)   = background
This is the opposite of the convention used internally in the Ov3rLoRd
pipeline (where black=regenerate/white=preserve for inpainting masks) —
if you're integrating with that pipeline specifically, see infer.py in
the main repo instead. For general use (dataset building, cutout, your
own inpainting pipeline, etc.) this script's plain "white=object" output
is what you want.
"""

import argparse
from pathlib import Path

import numpy as np
import torch
from PIL import Image, ImageFilter


def load_state_dict(checkpoint_path: Path) -> dict:
    """Loads a state_dict from either .pth (torch) or .safetensors."""
    if checkpoint_path.suffix == ".safetensors":
        from safetensors.torch import load_file
        return load_file(str(checkpoint_path))
    return torch.load(str(checkpoint_path), map_location="cpu", weights_only=True)


def load_model(checkpoint_path: Path, device: str):
    """Builds a SAM ViT-B skeleton and loads the fine-tuned FootSegNet weights."""
    from segment_anything import sam_model_registry, SamPredictor

    sam = sam_model_registry["vit_b"](checkpoint=None)
    state_dict = load_state_dict(checkpoint_path)
    sam.load_state_dict(state_dict)
    sam.to(device)
    sam.eval()
    return SamPredictor(sam)


def prepare_rgb(image_path: Path) -> Image.Image:
    """Opens the image as RGB, compositing any alpha channel onto a white
    background first. Passing raw RGBA straight into SAM silently produces
    a degenerate (near-instant, empty) result — always flatten alpha first."""
    img = Image.open(str(image_path))
    if img.mode in ("RGBA", "LA") or (img.mode == "P" and "transparency" in img.info):
        img = img.convert("RGBA")
        bg = Image.new("RGB", img.size, (255, 255, 255))
        bg.paste(img, mask=img.split()[3])
        return bg
    return img.convert("RGB")


def segment(
    predictor,
    image_path: Path,
    box: tuple | None = None,
    threshold: float = 0.5,
    feather_px: int = 8,
    refine: bool = True,
) -> tuple[Image.Image, float]:
    """Runs segmentation and returns (mask_image, sam_confidence_score).

    box: (x, y, w, h) in absolute pixels restricting the search region
         (e.g. a foot bounding box from a pose estimator). None = whole image.
    refine: does a second SAM decoder pass, feeding back the first pass's
            logits as mask_input with the same box — lets SAM refine its own
            initial guess rather than a single forward pass. Recommended on.
    """
    img = prepare_rgb(image_path)
    arr = np.array(img)
    ih, iw = arr.shape[:2]

    if box is not None:
        x, y, w, h = box
        box_arr = np.array([max(0, x), max(0, y), min(iw, x + w), min(ih, y + h)], dtype=np.float32)
    else:
        box_arr = np.array([0, 0, iw, ih], dtype=np.float32)

    predictor.set_image(arr)
    with torch.no_grad():
        masks, scores, logits = predictor.predict(box=box_arr, multimask_output=False, return_logits=True)
        if refine:
            masks, scores, logits = predictor.predict(
                box=box_arr, mask_input=logits, multimask_output=False, return_logits=True
            )

    # `masks[0]` (not `logits[0]`) — predictor.predict(return_logits=True)
    # already upscales to the source image resolution; `logits` is the raw
    # low-res (256x256) mask_decoder output and must not be thresholded directly.
    prob = 1.0 / (1.0 + np.exp(-masks[0].astype(np.float64)))
    obj = (prob >= threshold).astype(np.uint8)

    out_arr = (obj * 255).astype(np.uint8)
    mask_img = Image.fromarray(out_arr, mode="L")
    if feather_px > 0:
        mask_img = mask_img.filter(ImageFilter.GaussianBlur(feather_px))

    return mask_img, float(scores[0])


def main():
    parser = argparse.ArgumentParser(description="FootSegNet — standalone foot/shoe segmentation")
    parser.add_argument("--image", required=True, help="Input image")
    parser.add_argument("--checkpoint", required=True, help="Path to footsegnet_vit_b_best.pth or .safetensors")
    parser.add_argument("--box", default=None, help="Bounding box 'x,y,w,h' in pixels (default: whole image)")
    parser.add_argument("--output", default=None, help="Output mask path (default: <image>_footmask.png)")
    parser.add_argument("--threshold", type=float, default=0.5)
    parser.add_argument("--feather", type=int, default=8, help="Gaussian blur radius on mask edges (0 = hard edge)")
    parser.add_argument("--no-refine", action="store_true", help="Disable the second SAM refinement pass")
    parser.add_argument("--device", default=None, help="cuda / cpu (default: auto-detect)")
    args = parser.parse_args()

    image_path = Path(args.image)
    if not image_path.exists():
        raise SystemExit(f"Image not found: {image_path}")

    box = None
    if args.box:
        box = tuple(int(v) for v in args.box.split(","))
        if len(box) != 4:
            raise SystemExit("--box must be 'x,y,w,h', e.g. '259,1049,200,409'")

    device = args.device or ("cuda" if torch.cuda.is_available() else "cpu")
    print(f"[footsegnet] Loading {args.checkpoint} on {device}...")
    predictor = load_model(Path(args.checkpoint), device)

    mask_img, score = segment(
        predictor, image_path, box=box, threshold=args.threshold,
        feather_px=args.feather, refine=not args.no_refine,
    )

    output_path = args.output or str(image_path.parent / f"{image_path.stem}_footmask.png")
    mask_img.save(output_path)
    pct = float(np.array(mask_img).astype(bool).mean()) * 100
    print(f"[footsegnet] SAM confidence={score:.3f}  foot/shoe pixels={pct:.1f}%")
    print(f"[footsegnet] -> {output_path}")


if __name__ == "__main__":
    main()

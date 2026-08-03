# reference_aligner_v2.py — Ov3rLoRd Pipeline
# Extraction directe : frames Kling brutes → skeletons + lineart
# Aucun crop, aucun resize — sortie à la résolution native de la frame source
# py -3.12

import argparse
import os
import shutil
import sys
from pathlib import Path
from PIL import Image

_REPO_ROOT = Path(__file__).resolve().parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))
import config

# ── CONFIG ─────────────────────────────────────────────────────────────────────
FRAMES_DIR      = str(config.DEMO_DIR / "frames")
FRAMES_SRC_DIR  = os.path.join(FRAMES_DIR, "frames")
SKEL_OUTPUT_DIR = os.path.join(FRAMES_DIR, "skeletons_1024x1024")
LA_OUTPUT_DIR   = os.path.join(FRAMES_DIR, "lineart_1024x1024")


# ── EXTRACTION SKELETON ────────────────────────────────────────────────────────
def extract_skeleton(img: Image.Image, out_path: str) -> bool:
    try:
        from controlnet_aux import OpenposeDetector
        detector = OpenposeDetector.from_pretrained("lllyasviel/ControlNet")
        result = detector(img, output_type="pil",
                          include_body=True,
                          include_hand=False,
                          include_face=False)
        result.save(out_path)
        return True
    except Exception as e:
        print(f"[aligner] ERREUR skeleton: {e}")
        return False


# ── EXTRACTION LINEART ─────────────────────────────────────────────────────────
def extract_lineart(img: Image.Image, out_path: str) -> bool:
    try:
        from controlnet_aux import LineartStandardDetector
        detector = LineartStandardDetector()
        result = detector(img, output_type="pil")
        result.save(out_path)
        return True
    except Exception as e:
        print(f"[aligner] ERREUR lineart: {e}")
        return False


# ── PIPELINE FRAME UNIQUE ──────────────────────────────────────────────────────
def process_frame(frame_path: str, frame_num: int,
                  skel_out_dir: str, la_out_dir: str,
                  overwrite: bool = False):
    stem     = f"{frame_num:04d}"
    out_skel = Path(skel_out_dir) / f"skeleton_{stem}.png"
    out_la   = Path(la_out_dir)   / f"lineart_{stem}.png"

    if not overwrite and out_skel.exists() and out_la.exists():
        return None

    with Image.open(frame_path) as img:
        img_rgb = img.convert("RGB")

    if not extract_skeleton(img_rgb, str(out_skel)):
        return False
    if not extract_lineart(img_rgb, str(out_la)):
        return False
    return True


# ── BATCH ──────────────────────────────────────────────────────────────────────
def batch_process(frames_src_dir, skel_out_dir, la_out_dir,
                  start=0, end=None, overwrite=False):

    frames = sorted(Path(frames_src_dir).glob("*.png"))
    if not frames:
        frames = sorted(Path(frames_src_dir).glob("*.jpg"))
    if not frames:
        print(f"[aligner] Aucune frame dans {frames_src_dir}")
        return 0

    for d in [skel_out_dir, la_out_dir]:
        Path(d).mkdir(parents=True, exist_ok=True)

    if end is None:
        end = len(frames)
    frames = frames[start:end]

    ok = skip = err = 0
    for i, frame_path in enumerate(frames):
        frame_num = start + i
        result = process_frame(
            str(frame_path), frame_num,
            skel_out_dir, la_out_dir,
            overwrite=overwrite,
        )
        if result is None:
            skip += 1
        elif result:
            ok += 1
            if ok % 10 == 0:
                print(f"[aligner] {ok} frames traitées...")
        else:
            err += 1

    print(f"[aligner] Batch terminé : {ok} OK / {skip} skips / {err} erreurs")
    return ok


# ── CLI ────────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Ov3rLoRd — Reference Aligner (extraction directe sans crop)"
    )
    subparsers = parser.add_subparsers(dest="command")

    p_batch = subparsers.add_parser("batch")
    p_batch.add_argument("--frames-src",  default=FRAMES_SRC_DIR)
    p_batch.add_argument("--skel-output", default=SKEL_OUTPUT_DIR)
    p_batch.add_argument("--la-output",   default=LA_OUTPUT_DIR)
    p_batch.add_argument("--start",       type=int, default=0)
    p_batch.add_argument("--end",         type=int, default=None)
    p_batch.add_argument("--overwrite",   action="store_true")

    p_single = subparsers.add_parser("single")
    p_single.add_argument("--frame",       required=True)
    p_single.add_argument("--frame-num",   type=int, required=True)
    p_single.add_argument("--skel-output", default=SKEL_OUTPUT_DIR)
    p_single.add_argument("--la-output",   default=LA_OUTPUT_DIR)
    p_single.add_argument("--overwrite",   action="store_true")

    args = parser.parse_args()

    if args.command == "batch":
        batch_process(
            args.frames_src,
            args.skel_output, args.la_output,
            start=args.start, end=args.end,
            overwrite=args.overwrite,
        )
    elif args.command == "single":
        for d in [args.skel_output, args.la_output]:
            Path(d).mkdir(parents=True, exist_ok=True)
        result = process_frame(
            args.frame, args.frame_num,
            args.skel_output, args.la_output,
            overwrite=args.overwrite,
        )
        status = "OK" if result is True else ("skip" if result is None else "ERREUR")
        print(f"[aligner] {status}")
    else:
        parser.print_help()

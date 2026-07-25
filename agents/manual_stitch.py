# manual_stitch.py — Ov3rLoRd Pipeline
# Recolle manuellement un crop inpainté dans l'image originale.
# Usage : py -3.12 manual_stitch.py
#
# À adapter selon les chemins réels avant chaque utilisation.

import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))
import config

from PIL import Image, ImageFilter

import io
if hasattr(sys.stdout, 'buffer') and getattr(sys.stdout, 'encoding','').lower() != 'utf-8':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

# ── À ADAPTER ────────────────────────────────────────────────────────────────
SOURCE_IMAGE    = "2026-06-30-212153_fabricatedXL_v70_391065954874066.png"
INPAINTED_CROP  = str(config.COMFYUI_OUTPUT / "asuka_run" / "inpaint__00007_.png")
CROP_BOX        = (199, 943, 519, 1519)   # (x1, y1, x2, y2) dans l'image originale
MASK_PATH       = str(config.COMFYUI_INPUT / "mask_frame_0000_shoe_mismatch.png")
OUTPUT_PATH     = "stitched_frame_0000.png"
# ─────────────────────────────────────────────────────────────────────────────

original      = Image.open(SOURCE_IMAGE).convert("RGB")
inpainted     = Image.open(INPAINTED_CROP).convert("RGB")
mask          = Image.open(MASK_PATH).convert("L")

cw = CROP_BOX[2] - CROP_BOX[0]
ch = CROP_BOX[3] - CROP_BOX[1]

if inpainted.size != (cw, ch):
    inpainted = inpainted.resize((cw, ch), Image.LANCZOS)
    print(f"Crop redimensionné : {inpainted.size}")

if mask.size != (cw, ch):
    mask = mask.resize((cw, ch), Image.LANCZOS)

result = original.copy()
result.paste(inpainted, (CROP_BOX[0], CROP_BOX[1]), mask)
result.save(OUTPUT_PATH)
print(f"Stitch OK → {OUTPUT_PATH}")

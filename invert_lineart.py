# invert_lineart.py — Ov3rLoRd Pipeline
# Inverse noir/blanc sur les lineart (fond noir → fond blanc)
# py -3.12

import argparse
from pathlib import Path
from PIL import Image, ImageOps

LINEART_DIR = r"D:\OVERLORD\DEMO\frames\lineart_1024x1024"

def invert_image(src: str, dst: str):
    with Image.open(src) as img:
        inverted = ImageOps.invert(img.convert("RGB"))
    inverted.save(dst)

def batch_invert(input_dir: str, output_dir: str, overwrite: bool = False):
    files = sorted(Path(input_dir).glob("*.png"))
    if not files:
        print(f"[invert] Aucun fichier dans {input_dir}")
        return 0
    Path(output_dir).mkdir(parents=True, exist_ok=True)
    ok = skip = 0
    for f in files:
        out = Path(output_dir) / f.name
        if not overwrite and out.exists():
            skip += 1
            continue
        invert_image(str(f), str(out))
        ok += 1
    print(f"[invert] Terminé : {ok} OK / {skip} skips")
    return ok

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Ov3rLoRd — Invert Lineart")
    parser.add_argument("--input",     default=LINEART_DIR)
    parser.add_argument("--output",    default=LINEART_DIR)
    parser.add_argument("--overwrite", action="store_true")
    args = parser.parse_args()
    batch_invert(args.input, args.output, args.overwrite)

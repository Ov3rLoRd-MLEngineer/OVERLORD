# build_coco.py — HandSegNet (Ov3rLoRd Pipeline)
# Masques PNG multi-classes → COCO JSON (RLE non compressé) + split train/val.
# Même architecture que footsegnet\build_coco.py, étendue à N catégories :
# un masque par catégorie, nommé dataset\masks_raw\<stem>__<catégorie>.png.
#
# Usage :
#   py -3.12 build_coco.py
#   py -3.12 build_coco.py --val-ratio 0.15 --split-seed 42

import argparse
import json
import random
import shutil
from datetime import date
from pathlib import Path

import numpy as np
from PIL import Image

# ── CONFIG ────────────────────────────────────────────────────────────────────
PROJECT_ROOT = Path(r"D:\OVERLORD\handsegnet")
RAW_IMAGES = PROJECT_ROOT / "dataset" / "raw"
RAW_MASKS  = PROJECT_ROOT / "dataset" / "masks_raw"
IMAGES_DIR = PROJECT_ROOT / "dataset" / "images"
MASKS_DIR  = PROJECT_ROOT / "dataset" / "masks"
ANNOT_DIR  = PROJECT_ROOT / "dataset" / "annotations"

CATEGORIES = [
    {"id": 1, "name": "hand",    "supercategory": "hand"},
    {"id": 2, "name": "fingers", "supercategory": "hand"},
    {"id": 3, "name": "wrist",   "supercategory": "hand"},
]
CAT_ID = {c["name"]: c["id"] for c in CATEGORIES}


# ── RLE COCO (non compressé, ordre colonne / Fortran) ────────────────────────

def encode_rle(mask_bin: np.ndarray) -> dict:
    flat = mask_bin.flatten(order="F").astype(np.uint8)
    counts = []
    current = 0
    run = 0
    for v in flat:
        if v == current:
            run += 1
        else:
            counts.append(run)
            current = v
            run = 1
    counts.append(run)
    h, w = mask_bin.shape
    return {"counts": counts, "size": [h, w]}


def decode_rle(rle: dict) -> np.ndarray:
    h, w = rle["size"]
    flat = np.zeros(h * w, dtype=np.uint8)
    idx = 0
    val = 0
    for c in rle["counts"]:
        if val:
            flat[idx:idx + c] = 1
        idx += c
        val = 1 - val
    return flat.reshape((h, w), order="F")


def mask_to_annotation(mask_bin: np.ndarray, ann_id: int, image_id: int,
                       category_id: int) -> dict | None:
    ys, xs = np.nonzero(mask_bin)
    if len(xs) == 0:
        return None
    x0, x1 = int(xs.min()), int(xs.max())
    y0, y1 = int(ys.min()), int(ys.max())
    return {
        "id": ann_id,
        "image_id": image_id,
        "category_id": category_id,
        "segmentation": encode_rle(mask_bin),
        "bbox": [x0, y0, x1 - x0 + 1, y1 - y0 + 1],
        "area": int(mask_bin.sum()),
        "iscrowd": 0,
    }


# ── Construction ─────────────────────────────────────────────────────────────

def collect_entries() -> list[tuple[Path, dict]]:
    """Retourne [(image, {catégorie: chemin_masque})] pour les images annotées."""
    entries = []
    exts = {".png", ".jpg", ".jpeg", ".webp"}
    for img_path in sorted(RAW_IMAGES.iterdir()):
        if img_path.suffix.lower() not in exts or img_path.name.startswith("_"):
            continue
        cat_masks = {}
        for cat in CAT_ID:
            mp = RAW_MASKS / f"{img_path.stem}__{cat}.png"
            if mp.exists():
                cat_masks[cat] = mp
        if cat_masks:
            entries.append((img_path, cat_masks))
    return entries


def build_split_json(entries: list[tuple[Path, dict]], split: str) -> dict:
    img_out  = IMAGES_DIR / split
    mask_out = MASKS_DIR / split
    img_out.mkdir(parents=True, exist_ok=True)
    mask_out.mkdir(parents=True, exist_ok=True)

    coco = {
        "info": {
            "description": "HandSegNet — anime hands/fingers/wrist segmentation (Ov3rLoRd)",
            "version": "1.0",
            "date_created": date.today().isoformat(),
        },
        "licenses": [],
        "categories": CATEGORIES,
        "images": [],
        "annotations": [],
    }

    ann_id = 1
    for image_id, (img_path, cat_masks) in enumerate(entries, start=1):
        img = Image.open(str(img_path))
        w, h = img.size

        anns = []
        for cat, mp in cat_masks.items():
            mask = Image.open(str(mp)).convert("L")
            if mask.size != (w, h):
                mask = mask.resize((w, h), Image.NEAREST)
            mask_bin = (np.array(mask) > 127).astype(np.uint8)
            ann = mask_to_annotation(mask_bin, ann_id, image_id, CAT_ID[cat])
            if ann is not None:
                anns.append((ann, mp))
                ann_id += 1

        if not anns:
            print(f"[build_coco] Aucun masque non vide pour {img_path.name} — ignoré")
            continue

        shutil.copy2(str(img_path), str(img_out / img_path.name))    # ADR-007
        for ann, mp in anns:
            shutil.copy2(str(mp), str(mask_out / mp.name))
            coco["annotations"].append(ann)

        coco["images"].append({
            "id": image_id,
            "file_name": img_path.name,
            "width": w,
            "height": h,
        })

    return coco


def main(val_ratio: float, split_seed: int) -> None:
    entries = collect_entries()
    if not entries:
        raise SystemExit(
            f"[build_coco] Aucune image annotée ({RAW_IMAGES} + {RAW_MASKS}) — "
            f"annoter d'abord avec annotate.py"
        )

    rng = random.Random(split_seed)
    shuffled = entries[:]
    rng.shuffle(shuffled)
    n_val = max(1, int(len(shuffled) * val_ratio))
    val_entries = shuffled[:n_val]
    train_entries = shuffled[n_val:]

    print(f"[build_coco] {len(entries)} images — train={len(train_entries)} val={len(val_entries)}")

    ANNOT_DIR.mkdir(parents=True, exist_ok=True)
    for split, split_entries in (("train", train_entries), ("val", val_entries)):
        coco = build_split_json(split_entries, split)
        out = ANNOT_DIR / f"instances_{split}.json"
        out.write_text(json.dumps(coco), encoding="utf-8")
        print(f"[build_coco] {out} : {len(coco['images'])} images, "
              f"{len(coco['annotations'])} annotations")

    print("[build_coco] Terminé — prêt pour train.py")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="HandSegNet — masques PNG → COCO JSON")
    parser.add_argument("--val-ratio",  type=float, default=0.1)
    parser.add_argument("--split-seed", type=int, default=1337)
    args = parser.parse_args()
    main(args.val_ratio, args.split_seed)

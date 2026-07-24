# ██████╗ ██╗   ██╗██████╗ ██████╗ ██╗      ██████╗ ██████╗ ██████╗
# ██╔═══██╗██║   ██║╚════██╗██╔══██╗██║     ██╔═══██╗██╔══██╗██╔══██╗
# ██║   ██║██║   ██║ █████╔╝██████╔╝██║     ██║   ██║██████╔╝██║  ██║
# ██║   ██║╚██╗ ██╔╝ ╚═══██╗██╔══██╗██║     ██║   ██║██╔══██╗██║  ██║
# ╚██████╔╝ ╚████╔╝ ██████╔╝██║  ██║███████╗╚██████╔╝██║  ██║██████╔╝
# ╚═════╝   ╚═══╝  ╚═════╝ ╚═╝  ╚═╝╚══════╝ ╚═════╝ ╚═╝  ╚═╝╚═════╝
# Ov3rLoRd -- pipeline de production anime autonome (ComfyUI)
# https://github.com/Ov3rLoRd-MLEngineer
#
# build_coco.py — BodySegNet (Ov3rLoRd Pipeline)
# Masques PNG multi-classes → COCO JSON (RLE non compressé) + split train/val.
# Même architecture que handsegnet\build_coco.py, avec les 4 catégories corps.
# Les masques peuvent se chevaucher (clothes recouvre torso/arms/legs) —
# chaque catégorie est une annotation indépendante.
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
PROJECT_ROOT = Path(r"D:\OVERLORD\bodysegnet")
RAW_IMAGES = PROJECT_ROOT / "dataset" / "raw"
RAW_MASKS  = PROJECT_ROOT / "dataset" / "masks_raw"
IMAGES_DIR = PROJECT_ROOT / "dataset" / "images"
MASKS_DIR  = PROJECT_ROOT / "dataset" / "masks"
ANNOT_DIR  = PROJECT_ROOT / "dataset" / "annotations"

CATEGORIES = [
    {"id": 1, "name": "torso",   "supercategory": "body"},
    {"id": 2, "name": "arms",    "supercategory": "body"},
    {"id": 3, "name": "legs",    "supercategory": "body"},
    {"id": 4, "name": "clothes", "supercategory": "body"},
]
CAT_ID = {c["name"]: c["id"] for c in CATEGORIES}

# (angle degrés, tag fichier) — rotation additionnelle, incliné gauche/droit
ROTATION_ANGLES = [(-15, "rotL15"), (15, "rotR15")]


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


# ── Augmentation ─────────────────────────────────────────────────────────────

def augment_hflip(img_path: Path, bins: dict,
                  img_out: Path, mask_out: Path) -> tuple:
    """
    Augmentation : flip horizontal (miroir gauche/droite) de l'image annotée
    ET de chacun de ses masques de catégorie. Écrit <stem>_hflip.<ext> dans
    images\\<split> et <stem>_hflip__<cat>.png dans masks\\<split>.

    Args:
        bins : {catégorie: masque_binaire HxW 0/1}

    Returns:
        (nom_fichier_image_flippée, {catégorie: masque_binaire_flippé}, image PIL flippée)
    """
    flip_name = f"{img_path.stem}_hflip{img_path.suffix}"
    img_flip = Image.open(str(img_path)).transpose(Image.FLIP_LEFT_RIGHT)
    img_flip.save(str(img_out / flip_name))
    flip_bins = {}
    for cat, mask_bin in bins.items():
        fb = np.fliplr(mask_bin).copy()
        Image.fromarray((fb * 255).astype(np.uint8), mode="L").save(
            str(mask_out / f"{img_path.stem}_hflip__{cat}.png"))
        flip_bins[cat] = fb
    return flip_name, flip_bins, img_flip


def augment_rotate(img: Image.Image, bins: dict, angle: float,
                   stem: str, tag: str, ext: str,
                   img_out: Path, mask_out: Path) -> tuple:
    """
    Augmentation : rotation de `angle`° autour du centre (canevas inchangé,
    coins découverts remplis en noir/fond) de l'image ET de chacun de ses
    masques de catégorie. Écrit <stem>_<tag>.<ext> dans images\\<split> et
    <stem>_<tag>__<cat>.png dans masks\\<split>. Image en bilinéaire, masques
    en plus-proche-voisin (restent binaires).

    Args:
        bins : {catégorie: masque_binaire HxW 0/1}

    Returns:
        (nom_fichier_image_pivotée, {catégorie: masque_binaire_pivoté})
    """
    name = f"{stem}_{tag}{ext}"
    img_rot = img.rotate(angle, resample=Image.BILINEAR)
    img_rot.save(str(img_out / name))
    rot_bins = {}
    for cat, mask_bin in bins.items():
        mask_img = Image.fromarray((mask_bin * 255).astype(np.uint8), mode="L")
        mask_rot = mask_img.rotate(angle, resample=Image.NEAREST, fillcolor=0)
        rb = (np.array(mask_rot) > 127).astype(np.uint8)
        Image.fromarray((rb * 255).astype(np.uint8), mode="L").save(
            str(mask_out / f"{stem}_{tag}__{cat}.png"))
        rot_bins[cat] = rb
    return name, rot_bins


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


def build_split_json(entries: list[tuple[Path, dict]], split: str,
                     augment: bool = False) -> dict:
    img_out  = IMAGES_DIR / split
    mask_out = MASKS_DIR / split
    img_out.mkdir(parents=True, exist_ok=True)
    mask_out.mkdir(parents=True, exist_ok=True)

    coco = {
        "info": {
            "description": "BodySegNet — anime body/clothes segmentation (Ov3rLoRd)",
            "version": "1.0",
            "date_created": date.today().isoformat(),
        },
        "licenses": [],
        "categories": CATEGORIES,
        "images": [],
        "annotations": [],
    }

    ann_id = 1
    image_id = 0
    flipped = 0
    rotated = 0
    for img_path, cat_masks in entries:
        img = Image.open(str(img_path))
        w, h = img.size

        bins = {}
        for cat, mp in cat_masks.items():
            mask = Image.open(str(mp)).convert("L")
            if mask.size != (w, h):
                mask = mask.resize((w, h), Image.NEAREST)
            mask_bin = (np.array(mask) > 127).astype(np.uint8)
            if mask_bin.any():
                bins[cat] = (mask_bin, mp)

        if not bins:
            print(f"[build_coco] Aucun masque non vide pour {img_path.name} — ignoré")
            continue

        # Image originale
        image_id += 1
        shutil.copy2(str(img_path), str(img_out / img_path.name))    # ADR-007
        coco["images"].append({
            "id": image_id,
            "file_name": img_path.name,
            "width": w,
            "height": h,
        })
        for cat, (mask_bin, mp) in bins.items():
            shutil.copy2(str(mp), str(mask_out / mp.name))
            coco["annotations"].append(
                mask_to_annotation(mask_bin, ann_id, image_id, CAT_ID[cat]))
            ann_id += 1

        # Augmentation : flip horizontal + rotation ±15° (seules ou combinées)
        # → jusqu'à 6 variantes par image (recto/verso × normal/incliné G/D).
        if augment:
            base_bins = {c: b for c, (b, _mp) in bins.items()}

            image_id += 1
            flip_name, flip_bins, img_flip = augment_hflip(
                img_path, base_bins, img_out, mask_out)
            coco["images"].append({
                "id": image_id,
                "file_name": flip_name,
                "width": w,
                "height": h,
            })
            for cat, fb in flip_bins.items():
                coco["annotations"].append(
                    mask_to_annotation(fb, ann_id, image_id, CAT_ID[cat]))
                ann_id += 1
            flipped += 1

            for base_img, base, base_tag in (
                (img, base_bins, ""), (img_flip, flip_bins, "hflip_"),
            ):
                for angle, tag in ROTATION_ANGLES:
                    image_id += 1
                    rot_name, rot_bins = augment_rotate(
                        base_img, base, angle, img_path.stem,
                        f"{base_tag}{tag}", img_path.suffix, img_out, mask_out)
                    coco["images"].append({
                        "id": image_id,
                        "file_name": rot_name,
                        "width": w,
                        "height": h,
                    })
                    for cat, rb in rot_bins.items():
                        ann = mask_to_annotation(rb, ann_id, image_id, CAT_ID[cat])
                        if ann is not None:
                            coco["annotations"].append(ann)
                        ann_id += 1
                    rotated += 1

    if flipped:
        print(f"[build_coco] {split} : {flipped} flips horizontaux ajoutés")
    if rotated:
        print(f"[build_coco] {split} : {rotated} rotations ±15° ajoutées")
    return coco


def main(val_ratio: float, split_seed: int,
         no_augment: bool = False, augment_val: bool = False) -> None:
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
        # Flip horizontal sur le train uniquement par défaut (le val reste
        # non augmenté pour une métrique IoU honnête) — --augment-val pour forcer.
        do_aug = (not no_augment) and (split == "train" or augment_val)
        coco = build_split_json(split_entries, split, augment=do_aug)
        out = ANNOT_DIR / f"instances_{split}.json"
        out.write_text(json.dumps(coco), encoding="utf-8")
        print(f"[build_coco] {out} : {len(coco['images'])} images, "
              f"{len(coco['annotations'])} annotations")

    print("[build_coco] Terminé — prêt pour train.py")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="BodySegNet — masques PNG -> COCO JSON")
    parser.add_argument("--val-ratio",  type=float, default=0.1)
    parser.add_argument("--split-seed", type=int, default=1337)
    parser.add_argument("--no-augment", action="store_true",
                        help="Désactive l'augmentation par flip horizontal")
    parser.add_argument("--augment-val", action="store_true",
                        help="Applique aussi le flip horizontal au split val")
    args = parser.parse_args()
    main(args.val_ratio, args.split_seed, args.no_augment, args.augment_val)

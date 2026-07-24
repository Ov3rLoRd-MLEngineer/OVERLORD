# ██████╗ ██╗   ██╗██████╗ ██████╗ ██╗      ██████╗ ██████╗ ██████╗
# ██╔═══██╗██║   ██║╚════██╗██╔══██╗██║     ██╔═══██╗██╔══██╗██╔══██╗
# ██║   ██║██║   ██║ █████╔╝██████╔╝██║     ██║   ██║██████╔╝██║  ██║
# ██║   ██║╚██╗ ██╔╝ ╚═══██╗██╔══██╗██║     ██║   ██║██╔══██╗██║  ██║
# ╚██████╔╝ ╚████╔╝ ██████╔╝██║  ██║███████╗╚██████╔╝██║  ██║██████╔╝
# ╚═════╝   ╚═══╝  ╚═════╝ ╚═╝  ╚═╝╚══════╝ ╚═════╝ ╚═╝  ╚═╝╚═════╝
# Ov3rLoRd -- pipeline de production anime autonome (ComfyUI)
# https://github.com/Ov3rLoRd-MLEngineer
#
# build_coco.py — FootSegNet (Ov3rLoRd Pipeline)
# Construit le dataset au format COCO à partir des paires image/masque annotées :
#   dataset\raw\*.png + dataset\masks_raw\*.png
#     → split reproductible train/val (copy2, jamais de move — ADR-007)
#     → dataset\images\{train,val}\ + dataset\masks\{train,val}\
#     → dataset\annotations\instances_{train,val}.json (RLE non compressé COCO)
#
# Catégorie unique : id=1 "foot_shoe".
# Convention masque dataset : BLANC (>127) = pied/chaussure, NOIR = fond.
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
FOOTSEGNET_ROOT = Path(r"D:\OVERLORD\footsegnet")
RAW_IMAGES  = FOOTSEGNET_ROOT / "dataset" / "raw"
RAW_MASKS   = FOOTSEGNET_ROOT / "dataset" / "masks_raw"
IMAGES_DIR  = FOOTSEGNET_ROOT / "dataset" / "images"
MASKS_DIR   = FOOTSEGNET_ROOT / "dataset" / "masks"
ANNOT_DIR   = FOOTSEGNET_ROOT / "dataset" / "annotations"

CATEGORY = {"id": 1, "name": "foot_shoe", "supercategory": "body_part"}

# (angle degrés, tag fichier) — rotation additionnelle, incliné gauche/droit
ROTATION_ANGLES = [(-15, "rotL15"), (15, "rotR15")]


# ── RLE COCO (non compressé, ordre colonne / Fortran) ────────────────────────

def encode_rle(mask_bin: np.ndarray) -> dict:
    """
    Encode un masque binaire HxW en RLE COCO non compressé :
    counts = longueurs alternées de 0 puis 1, aplatissement en ordre colonne.
    """
    flat = mask_bin.flatten(order="F").astype(np.uint8)
    counts = []
    current = 0   # COCO commence toujours par le nombre de zéros
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
    """Décode un RLE COCO non compressé en masque binaire HxW (uint8 0/1)."""
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


def mask_to_annotation(mask_bin: np.ndarray, ann_id: int, image_id: int) -> dict | None:
    """Convertit un masque binaire en annotation COCO (bbox + RLE + area)."""
    ys, xs = np.nonzero(mask_bin)
    if len(xs) == 0:
        return None
    x0, x1 = int(xs.min()), int(xs.max())
    y0, y1 = int(ys.min()), int(ys.max())
    return {
        "id": ann_id,
        "image_id": image_id,
        "category_id": CATEGORY["id"],
        "segmentation": encode_rle(mask_bin),
        "bbox": [x0, y0, x1 - x0 + 1, y1 - y0 + 1],
        "area": int(mask_bin.sum()),
        "iscrowd": 0,
    }


# ── Augmentation ─────────────────────────────────────────────────────────────

def augment_hflip(img_path: Path, mask_bin: np.ndarray,
                  img_out: Path, mask_out: Path) -> tuple:
    """
    Augmentation : flip horizontal (miroir gauche/droite) de l'image annotée
    ET de son masque. Écrit <stem>_hflip.<ext> dans images\\<split> et
    <stem>_hflip.png dans masks\\<split>.

    Returns:
        (nom_fichier_image_flippée, masque_binaire_flippé HxW 0/1, image PIL flippée)
    """
    flip_name = f"{img_path.stem}_hflip{img_path.suffix}"
    img_flip = Image.open(str(img_path)).transpose(Image.FLIP_LEFT_RIGHT)
    img_flip.save(str(img_out / flip_name))
    flip_bin = np.fliplr(mask_bin).copy()
    Image.fromarray((flip_bin * 255).astype(np.uint8), mode="L").save(
        str(mask_out / f"{img_path.stem}_hflip.png"))
    return flip_name, flip_bin, img_flip


def augment_rotate(img: Image.Image, mask_bin: np.ndarray, angle: float,
                   stem: str, tag: str, ext: str,
                   img_out: Path, mask_out: Path) -> tuple:
    """
    Augmentation : rotation de `angle`° autour du centre (canevas inchangé,
    coins découverts remplis en noir/fond) de l'image ET de son masque.
    Écrit <stem>_<tag>.<ext> dans images\\<split> et <stem>_<tag>.png dans
    masks\\<split>. Image en bilinéaire, masque en plus-proche-voisin (le
    masque reste binaire — pas de valeurs intermédiaires sur les bords).

    Returns:
        (nom_fichier_image_pivotée, masque_binaire_pivoté HxW 0/1)
    """
    name = f"{stem}_{tag}{ext}"
    img_rot = img.rotate(angle, resample=Image.BILINEAR)
    img_rot.save(str(img_out / name))
    mask_img = Image.fromarray((mask_bin * 255).astype(np.uint8), mode="L")
    mask_rot = mask_img.rotate(angle, resample=Image.NEAREST, fillcolor=0)
    rot_bin = (np.array(mask_rot) > 127).astype(np.uint8)
    Image.fromarray((rot_bin * 255).astype(np.uint8), mode="L").save(
        str(mask_out / f"{stem}_{tag}.png"))
    return name, rot_bin


# ── Construction ─────────────────────────────────────────────────────────────

def collect_pairs() -> list[tuple[Path, Path]]:
    """Retourne les paires (image, masque) dont l'annotation existe et n'est pas vide."""
    pairs = []
    exts = {".png", ".jpg", ".jpeg", ".webp"}
    for img_path in sorted(RAW_IMAGES.iterdir()):
        if img_path.suffix.lower() not in exts or img_path.name.startswith("_"):
            continue
        mask_path = RAW_MASKS / f"{img_path.stem}.png"
        if mask_path.exists():
            pairs.append((img_path, mask_path))
    return pairs


def build_split_json(pairs: list[tuple[Path, Path]], split: str,
                     augment: bool = False) -> dict:
    """Copie images/masques du split et construit le JSON COCO correspondant.
    Si augment=True, ajoute le flip horizontal de chaque paire au dataset."""
    img_out  = IMAGES_DIR / split
    mask_out = MASKS_DIR / split
    img_out.mkdir(parents=True, exist_ok=True)
    mask_out.mkdir(parents=True, exist_ok=True)

    coco = {
        "info": {
            "description": "FootSegNet — anime feet/shoes segmentation (Ov3rLoRd)",
            "version": "1.0",
            "date_created": date.today().isoformat(),
        },
        "licenses": [],
        "categories": [CATEGORY],
        "images": [],
        "annotations": [],
    }

    ann_id = 1
    image_id = 0
    skipped = 0
    flipped = 0
    rotated = 0
    for img_path, mask_path in pairs:
        img = Image.open(str(img_path))
        w, h = img.size
        mask = Image.open(str(mask_path)).convert("L")
        if mask.size != (w, h):
            mask = mask.resize((w, h), Image.NEAREST)
        mask_bin = (np.array(mask) > 127).astype(np.uint8)

        image_id += 1
        ann = mask_to_annotation(mask_bin, ann_id, image_id)
        if ann is None:
            print(f"[build_coco] Masque vide, ignoré : {mask_path.name}")
            skipped += 1
            image_id -= 1
            continue

        shutil.copy2(str(img_path), str(img_out / img_path.name))    # ADR-007
        shutil.copy2(str(mask_path), str(mask_out / mask_path.name))

        coco["images"].append({
            "id": image_id,
            "file_name": img_path.name,
            "width": w,
            "height": h,
        })
        coco["annotations"].append(ann)
        ann_id += 1

        # Augmentation : flip horizontal + rotation ±15° (seules ou combinées)
        # → jusqu'à 6 variantes par paire (recto/verso × normal/incliné G/D).
        if augment:
            image_id += 1
            flip_name, flip_bin, img_flip = augment_hflip(
                img_path, mask_bin, img_out, mask_out)
            coco["images"].append({
                "id": image_id,
                "file_name": flip_name,
                "width": w,
                "height": h,
            })
            coco["annotations"].append(
                mask_to_annotation(flip_bin, ann_id, image_id))
            ann_id += 1
            flipped += 1

            for base_img, base_bin, base_tag in (
                (img, mask_bin, ""), (img_flip, flip_bin, "hflip_"),
            ):
                for angle, tag in ROTATION_ANGLES:
                    image_id += 1
                    rot_name, rot_bin = augment_rotate(
                        base_img, base_bin, angle, img_path.stem,
                        f"{base_tag}{tag}", img_path.suffix, img_out, mask_out)
                    coco["images"].append({
                        "id": image_id,
                        "file_name": rot_name,
                        "width": w,
                        "height": h,
                    })
                    ann = mask_to_annotation(rot_bin, ann_id, image_id)
                    if ann is not None:
                        coco["annotations"].append(ann)
                    ann_id += 1
                    rotated += 1

    if skipped:
        print(f"[build_coco] {split} : {skipped} masque(s) vide(s) ignoré(s)")
    if flipped:
        print(f"[build_coco] {split} : {flipped} flips horizontaux ajoutés")
    if rotated:
        print(f"[build_coco] {split} : {rotated} rotations ±15° ajoutées")
    return coco


def main(val_ratio: float, split_seed: int,
         no_augment: bool = False, augment_val: bool = False) -> None:
    pairs = collect_pairs()
    if not pairs:
        raise SystemExit(
            f"[build_coco] Aucune paire image/masque trouvée "
            f"({RAW_IMAGES} + {RAW_MASKS}) — annoter d'abord avec annotate.py"
        )

    rng = random.Random(split_seed)
    shuffled = pairs[:]
    rng.shuffle(shuffled)
    n_val = max(1, int(len(shuffled) * val_ratio))
    val_pairs = shuffled[:n_val]
    train_pairs = shuffled[n_val:]

    print(f"[build_coco] {len(pairs)} paires — train={len(train_pairs)} val={len(val_pairs)}")

    ANNOT_DIR.mkdir(parents=True, exist_ok=True)
    for split, split_pairs in (("train", train_pairs), ("val", val_pairs)):
        # Flip horizontal sur le train uniquement par défaut (le val reste
        # non augmenté pour une métrique IoU honnête) — --augment-val pour forcer.
        do_aug = (not no_augment) and (split == "train" or augment_val)
        coco = build_split_json(split_pairs, split, augment=do_aug)
        out = ANNOT_DIR / f"instances_{split}.json"
        out.write_text(json.dumps(coco), encoding="utf-8")
        print(f"[build_coco] {out} : {len(coco['images'])} images, "
              f"{len(coco['annotations'])} annotations")

    print("[build_coco] Terminé — prêt pour train_sam.py")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="FootSegNet — masques PNG -> COCO JSON")
    parser.add_argument("--val-ratio",  type=float, default=0.1,
                        help="Fraction validation (défaut: 0.1)")
    parser.add_argument("--split-seed", type=int, default=1337,
                        help="Seed du split (reproductible)")
    parser.add_argument("--no-augment", action="store_true",
                        help="Désactive l'augmentation par flip horizontal")
    parser.add_argument("--augment-val", action="store_true",
                        help="Applique aussi le flip horizontal au split val")
    args = parser.parse_args()
    main(args.val_ratio, args.split_seed, args.no_augment, args.augment_val)

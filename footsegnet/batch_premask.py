# batch_premask.py — FootSegNet (Ov3rLoRd Pipeline)
# Génère en batch les pré-masques (pose DWPose -> box pied -> SAM + raffinement
# de infer.py) pour toutes les images de dataset\raw\ qui n'ont pas encore de
# masque annoté à la main, afin de pré-remplir annotate.py (voir tâche
# suivante) et accélérer la correction manuelle sur les images restantes.
#
# Écrit UNIQUEMENT dans dataset\premasks\ -- jamais dans dataset\masks_raw\,
# pour ne jamais écraser du travail d'annotation manuel déjà fait.
#
# Convention : BLANC (255) = pied/chaussure, NOIR (0) = fond (convention ML,
# la même que masks_raw -- pas la convention pipeline inpaint de infer.py).
#
# Usage :
#   py -3.12 batch_premask.py
#   py -3.12 batch_premask.py --clean --limit 20

import argparse
from datetime import datetime
from pathlib import Path

import numpy as np
from PIL import Image
from scipy import ndimage

from infer import generate_foot_mask
from _pose_box import foot_box_for_image

# ── CONFIG ────────────────────────────────────────────────────────────────────
FOOTSEGNET_ROOT = Path(r"D:\OVERLORD\footsegnet")
RAW_IMAGES  = FOOTSEGNET_ROOT / "dataset" / "raw"
MASKS_RAW   = FOOTSEGNET_ROOT / "dataset" / "masks_raw"
PREMASKS    = FOOTSEGNET_ROOT / "dataset" / "premasks"
FAILURE_LOG = PREMASKS / "_failures.log"


def clean_mask(mask_bin: np.ndarray, keep: int = 2) -> np.ndarray:
    """
    Garde les `keep` plus grosses composantes connexes du masque binaire,
    retire le reste (bruit type point isolé observé sur footsegnet_00112).
    """
    labeled, n = ndimage.label(mask_bin)
    if n <= keep:
        return mask_bin
    sizes = ndimage.sum(mask_bin, labeled, index=range(1, n + 1))
    keep_labels = set((np.argsort(sizes)[::-1][:keep] + 1).tolist())
    return np.isin(labeled, list(keep_labels)).astype(np.uint8)


def collect_unannotated() -> list[Path]:
    """Images de dataset/raw/ sans masque correspondant dans masks_raw/."""
    exts = {".png", ".jpg", ".jpeg", ".webp"}
    result = []
    for img_path in sorted(RAW_IMAGES.iterdir()):
        if img_path.suffix.lower() not in exts or img_path.name.startswith("_"):
            continue
        if (MASKS_RAW / f"{img_path.stem}.png").exists():
            continue
        result.append(img_path)
    return result


def run(limit: int | None, clean: bool, refine: bool, threshold: float) -> None:
    images = collect_unannotated()
    if limit:
        images = images[:limit]
    PREMASKS.mkdir(parents=True, exist_ok=True)

    print(f"[batch_premask] {len(images)} image(s) sans masque manuel à traiter")

    ok = 0
    pose_failed: list[str] = []
    infer_failed: list[str] = []

    for i, img_path in enumerate(images, 1):
        box = foot_box_for_image(img_path)
        if box is None:
            print(f"[batch_premask] ({i}/{len(images)}) Pose non détectée, ignoré : {img_path.name}")
            pose_failed.append(img_path.name)
            continue

        out_path = PREMASKS / f"{img_path.stem}.png"
        result = generate_foot_mask(
            frame_path=str(img_path), zone=box, output_path=str(out_path),
            threshold=threshold, pipeline_convention=False, feather_px=0,
            refine=refine,
        )
        if result is None:
            print(f"[batch_premask] ({i}/{len(images)}) Inférence échouée, ignoré : {img_path.name}")
            infer_failed.append(img_path.name)
            continue

        if clean:
            mask_bin = (np.array(Image.open(str(out_path)).convert("L")) > 127).astype(np.uint8)
            cleaned = clean_mask(mask_bin)
            Image.fromarray(cleaned * 255, mode="L").save(str(out_path))

        ok += 1
        print(f"[batch_premask] ({i}/{len(images)}) -> {out_path.name}")

    total_failed = len(pose_failed) + len(infer_failed)
    print(f"\n[batch_premask] Terminé : {ok} pré-masque(s) généré(s), {total_failed} échec(s)")

    if pose_failed or infer_failed:
        ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        lines = [f"[{ts}] batch_premask -- {ok} OK, "
                f"{len(pose_failed)} échec(s) pose, {len(infer_failed)} échec(s) inférence"]
        lines += [f"  POSE   {n}" for n in pose_failed]
        lines += [f"  INFER  {n}" for n in infer_failed]
        with open(FAILURE_LOG, "a", encoding="utf-8") as f:
            f.write("\n".join(lines) + "\n")
        print(f"[batch_premask] Échecs journalisés -> {FAILURE_LOG}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="FootSegNet — génération batch de pré-masques (images raw sans masque manuel)"
    )
    parser.add_argument("--limit", type=int, default=None,
                        help="Limiter aux N premières images (test rapide)")
    parser.add_argument("--clean", action="store_true",
                        help="Garde les 2 plus grosses composantes connexes, retire le bruit isolé")
    parser.add_argument("--refine", action=argparse.BooleanOptionalAction, default=True,
                        help="Raffinement itératif de infer.py (défaut: activé)")
    parser.add_argument("--threshold", type=float, default=0.5)
    args = parser.parse_args()

    run(limit=args.limit, clean=args.clean, refine=args.refine, threshold=args.threshold)

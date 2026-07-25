# analyze_errors.py — FootSegNet (Ov3rLoRd Pipeline)
# Compare le pré-masque auto (infer.py, box dérivée des chevilles DWPose) au
# masque corrigé à la main (dataset\masks_raw\) pour les images déjà
# annotées, afin d'identifier où le modèle/la box automatique se trompe le
# plus avant de lancer la génération batch sur les images restantes
# (batch_premask.py).
#
# IMPORTANT : IoU calculé sur train ET val, mais SÉPARÉMENT rapportés — un
# score train élevé n'indique PAS une bonne généralisation (données vues à
# l'entraînement) — seul le score val est représentatif de ce à quoi
# s'attendre sur des images inédites.
#
# Usage :
#   py -3.12 analyze_errors.py
#   py -3.12 analyze_errors.py --limit 20 --no-refine

import argparse
import json
from pathlib import Path

import numpy as np
from PIL import Image

import sys
_REPO_ROOT = Path(__file__).resolve().parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))
import config

from infer import generate_foot_mask
from _pose_box import foot_box_for_image

# ── CONFIG ────────────────────────────────────────────────────────────────────
FOOTSEGNET_ROOT = config.FOOTSEGNET_ROOT
RAW_IMAGES  = FOOTSEGNET_ROOT / "dataset" / "raw"
RAW_MASKS   = FOOTSEGNET_ROOT / "dataset" / "masks_raw"
ANNOT_DIR   = FOOTSEGNET_ROOT / "dataset" / "annotations"
OUT_DIR     = FOOTSEGNET_ROOT / "dataset" / "error_analysis"

DIFF_FP_COLOR = (255, 40, 40)   # rouge : auto=objet, manuel=fond (faux positif)
DIFF_FN_COLOR = (40, 90, 255)   # bleu  : auto=fond, manuel=objet (faux négatif)
DIFF_ALPHA    = 140


def collect_pairs() -> list[tuple[Path, Path]]:
    """Paires (image, masque manuel) — même logique que build_coco.collect_pairs()."""
    pairs = []
    exts = {".png", ".jpg", ".jpeg", ".webp"}
    for img_path in sorted(RAW_IMAGES.iterdir()):
        if img_path.suffix.lower() not in exts or img_path.name.startswith("_"):
            continue
        mask_path = RAW_MASKS / f"{img_path.stem}.png"
        if mask_path.exists():
            pairs.append((img_path, mask_path))
    return pairs


def load_split_membership() -> tuple[set, set]:
    """
    Noms de fichiers (file_name COCO, non augmentés) appartenant à train/val.
    Les copies augmentées (hflip/rotation) portent toujours un suffixe -- seule
    la copie "plain" a un file_name strictement égal au nom du fichier raw --
    donc tester l'appartenance du nom raw suffit à distinguer les deux splits.
    """
    train_path = ANNOT_DIR / "instances_train.json"
    val_path   = ANNOT_DIR / "instances_val.json"
    if not train_path.exists() or not val_path.exists():
        print(f"[analyze_errors] annotations COCO introuvables dans {ANNOT_DIR} "
              f"— lancer build_coco.py d'abord pour distinguer train/val. "
              f"Tous les résultats seront marqués 'unknown'.")
        return set(), set()
    train_names = {i["file_name"] for i in json.loads(train_path.read_text(encoding="utf-8"))["images"]}
    val_names   = {i["file_name"] for i in json.loads(val_path.read_text(encoding="utf-8"))["images"]}
    return train_names, val_names


def compute_iou(auto_bin: np.ndarray, manual_bin: np.ndarray) -> float:
    inter = np.logical_and(auto_bin, manual_bin).sum()
    union = np.logical_or(auto_bin, manual_bin).sum()
    return float(inter) / float(union) if union > 0 else 1.0


def build_diff_image(img: Image.Image, auto_bin: np.ndarray, manual_bin: np.ndarray) -> Image.Image:
    """Overlay rouge=faux positif (auto en trop), bleu=faux négatif (auto manquant)."""
    fp = np.logical_and(auto_bin, np.logical_not(manual_bin))
    fn = np.logical_and(np.logical_not(auto_bin), manual_bin)

    overlay = img.convert("RGB").copy()
    w, h = overlay.size

    fp_layer = Image.new("RGB", (w, h), DIFF_FP_COLOR)
    fp_alpha = Image.fromarray((fp.astype(np.uint8) * DIFF_ALPHA), mode="L")
    overlay.paste(fp_layer, (0, 0), fp_alpha)

    fn_layer = Image.new("RGB", (w, h), DIFF_FN_COLOR)
    fn_alpha = Image.fromarray((fn.astype(np.uint8) * DIFF_ALPHA), mode="L")
    overlay.paste(fn_layer, (0, 0), fn_alpha)

    return overlay


def analyze(limit: int | None, refine: bool, threshold: float) -> None:
    pairs = collect_pairs()
    if not pairs:
        raise SystemExit(f"[analyze_errors] Aucune paire trouvée dans {RAW_IMAGES} / {RAW_MASKS}")
    if limit:
        pairs = pairs[:limit]

    train_names, val_names = load_split_membership()
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    results = []
    skipped = []

    for img_path, mask_path in pairs:
        split = "val" if img_path.name in val_names else (
            "train" if img_path.name in train_names else "unknown")

        box = foot_box_for_image(img_path)
        if box is None:
            print(f"[analyze_errors] Box pied non dérivable, ignoré : {img_path.name}")
            skipped.append(img_path.name)
            continue

        tmp_out = OUT_DIR / f"_tmp_{img_path.stem}_premask.png"
        auto_path = generate_foot_mask(
            frame_path=str(img_path), zone=box, output_path=str(tmp_out),
            threshold=threshold, pipeline_convention=False, feather_px=0,
            refine=refine,
        )
        if auto_path is None:
            print(f"[analyze_errors] Inférence échouée, ignoré : {img_path.name}")
            skipped.append(img_path.name)
            continue

        auto_bin = (np.array(Image.open(auto_path).convert("L")) > 127).astype(np.uint8)
        src_img = Image.open(str(img_path))
        manual = Image.open(str(mask_path)).convert("L")
        if manual.size != src_img.size:
            manual = manual.resize(src_img.size, Image.NEAREST)
        manual_bin = (np.array(manual) > 127).astype(np.uint8)

        iou = compute_iou(auto_bin, manual_bin)

        diff_img = build_diff_image(src_img, auto_bin, manual_bin)
        diff_path = OUT_DIR / f"{img_path.stem}_diff.png"
        diff_img.save(str(diff_path))

        tmp_out.unlink(missing_ok=True)

        results.append({
            "stem": img_path.stem,
            "split": split,
            "iou": iou,
            "diff_path": str(diff_path),
        })
        print(f"[analyze_errors] {img_path.name} [{split}] IoU={iou:.4f}")

    results.sort(key=lambda r: r["iou"])  # pire -> meilleur

    report_path = OUT_DIR / "report.txt"
    lines = [
        "FootSegNet — analyse d'erreurs pré-masque auto vs masque manuel",
        f"refine={refine}  threshold={threshold}",
        f"{len(results)} image(s) analysée(s), {len(skipped)} ignorée(s) (box non dérivable)",
        "",
        "Rappel : les scores TRAIN ne sont PAS un indicateur de généralisation "
        "(données vues à l'entraînement) — seul VAL l'est.",
        "",
        f"{'rang':>4}  {'split':<7}  {'IoU':>7}  stem",
        "-" * 60,
    ]
    for i, r in enumerate(results, 1):
        lines.append(f"{i:>4}  {r['split']:<7}  {r['iou']:>7.4f}  {r['stem']}")

    for split_name in ("train", "val", "unknown"):
        subset = [r["iou"] for r in results if r["split"] == split_name]
        if subset:
            lines.append("")
            lines.append(f"{split_name.upper()} (n={len(subset)}) : "
                         f"IoU moyen={np.mean(subset):.4f}  min={np.min(subset):.4f}  "
                         f"max={np.max(subset):.4f}")

    if skipped:
        lines.append("")
        lines.append("Ignorées (box pied non dérivable) :")
        lines.extend(f"  - {name}" for name in skipped)

    report_path.write_text("\n".join(lines), encoding="utf-8")
    print(f"\n[analyze_errors] Rapport -> {report_path}")
    print(f"[analyze_errors] Diffs visuelles -> {OUT_DIR}\\<stem>_diff.png")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="FootSegNet — analyse d'erreurs pré-masque auto vs masque manuel"
    )
    parser.add_argument("--limit", type=int, default=None,
                        help="Limiter aux N premières paires (test rapide)")
    parser.add_argument("--refine", action=argparse.BooleanOptionalAction, default=True,
                        help="Utilise le raffinement itératif de infer.py (défaut: activé)")
    parser.add_argument("--threshold", type=float, default=0.5)
    args = parser.parse_args()

    analyze(limit=args.limit, refine=args.refine, threshold=args.threshold)

# ██████╗ ██╗   ██╗██████╗ ██████╗ ██╗      ██████╗ ██████╗ ██████╗
# ██╔═══██╗██║   ██║╚════██╗██╔══██╗██║     ██╔═══██╗██╔══██╗██╔══██╗
# ██║   ██║██║   ██║ █████╔╝██████╔╝██║     ██║   ██║██████╔╝██║  ██║
# ██║   ██║╚██╗ ██╔╝ ╚═══██╗██╔══██╗██║     ██║   ██║██╔══██╗██║  ██║
# ╚██████╔╝ ╚████╔╝ ██████╔╝██║  ██║███████╗╚██████╔╝██║  ██║██████╔╝
# ╚═════╝   ╚═══╝  ╚═════╝ ╚═╝  ╚═╝╚══════╝ ╚═════╝ ╚═╝  ╚═╝═════╝
# Ov3rLoRd -- pipeline de production anime autonome (ComfyUI)
# https://github.com/Ov3rLoRd-MLEngineer
#
# box_source_compare.py — HandSegNet
#
# Compare deux sources de boite englobante pour l'inference HandSegNet :
#   - VLM grounding actuel (agents.vlm_grounding, deja utilise par
#     batch_premask.py en production) -- IoU REUTILISEE depuis
#     dataset/premasks/_provenance.csv (evaluation qualitative du
#     2026-07-29, pas re-interrogee : memes images, meme checkpoint,
#     resultat deterministe a l'identique)
#   - YOLO specialise mains (hand_yolov9c.pt, Bingsu/adetailer, deja
#     present dans l'install ComfyUI personnelle -- pas de telechargement
#     necessaire) -- calculee dans ce script
#
# Meme mecanique d'inference que la production (agents.segnet_premask.
# _infer_union : une passe SAM par boite detectee, union des masques,
# checkpoint handsegnet_vit_b_best.pth via infer.py).
#
# Script de TEST ISOLE : ne touche pas au pipeline de production
# (batch_premask.py / segnet_premask.py) -- lecture seule sur le dataset,
# ecrit uniquement dans dataset/error_analysis/box_source_compare/.
#
# Usage :
#   py -3.12 box_source_compare.py
#   py -3.12 box_source_compare.py --stems 00138,00095,00274 --yolo-conf 0.25

import argparse
import csv
import sys
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw

_REPO_ROOT = Path(__file__).resolve().parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))
import config

from infer import generate_part_mask  # noqa: E402
from agents.segnet_premask import _infer_union, _iou  # noqa: E402

PROJECT_ROOT = config.HANDSEGNET_ROOT
RAW_IMAGES = PROJECT_ROOT / "dataset" / "raw"
RAW_MASKS = PROJECT_ROOT / "dataset" / "masks_raw"
PROVENANCE_CSV = PROJECT_ROOT / "dataset" / "premasks" / "_provenance.csv"
OUT_DIR = PROJECT_ROOT / "dataset" / "error_analysis" / "box_source_compare"

YOLO_MODEL_PATH = Path(r"D:\Ov3rLoRd AI\ComfyUI\models\ultralytics\bbox\hand_yolov9c.pt")
YOLO_MARGIN_PX = 20  # meme marge par defaut que agents.vlm_grounding.DEFAULT_MARGIN

DEFAULT_STEMS = [
    "handsegnet_00138",  # VLM : echec total (box sur le poignet)
    "handsegnet_00095",  # VLM : une main sur deux detectee
    "handsegnet_00274",  # VLM : IoU=0.96 (bon cas -- verifier l'absence de regression)
    "handsegnet_00108",  # VLM : IoU=0.92
    "handsegnet_00044",  # VLM : IoU=0.92
    "handsegnet_00079",  # VLM : IoU=0.93
]


def load_vlm_iou(csv_path: Path) -> dict[str, float]:
    """IoU vs masque manuel deja mesuree pour la source VLM (evaluation du
    2026-07-29) -- derniere ligne par image (les stems requalifies comme
    00167 ont plusieurs lignes, on garde la plus recente)."""
    if not csv_path.exists():
        return {}
    by_stem: dict[str, float] = {}
    with open(csv_path, encoding="utf-8-sig", newline="") as f:
        for row in csv.DictReader(f):
            stem = Path(row["image"]).stem
            iou_raw = (row.get("iou_manual") or "").strip()
            if iou_raw:
                by_stem[stem] = float(iou_raw)
    return by_stem


def yolo_boxes_for_image(model, image_path: Path, conf: float,
                         margin_px: int = YOLO_MARGIN_PX) -> tuple[list[tuple[int, int, int, int]], list[float]]:
    """Boites main (x, y, w, h) detectees par YOLO, avec marge -- meme
    convention que agents.vlm_grounding._to_zone. Retourne (boites, confidences)."""
    results = model.predict(str(image_path), conf=conf, verbose=False)
    boxes: list[tuple[int, int, int, int]] = []
    confs: list[float] = []
    if not results:
        return boxes, confs
    r = results[0]
    for box_xyxy, c in zip(r.boxes.xyxy.tolist(), r.boxes.conf.tolist()):
        x1, y1, x2, y2 = box_xyxy
        boxes.append((
            int(x1 - margin_px), int(y1 - margin_px),
            int((x2 - x1) + 2 * margin_px), int((y2 - y1) + 2 * margin_px),
        ))
        confs.append(float(c))
    return boxes, confs


def build_qc_image(source: Image.Image, boxes: list[tuple[int, int, int, int]],
                   mask_bin: np.ndarray, label: str) -> Image.Image:
    """2 panneaux : source+boites | masque -- meme esprit visuel que
    agents.segnet_premask._build_compare, en plus simple (un seul panneau
    source, pas de redimensionnement)."""
    src = source.convert("RGB").copy()
    draw = ImageDraw.Draw(src)
    for (x, y, w, h) in boxes:
        draw.rectangle([x, y, x + w, y + h], outline=(0, 255, 0), width=3)
    draw.text((5, 5), f"{label}", fill=(255, 255, 0))

    mask_img = Image.fromarray((mask_bin * 255).astype(np.uint8), mode="L").convert("RGB")

    w, h = src.size
    combo = Image.new("RGB", (w * 2 + 2, h), (0, 0, 0))
    combo.paste(src, (0, 0))
    combo.paste(mask_img, (w + 2, 0))
    return combo


def run(stems: list[str], yolo_conf: float) -> None:
    from ultralytics import YOLO

    if not YOLO_MODEL_PATH.exists():
        raise SystemExit(f"[box_source_compare] Modele introuvable : {YOLO_MODEL_PATH}")
    yolo = YOLO(str(YOLO_MODEL_PATH))

    vlm_iou = load_vlm_iou(PROVENANCE_CSV)
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    rows = []
    for stem in stems:
        img_path = RAW_IMAGES / f"{stem}.png"
        mask_path = RAW_MASKS / f"{stem}.png"
        if not img_path.exists() or not mask_path.exists():
            print(f"[box_source_compare] {stem} : image/masque manuel introuvable, ignore")
            continue

        manual_bin = (np.array(Image.open(mask_path).convert("L")) > 127)

        boxes, confs = yolo_boxes_for_image(yolo, img_path, conf=yolo_conf)
        if not boxes:
            print(f"[box_source_compare] {stem} : YOLO n'a detecte aucune main (conf>={yolo_conf})")
            rows.append({"stem": stem, "iou_vlm": vlm_iou.get(stem),
                        "iou_yolo": None, "n_boxes_yolo": 0, "yolo_conf_min": None})
            continue

        out_path = OUT_DIR / f"{stem}_yolo_premask.png"
        ok, sam_score = _infer_union(generate_part_mask, img_path, out_path, boxes,
                                     threshold=0.5, infer_kwargs={"part": "hand"})
        if not ok:
            print(f"[box_source_compare] {stem} : inference SAM echouee sur boite(s) YOLO")
            rows.append({"stem": stem, "iou_vlm": vlm_iou.get(stem),
                        "iou_yolo": None, "n_boxes_yolo": len(boxes), "yolo_conf_min": min(confs)})
            continue

        yolo_bin = (np.array(Image.open(out_path).convert("L")) > 127)
        iou_yolo = _iou(yolo_bin, manual_bin)

        with Image.open(img_path) as src:
            qc = build_qc_image(src, boxes, yolo_bin.astype(np.uint8),
                               f"YOLO hand_yolov9c conf>={yolo_conf} n={len(boxes)}")
        qc.save(OUT_DIR / f"{stem}_compare.png")

        iou_v = vlm_iou.get(stem)
        rows.append({"stem": stem, "iou_vlm": iou_v, "iou_yolo": iou_yolo,
                    "n_boxes_yolo": len(boxes), "yolo_conf_min": round(min(confs), 3)})
        v_txt = f"{iou_v:.3f}" if iou_v is not None else "?"
        print(f"[box_source_compare] {stem} : IoU_VLM={v_txt}  IoU_YOLO={iou_yolo:.3f}  "
              f"(n_boxes={len(boxes)}, conf_min={min(confs):.3f}, SAM_score={sam_score:.3f})")

    print(f"\n[box_source_compare] {'stem':<20} {'IoU_VLM':>8} {'IoU_YOLO':>9} {'delta':>7} {'n_boxes':>8}")
    print("-" * 60)
    for r in rows:
        v = r["iou_vlm"]
        y = r["iou_yolo"]
        v_txt = f"{v:.3f}" if v is not None else "?"
        y_txt = f"{y:.3f}" if y is not None else "?"
        d_txt = f"{y - v:+.3f}" if (v is not None and y is not None) else "?"
        print(f"[box_source_compare] {r['stem']:<20} {v_txt:>8} {y_txt:>9} {d_txt:>7} {r['n_boxes_yolo']:>8}")

    print(f"\n[box_source_compare] QC visuelle -> {OUT_DIR}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="HandSegNet -- compare boite VLM (deja mesuree) vs YOLO hand_yolov9c pour l'inference SAM"
    )
    parser.add_argument("--stems", default=None,
                        help="Stems separes par des virgules (ex: 00138,00095) -- defaut : jeu de cas prevu (2 echecs VLM + 4 succes VLM)")
    parser.add_argument("--yolo-conf", type=float, default=0.25,
                        help="Seuil de confiance YOLO (defaut 0.25, meme ordre de grandeur que le defaut ultralytics)")
    args = parser.parse_args()

    if args.stems:
        stems = [f"handsegnet_{s.strip().zfill(5)}" if s.strip().isdigit() else s.strip()
                for s in args.stems.split(",")]
    else:
        stems = DEFAULT_STEMS

    run(stems, args.yolo_conf)

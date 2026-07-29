# ██████╗ ██╗   ██╗██████╗ ██████╗ ██╗      ██████╗ ██████╗ ██████╗
# ██╔═══██╗██║   ██║╚════██╗██╔══██╗██║     ██╔═══██╗██╔══██╗██╔══██╗
# ██║   ██║██║   ██║ █████╔╝██████╔╝██║     ██║   ██║██████╔╝██║  ██║
# ██║   ██║╚██╗ ██╔╝ ╚═══██╗██╔══██╗██║     ██║   ██║██╔══██╗██║  ██║
# ╚██████╔╝ ╚████╔╝ ██████╔╝██║  ██║███████╗╚██████╔╝██║  ██║██████╔╝
# ╚═════╝   ╚═══╝  ╚═════╝ ╚═╝  ╚═╝╚══════╝ ╚═════╝ ╚═╝  ╚═╝╚═════╝
# Ov3rLoRd -- pipeline de production anime autonome (ComfyUI)
# https://github.com/Ov3rLoRd-MLEngineer
#
# _hand_box.py — HandSegNet (Ov3rLoRd Pipeline)
# Dérive la/les bbox main(s) (x, y, w, h) d'une image via YOLO hand_yolov9c
# (Bingsu/adetailer, déjà présent localement dans
# ComfyUI/models/ultralytics/bbox/) -- factorisé pour être branché en
# primary_box_fn dans agents.segnet_premask.run_batch, à la place du
# grounding VLM qui échoue régulièrement sur les scènes multi-mains
# (cf. box_source_compare.py, rapport du 2026-07-29 : +0.854 et +0.435 IoU
# sur les échecs VLM, régression négligeable sur les bons cas).
#
# Même convention que box_source_compare.py (marge px, conversion xyxy->xywh)
# pour reproduire dans le pipeline réel les résultats du script de test isolé.
# Retourne None si aucune main détectée (seuil de confiance non atteint) :
# run_batch retombe alors sur le fallback grounding VLM existant.

import os
os.environ.setdefault("CUDA_VISIBLE_DEVICES", "1")  # GPU1 (5060 Ti) -- GPU0
# (5080) réservée à d'autres sessions en cours, cf. règles GPU CLAUDE.md ;
# même convention que handsegnet/annotate.py et prototype_circle_sam*.py.

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))
import config  # noqa: E402,F401 -- non utilisé directement, cohérent avec les autres modules du projet

YOLO_MODEL_PATH = Path(r"D:\Ov3rLoRd AI\ComfyUI\models\ultralytics\bbox\hand_yolov9c.pt")
DEFAULT_CONF = 0.25       # même défaut que box_source_compare.py
DEFAULT_MARGIN_PX = 20    # même marge que agents.vlm_grounding.DEFAULT_MARGIN

_yolo_model = None


def _get_model():
    """Charge le modèle YOLO une seule fois par process (appelé une fois par
    image dans run_batch -- éviter un rechargement disque à chaque appel)."""
    global _yolo_model
    if _yolo_model is None:
        from ultralytics import YOLO
        if not YOLO_MODEL_PATH.exists():
            raise FileNotFoundError(f"[hand_box] Modèle YOLO introuvable : {YOLO_MODEL_PATH}")
        _yolo_model = YOLO(str(YOLO_MODEL_PATH))
    return _yolo_model


def hand_box_for_image(
    image_path: Path,
    conf: float = DEFAULT_CONF,
    margin_px: int = DEFAULT_MARGIN_PX,
) -> list[tuple[int, int, int, int]] | None:
    """
    Retourne la liste des bbox main (x, y, w, h) en pixels absolus détectées
    par YOLO hand_yolov9c sur `image_path` (une par main -- multi-instance),
    ou None si aucune détection au-dessus de `conf` (déclenche le fallback
    grounding VLM dans agents.segnet_premask.run_batch).
    """
    image_path = Path(image_path)
    try:
        model = _get_model()
        results = model.predict(str(image_path), conf=conf, verbose=False)
    except Exception as e:
        print(f"[hand_box] Échec YOLO sur {image_path.name} : {e}")
        return None

    if not results or results[0].boxes is None or len(results[0].boxes) == 0:
        return None

    boxes: list[tuple[int, int, int, int]] = []
    for x1, y1, x2, y2 in results[0].boxes.xyxy.tolist():
        boxes.append((
            int(x1 - margin_px), int(y1 - margin_px),
            int((x2 - x1) + 2 * margin_px), int((y2 - y1) + 2 * margin_px),
        ))
    return boxes


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Test manuel de hand_box_for_image sur une image")
    parser.add_argument("image", help="Chemin de l'image")
    parser.add_argument("--conf", type=float, default=DEFAULT_CONF)
    args = parser.parse_args()
    print(hand_box_for_image(Path(args.image), conf=args.conf))

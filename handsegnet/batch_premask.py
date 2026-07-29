# batch_premask.py — HandSegNet (Ov3rLoRd Pipeline)
# Génère en batch les pré-masques mono-classe "hand" pour pré-remplir
# l'annotation. Bbox : YOLO spécialisé mains (hand_yolov9c, _hand_box.py) en
# source principale, multi-instance (une bbox par main détectée) -- intégré
# le 2026-07-29 suite au rapport box_source_compare.py (+0.854/+0.435 IoU sur
# les échecs VLM). FALLBACK grounding VLM (agents.vlm_grounding, requête
# neutre, multi-instance) si YOLO ne détecte rien -- même pattern que le
# fallback validé sur footsegnet 2026-07-14.
#
# La logique batch (sélection, provenance, closing des trous, QC, rapports)
# est factorisée dans agents\segnet_premask.py, partagée par les 4 *segnet.
#
# Écrit UNIQUEMENT dans dataset\premasks\ (<stem>.png, mêmes noms que
# masks_raw\) -- jamais dans masks_raw\. Convention : BLANC (255) = objet.
#
# Usage :
#   py -3.12 batch_premask.py
#   py -3.12 batch_premask.py --limit 5
#   py -3.12 batch_premask.py --clean --skip-existing

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))
import config
PROJECT_ROOT = config.HANDSEGNET_ROOT
REPO_ROOT = config.OVERLORD_ROOT
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from infer import generate_part_mask                       # noqa: E402
from _hand_box import hand_box_for_image                   # noqa: E402
from agents.segnet_premask import (                        # noqa: E402
    PremaskCategory, run_batch, make_cli_parser,
)

# Objet de grounding neutre, aligné sur la catégorie unique d'annotation
# (id 1 "hand", cf. annotate.py/build_coco.py). Pas de couleur dans la
# requête (biais de complaisance).
DEFAULT_OBJECT = "the character's hands"


if __name__ == "__main__":
    parser = make_cli_parser("HandSegNet", "mains")
    parser.add_argument("--grounding-object", default=DEFAULT_OBJECT,
                        help=f"Requête de grounding VLM (défaut: \"{DEFAULT_OBJECT}\")")
    args = parser.parse_args()

    categories = [PremaskCategory(
        name=None,                       # mono-classe : premasks\<stem>.png
        grounding_object=args.grounding_object,
        primary_box_fn=hand_box_for_image,
        primary_box_source="yolo_hand",
        infer_kwargs={"part": "hand"},
        keep_components=2,               # deux mains attendues
    )]

    run_batch(
        "handsegnet", PROJECT_ROOT / "dataset", generate_part_mask,
        categories,
        limit=args.limit, only=args.only, clean=args.clean,
        skip_existing=args.skip_existing, force=args.force,
        from_failures=args.from_failures, threshold=args.threshold,
        grounding_margin=args.grounding_margin, no_fallback=args.no_fallback,
    )

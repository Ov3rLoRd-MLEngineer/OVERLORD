# ██████╗ ██╗   ██╗██████╗ ██████╗ ██╗      ██████╗ ██████╗ ██████╗
# ██╔═══██╗██║   ██║╚════██╗██╔══██╗██║     ██╔═══██╗██╔══██╗██╔══██╗
# ██║   ██║██║   ██║ █████╔╝██████╔╝██║     ██║   ██║██████╔╝██║  ██║
# ██║   ██║╚██╗ ██╔╝ ╚═══██╗██╔══██╗██║     ██║   ██║██╔══██╗██║  ██║
# ╚██████╔╝ ╚████╔╝ ██████╔╝██║  ██║███████╗╚██████╔╝██║  ██║██████╔╝
# ╚═════╝   ╚═══╝  ╚═════╝ ╚═╝  ╚═╝╚══════╝ ╚═════╝ ╚═╝  ╚═╝╚═════╝
# Ov3rLoRd -- pipeline de production anime autonome (ComfyUI)
# https://github.com/Ov3rLoRd-MLEngineer
#
# batch_premask.py — FootSegNet (Ov3rLoRd Pipeline)
# Génère en batch les pré-masques (bbox pied -> SAM + raffinement de infer.py)
# pour pré-remplir annotate.py. Bbox : pose DWPose (foot_box_for_image) en
# source principale, avec FALLBACK grounding VLM (agents.vlm_grounding,
# requête neutre "the character's shoes or feet") quand la pose échoue —
# intégration validée le 2026-07-14 sur les 8 images en échec DWPose.
#
# La logique batch (sélection, provenance, closing des trous, QC, rapports)
# est factorisée dans agents\segnet_premask.py, partagée avec hand/face/body.
#
# Écrit UNIQUEMENT dans dataset\premasks\ -- jamais dans dataset\masks_raw\.
# Convention : BLANC (255) = pied/chaussure, NOIR (0) = fond (convention ML).
#
# Usage :
#   py -3.12 batch_premask.py
#   py -3.12 batch_premask.py --clean --limit 20
#   py -3.12 batch_premask.py --from-failures --force        (validation IoU)
#   py -3.12 batch_premask.py --no-fallback                  (DWPose seul, historique)

import sys
from pathlib import Path

FOOTSEGNET_ROOT = Path(r"D:\OVERLORD\footsegnet")
REPO_ROOT = Path(r"D:\OVERLORD")
for _p in (str(FOOTSEGNET_ROOT), str(REPO_ROOT)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from infer import generate_foot_mask                       # noqa: E402
from _pose_box import foot_box_for_image                   # noqa: E402
from agents.segnet_premask import (                        # noqa: E402
    PremaskCategory, run_batch, make_cli_parser,
)

DEFAULT_OBJECT = "the character's shoes or feet"


def _foot_box(image_path: Path):
    # person_index="largest" : cible la personne à la plus grande boîte
    # englobante (sujet principal), pas people[0] qui peut être un personnage
    # secondaire minuscule (même choix que run_dilation_test.py).
    return foot_box_for_image(image_path, person_index="largest")


if __name__ == "__main__":
    parser = make_cli_parser("FootSegNet", "pieds/chaussures")
    parser.add_argument("--refine", action="store_true", default=True,
                        help="Raffinement itératif de infer.py (défaut: activé)")
    parser.add_argument("--no-refine", dest="refine", action="store_false")
    parser.add_argument("--grounding-object", default=DEFAULT_OBJECT,
                        help=f"Requête de grounding VLM (défaut: \"{DEFAULT_OBJECT}\")")
    args = parser.parse_args()

    categories = [PremaskCategory(
        name=None,                       # mono-classe : premasks\<stem>.png
        grounding_object=args.grounding_object,
        primary_box_fn=_foot_box,
        infer_kwargs={"refine": args.refine},
    )]

    run_batch(
        "footsegnet", FOOTSEGNET_ROOT / "dataset", generate_foot_mask,
        categories,
        limit=args.limit, only=args.only, clean=args.clean,
        skip_existing=args.skip_existing, force=args.force,
        from_failures=args.from_failures, threshold=args.threshold,
        grounding_margin=args.grounding_margin, no_fallback=args.no_fallback,
    )

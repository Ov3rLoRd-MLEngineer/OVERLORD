# batch_premask.py — FaceSegNet (Ov3rLoRd Pipeline)
# Génère en batch les pré-masques multi-classes (eyes/mouth/nose/eyebrows/
# hairline) pour pré-remplir l'annotation. Pas de helper pose visage dans le
# repo : la bbox vient du grounding VLM (agents.vlm_grounding, requête neutre
# par catégorie) — même pattern que le fallback validé sur footsegnet
# 2026-07-14.
#
# La logique batch (sélection, provenance, closing des trous, QC, rapports)
# est factorisée dans agents\segnet_premask.py, partagée par les 4 *segnet.
#
# Écrit UNIQUEMENT dans dataset\premasks\ (<stem>__<cat>.png, mêmes noms que
# masks_raw\) -- jamais dans masks_raw\. Convention : BLANC (255) = objet.
#
# Usage :
#   py -3.12 batch_premask.py
#   py -3.12 batch_premask.py --category eyes --limit 5

import sys
from pathlib import Path

PROJECT_ROOT = Path(r"D:\OVERLORD\facesegnet")
REPO_ROOT = Path(r"D:\OVERLORD")
for _p in (str(PROJECT_ROOT), str(REPO_ROOT)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from infer import generate_part_mask                       # noqa: E402
from agents.segnet_premask import (                        # noqa: E402
    PremaskCategory, run_batch, make_cli_parser,
)

# Objets de grounding neutres, alignés sur les catégories d'annotation du
# README (id 1-5). Pas de couleur dans la requête (biais de complaisance).
CATEGORIES = {
    "eyes":     ("the character's eyes", 2),
    "mouth":    ("the character's mouth", 1),
    "nose":     ("the character's nose", 1),
    "eyebrows": ("the character's eyebrows", 2),
    "hairline": ("the character's hairline (the edge between the forehead and the hair)", 1),
}


if __name__ == "__main__":
    parser = make_cli_parser("FaceSegNet", "traits du visage")
    parser.add_argument("--category", choices=sorted(CATEGORIES), default=None,
                        help="Ne traiter qu'une catégorie (défaut: toutes)")
    args = parser.parse_args()

    names = [args.category] if args.category else list(CATEGORIES)
    categories = [PremaskCategory(
        name=name,
        grounding_object=CATEGORIES[name][0],
        infer_kwargs={"part": name},
        keep_components=CATEGORIES[name][1],
    ) for name in names]

    run_batch(
        "facesegnet", PROJECT_ROOT / "dataset", generate_part_mask,
        categories,
        limit=args.limit, only=args.only, clean=args.clean,
        skip_existing=args.skip_existing, force=args.force,
        from_failures=args.from_failures, threshold=args.threshold,
        grounding_margin=args.grounding_margin, no_fallback=args.no_fallback,
    )

# ██████╗ ██╗   ██╗██████╗ ██████╗ ██╗      ██████╗ ██████╗ ██████╗
# ██╔═══██╗██║   ██║╚════██╗██╔══██╗██║     ██╔═══██╗██╔══██╗██╔══██╗
# ██║   ██║██║   ██║ █████╔╝██████╔╝██║     ██║   ██║██████╔╝██║  ██║
# ██║   ██║╚██╗ ██╔╝ ╚═══██╗██╔══██╗██║     ██║   ██║██╔══██╗██║  ██║
# ╚██████╔╝ ╚████╔╝ ██████╔╝██║  ██║███████╗╚██████╔╝██║  ██║██████╔╝
# ╚═════╝   ╚═══╝  ╚═════╝ ╚═╝  ╚═╝╚══════╝ ╚═════╝ ╚═╝  ╚═╝╚═════╝
# Ov3rLoRd -- pipeline de production anime autonome (ComfyUI)
# https://github.com/Ov3rLoRd-MLEngineer
#
# route_by_sam_confidence.py — routage generique multi-SegNet par confiance SAM
#
# Generalise footsegnet/controlnet/route_by_sam_confidence.py (calibre a 0.20
# sur FootSegNet, cf. ce fichier) aux 3 autres modules. AUCUN seuil unique
# partage entre modules : la morphologie du masque (pied/corps/visage/main)
# change trop la distribution de score pour transferer un seuil par reflexe
# (cf. instructions de session du 2026-07-28 -- inspection visuelle
# obligatoire avant de fixer un seuil).
#
# Seuils calibres a ce jour :
#   - footsegnet : 0.20 (calibration existante, cf. footsegnet/controlnet/
#     route_by_sam_confidence.py -- pas rejoue ici, ce script ne fait que
#     rendre le MECANISME disponible pour footsegnet aussi si besoin futur ;
#     ne PAS lancer --module footsegnet sans relire d'abord route_manual_review.txt/
#     route_auto_sort.txt existants, ce script les ecraserait).
#   - handsegnet : 0.62 -- calibre le 2026-07-28 sur inspection visuelle de 7
#     images couvrant les scores 0.304 a 0.746 (les 71/240 lignes OK du
#     dataset avec un sam_score exploitable). Constat : le signal est REEL
#     mais BEAUCOUP plus bruite que sur FootSegNet -- non monotone dans
#     l'echantillon inspecte (handsegnet_00102, score 0.621, masque propre ;
#     handsegnet_00123, score 0.746, masque bruite/dechiquete). 0.62 attrape
#     les 4 pires cas confirmes visuellement mauvais (0.304, 0.482, 0.571,
#     0.575 -- masques meconnaissables/troues/tachetes) sans sur-flaguer le
#     seul cas propre observe sous 0.65 (0.621). A traiter comme une
#     priorisation de revue ("ouvrir ces images en premier"), PAS comme un
#     gate de confiance fiable comme sur FootSegNet -- la couverture est
#     aussi plus faible (71/240 lignes OK ont un score, ~30%, contre ~62%
#     sur FootSegNet) car la majorite des lignes handsegnet proviennent de
#     qwenvl_grounding_multi(2) qui ne journalise pas toujours sam_score.
#   - bodysegnet, facesegnet : NON CALIBRABLE au 2026-07-28 -- _provenance.csv
#     n'a meme pas de colonne sam_score (4-5 lignes issues d'un test isole sur
#     une seule image, aucune annotation manuelle). Le script le detecte tout
#     seul (load_sam_scores renvoie un dict vide) et refuse de router plutot
#     que d'inventer un seuil sur du vide.
#
# Fragmentation (scipy.ndimage.label, cf. footsegnet/controlnet/quality_sort.py) :
# PAS generalisee ici. Verifie visuellement sur HandSegNet (2026-07-28,
# handsegnet_00253/00222 : 2 composantes ~50/50, masques parfaitement propres
# -- deux mains distinctes dans le cadre, pas un defaut) que le ratio
# minoritaire utilise pour FootSegNet (mesure sur une silhouette compacte
# unique) n'a AUCUN pouvoir discriminant sur les mains : une main correctement
# segmentee produit couramment plusieurs composantes "significatives"
# legitimes (doigts ecartes, deux mains dans le cadre), alors qu'un vrai echec
# SAM (handsegnet_00289, 200 composantes) partage la meme signature que ces
# cas valides sur le ratio minoritaire seul. Necessiterait un vrai signal de
# forme (pas juste composantes connexes) pour etre utile sur les mains --
# hors perimetre de cette session.
#
# Usage :
#   py -3.12 agents/route_by_sam_confidence.py --module handsegnet
#   py -3.12 agents/route_by_sam_confidence.py --module handsegnet --threshold 0.55
#   py -3.12 agents/route_by_sam_confidence.py --module bodysegnet   # refuse proprement

import argparse
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))
import config
from agents.segnet_premask import load_sam_scores   # noqa: E402

MODULE_ROOTS = {
    "footsegnet": config.FOOTSEGNET_ROOT,
    "handsegnet": config.HANDSEGNET_ROOT,
    "bodysegnet": config.BODYSEGNET_ROOT,
    "facesegnet": config.FACESEGNET_ROOT,
}

DEFAULT_THRESHOLDS = {
    "footsegnet": 0.20,
    "handsegnet": 0.62,
    "bodysegnet": None,
    "facesegnet": None,
}


def main(module: str, threshold: float | None) -> None:
    premasks_dir = MODULE_ROOTS[module] / "dataset" / "premasks"
    scores = load_sam_scores(premasks_dir)

    if not scores:
        print(f"[route_by_sam_confidence] {module} : aucun score SAM exploitable dans "
              f"{premasks_dir / '_provenance.csv'} -- dataset trop jeune (pas de colonne "
              f"sam_score, ou aucune ligne OK avec un score renseigne). Rien a router -- "
              f"relancer batch_premask.py a plus grande echelle d'abord, puis recalibrer "
              f"un seuil sur un echantillon inspecte visuellement (cf. commentaire de tete "
              f"pour la methode suivie sur handsegnet).")
        return

    if threshold is None:
        threshold = DEFAULT_THRESHOLDS.get(module)
        if threshold is None:
            print(f"[route_by_sam_confidence] {module} : {len(scores)} score(s) SAM "
                  f"disponible(s) mais pas encore de seuil calibre pour ce module -- "
                  f"passe --threshold explicitement pour forcer un essai, ou inspecte "
                  f"visuellement un echantillon avant de fixer une valeur par defaut.")
            return

    manual_review, auto_sort = [], []
    for stem, score in scores.items():
        (manual_review if score < threshold else auto_sort).append((score, stem))
    manual_review.sort(key=lambda x: x[0])
    auto_sort.sort(key=lambda x: x[0])

    manual_path = premasks_dir / "route_manual_review.txt"
    auto_path = premasks_dir / "route_auto_sort.txt"
    manual_path.write_text(
        "".join(f"{stem}\n" for _, stem in manual_review), encoding="utf-8")
    auto_path.write_text(
        "".join(f"{stem}\n" for _, stem in auto_sort), encoding="utf-8")

    print(f"[route_by_sam_confidence] {module} -- seuil={threshold}  "
          f"scores exploitables={len(scores)}")
    print(f"  verification manuelle (score < {threshold}) : {len(manual_review)}")
    print(f"  tri automatique       (score >= {threshold}) : {len(auto_sort)}")
    print(f"  -> {manual_path}")
    print(f"  -> {auto_path}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Route les images d'un SegNet en verification manuelle / tri "
                     "automatique selon leur score SAM natif (seuil calibre par module -- "
                     "cf. commentaire de tete du fichier pour la justification de chacun)."
    )
    parser.add_argument("--module", required=True, choices=sorted(MODULE_ROOTS),
                         help="Module SegNet a router")
    parser.add_argument("--threshold", type=float, default=None,
                         help="Force un seuil (sinon utilise le seuil calibre du module, "
                              "ou refuse si aucun n'est encore calibre)")
    args = parser.parse_args()
    main(args.module, args.threshold)

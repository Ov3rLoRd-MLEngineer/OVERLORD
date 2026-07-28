# ██████╗ ██╗   ██╗██████╗ ██████╗ ██╗      ██████╗ ██████╗ ██████╗
# ██╔═══██╗██║   ██║╚════██╗██╔══██╗██║     ██╔═══██╗██╔══██╗██╔══██╗
# ██║   ██║██║   ██║ █████╔╝██████╔╝██║     ██║   ██║██████╔╝██║  ██║
# ██║   ██║╚██╗ ██╔╝ ╚═══██╗██╔══██╗██║     ██║   ██║██╔══██╗██║  ██║
# ╚██████╔╝ ╚████╔╝ ██████╔╝██║  ██║███████╗╚██████╔╝██║  ██║██████╔╝
# ╚═════╝   ╚═══╝  ╚═════╝ ╚═╝  ╚═╝╚══════╝ ╚═════╝ ╚═╝  ╚═╝╚═════╝
# Ov3rLoRd -- pipeline de production anime autonome (ComfyUI)
# https://github.com/Ov3rLoRd-MLEngineer
#
# prototype_circle_sam_multi.py — HandSegNet
#
# Suite de PR #23 (prototype_circle_sam.py) : "un cercle par main, detecte
# automatiquement via VLM" au lieu d'un cercle unique simule depuis la bbox
# de provenance (DWPose/grounding englobante). PR #23 a documente un
# resultat ambigu sur handsegnet_00123 (mains proches/chevauchement) :
# aucune des 3 strategies testees (center / contour / center+box) n'isolait
# proprement les DEUX mains avec un seul cercle -- limite structurelle
# identifiee en fin de session ("un humain dessinerait plutot deux cercles
# distincts"). Cette session teste exactement cette piste.
#
# RIEN REINVENTE -- reutilise :
#   - agents/vlm_grounding.py::grounding_boxes() : deja en prod pour le
#     grounding multi-instance des premasques (handsegnet/batch_premask.py
#     l'utilise deja avec la MEME requete "the character's hands" -- une
#     bbox par main detectee, avec verification anti-boite-fantome quand
#     plusieurs boites sont retournees). Aucune nouvelle logique VLM.
#   - prototype_circle_sam.py : get_predictor(), _prepare_rgb(),
#     bbox_to_circle(), circle_to_points(), circle_to_box(), run_sam_circle(),
#     iou(). Importe directement, rien duplique.
#   - La strategie "center+box" : SEULE des 3 testees en PR #23 a produire un
#     resultat exploitable (prompt par points seul deborde systematiquement
#     sur tout objet connexe salient sur SAM de base, cf. rapport PR #23).
#     Les strategies "center" et "contour" seules ne sont pas reconduites ici.
#
# CE QUI CHANGE : au lieu d'un cercle unique derive de la bbox englobante des
# deux mains (PR #23), un cercle PAR main detectee par le VLM -- chaque main
# recoit son propre appel SAM independant (predictor.predict() avec son
# propre point + sa propre box), les masques sont fusionnes par union
# (meme logique que agents/segnet_premask.py::_infer_union() en mode
# multi-instance bbox).
#
# LIMITE CONNUE, NON CORRIGEE ICI (documentee, pas traitee) : si le VLM ne
# detecte qu'UNE main sur une image qui en montre deux (sous-detection
# grounding multi-instance), un seul cercle est derive et le probleme de
# PR #23 se reproduit tel quel sur cette image -- ce prototype ne fait rien
# de plus que ce que grounding_boxes() fait deja nativement (verify_crop
# rejette les boites fantomes EN TROP, mais rien ne compense une boite
# manquante). Fiabilite du grounding multi-instance deja suivie separement
# (10 pires cas d'IoU deja documentes sur le fallback grounding footsegnet/
# handsegnet, cf. rapport de session dedie) -- hors perimetre ici.
#
# Usage :
#   py -3.12 handsegnet/prototype_circle_sam_multi.py --stems handsegnet_00123,handsegnet_00137
#   py -3.12 handsegnet/prototype_circle_sam_multi.py   (jeu de test par defaut)

import argparse
import os
import sys
import time
from pathlib import Path

# GPU 1 (RTX 5060 Ti) uniquement -- ne jamais toucher a la RTX 5080 (GPU 0).
# Fixe AVANT l'import de torch (repris tel quel de prototype_circle_sam.py).
os.environ.setdefault("CUDA_VISIBLE_DEVICES", "1")

import numpy as np  # noqa: E402
from PIL import Image  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))
import config  # noqa: E402

from agents.vlm_grounding import grounding_boxes  # noqa: E402

# Script cote-a-cote dans handsegnet/ : le repertoire du script est deja en
# tete de sys.path a l'execution directe (py -3.12 handsegnet/xxx.py) --
# import module a module, rien duplique.
from prototype_circle_sam import (  # noqa: E402
    get_predictor, _prepare_rgb, bbox_to_circle, circle_to_points,
    circle_to_box, run_sam_circle, iou, RAW_DIR, MASKS_RAW_DIR,
)

OUT_DIR = Path(__file__).resolve().parent / "prototype_circle_sam_multi_output"

# Requete de grounding : identique a handsegnet/batch_premask.py::DEFAULT_OBJECT
# (deja en prod) -- ne pas diverger, une requete differente changerait le
# comportement mesure ici par rapport a ce qui tourne deja en batch premask.
GROUNDING_OBJECT = "the character's hands"
GROUNDING_MARGIN = 20   # vlm_grounding.DEFAULT_MARGIN, meme valeur que segnet_premask.py

DEFAULT_TEST_STEMS = [
    "handsegnet_00123",   # cas cible PR #23 : mains proches/chevauchement, pas de masque manuel
    "handsegnet_00137",   # masque manuel ; pire score SAM natif historique (0.304)
    "handsegnet_00000",   # masque manuel ; bbox haute/etroite
    "handsegnet_00002",   # masque manuel ; bbox large/basse
    "handsegnet_00004",   # masque manuel ; bbox large
    "handsegnet_00010",   # masque manuel ; candidat non teste en PR #23 (screening 1 vs 2 mains)
    "handsegnet_00021",   # masque manuel ; candidat non teste en PR #23 (screening 1 vs 2 mains)
]


def detect_hand_centers(image_path: Path, margin_px: int = GROUNDING_MARGIN
                        ) -> tuple[list[tuple[float, float, float]], int, float]:
    """
    Detecte les mains visibles via grounding VLM multi-instance
    (agents.vlm_grounding.grounding_boxes -- meme appel que
    handsegnet/batch_premask.py en production).

    Retourne (cercles, n_mains, temps_vlm_s) :
      - cercles  : liste de (cx, cy, radius), un par bbox detectee, derive
                   par bbox_to_circle() (rayon calibre sur la taille de la
                   bbox VLM disponible -- pas de valeur par defaut necessaire,
                   grounding_boxes() ne retourne que des bbox valides ou rien)
      - n_mains  : nombre d'instances trouvees, explicite : 0 (rien detecte),
                   1, ou 2+
      - temps_vlm_s : duree de l'appel grounding (inclut le chargement modele
                      au tout premier appel, ~11s, cf. en-tete vlm_grounding.py)
    """
    t0 = time.time()
    boxes = grounding_boxes(image_path, GROUNDING_OBJECT, margin_px=margin_px)
    t_vlm = time.time() - t0
    if not boxes:
        return [], 0, t_vlm
    circles = [bbox_to_circle(x, y, w, h) for (x, y, w, h) in boxes]
    return circles, len(circles), t_vlm


def run_multi_circle_sam(predictor, circles: list[tuple[float, float, float]],
                         img_shape: tuple[int, int], refine: bool = True
                        ) -> tuple[np.ndarray, list[float], float]:
    """
    Un appel SAM independant par cercle -- reutilise run_sam_circle()
    (predictor.predict() + raffinement) de prototype_circle_sam.py,
    strategie "center+box" (seule des 3 testees en PR #23 a etre exploitable).
    Fusion des masques par union (logical OR), meme principe que
    agents/segnet_premask.py::_infer_union() en mode multi-instance bbox.

    predictor.set_image() doit deja avoir ete appele par l'appelant (cout
    partage entre les cercles de la meme image).
    Retourne (masque union bool, liste des scores SAM par main, temps total
    predict() en secondes -- somme des appels, pas le set_image()).
    """
    union = np.zeros(img_shape, dtype=bool)
    scores: list[float] = []
    t_total = 0.0
    for cx, cy, radius in circles:
        point_coords, point_labels = circle_to_points(cx, cy, radius, "center")
        box = circle_to_box(cx, cy, radius)
        mask, score, elapsed = run_sam_circle(
            predictor, point_coords, point_labels, box=box, refine=refine)
        union = np.logical_or(union, mask)
        scores.append(score)
        t_total += elapsed
    return union, scores, t_total


def main(stems: list[str], refine: bool) -> None:
    OUT_DIR.mkdir(exist_ok=True)
    predictor = get_predictor()

    print(f"\n{'stem':<20} {'n_mains':>7} {'scores':<20} {'IoU vs manuel':>14} "
          f"{'t_vlm(s)':>9} {'t_img(s)':>9} {'t_sam(s)':>9} {'t_total(s)':>10}")
    for stem in stems:
        img_path = RAW_DIR / f"{stem}.png"
        if not img_path.exists():
            print(f"{stem} : image source introuvable ({img_path}) -- ignore")
            continue

        circles, n_hands, t_vlm = detect_hand_centers(img_path)

        manual_path = MASKS_RAW_DIR / f"{stem}.png"
        manual_bin = None
        if manual_path.exists():
            manual_bin = np.array(Image.open(manual_path).convert("L")) > 127
            if not manual_bin.any():
                print(f"{stem} : masque manuel PRESENT MAIS VIDE (0% blanc) -- "
                      f"IoU non significatif pour ce stem")

        if n_hands == 0:
            print(f"{stem:<20} {n_hands:>7} {'--':<20} {'n/a':>14} "
                  f"{t_vlm:>9.2f} {'--':>9} {'--':>9} {t_vlm:>10.2f}  <- aucune main detectee")
            continue

        rgb = _prepare_rgb(img_path)
        arr = np.array(rgb)

        t_img0 = time.time()
        predictor.set_image(arr)
        t_img = time.time() - t_img0

        mask, scores, t_sam = run_multi_circle_sam(
            predictor, circles, arr.shape[:2], refine=refine)

        iou_txt = "n/a (pas de GT)"
        if manual_bin is not None:
            if manual_bin.shape == mask.shape:
                v = iou(mask, manual_bin)
                iou_txt = f"{v:.3f}" if v is not None else "indefini"
            else:
                iou_txt = "shape mismatch"

        scores_txt = ",".join(f"{s:.2f}" for s in scores)
        t_total = t_vlm + t_img + t_sam
        print(f"{stem:<20} {n_hands:>7} {scores_txt:<20} {iou_txt:>14} "
              f"{t_vlm:>9.2f} {t_img:>9.2f} {t_sam:>9.2f} {t_total:>10.2f}")

        out_path = OUT_DIR / f"{stem}__multi.png"
        Image.fromarray((mask * 255).astype(np.uint8), mode="L").save(out_path)

    print(f"\n[prototype_circle_sam_multi] Masques -> {OUT_DIR}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__,
                                      formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--stems", default=None,
                        help="Stems separes par des virgules (defaut : jeu de test predefini)")
    parser.add_argument("--no-refine", action="store_true",
                        help="Desactive le raffinement (1 seule passe SAM par main)")
    args = parser.parse_args()
    stems = args.stems.split(",") if args.stems else DEFAULT_TEST_STEMS
    main(stems, refine=not args.no_refine)

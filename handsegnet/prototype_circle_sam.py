# ██████╗ ██╗   ██╗██████╗ ██████╗ ██╗      ██████╗ ██████╗ ██████╗
# ██╔═══██╗██║   ██║╚════██╗██╔══██╗██║     ██╔═══██╗██╔══██╗██╔══██╗
# ██║   ██║██║   ██║ █████╔╝██████╔╝██║     ██║   ██║██████╔╝██║  ██║
# ██║   ██║╚██╗ ██╔╝ ╚═══██╗██╔══██╗██║     ██║   ██║██╔══██╗██║  ██║
# ╚██████╔╝ ╚████╔╝ ██████╔╝██║  ██║███████╗╚██████╔╝██║  ██║██████╔╝
# ╚═════╝   ╚═══╝  ╚═════╝ ╚═╝  ╚═╝╚══════╝ ╚═════╝ ╚═╝  ╚═╝╚═════╝
# Ov3rLoRd -- pipeline de production anime autonome (ComfyUI)
# https://github.com/Ov3rLoRd-MLEngineer
#
# prototype_circle_sam.py — HandSegNet
#
# Prototype "cercle grossier -> points derives automatiquement -> SAM affine"
# comme alternative plus rapide au clic point-par-point de
# handsegnet/annotate.py::run_sam() (identique dans les 4 SegNets).
#
# RIEN REINVENTE -- reutilise exactement :
#   - Le meme checkpoint que annotate.py::get_sam_predictor() : SAM ViT-B DE
#     BASE (config.SAM_CHECKPOINT), PAS le SAM finetune HandSegNet
#     (checkpoints/handsegnet_vit_b_best.pth utilise par infer.py). Choix
#     deliberer : annotate.py sert a produire les masques manuels qui
#     ENTRAINENT le finetune -- utiliser le modele deja finetune pour
#     accelerer sa propre annotation de verite terrain serait circulaire
#     (biais de confirmation). Comparaison equitable avec "l'annotation
#     actuelle" (annotate.py) : meme modele.
#   - Le meme appel predictor.predict(point_coords=..., point_labels=...,
#     multimask_output=True) + selection par argmax(scores) que
#     annotate.py::run_sam().
#   - Le meme mecanisme de raffinement que footsegnet/infer.py (refine=True) :
#     reinjection des logits basse resolution (mask_input) du meilleur masque
#     de la 1re passe comme point de depart de la 2e passe -- adapte ici au
#     prompt par points au lieu du prompt par box.
#
# Deux strategies de derivation cercle -> points (le cercle est defini par
# centre + rayon, la donnee la plus simple a produire au stylet) :
#   - "center"  : un seul point positif au centre du cercle
#   - "contour" : centre + N points positifs repartis sur la circonference,
#                 a 0.7*rayon (pas au rayon exact -- une silhouette de main
#                 irreguliere deborde rarement du cercle mais son contour
#                 exact ne colle pas au cercle non plus ; 0.7 est une marge
#                 de securite pour rester sur l'objet, pas sur le fond)
#
# Usage :
#   py -3.12 handsegnet/prototype_circle_sam.py --stems handsegnet_00123,handsegnet_00137
#   py -3.12 handsegnet/prototype_circle_sam.py   (jeu de test par defaut, 5 images)

import argparse
import csv
import os
import sys
import time
from pathlib import Path

# GPU 1 (RTX 5060 Ti) uniquement -- ne jamais toucher a la RTX 5080 (GPU 0).
# Fixe AVANT l'import de torch.
os.environ.setdefault("CUDA_VISIBLE_DEVICES", "1")

import numpy as np  # noqa: E402
import torch  # noqa: E402
from PIL import Image  # noqa: E402
from segment_anything import SamPredictor, sam_model_registry  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))
import config  # noqa: E402

DATASET_DIR = config.HANDSEGNET_ROOT / "dataset"
RAW_DIR = DATASET_DIR / "raw"
MASKS_RAW_DIR = DATASET_DIR / "masks_raw"
PROVENANCE_CSV = DATASET_DIR / "premasks" / "_provenance.csv"
OUT_DIR = Path(__file__).resolve().parent / "prototype_circle_sam_output"

CIRCLE_MARGIN = 1.15     # rayon = moitie de la plus grande dimension bbox * marge
CONTOUR_N_POINTS = 4     # points repartis sur la circonference (strategie "contour")
CONTOUR_RADIUS_FRACTION = 0.7   # points places a 70% du rayon, pas au bord exact

# Jeu de test par defaut : handsegnet_00123 (obligatoire -- mains proches/
# chevauchement, cas difficile identifie a deux reprises) + 4 images avec
# masque manuel (verite terrain) de formes de bbox variees, pour verifier
# l'absence de regression sur les cas plus simples.
DEFAULT_TEST_STEMS = [
    "handsegnet_00123",   # pas de masque manuel -- evaluation visuelle uniquement
    "handsegnet_00137",   # masque manuel ; pire score SAM natif historique (0.304)
    "handsegnet_00000",   # masque manuel ; bbox haute/etroite
    "handsegnet_00002",   # masque manuel ; bbox large/basse
    "handsegnet_00004",   # masque manuel ; bbox large
]


def _prepare_rgb(frame_path: Path) -> Image.Image:
    """RGBA composite sur fond blanc avant tout traitement SAM (regle projet)."""
    img_raw = Image.open(str(frame_path))
    if img_raw.mode in ("RGBA", "LA") or (
        img_raw.mode == "P" and "transparency" in img_raw.info
    ):
        bg = Image.new("RGB", img_raw.size, (255, 255, 255))
        if img_raw.mode != "RGBA":
            img_raw = img_raw.convert("RGBA")
        bg.paste(img_raw, mask=img_raw.split()[3])
        return bg
    return img_raw.convert("RGB")


def get_predictor() -> SamPredictor:
    """Meme checkpoint/chargement que annotate.py::get_sam_predictor()."""
    device = "cuda" if torch.cuda.is_available() else "cpu"
    print(f"[prototype_circle_sam] Chargement SAM ViT-B (base) sur {device}...")
    sam = sam_model_registry["vit_b"](checkpoint=str(config.SAM_CHECKPOINT))
    sam.to(device)
    print("[prototype_circle_sam] SAM pret")
    return SamPredictor(sam)


def bbox_to_circle(x: int, y: int, w: int, h: int,
                   margin: float = CIRCLE_MARGIN) -> tuple[float, float, float]:
    """Simule le cercle grossier qu'un humain dessinerait au stylet autour de
    la zone deja connue (bbox de _provenance.csv) -- pour ne pas dependre
    d'une vraie interaction stylet dans cette session. cx, cy = centre bbox ;
    rayon = moyenne geometrique sqrt(w*h)/2 (PAS max(w,h)/2 -- teste et
    rejete en session : sur une bbox multi-instance tres allongee, ex.
    740x233, max(w,h)/2 produit un cercle qui deborde largement sur le
    visage/torse au-dessus des mains, verifie visuellement. sqrt(w*h)/2
    approxime un cercle "de taille raisonnable" pour la zone, au prix d'un
    sous-dimensionnement sur les bbox tres allongees -- limite assumee :
    un humain dessinerait plutot DEUX cercles distincts pour deux mains
    ecartees, un seul cercle n'est de toute facon pas le bon outil dans ce
    cas ; cf. rapport de session pour la portee de cette approximation)."""
    cx = x + w / 2
    cy = y + h / 2
    radius = (w * h) ** 0.5 / 2 * margin
    return cx, cy, radius


def circle_to_points(cx: float, cy: float, radius: float,
                     strategy: str) -> tuple[np.ndarray, np.ndarray]:
    """Derive un set de points positifs (point_coords, point_labels, tous
    label=1) depuis un cercle (centre + rayon). Deux strategies :
      - "center"  : un seul point au centre
      - "contour" : centre + CONTOUR_N_POINTS points repartis sur le cercle
                    a CONTOUR_RADIUS_FRACTION * rayon
    """
    if strategy == "center":
        coords = [(cx, cy)]
    elif strategy == "contour":
        coords = [(cx, cy)]
        r = radius * CONTOUR_RADIUS_FRACTION
        for k in range(CONTOUR_N_POINTS):
            theta = 2 * np.pi * k / CONTOUR_N_POINTS
            coords.append((cx + r * np.cos(theta), cy + r * np.sin(theta)))
    else:
        raise ValueError(f"strategie inconnue : {strategy!r}")

    point_coords = np.array(coords, dtype=np.float32)
    point_labels = np.ones(len(coords), dtype=np.int32)
    return point_coords, point_labels


def circle_to_box(cx: float, cy: float, radius: float) -> np.ndarray:
    """Carre englobant du cercle -- SEULE donnee de "cadrage" reellement
    disponible si l'utilisateur n'a trace qu'un cercle (pas une bbox
    precise). A ne pas confondre avec une vraie bbox : c'est deliberement
    plus large qu'un rectangle ajuste, cf. resultats de session (degrade la
    qualite sur les mains tres ecartees par rapport a une bbox precise, mais
    reste la seule option fidele a "l'utilisateur n'a dessine qu'un cercle")."""
    return np.array([cx - radius, cy - radius, cx + radius, cy + radius], dtype=np.float32)


def run_sam_circle(predictor: SamPredictor, point_coords: np.ndarray,
                   point_labels: np.ndarray, box: np.ndarray | None = None,
                   refine: bool = True) -> tuple[np.ndarray, float, float]:
    """Meme appel que annotate.py::run_sam() (predict + argmax(scores)),
    avec en plus :
      - le raffinement de footsegnet/infer.py (reinjection des logits basse
        resolution comme mask_input) adapte au prompt par points ;
      - optionnellement `box` (carre englobant du cercle, cf. circle_to_box) :
        DECOUVERTE EN SESSION -- le prompt par points SEUL (sans box), sur le
        SAM de base, deborde systematiquement sur tout objet connexe salient
        (veste, torse, cou) au lieu de isoler juste la main, meme en
        inspectant les 3 candidats multimask_output et pas seulement le
        meilleur score (verifie : IoU proche de 0 sur 4/5 images testees).
        predictor.predict() accepte nativement points ET box en meme temps
        (rien a reinventer) -- ajouter la box derivee du cercle ameliore
        radicalement le resultat sur le cas cible (mains proches/
        chevauchement, cf. rapport de session) meme si elle reste imprecise
        sur des mains tres ecartees (cf. limite documentee de circle_to_box).
    predictor.set_image() doit deja avoir ete appele par l'appelant (cout
    partage entre les strategies testees sur la meme image, mesure a part).
    Retourne (masque bool, score, temps predict() en secondes)."""
    t0 = time.time()
    kwargs = {"box": box} if box is not None else {}
    masks, scores, logits = predictor.predict(
        point_coords=point_coords, point_labels=point_labels,
        multimask_output=True, **kwargs,
    )
    best_idx = int(np.argmax(scores))
    best_mask, best_score, best_logit = masks[best_idx], float(scores[best_idx]), logits[best_idx]

    if refine:
        masks2, scores2, _ = predictor.predict(
            point_coords=point_coords, point_labels=point_labels,
            mask_input=best_logit[None, :, :], multimask_output=False, **kwargs,
        )
        best_mask, best_score = masks2[0], float(scores2[0])

    elapsed = time.time() - t0
    return best_mask.astype(bool), best_score, elapsed


def iou(a: np.ndarray, b: np.ndarray) -> float | None:
    union = np.logical_or(a, b).sum()
    if union == 0:
        return None
    return float(np.logical_and(a, b).sum() / union)


def load_provenance_bbox(stem: str) -> tuple[int, int, int, int] | None:
    with open(PROVENANCE_CSV, encoding="utf-8-sig", newline="") as f:
        rows = [r for r in csv.DictReader(f) if Path(r["image"]).stem == stem]
    if not rows:
        return None
    row = rows[-1]   # derniere ligne = plus recente
    return int(row["x"]), int(row["y"]), int(row["w"]), int(row["h"])


# 3 strategies testees : les 2 demandees a l'origine (center/contour, points
# seuls) + celle decouverte en session (center+box, cf. run_sam_circle) qui
# s'est averee necessaire pour tout resultat exploitable -- gardee comme 3e
# colonne plutot que remplacer les 2 premieres, pour que la comparaison
# demandee reste visible telle quelle en plus de la decouverte.
STRATEGIES = ("center", "contour", "center+box")


def main(stems: list[str], refine: bool) -> None:
    OUT_DIR.mkdir(exist_ok=True)
    predictor = get_predictor()

    print(f"\n{'stem':<20} {'strategie':<14} {'score':>7} {'IoU vs manuel':>14} {'set_image(s)':>13} {'predict(s)':>11}")
    for stem in stems:
        img_path = RAW_DIR / f"{stem}.png"
        if not img_path.exists():
            print(f"{stem} : image source introuvable ({img_path}) -- ignore")
            continue
        bbox = load_provenance_bbox(stem)
        if bbox is None:
            print(f"{stem} : aucune bbox en provenance -- ignore")
            continue
        x, y, w, h = bbox
        cx, cy, radius = bbox_to_circle(x, y, w, h)
        circle_box = circle_to_box(cx, cy, radius)

        manual_path = MASKS_RAW_DIR / f"{stem}.png"
        manual_bin = None
        if manual_path.exists():
            manual_bin = np.array(Image.open(manual_path).convert("L")) > 127
            if not manual_bin.any():
                print(f"{stem} : masque manuel PRESENT MAIS VIDE (0% blanc) -- "
                      f"IoU non significatif pour ce stem")

        rgb = _prepare_rgb(img_path)
        arr = np.array(rgb)

        t_img0 = time.time()
        predictor.set_image(arr)
        t_img = time.time() - t_img0

        for strategy in STRATEGIES:
            point_strategy = strategy.split("+")[0]
            use_box = strategy.endswith("+box")
            point_coords, point_labels = circle_to_points(cx, cy, radius, point_strategy)
            mask, score, t_predict = run_sam_circle(
                predictor, point_coords, point_labels,
                box=circle_box if use_box else None, refine=refine)

            iou_txt = "n/a (pas de GT)"
            if manual_bin is not None:
                if manual_bin.shape == mask.shape:
                    v = iou(mask, manual_bin)
                    iou_txt = f"{v:.3f}" if v is not None else "indefini"
                else:
                    iou_txt = "shape mismatch"

            print(f"{stem:<20} {strategy:<14} {score:>7.3f} {iou_txt:>14} {t_img:>13.2f} {t_predict:>11.2f}")

            out_path = OUT_DIR / f"{stem}__{strategy}.png"
            Image.fromarray((mask * 255).astype(np.uint8), mode="L").save(out_path)

    print(f"\n[prototype_circle_sam] Masques -> {OUT_DIR}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__,
                                      formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--stems", default=None,
                        help="Stems separes par des virgules (defaut : jeu de test predefini, 5 images)")
    parser.add_argument("--no-refine", action="store_true",
                        help="Desactive le raffinement (1 seule passe SAM, comme annotate.py aujourd'hui)")
    args = parser.parse_args()
    stems = args.stems.split(",") if args.stems else DEFAULT_TEST_STEMS
    main(stems, refine=not args.no_refine)

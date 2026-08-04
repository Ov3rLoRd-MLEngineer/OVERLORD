"""
Ov3rLoRd -- cycle_detector.py V1.0

Detecte le meilleur cycle de N frames (defaut 24) a boucler dans une
sequence de squelettes DWPose, pour transformer un cycle de course court
(ex. 38 frames Mixamo) en une boucle video continue sans a-coup de pose au
raccord. Bloquant 3 identifie dans DOCS/MD/PLAN_PIPELINE_A_DEMO_30S.md --
jamais construit avant cette session.

Entree reelle disponible : PNG squelette DWPose (rendu OpenPose COCO-18,
un point + une couleur par articulation), PAS de JSON de keypoints --
DEMO/frames/skeletons_1024x1024/ ne contient que des images. Ce script
reconstruit des keypoints approximatifs directement depuis les pixels
colores de chaque PNG (palette OpenPose standard, cf. OPENPOSE_COLORS)
plutot que d'attendre un format JSON qui n'existe pas sur cette machine --
evite une dependance a un ré-export DWPose.

Critere de bouclabilite : distance L2 normalisee entre les keypoints de la
frame N et ceux de la frame N+cycle_length (candidate de raccord), moyennee
uniquement sur les articulations detectees dans les DEUX frames (une
articulation absente -- ex. bras gauche manquant sur le modele "Sophie",
cf. Blocage 2 -- est ignoree plutot que de fausser le score). Normalisation
par la distance epaule-hanche (echelle du buste) apres recentrage sur le
cou, pour comparer la POSE et non la position/echelle a l'ecran.

Usage :
  py -3.12 agents/production_video/cycle_detector.py
  py -3.12 agents/production_video/cycle_detector.py --cycle-length 24 --skeletons-dir DEMO/frames/skeletons_1024x1024
  py -3.12 agents/production_video/cycle_detector.py --output DEMO/frames/cycle_best.json
"""

import argparse
import ast
import glob
import json
import os
import sys
import time

try:
    from PIL import Image
    import numpy as np
    HAS_DEPS = True
except ImportError:
    HAS_DEPS = False

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)
import config

DEFAULT_SKELETONS_DIR = os.path.join(str(config.DEMO_DIR), "frames", "skeletons_1024x1024")
DEFAULT_OUTPUT = os.path.join(str(config.DEMO_DIR), "frames", "cycle_best.json")
DEFAULT_CYCLE_LENGTH = 24

# Palette OpenPose COCO-18 standard (identique pytorch-openpose / controlnet_aux
# DWPose util.py::draw_bodypose) -- un RGB fixe par indice d'articulation.
JOINT_NAMES = [
    "Nose", "Neck", "RShoulder", "RElbow", "RWrist", "LShoulder", "LElbow",
    "LWrist", "RHip", "RKnee", "RAnkle", "LHip", "LKnee", "LAnkle",
    "REye", "LEye", "REar", "LEar",
]
OPENPOSE_COLORS = [
    (255, 0, 0), (255, 85, 0), (255, 170, 0), (255, 255, 0), (170, 255, 0),
    (85, 255, 0), (0, 255, 0), (0, 255, 85), (0, 255, 170), (0, 255, 255),
    (0, 170, 255), (0, 85, 255), (0, 0, 255), (85, 0, 255), (170, 0, 255),
    (255, 0, 255), (255, 0, 170), (255, 0, 85),
]
# Distance RGB max pour rattacher un pixel a une couleur d'articulation --
# tolere l'anti-aliasing des points/traits sans confondre deux couleurs
# voisines dans la palette (ecart mini entre couleurs adjacentes ~85).
COLOR_TOLERANCE = 40
MIN_PIXELS_FOR_JOINT = 3
MIN_COMMON_JOINTS = 5  # sous ce seuil, le score n'est pas jugé fiable


def self_validate():
    with open(__file__, encoding="utf-8") as f:
        src = f.read()
    ast.parse(src)
    print("[OK] AST validation passed")


def list_skeleton_frames(skeletons_dir):
    files = sorted(glob.glob(os.path.join(skeletons_dir, "*.png")))
    return files


def extract_keypoints(image_path):
    """Reconstruit {joint_idx: (x, y)} depuis les pixels colores du PNG squelette.

    Pour chaque couleur de la palette OpenPose, on prend le centroide des
    pixels proches (tolerance COLOR_TOLERANCE) -- une articulation absente
    de l'image (occlusion, membre manquant) donne simplement une entree
    manquante dans le dict, pas une erreur.
    """
    with Image.open(image_path) as img:
        arr = np.array(img.convert("RGB")).astype(int)

    keypoints = {}
    for idx, color in enumerate(OPENPOSE_COLORS):
        diff = arr - np.array(color)
        dist = np.sqrt((diff ** 2).sum(axis=2))
        ys, xs = np.where(dist <= COLOR_TOLERANCE)
        if len(xs) < MIN_PIXELS_FOR_JOINT:
            continue
        keypoints[idx] = (float(xs.mean()), float(ys.mean()))
    return keypoints


def normalize_keypoints(keypoints):
    """Recentre sur le cou (idx 1) et met a l'echelle par la distance
    epaule-hanche (idx 2 ou 5, idx 8 ou 11) -- rend la comparaison
    insensible a la position/echelle a l'ecran, sensible a la pose.

    Si le cou n'est pas detecte (occlusion), retombe sur la moyenne des
    epaules/hanches disponibles comme centre -- retourner les coordonnees
    brutes non recentrees dans ce cas produirait un score de distance
    aberrant vis-a-vis des autres frames normalisees (constate en pratique :
    la paire 0012->0036 sortait un score de 470 contre <1 pour toutes les
    autres, uniquement parce que 0036 n'a pas de cou detecte)."""
    torso_idx = [2, 5, 8, 11]  # RShoulder, LShoulder, RHip, LHip
    if 1 in keypoints:
        cx, cy = keypoints[1]
    else:
        available = [keypoints[i] for i in torso_idx if i in keypoints]
        if not available:
            available = list(keypoints.values())
        if not available:
            return keypoints
        cx = sum(p[0] for p in available) / len(available)
        cy = sum(p[1] for p in available) / len(available)

    scale_pairs = [(2, 8), (5, 11), (2, 11), (5, 8)]
    scale = None
    for shoulder_idx, hip_idx in scale_pairs:
        if shoulder_idx in keypoints and hip_idx in keypoints:
            sx, sy = keypoints[shoulder_idx]
            hx, hy = keypoints[hip_idx]
            d = ((sx - hx) ** 2 + (sy - hy) ** 2) ** 0.5
            if d > 1e-3:
                scale = d
                break
    if scale is None:
        scale = 1.0

    return {idx: ((x - cx) / scale, (y - cy) / scale) for idx, (x, y) in keypoints.items()}


def pose_distance(kp_a, kp_b):
    """L2 moyenne sur les articulations communes aux deux frames.
    Retourne (distance, nb_articulations_communes)."""
    common = set(kp_a.keys()) & set(kp_b.keys())
    if len(common) < MIN_COMMON_JOINTS:
        return None, len(common)
    total = 0.0
    for idx in common:
        ax, ay = kp_a[idx]
        bx, by = kp_b[idx]
        total += ((ax - bx) ** 2 + (ay - by) ** 2) ** 0.5
    return total / len(common), len(common)


def find_best_cycle(skeleton_paths, cycle_length):
    n = len(skeleton_paths)
    if n <= cycle_length:
        raise ValueError(
            f"{n} frames disponibles <= cycle_length {cycle_length} -- "
            f"aucun candidat de bouclage possible."
        )

    print(f"  Extraction keypoints sur {n} frames...")
    all_keypoints = []
    for i, path in enumerate(skeleton_paths):
        raw = extract_keypoints(path)
        norm = normalize_keypoints(raw)
        all_keypoints.append(norm)
        missing = [JOINT_NAMES[j] for j in range(18) if j not in raw]
        if missing:
            print(f"    [{i:04d}] {os.path.basename(path)} -- articulations absentes: {', '.join(missing)}")

    candidates = []
    max_start = n - cycle_length - 1
    for start in range(0, max_start + 1):
        end = start + cycle_length
        dist, common = pose_distance(all_keypoints[start], all_keypoints[end])
        candidates.append({
            "start": start,
            "end": end,
            "score": dist,
            "common_joints": common,
        })

    scored = [c for c in candidates if c["score"] is not None]
    if not scored:
        raise RuntimeError(
            "Aucun candidat n'a assez d'articulations communes "
            f"(seuil MIN_COMMON_JOINTS={MIN_COMMON_JOINTS}) -- squelettes trop degrades."
        )
    best = min(scored, key=lambda c: c["score"])
    return candidates, best


def main():
    parser = argparse.ArgumentParser(description="Ov3rLoRd Cycle Detector V1.0")
    parser.add_argument("--skeletons-dir", type=str, default=DEFAULT_SKELETONS_DIR,
                         help=f"Dossier squelettes DWPose PNG (défaut: {DEFAULT_SKELETONS_DIR})")
    parser.add_argument("--cycle-length", type=int, default=DEFAULT_CYCLE_LENGTH,
                         help=f"Longueur du cycle à boucler (défaut: {DEFAULT_CYCLE_LENGTH})")
    parser.add_argument("--output", type=str, default=DEFAULT_OUTPUT,
                         help=f"Fichier JSON de sortie (défaut: {DEFAULT_OUTPUT})")
    args = parser.parse_args()

    self_validate()

    if not HAS_DEPS:
        print("[ERR] Pillow/numpy manquant -- requis pour ce script.")
        sys.exit(1)

    print("=" * 66)
    print("  Ov3rLoRd -- Cycle Detector V1.0")
    print("=" * 66)

    skeleton_paths = list_skeleton_frames(args.skeletons_dir)
    if not skeleton_paths:
        print(f"[ERR] Aucun squelette trouvé dans {args.skeletons_dir}")
        sys.exit(1)

    print(f"  Squelettes  : {len(skeleton_paths)} ({args.skeletons_dir})")
    print(f"  Cycle       : {args.cycle_length} frames")
    print()

    candidates, best = find_best_cycle(skeleton_paths, args.cycle_length)

    print()
    print("  Candidats (start -> end : score de drift, articulations communes) :")
    for c in sorted(candidates, key=lambda c: (c["score"] is None, c["score"])):
        marker = " <== MEILLEUR" if c is best else ""
        score_str = f"{c['score']:.4f}" if c["score"] is not None else "N/A"
        print(f"    {c['start']:04d} -> {c['end']:04d}  score={score_str}  "
              f"articulations={c['common_joints']}{marker}")

    print()
    print(f"  Meilleur cycle : frames {best['start']:04d} -> {best['end']:04d}")
    print(f"  Score de bouclabilité (drift, plus bas = mieux) : {best['score']:.4f}")
    print(f"  Articulations comparées : {best['common_joints']}/18")

    result = {
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "skeletons_dir": args.skeletons_dir,
        "total_frames": len(skeleton_paths),
        "cycle_length": args.cycle_length,
        "best_start": best["start"],
        "best_end": best["end"],
        "best_score": best["score"],
        "common_joints": best["common_joints"],
        "candidates": candidates,
    }
    os.makedirs(os.path.dirname(args.output), exist_ok=True)
    with open(args.output, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)
    print(f"\n  Résultat écrit dans {args.output}")


if __name__ == "__main__":
    main()

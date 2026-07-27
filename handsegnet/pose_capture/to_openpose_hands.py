"""
Convertit la sortie de extract_hand_landmarks.py (21 landmarks MediaPipe par
main, coordonnees normalisees [0,1]) au format OpenPose deja consomme par le
pipeline (meme schema que "openpose_json" produit par DWPreprocessor dans
agents/pose_generator.py, cf. exemple reel dans
workspace/poses/*_keypoints.json) :

    [{"people": [{"pose_keypoints_2d": [...], "face_keypoints_2d": [...],
                  "hand_left_keypoints_2d": [x,y,conf]*21,
                  "hand_right_keypoints_2d": [x,y,conf]*21}],
      "canvas_width": W, "canvas_height": H}, ...]

L'ordre des 21 points MediaPipe (wrist, thumb x4, index x4, middle x4,
ring x4, pinky x4 - cf. LANDMARK_NAMES dans extract_hand_landmarks.py) est
deja celui attendu par OpenPose pour hand_*_keypoints_2d : aucun reordonnancement
necessaire, juste [x,y,z] -> [x,y,confiance] et normalise -> pixels absolus.

Ce script ne genere PAS pose_keypoints_2d/face_keypoints_2d (corps/visage
hors perimetre de extract_hand_landmarks.py) : ces deux listes sont laissees
vides. Un node ControlNet qui exploite uniquement les mains (pas le squelette
corps) peut consommer directement cette sortie ; un usage combine avec un
squelette corps necessiterait de fusionner ce JSON avec une sortie
pose_keypoints_2d issue de DWPreprocessor sur la meme frame.

ATTENTION - convention gauche/droite non verifiee (cf. LANDMARKS_FORMAT.md,
section "Limite de convention a verifier avant tournage soigne") : MediaPipe
etiquette "Left"/"Right" du point de vue "selfie" (image miroir), et il n'est
PAS confirme que cela correspond a hand_left_keypoints_2d/hand_right_keypoints_2d
d'OpenPose sur ce pipeline. Par defaut ce script fait le mapping direct
(Left -> hand_left, Right -> hand_right) ; utiliser --swap-handedness si une
verification visuelle (cf. README stereo_calib, etape 6) montre l'inverse.

Usage :
    python to_openpose_hands.py --input out_001.json --frame-index 0 \
        --out frame_0000_keypoints.json

    python to_openpose_hands.py --input out_001.json --all \
        --out-dir openpose_frames/
"""
import argparse
import json
import os
import sys

NUM_LANDMARKS = 21
_EMPTY_HAND = [0.0] * (NUM_LANDMARKS * 3)


def _hand_to_keypoints(hand, width, height):
    conf = float(hand.get("score", 1.0))
    flat = []
    for lm in hand["landmarks_image"]:
        flat.extend([lm["x"] * width, lm["y"] * height, conf])
    return flat


def frame_to_openpose(frame, width, height, swap_handedness=False):
    """Convertit une entree `frames[i]` du JSON extract_hand_landmarks.py en
    un dict OpenPose (une image). Retourne {"people": [], ...} si aucune main
    n'est detectee sur cette frame (convention OpenPose : liste vide)."""
    hands_by_side = {}
    for hand in frame["hands"]:
        side = hand["handedness"]  # "Left" / "Right"
        if side in hands_by_side:
            print(f"[to_openpose_hands] frame {frame['frame_index']}: "
                  f"plusieurs mains '{side}' detectees, seule la premiere est gardee.",
                  file=sys.stderr)
            continue
        hands_by_side[side] = hand

    if not hands_by_side:
        return {"people": [], "canvas_width": width, "canvas_height": height}

    left_key, right_key = "hand_left_keypoints_2d", "hand_right_keypoints_2d"
    if swap_handedness:
        left_key, right_key = right_key, left_key

    person = {
        "pose_keypoints_2d": [],
        "face_keypoints_2d": [],
        left_key: (_hand_to_keypoints(hands_by_side["Left"], width, height)
                   if "Left" in hands_by_side else list(_EMPTY_HAND)),
        right_key: (_hand_to_keypoints(hands_by_side["Right"], width, height)
                    if "Right" in hands_by_side else list(_EMPTY_HAND)),
    }
    return {"people": [person], "canvas_width": width, "canvas_height": height}


def convert(input_path, swap_handedness=False):
    with open(input_path, encoding="utf-8") as f:
        data = json.load(f)
    width, height = data["resolution"]
    return data, [
        frame_to_openpose(frame, width, height, swap_handedness=swap_handedness)
        for frame in data["frames"]
    ]


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__,
                                  formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--input", required=True, help="JSON produit par extract_hand_landmarks.py")
    ap.add_argument("--frame-index", type=int, default=0,
                     help="index de frame a convertir (ignore si --all)")
    ap.add_argument("--out", default="", help="fichier de sortie (mode frame unique)")
    ap.add_argument("--all", action="store_true",
                     help="convertit toutes les frames, un fichier par frame dans --out-dir")
    ap.add_argument("--out-dir", default="", help="dossier de sortie (mode --all)")
    ap.add_argument("--swap-handedness", action="store_true",
                     help="inverse hand_left/hand_right (cf. avertissement convention en tete de fichier)")
    args = ap.parse_args()

    data, openpose_frames = convert(args.input, swap_handedness=args.swap_handedness)

    if args.all:
        out_dir = args.out_dir or os.path.splitext(args.input)[0] + "_openpose"
        os.makedirs(out_dir, exist_ok=True)
        written = 0
        for frame, openpose_dict in zip(data["frames"], openpose_frames):
            out_path = os.path.join(out_dir, f"frame_{frame['frame_index']:04d}_keypoints.json")
            with open(out_path, "w", encoding="utf-8") as f:
                json.dump([openpose_dict], f, indent=2)
            written += 1
        print(f"OK - {written} fichier(s) ecrit(s) dans {out_dir}")
    else:
        if args.frame_index >= len(openpose_frames):
            print(f"frame-index {args.frame_index} hors limites "
                  f"({len(openpose_frames)} frame(s) dans {args.input}).", file=sys.stderr)
            sys.exit(1)
        out_path = args.out or (os.path.splitext(args.input)[0]
                                 + f"_frame{args.frame_index:04d}_keypoints.json")
        with open(out_path, "w", encoding="utf-8") as f:
            json.dump([openpose_frames[args.frame_index]], f, indent=2)
        print(f"OK - ecrit : {out_path}")

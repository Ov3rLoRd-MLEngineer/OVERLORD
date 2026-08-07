"""Convertit un JSON OpenPose BODY_25 (+ mains) exporte par
agents/production_video/export_skeleton_openpose.py en image de
conditionnement ControlNet (squelette dessine sur fond noir), format standard
attendu par un ControlNet OpenPose ComfyUI (meme convention couleur que
comfyui_controlnet_aux / DWPose : membres colores, points mains verts/rouges).

Usage:
    "D:\\Ov3rLoRd AI\\python_embeded\\python.exe" DEMO/draw_openpose_skeleton.py

Genere DEMO/frames/comparaison_unification_ref/piste_D_skeleton.png a partir
du frame le plus proche disponible (frame_00001.json, choisi par defaut faute
de correspondance etablie entre l'index mmd et les frames SVI de reference --
voir note dans le rapport COMPARAISON_UNIFICATION_20260806.md).
"""
import json
import os

from PIL import Image, ImageDraw

SKELETON_JSON = r"D:\OVERLORD\DEMO\frames\openpose_synthetic\mmd\miku\casual\frame_00001.json"
OUT_PNG = r"D:\OVERLORD\DEMO\frames\comparaison_unification_ref\piste_D_skeleton.png"

# Canvas : les coordonnees du JSON exporte sont deja a l'echelle de la
# keyframe SDXL d'origine (1024x1536, cf. verification empirique -- y max
# observe ~1530, coherent avec une hauteur 1536).
CANVAS_W, CANVAS_H = 1024, 1536

# BODY_25 paires d'os + couleurs BGR->RGB standard OpenPose (openpose/src
# util.py POSE_COLORS, reprises ici telles quelles).
BODY_25_PAIRS = [
    (1, 8), (1, 2), (1, 5), (2, 3), (3, 4), (5, 6), (6, 7), (8, 9), (9, 10),
    (10, 11), (8, 12), (12, 13), (13, 14), (1, 0), (0, 15), (15, 17), (0, 16),
    (16, 18), (14, 19), (19, 20), (14, 21), (11, 22), (22, 23), (11, 24),
]
BODY_25_COLORS = [
    (255, 0, 0), (255, 85, 0), (255, 170, 0), (255, 255, 0), (170, 255, 0),
    (85, 255, 0), (0, 255, 0), (0, 255, 85), (0, 255, 170), (0, 255, 255),
    (0, 170, 255), (0, 85, 255), (0, 0, 255), (85, 0, 255), (170, 0, 255),
    (255, 0, 255), (255, 0, 170), (255, 0, 85), (255, 0, 0), (255, 0, 0),
    (255, 0, 0), (0, 255, 0), (0, 255, 0), (0, 255, 0),
]

HAND_PAIRS = [
    (0, 1), (1, 2), (2, 3), (3, 4),
    (0, 5), (5, 6), (6, 7), (7, 8),
    (0, 9), (9, 10), (10, 11), (11, 12),
    (0, 13), (13, 14), (14, 15), (15, 16),
    (0, 17), (17, 18), (18, 19), (19, 20),
]


def _pts(flat):
    return [(flat[i], flat[i + 1], flat[i + 2]) for i in range(0, len(flat), 3)]


def draw_skeleton(person, canvas):
    draw = ImageDraw.Draw(canvas, "RGBA")
    body = _pts(person.get("pose_keypoints_2d", []))
    for (a, b), color in zip(BODY_25_PAIRS, BODY_25_COLORS):
        if a >= len(body) or b >= len(body):
            continue
        xa, ya, ca = body[a]
        xb, yb, cb = body[b]
        if ca <= 0 or cb <= 0:
            continue
        draw.line([(xa, ya), (xb, yb)], fill=color + (255,), width=8)
    for x, y, c in body:
        if c > 0:
            draw.ellipse([x - 6, y - 6, x + 6, y + 6], fill=(255, 255, 255, 255))

    for hand_key, base_color in (("hand_left_keypoints_2d", (0, 255, 0)),
                                  ("hand_right_keypoints_2d", (255, 0, 0))):
        hand = _pts(person.get(hand_key, []))
        for a, b in HAND_PAIRS:
            if a >= len(hand) or b >= len(hand):
                continue
            xa, ya, ca = hand[a]
            xb, yb, cb = hand[b]
            if ca <= 0 or cb <= 0:
                continue
            draw.line([(xa, ya), (xb, yb)], fill=base_color + (255,), width=3)


def main():
    with open(SKELETON_JSON, encoding="utf-8") as f:
        data = json.load(f)
    people = data.get("people", [])
    if not people:
        raise SystemExit(f"aucun 'people' dans {SKELETON_JSON}")

    canvas = Image.new("RGB", (CANVAS_W, CANVAS_H), (0, 0, 0))
    for person in people:
        draw_skeleton(person, canvas)

    os.makedirs(os.path.dirname(OUT_PNG), exist_ok=True)
    canvas.save(OUT_PNG)
    print(f"RESULT: skeleton -> {OUT_PNG} ({CANVAS_W}x{CANVAS_H}), source={SKELETON_JSON}")


if __name__ == "__main__":
    main()

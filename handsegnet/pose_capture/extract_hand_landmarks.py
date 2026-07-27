"""
Test de faisabilite minimal pour l'axe "3D comme guide de pose" (option 2 de
ADDENDUM_PISTES_FUTURES_V3_JUILLET2026.md, retenue apres l'echec du calibrage
cel-shading sur geometrie proxy - le rendu 3D sert de guide de mouvement/pose,
pas de masque pixel-exact).

Extrait, frame par frame, les 21 landmarks MediaPipe par main detectee dans une
video, et exporte en JSON sequentiel. Voir LANDMARKS_FORMAT.md pour le format
de sortie et la convention retenue.

A executer avec l'interpreteur du venv isole (mediapipe a ses propres pins
numpy/protobuf qui entrent en conflit avec le venv principal torch/segment-
anything du projet - meme logique que l'isolation Unsloth Studio) :

    "C:\\Users\\Ov3rL0rD\\.venvs\\mediapipe_handpose\\Scripts\\python.exe" ^
        extract_hand_landmarks.py --video "chemin\\vers\\clip.mp4" --out out.json

Usage minimal (ce test) :
    python extract_hand_landmarks.py --video "D:\\OVERLORD\\DEMO\\video ref\\001.mp4" ^
        --out "D:\\OVERLORD\\handsegnet\\pose_capture\\out_001.json" --preview 3
"""
import argparse
import json
import os
import sys
import time

import cv2
import mediapipe as mp
from mediapipe.tasks import python as mp_python
from mediapipe.tasks.python import vision

MODEL_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "models", "hand_landmarker.task")

# Ordre des 21 landmarks MediaPipe (convention standard, cf. LANDMARKS_FORMAT.md)
LANDMARK_NAMES = [
    "wrist",
    "thumb_cmc", "thumb_mcp", "thumb_ip", "thumb_tip",
    "index_mcp", "index_pip", "index_dip", "index_tip",
    "middle_mcp", "middle_pip", "middle_dip", "middle_tip",
    "ring_mcp", "ring_pip", "ring_dip", "ring_tip",
    "pinky_mcp", "pinky_pip", "pinky_dip", "pinky_tip",
]


def build_detector(num_hands=2, min_detection_confidence=0.5):
    base_options = mp_python.BaseOptions(model_asset_path=MODEL_PATH)
    options = vision.HandLandmarkerOptions(
        base_options=base_options,
        running_mode=vision.RunningMode.VIDEO,
        num_hands=num_hands,
        min_hand_detection_confidence=min_detection_confidence,
        min_hand_presence_confidence=min_detection_confidence,
        min_tracking_confidence=min_detection_confidence,
    )
    return vision.HandLandmarker.create_from_options(options)


def landmarks_to_list(landmark_list):
    return [{"x": lm.x, "y": lm.y, "z": lm.z} for lm in landmark_list]


def extract(video_path, out_path, preview_count=0, max_frames=None):
    if not os.path.exists(MODEL_PATH):
        raise FileNotFoundError(f"Modele HandLandmarker introuvable : {MODEL_PATH}")

    cap = cv2.VideoCapture(video_path)
    if not cap.isOpened():
        raise RuntimeError(f"Impossible d'ouvrir la video : {video_path}")

    fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
    width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))

    detector = build_detector()
    preview_dir = os.path.join(os.path.dirname(out_path), "preview")
    if preview_count:
        os.makedirs(preview_dir, exist_ok=True)

    frames_out = []
    frame_idx = 0
    hands_detected_count = 0
    t0 = time.time()

    while True:
        if max_frames is not None and frame_idx >= max_frames:
            break
        ok, frame_bgr = cap.read()
        if not ok:
            break

        frame_rgb = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2RGB)
        mp_image = mp.Image(image_format=mp.ImageFormat.SRGB, data=frame_rgb)
        timestamp_ms = int((frame_idx / fps) * 1000)

        result = detector.detect_for_video(mp_image, timestamp_ms)

        hands_this_frame = []
        for i, hand_landmarks in enumerate(result.hand_landmarks):
            handedness = result.handedness[i][0]  # top classification
            world_landmarks = result.hand_world_landmarks[i] if result.hand_world_landmarks else []
            hands_this_frame.append({
                "handedness": handedness.category_name,   # "Left" / "Right" (repere camera, cf. doc)
                "score": handedness.score,
                "landmarks_image": landmarks_to_list(hand_landmarks),          # normalises [0,1], z = profondeur relative au poignet
                "landmarks_world": landmarks_to_list(world_landmarks),          # metres, origine = poignet, mono-vue (estimee)
            })
            hands_detected_count += 1

        frames_out.append({
            "frame_index": frame_idx,
            "timestamp_ms": timestamp_ms,
            "hands": hands_this_frame,
        })

        if preview_count and frame_idx < preview_count and hands_this_frame:
            annotated = frame_bgr.copy()
            for hand in hands_this_frame:
                for lm in hand["landmarks_image"]:
                    px, py = int(lm["x"] * width), int(lm["y"] * height)
                    cv2.circle(annotated, (px, py), 4, (0, 0, 255), -1)
            cv2.imwrite(os.path.join(preview_dir, f"frame_{frame_idx:04d}.png"), annotated)

        frame_idx += 1

    cap.release()
    elapsed = time.time() - t0

    output = {
        "source_video": os.path.abspath(video_path),
        "fps": fps,
        "resolution": [width, height],
        "frame_count_total": total_frames,
        "frame_count_processed": frame_idx,
        "landmark_names": LANDMARK_NAMES,
        "frames": frames_out,
    }

    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(output, f, indent=1)

    print(f"OK - {frame_idx} frames traitees en {elapsed:.1f}s ({frame_idx/elapsed:.1f} fps), "
          f"mains detectees sur {sum(1 for fr in frames_out if fr['hands'])}/{frame_idx} frames "
          f"({hands_detected_count} detections main au total).")
    print(f"JSON ecrit : {out_path}")
    if preview_count:
        print(f"Previews annotees : {preview_dir}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--video", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--preview", type=int, default=0, help="nombre de frames a exporter avec landmarks dessines (sanity check visuel)")
    ap.add_argument("--max-frames", type=int, default=None)
    args = ap.parse_args()
    extract(args.video, args.out, preview_count=args.preview, max_frames=args.max_frames)

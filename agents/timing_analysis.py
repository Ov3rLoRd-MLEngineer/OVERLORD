"""H-002 (DOCS/HERMES) -- module de timing/decoupage plan par plan.

Approche 3 etages (voir DOCS/HERMES/OUTBOX/H-002_timing_module_v1.md) :
1. PySceneDetect pour detecter les coupures entre plans.
2. Frame-diff (moyenne des differences pixel entre frames consecutives)
   pour estimer la cadence/holds a l'interieur d'un plan.
3. QwenVL sur UNE keyframe par plan (pas de resume frame-par-frame).

Usage :
    py -3.12 agents/timing_analysis.py chemin/vers/episode.mp4
    py -3.12 agents/timing_analysis.py chemin/vers/episode.mp4 --run-vlm

Sans --run-vlm, le champ "qwenvl_description" reste vide dans le JSON de
sortie (a remplir plus tard par une passe separee) -- voir contexte du
brief H-002. Avec --run-vlm, l'appel Ollama/QwenVL reel est fait (meme
convention que agents/qc_validation/vlm_grounding.py::_call_vlm).
"""

from __future__ import annotations

import argparse
import base64
import json
import statistics
from pathlib import Path

import cv2
import numpy as np
import requests
from scenedetect import SceneManager, open_video
from scenedetect.detectors import ContentDetector

DEFAULT_QWENVL_MODEL = "qwen2.5vl:7b"
DEFAULT_OLLAMA_URL = "http://127.0.0.1:11434"
DEFAULT_VLM_TIMEOUT = 120  # s -- keyframe unique, plus leger qu'une bbox grounding

QWENVL_PROMPT = """You are describing a single keyframe from an anime episode for shot-timing analysis.
Describe in 1-2 short sentences: shot type (close-up/medium/wide/establishing), main subject and action, camera angle if notable.
Do not describe colors or art style. Be terse -- this feeds a previz spreadsheet, not a review."""


def detect_scenes(video_path: str) -> list[tuple]:
    """Retourne la liste des plans (FrameTimecode start, FrameTimecode end)."""
    video = open_video(video_path)
    scene_manager = SceneManager()
    scene_manager.add_detector(ContentDetector())
    scene_manager.detect_scenes(video)
    scene_list = scene_manager.get_scene_list()
    if not scene_list:
        # Aucune coupure detectee (video = un seul plan) -- fallback sur la duree totale.
        duration = video.duration
        scene_list = [(video.base_timecode, duration)]
    return scene_list


def frame_diff_metric(video_path: str, start_frame: int, end_frame: int) -> float:
    """Moyenne des differences pixel (niveaux de gris) entre frames consecutives du plan."""
    cap = cv2.VideoCapture(video_path)
    cap.set(cv2.CAP_PROP_POS_FRAMES, start_frame)
    diffs = []
    prev_gray = None
    for _ in range(start_frame, end_frame):
        ret, frame = cap.read()
        if not ret:
            break
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        if prev_gray is not None:
            diffs.append(float(np.mean(cv2.absdiff(gray, prev_gray))))
        prev_gray = gray
    cap.release()
    return statistics.mean(diffs) if diffs else 0.0


def extract_keyframe(video_path: str, frame_number: int, out_path: Path) -> bool:
    """Extrait la frame `frame_number` et l'ecrit dans out_path (PNG)."""
    cap = cv2.VideoCapture(video_path)
    cap.set(cv2.CAP_PROP_POS_FRAMES, frame_number)
    ret, frame = cap.read()
    cap.release()
    if not ret:
        return False
    out_path.parent.mkdir(parents=True, exist_ok=True)
    cv2.imwrite(str(out_path), frame)
    return True


def call_qwenvl_keyframe(
    image_path: Path,
    model: str = DEFAULT_QWENVL_MODEL,
    ollama_url: str = DEFAULT_OLLAMA_URL,
    timeout: int = DEFAULT_VLM_TIMEOUT,
) -> tuple[str | None, str]:
    """Appel Ollama/QwenVL reel sur une keyframe. Retourne (description, "") ou (None, raison d'erreur)."""
    image_bytes = Path(image_path).read_bytes()
    payload = {
        "model": model,
        "prompt": QWENVL_PROMPT,
        "images": [base64.b64encode(image_bytes).decode("ascii")],
        "stream": False,
    }
    try:
        r = requests.post(f"{ollama_url}/api/generate", json=payload, timeout=timeout)
        r.raise_for_status()
        return r.json().get("response", "").strip(), ""
    except Exception as e:
        return None, f"appel QwenVL echoue : {e}"


def analyze_video(video_path: str, output_dir: str, run_vlm: bool = False) -> Path:
    video_path_obj = Path(video_path)
    episode_name = video_path_obj.stem
    out_dir = Path(output_dir)
    keyframes_dir = out_dir / f"{episode_name}_keyframes"

    fps = cv2.VideoCapture(video_path).get(cv2.CAP_PROP_FPS) or 24.0

    scene_list = detect_scenes(video_path)
    plans = []
    for i, (start_tc, end_tc) in enumerate(scene_list):
        start_frame = start_tc.frame_num if hasattr(start_tc, "frame_num") else int(start_tc * fps)
        end_frame = end_tc.frame_num if hasattr(end_tc, "frame_num") else int(end_tc * fps)
        end_frame = max(end_frame, start_frame + 1)
        mid_frame = (start_frame + end_frame) // 2

        keyframe_path = keyframes_dir / f"plan_{i:04d}.png"
        extract_keyframe(video_path, mid_frame, keyframe_path)

        cadence = frame_diff_metric(video_path, start_frame, end_frame)

        plan = {
            "plan_id": i,
            "start_timecode": str(start_tc),
            "end_timecode": str(end_tc),
            "start_frame": start_frame,
            "end_frame": end_frame,
            "duration_frames": end_frame - start_frame,
            "cadence_frame_diff": round(cadence, 3),
            "keyframe_path": str(keyframe_path),
            "qwenvl_description": "",
        }

        if run_vlm:
            desc, err = call_qwenvl_keyframe(keyframe_path)
            if desc is not None:
                plan["qwenvl_description"] = desc
            else:
                plan["qwenvl_error"] = err

        plans.append(plan)

    out_dir.mkdir(parents=True, exist_ok=True)
    out_json = out_dir / f"{episode_name}_timing.json"
    with out_json.open("w", encoding="utf-8") as f:
        json.dump(
            {"video": str(video_path_obj), "fps": fps, "plan_count": len(plans), "plans": plans},
            f,
            indent=2,
            ensure_ascii=False,
        )
    return out_json


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("video", help="Chemin vers le fichier video (episode de reference)")
    parser.add_argument(
        "--output-dir",
        default="workspace/timing_analysis",
        help="Dossier de sortie (JSON + keyframes). Defaut : workspace/timing_analysis",
    )
    parser.add_argument(
        "--run-vlm",
        action="store_true",
        help="Appelle QwenVL sur chaque keyframe (1 appel/plan). Sans ce flag, qwenvl_description reste vide.",
    )
    args = parser.parse_args()

    result_path = analyze_video(args.video, args.output_dir, run_vlm=args.run_vlm)
    print(f"Timing analysis ecrite dans : {result_path}")

"""
agents/video_analyzer.py — Analyseur Vidéo pour Référence V1.70
Extrait frames, scénario et storyboard depuis une vidéo de référence.

Méthode rotoscoping assisté :
  1. Découpe la vidéo en frames (24fps ou réduit)
  2. QwenVL analyse chaque frame → description textuelle
  3. Regroupe les descriptions en shots (détection de changement de scène)
  4. Génère le scénario structuré + storyboard textuel
  5. Exporte les frames clés pour le pipeline ComfyUI

Légalité : usage à des fins d'analyse et de référence créative.
Ne pas redistribuer les frames extraites d'œuvres protégées.

Usage :
  python agents/video_analyzer.py --video ma_reference.mp4
  python agents/video_analyzer.py --video clip.mp4 --fps 4 --analyze
  python agents/video_analyzer.py --video clip.mp4 --extract-keyframes
"""

import json
import logging
import subprocess
import sys
import io
from pathlib import Path
from datetime import datetime

if hasattr(sys.stdout, 'buffer'):
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

try:
    from PIL import Image
    PIL_OK = True
except ImportError:
    PIL_OK = False

try:
    from agents.overlord_utils import fallback_llm, safe_json_parse
    UTILS_OK = True
except ImportError:
    UTILS_OK = False

try:
    from agents.context_bus import get_bus
    BUS_OK = True
except ImportError:
    BUS_OK = False

ANALYZE_DIR = Path("workspace/video_analysis")
FRAMES_DIR  = Path("workspace/video_analysis/frames")
KEYS_DIR    = Path("workspace/video_analysis/keyframes")


def extract_frames(video_path: str, fps: float = 4.0,
                   max_frames: int = 500,
                   output_dir: Path = FRAMES_DIR,
                   logger=None) -> list[Path]:
    """
    Extrait les frames d'une vidéo via ffmpeg.
    fps=4 → 4 frames/seconde = 1 frame toutes les 0.25s
    fps=1 → 1 frame/seconde (pour storyboard rapide)
    fps=24 → toutes les frames (pour LoRA dataset)
    """
    log = logger or logging.getLogger("video_analyzer")
    output_dir.mkdir(parents=True, exist_ok=True)

    video_path = Path(video_path)
    if not video_path.exists():
        log.error(f"[VIDEO] Fichier introuvable : {video_path}")
        return []

    # Obtenir la durée
    probe_cmd = [
        "ffprobe", "-v", "quiet", "-print_format", "json",
        "-show_streams", str(video_path)
    ]
    try:
        result = subprocess.run(probe_cmd, capture_output=True, text=True, timeout=30)
        info = json.loads(result.stdout)
        duration = float(info["streams"][0].get("duration", 0))
        log.info(f"[VIDEO] Durée : {duration:.1f}s | fps extraction : {fps}")
    except Exception:
        duration = 0

    # Extraire les frames
    out_pattern = str(output_dir / "frame_%05d.jpg")
    cmd = [
        "ffmpeg", "-y",
        "-i", str(video_path),
        "-vf", f"fps={fps},scale=1024:-1",
        "-q:v", "3",
        "-frames:v", str(max_frames),
        out_pattern
    ]

    log.info(f"[VIDEO] Extraction frames depuis {video_path.name}...")
    try:
        subprocess.run(cmd, capture_output=True, timeout=300, check=True)
    except subprocess.CalledProcessError as e:
        log.error(f"[VIDEO] ffmpeg erreur : {e}")
        return []
    except FileNotFoundError:
        log.error("[VIDEO] ffmpeg non trouvé — installer ffmpeg")
        return []

    frames = sorted(output_dir.glob("frame_*.jpg"))
    log.info(f"[VIDEO] {len(frames)} frames extraites")
    return frames


def detect_scene_changes(frames: list[Path],
                          threshold: float = 30.0,
                          logger=None) -> list[int]:
    """
    Détecte les changements de scène par différence de couleur entre frames.
    Retourne les indices des frames de début de nouveau shot.
    """
    log = logger or logging.getLogger("video_analyzer")

    if not PIL_OK:
        log.warning("[VIDEO] PIL absent — détection scène basique")
        # Fallback : 1 shot toutes les 10 frames
        return list(range(0, len(frames), 10))

    try:
        import numpy as np
        NP_OK = True
    except ImportError:
        NP_OK = False

    if not NP_OK:
        return list(range(0, len(frames), 10))

    import numpy as np
    shot_starts = [0]
    prev_arr = None

    for i, frame_path in enumerate(frames):
        try:
            img = Image.open(frame_path).convert("RGB").resize((128, 72))
            arr = np.array(img, dtype=float)
            if prev_arr is not None:
                diff = np.mean(np.abs(arr - prev_arr))
                if diff > threshold:
                    shot_starts.append(i)
                    log.debug(f"[VIDEO] Changement scène à frame {i} (diff={diff:.1f})")
            prev_arr = arr
        except Exception:
            pass

    log.info(f"[VIDEO] {len(shot_starts)} shots détectés")
    return shot_starts


def analyze_frame_with_llm(frame_path: Path,
                             frame_num: int,
                             total_frames: int,
                             logger=None) -> dict:
    """
    Analyse une frame avec QwenVL ou le LLM pour décrire la scène.
    Retourne une description structurée pour le storyboard.
    """
    log = logger or logging.getLogger("video_analyzer")

    if not UTILS_OK:
        return {
            "frame": frame_num,
            "description": f"Frame {frame_num}/{total_frames}",
            "shot_type": "unknown",
            "characters": [],
            "action": "",
            "background": "",
        }

    # Position dans la vidéo (contexte narratif)
    position_pct = (frame_num / max(total_frames, 1)) * 100
    if position_pct < 20:
        narrative_pos = "début de séquence (introduction)"
    elif position_pct < 80:
        narrative_pos = "milieu de séquence (développement)"
    else:
        narrative_pos = "fin de séquence (conclusion)"

    system = (
        "You are an expert anime storyboard analyst. "
        "Analyze the visual content and describe it for animation reproduction. "
        "Reply ONLY with valid JSON."
    )
    prompt = (
        f"Analyze this animation frame (frame {frame_num}/{total_frames}, "
        f"{narrative_pos}).\n\n"
        f"Describe what you would need to recreate this frame in AI image generation.\n"
        f"Reply ONLY with JSON:\n"
        "{\n"
        '  "shot_type": "wide/medium/close_up/extreme_close_up/action",\n'
        '  "characters": ["character description with appearance"],\n'
        '  "character_pose": "detailed pose description",\n'
        '  "expression": "emotional expression",\n'
        '  "background": "background description for separate BG generation",\n'
        '  "action": "what is happening",\n'
        '  "lighting": "lighting description",\n'
        '  "comfyui_prompt": "ready-to-use Booru tags for ComfyUI generation",\n'
        '  "negative_prompt": "what to avoid",\n'
        '  "duration_estimate_s": 2.0\n'
        "}"
    )

    raw = fallback_llm(prompt, system=system, max_tokens=400, logger=log)
    ok, data, _ = safe_json_parse(raw, logger=log)

    if ok and isinstance(data, dict):
        data["frame"] = frame_num
        return data

    return {
        "frame":        frame_num,
        "shot_type":    "medium",
        "characters":   [],
        "action":       f"Frame {frame_num}",
        "background":   "anime background",
        "comfyui_prompt": "masterpiece, best quality, anime",
        "negative_prompt": "bad quality, worst quality",
        "duration_estimate_s": 2.0,
    }


def extract_keyframes(frames: list[Path],
                       shot_starts: list[int],
                       output_dir: Path = KEYS_DIR,
                       logger=None) -> list[Path]:
    """
    Copie les frames de début de chaque shot vers le dossier keyframes.
    Ces frames sont les références pour le pipeline ComfyUI.
    """
    log = logger or logging.getLogger("video_analyzer")
    output_dir.mkdir(parents=True, exist_ok=True)

    keyframes = []
    for i, idx in enumerate(shot_starts):
        if idx < len(frames):
            src  = frames[idx]
            dest = output_dir / f"keyframe_{i+1:03d}_shot{idx:05d}.jpg"
            import shutil
            shutil.copy2(src, dest)
            keyframes.append(dest)

    log.info(f"[VIDEO] {len(keyframes)} keyframes exportées → {output_dir}")
    return keyframes


def generate_storyboard(shot_analyses: list[dict],
                         video_name: str = "reference") -> dict:
    """
    Génère le storyboard structuré depuis les analyses de frames.
    Format compatible avec le pipeline Ov3rLoRd.
    """
    storyboard = {
        "title":       f"Storyboard — {video_name}",
        "source":      video_name,
        "method":      "video_analysis_rotoscoping",
        "generated":   datetime.now().isoformat(),
        "total_shots": len(shot_analyses),
        "shots":       [],
    }

    # Dédupliquer les backgrounds similaires
    bg_seen = {}

    for i, analysis in enumerate(shot_analyses):
        bg_desc = analysis.get("background", "")
        bg_key  = bg_desc[:50]

        if bg_key not in bg_seen:
            bg_id = f"bg_{len(bg_seen)+1:02d}"
            bg_seen[bg_key] = bg_id
        else:
            bg_id = bg_seen[bg_key]

        shot = {
            "id":                 f"shot_{i+1:03d}",
            "frame_reference":    analysis.get("frame", i),
            "shot_type":          analysis.get("shot_type", "medium"),
            "duration_s":         analysis.get("duration_estimate_s", 2.0),
            "bg_id":              bg_id,
            "bg_prompt":          bg_desc,
            "characters":         analysis.get("characters", []),
            "character_pose":     analysis.get("character_pose", ""),
            "expression":         analysis.get("expression", ""),
            "action":             analysis.get("action", ""),
            "lighting":           analysis.get("lighting", ""),
            "comfyui_prompt":     analysis.get("comfyui_prompt", ""),
            "negative_prompt":    analysis.get("negative_prompt", ""),
            "reuse_bg":           bg_id in [s.get("bg_id") for s in storyboard["shots"]],
        }
        storyboard["shots"].append(shot)

    # Stats
    unique_bgs = len(bg_seen)
    total_shots = len(storyboard["shots"])
    reused = sum(1 for s in storyboard["shots"] if s["reuse_bg"])

    storyboard["summary"] = {
        "total_shots":     total_shots,
        "unique_bgs":      unique_bgs,
        "bg_reuse_count":  reused,
        "bg_reuse_pct":    round(reused / max(total_shots, 1) * 100, 1),
        "production_order": [
            "1. Générer les backgrounds uniques",
            "2. Générer les personnages par shot (OpenPose depuis keyframes)",
            "3. Appliquer les vêtements et détails",
            "4. Passer Detailer (yeux, mains, visage)",
            "5. Composite par couches",
            "6. Montage selon durées estimées",
        ]
    }

    return storyboard


def run_full_analysis(video_path: str,
                       fps: float = 2.0,
                       analyze_llm: bool = True,
                       logger=None) -> dict:
    """Pipeline complet : vidéo → storyboard prêt pour Ov3rLoRd."""
    log = logger or logging.getLogger("video_analyzer")
    log.info(f"[VIDEO] Analyse complète : {video_path}")

    ANALYZE_DIR.mkdir(parents=True, exist_ok=True)
    video_name = Path(video_path).stem

    # 1. Extraire les frames
    frames = extract_frames(video_path, fps=fps, logger=log)
    if not frames:
        return {"error": "extraction_failed"}

    # 2. Détecter les changements de scène
    shot_starts = detect_scene_changes(frames, logger=log)

    # 3. Extraire les keyframes
    keyframes = extract_keyframes(frames, shot_starts, logger=log)

    # 4. Analyser les keyframes avec LLM
    analyses = []
    if analyze_llm:
        log.info(f"[VIDEO] Analyse LLM de {len(keyframes)} keyframes...")
        for i, kf in enumerate(keyframes[:24]):  # max 24 shots
            log.info(f"[VIDEO] Analyse keyframe {i+1}/{min(len(keyframes),24)}")
            analysis = analyze_frame_with_llm(kf, i+1, len(keyframes), log)
            analyses.append(analysis)
    else:
        # Sans LLM : storyboard basique depuis les métadonnées
        for i, kf in enumerate(keyframes):
            analyses.append({
                "frame":            i + 1,
                "shot_type":        "medium",
                "comfyui_prompt":   "masterpiece, best quality, anime",
                "negative_prompt":  "bad quality, worst quality",
                "background":       f"background_{i+1}",
                "duration_estimate_s": 3.0,
            })

    # 5. Générer le storyboard
    storyboard = generate_storyboard(analyses, video_name)

    # 6. Sauvegarder
    sb_path = ANALYZE_DIR / f"{video_name}_storyboard.json"
    sb_path.write_text(
        json.dumps(storyboard, indent=2, ensure_ascii=False),
        encoding='utf-8'
    )

    # 7. Export MD lisible
    md_lines = [
        f"# Storyboard — {video_name}",
        f"Source : analyse vidéo rotoscoping",
        f"Shots : {storyboard['total_shots']} | "
        f"BG uniques : {storyboard['summary']['unique_bgs']} | "
        f"Réutilisation BG : {storyboard['summary']['bg_reuse_pct']}%",
        "",
    ]
    for shot in storyboard["shots"]:
        md_lines.append(f"## Shot {shot['id']} — {shot['shot_type']} ({shot['duration_s']}s)")
        md_lines.append(f"**Action :** {shot['action']}")
        md_lines.append(f"**BG :** {shot['bg_id']} — {shot['bg_prompt'][:60]}")
        md_lines.append(f"**Prompt :** `{shot['comfyui_prompt'][:80]}`")
        md_lines.append("")

    (ANALYZE_DIR / f"{video_name}_storyboard.md").write_text(
        "\n".join(md_lines), encoding='utf-8'
    )

    log.info(f"[VIDEO] Storyboard → {sb_path.name}")
    log.info(f"[VIDEO] {storyboard['summary']['unique_bgs']} BG uniques "
             f"({storyboard['summary']['bg_reuse_pct']}% réutilisation)")

    if BUS_OK:
        try:
            bus = get_bus()
            bus.write("video.storyboard_path", str(sb_path), agent_id="video_analyzer")
            bus.write("video.total_shots",     storyboard["total_shots"], agent_id="video_analyzer")
        except Exception:
            pass

    return storyboard


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Ov3rLoRd Video Analyzer V1.70")
    parser.add_argument("--video",             type=str, required=True)
    parser.add_argument("--fps",               type=float, default=2.0,
                        help="Frames par seconde à extraire (défaut: 2)")
    parser.add_argument("--analyze",           action="store_true",
                        help="Analyser avec LLM (plus lent, meilleur résultat)")
    parser.add_argument("--extract-keyframes", action="store_true",
                        help="Extraire uniquement les keyframes sans analyse")
    parser.add_argument("--full-fps",          action="store_true",
                        help="Extraire à 24fps pour dataset LoRA")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO,
                        format="%(asctime)s [%(levelname)s] %(message)s")

    if args.full_fps:
        # Mode dataset LoRA : extraction 24fps
        frames = extract_frames(args.video, fps=24.0, max_frames=720)
        print(f"Dataset LoRA : {len(frames)} frames extraites → {FRAMES_DIR}")
        print(f"Prochaine étape : python agents/lora_trainer.py --auto")

    elif args.extract_keyframes:
        frames     = extract_frames(args.video, fps=args.fps)
        shot_starts= detect_scene_changes(frames)
        keyframes  = extract_keyframes(frames, shot_starts)
        print(f"Keyframes : {len(keyframes)} shots détectés → {KEYS_DIR}")
        print(f"Copier dans ComfyUI/input/ pour utiliser avec OpenPose")

    else:
        result = run_full_analysis(
            args.video,
            fps=args.fps,
            analyze_llm=args.analyze,
        )
        s = result.get("summary", {})
        print(f"\nStoryboard généré :")
        print(f"  Shots         : {result.get('total_shots', 0)}")
        print(f"  BG uniques    : {s.get('unique_bgs', 0)}")
        print(f"  Réutilisation : {s.get('bg_reuse_pct', 0)}%")
        print(f"\nProchaine étape :")
        print(f"  python maestro.py --storyboard workspace/video_analysis/{Path(args.video).stem}_storyboard.json")

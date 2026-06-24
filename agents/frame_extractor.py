r"""
╔══════════════════════════════════════════════════════════════════════╗
║          Ov3rLoRd — frame_extractor.py  V1.0                        ║
║          Studio Onibaku Gumi 鬼爆組                                  ║
║  Extrait des frames depuis un segment vidéo, génère les skeletons   ║
║  DWPose via ComfyUI, et injecte dans pose_library.py                ║
╚══════════════════════════════════════════════════════════════════════╝

Usage exemples :
  py -3.12 agents\frame_extractor.py --video "D:\refs\eva_ep01.mp4" --start 20 --end 30 --character asuka --action combat
  py -3.12 agents\frame_extractor.py --video "D:\refs\gundam.mp4" --start 1m30s --end 2m00s --character rei --action standing --fps 2
  py -3.12 agents\frame_extractor.py --video "D:\refs\eva_ep01.mp4" --start 20 --end 30 --character asuka --dry-run

Arguments :
  --video        Chemin vers la vidéo source (mp4, mkv, avi, webm)
  --start        Timecode debut  : secondes (20) ou HH:MM:SS ou Xm Xs (1m30s)
  --end          Timecode fin    : idem
  --character    Nom du personnage  (asuka / rei / mari / shinji / eva01 / ...)
  --action       Type d action      (combat / standing / running / sitting / ...)
  --fps          Frames par seconde a extraire   (defaut: 1)
  --no-pose      Extraire les frames SANS generer les skeletons DWPose
  --no-inject    Ne pas injecter dans pose_library apres generation
  --dry-run      Simule sans rien ecrire
  --output-dir   Dossier de sortie  (defaut: workspace\poses\extracted)
  --comfy-url    URL ComfyUI        (defaut: http://127.0.0.1:8188)
"""

import os
import sys
import re
import json
import time
import shutil
import argparse
import subprocess
import tempfile
import logging
from pathlib import Path
from datetime import datetime

# ── Bannière ───────────────────────────────────────────────────────────────────
BANNER = """
╔══════════════════════════════════════════════════════════════╗
║   Ov3rLoRd — Frame Extractor V1.0  🎬                       ║
║   EVA/Gundam → DWPose → Bibliothèque Poses                   ║
╚══════════════════════════════════════════════════════════════╝
"""

# ── Config par défaut ──────────────────────────────────────────────────────────
PROJECT_ROOT  = Path(os.environ.get("OVERLORD_ROOT", r"D:\OVERLORD"))
WORKSPACE     = PROJECT_ROOT / "workspace"
DEFAULT_OUT   = WORKSPACE / "poses" / "extracted"
COMFYUI_ROOT  = Path(r"D:\Ov3rLoRd AI\ComfyUI")
COMFYUI_INPUT = COMFYUI_ROOT / "input"
COMFY_URL     = "http://127.0.0.1:8188"
POSE_LIBRARY  = PROJECT_ROOT / "agents" / "pose_library.py"

# ── Logger ─────────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
log = logging.getLogger("frame_extractor")


# ══════════════════════════════════════════════════════════════════════════════
# Parsing timecodes
# ══════════════════════════════════════════════════════════════════════════════

def parse_timecode(tc: str) -> float:
    """
    Accepte :
      - float/int en secondes          "20"  "20.5"
      - HH:MM:SS ou MM:SS              "1:30"  "0:01:30"
      - Xm Xs ou XmXs                  "1m30s"  "1m30"  "90s"
    Retourne toujours des secondes (float).
    """
    tc = tc.strip()

    # Format XmXs / Xm / Xs
    m_fmt = re.fullmatch(r"(?:(\d+)m)?(?:(\d+(?:\.\d+)?)s?)?", tc, re.IGNORECASE)
    if m_fmt and (m_fmt.group(1) or m_fmt.group(2)):
        minutes = float(m_fmt.group(1) or 0)
        seconds = float(m_fmt.group(2) or 0)
        return minutes * 60 + seconds

    # Format HH:MM:SS ou MM:SS
    parts = tc.split(":")
    if len(parts) == 2:
        return float(parts[0]) * 60 + float(parts[1])
    if len(parts) == 3:
        return float(parts[0]) * 3600 + float(parts[1]) * 60 + float(parts[2])

    # Secondes brutes
    return float(tc)


def seconds_to_ffmpeg(secs: float) -> str:
    """Convertit en format HH:MM:SS.mmm pour ffmpeg."""
    h = int(secs // 3600)
    m = int((secs % 3600) // 60)
    s = secs % 60
    return f"{h:02d}:{m:02d}:{s:06.3f}"


# ══════════════════════════════════════════════════════════════════════════════
# Extraction de frames avec ffmpeg
# ══════════════════════════════════════════════════════════════════════════════

def extract_frames(
    video_path: Path,
    start_sec: float,
    end_sec: float,
    fps: float,
    output_dir: Path,
    dry_run: bool = False,
) -> list[Path]:
    """
    Extrait les frames du segment [start_sec, end_sec] à `fps` images/seconde.
    Retourne la liste des PNG générés.
    """
    duration = end_sec - start_sec
    if duration <= 0:
        raise ValueError(f"Segment invalide : start={start_sec}s >= end={end_sec}s")

    expected_count = int(duration * fps)
    log.info(f"📽  Segment : {seconds_to_ffmpeg(start_sec)} → {seconds_to_ffmpeg(end_sec)}")
    log.info(f"📐  Durée   : {duration:.1f}s  |  FPS extract : {fps}  |  ~{expected_count} frames attendues")

    output_dir.mkdir(parents=True, exist_ok=True)
    frame_pattern = output_dir / "frame_%04d.png"

    cmd = [
        "ffmpeg", "-y",
        "-ss", seconds_to_ffmpeg(start_sec),
        "-i", str(video_path),
        "-t",  str(duration),
        "-vf", f"fps={fps}",
        "-q:v", "2",          # qualité PNG maximale
        "-pix_fmt", "rgb24",
        str(frame_pattern),
    ]

    log.info(f"🔧  ffmpeg : {' '.join(cmd)}")

    if dry_run:
        log.info("🔵  [DRY-RUN] Extraction simulée — aucun fichier écrit.")
        # Génère des noms fictifs pour la suite du pipeline
        return [output_dir / f"frame_{i:04d}.png" for i in range(1, expected_count + 1)]

    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        log.error("ffmpeg stderr :\n" + result.stderr)
        raise RuntimeError("❌ ffmpeg a échoué — voir stderr ci-dessus.")

    frames = sorted(output_dir.glob("frame_*.png"))
    log.info(f"✅  {len(frames)} frames extraites → {output_dir}")
    return frames


# ══════════════════════════════════════════════════════════════════════════════
# Génération DWPose via ComfyUI
# ══════════════════════════════════════════════════════════════════════════════

def build_dwpose_workflow(input_image_name: str, output_prefix: str) -> dict:
    """
    Workflow ComfyUI minimal pour DWPose.
    Nodes :
      1 — LoadImage (l'image source)
      2 — DWPreprocessor (DWPose body+face+hands)
      3 — SaveImage (skeleton PNG)
    """
    return {
        "1": {
            "class_type": "LoadImage",
            "inputs": {"image": input_image_name},
        },
        "2": {
            "class_type": "DWPreprocessor",
            "inputs": {
                "image": ["1", 0],
                "detect_hand": "enable",
                "detect_body": "enable",
                "detect_face": "enable",
                "resolution": 512,
            },
        },
        "3": {
            "class_type": "SaveImage",
            "inputs": {
                "images": ["2", 0],
                "filename_prefix": output_prefix,
            },
        },
    }


def run_comfy_workflow(workflow: dict, comfy_url: str, timeout: int = 60) -> bool:
    """
    Soumet un workflow à ComfyUI via /prompt et attend la fin.
    Retourne True si succès.
    """
    try:
        import urllib.request
        import urllib.error

        payload = json.dumps({"prompt": workflow}).encode("utf-8")
        req = urllib.request.Request(
            f"{comfy_url}/prompt",
            data=payload,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = json.loads(resp.read())
            prompt_id = data.get("prompt_id")
            if not prompt_id:
                log.warning("ComfyUI n'a pas retourné de prompt_id.")
                return False

        # Polling /history jusqu'à completion
        deadline = time.time() + timeout
        while time.time() < deadline:
            try:
                with urllib.request.urlopen(
                    f"{comfy_url}/history/{prompt_id}", timeout=10
                ) as hr:
                    hist = json.loads(hr.read())
                    if prompt_id in hist:
                        return True
            except Exception:
                pass
            time.sleep(2)

        log.warning(f"⏱  ComfyUI timeout après {timeout}s pour prompt {prompt_id}")
        return False

    except Exception as e:
        log.error(f"ComfyUI erreur : {e}")
        return False


def generate_dwpose(
    frames: list[Path],
    output_dir: Path,
    comfy_url: str,
    dry_run: bool = False,
) -> list[Path]:
    """
    Pour chaque frame PNG :
      1. Copie dans ComfyUI/input/
      2. Soumet workflow DWPose
      3. Récupère le skeleton depuis ComfyUI/output/
    Retourne la liste des skeletons générés.
    """
    skeletons = []
    comfy_input = COMFYUI_INPUT
    comfy_output = COMFYUI_ROOT / "output"

    comfy_input.mkdir(parents=True, exist_ok=True)
    output_dir.mkdir(parents=True, exist_ok=True)

    log.info(f"\n🤖  Génération DWPose — {len(frames)} frames → ComfyUI")

    for i, frame in enumerate(frames, 1):
        input_name = f"overlord_pose_input_{frame.stem}.png"
        prefix     = f"overlord_skeleton_{frame.stem}"
        dest_input = comfy_input / input_name

        log.info(f"  [{i:03d}/{len(frames):03d}] {frame.name} → DWPose")

        if dry_run:
            skeleton_path = output_dir / f"{prefix}_00001_.png"
            skeletons.append(skeleton_path)
            continue

        # Copie dans ComfyUI/input/
        shutil.copy2(frame, dest_input)

        # Workflow
        wf = build_dwpose_workflow(input_name, prefix)
        ok = run_comfy_workflow(wf, comfy_url, timeout=60)

        if ok:
            # ComfyUI sauve dans output/ avec le préfixe donné
            candidates = sorted(comfy_output.glob(f"{prefix}*.png"))
            if candidates:
                skeleton_path = output_dir / candidates[-1].name
                shutil.copy2(candidates[-1], skeleton_path)
                skeletons.append(skeleton_path)
                log.info(f"    ✅  Skeleton → {skeleton_path.name}")
            else:
                log.warning(f"    ⚠️  Skeleton introuvable dans ComfyUI/output/ pour {prefix}")
        else:
            log.warning(f"    ❌  DWPose échoué pour {frame.name}")

        # Nettoyage input ComfyUI
        try:
            dest_input.unlink()
        except Exception:
            pass

    log.info(f"✅  {len(skeletons)}/{len(frames)} skeletons générés")
    return skeletons


# ══════════════════════════════════════════════════════════════════════════════
# Injection dans pose_library.py
# ══════════════════════════════════════════════════════════════════════════════

def inject_into_pose_library(
    skeletons: list[Path],
    character: str,
    action: str,
    dry_run: bool = False,
) -> int:
    """
    Appelle pose_library.py --add pour chaque skeleton valide.
    Retourne le nombre d'entrées injectées.
    """
    injected = 0
    py_exec = sys.executable  # utilise le même interpréteur que le script courant

    # Essaie de trouver pose_library.py
    candidates = [
        POSE_LIBRARY,
        PROJECT_ROOT / "pose_library.py",
        Path("agents") / "pose_library.py",
        Path("pose_library.py"),
    ]
    lib_path = next((p for p in candidates if p.exists()), None)

    if lib_path is None:
        log.warning("⚠️  pose_library.py introuvable — injection skippée.")
        log.warning(f"    Chemin attendu : {POSE_LIBRARY}")
        return 0

    log.info(f"\n📚  Injection dans pose_library ({lib_path})")

    for skeleton in skeletons:
        if not skeleton.exists():
            log.warning(f"  ⚠️  Fichier absent, skip : {skeleton}")
            continue

        cmd = [
            py_exec, str(lib_path),
            "--add", str(skeleton),
            "--character", character,
            "--shot-type", "extracted",
            "--action", action,
        ]

        log.info(f"  ➕  {skeleton.name}")

        if dry_run:
            log.info(f"    🔵  [DRY-RUN] {' '.join(cmd)}")
            injected += 1
            continue

        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode == 0:
            log.info(f"    ✅  Injecté")
            injected += 1
        else:
            log.warning(f"    ❌  Erreur pose_library : {result.stderr.strip()}")

    log.info(f"✅  {injected}/{len(skeletons)} poses injectées dans la bibliothèque")
    return injected


# ══════════════════════════════════════════════════════════════════════════════
# Rapport JSON de session
# ══════════════════════════════════════════════════════════════════════════════

def write_report(
    report_path: Path,
    video: Path,
    start_sec: float,
    end_sec: float,
    fps: float,
    character: str,
    action: str,
    frames: list[Path],
    skeletons: list[Path],
    injected: int,
    dry_run: bool,
) -> None:
    report = {
        "generated_at": datetime.now().isoformat(),
        "version": "1.0",
        "dry_run": dry_run,
        "source": {
            "video": str(video),
            "start_sec": start_sec,
            "end_sec": end_sec,
            "duration_sec": round(end_sec - start_sec, 3),
            "fps_extract": fps,
        },
        "target": {
            "character": character,
            "action": action,
        },
        "results": {
            "frames_extracted": len(frames),
            "skeletons_generated": len(skeletons),
            "poses_injected": injected,
        },
        "files": {
            "frames": [str(f) for f in frames],
            "skeletons": [str(s) for s in skeletons],
        },
    }
    report_path.parent.mkdir(parents=True, exist_ok=True)
    with open(report_path, "w", encoding="utf-8") as fh:
        json.dump(report, fh, indent=2, ensure_ascii=False)
    log.info(f"📋  Rapport → {report_path}")


# ══════════════════════════════════════════════════════════════════════════════
# Main
# ══════════════════════════════════════════════════════════════════════════════

def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description="Ov3rLoRd — Extracteur de frames + DWPose pour bibliothèque de poses",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    p.add_argument("--video",       required=True,       help="Chemin vidéo source")
    p.add_argument("--start",       required=True,       help="Timecode début (ex: 20, 1m30s, 0:01:30)")
    p.add_argument("--end",         required=True,       help="Timecode fin")
    p.add_argument("--character",   required=True,       help="Nom du personnage (asuka, rei, mari...)")
    p.add_argument("--action",      default="unknown",   help="Type d'action (combat, standing...)")
    p.add_argument("--fps",         type=float, default=1.0, help="Frames/seconde à extraire (défaut: 1)")
    p.add_argument("--output-dir",  default=None,        help="Dossier de sortie frames/skeletons")
    p.add_argument("--comfy-url",   default=COMFY_URL,   help="URL ComfyUI (défaut: http://127.0.0.1:8188)")
    p.add_argument("--no-pose",     action="store_true", help="Ne pas générer les skeletons DWPose")
    p.add_argument("--no-inject",   action="store_true", help="Ne pas injecter dans pose_library")
    p.add_argument("--dry-run",     action="store_true", help="Simulation sans écriture")
    return p


def main() -> int:
    print(BANNER)
    parser = build_parser()
    args   = parser.parse_args()

    # ── Validation vidéo ──────────────────────────────────────────────────────
    video_path = Path(args.video)
    if not video_path.exists() and not args.dry_run:
        log.error(f"❌  Vidéo introuvable : {video_path}")
        return 1

    # ── Parsing timecodes ─────────────────────────────────────────────────────
    try:
        start_sec = parse_timecode(args.start)
        end_sec   = parse_timecode(args.end)
    except ValueError as e:
        log.error(f"❌  Timecode invalide : {e}")
        return 1

    if end_sec <= start_sec:
        log.error(f"❌  end ({end_sec}s) doit être > start ({start_sec}s)")
        return 1

    # ── Dossier de sortie ─────────────────────────────────────────────────────
    if args.output_dir:
        out_base = Path(args.output_dir)
    else:
        ts       = datetime.now().strftime("%Y%m%d_%H%M%S")
        out_base = DEFAULT_OUT / f"{args.character}_{args.action}_{ts}"

    frames_dir    = out_base / "frames"
    skeletons_dir = out_base / "skeletons"

    log.info(f"🎬  Vidéo    : {video_path}")
    log.info(f"👤  Perso    : {args.character}  |  Action : {args.action}")
    log.info(f"📂  Sortie   : {out_base}")
    if args.dry_run:
        log.info("🔵  MODE DRY-RUN — aucune écriture réelle")

    # ── Étape 1 — Extraction frames ───────────────────────────────────────────
    try:
        frames = extract_frames(
            video_path, start_sec, end_sec,
            args.fps, frames_dir, dry_run=args.dry_run,
        )
    except Exception as e:
        log.error(f"❌  Extraction échouée : {e}")
        return 1

    if not frames:
        log.error("❌  Aucune frame extraite.")
        return 1

    # ── Étape 2 — DWPose ──────────────────────────────────────────────────────
    skeletons: list[Path] = []
    if not args.no_pose:
        skeletons = generate_dwpose(
            frames, skeletons_dir, args.comfy_url, dry_run=args.dry_run
        )
    else:
        log.info("⏭  DWPose skippé (--no-pose)")

    # ── Étape 3 — Injection pose_library ─────────────────────────────────────
    injected = 0
    if skeletons and not args.no_inject:
        injected = inject_into_pose_library(
            skeletons, args.character, args.action, dry_run=args.dry_run
        )
    elif args.no_inject:
        log.info("⏭  Injection skippée (--no-inject)")

    # ── Rapport ───────────────────────────────────────────────────────────────
    report_path = out_base / "extraction_report.json"
    write_report(
        report_path, video_path, start_sec, end_sec,
        args.fps, args.character, args.action,
        frames, skeletons, injected, args.dry_run,
    )

    # ── Résumé final ──────────────────────────────────────────────────────────
    print("\n" + "═" * 62)
    print(f"  ✅  EXTRACTION TERMINÉE")
    print(f"  📽   Frames    : {len(frames)}")
    print(f"  🦴   Skeletons : {len(skeletons)}")
    print(f"  📚   Injectées : {injected}")
    print(f"  📋   Rapport   : {report_path}")
    print("═" * 62 + "\n")

    return 0


if __name__ == "__main__":
    sys.exit(main())

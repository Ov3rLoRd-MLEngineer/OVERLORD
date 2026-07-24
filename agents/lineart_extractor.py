# ██████╗ ██╗   ██╗██████╗ ██████╗ ██╗      ██████╗ ██████╗ ██████╗
# ██╔═══██╗██║   ██║╚════██╗██╔══██╗██║     ██╔═══██╗██╔══██╗██╔══██╗
# ██║   ██║██║   ██║ █████╔╝██████╔╝██║     ██║   ██║██████╔╝██║  ██║
# ██║   ██║╚██╗ ██╔╝ ╚═══██╗██╔══██╗██║     ██║   ██║██╔══██╗██║  ██║
# ╚██████╔╝ ╚████╔╝ ██████╔╝██║  ██║███████╗╚██████╔╝██║  ██║██████╔╝
# ╚═════╝   ╚═══╝  ╚═════╝ ╚═╝  ╚═╝╚══════╝ ╚═════╝ ╚═╝  ╚═╝╚═════╝
# Ov3rLoRd -- pipeline de production anime autonome (ComfyUI)
# https://github.com/Ov3rLoRd-MLEngineer
#
"""
lineart_extractor.py -- Ov3rLoRd Pipeline

Extrait les cartes lineart (contours/traits) depuis des frames video Kling
via le preprocesseur ComfyUI LineartStandardPreprocessor (pas de modele
SDXL, juste le preprocesseur) -- alimente ensuite lineart_remapper.py pour
un remapping vers la resolution finale 1344x768.

Sortie : 910x512 (meme resolution que les squelettes DWPose avant
remapping), ecrite dans DEMO/frames/lineart_910x512/.

Necessite ComfyUI demarre sur http://127.0.0.1:8188 (sauf --dry-run).

Options :
  --source PATH    Dossier des frames source Kling (defaut: DEMO/frames/video_frames)
  --output PATH    Dossier de sortie lineart (defaut: DEMO/frames/lineart_910x512)
  --start N        Index de la premiere frame a traiter (defaut: 0)
  --end N          Index de la derniere frame incluse (defaut: toutes)
  --skip-existing  Ignore les frames deja extraites (defaut: active)
  --sigma FLOAT    Gaussian sigma du preprocesseur LineartStandard (defaut: 6.0)
  --threshold INT  Intensity threshold du preprocesseur (defaut: 8)
  --dry-run        Simulation sans appel ComfyUI

Usage :
  py -3.12 agents/lineart_extractor.py
  py -3.12 agents/lineart_extractor.py --start 100 --end 200
  py -3.12 agents/lineart_extractor.py --dry-run
"""

import os
import sys
import argparse
from pathlib import Path
import requests
import json
import time
import shutil
from PIL import Image

COMFYUI_URL = "http://127.0.0.1:8188"
COMFYUI_INPUT = r"D:\Ov3rLoRd AI\ComfyUI\input"
COMFYUI_OUTPUT_ROOT = r"D:\Ov3rLoRd AI\ComfyUI\output"
COMFYUI_OUTPUT = r"D:\Ov3rLoRd AI\ComfyUI\output\lineart_extract"
FRAMES_DIR = r"D:\OVERLORD\DEMO\frames"
OUTPUT_DIR = os.path.join(FRAMES_DIR, "lineart_910x512")
SOURCE_VIDEO_FRAMES = os.path.join(FRAMES_DIR, "video_frames")

# Sortie 910x512 — même résolution que les squelettes DWPose avant remapping
# Le remapping vers 1344x768 est délégué à lineart_remapper.py
TARGET_W = 910
TARGET_H = 512


def print_banner():
    print("=" * 66)
    print("  Ov3rLoRd -- Lineart Extractor V1.1")
    print("=" * 66)


def check_comfyui():
    try:
        r = requests.get(f"{COMFYUI_URL}/system_stats", timeout=5)
        return r.status_code == 200
    except Exception:
        return False


def copy_to_comfyui_input(src_path, dest_name):
    """Copie sous nom fixe → cache-buster ComfyUI"""
    dest = os.path.join(COMFYUI_INPUT, dest_name)
    shutil.copy2(src_path, dest)
    return dest_name


def build_lineart_workflow(image_filename, output_prefix, sigma=6.0, threshold=8):
    """
    Workflow ComfyUI minimal :
      LoadImage → LineartStandardPreprocessor → SaveImage
    Pas de modèle SDXL — juste le préprocesseur.
    """
    workflow = {
        "1": {
            "class_type": "LoadImage",
            "inputs": {
                "image": image_filename
            }
        },
        "2": {
            "class_type": "LineartStandardPreprocessor",
            "inputs": {
                "image": ["1", 0],
                "guassian_sigma": sigma,
                "intensity_threshold": threshold,
                "resolution": TARGET_W
            }
        },
        "3": {
            "class_type": "SaveImage",
            "inputs": {
                "images": ["2", 0],
                "filename_prefix": output_prefix
            }
        }
    }
    return workflow


def submit_workflow(workflow):
    payload = {"prompt": workflow}
    try:
        r = requests.post(f"{COMFYUI_URL}/prompt", json=payload, timeout=30)
        if r.status_code == 200:
            return r.json().get("prompt_id")
        else:
            print(f"  [ERR] HTTP {r.status_code}: {r.text[:200]}")
            return None
    except Exception as e:
        print(f"  [ERR] Submit: {e}")
        return None


def wait_for_completion(prompt_id, timeout=120):
    start = time.time()
    while time.time() - start < timeout:
        try:
            r = requests.get(f"{COMFYUI_URL}/history/{prompt_id}", timeout=10)
            if r.status_code == 200:
                history = r.json()
                if prompt_id in history:
                    return history[prompt_id]
        except Exception:
            pass
        time.sleep(1)
    return None


def get_output_image(history_entry, output_prefix):
    """Récupère le fichier de sortie depuis l'historique ComfyUI"""
    prefix_name = output_prefix.split("/")[-1]
    try:
        outputs = history_entry.get("outputs", {})
        for node_id, node_out in outputs.items():
            images = node_out.get("images", [])
            for img_info in images:
                fname = img_info.get("filename", "")
                subfolder = img_info.get("subfolder", "")
                if prefix_name in fname:
                    candidates = [
                        os.path.join(COMFYUI_OUTPUT_ROOT, subfolder, fname),
                        os.path.join(COMFYUI_OUTPUT, fname),
                        os.path.join(COMFYUI_OUTPUT_ROOT, fname),
                    ]
                    for c in candidates:
                        if os.path.exists(c):
                            return c
    except Exception as e:
        print(f"  [WARN] get_output_image: {e}")
    return None


def find_latest_output(prefix_name, search_root):
    """Fallback : fichier le plus récent avec le préfixe donné"""
    candidates = []
    for root, dirs, files in os.walk(search_root):
        for f in files:
            if f.startswith(prefix_name) and f.endswith(".png"):
                full = os.path.join(root, f)
                candidates.append((os.path.getmtime(full), full))
    if candidates:
        candidates.sort(reverse=True)
        return candidates[0][1]
    return None


def resize_and_save(src_path, dest_path):
    """Redimensionne en TARGET_W x TARGET_H (LANCZOS) et sauvegarde PNG"""
    with Image.open(src_path) as img:
        img_resized = img.resize((TARGET_W, TARGET_H), Image.LANCZOS)
        img_resized.save(dest_path, "PNG")


def get_source_frames(source_dir):
    """Liste les frames source triées par nom"""
    if not os.path.exists(source_dir):
        return []
    exts = {".png", ".jpg", ".jpeg"}
    frames = sorted([
        os.path.join(source_dir, f)
        for f in os.listdir(source_dir)
        if os.path.splitext(f)[1].lower() in exts
    ])
    return frames


def main():
    print_banner()

    parser = argparse.ArgumentParser(description="Ov3rLoRd Lineart Extractor V1.0")
    parser.add_argument("--source", type=str, default=SOURCE_VIDEO_FRAMES,
                        help=f"Dossier frames source Kling (défaut: {SOURCE_VIDEO_FRAMES})")
    parser.add_argument("--output", type=str, default=OUTPUT_DIR,
                        help=f"Dossier sortie lineart 1344x768 (défaut: {OUTPUT_DIR})")
    parser.add_argument("--start", type=int, default=0,
                        help="Index frame de début (défaut: 0)")
    parser.add_argument("--end", type=int, default=None,
                        help="Index frame de fin incluse (défaut: toutes)")
    parser.add_argument("--skip-existing", action="store_true", default=True,
                        help="Ignorer frames déjà extraites (défaut: True)")
    parser.add_argument("--sigma", type=float, default=6.0,
                        help="Gaussian sigma LineartStandard (défaut: 6.0)")
    parser.add_argument("--threshold", type=int, default=8,
                        help="Intensity threshold LineartStandard (défaut: 8)")
    parser.add_argument("--dry-run", action="store_true",
                        help="Simulation sans appel ComfyUI")
    args = parser.parse_args()

    # Vérification ComfyUI
    if not args.dry_run:
        if not check_comfyui():
            print("[ERR] ComfyUI non accessible sur http://127.0.0.1:8188")
            print("      Lance ComfyUI puis relance ce script.")
            sys.exit(1)
        print("[OK] ComfyUI accessible")

    # Création dossiers
    os.makedirs(args.output, exist_ok=True)
    os.makedirs(COMFYUI_OUTPUT, exist_ok=True)

    # Lister frames source
    frames = get_source_frames(args.source)
    if not frames:
        print(f"[ERR] Aucune frame trouvée dans : {args.source}")
        print(f"      Extrais d'abord les frames Kling avec frame_extractor.py")
        print(f"      Ou spécifie le bon dossier avec --source CHEMIN")
        sys.exit(1)

    # Sélection plage
    end_idx = args.end if args.end is not None else len(frames) - 1
    end_idx = min(end_idx, len(frames) - 1)
    frames_to_process = frames[args.start:end_idx + 1]

    print(f"  Source      : {args.source}")
    print(f"  Output      : {args.output}")
    print(f"  Frames      : {args.start} -> {end_idx} ({len(frames_to_process)} frames)")
    print(f"  Résolution  : {TARGET_W}x{TARGET_H}")
    print(f"  Sigma       : {args.sigma} / Threshold : {args.threshold}")
    print(f"  Skip exist. : {args.skip_existing}")
    if args.dry_run:
        print(f"  [DRY-RUN]   : Simulation uniquement")
    print("")

    ok = 0
    skip = 0
    err = 0

    for i, frame_path in enumerate(frames_to_process):
        frame_num = args.start + i
        frame_name = f"lineart_{frame_num:04d}.png"
        dest_path = os.path.join(args.output, frame_name)

        # Skip si déjà extrait
        if args.skip_existing and os.path.exists(dest_path):
            skip += 1
            continue

        if args.dry_run:
            print(f"  [DRY] {frame_num:04d} -> {frame_name}")
            ok += 1
            continue

        # Copie sous nom fixe → cache-buster
        copy_to_comfyui_input(frame_path, "ov_lineart_source_current.png")

        # Préfixe output ComfyUI
        output_prefix = f"lineart_extract/lineart_{frame_num:04d}"

        # Build et submit
        workflow = build_lineart_workflow(
            "ov_lineart_source_current.png",
            output_prefix,
            sigma=args.sigma,
            threshold=args.threshold
        )
        prompt_id = submit_workflow(workflow)

        if not prompt_id:
            print(f"  [{frame_num:04d}] [ERR] Submit echoue")
            err += 1
            continue

        # Attente
        history = wait_for_completion(prompt_id, timeout=60)
        if not history:
            print(f"  [{frame_num:04d}] [ERR] Timeout")
            err += 1
            continue

        # Récupération fichier
        prefix_name = f"lineart_{frame_num:04d}"
        src = get_output_image(history, output_prefix)
        if not src:
            src = find_latest_output(prefix_name, COMFYUI_OUTPUT_ROOT)

        if src and os.path.exists(src):
            resize_and_save(src, dest_path)
            print(f"  [{frame_num:04d}] [OK] -> {frame_name}")
            ok += 1
        else:
            print(f"  [{frame_num:04d}] [ERR] Fichier introuvable en sortie ComfyUI")
            err += 1

    print("")
    print("=" * 66)
    print(f"  Extraites : {ok}")
    print(f"  Skippees  : {skip}")
    print(f"  Erreurs   : {err}")
    print(f"  Output    : {args.output}")
    print("=" * 66)


if __name__ == "__main__":
    main()

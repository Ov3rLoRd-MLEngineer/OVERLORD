"""
Ov3rLoRd — Frames To Video Agent V1.0
Reconvertit les frames PNG Asuka générées en MP4 final 24fps
"""

import ast
import os
import sys
import glob
import subprocess
import argparse

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)
import config

# ── CONFIG ────────────────────────────────────────────────────────────────────
COMFYUI_OUTPUT = str(config.COMFYUI_OUTPUT / "asuka_run")
DEMO_DIR       = str(config.DEMO_DIR)
OUTPUT_VIDEO   = os.path.join(DEMO_DIR, "asuka_run_FINAL.mp4")
FPS            = 24

# ── AST VALIDATION ────────────────────────────────────────────────────────────
def self_validate():
    with open(__file__, encoding="utf-8") as f:
        src = f.read()
    ast.parse(src)
    print("[OK] AST validation passed")

# ── MAIN ──────────────────────────────────────────────────────────────────────
def main():
    parser = argparse.ArgumentParser(description="Ov3rLoRd Frames To Video")
    parser.add_argument("--input",  default=COMFYUI_OUTPUT, help="Dossier frames PNG")
    parser.add_argument("--output", default=OUTPUT_VIDEO,   help="Fichier MP4 output")
    parser.add_argument("--fps",    type=int, default=FPS,  help="FPS (défaut: 24)")
    parser.add_argument("--crf",    type=int, default=18,   help="CRF qualité (défaut: 18)")
    args = parser.parse_args()

    self_validate()

    # Chercher les frames
    patterns = [
        os.path.join(args.input, "frame_*.png"),
        os.path.join(args.input, "*.png")
    ]
    frames = []
    for p in patterns:
        frames = sorted(glob.glob(p))
        if frames:
            break

    if not frames:
        print(f"[ERREUR] Aucune frame PNG trouvée dans {args.input}")
        sys.exit(1)

    print(f"╔══════════════════════════════════════════════════════════════╗")
    print(f"║   Ov3rLoRd — Frames To Video                                ║")
    print(f"╚══════════════════════════════════════════════════════════════╝")
    print(f"  Frames trouvées : {len(frames)}")
    print(f"  FPS             : {args.fps}")
    print(f"  Output          : {args.output}")
    print()

    # Créer liste ffmpeg
    list_file = os.path.join(args.input, "_frames_list.txt")
    with open(list_file, "w", encoding="utf-8") as f:
        for frame in frames:
            f.write(f"file '{frame.replace(chr(92), '/')}'\n")
            f.write(f"duration {1/args.fps:.6f}\n")

    # Conversion ffmpeg
    cmd = [
        "ffmpeg", "-y",
        "-f", "concat",
        "-safe", "0",
        "-i", list_file,
        "-vsync", "vfr",
        "-c:v", "libx264",
        "-crf", str(args.crf),
        "-pix_fmt", "yuv420p",
        "-movflags", "+faststart",
        args.output
    ]

    print(f"[FFMPEG] Assemblage en cours...")
    result = subprocess.run(cmd, capture_output=True, text=True)

    os.remove(list_file)

    if result.returncode != 0:
        print(f"[ERREUR] ffmpeg : {result.stderr[-500:]}")
        sys.exit(1)

    size_mb = os.path.getsize(args.output) / 1024 / 1024
    duration = len(frames) / args.fps

    print(f"[OK] Vidéo générée !")
    print()
    print(f"══════════════════════════════════════════════════════════════")
    print(f"  📽  Fichier  : {args.output}")
    print(f"  🎞  Frames   : {len(frames)}")
    print(f"  ⏱  Durée    : {duration:.1f}s @ {args.fps}fps")
    print(f"  💾 Taille   : {size_mb:.1f} MB")
    print(f"══════════════════════════════════════════════════════════════")

if __name__ == "__main__":
    main()

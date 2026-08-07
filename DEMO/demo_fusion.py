"""
Ov3rLoRd — Agent Fusion Demo Asuka Run
Fusionne 001-006.mp4 en un seul fichier + génère la fiche de prompts frame par frame
"""

import subprocess
import json
import ast
import os
import sys

# ── CONFIG ──────────────────────────────────────────────────────────────────
DEMO_DIR = r"D:\OVERLORD\DEMO"
OUTPUT_VIDEO = os.path.join(DEMO_DIR, "asuka_run_reference.mp4")
OUTPUT_JSON  = os.path.join(DEMO_DIR, "asuka_run_prompts.json")
OUTPUT_TXT   = os.path.join(DEMO_DIR, "asuka_run_prompts.txt")
FPS = 24

SHOTS = [
    {
        "file": "001.mp4",
        "duration": 6,
        "shot": 1,
        "label": "Départ course / accélération",
        "prompt": (
            "Athletic woman in black bodysuit, explosive sprint start from crouched position, "
            "wide full body shot, pure white background, side view, powerful acceleration, "
            "arms pumping, hair flowing back, slow motion, sharp focus, cinematic"
        ),
        "controlnet_hint": "Pose départ sprint — squelette incliné vers l'avant, jambe arrière propulsée"
    },
    {
        "file": "002.mp4",
        "duration": 6,
        "shot": 2,
        "label": "Gros plan visage / concentration / transition",
        "prompt": (
            "Athletic woman, extreme close-up face, running at full speed, "
            "intense focused expression, motion blur background, pure white background, "
            "side angle, sweat, determination, cinematic, sharp face"
        ),
        "controlnet_hint": "Gros plan visage — peu utile pour DWPose, garder pour montage final seulement"
    },
    {
        "file": "003.mp4",
        "duration": 6,
        "shot": 3,
        "label": "Chute / contact sol",
        "prompt": (
            "Athletic woman in black bodysuit, dynamic low angle shot, falling forward onto ground, "
            "knees and hands catching impact, explosive dust, pure white background, "
            "full body side view, slow motion freeze frame, cinematic, sharp focus"
        ),
        "controlnet_hint": "Corps penché en avant, mains au sol, jambes en extension — excellent pour DWPose"
    },
    {
        "file": "004.mp4",
        "duration": 8,
        "shot": 4,
        "label": "Relèvement depuis sol (push-up position)",
        "prompt": (
            "Athletic woman in black bodysuit, recovering from fall, pushing up from ground "
            "with both hands, body low horizontal, one knee coming forward, explosive push off ground, "
            "pure white background, full body side view, slow motion, cinematic, sharp focus, "
            "dust particles, momentum forward"
        ),
        "controlnet_hint": "Corps horizontal push-up — poses basses dynamiques pour DWPose"
    },
    {
        "file": "005.mp4",
        "duration": 8,
        "shot": 5,
        "label": "Debout / posture dynamique",
        "prompt": (
            "Athletic woman in black bodysuit, rising up from ground, pushing off hands, "
            "one foot planted forward, body coming upright, standing up explosively, "
            "then stopping abruptly in strong upright stance, pure white background, "
            "full body side view, cinematic, slow motion, sharp focus"
        ),
        "controlnet_hint": "Transition sol → debout — posture droite dynamique"
    },
    {
        "file": "006.mp4",
        "duration": 8,
        "shot": 6,
        "label": "Reprise jogging / accélération",
        "prompt": (
            "Athletic woman in black bodysuit, starting to walk forward, progressively "
            "accelerating into full sprint, slow walk to explosive run transition, "
            "pure white background, full body side view, left to right movement, "
            "cinematic, sharp focus, hair flowing back as speed increases"
        ),
        "controlnet_hint": "Transition marche → course — miroir du Shot 1 pour boucler la séquence"
    },
]

# ── VALIDATION AST ───────────────────────────────────────────────────────────
def self_validate():
    with open(__file__, encoding="utf-8") as f:
        src = f.read()
    ast.parse(src)
    print("[OK] AST validation passed")

# ── FUSION FFMPEG ────────────────────────────────────────────────────────────
def fusion_videos():
    concat_file = os.path.join(DEMO_DIR, "_concat_list.txt")
    
    # Vérifier que tous les fichiers existent
    for shot in SHOTS:
        path = os.path.join(DEMO_DIR, shot["file"])
        if not os.path.exists(path):
            print(f"[ERREUR] Fichier manquant : {path}")
            sys.exit(1)
    
    # Créer le fichier de liste ffmpeg
    with open(concat_file, "w", encoding="utf-8") as f:
        for shot in SHOTS:
            path = os.path.join(DEMO_DIR, shot["file"]).replace("\\", "/")
            f.write(f"file '{path}'\n")
    
    # Fusion ffmpeg
    cmd = [
        "ffmpeg", "-y",
        "-f", "concat",
        "-safe", "0",
        "-i", concat_file,
        "-c:v", "libx264",
        "-crf", "18",
        "-pix_fmt", "yuv420p",
        "-r", str(FPS),
        OUTPUT_VIDEO
    ]
    
    print(f"[FUSION] Démarrage fusion {len(SHOTS)} clips...")
    result = subprocess.run(cmd, capture_output=True, text=True)
    
    if result.returncode != 0:
        print(f"[ERREUR] ffmpeg : {result.stderr}")
        sys.exit(1)
    
    print(f"[OK] Vidéo fusionnée : {OUTPUT_VIDEO}")
    os.remove(concat_file)

# ── FICHE PROMPTS ─────────────────────────────────────────────────────────────
def generate_prompt_sheet():
    total_frames = 0
    data = {"shots": [], "total_frames": 0, "total_duration": 0, "fps": FPS}
    txt_lines = []
    txt_lines.append("=" * 70)
    txt_lines.append("OV3RLORD — FICHE PROMPTS ASUKA RUN REFERENCE")
    txt_lines.append("=" * 70)
    txt_lines.append(f"FPS: {FPS} | Total: 42s | Fichier: asuka_run_reference.mp4")
    txt_lines.append("")

    frame_cursor = 0
    for shot in SHOTS:
        frame_start = frame_cursor
        frame_count = shot["duration"] * FPS
        frame_end   = frame_cursor + frame_count - 1
        frame_cursor += frame_count

        shot_data = {
            "shot": shot["shot"],
            "label": shot["label"],
            "file": shot["file"],
            "duration_s": shot["duration"],
            "frame_start": frame_start,
            "frame_end": frame_end,
            "frame_count": frame_count,
            "prompt": shot["prompt"],
            "controlnet_hint": shot["controlnet_hint"]
        }
        data["shots"].append(shot_data)
        total_frames += frame_count

        txt_lines.append(f"── SHOT {shot['shot']} ─ {shot['label'].upper()}")
        txt_lines.append(f"   Fichier    : {shot['file']}")
        txt_lines.append(f"   Durée      : {shot['duration']}s")
        txt_lines.append(f"   Frames     : {frame_start} → {frame_end} ({frame_count} frames)")
        txt_lines.append(f"   Prompt     : {shot['prompt']}")
        txt_lines.append(f"   ControlNet : {shot['controlnet_hint']}")
        txt_lines.append("")

    data["total_frames"] = total_frames
    data["total_duration"] = sum(s["duration"] for s in SHOTS)

    txt_lines.append("=" * 70)
    txt_lines.append(f"TOTAL : {total_frames} frames | {data['total_duration']}s @ {FPS}fps")
    txt_lines.append("=" * 70)

    # Sauvegarde JSON
    with open(OUTPUT_JSON, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    print(f"[OK] Fiche JSON : {OUTPUT_JSON}")

    # Sauvegarde TXT
    with open(OUTPUT_TXT, "w", encoding="utf-8") as f:
        f.write("\n".join(txt_lines))
    print(f"[OK] Fiche TXT  : {OUTPUT_TXT}")

    # Affichage console
    print()
    for line in txt_lines:
        print(line)

# ── MAIN ──────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    self_validate()
    fusion_videos()
    generate_prompt_sheet()
    print("\n[DONE] Pipeline Asuka Run Reference terminé !")

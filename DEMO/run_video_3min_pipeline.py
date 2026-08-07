"""Pipeline complet 3 minutes (Priorite 1, tache_a_faire 2026-08-06) :
enchaine la generation SVI 51 clips (sequence_plan_20260806.csv, camera
prompts derives des guides Blender), l'assemblage + upscale SeedVR2 segmente
<=64 frames (assemble_and_upscale.py, deja valide sur les blocs v1-v9), puis
copie le resultat final vers DEMO/output/miku_demo_3min_v1.mp4.

Concu pour tourner en process detache visible (cf. CLAUDE.md "Lancement de
process detaches") :
    start cmd /k py -3.12 DEMO/run_video_3min_pipeline.py

Chaque sous-etape utilise l'interpreteur qu'elle attend deja en pratique
(generate_svi_chain.py -> python_embeded ComfyUI, assemble_and_upscale.py ->
py -3.12) plutot que de forcer un seul environnement pour les deux.
"""
import csv
import os
import shutil
import subprocess
import sys
import time

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
COMFY_PY = r"D:\Ov3rLoRd AI\python_embeded\python.exe"
PY312 = "py"

RUN_NAME = "v3min_kf"
N_CLIPS = 51
CLIP1_SEED = 900000001
CLIP1_KEYFRAME = r"D:\Ov3rLoRd AI\ComfyUI\output\WorkflowA\sdxl_keyframe_miku_00001_.png"
CAMERA_PROMPTS_FILE = os.path.join(REPO_ROOT, "DEMO", "camera_prompts_v3min.json")
# Priorite 3 session_nuit 2026-08-06/07 : ancrage identite/tenue par clip
# (clip_vision, cf. generate_svi_chain.py::add_clip_vision_identity_anchor),
# cense corriger le changement de tenue + l'accumulation de flou observes
# sur le premier run v3min (sans cet ancrage).
KEYFRAME_ANCHOR_DIR = os.path.join(REPO_ROOT, "DEMO", "frames", "keyframes_per_clip")
OUT_DIR = os.path.join(REPO_ROOT, "DEMO", "output")
FINAL_OUTPUT = os.path.join(OUT_DIR, "miku_demo_3min_v2_keyframed.mp4")
LOG_PATH = os.path.join(OUT_DIR, "run_video_3min_pipeline.log")
SEQUENCE_CSV = os.path.join(REPO_ROOT, "DEMO", "frames", "sequence_plan_20260806.csv")
GPU_LOG = os.path.join(REPO_ROOT, "gpu_usage_log.csv")


def log(msg):
    line = f"[{time.strftime('%Y-%m-%dT%H:%M:%S')}] {msg}"
    print(line, flush=True)
    os.makedirs(OUT_DIR, exist_ok=True)
    with open(LOG_PATH, "a", encoding="utf-8") as f:
        f.write(line + "\n")


def run(cmd, label):
    log(f"START {label}: {' '.join(cmd)}")
    t0 = time.time()
    result = subprocess.run(cmd, cwd=REPO_ROOT)
    dt = time.time() - t0
    if result.returncode != 0:
        log(f"ECHEC {label} (code {result.returncode}) apres {dt:.1f}s")
        raise SystemExit(result.returncode)
    log(f"OK {label} en {dt:.1f}s")
    return dt


def append_gpu_log(total_minutes, description):
    is_new = not os.path.exists(GPU_LOG)
    with open(GPU_LOG, "a", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        if is_new:
            w.writerow(["date_iso", "gpu", "duree_minutes", "module", "description",
                        "cout_estime_usd", "estime_retroactif"])
        cout = round(total_minutes / 60.0 * 1.20, 2)  # equivalent-cout A100 ~1,20$/h, reference
        w.writerow([time.strftime("%Y-%m-%dT%H:%M:%S"), "RTX5080", round(total_minutes, 2),
                    "video-3min-pipeline", description, cout, "false"])


def main():
    t_start = time.time()
    with open(SEQUENCE_CSV, encoding="utf-8") as f:
        n_rows = sum(1 for _ in csv.DictReader(f))
    log(f"Sequence plan : {n_rows} clips (attendu {N_CLIPS})")

    gen_cmd = [
        COMFY_PY, os.path.join("DEMO", "generate_svi_chain.py"),
        "--run-name", RUN_NAME,
        "--clip1-keyframe", CLIP1_KEYFRAME,
        "--clip1-seed", str(CLIP1_SEED),
        "--n-clips", str(N_CLIPS),
        "--camera-prompts-file", CAMERA_PROMPTS_FILE,
        "--out-dir", OUT_DIR,
        "--vmd-used", "sequence_plan_20260806 (51 VMD varies, cf. DEMO/frames/sequence_plan_20260806.csv)",
        "--keyframe-anchor-dir", KEYFRAME_ANCHOR_DIR,
    ]
    dt_gen = run(gen_cmd, "generation SVI 51 clips")

    assemble_cmd = [PY312, "-3.12", os.path.join("DEMO", "assemble_and_upscale.py"),
                     "--run-name", RUN_NAME, "--out-dir", OUT_DIR]
    dt_asm = run(assemble_cmd, "assemblage + upscale SeedVR2")

    produced = os.path.join(OUT_DIR, f"miku_demo_30s_{RUN_NAME}.mp4")
    if not os.path.exists(produced):
        log(f"ECHEC: sortie attendue absente ({produced})")
        raise SystemExit(1)
    shutil.copy2(produced, FINAL_OUTPUT)
    log(f"RESULT: sortie finale -> {FINAL_OUTPUT}")

    total_minutes = (time.time() - t_start) / 60.0
    append_gpu_log(
        total_minutes,
        f"Pipeline video 3min complet (51 clips SVI chaines, camera prompts derives des guides "
        f"Blender + rotation XYZ/sol reflechissant, ColorMatch LAB inter-clips, upscale SeedVR2 "
        f"segmente <=64 frames). generation={dt_gen/60:.1f}min, assemblage/upscale={dt_asm/60:.1f}min.",
    )
    log(f"RESULT: pipeline complet en {total_minutes:.1f} min")


if __name__ == "__main__":
    main()

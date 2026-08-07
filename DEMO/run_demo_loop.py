"""Boucle autonome : enchaine des blocs de ~30s (v2, v3, ...) sur les VMD
restants de DEMO/vmd_queue.json, jusqu'a epuisement de la file ou creation
du fichier DEMO/STOP_LOOP.flag (arret propre demande par l'utilisateur).

Concu pour tourner en process detache (cf. CLAUDE.md "Lancement de process
detaches") :
    start cmd /k py -3.12 DEMO/run_demo_loop.py

Chaque iteration :
    1. generate_keyframe.py  (nouvelle pose VMD -> keyframe SDXL stylisee)
    2. generate_svi_chain.py (clip1 depuis keyframe + clips 2-7 chaines)
    3. assemble_and_upscale.py (concat ffmpeg + SeedVR2 960x1440)

Seed de base par iteration : BASE_SEED_START + (index_iteration-1)*1000003
(grand pas premier pour eviter tout chevauchement avec les seeds
base+i*137 utilisees a l'interieur d'un bloc).
"""
import json
import os
import subprocess
import sys
import time

from upscale_segments_lib import probe_frame_count

PMX = r"E:\Data Demo\_extracted\atrier_Tsatou式初音ミク_ver.1.00\Tsatou式初音ミク_ver.1.00.pmx"
QUEUE_PATH = os.path.join("DEMO", "vmd_queue.json")
STOP_FLAG = os.path.join("DEMO", "STOP_LOOP.flag")
STOP_GENERATION_FLAG = os.path.join("DEMO", "STOP_GENERATION.flag")
GPU_PROGRESS_FILE = os.path.join("DEMO", "output", "gpu_progress.json")
GPU_BUDGET_FILE = os.path.join("DEMO", "output", "gpu_budget_state.json")
LOOP_LOG = os.path.join("DEMO", "output", "loop_log.txt")
PY = sys.executable
BASE_SEED_START = 741852963
SEED_ITER_STEP = 1000003

# Cible dataset LoRA (consignes.txt 2026-08-06) : 10 min video @ 24fps.
TARGET_FRAMES = 14400

# Budget GPU 8h total SVI+postprod (consignes (2).txt, 2026-08-06). Baseline
# = temps reellement consomme v1->v7 + tests postprod, reconstruit depuis
# loop_log.txt et logue retroactivement dans gpu_usage_log.csv (294.44 min) --
# v8 etait en cours au moment du calcul et redemarre de zero par ce
# redemarrage propre, donc pas inclus dans la baseline (evite double compte).
GPU_BUDGET_SECONDS = 8 * 3600
GPU_BUDGET_BASELINE_SECONDS = 294.44 * 60


def log(msg):
    line = f"[{time.strftime('%Y-%m-%dT%H:%M:%S')}] {msg}"
    print(line, flush=True)
    os.makedirs(os.path.dirname(LOOP_LOG), exist_ok=True)
    with open(LOOP_LOG, "a", encoding="utf-8") as f:
        f.write(line + "\n")


def run(cmd, label):
    log(f"START {label}: {' '.join(cmd)}")
    # capture_output=True (PIPE) a provoque un blocage indefini observe le
    # 2026-08-05 (assemble-v2 : fichier final ecrit sur disque mais
    # subprocess.run() jamais revenu -- piege Windows classique ou un
    # sous-processus petit-enfant garde le handle du pipe stdout/stderr
    # ouvert, empechant l'EOF). Rediriger vers un fichier reel evite la
    # classe de bug entierement.
    log_path = os.path.join("DEMO", "output", f"_subproc_{label}.log")
    with open(log_path, "w", encoding="utf-8") as logf:
        r = subprocess.run(cmd, stdout=logf, stderr=subprocess.STDOUT, text=True, encoding="utf-8", errors="replace")
    with open(log_path, encoding="utf-8", errors="replace") as logf:
        out = logf.read()
    log(f"END {label} (rc={r.returncode})")
    if out:
        log(f"stdout tail {label}:\n" + "\n".join(out.strip().splitlines()[-20:]))
    if r.returncode != 0:
        raise RuntimeError(f"{label} a echoue (rc={r.returncode}) -- voir {log_path}")
    return out


def next_run_index():
    manifest_dir = os.path.join("DEMO", "output")
    existing = [f for f in os.listdir(manifest_dir) if f.startswith("svi_v") and f.endswith("_clip_manifest.json")]
    nums = []
    for f in existing:
        try:
            nums.append(int(f[len("svi_v"):-len("_clip_manifest.json")]))
        except ValueError:
            pass
    return (max(nums) + 1) if nums else 2


def load_queue():
    with open(QUEUE_PATH, encoding="utf-8") as f:
        return json.load(f)


def save_queue(data):
    with open(QUEUE_PATH, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def read_gpu_progress():
    if not os.path.exists(GPU_PROGRESS_FILE):
        return {"svi_frames_available": 0, "svi_loop_done": False}
    with open(GPU_PROGRESS_FILE, encoding="utf-8") as f:
        return json.load(f)


def write_gpu_progress(svi_frames_available, svi_loop_done, last_run=None):
    os.makedirs(os.path.dirname(GPU_PROGRESS_FILE), exist_ok=True)
    with open(GPU_PROGRESS_FILE, "w", encoding="utf-8") as f:
        json.dump({
            "svi_frames_available": svi_frames_available,
            "svi_loop_done": svi_loop_done,
            "last_run": last_run,
            "updated": time.strftime("%Y-%m-%dT%H:%M:%S"),
        }, f, indent=2)


def read_gpu_budget():
    if not os.path.exists(GPU_BUDGET_FILE):
        return {"cumulative_seconds": GPU_BUDGET_BASELINE_SECONDS}
    with open(GPU_BUDGET_FILE, encoding="utf-8") as f:
        return json.load(f)


def write_gpu_budget(cumulative_seconds, last_run=None):
    os.makedirs(os.path.dirname(GPU_BUDGET_FILE), exist_ok=True)
    with open(GPU_BUDGET_FILE, "w", encoding="utf-8") as f:
        json.dump({
            "cumulative_seconds": cumulative_seconds,
            "cumulative_hours": round(cumulative_seconds / 3600, 3),
            "budget_hours": GPU_BUDGET_SECONDS / 3600,
            "last_run": last_run,
            "updated": time.strftime("%Y-%m-%dT%H:%M:%S"),
        }, f, indent=2)


def launch_descending_postprod_helper(cumulative_frames):
    """Bascule GPU0 (5080) sur le pipeline inpaint en ordre decroissant depuis
    la derniere frame produite, une fois la generation SVI arretee (consigne :
    'la 5080 termine son clip en cours puis bascule sur le meme pipeline
    inpaint en ordre decroissant'). Detache (start cmd /k), cf. CLAUDE.md."""
    keyframe_dir = r"D:\Ov3rLoRd AI\ComfyUI\output\DemoMiku30s\keyframes"
    candidates = sorted(
        (f for f in os.listdir(keyframe_dir) if f.startswith("sdxl_keyframe_v1_")),
        key=lambda f: os.path.getmtime(os.path.join(keyframe_dir, f)),
    )
    if not candidates:
        log("AVERTISSEMENT : keyframe v1 introuvable pour la reference IPAdapter -- bascule descendante annulee")
        return
    keyframe_ref = os.path.join(keyframe_dir, candidates[-1])
    videos = sorted(
        f for f in os.listdir(os.path.join("DEMO", "output"))
        if f.startswith("miku_demo_30s_v") and f.endswith(".mp4") and "_upscaled" not in f and "_merged" not in f
    )
    video_paths = [os.path.join("DEMO", "output", v) for v in videos]
    cmd = (
        f'"{PY}" agents/production_video/postprod_inpaint.py '
        f'--videos {" ".join(f"""{v}""" for v in video_paths)} '
        f'--keyframe-ref "{keyframe_ref}" --out-dir DEMO/postprod --order desc'
    )
    log(f"Rattrapage confirme -> bascule 5080 sur postprod (ordre decroissant, {cumulative_frames} frames dispo) : {cmd}")
    subprocess.Popen(f'start "postprod-desc-5080" cmd /k set CUDA_VISIBLE_DEVICES=0 ^& {cmd}', shell=True)


def main():
    iteration = next_run_index()
    # Semer depuis l'etat persiste, pas 0 : un redemarrage propre de ce
    # process (ex. pour recharger du code apres coordination GPU) remettait
    # sinon le compteur a zero et sous-comptait la cible 14400 frames par
    # rapport a la production reelle deja accumulee -- bug constate le
    # 2026-08-06 (log affichait "1544/14400" apres 9 iterations alors que
    # 9*772=6948 frames existaient reellement sur disque, cf. BUDGET_GPU_8H.md).
    cumulative_frames = read_gpu_progress().get("svi_frames_available", 0)
    while True:
        if os.path.exists(STOP_FLAG):
            log(f"STOP_LOOP.flag detecte -> arret propre avant iteration v{iteration}")
            write_gpu_progress(cumulative_frames, svi_loop_done=True, last_run=f"v{iteration-1}")
            break

        budget = read_gpu_budget()
        if budget["cumulative_seconds"] >= GPU_BUDGET_SECONDS:
            log(f"Budget GPU 8h atteint ({budget['cumulative_seconds']/3600:.2f}h >= "
                f"{GPU_BUDGET_SECONDS/3600:.0f}h, consignes (2).txt) -> ecriture STOP_LOOP.flag et arret")
            with open(STOP_FLAG, "w", encoding="utf-8") as f:
                f.write(f"budget GPU 8h atteint ({time.strftime('%Y-%m-%dT%H:%M:%S')})\n")
            write_gpu_progress(cumulative_frames, svi_loop_done=True, last_run=f"v{iteration-1}")
            break

        if os.path.exists(STOP_GENERATION_FLAG):
            log(f"STOP_GENERATION.flag detecte (rattrapage 5060Ti) -> fin de l'iteration en cours puis arret + bascule postprod decroissante")
            write_gpu_progress(cumulative_frames, svi_loop_done=True, last_run=f"v{iteration-1}")
            launch_descending_postprod_helper(cumulative_frames)
            break

        data = load_queue()
        used = set(data.get("used", []))
        remaining = [v for v in data.get("queue", []) if v["name"] not in used]
        if not remaining:
            log("File d'attente VMD epuisee -> fin de la boucle autonome")
            write_gpu_progress(cumulative_frames, svi_loop_done=True, last_run=f"v{iteration-1}")
            break

        vmd = remaining[0]
        run_name = f"v{iteration}"
        base_seed = BASE_SEED_START + (iteration - 2) * SEED_ITER_STEP
        log(f"=== Iteration {run_name} : VMD='{vmd['name']}' seed_base={base_seed} ===")
        iteration_t0 = time.time()

        try:
            run([PY, "DEMO/generate_keyframe.py", "--run-name", run_name,
                 "--pmx", PMX, "--vmd", vmd["path"], "--seed", str(base_seed)],
                f"keyframe-{run_name}")

            keyframe_glob_dir = r"D:\Ov3rLoRd AI\ComfyUI\output\DemoMiku30s\keyframes"
            candidates = sorted(
                (f for f in os.listdir(keyframe_glob_dir) if f.startswith(f"sdxl_keyframe_{run_name}_")),
                key=lambda f: os.path.getmtime(os.path.join(keyframe_glob_dir, f)),
            )
            if not candidates:
                raise RuntimeError(f"keyframe introuvable pour {run_name} dans {keyframe_glob_dir}")
            keyframe_path = os.path.join(keyframe_glob_dir, candidates[-1])

            run([PY, "DEMO/generate_svi_chain.py", "--run-name", run_name,
                 "--clip1-keyframe", keyframe_path, "--clip1-seed", str(base_seed),
                 "--n-clips", "7", "--vmd-used", vmd["name"]],
                f"svi-chain-{run_name}")

            # Marquer le VMD "used" des que les clips existent (avant
            # l'assemblage), pas apres : sinon un blocage/crash pendant
            # assemble_and_upscale.py (deja observe une fois, cf. hang
            # subprocess PIPE Windows du 2026-08-05) laisse le VMD non
            # marque alors qu'il a bien ete consomme -- la prochaine
            # iteration le reprendrait par erreur (bug reellement rencontre
            # sur v3, corrige manuellement dans vmd_queue.json ce jour-la).
            data = load_queue()
            data.setdefault("used", []).append(vmd["name"])
            save_queue(data)

            run([PY, "DEMO/assemble_and_upscale.py", "--run-name", run_name],
                f"assemble-{run_name}")

            final_mp4 = os.path.join("DEMO", "output", f"miku_demo_30s_{run_name}.mp4")
            cumulative_frames += probe_frame_count(final_mp4)
            write_gpu_progress(cumulative_frames, svi_loop_done=False, last_run=run_name)

            iteration_elapsed = time.time() - iteration_t0
            budget = read_gpu_budget()
            new_budget_seconds = budget["cumulative_seconds"] + iteration_elapsed
            write_gpu_budget(new_budget_seconds, last_run=run_name)

            log(f"=== Iteration {run_name} TERMINEE : {final_mp4} (cumul {cumulative_frames}/{TARGET_FRAMES} frames, "
                f"budget GPU {new_budget_seconds/3600:.2f}h/{GPU_BUDGET_SECONDS/3600:.0f}h) ===")

            if cumulative_frames >= TARGET_FRAMES:
                log(f"Cible dataset LoRA atteinte ({cumulative_frames} >= {TARGET_FRAMES} frames) -> arret de la boucle SVI")
                write_gpu_progress(cumulative_frames, svi_loop_done=True, last_run=run_name)
                break

            if new_budget_seconds >= GPU_BUDGET_SECONDS:
                log(f"Budget GPU 8h atteint ({new_budget_seconds/3600:.2f}h) apres {run_name} -> ecriture STOP_LOOP.flag et arret")
                with open(STOP_FLAG, "w", encoding="utf-8") as f:
                    f.write(f"budget GPU 8h atteint apres {run_name} ({time.strftime('%Y-%m-%dT%H:%M:%S')})\n")
                write_gpu_progress(cumulative_frames, svi_loop_done=True, last_run=run_name)
                break

        except Exception as e:
            log(f"ECHEC iteration {run_name} : {e} -- boucle interrompue (pas de retry automatique)")
            write_gpu_progress(cumulative_frames, svi_loop_done=True, last_run=f"v{iteration-1}")
            break

        iteration += 1

    log("Boucle autonome terminee (fin normale ou arret).")


if __name__ == "__main__":
    main()

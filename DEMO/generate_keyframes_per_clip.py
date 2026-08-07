"""Genere une keyframe SDXL stylisee par clip (Priorite 3, session_nuit.txt
2026-08-06/07) : reutilise les guides RGB Blender deja rendus par
agents/production_video/render_clip_guides.py (DEMO/frames/video_3min_guides/
clip_render_log.csv, 51 clips, pose+camera+sol reflechissant+eclairage 3
points) comme source img2img SDXL (meme template/prompt que
generate_keyframe.py, denoise=0.55) -- pas de nouveau rendu Blender, le guide
existe deja pour chaque clip.

Sortie : DEMO/frames/keyframes_per_clip/clip{NN}_keyframe.png, une par ligne
du CSV. Ces keyframes servent ensuite d'ancrage identite/tenue (clip_vision_
output, PAS start_image -- la continuite de mouvement reste sur la derniere
frame reelle du clip precedent, cf. CLAUDE.md) dans generate_svi_chain.py
--keyframe-anchor-dir.

Resumable : saute les clips deja rendus (fichier de sortie existant).

Usage :
    py -3.12 DEMO/generate_keyframes_per_clip.py \
        --render-log DEMO/frames/video_3min_guides/clip_render_log.csv \
        --out-dir DEMO/frames/keyframes_per_clip --base-seed 900000001
"""
import argparse
import csv
import json
import os
import shutil
import time
import urllib.request

COMFY = "http://127.0.0.1:8188"
COMFY_INPUT_DIR = r"D:\Ov3rLoRd AI\ComfyUI\input"
KEYFRAME_TEMPLATE = os.path.join("workspace", "comfyui_workflows", "sdxl_keyframe_img2img.json")
SEED_STEP = 137  # ADR-008


def queue_prompt(workflow, client_id):
    body = json.dumps({"prompt": workflow, "client_id": client_id}).encode("utf-8")
    req = urllib.request.Request(f"{COMFY}/prompt", data=body, headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.load(resp)


def wait_for_completion(prompt_id, timeout=180, poll=3):
    start = time.time()
    while time.time() - start < timeout:
        with urllib.request.urlopen(f"{COMFY}/history/{prompt_id}", timeout=30) as resp:
            hist = json.load(resp)
        if prompt_id in hist:
            entry = hist[prompt_id]
            status = entry.get("status", {})
            if status.get("completed") is True:
                return entry
            if status.get("status_str") == "error":
                raise RuntimeError(f"ComfyUI execution error: {json.dumps(status)}")
        time.sleep(poll)
    raise TimeoutError(f"prompt {prompt_id} pas termine apres {timeout}s")


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--render-log", default=os.path.join("DEMO", "frames", "video_3min_guides", "clip_render_log.csv"))
    p.add_argument("--out-dir", default=os.path.join("DEMO", "frames", "keyframes_per_clip"))
    p.add_argument("--base-seed", type=int, default=900000001)
    args = p.parse_args()

    os.makedirs(args.out_dir, exist_ok=True)
    with open(args.render_log, encoding="utf-8") as f:
        rows = list(csv.DictReader(f))

    with open(KEYFRAME_TEMPLATE, encoding="utf-8") as f:
        base_wf = json.load(f)

    log_path = os.path.join(args.out_dir, "keyframe_per_clip_log.csv")
    log_is_new = not os.path.exists(log_path)
    log_f = open(log_path, "a", newline="", encoding="utf-8")
    log_w = csv.writer(log_f)
    if log_is_new:
        log_w.writerow(["clip", "seed", "rgb_source", "keyframe_out", "elapsed_s", "status"])

    n_ok, n_skip, n_fail = 0, 0, 0
    for row in rows:
        i = int(row["clip"])
        out_path = os.path.join(args.out_dir, f"clip{i:02d}_keyframe.png")
        if os.path.exists(out_path):
            n_skip += 1
            continue

        rgb_source = row["rgb"]
        if not os.path.exists(rgb_source):
            print(f"[clip {i}] ECHEC: guide RGB introuvable {rgb_source}", flush=True)
            log_w.writerow([i, "", rgb_source, "", "", "ECHEC guide introuvable"])
            log_f.flush()
            n_fail += 1
            continue

        seed = args.base_seed + i * SEED_STEP
        comfy_input_name = f"keyframe_clip_source_{i:02d}.png"
        shutil.copy2(rgb_source, os.path.join(COMFY_INPUT_DIR, comfy_input_name))

        wf = json.loads(json.dumps(base_wf))
        wf["3"]["inputs"]["image"] = comfy_input_name
        wf["7"]["inputs"]["seed"] = seed
        wf["9"]["inputs"]["filename_prefix"] = f"DemoMiku30s/keyframes_per_clip/clip{i:02d}_keyframe"

        client_id = f"keyframe-per-clip-{i:02d}"
        t0 = time.time()
        try:
            r = queue_prompt(wf, client_id)
            if r.get("node_errors"):
                raise RuntimeError(f"node_errors: {json.dumps(r['node_errors'])}")
            entry = wait_for_completion(r["prompt_id"])
            info = entry["outputs"]["9"]["images"][0]
            src_path = info.get("fullpath") or os.path.join(
                r"D:\Ov3rLoRd AI\ComfyUI\output", info.get("subfolder", ""), info["filename"])
            shutil.copy2(src_path, out_path)
            dt = time.time() - t0
            print(f"[clip {i}/51] OK en {dt:.1f}s -> {out_path}", flush=True)
            log_w.writerow([i, seed, rgb_source, out_path, round(dt, 1), "OK"])
            n_ok += 1
        except Exception as e:
            dt = time.time() - t0
            print(f"[clip {i}/51] ECHEC apres {dt:.1f}s: {e}", flush=True)
            log_w.writerow([i, seed, rgb_source, "", round(dt, 1), f"ECHEC: {e}"])
            n_fail += 1
        log_f.flush()

    log_f.close()
    print(f"RESULT: ok={n_ok} skip(deja fait)={n_skip} echec={n_fail} -> {args.out_dir}")


if __name__ == "__main__":
    main()

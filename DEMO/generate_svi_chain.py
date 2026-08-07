"""Enchaine N clips SVI (AniSora V3.2 + Stable Video Infinity LoRA HIGH+LOW)
via l'API ComfyUI (port 8188, RTX 5080), pour produire un bloc video de
~30s a partir d'un unique clip 1 deja genere (keyframe SDXL stylisee).

Regles suivies (CLAUDE.md / DOCS/MD/TEST_SVI_04082026.md / TEST_WORKFLOW_A) :
- Ancrage du clip N+1 = derniere frame REELLE du clip N (jamais la keyframe
  SDXL d'origine).
- Seed different par clip (base_seed + (i-1)*137, convention ADR-008).
- ColorMatchV2 methode reinhard_lab_gpu, strength=0 pour le clip 1 (pas de
  reference), strength=1.0 pour les clips suivants (image_ref = derniere
  frame du clip precedent).
- Pas de refine/AnimateDiff dans cette chaine (consigne explicite : seul le
  pipeline SVI est valide pour cette demo).

Usage (depuis la racine du depot, clip 1 deja produit ailleurs) :
    py -3.12 DEMO/generate_svi_chain.py ^
        --run-name v1 ^
        --clip1-video "D:/Ov3rLoRd AI/ComfyUI/output/WorkflowA/svi_miku_clip1_00001.mp4" ^
        --clip1-seed 583920174 ^
        --n-clips 7 ^
        --camera-prompts-file DEMO/camera_prompts_v1.json ^
        --out-dir DEMO/output
"""
import argparse
import csv
import json
import os
import subprocess
import sys
import time
import urllib.request

COMFY = "http://127.0.0.1:8188"
COMFY_INPUT_DIR = r"D:\Ov3rLoRd AI\ComfyUI\input"
WORKFLOW_TEMPLATE = os.path.join("workspace", "comfyui_workflows", "anisora_svi_shot.json")
FFMPEG = r"C:\Users\Ov3rL0rD\AppData\Local\Microsoft\WinGet\Links\ffmpeg.exe"
SEED_STEP = 137  # ADR-008 : base_seed + i * 137

DEFAULT_NEGATIVE = "realistic, 3d render, blurry, deformed"
DEFAULT_BASE_PROMPT = (
    "1girl, aqua twin-tail hair, hair clip, grey headset with pink accent, "
    "grey sleeveless dress, black thigh-high boots, flexing arms muscle pose, "
    "dynamic motion, consistent character, smooth animation, white background"
)
DEFAULT_CAMERA_PROMPTS = {
    1: "camera slowly zooming in",
    2: "camera continuing to zoom in closer",
    3: "camera slowly zooming out, pulling back",
    4: "camera orbiting around the character, slow rotation",
    5: "camera continuing to orbit around the character",
    6: "close-up shot on face and upper body",
    7: "camera pulling back from close-up to a wide establishing shot",
}


def load_template():
    with open(WORKFLOW_TEMPLATE, encoding="utf-8") as f:
        return json.load(f)


def queue_prompt(workflow, client_id):
    body = json.dumps({"prompt": workflow, "client_id": client_id}).encode("utf-8")
    req = urllib.request.Request(f"{COMFY}/prompt", data=body, headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.load(resp)


def wait_for_completion(prompt_id, timeout=900, poll=5):
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


def extract_output_video(entry, node_id="18"):
    gifs = entry["outputs"][node_id]["gifs"]
    return gifs[0]["fullpath"]


def extract_last_frame(video_path, out_png_path):
    subprocess.run(
        [FFMPEG, "-y", "-sseof", "-0.2", "-i", video_path, "-update", "1", "-q:v", "2", out_png_path],
        check=True, capture_output=True, text=True,
    )


CLIP_VISION_MODEL = "model.safetensors"  # ViT-H-14, identifie par taille de fichier (session precedente)


def add_clip_vision_identity_anchor(wf, keyframe_image_name):
    """Ajoute une conditioning clip_vision (identite/tenue) a WanImageToVideo
    (node 12) SANS toucher a `start_image` (node 9, doit rester la derniere
    frame reelle du clip precedent -- continuite de mouvement, cf. CLAUDE.md).
    C'est le mecanisme natif de ce node (verifie via /object_info : entree
    optionnelle `clip_vision_output`), pas un IPAdapter -- celui-ci est
    specifique SDXL/SD1.5 et incompatible avec l'architecture WAN/Anisora.
    Corrige le changement de tenue/l'accumulation de flou sur une chaine
    longue (priorite 3, session_nuit 2026-08-06/07) en re-ancrant l'identite
    du personnage a chaque clip via sa propre keyframe SDXL, independamment
    de l'ancrage de mouvement."""
    wf["19"] = {
        "class_type": "CLIPVisionLoader",
        "inputs": {"clip_name": CLIP_VISION_MODEL},
        "_meta": {"title": "CLIPVisionLoader - ancrage identite keyframe par clip"},
    }
    wf["20"] = {
        "class_type": "LoadImage",
        "inputs": {"image": keyframe_image_name},
        "_meta": {"title": "LoadImage - keyframe SDXL du clip (identite/tenue)"},
    }
    wf["21"] = {
        "class_type": "CLIPVisionEncode",
        "inputs": {"clip_vision": ["19", 0], "image": ["20", 0], "crop": "center"},
        "_meta": {"title": "CLIPVisionEncode"},
    }
    wf["12"]["inputs"]["clip_vision_output"] = ["21", 0]


def run_clip(i, anchor_image_name, colormatch_ref_name, colormatch_strength, seed,
             positive_text, filename_prefix, client_id, keyframe_image_name=None):
    wf = load_template()
    wf["9"]["inputs"]["image"] = anchor_image_name
    wf["16"]["inputs"]["image"] = colormatch_ref_name
    wf["17"]["inputs"]["strength"] = colormatch_strength
    wf["10"]["inputs"]["text"] = positive_text
    wf["11"]["inputs"]["text"] = DEFAULT_NEGATIVE
    wf["13"]["inputs"]["noise_seed"] = seed
    wf["14"]["inputs"]["noise_seed"] = seed
    wf["18"]["inputs"]["filename_prefix"] = filename_prefix
    if keyframe_image_name:
        add_clip_vision_identity_anchor(wf, keyframe_image_name)

    r = queue_prompt(wf, client_id)
    if r.get("node_errors"):
        raise RuntimeError(f"node_errors clip {i}: {json.dumps(r['node_errors'])}")
    prompt_id = r["prompt_id"]
    t0 = time.time()
    entry = wait_for_completion(prompt_id)
    dt = time.time() - t0
    video_path = extract_output_video(entry)
    return video_path, dt


def parse_args():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--run-name", required=True, help="Identifiant du bloc 30s (ex: v1, v2...)")
    p.add_argument("--clip1-video", default=None, help="Chemin du clip 1 deja genere (mp4). Omis si --clip1-keyframe fourni (clip 1 sera genere).")
    p.add_argument("--clip1-keyframe", default=None, help="Chemin d'une keyframe SDXL stylisee (image) : genere le clip 1 via SVI (ColorMatch bypass) avant la chaine")
    p.add_argument("--clip1-seed", type=int, required=True)
    p.add_argument("--n-clips", type=int, default=7)
    p.add_argument("--base-prompt", default=DEFAULT_BASE_PROMPT)
    p.add_argument("--camera-prompts-file", default=None, help="JSON {clip_index: phrase} optionnel (sinon defaut interne)")
    p.add_argument("--out-dir", default=os.path.join("DEMO", "output"))
    p.add_argument("--vmd-used", default="", help="Nom du VMD utilise (documentation/log uniquement)")
    p.add_argument("--keyframe-anchor-dir", default=None,
                    help="Dossier de keyframes SDXL par clip (clipNN_keyframe.png, cf. "
                         "generate_keyframes_per_clip.py) : si fourni, chaque clip i>=2 recoit un "
                         "ancrage identite/tenue clip_vision (n'affecte pas start_image/continuite "
                         "de mouvement). Clip absent -> pas d'ancrage pour ce clip (pas d'erreur).")
    return p.parse_args()


def main():
    args = parse_args()
    client_id = f"demo30s-{args.run_name}"

    camera_prompts = dict(DEFAULT_CAMERA_PROMPTS)
    if args.camera_prompts_file:
        with open(args.camera_prompts_file, encoding="utf-8") as f:
            camera_prompts.update({int(k): v for k, v in json.load(f).items()})

    os.makedirs(args.out_dir, exist_ok=True)
    log_path = os.path.join(args.out_dir, "generation_log.csv")
    log_is_new = not os.path.exists(log_path)
    log_f = open(log_path, "a", newline="", encoding="utf-8")
    log_w = csv.writer(log_f)
    if log_is_new:
        log_w.writerow(["run_name", "clip", "seed", "camera_prompt", "vmd_used", "video_path", "elapsed_s", "timestamp_iso"])

    import shutil

    if not args.clip1_video:
        if not args.clip1_keyframe:
            raise ValueError("fournir --clip1-video (existant) ou --clip1-keyframe (a generer)")
        keyframe_name = f"clip1_keyframe_{args.run_name}.png"
        shutil.copy2(args.clip1_keyframe, os.path.join(COMFY_INPUT_DIR, keyframe_name))
        cam_phrase_1 = camera_prompts.get(1, "")
        positive_1 = f"{args.base_prompt}, {cam_phrase_1}" if cam_phrase_1 else args.base_prompt
        prefix_1 = f"DemoMiku30s/{args.run_name}/svi_chain_{args.run_name}_clip1"
        print(f"[clip 1/{args.n_clips}] generation depuis keyframe {keyframe_name} (seed={args.clip1_seed})", flush=True)
        video_path_1, dt1 = run_clip(
            1, keyframe_name, keyframe_name, 0.0, args.clip1_seed, positive_1, prefix_1, client_id,
        )
        print(f"[clip 1/{args.n_clips}] OK en {dt1:.1f}s -> {video_path_1}", flush=True)
        args.clip1_video = video_path_1
        log_w.writerow([args.run_name, 1, args.clip1_seed, cam_phrase_1, args.vmd_used, video_path_1, round(dt1, 1), time.strftime("%Y-%m-%dT%H:%M:%S")])
        log_f.flush()
    else:
        log_w.writerow([args.run_name, 1, args.clip1_seed, camera_prompts.get(1, ""), args.vmd_used, os.path.abspath(args.clip1_video), "", time.strftime("%Y-%m-%dT%H:%M:%S")])
        log_f.flush()

    clip_videos = {1: os.path.abspath(args.clip1_video)}
    last_frame_png = os.path.join(args.out_dir, f"svi_{args.run_name}_clip1_last.png")
    extract_last_frame(clip_videos[1], last_frame_png)
    anchor_name = f"svi_{args.run_name}_clip1_last.png"
    shutil.copy2(last_frame_png, os.path.join(COMFY_INPUT_DIR, anchor_name))

    for i in range(2, args.n_clips + 1):
        seed = args.clip1_seed + (i - 1) * SEED_STEP
        cam_phrase = camera_prompts.get(i, "")
        positive_text = f"{args.base_prompt}, {cam_phrase}" if cam_phrase else args.base_prompt
        prefix = f"DemoMiku30s/{args.run_name}/svi_chain_{args.run_name}_clip{i}"

        keyframe_image_name = None
        if args.keyframe_anchor_dir:
            keyframe_src = os.path.join(args.keyframe_anchor_dir, f"clip{i:02d}_keyframe.png")
            if os.path.exists(keyframe_src):
                keyframe_image_name = f"clip_keyframe_{args.run_name}_{i:02d}.png"
                shutil.copy2(keyframe_src, os.path.join(COMFY_INPUT_DIR, keyframe_image_name))
            else:
                print(f"[clip {i}/{args.n_clips}] AVERTISSEMENT: pas de keyframe ancrage ({keyframe_src} absent)", flush=True)

        print(f"[clip {i}/{args.n_clips}] seed={seed} cam='{cam_phrase}' anchor={anchor_name} "
              f"identity_keyframe={keyframe_image_name or '(aucune)'}", flush=True)
        video_path, dt = run_clip(
            i, anchor_name, anchor_name, 1.0, seed, positive_text, prefix, client_id,
            keyframe_image_name=keyframe_image_name,
        )
        print(f"[clip {i}/{args.n_clips}] OK en {dt:.1f}s -> {video_path}", flush=True)
        clip_videos[i] = video_path

        log_w.writerow([args.run_name, i, seed, cam_phrase, args.vmd_used, video_path, round(dt, 1), time.strftime("%Y-%m-%dT%H:%M:%S")])
        log_f.flush()

        if i < args.n_clips:
            last_frame_png = os.path.join(args.out_dir, f"svi_{args.run_name}_clip{i}_last.png")
            extract_last_frame(video_path, last_frame_png)
            anchor_name = f"svi_{args.run_name}_clip{i}_last.png"
            shutil.copy2(last_frame_png, os.path.join(COMFY_INPUT_DIR, anchor_name))

    log_f.close()

    manifest_path = os.path.join(args.out_dir, f"svi_{args.run_name}_clip_manifest.json")
    with open(manifest_path, "w", encoding="utf-8") as f:
        json.dump({str(k): v for k, v in clip_videos.items()}, f, ensure_ascii=False, indent=2)
    print(f"RESULT: {len(clip_videos)} clips -> manifest {manifest_path}")


if __name__ == "__main__":
    main()

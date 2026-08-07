"""Pipeline de post-production frame par frame (consignes.txt 2026-08-06) :

    v1/v2/v3... MP4 24fps
      -> extraction frames PNG (ffmpeg)
      -> background removal (easy imageRemBg / BEN2, ComfyUI) + recomposition
         fond blanc immediate (corrige le blanc des yeux contamine)
      -> HandSegNet (YOLO hand_yolov9c + SAM vit_b fine-tune) -> masque mains
      -> FootSegNet (DWPose + SAM vit_b fine-tune) -> masque pieds
      -> inpaint ComfyUI (VAEEncodeForInpaint + IPAdapterAdvanced, image de
         reference = keyframe stylisee de l'iteration) sur chaque zone
      -> hi-res fix 2K (UltimateSDUpscale, upscale_by=1.5, meme reglages que
         la branche hires deja validee dans Advanced_QwenVL_V35_ORIGINAL.json)
      -> sauvegarde PNG corrige
      -> reassemblage MP4 final (ffmpeg, 24fps)

Tourne sur RTX 5060 Ti (CUDA_VISIBLE_DEVICES=1) via une 2e instance ComfyUI
dediee (port 8189, cf. _launch_comfyui_5060ti.bat) pendant que la RTX 5080
(port 8188) continue la generation SVI en parallele (run_demo_loop.py).

Usage (extrait un run) :
    set CUDA_VISIBLE_DEVICES=1
    py -3.12 agents/production_video/postprod_inpaint.py ^
        --videos DEMO/output/miku_demo_30s_v1_fixed.mp4 DEMO/output/miku_demo_30s_v2.mp4 ^
        --keyframe-ref "D:\\Ov3rLoRd AI\\ComfyUI\\output\\DemoMiku30s\\keyframes\\sdxl_keyframe_v1_00001_.png" ^
        --out-dir DEMO/postprod --order asc

Voir DOCS/MD/POSTPROD_PIPELINE_20260806.md pour l'architecture complete et
les limites connues (cout GPU par frame, portee du tag lora_priority).
"""
import argparse
import csv
import json
import os
import shutil
import subprocess
import sys
import time
import urllib.request

os.environ.setdefault("CUDA_VISIBLE_DEVICES", "1")  # RTX 5060 Ti -- cf. consignes.txt regle GPU

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

import numpy as np
from PIL import Image

COMFY = "http://127.0.0.1:8189"  # instance dediee RTX 5060 Ti (cf. _launch_comfyui_5060ti.bat)
COMFY_INPUT_DIR = r"D:\Ov3rLoRd AI\ComfyUI\input"
COMFY_OUTPUT_DIR = r"D:\Ov3rLoRd AI\ComfyUI\output"
FFMPEG = r"C:\Users\Ov3rL0rD\AppData\Local\Microsoft\WinGet\Links\ffmpeg.exe"
FFPROBE = r"C:\Users\Ov3rL0rD\AppData\Local\Microsoft\WinGet\Links\ffprobe.exe"

CHECKPOINT = "fabricatedXL_v70.safetensors"
VAE_NAME = "taesdxl"  # ADR-002 : sdxl_vae reel corrompu, taesdxl en usage courant
IPADAPTER_FILE = "ip-adapter-plus_sdxl_vit-h.safetensors"
CLIP_VISION_FILE = "model.safetensors"  # ViT-H, valide dans animatediff_32frames_style_anchor.json
UPSCALE_MODEL = "4x_foolhardy_Remacri.pth"

INPAINT_STEPS, INPAINT_CFG, INPAINT_DENOISE = 25, 6.0, 0.90
INPAINT_SAMPLER, INPAINT_SCHEDULER = "dpmpp_2m", "karras"
# denoise=0.90 (pas 0.45 comme dans inpaint_corrector.py) : VAEEncodeForInpaint
# efface (met a gris 0.5) la zone masquee avant encodage -- il n'y a donc pas
# de structure existante a "preserver" a faible denoise, contrairement a un
# img2img classique. A 0.45, confirme empiriquement le 2026-08-06 : la zone
# reste un aplat gris quasi vide (pas assez de pas de debruitage pour faire
# emerger un motif), cf. DOCS/MD/POSTPROD_PIPELINE_20260806.md section 5.

HIRES_UPSCALE_BY = 1.5
HIRES_STEPS, HIRES_CFG, HIRES_DENOISE = 18, 6.0, 0.16
HIRES_SAMPLER, HIRES_SCHEDULER = "dpmpp_2m_sde", "karras"  # meme reglages que la branche
# hires deja validee dans Advanced_QwenVL_V35_ORIGINAL.json (UltimateSDUpscale id=128/132)

STOP_GENERATION_FLAG = os.path.join("DEMO", "STOP_GENERATION.flag")
GPU_PROGRESS_FILE = os.path.join("DEMO", "output", "gpu_progress.json")
POSTPROD_LOG = os.path.join("DEMO", "output", "postprod_log.csv")

HAND_POS_PROMPT = "hatsune miku, perfect hand, five fingers, correct anatomy, detailed hand, anime style"
HAND_NEG_PROMPT = "worst quality, blurry, deformed hand, extra fingers, missing fingers, fused fingers, mutated hand, bad anatomy"
FOOT_POS_PROMPT = "hatsune miku, perfect foot, black boots, correct anatomy, anime style"
FOOT_NEG_PROMPT = "worst quality, blurry, deformed feet, extra toes, mutated feet, bad anatomy"
HIRES_POS_PROMPT = "masterpiece, best quality, anime style, detailed"
HIRES_NEG_PROMPT = "worst quality, low quality, blurry, jpeg artifacts"


# ── Helpers ComfyUI (instance 8189 dediee -- copie locale volontaire, meme
# convention que generate_svi_chain.py / assemble_and_upscale.py qui ont
# chacun leur propre copie plutot qu'une dependance partagee) ──────────────

def _queue_prompt(workflow, client_id):
    body = json.dumps({"prompt": workflow, "client_id": client_id}).encode("utf-8")
    req = urllib.request.Request(f"{COMFY}/prompt", data=body, headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.load(resp)


def _wait_for_completion(prompt_id, timeout=300, poll=2):
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


def _resolve_output_path(out_node, key_candidates=("images", "videos", "gifs")):
    key = next(k for k in key_candidates if k in out_node)
    info = out_node[key][0]
    if "fullpath" in info:
        return info["fullpath"]
    return os.path.join(COMFY_OUTPUT_DIR, info.get("subfolder", ""), info["filename"])


def _run_graph(wf, client_id, save_node_id, timeout=300):
    r = _queue_prompt(wf, client_id)
    if r.get("node_errors"):
        raise RuntimeError(f"node_errors ({client_id}): {json.dumps(r['node_errors'])}")
    entry = _wait_for_completion(r["prompt_id"], timeout=timeout)
    return _resolve_output_path(entry["outputs"][save_node_id])


def _upload(local_path, comfy_name):
    shutil.copy2(local_path, os.path.join(COMFY_INPUT_DIR, comfy_name))
    return comfy_name


# ── Etape 1 : extraction frames ─────────────────────────────────────────────

def extract_all_frames(video_path, out_dir, start_index):
    """Extrait toutes les frames de video_path en PNG numerotees a partir de
    start_index (numerotation globale continue sur plusieurs videos concatenees)."""
    os.makedirs(out_dir, exist_ok=True)
    r = subprocess.run(
        [FFPROBE, "-v", "error", "-count_frames", "-select_streams", "v:0",
         "-show_entries", "stream=nb_read_frames", "-of", "csv=p=0", video_path],
        check=True, capture_output=True, text=True,
    )
    n = int(r.stdout.strip())
    tmp_pattern = os.path.join(out_dir, "_extract_%06d.png")
    subprocess.run([FFMPEG, "-y", "-i", video_path, tmp_pattern], check=True, capture_output=True, text=True)
    for i in range(1, n + 1):
        src = os.path.join(out_dir, f"_extract_{i:06d}.png")
        dst = os.path.join(out_dir, f"frame_{start_index + i - 1:06d}.png")
        os.replace(src, dst)
    return n


# ── Etape 2 : background removal + recomposition fond blanc ────────────────

def remove_background_white(frame_path, frame_id, client_id_prefix):
    comfy_name = _upload(frame_path, f"postprod_raw_{frame_id:06d}.png")
    wf = {
        "1": {"class_type": "LoadImage", "inputs": {"image": comfy_name}},
        "2": {"class_type": "easy imageRemBg", "inputs": {
            "images": ["1", 0], "rem_mode": "BEN2", "image_output": "Hide",
            "save_prefix": "postprod", "torchscript_jit": False,
            "add_background": "white", "refine_foreground": True,
        }},
        "3": {"class_type": "SaveImage", "inputs": {
            "images": ["2", 0], "filename_prefix": "DemoMiku30s/postprod/bgclean",
        }},
    }
    return _run_graph(wf, f"{client_id_prefix}-bgclean", "3")


# ── Etape 3/4 : masques HandSegNet / FootSegNet ─────────────────────────────

def get_hand_mask(frame_path, frame_id, out_dir):
    from handsegnet._hand_box import hand_box_for_image
    from handsegnet.infer import generate_part_mask

    boxes = hand_box_for_image(frame_path)
    if not boxes:
        return None, None
    mask_paths, scores = [], []
    for i, box in enumerate(boxes):
        out_path = os.path.join(out_dir, f"frame_{frame_id:06d}_handmask{i}.png")
        # pipeline_convention=False : BLANC=objet/zone a regenerer (convention
        # ML), pas la convention pipeline (NOIR=regenerer) par defaut de ce
        # module -- VAEEncodeForInpaint de ComfyUI (nodes_mask.py) fait
        # `m = 1 - mask.round()` puis preserve les pixels ou m=1 (mask=0) et
        # les efface (mis a 0.5 gris avant encodage) ou m=0 (mask=1) : il
        # attend donc BLANC=effacer/regenerer, l'oppose de la convention
        # pipeline. Confirme empiriquement le 2026-08-06 : la 1ere version
        # (pipeline_convention=True par defaut) effacait tout SAUF la petite
        # zone masquee (bug trouve sur le test frame 0, cf.
        # DOCS/MD/POSTPROD_PIPELINE_20260806.md section 5).
        result = generate_part_mask(frame_path, zone=box, output_path=out_path, part="hand",
                                     pipeline_convention=False, return_score=True)
        if result:
            mask_paths.append(result[0])
            scores.append(result[1])
    if not mask_paths:
        return None, None
    combined = mask_paths[0]
    if len(mask_paths) > 1:
        combined = os.path.join(out_dir, f"frame_{frame_id:06d}_handmask_combined.png")
        arrs = [np.array(Image.open(p).convert("L")) for p in mask_paths]
        merged = np.maximum.reduce(arrs)  # 255=regenerer domine (convention ML, cf. note ci-dessus)
        Image.fromarray(merged).save(combined)
    return combined, min(scores)


def get_foot_mask(frame_path, frame_id, out_dir):
    import agents.production_video.pose_generator as pose_gen_mod
    pose_gen_mod.COMFY_URL = COMFY  # DWPose sur l'instance 8189, pas 8188 (regle GPU postprod)
    from footsegnet._pose_box import foot_box_for_image
    from footsegnet.infer import generate_foot_mask

    box = foot_box_for_image(frame_path)
    if not box:
        return None, None
    out_path = os.path.join(out_dir, f"frame_{frame_id:06d}_footmask.png")
    # pipeline_convention=False : voir note dans get_hand_mask ci-dessus.
    result = generate_foot_mask(frame_path, zone=box, output_path=out_path,
                                 pipeline_convention=False, return_score=True)
    if not result:
        return None, None
    return result


# ── Etape 5 : inpaint IPAdapter (une zone a la fois) ────────────────────────

def inpaint_zone(frame_path, mask_path, keyframe_ref_name, positive, negative, seed, frame_id, zone_label, client_id_prefix):
    frame_name = _upload(frame_path, f"postprod_inpaintsrc_{frame_id:06d}_{zone_label}.png")
    mask_name = _upload(mask_path, f"postprod_mask_{frame_id:06d}_{zone_label}.png")
    wf = {
        "1": {"class_type": "CheckpointLoaderSimple", "inputs": {"ckpt_name": CHECKPOINT}},
        "2": {"class_type": "VAELoader", "inputs": {"vae_name": VAE_NAME}},
        "3": {"class_type": "LoadImage", "inputs": {"image": frame_name}},
        "4": {"class_type": "LoadImage", "inputs": {"image": mask_name}},
        "4b": {"class_type": "ImageToMask", "inputs": {"image": ["4", 0], "channel": "red"}},
        "5": {"class_type": "VAEEncodeForInpaint", "inputs": {
            "pixels": ["3", 0], "vae": ["2", 0], "mask": ["4b", 0], "grow_mask_by": 0,
        }},
        "6": {"class_type": "IPAdapterModelLoader", "inputs": {"ipadapter_file": IPADAPTER_FILE}},
        "7": {"class_type": "CLIPVisionLoader", "inputs": {"clip_name": CLIP_VISION_FILE}},
        "8": {"class_type": "LoadImage", "inputs": {"image": keyframe_ref_name}},
        "9": {"class_type": "PrepImageForClipVision", "inputs": {
            "image": ["8", 0], "interpolation": "LANCZOS", "crop_position": "pad", "sharpening": 0.0,
        }},
        "10": {"class_type": "IPAdapterAdvanced", "inputs": {
            "model": ["1", 0], "ipadapter": ["6", 0], "image": ["9", 0], "clip_vision": ["7", 0],
            "weight": 0.75, "weight_type": "linear", "combine_embeds": "concat",
            "start_at": 0.0, "end_at": 0.6, "embeds_scaling": "K+V", "attn_mask": ["4b", 0],
        }},
        "11": {"class_type": "CLIPTextEncode", "inputs": {"text": positive, "clip": ["1", 1]}},
        "12": {"class_type": "CLIPTextEncode", "inputs": {"text": negative, "clip": ["1", 1]}},
        "13": {"class_type": "KSampler", "inputs": {
            "model": ["10", 0], "positive": ["11", 0], "negative": ["12", 0], "latent_image": ["5", 0],
            "seed": seed, "steps": INPAINT_STEPS, "cfg": INPAINT_CFG,
            "sampler_name": INPAINT_SAMPLER, "scheduler": INPAINT_SCHEDULER, "denoise": INPAINT_DENOISE,
        }},
        "14": {"class_type": "VAEDecode", "inputs": {"samples": ["13", 0], "vae": ["2", 0]}},
        "15": {"class_type": "SaveImage", "inputs": {
            "images": ["14", 0], "filename_prefix": f"DemoMiku30s/postprod/inpaint_{zone_label}",
        }},
    }
    return _run_graph(wf, f"{client_id_prefix}-inpaint-{zone_label}", "15")


# ── Etape 6 : hi-res fix 2K (UltimateSDUpscale) ─────────────────────────────

def hires_fix_2k(frame_path, seed, frame_id, client_id_prefix):
    frame_name = _upload(frame_path, f"postprod_hiressrc_{frame_id:06d}.png")
    wf = {
        "1": {"class_type": "CheckpointLoaderSimple", "inputs": {"ckpt_name": CHECKPOINT}},
        "2": {"class_type": "VAELoader", "inputs": {"vae_name": VAE_NAME}},
        "3": {"class_type": "LoadImage", "inputs": {"image": frame_name}},
        "4": {"class_type": "UpscaleModelLoader", "inputs": {"model_name": UPSCALE_MODEL}},
        "5": {"class_type": "CLIPTextEncode", "inputs": {"text": HIRES_POS_PROMPT, "clip": ["1", 1]}},
        "6": {"class_type": "CLIPTextEncode", "inputs": {"text": HIRES_NEG_PROMPT, "clip": ["1", 1]}},
        "7": {"class_type": "UltimateSDUpscale", "inputs": {
            "image": ["3", 0], "model": ["1", 0], "positive": ["5", 0], "negative": ["6", 0], "vae": ["2", 0],
            "upscale_model": ["4", 0], "upscale_by": HIRES_UPSCALE_BY,
            "seed": seed, "steps": HIRES_STEPS, "cfg": HIRES_CFG,
            "sampler_name": HIRES_SAMPLER, "scheduler": HIRES_SCHEDULER, "denoise": HIRES_DENOISE,
            "mode_type": "Linear", "tile_width": 512, "tile_height": 512,
            "mask_blur": 16, "tile_padding": 64,
            "seam_fix_mode": "Half Tile + Intersections", "seam_fix_denoise": 1.0,
            "seam_fix_width": 64, "seam_fix_mask_blur": 8, "seam_fix_padding": 16,
            "force_uniform_tiles": True, "tiled_decode": False, "batch_size": 1,
        }},
        "8": {"class_type": "SaveImage", "inputs": {
            "images": ["7", 0], "filename_prefix": "DemoMiku30s/postprod/hires2k",
        }},
    }
    return _run_graph(wf, f"{client_id_prefix}-hires", "8", timeout=600)


# ── Boucle par frame ─────────────────────────────────────────────────────────

def process_frame(frame_id, raw_frame_path, keyframe_ref_name, out_dir, work_dir):
    t0 = time.time()
    client_id_prefix = f"postprod-f{frame_id:06d}"
    seed = 900000000 + frame_id

    clean_path_comfy = remove_background_white(raw_frame_path, frame_id, client_id_prefix)
    clean_path = os.path.join(work_dir, f"frame_{frame_id:06d}_clean.png")
    shutil.copy2(clean_path_comfy, clean_path)

    hand_mask, hand_score = get_hand_mask(clean_path, frame_id, work_dir)
    foot_mask, foot_score = get_foot_mask(clean_path, frame_id, work_dir)

    current_path = clean_path
    inpaint_applied = False
    if hand_mask:
        result = inpaint_zone(current_path, hand_mask, keyframe_ref_name, HAND_POS_PROMPT, HAND_NEG_PROMPT,
                               seed, frame_id, "hand", client_id_prefix)
        current_path = os.path.join(work_dir, f"frame_{frame_id:06d}_afterhand.png")
        shutil.copy2(result, current_path)
        inpaint_applied = True
    if foot_mask:
        result = inpaint_zone(current_path, foot_mask, keyframe_ref_name, FOOT_POS_PROMPT, FOOT_NEG_PROMPT,
                               seed + 1, frame_id, "foot", client_id_prefix)
        current_path = os.path.join(work_dir, f"frame_{frame_id:06d}_afterfoot.png")
        shutil.copy2(result, current_path)
        inpaint_applied = True

    hires_result = hires_fix_2k(current_path, seed + 2, frame_id, client_id_prefix)
    final_path = os.path.join(out_dir, f"frame_{frame_id:06d}.png")
    os.makedirs(out_dir, exist_ok=True)
    shutil.copy2(hires_result, final_path)

    elapsed = time.time() - t0
    return {
        "frame": frame_id,
        "hand_score": f"{hand_score:.3f}" if hand_score is not None else "",
        "foot_score": f"{foot_score:.3f}" if foot_score is not None else "",
        "inpaint_applied": inpaint_applied,
        "lora_priority": False,
        "elapsed_s": f"{elapsed:.1f}",
        "final_path": final_path,
    }


# ── Log CSV (append, idempotent) ────────────────────────────────────────────

CSV_FIELDS = ["frame", "hand_score", "foot_score", "inpaint_applied", "lora_priority", "elapsed_s", "final_path"]


def load_processed_frames(log_path):
    if not os.path.exists(log_path):
        return set()
    with open(log_path, encoding="utf-8") as f:
        return {int(row["frame"]) for row in csv.DictReader(f)}


def append_log_row(log_path, row):
    exists = os.path.exists(log_path)
    os.makedirs(os.path.dirname(log_path), exist_ok=True)
    with open(log_path, "a", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=CSV_FIELDS)
        if not exists:
            w.writeheader()
        w.writerow(row)


# ── Coordination GPU (rattrapage 5060Ti / 5080) ─────────────────────────────

def read_gpu_progress():
    if not os.path.exists(GPU_PROGRESS_FILE):
        return {"svi_frames_available": 0, "svi_loop_done": False}
    with open(GPU_PROGRESS_FILE, encoding="utf-8") as f:
        return json.load(f)


def check_catchup_and_flag(next_frame_idx):
    """Retourne True si la 5060 Ti a rattrape la 5080 (plus de frame
    disponible a traiter et generation toujours en cours) -- ecrit alors
    STOP_GENERATION.flag (consigne : la 5080 termine son clip en cours puis
    bascule sur le pipeline inpaint en ordre decroissant)."""
    progress = read_gpu_progress()
    if progress.get("svi_loop_done"):
        return False  # generation terminee, pas de rattrapage a signaler : il reste juste du travail solo
    if next_frame_idx >= progress.get("svi_frames_available", 0):
        if not os.path.exists(STOP_GENERATION_FLAG):
            os.makedirs(os.path.dirname(STOP_GENERATION_FLAG), exist_ok=True)
            with open(STOP_GENERATION_FLAG, "w", encoding="utf-8") as f:
                f.write(f"rattrapage 5060Ti->5080 a la frame {next_frame_idx} ({time.strftime('%Y-%m-%dT%H:%M:%S')})\n")
            print(f"[postprod] RATTRAPAGE detecte a la frame {next_frame_idx} -> {STOP_GENERATION_FLAG} ecrit", flush=True)
        return True
    return False


# ── Decouverte dynamique de nouvelles iterations (mode asc uniquement) ─────
# La boucle SVI (run_demo_loop.py) produit v1_fixed, v2, v3, ... au fil de
# l'eau -- le worker ascendant doit les integrer des qu'elles apparaissent,
# pas seulement traiter la liste --videos donnee au lancement (sinon la
# notion de "rattrapage" ne veut rien dire : il faut un flux continu en face).

import re

_VIDEO_RE = re.compile(r"^miku_demo_30s_v(\d+)(_fixed)?\.mp4$")


def _video_sort_key(name):
    m = _VIDEO_RE.match(name)
    return int(m.group(1)) if m else -1


def discover_new_videos(out_output_dir, already_known_names):
    """Scanne DEMO/output pour miku_demo_30s_v{N}[_fixed].mp4 pas encore
    connus, tries par N croissant. Exclut les fichiers intermediaires
    (_merged, _upscaled_8fps)."""
    if not os.path.isdir(out_output_dir):
        return []
    found = []
    for f in os.listdir(out_output_dir):
        if _VIDEO_RE.match(f) and f not in already_known_names:
            found.append(f)
    return sorted(found, key=_video_sort_key)


# ── Reassemblage MP4 ─────────────────────────────────────────────────────────

def reassemble_video(frames_dir, out_path, fps=24):
    pattern = os.path.join(frames_dir, "frame_%06d.png")
    subprocess.run(
        [FFMPEG, "-y", "-framerate", str(fps), "-start_number", "0", "-i", pattern,
         "-c:v", "libx264", "-pix_fmt", "yuv420p", "-crf", "18", out_path],
        check=True, capture_output=True, text=True,
    )


# ── Main ──────────────────────────────────────────────────────────────────

def main():
    p = argparse.ArgumentParser()
    p.add_argument("--videos", nargs="+", required=True,
                    help="MP4 24fps sources connues au demarrage, dans l'ordre (v1_fixed, v2, ...)")
    p.add_argument("--keyframe-ref", required=True, help="Image de reference identite (keyframe SDXL stylisee)")
    p.add_argument("--out-dir", default=os.path.join("DEMO", "postprod"))
    p.add_argument("--order", choices=["asc", "desc"], default="asc")
    p.add_argument("--limit", type=int, default=None, help="Nombre max de frames a traiter cette execution")
    p.add_argument("--poll-wait-s", type=int, default=30, help="Attente entre polls si rattrapage/pas de nouvelle video (ordre asc)")
    p.add_argument("--no-watch", action="store_true",
                    help="Desactive la decouverte dynamique de nouvelles videos (ordre asc) -- traite uniquement --videos")
    p.add_argument("--videos-dir", default=os.path.join("DEMO", "output"), help="Dossier scanne pour la decouverte dynamique")
    p.add_argument("--start-frame", type=int, default=None,
                    help="Frame globale de depart (index dans --videos concatenes) -- pour cibler un clip precis "
                         "(ex. candidat lora_priority) sans traiter tout depuis 0. Implique --no-watch.")
    p.add_argument("--end-frame", type=int, default=None,
                    help="Frame globale de fin (incluse) -- avec --start-frame, traite uniquement [start,end].")
    args = p.parse_args()
    if args.start_frame is not None:
        args.no_watch = True

    frames_raw_dir = os.path.join(args.out_dir, "_raw_frames")
    work_dir = os.path.join(args.out_dir, "_work")
    final_dir = os.path.join(args.out_dir, "frames_final")
    os.makedirs(work_dir, exist_ok=True)

    print(f"[postprod] extraction frames depuis {len(args.videos)} video(s) initiale(s)...", flush=True)
    known_video_names = set()
    total = 0
    for v in args.videos:
        n = extract_all_frames(v, frames_raw_dir, start_index=total)
        print(f"[postprod] {v} -> {n} frames (indices {total}..{total+n-1})", flush=True)
        known_video_names.add(os.path.basename(v))
        total += n

    keyframe_ref_name = _upload(args.keyframe_ref, "postprod_identity_ref.png")
    processed = load_processed_frames(POSTPROD_LOG)
    n_done_this_run = 0

    if args.order == "desc":
        # Instantane fixe : invoque une seule fois APRES l'arret de la
        # generation SVI (cf. launch_descending_postprod_helper), pas de
        # decouverte dynamique necessaire.
        cursor = total - 1
        while cursor >= 0:
            if args.limit is not None and n_done_this_run >= args.limit:
                print(f"[postprod] limite --limit={args.limit} atteinte, arret propre", flush=True)
                break
            if cursor not in processed:
                raw_path = os.path.join(frames_raw_dir, f"frame_{cursor:06d}.png")
                if os.path.exists(raw_path):
                    row = process_frame(cursor, raw_path, keyframe_ref_name, final_dir, work_dir)
                    append_log_row(POSTPROD_LOG, row)
                    processed.add(cursor)
                    n_done_this_run += 1
                    print(f"[postprod] RESULT frame {row['frame']}: hand={row['hand_score']} foot={row['foot_score']} "
                          f"inpaint={row['inpaint_applied']} {row['elapsed_s']}s", flush=True)
            cursor -= 1
        print(f"[postprod] {n_done_this_run} frame(s) traitee(s) cette execution (ordre decroissant).", flush=True)
        return

    # Ordre ascendant : curseur mobile, poll pour nouvelles videos/rattrapage.
    cursor = args.start_frame if args.start_frame is not None else 0
    while True:
        if args.end_frame is not None and cursor > args.end_frame:
            print(f"[postprod] --end-frame={args.end_frame} atteint, arret propre", flush=True)
            break
        if args.limit is not None and n_done_this_run >= args.limit:
            print(f"[postprod] limite --limit={args.limit} atteinte, arret propre", flush=True)
            break
        if cursor in processed:
            cursor += 1
            continue

        if cursor >= total:
            if not args.no_watch:
                new_videos = discover_new_videos(args.videos_dir, known_video_names)
                for v in new_videos:
                    vpath = os.path.join(args.videos_dir, v)
                    n = extract_all_frames(vpath, frames_raw_dir, start_index=total)
                    print(f"[postprod] nouvelle video decouverte : {v} -> {n} frames (indices {total}..{total+n-1})", flush=True)
                    known_video_names.add(v)
                    total += n
            if cursor >= total:
                progress = read_gpu_progress()
                if progress.get("svi_loop_done") and not (not args.no_watch and discover_new_videos(args.videos_dir, known_video_names)):
                    print(f"[postprod] plus de frame a traiter et generation SVI terminee -> fin", flush=True)
                    break
                check_catchup_and_flag(cursor)
                print(f"[postprod] en attente de nouvelles frames (poll {args.poll_wait_s}s)...", flush=True)
                time.sleep(args.poll_wait_s)
                continue

        raw_path = os.path.join(frames_raw_dir, f"frame_{cursor:06d}.png")
        if not os.path.exists(raw_path):
            print(f"[postprod] frame {cursor} pas encore extraite -- skip pour l'instant", flush=True)
            cursor += 1
            continue

        row = process_frame(cursor, raw_path, keyframe_ref_name, final_dir, work_dir)
        append_log_row(POSTPROD_LOG, row)
        processed.add(cursor)
        n_done_this_run += 1
        print(f"[postprod] RESULT frame {row['frame']}: hand={row['hand_score']} foot={row['foot_score']} "
              f"inpaint={row['inpaint_applied']} {row['elapsed_s']}s", flush=True)
        cursor += 1

    print(f"[postprod] {n_done_this_run} frame(s) traitee(s) cette execution.", flush=True)


if __name__ == "__main__":
    main()

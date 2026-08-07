"""Fonctions partagees pour l'upscale SeedVR2 segmente (<=64 frames/passe).

Regle etablie 2026-08-06 (verdict Jerreemy, DOCS/MD/DEMO_30S_MIKU_20260806.md) :
SeedVR2 degrade visuellement au-dela de ~8s (64 frames @ 8fps) traitees en un
seul passage -- meme avec `uniform_batch_size=True` qui ne fait que du
batching interne pour la memoire, pas une segmentation qualite. Toute passe
SeedVR2 doit donc porter sur <=64 frames de source.
"""
import json
import math
import os
import subprocess
import time
import urllib.request

import numpy as np
from PIL import Image

COMFY = "http://127.0.0.1:8188"
COMFY_INPUT_DIR = r"D:\Ov3rLoRd AI\ComfyUI\input"
COMFY_OUTPUT_DIR = r"D:\Ov3rLoRd AI\ComfyUI\output"
UPSCALE_TEMPLATE = os.path.join("workspace", "comfyui_workflows", "anisora_seedvr2_upscale.json")
FFMPEG = r"C:\Users\Ov3rL0rD\AppData\Local\Microsoft\WinGet\Links\ffmpeg.exe"
FFPROBE = r"C:\Users\Ov3rL0rD\AppData\Local\Microsoft\WinGet\Links\ffprobe.exe"

SEGMENT_MAX_FRAMES = 64
SOURCE_FPS = 8
FINAL_FPS = 24
BOUNDARY_SCORE_THRESHOLD = 0.12  # au-dela : concordance de style jugee faible


def probe_frame_count(video_path):
    r = subprocess.run(
        [FFPROBE, "-v", "error", "-count_frames", "-select_streams", "v:0",
         "-show_entries", "stream=nb_read_frames", "-of", "csv=p=0", video_path],
        check=True, capture_output=True, text=True,
    )
    return int(r.stdout.strip())


def extract_frame_range(video_path, start_frame, n_frames, out_path):
    """Extrait [start_frame, start_frame+n_frames) (0-indexe) en un mp4 8fps independant."""
    # -r seul suffit a forcer un CFR base sur setpts ; -vsync/-fps_mode en
    # plus est rejete par ffmpeg 8.1 ("contradictory") -- confirme en testant
    # la commande a la main (2026-08-06).
    subprocess.run(
        [FFMPEG, "-y", "-i", video_path,
         "-vf", f"select='between(n\\,{start_frame}\\,{start_frame + n_frames - 1})',setpts=N/({SOURCE_FPS}*TB)",
         "-r", str(SOURCE_FPS), out_path],
        check=True, capture_output=True, text=True,
    )


def extract_single_frame(video_path, frame_index, out_png):
    subprocess.run(
        [FFMPEG, "-y", "-i", video_path,
         "-vf", f"select=eq(n\\,{frame_index})", "-update", "1", "-vframes", "1", out_png],
        check=True, capture_output=True, text=True,
    )


def split_into_segments(video_path, out_dir, prefix, max_frames=SEGMENT_MAX_FRAMES):
    total = probe_frame_count(video_path)
    n_segments = math.ceil(total / max_frames)
    segments = []
    os.makedirs(out_dir, exist_ok=True)
    for s in range(n_segments):
        start = s * max_frames
        n = min(max_frames, total - start)
        seg_path = os.path.join(out_dir, f"{prefix}_seg{s + 1:02d}.mp4")
        extract_frame_range(video_path, start, n, seg_path)
        segments.append({"path": seg_path, "start": start, "n_frames": n, "index": s + 1})
    return segments


def _queue_prompt(workflow, client_id):
    body = json.dumps({"prompt": workflow, "client_id": client_id}).encode("utf-8")
    req = urllib.request.Request(f"{COMFY}/prompt", data=body, headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.load(resp)


def _wait_for_completion(prompt_id, timeout=900, poll=5):
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


def _resolve_output_path(out_node, key_candidates=("videos", "gifs", "images")):
    key = next(k for k in key_candidates if k in out_node)
    info = out_node[key][0]
    if "fullpath" in info:
        return info["fullpath"]
    return os.path.join(COMFY_OUTPUT_DIR, info.get("subfolder", ""), info["filename"])


def upscale_segment(segment_path, resolution, client_id_prefix, filename_prefix):
    """Upscale UN segment (<=64 frames, deja garanti par l'appelant) via SeedVR2.
    batch_size du node = n_frames du segment (jamais >64) : c'est le levier
    qui evite la degradation constatee au-dela de 64 frames en un seul passage."""
    n_frames = probe_frame_count(segment_path)
    if n_frames > SEGMENT_MAX_FRAMES:
        raise ValueError(f"segment de {n_frames} frames > {SEGMENT_MAX_FRAMES} (regle SeedVR2 64 max)")

    comfy_input_name = os.path.basename(segment_path)
    import shutil
    shutil.copy2(segment_path, os.path.join(COMFY_INPUT_DIR, comfy_input_name))

    with open(UPSCALE_TEMPLATE, encoding="utf-8") as f:
        wf = json.load(f)
    wf["1"]["inputs"]["file"] = comfy_input_name
    wf["5"]["inputs"]["batch_size"] = n_frames
    wf["5"]["inputs"]["resolution"] = resolution
    wf["7"]["inputs"]["filename_prefix"] = filename_prefix

    r = _queue_prompt(wf, f"{client_id_prefix}-{comfy_input_name}")
    if r.get("node_errors"):
        raise RuntimeError(f"node_errors upscale segment {comfy_input_name}: {json.dumps(r['node_errors'])}")
    prompt_id = r["prompt_id"]
    t0 = time.time()
    entry = _wait_for_completion(prompt_id)
    dt = time.time() - t0
    return _resolve_output_path(entry["outputs"]["7"]), dt


def colormatch_correct_segment(segment_path, ref_frame_path, client_id_prefix, filename_prefix):
    """Corrige un segment (deja upscale) par ColorMatchV2 LAB vs une frame de
    reference (derniere frame du segment precedent), utilise quand le score
    de concordance de frontiere est bas. Substitut pragmatique a un inpaint
    guide par keyframe (aucune chaine d'inpainting video n'existe dans ce
    depot -- les *SegNet en font sur images statiques, pas reutilisable ici
    sans developpement dedie hors perimetre) : documente explicitement comme
    un choix de portee, pas une equivalence qualite."""
    comfy_seg_name = "cmfix_" + os.path.basename(segment_path)
    comfy_ref_name = "cmfix_ref_" + os.path.basename(ref_frame_path)
    import shutil
    shutil.copy2(segment_path, os.path.join(COMFY_INPUT_DIR, comfy_seg_name))
    shutil.copy2(ref_frame_path, os.path.join(COMFY_INPUT_DIR, comfy_ref_name))

    wf = {
        "1": {"class_type": "LoadVideo", "inputs": {"file": comfy_seg_name}},
        "2": {"class_type": "GetVideoComponents", "inputs": {"video": ["1", 0]}},
        "3": {"class_type": "LoadImage", "inputs": {"image": comfy_ref_name}},
        "4": {"class_type": "ColorMatchV2", "inputs": {
            "image_target": ["2", 0], "image_ref": ["3", 0],
            "method": "reinhard_lab_gpu", "strength": 1.0, "multithread": True,
        }},
        "5": {"class_type": "CreateVideo", "inputs": {"images": ["4", 0], "audio": ["2", 1], "fps": ["2", 2]}},
        "6": {"class_type": "SaveVideo", "inputs": {
            "video": ["5", 0], "filename_prefix": filename_prefix, "format": "auto", "codec": "auto",
            "pix_fmt": "yuv420p", "crf": 19, "save_metadata": True, "trim_to_audio": False,
        }},
    }
    r = _queue_prompt(wf, f"{client_id_prefix}-colormatch")
    if r.get("node_errors"):
        raise RuntimeError(f"node_errors colormatch: {json.dumps(r['node_errors'])}")
    prompt_id = r["prompt_id"]
    entry = _wait_for_completion(prompt_id)
    return _resolve_output_path(entry["outputs"]["6"])


def boundary_score(png_a, png_b, size=64):
    """Score de concordance de style entre 2 frames (0=identiques, 1=tres
    different). Metrique legere (diff couleur moyenne normalisee) -- pas un
    modele perceptuel entraine, suffisant pour detecter une rupture de
    coloration/luminosite franche a une frontiere de segment."""
    a = np.asarray(Image.open(png_a).convert("RGB").resize((size, size)), dtype=np.float32) / 255.0
    b = np.asarray(Image.open(png_b).convert("RGB").resize((size, size)), dtype=np.float32) / 255.0
    return float(np.abs(a - b).mean())


def interpolate_to_final_fps(video_path, out_path, target_fps=FINAL_FPS, source_fps=SOURCE_FPS):
    """8fps -> 24fps. RIFE natif indisponible sur cette install (checkpoint
    incompatible, cf. TEST_WORKFLOW_A_20260806.md) : ffmpeg minterpolate
    (mode mci, compensation de mouvement classique) reste le contournement
    documente -- pas un equivalent qualite a un vrai RIFE."""
    subprocess.run(
        [FFMPEG, "-y", "-i", video_path,
         "-vf", f"minterpolate=fps={target_fps}:mi_mode=mci:mc_mode=aobmc:vsbmc=1",
         "-c:v", "libx264", "-pix_fmt", "yuv420p", "-crf", "18", out_path],
        check=True, capture_output=True, text=True,
    )


def concat_copy(video_paths, out_path):
    # ffmpeg (concat demuxer) resout un chemin relatif dans la liste par
    # rapport au dossier du fichier de liste lui-meme, pas au cwd du process
    # Python -- un melange chemins relatifs/absolus (constate 2026-08-06,
    # good_segment relatif + segments SeedVR2 absolus) produit une
    # duplication de chemin et "No such file or directory". Toujours
    # resoudre en absolu ici, quel que soit ce que l'appelant a fourni.
    list_path = os.path.abspath(out_path) + ".concat_list.txt"
    with open(list_path, "w", encoding="utf-8") as f:
        for p in video_paths:
            f.write(f"file '{os.path.abspath(p).replace(chr(92), '/')}'\n")
    subprocess.run(
        [FFMPEG, "-y", "-f", "concat", "-safe", "0", "-i", list_path, "-c", "copy", out_path],
        check=True, capture_output=True, text=True,
    )
    return list_path

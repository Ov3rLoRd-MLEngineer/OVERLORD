"""Piste E : deconstruction/reconstruction lineart N&B -> recolorisation IPAdapter.

Frame SVI brute -> AnimeLineArtPreprocessor (controlnet_aux) -> nettoyage
(seuillage + dilatation, cv2, local) -> recolorisation SDXL guidee par le
squelette lineart (ControlNet xinsir-lineart-sdxl) + couleur ancree sur le
keyframe SDXL (IPAdapter Plus, poids variable) -> fusion multiply avec le
lineart nettoye -> (E4 seulement) ColorMatchV2 LAB final vs keyframe.

4 variantes sur les 10 memes frames de reference que le comparatif A/B/C/D
(DOCS/MD/COMPARAISON_UNIFICATION_20260806.md) :
  E1 : ControlNet lineart seul, pas d'IPAdapter (mesure la perte de coherence
       couleur pure -- aucune source de couleur autre que le prior du modele)
  E2 : + IPAdapter Plus (keyframe), weight=0.6
  E3 : + IPAdapter Plus (keyframe), weight=0.9
  E4 : E3 + ColorMatchV2 LAB (piste A) applique sur le resultat fusionne
       (combinaison A+E)

IPAdapter charge manuellement (CLIPVisionLoader + IPAdapterModelLoader) plutot
que IPAdapterUnifiedLoader : le seul ipadapter SDXL installe
(`ip-adapter-plus_sdxl_vit-h.safetensors`) attend un clip vision ViT-H (pas
bigG malgre le nom "sdxl"), et le fichier installe `model.safetensors`
(2 528 373 448 octets, taille exacte du ViT-H-14 laion2B s32B b79K) ne
correspond a aucun motif de nommage reconnu par le preset-matching de
IPAdapterUnifiedLoader -- chargement explicite par nom de fichier pour eviter
l'exception "ClipVision model not found."

Usage:
    "D:\\Ov3rLoRd AI\\python_embeded\\python.exe" DEMO/run_piste_e_lineart.py
"""
import json
import os
import shutil
import time
import urllib.request

import cv2
import numpy as np
from PIL import Image

COMFY = "http://127.0.0.1:8188"
COMFY_INPUT_DIR = r"D:\Ov3rLoRd AI\ComfyUI\input"
COMFY_OUTPUT_DIR = r"D:\Ov3rLoRd AI\ComfyUI\output"

REF_DIR = r"D:\OVERLORD\DEMO\frames\comparaison_unification_ref"
KEYFRAME = r"D:\Ov3rLoRd AI\ComfyUI\output\WorkflowA\sdxl_keyframe_miku_00001_.png"
LINEART_CLEAN_DIR = os.path.join(REF_DIR, "piste_E_lineart_clean")

FRAME_IDS = [1, 5, 9, 13, 17, 21, 25, 29, 33, 37]

CHECKPOINT = "fabricatedXL_v70.safetensors"
VAE_NAME = "taesdxl"
LINEART_CN_MODEL = "xinsir-controlnet-lineart-sdxl.safetensors"
LINEART_PREPROC_RESOLUTION = 720

IPADAPTER_FILE = "ip-adapter-plus_sdxl_vit-h.safetensors"
CLIPVISION_FILE = "model.safetensors"  # ViT-H-14 laion2B s32B b79K (taille verifiee)

RECOLOR_STEPS, RECOLOR_CFG = 18, 6.0
RECOLOR_SAMPLER, RECOLOR_SCHEDULER = "dpmpp_2m_sde", "karras"
RECOLOR_DENOISE = 0.85  # depart quasi-vierge (lineart), besoin de forte denoise pour la couleur
CN_STRENGTH, CN_START, CN_END = 1.3, 0.0, 1.0  # structure tenue tout du long

POS_PROMPT = (
    "masterpiece, best quality, anime style, 1girl, twin-tail hair, hair clip, "
    "headset, sleeveless dress, thigh-high boots, flexing arms muscle pose, "
    "flat colors, clean lineart, consistent character"
)
NEG_PROMPT = "worst quality, low quality, blurry, jpeg artifacts, monochrome, grayscale, sketch, unfinished lineart"

VARIANTS = {
    "E1": {"ipadapter": False, "weight": 0.0, "colormatch": False},
    "E2": {"ipadapter": True, "weight": 0.6, "colormatch": False},
    "E3": {"ipadapter": True, "weight": 0.9, "colormatch": False},
    "E4": {"ipadapter": True, "weight": 0.9, "colormatch": True},
}


def queue_prompt(workflow, client_id):
    body = json.dumps({"prompt": workflow, "client_id": client_id}).encode("utf-8")
    req = urllib.request.Request(f"{COMFY}/prompt", data=body, headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.load(resp)


def wait_for_completion(prompt_id, timeout=600, poll=3):
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


def resolve_output_path(out_node):
    key = next(k for k in ("images", "gifs", "videos") if k in out_node)
    info = out_node[key][0]
    if "fullpath" in info:
        return info["fullpath"]
    return os.path.join(COMFY_OUTPUT_DIR, info.get("subfolder", ""), info["filename"])


def run_graph(wf, client_id, save_node_id, timeout=600):
    r = queue_prompt(wf, client_id)
    if r.get("node_errors"):
        raise RuntimeError(f"node_errors ({client_id}): {json.dumps(r['node_errors'])}")
    entry = wait_for_completion(r["prompt_id"], timeout=timeout)
    return resolve_output_path(entry["outputs"][save_node_id])


def upload(local_path, comfy_name):
    shutil.copy2(local_path, os.path.join(COMFY_INPUT_DIR, comfy_name))
    return comfy_name


# ── Phase 1 : extraction + nettoyage lineart (une fois par frame) ──────────

def extract_lineart(fid, frame_path):
    frame_name = upload(frame_path, f"cmpE_src_{fid:06d}.png")
    wf = {
        "1": {"class_type": "LoadImage", "inputs": {"image": frame_name}},
        "2": {"class_type": "AnimeLineArtPreprocessor", "inputs": {
            "image": ["1", 0], "resolution": LINEART_PREPROC_RESOLUTION,
        }},
        "3": {"class_type": "SaveImage", "inputs": {
            "images": ["2", 0], "filename_prefix": "CmpUnification/pisteE_lineart_raw",
        }},
    }
    raw_path = run_graph(wf, f"cmpE-lineart-f{fid}", "3", timeout=120)

    raw = np.array(Image.open(raw_path).convert("L"))
    # BUG CORRIGE (premiere passe 2026-08-06) : AnimeLineArtPreprocessor sort
    # des traits CLAIRS sur fond SOMBRE (verifie visuellement sur
    # pisteE_lineart_raw_00001_.png -- pas l'inverse suppose initialement).
    # Seuiller/dilater directement dans cette polarite (les traits sont deja
    # le "premier plan" clair, cv2.dilate() les epaissit correctement) puis
    # une SEULE inversion finale pour obtenir la convention "fond blanc /
    # traits noirs" attendue par VAEEncode/ControlNet/fusion multiply.
    # L'ancienne version inversait AVANT le dilate : cv2.dilate() faisait
    # alors grossir le fond (devenu clair) et rongeait les traits (devenus
    # sombre et fins) jusqu'a quasi-disparition -> image de sortie quasi
    # noire, latents VAEEncode quasi noirs, ControlNet quasi sans structure.
    _, thresh = cv2.threshold(raw, 40, 255, cv2.THRESH_BINARY)
    dilated = cv2.dilate(thresh, np.ones((2, 2), np.uint8), iterations=1)
    clean = 255 - dilated

    os.makedirs(LINEART_CLEAN_DIR, exist_ok=True)
    clean_path = os.path.join(LINEART_CLEAN_DIR, f"frame_{fid:05d}.png")
    Image.fromarray(clean).convert("RGB").save(clean_path)
    return clean_path, clean


# ── Phase 2 : recolorisation guidee (ControlNet lineart [+ IPAdapter]) ─────

def recolor_graph(fid, clean_lineart_name, keyframe_name, seed, use_ipadapter, weight):
    wf = {
        "1": {"class_type": "CheckpointLoaderSimple", "inputs": {"ckpt_name": CHECKPOINT}},
        "2": {"class_type": "VAELoader", "inputs": {"vae_name": VAE_NAME}},
        "3": {"class_type": "LoadImage", "inputs": {"image": clean_lineart_name}},
        "4": {"class_type": "VAEEncode", "inputs": {"pixels": ["3", 0], "vae": ["2", 0]}},
        "5": {"class_type": "CLIPTextEncode", "inputs": {"text": POS_PROMPT, "clip": ["1", 1]}},
        "6": {"class_type": "CLIPTextEncode", "inputs": {"text": NEG_PROMPT, "clip": ["1", 1]}},
        "7": {"class_type": "ControlNetLoader", "inputs": {"control_net_name": LINEART_CN_MODEL}},
        "8": {"class_type": "ControlNetApplyAdvanced", "inputs": {
            "positive": ["5", 0], "negative": ["6", 0], "control_net": ["7", 0], "image": ["3", 0],
            "vae": ["2", 0], "strength": CN_STRENGTH, "start_percent": CN_START, "end_percent": CN_END,
        }},
    }

    model_ref = ["1", 0]
    if use_ipadapter:
        wf["9"] = {"class_type": "CLIPVisionLoader", "inputs": {"clip_name": CLIPVISION_FILE}}
        wf["10"] = {"class_type": "IPAdapterModelLoader", "inputs": {"ipadapter_file": IPADAPTER_FILE}}
        wf["11"] = {"class_type": "LoadImage", "inputs": {"image": keyframe_name}}
        wf["12"] = {"class_type": "IPAdapterAdvanced", "inputs": {
            "model": ["1", 0], "ipadapter": ["10", 0], "image": ["11", 0], "clip_vision": ["9", 0],
            "weight": weight, "weight_type": "linear", "combine_embeds": "concat",
            "start_at": 0.0, "end_at": 1.0, "embeds_scaling": "V only",
        }}
        model_ref = ["12", 0]

    wf["13"] = {"class_type": "KSampler", "inputs": {
        "model": model_ref, "positive": ["8", 0], "negative": ["8", 1], "latent_image": ["4", 0],
        "seed": seed, "steps": RECOLOR_STEPS, "cfg": RECOLOR_CFG,
        "sampler_name": RECOLOR_SAMPLER, "scheduler": RECOLOR_SCHEDULER, "denoise": RECOLOR_DENOISE,
    }}
    wf["14"] = {"class_type": "VAEDecode", "inputs": {"samples": ["13", 0], "vae": ["2", 0]}}
    wf["15"] = {"class_type": "SaveImage", "inputs": {
        "images": ["14", 0], "filename_prefix": "CmpUnification/pisteE_recolor",
    }}
    return wf


def colormatch_graph(fused_name, keyframe_name):
    wf = {
        "1": {"class_type": "LoadImage", "inputs": {"image": fused_name}},
        "2": {"class_type": "LoadImage", "inputs": {"image": keyframe_name}},
        "3": {"class_type": "ColorMatchV2", "inputs": {
            "image_target": ["1", 0], "image_ref": ["2", 0],
            "method": "reinhard_lab_gpu", "strength": 1.0, "multithread": True,
        }},
        "4": {"class_type": "SaveImage", "inputs": {
            "images": ["3", 0], "filename_prefix": "CmpUnification/pisteE4_colormatch",
        }},
    }
    return wf


def multiply_blend(colored_path, clean_lineart_arr, out_path):
    colored = np.array(Image.open(colored_path).convert("RGB")).astype(np.float64)
    lineart = clean_lineart_arr.astype(np.float64) / 255.0
    if lineart.shape != colored.shape[:2]:
        lineart = np.array(Image.fromarray(clean_lineart_arr).resize(
            (colored.shape[1], colored.shape[0]), Image.NEAREST
        )).astype(np.float64) / 255.0
    fused = np.clip(colored * lineart[..., None], 0, 255).astype(np.uint8)
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    Image.fromarray(fused).save(out_path)
    return out_path


def main():
    log = {v: {"ok": [], "errors": []} for v in VARIANTS}
    keyframe_name = upload(KEYFRAME, "cmpE_keyframe_ref.png")
    t_total0 = time.time()

    for fid in FRAME_IDS:
        frame_path = os.path.join(REF_DIR, f"frame_{fid:05d}.png")
        try:
            clean_path, clean_arr = extract_lineart(fid, frame_path)
            print(f"[lineart] frame {fid} OK -> {clean_path}", flush=True)
        except Exception as e:
            print(f"[lineart] frame {fid} ECHEC: {e}", flush=True)
            for v in VARIANTS:
                log[v]["errors"].append((fid, f"lineart extraction failed: {e}"))
            continue

        clean_name = upload(clean_path, f"cmpE_linclean_{fid:06d}.png")
        seed = 700000000 + fid

        for vname, vcfg in VARIANTS.items():
            out_path = os.path.join(REF_DIR, f"piste_{vname}", f"frame_{fid:05d}.png")
            try:
                wf = recolor_graph(fid, clean_name, keyframe_name, seed, vcfg["ipadapter"], vcfg["weight"])
                recolored_path = run_graph(wf, f"cmpE-{vname}-f{fid}", "15", timeout=600)

                fused_local = os.path.join(REF_DIR, f"piste_{vname}", f"_fused_{fid:05d}.png")
                multiply_blend(recolored_path, clean_arr, fused_local)

                if vcfg["colormatch"]:
                    fused_name = upload(fused_local, f"cmpE_fused_{vname}_{fid:06d}.png")
                    wf_cm = colormatch_graph(fused_name, keyframe_name)
                    cm_path = run_graph(wf_cm, f"cmpE-{vname}-cm-f{fid}", "4", timeout=120)
                    shutil.copy2(cm_path, out_path)
                else:
                    shutil.copy2(fused_local, out_path)
                os.remove(fused_local)

                log[vname]["ok"].append(fid)
                print(f"[{vname}] frame {fid} OK -> {out_path}", flush=True)
            except Exception as e:
                log[vname]["errors"].append((fid, str(e)))
                print(f"[{vname}] frame {fid} ECHEC: {e}", flush=True)

    elapsed_total = time.time() - t_total0
    print(f"RESULT_SUMMARY: {json.dumps(log)}")
    print(f"RESULT_ELAPSED_S: {elapsed_total:.1f}")


if __name__ == "__main__":
    main()

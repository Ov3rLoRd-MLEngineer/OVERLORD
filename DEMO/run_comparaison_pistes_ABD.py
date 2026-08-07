"""Execute reellement les pistes A (ColorMatch LAB pre-hi-res), B (hi-res fix
UltimateSDUpscale seul) et D (meme hi-res fix + ControlNet OpenPose) sur les
10 frames de reference de DOCS/MD/COMPARAISON_UNIFICATION_20260806.md, via
l'API ComfyUI (port 8188, RTX 5080 -- instance deja active, un seul
utilisateur donc pas de contention).

Reprend tel quel le pattern d'appel HTTP de DEMO/generate_svi_chain.py
(queue_prompt/wait_for_completion) et les parametres checkpoint/VAE/upscale
de la branche hires deja validee dans
agents/production_video/postprod_inpaint.py::hires_fix_2k (memes noms de
modele, HIRES_DENOISE ajuste a 0.40 -- milieu de la plage 0.35-0.45 demandee
pour ce test, au lieu de 0.16 en prod).

Usage:
    "D:\\Ov3rLoRd AI\\python_embeded\\python.exe" DEMO/run_comparaison_pistes_ABD.py
"""
import json
import os
import shutil
import time
import urllib.request

COMFY = "http://127.0.0.1:8188"
COMFY_INPUT_DIR = r"D:\Ov3rLoRd AI\ComfyUI\input"
COMFY_OUTPUT_DIR = r"D:\Ov3rLoRd AI\ComfyUI\output"

REF_DIR = r"D:\OVERLORD\DEMO\frames\comparaison_unification_ref"
KEYFRAME = r"D:\Ov3rLoRd AI\ComfyUI\output\WorkflowA\sdxl_keyframe_miku_00001_.png"
SKELETON = os.path.join(REF_DIR, "piste_D_skeleton.png")

FRAME_IDS = [1, 5, 9, 13, 17, 21, 25, 29, 33, 37]

CHECKPOINT = "fabricatedXL_v70.safetensors"
VAE_NAME = "taesdxl"
UPSCALE_MODEL = "4x_foolhardy_Remacri.pth"
OPENPOSE_CN_MODEL = "noobaiXLControlnet_openposeModel.safetensors"

HIRES_UPSCALE_BY = 1.5
HIRES_STEPS, HIRES_CFG = 18, 6.0
HIRES_DENOISE = 0.40  # consigne de tache : 0.35-0.45 (milieu de plage), pas le 0.16 de prod
HIRES_SAMPLER, HIRES_SCHEDULER = "dpmpp_2m_sde", "karras"
HIRES_POS_PROMPT = "masterpiece, best quality, anime style, detailed"
HIRES_NEG_PROMPT = "worst quality, low quality, blurry, jpeg artifacts"

# ControlNetApplyAdvanced (openpose) -- valeurs reprises telles quelles du
# node 165 de Advanced_QwenVL_V35_ORIGINAL.json (seul usage valide de ce
# modele CN dans le depot) : strength=1.25, start_percent=0.0, end_percent=0.5
CN_STRENGTH, CN_START, CN_END = 1.25, 0.0, 0.5


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


# ── Piste A : ColorMatchV2 LAB pre-hi-res ───────────────────────────────────

def piste_a(frame_id, frame_path, keyframe_name):
    frame_name = upload(frame_path, f"cmpA_src_{frame_id:06d}.png")
    wf = {
        "1": {"class_type": "LoadImage", "inputs": {"image": frame_name}},
        "2": {"class_type": "LoadImage", "inputs": {"image": keyframe_name}},
        "3": {"class_type": "ColorMatchV2", "inputs": {
            "image_target": ["1", 0], "image_ref": ["2", 0],
            "method": "reinhard_lab_gpu", "strength": 1.0, "multithread": True,
        }},
        "4": {"class_type": "SaveImage", "inputs": {
            "images": ["3", 0], "filename_prefix": "CmpUnification/pisteA",
        }},
    }
    return run_graph(wf, f"cmpA-f{frame_id}", "4", timeout=120)


# ── Piste B : hi-res fix seul (UltimateSDUpscale, branche postprod_inpaint) ─

def _hires_graph_base(frame_name):
    return {
        "1": {"class_type": "CheckpointLoaderSimple", "inputs": {"ckpt_name": CHECKPOINT}},
        "2": {"class_type": "VAELoader", "inputs": {"vae_name": VAE_NAME}},
        "3": {"class_type": "LoadImage", "inputs": {"image": frame_name}},
        "4": {"class_type": "UpscaleModelLoader", "inputs": {"model_name": UPSCALE_MODEL}},
        "5": {"class_type": "CLIPTextEncode", "inputs": {"text": HIRES_POS_PROMPT, "clip": ["1", 1]}},
        "6": {"class_type": "CLIPTextEncode", "inputs": {"text": HIRES_NEG_PROMPT, "clip": ["1", 1]}},
    }


def piste_b(frame_id, frame_path, seed):
    frame_name = upload(frame_path, f"cmpB_src_{frame_id:06d}.png")
    wf = _hires_graph_base(frame_name)
    wf["7"] = {"class_type": "UltimateSDUpscale", "inputs": {
        "image": ["3", 0], "model": ["1", 0], "positive": ["5", 0], "negative": ["6", 0], "vae": ["2", 0],
        "upscale_model": ["4", 0], "upscale_by": HIRES_UPSCALE_BY,
        "seed": seed, "steps": HIRES_STEPS, "cfg": HIRES_CFG,
        "sampler_name": HIRES_SAMPLER, "scheduler": HIRES_SCHEDULER, "denoise": HIRES_DENOISE,
        "mode_type": "Linear", "tile_width": 512, "tile_height": 512,
        "mask_blur": 16, "tile_padding": 64,
        "seam_fix_mode": "Half Tile + Intersections", "seam_fix_denoise": 1.0,
        "seam_fix_width": 64, "seam_fix_mask_blur": 8, "seam_fix_padding": 16,
        "force_uniform_tiles": True, "tiled_decode": False, "batch_size": 1,
    }}
    wf["8"] = {"class_type": "SaveImage", "inputs": {
        "images": ["7", 0], "filename_prefix": "CmpUnification/pisteB",
    }}
    return run_graph(wf, f"cmpB-f{frame_id}", "8", timeout=600)


# ── Piste D : meme branche hi-res + ControlNet OpenPose (squelette synth.) ──

def piste_d(frame_id, frame_path, seed, skeleton_name):
    frame_name = upload(frame_path, f"cmpD_src_{frame_id:06d}.png")
    wf = _hires_graph_base(frame_name)
    wf["9"] = {"class_type": "ControlNetLoader", "inputs": {"control_net_name": OPENPOSE_CN_MODEL}}
    wf["10"] = {"class_type": "LoadImage", "inputs": {"image": skeleton_name}}
    wf["11"] = {"class_type": "ControlNetApplyAdvanced", "inputs": {
        "positive": ["5", 0], "negative": ["6", 0], "control_net": ["9", 0], "image": ["10", 0],
        "vae": ["2", 0], "strength": CN_STRENGTH, "start_percent": CN_START, "end_percent": CN_END,
    }}
    wf["7"] = {"class_type": "UltimateSDUpscale", "inputs": {
        "image": ["3", 0], "model": ["1", 0], "positive": ["11", 0], "negative": ["11", 1], "vae": ["2", 0],
        "upscale_model": ["4", 0], "upscale_by": HIRES_UPSCALE_BY,
        "seed": seed, "steps": HIRES_STEPS, "cfg": HIRES_CFG,
        "sampler_name": HIRES_SAMPLER, "scheduler": HIRES_SCHEDULER, "denoise": HIRES_DENOISE,
        "mode_type": "Linear", "tile_width": 512, "tile_height": 512,
        "mask_blur": 16, "tile_padding": 64,
        "seam_fix_mode": "Half Tile + Intersections", "seam_fix_denoise": 1.0,
        "seam_fix_width": 64, "seam_fix_mask_blur": 8, "seam_fix_padding": 16,
        "force_uniform_tiles": True, "tiled_decode": False, "batch_size": 1,
    }}
    wf["8"] = {"class_type": "SaveImage", "inputs": {
        "images": ["7", 0], "filename_prefix": "CmpUnification/pisteD",
    }}
    return run_graph(wf, f"cmpD-f{frame_id}", "8", timeout=600)


def main():
    log = {"A": {"ok": [], "errors": []}, "B": {"ok": [], "errors": []}, "D": {"ok": [], "errors": []}}
    keyframe_name = upload(KEYFRAME, "cmp_unif_keyframe_ref.png")
    skeleton_name = upload(SKELETON, "cmp_unif_piste_D_skeleton.png")

    t_total0 = time.time()

    for fid in FRAME_IDS:
        frame_path = os.path.join(REF_DIR, f"frame_{fid:05d}.png")
        out_a = os.path.join(REF_DIR, "piste_A", f"frame_{fid:05d}.png")
        seed = 700000000 + fid

        # Piste A
        try:
            result = piste_a(fid, frame_path, keyframe_name)
            shutil.copy2(result, out_a)
            log["A"]["ok"].append(fid)
            print(f"[A] frame {fid} OK -> {out_a}", flush=True)
        except Exception as e:
            log["A"]["errors"].append((fid, str(e)))
            print(f"[A] frame {fid} ECHEC: {e}", flush=True)

        # Piste B
        out_b = os.path.join(REF_DIR, "piste_B", f"frame_{fid:05d}.png")
        try:
            result = piste_b(fid, frame_path, seed)
            shutil.copy2(result, out_b)
            log["B"]["ok"].append(fid)
            print(f"[B] frame {fid} OK -> {out_b}", flush=True)
        except Exception as e:
            log["B"]["errors"].append((fid, str(e)))
            print(f"[B] frame {fid} ECHEC: {e}", flush=True)

        # Piste D
        out_d = os.path.join(REF_DIR, "piste_D", f"frame_{fid:05d}.png")
        try:
            result = piste_d(fid, frame_path, seed, skeleton_name)
            shutil.copy2(result, out_d)
            log["D"]["ok"].append(fid)
            print(f"[D] frame {fid} OK -> {out_d}", flush=True)
        except Exception as e:
            log["D"]["errors"].append((fid, str(e)))
            print(f"[D] frame {fid} ECHEC: {e}", flush=True)

    elapsed_total = time.time() - t_total0
    print(f"RESULT_SUMMARY: {json.dumps(log)}")
    print(f"RESULT_ELAPSED_S: {elapsed_total:.1f}")


if __name__ == "__main__":
    main()

"""
motion_mask_generator.py — Ov3rLoRd Pipeline
Génère un masque de mouvement entre deux frames via diff squelettes,
puis soumet un workflow inpaint ComfyUI avec DifferentialDiffusion
pour régénérer uniquement les zones qui bougent.

Usage standalone :
    py -3.12 agents/motion_mask_generator.py \
        --skel-prev SK_N-1 --skel-cur SK_N \
        --frame-prev FRAME_N-1 --output OUT_N \
        --denoise 0.25

Usage depuis batch_controlnet.py :
    from motion_mask_generator import generate_motion_inpaint
    result = generate_motion_inpaint(skel_prev, skel_cur, frame_prev,
                                     output_prefix, seed, denoise,
                                     prompt_pos, prompt_neg)
"""

import os
import sys
import json
import time
import glob
import shutil
import argparse
import urllib.request
import urllib.error

try:
    import numpy as np
    from PIL import Image, ImageFilter
    HAS_PIL = True
except ImportError:
    HAS_PIL = False
    print("[WARN] Pillow/numpy manquant")

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)
import config

import io
if hasattr(sys.stdout, 'buffer') and getattr(sys.stdout, 'encoding','').lower() != 'utf-8':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

# ── CONFIG ────────────────────────────────────────────────────────────────────
COMFY_URL      = "http://127.0.0.1:8188"
COMFY_INPUT    = str(config.COMFYUI_INPUT)
COMFY_OUTPUT   = str(config.COMFYUI_OUTPUT / "asuka_run")

CHECKPOINT     = "fabricatedXL_v70.safetensors"
LORA           = "asuka-langley-soryuu-classic-ponyxl-lora-nochekaiser.safetensors"
LORA_WEIGHT    = 0.75
VAE            = "taesdxl"
CONTROLNET     = "control-lora-openposeXL2-rank256.safetensors"
CONTROLNET_LA  = "xinsir-controlnet-lineart-sdxl.safetensors"

CN_STRENGTH    = 1.25
CN_START       = 0.0
CN_END         = 0.50
CN_LA_STRENGTH = 1.25
CN_LA_START    = 0.0
CN_LA_END      = 0.50

STEPS          = 40
CFG            = 7.0
SAMPLER        = "dpmpp_2m"
SCHEDULER      = "karras"

# Masque
MASK_DIFF_THRESHOLD = 15    # diff pixel considéré comme mouvement
MASK_GROW_PX        = 20    # expansion du masque (pixels)
MASK_BLUR_RADIUS    = 8     # flou pour transitions douces

PROMPT_POS = (
    "score_9, score_8_up, score_7_up, source_anime, masterpiece, highly detailed, "
    "1girl, asuka shoryu langley, blue eyes, nike jordan sneakers, hoodie, "
    "detailed clothing textures, side view, profile, full body, run, "
    "concentrated expression, pure white background"
)
PROMPT_NEG = (
    "blurry, low quality, deformed, ugly, bad anatomy, bad eyes, bad hand, bad finger, "
    "extra limbs, watermark, text, logo, cartoon, anime, painting, 3d render, "
    "child, loli, overexposed, underexposed, plastic skin"
)


# ── COMFYUI HELPERS ───────────────────────────────────────────────────────────
def comfy_post(endpoint, data):
    url = f"{COMFY_URL}/{endpoint}"
    payload = json.dumps(data).encode("utf-8")
    req = urllib.request.Request(
        url, data=payload,
        headers={"Content-Type": "application/json"}
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return json.loads(r.read())
    except urllib.error.HTTPError as e:
        raise RuntimeError(f"HTTP {e.code}: {e.read().decode()}")


def comfy_get(endpoint):
    url = f"{COMFY_URL}/{endpoint}"
    with urllib.request.urlopen(url, timeout=30) as r:
        return json.loads(r.read())


def wait_for_idle(timeout=300):
    start = time.time()
    while time.time() - start < timeout:
        try:
            q = comfy_get("queue")
            if (len(q.get("queue_running", [])) == 0 and
                    len(q.get("queue_pending", [])) == 0):
                return True
        except Exception:
            pass
        time.sleep(1)
    return False


def copy_to_input(src, name):
    dst = os.path.join(COMFY_INPUT, name)
    for attempt in range(5):
        try:
            shutil.copy2(src, dst)
            return name
        except PermissionError:
            time.sleep(0.5)
    shutil.copy2(src, dst)
    return name


def find_generated(frame_num):
    pattern = os.path.join(COMFY_OUTPUT, f"frame_{frame_num:04d}_*.png")
    files = sorted(glob.glob(pattern))
    return files[-1] if files else None


# ── GÉNÉRATION DU MASQUE PIL ──────────────────────────────────────────────────
def generate_motion_mask(skel_prev: str, skel_cur: str,
                          output_mask_path: str = None) -> str:
    """
    Génère un masque PIL depuis le diff entre deux squelettes.

    Logique :
    - Diff pixel entre squelette n-1 et n
    - Seuillage → zones de mouvement (blanc) sur fond noir
    - Expansion + flou pour transitions douces
    - Sauvegarde dans COMFY_INPUT

    Retourne le chemin du masque sauvé.
    """
    if not HAS_PIL:
        raise RuntimeError("Pillow requis pour generate_motion_mask")

    with Image.open(skel_prev) as _i1:
        sk1 = np.array(_i1.convert("L")).astype(float)
    with Image.open(skel_cur) as _i2:
        sk2 = np.array(_i2.convert("L")).astype(float)

    # Diff absolu
    diff = np.abs(sk1 - sk2)

    # Seuillage
    mask = (diff > MASK_DIFF_THRESHOLD).astype(np.uint8) * 255

    # Expansion du masque (morphologie manuelle via PIL)
    mask_img = Image.fromarray(mask, mode="L")
    # Expand via max filter répété
    for _ in range(MASK_GROW_PX // 4):
        mask_img = mask_img.filter(ImageFilter.MaxFilter(9))

    # Flou pour transitions douces (bords smooth)
    mask_img = mask_img.filter(ImageFilter.GaussianBlur(radius=MASK_BLUR_RADIUS))

    # Sauvegarder dans dossier temp hors COMFY_INPUT (evite WinError 32)
    tmp_dir = str(config.WORKSPACE_DIR / "tmp")
    os.makedirs(tmp_dir, exist_ok=True)
    out = output_mask_path or os.path.join(tmp_dir, "ov_motion_mask.png")
    mask_img.save(out)
    mask_img.close()
    return out


# ── WORKFLOW INPAINT AVEC DIFFERENTIALDIFFUSION ───────────────────────────────
def build_inpaint_workflow(frame_filename: str, mask_filename: str,
                            skel_filename: str, la_filename: str,
                            output_prefix: str, seed: int,
                            denoise: float,
                            prompt_pos: str = PROMPT_POS,
                            prompt_neg: str = PROMPT_NEG) -> dict:
    """
    Workflow ComfyUI :
    Checkpoint → LoRA → CLIPSkip → Prompt
    LoadImage(frame_prev) → VAEEncode → SetLatentNoiseMask(mask)
    DifferentialDiffusion(model, mask) → KSampler(denoise)
    ControlNet OpenPose + Lineart en série
    VAEDecode → SaveImage
    """
    w = {
        # Checkpoint + LoRA + CLIPSkip
        "1": {
            "class_type": "CheckpointLoaderSimple",
            "inputs": {"ckpt_name": CHECKPOINT}
        },
        "2": {
            "class_type": "LoraLoader",
            "inputs": {
                "model": ["1", 0], "clip": ["1", 1],
                "lora_name": LORA,
                "strength_model": LORA_WEIGHT,
                "strength_clip": LORA_WEIGHT,
            }
        },
        "20": {
            "class_type": "CLIPSetLastLayer",
            "inputs": {"clip": ["2", 1], "stop_at_clip_layer": -2}
        },
        "3": {
            "class_type": "CLIPTextEncode",
            "inputs": {"text": prompt_pos, "clip": ["20", 0]}
        },
        "4": {
            "class_type": "CLIPTextEncode",
            "inputs": {"text": prompt_neg, "clip": ["20", 0]}
        },

        # Image précédente → latent
        "30": {
            "class_type": "LoadImage",
            "inputs": {"image": frame_filename, "upload": "image"}
        },
        "10": {
            "class_type": "VAELoader",
            "inputs": {"vae_name": VAE}
        },
        "31": {
            "class_type": "VAEEncode",
            "inputs": {"pixels": ["30", 0], "vae": ["10", 0]}
        },

        # Masque de mouvement
        "32": {
            "class_type": "LoadImage",
            "inputs": {"image": mask_filename, "upload": "image"}
        },
        "33": {
            "class_type": "ImageToMask",
            "inputs": {"image": ["32", 0], "channel": "red"}
        },
        # Applique le masque au latent
        "34": {
            "class_type": "SetLatentNoiseMask",
            "inputs": {
                "samples": ["31", 0],
                "mask": ["33", 0]
            }
        },

        # DifferentialDiffusion — denoise variable par zone
        "35": {
            "class_type": "DifferentialDiffusion",
            "inputs": {"model": ["2", 0]}
        },

        # OpenPose skeleton
        "5": {
            "class_type": "LoadImage",
            "inputs": {"image": skel_filename, "upload": "image"}
        },
        "6": {
            "class_type": "ControlNetLoader",
            "inputs": {"control_net_name": CONTROLNET}
        },
        "7": {
            "class_type": "ControlNetApplyAdvanced",
            "inputs": {
                "positive":      ["3", 0],
                "negative":      ["4", 0],
                "control_net":   ["6", 0],
                "image":         ["5", 0],
                "strength":      CN_STRENGTH,
                "start_percent": CN_START,
                "end_percent":   CN_END,
            }
        },

        # VAEDecode + Save
        "11": {
            "class_type": "VAEDecode",
            "inputs": {"samples": ["9", 0], "vae": ["10", 0]}
        },
        "12": {
            "class_type": "SaveImage",
            "inputs": {
                "images": ["11", 0],
                "filename_prefix": output_prefix,
            }
        },
    }

    # Lineart (optionnel)
    cn_out = "7"
    if la_filename:
        w["17"] = {
            "class_type": "LoadImage",
            "inputs": {"image": la_filename, "upload": "image"}
        }
        w["18"] = {
            "class_type": "ControlNetLoader",
            "inputs": {"control_net_name": CONTROLNET_LA}
        }
        w["19"] = {
            "class_type": "ControlNetApplyAdvanced",
            "inputs": {
                "positive":      ["7", 0],
                "negative":      ["7", 1],
                "control_net":   ["18", 0],
                "image":         ["17", 0],
                "strength":      CN_LA_STRENGTH,
                "start_percent": CN_LA_START,
                "end_percent":   CN_LA_END,
            }
        }
        cn_out = "19"

    # KSampler avec DifferentialDiffusion
    w["9"] = {
        "class_type": "KSampler",
        "inputs": {
            "model":         ["35", 0],
            "positive":      [cn_out, 0],
            "negative":      [cn_out, 1],
            "latent_image":  ["34", 0],
            "seed":          seed,
            "steps":         STEPS,
            "cfg":           CFG,
            "sampler_name":  SAMPLER,
            "scheduler":     SCHEDULER,
            "denoise":       denoise,
        }
    }

    return w


# ── FONCTION PRINCIPALE ───────────────────────────────────────────────────────
# ── REMBG PIL INLINE ─────────────────────────────────────────────────────────
REMBG_THRESHOLD = 200

def prepare_prev_for_i2i(img_path: str) -> str:
    """Isole le personnage sur fond blanc avant VAEEncode — évite dérive fond."""
    if not HAS_PIL:
        return img_path
    try:
        with Image.open(img_path) as raw:
            img = raw.convert("RGBA")
        arr = np.array(img)
        r = arr[:,:,0].astype(int)
        g = arr[:,:,1].astype(int)
        b = arr[:,:,2].astype(int)
        is_bg = (r + g + b) > (REMBG_THRESHOLD * 3)
        result = arr.copy()
        result[is_bg] = [255, 255, 255, 255]
        out_img = Image.fromarray(result).convert("RGB")
        tmp_dir = str(config.WORKSPACE_DIR / "tmp")
        os.makedirs(tmp_dir, exist_ok=True)
        tmp = os.path.join(tmp_dir, "_rembg_prev.png")
        out_img.save(tmp)
        out_img.close()
        return tmp
    except Exception as e:
        print(f"[WARN] prepare_prev_for_i2i: {e}")
        return img_path


def generate_motion_inpaint(skel_prev: str, skel_cur: str,
                             frame_prev: str,
                             la_cur: str,
                             output_prefix: str,
                             frame_num: int,
                             seed: int,
                             denoise: float,
                             prompt_pos: str = PROMPT_POS,
                             prompt_neg: str = PROMPT_NEG,
                             verbose: bool = False) -> str | None:
    """
    Pipeline complet motion inpaint pour une frame :
    1. Génère le masque depuis diff squelettes
    2. Copie les fichiers dans ComfyUI input
    3. Soumet le workflow inpaint
    4. Retourne le chemin de la frame générée

    Returns:
        str : chemin de la frame générée, ou None si échec
    """
    # Attendre que ComfyUI soit idle avant de toucher aux fichiers input
    wait_for_idle(timeout=30)

    # Générer et copier le masque
    mask_path = generate_motion_mask(skel_prev, skel_cur)
    copy_to_input(mask_path, "ov_motion_mask_current.png")

    # RemBg sur frame précédente avant VAEEncode — évite dérive fond
    frame_prev_clean = prepare_prev_for_i2i(frame_prev)
    copy_to_input(frame_prev_clean, "ov_inpaint_base_current.png")

    # Copier squelette courant
    copy_to_input(skel_cur, "ov_skeleton_current.png")

    # Lineart courant (optionnel)
    la_filename = None
    if la_cur and os.path.exists(la_cur):
        copy_to_input(la_cur, "ov_lineart_current.png")
        la_filename = "ov_lineart_current.png"

    # Build workflow
    workflow = build_inpaint_workflow(
        frame_filename="ov_inpaint_base_current.png",
        mask_filename="ov_motion_mask_current.png",
        skel_filename="ov_skeleton_current.png",
        la_filename=la_filename,
        output_prefix=output_prefix,
        seed=seed,
        denoise=denoise,
        prompt_pos=prompt_pos,
        prompt_neg=prompt_neg,
    )

    # Soumettre
    wait_for_idle(timeout=60)
    comfy_post("prompt", {"prompt": workflow})
    wait_for_idle(timeout=180)

    result = find_generated(frame_num)
    if verbose:
        if result:
            print(f"[motion_mask] OK → {os.path.basename(result)}")
        else:
            print(f"[motion_mask] ERR — fichier non trouvé")

    return result


# ── CLI ───────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Ov3rLoRd — Motion Mask Generator + Inpaint"
    )
    parser.add_argument("--skel-prev",    required=True)
    parser.add_argument("--skel-cur",     required=True)
    parser.add_argument("--frame-prev",   required=True,
                        help="Frame N-1 générée (base de l'inpaint)")
    parser.add_argument("--la-cur",       default=None,
                        help="Lineart frame N (optionnel)")
    parser.add_argument("--frame-num",    type=int, required=True,
                        help="Numéro de frame pour find_generated()")
    parser.add_argument("--output",       default="asuka_run/frame_test",
                        help="Préfixe output ComfyUI")
    parser.add_argument("--seed",         type=int, default=42)
    parser.add_argument("--denoise",      type=float, default=0.25)
    parser.add_argument("--mask-only",    action="store_true",
                        help="Générer seulement le masque sans soumettre")
    parser.add_argument("--verbose",      action="store_true")
    args = parser.parse_args()

    def absp(p):
        return os.path.abspath(p) if p else None

    if args.mask_only:
        mask = generate_motion_mask(
            absp(args.skel_prev), absp(args.skel_cur),
            os.path.join(COMFY_INPUT, "ov_motion_mask_preview.png")
        )
        print(f"Masque généré : {mask}")
    else:
        result = generate_motion_inpaint(
            skel_prev=absp(args.skel_prev),
            skel_cur=absp(args.skel_cur),
            frame_prev=absp(args.frame_prev),
            la_cur=absp(args.la_cur),
            output_prefix=args.output,
            frame_num=args.frame_num,
            seed=args.seed,
            denoise=args.denoise,
            verbose=args.verbose,
        )
        print(f"Résultat : {result}")

"""
Ov3rLoRd — Batch ControlNet + IP-Adapter + Watchdog V1.4
Fusion V1.3 (architecture robuste) + V1.4 (corrections + features)

Corrections V1.4 :
  - CN strength 0.85 / CN end 0.80 (anti-rigidité, validé sources)
  - SSIM threshold 0.25 (corrigé depuis 0.55 trop strict)
  - Seed par shot (stable par séquence visuelle)
  - IPAdapter end_at 0.30 / weight_type original / K+V
  - Prompt enrichi : TWO black stripes, consistency anchors

Conservé de V1.3 :
  - urllib natif (zéro dépendance externe)
  - wait_for_idle() polling /queue (fiable)
  - WATCHDOG_MAX_RETRY=3 avec seed différente par retry
  - find_generated() glob (gère suffixes ComfyUI variables)
  - copy_to_comfy_input() avec nom custom
  - Flip auto zones course
  - Architecture main() éprouvée
"""

import ast
import json
import time
import os
import sys
import glob
import shutil
import urllib.request
import urllib.error
import argparse

try:
    from PIL import Image, ImageOps, ImageFilter
    import numpy as np
    HAS_PIL = True
except ImportError:
    HAS_PIL = False
    print("[WARN] Pillow/numpy manquant — watchdog et flip désactivés")

try:
    from denoise_estimator import estimate_denoise
    HAS_DENOISE_EST = True
except ImportError:
    HAS_DENOISE_EST = False

try:
    from motion_mask_generator import generate_motion_inpaint
    HAS_MOTION_MASK = True
except ImportError:
    HAS_MOTION_MASK = False

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)
import config

import io
if hasattr(sys.stdout, 'buffer') and getattr(sys.stdout, 'encoding','').lower() != 'utf-8':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

# ── CONFIG ────────────────────────────────────────────────────────────────────
COMFY_URL      = "http://127.0.0.1:8188"
DEMO_DIR       = str(config.DEMO_DIR)
SKELETONS_DIR  = os.path.join(DEMO_DIR, "frames", "skeletons")
SKELETONS_REMAP= os.path.join(DEMO_DIR, "frames", "skeletons_1024x1024")
COMFY_INPUT    = str(config.COMFYUI_INPUT)
COMFY_OUTPUT   = str(config.COMFYUI_OUTPUT / "asuka_run")
GLOBAL_ANCHOR  = os.path.join(DEMO_DIR, "frame_0000_00001_.png")

CHECKPOINT     = "fabricatedXL_v70.safetensors"
LORA           = "asuka-langley-soryuu-classic-ponyxl-lora-nochekaiser.safetensors"
LORA_WEIGHT    = 0.75
CONTROLNET     = "control-lora-openposeXL2-rank256.safetensors"
CONTROLNET_LA  = "xinsir-controlnet-lineart-sdxl.safetensors"
LINEART_DIR    = os.path.join(DEMO_DIR, "frames", "lineart_1024x1024")
VAE            = "taesdxl"
CLIP_VISION    = "model.safetensors"
IPADAPTER      = "ip-adapter-plus_sdxl_vit-h.safetensors"

# ── PARAMÈTRES GÉNÉRATION V1.7 ────────────────────────────────────────────────
CN_STRENGTH    = 1.25   # OpenPose
CN_START       = 0.0
CN_END         = 0.50

CN_LA_STRENGTH = 1.25   # Lineart
CN_LA_START    = 0.0
CN_LA_END      = 0.50

IPA_WEIGHT     = 0.70
IPA_START      = 0.0
IPA_END        = 0.30
IPA_WEIGHT_TYPE= "linear"
IPA_EMBEDS     = "K+V"

DENOISE_T2I    = 1.00   # Frame 0 — txt2img pur
DENOISE_I2I    = 0.20   # Frames 1+ — fallback img2img

# RemBg PIL — seuil fond clair
REMBG_THRESHOLD = 200
# IPA square size
IPA_SQUARE_SIZE = 768
# Motion mask — inpaint zones mouvement
USE_MOTION_MASK = True
MOTION_DENOISE_FALLBACK = 0.20

WIDTH          = 1024
HEIGHT         = 1024
STEPS          = 40
CFG            = 7.0
SAMPLER        = "dpmpp_2m"
SCHEDULER      = "karras"

# Watchdog
WATCHDOG_THRESHOLD = 0.25   # ✅ Corrigé depuis 0.55
WATCHDOG_MAX_RETRY = 3      # Conservé V1.3

# Seeds par shot (fixer manuellement après test ComfyUI, -1 = auto)
SEEDS_BY_SHOT = {
    1: 527494254591352,  # Départ sprint      frames 0→143
    2: -1,               # Visage transition  frames 144→287
    3: -1,               # Chute              frames 288→431
    4: -1,               # Relèvement         frames 432→623
    5: -1,               # Debout             frames 624→815
    6: -1,               # Reprise jogging    frames 816→1007
}

# ── ZONES ─────────────────────────────────────────────────────────────────────
# (start, end_inclusive, watchdog, master_frame, label, shot_id)
ZONES = [
    (0,    143,  True,  0,    "Départ sprint",     1),
    (144,  287,  False, None, "Visage transition", 2),
    (288,  431,  False, 334,  "Chute",             3),
    (432,  623,  False, None, "Relèvement",        4),
    (624,  815,  False, None, "Debout",            5),
    (816,  1007, True,  816,  "Reprise jogging",   6),
]

def get_zone(frame_num):
    for start, end, watchdog, master_frame, label, shot_id in ZONES:
        if start <= frame_num <= end:
            return watchdog, master_frame, label, shot_id
    return False, None, "Inconnu", 0

def get_seed_for_frame(frame_num, retry=0):
    """Seed par shot + offset retry. -1 → seed aléatoire."""
    import random
    _, _, _, shot_id = get_zone(frame_num)
    base = SEEDS_BY_SHOT.get(shot_id, -1)
    if base == -1:
        return random.randint(0, 2**32 - 1) + retry * 1000
    return base + retry * 1000

# ── PROMPTS V1.7 — PonyXL format ─────────────────────────────────────────────
# Prompt unique pour frames 0→200 (test)
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

# ── AST VALIDATION ────────────────────────────────────────────────────────────
def self_validate():
    with open(__file__, encoding="utf-8") as f:
        src = f.read()
    ast.parse(src)
    print("[OK] AST validation passed")

# ── FLIP DETECTION (conservé V1.3) ───────────────────────────────────────────
def detect_subject_side(img_path, size=(256, 144)):
    if not HAS_PIL:
        return "right"
    try:
        with Image.open(img_path) as _ds:
            img = np.array(_ds.convert("L").resize(size)).astype(float)
        mask = 255.0 - img
        cols = np.arange(size[0])
        total = mask.sum()
        if total < 1:
            return "right"
        center_x = (mask.sum(axis=0) * cols).sum() / total
        return "left" if center_x < size[0] / 2 else "right"
    except Exception:
        return "right"

def maybe_flip_image(img_path, expected_side="right"):
    if not HAS_PIL:
        return False
    side = detect_subject_side(img_path)
    if side != expected_side:
        with Image.open(img_path) as img:
            flipped = ImageOps.mirror(img)
        flipped.save(img_path)
        flipped.close()
        return True
    return False

# ── SSIM WATCHDOG (conservé V1.3, seuil V1.4) ────────────────────────────────
def compute_ssim(img1_path, img2_path, size=(256, 144)):
    if not HAS_PIL:
        return 1.0
    try:
        with Image.open(img1_path) as _s1:
            img1 = np.array(_s1.convert("L").resize(size)).astype(float)
        with Image.open(img2_path) as _s2:
            img2 = np.array(_s2.convert("L").resize(size)).astype(float)
        mu1, mu2 = img1.mean(), img2.mean()
        s1, s2 = img1.std(), img2.std()
        cov = ((img1 - mu1) * (img2 - mu2)).mean()
        c1, c2 = 6.5025, 58.5225
        ssim = ((2*mu1*mu2 + c1) * (2*cov + c2)) / ((mu1**2 + mu2**2 + c1) * (s1**2 + s2**2 + c2))
        return float(ssim)
    except Exception as e:
        print(f"[WARN] SSIM error: {e}")
        return 1.0

# ── COMFYUI HELPERS (conservé V1.3 — urllib natif) ───────────────────────────
def comfy_post(endpoint, data):
    url = f"{COMFY_URL}/{endpoint}"
    payload = json.dumps(data).encode("utf-8")
    req = urllib.request.Request(
        url, data=payload, headers={"Content-Type": "application/json"}
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return json.loads(r.read())
    except urllib.error.HTTPError as e:
        raise RuntimeError(f"HTTP {e.code}: {e.reason} — {e.read().decode()}")

def comfy_get(endpoint):
    url = f"{COMFY_URL}/{endpoint}"
    try:
        with urllib.request.urlopen(url, timeout=30) as r:
            return json.loads(r.read())
    except urllib.error.HTTPError as e:
        raise RuntimeError(f"HTTP {e.code}: {e.reason}")

def wait_for_idle(timeout=300):
    """Polling /queue — conservé V1.3, plus fiable que wait_for_output."""
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

def find_generated(frame_num):
    """Glob avec suffixe variable — conservé V1.3."""
    pattern = os.path.join(COMFY_OUTPUT, f"frame_{frame_num:04d}_*.png")
    existing = sorted(glob.glob(pattern))
    return existing[-1] if existing else None

def copy_to_comfy_input(src_path, name=None):
    dst_name = name or os.path.basename(src_path)
    dst = os.path.join(COMFY_INPUT, dst_name)
    for attempt in range(5):
        try:
            shutil.copy2(src_path, dst)
            return dst_name
        except PermissionError:
            time.sleep(0.5)
    shutil.copy2(src_path, dst)
    return dst_name

def get_skeleton_path(frame_num):
    """Utilise le répertoire remappé 1344x768 si dispo, sinon source."""
    name = f"overlord_skeleton_frame_{frame_num + 1:04d}_00001_.png"
    remap = os.path.join(SKELETONS_REMAP, name)
    if os.path.exists(remap):
        return remap
    return os.path.join(SKELETONS_DIR, name)

# ── REMBG PIL INLINE ────────────────────────────────────────────────────────────────────────────
def prepare_prev_for_i2i(img_path: str) -> str:
    """Isole le personnage sur fond blanc avant VAEEncode img2img."""
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
        out = Image.fromarray(result).convert("RGB")
        tmp = os.path.join(COMFY_INPUT, "_rembg_tmp.png")
        out.save(tmp)
        out.close()
        return tmp
    except Exception as e:
        print(f"[WARN] prepare_prev_for_i2i: {e}")
        return img_path

# ── WORKFLOW BUILDER V1.4 ─────────────────────────────────────────────────────
def get_lineart_filename(frame_num):
    """Retourne le nom du fichier lineart pour la frame donnée."""
    return f"lineart_{frame_num:04d}.png"

def build_workflow(skeleton_filename, output_prefix, seed,
                   ref_image_filename=None, lineart_filename=None,
                   prev_image_filename=None):
    """
    Workflow V1.7 :
    - CLIP Skip (-2)
    - ControlNet OpenPose + ControlNet Lineart en série
    - txt2img (frame 0, denoise=1.0) ou img2img (frames 1+, denoise=0.35 + n-1)
    - IPA optionnel (ref_image_filename)
    """
    w = {
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
                "strength_clip":  LORA_WEIGHT,
            }
        },
        # CLIP Skip -2
        "20": {
            "class_type": "CLIPSetLastLayer",
            "inputs": {"clip": ["2", 1], "stop_at_clip_layer": -2}
        },
        "3": {
            "class_type": "CLIPTextEncode",
            "inputs": {"text": PROMPT_POS, "clip": ["20", 0]}
        },
        "4": {
            "class_type": "CLIPTextEncode",
            "inputs": {"text": PROMPT_NEG, "clip": ["20", 0]}
        },
        # OpenPose skeleton
        "5": {
            "class_type": "LoadImage",
            "inputs": {"image": skeleton_filename, "upload": "image"}
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
        "10": {
            "class_type": "VAELoader",
            "inputs": {"vae_name": VAE}
        },
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

    # ── ControlNet Lineart (chaîné après OpenPose) ──────────────────────────
    if lineart_filename:
        w["17"] = {
            "class_type": "LoadImage",
            "inputs": {"image": lineart_filename, "upload": "image"}
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
    else:
        cn_out = "7"

    # ── img2img : Load Image n-1 → VAEEncode → latent ───────────────────────
    if prev_image_filename:
        w["21"] = {
            "class_type": "LoadImage",
            "inputs": {"image": prev_image_filename, "upload": "image"}
        }
        w["22"] = {
            "class_type": "VAEEncode",
            "inputs": {"pixels": ["21", 0], "vae": ["10", 0]}
        }
        latent_src = ["22", 0]
        denoise = DENOISE_I2I
    else:
        w["8"] = {
            "class_type": "EmptyLatentImage",
            "inputs": {"width": WIDTH, "height": HEIGHT, "batch_size": 1}
        }
        latent_src = ["8", 0]
        denoise = DENOISE_T2I

    # ── IPAdapter (optionnel) ───────────────────────────────────────────────
    if ref_image_filename:
        w["13"] = {
            "class_type": "LoadImage",
            "inputs": {"image": ref_image_filename, "upload": "image"}
        }
        w["14"] = {
            "class_type": "CLIPVisionLoader",
            "inputs": {"clip_name": CLIP_VISION}
        }
        w["23"] = {
            "class_type": "PrepImageForClipVision",
            "inputs": {
                "image":         ["13", 0],
                "interpolation": "LANCZOS",
                "crop_position": "pad",
                "sharpening":    0.0
            }
        }
        w["15"] = {
            "class_type": "IPAdapterModelLoader",
            "inputs": {"ipadapter_file": IPADAPTER}
        }
        w["16"] = {
            "class_type": "IPAdapterAdvanced",
            "inputs": {
                "model":          ["2", 0],
                "ipadapter":      ["15", 0],
                "image":          ["23", 0],
                "clip_vision":    ["14", 0],
                "weight":         IPA_WEIGHT,
                "weight_type":    IPA_WEIGHT_TYPE,
                "combine_embeds": "concat",
                "start_at":       IPA_START,
                "end_at":         IPA_END,
                "embeds_scaling": IPA_EMBEDS,
            }
        }
        model_src = ["16", 0]
    else:
        model_src = ["2", 0]

    # ── KSampler ────────────────────────────────────────────────────────────
    w["9"] = {
        "class_type": "KSampler",
        "inputs": {
            "model":         model_src,
            "positive":      [cn_out, 0],
            "negative":      [cn_out, 1],
            "latent_image":  latent_src,
            "seed": seed, "steps": STEPS, "cfg": CFG,
            "sampler_name": SAMPLER, "scheduler": SCHEDULER,
            "denoise": denoise
        }
    }

    return w

# ── MAIN ──────────────────────────────────────────────────────────────────────
def main():
    parser = argparse.ArgumentParser(description="Ov3rLoRd Batch ControlNet V1.4")
    parser.add_argument("--start",       type=int,  default=0,    help="Frame de départ")
    parser.add_argument("--end",         type=int,  default=None, help="Frame de fin (exclu)")
    parser.add_argument("--no-ipa",      action="store_true", help="Désactiver IP-Adapter")
    parser.add_argument("--no-watchdog", action="store_true", help="Désactiver watchdog SSIM")
    parser.add_argument("--no-flip",     action="store_true", help="Désactiver flip auto")
    parser.add_argument("--dry-run",     action="store_true", help="Test sans générer")
    parser.add_argument(
        "--ipa-source", choices=["rolling", "anchor"], default="rolling",
        help="Source IPAdapter : rolling=frame N-1, anchor=frame 0 fixe (défaut: rolling)"
    )
    parser.add_argument(
        "--set-seed", nargs=2, metavar=("SHOT_ID", "SEED"),
        help="Fixer la seed d'un shot : --set-seed 1 42"
    )
    args = parser.parse_args()

    # ── Fix seed ──────────────────────────────────────────────────────────────
    if args.set_seed:
        sid   = int(args.set_seed[0])
        sval  = int(args.set_seed[1])
        if sid in SEEDS_BY_SHOT:
            SEEDS_BY_SHOT[sid] = sval
            print(f"[batch_controlnet] Seed shot {sid} = {sval}")
            print("[batch_controlnet] ATTENTION : modifie SEEDS_BY_SHOT dans le fichier pour persistance.")
        else:
            print(f"[batch_controlnet] Shot {sid} inconnu.")
        return

    self_validate()
    os.makedirs(COMFY_OUTPUT, exist_ok=True)

    # ── Détection squelettes ──────────────────────────────────────────────────
    # Priorité : répertoire remappé 1344x768, sinon source
    skel_dir = SKELETONS_REMAP if os.path.isdir(SKELETONS_REMAP) else SKELETONS_DIR
    pattern  = os.path.join(skel_dir, "overlord_skeleton_frame_*_*.png")
    skeletons = sorted(glob.glob(pattern))

    if not skeletons:
        # Fallback source
        skel_dir  = SKELETONS_DIR
        pattern   = os.path.join(skel_dir, "overlord_skeleton_frame_*_*.png")
        skeletons = sorted(glob.glob(pattern))

    if not skeletons:
        print(f"[ERREUR] Aucun squelette trouvé dans {skel_dir}")
        sys.exit(1)

    end = args.end if args.end is not None else len(skeletons)
    skeletons_batch = skeletons[args.start:end]
    use_ipa      = not args.no_ipa
    use_watchdog = not args.no_watchdog and HAS_PIL
    use_flip     = not args.no_flip and HAS_PIL

    # Ancre IPAdapter globale (frame 0)
    anchor_path = GLOBAL_ANCHOR if os.path.exists(GLOBAL_ANCHOR) else None

    print(f"╔══════════════════════════════════════════════════════════════╗")
    print(f"║   Ov3rLoRd — Batch ControlNet + IPA + Watchdog V1.9         ║")
    print(f"╚══════════════════════════════════════════════════════════════╝")
    print(f"  Squelettes  : {len(skeletons_batch)} ({skel_dir})")
    print(f"  Frames      : {args.start} → {end-1}")
    print(f"  CN          : strength={CN_STRENGTH} / end={CN_END}  ✅V1.4")
    print(f"  IP-Adapter  : {'✅ ON w=' + str(IPA_WEIGHT) + ' end=' + str(IPA_END) if use_ipa else '❌ OFF'}  ✅V1.4")
    print(f"  IPA source  : {args.ipa_source}")
    print(f"  Watchdog    : {'✅ ON SSIM>' + str(WATCHDOG_THRESHOLD) if use_watchdog else '❌ OFF'}  ✅V1.4")
    print(f"  Flip auto   : {'✅ ON (zones course)' if use_flip else '❌ OFF'}")
    print(f"  Résolution  : {WIDTH}x{HEIGHT}")
    print()
    print(f"  Seeds par shot :")
    for sid, sv in SEEDS_BY_SHOT.items():
        print(f"    Shot {sid} : {sv if sv != -1 else 'ALÉATOIRE (fixer avant batch !)'}")
    print()
    print(f"  Zones :")
    for start, end_z, wd, mf, label, sid in ZONES:
        print(f"    {start:04d}→{end_z:04d}  {label:22s}  watchdog={'ON ' if wd else 'OFF'}  maître={mf}  shot={sid}")
    print()

    if args.dry_run:
        for i, s in enumerate(skeletons_batch[:5]):
            fn = args.start + i
            _, _, label, sid = get_zone(fn)
            seed = get_seed_for_frame(fn)
            print(f"  {fn:04d} → {os.path.basename(s)}  [{label}]  seed={seed}")
        if len(skeletons_batch) > 5:
            print(f"  ... ({len(skeletons_batch)} total)")
        print("\n[DRY RUN] OK")
        return

    # ── Maîtres par zone ──────────────────────────────────────────────────────
    zone_masters = {}
    for start, end_z, wd, mf, label, sid in ZONES:
        if mf is not None:
            existing = find_generated(mf)
            if existing:
                zone_masters[mf] = existing

    prev_path = anchor_path  # Rolling part de l'ancre globale si dispo
    ok = 0
    fail = 0
    watchdog_hits = 0
    flip_count = 0

    for i, skel_path in enumerate(skeletons_batch):
        frame_num = args.start + i
        use_wd_zone, master_frame_id, zone_label, shot_id = get_zone(frame_num)
        active_watchdog = use_watchdog and use_wd_zone
        master_path = zone_masters.get(master_frame_id) if master_frame_id is not None else None

        # Skip si déjà généré
        existing = find_generated(frame_num)
        if existing:
            print(f"  [{frame_num:04d}] SKIP [{zone_label}]")
            if master_frame_id is not None and master_frame_id not in zone_masters:
                zone_masters[master_frame_id] = existing
            prev_path = existing
            ok += 1
            continue

        print(f"  [{frame_num:04d}/{end-1}] [{zone_label}]", end=" → ", flush=True)

        result = None
        score  = 1.0

        for retry in range(WATCHDOG_MAX_RETRY):
            try:
                output_prefix = f"asuka_run/frame_{frame_num:04d}"
                seed = get_seed_for_frame(frame_num, retry)

                # Copie squelette sous nom fixe → force rechargement ComfyUI (cache-buster)
                copy_to_comfy_input(skel_path, "ov_skeleton_current.png")
                skel_filename = "ov_skeleton_current.png"

                # Source IPAdapter
                ref_filename = None
                if use_ipa:
                    if args.ipa_source == "anchor" and anchor_path:
                        ipa_src = anchor_path
                    else:
                        ipa_src = prev_path or anchor_path
                    if ipa_src and os.path.exists(ipa_src):
                        ref_filename = copy_to_comfy_input(
                            ipa_src, "ov_ipa_ref_current.png"
                        )

                # Lineart — cache-buster nom fixe
                la_name = get_lineart_filename(frame_num)
                la_path = os.path.join(LINEART_DIR, la_name)
                lineart_filename = None
                if os.path.exists(la_path):
                    copy_to_comfy_input(la_path, "ov_lineart_current.png")
                    lineart_filename = "ov_lineart_current.png"

                # Mode motion mask (frames 1+) ou txt2img (frame 0)
                if (frame_num > 0 and prev_path and os.path.exists(prev_path)
                        and USE_MOTION_MASK and HAS_MOTION_MASK):

                    # Estimer denoise via diff squelettes
                    skel_prev_path = get_skeleton_path(frame_num - 1)
                    if HAS_DENOISE_EST and os.path.exists(skel_prev_path):
                        la_prev_path = os.path.join(
                            LINEART_DIR, get_lineart_filename(frame_num - 1)
                        )
                        dynamic_denoise = estimate_denoise(
                            skel_prev=skel_prev_path,
                            skel_cur=skel_path,
                            la_prev=la_prev_path if os.path.exists(la_prev_path) else None,
                            la_cur=la_path if os.path.exists(la_path) else None,
                            use_qwen=False,
                        )
                    else:
                        dynamic_denoise = MOTION_DENOISE_FALLBACK

                    # Inpaint zones de mouvement uniquement
                    print(f"\n    [PARAMS] mode=motion_mask denoise={dynamic_denoise:.3f} seed={seed}", flush=True)
                    print(f"    [PARAMS] skel_diff→denoise_est via PIL", flush=True)
                    generated = generate_motion_inpaint(
                        skel_prev=skel_prev_path,
                        skel_cur=skel_path,
                        frame_prev=prev_path,
                        la_cur=la_path if os.path.exists(la_path) else None,
                        output_prefix=output_prefix,
                        frame_num=frame_num,
                        seed=seed,
                        denoise=dynamic_denoise,
                        verbose=False,
                    )
                    if not generated:
                        continue

                else:
                    # Frame 0 ou motion mask indisponible — build_workflow standard
                    prev_img_filename = None
                    if frame_num > 0 and prev_path and os.path.exists(prev_path):
                        cleaned = prepare_prev_for_i2i(prev_path)
                        copy_to_comfy_input(cleaned, "ov_prev_frame_current.png")
                        prev_img_filename = "ov_prev_frame_current.png"

                    mode_str = "txt2img" if frame_num == 0 else "img2img_fallback"
                    denoise_str = f"{DENOISE_T2I}" if frame_num == 0 else f"{DENOISE_I2I}"
                    ipa_str = f"+IPA" if ref_filename else ""
                    la_str = f"+LA" if lineart_filename else ""
                    print(f"\n    [PARAMS] mode={mode_str} denoise={denoise_str} seed={seed}{ipa_str}{la_str} cfg={CFG} steps={STEPS}", flush=True)
                    workflow = build_workflow(
                        skel_filename, output_prefix, seed,
                        ref_image_filename=ref_filename,
                        lineart_filename=lineart_filename,
                        prev_image_filename=prev_img_filename,
                    )
                    wait_for_idle(timeout=60)
                    comfy_post("prompt", {"prompt": workflow})
                    wait_for_idle(timeout=180)

                    generated = find_generated(frame_num)
                    if not generated:
                        continue

                # Flip auto sur zones course
                flipped = False
                if use_flip and use_wd_zone:
                    flipped = maybe_flip_image(generated, expected_side="left")
                    if flipped:
                        flip_count += 1

                # Watchdog SSIM
                if active_watchdog and master_path:
                    score = compute_ssim(master_path, generated)
                    if score < WATCHDOG_THRESHOLD:
                        os.remove(generated)
                        watchdog_hits += 1
                        print(f"⚠SSIM={score:.2f} retry{retry+1}", end="→", flush=True)
                        continue

                result = generated
                break

            except Exception as e:
                import traceback
                print(f"❌ {e}")
                traceback.print_exc()
                fail += 1
                break

        if result:
            tags = "✅"
            if active_watchdog:
                tags += f" SSIM={score:.2f}"
            if use_ipa and prev_path:
                tags += f"+IPA({args.ipa_source})"
            if use_flip and use_wd_zone and flip_count > 0:
                tags += "+FLIP"
            print(tags)

            if master_frame_id is not None and master_frame_id not in zone_masters:
                zone_masters[master_frame_id] = result
                print(f"  [MASTER {zone_label}] → {os.path.basename(result)}")

            prev_path = result
            ok += 1
        else:
            if result is None:
                fail += 1

    print()
    print(f"══════════════════════════════════════════════════════════════")
    print(f"  ✅ Générées      : {ok}")
    print(f"  ❌ Échecs        : {fail}")
    print(f"  ⚠  Watchdog hits : {watchdog_hits}")
    print(f"  🔄 Flips auto    : {flip_count}")
    print(f"  📁 Output        : {COMFY_OUTPUT}")
    print(f"══════════════════════════════════════════════════════════════")

if __name__ == "__main__":
    main()

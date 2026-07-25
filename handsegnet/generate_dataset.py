# ██████╗ ██╗   ██╗██████╗ ██████╗ ██╗      ██████╗ ██████╗ ██████╗
# ██╔═══██╗██║   ██║╚════██╗██╔══██╗██║     ██╔═══██╗██╔══██╗██╔══██╗
# ██║   ██║██║   ██║ █████╔╝██████╔╝██║     ██║   ██║██████╔╝██║  ██║
# ██║   ██║╚██╗ ██╔╝ ╚═══██╗██╔══██╗██║     ██║   ██║██╔══██╗██║  ██║
# ╚██████╔╝ ╚████╔╝ ██████╔╝██║  ██║███████╗╚██████╔╝██║  ██║██████╔╝
# ╚═════╝   ╚═══╝  ╚═════╝ ╚═╝  ╚═╝╚══════╝ ╚═════╝ ╚═╝  ╚═╝╚═════╝
# Ov3rLoRd -- pipeline de production anime autonome (ComfyUI)
# https://github.com/Ov3rLoRd-MLEngineer
#
# generate_dataset.py — HandSegNet (Ov3rLoRd Pipeline)
# Génération batch du dataset mains via l'API ComfyUI.
# Même architecture que footsegnet\generate_dataset.py :
#   wildcards + 1024x1280 buste, fabricatedXL_v70, dpmpp_2m+karras (ADR-003),
#   seeds base + i*137 (ADR-008), archivage copy2 (ADR-007), prompts anglais (ADR-006).
#
# Usage :
#   py -3.12 generate_dataset.py --count 300
#   py -3.12 generate_dataset.py --count 2 --dry-run

import argparse
import json
import random
import re
import shutil
import time
from pathlib import Path

try:
    import requests as _req
    HAS_REQUESTS = True
except ImportError:
    HAS_REQUESTS = False

import sys
_REPO_ROOT = Path(__file__).resolve().parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))
import config

# ── CONFIG ────────────────────────────────────────────────────────────────────
PROJECT         = "handsegnet"
COMFYUI_URL     = "http://127.0.0.1:8188"
COMFYUI_OUTPUT  = str(config.COMFYUI_OUTPUT)

PROJECT_ROOT  = config.HANDSEGNET_ROOT
RAW_DIR       = PROJECT_ROOT / "dataset" / "raw"
MANIFEST_PATH = RAW_DIR / "manifest.json"
PROMPTS_FILE  = PROJECT_ROOT / "prompts_wildcards.txt"
WILDCARDS_DIR = PROJECT_ROOT / "wildcards"

CHECKPOINT  = "fabricatedXL_v70.safetensors"
VAE         = "taesdxl"
SAMPLER     = "dpmpp_2m"
SCHEDULER   = "karras"
STEPS       = 30
CFG         = 6.5
WIDTH       = 1024
HEIGHT      = 1280          # cadrage buste — mains assez grandes pour l'annotation
BASE_SEED   = 515151
SEED_STRIDE = 137           # ADR-008

OUTPUT_PREFIX = f"{PROJECT}/ds_"

NEGATIVE_PROMPT = (
    "worst quality, low quality, blurry, deformed hands, extra fingers, "
    "missing fingers, fused fingers, bad anatomy, mutated hands, "
    "hands out of frame, hands cropped, watermark, signature, text, nsfw"
)

# LoRA anti-mains-difformes (sdxl-wrong-lora, HuggingFace minimaxir, MIT) --
# teste sur 12 seeds rejetes du 1er lot (voir session du 2026-07-25) :
# 4/12 amelioration nette, 0/12 degradation, aucune difference 0.5 vs 0.7 --
# poids 0.5 retenu (le plus leger qui apporte le benefice observe).
LORA_FILE           = "sdxl-wrong-lora.bin"
LORA_WEIGHT_DEFAULT = 0.5
LORA_TRIGGER_NEGATIVE = "wrong"

POLL_INTERVAL = 2.0
POLL_TIMEOUT  = 300

WILDCARD_RE = re.compile(r"__([a-zA-Z0-9_]+)__")


# ── Wildcards ────────────────────────────────────────────────────────────────

def load_templates() -> list[str]:
    if not PROMPTS_FILE.exists():
        raise FileNotFoundError(f"Fichier de prompts introuvable : {PROMPTS_FILE}")
    lines = [
        l.strip() for l in PROMPTS_FILE.read_text(encoding="utf-8").splitlines()
        if l.strip() and not l.strip().startswith("#")
    ]
    if not lines:
        raise ValueError(f"Aucun template dans {PROMPTS_FILE}")
    return lines


def load_wildcard(name: str) -> list[str]:
    path = WILDCARDS_DIR / f"{name}.txt"
    if not path.exists():
        print(f"[{PROJECT}] WARN : wildcard '{name}' introuvable ({path})")
        return []
    return [
        l.strip() for l in path.read_text(encoding="utf-8").splitlines()
        if l.strip() and not l.strip().startswith("#")
    ]


_wildcard_cache: dict[str, list[str]] = {}


def resolve_prompt(template: str, rng: random.Random) -> str:
    def _sub(m: "re.Match") -> str:
        name = m.group(1)
        if name not in _wildcard_cache:
            _wildcard_cache[name] = load_wildcard(name)
        values = _wildcard_cache[name]
        return rng.choice(values) if values else m.group(0)
    return WILDCARD_RE.sub(_sub, template)


# ── Workflow ComfyUI ─────────────────────────────────────────────────────────

def build_txt2img_workflow(positive: str, seed: int, filename_prefix: str,
                            lora_weight: float | None = None) -> dict:
    wf = {
        "1": {"class_type": "CheckpointLoaderSimple",
              "inputs": {"ckpt_name": CHECKPOINT}},
        "2": {"class_type": "VAELoader",
              "inputs": {"vae_name": VAE}},
        "5": {"class_type": "EmptyLatentImage",
              "inputs": {"width": WIDTH, "height": HEIGHT, "batch_size": 1}},
        "7": {"class_type": "VAEDecode",
              "inputs": {"samples": ["6", 0], "vae": ["2", 0]}},
        "8": {"class_type": "SaveImage",
              "inputs": {"images": ["7", 0], "filename_prefix": filename_prefix}},
    }

    model_ref, clip_ref = ["1", 0], ["1", 1]
    negative_text = NEGATIVE_PROMPT
    if lora_weight is not None:
        wf["9"] = {"class_type": "LoraLoader",
                    "inputs": {
                        "model": ["1", 0], "clip": ["1", 1],
                        "lora_name": LORA_FILE,
                        "strength_model": lora_weight, "strength_clip": lora_weight,
                    }}
        model_ref, clip_ref = ["9", 0], ["9", 1]
        negative_text = NEGATIVE_PROMPT + ", " + LORA_TRIGGER_NEGATIVE

    wf["3"] = {"class_type": "CLIPTextEncode", "inputs": {"text": positive, "clip": clip_ref}}
    wf["4"] = {"class_type": "CLIPTextEncode", "inputs": {"text": negative_text, "clip": clip_ref}}
    wf["6"] = {"class_type": "KSampler",
               "inputs": {
                   "model":        model_ref,
                   "positive":     ["3", 0],
                   "negative":     ["4", 0],
                   "latent_image": ["5", 0],
                   "seed":         seed,
                   "steps":        STEPS,
                   "cfg":          CFG,
                   "sampler_name": SAMPLER,
                   "scheduler":    SCHEDULER,
                   "denoise":      1.0,
               }}
    return wf


def submit(workflow: dict) -> str | None:
    try:
        r = _req.post(f"{COMFYUI_URL}/prompt", json={"prompt": workflow}, timeout=30)
        r.raise_for_status()
        return r.json().get("prompt_id")
    except Exception as e:
        print(f"[{PROJECT}] Erreur submit : {e}")
        return None


def wait_and_fetch(prompt_id: str, submit_time: float) -> str | None:
    start = time.time()
    while time.time() - start < POLL_TIMEOUT:
        try:
            r = _req.get(f"{COMFYUI_URL}/history/{prompt_id}", timeout=10)
            r.raise_for_status()
            history = r.json()
            if prompt_id in history:
                outputs = history[prompt_id].get("outputs", {})
                for node_output in outputs.values():
                    for img in node_output.get("images", []):
                        candidate = (Path(COMFYUI_OUTPUT) / img.get("subfolder", "")
                                     / img.get("filename", ""))
                        if candidate.exists() and candidate.stat().st_mtime >= submit_time - 1:
                            return str(candidate)
                return None
        except Exception:
            pass
        time.sleep(POLL_INTERVAL)
    print(f"[{PROJECT}] Timeout après {POLL_TIMEOUT}s (pid={prompt_id})")
    return None


# ── Manifest ─────────────────────────────────────────────────────────────────

def load_manifest() -> dict:
    if MANIFEST_PATH.exists():
        try:
            return json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
        except Exception:
            print(f"[{PROJECT}] WARN : manifest illisible — réinitialisé")
    return {"images": {}}


def save_manifest(manifest: dict) -> None:
    MANIFEST_PATH.write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8"
    )


# ── Boucle principale ────────────────────────────────────────────────────────

def generate_batch(count: int, start_index: int, base_seed: int, dry_run: bool,
                    lora_weight: float | None = LORA_WEIGHT_DEFAULT) -> int:
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    templates = load_templates()
    manifest = load_manifest()
    done = 0

    for i in range(start_index, start_index + count):
        seed = base_seed + i * SEED_STRIDE
        rng = random.Random(seed)
        template = rng.choice(templates)
        prompt = resolve_prompt(template, rng)
        dest_name = f"{PROJECT}_{i:05d}.png"
        dest_path = RAW_DIR / dest_name

        if dest_path.exists():
            print(f"[{PROJECT}] {dest_name} existe déjà — SKIP")
            done += 1
            continue

        print(f"[{PROJECT}] [{i - start_index + 1}/{count}] seed={seed}")
        print(f"[{PROJECT}]   prompt : {prompt[:120]}...")

        if dry_run:
            done += 1
            continue

        wf = build_txt2img_workflow(prompt, seed, f"{OUTPUT_PREFIX}{i:05d}_", lora_weight)
        submit_time = time.time()
        pid = submit(wf)
        if not pid:
            print(f"[{PROJECT}]   échec soumission — SKIP index {i}")
            continue

        out = wait_and_fetch(pid, submit_time)
        if not out:
            print(f"[{PROJECT}]   image non produite — SKIP index {i}")
            continue

        shutil.copy2(out, str(dest_path))     # ADR-007
        manifest["images"][dest_name] = {
            "index": i, "seed": seed, "prompt": prompt, "template": template,
            "comfyui_source": out, "width": WIDTH, "height": HEIGHT,
            "checkpoint": CHECKPOINT,
            "lora": {"file": LORA_FILE, "weight": lora_weight} if lora_weight is not None else None,
        }
        save_manifest(manifest)
        done += 1
        print(f"[{PROJECT}]   OK -> {dest_path}")

    return done


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=f"{PROJECT} — génération dataset via ComfyUI")
    parser.add_argument("--count",       type=int, default=100)
    parser.add_argument("--start-index", type=int, default=0)
    parser.add_argument("--base-seed",   type=int, default=BASE_SEED)
    parser.add_argument("--dry-run",     action="store_true")
    parser.add_argument("--lora-weight", type=float, default=LORA_WEIGHT_DEFAULT,
                         help=f"Poids du LoRA anti-mains-difformes {LORA_FILE} "
                              f"(défaut: {LORA_WEIGHT_DEFAULT}, testé 0.5/0.7 sans différence)")
    parser.add_argument("--no-lora",     action="store_true",
                         help="Désactive le LoRA (comportement du 1er lot, avant test)")
    args = parser.parse_args()

    if not args.dry_run and not HAS_REQUESTS:
        print(f"[{PROJECT}] 'requests' requis (py -3.12 -m pip install requests)")
        raise SystemExit(1)

    lora_weight = None if args.no_lora else args.lora_weight
    lora_suffix = f"(LoRA {LORA_FILE}@{lora_weight})" if lora_weight is not None else "(sans LoRA)"
    n = generate_batch(args.count, args.start_index, args.base_seed, args.dry_run, lora_weight)
    print(f"\n[{PROJECT}] Terminé : {n}/{args.count} images dans {RAW_DIR} {lora_suffix}")

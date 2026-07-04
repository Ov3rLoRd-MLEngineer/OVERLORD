# generate_dataset.py — FaceSegNet (Ov3rLoRd Pipeline)
# Génération batch du dataset visages via l'API ComfyUI.
# Même architecture que footsegnet\generate_dataset.py :
#   wildcards + 1024x1024 portrait, fabricatedXL_v70, dpmpp_2m+karras (ADR-003),
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

# ── CONFIG ────────────────────────────────────────────────────────────────────
PROJECT         = "facesegnet"
COMFYUI_URL     = "http://127.0.0.1:8188"
COMFYUI_OUTPUT  = r"D:\Ov3rLoRd AI\ComfyUI\output"

PROJECT_ROOT  = Path(r"D:\OVERLORD\facesegnet")
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
HEIGHT      = 1024          # portrait carré rapproché — traits du visage grands
BASE_SEED   = 616161
SEED_STRIDE = 137           # ADR-008

OUTPUT_PREFIX = f"{PROJECT}/ds_"

NEGATIVE_PROMPT = (
    "worst quality, low quality, blurry, deformed face, asymmetric eyes, "
    "cross-eyed, bad anatomy, multiple faces, face cropped, back of head, "
    "face out of frame, watermark, signature, text, nsfw"
)

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

def build_txt2img_workflow(positive: str, seed: int, filename_prefix: str) -> dict:
    return {
        "1": {"class_type": "CheckpointLoaderSimple",
              "inputs": {"ckpt_name": CHECKPOINT}},
        "2": {"class_type": "VAELoader",
              "inputs": {"vae_name": VAE}},
        "3": {"class_type": "CLIPTextEncode",
              "inputs": {"text": positive, "clip": ["1", 1]}},
        "4": {"class_type": "CLIPTextEncode",
              "inputs": {"text": NEGATIVE_PROMPT, "clip": ["1", 1]}},
        "5": {"class_type": "EmptyLatentImage",
              "inputs": {"width": WIDTH, "height": HEIGHT, "batch_size": 1}},
        "6": {"class_type": "KSampler",
              "inputs": {
                  "model":        ["1", 0],
                  "positive":     ["3", 0],
                  "negative":     ["4", 0],
                  "latent_image": ["5", 0],
                  "seed":         seed,
                  "steps":        STEPS,
                  "cfg":          CFG,
                  "sampler_name": SAMPLER,
                  "scheduler":    SCHEDULER,
                  "denoise":      1.0,
              }},
        "7": {"class_type": "VAEDecode",
              "inputs": {"samples": ["6", 0], "vae": ["2", 0]}},
        "8": {"class_type": "SaveImage",
              "inputs": {"images": ["7", 0], "filename_prefix": filename_prefix}},
    }


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

def generate_batch(count: int, start_index: int, base_seed: int, dry_run: bool) -> int:
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

        wf = build_txt2img_workflow(prompt, seed, f"{OUTPUT_PREFIX}{i:05d}_")
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
        }
        save_manifest(manifest)
        done += 1
        print(f"[{PROJECT}]   OK → {dest_path}")

    return done


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=f"{PROJECT} — génération dataset via ComfyUI")
    parser.add_argument("--count",       type=int, default=100)
    parser.add_argument("--start-index", type=int, default=0)
    parser.add_argument("--base-seed",   type=int, default=BASE_SEED)
    parser.add_argument("--dry-run",     action="store_true")
    args = parser.parse_args()

    if not args.dry_run and not HAS_REQUESTS:
        print(f"[{PROJECT}] 'requests' requis (py -3.12 -m pip install requests)")
        raise SystemExit(1)

    n = generate_batch(args.count, args.start_index, args.base_seed, args.dry_run)
    print(f"\n[{PROJECT}] Terminé : {n}/{args.count} images dans {RAW_DIR}")

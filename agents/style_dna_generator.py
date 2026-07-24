"""
style_dna_generator.py V1.0 -- Generateur de Style DNA (Run 0b)
Studio Ov3rLoRd
Genere une image de reference de style pur (palette, trait, lumiere)
via ComfyUI. Verrouille le Style DNA pour tous les shots du run.
Sortie : workspace/style/style_dna_{run_id}.png
         workspace/style/style_dna_{run_id}.json
"""

import sys
import json
import time
import logging
import requests
from pathlib import Path
from datetime import datetime
from typing import Optional

_BASE_DIR = Path(__file__).resolve().parent.parent
if str(_BASE_DIR) not in sys.path:
    sys.path.insert(0, str(_BASE_DIR))

COMFY_URL      = "http://127.0.0.1:8188"
STYLE_DIR      = Path("workspace/style")
TIMEOUT_PROMPT = 30
TIMEOUT_POLL   = 120
POLL_INTERVAL  = 3

# ── Profils de style pre-definis ──────────────────────────────────────
STYLE_PRESETS = {
    "evangelion": {
        "label":    "Neon Genesis Evangelion",
        "positive": (
            "neon genesis evangelion art style, gainax animation, "
            "dark atmospheric, desaturated palette, heavy shadows, "
            "angular character design, expressive eyes, industrial backgrounds, "
            "dramatic lighting, film grain, 1990s anime aesthetic, "
            "masterpiece, best quality"
        ),
        "negative": (
            "bright colors, cheerful, moe style, chibi, "
            "3d render, photorealistic, western cartoon, "
            "bad quality, blurry, watermark"
        ),
        "cfg":   7.5,
        "steps": 35,
        "width": 1344,
        "height": 1984,
    },
    "gundam": {
        "label":    "Mobile Suit Gundam",
        "positive": (
            "gundam anime style, sunrise animation, mecha design, "
            "military aesthetic, space opera, clean linework, "
            "bold colors, dynamic action poses, detailed mechanical design, "
            "masterpiece, best quality"
        ),
        "negative": (
            "chibi, moe, cute, photorealistic, 3d render, "
            "bad anatomy, blurry, watermark"
        ),
        "cfg":   7.0,
        "steps": 35,
        "width": 1344,
        "height": 1984,
    },
    "trigger": {
        "label":    "Trigger/SSSS style",
        "positive": (
            "trigger studio anime style, ssss.gridman aesthetic, "
            "vibrant saturated colors, dynamic composition, "
            "expressive character art, kinetic energy, bold outlines, "
            "modern anime, masterpiece, best quality"
        ),
        "negative": (
            "dull colors, static, photorealistic, 3d, "
            "bad quality, blurry, watermark"
        ),
        "cfg":   7.0,
        "steps": 35,
        "width": 1344,
        "height": 1984,
    },
    "shinkai": {
        "label":    "Makoto Shinkai style",
        "positive": (
            "makoto shinkai art style, your name aesthetic, "
            "photorealistic backgrounds, detailed environments, "
            "soft atmospheric lighting, lens flare, bokeh, "
            "emotional atmosphere, cinematic, masterpiece, best quality"
        ),
        "negative": (
            "flat colors, simple backgrounds, bad quality, blurry, "
            "watermark, deformed"
        ),
        "cfg":   7.0,
        "steps": 35,
        "width": 1344,
        "height": 1984,
    },
}


def _comfy_post(endpoint: str, payload: dict, logger: logging.Logger) -> dict:
    try:
        r = requests.post(COMFY_URL + endpoint, json=payload, timeout=TIMEOUT_PROMPT)
        r.raise_for_status()
        return r.json() if r.text else {}
    except requests.exceptions.ConnectionError:
        logger.error("[SDG] ComfyUI inaccessible sur %s", COMFY_URL)
        return {}
    except Exception as e:
        logger.error("[SDG] Erreur POST %s : %s", endpoint, e)
        return {}


def _wait_for_image(prompt_id: str, output_path: Path,
                    logger: logging.Logger) -> bool:
    elapsed = 0
    while elapsed < TIMEOUT_POLL:
        time.sleep(POLL_INTERVAL)
        elapsed += POLL_INTERVAL
        try:
            r = requests.get(COMFY_URL + "/history/" + prompt_id, timeout=10)
            history = r.json()
        except Exception:
            continue
        if prompt_id not in history:
            continue
        outputs = history[prompt_id].get("outputs", {})
        for node_id, node_out in outputs.items():
            for img_info in node_out.get("images", []):
                filename  = img_info.get("filename", "")
                subfolder = img_info.get("subfolder", "")
                if not filename:
                    continue
                try:
                    img_r = requests.get(
                        COMFY_URL + "/view",
                        params={"filename": filename, "subfolder": subfolder,
                                "type": "output"},
                        timeout=30
                    )
                    if img_r.status_code == 200:
                        output_path.parent.mkdir(parents=True, exist_ok=True)
                        output_path.write_bytes(img_r.content)
                        logger.info("[SDG] Style DNA sauvegarde : %s", output_path.name)
                        return True
                except Exception as e:
                    logger.warning("[SDG] Erreur telechargement : %s", e)
    logger.error("[SDG] Timeout %ds pour prompt_id=%s", TIMEOUT_POLL, prompt_id)
    return False


def _build_style_workflow(style: dict, seed: int) -> dict:
    """Workflow ComfyUI pour generation Style DNA pur (pas de personnage)."""
    return {
        "1": {
            "class_type": "CheckpointLoaderSimple",
            "inputs": {"ckpt_name": "fabricatedXL_v70.safetensors"}
        },
        "2": {
            "class_type": "CLIPTextEncode",
            "inputs": {"text": style["positive"], "clip": ["1", 1]}
        },
        "3": {
            "class_type": "CLIPTextEncode",
            "inputs": {"text": style["negative"], "clip": ["1", 1]}
        },
        "4": {
            "class_type": "EmptyLatentImage",
            "inputs": {
                "width":      style["width"],
                "height":     style["height"],
                "batch_size": 1
            }
        },
        "5": {
            "class_type": "KSampler",
            "inputs": {
                "model":        ["1", 0],
                "positive":     ["2", 0],
                "negative":     ["3", 0],
                "latent_image": ["4", 0],
                "seed":         seed,
                "steps":        style["steps"],
                "cfg":          style["cfg"],
                "sampler_name": "dpmpp_2m_sde",
                "scheduler":    "karras",
                "denoise":      1.0
            }
        },
        "6": {
            "class_type": "VAEDecode",
            "inputs": {"samples": ["5", 0], "vae": ["1", 2]}
        },
        "7": {
            "class_type": "SaveImage",
            "inputs": {"images": ["6", 0], "filename_prefix": "style_dna"}
        }
    }


# ── API principale ────────────────────────────────────────────────────

def generate_style_dna(
    style_name:   str  = "evangelion",
    style_config: Optional[dict] = None,
    run_id:       Optional[str]  = None,
    seed:         Optional[int]  = None,
    output_dir:   Optional[Path] = None,
    logger:       Optional[logging.Logger] = None
) -> dict:
    """
    Genere l'image de reference Style DNA pour le run.

    Args:
        style_name  : Preset (evangelion, gundam, trigger, shinkai).
        style_config: Config custom (remplace STYLE_PRESETS).
        run_id      : ID du run pour nommage fichier.
        seed        : Seed fixe. Defaut : timestamp.
        output_dir  : Dossier sortie. Defaut : workspace/style/
        logger      : Logger optionnel.

    Returns:
        dict : style_name, run_id, image_path, json_path, seed, success.
    """
    if logger is None:
        logger = logging.getLogger("style_dna_generator")

    out_dir = output_dir or STYLE_DIR
    out_dir.mkdir(parents=True, exist_ok=True)

    style = style_config or STYLE_PRESETS.get(style_name)
    if not style:
        logger.warning("[SDG] Style inconnu %r -- fallback evangelion", style_name)
        style      = STYLE_PRESETS["evangelion"]
        style_name = "evangelion"

    run_id = run_id or datetime.now().strftime("%Y%m%d_%H%M%S")
    seed   = seed   or (int(datetime.now().timestamp()) % (2**32))

    img_path  = out_dir / ("style_dna_" + run_id + ".png")
    json_path = out_dir / ("style_dna_" + run_id + ".json")

    logger.info("[SDG] Style=%s | run_id=%s | seed=%d", style_name, run_id, seed)

    # Liberer VRAM
    try:
        requests.post(COMFY_URL + "/interrupt", timeout=5)
        requests.post(COMFY_URL + "/free",
                      json={"unload_models": False, "free_memory": True}, timeout=10)
    except Exception:
        pass

    workflow  = _build_style_workflow(style, seed)
    response  = _comfy_post("/prompt", {"prompt": workflow}, logger)
    prompt_id = response.get("prompt_id")

    if not prompt_id:
        logger.error("[SDG] Pas de prompt_id -- ComfyUI inaccessible ?")
        return {"success": False, "style_name": style_name,
                "run_id": run_id, "error": "no_prompt_id"}

    logger.info("[SDG] prompt_id=%s | generation...", prompt_id)
    ok = _wait_for_image(prompt_id, img_path, logger)

    dna = {
        "style_name": style_name,
        "label":      style.get("label", style_name),
        "run_id":     run_id,
        "seed":       seed,
        "cfg":        style["cfg"],
        "steps":      style["steps"],
        "width":      style["width"],
        "height":     style["height"],
        "sampler":    "dpmpp_2m_sde",
        "scheduler":  "karras",
        "checkpoint": "fabricatedXL_v70.safetensors",
        "positive":   style["positive"],
        "negative":   style["negative"],
        "image_path": str(img_path) if ok else None,
        "json_path":  str(json_path),
        "success":    ok,
    }

    try:
        json_path.write_text(
            json.dumps(dna, indent=2, ensure_ascii=False), encoding="utf-8"
        )
        logger.info("[SDG] DNA JSON : %s", json_path.name)
    except Exception as e:
        logger.warning("[SDG] Sauvegarde JSON echouee : %s", e)

    logger.info("[SDG] Style DNA %s -- %s", style_name, "OK" if ok else "ECHEC")
    return dna


def load_style_dna(run_id: str,
                   output_dir: Optional[Path] = None) -> Optional[dict]:
    """Charge un Style DNA existant depuis le disque."""
    out_dir = output_dir or STYLE_DIR
    path    = out_dir / ("style_dna_" + run_id + ".json")
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None


def get_latest_style_dna(output_dir: Optional[Path] = None) -> Optional[dict]:
    """Retourne le Style DNA le plus recent disponible."""
    out_dir = output_dir or STYLE_DIR
    if not out_dir.exists():
        return None
    jsons = sorted(out_dir.glob("style_dna_*.json"),
                   key=lambda p: p.stat().st_mtime, reverse=True)
    if not jsons:
        return None
    try:
        return json.loads(jsons[0].read_text(encoding="utf-8"))
    except Exception:
        return None


# ── CLI standalone ────────────────────────────────────────────────────
if __name__ == "__main__":
    import argparse

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)-8s] %(message)s"
    )
    log_cli = logging.getLogger("style_dna_generator")

    parser = argparse.ArgumentParser(description="Style DNA Generator V1.0 -- Ov3rLoRd")
    parser.add_argument("--style",  type=str, default="evangelion")
    parser.add_argument("--run-id", type=str, default=None)
    parser.add_argument("--seed",   type=int, default=None)
    parser.add_argument("--list",   action="store_true")
    parser.add_argument("--latest", action="store_true")
    args = parser.parse_args()

    if args.list:
        print("Styles disponibles :")
        for k, v in STYLE_PRESETS.items():
            print(f"  {k:12s} -> {v['label']}")
        sys.exit(0)

    if args.latest:
        dna = get_latest_style_dna()
        if dna:
            print(json.dumps(dna, indent=2, ensure_ascii=False))
        else:
            print("[SDG] Aucun Style DNA dans workspace/style/")
        sys.exit(0)

    result = generate_style_dna(
        style_name=args.style,
        run_id=args.run_id,
        seed=args.seed,
        logger=log_cli
    )
    print(json.dumps(result, indent=2, ensure_ascii=False, default=str))

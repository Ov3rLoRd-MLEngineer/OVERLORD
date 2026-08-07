# ██████╗ ██╗   ██╗██████╗ ██████╗ ██╗      ██████╗ ██████╗ ██████╗
# ██╔═══██╗██║   ██║╚════██╗██╔══██╗██║     ██╔═══██╗██╔══██╗██╔══██╗
# ██║   ██║██║   ██║ █████╔╝██████╔╝██║     ██║   ██║██████╔╝██║  ██║
# ██║   ██║╚██╗ ██╔╝ ╚═══██╗██╔══██╗██║     ██║   ██║██╔══██╗██║  ██║
# ╚██████╔╝ ╚████╔╝ ██████╔╝██║  ██║███████╗╚██████╔╝██║  ██║██████╔╝
# ╚═════╝   ╚═══╝  ╚═════╝ ╚═╝  ╚═╝╚══════╝ ╚═════╝ ╚═╝  ╚═╝╚═════╝
# Ov3rLoRd -- pipeline de production anime autonome (ComfyUI)
# https://github.com/Ov3rLoRd-MLEngineer
#
"""
controlnet_preprocess_5060ti.py -- Ov3rLoRd Pipeline

Soumet UN SEUL graphe ComfyUI qui charge simultanement les 5 preprocesseurs
ControlNet demandes en tache 2 (OpenPose/DWPose, DepthAnythingV2, Canny,
Tile, Lineart) sur une image de reference, cible par defaut l'instance
ComfyUI de la RTX 5060 Ti (port 8189) -- voir DOCS/MD/AUDIT_GPU_ALLOCATION.md
§2 : aucun split "device par node" n'existe dans ComfyUI/comfyui_controlnet_aux,
la separation se fait au niveau instance (process ComfyUI entier pinne sur
une carte via CUDA_VISIBLE_DEVICES), pas au niveau node individuel.

Objectif mesurable : les 5 modeles preprocesseurs tiennent charges en meme
temps sur 16 Go sans swap VRAM (a verifier via nvidia-smi pendant le run).
L'instance 5080 (8188, AniSora) n'est pas sollicitee par ce script -- reste
disponible pour la generation principale en parallele.

Necessite l'instance ComfyUI 8189 demarree (D:\\Ov3rLoRd AI\\_launch_comfyui_5060ti.bat).

Usage :
  py -3.12 agents/production_video/controlnet_preprocess_5060ti.py --image ref.png
  py -3.12 agents/production_video/controlnet_preprocess_5060ti.py --image ref.png --output-dir workspace/controlnet_test --comfy-url http://127.0.0.1:8189
"""
import argparse
import json
import logging
import shutil
import sys
import time
import uuid
from pathlib import Path

import requests

_REPO_ROOT = Path(__file__).resolve().parent.parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))
import config

COMFY_URL = "http://127.0.0.1:8189"  # RTX 5060 Ti -- cf. AUDIT_GPU_ALLOCATION.md

log = logging.getLogger("controlnet_preprocess_5060ti")
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

# Node id -> (class_type, label utilise pour filename_prefix + rapport)
PREPROCESSORS = {
    "openpose": "DWPreprocessor",
    "depth":    "DepthAnythingV2Preprocessor",
    "canny":    "CannyEdgePreprocessor",
    "tile":     "TilePreprocessor",
    "lineart":  "LineartStandardPreprocessor",
}


def upload_image(comfy_url, image_path):
    with open(image_path, "rb") as f:
        r = requests.post(
            f"{comfy_url}/upload/image",
            files={"image": (image_path.name, f, "image/png")},
            timeout=30,
        )
    r.raise_for_status()
    return r.json().get("name", image_path.name)


def build_workflow(uploaded_name, resolution=512):
    """
    Un seul LoadImage en entree, 5 branches preprocesseur independantes en
    parallele (meme pattern que pose_generator.py/lineart_extractor.py,
    fusionne dans un seul graphe pour forcer les 5 modeles a etre charges
    ensemble dans le meme process ComfyUI).
    """
    workflow = {
        "load": {
            "class_type": "LoadImage",
            "inputs": {"image": uploaded_name},
        },
        "openpose": {
            "class_type": PREPROCESSORS["openpose"],
            "inputs": {
                "image": ["load", 0],
                "detect_hand": "enable",
                "detect_body": "enable",
                "detect_face": "enable",
                "resolution": resolution,
            },
        },
        "depth": {
            "class_type": PREPROCESSORS["depth"],
            "inputs": {
                "image": ["load", 0],
                "ckpt_name": "depth_anything_v2_vitl.pth",
                "resolution": resolution,
            },
        },
        "canny": {
            "class_type": PREPROCESSORS["canny"],
            "inputs": {
                "image": ["load", 0],
                "low_threshold": 100,
                "high_threshold": 200,
                "resolution": resolution,
            },
        },
        "tile": {
            "class_type": PREPROCESSORS["tile"],
            "inputs": {
                "image": ["load", 0],
                "pyrUp_iters": 3,
                "resolution": resolution,
            },
        },
        "lineart": {
            "class_type": PREPROCESSORS["lineart"],
            "inputs": {
                "image": ["load", 0],
                "guassian_sigma": 6.0,
                "intensity_threshold": 8,
                "resolution": resolution,
            },
        },
    }
    for name in PREPROCESSORS:
        workflow[f"save_{name}"] = {
            "class_type": "SaveImage",
            "inputs": {
                "images": [name, 0],
                "filename_prefix": f"controlnet_test_{name}",
            },
        }
    return workflow


def run(image_path, output_dir, comfy_url, resolution=512, timeout_s=180):
    image_path = Path(image_path)
    if not image_path.exists():
        raise FileNotFoundError(f"Image introuvable : {image_path}")
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    log.info(f"[CN5060] Upload {image_path.name} -> {comfy_url}")
    uploaded_name = upload_image(comfy_url, image_path)

    workflow = build_workflow(uploaded_name, resolution=resolution)
    client_id = str(uuid.uuid4())
    log.info(f"[CN5060] Soumission graphe (5 preprocesseurs : {', '.join(PREPROCESSORS)})")
    r = requests.post(
        f"{comfy_url}/prompt",
        json={"prompt": workflow, "client_id": client_id},
        timeout=30,
    )
    r.raise_for_status()
    resp = r.json()
    if resp.get("error"):
        raise RuntimeError(f"ComfyUI a rejete le graphe : {resp['error']}")
    prompt_id = resp.get("prompt_id")
    log.info(f"[CN5060] prompt_id={prompt_id}")

    t0 = time.time()
    deadline = t0 + timeout_s
    results = {}
    while time.time() < deadline:
        r = requests.get(f"{comfy_url}/history/{prompt_id}", timeout=10)
        if r.status_code == 200:
            hist = r.json()
            if prompt_id in hist:
                outputs = hist[prompt_id].get("outputs", {})
                if len(outputs) >= len(PREPROCESSORS):
                    for name in PREPROCESSORS:
                        images = outputs.get(f"save_{name}", {}).get("images", [])
                        if images:
                            img = images[0]
                            src = config.COMFYUI_OUTPUT / img.get("subfolder", "") / img.get("filename", "")
                            dest = output_dir / f"{name}_{image_path.stem}.png"
                            if src.exists():
                                shutil.copy2(src, dest)
                                results[name] = str(dest)
                    if len(results) == len(PREPROCESSORS):
                        break
        time.sleep(1.5)

    elapsed = time.time() - t0
    missing = set(PREPROCESSORS) - set(results)
    if missing:
        log.warning(f"[CN5060] Preprocesseurs manquants apres {elapsed:.1f}s : {missing}")
    else:
        log.info(f"[CN5060] 5/5 preprocesseurs charges + executes en {elapsed:.1f}s")

    report = {
        "image_source": str(image_path),
        "comfy_url": comfy_url,
        "resolution": resolution,
        "elapsed_s": round(elapsed, 1),
        "outputs": results,
        "missing": sorted(missing),
    }
    report_path = output_dir / "controlnet_5060ti_report.json"
    report_path.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    log.info(f"[CN5060] Rapport -> {report_path}")
    return report


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--image", required=True, help="Image de reference (PNG)")
    p.add_argument("--output-dir", default="workspace/controlnet_test", help="Dossier de sortie")
    p.add_argument("--comfy-url", default=COMFY_URL, help=f"URL ComfyUI (defaut: {COMFY_URL}, instance 5060 Ti)")
    p.add_argument("--resolution", type=int, default=512, help="Resolution des preprocesseurs (defaut: 512)")
    args = p.parse_args()

    run(args.image, args.output_dir, args.comfy_url, resolution=args.resolution)

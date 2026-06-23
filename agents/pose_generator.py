"""
pose_generator.py V1.0
Ov3rLoRd -- Onibaku Gumi
Genere un skeleton OpenPose depuis une image de reference via ComfyUI DWPose.
Usage : py -3.12 pose_generator.py --image ref.png --output workspace/poses/pose_01.png
"""
import json
import time
import uuid
import logging
import argparse
import requests
from pathlib import Path

COMFY_URL = "http://127.0.0.1:8188"
POSES_DIR = Path("workspace/poses")

log = logging.getLogger("pose_generator")


def generate_pose(image_path: str, output_path: str = "") -> str:
    """
    Envoie l'image dans ComfyUI DWPose et recupere le skeleton.
    Retourne le chemin du skeleton sauvegarde.
    """
    image_path = Path(image_path)
    if not image_path.exists():
        raise FileNotFoundError(f"Image introuvable : {image_path}")

    POSES_DIR.mkdir(parents=True, exist_ok=True)
    if not output_path:
        output_path = str(POSES_DIR / f"pose_{image_path.stem}.png")

    # Upload image vers ComfyUI
    log.info(f"[POSE] Upload image -> ComfyUI : {image_path.name}")
    with open(image_path, "rb") as f:
        r = requests.post(
            f"{COMFY_URL}/upload/image",
            files={"image": (image_path.name, f, "image/png")},
            timeout=30,
        )
    r.raise_for_status()
    uploaded_name = r.json().get("name", image_path.name)
    log.info(f"[POSE] Image uploadee : {uploaded_name}")

    # Workflow DWPose -> SaveImage
    client_id = str(uuid.uuid4())
    workflow = {
        "1": {
            "class_type": "LoadImage",
            "inputs": {"image": uploaded_name, "upload": "image"},
        },
        "2": {
            "class_type": "DWPreprocessor",
            "inputs": {
                "image":       ["1", 0],
                "detect_hand": "enable",
                "detect_body": "enable",
                "detect_face": "enable",
                "resolution":  512,
            },
        },
        "3": {
            "class_type": "SaveImage",
            "inputs": {
                "images":          ["2", 0],
                "filename_prefix": f"pose_{image_path.stem}",
            },
        },
    }

    log.info("[POSE] Soumission workflow DWPose...")
    r = requests.post(
        f"{COMFY_URL}/prompt",
        json={"prompt": workflow, "client_id": client_id},
        timeout=30,
    )
    r.raise_for_status()
    prompt_id = r.json().get("prompt_id")
    log.info(f"[POSE] prompt_id={prompt_id}")

    # Poll resultat
    deadline = time.time() + 120
    while time.time() < deadline:
        try:
            r = requests.get(f"{COMFY_URL}/history/{prompt_id}", timeout=10)
            if r.status_code == 200:
                hist = r.json()
                if prompt_id in hist:
                    for node_out in hist[prompt_id].get("outputs", {}).values():
                        images = node_out.get("images", [])
                        if images:
                            img      = images[0]
                            comfy_out = (
                                Path(r"D:\Ov3rLoRd AI\ComfyUI\output")
                                / img.get("subfolder", "")
                                / img.get("filename", "")
                            )
                            if comfy_out.exists():
                                import shutil
                                shutil.copy2(comfy_out, output_path)
                                log.info(f"[POSE] Skeleton sauvegarde -> {output_path}")
                                return output_path
        except Exception as e:
            log.warning(f"[POSE] Poll erreur : {e}")
        time.sleep(2)

    raise TimeoutError("[POSE] Timeout -- DWPose n'a pas repondu en 120s")


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="[POSE] %(asctime)s %(levelname)s -- %(message)s",
    )
    parser = argparse.ArgumentParser(description="Pose Generator -- Ov3rLoRd")
    parser.add_argument("--image",  required=True, help="Image source (photo ou dessin)")
    parser.add_argument("--output", default="",    help="Chemin skeleton de sortie")
    args = parser.parse_args()

    result = generate_pose(args.image, args.output)
    print(f"\nSkeleton genere : {result}")
    print("Pour utiliser dans le pipeline, ajouter dans le job :")
    print(f'  "openpose_path": "{result}"')

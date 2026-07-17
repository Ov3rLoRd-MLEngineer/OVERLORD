"""
pose_generator.py V1.1
Ov3rLoRd -- Onibaku Gumi
Genere un skeleton OpenPose depuis une image de reference via ComfyUI DWPose,
et recupere aussi les keypoints JSON (POSE_KEYPOINT) pour en deriver
automatiquement une bbox pied (voir extract_foot_bbox / --foot-box).
Usage : py -3.12 pose_generator.py --image ref.png --output workspace/poses/pose_01.png
        py -3.12 pose_generator.py --image ref.png --foot-box
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

# Indices OpenPose BODY_18 (ordre COCO utilise par DWPose) pour les chevilles.
FOOT_KEYPOINT_INDICES = {"RAnkle": 10, "LAnkle": 13}

log = logging.getLogger("pose_generator")


def extract_foot_bbox(
    openpose_dict: dict,
    img_width: int | None = None,
    img_height: int | None = None,
    margin: float = 0.05,
    foot_extension: float = 0.12,
    min_confidence: float = 0.1,
    person_index: int = 0,
) -> tuple[int, int, int, int] | None:
    """
    Derive une bbox (x, y, w, h) en pixels autour des chevilles a partir d'un
    dict OpenPose (une entree de la liste renvoyee par DWPreprocessor --
    structure {"people": [...], "canvas_width": .., "canvas_height": ..}).

    Les coordonnees pose_keypoints_2d de DWPose sont normalisees [0,1], pas
    en pixels absolus -- d'ou la multiplication par img_width/img_height.

    Args:
        openpose_dict   : un element de la liste openpose_json (1 par image
                           source envoyee au workflow)
        img_width, img_height : dimensions de l'image cible en pixels. Si
                           omis, utilise canvas_width/canvas_height du dict
                           lui-meme -- toujours a la taille REELLE de l'image
                           d'entree, pas au parametre `resolution` du node
                           (qui ne pilote que l'analyse interne) ; ne les
                           fournir que si l'image cible a ete redimensionnee
                           depuis la generation du skeleton. Selon la version
                           de comfyui_controlnet_aux installee, DWPreprocessor
                           renvoie pose_keypoints_2d soit normalise [0,1],
                           soit deja en pixels absolus -- le format est
                           detecte automatiquement (une valeur > 1.5 ne peut
                           pas etre une coordonnee normalisee).
        margin          : marge relative (fraction de l'image) ajoutee de
                           chaque cote (haut/gauche/droite) autour des points
                           chevilles
        foot_extension  : marge additionnelle vers le BAS uniquement
                           (fraction de la hauteur image) -- la cheville est
                           proche du HAUT du pied, pas de son centre ; une
                           marge symetrique couperait la moitie du pied/de
                           la chaussure
        min_confidence  : confiance minimale pour retenir un keypoint cheville
        person_index    : index de la personne dans people[] (defaut : 0,
                           premiere/seule personne detectee)

    Returns:
        (x, y, w, h) en pixels absolus, ou None si aucune cheville fiable
        n'a ete detectee (personne absente, chevilles occluses, etc.)
    """
    people = openpose_dict.get("people", [])
    if person_index >= len(people):
        return None
    pk = people[person_index].get("pose_keypoints_2d", [])
    if len(pk) < (max(FOOT_KEYPOINT_INDICES.values()) + 1) * 3:
        return None

    if img_width is None:
        img_width = openpose_dict.get("canvas_width")
    if img_height is None:
        img_height = openpose_dict.get("canvas_height")
    if not img_width or not img_height:
        return None

    raw_pts = []
    for idx in FOOT_KEYPOINT_INDICES.values():
        x, y, conf = pk[idx * 3], pk[idx * 3 + 1], pk[idx * 3 + 2]
        if conf >= min_confidence and (x, y) != (0.0, 0.0):
            raw_pts.append((x, y))
    if not raw_pts:
        return None

    # Detection du format plutot qu'hypothese figee : une coordonnee
    # normalisee [0,1] ne peut jamais depasser 1.0.
    normalized = all(x <= 1.5 and y <= 1.5 for x, y in raw_pts)
    if normalized:
        pts = [(x * img_width, y * img_height) for x, y in raw_pts]
    else:
        pts = raw_pts

    xs, ys = [p[0] for p in pts], [p[1] for p in pts]
    x0, x1 = min(xs), max(xs)
    y0, y1 = min(ys), max(ys)

    mx = img_width * margin
    my_top = img_height * margin
    my_bottom = img_height * foot_extension

    x = max(0.0, x0 - mx)
    x1 = min(img_width, x1 + mx)
    y = max(0.0, y0 - my_top)
    y1 = min(img_height, y1 + my_bottom)

    return (int(round(x)), int(round(y)), int(round(x1 - x)), int(round(y1 - y)))


def generate_pose(image_path: str, output_path: str = "") -> tuple[str, str | None]:
    """
    Envoie l'image dans ComfyUI DWPose et recupere le skeleton ET les
    keypoints JSON (POSE_KEYPOINT, expose par le node via son sortie 'ui' --
    pas besoin de brancher un node supplementaire dans le workflow).

    Returns:
        (chemin_skeleton_png, chemin_keypoints_json_ou_None)
    """
    image_path = Path(image_path)
    if not image_path.exists():
        raise FileNotFoundError(f"Image introuvable : {image_path}")

    POSES_DIR.mkdir(parents=True, exist_ok=True)
    if not output_path:
        output_path = str(POSES_DIR / f"pose_{image_path.stem}.png")
    keypoints_path = str(Path(output_path).with_name(f"{Path(output_path).stem}_keypoints.json"))

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

    # Poll resultat -- node "3" (SaveImage) donne le skeleton PNG, node "2"
    # (DWPreprocessor) expose les keypoints via son sortie 'ui' "openpose_json"
    # (json.dumps d'une liste de dicts OpenPose, un par image du batch -- ici 1)
    deadline = time.time() + 120
    while time.time() < deadline:
        try:
            r = requests.get(f"{COMFY_URL}/history/{prompt_id}", timeout=10)
            if r.status_code == 200:
                hist = r.json()
                if prompt_id in hist:
                    outputs = hist[prompt_id].get("outputs", {})
                    images = outputs.get("3", {}).get("images", [])
                    if images:
                        img = images[0]
                        comfy_out = (
                            Path(r"D:\Ov3rLoRd AI\ComfyUI\output")
                            / img.get("subfolder", "")
                            / img.get("filename", "")
                        )
                        if comfy_out.exists():
                            import shutil
                            shutil.copy2(comfy_out, output_path)
                            log.info(f"[POSE] Skeleton sauvegarde -> {output_path}")

                            saved_keypoints_path = None
                            raw_json = outputs.get("2", {}).get("openpose_json", [])
                            if raw_json:
                                try:
                                    openpose_dicts = json.loads(raw_json[0])
                                    Path(keypoints_path).write_text(
                                        json.dumps(openpose_dicts, indent=2),
                                        encoding="utf-8",
                                    )
                                    saved_keypoints_path = keypoints_path
                                    log.info(f"[POSE] Keypoints sauvegardes -> {keypoints_path}")
                                except Exception as e:
                                    log.warning(f"[POSE] Keypoints illisibles : {e}")
                            else:
                                log.warning("[POSE] Pas de openpose_json dans la reponse "
                                            "(version de comfyui_controlnet_aux differente ?)")

                            return output_path, saved_keypoints_path
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
    parser.add_argument("--foot-box", action="store_true",
                        help="Derive et affiche la bbox pied (format --box de infer.py) "
                             "a partir des chevilles detectees")
    parser.add_argument("--foot-box-margin", type=float, default=0.05,
                        help="Marge relative haut/gauche/droite autour des chevilles (defaut 0.05)")
    parser.add_argument("--foot-box-extension", type=float, default=0.12,
                        help="Marge relative vers le bas -- la cheville est en haut du pied, "
                             "pas au centre (defaut 0.12)")
    args = parser.parse_args()

    skeleton_path, keypoints_path = generate_pose(args.image, args.output)
    print(f"\nSkeleton genere : {skeleton_path}")
    print("Pour utiliser dans le pipeline, ajouter dans le job :")
    print(f'  "openpose_path": "{skeleton_path}"')

    if args.foot_box:
        if not keypoints_path:
            print("\n[POSE] Pas de keypoints disponibles -- impossible de deriver la bbox pied.")
        else:
            openpose_dicts = json.loads(Path(keypoints_path).read_text(encoding="utf-8"))
            box = extract_foot_bbox(
                openpose_dicts[0],
                margin=args.foot_box_margin,
                foot_extension=args.foot_box_extension,
            ) if openpose_dicts else None
            if box is None:
                print("\n[POSE] Chevilles non detectees -- pas de bbox pied derivable.")
            else:
                x, y, w, h = box
                print(f"\nBbox pied derivee : {x},{y},{w},{h}")
                print("Pour infer.py :")
                print(f'  py -3.12 infer.py --image {args.image} --box "{x},{y},{w},{h}" --output mask.png')

# _pose_box.py — FootSegNet (Ov3rLoRd Pipeline)
# Dérive la bbox pied (x, y, w, h) d'une image via DWPose, factorisé pour être
# partagé par analyze_errors.py et batch_premask.py (les deux ont besoin de la
# même logique : keypoints déjà en cache -> sinon appel ComfyUI).
#
# Réutilise workspace\poses\pose_<stem>_keypoints.json si déjà présent (évite
# un aller-retour ComfyUI superflu, notamment en re-lançant analyze_errors.py
# plusieurs fois) ; sinon appelle agents.pose_generator.generate_pose(), qui
# nécessite ComfyUI démarré sur 127.0.0.1:8188.

import json
import sys
from pathlib import Path

REPO_ROOT = Path(r"D:\OVERLORD")
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from agents.pose_generator import generate_pose, extract_foot_bbox  # noqa: E402

POSES_DIR = REPO_ROOT / "workspace" / "poses"


def foot_box_for_image(
    image_path: Path,
    margin: float = 0.05,
    extension: float = 0.12,
) -> tuple[int, int, int, int] | None:
    """
    Retourne la bbox pied (x, y, w, h) en pixels absolus pour `image_path`,
    ou None si non dérivable (ComfyUI indisponible, chevilles non détectées).

    Args:
        image_path : image source
        margin      : marge relative haut/gauche/droite (cf. extract_foot_bbox)
        extension   : marge relative vers le bas (cf. extract_foot_bbox)
    """
    image_path = Path(image_path)
    stem = image_path.stem
    keypoints_path = POSES_DIR / f"pose_{stem}_keypoints.json"

    if not keypoints_path.exists():
        try:
            _, generated = generate_pose(
                str(image_path), str(POSES_DIR / f"pose_{stem}.png")
            )
        except Exception as e:
            print(f"[foot_box] Échec pose_generator sur {image_path.name} : {e}")
            return None
        if not generated:
            print(f"[foot_box] Pas de keypoints retournés pour {image_path.name}")
            return None
        keypoints_path = Path(generated)

    try:
        openpose_dicts = json.loads(keypoints_path.read_text(encoding="utf-8"))
    except Exception as e:
        print(f"[foot_box] Keypoints illisibles ({keypoints_path.name}) : {e}")
        return None
    if not openpose_dicts:
        return None

    return extract_foot_bbox(openpose_dicts[0], margin=margin, foot_extension=extension)

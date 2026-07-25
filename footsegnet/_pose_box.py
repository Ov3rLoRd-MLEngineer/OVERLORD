# ██████╗ ██╗   ██╗██████╗ ██████╗ ██╗      ██████╗ ██████╗ ██████╗
# ██╔═══██╗██║   ██║╚════██╗██╔══██╗██║     ██╔═══██╗██╔══██╗██╔══██╗
# ██║   ██║██║   ██║ █████╔╝██████╔╝██║     ██║   ██║██████╔╝██║  ██║
# ██║   ██║╚██╗ ██╔╝ ╚═══██╗██╔══██╗██║     ██║   ██║██╔══██╗██║  ██║
# ╚██████╔╝ ╚████╔╝ ██████╔╝██║  ██║███████╗╚██████╔╝██║  ██║██████╔╝
# ╚═════╝   ╚═══╝  ╚═════╝ ╚═╝  ╚═╝╚══════╝ ╚═════╝ ╚═╝  ╚═╝╚═════╝
# Ov3rLoRd -- pipeline de production anime autonome (ComfyUI)
# https://github.com/Ov3rLoRd-MLEngineer
#
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

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))
import config
REPO_ROOT = config.OVERLORD_ROOT

from agents.pose_generator import generate_pose, extract_foot_bbox  # noqa: E402

POSES_DIR = REPO_ROOT / "workspace" / "poses"


def foot_box_for_image(
    image_path: Path,
    margin: float = 0.05,
    extension: float = 0.12,
    margin_top_px: int | None = None,
    margin_side_px: int | None = None,
    person_index: int | str = 0,
) -> tuple[int, int, int, int] | None:
    """
    Retourne la bbox pied (x, y, w, h) en pixels absolus pour `image_path`,
    ou None si non dérivable (ComfyUI indisponible, chevilles non détectées).

    Args:
        image_path : image source
        margin      : marge relative haut/gauche/droite (cf. extract_foot_bbox)
        extension   : marge relative vers le bas (cf. extract_foot_bbox)
        margin_top_px : marge haute en pixels absolus, remplace la marge
                      relative pour le haut uniquement (cf. extract_foot_bbox ;
                      None = comportement historique, ex. batch_premask.py)
        margin_side_px : marge latérale en pixels absolus, remplace la marge
                      relative gauche/droite (cf. extract_foot_bbox ; None =
                      comportement historique)
        person_index : index de personne, ou "largest" pour cibler la personne
                      avec la plus grande boîte englobante (sujet principal
                      probable — cf. extract_foot_bbox ; 0 = historique)
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

    return extract_foot_bbox(
        openpose_dicts[0], margin=margin, foot_extension=extension,
        margin_top_px=margin_top_px, margin_side_px=margin_side_px,
        person_index=person_index,
    )

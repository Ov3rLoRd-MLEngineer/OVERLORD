# shoe_consistency_checker.py — Ov3rLoRd Pipeline
# Vérifie la cohérence des sneakers (Nike Air Jordan) sur une frame générée
# par rapport à une image de référence, via Qwen-VL.
#
# Contrairement à qwen_prompt_refiner.py (jugement global de la frame),
# ce module fait un jugement CIBLÉ sur une zone précise (les pieds),
# localisée dynamiquement à partir des keypoints du squelette OpenPose
# de la frame courante — pas un rectangle fixe en ratio, car la pose
# change à chaque frame du cycle de course.
#
# Sortie : même format JSON pivot que qwen_prompt_refiner.py
# ({"passed", "issues", "confidence", ...}) pour rester compatible
# avec inpaint_corrector.py.
#
# Usage standalone :
#   py -3.12 agents/shoe_consistency_checker.py \
#       --frame FRAME.png --skeleton SKEL.png --reference SHOE_REF.png
#
# Usage depuis le pipeline batch :
#   from shoe_consistency_checker import check_shoe_consistency
#   result = check_shoe_consistency(frame_path, skeleton_path, reference_path)

import base64
import json
import os
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))
import config

try:
    import requests as _req
    HAS_REQUESTS = True
except ImportError:
    HAS_REQUESTS = False

try:
    import numpy as np
    from PIL import Image
    HAS_PIL = True
except ImportError:
    HAS_PIL = False

# ── CONFIG ────────────────────────────────────────────────────────────────────
OLLAMA_URL   = "http://127.0.0.1:11434"
QWEN_MODEL   = "qwen2.5vl:7b"
OLLAMA_TIMEOUT = 180  # secondes — le premier appel charge le modèle en VRAM, peut être lent

CONFIDENCE_THRESHOLD = 0.70   # confiance minimale pour considérer le jugement fiable
MATCH_THRESHOLD       = 0.70   # en dessous de ce score → mismatch déclaré

# Zone autour des pieds en l'absence de squelette exploitable (repli ratio)
FALLBACK_FEET_ZONE = (0.10, 0.55, 0.80, 0.40)  # x, y, w, h en ratio image entière

SYSTEM_PROMPT = """You are a visual quality inspector for an anime production pipeline.
You compare a character's footwear in a generated frame against a reference shoe image.
You respond ONLY with a JSON object, no markdown, no explanation.

Respond with this exact JSON structure:
{
  "passed": true/false,
  "match_score": 0.0-1.0,
  "issues": ["list of specific mismatches, e.g. 'wrong colorway', 'missing swoosh logo', 'inconsistent between left/right foot'"],
  "confidence": 0.0-1.0,
  "notes": "brief observation"
}

A passed=true result requires match_score >= 0.70 AND both feet showing the same shoe design.
Pay special attention to: silhouette (high-top vs low-top), colorway, logo presence and placement,
sole color, and consistency between the two feet (a common defect is each foot showing a
different shoe due to per-frame generation drift)."""


def image_to_base64(image_path: str) -> str:
    with open(image_path, "rb") as f:
        return base64.b64encode(f.read()).decode("utf-8")


# ── LOCALISATION DYNAMIQUE DES PIEDS VIA SQUELETTE ────────────────────────────

# Indices keypoints OpenPose COCO/Body25 pertinents pour les pieds.
# Body25 : 19=LBigToe 20=LSmallToe 21=LHeel 22=RBigToe 23=RSmallToe 24=RHeel
# Body18 (COCO) n'a pas les pieds détaillés — on retombe sur les chevilles 10/13.
FOOT_KEYPOINT_INDICES_BODY25 = [19, 20, 21, 22, 23, 24]
ANKLE_KEYPOINT_INDICES_COCO  = [10, 13]  # RAnkle, LAnkle


def locate_feet_zone_from_keypoints(
    pose_keypoints: list,
    image_w: int,
    image_h: int,
    margin_ratio: float = 0.06,
    normalized: bool = True,
) -> tuple:
    """
    Calcule une zone rectangulaire (x, y, w, h en pixels) englobant les deux
    pieds à partir d'une liste de keypoints OpenPose [x1,y1,c1, x2,y2,c2, ...].

    Tente d'abord les keypoints pieds détaillés (Body25), retombe sur les
    chevilles (COCO/Body18) si indisponibles, et enfin sur une zone fixe
    si aucun keypoint exploitable n'est trouvé.

    Args:
        pose_keypoints : liste plate [x,y,confidence, ...] format OpenPose
        image_w, image_h : dimensions de l'image source (en pixels)
        margin_ratio : marge autour des points détectés — intentionnellement
                       faible (0.06) pour cibler uniquement les pieds/chaussures
                       sans déborder sur le bas du jean. La zone couvre environ
                       cheville + chaussure uniquement, pas le mollet.
        normalized : True si x/y dans pose_keypoints sont normalisés (0-1),
                     comme produit par SavePoseKpsAsJsonFile.

    Returns:
        ((x, y, w, h), source_str) en pixels absolus
    """
    def _extract(indices):
        pts = []
        for idx in indices:
            base = idx * 3
            if base + 2 < len(pose_keypoints):
                x, y, conf = pose_keypoints[base:base + 3]
                if conf > 0.1 and (x > 0 or y > 0):
                    if normalized:
                        x, y = x * image_w, y * image_h
                    pts.append((x, y))
        return pts

    points = _extract(FOOT_KEYPOINT_INDICES_BODY25)
    source = "feet_body25"

    if not points:
        points = _extract(ANKLE_KEYPOINT_INDICES_COCO)
        source = "ankles_coco"

    if not points:
        # Repli total : zone fixe basse de l'image (où sont statistiquement
        # les pieds vu le cadrage "full body, side view, run" du prompt)
        x = int(FALLBACK_FEET_ZONE[0] * image_w)
        y = int(FALLBACK_FEET_ZONE[1] * image_h)
        w = int(FALLBACK_FEET_ZONE[2] * image_w)
        h = int(FALLBACK_FEET_ZONE[3] * image_h)
        return (x, y, w, h), "fallback_fixed_ratio"

    xs = [p[0] for p in points]
    ys = [p[1] for p in points]
    min_x, max_x = min(xs), max(xs)
    min_y, max_y = min(ys), max(ys)

    # Marge horizontale faible : juste assez pour le contour de chaque chaussure
    margin_x = int((max_x - min_x + 1) * margin_ratio) + int(0.03 * image_w)

    # Marge vers le haut : légère (on est à la cheville, la chaussure est en dessous)
    margin_y_up = int(0.02 * image_h)

    # Hauteur vers le bas fixe : une Jordan 1 high-top fait ~12% de hauteur d'image
    # en cadrage full body 1024×1536 — indépendant de l'écartement inter-chevilles.
    shoe_height_estimate = int(0.12 * image_h)

    x  = max(0, int(min_x) - margin_x)
    y  = max(0, int(min_y) - margin_y_up)
    x2 = min(image_w, int(max_x) + margin_x)
    y2 = min(image_h, int(max_y) + shoe_height_estimate)

    return (x, y, x2 - x, y2 - y), source


def load_pose_keypoints_from_json(pose_json_path: str) -> tuple[list | None, int | None, int | None]:
    """
    Charge les keypoints depuis un fichier produit par SavePoseKpsAsJsonFile
    (comfyui_controlnet_aux). Format réel observé :

        [{"people": [{"pose_keypoints_2d": [x,y,c, ...], ...}],
          "canvas_width": W, "canvas_height": H}]

    C'est une LISTE contenant un seul objet (pas l'objet directement), et
    les coordonnées x/y sont NORMALISÉES entre 0 et 1 (pas en pixels absolus) —
    il faut les multiplier par canvas_width/canvas_height pour obtenir des pixels.

    Retourne (keypoints_normalisés, canvas_width, canvas_height), ou
    (None, None, None) si le fichier est absent ou illisible.
    """
    if not Path(pose_json_path).exists():
        return None, None, None
    try:
        with open(pose_json_path, encoding="utf-8") as f:
            raw = json.load(f)

        # Le format réel est une liste [ {...} ] — on prend le premier élément.
        # On garde un repli sur l'ancien format hypothétique (dict direct ou
        # liste sous "people" à la racine) au cas où une autre version du
        # nœud produirait une structure différente.
        if isinstance(raw, list):
            entry = raw[0] if raw else {}
        elif isinstance(raw, dict):
            entry = raw
        else:
            return None, None, None

        people = entry.get("people", [])
        if not people:
            return None, None, None

        keypoints = people[0].get("pose_keypoints_2d")
        canvas_w  = entry.get("canvas_width")
        canvas_h  = entry.get("canvas_height")
        return keypoints, canvas_w, canvas_h
    except Exception as e:
        print(f"[shoe_checker] Erreur lecture pose JSON : {e}")
        return None, None, None


def crop_feet_region(
    frame_path: str,
    zone: tuple,
    output_path: str = None,
) -> str | None:
    """Découpe la zone pieds calculée et sauvegarde un crop pour Qwen-VL."""
    if not HAS_PIL:
        return None
    try:
        x, y, w, h = zone
        with Image.open(frame_path) as img:
            img = img.convert("RGB")
            crop = img.crop((x, y, x + w, y + h))
            tmp_dir = config.WORKSPACE_DIR / "tmp"
            tmp_dir.mkdir(parents=True, exist_ok=True)
            out = output_path or str(tmp_dir / f"_feet_crop_{Path(frame_path).stem}.png")
            crop.save(out)
            return out
    except Exception as e:
        print(f"[shoe_checker] Erreur crop : {e}")
        return None


# ── APPEL QWEN-VL ──────────────────────────────────────────────────────────────

def ask_qwen_shoe_match(
    feet_crop_path: str,
    reference_shoe_path: str,
    model: str = QWEN_MODEL,
) -> dict | None:
    """Compare le crop pieds à la référence sneaker via Qwen-VL."""
    if not HAS_REQUESTS:
        print("[shoe_checker] requests indisponible")
        return None

    if not Path(feet_crop_path).exists() or not Path(reference_shoe_path).exists():
        print("[shoe_checker] Image manquante (crop ou référence)")
        return None

    img_crop_b64 = image_to_base64(feet_crop_path)
    img_ref_b64  = image_to_base64(reference_shoe_path)

    payload = {
        "model": model,
        "prompt": (
            f"{SYSTEM_PROMPT}\n\n"
            "Image 1 is the reference shoe (Nike Air Jordan) the character should wear.\n"
            "Image 2 is a crop of the character's feet from the generated frame.\n"
            "Compare them and respond ONLY with JSON."
        ),
        "images": [img_ref_b64, img_crop_b64],
        "stream": False,
        "options": {"temperature": 0.1},
    }

    try:
        r = _req.post(f"{OLLAMA_URL}/api/generate", json=payload, timeout=OLLAMA_TIMEOUT)
        r.raise_for_status()
        raw = r.json().get("response", "")
        return _parse_json_response(raw)
    except _req.exceptions.Timeout:
        print(f"[shoe_checker] Ollama {model} timeout après {OLLAMA_TIMEOUT}s — "
              f"le modèle est peut-être en cours de chargement, réessayer")
    except Exception as e:
        print(f"[shoe_checker] Ollama {model} erreur : {e}")

    return None


def _parse_json_response(raw: str) -> dict | None:
    raw = raw.strip()
    for fence in ["```json", "```"]:
        raw = raw.replace(fence, "")
    raw = raw.strip()
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        start = raw.find("{")
        end   = raw.rfind("}") + 1
        if start >= 0 and end > start:
            try:
                return json.loads(raw[start:end])
            except Exception:
                pass
    print(f"[shoe_checker] Impossible de parser la réponse : {raw[:200]}")
    return None


# ── PIPELINE COMPLET ───────────────────────────────────────────────────────────

def check_shoe_consistency(
    frame_path: str,
    reference_shoe_path: str,
    pose_keypoints: list = None,
    pose_json_path: str = None,
    image_w: int = 1024,
    image_h: int = 1536,
    verbose: bool = False,
) -> dict:
    """
    Pipeline complet : localise les pieds, crop, interroge Qwen-VL, retourne
    un diagnostic au format pivot compatible inpaint_corrector.py.

    La zone pieds est calculée dynamiquement via les keypoints du squelette
    (passés directement ou chargés depuis un export JSON produit par le nœud
    SavePoseKpsAsJsonFile de comfyui_controlnet_aux). En l'absence de
    keypoints exploitables, une zone fixe de repli est utilisée.

    IMPORTANT : si pose_json_path est fourni, les dimensions canvas_width/
    canvas_height contenues DANS le fichier JSON priment sur image_w/image_h
    passés en paramètre — le JSON est la source de vérité sur la résolution
    réelle à laquelle le squelette a été calculé, qui peut différer de la
    résolution de travail standard du pipeline (observé : 1536x2304 sur un
    test, alors que la config standard est 1024x1536).

    Returns:
        {
            "passed": bool,
            "match_score": float,
            "issues": list[str],
            "confidence": float,
            "zone": (x, y, w, h),       # zone pieds en pixels, pour inpaint_corrector
            "zone_source": str,          # "feet_body25" | "ankles_coco" | "fallback_fixed_ratio"
            "notes": str,
        }
    """
    if pose_keypoints is None and pose_json_path:
        pose_keypoints, json_w, json_h = load_pose_keypoints_from_json(pose_json_path)
        if json_w and json_h:
            if verbose and (json_w != image_w or json_h != image_h):
                print(f"[shoe_checker] Résolution du JSON ({json_w}x{json_h}) "
                      f"différente de celle passée en paramètre ({image_w}x{image_h}) "
                      f"— utilisation de celle du JSON")
            image_w, image_h = json_w, json_h

    if pose_keypoints:
        zone, zone_source = locate_feet_zone_from_keypoints(
            pose_keypoints, image_w, image_h, normalized=True
        )
    else:
        x = int(FALLBACK_FEET_ZONE[0] * image_w)
        y = int(FALLBACK_FEET_ZONE[1] * image_h)
        w = int(FALLBACK_FEET_ZONE[2] * image_w)
        h = int(FALLBACK_FEET_ZONE[3] * image_h)
        zone, zone_source = (x, y, w, h), "fallback_fixed_ratio"

    if verbose:
        print(f"[shoe_checker] Zone pieds ({zone_source}) : {zone}")

    crop_path = crop_feet_region(frame_path, zone)
    if not crop_path:
        return _make_unavailable_result(zone, zone_source, "crop_failed")

    analysis = ask_qwen_shoe_match(crop_path, reference_shoe_path)
    if analysis is None:
        return _make_unavailable_result(zone, zone_source, "qwen_unavailable")

    match_score = float(analysis.get("match_score", 0.0))
    confidence  = float(analysis.get("confidence", 0.0))
    issues      = analysis.get("issues", [])
    passed      = bool(analysis.get("passed", match_score >= MATCH_THRESHOLD))

    if confidence < CONFIDENCE_THRESHOLD and verbose:
        print(f"[shoe_checker] Confiance faible ({confidence:.2f}) — jugement peu fiable")

    result = {
        "passed":      passed,
        "match_score": round(match_score, 3),
        "issues":      issues,
        "confidence":  round(confidence, 3),
        "zone":        zone,
        "zone_source": zone_source,
        "notes":       analysis.get("notes", ""),
    }

    if verbose:
        status = "PASS" if passed else "MISMATCH"
        print(f"[shoe_checker] {status} | score={match_score:.2f} | conf={confidence:.2f}")
        for iss in issues:
            print(f"  - {iss}")

    return result


def _make_unavailable_result(zone: tuple, zone_source: str, reason: str) -> dict:
    return {
        "passed":      True,   # fail-open : ne bloque pas le pipeline si Qwen-VL est indisponible
        "match_score": -1.0,
        "issues":      [],
        "confidence":  0.0,
        "zone":        zone,
        "zone_source": zone_source,
        "notes":       f"unavailable: {reason}",
    }


# ── CLI ───────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Ov3rLoRd — Shoe Consistency Checker")
    parser.add_argument("--frame",     required=True, help="Frame générée à vérifier")
    parser.add_argument("--reference", required=True, help="Image de référence de la sneaker")
    parser.add_argument("--pose-json", default=None, help="Export POSE_KEYPOINT JSON (optionnel)")
    parser.add_argument("--width",     type=int, default=1024)
    parser.add_argument("--height",    type=int, default=1536)
    parser.add_argument("--verbose",   action="store_true")
    args = parser.parse_args()

    result = check_shoe_consistency(
        frame_path=args.frame,
        reference_shoe_path=args.reference,
        pose_json_path=args.pose_json,
        image_w=args.width,
        image_h=args.height,
        verbose=True,
    )
    print(f"\nRésultat :\n{json.dumps(result, indent=2, ensure_ascii=False)}")

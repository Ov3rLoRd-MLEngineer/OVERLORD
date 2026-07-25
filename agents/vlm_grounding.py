# vlm_grounding.py — Grounding par texte libre via VLM Ollama (Ov3rLoRd Pipeline)
#
# Factorisation pipeline du client validé dans
# tests\bottes_generiques\grounding_qwenvl_test.py (2026-07-14) : demander à
# qwen2.5vl la bbox d'un objet décrit en langage naturel, en pixels absolus.
# Usage principal : fallback de bbox quand la détection pose DWPose échoue
# (batch_premask des projets *segnet), ou source de bbox directe pour les
# parties sans helper pose (mains, visage, corps).
#
# Leçons du test de validation (8 images en échec DWPose) :
# - `found`/`confidence` auto-déclarés ne sont PAS discriminants (toujours
#   "high", y compris sur un faux positif) — ne jamais filtrer dessus.
#   Le NOT_FOUND est en revanche un vrai signal.
# - Requête neutre sans couleur ("the character's shoes", pas "yellow boots") :
#   une couleur précise déclenche la complaisance (objet vert déclaré jaune).
# - ~2-3 s/image une fois le modèle chargé (~11 s au premier appel).
#
# ADR-006 : prompt en anglais (les prompts français augmentent le taux de
# JSON invalide), réponse forcée en JSON via le paramètre "format" d'Ollama.

import base64
import json
from pathlib import Path

import requests
from PIL import Image

import sys
_REPO_ROOT = Path(__file__).resolve().parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))
import config

# ── CONFIG ────────────────────────────────────────────────────────────────────
ENDPOINTS_CFG = config.OVERLORD_ROOT / "config" / "llm_endpoints.json"

DEFAULT_MODEL   = "qwen2.5vl:7b"
DEFAULT_TIMEOUT = 240   # s par image — modèle vision 7B
DEFAULT_MARGIN  = 20    # px ajoutés autour de la bbox par grounding_box()
OLLAMA_URL_FALLBACK = "http://127.0.0.1:11434"

# Width/height réels injectés dans le prompt pour ancrer les coordonnées
# (sans eux, le modèle répond des bbox génériques/normalisées).
PROMPT_TEMPLATE = """You are a precise visual grounding assistant for an anime illustration pipeline.
The image is exactly {width} pixels wide and {height} pixels tall.

Task: locate "{obj}" in the image.
- Target the MAIN (largest, foreground) character; ignore secondary characters, mascots and background objects.
- If several instances belong to the target (e.g. both hands, both boots of a pair), return ONE bounding box that encloses ALL of them.
- The box must be tight but complete: include the full visible extent of the object.

Coordinates MUST be absolute pixel values relative to this exact {width}x{height} image: x between 0 and {width}, y between 0 and {height}. Do NOT return normalized values or values in a 0-1000 range.

Reply with a JSON object only:
{{"found": true, "bbox": [x1, y1, x2, y2], "confidence": "high" | "medium" | "low", "description": "<one short sentence: what the box contains and where it is>"}}
If the object is not visible at all, reply:
{{"found": false, "bbox": null, "confidence": "high" | "medium" | "low", "description": "<why it was not found>"}}"""

# Variante multi-instance : une bbox PAR occurrence (chaque pied, chaque main)
# au lieu d'une boîte englobante unique — celle-ci devient énorme ou mal
# centrée dès que les instances sont éloignées (pied levé, poings écartés),
# cause des 10 pires IoU du run de validation footsegnet 2026-07-14.
PROMPT_MULTI_TEMPLATE = """You are a precise visual grounding assistant for an anime illustration pipeline.
The image is exactly {width} pixels wide and {height} pixels tall.

Task: locate EVERY individual instance of "{obj}" in the image.
- Target the MAIN (largest, foreground) character; ignore secondary characters, mascots and background objects.
- Return ONE bounding box PER instance: e.g. one box for the left boot and one for the right boot, one box per hand. Do NOT merge distant instances into a single large box.
- If the instances touch or overlap (feet side by side), a single box covering them is acceptable.
- Each box must be tight but complete: include the full visible extent of that instance.

Coordinates MUST be absolute pixel values relative to this exact {width}x{height} image: x between 0 and {width}, y between 0 and {height}. Do NOT return normalized values or values in a 0-1000 range.

Reply with a JSON object only:
{{"found": true, "instances": [{{"bbox": [x1, y1, x2, y2], "label": "<short name, e.g. left hand>"}}, ...], "confidence": "high" | "medium" | "low", "description": "<one short sentence>"}}
If the object is not visible at all, reply:
{{"found": false, "instances": [], "confidence": "high" | "medium" | "low", "description": "<why it was not found>"}}"""

MAX_INSTANCES = 6   # garde-fou contre les listes pathologiques du modèle

# Vérification anti-boîte-fantôme : le prompt multi-instance pousse le modèle
# à répondre 2 boîtes même quand une seule instance est visible (complaisance
# — régressions 00287/00298 du re-run 2026-07-14 : 2e boîte sur cuisse/genou
# quand le 2e pied est occulté). Chaque boîte est recadrée et soumise à un
# contrôle strict "ce crop contient-il vraiment l'objet ?" — description
# d'abord (ancre l'analyse, même pattern que check_masks_qwenvl) puis verdict.
PROMPT_VERIFY_TEMPLATE = """You are a strict visual inspector for an anime illustration pipeline.
This image is a small CROP taken from a larger illustration.

FIRST describe what the crop actually shows, THEN judge whether it clearly contains "{obj}" (fully or partially visible).
Be strict: if the crop shows only skin, a thigh, a knee, clothing, or background with no actual "{obj}", answer false. Do not guess from context outside the crop: judge only what is visible in it.

Reply with a JSON object only:
{{"content": "<short description of what the crop shows>", "contains": true | false}}"""


def load_ollama_url() -> str:
    """URL Ollama depuis config\\llm_endpoints.json, sinon fallback local."""
    try:
        cfg = json.loads(ENDPOINTS_CFG.read_text(encoding="utf-8"))
        url = cfg.get("ollama", {}).get("url")
        if url:
            return url.rstrip("/")
    except Exception as e:
        print(f"[vlm_grounding] WARN : {ENDPOINTS_CFG.name} illisible ({e}) — "
              f"fallback {OLLAMA_URL_FALLBACK}")
    return OLLAMA_URL_FALLBACK


def _coerce_bbox(raw_bbox, width: int, height: int) -> tuple[int, int, int, int] | None:
    """
    Valide/normalise la bbox retournée par le modèle en [x1, y1, x2, y2]
    pixels absolus entiers, clampée aux bords. Retourne None si inexploitable.
    Gère le repli où le modèle répond malgré tout en normalisé [0, 1].
    """
    if not isinstance(raw_bbox, (list, tuple)) or len(raw_bbox) != 4:
        return None
    try:
        coords = [float(v) for v in raw_bbox]
    except (TypeError, ValueError):
        return None

    # Repli : coordonnées normalisées [0, 1] malgré la consigne
    if all(0.0 <= c <= 1.0 for c in coords) and max(coords) > 0.0:
        coords = [coords[0] * width, coords[1] * height,
                  coords[2] * width, coords[3] * height]

    x1, y1, x2, y2 = coords
    if x2 < x1:
        x1, x2 = x2, x1
    if y2 < y1:
        y1, y2 = y2, y1
    x1 = max(0, min(int(round(x1)), width - 1))
    x2 = max(0, min(int(round(x2)), width))
    y1 = max(0, min(int(round(y1)), height - 1))
    y2 = max(0, min(int(round(y2)), height))
    if x2 - x1 < 4 or y2 - y1 < 4:   # boîte dégénérée
        return None
    return (x1, y1, x2, y2)


def _call_vlm(image_bytes: bytes, prompt: str, model: str, timeout: int,
              ollama_url: str) -> tuple[dict | None, str]:
    """Appel Ollama commun (image + prompt, JSON forcé).
    Retourne (données JSON, "") ou (None, raison d'erreur)."""
    payload = {
        "model": model,
        "prompt": prompt,
        "images": [base64.b64encode(image_bytes).decode("ascii")],
        "format": "json",
        "stream": False,
        "options": {"temperature": 0.0},
    }
    try:
        r = requests.post(f"{ollama_url}/api/generate", json=payload,
                          timeout=timeout)
        r.raise_for_status()
        raw = r.json().get("response", "")
    except Exception as e:
        return None, f"appel Ollama échoué : {e}"
    try:
        return json.loads(raw), ""
    except Exception:
        return None, f"JSON invalide : {raw.strip()[:200]}"


def _image_size(image_path: Path) -> tuple[int, int] | None:
    try:
        with Image.open(image_path) as im:
            return im.size
    except Exception:
        return None


def ask_grounding(image_path: Path | str, obj: str,
                  model: str = DEFAULT_MODEL, timeout: int = DEFAULT_TIMEOUT,
                  ollama_url: str | None = None) -> dict:
    """
    Demande au VLM la bbox de `obj` dans l'image. Retourne un dict :
      status      : OK | NOT_FOUND | ERROR
      bbox        : (x1, y1, x2, y2) pixels absolus, ou None
      confidence  : confiance qualitative auto-déclarée (NON discriminante,
                    ne pas filtrer dessus — cf. en-tête)
      description : description courte du modèle
      reason      : détail en cas d'ERROR/NOT_FOUND
    """
    image_path = Path(image_path)
    if ollama_url is None:
        ollama_url = load_ollama_url()

    size = _image_size(image_path)
    if size is None:
        return {"status": "ERROR", "bbox": None, "confidence": "",
                "description": "", "reason": "image illisible"}
    width, height = size

    prompt = PROMPT_TEMPLATE.format(obj=obj, width=width, height=height)
    data, err = _call_vlm(image_path.read_bytes(), prompt, model, timeout,
                          ollama_url)
    if data is None:
        return {"status": "ERROR", "bbox": None, "confidence": "",
                "description": "", "reason": err}

    confidence = str(data.get("confidence", "")).strip().lower()
    description = str(data.get("description", "")).strip()

    if data.get("found") is False:
        return {"status": "NOT_FOUND", "bbox": None, "confidence": confidence,
                "description": description,
                "reason": description or "objet non trouvé"}

    bbox = _coerce_bbox(data.get("bbox"), width, height)
    if bbox is None:
        return {"status": "ERROR", "bbox": None, "confidence": confidence,
                "description": description,
                "reason": f"bbox inexploitable : {data.get('bbox')!r}"}

    return {"status": "OK", "bbox": bbox, "confidence": confidence,
            "description": description, "reason": ""}


def ask_grounding_multi(image_path: Path | str, obj: str,
                        model: str = DEFAULT_MODEL,
                        timeout: int = DEFAULT_TIMEOUT,
                        ollama_url: str | None = None) -> dict:
    """
    Variante multi-instance : une bbox PAR occurrence de `obj` (chaque pied,
    chaque main). Retourne un dict :
      status      : OK | NOT_FOUND | ERROR
      bboxes      : liste de (x1, y1, x2, y2) pixels absolus (vide sauf OK),
                    plafonnée à MAX_INSTANCES, bbox invalides écartées
      confidence  : confiance auto-déclarée (non discriminante)
      description : description courte du modèle
      reason      : détail en cas d'ERROR/NOT_FOUND
    """
    image_path = Path(image_path)
    if ollama_url is None:
        ollama_url = load_ollama_url()

    size = _image_size(image_path)
    if size is None:
        return {"status": "ERROR", "bboxes": [], "confidence": "",
                "description": "", "reason": "image illisible"}
    width, height = size

    prompt = PROMPT_MULTI_TEMPLATE.format(obj=obj, width=width, height=height)
    data, err = _call_vlm(image_path.read_bytes(), prompt, model, timeout,
                          ollama_url)
    if data is None:
        return {"status": "ERROR", "bboxes": [], "confidence": "",
                "description": "", "reason": err}

    confidence = str(data.get("confidence", "")).strip().lower()
    description = str(data.get("description", "")).strip()

    if data.get("found") is False:
        return {"status": "NOT_FOUND", "bboxes": [], "confidence": confidence,
                "description": description,
                "reason": description or "objet non trouvé"}

    instances = data.get("instances")
    if not isinstance(instances, list):
        return {"status": "ERROR", "bboxes": [], "confidence": confidence,
                "description": description,
                "reason": f"instances inexploitables : {instances!r}"}

    bboxes = []
    for inst in instances[:MAX_INSTANCES]:
        raw = inst.get("bbox") if isinstance(inst, dict) else inst
        bbox = _coerce_bbox(raw, width, height)
        if bbox is not None:
            bboxes.append(bbox)
    if not bboxes:
        return {"status": "ERROR", "bboxes": [], "confidence": confidence,
                "description": description,
                "reason": "aucune bbox valide dans les instances"}

    return {"status": "OK", "bboxes": bboxes, "confidence": confidence,
            "description": description, "reason": ""}


def grounding_box(image_path: Path | str, obj: str,
                  margin_px: int = DEFAULT_MARGIN,
                  model: str = DEFAULT_MODEL, timeout: int = DEFAULT_TIMEOUT,
                  ollama_url: str | None = None) -> tuple[int, int, int, int] | None:
    """
    Version pipeline de ask_grounding() : retourne directement une zone
    (x, y, w, h) en pixels absolus avec `margin_px` de marge sur chaque côté
    (même format que foot_box_for_image / le paramètre `zone` des infer.py),
    ou None si le grounding échoue ou ne trouve rien. La confiance
    auto-déclarée est volontairement ignorée (non discriminante).
    """
    res = ask_grounding(image_path, obj, model=model, timeout=timeout,
                        ollama_url=ollama_url)
    if res["bbox"] is None:
        if res["status"] != "OK":
            print(f"[vlm_grounding] {Path(image_path).name} : {res['status']}"
                  f" — {res['reason']}")
        return None
    return _to_zone(res["bbox"], margin_px)


def _to_zone(bbox_xyxy: tuple[int, int, int, int],
             margin_px: int) -> tuple[int, int, int, int]:
    x1, y1, x2, y2 = bbox_xyxy
    return (x1 - margin_px, y1 - margin_px,
            (x2 - x1) + 2 * margin_px, (y2 - y1) + 2 * margin_px)


def verify_crop(image_path: Path | str, zone: tuple[int, int, int, int],
                obj: str, model: str = DEFAULT_MODEL,
                timeout: int = DEFAULT_TIMEOUT,
                ollama_url: str | None = None) -> bool | None:
    """
    Vérification anti-boîte-fantôme : recadre `zone` (x, y, w, h) dans l'image
    et demande au VLM si le crop contient réellement `obj`. Retourne
    True/False, ou None si le contrôle est impossible (erreur d'appel/parse)
    — l'appelant doit alors garder la boîte (fail-open : ne jamais dégrader
    par rapport au comportement sans vérification).
    """
    import io

    image_path = Path(image_path)
    if ollama_url is None:
        ollama_url = load_ollama_url()

    try:
        with Image.open(image_path) as im:
            im = im.convert("RGB")
            x, y, w, h = zone
            x1 = max(0, x)
            y1 = max(0, y)
            x2 = min(im.width, x + w)
            y2 = min(im.height, y + h)
            if x2 - x1 < 4 or y2 - y1 < 4:
                return False   # zone dégénérée : rien à vérifier
            crop = im.crop((x1, y1, x2, y2))
            buf = io.BytesIO()
            crop.save(buf, format="PNG")
    except Exception as e:
        print(f"[vlm_grounding] verify_crop : crop impossible ({e})")
        return None

    prompt = PROMPT_VERIFY_TEMPLATE.format(obj=obj)
    data, err = _call_vlm(buf.getvalue(), prompt, model, timeout, ollama_url)
    if data is None:
        print(f"[vlm_grounding] verify_crop : {err}")
        return None
    contains = data.get("contains")
    if not isinstance(contains, bool):
        return None
    return contains


def grounding_boxes(image_path: Path | str, obj: str,
                    margin_px: int = DEFAULT_MARGIN,
                    model: str = DEFAULT_MODEL, timeout: int = DEFAULT_TIMEOUT,
                    ollama_url: str | None = None,
                    verify: bool = True) -> list[tuple[int, int, int, int]] | None:
    """
    Version pipeline multi-instance : liste de zones (x, y, w, h) — une par
    occurrence de `obj` — avec `margin_px` de marge. Si le grounding
    multi-instance échoue (ERROR), repli automatique sur le mode bbox unique
    (grounding_box) ; s'il ne retourne qu'une instance, c'est le cas normal
    (objets proches) et la liste n'a qu'un élément. None si rien trouvé.

    verify=True (défaut) : quand PLUSIEURS boîtes sont retournées, chacune
    est contre-vérifiée par verify_crop() et les boîtes fantômes (crop sans
    l'objet — cuisse/genou quand le 2e pied est occulté) sont rejetées
    (~1 s/boîte). Fail-open : contrôle indécis = boîte gardée ; si TOUTES
    sont rejetées, la liste complète est conservée avec un avertissement
    (une vérification sur-stricte ne doit pas faire pire que l'absence de
    vérification). Une boîte unique n'est jamais vérifiée (pas de problème
    d'union, et le mode historique n'avait pas ce contrôle).
    """
    if ollama_url is None:
        ollama_url = load_ollama_url()
    name = Path(image_path).name
    res = ask_grounding_multi(image_path, obj, model=model, timeout=timeout,
                              ollama_url=ollama_url)
    if res["status"] == "OK":
        zones = [_to_zone(b, margin_px) for b in res["bboxes"]]
        if verify and len(zones) >= 2:
            kept = []
            for zone in zones:
                v = verify_crop(image_path, zone, obj, model=model,
                                timeout=timeout, ollama_url=ollama_url)
                if v is False:
                    print(f"[vlm_grounding] {name} : boîte fantôme rejetée "
                          f"{zone} (crop sans \"{obj}\")")
                else:
                    kept.append(zone)
            if kept:
                zones = kept
            else:
                print(f"[vlm_grounding] {name} : WARN — toutes les boîtes "
                      f"rejetées par la vérification, liste conservée telle "
                      f"quelle (fail-open)")
        return zones
    if res["status"] == "NOT_FOUND":
        print(f"[vlm_grounding] {name} : NOT_FOUND — {res['reason']}")
        return None
    # ERROR multi-instance -> repli sur le mode bbox unique historique
    print(f"[vlm_grounding] {name} : multi-instance ERROR "
          f"({res['reason']}) — repli bbox unique")
    zone = grounding_box(image_path, obj, margin_px=margin_px, model=model,
                         timeout=timeout, ollama_url=ollama_url)
    return [zone] if zone is not None else None

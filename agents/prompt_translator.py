"""
prompt_translator.py V1.1 -- Traducteur Narratif -> Intentions de Realisation JSON
Studio Ov3rLoRd
V1.1 : Fix JSON tronque Ollama (extraction regex champs partiels) + Pacing Engine integre.
"""

import os
import sys
import re
import json
import logging
from pathlib import Path
from typing import Optional

_BASE_DIR = Path(__file__).resolve().parent.parent
if str(_BASE_DIR) not in sys.path:
    sys.path.insert(0, str(_BASE_DIR))

try:
    from overlord_utils import fallback_llm, safe_json_parse
    UTILS_OK = True
except ImportError:
    try:
        from agents.overlord_utils import fallback_llm, safe_json_parse
        UTILS_OK = True
    except ImportError:
        UTILS_OK = False
        def fallback_llm(prompt, system=None, logger=None):
            return ""
        def safe_json_parse(text, logger=None):
            try:
                return json.loads(text)
            except Exception:
                return {}

try:
    from agents.negative_bank import get_negative
    NEGBANK_OK = True
except ImportError:
    try:
        from negative_bank import get_negative
        NEGBANK_OK = True
    except ImportError:
        NEGBANK_OK = False
        def get_negative(**kw): return "bad anatomy, deformed, watermark, signature, blurry, low quality"

SHOT_TYPES = [
    "extreme_close_up", "close_up", "medium_close_up",
    "medium_shot", "medium_long_shot", "long_shot",
    "extreme_long_shot", "over_the_shoulder", "two_shot",
    "birds_eye", "low_angle", "dutch_angle",
]

LIGHTING_TYPES = [
    "natural_daylight", "golden_hour", "blue_hour",
    "chiaroscuro", "flat_soft", "high_contrast",
    "neon", "backlighting", "ambient_glow", "dramatic",
]

ACTING_INTENTS = [
    "determination", "suppressed_grief", "rage",
    "fear", "wonder", "tenderness", "resignation",
    "defiance", "despair", "relief", "shock", "neutral",
]

CAMERA_MOVEMENTS = [
    "static", "slow_pan", "fast_cut", "zoom_in",
    "zoom_out", "dolly_forward", "slight_jitter_for_unease",
    "tracking_shot", "crane_up", "handheld",
]

_FEW_SHOT_EXAMPLES = [
    {
        "narrative": "Asuka regarde l'EVA-02 pour la premiere fois, ses yeux s'illuminent de determination",
        "translation": {
            "shot_type": "medium_close_up",
            "lighting": "dramatic",
            "acting_intent": "determination",
            "camera_movement": "slow_pan",
            "positive_prompt": "asuka langley soryu, red plugsuit, looking up at giant mecha, eyes wide with resolve, evangelion unit 02, hangar interior, cinematic lighting, anime style, highly detailed",
            "negative_prompt": "wrong hair color, blue hair, white plugsuit, bad anatomy, deformed, watermark, signature"
        }
    },
    {
        "narrative": "Shinji seul dans l'entry plug, pleure silencieusement dans le noir",
        "translation": {
            "shot_type": "extreme_close_up",
            "lighting": "chiaroscuro",
            "acting_intent": "suppressed_grief",
            "camera_movement": "static",
            "positive_prompt": "shinji ikari, plugsuit, close up face, tears, dark cockpit, entry plug interior, single light source, emotional, neon genesis evangelion, anime style",
            "negative_prompt": "bright colors, smiling, multiple people, bad anatomy, blurry"
        }
    },
    {
        "narrative": "EVA-01 se releve lentement apres le combat, la ville detruite derriere elle",
        "translation": {
            "shot_type": "long_shot",
            "lighting": "golden_hour",
            "acting_intent": "determination",
            "camera_movement": "crane_up",
            "positive_prompt": "evangelion unit 01, purple mecha, standing in ruined cityscape, sunset, debris, smoke, epic scale, cinematic, anime style, highly detailed background",
            "negative_prompt": "humans in foreground, blue sky, cheerful, bad anatomy, deformed mecha"
        }
    },
]

_SYSTEM_PROMPT = (
    "Tu es un traducteur technique pour pipeline d'animation.\n"
    "Tu recois une description narrative en francais et tu la convertis en un JSON strict.\n"
    "Reponds UNIQUEMENT avec le JSON, sans texte avant ou apres, sans backticks.\n\n"
    "Structure JSON attendue :\n"
    "{\n"
    '  "shot_type": "<un de : extreme_close_up, close_up, medium_close_up, medium_shot, '
    'medium_long_shot, long_shot, extreme_long_shot, over_the_shoulder, two_shot, '
    'birds_eye, low_angle, dutch_angle>",\n'
    '  "lighting": "<un de : natural_daylight, golden_hour, blue_hour, chiaroscuro, '
    'flat_soft, high_contrast, neon, backlighting, ambient_glow, dramatic>",\n'
    '  "acting_intent": "<un de : determination, suppressed_grief, rage, fear, wonder, '
    'tenderness, resignation, defiance, despair, relief, shock, neutral>",\n'
    '  "camera_movement": "<un de : static, slow_pan, fast_cut, zoom_in, zoom_out, '
    'dolly_forward, slight_jitter_for_unease, tracking_shot, crane_up, handheld>",\n'
    '  "positive_prompt": "<prompt ComfyUI optimise, en anglais, style Booru, virgule-separe>",\n'
    '  "negative_prompt": "<prompt negatif ComfyUI, en anglais, style Booru, virgule-separe>"\n'
    "}"
)


def _repair_truncated_json(raw: str) -> dict:
    """
    Tente de recuperer les champs valides d'un JSON tronque par Ollama.
    Cas frequent : Ollama coupe la reponse avant la fermeture du JSON.
    Strategie : extraction regex des paires cle/valeur STRING completement fermees.
    """
    raw = raw.strip()
    # Nettoyage backticks markdown
    if raw.startswith("```"):
        parts = raw.split("```")
        raw = parts[1] if len(parts) > 1 else raw[3:]
        if raw.startswith("json"):
            raw = raw[4:]
    raw = raw.strip()
    # Tentative directe
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        pass
    # Extraction regex : uniquement les paires dont la valeur string est fermee
    pattern = r'"([^"]+)"\s*:\s*"((?:[^"\\]|\\.)*)"'
    matches = list(re.finditer(pattern, raw))
    if not matches:
        return {}
    result = {}
    for m in matches:
        result[m.group(1)] = m.group(2)
    return result


def _validate_and_repair(data: dict, narrative: str, logger: logging.Logger) -> dict:
    """Valide les champs enumeres et corrige les valeurs hors-liste."""
    changed = False

    if data.get("shot_type") not in SHOT_TYPES:
        old = data.get("shot_type", "(vide)")
        data["shot_type"] = "medium_shot"
        logger.warning("[TRANSLATOR] shot_type invalide %r -> medium_shot", old)
        changed = True

    if data.get("lighting") not in LIGHTING_TYPES:
        old = data.get("lighting", "(vide)")
        data["lighting"] = "natural_daylight"
        logger.warning("[TRANSLATOR] lighting invalide %r -> natural_daylight", old)
        changed = True

    if data.get("acting_intent") not in ACTING_INTENTS:
        old = data.get("acting_intent", "(vide)")
        data["acting_intent"] = "neutral"
        logger.warning("[TRANSLATOR] acting_intent invalide %r -> neutral", old)
        changed = True

    if data.get("camera_movement") not in CAMERA_MOVEMENTS:
        old = data.get("camera_movement", "(vide)")
        data["camera_movement"] = "static"
        logger.warning("[TRANSLATOR] camera_movement invalide %r -> static", old)
        changed = True

    if not isinstance(data.get("positive_prompt"), str) or not data["positive_prompt"].strip():
        data["positive_prompt"] = "anime style, highly detailed, " + narrative[:80]
        logger.warning("[TRANSLATOR] positive_prompt vide -> fallback narratif")
        changed = True

    if not isinstance(data.get("negative_prompt"), str) or not data["negative_prompt"].strip():
        # V2.20 : negative_bank contextuel si disponible
        if NEGBANK_OK:
            data["negative_prompt"] = get_negative(
                shot_type = data.get("shot_type", ""),
                lighting  = data.get("lighting",  ""),
            )
            logger.warning("[TRANSLATOR] negative_prompt vide -> negative_bank contextuel")
        else:
            data["negative_prompt"] = "bad anatomy, deformed, watermark, signature, blurry, low quality"
            logger.warning("[TRANSLATOR] negative_prompt vide -> fallback standard")
        changed = True

    if changed:
        logger.info("[TRANSLATOR] Reparation appliquee sur intent invalide")

    return data


def _build_few_shot_context(narrative: str) -> str:
    """Construit le contexte few-shot + la requete pour le LLM."""
    parts = []
    for ex in _FEW_SHOT_EXAMPLES:
        parts.append("Narrative: " + ex["narrative"])
        parts.append("JSON: " + json.dumps(ex["translation"], ensure_ascii=False))
        parts.append("")
    parts.append("Narrative: " + narrative)
    parts.append("JSON:")
    return "\n".join(parts)


def translate_shot(
    narrative: str,
    universe: str = "",
    character_hints: Optional[str] = None,
    logger: Optional[logging.Logger] = None
) -> dict:
    """
    Traduit une description narrative en dictionnaire d'intentions de realisation.
    V1.1 : tentative de recuperation JSON tronque avant fallback.

    Args:
        narrative      : Description narrative du shot (fr ou en).
        universe       : Univers de la serie (ex: evangelion, gundam, dragon_ball).
        character_hints: Hints personnages (ex: asuka red plugsuit).
        logger         : Logger Python optionnel.

    Returns:
        dict : shot_type, lighting, acting_intent, camera_movement,
               positive_prompt, negative_prompt.
    """
    if logger is None:
        logger = logging.getLogger("prompt_translator")

    if not narrative or not narrative.strip():
        logger.warning("[TRANSLATOR] Narrative vide -- retour intent par defaut")
        return _get_default_intent()

    context_prefix = ""
    if universe:
        context_prefix += "[UNIVERSE: " + universe + "] "
    if character_hints:
        context_prefix += "[CHARACTERS: " + character_hints + "] "

    full_narrative = context_prefix + narrative.strip()
    user_prompt = _build_few_shot_context(full_narrative)

    logger.info("[TRANSLATOR] Traduction shot : %.60s...", narrative)

    raw_response = fallback_llm(
        user_prompt,
        system=_SYSTEM_PROMPT,
        logger=logger
    )

    if not raw_response or not raw_response.strip():
        logger.warning("[TRANSLATOR] LLM retourne vide -- fallback default")
        return _get_default_intent(narrative)

    # Tentative 1 : parse standard
    intent = safe_json_parse(raw_response, logger=logger)

    # Tentative 2 : reparation troncature Ollama
    if not isinstance(intent, dict) or not intent:
        logger.warning("[TRANSLATOR] JSON standard invalide -- tentative reparation troncature")
        intent = _repair_truncated_json(raw_response)
        if intent:
            logger.info("[TRANSLATOR] JSON repare : %d champs recuperes", len(intent))
        else:
            logger.warning("[TRANSLATOR] Reparation echouee -- fallback default")
            return _get_default_intent(narrative)

    intent = _validate_and_repair(intent, narrative, logger)

    logger.info(
        "[TRANSLATOR] OK shot_type=%s | lighting=%s | acting=%s",
        intent["shot_type"], intent["lighting"], intent["acting_intent"]
    )

    return intent


def translate_storyboard(
    shots: list,
    universe: str = "",
    character_hints: Optional[str] = None,
    logger: Optional[logging.Logger] = None
) -> list:
    """
    Traduit une liste de shots storyboard en liste d'intents de realisation.

    Args:
        shots          : Liste de dicts avec au moins la cle positive ou narrative.
        universe       : Univers de la serie.
        character_hints: Hints personnages globaux.
        logger         : Logger Python optionnel.

    Returns:
        Liste de dicts enrichis avec les cles d'intention de realisation.
    """
    if logger is None:
        logger = logging.getLogger("prompt_translator")

    translated = []
    for i, shot in enumerate(shots):
        narrative = (
            shot.get("narrative")
            or shot.get("description")
            or shot.get("positive", "")
        )
        intent = translate_shot(
            narrative=narrative,
            universe=universe,
            character_hints=character_hints,
            logger=logger
        )
        # intent ne doit pas ecraser les metadonnees existantes du shot
        merged = {**intent, **shot}
        # Forcer les prompts ComfyUI avec la traduction
        merged["positive"] = intent["positive_prompt"]
        # V2.20 : enrichir negative_prompt avec negative_bank si univers connu
        _neg_base = intent.get("negative_prompt", shot.get("negative", ""))
        if NEGBANK_OK and universe:
            _neg_base = get_negative(
                universe  = universe,
                shot_type = intent.get("shot_type", ""),
                lighting  = intent.get("lighting",  ""),
                extra     = _neg_base,
            )
        merged["negative"] = _neg_base
        merged["_intent"]  = intent
        merged["universe"] = universe
        translated.append(merged)
        logger.debug("[TRANSLATOR] Shot %d/%d traduit", i + 1, len(shots))

    logger.info("[TRANSLATOR] Storyboard traduit : %d shots", len(translated))
    return translated


def _get_default_intent(narrative: str = "") -> dict:
    """Intent par defaut en cas d'echec LLM."""
    suffix = (", " + narrative[:60]) if narrative else ""
    return {
        "shot_type":       "medium_shot",
        "lighting":        "natural_daylight",
        "acting_intent":   "neutral",
        "camera_movement": "static",
        "positive_prompt": "anime style, highly detailed" + suffix,
        "negative_prompt": "bad anatomy, deformed, watermark, signature, blurry, low quality, jpeg artifacts",
    }


# ── Pacing Engine V1.0 ────────────────────────────────────────────────
# Duree de plan recommandee en secondes selon acting_intent
# Action = coupes rapides (<2s) | Introspection = plans longs (>3.5s)
_PACING_MAP = {
    "rage":              1.2,
    "determination":     1.8,
    "shock":             1.0,
    "fear":              1.5,
    "defiance":          1.6,
    "suppressed_grief":  4.5,
    "despair":           5.0,
    "resignation":       4.0,
    "tenderness":        3.5,
    "wonder":            3.0,
    "relief":            3.2,
    "neutral":           2.5,
}

def get_recommended_duration(intent: dict) -> float:
    """
    Retourne la duree recommandee du plan en secondes selon l'intensite emotionnelle.
    Utilise par le Pacing Engine dans storyboard.py et postprod.py.
    """
    acting = intent.get("acting_intent", "neutral")
    return _PACING_MAP.get(acting, 2.5)


# ── CLI standalone ────────────────────────────────────────────────────
if __name__ == "__main__":
    import argparse

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)-8s] %(message)s"
    )
    log = logging.getLogger("prompt_translator")

    parser = argparse.ArgumentParser(description="Prompt Translator V1.1 -- Ov3rLoRd")
    parser.add_argument("--narrative", type=str, default="")
    parser.add_argument("--universe",  type=str, default="evangelion")
    parser.add_argument("--chars",     type=str, default="")
    parser.add_argument("--json-out",  type=str, default=None)
    args = parser.parse_args()

    if not args.narrative:
        args.narrative = "Asuka defie l'EVA-02 du regard depuis le pont de commandement"
        args.universe  = "evangelion"
        args.chars     = "asuka langley soryu, red plugsuit, blue eyes, auburn hair"

    print("\n[TEST] Narrative :", args.narrative)
    print("[TEST] Universe  :", args.universe)

    result = translate_shot(
        narrative=args.narrative,
        universe=args.universe,
        character_hints=args.chars,
        logger=log
    )

    print("\n=== INTENT DE REALISATION ===")
    print(json.dumps(result, indent=2, ensure_ascii=False))

    duration = get_recommended_duration(result)
    print("\n[PACING] Duree recommandee :", duration, "s")

    if args.json_out:
        out = Path(args.json_out)
        out.write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")
        print("[EXPORT] Sauvegarde ->", out)

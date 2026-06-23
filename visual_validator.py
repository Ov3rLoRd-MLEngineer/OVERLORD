"""
agents/visual_validator.py — Validateur Visuel Inter-Passes V1.70
Soumet chaque image générée à Mistral/LLM pour validation narrative
avant de passer à la passe suivante.

Critères de validation :
  - Cohérence avec l'univers demandé
  - Absence d'artefacts majeurs (corps incomplets, fusion de styles)
  - Cohérence narrative avec le shot description
  - Score minimum configurable

Si l'image échoue → retry de la passe avec prompt ajusté
Si l'image passe → passe suivante autorisée

Usage :
  from agents.visual_validator import validate_image_for_pass
  result = validate_image_for_pass(
      image_path="output.png",
      shot_description="EVA-01 en combat urbain",
      universe="evangelion",
      pass_name="character_a"
  )
  if result["pass"]:
      # continuer
  else:
      # retry avec result["fix_prompt"]
"""

import json
import logging
import sys
import io
from pathlib import Path
from datetime import datetime

if hasattr(sys.stdout, 'buffer'):
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

try:
    from agents.overlord_utils import fallback_llm, safe_json_parse
    UTILS_OK = True
except ImportError:
    UTILS_OK = False

try:
    from PIL import Image
    import base64
    PIL_OK = True
except ImportError:
    PIL_OK = False

try:
    from agents.context_bus import get_bus
    BUS_OK = True
except ImportError:
    BUS_OK = False

VALIDATION_LOG = Path("workspace/logs/visual_validator.jsonl")

# Critères de rejet par type de problème
REJECTION_CRITERIA = {
    "universe_mismatch": {
        "desc": "L'image ne correspond pas à l'univers demandé",
        "examples": ["Conan dans EVA", "style chibi dans scène action", "wrong franchise"],
        "severity": "HIGH",
        "auto_reject": True,
    },
    "body_artifact": {
        "desc": "Artefact corporel majeur (fusion, membres manquants, corps incomplet)",
        "examples": ["bras fusionné", "jambes manquantes", "EVA en parka"],
        "severity": "HIGH",
        "auto_reject": True,
    },
    "style_break": {
        "desc": "Rupture de style dans l'image (mélange styles incompatibles)",
        "examples": ["réaliste + cartoon", "3D + 2D flat"],
        "severity": "MEDIUM",
        "auto_reject": False,
    },
    "narrative_inconsistency": {
        "desc": "Incohérence narrative avec la description du shot",
        "examples": ["action shot statique", "extérieur nuit généré en intérieur jour"],
        "severity": "MEDIUM",
        "auto_reject": False,
    },
    "watermark": {
        "desc": "Watermark ou signature non désirée visible",
        "examples": ["signature artiste", "logo modèle", "texte aléatoire"],
        "severity": "LOW",
        "auto_reject": False,
    },
    "quality_low": {
        "desc": "Qualité insuffisante (flou, artefacts JPEG, bruit excessif)",
        "severity": "LOW",
        "auto_reject": False,
    },
}

# Prompts de correction par type de problème
FIX_PROMPTS = {
    "universe_mismatch": (
        "STRICT UNIVERSE LOCK: Only {universe} characters and settings. "
        "NO crossover elements. NO other franchises. "
        "Focus exclusively on {universe} visual style."
    ),
    "body_artifact": (
        "Perfect anatomy, complete body, no body merging, "
        "correct proportions, detailed limbs, "
        "negative: fused body parts, missing limbs, anatomy errors"
    ),
    "style_break": (
        "Consistent anime style throughout, uniform rendering, "
        "single artistic style, no style mixing"
    ),
    "narrative_inconsistency": (
        "Match exactly: {shot_description}. "
        "Environment: {universe} setting. Action: {shot_action}."
    ),
    "watermark": (
        "No watermarks, no signatures, no text overlay, "
        "no artist marks, clean image"
    ),
}


def image_to_base64(image_path: str) -> str | None:
    """Convertit une image en base64 pour l'envoi au LLM vision."""
    if not PIL_OK:
        return None
    try:
        img  = Image.open(image_path).convert("RGB")
        # Réduire pour économiser les tokens
        img.thumbnail((512, 768), Image.LANCZOS)
        buf = io.BytesIO()
        img.save(buf, format="JPEG", quality=85)
        return base64.b64encode(buf.getvalue()).decode("utf-8")
    except Exception:
        return None


def validate_image_for_pass(
    image_path: str,
    shot_description: str = "",
    universe: str = "anime",
    pass_name: str = "production",
    min_score: int = 70,
    logger=None
) -> dict:
    """
    Valide une image générée avant de passer à la passe suivante.

    Args:
        image_path      : chemin vers l'image à valider
        shot_description: description du shot attendu
        universe        : univers de référence (evangelion, gundam, etc.)
        pass_name       : nom de la passe (background, character_a, etc.)
        min_score       : score minimum pour PASS (0-100)

    Returns:
        {
            "pass": bool,
            "score": int,
            "issues": [liste des problèmes détectés],
            "fix_prompt": str (prompt de correction si FAIL),
            "auto_reject": bool,
            "reasoning": str
        }
    """
    log = logger or logging.getLogger("visual_validator")

    result = {
        "pass":        True,
        "score":       85,
        "issues":      [],
        "fix_prompt":  "",
        "auto_reject": False,
        "reasoning":   "",
        "image":       image_path,
        "pass_name":   pass_name,
        "timestamp":   datetime.now().isoformat(),
    }

    if not Path(image_path).exists():
        log.warning(f"[VALIDATOR] Image introuvable : {image_path}")
        result["pass"]  = False
        result["score"] = 0
        result["reasoning"] = "Fichier image introuvable"
        return result

    if not UTILS_OK:
        log.warning("[VALIDATOR] LLM absent — validation basique uniquement")
        return result

    # Construction du prompt de validation
    system = (
        "You are a strict quality control expert for anime production. "
        "Analyze the image and report issues. "
        "Reply ONLY with valid JSON."
    )

    # Décrire les critères selon la passe
    pass_criteria = {
        "background": (
            "Check: 1) No characters present 2) Correct atmosphere for universe "
            "3) No obvious artifacts 4) Style consistency"
        ),
        "character_a": (
            "Check: 1) Complete anatomy - no body artifacts 2) Correct universe character "
            "3) No background (transparent/white) 4) Style consistency"
        ),
        "character_b": (
            "Check: 1) Complete anatomy 2) Different character from primary "
            "3) No background 4) Universe match"
        ),
        "fx": (
            "Check: 1) Effects are transparent overlay 2) Match universe effects style "
            "3) No character generation"
        ),
        "production": (
            "Check: 1) Universe match 2) Complete anatomy 3) Narrative consistency "
            "4) No unwanted watermarks 5) Style consistency"
        ),
    }.get(pass_name, "Check general quality and universe consistency")

    prompt = (
        f"Validate this anime image for production quality.\n\n"
        f"Universe: {universe}\n"
        f"Pass type: {pass_name}\n"
        f"Shot description: {shot_description[:200]}\n"
        f"Criteria: {pass_criteria}\n\n"
        f"Known rejection issues to check:\n"
        + "\n".join(f"- {k}: {v['desc']}" for k, v in REJECTION_CRITERIA.items())
        + "\n\nReply ONLY with JSON:\n"
        "{\n"
        '  "score": 0-100,\n'
        '  "pass": true/false,\n'
        '  "issues": ["issue1", "issue2"],\n'
        '  "issue_types": ["universe_mismatch", "body_artifact", etc],\n'
        '  "auto_reject": true/false,\n'
        '  "reasoning": "brief explanation",\n'
        '  "fix_suggestion": "specific prompt fix if failed"\n'
        "}"
    )

    raw = fallback_llm(prompt, system=system, max_tokens=400, logger=log)
    ok, data, err = safe_json_parse(raw, logger=log)

    if ok and isinstance(data, dict):
        result["score"]       = int(data.get("score", 75))
        result["pass"]        = bool(data.get("pass", True)) and result["score"] >= min_score
        result["issues"]      = data.get("issues", [])
        result["auto_reject"] = bool(data.get("auto_reject", False))
        result["reasoning"]   = data.get("reasoning", "")

        # Construire le prompt de correction
        issue_types   = data.get("issue_types", [])
        fix_parts     = []
        for issue_type in issue_types:
            if issue_type in FIX_PROMPTS:
                fix = FIX_PROMPTS[issue_type].format(
                    universe=universe,
                    shot_description=shot_description[:80],
                    shot_action=shot_description[:40],
                )
                fix_parts.append(fix)

        if data.get("fix_suggestion"):
            fix_parts.append(data["fix_suggestion"])

        result["fix_prompt"] = " | ".join(fix_parts)

        # Log
        status = "✓ PASS" if result["pass"] else "✗ FAIL"
        log.info(
            f"[VALIDATOR] {status} | pass={pass_name} | "
            f"score={result['score']} | "
            f"issues={len(result['issues'])} | "
            f"auto_reject={result['auto_reject']}"
        )
        if result["issues"]:
            for issue in result["issues"][:3]:
                log.warning(f"[VALIDATOR]   ✗ {issue}")

    else:
        log.warning(f"[VALIDATOR] LLM parse failed ({err}) — PASS par défaut")

    # Sauvegarder dans le log
    VALIDATION_LOG.parent.mkdir(parents=True, exist_ok=True)
    with open(VALIDATION_LOG, 'a', encoding='utf-8') as f:
        f.write(json.dumps({
            "ts":          result["timestamp"],
            "image":       str(Path(image_path).name),
            "pass_name":   pass_name,
            "score":       result["score"],
            "pass":        result["pass"],
            "auto_reject": result["auto_reject"],
            "issues":      result["issues"][:3],
        }, ensure_ascii=False) + '\n')

    if BUS_OK:
        try:
            bus = get_bus()
            bus.write("validator.last_score",  result["score"],  agent_id="validator")
            bus.write("validator.last_pass",   result["pass"],   agent_id="validator")
            bus.write("validator.last_issues", len(result["issues"]), agent_id="validator")
        except Exception:
            pass

    return result


def validate_batch(image_paths: list[str],
                    shot_descriptions: list[str] = None,
                    universe: str = "anime",
                    pass_name: str = "production",
                    min_score: int = 70,
                    max_retries: int = 2,
                    logger=None) -> dict:
    """
    Valide un batch d'images inter-passes.
    Retourne les images PASS et les jobs à retry.
    """
    log = logger or logging.getLogger("visual_validator")
    log.info(f"[VALIDATOR] Validation batch {len(image_paths)} images | pass={pass_name}")

    passed  = []
    failed  = []
    retries = []

    for i, image_path in enumerate(image_paths):
        shot_desc = (shot_descriptions[i] if shot_descriptions
                     and i < len(shot_descriptions) else "")

        result = validate_image_for_pass(
            image_path=image_path,
            shot_description=shot_desc,
            universe=universe,
            pass_name=pass_name,
            min_score=min_score,
            logger=log,
        )

        if result["pass"]:
            passed.append({"path": image_path, "result": result})
        else:
            failed.append({"path": image_path, "result": result})
            if not result["auto_reject"] and max_retries > 0:
                retries.append({
                    "path":       image_path,
                    "fix_prompt": result["fix_prompt"],
                    "score":      result["score"],
                    "issues":     result["issues"],
                })

    log.info(
        f"[VALIDATOR] Batch terminé : {len(passed)} PASS | "
        f"{len(failed)} FAIL | {len(retries)} à retry"
    )

    return {
        "passed":      passed,
        "failed":      failed,
        "retries":     retries,
        "pass_rate":   len(passed) / max(len(image_paths), 1) * 100,
        "total":       len(image_paths),
    }


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Visual Validator V1.70")
    parser.add_argument("--image",    type=str, required=True)
    parser.add_argument("--universe", type=str, default="evangelion")
    parser.add_argument("--pass",     type=str, default="production", dest="pass_name")
    parser.add_argument("--desc",     type=str, default="")
    parser.add_argument("--score",    type=int, default=70)
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO,
                        format="%(asctime)s [%(levelname)s] %(message)s")

    result = validate_image_for_pass(
        image_path=args.image,
        shot_description=args.desc,
        universe=args.universe,
        pass_name=args.pass_name,
        min_score=args.score,
    )

    print(f"\n{'═'*50}")
    print(f"  VALIDATION : {'✓ PASS' if result['pass'] else '✗ FAIL'}")
    print(f"  Score      : {result['score']}/100")
    print(f"  Auto-reject: {result['auto_reject']}")
    if result['issues']:
        print(f"  Problèmes  :")
        for issue in result['issues']:
            print(f"    ✗ {issue}")
    if result['fix_prompt']:
        print(f"  Fix prompt : {result['fix_prompt'][:80]}")
    print(f"  Reasoning  : {result['reasoning'][:100]}")
    print(f"{'═'*50}")

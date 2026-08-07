"""
agents/scenario.py — Agent Scenariste + Script Doctor V1.49
Utilise overlord_utils.fallback_llm (centralise) et publie sur le context_bus.
"""

import json
import logging
from datetime import datetime, timezone
from pathlib import Path

try:
    from agents.overlord_utils import fallback_llm, safe_json_parse, get_api_key, build_headers
    UTILS_OK = True
except ImportError:
    UTILS_OK = False
    fallback_llm   = None
    safe_json_parse= None

try:
    from agents.context_bus import get_bus
    BUS_OK = True
except ImportError:
    BUS_OK = False

CLAUDE_MODEL = "claude-sonnet-4-6"
SCRIPT_DIR   = Path("workspace/scripts")

MEDIA_FORMATS = {
    "anime":     "serie animee japonaise (style Shounen/Shonen)",
    "manga":     "manga decoupe en cases et bulles",
    "comics":    "comics occidental (Marvel/DC style)",
    "3d":        "court-metrage 3D CGI",
    "photoreal": "video photorealiste / proof concept",
    "art":       "serie d'illustrations / affiche artistique",
    "game":      "jeu video (game design document + assets 2D/3D)",
    "short":     "court-metrage anime (< 5 min)",
    "film":      "long metrage anime (90 min)",
}

MAX_SCRIPT_ITERATIONS = 3
QUALITY_CRITERIA = [
    "rythme narratif coherent",
    "conflit central clairement defini",
    "arc personnage present",
    "potentiel visuel fort (adaptable en images)",
    "accroche dans les 10 premieres secondes",
]


def _llm(prompt: str, system: str = "", logger: logging.Logger = None) -> str:
    """Appel LLM centralise via overlord_utils.fallback_llm."""
    log = logger or logging.getLogger("scenario.llm")
    if not UTILS_OK or not fallback_llm:
        log.error("[SCENARIO] overlord_utils indisponible")
        return ""
    return fallback_llm(prompt, system=system, model=CLAUDE_MODEL,
                        max_tokens=4000, logger=log)


def _parse(raw: str, logger: logging.Logger = None) -> dict | None:
    if not UTILS_OK or not safe_json_parse:
        try:
            return json.loads(raw.strip())
        except Exception:
            return None
    ok, data, _ = safe_json_parse(raw, logger=logger)
    return data if ok else None


# ── Generateur de script ──────────────────────────────────────────────
def generate_script(trend_report: dict, media_type: str = "anime",
                    duration: str = "short", universe: str = "",
                    logger: logging.Logger = None) -> dict:
    log = logger or logging.getLogger("scenario.writer")
    log.info(f"[SCENARISTE] Generation — media={media_type} | duree={duration}")

    format_desc  = MEDIA_FORMATS.get(media_type, media_type)
    hot_kw       = ", ".join(trend_report.get("hot_keywords", [])[:8])
    brief        = trend_report.get("brief", "Pas de brief disponible")
    top_posts    = "\n".join(
        f"- {p['title']} (score: {p.get('score',0)})"
        for p in trend_report.get("top_reddit", [])[:3]
    )
    universe_ctx = f"Univers cible : {universe}.\n" if universe else ""

    system = (
        "Tu es un scenariste professionnel specialise dans les medias populaires. "
        "Tu generes des scripts exploitables, structures et adaptes a la production "
        "automatisee par IA. Tes scripts sont riches en details visuels. "
        "Reponds UNIQUEMENT en JSON valide, sans backticks ni explication."
    )

    prompt = (
        f"{universe_ctx}Format : {format_desc}. Duree : {duration}.\n\n"
        f"Tendances :\nBrief : {brief}\nPosts viraux : {top_posts}\nMots-cles : {hot_kw}\n\n"
        f'Genere un script JSON strict avec : title, logline, genre, media_type, '
        f'duration_estimate, target_audience, synopsis, acts (avec scenes), characters, '
        f'visual_style, color_palette, music_mood, transmedia_notes.'
    )

    raw = _llm(prompt, system=system, logger=log)
    result = _parse(raw, logger=log)
    if result:
        log.info(f"[SCENARISTE] Script genere : '{result.get('title','?')}'")
        return result

    log.error("[SCENARISTE] JSON invalide")
    return {"error": "json_parse_failed", "raw": raw}


# ── Script Doctor ─────────────────────────────────────────────────────
def review_script(script: dict, iteration: int = 1,
                  logger: logging.Logger = None) -> dict:
    log = logger or logging.getLogger("scenario.doctor")
    log.info(f"[SCRIPT DOCTOR] Revision iteration {iteration}")

    criteria_list = "\n".join(f"- {c}" for c in QUALITY_CRITERIA)
    script_json   = json.dumps(script, ensure_ascii=False, indent=2)[:3000]

    system = (
        "Tu es un expert en developpement de scenarios et analyse narrative. "
        "Reponds UNIQUEMENT en JSON valide."
    )
    prompt = (
        f"Analyse ce script sur ces criteres :\n{criteria_list}\n\n"
        f"Script :\n{script_json}\n\n"
        f"Retourne JSON : score_global(0-100), criteria_scores, validated(bool), "
        f"strengths, weaknesses, correction_instructions."
    )

    raw    = _llm(prompt, system=system, logger=log)
    result = _parse(raw, logger=log)
    if result:
        log.info(f"[SCRIPT DOCTOR] Score={result.get('score_global',0)}/100 | "
                 f"Valide={'oui' if result.get('validated') else 'non'}")
        return result
    return {"validated": True, "score_global": 50, "correction_instructions": ""}


def improve_script(script: dict, review: dict,
                   logger: logging.Logger = None) -> dict:
    log          = logger or logging.getLogger("scenario.improve")
    instructions = review.get("correction_instructions", "")
    weaknesses   = "\n".join(f"- {w}" for w in review.get("weaknesses", []))
    script_json  = json.dumps(script, ensure_ascii=False, indent=2)[:3000]

    system = "Tu es un scenariste expert. Reponds UNIQUEMENT en JSON valide."
    prompt = (
        f"Ameliore ce script.\nFaiblesses :\n{weaknesses}\n"
        f"Instructions :\n{instructions}\n\nScript actuel :\n{script_json}\n\n"
        f"Retourne le script ameliore dans le meme format JSON."
    )

    raw    = _llm(prompt, system=system, logger=log)
    result = _parse(raw, logger=log)
    if result:
        log.info(f"[IMPROVE] Script ameliore : '{result.get('title','?')}'")
        return result
    log.warning("Amelioration JSON invalide — on garde le script precedent")
    return script


# ── Pipeline complet ──────────────────────────────────────────────────
def run_scenario(trend_report: dict, media_type: str = "anime",
                 duration: str = "short", universe: str = "",
                 quality_threshold: int = 70,
                 logger: logging.Logger = None) -> dict:
    log = logger or logging.getLogger("scenario")
    log.info(f"[SCENARIO] Pipeline demarre — media={media_type} | seuil={quality_threshold}")
    SCRIPT_DIR.mkdir(parents=True, exist_ok=True)

    script = generate_script(trend_report, media_type, duration, universe, logger=log)
    if "error" in script:
        log.error("[SCENARIO] Echec generation initiale")
        return script

    best_script = script
    best_score  = 0
    iteration   = 1

    for iteration in range(1, MAX_SCRIPT_ITERATIONS + 1):
        review = review_script(script, iteration=iteration, logger=log)
        score  = review.get("score_global", 0)
        if score > best_score:
            best_score  = score
            best_script = script
        if review.get("validated") and score >= quality_threshold:
            log.info(f"[SCENARIO] OK Valide iteration {iteration} — score={score}")
            break
        if iteration < MAX_SCRIPT_ITERATIONS:
            log.info(f"[SCENARIO] Iteration {iteration} score={score} < {quality_threshold} — amelioration...")
            script = improve_script(script, review, logger=log)
    else:
        log.warning(f"[SCENARIO] Seuil non atteint — meilleur score={best_score}")
        script = best_script

    ts         = datetime.now(tz=timezone.utc).strftime("%Y%m%d_%H%M%S")
    title_safe = script.get("title", "untitled").replace(" ", "_")[:40]
    out_path   = SCRIPT_DIR / f"{ts}_{title_safe}.json"
    out_path.write_text(json.dumps(script, indent=2, ensure_ascii=False), encoding="utf-8")
    log.info(f"[SCENARIO] Script sauvegarde -> {out_path}")

    script["_meta"] = {"final_score": best_score, "iterations": iteration,
                       "saved_to": str(out_path)}

    # Publier sur le context_bus
    if BUS_OK:
        try:
            bus = get_bus()
            bus.write("scenario.title",    script.get("title", ""),  agent_id="scenario")
            bus.write("scenario.genre",    script.get("genre", []),   agent_id="scenario")
            bus.write("scenario.score",    best_score,                agent_id="scenario")
            bus.write("scenario.saved_to", str(out_path),             agent_id="scenario")
        except Exception as e:
            log.warning(f"[SCENARIO] Publication bus echouee : {e}")

    return script


if __name__ == "__main__":
    import sys, io
    if hasattr(sys.stdout,'buffer'):
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
    logging.basicConfig(level=logging.INFO)
    fake_report = {
        "media_type":   "anime",
        "brief":        "Dragon Ball et les combats epiques dominent les tendances",
        "hot_keywords": ["dragon ball","super saiyan","tournament","epic fight"],
        "top_reddit":   [{"title": "New Dragon Ball arc leaked!", "score": 45000}],
    }
    script = run_scenario(fake_report, media_type="anime", universe="Dragon Ball Super Broly")
    print(json.dumps({"title": script.get("title"), "score": script.get("_meta",{}).get("final_score")}, indent=2))
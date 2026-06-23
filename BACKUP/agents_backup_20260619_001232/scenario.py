"""
agents/scenario.py — Agent Scénariste + Script Doctor
Utilise l'API Anthropic (Claude) pour générer des scripts exploitables
à partir des TrendReports produits par sourcing.py.

Sortie : Script structuré JSON → consommé par storyboard.py
"""

import json
import logging
import requests
from datetime import datetime
import os
from pathlib import Path

# ============================================================
# CONFIG
# ============================================================
ANTHROPIC_URL = "https://api.anthropic.com/v1/messages"
CLAUDE_MODEL      = "claude-sonnet-4-6"

def _get_api_key() -> str:
    """Lit la clé API Anthropic depuis l'environnement ou le fichier .env."""
    import os
    key = os.environ.get("ANTHROPIC_API_KEY", "")
    if not key:
        # Tentative lecture .env à la racine du projet
        env_path = Path(__file__).parent.parent / ".env"
        if env_path.exists():
            for line in env_path.read_text(encoding="utf-8").splitlines():
                if line.startswith("ANTHROPIC_API_KEY="):
                    key = line.split("=", 1)[1].strip().strip('"').strip("'")
                    break
    return key
MAX_TOKENS        = 4000
SCRIPT_DIR        = Path("workspace/scripts")

# Formats transmédias supportés
MEDIA_FORMATS = {
    "anime":      "série animée japonaise (style Shounen/Shonen)",
    "manga":      "manga découpé en cases et bulles",
    "comics":     "comics occidental (Marvel/DC style)",
    "3d":         "court-métrage 3D CGI",
    "photoreal":  "vidéo photoréaliste / proof concept",
    "art":        "série d'illustrations / affiche artistique",
    "game":       "jeu vidéo (game design document + assets 2D/3D)",
    "short":      "court-métrage animé (< 5 min)",
    "film":       "long métrage animé (90 min)",
}

# Loopback qualité scénario
MAX_SCRIPT_ITERATIONS = 3
QUALITY_CRITERIA = [
    "rythme narratif cohérent",
    "conflit central clairement défini",
    "arc personnage présent",
    "potentiel visuel fort (adaptable en images)",
    "accroche dans les 10 premières secondes",
]


# ============================================================
# APPEL API CLAUDE
# ============================================================
def _call_claude(prompt: str, system: str = "",
                 logger: logging.Logger = None) -> str:
    """Appelle l'API Anthropic et retourne le texte de réponse."""
    log = logger or logging.getLogger("scenario.claude")

    body = {
        "model":      CLAUDE_MODEL,
        "max_tokens": MAX_TOKENS,
        "messages":   [{"role": "user", "content": prompt}],
    }
    if system:
        body["system"] = system

    try:
        resp = requests.post(
            ANTHROPIC_URL,
            headers={
                "Content-Type": "application/json",
                "x-api-key": _get_api_key(),
                "anthropic-version": "2023-06-01",
            },
            json=body,
            timeout=60
        )
        if resp.status_code == 200:
            content = resp.json().get("content", [])
            text = " ".join(
                block["text"] for block in content
                if block.get("type") == "text"
            )
            log.debug(f"Claude réponse : {len(text)} caractères")
            return text
        else:
            log.error(f"API Claude HTTP {resp.status_code}: {resp.text[:200]}")
            return ""
    except Exception as e:
        log.error(f"Erreur API Claude : {e}")
        return ""


# ============================================================
# AGENT SCÉNARISTE
# ============================================================
def generate_script(trend_report: dict,
                    media_type: str = "anime",
                    duration: str = "short",
                    universe: str = "",
                    logger: logging.Logger = None) -> dict:
    """
    Génère un script structuré à partir du TrendReport.

    Paramètres :
        trend_report : sortie de sourcing.run_sourcing()
        media_type   : clé de MEDIA_FORMATS
        duration     : "short" | "episode" | "film"
        universe     : contexte libre (ex: "Dragon Ball Super Broly style")

    Retourne un dict ScriptDocument.
    """
    log = logger or logging.getLogger("scenario.writer")
    log.info(f"[SCÉNARISTE] Génération — media={media_type} | durée={duration}")

    format_desc = MEDIA_FORMATS.get(media_type, media_type)
    hot_kw      = ", ".join(trend_report.get("hot_keywords", [])[:8])
    brief       = trend_report.get("brief", "Pas de brief disponible")
    top_posts   = "\n".join(
        f"- {p['title']} (score: {p.get('score',0)})"
        for p in trend_report.get("top_reddit", [])[:3]
    )

    universe_ctx = f"Univers cible : {universe}.\n" if universe else ""

    system = (
        "Tu es un scénariste professionnel spécialisé dans les médias populaires. "
        "Tu génères des scripts exploitables, structurés et adaptés à la production "
        "automatisée par IA. Tes scripts sont toujours riches en détails visuels "
        "pour faciliter la génération d'images et de séquences animées. "
        "Réponds UNIQUEMENT en JSON valide, sans backticks ni explication."
    )

    prompt = f"""
{universe_ctx}Format de production : {format_desc}.
Durée cible : {duration}.

Données de tendance actuelles :
Brief : {brief}
Posts viraux : {top_posts}
Mots-clés chauds : {hot_kw}

Génère un script complet au format JSON strict suivant :
{{
  "title": "Titre de l'œuvre",
  "logline": "Phrase de concept en 1 ligne",
  "genre": ["action", "aventure", ...],
  "media_type": "{media_type}",
  "duration_estimate": "durée estimée",
  "target_audience": "description de l'audience cible",
  "synopsis": "Synopsis en 3-5 paragraphes",
  "acts": [
    {{
      "act": 1,
      "title": "L'Éveil",
      "summary": "Résumé de l'acte",
      "scenes": [
        {{
          "scene_id": "S01E01",
          "location": "Lieu",
          "time_of_day": "Jour/Nuit/Aube...",
          "characters": ["Perso1", "Perso2"],
          "action": "Description de l'action visuelle",
          "dialogue_hint": "Indication de dialogue clé",
          "visual_prompt_hint": "Prompt image suggéré pour cette scène",
          "duration_seconds": 30
        }}
      ]
    }}
  ],
  "characters": [
    {{
      "name": "Nom",
      "role": "Protagoniste/Antagoniste/Secondaire",
      "description": "Description physique et psychologique",
      "visual_prompt": "Prompt ComfyUI pour ce personnage"
    }}
  ],
  "visual_style": "Description du style visuel global",
  "color_palette": ["couleur1", "couleur2"],
  "music_mood": "Ambiance musicale",
  "transmedia_notes": {{
    "manga_adaptation": "Notes si adaptation manga",
    "game_assets_needed": ["asset1", "asset2"],
    "3d_scenes": ["scène qui bénéficierait d'un rendu 3D"]
  }}
}}
"""

    raw = _call_claude(prompt, system=system, logger=log)

    try:
        # Nettoyer les éventuels backticks résiduels
        clean = raw.strip()
        if clean.startswith("```"):
            clean = "\n".join(clean.split("\n")[1:-1])
        script = json.loads(clean)
        log.info(f"[SCÉNARISTE] Script généré : '{script.get('title','?')}'")
        return script
    except json.JSONDecodeError as e:
        log.error(f"JSON invalide reçu du scénariste : {e}")
        log.debug(f"Raw reçu : {raw[:500]}")
        return {"error": "json_parse_failed", "raw": raw}


# ============================================================
# AGENT SCRIPT DOCTOR — LOOPBACK QUALITÉ
# ============================================================
def review_script(script: dict,
                  iteration: int = 1,
                  logger: logging.Logger = None) -> dict:
    """
    Analyse le script et retourne un rapport de qualité.
    Si le script ne passe pas, retourne les instructions de correction.
    """
    log = logger or logging.getLogger("scenario.doctor")
    log.info(f"[SCRIPT DOCTOR] Révision itération {iteration}")

    criteria_list = "\n".join(f"- {c}" for c in QUALITY_CRITERIA)
    script_json   = json.dumps(script, ensure_ascii=False, indent=2)[:3000]

    system = (
        "Tu es un expert en développement de scénarios et en analyse narrative. "
        "Tu analyses des scripts pour la production IA et tu identifies les faiblesses "
        "structurelles. Réponds UNIQUEMENT en JSON valide."
    )

    prompt = f"""
Analyse ce script et évalue-le sur les critères suivants :
{criteria_list}

Script à analyser :
{script_json}

Retourne ce JSON strict :
{{
  "score_global": 0-100,
  "criteria_scores": {{
    "rythme": 0-100,
    "conflit": 0-100,
    "arc_personnage": 0-100,
    "potentiel_visuel": 0-100,
    "accroche": 0-100
  }},
  "validated": true/false,
  "strengths": ["point fort 1", ...],
  "weaknesses": ["point faible 1", ...],
  "correction_instructions": "Instructions précises pour l'itération suivante (vide si validé)"
}}
"""

    raw = _call_claude(prompt, system=system, logger=log)
    try:
        clean = raw.strip()
        if clean.startswith("```"):
            clean = "\n".join(clean.split("\n")[1:-1])
        review = json.loads(clean)
        score  = review.get("score_global", 0)
        valid  = review.get("validated", False)
        log.info(
            f"[SCRIPT DOCTOR] Score={score}/100 | "
            f"Validé={'✓' if valid else '✗'}"
        )
        return review
    except json.JSONDecodeError as e:
        log.error(f"Erreur parsing review : {e}")
        return {"validated": True, "score_global": 50, "correction_instructions": ""}


def improve_script(script: dict,
                   review: dict,
                   logger: logging.Logger = None) -> dict:
    """Améliore le script selon les instructions du Script Doctor."""
    log = logger or logging.getLogger("scenario.improve")

    instructions = review.get("correction_instructions", "")
    weaknesses   = "\n".join(f"- {w}" for w in review.get("weaknesses", []))
    script_json  = json.dumps(script, ensure_ascii=False, indent=2)[:3000]

    system = (
        "Tu es un scénariste expert. Tu améliores des scripts existants "
        "selon des instructions précises. Réponds UNIQUEMENT en JSON valide."
    )

    prompt = f"""
Améliore ce script selon les instructions suivantes.

Faiblesses identifiées :
{weaknesses}

Instructions de correction :
{instructions}

Script actuel :
{script_json}

Retourne le script amélioré dans le même format JSON que l'original.
"""

    raw = _call_claude(prompt, system=system, logger=log)
    try:
        clean = raw.strip()
        if clean.startswith("```"):
            clean = "\n".join(clean.split("\n")[1:-1])
        improved = json.loads(clean)
        log.info(f"[IMPROVE] Script amélioré : '{improved.get('title','?')}'")
        return improved
    except json.JSONDecodeError:
        log.warning("Amélioration JSON invalide — on garde le script précédent")
        return script


# ============================================================
# PIPELINE SCÉNARIO COMPLET AVEC LOOPBACK
# ============================================================
def run_scenario(trend_report: dict,
                 media_type: str = "anime",
                 duration: str = "short",
                 universe: str = "",
                 quality_threshold: int = 70,
                 logger: logging.Logger = None) -> dict:
    """
    Pipeline complet Scénariste → Script Doctor → Loopback.

    Retourne un ScriptDocument validé (ou le meilleur disponible).
    """
    log = logger or logging.getLogger("scenario")
    log.info(f"[SCÉNARIO] Pipeline démarré — media={media_type} | seuil={quality_threshold}")

    SCRIPT_DIR.mkdir(parents=True, exist_ok=True)

    # Génération initiale
    script = generate_script(
        trend_report, media_type, duration, universe, logger=log
    )

    if "error" in script:
        log.error("[SCÉNARIO] Échec génération initiale")
        return script

    best_script = script
    best_score  = 0

    # Boucle loopback
    for iteration in range(1, MAX_SCRIPT_ITERATIONS + 1):
        review = review_script(script, iteration=iteration, logger=log)
        score  = review.get("score_global", 0)

        if score > best_score:
            best_score  = score
            best_script = script

        if review.get("validated") and score >= quality_threshold:
            log.info(f"[SCÉNARIO] ✓ Validé à l'itération {iteration} — score={score}")
            break

        if iteration < MAX_SCRIPT_ITERATIONS:
            log.info(f"[SCÉNARIO] Itération {iteration} score={score} < {quality_threshold} — amélioration...")
            script = improve_script(script, review, logger=log)
    else:
        log.warning(
            f"[SCÉNARIO] Seuil non atteint après {MAX_SCRIPT_ITERATIONS} itérations "
            f"— on garde le meilleur (score={best_score})"
        )
        script = best_script

    # Sauvegarder le script final
    ts        = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
    title_safe = script.get("title", "untitled").replace(" ", "_")[:40]
    out_path  = SCRIPT_DIR / f"{ts}_{title_safe}.json"
    out_path.write_text(
        json.dumps(script, indent=2, ensure_ascii=False),
        encoding="utf-8"
    )
    log.info(f"[SCÉNARIO] Script sauvegardé → {out_path}")

    script["_meta"] = {
        "final_score": best_score,
        "iterations":  iteration,
        "saved_to":    str(out_path),
    }
    return script


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    # Test avec un faux TrendReport
    fake_report = {
        "media_type":   "anime",
        "brief":        "Dragon Ball et les combats épiques dominent les tendances",
        "hot_keywords": ["dragon ball", "super saiyan", "tournament", "epic fight"],
        "top_reddit":   [{"title": "New Dragon Ball arc leaked!", "score": 45000}],
    }
    script = run_scenario(fake_report, media_type="anime", universe="Dragon Ball Super Broly")
    print(json.dumps(script, indent=2, ensure_ascii=False))

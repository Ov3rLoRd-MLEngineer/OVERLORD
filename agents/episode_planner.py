"""
agents/episode_planner.py — Planificateur de Série V1.70
Planifie N épisodes avec arcs narratifs progressifs,
évolution des personnages, et variation visuelle contrôlée.
Alimente dream_mode avec une liste structurée et cohérente.

Fonctions :
  - Génération d'un plan de série complet via LLM
  - Arcs en 3 actes sur la série entière (setup/confrontation/résolution)
  - Variation des univers visuels par épisode
  - Export vers dream_mode (universes_file)
  - Intégration narrative_memory pour la continuité

Usage :
  python agents/episode_planner.py --series "Evangelion: Rebirth" --episodes 12
  python agents/episode_planner.py --load plan.json --export-universes universes.txt
"""

import json
import logging
import sys
import io
from datetime import datetime
from pathlib import Path

if hasattr(sys.stdout, 'buffer'):
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

try:
    from agents.overlord_utils import fallback_llm, safe_json_parse
    UTILS_OK = True
except ImportError:
    UTILS_OK = False

try:
    from agents.context_bus import get_bus
    BUS_OK = True
except ImportError:
    BUS_OK = False

try:
    from agents.narrative_memory import get_narrative_memory
    MEMORY_OK = True
except ImportError:
    MEMORY_OK = False

try:
    from agents.character_designer import (
        detect_characters_in_script,
        init_preset_characters,
        PRESET_CHARACTERS
    )
    CHARS_OK = True
except ImportError:
    CHARS_OK = False

PLANS_DIR = Path("workspace/narrative/plans")

# Arcs émotionnels par position dans la série
SERIES_ARC_TEMPLATES = {
    "3_act": [
        # Acte 1 : Setup (épisodes 1-3)
        {"arc": "wonder",    "tone": "hopeful",      "visual": "bright, vibrant colors, wide establishing shots"},
        {"arc": "wonder",    "tone": "curious",      "visual": "warm palette, dynamic compositions"},
        {"arc": "tension",   "tone": "foreboding",   "visual": "contrast shadows, dramatic angles"},
        # Acte 2 : Confrontation (épisodes 4-8)
        {"arc": "tension",   "tone": "intense",      "visual": "high contrast, speed lines, battle"},
        {"arc": "tension",   "tone": "desperate",    "visual": "dark palette, close-ups, sweat"},
        {"arc": "catharsis", "tone": "breaking",     "visual": "desaturated, broken compositions"},
        {"arc": "catharsis", "tone": "revelation",   "visual": "single color emphasis, symbolic"},
        {"arc": "tension",   "tone": "climactic",    "visual": "maximum contrast, explosion of color"},
        # Acte 3 : Résolution (épisodes 9-12)
        {"arc": "wonder",    "tone": "resolution",   "visual": "soft warm light, open spaces"},
        {"arc": "catharsis", "tone": "bittersweet",  "visual": "golden hour, silhouettes"},
        {"arc": "wonder",    "tone": "hopeful",      "visual": "sunrise, new beginning palette"},
        {"arc": "wonder",    "tone": "triumphant",   "visual": "full vibrant color, victory poses"},
    ]
}

# Variations visuelles par épisode pour éviter la monotonie
VISUAL_VARIATIONS = [
    "close-up character focus, detailed expressions",
    "wide establishing shots, environmental storytelling",
    "dynamic action composition, speed lines",
    "dramatic low angle, imposing perspective",
    "intimate two-shot, emotional connection",
    "aerial view, scope and scale",
    "night scene, dramatic lighting, moonlight",
    "indoor scene, warm artificial light",
    "battle scene, chaos and intensity",
    "quiet contemplative moment, negative space",
    "symbolic composition, metaphorical imagery",
    "triumphant full-body shot, epic stance",
]


def generate_series_plan_llm(series_title: str, n_episodes: int,
                              main_characters: list,
                              genre: str = "anime action drama",
                              logger=None) -> dict | None:
    """Génère un plan de série complet via LLM."""
    log = logger or logging.getLogger("episode_planner")

    if not UTILS_OK:
        log.error("[PLANNER] overlord_utils indisponible")
        return None

    chars_str = ", ".join(main_characters) if main_characters else "original characters"

    system = (
        "You are a professional anime series planner and screenwriter. "
        "Reply ONLY with valid JSON, no backticks, no explanation."
    )
    prompt = (
        f"Plan an anime series:\n"
        f"Title: {series_title}\n"
        f"Episodes: {n_episodes}\n"
        f"Main characters: {chars_str}\n"
        f"Genre: {genre}\n\n"
        f"Create a complete series plan with episode-by-episode breakdown.\n"
        f"Reply ONLY with JSON:\n"
        "{\n"
        '  "title": "Series Title",\n'
        '  "genre": ["genre1", "genre2"],\n'
        '  "main_theme": "the central theme of the series",\n'
        '  "overall_arc": "brief description of the series arc",\n'
        '  "episodes": [\n'
        '    {\n'
        '      "number": 1,\n'
        '      "title": "Episode Title",\n'
        '      "logline": "one sentence summary",\n'
        '      "universe_prompt": "visual description for AI generation (30-50 words)",\n'
        '      "key_characters": ["name1", "name2"],\n'
        '      "emotional_tone": "wonder/tension/catharsis/action/melancholy",\n'
        '      "key_visual": "one key visual moment to generate"\n'
        '    }\n'
        '  ]\n'
        "}"
    )

    log.info(f"[PLANNER] Génération plan {n_episodes} épisodes...")
    raw = fallback_llm(prompt, system=system, max_tokens=3000, logger=log)
    ok, data, err = safe_json_parse(raw, logger=log)

    if not ok or not isinstance(data, dict):
        log.error(f"[PLANNER] LLM JSON invalide : {err}")
        return None

    log.info(f"[PLANNER] Plan généré : {data.get('title', '?')} "
             f"({len(data.get('episodes', []))} épisodes)")
    return data


def build_series_plan(series_title: str, n_episodes: int,
                       main_characters: list = None,
                       universe_base: str = "evangelion",
                       use_llm: bool = True,
                       logger=None) -> dict:
    """
    Construit un plan de série complet.
    Tente le LLM, fallback sur un plan structuré automatique.
    """
    log = logger or logging.getLogger("episode_planner")

    characters = main_characters or []
    if CHARS_OK and not characters:
        characters = [v["name"] for v in list(PRESET_CHARACTERS.values())[:3]]

    # Essayer LLM d'abord
    if use_llm and UTILS_OK:
        plan = generate_series_plan_llm(
            series_title, n_episodes, characters, logger=log
        )
        if plan and plan.get("episodes"):
            plan["_source"] = "llm"
            return plan

    # Fallback : plan structuré automatique
    log.info("[PLANNER] Fallback : génération automatique du plan")
    arc_template = SERIES_ARC_TEMPLATES["3_act"]

    episodes = []
    for i in range(n_episodes):
        arc_data = arc_template[i % len(arc_template)]
        visual   = VISUAL_VARIATIONS[i % len(VISUAL_VARIATIONS)]

        # Rotation des personnages principaux
        char_idx  = i % max(len(characters), 1)
        key_chars = [characters[char_idx]] if characters else ["protagonist"]

        ep = {
            "number":         i + 1,
            "title":          f"Episode {i+1}: Chapter {i//3 + 1}",
            "logline":        f"Episode {i+1} of {series_title} — {arc_data['tone']} arc",
            "universe_prompt": (
                f"{universe_base} {arc_data['tone']} scene, "
                f"{visual}, {arc_data['visual']}, "
                f"featuring {', '.join(key_chars)}"
            ),
            "key_characters":  key_chars,
            "emotional_tone":  arc_data["arc"],
            "key_visual":      f"{arc_data['tone']} moment with {key_chars[0] if key_chars else 'character'}",
        }
        episodes.append(ep)

    plan = {
        "title":       series_title,
        "genre":       ["anime", "action", "drama"],
        "main_theme":  f"The journey and growth in {universe_base}",
        "overall_arc": f"A {n_episodes}-episode series following {', '.join(characters[:2])}",
        "episodes":    episodes,
        "_source":     "auto",
        "_generated":  datetime.now().isoformat(),
    }
    return plan


def save_plan(plan: dict, filename: str = None) -> Path:
    """Sauvegarde le plan sur le disque."""
    PLANS_DIR.mkdir(parents=True, exist_ok=True)
    if not filename:
        ts       = datetime.now().strftime("%Y%m%d_%H%M%S")
        title    = plan.get("title", "series").replace(" ", "_")[:20]
        filename = f"{ts}_{title}.json"
    path = PLANS_DIR / filename
    path.write_text(
        json.dumps(plan, indent=2, ensure_ascii=False),
        encoding='utf-8'
    )
    return path


def export_universes_file(plan: dict, output_path: Path = None) -> Path:
    """
    Exporte les universe_prompt de chaque épisode
    vers un fichier texte pour dream_mode --universes-file.
    """
    if not output_path:
        output_path = PLANS_DIR / f"universes_{plan.get('title','series')[:20].replace(' ','_')}.txt"

    PLANS_DIR.mkdir(parents=True, exist_ok=True)
    lines = [
        f"# Ov3rLoRd Universe File — {plan.get('title', 'Series')}",
        f"# Généré le {datetime.now().strftime('%Y-%m-%d %H:%M')}",
        f"# {len(plan.get('episodes',[]))} épisodes",
        "",
    ]
    for ep in plan.get("episodes", []):
        prompt = ep.get("universe_prompt", "")
        if prompt:
            lines.append(f"# Ep{ep['number']:02d}: {ep.get('title','?')}")
            lines.append(prompt)
            lines.append("")

    output_path.write_text("\n".join(lines), encoding='utf-8')
    return output_path


def inject_plan_into_memory(plan: dict, logger=None):
    """Enregistre le plan dans narrative_memory pour la continuité."""
    if not MEMORY_OK:
        return
    log = logger or logging.getLogger("episode_planner")
    try:
        mem = get_narrative_memory()
        for ep in plan.get("episodes", [])[:3]:  # Preview des 3 premiers
            fake_script = {
                "title":    ep.get("title", ""),
                "logline":  ep.get("logline", ""),
                "synopsis": ep.get("universe_prompt", ""),
                "characters": [{"name": c, "role": "main", "description": ""}
                               for c in ep.get("key_characters", [])],
                "acts": [],
            }
            mem.extract_from_script(
                fake_script,
                run_id=f"plan_ep{ep['number']}",
                universe=plan.get("title", ""),
                logger=log,
            )
        log.info(f"[PLANNER] Plan injecté dans narrative_memory")
    except Exception as e:
        log.warning(f"[PLANNER] Mémoire narrative : {e}")


def run_planner(series_title: str, n_episodes: int = 12,
                universe_base: str = "evangelion mecha anime",
                characters: list = None,
                export_for_dream: bool = True,
                logger=None) -> dict:
    """Point d'entrée principal."""
    log = logger or logging.getLogger("episode_planner")
    log.info(f"[PLANNER] Planification : '{series_title}' — {n_episodes} épisodes")

    plan = build_series_plan(
        series_title, n_episodes,
        main_characters=characters,
        universe_base=universe_base,
        logger=log,
    )

    plan_path = save_plan(plan)
    log.info(f"[PLANNER] Plan sauvegardé : {plan_path}")

    if export_for_dream:
        uni_path = export_universes_file(plan)
        plan["_universes_file"] = str(uni_path)
        log.info(f"[PLANNER] Univers exportés : {uni_path}")

    inject_plan_into_memory(plan, logger=log)

    if BUS_OK:
        try:
            bus = get_bus()
            bus.write("planner.series_title",   plan.get("title", ""),  agent_id="planner")
            bus.write("planner.episodes_count", n_episodes,             agent_id="planner")
            bus.write("planner.plan_path",      str(plan_path),         agent_id="planner")
            if export_for_dream:
                bus.write("planner.universes_file",
                          plan.get("_universes_file", ""),              agent_id="planner")
        except Exception:
            pass

    return plan


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Ov3rLoRd Episode Planner V1.70")
    parser.add_argument("--series",           type=str, default="Evangelion: New Saga")
    parser.add_argument("--episodes",         type=int, default=12)
    parser.add_argument("--universe-base",    type=str, default="evangelion mecha anime")
    parser.add_argument("--characters",       nargs="+", default=None)
    parser.add_argument("--load",             type=str, default=None,
                        help="Charger un plan existant")
    parser.add_argument("--export-universes", type=str, default=None,
                        help="Exporter les prompts vers ce fichier")
    parser.add_argument("--no-llm",           action="store_true",
                        help="Forcer le mode automatique sans LLM")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO,
                        format="%(asctime)s [%(levelname)s] %(message)s")

    if args.load:
        plan_path = Path(args.load)
        if not plan_path.exists():
            plan_path = PLANS_DIR / args.load
        if plan_path.exists():
            plan = json.loads(plan_path.read_text(encoding='utf-8'))
            print(f"Plan chargé : {plan.get('title')} — {len(plan.get('episodes',[]))} épisodes")
        else:
            print(f"Plan introuvable : {args.load}")
            sys.exit(1)
    else:
        plan = run_planner(
            series_title=args.series,
            n_episodes=args.episodes,
            universe_base=args.universe_base,
            characters=args.characters,
        )

    if args.export_universes:
        out = export_universes_file(plan, Path(args.export_universes))
        print(f"Univers exportés → {out}")
    else:
        # Afficher un résumé
        print(f"\n{'─'*55}")
        print(f"  {plan.get('title')} — {len(plan.get('episodes',[]))} épisodes")
        print(f"  Thème : {plan.get('main_theme','?')}")
        print(f"{'─'*55}")
        for ep in plan.get("episodes", [])[:6]:
            print(f"  Ep{ep['number']:02d} | {ep.get('title','?'):30s} | {ep.get('emotional_tone','?')}")
        if len(plan.get("episodes", [])) > 6:
            print(f"  ... ({len(plan.get('episodes',[]))-6} épisodes supplémentaires)")
        print(f"{'─'*55}")
        if plan.get("_universes_file"):
            print(f"\n  Dream mode : python agents/dream_mode.py "
                  f"--universes-file {plan['_universes_file']}")

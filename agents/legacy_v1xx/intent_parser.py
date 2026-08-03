# ██████╗ ██╗   ██╗██████╗ ██████╗ ██╗      ██████╗ ██████╗ ██████╗
# ██╔═══██╗██║   ██║╚════██╗██╔══██╗██║     ██╔═══██╗██╔══██╗██╔══██╗
# ██║   ██║██║   ██║ █████╔╝██████╔╝██║     ██║   ██║██████╔╝██║  ██║
# ██║   ██║╚██╗ ██╔╝ ╚═══██╗██╔══██╗██║     ██║   ██║██╔══██╗██║  ██║
# ╚██████╔╝ ╚████╔╝ ██████╔╝██║  ██║███████╗╚██████╔╝██║  ██║██████╔╝
# ╚═════╝   ╚═══╝  ╚═════╝ ╚═╝  ╚═╝╚══════╝ ╚═════╝ ╚═╝  ╚═╝╚═════╝
# Ov3rLoRd -- pipeline de production anime autonome (ComfyUI)
# https://github.com/Ov3rLoRd-MLEngineer
#
"""
agents/intent_parser.py — Agent Parseur d'Intention V1.70
Lit entre les lignes des demandes humaines naturelles et les traduit
en instructions précises pour les 55+ agents Ov3rLoRd.

"Je veux quelque chose dans le style de Rubilax"
→ universe="evangelion", sakuga_style="impact_heavy", 
   movement_types=["anticipation","impact","follow"],
   lora="asuka", steps=80, cfg=7.0

"Quelque chose de calme pour ce soir"
→ emotional_arc="peaceful", movement_types=["static","emotion"],
   color_palette=["soft green","warm white"], steps=50

"Lance la machine"
→ mode=FACTORY, batch=3, use_prompt_library=True, dream_mode=True

Le parser comprend :
  - Références culturelles (Rubilax, Imaishi, Nakamura, Wakfu, EVA)
  - Émotions et ambiances décrites naturellement
  - Niveaux d'urgence et de qualité
  - Intentions commerciales vs artistiques

Usage :
  from agents.intent_parser import parse_intent
  config = parse_intent("je veux quelque chose d'épique comme Rubilax")
  maestro.run_pipeline(config=config)
"""

import json
import logging
import re
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
    from agents.context_bus import get_bus
    BUS_OK = True
except ImportError:
    BUS_OK = False

INTENT_LOG = Path("workspace/logs/intent_parser.jsonl")

# ── Dictionnaire de références culturelles ────────────────────────────

CULTURAL_REFERENCES = {
    # Sakuga / Animateurs
    "rubilax":      {"style": "impact_heavy", "movement": ["anticipation","impact","follow"], "energy": "high"},
    "nakamura":     {"style": "fluid_combat", "movement": ["fast","impact","follow"],         "energy": "high"},
    "imaishi":      {"style": "over_the_top", "movement": ["fast","impact","fast"],           "energy": "maximum"},
    "wakfu":        {"style": "flash_symbols", "movement": ["normal","emotion","normal"],     "energy": "medium"},
    "ankama":       {"style": "layered_2d",    "movement": ["normal","slow","emotion"],       "energy": "medium"},
    # Univers
    "evangelion":   {"universe": "evangelion", "lora": "asuka", "tone": "dramatic"},
    "eva":          {"universe": "evangelion", "lora": "asuka", "tone": "dramatic"},
    "gundam":       {"universe": "gundam",     "lora": None,    "tone": "epic"},
    "miku":         {"universe": "hatsune miku", "lora": None,  "tone": "vibrant"},
    "vocaloid":     {"universe": "hatsune miku", "lora": None,  "tone": "vibrant"},
    "dragon ball":  {"universe": "dragon ball", "lora": None,   "tone": "battle"},
    "dbz":          {"universe": "dragon ball", "lora": None,   "tone": "battle"},
    # Ambiances
    "rubilax":      {"style": "impact_heavy", "arc": "tension"},
    "solaire":      {"arc": "wonder",    "palette": ["golden", "warm orange", "bright white"]},
    "nuit":         {"arc": "melancholy","palette": ["deep blue", "silver", "dark purple"]},
    "combat":       {"arc": "tension",   "movement": ["anticipation","impact","follow"]},
    "épique":       {"arc": "tension",   "steps": 70, "cfg": 7.0},
    "calme":        {"arc": "peaceful",  "movement": ["static","emotion"], "steps": 45},
    "triste":       {"arc": "catharsis", "palette": ["muted grey", "pale blue"]},
    "joyeux":       {"arc": "wonder",    "palette": ["vibrant", "warm", "bright"]},
}

# ── Mapping intention → paramètres pipeline ───────────────────────────

URGENCY_SIGNALS = {
    "vite":          {"batch": 1, "steps": 30, "quality_threshold": 60},
    "rapide":        {"batch": 1, "steps": 35, "quality_threshold": 65},
    "maintenant":    {"batch": 1, "steps": 30, "quality_threshold": 60},
    "ce soir":       {"batch": 1, "steps": 50, "quality_threshold": 73},
    "pour demain":   {"batch": 3, "steps": 60, "quality_threshold": 80},
    "parfait":       {"batch": 1, "steps": 80, "quality_threshold": 90},
    "la machine":    {"batch": 3, "dream_mode": True, "use_prompt_library": True},
    "à fond":        {"batch": 5, "dream_mode": True, "steps": 70},
    "nuit":          {"dream_mode": True, "batch": 0, "steps": 50},
}

QUALITY_SIGNALS = {
    "démo":     {"steps": 60, "quality_threshold": 80, "use_prompt_engineer": True},
    "asus":     {"steps": 80, "quality_threshold": 90, "use_prompt_engineer": True},
    "japan expo": {"steps": 70, "quality_threshold": 85},
    "portfolio": {"steps": 75, "quality_threshold": 85},
    "test":     {"steps": 30, "quality_threshold": 60},
    "poc":      {"steps": 35, "quality_threshold": 65},
}

DEFAULT_CONFIG = {
    "media_type":         "anime",
    "universe":           "evangelion battle mecha girl",
    "steps":              50,
    "cfg":                6.0,
    "sampler":            "dpmpp_2m",
    "scheduler":          "karras",
    "batch":              1,
    "quality_threshold":  73,
    "use_prompt_engineer": True,
    "use_prompt_library": False,
    "dream_mode":         False,
    "emotional_arc":      "wonder",
    "lora":               "",
}


def _extract_keywords(text: str) -> list[str]:
    """Extrait les mots-clés pertinents d'une phrase naturelle."""
    text_lower = text.lower()
    found = []
    for key in CULTURAL_REFERENCES:
        if key in text_lower:
            found.append(key)
    for key in URGENCY_SIGNALS:
        if key in text_lower:
            found.append(key)
    for key in QUALITY_SIGNALS:
        if key in text_lower:
            found.append(key)
    return found


def _parse_static(text: str) -> dict:
    """
    Parse statique basé sur les dictionnaires — rapide, sans LLM.
    Couvre 80% des cas courants.
    """
    text_lower = text.lower()
    config     = DEFAULT_CONFIG.copy()
    applied    = []

    # Références culturelles
    for ref, params in CULTURAL_REFERENCES.items():
        if ref in text_lower:
            if "universe" in params:
                config["universe"] = params["universe"]
            if "lora" in params and params["lora"]:
                config["lora"] = params["lora"]
            if "arc" in params:
                config["emotional_arc"] = params["arc"]
            if "steps" in params:
                config["steps"] = params["steps"]
            if "cfg" in params:
                config["cfg"] = params["cfg"]
            applied.append(ref)

    # Signaux d'urgence
    for signal, params in URGENCY_SIGNALS.items():
        if signal in text_lower:
            config.update(params)
            applied.append(signal)

    # Signaux de qualité
    for signal, params in QUALITY_SIGNALS.items():
        if signal in text_lower:
            config.update(params)
            applied.append(signal)

    # Détecter le nombre de scènes / batch
    numbers = re.findall(r'\b(\d+)\s*(?:scènes?|scenes?|runs?|fois)\b', text_lower)
    if numbers:
        config["batch"] = min(10, int(numbers[0]))

    config["_applied"]  = applied
    config["_method"]   = "static"
    return config


def parse_intent(user_input: str, logger=None) -> dict:
    """
    Point d'entrée principal.
    Parse une intention humaine naturelle et retourne une config pipeline.
    Essaie d'abord le parse statique, puis le LLM si ambigu.
    """
    log = logger or logging.getLogger("intent_parser")
    log.info(f"[INTENT] Parsing : '{user_input[:80]}'")

    # Parse statique d'abord
    config = _parse_static(user_input)

    # Si l'input est complexe et LLM disponible → enrichir
    if UTILS_OK and len(user_input.split()) > 6 and not config["_applied"]:
        config = _parse_with_llm(user_input, config, log)

    # Nettoyer les clés internes avant retour
    result = {k: v for k, v in config.items() if not k.startswith("_")}
    result["_raw_input"] = user_input
    result["_timestamp"] = datetime.now().isoformat()

    # Log
    INTENT_LOG.parent.mkdir(parents=True, exist_ok=True)
    with open(INTENT_LOG, 'a', encoding='utf-8') as f:
        f.write(json.dumps({
            "ts":     result["_timestamp"],
            "input":  user_input[:100],
            "arc":    result.get("emotional_arc"),
            "steps":  result.get("steps"),
            "batch":  result.get("batch"),
            "method": config.get("_method", "static"),
        }, ensure_ascii=False) + '\n')

    if BUS_OK:
        try:
            bus = get_bus()
            bus.write("intent.last_input",    user_input[:100], agent_id="intent")
            bus.write("intent.universe",       result.get("universe",""), agent_id="intent")
            bus.write("intent.emotional_arc",  result.get("emotional_arc",""), agent_id="intent")
        except Exception:
            pass

    log.info(
        f"[INTENT] → universe='{result.get('universe','')}' | "
        f"arc={result.get('emotional_arc')} | "
        f"steps={result.get('steps')} | "
        f"batch={result.get('batch')}"
    )
    return result


def _parse_with_llm(user_input: str, base_config: dict,
                     logger=None) -> dict:
    """Enrichissement LLM pour les intentions complexes."""
    log = logger or logging.getLogger("intent_parser.llm")

    system = (
        "You are an expert at understanding creative and technical intent "
        "for an AI anime production pipeline. "
        "Reply ONLY with valid JSON, no explanation."
    )
    prompt = (
        f"User intent: \"{user_input}\"\n\n"
        f"Translate this natural language request into pipeline configuration.\n"
        f"Consider: cultural references, emotional tone, urgency, quality level.\n\n"
        f"Reply ONLY with JSON:\n"
        "{\n"
        '  "universe": "evangelion|gundam|hatsune miku|dragon ball|original",\n'
        '  "emotional_arc": "wonder|tension|catharsis|peaceful|action",\n'
        '  "steps": 30-100,\n'
        '  "cfg": 5.0-8.0,\n'
        '  "batch": 1-5,\n'
        '  "quality_threshold": 60-95,\n'
        '  "use_prompt_engineer": true/false,\n'
        '  "use_prompt_library": true/false,\n'
        '  "dream_mode": true/false,\n'
        '  "lora": "asuka|rei|mari|",\n'
        '  "reasoning": "brief explanation of interpretation"\n'
        "}"
    )

    raw = fallback_llm(prompt, system=system, max_tokens=400, logger=log)
    ok, data, err = safe_json_parse(raw, logger=log)

    if ok and isinstance(data, dict):
        # Merger avec la config de base
        for key in ["universe","emotional_arc","steps","cfg","batch",
                    "quality_threshold","use_prompt_engineer",
                    "use_prompt_library","dream_mode","lora"]:
            if key in data and data[key] is not None:
                base_config[key] = data[key]
        base_config["_method"]    = "llm"
        base_config["_reasoning"] = data.get("reasoning", "")
        log.info(f"[INTENT] LLM enrichi : {data.get('reasoning','')[:60]}")
    else:
        log.warning(f"[INTENT] LLM échoué ({err}) — config statique conservée")

    return base_config


def interactive_mode():
    """Mode interactif — tape une intention, reçois la config."""
    print("\n" + "═"*60)
    print("  OV3RLORD INTENT PARSER — Mode Interactif")
    print("  Tape une intention naturelle, reçois la config pipeline")
    print("  'quit' pour quitter")
    print("═"*60 + "\n")

    examples = [
        "je veux quelque chose d'épique comme Rubilax",
        "quelque chose de calme pour ce soir",
        "lance la machine pour la nuit",
        "une démo pour ASUS, qualité maximale",
        "3 scènes evangelion en mode combat",
    ]
    print("Exemples :")
    for ex in examples:
        print(f"  → {ex}")
    print()

    while True:
        try:
            user_input = input("Intent > ").strip()
            if user_input.lower() in ("quit", "exit", "q"):
                break
            if not user_input:
                continue

            config = parse_intent(user_input)
            print(f"\n{'─'*50}")
            print(f"  Universe    : {config.get('universe')}")
            print(f"  Arc émot.   : {config.get('emotional_arc')}")
            print(f"  Steps       : {config.get('steps')}")
            print(f"  CFG         : {config.get('cfg')}")
            print(f"  Batch       : {config.get('batch')}")
            print(f"  Qualité min : {config.get('quality_threshold')}")
            print(f"  LoRa        : {config.get('lora') or 'auto'}")
            print(f"  Prompt Eng  : {config.get('use_prompt_engineer')}")
            print(f"  Dream mode  : {config.get('dream_mode')}")
            if config.get("_reasoning"):
                print(f"  Raisonnement: {config['_reasoning'][:60]}")
            print()

            cmd = (
                f"python maestro.py "
                f"--universe \"{config.get('universe','')}\" "
                f"--batch {config.get('batch',1)}"
            )
            if config.get("use_prompt_library"):
                cmd += " --use-prompt-library"
            if config.get("dream_mode"):
                cmd = f"python agents/dream_mode.py --universe \"{config.get('universe','')}\""
            print(f"  Commande : {cmd}")
            print(f"{'─'*50}\n")

        except KeyboardInterrupt:
            break


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Ov3rLoRd Intent Parser V1.70")
    parser.add_argument("--parse",       type=str, default=None)
    parser.add_argument("--interactive", action="store_true")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO,
                        format="%(asctime)s [%(levelname)s] %(message)s")

    if args.parse:
        config = parse_intent(args.parse)
        print(json.dumps({k:v for k,v in config.items()
                          if not k.startswith("_")}, indent=2, ensure_ascii=False))
    elif args.interactive:
        interactive_mode()
    else:
        print("=== Intent Parser V1.70 ===")
        tests = [
            "je veux quelque chose d'épique comme Rubilax",
            "quelque chose de calme pour ce soir",
            "lance la machine",
            "démo pour ASUS qualité maximale",
        ]
        for t in tests:
            c = parse_intent(t)
            print(f"'{t[:45]}...' → arc={c['emotional_arc']} steps={c['steps']} batch={c['batch']}")

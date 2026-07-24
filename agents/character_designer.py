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
agents/character_designer.py — Designer de Personnages V1.70
Génère des fiches personnages cohérentes et les injecte dans
narrative_memory + prompt_engineer pour une cohérence maximale
entre frames et entre épisodes.

Fonctions :
  - Génération fiche complète via LLM (physique, traits, LoRa, tags Booru)
  - Stockage persistant dans workspace/narrative/characters/
  - Injection automatique dans les jobs supervisor
  - Cohérence garantie : même personnage = mêmes tags = même LoRa

Usage :
  python agents/character_designer.py --create "Asuka Langley"
  python agents/character_designer.py --list
  python agents/character_designer.py --inject --run-id "maestro_xxx"
"""

import json
import logging
import random
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

CHARS_DIR   = Path("workspace/narrative/characters")
CHARS_INDEX = Path("workspace/narrative/characters/index.json")

AVAILABLE_LORAS = [
    "asuka-langley-soryuu-classic-ponyxl-lora-nochekaiser.safetensors",
    "mari-makinami-rebuild-ponyxl-lora-nochekaiser.safetensors",
    "rei-ayanami-classic-ponyxl-lora-nochekaiser.safetensors",
]

# Fiches prédéfinies pour les personnages Evangelion connus
PRESET_CHARACTERS = {
    "asuka langley": {
        "name":        "Asuka Langley Soryu",
        "series":      "Neon Genesis Evangelion",
        "role":        "protagonist",
        "lora":        "asuka-langley-soryuu-classic-ponyxl-lora-nochekaiser.safetensors",
        "lora_strength": 0.9,
        "base_tags": (
            "asuka langley, asuka langley soryu, "
            "red hair, long hair, blue eyes, hair clips, "
            "evangelion, red plug suit, unit-02 pilot, "
            "confident expression, tsundere"
        ),
        "action_tags": "dynamic pose, battle stance, intense expression, speed lines",
        "portrait_tags": "looking at viewer, close-up, sharp eyes, determined",
        "casual_tags": "school uniform, white shirt, red jacket",
        "physical": {
            "hair":       "long auburn-red hair with hair clips",
            "eyes":       "vivid blue eyes, intense gaze",
            "height":     "average, slender build",
            "distinctive": "hair clips, confident posture, German-Japanese heritage"
        },
        "personality": "fiercely competitive, proud, tsundere, hides vulnerability",
        "color_palette": ["deep red", "white", "blue", "orange"],
    },
    "rei ayanami": {
        "name":        "Rei Ayanami",
        "series":      "Neon Genesis Evangelion",
        "role":        "protagonist",
        "lora":        "rei-ayanami-classic-ponyxl-lora-nochekaiser.safetensors",
        "lora_strength": 0.85,
        "base_tags": (
            "rei ayanami, "
            "short blue hair, red eyes, pale skin, "
            "evangelion, white plug suit, unit-00 pilot, "
            "quiet expression, stoic"
        ),
        "action_tags": "calm battle stance, psychic aura, ethereal glow",
        "portrait_tags": "looking at viewer, blank expression, distant gaze",
        "casual_tags": "school uniform, white shirt",
        "physical": {
            "hair":       "short pale blue hair",
            "eyes":       "deep red eyes, vacant expression",
            "height":     "petite, slender",
            "distinctive": "pale complexion, bandages, otherworldly aura"
        },
        "personality": "quiet, obedient, emotionally detached, mysterious",
        "color_palette": ["pale blue", "white", "red", "grey"],
    },
    "mari makinami": {
        "name":        "Mari Makinami Illustrious",
        "series":      "Rebuild of Evangelion",
        "role":        "protagonist",
        "lora":        "mari-makinami-rebuild-ponyxl-lora-nochekaiser.safetensors",
        "lora_strength": 0.88,
        "base_tags": (
            "mari makinami, mari illustrious makinami, "
            "brown hair, pigtails, green eyes, glasses, "
            "evangelion, pink plug suit, unit-08 pilot, "
            "cheerful expression, energetic"
        ),
        "action_tags": "enthusiastic battle pose, happy battle face, energetic",
        "portrait_tags": "smile, cheerful, glasses, looking at viewer",
        "casual_tags": "school uniform, glasses, ponytails",
        "physical": {
            "hair":       "dark brown hair in pigtails",
            "eyes":       "green eyes behind round glasses",
            "height":     "average, athletic",
            "distinctive": "round glasses, cheerful demeanor, British accent"
        },
        "personality": "cheerful, combat-loving, mysterious past, always smiling",
        "color_palette": ["pink", "white", "brown", "green"],
    },
}


class CharacterSheet:
    """Fiche complète d'un personnage."""

    def __init__(self, data: dict):
        self.data = data

    @property
    def name(self) -> str:
        return self.data.get("name", "Unknown")

    @property
    def lora(self) -> str:
        return self.data.get("lora", random.choice(AVAILABLE_LORAS))

    @property
    def lora_strength(self) -> float:
        return float(self.data.get("lora_strength", 0.85))

    def get_tags(self, scene_type: str = "default") -> str:
        """Retourne les tags Booru adaptés au type de scène."""
        base = self.data.get("base_tags", "")
        extra = {
            "action":   self.data.get("action_tags", ""),
            "portrait": self.data.get("portrait_tags", ""),
            "casual":   self.data.get("casual_tags", ""),
            "default":  "",
        }.get(scene_type, "")
        tags = base
        if extra:
            tags += ", " + extra
        return tags

    def to_dict(self) -> dict:
        return self.data

    def save(self):
        CHARS_DIR.mkdir(parents=True, exist_ok=True)
        slug = self.name.lower().replace(" ", "_")
        path = CHARS_DIR / f"{slug}.json"
        path.write_text(
            json.dumps(self.data, indent=2, ensure_ascii=False),
            encoding='utf-8'
        )
        self._update_index()
        return path

    def _update_index(self):
        index = {}
        if CHARS_INDEX.exists():
            try:
                index = json.loads(CHARS_INDEX.read_text(encoding='utf-8'))
            except Exception:
                pass
        slug = self.name.lower().replace(" ", "_")
        index[slug] = {
            "name":       self.name,
            "series":     self.data.get("series", ""),
            "lora":       self.lora,
            "created_at": self.data.get("created_at", datetime.now().isoformat()),
        }
        CHARS_INDEX.write_text(
            json.dumps(index, indent=2, ensure_ascii=False),
            encoding='utf-8'
        )


def load_character(name: str) -> CharacterSheet | None:
    """Charge une fiche depuis le disque ou les presets."""
    slug = name.lower().replace(" ", "_").replace("-", "_")

    # Chercher dans les fichiers sauvegardés
    path = CHARS_DIR / f"{slug}.json"
    if path.exists():
        try:
            data = json.loads(path.read_text(encoding='utf-8'))
            return CharacterSheet(data)
        except Exception:
            pass

    # Chercher dans les presets
    for key, preset in PRESET_CHARACTERS.items():
        if key in name.lower() or name.lower() in key:
            sheet = CharacterSheet({**preset, "created_at": datetime.now().isoformat()})
            sheet.save()
            return sheet

    return None


def list_characters() -> list[dict]:
    """Liste tous les personnages disponibles."""
    if not CHARS_INDEX.exists():
        # Charger les presets par défaut
        for name, data in PRESET_CHARACTERS.items():
            CharacterSheet({**data, "created_at": datetime.now().isoformat()}).save()

    if CHARS_INDEX.exists():
        try:
            return list(json.loads(
                CHARS_INDEX.read_text(encoding='utf-8')
            ).values())
        except Exception:
            pass
    return []


def create_character_llm(name: str, series: str = "",
                          description: str = "",
                          logger=None) -> CharacterSheet | None:
    """
    Génère une fiche personnage complète via LLM.
    Utilisé pour les personnages non présents dans les presets.
    """
    log = logger or logging.getLogger("character_designer")

    if not UTILS_OK:
        log.error("[CHAR] overlord_utils indisponible")
        return None

    system = (
        "You are an anime character designer specialized in SDXL Booru-style tagging. "
        "Reply ONLY with valid JSON, no backticks, no explanation."
    )
    prompt = (
        f"Create a detailed character sheet for: {name}\n"
        f"Series: {series or 'original anime'}\n"
        f"Description hint: {description or 'anime style character'}\n\n"
        "Generate a complete character profile for use in AI image generation.\n"
        "Reply ONLY with JSON:\n"
        "{\n"
        '  "name": "Full Character Name",\n'
        '  "series": "Series Name",\n'
        '  "role": "protagonist/antagonist/supporting",\n'
        '  "base_tags": "comma-separated Booru tags for this character",\n'
        '  "action_tags": "extra tags for action scenes",\n'
        '  "portrait_tags": "extra tags for portrait/close-up scenes",\n'
        '  "casual_tags": "extra tags for casual/everyday scenes",\n'
        '  "physical": {\n'
        '    "hair": "hair description",\n'
        '    "eyes": "eye description",\n'
        '    "height": "height/build",\n'
        '    "distinctive": "distinctive features"\n'
        '  },\n'
        '  "personality": "brief personality description",\n'
        '  "color_palette": ["color1", "color2", "color3"]\n'
        "}"
    )

    raw = fallback_llm(prompt, system=system, max_tokens=800, logger=log)
    ok, data, err = safe_json_parse(raw, logger=log)
    if not ok or not isinstance(data, dict):
        log.error(f"[CHAR] LLM JSON invalide : {err}")
        return None

    # Assigner une LoRa
    data.setdefault("lora", random.choice(AVAILABLE_LORAS))
    data.setdefault("lora_strength", 0.85)
    data.setdefault("series", series)
    data["created_at"] = datetime.now().isoformat()
    data["generated_by"] = "llm"

    sheet = CharacterSheet(data)
    sheet.save()
    log.info(f"[CHAR] Fiche créée : {sheet.name}")

    # Enregistrer dans narrative_memory
    if MEMORY_OK:
        try:
            mem = get_narrative_memory()
            mem.register_character(
                name=sheet.name,
                description=data.get("personality", ""),
                lora=sheet.lora,
                universe=series,
            )
        except Exception as e:
            log.warning(f"[CHAR] Mémoire narrative : {e}")

    return sheet


def inject_character_into_jobs(jobs: list, character_name: str,
                                scene_types: list = None,
                                logger=None) -> list:
    """
    Injecte les tags d'un personnage dans les jobs supervisor.
    Garantit que tous les shots du run utilisent le même personnage
    avec la même LoRa et les mêmes tags de base.
    """
    log = logger or logging.getLogger("character_designer")

    sheet = load_character(character_name)
    if not sheet:
        log.warning(f"[CHAR] Personnage inconnu : {character_name} — tentative LLM")
        sheet = create_character_llm(character_name, logger=log)
    if not sheet:
        log.error(f"[CHAR] Impossible de créer la fiche pour : {character_name}")
        return jobs

    log.info(f"[CHAR] Injection {sheet.name} dans {len(jobs)} jobs "
             f"(LoRa: {sheet.lora[:35]}...)")

    enriched = []
    for i, job in enumerate(jobs):
        j = job.copy()

        # Type de scène depuis les métadonnées
        shot_meta  = j.get("_shot_meta", {})
        shot_type  = shot_meta.get("shot_type", "default").lower()
        scene_type = "portrait" if "close" in shot_type else \
                     "action"   if "action" in shot_type or \
                                   "fight"  in shot_meta.get("emotion", "").lower() \
                     else "default"

        if scene_types and i < len(scene_types):
            scene_type = scene_types[i]

        char_tags = sheet.get_tags(scene_type)

        # Injecter les tags en tête du prompt positif
        current_pos = j.get("positive", "")
        if char_tags not in current_pos:
            j["positive"] = f"{char_tags}, {current_pos}" if current_pos else char_tags

        # Forcer la LoRa du personnage
        j["lora"]     = sheet.lora
        j["strength"] = sheet.lora_strength
        j["det_lora"] = sheet.lora

        # Injecter la palette de couleur dans le prompt pour la cohérence
        palette = sheet.data.get("color_palette", [])
        if palette and i == 0:  # ancrer la palette sur le premier shot
            palette_str = ", ".join(palette[:2])
            if palette_str not in j["positive"]:
                j["positive"] += f", {palette_str} color scheme"

        enriched.append(j)
        log.debug(f"[CHAR] Job {i+1}: {scene_type} → {char_tags[:50]}...")

    if BUS_OK:
        try:
            get_bus().write("character.active_name",  sheet.name, agent_id="character")
            get_bus().write("character.active_lora",  sheet.lora, agent_id="character")
            get_bus().write("character.jobs_injected", len(enriched), agent_id="character")
        except Exception:
            pass

    return enriched


def detect_characters_in_script(script: dict) -> list[str]:
    """Détecte les personnages mentionnés dans un script."""
    text = json.dumps(script).lower()
    found = []
    for key in PRESET_CHARACTERS:
        if key in text:
            found.append(PRESET_CHARACTERS[key]["name"])
    # Dédupliquer
    return list(dict.fromkeys(found))


def init_preset_characters():
    """Initialise les fiches des personnages presets sur le disque."""
    CHARS_DIR.mkdir(parents=True, exist_ok=True)
    for name, data in PRESET_CHARACTERS.items():
        sheet = CharacterSheet({**data, "created_at": datetime.now().isoformat()})
        sheet.save()
    return len(PRESET_CHARACTERS)


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Ov3rLoRd Character Designer V1.70")
    parser.add_argument("--create",  type=str, default=None, help="Créer fiche via LLM")
    parser.add_argument("--series",  type=str, default="")
    parser.add_argument("--list",    action="store_true", help="Lister les personnages")
    parser.add_argument("--init",    action="store_true", help="Init presets Evangelion")
    parser.add_argument("--show",    type=str, default=None, help="Afficher une fiche")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO,
                        format="%(asctime)s [%(levelname)s] %(message)s")

    if args.init:
        n = init_preset_characters()
        print(f"[OK] {n} fiches presets initialisées dans {CHARS_DIR}")

    elif args.list:
        chars = list_characters()
        if not chars:
            init_preset_characters()
            chars = list_characters()
        print(f"\n{'─'*50}")
        print(f"  Personnages disponibles ({len(chars)})")
        print(f"{'─'*50}")
        for c in chars:
            print(f"  {c['name']:30s} | {c['series'][:25]}")
            print(f"    LoRa: {c['lora'][:55]}")
        print(f"{'─'*50}")

    elif args.show:
        sheet = load_character(args.show)
        if sheet:
            print(json.dumps(sheet.to_dict(), indent=2, ensure_ascii=False))
        else:
            print(f"Personnage '{args.show}' introuvable.")

    elif args.create:
        print(f"Création fiche : {args.create}...")
        sheet = create_character_llm(args.create, series=args.series)
        if sheet:
            print(json.dumps(sheet.to_dict(), indent=2, ensure_ascii=False))
        else:
            print("Échec de la création.")

    else:
        parser.print_help()

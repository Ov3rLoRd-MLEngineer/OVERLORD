"""
negative_bank.py V1.0
Ov3rLoRd — Onibaku Gumi 鬼爆組
Banque de prompts négatifs spécifiques par personnage, univers et shot_type.
Intégration : importé par agent_supervisor_v2.py et prompt_translator.py
"""

import os
import json
import logging
from pathlib import Path

log = logging.getLogger("negative_bank")

# ── Base commune (toujours active) ─────────────────────────────────────────────
BASE_NEGATIVE = (
    "bad anatomy, extra fingers, six fingers, deformed hands, missing fingers, "
    "fused fingers, mutated hands, poorly drawn hands, extra limbs, extra arms, "
    "extra legs, cloned face, disfigured, gross proportions, malformed limbs, "
    "missing arms, missing legs, extra digit, fewer digits, "
    "blurry, out of focus, low quality, jpeg artifacts, compression artifacts, "
    "watermark, signature, text, logo, username, artist name, "
    "multiple people, crowd, duplicate, copy, "
    "3d render, cgi, realistic, photo, photograph, "
    "western style, disney style, chibi, deformed"
)

# ── Négatifs par personnage ────────────────────────────────────────────────────
CHARACTER_NEGATIVES = {
    "asuka": (
        "blue hair, black hair, brown hair, wrong hair color, "
        "rei ayanami, misato, mari, kaworu, shinji, "
        "wrong eye color, green eyes, red eyes, "
        "plugsuit, bodysuit, uniform, suit, clothes, dressed, "
        "multiple girls, incorrect uniform"
    ),
    "asuka_plugsuit": (
        "blue hair, black hair, brown hair, wrong hair color, "
        "rei ayanami, misato, mari, kaworu, shinji, "
        "wrong eye color, green eyes, "
        "naked, nude, topless, undressed, "
        "wrong plugsuit color, blue plugsuit, white plugsuit"
    ),
    "rei": (
        "orange hair, brown hair, red hair, "
        "asuka, misato, mari, "
        "wrong eye color, green eyes, brown eyes, "
        "plugsuit, bodysuit, uniform"
    ),
    "rei_plugsuit": (
        "orange hair, brown hair, red hair, "
        "asuka, misato, mari, "
        "naked, nude, topless, "
        "wrong plugsuit color, red plugsuit, orange plugsuit"
    ),
    "mari": (
        "orange hair, blue hair, "
        "asuka, rei, "
        "wrong glasses style, no glasses, "
        "plugsuit"
    ),
    "misato": (
        "school uniform, plugsuit, "
        "asuka, rei, "
        "young girl, teenager"
    ),
    "shinji": (
        "female, girl, "
        "asuka, rei, "
        "plugsuit"
    ),
    "generic_female": (
        "male, man, boy, masculine features, flat chest"
    ),
    "generic_male": (
        "female, woman, girl, feminine features"
    ),
}

# ── Négatifs par univers ────────────────────────────────────────────────────────
UNIVERSE_NEGATIVES = {
    "evangelion": (
        "mecha visible in background during close-up, "
        "wrong AT field color, inconsistent eva unit color, "
        "modern clothing, contemporary fashion"
    ),
    "gundam": (
        "wrong mobile suit proportions, "
        "non-mechanical elements in cockpit, "
        "modern civilian clothes in military scene"
    ),
    "trigger": (
        "realistic shading, photorealistic, "
        "muted colors, desaturated"
    ),
    "shinkai": (
        "flat colors, no atmospheric perspective, "
        "harsh outlines, cel shading"
    ),
    "generic": "",
}

# ── Négatifs par shot_type ─────────────────────────────────────────────────────
SHOT_NEGATIVES = {
    "close_up":        "full body visible, legs visible, background characters",
    "extreme_close_up":"neck visible, shoulders visible, body visible",
    "medium_shot":     "extreme close-up, eyes only, crop at neck",
    "wide_shot":       "cropped limbs, missing feet, missing head",
    "over_shoulder":   "both faces fully visible, no depth",
    "low_angle":       "top-down view, bird's eye, high angle",
    "high_angle":      "low angle, worm's eye view",
    "dutch_angle":     "perfectly horizontal horizon",
    "establishing":    "close-up details, facial details as focus",
    "insert":          "wide shot, multiple characters",
    "pov":             "third person, observer visible",
    "two_shot":        "solo character, more than two characters",
}

# ── Négatifs par ambiance/lighting ─────────────────────────────────────────────
LIGHTING_NEGATIVES = {
    "night":        "bright daylight, noon sun, harsh shadows",
    "day":          "dark, night, shadows, moody",
    "dramatic":     "flat lighting, even illumination, studio light",
    "soft":         "harsh shadows, rim light, dramatic contrast",
    "backlit":      "front lit, flat lighting",
    "neon":         "natural lighting, daylight, warm tones",
    "explosion":    "calm lighting, soft light",
    "underwater":   "dry environment, sharp focus, normal colors",
}


# ══════════════════════════════════════════════════════════════════════════════
class NegativeBank:
    """
    Assemble le prompt négatif optimal pour un job donné.
    Usage :
        nb = NegativeBank()
        neg = nb.build(character="asuka_plugsuit", universe="evangelion",
                       shot_type="close_up", lighting="dramatic")
    """

    def __init__(self, custom_path: "Path | None" = None):
        self.custom = {}
        if custom_path and Path(custom_path).exists():
            try:
                with open(custom_path, "r", encoding="utf-8") as f:
                    self.custom = json.load(f)
                log.info(f"Négatifs custom chargés depuis {custom_path}")
            except Exception as e:
                log.warning(f"Impossible de charger négatifs custom: {e}")

    # ── Build ──────────────────────────────────────────────────────────────────
    def build(
        self,
        character: str = "",
        universe:  str = "generic",
        shot_type: str = "",
        lighting:  str = "",
        extra:     str = "",
    ) -> str:
        """Retourne la chaîne négative fusionnée et dédupliquée."""
        parts = [BASE_NEGATIVE]

        char_key = character.lower().replace(" ", "_").replace("-", "_")
        if char_key in CHARACTER_NEGATIVES:
            parts.append(CHARACTER_NEGATIVES[char_key])
        elif char_key:
            log.debug(f"Personnage '{char_key}' non trouvé dans la banque")

        uni_key = universe.lower()
        if uni_key in UNIVERSE_NEGATIVES and UNIVERSE_NEGATIVES[uni_key]:
            parts.append(UNIVERSE_NEGATIVES[uni_key])

        shot_key = shot_type.lower().replace(" ", "_")
        if shot_key in SHOT_NEGATIVES:
            parts.append(SHOT_NEGATIVES[shot_key])

        light_key = lighting.lower()
        if light_key in LIGHTING_NEGATIVES:
            parts.append(LIGHTING_NEGATIVES[light_key])

        for key in [char_key, uni_key, shot_key]:
            if key in self.custom:
                parts.append(self.custom[key])

        if extra:
            parts.append(extra)

        tokens = []
        seen   = set()
        for part in parts:
            for token in part.split(","):
                t = token.strip().lower()
                if t and t not in seen:
                    seen.add(t)
                    tokens.append(token.strip())

        return ", ".join(tokens)

    # ── Helpers ────────────────────────────────────────────────────────────────
    def list_characters(self) -> list:
        return sorted(CHARACTER_NEGATIVES.keys())

    def list_universes(self) -> list:
        return sorted(UNIVERSE_NEGATIVES.keys())

    def list_shot_types(self) -> list:
        return sorted(SHOT_NEGATIVES.keys())

    def export_json(self, path: "str | Path") -> None:
        data = {
            "base":       BASE_NEGATIVE,
            "characters": CHARACTER_NEGATIVES,
            "universes":  UNIVERSE_NEGATIVES,
            "shot_types": SHOT_NEGATIVES,
            "lightings":  LIGHTING_NEGATIVES,
        }
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        log.info(f"Banque exportée → {path}")


# ══════════════════════════════════════════════════════════════════════════════
_bank = NegativeBank()


def get_negative(
    character: str = "",
    universe:  str = "generic",
    shot_type: str = "",
    lighting:  str = "",
    extra:     str = "",
) -> str:
    """Raccourci module-level — importé par supervisor et translator."""
    return _bank.build(
        character=character,
        universe=universe,
        shot_type=shot_type,
        lighting=lighting,
        extra=extra,
    )


# ══════════════════════════════════════════════════════════════════════════════
if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Negative Bank — Ov3rLoRd")
    parser.add_argument("--character", default="",        help="Clé personnage")
    parser.add_argument("--universe",  default="generic", help="Univers")
    parser.add_argument("--shot-type", default="",        help="Type de plan")
    parser.add_argument("--lighting",  default="",        help="Ambiance lumière")
    parser.add_argument("--extra",     default="",        help="Négatifs additionnels")
    parser.add_argument("--export",    default="",        help="Exporter banque en JSON")
    parser.add_argument("--list",      action="store_true", help="Lister les clés")
    args = parser.parse_args()

    nb = NegativeBank()

    if args.list:
        print("Personnages:", nb.list_characters())
        print("Univers:",     nb.list_universes())
        print("Shot types:",  nb.list_shot_types())
    elif args.export:
        nb.export_json(args.export)
    else:
        result = nb.build(
            character=args.character,
            universe=args.universe,
            shot_type=getattr(args, "shot_type", ""),
            lighting=args.lighting,
            extra=args.extra,
        )
        print("\n=== NEGATIVE PROMPT ===")
        print(result)
        print(f"\n({len(result.split(','))} tokens)")

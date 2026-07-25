"""
Ov3rLoRd - watchdog_config.py V1.0
Studio Ov3rLoRd

Seuils adaptatifs pour watchdog, clip_validator et inpaint_queue.
Tous les agents lisent depuis ce module au lieu de hardcoder leurs seuils.
Les valeurs sont surchargees par le context_bus si disponible.
"""

import os
import logging
from pathlib import Path

log = logging.getLogger("watchdog_config")

# ── Presets par scene_type ─────────────────────────────────────────────────────
SCENE_PRESETS = {
    "default": {
        "luma_min":          0.35,   # luminosite minimale acceptable
        "luma_max":          0.95,   # luminosite maximale acceptable
        "clip_threshold":    0.80,   # coherence CLIP inter-shots
        "motion_blur_ok":    False,  # flou mouvement = defaut rejet
        "dark_zones_ok":     False,  # zones sombres = defaut rejet
        "inpaint_on_reject": True,   # inpaint auto sur REJECT
        "max_rejects":       3,      # max REJECT avant abandon shot
    },
    "action_dynamic": {
        "luma_min":          0.15,   # scenes sombres/contrastees OK
        "luma_max":          0.98,
        "clip_threshold":    0.72,   # coherence relachee (mouvement = variation normale)
        "motion_blur_ok":    True,   # flou mouvement attendu et valide
        "dark_zones_ok":     True,   # zones sombres = dramatique, pas defaut
        "inpaint_on_reject": True,
        "max_rejects":       2,
    },
    "cockpit_static": {
        "luma_min":          0.40,
        "luma_max":          0.90,
        "clip_threshold":    0.85,   # coherence stricte — decor fixe
        "motion_blur_ok":    False,
        "dark_zones_ok":     True,   # cockpit EVA souvent sombre
        "inpaint_on_reject": True,
        "max_rejects":       3,
    },
    "contemplative": {
        "luma_min":          0.30,
        "luma_max":          0.92,
        "clip_threshold":    0.82,
        "motion_blur_ok":    False,
        "dark_zones_ok":     True,
        "inpaint_on_reject": True,
        "max_rejects":       2,
    },
}


def load_config(scene_type: str = None) -> dict:
    """
    Charge la config watchdog pour le scene_type donne.
    Ordre de priorite :
      1. context_bus (runtime)
      2. argument scene_type
      3. variable env OVERLORD_SCENE_TYPE
      4. preset 'default'

    Retourne un dict avec tous les seuils resolus.
    """
    # Tentative lecture context_bus
    bus_config = _read_from_bus()

    # Resolution scene_type
    resolved_scene = (
        bus_config.get("scene_type")
        or scene_type
        or os.environ.get("OVERLORD_SCENE_TYPE", "default")
    )

    # Preset de base
    preset = SCENE_PRESETS.get(resolved_scene, SCENE_PRESETS["default"]).copy()
    preset["scene_type"] = resolved_scene

    # Surcharge depuis le bus (valeurs individuelles)
    for key in ["luma_min", "luma_max", "clip_threshold",
                "motion_blur_ok", "dark_zones_ok", "inpaint_on_reject", "max_rejects"]:
        if key in bus_config:
            preset[key] = bus_config[key]
            log.debug(f"  bus override {key} = {bus_config[key]}")

    log.info(
        f"WatchdogConfig : scene={resolved_scene} | "
        f"luma=[{preset['luma_min']},{preset['luma_max']}] | "
        f"clip={preset['clip_threshold']} | "
        f"motion_blur={preset['motion_blur_ok']}"
    )
    return preset


def _read_from_bus() -> dict:
    """
    Tente de lire les cles watchdog depuis context_bus.
    Retourne un dict vide si le bus est indisponible (pas de crash).
    """
    result = {}
    try:
        sys_path_backup = None

        import sys
        _repo_root = Path(__file__).resolve().parent.parent
        if str(_repo_root) not in sys.path:
            sys.path.insert(0, str(_repo_root))
        import config
        project_root = config.OVERLORD_ROOT

        from agents.context_bus import get_bus
        bus = get_bus()

        key_map = {
            "director.scene_type":      "scene_type",
            "director.luma_min":        "luma_min",
            "director.luma_max":        "luma_max",
            "director.clip_threshold":  "clip_threshold",
            "director.motion_blur":     "motion_blur_ok",
            "director.expected_dark":   "dark_zones_ok",
            "director.max_rejects":     "max_rejects",
        }

        for bus_key, config_key in key_map.items():
            val = bus.read(bus_key)
            if val is not None:
                result[config_key] = val

    except Exception as e:
        log.debug(f"context_bus indisponible ({e}) — utilisation preset uniquement")

    return result


def qwenvl_prompts_for_scene(scene_type: str, character: str = "asuka") -> dict:
    """
    Retourne les prompts positif/negatif QwenVL adaptes au scene_type.
    Ces prompts sont utilises par visual_validator.py pour juger les images.

    Retourne :
      {
        "positive": "...",   # ce qu on veut voir
        "negative": "...",   # ce qu on ne veut pas voir
        "focus":    "...",   # zone d attention prioritaire
      }
    """
    base_char = {
        "asuka": "Asuka Langley Soryu in red plugsuit, orange hair, blue eyes, twin tails",
        "rei":   "Rei Ayanami in white plugsuit, blue hair, red eyes",
        "mari":  "Mari Makinami in white plugsuit, brown hair, glasses",
    }.get(character, character)

    scene_prompts = {
        "action_dynamic": {
            "positive": (
                f"{base_char}, dynamic running pose, athletic motion, "
                "correct anatomy, single character, clear figure"
            ),
            "negative": (
                "extra limbs, deformed anatomy, two characters, "
                "static pose, blurry face, wrong hair color"
            ),
            "focus": "anatomy correctness and single character presence",
        },
        "cockpit_static": {
            "positive": (
                f"{base_char}, seated in Eva cockpit, LCL fluid environment, "
                "correct face, correct hair, emotional expression"
            ),
            "negative": (
                "wrong character, extra characters, deformed face, "
                "incorrect plugsuit color, outside cockpit"
            ),
            "focus": "character identity and cockpit environment consistency",
        },
        "contemplative": {
            "positive": (
                f"{base_char}, calm expression, correct anatomy, "
                "single character, detailed face"
            ),
            "negative": (
                "action pose, multiple characters, deformed, "
                "incorrect hair color, incorrect eye color"
            ),
            "focus": "character identity and emotional tone",
        },
        "default": {
            "positive": (
                f"{base_char}, correct anatomy, single character, "
                "masterpiece quality, detailed"
            ),
            "negative": (
                "extra limbs, deformed, multiple characters, "
                "low quality, blurry"
            ),
            "focus": "overall quality and character correctness",
        },
    }

    return scene_prompts.get(scene_type, scene_prompts["default"])


# ── Export direct des presets (pour inspection) ────────────────────────────────
def list_presets() -> None:
    import json
    print("\nPresets disponibles :")
    for name, preset in SCENE_PRESETS.items():
        print(f"\n  [{name}]")
        for k, v in preset.items():
            print(f"    {k:<22} : {v}")


if __name__ == "__main__":
    import sys
    logging.basicConfig(level=logging.DEBUG)
    if "--list" in sys.argv:
        list_presets()
    else:
        scene = sys.argv[1] if len(sys.argv) > 1 else "action_dynamic"
        cfg   = load_config(scene)
        print(f"\nConfig resolue pour '{scene}' :")
        for k, v in cfg.items():
            print(f"  {k:<22} : {v}")
        print("\nQwenVL prompts :")
        qp = qwenvl_prompts_for_scene(scene, "asuka")
        for k, v in qp.items():
            print(f"  {k:<10} : {v}")

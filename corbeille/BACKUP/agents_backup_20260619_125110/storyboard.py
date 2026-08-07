"""
agents/storyboard.py — Agent Storyboard V1.49
Transforme un ScriptDocument en ShotList ComfyUI.
Publie les resultats sur le context_bus.
"""

import json
import logging
from datetime import datetime, timezone
from pathlib import Path

try:
    from agents.overlord_utils import fallback_llm, safe_json_parse
    UTILS_OK = True
except ImportError:
    UTILS_OK = False
    fallback_llm    = None
    safe_json_parse = None

try:
    from agents.director import get_director
    DIRECTOR_OK = True
except ImportError:
    DIRECTOR_OK = False
    get_director = None

try:
    from agents.context_bus import get_bus
    BUS_OK = True
except ImportError:
    BUS_OK = False

CLAUDE_MODEL  = "claude-sonnet-4-6"
STORYBOARD_DIR= Path("workspace/storyboards")

MAX_STORYBOARD_ITERATIONS = 2
SHOT_QUALITY_THRESHOLD    = 65

SHOT_TYPES = {
    "ECU": "Extreme Close-Up", "CU": "Close-Up", "MCU": "Medium Close-Up",
    "MS":  "Medium Shot",      "MLS":"Medium Long Shot", "LS":"Long Shot",
    "VLS": "Very Long Shot",   "ELS":"Extreme Long Shot","OTS":"Over The Shoulder",
    "POV": "Point Of View",    "BIRD":"Bird Eye View",   "WORM":"Worm Eye View",
}

CAMERA_MOVES = [
    "static","pan_left","pan_right","tilt_up","tilt_down",
    "zoom_in","zoom_out","dolly_in","dolly_out","crane_up",
    "tracking","handheld","360_orbit",
]


def _llm(prompt: str, system: str = "", logger: logging.Logger = None) -> str:
    log = logger or logging.getLogger("storyboard.llm")
    if not UTILS_OK or not fallback_llm:
        log.error("[STORYBOARD] overlord_utils indisponible")
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


# ── Recuperation du style depuis le bus ──────────────────────────────
def _get_style_from_bus() -> str:
    """Lit style.style_prompt depuis le bus pour enrichir les prompts."""
    if not BUS_OK:
        return ""
    try:
        return get_bus().read("style.style_prompt") or ""
    except Exception:
        return ""


# ── Generateur de shot list ───────────────────────────────────────────
def generate_shotlist(script: dict, media_type: str = "anime",
                      logger: logging.Logger = None) -> dict:
    log = logger or logging.getLogger("storyboard.generator")
    log.info(f"[STORYBOARD] Generation — titre='{script.get('title','?')}'")

    visual_style  = script.get("visual_style", "style anime japonais")
    color_palette = ", ".join(script.get("color_palette", []))
    characters    = json.dumps(script.get("characters", []), ensure_ascii=False)[:800]
    all_scenes    = []
    for act in script.get("acts", []):
        all_scenes.extend(act.get("scenes", []))
    scenes_json = json.dumps(all_scenes[:15], ensure_ascii=False)[:2000]

    # Enrichissement style depuis le bus
    style_suffix = _get_style_from_bus()
    if style_suffix:
        visual_style = f"{visual_style}, {style_suffix}"

    # Enrichissement emotionnel Director
    if DIRECTOR_OK:
        try:
            d       = get_director()
            n_shots = len(all_scenes) or 12
            for i, scene in enumerate(all_scenes[:15]):
                ep = d.get_emotion_for_shot(i, n_shots)
                if ep.get("comfyui_tags"):
                    hint = scene.get("visual_prompt_hint","")
                    scene["visual_prompt_hint"] = f"{hint}, {', '.join(ep['comfyui_tags'][:3])}"
        except Exception:
            pass

    shot_types_desc = "\n".join(f"- {k}: {v}" for k, v in SHOT_TYPES.items())

    system = (
        "Tu es un directeur artistique et storyboarder professionnel specialise "
        "dans la production animee assistee par IA. Reponds UNIQUEMENT en JSON valide."
    )
    prompt = (
        f"Cree une shot list pour ce projet.\n"
        f"Titre : {script.get('title','Untitled')}\n"
        f"Style : {visual_style}\nPalette : {color_palette}\nMedia : {media_type}\n\n"
        f"Personnages :\n{characters}\n\nScenes :\n{scenes_json}\n\n"
        f"Types de plans :\n{shot_types_desc}\n\n"
        f"JSON : project_title, total_shots, estimated_total_duration_seconds, "
        f"shots[] (shot_id, scene_ref, act, shot_type, camera_move, duration_seconds, "
        f"characters, location, action, emotion, comfyui_positive, comfyui_negative, "
        f"comfyui_width, comfyui_height, transition, audio_cue, is_key_frame, "
        f"3d_required, vfx_notes), production_notes."
    )

    raw    = _llm(prompt, system=system, logger=log)
    result = _parse(raw, logger=log)
    if result:
        log.info(f"[STORYBOARD] {result.get('total_shots','?')} shots generes")
        return result
    log.error("[STORYBOARD] JSON invalide")
    return {"error": "json_parse_failed", "raw": raw[:500]}


# ── Review qualite ────────────────────────────────────────────────────
def review_shotlist(shotlist: dict, logger: logging.Logger = None) -> dict:
    log          = logger or logging.getLogger("storyboard.reviewer")
    shots_sample = json.dumps(shotlist.get("shots", [])[:5], ensure_ascii=False)[:1500]

    system = "Tu es un directeur de la photographie. Reponds UNIQUEMENT en JSON valide."
    prompt = (
        f"Analyse cette shot list ({shotlist.get('total_shots','?')} plans) :\n"
        f"{shots_sample}\n\n"
        f"JSON : score_global(0-100), validated(bool), issues[], "
        f"prompt_quality, correction_instructions."
    )

    raw    = _llm(prompt, system=system, logger=log)
    result = _parse(raw, logger=log)
    if result:
        log.info(f"[STORYBOARD REVIEW] Score={result.get('score_global',0)}/100 | "
                 f"Valide={'oui' if result.get('validated') else 'non'}")
        return result
    return {"validated": True, "score_global": 60, "correction_instructions": ""}


# ── Conversion shotlist -> jobs ───────────────────────────────────────
def shotlist_to_jobs(shotlist: dict, base_lora: str = "",
                     logger: logging.Logger = None) -> list:
    log        = logger or logging.getLogger("storyboard.converter")
    jobs       = []
    prod_notes = shotlist.get("production_notes", {})
    rec_lora   = base_lora or prod_notes.get("recommended_lora", "")

    for shot in shotlist.get("shots", []):
        total = shotlist.get("total_shots", 0)
        if not shot.get("is_key_frame", True) and total > 30:
            continue
        jobs.append({
            "shot_id":   shot.get("shot_id", ""),
            "scene_ref": shot.get("scene_ref", ""),
            "lora":      rec_lora,
            "det_lora":  "",
            "strength":  1.0,
            "width":     shot.get("comfyui_width",  1024),
            "height":    shot.get("comfyui_height",  576),
            "positive":  shot.get("comfyui_positive", ""),
            "negative":  shot.get("comfyui_negative",
                                  "bad quality, blurry, deformed, watermark, signature"),
            "_shot_meta": {
                "shot_type": shot.get("shot_type"),
                "camera":    shot.get("camera_move"),
                "duration_s":shot.get("duration_seconds"),
                "transition":shot.get("transition"),
                "audio_cue": shot.get("audio_cue"),
                "3d_needed": shot.get("3d_required", False),
                "vfx":       shot.get("vfx_notes", ""),
            },
        })

    log.info(f"[STORYBOARD -> JOBS] {len(jobs)} jobs depuis {shotlist.get('total_shots','?')} shots")
    return jobs


# ── Pipeline complet ──────────────────────────────────────────────────
def run_storyboard(script: dict, media_type: str = "anime",
                   base_lora: str = "",
                   logger: logging.Logger = None) -> tuple:
    log = logger or logging.getLogger("storyboard")
    log.info("[STORYBOARD] Pipeline demarre")
    STORYBOARD_DIR.mkdir(parents=True, exist_ok=True)

    shotlist = generate_shotlist(script, media_type, logger=log)
    if "error" in shotlist:
        log.error("[STORYBOARD] Echec generation")
        return shotlist, []

    for iteration in range(1, MAX_STORYBOARD_ITERATIONS + 1):
        review = review_shotlist(shotlist, logger=log)
        if review.get("validated") and review.get("score_global", 0) >= SHOT_QUALITY_THRESHOLD:
            log.info(f"[STORYBOARD] OK Valide iteration {iteration}")
            break
        log.warning(f"[STORYBOARD] Iteration {iteration} non validee — on continue")

    ts    = datetime.now(tz=timezone.utc).strftime("%Y%m%d_%H%M%S")
    title = script.get("title", "untitled").replace(" ", "_")[:30]
    path  = STORYBOARD_DIR / f"{ts}_{title}_storyboard.json"
    path.write_text(json.dumps(shotlist, indent=2, ensure_ascii=False), encoding="utf-8")
    log.info(f"[STORYBOARD] Sauvegarde -> {path}")

    jobs = shotlist_to_jobs(shotlist, base_lora=base_lora, logger=log)

    # Publier sur le context_bus
    if BUS_OK:
        try:
            bus = get_bus()
            bus.write("storyboard.shots_count", shotlist.get("total_shots", 0), agent_id="storyboard")
            bus.write("storyboard.jobs_count",  len(jobs),                       agent_id="storyboard")
            bus.write("storyboard.saved_to",    str(path),                       agent_id="storyboard")
        except Exception as e:
            log.warning(f"[STORYBOARD] Publication bus echouee : {e}")

    return shotlist, jobs


if __name__ == "__main__":
    import sys, io
    if hasattr(sys.stdout,'buffer'):
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
    logging.basicConfig(level=logging.INFO)
    fake_script = {
        "title": "Dragon Ball Ov3rLoRd",
        "visual_style": "anime style, high detail, dynamic action",
        "color_palette": ["orange","blue","gold"],
        "characters": [{"name":"Goku","visual_prompt":"1male, muscular, spiky hair, orange gi"}],
        "acts": [{"act":1,"title":"L'eveil","scenes":[
            {"scene_id":"S01E01","location":"Plaine","time_of_day":"Aube",
             "characters":["Goku"],"action":"Goku contemple l'horizon",
             "visual_prompt_hint":"1male, spiky hair, orange gi, desert, sunrise"}
        ]}]
    }
    shotlist, jobs = run_storyboard(fake_script)
    print(f"Shots: {shotlist.get('total_shots')} | Jobs: {len(jobs)}")
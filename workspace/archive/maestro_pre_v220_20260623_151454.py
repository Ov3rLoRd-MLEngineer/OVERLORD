"""
maestro.py V1.49n -- Chef d'Orchestre Ov3rLoRd
Pipeline : SOURCING -> SCENARIO -> STORYBOARD -> PRODUCTION -> POST-PROD -> 3D
FIX V1.49n :
  - sys.stdout.reconfigure() supprime (incompatible avec overlord_utils_utf8)
  - state initialisé avant le bloc try/finally pour eviter NameError dans finally
"""

import overlord_utils_utf8  # noqa -- force UTF-8 console des le demarrage

import sys
import os
import json
import logging
import argparse
import time
from pathlib import Path
from datetime import datetime

# ── Resolution du package AGENTS ─────────────────────────────────────
_BASE_DIR = Path(__file__).resolve().parent
if str(_BASE_DIR) not in sys.path:
    sys.path.insert(0, str(_BASE_DIR))

_agents_lower = _BASE_DIR / "agents"
_agents_upper = _BASE_DIR / "AGENTS"
if not _agents_lower.exists() and _agents_upper.exists():
    import importlib, types
    _pkg = types.ModuleType("agents")
    _pkg.__path__ = [str(_agents_upper)]
    _pkg.__package__ = "agents"
    sys.modules["agents"] = _pkg

# BASE defini ici -- avant tout import qui en depend
BASE = Path(__file__).parent

# ── Imports internes ──────────────────────────────────────────────────

# Utils centraux V1.42 -- en premier car d'autres en dependent
try:
    from agents.overlord_utils import (
        get_api_key, build_headers, retry_api, safe_json_parse,
        fallback_llm, ensure_workspace, ensure_env_file
    )
    UTILS_OK = True
    ensure_env_file(BASE)  # BASE est defini maintenant
except Exception:
    UTILS_OK = False

# Context Bus V1.48
try:
    from agents.context_bus import get_bus
    BUS_OK = True
    _bus = get_bus()
except Exception:
    BUS_OK = False
    _bus = None

# Director V1.48
try:
    from agents.director import get_director, Director, ProductionMode
    DIRECTOR_OK = True
except Exception:
    DIRECTOR_OK = False
    get_director = None

# Pipeline Conscience V1.45
try:
    from agents.pipeline_conscience import get_conscience, PipelineConscience
    CONSCIENCE_OK = True
    _conscience = get_conscience()
    _adaptive_params = _conscience.get_params()
except Exception:
    CONSCIENCE_OK = False
    _conscience = None
    _adaptive_params = {}

# Agents pipeline
try:
    from agents.sourcing   import run_sourcing;    SOURCING_OK   = True
except Exception:
    SOURCING_OK = False
    def run_sourcing(media_type="anime", logger=None):
        _log = logger or logging.getLogger("sourcing.fallback")
        _log.warning("[SOURCING] Module indisponible -- fallback minimal")
        return {"media_type": media_type, "brief": "Fallback sourcing",
                "hot_keywords": ["anime"], "top_reddit": [], "top_rss": [],
                "top_trends": [], "raw_count": {"reddit":0,"rss":0,"trends":0}}

try:
    from agents.scenario   import run_scenario;    SCENARIO_OK   = True
except Exception:
    SCENARIO_OK = False
    def run_scenario(**kwargs):
        _log = kwargs.get("logger") or logging.getLogger("scenario.fallback")
        _log.warning("[SCENARIO] Module indisponible -- fallback actif")
        return {"title":"Fallback","scenes":[],"media_type":kwargs.get("media_type","anime")}

try:
    from agents.storyboard import run_storyboard;  STORYBOARD_OK = True
except Exception:
    STORYBOARD_OK = False
    def run_storyboard(**kwargs):
        _log = kwargs.get("logger") or logging.getLogger("storyboard.fallback")
        _log.warning("[STORYBOARD] Module indisponible -- fallback actif")
        return {"shots": []}, []

try:
    from agents.postprod   import run_postprod;    POSTPROD_OK   = True
except Exception:
    POSTPROD_OK = False
    def run_postprod(**kwargs):
        _log = kwargs.get("logger") or logging.getLogger("postprod.fallback")
        _log.warning("[POSTPROD] Module indisponible -- fallback actif")
        return {"status": "fallback"}

try:
    from agents.prompt_library import run_prompt_library, init_data_structure
    PROMPT_LIB_OK = True
except Exception:
    PROMPT_LIB_OK = False
    def run_prompt_library(**kwargs): return []
    def init_data_structure(): pass

try:
    from agents.grok_client import grok_available
    GROK_OK = True
except Exception:
    GROK_OK = False
    def grok_available(): return False

try:
    from agents.prompt_engineer import engineer_jobs
    PROMPT_ENG_OK = True
except Exception:
    PROMPT_ENG_OK = False
    def engineer_jobs(jobs, **kw): return jobs

try:
    from agents.quality_gate import validate_workflow_file, auto_fix
    QUALITY_GATE_OK = True
except Exception:
    QUALITY_GATE_OK = False
    def validate_workflow_file(p, **kw): return {"valid": True, "errors": [], "warnings": []}
    def auto_fix(wf, **kw): return wf, 0

try:
    from agents.session_reporter import generate_report
    REPORTER_OK = True
except Exception:
    REPORTER_OK = False
    def generate_report(**kw): return {}

try:
    from agents.config_manager import get_config as get_cfg
    CONFIG_OK = True
except Exception:
    CONFIG_OK = False
    def get_cfg(): return None

try:
    from agents.gpu_optimizer import optimize_for_gpu, detect_gpu
    GPU_OPT_OK = True
except Exception:
    GPU_OPT_OK = False
    def detect_gpu(): return "unknown"
    def optimize_for_gpu(*a, **kw): return {}

try:
    from agents.style_continuity import apply_continuity, create_anchor, analyze_drift
    STYLE_OK = True
except Exception:
    STYLE_OK = False
    def apply_continuity(jobs, **kw): return jobs
    def create_anchor(*a, **kw): return None
    def analyze_drift(*a, **kw): return {}

try:
    from agents.character_sheet_generator import (
        generate_character_sheet, load_character_sheet, PRESET_CHARACTERS
    )
    CSG_OK = True
except Exception:
    CSG_OK = False

try:
    from agents.style_dna_generator import generate_style_dna, get_latest_style_dna
    SDG_OK = True
except Exception:
    SDG_OK = False

try:
    from agents.audit_logger import log_run_start, log_run_end
    AUDIT_OK = True
except Exception:
    AUDIT_OK = False
    def log_run_start(*a, **kw): return False
    def log_run_end(*a, **kw): return False

try:
    from agents.narrative_memory import get_narrative_memory
    NARRATIVE_OK = True
except Exception:
    NARRATIVE_OK = False
    def get_narrative_memory(): return None

try:
    from agents.character_designer import (
        detect_characters_in_script, inject_character_into_jobs,
        init_preset_characters, load_character
    )
    CHARS_OK = True
except Exception:
    CHARS_OK = False
    def detect_characters_in_script(s): return []
    def inject_character_into_jobs(j, **kw): return j
    def init_preset_characters(): return 0

try:
    from agents.episode_planner import run_planner, export_universes_file
    PLANNER_OK = True
except Exception:
    PLANNER_OK = False
    def run_planner(**kw): return {}

try:
    from agents.transmedia_publisher import run_publisher
    PUBLISHER_OK = True
except Exception:
    PUBLISHER_OK = False
    def run_publisher(**kw): return {}

try:
    from agents.agent_registry import get_registry
    REGISTRY_OK = True
except Exception:
    REGISTRY_OK = False
    def get_registry(): return None

try:
    from agents.critic  import CriticAgent, Verdict
    CRITIC_OK = True
except Exception as e:
    CRITIC_OK = False
    logging.getLogger("maestro").warning(f"[WARN] critic.py indisponible : {e}")

try:
    from agents.obs_agent import create_obs_agent
    OBS_OK = True
except Exception:
    OBS_OK = False

try:
    from agents.agent_3d_modeler import Agent3DModeler
    AGENT_3D_OK = True
except Exception:
    AGENT_3D_OK = False

try:
    from agents.checkpoint_manager import CheckpointManager, get_checkpoint_manager
    CP_OK = True
except Exception as e:
    CP_OK = False
    logging.getLogger("maestro").warning(f"[WARN] checkpoint_manager.py indisponible : {e}")

try:
    from agents.comfy_memory import VRAMManager
    VRAM_OK = True
except Exception:
    VRAM_OK = False

try:
    from agents.watchdog import Watchdog, analyze_frame
    WATCHDOG_OK = True
except Exception as e:
    WATCHDOG_OK = False
    logging.getLogger("maestro").warning(f"[WARN] watchdog.py indisponible : {e}")

# Supervisor
try:
    import importlib.util as _ilu
    _spec = _ilu.spec_from_file_location("supervisor", BASE / "agent_supervisor_v2.py")
    _sup  = _ilu.module_from_spec(_spec)
    _spec.loader.exec_module(_sup)
    supervisor    = _sup
    SUPERVISOR_OK = True
except Exception as e:
    SUPERVISOR_OK = False
    logging.getLogger("maestro").warning(f"[WARN] agent_supervisor_v2.py indisponible : {e}")


# ── Configuration ─────────────────────────────────────────────────────
WORKSPACE      = Path("workspace")
PIPELINE_STATE = WORKSPACE / "pipeline_state.json"
LOGS_DIR       = WORKSPACE / "logs"
ARCHIVE_DIR    = WORKSPACE / "archive"

BLOCKS      = ["sourcing","scenario","storyboard","production","postprod","3d"]
MEDIA_TYPES = ["anime","manga","comics","3d","photoreal","art","game","short","film"]

TELEGRAM_TOKEN   = ""
TELEGRAM_CHAT_ID = ""
MAX_CRITIC_RETRIES = 2


# ── Logging ───────────────────────────────────────────────────────────
def init():
    for d in [WORKSPACE, LOGS_DIR, ARCHIVE_DIR]:
        d.mkdir(parents=True, exist_ok=True)

def get_logger(run_id: str) -> logging.Logger:
    logger = logging.getLogger(f"maestro.{run_id}")
    if logger.handlers:
        return logger
    logger.setLevel(logging.DEBUG)
    fmt = logging.Formatter(
        "%(asctime)s [%(levelname)-8s] %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S"
    )
    ch = logging.StreamHandler(sys.stdout)
    ch.setLevel(logging.INFO)
    ch.setFormatter(fmt)
    logger.addHandler(ch)
    fh = logging.FileHandler(LOGS_DIR / f"{run_id}.log", encoding="utf-8")
    fh.setLevel(logging.DEBUG)
    fh.setFormatter(fmt)
    logger.addHandler(fh)
    return logger


# ── Etat persistant ───────────────────────────────────────────────────
def load_state() -> dict:
    if PIPELINE_STATE.exists():
        try:
            return json.loads(PIPELINE_STATE.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {"run_id": None, "current_block": None, "completed": [], "data": {}}

def save_state(state: dict):
    PIPELINE_STATE.write_text(
        json.dumps(state, indent=2, ensure_ascii=False, default=str),
        encoding="utf-8"
    )

def clear_state():
    save_state({"run_id": None, "current_block": None, "completed": [], "data": {}})


# ── Notifications ─────────────────────────────────────────────────────
def notify(msg: str, logger: logging.Logger = None):
    if not TELEGRAM_TOKEN or not TELEGRAM_CHAT_ID:
        return
    import requests as req
    try:
        req.post(
            f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage",
            json={"chat_id": TELEGRAM_CHAT_ID, "text": f"[MAESTRO] {msg}"},
            timeout=10
        )
    except Exception:
        pass


# ── Wrapper Critique ──────────────────────────────────────────────────
def _critic_gate(critic, handoff: str, data: dict,
                 extra: dict, logger: logging.Logger,
                 block_fn, block_args: dict,
                 retries: int = MAX_CRITIC_RETRIES) -> tuple:
    if not CRITIC_OK or critic is None:
        return data, extra

    for attempt in range(retries + 1):
        report = critic.validate_handoff(handoff, data, extra)

        if report.verdict == Verdict.PASS:
            return report.data_out or data, extra
        if report.verdict in (Verdict.WARN, Verdict.REPAIR):
            logger.warning(f"[MAESTRO/CRITIQUE] {handoff} {report.verdict.value}")
            return report.data_out or data, extra
        if report.verdict == Verdict.REJECT:
            if attempt < retries:
                logger.warning(
                    f"[MAESTRO/CRITIQUE] {handoff} REJECT "
                    f"(tentative {attempt+1}/{retries}) -- relance"
                )
                time.sleep(3)
                try:
                    data = block_fn(**block_args)
                    if isinstance(data, tuple):
                        data, extra_new = data
                        if extra is not None:
                            extra.update(extra_new if isinstance(extra_new, dict) else {})
                except Exception as e:
                    logger.error(f"[MAESTRO] Relance echouee : {e}")
            else:
                logger.error(f"[MAESTRO/CRITIQUE] {handoff} REJECT definitif")
                return report.data_out or data, extra
        if report.verdict == Verdict.HALT:
            raise StopIteration(f"HALT decide par le Critique sur {handoff}")

    return data, extra


# ── Blocs pipeline ────────────────────────────────────────────────────

def block_bible_visuelle(cfg, state, logger, cp_mgr=None):
    """
    Run 0 : genere les fiches personnages et le Style DNA si absents.
    Execute une seule fois par projet (skip si fiches deja presentes).
    """
    logger.info("=" * 55)
    logger.info("BLOC 0 -- BIBLE VISUELLE (Run 0)")
    logger.info("=" * 55)

    universe   = cfg.get("universe", "evangelion")
    style_name = cfg.get("style_name", "evangelion")
    run_id     = state.get("run_id", "")
    results    = {"characters": {}, "style_dna": None}

    # ── Fiches personnages ──
    if CSG_OK:
        chars_to_gen = cfg.get("characters", list(PRESET_CHARACTERS.keys()))
        for char_name in chars_to_gen:
            existing = load_character_sheet(char_name)
            if existing and existing.get("success"):
                logger.info("[BIBLE] Fiche %s deja presente -- skip", char_name)
                results["characters"][char_name] = existing
            else:
                logger.info("[BIBLE] Generation fiche %s...", char_name)
                sheet = generate_character_sheet(
                    char_name, quick=True, logger=logger
                )
                results["characters"][char_name] = sheet
                if not sheet.get("success"):
                    logger.warning("[BIBLE] Fiche %s incomplete", char_name)
    else:
        logger.warning("[BIBLE] character_sheet_generator indisponible -- skip")

    # ── Style DNA ──
    if SDG_OK:
        existing_dna = get_latest_style_dna()
        if existing_dna and existing_dna.get("success"):
            logger.info("[BIBLE] Style DNA deja present (%s) -- skip",
                        existing_dna.get("style_name","?"))
            results["style_dna"] = existing_dna
        else:
            logger.info("[BIBLE] Generation Style DNA %s...", style_name)
            dna = generate_style_dna(
                style_name=style_name, run_id=run_id, logger=logger
            )
            results["style_dna"] = dna
            if not dna.get("success"):
                logger.warning("[BIBLE] Style DNA echec -- production continue")
    else:
        logger.warning("[BIBLE] style_dna_generator indisponible -- skip")

    state["data"]["bible_visuelle"] = results
    state["completed"].append("bible_visuelle")
    if cp_mgr:
        cp_mgr.save_block("bible_visuelle", {"chars": list(results["characters"].keys())})
    logger.info("[BIBLE] Run 0 termine -- %d fiche(s) | DNA: %s",
                len(results["characters"]),
                "OK" if results.get("style_dna", {}) and
                results["style_dna"].get("success") else "ABSENT")
    return results


def block_sourcing(cfg, state, logger, critic, watchdog, cp_mgr=None):
    logger.info("=" * 55)
    logger.info("BLOC 1 -- SOURCING")
    logger.info("=" * 55)

    if watchdog and not watchdog.can_proceed("sourcing"):
        logger.warning("[SOURCING] Circuit breaker ouvert -- skip")
        return {"media_type": cfg.get("media_type","anime"),
                "brief": "Fallback sourcing", "hot_keywords": ["anime"]}

    if not SOURCING_OK:
        report = {"media_type": cfg.get("media_type","anime"),
                  "brief": cfg.get("brief","Production standard"),
                  "hot_keywords": cfg.get("keywords",["anime","action"])}
        logger.warning("[SOURCING] Module indisponible -- fallback config")
    else:
        report = run_sourcing(media_type=cfg.get("media_type","anime"), logger=logger)
        if watchdog:
            watchdog.breakers["sourcing"].record_success()

    report, _ = _critic_gate(
        critic, "sourcing->scenario", report, None, logger,
        run_sourcing, {"media_type": cfg.get("media_type","anime"), "logger": logger}
    )

    if BUS_OK and _bus:
        _bus.write("sourcing.trend_report", report, agent_id="sourcing")
        _bus.write("sourcing.media_type",   cfg.get("media_type","anime"), agent_id="sourcing")

    state["data"]["trend_report"] = report
    state["completed"].append("sourcing")
    save_state(state)
    if cp_mgr:
        cp_mgr.save_block("sourcing", report)
    logger.info(f"[SOURCING] OK Brief : {report.get('brief','')[:80]}")
    return report


def block_scenario(trend_report, cfg, state, logger, critic, watchdog, cp_mgr=None):
    logger.info("=" * 55)
    logger.info("BLOC 2 -- SCENARIO")
    logger.info("=" * 55)

    if watchdog and not watchdog.can_proceed("scenario"):
        logger.error("[SCENARIO] Circuit breaker ouvert -- arret")
        return {"error": "circuit_breaker_open"}

    quality_threshold = cfg.get(
        "script_quality_threshold",
        _adaptive_params.get("script_quality_threshold", 70)
    )
    if BUS_OK and _bus:
        bus_threshold = _bus.read("director.quality_threshold")
        if bus_threshold is not None:
            quality_threshold = bus_threshold

    script = run_scenario(
        trend_report      = trend_report,
        media_type        = cfg.get("media_type","anime"),
        duration          = cfg.get("duration","short"),
        universe          = cfg.get("universe",""),
        quality_threshold = quality_threshold,
        logger            = logger
    )
    if watchdog:
        (watchdog.breakers["scenario"].record_success()
         if "error" not in script
         else watchdog.breakers["scenario"].record_failure())

    script, _ = _critic_gate(
        critic, "scenario->storyboard", script, None, logger,
        run_scenario,
        {"trend_report": trend_report, "media_type": cfg.get("media_type","anime"),
         "duration": cfg.get("duration","short"), "universe": cfg.get("universe",""),
         "logger": logger}
    )

    if BUS_OK and _bus:
        _bus.write("scenario.title",  script.get("title",""), agent_id="scenario")
        _bus.write("scenario.scenes", len(script.get("scenes",[])), agent_id="scenario")

    state["data"]["script"] = script
    state["completed"].append("scenario")
    save_state(state)
    if cp_mgr:
        cp_mgr.save_block("scenario", script)
    logger.info(f"[SCENARIO] OK '{script.get('title','?')}'")
    return script


def block_storyboard(script, cfg, state, logger, critic, watchdog, cp_mgr=None):
    logger.info("=" * 55)
    logger.info("BLOC 3 -- STORYBOARD")
    logger.info("=" * 55)

    if watchdog and not watchdog.can_proceed("storyboard"):
        logger.error("[STORYBOARD] Circuit breaker ouvert -- arret")
        return {}, []
    if not STORYBOARD_OK:
        logger.error("[STORYBOARD] Module indisponible")
        return {}, []

    emotion_arc = None
    if BUS_OK and _bus:
        emotion_arc = _bus.read("director.emotion_arc")

    shotlist, jobs = run_storyboard(
        script     = script,
        media_type = cfg.get("media_type","anime"),
        base_lora  = cfg.get("lora",""),
        logger     = logger
    )
    if watchdog:
        (watchdog.breakers["storyboard"].record_success()
         if jobs else watchdog.breakers["storyboard"].record_failure())

    extra = {"jobs": jobs}
    shotlist, extra = _critic_gate(
        critic, "storyboard->production", shotlist, extra, logger,
        lambda **kw: run_storyboard(**kw),
        {"script": script, "media_type": cfg.get("media_type","anime"),
         "base_lora": cfg.get("lora",""), "logger": logger}
    )
    jobs = extra.get("jobs", jobs) if extra else jobs

    if BUS_OK and _bus:
        _bus.write("storyboard.shots_count", len(jobs), agent_id="storyboard")
        if emotion_arc:
            _bus.write("storyboard.emotion_arc", emotion_arc, agent_id="storyboard")

    state["data"]["shotlist"] = shotlist
    state["data"]["jobs"]     = jobs
    state["completed"].append("storyboard")
    save_state(state)
    if cp_mgr:
        cp_mgr.save_block("storyboard", {"shots": len(jobs)})
    logger.info(f"[STORYBOARD] OK {len(jobs)} jobs")
    return shotlist, jobs


def block_production(jobs, cfg, state, logger, critic, watchdog, cp_mgr=None):
    logger.info("=" * 55)
    logger.info("BLOC 4 -- PRODUCTION COMFYUI")
    logger.info("=" * 55)

    if not SUPERVISOR_OK:
        logger.error("[PRODUCTION] agent_supervisor_v2 indisponible")
        return {"success": 0, "failed": len(jobs), "total": len(jobs)}
    if not jobs:
        logger.warning("[PRODUCTION] Aucun job")
        return {"success": 0, "failed": 0, "total": 0}
    if watchdog:
        health = watchdog.health_check()
        if not health.get("comfyui",{}).get("up", True):
            logger.error("[PRODUCTION] ComfyUI hors ligne -- abandon")
            return {"success": 0, "failed": len(jobs), "total": len(jobs)}

    # Enrichir jobs depuis prompt_library si activé
    if cfg.get("use_prompt_library") and PROMPT_LIB_OK:
        lib_jobs = run_prompt_library(
            universe=cfg.get("universe",""),
            n_jobs=len(jobs),
            logger=logger
        )
        if lib_jobs:
            for i, job in enumerate(jobs):
                lib = lib_jobs[i] if i < len(lib_jobs) else lib_jobs[-1]
                # Prompts locaux enrichissent le job storyboard
                job.setdefault("positive",  lib.get("positive",""))
                job.setdefault("negative",  lib.get("negative",""))
                job.setdefault("lora",      lib.get("lora",""))
                job.setdefault("strength",  lib.get("strength", 1.0))
                job.setdefault("det_lora",  lib.get("det_lora",""))
                job.setdefault("width",     lib.get("width", 1024))
                job.setdefault("height",    lib.get("height", 1536))
            logger.info(f"[PRODUCTION] PromptLib injectée : {len(lib_jobs)} jobs enrichis")

    for job in jobs:
        job.setdefault("lora",     cfg.get("lora",""))
        job.setdefault("strength", cfg.get("strength", 1.0))
        job.setdefault("width",    cfg.get("width", 1024))
        job.setdefault("height",   cfg.get("height", 1536))

    # Libérer la VRAM ComfyUI avant chaque batch — évite les images répétées
    try:
        import requests as _rq
        _cb = "http://127.0.0.1:8188"
        _rq.post(f"{_cb}/interrupt", timeout=5)
        _rq.post(f"{_cb}/queue", json={"clear": True}, timeout=5)
        _rq.post(f"{_cb}/free",
                 json={"unload_models": True, "free_memory": True}, timeout=10)
        logger.info("[GPU] VRAM ComfyUI libérée avant batch")
    except Exception:
        pass

    # Quality gate : valider le workflow avant envoi
    if QUALITY_GATE_OK:
        wf_path = "Combined_V35_API.json"
        gate_result = validate_workflow_file(wf_path, logger=logger)
        if not gate_result["valid"]:
            logger.error(f"[QUALITY_GATE] Workflow corrompu — tentative autofix")
            import json as _json
            from pathlib import Path as _Path
            wf_raw = _json.loads(_Path(wf_path).read_text(encoding="utf-8"))
            wf_fixed, n_fixes = auto_fix(wf_raw, logger=logger)
            if n_fixes > 0:
                _Path(wf_path).write_text(
                    _json.dumps(wf_fixed, indent=2, ensure_ascii=False), encoding="utf-8")
                logger.info(f"[QUALITY_GATE] {n_fixes} corrections appliquées")
            else:
                logger.error("[QUALITY_GATE] Impossible de corriger — production risquée")

    # Prompt engineering : upsample les prompts si activé
    if PROMPT_ENG_OK and cfg.get("use_prompt_engineer", True):
        jobs = engineer_jobs(jobs, logger=logger)
        logger.info(f"[PROMPT_ENG] Jobs enrichis : {len(jobs)}")

    run_id_prod = state["run_id"] + "_prod"
    results = supervisor.run_batch_advanced(jobs, run_id=run_id_prod, resume=True)

    if watchdog and ARCHIVE_DIR.exists():
        frames_data   = []
        frame_reports = []
        for png in sorted(ARCHIVE_DIR.rglob("*.png"))[-len(jobs):]:
            try:
                img_bytes = png.read_bytes()
                fr = watchdog.guard_frame(img_bytes, shot_id=png.stem,
                                          palette=cfg.get("color_palette",[]))
                frames_data.append(img_bytes)
                frame_reports.append(fr.to_dict())
            except Exception as e:
                logger.warning(f"[WATCHDOG/FRAME] Erreur lecture {png.name} : {e}")
        if len(frames_data) >= 2:
            coherence = watchdog.guard_sequence(frames_data)
            results["sequence_coherence"] = coherence

    extra = {"archive_dir": str(ARCHIVE_DIR)}
    results, _ = _critic_gate(critic, "production->postprod", results, extra, logger, None, {})

    if BUS_OK and _bus:
        _bus.write("production.success", results.get("success",0), agent_id="production")
        _bus.write("production.failed",  results.get("failed", 0), agent_id="production")

    state["data"]["production_results"] = results
    state["completed"].append("production")
    save_state(state)
    logger.info(f"[PRODUCTION] OK {results.get('success',0)} succes | {results.get('failed',0)} echecs")
    return results


def block_postprod(shotlist, cfg, state, logger, critic, watchdog, cp_mgr=None):
    logger.info("=" * 55)
    logger.info("BLOC 5 -- POST-PRODUCTION")
    logger.info("=" * 55)

    if not POSTPROD_OK:
        logger.warning("[POST-PROD] Module indisponible -- ignore")
        return {}
    # Vérifier images dans l'archive complète (sous-dossiers run inclus)
    _has_images = ARCHIVE_DIR.exists() and (
        any(ARCHIVE_DIR.rglob("*.png")) or
        any(ARCHIVE_DIR.rglob("*.jpg")) or
        any(ARCHIVE_DIR.rglob("*.webp"))
    )
    if not _has_images:
        logger.warning("[POST-PROD] Aucune image -- ignore")
        return {}

    # Résolution du chemin archive du run en cours
    run_archive = None
    if BUS_OK and _bus:
        try:
            bus_dir = _bus.read("production.image_dir")
            if bus_dir and Path(bus_dir).exists():
                run_archive = Path(bus_dir)
                logger.info(f"[POST-PROD] Archive run depuis bus : {run_archive}")
        except Exception:
            pass
    if not run_archive:
        # Fallback : run_id le plus récent dans ARCHIVE_DIR
        if ARCHIVE_DIR.exists():
            runs = sorted(ARCHIVE_DIR.iterdir(), key=lambda p: p.stat().st_mtime, reverse=True)
            if runs:
                run_archive = runs[0]
                logger.info(f"[POST-PROD] Archive run fallback : {run_archive}")
    if not run_archive:
        run_archive = ARCHIVE_DIR

    result = run_postprod(
        shotlist       = shotlist,
        image_dir      = run_archive,
        dialogue_lines = cfg.get("dialogues", []),
        music_path     = cfg.get("music_path"),
        export_preset  = cfg.get("export_preset","anime_1080p"),
        tts_lang       = cfg.get("tts_lang","fr"),
        logger         = logger
    )
    if BUS_OK and _bus:
        _bus.write("postprod.video", result.get("files",{}).get("video",""), agent_id="postprod")

    state["data"]["postprod"] = result
    state["completed"].append("postprod")
    save_state(state)
    logger.info(f"[POST-PROD] OK Export -> {result.get('files',{}).get('video','N/A')}")
    return result


def block_3d(jobs: list, cfg: dict, state: dict,
             logger: logging.Logger, critic) -> dict:
    logger.info("=" * 55)
    logger.info("BLOC 3D -- MODELISATION")
    logger.info("=" * 55)

    if not AGENT_3D_OK:
        logger.warning("[3D] agent_3d_modeler.py indisponible -- bloc ignore")
        return {"skipped": True}

    mode      = cfg.get("mode_3d","render").split(" ")[0]
    prompt_3d = cfg.get("prompt_3d","")
    meshy_key = cfg.get("meshy_api_key","")
    scale_raw = [cfg.get("stl_w"), cfg.get("stl_d"), cfg.get("stl_h")]
    scale_mm  = None
    try:
        if all(scale_raw):
            scale_mm = tuple(float(v) for v in scale_raw)
    except Exception:
        pass

    agent = Agent3DModeler(logger=logger, meshy_api_key=meshy_key)
    results_3d = []

    if prompt_3d:
        r = agent.run_3d_pipeline(prompt=prompt_3d, mode=mode, scale_mm=scale_mm, logger=logger)
        results_3d.append(r)
    elif jobs:
        for shot in [j for j in jobs if j.get("_shot_meta",{}).get("3d_needed")][:3]:
            p = shot.get("positive","")
            if p:
                results_3d.append(agent.run_3d_pipeline(prompt=p, mode=mode,
                                                         scale_mm=scale_mm, logger=logger))

    state["data"]["3d_results"] = results_3d
    state["completed"].append("3d")
    save_state(state)
    ok = sum(1 for r in results_3d if r.get("mesh") or r.get("stl"))
    logger.info(f"[3D] OK {ok}/{len(results_3d)} modele(s)")
    return {"results": results_3d, "success": ok}


# ── PIPELINE PRINCIPAL ────────────────────────────────────────────────
def run_pipeline(config: dict = None, from_block: str = None,
                 run_id: str = None) -> dict:
    init()
    run_id = run_id or f"maestro_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    logger = get_logger(run_id)

    cfg = config or {}
    cfg.setdefault("media_type", "anime")
    cfg.setdefault("duration",   "short")
    cfg.setdefault("strength",   1.0)
    cfg.setdefault("width",      1024)
    cfg.setdefault("height",     1536)

    if AUDIT_OK:
        log_run_start(
            run_id,
            universe=cfg.get("universe", ""),
            media_type=cfg.get("media_type", "anime"),
            logger=logger
        )

    # FIX : state initialise AVANT le bloc try/finally pour eviter NameError dans finally
    state = load_state()
    if state.get("run_id") != run_id:
        state = {"run_id": run_id, "current_block": from_block or "sourcing",
                 "completed": [], "data": {}}

    # Director
    _director = None
    if DIRECTOR_OK and get_director:
        try:
            _director = get_director(cfg.get("universe","Ov3rLoRd"))
            intent    = _director.set_intent(
                media_type = cfg.get("media_type","anime"),
                universe   = cfg.get("universe",""),
                episode    = cfg.get("episode", 1),
            )
            logger.info(
                f"[DIRECTOR] Intent: mode={intent.mode} | "
                f"seuil={intent.quality_threshold} | "
                f"arc={intent.emotion_arc}"
            )
        except Exception as e:
            logger.warning(f"[DIRECTOR] Initialisation echouee : {e}")
            _director = None

    # Agents de controle
    critic   = CriticAgent(run_id, logger, use_llm=True)   if CRITIC_OK   else None
    watchdog = Watchdog(run_id, logger, check_interval=15)  if WATCHDOG_OK else None
    obs      = create_obs_agent(logger=logger)              if OBS_OK      else None
    vram     = VRAMManager(logger)                          if VRAM_OK     else None
    cp_mgr   = get_checkpoint_manager(cfg, logger)         if CP_OK       else None

    if watchdog:
        watchdog.start()
    if obs:
        if obs.connect():
            logger.info("[OBS] Connecte -- enregistrement actif")
    if cp_mgr:
        latest = cp_mgr.load_latest()
        if latest and latest.state.value in ("interrupted","failed"):
            analysis = cp_mgr.analyze_resume(latest)
            logger.info(f"[CHECKPOINT] Reprise : {analysis['message']}")
            for block, data in analysis.get("data", {}).items():
                state["data"][block] = data
            state["completed"] = analysis.get("skip", [])
        cp_mgr.new_checkpoint(cfg, run_id=run_id)

    # Initialiser les fiches personnages presets si première fois
    if CHARS_OK:
        try:
            from pathlib import Path as _Path
            if not (_Path("workspace/narrative/characters/index.json")).exists():
                n_chars = init_preset_characters()
                logger.info(f"[CHARS] {n_chars} fiches presets initialisées")
        except Exception as _e:
            logger.debug(f"[CHARS] Init presets : {_e}")

    # Auto-detect GPU et optimiser les paramètres
    if GPU_OPT_OK:
        try:
            gpu_key = detect_gpu()
            optimize_for_gpu(gpu_key, logger=logger)
            logger.info(f"[GPU] Optimisation auto : {gpu_key}")
        except Exception as e:
            logger.warning(f"[GPU] Auto-optimisation échouée : {e}")

    run_start_time = time.time()

    start_idx = 0
    if from_block and from_block in BLOCKS:
        start_idx = BLOCKS.index(from_block)
    elif state["completed"]:
        last = state["completed"][-1]
        if last in BLOCKS:
            start_idx = BLOCKS.index(last) + 1

    logger.info("=" * 60)
    logger.info("    Ov3rLoRd Pipeline V1.70")
    logger.info(f"  PIPELINE DEMARRE -- run_id={run_id}")
    logger.info(f"  Critique : {'OK' if critic   else 'INACTIF'}")
    logger.info(f"  Watchdog : {'OK' if watchdog else 'INACTIF'}")
    logger.info(f"  Director : {'OK' if _director else 'INACTIF'}")
    logger.info(f"  Bus      : {'OK' if BUS_OK   else 'INACTIF'}")
    logger.info(f"  Blocs    : {' -> '.join(BLOCKS[start_idx:])}")
    logger.info("=" * 60)
    notify(f"Pipeline demarre run={run_id}", logger)

    trend_report = state["data"].get("trend_report", {})
    script       = state["data"].get("script",       {})
    shotlist     = state["data"].get("shotlist",      {})
    jobs         = state["data"].get("jobs",          [])
    active       = BLOCKS[start_idx:]

    try:
        if "sourcing"   in active:
            trend_report = block_sourcing(cfg, state, logger, critic, watchdog, cp_mgr)

        if "scenario"   in active:
            if not trend_report:
                logger.error("Pas de TrendReport -- arret")
                return state
            # Injecter contexte narratif pour continuité inter-épisodes
            if NARRATIVE_OK:
                try:
                    mem = get_narrative_memory()
                    ctx = mem.get_continuation_context(cfg.get("universe",""))
                    if ctx:
                        cfg["narrative_context"] = ctx
                        logger.info("[NARRATIVE] Contexte inter-épisodes injecté")
                except Exception:
                    pass
            script = block_scenario(trend_report, cfg, state, logger, critic, watchdog, cp_mgr)
            if "error" in script:
                logger.error(f"Scenario echoue : {script['error']} -- arret")
                return state

        if "storyboard" in active:
            if not script:
                logger.error("Pas de script -- arret")
                return state
            shotlist, jobs = block_storyboard(script, cfg, state, logger, critic, watchdog, cp_mgr)

        # Détecter et injecter les personnages du script
        if CHARS_OK and script and jobs:
            try:
                detected_chars = detect_characters_in_script(script)
                if detected_chars:
                    main_char = detected_chars[0]
                    logger.info(f"[CHARS] Personnage détecté : {main_char}")
                    jobs = inject_character_into_jobs(jobs, main_char, logger=logger)
                else:
                    logger.debug("[CHARS] Aucun personnage preset détecté")
            except Exception as _e:
                logger.warning(f"[CHARS] Injection échouée : {_e}")

        # Créer ancre de style pour cohérence inter-frames
        if STYLE_OK and jobs:
            try:
                create_anchor(run_id, logger=logger)
                jobs = apply_continuity(jobs, run_id=run_id, logger=logger)
                logger.info(f"[STYLE] Continuité appliquée à {len(jobs)} jobs")
            except Exception as e:
                logger.warning(f"[STYLE] Continuité échouée : {e}")

        # Mémoriser le script pour continuité narrative
        if NARRATIVE_OK and script:
            try:
                mem = get_narrative_memory()
                mem.extract_from_script(
                    script, run_id=run_id,
                    universe=cfg.get("universe",""),
                    logger=logger
                )
                ctx = mem.get_continuation_context(cfg.get("universe",""))
                if ctx:
                    state["data"]["narrative_context"] = ctx
                    if BUS_OK and _bus:
                        _bus.write("narrative.context", ctx, agent_id="narrative")
            except Exception as e:
                logger.warning(f"[NARRATIVE] Mémoire échouée : {e}")

        # Run 0 : bible visuelle (une fois par projet, skip si deja presente)
        if cfg.get("run_bible_visuelle", False) or "bible_visuelle" in active:
            block_bible_visuelle(cfg, state, logger, cp_mgr)

        if "production" in active:
            block_production(jobs, cfg, state, logger, critic, watchdog, cp_mgr)

        if "postprod"   in active:
            block_postprod(shotlist, cfg, state, logger, critic, watchdog, cp_mgr)

        if "3d" in active or cfg.get("mode_3d") not in (None,"","none"):
            block_3d(jobs, cfg, state, logger, critic)

    except StopIteration as e:
        logger.error(f"[MAESTRO] Pipeline arrete par le Critique : {e}")
        notify(f"Pipeline stoppe : {e}", logger)
        return state
    except KeyboardInterrupt:
        logger.warning("[MAESTRO] Interruption clavier -- etat sauvegarde")
        notify("Pipeline interrompu", logger)
        return state
    except Exception as e:
        logger.error(f"[MAESTRO] Erreur critique : {e}", exc_info=True)
        notify(f"Erreur : {e}", logger)
        return state
    finally:
        run_duration = time.time() - run_start_time

        if _director:
            try:
                dir_summary = _director.end_session()
                logger.info(
                    f"[DIRECTOR] Session : {dir_summary.get('blocs_directed',[])} | "
                    f"mode={dir_summary.get('mode','')}"
                )
            except Exception:
                pass

        # Publication transmedia si demandé
        if PUBLISHER_OK and cfg.get("publish_after_run"):
            try:
                platforms = cfg.get("publish_platforms", ["youtube"])
                logger.info(f"[PUBLISH] Publication vers {platforms}")
                run_publisher(platforms=platforms, logger=logger)
            except Exception as _e:
                logger.warning(f"[PUBLISH] Échec : {_e}")

        # Rapport de session automatique
        if REPORTER_OK:
            try:
                archive_dir = None
                if BUS_OK and _bus:
                    try:
                        archive_dir = _bus.read("supervisor.archive_dir")
                    except Exception:
                        pass
                generate_report(
                    run_id=run_id, state=state,
                    archive_dir=archive_dir, logger=logger
                )
            except Exception as e:
                logger.warning(f"[REPORTER] Rapport echoue : {e}")

        if watchdog:
            watchdog.stop()
            try:
                wd_report = watchdog.report()
                logger.info(
                    f"[WATCHDOG] Bilan : {wd_report['frames_analyzed']} frames | "
                    f"echecs={wd_report['frames_failed']} | "
                    f"ComfyUI uptime={wd_report['comfy_uptime_s']}s"
                )
            except Exception as e:
                logger.warning(f"[WATCHDOG] Rapport indisponible : {e}")

        if obs:
            try:
                if obs.is_connected():
                    obs.disconnect()
            except Exception:
                pass

        if cp_mgr:
            if state.get("completed") and len(state["completed"]) >= 5:
                cp_mgr.mark_completed()
            else:
                cp_mgr.save_emergency()

        if critic:
            try:
                health = critic.health_summary()
                logger.info(
                    f"[CRITIQUE] Bilan : {health['total_checks']} verifications | "
                    f"score moyen={health['avg_score']} | "
                    f"sante={health['pipeline_health']}"
                )
            except Exception:
                pass

        if CONSCIENCE_OK and _conscience:
            try:
                completed_blocs = state.get("completed", [])
                critic_health   = {}
                if critic:
                    try: critic_health = critic.health_summary()
                    except Exception: pass
                _conscience.record_run({
                    "run_id":          run_id,
                    "pipeline_health": critic_health.get("pipeline_health","UNKNOWN"),
                    "blocs_ok":        len(completed_blocs),
                    "score_moyen":     critic_health.get("avg_score", 0),
                    "critic_checks":   critic_health.get("total_checks", 0),
                    "duration_s":      round(run_duration, 1),
                    "errors":          [],
                    "media_type":      cfg.get("media_type","anime"),
                })
                _conscience.analyze_and_adapt()
            except Exception as e:
                logger.warning(f"[CONSCIENCE] Enregistrement run echoue : {e}")

    clear_state()
    if AUDIT_OK:
        _completed = state.get("completed", [])
        log_run_end(
            run_id,
            total_frames=len(_completed),
            frames_ok=len(_completed),
            pipeline_health="OK",
            logger=logger
        )
    logger.info("=" * 60)
    logger.info(f"PIPELINE TERMINE -- run_id={run_id} | duree={run_duration:.0f}s")
    logger.info("=" * 60)
    notify(f"Pipeline termine ! run={run_id}", logger)
    return state


# ── CLI ───────────────────────────────────────────────────────────────
if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Maestro V1.60 -- Ov3rLoRd Pipeline")
    parser.add_argument("--config",     type=str, default=None)
    parser.add_argument("--from-block", type=str, default=None, choices=BLOCKS)
    parser.add_argument("--media-type", type=str, default="anime", choices=MEDIA_TYPES)
    parser.add_argument("--universe",   type=str, default="")
    parser.add_argument("--episode",    type=int, default=1)
    parser.add_argument("--lora",              type=str,  default="")
    parser.add_argument("--use-prompt-library", action="store_true",
                        help="Utiliser prompts Booru locaux (data/prompts/)")
    parser.add_argument("--auto-source",        action="store_true",
                        help="Mode sourcing autonome : collecte tendances puis génère")
    parser.add_argument("--no-prompt-engineer", action="store_true",
                        help="Désactiver l'upsampling Booru des prompts")
    parser.add_argument("--no-quality-gate",    action="store_true",
                        help="Désactiver la validation workflow avant production")
    parser.add_argument("--batch",              type=int, default=1,
                        help="Nombre de runs séquentiels à lancer")
    parser.add_argument("--report",             action="store_true", default=True,
                        help="Générer un rapport de session en fin de run")
    parser.add_argument("--publish",            action="store_true",
                        help="Publier transmedia après chaque run")
    parser.add_argument("--publish-platforms",  nargs="+",
                        default=["youtube"],
                        help="Plateformes de publication")
    parser.add_argument("--plan-series",        type=str, default=None,
                        help="Planifier une série N épisodes avant les runs")
    parser.add_argument("--series-episodes",    type=int, default=12)
    parser.add_argument("--run-id",      type=str, default=None)
    parser.add_argument("--bible",       action="store_true",
                        help="Executer le Run 0 : generation fiches personnages + Style DNA")
    args = parser.parse_args()

    cfg = {}
    if args.config and Path(args.config).exists():
        with open(args.config, encoding="utf-8") as f:
            cfg = json.load(f)
        if isinstance(cfg, list):
            cfg = {"jobs": cfg, "media_type": "anime"}

    cfg["media_type"] = args.media_type
    cfg["episode"]    = args.episode
    if args.universe: cfg["universe"] = args.universe
    if args.lora:     cfg["lora"]     = args.lora
    if getattr(args, "bible", False):
        cfg["run_bible_visuelle"] = True
    cfg.setdefault("duration", "short")
    cfg.setdefault("strength", 1.0)
    cfg.setdefault("width",    1024)
    cfg.setdefault("height",   1536)

    # Planifier une série si demandé
    plan_series = getattr(args, "plan_series", None)
    if plan_series and PLANNER_OK:
        n_eps = getattr(args, "series_episodes", 12)
        logging.getLogger("maestro").info(
            f"[PLANNER] Planification série : {plan_series} — {n_eps} épisodes")
        series_plan = run_planner(
            series_title=plan_series,
            n_episodes=n_eps,
            universe_base=cfg.get("universe", "anime"),
            export_for_dream=True,
        )
        uni_file = series_plan.get("_universes_file")
        if uni_file:
            logging.getLogger("maestro").info(
                f"[PLANNER] Univers → {uni_file}")
            logging.getLogger("maestro").info(
                f"[PLANNER] Dream mode : python agents/dream_mode.py "
                f"--universes-file {uni_file}")

    n_batch = getattr(args, "batch", 1)
    if n_batch > 1:
        logger_cli = logging.getLogger("maestro.batch")
        logger_cli.info(f"[BATCH] Mode batch : {n_batch} runs séquentiels")
        for i in range(n_batch):
            logger_cli.info(f"[BATCH] ── Run {i+1}/{n_batch} ──")
            from datetime import datetime as _dt
            batch_run_id = f"batch_{_dt.now().strftime('%Y%m%d_%H%M%S')}_{i+1:02d}"
            run_pipeline(config=cfg.copy(), from_block=args.from_block,
                         run_id=batch_run_id)
    else:
        run_pipeline(config=cfg, from_block=args.from_block, run_id=args.run_id)
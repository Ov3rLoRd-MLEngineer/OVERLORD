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
audit_logger.py V1.0 -- Tracabilite SQLite par Frame
Studio Ov3rLoRd
Enregistre chaque frame generee avec : run_id, shot_id, prompt_intent_id,
seed, model_hash, score_clip, score_conformite, artefacts detectes.
Permet le debug "pourquoi ca a plante a 3h du matin" en 1 requete SQL.
"""

import sys
import json
import hashlib
import logging
import sqlite3
from pathlib import Path
from datetime import datetime
from typing import Optional

_BASE_DIR = Path(__file__).resolve().parent.parent
if str(_BASE_DIR) not in sys.path:
    sys.path.insert(0, str(_BASE_DIR))

AUDIT_DIR = Path("workspace/audit")
AUDIT_DB  = AUDIT_DIR / "overlord_audit.db"

# ── Schema SQL ────────────────────────────────────────────────────────
_SCHEMA = """
CREATE TABLE IF NOT EXISTS frames (
    id                INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id            TEXT    NOT NULL,
    shot_id           TEXT    NOT NULL,
    frame_index       INTEGER DEFAULT 0,
    timestamp         TEXT    NOT NULL,
    prompt_intent_id  TEXT,
    seed              INTEGER,
    model_hash        TEXT,
    checkpoint        TEXT,
    lora              TEXT,
    positive_prompt   TEXT,
    negative_prompt   TEXT,
    shot_type         TEXT,
    lighting          TEXT,
    acting_intent     TEXT,
    camera_movement   TEXT,
    duration_s        REAL,
    width             INTEGER,
    height            INTEGER,
    steps             INTEGER,
    cfg               REAL,
    sampler           TEXT,
    score_clip        REAL    DEFAULT -1.0,
    score_conformite  REAL    DEFAULT -1.0,
    artefacts         TEXT    DEFAULT '[]',
    verdict           TEXT    DEFAULT 'PENDING',
    image_path        TEXT,
    notes             TEXT
);

CREATE TABLE IF NOT EXISTS runs (
    run_id            TEXT    PRIMARY KEY,
    started_at        TEXT    NOT NULL,
    finished_at       TEXT,
    universe          TEXT,
    media_type        TEXT,
    total_frames      INTEGER DEFAULT 0,
    frames_ok         INTEGER DEFAULT 0,
    frames_failed     INTEGER DEFAULT 0,
    avg_clip_score    REAL    DEFAULT -1.0,
    pipeline_health   TEXT    DEFAULT 'UNKNOWN',
    notes             TEXT
);

CREATE TABLE IF NOT EXISTS decisions (
    id                INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id            TEXT    NOT NULL,
    shot_id           TEXT    NOT NULL,
    timestamp         TEXT    NOT NULL,
    agent_id          TEXT,
    decision_type     TEXT,
    reason            TEXT,
    input_data        TEXT,
    output_data       TEXT
);

CREATE INDEX IF NOT EXISTS idx_frames_run     ON frames (run_id);
CREATE INDEX IF NOT EXISTS idx_frames_shot    ON frames (shot_id);
CREATE INDEX IF NOT EXISTS idx_frames_verdict ON frames (verdict);
CREATE INDEX IF NOT EXISTS idx_decisions_run  ON decisions (run_id);
"""


# ── Connexion ─────────────────────────────────────────────────────────

def _get_conn() -> sqlite3.Connection:
    """Connexion SQLite WAL -- thread-safe."""
    AUDIT_DIR.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(AUDIT_DB), check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")
    return conn


def init_db(logger: Optional[logging.Logger] = None) -> bool:
    """Initialise la DB et cree les tables si absentes."""
    _log = logger or logging.getLogger("audit_logger")
    try:
        conn = _get_conn()
        conn.executescript(_SCHEMA)
        conn.commit()
        conn.close()
        _log.info("[AUDIT] DB initialisee : %s", AUDIT_DB)
        return True
    except Exception as e:
        _log.error("[AUDIT] Erreur init DB : %s", e)
        return False


# ── API d'ecriture ────────────────────────────────────────────────────

def log_run_start(
    run_id:     str,
    universe:   str = "",
    media_type: str = "anime",
    logger:     Optional[logging.Logger] = None
) -> bool:
    """Enregistre le debut d'un run."""
    _log = logger or logging.getLogger("audit_logger")
    try:
        conn = _get_conn()
        conn.execute(
            "INSERT OR REPLACE INTO runs (run_id, started_at, universe, media_type) "
            "VALUES (?,?,?,?)",
            (run_id, datetime.now().isoformat(), universe, media_type)
        )
        conn.commit()
        conn.close()
        return True
    except Exception as e:
        _log.warning("[AUDIT] log_run_start echec : %s", e)
        return False


def log_run_end(
    run_id:          str,
    total_frames:    int   = 0,
    frames_ok:       int   = 0,
    frames_failed:   int   = 0,
    avg_clip_score:  float = -1.0,
    pipeline_health: str   = "UNKNOWN",
    logger:          Optional[logging.Logger] = None
) -> bool:
    """Enregistre la fin d'un run avec bilan."""
    _log = logger or logging.getLogger("audit_logger")
    try:
        conn = _get_conn()
        conn.execute(
            "UPDATE runs SET finished_at=?, total_frames=?, frames_ok=?, "
            "frames_failed=?, avg_clip_score=?, pipeline_health=? WHERE run_id=?",
            (datetime.now().isoformat(), total_frames, frames_ok,
             frames_failed, avg_clip_score, pipeline_health, run_id)
        )
        conn.commit()
        conn.close()
        return True
    except Exception as e:
        _log.warning("[AUDIT] log_run_end echec : %s", e)
        return False


def log_frame(
    run_id:           str,
    shot_id:          str,
    frame_index:      int   = 0,
    prompt_intent_id: Optional[str]  = None,
    seed:             Optional[int]  = None,
    checkpoint:       str   = "fabricatedXL_v70.safetensors",
    lora:             str   = "",
    positive_prompt:  str   = "",
    negative_prompt:  str   = "",
    intent:           Optional[dict] = None,
    width:            int   = 1344,
    height:           int   = 1984,
    steps:            int   = 35,
    cfg:              float = 7.0,
    sampler:          str   = "dpmpp_2m_sde",
    score_clip:       float = -1.0,
    score_conformite: float = -1.0,
    artefacts:        Optional[list] = None,
    verdict:          str   = "PENDING",
    image_path:       Optional[str]  = None,
    notes:            str   = "",
    logger:           Optional[logging.Logger] = None
) -> int:
    """
    Enregistre une frame generee dans l'audit.

    Args:
        intent : dict _intent du job (shot_type, lighting, acting_intent, duration_s...)

    Returns:
        int : ID de la ligne inseree, ou -1 si echec.
    """
    _log = logger or logging.getLogger("audit_logger")

    model_str  = (checkpoint or "") + "|" + (lora or "")
    model_hash = hashlib.md5(model_str.encode()).hexdigest()[:12]

    if not prompt_intent_id:
        prompt_intent_id = hashlib.md5(
            (positive_prompt or "")[:120].encode()
        ).hexdigest()[:8]

    _intent       = intent or {}
    shot_type     = _intent.get("shot_type",      "")
    lighting      = _intent.get("lighting",       "")
    acting_intent = _intent.get("acting_intent",  "")
    camera_mvt    = _intent.get("camera_movement","")
    duration_s    = _intent.get("duration_s",     -1.0)

    try:
        conn = _get_conn()
        cursor = conn.execute(
            """INSERT INTO frames (
                run_id, shot_id, frame_index, timestamp,
                prompt_intent_id, seed, model_hash, checkpoint, lora,
                positive_prompt, negative_prompt,
                shot_type, lighting, acting_intent, camera_movement, duration_s,
                width, height, steps, cfg, sampler,
                score_clip, score_conformite, artefacts, verdict, image_path, notes
               ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (
                run_id, shot_id, frame_index, datetime.now().isoformat(),
                prompt_intent_id, seed, model_hash, checkpoint, lora,
                positive_prompt, negative_prompt,
                shot_type, lighting, acting_intent, camera_mvt, duration_s,
                width, height, steps, cfg, sampler,
                score_clip, score_conformite,
                json.dumps(artefacts or []), verdict, image_path, notes
            )
        )
        row_id = cursor.lastrowid
        conn.commit()
        conn.close()
        _log.debug("[AUDIT] Frame logged : run=%s shot=%s id=%d verdict=%s",
                   run_id, shot_id, row_id, verdict)
        return row_id
    except Exception as e:
        _log.warning("[AUDIT] log_frame echec : %s", e)
        return -1


def log_decision(
    run_id:        str,
    shot_id:       str,
    agent_id:      str,
    decision_type: str,
    reason:        str  = "",
    input_data:    Optional[dict] = None,
    output_data:   Optional[dict] = None,
    logger:        Optional[logging.Logger] = None
) -> bool:
    """
    Enregistre une decision d'agent (rejet, inpaint, correction...).
    Permet de retracer POURQUOI une frame a ete modifiee ou rejetee.
    """
    _log = logger or logging.getLogger("audit_logger")
    try:
        conn = _get_conn()
        conn.execute(
            "INSERT INTO decisions "
            "(run_id, shot_id, timestamp, agent_id, decision_type, reason, input_data, output_data) "
            "VALUES (?,?,?,?,?,?,?,?)",
            (run_id, shot_id, datetime.now().isoformat(), agent_id, decision_type,
             reason, json.dumps(input_data or {}), json.dumps(output_data or {}))
        )
        conn.commit()
        conn.close()
        return True
    except Exception as e:
        _log.warning("[AUDIT] log_decision echec : %s", e)
        return False


def update_frame_scores(
    row_id:           int,
    score_clip:       float = -1.0,
    score_conformite: float = -1.0,
    artefacts:        Optional[list] = None,
    verdict:          str  = "PASS",
    logger:           Optional[logging.Logger] = None
) -> bool:
    """Met a jour les scores apres validation par visual_validator."""
    _log = logger or logging.getLogger("audit_logger")
    try:
        conn = _get_conn()
        conn.execute(
            "UPDATE frames SET score_clip=?, score_conformite=?, artefacts=?, verdict=? WHERE id=?",
            (score_clip, score_conformite, json.dumps(artefacts or []), verdict, row_id)
        )
        conn.commit()
        conn.close()
        return True
    except Exception as e:
        _log.warning("[AUDIT] update_frame_scores echec : %s", e)
        return False


# ── API de lecture / debug ────────────────────────────────────────────

def get_failed_frames(run_id: str,
                      logger: Optional[logging.Logger] = None) -> list:
    """Toutes les frames en echec ou rejet pour un run."""
    _log = logger or logging.getLogger("audit_logger")
    try:
        conn = _get_conn()
        rows = conn.execute(
            "SELECT * FROM frames WHERE run_id=? AND verdict IN ('REJECT','FAIL','PENDING') "
            "ORDER BY frame_index",
            (run_id,)
        ).fetchall()
        conn.close()
        return [dict(r) for r in rows]
    except Exception as e:
        _log.warning("[AUDIT] get_failed_frames echec : %s", e)
        return []


def get_run_summary(run_id: str,
                    logger: Optional[logging.Logger] = None) -> dict:
    """Bilan complet d'un run depuis l'audit."""
    _log = logger or logging.getLogger("audit_logger")
    try:
        conn = _get_conn()
        run = conn.execute("SELECT * FROM runs WHERE run_id=?", (run_id,)).fetchone()
        frames = conn.execute(
            "SELECT verdict, COUNT(*) as cnt, AVG(score_clip) as avg_clip, "
            "AVG(score_conformite) as avg_conf FROM frames WHERE run_id=? GROUP BY verdict",
            (run_id,)
        ).fetchall()
        dec = conn.execute(
            "SELECT COUNT(*) as cnt FROM decisions WHERE run_id=?", (run_id,)
        ).fetchone()
        conn.close()
        summary = dict(run) if run else {"run_id": run_id}
        summary["frame_stats"]    = [dict(f) for f in frames]
        summary["decision_count"] = dec["cnt"] if dec else 0
        return summary
    except Exception as e:
        _log.warning("[AUDIT] get_run_summary echec : %s", e)
        return {"run_id": run_id, "error": str(e)}


def get_artifact_report(run_id: str,
                        logger: Optional[logging.Logger] = None) -> list:
    """Frames avec artefacts detectes pour un run."""
    _log = logger or logging.getLogger("audit_logger")
    try:
        conn = _get_conn()
        rows = conn.execute(
            "SELECT shot_id, frame_index, artefacts, image_path, score_clip, prompt_intent_id "
            "FROM frames WHERE run_id=? AND artefacts != '[]' ORDER BY frame_index",
            (run_id,)
        ).fetchall()
        conn.close()
        result = []
        for r in rows:
            d = dict(r)
            try:
                d["artefacts"] = json.loads(d["artefacts"])
            except Exception:
                pass
            result.append(d)
        return result
    except Exception as e:
        _log.warning("[AUDIT] get_artifact_report echec : %s", e)
        return []


def print_run_report(run_id: str, logger: Optional[logging.Logger] = None):
    """Rapport lisible en console pour un run."""
    summary = get_run_summary(run_id, logger=logger)
    print("\n" + "=" * 60)
    print("  AUDIT REPORT -- run_id=" + run_id)
    print("=" * 60)
    print("  Started  :", summary.get("started_at", "?"))
    print("  Finished :", summary.get("finished_at", "?"))
    print("  Universe :", summary.get("universe", "?"))
    print("  Health   :", summary.get("pipeline_health", "?"))
    print("  Decisions:", summary.get("decision_count", 0))
    print()
    for stat in summary.get("frame_stats", []):
        print("  [%-8s] %3d frames | CLIP=%.3f | CONF=%.3f" % (
            stat["verdict"], stat["cnt"],
            stat["avg_clip"] or -1.0, stat["avg_conf"] or -1.0
        ))
    print("=" * 60)
    failed = get_failed_frames(run_id, logger=logger)
    if failed:
        print("\n  FRAMES EN ECHEC (%d) :" % len(failed))
        for f in failed:
            print("    shot=%s | frame=%d | verdict=%s | clip=%.3f" % (
                f["shot_id"], f["frame_index"], f["verdict"], f["score_clip"] or -1.0
            ))
            print("    intent_id=%s | path=%s" % (
                f["prompt_intent_id"], f["image_path"]
            ))


# ── CLI standalone ────────────────────────────────────────────────────
if __name__ == "__main__":
    import argparse

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)-8s] %(message)s"
    )
    log_cli = logging.getLogger("audit_logger")

    parser = argparse.ArgumentParser(description="Audit Logger V1.0 -- Ov3rLoRd")
    parser.add_argument("--init",      action="store_true",
                        help="Initialiser la base de donnees")
    parser.add_argument("--report",    type=str, default=None, metavar="RUN_ID")
    parser.add_argument("--failed",    type=str, default=None, metavar="RUN_ID")
    parser.add_argument("--artifacts", type=str, default=None, metavar="RUN_ID")
    args = parser.parse_args()

    if args.init:
        ok = init_db(logger=log_cli)
        print("[AUDIT] DB init :", "OK" if ok else "ECHEC")

    elif args.report:
        print_run_report(args.report, logger=log_cli)

    elif args.failed:
        frames = get_failed_frames(args.failed, logger=log_cli)
        print(json.dumps(frames, indent=2, ensure_ascii=False, default=str))

    elif args.artifacts:
        report = get_artifact_report(args.artifacts, logger=log_cli)
        print(json.dumps(report, indent=2, ensure_ascii=False, default=str))

    else:
        # Test autonome : init + log une frame de test
        init_db(logger=log_cli)
        test_run = "test_" + datetime.now().strftime("%H%M%S")
        log_run_start(test_run, universe="evangelion", logger=log_cli)
        row_id = log_frame(
            run_id=test_run,
            shot_id="S01",
            positive_prompt="asuka langley, red plugsuit, anime style",
            intent={
                "shot_type": "close_up", "lighting": "dramatic",
                "acting_intent": "defiance", "camera_movement": "static",
                "duration_s": 1.6
            },
            seed=42,
            verdict="PASS",
            score_clip=0.87,
            score_conformite=0.91,
            logger=log_cli
        )
        log_run_end(test_run, total_frames=1, frames_ok=1, logger=log_cli)
        print("[TEST] Frame loggee : row_id=%d" % row_id)
        print("[TEST] DB :", AUDIT_DB)
        print_run_report(test_run, logger=log_cli)

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
agents/api_server.py — Pont Flask HTML<->Python Ov3rLoRd V1.49
Expose le pipeline via une API REST locale sur http://localhost:5757
Routes :
  GET  /status              -> etat du pipeline
  POST /run                 -> lance un run maestro
  GET  /run/<run_id>        -> statut d'un run en cours
  GET  /runs                -> historique des runs
  POST /stop/<run_id>       -> stoppe un run
  GET  /context_bus         -> dump du context_bus
  GET  /logs                -> derniers logs
"""
import logging
import json
import uuid
import threading
import subprocess
import sys
from pathlib import Path
from datetime import datetime

log = logging.getLogger("api_server")

try:
    from flask import Flask, jsonify, request, abort
    FLASK_OK = True
except ImportError:
    FLASK_OK = False
    log.warning("[API] Flask non installé — pip install flask")

try:
    from agents.context_bus import get_bus
    BUS_OK = True
except ImportError:
    BUS_OK = False

# ── State ─────────────────────────────────────────────────────────────────────
_runs: dict[str, dict] = {}      # run_id -> {status, started_at, params, log_lines}
_runs_lock = threading.Lock()

# ── App Flask ─────────────────────────────────────────────────────────────────
if FLASK_OK:
    app = Flask("overlord_api")
    app.config["JSON_ENSURE_ASCII"] = False

    # ── /status ───────────────────────────────────────────────────────────────
    @app.route("/status")
    def status():
        with _runs_lock:
            active = [r for r in _runs.values() if r["status"] == "running"]
        return jsonify({
            "version":      "V1.49",
            "project":      "Ov3rLoRd",
            "active_runs":  len(active),
            "total_runs":   len(_runs),
            "flask":        True,
            "context_bus":  BUS_OK,
            "timestamp":    datetime.now().isoformat(),
        })

    # ── /run (POST) ───────────────────────────────────────────────────────────
    @app.route("/run", methods=["POST"])
    def start_run():
        data = request.get_json(silent=True) or {}
        media_type = data.get("media_type", "anime")
        universe   = data.get("universe",   "Dragon Ball")
        episode    = data.get("episode",    1)
        mode       = data.get("mode",       "balance")

        run_id = f"run_{uuid.uuid4().hex[:8]}"
        run_entry = {
            "run_id":     run_id,
            "status":     "running",
            "started_at": datetime.now().isoformat(),
            "ended_at":   None,
            "params":     {"media_type": media_type, "universe": universe,
                           "episode": episode, "mode": mode},
            "log_lines":  [],
            "returncode": None,
        }

        with _runs_lock:
            _runs[run_id] = run_entry

        # Lance maestro.py en sous-process non-bloquant
        def _worker():
            cmd = [
                sys.executable, "maestro.py",
                "--media-type", media_type,
                "--universe",   universe,
                "--episode",    str(episode),
            ]
            try:
                env = {"PYTHONIOENCODING": "utf-8", "PYTHONUTF8": "1"}
                import os; env.update(os.environ)
                proc = subprocess.Popen(
                    cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                    text=True, encoding="utf-8", errors="replace", env=env
                )
                for line in proc.stdout:
                    with _runs_lock:
                        _runs[run_id]["log_lines"].append(line.rstrip())
                proc.wait()
                with _runs_lock:
                    _runs[run_id]["status"]     = "done" if proc.returncode == 0 else "error"
                    _runs[run_id]["returncode"] = proc.returncode
                    _runs[run_id]["ended_at"]   = datetime.now().isoformat()
            except Exception as e:
                with _runs_lock:
                    _runs[run_id]["status"]   = "error"
                    _runs[run_id]["ended_at"] = datetime.now().isoformat()
                    _runs[run_id]["log_lines"].append(f"ERREUR WORKER : {e}")

        t = threading.Thread(target=_worker, daemon=True, name=f"run_{run_id}")
        t.start()

        log.info(f"[API] Run lancé : {run_id} | {universe} ep{episode}")
        return jsonify({"run_id": run_id, "status": "running"}), 202

    # ── /run/<run_id> (GET) ───────────────────────────────────────────────────
    @app.route("/run/<run_id>")
    def get_run(run_id):
        with _runs_lock:
            run = _runs.get(run_id)
        if not run:
            abort(404)
        tail = run["log_lines"][-50:]   # 50 dernières lignes
        return jsonify({**run, "log_lines": tail})

    # ── /runs (GET) ───────────────────────────────────────────────────────────
    @app.route("/runs")
    def list_runs():
        with _runs_lock:
            summary = [
                {"run_id": r["run_id"], "status": r["status"],
                 "started_at": r["started_at"], "params": r["params"]}
                for r in _runs.values()
            ]
        return jsonify(summary)

    # ── /stop/<run_id> (POST) ─────────────────────────────────────────────────
    @app.route("/stop/<run_id>", methods=["POST"])
    def stop_run(run_id):
        # Note : le sous-process est daemon, il s'arrête avec le serveur.
        # Un vrai kill nécessiterait de stocker le PID — V1.50.
        with _runs_lock:
            if run_id not in _runs:
                abort(404)
            _runs[run_id]["status"]   = "stopped"
            _runs[run_id]["ended_at"] = datetime.now().isoformat()
        log.info(f"[API] Run marqué stopped : {run_id}")
        return jsonify({"run_id": run_id, "status": "stopped"})

    # ── /context_bus (GET) ────────────────────────────────────────────────────
    @app.route("/context_bus")
    def dump_bus():
        if not BUS_OK:
            return jsonify({"error": "context_bus non disponible"}), 503
        try:
            bus = get_bus()
            return jsonify(bus.dump() if hasattr(bus, "dump") else {"status": "ok"})
        except Exception as e:
            return jsonify({"error": str(e)}), 500

    # ── /logs (GET) ───────────────────────────────────────────────────────────
    @app.route("/logs")
    def get_logs():
        log_path = Path("workspace/logs/overlord.log")
        if not log_path.exists():
            return jsonify({"lines": []})
        lines = log_path.read_text(encoding="utf-8", errors="replace").splitlines()
        return jsonify({"lines": lines[-100:]})   # 100 dernières lignes


def start_server(host: str = "127.0.0.1", port: int = 5757, debug: bool = False):
    if not FLASK_OK:
        log.error("[API] Flask manquant — pip install flask")
        return
    log.info(f"[API] Serveur Ov3rLoRd sur http://{host}:{port}")
    app.run(host=host, port=port, debug=debug, use_reloader=False)


if __name__ == "__main__":
    import overlord_utils_utf8  # noqa
    logging.basicConfig(level=logging.INFO,
                        format="%(asctime)s [%(levelname)-8s] %(message)s")
    start_server(debug=True)
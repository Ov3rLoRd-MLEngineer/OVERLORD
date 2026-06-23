"""
api_server.py — Serveur API Flask V1.70
Expose le context_bus en JSON temps réel pour le HUD web.
Gère aussi le pilotage distant (relancer le pipeline si crash).

Endpoints :
  GET  /api/status          → état global pipeline
  GET  /api/bus             → toutes les clés du bus
  GET  /api/bus/<key>       → une clé spécifique
  GET  /api/history         → historique des runs (session_reporter)
  GET  /api/gpu             → état GPU (VRAM, température)
  POST /api/run             → lancer un nouveau run
  POST /api/stop            → arrêter le run courant
  GET  /                    → sert live_monitor.html

Usage : python api_server.py [--port 5757] [--host 0.0.0.0]
Accès distant : http://IP_MACHINE:5757
"""

import argparse
import json
import logging
import os
import subprocess
import sys
import threading
import time
import io
from datetime import datetime
from pathlib import Path

if hasattr(sys.stdout, 'buffer'):
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

try:
    from flask import Flask, jsonify, request, send_from_directory
    FLASK_OK = True
except ImportError:
    FLASK_OK = False
    print("Flask non installé. Lancer : pip install flask")
    sys.exit(1)

try:
    from agents.context_bus import get_bus
    BUS_OK = True
except ImportError:
    BUS_OK = False

try:
    from agents.config_manager import get_config
    CFG_OK = True
except ImportError:
    CFG_OK = False

REPORTS_DIR = Path("workspace/reports")
UI_DIR      = Path("ui")  # dossier HTML
log         = logging.getLogger("api_server")

app = Flask(__name__, static_folder=str(UI_DIR))

# ── Processus pipeline courant ────────────────────────────────────────
_pipeline_proc: subprocess.Popen | None = None
_pipeline_lock = threading.Lock()
_pipeline_meta = {"run_id": None, "started_at": None, "universe": None}


def _get_gpu_info() -> dict:
    """Récupère les infos GPU via nvidia-smi."""
    try:
        result = subprocess.run(
            ["nvidia-smi", "--query-gpu=name,memory.used,memory.total,temperature.gpu,utilization.gpu",
             "--format=csv,noheader,nounits"],
            capture_output=True, text=True, timeout=5
        )
        if result.returncode == 0:
            parts = [p.strip() for p in result.stdout.strip().split(",")]
            if len(parts) >= 5:
                return {
                    "name":      parts[0],
                    "vram_used": int(parts[1]),
                    "vram_total": int(parts[2]),
                    "vram_pct":  round(int(parts[1]) / max(int(parts[2]), 1) * 100, 1),
                    "temp_c":    int(parts[3]),
                    "util_pct":  int(parts[4]),
                }
    except Exception:
        pass
    return {"name": "unknown", "vram_used": 0, "vram_total": 0,
            "vram_pct": 0, "temp_c": 0, "util_pct": 0}


def _get_bus_snapshot() -> dict:
    """Snapshot complet du context_bus."""
    if not BUS_OK:
        return {}
    try:
        bus  = get_bus()
        keys = [
            "director.mode", "director.emotion_arc", "director.quality_threshold",
            "scenario.title", "scenario.score", "scenario.scenes",
            "storyboard.shots_count",
            "supervisor.batch_done", "supervisor.final_success", "supervisor.final_failed",
            "supervisor.archive_dir", "supervisor.archived_images",
            "production.image_dir",
            "postprod.video", "postprod.image_count", "postprod.status",
            "prompt_engineer.jobs_enriched",
            "quality_gate.last_valid", "quality_gate.last_errors",
            "reviewer.last_score", "reviewer.last_pass",
            "style.base_seed", "style.emotion_arc", "style.drift_count",
            "narrative.characters_count", "narrative.episodes_count",
            "auto_sourcing.prompts_total", "auto_sourcing.last_run",
            "reporter.last_report_md",
        ]
        data = {}
        for key in keys:
            try:
                val = bus.read(key)
                if val is not None:
                    data[key] = val
            except Exception:
                pass
        return data
    except Exception:
        return {}


# ── Routes ────────────────────────────────────────────────────────────

@app.route("/")
def index():
    """Sert live_monitor.html."""
    if UI_DIR.exists() and (UI_DIR / "live_monitor.html").exists():
        return send_from_directory(str(UI_DIR), "live_monitor.html")
    # Fallback inline HTML
    return _inline_monitor()


@app.route("/api/status")
def api_status():
    bus  = _get_bus_snapshot()
    gpu  = _get_gpu_info()
    with _pipeline_lock:
        running = _pipeline_proc is not None and _pipeline_proc.poll() is None

    status = {
        "timestamp":    datetime.now().isoformat(),
        "pipeline_running": running,
        "pipeline_meta":    _pipeline_meta,
        "scenario_title":   bus.get("scenario.title", "—"),
        "last_score":       bus.get("reviewer.last_score", 0),
        "images_done":      bus.get("supervisor.final_success", 0),
        "images_failed":    bus.get("supervisor.final_failed", 0),
        "postprod_status":  bus.get("postprod.status", "—"),
        "gpu":              gpu,
        "prompts_library":  bus.get("auto_sourcing.prompts_total", 0),
    }
    return jsonify(status)


@app.route("/api/bus")
def api_bus():
    return jsonify(_get_bus_snapshot())


@app.route("/api/bus/<path:key>")
def api_bus_key(key):
    if not BUS_OK:
        return jsonify({"error": "bus unavailable"}), 503
    try:
        val = get_bus().read(key)
        return jsonify({"key": key, "value": val})
    except Exception as e:
        return jsonify({"key": key, "value": None, "error": str(e)})


@app.route("/api/gpu")
def api_gpu():
    return jsonify(_get_gpu_info())


@app.route("/api/history")
def api_history():
    history_file = REPORTS_DIR / "history.json"
    if history_file.exists():
        try:
            data = json.loads(history_file.read_text(encoding="utf-8"))
            return jsonify({"runs": data[-20:]})  # 20 derniers
        except Exception:
            pass
    return jsonify({"runs": []})


@app.route("/api/config")
def api_config():
    if not CFG_OK:
        return jsonify({"error": "config_manager unavailable"}), 503
    c = get_config()
    return jsonify({
        "comfyui": c.get_all("comfyui"),
        "llm":     c.get_all("llm"),
        "gpu":     c.get_all("gpu"),
    })


@app.route("/api/run", methods=["POST"])
def api_run():
    """Lancer un nouveau run pipeline."""
    global _pipeline_proc, _pipeline_meta

    with _pipeline_lock:
        if _pipeline_proc and _pipeline_proc.poll() is None:
            return jsonify({"error": "Pipeline déjà en cours"}), 409

    data     = request.get_json(silent=True) or {}
    universe = data.get("universe", "evangelion battle mecha girl")
    media    = data.get("media_type", "anime")
    batch    = data.get("batch", 1)
    use_lib  = data.get("use_prompt_library", False)

    cmd = [sys.executable, "maestro.py",
           "--media-type", media,
           "--universe",   universe,
           "--batch",      str(batch)]
    if use_lib:
        cmd.append("--use-prompt-library")

    log.info(f"[API] Lancement pipeline : {' '.join(cmd)}")

    with _pipeline_lock:
        _pipeline_proc = subprocess.Popen(
            cmd, cwd=str(Path.cwd()),
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            text=True, encoding="utf-8", errors="replace"
        )
        _pipeline_meta.update({
            "run_id":     f"api_{datetime.now().strftime('%Y%m%d_%H%M%S')}",
            "started_at": datetime.now().isoformat(),
            "universe":   universe,
            "command":    " ".join(cmd),
        })

    return jsonify({
        "status":  "started",
        "pid":     _pipeline_proc.pid,
        "command": " ".join(cmd),
    })


@app.route("/api/stop", methods=["POST"])
def api_stop():
    """Arrêter le run courant."""
    global _pipeline_proc
    with _pipeline_lock:
        if _pipeline_proc and _pipeline_proc.poll() is None:
            _pipeline_proc.terminate()
            log.info("[API] Pipeline terminé par l'API")
            return jsonify({"status": "stopped"})
    return jsonify({"status": "not_running"})


@app.route("/api/logs")
def api_logs():
    """Retourne les dernières lignes des logs."""
    n = int(request.args.get("n", 50))
    log_files = sorted(Path("workspace/logs").glob("*.log"), key=lambda p: p.stat().st_mtime, reverse=True)
    if not log_files:
        return jsonify({"lines": []})
    try:
        lines = log_files[0].read_text(encoding="utf-8", errors="replace").splitlines()
        return jsonify({"file": log_files[0].name, "lines": lines[-n:]})
    except Exception:
        return jsonify({"lines": []})


def _inline_monitor() -> str:
    """HUD HTML minimal inline si live_monitor.html absent."""
    return """<!DOCTYPE html>
<html lang="fr">
<head>
<meta charset="UTF-8">
<meta http-equiv="refresh" content="3">
<title>Ov3rLoRd HUD</title>
<style>
  * { margin:0; padding:0; box-sizing:border-box; }
  body { background:#0a0a0f; color:#c0c0d0; font-family:Consolas,monospace; padding:20px; }
  h1 { color:#7c3aed; font-size:1.4em; margin-bottom:16px; }
  .grid { display:grid; grid-template-columns:repeat(auto-fit,minmax(240px,1fr)); gap:12px; }
  .card { background:#12121a; border:1px solid #1e1e2e; border-radius:8px; padding:16px; }
  .card h2 { color:#7c3aed; font-size:.85em; margin-bottom:10px; text-transform:uppercase; }
  .metric { display:flex; justify-content:space-between; margin:6px 0; font-size:.85em; }
  .metric .val { color:#10b981; font-weight:bold; }
  .metric .val.warn { color:#f59e0b; }
  .metric .val.err  { color:#ef4444; }
  .btn { background:#7c3aed; color:#fff; border:none; padding:8px 16px;
         border-radius:4px; cursor:pointer; font-family:Consolas; margin:4px; }
  .btn:hover { background:#9d5cf0; }
  .btn.danger { background:#ef4444; }
  #log { background:#080810; padding:12px; border-radius:6px; font-size:.75em;
         height:200px; overflow-y:auto; border:1px solid #1e1e2e; margin-top:12px; }
  .log-line { color:#606070; margin:1px 0; }
  .log-line.INFO  { color:#c0c0d0; }
  .log-line.ERROR { color:#ef4444; }
  .log-line.WARN  { color:#f59e0b; }
</style>
</head>
<body>
<h1>◈ OV3RLORD HUD V1.70</h1>
<div class="grid" id="grid">Chargement...</div>
<div id="log"></div>
<div style="margin-top:12px">
  <input id="universe" placeholder="Universe..." value="evangelion battle mecha girl"
         style="background:#12121a;border:1px solid #1e1e2e;color:#c0c0d0;
                padding:8px;border-radius:4px;width:300px;font-family:Consolas">
  <button class="btn" onclick="startRun()">▶ Lancer</button>
  <button class="btn danger" onclick="stopRun()">■ Stop</button>
</div>
<script>
async function refresh() {
  try {
    const [status, gpu] = await Promise.all([
      fetch('/api/status').then(r=>r.json()),
      fetch('/api/gpu').then(r=>r.json())
    ]);
    const g = document.getElementById('grid');
    g.innerHTML = `
      <div class="card">
        <h2>Pipeline</h2>
        <div class="metric"><span>État</span>
          <span class="val ${status.pipeline_running?'':'warn'}">${status.pipeline_running?'EN COURS':'INACTIF'}</span></div>
        <div class="metric"><span>Scénario</span>
          <span class="val">${status.scenario_title||'—'}</span></div>
        <div class="metric"><span>Images OK</span>
          <span class="val">${status.images_done||0}</span></div>
        <div class="metric"><span>Score jury</span>
          <span class="val ${(status.last_score||0)>=80?'':'warn'}">${(status.last_score||0).toFixed(1)}/100</span></div>
        <div class="metric"><span>Post-prod</span>
          <span class="val">${status.postprod_status||'—'}</span></div>
      </div>
      <div class="card">
        <h2>GPU</h2>
        <div class="metric"><span>Modèle</span><span class="val">${gpu.name||'?'}</span></div>
        <div class="metric"><span>VRAM</span>
          <span class="val ${gpu.vram_pct>85?'warn':''}">${gpu.vram_used||0}/${gpu.vram_total||0} MB (${gpu.vram_pct||0}%)</span></div>
        <div class="metric"><span>Température</span>
          <span class="val ${(gpu.temp_c||0)>80?'err':''}">${gpu.temp_c||0}°C</span></div>
        <div class="metric"><span>Utilisation</span>
          <span class="val">${gpu.util_pct||0}%</span></div>
      </div>
      <div class="card">
        <h2>Bibliothèque</h2>
        <div class="metric"><span>Prompts locaux</span>
          <span class="val">${status.prompts_library||0}</span></div>
        <div class="metric"><span>Dernière MAJ</span>
          <span class="val" style="font-size:.75em">${new Date(status.timestamp).toLocaleTimeString()}</span></div>
      </div>
    `;
    const logs = await fetch('/api/logs?n=30').then(r=>r.json());
    const logDiv = document.getElementById('log');
    logDiv.innerHTML = (logs.lines||[]).map(l => {
      const cls = l.includes('[ERROR')  ? 'err'  :
                  l.includes('[WARNING') ? 'warn' :
                  l.includes('[INFO')   ? 'INFO' : '';
      return `<div class="log-line ${cls}">${l}</div>`;
    }).join('');
    logDiv.scrollTop = logDiv.scrollHeight;
  } catch(e) { console.error(e); }
}
async function startRun() {
  const u = document.getElementById('universe').value;
  await fetch('/api/run', {method:'POST', headers:{'Content-Type':'application/json'},
    body: JSON.stringify({universe: u, media_type: 'anime'})});
}
async function stopRun() {
  await fetch('/api/stop', {method:'POST'});
}
setInterval(refresh, 2000);
refresh();
</script>
</body></html>"""


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Ov3rLoRd API Server V1.70")
    parser.add_argument("--port", type=int, default=5757)
    parser.add_argument("--host", type=str, default="0.0.0.0")
    parser.add_argument("--debug", action="store_true")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO,
                        format="%(asctime)s [%(levelname)s] %(message)s")

    print(f"""
╔══════════════════════════════════════╗
║  Ov3rLoRd API Server V1.70          ║
║  http://localhost:{args.port}             ║
║  http://0.0.0.0:{args.port}  (réseau)    ║
╚══════════════════════════════════════╝
""")
    app.run(host=args.host, port=args.port, debug=args.debug, threaded=True)

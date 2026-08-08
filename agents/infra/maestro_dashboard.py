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
maestro_dashboard.py -- Ov3rLoRd Pipeline (tache 7)

Dashboard Flask dedie a l'orchestration parallele SVI (maestro.py
--parallel-svi, tache 5) -- distinct de api_server.py (:5757, HUD pipeline
creatif complet SOURCING->...->3D). Lit uniquement des sources reelles :

- GPU (5080 + 5060 Ti) : nvidia-smi, refresh 5s cote client
- Pipeline queue : workspace/pipeline_queue/{pending_postprod,completed}/*.json
- Logs : 50 dernieres lignes de workspace/logs/parallel_svi.log
- QC : derniers rapports agents/qc_validation/visual_qc_svi.py
  (workspace/logs/qc_reports/*.json) + miniatures (frames extraites,
  memes rapports)
- Controles : ecrit workspace/pipeline_queue/control.json, lu par
  maestro.py::run_parallel_svi_pipeline (pause/resume, skip clip,
  CFG/steps a chaud)

Aucune authentification (usage local uniquement, cf. consigne tache 7).

Usage :
  start cmd /k python agents/infra/maestro_dashboard.py
  -> http://localhost:5000
"""
import json
import subprocess
import sys
from pathlib import Path

from flask import Flask, jsonify, request, send_file

_REPO_ROOT = Path(__file__).resolve().parent.parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

QUEUE_DIR    = _REPO_ROOT / "workspace" / "pipeline_queue"
CONTROL_FILE = QUEUE_DIR / "control.json"
LOG_FILE     = _REPO_ROOT / "workspace" / "logs" / "parallel_svi.log"
QC_DIR       = _REPO_ROOT / "workspace" / "logs" / "qc_reports"

app = Flask(__name__)


def _read_control() -> dict:
    defaults = {"paused": False, "skip_clip": None, "cfg": None, "steps": None}
    if not CONTROL_FILE.exists():
        return defaults
    try:
        data = json.loads(CONTROL_FILE.read_text(encoding="utf-8"))
        defaults.update({k: data.get(k, v) for k, v in defaults.items()})
        return defaults
    except Exception:
        return defaults


def _write_control(patch: dict):
    QUEUE_DIR.mkdir(parents=True, exist_ok=True)
    current = _read_control()
    current.update(patch)
    CONTROL_FILE.write_text(json.dumps(current, indent=2), encoding="utf-8")
    return current


def _gpu_snapshot() -> list:
    try:
        result = subprocess.run(
            ["nvidia-smi",
             "--query-gpu=index,name,memory.used,memory.total,temperature.gpu,utilization.gpu",
             "--format=csv,noheader,nounits"],
            capture_output=True, text=True, timeout=5,
        )
        gpus = []
        if result.returncode == 0:
            for line in result.stdout.strip().splitlines():
                parts = [p.strip() for p in line.split(",")]
                if len(parts) >= 6:
                    used, total = int(parts[2]), int(parts[3])
                    gpus.append({
                        "index": int(parts[0]), "name": parts[1],
                        "vram_used_mb": used, "vram_total_mb": total,
                        "vram_pct": round(used / max(total, 1) * 100, 1),
                        "temp_c": int(parts[4]), "util_pct": int(parts[5]),
                    })
        return gpus
    except Exception as e:
        return [{"error": str(e)}]


def _queue_snapshot() -> dict:
    pending, completed = [], []
    pdir = QUEUE_DIR / "pending_postprod"
    cdir = QUEUE_DIR / "completed"
    if pdir.exists():
        for f in sorted(pdir.glob("clip_*.json")):
            done = (cdir / f.name).exists()
            if not done:
                try:
                    pending.append(json.loads(f.read_text(encoding="utf-8")))
                except Exception:
                    pass
    if cdir.exists():
        for f in sorted(cdir.glob("clip_*.json")):
            try:
                completed.append(json.loads(f.read_text(encoding="utf-8")))
            except Exception:
                pass
    return {"pending": pending, "completed": completed}


def _tail_log(n=50) -> list:
    if not LOG_FILE.exists():
        return []
    try:
        lines = LOG_FILE.read_text(encoding="utf-8", errors="replace").splitlines()
        return lines[-n:]
    except Exception:
        return []


def _qc_snapshot(n=5) -> list:
    if not QC_DIR.exists():
        return []
    reports = sorted(QC_DIR.glob("qc_svi_*.json"), key=lambda p: p.stat().st_mtime, reverse=True)[:n]
    out = []
    for r in reports:
        try:
            data = json.loads(r.read_text(encoding="utf-8"))
            frames_dir = QC_DIR / f"_frames_{Path(data['video']).stem}"
            thumbs = []
            for idx in data.get("frames_analyzed", []):
                fp = frames_dir / f"frame_{idx:05d}.png"
                if fp.exists():
                    thumbs.append({
                        "frame": idx,
                        "url": f"/api/qc_thumb?path={fp.relative_to(_REPO_ROOT).as_posix()}",
                        "verdict": data["results"].get(str(idx), {}),
                    })
            out.append({
                "report": r.name, "video": data.get("video"),
                "pass_count": data.get("pass_count"), "total": data.get("total_analyzed"),
                "thumbs": thumbs,
            })
        except Exception:
            continue
    return out


@app.route("/")
def index():
    return INDEX_HTML


@app.route("/api/gpu")
def api_gpu():
    return jsonify(_gpu_snapshot())


@app.route("/api/queue")
def api_queue():
    return jsonify(_queue_snapshot())


@app.route("/api/logs")
def api_logs():
    return jsonify({"lines": _tail_log(50)})


@app.route("/api/qc")
def api_qc():
    return jsonify(_qc_snapshot())


@app.route("/api/qc_thumb")
def api_qc_thumb():
    rel = request.args.get("path", "")
    fp = (_REPO_ROOT / rel).resolve()
    if not str(fp).startswith(str(_REPO_ROOT)) or not fp.exists():
        return "not found", 404
    return send_file(fp)


@app.route("/api/control", methods=["GET"])
def api_control_get():
    return jsonify(_read_control())


@app.route("/api/control", methods=["POST"])
def api_control_post():
    patch = request.get_json(force=True, silent=True) or {}
    allowed = {k: v for k, v in patch.items() if k in ("paused", "skip_clip", "cfg", "steps")}
    return jsonify(_write_control(allowed))


INDEX_HTML = """<!DOCTYPE html>
<html lang="fr">
<head>
<meta charset="UTF-8">
<title>Maestro Dashboard -- Ov3rLoRd</title>
<style>
  * { margin:0; padding:0; box-sizing:border-box; }
  body { background:#0a0a0f; color:#c0c0d0; font-family:Consolas,monospace; padding:20px; }
  h1 { color:#7c3aed; font-size:1.4em; margin-bottom:16px; }
  .grid { display:grid; grid-template-columns:repeat(auto-fit,minmax(280px,1fr)); gap:12px; margin-bottom:16px; }
  .card { background:#12121a; border:1px solid #1e1e2e; border-radius:8px; padding:16px; }
  .card h2 { color:#7c3aed; font-size:.85em; margin-bottom:10px; text-transform:uppercase; }
  .metric { display:flex; justify-content:space-between; margin:6px 0; font-size:.85em; }
  .metric .val { color:#10b981; font-weight:bold; }
  .metric .val.warn { color:#f59e0b; }
  .metric .val.err  { color:#ef4444; }
  .btn { background:#7c3aed; color:#fff; border:none; padding:8px 16px;
         border-radius:4px; cursor:pointer; font-family:Consolas; margin:4px 4px 4px 0; font-size:.85em; }
  .btn:hover { background:#9d5cf0; }
  .btn.danger { background:#ef4444; }
  input[type=text], input[type=number] {
    background:#0a0a0f; border:1px solid #1e1e2e; color:#c0c0d0;
    padding:6px 8px; border-radius:4px; font-family:Consolas; width:80px; margin:0 6px 0 0;
  }
  #log { background:#080810; padding:12px; border-radius:6px; font-size:.72em;
         height:220px; overflow-y:auto; border:1px solid #1e1e2e; white-space:pre-wrap; }
  .clip-row { font-size:.8em; padding:4px 0; border-bottom:1px solid #1e1e2e; }
  .thumbs { display:flex; gap:8px; flex-wrap:wrap; margin-top:8px; }
  .thumb { width:96px; }
  .thumb img { width:96px; height:auto; border-radius:4px; border:1px solid #1e1e2e; display:block; }
  .thumb .v { font-size:.65em; text-align:center; margin-top:2px; }
  .v.pass { color:#10b981; } .v.fail { color:#ef4444; }
</style>
</head>
<body>
<h1>&#9670; MAESTRO DASHBOARD -- Orchestration parallele SVI</h1>

<div class="grid">
  <div class="card"><h2>GPU</h2><div id="gpu">Chargement...</div></div>
  <div class="card"><h2>Queue pipeline</h2><div id="queue">Chargement...</div></div>
  <div class="card">
    <h2>Controles</h2>
    <button class="btn" id="pauseBtn" onclick="togglePause()">Pause</button>
    <div style="margin-top:8px">
      Skip clip # <input type="number" id="skipClip" min="0">
      <button class="btn" onclick="skipClip()">Skip</button>
    </div>
    <div style="margin-top:8px">
      CFG <input type="text" id="cfgVal" placeholder="1.5">
      Steps <input type="number" id="stepsVal" placeholder="8">
      <button class="btn" onclick="applyParams()">Appliquer</button>
    </div>
    <div id="ctrlState" style="margin-top:8px; font-size:.75em; color:#606070"></div>
  </div>
</div>

<div class="grid">
  <div class="card" style="grid-column:1 / -1">
    <h2>QC visuel (qwen2.5vl)</h2>
    <div id="qc">Chargement...</div>
  </div>
</div>

<div class="card">
  <h2>Logs (50 dernieres lignes)</h2>
  <div id="log"></div>
</div>

<script>
function fmtGpu(g) {
  if (g.error) return `<div class="metric"><span>Erreur</span><span class="val err">${g.error}</span></div>`;
  const vramClass = g.vram_pct > 90 ? 'err' : (g.vram_pct > 70 ? 'warn' : '');
  const tempClass = g.temp_c > 80 ? 'err' : (g.temp_c > 70 ? 'warn' : '');
  return `
    <div class="metric"><span>GPU ${g.index} -- ${g.name}</span><span></span></div>
    <div class="metric"><span>VRAM</span><span class="val ${vramClass}">${g.vram_used_mb}/${g.vram_total_mb} Mo (${g.vram_pct}%)</span></div>
    <div class="metric"><span>Temp</span><span class="val ${tempClass}">${g.temp_c}&deg;C</span></div>
    <div class="metric"><span>Util</span><span class="val">${g.util_pct}%</span></div>
  `;
}

async function refreshGpu() {
  const gpus = await fetch('/api/gpu').then(r=>r.json());
  document.getElementById('gpu').innerHTML = gpus.map(fmtGpu).join('<hr style="border-color:#1e1e2e;margin:8px 0">');
}

async function refreshQueue() {
  const q = await fetch('/api/queue').then(r=>r.json());
  let html = `<div class="metric"><span>En attente</span><span class="val">${q.pending.length}</span></div>`;
  html += `<div class="metric"><span>Termines</span><span class="val">${q.completed.length}</span></div>`;
  q.pending.slice(-5).forEach(c => html += `<div class="clip-row">clip ${c.clip_index} -- en attente postprod</div>`);
  q.completed.slice(-5).forEach(c => html += `<div class="clip-row">clip ${c.clip_index} -- OK (QC ${c.qc_pass_count ?? '?'}/${c.qc_total ?? '?'})</div>`);
  document.getElementById('queue').innerHTML = html;
}

async function refreshLogs() {
  const l = await fetch('/api/logs').then(r=>r.json());
  const box = document.getElementById('log');
  box.textContent = l.lines.join('\\n');
  box.scrollTop = box.scrollHeight;
}

async function refreshQc() {
  const reports = await fetch('/api/qc').then(r=>r.json());
  if (!reports.length) { document.getElementById('qc').innerHTML = '<span style="font-size:.8em;color:#606070">Aucun rapport QC pour le moment</span>'; return; }
  let html = '';
  reports.forEach(r => {
    html += `<div style="margin-bottom:10px"><div class="metric"><span>${r.video}</span><span class="val">${r.pass_count}/${r.total} OK</span></div>`;
    html += '<div class="thumbs">';
    r.thumbs.forEach(t => {
      const ok = t.verdict.pass;
      html += `<div class="thumb"><img src="${t.url}"><div class="v ${ok?'pass':'fail'}">f${t.frame} ${ok?'OK':'FAIL'} (${t.verdict.drift_severity||'?'})</div></div>`;
    });
    html += '</div></div>';
  });
  document.getElementById('qc').innerHTML = html;
}

async function refreshControl() {
  const c = await fetch('/api/control').then(r=>r.json());
  document.getElementById('pauseBtn').textContent = c.paused ? 'Resume' : 'Pause';
  document.getElementById('ctrlState').textContent =
    `paused=${c.paused} | skip_clip=${c.skip_clip} | cfg=${c.cfg ?? 'defaut'} | steps=${c.steps ?? 'defaut'}`;
}

async function togglePause() {
  const c = await fetch('/api/control').then(r=>r.json());
  await fetch('/api/control', {method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify({paused: !c.paused})});
  refreshControl();
}
async function skipClip() {
  const n = parseInt(document.getElementById('skipClip').value);
  if (isNaN(n)) return;
  await fetch('/api/control', {method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify({skip_clip: n})});
  refreshControl();
}
async function applyParams() {
  const cfg = parseFloat(document.getElementById('cfgVal').value);
  const steps = parseInt(document.getElementById('stepsVal').value);
  const patch = {};
  if (!isNaN(cfg)) patch.cfg = cfg;
  if (!isNaN(steps)) patch.steps = steps;
  await fetch('/api/control', {method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify(patch)});
  refreshControl();
}

function refreshAll() {
  refreshGpu(); refreshQueue(); refreshLogs(); refreshQc(); refreshControl();
}
refreshAll();
setInterval(refreshGpu, 5000);
setInterval(refreshQueue, 5000);
setInterval(refreshLogs, 5000);
setInterval(refreshQc, 10000);
setInterval(refreshControl, 5000);
</script>
</body>
</html>
"""


if __name__ == "__main__":
    QUEUE_DIR.mkdir(parents=True, exist_ok=True)
    print("Maestro Dashboard -- http://localhost:5000")
    app.run(host="0.0.0.0", port=5000, debug=False)

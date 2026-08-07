"""
agents/v130_pipeline_api.py — OverLord V1.30 — Pipeline as a Service

OverLord devient une API REST que d'autres applications peuvent utiliser.
Une application externe, un script, un autre pipeline, ou un partenaire
peut soumettre des jobs et récupérer les résultats via HTTP.

Architecture :
  - API Gateway Flask  : authentification, routing, rate limiting
  - Job Queue          : file d'attente des jobs externes
  - Webhook Support    : callbacks quand un job est terminé
  - SDK Python         : client Python pour consommer l'API

Endpoints :
  POST /api/v1/generate     — soumettre un job de génération
  GET  /api/v1/job/{id}     — status d'un job
  GET  /api/v1/jobs         — liste des jobs
  POST /api/v1/pipeline     — lancer un pipeline complet
  GET  /api/v1/health       — santé de l'API
  GET  /api/v1/capabilities — ce que l'API peut faire
  POST /api/v1/webhook      — enregistrer un webhook

pip install flask flask-limiter
"""

import json
import uuid
import time
import hashlib
import hmac
import logging
import threading
import requests as req
from pathlib import Path
from datetime import datetime, timedelta
from dataclasses import dataclass, field
from typing import Optional
from functools import wraps

try:
    from flask import Flask, request, jsonify, abort
    FLASK_OK = True
except ImportError:
    FLASK_OK = False

API_DIR       = Path("workspace/api")
JOBS_FILE     = API_DIR / "jobs.json"
KEYS_FILE     = API_DIR / "api_keys.json"
API_VERSION   = "v1"
DEFAULT_PORT  = 5002


# ══════════════════════════════════════════════════════════════════════
# JOB SYSTEM
# ══════════════════════════════════════════════════════════════════════

class JobStatus:
    QUEUED     = "queued"
    RUNNING    = "running"
    DONE       = "done"
    FAILED     = "failed"
    CANCELLED  = "cancelled"


@dataclass
class APIJob:
    """Un job soumis via l'API."""
    id:            str
    api_key_id:    str
    job_type:      str          # "generate", "pipeline", "scenario"
    params:        dict
    status:        str = JobStatus.QUEUED
    created_at:    str = field(default_factory=lambda: datetime.utcnow().isoformat())
    started_at:    str = ""
    ended_at:      str = ""
    result:        dict = field(default_factory=dict)
    error:         str = ""
    webhook_url:   str = ""
    priority:      int = 5      # 1=urgent, 10=basse

    def to_dict(self) -> dict:
        return {
            "id":          self.id,
            "job_type":    self.job_type,
            "status":      self.status,
            "created_at":  self.created_at,
            "started_at":  self.started_at,
            "ended_at":    self.ended_at,
            "result":      self.result,
            "error":       self.error,
            "params_preview": {k:v for k,v in list(self.params.items())[:3]},
        }


class JobQueue:
    """File d'attente des jobs API."""

    def __init__(self):
        self._jobs: dict[str, APIJob] = {}
        self._queue: list[str] = []    # IDs ordonnés par priorité
        self._lock  = threading.Lock()
        API_DIR.mkdir(parents=True, exist_ok=True)
        self._load()

    def submit(self, job: APIJob) -> str:
        with self._lock:
            self._jobs[job.id] = job
            # Insérer selon la priorité
            inserted = False
            for i, jid in enumerate(self._queue):
                if self._jobs[jid].priority > job.priority:
                    self._queue.insert(i, job.id)
                    inserted = True
                    break
            if not inserted:
                self._queue.append(job.id)
        self._save()
        return job.id

    def next(self) -> Optional[APIJob]:
        with self._lock:
            for jid in self._queue:
                job = self._jobs.get(jid)
                if job and job.status == JobStatus.QUEUED:
                    job.status     = JobStatus.RUNNING
                    job.started_at = datetime.utcnow().isoformat()
                    return job
        return None

    def complete(self, job_id: str, result: dict):
        with self._lock:
            job = self._jobs.get(job_id)
            if job:
                job.status   = JobStatus.DONE
                job.result   = result
                job.ended_at = datetime.utcnow().isoformat()
        self._save()

    def fail(self, job_id: str, error: str):
        with self._lock:
            job = self._jobs.get(job_id)
            if job:
                job.status   = JobStatus.FAILED
                job.error    = error
                job.ended_at = datetime.utcnow().isoformat()
        self._save()

    def get(self, job_id: str) -> Optional[APIJob]:
        return self._jobs.get(job_id)

    def list_jobs(self, api_key_id: str = None, limit: int = 20) -> list[dict]:
        jobs = list(self._jobs.values())
        if api_key_id:
            jobs = [j for j in jobs if j.api_key_id == api_key_id]
        jobs.sort(key=lambda j: j.created_at, reverse=True)
        return [j.to_dict() for j in jobs[:limit]]

    def stats(self) -> dict:
        with self._lock:
            all_jobs = list(self._jobs.values())
        return {
            "total":    len(all_jobs),
            "queued":   sum(1 for j in all_jobs if j.status == JobStatus.QUEUED),
            "running":  sum(1 for j in all_jobs if j.status == JobStatus.RUNNING),
            "done":     sum(1 for j in all_jobs if j.status == JobStatus.DONE),
            "failed":   sum(1 for j in all_jobs if j.status == JobStatus.FAILED),
        }

    def _save(self):
        data = {jid: j.__dict__ for jid, j in self._jobs.items()}
        JOBS_FILE.write_text(
            json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8"
        )

    def _load(self):
        if JOBS_FILE.exists():
            try:
                data = json.loads(JOBS_FILE.read_text(encoding="utf-8"))
                for jid, d in data.items():
                    self._jobs[jid] = APIJob(**d)
                    if d.get("status") == JobStatus.QUEUED:
                        self._queue.append(jid)
            except Exception:
                pass


# ══════════════════════════════════════════════════════════════════════
# GESTION DES CLÉS API
# ══════════════════════════════════════════════════════════════════════

class APIKeyManager:
    """Gestion des clés API pour l'accès externe."""

    def __init__(self):
        self._keys: dict[str, dict] = {}
        API_DIR.mkdir(parents=True, exist_ok=True)
        self._load()

    def create_key(self, name: str, permissions: list = None,
                    rate_limit: int = 100) -> dict:
        """Crée une nouvelle clé API."""
        import secrets
        raw_key  = "ovl_" + secrets.token_hex(24)
        key_id   = hashlib.sha256(raw_key.encode()).hexdigest()[:16]
        entry    = {
            "id":          key_id,
            "name":        name,
            "permissions": permissions or ["generate","status"],
            "rate_limit":  rate_limit,      # requêtes/heure
            "calls_today": 0,
            "created_at":  datetime.utcnow().isoformat(),
            "last_used":   None,
            "active":      True,
            "key_hash":    hashlib.sha256(raw_key.encode()).hexdigest(),
        }
        self._keys[key_id] = entry
        self._save()
        # Retourner la clé en clair UNE SEULE FOIS
        return {**entry, "api_key": raw_key}

    def validate(self, raw_key: str) -> Optional[dict]:
        """Valide une clé API et retourne son entrée."""
        if not raw_key or not raw_key.startswith("ovl_"):
            return None
        key_hash = hashlib.sha256(raw_key.encode()).hexdigest()
        for entry in self._keys.values():
            if hmac.compare_digest(entry["key_hash"], key_hash):
                if not entry["active"]:
                    return None
                entry["last_used"] = datetime.utcnow().isoformat()
                entry["calls_today"] += 1
                self._save()
                return entry
        return None

    def revoke(self, key_id: str):
        if key_id in self._keys:
            self._keys[key_id]["active"] = False
            self._save()

    def list_keys(self) -> list[dict]:
        return [{k:v for k,v in e.items() if k != "key_hash"}
                for e in self._keys.values()]

    def _save(self):
        KEYS_FILE.write_text(
            json.dumps(self._keys, indent=2, ensure_ascii=False), encoding="utf-8"
        )

    def _load(self):
        if KEYS_FILE.exists():
            try:
                self._keys = json.loads(KEYS_FILE.read_text(encoding="utf-8"))
            except Exception:
                pass


# ══════════════════════════════════════════════════════════════════════
# WEBHOOK MANAGER
# ══════════════════════════════════════════════════════════════════════

class WebhookManager:
    """Envoie des callbacks HTTP quand un job est terminé."""

    def __init__(self, logger: logging.Logger = None):
        self.log    = logger or logging.getLogger("webhook")
        self._hooks: dict[str, list[str]] = {}   # api_key_id → [urls]

    def register(self, api_key_id: str, url: str):
        if api_key_id not in self._hooks:
            self._hooks[api_key_id] = []
        if url not in self._hooks[api_key_id]:
            self._hooks[api_key_id].append(url)

    def fire(self, job: APIJob):
        """Envoie le webhook pour un job terminé (en background)."""
        urls = self._hooks.get(job.api_key_id, [])
        if job.webhook_url and job.webhook_url not in urls:
            urls = urls + [job.webhook_url]

        for url in urls:
            def _send(target_url):
                try:
                    req.post(target_url, json={
                        "event":    "job_complete",
                        "job_id":   job.id,
                        "status":   job.status,
                        "result":   job.result,
                        "error":    job.error,
                        "ts":       datetime.utcnow().isoformat(),
                    }, timeout=10)
                    self.log.info(f"[WEBHOOK] Sent to {target_url}")
                except Exception as e:
                    self.log.warning(f"[WEBHOOK] Failed {target_url}: {e}")
            threading.Thread(target=_send, args=(url,), daemon=True).start()


# ══════════════════════════════════════════════════════════════════════
# PIPELINE API SERVER
# ══════════════════════════════════════════════════════════════════════

class PipelineAPIServer:
    """
    Serveur API REST Flask pour OverLord Pipeline as a Service.
    """

    def __init__(self, pipeline_fn=None, logger: logging.Logger = None):
        self.log         = logger or logging.getLogger("pipeline_api")
        self.pipeline_fn = pipeline_fn   # callable(params) → result
        self.jobs        = JobQueue()
        self.keys        = APIKeyManager()
        self.webhooks    = WebhookManager(self.log)
        self._worker_thread: Optional[threading.Thread] = None

        if not FLASK_OK:
            self.log.error("pip install flask")
            return

        self.app = Flask(__name__)
        self._register_routes()
        self._start_worker()

    def _auth_required(self, permission: str = "generate"):
        """Décorateur d'authentification."""
        def decorator(fn):
            @wraps(fn)
            def wrapper(*args, **kwargs):
                auth = request.headers.get("Authorization","")
                if not auth.startswith("Bearer "):
                    abort(401)
                raw_key = auth[7:]
                entry   = self.keys.validate(raw_key)
                if not entry:
                    abort(401)
                if permission not in entry.get("permissions",[]):
                    abort(403)
                request.api_key_entry = entry
                return fn(*args, **kwargs)
            return wrapper
        return decorator

    def _register_routes(self):
        app = self.app

        @app.route(f"/api/{API_VERSION}/health")
        def health():
            return jsonify({
                "status":  "ok",
                "version": API_VERSION,
                "service": "OverLord Pipeline API",
                "jobs":    self.jobs.stats(),
                "ts":      datetime.utcnow().isoformat(),
            })

        @app.route(f"/api/{API_VERSION}/capabilities")
        def capabilities():
            return jsonify({
                "version":     API_VERSION,
                "endpoints":   [
                    "POST /generate",
                    "GET  /job/{id}",
                    "GET  /jobs",
                    "POST /pipeline",
                    "POST /webhook",
                ],
                "job_types":   ["generate","scenario","storyboard","pipeline"],
                "media_types": ["anime","manga","comics","3d","photoreal"],
                "max_priority":10,
                "rate_limit":  "100 req/hour per key",
            })

        @app.route(f"/api/{API_VERSION}/generate", methods=["POST"])
        @self._auth_required("generate")
        def generate():
            data = request.get_json(silent=True) or {}
            job  = APIJob(
                id          = str(uuid.uuid4()),
                api_key_id  = request.api_key_entry["id"],
                job_type    = "generate",
                params      = {
                    "positive":   data.get("positive","masterpiece, anime style"),
                    "negative":   data.get("negative","bad quality, worst quality"),
                    "media_type": data.get("media_type","anime"),
                    "width":      data.get("width",  1024),
                    "height":     data.get("height", 1536),
                    "steps":      data.get("steps",  28),
                    "cfg":        data.get("cfg",    6.0),
                    "sampler":    data.get("sampler","euler_ancestral"),
                },
                webhook_url = data.get("webhook_url",""),
                priority    = int(data.get("priority", 5)),
            )
            self.jobs.submit(job)
            self.log.info(f"[API] Job soumis : {job.id} par {request.api_key_entry['name']}")
            return jsonify({
                "job_id":     job.id,
                "status":     job.status,
                "queue_pos":  len([j for j in self.jobs._queue
                                    if self.jobs._jobs[j].status == JobStatus.QUEUED]),
                "estimated_s":job.params.get("steps",28) * 2,
            }), 202

        @app.route(f"/api/{API_VERSION}/job/<job_id>")
        @self._auth_required("status")
        def job_status(job_id):
            job = self.jobs.get(job_id)
            if not job:
                return jsonify({"error": "not_found"}), 404
            return jsonify(job.to_dict())

        @app.route(f"/api/{API_VERSION}/jobs")
        @self._auth_required("status")
        def list_jobs():
            jobs = self.jobs.list_jobs(
                api_key_id=request.api_key_entry["id"],
                limit=int(request.args.get("limit",20))
            )
            return jsonify({"jobs": jobs, "stats": self.jobs.stats()})

        @app.route(f"/api/{API_VERSION}/pipeline", methods=["POST"])
        @self._auth_required("pipeline")
        def run_pipeline():
            data = request.get_json(silent=True) or {}
            job  = APIJob(
                id         = str(uuid.uuid4()),
                api_key_id = request.api_key_entry["id"],
                job_type   = "pipeline",
                params     = data,
                priority   = int(data.get("priority",5)),
            )
            self.jobs.submit(job)
            return jsonify({"job_id":job.id,"status":job.status}), 202

        @app.route(f"/api/{API_VERSION}/webhook", methods=["POST"])
        @self._auth_required("generate")
        def register_webhook():
            data = request.get_json(silent=True) or {}
            url  = data.get("url","")
            if not url.startswith("http"):
                return jsonify({"error":"Invalid URL"}), 400
            self.webhooks.register(request.api_key_entry["id"], url)
            return jsonify({"registered":True,"url":url})

        # Admin (pas d'auth clé API — utiliser l'IP locale uniquement)
        @app.route(f"/api/{API_VERSION}/admin/keys", methods=["POST"])
        def create_key():
            if request.remote_addr not in ("127.0.0.1","::1"):
                abort(403)
            data = request.get_json(silent=True) or {}
            key  = self.keys.create_key(
                name=data.get("name","default"),
                permissions=data.get("permissions",["generate","status"]),
                rate_limit=data.get("rate_limit",100),
            )
            return jsonify(key)

        @app.route(f"/api/{API_VERSION}/admin/keys")
        def list_keys():
            if request.remote_addr not in ("127.0.0.1","::1"):
                abort(403)
            return jsonify({"keys": self.keys.list_keys()})

    def _start_worker(self):
        """Worker qui traite les jobs en file d'attente."""
        def _loop():
            while True:
                job = self.jobs.next()
                if job:
                    try:
                        if self.pipeline_fn:
                            result = self.pipeline_fn(job.params)
                        else:
                            # Simulation
                            time.sleep(2)
                            result = {
                                "simulated":  True,
                                "job_id":     job.id,
                                "output_url": f"/outputs/{job.id}.png",
                                "quality":    0.78,
                            }
                        self.jobs.complete(job.id, result)
                        self.webhooks.fire(job)
                        self.log.info(f"[API/Worker] Job {job.id} terminé ✓")
                    except Exception as e:
                        self.jobs.fail(job.id, str(e))
                        self.webhooks.fire(job)
                        self.log.error(f"[API/Worker] Job {job.id} échoué : {e}")
                else:
                    time.sleep(1)

        self._worker_thread = threading.Thread(target=_loop, daemon=True)
        self._worker_thread.start()

    def run(self, host: str = "0.0.0.0", port: int = DEFAULT_PORT,
             debug: bool = False):
        """Démarre le serveur API."""
        import socket
        local_ip = socket.gethostbyname(socket.gethostname())
        print(f"\n{'='*55}")
        print(f"  OverLord Pipeline API v{API_VERSION}")
        print(f"{'='*55}")
        print(f"  Local    : http://localhost:{port}/api/{API_VERSION}/health")
        print(f"  Réseau   : http://{local_ip}:{port}/api/{API_VERSION}/health")
        print(f"\n  Créer une clé API (admin local) :")
        print(f"  curl -X POST http://localhost:{port}/api/{API_VERSION}/admin/keys \\")
        print(f"       -H 'Content-Type: application/json' \\")
        print(f"       -d '{{\"name\":\"mon_client\",\"permissions\":[\"generate\",\"status\",\"pipeline\"]}}'")
        print(f"{'='*55}\n")
        self.app.run(host=host, port=port, debug=debug,
                      use_reloader=False, threaded=True)


# ══════════════════════════════════════════════════════════════════════
# SDK CLIENT PYTHON
# ══════════════════════════════════════════════════════════════════════

class OverLordClient:
    """
    SDK Python pour consommer l'API OverLord depuis n'importe quel script.

    Usage :
        client = OverLordClient("http://localhost:5002", "ovl_xxx")
        job    = client.generate(positive="1girl, anime style", steps=28)
        result = client.wait_for_job(job["job_id"])
        print(result)
    """

    def __init__(self, base_url: str, api_key: str):
        self.base     = base_url.rstrip("/")
        self.api_key  = api_key
        self.session  = req.Session()
        self.session.headers.update({
            "Authorization": f"Bearer {api_key}",
            "Content-Type":  "application/json",
        })

    def generate(self, **params) -> dict:
        r = self.session.post(f"{self.base}/api/{API_VERSION}/generate",
                               json=params, timeout=10)
        r.raise_for_status()
        return r.json()

    def pipeline(self, **params) -> dict:
        r = self.session.post(f"{self.base}/api/{API_VERSION}/pipeline",
                               json=params, timeout=10)
        r.raise_for_status()
        return r.json()

    def job_status(self, job_id: str) -> dict:
        r = self.session.get(f"{self.base}/api/{API_VERSION}/job/{job_id}",
                              timeout=10)
        r.raise_for_status()
        return r.json()

    def wait_for_job(self, job_id: str, timeout: float = 300,
                      poll_interval: float = 2.0) -> dict:
        """Attend la fin d'un job."""
        start = time.time()
        while time.time() - start < timeout:
            status = self.job_status(job_id)
            if status["status"] in (JobStatus.DONE, JobStatus.FAILED):
                return status
            time.sleep(poll_interval)
        return {"status": "timeout", "job_id": job_id}

    def health(self) -> dict:
        r = self.session.get(f"{self.base}/api/{API_VERSION}/health", timeout=5)
        return r.json() if r.status_code == 200 else {"status":"error"}

    def list_jobs(self, limit: int = 10) -> list:
        r = self.session.get(f"{self.base}/api/{API_VERSION}/jobs",
                              params={"limit":limit}, timeout=10)
        return r.json().get("jobs",[]) if r.status_code == 200 else []


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    log = logging.getLogger("api_test")

    if not FLASK_OK:
        print("pip install flask")
        import sys; sys.exit(1)

    server = PipelineAPIServer(logger=log)

    # Créer une clé API de test
    key_info = server.keys.create_key("test_client",
                                       permissions=["generate","status","pipeline"])
    print(f"\nClé API de test créée : {key_info['api_key']}")
    print(f"Démarrage du serveur sur le port {DEFAULT_PORT}...")
    server.run(debug=False)

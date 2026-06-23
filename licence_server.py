"""
licence_server.py — Serveur de Licences OverLord
Tourne sur ta machine Windows, accessible depuis ton Samsung S10+.

Démarrage :
  python licence_server.py

Accès mobile (S10+) :
  http://TON_IP_LOCAL:5001/dashboard  (réseau local WiFi)
  https://xxx.ngrok.io/dashboard      (via ngrok, partout)

Endpoints :
  POST /generate    → génère une nouvelle clé (admin seulement)
  POST /validate    → valide une clé (appelé par le .exe)
  POST /revoke      → révoque une clé (admin)
  GET  /status      → liste toutes les licences (admin)
  GET  /dashboard   → interface web mobile S10+
  GET  /health      → ping

pip install flask cryptography
"""

import os
import json
import uuid
import hashlib
import hmac
import secrets
import logging
import threading
from pathlib import Path
from datetime import datetime, timedelta
from functools import wraps

try:
    from flask import Flask, request, jsonify, render_template_string, abort
    FLASK_OK = True
except ImportError:
    FLASK_OK = False
    print("pip install flask")

try:
    from cryptography.fernet import Fernet
    CRYPTO_OK = True
except ImportError:
    CRYPTO_OK = False
    print("pip install cryptography")

# ── Configuration ──────────────────────────────────────────────────────
SERVER_PORT   = 5001
DATA_DIR      = Path("licence_data")
KEYS_FILE     = DATA_DIR / "licences.json"
CONFIG_FILE   = DATA_DIR / "server_config.json"
LOG_FILE      = DATA_DIR / "server.log"

# Durées de licence disponibles
DURATIONS = {
    "7d":   7,
    "30d":  30,
    "90d":  90,
    "365d": 365,
    "lifetime": 36500,  # 100 ans = lifetime
}

# Nombre max de machines par licence
MAX_MACHINES_PER_KEY = 2

# HTML du dashboard mobile
DASHBOARD_HTML = """
<!DOCTYPE html>
<html lang="fr">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0, user-scalable=no">
<title>Ov3rLoRd — Licences</title>
<style>
  * { box-sizing: border-box; margin: 0; padding: 0; }
  body {
    background: #0A0A12;
    color: #E0E0F0;
    font-family: -apple-system, 'Segoe UI', sans-serif;
    padding: 16px;
    min-height: 100vh;
  }
  .header {
    display: flex; align-items: center; gap: 12px;
    padding: 16px 0 20px;
    border-bottom: 1px solid #2A2A3E;
    margin-bottom: 20px;
  }
  .header h1 { font-size: 1.3rem; color: #A855F7; }
  .header .dot { width: 10px; height: 10px; border-radius: 50%;
                  background: #10B981; animation: pulse 2s infinite; }
  @keyframes pulse { 0%,100%{opacity:1} 50%{opacity:0.4} }
  .stats {
    display: grid; grid-template-columns: 1fr 1fr;
    gap: 12px; margin-bottom: 24px;
  }
  .stat-card {
    background: #16161E;
    border: 1px solid #2A2A3E;
    border-radius: 12px;
    padding: 16px; text-align: center;
  }
  .stat-card .val { font-size: 2rem; font-weight: 700; color: #A855F7; }
  .stat-card .lbl { font-size: 0.75rem; color: #7070A8; margin-top: 4px; }
  .section-title {
    font-size: 0.85rem; font-weight: 700;
    color: #7070A8; text-transform: uppercase;
    letter-spacing: 0.08em; margin-bottom: 12px;
  }
  .licence-card {
    background: #16161E;
    border: 1px solid #2A2A3E;
    border-radius: 12px;
    padding: 14px; margin-bottom: 10px;
  }
  .licence-card .key {
    font-family: 'Courier New', monospace;
    font-size: 0.75rem; color: #A0C8FF;
    word-break: break-all; margin-bottom: 8px;
  }
  .licence-card .meta {
    display: flex; gap: 8px; flex-wrap: wrap;
  }
  .badge {
    font-size: 0.7rem; padding: 3px 8px;
    border-radius: 20px; font-weight: 600;
  }
  .badge-active  { background: #064E3B; color: #10B981; }
  .badge-expired { background: #7F1D1D; color: #EF4444; }
  .badge-revoked { background: #3F2D00; color: #F59E0B; }
  .badge-info    { background: #1E1B4B; color: #A5B4FC; }
  .actions {
    display: grid; grid-template-columns: 1fr 1fr;
    gap: 10px; margin-top: 24px;
  }
  .btn {
    background: #7C3AED; color: white;
    border: none; border-radius: 10px;
    padding: 14px; font-size: 0.9rem; font-weight: 600;
    cursor: pointer; text-align: center;
  }
  .btn-danger { background: #991B1B; }
  .btn-secondary { background: #2A2A3E; }
  .form-section {
    background: #16161E; border: 1px solid #2A2A3E;
    border-radius: 12px; padding: 16px; margin-top: 20px;
  }
  .form-section h3 { color: #A855F7; margin-bottom: 14px; font-size: 1rem; }
  .form-row { margin-bottom: 12px; }
  .form-row label { font-size: 0.8rem; color: #7070A8; display: block; margin-bottom: 4px; }
  .form-row input, .form-row select {
    width: 100%; background: #0A0A12;
    border: 1px solid #3A3A5E; border-radius: 8px;
    color: #E0E0F0; padding: 10px 12px;
    font-size: 0.9rem;
  }
  .result-box {
    background: #0A0A12; border: 1px solid #3A3A5E;
    border-radius: 8px; padding: 12px; margin-top: 12px;
    font-family: monospace; font-size: 0.8rem;
    color: #A0FFA8; word-break: break-all;
    display: none;
  }
  .footer { text-align: center; color: #404060;
             font-size: 0.75rem; margin-top: 30px; padding: 16px; }
</style>
</head>
<body>

<div class="header">
  <div class="dot"></div>
  <h1>⬡ Ov3rLoRd Licences</h1>
</div>

<div class="stats">
  <div class="stat-card">
    <div class="val">{{ stats.total }}</div>
    <div class="lbl">Total licences</div>
  </div>
  <div class="stat-card">
    <div class="val">{{ stats.active }}</div>
    <div class="lbl">Actives</div>
  </div>
  <div class="stat-card">
    <div class="val">{{ stats.expired }}</div>
    <div class="lbl">Expirées</div>
  </div>
  <div class="stat-card">
    <div class="val">{{ stats.machines }}</div>
    <div class="lbl">Machines enr.</div>
  </div>
</div>

<div class="section-title">Licences actives</div>
{% for lic in licences %}
<div class="licence-card">
  <div class="key">{{ lic.key[:20] }}…{{ lic.key[-8:] }}</div>
  <div class="meta">
    <span class="badge badge-{{ lic.status_class }}">{{ lic.status }}</span>
    <span class="badge badge-info">{{ lic.name }}</span>
    <span class="badge badge-info">exp. {{ lic.expires }}</span>
    <span class="badge badge-info">{{ lic.machine_count }} machine(s)</span>
  </div>
</div>
{% endfor %}

<div class="form-section">
  <h3>🔑 Générer une licence</h3>
  <div class="form-row">
    <label>Nom du bêta-testeur</label>
    <input type="text" id="tester_name" placeholder="Ex: Alice_beta">
  </div>
  <div class="form-row">
    <label>Durée</label>
    <select id="duration">
      <option value="7d">7 jours</option>
      <option value="30d" selected>30 jours</option>
      <option value="90d">90 jours</option>
      <option value="365d">1 an</option>
      <option value="lifetime">Lifetime</option>
    </select>
  </div>
  <div class="form-row">
    <label>Clé admin</label>
    <input type="password" id="admin_key" placeholder="Ta clé admin secrète">
  </div>
  <button class="btn" onclick="generateKey()">Générer la clé</button>
  <div class="result-box" id="result_box"></div>
</div>

<div class="form-section">
  <h3>🚫 Révoquer une licence</h3>
  <div class="form-row">
    <label>Clé à révoquer</label>
    <input type="text" id="revoke_key" placeholder="Colle la clé ici">
  </div>
  <div class="form-row">
    <label>Clé admin</label>
    <input type="password" id="revoke_admin" placeholder="Ta clé admin secrète">
  </div>
  <button class="btn btn-danger" onclick="revokeKey()">Révoquer</button>
  <div class="result-box" id="revoke_result"></div>
</div>

<div class="footer">Ov3rLoRd v1.0.0-alpha • {{ server_time }}</div>

<script>
const BASE = window.location.origin;

async function generateKey() {
  const name  = document.getElementById('tester_name').value;
  const dur   = document.getElementById('duration').value;
  const admin = document.getElementById('admin_key').value;
  const box   = document.getElementById('result_box');
  box.style.display = 'block';
  box.textContent = 'Génération…';
  try {
    const r = await fetch(BASE + '/generate', {
      method: 'POST',
      headers: {'Content-Type':'application/json'},
      body: JSON.stringify({name, duration: dur, admin_key: admin})
    });
    const d = await r.json();
    if (d.key) {
      box.style.color = '#A0FFA8';
      box.textContent = '✓ Clé générée :\\n' + d.key + '\\n\\nExpire : ' + d.expires;
    } else {
      box.style.color = '#EF4444';
      box.textContent = '✗ ' + (d.error || 'Erreur');
    }
  } catch(e) {
    box.style.color = '#EF4444';
    box.textContent = '✗ ' + e.message;
  }
  setTimeout(() => location.reload(), 3000);
}

async function revokeKey() {
  const key   = document.getElementById('revoke_key').value;
  const admin = document.getElementById('revoke_admin').value;
  const box   = document.getElementById('revoke_result');
  box.style.display = 'block';
  try {
    const r = await fetch(BASE + '/revoke', {
      method: 'POST',
      headers: {'Content-Type':'application/json'},
      body: JSON.stringify({key, admin_key: admin})
    });
    const d = await r.json();
    box.style.color = d.revoked ? '#A0FFA8' : '#EF4444';
    box.textContent = d.revoked ? '✓ Clé révoquée' : '✗ ' + (d.error || 'Erreur');
  } catch(e) {
    box.style.color = '#EF4444';
    box.textContent = '✗ ' + e.message;
  }
  setTimeout(() => location.reload(), 2000);
}

// Auto-refresh toutes les 30s
setTimeout(() => location.reload(), 30000);
</script>
</body>
</html>
"""


class LicenceDB:
    """Base de données JSON des licences."""

    def __init__(self):
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        self._data = self._load()
        self._lock = threading.Lock()

    def _load(self) -> dict:
        if KEYS_FILE.exists():
            try:
                return json.loads(KEYS_FILE.read_text(encoding="utf-8"))
            except Exception:
                pass
        return {"licences": {}, "revoked": []}

    def _save(self):
        KEYS_FILE.write_text(
            json.dumps(self._data, indent=2, ensure_ascii=False),
            encoding="utf-8"
        )

    def add(self, key: str, entry: dict):
        with self._lock:
            self._data["licences"][key] = entry
            self._save()

    def get(self, key: str) -> dict | None:
        return self._data["licences"].get(key)

    def all_licences(self) -> dict:
        return dict(self._data["licences"])

    def revoke(self, key: str) -> bool:
        with self._lock:
            if key in self._data["licences"]:
                self._data["licences"][key]["status"] = "revoked"
                self._data["licences"][key]["revoked_at"] = datetime.utcnow().isoformat()
                if key not in self._data["revoked"]:
                    self._data["revoked"].append(key)
                self._save()
                return True
        return False

    def register_machine(self, key: str, machine_id: str) -> bool:
        with self._lock:
            entry = self._data["licences"].get(key)
            if not entry:
                return False
            machines = entry.get("machines", [])
            if machine_id not in machines:
                if len(machines) >= MAX_MACHINES_PER_KEY:
                    return False  # trop de machines
                machines.append(machine_id)
                entry["machines"] = machines
                entry["last_seen"] = datetime.utcnow().isoformat()
                self._save()
            else:
                entry["last_seen"] = datetime.utcnow().isoformat()
                self._save()
            return True


class LicenceServer:
    """Serveur Flask de gestion des licences."""

    def __init__(self):
        if not FLASK_OK:
            raise ImportError("flask requis : pip install flask")
        if not CRYPTO_OK:
            raise ImportError("cryptography requis : pip install cryptography")

        self.app   = Flask(__name__)
        self.db    = LicenceDB()
        self.cfg   = self._load_config()
        self.log   = self._setup_logging()

        # Clé de chiffrement Fernet
        self.fernet = Fernet(self.cfg["fernet_key"].encode())

        self._register_routes()
        self.log.info(f"[SERVER] OverLord Licence Server initialisé")
        self.log.info(f"[SERVER] Admin key hash : {self.cfg['admin_key_hash'][:16]}…")

    def _load_config(self) -> dict:
        if CONFIG_FILE.exists():
            try:
                return json.loads(CONFIG_FILE.read_text(encoding="utf-8"))
            except Exception:
                pass

        # Première exécution : générer les secrets
        admin_key  = secrets.token_hex(32)
        fernet_key = Fernet.generate_key().decode()
        cfg = {
            "admin_key_hash": hashlib.sha256(admin_key.encode()).hexdigest(),
            "fernet_key":     fernet_key,
            "server_name":    "OverLord Licence Server",
            "created_at":     datetime.utcnow().isoformat(),
        }
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        CONFIG_FILE.write_text(
            json.dumps(cfg, indent=2),
            encoding="utf-8"
        )

        # Afficher la clé admin UNE SEULE FOIS
        print("\n" + "═"*60)
        print("  🔑 CLÉ ADMIN GÉNÉRÉE — NOTE-LA MAINTENANT !")
        print("  (Elle ne sera plus affichée)")
        print(f"\n  ADMIN KEY : {admin_key}\n")
        print("═"*60 + "\n")

        return cfg

    def _setup_logging(self) -> logging.Logger:
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        log = logging.getLogger("licence_server")
        log.setLevel(logging.INFO)
        fmt = logging.Formatter("%(asctime)s [%(levelname)s] %(message)s")

        fh = logging.FileHandler(LOG_FILE, encoding="utf-8")
        fh.setFormatter(fmt)
        log.addHandler(fh)

        ch = logging.StreamHandler()
        ch.setFormatter(fmt)
        log.addHandler(ch)
        return log

    def _check_admin(self, provided_key: str) -> bool:
        """Vérifie la clé admin."""
        h = hashlib.sha256(provided_key.encode()).hexdigest()
        return hmac.compare_digest(h, self.cfg["admin_key_hash"])

    def _generate_licence_key(self, name: str, duration_days: int,
                               extra: dict = None) -> str:
        """Génère une clé de licence chiffrée."""
        payload = {
            "name":       name,
            "created_at": datetime.utcnow().isoformat(),
            "expires_at": (datetime.utcnow() + timedelta(days=duration_days)).isoformat(),
            "nonce":      secrets.token_hex(8),
        }
        if extra:
            payload.update(extra)
        raw     = json.dumps(payload, ensure_ascii=False)
        encoded = self.fernet.encrypt(raw.encode()).decode()
        return encoded

    def _decode_key(self, key: str) -> dict | None:
        """Déchiffre et valide une clé."""
        try:
            raw     = self.fernet.decrypt(key.encode())
            payload = json.loads(raw)
            return payload
        except Exception:
            return None

    def _register_routes(self):
        app = self.app

        @app.route("/health")
        def health():
            return jsonify({"status": "ok", "service": "OverLord Licence Server",
                             "time": datetime.utcnow().isoformat()})

        @app.route("/generate", methods=["POST"])
        def generate():
            data      = request.get_json(silent=True) or {}
            admin_key = data.get("admin_key", "")
            if not self._check_admin(admin_key):
                self.log.warning(f"[GEN] Tentative non autorisée depuis {request.remote_addr}")
                return jsonify({"error": "Unauthorized"}), 403

            name     = data.get("name", "beta_user")
            duration = data.get("duration", "30d")
            days     = DURATIONS.get(duration, 30)

            key      = self._generate_licence_key(name, days)
            expires  = (datetime.utcnow() + timedelta(days=days)).strftime("%d/%m/%Y")

            entry = {
                "name":       name,
                "created_at": datetime.utcnow().isoformat(),
                "expires_at": (datetime.utcnow() + timedelta(days=days)).isoformat(),
                "duration":   duration,
                "status":     "active",
                "machines":   [],
                "last_seen":  None,
            }
            self.db.add(key, entry)
            self.log.info(f"[GEN] Nouvelle licence : {name} | durée={duration} | expire={expires}")
            return jsonify({"key": key, "name": name,
                             "expires": expires, "duration": duration})

        @app.route("/validate", methods=["POST"])
        def validate():
            data       = request.get_json(silent=True) or {}
            key        = data.get("key", "")
            machine_id = data.get("machine_id", "unknown")
            app_version = data.get("version", "?")

            entry = self.db.get(key)

            # Clé inconnue
            if not entry:
                payload = self._decode_key(key)
                if not payload:
                    self.log.warning(f"[VAL] Clé invalide depuis {request.remote_addr}")
                    return jsonify({"valid": False, "reason": "invalid_key"}), 403
                # Clé valide mais pas en DB (première utilisation)
                entry = {
                    "name":       payload.get("name","unknown"),
                    "created_at": payload.get("created_at",""),
                    "expires_at": payload.get("expires_at",""),
                    "status":     "active",
                    "machines":   [],
                    "last_seen":  None,
                }
                self.db.add(key, entry)

            # Clé révoquée
            if entry.get("status") == "revoked":
                self.log.warning(f"[VAL] Clé révoquée : {entry.get('name')} | {machine_id}")
                return jsonify({"valid": False, "reason": "revoked"})

            # Vérifier l'expiration
            expires_at = entry.get("expires_at","")
            if expires_at:
                try:
                    exp_dt = datetime.fromisoformat(expires_at.replace("Z",""))
                    if datetime.utcnow() > exp_dt:
                        entry["status"] = "expired"
                        self.log.info(f"[VAL] Licence expirée : {entry.get('name')}")
                        return jsonify({"valid": False, "reason": "expired",
                                         "expired_at": expires_at})
                except Exception:
                    pass

            # Enregistrer la machine
            if not self.db.register_machine(key, machine_id):
                self.log.warning(f"[VAL] Trop de machines pour {entry.get('name')}")
                return jsonify({"valid": False, "reason": "too_many_machines",
                                 "max": MAX_MACHINES_PER_KEY})

            self.log.info(
                f"[VAL] ✓ {entry.get('name')} | machine={machine_id[:16]} | "
                f"app={app_version}"
            )
            return jsonify({
                "valid":      True,
                "name":       entry.get("name"),
                "expires_at": expires_at,
                "days_left":  self._days_left(expires_at),
            })

        @app.route("/revoke", methods=["POST"])
        def revoke():
            data      = request.get_json(silent=True) or {}
            admin_key = data.get("admin_key", "")
            if not self._check_admin(admin_key):
                return jsonify({"error": "Unauthorized"}), 403
            key = data.get("key", "")
            ok  = self.db.revoke(key)
            if ok:
                self.log.info(f"[REVOKE] Clé révoquée par admin")
            return jsonify({"revoked": ok})

        @app.route("/status")
        def status():
            """JSON pour monitoring programmatique."""
            admin_key = request.args.get("admin_key","")
            if not self._check_admin(admin_key):
                return jsonify({"error": "Unauthorized"}), 403
            licences = self.db.all_licences()
            return jsonify({
                "total":    len(licences),
                "active":   sum(1 for l in licences.values() if l["status"]=="active"),
                "expired":  sum(1 for l in licences.values() if l["status"]=="expired"),
                "revoked":  sum(1 for l in licences.values() if l["status"]=="revoked"),
                "licences": {k: {**v, "key_preview": k[:20]+"…"}
                              for k, v in licences.items()},
            })

        @app.route("/dashboard")
        def dashboard():
            """Dashboard web mobile pour Samsung S10+."""
            admin_key = request.args.get("admin_key","")
            # En local, on peut afficher sans clé
            is_local  = request.remote_addr in ("127.0.0.1","::1")
            if not is_local and not self._check_admin(admin_key):
                return "<h2>⛔ Accès refusé — ajoute ?admin_key=TA_CLE à l'URL</h2>", 403

            licences_raw = self.db.all_licences()
            licences_display = []
            for key, lic in licences_raw.items():
                status = lic.get("status","unknown")
                status_class = {"active":"active","expired":"expired",
                                 "revoked":"revoked"}.get(status,"info")
                days = self._days_left(lic.get("expires_at",""))
                expires_str = (
                    lic.get("expires_at","")[:10] if lic.get("expires_at") else "?"
                )
                licences_display.append({
                    "key":           key,
                    "name":          lic.get("name","?"),
                    "status":        status.upper(),
                    "status_class":  status_class,
                    "expires":       expires_str,
                    "machine_count": len(lic.get("machines",[])),
                    "days_left":     days,
                })

            stats = {
                "total":    len(licences_raw),
                "active":   sum(1 for l in licences_raw.values() if l["status"]=="active"),
                "expired":  sum(1 for l in licences_raw.values() if l["status"]=="expired"),
                "machines": sum(len(l.get("machines",[])) for l in licences_raw.values()),
            }

            return render_template_string(
                DASHBOARD_HTML,
                licences=licences_display,
                stats=stats,
                server_time=datetime.now().strftime("%d/%m/%Y %H:%M")
            )

    def _days_left(self, expires_at: str) -> int:
        if not expires_at:
            return 0
        try:
            exp = datetime.fromisoformat(expires_at.replace("Z",""))
            delta = exp - datetime.utcnow()
            return max(0, delta.days)
        except Exception:
            return 0

    def run(self, host: str = "0.0.0.0", port: int = SERVER_PORT,
             debug: bool = False):
        """Démarre le serveur."""
        import socket
        local_ip = socket.gethostbyname(socket.gethostname())

        print("\n" + "═"*60)
        print(f"  ⬡ Ov3rLoRd Licence Server — v1.0.0-alpha")
        print("═"*60)
        print(f"  Local     : http://localhost:{port}/dashboard")
        print(f"  Réseau    : http://{local_ip}:{port}/dashboard")
        print(f"  S10+ WiFi : http://{local_ip}:{port}/dashboard")
        print(f"\n  Pour accès internet (ngrok) :")
        print(f"  → ngrok http {port}")
        print(f"  → Copie l'URL https://xxx.ngrok.io")
        print("═"*60 + "\n")

        self.app.run(host=host, port=port, debug=debug,
                      use_reloader=False, threaded=True)


# ── Script ngrok automatique ──────────────────────────────────────────
def start_ngrok(port: int = SERVER_PORT) -> str | None:
    """Lance ngrok et retourne l'URL publique."""
    import subprocess, time, requests as req
    try:
        subprocess.Popen(
            ["ngrok", "http", str(port)],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL
        )
        time.sleep(2)
        # Récupérer l'URL depuis l'API locale ngrok
        r = req.get("http://localhost:4040/api/tunnels", timeout=5)
        tunnels = r.json().get("tunnels", [])
        for t in tunnels:
            if t.get("proto") == "https":
                url = t["public_url"]
                print(f"\n  🌐 ngrok URL : {url}/dashboard")
                print(f"  📱 Copie sur ton S10+ : {url}/dashboard\n")
                return url
    except Exception as e:
        print(f"  [ngrok] Non disponible : {e}")
        print(f"  → Télécharge depuis https://ngrok.com/download")
    return None


if __name__ == "__main__":
    import sys

    if not FLASK_OK:
        print("pip install flask cryptography")
        sys.exit(1)

    server = LicenceServer()

    # Lancer ngrok en parallèle si disponible
    import shutil
    if shutil.which("ngrok"):
        threading.Thread(
            target=start_ngrok, args=(SERVER_PORT,), daemon=True
        ).start()
    else:
        print(f"\n  📱 Pour accès mobile :")
        print(f"  1. Télécharge ngrok : https://ngrok.com/download")
        print(f"  2. ngrok http {SERVER_PORT}")
        print(f"  3. Copie l'URL https://xxx.ngrok.io sur ton S10+\n")

    server.run()

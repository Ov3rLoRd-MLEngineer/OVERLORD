"""
agents/config_manager.py — Config Centralisée V1.70
Remplace la dépendance exclusive au .env pour les 95+ agents.
Stockage SQLite léger — un seul fichier, zero dépendance externe.
Hiérarchie : defaults < config.db < .env < kwargs runtime
Le .env reste souverain pour les secrets (API keys).

Usage :
    from agents.config_manager import cfg
    steps = cfg.get("comfyui.steps", 50)
    cfg.set("comfyui.steps", 80)
    cfg.set("comfyui.steps", 80, scope="gpu_rtx5080")
"""

import json
import logging
import os
import sqlite3
import sys
import threading
from pathlib import Path
from datetime import datetime

_REPO_ROOT = Path(__file__).resolve().parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))
from config import COMFYUI_OUTPUT

DB_PATH   = Path("workspace/config.db")
ENV_PATH  = Path(".env")
log       = logging.getLogger("config_manager")

# ── Valeurs par défaut complètes ─────────────────────────────────────
DEFAULTS = {
    # LLM
    "llm.mode":           "offline",
    "llm.ollama_model":   "mistral",
    "llm.max_tokens":     4000,
    "llm.timeout":        120,
    # ComfyUI
    "comfyui.url":        "http://127.0.0.1:8188",
    "comfyui.steps":      50,
    "comfyui.cfg":        6.0,
    "comfyui.sampler":    "dpmpp_2m",
    "comfyui.scheduler":  "karras",
    "comfyui.width":      1024,
    "comfyui.height":     1536,
    "comfyui.vae":        "taesdxl",
    "comfyui.checkpoint": "fabricatedXL_v70.safetensors",
    "comfyui.output_dir": str(COMFYUI_OUTPUT),
    "comfyui.max_retries": 3,
    "comfyui.retry_delay": 5,
    # Production
    "production.batch_size":        8,
    "production.sharpness_threshold": 80.0,
    "production.archive_dir":       "workspace/archive",
    # LoRas
    "loras.available": json.dumps([
        "asuka-langley-soryuu-classic-ponyxl-lora-nochekaiser.safetensors",
        "mari-makinami-rebuild-ponyxl-lora-nochekaiser.safetensors",
        "rei-ayanami-classic-ponyxl-lora-nochekaiser.safetensors",
    ]),
    "loras.default_strength":     0.9,
    "loras.det_strength":         0.8,
    # Pipeline
    "pipeline.media_type":        "anime",
    "pipeline.duration":          "short",
    "pipeline.quality_threshold": 73,
    "pipeline.use_prompt_engineer": True,
    "pipeline.use_quality_gate":    True,
    "pipeline.use_prompt_library":  False,
    # Prompt engineering
    "prompt.default_negative": (
        "bad quality, worst quality, bad anatomy, deformed, blurry, "
        "extra limbs, bad hands, mutated hands, fused fingers, "
        "text, watermark, logo, censored, artist name, signature"
    ),
    # Post-production
    "postprod.export_preset": "anime_1080p",
    "postprod.fps":           24,
    "postprod.frame_duration": 3,
    "postprod.tts_lang":      "fr",
    # GPU profiles (surcharges par scope)
    "gpu.detected":           "unknown",
    "gpu.vram_gb":            8,
    # Auto sourcing
    "sourcing.loop_interval": 3600,
    "sourcing.prompts_per_cycle": 5,
    "sourcing.max_library_size":  100,
    # Telegram
    "telegram.token":   "",
    "telegram.chat_id": "",
    # Reporting
    "reporter.enabled":      True,
    "reporter.history_size": 50,
}

# Presets GPU — surcharges automatiques selon GPU détecté
GPU_PRESETS = {
    "rtx2070": {
        "comfyui.steps":  50,
        "comfyui.width":  1024,
        "comfyui.height": 1536,
        "comfyui.cfg":    6.0,
    },
    "rtx3080": {
        "comfyui.steps":  65,
        "comfyui.width":  1152,
        "comfyui.height": 1728,
        "comfyui.cfg":    6.5,
    },
    "rtx4080": {
        "comfyui.steps":  70,
        "comfyui.width":  1216,
        "comfyui.height": 1824,
        "comfyui.cfg":    6.5,
    },
    "rtx5080": {
        "comfyui.steps":  80,
        "comfyui.width":  1344,
        "comfyui.height": 1984,
        "comfyui.cfg":    7.0,
        "comfyui.vae":    "sdxl_vae.safetensors",
    },
    "rtx5090": {
        "comfyui.steps":  100,
        "comfyui.width":  1536,
        "comfyui.height": 2304,
        "comfyui.cfg":    7.0,
        "comfyui.vae":    "sdxl_vae.safetensors",
    },
}


class ConfigManager:
    """Gestionnaire de configuration centralisé thread-safe."""

    def __init__(self, db_path: Path = DB_PATH):
        self._db   = db_path
        self._lock = threading.Lock()
        self._cache: dict = {}
        self._init_db()
        self._load_env_overrides()

    def _init_db(self):
        self._db.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS config (
                    key        TEXT NOT NULL,
                    value      TEXT,
                    scope      TEXT DEFAULT 'global',
                    updated_at TEXT,
                    PRIMARY KEY (key, scope)
                )
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS config_history (
                    id         INTEGER PRIMARY KEY AUTOINCREMENT,
                    key        TEXT,
                    old_value  TEXT,
                    new_value  TEXT,
                    scope      TEXT,
                    changed_at TEXT
                )
            """)
            # Insérer les defaults si absents
            for key, val in DEFAULTS.items():
                conn.execute(
                    "INSERT OR IGNORE INTO config (key, value, scope, updated_at) "
                    "VALUES (?, ?, 'global', ?)",
                    (key, str(val), datetime.now().isoformat())
                )

    def _connect(self):
        return sqlite3.connect(str(self._db), check_same_thread=False)

    def _load_env_overrides(self):
        """Charge les variables .env et les mappe vers les clés config."""
        env_map = {
            "OV_LLM_MODE":       "llm.mode",
            "OV_OLLAMA_MODEL":   "llm.ollama_model",
            "TELEGRAM_TOKEN":    "telegram.token",
            "TELEGRAM_CHAT_ID":  "telegram.chat_id",
        }
        env_vals = {}
        if ENV_PATH.exists():
            for line in ENV_PATH.read_text(encoding="utf-8").splitlines():
                line = line.strip()
                if "=" in line and not line.startswith("#"):
                    k, v = line.split("=", 1)
                    env_vals[k.strip()] = v.strip().strip('"').strip("'")

        for env_key, cfg_key in env_map.items():
            val = os.environ.get(env_key) or env_vals.get(env_key)
            if val:
                self._cache[cfg_key] = val

    def get(self, key: str, default=None, scope: str = "global"):
        """Lit une valeur. Hiérarchie: cache(.env) > DB(scope) > DB(global) > default."""
        if key in self._cache:
            return self._coerce(self._cache[key], default)

        with self._lock:
            with self._connect() as conn:
                # Scope spécifique d'abord
                if scope != "global":
                    row = conn.execute(
                        "SELECT value FROM config WHERE key=? AND scope=?",
                        (key, scope)
                    ).fetchone()
                    if row:
                        return self._coerce(row[0], default)
                # Scope global
                row = conn.execute(
                    "SELECT value FROM config WHERE key=? AND scope='global'",
                    (key,)
                ).fetchone()
                if row:
                    return self._coerce(row[0], default)

        return default

    def set(self, key: str, value, scope: str = "global"):
        """Écrit une valeur avec historique."""
        old = self.get(key, scope=scope)
        str_val = json.dumps(value) if isinstance(value, (list, dict)) else str(value)

        with self._lock:
            with self._connect() as conn:
                conn.execute(
                    "INSERT OR REPLACE INTO config (key, value, scope, updated_at) "
                    "VALUES (?, ?, ?, ?)",
                    (key, str_val, scope, datetime.now().isoformat())
                )
                conn.execute(
                    "INSERT INTO config_history (key, old_value, new_value, scope, changed_at) "
                    "VALUES (?, ?, ?, ?, ?)",
                    (key, str(old), str_val, scope, datetime.now().isoformat())
                )
        # Invalider le cache
        self._cache.pop(key, None)

    def _coerce(self, raw: str, default):
        """Convertit la valeur string vers le type du default."""
        if raw is None:
            return default
        if default is None:
            return raw
        try:
            if isinstance(default, bool):
                return raw.lower() in ("true", "1", "yes", "on")
            if isinstance(default, int):
                return int(float(raw))
            if isinstance(default, float):
                return float(raw)
            if isinstance(default, list):
                return json.loads(raw)
            return raw
        except Exception:
            return default

    def apply_gpu_preset(self, gpu_name: str):
        """Applique un preset GPU (surcharge les paramètres ComfyUI)."""
        preset = GPU_PRESETS.get(gpu_name.lower().replace(" ", "").replace("rtx", "rtx"))
        if not preset:
            # Cherche par correspondance partielle
            for k, v in GPU_PRESETS.items():
                if k in gpu_name.lower():
                    preset = v
                    break
        if not preset:
            log.warning(f"[CONFIG] Preset GPU inconnu : {gpu_name}")
            return False

        self.set("gpu.detected", gpu_name)
        for key, val in preset.items():
            self.set(key, val, scope=f"gpu_{gpu_name.lower().replace(' ','_')}")
            log.info(f"[CONFIG] GPU preset {gpu_name} : {key} = {val}")

        log.info(f"[CONFIG] Preset GPU {gpu_name} appliqué ({len(preset)} paramètres)")
        return True

    def get_all(self, prefix: str = "", scope: str = "global") -> dict:
        """Retourne toutes les clés (avec préfixe optionnel)."""
        with self._lock:
            with self._connect() as conn:
                rows = conn.execute(
                    "SELECT key, value FROM config WHERE scope=? AND key LIKE ?",
                    (scope, f"{prefix}%" if prefix else "%")
                ).fetchall()
        return {k: v for k, v in rows}

    def export_json(self) -> dict:
        """Exporte la config complète en dict."""
        return self.get_all()

    def history(self, key: str, n: int = 10) -> list:
        """Retourne les N dernières modifications d'une clé."""
        with self._lock:
            with self._connect() as conn:
                rows = conn.execute(
                    "SELECT old_value, new_value, scope, changed_at "
                    "FROM config_history WHERE key=? ORDER BY id DESC LIMIT ?",
                    (key, n)
                ).fetchall()
        return [{"old": r[0], "new": r[1], "scope": r[2], "at": r[3]} for r in rows]


# Singleton global
_cfg_instance: ConfigManager | None = None
_cfg_lock = threading.Lock()

def get_config() -> ConfigManager:
    global _cfg_instance
    with _cfg_lock:
        if _cfg_instance is None:
            _cfg_instance = ConfigManager()
    return _cfg_instance

# Alias court
cfg = get_config()


if __name__ == "__main__":
    import sys, io
    if hasattr(sys.stdout, "buffer"):
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    logging.basicConfig(level=logging.INFO)

    c = get_config()
    print("=== Config Manager V1.70 ===")
    print(f"DB        : {DB_PATH}")
    print(f"Steps     : {c.get('comfyui.steps', 50)}")
    print(f"Sampler   : {c.get('comfyui.sampler', '?')}")
    print(f"LLM mode  : {c.get('llm.mode', '?')}")
    print(f"LoRas     : {c.get('loras.available', [])[:1]}")

    print("\n=== Test preset RTX 5080 ===")
    c.apply_gpu_preset("rtx5080")
    print(f"Steps après preset : {c.get('comfyui.steps', 50, scope='gpu_rtx5080')}")
    print(f"Width après preset : {c.get('comfyui.width', 1024, scope='gpu_rtx5080')}")

    print("\n=== Toutes les clés comfyui ===")
    for k, v in sorted(c.get_all("comfyui").items()):
        print(f"  {k} = {v}")

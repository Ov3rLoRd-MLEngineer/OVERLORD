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
agents/error_recovery.py — Récupération Automatique sur Crash V1.47
Détecte et corrige automatiquement les pannes ComfyUI, mémoire GPU, etc.
S'intègre dans watchdog.py et maestro.py.

Usage :
    from agents.error_recovery import ErrorRecovery
    recovery = ErrorRecovery()
    fixed = recovery.handle(error_type="comfyui_crash", context={})
"""

import json
import logging
import requests
import subprocess
import sys
import time
from pathlib import Path
from datetime import datetime
from enum import Enum

try:
    from agents.overlord_utils import fallback_llm, safe_json_parse
    UTILS_OK = True
except ImportError:
    UTILS_OK = False

log = logging.getLogger("error_recovery")
RECOVERY_DIR  = Path("workspace/recovery")
COMFY_URL     = "http://127.0.0.1:8188"
BASE_DIR      = Path(__file__).resolve().parent.parent

class ErrorType(Enum):
    COMFYUI_CRASH       = "comfyui_crash"
    COMFYUI_FREEZE      = "comfyui_freeze"
    GPU_OOM             = "gpu_oom"
    API_RATE_LIMIT      = "api_rate_limit"
    API_UNAVAILABLE     = "api_unavailable"
    CHECKPOINT_MISSING  = "checkpoint_missing"
    WORKFLOW_ERROR      = "workflow_error"
    DISK_FULL           = "disk_full"
    PYTHON_CRASH        = "python_crash"
    UNKNOWN             = "unknown"

class RecoveryAction(Enum):
    RESTART_COMFYUI   = "restart_comfyui"
    CLEAR_GPU_CACHE   = "clear_gpu_cache"
    SWITCH_TO_OLLAMA  = "switch_to_ollama"
    REDUCE_RESOLUTION = "reduce_resolution"
    CLEAN_DISK        = "clean_disk"
    RELOAD_WORKFLOW   = "reload_workflow"
    WAIT_AND_RETRY    = "wait_and_retry"
    SKIP_AND_CONTINUE = "skip_and_continue"
    HALT              = "halt"


RECOVERY_STRATEGIES = {
    ErrorType.COMFYUI_CRASH: [
        RecoveryAction.RESTART_COMFYUI,
        RecoveryAction.CLEAR_GPU_CACHE,
        RecoveryAction.WAIT_AND_RETRY,
    ],
    ErrorType.COMFYUI_FREEZE: [
        RecoveryAction.RESTART_COMFYUI,
        RecoveryAction.WAIT_AND_RETRY,
    ],
    ErrorType.GPU_OOM: [
        RecoveryAction.CLEAR_GPU_CACHE,
        RecoveryAction.REDUCE_RESOLUTION,
        RecoveryAction.RESTART_COMFYUI,
    ],
    ErrorType.API_RATE_LIMIT: [
        RecoveryAction.WAIT_AND_RETRY,
        RecoveryAction.SWITCH_TO_OLLAMA,
    ],
    ErrorType.API_UNAVAILABLE: [
        RecoveryAction.SWITCH_TO_OLLAMA,
        RecoveryAction.WAIT_AND_RETRY,
    ],
    ErrorType.CHECKPOINT_MISSING: [
        RecoveryAction.RELOAD_WORKFLOW,
        RecoveryAction.SKIP_AND_CONTINUE,
    ],
    ErrorType.DISK_FULL: [
        RecoveryAction.CLEAN_DISK,
        RecoveryAction.HALT,
    ],
}


class ErrorRecovery:
    def __init__(self, logger: logging.Logger = None):
        self.log      = logger or log
        self._history = []
        RECOVERY_DIR.mkdir(parents=True, exist_ok=True)

    def detect_error(self, error_message: str, context: dict = None) -> ErrorType:
        """Classifie l'erreur depuis le message."""
        msg = error_message.lower()
        if any(k in msg for k in ["cuda out of memory","oom","out of memory"]):
            return ErrorType.GPU_OOM
        if any(k in msg for k in ["connection refused","comfyui","http 503"]):
            return ErrorType.COMFYUI_CRASH
        if "rate limit" in msg or "429" in msg:
            return ErrorType.API_RATE_LIMIT
        if any(k in msg for k in ["401","402","credit","api","anthropic"]):
            return ErrorType.API_UNAVAILABLE
        if any(k in msg for k in ["checkpoint","model not found","safetensors"]):
            return ErrorType.CHECKPOINT_MISSING
        if "disk" in msg or "no space" in msg or "enospc" in msg:
            return ErrorType.DISK_FULL
        if "freeze" in msg or "timeout" in msg or "hung" in msg:
            return ErrorType.COMFYUI_FREEZE
        return ErrorType.UNKNOWN

    def handle(self, error_message: str, context: dict = None,
               max_attempts: int = 3) -> dict:
        """
        Gère une erreur avec récupération automatique.
        Retourne : {"resolved": bool, "action": str, "context": dict}
        """
        error_type = self.detect_error(error_message, context)
        strategies = RECOVERY_STRATEGIES.get(error_type, [RecoveryAction.WAIT_AND_RETRY])
        context    = context or {}

        self.log.warning(f"[RECOVERY] Erreur détectée : {error_type.value}")

        for attempt, action in enumerate(strategies[:max_attempts], 1):
            self.log.info(f"[RECOVERY] Tentative {attempt} : {action.value}")
            success, new_context = self._execute_action(action, context)

            self._log_attempt(error_type, action, success)

            if success:
                self.log.info(f"[RECOVERY] ✓ Résolu via {action.value}")
                return {"resolved": True, "action": action.value,
                        "context": {**context, **new_context}}

            time.sleep(min(5 * attempt, 30))  # backoff

        self.log.error(f"[RECOVERY] ✗ Non résolu après {len(strategies)} tentatives")
        return {"resolved": False, "action": RecoveryAction.HALT.value, "context": context}

    def _execute_action(self, action: RecoveryAction, context: dict) -> tuple:
        """Exécute une action de récupération. Retourne (success, new_context)."""
        try:
            if action == RecoveryAction.RESTART_COMFYUI:
                return self._restart_comfyui(), {}

            elif action == RecoveryAction.CLEAR_GPU_CACHE:
                return self._clear_gpu_cache(), {}

            elif action == RecoveryAction.SWITCH_TO_OLLAMA:
                return True, {"preferred_llm": "ollama/llama3", "api_fallback": True}

            elif action == RecoveryAction.REDUCE_RESOLUTION:
                w = max(512, context.get("width", 1024) // 2)
                h = max(288, context.get("height", 576) // 2)
                self.log.info(f"[RECOVERY] Résolution réduite → {w}x{h}")
                return True, {"width": w, "height": h, "resolution_reduced": True}

            elif action == RecoveryAction.WAIT_AND_RETRY:
                wait = context.get("wait_time", 30)
                self.log.info(f"[RECOVERY] Attente {wait}s...")
                time.sleep(wait)
                return self._check_comfyui(), {}

            elif action == RecoveryAction.CLEAN_DISK:
                freed = self._clean_temp_files()
                self.log.info(f"[RECOVERY] {freed:.1f} Mo libérés")
                return freed > 100, {"freed_mb": freed}

            elif action == RecoveryAction.RELOAD_WORKFLOW:
                return self._reload_workflow(context), {}

            elif action == RecoveryAction.SKIP_AND_CONTINUE:
                return True, {"skipped": True}

            elif action == RecoveryAction.HALT:
                return False, {}

        except Exception as e:
            self.log.error(f"[RECOVERY] Action {action.value} échouée : {e}")
        return False, {}

    def _restart_comfyui(self) -> bool:
        """Tente de redémarrer ComfyUI."""
        comfy_cfg = BASE_DIR / "comfy_path.cfg"
        if not comfy_cfg.exists():
            return False
        try:
            comfy_path = ""
            for line in comfy_cfg.read_text().splitlines():
                if line.startswith("COMFY_PATH="):
                    comfy_path = line.split("=",1)[1].strip()
            if not comfy_path:
                return False
            main_py = Path(comfy_path) / "main.py"
            if not main_py.exists():
                return False
            subprocess.Popen(
                [sys.executable, str(main_py),
                 "--disable-smart-memory","--normalvram","--cpu-vae",
                 "--preview-method","none","--disable-auto-launch"],
                cwd=comfy_path
            )
            time.sleep(8)
            return self._check_comfyui()
        except Exception as e:
            self.log.error(f"[RECOVERY] Restart ComfyUI : {e}")
            return False

    def _clear_gpu_cache(self) -> bool:
        """Vide le cache GPU via ComfyUI free_memory endpoint."""
        try:
            r = requests.post(f"{COMFY_URL}/free", json={"unload_models":True,"free_memory":True}, timeout=10)
            if r.status_code == 200:
                self.log.info("[RECOVERY] Cache GPU vidé")
                time.sleep(3)
                return True
        except Exception:
            pass
        return False

    def _check_comfyui(self) -> bool:
        try:
            r = requests.get(f"{COMFY_URL}/system_stats", timeout=5)
            return r.status_code == 200
        except Exception:
            return False

    def _clean_temp_files(self) -> float:
        """Nettoie les fichiers temporaires. Retourne Mo libérés."""
        freed = 0
        temp_dirs = [
            BASE_DIR / "workspace" / "radio_cache",
            BASE_DIR / "workspace" / "audio_cache",
        ]
        import shutil
        for d in temp_dirs:
            if d.exists():
                for f in d.glob("*"):
                    if f.is_file():
                        try:
                            size = f.stat().st_size
                            f.unlink()
                            freed += size
                        except Exception:
                            pass
        return freed / 1e6

    def _reload_workflow(self, context: dict) -> bool:
        """Tente de recharger le workflow avec autoconfig."""
        try:
            from agents.comfy_autoconfig import run_autoconfig
            result = run_autoconfig(logger=self.log)
            return result.get("updated", 0) > 0 or len(result.get("models",{}).get("checkpoints",[])) > 0
        except Exception:
            return False

    def _log_attempt(self, error_type: ErrorType, action: RecoveryAction, success: bool):
        entry = {
            "timestamp": datetime.now().isoformat(),
            "error":     error_type.value,
            "action":    action.value,
            "success":   success,
        }
        self._history.append(entry)
        log_path = RECOVERY_DIR / "recovery_log.jsonl"
        with open(log_path, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry) + "\n")

    def get_stats(self) -> dict:
        success_rate = (
            sum(1 for e in self._history if e["success"]) / len(self._history)
            if self._history else 0
        )
        return {
            "total_attempts":  len(self._history),
            "success_rate":    round(success_rate * 100, 1),
            "recent":          self._history[-5:],
        }


def get_recovery() -> ErrorRecovery:
    """Singleton pour maestro.py et watchdog.py."""
    return ErrorRecovery()


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    rec = ErrorRecovery()
    for error in ["CUDA out of memory","rate limit exceeded","ComfyUI connection refused"]:
        result = rec.handle(error, context={"width":1024,"height":576})
        print(f"  '{error[:30]}' → resolved={result['resolved']} action={result['action']}")

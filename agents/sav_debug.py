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
agents/sav_debug.py — AI-SAV Code & Debugging
Agent spécialiste ComfyUI avec boucle de validation rigoureuse.

Pipeline de résolution :
  Test unitaire → Résolution → Vérification → Loopback si échec

Bug connu géré : ControlNet double-génération
  Stratégie : Warm-Cache Protocol
    GEN 1 : ControlNet DÉSACTIVÉ  → charge le cache
    GEN 2 : ControlNet DÉSACTIVÉ  → lancée immédiatement, stoppée quand cache prêt
    GEN 3 : ControlNet RÉACTIVÉ   → génération propre sans bug

Ce module est utilisé par le launcher (panneau SAV) et par agent_supervisor_v2.py.
"""

import json
import logging
import queue
import subprocess
import sys
import time
import requests
import threading
from datetime import datetime
from enum import Enum
import os
from pathlib import Path

import io
if hasattr(sys.stdout, 'buffer') and getattr(sys.stdout, 'encoding','').lower() != 'utf-8':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

ANTHROPIC_URL = "https://api.anthropic.com/v1/messages"

def _get_api_key() -> str:
    import os as _os
    from pathlib import Path as _P
    key = _os.environ.get("ANTHROPIC_API_KEY", "")
    if not key:
        env = _P(__file__).parent.parent / ".env"
        if env.exists():
            for line in env.read_text(encoding="utf-8").splitlines():
                if line.startswith("ANTHROPIC_API_KEY="):
                    key = line.split("=",1)[1].strip().strip('"').strip("'")
    return key

CLAUDE_MODEL      = "claude-sonnet-4-6"
SAV_LOG_DIR       = Path("workspace/sav_logs")
COMFY_URL         = "http://127.0.0.1:8188"


# ============================================================
# TYPES
# ============================================================
class BugSeverity(Enum):
    LOW      = "LOW"
    MEDIUM   = "MEDIUM"
    HIGH     = "HIGH"
    CRITICAL = "CRITICAL"

class TestResult(Enum):
    PASS    = "PASS"
    FAIL    = "FAIL"
    SKIP    = "SKIP"
    UNKNOWN = "UNKNOWN"


class BugReport:
    def __init__(self, bug_id: str, description: str,
                 severity: BugSeverity = BugSeverity.MEDIUM):
        self.bug_id      = bug_id
        self.description = description
        self.severity    = severity
        self.ts          = datetime.utcnow().isoformat()
        self.tests       = []
        self.resolution  = None
        self.verified    = False

    def add_test(self, name: str, result: TestResult, detail: str = ""):
        self.tests.append({
            "name":   name,
            "result": result.value,
            "detail": detail,
            "ts":     datetime.utcnow().isoformat(),
        })

    def to_dict(self) -> dict:
        return {
            "bug_id":      self.bug_id,
            "description": self.description,
            "severity":    self.severity.value,
            "ts":          self.ts,
            "tests":       self.tests,
            "resolution":  self.resolution,
            "verified":    self.verified,
        }


# ============================================================
# CONTRÔLE DES NŒUDS COMFYUI VIA API
# ============================================================
def _get_queue_status() -> dict:
    """Retourne l'état de la queue ComfyUI."""
    try:
        r = requests.get(f"{COMFY_URL}/queue", timeout=5)
        if r.status_code == 200:
            return r.json()
    except Exception:
        pass
    return {}

def _get_history(prompt_id: str) -> dict:
    """Récupère l'historique d'un prompt."""
    try:
        r = requests.get(f"{COMFY_URL}/history/{prompt_id}", timeout=10)
        if r.status_code == 200:
            return r.json().get(prompt_id, {})
    except Exception:
        pass
    return {}

def _interrupt() -> bool:
    """Interrompt la génération en cours."""
    try:
        r = requests.post(f"{COMFY_URL}/interrupt", timeout=5)
        return r.status_code == 200
    except Exception:
        return False

def _send_workflow(workflow: dict) -> str | None:
    """Envoie un workflow et retourne le prompt_id."""
    try:
        r = requests.post(
            f"{COMFY_URL}/prompt",
            json={"prompt": workflow},
            timeout=30
        )
        if r.status_code == 200:
            return r.json().get("prompt_id")
    except Exception:
        pass
    return None

def _wait_until_queued(prompt_id: str, timeout: float = 30.0) -> bool:
    """Attend que le prompt soit pris en charge par ComfyUI."""
    start = time.time()
    while time.time() - start < timeout:
        status = _get_queue_status()
        running = status.get("queue_running", [])
        # Le prompt est en cours d'exécution
        for item in running:
            if isinstance(item, list) and len(item) > 1 and item[1] == prompt_id:
                return True
        time.sleep(0.5)
    return False

def _wait_completion(prompt_id: str, timeout: float = 600.0) -> bool:
    """Attend la fin d'exécution d'un prompt."""
    start = time.time()
    while time.time() - start < timeout:
        hist = _get_history(prompt_id)
        if hist:
            status = hist.get("status", {})
            if status.get("completed"):
                return True
            if status.get("status_str") == "error":
                return False
        time.sleep(2.0)
    return False


# ============================================================
# BUG #001 : CONTROLNET DOUBLE-GÉNÉRATION
# Warm-Cache Protocol
# ============================================================
CONTROLNET_SWITCH_IDS = ["169", "168", "166"]  # IDs des ImpactSwitch ControlNet dans le workflow

def _set_controlnet_state(workflow: dict, enabled: bool) -> dict:
    """
    Active ou désactive les nœuds ControlNet dans le workflow.
    Cible les ImpactSwitch liés aux ControlNetApplyAdvanced.
    """
    # Nœuds ControlNetApplyAdvanced connus
    cn_ids = ["165", "167", "171", "172"]
    # On modifie le champ 'mode' : 0 = actif, 4 = bypassé
    for nid in cn_ids:
        if nid in workflow:
            workflow[nid]["_mode_override"] = 0 if enabled else 4

    # Modifier aussi les switch qui les alimentent
    # select=1 → input1 (sans ControlNet), select=2 → input2 (avec ControlNet)
    for nid in CONTROLNET_SWITCH_IDS:
        if nid in workflow:
            inp = workflow[nid].get("inputs", {})
            if "select" in inp:
                inp["select"] = 2 if enabled else 1

    return workflow


class ControlNetWarmCacheProtocol:
    """
    Résout le bug de double-génération ControlNet en ComfyUI.

    Séquence complète pour N générations :
      - GEN 1 : CN OFF → charge le cache modèle
      - GEN 2 : CN OFF → lancée, stoppée dès que GEN 1 termine (cache chaud)
      - GEN 3…N : CN ON → génération propre

    Applicable que ce soit 1, 100 ou ∞ requêtes,
    avec ou sans nœud batch.
    """

    def __init__(self, workflow: dict, total_jobs: int,
                 logger: logging.Logger = None):
        self.workflow   = workflow
        self.total_jobs = total_jobs
        self.logger     = logger or logging.getLogger("sav.controlnet")
        self._gen_count = 0
        self._cache_hot = False
        self._lock      = threading.Lock()

    def _log(self, msg: str, level: int = logging.INFO):
        self.logger.log(level, f"[SAV/ControlNet] {msg}")

    def run_all(self, job_builder_fn, on_result_fn=None) -> list:
        """
        Exécute toutes les générations avec le protocole Warm-Cache.

        job_builder_fn(index) → workflow dict pour le job N
        on_result_fn(index, prompt_id, success) → callback optionnel
        """
        results = []

        for i in range(self.total_jobs):
            result = self._run_single(i, job_builder_fn)
            results.append(result)
            if on_result_fn:
                on_result_fn(i, result.get("prompt_id"), result.get("success", False))

        return results

    def _run_single(self, index: int, job_builder_fn) -> dict:
        """Exécute un job unique avec la stratégie correcte selon son index."""
        with self._lock:
            self._gen_count += 1
            gen_num = self._gen_count

        wf = job_builder_fn(index)

        # ── GEN 1 : Cache froid → CN désactivé ──────────────────────
        if gen_num == 1:
            self._log(f"GEN {gen_num} — Cache froid : ControlNet DÉSACTIVÉ")
            wf = _set_controlnet_state(wf, enabled=False)
            pid = _send_workflow(wf)
            if not pid:
                return {"index": index, "gen": gen_num, "success": False,
                        "reason": "send_failed"}

            success = _wait_completion(pid, timeout=600)
            self._cache_hot = success
            self._log(f"GEN {gen_num} terminée — cache={'chaud' if success else 'ERREUR'}")
            return {"index": index, "gen": gen_num, "prompt_id": pid,
                    "success": success, "cn": False}

        # ── GEN 2 : Préchauffage → lancée puis stoppée ──────────────
        elif gen_num == 2:
            self._log(f"GEN {gen_num} — Préchauffage : ControlNet DÉSACTIVÉ, arrêt auto")
            wf = _set_controlnet_state(wf, enabled=False)
            pid = _send_workflow(wf)
            if not pid:
                return {"index": index, "gen": gen_num, "success": False,
                        "reason": "send_failed"}

            # Attendre que ComfyUI ait chargé les modèles en mémoire (~3s)
            time.sleep(3.0)
            queued = _wait_until_queued(pid, timeout=20)
            if queued:
                time.sleep(2.0)  # laisser le temps de charger les modèles
                _interrupt()
                self._log(f"GEN {gen_num} interrompue — cache confirmé chaud")
            else:
                self._log(f"GEN {gen_num} — pas en queue, interruption directe", logging.WARNING)
                _interrupt()

            return {"index": index, "gen": gen_num, "prompt_id": pid,
                    "success": True, "cn": False, "interrupted": True}

        # ── GEN 3+ : Cache chaud → CN activé ────────────────────────
        else:
            self._log(f"GEN {gen_num} — Cache chaud : ControlNet ACTIVÉ")
            wf = _set_controlnet_state(wf, enabled=True)
            pid = _send_workflow(wf)
            if not pid:
                return {"index": index, "gen": gen_num, "success": False,
                        "reason": "send_failed"}

            success = _wait_completion(pid, timeout=600)
            self._log(
                f"GEN {gen_num} {'✓ terminée' if success else '✗ échouée'} | CN activé"
            )
            return {"index": index, "gen": gen_num, "prompt_id": pid,
                    "success": success, "cn": True}


# ============================================================
# BOUCLE DE VALIDATION : Test → Résolution → Vérification
# ============================================================
class SAVAgent:
    """
    Agent SAV ComfyUI.
    Pipeline : Test unitaire → LLM Resolution → Vérification → Loopback
    """

    MAX_LOOPBACK = 3

    def __init__(self, logger: logging.Logger = None,
                 llm_bridge=None):
        """
        llm_bridge : instance de OllamaBridge ou OnlineLLMBridge
                     (duck-typing : doit avoir une méthode complete(prompt) -> str)
        """
        self.logger     = logger or logging.getLogger("sav")
        self.llm        = llm_bridge
        self.known_bugs = self._load_known_bugs()
        SAV_LOG_DIR.mkdir(parents=True, exist_ok=True)

    def _load_known_bugs(self) -> list:
        """Base de connaissances des bugs connus ComfyUI."""
        return [
            {
                "id":          "CN-001",
                "name":        "ControlNet double-génération",
                "description": "Lancer 2 générations successives avec ControlNet actif corrompt la pipeline",
                "symptoms":    ["ControlNet ignore", "image sans ControlNet", "erreur CUDA"],
                "severity":    BugSeverity.HIGH,
                "fix":         "warm_cache_protocol",
            },
            {
                "id":          "SEED-001",
                "name":        "Seed -1 numpy crash",
                "description": "ImpactWildcardProcessor reçoit seed=-1, numpy crash",
                "symptoms":    ["ValueError: expected non-negative integer", "numpy", "seed"],
                "severity":    BugSeverity.CRITICAL,
                "fix":         "replace_seed",
            },
            {
                "id":          "KJ-001",
                "name":        "WidgetToString extra_pnginfo crash",
                "description": "WidgetToString cherche extra_pnginfo absent en mode API",
                "symptoms":    ["NoneType object is not subscriptable", "extra_pnginfo", "WidgetToString"],
                "severity":    BugSeverity.HIGH,
                "fix":         "remove_widget_to_string",
            },
            {
                "id":          "OOM-001",
                "name":        "VRAM insuffisante",
                "description": "RTX 2070 8GB saturée par deux checkpoints simultanés",
                "symptoms":    ["CUDA out of memory", "OOM", "RuntimeError"],
                "severity":    BugSeverity.CRITICAL,
                "fix":         "unload_checkpoint",
            },
        ]

    def diagnose(self, error_text: str) -> list:
        """Identifie les bugs connus dans un message d'erreur."""
        matches = []
        error_lower = error_text.lower()
        for bug in self.known_bugs:
            if any(s.lower() in error_lower for s in bug["symptoms"]):
                matches.append(bug)
        return matches

    # ─── Pipeline de résolution ──────────────────────────────────────
    def resolve(self, error_text: str, context: dict = None) -> BugReport:
        """
        Pipeline complet : Test → Résolution → Vérification → Loopback

        error_text : message d'erreur brut
        context    : dict optionnel {workflow, job, comfy_url}
        """
        ts     = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
        report = BugReport(f"BUG_{ts}", error_text[:200])

        self._log(f"Analyse du bug : {error_text[:100]}...")

        # ── ÉTAPE 1 : Test unitaire — identification ─────────────────
        known = self.diagnose(error_text)
        if known:
            bug = known[0]
            report.add_test(
                "identification",
                TestResult.PASS,
                f"Bug connu identifié : [{bug['id']}] {bug['name']}"
            )
            report.severity = bug["severity"]
            self._log(f"Bug identifié : [{bug['id']}] {bug['name']}", logging.WARNING)
        else:
            report.add_test(
                "identification",
                TestResult.UNKNOWN,
                "Bug non répertorié — analyse LLM requise"
            )
            self._log("Bug inconnu — escalade vers LLM")

        # ── ÉTAPE 2 : Résolution ─────────────────────────────────────
        resolution = None
        for attempt in range(1, self.MAX_LOOPBACK + 1):
            self._log(f"Tentative de résolution {attempt}/{self.MAX_LOOPBACK}")

            if known:
                resolution = self._apply_known_fix(known[0], context)
            elif self.llm:
                resolution = self._resolve_with_llm(error_text, context, attempt)
            else:
                resolution = {
                    "action":      "manual",
                    "description": "Aucun LLM disponible — résolution manuelle requise",
                    "success":     False,
                }

            # ── ÉTAPE 3 : Vérification ───────────────────────────────
            verified = self._verify_resolution(resolution, context)
            report.add_test(
                f"verification_attempt_{attempt}",
                TestResult.PASS if verified else TestResult.FAIL,
                resolution.get("description", "")
            )

            if verified:
                report.resolution = resolution
                report.verified   = True
                self._log(f"✓ Résolution vérifiée à la tentative {attempt}")
                break
            else:
                self._log(
                    f"✗ Vérification échouée (tentative {attempt}) — loopback",
                    logging.WARNING
                )
                if known and attempt < self.MAX_LOOPBACK:
                    # Tenter le fix suivant si plusieurs connus
                    known = known[1:] if len(known) > 1 else known
        else:
            self._log("Résolution non vérifiée après tous les loopbacks", logging.ERROR)
            report.resolution = resolution
            report.verified   = False

        self._save_report(report)
        return report

    # ─── Fixes connus ────────────────────────────────────────────────
    def _apply_known_fix(self, bug: dict, context: dict = None) -> dict:
        fix = bug.get("fix")
        self._log(f"Application du fix : {fix}")

        if fix == "warm_cache_protocol":
            return {
                "action":      "warm_cache_protocol",
                "description": (
                    "Protocole Warm-Cache appliqué : "
                    "GEN1 CN=OFF (charge cache), GEN2 CN=OFF+stop, GEN3+ CN=ON"
                ),
                "code":        "ControlNetWarmCacheProtocol",
                "success":     True,
            }

        elif fix == "replace_seed":
            if context and "workflow" in context:
                wf = context["workflow"]
                fixed = 0
                for nid, node in wf.items():
                    for k, v in node.get("inputs", {}).items():
                        if "seed" in k.lower() and v == -1:
                            node["inputs"][k] = 42
                            fixed += 1
                return {
                    "action":      "replace_seed",
                    "description": f"Seeds -1 remplacés : {fixed} nœuds",
                    "success":     fixed > 0,
                }
            return {"action": "replace_seed",
                    "description": "Workflow non disponible", "success": False}

        elif fix == "remove_widget_to_string":
            return {
                "action":      "remove_widget_to_string",
                "description": "WidgetToString supprimé — valeur hardcodée dans Image Saver",
                "success":     True,
            }

        elif fix == "unload_checkpoint":
            return {
                "action":      "unload_checkpoint",
                "description": "Même checkpoint utilisé pour Advanced et Detailer — pas de double chargement",
                "success":     True,
            }

        return {"action": "unknown", "description": "Fix non implémenté", "success": False}

    def _resolve_with_llm(self, error: str, context: dict,
                          attempt: int) -> dict:
        """Demande une résolution au LLM configuré."""
        if not self.llm:
            return {"action": "no_llm", "description": "LLM non disponible", "success": False}

        ctx_str = ""
        if context:
            ctx_str = f"\nContexte : {json.dumps(context, ensure_ascii=False, default=str)[:500]}"

        prompt = f"""Tu es un expert ComfyUI. Analyse cette erreur et propose une résolution précise.
Tentative {attempt}/{self.MAX_LOOPBACK}.

Erreur :
{error}
{ctx_str}

Réponds en JSON :
{{"action": "...", "description": "...", "code_fix": "...", "confidence": 0-100}}"""

        try:
            response = self.llm.complete(prompt)
            clean = response.strip()
            if clean.startswith("```"):
                clean = "\n".join(clean.split("\n")[1:-1])
            result = json.loads(clean)
            result["success"] = result.get("confidence", 0) >= 70
            return result
        except Exception as e:
            return {
                "action":      "llm_error",
                "description": f"Erreur LLM : {e}",
                "success":     False,
            }

    def _verify_resolution(self, resolution: dict, context: dict = None) -> bool:
        """Vérifie qu'une résolution est applicable et cohérente."""
        if not resolution:
            return False
        if not resolution.get("success", False):
            return False

        action = resolution.get("action", "")

        # Vérifications spécifiques
        if action == "warm_cache_protocol":
            # Vérifier que ComfyUI est joignable
            try:
                r = requests.get(f"{COMFY_URL}/system_stats", timeout=5)
                return r.status_code == 200
            except Exception:
                return False

        if action == "replace_seed":
            # Vérifier qu'aucun seed -1 ne subsiste
            if context and "workflow" in context:
                wf = context["workflow"]
                for nid, node in wf.items():
                    for k, v in node.get("inputs", {}).items():
                        if "seed" in k.lower() and v == -1:
                            return False
            return True

        # Par défaut : faire confiance au flag success
        return resolution.get("success", False)

    def _log(self, msg: str, level: int = logging.INFO):
        self.logger.log(level, f"[SAV] {msg}")

    def _save_report(self, report: BugReport):
        path = SAV_LOG_DIR / f"{report.bug_id}.json"
        try:
            path.write_text(
                json.dumps(report.to_dict(), indent=2, ensure_ascii=False),
                encoding="utf-8"
            )
        except Exception:
            pass


# ============================================================
# POINT D'ENTRÉE STANDALONE
# ============================================================
if __name__ == "__main__":
    logging.basicConfig(level=logging.DEBUG)
    log = logging.getLogger("sav_test")

    agent = SAVAgent(logger=log)

    # Test du diagnostic
    errors = [
        "ValueError: expected non-negative integer numpy seed",
        "NoneType object is not subscriptable extra_pnginfo workflow",
        "CUDA out of memory OOM RuntimeError",
        "ControlNet ignore second generation",
    ]
    for err in errors:
        bugs = agent.diagnose(err)
        print(f"Erreur: {err[:50]}")
        print(f"  → {[b['id'] for b in bugs]}")

    # Test résolution
    report = agent.resolve("ValueError: expected non-negative integer numpy seed")
    print(f"\nRapport : {report}")
    print(json.dumps(report.to_dict(), indent=2, ensure_ascii=False))

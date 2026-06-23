"""
agents/sav_agent.py — AI-SAV Code & Debugging
Spécialiste ComfyUI avec boucle de validation rigoureuse.

Gère notamment le bug ControlNet (cycle reset/warm/prod obligatoire)
et tout autre bug connu de ComfyUI via un système de patches.
"""
import json, logging, time, requests
from pathlib import Path
import os
from enum import Enum

COMFY_URL = "http://127.0.0.1:8188"
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

CLAUDE_MODEL = "claude-sonnet-4-6"

class TestResult(Enum):
    PASS = "PASS"
    FAIL = "FAIL"
    SKIP = "SKIP"

# ── Patches connus ────────────────────────────────────────────────────
KNOWN_BUGS = {
    "controlnet_cache_poison": {
        "description": "Après une génération avec ControlNet actif, le cache GPU "
                       "reste pollué. La 2e génération crashe ControlNet. "
                       "Fix : cycle Reset(CN off) → Warm(CN off) → Stop → Prod(CN on).",
        "trigger": lambda wf: any(
            n.get("class_type","").startswith("ControlNet")
            for n in (wf.values() if isinstance(wf, dict) else [])
        ),
        "fix": "controlnet_reset_cycle",
    },
}


class SAVAgent:
    """
    Agent SAV ComfyUI.
    - Diagnostique les erreurs reçues depuis les logs ComfyUI
    - Applique les patches connus
    - Valide chaque fix avec un test unitaire avant de passer au suivant
    """

    def __init__(self, logger: logging.Logger = None, use_llm: bool = True):
        self.log     = logger or logging.getLogger("sav")
        self.use_llm = use_llm
        self.history = []   # [(error, fix_applied, result)]

    # ── API interne ComfyUI ───────────────────────────────────────────
    def _comfy_get(self, endpoint: str) -> dict:
        try:
            r = requests.get(f"{COMFY_URL}{endpoint}", timeout=8)
            return r.json() if r.status_code == 200 else {}
        except Exception:
            return {}

    def _comfy_post(self, endpoint: str, payload: dict) -> dict:
        try:
            r = requests.post(f"{COMFY_URL}{endpoint}", json=payload, timeout=10)
            return r.json() if r.status_code == 200 else {}
        except Exception:
            return {}

    def _interrupt(self):
        try:
            requests.post(f"{COMFY_URL}/interrupt", timeout=5)
        except Exception:
            pass

    # ── Détection automatique des bugs dans un workflow ───────────────
    def detect_bugs(self, workflow: dict) -> list:
        found = []
        for bug_id, bug in KNOWN_BUGS.items():
            if bug["trigger"](workflow):
                found.append(bug_id)
                self.log.warning(f"[SAV] Bug détecté : {bug_id} — {bug['description'][:80]}")
        return found

    # ── TEST UNITAIRE : vérifie l'état de ComfyUI ────────────────────
    def unit_test_comfyui(self) -> TestResult:
        self.log.info("[SAV/TEST] Vérification état ComfyUI...")
        stats = self._comfy_get("/system_stats")
        if not stats:
            self.log.error("[SAV/TEST] FAIL — ComfyUI inaccessible")
            return TestResult.FAIL
        queue = self._comfy_get("/queue")
        running = len(queue.get("queue_running", []))
        pending = len(queue.get("queue_pending", []))
        self.log.info(f"[SAV/TEST] PASS — running={running} pending={pending}")
        return TestResult.PASS

    def unit_test_workflow(self, workflow: dict) -> TestResult:
        """Valide la structure minimale du workflow avant envoi."""
        if not workflow:
            return TestResult.FAIL
        required_classes = {"KSampler", "CheckpointLoaderSimple", "VAEDecode"}
        found = {n.get("class_type") for n in workflow.values()}
        missing = required_classes - found
        if missing:
            self.log.warning(f"[SAV/TEST] Nœuds manquants : {missing}")
            return TestResult.FAIL
        return TestResult.PASS

    # ── FIX : ControlNet Reset Cycle ─────────────────────────────────
    def fix_controlnet_reset_cycle(self, workflow: dict,
                                   send_fn,        # callable(wf) → prompt_id
                                   wait_fn,        # callable(pid) → bool
                                   cn_switch_ids: list = None) -> dict:
        """
        Protocole anti-bug ControlNet :
        Phase 1 — Reset  : envoie le workflow avec ControlNet DÉSACTIVÉ (mode=4)
        Phase 2 — Warm   : attend 2s, interrompt (charge le cache sans CN)
        Phase 3 — Prod   : ré-active ControlNet, envoie la vraie génération

        cn_switch_ids : liste des IDs de nœuds ImpactSwitch qui contrôlent CN
                        Si None, désactive tous les ControlNetApplyAdvanced
        """
        self.log.info("[SAV/FIX] Début du cycle ControlNet Reset")

        import copy
        wf_reset = copy.deepcopy(workflow)

        # Identifier les nœuds ControlNet
        cn_nodes = []
        for nid, node in wf_reset.items():
            ct = node.get("class_type", "")
            if "ControlNet" in ct and "Loader" not in ct:
                cn_nodes.append(nid)

        if not cn_nodes and not cn_switch_ids:
            self.log.warning("[SAV/FIX] Aucun nœud ControlNet trouvé — skip cycle")
            return workflow

        # ── Phase 1 : RESET (CN off) ──
        self.log.info("[SAV/FIX] Phase 1 — Reset (ControlNet désactivé)")
        for nid in cn_nodes:
            wf_reset[nid]["inputs"] = {}   # déconnecter les inputs
        if cn_switch_ids:
            for sid in cn_switch_ids:
                if sid in wf_reset:
                    wf_reset[sid]["inputs"]["select"] = 2   # input2 = sans CN

        pid_reset = send_fn(wf_reset)
        if not pid_reset:
            self.log.error("[SAV/FIX] Phase 1 échouée — envoi impossible")
            return workflow

        # ── Phase 2 : WARM (laisser charger le cache, puis interrompre) ──
        self.log.info("[SAV/FIX] Phase 2 — Warm (attente 2.5s → interruption)")
        time.sleep(2.5)
        self._interrupt()
        time.sleep(1.0)

        # ── Test unitaire post-reset ──
        if self.unit_test_comfyui() != TestResult.PASS:
            self.log.error("[SAV/FIX] Test post-reset échoué")
            return workflow

        # ── Phase 3 : PROD (CN on) ──
        self.log.info("[SAV/FIX] Phase 3 — Production (ControlNet réactivé)")
        self.history.append(("controlnet_cache_poison", "controlnet_reset_cycle", "applied"))
        return workflow   # le workflow original avec CN actif

    # ── Diagnostic LLM pour bugs inconnus ────────────────────────────
    def diagnose_with_llm(self, error_log: str, workflow_sample: dict) -> dict:
        if not self.use_llm:
            return {"diagnosis": "LLM désactivé", "fix": None}

        system = (
            "Tu es un expert ComfyUI et Python. Tu analyses des erreurs de pipeline "
            "et proposes des corrections précises. Réponds UNIQUEMENT en JSON valide."
        )
        prompt = f"""
Erreur ComfyUI détectée :
{error_log[:1500]}

Extrait du workflow (nœuds concernés) :
{json.dumps(workflow_sample, ensure_ascii=False)[:1000]}

Retourne ce JSON :
{{
  "root_cause": "cause racine en une phrase",
  "affected_nodes": ["id1", "id2"],
  "fix_type": "workflow_patch|restart|parameter_change|node_bypass",
  "fix_instructions": "instructions précises étape par étape",
  "severity": "low|medium|high|critical",
  "prevent_recurrence": "comment éviter ce bug à l'avenir"
}}
"""
        try:
            resp = requests.post(
                ANTHROPIC_URL,
                headers={
                "Content-Type": "application/json",
                "x-api-key": _get_api_key(),
                "anthropic-version": "2023-06-01",
            },
                json={"model": CLAUDE_MODEL, "max_tokens": 800,
                      "system": system, "messages": [{"role":"user","content":prompt}]},
                timeout=30
            )
            if resp.status_code == 200:
                raw = resp.json()["content"][0]["text"].strip()
                if raw.startswith("```"):
                    raw = "\n".join(raw.split("\n")[1:-1])
                result = json.loads(raw)
                self.log.info(f"[SAV/LLM] Diagnostic : {result.get('root_cause','?')}")
                return result
        except Exception as e:
            self.log.warning(f"[SAV/LLM] Erreur : {e}")
        return {"diagnosis": "échec LLM", "fix": None}

    # ── Pipeline complet de résolution ───────────────────────────────
    def resolve(self, error_log: str, workflow: dict,
                send_fn=None, wait_fn=None) -> dict:
        """
        Boucle : Test → Détection → Fix → Vérification → Test
        Retourne le workflow potentiellement patché.
        """
        self.log.info("[SAV] ══ Début résolution ══")

        # Test initial
        if self.unit_test_comfyui() == TestResult.FAIL:
            self.log.error("[SAV] ComfyUI hors ligne — résolution impossible")
            return workflow

        # Détection bugs connus
        bugs = self.detect_bugs(workflow)

        for bug_id in bugs:
            bug = KNOWN_BUGS[bug_id]
            fix_name = bug["fix"]
            self.log.info(f"[SAV] Application fix : {fix_name}")

            if fix_name == "controlnet_reset_cycle" and send_fn and wait_fn:
                workflow = self.fix_controlnet_reset_cycle(
                    workflow, send_fn, wait_fn
                )

            # Vérification post-fix
            result = self.unit_test_comfyui()
            self.log.info(f"[SAV] Test post-fix [{fix_name}] : {result.value}")

        # Si pas de bug connu → LLM
        if not bugs and error_log:
            diagnosis = self.diagnose_with_llm(error_log, workflow)
            self.log.info(f"[SAV/LLM] Sévérité : {diagnosis.get('severity','?')}")

        self.log.info("[SAV] ══ Résolution terminée ══")
        return workflow

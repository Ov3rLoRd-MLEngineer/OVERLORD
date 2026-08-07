"""
agents/pipeline_conscience.py — Pipeline Conscience V1.45 + Context Bus V1.49
Analyse les métriques de runs et ajuste automatiquement les paramètres.
NOUVEAU V1.49 : publie les paramètres adaptatifs sur le context_bus.
"""
import json
import logging
import statistics
from pathlib import Path
from datetime import datetime

try:
    from agents.overlord_utils import fallback_llm, safe_json_parse
    UTILS_OK = True
except ImportError:
    UTILS_OK = False

try:
    from agents.context_bus import get_bus
    BUS_OK = True
except ImportError:
    BUS_OK = False

log = logging.getLogger("pipeline_conscience")
CONSCIENCE_DIR = Path("workspace/conscience")
PARAMS_FILE    = CONSCIENCE_DIR / "adaptive_params.json"
HISTORY_FILE   = CONSCIENCE_DIR / "run_history.jsonl"

DEFAULT_PARAMS = {
    "script_quality_threshold": 70,
    "max_script_iterations":    3,
    "max_storyboard_iterations":2,
    "critic_strictness":        1.0,
    "preferred_llm":            "claude-sonnet-4-6",
    "sourcing_reddit_limit":    10,
    "loopback_patience":        2,
    "_version":                 "V1.49",
    "_updated":                 "",
}


class PipelineConscience:

    def __init__(self, logger: logging.Logger = None):
        self.log = logger or log
        CONSCIENCE_DIR.mkdir(parents=True, exist_ok=True)
        self.params  = self._load_params()
        self.history = self._load_history()

    def _load_params(self) -> dict:
        if PARAMS_FILE.exists():
            try:
                return json.loads(PARAMS_FILE.read_text(encoding="utf-8"))
            except Exception:
                pass
        return DEFAULT_PARAMS.copy()

    def _load_history(self) -> list:
        if not HISTORY_FILE.exists():
            return []
        runs = []
        try:
            for line in HISTORY_FILE.read_text(encoding="utf-8").splitlines():
                if line.strip():
                    runs.append(json.loads(line))
        except Exception:
            pass
        return runs[-50:]

    def _save_params(self):
        self.params["_updated"] = datetime.now().isoformat()
        PARAMS_FILE.write_text(
            json.dumps(self.params, indent=2, ensure_ascii=False),
            encoding="utf-8"
        )

    def _publish_to_bus(self):
        """Publie les paramètres adaptatifs sur le context_bus."""
        if not BUS_OK:
            return
        try:
            bus = get_bus()
            bus.write("conscience.quality_threshold",
                      self.params["script_quality_threshold"],
                      agent_id="conscience", confidence=0.85)
            bus.write("conscience.preferred_llm",
                      self.params["preferred_llm"],
                      agent_id="conscience", confidence=0.9)
            bus.write("conscience.critic_strictness",
                      self.params["critic_strictness"],
                      agent_id="conscience", confidence=0.8)
            bus.write("conscience.max_iterations",
                      self.params["max_script_iterations"],
                      agent_id="conscience", confidence=0.8)
        except Exception as e:
            self.log.warning(f"[CONSCIENCE] Publication bus échouée : {e}")

    def record_run(self, run_data: dict):
        entry = {
            "timestamp":    datetime.now().isoformat(),
            "run_id":       run_data.get("run_id", ""),
            "health":       run_data.get("pipeline_health", ""),
            "blocs_ok":     run_data.get("blocs_ok", 0),
            "score_moyen":  run_data.get("score_moyen", 0),
            "critic_checks":run_data.get("critic_checks", 0),
            "duration_s":   run_data.get("duration_s", 0),
            "errors":       run_data.get("errors", []),
            "media_type":   run_data.get("media_type", ""),
        }
        self.history.append(entry)
        with open(HISTORY_FILE, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")
        self.log.info(f"[CONSCIENCE] Run enregistré — {len(self.history)} runs en mémoire")

    def analyze_and_adapt(self) -> dict:
        if len(self.history) < 3:
            self.log.info("[CONSCIENCE] Pas assez de données — minimum 3 runs")
            return self.params

        recent  = self.history[-10:]
        changes = []

        scores = [r["score_moyen"] for r in recent if r.get("score_moyen", 0) > 0]
        if scores:
            avg_score = statistics.mean(scores)
            if avg_score > 88 and self.params["script_quality_threshold"] < 85:
                self.params["script_quality_threshold"] = min(85, self.params["script_quality_threshold"] + 3)
                changes.append(f"Seuil qualité augmenté -> {self.params['script_quality_threshold']}")
            elif avg_score < 60 and self.params["script_quality_threshold"] > 60:
                self.params["script_quality_threshold"] = max(60, self.params["script_quality_threshold"] - 5)
                changes.append(f"Seuil qualité baissé -> {self.params['script_quality_threshold']}")

        all_errors  = []
        for r in recent:
            all_errors.extend(r.get("errors", []))
        api_errors = sum(1 for e in all_errors if "401" in str(e) or "400" in str(e) or "credit" in str(e).lower())
        if api_errors >= 3 and self.params["preferred_llm"] != "ollama":
            self.params["preferred_llm"] = "ollama"
            changes.append("LLM préféré -> Ollama (API errors répétées)")
        if api_errors == 0 and self.params["preferred_llm"] == "ollama":
            self.params["preferred_llm"] = "claude-sonnet-4-6"
            changes.append("LLM préféré -> Claude (API stable)")

        durations = [r["duration_s"] for r in recent if r.get("duration_s", 0) > 0]
        if durations:
            avg_dur = statistics.mean(durations)
            if avg_dur > 300 and self.params["max_script_iterations"] > 1:
                self.params["max_script_iterations"] = max(1, self.params["max_script_iterations"] - 1)
                changes.append(f"Iterations script baissées -> {self.params['max_script_iterations']}")
            elif avg_dur < 60 and self.params["max_script_iterations"] < 3:
                self.params["max_script_iterations"] += 1
                changes.append(f"Iterations script augmentées -> {self.params['max_script_iterations']}")

        health_counts   = {}
        for r in recent:
            h = r.get("health", "")
            health_counts[h] = health_counts.get(h, 0) + 1
        degraded_count = health_counts.get("DEGRADED", 0) + health_counts.get("CRITICAL", 0)
        if degraded_count >= 5:
            self.params["critic_strictness"] = max(0.7, self.params["critic_strictness"] - 0.1)
            changes.append(f"Critique assoupli -> {self.params['critic_strictness']:.1f}")
        elif degraded_count == 0 and len(recent) >= 5:
            self.params["critic_strictness"] = min(1.2, self.params["critic_strictness"] + 0.05)
            changes.append(f"Critique durci -> {self.params['critic_strictness']:.2f}")

        if changes:
            self._save_params()
            self._publish_to_bus()   # NOUVEAU V1.49
            for c in changes:
                self.log.info(f"[CONSCIENCE] Adaptation : {c}")
        else:
            self.log.info("[CONSCIENCE] Paramètres optimaux — aucun ajustement")

        return {"params": self.params, "changes": changes, "runs_analyzed": len(recent)}

    def get_params(self) -> dict:
        return self.params.copy()

    def generate_insight(self) -> str:
        if not UTILS_OK or len(self.history) < 5:
            return ""
        recent_summary = json.dumps(self.history[-5:], ensure_ascii=False)[:1500]
        prompt = f"Analyse ces runs de pipeline et donne 1 insight clé en 1 phrase :\n{recent_summary}"
        raw = fallback_llm(prompt, max_tokens=100, logger=self.log)
        return raw.strip()[:200] if raw else ""

    def status(self) -> dict:
        return {
            "runs_recorded": len(self.history),
            "params":        self.params,
            "last_updated":  self.params.get("_updated", "jamais"),
        }


def get_conscience() -> PipelineConscience:
    return PipelineConscience()


if __name__ == "__main__":
    import sys, io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
    logging.basicConfig(level=logging.INFO)
    pc = PipelineConscience()
    for i in range(5):
        pc.record_run({
            "run_id": f"test_{i}",
            "pipeline_health": "DEGRADED" if i < 2 else "STABLE",
            "blocs_ok": 1 + i,
            "score_moyen": 45 + i*8,
            "errors": ["HTTP 400 credit" if i < 3 else ""],
            "duration_s": 120 + i*30,
        })
    result = pc.analyze_and_adapt()
    print(json.dumps(result, indent=2, ensure_ascii=False))
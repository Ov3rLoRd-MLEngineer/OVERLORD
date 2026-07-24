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
agents/critic.py -- Agent Critique Ov3rLoRd
Intercepte et valide TOUS les echanges entre agents.
V1.49p : overlord_utils centralise, datetime.utcnow() corrige.
"""

import json
import logging
import time
import hashlib
from pathlib import Path
from datetime import datetime, timezone
from enum import Enum

try:
    from agents.overlord_utils import fallback_llm, safe_json_parse, build_headers
    UTILS_OK = True
except ImportError:
    UTILS_OK = False
    fallback_llm    = None
    safe_json_parse = None
    build_headers   = None

try:
    from agents.context_bus import get_bus
    BUS_OK = True
except ImportError:
    BUS_OK = False

CRITIC_DIR   = Path("workspace/critic")
CLAUDE_MODEL = "claude-sonnet-4-6"
log          = logging.getLogger("critic")


def _llm(prompt: str, system: str = "", max_tokens: int = 500) -> str:
    if UTILS_OK and fallback_llm:
        return fallback_llm(prompt, system=system, model=CLAUDE_MODEL,
                            max_tokens=max_tokens)
    return ""


def _parse(raw: str) -> dict | None:
    if not raw:
        return None
    if UTILS_OK and safe_json_parse:
        ok, data, _ = safe_json_parse(raw)
        return data if ok else None
    try:
        clean = raw.strip()
        if clean.startswith("```"):
            clean = "\n".join(clean.split("\n")[1:-1])
        return json.loads(clean)
    except Exception:
        return None


class Verdict(Enum):
    PASS   = "pass"
    WARN   = "warn"
    REPAIR = "repair"
    REJECT = "reject"
    HALT   = "halt"


class CriticReport:
    def __init__(self, handoff: str, verdict: Verdict = Verdict.PASS,
                 score: int = 80, reason: str = "",
                 data_out: dict = None):
        self.handoff  = handoff
        self.verdict  = verdict
        self.score    = score
        self.reason   = reason
        self.data_out = data_out
        self.ts       = datetime.now(tz=timezone.utc).isoformat()

    def to_dict(self) -> dict:
        return {
            "handoff": self.handoff,
            "verdict": self.verdict.value,
            "score":   self.score,
            "reason":  self.reason,
            "ts":      self.ts,
        }


class CriticAgent:
    """
    Agent Critique -- valide chaque transition de bloc dans maestro.py.
    PASS / WARN / REPAIR / REJECT / HALT.
    """

    def __init__(self, run_id: str, logger: logging.Logger = None,
                 use_llm: bool = True):
        self.run_id   = run_id
        self.log      = logger or log
        self.use_llm  = use_llm and UTILS_OK
        self._history: list[CriticReport] = []
        self._loopback: dict[str, list]   = {}
        CRITIC_DIR.mkdir(parents=True, exist_ok=True)

    def validate_handoff(self, handoff: str, data: dict,
                          extra: dict = None) -> CriticReport:
        """
        Valide la transition entre deux blocs du pipeline.
        handoff : "sourcing->scenario" | "scenario->storyboard" | etc.
        """
        # Validations structurelles (sans LLM)
        report = self._structural_check(handoff, data, extra)

        # Loopback : detection de degradation
        loopback = self._check_loopback(handoff, report.score)
        if loopback:
            report.verdict = Verdict.HALT
            report.reason  = f"Degradation detectee sur {handoff} : {loopback}"
            self._record(report)
            return report

        # Si score bas et LLM disponible -> analyse approfondie
        if report.score < 60 and self.use_llm:
            llm_report = self._llm_check(handoff, data, extra)
            if llm_report:
                report.score   = llm_report.get("score", report.score)
                report.reason  = llm_report.get("reason", report.reason)
                verdict_str    = llm_report.get("verdict", "warn")
                try:
                    report.verdict = Verdict(verdict_str)
                except ValueError:
                    report.verdict = Verdict.WARN

        self._record(report)
        if BUS_OK:
            try:
                bus = get_bus()
                bus.write("critic.last_handoff", handoff,            agent_id="critic")
                bus.write("critic.last_verdict", report.verdict.value, agent_id="critic")
                bus.write("critic.last_score",   report.score,         agent_id="critic")
            except Exception:
                pass

        return report

    def _structural_check(self, handoff: str, data: dict,
                            extra: dict = None) -> CriticReport:
        """Validations rapides sans LLM."""
        report = CriticReport(handoff, Verdict.PASS, score=80)

        if not data:
            report.verdict = Verdict.REJECT
            report.score   = 0
            report.reason  = f"Donnees vides pour {handoff}"
            return report

        if "error" in data:
            report.verdict = Verdict.REJECT
            report.score   = 10
            report.reason  = f"Erreur dans les donnees : {data['error']}"
            return report

        # Checks specifiques par handoff
        if handoff == "sourcing->scenario":
            if not data.get("brief") and not data.get("hot_keywords"):
                report.verdict = Verdict.WARN
                report.score   = 50
                report.reason  = "Brief et keywords absents du TrendReport"

        elif handoff == "scenario->storyboard":
            if not data.get("title"):
                report.verdict = Verdict.WARN
                report.score   = 55
                report.reason  = "Titre absent du script"
            if not data.get("acts") and not data.get("scenes"):
                report.verdict = Verdict.REJECT
                report.score   = 20
                report.reason  = "Ni actes ni scenes dans le script"

        elif handoff == "storyboard->production":
            jobs = extra.get("jobs",[]) if extra else []
            if not jobs:
                report.verdict = Verdict.REJECT
                report.score   = 0
                report.reason  = "Aucun job de production genere"

        elif handoff == "production->postprod":
            success = data.get("success", 0)
            total   = data.get("total",   1)
            if total > 0 and success / total < 0.5:
                report.verdict = Verdict.WARN
                report.score   = 40
                report.reason  = f"Taux succes faible : {success}/{total}"

        return report

    def _llm_check(self, handoff: str, data: dict,
                    extra: dict = None) -> dict | None:
        """Analyse approfondie via LLM."""
        data_str = json.dumps(data, ensure_ascii=False, default=str)[:800]
        prompt = (
            f"Tu es l'agent Critique d'Ov3rLoRd.\n"
            f"Analyse cette transition de pipeline : {handoff}\n"
            f"Donnees : {data_str}\n\n"
            f"JSON : {{\"verdict\":\"pass|warn|repair|reject|halt\","
            f"\"score\":0-100,\"reason\":\"...\"}}"
        )
        return _parse(_llm(prompt, max_tokens=200))

    def _check_loopback(self, handoff: str, score: int) -> str:
        """Detecte les degradations de score sur un handoff."""
        if handoff not in self._loopback:
            self._loopback[handoff] = []
        self._loopback[handoff].append(score)
        history = self._loopback[handoff][-5:]

        if len(history) >= 3:
            trend = history[-1] - history[0]
            if trend < -30:
                return f"Score en chute : {history[0]} -> {history[-1]}"
            if all(s < 40 for s in history[-3:]):
                return f"3 scores consecutifs < 40 : {history[-3:]}"
        return ""

    def _record(self, report: CriticReport):
        self._history.append(report)
        self.log.info(
            f"[CRITIQUE] {report.handoff} | {report.verdict.value.upper()} | "
            f"score={report.score} | {report.reason[:60] if report.reason else 'OK'}"
        )
        # Sauvegarder si verdict severe
        if report.verdict in (Verdict.REJECT, Verdict.HALT):
            path = CRITIC_DIR / f"report_{self.run_id}_{int(time.time())}.json"
            try:
                path.write_text(
                    json.dumps(report.to_dict(), ensure_ascii=False, indent=2),
                    encoding="utf-8"
                )
            except Exception:
                pass

    def health_summary(self) -> dict:
        if not self._history:
            return {"total_checks":0, "avg_score":0, "pipeline_health":"UNKNOWN"}
        scores = [r.score for r in self._history]
        verdicts = {v.value: 0 for v in Verdict}
        for r in self._history:
            verdicts[r.verdict.value] += 1
        avg_score = sum(scores) / len(scores)
        if verdicts["halt"] > 0:
            health = "CRITICAL"
        elif verdicts["reject"] > 2:
            health = "DEGRADED"
        elif avg_score > 75:
            health = "STABLE"
        else:
            health = "DEGRADED"

        if BUS_OK:
            try:
                get_bus().write("critic.health", health,           agent_id="critic")
                get_bus().write("critic.avg_score", round(avg_score,1), agent_id="critic")
            except Exception:
                pass

        return {
            "total_checks":   len(self._history),
            "avg_score":      round(avg_score, 1),
            "pipeline_health":health,
            "verdicts":       verdicts,
        }


if __name__ == "__main__":
    import sys, io
    if hasattr(sys.stdout, "buffer"):
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    logging.basicConfig(level=logging.INFO)
    critic = CriticAgent("test_run")
    print("=== Critic V1.49p ===")
    r1 = critic.validate_handoff("sourcing->scenario",
                                  {"brief":"Dragon Ball trending","hot_keywords":["dragon ball"]})
    print(f"Check 1 : {r1.verdict.value} (score={r1.score})")
    r2 = critic.validate_handoff("scenario->storyboard", {"error":"json_parse_failed"})
    print(f"Check 2 : {r2.verdict.value} (score={r2.score})")
    print(f"Sante   : {critic.health_summary()['pipeline_health']}")
"""
agents/alignment.py -- Ov3rLoRd V1.20 -- Alignement IA
V1.49 : overlord_utils centralise, context_bus connecte.
Constitutional AI, Debate, Uncertainty, Anomaly Detection.
"""

import json
import math
import time
import logging
import threading
from pathlib import Path
from dataclasses import dataclass, field
from typing import Any, Optional
from datetime import datetime, timezone

try:
    from agents.overlord_utils import fallback_llm, safe_json_parse
    UTILS_OK = True
except ImportError:
    UTILS_OK = False
    fallback_llm    = None
    safe_json_parse = None

try:
    from agents.context_bus import get_bus
    BUS_OK = True
except ImportError:
    BUS_OK = False

ALIGNMENT_DIR = Path("workspace/alignment")
CLAUDE_MODEL  = "claude-sonnet-4-6"


def _llm(prompt: str, system: str = "", max_tokens: int = 400) -> str:
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


# ── Constitutional AI ─────────────────────────────────────────────────
CONSTITUTION = [
    "Ne pas generer de contenu nuisible, offensant ou illegal.",
    "Respecter les droits d'auteur et la propriete intellectuelle.",
    "Etre transparent sur la nature IA du contenu genere.",
    "Proteger la vie privee des individus reels.",
    "Eviter la desinformation et les contenus trompeurs.",
    "Promouvoir la diversite et l'inclusion dans les narrations.",
    "Respecter les reglementations locales (RGPD, droits d'auteur).",
]


class ConstitutionalChecker:
    """Verifie que le contenu respecte la charte constitutionnelle."""

    def __init__(self, logger: logging.Logger = None):
        self.log    = logger or logging.getLogger("constitution")
        self._log_path = ALIGNMENT_DIR / "violations.jsonl"
        ALIGNMENT_DIR.mkdir(parents=True, exist_ok=True)

    def check(self, content: dict, content_type: str = "script") -> dict:
        content_str  = json.dumps(content, ensure_ascii=False)[:800]
        constitution = "\n".join(f"{i+1}. {rule}" for i, rule in enumerate(CONSTITUTION))

        prompt = (
            f"Verifie si ce {content_type} respecte la charte :\n\n"
            f"CHARTE :\n{constitution}\n\n"
            f"CONTENU :\n{content_str}\n\n"
            f"JSON : {{\"compliant\":true,\"violations\":[],\"severity\":\"none|low|medium|high\","
            f"\"recommendations\":[]}}"
        )
        raw  = _llm(prompt, max_tokens=300)
        data = _parse(raw)
        result = data or {"compliant": True, "violations": [], "severity": "none"}

        if not result.get("compliant"):
            self._log_violation(content_type, result)
            self.log.warning(
                f"[CONSTITUTION] Violation detectee ({result.get('severity','?')}) : "
                f"{result.get('violations',[])}"
            )
        else:
            self.log.info(f"[CONSTITUTION] OK {content_type} conforme")

        if BUS_OK:
            try:
                bus = get_bus()
                bus.write("alignment.constitutional_ok",
                          result.get("compliant", True), agent_id="constitution")
                bus.write("alignment.severity",
                          result.get("severity", "none"), agent_id="constitution")
            except Exception:
                pass

        return result

    def _log_violation(self, content_type: str, result: dict):
        try:
            entry = {
                "timestamp":    datetime.now(tz=timezone.utc).isoformat(),
                "content_type": content_type,
                "violations":   result.get("violations", []),
                "severity":     result.get("severity", "?"),
            }
            with open(self._log_path, "a", encoding="utf-8") as f:
                f.write(json.dumps(entry, ensure_ascii=False) + "\n")
        except Exception:
            pass


# ── Debate (double validation) ────────────────────────────────────────
class DebateValidator:
    """
    Validation par debat : deux agents s'affrontent sur la qualite.
    Inspire du Constitutional AI Debate de DeepMind.
    """

    def __init__(self, logger: logging.Logger = None):
        self.log = logger or logging.getLogger("debate")

    def debate(self, proposal: dict, rounds: int = 2) -> dict:
        """Lance un debat en N rounds entre un defenseur et un critique."""
        proposal_str = json.dumps(proposal, ensure_ascii=False)[:600]

        current_arguments = {"for": [], "against": []}
        verdict = "approved"

        for round_n in range(1, rounds + 1):
            # Defenseur
            for_prompt = (
                f"Round {round_n}. Tu defends cette proposition.\n"
                f"Proposition : {proposal_str}\n"
                f"Arguments precedents contre : {current_arguments['against']}\n"
                f"JSON : {{\"argument\":\"...\",\"strength\":0.0-1.0}}"
            )
            for_data = _parse(_llm(for_prompt, max_tokens=200))
            if for_data:
                current_arguments["for"].append(for_data.get("argument",""))

            # Critique
            against_prompt = (
                f"Round {round_n}. Tu critiques cette proposition.\n"
                f"Proposition : {proposal_str}\n"
                f"Arguments pour : {current_arguments['for']}\n"
                f"JSON : {{\"argument\":\"...\",\"strength\":0.0-1.0}}"
            )
            against_data = _parse(_llm(against_prompt, max_tokens=200))
            if against_data:
                current_arguments["against"].append(against_data.get("argument",""))

        # Arbitre
        judge_prompt = (
            f"Arbitre ce debat.\n"
            f"Pour : {current_arguments['for']}\n"
            f"Contre : {current_arguments['against']}\n"
            f"JSON : {{\"verdict\":\"approved|rejected\","
            f"\"confidence\":0.0-1.0,\"reasoning\":\"...\"}}"
        )
        judge_data = _parse(_llm(judge_prompt, max_tokens=200))
        if judge_data:
            verdict = judge_data.get("verdict", "approved")
            conf    = judge_data.get("confidence", 0.6)
        else:
            verdict = "approved"
            conf    = 0.5

        self.log.info(f"[DEBATE] Verdict : {verdict} (conf={conf:.2f})")

        if BUS_OK:
            try:
                get_bus().write("alignment.debate_verdict", verdict,
                                agent_id="debate")
            except Exception:
                pass

        return {
            "verdict":    verdict,
            "confidence": conf,
            "arguments":  current_arguments,
            "rounds":     rounds,
        }


# ── Anomaly Detector ──────────────────────────────────────────────────
class AnomalyDetector:
    """Detecte les comportements anormaux du pipeline."""

    def __init__(self, logger: logging.Logger = None):
        self.log      = logger or logging.getLogger("anomaly")
        self._history: list[dict] = []
        self._thresholds = {
            "score_drop":    15.0,
            "duration_spike":300.0,
            "error_rate":    0.3,
        }

    def record(self, metrics: dict):
        self._history.append({**metrics, "ts": time.time()})
        self._history = self._history[-50:]

    def detect(self) -> list[dict]:
        if len(self._history) < 3:
            return []
        anomalies = []
        recent    = self._history[-5:]

        # Score drop
        scores = [m.get("score", 0) for m in recent if "score" in m]
        if len(scores) >= 2:
            drop = scores[0] - scores[-1]
            if drop > self._thresholds["score_drop"]:
                anomalies.append({"type":"score_drop","value":drop,
                                   "severity":"high"})

        # Duration spike
        durations = [m.get("duration_s", 0) for m in recent if "duration_s" in m]
        if durations and max(durations) > self._thresholds["duration_spike"]:
            anomalies.append({"type":"duration_spike","value":max(durations),
                               "severity":"medium"})

        if anomalies:
            self.log.warning(f"[ANOMALY] {len(anomalies)} anomalie(s) detectee(s)")
            if BUS_OK:
                try:
                    get_bus().write("alignment.anomalies", anomalies,
                                    agent_id="anomaly_detector")
                    get_bus().write("alignment.anomaly_count", len(anomalies),
                                    agent_id="anomaly_detector")
                except Exception:
                    pass

        return anomalies


# ── Facade AlignmentV120 ──────────────────────────────────────────────
class AlignmentV120:

    def __init__(self, logger: logging.Logger = None):
        self.log        = logger or logging.getLogger("alignment_v120")
        self.constitution = ConstitutionalChecker(logger=self.log)
        self.debate       = DebateValidator(logger=self.log)
        self.anomaly      = AnomalyDetector(logger=self.log)

    def full_check(self, content: dict, content_type: str = "script") -> dict:
        """Verification complete : Constitution + Debat."""
        const_result  = self.constitution.check(content, content_type)
        debate_needed = not const_result.get("compliant") or \
                        const_result.get("severity") in ("medium","high")
        debate_result = {}
        if debate_needed:
            self.log.info("[ALIGNMENT] Debat lance pour validation supplementaire")
            debate_result = self.debate.debate(content)

        final_ok = (const_result.get("compliant", True) and
                    debate_result.get("verdict", "approved") == "approved")

        if BUS_OK:
            try:
                get_bus().write("alignment.final_ok", final_ok, agent_id="alignment")
            except Exception:
                pass

        return {
            "ok":           final_ok,
            "constitution": const_result,
            "debate":       debate_result,
        }

    def monitor(self, metrics: dict) -> list[dict]:
        self.anomaly.record(metrics)
        return self.anomaly.detect()


if __name__ == "__main__":
    import sys, io
    if hasattr(sys.stdout, 'buffer'):
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
    logging.basicConfig(level=logging.INFO)
    av = AlignmentV120()
    print("=== V1.20 Alignment ===\n")
    content = {"title": "Episode de test", "synopsis": "Histoire simple sans contenu problematique"}
    result  = av.full_check(content, "script")
    print(f"Check OK : {result['ok']}")
    print(f"Constitution : {result['constitution'].get('compliant')}")
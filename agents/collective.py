"""
agents/collective.py -- Ov3rLoRd V1.20 -- Intelligence Collective et Nouveaux Agents
V1.49 : _llm() centralise via overlord_utils, context_bus connecte, ASCII logs.
"""

import json
import math
import time
import random
import logging
import threading
from pathlib import Path
from dataclasses import dataclass, field
from typing import Any, Callable, Optional
from enum import Enum

try:
    from agents.overlord_utils import fallback_llm, safe_json_parse, get_api_key
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

COLLECTIVE_DIR = Path("workspace/collective")
CLAUDE_MODEL   = "claude-sonnet-4-6"


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


# ── Parliament (vote democratique) ────────────────────────────────────
class VoteType(Enum):
    APPROVE = "approve"
    REJECT  = "reject"
    ABSTAIN = "abstain"


@dataclass
class Vote:
    agent:      str
    vote:       VoteType
    confidence: float = 0.5
    reasoning:  str   = ""


class AgentParliament:
    """Vote democratique pondere entre agents."""

    def __init__(self, agents: list[str] = None, logger: logging.Logger = None):
        self.log    = logger or logging.getLogger("parliament")
        self.agents = agents or ["sourcing","scenario","storyboard","critic","watchdog"]
        self._weights: dict[str,float] = {a: 1.0 for a in self.agents}
        COLLECTIVE_DIR.mkdir(parents=True, exist_ok=True)

    def vote(self, proposal: str, context: dict = None) -> dict:
        """Lance un vote entre agents sur une proposition."""
        self.log.info(f"[PARLIAMENT] Vote sur : {proposal[:60]}")
        votes   = []
        ctx_str = json.dumps(context or {}, ensure_ascii=False)[:500]

        for agent in self.agents:
            prompt = (
                f"Tu es l'agent '{agent}' d'Ov3rLoRd.\n"
                f"Proposition : {proposal}\nContexte : {ctx_str}\n\n"
                f"Vote JSON : {{\"vote\":\"approve|reject|abstain\","
                f"\"confidence\":0.0-1.0,\"reasoning\":\"...\"}}"
            )
            raw  = _llm(prompt, max_tokens=150)
            data = _parse(raw)
            if data:
                try:
                    v = Vote(
                        agent=agent,
                        vote=VoteType(data.get("vote","abstain")),
                        confidence=float(data.get("confidence",0.5)),
                        reasoning=data.get("reasoning",""),
                    )
                    votes.append(v)
                    self.log.info(f"[PARLIAMENT] {agent}: {v.vote.value} ({v.confidence:.2f})")
                except Exception:
                    votes.append(Vote(agent=agent, vote=VoteType.ABSTAIN))
            else:
                votes.append(Vote(agent=agent, vote=VoteType.ABSTAIN))

        result = self._tally(votes)

        if BUS_OK:
            try:
                get_bus().write("parliament.last_decision", result["decision"],
                                agent_id="parliament")
                get_bus().write("parliament.approval_score", result["approval_score"],
                                agent_id="parliament")
            except Exception:
                pass

        return result

    def _tally(self, votes: list[Vote]) -> dict:
        approve = sum(self._weights.get(v.agent,1.0) * v.confidence
                      for v in votes if v.vote == VoteType.APPROVE)
        reject  = sum(self._weights.get(v.agent,1.0) * v.confidence
                      for v in votes if v.vote == VoteType.REJECT)
        total   = sum(self._weights.get(v.agent,1.0) for v in votes) or 1
        score   = approve / total
        return {
            "decision":      "approve" if score >= 0.5 else "reject",
            "approval_score":round(score,3),
            "votes":         [{"agent":v.agent,"vote":v.vote.value,
                               "confidence":v.confidence} for v in votes],
        }

    def update_weight(self, agent: str, performance: float):
        current = self._weights.get(agent, 1.0)
        self._weights[agent] = max(0.1, min(3.0, current * 0.9 + performance * 0.1))


# ── Specialisation automatique ────────────────────────────────────────
class SpecializationTracker:

    def __init__(self, logger: logging.Logger = None):
        self.log       = logger or logging.getLogger("specialization")
        self._scores:  dict[str,dict[str,list]] = {}
        self._path     = COLLECTIVE_DIR / "specialization.json"
        self._load()

    def _load(self):
        if self._path.exists():
            try:
                self._scores = json.loads(self._path.read_text(encoding="utf-8"))
            except Exception:
                pass

    def _save(self):
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._path.write_text(
            json.dumps(self._scores, ensure_ascii=False, indent=2), encoding="utf-8"
        )

    def record(self, agent: str, task_type: str, score: float):
        if agent not in self._scores:
            self._scores[agent] = {}
        if task_type not in self._scores[agent]:
            self._scores[agent][task_type] = []
        self._scores[agent][task_type].append(score)
        self._scores[agent][task_type] = self._scores[agent][task_type][-20:]
        self._save()

    def get_best_agent(self, task_type: str) -> str:
        best_agent = None
        best_score = -1
        for agent, tasks in self._scores.items():
            if task_type in tasks:
                avg = sum(tasks[task_type]) / len(tasks[task_type])
                if avg > best_score:
                    best_score = avg
                    best_agent = agent
        return best_agent or "scenario"

    def get_specializations(self) -> dict:
        result = {}
        for agent, tasks in self._scores.items():
            best_task  = max(tasks.items(), key=lambda x: sum(x[1])/len(x[1])) if tasks else ("none",[])
            result[agent] = {"specialty": best_task[0],
                             "avg_score": round(sum(best_task[1])/max(len(best_task[1]),1),3)}
        return result


# ── Intelligence collective ───────────────────────────────────────────
class CollectiveIntelligence:

    def __init__(self, logger: logging.Logger = None):
        self.log      = logger or logging.getLogger("collective")
        self.parliament   = AgentParliament(logger=self.log)
        self.specializer  = SpecializationTracker(logger=self.log)

    def collective_decide(self, decision: str, context: dict = None) -> dict:
        self.log.info(f"[COLLECTIVE] Decision collective : {decision[:60]}")
        vote_result = self.parliament.vote(decision, context)
        best_agent  = self.specializer.get_best_agent(
            context.get("task_type","scenario") if context else "scenario"
        )
        result = {
            "decision":   vote_result["decision"],
            "score":      vote_result["approval_score"],
            "best_agent": best_agent,
            "votes":      vote_result["votes"],
        }
        if BUS_OK:
            try:
                get_bus().write("collective.decision",   result["decision"],  agent_id="collective")
                get_bus().write("collective.best_agent", result["best_agent"], agent_id="collective")
            except Exception:
                pass
        return result

    def status(self) -> dict:
        return {
            "parliament_agents": len(self.parliament.agents),
            "specializations":   self.specializer.get_specializations(),
        }


# ── Nouveaux agents specialises ───────────────────────────────────────
class SpecializedAgentBase:
    """Base pour tous les agents specialises V1.20."""

    def __init__(self, role: str, logger: logging.Logger = None):
        self.role = role
        self.log  = logger or logging.getLogger(role)
        self._history: list[dict] = []

    def _call(self, prompt: str, max_tokens: int = 500) -> str:
        system = f"Tu es l'agent '{self.role}' d'Ov3rLoRd Pipeline. Reponds en JSON valide."
        return _llm(prompt, system=system, max_tokens=max_tokens)

    def _remember(self, input_data: dict, result: dict):
        self._history.append({"input": str(input_data)[:200], "result": str(result)[:200],
                               "ts": time.time()})
        self._history = self._history[-20:]


class CareerManagerAgent(SpecializedAgentBase):
    def __init__(self, **kw):
        super().__init__("career_manager", **kw)

    def plan(self, series: str, episode: int, metadata: dict) -> dict:
        prompt = (f"Plan de carriere pour '{series}' episode {episode}.\n"
                  f"Metadata : {json.dumps(metadata, ensure_ascii=False)[:300]}\n"
                  f"JSON : {{\"next_steps\":[], \"platforms\":[], \"timeline\":\"\"}}")
        raw  = self._call(prompt)
        data = _parse(raw)
        result = data or {"next_steps":["Publier sur YouTube","Reddit","Instagram"]}
        self._remember(metadata, result)
        return result


class MonetizationAgent(SpecializedAgentBase):
    def __init__(self, **kw):
        super().__init__("monetization", **kw)

    def analyze(self, series: str, audience_data: dict) -> dict:
        prompt = (f"Strategie de monetisation pour '{series}'.\n"
                  f"Audience : {json.dumps(audience_data, ensure_ascii=False)[:300]}\n"
                  f"JSON : {{\"revenue_streams\":[], \"priority\":\"...\", "
                  f"\"estimated_monthly_usd\":0}}")
        raw    = self._call(prompt)
        data   = _parse(raw)
        result = data or {"revenue_streams":["AdSense","Patreon","Merch"]}
        if BUS_OK:
            try:
                get_bus().write("monetization.streams",
                                result.get("revenue_streams",[]), agent_id="monetization")
            except Exception:
                pass
        return result


class LegalComplianceAgent(SpecializedAgentBase):
    def __init__(self, **kw):
        super().__init__("legal_compliance", **kw)

    def check(self, content: dict) -> dict:
        prompt = (f"Verification conformite legale IA.\n"
                  f"Contenu : {json.dumps(content, ensure_ascii=False)[:300]}\n"
                  f"JSON : {{\"compliant\":true, \"risks\":[], \"recommendations\":[]}}")
        raw    = self._call(prompt, max_tokens=300)
        data   = _parse(raw)
        result = data or {"compliant": True, "risks": [], "recommendations": []}
        if BUS_OK:
            try:
                get_bus().write("legal.compliant",
                                result.get("compliant", True), agent_id="legal")
            except Exception:
                pass
        return result


if __name__ == "__main__":
    import sys, io
    if hasattr(sys.stdout, 'buffer'):
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
    logging.basicConfig(level=logging.INFO)
    ci = CollectiveIntelligence()
    print("=== V1.20 Intelligence Collective ===\n")
    print(f"Status : {json.dumps(ci.status(), indent=2, ensure_ascii=False)}")
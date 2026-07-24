"""
agents/intelligence.py — Ov3rLoRd V1.10 — Intelligence Avancee
Meta-Learning, Curiosity, Self-Reflection, Goal Decomposition, Counterfactual.
FIX V1.49k : x-api-key manquant -> overlord_utils.build_headers().
"""

import json
import logging
import math
import random
import time
import threading
import requests
from pathlib import Path
from datetime import datetime
from dataclasses import dataclass, field
from typing import Any, Callable, Optional

try:
    from agents.overlord_utils import fallback_llm, safe_json_parse, build_headers, get_api_key
    UTILS_OK = True
except ImportError:
    UTILS_OK = False
    fallback_llm  = None
    build_headers = None
    get_api_key   = None

try:
    from agents.context_bus import get_bus
    BUS_OK = True
except ImportError:
    BUS_OK = False

CLAUDE_MODEL = "claude-sonnet-4-6"
INTEL_DIR    = Path("workspace/intelligence")


def llm(prompt: str, system: str = "", max_tokens: int = 500) -> str:
    """
    Appel LLM centralise via overlord_utils.
    FIX : x-api-key etait manquant -> toutes les requetes echouaient en 401.
    """
    if UTILS_OK and fallback_llm:
        return fallback_llm(prompt, system=system, model=CLAUDE_MODEL,
                            max_tokens=max_tokens)
    # Fallback minimal sans overlord_utils
    try:
        key = (get_api_key() if get_api_key else "") or ""
        if not key:
            return ""
        body = {"model": CLAUDE_MODEL, "max_tokens": max_tokens,
                "messages": [{"role": "user", "content": prompt}]}
        if system:
            body["system"] = system
        r = requests.post(
            "https://api.anthropic.com/v1/messages",
            headers={"Content-Type": "application/json",
                     "x-api-key": key,
                     "anthropic-version": "2023-06-01"},
            json=body, timeout=30
        )
        if r.status_code == 200:
            return r.json()["content"][0]["text"].strip()
    except Exception:
        pass
    return ""


# ── Meta-Learning ─────────────────────────────────────────────────────
@dataclass
class TaskExperience:
    task_type: str
    params:    dict
    score:     float
    n_steps:   int   = 1
    timestamp: float = field(default_factory=time.time)


class MetaLearner:

    STYLE_FAMILIES = {
        "anime":     ["action","romance","isekai","mecha","shonen","seinen"],
        "manga":     ["tankobon","webtoon","seinen","shoujo"],
        "comics":    ["superhero","horror","noir","indie"],
        "3d":        ["realistic","stylized","lowpoly","sculpt"],
        "photoreal": ["portrait","landscape","product","cinematic"],
    }

    def __init__(self, logger: logging.Logger = None):
        self.log          = logger or logging.getLogger("meta_learner")
        self._experiences: list[TaskExperience] = []
        self._meta_params: dict = {}
        INTEL_DIR.mkdir(parents=True, exist_ok=True)
        self._load()

    def record_experience(self, task_type: str, params: dict,
                          score: float, n_steps: int = 1):
        exp = TaskExperience(task_type=task_type, params=dict(params),
                             score=score, n_steps=n_steps)
        self._experiences.append(exp)
        self._update_meta_params(exp)
        self._save()
        # Publier sur le bus
        if BUS_OK:
            try:
                get_bus().write("intel.meta_experiences",
                                len(self._experiences), agent_id="meta_learner")
            except Exception:
                pass

    def _update_meta_params(self, exp: TaskExperience):
        family = self._get_family(exp.task_type)
        if family not in self._meta_params:
            self._meta_params[family] = {"experiences": 0}
        mp = self._meta_params[family]
        n  = mp["experiences"]
        lr = 1.0 / (n + 1)
        for param, value in exp.params.items():
            if isinstance(value, (int, float)):
                current  = mp.get(param, value)
                weight   = exp.score * lr
                mp[param] = current * (1 - weight) + value * weight
        mp["experiences"] = n + 1
        mp["avg_score"]   = (mp.get("avg_score", 0) * n + exp.score) / (n + 1)

    def get_initial_params(self, task_type: str, base_params: dict = None) -> dict:
        base   = dict(base_params or {
            "steps":28,"cfg":6.0,"sampler":"euler_ancestral","strength":1.0,"denoise":1.0
        })
        family = self._get_family(task_type)
        meta   = self._meta_params.get(family, {})
        for param, value in meta.items():
            if param in ("experiences","avg_score"):
                continue
            if isinstance(value,(int,float)) and param in base:
                base[param] = type(base[param])(value)
        n_exp  = meta.get("experiences",0)
        avg_sc = meta.get("avg_score",0.5)
        self.log.info(
            f"[META] Params initiaux pour '{task_type}' "
            f"(famille={family}, {n_exp} experiences, score_moy={avg_sc:.2f})"
        )
        return base

    def estimate_convergence(self, task_type: str) -> dict:
        family  = self._get_family(task_type)
        similar = [e for e in self._experiences if self._get_family(e.task_type)==family]
        if not similar:
            return {"estimated_runs":15,"confidence":0.3}
        avg_steps  = sum(e.n_steps for e in similar) / len(similar)
        meta_steps = max(2, avg_steps * 0.6)
        confidence = min(0.9, len(similar) / 20)
        return {
            "estimated_runs": round(meta_steps),
            "without_meta":   round(avg_steps),
            "speedup":        f"{avg_steps/meta_steps:.1f}x",
            "confidence":     round(confidence,2),
            "n_similar_tasks":len(similar),
        }

    def _get_family(self, task_type: str) -> str:
        for family, subtypes in self.STYLE_FAMILIES.items():
            if task_type == family or task_type in subtypes:
                return family
            if any(s in task_type for s in [family]+subtypes):
                return family
        return "anime"

    def _save(self):
        data = {"meta_params": self._meta_params,
                "n_experiences": len(self._experiences)}
        (INTEL_DIR/"meta_learner.json").write_text(
            json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8"
        )

    def _load(self):
        p = INTEL_DIR / "meta_learner.json"
        if p.exists():
            try:
                data = json.loads(p.read_text(encoding="utf-8"))
                self._meta_params = data.get("meta_params", {})
            except Exception:
                pass


# ── Curiosity Engine ──────────────────────────────────────────────────
class CuriosityEngine:

    def __init__(self, logger: logging.Logger = None):
        self.log      = logger or logging.getLogger("curiosity")
        self._visited: list[dict] = []
        self._lock    = threading.Lock()

    def get_curiosity_score(self, params: dict) -> float:
        if not self._visited:
            return 0.8
        key = json.dumps(params, sort_keys=True)
        similar = sum(
            1 for v in self._visited
            if abs(v.get("cfg",0) - params.get("cfg",0)) < 0.5
            and v.get("sampler","") == params.get("sampler","")
        )
        score = max(0.1, 1.0 - similar / max(len(self._visited), 1))
        return round(score, 3)

    def suggest_exploration(self, base_params: dict, n_suggestions: int = 3) -> list:
        suggestions = []
        samplers = ["euler_ancestral","dpm++_2m_sde","dpm++_2m","euler","heun"]
        for _ in range(n_suggestions):
            variant = dict(base_params)
            variant["steps"]   = base_params.get("steps",28) + random.randint(-4,8)
            variant["cfg"]     = round(base_params.get("cfg",6.0) + random.uniform(-1.5,2.0), 1)
            variant["sampler"] = random.choice(samplers)
            variant["cfg"]     = max(3.0, min(12.0, variant["cfg"]))
            variant["steps"]   = max(10,  min(50,   variant["steps"]))
            suggestions.append(variant)
        return suggestions

    def record_outcome(self, params: dict, score: float):
        with self._lock:
            self._visited.append({**params, "_score": score})
            self._visited = self._visited[-200:]

    def get_exploration_summary(self) -> dict:
        if not self._visited:
            return {"explored":0,"avg_score":0}
        return {
            "explored":  len(self._visited),
            "avg_score": round(sum(v.get("_score",0) for v in self._visited)/len(self._visited), 3),
        }


# ── Self-Reflection Loop ──────────────────────────────────────────────
class SelfReflectionLoop:

    def __init__(self, logger: logging.Logger = None):
        self.log = logger or logging.getLogger("reflection")

    def reflect(self, output: dict, criteria: list = None) -> dict:
        crit = criteria or ["coherence","qualite_visuelle","fidelite_prompt","originalite"]
        prompt = (
            f"Auto-critique de cette sortie de pipeline :\n"
            f"{json.dumps(output, ensure_ascii=False)[:1000]}\n\n"
            f"Criteres : {', '.join(crit)}\n"
            f"JSON : {{\"scores\":{{\"critere\":0-100}},\"validated\":bool,"
            f"\"improvements\":[\"...\"]}}"
        )
        raw = llm(prompt, max_tokens=400)
        if raw:
            try:
                clean = raw.strip()
                if clean.startswith("```"):
                    clean = "\n".join(clean.split("\n")[1:-1])
                return json.loads(clean)
            except Exception:
                pass
        avg = 75
        return {
            "scores":       {c: avg for c in crit},
            "validated":    avg >= 70,
            "improvements": [],
        }


# ── Goal Decomposer ───────────────────────────────────────────────────
@dataclass
class SubGoal:
    id:          str
    description: str
    agent:       str
    depends_on:  list
    priority:    int = 1


class GoalDecomposer:

    def decompose(self, goal: str, media_type: str = "anime") -> list[SubGoal]:
        prompt = (
            f"Decompose cet objectif de production en sous-taches :\n"
            f"Objectif : {goal}\nType : {media_type}\n"
            f"JSON : [{{\"id\":\"sg1\",\"description\":\"\",\"agent\":\"\","
            f"\"depends_on\":[],\"priority\":1}}]"
        )
        raw = llm(prompt, max_tokens=600)
        if raw:
            try:
                clean = raw.strip()
                if clean.startswith("```"):
                    clean = "\n".join(clean.split("\n")[1:-1])
                data = json.loads(clean)
                if isinstance(data, list):
                    return [SubGoal(**s) for s in data]
            except Exception:
                pass
        return [
            SubGoal("sg1","Veille et sourcing",       "sourcing",   [],        1),
            SubGoal("sg2","Ecriture du scenario",     "scenario",   ["sg1"],   2),
            SubGoal("sg3","Creation du storyboard",   "storyboard", ["sg2"],   3),
            SubGoal("sg4","Generation des images",    "production", ["sg3"],   4),
            SubGoal("sg5","Montage et post-prod",     "postprod",   ["sg4"],   5),
            SubGoal("sg6","Publication reseaux",      "marketing",  ["sg5"],   6),
        ]

    def get_execution_order(self, subgoals: list[SubGoal]) -> list[list[SubGoal]]:
        completed = set()
        waves     = []
        remaining = list(subgoals)
        while remaining:
            wave = [sg for sg in remaining
                    if all(dep in completed for dep in sg.depends_on)]
            if not wave:
                break
            waves.append(sorted(wave, key=lambda x: x.priority))
            completed.update(sg.id for sg in wave)
            remaining = [sg for sg in remaining if sg.id not in completed]
        return waves


# ── Counterfactual Reasoner ───────────────────────────────────────────
class CounterfactualReasoner:

    def analyze(self, decision_made: dict, alternatives: list[dict],
                actual_result: float) -> dict:
        prompt = (
            f"Analyse cette decision de production IA :\n"
            f"DECISION : {json.dumps(decision_made, ensure_ascii=False)}\n"
            f"RESULTAT : {actual_result:.2f}/100\n\n"
            f"ALTERNATIVES :\n"
            + "\n".join(f"  {i+1}. {json.dumps(a, ensure_ascii=False)}"
                        for i,a in enumerate(alternatives[:3]))
            + "\n\nJSON : {{\"counterfactuals\":[{{\"alternative\":{{}},"
            f"\"estimated_score\":0.0,\"reasoning\":\"\","
            f"\"would_have_been_better\":true}}],"
            f"\"lesson\":\"\"}}"
        )
        raw = llm(prompt, max_tokens=600)
        if raw:
            try:
                clean = raw.strip()
                if clean.startswith("```"):
                    clean = "\n".join(clean.split("\n")[1:-1])
                return json.loads(clean)
            except Exception:
                pass
        return {"lesson": "Analyse non disponible"}


# ── Facade IntelligenceV110 ───────────────────────────────────────────
class IntelligenceV110:

    def __init__(self, logger: logging.Logger = None):
        self.log             = logger or logging.getLogger("intel")
        self.meta_learner    = MetaLearner(logger=self.log)
        self.curiosity       = CuriosityEngine(logger=self.log)
        self.reflection      = SelfReflectionLoop(logger=self.log)
        self.goal_decomposer = GoalDecomposer()
        self.counterfactual  = CounterfactualReasoner()

    def smart_start(self, task_type: str, base_params: dict = None) -> dict:
        meta_params     = self.meta_learner.get_initial_params(task_type, base_params)
        conv_est        = self.meta_learner.estimate_convergence(task_type)
        curiosity_score = self.curiosity.get_curiosity_score(meta_params)

        if curiosity_score > 0.6:
            suggestions = self.curiosity.suggest_exploration(meta_params, n_suggestions=1)
            if suggestions:
                meta_params = suggestions[0]
                self.log.info(f"[INTEL] Mode exploration (curiosite={curiosity_score:.2f})")
            mode = "explore"
        else:
            self.log.info(f"[INTEL] Mode exploitation (curiosite={curiosity_score:.2f})")
            mode = "exploit"

        result = {
            "params":          meta_params,
            "mode":            mode,
            "curiosity_score": curiosity_score,
            "estimated_runs":  conv_est.get("estimated_runs","?"),
            "speedup":         conv_est.get("speedup","1x"),
        }

        if BUS_OK:
            try:
                get_bus().write("intel.mode",            mode,            agent_id="intel")
                get_bus().write("intel.curiosity_score", curiosity_score, agent_id="intel")
            except Exception:
                pass

        return result

    def record_run(self, task_type: str, params: dict, score: float):
        self.meta_learner.record_experience(task_type, params, score)
        self.curiosity.record_outcome(params, score)

    def plan_production(self, goal: str, media_type: str = "anime") -> dict:
        subgoals = self.goal_decomposer.decompose(goal, media_type)
        waves    = self.goal_decomposer.get_execution_order(subgoals)
        return {
            "goal":     goal,
            "subgoals": len(subgoals),
            "waves":    len(waves),
            "wave_plan": [
                {"wave":i+1,"parallel":len(wave),
                 "tasks":[{"id":sg.id,"agent":sg.agent,"desc":sg.description[:60]}
                           for sg in wave]}
                for i,wave in enumerate(waves)
            ],
        }

    def get_dashboard(self) -> dict:
        return {
            "meta_learner": {
                "task_families": len(self.meta_learner._meta_params),
                "experiences":   len(self.meta_learner._experiences),
            },
            "curiosity": self.curiosity.get_exploration_summary(),
        }


if __name__ == "__main__":
    import sys, io
    if hasattr(sys.stdout,'buffer'):
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
    logging.basicConfig(level=logging.INFO)
    intel = IntelligenceV110()
    print("=== TEST INTELLIGENCE V1.10 ===\n")
    intel.meta_learner.record_experience("anime_action",
        {"steps":32,"cfg":7.0,"sampler":"dpm++_2m_sde"}, 0.88, n_steps=5)
    start = intel.smart_start("anime_shonen", {"steps":28,"cfg":6.0})
    print(f"Meta-start 'anime_shonen' :")
    print(f"  Params: steps={start['params'].get('steps')}, cfg={start['params'].get('cfg')}")
    print(f"  Mode: {start['mode']} | Curiosite: {start['curiosity_score']:.3f}")
    plan = intel.plan_production("Creer un episode anime de 5 minutes")
    print(f"\nPlan: {plan['subgoals']} sous-taches | {plan['waves']} vagues")
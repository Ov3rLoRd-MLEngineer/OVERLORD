"""
agents/learning.py -- Ov3rLoRd V1.20 -- Apprentissage Avance
V1.49 : overlord_utils centralise, context_bus connecte.
Reward Shaping, Policy Gradient, Experience Replay, Intrinsic Motivation, Curriculum.
"""

import json
import math
import random
import time
import threading
import logging
import hashlib
from pathlib import Path
from collections import deque
from dataclasses import dataclass, field
from typing import Any, Callable, Optional

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

LEARNING_DIR = Path("workspace/v120_learning")
CLAUDE_MODEL = "claude-sonnet-4-6"


def _llm(prompt: str, system: str = "", max_tokens: int = 300) -> str:
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


# ── Reward Shaping ────────────────────────────────────────────────────
@dataclass
class Reward:
    agent:     str
    action:    str
    value:     float
    timestamp: float = field(default_factory=time.time)
    metadata:  dict  = field(default_factory=dict)


class RewardShaper:
    """Recompenses granulaires a chaque micro-etape."""

    REWARD_TABLE = {
        "sourcing_complete":      0.1,
        "scenario_draft":         0.15,
        "scenario_validated":     0.3,
        "storyboard_complete":    0.2,
        "image_generated":        0.05,
        "image_quality_pass":     0.1,
        "episode_complete":       0.5,
        "critic_approved":        0.2,
        "audience_positive":      0.3,
        "error_recovered":        0.15,
        "budget_under_limit":     0.1,
    }

    def __init__(self, logger: logging.Logger = None):
        self.log      = logger or logging.getLogger("reward_shaper")
        self._buffer: list[Reward] = []
        self._total   = 0.0
        self._lock    = threading.Lock()
        LEARNING_DIR.mkdir(parents=True, exist_ok=True)

    def reward(self, agent: str, action: str,
               bonus: float = 0.0, metadata: dict = None) -> float:
        base  = self.REWARD_TABLE.get(action, 0.0)
        value = base + bonus
        r     = Reward(agent=agent, action=action, value=value,
                       metadata=metadata or {})
        with self._lock:
            self._buffer.append(r)
            self._total += value
            self._buffer = self._buffer[-1000:]
        self.log.debug(f"[REWARD] {agent}/{action} : +{value:.3f}")
        if BUS_OK:
            try:
                get_bus().write("learning.total_reward", round(self._total, 3),
                                agent_id="reward_shaper")
            except Exception:
                pass
        return value

    def get_agent_total(self, agent: str) -> float:
        with self._lock:
            return sum(r.value for r in self._buffer if r.agent == agent)

    def get_summary(self) -> dict:
        with self._lock:
            agents = set(r.agent for r in self._buffer)
            return {
                "total_reward": round(self._total, 3),
                "by_agent": {a: round(sum(r.value for r in self._buffer
                                          if r.agent == a), 3) for a in agents},
                "n_events":  len(self._buffer),
            }


# ── Experience Replay ─────────────────────────────────────────────────
@dataclass
class Episode:
    run_id:   str
    steps:    list[dict]
    reward:   float
    score:    float
    metadata: dict = field(default_factory=dict)


class ExperienceReplay:
    """Rejouer les meilleurs episodes passes pour accelerer l'apprentissage."""

    def __init__(self, capacity: int = 100, logger: logging.Logger = None):
        self.log      = logger or logging.getLogger("experience_replay")
        self._buffer: deque = deque(maxlen=capacity)
        self._path    = LEARNING_DIR / "experience_buffer.json"
        self._load()

    def _load(self):
        if self._path.exists():
            try:
                data = json.loads(self._path.read_text(encoding="utf-8"))
                for ep in data:
                    self._buffer.append(Episode(**ep))
            except Exception:
                pass

    def _save(self):
        try:
            data = [{"run_id":e.run_id,"steps":e.steps,"reward":e.reward,
                     "score":e.score,"metadata":e.metadata}
                    for e in self._buffer]
            self._path.parent.mkdir(parents=True, exist_ok=True)
            self._path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
        except Exception:
            pass

    def add(self, episode: Episode):
        self._buffer.append(episode)
        self._save()
        if BUS_OK:
            try:
                get_bus().write("learning.buffer_size", len(self._buffer),
                                agent_id="experience_replay")
            except Exception:
                pass

    def sample_best(self, n: int = 5) -> list[Episode]:
        episodes = sorted(self._buffer, key=lambda e: e.reward, reverse=True)
        return episodes[:n]

    def get_insights(self) -> dict:
        """Analyse les meilleurs episodes pour extraire des patterns."""
        best = self.sample_best(5)
        if not best:
            return {}
        avg_score  = sum(e.score  for e in best) / len(best)
        avg_reward = sum(e.reward for e in best) / len(best)
        return {
            "n_episodes":  len(self._buffer),
            "best_n":      len(best),
            "avg_score":   round(avg_score,  3),
            "avg_reward":  round(avg_reward, 3),
        }


# ── Curriculum Learning ───────────────────────────────────────────────
class CurriculumScheduler:
    """Progression du plus simple au plus complexe."""

    LEVELS = [
        {"name":"debutant",    "complexity":0.2, "quality_threshold":60,
         "description":"1 scene, style simple, 1 personnage"},
        {"name":"intermediaire","complexity":0.5,"quality_threshold":70,
         "description":"3-5 scenes, 2 personnages, un conflit"},
        {"name":"avance",      "complexity":0.8, "quality_threshold":80,
         "description":"Episode complet, arc narratif, 3+ personnages"},
        {"name":"expert",      "complexity":1.0, "quality_threshold":88,
         "description":"Transmedia, multi-episodes, innovation stylistique"},
    ]

    def __init__(self, logger: logging.Logger = None):
        self.log   = logger or logging.getLogger("curriculum")
        self._level_idx  = 0
        self._scores: list[float] = []
        self._path  = LEARNING_DIR / "curriculum_state.json"
        self._load()

    def _load(self):
        if self._path.exists():
            try:
                d = json.loads(self._path.read_text(encoding="utf-8"))
                self._level_idx = d.get("level_idx", 0)
                self._scores    = d.get("scores", [])
            except Exception:
                pass

    def _save(self):
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._path.write_text(
            json.dumps({"level_idx":self._level_idx,"scores":self._scores},
                       ensure_ascii=False),
            encoding="utf-8"
        )

    def get_current(self) -> dict:
        return self.LEVELS[min(self._level_idx, len(self.LEVELS)-1)]

    def record_score(self, score: float):
        self._scores.append(score)
        self._scores = self._scores[-10:]
        current      = self.get_current()
        avg          = sum(self._scores) / len(self._scores)
        if avg >= current["quality_threshold"] and self._level_idx < len(self.LEVELS)-1:
            self._level_idx += 1
            next_level = self.get_current()
            self.log.info(f"[CURRICULUM] Niveau suivant : {next_level['name']} "
                          f"(score moyen={avg:.0f})")
            if BUS_OK:
                try:
                    get_bus().write("learning.curriculum_level",
                                    next_level["name"], agent_id="curriculum")
                except Exception:
                    pass
        self._save()

    def get_complexity_params(self) -> dict:
        level = self.get_current()
        c     = level["complexity"]
        return {
            "max_scenes":       int(2 + c * 10),
            "max_characters":   int(1 + c * 4),
            "quality_threshold":level["quality_threshold"],
            "level":            level["name"],
        }


# ── Facade LearningV120 ───────────────────────────────────────────────
class LearningV120:

    def __init__(self, logger: logging.Logger = None):
        self.log        = logger or logging.getLogger("learning_v120")
        self.reward     = RewardShaper(logger=self.log)
        self.replay     = ExperienceReplay(logger=self.log)
        self.curriculum = CurriculumScheduler(logger=self.log)

    def on_run_complete(self, run_id: str, score: float,
                        steps: list[dict] = None, metadata: dict = None):
        total_reward = self.reward.get_agent_total("pipeline")
        episode      = Episode(run_id=run_id, steps=steps or [],
                               reward=total_reward, score=score,
                               metadata=metadata or {})
        self.replay.add(episode)
        self.curriculum.record_score(score)
        insights = self.replay.get_insights()
        if BUS_OK:
            try:
                bus = get_bus()
                bus.write("learning.last_score",     score,       agent_id="learning")
                bus.write("learning.curriculum",
                          self.curriculum.get_current()["name"],  agent_id="learning")
                bus.write("learning.n_episodes",
                          insights.get("n_episodes", 0),          agent_id="learning")
            except Exception:
                pass
        return insights

    def get_production_params(self) -> dict:
        return self.curriculum.get_complexity_params()

    def get_dashboard(self) -> dict:
        return {
            "reward_summary": self.reward.get_summary(),
            "replay_insights":self.replay.get_insights(),
            "curriculum":     self.curriculum.get_current(),
        }


if __name__ == "__main__":
    import sys, io
    if hasattr(sys.stdout, 'buffer'):
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
    logging.basicConfig(level=logging.INFO)
    lv = LearningV120()
    print("=== V1.20 Learning ===")
    lv.reward.reward("sourcing", "sourcing_complete")
    lv.reward.reward("scenario", "scenario_validated", bonus=0.1)
    lv.on_run_complete("test_run_001", score=78.0)
    print(json.dumps(lv.get_dashboard(), indent=2, ensure_ascii=False))
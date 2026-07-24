"""
agents/generative_world.py -- Ov3rLoRd V1.30 -- Generative World
V1.49m : overlord_utils centralise, context_bus connecte.
V1.49p : aliases advance_run() et get_world_prompt_context() ajoutes
         pour compatibilite avec director.py.
"""

import json
import random
import time
import logging
from pathlib import Path
from datetime import datetime, timezone
from dataclasses import dataclass, field
from typing import Optional

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

WORLD_GEN_DIR = Path("workspace/generative_world")
CLAUDE_MODEL  = "claude-sonnet-4-6"


def _llm(prompt: str, system: str = "", max_tokens: int = 400) -> str:
    if UTILS_OK and fallback_llm:
        return fallback_llm(prompt, system=system, model=CLAUDE_MODEL,
                            max_tokens=max_tokens)
    return ""


# ── Aging System ──────────────────────────────────────────────────────
@dataclass
class EntityAge:
    name:          str
    birth_episode: int   = 0
    age_rate:      float = 1.0
    current_age:   float = 0.0
    milestones:    list  = field(default_factory=list)


class AgingSystem:
    def __init__(self, logger: logging.Logger = None):
        self.log    = logger or logging.getLogger("aging")
        self._ages: dict[str, EntityAge] = {}
        self._path  = WORLD_GEN_DIR / "aging.json"
        self._load()

    def _load(self):
        WORLD_GEN_DIR.mkdir(parents=True, exist_ok=True)
        if self._path.exists():
            try:
                data = json.loads(self._path.read_text(encoding="utf-8"))
                for name, d in data.items():
                    self._ages[name] = EntityAge(**d)
            except Exception:
                pass

    def _save(self):
        self._path.write_text(
            json.dumps({n: {**e.__dict__, "milestones": e.milestones}
                        for n, e in self._ages.items()},
                       ensure_ascii=False),
            encoding="utf-8"
        )

    def register(self, name: str, birth_episode: int = 0, age_rate: float = 1.0):
        self._ages[name] = EntityAge(name=name, birth_episode=birth_episode,
                                      age_rate=age_rate)
        self._save()

    def advance(self, episodes: int = 1):
        for entity in self._ages.values():
            entity.current_age += episodes * entity.age_rate
        self._save()
        if BUS_OK:
            try:
                get_bus().write("world_gen.episode_count", episodes,
                                agent_id="aging_system")
            except Exception:
                pass

    def get_age(self, name: str) -> float:
        return self._ages.get(name, EntityAge(name=name)).current_age

    def get_aging_suffix(self, name: str) -> str:
        age = self.get_age(name)
        if age < 2:   return "young, energetic"
        if age < 5:   return "mature, experienced"
        if age < 10:  return "battle-worn, weathered"
        return "aged, wise, scarred"


# ── Consequence Engine ────────────────────────────────────────────────
@dataclass
class Consequence:
    trigger_event: str
    effect:        str
    delayed_by:    int   = 0
    triggered_at:  int   = -1
    resolved:      bool  = False


class ConsequenceEngine:
    def __init__(self, logger: logging.Logger = None):
        self.log    = logger or logging.getLogger("consequence")
        self._queue: list[Consequence] = []
        self._path  = WORLD_GEN_DIR / "consequences.json"
        self._load()

    def _load(self):
        WORLD_GEN_DIR.mkdir(parents=True, exist_ok=True)
        if self._path.exists():
            try:
                data = json.loads(self._path.read_text(encoding="utf-8"))
                self._queue = [Consequence(**c) for c in data]
            except Exception:
                pass

    def _save(self):
        self._path.write_text(
            json.dumps([c.__dict__ for c in self._queue], ensure_ascii=False),
            encoding="utf-8"
        )

    def add(self, event: str, current_episode: int, delay: int = 1) -> Consequence:
        prompt = (
            f"Un evenement vient de se passer : '{event}'.\n"
            f"Genere UNE consequence narrative dans {delay} episodes.\n"
            f"JSON : {{\"effect\":\"description en 1 phrase\"}}"
        )
        raw    = _llm(prompt, max_tokens=100)
        effect = "Suite directe de : " + event
        if raw and safe_json_parse:
            ok, data, _ = safe_json_parse(raw)
            if ok and data:
                effect = data.get("effect", effect)
        c = Consequence(trigger_event=event, effect=effect,
                         delayed_by=delay, triggered_at=current_episode + delay)
        self._queue.append(c)
        self._save()
        return c

    def get_due(self, episode: int) -> list[Consequence]:
        due = [c for c in self._queue
               if not c.resolved and c.triggered_at <= episode]
        for c in due:
            c.resolved = True
        if due:
            self._save()
            if BUS_OK:
                try:
                    get_bus().write("world_gen.due_consequences",
                                    [c.effect for c in due], agent_id="consequence_engine")
                except Exception:
                    pass
        return due


# ── Faction Dynamics ──────────────────────────────────────────────────
@dataclass
class Faction:
    name:      str
    power:     float = 0.5
    influence: float = 0.5
    allies:    list  = field(default_factory=list)
    enemies:   list  = field(default_factory=list)
    ideology:  str   = ""


class FactionDynamics:
    def __init__(self, logger: logging.Logger = None):
        self.log      = logger or logging.getLogger("factions")
        self._factions: dict[str, Faction] = {}
        self._path    = WORLD_GEN_DIR / "factions.json"
        self._load()

    def _load(self):
        WORLD_GEN_DIR.mkdir(parents=True, exist_ok=True)
        if self._path.exists():
            try:
                data = json.loads(self._path.read_text(encoding="utf-8"))
                for name, d in data.items():
                    self._factions[name] = Faction(**d)
            except Exception:
                pass

    def _save(self):
        self._path.write_text(
            json.dumps({n: f.__dict__ for n,f in self._factions.items()},
                       ensure_ascii=False),
            encoding="utf-8"
        )

    def add_faction(self, name: str, power: float = 0.5, ideology: str = ""):
        self._factions[name] = Faction(name=name, power=power, ideology=ideology)
        self._save()

    def update_power(self, name: str, delta: float):
        if name in self._factions:
            f = self._factions[name]
            f.power = max(0.0, min(1.0, f.power + delta))
            self._save()

    def get_dominant(self) -> str | None:
        if not self._factions:
            return None
        return max(self._factions.items(), key=lambda x: x[1].power)[0]

    def get_tension_level(self) -> float:
        if len(self._factions) < 2:
            return 0.0
        powers = [f.power for f in self._factions.values()]
        avg    = sum(powers) / len(powers)
        return sum(abs(p - avg) for p in powers) / len(powers)

    def get_narrative_context(self) -> dict:
        ctx = {
            "dominant":      self.get_dominant(),
            "tension":       round(self.get_tension_level(), 3),
            "faction_count": len(self._factions),
        }
        if BUS_OK:
            try:
                get_bus().write("world_gen.dominant_faction", ctx["dominant"] or "",
                                agent_id="factions")
                get_bus().write("world_gen.tension",          ctx["tension"],
                                agent_id="factions")
            except Exception:
                pass
        return ctx


# ── Facade GenerativeWorld ────────────────────────────────────────────
class GenerativeWorld:

    def __init__(self, series: str = "Ov3rLoRd", logger: logging.Logger = None):
        self.log        = logger or logging.getLogger("gen_world")
        self.series     = series
        self.aging      = AgingSystem(logger=self.log)
        self.consequence= ConsequenceEngine(logger=self.log)
        self.factions   = FactionDynamics(logger=self.log)
        self._episode   = 0

    # ── Methodes principales ──────────────────────────────────────────
    def advance_episode(self):
        """Avance d'un episode et retourne les consequences declenchees."""
        self._episode += 1
        self.aging.advance(1)
        due = self.consequence.get_due(self._episode)
        return due

    def on_event(self, event: str, delay: int = 2):
        return self.consequence.add(event, self._episode, delay)

    def get_world_state(self) -> dict:
        state = {
            "episode":  self._episode,
            "factions": self.factions.get_narrative_context(),
            "ages":     {n: round(self.aging.get_age(n), 1)
                         for n in self.aging._ages},
        }
        if BUS_OK:
            try:
                get_bus().write("world_gen.episode",  self._episode, agent_id="gen_world")
                get_bus().write("world_gen.state_ts",
                                datetime.now(tz=timezone.utc).isoformat(),
                                agent_id="gen_world")
            except Exception:
                pass
        return state

    # ── Aliases pour compatibilite director.py ────────────────────────
    def advance_run(self, episode: int):
        """
        Alias de advance_episode() pour compatibilite director.py.
        Met l'episode courant a la valeur demandee.
        """
        if episode > self._episode:
            steps = episode - self._episode
            for _ in range(steps):
                self.aging.advance(1)
            self._episode = episode
            self.consequence.get_due(self._episode)
        self.log.info(f"[GEN_WORLD] Episode avance -> {self._episode}")

    def get_world_prompt_context(self) -> dict:
        """
        Alias de get_world_state() retournant un dict plat
        pour injection directe dans les prompts du director.
        """
        state   = self.get_world_state()
        faction = state["factions"]
        context = {
            "gen_world_episode":   self._episode,
            "dominant_faction":    faction.get("dominant",""),
            "world_tension":       faction.get("tension", 0.0),
            "faction_count":       faction.get("faction_count", 0),
            "aging_context":       ", ".join(
                f"{n} ({a}ep)" for n, a in list(state["ages"].items())[:3]
            ),
        }
        return context


if __name__ == "__main__":
    import sys, io
    if hasattr(sys.stdout, 'buffer'):
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    logging.basicConfig(level=logging.INFO)
    world = GenerativeWorld("Dragon Ball Ov3rLoRd")
    world.factions.add_faction("Z Fighters", power=0.7, ideology="protection")
    world.advance_run(3)
    ctx = world.get_world_prompt_context()
    print(f"Context director : {ctx}")
    print("GenerativeWorld OK")
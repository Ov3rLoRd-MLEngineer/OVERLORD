"""
agents/v140_theory_of_mind.py -- Ov3rLoRd V1.40 -- Theory of Mind
Modelise ce que les personnages SAVENT vs ce que LE SPECTATEUR sait.
V1.49o : overlord_utils centralise, context_bus connecte.
"""

import json
import time
import logging
from pathlib import Path
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

TOM_DIR      = Path("workspace/theory_of_mind")
CLAUDE_MODEL = "claude-sonnet-4-6"
log          = logging.getLogger("theory_of_mind")


def _llm(prompt: str, system: str = "", max_tokens: int = 400) -> str:
    if UTILS_OK and fallback_llm:
        return fallback_llm(prompt, system=system, model=CLAUDE_MODEL, max_tokens=max_tokens)
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


# ── Etat Mental ───────────────────────────────────────────────────────
@dataclass
class MentalState:
    character:  str
    episode:    str
    knows:      list[str]  = field(default_factory=list)  # faits connus
    believes:   list[str]  = field(default_factory=list)  # croyances (peut etre faux)
    wants:      list[str]  = field(default_factory=list)  # desirs / objectifs
    fears:      list[str]  = field(default_factory=list)  # peurs
    ignores:    list[str]  = field(default_factory=list)  # ce qu'il ne sait PAS

    def to_prompt_context(self) -> str:
        lines = [f"Etat mental de {self.character} (ep.{self.episode}) :"]
        if self.knows:    lines.append(f"  Sait    : {', '.join(self.knows[:3])}")
        if self.believes: lines.append(f"  Croit   : {', '.join(self.believes[:3])}")
        if self.wants:    lines.append(f"  Veut    : {', '.join(self.wants[:2])}")
        if self.fears:    lines.append(f"  Craint  : {', '.join(self.fears[:2])}")
        if self.ignores:  lines.append(f"  Ignore  : {', '.join(self.ignores[:3])}")
        return "\n".join(lines)


# ── Graphe de connaissance ────────────────────────────────────────────
class KnowledgeGraph:
    """Qui sait quoi a quel moment de la serie."""

    def __init__(self, series: str):
        self.series    = series
        self._states:  dict[str, dict[str, MentalState]] = {}
        self._path     = TOM_DIR / f"knowledge_{series[:20]}.json"
        TOM_DIR.mkdir(parents=True, exist_ok=True)
        self._load()

    def _load(self):
        if self._path.exists():
            try:
                data = json.loads(self._path.read_text(encoding="utf-8"))
                for ep, chars in data.items():
                    self._states[ep] = {}
                    for char, state_dict in chars.items():
                        self._states[ep][char] = MentalState(**state_dict)
            except Exception:
                pass

    def _save(self):
        data = {}
        for ep, chars in self._states.items():
            data[ep] = {}
            for char, state in chars.items():
                data[ep][char] = {
                    "character": state.character, "episode": state.episode,
                    "knows": state.knows, "believes": state.believes,
                    "wants": state.wants, "fears": state.fears,
                    "ignores": state.ignores,
                }
        self._path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

    def set_state(self, character: str, episode: str, state: MentalState):
        self._states.setdefault(episode, {})[character] = state
        self._save()

    def get_state(self, character: str, episode: str) -> Optional[MentalState]:
        return self._states.get(episode, {}).get(character)

    def generate_state(self, character: str, episode: str,
                       series_context: str = "") -> MentalState:
        """Genere un etat mental via LLM."""
        prev_ep  = str(int(episode) - 1) if episode.isdigit() and int(episode) > 1 else ""
        prev_str = ""
        if prev_ep and prev_ep in self._states:
            prev_chars = self._states[prev_ep]
            if character in prev_chars:
                prev_str = f"Etat precedent (ep.{prev_ep}) : {prev_chars[character].to_prompt_context()}"

        prompt = (
            f"Serie : {self.series}\n"
            f"Contexte : {series_context[:300]}\n"
            f"{prev_str}\n\n"
            f"Genere l'etat mental de '{character}' a l'episode {episode}.\n"
            f"JSON : {{\"character\":\"{character}\",\"episode\":\"{episode}\","
            f"\"knows\":[],\"believes\":[],\"wants\":[],\"fears\":[],\"ignores\":[]}}"
        )
        raw  = _llm(prompt, max_tokens=300)
        data = _parse(raw)
        if data:
            state = MentalState(**{k: v for k, v in data.items()
                                   if k in MentalState.__dataclass_fields__})
        else:
            state = MentalState(character=character, episode=episode)
        self.set_state(character, episode, state)
        return state


# ── Dramatic Irony Engine ─────────────────────────────────────────────
class DramaticIronyEngine:
    """
    Detecte et exploite les gaps de connaissance entre personnages.
    Dramatic irony : le spectateur sait ce que le heros ignore.
    """

    def __init__(self, kg: KnowledgeGraph, logger: logging.Logger = None):
        self.log = logger or log
        self.kg  = kg

    def find_irony_opportunities(self, episode: str,
                                  audience_knowledge: list[str]) -> list[dict]:
        """
        Cherche les situations ou l'audience en sait plus que les personnages.
        audience_knowledge : liste de faits que le spectateur connait.
        """
        opportunities = []
        states = self.kg._states.get(episode, {})

        for char, state in states.items():
            char_ignorance = state.ignores
            dramatic = [fact for fact in audience_knowledge
                        if any(ig.lower() in fact.lower()
                               for ig in char_ignorance)]
            if dramatic:
                opportunities.append({
                    "character": char,
                    "type":      "dramatic_irony",
                    "tension":   len(dramatic),
                    "facts":     dramatic[:3],
                    "prompt_hint": (
                        f"{char} agit sans savoir : {', '.join(dramatic[:2])}. "
                        f"Montrer son ignorance dans les expressions et actions."
                    ),
                })

        opportunities.sort(key=lambda x: x["tension"], reverse=True)
        if opportunities and BUS_OK:
            try:
                get_bus().write("tom.irony_count",    len(opportunities), agent_id="theory_of_mind")
                get_bus().write("tom.max_tension_char",
                                opportunities[0]["character"], agent_id="theory_of_mind")
            except Exception:
                pass

        return opportunities

    def enrich_shot_prompt(self, prompt: str, character: str,
                            episode: str) -> str:
        """Enrichit un prompt ComfyUI avec l'etat mental du personnage."""
        state = self.kg.get_state(character, episode)
        if not state:
            return prompt
        mental_ctx = state.to_prompt_context()
        llm_prompt = (
            f"Prompt ComfyUI original : {prompt}\n\n"
            f"{mental_ctx}\n\n"
            f"Adapte le prompt pour refleter l'etat mental de {character}. "
            f"Reponds UNIQUEMENT avec le prompt enrichi, sans explication."
        )
        raw = _llm(llm_prompt, max_tokens=200)
        return raw.strip() if raw else prompt


# ── Facade TheoryOfMindV140 ───────────────────────────────────────────
class TheoryOfMindV140:

    def __init__(self, series: str, logger: logging.Logger = None):
        self.log    = logger or log
        self.kg     = KnowledgeGraph(series)
        self.irony  = DramaticIronyEngine(self.kg, logger=self.log)

    def update_episode(self, episode: str, characters: list[str],
                        series_context: str = "") -> dict:
        """Genere ou met a jour les etats mentaux pour un episode."""
        states = {}
        for char in characters:
            state = self.kg.generate_state(char, episode, series_context)
            states[char] = state.to_prompt_context()
            self.log.info(f"[TOM] ep.{episode} {char} : "
                          f"{len(state.knows)} faits, {len(state.ignores)} ignorances")

        if BUS_OK:
            try:
                get_bus().write("tom.episode",          episode,           agent_id="theory_of_mind")
                get_bus().write("tom.characters_count", len(characters),   agent_id="theory_of_mind")
            except Exception:
                pass

        return states

    def get_production_context(self, episode: str,
                                audience_knowledge: list[str] = None) -> dict:
        """Contexte complet pour la production d'un episode."""
        opportunities = self.irony.find_irony_opportunities(
            episode, audience_knowledge or []
        )
        return {
            "episode":      episode,
            "irony_count":  len(opportunities),
            "top_tensions": [o["prompt_hint"] for o in opportunities[:3]],
            "characters":   list(self.kg._states.get(episode, {}).keys()),
        }


if __name__ == "__main__":
    import sys, io
    if hasattr(sys.stdout, "buffer"):
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    logging.basicConfig(level=logging.INFO)
    tom = TheoryOfMindV140("Dragon Ball Ov3rLoRd")
    print("=== V1.40 Theory of Mind ===\n")
    states = tom.update_episode("3", ["Goku","Vegeta"],
                                 "Goku ignore que Frieza est encore en vie.")
    ctx = tom.get_production_context("3",
                                      audience_knowledge=["Frieza est en vie"])
    print(f"Irony opportunities : {ctx['irony_count']}")
    if ctx["top_tensions"]:
        print(f"Top tension : {ctx['top_tensions'][0][:80]}")
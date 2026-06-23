"""
agents/v140_theory_of_mind.py — OverLord V1.40 — Theory of Mind

L'IA modélise ce que les personnages SAVENT vs ce que LE SPECTATEUR sait.

C'est la base de toute narration japonaise sophistiquée :
  - Dramatic irony  : le spectateur sait ce que le héros ignore
  - Dramatic tension: le héros pressent ce que le spectateur découvrira
  - Character depth : les personnages agissent selon leur perspective,
                      pas selon la vérité objective

Exemples concrets :
  Run 3  : Le spectateur découvre que le général est le père de Kael.
  Run 4  : Kael combat le général sans savoir qui il est.
           → Tension dramatique maximale
  Run 7  : Kael commence à douter (indices visuels dans les prompts)
  Run 10 : La révélation — expressions générées selon le choc de Kael

Sans Theory of Mind → tous les personnages agissent avec la même info.
Avec Theory of Mind → chaque personnage agit depuis SA perspective.

Composants :
  MentalState     : ce qu'un personnage croit, sait, veut, ressent
  KnowledgeGraph  : qui sait quoi à quel moment
  DramaticIronyEngine : détecter et exploiter les gaps de connaissance
  BehaviorModifier : adapter les prompts selon l'état mental
"""

import json
import time
import logging
from pathlib import Path
from dataclasses import dataclass, field
from typing import Optional
from enum import Enum
import requests

TOM_DIR       = Path("workspace/theory_of_mind")
ANTHROPIC_URL = "https://api.anthropic.com/v1/messages"
CLAUDE_MODEL  = "claude-sonnet-4-6"


def _llm(prompt: str, system: str = "", max_tokens: int = 400) -> str:
    try:
        body = {"model": CLAUDE_MODEL, "max_tokens": max_tokens,
                "messages": [{"role": "user", "content": prompt}]}
        if system:
            body["system"] = system
        r = requests.post(ANTHROPIC_URL,
                          headers={"Content-Type": "application/json"},
                          json=body, timeout=25)
        if r.status_code == 200:
            return r.json()["content"][0]["text"].strip()
    except Exception:
        pass
    return ""


class BeliefStatus(Enum):
    TRUE_AND_KNOWN   = "true_known"      # sait la vérité
    FALSE_BELIEF     = "false_belief"    # croit quelque chose de faux
    PARTIAL_KNOWLEDGE= "partial"         # sait une partie
    SUSPECTS         = "suspects"        # pressent sans certitude
    IGNORANT         = "ignorant"        # ne sait pas du tout
    HIDING           = "hiding"          # sait mais cache


@dataclass
class Belief:
    """Une croyance d'un personnage sur un fait."""
    fact_id:    str
    fact:       str         # description du fait
    truth:      str         # la vérité objective
    character_believes: str  # ce que le personnage croit
    status:     BeliefStatus
    confidence: float = 0.5  # 0=doute total, 1=certitude
    run_acquired: int = 0    # quand cette croyance s'est formée


@dataclass
class MentalState:
    """État mental complet d'un personnage à un moment donné."""
    character_id:   str
    character_name: str
    run_id:         int

    # Ce qu'il sait
    beliefs:        list[Belief] = field(default_factory=list)

    # Ce qu'il ressent (connecté à l'Emotion Engine)
    dominant_emotion: str = "neutral"
    hidden_emotion:   str = ""         # ce qu'il cache
    emotional_mask:   bool = False     # porte-t-il un masque émotionnel ?

    # Ce qu'il veut
    primary_goal:   str = ""
    hidden_agenda:  str = ""           # objectif secret
    fear:           str = ""           # sa peur profonde

    # Son niveau de conscience narrative
    knows_truth:    bool = False       # sait-il la vérité de l'histoire ?
    suspicion_level:float = 0.0        # 0=naïf, 1=tout soupçonne

    def get_behavior_tags(self) -> list[str]:
        """Tags visuels pour les prompts selon l'état mental."""
        tags = []
        if self.emotional_mask:
            tags.extend(["forced smile","hidden emotion","tense jaw","guarded expression"])
        else:
            emotion_tags = {
                "fear":     ["scared eyes","trembling","pale"],
                "anger":    ["clenched fist","intense gaze","furrowed brow"],
                "sad":      ["downcast eyes","slouched posture"],
                "joy":      ["bright smile","open posture"],
                "suspicious":["narrowed eyes","cautious stance"],
                "determined":["set jaw","focused gaze","upright posture"],
            }
            tags.extend(emotion_tags.get(self.dominant_emotion, []))

        if self.suspicion_level > 0.6:
            tags.append("wary expression")
        if self.suspicion_level > 0.8:
            tags.append("knowing look")
        return tags[:4]

    def get_dialogue_tone(self) -> str:
        """Ton des dialogues selon l'état mental."""
        if self.emotional_mask:
            return "speaks carefully, choosing words, hints at deeper meaning"
        tones = {
            "fear":      "voice trembling slightly, short sentences",
            "anger":     "intense, direct, controlled anger",
            "sad":       "soft, measured, occasional pauses",
            "suspicious":"guarded, asks indirect questions",
            "determined":"firm, clear, no hesitation",
            "hiding":    "deflects direct questions, changes subject",
        }
        emo = self.hidden_emotion or self.dominant_emotion
        return tones.get(emo, "natural, direct speech")


class KnowledgeGraph:
    """
    Graphe de connaissance : qui sait quoi à quel run.
    La vérité objective vs les croyances de chaque personnage.
    """

    def __init__(self):
        self._facts:   dict[str, dict]               = {}
        self._beliefs: dict[str, dict[str, Belief]]  = {}
        self._reveals: list[dict]                    = []

    def add_fact(self, fact_id: str, truth: str, revealed_to_audience: bool = False):
        """Ajoute un fait à l'univers."""
        self._facts[fact_id] = {
            "truth":    truth,
            "audience_knows": revealed_to_audience,
            "run_added": 0,
        }

    def set_belief(self, character_id: str, fact_id: str,
                    what_they_believe: str,
                    status: BeliefStatus,
                    confidence: float = 0.5,
                    run_id: int = 0):
        """Définit ce qu'un personnage croit sur un fait."""
        if character_id not in self._beliefs:
            self._beliefs[character_id] = {}
        fact = self._facts.get(fact_id, {})
        self._beliefs[character_id][fact_id] = Belief(
            fact_id=fact_id,
            fact=fact.get("truth","?"),
            truth=fact.get("truth","?"),
            character_believes=what_they_believe,
            status=status,
            confidence=confidence,
            run_acquired=run_id,
        )

    def reveal_to_audience(self, fact_id: str, run_id: int):
        """Révèle un fait au spectateur (pas forcément aux personnages)."""
        if fact_id in self._facts:
            self._facts[fact_id]["audience_knows"] = True
            self._reveals.append({"fact": fact_id, "run": run_id})

    def reveal_to_character(self, character_id: str, fact_id: str,
                             run_id: int):
        """Un personnage découvre la vérité."""
        if fact_id in self._facts:
            truth = self._facts[fact_id]["truth"]
            self.set_belief(character_id, fact_id, truth,
                             BeliefStatus.TRUE_AND_KNOWN, 1.0, run_id)

    def get_irony_gaps(self, run_id: int) -> list[dict]:
        """
        Identifie les gaps d'ironie dramatique :
        faits que le spectateur connaît mais pas les personnages.
        """
        gaps = []
        for fact_id, fact in self._facts.items():
            if not fact["audience_knows"]:
                continue
            ignorant_chars = []
            for char_id, beliefs in self._beliefs.items():
                belief = beliefs.get(fact_id)
                if not belief or belief.status in (BeliefStatus.IGNORANT,
                                                    BeliefStatus.FALSE_BELIEF):
                    ignorant_chars.append(char_id)
            if ignorant_chars:
                gaps.append({
                    "fact":      fact_id,
                    "truth":     fact["truth"],
                    "ignorant":  ignorant_chars,
                    "tension":   "high" if len(ignorant_chars) > 1 else "medium",
                })
        return gaps

    def get_character_perspective(self, character_id: str) -> dict:
        """Retourne le monde tel que le personnage le perçoit."""
        beliefs = self._beliefs.get(character_id, {})
        return {
            "character":  character_id,
            "knows_true": [b.fact_id for b in beliefs.values()
                           if b.status == BeliefStatus.TRUE_AND_KNOWN],
            "false_beliefs": [{
                "fact": b.fact_id,
                "believes": b.character_believes
            } for b in beliefs.values() if b.status == BeliefStatus.FALSE_BELIEF],
            "suspects": [b.fact_id for b in beliefs.values()
                         if b.status == BeliefStatus.SUSPECTS],
            "ignorant": sum(1 for b in beliefs.values()
                            if b.status == BeliefStatus.IGNORANT),
        }


class DramaticIronyEngine:
    """
    Exploite les gaps de connaissance pour créer de la tension dramatique.
    Génère des indicateurs visuels subtils — le spectateur comprend
    ce que le personnage ne voit pas encore.
    """

    IRONY_VISUAL_CUES = {
        "character_in_danger_unaware": [
            "shadow looming", "ominous background", "dramatic lighting",
            "observer in the distance", "symbolic foreshadowing"
        ],
        "false_trust_scene": [
            "unseen betrayal gesture", "hidden weapon", "subtle smirk",
            "crossed fingers behind back"
        ],
        "approaching_revelation": [
            "symbol in background", "reflective surface showing truth",
            "documentary evidence visible", "coincidental framing"
        ],
        "emotional_irony": [
            "character smiling in tragic context", "celebrating before fall",
            "peaceful scene with dark undercurrent"
        ],
    }

    def get_irony_prompt_additions(self, irony_type: str,
                                    intensity: float = 0.7) -> list[str]:
        """Retourne les tags visuels pour l'ironie dramatique."""
        cues = self.IRONY_VISUAL_CUES.get(irony_type, [])
        n    = max(1, int(len(cues) * intensity))
        return cues[:n]

    def generate_irony_shot(self, gap: dict,
                             scene_context: str) -> dict:
        """
        Génère un shot qui exploite l'ironie dramatique.
        """
        prompt = (
            f"Fait que le spectateur sait : '{gap['truth']}'\n"
            f"Personnages qui l'ignorent : {gap['ignorant']}\n"
            f"Scène actuelle : {scene_context}\n\n"
            f"Décris comment composer ce shot pour créer une ironie dramatique.\n"
            f"Le spectateur doit comprendre la vérité, pas les personnages.\n"
            f"Donne : composition, élément symbolique, éclairage, cadrage. Max 3 phrases."
        )
        description = _llm(prompt, max_tokens=200)
        irony_type  = ("character_in_danger_unaware"
                        if gap["tension"] == "high" else "approaching_revelation")
        visual_cues = self.get_irony_prompt_additions(irony_type, 0.6)

        return {
            "irony_description": description,
            "visual_cues":       visual_cues,
            "tension_level":     gap["tension"],
            "fact":              gap["truth"][:80],
        }


class BehaviorModifier:
    """
    Modifie les prompts de génération selon l'état mental des personnages.
    """

    def modify_prompt(self, base_prompt: str,
                       mental_state: MentalState,
                       scene_type: str = "action") -> str:
        """Enrichit le prompt avec les indicateurs d'état mental."""
        behavior_tags = mental_state.get_behavior_tags()
        dialogue_tone = mental_state.get_dialogue_tone()

        if not behavior_tags:
            return base_prompt

        mental_prefix = ", ".join(behavior_tags)
        return f"{mental_prefix}, {base_prompt}"

    def generate_subtext_dialogue(self, character: str,
                                    mental_state: MentalState,
                                    surface_text: str) -> dict:
        """
        Génère un dialogue avec sous-texte (ce qui est dit vs pensé).
        """
        hidden = mental_state.hidden_emotion or mental_state.dominant_emotion
        mask   = mental_state.emotional_mask
        agenda = mental_state.hidden_agenda

        prompt = (
            f"Personnage : {character}\n"
            f"Ce qu'il dit : '{surface_text}'\n"
            f"Ce qu'il ressent vraiment : {hidden}\n"
            f"Cache-t-il ses émotions : {'oui' if mask else 'non'}\n"
            + (f"Agenda secret : {agenda}\n" if agenda else "") +
            f"\nRécris ce dialogue avec du sous-texte fort. "
            f"Le texte de surface doit sembler anodin mais charger d'une tension sous-jacente. "
            f"Format JSON : {{\"text\": \"réplique finale\", \"subtext\": \"ce qui est vraiment dit\"}}"
        )
        result = _llm(prompt, max_tokens=200)
        try:
            if result.startswith("```"):
                result = "\n".join(result.split("\n")[1:-1])
            return json.loads(result)
        except Exception:
            return {"text": surface_text, "subtext": ""}


# ══════════════════════════════════════════════════════════════════════
# THEORY OF MIND SYSTEM — FAÇADE
# ══════════════════════════════════════════════════════════════════════

class TheoryOfMindSystem:
    """Système Theory of Mind complet V1.40."""

    def __init__(self, logger: logging.Logger = None):
        self.log        = logger or logging.getLogger("theory_of_mind")
        self.knowledge  = KnowledgeGraph()
        self.irony_eng  = DramaticIronyEngine()
        self.modifier   = BehaviorModifier()
        self._states:   dict[str, MentalState] = {}
        TOM_DIR.mkdir(parents=True, exist_ok=True)

    def add_character(self, char_id: str, name: str,
                       emotion: str = "neutral",
                       goal: str = "",
                       fear: str = "") -> MentalState:
        state = MentalState(
            character_id=char_id, character_name=name,
            run_id=0, dominant_emotion=emotion,
            primary_goal=goal, fear=fear,
        )
        self._states[char_id] = state
        return state

    def update_state(self, char_id: str, **kwargs):
        if char_id in self._states:
            for k, v in kwargs.items():
                if hasattr(self._states[char_id], k):
                    setattr(self._states[char_id], k, v)

    def get_scene_context(self, run_id: int,
                           characters_present: list[str]) -> dict:
        """
        Retourne le contexte Theory of Mind pour une scène.
        Ce contexte est injecté dans tous les prompts de la scène.
        """
        gaps   = self.knowledge.get_irony_gaps(run_id)
        states = {cid: self._states[cid]
                  for cid in characters_present
                  if cid in self._states}

        # Tags visuels par personnage
        char_tags = {}
        for cid, state in states.items():
            char_tags[state.character_name] = state.get_behavior_tags()

        # Ironie dramatique
        active_irony = [g for g in gaps
                         if any(c in g["ignorant"] for c in characters_present)]

        return {
            "run_id":       run_id,
            "character_states": {
                s.character_name: {
                    "emotion":      s.dominant_emotion,
                    "hiding":       s.hidden_emotion if s.emotional_mask else "",
                    "behavior_tags":s.get_behavior_tags(),
                    "dialogue_tone":s.get_dialogue_tone(),
                }
                for s in states.values()
            },
            "dramatic_irony": active_irony,
            "irony_visual_cues": (
                self.irony_eng.get_irony_prompt_additions(
                    "character_in_danger_unaware"
                ) if active_irony else []
            ),
        }

    def enrich_prompt(self, base_prompt: str,
                       character_id: str,
                       scene_context: dict = None) -> str:
        """Enrichit un prompt avec l'état mental du personnage."""
        state = self._states.get(character_id)
        if not state:
            return base_prompt
        return self.modifier.modify_prompt(base_prompt, state)

    def initialize_from_world_model(self, world_data: dict) -> int:
        """Initialise depuis les données du World Model."""
        n = 0
        for char in world_data.get("characters", []):
            self.add_character(
                char_id=char.get("id", char["name"].lower()),
                name=char["name"],
                emotion=char.get("arc_stage","introduction"),
            )
            n += 1
        self.log.info(f"[TOM] {n} personnages initialisés depuis le World Model")
        return n

    def get_dashboard(self) -> dict:
        gaps = self.knowledge.get_irony_gaps(0)
        return {
            "version":          "1.40_theory_of_mind",
            "characters":       len(self._states),
            "facts_tracked":    len(self.knowledge._facts),
            "irony_gaps":       len(gaps),
            "active_tensions":  sum(1 for g in gaps if g["tension"]=="high"),
        }


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    tom = TheoryOfMindSystem()

    print("=== V1.40 THEORY OF MIND TEST ===\n")

    # Créer les personnages
    kael = tom.add_character("kael","Kael",
                               emotion="determined", fear="perdre ceux qu'il aime")
    general = tom.add_character("general","Général Frost",
                                  emotion="sad", fear="être reconnu par son fils",
                                  goal="protéger Kael sans se révéler")
    general.hidden_emotion  = "paternal_love"
    general.emotional_mask  = True
    general.hidden_agenda   = "sabote secrètement ses propres troupes pour sauver Kael"

    # Ajouter le fait central
    tom.knowledge.add_fact("parentage",
                            "Le Général Frost est le père biologique de Kael",
                            revealed_to_audience=True)
    tom.knowledge.set_belief("kael","parentage",
                              "Le Général est un ennemi mortel",
                              BeliefStatus.FALSE_BELIEF, 0.95)
    tom.knowledge.set_belief("general","parentage",
                              "Kael est mon fils",
                              BeliefStatus.TRUE_AND_KNOWN, 1.0)

    # Contexte d'une scène de combat
    ctx = tom.get_scene_context(run_id=5,
                                  characters_present=["kael","general"])
    print("Contexte Theory of Mind — scène de combat :")
    for name, state in ctx["character_states"].items():
        print(f"\n  {name} :")
        print(f"    Émotion visible  : {state['emotion']}")
        print(f"    Émotion cachée   : {state['hiding'] or '(aucune)'}")
        print(f"    Tags comportement: {state['behavior_tags']}")
        print(f"    Ton dialogue     : {state['dialogue_tone'][:60]}")

    print(f"\nIronie dramatique active : {len(ctx['dramatic_irony'])} gap(s)")
    for gap in ctx["dramatic_irony"]:
        print(f"  • {gap['truth']} → ignoré par {gap['ignorant']} ({gap['tension']})")

    # Enrichir un prompt
    base_prompt = "Kael et le Général se font face, épées croisées"
    enriched    = tom.enrich_prompt(base_prompt, "kael", ctx)
    print(f"\nPrompt base     : {base_prompt}")
    print(f"Prompt enrichi  : {enriched}")

    # Sous-texte
    subtext = tom.modifier.generate_subtext_dialogue(
        "Général Frost", general,
        "Kael. Tu te bats bien. C'est tout ce que j'ai à dire."
    )
    print(f"\nSous-texte dialogue :")
    print(f"  Ce qui est dit   : {subtext.get('text','')}")
    print(f"  Ce qui est pensé : {subtext.get('subtext','')}")

    print(f"\nDashboard : {tom.get_dashboard()}")

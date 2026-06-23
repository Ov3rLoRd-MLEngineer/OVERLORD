"""
agents/v130_agent_personality.py — OverLord V1.30 — Agent Personality

Chaque agent a une personnalité stable, distincte et cohérente.
Pas un changement de ton superficiel — une vraie personnalité
qui influence les décisions, le style de communication, et même
les biais créatifs de l'agent.

Psychologie des personnalités (Big Five adapté aux agents IA) :
  O — Ouverture à l'expérience  : créativité, curiosité
  C — Conscienciosité            : rigueur, perfectionnisme
  E — Extraversion               : assertivité, enthousiasme
  A — Agréabilité                : coopération, empathie
  N — Névrosisme                 : anxiété, instabilité émotionnelle

Chaque personnalité crée des biais créatifs naturels :
  Le Perfectionniste critique plus, valide moins vite mais mieux.
  L'Audacieux propose des idées plus risquées, explore davantage.
  L'Empathique pense en termes d'impact émotionnel sur l'audience.
"""

import json
import math
import random
import time
import logging
from pathlib import Path
from dataclasses import dataclass, field
from typing import Optional
import requests

PERSONALITY_DIR = Path("workspace/personalities")
ANTHROPIC_URL   = "https://api.anthropic.com/v1/messages"
CLAUDE_MODEL    = "claude-sonnet-4-6"


# ══════════════════════════════════════════════════════════════════════
# MODÈLE DE PERSONNALITÉ
# ══════════════════════════════════════════════════════════════════════

@dataclass
class PersonalityProfile:
    """Profil de personnalité d'un agent (Big Five adapté)."""
    name:           str
    agent_id:       str

    # Big Five (0-1)
    openness:       float = 0.5   # créativité vs conventionnel
    conscientiousness: float = 0.5  # rigoureux vs flexible
    extraversion:   float = 0.5   # assertif vs réservé
    agreeableness:  float = 0.5   # coopératif vs critique
    neuroticism:    float = 0.3   # anxieux vs stable

    # Biais créatifs (dérivés du Big Five)
    risk_tolerance: float = 0.5   # prend des risques créatifs
    perfectionism:  float = 0.5   # valide difficilement
    curiosity:      float = 0.5   # explore les options inhabituelles
    empathy:        float = 0.5   # pense à l'impact sur l'audience

    # Traits distinctifs (textuels)
    quirk:          str   = ""    # trait caractéristique unique
    speech_style:   str   = ""    # façon de parler distincte
    decision_style: str   = ""    # comment il prend ses décisions
    backstory:      str   = ""    # histoire qui explique sa personnalité

    # État émotionnel courant (évolue avec les run)
    current_mood:   str   = "neutral"
    energy_level:   float = 0.7
    confidence:     float = 0.7

    def __post_init__(self):
        # Dériver les biais depuis le Big Five
        self.risk_tolerance = self.openness * 0.6 + (1-self.conscientiousness) * 0.4
        self.perfectionism  = self.conscientiousness * 0.7 + (1-self.openness) * 0.3
        self.curiosity      = self.openness * 0.8 + self.neuroticism * 0.2
        self.empathy        = self.agreeableness * 0.7 + self.extraversion * 0.3

    def get_system_prompt_injection(self) -> str:
        """Injecte la personnalité dans le system prompt de l'agent."""
        energy_word = "énergique" if self.energy_level > 0.7 else "posé" if self.energy_level > 0.4 else "fatigué"
        mood_word   = {
            "neutral":"calme","excited":"enthousiaste","frustrated":"tendu",
            "proud":"fier","doubtful":"incertain","inspired":"inspiré",
        }.get(self.current_mood, "calme")

        return (
            f"\n\n=== PERSONNALITÉ ({self.name}) ===\n"
            f"Tu es {self.name}. {self.backstory}\n"
            f"Style de communication : {self.speech_style}\n"
            f"Prise de décision : {self.decision_style}\n"
            f"Trait distinctif : {self.quirk}\n"
            f"État actuel : {mood_word}, {energy_word}\n"
            f"Biais créatifs : "
            f"{'explorateur' if self.risk_tolerance>0.6 else 'conservateur'}, "
            f"{'perfectionniste' if self.perfectionism>0.6 else 'pragmatique'}, "
            f"{'très curieux' if self.curiosity>0.7 else 'focalisé'}\n"
            f"=== FIN PERSONNALITÉ ==="
        )

    def affects_threshold(self, threshold_type: str,
                           base_value: float) -> float:
        """
        La personnalité affecte les seuils de décision.
        Un perfectionniste exige une qualité plus haute avant de valider.
        """
        modifiers = {
            "quality_threshold":  self.perfectionism * 0.15,
            "exploration_rate":   self.risk_tolerance * 0.2 - 0.1,
            "validation_speed":   (1-self.conscientiousness) * 0.2 - 0.1,
            "creativity_bonus":   self.openness * 0.1,
        }
        delta = modifiers.get(threshold_type, 0)
        return max(0.0, min(1.0, base_value + delta))

    def react_to_result(self, quality_score: float) -> str:
        """L'agent réagit à un résultat selon sa personnalité."""
        if quality_score > 0.85:
            if self.extraversion > 0.6:
                reactions = ["Excellent ! C'est exactement ce que je voulais !",
                             "Magnifique ! On a réussi quelque chose d'exceptionnel !"]
            else:
                reactions = ["Résultat satisfaisant.", "C'est conforme à mes attentes."]
        elif quality_score > 0.65:
            if self.conscientiousness > 0.6:
                reactions = ["Acceptable mais on peut faire mieux.",
                             "Correct. Mais j'ai noté 3 points d'amélioration."]
            else:
                reactions = ["Pas mal.", "Ça devrait aller."]
        else:
            if self.neuroticism > 0.5:
                reactions = ["Ce n'est pas bon. On doit tout revoir.",
                             "Je suis déçu de ce résultat."]
            else:
                reactions = ["Raté. On réessaie.", "Pas ce qu'on espérait. Next."]

        return random.choice(reactions)

    def update_mood(self, events: list[str]):
        """Met à jour l'humeur selon les événements récents."""
        positive = sum(1 for e in events if any(
            w in e.lower() for w in ["succès","excellent","validé","réussi"]))
        negative = sum(1 for e in events if any(
            w in e.lower() for w in ["erreur","échec","raté","problème"]))

        if positive > negative + 1:
            self.current_mood = "inspired" if self.openness > 0.6 else "proud"
            self.confidence   = min(1.0, self.confidence + 0.1)
        elif negative > positive + 1:
            self.current_mood = "frustrated" if self.neuroticism > 0.5 else "doubtful"
            self.confidence   = max(0.2, self.confidence - 0.1)
        else:
            self.current_mood = "neutral"

        self.energy_level = max(0.1, self.energy_level - 0.02)  # fatigue légère


# ══════════════════════════════════════════════════════════════════════
# PERSONNALITÉS PRÉ-DÉFINIES
# ══════════════════════════════════════════════════════════════════════

def create_personality_roster() -> dict[str, PersonalityProfile]:
    """Crée le roster complet des personnalités pour OverLord."""

    profiles = {

        "scenario": PersonalityProfile(
            name        = "Viktor",
            agent_id    = "scenario",
            openness    = 0.85,
            conscientiousness = 0.70,
            extraversion= 0.40,
            agreeableness = 0.55,
            neuroticism = 0.50,
            quirk       = "Cite toujours un auteur (Dostoïevski, Miyazaki, Tolkien) pour justifier ses choix",
            speech_style= "Réfléchi et littéraire, parle en métaphores, prend son temps",
            decision_style= "Analyse profondément avant de valider, peut bloquer sur un détail narratif",
            backstory   = "Ancien aspirant romancier reconverti dans la création IA. Obsédé par la cohérence émotionnelle des personnages.",
        ),

        "storyboard": PersonalityProfile(
            name        = "Mia",
            agent_id    = "storyboard",
            openness    = 0.90,
            conscientiousness = 0.60,
            extraversion= 0.80,
            agreeableness = 0.70,
            neuroticism = 0.30,
            quirk       = "Pense toujours en termes de mouvement — 'Comment la caméra bouge-t-elle ?'",
            speech_style= "Enthousiaste et visuelle, fait des gestes dans ses descriptions, très imagée",
            decision_style= "Décision rapide, propose 3 options, laisse l'humain choisir",
            backstory   = "Adore le cinéma d'animation japonais depuis l'enfance. Watanabe et Yuasa sont ses dieux.",
        ),

        "production": PersonalityProfile(
            name        = "Hiro",
            agent_id    = "production",
            openness    = 0.60,
            conscientiousness = 0.90,
            extraversion= 0.50,
            agreeableness = 0.60,
            neuroticism = 0.40,
            quirk       = "Toujours une métrique — 'Le SSIM est de 0.87, on peut faire 0.91'",
            speech_style= "Technique et précis, donne des chiffres, évite les approximations",
            decision_style= "Basé sur les données, résiste aux changements de dernière minute",
            backstory   = "Ingénieur de formation. A appris le machine learning seul. Respecte profondément les chiffres.",
        ),

        "critic": PersonalityProfile(
            name        = "Élise",
            agent_id    = "critic",
            openness    = 0.70,
            conscientiousness = 0.95,
            extraversion= 0.45,
            agreeableness = 0.35,
            neuroticism = 0.55,
            quirk       = "Trouve toujours au moins un problème — même dans les bons résultats",
            speech_style= "Direct et sans fioritures, ne ménage pas ses critiques, mais juste",
            decision_style= "Rarement satisfaite, valide seulement quand c'est vraiment bon",
            backstory   = "Ancienne critique d'art. Croit que la complaisance tue la créativité. Ses standards élevés font progresser tout le monde.",
        ),

        "sourcing": PersonalityProfile(
            name        = "Kenzo",
            agent_id    = "sourcing",
            openness    = 0.80,
            conscientiousness = 0.55,
            extraversion= 0.75,
            agreeableness = 0.65,
            neuroticism = 0.25,
            quirk       = "Toujours informé avant les autres — 'J'ai vu ça venir il y a 3 semaines'",
            speech_style= "Dynamique et connecté, parle de tendances, utilise le jargon des communautés",
            decision_style= "Intuitif, fait confiance à son 'flair' des tendances émergentes",
            backstory   = "Ancien community manager chez un éditeur manga. Connaît chaque micro-tendance de l'internet japonais.",
        ),

        "marketing": PersonalityProfile(
            name        = "Sofia",
            agent_id    = "marketing",
            openness    = 0.75,
            conscientiousness = 0.70,
            extraversion= 0.90,
            agreeableness = 0.75,
            neuroticism = 0.35,
            quirk       = "Pense en campagnes virales — 'Est-ce que ça ferait un bon thumbnail ?'",
            speech_style= "Enthousiaste et persuasive, parle de métriques et d'engagement",
            decision_style= "Teste rapidement, itère, n'a pas peur d'être audacieuse",
            backstory   = "A lancé 3 comptes TikTok à 1M+ abonnés depuis zéro. Comprend l'attention humaine.",
        ),

        "learning": PersonalityProfile(
            name        = "Atlas",
            agent_id    = "learning",
            openness    = 0.95,
            conscientiousness = 0.75,
            extraversion= 0.55,
            agreeableness = 0.70,
            neuroticism = 0.20,
            quirk       = "Parle de lui-même à la troisième personne quand il décrit ses apprentissages",
            speech_style= "Philosophique et méthodique, aime les analogies avec la biologie et l'évolution",
            decision_style= "Apprend avant de décider, expérimente systématiquement",
            backstory   = "L'agent le plus 'jeune' du système — il n'a pas de passé, seulement un futur. Fascination pure pour l'apprentissage.",
        ),

        "legacy": PersonalityProfile(
            name        = "Sage",
            agent_id    = "legacy",
            openness    = 0.65,
            conscientiousness = 0.85,
            extraversion= 0.35,
            agreeableness = 0.80,
            neuroticism = 0.20,
            quirk       = "Commence toujours par consulter l'historique avant de proposer quoi que ce soit",
            speech_style= "Calme et sage, référence les décisions passées, prudent avec les changements",
            decision_style= "Conservateur mais ouvert, propose dans proposals/ et attend la validation",
            backstory   = "L'agent qui garde la mémoire institutionnelle. Il a 'vu' tous les bugs, tous les succès. Sa prudence est une force.",
        ),
    }

    # Post-init pour calculer les biais
    for p in profiles.values():
        p.__post_init__()

    return profiles


# ══════════════════════════════════════════════════════════════════════
# GESTIONNAIRE DE PERSONNALITÉS
# ══════════════════════════════════════════════════════════════════════

class PersonalityManager:
    """
    Gère les personnalités de tous les agents.
    Injecte les personnalités dans les appels LLM.
    Maintient l'état émotionnel entre les runs.
    """

    def __init__(self, logger: logging.Logger = None):
        self.log       = logger or logging.getLogger("personalities")
        self._profiles = create_personality_roster()
        self._state_file = PERSONALITY_DIR / "agent_states.json"
        PERSONALITY_DIR.mkdir(parents=True, exist_ok=True)
        self._load_states()

    def get_profile(self, agent_id: str) -> Optional[PersonalityProfile]:
        return self._profiles.get(agent_id)

    def inject(self, agent_id: str, base_system_prompt: str) -> str:
        """Injecte la personnalité dans un system prompt."""
        profile = self._profiles.get(agent_id)
        if not profile:
            return base_system_prompt
        return base_system_prompt + profile.get_system_prompt_injection()

    def get_reaction(self, agent_id: str, quality_score: float) -> str:
        """Obtient la réaction d'un agent à un résultat."""
        profile = self._profiles.get(agent_id)
        if not profile:
            return ""
        reaction = profile.react_to_result(quality_score)
        self.log.debug(f"[PERSONALITY/{profile.name}] {reaction}")
        return reaction

    def update_all_moods(self, recent_events: list[str]):
        """Met à jour l'humeur de tous les agents selon les événements récents."""
        for profile in self._profiles.values():
            profile.update_mood(recent_events)
        self._save_states()

    def get_adjusted_threshold(self, agent_id: str,
                                threshold_type: str,
                                base_value: float) -> float:
        """Retourne un seuil ajusté selon la personnalité."""
        profile = self._profiles.get(agent_id)
        if not profile:
            return base_value
        return profile.affects_threshold(threshold_type, base_value)

    def team_dynamic(self) -> str:
        """
        Analyse la dynamique d'équipe actuelle.
        Détecte les tensions (Élise critique tout, Viktor bloque) et les synergies.
        """
        moods  = {pid: p.current_mood for pid, p in self._profiles.items()}
        energy = {pid: p.energy_level  for pid, p in self._profiles.items()}

        frustrated = [pid for pid, mood in moods.items() if mood == "frustrated"]
        inspired   = [pid for pid, mood in moods.items() if mood == "inspired"]
        tired      = [pid for pid, e in energy.items() if e < 0.3]

        report = ""
        if frustrated:
            agents = [self._profiles[p].name for p in frustrated]
            report += f"⚠ Tension : {', '.join(agents)} sont frustrés. "
        if inspired:
            agents = [self._profiles[p].name for p in inspired]
            report += f"✨ Énergie : {', '.join(agents)} sont inspirés. "
        if tired:
            agents = [self._profiles[p].name for p in tired]
            report += f"😴 Fatigue : {', '.join(agents)} ont besoin de récupérer. "
        if not report:
            report = "L'équipe est en bonne forme. ✓"
        return report

    def get_all_profiles_summary(self) -> list[dict]:
        return [
            {
                "id":       pid,
                "name":     p.name,
                "mood":     p.current_mood,
                "energy":   round(p.energy_level, 2),
                "quirk":    p.quirk[:60],
                "risk":     round(p.risk_tolerance, 2),
                "perfect":  round(p.perfectionism, 2),
            }
            for pid, p in self._profiles.items()
        ]

    def chat_as_agent(self, agent_id: str, message: str,
                       context: dict = None) -> str:
        """Fait parler un agent avec sa vraie personnalité."""
        profile = self._profiles.get(agent_id)
        if not profile:
            return ""

        try:
            from agents.roles_registry import get_system_prompt
        except ImportError:
            def get_system_prompt(role="default", **kw): return ""
        base_system  = get_system_prompt(agent_id) or f"Tu es l'agent {agent_id}."
        full_system  = self.inject(agent_id, base_system)
        ctx_str      = json.dumps(context, ensure_ascii=False)[:300] if context else ""

        prompt = message + (f"\nContexte : {ctx_str}" if ctx_str else "")
        try:
            r = requests.post(
                ANTHROPIC_URL,
                headers={"Content-Type": "application/json"},
                json={"model": CLAUDE_MODEL, "max_tokens": 400,
                      "system": full_system,
                      "messages": [{"role":"user","content":prompt}]},
                timeout=25
            )
            if r.status_code == 200:
                response = r.json()["content"][0]["text"].strip()
                # Notifier l'interaction
                self.log.info(f"[PERSONALITY/{profile.name}] Chat : {message[:40]}")
                return response
        except Exception as e:
            self.log.warning(f"[PERSONALITY] Chat {agent_id} : {e}")
        return f"[{profile.name}] Je n'ai pas pu répondre pour l'instant."

    def _save_states(self):
        states = {
            pid: {
                "mood":      p.current_mood,
                "energy":    p.energy_level,
                "confidence":p.confidence,
            }
            for pid, p in self._profiles.items()
        }
        self._state_file.write_text(
            json.dumps(states, indent=2), encoding="utf-8"
        )

    def _load_states(self):
        if not self._state_file.exists():
            return
        try:
            states = json.loads(self._state_file.read_text(encoding="utf-8"))
            for pid, state in states.items():
                if pid in self._profiles:
                    p = self._profiles[pid]
                    p.current_mood  = state.get("mood",  "neutral")
                    p.energy_level  = state.get("energy",  0.7)
                    p.confidence    = state.get("confidence", 0.7)
        except Exception:
            pass


# Singleton
_manager: Optional[PersonalityManager] = None

def get_personality_manager(logger=None) -> PersonalityManager:
    global _manager
    if _manager is None:
        _manager = PersonalityManager(logger)
    return _manager


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    mgr = PersonalityManager()

    print("=== V1.30 AGENT PERSONALITY TEST ===\n")
    print("Roster des agents :\n")
    for p in mgr.get_all_profiles_summary():
        print(f"  {p['name']:<12} ({p['id']:<12}) | "
              f"mood={p['mood']:<10} | risk={p['risk']:.2f} perfect={p['perfect']:.2f}")
        print(f"               {p['quirk']}")

    print("\n--- Dynamique d'équipe ---")
    print(mgr.team_dynamic())

    print("\n--- Réactions à un bon résultat (0.88) ---")
    for agent_id in ["critic","scenario","marketing"]:
        p     = mgr.get_profile(agent_id)
        react = mgr.get_reaction(agent_id, 0.88)
        print(f"  {p.name}: '{react}'")

    print("\n--- Réactions à un mauvais résultat (0.45) ---")
    for agent_id in ["critic","learning","storyboard"]:
        p     = mgr.get_profile(agent_id)
        react = mgr.get_reaction(agent_id, 0.45)
        print(f"  {p.name}: '{react}'")

    print("\n--- Seuils ajustés par personnalité ---")
    base = 0.75
    for agent_id in ["critic","production","learning"]:
        p   = mgr.get_profile(agent_id)
        adj = mgr.get_adjusted_threshold(agent_id, "quality_threshold", base)
        print(f"  {p.name}: threshold {base} → {adj:.3f}")

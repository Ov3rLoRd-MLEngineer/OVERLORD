"""
agents/cocreation.py — OverLord V1.30 — Live Co-Creation

L'humain et l'IA créent ensemble en temps réel.
Modèle : Figma appliqué à la création générative.

AVANT : tu donnes un brief → tu attends → tu reçois un résultat.
APRÈS : tu esquisses une idée → l'IA complète instantanément →
        tu ajustes → l'IA s'adapte → en direct, en continu.

Modes de co-création :
  1. Prompt Co-Edit    — tu écris, l'IA complète et enrichit en live
  2. Visual Dialogue   — tu décris un élément, l'IA propose 3 variations
  3. Narrative Branch  — tu choisis une direction, l'IA développe le reste
  4. Parameter Tuning  — sliders temps réel avec preview instantané
  5. Style Negotiation — négociation itérative du style final

Interface :
  - Latence cible < 500ms pour les suggestions textuelles
  - Aperçu visuel (mini-génération) en < 5s
  - Historique des décisions pour undo/redo sémantique
  - Annotation des raisons de chaque décision IA
"""

import json
import time
import threading
import queue
import logging
from pathlib import Path
from dataclasses import dataclass, field
from typing import Callable, Optional
from enum import Enum
import requests

COCREATION_DIR = Path("workspace/cocreation")
ANTHROPIC_URL  = "https://api.anthropic.com/v1/messages"
CLAUDE_MODEL   = "claude-sonnet-4-6"


def _llm_fast(prompt: str, system: str = "",
               max_tokens: int = 200) -> str:
    """Appel LLM rapide optimisé pour la co-création temps réel."""
    try:
        body = {
            "model":      CLAUDE_MODEL,
            "max_tokens": max_tokens,
            "messages":   [{"role": "user", "content": prompt}],
        }
        if system:
            body["system"] = system
        r = requests.post(
            ANTHROPIC_URL,
            headers={"Content-Type": "application/json"},
            json=body, timeout=15
        )
        if r.status_code == 200:
            return r.json()["content"][0]["text"].strip()
    except Exception:
        pass
    return ""


# ══════════════════════════════════════════════════════════════════════
# DÉCISIONS ET HISTORIQUE
# ══════════════════════════════════════════════════════════════════════

class DecisionType(Enum):
    PROMPT_EDIT   = "prompt_edit"
    STYLE_CHOICE  = "style_choice"
    PARAM_CHANGE  = "param_change"
    BRANCH_SELECT = "branch_select"
    HUMAN_OVERRIDE= "human_override"
    AI_SUGGESTION = "ai_suggestion"


@dataclass
class Decision:
    """Une décision prise pendant la co-création."""
    id:          str
    type:        DecisionType
    author:      str          # "human" ou "ai"
    content:     str          # ce qui a été décidé
    reasoning:   str          # pourquoi (surtout pour l'IA)
    timestamp:   float = field(default_factory=time.time)
    undone:      bool  = False
    parent_id:   str   = ""   # décision précédente (arbre)


class DecisionHistory:
    """
    Historique des décisions avec undo/redo SÉMANTIQUE.
    Undo ne revient pas juste à l'état précédent —
    il comprend POURQUOI cette décision avait été prise
    et peut proposer une alternative intelligente.
    """

    def __init__(self):
        self._decisions: list[Decision] = []
        self._current_idx = -1
        self._lock = threading.Lock()

    def record(self, decision: Decision):
        with self._lock:
            # Supprimer les décisions "futures" si on était en undo
            if self._current_idx < len(self._decisions) - 1:
                self._decisions = self._decisions[:self._current_idx+1]
            self._decisions.append(decision)
            self._current_idx = len(self._decisions) - 1

    def undo(self) -> Optional[Decision]:
        """Annule la dernière décision."""
        with self._lock:
            if self._current_idx < 0:
                return None
            decision = self._decisions[self._current_idx]
            decision.undone = True
            self._current_idx -= 1
            return decision

    def redo(self) -> Optional[Decision]:
        """Rétablit la décision annulée."""
        with self._lock:
            if self._current_idx >= len(self._decisions) - 1:
                return None
            self._current_idx += 1
            decision = self._decisions[self._current_idx]
            decision.undone = False
            return decision

    def get_context(self, last_n: int = 5) -> str:
        """Résumé des dernières décisions pour contexte LLM."""
        with self._lock:
            active = [d for d in self._decisions if not d.undone]
        recent = active[-last_n:]
        lines  = []
        for d in recent:
            author = "Humain" if d.author == "human" else "IA"
            lines.append(f"[{author}] {d.type.value}: {d.content[:80]}")
            if d.reasoning:
                lines.append(f"  → {d.reasoning[:60]}")
        return "\n".join(lines)

    def get_semantic_undo_suggestion(self) -> str:
        """Génère une suggestion intelligente après un undo."""
        if not self._decisions:
            return ""
        last = self._decisions[self._current_idx + 1] if self._current_idx + 1 < len(self._decisions) else None
        if not last:
            return ""
        return _llm_fast(
            f"Cette décision a été annulée : '{last.content}'\n"
            f"Raison originale : '{last.reasoning}'\n"
            f"Propose une alternative différente en 1 phrase.",
            max_tokens=100
        )

    @property
    def can_undo(self) -> bool:
        return self._current_idx >= 0

    @property
    def can_redo(self) -> bool:
        return self._current_idx < len(self._decisions) - 1


# ══════════════════════════════════════════════════════════════════════
# MOTEUR DE COMPLÉTION TEMPS RÉEL
# ══════════════════════════════════════════════════════════════════════

class RealtimeCompletionEngine:
    """
    Complète et enrichit les inputs humains en temps réel.
    Optimisé pour une latence < 500ms.
    """

    SYSTEM = (
        "Tu es un assistant créatif pour un pipeline d'animation anime IA. "
        "Tu complètes et enrichis les inputs de l'utilisateur de façon concise "
        "et pertinente. Tu penses en termes de production anime/manga/ComfyUI. "
        "Tes suggestions sont courtes, précises, actionnables."
    )

    def __init__(self):
        self._cache:    dict[str, str] = {}
        self._pending:  Optional[threading.Thread] = None
        self._lock      = threading.Lock()
        self._listeners: list[Callable] = []

    def add_listener(self, cb: Callable):
        """Appelé quand une complétion est prête."""
        self._listeners.append(cb)

    def _emit(self, suggestion: str, suggestion_type: str):
        for cb in self._listeners:
            try:
                cb(suggestion, suggestion_type)
            except Exception:
                pass

    def complete_prompt(self, partial: str,
                         context: dict = None) -> str:
        """
        Complète un prompt partiel avec des tags pertinents.
        Retour < 500ms via cache ou LLM rapide.
        """
        if not partial or len(partial) < 3:
            return ""

        # Cache pour éviter des appels redondants
        cache_key = partial.lower().strip()[:50]
        if cache_key in self._cache:
            return self._cache[cache_key]

        ctx_str = ""
        if context:
            ctx_str = f"Contexte : {json.dumps(context, ensure_ascii=False)[:200]}\n"

        prompt = (
            f"{ctx_str}"
            f"Prompt partiel : '{partial}'\n"
            f"Complète avec 3-5 tags ComfyUI supplémentaires pertinents. "
            f"Format : tag1, tag2, tag3 (UNIQUEMENT les tags, pas de phrase)"
        )
        result = _llm_fast(prompt, self.SYSTEM, max_tokens=80)
        if result:
            self._cache[cache_key] = result
        return result

    def suggest_variations(self, element: str,
                            n: int = 3,
                            context: dict = None) -> list[str]:
        """
        Génère N variations d'un élément créatif.
        Ex: "guerrier" → ["guerrier solitaire", "guerrier blessé", "guerrier légendaire"]
        """
        ctx_str = json.dumps(context or {}, ensure_ascii=False)[:200]
        prompt  = (
            f"Élément : '{element}'\n"
            f"Contexte : {ctx_str}\n"
            f"Génère {n} variations créatives pour une production anime. "
            f"Chaque variation en 5 mots max. Réponds : var1 | var2 | var3"
        )
        result = _llm_fast(prompt, self.SYSTEM, max_tokens=100)
        if result:
            parts = [v.strip() for v in result.split("|") if v.strip()]
            return parts[:n]
        return [element] * n

    def develop_branch(self, direction: str,
                        current_state: dict) -> dict:
        """
        Développe une direction narrative choisie par l'humain.
        L'IA prend en charge tout le développement de cette branche.
        """
        state_str = json.dumps(current_state, ensure_ascii=False)[:400]
        prompt    = (
            f"État actuel de la production :\n{state_str}\n\n"
            f"L'humain a choisi cette direction : '{direction}'\n\n"
            f"Développe cette branche narrative avec :\n"
            f"- Suite du scénario (2 phrases)\n"
            f"- Shot suivant suggéré (description)\n"
            f"- Emotion dominante\n"
            f"- Tags visuels clés\n\n"
            f"Réponds en JSON : {{\"scenario_next\":\"...\",\"next_shot\":\"...\","
            f"\"emotion\":\"...\",\"visual_tags\":[\"...\",\"...\"]}}"
        )
        result = _llm_fast(prompt, self.SYSTEM, max_tokens=300)
        try:
            if result.startswith("```"):
                result = "\n".join(result.split("\n")[1:-1])
            return json.loads(result)
        except Exception:
            return {"scenario_next": direction, "next_shot": "",
                    "emotion": "neutral", "visual_tags": []}

    def negotiate_style(self, human_wants: str,
                         ai_suggestion: str,
                         context: dict = None) -> dict:
        """
        Négocie un compromis entre ce que l'humain veut
        et ce que l'IA suggère.
        """
        prompt = (
            f"L'humain veut : '{human_wants}'\n"
            f"L'IA suggère  : '{ai_suggestion}'\n"
            f"Contexte      : {json.dumps(context or {}, ensure_ascii=False)[:200]}\n\n"
            f"Propose un compromis créatif qui respecte l'intention humaine "
            f"tout en intégrant les forces de la suggestion IA. "
            f"Réponds en JSON : {{\"compromise\":\"...\",\"keeps_from_human\":\"...\","
            f"\"keeps_from_ai\":\"...\",\"tags\":[\"...\"]}}"
        )
        result = _llm_fast(prompt, self.SYSTEM, max_tokens=250)
        try:
            if result.startswith("```"):
                result = "\n".join(result.split("\n")[1:-1])
            return json.loads(result)
        except Exception:
            return {"compromise": human_wants, "keeps_from_human": human_wants,
                    "keeps_from_ai": "", "tags": []}


# ══════════════════════════════════════════════════════════════════════
# SESSION DE CO-CRÉATION
# ══════════════════════════════════════════════════════════════════════

class CoCreationSession:
    """
    Une session de co-création entre l'humain et l'IA.
    Maintient l'état partagé, les décisions, les variations.
    """

    def __init__(self, session_id: str,
                 project_name: str = "",
                 logger: logging.Logger = None):
        self.session_id  = session_id
        self.project     = project_name
        self.log         = logger or logging.getLogger("cocreation")
        self.history     = DecisionHistory()
        self.completion  = RealtimeCompletionEngine()
        self._state      = {
            "positive":   "",
            "negative":   "bad quality, worst quality, deformed",
            "style":      "",
            "characters": [],
            "emotion":    "neutral",
            "params":     {"cfg": 6.0, "steps": 28, "sampler": "euler_ancestral"},
            "approved":   False,
        }
        self._listeners: list[Callable] = []
        COCREATION_DIR.mkdir(parents=True, exist_ok=True)
        self.log.info(f"[COCREATION] Session {session_id} démarrée")

    def add_listener(self, cb: Callable):
        """Callback appelé à chaque changement d'état."""
        self._listeners.append(cb)

    def _emit(self, event: str, data: dict):
        for cb in self._listeners:
            try:
                cb(event, data)
            except Exception:
                pass

    # ── Actions humaines ──────────────────────────────────────────────

    def human_types(self, text: str) -> dict:
        """
        L'humain tape du texte — l'IA complète en temps réel.
        Retourne une suggestion immédiate.
        """
        suggestion = self.completion.complete_prompt(text, self._state)
        decision   = Decision(
            id=f"d_{int(time.time()*1000)}",
            type=DecisionType.PROMPT_EDIT,
            author="human",
            content=text,
            reasoning="Input direct humain",
        )
        self.history.record(decision)
        self._state["positive"] = text
        result = {"text": text, "ai_suggestion": suggestion, "can_undo": self.history.can_undo}
        self._emit("human_typed", result)
        return result

    def human_chooses_direction(self, direction: str) -> dict:
        """L'humain choisit une direction narrative."""
        developed = self.completion.develop_branch(direction, self._state)
        decision  = Decision(
            id=f"d_{int(time.time()*1000)}",
            type=DecisionType.BRANCH_SELECT,
            author="human",
            content=direction,
            reasoning="Choix de direction narrative",
        )
        self.history.record(decision)
        # L'IA enregistre aussi sa contribution
        ai_decision = Decision(
            id=f"d_{int(time.time()*1000)+1}",
            type=DecisionType.AI_SUGGESTION,
            author="ai",
            content=str(developed),
            reasoning=f"Développement de la branche '{direction}'",
        )
        self.history.record(ai_decision)
        if developed.get("emotion"):
            self._state["emotion"] = developed["emotion"]
        if developed.get("visual_tags"):
            current_tags = self._state["positive"]
            new_tags     = ", ".join(developed["visual_tags"])
            self._state["positive"] = f"{current_tags}, {new_tags}".strip(", ")
        result = {"direction": direction, "development": developed,
                  "state": self._state}
        self._emit("direction_chosen", result)
        return result

    def human_adjusts_param(self, param: str, value) -> dict:
        """L'humain ajuste un paramètre (slider)."""
        old_value = self._state["params"].get(param)
        self._state["params"][param] = value
        decision  = Decision(
            id=f"d_{int(time.time()*1000)}",
            type=DecisionType.PARAM_CHANGE,
            author="human",
            content=f"{param}={value}",
            reasoning=f"Ajustement de {param}: {old_value} → {value}",
        )
        self.history.record(decision)
        result = {"param": param, "old": old_value, "new": value}
        self._emit("param_adjusted", result)
        return result

    def human_overrides_ai(self, what: str, original_ai: str,
                            human_version: str) -> dict:
        """L'humain remplace une suggestion IA."""
        decision = Decision(
            id=f"d_{int(time.time()*1000)}",
            type=DecisionType.HUMAN_OVERRIDE,
            author="human",
            content=human_version,
            reasoning=f"Override de '{original_ai[:40]}' par l'humain",
        )
        self.history.record(decision)
        result = {"what": what, "ai_had": original_ai, "human_chose": human_version}
        self._emit("human_override", result)
        return result

    def undo(self) -> dict:
        """Annule la dernière décision avec suggestion alternative."""
        undone = self.history.undo()
        if not undone:
            return {"success": False, "message": "Rien à annuler"}
        suggestion = self.history.get_semantic_undo_suggestion()
        result = {
            "success":    True,
            "undone":     undone.content,
            "suggestion": suggestion,
            "can_undo":   self.history.can_undo,
            "can_redo":   self.history.can_redo,
        }
        self._emit("undo", result)
        return result

    def redo(self) -> dict:
        """Rétablit la dernière décision annulée."""
        redone = self.history.redo()
        if not redone:
            return {"success": False}
        result = {"success": True, "redone": redone.content,
                  "can_undo": self.history.can_undo, "can_redo": self.history.can_redo}
        self._emit("redo", result)
        return result

    # ── Actions IA proactives ─────────────────────────────────────────

    def ai_suggests_variations(self, element: str = None) -> list[dict]:
        """L'IA propose des variations proactivement."""
        element  = element or self._state.get("positive","scène anime")
        variants = self.completion.suggest_variations(element, n=3, context=self._state)
        result   = [{"variation": v, "index": i} for i, v in enumerate(variants)]
        self._emit("ai_variations", {"element": element, "variations": result})
        return result

    def ai_critiques_state(self) -> dict:
        """L'IA critique l'état actuel et propose des améliorations."""
        state_str = json.dumps(self._state, ensure_ascii=False)[:400]
        prompt    = (
            f"État actuel de la co-création :\n{state_str}\n\n"
            f"Identifie 2 améliorations concrètes. "
            f"Réponds en JSON : {{\"critiques\":[{{\"issue\":\"...\",\"fix\":\"...\"}}]}}"
        )
        result = _llm_fast(prompt, max_tokens=250)
        try:
            if result.startswith("```"):
                result = "\n".join(result.split("\n")[1:-1])
            return json.loads(result)
        except Exception:
            return {"critiques": []}

    def negotiate_style(self, human_wants: str,
                         ai_idea: str = None) -> dict:
        """Négocie le style entre humain et IA."""
        if not ai_idea:
            ai_idea = self.completion.complete_prompt(human_wants, self._state)
        return self.completion.negotiate_style(
            human_wants, ai_idea, self._state
        )

    # ── État et export ────────────────────────────────────────────────

    def get_state(self) -> dict:
        return dict(self._state)

    def approve_and_export(self) -> dict:
        """L'humain valide l'état final — prêt pour la production."""
        self._state["approved"] = True
        export = {
            "session_id":  self.session_id,
            "project":     self.project,
            "positive":    self._state["positive"],
            "negative":    self._state["negative"],
            "params":      self._state["params"],
            "emotion":     self._state["emotion"],
            "n_decisions": len(self.history._decisions),
            "context":     self.history.get_context(last_n=5),
            "approved_at": time.time(),
        }
        # Sauvegarder
        (COCREATION_DIR / f"{self.session_id}.json").write_text(
            json.dumps(export, indent=2, ensure_ascii=False), encoding="utf-8"
        )
        self.log.info(
            f"[COCREATION] Session {self.session_id} validée | "
            f"{len(self.history._decisions)} décisions"
        )
        self._emit("approved", export)
        return export

    def get_decision_summary(self) -> dict:
        """Résumé de toutes les décisions prises."""
        all_d  = self.history._decisions
        human  = sum(1 for d in all_d if d.author=="human" and not d.undone)
        ai     = sum(1 for d in all_d if d.author=="ai"    and not d.undone)
        undone = sum(1 for d in all_d if d.undone)
        return {
            "total":   len(all_d),
            "human":   human,
            "ai":      ai,
            "undone":  undone,
            "context": self.history.get_context(last_n=3),
        }


# ══════════════════════════════════════════════════════════════════════
# MANAGER DE SESSIONS
# ══════════════════════════════════════════════════════════════════════

class CoCreationManager:
    """Gère plusieurs sessions de co-création simultanées."""

    def __init__(self, logger: logging.Logger = None):
        self.log      = logger or logging.getLogger("cocreation_mgr")
        self._sessions: dict[str, CoCreationSession] = {}

    def new_session(self, project: str = "") -> CoCreationSession:
        """Crée une nouvelle session."""
        session_id = f"cocreate_{int(time.time())}"
        session    = CoCreationSession(session_id, project, self.log)
        self._sessions[session_id] = session
        return session

    def get_session(self, session_id: str) -> Optional[CoCreationSession]:
        return self._sessions.get(session_id)

    def list_sessions(self) -> list[dict]:
        return [
            {"id": sid, "project": s.project,
             "approved": s._state.get("approved", False),
             "n_decisions": len(s.history._decisions)}
            for sid, s in self._sessions.items()
        ]


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    mgr     = CoCreationManager()
    session = mgr.new_session("Dragon Ball Test")

    print("=== V1.30 LIVE CO-CREATION TEST ===\n")
    print("Simulation d'une session de co-création :\n")

    # 1. L'humain tape un début de prompt
    r1 = session.human_types("guerrier anime, cicatrice, pose héroïque")
    print(f"Humain tape : '{r1['text']}'")
    print(f"IA complète : '{r1['ai_suggestion'][:80]}'")

    # 2. L'humain choisit une direction narrative
    r2 = session.human_chooses_direction("scène de combat final au coucher du soleil")
    print(f"\nDirection choisie : '{r2['direction']}'")
    if r2["development"]:
        print(f"IA développe → émotion: {r2['development'].get('emotion','?')}")
        print(f"  Tags visuels: {r2['development'].get('visual_tags',[])[:3]}")

    # 3. L'IA propose des variations
    variations = session.ai_suggests_variations()
    print(f"\nVariations IA :")
    for v in variations:
        print(f"  [{v['index']+1}] {v['variation']}")

    # 4. Ajustement paramètre
    session.human_adjusts_param("cfg", 7.5)
    print(f"\nCFG ajusté à 7.5")

    # 5. Undo
    r_undo = session.undo()
    print(f"\nUndo : '{r_undo['undone'][:50]}'")
    if r_undo.get("suggestion"):
        print(f"Suggestion alternative : '{r_undo['suggestion'][:80]}'")

    # 6. Validation finale
    export = session.approve_and_export()
    print(f"\nValidé ! {export['n_decisions']} décisions → prêt pour production")
    print(f"Contexte : {export['context'][:150]}")

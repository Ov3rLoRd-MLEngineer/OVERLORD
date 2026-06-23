"""
agents/neural_orchestrator.py — Orchestrateur Neuronal OverLord
Remplace le pipeline séquentiel par un graphe d'attention dynamique.

Inspiré directement de l'architecture Transformer :

  Claude              →  OverLord Neural Orchestrator
  ────────────────────────────────────────────────────
  Context Window      →  ContextBus (context_bus.py)
  Multi-Head Attention→  MultiAttentionAnalyzer
  Chain of Thought    →  ThoughtChain (trace visible)
  Constitution        →  PipelineConstitution
  RLHF                →  HumanFeedbackLoop
  Token Streaming     →  Progressive generation
  Residual connections→  Parallel agent execution + merge

Le pipeline OverLord passe de :
  [A] → [B] → [C] → [D]   (séquentiel, bloquant)

À :
  [A] ──┐
  [B] ──┼──→ [ATTENTION + CONSENSUS] ──→ [CONSTITUTION CHECK] ──→ [OUTPUT]
  [C] ──┘
  (parallèle, avec pondération par confiance et historique)
"""

import json
import logging
import threading
import time
import queue
from pathlib import Path
from datetime import datetime
from dataclasses import dataclass, field
from typing import Callable, Optional, Any
from enum import Enum
import requests

# Imports des composants neuraux
try:
    from context_bus import ContextBus, ContextLayer, get_bus
    BUS_OK = True
except ImportError:
    BUS_OK = False

try:
    from pipeline_constitution import PipelineConstitution, get_constitution
    CONST_OK = True
except ImportError:
    CONST_OK = False

ANTHROPIC_URL = "https://api.anthropic.com/v1/messages"

def _get_api_key() -> str:
    import os as _os
    from pathlib import Path as _P
    key = _os.environ.get("ANTHROPIC_API_KEY", "")
    if not key:
        for env in [_P(__file__).parent / ".env", _P(".env")]:
            if env.exists():
                for line in env.read_text(encoding="utf-8").splitlines():
                    if line.startswith("ANTHROPIC_API_KEY="):
                        key = line.split("=",1)[1].strip().strip('"').strip("'")
                        if key: break
            if key: break
    return key

CLAUDE_MODEL  = "claude-sonnet-4-6"
THOUGHT_DIR   = Path("workspace/thoughts")
FEEDBACK_DIR  = Path("workspace/feedback")


# ══════════════════════════════════════════════════════════════════════
# CHAIN OF THOUGHT
# ══════════════════════════════════════════════════════════════════════

@dataclass
class Thought:
    """Un pas de raisonnement d'un agent — équivalent d'un token de pensée."""
    agent:      str
    step:       int
    reasoning:  str
    conclusion: str
    confidence: float = 0.8
    timestamp:  float = field(default_factory=time.time)


class ThoughtChain:
    """
    Trace visible du raisonnement de chaque agent.
    Équivalent de mon chain-of-thought : je réfléchis étape par étape
    avant de répondre, et ici chaque agent laisse une trace exploitable.
    """

    def __init__(self, agent_name: str, run_id: str):
        self.agent    = agent_name
        self.run_id   = run_id
        self._thoughts: list[Thought] = []
        self._lock    = threading.Lock()
        THOUGHT_DIR.mkdir(parents=True, exist_ok=True)

    def think(self, reasoning: str,
               conclusion: str,
               confidence: float = 0.8) -> Thought:
        """Enregistre un pas de raisonnement."""
        with self._lock:
            step = len(self._thoughts) + 1
        t = Thought(
            agent=self.agent, step=step,
            reasoning=reasoning, conclusion=conclusion,
            confidence=confidence,
        )
        with self._lock:
            self._thoughts.append(t)
        # Publier dans le context bus
        if BUS_OK:
            get_bus().write(
                self.agent,
                f"thought_{self.agent}_{step}",
                {"reasoning": reasoning[:200], "conclusion": conclusion[:100]},
                layer=ContextLayer.SEMANTIC,
                confidence=confidence,
                ttl_s=7200,
                importance=0.6,
            )
        return t

    def get_chain(self) -> list[Thought]:
        with self._lock:
            return list(self._thoughts)

    def summarize(self) -> str:
        """Résumé du raisonnement complet."""
        chain = self.get_chain()
        if not chain:
            return "Aucun raisonnement enregistré."
        lines = [f"Raisonnement de {self.agent} ({len(chain)} étapes) :"]
        for t in chain:
            lines.append(f"  [{t.step}] {t.reasoning[:80]} → {t.conclusion[:60]}")
        return "\n".join(lines)

    def save(self):
        path = THOUGHT_DIR / f"{self.run_id}_{self.agent}.json"
        data = [{"step": t.step, "reasoning": t.reasoning,
                  "conclusion": t.conclusion, "confidence": t.confidence,
                  "timestamp": t.timestamp}
                for t in self._thoughts]
        path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")


# ══════════════════════════════════════════════════════════════════════
# MULTI-HEAD ATTENTION
# ══════════════════════════════════════════════════════════════════════

@dataclass
class AttentionHead:
    """Une tête d'attention — un agent qui analyse une dimension spécifique."""
    name:       str
    role:       str    # ce qu'il analyse
    fn:         Callable
    weight:     float = 1.0    # poids de cette tête dans le consensus
    result:     Any   = None
    confidence: float = 0.0
    duration_s: float = 0.0
    error:      str   = ""


class MultiHeadAttention:
    """
    Analyse multi-tête — N agents analysent le même input en parallèle.

    Inspiré du multi-head attention de Transformer :
    - Chaque "tête" se spécialise sur un aspect différent
    - Les résultats sont pondérés et fusionnés
    - Le consensus émerge de toutes les perspectives

    Exemple pour un brief créatif :
      Tête 1 : analyse narrative (quel arc dramatique ?)
      Tête 2 : analyse visuelle (quel style ComfyUI ?)
      Tête 3 : analyse audience (qui va regarder ?)
      Tête 4 : analyse tendances (qu'est-ce qui marche ?)
      → Consensus : brief enrichi par 4 perspectives simultanées
    """

    def __init__(self, logger: logging.Logger = None):
        self.log    = logger or logging.getLogger("multi_attention")
        self._heads: list[AttentionHead] = []

    def add_head(self, name: str, role: str,
                  fn: Callable, weight: float = 1.0):
        """Ajoute une tête d'attention."""
        self._heads.append(AttentionHead(
            name=name, role=role, fn=fn, weight=weight
        ))

    def attend(self, input_data: dict,
               timeout_s: float = 30.0) -> dict:
        """
        Lance toutes les têtes en parallèle sur le même input.
        Fusionne les résultats avec attention pondérée.
        """
        if not self._heads:
            return {"error": "no_heads_defined"}

        self.log.info(
            f"[ATTENTION] Analyse multi-tête : "
            f"{len(self._heads)} têtes | input={list(input_data.keys())}"
        )

        results = {}
        threads = []
        result_queue = queue.Queue()

        def _run_head(head: AttentionHead):
            start = time.time()
            try:
                result     = head.fn(input_data)
                head.result     = result
                head.confidence = result.get("confidence", 0.8) if isinstance(result, dict) else 0.8
                head.duration_s = time.time() - start
                result_queue.put(("ok", head))
                self.log.debug(
                    f"[ATTENTION/{head.name}] ✓ {head.duration_s:.1f}s "
                    f"conf={head.confidence:.2f}"
                )
            except Exception as e:
                head.error      = str(e)
                head.confidence = 0.0
                result_queue.put(("error", head))
                self.log.warning(f"[ATTENTION/{head.name}] ✗ {e}")

        for head in self._heads:
            t = threading.Thread(target=_run_head, args=(head,), daemon=True)
            t.start(); threads.append(t)

        for t in threads:
            t.join(timeout=timeout_s)

        # Collecter les résultats
        successful = [h for h in self._heads if not h.error and h.result is not None]

        if not successful:
            return {"error": "all_heads_failed", "n_heads": len(self._heads)}

        # Fusion par attention pondérée
        merged = self._weighted_merge(successful, input_data)

        # Publier dans le context bus
        if BUS_OK:
            bus = get_bus()
            for head in successful:
                if isinstance(head.result, dict):
                    for k, v in head.result.items():
                        if k != "confidence":
                            bus.write(
                                head.name, k, v,
                                layer=ContextLayer.SEMANTIC,
                                confidence=head.confidence * head.weight,
                                importance=head.weight / len(self._heads),
                            )

        return {
            "heads_run":   len(self._heads),
            "heads_ok":    len(successful),
            "merged":      merged,
            "attention_weights": {
                h.name: round(h.weight * h.confidence, 3)
                for h in successful
            },
            "duration_s":  max((h.duration_s for h in self._heads), default=0),
        }

    def _weighted_merge(self, heads: list[AttentionHead],
                         input_data: dict) -> dict:
        """Fusionne les résultats pondérés de toutes les têtes."""
        merged = {}
        total_weight = sum(h.weight * h.confidence for h in heads)

        for head in heads:
            if not isinstance(head.result, dict):
                continue
            w = (head.weight * head.confidence) / (total_weight or 1)
            for key, value in head.result.items():
                if key == "confidence":
                    continue
                if key not in merged:
                    merged[key] = {"values": [], "weights": [], "source": []}
                merged[key]["values"].append(value)
                merged[key]["weights"].append(w)
                merged[key]["source"].append(head.name)

        # Résoudre chaque clé
        result = {}
        for key, data in merged.items():
            values  = data["values"]
            weights = data["weights"]
            # Numérique → moyenne pondérée
            if all(isinstance(v, (int, float)) for v in values):
                total = sum(weights)
                result[key] = round(sum(v*w for v,w in zip(values,weights)) / (total or 1), 4)
            # Texte → valeur la plus pondérée
            elif all(isinstance(v, str) for v in values):
                best_idx = weights.index(max(weights))
                result[key] = values[best_idx]
                result[f"{key}_sources"] = data["source"]
            # Listes → union
            elif all(isinstance(v, list) for v in values):
                combined = []
                for v in values:
                    combined.extend(v)
                result[key] = list(dict.fromkeys(combined))  # dédup, ordre préservé
            # Autres → priorité au plus confiant
            else:
                best_idx  = weights.index(max(weights))
                result[key] = values[best_idx]
        return result


# ══════════════════════════════════════════════════════════════════════
# HUMAN FEEDBACK LOOP (RLHF-like)
# ══════════════════════════════════════════════════════════════════════

class HumanFeedbackLoop:
    """
    Boucle de feedback humain — inspiré du RLHF de Claude.
    Tes préférences améliorent DIRECTEMENT les paramètres du pipeline.

    Analogie :
      Claude RLHF  → feedback humain → meilleure réponse
      OverLord     → feedback humain → meilleurs paramètres + prompts

    Usage :
      feedback.rate(run_id, 8.5/10, liked=["composition","couleurs"],
                    disliked=["flou", "mauvaises mains"])
    """

    def __init__(self, logger: logging.Logger = None):
        self.log = logger or logging.getLogger("rlhf")
        self._feedback: list[dict] = []
        self._preferences: dict    = {}
        self._param_adjustments: dict = {}
        FEEDBACK_DIR.mkdir(parents=True, exist_ok=True)
        self._load()

    def rate(self, run_id: str, score: float,
              liked: list[str]    = None,
              disliked: list[str] = None,
              comments: str = "") -> dict:
        """
        Note un run et extrait les préférences.
        score : 0-10
        liked : aspects positifs ("composition", "couleurs", "style", "personnage")
        disliked : aspects négatifs ("flou", "mains", "anatomie", "fond")
        """
        liked    = liked    or []
        disliked = disliked or []

        entry = {
            "run_id":    run_id,
            "score":     score,
            "liked":     liked,
            "disliked":  disliked,
            "comments":  comments,
            "timestamp": datetime.utcnow().isoformat(),
        }
        self._feedback.append(entry)

        # Apprendre des préférences
        adjustments = self._learn_from_feedback(entry)
        self.log.info(
            f"[RLHF] Feedback {score}/10 pour {run_id} | "
            f"likes={liked} | dislikes={disliked}"
        )

        # Publier dans le bus de contexte
        if BUS_OK:
            bus = get_bus()
            bus.write("human_feedback", "last_score",      score,
                      ContextLayer.FEEDBACK, confidence=1.0,
                      importance=1.0, ttl_s=86400)
            bus.write("human_feedback", "liked_aspects",   liked,
                      ContextLayer.FEEDBACK, confidence=1.0, importance=0.9)
            bus.write("human_feedback", "disliked_aspects",disliked,
                      ContextLayer.FEEDBACK, confidence=1.0, importance=0.9)

        # Enregistrer dans la constitution
        if CONST_OK:
            const = get_constitution()
            for d in disliked:
                const.set_preference(f"avoid_{d}", d, pref_type="avoid")

        self._save()
        return {**entry, "adjustments": adjustments}

    def _learn_from_feedback(self, entry: dict) -> dict:
        """
        Extrait des ajustements de paramètres depuis le feedback.
        Inspiré du policy gradient de RLHF.
        """
        adjustments = {}
        score       = entry["score"]
        liked       = entry["liked"]
        disliked    = entry["disliked"]

        # Mapping feedback → paramètres ComfyUI
        feedback_param_map = {
            "flou":           {"denoising": -0.05, "steps": +2},
            "trop_détaillé":  {"denoising": +0.05, "detail_lora_strength": -0.1},
            "mains":          {"enable_hand_detailer": True},
            "anatomie":       {"cfg": -0.5, "steps": +4},
            "couleurs_ternes":{"saturation_boost": +0.1},
            "trop_saturé":    {"saturation_boost": -0.1},
            "composition":    {"cfg": +0.3},
            "style_parfait":  {"style_lora_strength": +0.1},
            "personnage":     {"character_lora_strength": +0.05},
            "fond":           {"background_weight": -0.1},
        }

        lr = 0.1  # learning rate
        for d in disliked:
            for key, adj in feedback_param_map.items():
                if key in d.lower():
                    for param, delta in adj.items():
                        current = self._param_adjustments.get(param, 0.0)
                        self._param_adjustments[param] = current - delta * lr
                        adjustments[param] = self._param_adjustments[param]

        for l in liked:
            for key, adj in feedback_param_map.items():
                if key in l.lower():
                    for param, delta in adj.items():
                        current = self._param_adjustments.get(param, 0.0)
                        self._param_adjustments[param] = current + delta * lr * 0.5
                        adjustments[param] = self._param_adjustments[param]

        return adjustments

    def get_preferred_params(self) -> dict:
        """Retourne les paramètres ajustés par le feedback humain."""
        return dict(self._param_adjustments)

    def get_report(self) -> dict:
        """Rapport sur les feedbacks collectés."""
        if not self._feedback:
            return {"n_feedbacks": 0, "avg_score": 0}
        scores   = [f["score"] for f in self._feedback]
        all_liked    = [item for f in self._feedback for item in f["liked"]]
        all_disliked = [item for f in self._feedback for item in f["disliked"]]

        def top_n(items, n=5):
            counts = {}
            for i in items: counts[i] = counts.get(i,0) + 1
            return sorted(counts.items(), key=lambda x: -x[1])[:n]

        return {
            "n_feedbacks":     len(self._feedback),
            "avg_score":       round(sum(scores)/len(scores), 2),
            "best_score":      max(scores),
            "worst_score":     min(scores),
            "top_liked":       top_n(all_liked),
            "top_disliked":    top_n(all_disliked),
            "param_adjustments": self._param_adjustments,
        }

    def generate_preference_prompt(self) -> str:
        """
        Génère un paragraphe de préférences à injecter dans les prompts.
        Comme mes guidelines RLHF guident mes réponses.
        """
        if not self._feedback:
            return ""

        report       = self.get_report()
        top_liked    = [k for k,_ in report.get("top_liked",[])[:3]]
        top_disliked = [k for k,_ in report.get("top_disliked",[])[:3]]

        lines = []
        if top_liked:
            lines.append(f"L'utilisateur AIME : {', '.join(top_liked)}")
        if top_disliked:
            lines.append(f"L'utilisateur ÉVITE : {', '.join(top_disliked)}")
        return " | ".join(lines) if lines else ""

    def _save(self):
        data = {
            "feedback":          self._feedback[-200:],
            "preferences":       self._preferences,
            "param_adjustments": self._param_adjustments,
        }
        (FEEDBACK_DIR / "rlhf_data.json").write_text(
            json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8"
        )

    def _load(self):
        f = FEEDBACK_DIR / "rlhf_data.json"
        if f.exists():
            try:
                data = json.loads(f.read_text(encoding="utf-8"))
                self._feedback         = data.get("feedback", [])
                self._preferences      = data.get("preferences", {})
                self._param_adjustments = data.get("param_adjustments", {})
            except Exception:
                pass


# ══════════════════════════════════════════════════════════════════════
# PROMPT DECOMPOSER
# ══════════════════════════════════════════════════════════════════════

class PromptDecomposer:
    """
    Décomposition sémantique des prompts complexes.
    Inspiré de la tokenisation + parsing sémantique que j'effectue
    sur chaque input avant de répondre.

    'scène de bataille épique au coucher du soleil avec 3 guerriers anime'
    →
    [sujet: 3 guerriers anime] + [action: bataille] + [ambiance: épique]
    + [éclairage: coucher de soleil] + [style: anime] + [composition: multi-personnages]
    →
    Prompts optimisés séparément pour chaque dimension + tags ComfyUI enrichis
    """

    DIMENSIONS = [
        "sujet_principal",   # personnages, objets
        "action",            # ce qui se passe
        "ambiance",          # émotion, tension
        "eclairage",         # lumière, heure du jour
        "style_visuel",      # anime, réaliste, cartoon
        "composition",       # plan, angle, distance
        "palette_couleurs",  # tons dominants
        "details_techniques",# résolution, qualité
    ]

    def decompose(self, prompt: str,
                   media_type: str = "anime") -> dict:
        """
        Décompose un prompt en dimensions sémantiques.
        Génère des tags ComfyUI optimisés pour chaque dimension.
        """
        try:
            resp = requests.post(
                ANTHROPIC_URL,
                headers={
                "Content-Type": "application/json",
                "x-api-key": _get_api_key(),
                "anthropic-version": "2023-06-01",
            },
                json={
                    "model": CLAUDE_MODEL,
                    "max_tokens": 800,
                    "system": (
                        "Tu es un expert en tokenisation sémantique de prompts "
                        f"pour la génération d'images {media_type} SDXL. "
                        "Décompose le prompt en dimensions et génère des tags Booru optimisés. "
                        "Réponds UNIQUEMENT en JSON valide."
                    ),
                    "messages": [{
                        "role": "user",
                        "content": (
                            f"Décompose ce prompt en dimensions sémantiques :\n'{prompt}'\n\n"
                            f"Réponds en JSON :\n"
                            f"{{\"sujet_principal\":\"tags\","
                            f"\"action\":\"tags\","
                            f"\"ambiance\":\"tags\","
                            f"\"eclairage\":\"tags\","
                            f"\"style_visuel\":\"tags\","
                            f"\"composition\":\"tags\","
                            f"\"palette_couleurs\":\"tags\","
                            f"\"details_techniques\":\"masterpiece, best quality, absurdres\","
                            f"\"full_positive_optimized\":\"prompt complet optimisé\","
                            f"\"negative_suggested\":\"éléments à éviter\"}}"
                        )
                    }]
                },
                timeout=25
            )
            if resp.status_code == 200:
                raw = resp.json()["content"][0]["text"].strip()
                if raw.startswith("```"):
                    raw = "\n".join(raw.split("\n")[1:-1])
                result = json.loads(raw)
                # Publier dans le bus
                if BUS_OK:
                    bus = get_bus()
                    bus.write("prompt_decomposer", "decomposed_prompt",
                               result, ContextLayer.CREATIVE,
                               confidence=0.9, importance=0.8)
                return result
        except Exception as e:
            pass

        # Fallback simple
        return {
            "full_positive_optimized": prompt,
            "details_techniques":      "masterpiece, best quality, absurdres",
            "negative_suggested":      "bad quality, worst quality, deformed",
        }

    def enrich_with_context(self, decomposed: dict) -> dict:
        """Enrichit le prompt décomposé avec le contexte du bus."""
        if not BUS_OK:
            return decomposed
        bus   = get_bus()
        mood  = bus.read("trend_mood",    default="")
        audio = bus.read("audio_mood",    default="")
        liked = bus.read("liked_aspects", default=[])

        enriched = dict(decomposed)
        additions = []
        if mood:
            additions.append(mood)
        if audio and audio != mood:
            additions.append(audio)
        if liked and isinstance(liked, list):
            additions.extend(liked[:2])

        if additions and "full_positive_optimized" in enriched:
            enriched["full_positive_optimized"] += ", " + ", ".join(additions)
            enriched["_context_additions"] = additions
        return enriched


# ══════════════════════════════════════════════════════════════════════
# ORCHESTRATEUR NEURONAL PRINCIPAL
# ══════════════════════════════════════════════════════════════════════

class NeuralOrchestrator:
    """
    L'orchestrateur neuronal d'OverLord.
    Intègre tous les composants inspirés de Claude :
      - Context Bus (context window partagée)
      - Multi-Head Attention (analyse parallèle)
      - Chain of Thought (raisonnement visible)
      - Constitution (valeurs partagées)
      - RLHF (feedback humain)
      - Prompt Decomposer (tokenisation sémantique)

    Usage :
      orch = NeuralOrchestrator()
      result = orch.process(
          prompt="scène épique dragon ball",
          media_type="anime",
          run_id="run_001"
      )
    """

    def __init__(self, logger: logging.Logger = None):
        self.log          = logger or logging.getLogger("neural_orch")
        self.bus          = get_bus()         if BUS_OK   else None
        self.constitution = get_constitution() if CONST_OK else None
        self.feedback     = HumanFeedbackLoop(logger=self.log)
        self.decomposer   = PromptDecomposer()
        self._run_count   = 0

    def process(self, prompt: str,
                 media_type: str = "anime",
                 universe:   str = "",
                 run_id:     str = None,
                 cfg:        dict = None) -> dict:
        """
        Traitement neuronal complet d'un brief.

        Phase 1 : Décomposition sémantique (tokenisation)
        Phase 2 : Enrichissement par le contexte bus
        Phase 3 : Analyse multi-tête (4 angles simultanés)
        Phase 4 : Constitution check
        Phase 5 : Chain of thought logging
        Phase 6 : Intégration feedback RLHF
        """
        self._run_count += 1
        run_id  = run_id or f"neural_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        cfg     = cfg or {}
        thought = ThoughtChain("neural_orchestrator", run_id)
        self.log.info(f"[NEURAL] Traitement neuronal : run_id={run_id}")

        # ── Phase 1 : Décomposition ──────────────────────────────────
        thought.think(
            "Je décompose le prompt en dimensions sémantiques",
            "Chaque dimension sera optimisée indépendamment"
        )
        decomposed = self.decomposer.decompose(prompt, media_type)
        enriched   = self.decomposer.enrich_with_context(decomposed)
        self.log.info(f"[NEURAL] Prompt décomposé en {len(decomposed)} dimensions")

        # ── Phase 2 : Préférences RLHF ──────────────────────────────
        thought.think(
            "Je consulte les préférences humaines accumulées",
            "Intégration du feedback historique dans les paramètres"
        )
        human_params  = self.feedback.get_preferred_params()
        human_prompt  = self.feedback.generate_preference_prompt()
        if human_prompt and "full_positive_optimized" in enriched:
            enriched["full_positive_optimized"] += f", {human_prompt}"
        self.log.info(
            f"[NEURAL] RLHF : {len(human_params)} ajustements de paramètres"
        )

        # ── Phase 3 : Analyse multi-tête ────────────────────────────
        thought.think(
            "Je lance 3 analyses en parallèle sur le brief",
            "Convergence vers le meilleur angle créatif"
        )
        attention = MultiHeadAttention(logger=self.log)

        def _narrative_head(data):
            p = data.get("prompt","")
            try:
                r = requests.post(
                    ANTHROPIC_URL,
                    headers={"Content-Type":"application/json"},
                    json={"model":CLAUDE_MODEL,"max_tokens":200,
                          "system":"Expert en narration anime. Réponds en JSON.",
                          "messages":[{"role":"user","content":
                              f"Pour '{p}', donne en JSON : "
                              f"{{\"arc\":\"type d'arc narratif\","
                              f"\"tension\":0.8,"
                              f"\"pacing\":\"rapide|lent|mixte\","
                              f"\"confidence\":0.85}}"}]},
                    timeout=20
                )
                if r.status_code==200:
                    raw=r.json()["content"][0]["text"].strip()
                    if raw.startswith("```"): raw="\n".join(raw.split("\n")[1:-1])
                    return json.loads(raw)
            except Exception: pass
            return {"arc":"héroïque","tension":0.7,"pacing":"rapide","confidence":0.5}

        def _visual_head(data):
            p    = data.get("prompt","")
            mood = self.bus.read("trend_mood","neutral") if self.bus else "neutral"
            return {
                "composition":  "dynamic",
                "color_temp":   "warm" if "coucher" in p.lower() else "cool",
                "energy":       "high" if "bataille" in p.lower() else "medium",
                "style_tags":   f"anime style, {mood}, cinematic",
                "confidence":   0.8,
            }

        def _technical_head(data):
            params = human_params.copy()
            return {
                "steps":    int(params.get("steps", 28) + params.get("steps_adj", 0)),
                "cfg":      round(float(params.get("cfg", 6.0)), 1),
                "sampler":  "euler_ancestral",
                "width":    1024,
                "height":   1536,
                "confidence": 0.9,
            }

        attention.add_head("narrative", "Arc narratif",     _narrative_head, weight=0.3)
        attention.add_head("visual",    "Style visuel",     _visual_head,    weight=0.4)
        attention.add_head("technical", "Paramètres SDXL",  _technical_head, weight=0.3)

        merged = attention.attend({"prompt": prompt, "media_type": media_type})
        self.log.info(
            f"[NEURAL] Multi-tête : {merged.get('heads_ok',0)}/{merged.get('heads_run',0)} OK"
        )

        # ── Phase 4 : Constitution check ─────────────────────────────
        thought.think(
            "Je vérifie que le résultat respecte la constitution",
            "Validation des règles et préférences humaines"
        )
        valid_result = {"valid": True}
        if self.constitution:
            valid_result = self.constitution.validate(
                "neural_orchestrator", "generate",
                {"positive": enriched.get("full_positive_optimized",""),
                 "quality_score": 75}
            )
            if not valid_result["valid"]:
                self.log.warning(
                    f"[NEURAL] Constitution : {len(valid_result['violations'])} violation(s)"
                )

        # ── Phase 5 : Assemblage final ────────────────────────────────
        tech = merged.get("merged",{})
        final_positive = enriched.get("full_positive_optimized", prompt)

        # Injecter l'extension constitutionnelle dans le prompt système
        if self.constitution:
            const_ext = self.constitution.get_system_prompt_extension("production")
        else:
            const_ext = ""

        thought.think(
            "J'assemble tous les résultats en un package de production",
            "Package prêt pour ComfyUI"
        )
        thought.save()

        result = {
            "run_id":          run_id,
            "timestamp":       datetime.utcnow().isoformat(),
            # Prompt enrichi
            "positive":        final_positive,
            "negative":        enriched.get("negative_suggested",
                               "bad quality, worst quality, deformed, bad hands"),
            "prompt_decomposed": decomposed,
            # Paramètres SDXL
            "steps":           tech.get("steps", 28),
            "cfg":             tech.get("cfg", 6.0),
            "sampler":         tech.get("sampler", "euler_ancestral"),
            "width":           tech.get("width", 1024),
            "height":          tech.get("height", 1536),
            # Créatif
            "visual_style":    merged.get("merged",{}).get("style_tags","anime style"),
            "narrative_arc":   merged.get("merged",{}).get("arc","héroïque"),
            "pacing":          merged.get("merged",{}).get("pacing","rapide"),
            # Meta
            "constitution_valid": valid_result.get("valid", True),
            "rlhf_adjustments":   human_params,
            "attention_weights":  merged.get("attention_weights",{}),
            "thought_chain":      thought.summarize(),
            "context_additions":  enriched.get("_context_additions",[]),
        }

        # Publier dans le bus
        if self.bus:
            self.bus.write("neural_orchestrator", "last_production_brief",
                            result, ContextLayer.PRODUCTION,
                            confidence=0.95, importance=1.0)

        self.log.info(
            f"[NEURAL] ✓ Package prêt | "
            f"positive={final_positive[:60]}... | "
            f"steps={result['steps']} cfg={result['cfg']}"
        )
        return result

    def feedback_run(self, run_id: str, score: float,
                      liked: list = None, disliked: list = None,
                      comments: str = "") -> dict:
        """Interface simplifiée pour noter un run."""
        return self.feedback.rate(run_id, score, liked, disliked, comments)

    def get_dashboard(self) -> dict:
        """Dashboard de l'orchestrateur neuronal."""
        bus_snap  = self.bus.snapshot() if self.bus else {}
        fb_report = self.feedback.get_report()
        return {
            "runs_processed":  self._run_count,
            "context_entries": bus_snap.get("total_entries", 0),
            "feedback":        fb_report,
            "attention_map":   self.bus.get_attention_map() if self.bus else [],
            "constitution_ok": self.constitution is not None,
        }


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    orch = NeuralOrchestrator()

    # Test complet
    result = orch.process(
        prompt="scène de bataille épique au coucher du soleil, 3 guerriers anime, "
               "style Dragon Ball Super, poses dynamiques, énergie ki",
        media_type="anime",
        universe="Dragon Ball Super",
        run_id="test_neural_001"
    )

    print("\n=== RÉSULTAT ORCHESTRATEUR NEURONAL ===")
    print(f"Prompt positif  : {result['positive'][:100]}...")
    print(f"Steps           : {result['steps']} | CFG : {result['cfg']}")
    print(f"Arc narratif    : {result['narrative_arc']}")
    print(f"Pacing          : {result['pacing']}")
    print(f"Constitution    : {'✓' if result['constitution_valid'] else '✗'}")
    print(f"Context +       : {result['context_additions']}")
    print(f"\nChain of Thought :\n{result['thought_chain']}")

    # Simuler un feedback
    orch.feedback_run("test_neural_001", 8.0,
                       liked=["composition","style_visuel"],
                       disliked=["mains"])

    print("\n=== DASHBOARD ===")
    dash = orch.get_dashboard()
    print(json.dumps(dash, indent=2, ensure_ascii=False, default=str))

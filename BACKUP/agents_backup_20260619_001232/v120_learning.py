"""
agents/v120_learning.py — OverLord V1.20 — Apprentissage Avancé

1. Reward Shaping        — récompenses granulaires à chaque micro-étape
2. Policy Gradient       — optimisation directe des décisions (REINFORCE)
3. Experience Replay     — rejouer les meilleurs épisodes passés
4. Intrinsic Motivation  — récompense juste pour avoir appris quelque chose de nouveau
5. Curriculum Learning   — progression du plus simple au plus complexe

Inspiré de : PPO (Proximal Policy Optimization), A3C, Curiosity-Driven Exploration
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
import requests

LEARNING_DIR  = Path("workspace/v120_learning")
ANTHROPIC_URL = "https://api.anthropic.com/v1/messages"
CLAUDE_MODEL  = "claude-sonnet-4-6"


def _llm(prompt: str, system: str = "", max_tokens: int = 300) -> str:
    try:
        body = {"model": CLAUDE_MODEL, "max_tokens": max_tokens,
                "messages": [{"role": "user", "content": prompt}]}
        if system:
            body["system"] = system
        r = requests.post(ANTHROPIC_URL,
                          headers={"Content-Type": "application/json"},
                          json=body, timeout=20)
        if r.status_code == 200:
            return r.json()["content"][0]["text"].strip()
    except Exception:
        pass
    return ""


# ══════════════════════════════════════════════════════════════════════
# 1. REWARD SHAPING — Récompenses granulaires
# ══════════════════════════════════════════════════════════════════════

@dataclass
class RewardSignal:
    """Un signal de récompense à un instant précis."""
    timestamp:   float
    agent:       str
    action:      str
    reward:      float        # -1 à +1
    reason:      str
    is_terminal: bool = False  # True = fin d'épisode


class RewardShaper:
    """
    Reward Shaping — transforme les récompenses brutes en signaux
    d'apprentissage plus denses et plus informatives.

    Problème de base : si l'agent ne reçoit une récompense qu'à la fin
    (image générée = bonne/mauvaise), il ne sait pas QUELLE décision
    intermédiaire était la bonne.

    Solution : décomposer en récompenses intermédiaires :
    - +0.1 pour chaque prompt enrichi correctement
    - +0.2 pour chaque LoRA bien sélectionné
    - +0.3 pour chaque shot cohérent avec le scénario
    - -0.1 pour chaque retry ComfyUI
    - -0.3 pour chaque violation constitutionnelle
    - +1.0 pour image finale > 80/100
    """

    # Définition des récompenses par action
    REWARD_TABLE = {
        # Positifs
        "prompt_enriched":         +0.10,
        "lora_selected_correctly": +0.15,
        "shot_coherent":           +0.20,
        "character_consistent":    +0.25,
        "quality_threshold_met":   +0.50,
        "human_positive_feedback": +1.00,
        "novel_style_discovered":  +0.30,
        "context_bus_hit":         +0.05,
        "cache_hit":               +0.08,
        "fast_execution":          +0.10,
        "constitutional_respected":+0.15,
        # Négatifs
        "comfyui_retry":           -0.10,
        "oom_error":               -0.20,
        "character_inconsistent":  -0.25,
        "quality_below_threshold": -0.50,
        "human_negative_feedback": -1.00,
        "constitutional_violation":-0.40,
        "timeout":                 -0.15,
    }

    def __init__(self, gamma: float = 0.95):
        self.gamma    = gamma    # discount factor (récompenses futures valent moins)
        self._signals: list[RewardSignal] = []
        self._episodic: dict[str, list[RewardSignal]] = {}  # run_id → signals
        LEARNING_DIR.mkdir(parents=True, exist_ok=True)

    def reward(self, agent: str, action: str,
               run_id: str = "default",
               bonus: float = 0.0) -> RewardSignal:
        """Émet un signal de récompense pour une action."""
        base_reward = self.REWARD_TABLE.get(action, 0.0)
        total       = max(-1.0, min(1.0, base_reward + bonus))
        signal      = RewardSignal(
            timestamp=time.time(), agent=agent,
            action=action, reward=total,
            reason=f"{action}: {total:+.2f}",
        )
        self._signals.append(signal)
        if run_id not in self._episodic:
            self._episodic[run_id] = []
        self._episodic[run_id].append(signal)
        return signal

    def compute_returns(self, run_id: str) -> list[float]:
        """
        Calcule les retours cumulés actualisés (discounted returns).
        G_t = r_t + γ·r_{t+1} + γ²·r_{t+2} + ...
        """
        signals = self._episodic.get(run_id, [])
        rewards = [s.reward for s in signals]
        returns = []
        G       = 0.0
        for r in reversed(rewards):
            G = r + self.gamma * G
            returns.insert(0, G)
        return returns

    def normalize_returns(self, returns: list[float]) -> list[float]:
        """Normalise les retours (moyenne=0, std=1) pour stabiliser l'apprentissage."""
        if not returns:
            return returns
        mean = sum(returns) / len(returns)
        std  = math.sqrt(sum((r-mean)**2 for r in returns) / len(returns)) + 1e-8
        return [(r - mean) / std for r in returns]

    def get_episode_summary(self, run_id: str) -> dict:
        signals = self._episodic.get(run_id, [])
        if not signals:
            return {}
        returns  = self.compute_returns(run_id)
        pos      = sum(1 for s in signals if s.reward > 0)
        neg      = sum(1 for s in signals if s.reward < 0)
        return {
            "run_id":       run_id,
            "n_signals":    len(signals),
            "total_reward": round(sum(s.reward for s in signals), 3),
            "total_return": round(returns[0] if returns else 0, 3),
            "positive":     pos,
            "negative":     neg,
            "agents":       list(set(s.agent for s in signals)),
        }

    def get_agent_cumulative(self, agent: str) -> dict:
        """Cumul des récompenses par agent."""
        signals = [s for s in self._signals if s.agent == agent]
        total   = sum(s.reward for s in signals)
        best    = max((s.action for s in signals if s.reward > 0), default="?",
                      key=lambda a: sum(s.reward for s in signals if s.action==a))
        return {
            "agent":        agent,
            "n_signals":    len(signals),
            "total_reward": round(total, 3),
            "avg_reward":   round(total/max(len(signals),1), 4),
            "best_action":  best,
        }


# ══════════════════════════════════════════════════════════════════════
# 2. POLICY GRADIENT (REINFORCE simplifié)
# ══════════════════════════════════════════════════════════════════════

@dataclass
class Policy:
    """Politique d'un agent : distribution de probabilités sur les actions."""
    agent:      str
    action_probs: dict[str, float]   # action → probabilité
    n_updates:  int   = 0
    total_reward: float = 0.0

    def sample_action(self, available_actions: list[str]) -> str:
        """Échantillonne une action selon la politique (probabilités)."""
        probs = {a: self.action_probs.get(a, 0.1) for a in available_actions}
        total = sum(probs.values())
        probs = {a: p/total for a, p in probs.items()}

        r   = random.random()
        cum = 0.0
        for action, prob in probs.items():
            cum += prob
            if r <= cum:
                return action
        return available_actions[-1]


class PolicyGradientOptimizer:
    """
    Optimiseur Policy Gradient (REINFORCE).
    Met à jour les probabilités d'actions selon les récompenses reçues.

    Formule : θ ← θ + α · G_t · ∇log π(a_t|s_t)
    Simplifié : augmenter la prob d'une action si elle a mené à une bonne récompense.
    """

    def __init__(self, lr: float = 0.05):
        self.lr       = lr
        self._policies: dict[str, Policy] = {}
        self._history:  list[dict] = []

    def get_policy(self, agent: str,
                   initial_actions: list[str] = None) -> Policy:
        """Récupère ou crée la politique d'un agent."""
        if agent not in self._policies:
            actions = initial_actions or [
                "euler_ancestral", "euler", "dpm++_2m", "dpm++_2m_sde",
                "lcm", "ddim"
            ]
            uniform = 1.0 / len(actions)
            self._policies[agent] = Policy(
                agent=agent,
                action_probs={a: uniform for a in actions}
            )
        return self._policies[agent]

    def update(self, agent: str, action: str,
               normalized_return: float):
        """
        Met à jour la politique selon le retour normalisé.
        Si retour > 0 → augmenter la prob de cette action.
        Si retour < 0 → diminuer la prob de cette action.
        """
        policy = self.get_policy(agent)
        if action not in policy.action_probs:
            policy.action_probs[action] = 0.1

        # Mise à jour REINFORCE
        old_prob = policy.action_probs[action]
        delta    = self.lr * normalized_return * old_prob * (1 - old_prob)
        policy.action_probs[action] = max(0.01, min(0.99, old_prob + delta))

        # Renormaliser
        total = sum(policy.action_probs.values())
        policy.action_probs = {a: p/total for a, p in policy.action_probs.items()}
        policy.n_updates    += 1

        self._history.append({
            "agent":   agent,
            "action":  action,
            "return":  normalized_return,
            "old_prob":round(old_prob, 4),
            "new_prob":round(policy.action_probs[action], 4),
        })

    def batch_update(self, agent: str, actions: list[str],
                     returns: list[float]):
        """Met à jour depuis un batch d'expériences (plus stable)."""
        norm_returns = self._normalize(returns)
        for action, ret in zip(actions, norm_returns):
            self.update(agent, action, ret)

    def get_best_action(self, agent: str,
                         available: list[str] = None) -> str:
        """Retourne l'action avec la probabilité la plus haute."""
        policy = self.get_policy(agent, available)
        probs  = policy.action_probs
        if available:
            probs = {a: p for a, p in probs.items() if a in available}
        return max(probs, key=probs.get)

    def get_policy_summary(self, agent: str) -> dict:
        policy = self._policies.get(agent)
        if not policy:
            return {}
        sorted_probs = sorted(policy.action_probs.items(),
                               key=lambda x: -x[1])
        return {
            "agent":      agent,
            "n_updates":  policy.n_updates,
            "top_actions": sorted_probs[:3],
        }

    def _normalize(self, values: list[float]) -> list[float]:
        if not values:
            return values
        m   = sum(values) / len(values)
        std = math.sqrt(sum((v-m)**2 for v in values) / len(values)) + 1e-8
        return [(v-m)/std for v in values]


# ══════════════════════════════════════════════════════════════════════
# 3. EXPERIENCE REPLAY BUFFER
# ══════════════════════════════════════════════════════════════════════

@dataclass
class Experience:
    """Une expérience = (état, action, récompense, état_suivant, terminal)."""
    state:       dict
    action:      str
    reward:      float
    next_state:  dict
    terminal:    bool
    quality:     float = 0.0   # score de qualité du résultat
    timestamp:   float = field(default_factory=time.time)
    priority:    float = 1.0   # priorité pour Prioritized Experience Replay


class ExperienceReplayBuffer:
    """
    Buffer de rejeu d'expériences.
    Stocke les meilleures expériences passées et les rejoue pour
    renforcer les bonnes décisions, même si elles datent de loin.

    Implémenté avec Prioritized Experience Replay (PER) :
    les expériences avec des TD-errors élevés sont plus souvent rejouées.
    """

    def __init__(self, capacity: int = 1000, alpha: float = 0.6):
        self.capacity = capacity
        self.alpha    = alpha    # exposant de priorité (0=uniforme, 1=total priority)
        self._buffer  = deque(maxlen=capacity)
        self._priorities = deque(maxlen=capacity)
        self._lock    = threading.Lock()
        self._max_priority = 1.0
        LEARNING_DIR.mkdir(parents=True, exist_ok=True)
        self._load()

    def add(self, experience: Experience):
        """Ajoute une expérience avec la priorité maximale actuelle."""
        with self._lock:
            self._buffer.append(experience)
            self._priorities.append(self._max_priority)

    def add_from_run(self, states: list[dict], actions: list[str],
                      rewards: list[float], quality: float):
        """Ajoute tout un run comme séquence d'expériences."""
        for i in range(len(actions)):
            exp = Experience(
                state      = states[i] if i < len(states) else {},
                action     = actions[i],
                reward     = rewards[i],
                next_state = states[i+1] if i+1 < len(states) else {},
                terminal   = (i == len(actions)-1),
                quality    = quality,
                priority   = max(1.0, quality * 2),  # meilleures expériences = haute priorité
            )
            self.add(exp)

    def sample(self, n: int, beta: float = 0.4) -> list[Experience]:
        """
        Échantillonne N expériences avec pondération par priorité.
        beta : exposant de correction (0=pas de correction, 1=correction totale)
        """
        with self._lock:
            if len(self._buffer) < n:
                return list(self._buffer)

            # Priorités normalisées
            probs = [p**self.alpha for p in self._priorities]
            total = sum(probs)
            probs = [p/total for p in probs]

            # Échantillonnage pondéré sans remplacement
            indices = random.choices(
                range(len(self._buffer)),
                weights=probs, k=n
            )
            return [self._buffer[i] for i in indices]

    def sample_best(self, n: int) -> list[Experience]:
        """Retourne les N meilleures expériences par qualité."""
        with self._lock:
            sorted_exp = sorted(self._buffer,
                                key=lambda e: e.quality, reverse=True)
        return sorted_exp[:n]

    def update_priority(self, idx: int, new_priority: float):
        """Met à jour la priorité d'une expérience après utilisation."""
        with self._lock:
            if idx < len(self._priorities):
                self._priorities[idx] = max(0.01, new_priority)
                self._max_priority    = max(self._max_priority, new_priority)

    def replay_and_learn(self, optimizer: PolicyGradientOptimizer,
                          agent: str, n_samples: int = 32) -> dict:
        """
        Rejoue des expériences et met à jour la politique.
        Coeur du Experience Replay.
        """
        samples = self.sample(n_samples)
        if not samples:
            return {"samples": 0}

        actions = [e.action for e in samples]
        rewards = [e.reward * e.quality for e in samples]  # pondéré par qualité
        optimizer.batch_update(agent, actions, rewards)

        return {
            "samples_replayed": len(samples),
            "avg_reward":       round(sum(e.reward for e in samples)/len(samples), 3),
            "avg_quality":      round(sum(e.quality for e in samples)/len(samples), 3),
        }

    def stats(self) -> dict:
        with self._lock:
            n = len(self._buffer)
            q = [e.quality for e in self._buffer]
        return {
            "size":           n,
            "capacity":       self.capacity,
            "fill_rate":      f"{n/self.capacity*100:.1f}%",
            "avg_quality":    round(sum(q)/max(len(q),1), 3),
            "best_quality":   round(max(q, default=0), 3),
        }

    def _save(self):
        data = [
            {"action": e.action, "reward": e.reward,
             "quality": e.quality, "terminal": e.terminal}
            for e in list(self._buffer)[-500:]  # sauvegarder les 500 dernières
        ]
        (LEARNING_DIR / "replay_buffer.json").write_text(
            json.dumps(data, indent=2), encoding="utf-8"
        )

    def _load(self):
        f = LEARNING_DIR / "replay_buffer.json"
        if f.exists():
            try:
                data = json.loads(f.read_text(encoding="utf-8"))
                for d in data:
                    self._buffer.append(Experience(
                        state={}, action=d["action"], reward=d["reward"],
                        next_state={}, terminal=d["terminal"], quality=d["quality"]
                    ))
                    self._priorities.append(max(1.0, d["quality"]*2))
            except Exception:
                pass


# ══════════════════════════════════════════════════════════════════════
# 4. INTRINSIC MOTIVATION
# ══════════════════════════════════════════════════════════════════════

class IntrinsicMotivationEngine:
    """
    Motivation intrinsèque — l'agent est récompensé juste pour
    avoir appris quelque chose de nouveau, indépendamment du résultat.

    Inspiré de : Random Network Distillation (RND) et Count-Based Exploration.

    L'agent accumule une "soif d'apprentissage" quand il stagne,
    et est poussé à explorer de nouveaux territoires.

    Applications pratiques :
    - Découvrir de nouvelles combinaisons de LoRAs jamais testées
    - Explorer des samplers peu utilisés
    - Tenter des compositions visuelles inhabituelles
    """

    def __init__(self):
        self._state_visits:  dict[str, int]   = {}  # hash(état) → nb visites
        self._param_novelty: dict[str, float] = {}  # param → score de nouveauté
        self._total_novelty  = 0.0
        self._stagnation_counter = 0
        self._lock = threading.Lock()

    def _state_hash(self, state: dict) -> str:
        """Hash rapide d'un état (paramètres clés)."""
        key_params = {
            k: state.get(k) for k in
            ["sampler","steps","cfg","lora","strength","scheduler"]
            if k in state
        }
        return hashlib.md5(
            json.dumps(key_params, sort_keys=True).encode()
        ).hexdigest()[:12]

    def compute_intrinsic_reward(self, state: dict,
                                  action: str) -> float:
        """
        Calcule la récompense intrinsèque pour un état/action.
        Plus c'est nouveau, plus la récompense est élevée.
        """
        state_hash = self._state_hash(state)
        with self._lock:
            visits = self._state_visits.get(state_hash, 0)
            self._state_visits[state_hash] = visits + 1

        # Récompense de nouveauté : 1/(1+sqrt(n_visits))
        novelty_reward = 1.0 / (1.0 + math.sqrt(visits))

        # Bonus si l'action est peu utilisée dans ce contexte
        action_key = f"{state.get('sampler','?')}:{action}"
        action_novelty = 1.0 / (1.0 + self._param_novelty.get(action_key, 0))
        with self._lock:
            self._param_novelty[action_key] = \
                self._param_novelty.get(action_key, 0) + 0.1
            self._total_novelty += novelty_reward

        # Combiner
        intrinsic = (novelty_reward * 0.7 + action_novelty * 0.3) * 0.5
        return round(intrinsic, 4)

    def detect_stagnation(self, recent_rewards: list[float],
                           threshold: float = 0.01) -> bool:
        """Détecte si l'agent stagne (peu d'amélioration récente)."""
        if len(recent_rewards) < 5:
            return False
        variance = sum((r - sum(recent_rewards)/len(recent_rewards))**2
                       for r in recent_rewards) / len(recent_rewards)
        is_stagnating = variance < threshold
        if is_stagnating:
            self._stagnation_counter += 1
        else:
            self._stagnation_counter = 0
        return is_stagnating and self._stagnation_counter >= 3

    def suggest_exploration_bonus(self, stagnating: bool,
                                   current_temp: float) -> float:
        """Suggère un bonus de température en cas de stagnation."""
        if stagnating:
            return min(0.5, 0.1 * self._stagnation_counter)
        return 0.0

    def get_novelty_map(self, top_n: int = 10) -> list[dict]:
        """Carte des états les moins explorés (plus curieux)."""
        with self._lock:
            items = sorted(self._state_visits.items(), key=lambda x: x[1])
        return [{"state": k, "visits": v} for k, v in items[:top_n]]

    def stats(self) -> dict:
        with self._lock:
            n_states = len(self._state_visits)
            n_visits = sum(self._state_visits.values())
        return {
            "unique_states_visited":  n_states,
            "total_visits":           n_visits,
            "total_novelty_earned":   round(self._total_novelty, 3),
            "avg_visits_per_state":   round(n_visits/max(n_states,1), 2),
            "stagnation_counter":     self._stagnation_counter,
        }


# ══════════════════════════════════════════════════════════════════════
# 5. CURRICULUM LEARNING
# ══════════════════════════════════════════════════════════════════════

class CurriculumScheduler:
    """
    Curriculum Learning — l'agent progresse du plus simple au plus complexe.

    Comme un enfant apprend les maths : additions → multiplications → algèbre.
    OverLord commence par des tâches simples (portrait 1 personnage) et
    progresse vers des scènes complexes (bataille 6 personnages avec effets).

    Le curriculum s'adapte automatiquement selon les performances.
    """

    DIFFICULTY_LEVELS = {
        1: {
            "name": "Débutant",
            "description": "1 personnage, fond simple, prompt court",
            "constraints": {"max_characters":1, "max_loras":1, "steps_range":(20,28), "cfg_range":(5,7)},
            "min_score_to_advance": 70.0,
        },
        2: {
            "name": "Intermédiaire",
            "description": "2 personnages, décor modéré, effets basiques",
            "constraints": {"max_characters":2, "max_loras":2, "steps_range":(24,32), "cfg_range":(5,8)},
            "min_score_to_advance": 75.0,
        },
        3: {
            "name": "Avancé",
            "description": "3+ personnages, scènes d'action, LoRAs multiples",
            "constraints": {"max_characters":4, "max_loras":3, "steps_range":(28,40), "cfg_range":(5,9)},
            "min_score_to_advance": 80.0,
        },
        4: {
            "name": "Expert",
            "description": "Scènes complexes, cohérence temporelle, style parfait",
            "constraints": {"max_characters":6, "max_loras":4, "steps_range":(28,48), "cfg_range":(4,10)},
            "min_score_to_advance": 85.0,
        },
        5: {
            "name": "Maître",
            "description": "Production complète, pas de contraintes",
            "constraints": {},
            "min_score_to_advance": 95.0,
        },
    }

    def __init__(self):
        self._current_level = 1
        self._run_scores:   list[float] = []
        self._n_at_level:   dict[int, int] = {1: 0}
        self._transitions:  list[dict] = []

    @property
    def current_level(self) -> int:
        return self._current_level

    @property
    def current_config(self) -> dict:
        return self.DIFFICULTY_LEVELS.get(self._current_level, self.DIFFICULTY_LEVELS[5])

    def record_score(self, score: float) -> dict:
        """Enregistre un score et vérifie si on doit avancer."""
        self._run_scores.append(score)
        self._n_at_level[self._current_level] = \
            self._n_at_level.get(self._current_level, 0) + 1

        # Calculer la moyenne des 5 derniers runs
        recent = self._run_scores[-5:]
        avg    = sum(recent) / len(recent)
        level_cfg = self.DIFFICULTY_LEVELS.get(self._current_level, {})
        min_score = level_cfg.get("min_score_to_advance", 100)

        action = "continue"
        if len(recent) >= 3 and avg >= min_score and self._current_level < 5:
            old_level = self._current_level
            self._current_level += 1
            self._n_at_level[self._current_level] = 0
            action = "advanced"
            self._transitions.append({
                "from": old_level, "to": self._current_level,
                "avg_score": round(avg, 2),
                "n_runs": self._n_at_level.get(old_level, 0),
            })
        elif len(recent) >= 5 and avg < min_score - 20 and self._current_level > 1:
            self._current_level -= 1   # régresser si trop mauvais
            action = "regressed"

        return {
            "action":        action,
            "current_level": self._current_level,
            "level_name":    self.current_config.get("name", "?"),
            "avg_score":     round(avg, 2),
            "min_to_advance":min_score,
        }

    def get_task_constraints(self) -> dict:
        """Retourne les contraintes du niveau actuel."""
        return self.current_config.get("constraints", {})

    def get_progress_report(self) -> dict:
        recent = self._run_scores[-10:] if self._run_scores else []
        return {
            "current_level":     self._current_level,
            "level_name":        self.current_config.get("name","?"),
            "level_description": self.current_config.get("description",""),
            "total_runs":        len(self._run_scores),
            "avg_score_recent":  round(sum(recent)/max(len(recent),1), 2),
            "n_transitions":     len(self._transitions),
            "transitions":       self._transitions[-3:],
        }


# ══════════════════════════════════════════════════════════════════════
# FAÇADE APPRENTISSAGE V1.20
# ══════════════════════════════════════════════════════════════════════

class LearningSystemV120:
    """Système d'apprentissage avancé V1.20 — façade unifiée."""

    def __init__(self, logger: logging.Logger = None):
        self.log        = logger or logging.getLogger("learning_v120")
        self.reward     = RewardShaper(gamma=0.95)
        self.policy     = PolicyGradientOptimizer(lr=0.05)
        self.replay     = ExperienceReplayBuffer(capacity=2000)
        self.intrinsic  = IntrinsicMotivationEngine()
        self.curriculum = CurriculumScheduler()

    def process_run(self, run_id: str, agent: str,
                    actions: list[str], states: list[dict],
                    extrinsic_reward: float,
                    quality_score: float) -> dict:
        """
        Traitement complet d'un run dans le système d'apprentissage.
        1. Reward shaping → récompenses intermédiaires
        2. Intrinsic motivation → bonus de nouveauté
        3. Experience replay → ajout au buffer
        4. Policy gradient → mise à jour de la politique
        5. Curriculum → ajustement de la difficulté
        """
        # 1. Reward shaping
        for action in actions:
            if quality_score >= 0.8:
                self.reward.reward(agent, "quality_threshold_met", run_id, bonus=quality_score-0.8)
            if "lora" in action.lower():
                self.reward.reward(agent, "lora_selected_correctly", run_id)
        # Récompense terminale
        self.reward.reward(agent, "quality_threshold_met" if quality_score >= 0.7
                            else "quality_below_threshold", run_id,
                            bonus=quality_score - 0.7)

        # 2. Intrinsic motivation
        intrinsic_rewards = []
        for i, action in enumerate(actions):
            state    = states[i] if i < len(states) else {}
            intr     = self.intrinsic.compute_intrinsic_reward(state, action)
            intrinsic_rewards.append(intr)

        # Détecter stagnation
        recent = [self.reward.get_agent_cumulative(agent)["avg_reward"]]
        stagnating = self.intrinsic.detect_stagnation(recent * 5)

        # 3. Experience replay
        rewards = [extrinsic_reward / max(len(actions),1)] * len(actions)
        for i, ir in enumerate(intrinsic_rewards):
            rewards[i] += ir
        self.replay.add_from_run(states, actions, rewards, quality_score)

        # 4. Policy gradient (depuis le replay buffer)
        replay_result = self.replay.replay_and_learn(self.policy, agent, n_samples=16)

        # 5. Curriculum
        curriculum_result = self.curriculum.record_score(quality_score * 100)

        return {
            "run_id":          run_id,
            "reward_summary":  self.reward.get_episode_summary(run_id),
            "intrinsic_total": round(sum(intrinsic_rewards), 4),
            "stagnating":      stagnating,
            "replay":          replay_result,
            "curriculum":      curriculum_result,
            "best_sampler":    self.policy.get_best_action(agent,
                                ["euler_ancestral","euler","dpm++_2m","lcm"]),
        }

    def get_dashboard(self) -> dict:
        return {
            "version":    "1.20_learning",
            "replay":     self.replay.stats(),
            "intrinsic":  self.intrinsic.stats(),
            "curriculum": self.curriculum.get_progress_report(),
        }


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    sys = LearningSystemV120()

    print("=== V1.20 LEARNING SYSTEM TEST ===\n")

    # Simuler 5 runs progressifs
    for i in range(5):
        quality = 0.55 + i * 0.08   # amélioration progressive
        result  = sys.process_run(
            run_id   = f"run_{i:03d}",
            agent    = "production",
            actions  = ["euler_ancestral", "lora_style", "cfg_6.0"],
            states   = [{"sampler":"euler_ancestral","cfg":6.0,"steps":28}]*3,
            extrinsic_reward = quality,
            quality_score    = quality,
        )
        print(f"Run {i+1}: score={quality*100:.0f} | "
              f"curriculum={result['curriculum']['level_name']} | "
              f"best_sampler={result['best_sampler']} | "
              f"intrinsic={result['intrinsic_total']:.4f}")

    print(f"\nDashboard :")
    print(json.dumps(sys.get_dashboard(), indent=2))

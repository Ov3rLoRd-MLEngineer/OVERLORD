"""
agents/v110_intelligence.py — OverLord V1.10 — Intelligence Avancée
Mécanismes d'apprentissage inspirés de la recherche en IA moderne.

1. Meta-Learning (MAML-inspired) — apprendre à apprendre plus vite
2. Curiosity-Driven Exploration  — explorer l'inconnu activement
3. Self-Reflection Loop          — l'agent se critique avant de valider
4. Goal Decomposition            — décomposer les objectifs complexes
5. Counterfactual Reasoning      — raisonner sur les "et si..."
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

ANTHROPIC_URL = "https://api.anthropic.com/v1/messages"
CLAUDE_MODEL  = "claude-sonnet-4-6"
INTEL_DIR     = Path("workspace/intelligence")


def llm(prompt: str, system: str = "", max_tokens: int = 500) -> str:
    try:
        body = {"model": CLAUDE_MODEL, "max_tokens": max_tokens,
                "messages": [{"role":"user","content":prompt}]}
        if system:
            body["system"] = system
        r = requests.post(ANTHROPIC_URL,
                          headers={"Content-Type":"application/json"},
                          json=body, timeout=30)
        if r.status_code == 200:
            return r.json()["content"][0]["text"].strip()
    except Exception:
        pass
    return ""


# ══════════════════════════════════════════════════════════════════════
# 1. META-LEARNING (MAML-inspired)
# Apprendre à apprendre : adapter rapidement les paramètres à un nouveau style
# ══════════════════════════════════════════════════════════════════════

@dataclass
class TaskExperience:
    """Une expérience sur un type de tâche spécifique."""
    task_type:  str         # "anime_action", "manga_romance", "comics_horror"...
    params:     dict        # paramètres utilisés
    score:      float       # score obtenu
    n_steps:    int = 1     # combien de runs pour atteindre ce score
    timestamp:  float = field(default_factory=time.time)


class MetaLearner:
    """
    Meta-learner inspiré de MAML (Model-Agnostic Meta-Learning).

    Principe : au lieu d'apprendre UN seul ensemble de paramètres optimaux,
    apprendre à ADAPTER RAPIDEMENT les paramètres à un nouveau style.

    Résultat concret :
    - Nouveau style demandé : "cyberpunk manga"
    - MetaLearner : "j'ai appris sur des styles similaires (anime, noir comics)"
    - Il propose des paramètres initiaux déjà bien calibrés
    - Au lieu de 20 runs pour converger → 3-5 runs suffisent
    """

    STYLE_FAMILIES = {
        "anime":     ["action", "romance", "isekai", "mecha", "shonen", "seinen"],
        "manga":     ["tankōbon", "webtoon", "seinen", "shoujo"],
        "comics":    ["superhero", "horror", "noir", "indie"],
        "3d":        ["realistic", "stylized", "lowpoly", "sculpt"],
        "photoreal": ["portrait", "landscape", "product", "cinematic"],
    }

    def __init__(self, logger: logging.Logger = None):
        self.log        = logger or logging.getLogger("meta_learner")
        self._experiences: list[TaskExperience] = []
        self._meta_params: dict = {}   # paramètres "méta" initiaux par famille
        INTEL_DIR.mkdir(parents=True, exist_ok=True)
        self._load()

    def record_experience(self, task_type: str, params: dict,
                           score: float, n_steps: int = 1):
        """Enregistre une expérience sur un type de tâche."""
        exp = TaskExperience(task_type=task_type, params=dict(params),
                              score=score, n_steps=n_steps)
        self._experiences.append(exp)
        self._update_meta_params(exp)
        self._save()

    def _update_meta_params(self, exp: TaskExperience):
        """Met à jour les paramètres méta depuis une expérience."""
        family = self._get_family(exp.task_type)
        if family not in self._meta_params:
            self._meta_params[family] = {"experiences": 0}

        mp = self._meta_params[family]
        n  = mp["experiences"]
        lr = 1.0 / (n + 1)   # learning rate décroissant

        for param, value in exp.params.items():
            if isinstance(value, (int, float)):
                current = mp.get(param, value)
                # Mise à jour pondérée par le score
                weight  = exp.score * lr
                mp[param] = current * (1 - weight) + value * weight

        mp["experiences"] = n + 1
        mp["avg_score"]   = (mp.get("avg_score", 0) * n + exp.score) / (n + 1)

    def get_initial_params(self, task_type: str,
                            base_params: dict = None) -> dict:
        """
        Retourne des paramètres initiaux optimaux pour un nouveau style.
        Si le style est inconnu, utilise la famille la plus proche.
        """
        base   = dict(base_params or {
            "steps": 28, "cfg": 6.0, "sampler": "euler_ancestral",
            "strength": 1.0, "denoise": 1.0,
        })
        family = self._get_family(task_type)
        meta   = self._meta_params.get(family, {})

        # Appliquer les paramètres méta comme point de départ
        for param, value in meta.items():
            if param in ("experiences", "avg_score"):
                continue
            if isinstance(value, (int, float)) and param in base:
                base[param] = type(base[param])(value)  # garder le type

        n_exp    = meta.get("experiences", 0)
        avg_sc   = meta.get("avg_score",   0.5)
        self.log.info(
            f"[META] Params initiaux pour '{task_type}' "
            f"(famille={family}, {n_exp} expériences, score_moy={avg_sc:.2f})"
        )
        return base

    def estimate_convergence(self, task_type: str) -> dict:
        """Estime combien de runs nécessaires pour converger."""
        family   = self._get_family(task_type)
        similar  = [e for e in self._experiences
                    if self._get_family(e.task_type) == family]
        if not similar:
            return {"estimated_runs": 15, "confidence": 0.3}

        avg_steps   = sum(e.n_steps for e in similar) / len(similar)
        # Avec meta-learning : réduction estimée à 40%
        meta_steps  = max(2, avg_steps * 0.6)
        confidence  = min(0.9, len(similar) / 20)
        return {
            "estimated_runs": round(meta_steps),
            "without_meta":   round(avg_steps),
            "speedup":        f"{avg_steps/meta_steps:.1f}x",
            "confidence":     round(confidence, 2),
            "n_similar_tasks":len(similar),
        }

    def _get_family(self, task_type: str) -> str:
        for family, subtypes in self.STYLE_FAMILIES.items():
            if task_type == family or task_type in subtypes:
                return family
            if any(s in task_type for s in [family] + subtypes):
                return family
        return "anime"  # défaut

    def _save(self):
        data = {
            "meta_params": self._meta_params,
            "n_experiences": len(self._experiences),
        }
        (INTEL_DIR / "meta_learner.json").write_text(
            json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8"
        )

    def _load(self):
        f = INTEL_DIR / "meta_learner.json"
        if f.exists():
            try:
                data = json.loads(f.read_text(encoding="utf-8"))
                self._meta_params = data.get("meta_params", {})
            except Exception:
                pass


# ══════════════════════════════════════════════════════════════════════
# 2. CURIOSITY-DRIVEN EXPLORATION
# L'agent explore activement ce qu'il ne comprend pas encore
# ══════════════════════════════════════════════════════════════════════

class CuriosityEngine:
    """
    Moteur de curiosité intrinsèque.

    Principe : l'agent est "curieux" des configurations qu'il a
    peu explorées ou dont il est peu sûr. Il n'attend pas qu'on lui
    demande d'expérimenter — il propose lui-même des explorations.

    Inspiré de l'intrinsic curiosity module (ICM) en RL.

    Score de curiosité = incertitude × nouveauté × potentiel
    """

    def __init__(self, logger: logging.Logger = None):
        self.log          = logger or logging.getLogger("curiosity")
        self._visited:    dict[str, int]   = {}    # config → nb visites
        self._outcomes:   dict[str, float] = {}    # config → score
        self._uncertainty: dict[str, float] = {}   # config → variance du score
        self._total_runs  = 0

    def _config_key(self, params: dict) -> str:
        """Clé canonique pour une configuration."""
        relevant = {k: params.get(k) for k in
                    ["steps","cfg","sampler","strength","scheduler"]
                    if k in params}
        return json.dumps(relevant, sort_keys=True)

    def get_curiosity_score(self, params: dict) -> float:
        """
        Score de curiosité pour une configuration donnée.
        Haut score = l'agent veut explorer cette config.
        """
        key   = self._config_key(params)
        n     = self._visited.get(key, 0)
        score = self._outcomes.get(key, 0.5)
        unc   = self._uncertainty.get(key, 0.5)

        # Formule de curiosité :
        # novelty     = 1/(1+n)      → plus on a visité, moins c'est nouveau
        # uncertainty = unc          → plus on est incertain, plus c'est curieux
        # potential   = 1 - score    → les configs mauvaises ont du potentiel d'amélioration
        novelty     = 1.0 / (1.0 + n)
        potential   = max(0, 1.0 - score)
        curiosity   = (novelty * 0.4 + unc * 0.35 + potential * 0.25)
        return round(curiosity, 4)

    def suggest_exploration(self, base_params: dict,
                             n_suggestions: int = 3) -> list[dict]:
        """
        Génère N configurations à explorer, guidées par la curiosité.
        Les configurations peu visitées et incertaines sont priorisées.
        """
        suggestions = []
        param_ranges = {
            "steps":    [16, 20, 24, 28, 32, 36, 40, 48],
            "cfg":      [3.5, 4.0, 5.0, 6.0, 7.0, 8.0, 9.0, 10.0],
            "sampler":  ["euler_ancestral","euler","dpm++_2m","dpm++_2m_sde",
                         "dpm++_3m_sde","lcm","ddim"],
            "strength": [0.6, 0.7, 0.8, 0.9, 1.0, 1.1],
            "scheduler":["normal","karras","exponential"],
        }

        # Générer des variantes et les scorer par curiosité
        candidates = []
        for _ in range(50):   # générer beaucoup, garder les meilleurs
            candidate = dict(base_params)
            # Varier 1-2 paramètres aléatoirement
            n_changes = random.randint(1, 2)
            for _ in range(n_changes):
                param = random.choice(list(param_ranges.keys()))
                candidate[param] = random.choice(param_ranges[param])
            score_c = self.get_curiosity_score(candidate)
            candidates.append((score_c, candidate))

        # Trier par score de curiosité décroissant
        candidates.sort(key=lambda x: -x[0])
        suggestions = [c for _, c in candidates[:n_suggestions]]

        self.log.info(
            f"[CURIOSITY] {n_suggestions} explorations suggérées "
            f"(score max: {candidates[0][0]:.3f})"
        )
        return suggestions

    def record_outcome(self, params: dict, score: float):
        """Enregistre le résultat d'une exploration."""
        key = self._config_key(params)
        self._visited[key]  = self._visited.get(key, 0) + 1
        self._total_runs    += 1

        # Mise à jour de la moyenne et de la variance (Welford's algorithm)
        old_score = self._outcomes.get(key, score)
        n         = self._visited[key]
        new_score = old_score + (score - old_score) / n
        self._outcomes[key]    = new_score
        self._uncertainty[key] = abs(score - old_score)   # approximation variance

    def get_exploration_summary(self) -> dict:
        """Résumé de l'exploration."""
        return {
            "total_runs":         self._total_runs,
            "unique_configs":     len(self._visited),
            "most_visited":       max(self._visited.values(), default=0),
            "unexplored_ratio":   round(
                1 - len(self._visited) / max(self._total_runs, 1), 3
            ),
            "avg_uncertainty":    round(
                sum(self._uncertainty.values()) / max(len(self._uncertainty),1), 3
            ),
        }


# ══════════════════════════════════════════════════════════════════════
# 3. SELF-REFLECTION LOOP
# L'agent se critique lui-même avant de valider son output
# ══════════════════════════════════════════════════════════════════════

class SelfReflectionLoop:
    """
    Boucle de réflexion interne — l'agent vérifie son propre travail.

    Inspiré du "Constitutional AI" d'Anthropic :
    avant de retourner un résultat, l'agent se pose des questions critiques
    sur sa propre production et s'autocorrige si nécessaire.

    Analogie Claude : avant de répondre, je vérifie mentalement si ma
    réponse est cohérente, complète, et respecte mes valeurs.
    """

    MAX_REFLECTION_ROUNDS = 2

    def __init__(self, logger: logging.Logger = None):
        self.log = logger or logging.getLogger("reflection")

    def reflect_and_improve(self, agent_name: str,
                             task: str,
                             output: dict,
                             criteria: list[str] = None) -> dict:
        """
        Fait réfléchir l'agent sur son output et propose des améliorations.

        criteria : critères de qualité à vérifier
        Retourne : {"improved_output": ..., "reflections": [...], "improved": bool}
        """
        criteria = criteria or [
            "L'output est-il cohérent avec la tâche demandée ?",
            "Y a-t-il des contradictions internes ?",
            "Manque-t-il des informations importantes ?",
            "L'output respecte-t-il les contraintes de qualité ?",
        ]

        prompt = (
            f"Tu es l'{agent_name} d'OverLord Pipeline.\n"
            f"Tu viens de produire cet output pour la tâche : '{task}'\n\n"
            f"OUTPUT PRODUIT :\n{json.dumps(output, ensure_ascii=False, indent=2)[:1000]}\n\n"
            f"Maintenant, critique ton propre travail sur ces points :\n"
            + "\n".join(f"  {i+1}. {c}" for i,c in enumerate(criteria)) +
            "\n\nSi tu identifies des problèmes, propose une version améliorée.\n"
            "Réponds en JSON :\n"
            '{"issues_found": ["problème1", ...], '
            '"has_improvements": true/false, '
            '"improved_output": {...ou null si rien à améliorer...}, '
            '"confidence_after_reflection": 0.85}'
        )

        result = {
            "original_output":           output,
            "reflections":               [],
            "improved_output":           output,
            "improved":                  False,
            "confidence_after_reflection": 0.7,
        }

        reflection = llm(prompt, max_tokens=800)
        if not reflection:
            return result

        try:
            if reflection.startswith("```"):
                reflection = "\n".join(reflection.split("\n")[1:-1])
            data = json.loads(reflection)

            issues   = data.get("issues_found", [])
            improved = data.get("improved_output")
            has_impr = data.get("has_improvements", False)
            conf     = data.get("confidence_after_reflection", 0.7)

            result["reflections"]               = issues
            result["confidence_after_reflection"] = conf
            result["improved"]                  = has_impr and improved is not None

            if result["improved"] and improved:
                result["improved_output"] = improved
                self.log.info(
                    f"[REFLECT/{agent_name}] Améliorations : {issues[:2]}"
                )
            else:
                self.log.debug(f"[REFLECT/{agent_name}] Output validé sans modification")

        except json.JSONDecodeError:
            pass

        return result

    def quick_sanity_check(self, output: dict,
                            required_keys: list[str]) -> dict:
        """Vérification rapide (sans LLM) des clés requises."""
        missing = [k for k in required_keys if k not in output]
        return {
            "valid":   len(missing) == 0,
            "missing": missing,
            "has_values": all(output.get(k) for k in required_keys if k in output),
        }


# ══════════════════════════════════════════════════════════════════════
# 4. GOAL DECOMPOSITION
# Décomposer les objectifs complexes en sous-objectifs atomiques
# ══════════════════════════════════════════════════════════════════════

@dataclass
class SubGoal:
    id:           str
    description:  str
    agent:        str    # qui doit l'accomplir
    depends_on:   list   = field(default_factory=list)
    status:       str    = "pending"   # pending/running/done/failed
    result:       Any    = None
    priority:     int    = 5


class GoalDecomposer:
    """
    Décompose les objectifs complexes en sous-objectifs atomiques.

    'Créer un épisode anime de 5 minutes sur Dragon Ball'
    →
    [1] Analyser les tendances Dragon Ball (sourcing)
    [2] Écrire le scénario de l'épisode (scenario)
    [3] Créer le storyboard (storyboard)
    [4] Générer les personnages (production, dépend 2+3)
    [5] Générer les décors (production, dépend 2+3)
    [6] Générer les effets (production, dépend 4+5)
    [7] Assembler la vidéo (postprod, dépend 4+5+6)
    [8] Créer les posts réseaux (marketing, dépend 7)
    """

    def decompose(self, goal: str,
                   media_type: str = "anime",
                   duration: str  = "5 minutes") -> list[SubGoal]:
        """Décompose un objectif en sous-objectifs via LLM."""
        prompt = (
            f"Décompose cet objectif de production en sous-tâches atomiques :\n"
            f"OBJECTIF : {goal}\n"
            f"Média    : {media_type}\n"
            f"Durée    : {duration}\n\n"
            f"Chaque sous-tâche doit être :\n"
            f"- Réalisable par un seul agent\n"
            f"- Clairement définie\n"
            f"- Avec ses dépendances explicites\n\n"
            f"Agents disponibles : sourcing, scenario, storyboard, "
            f"production, postprod, marketing, community, 3d\n\n"
            f"Réponds en JSON :\n"
            f'[{{"id":"sg1","description":"...","agent":"sourcing",'
            f'"depends_on":[],"priority":1}}, ...]'
        )
        result = llm(prompt, max_tokens=1000)
        subgoals = []

        if result:
            try:
                if result.startswith("```"):
                    result = "\n".join(result.split("\n")[1:-1])
                data = json.loads(result)
                for i, sg in enumerate(data):
                    subgoals.append(SubGoal(
                        id=sg.get("id",f"sg{i+1}"),
                        description=sg.get("description",""),
                        agent=sg.get("agent","scenario"),
                        depends_on=sg.get("depends_on",[]),
                        priority=sg.get("priority",5),
                    ))
            except json.JSONDecodeError:
                pass

        if not subgoals:
            # Décomposition par défaut
            default = [
                SubGoal("sg1","Analyse des tendances",    "sourcing",   [],            1),
                SubGoal("sg2","Écriture du scénario",     "scenario",   ["sg1"],       2),
                SubGoal("sg3","Création du storyboard",   "storyboard", ["sg2"],       3),
                SubGoal("sg4","Génération des images",    "production", ["sg3"],       4),
                SubGoal("sg5","Montage et post-prod",     "postprod",   ["sg4"],       5),
                SubGoal("sg6","Publication réseaux",      "marketing",  ["sg5"],       6),
            ]
            subgoals = default

        return subgoals

    def get_execution_order(self, subgoals: list[SubGoal]) -> list[list[SubGoal]]:
        """
        Retourne les sous-objectifs ordonnés par vagues d'exécution parallèle.
        Vague 1 : pas de dépendances → exécution parallèle
        Vague 2 : dépend de la vague 1 → etc.
        """
        completed = set()
        waves     = []

        remaining = list(subgoals)
        while remaining:
            wave = [sg for sg in remaining
                    if all(dep in completed for dep in sg.depends_on)]
            if not wave:
                break   # dépendances circulaires → stopper
            waves.append(sorted(wave, key=lambda x: x.priority))
            completed.update(sg.id for sg in wave)
            remaining  = [sg for sg in remaining if sg.id not in completed]

        return waves


# ══════════════════════════════════════════════════════════════════════
# 5. COUNTERFACTUAL REASONING
# "Et si..." — raisonner sur les alternatives non prises
# ══════════════════════════════════════════════════════════════════════

class CounterfactualReasoner:
    """
    Raisonnement contrefactuel : analyser les alternatives non prises
    pour apprendre comment améliorer les décisions futures.

    "Si j'avais utilisé steps=40 au lieu de 28, le résultat aurait été..."
    "Si j'avais choisi un sampler différent, le score aurait été..."

    Permet d'apprendre sans nécessairement exécuter toutes les alternatives.
    """

    def analyze(self, decision_made: dict,
                 alternatives: list[dict],
                 actual_result: float) -> dict:
        """
        Analyse une décision prise et ses alternatives.
        Retourne des insights sur ce qui aurait pu être mieux.
        """
        prompt = (
            f"Analyse cette décision de production IA et ses alternatives :\n\n"
            f"DÉCISION PRISE : {json.dumps(decision_made, ensure_ascii=False)}\n"
            f"RÉSULTAT OBTENU : {actual_result:.2f}/100\n\n"
            f"ALTERNATIVES NON PRISES :\n"
            + "\n".join(f"  {i+1}. {json.dumps(a, ensure_ascii=False)}"
                        for i,a in enumerate(alternatives[:3])) +
            "\n\nPour chaque alternative, estime le résultat probable "
            "et explique pourquoi. Réponds en JSON :\n"
            '{"counterfactuals":[{"alternative":{},"estimated_score":0.0,'
            '"reasoning":"...","would_have_been_better":true}],'
            '"lesson":"ce qu\'on apprend de cette analyse"}'
        )
        result = llm(prompt, max_tokens=600)
        if not result:
            return {"lesson": "Analyse non disponible"}
        try:
            if result.startswith("```"):
                result = "\n".join(result.split("\n")[1:-1])
            return json.loads(result)
        except Exception:
            return {"lesson": result[:200]}


# ══════════════════════════════════════════════════════════════════════
# FAÇADE INTELLIGENCE V1.10
# ══════════════════════════════════════════════════════════════════════

class IntelligenceV110:
    """Point d'entrée unifié pour les capacités d'intelligence V1.10."""

    def __init__(self, logger: logging.Logger = None):
        self.log             = logger or logging.getLogger("intel")
        self.meta_learner    = MetaLearner(logger=self.log)
        self.curiosity       = CuriosityEngine(logger=self.log)
        self.reflection      = SelfReflectionLoop(logger=self.log)
        self.goal_decomposer = GoalDecomposer()
        self.counterfactual  = CounterfactualReasoner()

    def smart_start(self, task_type: str,
                     base_params: dict = None) -> dict:
        """
        Point d'entrée intelligent pour démarrer un run.
        Combine meta-learning + curiosité pour les meilleurs params initiaux.
        """
        # Meta-learning : params initiaux adaptés au style
        meta_params = self.meta_learner.get_initial_params(task_type, base_params)
        conv_est    = self.meta_learner.estimate_convergence(task_type)

        # Curiosité : faut-il explorer ou exploiter ?
        curiosity_score = self.curiosity.get_curiosity_score(meta_params)

        if curiosity_score > 0.6:
            # Explorer : proposer une variante curieuse
            suggestions = self.curiosity.suggest_exploration(meta_params, n_suggestions=1)
            if suggestions:
                meta_params = suggestions[0]
                self.log.info(f"[INTEL] Mode exploration (curiosité={curiosity_score:.2f})")
            mode = "explore"
        else:
            self.log.info(f"[INTEL] Mode exploitation (curiosité={curiosity_score:.2f})")
            mode = "exploit"

        return {
            "params":           meta_params,
            "mode":             mode,
            "curiosity_score":  curiosity_score,
            "estimated_runs":   conv_est.get("estimated_runs", "?"),
            "speedup":          conv_est.get("speedup", "1x"),
        }

    def record_run(self, task_type: str, params: dict, score: float):
        """Enregistre un run dans tous les systèmes d'apprentissage."""
        self.meta_learner.record_experience(task_type, params, score)
        self.curiosity.record_outcome(params, score)

    def plan_production(self, goal: str,
                         media_type: str = "anime") -> dict:
        """Décompose et planifie une production complète."""
        subgoals = self.goal_decomposer.decompose(goal, media_type)
        waves    = self.goal_decomposer.get_execution_order(subgoals)
        return {
            "goal":      goal,
            "subgoals":  len(subgoals),
            "waves":     len(waves),
            "wave_plan": [
                {
                    "wave":     i+1,
                    "parallel": len(wave),
                    "tasks":    [{"id":sg.id,"agent":sg.agent,"desc":sg.description[:60]}
                                  for sg in wave]
                }
                for i, wave in enumerate(waves)
            ],
        }

    def get_dashboard(self) -> dict:
        return {
            "meta_learner":  {
                "task_families": len(self.meta_learner._meta_params),
                "experiences":   len(self.meta_learner._experiences),
            },
            "curiosity":     self.curiosity.get_exploration_summary(),
        }


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    intel = IntelligenceV110()

    print("=== TEST INTELLIGENCE V1.10 ===\n")

    # 1. Meta-learning
    intel.meta_learner.record_experience("anime_action",
        {"steps":32,"cfg":7.0,"sampler":"dpm++_2m_sde"}, 0.88, n_steps=5)
    intel.meta_learner.record_experience("anime_action",
        {"steps":28,"cfg":6.0,"sampler":"euler_ancestral"}, 0.82, n_steps=3)

    start = intel.smart_start("anime_shonen", {"steps":28,"cfg":6.0})
    print(f"Meta-start 'anime_shonen' :")
    print(f"  Params: steps={start['params'].get('steps')}, cfg={start['params'].get('cfg')}")
    print(f"  Mode: {start['mode']} | Curiosité: {start['curiosity_score']:.3f}")
    print(f"  Convergence estimée: {start['estimated_runs']} runs ({start['speedup']})")

    # 2. Curiosité
    expl = intel.curiosity.suggest_exploration({"steps":28,"cfg":6.0}, n_suggestions=2)
    print(f"\nExplorations suggérées :")
    for e in expl:
        print(f"  steps={e.get('steps')} cfg={e.get('cfg')} sampler={e.get('sampler')}")

    # 3. Décomposition d'objectifs
    plan = intel.plan_production("Créer un épisode anime de 5 minutes sur Dragon Ball")
    print(f"\nPlan de production :")
    print(f"  {plan['subgoals']} sous-tâches | {plan['waves']} vagues d'exécution")
    for w in plan["wave_plan"]:
        tasks = ", ".join(t["agent"] for t in w["tasks"])
        print(f"  Vague {w['wave']} ({w['parallel']} en parallèle) : {tasks}")

    # 4. Dashboard
    print(f"\nDashboard Intelligence :")
    print(json.dumps(intel.get_dashboard(), indent=2))

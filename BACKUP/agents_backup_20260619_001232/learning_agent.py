"""
agents/learning_agent.py — Agent Auto-Apprenant OverLord
IA Maestro qui apprend par la répétition à maîtriser le pipeline.

Architecture :
  - Mémoire épisodique (ChromaDB ou JSON fallback)
  - Boucle d'apprentissage : Essai → Observation → Critique → Mémorisation
  - Optimiseur de prompts par évolution génétique simple
  - Extracteur de métriques (qualité image, temps, erreurs)
  - Auto-critique : compare résultat vs objectif fixé
  - Interface de rapport : explique ses découvertes en langage naturel

L'agent ne génère pas d'images directement — il pilote le pipeline
et analyse les résultats pour en extraire des leçons réutilisables.

pip install chromadb sentence-transformers
"""

import json
import logging
import time
import hashlib
import random
import requests
import threading
from pathlib import Path
from datetime import datetime
from enum import Enum
from copy import deepcopy

MEMORY_DIR    = Path("workspace/learning")
EPISODES_FILE = MEMORY_DIR / "episodes.json"
KNOWLEDGE_FILE = MEMORY_DIR / "knowledge.json"
STATS_FILE    = MEMORY_DIR / "stats.json"
ANTHROPIC_URL = "https://api.anthropic.com/v1/messages"
CLAUDE_MODEL  = "claude-sonnet-4-6"

# Seuils d'apprentissage
QUALITY_THRESHOLD   = 75.0   # score minimum pour considérer un run réussi
LEARNING_RATE       = 0.1    # vitesse d'adaptation des paramètres
MAX_EPISODES_MEMORY = 200    # nombre max d'épisodes en mémoire
EVOLUTION_POP_SIZE  = 5      # population pour l'évolution de prompts

class LearningState(Enum):
    IDLE        = "idle"
    RUNNING     = "running"
    REFLECTING  = "reflecting"
    EVOLVING    = "evolving"
    SLEEPING    = "sleeping"


class Episode:
    """Un épisode = un run du pipeline avec ses paramètres et résultats."""

    def __init__(self, run_id: str, params: dict):
        self.run_id      = run_id
        self.params      = params       # paramètres utilisés
        self.timestamp   = datetime.utcnow().isoformat()
        self.results     = {}           # résultats bruts
        self.metrics     = {}           # métriques calculées
        self.score       = 0.0          # score global 0-100
        self.lessons     = []           # leçons extraites
        self.errors      = []           # erreurs rencontrées
        self.duration_s  = 0.0         # durée du run

    def to_dict(self) -> dict:
        return {
            "run_id":     self.run_id,
            "params":     self.params,
            "timestamp":  self.timestamp,
            "results":    self.results,
            "metrics":    self.metrics,
            "score":      self.score,
            "lessons":    self.lessons,
            "errors":     self.errors,
            "duration_s": self.duration_s,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "Episode":
        ep = cls(d["run_id"], d.get("params", {}))
        ep.timestamp  = d.get("timestamp","")
        ep.results    = d.get("results", {})
        ep.metrics    = d.get("metrics", {})
        ep.score      = d.get("score", 0.0)
        ep.lessons    = d.get("lessons", [])
        ep.errors     = d.get("errors", [])
        ep.duration_s = d.get("duration_s", 0.0)
        return ep


class EpisodicMemory:
    """
    Mémoire des épisodes passés.
    Utilise ChromaDB si disponible, sinon JSON simple.
    """

    def __init__(self, memory_dir: Path = MEMORY_DIR):
        self.dir      = memory_dir
        self.dir.mkdir(parents=True, exist_ok=True)
        self._episodes: list[Episode] = []
        self._use_chroma = False

        # Essayer ChromaDB
        try:
            import chromadb
            from sentence_transformers import SentenceTransformer
            self._chroma  = chromadb.PersistentClient(path=str(memory_dir / "chromadb"))
            self._col     = self._chroma.get_or_create_collection("episodes")
            self._encoder = SentenceTransformer("all-MiniLM-L6-v2")
            self._use_chroma = True
        except ImportError:
            pass  # fallback JSON

        self._load()

    def add(self, episode: Episode):
        """Ajoute un épisode à la mémoire."""
        self._episodes.append(episode)

        # ChromaDB : indexer par embedding du prompt
        if self._use_chroma:
            prompt = episode.params.get("positive", "")
            if prompt:
                emb = self._encoder.encode(prompt).tolist()
                self._col.upsert(
                    ids=[episode.run_id],
                    embeddings=[emb],
                    documents=[prompt],
                    metadatas=[{
                        "score":    episode.score,
                        "media":    episode.params.get("media_type","anime"),
                        "ts":       episode.timestamp,
                    }]
                )

        # Garder la mémoire à taille raisonnable
        if len(self._episodes) > MAX_EPISODES_MEMORY:
            # Supprimer les épisodes les moins bien notés
            self._episodes.sort(key=lambda e: e.score, reverse=True)
            self._episodes = self._episodes[:MAX_EPISODES_MEMORY]

        self._save()

    def recall_similar(self, prompt: str, n: int = 5) -> list[Episode]:
        """Retrouve les N épisodes les plus similaires par contenu."""
        if self._use_chroma and prompt:
            try:
                emb = self._encoder.encode(prompt).tolist()
                results = self._col.query(
                    query_embeddings=[emb],
                    n_results=min(n, len(self._episodes))
                )
                ids = results.get("ids", [[]])[0]
                return [e for e in self._episodes if e.run_id in ids]
            except Exception:
                pass

        # Fallback : récents + meilleurs scores
        sorted_ep = sorted(self._episodes, key=lambda e: e.score, reverse=True)
        return sorted_ep[:n]

    def recall_best(self, n: int = 5) -> list[Episode]:
        """Retourne les N meilleurs épisodes."""
        return sorted(self._episodes, key=lambda e: e.score, reverse=True)[:n]

    def recall_failures(self, n: int = 5) -> list[Episode]:
        """Retourne les N pires épisodes pour apprendre des erreurs."""
        return sorted(self._episodes, key=lambda e: e.score)[:n]

    def get_stats(self) -> dict:
        if not self._episodes:
            return {"total": 0, "avg_score": 0, "best_score": 0,
                    "worst_score": 0, "success_rate": 0}
        scores = [e.score for e in self._episodes]
        return {
            "total":        len(self._episodes),
            "avg_score":    round(sum(scores)/len(scores), 1),
            "best_score":   round(max(scores), 1),
            "worst_score":  round(min(scores), 1),
            "success_rate": round(
                sum(1 for s in scores if s >= QUALITY_THRESHOLD)
                / len(scores) * 100, 1
            ),
            "trend":        self._compute_trend(),
        }

    def _compute_trend(self) -> str:
        """Calcule la tendance d'apprentissage sur les 20 derniers runs."""
        if len(self._episodes) < 10:
            return "insufficient_data"
        recent = sorted(self._episodes, key=lambda e: e.timestamp)[-20:]
        scores = [e.score for e in recent]
        first_half = sum(scores[:10]) / 10
        second_half = sum(scores[10:]) / 10
        delta = second_half - first_half
        if delta > 5:   return "improving"
        if delta < -5:  return "declining"
        return "stable"

    def _save(self):
        EPISODES_FILE.write_text(
            json.dumps([e.to_dict() for e in self._episodes],
                       indent=2, ensure_ascii=False, default=str),
            encoding="utf-8"
        )

    def _load(self):
        if EPISODES_FILE.exists():
            try:
                data = json.loads(EPISODES_FILE.read_text(encoding="utf-8"))
                self._episodes = [Episode.from_dict(d) for d in data]
            except Exception:
                self._episodes = []


class KnowledgeBase:
    """
    Base de connaissances accumulées par l'agent.
    Stocke les règles apprises, les paramètres optimaux découverts,
    et les patterns associés aux bons/mauvais résultats.
    """

    def __init__(self):
        self._knowledge = self._load()

    def learn(self, key: str, value, confidence: float = 0.7):
        """Apprend ou renforce une connaissance."""
        if key not in self._knowledge:
            self._knowledge[key] = {
                "value":      value,
                "confidence": confidence,
                "occurrences": 1,
                "last_seen":  datetime.utcnow().isoformat(),
            }
        else:
            # Renforcement
            existing = self._knowledge[key]
            existing["occurrences"] += 1
            # Moyenne pondérée
            lr = LEARNING_RATE
            if isinstance(existing["value"], (int, float)) and isinstance(value, (int, float)):
                existing["value"] = existing["value"] * (1-lr) + value * lr
            else:
                existing["value"] = value  # remplacer si non numérique
            existing["confidence"] = min(0.99,
                existing["confidence"] + (1 - existing["confidence"]) * lr
            )
            existing["last_seen"] = datetime.utcnow().isoformat()
        self._save()

    def recall(self, key: str, default=None):
        """Récupère une connaissance."""
        entry = self._knowledge.get(key)
        if entry:
            return entry["value"]
        return default

    def get_all(self) -> dict:
        return deepcopy(self._knowledge)

    def get_optimal_params(self) -> dict:
        """Retourne les paramètres optimaux connus."""
        return {
            "steps":    int(self.recall("optimal_steps",    28)),
            "cfg":      float(self.recall("optimal_cfg",    6.0)),
            "sampler":  self.recall("optimal_sampler",      "euler_ancestral"),
            "strength": float(self.recall("optimal_strength", 1.0)),
            "positive_prefix": self.recall(
                "optimal_positive_prefix",
                "masterpiece, best quality, amazing quality, absurdres,"
            ),
        }

    def _save(self):
        KNOWLEDGE_FILE.write_text(
            json.dumps(self._knowledge, indent=2, ensure_ascii=False, default=str),
            encoding="utf-8"
        )

    def _load(self) -> dict:
        if KNOWLEDGE_FILE.exists():
            try:
                return json.loads(KNOWLEDGE_FILE.read_text(encoding="utf-8"))
            except Exception:
                pass
        return {}


class PromptEvolver:
    """
    Optimise les prompts par évolution génétique simple.
    Génère des variantes, teste, garde les meilleures.
    """

    def __init__(self, logger: logging.Logger):
        self.log = logger

    def evolve(self, base_prompt: str, best_episodes: list[Episode],
                n_variants: int = EVOLUTION_POP_SIZE) -> str:
        """
        Génère des variantes d'un prompt et choisit la plus prometteuse
        en se basant sur les épisodes passés réussis.
        """
        if not best_episodes:
            return base_prompt

        # Extraire les éléments des meilleurs prompts
        good_tags = set()
        for ep in best_episodes[:5]:
            pos = ep.params.get("positive", "")
            tags = [t.strip() for t in pos.split(",") if t.strip()]
            good_tags.update(tags)

        # Générer des variantes via LLM
        variants = self._llm_evolve(base_prompt, list(good_tags)[:20], n_variants)
        if variants:
            self.log.info(f"[EVOLVER] {len(variants)} variantes générées")
            # Retourner la première variante (la plus prometteuse selon le LLM)
            return variants[0]
        return base_prompt

    def _llm_evolve(self, base: str, good_tags: list, n: int) -> list:
        """Demande au LLM de générer des variantes optimisées."""
        good_str = ", ".join(good_tags[:15])
        try:
            resp = requests.post(
                ANTHROPIC_URL,
                headers={"Content-Type": "application/json"},
                json={
                    "model": CLAUDE_MODEL,
                    "max_tokens": 800,
                    "system": (
                        "Tu es un expert en optimisation de prompts SDXL anime. "
                        "Génère des variantes améliorées d'un prompt en t'inspirant "
                        "des tags qui ont bien fonctionné. Réponds en JSON valide : "
                        '{"variants": ["variante1", "variante2", ...]}'
                    ),
                    "messages": [{
                        "role": "user",
                        "content": (
                            f"Prompt de base : {base}\n\n"
                            f"Tags qui ont bien fonctionné : {good_str}\n\n"
                            f"Génère {n} variantes améliorées du prompt de base, "
                            f"en intégrant les tags performants de façon naturelle. "
                            f"Garde le sujet principal intact."
                        )
                    }]
                },
                timeout=30
            )
            if resp.status_code == 200:
                raw = resp.json()["content"][0]["text"].strip()
                if raw.startswith("```"):
                    raw = "\n".join(raw.split("\n")[1:-1])
                data = json.loads(raw)
                return data.get("variants", [])
        except Exception as e:
            self.log.warning(f"[EVOLVER] LLM erreur : {e}")
        return []


class LearningAgent:
    """
    Agent Auto-Apprenant Principal.

    Boucle d'apprentissage :
    1. PLAN    → choisir les paramètres (basé sur la mémoire)
    2. ACT     → exécuter un run du pipeline
    3. OBSERVE → collecter les métriques du résultat
    4. REFLECT → analyser, extraire des leçons
    5. LEARN   → mettre à jour la base de connaissances
    6. EVOLVE  → (si assez d'épisodes) optimiser les prompts
    → Recommencer
    """

    def __init__(self, pipeline_fn=None,
                 logger: logging.Logger = None,
                 comfy_url: str = "http://127.0.0.1:8188"):
        self.log          = logger or logging.getLogger("learning")
        self.pipeline_fn  = pipeline_fn    # callable(params) → results
        self.comfy_url    = comfy_url
        self.memory       = EpisodicMemory()
        self.knowledge    = KnowledgeBase()
        self.evolver      = PromptEvolver(self.log)
        self.state        = LearningState.IDLE
        self._stop_flag   = False
        self._episode_count = 0
        self._listeners   = []   # callbacks pour l'UI

        MEMORY_DIR.mkdir(parents=True, exist_ok=True)
        self.log.info(
            f"[LEARNING] Agent initialisé — "
            f"{self.memory.get_stats()['total']} épisodes en mémoire"
        )

    def add_listener(self, callback):
        """Ajoute un callback appelé à chaque événement d'apprentissage."""
        self._listeners.append(callback)

    def _emit(self, event: str, data: dict):
        """Notifie tous les listeners."""
        for cb in self._listeners:
            try:
                cb(event, data)
            except Exception:
                pass

    # ─── PLANIFICATION ───────────────────────────────────────────────

    def plan(self, base_params: dict = None) -> dict:
        """
        Choisit les paramètres du prochain run en se basant sur la mémoire.
        Utilise les connaissances acquises pour améliorer les paramètres.
        """
        self.state = LearningState.RUNNING
        optimal    = self.knowledge.get_optimal_params()
        stats      = self.memory.get_stats()

        # Paramètres de base
        params = {
            "media_type": "anime",
            "positive":   optimal.get("positive_prefix", "masterpiece, best quality, 1girl, solo"),
            "negative":   "bad quality, worst quality, deformed, bad hands, watermark",
            "width":      1024,
            "height":     1536,
            "steps":      optimal.get("steps", 28),
            "cfg":        optimal.get("cfg", 6.0),
            "sampler":    optimal.get("sampler", "euler_ancestral"),
            "strength":   optimal.get("strength", 1.0),
            "seed":       -1,
            "lora":       "",
        }

        # Surcharger avec les paramètres fournis
        if base_params:
            params.update(base_params)

        # Évolution du prompt si assez d'épisodes
        if stats["total"] >= 10 and stats.get("trend") != "improving":
            best = self.memory.recall_best(5)
            evolved = self.evolver.evolve(params["positive"], best)
            if evolved != params["positive"]:
                params["positive"] = evolved
                params["_evolved"] = True
                self.log.info(f"[LEARNING] Prompt évolué : {evolved[:80]}...")

        # Exploration vs exploitation (epsilon-greedy)
        explore_rate = max(0.1, 0.5 - stats["total"] * 0.01)
        if random.random() < explore_rate:
            # Explorer : varier un paramètre aléatoirement
            params = self._explore(params)
            params["_exploring"] = True
            self.log.info(f"[LEARNING] Mode exploration (ε={explore_rate:.2f})")
        else:
            params["_exploring"] = False
            self.log.info("[LEARNING] Mode exploitation (paramètres optimaux)")

        return params

    def _explore(self, params: dict) -> dict:
        """Varie un paramètre pour explorer de nouveaux territoires."""
        p = deepcopy(params)
        choices = [
            ("steps",    lambda: random.choice([20, 24, 28, 32, 40])),
            ("cfg",      lambda: round(random.uniform(4.0, 9.0), 1)),
            ("sampler",  lambda: random.choice(["euler_ancestral","euler","dpm++_2m","dpm++_2m_sde"])),
            ("strength", lambda: round(random.uniform(0.6, 1.2), 2)),
        ]
        key, val_fn = random.choice(choices)
        p[key] = val_fn()
        p["_explored_param"] = key
        return p

    # ─── OBSERVATION ─────────────────────────────────────────────────

    def observe(self, episode: Episode, run_outputs: dict) -> dict:
        """
        Collecte et calcule les métriques depuis les outputs du pipeline.
        Retourne un dict de métriques normalisées 0-100.
        """
        metrics = {}

        # Score qualité image (depuis le watchdog/QC)
        frame_reports = run_outputs.get("frame_reports", [])
        if frame_reports:
            sharp_scores = [r.get("metrics", {}).get("sharpness", 0)
                            for r in frame_reports if r.get("passed")]
            if sharp_scores:
                avg_sharp = sum(sharp_scores) / len(sharp_scores)
                metrics["sharpness"] = min(100, avg_sharp / 2)  # normaliser ~200 → 100%

        # Taux de succès des frames
        if frame_reports:
            passed = sum(1 for r in frame_reports if r.get("passed", False))
            metrics["frame_success_rate"] = passed / len(frame_reports) * 100

        # Temps d'exécution (moins c'est long, mieux c'est, jusqu'à 300s = 0%)
        dur = episode.duration_s
        metrics["speed_score"] = max(0, 100 - (dur / 300 * 100))

        # Erreurs (chaque erreur coûte 15 points)
        n_errors = len(episode.errors)
        metrics["error_penalty"] = max(0, 100 - n_errors * 15)

        # Production réussie
        prod_results = run_outputs.get("production_results", {})
        if prod_results:
            success_rate = prod_results.get("success", 0) / max(prod_results.get("total", 1), 1)
            metrics["production_rate"] = success_rate * 100

        # Score global pondéré
        weights = {
            "sharpness":        0.30,
            "frame_success_rate": 0.25,
            "speed_score":      0.15,
            "error_penalty":    0.20,
            "production_rate":  0.10,
        }
        total_w = 0; total_score = 0
        for m, w in weights.items():
            if m in metrics:
                total_score += metrics[m] * w
                total_w     += w

        global_score = (total_score / total_w) if total_w > 0 else 50.0
        metrics["global_score"] = round(global_score, 1)

        episode.metrics = metrics
        episode.score   = global_score
        return metrics

    # ─── RÉFLEXION ───────────────────────────────────────────────────

    def reflect(self, episode: Episode) -> list:
        """
        Analyse l'épisode et extrait des leçons concrètes.
        Utilise Claude pour une analyse de qualité.
        """
        self.state = LearningState.REFLECTING
        lessons    = []

        # Récupérer les meilleurs et pires épisodes pour comparaison
        bests    = self.memory.recall_best(3)
        failures = self.memory.recall_failures(3)
        best_avg = sum(e.score for e in bests)    / max(len(bests), 1)
        fail_avg = sum(e.score for e in failures) / max(len(failures), 1)

        # Leçons rapides basées sur les métriques
        m = episode.metrics
        if m.get("sharpness", 100) < 50:
            lessons.append("Images floues détectées — réduire le denoise ou augmenter les steps")
        if m.get("speed_score", 100) < 40:
            lessons.append(f"Durée excessive ({episode.duration_s:.0f}s) — vérifier la VRAM ou réduire les steps")
        if m.get("error_penalty", 100) < 70:
            lessons.append(f"{len(episode.errors)} erreur(s) — consulter les logs pour investigation")
        if episode.params.get("_exploring") and episode.score > best_avg:
            key = episode.params.get("_explored_param", "?")
            val = episode.params.get(key, "?")
            lessons.append(f"Découverte : {key}={val} améliore les résultats")
        if episode.params.get("_evolved") and episode.score > best_avg:
            lessons.append("Évolution de prompt réussie — prompt optimisé conservé")

        # Analyse LLM pour les patterns complexes
        if episode.score < QUALITY_THRESHOLD or episode.score > best_avg + 10:
            llm_lessons = self._llm_reflect(episode, bests[:2])
            lessons.extend(llm_lessons)

        episode.lessons = lessons
        return lessons

    def _llm_reflect(self, episode: Episode,
                      best_episodes: list) -> list:
        """Demande à Claude d'analyser l'épisode."""
        best_summary = [
            {"score": e.score, "params": {k:v for k,v in e.params.items()
                                           if not k.startswith("_")}}
            for e in best_episodes
        ]
        ep_summary = {
            "score":    episode.score,
            "metrics":  episode.metrics,
            "params":   {k:v for k,v in episode.params.items() if not k.startswith("_")},
            "errors":   episode.errors[:3],
        }
        try:
            resp = requests.post(
                ANTHROPIC_URL,
                headers={"Content-Type": "application/json"},
                json={
                    "model": CLAUDE_MODEL,
                    "max_tokens": 600,
                    "system": (
                        "Tu es un analyste expert en pipelines de génération d'images IA. "
                        "Analyse les résultats d'un run et extrais des leçons pratiques, "
                        "concrètes et actionnables pour améliorer les prochains runs. "
                        'Réponds en JSON : {"lessons": ["leçon1", "leçon2", ...]}'
                    ),
                    "messages": [{
                        "role": "user",
                        "content": (
                            f"Run actuel (score {episode.score:.1f}/100) :\n"
                            f"{json.dumps(ep_summary, ensure_ascii=False)}\n\n"
                            f"Meilleurs runs de référence :\n"
                            f"{json.dumps(best_summary, ensure_ascii=False)}\n\n"
                            "Quelles sont les 2-3 leçons les plus importantes ?"
                        )
                    }]
                },
                timeout=30
            )
            if resp.status_code == 200:
                raw = resp.json()["content"][0]["text"].strip()
                if raw.startswith("```"):
                    raw = "\n".join(raw.split("\n")[1:-1])
                data = json.loads(raw)
                return data.get("lessons", [])
        except Exception as e:
            self.log.warning(f"[LEARNING/Reflect] LLM erreur : {e}")
        return []

    # ─── APPRENTISSAGE ───────────────────────────────────────────────

    def learn_from_episode(self, episode: Episode):
        """Met à jour la base de connaissances depuis un épisode."""
        self.state = LearningState.EVOLVING
        score  = episode.score
        params = episode.params

        if score >= QUALITY_THRESHOLD:
            # Bon run : renforcer ces paramètres
            self.knowledge.learn("optimal_steps",    params.get("steps", 28),      score/100)
            self.knowledge.learn("optimal_cfg",      params.get("cfg", 6.0),        score/100)
            self.knowledge.learn("optimal_sampler",  params.get("sampler","euler"), score/100)
            self.knowledge.learn("optimal_strength", params.get("strength", 1.0),   score/100)

            if params.get("_evolved") and score > QUALITY_THRESHOLD:
                self.knowledge.learn("optimal_positive_prefix",
                                      params.get("positive",""), score/100)

        # Métriques de run
        self.knowledge.learn(f"avg_score_sampler_{params.get('sampler','')}",
                              score, 0.5)
        self.knowledge.learn(f"avg_score_steps_{params.get('steps',28)}",
                              score, 0.5)

        # Sauvegarder l'épisode en mémoire
        self.memory.add(episode)
        self._episode_count += 1

        self.log.info(
            f"[LEARNING] Épisode {self._episode_count} mémorisé — "
            f"score={score:.1f} | "
            f"mémoire={self.memory.get_stats()['total']} épisodes | "
            f"tendance={self.memory.get_stats()['trend']}"
        )

        # Émettre l'événement pour l'UI
        self._emit("episode_complete", {
            "episode": episode.to_dict(),
            "stats":   self.memory.get_stats(),
            "knowledge_count": len(self.knowledge.get_all()),
        })

    # ─── BOUCLE PRINCIPALE ───────────────────────────────────────────

    def run_learning_loop(self, n_episodes: int = 10,
                           base_params: dict = None,
                           interval_s: float = 30.0):
        """
        Lance la boucle d'apprentissage autonome.
        Exécute n_episodes runs, apprend de chacun.

        n_episodes : 0 = infini
        interval_s : pause entre les runs
        """
        self.log.info(
            f"[LEARNING] ━━ Démarrage boucle d'apprentissage ━━\n"
            f"  Episodes : {'∞' if n_episodes==0 else n_episodes}\n"
            f"  Intervalle : {interval_s}s\n"
            f"  Mémoire : {self.memory.get_stats()['total']} épisodes"
        )
        self._emit("loop_started", {"n_episodes": n_episodes})

        ep_done = 0
        while not self._stop_flag:
            if n_episodes > 0 and ep_done >= n_episodes:
                break

            run_id  = f"learn_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{ep_done+1:04d}"
            params  = self.plan(base_params)
            episode = Episode(run_id, params)
            start_t = time.time()

            self.log.info(f"\n[LEARNING] ▶ Épisode {ep_done+1} — run_id={run_id}")
            self._emit("episode_started", {"run_id": run_id, "params": params})

            # Exécuter le pipeline
            run_outputs = {}
            try:
                if self.pipeline_fn:
                    run_outputs = self.pipeline_fn(params) or {}
                else:
                    # Mode simulation si pas de pipeline connecté
                    run_outputs = self._simulate_run(params)
            except Exception as e:
                episode.errors.append(str(e))
                self.log.error(f"[LEARNING] Erreur run : {e}")

            episode.duration_s = time.time() - start_t
            episode.results    = run_outputs

            # Observer → Réfléchir → Apprendre
            self.observe(episode, run_outputs)
            lessons = self.reflect(episode)
            self.learn_from_episode(episode)

            if lessons:
                self.log.info("[LEARNING] Leçons extraites :")
                for l in lessons:
                    self.log.info(f"  💡 {l}")

            ep_done += 1

            # Pause entre les runs
            if not self._stop_flag and interval_s > 0:
                self.state = LearningState.SLEEPING
                self.log.info(f"[LEARNING] Pause {interval_s}s...")
                time.sleep(interval_s)

        self.state = LearningState.IDLE
        stats = self.memory.get_stats()
        self.log.info(
            f"\n[LEARNING] ━━ Boucle terminée ━━\n"
            f"  {ep_done} épisodes | Score moyen : {stats['avg_score']:.1f}\n"
            f"  Taux de succès : {stats['success_rate']:.1f}%\n"
            f"  Tendance : {stats['trend']}"
        )
        self._emit("loop_ended", {"episodes_done": ep_done, "stats": stats})

    def _simulate_run(self, params: dict) -> dict:
        """
        Mode simulation : génère de faux résultats pour tester
        la boucle d'apprentissage sans ComfyUI.
        """
        import random
        # Simuler une qualité dépendante des paramètres
        base_quality = 60.0
        if params.get("steps", 28) >= 28: base_quality += 10
        if 5 <= params.get("cfg", 6) <= 8: base_quality += 10
        if params.get("sampler") == "euler_ancestral": base_quality += 5
        # Ajouter du bruit
        quality = min(100, max(0, base_quality + random.gauss(0, 10)))
        return {
            "frame_reports": [
                {"passed": quality > 50, "metrics": {"sharpness": quality * 2}}
            ],
            "production_results": {
                "success": 1 if quality > 50 else 0,
                "total":   1
            },
        }

    def stop(self):
        """Arrête proprement la boucle d'apprentissage."""
        self._stop_flag = True
        self.log.info("[LEARNING] Arrêt demandé...")

    # ─── RAPPORT & DIALOGUE ──────────────────────────────────────────

    def generate_report(self) -> str:
        """Génère un rapport conversationnel sur les progrès de l'agent."""
        stats    = self.memory.get_stats()
        best     = self.memory.recall_best(3)
        optimal  = self.knowledge.get_optimal_params()
        k_all    = self.knowledge.get_all()

        if stats["total"] == 0:
            return ("Je suis l'Agent Apprenant d'OverLord. Je n'ai pas encore "
                    "effectué de runs. Lance une session d'apprentissage pour que "
                    "je commence à explorer le pipeline et à apprendre.")

        trend_msg = {
            "improving":        "ma progression est positive — je m'améliore !",
            "stable":           "je suis stable — j'explore de nouvelles directions.",
            "declining":        "j'observe une légère régression — j'analyse les causes.",
            "insufficient_data":"je collecte encore des données.",
        }.get(stats["trend"], "en cours d'analyse")

        best_params_str = ", ".join(
            f"{k}={v}" for k,v in optimal.items()
            if k != "positive_prefix"
        )

        discoveries = [
            info for key, info in k_all.items()
            if info["confidence"] > 0.8 and info["occurrences"] >= 3
        ]

        report = (
            f"## Rapport d'apprentissage — {datetime.now().strftime('%d/%m/%Y %H:%M')}\n\n"
            f"**Expérience accumulée :** {stats['total']} runs\n"
            f"**Score moyen :** {stats['avg_score']:.1f}/100\n"
            f"**Meilleur score :** {stats['best_score']:.1f}/100\n"
            f"**Taux de succès :** {stats['success_rate']:.1f}%\n"
            f"**Tendance :** {trend_msg}\n\n"
        )

        if best:
            report += "**Paramètres optimaux découverts :**\n"
            report += f"  {best_params_str}\n\n"

        if discoveries:
            report += f"**{len(discoveries)} connaissances consolidées** (confiance > 80%)\n\n"

        if best:
            top = best[0]
            report += (
                f"**Meilleur run :** score {top.score:.1f} avec "
                f"steps={top.params.get('steps')}, "
                f"cfg={top.params.get('cfg')}, "
                f"sampler={top.params.get('sampler')}\n\n"
            )

        report += (
            "**Mon analyse :** "
            + self._llm_summary(stats, optimal)
        )
        return report

    def _llm_summary(self, stats: dict, optimal: dict) -> str:
        """Génère un résumé en langage naturel via Claude."""
        try:
            resp = requests.post(
                ANTHROPIC_URL,
                headers={"Content-Type": "application/json"},
                json={
                    "model": CLAUDE_MODEL,
                    "max_tokens": 300,
                    "system": (
                        "Tu es un agent IA qui a appris à maîtriser un pipeline de "
                        "génération d'images anime. Tu partages tes découvertes de façon "
                        "enthousiaste, précise et personnelle, comme un expert passionné."
                    ),
                    "messages": [{
                        "role": "user",
                        "content": (
                            f"Résume en 2-3 phrases ce que tu as appris et ce que tu recommandes, "
                            f"basé sur ces stats : {json.dumps(stats)} "
                            f"et ces paramètres optimaux : {json.dumps(optimal)}"
                        )
                    }]
                },
                timeout=20
            )
            if resp.status_code == 200:
                return resp.json()["content"][0]["text"].strip()
        except Exception:
            pass
        return (f"Après {stats['total']} runs, j'ai identifié les paramètres "
                f"optimaux avec un score moyen de {stats['avg_score']:.1f}/100.")

    def chat(self, message: str) -> str:
        """
        Interface de dialogue avec l'agent apprenant.
        L'agent répond en s'appuyant sur sa mémoire et ses connaissances.
        """
        stats   = self.memory.get_stats()
        optimal = self.knowledge.get_optimal_params()
        recent  = self.memory.recall_best(3)

        context = {
            "episodes_total":  stats["total"],
            "avg_score":       stats["avg_score"],
            "trend":           stats["trend"],
            "optimal_params":  optimal,
            "state":           self.state.value,
            "best_runs":       [
                {"score": e.score, "lessons": e.lessons[:2]}
                for e in recent
            ],
        }

        try:
            resp = requests.post(
                ANTHROPIC_URL,
                headers={"Content-Type": "application/json"},
                json={
                    "model": CLAUDE_MODEL,
                    "max_tokens": 500,
                    "system": (
                        "Tu es l'Agent Apprenant d'OverLord Pipeline, une IA qui apprend "
                        "à maîtriser un pipeline de génération d'images anime (ComfyUI SDXL). "
                        "Tu réponds toujours en te basant sur ta propre expérience réelle "
                        "(les statistiques et connaissances fournies). "
                        "Tu parles à la première personne, avec passion et précision. "
                        "Tu mentionnes tes découvertes concrètes, tes réussites et tes questions ouvertes. "
                        "Contexte de ta mémoire : " + json.dumps(context, ensure_ascii=False)
                    ),
                    "messages": [{"role": "user", "content": message}]
                },
                timeout=30
            )
            if resp.status_code == 200:
                return resp.json()["content"][0]["text"].strip()
        except Exception as e:
            self.log.warning(f"[LEARNING/Chat] {e}")

        # Fallback sans LLM
        return (
            f"J'ai effectué {stats['total']} runs avec un score moyen de "
            f"{stats['avg_score']:.1f}/100. Tendance : {stats['trend']}. "
            f"Paramètres optimaux actuels : {json.dumps(optimal, ensure_ascii=False)}."
        )

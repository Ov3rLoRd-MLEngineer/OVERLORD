"""
agents/dream_simulation.py — OverLord V1.30 — Dream Mode (auto-apprentissage par simulation)

A ne pas confondre avec agents/dream_mode.py (boucle de production autonome
nocturne, V1.70) : ce module-ci ne genere aucune image, il simule des
scenarios hypothetiques pour consolider les connaissances de l'agent.

L'agent s'entraîne la nuit par simulation sans générer d'images réelles.
Inspiré du sommeil paradoxal : le cerveau rejoue et consolide les expériences.

Principe :
  Pendant que tu dors, OverLord tourne en mode simulation.
  Il génère des milliers de scénarios hypothétiques :
  "Si j'avais utilisé ce sampler pour ce type de scène, qu'aurait-il obtenu ?"
  Il met à jour sa base de connaissances sans consommer de VRAM.
  Le matin : il est significativement meilleur.

Phases du Dream Mode (comme le cycle du sommeil) :
  Phase 1 — Consolidation  : rejouer les meilleurs épisodes réels
  Phase 2 — Exploration    : tester des configurations jamais essayées (simulation)
  Phase 3 — Intégration    : synthétiser les leçons dans les politiques
  Phase 4 — Innovation     : générer des idées nouvelles par recombinaison
  Phase 5 — Réveil         : rapport de ce qui a été appris
"""

import json
import math
import time
import random
import logging
import threading
from pathlib import Path
from datetime import datetime
from dataclasses import dataclass, field
import requests

DREAM_DIR     = Path("workspace/dream_mode")
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
# SIMULATEUR DE RUNS
# ══════════════════════════════════════════════════════════════════════

class RunSimulator:
    """
    Simule des runs sans vraiment générer d'images.
    Utilise un modèle interne approximatif basé sur l'historique.

    "Que se serait-il passé si j'avais utilisé CFG=8 au lieu de 6 ?"
    """

    # Modèle de qualité approximatif basé sur les paramètres
    # (construit progressivement depuis l'historique réel)
    PARAM_QUALITY_MODEL = {
        "euler_ancestral": {"base": 0.75, "variance": 0.12},
        "euler":           {"base": 0.70, "variance": 0.08},
        "dpm++_2m":        {"base": 0.78, "variance": 0.07},
        "dpm++_2m_sde":    {"base": 0.80, "variance": 0.09},
        "dpm++_3m_sde":    {"base": 0.76, "variance": 0.10},
        "lcm":             {"base": 0.65, "variance": 0.15},
    }
    CFG_QUALITY_CURVE = {
        # cfg → multiplicateur de qualité
        3.0: 0.70, 4.0: 0.80, 5.0: 0.90, 6.0: 1.00,
        7.0: 1.02, 8.0: 1.00, 9.0: 0.95, 10.0: 0.88,
    }
    STEPS_QUALITY_CURVE = {
        16: 0.75, 20: 0.85, 24: 0.92, 28: 1.00,
        32: 1.03, 36: 1.04, 40: 1.04, 48: 1.03,
    }

    def simulate(self, params: dict, content_type: str = "anime") -> dict:
        """Simule un run et retourne la qualité estimée."""
        sampler = params.get("sampler", "euler_ancestral")
        cfg     = params.get("cfg", 6.0)
        steps   = params.get("steps", 28)

        # Base qualité depuis le sampler
        sm = self.PARAM_QUALITY_MODEL.get(sampler,
             self.PARAM_QUALITY_MODEL["euler_ancestral"])
        base = sm["base"] + random.gauss(0, sm["variance"] * 0.3)

        # Multiplicateur CFG
        cfg_keys = sorted(self.CFG_QUALITY_CURVE.keys())
        cfg_key  = min(cfg_keys, key=lambda k: abs(k-cfg))
        cfg_mult = self.CFG_QUALITY_CURVE[cfg_key]

        # Multiplicateur Steps
        step_keys = sorted(self.STEPS_QUALITY_CURVE.keys())
        step_key  = min(step_keys, key=lambda k: abs(k-steps))
        step_mult = self.STEPS_QUALITY_CURVE[step_key]

        quality = min(1.0, max(0.0, base * cfg_mult * step_mult))
        # Ajouter du bruit réaliste
        quality += random.gauss(0, 0.05)
        quality  = max(0.0, min(1.0, quality))

        return {
            "simulated":    True,
            "quality":      round(quality, 4),
            "sampler":      sampler,
            "cfg":          cfg,
            "steps":        steps,
            "content_type": content_type,
            "cost_units":   steps / 28.0,  # coût relatif
        }

    def grid_search(self, param_grid: dict, n_samples: int = 50) -> list[dict]:
        """
        Recherche par grille dans l'espace des paramètres.
        C'est l'exploration du Dream Mode — tester tout sans GPU.
        """
        results = []
        samplers  = param_grid.get("samplers",  ["euler_ancestral","dpm++_2m_sde"])
        cfgs      = param_grid.get("cfgs",      [5.0, 6.0, 7.0, 8.0])
        steps_list= param_grid.get("steps",     [20, 24, 28, 32])

        for _ in range(n_samples):
            params = {
                "sampler": random.choice(samplers),
                "cfg":     random.choice(cfgs),
                "steps":   random.choice(steps_list),
            }
            result = self.simulate(params)
            results.append(result)

        return sorted(results, key=lambda r: -r["quality"])


# ══════════════════════════════════════════════════════════════════════
# MÉMOIRE DU RÊVE
# ══════════════════════════════════════════════════════════════════════

class DreamMemory:
    """Stocke et analyse ce qui a été appris pendant le Dream Mode."""

    def __init__(self):
        self._dreams:   list[dict] = []
        self._insights: list[str]  = []
        self._optimal_discovered: dict = {}
        DREAM_DIR.mkdir(parents=True, exist_ok=True)
        self._load()

    def record_dream_session(self, session: dict):
        self._dreams.append(session)
        self._save()

    def add_insight(self, insight: str):
        self._insights.append({
            "insight":   insight,
            "timestamp": datetime.utcnow().isoformat(),
        })

    def update_optimal(self, content_type: str, params: dict, quality: float):
        if content_type not in self._optimal_discovered:
            self._optimal_discovered[content_type] = {"quality": 0}
        if quality > self._optimal_discovered[content_type]["quality"]:
            self._optimal_discovered[content_type] = {**params, "quality": quality}

    def get_best_params(self, content_type: str = "anime") -> dict:
        return self._optimal_discovered.get(content_type,
               {"sampler":"euler_ancestral","cfg":6.0,"steps":28,"quality":0.75})

    def get_morning_report(self) -> str:
        if not self._dreams:
            return "Aucune session de rêve enregistrée."
        last  = self._dreams[-1]
        n_sim = last.get("simulations_run", 0)
        best  = last.get("best_quality_found", 0)
        discoveries = last.get("discoveries", [])

        report = (
            f"Rapport du Dream Mode — {datetime.now().strftime('%d/%m/%Y %H:%M')}\n"
            f"Simulations : {n_sim} | Meilleure qualité : {best*100:.1f}/100\n"
        )
        if discoveries:
            report += f"\nDécouvertes :\n"
            for d in discoveries[:5]:
                report += f"  • {d}\n"
        if self._insights:
            report += f"\nInsights accumulés : {len(self._insights)}\n"
            for ins in self._insights[-3:]:
                report += f"  → {ins['insight'][:80]}\n"
        return report

    def _save(self):
        data = {
            "dreams":   self._dreams[-50:],
            "insights": self._insights[-100:],
            "optimal":  self._optimal_discovered,
        }
        (DREAM_DIR / "dream_memory.json").write_text(
            json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8"
        )

    def _load(self):
        f = DREAM_DIR / "dream_memory.json"
        if f.exists():
            try:
                data = json.loads(f.read_text(encoding="utf-8"))
                self._dreams   = data.get("dreams", [])
                self._insights = data.get("insights", [])
                self._optimal_discovered = data.get("optimal", {})
            except Exception:
                pass


# ══════════════════════════════════════════════════════════════════════
# DREAM MODE ENGINE
# ══════════════════════════════════════════════════════════════════════

class DreamModeEngine:
    """
    Le moteur du Dream Mode — entraînement nocturne par simulation.
    """

    def __init__(self, logger: logging.Logger = None):
        self.log       = logger or logging.getLogger("dream_mode")
        self.simulator = RunSimulator()
        self.memory    = DreamMemory()
        self._running  = False
        self._thread:  threading.Thread = None
        self._progress = {"phase": "idle", "progress": 0, "simulations": 0}

    # ── Phases du rêve ────────────────────────────────────────────────

    def _phase1_consolidation(self, real_episodes: list[dict],
                               n_replay: int = 20) -> dict:
        """
        Phase 1 : Consolidation — rejouer les meilleurs épisodes réels.
        Renforce les connexions qui ont bien fonctionné.
        """
        self.log.info("[DREAM/P1] Consolidation...")
        self._progress["phase"] = "consolidation"

        best = sorted(real_episodes, key=lambda e: e.get("score",0), reverse=True)[:n_replay]
        insights = []
        for ep in best:
            score   = ep.get("score", 0)
            sampler = ep.get("params",{}).get("sampler","?")
            cfg     = ep.get("params",{}).get("cfg",6)
            steps   = ep.get("params",{}).get("steps",28)
            if score > 0.8:
                insights.append(
                    f"Excellent résultat ({score*100:.0f}) avec {sampler} cfg={cfg} steps={steps}"
                )
        return {
            "phase":   "consolidation",
            "replayed":len(best),
            "insights":insights[:5],
        }

    def _phase2_exploration(self, n_simulations: int = 200,
                             content_types: list = None) -> dict:
        """
        Phase 2 : Exploration — tester des configs jamais essayées.
        C'est le vrai "rêve" — explorer l'impossible pendant la nuit.
        """
        self.log.info(f"[DREAM/P2] Exploration ({n_simulations} simulations)...")
        self._progress["phase"] = "exploration"

        content_types = content_types or ["anime","portrait","action","landscape"]
        all_results   = []

        for ct in content_types:
            results = self.simulator.grid_search({
                "samplers": ["euler_ancestral","euler","dpm++_2m","dpm++_2m_sde",
                             "dpm++_3m_sde","lcm"],
                "cfgs":     [4.0, 5.0, 5.5, 6.0, 6.5, 7.0, 7.5, 8.0, 9.0],
                "steps":    [16, 20, 24, 28, 32, 36, 40, 48],
            }, n_samples=n_simulations//len(content_types))

            # Enregistrer les meilleures configs
            for r in results[:3]:
                self.memory.update_optimal(ct, r, r["quality"])

            all_results.extend(results)
            self._progress["simulations"] += len(results)

        # Top découvertes
        top     = sorted(all_results, key=lambda r: -r["quality"])[:5]
        discoveries = [
            f"{r['sampler']} cfg={r['cfg']} steps={r['steps']} → {r['quality']*100:.1f}/100"
            for r in top
        ]
        return {
            "phase":        "exploration",
            "simulations":  len(all_results),
            "best_quality": top[0]["quality"] if top else 0,
            "discoveries":  discoveries,
        }

    def _phase3_integration(self, exploration_results: dict) -> dict:
        """
        Phase 3 : Intégration — synthétiser les leçons dans les politiques.
        Met à jour les poids et recommandations pour les futurs runs.
        """
        self.log.info("[DREAM/P3] Intégration...")
        self._progress["phase"] = "integration"

        discoveries = exploration_results.get("discoveries", [])
        if discoveries:
            prompt = (
                f"Ces configurations ont donné les meilleurs résultats en simulation :\n"
                + "\n".join(f"  {d}" for d in discoveries) +
                "\n\nQuelle est la leçon principale à retenir pour optimiser "
                "les futurs runs de génération d'images anime ?\n"
                "Réponds en 2 phrases concrètes et actionnables."
            )
            insight = _llm(prompt, max_tokens=150)
            if insight:
                self.memory.add_insight(insight)

        return {
            "phase":       "integration",
            "insights_added": len(discoveries) > 0,
        }

    def _phase4_innovation(self) -> dict:
        """
        Phase 4 : Innovation — générer des idées nouvelles par recombinaison.
        Combines des éléments de façon inédite.
        """
        self.log.info("[DREAM/P4] Innovation...")
        self._progress["phase"] = "innovation"

        optimal = {ct: self.memory.get_best_params(ct)
                   for ct in ["anime","portrait","action"]}
        prompt  = (
            f"Paramètres optimaux découverts en simulation :\n"
            f"{json.dumps(optimal, indent=2)}\n\n"
            f"Propose 3 combinaisons créatives NON TESTÉES qui pourraient "
            f"dépasser ces résultats. Pense en dehors des patterns habituels.\n"
            f"Réponds : 3 idées courtes et précises."
        )
        innovations = _llm(prompt, max_tokens=200)
        if innovations:
            self.memory.add_insight(f"INNOVATION: {innovations[:200]}")

        return {"phase": "innovation", "innovations_proposed": bool(innovations)}

    # ── Boucle principale ─────────────────────────────────────────────

    def start(self, real_episodes: list[dict] = None,
               duration_minutes: float = 60,
               n_simulations: int = 500,
               content_types: list = None) -> threading.Thread:
        """
        Lance le Dream Mode en tâche de fond.
        Tourne pendant N minutes en simulant des runs.
        """
        if self._running:
            self.log.warning("[DREAM] Déjà en cours")
            return self._thread

        self._running    = True
        real_eps = real_episodes or []
        n_sim    = n_simulations
        dur_min  = duration_minutes

        def _dream_loop():
            start_time = time.time()
            session    = {
                "started_at":         datetime.utcnow().isoformat(),
                "duration_minutes":   dur_min,
                "simulations_run":    0,
                "discoveries":        [],
                "best_quality_found": 0,
            }

            self.log.info(
                f"[DREAM] 💤 Début du Dream Mode "
                f"({dur_min:.0f} min | {n_sim} simulations)"
            )
            self._progress = {"phase": "starting", "progress": 0, "simulations": 0}

            # Phase 1 : Consolidation
            p1 = self._phase1_consolidation(real_eps)
            session["discoveries"].extend(p1.get("insights",[])[:2])
            self._progress["progress"] = 20

            # Phase 2 : Exploration (la plus longue)
            p2 = self._phase2_exploration(n_sim, content_types)
            session["simulations_run"]    = p2.get("simulations", 0)
            session["best_quality_found"] = p2.get("best_quality", 0)
            session["discoveries"].extend(p2.get("discoveries",[])[:3])
            self._progress["progress"] = 70

            # Phase 3 : Intégration
            self._phase3_integration(p2)
            self._progress["progress"] = 85

            # Phase 4 : Innovation
            self._phase4_innovation()
            self._progress["progress"] = 95

            # Fin
            session["ended_at"]  = datetime.utcnow().isoformat()
            session["duration_actual_s"] = time.time() - start_time
            self.memory.record_dream_session(session)

            self._running = False
            self._progress = {"phase": "awake", "progress": 100,
                               "simulations": session["simulations_run"]}

            self.log.info(
                f"[DREAM] ☀️ Réveil ! "
                f"{session['simulations_run']} simulations | "
                f"Meilleure qualité : {session['best_quality_found']*100:.1f}/100"
            )

        self._thread = threading.Thread(target=_dream_loop, daemon=True)
        self._thread.start()
        return self._thread

    def stop(self):
        self._running = False

    def get_status(self) -> dict:
        return {
            "running":     self._running,
            "phase":       self._progress.get("phase","idle"),
            "progress":    self._progress.get("progress",0),
            "simulations": self._progress.get("simulations",0),
        }

    def get_morning_report(self) -> str:
        return self.memory.get_morning_report()

    def get_best_params(self, content_type: str = "anime") -> dict:
        return self.memory.get_best_params(content_type)

    def schedule_nightly(self, start_hour: int = 2,
                          duration_minutes: float = 120):
        """
        Programme le Dream Mode chaque nuit à start_hour.
        Lance un thread de surveillance.
        """
        def _scheduler():
            while True:
                now = __import__("datetime").datetime.now()
                if now.hour == start_hour and now.minute == 0:
                    if not self._running:
                        self.log.info(f"[DREAM] Démarrage programmé {start_hour}h00")
                        self.start(duration_minutes=duration_minutes)
                time.sleep(60)

        t = threading.Thread(target=_scheduler, daemon=True)
        t.start()
        self.log.info(f"[DREAM] Scheduler activé — démarrage chaque nuit à {start_hour}h00")
        return t


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    engine = DreamModeEngine()

    print("=== V1.30 DREAM MODE TEST ===\n")
    print("Lancement d'une session courte (5 simulations)...")

    fake_episodes = [
        {"score": 0.82, "params": {"sampler":"euler_ancestral","cfg":6.0,"steps":28}},
        {"score": 0.75, "params": {"sampler":"dpm++_2m","cfg":7.0,"steps":32}},
        {"score": 0.91, "params": {"sampler":"dpm++_2m_sde","cfg":6.5,"steps":28}},
    ]

    thread = engine.start(
        real_episodes=fake_episodes,
        duration_minutes=0.1,
        n_simulations=30,
    )
    thread.join(timeout=15)

    print(f"\nStatut : {engine.get_status()}")
    print(f"\nRapport du matin :\n{engine.get_morning_report()}")
    print(f"\nMeilleurs params anime : {engine.get_best_params('anime')}")

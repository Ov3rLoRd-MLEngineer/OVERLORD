"""
agents/director.py — Le Réalisateur Ov3rLoRd V1.48
═══════════════════════════════════════════════════════════════

Le chaînon manquant évoqué 7 fois dans les sessions précédentes.
Jamais construit. Construit maintenant.

Le Director est l'arbitre entre FACTORY et ATELIER.
Il orchestre TOUS les modules V1.30 + V1.47 via le context_bus.
Il décide de la tonalité de chaque run, de l'exigence du critique,
du niveau de créativité, de la fatigue émotionnelle du pipeline.

Il donne à Ov3rLoRd une INTENTION, pas juste des tâches.

Architecture :
    director.py
        ↓ lit le context_bus
        ↓ consulte emotion_engine, world_model, personality, intelligence_ext
        ↓ configure maestro.py, critic.py, storyboard.py, self_improve.py
        ↓ écrit ses décisions dans le context_bus pour tous les agents

Usage dans maestro.py :
    from agents.director import Director
    director = Director()
    intent = director.set_intent(media_type="anime", universe="Dragon Ball")
    # Tous les agents lisent intent depuis le context_bus automatiquement
"""

import json
import logging
import time
from pathlib import Path
from datetime import datetime
from enum import Enum
from typing import Optional

# ── Imports avec fallbacks complets ──────────────────────────────────
try:
    from agents.context_bus import get_bus, ContextBus
    BUS_OK = True
except ImportError:
    BUS_OK = False
    def get_bus(): return None

try:
    from agents.v130_emotion_engine import EmotionEngine
    EMOTION_OK = True
except ImportError:
    EMOTION_OK = False
    EmotionEngine = None

try:
    from agents.v130_world_model import WorldModel
    WORLD_OK = True
except ImportError:
    WORLD_OK = False
    WorldModel = None

try:
    from agents.v130_agent_personality import get_personality_manager
    PERSONALITY_OK = True
except ImportError:
    PERSONALITY_OK = False
    get_personality_manager = None

try:
    from agents.v130_intelligence_ext import IntelligenceExtV130
    INTEL_OK = True
except ImportError:
    INTEL_OK = False
    IntelligenceExtV130 = None

try:
    from agents.v130_generative_world import GenerativeWorld
    GENWORLD_OK = True
except ImportError:
    GENWORLD_OK = False
    GenerativeWorld = None

try:
    from agents.pipeline_conscience import PipelineConscience
    CONSCIENCE_OK = True
except ImportError:
    CONSCIENCE_OK = False
    PipelineConscience = None

try:
    from agents.overlord_utils import fallback_llm, safe_json_parse
    UTILS_OK = True
except ImportError:
    UTILS_OK = False

log = logging.getLogger("director")
DIRECTOR_DIR = Path("workspace/director")


# ── Mode de production ────────────────────────────────────────────────
class ProductionMode(Enum):
    FACTORY = "factory"    # Vitesse, volume, cohérence. 1 épisode/semaine.
    ATELIER = "atelier"    # Qualité, unicité, risque artistique.
    BALANCE = "balance"    # Entre les deux — mode par défaut.
    DREAM   = "dream"      # Expérimentation pure, pas de contrainte de qualité.


# ── Intent de run ─────────────────────────────────────────────────────
class RunIntent:
    """L'intention complète d'un run — ce que le Director a décidé."""

    def __init__(self):
        self.mode              = ProductionMode.BALANCE
        self.emotion_arc       = "tension_to_catharsis"
        self.emotion_params    = {}
        self.world_context     = {}
        self.personality_lead  = "viktor"   # Qui mène ce run
        self.quality_threshold = 70
        self.critic_strictness = 1.0
        self.creative_risk     = 0.5        # 0=safe, 1=maximal
        self.fatigue_level     = 0.0        # 0=fresh, 1=épuisé
        self.inspiration_boost = []
        self.world_run_id      = None
        self.created_at        = datetime.now().isoformat()

    def to_dict(self) -> dict:
        return {
            "mode":              self.mode.value,
            "emotion_arc":       self.emotion_arc,
            "emotion_params":    self.emotion_params,
            "world_context":     self.world_context,
            "personality_lead":  self.personality_lead,
            "quality_threshold": self.quality_threshold,
            "critic_strictness": self.critic_strictness,
            "creative_risk":     self.creative_risk,
            "fatigue_level":     self.fatigue_level,
            "inspiration_boost": self.inspiration_boost,
            "world_run_id":      self.world_run_id,
            "created_at":        self.created_at,
        }


class Director:
    """
    Le Réalisateur — orchestre tous les systèmes pour donner une intention au run.

    Il ne génère rien. Il configure tout.
    Chaque décision est écrite dans le context_bus pour que
    tous les agents puissent la lire sans couplage fort.
    """

    def __init__(self, series: str = "Ov3rLoRd", logger: logging.Logger = None):
        self.log    = logger or log
        self.series = series
        DIRECTOR_DIR.mkdir(parents=True, exist_ok=True)

        # Initialiser les systèmes disponibles
        self.bus         = get_bus() if BUS_OK else None
        self.emotion     = EmotionEngine() if EMOTION_OK else None
        self.world       = WorldModel(series) if WORLD_OK else None
        self.personality = get_personality_manager() if PERSONALITY_OK else None
        self.intel       = IntelligenceExtV130() if INTEL_OK else None
        self.genworld    = GenerativeWorld(series) if GENWORLD_OK else None
        self.conscience  = PipelineConscience() if CONSCIENCE_OK else None

        self._intent = RunIntent()
        self._history = []

        active = [k for k,v in {
            'context_bus':   BUS_OK,
            'emotion_engine':EMOTION_OK,
            'world_model':   WORLD_OK,
            'personality':   PERSONALITY_OK,
            'intelligence':  INTEL_OK,
            'gen_world':     GENWORLD_OK,
            'conscience':    CONSCIENCE_OK,
        }.items() if v]

        self.log.info(f"[DIRECTOR] Initialisé — {len(active)}/7 systèmes actifs : {active}")

    # ── Décision principale ───────────────────────────────────────────
    def set_intent(self, media_type: str = "anime", universe: str = "",
                   episode: int = 1, emotion_hint: str = "",
                   force_mode: Optional[ProductionMode] = None) -> RunIntent:
        """
        Point d'entrée principal — appelé par maestro.py au démarrage de chaque run.
        Consulte tous les systèmes et construit l'intention du run.
        """
        self.log.info(f"[DIRECTOR] ════ Construction de l'intention ════")
        self.log.info(f"[DIRECTOR] Série={self.series} | Ep={episode} | Media={media_type}")

        intent = RunIntent()

        # ── 1. Mode production ────────────────────────────────────────
        intent.mode = force_mode or self._decide_mode()
        self.log.info(f"[DIRECTOR] Mode : {intent.mode.value.upper()}")

        # ── 2. Paramètres adaptatifs depuis pipeline_conscience ───────
        if self.conscience:
            params = self.conscience.get_params()
            intent.quality_threshold = params.get("script_quality_threshold", 70)
            intent.critic_strictness = params.get("critic_strictness", 1.0)
            self.log.info(f"[DIRECTOR] Conscience : seuil={intent.quality_threshold} | strictness={intent.critic_strictness:.2f}")

        # ── 3. Contexte monde ─────────────────────────────────────────
        if self.world:
            try:
                world_ctx = self.world.get_context_for_run()
                intent.world_context = world_ctx
                intent.world_run_id  = world_ctx.get("run_id")
                self.log.info(f"[DIRECTOR] World : {len(world_ctx)} clés de contexte")
            except Exception as e:
                self.log.warning(f"[DIRECTOR] World Model : {e}")

        # Monde génératif en complément
        if self.genworld:
            try:
                self.genworld.advance_run(episode)
                gen_ctx = self.genworld.get_world_prompt_context()
                intent.world_context.update(gen_ctx)
                self.log.info(f"[DIRECTOR] GenWorld avancé → run {episode}")
            except Exception as e:
                self.log.warning(f"[DIRECTOR] GenWorld : {e}")

        # ── 4. Arc émotionnel ─────────────────────────────────────────
        if self.emotion:
            try:
                arc = self._choose_emotion_arc(episode, emotion_hint)
                intent.emotion_arc = arc
                ep_emotions = self.emotion.plan_episode_emotions(arc, n_shots=12)
                if ep_emotions:
                    # Premier shot = référence principale
                    first_emotion = ep_emotions[0]
                    intent.emotion_params = self.emotion.generate_params(
                        first_emotion.emotion if hasattr(first_emotion,'emotion') else arc,
                        intensity=0.8
                    )
                self.log.info(f"[DIRECTOR] Émotion : arc={arc}")
            except Exception as e:
                self.log.warning(f"[DIRECTOR] Emotion Engine : {e}")

        # ── 5. Personnalité dominante ─────────────────────────────────
        if self.personality:
            try:
                lead = self._choose_personality_lead(intent.mode)
                intent.personality_lead = lead
                self.log.info(f"[DIRECTOR] Personnalité dominante : {lead}")
            except Exception as e:
                self.log.warning(f"[DIRECTOR] Personality : {e}")

        # ── 6. Fatigue créative ───────────────────────────────────────
        if self.intel:
            try:
                fatigue = self.intel.process_prompt("") if hasattr(self.intel,'process_prompt') else {}
                intent.fatigue_level = fatigue.get("fatigue_level", 0.0) if isinstance(fatigue, dict) else 0.0
                if intent.fatigue_level > 0.7:
                    self.log.warning(f"[DIRECTOR] Fatigue créative élevée ({intent.fatigue_level:.2f}) — disruption activée")
                    intent.creative_risk = min(1.0, intent.creative_risk + 0.3)
            except Exception as e:
                self.log.warning(f"[DIRECTOR] Intelligence : {e}")

        # ── 7. Ajustement selon le mode ───────────────────────────────
        if intent.mode == ProductionMode.FACTORY:
            intent.quality_threshold = max(60, intent.quality_threshold - 10)
            intent.critic_strictness = max(0.7, intent.critic_strictness - 0.2)
            intent.creative_risk     = min(0.3, intent.creative_risk)

        elif intent.mode == ProductionMode.ATELIER:
            intent.quality_threshold = min(90, intent.quality_threshold + 10)
            intent.critic_strictness = min(1.3, intent.critic_strictness + 0.2)
            intent.creative_risk     = max(0.7, intent.creative_risk)

        elif intent.mode == ProductionMode.DREAM:
            intent.quality_threshold = 40   # On laisse tout passer
            intent.critic_strictness = 0.5
            intent.creative_risk     = 1.0

        # ── 8. Publication sur le context_bus ────────────────────────
        self._publish_intent(intent)

        self._intent = intent
        self._save_intent(intent)

        self.log.info(f"[DIRECTOR] ✓ Intention construite — mode={intent.mode.value} | seuil={intent.quality_threshold} | risque={intent.creative_risk:.2f}")
        return intent

    # ── Décisions internes ────────────────────────────────────────────
    def _decide_mode(self) -> ProductionMode:
        """Décide du mode selon l'historique et la conscience."""
        if not self.conscience:
            return ProductionMode.BALANCE

        params = self.conscience.get_params()
        hist   = self.conscience.history[-10:] if hasattr(self.conscience,'history') else []

        if not hist:
            return ProductionMode.BALANCE

        # Si les 5 derniers runs ont tous un score > 85 → passer en ATELIER
        recent_scores = [h.get("score_moyen",0) for h in hist[-5:] if h.get("score_moyen",0) > 0]
        if len(recent_scores) >= 3 and sum(recent_scores)/len(recent_scores) > 85:
            self.log.info("[DIRECTOR] Scores élevés détectés → mode ATELIER")
            return ProductionMode.ATELIER

        # Si > 3 échecs récents → passer en FACTORY pour stabiliser
        recent_health = [h.get("health","") for h in hist[-5:]]
        failures = sum(1 for h in recent_health if h in ["CRITICAL","DEGRADED"])
        if failures >= 3:
            self.log.info("[DIRECTOR] Échecs répétés → mode FACTORY pour stabiliser")
            return ProductionMode.FACTORY

        return ProductionMode.BALANCE

    def _choose_emotion_arc(self, episode: int, hint: str) -> str:
        """Choisit l'arc émotionnel selon l'épisode et les hints."""
        if hint:
            return hint

        # Progression narrative classique shonen
        arcs_by_episode = {
            range(1,4):   "wonder",
            range(4,8):   "tension",
            range(8,12):  "catharsis",
            range(12,16): "triumph",
            range(16,20): "transcendence",
        }
        for ep_range, arc in arcs_by_episode.items():
            if episode in ep_range:
                return arc
        return "tension"

    def _choose_personality_lead(self, mode: ProductionMode) -> str:
        """Choisit quelle personnalité domine ce run."""
        leads = {
            ProductionMode.FACTORY: "mia",     # Enthousiaste, efficace
            ProductionMode.BALANCE: "viktor",   # Perfectionniste, équilibré
            ProductionMode.ATELIER: "elise",    # Critique sévère, qualité
            ProductionMode.DREAM:   "atlas",    # Philosophique, expérimental
        }
        return leads.get(mode, "viktor")

    def _publish_intent(self, intent: RunIntent):
        """Publie l'intention sur le context_bus pour tous les agents."""
        if not self.bus:
            return
        try:
            data = intent.to_dict()
            self.bus.write("director.intent",          data,                      agent_id="director", confidence=1.0)
            self.bus.write("director.mode",            intent.mode.value,          agent_id="director", confidence=1.0)
            self.bus.write("director.emotion_arc",     intent.emotion_arc,         agent_id="director", confidence=0.9)
            self.bus.write("director.emotion_params",  intent.emotion_params,      agent_id="director", confidence=0.9)
            self.bus.write("director.quality_threshold",intent.quality_threshold,  agent_id="director", confidence=1.0)
            self.bus.write("director.critic_strictness",intent.critic_strictness,  agent_id="director", confidence=1.0)
            self.bus.write("director.world_context",   intent.world_context,       agent_id="director", confidence=0.8)
            self.bus.write("director.personality_lead",intent.personality_lead,    agent_id="director", confidence=0.9)
            self.bus.write("director.creative_risk",   intent.creative_risk,       agent_id="director", confidence=0.8)
            self.bus.write("director.universe",        self.series,                agent_id="director", confidence=1.0)
            self.log.info(f"[DIRECTOR] ✓ Intention publiée sur context_bus (10 clés)")
        except Exception as e:
            self.log.warning(f"[DIRECTOR] Publication bus : {e}")

    def _save_intent(self, intent: RunIntent):
        """Sauvegarde l'intention pour l'analyse post-run."""
        ts   = datetime.now().strftime("%Y%m%d_%H%M%S")
        path = DIRECTOR_DIR / f"intent_{ts}.json"
        path.write_text(json.dumps(intent.to_dict(), indent=2, ensure_ascii=False, default=str), encoding="utf-8")
        self._history.append(intent.to_dict())

    # ── Post-run ──────────────────────────────────────────────────────
    def close_run(self, run_result: dict):
        """
        Appelé par maestro.py à la fin du run.
        Publie les résultats sur le bus, met à jour la conscience.
        """
        if self.bus:
            try:
                self.bus.write("director.last_run_result", run_result, agent_id="director")
                self.bus.write("director.last_run_health",
                               run_result.get("pipeline_health",""), agent_id="director")
            except Exception:
                pass

        if self.world:
            try:
                self.world.end_run(run_result)
            except Exception:
                pass

        if self.intel and hasattr(self.intel, 'sync_hivemind'):
            try:
                self.intel.sync_hivemind()
            except Exception:
                pass

        self.log.info(f"[DIRECTOR] Run fermé — health={run_result.get('pipeline_health','?')}")

    # ── Lecture context_bus pour les autres agents ────────────────────
    def get_intent_for_agent(self, agent_id: str) -> dict:
        """
        Interface pour que les agents lisent l'intention du Director.
        storyboard.py, critic.py, scenario.py l'appellent pour se calibrer.
        """
        if self.bus:
            try:
                ctx = self.bus.get_context_for(agent_id)
                return {k.replace("director.",""):v for k,v in ctx.items()
                        if k.startswith("director.")}
            except Exception:
                pass
        return self._intent.to_dict()

    def get_emotion_for_shot(self, shot_index: int, total_shots: int) -> dict:
        """
        Retourne les paramètres émotionnels pour un plan spécifique.
        Appelé par storyboard.py pour enrichir chaque shot.
        """
        if not self.emotion:
            return {}
        try:
            arc       = self._intent.emotion_arc
            position  = shot_index / max(total_shots - 1, 1)
            trajectory= self.emotion.plan_episode_emotions(arc, n_shots=total_shots)
            if shot_index < len(trajectory):
                shot_emotion = trajectory[shot_index]
                em_name = shot_emotion.emotion if hasattr(shot_emotion,'emotion') else arc
                return self.emotion.generate_params(em_name, intensity=0.8)
        except Exception:
            pass
        return self._intent.emotion_params

    def validate_prompt(self, prompt: str, agent_id: str = "") -> dict:
        """
        Valide un prompt via WorldModel et personality.
        Appelé par storyboard.py et scenario.py avant envoi à ComfyUI.
        """
        result = {"prompt": prompt, "fixed": False, "warnings": []}

        # World Model — cohérence narrative
        if self.world:
            try:
                check = self.world.validate_and_fix_prompt(prompt)
                if check.get("fixed"):
                    result["prompt"]   = check.get("fixed_prompt", prompt)
                    result["fixed"]    = True
                    result["warnings"].extend(check.get("violations", []))
            except Exception:
                pass

        # Personality — injection du ton
        if self.personality and agent_id:
            try:
                result["personality_tone"] = self.personality.get_profile(agent_id)
            except Exception:
                pass

        return result

    def status(self) -> dict:
        systems = {
            "context_bus":    BUS_OK,
            "emotion_engine": EMOTION_OK,
            "world_model":    WORLD_OK,
            "personality":    PERSONALITY_OK,
            "intelligence":   INTEL_OK,
            "gen_world":      GENWORLD_OK,
            "conscience":     CONSCIENCE_OK,
        }
        return {
            "series":         self.series,
            "systems_active": sum(systems.values()),
            "systems":        systems,
            "current_mode":   self._intent.mode.value,
            "current_arc":    self._intent.emotion_arc,
            "quality_threshold": self._intent.quality_threshold,
            "critic_strictness": self._intent.critic_strictness,
            "runs_recorded":  len(self._history),
        }

    def print_status(self):
        s = self.status()
        print(f"\n{'═'*55}")
        print(f"  Ov3rLoRd Director V1.48 — {s['series']}")
        print(f"{'─'*55}")
        print(f"  Mode actuel   : {s['current_mode'].upper()}")
        print(f"  Arc émotionnel: {s['current_arc']}")
        print(f"  Seuil qualité : {s['quality_threshold']}")
        print(f"  Systèmes      : {s['systems_active']}/7 actifs")
        for k,v in s['systems'].items():
            print(f"    {'✓' if v else '✗'} {k}")
        print(f"{'═'*55}\n")


# ── Singleton ─────────────────────────────────────────────────────────
_director: Optional[Director] = None

def get_director(series: str = "Ov3rLoRd") -> Director:
    global _director
    if _director is None:
        _director = Director(series)
    return _director


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    d = Director("Dragon Ball Ov3rLoRd")
    intent = d.set_intent(media_type="anime", universe="Dragon Ball", episode=3)
    d.print_status()
    print(f"\nMode         : {intent.mode.value}")
    print(f"Arc émotion  : {intent.emotion_arc}")
    print(f"Seuil qualité: {intent.quality_threshold}")
    print(f"Risque créatif: {intent.creative_risk}")
    print(f"Personnalité : {intent.personality_lead}")
    shot_emotion = d.get_emotion_for_shot(5, 12)
    if shot_emotion:
        print(f"Shot 5/12    : {list(shot_emotion.keys())[:5]}")

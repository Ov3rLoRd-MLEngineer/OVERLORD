"""
agents/v130_emotion_engine.py — OverLord V1.30 — Emotion Engine

La distinction fondamentale entre technicien et artiste :
un technicien dit "génère une image anime de qualité".
un artiste dit "génère quelque chose qui donne envie de pleurer à 35 secondes".

L'Emotion Engine inverse le pipeline :
AVANT : brief → paramètres → image → émotion (aléatoire)
APRÈS : émotion cible → paramètres optimaux → image → émotion (contrôlée)

L'IA ne pense plus en termes de style mais en termes d'impact émotionnel.
Elle choisit ensuite ELLE-MÊME tous les paramètres pour atteindre cet objectif.

Émotions modélisées (roue de Plutchik adaptée à l'animation) :
  Joie / Anticipation / Colère / Dégoût / Tristesse / Peur / Surprise / Confiance
  + états composites : Nostalgie, Émerveillement, Mélancolie douce, Épique, Catharsis...

Composants :
  - EmotionModel      : représentation mathématique d'une émotion cible
  - EmotionTranslator : émotion → paramètres visuels/narratifs/sonores
  - ImpactPredictor   : prédit l'impact émotionnel d'un output avant génération
  - EmotionCalibrator : apprend depuis les feedbacks humains réels
  - EmotionTrajectory : planifie l'arc émotionnel d'un épisode complet
"""

import json
import math
import time
import logging
from pathlib import Path
from dataclasses import dataclass, field
from typing import Optional
import requests

EMOTION_DIR   = Path("workspace/emotion_engine")
ANTHROPIC_URL = "https://api.anthropic.com/v1/messages"
CLAUDE_MODEL  = "claude-sonnet-4-6"


def _llm(prompt: str, system: str = "", max_tokens: int = 500) -> str:
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


# ══════════════════════════════════════════════════════════════════════
# MODÈLE ÉMOTIONNEL — Roue de Plutchik étendue
# ══════════════════════════════════════════════════════════════════════

# Émotions primaires et leurs valences
EMOTION_SPACE = {
    # Primaires
    "joy":          {"valence": +1.0, "arousal": +0.8, "color": "warm_gold"},
    "anticipation": {"valence": +0.6, "arousal": +0.6, "color": "orange"},
    "trust":        {"valence": +0.7, "arousal": +0.2, "color": "blue_soft"},
    "surprise":     {"valence":  0.0, "arousal": +0.9, "color": "electric_blue"},
    "fear":         {"valence": -0.8, "arousal": +0.9, "color": "dark_purple"},
    "disgust":      {"valence": -0.7, "arousal": +0.3, "color": "sickly_green"},
    "anger":        {"valence": -0.6, "arousal": +1.0, "color": "blood_red"},
    "sadness":      {"valence": -0.9, "arousal": -0.6, "color": "cold_blue"},

    # Composites (pour l'animation)
    "nostalgia":    {"valence": +0.3, "arousal": -0.3, "color": "sepia_warm"},
    "awe":          {"valence": +0.8, "arousal": +0.5, "color": "cosmic_purple"},
    "melancholy":   {"valence": -0.4, "arousal": -0.4, "color": "grey_blue"},
    "epic":         {"valence": +0.5, "arousal": +0.9, "color": "dramatic_gold"},
    "catharsis":    {"valence": +0.4, "arousal": +0.2, "color": "warm_tears"},
    "wonder":       {"valence": +0.9, "arousal": +0.4, "color": "luminous_white"},
    "dread":        {"valence": -0.9, "arousal": +0.6, "color": "oppressive_dark"},
    "hope":         {"valence": +0.6, "arousal": +0.3, "color": "dawn_pink"},
    "bittersweet":  {"valence":  0.0, "arousal": -0.2, "color": "autumn_orange"},
    "triumph":      {"valence": +0.9, "arousal": +0.8, "color": "blazing_gold"},
    "despair":      {"valence": -1.0, "arousal": -0.8, "color": "void_black"},
    "tenderness":   {"valence": +0.8, "arousal": -0.5, "color": "soft_pink"},
}


@dataclass
class EmotionTarget:
    """Une émotion cible avec son intensité et ses nuances."""
    primary:    str             # émotion principale
    intensity:  float = 0.8    # 0-1
    secondary:  str   = ""     # émotion secondaire (nuance)
    blend_ratio:float = 0.3    # ratio secondaire (0=pure, 1=moitié-moitié)
    onset_time: float = 0.0    # quand l'émotion doit frapper (0=début, 1=fin)
    target_audience: str = "general"  # général/jeune/adulte/geek

    @property
    def valence(self) -> float:
        p = EMOTION_SPACE.get(self.primary, {}).get("valence", 0)
        if self.secondary:
            s = EMOTION_SPACE.get(self.secondary, {}).get("valence", 0)
            return p * (1-self.blend_ratio) + s * self.blend_ratio
        return p

    @property
    def arousal(self) -> float:
        p = EMOTION_SPACE.get(self.primary, {}).get("arousal", 0)
        if self.secondary:
            s = EMOTION_SPACE.get(self.secondary, {}).get("arousal", 0)
            return p * (1-self.blend_ratio) + s * self.blend_ratio
        return p

    @property
    def dominant_color(self) -> str:
        return EMOTION_SPACE.get(self.primary, {}).get("color", "neutral")


# ══════════════════════════════════════════════════════════════════════
# TRADUCTEUR ÉMOTION → PARAMÈTRES
# ══════════════════════════════════════════════════════════════════════

class EmotionTranslator:
    """
    Traduit une émotion cible en paramètres concrets pour tous les agents.

    Sortie :
    - visual_params   : palette, composition, éclairage
    - prompt_tags     : tags ComfyUI qui induisent cette émotion
    - narrative_tone  : ton pour le scénariste
    - audio_mood      : mood pour la synesthésie
    - sampler_params  : CFG, steps, sampler adaptés
    - camera_style    : angles et mouvements de caméra
    """

    # Mappings émotion → éléments visuels
    VISUAL_MAP = {
        "joy":       {
            "palette":   ["warm yellow", "bright orange", "light blue sky"],
            "lighting":  "bright sunlight, golden hour",
            "composition":"open space, upward angles, wide shots",
            "camera":    "low angle looking up, dynamic movement",
            "tags":      ["cheerful","bright colors","smiling","sunlit","vibrant"],
        },
        "sadness":   {
            "palette":   ["desaturated blue", "grey", "cold tones"],
            "lighting":  "overcast, muted, rain",
            "composition":"isolating framing, downward angles",
            "camera":    "eye level or slightly above, slow movement",
            "tags":      ["melancholic","rain","tears","alone","empty background","blue tones"],
        },
        "fear":      {
            "palette":   ["dark purple", "black", "cold blue"],
            "lighting":  "harsh shadows, single source, darkness",
            "composition":"claustrophobic framing, dutch angle, obscured",
            "camera":    "unstable, close-up on face, looking down",
            "tags":      ["scared expression","dark background","shadows","tense","horror atmosphere"],
        },
        "anger":     {
            "palette":   ["blood red", "orange", "black"],
            "lighting":  "harsh, high contrast, dramatic",
            "composition":"powerful low angle, dynamic action",
            "camera":    "extreme low angle, aggressive framing",
            "tags":      ["intense expression","battle aura","speed lines","fire","power"],
        },
        "awe":       {
            "palette":   ["cosmic purple", "stellar blue", "luminous white"],
            "lighting":  "god rays, volumetric light, epic scale",
            "composition":"extreme wide shot, tiny figure vs massive environment",
            "camera":    "wide establishing, looking up",
            "tags":      ["vast landscape","epic scale","glowing","majestic","awe-inspiring"],
        },
        "nostalgia": {
            "palette":   ["warm sepia", "amber", "faded colors"],
            "lighting":  "golden afternoon, soft lens flare, hazy",
            "composition":"medium shots, familiar settings",
            "camera":    "slow zoom out, bokeh",
            "tags":      ["vintage style","warm tones","memories","childhood","soft focus"],
        },
        "epic":      {
            "palette":   ["dramatic gold", "deep red", "dark blue"],
            "lighting":  "dramatic backlight, rim lighting, storm clouds",
            "composition":"heroic low angle, silhouette, power stance",
            "camera":    "rotating arc shot, extreme low angle",
            "tags":      ["heroic pose","dramatic lighting","epic scale","power","determination"],
        },
        "tenderness":{
            "palette":   ["soft pink", "warm cream", "gentle lavender"],
            "lighting":  "soft diffused, warm, intimate",
            "composition":"close-up, soft framing, two subjects close",
            "camera":    "gentle close-up, shallow depth of field",
            "tags":      ["gentle expression","soft lighting","intimate","warm colors","caring"],
        },
        "catharsis": {
            "palette":   ["gold and tears", "warm", "morning light"],
            "lighting":  "breaking through clouds, tears catching light",
            "composition":"medium close-up, open sky visible",
            "camera":    "slow pull-back, revealing space",
            "tags":      ["crying with smile","release","dawn","cathartic","emotional resolution"],
        },
        "triumph":   {
            "palette":   ["blazing gold", "white", "royal blue"],
            "lighting":  "apex sunlight, dramatic god rays",
            "composition":"extreme low angle, arms raised, crowd",
            "camera":    "low angle rotating, ascending",
            "tags":      ["victory pose","golden light","triumphant","arms raised","crowd"],
        },
    }

    # Paramètres SDXL par arousal
    SAMPLER_BY_AROUSAL = {
        "high":   {"cfg": 7.5, "steps": 28, "sampler": "euler_ancestral", "scheduler": "karras"},
        "medium": {"cfg": 6.5, "steps": 28, "sampler": "dpm++_2m",        "scheduler": "karras"},
        "low":    {"cfg": 5.5, "steps": 24, "sampler": "euler",            "scheduler": "normal"},
    }

    def translate(self, emotion: EmotionTarget) -> dict:
        """Traduit une émotion en paramètres complets."""
        # Trouver le mapping le plus proche
        visual   = self._get_visual_params(emotion.primary, emotion.secondary,
                                            emotion.blend_ratio)
        # Paramètres sampler selon l'arousal
        if emotion.arousal > 0.5:
            sampler_key = "high"
        elif emotion.arousal > 0:
            sampler_key = "medium"
        else:
            sampler_key = "low"
        sampler_p = self.SAMPLER_BY_AROUSAL[sampler_key].copy()
        # Ajuster CFG selon l'intensité
        sampler_p["cfg"] = round(sampler_p["cfg"] * (0.7 + emotion.intensity * 0.6), 1)
        sampler_p["cfg"] = max(3.0, min(12.0, sampler_p["cfg"]))

        # Ton narratif
        narrative_tone = self._get_narrative_tone(emotion)

        # Tags prompt
        prompt_tags = visual.get("tags", []).copy()
        # Ajouter des tags d'intensité
        if emotion.intensity > 0.8:
            prompt_tags.append("highly emotional")
        if emotion.secondary:
            sec_visual = self.VISUAL_MAP.get(emotion.secondary, {})
            prompt_tags.extend(sec_visual.get("tags", [])[:2])

        return {
            "emotion_target":  emotion.primary,
            "emotion_blend":   emotion.secondary,
            "intensity":       emotion.intensity,
            "valence":         round(emotion.valence, 3),
            "arousal":         round(emotion.arousal, 3),
            # Visuel
            "color_palette":   visual.get("palette", ["neutral"]),
            "lighting":        visual.get("lighting", "natural lighting"),
            "composition":     visual.get("composition", "balanced"),
            "camera_style":    visual.get("camera", "medium shot"),
            "dominant_color":  emotion.dominant_color,
            # Prompt
            "prompt_tags":     prompt_tags,
            "prompt_prefix":   f"({', '.join(prompt_tags[:4])})",
            # Technique
            "sampler_params":  sampler_p,
            # Narration
            "narrative_tone":  narrative_tone,
            "audio_mood":      self._get_audio_mood(emotion),
        }

    def _get_visual_params(self, primary: str, secondary: str,
                            blend: float) -> dict:
        """Fusionne les paramètres visuels de deux émotions."""
        p_vis = self.VISUAL_MAP.get(primary, self.VISUAL_MAP.get("joy",{}))
        if not secondary or blend < 0.1:
            return p_vis
        s_vis = self.VISUAL_MAP.get(secondary, {})
        # Mixer les tags
        mixed_tags = p_vis.get("tags",[])[:4-int(blend*2)]
        mixed_tags += s_vis.get("tags",[])[:int(blend*2)]
        return {
            "palette":     p_vis.get("palette",[]),
            "lighting":    p_vis.get("lighting",""),
            "composition": p_vis.get("composition",""),
            "camera":      p_vis.get("camera",""),
            "tags":        mixed_tags,
        }

    def _get_narrative_tone(self, emotion: EmotionTarget) -> str:
        tones = {
            "joy":       "léger, rythmé, dialogues vifs et spontanés",
            "sadness":   "lent, poétique, silences significatifs",
            "fear":      "tendu, phrases courtes, montée crescendo",
            "anger":     "percutant, direct, intensité croissante",
            "awe":       "contemplatif, descriptif, grandiose",
            "nostalgia": "doux, mélancolique, détails sensoriels",
            "epic":      "grandiose, héroïque, rythme en montée",
            "catharsis": "libérateur, résolutif, après la tempête",
            "triumph":   "exalté, court, intense, clairement gagné",
            "tenderness":"intime, doux, sous-texte fort",
        }
        base = tones.get(emotion.primary, "neutre et équilibré")
        if emotion.secondary:
            sec  = tones.get(emotion.secondary, "")
            if sec:
                base += f", avec une nuance de {sec}"
        return base

    def _get_audio_mood(self, emotion: EmotionTarget) -> dict:
        audio_map = {
            "joy":       {"mood":"upbeat","bpm_range":(100,140),"key":"C,G"},
            "sadness":   {"mood":"ambient","bpm_range":(50,70), "key":"Am,Dm"},
            "fear":      {"mood":"tense",  "bpm_range":(80,120),"key":"Bm,Em"},
            "anger":     {"mood":"energetic","bpm_range":(130,180),"key":"Em,Bm"},
            "awe":       {"mood":"epic",   "bpm_range":(60,90), "key":"D,A"},
            "nostalgia": {"mood":"melodic","bpm_range":(60,80), "key":"G,C"},
            "epic":      {"mood":"epic",   "bpm_range":(90,120),"key":"E,B"},
            "catharsis": {"mood":"melodic","bpm_range":(70,90), "key":"F,C"},
            "triumph":   {"mood":"epic",   "bpm_range":(120,150),"key":"D,A"},
            "tenderness":{"mood":"melodic","bpm_range":(50,70), "key":"G,D"},
        }
        return audio_map.get(emotion.primary,
                              {"mood":"neutral","bpm_range":(80,120),"key":"C"})


# ══════════════════════════════════════════════════════════════════════
# PRÉDICTEUR D'IMPACT
# ══════════════════════════════════════════════════════════════════════

class ImpactPredictor:
    """
    Prédit l'impact émotionnel d'un output avant de le générer.
    Évite de générer quelque chose qui manquerait sa cible émotionnelle.
    """

    def __init__(self):
        self._calibration: dict[str, list] = {}  # emotion → [(predicted, actual)]

    def predict(self, prompt: str,
                visual_params: dict,
                target_emotion: EmotionTarget) -> dict:
        """Prédit l'impact émotionnel d'une combinaison prompt+params."""
        tags = [t.strip().lower() for t in prompt.split(",")]
        target_tags = set(target_emotion.primary.lower().split()
                          + visual_params.get("prompt_tags", []))

        # Score de couverture des tags émotionnels
        matches = sum(1 for tag in tags
                      if any(et in tag for et in target_tags))
        coverage = matches / max(len(target_tags), 1)

        # Score de cohérence visuelle
        palette   = visual_params.get("color_palette", [])
        palette_score = min(1.0, len([p for p in palette if p]) / 3)

        # Prédiction globale
        predicted_impact = (coverage * 0.5 + palette_score * 0.3 +
                             target_emotion.intensity * 0.2)
        confidence       = self._get_calibrated_confidence(
            target_emotion.primary, predicted_impact
        )

        return {
            "predicted_impact": round(predicted_impact, 3),
            "confidence":       round(confidence, 3),
            "coverage":         round(coverage, 3),
            "meets_target":     predicted_impact >= target_emotion.intensity * 0.7,
            "emotion_target":   target_emotion.primary,
            "suggestions":      self._suggest_improvements(coverage, tags, target_tags),
        }

    def record_actual(self, emotion: str, predicted: float, actual: float):
        """Enregistre l'impact réel pour calibrer les futures prédictions."""
        if emotion not in self._calibration:
            self._calibration[emotion] = []
        self._calibration[emotion].append((predicted, actual))

    def _get_calibrated_confidence(self, emotion: str, predicted: float) -> float:
        history = self._calibration.get(emotion, [])
        if len(history) < 3:
            return 0.6   # confiance par défaut
        errors = [abs(p-a) for p,a in history[-10:]]
        avg_error = sum(errors) / len(errors)
        return max(0.1, 1.0 - avg_error)

    def _suggest_improvements(self, coverage: float, tags: list,
                               target_tags: set) -> list:
        if coverage >= 0.7:
            return []
        missing = [t for t in list(target_tags)[:5]
                   if not any(t in tag for tag in tags)]
        return [f"Ajouter : {m}" for m in missing[:3]]


# ══════════════════════════════════════════════════════════════════════
# TRAJECTOIRE ÉMOTIONNELLE
# ══════════════════════════════════════════════════════════════════════

class EmotionTrajectory:
    """
    Planifie l'arc émotionnel d'un épisode complet.

    Comme un compositeur qui plan les tensions et résolutions d'une symphonie,
    l'Emotion Engine planifie comment les émotions vont évoluer shot par shot.

    Patterns classiques :
    - Hero's Journey  : wonder → fear → anger → triumph → catharsis
    - Tragedy         : joy → trust → dread → despair
    - Romance         : trust → anticipation → tenderness → joy
    - Action          : anticipation → fear → anger → epic → triumph
    - Drama           : trust → sadness → catharsis → hope
    """

    NARRATIVE_ARCS = {
        "heros_journey": ["wonder","anticipation","fear","anger","epic","triumph","catharsis"],
        "tragedy":       ["joy","trust","anticipation","dread","despair"],
        "romance":       ["trust","anticipation","tenderness","joy","catharsis"],
        "action":        ["anticipation","fear","anger","epic","triumph"],
        "drama":         ["trust","sadness","catharsis","hope"],
        "thriller":      ["anticipation","dread","fear","surprise","triumph"],
        "comedy":        ["anticipation","surprise","joy","awe","joy"],
        "epic_fantasy":  ["wonder","anticipation","epic","fear","anger","triumph","awe"],
        "slice_of_life": ["tenderness","joy","nostalgia","bittersweet","hope"],
        "horror":        ["trust","anticipation","dread","fear","despair","surprise"],
    }

    def get_arc(self, arc_type: str) -> list[str]:
        return self.NARRATIVE_ARCS.get(arc_type, self.NARRATIVE_ARCS["heros_journey"])

    def plan_episode(self, arc_type: str, n_shots: int) -> list[EmotionTarget]:
        """
        Génère la trajectoire émotionnelle d'un épisode complet.
        Distribue les émotions de l'arc sur N shots.
        """
        arc    = self.get_arc(arc_type)
        targets = []

        for i in range(n_shots):
            # Position dans l'arc
            arc_pos  = (i / (n_shots - 1)) if n_shots > 1 else 0.5
            arc_idx  = int(arc_pos * (len(arc) - 1))
            arc_idx2 = min(arc_idx + 1, len(arc) - 1)

            # Interpoler entre deux émotions de l'arc
            emotion1 = arc[arc_idx]
            emotion2 = arc[arc_idx2]
            blend    = (arc_pos * (len(arc)-1)) - arc_idx

            # Intensité : monte vers le climax (shot du milieu), redescend
            peak   = 0.6   # le climax est à 60% de l'épisode
            dist   = abs(arc_pos - peak)
            intensity = max(0.4, 1.0 - dist * 1.5)

            targets.append(EmotionTarget(
                primary     = emotion1,
                secondary   = emotion2 if blend > 0.3 else "",
                blend_ratio = blend if blend > 0.3 else 0,
                intensity   = round(intensity, 2),
                onset_time  = arc_pos,
            ))
        return targets

    def get_arc_summary(self, arc_type: str) -> str:
        arc = self.get_arc(arc_type)
        return f"{arc_type}: " + " → ".join(arc)


# ══════════════════════════════════════════════════════════════════════
# EMOTION ENGINE — FAÇADE
# ══════════════════════════════════════════════════════════════════════

class EmotionEngine:
    """
    L'Emotion Engine complet — point d'entrée pour la génération émotionnelle.
    """

    def __init__(self, logger: logging.Logger = None):
        self.log        = logger or logging.getLogger("emotion_engine")
        self.translator = EmotionTranslator()
        self.predictor  = ImpactPredictor()
        self.trajectory = EmotionTrajectory()
        self._history:  list[dict] = []
        EMOTION_DIR.mkdir(parents=True, exist_ok=True)

    def target(self, emotion: str, intensity: float = 0.8,
               secondary: str = "", blend: float = 0.2) -> EmotionTarget:
        """Crée une cible émotionnelle."""
        if emotion not in EMOTION_SPACE:
            # Trouver la plus proche
            emotion = min(EMOTION_SPACE.keys(),
                          key=lambda e: sum(c!=d for c,d in zip(e,emotion)) if len(e)==len(emotion) else 99)
        return EmotionTarget(primary=emotion, intensity=intensity,
                              secondary=secondary, blend_ratio=blend)

    def generate_params(self, emotion: str, intensity: float = 0.8,
                         secondary: str = "") -> dict:
        """
        Génère tous les paramètres pour atteindre une émotion cible.
        C'est la méthode principale de l'Emotion Engine.
        """
        et     = self.target(emotion, intensity, secondary)
        params = self.translator.translate(et)

        # Prédire l'impact
        mock_prompt = ", ".join(params["prompt_tags"])
        prediction  = self.predictor.predict(mock_prompt, params, et)
        params["predicted_impact"] = prediction

        self._history.append({
            "emotion":   emotion,
            "intensity": intensity,
            "params":    params,
            "ts":        time.time(),
        })
        self.log.info(
            f"[EMOTION] Target='{emotion}' I={intensity:.1f} | "
            f"valence={params['valence']:+.2f} arousal={params['arousal']:+.2f} | "
            f"predicted_impact={prediction['predicted_impact']:.2f}"
        )
        return params

    def plan_episode_emotions(self, arc_type: str = "heros_journey",
                               n_shots: int = 12) -> list[dict]:
        """
        Planifie l'arc émotionnel complet d'un épisode.
        Retourne les paramètres pour chaque shot.
        """
        targets = self.trajectory.plan_episode(arc_type, n_shots)
        episode_params = []

        for i, et in enumerate(targets):
            params = self.translator.translate(et)
            episode_params.append({
                "shot":      i + 1,
                "emotion":   et.primary,
                "intensity": et.intensity,
                "onset":     et.onset_time,
                **params,
            })

        self.log.info(
            f"[EMOTION] Arc '{arc_type}' planifié : {n_shots} shots | "
            f"Émotions : {[p['emotion'] for p in episode_params]}"
        )
        return episode_params

    def from_human_description(self, description: str) -> dict:
        """
        Extrait une cible émotionnelle depuis une description humaine.
        Ex: "je veux quelque chose qui donne des frissons dans le dos"
            → {"emotion":"awe","intensity":0.9,"secondary":"fear"}
        """
        emotions_list = ", ".join(EMOTION_SPACE.keys())
        prompt = (
            f"Description de l'effet voulu : '{description}'\n\n"
            f"Émotions disponibles : {emotions_list}\n\n"
            f"Identifie l'émotion principale et secondaire voulue.\n"
            f"Réponds en JSON : {{\"primary\": \"...\", \"secondary\": \"...ou null\", "
            f"\"intensity\": 0.85, \"reasoning\": \"1 phrase\"}}"
        )
        result = _llm(prompt, max_tokens=200)
        try:
            if result.startswith("```"):
                result = "\n".join(result.split("\n")[1:-1])
            data = json.loads(result)
            return self.generate_params(
                emotion   = data.get("primary", "awe"),
                intensity = data.get("intensity", 0.8),
                secondary = data.get("secondary", "") or "",
            )
        except Exception:
            return self.generate_params("awe", 0.8)

    def record_feedback(self, emotion: str, predicted: float, actual: float):
        """Enregistre le feedback humain pour calibrer les futures prédictions."""
        self.predictor.record_actual(emotion, predicted, actual)

    def get_available_emotions(self) -> dict:
        """Liste toutes les émotions disponibles avec leurs caractéristiques."""
        return {
            name: {
                "valence": round(data["valence"], 2),
                "arousal": round(data["arousal"], 2),
                "color":   data["color"],
                "has_visual_map": name in self.translator.VISUAL_MAP,
            }
            for name, data in EMOTION_SPACE.items()
        }

    def get_dashboard(self) -> dict:
        return {
            "version":           "1.30_emotion",
            "emotions_available":len(EMOTION_SPACE),
            "arcs_available":    list(self.trajectory.NARRATIVE_ARCS.keys()),
            "history_count":     len(self._history),
            "last_emotion":      self._history[-1]["emotion"] if self._history else None,
        }


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    engine = EmotionEngine()

    print("=== V1.30 EMOTION ENGINE TEST ===\n")

    print("Émotions disponibles :")
    for name, data in list(engine.get_available_emotions().items())[:8]:
        v = data["valence"]; a = data["arousal"]
        print(f"  {name:<15} valence={v:+.2f} arousal={a:+.2f} | {data['color']}")

    print("\n--- Test génération épique ---")
    params = engine.generate_params("epic", intensity=0.9, secondary="awe")
    print(f"Palette       : {params['color_palette']}")
    print(f"Éclairage     : {params['lighting']}")
    print(f"Tags prompt   : {params['prompt_tags'][:5]}")
    print(f"CFG/Steps     : {params['sampler_params']['cfg']}/{params['sampler_params']['steps']}")
    print(f"Ton narratif  : {params['narrative_tone']}")
    print(f"Impact prédit : {params['predicted_impact']['predicted_impact']:.2f}")

    print("\n--- Depuis description humaine ---")
    human_params = engine.from_human_description(
        "je veux quelque chose qui donne des frissons et de l'espoir à la fois"
    )
    print(f"Émotion déduite : {human_params['emotion_target']}")
    print(f"Blend           : {human_params['emotion_blend']}")

    print("\n--- Plan épisode Hero's Journey (6 shots) ---")
    episode = engine.plan_episode_emotions("heros_journey", n_shots=6)
    for shot in episode:
        print(f"  Shot {shot['shot']}: {shot['emotion']:<15} I={shot['intensity']:.2f} | {shot['narrative_tone'][:50]}")

    print(f"\n{engine.get_dashboard()}")

"""
agents/emotion_engine.py -- Moteur d'emotions Ov3rLoRd V1.30
Mappe les arcs narratifs vers des parametres ComfyUI.
FIX V1.49  : SyntaxError 'break outside loop' corrige.
FIX V1.49p : plan_episode_emotions() et generate_params() ajoutes
             (requis par director.py).
"""
import logging
import math
from pathlib import Path
from dataclasses import dataclass

log = logging.getLogger("emotion_engine")


def _get_api_key() -> str:
    import os as _os
    key = _os.environ.get("ANTHROPIC_API_KEY", "")
    if not key:
        for env_path in [Path(__file__).parent.parent / ".env", Path(".env")]:
            if env_path.exists():
                for line in env_path.read_text(encoding="utf-8").splitlines():
                    if line.startswith("ANTHROPIC_API_KEY="):
                        key = line.split("=", 1)[1].strip().strip('"').strip("'")
                        break
            if key:
                break
    return key


EMOTION_TABLE = {
    "tension":     {"cfg": 8.5, "steps": 35, "sampler": "dpm++2m", "denoise": 0.85},
    "catharsis":   {"cfg": 7.0, "steps": 30, "sampler": "euler_a",  "denoise": 0.75},
    "wonder":      {"cfg": 6.5, "steps": 28, "sampler": "euler_a",  "denoise": 0.70},
    "melancholy":  {"cfg": 7.5, "steps": 32, "sampler": "dpm++2m",  "denoise": 0.80},
    "joy":         {"cfg": 6.0, "steps": 25, "sampler": "euler_a",  "denoise": 0.65},
    "dread":       {"cfg": 9.0, "steps": 40, "sampler": "dpm++2m",  "denoise": 0.90},
    "triumph":     {"cfg": 8.0, "steps": 32, "sampler": "euler_a",  "denoise": 0.82},
    "transcendence":{"cfg":7.5, "steps": 35, "sampler": "dpm++2m",  "denoise": 0.85},
    "neutral":     {"cfg": 7.0, "steps": 28, "sampler": "euler_a",  "denoise": 0.75},
}

PALETTE_TABLE = {
    "tension":      ["#1a0a0a", "#8b0000", "#ff4500"],
    "catharsis":    ["#0d1b2a", "#1b4f72", "#85c1e9"],
    "wonder":       ["#0a0a1a", "#6a0dad", "#e040fb"],
    "melancholy":   ["#1c1c1c", "#4a4a6a", "#9090b0"],
    "joy":          ["#fff9c4", "#ffcc02", "#ff8f00"],
    "dread":        ["#000000", "#1a1a2e", "#16213e"],
    "triumph":      ["#ffd700", "#ff6b00", "#ffffff"],
    "transcendence":["#e8f5e9", "#80cbc4", "#b39ddb"],
    "neutral":      ["#2c2c2c", "#555555", "#aaaaaa"],
}

# Tags ComfyUI par emotion
COMFYUI_TAGS = {
    "tension":      "dramatic lighting, intense atmosphere, high contrast shadows",
    "catharsis":    "soft blue tones, tears of joy, emotional release, gentle light",
    "wonder":       "magical atmosphere, glowing particles, awe-inspiring vista",
    "melancholy":   "desaturated colors, rain, lonely composition, muted tones",
    "joy":          "bright warm colors, dynamic pose, laughing, sunshine",
    "dread":        "dark atmosphere, horror lighting, deep shadows, ominous",
    "triumph":      "golden hour, victory pose, dynamic action, radiant energy",
    "transcendence":"ethereal light, particle effects, spiritual atmosphere",
    "neutral":      "balanced lighting, natural colors",
}


@dataclass
class ShotEmotion:
    """Emotion d'un shot specifique dans l'episode."""
    shot_index: int
    emotion:    str
    intensity:  float
    params:     dict


class EmotionEngine:
    def __init__(self):
        self.current_emotion = "neutral"
        log.info("[EMOTION] Moteur d'emotions initialise.")

    def set_emotion(self, emotion: str):
        if emotion not in EMOTION_TABLE:
            emotion = "neutral"
        self.current_emotion = emotion
        log.info(f"[EMOTION] Arc emotionnel -> {emotion}")

    def get_comfy_params(self, emotion: str = None) -> dict:
        e = emotion or self.current_emotion
        params = EMOTION_TABLE.get(e, EMOTION_TABLE["neutral"]).copy()
        params["palette"] = PALETTE_TABLE.get(e, PALETTE_TABLE["neutral"])
        params["emotion"] = e
        return params

    def generate_params(self, emotion: str, intensity: float = 0.8) -> dict:
        """
        Genere les parametres ComfyUI pour une emotion avec intensite.
        Requis par director.py (get_emotion_for_shot, set_intent).
        """
        base = EMOTION_TABLE.get(emotion, EMOTION_TABLE["neutral"]).copy()
        # Intensite : ajuste cfg et steps
        base["cfg"]   = round(base["cfg"]   * (0.8 + intensity * 0.4), 1)
        base["cfg"]   = max(4.0, min(12.0, base["cfg"]))
        base["steps"] = int(base["steps"]   * (0.8 + intensity * 0.4))
        base["steps"] = max(15, min(50, base["steps"]))
        base["palette"]      = PALETTE_TABLE.get(emotion, PALETTE_TABLE["neutral"])
        base["comfyui_tags"] = COMFYUI_TAGS.get(emotion, "")
        base["emotion"]      = emotion
        base["intensity"]    = intensity
        return base

    def plan_episode_emotions(self, arc: str, n_shots: int = 12) -> list[ShotEmotion]:
        """
        Planifie l'arc emotionnel d'un episode en N shots.
        Requis par director.py (set_intent, get_emotion_for_shot).

        arc : "wonder" | "tension" | "catharsis" | "triumph" | "transcendence"
              ou arc compose "tension_to_catharsis"
        """
        # Decomposer les arcs composes
        arc_sequences = {
            "tension_to_catharsis":    ["tension","dread","catharsis"],
            "wonder_to_triumph":       ["wonder","tension","triumph"],
            "melancholy_to_joy":       ["melancholy","tension","joy"],
            "dread_to_transcendence":  ["dread","tension","transcendence"],
        }

        sequence = arc_sequences.get(arc)
        if not sequence:
            # Arc simple : emotion principale + montee puis redescente
            sequence = ["neutral", arc, arc, "neutral"]

        shots = []
        for i in range(n_shots):
            # Position dans la sequence 0.0 -> 1.0
            pos     = i / max(n_shots - 1, 1)
            # Indice dans la sequence d'emotions
            seq_idx = min(int(pos * len(sequence)), len(sequence)-1)
            emotion = sequence[seq_idx]
            # Intensite : monte puis redescend (courbe en cloche)
            intensity = math.sin(pos * math.pi) * 0.5 + 0.5

            shots.append(ShotEmotion(
                shot_index = i,
                emotion    = emotion,
                intensity  = round(intensity, 3),
                params     = self.generate_params(emotion, intensity),
            ))
        return shots

    def enrich_shot(self, shot: dict, emotion: str = None) -> dict:
        params = self.get_comfy_params(emotion or self.current_emotion)
        shot.update({
            "cfg_scale":   params["cfg"],
            "steps":       params["steps"],
            "sampler":     params["sampler"],
            "denoise":     params["denoise"],
            "palette":     params["palette"],
            "emotion_tag": params["emotion"],
        })
        return shot

    def get_emotion_arc(self, episode: int, total_episodes: int = 12) -> str:
        ratio = episode / max(total_episodes, 1)
        if ratio < 0.2:   return "wonder"
        if ratio < 0.4:   return "tension"
        if ratio < 0.6:   return "dread"
        if ratio < 0.75:  return "catharsis"
        if ratio < 0.9:   return "melancholy"
        return "triumph"


_engine_instance = None

def get_emotion_engine() -> EmotionEngine:
    global _engine_instance
    if _engine_instance is None:
        _engine_instance = EmotionEngine()
    return _engine_instance


if __name__ == "__main__":
    import sys, io
    if hasattr(sys.stdout,'buffer'):
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    logging.basicConfig(level=logging.INFO)
    eng = get_emotion_engine()
    print("=== Emotion Engine V1.49p ===")
    for em in ["tension","catharsis","wonder"]:
        p = eng.get_comfy_params(em)
        print(f"  {em:14} cfg={p['cfg']} steps={p['steps']}")
    shots = eng.plan_episode_emotions("tension_to_catharsis", n_shots=6)
    print(f"\nArc 'tension_to_catharsis' sur 6 shots :")
    for s in shots:
        print(f"  Shot {s.shot_index} : {s.emotion:14} intensity={s.intensity:.2f}")
    print("EmotionEngine OK")
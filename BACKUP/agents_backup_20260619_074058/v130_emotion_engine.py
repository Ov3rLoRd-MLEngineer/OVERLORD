"""
v130_emotion_engine.py — Moteur d'émotions Ov3rLoRd V1.30
Mappe les arcs narratifs vers des paramètres ComfyUI.
FIX V1.49 : SyntaxError 'break outside loop' ligne 55 corrigé.
"""
import logging
import os
from pathlib import Path

log = logging.getLogger("emotion_engine")

# ── Lecture clé API (pattern standard Ov3rLoRd) ──────────────────────────────
def _get_api_key() -> str:
    import os as _os
    key = _os.environ.get("ANTHROPIC_API_KEY", "")
    if not key:
        for env_path in [Path(__file__).parent.parent / ".env", Path(".env")]:
            if env_path.exists():
                for line in env_path.read_text(encoding="utf-8").splitlines():
                    if line.startswith("ANTHROPIC_API_KEY="):
                        key = line.split("=", 1)[1].strip().strip('"').strip("'")
                        break  # <- dans la boucle for -> syntaxe valide
            if key:
                break  # <- dans la boucle for externe -> valide
    return key

# ── Table des émotions → paramètres ComfyUI ──────────────────────────────────
EMOTION_TABLE = {
    "tension":    {"cfg": 8.5, "steps": 35, "sampler": "dpm++2m", "denoise": 0.85},
    "catharsis":  {"cfg": 7.0, "steps": 30, "sampler": "euler_a",  "denoise": 0.75},
    "wonder":     {"cfg": 6.5, "steps": 28, "sampler": "euler_a",  "denoise": 0.70},
    "melancholy": {"cfg": 7.5, "steps": 32, "sampler": "dpm++2m", "denoise": 0.80},
    "joy":        {"cfg": 6.0, "steps": 25, "sampler": "euler_a",  "denoise": 0.65},
    "dread":      {"cfg": 9.0, "steps": 40, "sampler": "dpm++2m", "denoise": 0.90},
    "neutral":    {"cfg": 7.0, "steps": 28, "sampler": "euler_a",  "denoise": 0.75},
}

PALETTE_TABLE = {
    "tension":    ["#1a0a0a", "#8b0000", "#ff4500"],
    "catharsis":  ["#0d1b2a", "#1b4f72", "#85c1e9"],
    "wonder":     ["#0a0a1a", "#6a0dad", "#e040fb"],
    "melancholy": ["#1c1c1c", "#4a4a6a", "#9090b0"],
    "joy":        ["#fff9c4", "#ffcc02", "#ff8f00"],
    "dread":      ["#000000", "#1a1a2e", "#16213e"],
    "neutral":    ["#2c2c2c", "#555555", "#aaaaaa"],
}

class EmotionEngine:
    def __init__(self):
        self.current_emotion = "neutral"
        log.info("[EMOTION] Moteur d'émotions initialisé.")

    def set_emotion(self, emotion: str):
        if emotion not in EMOTION_TABLE:
            log.warning(f"[EMOTION] Émotion inconnue '{emotion}', fallback neutral.")
            emotion = "neutral"
        self.current_emotion = emotion
        log.info(f"[EMOTION] Arc émotionnel -> {emotion}")

    def get_comfy_params(self, emotion: str = None) -> dict:
        e = emotion or self.current_emotion
        params = EMOTION_TABLE.get(e, EMOTION_TABLE["neutral"]).copy()
        params["palette"] = PALETTE_TABLE.get(e, PALETTE_TABLE["neutral"])
        params["emotion"] = e
        return params

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
        return "joy"


_engine_instance = None

def get_emotion_engine() -> EmotionEngine:
    global _engine_instance
    if _engine_instance is None:
        _engine_instance = EmotionEngine()
    return _engine_instance


if __name__ == "__main__":
    import sys, io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    logging.basicConfig(level=logging.INFO)
    eng = get_emotion_engine()
    for em in ["tension", "catharsis", "wonder"]:
        p = eng.get_comfy_params(em)
        print(f"  {em:12} -> cfg={p['cfg']} steps={p['steps']} sampler={p['sampler']}")
    print("EmotionEngine OK")
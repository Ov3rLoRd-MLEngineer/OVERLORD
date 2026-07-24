# ██████╗ ██╗   ██╗██████╗ ██████╗ ██╗      ██████╗ ██████╗ ██████╗
# ██╔═══██╗██║   ██║╚════██╗██╔══██╗██║     ██╔═══██╗██╔══██╗██╔══██╗
# ██║   ██║██║   ██║ █████╔╝██████╔╝██║     ██║   ██║██████╔╝██║  ██║
# ██║   ██║╚██╗ ██╔╝ ╚═══██╗██╔══██╗██║     ██║   ██║██╔══██╗██║  ██║
# ╚██████╔╝ ╚████╔╝ ██████╔╝██║  ██║███████╗╚██████╔╝██║  ██║██████╔╝
# ╚═════╝   ╚═══╝  ╚═════╝ ╚═╝  ╚═╝╚══════╝ ╚═════╝ ╚═╝  ╚═╝╚═════╝
# Ov3rLoRd -- pipeline de production anime autonome (ComfyUI)
# https://github.com/Ov3rLoRd-MLEngineer
#
"""
agents/prompt_optimizer.py — Optimiseur de Prompts ComfyUI V1.47
Améliore les prompts via feedback loop : génère → évalue → affine → regénère.
Apprend des meilleurs résultats et construit une base de connaissances.

Usage :
    from agents.prompt_optimizer import PromptOptimizer
    opt = PromptOptimizer()
    best_prompt = opt.optimize("Goku fights Broly", style="anime SDXL", iterations=3)
"""

import json
import logging
import hashlib
from pathlib import Path
from datetime import datetime
from typing import Optional

try:
    from agents.overlord_utils import fallback_llm, safe_json_parse
    UTILS_OK = True
except ImportError:
    UTILS_OK = False

try:
    from agents.cost_tracker import get_tracker
    TRACK_OK = True
except ImportError:
    TRACK_OK = False

log = logging.getLogger("prompt_optimizer")
OPT_DIR   = Path("workspace/prompt_optimizer")
KB_FILE   = OPT_DIR / "knowledge_base.json"   # Base de connaissances prompts

# Modificateurs positifs connus pour l'anime SDXL
QUALITY_BOOSTERS = [
    "masterpiece", "best quality", "ultra detailed", "sharp focus",
    "8k", "anime style", "cel shading", "vibrant colors",
    "dynamic composition", "dramatic lighting", "volumetric light",
]

NEGATIVE_BASE = (
    "bad quality, blurry, deformed, ugly, duplicate, error, "
    "watermark, signature, text, jpeg artifacts, low resolution, "
    "extra limbs, missing limbs, bad anatomy, proportions error"
)

SDXL_STYLE_SUFFIXES = {
    "anime":     ", anime style, cel shading, vibrant, Toriyama style",
    "manga":     ", manga style, ink drawing, black and white, hatching",
    "3d":        ", 3D render, Blender, octane render, subsurface scattering",
    "photoreal": ", photorealistic, hyperrealism, studio lighting, 8k",
    "art":       ", digital art, artstation, concept art, detailed illustration",
}


class PromptKnowledgeBase:
    """Base de connaissances des prompts qui ont bien fonctionné."""

    def __init__(self):
        OPT_DIR.mkdir(parents=True, exist_ok=True)
        self._db = self._load()

    def _load(self) -> dict:
        if KB_FILE.exists():
            try:
                return json.loads(KB_FILE.read_text(encoding="utf-8"))
            except Exception:
                pass
        return {"prompts": {}, "patterns": {}, "stats": {}}

    def _save(self):
        KB_FILE.write_text(json.dumps(self._db, indent=2, ensure_ascii=False), encoding="utf-8")

    def record(self, original: str, optimized: str, score: float,
               style: str = "anime", metadata: dict = None):
        key = hashlib.md5(original.encode()).hexdigest()[:8]
        self._db["prompts"][key] = {
            "original":  original[:200],
            "optimized": optimized[:500],
            "score":     score,
            "style":     style,
            "metadata":  metadata or {},
            "recorded":  datetime.now().isoformat(),
        }
        # Extraire les patterns gagnants
        words = optimized.lower().split(",")
        for w in words:
            w = w.strip()
            if len(w) > 3:
                if w not in self._db["patterns"]:
                    self._db["patterns"][w] = {"count": 0, "avg_score": 0.0}
                p = self._db["patterns"][w]
                n = p["count"]
                p["avg_score"] = (p["avg_score"] * n + score) / (n + 1)
                p["count"] += 1
        self._save()

    def get_top_patterns(self, style: str = "anime", n: int = 10) -> list:
        """Retourne les N meilleurs modificateurs basés sur l'historique."""
        patterns = sorted(
            self._db["patterns"].items(),
            key=lambda x: x[1]["avg_score"] * min(x[1]["count"], 10),
            reverse=True
        )
        return [p[0] for p in patterns[:n]]

    def find_similar(self, prompt: str) -> Optional[dict]:
        """Trouve un prompt similaire dans la base."""
        prompt_words = set(prompt.lower().split())
        best_match   = None
        best_overlap = 0
        for key, data in self._db["prompts"].items():
            orig_words = set(data["original"].lower().split())
            overlap    = len(prompt_words & orig_words) / max(len(prompt_words), 1)
            if overlap > best_overlap and overlap > 0.4:
                best_overlap = overlap
                best_match   = data
        return best_match


class PromptOptimizer:
    """Optimise les prompts via un cycle génère→évalue→affine."""

    def __init__(self, logger: logging.Logger = None):
        self.log = logger or log
        self.kb  = PromptKnowledgeBase()

    def expand(self, base_prompt: str, style: str = "anime",
               characters: list = None) -> str:
        """
        Expansion rapide sans LLM — ajoute les modificateurs de base.
        Utile comme première passe avant l'optimisation LLM.
        """
        parts = [base_prompt.strip()]

        # Suffix de style
        if style in SDXL_STYLE_SUFFIXES:
            parts.append(SDXL_STYLE_SUFFIXES[style].strip(", "))

        # Patterns appris
        top_patterns = self.kb.get_top_patterns(style, n=5)
        if top_patterns:
            parts.extend(top_patterns[:3])
        else:
            parts.extend(QUALITY_BOOSTERS[:3])

        # Personnages si spécifiés
        if characters:
            parts.insert(1, f"featuring {', '.join(characters)}")

        return ", ".join(p for p in parts if p.strip())

    def optimize(self, base_prompt: str, style: str = "anime",
                 iterations: int = 3, characters: list = None,
                 score_threshold: float = 80.0) -> dict:
        """
        Optimise un prompt en N itérations via LLM.
        Chaque itération analyse et améliore le prompt précédent.
        """
        self.log.info(f"[OPTIMIZER] Optimisation : '{base_prompt[:50]}' ({iterations} itérations)")

        # Vérifier la base de connaissances
        similar = self.kb.find_similar(base_prompt)
        if similar and similar["score"] >= score_threshold:
            self.log.info(f"[OPTIMIZER] Prompt similaire trouvé en KB (score={similar['score']})")
            return {"prompt": similar["optimized"], "score": similar["score"],
                    "source": "knowledge_base", "iterations": 0}

        # Expansion initiale
        current = self.expand(base_prompt, style, characters)
        best    = current
        best_score = 0.0
        history = []

        for i in range(1, iterations + 1):
            self.log.info(f"[OPTIMIZER] Itération {i}/{iterations}")

            if not UTILS_OK:
                score = self._heuristic_score(current)
                history.append({"iteration": i, "prompt": current, "score": score})
                if score > best_score:
                    best_score = score
                    best = current
                break

            # Évaluation + amélioration via LLM
            eval_prompt = f"""Tu es expert en prompts Stable Diffusion XL pour l'animation {style}.

Prompt actuel : {current[:300]}

Évalue et améliore ce prompt. Critères : clarté visuelle, spécificité, qualité SDXL.

Réponds UNIQUEMENT avec ce JSON :
{{
  "score": 0-100,
  "weaknesses": ["point faible 1"],
  "improved_prompt": "prompt amélioré complet",
  "improvements_made": ["amélioration 1"]
}}"""

            raw = fallback_llm(eval_prompt, max_tokens=400, logger=self.log)
            ok, data, _ = safe_json_parse(raw, logger=self.log)

            if ok and data:
                score    = float(data.get("score", 70))
                improved = data.get("improved_prompt", current)
                history.append({
                    "iteration":      i,
                    "prompt":         current,
                    "score":          score,
                    "improved_prompt":improved,
                    "improvements":   data.get("improvements_made", []),
                })
                if score > best_score:
                    best_score = score
                    best = improved
                if score >= score_threshold:
                    self.log.info(f"[OPTIMIZER] ✓ Seuil atteint ({score:.0f}) à l'itération {i}")
                    break
                current = improved
            else:
                score = self._heuristic_score(current)
                history.append({"iteration": i, "prompt": current, "score": score})
                if score > best_score:
                    best_score = score

        # Enregistrer dans la base de connaissances
        self.kb.record(base_prompt, best, best_score, style)

        result = {
            "original":     base_prompt,
            "prompt":        best,
            "negative":      NEGATIVE_BASE,
            "score":         best_score,
            "iterations":    len(history),
            "history":       history,
            "style":         style,
        }
        self.log.info(f"[OPTIMIZER] ✓ Score final : {best_score:.0f}/100")
        return result

    def _heuristic_score(self, prompt: str) -> float:
        """Score heuristique sans LLM."""
        score = 50.0
        words = prompt.lower()
        for booster in QUALITY_BOOSTERS:
            if booster in words:
                score += 3
        if len(prompt) > 100:
            score += 5
        if len(prompt) > 200:
            score += 5
        if "," in prompt:
            score += 5
        return min(95.0, score)

    def batch_optimize(self, shots: list, style: str = "anime") -> list:
        """Optimise tous les prompts d'une shotlist en batch."""
        optimized = []
        for i, shot in enumerate(shots):
            self.log.info(f"[OPTIMIZER] Shot {i+1}/{len(shots)} : {shot.get('shot_id','')}")
            positive = shot.get("comfyui_positive", "")
            chars    = shot.get("characters", [])
            if positive:
                result = self.optimize(positive, style=style,
                                       characters=chars, iterations=2)
                shot = {**shot,
                        "comfyui_positive": result["prompt"],
                        "comfyui_negative": result.get("negative", NEGATIVE_BASE),
                        "_prompt_score":    result["score"]}
            optimized.append(shot)
        return optimized


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    opt = PromptOptimizer()
    result = opt.optimize(
        "Goku fights Broly in a desert",
        style="anime",
        characters=["Goku","Broly"],
        iterations=2
    )
    print(f"\nPrompt original : {result['original']}")
    print(f"Prompt optimisé : {result['prompt']}")
    print(f"Score : {result['score']:.0f}/100")
    print(f"Itérations : {result['iterations']}")

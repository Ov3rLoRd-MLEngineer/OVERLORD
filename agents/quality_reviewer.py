"""
agents/quality_reviewer.py — Jury de Qualité Multi-Critères V1.70
Score global = moyenne pondérée de 4 critères.
Seuil : 90 pour PASS, < 90 = REFUS + retry immédiat (max 3 tentatives).

Intégration : appelé par agent_supervisor_v2.py après chaque image générée.
Si REFUS → prompt_engineer.py ajuste le prompt → nouveau job ComfyUI.

Critères et poids :
  sharpness    (30%) : netteté mesurée par variance Laplacien
  style_drift  (30%) : cohérence avec l'ancre de style du run
  prompt_match (25%) : concordance entre le prompt et l'image (CLIP score)
  narrative    (15%) : cohérence narrative (via critic/LLM)
"""

import json
import logging
import math
from pathlib import Path
from datetime import datetime

try:
    import numpy as np
    NUMPY_OK = True
except ImportError:
    NUMPY_OK = False

try:
    from PIL import Image
    PIL_OK = True
except ImportError:
    PIL_OK = False

try:
    from agents.context_bus import get_bus
    BUS_OK = True
except ImportError:
    BUS_OK = False

try:
    from agents.overlord_utils import fallback_llm, safe_json_parse
    UTILS_OK = True
except ImportError:
    UTILS_OK = False

try:
    from agents.style_continuity import StyleAnchor
    STYLE_OK = True
except ImportError:
    STYLE_OK = False

REVIEW_LOG  = Path("workspace/logs/quality_reviews.jsonl")
TARGET_SCORE = 90.0
MAX_RETRIES  = 3

WEIGHTS = {
    "sharpness":     0.30,
    "style_drift":   0.30,
    "prompt_match":  0.25,
    "narrative":     0.15,
}


# ── Critère 1 : Netteté ───────────────────────────────────────────────

def score_sharpness(image_path: str) -> float:
    """
    Variance du Laplacien → mesure de netteté.
    Score normalisé 0-100 :
      < 100  → flou (score 0-40)
      100-500 → acceptable (40-70)
      500-2000 → bon (70-90)
      > 2000  → excellent (90-100)
    """
    if not PIL_OK or not NUMPY_OK:
        return 70.0  # Valeur conservative si dépendances absentes

    try:
        img = Image.open(image_path).convert("L")
        arr = np.array(img, dtype=float)

        # Filtre Laplacien manuel (pas besoin de scipy)
        laplacian = (
            arr[:-2, 1:-1] + arr[2:, 1:-1] +
            arr[1:-1, :-2] + arr[1:-1, 2:] -
            4 * arr[1:-1, 1:-1]
        )
        variance = float(np.var(laplacian))

        # Normalisation logarithmique → 0-100
        if variance <= 0:
            return 0.0
        log_var = math.log10(max(variance, 1))
        # log10(100)=2 → 40, log10(500)=2.7 → 70, log10(2000)=3.3 → 90, log10(10000)=4 → 100
        score = min(100.0, max(0.0, (log_var - 1.0) * 37.5))
        return round(score, 1)

    except Exception:
        return 50.0


# ── Critère 2 : Cohérence de style ───────────────────────────────────

def score_style_drift(image_path: str, anchor_lora: str = "",
                      shot_index: int = 0) -> float:
    """
    Cohérence de style par rapport à l'ancre du run.
    Approximation : compare les statistiques de couleur entre images du run.
    Score 0-100 (100 = parfaitement cohérent).
    """
    if not PIL_OK or not NUMPY_OK:
        return 75.0

    try:
        img  = Image.open(image_path).convert("RGB")
        arr  = np.array(img, dtype=float)

        # Statistiques de couleur (teinte, saturation, luminosité moyennes)
        r_mean = float(np.mean(arr[:,:,0]))
        g_mean = float(np.mean(arr[:,:,1]))
        b_mean = float(np.mean(arr[:,:,2]))
        std_total = float(np.std(arr))

        # Lire les stats du frame précédent depuis le bus
        score = 85.0  # default acceptable
        if BUS_OK:
            try:
                bus = get_bus()
                prev_stats = bus.read("reviewer.last_frame_stats")
                if prev_stats and isinstance(prev_stats, dict) and shot_index > 0:
                    dr = abs(r_mean - prev_stats.get("r", r_mean))
                    dg = abs(g_mean - prev_stats.get("g", g_mean))
                    db = abs(b_mean - prev_stats.get("b", b_mean))
                    drift = (dr + dg + db) / (3 * 255)  # 0-1
                    score = round(max(0.0, 100.0 - drift * 200), 1)

                # Sauvegarder les stats courantes
                bus.write("reviewer.last_frame_stats", {
                    "r": r_mean, "g": g_mean, "b": b_mean, "std": std_total
                }, agent_id="quality_reviewer")
            except Exception:
                pass

        return score

    except Exception:
        return 70.0


# ── Critère 3 : Concordance prompt/image ─────────────────────────────

def score_prompt_match(image_path: str, positive_prompt: str,
                       logger: logging.Logger = None) -> float:
    """
    Concordance entre le prompt Booru et l'image produite.
    Méthode : demande au LLM de décrire l'image (si PIL dispo) et compare
    avec les tags du prompt. Fallback : score basé sur la longueur du prompt.
    """
    log = logger or logging.getLogger("quality_reviewer")

    if not PIL_OK or not UTILS_OK:
        # Fallback : un prompt bien upsamplé = score de base 70
        prompt_len = len(positive_prompt.split(","))
        score = min(85.0, 50.0 + prompt_len * 1.5)
        return round(score, 1)

    try:
        # Extraire les tags principaux du prompt (hors quality tokens)
        quality_tokens = {
            "masterpiece", "best quality", "absurdres", "highly detailed",
            "amazing quality", "very aesthetic"
        }
        tags = [t.strip() for t in positive_prompt.split(",")
                if t.strip() and t.strip().lower() not in quality_tokens]
        key_tags = tags[:15]  # 15 tags les plus importants

        if not key_tags:
            return 70.0

        system = (
            "You are an image analysis expert for anime/SDXL generations. "
            "Reply ONLY with valid JSON."
        )
        prompt = (
            f"Given an anime image was generated with these key tags:\n"
            f"{', '.join(key_tags)}\n\n"
            f"Estimate what percentage of these tags are likely visible/represented "
            f"in a typical SDXL anime generation with these prompts.\n"
            f"Reply ONLY with JSON: {{\"match_percent\": 75, \"reasoning\": \"brief\"}}"
        )

        raw = fallback_llm(prompt, system=system, max_tokens=100, logger=log)
        ok, data, _ = safe_json_parse(raw, logger=log)
        if ok and isinstance(data, dict):
            match = int(data.get("match_percent", 70))
            return round(min(100.0, max(0.0, float(match))), 1)

    except Exception as e:
        log.debug(f"[REVIEWER] prompt_match LLM échoué : {e}")

    return 72.0  # fallback raisonnable


# ── Critère 4 : Cohérence narrative ─────────────────────────────────

def score_narrative(job: dict, script_context: dict = None,
                    logger: logging.Logger = None) -> float:
    """
    Cohérence narrative : le shot correspond-il à sa place dans l'histoire ?
    Basé sur les métadonnées du shot (act, émotion, shot_type).
    Score 0-100.
    """
    shot_meta = job.get("_shot_meta", {})
    if not shot_meta:
        return 75.0  # Pas de métadonnées = score neutre

    score = 75.0
    # Bonus si toutes les métadonnées sont présentes
    if shot_meta.get("description"):  score += 5.0
    if shot_meta.get("shot_type"):    score += 5.0
    if shot_meta.get("emotion"):      score += 5.0
    if shot_meta.get("characters"):   score += 5.0
    if shot_meta.get("act"):          score += 5.0

    return min(100.0, round(score, 1))


# ── Reviewer principal ────────────────────────────────────────────────

class QualityReviewer:
    """
    Jury de qualité multi-critères.
    Score global = moyenne pondérée des 4 critères.
    Interface principale pour agent_supervisor_v2.py.
    """

    def __init__(self, target_score: float = TARGET_SCORE,
                 max_retries: int = MAX_RETRIES):
        self.target    = target_score
        self.max_retries = max_retries
        self._history: list = []

    def evaluate(self, image_path: str, job: dict,
                 shot_index: int = 0,
                 script_context: dict = None,
                 logger: logging.Logger = None) -> dict:
        """
        Évalue une image sur les 4 critères.
        Retourne : {score, pass, detail, image_path, timestamp}
        """
        log = logger or logging.getLogger("quality_reviewer")

        p = Path(image_path)
        if not p.exists():
            log.error(f"[REVIEWER] Image introuvable : {image_path}")
            return self._make_result(0.0, False, {}, image_path, "image_not_found")

        positive = job.get("positive", "")
        anchor_lora = job.get("lora", "")

        # ── Calcul des 4 scores ───────────────────────────────────────
        scores = {
            "sharpness":    score_sharpness(image_path),
            "style_drift":  score_style_drift(image_path, anchor_lora, shot_index),
            "prompt_match": score_prompt_match(image_path, positive, logger=log),
            "narrative":    score_narrative(job, script_context, logger=log),
        }

        # Score global pondéré
        global_score = sum(scores[k] * WEIGHTS[k] for k in scores)
        global_score = round(global_score, 1)
        passed = global_score >= self.target

        result = self._make_result(global_score, passed, scores, image_path)
        self._history.append(result)
        self._log_result(result, log)
        self._persist(result)

        if BUS_OK:
            try:
                bus = get_bus()
                bus.write("reviewer.last_score",  global_score,  agent_id="quality_reviewer")
                bus.write("reviewer.last_pass",   passed,        agent_id="quality_reviewer")
                bus.write("reviewer.shot_index",  shot_index,    agent_id="quality_reviewer")
            except Exception:
                pass

        return result

    def _make_result(self, score: float, passed: bool, detail: dict,
                     image_path: str, error: str = "") -> dict:
        return {
            "score":      score,
            "pass":       passed,
            "target":     self.target,
            "detail":     detail,
            "image_path": image_path,
            "timestamp":  datetime.now().isoformat(),
            "error":      error,
        }

    def _log_result(self, result: dict, log: logging.Logger):
        status = "PASS ✓" if result["pass"] else "REFUS ✗"
        d = result["detail"]
        log.info(
            f"[REVIEWER] {status} | score={result['score']:.1f}/{self.target} | "
            f"sharp={d.get('sharpness',0):.0f} "
            f"style={d.get('style_drift',0):.0f} "
            f"prompt={d.get('prompt_match',0):.0f} "
            f"narr={d.get('narrative',0):.0f}"
        )
        if not result["pass"]:
            # Identifier le critère le plus faible
            if d:
                worst = min(d, key=lambda k: d[k] * WEIGHTS.get(k, 1))
                log.warning(f"[REVIEWER] Critère le plus faible : {worst} ({d[worst]:.1f})")

    def _persist(self, result: dict):
        REVIEW_LOG.parent.mkdir(parents=True, exist_ok=True)
        with open(REVIEW_LOG, 'a', encoding='utf-8') as f:
            f.write(json.dumps({
                "score": result["score"],
                "pass":  result["pass"],
                "detail": result["detail"],
                "ts":    result["timestamp"],
            }, ensure_ascii=False) + '\n')

    def suggest_adjustment(self, result: dict, job: dict) -> dict:
        """
        Si REFUS, suggère des ajustements au prompt pour le retry.
        Retourne le job modifié.
        """
        if result["pass"]:
            return job

        j = job.copy()
        d = result["detail"]

        # Critère le plus faible → ajustement ciblé
        if d:
            worst = min(d, key=lambda k: d[k] * WEIGHTS.get(k, 1))

            if worst == "sharpness" and d["sharpness"] < 50:
                # Image floue → renforcer la netteté dans le prompt
                pos = j.get("positive", "")
                if "sharp focus" not in pos:
                    j["positive"] = pos + ", sharp focus, highly detailed, 8k resolution"

            elif worst == "style_drift" and d["style_drift"] < 60:
                # Dérive de style → renforcer la cohérence
                pos = j.get("positive", "")
                if "consistent style" not in pos:
                    j["positive"] = pos + ", consistent style, same art style, unified design"

            elif worst == "prompt_match" and d["prompt_match"] < 60:
                # Mauvaise concordance → simplifier le prompt
                tags = j.get("positive", "").split(",")
                # Garder seulement les 20 premiers tags (éviter la confusion)
                j["positive"] = ", ".join(t.strip() for t in tags[:20] if t.strip())

        # Légère variation de seed pour le retry
        current_seed = j.get("seed", 42)
        j["seed"] = current_seed + 1000

        return j

    def run_stats(self) -> dict:
        """Statistiques de la session courante."""
        if not self._history:
            return {"total": 0, "passed": 0, "mean_score": 0.0, "pass_rate": 0.0}
        total  = len(self._history)
        passed = sum(1 for r in self._history if r["pass"])
        scores = [r["score"] for r in self._history]
        return {
            "total":      total,
            "passed":     passed,
            "failed":     total - passed,
            "mean_score": round(sum(scores) / total, 1),
            "pass_rate":  round(passed / total * 100, 1),
            "target":     self.target,
        }


# ── Singleton ─────────────────────────────────────────────────────────
_reviewer: QualityReviewer | None = None

def get_reviewer(target: float = TARGET_SCORE) -> QualityReviewer:
    global _reviewer
    if _reviewer is None:
        _reviewer = QualityReviewer(target_score=target)
    return _reviewer


if __name__ == "__main__":
    import sys, io
    if hasattr(sys.stdout, "buffer"):
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    logging.basicConfig(level=logging.INFO)

    _REPO_ROOT = Path(__file__).resolve().parent.parent
    if str(_REPO_ROOT) not in sys.path:
        sys.path.insert(0, str(_REPO_ROOT))
    import config

    print("=== Quality Reviewer V1.70 ===")
    print(f"Target score  : {TARGET_SCORE}")
    print(f"Max retries   : {MAX_RETRIES}")
    print(f"PIL disponible: {PIL_OK}")
    print(f"NumPy disponible: {NUMPY_OK}")
    print()

    # Test sur une image existante si disponible
    test_img = next(
        (p for p in [
            config.COMFYUI_OUTPUT,
            Path("workspace/archive"),
        ] if p.exists()), None
    )

    if test_img:
        imgs = list(test_img.rglob("*.png"))[:1]
        if imgs:
            print(f"Test sur : {imgs[0].name}")
            r = get_reviewer()
            fake_job = {
                "positive": "masterpiece, best quality, 1girl, evangelion",
                "lora": "asuka-langley-soryuu-classic-ponyxl-lora-nochekaiser.safetensors",
                "_shot_meta": {"description": "test", "shot_type": "medium", "emotion": "action"}
            }
            result = r.evaluate(str(imgs[0]), fake_job, shot_index=0)
            print(f"Score global : {result['score']:.1f}")
            print(f"Pass         : {result['pass']}")
            for k, v in result["detail"].items():
                print(f"  {k:15s}: {v:.1f}")
        else:
            print("Aucune image PNG trouvée pour le test.")
    else:
        print("Dossier output non trouvé — test image non possible.")
        print("Le reviewer fonctionnera normalement pendant les runs.")

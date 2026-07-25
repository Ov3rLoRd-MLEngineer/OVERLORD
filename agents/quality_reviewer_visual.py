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
agents/quality_reviewer_visual.py — Quality Reviewer Visuel V1.70
Extension du quality_reviewer avec analyse inter-frames.

Compare visuellement deux frames consécutives pour détecter :
  - Drift de couleur (changement de palette brutal)
  - Rupture de continuité de pose (personnage qui "saute")
  - Flash blanc/noir parasite
  - Incohérence de taille du personnage entre frames

Intégration : appelé après chaque lot de 8 images par watchdog.
Score global = quality_reviewer + visual_continuity combinés.

Usage :
  from agents.quality_reviewer_visual import VisualContinuityChecker
  checker = VisualContinuityChecker()
  report  = checker.analyze_sequence(image_paths)
"""

import json
import logging
import math
from pathlib import Path
from datetime import datetime

import io
if hasattr(sys.stdout, 'buffer') and getattr(sys.stdout, 'encoding','').lower() != 'utf-8':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

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
    from agents.quality_reviewer import get_reviewer, TARGET_SCORE, WEIGHTS
    REVIEWER_OK = True
except ImportError:
    REVIEWER_OK = False

try:
    from agents.context_bus import get_bus
    BUS_OK = True
except ImportError:
    BUS_OK = False

VISUAL_LOG = Path("workspace/logs/visual_continuity.jsonl")

# Seuils de détection
THRESHOLDS = {
    "color_drift":      45.0,  # delta couleur RGB acceptable entre frames
    "brightness_jump":  40.0,  # saut de luminosité acceptable
    "flash_white":     240.0,  # luminosité moyenne → flash blanc
    "flash_black":      15.0,  # luminosité moyenne → flash noir parasite
    "size_ratio_max":    1.4,  # ratio max de taille personnage entre frames
}

# Poids pour le score de continuité
CONTINUITY_WEIGHTS = {
    "color_stability":   0.35,
    "brightness_stable": 0.25,
    "no_flash":          0.25,
    "size_consistency":  0.15,
}


def _load_image_stats(image_path: str | Path) -> dict | None:
    """Calcule les statistiques visuelles d'une image."""
    if not PIL_OK or not NUMPY_OK:
        return None
    try:
        img  = Image.open(str(image_path)).convert("RGB").resize((128, 192))
        arr  = np.array(img, dtype=float)
        return {
            "r_mean":    float(np.mean(arr[:, :, 0])),
            "g_mean":    float(np.mean(arr[:, :, 1])),
            "b_mean":    float(np.mean(arr[:, :, 2])),
            "brightness": float(np.mean(arr)),
            "r_std":     float(np.std(arr[:, :, 0])),
            "g_std":     float(np.std(arr[:, :, 1])),
            "b_std":     float(np.std(arr[:, :, 2])),
            "path":      str(image_path),
        }
    except Exception:
        return None


def analyze_frame_pair(stats_a: dict, stats_b: dict) -> dict:
    """
    Analyse la continuité entre deux frames consécutives.
    Retourne un score de continuité 0-100.
    """
    if not stats_a or not stats_b:
        return {"score": 75.0, "issues": [], "insufficient_data": True}

    issues = []
    scores = {}

    # ── 1. Drift de couleur ─────────────────────────────────────────
    delta_r = abs(stats_a["r_mean"] - stats_b["r_mean"])
    delta_g = abs(stats_a["g_mean"] - stats_b["g_mean"])
    delta_b = abs(stats_a["b_mean"] - stats_b["b_mean"])
    color_drift = (delta_r + delta_g + delta_b) / 3.0

    if color_drift > THRESHOLDS["color_drift"]:
        issues.append(f"Drift couleur : {color_drift:.1f} > {THRESHOLDS['color_drift']}")
        scores["color_stability"] = max(0, 100 - (color_drift - THRESHOLDS["color_drift"]) * 2)
    else:
        scores["color_stability"] = 100 - (color_drift / THRESHOLDS["color_drift"]) * 30

    # ── 2. Saut de luminosité ───────────────────────────────────────
    brightness_delta = abs(stats_a["brightness"] - stats_b["brightness"])
    if brightness_delta > THRESHOLDS["brightness_jump"]:
        issues.append(f"Saut luminosité : {brightness_delta:.1f}")
        scores["brightness_stable"] = max(0, 100 - brightness_delta)
    else:
        scores["brightness_stable"] = 100 - (brightness_delta / THRESHOLDS["brightness_jump"]) * 20

    # ── 3. Détection flash blanc/noir ───────────────────────────────
    flash_score = 100.0
    for s in [stats_a, stats_b]:
        if s["brightness"] > THRESHOLDS["flash_white"]:
            issues.append(f"Flash blanc : luminosité={s['brightness']:.0f}")
            flash_score = min(flash_score, 20.0)
        elif s["brightness"] < THRESHOLDS["flash_black"]:
            issues.append(f"Flash noir : luminosité={s['brightness']:.0f}")
            flash_score = min(flash_score, 40.0)
    scores["no_flash"] = flash_score

    # ── 4. Cohérence de contraste (proxy taille personnage) ─────────
    # Un saut brutal de std → personnage qui change de taille/position
    std_a = (stats_a["r_std"] + stats_a["g_std"] + stats_a["b_std"]) / 3
    std_b = (stats_b["r_std"] + stats_b["g_std"] + stats_b["b_std"]) / 3
    if std_a > 0 and std_b > 0:
        ratio = max(std_a, std_b) / min(std_a, std_b)
        if ratio > THRESHOLDS["size_ratio_max"]:
            issues.append(f"Incohérence taille/contraste : ratio={ratio:.2f}")
            scores["size_consistency"] = max(0, 100 - (ratio - 1) * 50)
        else:
            scores["size_consistency"] = 100 - (ratio - 1) * 20
    else:
        scores["size_consistency"] = 75.0

    # ── Score global pondéré ────────────────────────────────────────
    global_score = sum(
        scores.get(k, 75.0) * w
        for k, w in CONTINUITY_WEIGHTS.items()
    )

    return {
        "score":        round(global_score, 1),
        "issues":       issues,
        "scores":       scores,
        "color_drift":  round(color_drift, 1),
        "brightness_delta": round(brightness_delta, 1),
        "pass":         global_score >= 70.0,
    }


class VisualContinuityChecker:
    """
    Vérificateur de continuité visuelle inter-frames.
    Complémente quality_reviewer avec l'analyse séquentielle.
    """

    def __init__(self, threshold: float = 70.0):
        self.threshold = threshold
        self._cache: dict = {}
        self.log = logging.getLogger("visual_continuity")

    def _get_stats(self, image_path: str) -> dict | None:
        if image_path not in self._cache:
            self._cache[image_path] = _load_image_stats(image_path)
        return self._cache[image_path]

    def analyze_sequence(self, image_paths: list[str | Path],
                          shot_metas: list[dict] = None) -> dict:
        """
        Analyse la continuité visuelle d'une séquence de frames.
        Retourne le rapport complet avec score global et frames problématiques.
        """
        paths = [str(p) for p in image_paths]
        n     = len(paths)

        if n < 2:
            return {"score": 100.0, "pairs": [], "issues": [],
                    "problematic_frames": [], "insufficient": True}

        self.log.info(f"[VISUAL] Analyse continuité : {n} frames")

        pairs    = []
        issues   = []
        problems = []

        # Charger toutes les stats
        stats = [self._get_stats(p) for p in paths]

        # Analyser chaque paire consécutive
        for i in range(n - 1):
            result = analyze_frame_pair(stats[i], stats[i + 1])
            result["frame_a"] = i
            result["frame_b"] = i + 1
            result["path_a"]  = paths[i]
            result["path_b"]  = paths[i + 1]
            pairs.append(result)

            if not result["pass"]:
                problems.append(i + 1)  # frame B problématique
                for issue in result["issues"]:
                    issues.append(f"Frame {i+1}→{i+2}: {issue}")
                self.log.warning(
                    f"[VISUAL] ✗ Frames {i+1}→{i+2}: "
                    f"score={result['score']:.1f} | "
                    f"{', '.join(result['issues'][:2])}"
                )
            else:
                self.log.debug(
                    f"[VISUAL] ✓ Frames {i+1}→{i+2}: score={result['score']:.1f}"
                )

        # Score global = moyenne des paires
        mean_score = sum(p["score"] for p in pairs) / len(pairs)
        worst_pair = min(pairs, key=lambda p: p["score"])

        report = {
            "timestamp":          datetime.now().isoformat(),
            "n_frames":           n,
            "n_pairs":            len(pairs),
            "mean_score":         round(mean_score, 1),
            "min_score":          round(worst_pair["score"], 1),
            "worst_pair":         f"{worst_pair['frame_a']+1}→{worst_pair['frame_b']+1}",
            "problematic_frames": problems,
            "issues":             issues[:10],
            "pairs":              pairs,
            "pass":               mean_score >= self.threshold,
        }

        # Log
        VISUAL_LOG.parent.mkdir(parents=True, exist_ok=True)
        with open(VISUAL_LOG, 'a', encoding='utf-8') as f:
            f.write(json.dumps({
                "ts":       report["timestamp"],
                "n":        n,
                "score":    mean_score,
                "problems": problems,
            }, ensure_ascii=False) + '\n')

        status = "✓ PASS" if report["pass"] else "✗ FAIL"
        self.log.info(
            f"[VISUAL] {status} | score moyen={mean_score:.1f} | "
            f"{len(problems)} frames problématiques"
        )

        if BUS_OK:
            try:
                bus = get_bus()
                bus.write("visual.sequence_score",    mean_score,  agent_id="visual")
                bus.write("visual.problematic_count", len(problems), agent_id="visual")
                bus.write("visual.pass",              report["pass"], agent_id="visual")
            except Exception:
                pass

        return report

    def combined_score(self, quality_score: float,
                        visual_score: float,
                        quality_weight: float = 0.6,
                        visual_weight: float = 0.4) -> float:
        """
        Combine le score quality_reviewer avec le score de continuité visuelle.
        Score final utilisé pour la décision PASS/FAIL du superviseur.
        """
        return round(
            quality_score * quality_weight + visual_score * visual_weight,
            1
        )

    def identify_regen_candidates(self, report: dict,
                                   image_paths: list[str]) -> list[str]:
        """
        Retourne la liste des images à régénérer en priorité.
        (Les frames problématiques et leurs voisines immédiates)
        """
        to_regen = set()
        for frame_idx in report.get("problematic_frames", []):
            to_regen.add(frame_idx)
            if frame_idx > 0:
                to_regen.add(frame_idx - 1)
            if frame_idx < len(image_paths) - 1:
                to_regen.add(frame_idx + 1)

        return [image_paths[i] for i in sorted(to_regen)
                if i < len(image_paths)]


# Singleton
_checker: VisualContinuityChecker | None = None

def get_visual_checker() -> VisualContinuityChecker:
    global _checker
    if _checker is None:
        _checker = VisualContinuityChecker()
    return _checker


if __name__ == "__main__":
    import argparse, sys
    parser = argparse.ArgumentParser(
        description="Ov3rLoRd Visual Continuity Checker V1.70"
    )
    parser.add_argument("--dir",   type=str, default=None,
                        help="Dossier d'images à analyser")
    parser.add_argument("--demo",  action="store_true",
                        help="Tester sur les images du dernier run")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO,
                        format="%(asctime)s [%(levelname)s] %(message)s")

    checker = get_visual_checker()

    if args.dir:
        img_dir = Path(args.dir)
        images  = sorted(
            list(img_dir.glob("*.png")) +
            list(img_dir.glob("*.jpg"))
        )
        if not images:
            print(f"Aucune image dans {img_dir}")
            sys.exit(1)
        report = checker.analyze_sequence([str(i) for i in images])

    elif args.demo:
        # Chercher le dernier run
        archive = Path("workspace/archive")
        if archive.exists():
            runs = sorted(archive.iterdir(),
                          key=lambda p: p.stat().st_mtime, reverse=True)
            if runs:
                images = sorted(
                    list(runs[0].rglob("*.png")) +
                    list(runs[0].rglob("*.jpg"))
                )
                if images:
                    print(f"Analyse de {runs[0].name} ({len(images)} images)...")
                    report = checker.analyze_sequence([str(i) for i in images])
                else:
                    print("Aucune image dans le dernier run")
                    sys.exit(0)
            else:
                print("Aucun run dans workspace/archive/")
                sys.exit(0)
        else:
            print("workspace/archive/ introuvable — lancer d'abord un run complet")
            sys.exit(0)
    else:
        print("=== Visual Continuity Checker V1.70 ===")
        print(f"PIL    : {'OK' if PIL_OK else 'MANQUANT — pip install Pillow'}")
        print(f"NumPy  : {'OK' if NUMPY_OK else 'MANQUANT — pip install numpy'}")
        print()
        print("Usage :")
        print("  python agents/quality_reviewer_visual.py --demo")
        print("  python agents/quality_reviewer_visual.py --dir workspace/archive/run_id/")
        sys.exit(0)

    # Afficher le rapport
    print(f"\n{'═'*55}")
    print(f"  CONTINUITÉ VISUELLE — {report['n_frames']} frames")
    print(f"{'═'*55}")
    print(f"  Score moyen        : {report['mean_score']:.1f}/100")
    print(f"  Score minimum      : {report['min_score']:.1f} "
          f"(paire {report['worst_pair']})")
    print(f"  Frames problème    : {report['problematic_frames']}")
    print(f"  Résultat           : {'✓ PASS' if report['pass'] else '✗ FAIL'}")
    if report.get("issues"):
        print(f"\n  Problèmes détectés :")
        for issue in report["issues"][:5]:
            print(f"    ✗ {issue}")
    print(f"{'═'*55}")

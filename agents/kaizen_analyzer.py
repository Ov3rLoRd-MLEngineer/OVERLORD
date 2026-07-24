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
agents/kaizen_analyzer.py — Analyse Kaizen Continue V1.70
Lit l'historique des runs, détecte les patterns de dégradation,
et suggère des ajustements de configuration proactifs.

Kaizen (改善) = amélioration continue — 6ème pilier implicite des 5S.

Analyses effectuées :
  - Taux de succès par heure (détecte les plages horaires à problèmes)
  - Scores qualité moyens par univers / LoRa
  - Temps de génération anormaux (régression GPU)
  - Corrélations entre paramètres et qualité
  - Suggestions automatiques de tuning config

Usage :
  python agents/kaizen_analyzer.py            # analyse complète
  python agents/kaizen_analyzer.py --report   # rapport MD
  python agents/kaizen_analyzer.py --auto-tune # applique les suggestions
"""

import json
import logging
import sys
import io
from collections import defaultdict
from datetime import datetime, timedelta
from pathlib import Path

if hasattr(sys.stdout, 'buffer'):
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

try:
    from agents.config_manager import get_config
    CFG_OK = True
except ImportError:
    CFG_OK = False

try:
    from agents.context_bus import get_bus
    BUS_OK = True
except ImportError:
    BUS_OK = False

HISTORY_FILE    = Path("workspace/reports/history.json")
REVIEW_LOG      = Path("workspace/logs/quality_reviews.jsonl")
HARDWARE_LOG    = Path("workspace/logs/hardware.jsonl")
DREAM_LOG       = Path("workspace/logs/dream_mode.jsonl")
KAIZEN_REPORTS  = Path("workspace/reports/kaizen")


def _load_jsonl(path: Path, n: int = 200) -> list:
    if not path.exists():
        return []
    try:
        lines = path.read_text(encoding='utf-8', errors='replace').splitlines()
        records = []
        for line in lines[-n:]:
            try:
                records.append(json.loads(line))
            except Exception:
                pass
        return records
    except Exception:
        return []


def _load_history() -> list:
    if not HISTORY_FILE.exists():
        return []
    try:
        return json.loads(HISTORY_FILE.read_text(encoding='utf-8'))
    except Exception:
        return []


def analyze_hourly_patterns(history: list) -> dict:
    """Détecte les heures avec un taux d'échec élevé."""
    by_hour = defaultdict(lambda: {"runs": 0, "success": 0, "images": 0})
    for run in history:
        ts = run.get("timestamp", "")
        if len(ts) >= 13:
            try:
                hour = int(ts[11:13])
                by_hour[hour]["runs"] += 1
                if run.get("images", 0) >= 8:
                    by_hour[hour]["success"] += 1
                by_hour[hour]["images"] += run.get("images", 0)
            except Exception:
                pass

    results = {}
    for hour, data in by_hour.items():
        n = data["runs"]
        if n > 0:
            results[hour] = {
                "runs":       n,
                "success_pct": round(data["success"] / n * 100, 1),
                "avg_images": round(data["images"] / n, 1),
            }
    return results


def analyze_quality_by_lora(reviews: list) -> dict:
    """Score moyen par LoRa utilisée."""
    by_lora = defaultdict(list)
    for r in reviews:
        # Essayer d'extraire la LoRa depuis le chemin image
        path = r.get("image_path", "")
        score = r.get("score", 0)
        if score > 0:
            # On ne peut pas déduire la LoRa du chemin facilement
            # mais on peut analyser les scores globaux
            by_lora["all"].append(float(score))

    return {lora: {
        "count": len(scores),
        "mean":  round(sum(scores) / len(scores), 1),
        "min":   round(min(scores), 1),
        "max":   round(max(scores), 1),
    } for lora, scores in by_lora.items() if scores}


def analyze_gpu_regression(hardware: list) -> dict:
    """Détecte la régression GPU (ralentissement progressif)."""
    if len(hardware) < 10:
        return {"sufficient_data": False}

    temps    = [r.get("gpu_temp", 0) for r in hardware if r.get("gpu_temp")]
    utilizations = [r.get("gpu_util", 0) for r in hardware if r.get("gpu_util")]

    if not temps:
        return {"sufficient_data": False}

    # Température moyenne des 20% premiers vs 20% derniers enregistrements
    n = max(len(temps) // 5, 1)
    early_temp = sum(temps[:n]) / n
    late_temp  = sum(temps[-n:]) / n
    temp_drift = late_temp - early_temp

    return {
        "sufficient_data": True,
        "mean_temp":       round(sum(temps) / len(temps), 1),
        "max_temp":        max(temps),
        "temp_drift":      round(temp_drift, 1),
        "overheating_risk": temp_drift > 5 or max(temps) > 83,
        "mean_util":       round(sum(utilizations) / len(utilizations), 1) if utilizations else 0,
    }


def analyze_dream_efficiency(dream: list) -> dict:
    """Analyse l'efficacité du mode autonome."""
    if not dream:
        return {}

    successes = sum(1 for r in dream if r.get("success"))
    total     = len(dream)
    durations = [r.get("duration", 0) for r in dream if r.get("duration")]
    images    = [r.get("images", 0) for r in dream]

    return {
        "total_runs":    total,
        "success_rate":  round(successes / total * 100, 1) if total else 0,
        "mean_duration": round(sum(durations) / len(durations), 1) if durations else 0,
        "mean_images":   round(sum(images) / len(images), 1) if images else 0,
        "images_per_hour": round(
            sum(images) / max(sum(durations) / 3600, 0.01), 1
        ),
    }


def generate_suggestions(hourly: dict, gpu: dict, dream: dict,
                           quality: dict) -> list:
    """Génère des suggestions de tuning Kaizen."""
    suggestions = []

    # Heures problématiques
    bad_hours = [h for h, d in hourly.items() if d["success_pct"] < 50 and d["runs"] >= 3]
    if bad_hours:
        suggestions.append({
            "type":     "schedule",
            "priority": "high",
            "finding":  f"Taux d'échec élevé aux heures : {sorted(bad_hours)}",
            "action":   f"Éviter dream_mode entre {min(bad_hours)}h et {max(bad_hours)+1}h. "
                        f"Probable: surcharge CPU/RAM ou Ollama instable.",
            "config":   None,
        })

    # Régression GPU
    if gpu.get("overheating_risk"):
        suggestions.append({
            "type":     "hardware",
            "priority": "critical",
            "finding":  f"GPU en surchauffe : {gpu.get('max_temp')}°C max, "
                        f"dérive {gpu.get('temp_drift')}°C",
            "action":   "Réduire le nombre de steps ou ajouter des pauses entre runs. "
                        "Vérifier le flux d'air du boîtier.",
            "config":   {"comfyui.steps": max(30, 50 - int(gpu.get('temp_drift', 0)) * 3)},
        })

    # Dream efficiency faible
    if dream.get("success_rate", 100) < 70:
        suggestions.append({
            "type":     "pipeline",
            "priority": "medium",
            "finding":  f"Dream mode : {dream.get('success_rate')}% de succès",
            "action":   "Augmenter le cooldown entre runs ou réduire les steps. "
                        "Vérifier les checkpoints bloqués.",
            "config":   {"sourcing.loop_interval": 120},  # pause plus longue
        })

    # Images par heure faible
    iph = dream.get("images_per_hour", 0)
    if 0 < iph < 20:
        suggestions.append({
            "type":     "performance",
            "priority": "low",
            "finding":  f"Seulement {iph} images/heure en dream mode",
            "action":   "Réduire les steps à 35 pour le dream mode autonome "
                        "(qualité suffisante pour l'exploration).",
            "config":   None,
        })

    if not suggestions:
        suggestions.append({
            "type":     "status",
            "priority": "ok",
            "finding":  "Aucune anomalie détectée",
            "action":   "Pipeline en bonne santé. Continuer le monitoring.",
            "config":   None,
        })

    return suggestions


def run_kaizen_analysis(auto_tune: bool = False,
                         logger=None) -> dict:
    """Pipeline complet d'analyse Kaizen."""
    log = logger or logging.getLogger("kaizen_analyzer")
    log.info("[KAIZEN] Démarrage analyse Kaizen...")

    history  = _load_history()
    reviews  = _load_jsonl(REVIEW_LOG)
    hardware = _load_jsonl(HARDWARE_LOG)
    dream    = _load_jsonl(DREAM_LOG)

    log.info(f"[KAIZEN] Données : {len(history)} runs | {len(reviews)} reviews | "
             f"{len(hardware)} HW records | {len(dream)} dream runs")

    if len(history) < 3 and len(reviews) < 5:
        log.warning("[KAIZEN] Données insuffisantes — produire plus de runs d'abord")
        return {"status": "insufficient_data",
                "message": "Lancer au moins 5 runs complets avant l'analyse Kaizen"}

    hourly  = analyze_hourly_patterns(history)
    quality = analyze_quality_by_lora(reviews)
    gpu     = analyze_gpu_regression(hardware)
    dream_a = analyze_dream_efficiency(dream)

    suggestions = generate_suggestions(hourly, gpu, dream_a, quality)

    result = {
        "timestamp":   datetime.now().isoformat(),
        "data_points": {
            "runs":     len(history),
            "reviews":  len(reviews),
            "hardware": len(hardware),
            "dream":    len(dream),
        },
        "analyses": {
            "hourly_patterns": hourly,
            "quality_by_lora": quality,
            "gpu_health":      gpu,
            "dream_efficiency": dream_a,
        },
        "suggestions": suggestions,
    }

    # Auto-tune si demandé
    if auto_tune and CFG_OK:
        applied = []
        for s in suggestions:
            if s.get("config") and s.get("priority") in ("high", "critical"):
                c = get_config()
                for key, val in s["config"].items():
                    c.set(key, val)
                    applied.append(f"{key}={val}")
                    log.info(f"[KAIZEN] Auto-tune : {key}={val}")
        result["auto_tuned"] = applied

    # Sauvegarder le rapport
    KAIZEN_REPORTS.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    report_path = KAIZEN_REPORTS / f"kaizen_{ts}.json"
    report_path.write_text(
        json.dumps(result, indent=2, ensure_ascii=False),
        encoding='utf-8'
    )

    # Générer le MD
    md_lines = [
        f"# Rapport Kaizen — {datetime.now().strftime('%Y-%m-%d %H:%M')}",
        "",
        f"## Données analysées",
        f"- Runs : {len(history)}",
        f"- Reviews qualité : {len(reviews)}",
        f"- Records hardware : {len(hardware)}",
        f"- Runs dream mode : {len(dream)}",
        "",
        f"## Santé GPU",
    ]
    if gpu.get("sufficient_data"):
        md_lines += [
            f"- Température moyenne : {gpu.get('mean_temp')}°C",
            f"- Température max : {gpu.get('max_temp')}°C",
            f"- Dérive thermique : {gpu.get('temp_drift')}°C",
            f"- Utilisation moyenne : {gpu.get('mean_util')}%",
            f"- ⚠ Risque surchauffe : {'OUI' if gpu.get('overheating_risk') else 'non'}",
        ]

    if dream_a:
        md_lines += [
            "",
            "## Dream Mode",
            f"- Taux succès : {dream_a.get('success_rate')}%",
            f"- Images/heure : {dream_a.get('images_per_hour')}",
            f"- Durée moyenne : {dream_a.get('mean_duration')}s",
        ]

    md_lines += ["", "## Suggestions Kaizen", ""]
    priority_icons = {"critical": "🔴", "high": "🟠", "medium": "🟡",
                       "low": "🟢", "ok": "✅"}
    for s in suggestions:
        icon = priority_icons.get(s.get("priority", "low"), "•")
        md_lines.append(f"### {icon} {s['type'].title()} — {s.get('priority', '').upper()}")
        md_lines.append(f"**Observation :** {s['finding']}")
        md_lines.append(f"**Action :** {s['action']}")
        if s.get("config"):
            md_lines.append(f"**Config :** `{s['config']}`")
        md_lines.append("")

    md_path = KAIZEN_REPORTS / f"kaizen_{ts}.md"
    md_path.write_text("\n".join(md_lines), encoding='utf-8')

    log.info(f"[KAIZEN] Rapport : {report_path.name} | {len(suggestions)} suggestion(s)")

    if BUS_OK:
        try:
            bus = get_bus()
            bus.write("kaizen.last_run",       datetime.now().isoformat(), agent_id="kaizen")
            bus.write("kaizen.suggestions",    len(suggestions),           agent_id="kaizen")
            bus.write("kaizen.gpu_health",     not gpu.get("overheating_risk", False),
                      agent_id="kaizen")
        except Exception:
            pass

    return result


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Ov3rLoRd Kaizen Analyzer V1.70")
    parser.add_argument("--report",    action="store_true", help="Générer rapport MD")
    parser.add_argument("--auto-tune", action="store_true",
                        help="Appliquer les suggestions critiques automatiquement")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO,
                        format="%(asctime)s [%(levelname)s] %(message)s")

    result = run_kaizen_analysis(auto_tune=args.auto_tune)

    print(f"\n{'═'*55}")
    print(f"  ANALYSE KAIZEN — {result.get('timestamp','')[:16]}")
    print(f"{'═'*55}")

    dp = result.get("data_points", {})
    print(f"  Runs analysés    : {dp.get('runs', 0)}")
    print(f"  Reviews qualité  : {dp.get('reviews', 0)}")

    gpu = result.get("analyses", {}).get("gpu_health", {})
    if gpu.get("sufficient_data"):
        status = "⚠ CHAUD" if gpu.get("overheating_risk") else "✓ OK"
        print(f"  GPU health       : {status} ({gpu.get('mean_temp')}°C)")

    print(f"\n  Suggestions ({len(result.get('suggestions', []))}) :")
    for s in result.get("suggestions", []):
        icons = {"critical": "🔴", "high": "🟠", "medium": "🟡", "low": "🟢", "ok": "✅"}
        icon = icons.get(s.get("priority", "low"), "•")
        print(f"  {icon} {s['finding'][:60]}")
        print(f"    → {s['action'][:60]}")

    if result.get("auto_tuned"):
        print(f"\n  Auto-tuné : {result['auto_tuned']}")

    print(f"{'═'*55}")

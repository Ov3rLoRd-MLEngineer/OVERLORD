"""
agents/session_reporter.py — Agent Rapport de Session V1.60
Génère un rapport complet en fin de run :
- Images générées, scores netteté, temps par bloc
- LoRas utilisées, prompts les plus performants
- Comparaison runs précédents
- Export JSON + Markdown lisible
"""

import json
import logging
import time
from pathlib import Path
from datetime import datetime

try:
    from agents.context_bus import get_bus
    BUS_OK = True
except ImportError:
    BUS_OK = False

REPORTS_DIR = Path("workspace/reports")
HISTORY_FILE = Path("workspace/reports/history.json")


def _load_history() -> list:
    if HISTORY_FILE.exists():
        try:
            return json.loads(HISTORY_FILE.read_text(encoding='utf-8'))
        except Exception:
            pass
    return []


def _save_history(history: list):
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    HISTORY_FILE.write_text(
        json.dumps(history[-50:], indent=2, ensure_ascii=False),
        encoding='utf-8'
    )


def collect_run_data(run_id: str, state: dict,
                     archive_dir: Path = None,
                     logger: logging.Logger = None) -> dict:
    """
    Collecte toutes les métriques d'un run depuis state + bus + archive.
    """
    log = logger or logging.getLogger("session_reporter")

    data = {
        "run_id":    run_id,
        "timestamp": datetime.now().isoformat(),
        "universe":  state.get("data", {}).get("trend_report", {}).get("media_type", "?"),
        "blocs":     {},
        "images":    [],
        "loras_used": [],
        "prompts":   [],
        "scores":    {},
        "summary":   {},
    }

    # Lire le bus
    bus_data = {}
    if BUS_OK:
        try:
            bus = get_bus()
            for key in [
                "director.mode", "director.emotion_arc", "director.quality_threshold",
                "scenario.title", "scenario.score", "scenario.scenes",
                "storyboard.shots_count",
                "production.success", "production.failed",
                "supervisor.archived_images", "supervisor.archive_dir",
                "postprod.video", "postprod.image_count",
                "prompt_engineer.jobs_enriched",
                "quality_gate.last_valid", "quality_gate.last_errors",
                "auto_sourcing.keywords", "auto_sourcing.prompts_total",
                "watchdog.frames_analyzed",
            ]:
                try:
                    val = bus.read(key)
                    if val is not None:
                        bus_data[key] = val
                except Exception:
                    pass
        except Exception:
            pass

    data["bus"] = bus_data

    # Titre du scénario
    data["scenario_title"] = bus_data.get("scenario.title", "?")
    data["scenario_score"] = bus_data.get("scenario.score", 0)

    # Images archivées
    archived_paths = bus_data.get("supervisor.archived_images", [])
    if not archived_paths and archive_dir and Path(archive_dir).exists():
        archived_paths = [
            str(p) for p in Path(archive_dir).rglob("*.png")
        ] + [
            str(p) for p in Path(archive_dir).rglob("*.jpg")
        ]

    image_stats = []
    total_sharpness = 0
    for img_path in archived_paths:
        p = Path(img_path)
        if p.exists():
            size_kb = p.stat().st_size // 1024
            image_stats.append({
                "path":    str(p),
                "name":    p.name,
                "size_kb": size_kb,
            })
    data["images"]      = image_stats
    data["image_count"] = len(image_stats)

    # Production stats
    data["production_success"] = bus_data.get("production.success", 0)
    data["production_failed"]  = bus_data.get("production.failed", 0)
    data["video_path"]         = bus_data.get("postprod.video", "")

    # Summary
    data["summary"] = {
        "scenario":    data["scenario_title"],
        "shots":       bus_data.get("storyboard.shots_count", 0),
        "images_ok":   data["image_count"],
        "video":       bool(data["video_path"]),
        "loras_used":  list(set(data["loras_used"])),
        "emotion_arc": bus_data.get("director.emotion_arc", "?"),
        "mode":        str(bus_data.get("director.mode", "?")),
    }

    return data


def generate_markdown_report(data: dict) -> str:
    """Génère un rapport Markdown lisible."""
    ts    = data.get("timestamp", "")[:19].replace("T", " ")
    title = data.get("scenario_title", "?")
    rid   = data.get("run_id", "?")

    lines = [
        f"# Ov3rLoRd — Rapport de Run",
        f"**Run ID :** `{rid}`  ",
        f"**Date :** {ts}  ",
        f"**Scénario :** {title}  ",
        f"**Score scénario :** {data.get('scenario_score', '?')}/100  ",
        "",
        "## Résultats",
        f"| Métrique | Valeur |",
        f"|----------|--------|",
        f"| Images générées | {data.get('image_count', 0)} |",
        f"| Production succès | {data.get('production_success', 0)}/{data.get('production_success', 0) + data.get('production_failed', 0)} |",
        f"| Vidéo assemblée | {'✅' if data.get('video_path') else '❌'} |",
        f"| Arc émotionnel | {data.get('summary', {}).get('emotion_arc', '?')} |",
        f"| Mode Director | {data.get('summary', {}).get('mode', '?')} |",
        "",
    ]

    bus = data.get("bus", {})
    if bus.get("auto_sourcing.prompts_total"):
        lines += [
            "## Sourcing Autonome",
            f"- Prompts en bibliothèque : {bus['auto_sourcing.prompts_total']}",
            "",
        ]

    if data.get("images"):
        lines += ["## Images Archivées", ""]
        for i, img in enumerate(data["images"][:8]):
            lines.append(f"{i+1}. `{img['name']}` — {img['size_kb']} KB")
        lines.append("")

    if data.get("video_path"):
        lines += [
            "## Export Vidéo",
            f"```",
            data["video_path"],
            "```",
            "",
        ]

    lines += [
        "---",
        f"*Généré par session_reporter.py — Ov3rLoRd V1.60*",
    ]

    return "\n".join(lines)


def generate_report(run_id: str, state: dict,
                    archive_dir: Path = None,
                    logger: logging.Logger = None) -> dict:
    """
    Point d'entrée principal.
    Collecte, génère, sauvegarde JSON + MD, met à jour l'historique.
    """
    log = logger or logging.getLogger("session_reporter")
    log.info(f"[REPORTER] Génération rapport run={run_id}")

    REPORTS_DIR.mkdir(parents=True, exist_ok=True)

    data = collect_run_data(run_id, state, archive_dir=archive_dir, logger=log)
    md   = generate_markdown_report(data)

    ts        = datetime.now().strftime("%Y%m%d_%H%M%S")
    json_path = REPORTS_DIR / f"{ts}_{run_id}.json"
    md_path   = REPORTS_DIR / f"{ts}_{run_id}.md"

    json_path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding='utf-8')
    md_path.write_text(md, encoding='utf-8')

    # Historique
    history = _load_history()
    history.append({
        "run_id":       run_id,
        "timestamp":    data["timestamp"],
        "scenario":     data.get("scenario_title", "?"),
        "images":       data.get("image_count", 0),
        "video":        bool(data.get("video_path")),
        "score":        data.get("scenario_score", 0),
        "report_json":  str(json_path),
        "report_md":    str(md_path),
    })
    _save_history(history)

    log.info(f"[REPORTER] OK — JSON: {json_path.name} | MD: {md_path.name}")
    log.info(f"[REPORTER] Résumé : {data['image_count']} images | vidéo: {bool(data.get('video_path'))}")

    if BUS_OK:
        try:
            get_bus().write("reporter.last_report_md",   str(md_path),  agent_id="reporter")
            get_bus().write("reporter.last_report_json",  str(json_path), agent_id="reporter")
        except Exception:
            pass

    return data


if __name__ == "__main__":
    import sys, io
    if hasattr(sys.stdout, "buffer"):
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    logging.basicConfig(level=logging.INFO)
    print("Session Reporter V1.60 — test autonome")
    history = _load_history()
    print(f"Runs en historique : {len(history)}")
    for h in history[-3:]:
        print(f"  {h['timestamp'][:19]} | {h['scenario']} | {h['images']} images")

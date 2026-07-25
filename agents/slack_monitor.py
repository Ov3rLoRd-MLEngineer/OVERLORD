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
agents/slack_monitor.py — Moniteur de Slack PERT V1.70
Mesure les temps réels par bloc et calcule le slack (marge) de chaque tâche.
Identifie où gagner du temps sans risque sur le chemin critique.

PERT Slack = Earliest Finish - Latest Finish pour chaque tâche.
  slack = 0  → chemin critique (toute amélioration ici = gain global)
  slack > 0  → marge disponible (peut attendre sans bloquer)

Usage :
  from agents.slack_monitor import get_monitor
  mon = get_monitor()
  with mon.measure("scenario"):
      run_scenario(...)
  mon.report()
"""

import json
import logging
import threading
import time
from collections import defaultdict
from datetime import datetime
from pathlib import Path

import sys
import io
if hasattr(sys.stdout, 'buffer') and getattr(sys.stdout, 'encoding','').lower() != 'utf-8':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

try:
    from agents.context_bus import get_bus
    BUS_OK = True
except ImportError:
    BUS_OK = False

SLACK_LOG  = Path("workspace/logs/slack_monitor.jsonl")
SLACK_DIR  = Path("workspace/reports/pert")

# Durées PERT estimées (secondes) — mises à jour avec les mesures réelles
PERT_ESTIMATES = {
    "sourcing":       30,
    "scenario":       45,
    "storyboard":     30,
    "quality_gate":    5,
    "prompt_engineer": 60,
    "production":     360,
    "postprod":        30,
    "reporter":         5,
    "style":            5,
    "narrative":        3,
}

# Chemin critique théorique (tâches séquentielles obligatoires)
CRITICAL_PATH = [
    "sourcing", "scenario", "storyboard",
    "quality_gate", "prompt_engineer", "production",
    "postprod", "reporter"
]

# Tâches parallèles (peuvent tourner en même temps)
PARALLEL_TASKS = {
    "style":     "storyboard",     # pendant storyboard
    "narrative": "scenario",       # pendant scenario
}


class TaskMeasure:
    def __init__(self, task_name: str, monitor: "SlackMonitor"):
        self.task    = task_name
        self.monitor = monitor
        self.start   = None

    def __enter__(self):
        self.start = time.time()
        return self

    def __exit__(self, *args):
        duration = time.time() - self.start
        self.monitor._record(self.task, duration)


class SlackMonitor:
    """Moniteur PERT de slack pour le pipeline Ov3rLoRd."""

    def __init__(self):
        self._lock    = threading.Lock()
        self._history = defaultdict(list)  # task → [durations]
        self._run_log: list = []
        self.log      = logging.getLogger("slack_monitor")
        self._load_history()

    def _load_history(self):
        if not SLACK_LOG.exists():
            return
        try:
            for line in SLACK_LOG.read_text(encoding='utf-8',
                                             errors='replace').splitlines()[-200:]:
                try:
                    r = json.loads(line)
                    self._history[r["task"]].append(r["duration"])
                except Exception:
                    pass
        except Exception:
            pass

    def _record(self, task: str, duration: float):
        """Enregistre une mesure."""
        with self._lock:
            self._history[task].append(duration)
            record = {
                "ts":       datetime.now().isoformat(),
                "task":     task,
                "duration": round(duration, 2),
                "estimate": PERT_ESTIMATES.get(task, 0),
                "delta":    round(duration - PERT_ESTIMATES.get(task, 0), 2),
            }
            self._run_log.append(record)

        SLACK_LOG.parent.mkdir(parents=True, exist_ok=True)
        with open(SLACK_LOG, 'a', encoding='utf-8') as f:
            f.write(json.dumps(record, ensure_ascii=False) + '\n')

        if BUS_OK:
            try:
                get_bus().write(f"pert.{task}_duration",
                                round(duration, 1), agent_id="slack_monitor")
            except Exception:
                pass

        self.log.debug(
            f"[PERT] {task} : {duration:.1f}s "
            f"(estimé {PERT_ESTIMATES.get(task, '?')}s, "
            f"delta {duration - PERT_ESTIMATES.get(task, 0):+.1f}s)"
        )

    def measure(self, task_name: str) -> TaskMeasure:
        """Context manager pour mesurer une tâche."""
        return TaskMeasure(task_name, self)

    def get_mean(self, task: str) -> float:
        """Retourne la durée moyenne mesurée d'une tâche."""
        history = self._history.get(task, [])
        if not history:
            return float(PERT_ESTIMATES.get(task, 60))
        return sum(history) / len(history)

    def calculate_slack(self) -> dict:
        """
        Calcule le slack PERT pour chaque tâche.
        Retourne un dict task → {duration, estimate, slack, on_critical_path}
        """
        # Durées réelles ou estimées
        durations = {task: self.get_mean(task) for task in PERT_ESTIMATES}

        # Durée totale chemin critique
        critical_total = sum(durations[t] for t in CRITICAL_PATH
                             if t in durations)

        # Earliest/Latest start pour chaque tâche
        es = {}  # Earliest Start
        ef = {}  # Earliest Finish
        ls = {}  # Latest Start
        lf = {}  # Latest Finish

        # Forward pass (ES/EF)
        t = 0
        for task in CRITICAL_PATH:
            es[task] = t
            ef[task] = t + durations.get(task, 0)
            t = ef[task]

        # Tâches parallèles
        for task, parallel_with in PARALLEL_TASKS.items():
            if parallel_with in es:
                es[task] = es[parallel_with]
                ef[task] = es[task] + durations.get(task, 0)

        # Backward pass (LF/LS)
        project_end = critical_total
        t = project_end
        for task in reversed(CRITICAL_PATH):
            lf[task] = t
            ls[task] = t - durations.get(task, 0)
            t = ls[task]

        for task, parallel_with in PARALLEL_TASKS.items():
            if parallel_with in lf:
                lf[task] = lf[parallel_with]
                ls[task] = lf[task] - durations.get(task, 0)

        # Calcul slack
        result = {}
        for task in durations:
            duration = durations[task]
            slack    = lf.get(task, 0) - ef.get(task, 0) if task in ef else 0
            on_cp    = task in CRITICAL_PATH and abs(slack) < 1.0

            result[task] = {
                "duration_real": round(duration, 1),
                "duration_est":  PERT_ESTIMATES.get(task, 0),
                "delta":         round(duration - PERT_ESTIMATES.get(task, 0), 1),
                "slack":         round(slack, 1),
                "on_critical_path": on_cp,
                "measures":      len(self._history.get(task, [])),
            }

        return result

    def report(self, print_to_console: bool = True) -> dict:
        """Génère le rapport PERT complet."""
        slack_data = self.calculate_slack()
        total_time = sum(d["duration_real"] for d in slack_data.values()
                         if d.get("on_critical_path"))

        report = {
            "timestamp":      datetime.now().isoformat(),
            "total_critical": round(total_time, 1),
            "tasks":          slack_data,
            "bottleneck":     max(
                (t for t in slack_data if slack_data[t]["on_critical_path"]),
                key=lambda t: slack_data[t]["duration_real"],
                default="unknown"
            ),
        }

        if print_to_console:
            print(f"\n{'═'*65}")
            print(f"  RAPPORT PERT SLACK — {datetime.now().strftime('%Y-%m-%d %H:%M')}")
            print(f"  Temps chemin critique total : {total_time:.0f}s "
                  f"({total_time//60:.0f}min{total_time%60:.0f}s)")
            print(f"{'═'*65}")
            print(f"  {'Tâche':20s} {'Réel':>8s} {'Estimé':>8s} {'Delta':>8s} "
                  f"{'Slack':>8s} CP")
            print(f"{'─'*65}")

            for task, data in sorted(
                slack_data.items(),
                key=lambda x: (not x[1]["on_critical_path"], x[1]["duration_real"])
            ):
                cp_flag = "⚡" if data["on_critical_path"] else "  "
                delta   = data["delta"]
                delta_s = f"+{delta:.0f}" if delta > 0 else f"{delta:.0f}"
                slack   = data["slack"]
                print(
                    f"  {task:20s} {data['duration_real']:>7.0f}s "
                    f"{data['duration_est']:>7.0f}s "
                    f"{delta_s:>8s}s "
                    f"{slack:>7.0f}s {cp_flag}"
                )

            bn = report["bottleneck"]
            if bn in slack_data:
                print(f"\n  🔴 Goulot principal : {bn} "
                      f"({slack_data[bn]['duration_real']:.0f}s)")
            print(f"{'═'*65}")

        # Sauvegarder
        SLACK_DIR.mkdir(parents=True, exist_ok=True)
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        rpath = SLACK_DIR / f"pert_report_{ts}.json"
        rpath.write_text(
            json.dumps(report, indent=2, ensure_ascii=False),
            encoding='utf-8'
        )

        if BUS_OK:
            try:
                bus = get_bus()
                bus.write("pert.total_time",  total_time, agent_id="slack_monitor")
                bus.write("pert.bottleneck",  report["bottleneck"], agent_id="slack_monitor")
            except Exception:
                pass

        return report


# Singleton
_monitor: SlackMonitor | None = None

def get_monitor() -> SlackMonitor:
    global _monitor
    if _monitor is None:
        _monitor = SlackMonitor()
    return _monitor


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)

    mon = get_monitor()
    print("=== Slack Monitor V1.70 ===")
    print("Simulation d'un run complet...")

    # Simuler des mesures réalistes RTX 2070
    import random
    measures = {
        "sourcing":        random.uniform(28, 35),
        "scenario":        random.uniform(38, 55),
        "storyboard":      random.uniform(25, 38),
        "quality_gate":    random.uniform(3, 7),
        "prompt_engineer": random.uniform(50, 75),
        "production":      random.uniform(320, 420),
        "postprod":        random.uniform(25, 40),
        "reporter":        random.uniform(3, 8),
        "style":           random.uniform(4, 7),
        "narrative":       random.uniform(2, 5),
    }
    for task, duration in measures.items():
        mon._record(task, duration)

    mon.report()

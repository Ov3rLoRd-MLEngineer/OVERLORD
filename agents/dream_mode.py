"""
agents/dream_mode.py — Mode Autonome Nuit V1.70
Lance le pipeline en boucle infinie sans supervision humaine.
Gère les crashs, ajuste les paramètres selon les performances,
alerte par Telegram si problème, s'arrête proprement le matin.

Usage :
  python agents/dream_mode.py                         # boucle infinie
  python agents/dream_mode.py --runs 10               # 10 runs puis stop
  python agents/dream_mode.py --stop-at 08:00         # s'arrête à 8h
  python agents/dream_mode.py --universes-file u.txt  # liste d'univers
"""

import argparse
import json
import logging
import random
import subprocess
import sys
import time
import io
from datetime import datetime, timedelta
from pathlib import Path

if hasattr(sys.stdout, 'buffer'):
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

try:
    from agents.context_bus import get_bus
    BUS_OK = True
except ImportError:
    BUS_OK = False

try:
    from agents.config_manager import get_config
    CFG_OK = True
except ImportError:
    CFG_OK = False

DREAM_LOG    = Path("workspace/logs/dream_mode.jsonl")
DREAM_STATE  = Path("workspace/dream_state.json")

# Univers par défaut — rotation automatique
DEFAULT_UNIVERSES = [
    "evangelion battle mecha girl",
    "rei ayanami contemplation",
    "asuka langley combat intense",
    "evangelion unit 01 awakening",
    "mari makinami cheerful action",
    "evangelion angels tokyo3",
    "neon genesis evangelion drama",
    "evangelion yuri romance",
]

log = logging.getLogger("dream_mode")


def _notify(msg: str):
    """Notification Telegram si configuré."""
    if not CFG_OK:
        return
    try:
        c     = get_config()
        token = c.get("telegram.token", "")
        chat  = c.get("telegram.chat_id", "")
        if not token or not chat:
            return
        import urllib.request
        url  = f"https://api.telegram.org/bot{token}/sendMessage"
        data = json.dumps({"chat_id": chat, "text": f"🔮 DreamMode: {msg}"}).encode()
        req  = urllib.request.Request(url, data=data,
                                       headers={"Content-Type": "application/json"})
        urllib.request.urlopen(req, timeout=10)
    except Exception:
        pass


def _load_state() -> dict:
    if DREAM_STATE.exists():
        try:
            return json.loads(DREAM_STATE.read_text(encoding='utf-8'))
        except Exception:
            pass
    return {"total_runs": 0, "successes": 0, "failures": 0,
            "started_at": None, "last_universe": None}


def _save_state(state: dict):
    DREAM_STATE.parent.mkdir(parents=True, exist_ok=True)
    DREAM_STATE.write_text(json.dumps(state, indent=2, ensure_ascii=False), encoding='utf-8')


def _should_stop(stop_at: str | None, max_runs: int, total_runs: int) -> bool:
    if max_runs > 0 and total_runs >= max_runs:
        return True
    if stop_at:
        now  = datetime.now()
        h, m = map(int, stop_at.split(":"))
        stop = now.replace(hour=h, minute=m, second=0, microsecond=0)
        if stop <= now:
            stop += timedelta(days=1)  # Demain si déjà passé
        if datetime.now() >= stop:
            return True
    return False


def _run_pipeline(universe: str, use_lib: bool = False) -> dict:
    """Lance un run pipeline et retourne le résultat."""
    cmd = [sys.executable, "maestro.py",
           "--media-type", "anime",
           "--universe", universe]
    if use_lib:
        cmd.append("--use-prompt-library")

    log.info(f"[DREAM] Lancement : {universe[:50]}")
    t0 = time.time()

    try:
        result = subprocess.run(
            cmd, capture_output=True, text=True,
            encoding="utf-8", errors="replace",
            timeout=900,  # 15min max par run
            cwd=str(Path.cwd())
        )
        duration = time.time() - t0
        success  = result.returncode == 0

        # Extraire les métriques des logs
        stdout = result.stdout or ""
        images = stdout.count("PASS |") if "PASS |" in stdout else 0
        if "8/8 succes" in stdout or "8/8 success" in stdout:
            images = 8

        return {
            "success":  success,
            "duration": round(duration, 1),
            "universe": universe,
            "images":   images,
            "returncode": result.returncode,
            "timestamp": datetime.now().isoformat(),
        }

    except subprocess.TimeoutExpired:
        log.error(f"[DREAM] Timeout (900s) pour : {universe}")
        return {"success": False, "duration": 900, "universe": universe,
                "images": 0, "returncode": -1, "timestamp": datetime.now().isoformat(),
                "error": "timeout"}
    except Exception as e:
        log.error(f"[DREAM] Exception : {e}")
        return {"success": False, "duration": 0, "universe": universe,
                "images": 0, "returncode": -2, "timestamp": datetime.now().isoformat(),
                "error": str(e)}


def run_dream_mode(universes: list = None, max_runs: int = 0,
                   stop_at: str = None, use_lib: bool = True,
                   cooldown_s: int = 30):
    """
    Boucle principale du mode autonome.
    Tourne jusqu'à max_runs, stop_at, ou Ctrl+C.
    """
    universes = universes or DEFAULT_UNIVERSES
    state     = _load_state()

    if not state.get("started_at"):
        state["started_at"] = datetime.now().isoformat()

    log.info(f"[DREAM] Mode autonome démarré")
    log.info(f"[DREAM] Univers disponibles : {len(universes)}")
    log.info(f"[DREAM] Runs max  : {max_runs or '∞'}")
    log.info(f"[DREAM] Stop à    : {stop_at or 'jamais'}")
    _notify(f"Démarrage dream mode — {len(universes)} univers, {max_runs or '∞'} runs")

    run_index = 0

    try:
        while True:
            if _should_stop(stop_at, max_runs, state["total_runs"]):
                log.info("[DREAM] Condition d'arrêt atteinte")
                break

            # Choisir l'univers (rotation + aléatoire)
            universe = universes[run_index % len(universes)]
            run_index += 1

            # Lancer le run
            result = _run_pipeline(universe, use_lib=use_lib)
            state["total_runs"] += 1

            if result["success"]:
                state["successes"] += 1
                state["last_universe"] = universe
                log.info(
                    f"[DREAM] Run {state['total_runs']} OK | "
                    f"{result['images']} images | {result['duration']}s | "
                    f"{universe[:40]}"
                )
                if state["total_runs"] % 5 == 0:
                    _notify(
                        f"✅ {state['successes']}/{state['total_runs']} runs OK — "
                        f"dernière : {universe[:30]}"
                    )
            else:
                state["failures"] += 1
                log.error(
                    f"[DREAM] Run {state['total_runs']} ÉCHOUÉ | "
                    f"code={result.get('returncode')} | {universe[:40]}"
                )
                if state["failures"] >= 3 and state["failures"] % 3 == 0:
                    _notify(f"⚠ {state['failures']} échecs consécutifs — vérifier le pipeline")
                # Pause plus longue après échec
                time.sleep(cooldown_s * 2)
                continue

            # Publier sur le bus
            if BUS_OK:
                try:
                    bus = get_bus()
                    bus.write("dream.total_runs",  state["total_runs"], agent_id="dream")
                    bus.write("dream.successes",   state["successes"],  agent_id="dream")
                    bus.write("dream.failures",    state["failures"],   agent_id="dream")
                    bus.write("dream.last_universe", universe,          agent_id="dream")
                except Exception:
                    pass

            # Log JSONL
            DREAM_LOG.parent.mkdir(parents=True, exist_ok=True)
            with open(DREAM_LOG, 'a', encoding='utf-8') as f:
                f.write(json.dumps(result, ensure_ascii=False) + '\n')

            _save_state(state)

            # Cooldown entre runs
            log.info(f"[DREAM] Pause {cooldown_s}s avant prochain run...")
            time.sleep(cooldown_s)

    except KeyboardInterrupt:
        log.info("[DREAM] Interruption manuelle")
        _notify("🛑 Dream mode interrompu manuellement")

    # Rapport final
    _save_state(state)
    total   = state["total_runs"]
    success = state["successes"]
    rate    = round(success / max(total, 1) * 100, 1)

    log.info(f"[DREAM] Bilan final :")
    log.info(f"  Runs total    : {total}")
    log.info(f"  Succès        : {success} ({rate}%)")
    log.info(f"  Échecs        : {state['failures']}")
    if state.get("started_at"):
        started = datetime.fromisoformat(state["started_at"])
        elapsed = datetime.now() - started
        log.info(f"  Durée totale  : {str(elapsed).split('.')[0]}")

    _notify(f"🏁 Dream mode terminé : {success}/{total} ({rate}%)")
    return state


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Ov3rLoRd Dream Mode V1.70")
    parser.add_argument("--runs",           type=int, default=0,
                        help="Nombre de runs (0=infini)")
    parser.add_argument("--stop-at",        type=str, default=None,
                        help="Heure d'arrêt HH:MM (ex: 08:00)")
    parser.add_argument("--universes-file", type=str, default=None,
                        help="Fichier texte avec un univers par ligne")
    parser.add_argument("--cooldown",       type=int, default=30,
                        help="Pause entre runs en secondes")
    parser.add_argument("--no-lib",         action="store_true",
                        help="Ne pas utiliser la prompt library")
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)-8s] %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S"
    )

    universes = DEFAULT_UNIVERSES
    if args.universes_file and Path(args.universes_file).exists():
        lines = Path(args.universes_file).read_text(encoding='utf-8').splitlines()
        universes = [l.strip() for l in lines if l.strip() and not l.startswith('#')]
        print(f"Univers chargés depuis fichier : {len(universes)}")

    print(f"""
╔══════════════════════════════════════════╗
║  Ov3rLoRd Dream Mode V1.70              ║
║  {len(universes)} univers | {args.runs or '∞'} runs | stop={args.stop_at or 'jamais'}
║  Cooldown: {args.cooldown}s entre chaque run
╚══════════════════════════════════════════╝
Ctrl+C pour arrêter proprement.
""")

    run_dream_mode(
        universes=universes,
        max_runs=args.runs,
        stop_at=args.stop_at,
        use_lib=not args.no_lib,
        cooldown_s=args.cooldown,
    )

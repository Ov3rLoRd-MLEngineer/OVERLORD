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
agents/resource_scheduler.py — Scheduleur de Ressources V1.70
File d'attente prioritaire avec VRAM comme token partagé.
Évite les OOM quand dream_mode + auto_sourcing + lora_trainer tournent simultanément.

Principe :
  - Chaque agent déclare ses besoins VRAM avant de démarrer
  - Le scheduler accorde ou met en attente selon la VRAM disponible
  - Priorités : production > dream_mode > sourcing > training

Usage :
  from agents.resource_scheduler import get_scheduler
  sched = get_scheduler()
  token = sched.request("production", vram_gb=6.0)
  # ... faire le travail ...
  sched.release(token)
"""

import json
import logging
import threading
import time
from datetime import datetime
from pathlib import Path

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

SCHEDULE_LOG = Path("workspace/logs/resource_scheduler.jsonl")

# Priorités agents (plus bas = priorité plus haute)
AGENT_PRIORITIES = {
    "production":     0,   # génération ComfyUI — toujours prioritaire
    "quality_gate":   1,
    "quality_review": 1,
    "prompt_engineer":2,
    "dream_mode":     3,
    "postprod":       3,
    "music_synthesis":3,   # MusicGen — ADR-012, jamais concurrent de ComfyUI
    "auto_sourcing":  5,
    "narrative":      6,
    "lora_trainer":   8,   # très gourmand, toujours en dernier
    "default":        4,
}

# VRAM réservée par type de tâche (GB)
VRAM_ESTIMATES = {
    "production":     5.5,  # fabricatedXL_v70 + CLIP
    "lora_trainer":   8.0,  # entraînement kohya_ss
    "dream_mode":     5.5,
    "postprod":       1.0,
    "music_synthesis":4.0,  # MusicGen small (~300M, fp16 ~4Go — ADR-012
    "auto_sourcing":  0.5,
    "default":        2.0,
}


class ResourceToken:
    """Token accordé par le scheduler pour utiliser une ressource."""
    def __init__(self, agent: str, vram_gb: float, token_id: str):
        self.agent    = agent
        self.vram_gb  = vram_gb
        self.token_id = token_id
        self.acquired_at = datetime.now()
        self.released    = False

    def __repr__(self):
        return f"ResourceToken({self.agent}, {self.vram_gb}GB, {self.token_id})"


class ResourceScheduler:
    """Gestionnaire de ressources VRAM thread-safe."""

    def __init__(self, total_vram_gb: float = 8.0):
        self.total_vram   = total_vram_gb
        self._lock        = threading.Lock()
        self._tokens: dict[str, ResourceToken] = {}
        self._queue: list  = []  # (priority, agent, vram_gb, event)
        self._counter      = 0
        self.log           = logging.getLogger("resource_scheduler")

        # Lire la VRAM totale depuis config si disponible
        if CFG_OK:
            try:
                c = get_config()
                vram = c.get("gpu.vram_gb", total_vram_gb)
                self.total_vram = float(vram)
            except Exception:
                pass

    @property
    def vram_used(self) -> float:
        with self._lock:
            return sum(t.vram_gb for t in self._tokens.values() if not t.released)

    @property
    def vram_free(self) -> float:
        return max(0.0, self.total_vram - self.vram_used)

    def request(self, agent: str, vram_gb: float = None,
                timeout: float = 300.0) -> ResourceToken | None:
        """
        Demande un token de ressource.
        Bloque jusqu'à ce que la VRAM soit disponible ou timeout.
        Retourne le token ou None si timeout.
        """
        if vram_gb is None:
            vram_gb = VRAM_ESTIMATES.get(agent, VRAM_ESTIMATES["default"])

        priority = AGENT_PRIORITIES.get(agent, AGENT_PRIORITIES["default"])
        event    = threading.Event()

        with self._lock:
            self._counter += 1
            token_id = f"{agent}_{self._counter:04d}"

            # Si VRAM disponible immédiatement
            if self.vram_free >= vram_gb:
                token = ResourceToken(agent, vram_gb, token_id)
                self._tokens[token_id] = token
                self.log.info(
                    f"[SCHEDULER] ✓ {agent} — {vram_gb}GB accordé | "
                    f"utilisé: {self.vram_used:.1f}/{self.total_vram}GB"
                )
                self._log_event("acquired", agent, vram_gb)
                self._publish_bus()
                return token

            # Sinon mettre en file d'attente
            self._queue.append((priority, token_id, agent, vram_gb, event))
            self._queue.sort(key=lambda x: x[0])
            self.log.info(
                f"[SCHEDULER] ⏳ {agent} — {vram_gb}GB en attente | "
                f"libre: {self.vram_free:.1f}GB | queue: {len(self._queue)}"
            )

        # Attendre que la ressource soit libérée
        acquired = event.wait(timeout=timeout)
        if not acquired:
            # Retirer de la queue
            with self._lock:
                self._queue = [(p, tid, a, v, e)
                               for p, tid, a, v, e in self._queue
                               if tid != token_id]
            self.log.warning(f"[SCHEDULER] ✗ {agent} — timeout ({timeout}s)")
            return None

        with self._lock:
            token = ResourceToken(agent, vram_gb, token_id)
            self._tokens[token_id] = token
            self._log_event("acquired_after_wait", agent, vram_gb)
            self._publish_bus()
            return token

    def release(self, token: ResourceToken):
        """Libère un token et traite la file d'attente."""
        if token is None or token.released:
            return

        with self._lock:
            token.released = True
            held_secs = (datetime.now() - token.acquired_at).total_seconds()
            self.log.info(
                f"[SCHEDULER] ↩ {token.agent} libéré — "
                f"{token.vram_gb}GB pendant {held_secs:.0f}s"
            )
            self._log_event("released", token.agent, token.vram_gb, held_secs)

            # Traiter la file d'attente
            self._process_queue()
            self._publish_bus()

    def _process_queue(self):
        """Accorde les ressources aux agents en attente (appelé sous lock)."""
        to_remove = []
        for item in list(self._queue):
            priority, token_id, agent, vram_gb, event = item
            if self.vram_free >= vram_gb:
                to_remove.append(item)
                event.set()  # Réveiller le thread en attente
                self.log.info(f"[SCHEDULER] ↑ {agent} débloqué ({vram_gb}GB)")

        for item in to_remove:
            self._queue.remove(item)

    def _log_event(self, event_type: str, agent: str, vram_gb: float,
                   duration: float = None):
        SCHEDULE_LOG.parent.mkdir(parents=True, exist_ok=True)
        record = {
            "ts":       datetime.now().isoformat(),
            "event":    event_type,
            "agent":    agent,
            "vram_gb":  vram_gb,
            "vram_free": round(self.vram_free, 1),
            "queue_len": len(self._queue),
        }
        if duration is not None:
            record["duration_s"] = round(duration, 1)
        with open(SCHEDULE_LOG, 'a', encoding='utf-8') as f:
            f.write(json.dumps(record, ensure_ascii=False) + '\n')

    def _publish_bus(self):
        if BUS_OK:
            try:
                bus = get_bus()
                bus.write("scheduler.vram_used",  round(self.vram_used, 1),
                          agent_id="scheduler")
                bus.write("scheduler.vram_free",  round(self.vram_free, 1),
                          agent_id="scheduler")
                bus.write("scheduler.queue_len",  len(self._queue),
                          agent_id="scheduler")
                bus.write("scheduler.active_agents",
                          [t.agent for t in self._tokens.values() if not t.released],
                          agent_id="scheduler")
            except Exception:
                pass

    def status(self) -> dict:
        with self._lock:
            return {
                "total_vram": self.total_vram,
                "vram_used":  round(self.vram_used, 1),
                "vram_free":  round(self.vram_free, 1),
                "active":     [t.agent for t in self._tokens.values()
                               if not t.released],
                "queue":      [a for _, _, a, _, _ in self._queue],
            }

    def context_manager(self, agent: str, vram_gb: float = None):
        """Context manager pour usage avec 'with'."""
        return _SchedulerContext(self, agent, vram_gb)


class _SchedulerContext:
    def __init__(self, scheduler: ResourceScheduler, agent: str, vram_gb: float):
        self._sched  = scheduler
        self._agent  = agent
        self._vram   = vram_gb
        self._token  = None

    def __enter__(self) -> ResourceToken | None:
        self._token = self._sched.request(self._agent, self._vram)
        return self._token

    def __exit__(self, *args):
        if self._token:
            self._sched.release(self._token)


# ── Singleton ─────────────────────────────────────────────────────────
_scheduler: ResourceScheduler | None = None
_sched_lock = threading.Lock()

def get_scheduler(total_vram_gb: float = None) -> ResourceScheduler:
    global _scheduler
    with _sched_lock:
        if _scheduler is None:
            vram = total_vram_gb or 8.0
            if CFG_OK:
                try:
                    vram = float(get_config().get("gpu.vram_gb", vram))
                except Exception:
                    pass
            _scheduler = ResourceScheduler(total_vram_gb=vram)
    return _scheduler


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO,
                        format="%(asctime)s [%(levelname)s] %(message)s")

    print("=== Resource Scheduler V1.70 ===")
    sched = get_scheduler(total_vram_gb=8.0)
    print(f"VRAM totale : {sched.total_vram}GB")
    print(f"Statut      : {sched.status()}")

    # Test : deux agents simultanés
    import threading

    def agent_task(name, vram, duration):
        print(f"[{name}] Demande {vram}GB...")
        with sched.context_manager(name, vram) as token:
            if token:
                print(f"[{name}] Token accordé — travail pendant {duration}s")
                time.sleep(duration)
                print(f"[{name}] Terminé")
            else:
                print(f"[{name}] Timeout !")

    t1 = threading.Thread(target=agent_task, args=("production", 5.5, 3))
    t2 = threading.Thread(target=agent_task, args=("lora_trainer", 8.0, 2))
    t3 = threading.Thread(target=agent_task, args=("postprod", 1.0, 1))

    t1.start()
    time.sleep(0.1)
    t2.start()  # devra attendre (VRAM insuffisante)
    t3.start()  # peut passer en parallèle de production

    t1.join(); t2.join(); t3.join()
    print(f"\nStatut final : {sched.status()}")

"""
agents/session_manager.py — Gestionnaire de Sessions Multi-Séries V1.47
Gère plusieurs séries en parallèle, priorise les jobs GPU, reprend après crash.

Usage :
    from agents.session_manager import SessionManager
    mgr = SessionManager()
    sid = mgr.create_session("Dragon Ball Ov3rLoRd", media_type="anime", priority=1)
    mgr.queue_episode(sid, episode=1, universe="Dragon Ball Super Broly")
    mgr.start_scheduler()
"""

import json
import logging
import threading
import time
import subprocess
import sys
from pathlib import Path
from datetime import datetime
from enum import Enum

log = logging.getLogger("session_manager")
SESSIONS_DIR = Path("workspace/sessions")

class SessionStatus(Enum):
    IDLE      = "idle"
    QUEUED    = "queued"
    RUNNING   = "running"
    PAUSED    = "paused"
    COMPLETED = "completed"
    FAILED    = "failed"

class EpisodeStatus(Enum):
    PENDING   = "pending"
    RUNNING   = "running"
    DONE      = "done"
    FAILED    = "failed"
    SKIPPED   = "skipped"


class Session:
    def __init__(self, session_id: str, series: str, media_type: str = "anime",
                 priority: int = 5):
        self.id        = session_id
        self.series    = series
        self.media_type= media_type
        self.priority  = priority  # 1=haute, 10=basse
        self.status    = SessionStatus.IDLE
        self.episodes  = []
        self.created   = datetime.now().isoformat()
        self.stats     = {"completed":0,"failed":0,"total_duration_s":0}

    def to_dict(self) -> dict:
        return {
            "id": self.id, "series": self.series,
            "media_type": self.media_type, "priority": self.priority,
            "status": self.status.value,
            "episodes": self.episodes,
            "created": self.created, "stats": self.stats,
        }


class SessionManager:
    """Gère plusieurs sessions de production en parallèle."""

    def __init__(self, max_concurrent: int = 1, logger: logging.Logger = None):
        self.log            = logger or log
        self.max_concurrent = max_concurrent
        self._sessions      = {}
        self._lock          = threading.Lock()
        self._scheduler_thr = None
        self._running       = False
        SESSIONS_DIR.mkdir(parents=True, exist_ok=True)
        self._load_sessions()

    def _load_sessions(self):
        for f in SESSIONS_DIR.glob("*.json"):
            try:
                data = json.loads(f.read_text(encoding="utf-8"))
                sid  = data["id"]
                s    = Session(sid, data["series"], data.get("media_type","anime"),
                               data.get("priority",5))
                s.status   = SessionStatus(data.get("status","idle"))
                s.episodes = data.get("episodes",[])
                s.stats    = data.get("stats",{})
                self._sessions[sid] = s
                # Remettre en queue les sessions interrompues
                if s.status == SessionStatus.RUNNING:
                    s.status = SessionStatus.QUEUED
            except Exception:
                pass
        self.log.info(f"[SESSION] {len(self._sessions)} sessions chargées")

    def _save_session(self, s: Session):
        path = SESSIONS_DIR / f"{s.id}.json"
        path.write_text(json.dumps(s.to_dict(), indent=2, ensure_ascii=False), encoding="utf-8")

    def create_session(self, series: str, media_type: str = "anime",
                       priority: int = 5) -> str:
        """Crée une nouvelle session de production."""
        import hashlib
        sid = f"sess_{hashlib.md5(f'{series}{datetime.now()}'.encode()).hexdigest()[:8]}"
        with self._lock:
            s = Session(sid, series, media_type, priority)
            self._sessions[sid] = s
            self._save_session(s)
        self.log.info(f"[SESSION] ✓ Créée : {series} ({sid})")
        return sid

    def queue_episode(self, session_id: str, episode: int,
                      universe: str = "", extra_args: dict = None) -> bool:
        """Ajoute un épisode à la file d'attente d'une session."""
        with self._lock:
            if session_id not in self._sessions:
                return False
            s = self._sessions[session_id]
            ep_data = {
                "episode":    episode,
                "universe":   universe,
                "extra_args": extra_args or {},
                "status":     EpisodeStatus.PENDING.value,
                "queued_at":  datetime.now().isoformat(),
                "run_id":     None,
                "duration_s": None,
            }
            s.episodes.append(ep_data)
            if s.status == SessionStatus.IDLE:
                s.status = SessionStatus.QUEUED
            self._save_session(s)
        self.log.info(f"[SESSION] Épisode {episode} ajouté à {session_id}")
        return True

    def pause_session(self, session_id: str):
        with self._lock:
            if session_id in self._sessions:
                self._sessions[session_id].status = SessionStatus.PAUSED
                self._save_session(self._sessions[session_id])

    def resume_session(self, session_id: str):
        with self._lock:
            if session_id in self._sessions:
                s = self._sessions[session_id]
                if s.status == SessionStatus.PAUSED:
                    s.status = SessionStatus.QUEUED
                    self._save_session(s)

    def get_queue(self) -> list:
        """Retourne la file triée par priorité."""
        with self._lock:
            queued = [s for s in self._sessions.values()
                      if s.status == SessionStatus.QUEUED]
            return sorted(queued, key=lambda s: s.priority)

    def start_scheduler(self, check_interval: int = 30):
        """Lance le scheduler en arrière-plan."""
        if self._scheduler_thr and self._scheduler_thr.is_alive():
            return
        self._running = True
        self._scheduler_thr = threading.Thread(
            target=self._scheduler_loop,
            args=(check_interval,), daemon=True
        )
        self._scheduler_thr.start()
        self.log.info(f"[SESSION] Scheduler démarré (intervalle {check_interval}s)")

    def stop_scheduler(self):
        self._running = False

    def _scheduler_loop(self, interval: int):
        while self._running:
            running_count = sum(1 for s in self._sessions.values()
                                if s.status == SessionStatus.RUNNING)
            if running_count < self.max_concurrent:
                queue = self.get_queue()
                for session in queue:
                    if running_count >= self.max_concurrent:
                        break
                    self._run_next_episode(session)
                    running_count += 1
            time.sleep(interval)

    def _run_next_episode(self, session: Session):
        """Lance le prochain épisode en attente d'une session."""
        pending = [ep for ep in session.episodes
                   if ep["status"] == EpisodeStatus.PENDING.value]
        if not pending:
            session.status = SessionStatus.COMPLETED
            self._save_session(session)
            return

        ep = pending[0]

        def _execute():
            ep["status"]   = EpisodeStatus.RUNNING.value
            ep["started_at"]= datetime.now().isoformat()
            session.status = SessionStatus.RUNNING
            self._save_session(session)

            start = time.time()
            try:
                cmd = [
                    sys.executable, "maestro.py",
                    "--media-type", session.media_type,
                    "--universe",   ep.get("universe",""),
                ]
                result = subprocess.run(cmd, capture_output=True, timeout=1800)
                duration = int(time.time() - start)

                if result.returncode == 0:
                    ep["status"]     = EpisodeStatus.DONE.value
                    ep["duration_s"] = duration
                    session.stats["completed"] = session.stats.get("completed",0) + 1
                    session.stats["total_duration_s"] = session.stats.get("total_duration_s",0) + duration
                    self.log.info(f"[SESSION] ✓ Ep.{ep['episode']} terminé ({duration}s)")
                else:
                    ep["status"] = EpisodeStatus.FAILED.value
                    session.stats["failed"] = session.stats.get("failed",0) + 1
                    self.log.error(f"[SESSION] ✗ Ep.{ep['episode']} échoué")

            except subprocess.TimeoutExpired:
                ep["status"] = EpisodeStatus.FAILED.value
                self.log.error(f"[SESSION] Timeout Ep.{ep['episode']}")
            except Exception as e:
                ep["status"] = EpisodeStatus.FAILED.value
                self.log.error(f"[SESSION] Exception : {e}")
            finally:
                remaining = [e for e in session.episodes
                             if e["status"] == EpisodeStatus.PENDING.value]
                session.status = SessionStatus.QUEUED if remaining else SessionStatus.COMPLETED
                self._save_session(session)

        threading.Thread(target=_execute, daemon=True).start()

    def status_report(self) -> dict:
        with self._lock:
            return {
                "sessions": len(self._sessions),
                "running":  sum(1 for s in self._sessions.values() if s.status==SessionStatus.RUNNING),
                "queued":   sum(1 for s in self._sessions.values() if s.status==SessionStatus.QUEUED),
                "completed":sum(1 for s in self._sessions.values() if s.status==SessionStatus.COMPLETED),
                "details":  [s.to_dict() for s in sorted(
                    self._sessions.values(), key=lambda x:x.priority)]
            }

    def print_status(self):
        report = self.status_report()
        print(f"\n{'═'*55}")
        print(f"  Ov3rLoRd Session Manager V1.47")
        print(f"  Sessions: {report['sessions']} | Running: {report['running']} | Queued: {report['queued']}")
        print(f"{'─'*55}")
        for s in report["details"]:
            ep_done    = sum(1 for ep in s["episodes"] if ep["status"]=="done")
            ep_total   = len(s["episodes"])
            status_col = {"running":"✓","queued":"○","completed":"✓✓","failed":"✗","idle":"·","paused":"⏸"}.get(s["status"],"?")
            print(f"  {status_col} [{s['priority']}] {s['series'][:30]:<30} {ep_done}/{ep_total} eps")
        print(f"{'═'*55}\n")


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    mgr = SessionManager(max_concurrent=1)
    sid1 = mgr.create_session("Dragon Ball Ov3rLoRd", "anime", priority=1)
    sid2 = mgr.create_session("One Piece Arc Wano",   "anime", priority=2)
    mgr.queue_episode(sid1, 1, "Dragon Ball Super Broly")
    mgr.queue_episode(sid1, 2, "Dragon Ball Super Broly")
    mgr.queue_episode(sid2, 1, "One Piece Wano Kuni")
    mgr.print_status()

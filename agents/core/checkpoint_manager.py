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
agents/checkpoint_manager.py — Gestionnaire de Sauvegarde V1.49
FIX V1.49 : datetime.utcnow() -> datetime.now(tz=timezone.utc).
Publie l'etat du checkpoint sur le context_bus.
"""

import json
import logging
import signal
import time
import shutil
from pathlib import Path
from datetime import datetime, timezone
from enum import Enum

try:
    from agents.context_bus import get_bus
    BUS_OK = True
except ImportError:
    BUS_OK = False

CHECKPOINT_DIR  = Path("workspace/checkpoints")
MAX_CHECKPOINTS = 10


class CheckpointState(Enum):
    EMPTY       = "empty"
    SOURCING    = "sourcing"
    SCENARIO    = "scenario"
    STORYBOARD  = "storyboard"
    PRODUCTION  = "production"
    POSTPROD    = "postprod"
    COMPLETED   = "completed"
    INTERRUPTED = "interrupted"
    FAILED      = "failed"


BLOCK_ORDER = [
    CheckpointState.SOURCING, CheckpointState.SCENARIO,
    CheckpointState.STORYBOARD, CheckpointState.PRODUCTION,
    CheckpointState.POSTPROD,
]


class Checkpoint:

    def __init__(self, project_id: str, run_id: str):
        self.project_id = project_id
        self.run_id     = run_id
        # FIX : datetime.utcnow() -> datetime.now(tz=timezone.utc)
        self.created_at = datetime.now(tz=timezone.utc).isoformat()
        self.updated_at = self.created_at
        self.state      = CheckpointState.EMPTY
        self.config     = {}
        self.data       = {}
        self.completed  = []
        self.current    = None
        self.errors     = []
        self.metadata   = {}

    def to_dict(self) -> dict:
        return {
            "project_id": self.project_id,
            "run_id":     self.run_id,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "state":      self.state.value,
            "config":     self.config,
            "data":       self.data,
            "completed":  self.completed,
            "current":    self.current,
            "errors":     self.errors,
            "metadata":   self.metadata,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "Checkpoint":
        cp = cls(d["project_id"], d["run_id"])
        cp.created_at = d.get("created_at", "")
        cp.updated_at = d.get("updated_at", "")
        cp.state      = CheckpointState(d.get("state", "empty"))
        cp.config     = d.get("config",    {})
        cp.data       = d.get("data",      {})
        cp.completed  = d.get("completed", [])
        cp.current    = d.get("current")
        cp.errors     = d.get("errors",    [])
        cp.metadata   = d.get("metadata",  {})
        return cp


class CheckpointManager:

    def __init__(self, project_id: str, logger: logging.Logger = None):
        self.project_id = project_id
        self.log        = logger or logging.getLogger("checkpoint")
        self._current   = None
        self._autosave  = True
        self._dir       = CHECKPOINT_DIR / self._safe_name(project_id)
        self._dir.mkdir(parents=True, exist_ok=True)
        self._original_sigint = signal.getsignal(signal.SIGINT)
        signal.signal(signal.SIGINT, self._emergency_handler)

    def _safe_name(self, name: str) -> str:
        safe = "".join(c if c.isalnum() or c in "-_" else "_" for c in name)
        return safe[:50]

    def new_checkpoint(self, config: dict, run_id: str = None) -> Checkpoint:
        rid = run_id or f"run_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        cp  = Checkpoint(self.project_id, rid)
        cp.config   = config
        cp.metadata = {"hostname": self._get_hostname(),
                       "python":   self._get_python_version()}
        self._current = cp
        self._save_to_disk(cp)
        self.log.info(f"[CHECKPOINT] Nouveau checkpoint : {rid}")
        return cp

    def load_latest(self) -> "Checkpoint | None":
        checkpoints = self._list_checkpoints()
        if not checkpoints:
            self.log.info(f"[CHECKPOINT] Aucun checkpoint pour '{self.project_id}'")
            return None
        latest = checkpoints[-1]
        cp     = self._load_from_disk(latest)
        if cp:
            self._current = cp
            self.log.info(
                f"[CHECKPOINT] Charge : {cp.run_id} | "
                f"Etat : {cp.state.value} | "
                f"Blocs termines : {cp.completed}"
            )
        return cp

    def load_checkpoint(self, run_id: str) -> "Checkpoint | None":
        path = self._dir / f"{run_id}.json"
        return self._load_from_disk(path)

    def save_block(self, block_name: str, data: object,
                   state: CheckpointState = None):
        if not self._current:
            self.log.warning("[CHECKPOINT] Pas de checkpoint actif")
            return
        cp = self._current
        cp.data[block_name] = self._serialize(data)
        # FIX : datetime.utcnow() -> datetime.now(tz=timezone.utc)
        cp.updated_at       = datetime.now(tz=timezone.utc).isoformat()
        if block_name not in cp.completed:
            cp.completed.append(block_name)
        cp.current = block_name
        cp.state   = state or self._block_to_state(block_name)
        self._save_to_disk(cp)

        # Publier sur le bus
        if BUS_OK:
            try:
                bus = get_bus()
                bus.write("checkpoint.last_block",   block_name,       agent_id="checkpoint")
                bus.write("checkpoint.completed",    cp.completed,     agent_id="checkpoint")
                bus.write("checkpoint.state",        cp.state.value,   agent_id="checkpoint")
                bus.write("checkpoint.run_id",       cp.run_id,        agent_id="checkpoint")
            except Exception:
                pass

        self.log.info(f"[CHECKPOINT] OK Bloc '{block_name}' sauvegarde ({len(cp.completed)}/5 blocs)")

    def save_block_start(self, block_name: str):
        if not self._current: return
        self._current.current    = block_name
        self._current.updated_at = datetime.now(tz=timezone.utc).isoformat()
        self._save_to_disk(self._current)
        self.log.debug(f"[CHECKPOINT] Debut bloc '{block_name}'")

    def save_error(self, block_name: str, error: str):
        if not self._current: return
        self._current.errors.append({
            "block": block_name, "error": error,
            "time": datetime.now(tz=timezone.utc).isoformat(),
        })
        self._current.state = CheckpointState.FAILED
        self._save_to_disk(self._current)
        self.log.error(f"[CHECKPOINT] Erreur sauvegardee : {block_name} -> {error[:100]}")

    def mark_completed(self):
        if not self._current: return
        self._current.state      = CheckpointState.COMPLETED
        self._current.current    = None
        self._current.updated_at = datetime.now(tz=timezone.utc).isoformat()
        self._save_to_disk(self._current)
        self._cleanup_old_checkpoints()
        self.log.info(f"[CHECKPOINT] Pipeline complete : {self._current.run_id}")
        if BUS_OK:
            try:
                get_bus().write("checkpoint.state", "completed", agent_id="checkpoint")
            except Exception:
                pass

    def save_emergency(self):
        if not self._current: return
        self._current.state      = CheckpointState.INTERRUPTED
        self._current.updated_at = datetime.now(tz=timezone.utc).isoformat()
        self._save_to_disk(self._current)
        self.log.warning(
            f"[CHECKPOINT] Sauvegarde d'urgence : {self._current.run_id} | "
            f"Blocs termines : {self._current.completed}"
        )

    def analyze_resume(self, cp: "Checkpoint") -> dict:
        if not cp:
            return {"action": "start_fresh", "skip": [], "resume_from": None}

        completed = cp.completed
        current   = cp.current

        if cp.state == CheckpointState.COMPLETED:
            return {"action": "nothing",
                    "message": "Pipeline deja termine avec succes",
                    "skip": completed, "resume_from": None}

        all_blocks  = ["sourcing","scenario","storyboard","production","postprod"]
        resume_from = None
        for block in all_blocks:
            if block not in completed:
                resume_from = block
                break

        if current and current not in completed:
            resume_from = current

        message = (
            f"Reprise depuis '{resume_from}' "
            f"({len(completed)}/5 blocs deja termines : {completed})"
        )
        return {
            "action":      "resume",
            "resume_from": resume_from,
            "skip":        completed,
            "data":        cp.data,
            "config":      cp.config,
            "message":     message,
            "run_id":      cp.run_id,
        }

    def get_resume_data(self, block_name: str):
        if not self._current: return None
        raw = self._current.data.get(block_name)
        return self._deserialize(raw) if raw is not None else None

    def list_checkpoints(self) -> list:
        paths  = self._list_checkpoints()
        result = []
        for path in paths:
            cp = self._load_from_disk(path)
            if cp:
                result.append({
                    "run_id":    cp.run_id,
                    "state":     cp.state.value,
                    "completed": cp.completed,
                    "updated":   cp.updated_at,
                    "has_error": len(cp.errors) > 0,
                })
        return result

    def delete_checkpoint(self, run_id: str) -> bool:
        path = self._dir / f"{run_id}.json"
        if path.exists():
            path.unlink()
            self.log.info(f"[CHECKPOINT] Supprime : {run_id}")
            return True
        return False

    def delete_all(self):
        for path in self._list_checkpoints():
            path.unlink()
        self.log.info(f"[CHECKPOINT] Tous les checkpoints supprimes pour '{self.project_id}'")

    def _list_checkpoints(self) -> list:
        return sorted(self._dir.glob("*.json"), key=lambda p: p.stat().st_mtime)

    def _save_to_disk(self, cp: Checkpoint):
        path = self._dir / f"{cp.run_id}.json"
        try:
            path.write_text(
                json.dumps(cp.to_dict(), indent=2, ensure_ascii=False, default=str),
                encoding="utf-8"
            )
        except Exception as e:
            self.log.error(f"[CHECKPOINT] Erreur ecriture : {e}")

    def _load_from_disk(self, path: Path) -> "Checkpoint | None":
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            return Checkpoint.from_dict(data)
        except Exception as e:
            self.log.error(f"[CHECKPOINT] Erreur lecture {path.name} : {e}")
            return None

    def _cleanup_old_checkpoints(self):
        checkpoints = self._list_checkpoints()
        if len(checkpoints) > MAX_CHECKPOINTS:
            to_delete = checkpoints[:len(checkpoints) - MAX_CHECKPOINTS]
            for path in to_delete:
                path.unlink()

    def _block_to_state(self, block: str) -> CheckpointState:
        mapping = {
            "sourcing":   CheckpointState.SOURCING,
            "scenario":   CheckpointState.SCENARIO,
            "storyboard": CheckpointState.STORYBOARD,
            "production": CheckpointState.PRODUCTION,
            "postprod":   CheckpointState.POSTPROD,
        }
        return mapping.get(block, CheckpointState.EMPTY)

    def _serialize(self, data: object) -> object:
        try:
            json.dumps(data)
            return data
        except Exception:
            return str(data)

    def _deserialize(self, data: object) -> object:
        return data

    def _get_hostname(self) -> str:
        try:
            import socket
            return socket.gethostname()
        except Exception:
            return "unknown"

    def _get_python_version(self) -> str:
        import sys
        return sys.version.split()[0]

    def _emergency_handler(self, signum, frame):
        print("\n")
        self.log.warning("[CHECKPOINT] Interruption detectee — sauvegarde d'urgence...")
        self.save_emergency()
        self.log.info(
            f"[CHECKPOINT] Etat sauvegarde. Pour reprendre :\n"
            f"  python maestro.py --resume --run-id "
            f"{self._current.run_id if self._current else '?'}"
        )
        signal.signal(signal.SIGINT, self._original_sigint)
        raise KeyboardInterrupt

    def __del__(self):
        try:
            signal.signal(signal.SIGINT, self._original_sigint)
        except Exception:
            pass


def get_checkpoint_manager(config: dict,
                            logger: logging.Logger = None) -> CheckpointManager:
    media    = config.get("media_type", "anime")
    universe = config.get("universe",   "default")
    pid      = f"{media}_{universe}"[:40].replace(" ", "_")
    return CheckpointManager(pid, logger)


if __name__ == "__main__":
    import sys, io
    if hasattr(sys.stdout,'buffer'):
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
    logging.basicConfig(level=logging.DEBUG)
    _log = logging.getLogger("cp_test")
    cm  = CheckpointManager("test_projet", _log)
    cfg = {"media_type":"anime","lora":"test.safetensors","width":1024,"height":1536}
    cp  = cm.new_checkpoint(cfg)
    for block, data in [
        ("sourcing",   {"brief":"Dragon Ball domine les tendances"}),
        ("scenario",   {"title":"L'Eveil du Super Saiyan","acts":[]}),
        ("storyboard", {"total_shots":12,"shots":[]}),
    ]:
        cm.save_block_start(block)
        time.sleep(0.1)
        cm.save_block(block, data)
    cm.save_emergency()
    cp_loaded = cm.load_latest()
    if cp_loaded:
        analysis = cm.analyze_resume(cp_loaded)
        _log.info(f"Analyse reprise : {analysis['message']}")
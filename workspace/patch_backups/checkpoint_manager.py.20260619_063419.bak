"""
agents/checkpoint_manager.py — Gestionnaire de Sauvegarde des Travaux
Sauvegarde l'état complet du pipeline à chaque étape clé.
Permet de reprendre exactement où l'on s'est arrêté après une interruption.

Fonctionnalités :
  - Sauvegarde automatique après chaque bloc (Sourcing, Scénario, Storyboard...)
  - Sauvegarde d'urgence sur Ctrl+C ou crash
  - Reprise intelligente : détecte l'avancement et propose de continuer
  - Historique des checkpoints par projet
  - Nettoyage automatique des vieux checkpoints
"""

import json
import logging
import signal
import time
import hashlib
import shutil
from pathlib import Path
from datetime import datetime
from enum import Enum


CHECKPOINT_DIR = Path("workspace/checkpoints")
MAX_CHECKPOINTS = 10   # nombre max de checkpoints par projet


class CheckpointState(Enum):
    EMPTY      = "empty"
    SOURCING   = "sourcing"
    SCENARIO   = "scenario"
    STORYBOARD = "storyboard"
    PRODUCTION = "production"
    POSTPROD   = "postprod"
    COMPLETED  = "completed"
    INTERRUPTED = "interrupted"
    FAILED     = "failed"


# Ordre des blocs pour la logique de reprise
BLOCK_ORDER = [
    CheckpointState.SOURCING,
    CheckpointState.SCENARIO,
    CheckpointState.STORYBOARD,
    CheckpointState.PRODUCTION,
    CheckpointState.POSTPROD,
]


class Checkpoint:
    """Représente un point de sauvegarde du pipeline."""

    def __init__(self, project_id: str, run_id: str):
        self.project_id = project_id
        self.run_id     = run_id
        self.created_at = datetime.utcnow().isoformat()
        self.updated_at = self.created_at
        self.state      = CheckpointState.EMPTY
        self.config     = {}      # paramètres du job
        self.data       = {}      # données produites par les blocs
        self.completed  = []      # blocs terminés
        self.current    = None    # bloc en cours
        self.errors     = []      # erreurs rencontrées
        self.metadata   = {}      # infos supplémentaires

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
        cp.config     = d.get("config",  {})
        cp.data       = d.get("data",    {})
        cp.completed  = d.get("completed", [])
        cp.current    = d.get("current")
        cp.errors     = d.get("errors",  [])
        cp.metadata   = d.get("metadata", {})
        return cp


class CheckpointManager:
    """
    Gère la sauvegarde et la reprise des travaux du pipeline.

    Usage :
        cm = CheckpointManager("mon_projet")
        cp = cm.new_checkpoint(config)
        cm.save_block("sourcing", trend_report)
        ...
        # En cas d'interruption → cm.save_emergency()
        # Pour reprendre → cm.load_latest()
    """

    def __init__(self, project_id: str,
                 logger: logging.Logger = None):
        self.project_id = project_id
        self.log        = logger or logging.getLogger("checkpoint")
        self._current   = None
        self._autosave  = True
        self._dir       = CHECKPOINT_DIR / self._safe_name(project_id)
        self._dir.mkdir(parents=True, exist_ok=True)

        # Intercepter Ctrl+C pour sauvegarde d'urgence
        self._original_sigint = signal.getsignal(signal.SIGINT)
        signal.signal(signal.SIGINT, self._emergency_handler)

    def _safe_name(self, name: str) -> str:
        """Convertit un nom en identifiant de dossier sûr."""
        safe = "".join(c if c.isalnum() or c in "-_" else "_" for c in name)
        return safe[:50]

    # ── Création / Chargement ─────────────────────────────────────────
    def new_checkpoint(self, config: dict,
                        run_id: str = None) -> Checkpoint:
        """Crée un nouveau checkpoint pour ce projet."""
        rid = run_id or f"run_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        cp  = Checkpoint(self.project_id, rid)
        cp.config   = config
        cp.metadata = {
            "hostname": self._get_hostname(),
            "python":   self._get_python_version(),
        }
        self._current = cp
        self._save_to_disk(cp)
        self.log.info(f"[CHECKPOINT] Nouveau checkpoint : {rid}")
        return cp

    def load_latest(self) -> Checkpoint | None:
        """
        Charge le checkpoint le plus récent pour ce projet.
        Retourne None s'il n'y en a pas.
        """
        checkpoints = self._list_checkpoints()
        if not checkpoints:
            self.log.info(f"[CHECKPOINT] Aucun checkpoint pour '{self.project_id}'")
            return None

        latest = checkpoints[-1]
        cp     = self._load_from_disk(latest)
        if cp:
            self._current = cp
            self.log.info(
                f"[CHECKPOINT] Checkpoint chargé : {cp.run_id} | "
                f"État : {cp.state.value} | "
                f"Blocs terminés : {cp.completed}"
            )
        return cp

    def load_checkpoint(self, run_id: str) -> Checkpoint | None:
        """Charge un checkpoint spécifique par son run_id."""
        path = self._dir / f"{run_id}.json"
        return self._load_from_disk(path)

    # ── Sauvegarde par bloc ───────────────────────────────────────────
    def save_block(self, block_name: str, data: object,
                    state: CheckpointState = None):
        """
        Sauvegarde l'état après un bloc terminé.
        Appelé à la fin de chaque bloc du pipeline.
        """
        if not self._current:
            self.log.warning("[CHECKPOINT] Pas de checkpoint actif")
            return

        cp = self._current
        cp.data[block_name] = self._serialize(data)
        cp.updated_at       = datetime.utcnow().isoformat()

        if block_name not in cp.completed:
            cp.completed.append(block_name)

        cp.current = block_name
        cp.state   = state or self._block_to_state(block_name)

        self._save_to_disk(cp)
        self.log.info(
            f"[CHECKPOINT] ✓ Bloc '{block_name}' sauvegardé "
            f"({len(cp.completed)}/5 blocs)"
        )

    def save_block_start(self, block_name: str):
        """Marque le début d'un bloc (pour détecter les interruptions)."""
        if not self._current: return
        self._current.current    = block_name
        self._current.updated_at = datetime.utcnow().isoformat()
        self._save_to_disk(self._current)
        self.log.debug(f"[CHECKPOINT] Début bloc '{block_name}'")

    def save_error(self, block_name: str, error: str):
        """Sauvegarde une erreur rencontrée."""
        if not self._current: return
        self._current.errors.append({
            "block":    block_name,
            "error":    error,
            "time":     datetime.utcnow().isoformat(),
        })
        self._current.state = CheckpointState.FAILED
        self._save_to_disk(self._current)
        self.log.error(f"[CHECKPOINT] Erreur sauvegardée : {block_name} → {error[:100]}")

    def mark_completed(self):
        """Marque le pipeline comme terminé avec succès."""
        if not self._current: return
        self._current.state      = CheckpointState.COMPLETED
        self._current.current    = None
        self._current.updated_at = datetime.utcnow().isoformat()
        self._save_to_disk(self._current)
        self.log.info("[CHECKPOINT] ✓ Pipeline marqué comme TERMINÉ")
        self._cleanup_old_checkpoints()

    def save_emergency(self):
        """Sauvegarde d'urgence sur interruption."""
        if not self._current: return
        self._current.state      = CheckpointState.INTERRUPTED
        self._current.updated_at = datetime.utcnow().isoformat()
        self._current.metadata["interrupted_at"] = datetime.utcnow().isoformat()
        self._save_to_disk(self._current)
        self.log.warning(
            f"[CHECKPOINT] ⚠ Sauvegarde d'urgence — "
            f"Reprise possible avec : run_id={self._current.run_id}"
        )

    # ── Analyse de reprise ────────────────────────────────────────────
    def analyze_resume(self, cp: Checkpoint) -> dict:
        """
        Analyse un checkpoint et recommande comment reprendre.
        Retourne les blocs à relancer et ceux à sauter.
        """
        if not cp:
            return {"action": "start_fresh", "skip": [], "resume_from": None}

        completed = cp.completed
        current   = cp.current

        if cp.state == CheckpointState.COMPLETED:
            return {
                "action":      "nothing",
                "message":     "Pipeline déjà terminé avec succès",
                "skip":        completed,
                "resume_from": None,
            }

        # Trouver le premier bloc non terminé
        all_blocks = ["sourcing", "scenario", "storyboard", "production", "postprod"]
        resume_from = None
        for block in all_blocks:
            if block not in completed:
                resume_from = block
                break

        # Si le bloc en cours était interrompu, le relancer
        if current and current not in completed:
            resume_from = current

        message = (
            f"Reprise depuis '{resume_from}' "
            f"({len(completed)}/5 blocs déjà terminés : {completed})"
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

    def get_resume_data(self, block_name: str) -> object | None:
        """Récupère les données sauvegardées d'un bloc terminé."""
        if not self._current: return None
        raw = self._current.data.get(block_name)
        return self._deserialize(raw) if raw is not None else None

    # ── Historique ────────────────────────────────────────────────────
    def list_checkpoints(self) -> list:
        """Liste tous les checkpoints de ce projet avec résumé."""
        paths = self._list_checkpoints()
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
        """Supprime un checkpoint spécifique."""
        path = self._dir / f"{run_id}.json"
        if path.exists():
            path.unlink()
            self.log.info(f"[CHECKPOINT] Supprimé : {run_id}")
            return True
        return False

    def delete_all(self):
        """Supprime tous les checkpoints de ce projet."""
        for path in self._list_checkpoints():
            path.unlink()
        self.log.info(f"[CHECKPOINT] Tous les checkpoints supprimés pour '{self.project_id}'")

    # ── Utilitaires privés ────────────────────────────────────────────
    def _list_checkpoints(self) -> list:
        """Liste les fichiers de checkpoint triés par date."""
        files = sorted(self._dir.glob("*.json"),
                       key=lambda p: p.stat().st_mtime)
        return files

    def _save_to_disk(self, cp: Checkpoint):
        """Sauvegarde un checkpoint sur disque."""
        path = self._dir / f"{cp.run_id}.json"
        try:
            path.write_text(
                json.dumps(cp.to_dict(), indent=2,
                            ensure_ascii=False, default=str),
                encoding="utf-8"
            )
        except Exception as e:
            self.log.error(f"[CHECKPOINT] Erreur écriture : {e}")

    def _load_from_disk(self, path: Path) -> Checkpoint | None:
        """Charge un checkpoint depuis le disque."""
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            return Checkpoint.from_dict(data)
        except Exception as e:
            self.log.error(f"[CHECKPOINT] Erreur lecture {path.name} : {e}")
            return None

    def _cleanup_old_checkpoints(self):
        """Supprime les checkpoints trop anciens."""
        checkpoints = self._list_checkpoints()
        if len(checkpoints) > MAX_CHECKPOINTS:
            to_delete = checkpoints[:len(checkpoints) - MAX_CHECKPOINTS]
            for path in to_delete:
                path.unlink()
            self.log.debug(f"[CHECKPOINT] {len(to_delete)} vieux checkpoint(s) supprimé(s)")

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
        """Sérialise les données pour JSON (gère les types non-sérialisables)."""
        try:
            json.dumps(data)
            return data
        except Exception:
            return str(data)

    def _deserialize(self, data: object) -> object:
        """Désérialise les données (actuellement identité)."""
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
        """Handler Ctrl+C : sauvegarde d'urgence puis quitte."""
        print("\n")
        self.log.warning("[CHECKPOINT] Interruption détectée — sauvegarde d'urgence...")
        self.save_emergency()
        self.log.info(
            f"[CHECKPOINT] État sauvegardé. Pour reprendre :\n"
            f"  python maestro.py --resume --run-id {self._current.run_id if self._current else '?'}"
        )
        # Restaurer le handler original et propager le signal
        signal.signal(signal.SIGINT, self._original_sigint)
        raise KeyboardInterrupt

    def __del__(self):
        """Restaurer le handler signal à la destruction."""
        try:
            signal.signal(signal.SIGINT, self._original_sigint)
        except Exception:
            pass


# ── Intégration dans maestro.py ───────────────────────────────────────
def get_checkpoint_manager(config: dict,
                             logger: logging.Logger = None) -> CheckpointManager:
    """
    Crée un CheckpointManager pour le projet actuel.
    Le project_id est dérivé du type de média + universe.
    """
    media   = config.get("media_type", "anime")
    universe = config.get("universe",  "default")
    pid     = f"{media}_{universe}"[:40].replace(" ", "_")
    return CheckpointManager(pid, logger)


if __name__ == "__main__":
    logging.basicConfig(level=logging.DEBUG)
    log = logging.getLogger("cp_test")

    # Test complet
    cm = CheckpointManager("test_projet", log)

    # Nouveau run
    cfg = {"media_type": "anime", "lora": "test.safetensors",
           "width": 1024, "height": 1536}
    cp = cm.new_checkpoint(cfg)

    # Simuler les blocs
    for block, data in [
        ("sourcing",   {"brief": "Dragon Ball domine les tendances"}),
        ("scenario",   {"title": "L'Éveil du Super Saiyan", "acts": []}),
        ("storyboard", {"total_shots": 12, "shots": []}),
    ]:
        cm.save_block_start(block)
        time.sleep(0.1)
        cm.save_block(block, data)
        log.info(f"Bloc '{block}' terminé")

    # Simuler une interruption avant production
    log.warning("Interruption simulée...")
    cm.save_emergency()

    # Analyser la reprise
    cp_loaded = cm.load_latest()
    if cp_loaded:
        analysis = cm.analyze_resume(cp_loaded)
        log.info(f"Analyse reprise : {analysis['message']}")
        log.info(f"Reprendre depuis : {analysis['resume_from']}")

    # Liste des checkpoints
    all_cp = cm.list_checkpoints()
    log.info(f"Checkpoints disponibles : {len(all_cp)}")
    for c in all_cp:
        log.info(f"  [{c['state']}] {c['run_id']} — {c['completed']}")

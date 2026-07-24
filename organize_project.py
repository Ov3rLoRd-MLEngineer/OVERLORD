"""
organize_project.py V1.49q -- Organisateur intelligent Ov3rLoRd
Appele depuis aAa_MaintenanceHub.py (pas compile en EXE separement).

Logique V1.49q :
  - Detecte la structure reelle de D:\OVERLORD\ (V1.49 = dossier agents/ minuscule)
  - Ne touche PAS aux dossiers non-natifs (ex: ComfyUI, models, custom_nodes)
  - Deplace les doublons et fichiers mal places dans "A_EVACUER\"
  - Detecte les fichiers en trop dans les dossiers natifs
  - Conforme a la structure V1.49 (agents/ en minuscule, pas AGENTS\)
"""

import sys
import os
import shutil
import hashlib
import json
from pathlib import Path
from datetime import datetime

try:
    import colorama; colorama.init()
    C_GREEN="\033[92m"; C_YELLOW="\033[93m"; C_RED="\033[91m"
    C_CYAN="\033[96m";  C_BOLD="\033[1m";    C_RESET="\033[0m"
except ImportError:
    C_GREEN=C_YELLOW=C_RED=C_CYAN=C_BOLD=C_RESET=""

# ── Structure V1.49 attendue ──────────────────────────────────────────

# Fichiers Python attendus a la RACINE (D:\OVERLORD\)
ROOT_PY_FILES = {
    "launcher.py", "maestro.py", "agent_supervisor_v2.py",
    "oracle_interface.py", "self_improve.py", "deploy.py",
    "test_integration.py", "test_pipeline.py", "patcher.py",
    "build_exe.py", "build_organizer.py", "organize_project.py",
    "overlord_utils_utf8.py", "aAa_MaintenanceHub.py", "aAa_Auditeur.py",
    "licence_server.py", "llama_chat.py", "learning_ui.py",
    "update_checkpoint.py", "download_dependencies.bat",
    "neural_orchestrator.py", "comfy_synesthesia_node.py",
}

# Fichiers de config / data attendus a la RACINE
ROOT_DATA_FILES = {
    "Combined_V35_API.json", "Combined_V35_CANVAS.json",
    "config.json", "node_catalog.json", "settings.json",
    "learning_settings.json", "llama_chat_settings.json",
    ".env", "journal.txt", "6.0.0",
}

ROOT_FILES = ROOT_PY_FILES | ROOT_DATA_FILES

# Fichiers agents Python (doivent etre dans agents/)
AGENT_PY_FILES = {
    # Core V1.49
    "__init__.py", "overlord_utils.py", "context_bus.py", "director.py",
    "critic.py", "watchdog.py", "sourcing.py", "scenario.py",
    "storyboard.py", "postprod.py", "pipeline_conscience.py",
    "cost_tracker.py", "transmedia_export.py",
    # Agents memoire / checkpoint
    "checkpoint_manager.py", "narrative_memory.py", "episode_packager.py",
    "asset_library.py", "error_recovery.py",
    # Agents specialises
    "sav_agent.py", "obs_agent.py", "capture.py", "comfy_memory.py",
    "agent_3d_modeler.py", "ollama_bridge.py", "roles_registry.py",
    "style_dna.py", "audience_analyzer.py", "style_evolution.py",
    "benchmark_arena.py", "prompt_optimizer.py",
    # Agents optionnels
    "learning_agent.py", "legacy_agent.py", "memory_agent.py",
    "marketing_pub.py", "webmaster.py", "community_manager.py",
    "social_agent.py", "sys_agent.py", "remote_gpu.py",
    "gpu_scheduler.py", "ray_cluster.py", "telegram_bot.py",
    "comfy_autoconfig.py", "api_server.py", "agent_supervisor_v2.py",
    # v110-v140 : noms historiques debarrasses du prefixe de version le
    # 2026-07-25 (restructuration en-tetes/nommage) -- lignee still tracee
    # dans les CONTEXTE_OVERLORD_V1x0.md correspondants.
    "core.py", "intelligence.py", "graph_ui.py",
    "dashboard.py", "alignment.py", "collective.py", "generation.py",
    "learning.py", "moe.py",
    "emotion_engine.py", "world_model.py", "generative_world.py",
    "narrative_dna.py", "agent_personality.py",
    "cocreation.py", "dream_simulation.py", "intelligence_ext.py",
    "model_downloader.py", "synchronicity.py", "theory_of_mind.py",
    "thermal_protection.py", "video_pipeline.py", "voice_synthesis.py",
    # Jamais implementes -- references historiques (etaient deja dans cette
    # liste avant le nettoyage du 2026-07-25, aucun fichier correspondant
    # n'a jamais existe dans le depot) -- a garder si ce travail est repris.
    "v120_analytics.py", "v120_ab_testing.py",
    "v120_narrative_coach.py", "v120_production_director.py",
    # Sous-agents
    "agent_supervisor_v2.py",
}

# Dossiers NATIFS Ov3rLoRd (a ne pas toucher sauf conformite interne)
NATIVE_DIRS = {
    "agents",       # agents Python
    "workspace",    # donnees runtime
    "assets",       # icones, images projet
    "dist",         # EXE compiles
    "build",        # artefacts build PyInstaller
    "DOCS",         # documentation
    "BACKUP",       # backups
    "A_EVACUER",    # fichiers a evacuer (cree par cet outil)
    "workspace",
}

# Dossiers NON-NATIFS a ignorer completement (ex: ComfyUI, modeles IA)
# L'outil ne touchera jamais a ces dossiers
NON_NATIVE_PATTERNS = {
    "ComfyUI", "models", "custom_nodes", "loras", "checkpoints",
    "venv", ".venv", "env", "__pycache__", ".git", "node_modules",
    "stable-diffusion", "automatic1111", "outputs", "inputs",
}

# Extensions → dossier cible
EXT_TO_DIR = {
    ".md":   "DOCS",
    ".txt":  "DOCS",   # sauf .env et journal.txt
    ".pdf":  "DOCS",
    ".docx": "DOCS",
}


def md5(path: Path) -> str:
    try:
        return hashlib.md5(path.read_bytes()).hexdigest()
    except Exception:
        return ""


def is_non_native(name: str) -> bool:
    return name in NON_NATIVE_PATTERNS or name.startswith(".")


def find_root() -> Path:
    cwd = Path.cwd()
    if (cwd / "maestro.py").exists() or (cwd / "launcher.py").exists():
        return cwd
    if getattr(sys, "frozen", False):
        exe_dir = Path(sys.executable).parent
        if (exe_dir / "maestro.py").exists():
            return exe_dir
    for parent in list(cwd.parents)[:3]:
        if (parent / "maestro.py").exists():
            return parent
    return cwd


def log_ok(m):   print(f"  {C_GREEN}[OK]{C_RESET}  {m}")
def log_mv(m):   print(f"  {C_YELLOW}[MV]{C_RESET}  {m}")
def log_ev(m):   print(f"  {C_RED}[!!]{C_RESET}  {m}")
def log_sk(m):   print(f"  {C_CYAN}[--]{C_RESET}  {m}")
def log_h(m):    print(f"\n{C_BOLD}{C_CYAN}--- {m} ---{C_RESET}")


class ProjectOrganizer:

    def __init__(self, root: Path, dry_run: bool = False,
                 logger=None):
        self.root    = root
        self.dry_run = dry_run
        self.log     = logger  # callable(level, msg) pour le Hub
        self.evac    = root / "A_EVACUER"
        self.agents  = root / "agents"
        self.docs    = root / "DOCS"
        self.backup  = root / "BACKUP"
        self.report  = {
            "root": str(root),
            "dry_run": dry_run,
            "moved": [], "evacuated": [], "duplicates": [],
            "ok": [], "unknown": [], "errors": [],
        }

    def _emit(self, level: str, msg: str):
        """Emetteur de log compatible Hub (callable) et console."""
        if self.log:
            self.log(level, msg)
        else:
            if   level == "ok":   log_ok(msg)
            elif level == "move": log_mv(msg)
            elif level == "evac": log_ev(msg)
            elif level == "skip": log_sk(msg)
            else:                 print(f"  {msg}")

    def _safe_move(self, src: Path, dst_dir: Path,
                    reason: str = "") -> bool:
        """Deplace src vers dst_dir, gere les doublons de nom."""
        if self.dry_run:
            self._emit("move", f"[DRY] {src.name} -> {dst_dir.name}/  {reason}")
            return True
        try:
            dst_dir.mkdir(parents=True, exist_ok=True)
            dst = dst_dir / src.name
            if dst.exists():
                # Renommer avec timestamp pour eviter l'ecrasement
                ts  = datetime.now().strftime("%Y%m%d_%H%M%S")
                dst = dst_dir / f"{src.stem}_{ts}{src.suffix}"
            shutil.move(str(src), str(dst))
            self._emit("move", f"{src.name} -> {dst_dir.name}/{dst.name}  {reason}")
            self.report["moved"].append(str(src))
            return True
        except Exception as e:
            self._emit("skip", f"Erreur deplacement {src.name} : {e}")
            self.report["errors"].append(str(src))
            return False

    def _evacuate(self, path: Path, reason: str):
        """Envoie un fichier vers A_EVACUER/."""
        if self.dry_run:
            self._emit("evac", f"[DRY] EVACUER {path.name} : {reason}")
            return
        self.evac.mkdir(parents=True, exist_ok=True)
        dst = self.evac / path.name
        if dst.exists():
            ts  = datetime.now().strftime("%Y%m%d_%H%M%S")
            dst = self.evac / f"{path.stem}_{ts}{path.suffix}"
        try:
            shutil.move(str(path), str(dst))
            self._emit("evac", f"EVACUE : {path.name} -> A_EVACUER/  ({reason})")
            self.report["evacuated"].append({"file": str(path), "reason": reason})
        except Exception as e:
            self._emit("skip", f"Evacuation impossible {path.name} : {e}")

    # ── Phase 1 : Racine ──────────────────────────────────────────────
    def scan_root(self):
        self._emit("info", "Scan de la racine...")
        seen_hashes: dict[str, Path] = {}

        for item in sorted(self.root.iterdir()):
            if item.is_dir():
                continue  # les dossiers sont traites separement
            name = item.name
            ext  = item.suffix.lower()

            # Ignorer les fichiers systeme
            if name.startswith(".") and name not in {".env"}:
                continue
            if name == "__pycache__":
                continue

            # Fichier attendu a la racine -> OK
            if name in ROOT_FILES:
                # Verifier doublon avec agents/
                agent_copy = self.agents / name
                if agent_copy.exists():
                    h1 = md5(item)
                    h2 = md5(agent_copy)
                    if h1 == h2:
                        self._evacuate(agent_copy,
                            f"doublon identique de {name} (racine = reference)")
                        self.report["duplicates"].append(name)
                    else:
                        self._emit("evac",
                            f"CONFLIT : {name} existe en racine ET agents/ (contenu different) -- evacuation de la copie agents/")
                        self._evacuate(agent_copy,
                            "conflit racine/agents -- version agents evacuee")
                self._emit("ok", f"{name} -> racine (correct)")
                self.report["ok"].append(name)
                continue

            # Fichier agent Python a la racine -> deplacer vers agents/
            if name in AGENT_PY_FILES and ext == ".py":
                # Verifier doublon dans agents/
                dst = self.agents / name
                if dst.exists():
                    h1 = md5(item)
                    h2 = md5(dst)
                    if h1 == h2:
                        self._evacuate(item,
                            f"doublon identique de agents/{name}")
                    else:
                        self._evacuate(item,
                            f"conflit avec agents/{name} (contenu different) -- copie racine evacuee")
                    self.report["duplicates"].append(name)
                else:
                    self._safe_move(item, self.agents, "(agent mal place a la racine)")
                continue

            # Fichier de doc -> DOCS/
            if ext in EXT_TO_DIR and name not in {".env", "journal.txt"}:
                self._safe_move(item, self.docs, f"({ext} -> DOCS/)")
                continue

            # .spec PyInstaller -> BACKUP/
            if ext == ".spec":
                self._safe_move(item, self.backup, "(.spec -> BACKUP/)")
                continue

            # .bak -> BACKUP/
            if ext == ".bak":
                self._safe_move(item, self.backup, "(.bak -> BACKUP/)")
                continue

            # Python non reconnu a la racine
            if ext == ".py":
                # Verifier hash doublon
                h = md5(item)
                if h in seen_hashes:
                    self._evacuate(item,
                        f"doublon de {seen_hashes[h].name}")
                    self.report["duplicates"].append(name)
                else:
                    seen_hashes[h] = item
                    self._evacuate(item,
                        "fichier Python non repertorie -- a classer manuellement")
                continue

            # Tout le reste -> non classifie
            self.report["unknown"].append(name)
            self._emit("skip", f"Non classifie : {name} (ignore)")

    # ── Phase 2 : Dossier agents/ ─────────────────────────────────────
    def scan_agents(self):
        if not self.agents.exists():
            self._emit("skip", "Dossier agents/ absent -- skip")
            return
        self._emit("info", "Scan de agents/...")
        seen_hashes: dict[str, Path] = {}
        known = AGENT_PY_FILES

        for item in sorted(self.agents.iterdir()):
            if item.is_dir():
                continue
            name = item.name
            ext  = item.suffix.lower()

            if ext != ".py":
                # Fichier non-Python dans agents/ -> evac
                self._evacuate(item, "fichier non-Python dans agents/")
                continue

            h = md5(item)
            if h in seen_hashes:
                # Doublon exact
                self._evacuate(item,
                    f"doublon de {seen_hashes[h].name}")
                self.report["duplicates"].append(name)
                continue
            seen_hashes[h] = item

            if name in known:
                self._emit("ok", f"agents/{name} (correct)")
                self.report["ok"].append(f"agents/{name}")
            else:
                # Fichier Python dans agents/ mais pas dans la liste connue
                # Peut etre un agent custom -> ne pas evacuer, signaler
                self._emit("skip",
                    f"agents/{name} non repertorie (agent custom ?) -- conserve")
                self.report["unknown"].append(f"agents/{name}")

    # ── Phase 3 : Dossiers non-natifs ────────────────────────────────
    def scan_extra_dirs(self):
        self._emit("info", "Scan des dossiers extra...")
        for item in sorted(self.root.iterdir()):
            if not item.is_dir():
                continue
            name = item.name
            if name in NATIVE_DIRS or is_non_native(name):
                continue
            # Dossier non reconnu -> signaler mais ne pas toucher
            self._emit("skip",
                f"Dossier non-natif detecte : {name}/ -- IGNORE (non modifie)")
            self.report["unknown"].append(f"{name}/")

    # ── Phase 4 : Workspace ────────────────────────────────────────────
    def check_workspace(self):
        ws = self.root / "workspace"
        if not ws.exists():
            self._emit("skip", "workspace/ absent (sera cree au prochain run)")
            return
        # Juste verifier la taille
        size = sum(f.stat().st_size for f in ws.rglob("*") if f.is_file())
        self._emit("ok",
            f"workspace/ present ({size//1024//1024} MB, non modifie)")

    # ── Run complet ───────────────────────────────────────────────────
    def run(self) -> dict:
        mode = "SIMULATION" if self.dry_run else "REEL"
        self._emit("info",
            f"OrganizeProject V1.49q -- mode {mode} -- racine : {self.root}")

        self.scan_root()
        self.scan_agents()
        self.scan_extra_dirs()
        self.check_workspace()

        # Ecrire le rapport
        if not self.dry_run:
            rpt_path = self.root / "DOCS" / "organize_report.json"
            try:
                rpt_path.parent.mkdir(parents=True, exist_ok=True)
                rpt_path.write_text(
                    json.dumps({
                        **self.report,
                        "timestamp": datetime.now().isoformat(),
                    }, ensure_ascii=False, indent=2),
                    encoding="utf-8"
                )
                self._emit("ok", f"Rapport -> {rpt_path}")
            except Exception:
                pass

        n_mv  = len(self.report["moved"])
        n_ev  = len(self.report["evacuated"])
        n_dup = len(self.report["duplicates"])
        n_ok  = len(self.report["ok"])
        self._emit("info",
            f"Termine : {n_ok} OK | {n_mv} deplaces | "
            f"{n_ev} evacues | {n_dup} doublons")
        return self.report


def run_from_hub(root: Path = None, dry_run: bool = False,
                 logger=None) -> dict:
    """
    Point d'entree appele depuis aAa_MaintenanceHub.py.
    logger : callable(level: str, msg: str) ou None
    """
    r = root or find_root()
    organizer = ProjectOrganizer(r, dry_run=dry_run, logger=logger)
    return organizer.run()


def main():
    import argparse
    parser = argparse.ArgumentParser(
        description="Ov3rLoRd OrganizeProject V1.49q")
    parser.add_argument("--path",    default=None)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    root = Path(args.path) if args.path else find_root()
    if not root.exists():
        print(f"Dossier introuvable : {root}"); sys.exit(1)

    print(f"\n{C_BOLD}OrganizeProject V1.49q{C_RESET}")
    print(f"Racine : {root}")
    print(f"Mode   : {'SIMULATION' if args.dry_run else 'REEL'}\n")

    organizer = ProjectOrganizer(root, dry_run=args.dry_run)
    report    = organizer.run()

    print(f"\n{C_BOLD}Done.{C_RESET}")
    if getattr(sys, "frozen", False):
        input("\nAppuie sur Entree pour fermer...")


if __name__ == "__main__":
    main()

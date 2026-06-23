"""
agents/agent_registry.py — Registre & Versioning Agents V1.70
Chaque agent possède un manifest.json (version, dépendances, checksum).
Le registre scanne, compare les versions, détecte les conflits,
et permet le rollback automatique vers la dernière version stable.

Usage :
    from agents.agent_registry import get_registry
    reg = get_registry()
    reg.scan()                          # Scanner tous les agents
    reg.status()                        # Rapport de santé
    reg.rollback("scenario")            # Rollback vers v_stable
    reg.snapshot("scenario")            # Sauvegarder version stable
"""

import hashlib
import json
import logging
import shutil
import threading
from datetime import datetime
from pathlib import Path

AGENTS_DIR    = Path("agents")
REGISTRY_DIR  = Path("workspace/registry")
MANIFESTS_DIR = REGISTRY_DIR / "manifests"
SNAPSHOTS_DIR = REGISTRY_DIR / "snapshots"
REGISTRY_FILE = REGISTRY_DIR / "registry.json"

log = logging.getLogger("agent_registry")


def _file_checksum(path: Path) -> str:
    """SHA256 des 8 premiers KB du fichier (rapide)."""
    try:
        content = path.read_bytes()[:8192]
        return hashlib.sha256(content).hexdigest()[:16]
    except Exception:
        return "error"


def _count_lines(path: Path) -> int:
    try:
        return len(path.read_text(encoding="utf-8", errors="replace").splitlines())
    except Exception:
        return 0


class AgentManifest:
    """Manifest d'un agent individuel."""

    def __init__(self, agent_name: str):
        self.name     = agent_name
        self.path     = AGENTS_DIR / f"{agent_name}.py"
        self.manifest_path = MANIFESTS_DIR / f"{agent_name}.json"
        self.data: dict = {}

    def load(self) -> bool:
        if self.manifest_path.exists():
            try:
                self.data = json.loads(self.manifest_path.read_text(encoding="utf-8"))
                return True
            except Exception:
                pass
        return False

    def generate(self) -> dict:
        """Génère le manifest depuis le fichier .py."""
        if not self.path.exists():
            return {}

        checksum = _file_checksum(self.path)
        lines    = _count_lines(self.path)
        src      = self.path.read_text(encoding="utf-8", errors="replace")

        # Extraire version depuis docstring (ex: "V1.60")
        import re
        version_match = re.search(r'V(\d+\.\d+[a-z]?)', src[:500])
        version = version_match.group(0) if version_match else "V?.?"

        # Extraire imports pour détecter dépendances
        deps = re.findall(r'from agents\.(\w+) import', src)
        deps = list(set(deps))

        # Détecter si le fichier a des erreurs de syntaxe
        import ast
        try:
            ast.parse(src)
            syntax_ok = True
        except SyntaxError:
            syntax_ok = False

        self.data = {
            "name":        self.name,
            "version":     version,
            "checksum":    checksum,
            "lines":       lines,
            "dependencies": deps,
            "syntax_ok":   syntax_ok,
            "last_scan":   datetime.now().isoformat(),
            "path":        str(self.path),
        }
        return self.data

    def save(self):
        MANIFESTS_DIR.mkdir(parents=True, exist_ok=True)
        self.manifest_path.write_text(
            json.dumps(self.data, indent=2, ensure_ascii=False),
            encoding="utf-8"
        )

    def is_changed(self) -> bool:
        """Détecte si le fichier a changé depuis le dernier manifest."""
        if not self.data:
            return True
        return _file_checksum(self.path) != self.data.get("checksum", "")


class AgentRegistry:
    """Registre central de tous les agents."""

    def __init__(self):
        self._lock     = threading.Lock()
        self._registry = {}
        REGISTRY_DIR.mkdir(parents=True, exist_ok=True)
        MANIFESTS_DIR.mkdir(parents=True, exist_ok=True)
        SNAPSHOTS_DIR.mkdir(parents=True, exist_ok=True)
        self._load_registry()

    def _load_registry(self):
        if REGISTRY_FILE.exists():
            try:
                self._registry = json.loads(REGISTRY_FILE.read_text(encoding="utf-8"))
            except Exception:
                self._registry = {}

    def _save_registry(self):
        REGISTRY_FILE.write_text(
            json.dumps(self._registry, indent=2, ensure_ascii=False),
            encoding="utf-8"
        )

    def scan(self, verbose: bool = True) -> dict:
        """
        Scanne tous les agents dans agents/.
        Met à jour les manifests si le fichier a changé.
        Retourne le rapport de scan.
        """
        log.info("[REGISTRY] Scan des agents...")
        report = {
            "timestamp":   datetime.now().isoformat(),
            "total":       0,
            "updated":     0,
            "syntax_errors": [],
            "agents":      {},
        }

        if not AGENTS_DIR.exists():
            log.error(f"[REGISTRY] Dossier agents/ introuvable : {AGENTS_DIR}")
            return report

        py_files = sorted(AGENTS_DIR.glob("*.py"))
        report["total"] = len(py_files)

        for py_file in py_files:
            name = py_file.stem
            if name.startswith("__"):
                continue

            manifest = AgentManifest(name)
            manifest.load()

            if manifest.is_changed() or not manifest.data:
                data = manifest.generate()
                manifest.save()
                report["updated"] += 1
                if verbose:
                    log.info(f"[REGISTRY] Mis à jour : {name} {data.get('version','?')} "
                             f"({data.get('lines',0)} lignes)")
            else:
                data = manifest.data

            if not data.get("syntax_ok", True):
                report["syntax_errors"].append(name)
                log.error(f"[REGISTRY] ERREUR SYNTAXE : {name}")

            report["agents"][name] = {
                "version":  data.get("version", "?"),
                "checksum": data.get("checksum", "?"),
                "lines":    data.get("lines", 0),
                "ok":       data.get("syntax_ok", True),
                "deps":     data.get("dependencies", []),
            }

        # Détecter les dépendances circulaires
        circular = self._detect_circular(report["agents"])
        report["circular_deps"] = circular
        if circular:
            log.warning(f"[REGISTRY] Dépendances circulaires : {circular}")

        # Sauvegarder dans le registre
        with self._lock:
            self._registry["last_scan"] = report
            self._save_registry()

        log.info(f"[REGISTRY] Scan terminé : {report['total']} agents | "
                 f"{report['updated']} mis à jour | "
                 f"{len(report['syntax_errors'])} erreurs syntaxe")
        return report

    def _detect_circular(self, agents: dict) -> list:
        """Détecte les dépendances circulaires (DFS)."""
        circular = []
        visited  = set()
        rec_stack = set()

        def dfs(name, path):
            visited.add(name)
            rec_stack.add(name)
            for dep in agents.get(name, {}).get("deps", []):
                if dep not in agents:
                    continue
                if dep not in visited:
                    dfs(dep, path + [dep])
                elif dep in rec_stack:
                    cycle = path + [dep]
                    circular.append(" → ".join(cycle))
            rec_stack.discard(name)

        for agent_name in agents:
            if agent_name not in visited:
                dfs(agent_name, [agent_name])

        return circular

    def snapshot(self, agent_name: str, label: str = "v_stable") -> bool:
        """Sauvegarde la version actuelle d'un agent comme snapshot stable."""
        src = AGENTS_DIR / f"{agent_name}.py"
        if not src.exists():
            log.error(f"[REGISTRY] Agent introuvable : {agent_name}")
            return False

        ts   = datetime.now().strftime("%Y%m%d_%H%M%S")
        dest = SNAPSHOTS_DIR / agent_name / f"{label}_{ts}.py"
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dest)

        # Mettre à jour le pointeur v_stable
        stable_ptr = SNAPSHOTS_DIR / agent_name / f"{label}.py"
        shutil.copy2(src, stable_ptr)

        log.info(f"[REGISTRY] Snapshot '{label}' sauvegardé : {agent_name} → {dest.name}")

        with self._lock:
            if "snapshots" not in self._registry:
                self._registry["snapshots"] = {}
            self._registry["snapshots"][agent_name] = {
                "label":    label,
                "path":     str(stable_ptr),
                "saved_at": datetime.now().isoformat(),
                "checksum": _file_checksum(src),
            }
            self._save_registry()
        return True

    def rollback(self, agent_name: str, label: str = "v_stable") -> bool:
        """Restaure un agent depuis son snapshot stable."""
        stable = SNAPSHOTS_DIR / agent_name / f"{label}.py"
        if not stable.exists():
            log.error(f"[REGISTRY] Aucun snapshot '{label}' pour {agent_name}")
            return False

        dest = AGENTS_DIR / f"{agent_name}.py"
        # Backup de la version actuelle avant rollback
        if dest.exists():
            bk = SNAPSHOTS_DIR / agent_name / f"pre_rollback_{datetime.now().strftime('%Y%m%d_%H%M%S')}.py"
            bk.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(dest, bk)

        shutil.copy2(stable, dest)
        log.info(f"[REGISTRY] Rollback effectué : {agent_name} ← {label}")
        return True

    def snapshot_all(self):
        """Snapshot de tous les agents syntaxiquement valides."""
        log.info("[REGISTRY] Snapshot global de tous les agents valides...")
        count = 0
        for py_file in AGENTS_DIR.glob("*.py"):
            name = py_file.stem
            if name.startswith("__"):
                continue
            # Vérifier syntaxe avant snapshot
            import ast
            try:
                ast.parse(py_file.read_text(encoding="utf-8", errors="replace"))
                self.snapshot(name)
                count += 1
            except SyntaxError:
                log.warning(f"[REGISTRY] Skip snapshot {name} (syntaxe invalide)")
        log.info(f"[REGISTRY] {count} agents snapshotés")

    def status(self) -> dict:
        """Rapport de santé du registre."""
        scan = self._registry.get("last_scan", {})
        agents = scan.get("agents", {})
        return {
            "total_agents":   len(agents),
            "ok":             sum(1 for a in agents.values() if a.get("ok", True)),
            "syntax_errors":  scan.get("syntax_errors", []),
            "circular_deps":  scan.get("circular_deps", []),
            "last_scan":      scan.get("timestamp", "jamais"),
            "snapshots":      len(self._registry.get("snapshots", {})),
        }

    def get_manifest(self, agent_name: str) -> dict:
        scan = self._registry.get("last_scan", {})
        return scan.get("agents", {}).get(agent_name, {})


# Singleton
_registry_instance: AgentRegistry | None = None
_reg_lock = threading.Lock()

def get_registry() -> AgentRegistry:
    global _registry_instance
    with _reg_lock:
        if _registry_instance is None:
            _registry_instance = AgentRegistry()
    return _registry_instance


if __name__ == "__main__":
    import sys, io
    if hasattr(sys.stdout, "buffer"):
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    logging.basicConfig(level=logging.INFO)

    reg = get_registry()

    print("=== Scan des agents ===")
    report = reg.scan()

    print(f"\n=== Statut ===")
    status = reg.status()
    for k, v in status.items():
        print(f"  {k}: {v}")

    if report.get("syntax_errors"):
        print(f"\n⚠ Erreurs syntaxe : {report['syntax_errors']}")

    if report.get("circular_deps"):
        print(f"\n⚠ Dépendances circulaires : {report['circular_deps']}")

    print(f"\n✓ Snapshot de tous les agents valides ? (oui/non) ", end="")
    # En mode non-interactif, on skip
    print("(mode auto : skip)")

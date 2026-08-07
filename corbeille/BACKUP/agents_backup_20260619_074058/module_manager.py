"""
agents/module_manager.py — Gestionnaire de Modules Dynamique V1.46
Active/désactive les agents à chaud, gère les dépendances.
S'intègre dans overlord_launcher.py et l'UI web.

Usage :
    from agents.module_manager import ModuleManager
    mgr = ModuleManager()
    mgr.enable("telegram_bot")
    mgr.disable("ray_cluster")
    active = mgr.get_active_modules()
"""

import ast
import importlib
import json
import logging
import subprocess
import sys
from pathlib import Path
from datetime import datetime

try:
    from agents.overlord_utils import ensure_workspace
    UTILS_OK = True
except ImportError:
    UTILS_OK = False

log = logging.getLogger("module_manager")
BASE_DIR   = Path(__file__).resolve().parent.parent
AGENTS_DIR = BASE_DIR / "agents"
CONFIG_FILE= BASE_DIR / "workspace" / "module_config.json"

# Catalogue des modules avec métadonnées
MODULE_CATALOG = {
    # Pipeline core — toujours actifs
    "maestro":            {"label":"Orchestrateur",      "category":"core",     "required":True,  "deps":[]},
    "critic":             {"label":"Agent Critique",     "category":"core",     "required":True,  "deps":[]},
    "watchdog":           {"label":"Watchdog",           "category":"core",     "required":True,  "deps":[]},
    "checkpoint_manager": {"label":"Checkpoint",         "category":"core",     "required":True,  "deps":[]},
    "overlord_utils":     {"label":"Utils centraux",     "category":"core",     "required":True,  "deps":[]},
    # Agents créatifs
    "sourcing":           {"label":"Veille Tendances",   "category":"creative", "required":False, "deps":[]},
    "scenario":           {"label":"Scénariste",         "category":"creative", "required":False, "deps":["overlord_utils"]},
    "storyboard":         {"label":"Storyboarder",       "category":"creative", "required":False, "deps":["scenario"]},
    "postprod":           {"label":"Post-Production",    "category":"creative", "required":False, "deps":["storyboard"]},
    "agent_3d_modeler":   {"label":"Modeleur 3D",        "category":"creative", "required":False, "deps":[]},
    # Intelligence
    "narrative_memory":   {"label":"Mémoire Narrative",  "category":"ai",       "required":False, "deps":[]},
    "style_dna":          {"label":"Style DNA Lock",     "category":"ai",       "required":False, "deps":[]},
    "asset_library":      {"label":"Bibliothèque Assets","category":"ai",       "required":False, "deps":["style_dna"]},
    "pipeline_conscience":{"label":"Pipeline Conscience","category":"ai",       "required":False, "deps":[]},
    "self_improve":       {"label":"Auto-Amélioration",  "category":"ai",       "required":False, "deps":["overlord_utils"]},
    # Outils
    "episode_packager":   {"label":"Assembleur Épisode", "category":"tools",    "required":False, "deps":["postprod"]},
    "comfy_autoconfig":   {"label":"ComfyUI AutoConfig", "category":"tools",    "required":False, "deps":[]},
    "cost_tracker":       {"label":"Suivi Coûts",        "category":"tools",    "required":False, "deps":[]},
    "telegram_bot":       {"label":"Bot Telegram",       "category":"tools",    "required":False, "deps":[]},
    "oracle_interface":   {"label":"Oracle CLI",         "category":"tools",    "required":False, "deps":["overlord_utils"]},
    "test_pipeline":      {"label":"Tests Pipeline",     "category":"tools",    "required":False, "deps":[]},
    # Optionnels lourds
    "ray_cluster":        {"label":"Cluster Ray",        "category":"optional", "required":False, "deps":[]},
    "remote_gpu":         {"label":"GPU Distant",        "category":"optional", "required":False, "deps":[]},
    "sourcing_multisensor":{"label":"Sourcing Multi",    "category":"optional", "required":False, "deps":["sourcing"]},
}


class ModuleManager:
    def __init__(self, logger: logging.Logger = None):
        self.log = logger or log
        CONFIG_FILE.parent.mkdir(parents=True, exist_ok=True)
        self._config = self._load_config()

    def _load_config(self) -> dict:
        if CONFIG_FILE.exists():
            try:
                return json.loads(CONFIG_FILE.read_text(encoding="utf-8"))
            except Exception:
                pass
        # Par défaut : tout actif sauf les optionnels lourds
        return {
            "enabled": {k: v["category"] != "optional"
                        for k, v in MODULE_CATALOG.items()},
            "updated_at": datetime.now().isoformat(),
        }

    def _save_config(self):
        self._config["updated_at"] = datetime.now().isoformat()
        CONFIG_FILE.write_text(
            json.dumps(self._config, indent=2, ensure_ascii=False),
            encoding="utf-8"
        )

    # ── Activation/Désactivation ──────────────────────────────────────
    def enable(self, module_name: str) -> tuple:
        """Active un module. Vérifie les dépendances."""
        if module_name not in MODULE_CATALOG:
            return False, f"Module '{module_name}' inconnu"

        deps = MODULE_CATALOG[module_name].get("deps", [])
        missing_deps = [d for d in deps if not self._config["enabled"].get(d, False)]
        if missing_deps:
            return False, f"Dépendances manquantes : {missing_deps}"

        self._config["enabled"][module_name] = True
        self._save_config()
        self.log.info(f"[MODULES] ✓ Activé : {module_name}")
        return True, f"Module '{module_name}' activé"

    def disable(self, module_name: str) -> tuple:
        """Désactive un module. Refuse si requis ou si d'autres en dépendent."""
        if module_name not in MODULE_CATALOG:
            return False, f"Module '{module_name}' inconnu"

        if MODULE_CATALOG[module_name].get("required"):
            return False, f"Module '{module_name}' est requis — impossible de désactiver"

        dependents = [k for k, v in MODULE_CATALOG.items()
                      if module_name in v.get("deps", [])
                      and self._config["enabled"].get(k, False)]
        if dependents:
            return False, f"Modules dépendants actifs : {dependents}"

        self._config["enabled"][module_name] = False
        self._save_config()
        self.log.info(f"[MODULES] ✗ Désactivé : {module_name}")
        return True, f"Module '{module_name}' désactivé"

    # ── Statut et listing ─────────────────────────────────────────────
    def get_status(self) -> dict:
        """Retourne le statut complet de tous les modules."""
        status = {}
        for name, meta in MODULE_CATALOG.items():
            enabled  = self._config["enabled"].get(name, False)
            exists   = (AGENTS_DIR / f"{name}.py").exists() or (BASE_DIR / f"{name}.py").exists()
            loadable = self._test_import(name) if enabled and exists else None

            status[name] = {
                "label":    meta["label"],
                "category": meta["category"],
                "required": meta.get("required", False),
                "enabled":  enabled,
                "exists":   exists,
                "loadable": loadable,
                "deps":     meta.get("deps", []),
            }
        return status

    def _test_import(self, module_name: str) -> bool:
        """Teste si le module peut être importé."""
        try:
            if f"agents.{module_name}" in sys.modules:
                return True
            spec = importlib.util.find_spec(f"agents.{module_name}")
            return spec is not None
        except Exception:
            return False

    def get_active_modules(self) -> list:
        return [k for k, v in self._config["enabled"].items() if v]

    def get_by_category(self, category: str) -> list:
        return [k for k, v in MODULE_CATALOG.items()
                if v["category"] == category
                and self._config["enabled"].get(k, False)]

    def install_deps(self, module_name: str) -> bool:
        """Installe les dépendances Python d'un module."""
        DEP_MAP = {
            "telegram_bot":     ["python-telegram-bot"],
            "narrative_memory": ["networkx", "chromadb"],
            "ray_cluster":      ["ray"],
            "sourcing":         ["feedparser", "pytrends"],
            "postprod":         ["gTTS", "pydub"],
            "agent_3d_modeler": ["trimesh", "numpy"],
            "cost_tracker":     [],
        }
        pkgs = DEP_MAP.get(module_name, [])
        if not pkgs:
            return True
        try:
            result = subprocess.run(
                [sys.executable, "-m", "pip", "install"] + pkgs + ["--quiet"],
                capture_output=True, timeout=120
            )
            if result.returncode == 0:
                self.log.info(f"[MODULES] Dépendances installées : {pkgs}")
                return True
        except Exception as e:
            self.log.error(f"[MODULES] Erreur install : {e}")
        return False

    def print_status(self):
        status = self.get_status()
        cats = {}
        for name, s in status.items():
            c = s["category"]
            cats.setdefault(c, []).append((name, s))

        print(f"\n{'═'*60}")
        print(f"  Ov3rLoRd — Module Manager V1.46")
        print(f"{'═'*60}")
        for cat, items in cats.items():
            print(f"\n  ── {cat.upper()} ──")
            for name, s in items:
                icon = "✓" if s["enabled"] else "○"
                req  = " [REQ]" if s["required"] else ""
                ex   = "✓" if s["exists"] else "✗"
                print(f"  {icon} {name:<30} {s['label']:<25}{req} fichier={ex}")
        print(f"\n{'═'*60}\n")


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    mgr = ModuleManager()
    mgr.print_status()

    ok, msg = mgr.disable("ray_cluster")
    print(f"Disable ray_cluster : {ok} — {msg}")
    ok, msg = mgr.enable("telegram_bot")
    print(f"Enable telegram_bot : {ok} — {msg}")

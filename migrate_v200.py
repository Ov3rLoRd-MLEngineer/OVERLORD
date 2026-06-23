"""
migrate_v200.py — Migration vers l'architecture V2.0
Restructure D:\\OVERLORD\\ selon le plan Seiri/Seiton du document Gantt/PERT/5S.

Nouvelle structure :
  core/          → Agents fondamentaux (director, critic, watchdog, context_bus, config_manager)
  pipeline/      → Blocs du pipeline (sourcing, scenario, storyboard, prompt_engineer, quality_gate, postprod)
  intelligence/  → Agents cerveau (narrative_memory, style_continuity, auto_sourcing, prompt_library, character_designer, episode_planner)
  production/    → Agents rendu (agent_supervisor_v2, gpu_optimizer, quality_reviewer, lora_trainer)
  infra/         → Infrastructure (agent_registry, session_reporter, overlord_utils, grok_client, schema_validator)
  transmedia/    → Publication (transmedia_publisher, api_server)
  ui/            → Interfaces (overlord_launcher, overlord_auditor)
  tests/         → Tests (test_suite_v170, test_pipeline)
  maestro.py     → Racine (toujours)

Usage :
  python migrate_v200.py --dry-run   # Voir sans modifier
  python migrate_v200.py --apply     # Appliquer la migration
  python migrate_v200.py --rollback  # Restaurer depuis le backup
"""

import ast
import json
import re
import shutil
import sys
import io
from datetime import datetime
from pathlib import Path

if hasattr(sys.stdout, 'buffer'):
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

# ── Cartographie agent → nouveau dossier ────────────────────────────
AGENT_MAPPING = {
    # core/ — fondamentaux, toujours disponibles
    "director":           "core",
    "critic":             "core",
    "watchdog":           "core",
    "context_bus":        "core",
    "config_manager":     "core",
    "checkpoint_manager": "core",
    "overlord_utils_utf8":"core",

    # pipeline/ — blocs du pipeline dans l'ordre
    "sourcing":           "pipeline",
    "scenario":           "pipeline",
    "storyboard":         "pipeline",
    "prompt_engineer":    "pipeline",
    "quality_gate":       "pipeline",
    "postprod":           "pipeline",

    # intelligence/ — cerveau et mémoire
    "narrative_memory":   "intelligence",
    "style_continuity":   "intelligence",
    "auto_sourcing":      "intelligence",
    "prompt_library":     "intelligence",
    "character_designer": "intelligence",
    "episode_planner":    "intelligence",
    "director_v2":        "intelligence",

    # production/ — rendu ComfyUI
    "gpu_optimizer":      "production",
    "quality_reviewer":   "production",
    "lora_trainer":       "production",

    # infra/ — infrastructure transversale
    "agent_registry":     "infra",
    "session_reporter":   "infra",
    "overlord_utils":     "infra",
    "grok_client":        "infra",
    "schema_validator":   "infra",
    "dream_mode":         "infra",
    "agent_overclock":    "infra",

    # transmedia/ — publication
    "transmedia_publisher": "transmedia",
    "api_server":           "transmedia",

    # ui/ — interfaces utilisateur
    "overlord_launcher":  "ui",
    "overlord_auditor":   "ui",
}

# Fichiers à garder à la racine (jamais déplacés)
ROOT_FILES = {
    "maestro.py",
    "agent_supervisor_v2.py",
    "Combined_V35_API.json",
    "patch_workflow_v35.py",
    "install.bat",
    ".env",
    ".env.template",
    "requirements.txt",
    "README.md",
    "migrate_v200.py",
}

# Tests dans leur propre dossier
TEST_FILES = {"test_suite_v170", "test_pipeline", "test_integration"}

BACKUP_DIR = Path("workspace/migration_backup")
NEW_ROOT   = Path(".")


def scan_agents(agents_dir: Path = Path("agents")) -> dict:
    """Scanne les agents existants et retourne leur mapping."""
    found = {}
    for f in sorted(agents_dir.glob("*.py")):
        stem = f.stem
        if stem.startswith("__"):
            continue
        target = AGENT_MAPPING.get(stem)
        if not target:
            # Cherche par correspondance partielle
            for key, folder in AGENT_MAPPING.items():
                if key in stem or stem in key:
                    target = folder
                    break
        if not target:
            target = "agents"  # fallback : garder dans agents/
        found[stem] = {"path": f, "target": target}
    return found


def scan_root_py(root: Path = Path(".")) -> dict:
    """Scanne les .py à la racine qui ne sont pas dans ROOT_FILES."""
    found = {}
    for f in sorted(root.glob("*.py")):
        stem = f.stem
        if f.name in ROOT_FILES:
            continue
        if stem in TEST_FILES:
            found[stem] = {"path": f, "target": "tests"}
            continue
        target = AGENT_MAPPING.get(stem, "ui")  # default: ui pour les scripts racine
        found[stem] = {"path": f, "target": target}
    return found


def update_imports_in_file(src: str, mapping: dict) -> str:
    """
    Met à jour les imports d'un fichier selon le nouveau mapping.
    Remplace : from agents.X import → from {target}.X import
    """
    for agent_name, info in mapping.items():
        target = info["target"]
        if target == "agents":
            continue  # pas de changement
        old_import = f"from agents.{agent_name} import"
        new_import = f"from {target}.{agent_name} import"
        src = src.replace(old_import, new_import)
        old_import2 = f"import agents.{agent_name}"
        new_import2 = f"import {target}.{agent_name}"
        src = src.replace(old_import2, new_import2)
    return src


def dry_run(root: Path = Path(".")) -> dict:
    """Simulation sans modification."""
    agents_dir = root / "agents"
    agent_map  = scan_agents(agents_dir) if agents_dir.exists() else {}
    root_map   = scan_root_py(root)

    all_moves = {**agent_map, **root_map}

    print(f"\n{'═'*60}")
    print(f"  MIGRATION V2.0 — Dry Run")
    print(f"  {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    print(f"{'═'*60}")

    by_target = {}
    for name, info in all_moves.items():
        t = info["target"]
        by_target.setdefault(t, []).append(name)

    for target in sorted(by_target):
        print(f"\n  {target}/")
        for name in sorted(by_target[target]):
            print(f"    {name}.py")

    print(f"\n  Racine (inchangé) :")
    for f in sorted(root.glob("*.py")):
        if f.name in ROOT_FILES:
            print(f"    {f.name}")

    print(f"\n{'─'*60}")
    print(f"  Total agents à migrer : {len(all_moves)}")
    print(f"  Dossiers créés        : {len(set(i['target'] for i in all_moves.values()))}")
    print(f"{'═'*60}")
    print(f"\n  Lancer avec --apply pour effectuer la migration.")

    return all_moves


def apply_migration(root: Path = Path("."),
                    update_imports: bool = True) -> dict:
    """Applique la migration avec backup complet."""
    agents_dir = root / "agents"
    agent_map  = scan_agents(agents_dir) if agents_dir.exists() else {}
    root_map   = scan_root_py(root)
    all_moves  = {**agent_map, **root_map}

    # ── 1. Backup complet ─────────────────────────────────────────────
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    bk = BACKUP_DIR / ts
    bk.mkdir(parents=True, exist_ok=True)

    if agents_dir.exists():
        shutil.copytree(agents_dir, bk / "agents", dirs_exist_ok=True)
    for f in root.glob("*.py"):
        shutil.copy2(f, bk / f.name)

    print(f"[MIGRATION] Backup → {bk}")

    # ── 2. Créer les nouveaux dossiers avec __init__.py ───────────────
    new_dirs = set(i["target"] for i in all_moves.values())
    for d in new_dirs:
        if d == "agents":
            continue
        new_dir = root / d
        new_dir.mkdir(exist_ok=True)
        init_file = new_dir / "__init__.py"
        if not init_file.exists():
            init_file.write_text(
                f'"""{d} — Ov3rLoRd V2.0"""\n',
                encoding='utf-8'
            )
        print(f"[MIGRATION] Créé : {d}/")

    # tests/ spécial
    (root / "tests").mkdir(exist_ok=True)
    (root / "tests" / "__init__.py").write_text('"""tests"""\n', encoding='utf-8')

    # ── 3. Déplacer les fichiers ──────────────────────────────────────
    moved = []
    failed = []
    content_cache = {}  # nom_stem → nouveau contenu

    for name, info in all_moves.items():
        src_path = info["path"]
        target   = info["target"]

        if target == "agents":
            continue  # garder en place

        if target in TEST_FILES or name in TEST_FILES:
            dest_dir = root / "tests"
        else:
            dest_dir = root / target

        dest_path = dest_dir / src_path.name

        try:
            # Lire + mettre à jour les imports si demandé
            content = src_path.read_text(encoding='utf-8', errors='replace')
            if update_imports:
                content = update_imports_in_file(content, all_moves)

            dest_path.write_text(content, encoding='utf-8')
            content_cache[name] = content
            moved.append((src_path, dest_path))
            print(f"[MIGRATION] ✓ {src_path} → {dest_path}")
        except Exception as e:
            failed.append((src_path, str(e)))
            print(f"[MIGRATION] ✗ {src_path} : {e}")

    # ── 4. Mettre à jour maestro.py et agent_supervisor ───────────────
    for root_file in ["maestro.py", "agent_supervisor_v2.py"]:
        rf = root / root_file
        if rf.exists():
            content = rf.read_text(encoding='utf-8', errors='replace')
            updated = update_imports_in_file(content, all_moves)
            if updated != content:
                rf.write_text(updated, encoding='utf-8')
                print(f"[MIGRATION] ✓ Imports mis à jour : {root_file}")

    # ── 5. Supprimer les originaux (après validation syntaxe) ─────────
    removed = []
    for src_path, dest_path in moved:
        try:
            # Valider la destination avant de supprimer la source
            dest_content = dest_path.read_text(encoding='utf-8', errors='replace')
            ast.parse(dest_content)
            src_path.unlink()
            removed.append(src_path)
        except SyntaxError as e:
            print(f"[MIGRATION] ⚠ Syntaxe destination invalide, source conservée : {src_path.name} ({e})")
        except Exception as e:
            print(f"[MIGRATION] ⚠ Suppression échouée : {src_path.name} ({e})")

    # ── 6. Créer les __init__.py des sous-packages ────────────────────
    # Pour permettre les imports relatifs si nécessaire
    for d in new_dirs:
        if d != "agents":
            init = root / d / "__init__.py"
            files_in_dir = list((root / d).glob("*.py"))
            module_list  = [f.stem for f in files_in_dir if f.stem != "__init__"]
            init.write_text(
                f'"""{d} — Ov3rLoRd V2.0"""\n'
                f'# Modules: {", ".join(sorted(module_list))}\n',
                encoding='utf-8'
            )

    # ── Rapport ───────────────────────────────────────────────────────
    print(f"\n{'═'*60}")
    print(f"  MIGRATION TERMINÉE")
    print(f"  Déplacés  : {len(moved)}")
    print(f"  Supprimés : {len(removed)}")
    print(f"  Échecs    : {len(failed)}")
    print(f"  Backup    : {bk}")
    print(f"{'═'*60}")

    # Sauvegarder le rapport de migration
    report = {
        "timestamp":  datetime.now().isoformat(),
        "backup_dir": str(bk),
        "moved":      [(str(s), str(d)) for s, d in moved],
        "failed":     [(str(s), e) for s, e in failed],
        "removed":    [str(s) for s in removed],
    }
    (BACKUP_DIR / f"migration_report_{ts}.json").write_text(
        json.dumps(report, indent=2, ensure_ascii=False),
        encoding='utf-8'
    )

    return report


def rollback(root: Path = Path(".")) -> bool:
    """Restaure depuis le dernier backup."""
    if not BACKUP_DIR.exists():
        print("[ROLLBACK] Aucun backup trouvé")
        return False

    backups = sorted(BACKUP_DIR.iterdir(), key=lambda p: p.stat().st_mtime, reverse=True)
    backups = [b for b in backups if b.is_dir()]

    if not backups:
        print("[ROLLBACK] Aucun dossier de backup")
        return False

    latest = backups[0]
    print(f"[ROLLBACK] Restauration depuis : {latest}")

    # Restaurer agents/
    bk_agents = latest / "agents"
    if bk_agents.exists():
        agents_dest = root / "agents"
        if agents_dest.exists():
            shutil.rmtree(agents_dest)
        shutil.copytree(bk_agents, agents_dest)
        print("[ROLLBACK] ✓ agents/ restauré")

    # Restaurer les .py racine
    for f in latest.glob("*.py"):
        dest = root / f.name
        shutil.copy2(f, dest)
        print(f"[ROLLBACK] ✓ {f.name} restauré")

    print("[ROLLBACK] Terminé")
    return True


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Ov3rLoRd Migration V2.0")
    parser.add_argument("--dry-run",  action="store_true", help="Voir sans modifier")
    parser.add_argument("--apply",    action="store_true", help="Appliquer la migration")
    parser.add_argument("--rollback", action="store_true", help="Restaurer depuis backup")
    parser.add_argument("--no-import-update", action="store_true",
                        help="Ne pas mettre à jour les imports")
    args = parser.parse_args()

    root = Path(".")

    if args.rollback:
        rollback(root)
    elif args.apply:
        print("⚠  Cette opération restructure D:\\OVERLORD\\.")
        print("   Un backup complet sera créé automatiquement.")
        confirm = input("   Confirmer ? (oui/non) : ").strip().lower()
        if confirm == "oui":
            apply_migration(root, update_imports=not args.no_import_update)
        else:
            print("Migration annulée.")
    else:
        # Dry run par défaut
        dry_run(root)
        print("\nUtiliser --apply pour effectuer la migration.")
        print("Utiliser --rollback pour restaurer si problème.")

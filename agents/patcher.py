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
patcher.py — Ov3rLoRd Patch Agent V1.0
Usage : python patcher.py [--bundle patch_bundle.txt] [--dry-run] [--backup]
Lit un fichier bundle de patches et applique CREATE/UPDATE sur le disque.
"""

import sys
import os
import re
import shutil
import argparse
import ast
from pathlib import Path
from datetime import datetime

# ─── Config ───────────────────────────────────────────────────────────────────
BUNDLE_DEFAULT   = "patch_bundle.txt"
BACKUP_DIR       = Path("workspace/patch_backups")
PROTECTED_FILES  = {"self_improve.py", "licence_server.py", "config.json", ".env", "patcher.py"}
LOG_FILE         = Path("workspace/logs/patcher.log")
MAX_SIZE_RATIO   = 3.0   # Refuse si le nouveau fichier fait >3x la taille de l'original

# ─── Logging ──────────────────────────────────────────────────────────────────
def _log(msg: str, level: str = "INFO"):
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    line = f"[{ts}] [{level}] {msg}"
    print(line)
    try:
        LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
        with open(LOG_FILE, "a", encoding="utf-8") as f:
            f.write(line + "\n")
    except Exception:
        pass

def log_info(msg):  _log(msg, "INFO")
def log_ok(msg):    _log(msg, "OK  ")
def log_warn(msg):  _log(msg, "WARN")
def log_err(msg):   _log(msg, "ERR ")

# ─── Parser du bundle ─────────────────────────────────────────────────────────
HEADER_RE = re.compile(
    r"\[ACTION:\s*(CREATE|UPDATE)\s*\|\s*FILE:\s*(.+?)\]",
    re.IGNORECASE
)
SECTION_RE = re.compile(
    r"\[(CONTENU|EXPLICATION):\s*\]",
    re.IGNORECASE
)

def parse_bundle(bundle_path: Path) -> list[dict]:
    """
    Découpe le bundle en liste de patches :
    [{"action": "CREATE|UPDATE", "file": "...", "contenu": "...", "explication": "..."}]

    Format attendu dans le bundle :
    ──────────────────────────────
    [ACTION: CREATE | FILE: agents/mon_agent.py]
    [CONTENU:]
    <code Python>
    [EXPLICATION:]
    Pourquoi ce fichier, impact sur le pipeline.
    ──────────────────────────────
    """
    text = bundle_path.read_text(encoding="utf-8")
    patches = []

    # Découpe sur les headers ACTION
    blocks = HEADER_RE.split(text)
    # blocks = [pre, action1, file1, body1, action2, file2, body2, ...]
    i = 1
    while i < len(blocks) - 2:
        action = blocks[i].strip().upper()
        filepath = blocks[i + 1].strip()
        body = blocks[i + 2]

        contenu = ""
        explication = ""

        # Sépare CONTENU et EXPLICATION dans le body
        parts = re.split(r"\[CONTENU:\s*\]|\[EXPLICATION:\s*\]", body, flags=re.IGNORECASE)
        if len(parts) == 3:
            # parts[0] = vide, parts[1] = contenu, parts[2] = explication
            contenu     = parts[1].strip("\n")
            explication = parts[2].strip()
        elif len(parts) == 2:
            contenu = parts[1].strip("\n")
        else:
            contenu = body.strip("\n")

        patches.append({
            "action":      action,
            "file":        filepath,
            "contenu":     contenu,
            "explication": explication,
        })
        i += 3

    return patches

# ─── Validation ───────────────────────────────────────────────────────────────
def validate_python(code: str, filepath: str) -> bool:
    """Vérifie la syntaxe Python si l'extension est .py"""
    if not filepath.endswith(".py"):
        return True
    try:
        ast.parse(code)
        return True
    except SyntaxError as e:
        log_err(f"  Syntaxe invalide dans {filepath} : {e}")
        return False

def is_protected(filepath: str) -> bool:
    name = Path(filepath).name
    return name in PROTECTED_FILES

def check_size_ratio(target: Path, new_content: str) -> bool:
    if not target.exists():
        return True
    old_size = target.stat().st_size
    new_size = len(new_content.encode("utf-8"))
    if old_size > 0 and (new_size / old_size) > MAX_SIZE_RATIO:
        log_warn(f"  Ratio taille suspect ({new_size}/{old_size} = {new_size/old_size:.1f}x). Patch bloqué.")
        return False
    return True

# ─── Application ──────────────────────────────────────────────────────────────
def backup_file(target: Path):
    if not target.exists():
        return
    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    dest = BACKUP_DIR / f"{target.name}.{ts}.bak"
    shutil.copy2(target, dest)
    log_info(f"  Backup → {dest}")

def apply_patch(patch: dict, dry_run: bool = False, do_backup: bool = True) -> bool:
    action   = patch["action"]
    filepath = patch["file"]
    contenu  = patch["contenu"]
    expl     = patch["explication"]

    target = Path(filepath)

    log_info(f"── [{action}] {filepath}")
    if expl:
        log_info(f"   Raison : {expl[:120]}{'...' if len(expl) > 120 else ''}")

    # Garde-fous
    if is_protected(filepath):
        log_err(f"  BLOQUÉ — fichier protégé : {filepath}")
        return False

    if action == "CREATE" and target.exists():
        log_warn(f"  Le fichier existe déjà. Traité comme UPDATE.")
        action = "UPDATE"

    if action == "UPDATE" and not target.exists():
        log_warn(f"  Fichier introuvable pour UPDATE, création forcée.")
        action = "CREATE"

    if not validate_python(contenu, filepath):
        return False

    if not check_size_ratio(target, contenu):
        return False

    if dry_run:
        log_ok(f"  [DRY-RUN] Serait appliqué : {action} {filepath} ({len(contenu)} chars)")
        return True

    # Backup avant écrasement
    if action == "UPDATE" and do_backup:
        backup_file(target)

    # Écriture
    try:
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(contenu, encoding="utf-8")
        log_ok(f"  ✓ {action} → {filepath} ({len(contenu)} chars)")
        return True
    except Exception as e:
        log_err(f"  Échec écriture {filepath} : {e}")
        return False

# ─── Main ─────────────────────────────────────────────────────────────────────
def main():
    parser = argparse.ArgumentParser(description="Ov3rLoRd Patcher V1.0")
    parser.add_argument("--bundle",  default=BUNDLE_DEFAULT, help="Fichier bundle de patches")
    parser.add_argument("--dry-run", action="store_true",   help="Simule sans écrire")
    parser.add_argument("--backup",  action="store_true",   help="Backup avant UPDATE (défaut: activé)")
    parser.add_argument("--no-backup", action="store_true", help="Désactive les backups")
    args = parser.parse_args()

    do_backup = not args.no_backup

    print("=" * 60)
    print("  Ov3rLoRd Patcher V1.0")
    print(f"  Bundle  : {args.bundle}")
    print(f"  Dry-run : {args.dry_run}")
    print(f"  Backup  : {do_backup}")
    print("=" * 60)

    bundle_path = Path(args.bundle)
    if not bundle_path.exists():
        log_err(f"Bundle introuvable : {bundle_path}")
        sys.exit(1)

    patches = parse_bundle(bundle_path)
    if not patches:
        log_warn("Aucun patch trouvé dans le bundle. Vérifier le format.")
        sys.exit(0)

    log_info(f"{len(patches)} patch(es) détecté(s)")

    ok_count  = 0
    err_count = 0

    for patch in patches:
        success = apply_patch(patch, dry_run=args.dry_run, do_backup=do_backup)
        if success:
            ok_count += 1
        else:
            err_count += 1

    print("=" * 60)
    print(f"  Résultat : {ok_count} OK | {err_count} ERREUR(S)")
    print("=" * 60)

    if err_count > 0:
        sys.exit(1)

if __name__ == "__main__":
    main()

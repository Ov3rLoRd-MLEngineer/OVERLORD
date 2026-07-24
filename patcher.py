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
patcher.py — Ov3rLoRd Patch Agent V1.1
Usage : python patcher.py [bundle] [--dry-run] [--backup]

Supporte DEUX formats de bundle :

FORMAT A — Find/Replace (V1.70a) :
  ==== FILE: chemin/fichier.py ====
  ==== FIND ====
  <texte exact à trouver>
  ==== REPLACE ====
  <texte de remplacement>
  ==== END ====

FORMAT B — Create/Update complet (V1.0) :
  [ACTION: CREATE|UPDATE | FILE: chemin/fichier.py]
  [CONTENU:]
  <contenu complet du fichier>
  [EXPLICATION:]
  Pourquoi ce changement.
"""

import sys
import os
import re
import shutil
import argparse
import ast
from pathlib import Path
from datetime import datetime

# ─── Config ──────────────────────────────────────────────────────────
BUNDLE_DEFAULT  = "patch_bundle.txt"
BACKUP_DIR      = Path("workspace/patch_backups")
PROTECTED_FILES = {"self_improve.py", "licence_server.py",
                   "config.json", ".env", "patcher.py"}
LOG_FILE        = Path("workspace/logs/patcher.log")
MAX_SIZE_RATIO  = 3.0

# ─── Logging ─────────────────────────────────────────────────────────
def _log(msg: str, level: str = "INFO"):
    ts   = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    line = f"[{ts}] [{level}] {msg}"
    print(line)
    try:
        LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
        with open(LOG_FILE, "a", encoding="utf-8") as f:
            f.write(line + "\n")
    except Exception:
        pass

def log_info(m): _log(m, "INFO")
def log_ok(m):   _log(m, "OK  ")
def log_warn(m): _log(m, "WARN")
def log_err(m):  _log(m, "ERR ")

# ─── Détection du format ─────────────────────────────────────────────
def detect_format(text: str) -> str:
    """Détecte le format du bundle : 'find_replace' ou 'create_update'."""
    if re.search(r'^==== FILE:', text, re.MULTILINE):
        return "find_replace"
    if re.search(r'\[ACTION:\s*(CREATE|UPDATE)', text, re.IGNORECASE):
        return "create_update"
    return "unknown"

# ─── Parser FORMAT A — Find/Replace ──────────────────────────────────
def parse_find_replace(text: str) -> list[dict]:
    """
    Parse le format ==== FILE / FIND / REPLACE / END ====
    Retourne une liste de patches avec action='FIND_REPLACE'.
    """
    patches = []

    # Découper par bloc FILE
    file_blocks = re.split(r'^==== FILE:\s*(.+?)\s*====\s*$',
                            text, flags=re.MULTILINE)
    # file_blocks = [pre, filename1, body1, filename2, body2, ...]

    i = 1
    while i < len(file_blocks) - 1:
        filename = file_blocks[i].strip()
        body     = file_blocks[i + 1]

        # Extraire les paires FIND/REPLACE/END dans ce bloc fichier
        # Découper sur les marqueurs
        segments = re.split(
            r'^==== (FIND|REPLACE|END) ====\s*$',
            body, flags=re.MULTILINE
        )
        # segments = [pre, marker1, content1, marker2, content2, ...]

        j = 1
        while j < len(segments) - 2:
            marker  = segments[j].strip()
            content = segments[j + 1]
            if marker == "FIND":
                find_text = content
                # Chercher le REPLACE suivant
                if j + 2 < len(segments) and segments[j + 2].strip() == "REPLACE":
                    replace_text = segments[j + 3] if j + 3 < len(segments) else ""
                    patches.append({
                        "action":   "FIND_REPLACE",
                        "file":     filename,
                        "find":     find_text,
                        "replace":  replace_text,
                        "contenu":  "",
                        "explication": "",
                    })
                    j += 4  # sauter FIND + content + REPLACE + content
                    continue
            j += 2

        i += 2

    return patches

# ─── Parser FORMAT B — Create/Update ─────────────────────────────────
HEADER_RE = re.compile(
    r"\[ACTION:\s*(CREATE|UPDATE)\s*\|\s*FILE:\s*(.+?)\]",
    re.IGNORECASE
)

def parse_create_update(text: str) -> list[dict]:
    """Parse le format [ACTION: ... | FILE: ...] / [CONTENU:] / [EXPLICATION:]"""
    patches = []
    blocks  = HEADER_RE.split(text)
    i = 1
    while i < len(blocks) - 2:
        action   = blocks[i].strip().upper()
        filepath = blocks[i + 1].strip()
        body     = blocks[i + 2]

        parts = re.split(r'\[CONTENU:\s*\]|\[EXPLICATION:\s*\]',
                         body, flags=re.IGNORECASE)
        if len(parts) == 3:
            contenu     = parts[1].strip("\n")
            explication = parts[2].strip()
        elif len(parts) == 2:
            contenu     = parts[1].strip("\n")
            explication = ""
        else:
            contenu     = body.strip("\n")
            explication = ""

        patches.append({
            "action":      action,
            "file":        filepath,
            "find":        "",
            "replace":     "",
            "contenu":     contenu,
            "explication": explication,
        })
        i += 3
    return patches

# ─── Parser principal ─────────────────────────────────────────────────
def parse_bundle(bundle_path: Path) -> list[dict]:
    text   = bundle_path.read_text(encoding="utf-8")
    fmt    = detect_format(text)
    log_info(f"Format bundle détecté : {fmt}")

    if fmt == "find_replace":
        return parse_find_replace(text)
    elif fmt == "create_update":
        return parse_create_update(text)
    else:
        log_err("Format de bundle non reconnu.")
        log_err("Formats supportés :")
        log_err("  A) ==== FILE: f.py ==== / ==== FIND ==== / ==== REPLACE ==== / ==== END ====")
        log_err("  B) [ACTION: UPDATE | FILE: f.py] / [CONTENU:] / [EXPLICATION:]")
        return []

# ─── Validation ──────────────────────────────────────────────────────
def validate_python(code: str, filepath: str) -> bool:
    if not filepath.endswith(".py"):
        return True
    try:
        ast.parse(code)
        return True
    except SyntaxError as e:
        log_err(f"  Syntaxe invalide : {e}")
        return False

def is_protected(filepath: str) -> bool:
    return Path(filepath).name in PROTECTED_FILES

def check_size_ratio(target: Path, new_content: str) -> bool:
    if not target.exists():
        return True
    old_size = target.stat().st_size
    new_size = len(new_content.encode("utf-8"))
    if old_size > 0 and (new_size / old_size) > MAX_SIZE_RATIO:
        log_warn(f"  Ratio taille suspect ({new_size}/{old_size} = "
                 f"{new_size/old_size:.1f}x). Patch bloqué.")
        return False
    return True

# ─── Backup ──────────────────────────────────────────────────────────
def backup_file(target: Path):
    if not target.exists():
        return
    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    ts   = datetime.now().strftime("%Y%m%d_%H%M%S")
    dest = BACKUP_DIR / f"{target.name}.{ts}.bak"
    shutil.copy2(target, dest)
    log_info(f"  Backup → {dest}")

# ─── Application d'un patch ──────────────────────────────────────────
def apply_patch(patch: dict, dry_run: bool = False,
                do_backup: bool = True) -> bool:
    action   = patch["action"]
    filepath = patch["file"]

    # Résoudre le chemin — strip D:\OVERLORD\ si présent
    fp_clean = filepath.replace("D:\\OVERLORD\\", "").replace("D:/OVERLORD/", "")
    target   = Path(fp_clean)

    log_info(f"── [{action}] {fp_clean}")

    if is_protected(filepath):
        log_err(f"  BLOQUÉ — fichier protégé : {fp_clean}")
        return False

    # ── FORMAT A : Find/Replace ───────────────────────────────────────
    if action == "FIND_REPLACE":
        if not target.exists():
            log_err(f"  Fichier cible introuvable : {fp_clean}")
            return False

        source = target.read_text(encoding="utf-8")
        find_text    = patch["find"]
        replace_text = patch["replace"]

        # Nettoyage : retirer un éventuel \n initial/final issu du parsing
        find_clean    = find_text.lstrip("\n").rstrip("\n")
        replace_clean = replace_text.lstrip("\n").rstrip("\n")

        if find_clean not in source:
            log_err(f"  Texte FIND non trouvé dans {fp_clean}")
            log_err(f"  Début FIND attendu : {repr(find_clean[:80])}")
            return False

        occurrences = source.count(find_clean)
        if occurrences > 1:
            log_warn(f"  {occurrences} occurrences trouvées — seule la 1ère sera remplacée")

        new_source = source.replace(find_clean, replace_clean, 1)

        if not validate_python(new_source, fp_clean):
            return False

        if not check_size_ratio(target, new_source):
            return False

        if dry_run:
            log_ok(f"  [DRY-RUN] FIND_REPLACE dans {fp_clean} "
                   f"({len(find_clean)} → {len(replace_clean)} chars)")
            return True

        if do_backup:
            backup_file(target)

        try:
            target.write_text(new_source, encoding="utf-8")
            log_ok(f"  ✓ FIND_REPLACE appliqué dans {fp_clean}")
            return True
        except Exception as e:
            log_err(f"  Échec écriture : {e}")
            return False

    # ── FORMAT B : Create/Update ──────────────────────────────────────
    contenu = patch["contenu"]
    expl    = patch.get("explication", "")

    if expl:
        log_info(f"   Raison : {expl[:120]}")

    if action == "CREATE" and target.exists():
        log_warn("  Fichier existe déjà → traité comme UPDATE")
        action = "UPDATE"

    if action == "UPDATE" and not target.exists():
        log_warn("  Fichier introuvable → création forcée")
        action = "CREATE"

    if not validate_python(contenu, fp_clean):
        return False

    if not check_size_ratio(target, contenu):
        return False

    if dry_run:
        log_ok(f"  [DRY-RUN] {action} {fp_clean} ({len(contenu)} chars)")
        return True

    if action == "UPDATE" and do_backup:
        backup_file(target)

    try:
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(contenu, encoding="utf-8")
        log_ok(f"  ✓ {action} → {fp_clean} ({len(contenu)} chars)")
        return True
    except Exception as e:
        log_err(f"  Échec écriture {fp_clean} : {e}")
        return False

# ─── Main ─────────────────────────────────────────────────────────────
def main():
    ap = argparse.ArgumentParser(description="Ov3rLoRd Patcher V1.1")
    ap.add_argument("bundle",      nargs="?", default=BUNDLE_DEFAULT,
                    help="Fichier bundle de patches")
    ap.add_argument("--bundle",    dest="bundle_opt", default=None,
                    help="Alias --bundle (optionnel)")
    ap.add_argument("--dry-run",   action="store_true")
    ap.add_argument("--backup",    action="store_true")
    ap.add_argument("--no-backup", action="store_true")
    args = ap.parse_args()

    bundle_file = args.bundle_opt or args.bundle
    do_backup   = not args.no_backup

    print("=" * 60)
    print("  Ov3rLoRd Patcher V1.1")
    print(f"  Bundle  : {bundle_file}")
    print(f"  Dry-run : {args.dry_run}")
    print(f"  Backup  : {do_backup}")
    print("=" * 60)

    bundle_path = Path(bundle_file)
    if not bundle_path.exists():
        log_err(f"Bundle introuvable : {bundle_path}")
        sys.exit(1)

    patches = parse_bundle(bundle_path)
    if not patches:
        log_warn("Aucun patch trouvé. Vérifier le format du bundle.")
        sys.exit(0)

    log_info(f"{len(patches)} patch(es) détecté(s)")

    ok_count  = 0
    err_count = 0

    for patch in patches:
        ok = apply_patch(patch, dry_run=args.dry_run, do_backup=do_backup)
        if ok:
            ok_count += 1
        else:
            err_count += 1

    print("=" * 60)
    print(f"  Résultat : {ok_count} OK | {err_count} ERREUR(S)")
    print("=" * 60)

    if err_count:
        sys.exit(1)

if __name__ == "__main__":
    main()

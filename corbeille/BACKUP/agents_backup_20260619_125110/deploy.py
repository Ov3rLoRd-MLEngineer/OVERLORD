"""
deploy.py — Deploiement automatique Ov3rLoRd V1.49
Dezippe une archive ZIP du projet et applique les fichiers
avec backup automatique des fichiers existants.

Usage :
  python deploy.py --zip OverLord_Pipeline_V149_FULL.zip
  python deploy.py --zip patch.zip --dry-run
  python deploy.py --zip patch.zip --target D:\\OVERLORD
"""
import sys
import os
import zipfile
import shutil
import argparse
import hashlib
from pathlib import Path
from datetime import datetime

# ── Config ────────────────────────────────────────────────────────────────────
PROTECTED = {".env", "config.json", "self_improve.py", "licence_server.py"}
BACKUP_ROOT = Path("workspace/deploy_backups")
LOG_PATH    = Path("workspace/logs/deploy.log")

def _log(msg: str, level: str = "INFO"):
    ts   = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    line = f"[{ts}] [{level}] {msg}"
    print(line)
    try:
        LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
        with open(LOG_PATH, "a", encoding="utf-8") as f:
            f.write(line + "\n")
    except Exception:
        pass

def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    h.update(path.read_bytes())
    return h.hexdigest()[:12]

def _backup(path: Path, backup_dir: Path):
    if not path.exists():
        return
    backup_dir.mkdir(parents=True, exist_ok=True)
    ts   = datetime.now().strftime("%Y%m%d_%H%M%S")
    dest = backup_dir / f"{path.name}.{ts}.bak"
    shutil.copy2(path, dest)
    _log(f"  Backup -> {dest}", "BAK ")

def deploy(zip_path: Path, target: Path, dry_run: bool = False):
    if not zip_path.exists():
        _log(f"Archive introuvable : {zip_path}", "ERR ")
        sys.exit(1)

    ts         = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_dir = BACKUP_ROOT / ts

    _log(f"=== Deploy Ov3rLoRd depuis {zip_path.name} -> {target} ===")
    _log(f"    Dry-run : {dry_run}")

    ok_count  = 0
    skip_count = 0
    err_count  = 0

    with zipfile.ZipFile(zip_path, 'r') as zf:
        members = [m for m in zf.infolist() if not m.filename.endswith('/')]
        _log(f"    Fichiers dans l'archive : {len(members)}")

        for member in members:
            rel_path = Path(member.filename)
            dest     = target / rel_path

            # Protection
            if rel_path.name in PROTECTED:
                _log(f"  [SKIP] Protege : {rel_path}", "SKIP")
                skip_count += 1
                continue

            # Hash check — skip si identique
            raw = zf.read(member.filename)
            if dest.exists():
                existing_hash = hashlib.sha256(dest.read_bytes()).hexdigest()[:12]
                new_hash      = hashlib.sha256(raw).hexdigest()[:12]
                if existing_hash == new_hash:
                    skip_count += 1
                    continue
                if not dry_run:
                    _backup(dest, backup_dir)

            if dry_run:
                _log(f"  [DRY] {rel_path} ({len(raw)} bytes)", "DRY ")
                ok_count += 1
                continue

            try:
                dest.parent.mkdir(parents=True, exist_ok=True)
                dest.write_bytes(raw)
                _log(f"  [OK] {rel_path}", "OK  ")
                ok_count += 1
            except Exception as e:
                _log(f"  [ERR] {rel_path} : {e}", "ERR ")
                err_count += 1

    _log(f"=== Resultat : {ok_count} deployes | {skip_count} skips | {err_count} erreurs ===")
    if err_count > 0:
        sys.exit(1)

def main():
    p = argparse.ArgumentParser(description="Deploy Ov3rLoRd depuis ZIP")
    p.add_argument("--zip",     required=True,        help="Archive ZIP source")
    p.add_argument("--target",  default=".",           help="Dossier cible (defaut: .)")
    p.add_argument("--dry-run", action="store_true",   help="Simule sans ecrire")
    args = p.parse_args()

    deploy(Path(args.zip), Path(args.target), dry_run=args.dry_run)

if __name__ == "__main__":
    main()
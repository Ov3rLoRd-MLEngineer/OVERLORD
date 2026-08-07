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
reset_hard.py — Reset COMPLET : state + tous les checkpoints en cours
Colle dans D:\OVERLORD\ et lance : python reset_hard.py
"""
import json, shutil
from pathlib import Path
from datetime import datetime

ts = datetime.now().strftime('%H%M%S')

# 1. Reset pipeline_state.json
state_file = Path("workspace/pipeline_state.json")
if state_file.exists():
    shutil.copy2(state_file, state_file.with_suffix(f".{ts}.bak"))
state_file.write_text(json.dumps({
    "run_id": None, "current_block": None,
    "completed": [], "data": {}
}, indent=2), encoding="utf-8")
print(f"✓ pipeline_state.json remis à zéro")

# 2. Supprimer les checkpoints interrompus
cp_dir = Path("workspace/checkpoints")
if cp_dir.exists():
    interrupted = list(cp_dir.glob("*interrupted*")) + \
                  list(cp_dir.glob("*emergency*"))
    backup_dir = Path("workspace/patch_backups/old_checkpoints")
    backup_dir.mkdir(parents=True, exist_ok=True)
    for f in interrupted:
        shutil.move(str(f), backup_dir / f.name)
        print(f"  Archivé : {f.name}")
    
    # Aussi déplacer tous les checkpoints du dernier run cassé
    for f in sorted(cp_dir.glob("maestro_20260622_02*.json")):
        shutil.move(str(f), backup_dir / f.name)
        print(f"  Archivé : {f.name}")
    for f in sorted(cp_dir.glob("maestro_20260622_04*.json")):
        shutil.move(str(f), backup_dir / f.name)
        print(f"  Archivé : {f.name}")

print()
print("✓ Reset complet — tous les checkpoints cassés archivés")
print()
print("Lance maintenant :")
print('  python maestro.py --media-type anime --universe "evangelion battle mecha girl"')

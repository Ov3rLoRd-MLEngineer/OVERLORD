"""
reset_total.py — Vide TOUT : state + TOUS les checkpoints sans exception
"""
import json, shutil
from pathlib import Path
from datetime import datetime

ts      = datetime.now().strftime('%H%M%S')
archive = Path(f"workspace/patch_backups/checkpoints_{ts}")
archive.mkdir(parents=True, exist_ok=True)

# 1. Reset state
state = Path("workspace/pipeline_state.json")
if state.exists():
    shutil.copy2(state, archive / "pipeline_state.bak")
state.write_text(json.dumps({
    "run_id": None, "current_block": None,
    "completed": [], "data": {}
}, indent=2), encoding="utf-8")
print("✓ pipeline_state.json → zéro")

# 2. Vider TOUT le dossier checkpoints
cp_dir = Path("workspace/checkpoints")
if cp_dir.exists():
    files = list(cp_dir.glob("*.json"))
    for f in files:
        shutil.move(str(f), archive / f.name)
    print(f"✓ {len(files)} checkpoints archivés → {archive}")
else:
    print("  workspace/checkpoints/ vide ou inexistant")

# 3. Vider aussi workspace/state/ si existe
for alt in [Path("workspace/state"), Path("workspace/states")]:
    if alt.exists():
        for f in alt.glob("*.json"):
            shutil.move(str(f), archive / f.name)
        print(f"✓ {alt} vidé")

print()
print("Run propre garanti. Lance :")
print('  python maestro.py --media-type anime --universe "evangelion battle mecha girl"')

"""
reset_checkpoint.py — Remet le checkpoint a zero pour forcer un run propre
Colle dans D:\OVERLORD\ et lance : python reset_checkpoint.py
"""
import json
from pathlib import Path
from datetime import datetime

# Trouver le fichier de state
candidates = [
    Path("workspace/pipeline_state.json"),
    Path("workspace/state.json"),
    Path("pipeline_state.json"),
]

state_file = None
for c in candidates:
    if c.exists():
        state_file = c
        break

if not state_file:
    # Chercher dans workspace/
    ws = Path("workspace")
    if ws.exists():
        found = list(ws.glob("*state*.json"))
        if found:
            state_file = found[0]

if not state_file:
    print("Aucun fichier de state trouve — deja propre")
else:
    # Backup
    backup = state_file.with_suffix(f".{datetime.now().strftime('%H%M%S')}.bak")
    backup.write_bytes(state_file.read_bytes())
    print(f"Backup : {backup}")

    # Reset
    state_file.write_text(
        json.dumps({
            "run_id": None,
            "current_block": None,
            "completed": [],
            "data": {}
        }, indent=2),
        encoding="utf-8"
    )
    print(f"State remis a zero : {state_file}")

print()
print("Lance maintenant :")
print('  python maestro.py --media-type anime --universe "evangelion battle mecha girl"')

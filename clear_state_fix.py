# clear_state_fix.py — colle dans D:\OVERLORD\ et lance : python clear_state_fix.py
# Remplace le workaround -c par un script dédié qui gère stdout proprement

import sys
import io

# Protéger stdout AVANT tout import de maestro
try:
    if sys.stdout is None or sys.stdout.closed:
        sys.stdout = io.TextIOWrapper(
            io.FileIO(1, closefd=False),
            encoding="utf-8", errors="replace"
        )
except Exception:
    sys.stdout = io.TextIOWrapper(
        io.FileIO(1, closefd=False),
        encoding="utf-8", errors="replace"
    )

from maestro import clear_state
clear_state()
sys.stdout.write("State cleared\n")
sys.stdout.flush()

"""
fix_5080_steps.py — Corrige les steps RTX 5080 dans gpu_optimizer.py
Colle dans D:\OVERLORD\ et lance : python fix_5080_steps.py
"""
import re, shutil, ast
from pathlib import Path
from datetime import datetime

target = Path("agents/gpu_optimizer.py")
src    = target.read_text(encoding="utf-8")

# Afficher le contexte autour de rtx5080
print("=== Contexte rtx5080 dans gpu_optimizer.py ===")
lines = src.splitlines()
for i, line in enumerate(lines):
    if "rtx5080" in line.lower() or ("steps" in line and i > 0 and "rtx5080" in "\n".join(lines[max(0,i-5):i]).lower()):
        print(f"  {i+1:4d}: {repr(line)}")

# Chercher et remplacer steps > 50 dans le bloc rtx5080
# Pattern : dans le bloc rtx5080, trouver "steps" et changer la valeur
pattern = r'("rtx5080"[^}]{0,200}"steps"\s*:\s*)(\d+)'
match = re.search(pattern, src, re.DOTALL)
if match:
    current_steps = int(match.group(2))
    print(f"\nSteps actuels : {current_steps}")
    if current_steps > 50:
        new_src = re.sub(pattern,
                         lambda m: m.group(1) + "35",
                         src, count=1, flags=re.DOTALL)
        # Vérifier syntaxe
        try:
            ast.parse(new_src)
        except SyntaxError as e:
            print(f"ERREUR syntaxe : {e}")
            exit(1)
        # Backup
        backup = Path(f"workspace/patch_backups/gpu_optimizer.{datetime.now().strftime('%H%M%S')}.bak")
        backup.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(target, backup)
        target.write_text(new_src, encoding="utf-8")
        print(f"✓ Steps 5080 : {current_steps} → 35")
    else:
        print(f"Steps déjà à {current_steps} — rien à faire")
else:
    print("Pattern rtx5080/steps non trouvé — affichage du bloc rtx5080 :")
    in_block = False
    for i, line in enumerate(lines):
        if "rtx5080" in line:
            in_block = True
        if in_block:
            print(f"  {i+1:4d}: {repr(line)}")
        if in_block and "}" in line and i > 0:
            break

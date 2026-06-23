"""
fix_storyboard_title.py — Fix direct NameError title dans storyboard.py
Colle dans D:\OVERLORD\ et lance : python fix_storyboard_title.py
"""
from pathlib import Path
import ast, shutil
from datetime import datetime

target = Path("agents/storyboard.py")
src    = target.read_text(encoding="utf-8")

# Chercher la ligne exacte avec le bug
bug_line = '    sketches_dir = Path("workspace/storyboards/sketches") / (title or "run")'
fix_line = '    _sb_title    = storyboard.get("title", "run") if isinstance(storyboard, dict) else "run"\n    sketches_dir = Path("workspace/storyboards/sketches") / (_sb_title or "run")'

if bug_line not in src:
    print("Ligne cible introuvable — cherche la variante...")
    # Chercher par mot-clé
    for i, line in enumerate(src.splitlines()):
        if 'sketches_dir' in line and 'title' in line:
            print(f"  Ligne {i+1}: {repr(line)}")
    print("Envoie ces lignes à Claude.")
else:
    # Backup
    backup = Path(f"workspace/patch_backups/storyboard.py.fix_title.{datetime.now().strftime('%H%M%S')}.bak")
    backup.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(target, backup)
    print(f"Backup → {backup}")

    new_src = src.replace(bug_line, fix_line, 1)

    try:
        ast.parse(new_src)
        print("Syntaxe OK")
    except SyntaxError as e:
        print(f"ERREUR syntaxe : {e}")
        exit(1)

    target.write_text(new_src, encoding="utf-8")
    print("✓ Fix appliqué — NameError title corrigé")
    print()
    print("Lance maintenant :")
    print("  python reset_checkpoint.py")
    print('  python maestro.py --media-type anime --universe "evangelion battle mecha girl"')

"""
fix_sketch_dirname.py — Sanitize le nom de dossier sketches dans storyboard.py
Remplace les caractères interdits Windows dans le titre utilisé comme dossier.
Colle dans D:\OVERLORD\ et lance : python fix_sketch_dirname.py
"""
import re, shutil, ast
from pathlib import Path
from datetime import datetime

target = Path("agents/storyboard.py")
src    = target.read_text(encoding="utf-8")

# Chercher la ligne avec sketches_dir et _sb_title
old = '    _sb_title    = storyboard.get("title", "run") if isinstance(storyboard, dict) else "run"\n    sketches_dir = Path("workspace/storyboards/sketches") / (_sb_title or "run")'

new = '''    _sb_title    = storyboard.get("title", "run") if isinstance(storyboard, dict) else "run"
    # Sanitize : supprimer les caractères interdits Windows dans les noms de dossier
    import re as _re
    _sb_title = _re.sub(r'[\\\\/:*?"<>|]', '_', _sb_title or "run")[:60]
    sketches_dir = Path("workspace/storyboards/sketches") / (_sb_title or "run")'''

if old in src:
    backup = Path(f"workspace/patch_backups/storyboard.{datetime.now().strftime('%H%M%S')}.bak")
    backup.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(target, backup)
    new_src = src.replace(old, new, 1)
    ast.parse(new_src)
    target.write_text(new_src, encoding="utf-8")
    print("✓ Fix WinError 267 appliqué — titres sanitizés")
else:
    # Chercher la ligne exacte dans le fichier
    lines = src.splitlines()
    for i, line in enumerate(lines):
        if 'sketches_dir' in line and '_sb_title' in line:
            print(f"Ligne {i+1}: {repr(line)}")
        if '_sb_title' in line and 'storyboard.get' in line:
            print(f"Ligne {i+1}: {repr(line)}")
    print()
    print("Texte non trouvé — envoie les lignes ci-dessus à Claude")

# Aussi vérifier et créer agents/overlord_utils.py si absent
agents_utils = Path("agents/overlord_utils.py")
root_utils   = Path("overlord_utils.py")
utf8_utils   = Path("overlord_utils_utf8.py")

if not agents_utils.exists():
    source = root_utils if root_utils.exists() else utf8_utils
    if source.exists():
        agents_utils.write_text(f'''import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))
from {source.stem} import *
try:
    from {source.stem} import fallback_llm, safe_json_parse
except ImportError:
    pass
''', encoding="utf-8")
        print(f"✓ agents/overlord_utils.py créé (→ {source.name})")
    else:
        print("⚠ overlord_utils source non trouvée")
else:
    print("✓ agents/overlord_utils.py existe déjà")

print()
print("Lance maintenant :")
print("  python reset_total.py")
print('  python maestro.py --media-type anime --universe "evangelion battle mecha girl"')

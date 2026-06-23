"""
fix_overlord_utils_path.py — Crée overlord_utils.py à la racine 
depuis overlord_utils_utf8.py si nécessaire, et crée un agents/overlord_utils.py
qui redirige vers la racine.
Colle dans D:\OVERLORD\ et lance : python fix_overlord_utils_path.py
"""
from pathlib import Path
import shutil

root     = Path(".")
agents   = Path("agents")

# Chercher la source
candidates = [
    root  / "overlord_utils_utf8.py",
    root  / "overlord_utils.py",
    agents / "overlord_utils.py",
]

source = None
for c in candidates:
    if c.exists():
        source = c
        print(f"Source trouvée : {c}")
        break

if not source:
    print("ERREUR : overlord_utils introuvable")
    exit(1)

# S'assurer que overlord_utils.py est à la racine
root_utils = root / "overlord_utils.py"
if not root_utils.exists() or root_utils != source:
    shutil.copy2(source, root_utils)
    print(f"✓ overlord_utils.py → racine")

# Créer agents/overlord_utils.py qui redirige vers la racine
agents_utils = agents / "overlord_utils.py"
redirect = '''"""
overlord_utils.py (agents/) — Redirection vers la racine
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))
from overlord_utils import *  # noqa: F401, F403
from overlord_utils import fallback_llm, safe_json_parse  # import explicite
'''
agents_utils.write_text(redirect, encoding="utf-8")
print(f"✓ agents/overlord_utils.py → redirect vers racine")
print()
print("Le visual_validator.py trouvera maintenant overlord_utils correctement.")

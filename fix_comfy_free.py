"""
fix_comfy_free.py — Ajoute la libération VRAM avant le quality gate
Colle dans D:\OVERLORD\ et lance : python fix_comfy_free.py
"""
import shutil, ast
from pathlib import Path
from datetime import datetime

target = Path("maestro.py")
src    = target.read_text(encoding="utf-8")

# Texte à trouver — 4 espaces d'indentation
find = "    # Quality gate : valider le workflow avant envoi"

# Texte à insérer AVANT
insert = """    # Libérer la VRAM ComfyUI avant chaque batch — évite les images répétées
    try:
        import requests as _rq
        _cb = "http://127.0.0.1:8188"
        _rq.post(f"{_cb}/interrupt", timeout=5)
        _rq.post(f"{_cb}/queue", json={"clear": True}, timeout=5)
        _rq.post(f"{_cb}/free",
                 json={"unload_models": True, "free_memory": True}, timeout=10)
        logger.info("[GPU] VRAM ComfyUI libérée avant batch")
    except Exception:
        pass

"""

if find not in src:
    print("Texte FIND introuvable — affichage du contexte :")
    for i, line in enumerate(src.splitlines()):
        if "Quality gate" in line or "quality_gate" in line.lower():
            print(f"  {i+1}: {repr(line)}")
else:
    new_src = src.replace(find, insert + find, 1)
    try:
        ast.parse(new_src)
        print("Syntaxe OK")
    except SyntaxError as e:
        print(f"ERREUR : {e}")
        exit(1)

    backup = Path(f"workspace/patch_backups/maestro.comfy_free.{datetime.now().strftime('%H%M%S')}.bak")
    backup.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(target, backup)
    target.write_text(new_src, encoding="utf-8")
    print(f"✓ Fix appliqué — VRAM sera libérée avant chaque batch")
    print(f"  Backup : {backup}")

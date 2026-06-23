"""
fix_vae_fallback.py — Remet taesdxl en attendant le re-téléchargement de sdxl_vae
Colle dans D:\OVERLORD\ et lance : python fix_vae_fallback.py
"""
import re, shutil, ast
from pathlib import Path
from datetime import datetime

target = Path("agents/gpu_optimizer.py")
src    = target.read_text(encoding="utf-8")

# Remplacer sdxl_vae.safetensors par taesdxl dans les deux profils
new_src = src.replace('"sdxl_vae.safetensors"', '"taesdxl"')

count = src.count('"sdxl_vae.safetensors"')
print(f"Occurrences trouvées : {count}")

if count == 0:
    print("Déjà sur taesdxl ou VAE différent")
else:
    try:
        ast.parse(new_src)
    except SyntaxError as e:
        print(f"ERREUR : {e}")
        exit(1)
    backup = Path(f"workspace/patch_backups/gpu_optimizer.vae.{datetime.now().strftime('%H%M%S')}.bak")
    backup.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(target, backup)
    target.write_text(new_src, encoding="utf-8")
    print(f"✓ VAE → taesdxl (fallback)")
    print(f"  Re-télécharge sdxl_vae.safetensors depuis :")
    print(f"  https://huggingface.co/stabilityai/sdxl-vae/resolve/main/sdxl_vae.safetensors")
    print(f"  → D:\\Ov3rLoRd AI\\ComfyUI\\models\\vae\\sdxl_vae.safetensors")
    print()
    print(f"  Après téléchargement complet (~335MB), relancer :")
    print(f"  python fix_vae_fallback.py --restore")

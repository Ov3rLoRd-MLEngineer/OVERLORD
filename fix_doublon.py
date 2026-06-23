"""
fix_doublon.py — Supprime le doublon _safe_stdout dans maestro.py
Colle dans D:\OVERLORD\ et lance : python fix_doublon.py
"""
import sys
from pathlib import Path

target = Path("maestro.py")
if not target.exists():
    print("ERREUR : maestro.py introuvable dans le répertoire courant")
    sys.exit(1)

src = target.read_text(encoding="utf-8")
lines = src.splitlines(keepends=True)

# Trouver les deux occurrences de "def _safe_stdout():"
positions = [i for i, l in enumerate(lines) if "def _safe_stdout():" in l]
print(f"Occurrences de _safe_stdout : {len(positions)} — lignes {[p+1 for p in positions]}")

if len(positions) < 2:
    print("Pas de doublon — rien à faire.")
    sys.exit(0)

# Trouver la fin du premier bloc (jusqu'à la prochaine def/classe)
start = positions[0]
end   = positions[1]  # Le second bloc commence ici

# Supprimer les lignes du premier bloc (start → end-1 inclus)
# + la ligne vide éventuelle entre les deux
while end > start and lines[end-1].strip() == "":
    end -= 1

print(f"Suppression lignes {start+1} à {end} (premier doublon)")

# Backup
backup = Path("workspace/patch_backups/maestro.py.fix_doublon.bak")
backup.parent.mkdir(parents=True, exist_ok=True)
target_copy = target.read_bytes()
backup.write_bytes(target_copy)
print(f"Backup → {backup}")

# Supprimer le premier bloc
new_lines = lines[:start] + lines[end:]
new_src   = "".join(new_lines)

# Vérifier syntaxe
import ast
try:
    ast.parse(new_src)
    print("Syntaxe après suppression : OK")
except SyntaxError as e:
    print(f"ERREUR syntaxe : {e}")
    print("Annulation — maestro.py non modifié")
    sys.exit(1)

target.write_text(new_src, encoding="utf-8")

# Vérifier
remaining = [i for i, l in enumerate(new_src.splitlines()) if "def _safe_stdout():" in l]
print(f"Occurrences restantes : {len(remaining)} — lignes {[r+1 for r in remaining]}")
print()
print("✓ Doublon supprimé")
print()
print("Teste maintenant :")
print("  python clear_state_fix.py")

# scan_maestro2.py — colle dans D:\OVERLORD\ et lance : python scan_maestro2.py
# Vérifie si le patch V170b a bien été appliqué

src = open('maestro.py', encoding='utf-8').read()
lines = src.splitlines()

checks = {
    "_safe_stdout":          False,
    "StreamHandler(_safe":   False,
    "StreamHandler(sys.std": False,  # ne doit plus exister
}

for i, line in enumerate(lines):
    for key in checks:
        if key in line:
            checks[key] = True
            print(f"  Ligne {i+1:4d} [{key}] : {repr(line.strip()[:70])}")

print()
print("=== RÉSULTAT PATCH V170b ===")
print(f"  _safe_stdout présent      : {'OUI ✓' if checks['_safe_stdout'] else 'NON ✗ — patch non appliqué'}")
print(f"  StreamHandler(_safe_...)  : {'OUI ✓' if checks['StreamHandler(_safe'] else 'NON ✗'}")
print(f"  StreamHandler(sys.stdout) : {'ENCORE LÀ ✗' if checks['StreamHandler(sys.std)'] else 'supprimé ✓'}")

# Vérifier aussi où clear_state() est défini
print()
for i, line in enumerate(lines):
    if 'def clear_state' in line:
        print(f"  clear_state définie ligne {i+1}")
        # Afficher les 5 lignes suivantes
        for j in range(i, min(i+8, len(lines))):
            print(f"    {j+1:4d}: {repr(lines[j])}")
        break

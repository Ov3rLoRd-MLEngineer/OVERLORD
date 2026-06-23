# scan_maestro3.py — colle dans D:\OVERLORD\ et lance : python scan_maestro3.py
src   = open('maestro.py', encoding='utf-8').read()
lines = src.splitlines()

# 1. Montrer le contenu exact de clear_state()
print("=== CONTENU clear_state() ===")
in_func = False
for i, line in enumerate(lines):
    if 'def clear_state' in line:
        in_func = True
    if in_func:
        print(f"  {i+1:4d}: {line}")
        # Arrêter à la prochaine fonction
        if i > 324 and (line.startswith('def ') or line.startswith('class ')):
            break
        if in_func and i > 350:
            break

# 2. Montrer les deux blocs _safe_stdout (doublon)
print()
print("=== DOUBLONS _safe_stdout ===")
for i, line in enumerate(lines):
    if '_safe_stdout' in line or 'def get_logger' in line:
        print(f"  {i+1:4d}: {line}")

# 3. Montrer les lignes 285-325 pour voir l'état exact
print()
print("=== LIGNES 285-325 (contexte get_logger) ===")
for i in range(284, 325):
    print(f"  {i+1:4d}: {repr(lines[i])}")

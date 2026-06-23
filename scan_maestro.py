# scan_maestro.py — colle ce fichier dans D:\OVERLORD\ et lance :
# python scan_maestro.py
src = open('maestro.py', encoding='utf-8').read()
lines = src.splitlines()
print(f"Total lignes : {len(lines)}")
print()
for i, line in enumerate(lines):
    if any(k in line for k in ['Logger', 'stdout', 'get_logger',
                                 'import sys', 'import logging',
                                 'StreamHandler', 'clear_state']):
        print(f"{i+1:4d}: {repr(line)}")

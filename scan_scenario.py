# scan_scenario.py — colle dans D:\OVERLORD\ et lance : python scan_scenario.py
src   = open('agents/scenario.py', encoding='utf-8').read()
lines = src.splitlines()
print(f"Total lignes : {len(lines)}")
print()
for i, line in enumerate(lines):
    if any(k in line for k in [
        'scénariste', 'scenariste', 'prompt =', 'prompt=',
        'universe', 'univers', 'Tu es', 'tu es',
        'generate_script', 'def generate'
    ]):
        print(f"  {i+1:4d}: {repr(line[:90])}")

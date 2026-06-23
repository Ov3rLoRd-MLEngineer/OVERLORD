# scan_storyboard.py — colle dans D:\OVERLORD\ et lance : python scan_storyboard.py
src   = open('agents/storyboard.py', encoding='utf-8').read()
lines = src.splitlines()
print(f"Total lignes : {len(lines)}")
print()
# Chercher les lignes clés autour du return final
for i, line in enumerate(lines):
    if any(k in line for k in ['jobs ComfyUI', 'return shots', 'return shot',
                                 'prepares', 'prepared', 'jobs prepar']):
        # Afficher contexte 3 lignes avant/après
        start = max(0, i-2)
        end   = min(len(lines), i+4)
        print(f"  --- Zone ligne {i+1} ---")
        for j in range(start, end):
            print(f"  {j+1:4d}: {repr(lines[j])}")
        print()

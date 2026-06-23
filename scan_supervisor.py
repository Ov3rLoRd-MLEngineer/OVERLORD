# scan_supervisor.py — colle dans D:\OVERLORD\ et lance : python scan_supervisor.py
src   = open('agents/agent_supervisor_v2.py', encoding='utf-8').read()
lines = src.splitlines()
print(f"Total lignes : {len(lines)}")
print()
for i, line in enumerate(lines):
    if any(k in line for k in [
        'def run_batch', 'def submit', 'def _send',
        'production_pass', 'has_sketch', 'background',
        'comfyui', 'ComfyUI', 'queue_prompt',
        'class Supervisor', 'def run'
    ]):
        print(f"  {i+1:4d}: {repr(line[:80])}")

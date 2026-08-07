"""Surveillance systeme pour session nuit autonome (session_nuit.txt Priorite 1,
2026-08-06/07). Deux boucles independantes dans un seul process :

1. Toutes les 30s : interroge le journal d'evenements Windows (System) pour les
   IDs critiques (Kernel-Power 41 = arret/crash inattendu, BugCheck 1001 = dump
   BSOD, EventLog 6008 = arret inattendu, nvlddmkm/Display 4101 = TDR GPU deja
   documente en memoire long terme). Nouveaux evenements -> DEMO/output/
   system_crashes.csv + CRASH_ALERT.flag (racine repo) pour reveil immediat.
2. Toutes les 5 min : stats CPU/RAM/GPU -> DEMO/output/system_log.csv (meme
   schema que le fichier deja produit par une session precedente, on continue
   dessus plutot que d'en creer un nouveau).

Pas de dependance pywin32 : le journal d'evenements est interroge via
`powershell Get-WinEvent` en sous-processus (requirements.txt reste minimal,
cf. CLAUDE.md).

Lancement (process detache visible, cf. CLAUDE.md "Lancement de process
detaches") :
    start cmd /k py -3.12 workspace/scripts/system_monitor.py
"""
import csv
import json
import os
import subprocess
import time

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
OUT_DIR = os.path.join(REPO_ROOT, "DEMO", "output")
CRASHES_CSV = os.path.join(OUT_DIR, "system_crashes.csv")
SYSTEM_LOG_CSV = os.path.join(OUT_DIR, "system_log.csv")
CRASH_FLAG = os.path.join(REPO_ROOT, "CRASH_ALERT.flag")

EVENT_POLL_S = 30
STATS_INTERVAL_S = 300
CRITICAL_IDS = [41, 1001, 6008, 6009, 4101, 4100]

CRASHES_HEADER = ["timestamp_detected", "event_time", "event_id", "provider", "level", "message_snippet"]
STATS_HEADER = ["timestamp", "cpu_percent", "ram_used_go", "ram_percent",
                "gpu0_vram_go", "gpu1_vram_go", "gpu0_util", "gpu1_util"]


def log(msg):
    print(f"[{time.strftime('%Y-%m-%dT%H:%M:%S')}] {msg}", flush=True)


def ensure_csv(path, header):
    if not os.path.exists(path):
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", newline="", encoding="utf-8") as f:
            csv.writer(f).writerow(header)


def poll_event_log(since_iso):
    ps_cmd = (
        f"$ErrorActionPreference='SilentlyContinue'; "
        f"Get-WinEvent -FilterHashtable @{{LogName='System'; Id={','.join(str(i) for i in CRITICAL_IDS)}; "
        f"StartTime='{since_iso}'}} | "
        f"Select-Object TimeCreated,Id,ProviderName,LevelDisplayName,Message | ConvertTo-Json -Compress"
    )
    try:
        result = subprocess.run(
            ["powershell", "-NoProfile", "-Command", ps_cmd],
            capture_output=True, text=True, timeout=25,
        )
    except subprocess.TimeoutExpired:
        log("WARN: poll event log timeout, skip ce cycle")
        return []
    raw = result.stdout.strip()
    if not raw:
        return []
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        log(f"WARN: sortie Get-WinEvent non parsable : {raw[:200]}")
        return []
    if isinstance(data, dict):
        data = [data]
    return data


def append_crash_events(events):
    ensure_csv(CRASHES_CSV, CRASHES_HEADER)
    new_max_time = None
    with open(CRASHES_CSV, "a", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        for ev in events:
            event_time = ev.get("TimeCreated", "")
            msg = (ev.get("Message") or "").replace("\n", " ").replace("\r", "")[:300]
            w.writerow([time.strftime("%Y-%m-%dT%H:%M:%S"), event_time, ev.get("Id"),
                        ev.get("ProviderName"), ev.get("LevelDisplayName"), msg])
            if new_max_time is None or str(event_time) > new_max_time:
                new_max_time = str(event_time)
    flag_lines = [f"CRASH DETECTE {time.strftime('%Y-%m-%dT%H:%M:%S')} : "
                  f"Id={ev.get('Id')} {ev.get('ProviderName')} {ev.get('LevelDisplayName')} -- "
                  f"{(ev.get('Message') or '')[:200]}" for ev in events]
    mode = "a" if os.path.exists(CRASH_FLAG) else "w"
    with open(CRASH_FLAG, mode, encoding="utf-8") as f:
        f.write("\n".join(flag_lines) + "\n")
    log(f"CRASH_ALERT : {len(events)} evenement(s) critique(s) -> {CRASH_FLAG}")
    return new_max_time


def nvidia_smi_stats():
    try:
        result = subprocess.run(
            ["nvidia-smi", "--query-gpu=index,memory.used,utilization.gpu",
             "--format=csv,noheader,nounits"],
            capture_output=True, text=True, timeout=10,
        )
    except (subprocess.TimeoutExpired, FileNotFoundError):
        return {}
    stats = {}
    for line in result.stdout.strip().splitlines():
        parts = [p.strip() for p in line.split(",")]
        if len(parts) == 3:
            idx, mem_mib, util = parts
            stats[int(idx)] = (float(mem_mib) / 1024.0, float(util))
    return stats


def log_stats():
    import psutil
    ensure_csv(SYSTEM_LOG_CSV, STATS_HEADER)
    cpu = psutil.cpu_percent(interval=1)
    vm = psutil.virtual_memory()
    gpu = nvidia_smi_stats()
    g0 = gpu.get(0, (0.0, 0.0))
    g1 = gpu.get(1, (0.0, 0.0))
    row = [time.strftime("%Y-%m-%dT%H:%M:%S"), cpu, round(vm.used / 1e9, 2), vm.percent,
           round(g0[0], 2), round(g1[0], 2), g0[1], g1[1]]
    with open(SYSTEM_LOG_CSV, "a", newline="", encoding="utf-8") as f:
        csv.writer(f).writerow(row)
    log(f"stats: cpu={cpu}% ram={vm.percent}% gpu0={g0[0]:.1f}Go/{g0[1]:.0f}% gpu1={g1[0]:.1f}Go/{g1[1]:.0f}%")


def main():
    log("system_monitor demarre (session nuit, priorite 1)")
    ensure_csv(CRASHES_CSV, CRASHES_HEADER)
    ensure_csv(SYSTEM_LOG_CSV, STATS_HEADER)
    since_iso = time.strftime("%Y-%m-%dT%H:%M:%S")
    last_stats_t = 0.0
    while True:
        t0 = time.time()
        events = poll_event_log(since_iso)
        if events:
            new_since = append_crash_events(events)
            if new_since:
                since_iso = new_since
        if time.time() - last_stats_t >= STATS_INTERVAL_S:
            try:
                log_stats()
            except Exception as e:
                log(f"WARN log_stats: {e}")
            last_stats_t = time.time()
        elapsed = time.time() - t0
        time.sleep(max(1.0, EVENT_POLL_S - elapsed))


if __name__ == "__main__":
    main()

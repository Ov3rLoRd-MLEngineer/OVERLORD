"""Logge CPU/RAM/VRAM toutes les 5 minutes dans DEMO/output/system_log.csv.
Arret automatique si RAM systeme > RAM_STOP_GB (marge sur 32Go total, cf.
ANNEXE_SESSION_CLAUDE_CODE_20260806.md).

Usage : py -3.12 DEMO/system_monitor.py [--interval 300] [--stop-gb 28]
"""
import argparse
import csv
import os
import subprocess
import sys
import time
from datetime import datetime

import psutil

OUT_CSV = os.path.join(os.path.dirname(__file__), "output", "system_log.csv")
FIELDNAMES = [
    "timestamp", "cpu_percent", "ram_used_go", "ram_percent",
    "gpu0_vram_go", "gpu1_vram_go", "gpu0_util", "gpu1_util",
]


def query_gpu():
    try:
        out = subprocess.check_output(
            ["nvidia-smi", "--query-gpu=index,memory.used,utilization.gpu",
             "--format=csv,noheader,nounits"],
            text=True, timeout=10,
        )
        rows = {}
        for line in out.strip().splitlines():
            idx, mem, util = [x.strip() for x in line.split(",")]
            rows[int(idx)] = (float(mem) / 1024.0, float(util))
        return rows
    except Exception:
        return {}


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--interval", type=int, default=300)
    p.add_argument("--stop-gb", type=float, default=28.0)
    args = p.parse_args()

    os.makedirs(os.path.dirname(OUT_CSV), exist_ok=True)
    write_header = not os.path.exists(OUT_CSV)
    with open(OUT_CSV, "a", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=FIELDNAMES)
        if write_header:
            writer.writeheader()
            f.flush()

        while True:
            vm = psutil.virtual_memory()
            ram_used_go = (vm.total - vm.available) / (1024 ** 3)
            gpus = query_gpu()
            row = {
                "timestamp": datetime.now().isoformat(timespec="seconds"),
                "cpu_percent": psutil.cpu_percent(interval=1),
                "ram_used_go": round(ram_used_go, 2),
                "ram_percent": vm.percent,
                "gpu0_vram_go": round(gpus.get(0, (0, 0))[0], 2),
                "gpu1_vram_go": round(gpus.get(1, (0, 0))[0], 2),
                "gpu0_util": gpus.get(0, (0, 0))[1],
                "gpu1_util": gpus.get(1, (0, 0))[1],
            }
            writer.writerow(row)
            f.flush()
            print(f"[{row['timestamp']}] RAM {row['ram_used_go']}Go "
                  f"CPU {row['cpu_percent']}% GPU0 {row['gpu0_vram_go']}Go "
                  f"GPU1 {row['gpu1_vram_go']}Go", flush=True)

            if ram_used_go > args.stop_gb:
                print(f"STOP: RAM systeme {ram_used_go:.1f}Go > seuil {args.stop_gb}Go", flush=True)
                sys.exit(1)

            time.sleep(args.interval)


if __name__ == "__main__":
    main()

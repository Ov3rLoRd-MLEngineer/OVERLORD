# ██████╗ ██╗   ██╗██████╗ ██████╗ ██╗      ██████╗ ██████╗ ██████╗
# ██╔═══██╗██║   ██║╚════██╗██╔══██╗██║     ██╔═══██╗██╔══██╗██╔══██╗
# ██║   ██║██║   ██║ █████╔╝██████╔╝██║     ██║   ██║██████╔╝██║  ██║
# ██║   ██║╚██╗ ██╔╝ ╚═══██╗██╔══██╗██║     ██║   ██║██╔══██╗██║  ██║
# ╚██████╔╝ ╚████╔╝ ██████╔╝██║  ██║███████╗╚██████╔╝██║  ██║██████╔╝
# ╚═════╝   ╚═══╝  ╚═════╝ ╚═╝  ╚═╝╚══════╝ ╚═════╝ ╚═╝  ╚═╝╚═════╝
# Ov3rLoRd -- pipeline de production anime autonome (ComfyUI)
# https://github.com/Ov3rLoRd-MLEngineer
#
"""
agents/agent_overclock.py — Agent Overclock & Monitoring Hardware V1.70
Gère l'overclock CPU (i7 8700K) et surveille les ressources système.
Objectif : maximiser les performances pendant les runs ComfyUI.

Fonctions :
  - Monitoring temps réel CPU/RAM/GPU (toutes les 5s)
  - Profils de performance (normal, turbo, max)
  - Alertes température (CPU > 85°C, GPU > 83°C)
  - Logs hardware dans workspace/logs/hardware.jsonl
  - Exposition sur le bus pour le HUD

Prérequis Windows :
  pip install psutil --break-system-packages
  nvidia-smi dans le PATH (NVIDIA drivers)

Overclock CPU (i7 8700K) :
  Via ThrottleStop ou Intel XTU — ce script gère le profil via commandes système.
  ATTENTION : l'overclock nécessite une config BIOS préalable.

Usage :
  python agents/agent_overclock.py              # monitoring + profil auto
  python agents/agent_overclock.py --profile turbo
  python agents/agent_overclock.py --monitor-only
"""

import argparse
import json
import logging
import subprocess
import sys
import threading
import time
import io
from datetime import datetime
from pathlib import Path

if hasattr(sys.stdout, 'buffer'):
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

try:
    import psutil
    PSUTIL_OK = True
except ImportError:
    PSUTIL_OK = False

try:
    from agents.context_bus import get_bus
    BUS_OK = True
except ImportError:
    BUS_OK = False

HARDWARE_LOG = Path("workspace/logs/hardware.jsonl")
ALERT_LOG    = Path("workspace/logs/hardware_alerts.jsonl")

# Seuils d'alerte
CPU_TEMP_WARN   = 80   # °C
CPU_TEMP_CRIT   = 90   # °C
GPU_TEMP_WARN   = 80   # °C
GPU_TEMP_CRIT   = 85   # °C
RAM_WARN_PCT    = 85   # %
VRAM_WARN_PCT   = 90   # %

# Profils de performance CPU
PERFORMANCE_PROFILES = {
    "normal": {
        "description": "Profil équilibré — économie d'énergie active",
        "power_plan":  "Balanced",
        "priority":    "Normal",
    },
    "turbo": {
        "description": "Turbo — boost CPU maximal, pas d'OC",
        "power_plan":  "High performance",
        "priority":    "High",
    },
    "max": {
        "description": "Maximum — tous les cœurs à fond (nécessite OC BIOS)",
        "power_plan":  "Ultimate Performance",
        "priority":    "Realtime",
    },
}

# GUIDs Windows Power Plans
POWER_PLAN_GUIDS = {
    "Balanced":              "381b4222-f694-41f0-9685-ff5bb260df2e",
    "High performance":      "8c5e7fda-e8bf-4a96-9a85-a6e23a8c635c",
    "Ultimate Performance":  "e9a42b02-d5df-448d-aa00-03f14749eb61",
}


class HardwareMonitor:
    """Monitoring temps réel CPU/RAM/GPU."""

    def __init__(self, interval_s: int = 5):
        self.interval   = interval_s
        self._running   = False
        self._thread: threading.Thread | None = None
        self._last_data: dict = {}
        self._alerts:   list  = []
        self.log        = logging.getLogger("overclock.monitor")

    def _read_gpu(self) -> dict:
        try:
            result = subprocess.run(
                ["nvidia-smi",
                 "--query-gpu=name,memory.used,memory.total,temperature.gpu,"
                 "utilization.gpu,power.draw,clocks.current.graphics",
                 "--format=csv,noheader,nounits"],
                capture_output=True, text=True, timeout=5
            )
            if result.returncode == 0:
                p = [x.strip() for x in result.stdout.strip().split(",")]
                if len(p) >= 6:
                    return {
                        "name":       p[0],
                        "vram_used":  int(p[1]),
                        "vram_total": int(p[2]),
                        "vram_pct":   round(int(p[1]) / max(int(p[2]), 1) * 100, 1),
                        "temp_c":     int(p[3]),
                        "util_pct":   int(p[4]),
                        "power_w":    float(p[5]) if p[5] != "N/A" else 0.0,
                        "clock_mhz":  int(p[6]) if len(p) > 6 and p[6] != "N/A" else 0,
                    }
        except Exception:
            pass
        return {}

    def _read_cpu(self) -> dict:
        if not PSUTIL_OK:
            return {}
        try:
            freq = psutil.cpu_freq()
            temps = {}
            try:
                sensor_data = psutil.sensors_temperatures()
                for name, entries in (sensor_data or {}).items():
                    if entries:
                        temps[name] = round(entries[0].current, 1)
            except (AttributeError, Exception):
                pass

            return {
                "percent":    psutil.cpu_percent(interval=0.5),
                "freq_mhz":   round(freq.current, 0) if freq else 0,
                "freq_max":   round(freq.max, 0) if freq else 0,
                "cores":      psutil.cpu_count(logical=False),
                "threads":    psutil.cpu_count(logical=True),
                "temps":      temps,
            }
        except Exception:
            return {}

    def _read_ram(self) -> dict:
        if not PSUTIL_OK:
            return {}
        try:
            vm = psutil.virtual_memory()
            return {
                "total_gb":   round(vm.total / 1e9, 1),
                "used_gb":    round(vm.used / 1e9, 1),
                "available_gb": round(vm.available / 1e9, 1),
                "percent":    vm.percent,
            }
        except Exception:
            return {}

    def _check_alerts(self, data: dict):
        """Déclenche des alertes si seuils dépassés."""
        gpu  = data.get("gpu", {})
        cpu  = data.get("cpu", {})
        ram  = data.get("ram", {})

        alerts = []
        if gpu.get("temp_c", 0) >= GPU_TEMP_CRIT:
            alerts.append({"type": "GPU_TEMP_CRITICAL", "value": gpu["temp_c"],
                           "threshold": GPU_TEMP_CRIT})
            self.log.error(f"[OVERCLOCK] ⚠ GPU SURCHAUFFE : {gpu['temp_c']}°C")

        elif gpu.get("temp_c", 0) >= GPU_TEMP_WARN:
            alerts.append({"type": "GPU_TEMP_WARN", "value": gpu["temp_c"],
                           "threshold": GPU_TEMP_WARN})
            self.log.warning(f"[OVERCLOCK] GPU chaud : {gpu['temp_c']}°C")

        if ram.get("percent", 0) >= RAM_WARN_PCT:
            alerts.append({"type": "RAM_HIGH", "value": ram["percent"],
                           "threshold": RAM_WARN_PCT})
            self.log.warning(f"[OVERCLOCK] RAM haute : {ram['percent']}%")

        if gpu.get("vram_pct", 0) >= VRAM_WARN_PCT:
            alerts.append({"type": "VRAM_HIGH", "value": gpu["vram_pct"],
                           "threshold": VRAM_WARN_PCT})
            self.log.warning(f"[OVERCLOCK] VRAM haute : {gpu['vram_pct']}%")

        if alerts:
            ts = datetime.now().isoformat()
            ALERT_LOG.parent.mkdir(parents=True, exist_ok=True)
            with open(ALERT_LOG, 'a', encoding='utf-8') as f:
                for a in alerts:
                    f.write(json.dumps({"ts": ts, **a}, ensure_ascii=False) + '\n')
            self._alerts.extend(alerts)

    def _collect(self) -> dict:
        data = {
            "timestamp": datetime.now().isoformat(),
            "gpu":       self._read_gpu(),
            "cpu":       self._read_cpu(),
            "ram":       self._read_ram(),
        }
        self._last_data = data
        return data

    def _loop(self):
        while self._running:
            data = self._collect()
            self._check_alerts(data)

            # Persister
            HARDWARE_LOG.parent.mkdir(parents=True, exist_ok=True)
            with open(HARDWARE_LOG, 'a', encoding='utf-8') as f:
                f.write(json.dumps({
                    "ts":         data["timestamp"],
                    "gpu_temp":   data["gpu"].get("temp_c", 0),
                    "gpu_vram_pct": data["gpu"].get("vram_pct", 0),
                    "gpu_util":   data["gpu"].get("util_pct", 0),
                    "ram_pct":    data["ram"].get("percent", 0),
                    "cpu_pct":    data["cpu"].get("percent", 0),
                }, ensure_ascii=False) + '\n')

            # Publier sur le bus
            if BUS_OK:
                try:
                    bus = get_bus()
                    bus.write("hardware.gpu_temp",   data["gpu"].get("temp_c", 0),
                              agent_id="overclock")
                    bus.write("hardware.gpu_vram",   data["gpu"].get("vram_pct", 0),
                              agent_id="overclock")
                    bus.write("hardware.gpu_util",   data["gpu"].get("util_pct", 0),
                              agent_id="overclock")
                    bus.write("hardware.ram_pct",    data["ram"].get("percent", 0),
                              agent_id="overclock")
                    bus.write("hardware.cpu_pct",    data["cpu"].get("percent", 0),
                              agent_id="overclock")
                    bus.write("hardware.alerts_count", len(self._alerts),
                              agent_id="overclock")
                except Exception:
                    pass

            time.sleep(self.interval)

    def start(self):
        self._running = True
        self._thread  = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()
        self.log.info(f"[OVERCLOCK] Monitoring démarré (intervalle={self.interval}s)")

    def stop(self):
        self._running = False
        if self._thread:
            self._thread.join(timeout=10)
        self.log.info("[OVERCLOCK] Monitoring arrêté")

    @property
    def latest(self) -> dict:
        return self._last_data

    def print_status(self):
        d = self._collect()
        g = d.get("gpu", {})
        c = d.get("cpu", {})
        r = d.get("ram", {})
        print(f"\n{'─'*50}")
        print(f"  GPU  : {g.get('name','?')}")
        print(f"  VRAM : {g.get('vram_used',0)}/{g.get('vram_total',0)}MB "
              f"({g.get('vram_pct',0)}%)")
        print(f"  Temp : {g.get('temp_c',0)}°C | Util: {g.get('util_pct',0)}%")
        print(f"  Power: {g.get('power_w',0):.1f}W | Clock: {g.get('clock_mhz',0)}MHz")
        print(f"  CPU  : {c.get('percent',0)}% | {c.get('freq_mhz',0):.0f}MHz")
        print(f"  RAM  : {r.get('used_gb',0):.1f}/{r.get('total_gb',0):.1f}GB "
              f"({r.get('percent',0)}%)")
        print(f"{'─'*50}")


class OverclockManager:
    """Gestion du profil de performance CPU via Windows Power Plans."""

    def __init__(self):
        self.log = logging.getLogger("overclock.manager")
        self.current_profile = "normal"

    def set_profile(self, profile_name: str) -> bool:
        profile = PERFORMANCE_PROFILES.get(profile_name)
        if not profile:
            self.log.error(f"[OVERCLOCK] Profil inconnu : {profile_name}")
            return False

        plan = profile["power_plan"]
        guid = POWER_PLAN_GUIDS.get(plan)

        if guid:
            try:
                result = subprocess.run(
                    ["powercfg", "/setactive", guid],
                    capture_output=True, text=True, timeout=10
                )
                if result.returncode == 0:
                    self.log.info(f"[OVERCLOCK] Profil '{profile_name}' appliqué : {plan}")
                    self.current_profile = profile_name
                    if BUS_OK:
                        try:
                            get_bus().write("hardware.power_profile", profile_name,
                                            agent_id="overclock")
                        except Exception:
                            pass
                    return True
                else:
                    self.log.warning(f"[OVERCLOCK] powercfg échoué : {result.stderr[:100]}")
            except FileNotFoundError:
                self.log.warning("[OVERCLOCK] powercfg non trouvé — Windows requis")
            except Exception as e:
                self.log.error(f"[OVERCLOCK] Erreur profil : {e}")

        # Fallback : priorité processus Python
        self.log.info(f"[OVERCLOCK] Fallback : ajustement priorité processus")
        self._set_process_priority(profile.get("priority", "Normal"))
        return True

    def _set_process_priority(self, priority: str):
        """Ajuste la priorité du processus Python courant."""
        import os
        priority_map = {
            "Normal":   psutil.NORMAL_PRIORITY_CLASS if PSUTIL_OK else None,
            "High":     psutil.HIGH_PRIORITY_CLASS   if PSUTIL_OK else None,
            "Realtime": psutil.REALTIME_PRIORITY_CLASS if PSUTIL_OK else None,
        }
        if PSUTIL_OK:
            try:
                p = psutil.Process(os.getpid())
                pc = priority_map.get(priority)
                if pc:
                    p.nice(pc)
                    self.log.info(f"[OVERCLOCK] Priorité processus : {priority}")
            except Exception as e:
                self.log.warning(f"[OVERCLOCK] Priorité non modifiable : {e}")

    def optimize_for_comfyui(self):
        """Profil optimisé pour une session ComfyUI."""
        self.log.info("[OVERCLOCK] Optimisation pour ComfyUI...")
        self.set_profile("turbo")
        if PSUTIL_OK:
            try:
                # Trouver le processus ComfyUI et augmenter sa priorité
                for proc in psutil.process_iter(['pid', 'name', 'cmdline']):
                    if 'python' in proc.info['name'].lower():
                        cmdline = ' '.join(proc.info.get('cmdline', []))
                        if 'comfyui' in cmdline.lower() or 'main.py' in cmdline.lower():
                            p = psutil.Process(proc.info['pid'])
                            p.nice(psutil.HIGH_PRIORITY_CLASS)
                            self.log.info(f"[OVERCLOCK] ComfyUI PID {proc.info['pid']} → priorité HIGH")
            except Exception as e:
                self.log.debug(f"[OVERCLOCK] Priorité ComfyUI : {e}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Ov3rLoRd Hardware Agent V1.70")
    parser.add_argument("--profile",      type=str, default="turbo",
                        choices=PERFORMANCE_PROFILES.keys())
    parser.add_argument("--monitor-only", action="store_true")
    parser.add_argument("--interval",     type=int, default=5)
    parser.add_argument("--comfyui",      action="store_true",
                        help="Optimiser pour session ComfyUI")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO,
                        format="%(asctime)s [%(levelname)s] %(message)s")
    log = logging.getLogger("overclock")

    monitor = HardwareMonitor(interval_s=args.interval)
    manager = OverclockManager()

    print("=== Ov3rLoRd Hardware Agent V1.70 ===")
    if not PSUTIL_OK:
        print("⚠ psutil non installé : pip install psutil")
    print(f"Profil cible  : {args.profile}")
    print(f"Intervalle    : {args.interval}s")

    # Afficher l'état matériel
    monitor.print_status()

    if not args.monitor_only:
        if args.comfyui:
            manager.optimize_for_comfyui()
        else:
            manager.set_profile(args.profile)

    print("\nMonitoring en cours... (Ctrl+C pour arrêter)")
    monitor.start()

    try:
        while True:
            time.sleep(args.interval)
            d = monitor.latest
            if d:
                gpu = d.get("gpu", {})
                ram = d.get("ram", {})
                print(f"\r  GPU: {gpu.get('temp_c',0)}°C "
                      f"VRAM:{gpu.get('vram_pct',0):.0f}% "
                      f"Util:{gpu.get('util_pct',0)}% "
                      f"RAM:{ram.get('percent',0):.0f}%     ", end="", flush=True)
    except KeyboardInterrupt:
        print()
        monitor.stop()
        manager.set_profile("normal")  # Revenir au profil normal à l'arrêt
        print("Agent overclock arrêté.")

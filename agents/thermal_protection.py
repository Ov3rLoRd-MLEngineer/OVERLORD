"""
agents/thermal_protection.py -- Ov3rLoRd V1.40 -- Thermal Protection RTX
Protection intelligente du GPU. Surveille temperature et adapte la charge.
V1.49o : context_bus connecte, datetime.utcnow() corrige.
"""

import time
import json
import threading
import logging
from pathlib import Path
from datetime import datetime, timezone
from dataclasses import dataclass, field
from typing import Optional

try:
    import pynvml
    NVML_OK = True
except ImportError:
    NVML_OK = False

try:
    from agents.context_bus import get_bus
    BUS_OK = True
except ImportError:
    BUS_OK = False

THERMAL_DIR  = Path("workspace/thermal")
log          = logging.getLogger("thermal_protection")

# Seuils RTX (adaptables)
TEMP_WARNING  = 80
TEMP_CRITICAL = 88
TEMP_SHUTDOWN = 93
VRAM_WARNING  = 0.90
POWER_WARNING = 0.95


@dataclass
class GpuMetrics:
    timestamp:   str
    temp_c:      float = 0.0
    vram_used_mb:float = 0.0
    vram_total_mb:float= 0.0
    power_w:     float = 0.0
    power_max_w: float = 0.0
    gpu_util_pct:float = 0.0
    clock_mhz:   float = 0.0

    @property
    def vram_pct(self) -> float:
        return self.vram_used_mb / max(self.vram_total_mb, 1)

    @property
    def power_pct(self) -> float:
        return self.power_w / max(self.power_max_w, 1)

    def is_safe(self) -> bool:
        return (self.temp_c < TEMP_WARNING and
                self.vram_pct < VRAM_WARNING and
                self.power_pct < POWER_WARNING)


class GpuMonitor:

    def __init__(self, gpu_index: int = 0):
        self._gpu_index = gpu_index
        self._handle    = None
        if NVML_OK:
            try:
                pynvml.nvmlInit()
                self._handle = pynvml.nvmlDeviceGetHandleByIndex(gpu_index)
            except Exception as e:
                log.warning(f"[THERMAL] NVML init : {e}")

    def read(self) -> GpuMetrics:
        # FIX : datetime.utcnow() -> datetime.now(tz=timezone.utc)
        ts = datetime.now(tz=timezone.utc).isoformat()
        if not NVML_OK or not self._handle:
            return GpuMetrics(timestamp=ts, temp_c=40.0)
        try:
            mem      = pynvml.nvmlDeviceGetMemoryInfo(self._handle)
            temp     = pynvml.nvmlDeviceGetTemperature(self._handle, pynvml.NVML_TEMPERATURE_GPU)
            power    = pynvml.nvmlDeviceGetPowerUsage(self._handle) / 1000
            power_lim= pynvml.nvmlDeviceGetPowerManagementLimit(self._handle) / 1000
            util     = pynvml.nvmlDeviceGetUtilizationRates(self._handle)
            clock    = pynvml.nvmlDeviceGetClockInfo(self._handle, pynvml.NVML_CLOCK_GRAPHICS)
            return GpuMetrics(
                timestamp    = ts,
                temp_c       = float(temp),
                vram_used_mb = mem.used  / 1024**2,
                vram_total_mb= mem.total / 1024**2,
                power_w      = float(power),
                power_max_w  = float(power_lim),
                gpu_util_pct = float(util.gpu),
                clock_mhz    = float(clock),
            )
        except Exception as e:
            log.debug(f"[THERMAL] Read error : {e}")
            return GpuMetrics(timestamp=ts, temp_c=40.0)


class ThermalThrottler:
    """Adapte les parametres de generation selon la temperature GPU."""

    PROFILES = {
        "safe":     {"steps_mult":1.00, "batch_mult":1.0, "delay_s":0},
        "warm":     {"steps_mult":0.90, "batch_mult":1.0, "delay_s":2},
        "hot":      {"steps_mult":0.80, "batch_mult":0.5, "delay_s":5},
        "critical": {"steps_mult":0.60, "batch_mult":0.5, "delay_s":15},
    }

    def get_profile(self, metrics: GpuMetrics) -> tuple[str, dict]:
        if metrics.temp_c >= TEMP_CRITICAL:
            return "critical", self.PROFILES["critical"]
        if metrics.temp_c >= TEMP_WARNING:
            return "hot", self.PROFILES["hot"]
        if metrics.temp_c >= TEMP_WARNING - 5 or metrics.vram_pct >= VRAM_WARNING:
            return "warm", self.PROFILES["warm"]
        return "safe", self.PROFILES["safe"]

    def apply(self, params: dict, metrics: GpuMetrics) -> dict:
        profile_name, profile = self.get_profile(metrics)
        if profile_name != "safe":
            log.warning(f"[THERMAL] Profil {profile_name} | {metrics.temp_c:.0f}C | "
                        f"VRAM {metrics.vram_pct:.0%}")
        delay = profile["delay_s"]
        if delay > 0:
            log.info(f"[THERMAL] Pause thermique {delay}s")
            time.sleep(delay)
        p = dict(params)
        if "steps" in p:
            p["steps"] = max(15, int(p["steps"] * profile["steps_mult"]))
        return p


class ThermalProtection:
    """Orchestrateur de la protection thermique."""

    def __init__(self, gpu_index: int = 0, logger: logging.Logger = None):
        self.log      = logger or log
        self.monitor  = GpuMonitor(gpu_index)
        self.throttler= ThermalThrottler()
        self._history: list[GpuMetrics] = []
        self._running  = False
        self._thread:  Optional[threading.Thread] = None
        THERMAL_DIR.mkdir(parents=True, exist_ok=True)

    def start_monitoring(self, interval_s: float = 5.0):
        self._running = True
        def _loop():
            while self._running:
                m = self.monitor.read()
                self._history.append(m)
                self._history = self._history[-120:]  # 10min a 5s
                if not m.is_safe():
                    if BUS_OK:
                        try:
                            bus = get_bus()
                            bus.write("thermal.temp_c",     m.temp_c,           agent_id="thermal")
                            bus.write("thermal.vram_pct",   round(m.vram_pct*100,1), agent_id="thermal")
                            bus.write("thermal.is_safe",    m.is_safe(),        agent_id="thermal")
                            bus.write("thermal.profile",
                                      self.throttler.get_profile(m)[0], agent_id="thermal")
                        except Exception:
                            pass
                time.sleep(interval_s)
        self._thread = threading.Thread(target=_loop, daemon=True, name="thermal_monitor")
        self._thread.start()
        self.log.info("[THERMAL] Monitoring demarre")

    def stop_monitoring(self):
        self._running = False

    def safe_generate(self, params: dict) -> dict:
        """Retourne les params ajustes selon l'etat thermique actuel."""
        m = self.monitor.read()
        if BUS_OK:
            try:
                get_bus().write("thermal.temp_c",  m.temp_c,  agent_id="thermal")
                get_bus().write("thermal.is_safe", m.is_safe(), agent_id="thermal")
            except Exception:
                pass
        if m.temp_c >= TEMP_SHUTDOWN:
            self.log.error(f"[THERMAL] ARRET D'URGENCE : {m.temp_c:.0f}C")
            raise RuntimeError(f"GPU surchauffe : {m.temp_c:.0f}C >= {TEMP_SHUTDOWN}C")
        return self.throttler.apply(params, m)

    def get_status(self) -> dict:
        m = self.monitor.read()
        return {
            "temp_c":     m.temp_c,
            "vram_pct":   round(m.vram_pct*100, 1),
            "power_w":    m.power_w,
            "gpu_util":   m.gpu_util_pct,
            "is_safe":    m.is_safe(),
            "profile":    self.throttler.get_profile(m)[0],
            "nvml_ok":    NVML_OK,
        }


_thermal: Optional[ThermalProtection] = None

def get_thermal() -> ThermalProtection:
    global _thermal
    if _thermal is None:
        _thermal = ThermalProtection()
    return _thermal


if __name__ == "__main__":
    import sys, io
    if hasattr(sys.stdout, "buffer"):
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    logging.basicConfig(level=logging.INFO)
    tp = ThermalProtection()
    print(f"Status GPU : {json.dumps(tp.get_status(), indent=2)}")
    params = tp.safe_generate({"steps":28,"cfg":7.0,"width":1024,"height":1536})
    print(f"Params securises : {params}")
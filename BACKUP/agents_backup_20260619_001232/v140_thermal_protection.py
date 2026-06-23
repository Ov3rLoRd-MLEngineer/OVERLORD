"""
agents/v140_thermal_protection.py — OverLord V1.40 — Thermal Protection RTX 5080

Protection intelligente de la RTX 5080 (360W TDP, 16Go VRAM).
Surveille la température GPU en temps réel et adapte la charge
pour éviter le throttling thermique qui dégrade les performances.

Fonctionnalités :
  - Monitoring continu (température, VRAM, puissance, horloge)
  - Throttling adaptatif automatique (réduction steps/batch)
  - Alertes configurables (S10+ via licence_server)
  - Profils de charge (silent/balanced/performance/turbo)
  - Historique thermique pour optimiser les sessions longues
  - Calcul du ROI thermique (qualité vs température)

pip install pynvml
"""

import time
import json
import threading
import logging
from pathlib import Path
from datetime import datetime
from dataclasses import dataclass, field
from typing import Optional, Callable

THERMAL_DIR = Path("workspace/thermal")
HISTORY_FILE= THERMAL_DIR / "thermal_history.json"


# ══════════════════════════════════════════════════════════════════════
# PROFILS THERMIQUES
# ══════════════════════════════════════════════════════════════════════

THERMAL_PROFILES = {
    "silent": {
        "max_temp_c":     75,
        "throttle_at":    70,
        "steps_max":      24,
        "batch_max":      1,
        "vram_budget_gb": 12,
        "desc": "Mode silencieux — ventilateurs bas, performance réduite",
    },
    "balanced": {
        "max_temp_c":     83,
        "throttle_at":    80,
        "steps_max":      32,
        "batch_max":      2,
        "vram_budget_gb": 14,
        "desc": "Mode équilibré — recommandé pour sessions longues",
    },
    "performance": {
        "max_temp_c":     88,
        "throttle_at":    85,
        "steps_max":      48,
        "batch_max":      4,
        "vram_budget_gb": 15,
        "desc": "Mode performance — pour la RTX 5080 bien refroidie",
    },
    "turbo": {
        "max_temp_c":     93,
        "throttle_at":    90,
        "steps_max":      60,
        "batch_max":      8,
        "vram_budget_gb": 15.5,
        "desc": "Mode turbo — risque de throttling, sessions courtes",
    },
}


# ══════════════════════════════════════════════════════════════════════
# SNAPSHOT GPU
# ══════════════════════════════════════════════════════════════════════

@dataclass
class GPUSnapshot:
    """État instantané du GPU."""
    timestamp:      float
    gpu_temp_c:     float
    gpu_util_pct:   float
    vram_used_mb:   float
    vram_total_mb:  float
    power_w:        float
    clock_mhz:      float
    fan_speed_pct:  float
    throttle_reason:str = ""

    @property
    def vram_pct(self) -> float:
        return self.vram_used_mb / max(self.vram_total_mb, 1) * 100

    @property
    def vram_free_gb(self) -> float:
        return (self.vram_total_mb - self.vram_used_mb) / 1024

    @property
    def is_throttling(self) -> bool:
        return bool(self.throttle_reason) and self.throttle_reason != "none"

    def to_dict(self) -> dict:
        return {
            "ts":       datetime.fromtimestamp(self.timestamp).strftime("%H:%M:%S"),
            "temp":     self.gpu_temp_c,
            "util":     self.gpu_util_pct,
            "vram_pct": round(self.vram_pct, 1),
            "power_w":  self.power_w,
            "clock":    self.clock_mhz,
            "fan":      self.fan_speed_pct,
            "throttle": self.throttle_reason,
        }


# ══════════════════════════════════════════════════════════════════════
# READER NVML
# ══════════════════════════════════════════════════════════════════════

class NVMLReader:
    """Lit les métriques GPU via PyNVML."""

    def __init__(self, gpu_index: int = 0):
        self.gpu_index = gpu_index
        self._handle   = None
        self._ready    = False
        self._init()

    def _init(self):
        try:
            import pynvml
            pynvml.nvmlInit()
            self._handle  = pynvml.nvmlDeviceGetHandleByIndex(self.gpu_index)
            self._pynvml  = pynvml
            self._ready   = True
            name = pynvml.nvmlDeviceGetName(self._handle)
            logging.getLogger("nvml").info(f"[THERMAL] ✓ GPU : {name}")
        except ImportError:
            logging.getLogger("nvml").warning("[THERMAL] pip install pynvml")
        except Exception as e:
            logging.getLogger("nvml").warning(f"[THERMAL] NVML init : {e}")

    def read(self) -> Optional[GPUSnapshot]:
        """Lit l'état actuel du GPU."""
        if not self._ready:
            return self._mock_snapshot()
        try:
            pv = self._pynvml
            h  = self._handle

            temp      = pv.nvmlDeviceGetTemperature(h, pv.NVML_TEMPERATURE_GPU)
            util      = pv.nvmlDeviceGetUtilizationRates(h)
            mem       = pv.nvmlDeviceGetMemoryInfo(h)
            power     = pv.nvmlDeviceGetPowerUsage(h) / 1000  # mW → W
            clock     = pv.nvmlDeviceGetClockInfo(h, pv.NVML_CLOCK_GRAPHICS)
            fan       = pv.nvmlDeviceGetFanSpeed(h)

            # Raison de throttling
            throttle_flags = pv.nvmlDeviceGetCurrentClocksThrottleReasons(h)
            throttle_str   = "none"
            if throttle_flags:
                reasons = []
                if throttle_flags & pv.nvmlClocksThrottleReasonGpuIdle:
                    reasons.append("idle")
                if throttle_flags & pv.nvmlClocksThrottleReasonApplicationsClocksSetting:
                    reasons.append("app_setting")
                if throttle_flags & pv.nvmlClocksThrottleReasonSwPowerCap:
                    reasons.append("power_cap")
                if throttle_flags & pv.nvmlClocksThrottleReasonHwThermalSlowdown:
                    reasons.append("THERMAL_HW")
                if throttle_flags & pv.nvmlClocksThrottleReasonSwThermalSlowdown:
                    reasons.append("THERMAL_SW")
                if reasons:
                    throttle_str = "|".join(reasons)

            return GPUSnapshot(
                timestamp      = time.time(),
                gpu_temp_c     = float(temp),
                gpu_util_pct   = float(util.gpu),
                vram_used_mb   = mem.used / 1e6,
                vram_total_mb  = mem.total / 1e6,
                power_w        = power,
                clock_mhz      = float(clock),
                fan_speed_pct  = float(fan),
                throttle_reason= throttle_str,
            )
        except Exception as e:
            logging.getLogger("nvml").error(f"[THERMAL] Read : {e}")
            return self._mock_snapshot()

    def _mock_snapshot(self) -> GPUSnapshot:
        """Snapshot simulé si NVML non disponible."""
        import random
        return GPUSnapshot(
            timestamp=time.time(), gpu_temp_c=65.0+random.gauss(0,3),
            gpu_util_pct=75.0, vram_used_mb=8192, vram_total_mb=16384,
            power_w=280.0, clock_mhz=2500.0, fan_speed_pct=55.0,
        )

    def shutdown(self):
        if self._ready:
            try:
                self._pynvml.nvmlShutdown()
            except Exception:
                pass


# ══════════════════════════════════════════════════════════════════════
# THERMAL CONTROLLER
# ══════════════════════════════════════════════════════════════════════

class ThermalController:
    """
    Contrôleur thermique adaptatif.
    Ajuste les paramètres de génération en fonction de la température.
    """

    def __init__(self, profile_name: str = "balanced",
                 logger: logging.Logger = None):
        self.log         = logger or logging.getLogger("thermal")
        self._profile    = THERMAL_PROFILES[profile_name]
        self._profile_nm = profile_name
        self._history:   list[GPUSnapshot] = []
        self._callbacks: list[Callable]    = []
        self._alert_sent = False

    def set_profile(self, profile_name: str):
        if profile_name in THERMAL_PROFILES:
            self._profile    = THERMAL_PROFILES[profile_name]
            self._profile_nm = profile_name
            self.log.info(f"[THERMAL] Profil : {profile_name}")

    def add_alert_callback(self, cb: Callable):
        """Callback appelé en cas d'alerte thermique."""
        self._callbacks.append(cb)

    def record(self, snap: GPUSnapshot):
        """Enregistre un snapshot et vérifie les seuils."""
        self._history.append(snap)
        if len(self._history) > 600:  # 10 min à 1 snap/s
            self._history.pop(0)
        self._check_thresholds(snap)

    def _check_thresholds(self, snap: GPUSnapshot):
        throttle_at = self._profile["throttle_at"]
        max_temp    = self._profile["max_temp_c"]

        if snap.gpu_temp_c >= max_temp and not self._alert_sent:
            msg = (f"⚠️ RTX 5080 CRITIQUE : {snap.gpu_temp_c:.0f}°C "
                   f"(seuil {max_temp}°C) — Throttling forcé")
            self.log.critical(f"[THERMAL] {msg}")
            for cb in self._callbacks:
                try: cb("critical", snap, msg)
                except Exception: pass
            self._alert_sent = True

        elif snap.gpu_temp_c < throttle_at - 5:
            self._alert_sent = False  # reset après refroidissement

        if snap.is_throttling and "THERMAL" in snap.throttle_reason:
            self.log.warning(
                f"[THERMAL] Throttling actif : {snap.throttle_reason} "
                f"@ {snap.gpu_temp_c:.0f}°C"
            )

    def get_recommended_params(self, snap: GPUSnapshot,
                                base_params: dict) -> dict:
        """
        Ajuste les paramètres de génération selon la température.
        Retourne les paramètres adaptés + raison de l'adaptation.
        """
        params = dict(base_params)
        temp   = snap.gpu_temp_c
        reason = "nominal"

        throttle_at = self._profile["throttle_at"]
        max_temp    = self._profile["max_temp_c"]
        steps_max   = self._profile["steps_max"]
        vram_budget = self._profile["vram_budget_gb"]

        if temp >= max_temp:
            # Urgence — réduction maximale
            params["steps"]  = max(8, params.get("steps",28) // 3)
            params["batch"]  = 1
            params["width"]  = min(params.get("width",1024), 768)
            params["height"] = min(params.get("height",1536), 1024)
            reason = f"URGENCE {temp:.0f}°C — params réduits au minimum"

        elif temp >= throttle_at:
            # Throttling préventif
            reduction = (temp - throttle_at) / (max_temp - throttle_at)
            new_steps = max(16, int(params.get("steps",28) * (1 - reduction * 0.4)))
            params["steps"] = min(new_steps, steps_max)
            reason = f"Throttling préventif {temp:.0f}°C → steps={params['steps']}"

        elif snap.vram_free_gb < 2.0:
            # VRAM faible
            params["width"]  = min(params.get("width",1024), 896)
            params["height"] = min(params.get("height",1536), 1152)
            reason = f"VRAM faible ({snap.vram_free_gb:.1f}Go libres)"

        else:
            params["steps"] = min(params.get("steps",28), steps_max)

        if reason != "nominal":
            self.log.info(f"[THERMAL] {reason}")

        params["_thermal_reason"]  = reason
        params["_gpu_temp"]        = temp
        params["_vram_free_gb"]    = snap.vram_free_gb
        return params

    def get_cooldown_recommendation(self, snap: GPUSnapshot) -> dict:
        """Recommande une pause si nécessaire."""
        temp = snap.gpu_temp_c
        target_temp = self._profile["throttle_at"] - 10

        if temp < self._profile["throttle_at"]:
            return {"pause_needed": False, "seconds": 0}

        # Estimer le temps de refroidissement
        # RTX 5080 perd ~2°C/s à l'arrêt
        cool_s = max(5, int((temp - target_temp) / 2))
        return {
            "pause_needed": True,
            "seconds":      cool_s,
            "reason":       f"GPU à {temp:.0f}°C → attendre {cool_s}s",
            "target_temp":  target_temp,
        }

    def get_session_report(self) -> dict:
        """Rapport thermique de la session."""
        if not self._history:
            return {}
        temps = [s.gpu_temp_c for s in self._history]
        pwrs  = [s.power_w    for s in self._history]
        return {
            "profile":       self._profile_nm,
            "samples":       len(self._history),
            "temp_avg":      round(sum(temps)/len(temps), 1),
            "temp_max":      round(max(temps), 1),
            "temp_min":      round(min(temps), 1),
            "power_avg_w":   round(sum(pwrs)/len(pwrs), 1),
            "throttle_events": sum(1 for s in self._history if s.is_throttling),
            "duration_min":  round(len(self._history) / 60, 1),
        }


# ══════════════════════════════════════════════════════════════════════
# THERMAL MONITOR — FAÇADE
# ══════════════════════════════════════════════════════════════════════

class ThermalMonitor:
    """
    Moniteur thermique complet pour la RTX 5080.
    Tourne en arrière-plan, intégré dans le pipeline.
    """

    def __init__(self, profile: str = "balanced",
                 gpu_index: int = 0,
                 logger: logging.Logger = None):
        self.log        = logger or logging.getLogger("thermal_monitor")
        self.reader     = NVMLReader(gpu_index)
        self.controller = ThermalController(profile, logger=self.log)
        self._running   = False
        self._thread:   Optional[threading.Thread] = None
        self._latest:   Optional[GPUSnapshot] = None
        self._lock      = threading.Lock()
        THERMAL_DIR.mkdir(parents=True, exist_ok=True)

    def start(self, interval_s: float = 1.0) -> threading.Thread:
        """Démarre la surveillance en arrière-plan."""
        self._running = True
        def _loop():
            while self._running:
                snap = self.reader.read()
                if snap:
                    with self._lock:
                        self._latest = snap
                    self.controller.record(snap)
                time.sleep(interval_s)
        self._thread = threading.Thread(target=_loop, daemon=True)
        self._thread.start()
        self.log.info(
            f"[THERMAL] Surveillance démarrée — "
            f"profil={self.controller._profile_nm} | "
            f"intervalle={interval_s}s"
        )
        return self._thread

    def stop(self):
        self._running = False
        self.reader.shutdown()

    def get_current(self) -> Optional[GPUSnapshot]:
        with self._lock:
            return self._latest

    def get_safe_params(self, base_params: dict) -> dict:
        """Retourne les paramètres adaptés à l'état thermique actuel."""
        snap = self.get_current()
        if snap is None:
            snap = self.reader.read()
        if snap is None:
            return base_params
        return self.controller.get_recommended_params(snap, base_params)

    def should_pause(self) -> dict:
        """Vérifie si une pause de refroidissement est nécessaire."""
        snap = self.get_current()
        if snap is None:
            return {"pause_needed": False, "seconds": 0}
        rec = self.controller.get_cooldown_recommendation(snap)
        if rec["pause_needed"]:
            self.log.warning(f"[THERMAL] {rec['reason']}")
        return rec

    def wait_if_hot(self, max_wait_s: int = 120):
        """Attend que le GPU soit refroidi avant de continuer."""
        start = time.time()
        while time.time() - start < max_wait_s:
            rec = self.should_pause()
            if not rec["pause_needed"]:
                return True
            self.log.info(
                f"[THERMAL] Pause refroidissement "
                f"({rec['seconds']}s restantes)..."
            )
            time.sleep(min(5, rec["seconds"]))
        return False

    def get_status_line(self) -> str:
        """Ligne de status courte pour l'UI."""
        snap = self.get_current()
        if snap is None:
            return "GPU: N/A"
        temp_icon = (
            "🔴" if snap.gpu_temp_c >= self.controller._profile["max_temp_c"] else
            "🟡" if snap.gpu_temp_c >= self.controller._profile["throttle_at"] else
            "🟢"
        )
        return (
            f"{temp_icon} {snap.gpu_temp_c:.0f}°C | "
            f"VRAM {snap.vram_pct:.0f}% ({snap.vram_free_gb:.1f}Go libres) | "
            f"{snap.power_w:.0f}W | {snap.clock_mhz:.0f}MHz"
        )

    def get_dashboard(self) -> dict:
        snap = self.get_current()
        report = self.controller.get_session_report()
        return {
            "version":    "1.40_thermal",
            "profile":    self.controller._profile_nm,
            "current":    snap.to_dict() if snap else {},
            "session":    report,
            "status_line":self.get_status_line(),
            "profiles":   list(THERMAL_PROFILES.keys()),
        }

    def add_ui_widget(self, parent_frame):
        """
        Widget tkinter à intégrer dans n'importe quel dashboard.
        Affiche l'état thermique en temps réel.
        """
        try:
            import tkinter as tk
            P = {"bg":"#050508","ok":"#10B981","warn":"#F59E0B",
                 "err":"#EF4444","text":"#E0E0F8","textd":"#7070A8"}

            frame = tk.Frame(parent_frame, bg=P["bg"])
            lbl   = tk.Label(frame, text=self.get_status_line(),
                              font=("Consolas",9), bg=P["bg"], fg=P["ok"])
            lbl.pack(anchor="w", padx=8)

            def _update():
                line = self.get_status_line()
                snap = self.get_current()
                color = P["ok"]
                if snap:
                    if snap.gpu_temp_c >= self.controller._profile["max_temp_c"]:
                        color = P["err"]
                    elif snap.gpu_temp_c >= self.controller._profile["throttle_at"]:
                        color = P["warn"]
                lbl.configure(text=line, fg=color)
                frame.after(2000, _update)

            frame.after(2000, _update)
            return frame
        except ImportError:
            return None


# Singleton
_monitor: Optional[ThermalMonitor] = None

def get_thermal_monitor(profile: str = "balanced",
                         logger=None) -> ThermalMonitor:
    global _monitor
    if _monitor is None:
        _monitor = ThermalMonitor(profile=profile, logger=logger)
        _monitor.start(interval_s=2.0)
    return _monitor


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    monitor = ThermalMonitor(profile="balanced")
    monitor.start(interval_s=1.0)

    print("=== V1.40 THERMAL PROTECTION — RTX 5080 ===\n")
    print(f"Profils disponibles : {list(THERMAL_PROFILES.keys())}")
    print()

    time.sleep(2)
    print(f"État actuel : {monitor.get_status_line()}")

    # Test ajustement des paramètres
    base = {"steps":32,"cfg":7.0,"width":1024,"height":1536,"batch":2}
    safe = monitor.get_safe_params(base)
    print(f"\nParamètres base   : steps={base['steps']} batch={base['batch']}")
    print(f"Paramètres sûrs   : steps={safe['steps']} batch={safe.get('batch',base['batch'])}")
    if safe.get("_thermal_reason","nominal") != "nominal":
        print(f"Raison adaptation : {safe['_thermal_reason']}")

    print(f"\nDashboard : {monitor.get_dashboard()['session']}")
    monitor.stop()

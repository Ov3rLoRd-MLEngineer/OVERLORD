"""
agents/watchdog.py — Watchdog Ov3rLoRd V1.49
Surveillance continue du pipeline en temps reel.
FIX V1.49 : overlord_utils centralise, datetime.UTC, context_bus, ASCII logs.
"""

import io
import json
import logging
import math
import requests
import threading
import time
from collections import defaultdict, deque
from datetime import datetime, timezone
from pathlib import Path

try:
    from PIL import Image, ImageFilter, ImageStat
    PIL_OK = True
except ImportError:
    PIL_OK = False

try:
    from agents.overlord_utils import get_api_key
    UTILS_OK = True
except ImportError:
    UTILS_OK = False
    get_api_key = None

try:
    from agents.context_bus import get_bus
    BUS_OK = True
except ImportError:
    BUS_OK = False

COMFY_URL        = "http://127.0.0.1:8188"
WATCHDOG_LOG_DIR = Path("workspace/watchdog_logs")

SHARP_MIN       = 50.0
BRIGHT_MIN      = 20.0
BRIGHT_MAX      = 235.0
COLOR_STD_MIN   = 10.0
STYLE_DRIFT_MAX = 0.35

CB_FAILURE_WINDOW = 5
CB_FAILURE_THRESH = 3
CB_RECOVER_DELAY  = 30


# ── Circuit Breaker ───────────────────────────────────────────────────
class CircuitBreaker:
    CLOSED    = "CLOSED"
    OPEN      = "OPEN"
    HALF_OPEN = "HALF_OPEN"

    def __init__(self, name: str, failure_threshold: int = CB_FAILURE_THRESH,
                 recover_delay: float = CB_RECOVER_DELAY):
        self.name              = name
        self.failure_threshold = failure_threshold
        self.recover_delay     = recover_delay
        self.state             = self.CLOSED
        self.failures          = deque(maxlen=CB_FAILURE_WINDOW)
        self.last_open_time    = 0.0
        self._lock             = threading.Lock()

    def record_success(self):
        with self._lock:
            self.failures.append(0)
            if self.state == self.HALF_OPEN:
                self.state = self.CLOSED

    def record_failure(self):
        with self._lock:
            self.failures.append(1)
            if sum(self.failures) >= self.failure_threshold:
                if self.state != self.OPEN:
                    self.state          = self.OPEN
                    self.last_open_time = time.time()

    def can_proceed(self) -> bool:
        with self._lock:
            if self.state == self.CLOSED:
                return True
            if self.state == self.OPEN:
                if time.time() - self.last_open_time >= self.recover_delay:
                    self.state = self.HALF_OPEN
                    return True
                return False
            return True

    def status(self) -> dict:
        return {"name": self.name, "state": self.state,
                "failures": sum(self.failures), "window": len(self.failures)}


# ── Analyse qualite d'une frame ───────────────────────────────────────
class FrameReport:
    def __init__(self, shot_id: str):
        self.shot_id = shot_id
        self.passed  = True
        self.issues  = []
        self.metrics = {}
        self.verdict = "PASS"

    def fail(self, reason: str):
        self.passed  = False
        self.verdict = "FAIL"
        self.issues.append(reason)

    def warn(self, reason: str):
        self.issues.append(f"[WARN] {reason}")
        if self.verdict == "PASS":
            self.verdict = "WARN"

    def to_dict(self) -> dict:
        return {"shot_id": self.shot_id, "verdict": self.verdict,
                "passed": self.passed, "issues": self.issues, "metrics": self.metrics}


def analyze_frame(img_data: bytes, shot_id: str = "?",
                  palette: list = None) -> FrameReport:
    report = FrameReport(shot_id)
    if not PIL_OK:
        report.warn("Pillow non installe — analyse image impossible")
        return report

    try:
        img = Image.open(io.BytesIO(img_data)).convert("RGB")
    except Exception as e:
        report.fail(f"Image illisible : {e}")
        return report

    w, h = img.size
    report.metrics["dimensions"] = f"{w}x{h}"

    # Nettete (Laplacien)
    gray       = img.convert("L")
    gray_small = gray.resize((512, 512), Image.LANCZOS)
    lap        = gray_small.filter(ImageFilter.FIND_EDGES)
    data_lap   = list(lap.getdata())
    mean       = sum(data_lap) / len(data_lap)
    var        = sum((x - mean) ** 2 for x in data_lap) / len(data_lap)
    report.metrics["sharpness"] = round(var, 1)
    if var < SHARP_MIN:
        report.fail(f"Image floue (Laplacien={var:.1f} < seuil={SHARP_MIN})")
    elif var < SHARP_MIN * 1.5:
        report.warn(f"Nettete limite (Laplacien={var:.1f})")

    # Luminosite
    stat       = ImageStat.Stat(gray)
    brightness = stat.mean[0]
    report.metrics["brightness"] = round(brightness, 1)
    if brightness < BRIGHT_MIN:
        report.fail(f"Image trop sombre (brightness={brightness:.0f})")
    elif brightness > BRIGHT_MAX:
        report.fail(f"Image surexposee (brightness={brightness:.0f})")

    # Diversite colorimetrique
    stat_rgb  = ImageStat.Stat(img)
    color_std = sum(stat_rgb.stddev) / 3
    report.metrics["color_diversity"] = round(color_std, 1)
    if color_std < COLOR_STD_MIN:
        report.fail(f"Image monochrome/artefact (color_std={color_std:.1f})")

    # Zones noires excessives
    pixels    = list(gray.getdata())
    black_pct = sum(1 for p in pixels if p < 15) / len(pixels)
    report.metrics["black_pct"] = round(black_pct * 100, 1)
    if black_pct > 0.4:
        report.fail(f"Zone noire excessive : {black_pct:.0%}")
    elif black_pct > 0.2:
        report.warn(f"Zone noire importante : {black_pct:.0%}")

    # Zones blanches excessives
    white_pct = sum(1 for p in pixels if p > 240) / len(pixels)
    report.metrics["white_pct"] = round(white_pct * 100, 1)
    if white_pct > 0.5:
        report.fail(f"Surexposition / blanc excessif : {white_pct:.0%}")

    # Coherence palette
    if palette:
        palette_score = _check_palette(img, palette)
        report.metrics["palette_match"] = round(palette_score, 2)
        if palette_score < 0.3:
            report.warn(f"Coherence palette faible ({palette_score:.0%}) — style potentiellement deviant")

    return report


def _check_palette(img: Image.Image, palette_hex: list) -> float:
    def hex_to_rgb(h: str):
        h = h.lstrip("#")
        return tuple(int(h[i:i+2], 16) for i in (0, 2, 4))
    try:
        ref_colors = [hex_to_rgb(c) for c in palette_hex if c.startswith("#")]
        if not ref_colors:
            return 1.0
        small  = img.resize((50, 50), Image.LANCZOS)
        pixels = list(small.getdata())
        total_match = 0
        for px in pixels:
            min_dist = min(math.sqrt(sum((px[i]-ref[i])**2 for i in range(3))) for ref in ref_colors)
            total_match += max(0, 1 - min_dist / 200)
        return total_match / len(pixels)
    except Exception:
        return 1.0


# ── Coherence inter-frames ────────────────────────────────────────────
def compute_color_signature(img_data: bytes) -> list:
    if not PIL_OK:
        return []
    try:
        img   = Image.open(io.BytesIO(img_data)).convert("RGB")
        small = img.resize((64, 64), Image.LANCZOS)
        sig   = []
        for band in small.split():
            hist   = band.histogram()
            binned = [sum(hist[i*32:(i+1)*32]) for i in range(8)]
            total  = sum(binned) or 1
            sig.extend([b/total for b in binned])
        return sig
    except Exception:
        return []


def style_drift_score(sig_a: list, sig_b: list) -> float:
    if not sig_a or not sig_b or len(sig_a) != len(sig_b):
        return 0.0
    dot = sum(a*b for a,b in zip(sig_a, sig_b))
    na  = math.sqrt(sum(a**2 for a in sig_a))
    nb  = math.sqrt(sum(b**2 for b in sig_b))
    if na == 0 or nb == 0:
        return 0.0
    return 1.0 - (dot / (na * nb))


def check_sequence_coherence(frames_data: list, max_drift: float = STYLE_DRIFT_MAX,
                              logger: logging.Logger = None) -> dict:
    _log = logger or logging.getLogger("watchdog.coherence")
    if len(frames_data) < 2:
        return {"coherent": True, "drifts": [], "max_drift": 0.0}

    signatures = [compute_color_signature(f) for f in frames_data]
    drifts     = []
    breaks     = []

    for i in range(1, len(signatures)):
        if signatures[i-1] and signatures[i]:
            drift = style_drift_score(signatures[i-1], signatures[i])
            drifts.append({"frame": i, "drift": round(drift, 3)})
            if drift > max_drift:
                breaks.append(i)
                _log.warning(f"[WATCHDOG] Rupture style : frame {i-1}->{i} (drift={drift:.3f})")

    avg_drift = sum(d["drift"] for d in drifts) / len(drifts) if drifts else 0.0
    return {
        "coherent":     len(breaks) == 0,
        "drifts":       drifts,
        "style_breaks": breaks,
        "avg_drift":    round(avg_drift, 3),
        "max_drift":    round(max(d["drift"] for d in drifts), 3) if drifts else 0.0,
    }


# ── Watchdog principal ────────────────────────────────────────────────
class Watchdog:

    def __init__(self, run_id: str, logger: logging.Logger,
                 check_interval: float = 15.0):
        self.run_id         = run_id
        self.logger         = logger
        self.check_interval = check_interval
        self._running       = False
        self._thread        = None
        self._lock          = threading.Lock()

        self.breakers = {
            "comfyui":    CircuitBreaker("comfyui",    failure_threshold=3, recover_delay=30),
            "anthropic":  CircuitBreaker("anthropic",  failure_threshold=3, recover_delay=60),
            "sourcing":   CircuitBreaker("sourcing",   failure_threshold=5, recover_delay=20),
            "scenario":   CircuitBreaker("scenario",   failure_threshold=3, recover_delay=30),
            "storyboard": CircuitBreaker("storyboard", failure_threshold=3, recover_delay=30),
        }

        self.metrics = {
            "start_time":      time.time(),
            "checks":          0,
            "comfy_uptime":    0,
            "comfy_downtime":  0,
            "frames_analyzed": 0,
            "frames_failed":   0,
        }

        WATCHDOG_LOG_DIR.mkdir(parents=True, exist_ok=True)

    def start(self):
        self._running = True
        self._thread  = threading.Thread(
            target=self._monitor_loop, daemon=True,
            name=f"watchdog_{self.run_id}"
        )
        self._thread.start()
        self.logger.info("[WATCHDOG] Demarre en arriere-plan")

    def stop(self):
        self._running = False
        if self._thread:
            self._thread.join(timeout=5)
        self.logger.info("[WATCHDOG] Arrete")
        self._save_metrics()

    def _monitor_loop(self):
        while self._running:
            try:
                self._check_comfyui()
                self._check_anthropic()
                self.metrics["checks"] += 1
            except Exception as e:
                self.logger.debug(f"[WATCHDOG] Erreur monitoring : {e}")
            time.sleep(self.check_interval)

    def _check_comfyui(self):
        breaker = self.breakers["comfyui"]
        try:
            resp = requests.get(f"{COMFY_URL}/system_stats", timeout=5)
            if resp.status_code == 200:
                breaker.record_success()
                self.metrics["comfy_uptime"] += self.check_interval
            else:
                raise ValueError(f"HTTP {resp.status_code}")
        except Exception as e:
            breaker.record_failure()
            self.metrics["comfy_downtime"] += self.check_interval
            if breaker.state == CircuitBreaker.OPEN:
                self.logger.error(
                    f"[WATCHDOG] ComfyUI HORS LIGNE "
                    f"({sum(breaker.failures)} echecs) — {e}"
                )
                # Publier l'alerte sur le bus
                if BUS_OK:
                    try:
                        get_bus().write("watchdog.comfyui_status", "DOWN",
                                        agent_id="watchdog")
                    except Exception:
                        pass

    def _check_anthropic(self):
        breaker = self.breakers["anthropic"]
        try:
            resp = requests.head("https://api.anthropic.com", timeout=5)
            if resp.status_code < 500:
                breaker.record_success()
            else:
                breaker.record_failure()
        except Exception:
            breaker.record_failure()

    def health_check(self) -> dict:
        status = {}
        try:
            r = requests.get(f"{COMFY_URL}/system_stats", timeout=5)
            if r.status_code == 200:
                stats = r.json()
                status["comfyui"] = {
                    "up":    True,
                    "vram":  stats.get("system", {}).get("vram_total", "?"),
                    "queue": stats.get("queue_running", 0),
                }
            else:
                status["comfyui"] = {"up": False, "code": r.status_code}
        except Exception as e:
            status["comfyui"] = {"up": False, "error": str(e)}

        status["circuit_breakers"] = {
            name: cb.status() for name, cb in self.breakers.items()
        }

        # Publier l'etat sante sur le bus
        if BUS_OK:
            try:
                comfy_up = status.get("comfyui", {}).get("up", False)
                get_bus().write("watchdog.comfyui_status",
                                "UP" if comfy_up else "DOWN",
                                agent_id="watchdog")
                get_bus().write("watchdog.checks", self.metrics["checks"],
                                agent_id="watchdog")
            except Exception:
                pass

        return status

    def can_proceed(self, service: str) -> bool:
        breaker = self.breakers.get(service)
        if not breaker:
            return True
        can = breaker.can_proceed()
        if not can:
            self.logger.warning(
                f"[WATCHDOG] Circuit breaker OPEN pour '{service}' — "
                f"attente {CB_RECOVER_DELAY}s"
            )
        return can

    def guard_frame(self, img_data: bytes, shot_id: str = "?",
                    palette: list = None) -> FrameReport:
        report = analyze_frame(img_data, shot_id, palette)

        with self._lock:
            self.metrics["frames_analyzed"] += 1
            if not report.passed:
                self.metrics["frames_failed"] += 1

        level = logging.INFO if report.passed else logging.WARNING
        self.logger.log(
            level,
            f"[WATCHDOG/FRAME] {shot_id} -> {report.verdict} | "
            f"nettete={report.metrics.get('sharpness','?')} | "
            f"luminosite={report.metrics.get('brightness','?')}"
            + (f" | problemes={report.issues}" if report.issues else " | OK")
        )

        if not report.passed:
            self._save_frame_report(report)

        return report

    def guard_sequence(self, frames_data: list) -> dict:
        result = check_sequence_coherence(frames_data, max_drift=STYLE_DRIFT_MAX,
                                          logger=self.logger)
        breaks = result.get("style_breaks", [])
        if breaks:
            self.logger.warning(
                f"[WATCHDOG] {len(breaks)} rupture(s) de style aux frames : {breaks}"
            )
            if BUS_OK:
                try:
                    get_bus().write("watchdog.style_breaks", breaks,
                                    agent_id="watchdog")
                except Exception:
                    pass
        else:
            self.logger.info(
                f"[WATCHDOG] Sequence coherente — drift moyen={result['avg_drift']:.3f}"
            )
        return result

    def report(self) -> dict:
        elapsed  = time.time() - self.metrics["start_time"]
        analyzed = self.metrics["frames_analyzed"]
        failed   = self.metrics["frames_failed"]
        fail_rate = failed / analyzed if analyzed else 0.0

        r = {
            "run_id":           self.run_id,
            "elapsed_s":        round(elapsed, 1),
            "checks":           self.metrics["checks"],
            "comfy_uptime_s":   round(self.metrics["comfy_uptime"], 0),
            "frames_analyzed":  analyzed,
            "frames_failed":    failed,
            "frame_fail_rate":  f"{fail_rate:.0%}",
            "circuit_breakers": {n: cb.status() for n, cb in self.breakers.items()},
        }

        # Publier le rapport final sur le bus
        if BUS_OK:
            try:
                bus = get_bus()
                bus.write("watchdog.frames_analyzed",  analyzed,  agent_id="watchdog")
                bus.write("watchdog.frames_failed",    failed,    agent_id="watchdog")
                bus.write("watchdog.frame_fail_rate",  fail_rate, agent_id="watchdog")
            except Exception:
                pass

        return r

    def _save_metrics(self):
        path = WATCHDOG_LOG_DIR / f"{self.run_id}_watchdog.json"
        try:
            path.write_text(json.dumps(self.report(), indent=2, ensure_ascii=False),
                            encoding="utf-8")
        except Exception:
            pass

    def _save_frame_report(self, report: FrameReport):
        # FIX : datetime.utcnow() -> datetime.now(tz=timezone.utc)
        ts   = datetime.now(tz=timezone.utc).strftime("%Y%m%d_%H%M%S_%f")
        path = WATCHDOG_LOG_DIR / f"frame_{report.shot_id}_{ts}.json"
        try:
            path.write_text(json.dumps(report.to_dict(), indent=2, ensure_ascii=False),
                            encoding="utf-8")
        except Exception:
            pass


if __name__ == "__main__":
    import sys, io as _io
    if hasattr(sys.stdout, 'buffer'):
        sys.stdout = _io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
    logging.basicConfig(level=logging.DEBUG)
    _log = logging.getLogger("watchdog_test")

    wd = Watchdog("test_run", _log, check_interval=5)
    wd.start()
    print("Health check :")
    print(json.dumps(wd.health_check(), indent=2))
    cb = wd.breakers["comfyui"]
    for _ in range(4):
        cb.record_failure()
    print(f"Circuit breaker apres 4 echecs : {cb.status()}")
    print(f"Can proceed : {wd.can_proceed('comfyui')}")
    time.sleep(2)
    wd.stop()
    print(json.dumps(wd.report(), indent=2))
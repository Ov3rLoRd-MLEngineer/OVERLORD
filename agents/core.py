"""
agents/core.py — Ov3rLoRd V1.10 — Extensions Neuronales Avancees
Residual, Temperature, Circuit Breaker, Hot Reload, KV Cache, Event Sourcing, Confidence.
FIX V1.49k : context_bus connecte, ASCII dans __main__.
"""

import ast
import json
import importlib
import importlib.util
import hashlib
import logging
import threading
import time
import math
import queue
from pathlib import Path
from datetime import datetime
from dataclasses import dataclass, field
from typing import Any, Callable, Optional
from enum import Enum

try:
    from agents.context_bus import get_bus
    BUS_OK = True
except ImportError:
    BUS_OK = False

EVENTS_DIR = Path("workspace/events")
CACHE_DIR  = Path("workspace/kv_cache")


# ── Residual Pipeline ─────────────────────────────────────────────────
class ResidualPipeline:

    def __init__(self, residual_weight: float = 0.2,
                 logger: logging.Logger = None):
        self.log    = logger or logging.getLogger("residual")
        self.weight = residual_weight
        self._accumulated: dict = {}

    def run_with_residual(self, blocks: list[tuple[str, Callable]],
                           initial_input: dict) -> dict:
        current_input     = dict(initial_input)
        self._accumulated = {}
        results           = {}

        for block_name, block_fn in blocks:
            enriched_input = dict(current_input)
            if self._accumulated:
                enriched_input["_residual"] = dict(self._accumulated)
                self.log.debug(
                    f"[RESIDUAL] {block_name} recoit residuel "
                    f"de {list(self._accumulated.keys())}"
                )
            start = time.time()
            try:
                result   = block_fn(enriched_input)
                duration = time.time() - start
                # ASCII : pas d'emoji dans les logs Python
                self.log.info(f"[RESIDUAL] OK {block_name} ({duration:.1f}s)")
            except Exception as e:
                self.log.error(f"[RESIDUAL] ERR {block_name} : {e}")
                result = {"error": str(e)}

            results[block_name] = result

            if isinstance(result, dict):
                for k, v in result.items():
                    if k.startswith("_"):
                        continue
                    if k in self._accumulated:
                        old = self._accumulated[k]
                        if isinstance(old,(int,float)) and isinstance(v,(int,float)):
                            self._accumulated[k] = old*(1-self.weight) + v*self.weight
                        else:
                            self._accumulated[k] = v
                    else:
                        self._accumulated[k] = v

            current_input = enriched_input
            if isinstance(result, dict):
                current_input.update({k:v for k,v in result.items() if not k.startswith("_")})

        # Publier sur le bus
        if BUS_OK:
            try:
                bus = get_bus()
                bus.write("v110.blocks_run",     len(blocks),          agent_id="v110_residual")
                bus.write("v110.residual_keys",  list(self._accumulated.keys()), agent_id="v110_residual")
            except Exception:
                pass

        return {
            "blocks_run": len(blocks),
            "final_state":current_input,
            "results":    results,
            "residual":   dict(self._accumulated),
        }


# ── Temperature Controller ────────────────────────────────────────────
class TemperatureController:

    DEFAULT_TEMPS = {
        "sourcing":0.7,"scenario":0.9,"storyboard":0.8,"production":0.3,
        "postprod":0.5,"critic":0.1,"watchdog":0.0,"learning":1.2,
        "legacy":0.4,"marketing":1.0,"community":0.8,
    }

    def __init__(self):
        self._temps:   dict[str,float] = dict(self.DEFAULT_TEMPS)
        self._history: dict[str,list]  = {}
        self._lock     = threading.Lock()

    def get(self, agent: str) -> float:
        with self._lock:
            return self._temps.get(agent, 0.7)

    def set(self, agent: str, temp: float):
        temp = max(0.0, min(2.0, temp))
        with self._lock:
            self._temps[agent] = temp

    def adapt(self, agent: str, success: bool, score: float = 0.5):
        with self._lock:
            if agent not in self._history:
                self._history[agent] = []
            self._history[agent].append((success, score))
            self._history[agent] = self._history[agent][-10:]
            recent       = self._history[agent]
            if len(recent) < 3:
                return
            success_rate = sum(1 for s,_ in recent if s) / len(recent)
            avg_score    = sum(sc for _,sc in recent) / len(recent)
            current      = self._temps.get(agent, 0.7)
            if success_rate > 0.8 and avg_score > 0.7:
                self._temps[agent] = max(0.1, current - 0.05)
            elif success_rate < 0.4 or avg_score < 0.4:
                self._temps[agent] = min(1.5, current + 0.1)

    def apply_to_llm_params(self, agent: str, base_params: dict) -> dict:
        temp   = self.get(agent)
        params = dict(base_params)
        params["temperature"] = min(1.0, temp)
        if "cfg" in params:
            params["cfg"] = round(params["cfg"] * (1.5 - temp*0.5), 1)
            params["cfg"] = max(3.0, min(12.0, params["cfg"]))
        return params

    def get_all(self) -> dict:
        with self._lock:
            return dict(self._temps)


# ── Circuit Breaker ───────────────────────────────────────────────────
class CircuitState(Enum):
    CLOSED    = "closed"
    OPEN      = "open"
    HALF_OPEN = "half_open"


@dataclass
class CircuitBreaker:
    name:              str
    failure_threshold: int   = 3
    recovery_timeout:  float = 60.0
    state:             CircuitState = CircuitState.CLOSED
    failure_count:     int   = 0
    last_failure:      float = 0.0
    success_count:     int   = 0

    def call(self, fn: Callable, *args, **kwargs) -> Any:
        if self.state == CircuitState.OPEN:
            elapsed = time.time() - self.last_failure
            if elapsed >= self.recovery_timeout:
                self.state = CircuitState.HALF_OPEN
            else:
                raise RuntimeError(
                    f"[CIRCUIT/{self.name}] Circuit OUVERT "
                    f"({self.recovery_timeout - elapsed:.0f}s restantes)"
                )
        try:
            result = fn(*args, **kwargs)
            self._on_success()
            return result
        except Exception:
            self._on_failure()
            raise

    def _on_success(self):
        if self.state == CircuitState.HALF_OPEN:
            self.success_count += 1
            if self.success_count >= 2:
                self.state         = CircuitState.CLOSED
                self.failure_count = 0
                self.success_count = 0
        elif self.state == CircuitState.CLOSED:
            self.failure_count = max(0, self.failure_count - 1)

    def _on_failure(self):
        self.failure_count += 1
        self.last_failure   = time.time()
        self.success_count  = 0
        if self.failure_count >= self.failure_threshold:
            self.state = CircuitState.OPEN

    def status(self) -> dict:
        return {
            "name":          self.name,
            "state":         self.state.value,
            "failures":      self.failure_count,
            "threshold":     self.failure_threshold,
            "time_to_retry": max(0, self.recovery_timeout-(time.time()-self.last_failure))
                             if self.state==CircuitState.OPEN else 0,
        }


class CircuitBreakerRegistry:
    _breakers: dict[str, CircuitBreaker] = {}
    _lock = threading.Lock()

    @classmethod
    def get(cls, name: str, **kwargs) -> CircuitBreaker:
        with cls._lock:
            if name not in cls._breakers:
                cls._breakers[name] = CircuitBreaker(name=name, **kwargs)
            return cls._breakers[name]

    @classmethod
    def status_all(cls) -> list[dict]:
        with cls._lock:
            return [b.status() for b in cls._breakers.values()]


# ── Hot Reloader ──────────────────────────────────────────────────────
class HotReloader:

    def __init__(self, watch_dir: str, logger: logging.Logger = None):
        self.log       = logger or logging.getLogger("hotreload")
        self.watch_dir = Path(watch_dir)
        self._modules: dict[str,tuple] = {}
        self._running  = False
        self._lock     = threading.Lock()
        self._callbacks: list[Callable] = []

    def add_callback(self, cb: Callable):
        self._callbacks.append(cb)

    def _file_hash(self, path: Path) -> str:
        return hashlib.md5(path.read_bytes()).hexdigest()

    def register(self, py_path: str) -> bool:
        p = Path(py_path)
        if not p.exists():
            return False
        try:
            spec   = importlib.util.spec_from_file_location(p.stem, str(p))
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
            with self._lock:
                self._modules[str(p)] = (module, p.stat().st_mtime, self._file_hash(p))
            return True
        except Exception as e:
            self.log.warning(f"[HOT] Register {p.name} : {e}")
            return False

    def _check_and_reload(self):
        with self._lock:
            paths = list(self._modules.keys())
        for path_str in paths:
            p = Path(path_str)
            if not p.exists():
                continue
            try:
                current_hash = self._file_hash(p)
                _,_,old_hash = self._modules[path_str]
                if current_hash != old_hash:
                    self.log.info(f"[HOT] Rechargement : {p.name}")
                    spec   = importlib.util.spec_from_file_location(p.stem, str(p))
                    module = importlib.util.module_from_spec(spec)
                    spec.loader.exec_module(module)
                    with self._lock:
                        self._modules[path_str] = (module, p.stat().st_mtime, current_hash)
                    for cb in self._callbacks:
                        try: cb(p.stem, module)
                        except Exception: pass
            except SyntaxError as e:
                self.log.error(f"[HOT] Syntaxe invalide {p.name} : {e}")
            except Exception:
                pass

    def start(self, interval_s: float = 2.0):
        self._running = True
        def _loop():
            while self._running:
                self._check_and_reload()
                time.sleep(interval_s)
        threading.Thread(target=_loop, daemon=True).start()
        self.log.info(f"[HOT] Surveillance demarree — {len(self._modules)} modules")

    def stop(self):
        self._running = False


# ── KV Cache ──────────────────────────────────────────────────────────
class KVCache:

    def __init__(self, max_size: int = 200, ttl_s: float = 3600):
        self._cache:    dict[str,dict] = {}
        self._max_size  = max_size
        self._ttl_s     = ttl_s
        self._lock      = threading.Lock()
        self._hits      = 0
        self._misses    = 0
        CACHE_DIR.mkdir(parents=True, exist_ok=True)

    def _key(self, *args, **kwargs) -> str:
        content = json.dumps({"args":list(args),"kwargs":kwargs},
                              sort_keys=True, ensure_ascii=False, default=str)
        return hashlib.sha256(content.encode()).hexdigest()[:16]

    def get(self, *args, **kwargs) -> tuple[bool, Any]:
        k = self._key(*args, **kwargs)
        with self._lock:
            entry = self._cache.get(k)
            if entry and (time.time()-entry["ts"]) < self._ttl_s:
                self._hits += 1
                return True, entry["value"]
            self._misses += 1
            return False, None

    def set(self, value: Any, *args, **kwargs):
        k = self._key(*args, **kwargs)
        with self._lock:
            self._cache[k] = {"value":value,"ts":time.time()}
            if len(self._cache) > self._max_size:
                oldest = sorted(self._cache.items(), key=lambda x: x[1]["ts"])
                for ok,_ in oldest[:self._max_size//4]:
                    del self._cache[ok]

    def cached(self, fn: Callable) -> Callable:
        def wrapper(*args, **kwargs):
            hit, val = self.get(*args, **kwargs)
            if hit:
                return val
            result = fn(*args, **kwargs)
            self.set(result, *args, **kwargs)
            return result
        return wrapper

    def stats(self) -> dict:
        total = self._hits + self._misses
        return {
            "hits":     self._hits,
            "misses":   self._misses,
            "hit_rate": round(self._hits/total*100,1) if total else 0,
            "size":     len(self._cache),
        }


# ── Event Sourcing ────────────────────────────────────────────────────
class EventType(Enum):
    AGENT_STARTED   = "agent_started"
    AGENT_ENDED     = "agent_ended"
    CONTEXT_WRITE   = "context_write"
    PARAM_CHANGE    = "param_change"
    LLM_CALL        = "llm_call"
    IMAGE_GENERATED = "image_generated"
    ERROR           = "error"
    HUMAN_INPUT     = "human_input"
    FEEDBACK        = "feedback"


@dataclass
class Event:
    id:        str
    type:      EventType
    agent:     str
    data:      dict
    timestamp: float = field(default_factory=time.time)
    run_id:    str   = ""


class EventStore:

    def __init__(self, run_id: str):
        self.run_id  = run_id
        self._events: list[Event] = []
        self._lock   = threading.Lock()
        EVENTS_DIR.mkdir(parents=True, exist_ok=True)
        self._file   = EVENTS_DIR / f"{run_id}.jsonl"

    def record(self, event_type: EventType, agent: str, data: dict) -> Event:
        event = Event(
            id=hashlib.md5(f"{agent}{time.time()}".encode()).hexdigest()[:8],
            type=event_type, agent=agent, data=data, run_id=self.run_id,
        )
        with self._lock:
            self._events.append(event)
            with open(self._file,"a",encoding="utf-8") as f:
                f.write(json.dumps({
                    "id":event.id,"type":event.type.value,
                    "agent":event.agent,"data":event.data,
                    "timestamp":event.timestamp,"run_id":event.run_id,
                }, ensure_ascii=False) + "\n")
        return event

    def replay_from(self, from_agent: str) -> list[Event]:
        with self._lock:
            found  = False
            replay = []
            for e in self._events:
                if e.agent == from_agent:
                    found = True
                if found:
                    replay.append(e)
        return replay

    def get_timeline(self) -> list[dict]:
        with self._lock:
            return [
                {"time":  datetime.fromtimestamp(e.timestamp).strftime("%H:%M:%S.%f")[:11],
                 "agent": e.agent, "type": e.type.value, "data": str(e.data)[:80]}
                for e in self._events
            ]

    @classmethod
    def load(cls, run_id: str) -> "EventStore":
        store = cls(run_id)
        f     = EVENTS_DIR / f"{run_id}.jsonl"
        if f.exists():
            for line in f.read_text(encoding="utf-8").splitlines():
                if not line.strip():
                    continue
                try:
                    d = json.loads(line)
                    store._events.append(Event(
                        id=d["id"], type=EventType(d["type"]),
                        agent=d["agent"], data=d["data"],
                        timestamp=d["timestamp"], run_id=d["run_id"],
                    ))
                except Exception:
                    pass
        return store


# ── Confidence Calibrator ─────────────────────────────────────────────
class ConfidenceCalibrator:

    def __init__(self):
        self._history: dict[str,list] = {}

    def record(self, agent: str, declared_confidence: float, actual_success: bool):
        if agent not in self._history:
            self._history[agent] = []
        self._history[agent].append((declared_confidence, float(actual_success)))

    def calibrate(self, agent: str, raw_confidence: float) -> float:
        history = self._history.get(agent, [])
        if len(history) < 5:
            return raw_confidence
        declared   = [h[0] for h in history]
        actual     = [h[1] for h in history]
        avg_decl   = sum(declared)/len(declared)
        avg_act    = sum(actual)/len(actual)
        ratio      = avg_act / (avg_decl + 1e-9)
        calibrated = raw_confidence * ratio
        return max(0.01, min(0.99, calibrated))

    def is_uncertain(self, agent: str, confidence: float,
                      threshold: float = 0.5) -> bool:
        return self.calibrate(agent, confidence) < threshold

    def get_agent_reliability(self, agent: str) -> dict:
        history = self._history.get(agent, [])
        if not history:
            return {"agent":agent,"reliability":0.5,"n_samples":0}
        avg_success        = sum(h[1] for h in history)/len(history)
        avg_conf           = sum(h[0] for h in history)/len(history)
        calibration_error  = abs(avg_conf-avg_success)
        return {
            "agent":             agent,
            "reliability":       round(avg_success,3),
            "avg_confidence":    round(avg_conf,3),
            "calibration_error": round(calibration_error,3),
            "n_samples":         len(history),
        }


# ── Facade OverLordV110 ───────────────────────────────────────────────
class OverLordV110:

    def __init__(self, logger: logging.Logger = None):
        self.log         = logger or logging.getLogger("v110")
        self.residual    = ResidualPipeline(logger=self.log)
        self.temperature = TemperatureController()
        self.breakers    = CircuitBreakerRegistry()
        self.hot_reload  = HotReloader("agents", logger=self.log)
        self.kv_cache    = KVCache()
        self.calibrator  = ConfidenceCalibrator()
        self._event_stores: dict[str,EventStore] = {}

    def new_run(self, run_id: str) -> EventStore:
        store = EventStore(run_id)
        self._event_stores[run_id] = store
        return store

    def get_run(self, run_id: str) -> Optional[EventStore]:
        return self._event_stores.get(run_id)

    def safe_call(self, agent_name: str, fn: Callable, *args, **kwargs) -> Any:
        breaker = self.breakers.get(agent_name)
        try:
            result = breaker.call(fn, *args, **kwargs)
            self.calibrator.record(agent_name, 0.8, True)
            self.temperature.adapt(agent_name, True, 0.8)
            return result
        except RuntimeError as e:
            self.log.warning(f"[V110] {e}")
            return None
        except Exception as e:
            self.calibrator.record(agent_name, 0.8, False)
            self.temperature.adapt(agent_name, False, 0.2)
            self.log.error(f"[V110] Erreur {agent_name} : {e}")
            return None

    def get_dashboard(self) -> dict:
        d = {
            "version":     "1.10",
            "temperatures":self.temperature.get_all(),
            "circuits":    CircuitBreakerRegistry.status_all(),
            "kv_cache":    self.kv_cache.stats(),
            "hot_modules": len(self.hot_reload._modules),
            "event_runs":  len(self._event_stores),
        }
        if BUS_OK:
            try:
                bus = get_bus()
                bus.write("v110.kv_hit_rate", d["kv_cache"]["hit_rate"], agent_id="v110")
                bus.write("v110.event_runs",  d["event_runs"],           agent_id="v110")
            except Exception:
                pass
        return d


_v110: Optional[OverLordV110] = None

def get_v110(logger=None) -> OverLordV110:
    global _v110
    if _v110 is None:
        _v110 = OverLordV110(logger)
    return _v110


if __name__ == "__main__":
    import sys, io
    if hasattr(sys.stdout,'buffer'):
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
    logging.basicConfig(level=logging.INFO)
    _log = logging.getLogger("v110_test")
    v110 = OverLordV110(_log)

    # ASCII : pas de box-drawing dans __main__
    print("=== V1.10 Tests des composants ===\n")

    def bloc_sourcing(inp):
        return {"trend":"dark_fantasy","score":0.85}
    def bloc_scenario(inp):
        res = inp.get("_residual",{})
        return {"title":f"Histoire {res.get('trend','neutre')}","acts":3}
    def bloc_storyboard(inp):
        res = inp.get("_residual",{})
        return {"shots":12,"inherited_trend":res.get("trend","?")}

    result = v110.residual.run_with_residual(
        [("sourcing",bloc_sourcing),("scenario",bloc_scenario),("storyboard",bloc_storyboard)],
        initial_input={"media":"anime"}
    )
    print(f"Residual : storyboard voit trend = '{result['results']['storyboard']['inherited_trend']}'")
    print(f"\nTemperature scenario : {v110.temperature.get('scenario')}")
    v110.temperature.adapt("scenario",False,0.2)
    print(f"Temperature scenario apres echec : {v110.temperature.get('scenario'):.2f}")
    cb = CircuitBreakerRegistry.get("test_agent", failure_threshold=2)
    for i in range(3):
        try:
            cb.call(lambda: (_ for _ in ()).throw(ValueError("Erreur simulee")))
        except Exception:
            pass
    print(f"\nCircuit test_agent : {cb.status()['state']}")
    cache = v110.kv_cache
    cache.set("resultat couteux","prompt=test","agent=sourcing")
    hit, val = cache.get("prompt=test","agent=sourcing")
    print(f"\nKV Cache hit : {hit} | valeur : {val}")
    print(f"Stats : {cache.stats()}")
    print("\n=== DASHBOARD V1.10 ===")
    print(json.dumps(v110.get_dashboard(), indent=2, ensure_ascii=False))
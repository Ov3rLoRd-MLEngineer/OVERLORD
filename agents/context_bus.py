"""
agents/context_bus.py -- Context Bus Ov3rLoRd V1.49o
Bus de communication inter-agents. Singleton thread-safe.
FIX V1.49o : write() accepte maintenant agent_id et confidence en kwargs
(30+ modules les passent depuis V1.49 -- provoquait TypeError silencieux).
"""

import json
import time
import threading
import logging
from pathlib import Path
from typing import Any, Optional

log = logging.getLogger("context_bus")

BUS_DIR = Path("workspace/context_bus")


class ContextBus:
    """
    Bus de messages inter-agents.
    Chaque entree : {"value": ..., "agent_id": ..., "confidence": ..., "ts": ...}
    """

    def __init__(self):
        self._store: dict[str, dict] = {}
        self._lock  = threading.RLock()
        self._subscribers: dict[str, list] = {}
        BUS_DIR.mkdir(parents=True, exist_ok=True)
        self._persist_path = BUS_DIR / "bus_state.json"
        self._load()

    def _load(self):
        if self._persist_path.exists():
            try:
                data = json.loads(self._persist_path.read_text(encoding="utf-8"))
                with self._lock:
                    self._store = data
            except Exception:
                pass

    def _save(self):
        try:
            with self._lock:
                snapshot = dict(self._store)
            self._persist_path.write_text(
                json.dumps(snapshot, ensure_ascii=False, default=str),
                encoding="utf-8"
            )
        except Exception:
            pass

    def write(self, key: str, value: Any,
              agent_id: str = "",
              confidence: float = 1.0,
              **kwargs) -> None:
        """
        Ecrit une valeur sur le bus.
        FIX V1.49o : agent_id et confidence acceptes en kwargs
        (etaient passes par 30+ modules mais non supportes -> TypeError).
        """
        entry = {
            "value":      value,
            "agent_id":   agent_id,
            "confidence": confidence,
            "ts":         time.time(),
        }
        with self._lock:
            self._store[key] = entry
        self._notify(key, value)
        self._save()
        log.debug(f"[BUS] {key} = {str(value)[:60]} (agent={agent_id or '?'})")

    def read(self, key: str, default: Any = None) -> Any:
        with self._lock:
            entry = self._store.get(key)
        if entry is None:
            return default
        return entry.get("value", default)

    def read_entry(self, key: str) -> Optional[dict]:
        """Retourne l'entree complete avec metadata."""
        with self._lock:
            return dict(self._store.get(key, {}))

    def delete(self, key: str):
        with self._lock:
            self._store.pop(key, None)
        self._save()

    def keys(self, prefix: str = "") -> list[str]:
        with self._lock:
            return [k for k in self._store if k.startswith(prefix)]

    def snapshot(self) -> dict:
        """Retourne une copie complete du bus."""
        with self._lock:
            return {k: dict(v) for k, v in self._store.items()}

    def dump(self) -> dict:
        """Alias pour api_server /context_bus."""
        return self.snapshot()

    def get_context_for(self, agent: str, prefixes: list[str] = None) -> dict:
        """
        Retourne les cles pertinentes pour un agent donne.
        Par defaut : toutes les cles sauf celles de l'agent lui-meme.
        """
        snap = self.snapshot()
        if prefixes:
            return {k: v["value"] for k, v in snap.items()
                    if any(k.startswith(p) for p in prefixes)}
        return {k: v["value"] for k, v in snap.items()
                if v.get("agent_id","") != agent}

    def get_attention_map(self) -> list[dict]:
        """Pour graph_ui : carte d'attention des agents."""
        snap = self.snapshot()
        agents = {}
        for entry in snap.values():
            aid = entry.get("agent_id","")
            if aid:
                agents[aid] = agents.get(aid, 0) + 1
        total = sum(agents.values()) or 1
        return [{"agent": a, "raw": n, "weight": round(n/total, 3)}
                for a, n in sorted(agents.items(), key=lambda x: -x[1])]

    def subscribe(self, key: str, callback):
        """Abonnement a un changement de cle (callback(key, value))."""
        with self._lock:
            self._subscribers.setdefault(key, []).append(callback)

    def _notify(self, key: str, value: Any):
        with self._lock:
            callbacks = list(self._subscribers.get(key, []))
        for cb in callbacks:
            try:
                cb(key, value)
            except Exception:
                pass

    def clear(self):
        with self._lock:
            self._store.clear()
        self._save()


_bus_instance: Optional[ContextBus] = None
_bus_lock = threading.Lock()


def get_bus() -> ContextBus:
    global _bus_instance
    if _bus_instance is None:
        with _bus_lock:
            if _bus_instance is None:
                _bus_instance = ContextBus()
    return _bus_instance


if __name__ == "__main__":
    import sys, io
    if hasattr(sys.stdout, "buffer"):
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    logging.basicConfig(level=logging.DEBUG)
    bus = get_bus()
    bus.write("test.hello", "world", agent_id="test", confidence=0.99)
    bus.write("sourcing.brief", "Dragon Ball trending", agent_id="sourcing")
    print(f"read test.hello : {bus.read('test.hello')}")
    print(f"keys sourcing.* : {bus.keys('sourcing.')}")
    print(f"snapshot size   : {len(bus.snapshot())}")
    print(f"attention map   : {bus.get_attention_map()}")
    print("context_bus OK")
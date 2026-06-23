"""
agents/context_bus.py — Context Bus OverLord
L'équivalent de la Context Window de Claude.

Tous mes processus internes partagent le même contexte à tout moment.
OverLord aura la même chose : un bus de contexte partagé, temps réel,
accessible en lecture/écriture par TOUS les agents simultanément.

Analogie directe :
  Claude      → Context Window (tokens, attention weights, KV cache)
  OverLord    → ContextBus (état JSON partagé, priorités, signaux)

Fonctionnement :
  - Chaque agent peut LIRE le contexte global à tout moment
  - Chaque agent peut ÉCRIRE ses découvertes dans le contexte
  - Le bus maintient une fenêtre glissante (comme ma context window)
  - Les informations vieillissent et sont déprioritisées (attention decay)
  - Les agents "savent" ce que les autres ont trouvé, en temps réel
"""

import json
import threading
import time
import hashlib
import math
from pathlib import Path
from datetime import datetime
from dataclasses import dataclass, field
from typing import Any, Optional
from enum import Enum

CONTEXT_DIR  = Path("workspace/context_bus")
CONTEXT_FILE = CONTEXT_DIR / "shared_context.json"


class ContextLayer(Enum):
    """Couches du contexte — inspiré des couches d'attention."""
    SENSORY     = "sensory"      # inputs bruts (sourcing, audio, images)
    SEMANTIC    = "semantic"     # compréhension (scénario, concepts)
    CREATIVE    = "creative"     # création (storyboard, prompts)
    PRODUCTION  = "production"   # génération (ComfyUI, 3D)
    FEEDBACK    = "feedback"     # retours (qualité, préférences humaines)
    MEMORY      = "memory"       # mémoire long terme
    SYSTEM      = "system"       # état système (GPU, erreurs, timing)


@dataclass
class ContextEntry:
    """Une entrée dans le bus de contexte."""
    id:          str
    layer:       ContextLayer
    agent:       str          # qui a écrit cette entrée
    key:         str          # clé sémantique
    value:       Any          # valeur (texte, dict, liste...)
    confidence:  float = 1.0  # 0-1, comme les attention weights
    timestamp:   float = field(default_factory=time.time)
    ttl_s:       float = 3600 # durée de vie en secondes (0 = permanent)
    reads:       int   = 0    # combien de fois lu (= signal d'importance)
    importance:  float = 0.5  # 0-1, calculé dynamiquement

    def is_alive(self) -> bool:
        if self.ttl_s <= 0:
            return True
        return (time.time() - self.timestamp) < self.ttl_s

    def attention_weight(self) -> float:
        """
        Calcule le poids d'attention de cette entrée.
        Inspiré du mécanisme d'attention de Transformer :
          - fraîcheur (récence)
          - confiance de la source
          - popularité (nb lectures)
          - importance déclarée
        """
        age_s     = time.time() - self.timestamp
        freshness = math.exp(-age_s / 3600)         # décroissance exponentielle
        popularity = math.log1p(self.reads) / 10     # log pour éviter l'explosion
        return min(1.0, (
            freshness   * 0.35 +
            self.confidence * 0.30 +
            popularity  * 0.15 +
            self.importance * 0.20
        ))

    def to_dict(self) -> dict:
        return {
            "id":         self.id,
            "layer":      self.layer.value,
            "agent":      self.agent,
            "key":        self.key,
            "value":      self.value if not isinstance(self.value, bytes) else str(self.value),
            "confidence": self.confidence,
            "timestamp":  self.timestamp,
            "ttl_s":      self.ttl_s,
            "reads":      self.reads,
            "importance": self.importance,
            "weight":     self.attention_weight(),
        }


class ContextBus:
    """
    Bus de contexte partagé — Context Window d'OverLord.

    Architecture inspirée de mon fonctionnement :

    [Agent Sourcing]  →  ┐
    [Agent Scénario]  →  ├→  [CONTEXT BUS]  ←→  [Tous les agents]
    [Agent Watchdog]  →  ┘        ↓
    [Human feedback]  →      Attention weights
                             Fenêtre glissante
                             Résolution conflits

    Usage :
        bus = ContextBus.get_instance()
        bus.write("sourcing", "trend_mood", "dark_fantasy", confidence=0.9)
        mood = bus.read("trend_mood")                # n'importe quel agent
        context = bus.get_context_for("storyboard")  # contexte pertinent filtré
    """

    _instance: Optional["ContextBus"] = None
    _lock_class = threading.Lock()

    def __init__(self):
        self._entries: dict[str, ContextEntry] = {}
        self._lock     = threading.RLock()
        self._listeners: list = []
        self._history: list[dict] = []
        self._window_size = 500   # nb max d'entrées actives (comme context tokens)
        CONTEXT_DIR.mkdir(parents=True, exist_ok=True)
        self._load()
        self._start_gc()

    @classmethod
    def get_instance(cls) -> "ContextBus":
        """Singleton — une seule instance pour tout le pipeline."""
        with cls._lock_class:
            if cls._instance is None:
                cls._instance = cls()
        return cls._instance

    # ── ÉCRITURE ─────────────────────────────────────────────────────

    def write(self, agent: str, key: str, value: Any,
              layer: ContextLayer = ContextLayer.SEMANTIC,
              confidence: float   = 1.0,
              ttl_s: float        = 3600,
              importance: float   = 0.5) -> str:
        """
        Écrit une information dans le bus de contexte.
        Accessible immédiatement par tous les autres agents.
        """
        entry_id = hashlib.md5(f"{agent}{key}{time.time()}".encode()).hexdigest()[:12]
        entry = ContextEntry(
            id=entry_id, layer=layer, agent=agent,
            key=key, value=value,
            confidence=confidence, ttl_s=ttl_s,
            importance=importance,
        )
        with self._lock:
            # Si clé existante du même agent → update
            for eid, e in list(self._entries.items()):
                if e.key == key and e.agent == agent:
                    del self._entries[eid]
                    break
            self._entries[entry_id] = entry
            self._history.append({
                "ts": time.time(), "agent": agent,
                "key": key, "action": "write",
            })
            self._enforce_window()

        self._emit("write", {"agent": agent, "key": key,
                              "layer": layer.value, "confidence": confidence})
        return entry_id

    def write_batch(self, agent: str, data: dict,
                    layer: ContextLayer = ContextLayer.SEMANTIC,
                    confidence: float   = 1.0) -> list[str]:
        """Écrit plusieurs clés d'un coup."""
        ids = []
        for key, value in data.items():
            ids.append(self.write(agent, key, value, layer, confidence))
        return ids

    # ── LECTURE ──────────────────────────────────────────────────────

    def read(self, key: str,
             default: Any = None,
             min_confidence: float = 0.0) -> Any:
        """
        Lit une valeur depuis le bus.
        Si plusieurs agents ont écrit la même clé → retourne celle
        avec le meilleur attention_weight (comme l'attention sélective).
        """
        with self._lock:
            candidates = [
                e for e in self._entries.values()
                if e.key == key
                and e.is_alive()
                and e.confidence >= min_confidence
            ]
            if not candidates:
                return default
            best = max(candidates, key=lambda e: e.attention_weight())
            best.reads += 1
            return best.value

    def read_with_meta(self, key: str) -> Optional[ContextEntry]:
        """Lit une entrée avec ses métadonnées complètes."""
        with self._lock:
            candidates = [e for e in self._entries.values()
                          if e.key == key and e.is_alive()]
            if not candidates:
                return None
            best = max(candidates, key=lambda e: e.attention_weight())
            best.reads += 1
            return best

    def read_by_layer(self, layer: ContextLayer,
                       n: int = 20) -> list[ContextEntry]:
        """Lit toutes les entrées d'une couche, triées par poids d'attention."""
        with self._lock:
            entries = [e for e in self._entries.values()
                       if e.layer == layer and e.is_alive()]
            return sorted(entries, key=lambda e: e.attention_weight(),
                          reverse=True)[:n]

    def read_by_agent(self, agent: str) -> list[ContextEntry]:
        """Tout ce qu'un agent a écrit."""
        with self._lock:
            return [e for e in self._entries.values()
                    if e.agent == agent and e.is_alive()]

    # ── CONTEXTE CIBLÉ ───────────────────────────────────────────────

    def get_context_for(self, agent_role: str,
                         n_top: int = 30) -> dict:
        """
        Retourne le contexte le plus pertinent pour un agent donné.
        Équivalent du "contexte fourni à une tête d'attention" :
        chaque agent reçoit une vue filtrée et priorisée du contexte global.
        """
        # Mapping rôle → couches pertinentes
        role_layers = {
            "sourcing":   [ContextLayer.SENSORY, ContextLayer.FEEDBACK, ContextLayer.MEMORY],
            "scenario":   [ContextLayer.SEMANTIC, ContextLayer.SENSORY, ContextLayer.CREATIVE],
            "storyboard": [ContextLayer.SEMANTIC, ContextLayer.CREATIVE, ContextLayer.FEEDBACK],
            "production": [ContextLayer.CREATIVE, ContextLayer.PRODUCTION, ContextLayer.SYSTEM],
            "postprod":   [ContextLayer.PRODUCTION, ContextLayer.CREATIVE, ContextLayer.FEEDBACK],
            "marketing":  [ContextLayer.FEEDBACK, ContextLayer.SEMANTIC, ContextLayer.PRODUCTION],
            "critic":     [ContextLayer.SEMANTIC, ContextLayer.PRODUCTION, ContextLayer.FEEDBACK],
            "watchdog":   [ContextLayer.SYSTEM, ContextLayer.PRODUCTION],
            "learning":   [ContextLayer.FEEDBACK, ContextLayer.MEMORY, ContextLayer.PRODUCTION],
        }
        relevant_layers = role_layers.get(
            agent_role,
            list(ContextLayer)  # si rôle inconnu → tout
        )

        with self._lock:
            all_relevant = [
                e for e in self._entries.values()
                if e.layer in relevant_layers and e.is_alive()
            ]
            top = sorted(all_relevant,
                         key=lambda e: e.attention_weight(),
                         reverse=True)[:n_top]
            for e in top:
                e.reads += 1

        return {
            "agent_role":    agent_role,
            "timestamp":     datetime.utcnow().isoformat(),
            "n_entries":     len(top),
            "entries":       {e.key: {
                "value":      e.value,
                "from":       e.agent,
                "layer":      e.layer.value,
                "confidence": e.confidence,
                "weight":     round(e.attention_weight(), 3),
            } for e in top},
        }

    # ── AGRÉGATION & CONSENSUS ────────────────────────────────────────

    def get_consensus(self, key: str) -> dict:
        """
        Retourne le consensus de tous les agents sur une clé.
        Pondéré par confidence × attention_weight.
        Équivalent du vote pondéré dans l'attention multi-tête.
        """
        with self._lock:
            entries = [e for e in self._entries.values()
                       if e.key == key and e.is_alive()]

        if not entries:
            return {"key": key, "consensus": None, "agreement": 0.0}

        # Si valeurs numériques → moyenne pondérée
        values = [e.value for e in entries]
        if all(isinstance(v, (int, float)) for v in values):
            weights   = [e.attention_weight() * e.confidence for e in entries]
            total_w   = sum(weights)
            if total_w > 0:
                weighted_mean = sum(v*w for v,w in zip(values,weights)) / total_w
                variance      = sum(w*(v-weighted_mean)**2
                                    for v,w in zip(values,weights)) / total_w
                agreement     = max(0, 1 - math.sqrt(variance) / (max(values)-min(values)+1e-9))
                return {
                    "key":        key,
                    "consensus":  round(weighted_mean, 4),
                    "agreement":  round(agreement, 3),
                    "n_sources":  len(entries),
                    "sources":    [e.agent for e in entries],
                }

        # Si valeurs textuelles → vote pondéré
        vote: dict[str, float] = {}
        for e in entries:
            v = str(e.value)
            vote[v] = vote.get(v, 0) + e.attention_weight() * e.confidence
        winner   = max(vote, key=vote.get)
        total    = sum(vote.values())
        agreement = vote[winner] / total if total > 0 else 0
        return {
            "key":        key,
            "consensus":  winner,
            "agreement":  round(agreement, 3),
            "n_sources":  len(entries),
            "votes":      {k: round(v/total, 3) for k,v in vote.items()},
        }

    # ── SNAPSHOT & ÉTAT ──────────────────────────────────────────────

    def snapshot(self) -> dict:
        """Snapshot complet du bus — équivalent d'un dump de context window."""
        with self._lock:
            alive = [e for e in self._entries.values() if e.is_alive()]
            by_layer = {}
            for e in alive:
                k = e.layer.value
                by_layer[k] = by_layer.get(k, 0) + 1

            top_weighted = sorted(alive, key=lambda e: e.attention_weight(),
                                   reverse=True)[:10]
        return {
            "timestamp":    datetime.utcnow().isoformat(),
            "total_entries":len(alive),
            "window_used":  f"{len(alive)}/{self._window_size}",
            "by_layer":     by_layer,
            "top_entries":  [e.to_dict() for e in top_weighted],
            "history_len":  len(self._history),
        }

    def get_attention_map(self) -> list[dict]:
        """Retourne la carte d'attention — quels agents influencent le plus le bus."""
        with self._lock:
            by_agent: dict[str, float] = {}
            for e in self._entries.values():
                if e.is_alive():
                    by_agent[e.agent] = by_agent.get(e.agent, 0.0) + e.attention_weight()

        total = sum(by_agent.values()) or 1
        return sorted([
            {"agent": a, "weight": round(w/total, 3), "raw": round(w, 3)}
            for a, w in by_agent.items()
        ], key=lambda x: -x["weight"])

    # ── GESTION DU BUS ───────────────────────────────────────────────

    def invalidate(self, key: str, agent: str = None):
        """Invalide une entrée (comme une invalidation de cache)."""
        with self._lock:
            to_del = [
                eid for eid, e in self._entries.items()
                if e.key == key and (agent is None or e.agent == agent)
            ]
            for eid in to_del:
                del self._entries[eid]

    def _enforce_window(self):
        """Maintient la fenêtre de contexte à _window_size entrées max."""
        if len(self._entries) > self._window_size:
            alive = [e for e in self._entries.values() if e.is_alive()]
            to_keep = sorted(alive, key=lambda e: e.attention_weight(),
                              reverse=True)[:self._window_size]
            keep_ids = {e.id for e in to_keep}
            self._entries = {k: v for k, v in self._entries.items()
                             if k in keep_ids}

    def _start_gc(self):
        """Garbage collector — supprime les entrées expirées toutes les 60s."""
        def _gc():
            while True:
                time.sleep(60)
                with self._lock:
                    expired = [eid for eid, e in self._entries.items()
                               if not e.is_alive()]
                    for eid in expired:
                        del self._entries[eid]
                self._save()
        t = threading.Thread(target=_gc, daemon=True)
        t.start()

    def add_listener(self, cb):
        self._listeners.append(cb)

    def _emit(self, event: str, data: dict):
        for cb in self._listeners:
            try: cb(event, data)
            except Exception: pass

    def _save(self):
        try:
            data = {k: v.to_dict() for k, v in self._entries.items()
                    if v.is_alive()}
            CONTEXT_FILE.write_text(
                json.dumps(data, indent=2, ensure_ascii=False, default=str),
                encoding="utf-8"
            )
        except Exception:
            pass

    def _load(self):
        if not CONTEXT_FILE.exists():
            return
        try:
            data = json.loads(CONTEXT_FILE.read_text(encoding="utf-8"))
            for eid, d in data.items():
                e = ContextEntry(
                    id=d["id"], layer=ContextLayer(d["layer"]),
                    agent=d["agent"], key=d["key"], value=d["value"],
                    confidence=d.get("confidence",1.0),
                    timestamp=d.get("timestamp",time.time()),
                    ttl_s=d.get("ttl_s",3600),
                    reads=d.get("reads",0),
                    importance=d.get("importance",0.5),
                )
                if e.is_alive():
                    self._entries[eid] = e
        except Exception:
            pass


# ── Mixin pour les agents ─────────────────────────────────────────────
class ContextAwareMixin:
    """
    Mixin à ajouter à tous les agents pour qu'ils aient accès au bus.

    Usage dans un agent existant :
        class MyAgent(ContextAwareMixin):
            def run(self):
                ctx = self.ctx_read("trend_mood")          # lire
                self.ctx_write("my_output", result)        # écrire
                context = self.ctx_get_for_me()            # contexte filtré
    """

    @property
    def _bus(self) -> ContextBus:
        return ContextBus.get_instance()

    @property
    def _agent_name(self) -> str:
        return getattr(self, "AGENT_NAME",
                       self.__class__.__name__.lower().replace("agent",""))

    def ctx_write(self, key: str, value: Any,
                  layer: ContextLayer = ContextLayer.SEMANTIC,
                  confidence: float   = 1.0,
                  ttl_s: float        = 3600,
                  importance: float   = 0.5) -> str:
        return self._bus.write(self._agent_name, key, value,
                                layer, confidence, ttl_s, importance)

    def ctx_read(self, key: str, default: Any = None,
                 min_confidence: float = 0.0) -> Any:
        return self._bus.read(key, default, min_confidence)

    def ctx_get_for_me(self) -> dict:
        return self._bus.get_context_for(self._agent_name)

    def ctx_consensus(self, key: str) -> dict:
        return self._bus.get_consensus(key)

    def ctx_write_batch(self, data: dict,
                         layer: ContextLayer = ContextLayer.SEMANTIC,
                         confidence: float   = 1.0):
        return self._bus.write_batch(self._agent_name, data, layer, confidence)


# ── Helper global ─────────────────────────────────────────────────────
def get_bus() -> ContextBus:
    return ContextBus.get_instance()


if __name__ == "__main__":
    bus = get_bus()

    # Simulation de plusieurs agents qui écrivent en parallèle
    import threading

    def sourcing_agent():
        bus.write("sourcing", "trend_mood",    "dark_epic",   ContextLayer.SENSORY,   confidence=0.9)
        bus.write("sourcing", "trend_genre",   "shonen",      ContextLayer.SENSORY,   confidence=0.85)
        bus.write("sourcing", "bpm_dominant",  142.0,         ContextLayer.SENSORY,   confidence=0.7)
        bus.write("sourcing", "top_hashtag",   "#DragonBall", ContextLayer.SENSORY,   confidence=0.95)

    def scenario_agent():
        time.sleep(0.1)  # attend un peu le sourcing
        mood = bus.read("trend_mood", default="neutral")
        bus.write("scenario", "narrative_tone", f"épique basé sur {mood}", ContextLayer.SEMANTIC, confidence=0.8)
        bus.write("scenario", "main_character", "guerrier solitaire",       ContextLayer.SEMANTIC, confidence=0.9)

    def storyboard_agent():
        time.sleep(0.2)
        tone = bus.read("narrative_tone", default="neutre")
        bus.write("storyboard", "shot_style",    f"cinématique, {tone}", ContextLayer.CREATIVE, confidence=0.85)
        bus.write("storyboard", "color_palette", "orange/noir/or",        ContextLayer.CREATIVE, confidence=0.8)

    threads = [
        threading.Thread(target=sourcing_agent),
        threading.Thread(target=scenario_agent),
        threading.Thread(target=storyboard_agent),
    ]
    for t in threads: t.start()
    for t in threads: t.join()

    time.sleep(0.3)  # laisser le temps d'écrire

    print("\n=== SNAPSHOT DU BUS DE CONTEXTE ===")
    snap = bus.snapshot()
    print(f"Entrées actives : {snap['total_entries']}/{snap['window_used']}")
    print(f"Par couche : {snap['by_layer']}")

    print("\n=== CARTE D'ATTENTION ===")
    for entry in bus.get_attention_map():
        bar = "█" * int(entry["weight"]*20)
        print(f"  {entry['agent']:<15} [{bar:<20}] {entry['weight']:.3f}")

    print("\n=== CONTEXTE POUR LE STORYBOARD ===")
    ctx = bus.get_context_for("storyboard")
    for key, data in ctx["entries"].items():
        print(f"  {key:<20} = {str(data['value']):<30} [weight={data['weight']}] (from {data['from']})")

    print("\n=== CONSENSUS SUR 'trend_mood' ===")
    print(bus.get_consensus("trend_mood"))

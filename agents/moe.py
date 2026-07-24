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
agents/moe.py -- Ov3rLoRd V1.20 -- Mixture of Experts
V1.49 : overlord_utils centralise, context_bus connecte.
MoE Router, Sparse Attention, RoPE Positional Encoding.
"""

import json
import math
import time
import logging
import threading
from pathlib import Path
from dataclasses import dataclass, field
from typing import Any, Callable, Optional

try:
    from agents.overlord_utils import fallback_llm, safe_json_parse
    UTILS_OK = True
except ImportError:
    UTILS_OK = False
    fallback_llm    = None
    safe_json_parse = None

try:
    from agents.context_bus import get_bus
    BUS_OK = True
except ImportError:
    BUS_OK = False

MOE_DIR      = Path("workspace/moe")
CLAUDE_MODEL = "claude-sonnet-4-6"


def _llm(prompt: str, system: str = "", max_tokens: int = 300) -> str:
    if UTILS_OK and fallback_llm:
        return fallback_llm(prompt, system=system, model=CLAUDE_MODEL,
                            max_tokens=max_tokens)
    return ""


# ── MoE Router ────────────────────────────────────────────────────────
@dataclass
class Expert:
    name:       str
    specialty:  list[str]
    fn:         Callable
    weight:     float = 1.0
    call_count: int   = 0
    avg_score:  float = 0.0


class MoERouter:
    """
    Mixture of Experts : router les inputs vers les experts les plus pertinents.
    Inspire de Switch Transformer et Mixtral.
    """

    def __init__(self, top_k: int = 2, logger: logging.Logger = None):
        self.log     = logger or logging.getLogger("moe_router")
        self.top_k   = top_k
        self._experts: dict[str, Expert] = {}
        self._lock   = threading.Lock()
        MOE_DIR.mkdir(parents=True, exist_ok=True)

    def register(self, name: str, fn: Callable, specialty: list[str],
                 weight: float = 1.0):
        with self._lock:
            self._experts[name] = Expert(name=name, specialty=specialty,
                                         fn=fn, weight=weight)
        self.log.info(f"[MOE] Expert enregistre : {name} ({specialty})")

    def route(self, task: str, context: dict = None) -> list[str]:
        """Selectionne les top_k experts les plus pertinents."""
        task_lower = task.lower()
        scores     = {}
        with self._lock:
            for name, expert in self._experts.items():
                match = sum(1 for s in expert.specialty if s in task_lower)
                scores[name] = match * expert.weight + expert.avg_score * 0.3
        sorted_experts = sorted(scores.items(), key=lambda x: x[1], reverse=True)
        selected       = [e[0] for e in sorted_experts[:self.top_k] if e[1] > 0]
        if not selected and self._experts:
            selected = [list(self._experts.keys())[0]]
        self.log.info(f"[MOE] Experts selectionnes pour '{task[:40]}' : {selected}")
        if BUS_OK:
            try:
                get_bus().write("moe.selected_experts", selected, agent_id="moe_router")
            except Exception:
                pass
        return selected

    def call(self, task: str, context: dict = None) -> dict:
        """Appelle les experts selectionnes et fusionne leurs resultats."""
        selected = self.route(task, context)
        results  = {}
        with self._lock:
            experts_to_call = {n: self._experts[n] for n in selected
                               if n in self._experts}
        for name, expert in experts_to_call.items():
            try:
                result             = expert.fn(task, context or {})
                results[name]      = result
                expert.call_count += 1
            except Exception as e:
                self.log.warning(f"[MOE] Expert {name} echec : {e}")
                results[name] = {"error": str(e)}

        merged = self._merge(results)
        if BUS_OK:
            try:
                get_bus().write("moe.last_task",   task[:80], agent_id="moe_router")
                get_bus().write("moe.experts_used", len(results), agent_id="moe_router")
            except Exception:
                pass
        return merged

    def _merge(self, results: dict) -> dict:
        if len(results) == 1:
            return list(results.values())[0]
        return {"merged": True, "results": results,
                "n_experts": len(results)}

    def update_score(self, expert_name: str, score: float):
        with self._lock:
            if expert_name in self._experts:
                exp = self._experts[expert_name]
                n   = exp.call_count or 1
                exp.avg_score = exp.avg_score * (n-1)/n + score/n

    def get_status(self) -> dict:
        with self._lock:
            return {
                name: {
                    "specialty":  e.specialty,
                    "weight":     e.weight,
                    "calls":      e.call_count,
                    "avg_score":  round(e.avg_score, 3),
                }
                for name, e in self._experts.items()
            }


# ── Sparse Attention ──────────────────────────────────────────────────
class SparseAttention:
    """
    Attention eparse : ne calcule l'attention que pour les K tokens les plus
    pertinents. Reduit O(n^2) en O(n*k).
    Applique a la selection de contexte dans le context_bus.
    """

    def __init__(self, top_k: int = 10, logger: logging.Logger = None):
        self.log   = logger or logging.getLogger("sparse_attention")
        self.top_k = top_k

    def select_relevant(self, query: str, context_items: dict,
                        threshold: float = 0.1) -> dict:
        """
        Selectionne les K elements de contexte les plus pertinents.
        Utilise un score TF-IDF simplifie.
        """
        query_words = set(query.lower().split())
        scores      = {}
        for key, value in context_items.items():
            val_str = str(value).lower()
            overlap = len(query_words & set(val_str.split()))
            scores[key] = overlap / max(len(query_words), 1)

        top = sorted(scores.items(), key=lambda x: x[1], reverse=True)
        selected = {k: context_items[k]
                    for k, s in top[:self.top_k] if s >= threshold}
        self.log.debug(f"[SPARSE] {len(context_items)} -> {len(selected)} items retenus")
        return selected

    def get_attention_weights(self, query: str, keys: list[str]) -> dict:
        """Calcule les poids d'attention entre query et une liste de cles."""
        query_words = set(query.lower().split())
        weights     = {}
        for key in keys:
            key_words    = set(key.lower().split("_"))
            overlap      = len(query_words & key_words)
            weights[key] = overlap / max(len(query_words), 1)
        total = sum(weights.values()) or 1
        return {k: round(v/total, 4) for k, v in weights.items()}


# ── RoPE Positional Encoding ──────────────────────────────────────────
class RoPEEncoder:
    """
    Rotary Position Embedding : encode la position des elements dans les sequences.
    Utilise pour encoder la position des shots dans un episode.
    Inspire de GPT-NeoX et LLaMA.
    """

    def __init__(self, dim: int = 64, max_seq: int = 1000):
        self.dim     = dim
        self.max_seq = max_seq
        self._cache  = {}

    def encode(self, position: int) -> list[float]:
        if position in self._cache:
            return self._cache[position]
        encoding = []
        for i in range(0, self.dim, 2):
            theta = position / (10000 ** (i / self.dim))
            encoding.extend([math.cos(theta), math.sin(theta)])
        encoding = encoding[:self.dim]
        self._cache[position] = encoding
        return encoding

    def encode_sequence(self, n: int) -> list[list[float]]:
        return [self.encode(i) for i in range(n)]

    def similarity(self, pos_a: int, pos_b: int) -> float:
        ea  = self.encode(pos_a)
        eb  = self.encode(pos_b)
        dot = sum(a*b for a,b in zip(ea,eb))
        na  = math.sqrt(sum(a**2 for a in ea))
        nb  = math.sqrt(sum(b**2 for b in eb))
        return dot / (na * nb) if na and nb else 0.0


# ── Facade MoEV120 ────────────────────────────────────────────────────
class MoEV120:

    def __init__(self, logger: logging.Logger = None):
        self.log      = logger or logging.getLogger("moe_v120")
        self.router   = MoERouter(top_k=2, logger=self.log)
        self.attention = SparseAttention(top_k=10, logger=self.log)
        self.rope     = RoPEEncoder(dim=32)

    def smart_route(self, task: str, context: dict = None) -> dict:
        sparse_ctx = {}
        if context and BUS_OK:
            try:
                bus_snap = {}
                bus      = get_bus()
                if hasattr(bus, "snapshot"):
                    bus_snap = {k: v.get("value") for k,v in bus.snapshot().items()}
                sparse_ctx = self.attention.select_relevant(task, bus_snap)
            except Exception:
                sparse_ctx = context or {}
        else:
            sparse_ctx = context or {}

        return self.router.call(task, sparse_ctx)

    def encode_shots(self, shots: list[dict]) -> list[dict]:
        encodings = self.rope.encode_sequence(len(shots))
        for i, (shot, enc) in enumerate(zip(shots, encodings)):
            shot["_rope_encoding"] = enc[:8]
            shot["_position"]      = i
        return shots

    def get_status(self) -> dict:
        s = {
            "router":   self.router.get_status(),
            "attention_top_k": self.attention.top_k,
            "rope_dim":        self.rope.dim,
        }
        if BUS_OK:
            try:
                get_bus().write("moe.router_experts",
                                len(self.router._experts), agent_id="moe_v120")
            except Exception:
                pass
        return s


if __name__ == "__main__":
    import sys, io
    if hasattr(sys.stdout, 'buffer'):
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
    logging.basicConfig(level=logging.INFO)
    moe = MoEV120()
    def expert_scenario(task, ctx):
        return {"type":"scenario","recommendation":f"Pour '{task[:30]}' : generer un scenario"}
    def expert_visual(task, ctx):
        return {"type":"visual","recommendation":f"Pour '{task[:30]}' : optimiser style"}
    moe.router.register("scenario_expert", expert_scenario, ["scenario","script","histoire"])
    moe.router.register("visual_expert",   expert_visual,   ["visuel","style","image"])
    result = moe.smart_route("scenario pour episode de combat visuel", {})
    print(f"Resultat MoE : {json.dumps(result, indent=2, ensure_ascii=False)}")
    shots  = [{"shot_id":f"S{i:02d}"} for i in range(5)]
    moe.encode_shots(shots)
    print(f"\nRoPE shot 0 vs 1 : similarity={moe.rope.similarity(0,1):.3f}")
    print(f"RoPE shot 0 vs 4 : similarity={moe.rope.similarity(0,4):.3f}")
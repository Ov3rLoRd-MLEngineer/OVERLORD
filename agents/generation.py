"""
agents/generation.py -- Ov3rLoRd V1.20 -- Generation Avancee
V1.49 : overlord_utils centralise, context_bus connecte.
Diffusion Scheduling, LoRA Composer, Style Consistency, Temporal Coherence,
Prompt Archaeology, Dynamic Resolution.
"""

import json
import math
import time
import hashlib
import logging
import threading
from pathlib import Path
from dataclasses import dataclass, field
from typing import Any, Optional

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

GEN_DIR      = Path("workspace/generation")
CLAUDE_MODEL = "claude-sonnet-4-6"


def _llm(prompt: str, system: str = "", max_tokens: int = 300) -> str:
    if UTILS_OK and fallback_llm:
        return fallback_llm(prompt, system=system, model=CLAUDE_MODEL,
                            max_tokens=max_tokens)
    return ""


def _parse(raw: str) -> dict | None:
    if not raw:
        return None
    if UTILS_OK and safe_json_parse:
        ok, data, _ = safe_json_parse(raw)
        return data if ok else None
    try:
        clean = raw.strip()
        if clean.startswith("```"):
            clean = "\n".join(clean.split("\n")[1:-1])
        return json.loads(clean)
    except Exception:
        return None


# ── Diffusion Scheduler ───────────────────────────────────────────────
class DiffusionScheduler:
    """Controle fin du scheduler selon le contenu."""

    CONTENT_PROFILES = {
        "action":    {"sampler":"dpm++_2m_sde","steps":30,"cfg":8.0,"denoise":0.85},
        "portrait":  {"sampler":"euler_a",      "steps":25,"cfg":6.5,"denoise":0.75},
        "landscape": {"sampler":"dpm++_2m",     "steps":28,"cfg":7.0,"denoise":0.80},
        "emotion":   {"sampler":"euler_a",      "steps":30,"cfg":7.5,"denoise":0.82},
        "vfx":       {"sampler":"dpm++_2m_sde","steps":35,"cfg":8.5,"denoise":0.90},
        "default":   {"sampler":"euler_a",      "steps":28,"cfg":7.0,"denoise":0.80},
    }

    def get_params(self, content_type: str, emotion: str = "",
                   quality_target: float = 0.8) -> dict:
        profile = self.CONTENT_PROFILES.get(content_type,
                                             self.CONTENT_PROFILES["default"]).copy()
        # Ajustement selon la qualite cible
        profile["steps"] = int(profile["steps"] * (0.7 + quality_target * 0.6))
        profile["steps"] = max(15, min(50, profile["steps"]))
        # Lire le style depuis le bus
        if BUS_OK:
            try:
                mood = get_bus().read("style.mood") or ""
                if "intense" in mood or "epic" in mood:
                    profile["cfg"]  = min(10.0, profile["cfg"] + 0.5)
                    profile["steps"] = min(50, profile["steps"] + 3)
            except Exception:
                pass
        if BUS_OK:
            try:
                get_bus().write("generation.scheduler_params",
                                profile, agent_id="diffusion_scheduler")
            except Exception:
                pass
        return profile


# ── LoRA Auto-Composer ────────────────────────────────────────────────
@dataclass
class LoRALayer:
    name:     str
    strength: float = 0.8
    trigger:  str   = ""


class LoRAComposer:
    """Compose automatiquement les LoRAs optimaux."""

    def __init__(self, logger: logging.Logger = None):
        self.log       = logger or logging.getLogger("lora_composer")
        self._registry: dict[str,dict] = {}
        self._path     = GEN_DIR / "lora_registry.json"
        self._load()

    def _load(self):
        if self._path.exists():
            try:
                self._registry = json.loads(self._path.read_text(encoding="utf-8"))
            except Exception:
                pass

    def _save(self):
        GEN_DIR.mkdir(parents=True, exist_ok=True)
        self._path.write_text(
            json.dumps(self._registry, ensure_ascii=False, indent=2), encoding="utf-8"
        )

    def register(self, name: str, tags: list[str], trigger: str = "",
                 base_strength: float = 0.8):
        self._registry[name] = {"tags":tags,"trigger":trigger,"strength":base_strength}
        self._save()

    def compose(self, style: str, characters: list[str] = None,
                max_loras: int = 3) -> list[LoRALayer]:
        candidates = []
        style_lower = style.lower()
        for name, info in self._registry.items():
            score = sum(1 for tag in info["tags"] if tag in style_lower)
            if characters:
                score += sum(2 for char in characters
                             if char.lower() in name.lower())
            if score > 0:
                candidates.append((score, name, info))

        candidates.sort(key=lambda x: x[0], reverse=True)
        layers = [
            LoRALayer(name=name, strength=info["strength"], trigger=info["trigger"])
            for _, name, info in candidates[:max_loras]
        ]
        if BUS_OK and layers:
            try:
                get_bus().write("generation.active_loras",
                                [l.name for l in layers], agent_id="lora_composer")
            except Exception:
                pass
        return layers

    def build_prompt_suffix(self, layers: list[LoRALayer]) -> str:
        parts = []
        for l in layers:
            if l.trigger:
                parts.append(l.trigger)
        return ", ".join(parts)


# ── Style Consistency Engine ──────────────────────────────────────────
class StyleConsistencyEngine:
    """Maintient la coherence stylistique entre toutes les images."""

    def __init__(self, series: str, logger: logging.Logger = None):
        self.log    = logger or logging.getLogger("style_consistency")
        self.series = series
        self._locked_elements: dict = {}
        self._path  = GEN_DIR / f"style_{hashlib.md5(series.encode()).hexdigest()[:8]}.json"
        self._load()

    def _load(self):
        if self._path.exists():
            try:
                self._locked_elements = json.loads(self._path.read_text(encoding="utf-8"))
            except Exception:
                pass

    def _save(self):
        GEN_DIR.mkdir(parents=True, exist_ok=True)
        self._path.write_text(
            json.dumps(self._locked_elements, ensure_ascii=False), encoding="utf-8"
        )

    def lock_element(self, key: str, value: str):
        self._locked_elements[key] = value
        self._save()

    def enforce(self, prompt: str) -> str:
        """Injecte les elements verrouilles dans le prompt."""
        additions = []
        for key, value in self._locked_elements.items():
            if value not in prompt:
                additions.append(value)
        if additions:
            prompt = ", ".join(additions) + ", " + prompt
        return prompt

    def get_locked(self) -> dict:
        return dict(self._locked_elements)


# ── Temporal Coherence ────────────────────────────────────────────────
class TemporalCoherence:
    """Maintient la coherence entre frames pour la video."""

    def __init__(self, window: int = 5, logger: logging.Logger = None):
        self.log     = logger or logging.getLogger("temporal")
        self.window  = window
        self._frames: list[dict] = []

    def add_frame(self, frame_metadata: dict):
        self._frames.append(frame_metadata)
        self._frames = self._frames[-self.window:]

    def get_consistency_prompt(self) -> str:
        if not self._frames:
            return ""
        last = self._frames[-1]
        elements = []
        for key in ["lighting","color_tone","character_position","background"]:
            if key in last:
                elements.append(f"{key}={last[key]}")
        return ", ".join(elements) if elements else ""

    def check_drift(self, new_frame: dict) -> float:
        if not self._frames:
            return 0.0
        last  = self._frames[-1]
        drift = sum(1 for k in new_frame if k in last and new_frame[k] != last[k])
        return drift / max(len(new_frame), 1)


# ── Prompt Archaeology ────────────────────────────────────────────────
class PromptArchaeologist:
    """Deconstruit les meilleurs prompts pour apprendre leurs patterns."""

    def __init__(self, logger: logging.Logger = None):
        self.log     = logger or logging.getLogger("archaeology")
        self._kb:    list[dict] = []
        self._path   = GEN_DIR / "prompt_archaeology.json"
        self._load()

    def _load(self):
        if self._path.exists():
            try:
                self._kb = json.loads(self._path.read_text(encoding="utf-8"))
            except Exception:
                pass

    def _save(self):
        GEN_DIR.mkdir(parents=True, exist_ok=True)
        self._path.write_text(json.dumps(self._kb, ensure_ascii=False), encoding="utf-8")

    def analyze(self, prompt: str, score: float) -> dict:
        prompt_data = (
            f"Analyse ce prompt SDXL (score={score:.0f}/100) :\n{prompt[:400]}\n\n"
            f"JSON : {{\"key_elements\":[],\"style_tags\":[],\"composition\":\"...\","
            f"\"what_works\":\"...\"}}"
        )
        raw  = _llm(prompt_data, max_tokens=300)
        data = _parse(raw)
        if data and score >= 80:
            entry = {**data, "prompt":prompt[:200], "score":score}
            self._kb.append(entry)
            self._kb = self._kb[-100:]
            self._save()
        return data or {}

    def get_best_elements(self, n: int = 5) -> list[str]:
        from collections import Counter
        elements = []
        for entry in self._kb:
            elements.extend(entry.get("key_elements",[]))
            elements.extend(entry.get("style_tags",[]))
        return [e for e,_ in Counter(elements).most_common(n)]


# ── Dynamic Resolution ────────────────────────────────────────────────
class DynamicResolution:
    """Adapte la resolution au contenu automatiquement."""

    PRESETS = {
        "portrait":  (896,  1152),
        "landscape": (1344, 768),
        "square":    (1024, 1024),
        "cinematic": (1344, 576),
        "manga":     (768,  1152),
    }

    def get(self, content_type: str, vram_gb: float = 8.0) -> tuple[int,int]:
        w, h = self.PRESETS.get(content_type, (1024, 1024))
        if vram_gb < 6:
            w, h = int(w*0.75), int(h*0.75)
        elif vram_gb > 12:
            w, h = int(w*1.25), int(h*1.25)
        w = (w // 64) * 64
        h = (h // 64) * 64
        return w, h


# ── Facade GenerationV120 ─────────────────────────────────────────────
class GenerationV120:

    def __init__(self, series: str = "Ov3rLoRd", logger: logging.Logger = None):
        self.log        = logger or logging.getLogger("generation_v120")
        self.scheduler  = DiffusionScheduler()
        self.lora       = LoRAComposer(logger=self.log)
        self.style      = StyleConsistencyEngine(series, logger=self.log)
        self.temporal   = TemporalCoherence(logger=self.log)
        self.archaeo    = PromptArchaeologist(logger=self.log)
        self.resolution = DynamicResolution()

    def optimize_shot(self, shot: dict, vram_gb: float = 8.0) -> dict:
        content_type = shot.get("shot_type","default").lower()
        if "CU" in content_type or "MCU" in content_type:
            res_type = "portrait"
        elif "ELS" in content_type or "VLS" in content_type:
            res_type = "landscape"
        else:
            res_type = "square"

        w, h    = self.resolution.get(res_type, vram_gb)
        params  = self.scheduler.get_params(
            shot.get("emotion","default").lower(),
            quality_target=0.85
        )
        loras   = self.lora.compose(
            shot.get("comfyui_positive",""),
            shot.get("characters",[])
        )
        prompt  = self.style.enforce(shot.get("comfyui_positive",""))
        consist = self.temporal.get_consistency_prompt()
        if consist:
            prompt = f"{consist}, {prompt}"

        shot.update({
            "comfyui_positive":     prompt,
            "comfyui_width":        w,
            "comfyui_height":       h,
            "comfyui_steps":        params["steps"],
            "comfyui_cfg":          params["cfg"],
            "comfyui_sampler":      params["sampler"],
            "comfyui_denoise":      params["denoise"],
            "_active_loras":        [{"name":l.name,"strength":l.strength} for l in loras],
            "_lora_suffix":         self.lora.build_prompt_suffix(loras),
        })

        if BUS_OK:
            try:
                bus = get_bus()
                bus.write("generation.resolution", f"{w}x{h}", agent_id="generation_v120")
                bus.write("generation.steps",      params["steps"], agent_id="generation_v120")
            except Exception:
                pass

        return shot

    def batch_optimize(self, shots: list[dict], vram_gb: float = 8.0) -> list[dict]:
        return [self.optimize_shot(s, vram_gb) for s in shots]

    def record_result(self, prompt: str, score: float, frame_meta: dict = None):
        self.archaeo.analyze(prompt, score)
        if frame_meta:
            self.temporal.add_frame(frame_meta)


if __name__ == "__main__":
    import sys, io
    if hasattr(sys.stdout, 'buffer'):
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
    logging.basicConfig(level=logging.INFO)
    gen = GenerationV120("Dragon Ball Ov3rLoRd")
    gen.lora.register("goku_v2", ["goku","saiyan","hero"], trigger="goku outfit")
    shot = {
        "shot_id":          "S01_SH001",
        "shot_type":        "MCU",
        "emotion":          "action",
        "characters":       ["Goku"],
        "comfyui_positive": "1male, muscular, spiky hair, orange gi, battle stance",
    }
    optimized = gen.optimize_shot(shot, vram_gb=8.0)
    print(f"Resolution  : {optimized['comfyui_width']}x{optimized['comfyui_height']}")
    print(f"Steps       : {optimized['comfyui_steps']}")
    print(f"LoRAs actifs: {optimized['_active_loras']}")
    print(f"Best elements: {gen.archaeo.get_best_elements()}")
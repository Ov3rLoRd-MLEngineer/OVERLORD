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
agents/asset_library.py — Bibliotheque d'Assets Ov3rLoRd V1.46 + Context Bus V1.49
Publie le resume de la bibliotheque sur le bus apres chaque ajout.
"""

import json
import hashlib
import logging
from pathlib import Path
from datetime import datetime
from typing import Optional

try:
    from agents.overlord_utils import fallback_llm, safe_json_parse
    UTILS_OK = True
except ImportError:
    UTILS_OK = False

try:
    from agents.context_bus import get_bus
    BUS_OK = True
except ImportError:
    BUS_OK = False

log = logging.getLogger("asset_library")
LIBRARY_DIR = Path("workspace/asset_library")


class Asset:
    def __init__(self, asset_id: str, name: str, category: str, data: dict):
        self.id       = asset_id
        self.name     = name
        self.category = category
        self.data     = data

    def to_dict(self) -> dict:
        return {"id":self.id,"name":self.name,"category":self.category,"data":self.data}


class AssetLibrary:

    def __init__(self, series: str, logger: logging.Logger = None):
        self.log    = logger or log
        self.series = series
        self.lib_id = hashlib.md5(series.encode()).hexdigest()[:8]
        self.path   = LIBRARY_DIR / f"{self.lib_id}.json"
        LIBRARY_DIR.mkdir(parents=True, exist_ok=True)
        self._data  = self._load()

    def _load(self) -> dict:
        if self.path.exists():
            try:
                return json.loads(self.path.read_text(encoding="utf-8"))
            except Exception:
                pass
        return {"series": self.series, "assets": {}, "usage_log": []}

    def _save(self):
        self.path.write_text(
            json.dumps(self._data, ensure_ascii=False, indent=2, default=str),
            encoding="utf-8"
        )

    def _publish(self):
        """Publie le resume de la bibliotheque sur le bus."""
        if not BUS_OK:
            return
        try:
            s   = self.summary()
            bus = get_bus()
            bus.write("asset_library.total",      s["total"],                  agent_id="asset_library")
            bus.write("asset_library.characters",
                      [a["name"] for a in self.list_assets("character")],      agent_id="asset_library")
            bus.write("asset_library.locations",
                      [a["name"] for a in self.list_assets("location")],       agent_id="asset_library")
        except Exception:
            pass

    def add_character(self, name: str, positive_prompt: str,
                      negative_prompt: str = "", lora: str = "",
                      lora_strength: float = 0.8,
                      reference_images: list = None,
                      traits: dict = None) -> str:
        asset_id = f"char_{hashlib.md5(name.encode()).hexdigest()[:6]}"
        self._data["assets"][asset_id] = {
            "id":asset_id,"name":name,"category":"character",
            "data":{
                "positive_prompt":  positive_prompt,
                "negative_prompt":  negative_prompt or "bad anatomy, wrong proportions",
                "lora":             lora,
                "lora_strength":    lora_strength,
                "reference_images": reference_images or [],
                "traits":           traits or {},
                "created_at":       datetime.now().isoformat(),
                "version":          1,
            }
        }
        self._save()
        self._publish()
        self.log.info(f"[LIBRARY] Personnage ajoute : {name} ({asset_id})")
        return asset_id

    def add_location(self, name: str, positive_prompt: str,
                     time_variants: dict = None,
                     weather_variants: dict = None) -> str:
        asset_id = f"loc_{hashlib.md5(name.encode()).hexdigest()[:6]}"
        self._data["assets"][asset_id] = {
            "id":asset_id,"name":name,"category":"location",
            "data":{
                "positive_prompt":  positive_prompt,
                "time_variants":    time_variants or {"day": positive_prompt},
                "weather_variants": weather_variants or {},
                "created_at":       datetime.now().isoformat(),
            }
        }
        self._save()
        self._publish()
        self.log.info(f"[LIBRARY] Decor ajoute : {name}")
        return asset_id

    def add_effect(self, name: str, positive_prompt: str,
                   category: str = "effect") -> str:
        asset_id = f"{category[:3]}_{hashlib.md5(name.encode()).hexdigest()[:6]}"
        self._data["assets"][asset_id] = {
            "id":asset_id,"name":name,"category":category,
            "data":{"positive_prompt":positive_prompt,"created_at":datetime.now().isoformat()}
        }
        self._save()
        return asset_id

    def get_character_prompt(self, name: str, scene_context: str = "",
                              time_of_day: str = "day") -> dict:
        asset = self._find_asset(name, "character")
        if not asset:
            self.log.warning(f"[LIBRARY] Personnage '{name}' introuvable")
            return {"positive":name,"negative":"","lora":""}
        data  = asset["data"]
        parts = [data["positive_prompt"]]
        if scene_context:
            parts.append(scene_context)
        self._log_usage(asset["id"], "character", name)
        return {
            "positive":      ", ".join(parts),
            "negative":      data.get("negative_prompt",""),
            "lora":          data.get("lora",""),
            "lora_strength": data.get("lora_strength",0.8),
            "asset_id":      asset["id"],
        }

    def get_location_prompt(self, name: str, time_of_day: str = "day",
                            weather: str = "") -> dict:
        asset = self._find_asset(name, "location")
        if not asset:
            return {"positive":name,"negative":""}
        data     = asset["data"]
        variants = data.get("time_variants",{})
        base     = variants.get(time_of_day, data.get("positive_prompt",name))
        weather_variants = data.get("weather_variants",{})
        if weather and weather in weather_variants:
            base = f"{base}, {weather_variants[weather]}"
        self._log_usage(asset["id"],"location",name)
        return {"positive":base,"negative":"","asset_id":asset["id"]}

    def compose_scene_prompt(self, characters: list, location: str,
                             time_of_day: str = "day", action: str = "",
                             style_prompt: str = "") -> dict:
        parts     = []
        loras     = []
        negatives = []
        for char_name in characters:
            cp = self.get_character_prompt(char_name, time_of_day=time_of_day)
            parts.append(cp["positive"])
            if cp.get("lora"):
                loras.append({"name":cp["lora"],"strength":cp.get("lora_strength",0.8)})
            if cp.get("negative"):
                negatives.append(cp["negative"])
        if location:
            lp = self.get_location_prompt(location, time_of_day=time_of_day)
            parts.append(lp["positive"])
        if action:      parts.append(action)
        if style_prompt:parts.append(style_prompt)
        return {
            "positive": ", ".join(p for p in parts if p),
            "negative": ", ".join(set(n for n in negatives if n)) or "bad quality, blurry, deformed",
            "loras":    loras,
        }

    def _find_asset(self, name: str, category: str = None) -> Optional[dict]:
        for asset in self._data["assets"].values():
            if asset["name"].lower() == name.lower():
                if category is None or asset["category"] == category:
                    return asset
        return None

    def _log_usage(self, asset_id: str, category: str, name: str):
        self._data["usage_log"].append({
            "asset_id":asset_id,"category":category,
            "name":name,"used_at":datetime.now().isoformat()
        })
        self._data["usage_log"] = self._data["usage_log"][-200:]
        self._save()

    def generate_character_prompt(self, name: str, description: str,
                                   style: str = "anime SDXL") -> str:
        if not UTILS_OK:
            return f"1character, {description}, {style}, high quality"
        prompt = (
            f"Genere un prompt ComfyUI SDXL pour ce personnage.\n"
            f"Nom : {name}\nDescription : {description}\nStyle : {style}\n"
            f"Retourne UNIQUEMENT le prompt positif, en anglais, sans explication."
        )
        result = fallback_llm(prompt, max_tokens=200, logger=self.log)
        return result.strip() if result else f"1character, {description}, {style}"

    def list_assets(self, category: str = None) -> list:
        assets = list(self._data["assets"].values())
        if category:
            assets = [a for a in assets if a["category"] == category]
        return assets

    def get_most_used(self, n: int = 5) -> list:
        from collections import Counter
        names = [u["name"] for u in self._data.get("usage_log",[])]
        return Counter(names).most_common(n)

    def export_for_storyboard(self) -> dict:
        chars = {a["name"]:a["data"] for a in self.list_assets("character")}
        locs  = {a["name"]:a["data"] for a in self.list_assets("location")}
        return {"characters":chars,"locations":locs,
                "series":self.series,"asset_count":len(self._data["assets"])}

    def summary(self) -> dict:
        by_cat = {}
        for a in self._data["assets"].values():
            c = a["category"]
            by_cat[c] = by_cat.get(c,0) + 1
        return {"series":self.series,"total":len(self._data["assets"]),
                "by_category":by_cat,"usage_logs":len(self._data.get("usage_log",[]))}


if __name__ == "__main__":
    import sys, io
    if hasattr(sys.stdout,'buffer'):
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
    logging.basicConfig(level=logging.INFO)
    lib = AssetLibrary("Dragon Ball Ov3rLoRd")
    lib.add_character("Goku",
        positive_prompt="1male, muscular, spiky black hair, orange gi, determined expression",
        lora="goku_sdxl_v2.safetensors",
        traits={"power_level":"Ultra Instinct","alignment":"hero"})
    lib.add_location("Plaine desertique",
        positive_prompt="vast desert plain, red earth, dramatic sky",
        time_variants={
            "day":   "vast desert plain, harsh sunlight, heat haze",
            "night": "vast desert plain, star filled sky, moonlight",
            "dusk":  "vast desert plain, orange sunset, dramatic clouds",
        })
    scene = lib.compose_scene_prompt(
        characters=["Goku"], location="Plaine desertique",
        time_of_day="dusk", action="epic battle, dynamic pose",
        style_prompt="anime cel shading, Toriyama style"
    )
    print(json.dumps(scene, indent=2, ensure_ascii=False))
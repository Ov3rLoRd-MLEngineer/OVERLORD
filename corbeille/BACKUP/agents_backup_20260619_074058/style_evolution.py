"""
agents/style_evolution.py — Évolution Stylistique entre Arcs V1.47
Fait évoluer le style visuel de façon cohérente entre les arcs narratifs.
Arc 1 → Arc 2 → Arc 3 : progression de couleurs, d'ambiance, de densité visuelle.

Usage :
    from agents.style_evolution import StyleEvolution
    evo = StyleEvolution("Dragon Ball Ov3rLoRd")
    style = evo.get_style_for_arc(arc=2, episode=8)
"""

import json
import logging
import math
from pathlib import Path
from datetime import datetime

try:
    from agents.overlord_utils import fallback_llm, safe_json_parse
    UTILS_OK = True
except ImportError:
    UTILS_OK = False

try:
    from agents.style_dna import StyleDNA
    DNA_OK = True
except ImportError:
    DNA_OK = False

log = logging.getLogger("style_evolution")
EVO_DIR = Path("workspace/style_evolution")

# Templates d'évolution narrative → stylistique
ARC_TEMPLATES = {
    "shonen_classic": {
        "arc_1": {"name":"Origine",    "palette":["blue","orange","white"],       "mood":"hopeful, bright, energetic",         "cfg":7.0, "steps":20},
        "arc_2": {"name":"Épreuves",   "palette":["red","dark orange","grey"],    "mood":"intense, dramatic, determined",      "cfg":7.5, "steps":22},
        "arc_3": {"name":"Apothéose",  "palette":["gold","white","deep red"],     "mood":"epic, transcendent, overwhelming",   "cfg":8.0, "steps":25},
        "arc_4": {"name":"Résolution", "palette":["warm orange","green","blue"],  "mood":"peaceful, victorious, emotional",    "cfg":7.0, "steps":20},
    },
    "dark_fantasy": {
        "arc_1": {"name":"Ordinary",   "palette":["grey","brown","muted green"], "mood":"grounded, realistic, subtle",       "cfg":6.5, "steps":20},
        "arc_2": {"name":"Descent",    "palette":["dark purple","black","red"],   "mood":"ominous, corrupted, hopeless",       "cfg":7.5, "steps":24},
        "arc_3": {"name":"Abyss",      "palette":["near black","crimson","void"], "mood":"apocalyptic, cosmic horror, chaos",  "cfg":8.5, "steps":28},
        "arc_4": {"name":"Redemption", "palette":["golden","white","silver"],     "mood":"bittersweet, transcendent, final",   "cfg":7.0, "steps":22},
    },
    "cyberpunk": {
        "arc_1": {"name":"Street",     "palette":["cyan","purple","grey"],        "mood":"gritty, neon, underground",          "cfg":7.0, "steps":20},
        "arc_2": {"name":"Corporate",  "palette":["blue","white","chrome"],       "mood":"cold, clinical, oppressive",         "cfg":7.5, "steps":22},
        "arc_3": {"name":"Revolution", "palette":["red","orange","gold"],         "mood":"explosive, chaotic, electric",       "cfg":8.0, "steps":25},
        "arc_4": {"name":"New Dawn",   "palette":["pink","purple","sunrise"],     "mood":"hopeful, digital, reborn",           "cfg":7.0, "steps":20},
    },
}


class ColorInterpolator:
    """Interpole les couleurs entre deux arcs pour les épisodes de transition."""

    def lerp_palettes(self, palette_a: list, palette_b: list,
                      t: float) -> list:
        """Interpole linéairement entre deux palettes (t=0→A, t=1→B)."""
        result = []
        for i in range(min(len(palette_a), len(palette_b))):
            if t < 0.3:
                result.append(palette_a[i])
            elif t > 0.7:
                result.append(palette_b[i])
            else:
                # Zone de transition — mélanger les deux
                result.append(f"blend of {palette_a[i]} and {palette_b[i]}")
        return result

    def lerp_cfg(self, cfg_a: float, cfg_b: float, t: float) -> float:
        return round(cfg_a + (cfg_b - cfg_a) * t, 1)

    def lerp_steps(self, steps_a: int, steps_b: int, t: float) -> int:
        return int(steps_a + (steps_b - steps_a) * t)


class StyleEvolution:
    """Gère l'évolution cohérente du style visuel sur toute une série."""

    def __init__(self, series: str, genre: str = "shonen_classic",
                 logger: logging.Logger = None):
        self.log       = logger or log
        self.series    = series
        self.genre     = genre
        self.template  = ARC_TEMPLATES.get(genre, ARC_TEMPLATES["shonen_classic"])
        self.interp    = ColorInterpolator()
        EVO_DIR.mkdir(parents=True, exist_ok=True)
        self.evo_path  = EVO_DIR / f"{series.replace(' ','_')}_evolution.json"
        self._data     = self._load()

    def _load(self) -> dict:
        if self.evo_path.exists():
            try:
                return json.loads(self.evo_path.read_text(encoding="utf-8"))
            except Exception:
                pass
        return {
            "series": self.series, "genre": self.genre,
            "arcs": {}, "episode_styles": {},
        }

    def _save(self):
        self.evo_path.write_text(
            json.dumps(self._data, indent=2, ensure_ascii=False), encoding="utf-8"
        )

    def define_arc(self, arc: int, title: str, episodes: list,
                   custom_style: dict = None):
        """Définit un arc narratif avec sa plage d'épisodes et son style."""
        base_style = self.template.get(f"arc_{arc}", self.template.get("arc_1", {}))
        style = {**base_style, **(custom_style or {}), "title": title, "episodes": episodes}
        self._data["arcs"][str(arc)] = style
        self._save()
        self.log.info(f"[EVOLUTION] Arc {arc} '{title}' défini ({len(episodes)} épisodes)")

    def get_style_for_episode(self, episode: int) -> dict:
        """
        Retourne le style exact pour un épisode donné.
        Gère les transitions progressives entre arcs.
        """
        # Trouver l'arc de cet épisode
        current_arc  = None
        next_arc     = None
        arc_position = 0.0

        arcs = {int(k): v for k,v in self._data["arcs"].items()}

        for arc_num in sorted(arcs.keys()):
            arc_data = arcs[arc_num]
            episodes = arc_data.get("episodes", [])
            if episode in episodes:
                current_arc   = arc_data
                arc_position  = episodes.index(episode) / max(len(episodes)-1, 1)
                # Chercher l'arc suivant
                next_arc_num  = arc_num + 1
                if next_arc_num in arcs:
                    next_arc  = arcs[next_arc_num]
                break

        if not current_arc:
            # Épisode non trouvé — utiliser arc 1 par défaut
            current_arc = list(arcs.values())[0] if arcs else self.template["arc_1"]
            arc_position = 0.0

        # Interpolation en fin d'arc
        transition_start = 0.8  # Commence la transition à 80% de l'arc
        if next_arc and arc_position >= transition_start:
            t = (arc_position - transition_start) / (1 - transition_start)
            palette = self.interp.lerp_palettes(
                current_arc.get("palette", []),
                next_arc.get("palette", []), t
            )
            cfg   = self.interp.lerp_cfg(current_arc.get("cfg",7.0), next_arc.get("cfg",7.0), t)
            steps = self.interp.lerp_steps(current_arc.get("steps",20), next_arc.get("steps",20), t)
            mood  = f"{current_arc.get('mood','')} transitioning to {next_arc.get('mood','')}"
        else:
            palette = current_arc.get("palette", [])
            cfg     = current_arc.get("cfg", 7.0)
            steps   = current_arc.get("steps", 20)
            mood    = current_arc.get("mood", "")

        style = {
            "episode":      episode,
            "arc":          current_arc.get("name", ""),
            "palette":      palette,
            "mood":         mood,
            "cfg_scale":    cfg,
            "steps":        steps,
            "arc_position": round(arc_position, 2),
            "in_transition":arc_position >= transition_start and next_arc is not None,
            "style_prompt": self._build_style_prompt(palette, mood),
        }

        # Mettre à jour le style DNA si disponible
        if DNA_OK:
            try:
                dna = StyleDNA(self.series)
                dna.lock(
                    palette=palette,
                    style_prompt=style["style_prompt"],
                    cfg_scale=cfg, steps=steps,
                )
            except Exception:
                pass

        self._data["episode_styles"][str(episode)] = style
        self._save()
        return style

    def _build_style_prompt(self, palette: list, mood: str) -> str:
        """Construit le suffix de style à ajouter aux prompts."""
        parts = []
        if palette:
            parts.append(f"color palette: {', '.join(palette[:3])}")
        if mood:
            parts.append(mood)
        parts.append("cinematic composition, professional anime production")
        return ", ".join(parts)

    def generate_arc_structure(self, total_episodes: int,
                               n_arcs: int = 3) -> dict:
        """Génère automatiquement une structure d'arcs via LLM."""
        if not UTILS_OK:
            eps_per_arc = total_episodes // n_arcs
            for i in range(1, n_arcs+1):
                start = (i-1)*eps_per_arc + 1
                end   = i*eps_per_arc if i < n_arcs else total_episodes
                self.define_arc(i, f"Arc {i}", list(range(start, end+1)))
            return self._data["arcs"]

        prompt = (
            f"Série : {self.series} | Genre : {self.genre} | {total_episodes} épisodes | {n_arcs} arcs\n"
            f"Génère la structure narrative et stylistique. JSON uniquement :\n"
            + '{"arcs":[{"arc":1,"title":"","episodes":[1,2,3],"mood":"","palette":["","",""]}]}'
        )
        raw = fallback_llm(prompt, max_tokens=500, logger=self.log)
        ok, data, _ = safe_json_parse(raw, logger=self.log)
        if ok and data:
            for arc_data in data.get("arcs", []):
                self.define_arc(
                    arc_data["arc"], arc_data.get("title",""),
                    arc_data.get("episodes",[]),
                    {"mood": arc_data.get("mood",""), "palette": arc_data.get("palette",[])}
                )
        return self._data["arcs"]

    def get_series_overview(self) -> dict:
        return {
            "series":   self.series,
            "genre":    self.genre,
            "arcs":     len(self._data["arcs"]),
            "episodes_styled": len(self._data["episode_styles"]),
            "arc_list": [{"arc":k, "title":v.get("name",""), "n_eps":len(v.get("episodes",[]))}
                         for k,v in self._data["arcs"].items()],
        }


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    evo = StyleEvolution("Dragon Ball Ov3rLoRd", "shonen_classic")
    evo.define_arc(1, "L'Éveil", list(range(1, 7)))
    evo.define_arc(2, "L'Épreuve", list(range(7, 14)))
    evo.define_arc(3, "L'Apothéose", list(range(14, 20)))

    for ep in [1, 5, 6, 7, 13, 14, 19]:
        style = evo.get_style_for_episode(ep)
        trans = " [TRANSITION]" if style["in_transition"] else ""
        print(f"  Ep.{ep:02d} — {style['arc']:<15} palette={style['palette'][:2]} cfg={style['cfg_scale']}{trans}")

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
agents/narrative_dna.py — OverLord V1.30 — Narrative DNA

Encoder l'ADN narratif d'une oeuvre et le croiser avec d'autres.

Concept :
  Chaque oeuvre créative a un "ADN" unique — un vecteur de caractéristiques
  qui encode son rythme, son mood, ses codes visuels, sa structure narrative,
  ses archétypes de personnages, ses thèmes.

  Dragon Ball  → [énergie=0.95, combat=0.9, amitié=0.8, humour=0.6, drame=0.4]
  Your Name    → [mélancolie=0.9, romance=0.9, beauté=0.95, mystère=0.8, action=0.1]
  Attack on Titan → [drame=0.95, horreur=0.8, politique=0.7, sacrifice=0.9, action=0.8]

  Croiser Dragon Ball × Your Name → énergie épique + beauté visuelle + mélancolie
  = quelque chose d'entièrement nouveau qui n'existe nulle part.

Composants :
  - DNAEncoder      : extrait l'ADN d'une oeuvre depuis sa description
  - DNACrosser      : croise plusieurs ADN avec pondération
  - DNALibrary      : bibliothèque d'ADN d'oeuvres connues
  - DNATranslator   : traduit un ADN croisé en paramètres de production
  - StyleFingerprint: identifie le style d'un artiste depuis ses oeuvres
"""

import json
import math
import time
import logging
from pathlib import Path
from dataclasses import dataclass, field
from typing import Optional
import requests

DNA_DIR       = Path("workspace/narrative_dna")
ANTHROPIC_URL = "https://api.anthropic.com/v1/messages"
CLAUDE_MODEL  = "claude-sonnet-4-6"


def _llm(prompt: str, system: str = "", max_tokens: int = 600) -> str:
    try:
        body = {"model": CLAUDE_MODEL, "max_tokens": max_tokens,
                "messages": [{"role": "user", "content": prompt}]}
        if system:
            body["system"] = system
        r = requests.post(ANTHROPIC_URL,
                          headers={"Content-Type": "application/json"},
                          json=body, timeout=25)
        if r.status_code == 200:
            return r.json()["content"][0]["text"].strip()
    except Exception:
        pass
    return ""


# ══════════════════════════════════════════════════════════════════════
# DIMENSIONS DE L'ADN NARRATIF
# ══════════════════════════════════════════════════════════════════════

DNA_DIMENSIONS = {
    # Énergie & Rythme
    "energy":       "Niveau d'énergie général (0=contemplatif, 1=explosif)",
    "pacing":       "Rythme narratif (0=lent/méditatif, 1=frénétique)",
    "tension":      "Tension dramatique (0=détendu, 1=haletant)",
    # Émotions dominantes
    "melancholy":   "Mélancolie (0=absent, 1=omniprésent)",
    "joy":          "Joie et légèreté",
    "dread":        "Peur/angoisse",
    "hope":         "Espoir et rédemption",
    "epic":         "Grandiosité épique",
    # Thèmes narratifs
    "friendship":   "Amitié et liens entre personnages",
    "sacrifice":    "Sacrifice et perte",
    "romance":      "Romance et amour",
    "politics":     "Enjeux politiques/sociaux",
    "philosophy":   "Profondeur philosophique",
    "comedy":       "Humour et légèreté",
    # Style visuel
    "visual_beauty":"Beauté visuelle pure (soin des détails)",
    "darkness":     "Esthétique sombre et contraste fort",
    "color_vibrancy":"Saturation et vibrance des couleurs",
    "detail_level": "Niveau de détail visuel",
    # Archétypes
    "hero_journey": "Arc héroïque classique",
    "anti_hero":    "Protagoniste moralement ambigu",
    "ensemble":     "Ensemble cast vs héros solo",
    "mystery":      "Mystère et révélations",
    # Combat & Action
    "action":       "Scènes d'action et combat",
    "power_system": "Système de pouvoirs/magie codifié",
    # Univers
    "world_building":"Richesse de la construction du monde",
    "realism":      "Ancrage dans la réalité (0=fantaisie pure, 1=réaliste)",
}


@dataclass
class NarrativeDNA:
    """L'ADN narratif d'une oeuvre — vecteur de 28 dimensions."""
    work_id:    str
    title:      str
    medium:     str        # "anime","manga","film","serie","jeu"
    dimensions: dict[str, float] = field(default_factory=dict)
    tags:       list[str]  = field(default_factory=list)
    description:str = ""
    created_at: float = field(default_factory=time.time)

    def __post_init__(self):
        # Initialiser toutes les dimensions à 0.5 par défaut
        for dim in DNA_DIMENSIONS:
            if dim not in self.dimensions:
                self.dimensions[dim] = 0.5

    def distance(self, other: "NarrativeDNA") -> float:
        """Distance euclidienne entre deux ADN (similarité)."""
        dims = list(DNA_DIMENSIONS.keys())
        diff = sum((self.dimensions.get(d,0.5) - other.dimensions.get(d,0.5))**2
                   for d in dims)
        return math.sqrt(diff / len(dims))

    def similarity(self, other: "NarrativeDNA") -> float:
        """Score de similarité 0-1 (1=identiques)."""
        max_dist = math.sqrt(len(DNA_DIMENSIONS))
        return max(0.0, 1.0 - self.distance(other) / max_dist)

    def dominant_traits(self, top_n: int = 5) -> list[tuple]:
        """Retourne les N traits les plus marqués."""
        sorted_dims = sorted(self.dimensions.items(),
                             key=lambda x: abs(x[1] - 0.5), reverse=True)
        return sorted_dims[:top_n]

    def to_dict(self) -> dict:
        return {
            "work_id":    self.work_id,
            "title":      self.title,
            "medium":     self.medium,
            "dimensions": self.dimensions,
            "tags":       self.tags,
            "description":self.description,
            "created_at": self.created_at,
        }


# ══════════════════════════════════════════════════════════════════════
# ENCODEUR D'ADN
# ══════════════════════════════════════════════════════════════════════

class DNAEncoder:
    """
    Extrait l'ADN d'une oeuvre depuis sa description.
    Utilise le LLM pour quantifier chaque dimension.
    """

    SYSTEM = (
        "Tu es un analyste expert en narratologie et esthétique anime/manga/film. "
        "Tu quantifies les caractéristiques d'une oeuvre avec précision et nuance. "
        "Tu connais en détail : Dragon Ball, One Piece, Naruto, Attack on Titan, "
        "Your Name, Demon Slayer, Fullmetal Alchemist, Evangelion, Cowboy Bebop, "
        "et des centaines d'autres oeuvres de référence."
    )

    def encode(self, title: str, description: str,
               medium: str = "anime") -> NarrativeDNA:
        """Encode une oeuvre en ADN narratif."""
        dims_desc = "\n".join(
            f'  "{k}": {v}' for k, v in DNA_DIMENSIONS.items()
        )
        prompt = (
            f"Analyse cette oeuvre et quantifie chaque dimension de 0.0 à 1.0 :\n\n"
            f"Titre  : {title}\n"
            f"Medium : {medium}\n"
            f"Description : {description}\n\n"
            f"Dimensions à quantifier :\n{dims_desc}\n\n"
            f"Réponds UNIQUEMENT en JSON avec les valeurs numériques. "
            f"Exemple : {{\"energy\": 0.9, \"pacing\": 0.85, ...}}"
        )
        result = _llm(prompt, self.SYSTEM, max_tokens=800)

        dna = NarrativeDNA(
            work_id=title.lower().replace(" ","_")[:20],
            title=title, medium=medium, description=description,
        )
        try:
            if result.startswith("```"):
                result = "\n".join(result.split("\n")[1:-1])
            dims = json.loads(result)
            for k, v in dims.items():
                if k in DNA_DIMENSIONS and isinstance(v, (int, float)):
                    dna.dimensions[k] = max(0.0, min(1.0, float(v)))
        except Exception:
            pass

        # Extraire les tags dominants
        dna.tags = [
            trait for trait, value in dna.dominant_traits(5)
            if abs(value - 0.5) > 0.2
        ]
        return dna

    def encode_from_tags(self, tags: list[str],
                          title: str = "custom") -> NarrativeDNA:
        """Encode rapidement depuis des tags sans description complète."""
        dna = NarrativeDNA(
            work_id=f"custom_{int(time.time())}",
            title=title, medium="custom", tags=tags,
        )
        # Heuristiques rapides
        tag_map = {
            "action":        {"action": 0.9, "energy": 0.8},
            "romance":       {"romance": 0.9, "joy": 0.7},
            "dark":          {"darkness": 0.9, "dread": 0.7},
            "epic":          {"epic": 0.9, "world_building": 0.8},
            "comedy":        {"comedy": 0.9, "joy": 0.8, "tension": 0.1},
            "melancholic":   {"melancholy": 0.9, "pacing": 0.2},
            "friendship":    {"friendship": 0.9, "hope": 0.7},
            "magic":         {"power_system": 0.8, "world_building": 0.7},
        }
        for tag in tags:
            for pattern, updates in tag_map.items():
                if pattern in tag.lower():
                    for dim, val in updates.items():
                        dna.dimensions[dim] = max(dna.dimensions.get(dim,0.5), val)
        return dna


# ══════════════════════════════════════════════════════════════════════
# CROISEUR D'ADN
# ══════════════════════════════════════════════════════════════════════

class DNACrosser:
    """
    Croise plusieurs ADN pour créer quelque chose de nouveau.

    Modes de croisement :
    - Blend      : moyenne pondérée de tous les ADN
    - Dominant   : un ADN principal + touches des autres
    - Contrast   : amplifier les différences entre les ADN
    - Synthesis  : trouver les traits complémentaires et les combiner
    """

    def blend(self, dnas: list[NarrativeDNA],
               weights: list[float] = None) -> NarrativeDNA:
        """Mélange pondéré de plusieurs ADN."""
        if not dnas:
            return NarrativeDNA("empty","Empty","custom")

        weights = weights or [1.0/len(dnas)] * len(dnas)
        total_w = sum(weights)
        weights = [w/total_w for w in weights]

        result_dims = {}
        for dim in DNA_DIMENSIONS:
            result_dims[dim] = sum(
                dna.dimensions.get(dim, 0.5) * w
                for dna, w in zip(dnas, weights)
            )

        title  = " × ".join(d.title for d in dnas)
        result = NarrativeDNA(
            work_id  = f"blend_{int(time.time())}",
            title    = title,
            medium   = dnas[0].medium,
            dimensions=result_dims,
            description=f"Croisement : {title}",
        )
        result.tags = [t for trait, val in result.dominant_traits(6)
                       for t in [trait] if abs(val-0.5) > 0.25]
        return result

    def contrast(self, dna_a: NarrativeDNA,
                  dna_b: NarrativeDNA) -> NarrativeDNA:
        """
        Amplifie les différences entre deux ADN.
        Résultat : quelque chose qui a les EXTREMES de chaque oeuvre
        sans les traits communs (qui s'annulent).
        """
        result_dims = {}
        for dim in DNA_DIMENSIONS:
            a = dna_a.dimensions.get(dim, 0.5)
            b = dna_b.dimensions.get(dim, 0.5)
            diff = abs(a - b)
            if diff > 0.2:
                # Garder le trait de celui qui est le plus extrême
                result_dims[dim] = a if abs(a-0.5) > abs(b-0.5) else b
            else:
                result_dims[dim] = 0.5   # annuler les similitudes
        return NarrativeDNA(
            work_id   = f"contrast_{int(time.time())}",
            title     = f"{dna_a.title} ≠ {dna_b.title}",
            medium    = "hybrid",
            dimensions= result_dims,
            description= f"Contraste maximal entre {dna_a.title} et {dna_b.title}",
        )

    def synthesis(self, dnas: list[NarrativeDNA]) -> dict:
        """
        Synthèse créative via LLM.
        Décrit en langage naturel le style hybride résultant.
        """
        crossed   = self.blend(dnas)
        traits    = crossed.dominant_traits(8)
        traits_str = "\n".join(f"  {t}: {v:.2f}" for t,v in traits)
        titles    = [d.title for d in dnas]
        result    = _llm(
            f"Tu croises les ADN narratifs de : {', '.join(titles)}\n\n"
            f"Traits dominants du croisement :\n{traits_str}\n\n"
            f"Décris en 3-4 phrases le style hybride qui en résulte : "
            f"comment il sonnrait, se verrait, quel type d'histoire il raconterait.\n"
            f"Puis propose 5 tags visuels ComfyUI pour capturer ce style.",
            max_tokens=400
        )
        return {
            "dna":         crossed,
            "description": result,
            "titles":      titles,
            "key_traits":  [t for t,_ in traits[:5]],
        }


# ══════════════════════════════════════════════════════════════════════
# BIBLIOTHÈQUE D'ADN
# ══════════════════════════════════════════════════════════════════════

class DNALibrary:
    """
    Bibliothèque d'ADN d'oeuvres de référence.
    Pré-encodés pour éviter des appels LLM répétés.
    """

    # ADN pré-définis pour les oeuvres majeures (expertise encodée)
    PRESETS: dict[str, dict] = {
        "dragon_ball": {
            "title": "Dragon Ball Z", "medium": "anime",
            "dims": {
                "energy":0.97,"pacing":0.85,"action":0.95,"epic":0.90,
                "friendship":0.85,"power_system":0.90,"comedy":0.60,
                "sacrifice":0.70,"dread":0.30,"melancholy":0.20,
                "romance":0.20,"color_vibrancy":0.85,"visual_beauty":0.65,
                "hero_journey":0.90,"world_building":0.70,"tension":0.85,
            }
        },
        "your_name": {
            "title": "Your Name (Kimi no Na wa)", "medium": "anime",
            "dims": {
                "visual_beauty":0.99,"melancholy":0.85,"romance":0.90,
                "mystery":0.80,"pacing":0.50,"energy":0.40,"action":0.15,
                "color_vibrancy":0.95,"hope":0.80,"joy":0.65,"detail_level":0.95,
                "realism":0.60,"friendship":0.70,"philosophy":0.50,
                "hero_journey":0.70,"world_building":0.60,
            }
        },
        "attack_on_titan": {
            "title": "Attack on Titan", "medium": "anime",
            "dims": {
                "dread":0.90,"sacrifice":0.95,"politics":0.90,"action":0.85,
                "tension":0.95,"darkness":0.90,"mystery":0.85,"epic":0.90,
                "anti_hero":0.80,"philosophy":0.75,"energy":0.80,
                "pacing":0.80,"romance":0.35,"comedy":0.10,"joy":0.20,
                "world_building":0.90,"visual_beauty":0.75,"ensemble":0.80,
            }
        },
        "demon_slayer": {
            "title": "Demon Slayer (Kimetsu no Yaiba)", "medium": "anime",
            "dims": {
                "visual_beauty":0.97,"action":0.90,"family":0.90,"dread":0.65,
                "color_vibrancy":0.98,"detail_level":0.97,"hope":0.80,
                "sacrifice":0.80,"epic":0.85,"energy":0.85,"pacing":0.80,
                "power_system":0.75,"romance":0.25,"comedy":0.35,
                "world_building":0.75,"hero_journey":0.85,"tension":0.80,
            }
        },
        "cowboy_bebop": {
            "title": "Cowboy Bebop", "medium": "anime",
            "dims": {
                "melancholy":0.90,"philosophy":0.80,"action":0.60,"jazz_aesthetic":0.95,
                "pacing":0.55,"energy":0.55,"romance":0.55,"mystery":0.65,
                "anti_hero":0.85,"realism":0.70,"darkness":0.65,"color_vibrancy":0.60,
                "visual_beauty":0.80,"comedy":0.45,"ensemble":0.70,"sacrifice":0.75,
            }
        },
        "evangelion": {
            "title": "Neon Genesis Evangelion", "medium": "anime",
            "dims": {
                "philosophy":0.97,"dread":0.85,"melancholy":0.90,"mystery":0.90,
                "anti_hero":0.80,"tension":0.90,"darkness":0.85,"energy":0.65,
                "action":0.75,"romance":0.55,"sacrifice":0.85,"pacing":0.60,
                "world_building":0.85,"visual_beauty":0.75,"realism":0.55,
            }
        },
        "one_piece": {
            "title": "One Piece", "medium": "anime",
            "dims": {
                "friendship":0.97,"adventure":0.95,"joy":0.80,"epic":0.85,
                "comedy":0.70,"sacrifice":0.75,"action":0.80,"hope":0.90,
                "world_building":0.95,"ensemble":0.90,"energy":0.80,
                "pacing":0.65,"power_system":0.80,"color_vibrancy":0.80,
                "melancholy":0.45,"dread":0.40,"visual_beauty":0.65,
            }
        },
    }

    def __init__(self):
        self._library: dict[str, NarrativeDNA] = {}
        self._file    = DNA_DIR / "dna_library.json"
        DNA_DIR.mkdir(parents=True, exist_ok=True)
        self._load_presets()
        self._load_custom()

    def _load_presets(self):
        """Charge les ADN pré-définis."""
        for key, data in self.PRESETS.items():
            dna = NarrativeDNA(
                work_id   = key,
                title     = data["title"],
                medium    = data["medium"],
                dimensions= {
                    **{dim: 0.5 for dim in DNA_DIMENSIONS},
                    **data["dims"]
                },
            )
            dna.tags = [t for t,v in dna.dominant_traits(6)
                        if abs(v-0.5) > 0.25]
            self._library[key] = dna

    def add(self, dna: NarrativeDNA):
        """Ajoute un ADN à la bibliothèque."""
        self._library[dna.work_id] = dna
        self._save()

    def get(self, work_id: str) -> Optional[NarrativeDNA]:
        return self._library.get(work_id)

    def find_similar(self, dna: NarrativeDNA,
                      n: int = 3) -> list[tuple[float, NarrativeDNA]]:
        """Trouve les N oeuvres les plus similaires."""
        similarities = [
            (dna.similarity(other), other)
            for other in self._library.values()
            if other.work_id != dna.work_id
        ]
        return sorted(similarities, key=lambda x: -x[0])[:n]

    def list_all(self) -> list[dict]:
        return [
            {
                "id":     d.work_id,
                "title":  d.title,
                "medium": d.medium,
                "traits": [f"{t}={v:.2f}" for t,v in d.dominant_traits(3)],
            }
            for d in self._library.values()
        ]

    def _save(self):
        custom = {k: v.to_dict() for k, v in self._library.items()
                  if k not in self.PRESETS}
        self._file.write_text(
            json.dumps(custom, indent=2, ensure_ascii=False), encoding="utf-8"
        )

    def _load_custom(self):
        if not self._file.exists():
            return
        try:
            data = json.loads(self._file.read_text(encoding="utf-8"))
            for k, d in data.items():
                dna = NarrativeDNA(
                    work_id=d["work_id"], title=d["title"],
                    medium=d["medium"], dimensions=d["dimensions"],
                    tags=d.get("tags",[]), description=d.get("description",""),
                )
                self._library[k] = dna
        except Exception:
            pass


# ══════════════════════════════════════════════════════════════════════
# TRADUCTEUR ADN → PRODUCTION
# ══════════════════════════════════════════════════════════════════════

class DNATranslator:
    """Traduit un ADN (croisé ou simple) en paramètres de production."""

    def translate(self, dna: NarrativeDNA) -> dict:
        """Traduit un ADN en paramètres complets pour le pipeline."""
        dims = dna.dimensions

        # Paramètres SDXL depuis l'ADN
        energy   = dims.get("energy", 0.5)
        beauty   = dims.get("visual_beauty", 0.5)
        darkness = dims.get("darkness", 0.5)
        detail   = dims.get("detail_level", 0.5)
        vibrant  = dims.get("color_vibrancy", 0.5)

        cfg    = 5.0 + energy * 3.0 + detail * 1.5
        cfg    = round(min(12.0, max(4.0, cfg)), 1)
        steps  = int(20 + beauty * 15 + detail * 10)
        steps  = min(48, max(16, steps))

        # Sampler selon l'énergie
        if energy > 0.75:   sampler = "euler_ancestral"
        elif energy > 0.45: sampler = "dpm++_2m_sde"
        else:               sampler = "dpm++_2m"

        # Tags visuels depuis l'ADN
        visual_tags = []
        if beauty > 0.7:    visual_tags.extend(["masterpiece","highly detailed","best quality"])
        if vibrant > 0.7:   visual_tags.extend(["vibrant colors","colorful"])
        if darkness > 0.6:  visual_tags.extend(["dark atmosphere","dramatic lighting","shadows"])
        if energy > 0.7:    visual_tags.extend(["dynamic pose","action","motion"])
        if dims.get("epic", 0) > 0.7:
            visual_tags.extend(["epic scale","dramatic","cinematic"])
        if dims.get("romance", 0) > 0.7:
            visual_tags.extend(["soft lighting","romantic","warm colors"])
        if dims.get("melancholy", 0) > 0.7:
            visual_tags.extend(["melancholic","rain","grey tones"])

        # Ton narratif
        dominant = dna.dominant_traits(3)
        tone_map = {
            "energy":      "rythme soutenu et dynamique",
            "melancholy":  "mélancolique et contemplatif",
            "epic":        "grandiose et épique",
            "comedy":      "léger et humoristique",
            "dread":       "tendu et oppressant",
            "romance":     "romantique et tendre",
            "philosophy":  "profond et réflexif",
        }
        narrative_tones = [tone_map.get(t,"neutre") for t,_ in dominant if t in tone_map]

        return {
            "dna_title":      dna.title,
            "dominant_traits":[t for t,_ in dominant],
            "visual_tags":    visual_tags,
            "cfg":            cfg,
            "steps":          steps,
            "sampler":        sampler,
            "scheduler":      "karras" if energy > 0.5 else "normal",
            "narrative_tone": ", ".join(narrative_tones[:2]) or "équilibré",
            "color_mood":     "vibrant" if vibrant > 0.6 else "muted",
            "lighting":       "dramatic" if darkness > 0.6 else "natural",
        }


# ══════════════════════════════════════════════════════════════════════
# NARRATIVE DNA — FAÇADE
# ══════════════════════════════════════════════════════════════════════

class NarrativeDNASystem:
    """Façade complète du système Narrative DNA."""

    def __init__(self, logger: logging.Logger = None):
        self.log        = logger or logging.getLogger("narrative_dna")
        self.encoder    = DNAEncoder()
        self.crosser    = DNACrosser()
        self.library    = DNALibrary()
        self.translator = DNATranslator()

    def encode_work(self, title: str, description: str,
                     medium: str = "anime") -> NarrativeDNA:
        """Encode une nouvelle oeuvre et l'ajoute à la bibliothèque."""
        dna = self.encoder.encode(title, description, medium)
        self.library.add(dna)
        self.log.info(f"[DNA] Encodé : '{title}' | traits: {dna.tags[:3]}")
        return dna

    def cross(self, work_ids: list[str],
               weights: list[float] = None) -> dict:
        """
        Croise plusieurs oeuvres par leurs IDs et retourne
        les paramètres de production + la description du style hybride.
        """
        dnas = []
        for wid in work_ids:
            dna = self.library.get(wid)
            if dna:
                dnas.append(dna)

        if not dnas:
            return {"error": "Aucune oeuvre trouvée"}

        if len(dnas) == 1:
            crossed = dnas[0]
            synthesis = {"description": f"ADN pur de {dnas[0].title}",
                          "key_traits": [t for t,_ in dnas[0].dominant_traits(5)]}
        else:
            synthesis = self.crosser.synthesis(dnas)
            crossed   = synthesis["dna"]

        params = self.translator.translate(crossed)
        self.log.info(
            f"[DNA] Croisement : {[d.title for d in dnas]} | "
            f"CFG={params['cfg']} steps={params['steps']}"
        )
        return {
            "crossed_dna":   crossed.to_dict(),
            "synthesis":     synthesis,
            "production_params": params,
            "similar_works": [
                {"similarity": round(sim,3), "title": other.title}
                for sim, other in self.library.find_similar(crossed, n=3)
            ],
        }

    def get_production_params(self, work_id: str) -> dict:
        """Paramètres de production pour une oeuvre de référence."""
        dna = self.library.get(work_id)
        if not dna:
            return {}
        return self.translator.translate(dna)

    def suggest_crosses(self, work_id: str) -> list[dict]:
        """Suggère des croisements intéressants pour une oeuvre."""
        dna = self.library.get(work_id)
        if not dna:
            return []
        # Trouver des oeuvres complémentaires (pas trop similaires, pas trop différentes)
        all_works = list(self.library._library.values())
        scored    = []
        for other in all_works:
            if other.work_id == work_id:
                continue
            sim = dna.similarity(other)
            # Croisement idéal : similarité entre 0.4 et 0.7 (complémentaire mais pas identique)
            interest = 1.0 - abs(sim - 0.55)
            scored.append((interest, sim, other))

        scored.sort(key=lambda x: -x[0])
        return [
            {
                "work_id":    other.work_id,
                "title":      other.title,
                "similarity": round(sim, 3),
                "interest":   round(interest, 3),
                "why":        f"Complémentarité sur : "
                              + ", ".join([t for t,v in other.dominant_traits(3)
                                           if dna.dimensions.get(t,0.5) < 0.4]),
            }
            for interest, sim, other in scored[:5]
        ]

    def get_dashboard(self) -> dict:
        return {
            "version":   "1.30_narrative_dna",
            "library_size": len(self.library._library),
            "preset_works": list(self.library.PRESETS.keys()),
            "dimensions": len(DNA_DIMENSIONS),
        }


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    dna_sys = NarrativeDNASystem()

    print("=== V1.30 NARRATIVE DNA TEST ===\n")
    print(f"Bibliothèque : {len(dna_sys.library._library)} oeuvres")
    for entry in dna_sys.library.list_all():
        print(f"  {entry['title']:<35} {entry['traits']}")

    print("\n--- Croisement Dragon Ball × Your Name ---")
    result = dna_sys.cross(["dragon_ball","your_name"], weights=[0.6, 0.4])
    if "production_params" in result:
        params = result["production_params"]
        print(f"CFG={params['cfg']} | steps={params['steps']} | {params['sampler']}")
        print(f"Tags : {params['visual_tags'][:5]}")
        print(f"Ton  : {params['narrative_tone']}")
    if result.get("synthesis",{}).get("description"):
        print(f"Style : {result['synthesis']['description'][:200]}")

    print("\n--- Suggestions de croisement pour Evangelion ---")
    suggestions = dna_sys.suggest_crosses("evangelion")
    for s in suggestions[:3]:
        print(f"  × {s['title']:<30} sim={s['similarity']:.2f} | {s['why'][:50]}")

    print(f"\nDashboard : {dna_sys.get_dashboard()}")

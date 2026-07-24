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
comfy_synesthesia_node.py — Nœud ComfyUI Synesthésie IA
Convertit une analyse audio en hallucinations visuelles contrôlées.
Activable manuellement depuis l'interface OverLord.

Installation :
  Copier ce fichier dans :
  ComfyUI/custom_nodes/overlord_synesthesia/

Le nœud apparaît dans ComfyUI sous : "Ov3rLoRd / Synesthésie IA"

Fonctionnement :
  audio_file → [SYNESTHÉSIE IA] → positive_prompt_enrichi
                                 → negative_prompt_adapté
                                 → color_conditioning
                                 → energy_multiplier (pour le CFG)

Inspiration :
  La synesthésie est un phénomène neurologique où les sens se mélangent.
  Un musicien synesthète "voit" les couleurs quand il entend de la musique.
  Ce nœud fait pareil pour notre IA : l'audio devient de la vision.
"""

# ── Pour ComfyUI custom node ──────────────────────────────────────────
# ComfyUI charge automatiquement ce fichier depuis custom_nodes/

import json
import os
import hashlib
from pathlib import Path

# Dépendances optionnelles
try:
    import numpy as np
    import torch
    TORCH_OK = True
except ImportError:
    TORCH_OK = False

try:
    import librosa
    LIBROSA_OK = True
except ImportError:
    LIBROSA_OK = False


# ══════════════════════════════════════════════════════════════════════
# MAPPINGS SYNESTHÉSIE
# ══════════════════════════════════════════════════════════════════════

# BPM → énergie visuelle
BPM_TO_ENERGY = {
    (0,   60):  ("slow",       0.6, "slow motion, peaceful atmosphere, soft"),
    (60,  90):  ("calm",       0.7, "calm composition, balanced, measured pacing"),
    (90,  120): ("moderate",   0.8, "dynamic but controlled, steady rhythm"),
    (120, 150): ("energetic",  1.0, "dynamic angle, action pose, motion lines"),
    (150, 180): ("intense",    1.1, "extreme angle, explosive energy, speed lines"),
    (180, 999): ("frantic",    1.2, "chaotic energy, rapid motion, overwhelming"),
}

# Tonalité musicale → palette de couleurs
KEY_TO_COLORS = {
    "C":  ("rouge",    ["crimson red", "scarlet", "ruby tones", "warm red palette"]),
    "C#": ("orangé",   ["orange red", "amber", "fiery orange"]),
    "D":  ("jaune",    ["golden yellow", "sunlight", "warm gold"]),
    "D#": ("vert",     ["forest green", "emerald", "natural green"]),
    "E":  ("turquoise",["teal", "turquoise", "ocean blue-green"]),
    "F":  ("bleu",     ["deep blue", "cobalt", "sapphire blue"]),
    "F#": ("indigo",   ["indigo", "violet blue", "twilight blue"]),
    "G":  ("violet",   ["purple violet", "lavender", "mystic purple"]),
    "G#": ("magenta",  ["magenta", "hot pink", "electric purple"]),
    "A":  ("rose",     ["rose gold", "salmon pink", "warm pink"]),
    "A#": ("blanc",    ["silver white", "pearl", "luminous white"]),
    "B":  ("gris",     ["charcoal", "silver grey", "metallic tones"]),
}

# Mood audio → style visuel ComfyUI
MOOD_TO_VISUAL = {
    "energetic": {
        "style":     "dynamic composition, action lines, explosive energy",
        "lighting":  "harsh dramatic lighting, high contrast",
        "camera":    "dutch angle, low angle shot, extreme close-up",
        "effects":   "motion blur, speed lines, energy particles",
        "negative_add": "static, peaceful, slow, boring composition",
    },
    "ambient": {
        "style":     "dreamy atmosphere, soft bokeh, ethereal glow",
        "lighting":  "soft diffused light, golden hour, moonlight",
        "camera":    "wide shot, symmetrical composition, long shot",
        "effects":   "lens flare, soft glow, atmospheric haze",
        "negative_add": "harsh lighting, sharp contrast, busy composition",
    },
    "upbeat": {
        "style":     "cheerful expression, vibrant colors, energetic pose",
        "lighting":  "bright sunlight, clear sky, colorful",
        "camera":    "medium shot, slight tilt, dynamic framing",
        "effects":   "sparkles, light rays, colorful particles",
        "negative_add": "dark, gloomy, sad, monochrome",
    },
    "melodic": {
        "style":     "emotional expression, cinematic depth, poetic composition",
        "lighting":  "warm tones, sunset, candlelight",
        "camera":    "close-up, shallow depth of field, portrait",
        "effects":   "soft focus, vignette, warm color grading",
        "negative_add": "cold tones, harsh, clinical, empty",
    },
    "melancholic": {
        "style":     "melancholic expression, rain, solitude",
        "lighting":  "cold blue tones, overcast, muted colors",
        "camera":    "bird eye view, distant shot, lonely framing",
        "effects":   "rain drops, fog, desaturated",
        "negative_add": "happy, bright, crowded, colorful",
    },
    "epic": {
        "style":     "epic scale, heroic pose, majestic composition",
        "lighting":  "dramatic god rays, strong contrasts, golden glow",
        "camera":    "low angle, wide establishing shot, heroic framing",
        "effects":   "lens flare, atmospheric dust, dramatic clouds",
        "negative_add": "mundane, small scale, casual, everyday",
    },
}

# Instrument dominant → texture visuelle
INSTRUMENT_TO_TEXTURE = {
    "piano":     "smooth surfaces, classical elegance, refined details",
    "guitar":    "organic textures, natural materials, handcrafted feel",
    "bass":      "heavy shadows, depth, underground aesthetic",
    "drums":     "raw energy, grunge texture, urban style",
    "synth":     "neon glow, digital aesthetic, futuristic",
    "violin":    "flowing lines, silk textures, romantic style",
    "electronic":"glitch effects, pixel art elements, cyberpunk",
    "orchestra": "grand scale, classical composition, epic staging",
}


# ══════════════════════════════════════════════════════════════════════
# ANALYSEUR AUDIO
# ══════════════════════════════════════════════════════════════════════

class AudioAnalyzer:
    """Analyse un fichier audio et extrait les caractéristiques synesthésiques."""

    def analyze(self, audio_path: str) -> dict:
        """Analyse complète d'un fichier audio."""
        result = {
            "bpm":        120.0,
            "key":        "C",
            "mood":       "melodic",
            "energy":     0.5,
            "brightness": 0.5,
            "roughness":  0.3,
            "duration_s": 0.0,
            "analysis_ok": False,
        }

        if not LIBROSA_OK:
            result["error"] = "librosa non installé (pip install librosa)"
            return result

        try:
            y, sr = librosa.load(audio_path, duration=60, mono=True)
            result["duration_s"] = float(len(y) / sr)

            # BPM
            tempo, _ = librosa.beat.beat_track(y=y, sr=sr)
            result["bpm"] = float(tempo)

            # Énergie RMS
            rms = librosa.feature.rms(y=y)
            result["energy"] = float(np.mean(rms))

            # Brightness (centroid spectral normalisé)
            centroid = librosa.feature.spectral_centroid(y=y, sr=sr)
            result["brightness"] = min(1.0, float(np.mean(centroid)) / 4000.0)

            # Roughness (zero crossing rate)
            zcr = librosa.feature.zero_crossing_rate(y=y)
            result["roughness"] = min(1.0, float(np.mean(zcr)) * 10)

            # Tonalité (chroma)
            chroma = librosa.feature.chroma_cqt(y=y, sr=sr)
            keys   = ["C","C#","D","D#","E","F","F#","G","G#","A","A#","B"]
            result["key"] = keys[int(np.mean(chroma, axis=1).argmax())]

            # Mood composite
            bpm   = result["bpm"]
            energy = result["energy"]
            if energy > 0.15 and bpm > 140:
                result["mood"] = "energetic"
            elif energy > 0.10 and bpm > 120:
                result["mood"] = "epic"
            elif energy > 0.08 and bpm > 100:
                result["mood"] = "upbeat"
            elif energy < 0.03:
                result["mood"] = "ambient"
            elif result["brightness"] < 0.3:
                result["mood"] = "melancholic"
            else:
                result["mood"] = "melodic"

            result["analysis_ok"] = True

        except Exception as e:
            result["error"] = str(e)

        return result


# ══════════════════════════════════════════════════════════════════════
# GÉNÉRATEUR SYNESTHÉSIE
# ══════════════════════════════════════════════════════════════════════

class SynesthesiaGenerator:
    """Convertit une analyse audio en paramètres visuels ComfyUI."""

    def generate(self, audio_analysis: dict,
                  base_positive: str = "",
                  base_negative: str = "",
                  intensity: float = 1.0) -> dict:
        """
        Génère les paramètres visuels depuis l'analyse audio.

        intensity : 0.0 = pas de synesthésie | 1.0 = pleine synesthésie
        """
        bpm      = audio_analysis.get("bpm",    120.0)
        key      = audio_analysis.get("key",    "C")
        mood     = audio_analysis.get("mood",   "melodic")
        energy   = audio_analysis.get("energy", 0.5)
        bright   = audio_analysis.get("brightness", 0.5)

        # BPM → énergie visuelle
        energy_info = None
        for (lo, hi), (label, mult, tags) in BPM_TO_ENERGY.items():
            if lo <= bpm < hi:
                energy_info = (label, mult, tags)
                break
        if not energy_info:
            energy_info = ("moderate", 1.0, "balanced energy")

        _, cfg_mult, energy_tags = energy_info

        # Tonalité → couleurs
        _, color_tags = KEY_TO_COLORS.get(key, ("neutre", ["balanced colors"]))

        # Mood → style visuel
        mood_data = MOOD_TO_VISUAL.get(mood, MOOD_TO_VISUAL["melodic"])

        # Assembler les tags positifs
        synesthesia_tags = [
            energy_tags,
            ", ".join(color_tags[:2]),
            mood_data["style"],
            mood_data["lighting"],
            mood_data["camera"],
            mood_data["effects"],
        ]
        synesthesia_positive = ", ".join(synesthesia_tags)

        # Mélange avec le prompt de base selon l'intensité
        if base_positive and intensity < 1.0:
            merged_positive = (
                base_positive + ", " +
                self._blend_prompts(synesthesia_positive, intensity)
            )
        else:
            merged_positive = (
                (base_positive + ", " if base_positive else "") +
                synesthesia_positive
            )

        # Négatif adapté
        merged_negative = base_negative
        if mood_data.get("negative_add"):
            merged_negative += (", " if merged_negative else "") + mood_data["negative_add"]

        # CFG ajusté selon l'énergie
        cfg_adjustment = (cfg_mult - 1.0) * intensity * 2  # ±2 max

        return {
            # Prompts synesthésiques
            "positive":          merged_positive,
            "negative":          merged_negative,
            "synesthesia_tags":  synesthesia_positive,
            # Paramètres ajustés
            "cfg_adjustment":    round(cfg_adjustment, 2),
            "recommended_cfg":   round(6.0 + cfg_adjustment, 1),
            "energy_level":      energy_info[0],
            # Info synesthésie
            "bpm":               bpm,
            "key":               key,
            "mood":              mood,
            "color_palette":     color_tags,
            "intensity_applied": intensity,
            # Métadonnées
            "analysis": {
                "energy_raw":  round(energy, 4),
                "brightness":  round(bright, 3),
                "cfg_mult":    cfg_mult,
            }
        }

    def _blend_prompts(self, synesthesia: str, intensity: float) -> str:
        """Sélectionne les N premiers tags selon l'intensité."""
        tags  = [t.strip() for t in synesthesia.split(",") if t.strip()]
        n     = max(1, int(len(tags) * intensity))
        return ", ".join(tags[:n])


# ══════════════════════════════════════════════════════════════════════
# NŒUD COMFYUI
# ══════════════════════════════════════════════════════════════════════

class OverLordSynesthesiaNode:
    """
    Nœud ComfyUI : Synesthésie IA OverLord
    Catégorie : Ov3rLoRd / Synesthésie IA
    """

    _analyzer  = AudioAnalyzer()
    _generator = SynesthesiaGenerator()
    _cache: dict = {}

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "base_positive": ("STRING", {
                    "default": "masterpiece, best quality, 1girl, anime style",
                    "multiline": True,
                }),
                "base_negative": ("STRING", {
                    "default": "bad quality, worst quality, deformed",
                    "multiline": True,
                }),
                "audio_file": ("STRING", {
                    "default": "",
                    "placeholder": "Chemin vers le fichier audio (.mp3/.wav/.flac)",
                }),
                "synesthesia_intensity": ("FLOAT", {
                    "default": 0.7,
                    "min":     0.0,
                    "max":     1.0,
                    "step":    0.05,
                    "display": "slider",
                }),
                "enabled": ("BOOLEAN", {
                    "default": True,
                    "label_on":  "Synesthésie ACTIVE",
                    "label_off": "Synesthésie OFF",
                }),
            },
            "optional": {
                "override_mood": (["auto", "energetic", "ambient", "upbeat",
                                    "melodic", "melancholic", "epic"], {
                    "default": "auto",
                }),
                "override_bpm": ("FLOAT", {
                    "default": 0.0,
                    "min": 0.0, "max": 300.0, "step": 1.0,
                }),
            }
        }

    RETURN_TYPES  = ("STRING", "STRING", "FLOAT", "STRING", "STRING")
    RETURN_NAMES  = ("positive", "negative", "cfg_adjustment",
                      "synesthesia_report", "mood_detected")
    FUNCTION      = "process"
    CATEGORY      = "OverLord/Synesthésie IA"
    OUTPUT_NODE   = False

    def process(self, base_positive: str, base_negative: str,
                 audio_file: str, synesthesia_intensity: float,
                 enabled: bool, override_mood: str = "auto",
                 override_bpm: float = 0.0):
        """Traitement principal du nœud."""

        # Mode désactivé → pass-through
        if not enabled:
            return (base_positive, base_negative, 0.0,
                    "Synesthésie désactivée", "N/A")

        # Cache pour éviter de réanalyser le même fichier
        cache_key = hashlib.md5(f"{audio_file}{intensity}".encode()).hexdigest()[:8]
        if audio_file and Path(audio_file).exists():
            if cache_key not in self._cache:
                analysis = self._analyzer.analyze(audio_file)
                self._cache[cache_key] = analysis
            else:
                analysis = self._cache[cache_key]
        else:
            # Pas de fichier → utiliser les overrides ou valeurs par défaut
            analysis = {
                "bpm":    override_bpm if override_bpm > 0 else 120.0,
                "key":    "C",
                "mood":   override_mood if override_mood != "auto" else "melodic",
                "energy": 0.5,
                "brightness": 0.5,
                "analysis_ok": False,
            }

        # Appliquer overrides
        intensity = synesthesia_intensity
        if override_mood != "auto":
            analysis["mood"] = override_mood
        if override_bpm > 0:
            analysis["bpm"] = override_bpm

        # Génération
        result = self._generator.generate(
            analysis, base_positive, base_negative, intensity
        )

        # Rapport
        report = (
            f"🎵 SYNESTHÉSIE IA OverLord\n"
            f"BPM: {result['bpm']:.0f} | "
            f"Tonalité: {result['key']} | "
            f"Mood: {result['mood']}\n"
            f"Énergie: {result['energy_level']} | "
            f"CFG ajust: {result['cfg_adjustment']:+.2f}\n"
            f"Palette: {', '.join(result['color_palette'][:2])}\n"
            f"Tags ajoutés: {result['synesthesia_tags'][:80]}..."
        )

        return (
            result["positive"],
            result["negative"],
            result["cfg_adjustment"],
            report,
            result["mood"],
        )


# ══════════════════════════════════════════════════════════════════════
# REGISTRATION COMFYUI
# ══════════════════════════════════════════════════════════════════════

# Ces deux dicts sont requis par ComfyUI pour charger le nœud
NODE_CLASS_MAPPINGS = {
    "OverLordSynesthesia": OverLordSynesthesiaNode,
}

NODE_DISPLAY_NAME_MAPPINGS = {
    "OverLordSynesthesia": "🎵 Synesthésie IA OverLord",
}


# ══════════════════════════════════════════════════════════════════════
# TEST STANDALONE (hors ComfyUI)
# ══════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    print("=== TEST NŒUD SYNESTHÉSIE IA ===\n")

    analyzer  = AudioAnalyzer()
    generator = SynesthesiaGenerator()

    # Test avec analyse simulée (sans vrai fichier audio)
    test_analyses = [
        {"bpm": 165, "key": "D#", "mood": "energetic",  "energy": 0.18, "brightness": 0.8,  "analysis_ok": True},
        {"bpm": 72,  "key": "A",  "mood": "ambient",    "energy": 0.02, "brightness": 0.3,  "analysis_ok": True},
        {"bpm": 128, "key": "G",  "mood": "epic",       "energy": 0.12, "brightness": 0.65, "analysis_ok": True},
        {"bpm": 95,  "key": "F",  "mood": "melancholic","energy": 0.05, "brightness": 0.25, "analysis_ok": True},
    ]

    base_pos = "masterpiece, best quality, 1girl, solo, looking at viewer, anime style"
    base_neg = "bad quality, worst quality, deformed, bad hands"

    for analysis in test_analyses:
        result = generator.generate(analysis, base_pos, base_neg, intensity=0.8)
        print(f"━━━ BPM:{analysis['bpm']:.0f} | Key:{analysis['key']} | Mood:{analysis['mood']} ━━━")
        print(f"Énergie visuelle : {result['energy_level']} | CFG ajust : {result['cfg_adjustment']:+.2f}")
        print(f"Palette          : {', '.join(result['color_palette'][:3])}")
        print(f"Prompt positif   : {result['positive'][:120]}...")
        print()

    print("Installation dans ComfyUI :")
    print("  Copier comfy_synesthesia_node.py dans :")
    print("  ComfyUI/custom_nodes/overlord_synesthesia/__init__.py")
    print("  Le nœud apparaît sous : Ov3rLoRd / Synesthésie IA")

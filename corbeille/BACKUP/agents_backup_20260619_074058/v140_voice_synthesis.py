"""
agents/v140_voice_synthesis.py — Ov3rLoRd V1.40 — Voice & Audio Synthesis

Synthèse vocale et musicale avancée :
  - XTTS v2     : clonage de voix depuis 3 secondes d'audio
  - Bark        : voix expressives avec émotions, bruits, musique
  - MusicGen    : musique générative adaptée au mood de la scène
  - Synchronizer: alignement automatique voix/musique/effets

Chaque personnage a une voix unique persistante.
La musique s'adapte automatiquement à l'Emotion Engine.
"""

import json
import time
import logging
import hashlib
import threading
from pathlib import Path
from dataclasses import dataclass, field
from typing import Optional
import requests

VOICE_DIR     = Path("workspace/voice_synthesis")
ANTHROPIC_URL = "https://api.anthropic.com/v1/messages"

def _get_api_key() -> str:
    import os as _os
    from pathlib import Path as _P
    key = _os.environ.get("ANTHROPIC_API_KEY", "")
    if not key:
        env = _P(__file__).parent.parent / ".env"
        if env.exists():
            for line in env.read_text(encoding="utf-8").splitlines():
                if line.startswith("ANTHROPIC_API_KEY="):
                    key = line.split("=",1)[1].strip().strip('"').strip("'")
    return key

CLAUDE_MODEL  = "claude-sonnet-4-6"


def _llm(prompt: str, system: str = "", max_tokens: int = 300) -> str:
    try:
        body = {"model": CLAUDE_MODEL, "max_tokens": max_tokens,
                "messages": [{"role": "user", "content": prompt}]}
        if system:
            body["system"] = system
        r = requests.post(ANTHROPIC_URL,
                          headers={
                "Content-Type": "application/json",
                "x-api-key": _get_api_key(),
                "anthropic-version": "2023-06-01",
            },
                          json=body, timeout=20)
        if r.status_code == 200:
            return r.json()["content"][0]["text"].strip()
    except Exception:
        pass
    return ""


# ══════════════════════════════════════════════════════════════════════
# PROFIL DE VOIX
# ══════════════════════════════════════════════════════════════════════

@dataclass
class VoiceProfile:
    """Profil de voix d'un personnage."""
    character_id:   str
    character_name: str
    voice_sample:   str = ""       # chemin vers le fichier audio de référence
    bark_preset:    str = "v2/en_speaker_0"
    language:       str = "fr"
    pitch:          float = 1.0    # 0.5=grave, 2.0=aigu
    speed:          float = 1.0
    emotion_default:str = "neutral"
    description:    str = ""       # "voix grave et posée d'un guerrier"

    def to_tts_params(self, emotion: str = "") -> dict:
        emo = emotion or self.emotion_default
        speed_mod = {
            "angry": 1.2, "excited": 1.15, "sad": 0.85,
            "scared": 1.1, "tender": 0.9, "epic": 1.0,
        }.get(emo, 1.0)
        return {
            "language":    self.language,
            "speed":       self.speed * speed_mod,
            "pitch":       self.pitch,
            "emotion":     emo,
            "bark_preset": self.bark_preset,
        }


# ══════════════════════════════════════════════════════════════════════
# XTTS ENGINE
# ══════════════════════════════════════════════════════════════════════

class XTTSEngine:
    """
    XTTS v2 — clonage de voix haute qualité.
    Clone une voix depuis 3-10 secondes d'audio de référence.

    pip install TTS  (Coqui TTS — contient XTTS v2)
    """

    def __init__(self, logger: logging.Logger = None):
        self.log    = logger or logging.getLogger("xtts")
        self._model = None
        self._ready = False
        VOICE_DIR.mkdir(parents=True, exist_ok=True)

    def _load(self) -> bool:
        """Charge le modèle XTTS (lazy loading)."""
        if self._ready:
            return True
        try:
            from TTS.api import TTS
            self._model = TTS("tts_models/multilingual/multi-dataset/xtts_v2")
            self._ready = True
            self.log.info("[XTTS] ✓ Modèle chargé")
            return True
        except ImportError:
            self.log.warning("[XTTS] pip install TTS")
            return False
        except Exception as e:
            self.log.error(f"[XTTS] Chargement : {e}")
            return False

    def synthesize(self, text: str,
                    speaker_wav: str,
                    language:    str = "fr",
                    output_path: str = "") -> str:
        """
        Synthétise du texte avec clonage de voix.
        speaker_wav : fichier WAV de référence (3-10 secondes)
        """
        if not self._load():
            return self._fallback_tts(text, output_path)

        if not output_path:
            h = hashlib.md5(text.encode()).hexdigest()[:8]
            output_path = str(VOICE_DIR / f"xtts_{h}.wav")

        try:
            self._model.tts_to_file(
                text=text,
                speaker_wav=speaker_wav,
                language=language,
                file_path=output_path,
            )
            self.log.info(f"[XTTS] ✓ Synthèse : {Path(output_path).name}")
            return output_path
        except Exception as e:
            self.log.error(f"[XTTS] Synthèse : {e}")
            return self._fallback_tts(text, output_path)

    def _fallback_tts(self, text: str, output_path: str) -> str:
        """Fallback vers gTTS si XTTS non disponible."""
        try:
            from gtts import gTTS
            if not output_path:
                output_path = str(VOICE_DIR / f"gtts_{int(time.time())}.mp3")
            gTTS(text=text, lang="fr").save(output_path)
            self.log.info(f"[XTTS→gTTS] Fallback : {output_path}")
            return output_path
        except Exception as e:
            self.log.error(f"[gTTS] {e}")
            return ""

    def clone_character_voice(self, character_name: str,
                               reference_audio: str,
                               test_text: str = "Bonjour, je suis prêt.") -> VoiceProfile:
        """Clone une voix et crée un profil de personnage."""
        profile = VoiceProfile(
            character_id=hashlib.md5(character_name.encode()).hexdigest()[:8],
            character_name=character_name,
            voice_sample=reference_audio,
        )
        # Test de synthèse
        test_path = str(VOICE_DIR / f"test_{profile.character_id}.wav")
        result = self.synthesize(test_text, reference_audio, output_path=test_path)
        if result:
            self.log.info(f"[XTTS] ✓ Voix clonée : {character_name}")
        return profile


# ══════════════════════════════════════════════════════════════════════
# BARK ENGINE
# ══════════════════════════════════════════════════════════════════════

class BarkEngine:
    """
    Bark — voix expressives avec émotions, rires, bruits.
    Supporte : [laughs], [sighs], [gasps], [clears throat], [music]
    pip install bark
    """

    EMOTION_TAGS = {
        "angry":   "[angry]",
        "sad":     "[sad]",
        "happy":   "[laughs]",
        "scared":  "[gasp]",
        "tired":   "[sighs]",
        "epic":    "",   # pas de tag — laisser le modèle interpréter
        "tender":  "[whispers]",
    }

    SPEAKER_PRESETS = {
        "male_hero":    "v2/fr_speaker_3",
        "female_hero":  "v2/fr_speaker_6",
        "villain":      "v2/fr_speaker_8",
        "narrator":     "v2/fr_speaker_0",
        "child":        "v2/fr_speaker_2",
        "elder":        "v2/fr_speaker_5",
    }

    def __init__(self, logger: logging.Logger = None):
        self.log    = logger or logging.getLogger("bark")
        self._model = None
        self._ready = False

    def _load(self) -> bool:
        if self._ready:
            return True
        try:
            from bark import SAMPLE_RATE, generate_audio, preload_models
            preload_models()
            self._SAMPLE_RATE   = SAMPLE_RATE
            self._generate      = generate_audio
            self._ready         = True
            self.log.info("[BARK] ✓ Modèle chargé")
            return True
        except ImportError:
            self.log.warning("[BARK] pip install bark")
            return False
        except Exception as e:
            self.log.error(f"[BARK] {e}")
            return False

    def synthesize(self, text: str,
                    speaker_type: str = "narrator",
                    emotion: str = "",
                    output_path: str = "") -> str:
        """
        Synthétise avec Bark.
        Injecte automatiquement les tags d'émotion.
        """
        if not output_path:
            h = hashlib.md5(f"{text}{emotion}".encode()).hexdigest()[:8]
            output_path = str(VOICE_DIR / f"bark_{h}.wav")

        # Enrichir le texte avec les tags d'émotion
        emo_tag   = self.EMOTION_TAGS.get(emotion, "")
        full_text = f"{emo_tag} {text}" if emo_tag else text
        preset    = self.SPEAKER_PRESETS.get(speaker_type, "v2/fr_speaker_0")

        if not self._load():
            # Fallback gTTS
            try:
                from gtts import gTTS
                gTTS(text=text, lang="fr").save(output_path)
                return output_path
            except Exception:
                return ""

        try:
            import numpy as np
            import scipy.io.wavfile as wav
            audio = self._generate(full_text, history_prompt=preset)
            wav.write(output_path, self._SAMPLE_RATE,
                      audio.astype(np.int16))
            self.log.info(f"[BARK] ✓ {speaker_type}/{emotion} : {Path(output_path).name}")
            return output_path
        except Exception as e:
            self.log.error(f"[BARK] {e}")
            return ""

    def narrate_scene(self, narration: str,
                       output_path: str = "") -> str:
        """Synthétise une narration avec la voix du narrateur."""
        return self.synthesize(narration, "narrator", output_path=output_path)


# ══════════════════════════════════════════════════════════════════════
# MUSICGEN ENGINE
# ══════════════════════════════════════════════════════════════════════

class MusicGenEngine:
    """
    MusicGen (Meta) — musique générative adaptée au mood.
    pip install audiocraft
    """

    MOOD_PROMPTS = {
        "epic":       "epic orchestral music, dramatic strings, powerful drums, anime battle theme",
        "sad":        "melancholic piano, slow tempo, emotional strings, sad anime ost",
        "joy":        "upbeat japanese pop, cheerful melody, bright instruments, happy anime",
        "tension":    "tense orchestral, building suspense, staccato strings, thriller",
        "peaceful":   "ambient nature sounds, gentle piano, calm flute, slice of life anime",
        "action":     "fast paced electronic, heavy drums, electric guitar, action anime",
        "romance":    "soft piano, romantic strings, warm tones, shoujo anime ost",
        "mystery":    "dark ambient, mysterious bells, ethereal voices, fantasy rpg",
        "triumph":    "triumphant brass, epic choir, victory fanfare, climax theme",
        "nostalgia":  "acoustic guitar, warm tones, nostalgic melody, childhood memories",
    }

    def __init__(self, logger: logging.Logger = None):
        self.log    = logger or logging.getLogger("musicgen")
        self._model = None
        self._ready = False

    def _load(self, model_size: str = "small") -> bool:
        """Charge MusicGen (small=300M, medium=1.5B, large=3.3B)."""
        if self._ready:
            return True
        try:
            from audiocraft.models import MusicGen
            self._model = MusicGen.get_pretrained(f"facebook/musicgen-{model_size}")
            self._model.set_generation_params(duration=8)
            self._ready = True
            self.log.info(f"[MUSICGEN] ✓ {model_size} chargé")
            return True
        except ImportError:
            self.log.warning("[MUSICGEN] pip install audiocraft")
            return False
        except Exception as e:
            self.log.error(f"[MUSICGEN] {e}")
            return False

    def generate(self, mood: str,
                  duration_s: float = 8.0,
                  output_path: str = "") -> str:
        """Génère de la musique adaptée au mood."""
        if not output_path:
            h = hashlib.md5(f"{mood}{duration_s}".encode()).hexdigest()[:8]
            output_path = str(VOICE_DIR / f"music_{mood}_{h}.wav")

        prompt = self.MOOD_PROMPTS.get(mood,
                  f"anime soundtrack, {mood} mood, instrumental")

        if not self._load():
            self.log.warning("[MUSICGEN] Non disponible — musique ignorée")
            return ""

        try:
            import torchaudio
            self._model.set_generation_params(duration=duration_s)
            wav = self._model.generate([prompt])
            torchaudio.save(output_path, wav[0].cpu(), 32000)
            self.log.info(f"[MUSICGEN] ✓ {duration_s}s de {mood} : {output_path}")
            return output_path
        except Exception as e:
            self.log.error(f"[MUSICGEN] {e}")
            return ""

    def generate_for_episode(self, emotion_arc: list[str],
                              shot_durations: list[float]) -> list[str]:
        """
        Génère la musique pour tout un épisode selon l'arc émotionnel.
        emotion_arc : ["epic","tension","triumph"] pour chaque shot
        """
        music_files = []
        for i, (emotion, duration) in enumerate(zip(emotion_arc, shot_durations)):
            self.log.info(f"[MUSICGEN] Shot {i+1}/{len(emotion_arc)} : {emotion} ({duration:.1f}s)")
            f = self.generate(emotion, duration_s=max(3, duration))
            music_files.append(f)
            time.sleep(0.5)
        return music_files


# ══════════════════════════════════════════════════════════════════════
# DIALOGUE GENERATOR
# ══════════════════════════════════════════════════════════════════════

class DialogueGenerator:
    """
    Génère les dialogues des personnages via Claude,
    puis les synthétise avec leur voix personnalisée.
    """

    def __init__(self, voice_profiles: dict[str, VoiceProfile],
                 xtts: XTTSEngine, bark: BarkEngine,
                 logger: logging.Logger = None):
        self.log      = logger or logging.getLogger("dialogue")
        self.profiles = voice_profiles
        self.xtts     = xtts
        self.bark     = bark

    def generate_dialogue(self, scene: dict,
                           characters: list[str],
                           world_context: str = "") -> list[dict]:
        """Génère les répliques d'une scène via Claude."""
        chars_str = ", ".join(characters)
        prompt = (
            f"Scène : {scene.get('description','')}\n"
            f"Émotion : {scene.get('emotion','')}\n"
            f"Personnages : {chars_str}\n"
            + (f"Contexte : {world_context}\n" if world_context else "") +
            f"\nÉcris 2-4 répliques courtes (max 15 mots chacune) pour cette scène. "
            f"Format JSON : [{{'character':'...','line':'...','emotion':'...'}}]"
        )
        result = _llm(prompt, max_tokens=300)
        try:
            if result.startswith("```"):
                result = "\n".join(result.split("\n")[1:-1])
            return json.loads(result)
        except Exception:
            return [{"character": characters[0] if characters else "?",
                     "line": scene.get("description","")[:50],
                     "emotion": scene.get("emotion","neutral")}]

    def synthesize_dialogue(self, dialogue: list[dict]) -> list[dict]:
        """Synthétise chaque réplique avec la voix du personnage."""
        results = []
        for line in dialogue:
            char    = line["character"]
            text    = line["line"]
            emotion = line.get("emotion","neutral")
            profile = self.profiles.get(char)

            if profile and profile.voice_sample:
                audio = self.xtts.synthesize(
                    text, profile.voice_sample,
                    language=profile.language
                )
            else:
                # Bark avec le type de voix par défaut
                audio = self.bark.synthesize(text, "narrator", emotion)

            results.append({**line, "audio_path": audio})
        return results


# ══════════════════════════════════════════════════════════════════════
# FAÇADE VOICE SYNTHESIS V1.40
# ══════════════════════════════════════════════════════════════════════

class VoiceSynthesisSystem:
    """Système de synthèse vocale et musicale unifié V1.40."""

    def __init__(self, logger: logging.Logger = None):
        self.log       = logger or logging.getLogger("voice_v140")
        self.xtts      = XTTSEngine(logger=self.log)
        self.bark      = BarkEngine(logger=self.log)
        self.musicgen  = MusicGenEngine(logger=self.log)
        self._profiles: dict[str, VoiceProfile] = {}
        self._load_default_profiles()

    def _load_default_profiles(self):
        """Profils de voix par défaut pour les personnalités V1.30."""
        defaults = [
            VoiceProfile("viktor",  "Viktor",  bark_preset="v2/fr_speaker_3",
                         description="voix grave et réfléchie d'un scénariste"),
            VoiceProfile("mia",     "Mia",     bark_preset="v2/fr_speaker_6",
                         description="voix enthousiaste d'une réalisatrice"),
            VoiceProfile("hiro",    "Hiro",    bark_preset="v2/fr_speaker_8",
                         description="voix technique et précise"),
            VoiceProfile("elise",   "Élise",   bark_preset="v2/fr_speaker_5",
                         description="voix directe et critique"),
        ]
        for p in defaults:
            self._profiles[p.character_id] = p

    def register_character(self, name: str,
                             reference_audio: str = "",
                             bark_preset: str = "v2/fr_speaker_0") -> VoiceProfile:
        """Enregistre un nouveau personnage avec sa voix."""
        if reference_audio and Path(reference_audio).exists():
            profile = self.xtts.clone_character_voice(name, reference_audio)
        else:
            cid = hashlib.md5(name.encode()).hexdigest()[:8]
            profile = VoiceProfile(
                character_id=cid, character_name=name,
                bark_preset=bark_preset,
            )
        self._profiles[profile.character_id] = profile
        self.log.info(f"[VOICE] Personnage enregistré : {name}")
        return profile

    def speak(self, text: str, character: str = "",
               emotion: str = "neutral") -> str:
        """Synthétise une réplique."""
        profile = self._get_profile(character)
        if profile and profile.voice_sample:
            return self.xtts.synthesize(text, profile.voice_sample)
        return self.bark.synthesize(text, "narrator", emotion)

    def compose_music(self, mood: str, duration_s: float = 8.0) -> str:
        """Compose de la musique pour un mood donné."""
        return self.musicgen.generate(mood, duration_s)

    def _get_profile(self, character: str) -> Optional[VoiceProfile]:
        for p in self._profiles.values():
            if p.character_name.lower() == character.lower():
                return p
        return None

    def get_dashboard(self) -> dict:
        return {
            "version":          "1.40_voice",
            "characters":       len(self._profiles),
            "xtts_ready":       self.xtts._ready,
            "bark_ready":       self.bark._ready,
            "musicgen_ready":   self.musicgen._ready,
            "mood_library":     list(self.musicgen.MOOD_PROMPTS.keys()),
        }


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    vs = VoiceSynthesisSystem()
    print("=== V1.40 VOICE SYNTHESIS ===")
    print(f"Personnages : {len(vs._profiles)}")
    print(f"Moods musicaux : {list(vs.musicgen.MOOD_PROMPTS.keys())}")
    print(f"\nDashboard : {vs.get_dashboard()}")

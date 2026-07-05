"""
agents/v140_voice_synthesis.py -- Ov3rLoRd V1.40 -- Voice Synthesis
Synthese vocale avancee : gTTS, ElevenLabs, Coqui TTS.
V1.49p : bug syntaxe ligne 57 corrige (dataclass_ready = True invalide),
overlord_utils centralise, context_bus connecte.
"""

import json
import logging
import os
import subprocess
import sys
from pathlib import Path
from datetime import datetime, timezone
from dataclasses import dataclass, field
from typing import Optional

try:
    from agents.overlord_utils import fallback_llm, safe_json_parse, get_api_key
    UTILS_OK = True
except ImportError:
    UTILS_OK = False
    fallback_llm = None
    get_api_key  = None

try:
    from gtts import gTTS
    GTTS_OK = True
except ImportError:
    GTTS_OK = False

try:
    import importlib.util as _importlib_util
    # Coqui (torch + TTS.api) n'est PAS importe ici : un access violation Windows
    # a ete observe de maniere reproductible quand un appel reseau (fallback_llm/
    # requests, deja importe par ce process pour DialogueAdapter) precede le
    # chargement du modele XTTS-v2 dans le meme process. La synthese tourne donc
    # dans un subprocess isole (agents/_coqui_tts_worker.py, cf. CoquiTTSSynthesizer) :
    # un crash natif y reste confine et se traduit par un code de sortie non-zero.
    COQUI_OK = (_importlib_util.find_spec("TTS") is not None
                and _importlib_util.find_spec("torch") is not None)
except Exception:
    COQUI_OK = False

try:
    from agents.context_bus import get_bus
    BUS_OK = True
except ImportError:
    BUS_OK = False

VOICE_DIR       = Path("workspace/voice_synthesis")
VOICE_REFS_DIR  = Path("workspace/voice_refs")
CLAUDE_MODEL    = "claude-sonnet-4-6"
COQUI_MODEL_NAME = "tts_models/multilingual/multi-dataset/xtts_v2"
# xtts_v2 -> codes langue courts (sous-ensemble supporte par le modele)
COQUI_LANGUAGE_MAP = {"fr": "fr", "ja": "ja", "en": "en"}
log             = logging.getLogger("voice_synthesis")


def _llm(prompt: str, system: str = "", max_tokens: int = 300) -> str:
    if UTILS_OK and fallback_llm:
        return fallback_llm(prompt, system=system, model=CLAUDE_MODEL, max_tokens=max_tokens)
    return ""


# ── Profils de voix ───────────────────────────────────────────────────
VOICE_PROFILES = {
    "hero":     {"lang":"fr","tld":"fr","slow":False},
    "villain":  {"lang":"fr","tld":"ca","slow":True},
    "narrator": {"lang":"fr","tld":"fr","slow":False},
    "child":    {"lang":"fr","tld":"fr","slow":False},
    "elder":    {"lang":"fr","tld":"fr","slow":True},
    "default":  {"lang":"fr","tld":"fr","slow":False},
}


@dataclass
class VoiceLine:
    character:  str
    text:       str
    shot_id:    str   = ""
    profile:    str   = "default"
    audio_path: str   = ""
    duration_s: float = 0.0
    generated:  bool  = False


class DialogueAdapter:

    def adapt(self, raw_dialogue: str, character: str = "",
               style: str = "anime") -> str:
        if not raw_dialogue:
            return ""
        prompt = (
            f"Adapte ce dialogue pour la synthese vocale (style {style}) :\n"
            f"Personnage : {character}\n"
            f"Dialogue : {raw_dialogue[:300]}\n\n"
            f"Retourne UNIQUEMENT le texte adapte, sans didascalies."
        )
        raw = _llm(prompt, max_tokens=150)
        return raw.strip() if raw else raw_dialogue


class GTTSSynthesizer:

    def __init__(self, logger: logging.Logger = None):
        self.log = logger or log

    def synthesize(self, text: str, output_path: str,
                    profile: str = "default") -> bool:
        if not GTTS_OK:
            self.log.warning("[VOICE] gTTS non installe -- pip install gTTS")
            return False
        try:
            p   = VOICE_PROFILES.get(profile, VOICE_PROFILES["default"])
            tts = gTTS(text=text, lang=p["lang"], tld=p["tld"], slow=p["slow"])
            tts.save(output_path)
            self.log.info(f"[VOICE] gTTS OK : {output_path}")
            return True
        except Exception as e:
            self.log.error(f"[VOICE] gTTS erreur : {e}")
            return False


class ElevenLabsSynthesizer:

    VOICE_IDS = {
        "hero":    "21m00Tcm4TlvDq8ikWAM",
        "villain": "AZnzlk1XvdvUeBnXmlld",
        "narrator":"D38z5RcWu1voky8WS1ja",
        "default": "21m00Tcm4TlvDq8ikWAM",
    }

    def __init__(self, logger: logging.Logger = None):
        self.log      = logger or log
        self._api_key = os.environ.get("ELEVENLABS_API_KEY", "")

    def synthesize(self, text: str, output_path: str,
                    character: str = "default") -> bool:
        if not self._api_key:
            return False
        try:
            import requests
            voice_id = self.VOICE_IDS.get(character, self.VOICE_IDS["default"])
            resp = requests.post(
                f"https://api.elevenlabs.io/v1/text-to-speech/{voice_id}",
                headers={"xi-api-key": self._api_key,
                         "Content-Type": "application/json"},
                json={"text": text, "model_id": "eleven_multilingual_v2",
                      "voice_settings": {"stability":0.5,"similarity_boost":0.75}},
                timeout=60
            )
            if resp.status_code == 200:
                Path(output_path).write_bytes(resp.content)
                self.log.info(f"[VOICE] ElevenLabs OK : {output_path}")
                return True
            self.log.warning(f"[VOICE] ElevenLabs HTTP {resp.status_code}")
        except Exception as e:
            self.log.warning(f"[VOICE] ElevenLabs : {e}")
        return False


def _select_coqui_device() -> str:
    """
    RTX 5080 (cuda:0) sert ComfyUI -- l'eviter pour ne pas se battre sur la VRAM.
    RTX 2070 (cuda:1) est la carte secondaire quasi inactive (meme convention
    que le pinning CUDA_VISIBLE_DEVICES=1 utilise pour Ollama). Detection via
    nvidia-smi (le process principal n'importe pas torch, cf. worker isole).
    """
    try:
        result = subprocess.run(["nvidia-smi", "-L"], capture_output=True,
                                 text=True, timeout=10)
        if result.returncode == 0:
            gpu_count = len([l for l in result.stdout.strip().splitlines() if l.strip()])
            if gpu_count > 1:
                return "cuda:1"
            if gpu_count == 1:
                return "cuda:0"
    except Exception:
        pass
    return "cpu"


class CoquiTTSSynthesizer:
    """
    Lance agents/_coqui_tts_worker.py dans un subprocess isole. Le checkpoint
    XTTS-v2 (~2 Go) est donc recharge a chaque appel (cout ~3-5s) -- accepte en
    echange de l'isolation (cf. commentaire COQUI_OK plus haut) : un crash
    natif dans le worker ne fait jamais tomber le pipeline appelant.
    """

    _WORKER_TIMEOUT_S = 120

    def __init__(self, logger: logging.Logger = None):
        self.log = logger or log

    def _resolve_speaker_wav(self, character: str) -> Optional[str]:
        candidate = VOICE_REFS_DIR / f"{character}.wav"
        if candidate.exists():
            return str(candidate)
        default_ref = VOICE_REFS_DIR / "default.wav"
        if default_ref.exists():
            return str(default_ref)
        return None

    def synthesize(self, text: str, output_path: str,
                    character: str = "default", profile: str = "default") -> bool:
        if not COQUI_OK:
            self.log.warning("[VOICE] Coqui TTS non installe -- pip install coqui-tts")
            return False
        speaker_wav = self._resolve_speaker_wav(character)
        if speaker_wav is None:
            self.log.warning(f"[VOICE] Coqui : aucune reference vocale pour '{character}' "
                              f"(attendu : {VOICE_REFS_DIR}/{character}.wav ou default.wav)")
            return False
        p        = VOICE_PROFILES.get(profile, VOICE_PROFILES["default"])
        language = COQUI_LANGUAGE_MAP.get(p["lang"], "fr")
        device   = _select_coqui_device()
        worker   = str(Path(__file__).resolve().parent / "_coqui_tts_worker.py")
        try:
            result = subprocess.run(
                [sys.executable, worker, output_path, speaker_wav, language, device],
                input=text, capture_output=True, text=True, encoding="utf-8",
                env={**os.environ, "PYTHONIOENCODING": "utf-8"},
                timeout=self._WORKER_TIMEOUT_S,
            )
            if result.returncode == 0 and Path(output_path).exists():
                self.log.info(f"[VOICE] Coqui XTTS-v2 OK (worker isole, {device}) : {output_path}")
                return True
            self.log.error(f"[VOICE] Coqui worker echec (code {result.returncode}) : "
                            f"{result.stderr[-500:]}")
        except subprocess.TimeoutExpired:
            self.log.error(f"[VOICE] Coqui worker timeout ({self._WORKER_TIMEOUT_S}s)")
        except Exception as e:
            self.log.error(f"[VOICE] Coqui erreur : {e}")
        return False


class VoiceSynthesisV140:

    def __init__(self, logger: logging.Logger = None):
        self.log        = logger or log
        self.adapter    = DialogueAdapter()
        self.coqui      = CoquiTTSSynthesizer(logger=self.log)
        self.gtts       = GTTSSynthesizer(logger=self.log)
        self.elevenlabs = ElevenLabsSynthesizer(logger=self.log)
        VOICE_DIR.mkdir(parents=True, exist_ok=True)

    def synthesize_line(self, line: VoiceLine,
                         prefer_quality: bool = False) -> VoiceLine:
        if not line.text:
            return line
        ts       = datetime.now(tz=timezone.utc).strftime("%Y%m%d_%H%M%S_%f")
        out_path = str(VOICE_DIR / f"{line.shot_id or 'line'}_{ts}.mp3")
        adapted  = self.adapter.adapt(line.text, character=line.character)
        success  = False
        if prefer_quality:
            success = self.elevenlabs.synthesize(adapted, out_path, line.character)
        if not success:
            success = self.coqui.synthesize(adapted, out_path, line.character, line.profile)
        if not success:
            success = self.gtts.synthesize(adapted, out_path, line.profile)
        if success:
            line.audio_path = out_path
            line.generated  = True
            if BUS_OK:
                try:
                    get_bus().write(f"voice.{line.shot_id}", out_path,
                                    agent_id="voice_synthesis")
                except Exception:
                    pass
        return line

    def synthesize_script(self, dialogue_lines: list[dict],
                            prefer_quality: bool = False) -> list[VoiceLine]:
        results = []
        for d in dialogue_lines:
            line = VoiceLine(
                character = d.get("character","narrator"),
                text      = d.get("text",""),
                shot_id   = d.get("shot_id",""),
                profile   = d.get("profile","default"),
            )
            results.append(self.synthesize_line(line, prefer_quality))
        generated = sum(1 for l in results if l.generated)
        self.log.info(f"[VOICE] {generated}/{len(results)} lignes synthetisees")
        if BUS_OK:
            try:
                get_bus().write("voice.lines_generated", generated,
                                agent_id="voice_synthesis")
                get_bus().write("voice.lines_total",     len(results),
                                agent_id="voice_synthesis")
            except Exception:
                pass
        return results

    def get_audio_map(self, lines: list[VoiceLine]) -> dict:
        return {l.shot_id: l.audio_path for l in lines if l.generated and l.shot_id}


if __name__ == "__main__":
    import io
    if hasattr(sys.stdout, "buffer"):
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    logging.basicConfig(level=logging.INFO)
    vs = VoiceSynthesisV140()
    print(f"gTTS disponible       : {GTTS_OK}")
    print(f"Coqui TTS disponible  : {COQUI_OK}")
    print(f"ElevenLabs disponible : {bool(vs.elevenlabs._api_key)}")
    print("VoiceSynthesisV140 OK")
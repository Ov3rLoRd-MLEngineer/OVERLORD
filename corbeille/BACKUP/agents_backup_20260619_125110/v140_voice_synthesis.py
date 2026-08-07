"""
agents/v140_voice_synthesis.py -- Ov3rLoRd V1.40 -- Voice Synthesis
Synthese vocale avancee : gTTS, ElevenLabs, Coqui TTS.
V1.49p : bug syntaxe ligne 57 corrige (dataclass_ready = True invalide),
overlord_utils centralise, context_bus connecte.
"""

import json
import logging
import os
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
    from agents.context_bus import get_bus
    BUS_OK = True
except ImportError:
    BUS_OK = False

VOICE_DIR    = Path("workspace/voice_synthesis")
CLAUDE_MODEL = "claude-sonnet-4-6"
log          = logging.getLogger("voice_synthesis")


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


class VoiceSynthesisV140:

    def __init__(self, logger: logging.Logger = None):
        self.log        = logger or log
        self.adapter    = DialogueAdapter()
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
    import sys, io
    if hasattr(sys.stdout, "buffer"):
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    logging.basicConfig(level=logging.INFO)
    vs = VoiceSynthesisV140()
    print(f"gTTS disponible       : {GTTS_OK}")
    print(f"ElevenLabs disponible : {bool(vs.elevenlabs._api_key)}")
    print("VoiceSynthesisV140 OK")
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
agents/_coqui_tts_worker.py -- Ov3rLoRd -- worker isole pour la synthese XTTS-v2.

Execute dans un subprocess dedie, sans import de agents.overlord_utils/requests :
un access violation Windows a ete observe de maniere reproductible quand un
appel reseau (fallback_llm) precede le chargement du modele XTTS-v2 dans le
meme process (allocation des tenseurs GPT2). L'isolation garantit qu'un crash
natif ici n'emporte pas le pipeline -- code de sortie non-zero => le process
appelant (CoquiTTSSynthesizer) bascule sur gTTS.

Usage : python -m agents._coqui_tts_worker <output_path> <speaker_wav> <language> <device>
Le texte a synthetiser est lu sur stdin (evite les soucis d'encodage/quoting
en argument de ligne de commande).
"""

import os
import sys
from pathlib import Path

os.environ.setdefault("HF_HUB_OFFLINE", "1")
os.environ.setdefault("HF_HUB_DISABLE_TELEMETRY", "1")

COQUI_MODEL_NAME = "tts_models/multilingual/multi-dataset/xtts_v2"


def _register_ffmpeg_dll_dirs() -> None:
    """cf. commentaire jumeau dans agents/voice_synthesis.py."""
    if os.name != "nt" or not hasattr(os, "add_dll_directory"):
        return
    candidates = []
    override = os.environ.get("OVERLORD_FFMPEG_SHARED_BIN")
    if override:
        candidates.append(Path(override))
    winget_pkgs = Path(os.environ.get("LOCALAPPDATA", "")) / "Microsoft" / "WinGet" / "Packages"
    if winget_pkgs.is_dir():
        candidates += list(winget_pkgs.glob("BtbN.FFmpeg.*Shared*/*/bin"))
    for c in candidates:
        if c.is_dir() and any(c.glob("avcodec-*.dll")):
            try:
                os.add_dll_directory(str(c))
            except OSError:
                pass


def main() -> int:
    if len(sys.argv) != 5:
        print("usage: _coqui_tts_worker.py <output_path> <speaker_wav> <language> <device>",
              file=sys.stderr)
        return 2
    output_path, speaker_wav, language, device = sys.argv[1:5]
    text = sys.stdin.read()
    if not text.strip():
        print("texte vide", file=sys.stderr)
        return 2

    _register_ffmpeg_dll_dirs()
    from TTS.api import TTS

    model = TTS(COQUI_MODEL_NAME).to(device)
    model.tts_to_file(text=text, speaker_wav=speaker_wav,
                       language=language, file_path=output_path)
    return 0


if __name__ == "__main__":
    sys.exit(main())

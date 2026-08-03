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
agents/audio_compositor.py — Compositeur Audio V1.70
Synchronise et mixe les pistes audio pour la vidéo finale.

Pistes :
  - Voix (Blue Yeti → prise .wav)
  - Musique de fond (libre de droits ou IA)
  - Effets sonores (impacts, whoosh, transitions)
  - Ambiance (pluie, ville, espace...)

Toutes les opérations via ffmpeg.

Usage :
  python agents/audio_compositor.py --video scene.mp4 --voice voice.wav
  python agents/audio_compositor.py --mix --voice v.wav --music bgm.mp3
  python agents/audio_compositor.py --add-sfx impact --at 00:00:03.5
"""

import subprocess
import sys
import io
import logging
import json
from pathlib import Path
from datetime import datetime

if hasattr(sys.stdout, 'buffer'):
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

AUDIO_DIR  = Path("workspace/audio")
SFX_DIR    = Path("workspace/audio/sfx")
VOICE_DIR  = Path("workspace/audio/voice")
MUSIC_DIR  = Path("workspace/audio/music")
MIX_DIR    = Path("workspace/audio/mix")

# Sources de musique libre de droits recommandées
FREE_MUSIC_SOURCES = {
    "freemusicarchive": "https://freemusicarchive.org",
    "musescore":        "https://musescore.com (MIDI → WAV)",
    "pixabay":          "https://pixabay.com/music/",
    "incompetech":      "https://incompetech.com",
    "zapsplat":         "https://www.zapsplat.com",
}

# Niveaux audio standard
AUDIO_LEVELS = {
    "voice":   -6,   # dB — voix au premier plan
    "music":   -18,  # dB — musique en retrait
    "sfx":     -10,  # dB — effets sonores
    "ambiance":-24,  # dB — ambiance très en retrait
}


def normalize_audio(input_path: Path, output_path: Path = None,
                     target_db: float = -16.0,
                     logger=None) -> Path | None:
    """Normalise le volume d'une piste audio."""
    log = logger or logging.getLogger("audio_compositor")

    if output_path is None:
        AUDIO_DIR.mkdir(parents=True, exist_ok=True)
        output_path = AUDIO_DIR / f"norm_{input_path.stem}.wav"

    try:
        subprocess.run([
            "ffmpeg", "-y", "-i", str(input_path),
            "-af", f"loudnorm=I={target_db}:TP=-1.5:LRA=11",
            str(output_path)
        ], capture_output=True, timeout=120, check=True)
        log.info(f"[AUDIO] Normalisé → {output_path.name}")
        return output_path
    except Exception as e:
        log.error(f"[AUDIO] Normalisation : {e}")
        return None


def mix_tracks(voice: Path = None, music: Path = None,
               sfx_list: list = None, ambiance: Path = None,
               output_path: Path = None, logger=None) -> Path | None:
    """
    Mixe toutes les pistes audio selon les niveaux standard.
    Voix au premier plan, musique en retrait.
    """
    log = logger or logging.getLogger("audio_compositor")
    MIX_DIR.mkdir(parents=True, exist_ok=True)

    if output_path is None:
        ts          = datetime.now().strftime("%Y%m%d_%H%M%S")
        output_path = MIX_DIR / f"mix_{ts}.wav"

    inputs   = []
    filters  = []
    n        = 0

    if voice and Path(str(voice)).exists():
        inputs  += ["-i", str(voice)]
        filters.append(f"[{n}:a]volume={AUDIO_LEVELS['voice']}dB[v{n}]")
        n += 1

    if music and Path(str(music)).exists():
        inputs  += ["-i", str(music)]
        filters.append(f"[{n}:a]volume={AUDIO_LEVELS['music']}dB[v{n}]")
        n += 1

    if ambiance and Path(str(ambiance)).exists():
        inputs  += ["-i", str(ambiance)]
        filters.append(f"[{n}:a]volume={AUDIO_LEVELS['ambiance']}dB[v{n}]")
        n += 1

    if n == 0:
        log.error("[AUDIO] Aucune piste fournie")
        return None

    # Mixer toutes les pistes
    mix_inputs = "".join(f"[v{i}]" for i in range(n))
    filters.append(f"{mix_inputs}amix=inputs={n}:duration=longest[aout]")
    filter_complex = ";".join(filters)

    cmd = ["ffmpeg", "-y"] + inputs + [
        "-filter_complex", filter_complex,
        "-map", "[aout]",
        "-c:a", "pcm_s16le", "-ar", "48000",
        str(output_path)
    ]

    try:
        subprocess.run(cmd, capture_output=True, timeout=300, check=True)
        log.info(f"[AUDIO] Mix ✓ → {output_path.name}")
        return output_path
    except Exception as e:
        log.error(f"[AUDIO] Mix erreur : {e}")
        return None


def add_audio_to_video(video_path: Path, audio_path: Path,
                        output_path: Path = None,
                        audio_offset: float = 0.0,
                        logger=None) -> Path | None:
    """Ajoute la piste audio à la vidéo."""
    log = logger or logging.getLogger("audio_compositor")

    if output_path is None:
        MIX_DIR.mkdir(parents=True, exist_ok=True)
        output_path = MIX_DIR / f"{video_path.stem}_audio.mp4"

    delay_filter = f"adelay={int(audio_offset*1000)}|{int(audio_offset*1000)}" \
                   if audio_offset > 0 else "anull"

    try:
        subprocess.run([
            "ffmpeg", "-y",
            "-i", str(video_path),
            "-i", str(audio_path),
            "-af", delay_filter,
            "-c:v", "copy",
            "-c:a", "aac", "-b:a", "192k",
            "-shortest",
            str(output_path)
        ], capture_output=True, timeout=300, check=True)
        log.info(f"[AUDIO] Vidéo+Audio ✓ → {output_path.name}")
        return output_path
    except Exception as e:
        log.error(f"[AUDIO] Ajout audio : {e}")
        return None


def extract_audio(video_path: Path, output_path: Path = None,
                   logger=None) -> Path | None:
    """Extrait la piste audio d'une vidéo."""
    log = logger or logging.getLogger("audio_compositor")

    if output_path is None:
        AUDIO_DIR.mkdir(parents=True, exist_ok=True)
        output_path = AUDIO_DIR / f"{Path(video_path).stem}_audio.wav"

    try:
        subprocess.run([
            "ffmpeg", "-y", "-i", str(video_path),
            "-vn", "-c:a", "pcm_s16le", "-ar", "48000",
            str(output_path)
        ], capture_output=True, timeout=120, check=True)
        log.info(f"[AUDIO] Extrait → {output_path.name}")
        return output_path
    except Exception as e:
        log.error(f"[AUDIO] Extraction : {e}")
        return None


def generate_silence(duration_s: float, output_path: Path = None,
                      logger=None) -> Path | None:
    """Génère un fichier de silence (utile pour synchronisation)."""
    log = logger or logging.getLogger("audio_compositor")

    if output_path is None:
        AUDIO_DIR.mkdir(parents=True, exist_ok=True)
        output_path = AUDIO_DIR / f"silence_{duration_s}s.wav"

    try:
        subprocess.run([
            "ffmpeg", "-y",
            "-f", "lavfi", "-i", f"anullsrc=r=48000:cl=stereo",
            "-t", str(duration_s),
            "-c:a", "pcm_s16le",
            str(output_path)
        ], capture_output=True, timeout=60, check=True)
        return output_path
    except Exception as e:
        log.error(f"[AUDIO] Silence : {e}")
        return None


def build_demo_audio_plan() -> dict:
    """Plan audio pour la démo 2 minutes."""
    return {
        "opening_15s": {
            "music":    "bgm_epic_intro.mp3 (libre droits — incompetech.com)",
            "voice":    None,
            "sfx":      ["whoosh_logo", "impact_title"],
            "volume":   {"music": -12, "sfx": -8},
        },
        "scene_eva_30s": {
            "music":    "bgm_battle_tension.mp3",
            "voice":    "voice_asuka_battle.wav (Blue Yeti)",
            "sfx":      ["impact_01", "explosion_01", "energy_charge"],
            "volume":   {"music": -18, "voice": -6, "sfx": -10},
        },
        "scene_gundam_30s": {
            "music":    "bgm_space_epic.mp3",
            "voice":    "voice_gundam.wav (Blue Yeti)",
            "sfx":      ["beam_sabre", "thruster", "explosion_space"],
            "volume":   {"music": -18, "voice": -6, "sfx": -10},
        },
        "scene_miku_30s": {
            "music":    "bgm_miku_electronic.mp3",
            "voice":    "voice_miku_modulated.wav (Blue Yeti + modulateur)",
            "sfx":      ["glowstick_crowd", "stage_light", "confetti"],
            "volume":   {"music": -14, "voice": -8, "sfx": -12},
        },
        "ending_15s": {
            "music":    "bgm_epic_outro.mp3",
            "voice":    "voice_narrator_fr.wav",
            "sfx":      ["impact_final"],
            "volume":   {"music": -12, "voice": -6, "sfx": -8},
        },
        "sources_libres": FREE_MUSIC_SOURCES,
        "blue_yeti_tips": [
            "Mode cardioïde (icône cœur) pour voix solo",
            "Gain à 50% — ajuster selon distance micro",
            "Pop filter recommandé pour les plosives",
            "Enregistrer à 48kHz/24bit pour la prod",
            "Modulateur : changer la hauteur sans affecter la prosodie",
        ]
    }


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Ov3rLoRd Audio Compositor V1.70")
    parser.add_argument("--video",    type=str)
    parser.add_argument("--voice",    type=str)
    parser.add_argument("--music",    type=str)
    parser.add_argument("--output",   type=str)
    parser.add_argument("--mix",      action="store_true")
    parser.add_argument("--plan",     action="store_true")
    parser.add_argument("--normalize",type=str)
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO,
                        format="%(asctime)s [%(levelname)s] %(message)s")

    if args.plan:
        plan = build_demo_audio_plan()
        print(json.dumps(plan, indent=2, ensure_ascii=False))

    elif args.normalize:
        out = normalize_audio(Path(args.normalize))
        print(f"Normalisé : {out}")

    elif args.mix:
        out = mix_tracks(
            voice   = Path(args.voice)  if args.voice  else None,
            music   = Path(args.music)  if args.music  else None,
            output_path = Path(args.output) if args.output else None,
        )
        print(f"Mix : {out}")

    elif args.video and args.voice:
        mix = mix_tracks(
            voice = Path(args.voice),
            music = Path(args.music) if args.music else None,
        )
        if mix:
            out = add_audio_to_video(
                Path(args.video), mix,
                output_path=Path(args.output) if args.output else None
            )
            print(f"Vidéo finale : {out}")

    else:
        print("=== Audio Compositor V1.70 ===")
        print("\nPlan audio démo :")
        print("  python agents/audio_compositor.py --plan")
        print("\nMixer voix + musique :")
        print("  python agents/audio_compositor.py --mix --voice v.wav --music bgm.mp3")
        print("\nAjouter audio à vidéo :")
        print("  python agents/audio_compositor.py --video scene.mp4 --voice v.wav")
        print(f"\nSources musique libre :")
        for name, url in FREE_MUSIC_SOURCES.items():
            print(f"  {url}")

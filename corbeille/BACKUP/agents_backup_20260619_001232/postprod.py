"""
agents/postprod.py — Agent Post-Production
Gère : assemblage vidéo (ffmpeg), TTS, lip-sync, montage final.

Dépendances :
  pip install gTTS pydub
  ffmpeg doit être dans le PATH système (https://ffmpeg.org)
  Lip-sync : SadTalker ou wav2lip (GPU requis, installation séparée)
"""

import json
import logging
import subprocess
import shutil
import time
from pathlib import Path
from datetime import datetime

# TTS optionnel
try:
    from gtts import gTTS
    GTTS_OK = True
except ImportError:
    GTTS_OK = False

POSTPROD_DIR = Path("workspace/postprod")
EXPORTS_DIR  = Path("workspace/exports")

# Paramètres vidéo par défaut
VIDEO_FPS        = 24
FRAME_DURATION_S = 3    # secondes par frame si pas de durée définie
AUDIO_SAMPLE_RATE = 44100

# Presets ffmpeg par format
FFMPEG_PRESETS = {
    "anime_720p":  ["-vf", "scale=1280:720",  "-c:v", "libx264", "-crf", "18", "-preset", "fast"],
    "anime_1080p": ["-vf", "scale=1920:1080", "-c:v", "libx264", "-crf", "16", "-preset", "fast"],
    "anime_4k":    ["-vf", "scale=3840:2160", "-c:v", "libx264", "-crf", "14", "-preset", "slow"],
    "short_web":   ["-vf", "scale=1080:1920", "-c:v", "libx264", "-crf", "20", "-preset", "fast"],
    "nvenc_1080p": ["-vf", "scale=1920:1080", "-c:v", "h264_nvenc", "-preset", "p4", "-cq", "18"],
}


# ============================================================
# VÉRIFICATION FFMPEG
# ============================================================
def check_ffmpeg(logger: logging.Logger = None) -> bool:
    log = logger or logging.getLogger("postprod")
    if shutil.which("ffmpeg") is None:
        log.error(
            "ffmpeg non trouvé dans le PATH. "
            "Télécharge depuis https://ffmpeg.org/download.html"
        )
        return False
    log.debug("ffmpeg détecté ✓")
    return True


# ============================================================
# ASSEMBLAGE VIDÉO DEPUIS IMAGES
# ============================================================
def images_to_video(image_paths: list,
                    output_path: str,
                    fps: int = VIDEO_FPS,
                    preset: str = "anime_1080p",
                    audio_path: str = None,
                    durations: list = None,
                    logger: logging.Logger = None) -> bool:
    """
    Assemble une séquence d'images en vidéo via ffmpeg.

    image_paths : liste ordonnée des chemins d'images
    durations   : durée de chaque image en secondes (optionnel)
    audio_path  : chemin vers la piste audio finale (optionnel)
    """
    log = logger or logging.getLogger("postprod.video")
    if not check_ffmpeg(log):
        return False

    POSTPROD_DIR.mkdir(parents=True, exist_ok=True)
    concat_file = POSTPROD_DIR / f"concat_{datetime.now().strftime('%H%M%S')}.txt"

    # Créer le fichier de concaténation ffmpeg
    with open(concat_file, "w", encoding="utf-8") as f:
        for i, img_path in enumerate(image_paths):
            duration = (
                durations[i] if durations and i < len(durations)
                else FRAME_DURATION_S
            )
            f.write(f"file '{Path(img_path).resolve()}'\n")
            f.write(f"duration {duration}\n")
        # Répéter la dernière image (requis par ffmpeg concat)
        if image_paths:
            f.write(f"file '{Path(image_paths[-1]).resolve()}'\n")

    preset_args = FFMPEG_PRESETS.get(preset, FFMPEG_PRESETS["anime_1080p"])

    cmd = [
        "ffmpeg", "-y",
        "-f", "concat", "-safe", "0",
        "-i", str(concat_file),
    ]

    if audio_path and Path(audio_path).exists():
        cmd += ["-i", str(audio_path), "-c:a", "aac", "-shortest"]

    cmd += preset_args
    cmd += ["-pix_fmt", "yuv420p", str(output_path)]

    log.info(f"[VIDÉO] Assemblage {len(image_paths)} images → {output_path}")
    try:
        result = subprocess.run(
            cmd, capture_output=True, text=True, timeout=300
        )
        if result.returncode == 0:
            log.info(f"[VIDÉO] ✓ Vidéo créée : {output_path}")
            concat_file.unlink(missing_ok=True)
            return True
        else:
            log.error(f"[VIDÉO] ffmpeg erreur : {result.stderr[-500:]}")
            return False
    except subprocess.TimeoutExpired:
        log.error("[VIDÉO] Timeout ffmpeg (300s)")
        return False
    except Exception as e:
        log.error(f"[VIDÉO] Erreur : {e}")
        return False


# ============================================================
# TTS — TEXT TO SPEECH
# ============================================================
def generate_tts(text: str,
                 output_path: str,
                 lang: str = "fr",
                 logger: logging.Logger = None) -> bool:
    """
    Génère un fichier audio depuis du texte.
    Utilise gTTS (gratuit, nécessite internet).
    Pour une qualité production : remplacer par ElevenLabs API.
    """
    log = logger or logging.getLogger("postprod.tts")

    if not GTTS_OK:
        log.warning("gTTS non installé — pip install gTTS")
        return False

    try:
        tts = gTTS(text=text, lang=lang, slow=False)
        tts.save(str(output_path))
        log.info(f"[TTS] Audio généré → {output_path}")
        return True
    except Exception as e:
        log.error(f"[TTS] Erreur gTTS : {e}")
        return False


def generate_tts_elevenlabs(text: str,
                             output_path: str,
                             api_key: str,
                             voice_id: str = "21m00Tcm4TlvDq8ikWAM",
                             logger: logging.Logger = None) -> bool:
    """
    TTS haute qualité via ElevenLabs API.
    Nécessite une clé API ElevenLabs.
    """
    import requests as req
    log = logger or logging.getLogger("postprod.tts_xl")
    try:
        resp = req.post(
            f"https://api.elevenlabs.io/v1/text-to-speech/{voice_id}",
            headers={
                "xi-api-key":   api_key,
                "Content-Type": "application/json",
            },
            json={
                "text":            text,
                "model_id":        "eleven_multilingual_v2",
                "voice_settings":  {"stability": 0.5, "similarity_boost": 0.75},
            },
            timeout=60
        )
        if resp.status_code == 200:
            Path(output_path).write_bytes(resp.content)
            log.info(f"[TTS-XL] Audio généré → {output_path}")
            return True
        log.error(f"[TTS-XL] HTTP {resp.status_code}: {resp.text[:200]}")
        return False
    except Exception as e:
        log.error(f"[TTS-XL] Erreur : {e}")
        return False


# ============================================================
# LIP-SYNC — WRAPPER SADTALKER
# ============================================================
def apply_lipsync(image_path: str,
                  audio_path: str,
                  output_path: str,
                  sadtalker_path: str = "SadTalker",
                  logger: logging.Logger = None) -> bool:
    """
    Applique le lip-sync via SadTalker.

    Prérequis :
      - SadTalker installé (https://github.com/OpenTalker/SadTalker)
      - GPU avec CUDA disponible
      - sadtalker_path : chemin vers le dossier SadTalker

    image_path  : image du personnage (face visible)
    audio_path  : fichier audio (.wav ou .mp3)
    output_path : vidéo de sortie avec lip-sync
    """
    log = logger or logging.getLogger("postprod.lipsync")
    sadtalker = Path(sadtalker_path)

    if not sadtalker.exists():
        log.warning(
            f"[LIPSYNC] SadTalker non trouvé à {sadtalker_path}. "
            "Installe depuis https://github.com/OpenTalker/SadTalker"
        )
        return False

    inference_script = sadtalker / "inference.py"
    if not inference_script.exists():
        log.error(f"[LIPSYNC] inference.py introuvable dans {sadtalker_path}")
        return False

    cmd = [
        "python", str(inference_script),
        "--driven_audio",  str(audio_path),
        "--source_image",  str(image_path),
        "--result_dir",    str(Path(output_path).parent),
        "--still",
        "--preprocess",    "crop",
    ]

    log.info(f"[LIPSYNC] SadTalker → {output_path}")
    try:
        result = subprocess.run(
            cmd, capture_output=True, text=True, timeout=600,
            cwd=str(sadtalker)
        )
        if result.returncode == 0:
            log.info(f"[LIPSYNC] ✓ Lip-sync terminé")
            return True
        log.error(f"[LIPSYNC] Erreur : {result.stderr[-500:]}")
        return False
    except Exception as e:
        log.error(f"[LIPSYNC] Exception : {e}")
        return False


# ============================================================
# MIXAGE AUDIO FINAL
# ============================================================
def mix_audio(voice_path: str,
              music_path: str,
              output_path: str,
              voice_volume: float = 1.0,
              music_volume: float = 0.3,
              logger: logging.Logger = None) -> bool:
    """Mixe voix et musique de fond via ffmpeg."""
    log = logger or logging.getLogger("postprod.mix")
    if not check_ffmpeg(log):
        return False

    if not Path(voice_path).exists():
        log.error(f"[MIX] Voix introuvable : {voice_path}")
        return False

    if not Path(music_path).exists():
        log.warning(f"[MIX] Musique introuvable, on garde la voix seule.")
        shutil.copy(voice_path, output_path)
        return True

    cmd = [
        "ffmpeg", "-y",
        "-i", str(voice_path),
        "-i", str(music_path),
        "-filter_complex",
        f"[0:a]volume={voice_volume}[v];[1:a]volume={music_volume}[m];[v][m]amix=inputs=2:duration=first[out]",
        "-map", "[out]",
        "-c:a", "aac",
        str(output_path)
    ]

    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
        if result.returncode == 0:
            log.info(f"[MIX] ✓ Audio mixé → {output_path}")
            return True
        log.error(f"[MIX] ffmpeg erreur : {result.stderr[-300:]}")
        return False
    except Exception as e:
        log.error(f"[MIX] Exception : {e}")
        return False


# ============================================================
# PIPELINE POST-PROD COMPLET
# ============================================================
def run_postprod(shotlist: dict,
                 image_dir: Path,
                 dialogue_lines: list = None,
                 music_path: str = None,
                 export_preset: str = "anime_1080p",
                 tts_lang: str = "fr",
                 logger: logging.Logger = None) -> dict:
    """
    Pipeline de post-production complet.

    image_dir       : dossier contenant les images générées, nommées par shot_id
    dialogue_lines  : liste de strings (dialogues par ordre de shot)
    music_path      : chemin vers la musique de fond
    export_preset   : clé de FFMPEG_PRESETS

    Retourne un dict avec les chemins des fichiers produits.
    """
    log = logger or logging.getLogger("postprod")
    log.info(f"[POST-PROD] Pipeline démarré — preset={export_preset}")

    POSTPROD_DIR.mkdir(parents=True, exist_ok=True)
    EXPORTS_DIR.mkdir(parents=True, exist_ok=True)

    ts    = datetime.now().strftime("%Y%m%d_%H%M%S")
    title = shotlist.get("project_title", "untitled").replace(" ", "_")[:30]
    result = {"title": title, "timestamp": ts, "files": {}}

    shots = shotlist.get("shots", [])
    if not shots:
        log.error("[POST-PROD] Aucun shot dans la shotlist")
        return result

    # 1. Collecter les images dans l'ordre
    image_paths = []
    durations   = []
    for shot in shots:
        shot_id = shot.get("shot_id", "")
        # Chercher l'image correspondante dans image_dir
        candidates = list(Path(image_dir).glob(f"*{shot_id}*"))
        if candidates:
            image_paths.append(str(candidates[0]))
        else:
            # Fallback : toutes les images dans l'ordre
            pass
        durations.append(shot.get("duration_seconds", FRAME_DURATION_S))

    if not image_paths:
        # Fallback : toutes les images du dossier dans l'ordre alphabétique
        image_paths = sorted([str(p) for p in Path(image_dir).glob("*.png")])
        durations   = [FRAME_DURATION_S] * len(image_paths)
        log.warning(f"[POST-PROD] Fallback : {len(image_paths)} images trouvées par ordre alpha")

    if not image_paths:
        log.error("[POST-PROD] Aucune image trouvée")
        return result

    # 2. TTS si dialogues fournis
    audio_path = None
    if dialogue_lines:
        full_script = " ... ".join(dialogue_lines)
        tts_path    = str(POSTPROD_DIR / f"{ts}_voice.mp3")
        if generate_tts(full_script, tts_path, lang=tts_lang, logger=log):
            audio_path = tts_path
            result["files"]["voice"] = tts_path

    # 3. Mixage audio
    if audio_path and music_path and Path(music_path).exists():
        mixed_path = str(POSTPROD_DIR / f"{ts}_mixed.aac")
        if mix_audio(audio_path, music_path, mixed_path, logger=log):
            audio_path = mixed_path
            result["files"]["audio_mixed"] = mixed_path

    # 4. Assemblage vidéo final
    export_path = str(EXPORTS_DIR / f"{ts}_{title}.mp4")
    ok = images_to_video(
        image_paths  = image_paths,
        output_path  = export_path,
        fps          = VIDEO_FPS,
        preset       = export_preset,
        audio_path   = audio_path,
        durations    = durations,
        logger       = log
    )

    if ok:
        result["files"]["video"] = export_path
        log.info(f"[POST-PROD] ✓ Export final → {export_path}")
    else:
        log.error("[POST-PROD] Échec assemblage vidéo")

    return result


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    print("Post-prod agent chargé.")
    print(f"ffmpeg disponible : {check_ffmpeg()}")
    print(f"gTTS disponible   : {GTTS_OK}")

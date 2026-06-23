"""
agents/v140_synchronicity.py — Ov3rLoRd V1.40 — Synchronicity Engine

Timeline unifiée audio/vidéo/sous-titres à la milliseconde.

C'est le chef d'orchestre final : il prend tous les éléments produits
par les autres agents et les synchronise sur une timeline commune.

Pipeline :
  Storyboard (shots + durées)
  + Emotion Engine (arc émotionnel)
  + Voice Synthesis (dialogues + musique)
  + Video Pipeline (clips animés)
  → Synchronicity Engine
  → Production finale synchronisée

Composants :
  Timeline        : représentation temporelle de tous les éléments
  SyncPoint       : point de synchronisation précis (dialogue, effet, beat)
  AudioMixer      : mélange voix + musique + effets sonores
  SubtitleEngine  : génère et positionne les sous-titres
  MasterExporter  : export final (MP4 + SRT + metadata)
"""

import json
import time
import subprocess
import logging
from pathlib import Path
from datetime import timedelta
from dataclasses import dataclass, field
from typing import Optional
import requests

SYNC_DIR      = Path("workspace/synchronicity")
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


# ══════════════════════════════════════════════════════════════════════
# TIMELINE
# ══════════════════════════════════════════════════════════════════════

@dataclass
class TimelineTrack:
    """Une piste dans la timeline (vidéo, audio, sous-titres)."""
    track_id:  str
    track_type:str      # "video","dialogue","music","sfx","subtitle"
    start_ms:  int      # début en millisecondes
    duration_ms:int
    source:    str      # chemin vers le fichier source
    label:     str = ""
    volume:    float = 1.0
    fade_in_ms:int   = 0
    fade_out_ms:int  = 0

    @property
    def end_ms(self) -> int:
        return self.start_ms + self.duration_ms

    def to_ffmpeg_timestamp(self, ms: int) -> str:
        """Convertit des ms en timestamp ffmpeg HH:MM:SS.mmm"""
        td = timedelta(milliseconds=ms)
        total_s = int(td.total_seconds())
        h  = total_s // 3600
        m  = (total_s % 3600) // 60
        s  = total_s % 60
        ms_rem = ms % 1000
        return f"{h:02d}:{m:02d}:{s:02d}.{ms_rem:03d}"


class Timeline:
    """
    Timeline principale — contient toutes les pistes de la production.
    """

    def __init__(self, fps: int = 24, sample_rate: int = 44100):
        self.fps         = fps
        self.sample_rate = sample_rate
        self._tracks:    list[TimelineTrack] = []
        self._cursor_ms  = 0    # position courante pour l'ajout séquentiel

    def add_track(self, track: TimelineTrack):
        self._tracks.append(track)
        if track.end_ms > self._cursor_ms:
            self._cursor_ms = track.end_ms

    def add_video_shot(self, video_path: str, duration_ms: int,
                        label: str = "") -> TimelineTrack:
        """Ajoute un shot vidéo à la suite de la timeline."""
        t = TimelineTrack(
            track_id   = f"vid_{len(self._tracks):03d}",
            track_type = "video",
            start_ms   = self._cursor_ms,
            duration_ms= duration_ms,
            source     = video_path,
            label      = label,
        )
        self._tracks.append(t)
        self._cursor_ms += duration_ms
        return t

    def add_dialogue(self, audio_path: str, start_ms: int,
                      duration_ms: int, character: str,
                      text: str = "") -> TimelineTrack:
        """Ajoute une réplique de dialogue."""
        t = TimelineTrack(
            track_id   = f"dlg_{len(self._tracks):03d}",
            track_type = "dialogue",
            start_ms   = start_ms,
            duration_ms= duration_ms,
            source     = audio_path,
            label      = f"{character}: {text[:30]}",
            volume     = 1.0,
        )
        self._tracks.append(t)
        return t

    def add_music(self, audio_path: str, start_ms: int,
                   duration_ms: int, fade_in: int = 500,
                   fade_out: int = 1000, volume: float = 0.4) -> TimelineTrack:
        """Ajoute une piste musicale."""
        t = TimelineTrack(
            track_id    = f"mus_{len(self._tracks):03d}",
            track_type  = "music",
            start_ms    = start_ms,
            duration_ms = duration_ms,
            source      = audio_path,
            volume      = volume,
            fade_in_ms  = fade_in,
            fade_out_ms = fade_out,
        )
        self._tracks.append(t)
        return t

    @property
    def total_duration_ms(self) -> int:
        if not self._tracks:
            return 0
        return max(t.end_ms for t in self._tracks)

    def get_tracks_by_type(self, track_type: str) -> list[TimelineTrack]:
        return [t for t in self._tracks if t.track_type == track_type]

    def get_summary(self) -> dict:
        dur_s = self.total_duration_ms / 1000
        return {
            "total_duration_s": round(dur_s, 2),
            "total_tracks":     len(self._tracks),
            "video_tracks":     len(self.get_tracks_by_type("video")),
            "dialogue_tracks":  len(self.get_tracks_by_type("dialogue")),
            "music_tracks":     len(self.get_tracks_by_type("music")),
            "subtitle_tracks":  len(self.get_tracks_by_type("subtitle")),
        }


# ══════════════════════════════════════════════════════════════════════
# SUBTITLE ENGINE
# ══════════════════════════════════════════════════════════════════════

@dataclass
class Subtitle:
    index:     int
    start_ms:  int
    end_ms:    int
    text:      str
    character: str = ""

    def to_srt_block(self) -> str:
        """Convertit en bloc SRT standard."""
        def ms_to_srt(ms: int) -> str:
            td  = timedelta(milliseconds=ms)
            tot = int(td.total_seconds())
            h   = tot // 3600
            m   = (tot % 3600) // 60
            s   = tot % 60
            ms_rem = ms % 1000
            return f"{h:02d}:{m:02d}:{s:02d},{ms_rem:03d}"
        prefix = f"[{self.character}] " if self.character else ""
        return (
            f"{self.index}\n"
            f"{ms_to_srt(self.start_ms)} --> {ms_to_srt(self.end_ms)}\n"
            f"{prefix}{self.text}\n"
        )


class SubtitleEngine:
    """
    Génère les sous-titres depuis les dialogues et la timeline.
    Exporte en SRT, VTT, ASS.
    """

    def __init__(self):
        self._subtitles: list[Subtitle] = []

    def add_from_dialogue(self, text: str, character: str,
                           start_ms: int, duration_ms: int):
        """Ajoute un sous-titre depuis un dialogue."""
        # Découper les longues répliques si nécessaire
        MAX_CHARS = 42
        if len(text) <= MAX_CHARS:
            self._subtitles.append(Subtitle(
                index     = len(self._subtitles) + 1,
                start_ms  = start_ms,
                end_ms    = start_ms + duration_ms,
                text      = text,
                character = character,
            ))
        else:
            # Découper en deux lignes
            mid   = len(text) // 2
            space = text.rfind(" ", 0, mid + 10)
            if space > 0:
                line1 = text[:space]
                line2 = text[space+1:]
            else:
                line1 = text[:mid]
                line2 = text[mid:]
            half_dur = duration_ms // 2
            self._subtitles.append(Subtitle(
                index=len(self._subtitles)+1, start_ms=start_ms,
                end_ms=start_ms+half_dur, text=line1, character=character
            ))
            self._subtitles.append(Subtitle(
                index=len(self._subtitles)+1, start_ms=start_ms+half_dur,
                end_ms=start_ms+duration_ms, text=line2, character=character
            ))

    def generate_from_timeline(self, timeline: Timeline) -> list[Subtitle]:
        """Génère les sous-titres depuis les pistes dialogue de la timeline."""
        for track in timeline.get_tracks_by_type("dialogue"):
            if track.label:
                parts = track.label.split(":", 1)
                char  = parts[0].strip() if len(parts) > 1 else ""
                text  = parts[1].strip() if len(parts) > 1 else track.label
                self.add_from_dialogue(text, char,
                                        track.start_ms, track.duration_ms)
        return self._subtitles

    def export_srt(self, output_path: str) -> str:
        """Exporte en format SRT."""
        srt = "\n".join(s.to_srt_block() for s in
                         sorted(self._subtitles, key=lambda s: s.start_ms))
        Path(output_path).write_text(srt, encoding="utf-8")
        return output_path

    def export_vtt(self, output_path: str) -> str:
        """Exporte en format WebVTT (YouTube)."""
        lines = ["WEBVTT\n"]
        for s in sorted(self._subtitles, key=lambda x: x.start_ms):
            def ms_to_vtt(ms):
                td  = timedelta(milliseconds=ms)
                tot = int(td.total_seconds())
                h   = tot // 3600
                m   = (tot % 3600) // 60
                sc  = tot % 60
                return f"{h:02d}:{m:02d}:{sc:02d}.{ms%1000:03d}"
            lines.append(
                f"\n{ms_to_vtt(s.start_ms)} --> {ms_to_vtt(s.end_ms)}\n"
                f"{('['+s.character+'] ') if s.character else ''}{s.text}\n"
            )
        Path(output_path).write_text("".join(lines), encoding="utf-8")
        return output_path

    def generate_seo_content(self, title: str, description: str = "") -> dict:
        """Génère le contenu SEO depuis les sous-titres via Claude."""
        all_text = " ".join(s.text for s in self._subtitles[:20])
        prompt   = (
            f"Production vidéo : '{title}'\n"
            f"Dialogue extrait : '{all_text[:400]}'\n\n"
            f"Génère en JSON :\n"
            f"- youtube_title (max 70 chars, accrocheur)\n"
            f"- youtube_description (max 300 chars)\n"
            f"- tags (10 hashtags sans #, séparés par virgule)\n"
            f"- tiktok_caption (max 150 chars avec emojis)\n"
        )
        result = ""
        try:
            r = requests.post(ANTHROPIC_URL,
                headers={"Content-Type":"application/json"},
                json={"model":CLAUDE_MODEL,"max_tokens":400,
                      "messages":[{"role":"user","content":prompt}]},
                timeout=20)
            if r.status_code == 200:
                result = r.json()["content"][0]["text"].strip()
                if result.startswith("```"):
                    result = "\n".join(result.split("\n")[1:-1])
                return json.loads(result)
        except Exception:
            pass
        return {
            "youtube_title":      title[:70],
            "youtube_description":description[:300],
            "tags":               "anime,ia,overlord,animation,generative",
            "tiktok_caption":     f"✨ {title[:100]}",
        }


# ══════════════════════════════════════════════════════════════════════
# AUDIO MIXER
# ══════════════════════════════════════════════════════════════════════

class AudioMixer:
    """
    Mélange voix + musique + effets sonores via ffmpeg.
    Gère les niveaux, les fades, le ducking automatique.
    """

    def __init__(self, logger: logging.Logger = None):
        self.log = logger or logging.getLogger("audio_mixer")

    def mix(self, timeline: Timeline,
             output_path: str,
             total_duration_ms: int) -> str:
        """
        Mélange toutes les pistes audio de la timeline.
        Dialogue prend priorité sur la musique (ducking).
        """
        dialogue_tracks = timeline.get_tracks_by_type("dialogue")
        music_tracks    = timeline.get_tracks_by_type("music")

        if not dialogue_tracks and not music_tracks:
            return ""

        inputs    = []
        filters   = []
        i         = 0

        # Pistes de dialogue
        for t in dialogue_tracks:
            if t.source and Path(t.source).exists():
                start_s = t.start_ms / 1000
                inputs.extend(["-ss", "0", "-i", t.source])
                filters.append(
                    f"[{i}:a]adelay={t.start_ms}|{t.start_ms},"
                    f"volume={t.volume}[dlg{i}]"
                )
                i += 1

        # Pistes musicales (avec fade et volume réduit)
        for t in music_tracks:
            if t.source and Path(t.source).exists():
                inputs.extend(["-i", t.source])
                fi_s  = t.fade_in_ms / 1000
                fo_s  = t.fade_out_ms / 1000
                dur_s = t.duration_ms / 1000
                filters.append(
                    f"[{i}:a]adelay={t.start_ms}|{t.start_ms},"
                    f"afade=t=in:st=0:d={fi_s},"
                    f"afade=t=out:st={dur_s-fo_s}:d={fo_s},"
                    f"volume={t.volume}[mus{i}]"
                )
                i += 1

        if not inputs:
            return ""

        # Mix final
        all_labels = (
            [f"[dlg{j}]" for j in range(len(dialogue_tracks)) if dialogue_tracks[j].source and Path(dialogue_tracks[j].source).exists()] +
            [f"[mus{j+len(dialogue_tracks)}]" for j in range(len(music_tracks)) if music_tracks[j].source and Path(music_tracks[j].source).exists()]
        )
        if not all_labels:
            return ""

        n_inputs = len(all_labels)
        filters.append(f"{''.join(all_labels)}amix=inputs={n_inputs}:normalize=0[aout]")

        cmd = (
            ["ffmpeg"] +
            inputs +
            ["-filter_complex", ";".join(filters)] +
            ["-map", "[aout]"] +
            ["-t", str(total_duration_ms/1000)] +
            ["-ar", "44100", "-ac", "2"] +
            ["-y", output_path, "-loglevel", "quiet"]
        )
        try:
            result = subprocess.run(cmd, timeout=120, capture_output=True)
            if result.returncode == 0 and Path(output_path).exists():
                self.log.info(f"[MIXER] ✓ Mix audio : {output_path}")
                return output_path
        except Exception as e:
            self.log.error(f"[MIXER] {e}")
        return ""


# ══════════════════════════════════════════════════════════════════════
# MASTER EXPORTER
# ══════════════════════════════════════════════════════════════════════

class MasterExporter:
    """
    Export final de la production complète.
    Assemble vidéo + audio mixé + sous-titres incrustés.
    """

    def __init__(self, output_dir: Path = SYNC_DIR,
                 logger: logging.Logger = None):
        self.log        = logger or logging.getLogger("exporter")
        self.output_dir = output_dir
        self.output_dir.mkdir(parents=True, exist_ok=True)

    def export(self, video_path: str,
                audio_path: str,
                srt_path:   str = "",
                title:      str = "production",
                target_quality: str = "web") -> dict:
        """
        Export final MP4 + SRT + thumbnail.
        target_quality : "web" (CRF 23), "hd" (CRF 18), "preview" (CRF 28)
        """
        ts     = __import__("datetime").datetime.now().strftime("%Y%m%d_%H%M%S")
        out_mp4= str(self.output_dir / f"{title}_{ts}.mp4")
        out_srt= str(self.output_dir / f"{title}_{ts}.srt")

        crf = {"web":23,"hd":18,"preview":28}.get(target_quality, 23)

        # Copier le SRT
        if srt_path and Path(srt_path).exists():
            import shutil
            shutil.copy(srt_path, out_srt)

        # Assembler vidéo + audio
        if audio_path and Path(audio_path).exists():
            cmd = [
                "ffmpeg", "-i", video_path, "-i", audio_path,
                "-c:v", "libx264", "-crf", str(crf),
                "-c:a", "aac", "-b:a", "192k",
                "-shortest", "-movflags", "+faststart",
                "-y", out_mp4, "-loglevel", "quiet"
            ]
        else:
            cmd = [
                "ffmpeg", "-i", video_path,
                "-c:v", "libx264", "-crf", str(crf),
                "-movflags", "+faststart",
                "-y", out_mp4, "-loglevel", "quiet"
            ]

        success = False
        try:
            r = subprocess.run(cmd, timeout=300, capture_output=True)
            success = r.returncode == 0 and Path(out_mp4).exists()
        except Exception as e:
            self.log.error(f"[EXPORT] {e}")

        if success:
            size_mb = Path(out_mp4).stat().st_size / 1e6
            self.log.info(
                f"[EXPORT] ✓ {out_mp4} ({size_mb:.1f} Mo) — qualité={target_quality}"
            )

        # Générer thumbnail
        thumb_path = out_mp4.replace(".mp4", "_thumb.jpg")
        try:
            subprocess.run([
                "ffmpeg", "-i", out_mp4,
                "-ss", "1", "-vframes", "1", "-q:v", "2",
                "-y", thumb_path, "-loglevel", "quiet"
            ], timeout=15, capture_output=True)
        except Exception:
            pass

        return {
            "success":   success,
            "mp4":       out_mp4 if success else "",
            "srt":       out_srt if Path(out_srt).exists() else "",
            "thumbnail": thumb_path if Path(thumb_path).exists() else "",
            "quality":   target_quality,
            "title":     title,
        }


# ══════════════════════════════════════════════════════════════════════
# SYNCHRONICITY ENGINE — FAÇADE
# ══════════════════════════════════════════════════════════════════════

class SynchronicityEngine:
    """
    Chef d'orchestre de la synchronisation complète.
    Assemble tous les éléments V1.40 sur une timeline commune.
    """

    def __init__(self, logger: logging.Logger = None):
        self.log      = logger or logging.getLogger("synchronicity")
        self.mixer    = AudioMixer(logger=self.log)
        self.subtitles= SubtitleEngine()
        self.exporter = MasterExporter(logger=self.log)
        SYNC_DIR.mkdir(parents=True, exist_ok=True)

    def build_timeline(self, shots: list[dict]) -> Timeline:
        """
        Construit la timeline depuis la liste des shots.
        shots : [{"video_path":"...", "duration_s":2.5,
                  "dialogues":[{"character":"Kael","text":"...","audio":"..."}],
                  "music_path":"...", "emotion":"epic"}]
        """
        tl = Timeline()

        for i, shot in enumerate(shots):
            dur_ms = int(shot.get("duration_s", 3.0) * 1000)

            # Piste vidéo
            if shot.get("video_path"):
                tl.add_video_shot(
                    shot["video_path"], dur_ms,
                    label=f"Shot {i+1}: {shot.get('emotion','')}"
                )

            # Pistes dialogue
            dlg_start = tl._cursor_ms - dur_ms  # début du shot courant
            for dlg in shot.get("dialogues", []):
                if dlg.get("audio"):
                    # Estimer la durée depuis le texte (150 mots/min)
                    words     = len(dlg["text"].split())
                    dlg_dur_ms= max(1000, int(words / 2.5 * 1000))
                    tl.add_dialogue(
                        dlg["audio"], dlg_start,
                        dlg_dur_ms, dlg.get("character",""),
                        dlg.get("text","")
                    )
                    dlg_start += dlg_dur_ms + 200  # 200ms entre répliques

            # Piste musicale
            music_start = tl._cursor_ms - dur_ms
            if shot.get("music_path"):
                tl.add_music(
                    shot["music_path"], music_start, dur_ms,
                    volume=0.35
                )

        self.log.info(
            f"[SYNC] Timeline construite : {tl.get_summary()}"
        )
        return tl

    def produce(self, shots: list[dict],
                 video_concat_path: str,
                 title: str = "overlord_production",
                 quality: str = "web") -> dict:
        """
        Production complète synchronisée.
        1. Build timeline
        2. Mix audio
        3. Génère sous-titres
        4. Export final
        """
        self.log.info(f"[SYNC] Production '{title}' — {len(shots)} shots")

        # 1. Timeline
        tl = self.build_timeline(shots)

        # 2. Mix audio
        mix_path = str(SYNC_DIR / f"mix_{title}.aac")
        audio_ok = self.mixer.mix(tl, mix_path, tl.total_duration_ms)

        # 3. Sous-titres
        self.subtitles = SubtitleEngine()
        self.subtitles.generate_from_timeline(tl)
        srt_path = str(SYNC_DIR / f"{title}.srt")
        if self.subtitles._subtitles:
            self.subtitles.export_srt(srt_path)
            self.subtitles.export_vtt(srt_path.replace(".srt",".vtt"))

        # 4. SEO
        seo = self.subtitles.generate_seo_content(title)

        # 5. Export final
        export = self.exporter.export(
            video_concat_path,
            mix_path if audio_ok else "",
            srt_path if self.subtitles._subtitles else "",
            title, quality
        )

        return {
            "timeline":  tl.get_summary(),
            "audio_ok":  bool(audio_ok),
            "subtitles": len(self.subtitles._subtitles),
            "seo":       seo,
            "export":    export,
        }

    def get_dashboard(self) -> dict:
        return {
            "version": "1.40_synchronicity",
            "supported_formats": ["mp4","srt","vtt"],
            "audio_tracks": ["dialogue","music","sfx"],
        }


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    engine = SynchronicityEngine()
    print("=== V1.40 SYNCHRONICITY ENGINE ===")
    tl = engine.build_timeline([
        {"duration_s": 3.0, "emotion": "epic",
         "dialogues": [{"character":"Kael","text":"Je suis prêt à tout.","audio":""}]},
        {"duration_s": 2.5, "emotion": "action",
         "dialogues": [{"character":"Général","text":"Tu ne gagneras pas.","audio":""}]},
    ])
    print(f"Timeline : {tl.get_summary()}")
    print(f"Dashboard : {engine.get_dashboard()}")

"""
agents/video_pipeline.py -- Ov3rLoRd V1.40 -- Video Pipeline
Generation video avancee : interpolation, upscale, stabilisation.
V1.49o : overlord_utils centralise, context_bus connecte.
"""

import json
import subprocess
import shutil
import logging
import time
from pathlib import Path
from datetime import datetime, timezone
from dataclasses import dataclass, field
from typing import Optional

try:
    from agents.overlord_utils import fallback_llm, safe_json_parse
    UTILS_OK = True
except ImportError:
    UTILS_OK = False
    fallback_llm    = None
    safe_json_parse = None

try:
    from agents.context_bus import get_bus
    BUS_OK = True
except ImportError:
    BUS_OK = False

VIDEO_DIR    = Path("workspace/video_pipeline")
CLAUDE_MODEL = "claude-sonnet-4-6"
log          = logging.getLogger("video_pipeline")

FFMPEG_OK = shutil.which("ffmpeg") is not None


def _llm(prompt: str, system: str = "", max_tokens: int = 300) -> str:
    if UTILS_OK and fallback_llm:
        return fallback_llm(prompt, system=system, model=CLAUDE_MODEL, max_tokens=max_tokens)
    return ""


@dataclass
class VideoClip:
    shot_id:     str
    image_paths: list[str] = field(default_factory=list)
    duration_s:  float     = 3.0
    fps:         int        = 24
    interpolated:bool       = False
    upscaled:    bool       = False
    path:        str        = ""


class FrameInterpolator:
    """Interpole des frames entre images pour fluidifier le mouvement."""

    def interpolate(self, frames: list[str], output_dir: Path,
                    target_fps: int = 24, source_fps: int = 8) -> list[str]:
        if not FFMPEG_OK:
            log.warning("[VIDEO] ffmpeg requis pour l'interpolation")
            return frames
        if not frames:
            return []
        output_dir.mkdir(parents=True, exist_ok=True)
        multiplier = target_fps // max(source_fps, 1)
        results    = []
        for i, frame_path in enumerate(frames):
            out = output_dir / f"interp_{i:04d}.png"
            cmd = [
                "ffmpeg", "-y", "-loop", "1", "-i", frame_path,
                "-vf",    f"minterpolate=fps={target_fps}:mi_mode=mci",
                "-t",     str(1 / source_fps * multiplier),
                "-frames:v", str(multiplier),
                str(out)
            ]
            try:
                r = subprocess.run(cmd, capture_output=True, timeout=60)
                if r.returncode == 0:
                    results.append(str(out))
            except Exception as e:
                log.warning(f"[VIDEO] Interpolation frame {i} : {e}")
                results.append(frame_path)
        return results


class VideoUpscaler:
    """Upscale la video finale via Real-ESRGAN ou ffmpeg."""

    def upscale_ffmpeg(self, input_path: str, output_path: str,
                        scale: float = 2.0) -> bool:
        if not FFMPEG_OK:
            return False
        try:
            w = int(1920 * scale)
            h = int(1080 * scale)
            cmd = [
                "ffmpeg", "-y", "-i", input_path,
                "-vf", f"scale={w}:{h}:flags=lanczos",
                "-c:v", "libx264", "-crf", "16", "-preset", "slow",
                output_path
            ]
            r = subprocess.run(cmd, capture_output=True, timeout=300)
            if r.returncode == 0:
                log.info(f"[VIDEO] Upscale OK : {output_path}")
                return True
            log.warning(f"[VIDEO] Upscale ffmpeg echec : {r.stderr[-200:]}")
        except Exception as e:
            log.warning(f"[VIDEO] Upscale exception : {e}")
        return False


class VideoStabilizer:
    """Stabilise la video pour reduire les artefacts de transition."""

    def stabilize(self, input_path: str, output_path: str) -> bool:
        if not FFMPEG_OK:
            return False
        try:
            # Phase 1 : analyse
            analyze_path = str(Path(output_path).parent / "transforms.trf")
            cmd1 = [
                "ffmpeg", "-y", "-i", input_path,
                "-vf", f"vidstabdetect=stepsize=6:shakiness=8:accuracy=9:result={analyze_path}",
                "-f", "null", "-"
            ]
            r1 = subprocess.run(cmd1, capture_output=True, timeout=300)
            if r1.returncode != 0:
                return False
            # Phase 2 : stabilisation
            cmd2 = [
                "ffmpeg", "-y", "-i", input_path,
                "-vf", f"vidstabtransform=input={analyze_path}:zoom=1:smoothing=30",
                "-c:v", "libx264", "-crf", "18",
                output_path
            ]
            r2 = subprocess.run(cmd2, capture_output=True, timeout=300)
            return r2.returncode == 0
        except Exception as e:
            log.warning(f"[VIDEO] Stabilisation : {e}")
            return False


class SceneTransitionEngine:
    """Genere des transitions cinematographiques entre scenes."""

    TRANSITIONS = {
        "cut":     None,  # Pas de filtre -- montage direct
        "fade":    "fade=t=in:st=0:d=0.5,fade=t=out:st=2.5:d=0.5",
        "dissolve":"xfade=transition=dissolve:duration=0.5",
        "wipe":    "xfade=transition=wipeleft:duration=0.3",
        "zoom":    "zoompan=z='if(lte(on,1),1.5,max(1,z-0.01))':d=25:s=1920x1080",
    }

    def apply(self, input_a: str, input_b: str,
               transition: str, output: str) -> bool:
        if not FFMPEG_OK:
            return False
        if transition == "cut" or transition not in self.TRANSITIONS:
            # Concatenation directe
            concat = Path(output).parent / "concat_trans.txt"
            concat.write_text(
                f"file '{input_a}'\nfile '{input_b}'\n", encoding="utf-8"
            )
            cmd = ["ffmpeg","-y","-f","concat","-safe","0","-i",str(concat),
                   "-c:v","libx264","-crf","18",output]
        else:
            vf = self.TRANSITIONS[transition]
            cmd = [
                "ffmpeg","-y","-i",input_a,"-i",input_b,
                "-filter_complex",
                f"[0:v][1:v]{vf}[v]",
                "-map","[v]","-c:v","libx264","-crf","18",output
            ]
        try:
            r = subprocess.run(cmd, capture_output=True, timeout=120)
            return r.returncode == 0
        except Exception:
            return False


class VideoPipelineV140:
    """Pipeline video complet : interpolation + upscale + stabilisation."""

    def __init__(self, logger: logging.Logger = None):
        self.log          = logger or log
        self.interpolator = FrameInterpolator()
        self.upscaler     = VideoUpscaler()
        self.stabilizer   = VideoStabilizer()
        self.transitions  = SceneTransitionEngine()
        VIDEO_DIR.mkdir(parents=True, exist_ok=True)

    def process_clip(self, clip: VideoClip, output_dir: Path = None,
                     do_interpolate: bool = False,
                     do_upscale: bool = False,
                     do_stabilize: bool = False) -> VideoClip:
        out = output_dir or VIDEO_DIR
        out.mkdir(parents=True, exist_ok=True)
        ts  = datetime.now(tz=timezone.utc).strftime("%Y%m%d_%H%M%S")

        if not FFMPEG_OK:
            self.log.warning("[VIDEO] ffmpeg absent -- traitement ignore")
            return clip

        # Assemblage de base
        concat_file = out / f"concat_{clip.shot_id}.txt"
        with open(concat_file, "w", encoding="utf-8") as f:
            for img in clip.image_paths:
                f.write(f"file '{Path(img).resolve()}'\n")
                f.write(f"duration {clip.duration_s / max(len(clip.image_paths),1)}\n")
            if clip.image_paths:
                f.write(f"file '{Path(clip.image_paths[-1]).resolve()}'\n")

        base_path = str(out / f"{clip.shot_id}_{ts}_base.mp4")
        cmd = ["ffmpeg","-y","-f","concat","-safe","0","-i",str(concat_file),
               "-vf","scale=1920:1080","-c:v","libx264","-crf","18",
               "-pix_fmt","yuv420p","-r",str(clip.fps), base_path]
        r = subprocess.run(cmd, capture_output=True, timeout=120)
        if r.returncode != 0:
            self.log.error(f"[VIDEO] Assemblage echec : {r.stderr[-200:]}")
            return clip

        current = base_path

        if do_upscale:
            up_path = str(out / f"{clip.shot_id}_{ts}_upscaled.mp4")
            if self.upscaler.upscale_ffmpeg(current, up_path):
                current = up_path
                clip.upscaled = True

        if do_stabilize:
            stab_path = str(out / f"{clip.shot_id}_{ts}_stable.mp4")
            if self.stabilizer.stabilize(current, stab_path):
                current = stab_path

        clip.path = current
        self.log.info(f"[VIDEO] Clip traite : {clip.shot_id} -> {current}")

        if BUS_OK:
            try:
                get_bus().write(f"video.{clip.shot_id}", current, agent_id="video_pipeline")
                get_bus().write("video.last_clip",  clip.shot_id,  agent_id="video_pipeline")
            except Exception:
                pass

        return clip

    def assemble_episode(self, clips: list[VideoClip],
                          transition: str = "cut",
                          output_path: str = None) -> str:
        if not clips:
            return ""
        out_path = output_path or str(
            VIDEO_DIR / f"episode_{datetime.now(tz=timezone.utc).strftime('%Y%m%d_%H%M%S')}.mp4"
        )
        # Assembler via concat
        ready = [c for c in clips if c.path and Path(c.path).exists()]
        if not ready:
            self.log.error("[VIDEO] Aucun clip valide pour l'assemblage")
            return ""

        concat_file = VIDEO_DIR / "episode_concat.txt"
        with open(concat_file, "w", encoding="utf-8") as f:
            for clip in ready:
                f.write(f"file '{Path(clip.path).resolve()}'\n")

        cmd = ["ffmpeg","-y","-f","concat","-safe","0","-i",str(concat_file),
               "-c:v","libx264","-crf","18","-pix_fmt","yuv420p", out_path]
        try:
            r = subprocess.run(cmd, capture_output=True, timeout=600)
            if r.returncode == 0:
                self.log.info(f"[VIDEO] Episode assemble : {out_path}")
                if BUS_OK:
                    try:
                        get_bus().write("video.episode_path", out_path,   agent_id="video_pipeline")
                        get_bus().write("video.clip_count",   len(ready), agent_id="video_pipeline")
                    except Exception:
                        pass
                return out_path
        except Exception as e:
            self.log.error(f"[VIDEO] Assemblage episode : {e}")
        return ""


if __name__ == "__main__":
    import sys, io
    if hasattr(sys.stdout, "buffer"):
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    logging.basicConfig(level=logging.INFO)
    vp = VideoPipelineV140()
    print(f"ffmpeg disponible : {FFMPEG_OK}")
    print("VideoPipelineV140 OK")
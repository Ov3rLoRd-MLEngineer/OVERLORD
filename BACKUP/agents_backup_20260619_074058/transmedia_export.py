"""
agents/transmedia_export.py — Export Transmedia V1.47 + Context Bus V1.49
Lit les metadonnees depuis le context_bus (titre, arc emotionnel, shots).
Publie le statut d'export sur le bus en fin d'operation.
"""
import json
import logging
import os
import shutil
import subprocess
import sys
import io
from pathlib import Path
from datetime import datetime
from typing import Optional

if hasattr(sys.stdout, 'buffer'):
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

try:
    from agents.overlord_utils import fallback_llm, get_api_key
    UTILS_OK = True
except ImportError:
    UTILS_OK = False

try:
    from agents.context_bus import get_bus
    BUS_OK = True
except ImportError:
    BUS_OK = False

log = logging.getLogger("transmedia_export")
EXPORT_DIR = Path("workspace/transmedia")

PLATFORM_SPECS = {
    "youtube": {
        "video_ratio": "16:9", "res": "1920x1080",
        "thumb_res": "1280x720", "max_title": 100,
        "max_desc": 5000,
    },
    "instagram_post": {
        "image_ratio": "1:1", "res": "1080x1080",
        "max_caption": 2200, "hashtags_max": 30,
    },
    "instagram_reel": {
        "video_ratio": "9:16", "res": "1080x1920",
        "max_duration": 90, "max_caption": 2200,
    },
    "reddit": {
        "max_title": 300, "max_text": 40000,
        "subreddits": ["anime", "AIGeneratedArt", "StableDiffusion"],
    },
    "twitter_x": {
        "max_chars": 280, "media_max": 4, "video_max_mb": 512,
    },
    "webtoon": {
        "image_width": 800, "strip_height": 1280, "max_episodes": 999,
    },
}


class ContentGenerator:
    """Genere les textes adaptes a chaque plateforme via LLM."""

    def generate_for_platform(self, platform: str, metadata: dict) -> dict:
        # Enrichir depuis le context_bus si disponible
        if BUS_OK:
            try:
                bus = get_bus()
                if not metadata.get("title"):
                    val = bus.read("scenario.title")
                    if val:
                        metadata["title"] = val
                if not metadata.get("emotion_arc"):
                    val = bus.read("director.emotion_arc")
                    if val:
                        metadata["emotion_arc"] = val
                shots = bus.read("storyboard.shots_count")
                if shots is not None:
                    metadata["shots_count"] = shots
            except Exception:
                pass

        title    = metadata.get("title",    "Ov3rLoRd Episode")
        synopsis = metadata.get("synopsis", "")[:300]
        genre    = ", ".join(metadata.get("genre", ["anime"]))
        series   = metadata.get("series",   "Ov3rLoRd")
        ep       = metadata.get("episode",  1)
        chars    = ", ".join(metadata.get("characters", [])[:4])
        arc      = metadata.get("emotion_arc", "")
        arc_hint = f"Arc emotionnel : {arc}." if arc else ""

        if not UTILS_OK:
            return self._fallback_content(platform, metadata)

        prompt = (
            f"Genere du contenu optimise pour {platform}.\n"
            f"Serie : {series} | Episode {ep} | Titre : {title}\n"
            f"Synopsis : {synopsis}\n"
            f"Genre : {genre} | Personnages : {chars}\n"
            f"{arc_hint}\n\n"
            f"Retourne UNIQUEMENT ce JSON :\n"
            f'{{"title":"titre optimise {platform}","description":"description adaptee",'
            f'"hashtags":["tag1","tag2"],"cta":"call to action"}}'
        )
        raw = fallback_llm(prompt, max_tokens=400, logger=log)
        if raw:
            try:
                import re
                clean = re.sub(r'```json|```', '', raw).strip()
                return json.loads(clean)
            except Exception:
                pass
        return self._fallback_content(platform, metadata)

    def _fallback_content(self, platform: str, meta: dict) -> dict:
        series = meta.get("series", "Ov3rLoRd")
        ep     = meta.get("episode", 1)
        title  = meta.get("title",  "Episode")
        return {
            "title":       f"{series} - Ep.{ep:02d} : {title}",
            "description": meta.get("synopsis", "")[:300],
            "hashtags":    ["#anime", "#AIart", "#Ov3rLoRd", "#StableDiffusion"],
            "cta":         "Abonnez-vous pour la suite !",
        }


class VideoConverter:
    """Convertit la video pour chaque format de plateforme."""

    def convert(self, source: str, platform: str, output_dir: Path) -> Optional[str]:
        if not shutil.which("ffmpeg"):
            log.warning("[TRANSMEDIA] ffmpeg requis pour les conversions")
            return None

        output  = output_dir / f"export_{platform}_{Path(source).stem}.mp4"
        filters = {
            "youtube": [
                "-vf", "scale=1920:1080", "-c:v", "libx264", "-crf", "18", "-preset", "fast"
            ],
            "instagram_reel": [
                "-vf", "scale=1080:1920:force_original_aspect_ratio=decrease,"
                       "pad=1080:1920:(ow-iw)/2:(oh-ih)/2",
                "-c:v", "libx264", "-crf", "23"
            ],
            "twitter_x": [
                "-vf", "scale=1280:720", "-c:v", "libx264", "-crf", "23", "-t", "140"
            ],
        }
        args = filters.get(platform, ["-c:v", "libx264", "-crf", "23"])
        try:
            cmd = ["ffmpeg", "-y", "-i", str(source)] + args + [str(output)]
            r   = subprocess.run(cmd, capture_output=True, timeout=300)
            if r.returncode == 0:
                log.info(f"[TRANSMEDIA] Converti {platform} : {output.name}")
                return str(output)
        except Exception as e:
            log.warning(f"[TRANSMEDIA] Conversion {platform} : {e}")
        return None


class PlatformPublisher:
    """Publie sur chaque plateforme via leurs APIs."""

    def publish_reddit(self, subreddit: str, title: str, text: str,
                       image_path: str = None) -> dict:
        try:
            import praw
            cid  = os.environ.get("REDDIT_CLIENT_ID", "")
            csec = os.environ.get("REDDIT_CLIENT_SECRET", "")
            user = os.environ.get("REDDIT_USERNAME", "")
            pwd  = os.environ.get("REDDIT_PASSWORD", "")
            if not all([cid, csec, user, pwd]):
                return {"status": "skipped", "reason": "credentials manquants"}
            reddit = praw.Reddit(
                client_id=cid, client_secret=csec,
                username=user, password=pwd,
                user_agent="Ov3rLoRd-Pipeline/1.49"
            )
            sub = reddit.subreddit(subreddit)
            if image_path and Path(image_path).exists():
                sub_obj = sub.submit_image(title=title, image_path=image_path)
            else:
                sub_obj = sub.submit(title=title, selftext=text)
            return {"status": "ok", "url": f"https://reddit.com{sub_obj.permalink}"}
        except ImportError:
            return {"status": "skipped", "reason": "pip install praw"}
        except Exception as e:
            return {"status": "error", "reason": str(e)}

    def send_telegram_preview(self, video_path: str, caption: str) -> bool:
        try:
            from agents.telegram_bot import send_notification
            send_notification(f"Nouvel episode pret ! {caption[:200]}")
            return True
        except Exception:
            return False


class TransmediaExporter:
    """Orchestre l'export complet sur toutes les plateformes."""

    def __init__(self, logger: logging.Logger = None):
        self.log       = logger or log
        self.content   = ContentGenerator()
        self.converter = VideoConverter()
        self.publisher = PlatformPublisher()
        EXPORT_DIR.mkdir(parents=True, exist_ok=True)

    def export_all(self, episode_result: dict, metadata: dict,
                   platforms: list = None) -> dict:
        targets = platforms or ["youtube", "instagram_reel", "reddit", "twitter_x"]
        video   = episode_result.get("files", {}).get("video",     "")
        thumb   = episode_result.get("files", {}).get("thumbnail", "")
        ts      = datetime.now().strftime("%Y%m%d_%H%M%S")
        out_dir = EXPORT_DIR / ts
        out_dir.mkdir(parents=True, exist_ok=True)

        report = {"timestamp": ts, "platforms": {}, "assets": {}}
        self.log.info(f"[TRANSMEDIA] Export sur {len(targets)} plateformes...")

        for platform in targets:
            self.log.info(f"[TRANSMEDIA] -> {platform}")
            pdata   = {"status": "pending", "content": {}, "files": {}}
            content = self.content.generate_for_platform(platform, metadata)
            pdata["content"] = content

            if video and Path(video).exists():
                converted = self.converter.convert(video, platform, out_dir)
                if converted:
                    pdata["files"]["video"] = converted

            if platform == "instagram_post" and thumb and Path(thumb).exists():
                post_img = out_dir / f"instagram_post_{ts}.jpg"
                shutil.copy(thumb, post_img)
                pdata["files"]["image"] = str(post_img)

            if platform == "reddit":
                pdata["reddit_post"] = {
                    "title":      content["title"],
                    "text":       f"{content['description']}\n\n{content['cta']}",
                    "subreddits": PLATFORM_SPECS["reddit"]["subreddits"],
                }

            script_path = out_dir / f"publish_{platform}.txt"
            script_path.write_text(
                f"=== PUBLICATION {platform.upper()} ===\n"
                f"Titre : {content['title']}\n\n"
                f"Description :\n{content['description']}\n\n"
                f"Hashtags : {' '.join(content.get('hashtags', []))}\n\n"
                f"CTA : {content.get('cta', '')}\n",
                encoding="utf-8"
            )
            pdata["files"]["script"] = str(script_path)
            pdata["status"] = "ready"
            report["platforms"][platform] = pdata

        # Publier le statut export sur le context_bus
        if BUS_OK:
            try:
                bus = get_bus()
                bus.write("transmedia.status",    "ready",     agent_id="transmedia")
                bus.write("transmedia.platforms", targets,     agent_id="transmedia")
                bus.write("transmedia.timestamp", ts,          agent_id="transmedia")
                bus.write("transmedia.video",     video or "", agent_id="transmedia")
            except Exception:
                pass

        self.publisher.send_telegram_preview(
            video or "",
            f"Ep.{metadata.get('episode',1)} - {metadata.get('title','')} pret pour export !"
        )

        report_path = out_dir / "transmedia_report.json"
        report_path.write_text(
            json.dumps(report, indent=2, ensure_ascii=False, default=str),
            encoding="utf-8"
        )
        report["report_path"] = str(report_path)
        self.log.info(f"[TRANSMEDIA] Export termine -> {out_dir}")
        return report


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    exp = TransmediaExporter()
    fake_meta = {
        "series":    "Dragon Ball Ov3rLoRd",
        "episode":   1,
        "title":     "L'Eveil du Guerrier",
        "synopsis":  "Goku affronte Broly dans une plaine desertique a l'aube...",
        "genre":     ["action", "aventure", "sci-fi"],
        "characters":["Goku", "Broly"],
    }
    result = exp.export_all({}, fake_meta, platforms=["youtube", "reddit", "twitter_x"])
    print(json.dumps({k: v for k, v in result.items() if k != "platforms"}, indent=2))
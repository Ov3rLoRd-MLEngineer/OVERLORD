"""
agents/transmedia_publisher.py — Agent Publication Transmedia V1.70
Export automatique des productions vers les formats de diffusion.
Prépare les assets pour YouTube, TikTok, Instagram, et stockage local.

Fonctions :
  - Sélection automatique des meilleures images (score > seuil)
  - Création de thumbnails titrées
  - Découpe de clips courts (TikTok/Reels : 15-30s)
  - Génération de descriptions et hashtags via LLM
  - Export vers dossier organisé prêt à uploader

Prérequis :
  pip install Pillow requests
  ffmpeg dans le PATH
"""

import json
import logging
import shutil
import subprocess
import sys
import io
from datetime import datetime
from pathlib import Path

if hasattr(sys.stdout, 'buffer'):
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

try:
    from PIL import Image, ImageDraw, ImageFont
    PIL_OK = True
except ImportError:
    PIL_OK = False

try:
    from agents.overlord_utils import fallback_llm, safe_json_parse
    UTILS_OK = True
except ImportError:
    UTILS_OK = False

try:
    from agents.context_bus import get_bus
    BUS_OK = True
except ImportError:
    BUS_OK = False

try:
    from agents.music_synthesis import is_non_commercial_track
    MUSIC_LICENSE_OK = True
except ImportError:
    MUSIC_LICENSE_OK = False

PUBLISH_DIR  = Path("workspace/publish")
REPORTS_DIR  = Path("workspace/reports")

PLATFORM_SPECS = {
    "youtube": {
        "thumb_size":   (1280, 720),
        "video_preset": ["-vf", "scale=1920:1080", "-c:v", "libx264", "-crf", "18"],
        "description_max": 5000,
        "tags_max":     500,
    },
    "tiktok": {
        "thumb_size":   (1080, 1920),
        "video_preset": ["-vf", "scale=1080:1920", "-c:v", "libx264", "-crf", "23", "-t", "60"],
        "description_max": 2200,
        "tags_max":     100,
    },
    "instagram": {
        "thumb_size":   (1080, 1080),
        "video_preset": ["-vf", "scale=1080:1080:force_original_aspect_ratio=decrease,pad=1080:1080:(ow-iw)/2:(oh-ih)/2", "-c:v", "libx264", "-crf", "23"],
        "description_max": 2200,
        "tags_max":     30,
    },
}

ANIME_HASHTAGS = [
    "#anime", "#animeart", "#animegirl", "#mangaart",
    "#digitalart", "#illustration", "#aiart", "#stablediffusion",
    "#evangelion", "#neongenesis", "#comfyui", "#animedrawing",
    "#characterdesign", "#ov3rlord", "#overlordai",
]


def select_best_images(archive_dir: Path, min_score: float = 80.0,
                        n: int = 8, logger=None) -> list[Path]:
    """
    Sélectionne les N meilleures images d'un run selon le score quality_reviewer.
    Fallback : prend les N plus grandes images (heuristique qualité).
    """
    log = logger or logging.getLogger("publisher")

    # Chercher le log quality_reviews pour les scores
    review_log = Path("workspace/logs/quality_reviews.jsonl")
    scored = {}
    if review_log.exists():
        for line in review_log.read_text(encoding='utf-8', errors='replace').splitlines():
            try:
                r = json.loads(line)
                ip = r.get("image_path", "")
                if ip and r.get("score", 0) >= min_score:
                    scored[ip] = r["score"]
            except Exception:
                pass

    images = list(archive_dir.rglob("*.png")) + list(archive_dir.rglob("*.jpg"))

    # Images avec score connu
    scored_imgs = [(Path(p), s) for p, s in scored.items() if Path(p).exists() and Path(p).parent == archive_dir or str(archive_dir) in p]
    if scored_imgs:
        scored_imgs.sort(key=lambda x: x[1], reverse=True)
        result = [p for p, _ in scored_imgs[:n]]
        log.info(f"[PUBLISH] {len(result)} images sélectionnées (score ≥ {min_score})")
        return result

    # Fallback : taille fichier comme proxy qualité
    images.sort(key=lambda p: p.stat().st_size, reverse=True)
    result = images[:n]
    log.info(f"[PUBLISH] {len(result)} images sélectionnées (fallback taille)")
    return result


def create_thumbnail(image_path: Path, title: str, platform: str = "youtube",
                     logger=None) -> Path | None:
    """Crée une thumbnail titrée pour la plateforme cible."""
    log = logger or logging.getLogger("publisher")
    if not PIL_OK:
        log.warning("[PUBLISH] PIL absent — thumbnail non créée")
        return None

    spec   = PLATFORM_SPECS.get(platform, PLATFORM_SPECS["youtube"])
    w, h   = spec["thumb_size"]
    out    = PUBLISH_DIR / platform / f"thumb_{image_path.stem}.jpg"
    out.parent.mkdir(parents=True, exist_ok=True)

    try:
        img = Image.open(image_path).convert("RGB")
        img = img.resize((w, h), Image.LANCZOS)

        # Overlay titre
        draw = ImageDraw.Draw(img)
        # Bande noire semi-transparente en bas
        overlay = Image.new("RGBA", (w, h//5), (0, 0, 0, 180))
        img.paste(overlay, (0, h - h//5), overlay)

        # Texte
        try:
            font = ImageFont.truetype("arial.ttf", h // 16)
        except Exception:
            font = ImageFont.load_default()

        title_short = title[:50] + ("…" if len(title) > 50 else "")
        draw.text((w//20, h - h//7), title_short, fill=(255, 255, 255), font=font)
        draw.text((w//20, h - h//14), "Ov3rLoRd • AI Production",
                  fill=(200, 150, 255), font=font)

        img.save(str(out), "JPEG", quality=92)
        log.info(f"[PUBLISH] Thumbnail créée : {out.name}")
        return out
    except Exception as e:
        log.error(f"[PUBLISH] Thumbnail erreur : {e}")
        return None


def generate_description(script: dict, platform: str = "youtube",
                          logger=None) -> dict:
    """Génère description + hashtags via LLM."""
    log = logger or logging.getLogger("publisher")
    spec = PLATFORM_SPECS.get(platform, PLATFORM_SPECS["youtube"])

    title    = script.get("title", "Ov3rLoRd AI Production")
    logline  = script.get("logline", "")
    synopsis = script.get("synopsis", "")[:300]
    genre    = ", ".join(script.get("genre", ["anime"]))

    if UTILS_OK:
        system = (
            "You are a social media content specialist for anime AI productions. "
            "Reply ONLY with valid JSON."
        )
        prompt = (
            f"Platform: {platform}\n"
            f"Anime title: {title}\n"
            f"Logline: {logline}\n"
            f"Synopsis: {synopsis}\n"
            f"Genre: {genre}\n\n"
            f"Generate engaging {platform} content. Max description: {spec['description_max']} chars.\n"
            f"Reply ONLY with JSON: {{\"description\": \"...\", \"hashtags\": [\"#tag1\", \"#tag2\"]}}"
        )
        raw = fallback_llm(prompt, system=system, max_tokens=600, logger=log)
        ok, data, _ = safe_json_parse(raw, logger=log)
        if ok and isinstance(data, dict):
            desc  = data.get("description", "")[:spec["description_max"]]
            htags = data.get("hashtags", [])[:spec.get("tags_max", 30)]
            htags = list(set(htags + ANIME_HASHTAGS[:10]))
            return {"description": desc, "hashtags": htags}

    # Fallback manuel
    desc = (
        f"🎌 {title}\n\n"
        f"{logline}\n\n"
        f"{synopsis}\n\n"
        f"Generated with Ov3rLoRd AI Pipeline V1.70\n"
        f"Ov3rLoRd — AI Anime Production Studio"
    )
    return {"description": desc[:spec["description_max"]], "hashtags": ANIME_HASHTAGS}


def check_music_license(audio_path: Path | None, monetized: bool,
                         logger=None) -> tuple[bool, str]:
    """
    Vérifie le flag non-commercial d'une piste MusicGen avant une mise en ligne
    monétisée (cf. DOCS/ADR_MUSIC.md / ADR-012). Retourne (autorisé, raison).

    - Publication non-monétisée : toujours autorisée, aucune vérification.
    - Pas de piste audio jointe : autorisé (rien à bloquer).
    - Piste jointe + monétisation demandée : bloque si le sidecar de licence
      indique `non_commercial=True` (ou si le statut de licence est inconnu --
      fail-safe, on ne prend pas le risque).
    """
    log = logger or logging.getLogger("publisher")
    if not monetized or not audio_path:
        return True, "ok"

    if not MUSIC_LICENSE_OK:
        log.warning("[PUBLISH] agents.music_synthesis indisponible -- statut de licence "
                    "audio inconnu, publication monétisée bloquée par prudence")
        return False, "music_license_check_unavailable"

    if is_non_commercial_track(audio_path):
        log.error(
            f"[PUBLISH] BLOQUÉ — piste audio non-commerciale (MusicGen/CC-BY-NC 4.0) "
            f"détectée sur une publication monétisée : {audio_path}"
        )
        return False, "non_commercial_music_track"

    return True, "ok"


def export_for_platform(video_path: Path, images: list[Path],
                         script: dict, platform: str = "youtube",
                         logger=None, audio_path: Path = None,
                         monetized: bool = False) -> dict:
    """Export complet pour une plateforme."""
    log  = logger or logging.getLogger("publisher")
    spec = PLATFORM_SPECS.get(platform, PLATFORM_SPECS["youtube"])

    allowed, reason = check_music_license(audio_path, monetized, logger=log)
    if not allowed:
        return {"error": reason, "platform": platform, "blocked": True}

    out_dir = PUBLISH_DIR / platform / datetime.now().strftime("%Y%m%d_%H%M%S")
    out_dir.mkdir(parents=True, exist_ok=True)

    result = {"platform": platform, "files": {}, "metadata": {}}

    # Vidéo recodée pour la plateforme
    if video_path and video_path.exists():
        vid_out = out_dir / f"video_{platform}.mp4"
        cmd = ["ffmpeg", "-y", "-i", str(video_path)] + spec["video_preset"] + [str(vid_out)]
        try:
            subprocess.run(cmd, capture_output=True, timeout=300, check=True)
            result["files"]["video"] = str(vid_out)
            log.info(f"[PUBLISH] Vidéo {platform} : {vid_out.name}")
        except Exception as e:
            log.warning(f"[PUBLISH] Vidéo {platform} échouée : {e}")

    # Thumbnail depuis la meilleure image
    if images:
        thumb = create_thumbnail(images[0], script.get("title", ""), platform, logger=log)
        if thumb:
            result["files"]["thumbnail"] = str(thumb)

    # Copier les meilleures images
    img_dir = out_dir / "images"
    img_dir.mkdir(exist_ok=True)
    for i, img in enumerate(images[:8]):
        if img.exists():
            dest = img_dir / f"frame_{i+1:02d}{img.suffix}"
            shutil.copy2(img, dest)
    result["files"]["images_dir"] = str(img_dir)

    # Description et hashtags
    meta = generate_description(script, platform, logger=log)
    result["metadata"] = meta

    # Sauvegarder les métadonnées
    meta_file = out_dir / "metadata.json"
    meta_file.write_text(json.dumps({
        "title":       script.get("title", ""),
        "platform":    platform,
        "exported_at": datetime.now().isoformat(),
        **meta
    }, indent=2, ensure_ascii=False), encoding='utf-8')
    result["files"]["metadata"] = str(meta_file)

    log.info(f"[PUBLISH] Export {platform} OK → {out_dir}")

    if BUS_OK:
        try:
            get_bus().write(f"publish.{platform}_done", True, agent_id="publisher")
            get_bus().write(f"publish.{platform}_dir",  str(out_dir), agent_id="publisher")
        except Exception:
            pass

    return result


def run_publisher(run_id: str = None, platforms: list = None,
                  min_score: float = 75.0, logger=None,
                  monetized: bool = False) -> dict:
    """
    Point d'entrée principal.
    Récupère le run le plus récent, exporte vers toutes les plateformes.

    `monetized=True` active la vérification de licence audio (ADR-012) : toute
    piste MusicGen (non-commerciale) jointe à ce run bloque l'export pour
    chaque plateforme concernée.
    """
    log       = logger or logging.getLogger("publisher")
    platforms = platforms or ["youtube", "tiktok", "instagram"]

    log.info(f"[PUBLISH] Démarrage — plateformes={platforms} — monétisé={monetized}")

    # Trouver l'archive et la vidéo du run
    archive_root = Path("workspace/archive")
    exports_dir  = Path("workspace/exports")
    music_dir    = Path("workspace/music_synthesis")

    # Trouver le run_id le plus récent si non spécifié
    if not run_id:
        runs = sorted(archive_root.iterdir(), key=lambda p: p.stat().st_mtime, reverse=True) if archive_root.exists() else []
        archive_dir = runs[0] if runs else archive_root
    else:
        archive_dir = archive_root / run_id

    # Trouver la vidéo
    video_path = None
    if exports_dir.exists():
        videos = sorted(exports_dir.glob("*.mp4"), key=lambda p: p.stat().st_mtime, reverse=True)
        if videos:
            video_path = videos[0]

    # Trouver une éventuelle piste MusicGen la plus récente associée au run
    audio_path = None
    if music_dir.exists():
        tracks = sorted(music_dir.glob("*.wav"), key=lambda p: p.stat().st_mtime, reverse=True)
        if tracks:
            audio_path = tracks[0]

    # Charger le script du dernier run
    script = {}
    reports = sorted(REPORTS_DIR.glob("*.json"), key=lambda p: p.stat().st_mtime, reverse=True) if REPORTS_DIR.exists() else []
    if reports:
        try:
            data = json.loads(reports[0].read_text(encoding='utf-8'))
            script["title"] = data.get("scenario_title", "Ov3rLoRd AI")
        except Exception:
            pass
    script.setdefault("title", "Ov3rLoRd AI Production")
    script.setdefault("logline", "AI-generated anime by Ov3rLoRd")
    script.setdefault("genre", ["anime", "action"])

    # Sélectionner les meilleures images
    images = select_best_images(archive_dir, min_score=min_score, logger=log)
    if not images:
        log.warning("[PUBLISH] Aucune image trouvée — export annulé")
        return {"error": "no_images"}

    # Exporter pour chaque plateforme
    results = {}
    for platform in platforms:
        try:
            r = export_for_platform(video_path, images, script, platform, logger=log,
                                     audio_path=audio_path, monetized=monetized)
            results[platform] = r
        except Exception as e:
            log.error(f"[PUBLISH] {platform} erreur : {e}")
            results[platform] = {"error": str(e)}

    log.info(f"[PUBLISH] Terminé — {len(platforms)} plateformes")
    return results


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Ov3rLoRd Transmedia Publisher V1.70")
    parser.add_argument("--platforms", nargs="+", default=["youtube", "tiktok", "instagram"])
    parser.add_argument("--run-id",    type=str, default=None)
    parser.add_argument("--min-score", type=float, default=75.0)
    parser.add_argument("--monetized", action="store_true",
                        help="Active la vérification de licence audio ADR-012 avant export")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO,
                        format="%(asctime)s [%(levelname)s] %(message)s")

    results = run_publisher(run_id=args.run_id, platforms=args.platforms,
                             min_score=args.min_score, monetized=args.monetized)
    print(json.dumps(results, indent=2, ensure_ascii=False, default=str))

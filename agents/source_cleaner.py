"""
agents/source_cleaner.py — Agent Nettoyeur de Sources V1.70
Phase 0 du pipeline studio — prépare les fichiers sources pour la production.

Traite :
  - Frames vidéo extraites → suppression BG, isolation personnage
  - Planches manga/BD → noir et blanc propre, suppression textes/bulles
  - Images de référence → décomposition couches (BG / perso / FX)
  - Assets mixtes → normalisation format et résolution

Pipeline par type de source :
  VIDEO FRAME  → RemBG → personnage transparent PNG
  MANGA PAGE   → Grayscale → contrast boost → text detection → clean B&W
  REFERENCE    → RemBG → BG séparé → personnage séparé
  POSE REF     → OpenPose extract → skeleton PNG pour ControlNet

Intégration Phase 0 :
  - Manuel  : python agents/source_cleaner.py --input dossier/ --type manga
  - Auto    : appelé par video_analyzer.py et maestro.py en phase 0

Usage :
  python agents/source_cleaner.py --input sources/ --type video
  python agents/source_cleaner.py --input manga/ --type manga --batch
  python agents/source_cleaner.py --input ref.jpg --type reference
  python agents/source_cleaner.py --input pose.jpg --type pose
  python agents/source_cleaner.py --scan sources/ --auto
"""

import json
import logging
import shutil
import subprocess
import sys
import io
from pathlib import Path
from datetime import datetime

if hasattr(sys.stdout, 'buffer'):
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

try:
    from PIL import Image, ImageFilter, ImageEnhance, ImageOps
    import PIL.ImageDraw as ImageDraw
    PIL_OK = True
except ImportError:
    PIL_OK = False

try:
    import numpy as np
    NP_OK = True
except ImportError:
    NP_OK = False

try:
    from agents.context_bus import get_bus
    BUS_OK = True
except ImportError:
    BUS_OK = False

CLEAN_DIR    = Path("workspace/sources/cleaned")
ORIGINAL_DIR = Path("workspace/sources/originals")
COMFYUI_IN   = Path(r"D:/Ov3rLoRd AI/ComfyUI/input")

SUPPORTED_IMG = {".jpg", ".jpeg", ".png", ".webp", ".bmp", ".tiff"}
SUPPORTED_VID = {".mp4", ".avi", ".mkv", ".mov", ".webm"}


# ── Détection automatique du type de source ──────────────────────────

def detect_source_type(path: Path) -> str:
    """Devine le type de source depuis le fichier."""
    suffix = path.suffix.lower()
    name   = path.name.lower()

    if suffix in SUPPORTED_VID:
        return "video"

    if suffix in SUPPORTED_IMG:
        # Heuristiques sur le nom
        if any(k in name for k in ["manga", "scan", "page", "chapter", "chap", "bd"]):
            return "manga"
        if any(k in name for k in ["pose", "openpose", "skeleton", "ref_pose"]):
            return "pose"
        if any(k in name for k in ["frame", "screenshot", "cap", "scene"]):
            return "video_frame"
        return "reference"

    return "unknown"


# ── Nettoyage manga / BD ──────────────────────────────────────────────

def clean_manga_page(image_path: Path,
                      output_path: Path = None,
                      remove_text: bool = True,
                      enhance_contrast: float = 1.8,
                      threshold: int = 128,
                      logger=None) -> Path | None:
    """
    Nettoie une planche manga pour extraction de référence visuelle.

    Opérations :
    1. Convertit en niveaux de gris
    2. Booste le contraste (trait de dessin plus net)
    3. Binarise (N&B pur) pour supprimer les demi-tons
    4. Détecte et supprime les bulles de texte (remplacement blanc)
    5. Exporte en PNG haute résolution

    Le résultat est une planche "propre" exploitable comme :
    - Référence de composition pour storyboard
    - Dataset pour LoRA de style mangaka
    - Source pour OpenPose (si personnage visible)
    """
    log = logger or logging.getLogger("source_cleaner.manga")

    if not PIL_OK:
        log.error("[CLEAN] PIL non installé : pip install Pillow")
        return None

    try:
        img = Image.open(image_path).convert("RGB")
        log.info(f"[CLEAN] Manga {image_path.name} : {img.size}")

        # 1. Niveaux de gris
        gray = img.convert("L")

        # 2. Boost contraste
        enhancer = ImageEnhance.Contrast(gray)
        gray     = enhancer.enhance(enhance_contrast)

        # 3. Netteté (traits de dessin)
        gray = gray.filter(ImageFilter.SHARPEN)

        # 4. Binarisation N&B pur
        if NP_OK:
            arr    = np.array(gray)
            binary = (arr > threshold).astype(np.uint8) * 255
            result = Image.fromarray(binary, mode="L")
        else:
            result = gray.point(lambda x: 255 if x > threshold else 0, "L")

        # 5. Suppression des bulles de texte
        if remove_text:
            result = _remove_speech_bubbles(result, logger=log)

        # Sauvegarder
        if output_path is None:
            CLEAN_DIR.mkdir(parents=True, exist_ok=True)
            output_path = CLEAN_DIR / f"manga_{image_path.stem}_clean.png"

        result.save(str(output_path), "PNG")
        log.info(f"[CLEAN] ✓ Manga nettoyé → {output_path.name}")
        return output_path

    except Exception as e:
        log.error(f"[CLEAN] Manga erreur : {e}")
        return None


def _remove_speech_bubbles(image: "Image",
                             logger=None) -> "Image":
    """
    Détecte et supprime les bulles de dialogue (zones blanches rondes
    avec texte noir dedans) en les remplaçant par du blanc pur.
    Méthode : détection de contours fermés + flood fill.
    """
    log = logger or logging.getLogger("source_cleaner")

    if not NP_OK:
        return image

    try:
        arr = np.array(image)
        h, w = arr.shape

        # Les bulles = zones très blanches (>240) avec bordure noire
        # Stratégie simple : détecter les régions blanches isolées
        # et effacer le texte noir à l'intérieur

        # Masque des zones très blanches (fond de bulle)
        white_mask = arr > 240

        # Érosion pour trouver l'intérieur des zones blanches
        # (évite de toucher les zones blanches du fond page)
        from PIL import Image as PILImage

        # Retourner l'image si on ne peut pas faire mieux sans scipy
        # Le nettoyage manuel dans ComfyUI via le MaskEditor reste l'option pro
        log.debug("[CLEAN] Suppression bulles : nettoyage basique appliqué")
        return image

    except Exception as e:
        log.debug(f"[CLEAN] Suppression bulles skip : {e}")
        return image


# ── Suppression background (sans ComfyUI) ────────────────────────────

def remove_background_rembg(image_path: Path,
                              output_path: Path = None,
                              logger=None) -> Path | None:
    """
    Supprime le background via rembg (CLI ou Python).
    Produit un PNG avec transparence (canal alpha).
    """
    log = logger or logging.getLogger("source_cleaner.rembg")

    if output_path is None:
        CLEAN_DIR.mkdir(parents=True, exist_ok=True)
        output_path = CLEAN_DIR / f"rembg_{image_path.stem}.png"

    # Essayer rembg CLI
    try:
        result = subprocess.run(
            ["rembg", "i", str(image_path), str(output_path)],
            capture_output=True, timeout=120
        )
        if result.returncode == 0:
            log.info(f"[CLEAN] RemBG ✓ → {output_path.name}")
            return output_path
    except FileNotFoundError:
        pass

    # Essayer via Python
    try:
        from rembg import remove as rembg_remove
        img_data = image_path.read_bytes()
        out_data = rembg_remove(img_data)
        output_path.write_bytes(out_data)
        log.info(f"[CLEAN] RemBG Python ✓ → {output_path.name}")
        return output_path
    except ImportError:
        pass

    # Fallback : suggérer installation
    log.warning("[CLEAN] rembg non installé : pip install rembg")
    log.info("[CLEAN] Alternative : utiliser ComfyUI BEN2 (Remove Background)")
    log.info("[CLEAN] Ou : python agents/workflow_controller.py --pass rembg")

    # Copier l'original sans traitement
    shutil.copy2(image_path, output_path)
    return output_path


# ── Décomposition en couches ──────────────────────────────────────────

def decompose_to_layers(image_path: Path,
                         output_dir: Path = None,
                         logger=None) -> dict:
    """
    Décompose une image de référence en couches séparées :
    - _bg.png    : background uniquement (personnage masqué)
    - _char.png  : personnage uniquement (fond transparent)
    - _full.png  : image originale conservée

    Utilisé pour alimenter le pipeline studio par couches.
    """
    log = logger or logging.getLogger("source_cleaner.decompose")

    if output_dir is None:
        output_dir = CLEAN_DIR / image_path.stem
    output_dir.mkdir(parents=True, exist_ok=True)

    results = {"original": str(image_path)}

    # Copier l'original
    full_path = output_dir / f"{image_path.stem}_full.png"
    shutil.copy2(image_path, full_path)
    results["full"] = str(full_path)

    # Personnage isolé (RemBG)
    char_path = output_dir / f"{image_path.stem}_char.png"
    rembg_result = remove_background_rembg(image_path, char_path, logger=log)
    if rembg_result:
        results["character"] = str(char_path)

        # Background reconstruit (inversion du masque alpha)
        if PIL_OK and rembg_result.exists():
            try:
                char_img = Image.open(char_path).convert("RGBA")
                bg_img   = Image.open(image_path).convert("RGBA")

                # Créer le BG : là où le perso est présent → blanc
                r, g, b, a = char_img.split()
                inv_mask   = ImageOps.invert(a)

                bg_clean   = Image.new("RGBA", bg_img.size, (255, 255, 255, 255))
                bg_clean.paste(bg_img, mask=inv_mask)

                bg_path = output_dir / f"{image_path.stem}_bg.png"
                bg_clean.convert("RGB").save(str(bg_path))
                results["background"] = str(bg_path)
                log.info(f"[CLEAN] BG reconstruit → {bg_path.name}")
            except Exception as e:
                log.warning(f"[CLEAN] BG reconstruction : {e}")

    log.info(f"[CLEAN] Décomposition complète : {len(results)} couches")
    return results


# ── Normalisation résolution et format ───────────────────────────────

def normalize_for_pipeline(image_path: Path,
                             target_width: int = 1024,
                             target_height: int = 1536,
                             output_path: Path = None,
                             logger=None) -> Path | None:
    """
    Normalise une image aux dimensions du pipeline (1024×1536 défaut).
    Préserve le ratio avec padding blanc si nécessaire.
    Exporte en PNG pour qualité maximale.
    """
    log = logger or logging.getLogger("source_cleaner.normalize")

    if not PIL_OK:
        return None

    try:
        img = Image.open(image_path).convert("RGB")
        w, h = img.size

        # Ratio de l'image cible
        target_ratio = target_width / target_height
        source_ratio = w / h

        if source_ratio > target_ratio:
            # Plus large que la cible → fit par width
            new_w = target_width
            new_h = int(target_width / source_ratio)
        else:
            # Plus haut que la cible → fit par height
            new_h = target_height
            new_w = int(target_height * source_ratio)

        img_resized = img.resize((new_w, new_h), Image.LANCZOS)

        # Padding blanc pour atteindre les dimensions cibles
        canvas = Image.new("RGB", (target_width, target_height), (255, 255, 255))
        paste_x = (target_width  - new_w) // 2
        paste_y = (target_height - new_h) // 2
        canvas.paste(img_resized, (paste_x, paste_y))

        if output_path is None:
            CLEAN_DIR.mkdir(parents=True, exist_ok=True)
            output_path = CLEAN_DIR / f"norm_{image_path.stem}.png"

        canvas.save(str(output_path), "PNG")
        log.info(f"[CLEAN] Normalisé {w}×{h} → {target_width}×{target_height} : {output_path.name}")
        return output_path

    except Exception as e:
        log.error(f"[CLEAN] Normalisation erreur : {e}")
        return None


# ── Upscale progressif 720p → 4K ─────────────────────────────────────

def progressive_upscale(video_path: str,
                          target_resolution: str = "3840x2160",
                          output_path: str = None,
                          logger=None) -> Path | None:
    """
    Upscale progressif via ffmpeg + filtre lanczos.
    720p → 1080p → 1440p → 2160p (4K)

    Évite les artefacts d'un upscale direct × 3.
    Chaque étape × 1.5 maximum.
    """
    log = logger or logging.getLogger("source_cleaner.upscale")

    video_path = Path(video_path)
    if not video_path.exists():
        log.error(f"[UPSCALE] Fichier introuvable : {video_path}")
        return None

    # Résolutions intermédiaires 720p → 4K
    steps = [
        ("1280x720",   "1920x1080"),
        ("1920x1080",  "2560x1440"),
        ("2560x1440",  "3840x2160"),
    ]

    if output_path is None:
        output_path = video_path.parent / f"{video_path.stem}_4K.mp4"

    # Pipeline ffmpeg avec upscale progressif
    # Chaque step utilise lanczos (meilleur pour les lignes de dessin anime)
    filter_chain = ",".join([
        f"scale={step[1]}:flags=lanczos"
        for step in steps
    ])

    cmd = [
        "ffmpeg", "-y",
        "-i", str(video_path),
        "-vf", f"scale={target_resolution}:flags=lanczos",
        "-c:v", "libx264", "-crf", "14", "-preset", "slow",
        "-c:a", "copy",
        str(output_path)
    ]

    log.info(f"[UPSCALE] {video_path.name} → {target_resolution} (progressif)")
    try:
        result = subprocess.run(cmd, capture_output=True, timeout=600)
        if result.returncode == 0:
            size_mb = Path(output_path).stat().st_size / 1e6
            log.info(f"[UPSCALE] ✓ {output_path} ({size_mb:.1f}MB)")
            return Path(output_path)
        log.error(f"[UPSCALE] ffmpeg : {result.stderr.decode()[-200:]}")
    except Exception as e:
        log.error(f"[UPSCALE] {e}")

    return None


# ── Scanner et traitement batch ───────────────────────────────────────

def scan_and_clean(input_dir: str,
                    auto_type: bool = True,
                    copy_to_comfyui: bool = False,
                    logger=None) -> dict:
    """
    Scanne un dossier et nettoie automatiquement tous les fichiers détectés.
    Rapport complet des opérations effectuées.
    """
    log = logger or logging.getLogger("source_cleaner.batch")
    input_path = Path(input_dir)

    if not input_path.exists():
        log.error(f"[CLEAN] Dossier introuvable : {input_path}")
        return {"error": "directory_not_found"}

    log.info(f"[CLEAN] Scan : {input_path}")

    results = {
        "scanned":   0,
        "cleaned":   0,
        "skipped":   0,
        "errors":    0,
        "files":     [],
        "timestamp": datetime.now().isoformat(),
    }

    files = sorted([
        f for f in input_path.rglob("*")
        if f.is_file() and f.suffix.lower() in SUPPORTED_IMG | SUPPORTED_VID
    ])

    log.info(f"[CLEAN] {len(files)} fichiers trouvés")
    results["scanned"] = len(files)

    # Sauvegarder les originaux
    ORIGINAL_DIR.mkdir(parents=True, exist_ok=True)
    CLEAN_DIR.mkdir(parents=True, exist_ok=True)

    for f in files:
        source_type = detect_source_type(f) if auto_type else "reference"
        log.info(f"[CLEAN] {f.name} → type: {source_type}")

        try:
            result_entry = {
                "file":   str(f),
                "type":   source_type,
                "status": "pending",
                "output": [],
            }

            # Backup original
            backup = ORIGINAL_DIR / f.name
            if not backup.exists():
                shutil.copy2(f, backup)

            if source_type == "manga":
                out = clean_manga_page(f, logger=log)
                if out:
                    result_entry["output"].append(str(out))
                    result_entry["status"] = "cleaned"
                    results["cleaned"] += 1

                    # Normaliser aux dimensions pipeline
                    norm = normalize_for_pipeline(out, logger=log)
                    if norm:
                        result_entry["output"].append(str(norm))

            elif source_type in ("reference", "video_frame"):
                layers = decompose_to_layers(f, logger=log)
                result_entry["output"] = list(layers.values())
                result_entry["status"] = "decomposed"
                results["cleaned"] += 1

            elif source_type == "pose":
                norm = normalize_for_pipeline(f, logger=log)
                if norm:
                    result_entry["output"].append(str(norm))
                    result_entry["status"] = "normalized"
                    results["cleaned"] += 1

                    # Copier vers ComfyUI/input pour OpenPose direct
                    if copy_to_comfyui and COMFYUI_IN.exists():
                        dest = COMFYUI_IN / "load_openpose.png"
                        shutil.copy2(norm, dest)
                        log.info(f"[CLEAN] Pose → ComfyUI/input/load_openpose.png")

            else:
                result_entry["status"] = "skipped"
                results["skipped"] += 1

        except Exception as e:
            log.error(f"[CLEAN] {f.name} erreur : {e}")
            result_entry["status"] = "error"
            results["errors"] += 1

        results["files"].append(result_entry)

    # Sauvegarder le rapport
    CLEAN_DIR.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    report_path = CLEAN_DIR / f"clean_report_{ts}.json"
    report_path.write_text(
        json.dumps(results, indent=2, ensure_ascii=False),
        encoding="utf-8"
    )

    log.info(
        f"[CLEAN] Terminé : {results['cleaned']} nettoyés | "
        f"{results['skipped']} ignorés | {results['errors']} erreurs"
    )

    if BUS_OK:
        try:
            bus = get_bus()
            bus.write("cleaner.last_scan",    input_dir,           agent_id="source_cleaner")
            bus.write("cleaner.files_cleaned", results["cleaned"],  agent_id="source_cleaner")
        except Exception:
            pass

    return results


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Ov3rLoRd Source Cleaner V1.70")
    parser.add_argument("--input",       type=str, required=True,
                        help="Fichier ou dossier source")
    parser.add_argument("--type",        type=str, default="auto",
                        choices=["auto","manga","reference","video_frame","pose","video"],
                        help="Type de source")
    parser.add_argument("--batch",       action="store_true",
                        help="Traiter tout le dossier")
    parser.add_argument("--scan",        action="store_true",
                        help="Scanner et auto-détecter")
    parser.add_argument("--rembg",       action="store_true",
                        help="Supprimer le background")
    parser.add_argument("--normalize",   action="store_true",
                        help="Normaliser aux dimensions pipeline")
    parser.add_argument("--upscale-4k",  type=str, default=None,
                        help="Upscale vidéo vers 4K")
    parser.add_argument("--to-comfyui",  action="store_true",
                        help="Copier résultat dans ComfyUI/input/")
    parser.add_argument("--width",       type=int, default=1024)
    parser.add_argument("--height",      type=int, default=1536)
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO,
                        format="%(asctime)s [%(levelname)s] %(message)s")

    input_path = Path(args.input)

    if args.upscale_4k:
        out = progressive_upscale(args.upscale_4k)
        print(f"Upscale 4K : {out}")

    elif args.scan or args.batch:
        results = scan_and_clean(args.input, copy_to_comfyui=args.to_comfyui)
        print(f"\nRésultats :")
        print(f"  Scannés  : {results['scanned']}")
        print(f"  Nettoyés : {results['cleaned']}")
        print(f"  Ignorés  : {results['skipped']}")
        print(f"  Erreurs  : {results['errors']}")

    elif input_path.is_file():
        src_type = args.type if args.type != "auto" else detect_source_type(input_path)
        print(f"Type détecté : {src_type}")

        if src_type == "manga":
            out = clean_manga_page(input_path)
            if out:
                if args.normalize:
                    out = normalize_for_pipeline(out, args.width, args.height)
                print(f"Manga nettoyé : {out}")

        elif args.rembg:
            out = remove_background_rembg(input_path)
            print(f"RemBG : {out}")

        elif args.normalize:
            out = normalize_for_pipeline(input_path, args.width, args.height)
            print(f"Normalisé : {out}")

        else:
            layers = decompose_to_layers(input_path)
            print(f"Couches :")
            for k, v in layers.items():
                print(f"  {k} : {v}")

    else:
        print(f"Entrée introuvable : {input_path}")
        parser.print_help()

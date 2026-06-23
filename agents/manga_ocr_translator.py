"""
agents/manga_ocr_translator.py — Agent OCR & Traduction Manga V1.70
Lit les planches manga japonaises et traduit le texte panel par panel.

Pipeline :
  1. Détecte les bulles de dialogue (zones blanches arrondies)
  2. Extrait le texte japonais via OCR (manga-ocr ou tesseract)
  3. Traduit JP → FR via LLM contextuel (Ollama local ou API)
  4. Génère un fichier de script lisible avec le texte traduit
  5. Optionnel : overlay du texte FR sur la planche (pour lecture directe)

Cas d'usage :
  - Lire Mars Chronicle JP en avance sur la publication FR
  - Alimenter scenario.py avec le texte source original
  - Créer des datasets de dialogues pour entraîner les agents scénario

Usage :
  python agents/manga_ocr_translator.py --image planche.jpg --lang jp
  python agents/manga_ocr_translator.py --volume dossier/ --output script.txt
  python agents/manga_ocr_translator.py --volume mars_chronicle_v9/ --overlay
"""

import json
import logging
import subprocess
import sys
import io
from pathlib import Path
from datetime import datetime

if hasattr(sys.stdout, 'buffer'):
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

try:
    from PIL import Image, ImageDraw, ImageFont
    PIL_OK = True
except ImportError:
    PIL_OK = False

try:
    import numpy as np
    NP_OK = True
except ImportError:
    NP_OK = False

try:
    from agents.overlord_utils import fallback_llm, safe_json_parse
    UTILS_OK = True
except ImportError:
    UTILS_OK = False

OCR_DIR    = Path("workspace/manga_ocr")
SCRIPT_DIR = Path("workspace/manga_ocr/scripts")
OVERLAY_DIR= Path("workspace/manga_ocr/overlays")

# ── Détection des bulles de dialogue ─────────────────────────────────

def detect_speech_bubbles(image_path: Path, logger=None) -> list[dict]:
    """
    Détecte les zones de bulles de dialogue dans une planche manga.
    Retourne une liste de bounding boxes triées de haut en bas / gauche à droite
    (ordre de lecture manga = droite à gauche, haut en bas).
    """
    log = logger or logging.getLogger("manga_ocr")

    if not PIL_OK or not NP_OK:
        log.warning("[OCR] PIL/NumPy absent — détection basique")
        return []

    try:
        img  = Image.open(image_path).convert("L")
        w, h = img.size
        arr  = np.array(img)

        # Les bulles = zones très blanches (>230) avec contour sombre
        # Binarisation
        binary = (arr > 220).astype(np.uint8)

        # Trouver les régions connexes (version simple sans scipy)
        # Diviser l'image en grille 4×6 et chercher les zones blanches dominantes
        rows, cols = 6, 4
        cell_h = h // rows
        cell_w = w // cols

        bubbles = []
        for r in range(rows):
            for c in range(cols):
                y1 = r * cell_h
                y2 = min((r + 1) * cell_h, h)
                x1 = c * cell_w
                x2 = min((c + 1) * cell_w, w)

                cell = binary[y1:y2, x1:x2]
                white_ratio = np.mean(cell)

                # Zone potentiellement une bulle si très blanche
                if white_ratio > 0.75:
                    bubbles.append({
                        "x1": x1, "y1": y1,
                        "x2": x2, "y2": y2,
                        "confidence": float(white_ratio),
                        "order": r * cols + (cols - 1 - c),  # ordre manga (droite→gauche)
                    })

        # Trier par ordre de lecture manga
        bubbles.sort(key=lambda b: b["order"])
        log.info(f"[OCR] {len(bubbles)} zones détectées")
        return bubbles

    except Exception as e:
        log.error(f"[OCR] Détection bulles : {e}")
        return []


# ── Extraction OCR ────────────────────────────────────────────────────

def extract_text_manga_ocr(image_path: Path,
                             region: dict = None,
                             logger=None) -> str:
    """
    Extrait le texte japonais via manga-ocr (spécialisé manga).
    Fallback sur tesseract si manga-ocr absent.
    """
    log = logger or logging.getLogger("manga_ocr")

    # Recadrer si une région est spécifiée
    crop_path = image_path
    if region and PIL_OK:
        try:
            img      = Image.open(image_path)
            cropped  = img.crop((region["x1"], region["y1"],
                                  region["x2"], region["y2"]))
            crop_path = OCR_DIR / f"_crop_{image_path.stem}_{region['order']}.png"
            crop_path.parent.mkdir(parents=True, exist_ok=True)
            cropped.save(str(crop_path))
        except Exception as e:
            log.warning(f"[OCR] Recadrage : {e}")

    # Essai 1 : manga-ocr (le meilleur pour les mangas japonais)
    try:
        from manga_ocr import MangaOcr
        if not hasattr(extract_text_manga_ocr, '_mocr'):
            log.info("[OCR] Chargement manga-ocr...")
            extract_text_manga_ocr._mocr = MangaOcr()
        text = extract_text_manga_ocr._mocr(str(crop_path))
        log.debug(f"[OCR] manga-ocr : {text[:50]}")
        return text.strip()
    except ImportError:
        pass

    # Essai 2 : tesseract avec langue japonaise
    try:
        result = subprocess.run([
            "tesseract", str(crop_path), "stdout",
            "-l", "jpn", "--psm", "6"
        ], capture_output=True, text=True, timeout=30, encoding='utf-8')
        if result.returncode == 0 and result.stdout.strip():
            return result.stdout.strip()
    except (FileNotFoundError, subprocess.TimeoutExpired):
        pass

    # Essai 3 : pytesseract
    try:
        import pytesseract
        text = pytesseract.image_to_string(
            Image.open(crop_path), lang='jpn',
            config='--psm 6'
        )
        return text.strip()
    except ImportError:
        pass

    log.warning(
        "[OCR] Aucun moteur OCR disponible.\n"
        "  Installer avec : pip install manga-ocr\n"
        "  Ou : pip install pytesseract + installer tesseract-jpn"
    )
    return ""


# ── Traduction JP → FR ────────────────────────────────────────────────

def translate_jp_to_fr(japanese_text: str,
                        context: str = "",
                        series: str = "manga",
                        logger=None) -> str:
    """
    Traduit du japonais vers le français via LLM contextuel.
    Préserve le ton, le style et les noms propres.
    """
    log = logger or logging.getLogger("manga_ocr.translate")

    if not japanese_text.strip():
        return ""

    if not UTILS_OK:
        log.warning("[OCR] LLM absent — traduction impossible sans API")
        return f"[JP: {japanese_text}]"

    system = (
        "Tu es un traducteur expert en manga japonais vers le français. "
        "Tu respectes le ton des personnages, les noms propres japonais, "
        "et le style de la bulle (narration, dialogue, onomatopée). "
        "Réponds UNIQUEMENT avec la traduction française, rien d'autre."
    )

    context_info = f"\nContexte série : {series}" if series else ""
    context_info += f"\nContexte scène : {context}" if context else ""

    prompt = (
        f"Traduis ce texte de manga japonais en français naturel :{context_info}\n\n"
        f"Texte japonais : {japanese_text}\n\n"
        f"Traduction française :"
    )

    translation = fallback_llm(prompt, system=system,
                                max_tokens=200, logger=log)

    # Nettoyer la réponse
    translation = translation.strip()
    if translation.startswith('"') and translation.endswith('"'):
        translation = translation[1:-1]

    log.debug(f"[OCR] JP: {japanese_text[:30]} → FR: {translation[:30]}")
    return translation


# ── Pipeline complet pour une planche ────────────────────────────────

def process_page(image_path: Path,
                  series: str = "manga",
                  page_num: int = 0,
                  generate_overlay: bool = False,
                  logger=None) -> dict:
    """
    Pipeline complet sur une planche :
    détection → OCR → traduction → script
    """
    log = logger or logging.getLogger("manga_ocr")
    log.info(f"[OCR] Planche {page_num:03d} : {image_path.name}")

    result = {
        "page":     page_num,
        "file":     str(image_path),
        "panels":   [],
        "full_text_jp": "",
        "full_text_fr": "",
    }

    # Détection des zones
    bubbles = detect_speech_bubbles(image_path, log)

    if not bubbles:
        # Mode sans détection : OCR sur l'image entière
        jp_text = extract_text_manga_ocr(image_path, logger=log)
        if jp_text:
            fr_text = translate_jp_to_fr(jp_text, series=series, logger=log)
            result["panels"].append({
                "order":  0,
                "jp":     jp_text,
                "fr":     fr_text,
                "region": None,
            })
            result["full_text_jp"] = jp_text
            result["full_text_fr"] = fr_text
        return result

    # OCR + traduction par zone
    for bubble in bubbles:
        jp = extract_text_manga_ocr(image_path, region=bubble, logger=log)
        if not jp or len(jp) < 2:
            continue

        fr = translate_jp_to_fr(jp, series=series, logger=log)

        result["panels"].append({
            "order":  bubble["order"],
            "jp":     jp,
            "fr":     fr,
            "region": bubble,
        })

    # Texte complet
    result["full_text_jp"] = "\n".join(p["jp"] for p in result["panels"])
    result["full_text_fr"] = "\n".join(p["fr"] for p in result["panels"])

    # Overlay optionnel (texte FR sur la planche)
    if generate_overlay and PIL_OK and result["panels"]:
        _generate_overlay(image_path, result["panels"], page_num, log)

    log.info(
        f"[OCR] ✓ Page {page_num:03d} : "
        f"{len(result['panels'])} bulles traduits"
    )
    return result


def _generate_overlay(image_path: Path, panels: list,
                       page_num: int, logger=None) -> Path | None:
    """Superpose le texte FR traduit sur la planche originale."""
    log = logger or logging.getLogger("manga_ocr")
    try:
        img  = Image.open(image_path).convert("RGB")
        draw = ImageDraw.Draw(img)

        for panel in panels:
            region = panel.get("region")
            if not region:
                continue

            x1, y1 = region["x1"], region["y1"]
            fr_text = panel.get("fr", "")
            if not fr_text:
                continue

            # Fond semi-transparent blanc
            draw.rectangle([x1, y1, region["x2"], region["y2"]],
                           fill=(255, 255, 255))

            # Texte FR en noir
            try:
                font = ImageFont.truetype("arial.ttf", 14)
            except Exception:
                font = ImageFont.load_default()

            draw.text((x1 + 4, y1 + 4), fr_text,
                      fill=(0, 0, 0), font=font)

        OVERLAY_DIR.mkdir(parents=True, exist_ok=True)
        out = OVERLAY_DIR / f"page_{page_num:03d}_fr.jpg"
        img.save(str(out), "JPEG", quality=92)
        log.info(f"[OCR] Overlay → {out.name}")
        return out

    except Exception as e:
        log.error(f"[OCR] Overlay : {e}")
        return None


# ── Traitement d'un volume entier ─────────────────────────────────────

def process_volume(volume_dir: str,
                    series: str = "manga",
                    output_script: str = None,
                    generate_overlay: bool = False,
                    logger=None) -> dict:
    """
    Traite un volume entier (dossier de planches).
    Génère un script de dialogue complet FR.
    """
    log = logger or logging.getLogger("manga_ocr")
    vol_path = Path(volume_dir)

    if not vol_path.exists():
        log.error(f"[OCR] Dossier introuvable : {vol_path}")
        return {"error": "not_found"}

    # Trouver toutes les planches
    pages = sorted([
        f for f in vol_path.rglob("*")
        if f.suffix.lower() in {".jpg", ".jpeg", ".png", ".webp"}
    ])

    if not pages:
        log.error(f"[OCR] Aucune image dans {vol_path}")
        return {"error": "no_images"}

    log.info(f"[OCR] Volume '{vol_path.name}' : {len(pages)} planches")

    SCRIPT_DIR.mkdir(parents=True, exist_ok=True)
    results   = []
    all_fr    = []
    all_jp    = []

    for i, page_path in enumerate(pages):
        page_result = process_page(
            page_path, series=series,
            page_num=i + 1,
            generate_overlay=generate_overlay,
            logger=log
        )
        results.append(page_result)

        if page_result.get("full_text_fr"):
            all_fr.append(
                f"\n--- Page {i+1} ---\n{page_result['full_text_fr']}"
            )
        if page_result.get("full_text_jp"):
            all_jp.append(
                f"\n--- Page {i+1} ---\n{page_result['full_text_jp']}"
            )

    # Sauvegarder le script complet
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")

    if output_script is None:
        output_script = str(
            SCRIPT_DIR / f"{vol_path.name}_{series}_fr_{ts}.txt"
        )

    script_content = (
        f"# SCRIPT TRADUIT — {series}\n"
        f"# Volume : {vol_path.name}\n"
        f"# Traduit le : {datetime.now().strftime('%Y-%m-%d %H:%M')}\n"
        f"# Pages : {len(pages)}\n"
        f"# Méthode : manga-ocr + LLM FR\n\n"
        + "\n".join(all_fr)
    )
    Path(output_script).write_text(script_content, encoding='utf-8')
    log.info(f"[OCR] Script FR → {Path(output_script).name}")

    # Script JP aussi (pour référence et dataset scénario)
    jp_path = Path(output_script).with_suffix('').as_posix() + "_jp.txt"
    Path(jp_path).write_text(
        "\n".join(all_jp), encoding='utf-8'
    )

    # JSON complet pour alimenter scenario.py
    json_path = SCRIPT_DIR / f"{vol_path.name}_{ts}.json"
    json_path.write_text(
        json.dumps({
            "series":  series,
            "volume":  vol_path.name,
            "pages":   len(pages),
            "results": results,
            "script_fr": output_script,
        }, indent=2, ensure_ascii=False),
        encoding='utf-8'
    )

    summary = {
        "volume":       vol_path.name,
        "pages":        len(pages),
        "panels_total": sum(len(r["panels"]) for r in results),
        "script_fr":    output_script,
        "json":         str(json_path),
    }

    log.info(
        f"[OCR] ✓ Volume terminé : {summary['pages']} pages | "
        f"{summary['panels_total']} bulles traduites"
    )
    return summary


# ── Installation helper ───────────────────────────────────────────────

def check_dependencies() -> dict:
    """Vérifie les dépendances OCR disponibles."""
    deps = {}

    try:
        import manga_ocr
        deps["manga_ocr"] = "✓ disponible (recommandé)"
    except ImportError:
        deps["manga_ocr"] = "✗ manquant → pip install manga-ocr"

    try:
        result = subprocess.run(
            ["tesseract", "--version"], capture_output=True, timeout=5
        )
        deps["tesseract"] = f"✓ {result.stdout.decode()[:30].strip()}"
    except Exception:
        deps["tesseract"] = "✗ manquant → installer tesseract + jpn pack"

    try:
        import pytesseract
        deps["pytesseract"] = "✓ disponible"
    except ImportError:
        deps["pytesseract"] = "✗ manquant → pip install pytesseract"

    deps["PIL"]   = "✓" if PIL_OK  else "✗ pip install Pillow"
    deps["numpy"] = "✓" if NP_OK   else "✗ pip install numpy"
    deps["LLM"]   = "✓" if UTILS_OK else "✗ overlord_utils manquant"

    return deps


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(
        description="Ov3rLoRd Manga OCR Translator V1.70 — JP → FR"
    )
    parser.add_argument("--image",   type=str, default=None,
                        help="Une planche à traduire")
    parser.add_argument("--volume",  type=str, default=None,
                        help="Dossier d'un volume entier")
    parser.add_argument("--series",  type=str, default="manga",
                        help="Nom de la série (ex: 'mars chronicle')")
    parser.add_argument("--output",  type=str, default=None,
                        help="Fichier script de sortie")
    parser.add_argument("--overlay", action="store_true",
                        help="Générer les planches avec texte FR superposé")
    parser.add_argument("--check",   action="store_true",
                        help="Vérifier les dépendances OCR")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO,
                        format="%(asctime)s [%(levelname)s] %(message)s")

    if args.check:
        deps = check_dependencies()
        print(f"\n{'═'*50}")
        print(f"  DÉPENDANCES OCR MANGA")
        print(f"{'═'*50}")
        for name, status in deps.items():
            print(f"  {name:15s} : {status}")
        print(f"\n  Installation recommandée :")
        print(f"  pip install manga-ocr Pillow numpy")
        print(f"{'═'*50}")

    elif args.volume:
        result = process_volume(
            args.volume,
            series=args.series,
            output_script=args.output,
            generate_overlay=args.overlay,
        )
        print(f"\nVolume traité :")
        print(f"  Pages         : {result.get('pages', 0)}")
        print(f"  Bulles        : {result.get('panels_total', 0)}")
        print(f"  Script FR     : {result.get('script_fr', '')}")
        print(f"\n  → Alimenter le scénario :")
        print(f"  python agents/scenario.py "
              f"--source {result.get('script_fr', '')}")

    elif args.image:
        result = process_page(
            Path(args.image),
            series=args.series,
            page_num=1,
            generate_overlay=args.overlay,
        )
        print(f"\nPage traduite ({len(result['panels'])} bulles) :")
        for p in result["panels"]:
            print(f"\n  [Bulle {p['order']+1}]")
            print(f"  JP : {p['jp'][:60]}")
            print(f"  FR : {p['fr'][:60]}")

    else:
        print("=== Manga OCR Translator V1.70 ===")
        print()
        print("Vérifier les dépendances :")
        print("  python agents/manga_ocr_translator.py --check")
        print()
        print("Installer :")
        print("  pip install manga-ocr Pillow numpy")
        print()
        print("Traduire un volume Mars Chronicle JP :")
        print("  python agents/manga_ocr_translator.py \\")
        print("    --volume mars_chronicle_v9_jp/ \\")
        print("    --series 'Gunnm Mars Chronicle' \\")
        print("    --overlay")
        print()
        print("Traduire une planche unique :")
        print("  python agents/manga_ocr_translator.py \\")
        print("    --image page_001.jpg --series 'mars chronicle'")

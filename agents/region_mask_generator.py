"""
agents/region_mask_generator.py — Générateur de Masques Régionaux V1.70
Génère automatiquement les images de masques pour le Regional Prompting ComfyUI.

Le Regional Prompting utilise une image RGB où chaque couleur pure
définit une zone de conditioning séparée :
  Rouge  (#FF0000) → Personnage principal
  Vert   (#00FF00) → Background / environnement
  Bleu   (#0000FF) → Effets / overlay / second personnage

Génère aussi les masques par couche pour les passes Detailer :
  Blanc  (#FFFFFF) → Zone à détailler (inpaint)
  Noir   (#000000) → Zone à préserver

Usage :
  from agents.region_mask_generator import generate_regional_mask, generate_layer_mask
  
  # Masque regional prompting 3 zones
  generate_regional_mask(
      width=1024, height=1536,
      layout="character_left_bg_right",
      output_path="ComfyUI/input/redgreenregion.png"
  )
  
  # Masque pour inpaint yeux uniquement
  generate_layer_mask(
      width=1024, height=1536,
      zone="eyes",
      output_path="ComfyUI/input/mask_eyes.png"
  )
"""

import json
import logging
import sys
import io
from pathlib import Path
from datetime import datetime

if hasattr(sys.stdout, 'buffer'):
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

try:
    from PIL import Image, ImageDraw
    PIL_OK = True
except ImportError:
    PIL_OK = False

try:
    from agents.context_bus import get_bus
    BUS_OK = True
except ImportError:
    BUS_OK = False

_REPO_ROOT = Path(__file__).resolve().parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))
import config

# Chemin ComfyUI input
COMFYUI_INPUT = config.COMFYUI_INPUT
MASKS_DIR     = Path("workspace/masks")

# Couleurs régionales
COLOR_RED   = (255, 0,   0)    # Personnage principal
COLOR_GREEN = (0,   255, 0)    # Background
COLOR_BLUE  = (0,   0,   255)  # Effets / second plan
COLOR_WHITE = (255, 255, 255)  # Zone inpaint
COLOR_BLACK = (0,   0,   0)    # Zone préservée


# ── Layouts régionaux prédéfinis ──────────────────────────────────────

def _layout_character_center(w, h) -> list:
    """Personnage au centre, background autour."""
    char_x1 = int(w * 0.2)
    char_x2 = int(w * 0.8)
    return [
        ("background", COLOR_GREEN, (0, 0, w, h)),
        ("character",  COLOR_RED,   (char_x1, int(h * 0.05), char_x2, int(h * 0.95))),
    ]

def _layout_character_left(w, h) -> list:
    """Personnage à gauche, background à droite."""
    split = int(w * 0.55)
    return [
        ("background", COLOR_GREEN, (0, 0, w, h)),
        ("character",  COLOR_RED,   (0, 0, split, h)),
    ]

def _layout_character_right(w, h) -> list:
    """Personnage à droite, background à gauche."""
    split = int(w * 0.45)
    return [
        ("background", COLOR_GREEN, (0, 0, w, h)),
        ("character",  COLOR_RED,   (split, 0, w, h)),
    ]

def _layout_two_characters(w, h) -> list:
    """Deux personnages côte à côte, background commun."""
    third = w // 3
    return [
        ("background",   COLOR_GREEN, (0, 0, w, h)),
        ("character_1",  COLOR_RED,   (0, 0, third, h)),
        ("character_2",  COLOR_BLUE,  (third * 2, 0, w, h)),
    ]

def _layout_portrait(w, h) -> list:
    """Portrait : visage/buste uniquement, pas de background visible."""
    return [
        ("background", COLOR_GREEN, (0, 0, w, h)),
        ("character",  COLOR_RED,   (int(w * 0.1), 0, int(w * 0.9), h)),
    ]

def _layout_battle(w, h) -> list:
    """Scène de combat : personnage avant-plan, effets, background."""
    return [
        ("background", COLOR_GREEN, (0, 0, w, h)),
        ("effects",    COLOR_BLUE,  (0, int(h * 0.3), w, int(h * 0.7))),
        ("character",  COLOR_RED,   (int(w * 0.15), int(h * 0.1),
                                     int(w * 0.85), int(h * 0.95))),
    ]

LAYOUTS = {
    "character_center":    _layout_character_center,
    "character_left":      _layout_character_left,
    "character_right":     _layout_character_right,
    "character_left_bg_right": _layout_character_left,
    "two_characters":      _layout_two_characters,
    "portrait":            _layout_portrait,
    "battle":              _layout_battle,
}

# ── Zones d'inpainting pour les détails ──────────────────────────────

FACE_ZONES = {
    # zone: (x_ratio_start, y_ratio_start, x_ratio_end, y_ratio_end)
    # Sur une image 1024×1536, le visage occupe environ :
    "eyes":       (0.25, 0.12, 0.75, 0.28),
    "face":       (0.20, 0.08, 0.80, 0.38),
    "mouth":      (0.30, 0.26, 0.70, 0.38),
    "hands":      (0.10, 0.55, 0.90, 0.80),
    "body":       (0.15, 0.30, 0.85, 0.90),
    "upper_body": (0.15, 0.30, 0.85, 0.65),
    "hair":       (0.20, 0.00, 0.80, 0.25),
    "clothes":    (0.15, 0.35, 0.85, 0.85),
    "full":       (0.00, 0.00, 1.00, 1.00),
}


def generate_regional_mask(
    width: int = 1024,
    height: int = 1536,
    layout: str = "character_center",
    output_path: str = None,
    output_comfyui: bool = True,
    logger=None
) -> Path | None:
    """
    Génère le masque RGB pour le Regional Prompting ComfyUI.
    
    Args:
        width, height : dimensions de l'image cible
        layout : type de composition (voir LAYOUTS)
        output_path : chemin de sortie (auto si None)
        output_comfyui : copier aussi dans ComfyUI/input/
    
    Returns:
        Path du fichier généré
    """
    log = logger or logging.getLogger("region_mask_generator")

    if not PIL_OK:
        log.error("[MASK] PIL non installé : pip install Pillow")
        return None

    layout_fn = LAYOUTS.get(layout, _layout_character_center)
    regions   = layout_fn(width, height)

    img  = Image.new("RGB", (width, height), COLOR_GREEN)
    draw = ImageDraw.Draw(img)

    # Dessiner les régions du plus grand au plus petit (Z-order)
    for name, color, bbox in regions:
        draw.rectangle(bbox, fill=color)
        log.debug(f"[MASK] Zone '{name}' : {color} → {bbox}")

    # Chemin de sortie
    if output_path:
        out = Path(output_path)
    else:
        MASKS_DIR.mkdir(parents=True, exist_ok=True)
        ts  = datetime.now().strftime("%Y%m%d_%H%M%S")
        out = MASKS_DIR / f"regional_{layout}_{ts}.png"

    out.parent.mkdir(parents=True, exist_ok=True)
    img.save(str(out))
    log.info(f"[MASK] Masque régional généré : {out} ({width}×{height}, {len(regions)} zones)")

    # Copier vers ComfyUI/input/ avec le nom standard
    if output_comfyui and COMFYUI_INPUT.exists():
        dest = COMFYUI_INPUT / "redgreenregion.png"
        img.save(str(dest))
        log.info(f"[MASK] Copié → {dest}")

    # Générer aussi les versions mono-canal pour les LoadImage RED/GREEN/BLUE
    if output_comfyui and COMFYUI_INPUT.exists():
        for canal, color, suffix in [
            ("red",   COLOR_RED,   "load_image_red"),
            ("green", COLOR_GREEN, "load_image_green"),
            ("blue",  COLOR_BLUE,  "load_image_blue"),
        ]:
            mono = Image.new("RGB", (width, height), COLOR_BLACK)
            draw_mono = ImageDraw.Draw(mono)
            for name, c, bbox in regions:
                if c == color:
                    draw_mono.rectangle(bbox, fill=COLOR_WHITE)
            mono.save(str(COMFYUI_INPUT / f"{suffix}.png"))

    if BUS_OK:
        try:
            get_bus().write("mask.regional_layout", layout, agent_id="mask_gen")
            get_bus().write("mask.regional_path", str(out), agent_id="mask_gen")
        except Exception:
            pass

    return out


def generate_layer_mask(
    width: int = 1024,
    height: int = 1536,
    zone: str = "face",
    feather: int = 20,
    output_path: str = None,
    output_comfyui: bool = True,
    logger=None
) -> Path | None:
    """
    Génère un masque blanc/noir pour l'inpainting ciblé.
    Zone blanche = à régénérer, zone noire = à préserver.
    
    Args:
        zone : 'eyes', 'face', 'mouth', 'hands', 'body', 'hair', 'clothes', 'full'
        feather : pixels de fondu sur les bords (0 = bords nets)
    """
    log = logger or logging.getLogger("region_mask_generator")

    if not PIL_OK:
        log.error("[MASK] PIL non installé")
        return None

    ratios = FACE_ZONES.get(zone, FACE_ZONES["face"])
    x1 = max(0, int(ratios[0] * width)  - feather)
    y1 = max(0, int(ratios[1] * height) - feather)
    x2 = min(width,  int(ratios[2] * width)  + feather)
    y2 = min(height, int(ratios[3] * height) + feather)

    img  = Image.new("RGB", (width, height), COLOR_BLACK)
    draw = ImageDraw.Draw(img)
    draw.rectangle((x1, y1, x2, y2), fill=COLOR_WHITE)

    if output_path:
        out = Path(output_path)
    else:
        MASKS_DIR.mkdir(parents=True, exist_ok=True)
        ts  = datetime.now().strftime("%Y%m%d_%H%M%S")
        out = MASKS_DIR / f"mask_{zone}_{ts}.png"

    out.parent.mkdir(parents=True, exist_ok=True)
    img.save(str(out))
    log.info(f"[MASK] Masque inpaint '{zone}' : {out} ({x1},{y1})→({x2},{y2})")

    if output_comfyui and COMFYUI_INPUT.exists():
        dest = COMFYUI_INPUT / f"mask_{zone}.png"
        img.save(str(dest))
        log.info(f"[MASK] Copié → {dest}")

    if BUS_OK:
        try:
            get_bus().write(f"mask.{zone}_path", str(out), agent_id="mask_gen")
        except Exception:
            pass

    return out


def generate_character_body_masks(
    width: int = 1024,
    height: int = 1536,
    output_comfyui: bool = True,
    logger=None
) -> dict:
    """
    Génère tous les masques nécessaires pour la production par couche :
    - Corps nu (pass 2)
    - Yeux (pass 3)
    - Mains (pass 3)  
    - Vêtements (pass 3 — ajout vêtements sur corps nu)
    - Background region (pass 1)
    
    Retourne un dict zone → Path
    """
    log = logger or logging.getLogger("region_mask_generator")
    results = {}

    zones = ["face", "eyes", "mouth", "hands", "body",
             "upper_body", "hair", "clothes", "full"]
    for zone in zones:
        path = generate_layer_mask(
            width=width, height=height,
            zone=zone, feather=15,
            output_comfyui=output_comfyui,
            logger=log
        )
        if path:
            results[zone] = path

    log.info(f"[MASK] {len(results)} masques générés")
    return results


def generate_all_for_shot(
    width: int = 1024,
    height: int = 1536,
    layout: str = "character_center",
    shot_id: str = "shot_01",
    output_comfyui: bool = True,
    logger=None
) -> dict:
    """
    Génère tous les masques nécessaires pour un shot complet.
    Appelé par agent_supervisor avant chaque job ComfyUI.
    """
    log = logger or logging.getLogger("region_mask_generator")
    log.info(f"[MASK] Génération complète pour {shot_id} ({layout})")

    results = {
        "regional": generate_regional_mask(
            width=width, height=height,
            layout=layout,
            output_comfyui=output_comfyui,
            logger=log
        ),
        "layers": generate_character_body_masks(
            width=width, height=height,
            output_comfyui=output_comfyui,
            logger=log
        )
    }

    # Sauvegarder le manifest du shot
    MASKS_DIR.mkdir(parents=True, exist_ok=True)
    manifest = MASKS_DIR / f"{shot_id}_masks.json"
    manifest.write_text(
        json.dumps({
            "shot_id":  shot_id,
            "layout":   layout,
            "size":     (width, height),
            "regional": str(results["regional"]),
            "layers":   {k: str(v) for k, v in results["layers"].items()},
            "generated": datetime.now().isoformat(),
        }, indent=2, ensure_ascii=False),
        encoding='utf-8'
    )
    log.info(f"[MASK] Manifest → {manifest.name}")
    return results


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Ov3rLoRd Region Mask Generator")
    parser.add_argument("--layout",   type=str, default="character_center",
                        choices=list(LAYOUTS.keys()))
    parser.add_argument("--zone",     type=str, default=None,
                        help="Zone inpaint : eyes, face, hands, body...")
    parser.add_argument("--width",    type=int, default=1024)
    parser.add_argument("--height",   type=int, default=1536)
    parser.add_argument("--shot-id",  type=str, default="shot_01")
    parser.add_argument("--all",      action="store_true",
                        help="Générer tous les masques pour un shot")
    parser.add_argument("--list",     action="store_true",
                        help="Lister les layouts et zones disponibles")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO,
                        format="%(asctime)s [%(levelname)s] %(message)s")

    if args.list:
        print(f"\nLayouts disponibles ({len(LAYOUTS)}) :")
        for name in LAYOUTS:
            print(f"  {name}")
        print(f"\nZones inpaint disponibles ({len(FACE_ZONES)}) :")
        for name, ratios in FACE_ZONES.items():
            print(f"  {name:12s} → {ratios}")

    elif args.all:
        results = generate_all_for_shot(
            width=args.width, height=args.height,
            layout=args.layout, shot_id=args.shot_id
        )
        print(f"Masque régional : {results['regional']}")
        print(f"Masques couches : {len(results['layers'])} générés")

    elif args.zone:
        out = generate_layer_mask(width=args.width, height=args.height,
                                   zone=args.zone)
        print(f"Masque inpaint '{args.zone}' : {out}")

    else:
        out = generate_regional_mask(width=args.width, height=args.height,
                                      layout=args.layout)
        print(f"Masque régional '{args.layout}' : {out}")

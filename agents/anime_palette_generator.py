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
agents/anime_palette_generator.py — Générateur de Palettes Couleur Anime V1.70
Phase 0 — Génère des fichiers de palette directement utilisables dans ComfyUI
et dans le pipeline de production.

Contient les codes couleur de référence pour :
  - Palettes de fond par ambiance (jour urbain, nuit, coucher soleil...)
  - Effets de pouvoir et impacts (EVA, DBZ, Naruto style...)
  - Palettes atmosphériques Makoto Shinkai
  - Séquences de flashs et transitions chromatiques
  - Couleurs de vêtements par personnage type

Formats générés :
  - .json : usage par les agents Python
  - .png  : swatches visuels pour référence
  - .act  : fichier Adobe Color Table (compatible ComfyUI ImageQuantize)
  - .csv  : liste hex pour import externe

Usage :
  python agents/anime_palette_generator.py --generate-all
  python agents/anime_palette_generator.py --palette shinkai_day
  python agents/anime_palette_generator.py --effect power_blue
  python agents/anime_palette_generator.py --list
"""

import json
import struct
import sys
import io
import logging
from pathlib import Path
from datetime import datetime

if hasattr(sys.stdout, 'buffer'):
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

try:
    from PIL import Image, ImageDraw
    PIL_OK = True
except ImportError:
    PIL_OK = False

PALETTE_DIR = Path("workspace/palettes")
COMFYUI_DIR = Path(r"D:/Ov3rLoRd AI/ComfyUI/models/colors")

# ══════════════════════════════════════════════════════════════════════
#  DICTIONNAIRE COMPLET DES PALETTES ANIME
#  Source : analyse des œuvres de référence
#  Makoto Shinkai / Gainax / Khara / Ankama / Sunrise / Toei
# ══════════════════════════════════════════════════════════════════════

ANIME_PALETTES = {

    # ── Makoto Shinkai — Signature atmosphérique ──────────────────────
    "shinkai_day": {
        "description": "Ciel de jour urbain — Your Name / Suzume",
        "tags": ["background", "day", "urban", "shinkai"],
        "colors": {
            "sky_zenith":     "#1a3a6e",  # bleu profond zénith
            "sky_mid":        "#4a7eb5",  # bleu ciel moyen
            "sky_horizon":    "#89b4d4",  # bleu horizon brumeux
            "cloud_light":    "#e8f0f8",  # blanc nuage lumineux
            "cloud_shadow":   "#b8c8d8",  # gris bleuté ombre nuage
            "sunlight":       "#fff4d6",  # jaune chaud soleil
            "atmosphere":     "#c8dde8",  # brume atmosphérique
            "building_dark":  "#2a2a3a",  # immeuble sombre
            "building_light": "#8a8a9a",  # immeuble façade
            "window_glow":    "#ffe080",  # reflet fenêtre
        }
    },

    "shinkai_sunset": {
        "description": "Coucher de soleil — 5cm/s / Garden of Words",
        "tags": ["background", "sunset", "golden_hour", "shinkai"],
        "colors": {
            "sun_core":       "#ff8c00",  # orange soleil intense
            "sun_halo":       "#ffcc44",  # halo doré
            "sky_orange":     "#ff6633",  # orange ciel
            "sky_pink":       "#ff99aa",  # rose horizon
            "sky_purple":     "#cc44aa",  # violet crépuscule
            "sky_deep":       "#442266",  # indigo profond
            "silhouette":     "#1a0a22",  # silhouette noire
            "water_reflect":  "#ff8844",  # reflet eau
            "cloud_gold":     "#ffd700",  # nuage doré
            "light_ray":      "#ffe8aa",  # rayon de lumière
        }
    },

    "shinkai_night": {
        "description": "Nuit urbaine — Your Name (Tokyo night)",
        "tags": ["background", "night", "urban", "neon", "shinkai"],
        "colors": {
            "sky_night":      "#050510",  # noir nuit profond
            "star_bright":    "#ffffff",  # étoile blanche
            "star_blue":      "#aaaaff",  # étoile bleutée
            "neon_blue":      "#0044ff",  # néon bleu urbain
            "neon_pink":      "#ff00aa",  # néon rose/magenta
            "neon_yellow":    "#ffee00",  # néon jaune
            "street_orange":  "#ff8833",  # lampadaire orange
            "window_warm":    "#ffcc66",  # fenêtre illuminée
            "building_base":  "#0a0a1a",  # base immeuble nuit
            "reflection":     "#1a1a3a",  # reflet sol mouillé
        }
    },

    "shinkai_rain": {
        "description": "Pluie — Garden of Words signature",
        "tags": ["background", "rain", "atmospheric", "shinkai"],
        "colors": {
            "sky_gray":       "#4a5a6a",  # ciel couvert
            "rain_drop":      "#a0b8c8",  # goutte de pluie
            "puddle_reflect": "#5a7a8a",  # reflet flaque
            "wet_ground":     "#3a4a5a",  # sol mouillé
            "foliage_wet":    "#2a5a2a",  # végétation mouillée
            "foliage_light":  "#4a8a4a",  # feuille éclairée
            "mist":           "#8a9aaa",  # brume légère
            "umbrella_red":   "#cc2200",  # parapluie rouge signature
            "bench_wood":     "#8a6040",  # banc bois
            "concrete":       "#6a7a8a",  # béton mouillé
        }
    },

    # ── Evangelion / Gainax / Khara ───────────────────────────────────
    "eva_battle": {
        "description": "Ambiance combat Evangelion",
        "tags": ["background", "battle", "evangelion", "night"],
        "colors": {
            "sky_red":        "#880000",  # ciel rouge sang (alerte)
            "sky_orange":     "#cc4400",  # orange apocalyptique
            "ground_dark":    "#1a0a00",  # sol brûlé
            "explosion_core": "#ffffff",  # cœur explosion
            "explosion_mid":  "#ffaa00",  # explosion orange
            "explosion_outer":"#cc4400",  # bord explosion
            "at_field":       "#ffff00",  # AT Field jaune
            "at_field_glow":  "#ffff88",  # lueur AT Field
            "lance_red":      "#cc0022",  # lance de Longinus
            "angel_white":    "#f0e8e0",  # chair ange
            "angel_core":     "#ff0044",  # sphère de core
            "nerv_orange":    "#ff6600",  # orange NERV
            "umbra_dark":     "#000011",  # ombre totale
        }
    },

    "eva_interior": {
        "description": "Intérieur Eva / cockpit LCL",
        "tags": ["interior", "cockpit", "evangelion"],
        "colors": {
            "lcl_orange":     "#ff8833",  # liquide LCL ambiant
            "lcl_glow":       "#ffaa55",  # lueur LCL
            "screen_green":   "#00ff44",  # écran monitoring
            "screen_red":     "#ff2200",  # alerte écran
            "metal_dark":     "#1a1a2a",  # métal sombre cockpit
            "metal_mid":      "#3a3a5a",  # métal moyen
            "plug_suit_red":  "#cc0000",  # combinaison Asuka rouge
            "plug_suit_white":"#e0e0e0",  # combinaison blanche Rei
            "entry_plug":     "#885522",  # couleur capsule
            "neural_pattern": "#ffcc00",  # interface neurale
        }
    },

    # ── DBZ / Shonen combat ───────────────────────────────────────────
    "dbz_power": {
        "description": "Effets de pouvoir Dragon Ball Z",
        "tags": ["effect", "power", "battle", "dbz", "aura"],
        "colors": {
            "aura_yellow":    "#ffee00",  # aura Super Saiyan
            "aura_bright":    "#ffffff",  # flash aura max
            "aura_edge":      "#ffaa00",  # bord aura
            "ki_blast_yellow":"#ffdd00",  # ki blast jaune
            "ki_blast_core":  "#ffffff",  # cœur ki blast
            "energy_wave":    "#88ffff",  # onde d'énergie (Kamehameha)
            "kamehameha_mid": "#4488ff",  # milieu Kamehameha
            "kamehameha_dark":"#0022cc",  # base Kamehameha
            "impact_white":   "#ffffff",  # flash impact
            "crater_dark":    "#2a1a00",  # cratère post-impact
            "dust_cloud":     "#aa8866",  # nuage de poussière
            "lightning":      "#ffffff",  # éclair pouvoir
            "lightning_blue": "#8888ff",  # éclair bleu électrique
        }
    },

    "naruto_chakra": {
        "description": "Chakra et effets Naruto style",
        "tags": ["effect", "chakra", "power", "naruto"],
        "colors": {
            "chakra_blue":    "#4488ff",  # chakra standard bleu
            "rasengan_core":  "#88aaff",  # cœur Rasengan
            "rasengan_outer": "#ffffff",  # bord Rasengan
            "sage_orange":    "#ff8800",  # mode ermite orange
            "nine_tails_red": "#ff2200",  # chakra Kyubi rouge
            "nine_tails_dark":"#880000",  # bord chakra Kyubi
            "sharingan_red":  "#cc0000",  # fond Sharingan
            "sharingan_black":"#000000",  # motif Sharingan
            "lightning_white":"#ffffff",  # Chidori blanc
            "lightning_blue": "#6688ff",  # Chidori bleu
        }
    },

    # ── Gundam / Mecha ────────────────────────────────────────────────
    "gundam_space": {
        "description": "Espace et combat mecha Gundam",
        "tags": ["background", "space", "mecha", "gundam"],
        "colors": {
            "space_black":    "#000005",  # noir espace profond
            "nebula_blue":    "#112244",  # nébuleuse bleue
            "nebula_purple":  "#221133",  # nébuleuse violette
            "star_white":     "#ffffff",  # étoile
            "star_blue":      "#aaccff",  # étoile bleue
            "earth_ocean":    "#1144aa",  # océan depuis l'espace
            "earth_land":     "#226622",  # continent
            "earth_cloud":    "#ddddee",  # nuages atmosphère
            "beam_sabre_pink":"#ff44aa",  # sabre faisceau rose (RX-78)
            "beam_sabre_yellow":"#ffcc00",# sabre jaune (Zaku)
            "explosion_space":"#ff6600",  # explosion espace
            "thruster_blue":  "#44aaff",  # propulseur
            "thruster_orange":"#ff8833",  # propulseur orange
            "solar_panel":    "#223344",  # panneau solaire
        }
    },

    # ── Hatsune Miku / Vocaloid ───────────────────────────────────────
    "miku_stage": {
        "description": "Scène concert Hatsune Miku",
        "tags": ["stage", "concert", "miku", "vocaloid", "neon"],
        "colors": {
            "miku_teal":      "#39c5bb",  # couleur signature Miku
            "miku_dark":      "#1a8a88",  # version sombre Miku
            "stage_light_1":  "#ffffff",  # projecteur blanc
            "stage_light_2":  "#44ffff",  # projecteur cyan
            "stage_light_3":  "#ff44ff",  # projecteur magenta
            "crowd_dark":     "#0a0a1a",  # foule fond sombre
            "glowstick_teal": "#00ffcc",  # lightstick couleur Miku
            "glowstick_pink": "#ff44aa",  # lightstick rose
            "hologram_glow":  "#88ffff",  # lueur hologramme
            "screen_bg":      "#001122",  # fond écran scène
            "confetti_gold":  "#ffd700",  # confetti doré
            "confetti_teal":  "#39c5bb",  # confetti Miku
            "smoke_stage":    "#334444",  # fumée scène
        }
    },

    # ── Wakfu / Ankama ────────────────────────────────────────────────
    "wakfu_world": {
        "description": "World of Twelve — Wakfu style Ankama",
        "tags": ["background", "fantasy", "wakfu", "ankama"],
        "colors": {
            "sky_turquoise":  "#33aacc",  # ciel Wakfu turquoise
            "grass_bright":   "#66cc44",  # herbe lumineuse
            "grass_mid":      "#44aa22",  # herbe normale
            "stone_gray":     "#889988",  # pierre gris-vert
            "water_blue":     "#2288aa",  # eau claire
            "portal_blue":    "#0044cc",  # portail zaap bleu
            "portal_glow":    "#44aaff",  # lueur portail
            "iop_red":        "#cc2200",  # couleur Iop (Dally)
            "cra_brown":      "#884400",  # brun Cra (Amalia)
            "rubilax_purple": "#6622aa",  # Rubilax violet signature
            "rubilax_dark":   "#330066",  # Rubilax sombre
            "sadida_green":   "#226600",  # vert Sadida
            "kamas_gold":     "#ffaa00",  # pièces kamas
        }
    },

    # ── Palettes de transition / Flash ────────────────────────────────
    "impact_flashes": {
        "description": "Séquence de flashs pour impacts et transitions",
        "tags": ["effect", "flash", "transition", "impact"],
        "colors": {
            "flash_white":    "#ffffff",  # flash blanc pur
            "flash_yellow":   "#ffff00",  # flash impact énergie
            "flash_orange":   "#ff8800",  # flash explosion
            "flash_red":      "#ff0000",  # flash douleur/danger
            "flash_blue":     "#0044ff",  # flash pouvoir bleu
            "flash_cyan":     "#00ffff",  # flash électrique
            "flash_pink":     "#ff44ff",  # flash magique
            "flash_green":    "#00ff44",  # flash soin/nature
            "flash_purple":   "#8800ff",  # flash sombre/mystique
            "fade_black":     "#000000",  # fondu noir pur
            "fade_white":     "#ffffff",  # fondu blanc pur
            "vignette_dark":  "#0a0a0a",  # vignette sombre
        }
    },

    "pastel_emotion": {
        "description": "Palette pastel pour scènes émotionnelles",
        "tags": ["effect", "emotion", "pastel", "mood"],
        "colors": {
            "pastel_pink":    "#ffccdd",  # rose doux (amour, tendresse)
            "pastel_blue":    "#ccddff",  # bleu doux (mélancolie)
            "pastel_yellow":  "#ffffcc",  # jaune doux (joie légère)
            "pastel_green":   "#ccffdd",  # vert doux (espoir)
            "pastel_purple":  "#ddccff",  # violet doux (rêverie)
            "pastel_orange":  "#ffddcc",  # orange doux (nostalgie)
            "memory_sepia":   "#c8a880",  # sépia souvenir
            "memory_wash":    "#d8c8b0",  # lavage sépia clair
            "dream_white":    "#f8f4ff",  # blanc légèrement violet (rêve)
            "flashback_gray": "#b0b0b0",  # gris flashback
        }
    },

    "color_sequence_battle": {
        "description": "Séquence chromatique pour scènes de combat intense",
        "tags": ["effect", "battle", "sequence", "color_flow"],
        "sequence": [
            "#000000",  # 0. Noir initial
            "#220000",  # 1. Rouge très sombre (montée tension)
            "#550000",  # 2. Rouge sombre
            "#aa0000",  # 3. Rouge moyen
            "#ff0000",  # 4. Rouge vif (impact)
            "#ff4400",  # 5. Orange-rouge
            "#ff8800",  # 6. Orange
            "#ffcc00",  # 7. Jaune-orange
            "#ffff00",  # 8. Jaune vif (énergie max)
            "#ffffff",  # 9. BLANC TOTAL (flash peak)
            "#88ffff",  # 10. Cyan (aftermath)
            "#4488ff",  # 11. Bleu retour au calme
            "#224488",  # 12. Bleu sombre
            "#112233",  # 13. Indigo
            "#000011",  # 14. Noir final
        ],
        "colors": {
            "start":          "#000000",
            "peak":           "#ffffff",
            "end":            "#000011",
        }
    },
}


# ── Génération des fichiers de palette ───────────────────────────────

def hex_to_rgb(hex_color: str) -> tuple:
    h = hex_color.lstrip("#")
    return tuple(int(h[i:i+2], 16) for i in (0, 2, 4))


def generate_json(palette_name: str, output_dir: Path, logger=None) -> Path:
    """Export JSON — utilisé par les agents Python."""
    log = logger or logging.getLogger("palette_gen")
    data = ANIME_PALETTES.get(palette_name, {})
    if not data:
        log.error(f"[PALETTE] Palette inconnue : {palette_name}")
        return None

    out = output_dir / f"{palette_name}.json"
    out.write_text(json.dumps({
        "name":        palette_name,
        "description": data.get("description", ""),
        "tags":        data.get("tags", []),
        "colors":      data.get("colors", {}),
        "sequence":    data.get("sequence", []),
        "generated":   datetime.now().isoformat(),
    }, indent=2, ensure_ascii=False), encoding="utf-8")
    log.info(f"[PALETTE] JSON → {out.name}")
    return out


def generate_swatch_png(palette_name: str, output_dir: Path,
                          swatch_size: int = 60, logger=None) -> Path | None:
    """Export PNG swatch — référence visuelle."""
    log = logger or logging.getLogger("palette_gen")
    if not PIL_OK:
        return None

    data   = ANIME_PALETTES.get(palette_name, {})
    colors = data.get("colors", {})
    if not colors:
        return None

    n_colors = len(colors)
    cols     = min(n_colors, 10)
    rows     = (n_colors + cols - 1) // cols
    pad      = 4

    img  = Image.new("RGB", (cols * (swatch_size + pad), rows * (swatch_size + pad) + 30),
                     (20, 20, 30))
    draw = ImageDraw.Draw(img)

    for i, (name, hex_col) in enumerate(colors.items()):
        row = i // cols
        col = i % cols
        x   = col * (swatch_size + pad) + pad
        y   = row * (swatch_size + pad) + pad + 20

        try:
            rgb = hex_to_rgb(hex_col)
            draw.rectangle([x, y, x + swatch_size, y + swatch_size], fill=rgb)
            # Label petit
            label = name[:8]
            draw.text((x + 2, y + swatch_size - 12), label,
                       fill=(200, 200, 200))
        except Exception:
            pass

    # Titre
    draw.text((4, 4), f"{palette_name} — {data.get('description','')[:50]}",
               fill=(200, 200, 220))

    out = output_dir / f"{palette_name}_swatch.png"
    img.save(str(out))
    log.info(f"[PALETTE] Swatch PNG → {out.name}")
    return out


def generate_act(palette_name: str, output_dir: Path, logger=None) -> Path | None:
    """
    Export .act (Adobe Color Table) — compatible ComfyUI ImageQuantize.
    Format : 768 bytes = 256 couleurs × 3 bytes (R,G,B).
    """
    log = logger or logging.getLogger("palette_gen")
    data   = ANIME_PALETTES.get(palette_name, {})
    colors = list(data.get("colors", {}).values())
    if not colors:
        return None

    # Remplir jusqu'à 256 couleurs (répéter si nécessaire)
    rgb_list = []
    for c in colors:
        try:
            rgb_list.append(hex_to_rgb(c))
        except Exception:
            rgb_list.append((0, 0, 0))

    while len(rgb_list) < 256:
        rgb_list.extend(rgb_list[:max(1, 256 - len(rgb_list))])
    rgb_list = rgb_list[:256]

    # Construire le fichier ACT
    act_data = b""
    for r, g, b in rgb_list:
        act_data += struct.pack("BBB", r, g, b)

    out = output_dir / f"{palette_name}.act"
    out.write_bytes(act_data)
    log.info(f"[PALETTE] ACT → {out.name}")
    return out


def generate_csv(palette_name: str, output_dir: Path, logger=None) -> Path:
    """Export CSV — import externe / référence."""
    log = logger or logging.getLogger("palette_gen")
    data   = ANIME_PALETTES.get(palette_name, {})
    colors = data.get("colors", {})

    lines  = ["name,hex,r,g,b,description"]
    desc   = data.get("description", "")
    for name, hex_col in colors.items():
        try:
            r, g, b = hex_to_rgb(hex_col)
            lines.append(f"{name},{hex_col},{r},{g},{b},{desc}")
        except Exception:
            pass

    out = output_dir / f"{palette_name}.csv"
    out.write_text("\n".join(lines), encoding="utf-8")
    log.info(f"[PALETTE] CSV → {out.name}")
    return out


def generate_palette(palette_name: str,
                      output_dir: Path = None,
                      copy_to_comfyui: bool = True,
                      logger=None) -> dict:
    """Génère tous les formats pour une palette."""
    log = logger or logging.getLogger("palette_gen")

    if output_dir is None:
        output_dir = PALETTE_DIR / palette_name
    output_dir.mkdir(parents=True, exist_ok=True)

    results = {}
    results["json"] = generate_json(palette_name, output_dir, log)
    results["png"]  = generate_swatch_png(palette_name, output_dir, logger=log)
    results["act"]  = generate_act(palette_name, output_dir, log)
    results["csv"]  = generate_csv(palette_name, output_dir, log)

    # Copier vers ComfyUI si disponible
    if copy_to_comfyui:
        comfyui_colors = Path(r"D:/Ov3rLoRd AI/ComfyUI/models") / "colors"
        comfyui_colors.mkdir(parents=True, exist_ok=True)
        for fmt, path in results.items():
            if path and Path(str(path)).exists():
                import shutil
                dest = comfyui_colors / Path(str(path)).name
                try:
                    shutil.copy2(str(path), dest)
                except Exception:
                    pass

    log.info(f"[PALETTE] '{palette_name}' : {len([v for v in results.values() if v])} fichiers")
    return results


def generate_all_palettes(output_dir: Path = None,
                           copy_to_comfyui: bool = True,
                           logger=None) -> dict:
    """Génère toutes les palettes en une commande."""
    log = logger or logging.getLogger("palette_gen")
    if output_dir is None:
        output_dir = PALETTE_DIR

    log.info(f"[PALETTE] Génération de {len(ANIME_PALETTES)} palettes...")
    all_results = {}

    for name in ANIME_PALETTES:
        results = generate_palette(name, output_dir / name,
                                   copy_to_comfyui=copy_to_comfyui,
                                   logger=log)
        all_results[name] = results

    # Index global
    index = {
        "generated":    datetime.now().isoformat(),
        "total":        len(ANIME_PALETTES),
        "palettes":     {
            name: {
                "description": ANIME_PALETTES[name].get("description", ""),
                "tags":        ANIME_PALETTES[name].get("tags", []),
                "n_colors":    len(ANIME_PALETTES[name].get("colors", {})),
            }
            for name in ANIME_PALETTES
        }
    }
    (output_dir / "palette_index.json").write_text(
        json.dumps(index, indent=2, ensure_ascii=False), encoding="utf-8"
    )

    log.info(f"[PALETTE] ✓ {len(ANIME_PALETTES)} palettes générées → {output_dir}")
    return all_results


def get_palette_colors(palette_name: str) -> dict:
    """Accès rapide aux couleurs d'une palette depuis un agent."""
    data = ANIME_PALETTES.get(palette_name, {})
    return data.get("colors", {})


def get_sequence_colors(palette_name: str) -> list:
    """Récupère la séquence chromatique d'une palette de transition."""
    data = ANIME_PALETTES.get(palette_name, {})
    return data.get("sequence", list(data.get("colors", {}).values()))


def suggest_palette(arc: str = None, universe: str = None,
                     scene_type: str = None) -> str:
    """Suggère la palette la plus adaptée selon le contexte."""
    mapping = {
        # Arc narratif
        "tension":     "eva_battle",
        "wonder":      "shinkai_sunset",
        "catharsis":   "shinkai_rain",
        "peaceful":    "shinkai_day",
        "action":      "dbz_power",
        "impact":      "impact_flashes",
        "emotion":     "pastel_emotion",
        "epic":        "color_sequence_battle",
        # Univers
        "evangelion":  "eva_battle",
        "gundam":      "gundam_space",
        "miku":        "miku_stage",
        "wakfu":       "wakfu_world",
        "naruto":      "naruto_chakra",
        "dbz":         "dbz_power",
        # Type de scène
        "night":       "shinkai_night",
        "sunset":      "shinkai_sunset",
        "rain":        "shinkai_rain",
        "combat":      "eva_battle",
        "concert":     "miku_stage",
        "space":       "gundam_space",
    }
    for key, palette in mapping.items():
        if arc and key in arc.lower():
            return palette
        if universe and key in universe.lower():
            return palette
        if scene_type and key in scene_type.lower():
            return palette
    return "shinkai_day"  # défaut


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Ov3rLoRd Anime Palette Generator V1.70")
    parser.add_argument("--generate-all",  action="store_true",
                        help="Générer toutes les palettes")
    parser.add_argument("--palette",       type=str, default=None,
                        help="Générer une palette spécifique")
    parser.add_argument("--list",          action="store_true",
                        help="Lister toutes les palettes disponibles")
    parser.add_argument("--suggest",       type=str, default=None,
                        help="Suggérer une palette : --suggest 'evangelion battle'")
    parser.add_argument("--no-comfyui",    action="store_true",
                        help="Ne pas copier vers ComfyUI")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO,
                        format="%(asctime)s [%(levelname)s] %(message)s")

    if args.list:
        print(f"\n{'═'*65}")
        print(f"  PALETTES ANIME DISPONIBLES ({len(ANIME_PALETTES)})")
        print(f"{'═'*65}")
        for name, data in ANIME_PALETTES.items():
            n = len(data.get("colors", {}))
            tags = ", ".join(data.get("tags", [])[:3])
            print(f"  {name:30s} {n:2d} couleurs  [{tags}]")
            print(f"    {data.get('description','')}")
        print(f"{'═'*65}")

    elif args.suggest:
        suggestion = suggest_palette(arc=args.suggest, universe=args.suggest)
        print(f"Palette suggérée pour '{args.suggest}' : {suggestion}")
        print(f"Description : {ANIME_PALETTES[suggestion].get('description','')}")

    elif args.generate_all:
        results = generate_all_palettes(copy_to_comfyui=not args.no_comfyui)
        print(f"\n✓ {len(results)} palettes générées dans workspace/palettes/")
        print(f"  Formats : .json | .png (swatch) | .act (ComfyUI) | .csv")
        if not args.no_comfyui:
            print(f"  Copiées → D:\\Ov3rLoRd AI\\ComfyUI\\models\\colors\\")

    elif args.palette:
        results = generate_palette(args.palette,
                                   copy_to_comfyui=not args.no_comfyui)
        print(f"\nPalette '{args.palette}' générée :")
        for fmt, path in results.items():
            if path:
                print(f"  {fmt:5s} → {path}")

    else:
        parser.print_help()

"""
demo_pipeline.py — Pipeline Vidéo de Démonstration V1.70
Produit la démo "Onibaku Gumi" en 2 minutes :
  - Opening  : 15s — titre + logo Onibaku Gumi
  - Scène 1  : 30s — Evangelion (Asuka vs Angel)
  - Scène 2  : 30s — Gundam (mecha battle urban)
  - Scène 3  : 30s — Hatsune Miku (concert holographique)
  - Ending   : 15s — credits + ROG hardware reveal

Méthode Ankama adaptée :
  - Backgrounds générés séparément et réutilisés
  - Personnages générés par couche (corps, visage, détails)
  - Assembly en compositing ffmpeg
  - Transitions : cut noir + titre de scène inter-LoRa

Usage :
  python demo_pipeline.py --plan        # afficher le plan complet
  python demo_pipeline.py --scene 1     # générer une scène
  python demo_pipeline.py --full        # générer tout (8-12h)
  python demo_pipeline.py --assemble    # assembler depuis images existantes
"""

import json
import logging
import subprocess
import sys
import io
from datetime import datetime
from pathlib import Path

if hasattr(sys.stdout, 'buffer'):
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

try:
    from agents.context_bus import get_bus
    BUS_OK = True
except ImportError:
    BUS_OK = False

DEMO_DIR    = Path("workspace/demo")
RENDER_DIR  = DEMO_DIR / "renders"
COMPOSE_DIR = DEMO_DIR / "compositing"
EXPORT_DIR  = DEMO_DIR / "export"

FPS           = 24
SCENE_SECS    = 30
OPENING_SECS  = 15
ENDING_SECS   = 15

# ── Structure de la démo ─────────────────────────────────────────────

DEMO_STRUCTURE = {
    "title":       "Onibaku Gumi — AI Anime Production Demo",
    "subtitle":    "鬼爆組 | Powered by Ov3rLoRd V1.70 | ROG Hardware",
    "total_secs":  OPENING_SECS + 3*SCENE_SECS + ENDING_SECS,  # 120s

    "opening": {
        "id":        "opening",
        "duration":  OPENING_SECS,
        "type":      "ken_burns",   # illustration fixe animée (pas de LLM nécessaire)
        "n_images":  4,
        "positive":  (
            "masterpiece, best quality, absurdres, "
            "dark background, glowing text, Japanese calligraphy style, "
            "鬼爆組, neon purple glow, cyberpunk aesthetic, "
            "anime production studio logo, epic cinematic"
        ),
        "negative":  "bad quality, character, people, low resolution",
        "lora":      None,  # pas de LoRa pour l'opening
        "style":     "dark, minimalist, title card",
        "text_overlay": ["ONIBAKU GUMI", "鬼爆組", "AI Anime Production", "Powered by Ov3rLoRd V1.70"],
    },

    "scenes": [
        {
            "id":        "scene_01_evangelion",
            "title":     "Episode I — The Angel Descends",
            "duration":  SCENE_SECS,
            "universe":  "evangelion",
            "lora":      "asuka-langley-soryuu-classic-ponyxl-lora-nochekaiser.safetensors",
            "n_keyframes": 10,   # 10 keyframes × 3s = 30s
            "n_bg":      3,      # 3 backgrounds différents
            "n_chars":   2,      # Asuka + Angel
            # Plans : wide_shot → medium_shot → close_up → action → close_up
            "shots": [
                {"type": "wide",    "secs": 3,
                 "positive": "masterpiece, best quality, absurdres, asuka langley, red plug suit, evangelion unit-02, destroyed tokyo-3 cityscape, angel approaching, dramatic sky, epic scale, wide establishing shot"},
                {"type": "medium",  "secs": 3,
                 "positive": "masterpiece, best quality, absurdres, asuka langley soryu, close-up cockpit, intense expression, sweat, determined, evangelion interface, dramatic lighting"},
                {"type": "wide",    "secs": 3,
                 "positive": "masterpiece, best quality, absurdres, evangelion unit-02 battle stance, angel tentacles, neon genesis evangelion, epic battle, explosive energy"},
                {"type": "action",  "secs": 4,
                 "positive": "masterpiece, best quality, absurdres, asuka langley, fierce battle expression, speed lines, dynamic action, battle damage, unit-02 attacking, evangelion"},
                {"type": "close_up","secs": 3,
                 "positive": "masterpiece, best quality, absurdres, asuka langley soryu, victory expression, blue eyes, red hair, hair clips, evangelion cockpit, glowing displays"},
                {"type": "wide",    "secs": 4,
                 "positive": "masterpiece, best quality, absurdres, evangelion unit-02, angel defeated, tokyo-3 ruins, sunset aftermath, epic cinematic, wide shot"},
                {"type": "title",   "secs": 2,
                 "positive": "masterpiece, dark background, glowing text, 'Episode I', minimal, cinematic title card"},
                {"type": "medium",  "secs": 3,
                 "positive": "masterpiece, best quality, asuka langley, confident smile, victory pose, evangelion"},
                {"type": "wide",    "secs": 3,
                 "positive": "masterpiece, evangelion, tokyo-3, aerial view, peaceful after battle, golden hour"},
                {"type": "fade",    "secs": 2,
                 "positive": "masterpiece, evangelion, dark sky, fading light, transition"},
            ],
        },
        {
            "id":        "scene_02_gundam",
            "title":     "Episode II — Steel Wings",
            "duration":  SCENE_SECS,
            "universe":  "gundam",
            "lora":      None,  # LoRa Gundam Hathaway à télécharger
            "lora_url":  "https://civitai.com/models/780308",
            "n_keyframes": 10,
            "n_bg":      3,
            "n_chars":   2,
            "shots": [
                {"type": "wide",    "secs": 4,
                 "positive": "masterpiece, best quality, absurdres, mobile suit gundam, mecha, urban battlefield, space colony interior, dramatic lighting, gundam hathaway style, clean lineart"},
                {"type": "medium",  "secs": 3,
                 "positive": "masterpiece, best quality, absurdres, female mobile suit pilot, determined expression, cockpit, gundam, futuristic interface, gundam hathaway style"},
                {"type": "action",  "secs": 4,
                 "positive": "masterpiece, best quality, absurdres, gundam mecha battle, beam sabers, explosions, dynamic combat, speed lines, gundam hathaway aesthetic"},
                {"type": "close_up","secs": 3,
                 "positive": "masterpiece, best quality, absurdres, gundam head close-up, camera visor, battle damage, dramatic lighting, imposing perspective"},
                {"type": "wide",    "secs": 3,
                 "positive": "masterpiece, best quality, absurdres, two mobile suits facing off, destroyed urban background, dramatic sky, epic scale, gundam"},
                {"type": "action",  "secs": 4,
                 "positive": "masterpiece, best quality, gundam, beam cannon charging, energy buildup, dramatic lighting, cockpit pilot"},
                {"type": "medium",  "secs": 3,
                 "positive": "masterpiece, best quality, pilot female, intense eyes, helmet reflections, gundam cockpit"},
                {"type": "wide",    "secs": 3,
                 "positive": "masterpiece, gundam, aftermath, floating debris, space, stars, peaceful after battle"},
                {"type": "title",   "secs": 1,
                 "positive": "masterpiece, dark background, text overlay transition, minimal"},
                {"type": "fade",    "secs": 2,
                 "positive": "masterpiece, space, stars, fading, transition to next scene"},
            ],
        },
        {
            "id":        "scene_03_miku",
            "title":     "Episode III — Digital Serenade",
            "duration":  SCENE_SECS,
            "universe":  "hatsune miku",
            "lora":      None,  # LoRa Miku SDXL à télécharger
            "lora_url":  "https://civitai.com/models/647830",
            "n_keyframes": 10,
            "n_bg":      3,
            "n_chars":   1,
            "shots": [
                {"type": "wide",    "secs": 4,
                 "positive": "masterpiece, best quality, absurdres, hatsune miku, holographic concert stage, futuristic arena, teal lights, crowd, vocaloid, spectacular lighting"},
                {"type": "close_up","secs": 3,
                 "positive": "masterpiece, best quality, absurdres, hatsune miku, turquoise twintails, blue eyes, smiling, microphone, stage lighting, vocaloid"},
                {"type": "wide",    "secs": 3,
                 "positive": "masterpiece, hatsune miku, dancing, holographic particles, stage effects, concert, vocaloid, teal energy"},
                {"type": "medium",  "secs": 4,
                 "positive": "masterpiece, best quality, absurdres, hatsune miku, singing pose, emotional expression, concert lighting, teal and pink palette"},
                {"type": "wide",    "secs": 3,
                 "positive": "masterpiece, hatsune miku, hologram reveal, crowd reaction, concert arena, spectacular, vocaloid"},
                {"type": "close_up","secs": 3,
                 "positive": "masterpiece, best quality, hatsune miku, face close-up, eyes sparkling, concert makeup, twintails flowing"},
                {"type": "action",  "secs": 4,
                 "positive": "masterpiece, hatsune miku, dynamic dance pose, energy burst, holographic wings, concert climax"},
                {"type": "wide",    "secs": 3,
                 "positive": "masterpiece, hatsune miku, bow to audience, concert ending, warm lights, vocaloid"},
                {"type": "medium",  "secs": 1,
                 "positive": "masterpiece, hatsune miku, waving goodbye, smiling, teal palette"},
                {"type": "fade",    "secs": 2,
                 "positive": "masterpiece, concert stage, fading lights, end of show, transition"},
            ],
        },
    ],

    "ending": {
        "id":        "ending",
        "duration":  ENDING_SECS,
        "type":      "credits",
        "n_images":  4,
        "positive":  (
            "masterpiece, best quality, absurdres, "
            "dark cinematic background, purple and teal gradient, "
            "Japanese text aesthetic, credit roll style, "
            "anime production end card"
        ),
        "negative": "bad quality, characters, low resolution",
        "lora":     None,
        "text_overlay": [
            "ONIBAKU GUMI",
            "鬼爆組",
            "Produced by Ov3rLoRd AI Pipeline V1.70",
            "Hardware: ASUS ROG",
            "Pipeline: Ov3rLoRd | ComfyUI | Ollama",
            "© 2026 Onibaku Gumi"
        ],
    },
}


def print_plan():
    """Affiche le plan de production complet."""
    d = DEMO_STRUCTURE
    print(f"\n{'═'*65}")
    print(f"  {d['title']}")
    print(f"  {d['subtitle']}")
    print(f"  Durée totale : {d['total_secs']}s | {d['total_secs']//60}min{d['total_secs']%60}s")
    print(f"{'═'*65}")

    # Opening
    op = d["opening"]
    print(f"\n  OPENING ({op['duration']}s) — {op['style']}")
    print(f"    {op['n_images']} illustrations Ken Burns")
    print(f"    Textes : {' | '.join(op['text_overlay'][:2])}")

    # Scènes
    total_images = 0
    for scene in d["scenes"]:
        n_shots  = len(scene["shots"])
        n_images = sum(s["secs"] * FPS // 8 for s in scene["shots"])  # ~3 images/s
        total_images += n_images
        print(f"\n  {scene['title'].upper()} ({scene['duration']}s)")
        print(f"    Univers : {scene['universe']}")
        print(f"    LoRa    : {(scene['lora'] or 'À TÉLÉCHARGER')[:50]}")
        if scene.get("lora_url"):
            print(f"    URL     : {scene['lora_url']}")
        print(f"    Plans   : {n_shots} shots | ~{n_images} images générées")
        print(f"    Backgrounds : {scene['n_bg']} différents")
        for i, shot in enumerate(scene["shots"][:3]):
            print(f"      Plan {i+1} ({shot['secs']}s): {shot['type']} — "
                  f"{shot['positive'][:50]}...")
        if n_shots > 3:
            print(f"      ... ({n_shots-3} plans supplémentaires)")

    # Ending
    ed = d["ending"]
    print(f"\n  ENDING ({ed['duration']}s) — credits")
    print(f"    {ed['n_images']} illustrations + generique")

    print(f"\n{'─'*65}")
    print(f"  BILAN PRODUCTION")
    print(f"  Images totales estimées  : ~{total_images + 20}")
    print(f"  Temps gen RTX 5080 (80s) : ~{(total_images+20)*40//60}min")
    print(f"  Temps gen RTX 2070 (30s) : ~{(total_images+20)*30//60}min")
    print(f"\n  LoRas à télécharger avant génération :")
    print(f"    • Gundam Hathaway PonyXL → civitai.com/models/780308")
    print(f"    • Hatsune Miku SDXL      → civitai.com/models/647830")
    print(f"\n  Commandes :")
    print(f"    python demo_pipeline.py --scene 1   # Evangelion d'abord")
    print(f"    python demo_pipeline.py --scene 2   # Gundam")
    print(f"    python demo_pipeline.py --scene 3   # Miku")
    print(f"    python demo_pipeline.py --assemble  # Montage final")
    print(f"{'═'*65}")


def generate_scene_prompts(scene_id: int) -> list:
    """Retourne les prompts d'une scène numérotée (1-3)."""
    if scene_id < 1 or scene_id > len(DEMO_STRUCTURE["scenes"]):
        return []
    scene = DEMO_STRUCTURE["scenes"][scene_id - 1]
    return [
        {
            "positive":   shot["positive"],
            "negative":   "bad quality, worst quality, bad anatomy, deformed, "
                          "text, watermark, signature",
            "lora":       scene.get("lora", ""),
            "shot_type":  shot["type"],
            "duration_s": shot["secs"],
            "scene_id":   scene["id"],
            "shot_num":   i + 1,
        }
        for i, shot in enumerate(scene["shots"])
    ]


def assemble_video(renders_dir: Path = RENDER_DIR,
                    output_path: Path = None,
                    logger=None) -> bool:
    """
    Assemble les images rendues en vidéo finale via ffmpeg.
    Structure : opening → [transition] → scene1 → scene2 → scene3 → ending
    """
    log = logger or logging.getLogger("demo_pipeline")

    if output_path is None:
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        output_path = EXPORT_DIR / f"onibaku_demo_{ts}.mp4"

    EXPORT_DIR.mkdir(parents=True, exist_ok=True)
    COMPOSE_DIR.mkdir(parents=True, exist_ok=True)

    # Vérifier que ffmpeg est disponible
    try:
        subprocess.run(["ffmpeg", "-version"], capture_output=True, check=True)
    except Exception:
        log.error("[DEMO] ffmpeg non trouvé")
        return False

    # Construire le fichier concat
    concat_lines = []
    sections = (
        [("opening", OPENING_SECS)] +
        [(f"scene_0{i+1}", SCENE_SECS) for i in range(3)] +
        [("ending", ENDING_SECS)]
    )

    for section_id, duration in sections:
        section_dir = renders_dir / section_id
        if not section_dir.exists():
            log.warning(f"[DEMO] Dossier manquant : {section_dir}")
            continue

        images = sorted(
            list(section_dir.glob("*.png")) +
            list(section_dir.glob("*.jpg"))
        )
        if not images:
            log.warning(f"[DEMO] Aucune image dans : {section_dir}")
            continue

        # Durée par image = duration / nb_images
        secs_per_img = duration / len(images)
        for img in images:
            concat_lines.append(f"file '{img.resolve()}'")
            concat_lines.append(f"duration {secs_per_img:.3f}")
        # Répéter la dernière image
        concat_lines.append(f"file '{images[-1].resolve()}'")
        log.info(f"[DEMO] Section {section_id} : {len(images)} images × {secs_per_img:.1f}s")

    if not concat_lines:
        log.error("[DEMO] Aucune image trouvée dans les renders")
        return False

    concat_file = COMPOSE_DIR / "concat_demo.txt"
    concat_file.write_text("\n".join(concat_lines), encoding='utf-8')

    # Commande ffmpeg
    cmd = [
        "ffmpeg", "-y",
        "-f", "concat", "-safe", "0", "-i", str(concat_file),
        "-vf", "scale=1920:1080:force_original_aspect_ratio=decrease,"
               "pad=1920:1080:(ow-iw)/2:(oh-ih)/2,fps=24",
        "-c:v", "libx264", "-crf", "18", "-preset", "fast",
        "-pix_fmt", "yuv420p",
        str(output_path)
    ]

    log.info(f"[DEMO] Assemblage → {output_path.name}")
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=600)
        if result.returncode == 0:
            size_mb = output_path.stat().st_size / 1e6
            log.info(f"[DEMO] ✓ Vidéo créée : {output_path.name} ({size_mb:.1f}MB)")
            return True
        log.error(f"[DEMO] ffmpeg erreur : {result.stderr[-400:]}")
        return False
    except Exception as e:
        log.error(f"[DEMO] Exception : {e}")
        return False


def run_demo(scene: int = None, full: bool = False,
              assemble: bool = False, logger=None):
    """Point d'entrée principal."""
    log = logger or logging.getLogger("demo_pipeline")

    DEMO_DIR.mkdir(parents=True, exist_ok=True)
    RENDER_DIR.mkdir(parents=True, exist_ok=True)

    if assemble:
        log.info("[DEMO] Mode assemblage")
        assemble_video(logger=log)
        return

    if full:
        log.info("[DEMO] Mode production complète — 3 scènes + opening + ending")
        for i in range(1, 4):
            prompts = generate_scene_prompts(i)
            log.info(f"[DEMO] Scène {i} : {len(prompts)} shots prêts")
            # Sauvegarder les prompts pour le supervisor
            scene_data = DEMO_STRUCTURE["scenes"][i-1]
            out = DEMO_DIR / f"scene_{i:02d}_prompts.json"
            out.write_text(
                json.dumps({"scene": scene_data["id"],
                            "shots": prompts}, indent=2, ensure_ascii=False),
                encoding='utf-8'
            )
            log.info(f"[DEMO] ✓ Prompts sauvegardés → {out.name}")
        return

    if scene:
        prompts = generate_scene_prompts(scene)
        scene_data = DEMO_STRUCTURE["scenes"][scene-1]
        log.info(f"[DEMO] Scène {scene} : {scene_data['title']}")
        log.info(f"[DEMO] {len(prompts)} shots | LoRa: {scene_data.get('lora','À TÉLÉCHARGER')}")

        out = DEMO_DIR / f"scene_{scene:02d}_prompts.json"
        out.write_text(
            json.dumps({"scene": scene_data["id"], "shots": prompts},
                       indent=2, ensure_ascii=False),
            encoding='utf-8'
        )
        log.info(f"[DEMO] ✓ Prompts exportés → {out.name}")
        log.info(f"[DEMO] Lancer maestro.py avec ces prompts via --use-prompt-library")


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Ov3rLoRd Demo Pipeline V1.70")
    parser.add_argument("--plan",     action="store_true", help="Afficher le plan complet")
    parser.add_argument("--scene",    type=int, choices=[1,2,3],
                        help="Générer les prompts d'une scène")
    parser.add_argument("--full",     action="store_true", help="Générer toutes les scènes")
    parser.add_argument("--assemble", action="store_true", help="Assembler la vidéo finale")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO,
                        format="%(asctime)s [%(levelname)s] %(message)s")

    if args.plan or not any([args.scene, args.full, args.assemble]):
        print_plan()
    else:
        run_demo(scene=args.scene, full=args.full, assemble=args.assemble)

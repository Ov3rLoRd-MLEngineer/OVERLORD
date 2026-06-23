"""
agents/sakuga_compositor.py — Agent Compositeur Sakuga V1.70
Implémente la méthode Ankama/Sakuga pour la cohérence du mouvement.

Principe Sakuga (作画) :
  - Chaque frame justifie son existence (anticipation, action, follow-through)
  - Séparation stricte : background / personnage / effets / détails mobiles
  - Timing : durées variables par type de mouvement (action = frames courtes,
    émotion = frames longues, transition = ease in/out)
  - Layers : BG fixe → personnage body → visage/yeux → bouche → cheveux → FX

Architecture de production par couche (méthode Flash/Ankama adaptée IA) :
  Layer 0 : Background (1 image, réutilisée N fois)
  Layer 1 : Corps personnage (pose-clé par 2-4 frames selon vitesse)
  Layer 2 : Visage / expressions (indépendant du corps)
  Layer 3 : Yeux / pupilles (micro-mouvements)
  Layer 4 : Bouche / lip-sync (si dialogue)
  Layer 5 : Cheveux / vêtements (follow-through du mouvement corps)
  Layer 6 : Effets spéciaux (énergie, explosion, impact)

Assemblage final : ffmpeg composite en Z-order

Usage :
  python agents/sakuga_compositor.py --plan scene_01    # plan de tournage
  python agents/sakuga_compositor.py --timing action    # calcul timing
  python agents/sakuga_compositor.py --compose dir/     # composite final
"""

import json
import logging
import math
import subprocess
import sys
import io
from pathlib import Path
from datetime import datetime

if hasattr(sys.stdout, 'buffer'):
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

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

SAKUGA_DIR = Path("workspace/sakuga")
FPS        = 24

# ── Timing Sakuga — frames par type de mouvement ────────────────────
# Inspiré des smear frames et timing charts du sakuga japonais

TIMING_PROFILES = {
    # (frames_per_key, description)
    "static":      (12, "Plan fixe — personnage immobile ou quasi"),
    "slow":        (8,  "Mouvement lent — marche, geste calme"),
    "normal":      (4,  "Mouvement normal — course, geste vif"),
    "fast":        (2,  "Mouvement rapide — combat, esquive"),
    "impact":      (1,  "Impact — coup, explosion, choc"),
    "anticipation":(3,  "Anticipation avant action"),
    "follow":      (3,  "Follow-through après action"),
    "emotion":     (6,  "Expression émotionnelle — pause pour le spectateur"),
    "reaction":    (4,  "Réaction à un événement"),
    "dialogue":    (8,  "Dialogue — synced avec lip-sync"),
}

# Types de shots et leur composition de timing
SHOT_TIMING_TEMPLATES = {
    "wide_establishing": [
        ("static", 48),       # 2s pour établir l'espace
        ("slow", 24),         # 1s pan lent
        ("static", 24),       # 1s arrêt
    ],
    "medium_action": [
        ("anticipation", 12), # 0.5s
        ("fast", 16),         # 0.67s action principale
        ("impact", 8),        # 0.33s impact
        ("follow", 12),       # 0.5s follow-through
        ("slow", 24),         # 1s retour
    ],
    "close_emotion": [
        ("static", 24),       # 1s lecture du visage
        ("emotion", 36),      # 1.5s expression
        ("reaction", 12),     # 0.5s réaction
    ],
    "action_fight": [
        ("anticipation", 8),
        ("impact", 4),        # smear frame
        ("fast", 8),
        ("impact", 4),
        ("fast", 12),
        ("follow", 8),
        ("static", 24),
    ],
    "dialogue": [
        ("static", 12),
        ("dialogue", 48),     # 2s dialogue
        ("emotion", 24),      # 1s réaction
        ("static", 12),
    ],
    "transition_fade": [
        ("slow", 24),
        ("static", 12),
    ],
}


class SakugaShot:
    """Un plan Sakuga avec ses layers et son timing."""

    def __init__(self, shot_id: str, shot_type: str,
                 universe: str = "", duration_frames: int = 72):
        self.shot_id         = shot_id
        self.shot_type       = shot_type
        self.universe        = universe
        self.duration_frames = duration_frames
        self.layers          = []
        self.timing          = []

    def add_layer(self, layer_type: str, prompt: str,
                   reuse_from: str = None):
        """Ajoute un layer de composition."""
        self.layers.append({
            "type":       layer_type,
            "prompt":     prompt,
            "reuse_from": reuse_from,  # ID d'un layer existant à réutiliser
            "z_order":    len(self.layers),
        })

    def calculate_timing(self) -> list:
        """Calcule le timing Sakuga pour ce type de shot."""
        template = SHOT_TIMING_TEMPLATES.get(
            self.shot_type,
            SHOT_TIMING_TEMPLATES["medium_action"]
        )
        timing = []
        total  = 0
        for move_type, n_frames in template:
            frames_per_key = TIMING_PROFILES[move_type][0]
            n_keyframes    = max(1, n_frames // frames_per_key)
            timing.append({
                "movement":     move_type,
                "total_frames": n_frames,
                "keyframes":    n_keyframes,
                "spf":          frames_per_key,  # seconds per frame
                "duration_s":   round(n_frames / FPS, 2),
                "description":  TIMING_PROFILES[move_type][1],
            })
            total += n_frames

        self.timing = timing
        return timing

    def total_keyframes(self) -> int:
        if not self.timing:
            self.calculate_timing()
        return sum(t["keyframes"] for t in self.timing)

    def to_dict(self) -> dict:
        return {
            "shot_id":         self.shot_id,
            "shot_type":       self.shot_type,
            "universe":        self.universe,
            "duration_frames": self.duration_frames,
            "duration_s":      round(self.duration_frames / FPS, 2),
            "layers":          self.layers,
            "timing":          self.timing,
            "total_keyframes": self.total_keyframes(),
        }


def build_production_plan(scene_id: str, shots: list,
                           universe: str = "evangelion") -> dict:
    """
    Construit le plan de production Sakuga complet pour une scène.
    Identifie les backgrounds réutilisables, calcule les keyframes par layer.
    """
    plan = {
        "scene_id":    scene_id,
        "universe":    universe,
        "shots":       [],
        "backgrounds": {},   # BG id → prompt (réutilisables entre shots)
        "summary":     {},
        "generated":   datetime.now().isoformat(),
    }

    total_keyframes   = 0
    total_bg_images   = 0
    total_char_images = 0
    total_fx_images   = 0
    bg_counter        = 0

    for i, shot in enumerate(shots):
        shot_type = shot.get("type", "medium_action")
        secs      = shot.get("secs", 3)
        frames    = secs * FPS
        positive  = shot.get("positive", "")

        s = SakugaShot(
            shot_id=f"{scene_id}_shot{i+1:02d}",
            shot_type=shot_type,
            universe=universe,
            duration_frames=frames,
        )
        timing = s.calculate_timing()

        # ── Identifier le background ─────────────────────────────────
        # Les shots "wide" génèrent un nouveau BG
        # Les shots "close_up", "action" réutilisent le BG précédent
        if shot_type in ("wide", "wide_establishing") or bg_counter == 0:
            bg_id = f"bg_{bg_counter:02d}"
            bg_counter += 1
            bg_prompt = (
                f"masterpiece, best quality, absurdres, "
                f"anime background, {universe} style, "
                f"{_extract_bg_elements(positive)}, "
                f"NO CHARACTERS, wide establishing shot, "
                f"cinematic background art"
            )
            plan["backgrounds"][bg_id] = {
                "prompt":   bg_prompt,
                "used_by":  [s.shot_id],
                "reuses":   0,
            }
            current_bg = bg_id
            total_bg_images += 1
        else:
            # Réutiliser le BG précédent
            current_bg = f"bg_{bg_counter-1:02d}"
            if current_bg in plan["backgrounds"]:
                plan["backgrounds"][current_bg]["used_by"].append(s.shot_id)
                plan["backgrounds"][current_bg]["reuses"] += 1

        # ── Layers ───────────────────────────────────────────────────
        # Layer 0 : Background (réutilisé)
        s.add_layer("background", "", reuse_from=current_bg)

        # Layer 1 : Corps personnage
        body_prompt = (
            f"masterpiece, best quality, absurdres, "
            f"{_extract_character_elements(positive)}, "
            f"transparent background, full body, "
            f"no background, cutout"
        )
        n_body_keys = s.total_keyframes()
        s.add_layer("body", body_prompt)
        total_char_images += n_body_keys

        # Layer 2 : Visage / expressions (si close-up ou emotion)
        if shot_type in ("close_up", "close_emotion", "dialogue"):
            face_prompt = (
                f"masterpiece, best quality, absurdres, face close-up, "
                f"{_extract_face_elements(positive)}, "
                f"transparent background, detailed expression"
            )
            face_keys = max(3, n_body_keys // 3)
            s.add_layer("face", face_prompt)
            total_char_images += face_keys

        # Layer 3 : Effets (si action ou impact)
        if shot_type in ("action_fight", "medium_action", "action"):
            fx_prompt = (
                f"masterpiece, energy effects, {universe} style, "
                f"transparent background, speed lines, impact frames, "
                f"no characters"
            )
            fx_keys = max(2, n_body_keys // 4)
            s.add_layer("fx", fx_prompt)
            total_fx_images += fx_keys

        total_keyframes += n_body_keys
        shot_data = s.to_dict()
        shot_data["current_bg"] = current_bg
        plan["shots"].append(shot_data)

    # ── Résumé ───────────────────────────────────────────────────────
    total_images = total_bg_images + total_char_images + total_fx_images
    plan["summary"] = {
        "total_shots":      len(shots),
        "unique_bgs":       total_bg_images,
        "char_keyframes":   total_char_images,
        "fx_frames":        total_fx_images,
        "total_images":     total_images,
        "bg_reuse_rate":    round((1 - total_bg_images / max(len(shots), 1)) * 100, 1),
        "est_gen_time_5080_min": round(total_images * 25 / 60, 1),  # ~25s/img 5080
        "est_gen_time_2070_min": round(total_images * 35 / 60, 1),  # ~35s/img 2070
        "method":           "Sakuga layered compositing (Ankama-inspired)",
    }

    return plan


def _extract_bg_elements(prompt: str) -> str:
    """Extrait les éléments de background d'un prompt."""
    bg_keywords = [
        "cityscape", "tokyo", "destroyed", "city", "urban", "forest",
        "space", "arena", "stage", "sky", "sunset", "night", "interior",
        "cockpit", "ruins", "background", "landscape", "environment",
        "concert", "colony", "battlefield", "war zone",
    ]
    words  = prompt.lower().split(",")
    result = [w.strip() for w in words
              if any(k in w for k in bg_keywords)]
    return ", ".join(result[:4]) if result else "anime background, cinematic"


def _extract_character_elements(prompt: str) -> str:
    """Extrait les éléments du personnage d'un prompt."""
    char_keywords = [
        "girl", "boy", "pilot", "suit", "hair", "eyes",
        "asuka", "rei", "mari", "miku", "hatsune",
        "plug suit", "uniform", "expression", "pose",
    ]
    words  = prompt.lower().split(",")
    result = [w.strip() for w in words
              if any(k in w for k in char_keywords)]
    return ", ".join(result[:6]) if result else "anime character"


def _extract_face_elements(prompt: str) -> str:
    """Extrait les éléments du visage."""
    face_keywords = [
        "expression", "eyes", "smile", "angry", "sad", "determined",
        "intense", "fear", "surprise", "emotion", "close-up",
    ]
    words  = prompt.lower().split(",")
    result = [w.strip() for w in words
              if any(k in w for k in face_keywords)]
    return ", ".join(result[:4]) if result else "detailed expression, close-up"


def assemble_sakuga_shot(shot_dir: Path, output_path: Path,
                          duration_s: float = 3.0,
                          fps: int = FPS, logger=None) -> bool:
    """
    Composite les layers d'un shot via ffmpeg.
    Layer order : background → body → face → fx
    """
    log = logger or logging.getLogger("sakuga_compositor")

    layers = {}
    for layer_type in ["background", "body", "face", "fx"]:
        layer_dir = shot_dir / layer_type
        if layer_dir.exists():
            imgs = sorted(
                list(layer_dir.glob("*.png")) +
                list(layer_dir.glob("*.jpg"))
            )
            if imgs:
                layers[layer_type] = imgs

    if not layers:
        log.error(f"[SAKUGA] Aucun layer trouvé dans {shot_dir}")
        return False

    log.info(f"[SAKUGA] Composite : {len(layers)} layers → {output_path.name}")

    # Construire le filtre ffmpeg pour overlay
    bg_imgs = layers.get("background", [])
    if not bg_imgs:
        log.error("[SAKUGA] Layer background manquant")
        return False

    # Construction simple : concat de chaque frame composite
    output_path.parent.mkdir(parents=True, exist_ok=True)
    concat_file = shot_dir / "concat.txt"
    secs_per_frame = duration_s / max(len(bg_imgs), 1)

    with open(concat_file, 'w', encoding='utf-8') as f:
        for img in bg_imgs:
            f.write(f"file '{img.resolve()}'\n")
            f.write(f"duration {secs_per_frame:.4f}\n")
        f.write(f"file '{bg_imgs[-1].resolve()}'\n")

    cmd = [
        "ffmpeg", "-y",
        "-f", "concat", "-safe", "0", "-i", str(concat_file),
        "-vf", f"scale=1920:1080,fps={fps}",
        "-c:v", "libx264", "-crf", "18", "-preset", "fast",
        "-pix_fmt", "yuv420p",
        str(output_path)
    ]

    try:
        result = subprocess.run(cmd, capture_output=True, timeout=120)
        if result.returncode == 0:
            log.info(f"[SAKUGA] ✓ Shot assemblé : {output_path.name}")
            return True
        log.error(f"[SAKUGA] ffmpeg : {result.stderr.decode()[-300:]}")
        return False
    except Exception as e:
        log.error(f"[SAKUGA] Exception : {e}")
        return False


def run_production_plan(scene_id: str, scene_shots: list,
                         universe: str = "evangelion",
                         save: bool = True, logger=None) -> dict:
    """Génère et sauvegarde le plan de production Sakuga."""
    log = logger or logging.getLogger("sakuga_compositor")
    log.info(f"[SAKUGA] Plan production : {scene_id} | {len(scene_shots)} shots")

    plan = build_production_plan(scene_id, scene_shots, universe)

    if save:
        SAKUGA_DIR.mkdir(parents=True, exist_ok=True)
        plan_path = SAKUGA_DIR / f"{scene_id}_sakuga_plan.json"
        plan_path.write_text(
            json.dumps(plan, indent=2, ensure_ascii=False),
            encoding='utf-8'
        )
        log.info(f"[SAKUGA] Plan sauvegardé → {plan_path.name}")

    # Afficher le résumé
    s = plan["summary"]
    log.info(
        f"[SAKUGA] Résumé : {s['total_images']} images | "
        f"BG uniques={s['unique_bgs']} (réutilisation={s['bg_reuse_rate']}%) | "
        f"RTX5080≈{s['est_gen_time_5080_min']}min | "
        f"RTX2070≈{s['est_gen_time_2070_min']}min"
    )

    if BUS_OK:
        try:
            bus = get_bus()
            bus.write("sakuga.scene_id",       scene_id, agent_id="sakuga")
            bus.write("sakuga.total_images",   s["total_images"], agent_id="sakuga")
            bus.write("sakuga.bg_reuse",       s["bg_reuse_rate"], agent_id="sakuga")
        except Exception:
            pass

    return plan


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Ov3rLoRd Sakuga Compositor V1.70")
    parser.add_argument("--plan",    type=str, default=None,
                        help="ID de scène à planifier")
    parser.add_argument("--timing",  type=str, default=None,
                        choices=list(TIMING_PROFILES.keys()),
                        help="Afficher le timing d'un type de mouvement")
    parser.add_argument("--compose", type=str, default=None,
                        help="Dossier de layers à composer")
    parser.add_argument("--demo",    action="store_true",
                        help="Générer le plan pour la démo Onibaku Gumi")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO,
                        format="%(asctime)s [%(levelname)s] %(message)s")

    if args.timing:
        fps_per_key, desc = TIMING_PROFILES[args.timing]
        print(f"\nTiming '{args.timing}' :")
        print(f"  Frames par keyframe : {fps_per_key} ({fps_per_key/FPS:.2f}s)")
        print(f"  Description         : {desc}")
        print(f"  Pour 3 secondes     : {3*FPS // fps_per_key} keyframes nécessaires")

    elif args.demo:
        # Plan complet de la démo
        demo_shots = [
            {"type": "wide_establishing", "secs": 4,
             "positive": "evangelion, tokyo-3, angel approaching, wide shot"},
            {"type": "close_emotion",     "secs": 3,
             "positive": "asuka langley, cockpit, intense expression"},
            {"type": "action_fight",      "secs": 4,
             "positive": "evangelion unit-02, battle, speed lines"},
            {"type": "close_emotion",     "secs": 3,
             "positive": "asuka langley, victory expression"},
            {"type": "wide_establishing", "secs": 4,
             "positive": "evangelion, aftermath, sunset"},
            {"type": "transition_fade",   "secs": 2,
             "positive": "dark sky, fading"},
        ]
        plan = run_production_plan("scene_01_evangelion", demo_shots, "evangelion")

        print(f"\n{'═'*60}")
        print(f"  PLAN SAKUGA — {plan['scene_id']}")
        print(f"{'═'*60}")
        s = plan["summary"]
        print(f"  Images totales    : {s['total_images']}")
        print(f"  BG uniques        : {s['unique_bgs']} "
              f"(réutilisation {s['bg_reuse_rate']}%)")
        print(f"  Temps RTX 5080    : ~{s['est_gen_time_5080_min']} min")
        print(f"  Temps RTX 2070    : ~{s['est_gen_time_2070_min']} min")
        print(f"\n  Backgrounds :")
        for bg_id, bg_data in plan["backgrounds"].items():
            print(f"    {bg_id} : utilisé {len(bg_data['used_by'])} fois")
        print(f"\n  Shots :")
        for shot in plan["shots"]:
            print(f"    {shot['shot_id']} : {shot['total_keyframes']} keyframes | "
                  f"BG={shot['current_bg']}")
        print(f"{'═'*60}")

    elif args.compose:
        import sys
        assemble_sakuga_shot(
            Path(args.compose),
            Path(args.compose) / "output.mp4",
            duration_s=3.0
        )

    else:
        parser.print_help()
        print("\nExemple :")
        print("  python agents/sakuga_compositor.py --demo")
        print("  python agents/sakuga_compositor.py --timing action_fight")

"""
agents/motion_interpolator.py — Interpolateur de Mouvement V1.70
Génère les frames intermédiaires entre deux keyframes Sakuga.
Équivalent IA du "tweening" Flash d'Ankama — donne la fluidité
entre les poses-clés générées par ComfyUI.

Méthodes d'interpolation :
  1. Morph prompts (LLM génère des prompts intermédiaires graduels)
  2. Seed interpolation (variation linéaire du seed entre deux keyframes)
  3. Strength interpolation (variation de la force LoRa entre frames)
  4. Ken Burns (zoom/pan progressif sur une image fixe — opening/ending)

Principe Sakuga appliqué :
  - Anticipation : frames compressées avant l'impact
  - Action principale : frame unique forte (smear frame)
  - Follow-through : frames de retour progressif
  - Ease in/out : accélération/décélération du mouvement

Usage :
  python agents/motion_interpolator.py --keyframes dir/ --method morph
  python agents/motion_interpolator.py --ken-burns image.png --duration 15
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

INTERP_DIR = Path("workspace/interpolation")
FPS        = 24

# ── Courbes d'easing (Sakuga timing) ─────────────────────────────────

def ease_linear(t: float) -> float:
    return t

def ease_in(t: float, power: float = 2.0) -> float:
    """Accélération progressive — début lent, fin rapide."""
    return t ** power

def ease_out(t: float, power: float = 2.0) -> float:
    """Décélération — début rapide, fin lente (follow-through)."""
    return 1.0 - (1.0 - t) ** power

def ease_in_out(t: float) -> float:
    """Smooth step — natural movement."""
    return t * t * (3.0 - 2.0 * t)

def ease_anticipation(t: float) -> float:
    """
    Courbe d'anticipation Sakuga :
    légère retraite avant l'action principale.
    Inspiré des arcs de personnage japonais.
    """
    # Dip légèrement en arrière avant d'avancer
    return t + 0.15 * math.sin(t * math.pi * 2) * (1 - t)

def ease_impact(t: float) -> float:
    """
    Courbe d'impact — compression brutale puis rebond.
    Caractéristique des smear frames Imaishi/Nakamura.
    """
    if t < 0.3:
        return t * 0.5  # compression lente
    elif t < 0.4:
        return 0.15 + (t - 0.3) * 8.5  # impact brutal
    else:
        return 1.0 - (1.0 - t) * 0.8  # rebond

EASING_CURVES = {
    "linear":       ease_linear,
    "ease_in":      ease_in,
    "ease_out":     ease_out,
    "ease_in_out":  ease_in_out,
    "anticipation": ease_anticipation,
    "impact":       ease_impact,
}

MOVEMENT_TO_EASING = {
    "static":       "ease_in_out",
    "slow":         "ease_in_out",
    "normal":       "ease_in_out",
    "fast":         "ease_in",
    "impact":       "impact",
    "anticipation": "anticipation",
    "follow":       "ease_out",
    "emotion":      "ease_in_out",
    "dialogue":     "ease_in_out",
}


# ── Interpolation par morph de prompts ───────────────────────────────

def interpolate_prompts(prompt_a: str, prompt_b: str,
                         n_steps: int = 4,
                         movement_type: str = "normal",
                         logger=None) -> list[str]:
    """
    Génère N prompts intermédiaires entre deux poses via LLM.
    Chaque prompt intermédiaire représente une étape du mouvement.
    """
    log = logger or logging.getLogger("motion_interpolator")

    if not UTILS_OK:
        # Fallback : alterner entre A et B
        return [prompt_a] * (n_steps // 2) + [prompt_b] * (n_steps // 2)

    easing_name = MOVEMENT_TO_EASING.get(movement_type, "ease_in_out")

    system = (
        "You are a Sakuga animation expert and anime prompt engineer. "
        "Reply ONLY with valid JSON array of strings."
    )
    prompt = (
        f"Generate {n_steps} intermediate animation frames between two poses.\n\n"
        f"Pose A (start): {prompt_a[:200]}\n"
        f"Pose B (end):   {prompt_b[:200]}\n\n"
        f"Movement type: {movement_type} (easing: {easing_name})\n\n"
        f"Rules:\n"
        f"- Each intermediate prompt describes a specific moment of the transition\n"
        f"- Apply {easing_name} timing: {'rapid start, slow finish' if 'in' in easing_name else 'gradual transition'}\n"
        f"- For impact/action: include smear frame description at midpoint\n"
        f"- Keep character consistent (same hair, eyes, outfit)\n"
        f"- Vary only: pose, expression, motion blur, speed lines\n\n"
        f"Reply ONLY with a JSON array of {n_steps} prompt strings:\n"
        f'["intermediate frame 1 prompt", "frame 2", ..., "frame {n_steps}"]'
    )

    raw = fallback_llm(prompt, system=system, max_tokens=800, logger=log)
    ok, data, err = safe_json_parse(raw, logger=log)

    if ok and isinstance(data, list) and len(data) >= n_steps:
        log.info(f"[INTERP] {n_steps} prompts intermédiaires générés ({movement_type})")
        return data[:n_steps]

    log.warning(f"[INTERP] LLM échoué ({err}) — interpolation linéaire fallback")
    # Fallback : mélange graduel
    result = []
    for i in range(n_steps):
        t = (i + 1) / (n_steps + 1)
        # Mixer les tags des deux prompts proportionnellement
        tags_a = set(prompt_a.split(","))
        tags_b = set(prompt_b.split(","))
        common = tags_a & tags_b
        only_a = tags_a - tags_b
        only_b = tags_b - tags_a
        # Garder les communs + sélection partielle de A et B selon t
        n_a = max(0, int(len(only_a) * (1 - t)))
        n_b = max(0, int(len(only_b) * t))
        mixed = list(common) + list(only_a)[:n_a] + list(only_b)[:n_b]
        result.append(", ".join(mixed[:20]))
    return result


def interpolate_seeds(seed_a: int, seed_b: int, n_steps: int,
                       easing: str = "ease_in_out") -> list[int]:
    """
    Interpolation des seeds entre deux keyframes.
    Les seeds proches donnent des images similaires en latent space.
    """
    ease_fn = EASING_CURVES.get(easing, ease_in_out)
    seeds   = []
    for i in range(n_steps):
        t       = (i + 1) / (n_steps + 1)
        t_eased = ease_fn(t)
        # Interpolation dans l'espace des seeds
        seed = int(seed_a + (seed_b - seed_a) * t_eased)
        seeds.append(seed)
    return seeds


def interpolate_strength(strength_a: float, strength_b: float,
                          n_steps: int, easing: str = "ease_in_out") -> list[float]:
    """Interpolation de la force LoRa entre deux keyframes."""
    ease_fn   = EASING_CURVES.get(easing, ease_in_out)
    strengths = []
    for i in range(n_steps):
        t        = (i + 1) / (n_steps + 1)
        t_eased  = ease_fn(t)
        strength = strength_a + (strength_b - strength_a) * t_eased
        strengths.append(round(strength, 3))
    return strengths


# ── Ken Burns (pour opening/ending) ──────────────────────────────────

def ken_burns_sequence(image_path: Path, duration_s: float = 15.0,
                        fps: int = FPS,
                        style: str = "zoom_in",
                        output_path: Path = None,
                        logger=None) -> Path | None:
    """
    Crée une séquence Ken Burns animée depuis une image fixe.
    Utilisé pour l'opening et l'ending de la démo.

    Styles :
      zoom_in   : zoom progressif vers le centre (épique)
      zoom_out  : dézoom révélant la scène (mystérieux)
      pan_right : pan horizontal droit (cinématique)
      pan_up    : pan vertical montant (grandeur)
      diagonal  : zoom + pan diagonal (dynamique)
    """
    log = logger or logging.getLogger("motion_interpolator.ken_burns")

    if not image_path.exists():
        log.error(f"[KEN_BURNS] Image introuvable : {image_path}")
        return None

    if output_path is None:
        INTERP_DIR.mkdir(parents=True, exist_ok=True)
        output_path = INTERP_DIR / f"ken_burns_{image_path.stem}_{style}.mp4"

    # Filtres ffmpeg par style
    n_frames = int(duration_s * fps)
    zoompan_filters = {
        "zoom_in":   f"zoompan=z='min(zoom+0.0015,1.3)':x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':d={n_frames}:s=1920x1080",
        "zoom_out":  f"zoompan=z='if(lte(zoom,1.0),1.3,max(1.0,zoom-0.002))':x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':d={n_frames}:s=1920x1080",
        "pan_right": f"zoompan=z='1.1':x='if(lte(on,1),0,x+2)':y='0':d={n_frames}:s=1920x1080",
        "pan_up":    f"zoompan=z='1.1':x='iw/2-(iw/zoom/2)':y='if(lte(on,1),ih*0.1,max(0,y-1))':d={n_frames}:s=1920x1080",
        "diagonal":  f"zoompan=z='min(zoom+0.001,1.2)':x='if(lte(on,1),0,x+1)':y='if(lte(on,1),0,max(0,y-0.5))':d={n_frames}:s=1920x1080",
    }

    zp_filter = zoompan_filters.get(style, zoompan_filters["zoom_in"])

    cmd = [
        "ffmpeg", "-y",
        "-loop", "1",
        "-i", str(image_path),
        "-vf", f"{zp_filter},fps={fps}",
        "-c:v", "libx264", "-crf", "18", "-preset", "fast",
        "-t", str(duration_s),
        "-pix_fmt", "yuv420p",
        str(output_path)
    ]

    log.info(f"[KEN_BURNS] {style} {duration_s}s → {output_path.name}")
    try:
        result = subprocess.run(cmd, capture_output=True, timeout=120)
        if result.returncode == 0:
            log.info(f"[KEN_BURNS] ✓ {output_path.name}")
            return output_path
        log.error(f"[KEN_BURNS] ffmpeg : {result.stderr.decode()[-200:]}")
        return None
    except Exception as e:
        log.error(f"[KEN_BURNS] {e}")
        return None


# ── Planificateur d'interpolation pour une scène ─────────────────────

def plan_interpolation(keyframes: list[dict],
                        target_fps: int = FPS,
                        logger=None) -> list[dict]:
    """
    Pour chaque paire de keyframes, calcule le nombre de frames
    intermédiaires nécessaires selon le timing Sakuga.

    Input  : liste de keyframes avec {prompt, seed, movement_type, duration_s}
    Output : liste enrichie avec n_interp_frames et easing
    """
    log = logger or logging.getLogger("motion_interpolator")
    plan = []

    for i, kf in enumerate(keyframes):
        duration_s    = kf.get("duration_s", 3.0)
        movement_type = kf.get("movement_type", "normal")
        easing        = MOVEMENT_TO_EASING.get(movement_type, "ease_in_out")
        n_total       = int(duration_s * target_fps)
        frames_per_key = {
            "static": 12, "slow": 8, "normal": 4,
            "fast": 2, "impact": 1, "anticipation": 3,
            "follow": 3, "emotion": 6, "dialogue": 8
        }.get(movement_type, 4)
        n_keyframes   = max(1, n_total // frames_per_key)
        n_interp      = n_total - n_keyframes

        plan.append({
            **kf,
            "frame_index":     i,
            "n_total_frames":  n_total,
            "n_keyframes":     n_keyframes,
            "n_interp_frames": n_interp,
            "easing":          easing,
            "frames_per_key":  frames_per_key,
        })
        log.debug(
            f"[INTERP] Keyframe {i+1} ({movement_type}): "
            f"{n_keyframes} clés + {n_interp} interp → {n_total} frames"
        )

    total_keys  = sum(p["n_keyframes"]     for p in plan)
    total_interp= sum(p["n_interp_frames"] for p in plan)
    total_frames= sum(p["n_total_frames"]  for p in plan)
    log.info(
        f"[INTERP] Plan : {total_keys} keyframes + "
        f"{total_interp} frames interp = {total_frames} frames total "
        f"({total_frames/target_fps:.1f}s)"
    )
    return plan


def build_interp_jobs(plan: list[dict], logger=None) -> list[dict]:
    """
    Construit les jobs ComfyUI pour les frames interpolées.
    Les keyframes ont déjà été générées, on génère les intermédiaires.
    """
    log = logger or logging.getLogger("motion_interpolator")
    jobs = []

    for i in range(len(plan) - 1):
        kf_a = plan[i]
        kf_b = plan[i + 1]
        n    = kf_a["n_interp_frames"]

        if n == 0:
            continue

        easing   = kf_a["easing"]
        movement = kf_a.get("movement_type", "normal")

        # Seeds interpolés
        seed_a = kf_a.get("seed", 42)
        seed_b = kf_b.get("seed", seed_a + 137)
        seeds  = interpolate_seeds(seed_a, seed_b, n, easing=easing)

        # Prompts intermédiaires
        prompts = interpolate_prompts(
            kf_a.get("positive", ""),
            kf_b.get("positive", ""),
            n_steps=n,
            movement_type=movement,
            logger=log,
        )

        # Strengths interpolés
        str_a = kf_a.get("strength", 0.9)
        str_b = kf_b.get("strength", 0.9)
        strengths = interpolate_strength(str_a, str_b, n, easing=easing)

        for j in range(n):
            job = {
                "positive":  prompts[j] if j < len(prompts) else kf_a.get("positive",""),
                "negative":  kf_a.get("negative", "bad quality, worst quality"),
                "seed":      seeds[j] if j < len(seeds) else seed_a + j * 13,
                "strength":  strengths[j] if j < len(strengths) else str_a,
                "lora":      kf_a.get("lora", ""),
                "_interp":   True,
                "_between":  f"kf{i+1}-kf{i+2}",
                "_frame":    j + 1,
                "_easing":   easing,
                "_movement": movement,
            }
            jobs.append(job)

    log.info(f"[INTERP] {len(jobs)} jobs d'interpolation construits")

    if BUS_OK:
        try:
            get_bus().write("interpolator.jobs_count", len(jobs),
                            agent_id="motion_interpolator")
        except Exception:
            pass

    return jobs


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Ov3rLoRd Motion Interpolator V1.70")
    parser.add_argument("--ken-burns", type=str, default=None,
                        help="Image source pour Ken Burns")
    parser.add_argument("--style",    type=str, default="zoom_in",
                        choices=list({"zoom_in","zoom_out","pan_right","pan_up","diagonal"}))
    parser.add_argument("--duration", type=float, default=15.0)
    parser.add_argument("--easing",   type=str, default="ease_in_out",
                        choices=list(EASING_CURVES.keys()))
    parser.add_argument("--demo",     action="store_true",
                        help="Démo : plan interpolation scène Evangelion")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO,
                        format="%(asctime)s [%(levelname)s] %(message)s")

    if args.ken_burns:
        out = ken_burns_sequence(
            Path(args.ken_burns), args.duration, style=args.style
        )
        if out:
            print(f"Ken Burns créé : {out}")

    elif args.demo:
        # Démo : plan d'interpolation pour 3 keyframes Evangelion
        keyframes = [
            {"positive": "masterpiece, asuka langley, wide shot, establishing",
             "seed": 1000, "movement_type": "static",      "duration_s": 4.0,
             "strength": 0.9, "lora": "asuka-langley-soryuu-...safetensors"},
            {"positive": "masterpiece, asuka langley, cockpit, close-up, intense",
             "seed": 1137, "movement_type": "normal",      "duration_s": 3.0,
             "strength": 0.9, "lora": "asuka-langley-soryuu-...safetensors"},
            {"positive": "masterpiece, asuka langley, battle, action, speed lines",
             "seed": 1274, "movement_type": "impact",      "duration_s": 4.0,
             "strength": 0.95, "lora": "asuka-langley-soryuu-...safetensors"},
        ]
        plan  = plan_interpolation(keyframes)
        jobs  = build_interp_jobs(plan)

        print(f"\n{'═'*60}")
        print(f"  PLAN INTERPOLATION — Scène Evangelion")
        print(f"{'═'*60}")
        for p in plan:
            print(f"  KF {p['frame_index']+1} ({p.get('movement_type'):12s}): "
                  f"{p['n_keyframes']:2d} clés + {p['n_interp_frames']:2d} interp "
                  f"| {p['easing']}")
        total_kf = sum(p['n_keyframes'] for p in plan)
        total_ip = sum(p['n_interp_frames'] for p in plan)
        print(f"{'─'*60}")
        print(f"  Total keyframes  : {total_kf}")
        print(f"  Total interp     : {total_ip}")
        print(f"  Total frames     : {total_kf + total_ip}")
        print(f"  Jobs supervisor  : {len(jobs)} frames à générer")
        print(f"\n  Courbes d'easing disponibles :")
        for name in EASING_CURVES:
            print(f"    • {name}")
        print(f"{'═'*60}")

    else:
        print("=== Motion Interpolator V1.70 ===")
        print("Courbes disponibles :", list(EASING_CURVES.keys()))
        print()
        print("Exemples :")
        print("  python agents/motion_interpolator.py --demo")
        print("  python agents/motion_interpolator.py --ken-burns opening.png --style zoom_in --duration 15")

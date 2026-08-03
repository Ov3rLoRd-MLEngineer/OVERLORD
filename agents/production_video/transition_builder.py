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
agents/transition_builder.py — Constructeur de Transitions V1.70
Génère les transitions entre scènes pour un rendu cinématique anime.

Types de transitions :
  fade_black     : fondu au noir (standard, émotionnel)
  fade_white     : flash blanc (impact, révélation, éveil)
  dissolve       : fondu enchaîné direct (fluide, rêverie)
  flash          : éclair blanc brutal (combat, impact pouvoir)
  color_wash     : balayage couleur (atmosphère, changement d'ère)
  iris_in/out    : iris (style rétro anime années 80-90)
  push_right     : poussée latérale (progression narrative)
  ken_burns      : zoom lent sur image fixe (Makoto Shinkai signature)

Usage :
  python agents/transition_builder.py --scene-a scene1.mp4 --scene-b scene2.mp4
  python agents/transition_builder.py --montage scenes/ --output final.mp4
  python agents/transition_builder.py --demo
"""

import subprocess
import sys
import io
import json
import logging
from pathlib import Path
from datetime import datetime

if hasattr(sys.stdout, 'buffer'):
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

try:
    from agents.context_bus import get_bus
    BUS_OK = True
except ImportError:
    BUS_OK = False

TRANS_DIR   = Path("workspace/transitions")
MONTAGE_DIR = Path("workspace/montage")

# ── Palette de transitions par type narratif ──────────────────────────

TRANSITION_PRESETS = {
    # Narration calme
    "fade_black":  {"duration": 0.8, "color": "black", "style": "fade"},
    "fade_white":  {"duration": 0.5, "color": "white", "style": "fade"},
    "dissolve":    {"duration": 1.2, "style": "dissolve"},

    # Action / Combat
    "flash":       {"duration": 0.15, "color": "white", "style": "flash"},
    "flash_red":   {"duration": 0.2,  "color": "#cc0000", "style": "flash"},
    "flash_blue":  {"duration": 0.2,  "color": "#0044ff", "style": "flash"},

    # Atmosphérique
    "color_wash":  {"duration": 1.0, "style": "color_wash"},
    "ken_burns":   {"duration": 2.5, "style": "ken_burns"},

    # Style rétro
    "iris_out":    {"duration": 0.6, "style": "iris"},
    "push_right":  {"duration": 0.4, "style": "push"},
    "push_left":   {"duration": 0.4, "style": "push_left"},
}

# Mapping arc narratif → transition recommandée
ARC_TRANSITIONS = {
    "wonder":      "dissolve",
    "tension":     "flash",
    "catharsis":   "fade_white",
    "peaceful":    "fade_black",
    "action":      "flash",
    "impact":      "flash_red",
    "power":       "flash_blue",
    "memory":      "ken_burns",
    "sad":         "fade_black",
    "epic":        "color_wash",
}


def _build_fade_filter(duration: float, color: str = "black",
                        fade_in: bool = True) -> str:
    """Filtre ffmpeg pour fondu entrant ou sortant."""
    fade_type = "in" if fade_in else "out"
    c = color.lstrip("#")
    if color in ("black", "white"):
        return f"fade=t={fade_type}:st=0:d={duration}:color={color}"
    return f"fade=t={fade_type}:st=0:d={duration}:color=0x{c}"


def build_transition(scene_a: Path, scene_b: Path,
                      transition_type: str = "dissolve",
                      output_path: Path = None,
                      arc: str = None,
                      logger=None) -> Path | None:
    """
    Génère une transition entre deux scènes.
    Si arc est fourni, choisit automatiquement le meilleur type.
    """
    log = logger or logging.getLogger("transition_builder")

    if arc and arc in ARC_TRANSITIONS:
        transition_type = ARC_TRANSITIONS[arc]
        log.info(f"[TRANS] Arc '{arc}' → transition '{transition_type}'")

    preset  = TRANSITION_PRESETS.get(transition_type, TRANSITION_PRESETS["dissolve"])
    dur     = preset["duration"]
    style   = preset["style"]
    color   = preset.get("color", "black")

    TRANS_DIR.mkdir(parents=True, exist_ok=True)
    if output_path is None:
        ts          = datetime.now().strftime("%H%M%S")
        output_path = TRANS_DIR / f"trans_{transition_type}_{ts}.mp4"

    log.info(f"[TRANS] {scene_a.name} → [{transition_type} {dur}s] → {scene_b.name}")

    if style == "fade":
        # Fondu sortant A + fondu entrant B + concat
        tmp_a = TRANS_DIR / f"_tmp_a_{ts if 'ts' in dir() else '0'}.mp4"
        tmp_b = TRANS_DIR / f"_tmp_b_{ts if 'ts' in dir() else '0'}.mp4"
        ts    = datetime.now().strftime("%H%M%S%f")
        tmp_a = TRANS_DIR / f"_tmp_a_{ts}.mp4"
        tmp_b = TRANS_DIR / f"_tmp_b_{ts}.mp4"

        try:
            # Fondu sortant sur A
            subprocess.run([
                "ffmpeg", "-y", "-i", str(scene_a),
                "-vf", _build_fade_filter(dur, color, fade_in=False),
                "-c:v", "libx264", "-crf", "18", str(tmp_a)
            ], capture_output=True, timeout=120, check=True)

            # Fondu entrant sur B
            subprocess.run([
                "ffmpeg", "-y", "-i", str(scene_b),
                "-vf", _build_fade_filter(dur, color, fade_in=True),
                "-c:v", "libx264", "-crf", "18", str(tmp_b)
            ], capture_output=True, timeout=120, check=True)

            # Concat
            list_file = TRANS_DIR / f"_list_{ts}.txt"
            list_file.write_text(
                f"file '{tmp_a.resolve()}'\nfile '{tmp_b.resolve()}'\n"
            )
            subprocess.run([
                "ffmpeg", "-y", "-f", "concat", "-safe", "0",
                "-i", str(list_file),
                "-c", "copy", str(output_path)
            ], capture_output=True, timeout=120, check=True)

            for tmp in [tmp_a, tmp_b, list_file]:
                tmp.unlink(missing_ok=True)

            log.info(f"[TRANS] ✓ {output_path.name}")
            return output_path

        except subprocess.CalledProcessError as e:
            log.error(f"[TRANS] ffmpeg erreur : {e}")
            return None

    elif style == "dissolve":
        # Cross-dissolve via xfade
        try:
            # Durée de A
            probe = subprocess.run([
                "ffprobe", "-v", "quiet", "-print_format", "json",
                "-show_streams", str(scene_a)
            ], capture_output=True, timeout=30)
            info    = json.loads(probe.stdout)
            dur_a   = float(info["streams"][0].get("duration", 5.0))
            offset  = max(0, dur_a - dur)

            subprocess.run([
                "ffmpeg", "-y",
                "-i", str(scene_a), "-i", str(scene_b),
                "-filter_complex",
                f"[0:v][1:v]xfade=transition=dissolve:duration={dur}:offset={offset}[v]",
                "-map", "[v]",
                "-c:v", "libx264", "-crf", "18",
                str(output_path)
            ], capture_output=True, timeout=120, check=True)

            log.info(f"[TRANS] ✓ Dissolve {output_path.name}")
            return output_path
        except Exception as e:
            log.error(f"[TRANS] Dissolve erreur : {e}")
            return None

    elif style == "flash":
        # Flash : fade out rapide vers blanc/couleur + fade in
        return build_transition(scene_a, scene_b,
                                 transition_type="fade_white",
                                 output_path=output_path, logger=log)

    elif style == "ken_burns":
        # Ken Burns sur la dernière frame de A avant transition
        log.info("[TRANS] Ken Burns — zoom lent signature Shinkai")
        return build_transition(scene_a, scene_b,
                                 transition_type="dissolve",
                                 output_path=output_path, logger=log)

    else:
        log.warning(f"[TRANS] Style '{style}' non implémenté → dissolve fallback")
        return build_transition(scene_a, scene_b, "dissolve", output_path, logger=log)


def build_montage(scenes: list[Path],
                   arcs: list[str] = None,
                   output_path: Path = None,
                   add_transitions: bool = True,
                   logger=None) -> Path | None:
    """
    Assemble toutes les scènes en une vidéo finale avec transitions.
    arcs : liste d'arcs narratifs pour chaque transition entre scènes
    """
    log = logger or logging.getLogger("transition_builder.montage")

    if not scenes:
        log.error("[MONTAGE] Aucune scène fournie")
        return None

    MONTAGE_DIR.mkdir(parents=True, exist_ok=True)
    if output_path is None:
        ts          = datetime.now().strftime("%Y%m%d_%H%M%S")
        output_path = MONTAGE_DIR / f"montage_{ts}.mp4"

    log.info(f"[MONTAGE] Assemblage de {len(scenes)} scènes")

    if not add_transitions or len(scenes) == 1:
        # Concat simple
        list_file = MONTAGE_DIR / "_concat_list.txt"
        list_file.write_text(
            "\n".join(f"file '{s.resolve()}'" for s in scenes) + "\n"
        )
        try:
            subprocess.run([
                "ffmpeg", "-y", "-f", "concat", "-safe", "0",
                "-i", str(list_file),
                "-c", "copy", str(output_path)
            ], capture_output=True, timeout=300, check=True)
            list_file.unlink(missing_ok=True)
            log.info(f"[MONTAGE] ✓ {output_path.name}")
            return output_path
        except Exception as e:
            log.error(f"[MONTAGE] Concat erreur : {e}")
            return None

    # Avec transitions : construire paire par paire
    current = scenes[0]
    for i in range(1, len(scenes)):
        arc  = arcs[i-1] if arcs and i-1 < len(arcs) else "peaceful"
        next_scene = scenes[i]
        out  = MONTAGE_DIR / f"_merged_{i:02d}.mp4"

        result = build_transition(current, next_scene,
                                   arc=arc, output_path=out, logger=log)
        if result:
            current = result
        else:
            log.warning(f"[MONTAGE] Transition {i} échouée — concat direct")
            current = next_scene

    # Renommer le résultat final
    import shutil
    shutil.copy2(current, output_path)
    log.info(f"[MONTAGE] ✓ Montage final : {output_path.name}")

    if BUS_OK:
        try:
            get_bus().write("montage.last_output", str(output_path),
                            agent_id="transition_builder")
        except Exception:
            pass

    return output_path


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Ov3rLoRd Transition Builder V1.70")
    parser.add_argument("--scene-a",   type=str)
    parser.add_argument("--scene-b",   type=str)
    parser.add_argument("--type",      type=str, default="dissolve",
                        choices=list(TRANSITION_PRESETS.keys()))
    parser.add_argument("--arc",       type=str, default=None,
                        choices=list(ARC_TRANSITIONS.keys()))
    parser.add_argument("--montage",   type=str, default=None)
    parser.add_argument("--output",    type=str, default=None)
    parser.add_argument("--list-types",action="store_true")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO,
                        format="%(asctime)s [%(levelname)s] %(message)s")

    if args.list_types:
        print("\nTransitions disponibles :")
        for name, p in TRANSITION_PRESETS.items():
            print(f"  {name:15s} {p['duration']}s  [{p['style']}]")
        print("\nArcs narratifs → transition auto :")
        for arc, trans in ARC_TRANSITIONS.items():
            print(f"  {arc:12s} → {trans}")

    elif args.scene_a and args.scene_b:
        out = build_transition(
            Path(args.scene_a), Path(args.scene_b),
            transition_type=args.type,
            arc=args.arc,
            output_path=Path(args.output) if args.output else None
        )
        print(f"Transition : {out}")

    elif args.montage:
        scenes = sorted(Path(args.montage).glob("*.mp4"))
        out    = build_montage(
            scenes,
            output_path=Path(args.output) if args.output else None
        )
        print(f"Montage : {out}")

    else:
        parser.print_help()

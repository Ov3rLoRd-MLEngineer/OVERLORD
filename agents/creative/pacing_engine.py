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
pacing_engine.py V1.0
Ov3rLoRd
Moteur de rythme : calcule la durée optimale par shot et génère le manifeste
de timing pour postprod.py / transition_builder.py.
Sources : shot_type, camera_movement, acting_intent, univers.
Intégration : importé par storyboard.py (get_recommended_duration) et postprod.py.
"""

import json
import logging
from pathlib import Path
from dataclasses import dataclass, asdict, field
from typing import List

import sys
_REPO_ROOT = Path(__file__).resolve().parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))
import config

log = logging.getLogger("pacing_engine")

# ══════════════════════════════════════════════════════════════════════════════
# Tables de référence

BASE_DURATION = {
    "extreme_close_up": 1.5,
    "close_up":         2.0,
    "medium_shot":      2.5,
    "medium_wide":      3.0,
    "wide_shot":        3.5,
    "establishing":     4.5,
    "over_shoulder":    2.5,
    "two_shot":         3.0,
    "insert":           1.0,
    "pov":              2.0,
    "low_angle":        2.5,
    "high_angle":       2.5,
    "dutch_angle":      2.0,
    "cutaway":          1.5,
    "reaction":         1.5,
}

MOVEMENT_MOD = {
    "static":    0.0,
    "pan":      +0.5,
    "tilt":     +0.5,
    "dolly_in": +0.3,
    "dolly_out":+0.3,
    "zoom_in":  +0.2,
    "zoom_out": +0.2,
    "tracking": +0.8,
    "crane":    +1.0,
    "handheld": -0.2,
    "whip_pan": -0.5,
    "smear":    -0.3,
}

INTENT_MOD = {
    "action":         -0.5,
    "combat":         -0.8,
    "explosion":      -0.3,
    "running":        -0.4,
    "dramatic":       +0.5,
    "emotional":      +0.8,
    "introspective":  +1.2,
    "dialogue":       +1.0,
    "mystery":        +0.6,
    "comedy":         -0.2,
    "horror":         +0.4,
    "tension":        +0.3,
    "reveal":         +0.7,
    "death":          +1.5,
    "transformation": +1.0,
}

UNIVERSE_PACE = {
    "evangelion":   0.9,    # varié — lent introspectif / rapide combat
    "gundam":       1.0,
    "trigger":      0.85,   # rapide, énergie Trigger
    "shinkai":      1.15,   # contemplatif
    "shonen_battle":0.8,
    "slice_of_life":1.2,
    "generic":      1.0,
}

DURATION_MIN = 0.5
DURATION_MAX = 8.0
TARGET_FPS   = 24


# ══════════════════════════════════════════════════════════════════════════════
@dataclass
class ShotTiming:
    shot_id:         str
    shot_type:       str
    camera_movement: str
    acting_intent:   str
    duration_s:      float
    frame_count:     int
    transition_in:   str = "cut"
    transition_out:  str = "cut"
    notes:           str = ""


@dataclass
class PacingManifest:
    run_id:         str
    universe:       str
    total_duration: float
    fps:            int
    shots:          List[ShotTiming] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "run_id":         self.run_id,
            "universe":       self.universe,
            "total_duration": round(self.total_duration, 3),
            "fps":            self.fps,
            "shots":          [asdict(s) for s in self.shots],
        }


# ══════════════════════════════════════════════════════════════════════════════
class PacingEngine:
    """Calcule le timing optimal par shot et produit le manifeste de montage."""

    def __init__(self, universe: str = "generic", fps: int = TARGET_FPS):
        self.universe      = universe.lower()
        self.fps           = fps
        self.universe_mult = UNIVERSE_PACE.get(self.universe, 1.0)

    # ── Durée d'un shot ───────────────────────────────────────────────────────
    def get_recommended_duration(
        self,
        shot_type:        str,
        camera_movement:  str = "static",
        acting_intent:    str = "dramatic",
        n_words_dialogue: int = 0,
    ) -> float:
        """Retourne la durée recommandée en secondes."""
        base   = BASE_DURATION.get(shot_type.lower(), 2.5)
        mov    = MOVEMENT_MOD.get(camera_movement.lower(), 0.0)
        intent = INTENT_MOD.get(acting_intent.lower(), 0.0)
        dur    = (base + mov + intent) * self.universe_mult

        if n_words_dialogue > 0:
            dur = max(dur, n_words_dialogue * 0.25 + 0.5)

        return round(max(DURATION_MIN, min(DURATION_MAX, dur)), 2)

    # ── Transition recommandée ─────────────────────────────────────────────────
    @staticmethod
    def _recommend_transition(acting_intent: str, shot_type: str) -> str:
        if acting_intent in ("introspective", "emotional", "death", "dramatic"):
            return "dissolve"
        if acting_intent in ("mystery", "horror"):
            return "fade_black"
        if acting_intent in ("action", "combat", "explosion"):
            return "cut"
        if shot_type == "establishing":
            return "fade_in"
        return "cut"

    # ── Manifeste complet ──────────────────────────────────────────────────────
    def build_manifest(self, run_id: str, shots: list) -> PacingManifest:
        """
        Construit le manifeste depuis une liste de shots storyboard.
        Format shot (dict) :
          shot_id, shot_type, camera_movement, acting_intent,
          n_words (opt), duration_s (opt, forcé si présent)
        """
        manifest = PacingManifest(
            run_id=run_id, universe=self.universe,
            total_duration=0.0, fps=self.fps,
        )

        for i, shot in enumerate(shots):
            shot_id  = shot.get("shot_id",        f"S{i+1:02d}")
            stype    = shot.get("shot_type",       "medium_shot")
            movement = shot.get("camera_movement", "static")
            intent   = shot.get("acting_intent",   "dramatic")
            n_words  = shot.get("n_words",         0)
            forced   = shot.get("duration_s",      None)

            dur = (
                float(forced)
                if (forced and isinstance(forced, (int, float)) and forced > 0)
                else self.get_recommended_duration(stype, movement, intent, n_words)
            )

            frames     = max(1, round(dur * self.fps))
            trans_in   = self._recommend_transition(intent, stype)
            trans_out  = "cut" if i < len(shots) - 1 else "fade_black"

            manifest.shots.append(ShotTiming(
                shot_id=shot_id, shot_type=stype,
                camera_movement=movement, acting_intent=intent,
                duration_s=dur, frame_count=frames,
                transition_in=trans_in, transition_out=trans_out,
            ))
            manifest.total_duration += dur

        manifest.total_duration = round(manifest.total_duration, 3)
        log.info(
            f"Manifeste — {len(manifest.shots)} shots — "
            f"{manifest.total_duration:.1f}s"
        )
        return manifest

    # ── Sauvegarde ────────────────────────────────────────────────────────────
    def save_manifest(self, manifest: PacingManifest, output_dir: "str | Path") -> Path:
        out  = Path(output_dir)
        out.mkdir(parents=True, exist_ok=True)
        path = out / f"pacing_{manifest.run_id}.json"
        with open(path, "w", encoding="utf-8") as f:
            json.dump(manifest.to_dict(), f, indent=2, ensure_ascii=False)
        log.info(f"Manifeste → {path}")
        return path

    # ── Résumé console ────────────────────────────────────────────────────────
    @staticmethod
    def print_summary(manifest: PacingManifest) -> None:
        print(f"\n{'='*60}")
        print(f"  PACING — {manifest.run_id} | {manifest.universe} | {manifest.fps}fps")
        print(f"  Durée totale : {manifest.total_duration:.1f}s")
        print(f"{'='*60}")
        for s in manifest.shots:
            print(
                f"  {s.shot_id:6s} | {s.shot_type:20s} | "
                f"{s.duration_s:5.2f}s | {s.frame_count:3d}f | "
                f"{s.transition_in:12s}→ {s.transition_out}"
            )
        print(f"{'='*60}\n")


# ══════════════════════════════════════════════════════════════════════════════
# API module-level

def get_recommended_duration(
    shot_type:        str,
    camera_movement:  str = "static",
    acting_intent:    str = "dramatic",
    universe:         str = "generic",
    n_words_dialogue: int = 0,
) -> float:
    """Raccourci module-level — utilisé par storyboard.py."""
    return PacingEngine(universe=universe).get_recommended_duration(
        shot_type=shot_type,
        camera_movement=camera_movement,
        acting_intent=acting_intent,
        n_words_dialogue=n_words_dialogue,
    )


def build_manifest_from_storyboard(
    run_id:     str,
    storyboard: list,
    universe:   str = "generic",
    output_dir: "str | Path | None" = None,
) -> dict:
    """Point d'entrée pour postprod.py / maestro.py."""
    engine   = PacingEngine(universe=universe)
    manifest = engine.build_manifest(run_id=run_id, shots=storyboard)
    if output_dir:
        engine.save_manifest(manifest, output_dir)
    return manifest.to_dict()


# ══════════════════════════════════════════════════════════════════════════════
if __name__ == "__main__":
    import argparse, sys

    parser = argparse.ArgumentParser(description="Pacing Engine — Ov3rLoRd")
    parser.add_argument("--run-id",      required=True)
    parser.add_argument("--storyboard",  default="")
    parser.add_argument("--universe",    default="evangelion")
    parser.add_argument("--fps",         type=int, default=24)
    parser.add_argument("--output-dir",  default=str(config.WORKSPACE_DIR / "reports"))
    parser.add_argument("--shot-type",   default="")
    parser.add_argument("--movement",    default="static")
    parser.add_argument("--intent",      default="dramatic")
    args = parser.parse_args()

    if args.shot_type:
        dur = get_recommended_duration(
            shot_type=args.shot_type,
            camera_movement=args.movement,
            acting_intent=args.intent,
            universe=args.universe,
        )
        print(f"Durée recommandée : {dur}s")
        sys.exit(0)

    if args.storyboard and Path(args.storyboard).exists():
        with open(args.storyboard, "r", encoding="utf-8") as f:
            sb = json.load(f)
    else:
        sb = [
            {"shot_id":"S01","shot_type":"establishing",    "camera_movement":"pan",    "acting_intent":"dramatic"},
            {"shot_id":"S02","shot_type":"close_up",        "camera_movement":"static", "acting_intent":"emotional"},
            {"shot_id":"S03","shot_type":"extreme_close_up","camera_movement":"static", "acting_intent":"introspective"},
            {"shot_id":"S04","shot_type":"wide_shot",       "camera_movement":"dolly_in","acting_intent":"action"},
            {"shot_id":"S05","shot_type":"medium_shot",     "camera_movement":"static", "acting_intent":"dialogue","n_words":12},
            {"shot_id":"S06","shot_type":"close_up",        "camera_movement":"static", "acting_intent":"combat"},
            {"shot_id":"S07","shot_type":"insert",          "camera_movement":"static", "acting_intent":"action"},
            {"shot_id":"S08","shot_type":"medium_shot",     "camera_movement":"static", "acting_intent":"emotional"},
        ]

    engine   = PacingEngine(universe=args.universe, fps=args.fps)
    manifest = engine.build_manifest(run_id=args.run_id, shots=sb)
    engine.print_summary(manifest)
    engine.save_manifest(manifest, args.output_dir)

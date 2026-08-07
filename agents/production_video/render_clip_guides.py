"""Rendu par clip pour la sequence video 3 min (Priorite 1, tache_a_faire
2026-08-06 + regles annexe reprises dans la tache) : pour chaque ligne de
DEMO/frames/sequence_plan_20260806.csv (clip, vmd, shot_type, angle_deg,
duration_s), en un seul process Blender headless (pas de redemarrage par
clip) :

  1. Frame RGB previz -- sol reflechissant + eclairage 3 points
     (blender_previz.py::setup_decor_minimal/setup_three_point_lighting,
     patches 2026-08-06) -- a la camera EXACTE de ce clip : angle_deg fourni
     par le CSV (azimut) + elevation_deg varie par clip (rotation XYZ
     complete, jamais deux clips consecutifs a la meme elevation).
  2. Squelette OpenPose JSON + PNG projete a travers CETTE MEME camera
     (reutilise export_skeleton_openpose.py::project_bone_head /
     build_keypoint_array / resolve_mmd_lookup) -- guide ControlNet OpenPose
     coherent avec le cadrage du clip, meme pattern que la piste D validee
     (DOCS/MD/COMPARAISON_UNIFICATION_20260806.md).

Vitesse VMD adaptative (regle de session, video_pacing.py::classify_speed_from_deltas,
deja calibree 3 paliers x1/x2/x3 -- x1 si delta>5, x3 si delta<1, x2 sinon) :
calculee UNE FOIS par VMD importe (pas de reimport double), loggee par clip
et utilisee pour avancer la frame de pose choisie dans l'action (VMD reutilise
sur plusieurs clips du CSV -> varier la pose plutot que rendre toujours la
meme frame).

Sortie par clip (DEMO/frames/video_3min_guides/) :
    clip{NN}_rgb.png            -- previz RGB (sol reflechissant, 3 points)
    clip{NN}_openpose.json      -- keypoints BODY_25 + mains, projetes camera clip
    clip{NN}_openpose.png       -- meme squelette, dessine (entree ControlNet)
    clip_render_log.csv         -- angle/elevation/vmd_frame/speed_mult par clip

Usage :
    "C:\\Program Files\\Blender Foundation\\Blender 5.1\\blender.exe" -b -P ^
        agents/production_video/render_clip_guides.py -- ^
        --sequence-csv DEMO/frames/sequence_plan_20260806.csv ^
        --pmx "E:/Data Demo/_extracted/atrier_Rock Cat Miku_Ver.1.00/Tsatou_Rock Cat Miku_Ver.1.00.pmx" ^
        --out DEMO/frames/video_3min_guides --res 480 720 --fps 24
"""
import argparse
import csv
import json
import math
import os
import random
import sys

import bpy

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

from agents.production_video import blender_previz as bp
from agents.production_video import export_skeleton_openpose as eso
from agents.production_video.video_pacing import classify_speed_from_deltas


def to_windows_path(p):
    """CSV genere sur un shell POSIX-like (git bash) : "/e/Data Demo/..." ->
    "E:/Data Demo/...". Chemins deja Windows (contiennent ":") inchanges."""
    p = p.strip()
    if len(p) > 2 and p[0] == "/" and p[2] == "/" and p[1].isalpha():
        return f"{p[1].upper()}:{p[2:]}"
    return p


def parse_args():
    argv = sys.argv
    argv = argv[argv.index("--") + 1:] if "--" in argv else []
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--sequence-csv", required=True)
    p.add_argument("--pmx", required=True)
    p.add_argument("--out", required=True)
    p.add_argument("--res", type=int, nargs=2, default=[480, 720])
    p.add_argument("--samples", type=int, default=32)
    p.add_argument("--fps", type=float, default=24.0)
    p.add_argument("--seed", type=int, default=42, help="Determinisme du choix d'elevation caméra")
    p.add_argument("--limit", type=int, default=None, help="Limiter aux N premiers clips (tests)")
    return p.parse_args(argv)


def compute_speed_mult(armature):
    """Meme mesure que video_pacing.py::cmd_speed, sur l'action deja
    importee (evite un second import du meme VMD)."""
    action = armature.animation_data.action if armature.animation_data else None
    if action is None:
        return 1, 0.0
    frame_start, frame_end = int(action.frame_range[0]), int(action.frame_range[1])
    total_delta, n_samples = 0.0, 0
    prev_positions = {}
    scene = bpy.context.scene
    for f in range(frame_start, frame_end + 1):
        scene.frame_set(f)
        bpy.context.view_layer.update()
        for pb in armature.pose.bones:
            world_head = armature.matrix_world @ pb.head
            key = pb.name
            if key in prev_positions:
                total_delta += (world_head - prev_positions[key]).length
                n_samples += 1
            prev_positions[key] = world_head.copy()
    avg_delta = (total_delta / n_samples) if n_samples else 0.0
    return classify_speed_from_deltas(avg_delta), avg_delta


# Plage d'elevation (degres) gardant "corps entier visible en priorite
# absolue" (consigne) : evite les plongees/contre-plongees extremes qui
# coupent tete/pieds a radius/height calibres par shot_type.
ELEVATION_CHOICES = [-8.0, -3.0, 4.0, 10.0, 16.0, 22.0]


def pick_elevation(rng, prev_elevation):
    choices = [e for e in ELEVATION_CHOICES if e != prev_elevation]
    return rng.choice(choices)


def main():
    args = parse_args()
    args.out = os.path.abspath(args.out)
    os.makedirs(args.out, exist_ok=True)
    res = tuple(args.res)
    rng = random.Random(args.seed)

    with open(args.sequence_csv, encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    if args.limit:
        rows = rows[: args.limit]

    speed_cache = {}  # vmd path -> (speed_mult, avg_delta) ; VMD reutilises sur plusieurs clips
    log_rows = []
    prev_elevation = None

    for row in rows:
        clip_i = int(row["clip"])
        vmd_path = to_windows_path(row["vmd"])
        shot_type = row["shot_type"]
        angle_deg = float(row["angle_deg"])
        duration_s = float(row["duration_s"])

        bp.clear_scene()
        bp.setup_decor_minimal()
        armature = eso.import_mmd(args.pmx, [vmd_path])[0]
        bpy.context.view_layer.objects.active = armature

        if vmd_path not in speed_cache:
            speed_cache[vmd_path] = compute_speed_mult(armature)
        speed_mult, avg_delta = speed_cache[vmd_path]

        action = armature.animation_data.action if armature.animation_data else None
        f_start, f_end = (int(action.frame_range[0]), int(action.frame_range[1])) if action else (1, 1)
        span = max(1, f_end - f_start)
        # Vitesse adaptative appliquee au choix de pose : avance plus loin
        # dans l'action a chaque reutilisation du meme VMD, au rythme du
        # multiplicateur de vitesse (x1/x2/x3) -- pas une simple frame du milieu
        # repetee identique sur tous les clips qui partagent ce VMD.
        step = max(1, int(round(duration_s * args.fps * speed_mult / 4)))
        vmd_frame = f_start + ((clip_i * step) % span)
        bpy.context.scene.frame_set(vmd_frame)
        bpy.context.view_layer.update()

        target_loc = (0.0, 0.0, 0.0)
        bp.setup_three_point_lighting((0.0, 0.0, 1.2))
        elevation_deg = pick_elevation(rng, prev_elevation)
        prev_elevation = elevation_deg
        used_params = bp.setup_shot_camera(
            target_loc, shot_type, {"angle_deg": angle_deg, "elevation_deg": elevation_deg}
        )
        cam_obj = bpy.context.scene.camera

        rgb_path = os.path.join(args.out, f"clip{clip_i:02d}_rgb.png")
        bp.render_single_frame(rgb_path, res, args.samples)

        body_lookup, hand_lookup = eso.RESOLVERS["mmd"](armature)
        json_path = os.path.join(args.out, f"clip{clip_i:02d}_openpose.json")
        eso.export_frame(bpy.context.scene, cam_obj, armature, res, body_lookup, hand_lookup, json_path)

        log_rows.append({
            "clip": clip_i, "vmd": vmd_path, "shot_type": shot_type,
            "angle_deg": angle_deg, "elevation_deg": elevation_deg,
            "vmd_frame": vmd_frame, "speed_mult": speed_mult, "avg_delta": round(avg_delta, 4),
            "duration_s": duration_s, "rgb": rgb_path, "openpose_json": json_path,
        })
        print(f"RESULT clip {clip_i}/{len(rows)} OK -> {rgb_path} "
              f"(shot={shot_type} angle={angle_deg} elev={elevation_deg} speed_mult={speed_mult})", flush=True)

    log_path = os.path.join(args.out, "clip_render_log.csv")
    with open(log_path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(log_rows[0].keys()))
        w.writeheader()
        w.writerows(log_rows)
    print(f"RESULT: {len(log_rows)} clips rendus (RGB + OpenPose JSON) -> {args.out}")
    print(f"RESULT: log -> {log_path}")


if __name__ == "__main__":
    main()

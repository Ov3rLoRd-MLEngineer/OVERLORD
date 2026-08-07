"""Regles de rythme video (Priorite 2, ANNEXE_SESSION_CLAUDE_CODE_20260806.md) :

1. `classify_vmd_speed` (sous-commande `speed`, headless Blender) : detecte
   automatiquement le multiplicateur de vitesse d'anim (x1/x2/x3) a partir de
   l'amplitude moyenne des keyframes d'un VMD, en important via mmd_tools
   (coherent avec le reste du pipeline previz -- pas de parseur VMD maison).
   Seuil (regle de session) : delta position moyen/frame > 5 unites Blender
   -> x1 (deja rapide, ne pas accelerer) ; sinon x2 ; en-dessous d'un second
   seuil (quasi-statique/idle) -> x3.

2. `generate_shot_plan` (sous-commande `plan`, pur Python, pas de bpy) :
   genere une chaine `--shot-plan` compatible avec
   `agents/production_video/blender_previz.py --mode mmd` : jamais le meme
   type de plan ni le meme angle de camera sur deux clips consecutifs,
   couverture d'une rotation 360 degres etalee sur la sequence, corps entier
   privilegie (poids plus faible sur "closeup"/"closeup_wide").

Usage :
    py -3.12 agents/production_video/video_pacing.py plan --n-clips 12 --seed 1
    blender.exe -b -P agents/production_video/video_pacing.py -- speed \
        --vmd "E:/Data Demo/_extracted/.../Look at my muscle.vmd"
"""
import argparse
import random
import sys

# Meme jeu de plans que blender_previz.py::SHOT_TYPES -- garde ici en dur
# (pas d'import croise avec blender_previz.py, qui importe `bpy` au niveau
# module et casse hors process Blender ; `plan` doit pouvoir tourner en
# py -3.12 pur, sans Blender).
SHOT_TYPES = ("zoom_in", "zoom_out", "orbit", "closeup", "closeup_wide", "wide")
# Poids : corps entier priorise (consigne "corps entier visible en priorite
# absolue"), closeup limite a 1x/30s max par la consigne "zoom in sur visage
# 1 fois max par sequence de 30s" -- applique ici via poids faible plutot
# qu'un compteur strict (dataset de clips 2-5s, pas un minutage exact).
SHOT_WEIGHTS = {
    "wide": 3, "zoom_out": 2, "orbit": 3,
    "zoom_in": 2, "closeup": 1, "closeup_wide": 1,
}


def classify_speed_from_deltas(avg_delta, fast_threshold=5.0, idle_threshold=1.0):
    """avg_delta = delta de position moyen (unites Blender) par frame,
    moyenne sur tous les bones/frames de l'action. Regle de session :
    > fast_threshold -> x1 (deja rapide, ne pas accelerer) ; entre les deux
    seuils -> x2 ; < idle_threshold (quasi-statique/idle) -> x3."""
    if avg_delta > fast_threshold:
        return 1
    if avg_delta < idle_threshold:
        return 3
    return 2


def cmd_speed(args):
    import bpy
    import addon_utils

    bpy.ops.wm.read_factory_settings(use_empty=True)
    if not addon_utils.check("bl_ext.blender_org.mmd_tools")[1]:
        addon_utils.enable("bl_ext.blender_org.mmd_tools", default_set=True)
    if args.pmx:
        bpy.ops.mmd_tools.import_model(filepath=args.pmx, scale=0.08,
                                        types={'ARMATURE', 'DISPLAY'})
        armature = next(o for o in bpy.context.scene.objects if o.type == 'ARMATURE')
    else:
        # Sans PMX, importer le VMD seul requiert quand meme une armature
        # cible dans mmd_tools : on cree un rig minimal impossible ici --
        # --pmx est donc de facto requis, documente en argparse (required=False
        # pour permettre l'appel sans Blender sur `plan`, verifie explicitement
        # ici pour `speed`).
        raise SystemExit("cmd speed: --pmx est requis (mmd_tools a besoin d'une armature cible pour importer le VMD)")

    bpy.context.view_layer.objects.active = armature
    bpy.ops.mmd_tools.import_vmd(filepath=args.vmd, scale=1.0, margin=0, bone_mapper='PMX',
                                  use_pose_mode=False, use_mirror=False, update_scene_settings=True)
    action = armature.animation_data.action if armature.animation_data else None
    if action is None:
        print("RESULT speed_multiplier=1 (aucune action importee, defaut prudent)")
        return

    frame_start, frame_end = int(action.frame_range[0]), int(action.frame_range[1])
    total_delta, n_samples = 0.0, 0
    prev_positions = {}
    for f in range(frame_start, frame_end + 1):
        bpy.context.scene.frame_set(f)
        bpy.context.view_layer.update()
        for pb in armature.pose.bones:
            world_head = armature.matrix_world @ pb.head
            key = pb.name
            if key in prev_positions:
                delta = (world_head - prev_positions[key]).length
                total_delta += delta
                n_samples += 1
            prev_positions[key] = world_head.copy()

    avg_delta = (total_delta / n_samples) if n_samples else 0.0
    mult = classify_speed_from_deltas(avg_delta)
    print(f"RESULT avg_delta_per_frame={avg_delta:.4f} speed_multiplier={mult}")


def generate_shot_plan(n_clips, seed=None, angle_step_deg=None):
    """Retourne une chaine compatible `blender_previz.py --shot-plan`
    ("shot_type:angle_deg,shot_type:angle_deg,...").

    - Jamais le meme shot_type sur deux clips consecutifs.
    - Jamais le meme angle (a 1 degre pres) sur deux clips consecutifs, meme
      si le shot_type differe (consigne "jamais camera fixe sur plus d'un
      clip").
    - Angles etales pour couvrir une rotation 360 degres sur la sequence
      (angle de base = i * (360/n_clips), plus un jitter aleatoire pour
      eviter un pattern trop mecanique).
    """
    rng = random.Random(seed)
    if angle_step_deg is None:
        angle_step_deg = 360.0 / max(n_clips, 1)

    plan = []
    prev_type, prev_angle = None, None
    for i in range(n_clips):
        choices = [t for t in SHOT_TYPES if t != prev_type]
        weights = [SHOT_WEIGHTS[t] for t in choices]
        shot_type = rng.choices(choices, weights=weights, k=1)[0]

        base_angle = (i * angle_step_deg) % 360.0
        jitter = rng.uniform(-angle_step_deg * 0.25, angle_step_deg * 0.25)
        angle = round((base_angle + jitter) % 360.0, 1)
        if angle > 180.0:
            angle -= 360.0  # normalise en [-180, 180], convention setup_shot_camera
        if prev_angle is not None and abs(angle - prev_angle) < 5.0:
            angle = (angle + angle_step_deg / 2) % 360.0
            if angle > 180.0:
                angle -= 360.0

        plan.append(f"{shot_type}:{angle}")
        prev_type, prev_angle = shot_type, angle

    return ",".join(plan)


def cmd_plan(args):
    plan = generate_shot_plan(args.n_clips, seed=args.seed)
    print(plan)
    if args.csv_out:
        import csv
        with open(args.csv_out, "w", newline="", encoding="utf-8") as f:
            w = csv.writer(f)
            w.writerow(["clip", "shot_type", "angle_deg"])
            for i, item in enumerate(plan.split(","), start=1):
                st, ang = item.split(":")
                w.writerow([i, st, ang])
        print(f"RESULT: plan CSV -> {args.csv_out}")


def generate_sequence(vmd_paths, target_seconds=180.0, min_clip_s=2.0, max_clip_s=5.0,
                       max_clips=60, seed=None):
    """Planifie une sequence de clips visant `target_seconds` au total
    (Priorite 2, "Structure" : ~3 min, duree variable par clip, VMD jamais le
    meme deux fois de suite, plan de plans jamais fixe). Ne genere AUCUN
    pixel/frame -- c'est un plan (liste de dict) a consommer par la chaine de
    generation reelle (`DEMO/generate_svi_chain.py` ou equivalent), qui reste
    hors scope ici (deja lourde en calcul GPU, cf. HANDOFF_2026-08-06.md).
    """
    if not vmd_paths:
        raise ValueError("generate_sequence: liste de VMD vide")
    rng = random.Random(seed)

    clips = []
    total = 0.0
    prev_vmd = None
    prev_shot_type, prev_angle = None, None
    angle_step_deg = 24.0  # ~15 clips pour un tour complet, resserre naturellement sur une sequence plus longue
    i = 0
    while total < target_seconds and len(clips) < max_clips:
        vmd_choices = [v for v in vmd_paths if v != prev_vmd] or vmd_paths
        vmd = rng.choice(vmd_choices)

        choices = [t for t in SHOT_TYPES if t != prev_shot_type]
        weights = [SHOT_WEIGHTS[t] for t in choices]
        shot_type = rng.choices(choices, weights=weights, k=1)[0]
        base_angle = (i * angle_step_deg) % 360.0
        jitter = rng.uniform(-angle_step_deg * 0.25, angle_step_deg * 0.25)
        angle = round((base_angle + jitter) % 360.0, 1)
        if angle > 180.0:
            angle -= 360.0
        if prev_angle is not None and abs(angle - prev_angle) < 5.0:
            angle = (angle + angle_step_deg / 2) % 360.0
            if angle > 180.0:
                angle -= 360.0

        duration_s = round(rng.uniform(min_clip_s, max_clip_s), 2)
        clips.append({
            "clip": len(clips) + 1, "vmd": vmd, "shot_type": shot_type,
            "angle_deg": angle, "duration_s": duration_s,
        })
        total += duration_s
        prev_vmd, prev_shot_type, prev_angle = vmd, shot_type, angle
        i += 1

    return clips, total


def cmd_sequence(args):
    with open(args.vmd_list, encoding="utf-8") as f:
        vmd_paths = [line.strip() for line in f if line.strip()]
    clips, total = generate_sequence(vmd_paths, target_seconds=args.target_seconds,
                                      max_clips=args.max_clips, seed=args.seed)
    print(f"RESULT: {len(clips)} clips planifies, {total:.1f}s (cible {args.target_seconds}s)")
    if args.csv_out:
        import csv
        with open(args.csv_out, "w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=["clip", "vmd", "shot_type", "angle_deg", "duration_s"])
            w.writeheader()
            w.writerows(clips)
        print(f"RESULT: sequence CSV -> {args.csv_out}")


def main():
    argv = sys.argv
    argv = argv[argv.index("--") + 1:] if "--" in argv else argv[1:]

    p = argparse.ArgumentParser(description=__doc__)
    sub = p.add_subparsers(dest="cmd", required=True)

    p_speed = sub.add_parser("speed", help="Classification vitesse VMD (necessite Blender/bpy)")
    p_speed.add_argument("--vmd", required=True)
    p_speed.add_argument("--pmx", required=True, help="PMX cible (mmd_tools requiert une armature pour importer le VMD)")

    p_plan = sub.add_parser("plan", help="Generation d'un plan de plans camera (pur Python)")
    p_plan.add_argument("--n-clips", type=int, default=12)
    p_plan.add_argument("--seed", type=int, default=None)
    p_plan.add_argument("--csv-out", default=None)

    p_seq = sub.add_parser("sequence", help="Planification sequence ~3min (pur Python, pas de generation reelle)")
    p_seq.add_argument("--vmd-list", required=True, help="Fichier texte, un chemin VMD par ligne (camera exclues)")
    p_seq.add_argument("--target-seconds", type=float, default=180.0)
    p_seq.add_argument("--max-clips", type=int, default=60)
    p_seq.add_argument("--seed", type=int, default=None)
    p_seq.add_argument("--csv-out", default=None)

    args = p.parse_args(argv)
    if args.cmd == "speed":
        cmd_speed(args)
    elif args.cmd == "plan":
        cmd_plan(args)
    else:
        cmd_sequence(args)


if __name__ == "__main__":
    main()

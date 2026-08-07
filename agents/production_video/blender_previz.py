"""Previz 3D headless Blender : camera animee, rendu EEVEE.

Deux modes :
- `duo` (Workflow B, historique) : 2 personnages gltf/fbx, camera en dolly
  simple sur `--frames` frames continues.
- `mmd` (Workflow A / demo 30s Miku) : 1 personnage PMX + motion VMD
  (mmd_tools), camera scriptee par plan de plans ("shot plan") avec un type
  de mouvement par clip SVI en aval (zoom_in/zoom_out/orbit/closeup/wide).
  Ne rend qu'une frame representative par clip (previz de reference/
  documentation des parametres camera, pas d'injection pixel dans la chaine
  SVI qui reste ancree sur la derniere frame du clip precedent, cf. CLAUDE.md).

Sortie = frames RGB (beauty) uniquement. Depth/pose ne sont PAS extraits ici
(l'API compositeur Blender 5.1 est cassee, cf. CLAUDE.md) : passer les
frames RGB rendues a `DepthAnythingV2Preprocessor` + DWPose (ComfyUI) en
aval, comme le reste du pipeline video.

Usage duo (headless, depuis la racine du depot) :
    blender.exe -b -P agents/production_video/blender_previz.py -- \
        --char1 "E:/Data Demo/FighterZ_extracted/Chara/GKS/Costume01/Mesh/GKS_body.gltf" \
        --char2 "E:/Data Demo/FighterZ_extracted/Chara/VGN/Costume01/Mesh/VGN_body.gltf" \
        --out DEMO/frames/previz_blender --frames 48 --res 1024 1536

Usage mmd (shot plan documentaire, 1 frame/clip) :
    blender.exe -b -P agents/production_video/blender_previz.py -- \
        --mode mmd \
        --pmx "E:/Data Demo/_extracted/atrier_Tsatou..._ver.1.00/Tsatou..._ver.1.00.pmx" \
        --vmd "E:/Data Demo/_extracted/.../Look at my muscle.vmd" \
        --shot-plan zoom_in,zoom_in,zoom_out,orbit,orbit,closeup,closeup_wide \
        --out DEMO/frames/previz_shots --res 768 1152 --samples 16
"""
import argparse
import csv
import math
import os
import sys

import bpy

SHOT_TYPES = ("zoom_in", "zoom_out", "orbit", "closeup", "closeup_wide", "wide")


def parse_args():
    argv = sys.argv
    if "--" in argv:
        argv = argv[argv.index("--") + 1:]
    else:
        argv = []
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--mode", choices=["duo", "mmd"], default="duo")
    p.add_argument("--char1", help="[duo] Chemin du personnage 1 (.gltf/.glb/.fbx)")
    p.add_argument("--char2", help="[duo] Chemin du personnage 2 (.gltf/.glb/.fbx)")
    p.add_argument("--pmx", help="[mmd] Chemin du modele PMX")
    p.add_argument("--vmd", action="append", default=[], help="[mmd] Chemin VMD (repetable, applique en sequence)")
    p.add_argument("--vmd-frame", type=int, default=None, help="[mmd] Frame VMD a previsualiser (defaut: milieu de l'action importee)")
    p.add_argument("--shot-plan", default=None, help="[mmd] Liste de shots separes par des virgules, un par clip (voir SHOT_TYPES)")
    p.add_argument("--shot-csv-out", default=None, help="[mmd] Chemin CSV optionnel pour logger les parametres camera par clip")
    p.add_argument("--out", default="DEMO/frames/previz_blender", help="Dossier de sortie des frames")
    p.add_argument("--frames", type=int, default=48, help="[duo] Nombre de frames de la camera animee")
    p.add_argument("--res", type=int, nargs=2, default=[1024, 1536], help="Resolution (largeur hauteur)")
    p.add_argument("--samples", type=int, default=32, help="Samples EEVEE")
    p.add_argument("--hdri", default=None, help="Chemin optionnel d'un HDRI Poly Haven pour le decor (sinon degrade uni)")
    return p.parse_args(argv)


def clear_scene():
    bpy.ops.wm.read_factory_settings(use_empty=True)


def import_character(filepath, location, rotation_z_deg):
    ext = os.path.splitext(filepath)[1].lower()
    before = set(bpy.data.objects.keys())
    if ext in (".gltf", ".glb"):
        bpy.ops.import_scene.gltf(filepath=filepath)
    elif ext == ".fbx":
        bpy.ops.import_scene.fbx(filepath=filepath)
    else:
        raise ValueError(f"Format de personnage non supporte: {ext} ({filepath})")
    new_objs = [bpy.data.objects[n] for n in bpy.data.objects.keys() if n not in before]
    # L'import cree souvent plusieurs objets (armature + mesh(es)) ; on
    # regroupe sous un Empty pour positionner/orienter le personnage en bloc.
    anchor = bpy.data.objects.new(f"anchor_{os.path.basename(filepath)}", None)
    bpy.context.scene.collection.objects.link(anchor)
    anchor.location = location
    anchor.rotation_euler = (0, 0, math.radians(rotation_z_deg))
    for obj in new_objs:
        if obj.parent is None:
            obj.parent = anchor
    return anchor, new_objs


def import_mmd_character(pmx_path, vmd_paths, preview_frame=None):
    """Importe un modele PMX + une ou plusieurs motions VMD via mmd_tools
    (addon deja installe/valide session TEST_WORKFLOW_A). Retourne l'objet
    Armature et la frame VMD choisie pour le previz (milieu de l'action si
    non precisee explicitement)."""
    import addon_utils
    # `wm.read_factory_settings` (clear_scene) reinitialise aussi les preferences
    # utilisateur (use_userdef=True par defaut) et desactive donc l'extension
    # mmd_tools a chaque appel : la reactiver explicitement avant import.
    if not addon_utils.check("bl_ext.blender_org.mmd_tools")[1]:
        addon_utils.enable("bl_ext.blender_org.mmd_tools", default_set=True)

    # scale=0.08 = convention mmd_tools standard (1 unite MMD ~= 8cm) ; a 1.0
    # le modele sort ~12x trop grand (verifie : camera a portee "buste"
    # normale ne cadrait que les pieds).
    bpy.ops.mmd_tools.import_model(filepath=pmx_path, scale=0.08, types={'MESH', 'ARMATURE', 'PHYSICS', 'DISPLAY', 'MORPHS'})

    armature = next((o for o in bpy.context.scene.objects if o.type == 'ARMATURE'), None)
    if armature is None:
        raise RuntimeError(f"Aucune armature trouvee apres import PMX: {pmx_path}")

    bpy.context.view_layer.objects.active = armature
    armature.select_set(True)

    frame_end = 1
    for vmd_path in vmd_paths:
        bpy.ops.mmd_tools.import_vmd(
            filepath=vmd_path,
            scale=1.0,
            margin=0,
            bone_mapper='PMX',
            use_pose_mode=False,
            use_mirror=False,
            update_scene_settings=True,
        )
        if armature.animation_data and armature.animation_data.action:
            frame_end = max(frame_end, int(armature.animation_data.action.frame_range[1]))

    chosen_frame = preview_frame if preview_frame is not None else max(1, frame_end // 2)
    return armature, chosen_frame


def setup_shot_camera(target_location, shot_type, params=None):
    """Positionne (sans keyframe, previz = 1 frame fixe) la camera pour un
    type de plan donne. `params` permet de surcharger radius/angle/height
    par defaut. Retourne le dict des parametres reellement utilises (pour
    documentation/log)."""
    if shot_type not in SHOT_TYPES:
        raise ValueError(f"shot_type inconnu: {shot_type} (attendu: {SHOT_TYPES})")
    params = dict(params or {})
    tx, ty, tz = target_location

    # Reglages calibres visuellement sur Miku (mmd_tools scale=0.08, hauteur
    # totale ~1.4-1.5 Blender units, racine ~pieds) : radius/target_z/height
    # ajustes apres inspection d'un rendu "wide" trop large/flottant.
    defaults = {
        "zoom_in": dict(radius=3.5, angle_deg=0.0, elevation_deg=0.0, height=1.0, target_z=0.9, fov_deg=40.0),
        "zoom_out": dict(radius=5.5, angle_deg=10.0, elevation_deg=0.0, height=1.1, target_z=0.9, fov_deg=45.0),
        "orbit": dict(radius=3.8, angle_deg=75.0, elevation_deg=0.0, height=1.0, target_z=0.9, fov_deg=40.0),
        "closeup": dict(radius=1.0, angle_deg=15.0, elevation_deg=0.0, height=1.4, target_z=1.45, fov_deg=30.0),
        "closeup_wide": dict(radius=1.0, angle_deg=15.0, elevation_deg=0.0, height=1.4, target_z=1.45, fov_deg=30.0),
        "wide": dict(radius=5.0, angle_deg=0.0, elevation_deg=0.0, height=1.0, target_z=0.8, fov_deg=45.0),
    }
    p = defaults[shot_type]
    p.update(params)

    cam_data = bpy.data.cameras.new(f"cam_{shot_type}")
    cam_data.lens_unit = 'FOV'
    cam_data.angle = math.radians(p["fov_deg"])
    cam_obj = bpy.data.objects.new(f"cam_{shot_type}", cam_data)
    bpy.context.scene.collection.objects.link(cam_obj)
    bpy.context.scene.camera = cam_obj

    look_target_loc = (tx, ty, tz + p["target_z"])
    target = bpy.data.objects.new(f"cam_target_{shot_type}", None)
    target.location = look_target_loc
    bpy.context.scene.collection.objects.link(target)

    constraint = cam_obj.constraints.new(type='TRACK_TO')
    constraint.target = target
    constraint.track_axis = 'TRACK_NEGATIVE_Z'
    constraint.up_axis = 'UP_Y'

    # Rotation XYZ complete (consigne priorite 1, tache_a_faire 2026-08-06) :
    # angle_deg = azimut autour de Z (comme avant), elevation_deg = inclinaison
    # verticale de la camera sur son arc (orbite spherique, pas juste un
    # pivot plat) -- reste additif a `height` pour ne pas casser les reglages
    # par shot_type deja calibres visuellement.
    angle = math.radians(p["angle_deg"])
    elevation = math.radians(p["elevation_deg"])
    horiz_radius = p["radius"] * math.cos(elevation)
    cam_obj.location = (
        tx + horiz_radius * math.sin(angle),
        ty - horiz_radius * math.cos(angle),
        tz + p["height"] + p["radius"] * math.sin(elevation),
    )
    return p


def setup_decor_minimal(hdri_path=None):
    """Decor minimal : sol + fond. Poly Haven HDRI en option (--hdri) sinon
    degrade uni neutre, suffisant pour un rendu de previz (le style anime
    final vient de l'etage SDXL/AniSora en aval, pas de ce rendu 3D)."""
    bpy.ops.mesh.primitive_plane_add(size=40, location=(0, 0, 0))
    ground = bpy.context.active_object
    ground.name = "ground_minimal"
    mat = bpy.data.materials.new("ground_mat")
    mat.diffuse_color = (0.5, 0.5, 0.52, 1.0)
    # Sol reflechissant (consigne priorite 1, tache_a_faire 2026-08-06) :
    # roughness basse sur le Principled BSDF pour des reflets nets sous le
    # personnage, combinee au raytracing EEVEE Next active dans
    # render_frames/render_single_frame (sinon aucune reflexion visible meme
    # a roughness=0).
    mat.use_nodes = True
    bsdf = mat.node_tree.nodes.get("Principled BSDF")
    if bsdf is not None:
        bsdf.inputs["Base Color"].default_value = (0.5, 0.5, 0.52, 1.0)
        bsdf.inputs["Roughness"].default_value = 0.12
        if "IOR" in bsdf.inputs:
            bsdf.inputs["IOR"].default_value = 1.5
    ground.data.materials.append(mat)

    world = bpy.context.scene.world or bpy.data.worlds.new("World")
    bpy.context.scene.world = world
    world.use_nodes = True
    bg = world.node_tree.nodes.get("Background")
    if hdri_path and os.path.exists(hdri_path):
        env_tex = world.node_tree.nodes.new("ShaderNodeTexEnvironment")
        env_tex.image = bpy.data.images.load(hdri_path)
        world.node_tree.links.new(env_tex.outputs["Color"], bg.inputs["Color"])
    else:
        bg.inputs["Color"].default_value = (0.65, 0.68, 0.72, 1.0)
        bg.inputs["Strength"].default_value = 1.0


def setup_three_point_lighting(target_location):
    tx, ty, tz = target_location
    specs = [
        ("key_light", (tx + 3.0, ty - 4.0, tz + 4.0), 1200.0, (1.0, 0.97, 0.92)),
        ("fill_light", (tx - 4.0, ty - 2.0, tz + 2.5), 400.0, (0.85, 0.9, 1.0)),
        ("rim_light", (tx + 0.5, ty + 4.5, tz + 3.0), 600.0, (1.0, 1.0, 1.0)),
    ]
    for name, loc, power, color in specs:
        light_data = bpy.data.lights.new(name=name, type='AREA')
        light_data.energy = power
        light_data.color = color
        light_data.size = 2.0
        light_obj = bpy.data.objects.new(name, light_data)
        light_obj.location = loc
        bpy.context.scene.collection.objects.link(light_obj)
        # Oriente la lumiere vers la cible (look-at simplifie).
        direction = (tx - loc[0], ty - loc[1], tz - loc[2])
        light_obj.rotation_euler = (
            math.atan2(math.sqrt(direction[0] ** 2 + direction[1] ** 2), direction[2]),
            0.0,
            math.atan2(direction[1], direction[0]) + math.pi / 2,
        )


def setup_animated_camera(target_location, n_frames, radius_start=8.0, radius_end=5.0, height=2.2):
    cam_data = bpy.data.cameras.new("previz_cam")
    cam_obj = bpy.data.objects.new("previz_cam", cam_data)
    bpy.context.scene.collection.objects.link(cam_obj)
    bpy.context.scene.camera = cam_obj

    target = bpy.data.objects.new("cam_target", None)
    target.location = target_location
    bpy.context.scene.collection.objects.link(target)

    constraint = cam_obj.constraints.new(type='TRACK_TO')
    constraint.target = target
    constraint.track_axis = 'TRACK_NEGATIVE_Z'
    constraint.up_axis = 'UP_Y'

    tx, ty, tz = target_location
    angle_start_deg, angle_end_deg = -35.0, 35.0
    for i in range(n_frames):
        t = i / max(n_frames - 1, 1)
        angle = math.radians(angle_start_deg + t * (angle_end_deg - angle_start_deg))
        radius = radius_start + t * (radius_end - radius_start)
        cam_obj.location = (
            tx + radius * math.sin(angle),
            ty - radius * math.cos(angle),
            tz + height,
        )
        cam_obj.keyframe_insert(data_path="location", frame=i + 1)
    # Interpolation BEZIER par defaut a l'insertion de keyframe (suffisant
    # pour un dolly de previz). L'API des F-curves a change en Blender
    # 5.x (action layers/slots) ; pas besoin d'y toucher ici.
    return cam_obj


def render_frames(out_dir, n_frames, resolution, samples):
    scene = bpy.context.scene
    scene.render.engine = 'BLENDER_EEVEE_NEXT' if 'BLENDER_EEVEE_NEXT' in [
        e.identifier for e in bpy.types.RenderSettings.bl_rna.properties['engine'].enum_items
    ] else 'BLENDER_EEVEE'
    scene.render.resolution_x, scene.render.resolution_y = resolution
    scene.render.image_settings.file_format = 'PNG'
    try:
        scene.eevee.taa_render_samples = samples
    except AttributeError:
        pass
    try:
        scene.eevee.use_raytracing = True  # sol reflechissant : sans ceci, roughness basse seule ne reflete rien en EEVEE Next
    except AttributeError:
        pass
    scene.frame_start = 1
    scene.frame_end = n_frames

    os.makedirs(out_dir, exist_ok=True)
    for f in range(1, n_frames + 1):
        scene.frame_set(f)
        scene.render.filepath = os.path.join(out_dir, f"previz_{f:04d}.png")
        bpy.ops.render.render(write_still=True)
    return n_frames


def render_single_frame(out_path, resolution, samples, vmd_frame=None):
    scene = bpy.context.scene
    scene.render.engine = 'BLENDER_EEVEE_NEXT' if 'BLENDER_EEVEE_NEXT' in [
        e.identifier for e in bpy.types.RenderSettings.bl_rna.properties['engine'].enum_items
    ] else 'BLENDER_EEVEE'
    scene.render.resolution_x, scene.render.resolution_y = resolution
    scene.render.image_settings.file_format = 'PNG'
    try:
        scene.eevee.taa_render_samples = samples
    except AttributeError:
        pass
    try:
        scene.eevee.use_raytracing = True  # sol reflechissant : sans ceci, roughness basse seule ne reflete rien en EEVEE Next
    except AttributeError:
        pass
    if vmd_frame is not None:
        scene.frame_set(vmd_frame)
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    scene.render.filepath = out_path
    bpy.ops.render.render(write_still=True)


def run_mmd_shot_plan(args):
    if not args.pmx or not args.vmd or not args.shot_plan:
        raise ValueError("mode mmd requiert --pmx, --vmd (>=1) et --shot-plan")

    # Sans .blend charge (factory/empty settings), Blender resout les chemins
    # relatifs par rapport a un repertoire par defaut (pas le cwd du process
    # Python) : forcer l'absolu pour eviter une ecriture hors depot (constate:
    # atterrissage sous C:\ au lieu de D:\OVERLORD\...).
    args.out = os.path.abspath(args.out)
    if args.shot_csv_out:
        args.shot_csv_out = os.path.abspath(args.shot_csv_out)

    # Syntaxe par item : "shot_type" ou "shot_type:angle_deg" (surcharge
    # explicite de l'angle pour varier la prise de vue entre deux clips du
    # meme type, cf. consigne "pas de camera fixe sur 30 secondes").
    shots = []
    for raw in args.shot_plan.split(","):
        raw = raw.strip()
        if not raw:
            continue
        if ":" in raw:
            st, angle = raw.split(":", 1)
            shots.append((st.strip(), float(angle)))
        else:
            shots.append((raw, None))
    os.makedirs(args.out, exist_ok=True)

    log_rows = []
    for i, (shot_type, angle_override) in enumerate(shots, start=1):
        clear_scene()
        setup_decor_minimal(args.hdri)
        armature, vmd_frame = import_mmd_character(args.pmx, args.vmd, preview_frame=args.vmd_frame)

        # Hauteur du perso approx (mmd_tools importe en metres, racine au sol).
        target_loc = (0.0, 0.0, 0.0)
        setup_three_point_lighting((0.0, 0.0, 1.2))
        overrides = {"angle_deg": angle_override} if angle_override is not None else {}
        used_params = setup_shot_camera(target_loc, shot_type, overrides)

        out_path = os.path.join(args.out, f"previz_clip{i:02d}_{shot_type}.png")
        render_single_frame(out_path, tuple(args.res), args.samples, vmd_frame=vmd_frame)

        row = {"clip": i, "shot_type": shot_type, "vmd_frame": vmd_frame, "file": out_path}
        row.update(used_params)
        log_rows.append(row)
        print(f"RESULT clip {i}: shot={shot_type} vmd_frame={vmd_frame} -> {out_path}")

    if args.shot_csv_out:
        os.makedirs(os.path.dirname(args.shot_csv_out) or ".", exist_ok=True)
        fieldnames = ["clip", "shot_type", "vmd_frame", "file", "radius", "angle_deg", "height", "target_z", "fov_deg"]
        with open(args.shot_csv_out, "w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=fieldnames)
            w.writeheader()
            w.writerows(log_rows)
        print(f"RESULT: shot plan CSV -> {os.path.abspath(args.shot_csv_out)}")

    print(f"RESULT: {len(shots)} frames de previz (1/clip) rendues dans {os.path.abspath(args.out)}")


def run_duo(args):
    args.out = os.path.abspath(args.out)
    clear_scene()
    setup_decor_minimal(args.hdri)

    char1_loc = (-1.2, 0.0, 0.0)
    char2_loc = (1.2, 0.0, 0.0)
    import_character(args.char1, char1_loc, rotation_z_deg=25)
    import_character(args.char2, char2_loc, rotation_z_deg=-155)

    midpoint = (0.0, 0.0, 1.0)
    setup_three_point_lighting(midpoint)
    setup_animated_camera(midpoint, args.frames)

    n = render_frames(args.out, args.frames, tuple(args.res), args.samples)
    print(f"RESULT: {n} frames de previz rendues (EEVEE) dans {os.path.abspath(args.out)}")


def main():
    args = parse_args()
    if args.mode == "mmd":
        run_mmd_shot_plan(args)
    else:
        run_duo(args)


if __name__ == "__main__":
    main()

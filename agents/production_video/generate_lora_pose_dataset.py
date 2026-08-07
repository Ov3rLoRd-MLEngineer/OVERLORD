"""Genere un dataset de poses de reference pour entrainement LoRA personnage
(Priorite 4, ANNEXE_SESSION_CLAUDE_CODE_20260806.md) : rendu Blender EEVEE
headless, PAS de generation SDXL -- juste les images de reference posees
(T-pose/A-pose/8 angles x 2 fonds), a passer ensuite dans la chaine
ComfyUI/SDXL en aval si besoin. N'entraine RIEN (consigne explicite).

10 configurations de plan (8 angles sur A-pose + 1 T-pose face + 1 A-pose
face dediee) x 2 fonds (blanc pur / gris neutre) = 20 images minimum par
tenue, cf. "Regles tenues multiples (LoRA dataset)" de l'annexe de session.

Reutilise l'import mmd_tools de blender_previz.py/export_skeleton_openpose.py
pour rester coherent avec le reste du pipeline previz.

Usage (depuis la racine du depot, personnage mmd) :
    blender.exe -b -P agents/production_video/generate_lora_pose_dataset.py -- \
        --skel-type mmd \
        --pmx "E:/Data Demo/_extracted/atrier_Rock Cat Miku_Ver.1.00/Tsatou_Rock Cat Miku_Ver.1.00.pmx" \
        --out DEMO/lora_dataset/mmd/miku/casual \
        --res 1024 1024 --samples 32
"""
import argparse
import math
import os
import sys

import bpy

ANGLES_DEG = {
    "face": 0.0, "dos": 180.0,
    "profil_G": -90.0, "profil_D": 90.0,
    "34_face_G": -45.0, "34_face_D": 45.0,
    "plongee": 0.0, "contre_plongee": 0.0,
}
# plongee/contre_plongee varient la hauteur/inclinaison camera plutot que
# l'angle horizontal (vue de face en hauteur, coherent avec la definition
# usuelle "high angle"/"low angle").
CAMERA_PITCH = {"plongee": 25.0, "contre_plongee": -20.0}

BACKGROUNDS = {
    "blanc": (1.0, 1.0, 1.0, 1.0),
    "gris": (0.55, 0.55, 0.55, 1.0),
}

# Bones bras haut mmd (Semi-Standard, verifie DEMO/_bone_dump.txt) pour poser
# l'A-pose proceduralement depuis la bind pose (T-pose PMX standard).
MMD_UPARM_BONES = {"L": "\u8155.L", "R": "\u8155.R"}  # 腕.L / 腕.R


def parse_args():
    argv = sys.argv
    argv = argv[argv.index("--") + 1:] if "--" in argv else []
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--skel-type", required=True, choices=["mmd", "ue4"])
    p.add_argument("--pmx", help="[mmd] Chemin PMX")
    p.add_argument("--fbx", help="[ue4] Chemin FBX/glTF rigge")
    p.add_argument("--out", required=True)
    p.add_argument("--res", type=int, nargs=2, default=[1024, 1024])
    p.add_argument("--samples", type=int, default=32)
    return p.parse_args(argv)


def clear_scene():
    bpy.ops.wm.read_factory_settings(use_empty=True)


def import_mmd(pmx_path):
    import addon_utils
    if not addon_utils.check("bl_ext.blender_org.mmd_tools")[1]:
        addon_utils.enable("bl_ext.blender_org.mmd_tools", default_set=True)
    bpy.ops.mmd_tools.import_model(filepath=pmx_path, scale=0.08,
                                    types={'MESH', 'ARMATURE', 'PHYSICS', 'DISPLAY', 'MORPHS'})
    armature = next(o for o in bpy.context.scene.objects if o.type == 'ARMATURE')
    return armature


def import_rigged(path):
    ext = os.path.splitext(path)[1].lower()
    before = set(bpy.data.objects.keys())
    if ext in (".gltf", ".glb"):
        bpy.ops.import_scene.gltf(filepath=path)
    else:
        bpy.ops.import_scene.fbx(filepath=path)
    new_objs = [bpy.data.objects[n] for n in bpy.data.objects.keys() if n not in before]
    return next(o for o in new_objs if o.type == 'ARMATURE')


def apply_a_pose_mmd(armature):
    """Abaisse les bras d'environ 45 degres depuis la T-pose bind (rotation
    locale Z du bone 腕, convention mmd bras aligne sur X a la bind pose)."""
    bpy.context.view_layer.objects.active = armature
    bpy.ops.object.mode_set(mode='POSE')
    for side, bone_name in MMD_UPARM_BONES.items():
        pb = armature.pose.bones.get(bone_name)
        if pb is None:
            continue
        angle = math.radians(45.0 if side == "L" else -45.0)
        pb.rotation_mode = 'XYZ'
        pb.rotation_euler[2] = angle
    bpy.ops.object.mode_set(mode='OBJECT')


def reset_pose(armature):
    bpy.context.view_layer.objects.active = armature
    bpy.ops.object.mode_set(mode='POSE')
    for pb in armature.pose.bones:
        pb.rotation_quaternion = (1, 0, 0, 0)
        pb.rotation_euler = (0, 0, 0)
        pb.location = (0, 0, 0)
    bpy.ops.object.mode_set(mode='OBJECT')


def bbox_and_center(armature):
    bpy.context.view_layer.update()
    coords = [armature.matrix_world @ pb.head for pb in armature.pose.bones]
    xs, ys, zs = zip(*[(c.x, c.y, c.z) for c in coords])
    return (min(xs), max(xs)), (min(ys), max(ys)), (min(zs), max(zs))


def setup_camera(armature, angle_deg, pitch_deg=0.0):
    (xmin, xmax), (ymin, ymax), (zmin, zmax) = bbox_and_center(armature)
    cx, cy, cz = (xmin + xmax) / 2, (ymin + ymax) / 2, (zmin + zmax) / 2
    height = (zmax - zmin) or 1.0
    radius = height * 1.6

    for obj in list(bpy.data.objects):
        if obj.type == 'CAMERA':
            bpy.data.objects.remove(obj, do_unlink=True)

    cam_data = bpy.data.cameras.new("pose_cam")
    cam_data.lens_unit = 'FOV'
    cam_data.angle = math.radians(40.0)
    cam_obj = bpy.data.objects.new("pose_cam", cam_data)
    bpy.context.scene.collection.objects.link(cam_obj)
    bpy.context.scene.camera = cam_obj

    az = math.radians(angle_deg)
    pitch = math.radians(pitch_deg)
    cam_obj.location = (
        cx + radius * math.sin(az) * math.cos(pitch),
        cy - radius * math.cos(az) * math.cos(pitch),
        cz + height * 0.5 + radius * math.sin(pitch),
    )
    target = bpy.data.objects.new("pose_cam_target", None)
    target.location = (cx, cy, cz + height * 0.1)
    bpy.context.scene.collection.objects.link(target)
    constraint = cam_obj.constraints.new(type='TRACK_TO')
    constraint.target = target
    constraint.track_axis = 'TRACK_NEGATIVE_Z'
    constraint.up_axis = 'UP_Y'
    bpy.context.view_layer.update()
    return cam_obj


def setup_lighting_and_bg(bg_rgba):
    for obj in list(bpy.data.objects):
        if obj.type == 'LIGHT':
            bpy.data.objects.remove(obj, do_unlink=True)
    specs = [
        ("key", (3.0, -4.0, 4.0), 1200.0),
        ("fill", (-4.0, -2.0, 2.5), 400.0),
        ("rim", (0.5, 4.5, 3.0), 600.0),
    ]
    for name, loc, power in specs:
        light_data = bpy.data.lights.new(name=f"light_{name}", type='AREA')
        light_data.energy = power
        light_data.size = 2.0
        light_obj = bpy.data.objects.new(f"light_{name}", light_data)
        light_obj.location = loc
        bpy.context.scene.collection.objects.link(light_obj)

    world = bpy.context.scene.world or bpy.data.worlds.new("World")
    bpy.context.scene.world = world
    world.use_nodes = True
    bg = world.node_tree.nodes.get("Background")
    bg.inputs["Color"].default_value = bg_rgba
    bg.inputs["Strength"].default_value = 1.0


def render(out_path, res, samples):
    scene = bpy.context.scene
    scene.render.engine = 'BLENDER_EEVEE_NEXT' if 'BLENDER_EEVEE_NEXT' in [
        e.identifier for e in bpy.types.RenderSettings.bl_rna.properties['engine'].enum_items
    ] else 'BLENDER_EEVEE'
    scene.render.resolution_x, scene.render.resolution_y = res
    scene.render.image_settings.file_format = 'PNG'
    scene.render.film_transparent = False
    try:
        scene.eevee.taa_render_samples = samples
    except AttributeError:
        pass
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    scene.render.filepath = out_path
    bpy.ops.render.render(write_still=True)


def main():
    args = parse_args()
    args.out = os.path.abspath(args.out)
    clear_scene()

    if args.skel_type == "mmd":
        if not args.pmx:
            raise ValueError("--skel-type mmd requiert --pmx")
        armature = import_mmd(args.pmx)
        has_a_pose = True
    else:
        if not args.fbx:
            raise ValueError("--skel-type ue4 requiert --fbx")
        armature = import_rigged(args.fbx)
        has_a_pose = False  # pas de mapping bras generique fiable hors mmd

    n_rendered = 0
    for bg_name, bg_rgba in BACKGROUNDS.items():
        setup_lighting_and_bg(bg_rgba)

        # 8 angles, sur A-pose si disponible (silhouette plus lisible),
        # sinon bind pose telle quelle.
        if has_a_pose:
            apply_a_pose_mmd(armature)
        for angle_name, angle_deg in ANGLES_DEG.items():
            pitch = CAMERA_PITCH.get(angle_name, 0.0)
            cam = setup_camera(armature, angle_deg, pitch)
            out_path = os.path.join(args.out, bg_name, f"angle_{angle_name}.png")
            render(out_path, tuple(args.res), args.samples)
            n_rendered += 1
            print(f"RESULT: {out_path}")

        # T-pose face dediee (bind pose brute, reference neutre obligatoire).
        reset_pose(armature)
        cam = setup_camera(armature, 0.0, 0.0)
        out_path = os.path.join(args.out, bg_name, "tpose_face.png")
        render(out_path, tuple(args.res), args.samples)
        n_rendered += 1
        print(f"RESULT: {out_path}")

        # A-pose face dediee (si disponible -- sinon meme bind pose,
        # documente comme tel plutot que de dupliquer silencieusement).
        if has_a_pose:
            apply_a_pose_mmd(armature)
        out_path = os.path.join(args.out, bg_name, "apose_face.png")
        render(out_path, tuple(args.res), args.samples)
        n_rendered += 1
        print(f"RESULT: {out_path}")

    print(f"RESULT: {n_rendered} images rendues dans {args.out} "
          f"({'avec' if has_a_pose else 'SANS'} A-pose distincte du bind pose)")


if __name__ == "__main__":
    main()

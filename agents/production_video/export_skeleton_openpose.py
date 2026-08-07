"""Export headless Blender : squelette (bones, position monde) -> JSON
format OpenPose standard (25 keypoints corps BODY_25 + 21 main gauche +
21 main droite), un fichier par frame.

Pas de rendu image : projection 3D->2D des tetes d'os via la matrice de la
camera de scene (`bpy_extras.object_utils.world_to_camera_view`), a la
resolution `--res`. Reutilise les memes fonctions d'import que
`blender_previz.py` (mmd_tools pour PMX+VMD, import_scene.fbx/gltf pour les
FBX Umodel) pour rester coherent avec le reste du pipeline previz.

Skeletons supportes (auto-detection par nom d'armature/bones a l'import) :
- "mmd"    : PMX (bones japonais "Semi-Standard Bones" de mmd_tools : nom de
             base + suffixe ".L"/".R", ex. Miku, personnages MMD community
             SAO/DIVA convertis en VMD). Mapping verifie par dump reel des
             556 bones de Miku "Rock Cat" (session 2026-08-06,
             DEMO/_bone_dump.txt) -- PAS suppose depuis la doc en ligne.
- "mixamo" : FBX rigge Mixamo (prefixe "mixamorig:Hips" etc.)
- "ue4"    : FBX Umodel UE4 (FighterZ/SAO Alicization Lycoris, convention
             "pelvis"/"spine_01"/"hand_l" etc., variable selon l'export)

Le mapping bone->keypoint OpenPose est resolu dynamiquement par
`RESOLVERS[skel_type]` (nom de bone -> index BODY_25 ou main). Une frame/bone
introuvable est ecrite avec confidence 0.0 (pas d'erreur bloquante : certains
rigs n'ont pas tous les doigts, ex. FighterZ FBX simplifie).

Usage (depuis la racine du depot) :
    blender.exe -b -P agents/production_video/export_skeleton_openpose.py -- \
        --skel-type mmd \
        --pmx "E:/Data Demo/_extracted/atrier_Rock Cat Miku_Ver.1.00/Tsatou_Rock Cat Miku_Ver.1.00.pmx" \
        --vmd "E:/Data Demo/_extracted/atrier_motion_pack_2_by_kefast_dcneqrj/Motion Pack 2/Look at my muscle.vmd" \
        --out DEMO/frames/openpose_synthetic/mmd/miku/casual \
        --res 1024 1536 --frame-step 1

    blender.exe -b -P agents/production_video/export_skeleton_openpose.py -- \
        --skel-type ue4 \
        --fbx "E:/Data Demo/FighterZ_extracted/Chara/GKS/Anim/GKS_anim.fbx" \
        --out DEMO/frames/openpose_synthetic/dbz_fighterz/goku/base \
        --res 1024 1536
"""
import argparse
import json
import math
import os
import sys

import bpy

# --- BODY_25 (index -> nom OpenPose, pour documentation/debug uniquement) ---
BODY_25_NAMES = [
    "Nose", "Neck", "RShoulder", "RElbow", "RWrist", "LShoulder", "LElbow",
    "LWrist", "MidHip", "RHip", "RKnee", "RAnkle", "LHip", "LKnee", "LAnkle",
    "REye", "LEye", "REar", "LEar", "LBigToe", "LSmallToe", "LHeel",
    "RBigToe", "RSmallToe", "RHeel",
]
HAND_21_NAMES = [
    "Wrist",
    "Thumb1", "Thumb2", "Thumb3", "Thumb4",
    "Index1", "Index2", "Index3", "Index4",
    "Middle1", "Middle2", "Middle3", "Middle4",
    "Ring1", "Ring2", "Ring3", "Ring4",
    "Pinky1", "Pinky2", "Pinky3", "Pinky4",
]

# --- Mapping bone name (Blender, apres import) -> index BODY_25 / main ---
# mmd_tools importe les bones PMX renommes selon sa convention "Semi-Standard
# Bones" : nom de base japonais + SUFFIXE ".L"/".R" (le cote n'est PAS un
# prefixe conserve dans le nom, contrairement a la doc communautaire
# generique). Verifie par dump reel des 556 bones de Miku "Rock Cat" (session
# 2026-08-06, cf. DEMO/_bone_dump.txt) : "\u80a9.L" (epaule/clavicule),
# "\u8155.L" (bras haut -- tete de bone = point d'epaule reel pour
# OpenPose), "\u3072\u3058.L" (coude), "\u624b\u9996.L" (poignet).
# L/R = gauche/droite du PERSONNAGE, coherent avec la semantique OpenPose
# RShoulder/LShoulder (deja du point de vue du sujet, pas de la camera).
MMD_BODY_BASE = {
    "\u8155": "Shoulder",    # 腕 (bras haut)
    "\u3072\u3058": "Elbow",  # ひじ (coude)
    "\u624b\u9996": "Wrist",  # 手首 (poignet)
    "\u8db3": "Hip",          # 足 (cuisse)
    "\u3072\u3056": "Knee",   # ひざ (genou)
    "\u8db3\u9996": "Ankle",  # 足首 (cheville)
    "\u3064\u307e\u5148": "BigToe",  # つま先 (bout de pied)
    "\u76ee": "Eye",          # 目 (oeil)
}
MMD_BODY_SINGLE = {
    "\u982d": "Nose",  # 頭 (tete, approx pour Nose -- pas de bone nez dedie)
    "\u9996": "Neck",  # 首 (cou)
    "\u4e0b\u534a\u8eab": "MidHip",  # 下半身 (bas du corps)
}
# Doigts : base(=segment1/MCP), base+"1"(=segment2/PIP), base+"2"(=segment3/
# DIP), puis pouce base+"2\u5148"(bout, pas de bone de rotation) OU autres
# doigts base+"3\u5148"(bout) -- verifie sur le dump reel
# (\u89aa\u6307.L / \u89aa\u6307\uff11.L / \u89aa\u6307\uff12.L /
#  \u89aa\u6307\uff12\u5148.L ; \u4eba\u6307.L / \u4eba\u6307\uff11.L /
#  \u4eba\u6307\uff12.L / \u4eba\u6307\uff13.L / \u4eba\u6307\uff13\u5148.L).
MMD_FINGER_JP = {
    "\u89aa\u6307": ("Thumb", ("", "\uff11", "\uff12", "\uff12\u5148")),   # 親指
    "\u4eba\u6307": ("Index", ("", "\uff11", "\uff12", "\uff13\u5148")),   # 人指
    "\u4e2d\u6307": ("Middle", ("", "\uff11", "\uff12", "\uff13\u5148")),  # 中指
    "\u85ac\u6307": ("Ring", ("", "\uff11", "\uff12", "\uff13\u5148")),    # 薬指
    "\u5c0f\u6307": ("Pinky", ("", "\uff11", "\uff12", "\uff13\u5148")),   # 小指
}


def build_mmd_hand_map(side_en):
    """side_en: 'L' ou 'R'. Retourne {nom_keypoint: nom_bone_blender}."""
    suffix = f".{side_en}"
    m = {"Wrist": f"\u624b\u9996{suffix}"}  # 手首
    for jp_base, (en_name, segment_suffixes) in MMD_FINGER_JP.items():
        for seg_idx, seg_suffix in enumerate(segment_suffixes, start=1):
            m[f"{en_name}{seg_idx}"] = f"{jp_base}{seg_suffix}{suffix}"
    return m


MIXAMO_BODY_MAP = {
    "mixamorig:Head": "Nose", "mixamorig:Neck": "Neck",
    "mixamorig:RightArm": "RShoulder", "mixamorig:RightForeArm": "RElbow", "mixamorig:RightHand": "RWrist",
    "mixamorig:LeftArm": "LShoulder", "mixamorig:LeftForeArm": "LElbow", "mixamorig:LeftHand": "LWrist",
    "mixamorig:Hips": "MidHip",
    "mixamorig:RightUpLeg": "RHip", "mixamorig:RightLeg": "RKnee", "mixamorig:RightFoot": "RAnkle",
    "mixamorig:LeftUpLeg": "LHip", "mixamorig:LeftLeg": "LKnee", "mixamorig:LeftFoot": "LAnkle",
    "mixamorig:RightToeBase": "RBigToe", "mixamorig:LeftToeBase": "LBigToe",
}

# UE4/Umodel : conventions variables selon l'export (FighterZ/SAO), on
# tente plusieurs alias courants par keypoint (le premier trouve gagne).
# Alias "g_*"/"gd_*" verifies par dump reel de GKS_body.gltf (Goku FighterZ,
# session 2026-08-06, DEMO/_bone_dump_gks.txt, 581 bones) : rig maison Arc
# System Works (prefixe G_=os principal FK, GD_=os deformation, GP_=physique)
# -- PAS un rig UE4 Mannequin standard malgre l'origine Umodel/UE4, d'ou ces
# alias en tete de liste avant les conventions generiques (Mixamo-like /
# UE4 Mannequin) gardees en repli pour d'autres assets (SAO Alicization).
# Pas de bones doigts individuels trouves dans ce mesh (GD_hand_L/R = main
# entiere) : les keypoints main resteront a confidence 0 pour cet asset,
# comportement attendu (cf. docstring module).
UE4_BODY_ALIASES = {
    "Nose": ["g_head", "head", "Head"], "Neck": ["g_neck", "neck_01", "Neck"],
    "RShoulder": ["g_uparm_r", "upperarm_r", "RightArm"], "RElbow": ["g_lowarm_r", "lowerarm_r", "RightForeArm"], "RWrist": ["gd_hand_r", "hand_r", "RightHand"],
    "LShoulder": ["g_uparm_l", "upperarm_l", "LeftArm"], "LElbow": ["g_lowarm_l", "lowerarm_l", "LeftForeArm"], "LWrist": ["gd_hand_l", "hand_l", "LeftHand"],
    "MidHip": ["g_pelvis", "pelvis", "Hips"],
    "RHip": ["g_thigh_r", "thigh_r", "RightUpLeg"], "RKnee": ["g_calf_r", "calf_r", "RightLeg"], "RAnkle": ["gd_foot_r", "foot_r", "RightFoot"],
    "LHip": ["g_thigh_l", "thigh_l", "LeftUpLeg"], "LKnee": ["g_calf_l", "calf_l", "LeftLeg"], "LAnkle": ["gd_foot_l", "foot_l", "LeftFoot"],
    "RBigToe": ["gd_toe_r", "ball_r", "RightToeBase"], "LBigToe": ["gd_toe_l", "ball_l", "LeftToeBase"],
}
UE4_FINGERS = ["thumb", "index", "middle", "ring", "pinky"]


def parse_args():
    argv = sys.argv
    argv = argv[argv.index("--") + 1:] if "--" in argv else []
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--skel-type", required=True, choices=["mmd", "mixamo", "ue4"])
    p.add_argument("--pmx", help="[mmd] Chemin PMX")
    p.add_argument("--vmd", action="append", default=[], help="[mmd] Chemin VMD (repetable)")
    p.add_argument("--fbx", help="[mixamo/ue4] Chemin FBX rigge (.fbx ou .gltf/.glb -- extension auto-detectee)")
    p.add_argument("--out", required=True, help="Dossier de sortie (un JSON par frame)")
    p.add_argument("--res", type=int, nargs=2, default=[1024, 1536])
    p.add_argument("--frame-start", type=int, default=None)
    p.add_argument("--frame-end", type=int, default=None)
    p.add_argument("--frame-step", type=int, default=1)
    p.add_argument("--max-frames", type=int, default=300, help="Plafond de securite (evite un export de plusieurs Go par erreur)")
    return p.parse_args(argv)


def clear_scene():
    bpy.ops.wm.read_factory_settings(use_empty=True)


def import_mmd(pmx_path, vmd_paths):
    import addon_utils
    if not addon_utils.check("bl_ext.blender_org.mmd_tools")[1]:
        addon_utils.enable("bl_ext.blender_org.mmd_tools", default_set=True)
    bpy.ops.mmd_tools.import_model(filepath=pmx_path, scale=0.08,
                                    types={'MESH', 'ARMATURE', 'PHYSICS', 'DISPLAY', 'MORPHS'})
    armature = next((o for o in bpy.context.scene.objects if o.type == 'ARMATURE'), None)
    if armature is None:
        raise RuntimeError(f"Aucune armature apres import PMX: {pmx_path}")
    bpy.context.view_layer.objects.active = armature
    frame_end = 1
    for vmd_path in vmd_paths:
        bpy.ops.mmd_tools.import_vmd(filepath=vmd_path, scale=1.0, margin=0, bone_mapper='PMX',
                                      use_pose_mode=False, use_mirror=False, update_scene_settings=True)
        if armature.animation_data and armature.animation_data.action:
            frame_end = max(frame_end, int(armature.animation_data.action.frame_range[1]))
    return armature, 1, frame_end


def import_fbx(fbx_path):
    """Malgre le nom (conserve pour compat CLI --fbx), accepte aussi .gltf/.glb
    -- Umodel exporte le mesh+squelette FighterZ en .gltf (le .psa d'animation
    separe necessite l'addon io_scene_psk_psa, casse sur Blender 5.1, cf.
    WAKE_UP_2026-08-06.md point 3 : on importe donc ici la bind pose T-pose
    uniquement, pas d'animation, tant que ce blocage n'est pas leve)."""
    ext = os.path.splitext(fbx_path)[1].lower()
    before = set(bpy.data.objects.keys())
    if ext in (".gltf", ".glb"):
        bpy.ops.import_scene.gltf(filepath=fbx_path)
    else:
        bpy.ops.import_scene.fbx(filepath=fbx_path)
    new_objs = [bpy.data.objects[n] for n in bpy.data.objects.keys() if n not in before]
    armature = next((o for o in new_objs if o.type == 'ARMATURE'), None)
    if armature is None:
        raise RuntimeError(f"Aucune armature apres import FBX: {fbx_path}")
    frame_start, frame_end = 1, 1
    if armature.animation_data and armature.animation_data.action:
        frame_start = int(armature.animation_data.action.frame_range[0])
        frame_end = int(armature.animation_data.action.frame_range[1])
    return armature, frame_start, frame_end


def setup_camera_framing(armature):
    """Camera front, cadrant tout le corps (bounding box world de l'armature
    en pose courante), coherente avec `setup_shot_camera` de blender_previz.py
    (meme convention radius/height) mais figee (pas de plan de plans ici :
    l'objectif est l'export skeleton, pas le rendu)."""
    bpy.context.view_layer.update()
    coords = [armature.matrix_world @ pb.head for pb in armature.pose.bones]
    if not coords:
        coords = [armature.matrix_world.translation]
    xs, ys, zs = zip(*[(c.x, c.y, c.z) for c in coords])
    cx, cz = (min(xs) + max(xs)) / 2, (min(zs) + max(zs)) / 2
    height = max(zs) - min(zs) or 1.0

    cam_data = bpy.data.cameras.new("skel_cam")
    cam_data.lens_unit = 'FOV'
    cam_data.angle = math.radians(45.0)
    cam_obj = bpy.data.objects.new("skel_cam", cam_data)
    bpy.context.scene.collection.objects.link(cam_obj)
    bpy.context.scene.camera = cam_obj

    radius = height * 1.8
    cam_obj.location = (cx, min(ys) - radius, cz + height * 0.1)
    target = bpy.data.objects.new("skel_cam_target", None)
    target.location = (cx, (min(ys) + max(ys)) / 2, cz)
    bpy.context.scene.collection.objects.link(target)
    constraint = cam_obj.constraints.new(type='TRACK_TO')
    constraint.target = target
    constraint.track_axis = 'TRACK_NEGATIVE_Z'
    constraint.up_axis = 'UP_Y'
    bpy.context.view_layer.update()
    return cam_obj


def project_bone_head(scene, cam_obj, armature, pose_bone, res):
    from bpy_extras.object_utils import world_to_camera_view
    world_pos = armature.matrix_world @ pose_bone.head
    co2d = world_to_camera_view(scene, cam_obj, world_pos)
    x_px = co2d.x * res[0]
    y_px = (1.0 - co2d.y) * res[1]  # OpenPose: origine haut-gauche, y vers le bas
    visible = 0.0 <= co2d.x <= 1.0 and 0.0 <= co2d.y <= 1.0 and co2d.z > 0
    return x_px, y_px, (1.0 if visible else 0.0)


def build_keypoint_array(scene, cam_obj, armature, res, names, bone_lookup):
    """bone_lookup: dict nom_keypoint -> nom_bone_blender (ou None si absent)."""
    flat = []
    for name in names:
        bone_name = bone_lookup.get(name)
        pb = armature.pose.bones.get(bone_name) if bone_name else None
        if pb is None:
            flat.extend([0.0, 0.0, 0.0])
            continue
        x, y, c = project_bone_head(scene, cam_obj, armature, pb, res)
        flat.extend([round(x, 2), round(y, 2), c])
    return flat


def resolve_mmd_lookup(armature):
    bone_names = set(armature.pose.bones.keys())
    body_lookup = {}
    for jp_base, kp_base in MMD_BODY_BASE.items():
        for side_suffix, side_en in ((".L", "L"), (".R", "R")):
            bone = f"{jp_base}{side_suffix}"
            if bone in bone_names:
                body_lookup[f"{side_en}{kp_base}"] = bone
    for jp_bone, kp in MMD_BODY_SINGLE.items():
        if jp_bone in bone_names:
            body_lookup[kp] = jp_bone
    hand_lookup = {"L": {}, "R": {}}
    for side_en in ("L", "R"):
        for kp, bone in build_mmd_hand_map(side_en).items():
            if bone in bone_names:
                hand_lookup[side_en][kp] = bone
    return body_lookup, hand_lookup


def resolve_mixamo_lookup(armature):
    bone_names = set(armature.pose.bones.keys())
    body_lookup = {kp: bone for bone, kp in MIXAMO_BODY_MAP.items() if bone in bone_names}
    hand_lookup = {"L": {}, "R": {}}
    for side_prefix, side_en in (("Left", "L"), ("Right", "R")):
        wrist = f"mixamorig:{side_prefix}Hand"
        if wrist in bone_names:
            hand_lookup[side_en]["Wrist"] = wrist
        for finger in ["Thumb", "Index", "Middle", "Ring", "Pinky"]:
            for j in (1, 2, 3):
                bone = f"mixamorig:{side_prefix}Hand{finger}{j}"
                if bone in bone_names:
                    hand_lookup[side_en][f"{finger}{j+1}"] = bone
    return body_lookup, hand_lookup


def resolve_ue4_lookup(armature):
    bone_names = set(armature.pose.bones.keys())
    lower_map = {b.lower(): b for b in bone_names}
    body_lookup = {}
    for kp, aliases in UE4_BODY_ALIASES.items():
        for alias in aliases:
            if alias.lower() in lower_map:
                body_lookup[kp] = lower_map[alias.lower()]
                break
    hand_lookup = {"L": {}, "R": {}}
    for side_suffix, side_en in ("_l", "L"), ("_r", "R"):
        wrist_alias = f"hand{side_suffix}"
        if wrist_alias in lower_map:
            hand_lookup[side_en]["Wrist"] = lower_map[wrist_alias]
        for finger in UE4_FINGERS:
            for j in (1, 2, 3):
                for pattern in (f"{finger}_{j:02d}{side_suffix}", f"{finger}{j}{side_suffix}"):
                    if pattern in lower_map:
                        finger_kp = finger.capitalize()
                        hand_lookup[side_en][f"{finger_kp}{j+1}"] = lower_map[pattern]
                        break
    return body_lookup, hand_lookup


RESOLVERS = {"mmd": resolve_mmd_lookup, "mixamo": resolve_mixamo_lookup, "ue4": resolve_ue4_lookup}


def export_frame(scene, cam_obj, armature, res, body_lookup, hand_lookup, out_path):
    body = build_keypoint_array(scene, cam_obj, armature, res, BODY_25_NAMES, body_lookup)
    hand_l = build_keypoint_array(scene, cam_obj, armature, res, HAND_21_NAMES, hand_lookup["L"])
    hand_r = build_keypoint_array(scene, cam_obj, armature, res, HAND_21_NAMES, hand_lookup["R"])
    payload = {
        "version": 1.3,
        "people": [{
            "person_id": [-1],
            "pose_keypoints_2d": body,
            "face_keypoints_2d": [],
            "hand_left_keypoints_2d": hand_l,
            "hand_right_keypoints_2d": hand_r,
            "pose_keypoints_3d": [],
            "face_keypoints_3d": [],
            "hand_left_keypoints_3d": [],
            "hand_right_keypoints_3d": [],
        }],
    }
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(payload, f)


def main():
    args = parse_args()
    args.out = os.path.abspath(args.out)
    clear_scene()

    if args.skel_type == "mmd":
        if not args.pmx or not args.vmd:
            raise ValueError("--skel-type mmd requiert --pmx et >=1 --vmd")
        armature, f_start, f_end = import_mmd(args.pmx, args.vmd)
    else:
        if not args.fbx:
            raise ValueError("--skel-type mixamo/ue4 requiert --fbx")
        armature, f_start, f_end = import_fbx(args.fbx)

    f_start = args.frame_start if args.frame_start is not None else f_start
    f_end = args.frame_end if args.frame_end is not None else f_end
    frames = list(range(f_start, f_end + 1, max(1, args.frame_step)))
    if len(frames) > args.max_frames:
        print(f"AVERTISSEMENT: {len(frames)} frames > max-frames={args.max_frames}, troncature.")
        frames = frames[: args.max_frames]

    scene = bpy.context.scene
    scene.frame_set(frames[0])
    cam_obj = setup_camera_framing(armature)

    body_lookup, hand_lookup = RESOLVERS[args.skel_type](armature)
    n_body_found = len(body_lookup)
    n_hand_found = sum(len(v) for v in hand_lookup.values())
    print(f"RESULT mapping: {n_body_found}/{len(BODY_25_NAMES)} keypoints corps, "
          f"{n_hand_found}/{2*len(HAND_21_NAMES)} keypoints mains resolus sur ce squelette.")
    if n_body_found < 8:
        print("ERREUR: trop peu de bones corps resolus, verifier le mapping / le rig importe.", file=sys.stderr)

    for f in frames:
        scene.frame_set(f)
        bpy.context.view_layer.update()
        out_path = os.path.join(args.out, f"frame_{f:05d}.json")
        export_frame(scene, cam_obj, armature, tuple(args.res), body_lookup, hand_lookup, out_path)

    print(f"RESULT: {len(frames)} frames exportees (OpenPose JSON) dans {args.out}")


if __name__ == "__main__":
    main()

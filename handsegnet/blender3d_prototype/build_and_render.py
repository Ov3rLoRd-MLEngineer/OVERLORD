"""
Suite du test de faisabilite (ADDENDUM_PISTES_FUTURES_V3_JUILLET2026.md, prerequis #1) :

v2 - corrige le bug de rig de v1 (blobs disjoints) et passe en MULTI-CLASSE :
  - v1 utilisait un decalage manuel (0,-bone.length,0) apres BONE-parenting, qui ne
    tient pas pour des os avec un roll non trivial (tout ce qui n'est pas droit haut) ;
    corrige ici via bpy.ops.object.parent_set(type='BONE', keep_transform=True), qui
    laisse Blender calculer la bonne matrice - la geometrie est d'abord positionnee/
    orientee dans l'espace MONDE (alignee sur le vecteur reel de l'os), puis parentee
    sans bouger.
  - segments = ellipsoides (spheres UV etirees) qui se chevauchent legerement d'un
    segment a l'autre -> silhouette continue au lieu de capsules qui se touchent a peine.
  - chaque partie anatomique garde un pass_index distinct (deja le cas en v1) ; on
    exploite maintenant ca pour extraire un masque binaire SEPARE par classe
    (poignet, paume, pouce, index, majeur, annulaire, auriculaire), en plus du
    rendu ID-couleur combine et de la silhouette union (pour comparaison directe au
    masque HandSegNet reel mono-classe existant).

Usage :
  "C:\\Program Files\\Blender Foundation\\Blender 5.1\\blender.exe" -b -P build_and_render.py
"""
import bpy
import math
import os
import mathutils

OUT_DIR = os.path.dirname(os.path.abspath(__file__))
RES_X, RES_Y = 1024, 1280  # meme resolution que dataset/masks HandSegNet existant

# id -> (nom de classe, couleur d'identification / beaute)
ID_CLASSES = {
    1: ("wrist", (0.45, 0.45, 0.45)),
    2: ("palm", (0.75, 0.75, 0.75)),
    3: ("thumb", (1.0, 0.0, 0.0)),
    4: ("index", (0.0, 1.0, 0.0)),
    5: ("middle", (0.0, 0.3, 1.0)),
    6: ("ring", (1.0, 0.85, 0.0)),
    7: ("pinky", (1.0, 0.0, 1.0)),
}

# chevauchement entre segments voisins (fraction de la longueur du segment ajoutee
# de chaque cote) pour fusionner visuellement les phalanges en une silhouette continue
OVERLAP = 0.35


def clear_scene():
    bpy.ops.object.select_all(action='SELECT')
    bpy.ops.object.delete(use_global=False)


def make_material(name, color, pass_index):
    mat = bpy.data.materials.new(name)
    mat.use_nodes = True
    bsdf = mat.node_tree.nodes.get('Principled BSDF')
    if bsdf:
        bsdf.inputs['Base Color'].default_value = (*color, 1.0)
        if 'Roughness' in bsdf.inputs:
            bsdf.inputs['Roughness'].default_value = 0.6
    mat.pass_index = pass_index
    return mat


def bone_parent_keep_transform(obj, armature_obj, bone_name):
    """Parente obj a bone_name en preservant sa position/rotation monde actuelle
    (laisse Blender calculer la matrice parent-inverse correcte, y compris pour
    des os avec un roll non trivial - cf. echec du calcul manuel en v1)."""
    bpy.ops.object.select_all(action='DESELECT')
    obj.select_set(True)
    armature_obj.select_set(True)
    bpy.context.view_layer.objects.active = armature_obj
    armature_obj.data.bones.active = armature_obj.data.bones[bone_name]
    bpy.ops.object.parent_set(type='BONE', keep_transform=True)


def add_segment_ellipsoid(name, head, tail, radius, material):
    """Sphere UV etiree le long de head->tail, avec chevauchement OVERLAP de
    chaque cote pour que les segments voisins se fondent en silhouette continue."""
    head_v = mathutils.Vector(head)
    tail_v = mathutils.Vector(tail)
    direction = tail_v - head_v
    length = direction.length
    mid = (head_v + tail_v) / 2
    half_len = (length / 2) * (1.0 + OVERLAP)

    bpy.ops.mesh.primitive_uv_sphere_add(radius=1, location=mid)
    obj = bpy.context.active_object
    obj.name = name
    obj.rotation_mode = 'QUATERNION'
    obj.rotation_quaternion = mathutils.Vector((0, 0, 1)).rotation_difference(direction.normalized())
    obj.scale = (radius, radius, half_len)
    bpy.ops.object.shade_smooth()
    obj.data.materials.append(material)
    obj.pass_index = material.pass_index
    return obj


def add_box(name, center, half_extents, material):
    """half_extents: demi-taille en X/Y/Z. primitive_cube_add(size=1) cree un cube
    de demi-extent 0.5, donc scale = 2 * half_extents pour obtenir la taille voulue."""
    bpy.ops.mesh.primitive_cube_add(size=1, location=center)
    obj = bpy.context.active_object
    obj.name = name
    obj.scale = tuple(2 * h for h in half_extents)
    obj.data.materials.append(material)
    obj.pass_index = material.pass_index
    return obj


def build_finger_bones(name, base_head, direction, seg_lengths, edit_bones, palm_bone_name):
    head = list(base_head)
    prev_bone_name = palm_bone_name
    created = []
    for i, seg_len in enumerate(seg_lengths):
        tail = [head[j] + direction[j] * seg_len for j in range(3)]
        b = edit_bones.new(f"{name}_{i+1}")
        b.head = head
        b.tail = tail
        b.parent = edit_bones[prev_bone_name]
        b.use_connect = True
        created.append(b.name)
        prev_bone_name = b.name
        head = tail
    return created


def _norm(v):
    l = math.sqrt(sum(c * c for c in v))
    return tuple(c / l for c in v)


def main():
    clear_scene()
    scene = bpy.context.scene

    # --- Armature (squelette, positions identiques a v1) ---
    bpy.ops.object.armature_add(enter_editmode=False, location=(0, 0, 0))
    arm_obj = bpy.context.active_object
    arm_obj.name = "HandRig"
    arm_data = arm_obj.data
    arm_data.name = "HandRig_data"

    bpy.ops.object.mode_set(mode='EDIT')
    ebs = arm_data.edit_bones
    ebs.remove(ebs[0])

    wrist = ebs.new("wrist")
    wrist.head = (0, 0, 0)
    wrist.tail = (0, 0, 0.03)

    palm = ebs.new("palm")
    palm.head = (0, 0, 0.03)
    palm.tail = (0, 0, 0.10)
    palm.parent = wrist
    palm.use_connect = True

    finger_specs = [
        dict(name="thumb", base=(-0.05, -0.01, 0.055), dir=_norm((-0.9, -0.3, 0.9)),
             lengths=[0.035, 0.025, 0.02], radii=[0.013, 0.011, 0.009], pass_index=3),
        dict(name="index", base=(-0.028, 0, 0.10), dir=_norm((-0.15, 0, 1.0)),
             lengths=[0.042, 0.026, 0.02], radii=[0.011, 0.0095, 0.0085], pass_index=4),
        dict(name="middle", base=(0.0, 0, 0.10), dir=(0.0, 0.0, 1.0),
             lengths=[0.048, 0.03, 0.022], radii=[0.0115, 0.01, 0.0088], pass_index=5),
        dict(name="ring", base=(0.028, 0, 0.10), dir=_norm((0.15, 0, 1.0)),
             lengths=[0.044, 0.028, 0.02], radii=[0.011, 0.0095, 0.0085], pass_index=6),
        dict(name="pinky", base=(0.05, 0, 0.095), dir=_norm((0.3, 0, 1.0)),
             lengths=[0.034, 0.022, 0.017], radii=[0.0095, 0.0082, 0.0072], pass_index=7),
    ]

    finger_bones = {}
    for spec in finger_specs:
        bones = build_finger_bones(spec["name"], spec["base"], spec["dir"], spec["lengths"],
                                    ebs, "palm")
        finger_bones[spec["name"]] = bones

    bpy.ops.object.mode_set(mode='OBJECT')

    # --- Materiaux (un par classe) ---
    mats = {idx: make_material(f"mat_{name}", col, idx) for idx, (name, col) in ID_CLASSES.items()}

    # --- Meshes : wrist + palm en boites, doigts en ellipsoides chevauchants ---
    all_hand_meshes = []

    wrist_mesh = add_box("wrist_mesh", (0, 0, 0.015), (0.035, 0.02, 0.017), mats[1])
    bone_parent_keep_transform(wrist_mesh, arm_obj, "wrist")
    all_hand_meshes.append(wrist_mesh)

    palm_mesh = add_box("palm_mesh", (0, 0, 0.065), (0.05, 0.018, 0.035), mats[2])
    bone_parent_keep_transform(palm_mesh, arm_obj, "palm")
    all_hand_meshes.append(palm_mesh)

    for spec in finger_specs:
        bone_names = finger_bones[spec["name"]]
        for i, bname in enumerate(bone_names):
            bone = arm_obj.data.bones[bname]
            cap = add_segment_ellipsoid(f"{spec['name']}_seg{i+1}", bone.head_local, bone.tail_local,
                                         spec["radii"][i], mats[spec["pass_index"]])
            all_hand_meshes.append(cap)
            bone_parent_keep_transform(cap, arm_obj, bname)

    # --- Camera ---
    bpy.ops.object.camera_add(location=(0, -0.55, 0.11), rotation=(math.radians(90), 0, 0))
    cam = bpy.context.active_object
    cam.data.lens = 60
    scene.camera = cam

    # --- Lights (rendu beaute uniquement) ---
    bpy.ops.object.light_add(type='SUN', location=(0.3, -0.4, 0.6))
    bpy.context.active_object.data.energy = 3.0
    bpy.ops.object.light_add(type='AREA', location=(-0.3, -0.5, 0.2))
    bpy.context.active_object.data.energy = 40.0

    scene.render.resolution_x = RES_X
    scene.render.resolution_y = RES_Y
    scene.render.film_transparent = False
    scene.render.image_settings.file_format = 'PNG'

    # --- 1) Beaute/contexte (Workbench, couleur materiau, rapide) ---
    scene.render.engine = 'BLENDER_WORKBENCH'
    scene.display.shading.light = 'STUDIO'
    scene.display.shading.color_type = 'MATERIAL'
    scene.render.filepath = os.path.join(OUT_DIR, "render_beauty.png")
    bpy.ops.render.render(write_still=True)

    # --- 2) Buffers de segmentation via la passe Object Index (Cycles + compositor) ---
    scene.render.engine = 'CYCLES'
    scene.cycles.samples = 8
    scene.cycles.use_denoising = False
    view_layer = bpy.context.view_layer
    view_layer.use_pass_object_index = True

    scene.use_nodes = True
    tree = bpy.data.node_groups.new("Compositing Nodetree", 'CompositorNodeTree')
    scene.compositing_node_group = tree
    tree.interface.new_socket(name="Image", socket_type='NodeSocketColor', in_out='OUTPUT')

    rl = tree.nodes.new('CompositorNodeRLayers')
    rl.layer = view_layer.name
    group_out = tree.nodes.new('NodeGroupOutput')

    def new_mix_rgba(blend_type):
        m = tree.nodes.new('ShaderNodeMix')
        m.data_type = 'RGBA'
        m.blend_type = blend_type
        m.inputs[0].default_value = 1.0  # Factor
        return m.inputs[6], m.inputs[7], m.outputs[2]  # A, B, Result (sockets RGBA)

    idmask_out = {}  # idx -> alpha 0/1 socket
    color_chain_out = None
    for idx, (cls_name, col) in ID_CLASSES.items():
        idmask = tree.nodes.new('CompositorNodeIDMask')
        idmask.inputs['Index'].default_value = idx
        idmask.inputs['Anti-Alias'].default_value = True
        tree.links.new(rl.outputs['Object Index'], idmask.inputs['ID value'])
        idmask_out[idx] = idmask.outputs[0]

        rgb = tree.nodes.new('CompositorNodeRGB')
        rgb.outputs[0].default_value = (*col, 1.0)

        mul_a, mul_b, mul_out = new_mix_rgba('MULTIPLY')
        tree.links.new(idmask.outputs[0], mul_a)
        tree.links.new(rgb.outputs[0], mul_b)

        if color_chain_out is None:
            color_chain_out = mul_out
        else:
            add_a, add_b, add_out = new_mix_rgba('ADD')
            tree.links.new(color_chain_out, add_a)
            tree.links.new(mul_out, add_b)
            color_chain_out = add_out

    binary_chain_out = None
    for idx in ID_CLASSES:
        if binary_chain_out is None:
            binary_chain_out = idmask_out[idx]
        else:
            addb_a, addb_b, addb_out = new_mix_rgba('ADD')
            tree.links.new(binary_chain_out, addb_a)
            tree.links.new(idmask_out[idx], addb_b)
            binary_chain_out = addb_out

    def render_socket_to(socket, filename):
        for link in list(group_out.inputs['Image'].links):
            tree.links.remove(link)
        tree.links.new(socket, group_out.inputs['Image'])
        scene.render.filepath = os.path.join(OUT_DIR, filename)
        bpy.ops.render.render(write_still=True)

    render_socket_to(color_chain_out, "seg_idcolor.png")
    render_socket_to(binary_chain_out, "seg_binary.png")

    for idx, (cls_name, _col) in ID_CLASSES.items():
        render_socket_to(idmask_out[idx], f"seg_class_{idx}_{cls_name}.png")

    # --- 3) Rendu cel-shade (calibrage domain gap vs style SDXL/fabricatedXL) ---
    # Toon shader NPR classique : Diffuse -> Shader to RGB -> ColorRamp constant
    # (2 paliers = teinte eclairee / teinte d'ombre), pas de degrade photoreel.
    # + Freestyle pour le contour noir marque (silhouette/bordure/plis), a la
    # place des faces "matcap" plates du rendu beaute Workbench precedent.
    # scene.use_nodes = False est un no-op en Blender 5.x tant qu'un
    # compositing_node_group reste assigne (le compositeur continue de tourner et
    # ecrase le rendu - piege verifie empiriquement, cause du rendu 100% noir lors
    # du premier essai). Il faut detacher explicitement le groupe.
    scene.compositing_node_group = None
    scene.use_nodes = False
    scene.render.engine = 'BLENDER_EEVEE'
    # AgX (view transform par defaut) desature/compresse les tons -> rend le flat
    # cel-shade grisatre au lieu des couleurs franches voulues ; Standard les
    # restitue telles que definies dans le ColorRamp.
    scene.view_settings.view_transform = 'Standard'

    toon_mat = bpy.data.materials.new("mat_skin_toon")
    toon_mat.use_nodes = True
    nt = toon_mat.node_tree
    nt.nodes.clear()
    diffuse = nt.nodes.new('ShaderNodeBsdfDiffuse')
    diffuse.inputs['Color'].default_value = (0.8, 0.8, 0.8, 1.0)
    s2rgb = nt.nodes.new('ShaderNodeShaderToRGB')
    ramp = nt.nodes.new('ShaderNodeValToRGB')
    ramp.color_ramp.interpolation = 'CONSTANT'
    ramp.color_ramp.elements[0].position = 0.45
    ramp.color_ramp.elements[0].color = (0.86, 0.62, 0.55, 1.0)   # teinte d'ombre (plus chaude/foncee)
    ramp.color_ramp.elements[1].position = 0.46
    ramp.color_ramp.elements[1].color = (1.0, 0.87, 0.79, 1.0)    # teinte eclairee (peau claire anime)
    emission = nt.nodes.new('ShaderNodeEmission')
    out = nt.nodes.new('ShaderNodeOutputMaterial')
    nt.links.new(diffuse.outputs[0], s2rgb.inputs[0])
    nt.links.new(s2rgb.outputs[0], ramp.inputs[0])
    nt.links.new(ramp.outputs[0], emission.inputs['Color'])
    nt.links.new(emission.outputs[0], out.inputs['Surface'])

    for obj in all_hand_meshes:
        obj.data.materials.clear()
        obj.data.materials.append(toon_mat)

    scene.render.use_freestyle = True
    view_layer.use_freestyle = True
    fs = view_layer.freestyle_settings
    for existing in list(fs.linesets):
        fs.linesets.remove(existing)
    ls = fs.linesets.new("HandLines")
    ls.select_silhouette = True
    ls.select_border = True
    ls.select_crease = True
    ls.select_external_contour = True
    ls.linestyle.color = (0.0, 0.0, 0.0)
    ls.linestyle.thickness = 3.0

    scene.render.filepath = os.path.join(OUT_DIR, "render_celshaded.png")
    bpy.ops.render.render(write_still=True)

    print("DONE. Files written to", OUT_DIR)


if __name__ == "__main__":
    main()

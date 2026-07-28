"""
v3 - proxy geometrique en metaballs, remplace les boites+ellipsoides de v2.

Probleme identifie sur v2 (session du 2026-07-25, memoire projet
`blender-3d-segnet-pivot`, verdict du calibrage cel-shading) : ce n'est PAS
le shader qui bloquait le rendu cel-shade, c'est la geometrie. Les segments
de doigt (ellipsoides qui se chevauchent legerement, cf. `OVERLAP` de v2)
restent des surfaces DISTINCTES qui se touchent a peine -> chaque phalange
ressort comme un renflement separe ("collier de perles") au lieu d'un doigt
continu qui s'affine. Le poignet/la paume en boites ont des angles droits
qui n'existent dans aucune anatomie reelle. Sous Freestyle, ces jointures
artificielles (bosses inter-phalange + coins de boite) sont detectees comme
des aretes/creases et dessinees en trait noir a des endroits qui ne
correspondent a rien d'anatomique - aucun reglage de lumiere/ColorRamp ne
peut corriger ca, seule la geometrie sous-jacente est en cause.

Fix v3 : chaque partie anatomique (poignet, paume, chacun des 5 doigts)
devient un objet METABALL (surface implicite) au lieu d'un ou plusieurs
objets mesh :
  - poignet/paume : 1 element ELLIPSOID (arrondi, plus d'angle droit).
  - chaque doigt : 3 elements CAPSULE (un par phalange) DANS LE MEME objet
    metaball -> ils fusionnent nativement en une seule surface continue,
    effilee du doigt vers la pointe (rayons decroissants), sans bosse a
    chaque jointure.

Choix delibere : 7 objets SEPARES (un par classe), chacun avec un blend
INTERNE entre ses propres elements, plutot qu'un unique objet metaball
global pour toute la main. Un objet global aurait fusionne aussi les
FRONTIERES entre classes (base de doigt/paume, paume/poignet) - hors de
propos ici pour deux raisons : (1) l'Object Index (passe de segmentation)
est une propriete PAR OBJET (`obj.pass_index`), fusionner tout en un objet
aurait rendu impossible de separer les 7 masques de classe (verifie :
`MetaElement` n'a pas de `material_index` dans cette version de Blender,
donc pas d'alternative "index materiau par element" pour recuperer la
separation autrement) ; (2) une ligne visible base-de-doigt/paume et
poignet/paume correspond a une vraie crease anatomique (pli du poignet,
base des doigts) - ce n'est pas le meme defaut que les bosses intra-doigt
qui elles ne correspondent a rien de reel. Le probleme cible etait
specifiquement intra-partie, pas inter-partie.

Consequence sur le rig : le bone-parenting d'objets separes (mecanisme de
v1/v2, source de bugs d'orientation lies au parent-inverse de Blender) n'a
plus de sens ici puisqu'il n'y a plus d'objet mesh par phalange a parenter -
un objet metaball par DOIGT contient deja ses 3 phalanges comme elements
internes. L'armature (construite comme avant) reste la source de verite des
positions/orientations de bone (tete/queue en espace monde), lues directement
pour positionner chaque element metaball au moment de la construction, sans
passer par un parentage Blender. Le pilotage par landmarks MediaPipe (objectif
2 de la session en cours) recalculera ces positions par frame directement a
partir des landmarks - pas de dependance au parent-inverse a corriger plus tard.

Usage (identique a v2) :
  "C:\\Program Files\\Blender Foundation\\Blender 5.1\\blender.exe" -b -P build_and_render_v3.py
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

# extension du demi-longueur de chaque capsule (fraction de sa longueur
# nominale, de chaque cote) pour que les elements voisins d'un meme doigt
# se chevauchent assez pour que leurs champs metaball fusionnent sans pincement
# a la jointure - equivalent du OVERLAP de v2, mais ici purement geometrique
# (le blend metaball fait le lissage, pas besoin de "cacher" la couture)
OVERLAP = 0.25

FINGER_SPECS = [
    dict(name="thumb", base=(-0.05, -0.01, 0.055), dir=None,
         lengths=[0.035, 0.025, 0.02], radii=[0.013, 0.011, 0.009], pass_index=3),
    dict(name="index", base=(-0.028, 0, 0.10), dir=None,
         lengths=[0.042, 0.026, 0.02], radii=[0.011, 0.0095, 0.0085], pass_index=4),
    dict(name="middle", base=(0.0, 0, 0.10), dir=(0.0, 0.0, 1.0),
         lengths=[0.048, 0.03, 0.022], radii=[0.0115, 0.01, 0.0088], pass_index=5),
    dict(name="ring", base=(0.028, 0, 0.10), dir=None,
         lengths=[0.044, 0.028, 0.02], radii=[0.011, 0.0095, 0.0085], pass_index=6),
    dict(name="pinky", base=(0.05, 0, 0.095), dir=None,
         lengths=[0.034, 0.022, 0.017], radii=[0.0095, 0.0082, 0.0072], pass_index=7),
]
# directions non-normalisees (memes valeurs que v2), normalisees plus bas
_RAW_DIRS = {
    "thumb": (-0.9, -0.3, 0.9),
    "index": (-0.15, 0, 1.0),
    "ring": (0.15, 0, 1.0),
    "pinky": (0.3, 0, 1.0),
}


def _norm(v):
    l = math.sqrt(sum(c * c for c in v))
    return tuple(c / l for c in v)


for spec in FINGER_SPECS:
    if spec["dir"] is None:
        spec["dir"] = _norm(_RAW_DIRS[spec["name"]])


def clear_scene():
    bpy.ops.object.select_all(action='SELECT')
    bpy.ops.object.delete(use_global=False)


def _find_node(node_tree, bl_idname):
    """Cherche un noeud par bl_idname (stable), pas par nom localise (les noms
    par defaut sont traduits selon la langue de l'UI Blender - `.get('Principled
    BSDF')` echoue silencieusement sur une install en francais, ex. 'BSDF guidee' -
    piege verifie empiriquement sur cette machine)."""
    for n in node_tree.nodes:
        if n.bl_idname == bl_idname:
            return n
    return None


def make_material(name, color, pass_index):
    mat = bpy.data.materials.new(name)
    mat.use_nodes = True
    bsdf = _find_node(mat.node_tree, 'ShaderNodeBsdfPrincipled')
    if bsdf:
        bsdf.inputs['Base Color'].default_value = (*color, 1.0)
        if 'Roughness' in bsdf.inputs:
            bsdf.inputs['Roughness'].default_value = 0.6
    mat.pass_index = pass_index
    return mat


def build_rig():
    """Construit uniquement l'armature (source des positions/orientations de bone) -
    plus de bone-parenting d'objets separes en v3 (cf. docstring module)."""
    bpy.ops.object.armature_add(enter_editmode=False, location=(0, 0, 0))
    arm_obj = bpy.context.active_object
    arm_obj.name = "HandRig"
    arm_obj.data.name = "HandRig_data"

    bpy.ops.object.mode_set(mode='EDIT')
    ebs = arm_obj.data.edit_bones
    ebs.remove(ebs[0])

    wrist = ebs.new("wrist")
    wrist.head = (0, 0, 0)
    wrist.tail = (0, 0, 0.03)

    palm = ebs.new("palm")
    palm.head = (0, 0, 0.03)
    palm.tail = (0, 0, 0.10)
    palm.parent = wrist
    palm.use_connect = True

    finger_bones = {}
    for spec in FINGER_SPECS:
        head = list(spec["base"])
        prev_name = "palm"
        names = []
        for i, seg_len in enumerate(spec["lengths"]):
            tail = [head[j] + spec["dir"][j] * seg_len for j in range(3)]
            b = ebs.new(f"{spec['name']}_{i + 1}")
            b.head = head
            b.tail = tail
            b.parent = ebs[prev_name]
            # use_connect force head_local == parent.tail_local, ce qui est
            # correct entre deux phalanges consecutives (i>0, la pointe de la
            # precedente EST la base de la suivante) mais faux pour la 1ere
            # phalange : sa base (spec["base"]) n'est PAS la pointe de la paume,
            # elle est repartie a un endroit distinct par doigt. Sans ce fix,
            # use_connect=True ecrasait silencieusement les 5 `base` par le
            # meme point (tail de "palm") -> les 5 doigts convergeaient tous au
            # meme hub au lieu de partir de leur position propre le long de la
            # paume (verifie par introspection directe des bones apres
            # construction, cf. CLASS_SCHEMA.md "Limite restante" v3).
            b.use_connect = (i > 0)
            names.append(b.name)
            prev_name = b.name
            head = tail
        finger_bones[spec["name"]] = names

    bpy.ops.object.mode_set(mode='OBJECT')
    return arm_obj, finger_bones


def add_metaball_object(name, pass_index, material):
    mb = bpy.data.metaballs.new(name)
    mb.resolution = 0.003
    mb.render_resolution = 0.0012
    obj = bpy.data.objects.new(name, mb)
    bpy.context.collection.objects.link(obj)
    obj.pass_index = pass_index
    obj.data.materials.append(material)
    return obj, mb


def add_capsule_element(mb, head, tail, radius, overlap=OVERLAP, negative=False):
    head_v = mathutils.Vector(head)
    tail_v = mathutils.Vector(tail)
    direction = tail_v - head_v
    length = direction.length
    mid = (head_v + tail_v) / 2
    half_len = (length / 2) * (1.0 + overlap)

    elem = mb.elements.new(type='CAPSULE')
    elem.co = mid
    elem.radius = radius
    elem.size_x = half_len
    elem.rotation = mathutils.Vector((1, 0, 0)).rotation_difference(direction.normalized())
    elem.use_negative = negative
    return elem


def add_palm_creases(mb, palm_center):
    """Ajoute 3 lignes de paume stylisees sous forme de fines CRETES
    (elements CAPSULE positifs, legerement proeminents hors de la face avant
    cote camera -Y de l'ellipsoide paume). But : donner au guide un minimum
    de detail interne dans une zone auparavant totalement lisse, pour
    contraindre le contenu genere par ControlNet dans cette region (cf.
    session precedente : une paume vide sans aucune ligne s'est fait combler
    par un objet halluciné - piste secondaire, la cause principale identifiee
    est un fragment de prompt independant du guide, cf. CLASS_SCHEMA.md
    "Enquete metadonnees"). Pas un objectif de realisme anatomique (vraies
    lignes de main sont courbes, ici 3 segments droits suffisent pour le but
    recherche)."""
    # Approche calibrée empiriquement (test isolé dédié) : des elements
    # NEGATIFS (creux/sillon) ne creent qu'une depression lisse (continue en
    # courbure) - invisible pour Freestyle "crease" quel que soit le seuil
    # teste (100 deg, 70 deg) ou le rayon (0.006 a 0.02), car il n'y a jamais
    # de vraie cassure d'angle, juste une pente douce. Une fine CRETE
    # POSITIVE (legerement proeminente hors de la surface) cree en revanche
    # deux transitions d'angle nettes (montee + descente) detectees sans
    # probleme meme a rayon fin (0.004-0.008 tous visibles au test isole).
    cx, cy, cz = palm_center
    # cote camera (-Y) ; legerement au-dela de la surface avant nominale de
    # l'ellipsoide (half_extent Y=0.024) pour que la crete depasse vraiment
    front_y = cy - 0.026
    lines = [
        # (offset_z, demi-largeur X, legere inclinaison)
        (0.028, 0.030, -0.008),   # ligne de coeur (haute, proche des doigts)
        (0.010, 0.033, 0.005),    # ligne de tete (mediane)
        (-0.012, 0.024, 0.014),   # ligne de vie (basse, cote pouce)
    ]
    for dz, half_w, tilt in lines:
        head = (cx - half_w, front_y, cz + dz - tilt)
        tail = (cx + half_w, front_y, cz + dz + tilt)
        # rayon calibre empiriquement : 0.003-0.004 se fragmentent en petits
        # eclats disjoints (resolution du maillage marching-cubes trop
        # grossiere pour une crete aussi fine a cette echelle) ; 0.005 donne
        # des lignes pleines et continues - prime la continuite sur la
        # finesse visuelle, l'objectif est un guide exploitable, pas un rendu
        # elegant.
        add_capsule_element(mb, head, tail, radius=0.005, overlap=0.0, negative=False)


def add_ellipsoid_element(mb, center, half_extents):
    elem = mb.elements.new(type='ELLIPSOID')
    elem.co = mathutils.Vector(center)
    elem.radius = 1.0
    elem.size_x, elem.size_y, elem.size_z = half_extents
    return elem


def main():
    clear_scene()
    scene = bpy.context.scene

    arm_obj, finger_bones = build_rig()
    mats = {idx: make_material(f"mat_{name}", col, idx) for idx, (name, col) in ID_CLASSES.items()}

    all_meta_objects = []

    # --- poignet / paume : ellipsoides (arrondis, plus de boite a angle droit) ---
    # Mesure empirique (voir memoire projet) : au seuil metaball par defaut
    # (mb.threshold=0.6), la surface visible d'un element ELLIPSOID ISOLE ne
    # fait qu'environ 55% des size_x/y/z demandes (pas d'element voisin pour
    # renforcer le champ pres du bord, contrairement aux doigts qui se
    # chevauchent). Un demi-extent egal au bord exact du bone (comme en v2,
    # boite) laissait donc un vrai vide visible entre poignet/paume/doigts au
    # premier rendu v3. Fix : seuil abaisse a 0.3 (moins de retrait, cf. test
    # threshold 0.6->55%, 0.3->74%, 0.1->85% de la taille nominale) + demi-extent
    # Z elargi au-dela du bord du bone (marge de recouvrement volontaire,
    # meme principe que OVERLAP pour les capsules de doigt).
    ELLIPSOID_THRESHOLD = 0.3

    wrist_obj, wrist_mb = add_metaball_object("wrist", 1, mats[1])
    wrist_mb.threshold = ELLIPSOID_THRESHOLD
    add_ellipsoid_element(wrist_mb, (0, 0, 0.015), (0.047, 0.027, 0.028))
    all_meta_objects.append(wrist_obj)

    palm_obj, palm_mb = add_metaball_object("palm", 2, mats[2])
    palm_mb.threshold = ELLIPSOID_THRESHOLD
    add_ellipsoid_element(palm_mb, (0, 0, 0.065), (0.067, 0.024, 0.052))
    add_palm_creases(palm_mb, (0, 0, 0.065))
    all_meta_objects.append(palm_obj)

    # --- doigts : 3 elements CAPSULE par doigt, MEME objet metaball -> fusion
    # interne continue (fixe le "collier de perles" de v2) ---
    for spec in FINGER_SPECS:
        finger_obj, finger_mb = add_metaball_object(spec["name"], spec["pass_index"], mats[spec["pass_index"]])
        for i, bname in enumerate(finger_bones[spec["name"]]):
            bone = arm_obj.data.bones[bname]
            add_capsule_element(finger_mb, bone.head_local, bone.tail_local, spec["radii"][i])
        all_meta_objects.append(finger_obj)

    # --- Camera (identique v2) ---
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
    # Mecanisme identique a v2 (verifie compatible avec des objets metaball via
    # un test de faisabilite dedie avant d'ecrire ce script) : pass_index est une
    # propriete par OBJET, indifferente au type de geometrie sous-jacent.
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

    idmask_out = {}
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

    # --- 3) Rendu cel-shade (recalibrage domain gap vs style SDXL/fabricatedXL) ---
    scene.compositing_node_group = None
    scene.use_nodes = False
    scene.render.engine = 'BLENDER_EEVEE'
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
    ramp.color_ramp.elements[0].color = (0.86, 0.62, 0.55, 1.0)
    ramp.color_ramp.elements[1].position = 0.46
    ramp.color_ramp.elements[1].color = (1.0, 0.87, 0.79, 1.0)
    emission = nt.nodes.new('ShaderNodeEmission')
    out = nt.nodes.new('ShaderNodeOutputMaterial')
    nt.links.new(diffuse.outputs[0], s2rgb.inputs[0])
    nt.links.new(s2rgb.outputs[0], ramp.inputs[0])
    nt.links.new(ramp.outputs[0], emission.inputs['Color'])
    nt.links.new(emission.outputs[0], out.inputs['Surface'])

    for obj in all_meta_objects:
        obj.data.materials.clear()
        obj.data.materials.append(toon_mat)

    scene.render.use_freestyle = True
    view_layer.use_freestyle = True
    fs = view_layer.freestyle_settings
    # Le maillage d'un metaball est tessellise par marching cubes : meme lisse
    # en apparence (shade smooth applique par defaut), les facettes creent de
    # petits angles reels entre polygones que Freestyle "crease" detecte comme
    # des aretes parasites (visible en v3 initial : petits traits epars le
    # long des doigts, pas de vraie crease anatomique). ATTENTION sens de ce
    # parametre (verifie empiriquement, contre-intuitif) : une valeur PLUS
    # HAUTE rend la detection PLUS sensible (170 deg a produit un hachurage
    # dense de triangles, pire que le defaut ~150 deg) - c'est l'angle en
    # dessous duquel deux faces sont jugees non-plates, pas un seuil de
    # tolerance croissante. Abaisse a 100 deg pour n'accrocher que les vraies
    # cassures (jointures entre elements metaball), pas le bruit de facettage.
    fs.crease_angle = math.radians(100)
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

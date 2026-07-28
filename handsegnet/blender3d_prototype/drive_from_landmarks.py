"""
Objectif 2 de la session (preuve de concept, portee volontairement reduite) :
piloter le proxy geometrique metaball (v3, `build_and_render_v3.py`) depuis de
VRAIS landmarks MediaPipe (`handsegnet/pose_capture/extract_hand_landmarks.py`)
au lieu des positions fixes de `FINGER_SPECS` - objectif final du chantier :
un guide de pose 3D dont le mouvement suit une capture video reelle,
exploitable en entree ControlNet plutot que comme source de masque pixel-exact
(cf. `ADDENDUM_PISTES_FUTURES_V3_JUILLET2026.md`, option 2 du domain gap).

Portee de cette preuve de concept (UNE frame, pas une sequence animee) :
prouver que le mecanisme de cablage landmarks -> elements metaball fonctionne
et produit une silhouette de main plausible, pas encore construire le pipeline
d'export frame-par-frame pour ControlNet (etape logique suivante si ce chantier
est repris).

Choix et limites assumees (a verifier/affiner si ce chantier continue) :
- Utilise `landmarks_world` (3D, mono-vue, origine=poignet) plutot que
  `landmarks_image` (2D pixels) - suffisant pour une pose statique plausible,
  MAIS PAS fiable en echelle absolue (cf. `LANDMARKS_FORMAT.md` : "coherent en
  interne, pas fiable en position/echelle absolue"). Verifie empiriquement sur
  `out_001.json` frame 0 : wrist->middle_tip ne fait que ~0.084 (unite du
  modele) contre ~0.20 pour le proxy statique v3 (somme des longueurs
  wrist+palm+doigt) - PAS la meme echelle, d'ou le facteur `SCALE` ci-dessous
  (calibre sur ce seul ratio globale, pas par-doigt : les proportions
  precises du proxy statique et de cette main reelle captee ne sont pas
  identiques, ecart mineur assume pour cette preuve de concept).
- Convention d'axes MediaPipe (image-space, y vers le bas, z = profondeur
  camera) remappee arbitrairement vers Blender (z-up) : blender_x=mp_x,
  blender_y=mp_z, blender_z=-mp_y. Choix NON verifie contre une vraie prise de
  vue calibree (meme point ouvert que `LANDMARKS_FORMAT.md`, section
  handedness/convention) - a corriger avec de vraies donnees stereo calibrees
  plutot qu'un choix arbitraire, une fois le tournage double camera disponible.
- Rayons des capsules et taille poignet/paume repris tels quels de
  `FINGER_SPECS`/la version statique (MediaPipe ne donne pas d'epaisseur) -
  seules les POSITIONS/ORIENTATIONS des segments suivent les landmarks.

Usage :
  "C:\\Program Files\\Blender Foundation\\Blender 5.1\\blender.exe" -b -P drive_from_landmarks.py
"""
import json
import math
import os
import sys

import bpy
import mathutils

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import build_and_render_v3 as base  # noqa: E402  (reutilise mats/helpers/pipeline de rendu)

LANDMARKS_JSON = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "..", "pose_capture", "out_001.json"
)
FRAME_INDEX = 0
HAND_INDEX = 0

# cf. docstring : calibre sur le ratio global wrist->middle_tip (proxy
# statique 0.20 / landmarks captes 0.0843), pas par-doigt.
SCALE = 2.37

FINGER_LANDMARK_CHAINS = {
    "thumb": ["thumb_cmc", "thumb_mcp", "thumb_ip", "thumb_tip"],
    "index": ["wrist", "index_mcp", "index_pip", "index_dip", "index_tip"],
    "middle": ["wrist", "middle_mcp", "middle_pip", "middle_dip", "middle_tip"],
    "ring": ["wrist", "ring_mcp", "ring_pip", "ring_dip", "ring_tip"],
    "pinky": ["wrist", "pinky_mcp", "pinky_pip", "pinky_dip", "pinky_tip"],
}
# thumb_cmc part directement du poignet (pas de landmark "wrist" intermediaire
# a inserer, contrairement aux 4 autres doigts ou le 1er segment metaball va
# du poignet au MCP)


def _remap(p):
    """MediaPipe (image-space, y vers le bas, z=profondeur camera) -> Blender
    (z-up). Choix arbitraire documente en tete de fichier, pas verifie contre
    une prise de vue calibree."""
    return mathutils.Vector((p["x"], p["z"], -p["y"])) * SCALE


def load_hand_landmarks():
    with open(LANDMARKS_JSON, encoding="utf-8") as f:
        data = json.load(f)
    names = data["landmark_names"]
    frame = data["frames"][FRAME_INDEX]
    hand = frame["hands"][HAND_INDEX]
    raw = {n: hand["landmarks_world"][i] for i, n in enumerate(names)}
    wrist0 = raw["wrist"]
    centered = {
        n: {k: v[k] - wrist0[k] for k in "xyz"} for n, v in raw.items()
    }
    return {n: _remap(v) for n, v in centered.items()}


def main():
    base.clear_scene()
    scene = bpy.context.scene

    lm = load_hand_landmarks()
    mats = {idx: base.make_material(f"mat_{name}", col, idx)
            for idx, (name, col) in base.ID_CLASSES.items()}

    all_meta_objects = []

    wrist_obj, wrist_mb = base.add_metaball_object("wrist", 1, mats[1])
    wrist_mb.threshold = 0.3
    base.add_ellipsoid_element(wrist_mb, lm["wrist"], (0.047, 0.027, 0.028))
    all_meta_objects.append(wrist_obj)

    mcp_names = ["thumb_mcp", "index_mcp", "middle_mcp", "ring_mcp", "pinky_mcp"]
    palm_center = sum((lm[n] for n in mcp_names), mathutils.Vector((0, 0, 0))) / len(mcp_names)
    palm_center = (palm_center + lm["wrist"]) / 2  # a mi-chemin poignet/base-doigts
    palm_obj, palm_mb = base.add_metaball_object("palm", 2, mats[2])
    palm_mb.threshold = 0.3
    base.add_ellipsoid_element(palm_mb, palm_center, (0.067, 0.024, 0.052))
    all_meta_objects.append(palm_obj)

    for spec in base.FINGER_SPECS:
        name = spec["name"]
        chain = FINGER_LANDMARK_CHAINS[name]
        finger_obj, finger_mb = base.add_metaball_object(name, spec["pass_index"], mats[spec["pass_index"]])
        for i in range(len(chain) - 1):
            head = lm[chain[i]]
            tail = lm[chain[i + 1]]
            radius = spec["radii"][min(i, len(spec["radii"]) - 1)]
            base.add_capsule_element(finger_mb, head, tail, radius)
        all_meta_objects.append(finger_obj)

    # Cadrage automatique : la camera fixe de v3 est calibree pour le proxy
    # statique centre a l'origine, pas pour une pose reelle dont la position/
    # echelle dependent de SCALE et de cette capture particuliere (ici une
    # main au sol en position de sprint, pas une pose "face camera" upright) -
    # cadrer sur le centroide/etendue reelle des landmarks plutot que sur une
    # position de camera figee.
    pts = list(lm.values())
    centroid = sum(pts, mathutils.Vector((0, 0, 0))) / len(pts)
    span = max((p - centroid).length for p in pts)
    cam_dist = max(span * 4.0, 0.15)
    bpy.ops.object.camera_add(
        location=(centroid.x, centroid.y - cam_dist, centroid.z),
        rotation=(math.radians(90), 0, 0),
    )
    cam = bpy.context.active_object
    cam.data.lens = 45
    scene.camera = cam

    bpy.ops.object.light_add(type='SUN', location=(0.3, -0.4, 0.6))
    bpy.context.active_object.data.energy = 3.0
    bpy.ops.object.light_add(type='AREA', location=(-0.3, -0.5, 0.2))
    bpy.context.active_object.data.energy = 40.0

    scene.render.resolution_x = base.RES_X
    scene.render.resolution_y = base.RES_Y
    scene.render.film_transparent = False
    scene.render.image_settings.file_format = 'PNG'

    out_dir = os.path.dirname(os.path.abspath(__file__))

    scene.render.engine = 'BLENDER_WORKBENCH'
    scene.display.shading.light = 'STUDIO'
    scene.display.shading.color_type = 'MATERIAL'
    scene.render.filepath = os.path.join(out_dir, "render_from_landmarks_beauty.png")
    bpy.ops.render.render(write_still=True)

    toon_mat = bpy.data.materials.new("mat_skin_toon_lm")
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
    out_node = nt.nodes.new('ShaderNodeOutputMaterial')
    nt.links.new(diffuse.outputs[0], s2rgb.inputs[0])
    nt.links.new(s2rgb.outputs[0], ramp.inputs[0])
    nt.links.new(ramp.outputs[0], emission.inputs['Color'])
    nt.links.new(emission.outputs[0], out_node.inputs['Surface'])

    for obj in all_meta_objects:
        obj.data.materials.clear()
        obj.data.materials.append(toon_mat)

    scene.render.use_freestyle = True
    view_layer = bpy.context.view_layer
    view_layer.use_freestyle = True
    fs = view_layer.freestyle_settings
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

    scene.render.filepath = os.path.join(out_dir, "render_from_landmarks_celshaded.png")
    bpy.ops.render.render(write_still=True)

    print("DONE. Files written to", out_dir)


if __name__ == "__main__":
    main()

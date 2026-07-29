"""
Objectif 2 de la session (portee etendue a une sequence, suite de la preuve de
concept 1-frame) : piloter le proxy geometrique metaball (v3,
`build_and_render_v3.py`) depuis de VRAIS landmarks MediaPipe
(`handsegnet/pose_capture/extract_hand_landmarks.py`) au lieu des positions
fixes de `FINGER_SPECS` - objectif final du chantier : un guide de pose 3D
dont le mouvement suit une capture video reelle, exploitable en entree
ControlNet plutot que comme source de masque pixel-exact (cf.
`ADDENDUM_PISTES_FUTURES_V3_JUILLET2026.md`, option 2 du domain gap).

Portee de cette version (SEQUENCE de frames consecutives, pas juste une pose
statique) : pilote le rig sur une plage de frames de `out_001.json` (ou tout
JSON produit par `extract_hand_landmarks.py`) et rend un beauty pass (+
celshaded optionnel) par frame, numerotes, dans un sous-dossier de sortie -
etape logique suivante de la PoC 1-frame precedente si ce chantier est repris
(export frame-par-frame pour ControlNet).

Choix et limites assumees (a verifier/affiner si ce chantier continue) :
- Utilise `landmarks_world` (3D, mono-vue, origine=poignet) plutot que
  `landmarks_image` (2D pixels) - suffisant pour une pose statique plausible,
  MAIS PAS fiable en echelle absolue (cf. `LANDMARKS_FORMAT.md` : "coherent en
  interne, pas fiable en position/echelle absolue"). Meme facteur `SCALE`
  global que la PoC 1-frame (calibre sur un seul ratio wrist->middle_tip,
  pas par-doigt, pas recalibre ici - hors perimetre de cette etape).
- Convention d'axes MediaPipe (image-space, y vers le bas, z = profondeur
  camera) remappee arbitrairement vers Blender (z-up) : blender_x=mp_x,
  blender_y=mp_z, blender_z=-mp_y. Choix NON verifie contre une vraie prise de
  vue calibree (meme point ouvert que `LANDMARKS_FORMAT.md`) - a corriger avec
  de vraies donnees stereo calibrees plutot qu'un choix arbitraire, une fois
  le tournage double camera disponible.
- Rayons des capsules et taille poignet/paume repris tels quels de
  `FINGER_SPECS`/la version statique (MediaPipe ne donne pas d'epaisseur) -
  seules les POSITIONS/ORIENTATIONS des segments suivent les landmarks.
- Frames sans main detectee dans la plage demandee : ignorees (log +
  compteur), pas de hold-last-pose - une sequence avec des trous reste plus
  honnete qu'une interpolation non demandee pour cette etape.
- Cadrage camera recalcule par frame (centroide/etendue des landmarks de
  CETTE frame) plutot que fige : la main bouge dans l'espace 3D remape d'une
  frame a l'autre, un cadrage fixe la sortirait du champ sur certaines frames
  de la sequence de test (sprint depart, mouvement ample). Consequence
  assumee : le zoom relatif petite/grande main peut varier legerement d'une
  frame a l'autre - pas un probleme pour un guide ControlNet par frame (chaque
  frame est traitee independamment en aval), a revisiter si un cadrage stable
  devient necessaire.

Usage (une frame, retro-compatible avec la PoC precedente) :
  "C:\\Program Files\\Blender Foundation\\Blender 5.1\\blender.exe" -b -P drive_from_landmarks.py

Usage (sequence) :
  "C:\\Program Files\\Blender Foundation\\Blender 5.1\\blender.exe" -b -P drive_from_landmarks.py -- ^
      --input ..\\pose_capture\\out_001.json --start-frame 0 --end-frame 25 ^
      --out-dir sequence_out --no-celshade

## GPU utilise par le moteur de rendu

Le moteur Workbench (utilise par la PoC 1-frame d'origine) s'appuie sur le
contexte OpenGL par defaut du systeme, non pilotable : teste empiriquement le
2026-07-29, la preference Windows "GPU par application" (registre
UserGpuPreferences, GpuPreference=1 "power saving") ne redirige PAS ce
contexte - le rendu restait sur la RTX 5080 (GPU d'affichage principal) meme
avec cette preference active. Le moteur Cycles (`--engine cycles`, par
defaut) expose en revanche une liste de devices CUDA/OptiX activables
individuellement (`configure_cycles_gpu`), ce qui permet de restreindre le
rendu a un GPU precis par nom (`--gpu-name`) de facon fiable - seule methode
qui a fonctionne sur cette machine pour eviter un GPU utilise par un autre
run (cf. regle projet dans `CLAUDE.md`, section GPU).

## Resultat du test sequence (2026-07-29)

26/26 frames consecutives (0-25 de `out_001.json`, seule main "Right"/"Left"
bruite mais toujours un hand_index=0 valide sur cette plage - cf.
`LANDMARKS_FORMAT.md`) rendues avec succes en beauty+celshaded, entierement
sur la RTX 5060 Ti (Cycles/OptiX, 32 samples, `--gpu-name "5060 Ti"`),
pendant qu'un entrainement Control-LoRA tournait a 100% sur la RTX 5080 sans
etre perturbe (verifie via nvidia-smi avant/pendant/apres). ~8m36s pour les
52 renders (1024x1280). Sortie non versionnee (regenerable), 3 frames
representatives (0, 12, 25) copiees dans `sequence_sample/` : la pose suit
visiblement le mouvement reel de la main (doigts qui se referment/tournent
entre le depart au sol et la mise en mouvement du sprint), confirmant que le
rig suit une sequence video reelle et pas une pose figee.
"""
import argparse
import json
import math
import os
import sys

import bpy
import mathutils

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import build_and_render_v3 as base  # noqa: E402  (reutilise mats/helpers/pipeline de rendu)

DEFAULT_LANDMARKS_JSON = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "..", "pose_capture", "out_001.json"
)
DEFAULT_OUT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "sequence_out")

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


def load_landmarks_json(path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def extract_hand_for_frame(data, frame_index, hand_index):
    """Retourne le dict {landmark_name: Vector Blender} pour une frame/main
    donnee, ou None si aucune main a cet index sur cette frame."""
    names = data["landmark_names"]
    frame = data["frames"][frame_index]
    if hand_index >= len(frame["hands"]):
        return None
    hand = frame["hands"][hand_index]
    raw = {n: hand["landmarks_world"][i] for i, n in enumerate(names)}
    wrist0 = raw["wrist"]
    centered = {n: {k: v[k] - wrist0[k] for k in "xyz"} for n, v in raw.items()}
    return {n: _remap(v) for n, v in centered.items()}


def build_hand_rig(lm, mats):
    """Construit le rig metaball (poignet/paume/doigts) a partir des
    landmarks d'une frame. Retourne la liste des objets Blender crees."""
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

    return all_meta_objects


def setup_camera_and_lights(scene, lm):
    """Cadrage automatique sur le centroide/etendue des landmarks de CETTE
    frame (la position/echelle depend de SCALE et de la capture, pas une pose
    "face camera" upright figee - cf. limites en tete de fichier)."""
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


def make_toon_material():
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
    return toon_mat


def configure_cycles_gpu(gpu_name_substring):
    """Restreint Cycles au(x) device(s) dont le nom contient
    gpu_name_substring (insensible a la casse). Seul mecanisme fiable trouve
    sur cette machine pour epingler un rendu a un GPU precis : la preference
    Windows "GPU par application" (registre UserGpuPreferences) ne redirige
    PAS le contexte OpenGL utilise par le moteur Workbench en mode headless
    (`-b`) - verifie empiriquement le 2026-07-29, le rendu restait sur la
    RTX 5080 malgre GpuPreference=1 (power saving). Cycles expose en
    revanche une liste de devices CUDA/OptiX activables individuellement,
    ce qui permet une exclusion fiable des autres GPU."""
    cprefs = bpy.context.preferences.addons['cycles'].preferences
    for device_type in ('OPTIX', 'CUDA'):
        cprefs.compute_device_type = device_type
        cprefs.get_devices()
        if cprefs.devices:
            break
    matched = []
    for d in cprefs.devices:
        if d.type == 'CPU':
            d.use = False
            continue
        use = gpu_name_substring.lower() in d.name.lower()
        d.use = use
        if use:
            matched.append(d.name)
    if not matched:
        available = [d.name for d in cprefs.devices if d.type != 'CPU']
        raise RuntimeError(
            f"Aucun device Cycles ne correspond a '{gpu_name_substring}' parmi {available}")
    print(f"[drive_from_landmarks] Cycles ({cprefs.compute_device_type}) restreint a : {matched}")
    return matched


def render_beauty(scene, out_path, engine, cycles_samples):
    scene.render.filepath = out_path
    if engine == 'cycles':
        scene.render.engine = 'CYCLES'
        scene.cycles.device = 'GPU'
        scene.cycles.samples = cycles_samples
    else:
        scene.render.engine = 'BLENDER_WORKBENCH'
        scene.display.shading.light = 'STUDIO'
        scene.display.shading.color_type = 'MATERIAL'
    bpy.ops.render.render(write_still=True)


def render_celshaded(scene, out_path, meta_objects, engine, cycles_samples):
    toon_mat = make_toon_material()
    for obj in meta_objects:
        obj.data.materials.clear()
        obj.data.materials.append(toon_mat)

    if engine == 'cycles':
        scene.render.engine = 'CYCLES'
        scene.cycles.device = 'GPU'
        scene.cycles.samples = cycles_samples
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

    scene.render.filepath = out_path
    bpy.ops.render.render(write_still=True)


def render_one_frame(data, frame_index, hand_index, out_dir, celshade, engine, cycles_samples):
    lm = extract_hand_for_frame(data, frame_index, hand_index)
    if lm is None:
        print(f"[drive_from_landmarks] frame {frame_index}: pas de main a l'index "
              f"{hand_index}, frame ignoree.")
        return False

    base.clear_scene()
    scene = bpy.context.scene
    mats = {idx: base.make_material(f"mat_{name}", col, idx)
            for idx, (name, col) in base.ID_CLASSES.items()}

    meta_objects = build_hand_rig(lm, mats)
    setup_camera_and_lights(scene, lm)

    scene.render.resolution_x = base.RES_X
    scene.render.resolution_y = base.RES_Y
    scene.render.film_transparent = False
    scene.render.image_settings.file_format = 'PNG'

    render_beauty(scene, os.path.join(out_dir, f"frame_{frame_index:04d}_beauty.png"), engine, cycles_samples)
    if celshade:
        render_celshaded(scene, os.path.join(out_dir, f"frame_{frame_index:04d}_celshaded.png"),
                          meta_objects, engine, cycles_samples)
    return True


def parse_args():
    # Blender consomme ses propres arguments avant "--" ; seuls ceux apres
    # "--" nous appartiennent (absents => mode 1-frame retro-compatible).
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--input", default=DEFAULT_LANDMARKS_JSON,
                     help="JSON produit par extract_hand_landmarks.py")
    ap.add_argument("--hand-index", type=int, default=0,
                     help="index de la main dans hands[] a piloter (0 = premiere main detectee par frame)")
    ap.add_argument("--start-frame", type=int, default=0)
    ap.add_argument("--end-frame", type=int, default=0,
                     help="derniere frame incluse (par defaut : identique a --start-frame, 1 seule frame)")
    ap.add_argument("--out-dir", default=DEFAULT_OUT_DIR)
    ap.add_argument("--no-celshade", action="store_true",
                     help="rend uniquement le beauty pass (plus rapide pour tester une sequence)")
    ap.add_argument("--engine", choices=["workbench", "cycles"], default="cycles",
                     help="'cycles' (defaut) permet d'epingler le rendu a un GPU precis "
                          "via --gpu-name ; 'workbench' reproduit le rendu de la PoC 1-frame "
                          "d'origine mais ignore --gpu-name (contexte OpenGL non pilotable, "
                          "cf. docstring configure_cycles_gpu)")
    ap.add_argument("--gpu-name", default="5060 Ti",
                     help="sous-chaine (insensible a la casse) du nom du device Cycles a utiliser "
                          "exclusivement, ex. '5060 Ti' - ignore si --engine workbench")
    ap.add_argument("--cycles-samples", type=int, default=32,
                     help="nombre d'echantillons Cycles (un guide de pose n'a pas besoin de "
                          "beaucoup de samples, defaut volontairement bas pour la vitesse)")
    return ap.parse_args(argv)


def main():
    args = parse_args()
    os.makedirs(args.out_dir, exist_ok=True)
    data = load_landmarks_json(args.input)

    if args.engine == "cycles":
        configure_cycles_gpu(args.gpu_name)

    end_frame = max(args.end_frame, args.start_frame)
    n_total = end_frame - args.start_frame + 1
    n_rendered = 0
    for frame_index in range(args.start_frame, end_frame + 1):
        if frame_index >= len(data["frames"]):
            print(f"[drive_from_landmarks] frame {frame_index} hors limites "
                  f"({len(data['frames'])} frame(s) dans {args.input}), arret.")
            break
        if render_one_frame(data, frame_index, args.hand_index, args.out_dir,
                             celshade=not args.no_celshade, engine=args.engine,
                             cycles_samples=args.cycles_samples):
            n_rendered += 1

    print(f"DONE. {n_rendered}/{n_total} frame(s) rendues dans {args.out_dir}")


if __name__ == "__main__":
    main()

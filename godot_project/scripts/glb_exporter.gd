extends Node
class_name GlbExporter

## H-005 : export runtime GLTFDocument.append_from_scene() + write_to_filesystem(),
## en GLB. Point critique connu (brief H-005) : l'export glTF runtime de Godot
## est centre sur le mesh et documente comme pouvant omettre silencieusement
## des pistes d'animation -- verifie explicitement par le test cote Python
## (verify_glb_animations.py), pas suppose.
##
## ATTENTION materiaux (warning connu godot-vrm) : dans un contexte editeur
## reel (pas ce harness de test synthetique), sauvegarder la scene avant
## export et la revert apres, systematiquement -- l'export peut modifier les
## materiaux de la scene live. Ce harness ne charge aucune scene .tscn
## editeur donc rien a revert ici ; a appliquer manuellement en production.

static func export_scene(root: Node, out_path: String) -> Dictionary:
	DirAccess.make_dir_recursive_absolute(out_path.get_base_dir())

	var gltf_document := GLTFDocument.new()
	var gltf_state := GLTFState.new()

	var append_err := gltf_document.append_from_scene(root, gltf_state, GLTFDocument.VISIBILITY_MODE_INCLUDE_OPTIONAL)
	if append_err != OK:
		return {"success": false, "error": "append_from_scene a echoue (err %d)" % append_err}

	var write_err := gltf_document.write_to_filesystem(gltf_state, out_path)
	if write_err != OK:
		return {"success": false, "error": "write_to_filesystem a echoue (err %d)" % write_err}

	return {"success": true, "error": ""}

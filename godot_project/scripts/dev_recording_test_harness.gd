extends Node3D

## H-005 -- rig de validation synthetique (PAS le flux de production final).
## Construit un Skeleton3D minimal (3 os) + une DirectorCamera en code,
## enregistre N ticks via PoseRecorder/CameraRecorder, exporte en GLB via
## GlbExporter, puis quitte. Objectif : verifier reellement si le "seam"
## d'export glTF documente (pistes d'animation silencieusement omises) se
## produit sur cette installation Godot -- sans attendre le vrai VRM (H-003).
##
## Lancer : Godot_v4.7.1-stable_win64_console.exe --headless --path .
##          res://scenes/dev_recording_test.tscn --quit-after 40
## Sortie : user://test_pose_animation.tres, user://test_camera_animation.tres,
##          user://test_export.glb -- chemin reel affiche via OS.get_user_data_dir().
## Verification : DOCS/HERMES/../../godot_project/tools/verify_glb_animations.py
## (script Python, pygltflib) sur le .glb produit.

const TICKS := 40
const DELTA := 1.0 / 30.0

var _skeleton: Skeleton3D
var _camera: Camera3D
var _pose_recorder: PoseRecorder
var _camera_recorder: CameraRecorder
var _tick := 0


func _ready() -> void:
	_build_rig()
	_pose_recorder = PoseRecorder.new()
	_pose_recorder.start(_skeleton, "Skeleton3D")
	_camera_recorder = CameraRecorder.new()
	_camera_recorder.start(_camera, "DirectorCamera")


func _build_rig() -> void:
	_skeleton = Skeleton3D.new()
	_skeleton.name = "Skeleton3D"
	add_child(_skeleton)

	var root_idx := _skeleton.add_bone("Root")
	_skeleton.set_bone_rest(root_idx, Transform3D.IDENTITY)

	var spine_idx := _skeleton.add_bone("Spine")
	_skeleton.set_bone_parent(spine_idx, root_idx)
	_skeleton.set_bone_rest(spine_idx, Transform3D(Basis(), Vector3(0, 0.5, 0)))

	var head_idx := _skeleton.add_bone("Head")
	_skeleton.set_bone_parent(head_idx, spine_idx)
	_skeleton.set_bone_rest(head_idx, Transform3D(Basis(), Vector3(0, 0.5, 0)))

	_camera = Camera3D.new()
	_camera.name = "DirectorCamera"
	_camera.transform.origin = Vector3(0, 1.5, 4)
	add_child(_camera)


func _process(delta: float) -> void:
	# _process (pas _physics_process) pour ce harness de TEST seulement --
	# en --headless sans vsync, les frames idle s'enchainent plus vite que
	# l'accumulateur de physics tick (60 Hz fixe), donc --quit-after N sur
	# des frames idle epuise le budget avant que N physics tick ne se soient
	# ecoules. PoseRecorder/CameraRecorder sont agnostiques de la boucle
	# appelante ; la production (player_controller.gd) reste sur
	# _physics_process comme demande par le brief.
	var head_idx := _skeleton.find_bone("Head")
	var angle := sin(_tick * 0.2) * 0.3
	_skeleton.set_bone_pose_rotation(head_idx, Quaternion(Vector3.RIGHT, angle))
	_camera.fov = 60.0 + sin(_tick * 0.1) * 10.0

	_pose_recorder.record_tick(delta)
	_camera_recorder.record_tick(delta)

	_tick += 1
	if _tick >= TICKS:
		_finish()


func _finish() -> void:
	_pose_recorder.finish("user://test_pose_animation.tres")
	_camera_recorder.finish("user://test_camera_animation.tres")

	var anim_player := AnimationPlayer.new()
	anim_player.name = "AnimationPlayer"
	add_child(anim_player)
	var lib := AnimationLibrary.new()
	var pose_anim: Animation = ResourceLoader.load("user://test_pose_animation.tres")
	lib.add_animation("pose_test", pose_anim)
	anim_player.add_animation_library("", lib)

	var result := GlbExporter.export_scene(self, "user://test_export.glb")
	print("GLB_EXPORT_RESULT:", JSON.stringify(result))
	print("USER_DATA_DIR:", OS.get_user_data_dir())

	get_tree().quit()

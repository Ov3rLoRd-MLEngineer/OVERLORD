extends Node3D

## H-007 -- capture de rendus multi-angles d'un personnage VRM (rotation de
## camera) pour bootstrap dataset LoRA. NON TESTE : aucun fichier .vrm
## n'existe encore (attend H-003). Ecrit par symetrie avec le rig de test
## H-005 (dev_recording_test_harness.gd) mais jamais execute en conditions
## reelles -- traiter comme un premier jet a valider des qu'un .vrm existe.
##
## Lancer (une fois un .vrm disponible) :
##   Godot_v4.7.1-stable_win64_console.exe --headless --path . \
##     res://scenes/dev_character_turnaround.tscn --quit-after 200 -- \
##     --vrm-path=res://assets/vrm/neko_girl.vrm \
##     --out-dir=D:/OVERLORD/workspace/character_lora_dataset/raw_renders \
##     --angle-steps=24

const VIEWPORT_SIZE := Vector2i(1024, 1024)

var _character: Node3D
var _camera: Camera3D
var _out_dir := "D:/OVERLORD/workspace/character_lora_dataset/raw_renders"
var _vrm_path := "res://assets/vrm/neko_girl.vrm"
var _angle_steps := 24
var _current_step := 0


func _ready() -> void:
	_parse_args()

	if not ResourceLoader.exists(_vrm_path):
		push_error("dev_character_turnaround_capture: VRM introuvable a %s -- H-003 pas encore livre ?" % _vrm_path)
		get_tree().quit(1)
		return

	var vrm_scene: PackedScene = ResourceLoader.load(_vrm_path)
	_character = vrm_scene.instantiate()
	add_child(_character)

	_camera = Camera3D.new()
	add_child(_camera)

	var light := DirectionalLight3D.new()
	light.rotation_degrees = Vector3(-45, 45, 0)
	add_child(light)

	DirAccess.make_dir_recursive_absolute(_out_dir)

	# Viewport hors-ecran pour un rendu deterministe independant de la fenetre.
	get_viewport().size = VIEWPORT_SIZE


func _parse_args() -> void:
	for arg in OS.get_cmdline_user_args():
		if arg.begins_with("--vrm-path="):
			_vrm_path = arg.get_slice("=", 1)
		elif arg.begins_with("--out-dir="):
			_out_dir = arg.get_slice("=", 1)
		elif arg.begins_with("--angle-steps="):
			_angle_steps = int(arg.get_slice("=", 1))


func _process(_delta: float) -> void:
	if _character == null:
		return
	if _current_step >= _angle_steps:
		get_tree().quit()
		return

	var angle := TAU * float(_current_step) / float(_angle_steps)
	var radius := 2.5
	_camera.transform.origin = Vector3(sin(angle) * radius, 1.2, cos(angle) * radius)
	_camera.look_at(Vector3(0, 1.0, 0), Vector3.UP)

	# Laisser un frame s'ecouler pour que la camera/le rendu se stabilisent
	# avant capture (evite de capturer une frame de transition).
	await get_tree().process_frame
	await get_tree().process_frame

	var image := get_viewport().get_texture().get_image()
	var out_path := "%s/angle_%03d.png" % [_out_dir, _current_step]
	var err := image.save_png(out_path)
	if err != OK:
		push_error("Echec sauvegarde %s (err %d)" % [out_path, err])

	_current_step += 1

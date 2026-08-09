extends Camera3D

## Camera libre "realisateur" (H-004), independante du personnage. Stick droit
## = orbite autour de la cible. L2/R2 = zoom -- choix fait ici : zoom via FOV
## (plus simple a cabler qu'un dolly avant/arriere qui devrait gerer les
## collisions camera/decor ; a revisiter si besoin d'un vrai travelling).

@export var target_path: NodePath
@export var orbit_speed := 2.0
@export var zoom_speed := 20.0
@export var min_fov := 20.0
@export var max_fov := 90.0
@export var distance := 4.0
@export var height := 1.5

var _yaw := 0.0
var _pitch := 0.0
var _target: Node3D


func _ready() -> void:
	if target_path != NodePath():
		_target = get_node(target_path)


func _physics_process(delta: float) -> void:
	var cam_input := Input.get_vector("cam_left", "cam_right", "cam_up", "cam_down")
	_yaw -= cam_input.x * orbit_speed * delta
	_pitch = clamp(_pitch - cam_input.y * orbit_speed * delta, -1.2, 1.2)

	var zoom_input := Input.get_action_strength("zoom_in") - Input.get_action_strength("zoom_out")
	fov = clamp(fov - zoom_input * zoom_speed * delta, min_fov, max_fov)

	if _target:
		var offset := Vector3(
			sin(_yaw) * cos(_pitch),
			sin(_pitch) + height,
			cos(_yaw) * cos(_pitch)
		) * distance
		global_position = _target.global_position + offset
		look_at(_target.global_position + Vector3(0, height * 0.5, 0), Vector3.UP)

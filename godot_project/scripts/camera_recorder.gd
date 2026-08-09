extends Node
class_name CameraRecorder

## H-005 : enregistre transform + FOV de la DirectorCamera a chaque tick,
## meme mecanisme de piste d'animation que PoseRecorder. Piste FOV en
## TYPE_VALUE (pas de track type dedie pour un scalaire de camera dans
## l'API Animation de base).

var _camera: Camera3D
var _track_base_path: String
var _animation: Animation
var _pos_track: int
var _rot_track: int
var _fov_track: int
var _time := 0.0


func start(camera: Camera3D, track_base_path: String) -> void:
	_camera = camera
	_track_base_path = track_base_path
	_time = 0.0
	_animation = Animation.new()

	_pos_track = _animation.add_track(Animation.TYPE_POSITION_3D)
	_animation.track_set_path(_pos_track, NodePath(_track_base_path))

	_rot_track = _animation.add_track(Animation.TYPE_ROTATION_3D)
	_animation.track_set_path(_rot_track, NodePath(_track_base_path))

	_fov_track = _animation.add_track(Animation.TYPE_VALUE)
	_animation.track_set_path(_fov_track, NodePath("%s:fov" % _track_base_path))


func record_tick(delta: float) -> void:
	_animation.position_track_insert_key(_pos_track, _time, _camera.transform.origin)
	_animation.rotation_track_insert_key(_rot_track, _time, _camera.transform.basis.get_rotation_quaternion())
	_animation.track_insert_key(_fov_track, _time, _camera.fov)
	_time += delta
	_animation.length = _time


func finish(out_path: String) -> Animation:
	DirAccess.make_dir_recursive_absolute(out_path.get_base_dir())
	var err := ResourceSaver.save(_animation, out_path)
	if err != OK:
		push_error("CameraRecorder.finish: echec sauvegarde %s (err %d)" % [out_path, err])
	return _animation

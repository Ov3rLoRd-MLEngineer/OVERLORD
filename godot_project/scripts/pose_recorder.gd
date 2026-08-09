extends Node
class_name PoseRecorder

## H-005 : enregistre les poses des os d'un Skeleton3D a chaque tick physics
## (Skeleton3D.get_bone_pose()) dans une Animation Godot (pistes position +
## rotation par os), sauvegardee en .tres (texte, diff-able) via
## ResourceSaver.save(). Path des pistes relatif au node passe en argument de
## start() -- doit correspondre au root_node de l'AnimationPlayer qui jouera
## l'animation (typiquement le parent commun du Skeleton3D et du player).

var _skeleton: Skeleton3D
var _track_base_path: String
var _animation: Animation
var _pos_tracks: Dictionary = {}
var _rot_tracks: Dictionary = {}
var _time := 0.0


func start(skeleton: Skeleton3D, track_base_path: String) -> void:
	_skeleton = skeleton
	_track_base_path = track_base_path
	_time = 0.0
	_animation = Animation.new()
	_pos_tracks.clear()
	_rot_tracks.clear()

	for i in range(_skeleton.get_bone_count()):
		var bone_name := _skeleton.get_bone_name(i)

		var pos_idx := _animation.add_track(Animation.TYPE_POSITION_3D)
		_animation.track_set_path(pos_idx, NodePath("%s:%s" % [_track_base_path, bone_name]))
		_pos_tracks[i] = pos_idx

		var rot_idx := _animation.add_track(Animation.TYPE_ROTATION_3D)
		_animation.track_set_path(rot_idx, NodePath("%s:%s" % [_track_base_path, bone_name]))
		_rot_tracks[i] = rot_idx


func record_tick(delta: float) -> void:
	for i in range(_skeleton.get_bone_count()):
		var pose := _skeleton.get_bone_pose(i)
		_animation.position_track_insert_key(_pos_tracks[i], _time, pose.origin)
		_animation.rotation_track_insert_key(_rot_tracks[i], _time, pose.basis.get_rotation_quaternion())
	_time += delta
	_animation.length = _time


func finish(out_path: String) -> Animation:
	DirAccess.make_dir_recursive_absolute(out_path.get_base_dir())
	var err := ResourceSaver.save(_animation, out_path)
	if err != OK:
		push_error("PoseRecorder.finish: echec sauvegarde %s (err %d)" % [out_path, err])
	return _animation

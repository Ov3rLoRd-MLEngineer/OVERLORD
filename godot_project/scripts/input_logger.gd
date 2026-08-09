extends Node
class_name InputLogger

## H-005 : log JSON des inputs manette + transform/vitesse du personnage par
## tick physics (secondaire -- pour du behavior cloning ulterieur).

var _entries: Array = []
var _time := 0.0


func log_tick(delta: float, player: CharacterBody3D, anim_state: String = "") -> void:
	var move_input := Input.get_vector("move_left", "move_right", "move_forward", "move_back")
	_entries.append({
		"t": _time,
		"move_input": {"x": move_input.x, "y": move_input.y},
		"zoom_in": Input.get_action_strength("zoom_in"),
		"zoom_out": Input.get_action_strength("zoom_out"),
		"position": {"x": player.global_position.x, "y": player.global_position.y, "z": player.global_position.z},
		"velocity": {"x": player.velocity.x, "y": player.velocity.y, "z": player.velocity.z},
		"anim_state": anim_state,
	})
	_time += delta


func finish(out_path: String) -> void:
	DirAccess.make_dir_recursive_absolute(out_path.get_base_dir())
	var f := FileAccess.open(out_path, FileAccess.WRITE)
	if f == null:
		push_error("InputLogger.finish: echec ouverture %s" % out_path)
		return
	f.store_string(JSON.stringify(_entries, "  "))
	f.close()

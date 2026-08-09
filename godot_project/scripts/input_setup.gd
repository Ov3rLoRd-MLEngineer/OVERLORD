extends Node

## Autoload (H-004) : enregistre les InputMap actions au demarrage, avec
## fallback clavier pour le dev sans manette branchee sur la machine de dev
## (cf. brief H-004, etape 5). S'execute avant le _ready() des autres nodes
## puisque c'est un autoload.

func _init() -> void:
	_register_axis_pair("move_left", "move_right", JOY_AXIS_LEFT_X, KEY_A, KEY_D)
	_register_axis_pair("move_forward", "move_back", JOY_AXIS_LEFT_Y, KEY_W, KEY_S)
	_register_axis_pair("cam_left", "cam_right", JOY_AXIS_RIGHT_X, KEY_LEFT, KEY_RIGHT)
	_register_axis_pair("cam_up", "cam_down", JOY_AXIS_RIGHT_Y, KEY_UP, KEY_DOWN)
	_register_trigger("zoom_in", JOY_AXIS_TRIGGER_RIGHT, KEY_E)
	_register_trigger("zoom_out", JOY_AXIS_TRIGGER_LEFT, KEY_Q)


func _register_axis_pair(neg_action: String, pos_action: String, axis: JoyAxis, neg_key: Key, pos_key: Key) -> void:
	for action in [neg_action, pos_action]:
		if not InputMap.has_action(action):
			InputMap.add_action(action)

	var neg_axis_event := InputEventJoypadMotion.new()
	neg_axis_event.axis = axis
	neg_axis_event.axis_value = -1.0
	InputMap.action_add_event(neg_action, neg_axis_event)

	var pos_axis_event := InputEventJoypadMotion.new()
	pos_axis_event.axis = axis
	pos_axis_event.axis_value = 1.0
	InputMap.action_add_event(pos_action, pos_axis_event)

	var neg_key_event := InputEventKey.new()
	neg_key_event.physical_keycode = neg_key
	InputMap.action_add_event(neg_action, neg_key_event)

	var pos_key_event := InputEventKey.new()
	pos_key_event.physical_keycode = pos_key
	InputMap.action_add_event(pos_action, pos_key_event)


func _register_trigger(action: String, axis: JoyAxis, fallback_key: Key) -> void:
	if not InputMap.has_action(action):
		InputMap.add_action(action)

	var axis_event := InputEventJoypadMotion.new()
	axis_event.axis = axis
	axis_event.axis_value = 1.0
	InputMap.action_add_event(action, axis_event)

	var key_event := InputEventKey.new()
	key_event.physical_keycode = fallback_key
	InputMap.action_add_event(action, key_event)

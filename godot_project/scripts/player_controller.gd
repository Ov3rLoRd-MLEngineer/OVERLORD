extends CharacterBody3D

## Controleur personnage (H-004). Stick gauche = deplacement (Input.get_vector()).
## Gravite + collision basiques. Le mesh/squelette VRM (une fois H-003 livre)
## doit etre instancie sous le nœud "VrmSlot", enfant de ce CharacterBody3D --
## remplacer alors la CapsuleMesh placeholder par le mesh VRM importe.

const SPEED := 4.0
const GRAVITY := 9.8

func _physics_process(delta: float) -> void:
	if not is_on_floor():
		velocity.y -= GRAVITY * delta

	var input_dir := Input.get_vector("move_left", "move_right", "move_forward", "move_back")
	var direction := (transform.basis * Vector3(input_dir.x, 0.0, input_dir.y)).normalized()

	if direction:
		velocity.x = direction.x * SPEED
		velocity.z = direction.z * SPEED
	else:
		velocity.x = move_toward(velocity.x, 0.0, SPEED)
		velocity.z = move_toward(velocity.z, 0.0, SPEED)

	move_and_slide()

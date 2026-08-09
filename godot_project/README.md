# Ov3rLoRd World Controller — sous-projet Godot

Sous-projet Godot pour le contrôleur perso/caméra du World (H-001, brief `DOCS/HERMES/OUTBOX/H-001_setup_godot_vrm.md`). Charge un modèle VRM et l'affiche dans une scène 3D ; base pour le contrôleur manette (H-004) et le recorder de poses (H-005).

## Versions

- **Godot** : 4.7.1-stable (build officiel win64 portable, standard/non-Mono)
- **Plugin VRM** : [AzPepoze/godot-vrm](https://github.com/AzPepoze/godot-vrm), tag `v2.5.9` (release zip, GDExtension C++)

Le fork AzPepoze est utilisé en priorité (perfs physiques meilleures que V-Sekai/godot-vrm d'origine, `godot-vrm` confirmé "Available for Godot 4.3+" sur ce fork). Aucun repli sur V-Sekai n'a été nécessaire — l'installation s'est faite sans blocage.

## Emplacements

- Moteur Godot (portable, non versionné — voir `.gitignore` racine du dépôt) : `D:\OVERLORD\_tools\Godot\Godot_v4.7.1-stable_win64.exe`
- Ce projet : `D:\OVERLORD\godot_project\`

## Lancer le projet

```
D:\OVERLORD\_tools\Godot\Godot_v4.7.1-stable_win64.exe --path D:\OVERLORD\godot_project
```

Ou double-clic sur l'exe puis "Importer" en pointant sur `D:\OVERLORD\godot_project\project.godot`.

## Structure

```
godot_project/
├── project.godot
├── addons/
│   ├── vrm/       # AzPepoze/godot-vrm v2.5.9 — importeur VRM + GDExtension physique
│   └── mtoon/     # Shader MToon (dépendance du plugin VRM)
├── assets/vrm/    # Fichier .vrm du personnage — pas encore fourni, attend H-003
├── scenes/
│   ├── test_scene.tscn          # Sol + Player (CharacterBody3D) + DirectorCamera + VrmSlot
│   └── dev_recording_test.tscn  # H-005 -- rig de test synthetique (PAS la production), voir plus bas
├── scripts/
│   ├── input_setup.gd              # Autoload -- InputMap actions (manette + clavier fallback)
│   ├── player_controller.gd        # CharacterBody3D -- deplacement stick gauche, gravite, collision
│   ├── director_camera.gd          # Camera3D libre -- orbite stick droit, zoom FOV L2/R2
│   ├── pose_recorder.gd            # H-005 -- enregistre les poses Skeleton3D en Animation .tres
│   ├── camera_recorder.gd          # H-005 -- idem pour transform+FOV de la DirectorCamera
│   ├── input_logger.gd             # H-005 -- log JSON inputs manette + transform/velocite (secondaire)
│   ├── glb_exporter.gd             # H-005 -- export runtime GLTFDocument -> GLB
│   └── dev_recording_test_harness.gd  # H-005 -- pilote le rig de test synthetique
└── tools/
    └── verify_glb_animations.py    # H-005 -- verification post-export (pygltflib) du GLB produit
```

## État actuel

Aucun fichier `.vrm` n'existe encore (dépend de H-003 — création du personnage sous VRoid Studio). `scenes/test_scene.tscn` contient un `CharacterBody3D` nommé `Player` avec une capsule placeholder (mesh + collision) et un nœud `VrmSlot` en enfant, point d'ancrage pour instancier la scène VRM importée une fois le `.vrm` disponible (voir `assets/vrm/PLACEHOLDER.md`) — remplacer alors la capsule par le mesh VRM.

Validation faite sans VRM réel :
- Mode éditeur headless (`--headless --editor --quit`) : aucune erreur bloquante, les deux plugins (`vrm`, `mtoon`) s'activent et enregistrent leurs classes (`VRMInstance`, `VRMSpringBone`, `VRMConstraint`, `VRMConstraintApplier`, etc.).
- Mode jeu headless 30 frames (`--headless --quit-after 30`) : `Player` tombe sous gravité et se pose sur le sol (`Ground`, `StaticBody3D`) sans erreur, `DirectorCamera` orbite sans crash — confirme que le mécanisme (gravité, collision, `InputMap`, `Input.get_vector()`) fonctionne techniquement.
- **Non testé** : ressenti manette/clavier réel en interactif (fenêtre visible, joystick physique) — nécessite un lancement manuel par l'utilisateur, pas reproductible en CLI headless.

### Contrôleur & caméra (H-004)

- **Personnage** (`player_controller.gd`) : stick gauche = déplacement via `Input.get_vector("move_left","move_right","move_forward","move_back")`, gravité + `move_and_slide()`. Fallback clavier WASD (voir `input_setup.gd`).
- **Caméra réalisateur** (`director_camera.gd`) : `Camera3D` indépendante du personnage, stick droit = orbite (yaw/pitch), L2/R2 = **zoom via FOV** (choix documenté — plus simple qu'un dolly avant/arrière qui devrait gérer les collisions caméra/décor ; à revisiter si un vrai travelling est nécessaire). Fallback clavier flèches + E/Q.
- **Retargeting Mixamo** : non testé — aucune animation Mixamo n'est encore utilisée (pas de locomotion importée à ce stade). Méthode retenue documentée pour la suite : Bone Map manuel (Advanced Import → Skeleton3D → Bone Map → New BoneMap → Profile `SkeletonProfileHumanoid`), **pas** l'addon AssetLib `mixamo_animation_retargeter` (jugé peu fiable) ; `RaidTheory/Godot-Mixamo-Animation-Retargeter` en repli si un addon est nécessaire. À appliquer et vérifier dès qu'une première animation Mixamo entre dans le projet.
- **`VRMC_node_constraint`** : toujours non testable en conditions réelles (pas de VRM + animation retargetée) — voir section Limitations.

### Recorder de poses + export GLB (H-005)

Aucun VRM/squelette réel n'existant encore, la vérification du seam glTF documenté (brief H-005) a été faite avec un **rig synthétique** (`scripts/dev_recording_test_harness.gd`) : `Skeleton3D` de 3 os (Root/Spine/Head) construit en code, tête animée par une rotation procédurale sur 40 ticks, `PoseRecorder`/`CameraRecorder` enregistrent les poses en `Animation` (.tres), `GlbExporter` exporte en GLB (`GLTFDocument.append_from_scene` + `write_to_filesystem`, flag `VISIBILITY_MODE_INCLUDE_OPTIONAL`).

**Lancer le test** :
```
Godot_v4.7.1-stable_win64_console.exe --headless --path . res://scenes/dev_recording_test.tscn --quit-after 60
```
Sort 3 fichiers dans `user://` (`%APPDATA%\Godot\app_userdata\Ov3rLoRd World Controller\`) : `test_pose_animation.tres`, `test_camera_animation.tres`, `test_export.glb`.

**Vérification** (`tools/verify_glb_animations.py`, `pygltflib`) :
```
py -3.12 godot_project/tools/verify_glb_animations.py "<user_data_dir>/test_export.glb"
```

**Verdict réel obtenu (2026-08-09) : export animations OK.** Les 6 canaux attendus (translation + rotation pour Root/Spine/Head) sont bien présents et correctement ciblés dans le GLB exporté — pas de piste manquante sur ce rig synthétique.

**Portée du test — ce qui n'est PAS couvert** (à ne pas présenter comme validé) :
- Aucun **mesh skinné** n'est impliqué (`Skins: 0` dans la sortie du script) — le rig ne contient qu'un squelette + animation, pas de géométrie liée par poids de skin. Le vrai risque de seam documenté concerne potentiellement la combinaison squelette+mesh skinné+animation d'un VRM réel, code path différent et non exercé ici.
- L'animation de la `DirectorCamera` (`test_camera_animation.tres`) est bien sauvegardée mais n'a **pas** été ajoutée à l'`AnimationPlayer` exporté dans ce test — seule la piste de pose du squelette a été vérifiée dans le GLB. Le mécanisme est identique (même `Animation`/`AnimationPlayer`), donc a priori sans risque supplémentaire, mais non vérifié séparément.
- Le warning "export destructif sur les matériaux de la scène" (godot-vrm) n'a pas pu être exercé (rig construit en code, aucune scène `.tscn` éditeur avec matériaux réels à sauvegarder/revert). **À refaire avec sauvegarde/revert systématique une fois un VRM réel en place.**

**À refaire dès que H-003 livre un `.vrm` réel** : réexécuter ce protocole (rig réel au lieu du synthétique, mesh skinné inclus, sauvegarde/revert de la scène autour de l'export) avant de considérer le seam glTF définitivement écarté pour la production. Si un vrai seam apparaît à ce moment, bascule VMC (Godot→VMC→VMC4B Blender) recommandée par le brief, budget max ~2-3 jours de debug avant de basculer.

### LoRA personnage (H-007) — bloqué, non exécuté

**Deux blocages distincts, aucun contournable sans action humaine :**
1. **H-003 non livrée** — aucun fichier `.vrm` n'existe (`assets/vrm/` vide). Sans lui, aucun rendu multi-angle possible, donc aucun dataset, donc aucun entraînement réel.
2. **`kohya_ss` non installé** — `agents/production_image/lora_trainer.py` (script d'entraînement LoRA **déjà existant** dans le dépôt, rank 32/`network_dim=32` par défaut, checkpoint `fabricatedXL_v70.safetensors`) attend `D:\kohya_ss\train_network.py`, absent de cette machine au 2026-08-09. Ce blocage existerait même si H-003 était livrée aujourd'hui.

**Ce qui a été écrit** (code réel, syntaxiquement validé, **jamais exécuté de bout en bout** faute de VRM) :
- `scripts/dev_character_turnaround_capture.gd` — orbite une caméra autour du VRM importé, capture N angles en PNG (viewport headless).
- `agents/production_image/generate_character_dataset.py` — orchestration : capture Godot → stylisation fabricatedXL (workflow ComfyUI à fournir explicitement via `--workflow`, aucun node ID deviné) → écriture du dataset au format attendu par `lora_trainer.py::prepare_dataset()`.

**Pas de nouveau script d'entraînement écrit** — `agents/production_image/lora_trainer.py` existant fait déjà rank 32 par défaut ; dupliquer aurait été contraire aux conventions du dépôt (voir `CLAUDE.md`). Une fois le dataset généré, l'enchaînement est : `prepare_dataset()` → `auto_tag_images()` → `train_lora()` → `integrate_lora()` (nécessite `kohya_ss` installé au préalable).

**Token de déclenchement proposé** : `nekogirl_ov3rlord` (repris de l'exemple du brief H-007). Vérifié sans collision contre les LoRA déjà installées (`D:\Ov3rLoRd AI\ComfyUI\models\loras\` — Evangelion/Miku/Gundam, aucun `nekogirl`/`ov3rlord` existant, 2026-08-09). **À valider explicitement avant tout usage réel** — c'est une proposition, pas une décision prise.

**Test des poids (0.5 / 0.75 / 1.0)** demandé par le brief : non fait, nécessite une LoRA réellement entraînée. Méthode prévue une fois disponible : génération via l'API ComfyUI (même convention `queue_prompt`/`history` que `agent_supervisor_v2.py`) à chaque poids, comparaison visuelle manuelle.

**GPU** : `lora_trainer.py` ne pin explicitement aucun device CUDA (aucun `cuda:0`/`CUDA_VISIBLE_DEVICES` dans le script) — repose sur le défaut `cuda:0` de torch/kohya_ss, qui correspond à la RTX 5080 sur cette machine (convention établie, cf. `CLAUDE.md`). Cohérent avec l'exigence du brief ("pas la 5060 Ti"), mais implicite — à vérifier via `nvidia-smi` au premier vrai run plutôt que supposé.

## Limitations connues

- **Icônes d'éditeur du plugin VRM en erreur d'import** : `vrm_constraint.svg`, `vrm_constraint_applier.svg`, `vrm_instance.svg` échouent au chargement/import (`ERROR: Error loading image` / `ERROR: Error importing`) sur ce build Godot 4.7.1 standard. Purement cosmétique — n'empêche pas le plugin de fonctionner (classes bien enregistrées, import VRM opérationnel) — juste l'icône de ces 3 types de nœuds dans l'éditeur qui restera l'icône générique.
- **Spring bones physics** : implémentées côté natif (GDExtension, `addons/vrm/bin/libvrm_physics.windows.template_{debug,release}.x86_64.dll`), les deux templates Windows sont présents. Non testées faute de fichier `.vrm` réel — à vérifier dès que H-003 livre un modèle.
- **`VRMC_node_constraint`** : implémenté côté script (`VRMConstraint` / `VRMConstraintApplier`, classes enregistrées sans erreur à l'activation du plugin). Le bug documenté (combinaison avec le retargeting, cf. brief H-001/H-004) n'a **pas pu être testé** ici — aucune animation/retargeting en jeu à ce stade, aucun `.vrm` disponible. À vérifier explicitement en H-004 dès qu'un modèle + animations Mixamo retargetées seront en place.

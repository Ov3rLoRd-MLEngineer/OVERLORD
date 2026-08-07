# Bugfix (constat) — cube par défaut Blender

Date : 2026-08-06
Origine : consignes.txt (point 1) — "supprimer le cube par défaut à l'initialisation de la scène".

## Constat

`agents/production_video/blender_previz.py::clear_scene()` (ligne 66-67) appelle déjà :

```python
def clear_scene():
    bpy.ops.wm.read_factory_settings(use_empty=True)
```

`use_empty=True` réinitialise sur une scène **vide** (pas les préférences factory par défaut avec cube/caméra/lumière). Aucun objet résiduel (cube, caméra default, lumière default) n'est donc créé — le décor (`setup_decor_minimal`), les lumières (`setup_three_point_lighting`) et la caméra (`setup_shot_camera`/`setup_animated_camera`) sont recréés explicitement à chaque appel, pour les deux modes (`duo` et `mmd`).

Aucune occurrence de `primitive_cube_add` ni de scène par défaut ailleurs dans le fichier (grep vérifié).

## Vérification

Inspection visuelle de `DEMO/frames/keyframes/keyframe_source_v4.png` (rendu previz réel, mode `mmd`, généré par la boucle autonome en cours) : fond dégradé uni (`setup_decor_minimal`), personnage MMD seul, aucun cube visible.

## Conclusion

Ce point était déjà résolu par le code existant au moment de la consigne — pas de changement nécessaire. Aucune régression trouvée sur les 4 keyframes déjà produits par la boucle (v2 à v5).

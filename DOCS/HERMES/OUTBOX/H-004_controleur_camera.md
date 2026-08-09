ID: H-004 | LLM cible: Claude Code | Date: 09/08/2026

CONTEXTE (autoportant)
Suite de H-001 (setup Godot 4.3+ + plugin AzPepoze/godot-vrm, projet initialisé). Objectif : contrôleur de personnage jouable au gamepad + caméra libre type "réalisateur", tous deux nécessaires avant H-005 (enregistrement des poses/caméra). Rien n'est encore enregistré à ce stade — c'est uniquement le contrôle temps réel.

TÂCHE
1. Personnage : `CharacterBody3D` piloté manette, stick gauche = déplacement (avec `Input.get_vector()`), gravité + collision basiques. Le mesh/squelette VRM chargé en H-001 doit être piloté par ce controller.
2. Caméra : `Camera3D` libre séparée du personnage ("caméra réalisateur"), stick droit = orbite autour du perso, L2/R2 = zoom ou FOV (au choix, documenter lequel).
3. Retargeting Mixamo AVANT tout enregistrement futur : si des animations Mixamo sont utilisées pour la locomotion (idle/marche/course), les retargeter via Bone Map + `SkeletonProfileHumanoid` (Advanced Import → Skeleton3D → Bone Map → New BoneMap → Profile SkeletonProfileHumanoid) — PAS via l'addon `mixamo_animation_retargeter` de l'AssetLib, jugé peu fiable ; utiliser la méthode manuelle Bone Map, ou si besoin d'un addon, `RaidTheory/Godot-Mixamo-Animation-Retargeter`.
4. Vérifier explicitement si les animations utilisées font intervenir `VRMC_node_constraint` (connu buggé avec le retargeting dans godot-vrm) — si oui, documenter le comportement observé avant de continuer.
5. Scène de test jouable : lancer le projet, déplacer le perso au clavier/manette (clavier acceptable en dev si pas de manette branchée sur la machine de dev), orbiter la caméra.

FORMAT DE RETOUR ATTENDU
Scripts GDScript (contrôleur + caméra) + note sur la méthode de retargeting utilisée + verdict sur `VRMC_node_constraint`.

CE QUE TU NE DOIS PAS FAIRE
- Ne pas inventer de chemins de fichiers hors de ceux établis dans H-001.
- Ne pas committer/pousser sans confirmation explicite.
- Ne pas implémenter l'enregistrement des poses/caméra ni l'export GLB — c'est H-005, hors scope ici.
- Ne pas utiliser l'addon `mixamo_animation_retargeter` de l'AssetLib sans signaler explicitement le choix (jugé peu fiable en retour de terrain).

ID: H-005 | LLM cible: Claude Code | Date: 09/08/2026

CONTEXTE (autoportant)
Suite de H-001 (setup Godot+godot-vrm) et H-004 (contrôleur manette+caméra libre), tous deux supposés terminés. Godot 4.3+, plugin AzPepoze/godot-vrm. Objectif : enregistrer en runtime, EN PARALLÈLE, (a) les poses des os du personnage pilotées à la manette, (b) le transform+FOV de la caméra libre, (c) un log JSON des inputs manette (pour du behavior cloning ultérieur, secondaire). Puis exporter le tout en GLB pour import dans Blender.

Point critique connu : l'export glTF runtime de Godot est centré sur le mesh et documenté comme pouvant omettre silencieusement des pistes d'animation, avec des orientations d'os qui diffèrent à la ré-import dans Blender. C'est le maillon fragile de toute la chaîne — le vérifier explicitement, pas supposer que ça marche.

TÂCHE
1. Enregistrement des poses : utiliser `Skeleton3D.get_bone_pose()` (ou `get_bone_global_pose()`) appelé à chaque tick physics, construire une `Animation` Godot avec des pistes Transform 3D par os, sauvegarder via `ResourceSaver.save()`. Sauvegarder en `.tres` (texte, diff-able) plutôt qu'en `.res` binaire (défaut) — utile pour debug.
2. Enregistrement caméra : transform + FOV par tick, même mécanisme de piste d'animation.
3. Log JSON inputs manette : `Input.get_vector()` + états boutons + transform/vélocité du personnage + état d'animation, par `_physics_process`, un fichier JSON/CSV par session d'enregistrement.
4. Export runtime : `GLTFDocument.append_from_scene()` + `write_to_filesystem()`, en GLB, flag `VISIBILITY_MODE_INCLUDE_OPTIONAL`, mesh attaché. ATTENTION : l'export est destructif sur les matériaux de la scène (warning connu de godot-vrm) — sauvegarder la scène avant export et la revert après, systématiquement.
5. Vérification obligatoire post-export : ouvrir le GLB produit et confirmer explicitement que les pistes d'animation sont bien présentes (pas seulement le mesh). Documenter la méthode de vérification utilisée.
6. Si l'étape 5 échoue après un essai raisonnable de correctifs (≈2-3 jours, pas plus) : NE PAS s'acharner. Documenter l'échec précisément (quelles pistes manquent, quels os sont affectés) et signaler que le fallback VMC (pont VMC vers VMC4B dans Blender, brief séparé à écrire si besoin) doit être envisagé plutôt que de continuer à déboguer le seam glTF.

FORMAT DE RETOUR ATTENDU
Scripts/nodes Godot créés (GDScript) + procédure de vérification du GLB + verdict clair : "export animations OK" ou "seam glTF confirmé, bascule VMC recommandée".

CE QUE TU NE DOIS PAS FAIRE
- Ne pas inventer de chemins de fichiers hors de ceux établis dans H-001.
- Ne pas committer/pousser sans confirmation explicite.
- Ne pas passer plus de 2-3 jours à déboguer le seam d'export avant de remonter le problème — pas d'acharnement silencieux.
- Ne pas implémenter le pont VMC ici si le GLB fonctionne — hors scope tant que ce n'est pas nécessaire.

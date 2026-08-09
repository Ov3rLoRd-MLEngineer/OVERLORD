ID: H-007 | LLM cible: Claude Code / Aider (script d'entraînement) | Date: 09/08/2026

CONTEXTE (autoportant)
Projet Ov3rLoRd, pipeline SDXL (fabricatedXL_v70.safetensors, taesdxl VAE, dpmpp_2m_sde/karras, CFG 7.0, 35 steps). H-003 (création de la neko girl originale sous VRoid Studio, export VRM) est supposée terminée : le personnage existe en 3D. Objectif ici : entraîner un LoRA rank 32 de ce personnage pour l'injecter dans le pipeline SDXL de génération d'images (démo J1 ET World J3).

TÂCHE
1. Dataset : script pour générer/organiser des rendus multi-angles du personnage depuis le modèle VRoid (rotations de la caméra autour du perso, plusieurs expressions/poses si le rig VRoid le permet), puis passage par le pipeline de stylisation fabricatedXL existant pour obtenir des images d'entraînement stylisées cohérentes avec le reste du pipeline (pas des rendus 3D bruts).
2. Nettoyage/format du dataset : résolution cohérente, captions courtes (déclencheur de token dédié pour le personnage, à choisir et documenter clairement — ex. "nekogirl_ov3rlord" ou équivalent, jamais un nom qui entre en collision avec un token existant du pipeline).
3. Script d'entraînement LoRA rank 32 sur RTX 5080 (GPU d'entraînement préféré du pipeline, PAS la 5060 Ti — confirmé plus rapide pour ce type d'entraînement). Durée cible 1-4h.
4. Sortie : fichier LoRA safetensors + quelques images de test générées avec le LoRA appliqué à différents poids (0.5, 0.75, 1.0) pour valider la fidélité du personnage.

FORMAT DE RETOUR ATTENDU
Scripts (génération dataset + entraînement) + rapport court sur la taille finale du dataset et les résultats des tests de poids.

CE QUE TU NE DOIS PAS FAIRE
- Ne pas inventer de chemins de fichiers, de noms de fonctions ou de conventions du dépôt non données ci-dessus.
- Ne pas committer/pousser sans confirmation explicite.
- Ne pas utiliser la RTX 5060 Ti pour l'entraînement — GPU 0 (RTX 5080) réservé à ce type de tâche.
- Ne pas choisir un token de déclenchement sans le signaler explicitement pour validation (risque de collision avec un token existant du pipeline).

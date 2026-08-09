ID: H-001 | LLM cible: Claude Code | Date: 09/08/2026

CONTEXTE (autoportant)
Projet Ov3rLoRd (studio Onibaku Gumi), racine dépôt D:\OVERLORD\. Nouveau sous-projet Godot pour le contrôleur perso/caméra du World (démo Mistral, jalon J1 = 31/08/2026). Moteur retenu : Godot 4 (4.3+ requis). Plugin d'import VRM : godot-vrm, fork AzPepoze si la version stable ne supporte pas Godot 4.3+. Objectif de cette tâche : avoir une base Godot fonctionnelle qui charge un modèle VRM et l'affiche dans une scène 3D, prête à recevoir contrôleur/caméra (tâche H-004, brief séparé) et recorder de poses (H-005, brief séparé) plus tard.

TÂCHE
1. Proposer une structure de dossier pour ce sous-projet sous D:\OVERLORD\ (ex. D:\OVERLORD\godot_project\) et la soumettre avant toute création de fichier.
2. Initialiser un projet Godot 4.3+ (ou version compatible la plus récente disponible).
3. Intégrer le plugin VRM **AzPepoze/godot-vrm** (fork actif, GDExtension C++, meilleures perfs physiques que le dépôt V-Sekai d'origine — à utiliser en priorité vu Godot 4.3+). Si ce fork pose un problème bloquant, se rabattre sur V-Sekai/godot-vrm et le signaler explicitement.
4. Créer une scène de test qui charge un fichier .vrm placé dans un dossier assets dédié (le fichier VRM lui-même n'existe pas encore — placeholder acceptable, il sera fourni séparément une fois H-003 terminée).
5. Tester tôt si le modèle/les animations utilisées font intervenir `VRMC_node_constraint` — connu comme buggé en combinaison avec le retargeting dans godot-vrm. Signaler si c'est le cas.
6. Documenter dans un court README.md du sous-projet : version Godot utilisée, source du plugin VRM (dépôt + commit/tag), commande pour lancer le projet, limitations connues (spring bones physics, `VRMC_node_constraint`).

FORMAT DE RETOUR ATTENDU
Diff/liste des fichiers créés + le README.md complet en clair dans la réponse (pas seulement un chemin).

CE QUE TU NE DOIS PAS FAIRE
- Ne pas inventer de chemins de fichiers hors de ce qui est proposé et validé à l'étape 1.
- Ne pas committer/pousser sans confirmation explicite.
- Ne pas tenter d'implémenter le contrôleur manette, la caméra, ou le recorder de poses ici — hors scope de ce brief (voir H-004/H-005).
- Ne pas choisir une version Godot < 4.3 sans le signaler explicitement comme compromis.

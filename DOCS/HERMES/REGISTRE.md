# Registre Hermes

Priorisé le 09/08/2026. Vague = ordre d'exécution. Statuts : 📋 à faire · ⏳ en cours · ✅ fait · ❌ bloqué.

## Vague 1 — à lancer en parallèle, aucune dépendance

| ID | Vague | LLM cible | Tâche | Jalon | Dépend de | Statut | Fichier retour |
|---|---|---|---|---|---|---|---|
| H-003 | 1 | Manuel (Jérémy, VRoid Studio) | Création neko girl VRoid → export VRM | J1/S1 | — | 📋 | |
| H-001 | 1 | Claude Code | Setup projet Godot + import godot-vrm | J1/S1 | — | ✅ | `godot_project/README.md` |
| H-002 | 1 | Claude Code (ou DeepSeek 1er jet) | Timing module v1 (PySceneDetect+frame-diff+QwenVL) | J1/S1 | — | ✅ | `agents/timing_analysis.py` |

## Vague 2 — dès qu'une dépendance de vague 1 est prête

| ID | Vague | LLM cible | Tâche | Jalon | Dépend de | Statut | Fichier retour |
|---|---|---|---|---|---|---|---|
| H-004 | 2 | Claude Code | Contrôleur manette + caméra libre Godot | J1/S1 | H-001 | ✅ | `godot_project/README.md` (test interactif manette/clavier reel encore a faire par l'utilisateur) |
| H-007 | 2 | Claude Code / Aider | LoRA personnage (dataset VRoid+fabricatedXL, rank 32, 5060 Ti) | J1/S1-S2 | H-003 | ❌ | `godot_project/README.md` -- bloque : H-003 non livree (aucun .vrm) ET kohya_ss non installe (D:/kohya_ss absent). Scripts ecrits (capture Godot + generate_character_dataset.py) mais jamais executes de bout en bout. Reutilise agents/production_image/lora_trainer.py existant (deja rank 32) plutot qu'un nouveau script d'entrainement. |

## Vague 3

| ID | Vague | LLM cible | Tâche | Jalon | Dépend de | Statut | Fichier retour |
|---|---|---|---|---|---|---|---|
| H-005 | 3 | Claude Code | Recorder de poses + export GLB (VISIBILITY_MODE_INCLUDE_OPTIONAL, fallback VMC→VMC4B) | J1/S1-S2 | H-001, H-004 | ✅ | `godot_project/README.md` (verdict "export animations OK" sur rig synthetique -- a rejouer avec un vrai VRM+mesh skinne des H-003 termine) |
| H-006 | 3 | Le Chat (Mistral) + Jérémy | Découpage 8-12 plans previz | J1/S2 | H-002 | 📋 | |

## Note budget

H-001 est le seul vrai goulot en cascade (H-004 → H-005 en dépendent). En cas de quota Claude Code serré une semaine donnée : prioriser H-001 dessus, router H-002 vers DeepSeek en 1er jet + relecture Claude Code courte.

## Risque calendrier — chaîne Godot Motion Recorder

Rapport de recherche (Pipeline_open-source_pilotée_à_la_manette.md) : chaîne complète H-001+H-004+H-005 estimée **2-4 semaines** dont 3-5 jours rien que sur le seam d'export glTF (animations parfois omises silencieusement, orientations d'os altérées à l'import Blender). J1 = 31/08 = 22 jours au 09/08. Fallback VMC (Godot→VMC→VMC4B Blender) classé second mais estimé **1-2 semaines seulement**, et il élimine le seam par construction (VMC4B bake les keyframes directement sur l'armature VRM).

**Règle appliquée dans H-005** : budget max ~2-3 jours de debug sur le seam glTF avant bascule VMC — pas d'acharnement. À surveiller en fin de semaine 1 : si H-005 patine, basculer sans attendre plutôt que de grignoter la marge avant J1.

Autre point à tester tôt (H-001/H-004) : `VRMC_node_constraint` buggé en combinaison avec le retargeting dans godot-vrm.

Règle inchangée : un ID une fois attribué n'est jamais réutilisé, même si la tâche est abandonnée (statut ❌ + note).

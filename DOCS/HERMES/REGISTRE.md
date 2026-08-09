# Registre Hermes

Priorisé le 09/08/2026. Vague = ordre d'exécution. Statuts : 📋 à faire · ⏳ en cours · ✅ fait · ❌ bloqué.

## Vague 1 — à lancer en parallèle, aucune dépendance

| ID | Vague | LLM cible | Tâche | Jalon | Dépend de | Statut | Fichier retour |
|---|---|---|---|---|---|---|---|
| H-003 | 1 | Manuel (Jérémy, VRoid Studio) | Création neko girl VRoid → export VRM | J1/S1 | — | 📋 | |
| H-001 | 1 | Claude Code | Setup projet Godot + import godot-vrm | J1/S1 | — | 📋 | |
| H-002 | 1 | Claude Code (ou DeepSeek 1er jet) | Timing module v1 (PySceneDetect+frame-diff+QwenVL) | J1/S1 | — | 📋 | |

## Vague 2 — dès qu'une dépendance de vague 1 est prête

| ID | Vague | LLM cible | Tâche | Jalon | Dépend de | Statut | Fichier retour |
|---|---|---|---|---|---|---|---|
| H-004 | 2 | Claude Code | Contrôleur manette + caméra libre Godot | J1/S1 | H-001 | 📋 | |
| H-007 | 2 | Claude Code / Aider | LoRA personnage (dataset VRoid+fabricatedXL, rank 32, 5060 Ti) | J1/S1-S2 | H-003 | 📋 | `DOCS/MD/KOHYA_SS_VS_LORA_TRAINER_20260809.md` |

## Vague 3

| ID | Vague | LLM cible | Tâche | Jalon | Dépend de | Statut | Fichier retour |
|---|---|---|---|---|---|---|---|
| H-005 | 3 | Claude Code | Recorder de poses + export GLB (VISIBILITY_MODE_INCLUDE_OPTIONAL, fallback VMC→VMC4B) | J1/S1-S2 | H-001, H-004 | ✅ | verdict réel obtenu sur rig synthétique, à rejouer avec vrai VRM avant clôture définitive |
| H-006 | 3 | Le Chat (Mistral) + Jérémy | Découpage 8-12 plans previz | J1/S2 | H-002 | 📋 | |

## Hors-vague — indépendant des blocages H-003/kohya_ss

| ID | Vague | LLM cible | Tâche | Jalon | Dépend de | Statut | Fichier retour |
|---|---|---|---|---|---|---|---|
| H-008 | — | Claude Code | R-Tuning Stage 3 QLoRA (calibrated refusal) — RTX 5080, plusieurs heures | anti-hallucination | ov3rlord-coder-stage2v2 | ⏳ | `DOCS/MD/H008_RTUNING_STAGE3_PLAN_20260809.md` (plan étape 1, en attente de validation) |

## État vagues 1-2 (mise à jour 09/08 soir)

- H-001 ✅ Godot 4.7.1 + AzPepoze/godot-vrm v2.5.9, validé headless.
- H-002 ✅ agents/timing_analysis.py testé pour de vrai (cuts + frame-diff + QwenVL).
- H-004 ✅ Contrôleur + caméra validés headless, test interactif réel (manette/clavier) encore à faire par Jérémy.
- H-007 ❌ Bloqué : kohya_ss installé le 09/08 soir (`D:\kohya_ss`, venv isolé Python 3.11, voir `DOCS/MD/KOHYA_SS_VS_LORA_TRAINER_20260809.md` — confirmé non redondant avec `lora_trainer.py`, qui l'appelle en subprocess sans logique d'entraînement propre). Reste bloqué sur H-003 seul (aucun .vrm). Ne pas relancer H-007 tant que H-003 n'est pas livrée.

## Note budget

H-001 est le seul vrai goulot en cascade (H-004 → H-005 en dépendent). En cas de quota Claude Code serré une semaine donnée : prioriser H-001 dessus, router H-002 vers DeepSeek en 1er jet + relecture Claude Code courte.

## Risque calendrier — chaîne Godot Motion Recorder

Rapport de recherche (Pipeline_open-source_pilotée_à_la_manette.md) : chaîne complète H-001+H-004+H-005 estimée **2-4 semaines** dont 3-5 jours rien que sur le seam d'export glTF (animations parfois omises silencieusement, orientations d'os altérées à l'import Blender). J1 = 31/08 = 22 jours au 09/08. Fallback VMC (Godot→VMC→VMC4B Blender) classé second mais estimé **1-2 semaines seulement**, et il élimine le seam par construction (VMC4B bake les keyframes directement sur l'armature VRM).

**Règle appliquée dans H-005** : budget max ~1 jour de debug sur le seam glTF avant bascule VMC — pas d'acharnement. À surveiller en fin de semaine 1 : si H-005 patine, basculer sans attendre plutôt que de grignoter la marge avant J1.

Autre point à tester tôt (H-001/H-004) : `VRMC_node_constraint` buggé en combinaison avec le retargeting dans godot-vrm.

Règle inchangée : un ID une fois attribué n'est jamais réutilisé, même si la tâche est abandonnée (statut ❌ + note).

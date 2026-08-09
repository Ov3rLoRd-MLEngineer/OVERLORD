# Registre Hermes

Priorisé le 09/08/2026, mis à jour le 09/08/2026 soir. Vague = ordre d'exécution. Statuts : 📋 à faire · ⏳ en cours · ✅ fait · ❌ bloqué.

**Présence requise** — triage systématique depuis le 09/08 soir, pour paralléliser :
- **Non** : code pur, part en Claude Code dès que le brief est prêt, aucune attente sur Jérémy.
- **Courte** : check/décision/validation ponctuelle (quelques minutes), peut se glisser entre deux choses.
- **Longue** : travail créatif/manuel qui bloque tant que Jérémy n'a pas mis les mains dedans.

## Vague 1

| ID | Présence | LLM cible | Tâche | Dépend de | Statut |
|---|---|---|---|---|---|
| H-003 | Longue | Manuel (Jérémy, VRoid Studio) | Création neko girl VRoid → export VRM | — | 📋 |
| H-001 | Non | Claude Code | Setup projet Godot + import godot-vrm | — | ✅ |
| H-002 | Non | Claude Code (ou DeepSeek 1er jet) | Timing module v1 | — | ✅ |

## Vague 2

| ID | Présence | LLM cible | Tâche | Dépend de | Statut |
|---|---|---|---|---|---|
| H-004 | Non (code) + Courte (test manette réel) | Claude Code | Contrôleur manette + caméra libre Godot | H-001 | ✅ code, test réel manette/clavier en attente (Jérémy) |
| H-007 | Longue (dépend H-003) | Claude Code / Aider | LoRA personnage | H-003 | ❌ bloqué : pas de .vrm + kohya_ss en cours d'install |

## Vague 3

| ID | Présence | LLM cible | Tâche | Dépend de | Statut |
|---|---|---|---|---|---|
| H-005 | Non | Claude Code | Recorder de poses + export GLB | H-001, H-004 | ✅ verdict réel sur rig synthétique, à rejouer avec vrai VRM |
| H-006 | Longue (créatif) | Le Chat (Mistral) + Jérémy | Découpage 8-12 plans previz | H-002 | 📋 |

## Hors-vague — code pur, indépendant des blocages H-003/kohya_ss

| ID | Présence | LLM cible | Tâche | Dépend de | Statut |
|---|---|---|---|---|---|
| H-008 | Non | Claude Code | R-Tuning Stage 3 QLoRA (calibrated refusal) — RTX 5080 | ov3rlord-coder-stage2v2 | ✅ plan `DOCS/MD/H008_RTUNING_STAGE3_PLAN_20260809.md`, verdict `workspace/qlora_dataset/training/VERDICT_H008_STAGE3.md` (6/8 net, 1 sur-refus à corriger, 1 anomalie encodage) |
| H-009 | Non | Claude Code | Fix visual_validator.py (bug format Ollama, même pattern que visual_qc_svi.py déjà corrigé) | — | ✅ bug confirmé identique (payload OpenAI-style `content=[image_url,text]` → 400 Ollama), corrigé dans `agents/qc_validation/visual_validator.py` vers le format natif `content=str + images=[b64]`, test de régression ajouté (`test_suite.py::run_qc_validation`, PASS) |
| H-010 | Non | Claude Code | Fix régression sur-refus H-008 (continuation adapter_stage3_final, catégorie C calibration + investigation anomalie CJK) | H-008 | ❌ partiel : anomalie CJK résolue et adoptée (repetition_penalty 1.15→1.05), mais le correctif catégorie C est un **net négatif** — corrige le Prompt 2 visé mais introduit 2 régressions sévères (dont 1 cas flagship H-008) + 1 modérée. `adapter_stage3b_final` **non recommandé**, `adapter_stage3_final` (H-008) reste le meilleur checkpoint. Verdict détaillé + pistes de correction : `workspace/qlora_dataset/training/VERDICT_H010_OVERREFUSAL.md` |
| H-011 | Non | Claude Code | Retry fix sur-refus H-010 (catégorie C diversifiée + réinjection A/B + LR abaissé) | H-010 | ✅ net positif, `adapter_stage3c_final` **adopté** (remplace `adapter_stage3_final` H-008) — Prompt 2 corrigé comme visé, régression catastrophique H-010 (Prompt 7 flagship) **non reproduite**, mais 1 régression réelle non résolue subsiste (Prompt 3, même prompt qu'en H-010, confabulation d'un correctif cassé). Verdict détaillé + piste de correction future : `workspace/qlora_dataset/training/VERDICT_H011_OVERREFUSAL_RETRY.md` |
| H-012 | Non | Claude Code | Fix reasoning/thinking modèles locaux hermes-agent (erreurs 400) + investigation balises OUT-OF-BAND | — | ✅ diagnostic complet `DOCS/MD/H012_REASONING_LOCAL_MODELS_DIAGNOSTIC_20260809.md` : (1-5) confirmé + corrigé (config.yaml `reasoning_overrides: none` sur 7/9 modèles locaux non-thinking, gemma4:12b/31b-64k épargnés) ; (6) "Ultra" est une valeur légitime hermes-agent, pas un bug UI — gap résiduel non codé : `CustomProfile` (Ollama local) n'a pas de clamp vers le sous-ensemble 5 valeurs qu'Ollama accepte réellement, latent sur gemma4:12b/31b-64k si Ultra/Extra High/Minimal choisi manuellement ; (7) confirmé côté appli (`/steer` de hermes-agent, `agent/prompt_builder.py`), pas le modèle — testé en direct hors hermes-agent, aucune reproduction |

## Présence courte à caser (pas besoin d'une session dédiée)

- Vérifier nvidia-smi : écart carte d'affichage 5080/5060 Ti (process desktop sur la mauvaise carte, signalé HANDOFF 08/08, ~10 min).
- Valider le token de déclenchement LoRA `nekogirl_ov3rlord` (proposé dans H-007, à confirmer avant tout entraînement réel).
- Test manette/clavier réel de H-004 (fenêtre visible, pas headless).

## À reprendre plus tard — sync PLAN_MASTER_80J_AOUT_OCT2026.md

Le plan master fourni est la version d'avant le pivot Godot (session stratégie 09/08) : S1 y liste encore "Prototype Blender-gamepad (timebox 3j)" et un butoir 13/08 "Blender-gamepad vs Unity", plus un butoir 14/09 "choix moteur World" — tous deux déjà tranchés (Godot) dans les faits.

Décision explicite de Jérémy (09/08) : ne pas trancher Blender-gamepad et Unity comme abandonnés — les garder en piste secours / R&D, ils pourraient s'avérer meilleurs sur certains points. Donc la mise à jour du plan master, une fois faite, ne doit PAS supprimer ces options : les repositionner comme alternatives de secours documentées, pas comme obsolètes.

À faire quand on y reviendra : (1) patcher ou refaire le plan master en fonction de ce qui aura été décidé alors, (2) vérifier que l'usage réel de Hermes (cycle OUTBOX→INBOX→REGISTRE) a été validé par Jérémy sur au moins une tâche complète avant de considérer Hermes "opérationnel", (3) intégrer la colonne "Présence requise" comme grille de lecture officielle du plan, pas juste du REGISTRE.

## Note budget

H-001 était le seul vrai goulot en cascade (H-004 → H-005 en dépendaient) — résolu, les deux sont faits.

## Risque calendrier — chaîne Godot Motion Recorder

Rapport de recherche (Pipeline_open-source_pilotée_à_la_manette.md) : chaîne complète H-001+H-004+H-005 estimée 2-4 semaines dont 3-5 jours rien que sur le seam d'export glTF. Verdict réel obtenu sur rig synthétique : export animations OK (pygltflib vérifié). Reste à confirmer sur le vrai VRM (H-003) avant de clore définitivement le risque — mais le plus gros du risque semble déjà écarté.

**Règle appliquée dans H-005** : budget max ~2-3 jours de debug sur le seam glTF avant bascule VMC si jamais le test sur vrai VRM révèle un problème — pas d'acharnement au-delà.

Autre point à tester tôt (H-001/H-004) : `VRMC_node_constraint` buggé en combinaison avec le retargeting dans godot-vrm — pas encore testable, en attente d'un vrai .vrm (H-003).

Règle inchangée : un ID une fois attribué n'est jamais réutilisé, même si la tâche est abandonnée (statut ❌ + note).

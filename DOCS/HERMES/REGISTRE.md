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

| H-013 | Non | Claude Code | Doc exhaustive des commandes slash hermes-agent | — | ✅ `DOCS/MD/HERMES_AGENT_COMMANDES.md` (422 lignes) : source de vérité réelle = `hermes_cli/commands.py::COMMAND_REGISTRY` (95 commandes + 26 alias, 3 surfaces CLI/gateway/mixins) — plus large que les pointeurs de départ (`gateway/slash_commands.py`) qui n'étaient qu'une des 3 surfaces. `/help` existe et est synchronisé au code par construction (généré depuis le registre) ; le manque réel était la profondeur (persistance session/`--global`, nuances `/steer`), pas une dérive doc/code |
| H-014 | Non | Claude Code | Fix clamp reasoning_effort (Ultra/xhigh/minimal → valeurs valides Ollama) avant appel API | H-012 | ✅ `plugins/model-providers/custom/__init__.py` + nouveau `agent/ollama_reasoning.py::resolve_ollama_effort()` (ultra/xhigh→max, minimal→low), clamp appliqué seulement si `_is_verified_ollama(base_url)` (endpoints GLM/ARK/vLLM non-Ollama gardent la valeur verbatim). 216 tests unitaires passants (22 test_custom_profile + 12 test_ollama_reasoning + 182 model_providers). Test réel confirmé en direct (hors agent, coupé par limite de session) : `POST /v1/chat/completions` gemma4:12b-64k, `reasoning_effort=ultra` → 400 (bug), `max` (clamp) → 200 réel. **Non commité** (règle non-négociable session) |
| H-015 | Non | Claude Code | Itération ciblée Prompt 3 (confabulation correctif Unicode) depuis adapter_stage3c_final — RTX 5080 | H-011 | ✅ net positif, `adapter_stage3d_final` **adopté** (remplace `adapter_stage3c_final` H-011). Diagnostic empirique préalable (sonde sur les 12 exemples fichier_specifique) : Prompt 3 était un échec **isolé**, pas systémique. Lot ciblé de 5 exemples (pas de rééchantillonnage large), continuation stricte depuis H-011, LR=1e-5, 2 epochs. Prompt 3 corrigé sur le fond (confabulation `chcp860` éliminée, refuse et demande le fichier) mais phrase finale imparfaite/confuse — pas une victoire complète. Aucune régression sur les 7 autres prompts, Prompt 7 flagship stable, bonus incident : Prompt 5 (confus depuis H-010) redevenu cohérent. Verdict détaillé : `workspace/qlora_dataset/training/VERDICT_H015_TARGETED_PROMPT3.md`. **Déployé sur Ollama** (09/08, soir) sous `ov3rlord-coder-stage3d:latest` (merge fp16 + GGUF f16, `deploy_stage3d_to_ollama.py`) — nouveau tag distinct, `ov3rlord-coder-stage2v2` inchangé/non écrasé, réversible via `/model` (hermes-agent). Testé en direct (`ollama list` + requête réelle) |
| H-016 | Courte (manip physique écrans requise) | Claude Code | Diagnostic écart GPU 5080/5060Ti (affichage) + lenteur générale ressentie | HANDOFF 08/08 §2 | ✅ diagnostic complet `DOCS/MD/H016_DIAG_GPU_DISPLAY_LENTEUR_20260809.md` : confirmé sans ambiguïté (nvidia-smi `Disp.A`) que les écrans sont pilotés par la 5060 Ti, pas la 5080 — correctif = manip physique documentée (débrancher/rebrancher côté Jérémy). VRAM Ollama non mesurée en charge réelle (aucun modèle chargé au moment du test, catalogue jusqu'à 19 Go/modèle → contention plausible non observée). RAM 10/32 Go au moment du test (pic du 08/08 confirmé transitoire, pas permanent). CPU i7-8700K (2017) + charge de fond ~44% même sans tâche lourde + ArmouryCrate ET AI Suite 3 tournant en double (conflit connu) = facteurs indépendants plausibles ; pas de mesure thermique possible à distance (aucun outil de monitoring installé), gain OC non confirmé → revert recommandé. **Découverte annexe non demandée** : 5 redémarrages système inattendus sur 9 jours, un seul corrélé à une rafale TDR GPU (07/08), les 4 autres non expliqués par ce diagnostic — instabilité résiduelle à surveiller séparément. Aucune modification système appliquée (lecture seule), aucun commit |
| H-018 | Courte (validation kill process) | Claude Code | Diagnostic `ollama list` vide (modèles -64k + gemma4:31b introuvables) | H-016 (même machine) | ✅ diagnostic complet `DOCS/MD/H018_DIAG_OLLAMA_MODELS_MISSING_20260809.md` : **aucune perte de données** confirmée (132 Go de blobs + 27 manifestes intacts dans `D:\OVERLORD\models`, vérifié sur disque avant toute conclusion). Cause = 3ᵉ occurrence du piège déjà documenté en mémoire (`ollama-gpu-pinning.md`) : raccourci `Startup\Ollama.lnk` relance `ollama app.exe` avec un environnement figé sans `OLLAMA_MODELS` → serveur enfant retombe sur `~/.ollama/models` vide. Corrigé avec feu vert utilisateur : kill process + relance propre via `launch_ollama.bat` (26 modèles de nouveau visibles, confirmé en direct) + **raccourci Startup déplacé vers `corbeille/startup_shortcuts_disabled/`** (1ʳᵉ fois que cette étape est faite — évite la récidive au prochain login, contrairement aux 2 occurrences précédentes). Aucun re-pull, aucun commit |
| H-020 | Non | Claude Code | Régression fix H-012 (reasoning_overrides disparu sur devstral:24b-64k) | H-012, H-014 | ✅ diagnostic complet `DOCS/MD/H020_REGRESSION_REASONING_OVERRIDES_20260810.md` : **hypothèse de départ infirmée** — `config.yaml` n'a jamais perdu le fix H-012 (intact, inchangé depuis le 09/08). Cause réelle confirmée par inspection de `state.db` : le composer Desktop hermes-agent renvoie sa sélection d'Effort (repli `medium`) sur **chaque** `session.create`, ce qui crée un override scope-session qui gagne toujours sur `config.yaml.agent.reasoning_overrides` par conception — reproduit avec `devstral:24b-64k` (`reasoning_config: {"effort":"medium"}` persisté dans la session fautive). Le clamp H-014 ne couvrait que les valeurs hors grammaire Ollama, pas ce cas (`"medium"` est grammaticalement valide, juste incompatible avec ce modèle précis). Correctif appliqué dans `hermes-agent/plugins/model-providers/custom/__init__.py` : vérification de capacité `thinking` (probe `/api/show`, réutilise l'utilitaire déjà en place pour Ollama Cloud) juste avant l'envoi, donc imperméable à la source de la valeur — testé en direct contre Ollama réel (devstral forcé à `none`, gemma4:12b-64k thinking-capable inchangé) + 232 tests existants toujours verts. **Non commité** (règle non-négociable session) ; recommandation de committer cette fois (contrairement à H-014, dont le commit `4a920add2` montre que ça a déjà été fait sans casse) + redémarrer hermes-agent pour que la session H-017 bloquée reprenne |
| H-019A | Courte (test raccourci) | Claude Code | Créer raccourci bureau pour lancer Aider facilement | H-008..H-011 (venv Aider) | ✅ `D:\OVERLORD\launch_aider.bat` créé (détecte Ollama sur 11434, le lance via `launch_ollama.bat` sinon — jamais autrement ; active le venv `C:\Users\Ov3rL0rD\.aider\venv` ; `OLLAMA_API_BASE` explicite ; `cd D:\OVERLORD`) + raccourci bureau `Aider - Ov3rLoRd.lnk` (icône cmd.exe). Testé de bout en bout en direct (venv activé, modèle résolu, `CLAUDE.md`/`DOCS/INDEX.md` chargés en lecture seule, prompt Aider atteint) — un `OllamaError 404` initial tracé à une **mauvaise instance Ollama relancée manuellement le jour même** (pas via Startup, déjà corrigé H-018), corrigé en re-testant. **Effet de bord positif demandé en cours de tâche** : les 2 raccourcis Démarrer "Ollama" (posés par l'installeur, pointaient vers l'app brute non pinnée) corrigés pour lancer `launch_ollama.bat` — 2ᵉ vecteur de récidive du bug H-018 trouvé et neutralisé, mémoire `ollama-gpu-pinning.md` mise à jour |
| H-019B | Courte (vérification config, pas de tâche réelle) | Claude Code | Vérifier installation Google Antigravity (config seule, pas d'usage réel) | — | ✅ rapport `DOCS/MD/ANTIGRAVITY_SETUP.md` : install confirmée (v2.6.0, à jour, déjà authentifié), backend par défaut 100% cloud Google (pas de modèle local par défaut). **Limitation réelle trouvée** : téléchargement Playwright en échec au démarrage (404 sur 3 miroirs CDN) → preview/test navigateur cassé, indépendant du dépôt. App Electron sans surface CLI exploitable (`--version`/`--help` ouvrent la GUI, aucune trace de workspace/CLAUDE.md/provider local dans les logs backend) — 3 vérifications restantes (pointer sur D:\OVERLORD, détection CLAUDE.md, connexion Ollama local) documentées comme étapes manuelles pour Jérémy, pas faisables headless. Conforme à la consigne : aucune tâche réelle exécutée, 2 lancements de test fermés proprement |

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

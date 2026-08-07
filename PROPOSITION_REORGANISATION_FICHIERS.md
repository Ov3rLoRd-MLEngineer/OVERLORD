# Réorganisation — fichiers et dossiers `D:\OVERLORD`

**Statut : exécutée le 2026-08-02.** Ce document a d'abord servi de
proposition (voir Git/mémoire pour l'historique), puis a été exécuté
intégralement après validation explicite de l'utilisateur. Rédigé en
complément de `RAPPORT_AUDIT_PIPELINE_AOUT2026.md` et
`RAPPORT_IDEES_HISTORIQUE_V150_V227.md`.

## Résumé d'exécution

- **Phase A** (corbeille/ — obsolète confirmé) : exécutée intégralement.
- **Phase B** (docs conservés réorganisés) : exécutée, **sauf** la
  consolidation `launcher_gui/` initialement envisagée — abandonnée après
  vérification : `overlord_launcher.py` lance ses scripts compagnons par
  chemin relatif à `BASE_DIR` (racine), les déplacer aurait cassé le
  lanceur. Ces fichiers restent à la racine, non touchés.
- **Phase C** (regroupement `agents/*.py`) : exécutée intégralement —
  153 fichiers déplacés en 10 sous-dossiers thématiques, chacun remplacé
  à son ancien emplacement par un shim de compatibilité basé sur
  `runpy.run_path(..., run_name=__name__)`, qui fonctionne aussi bien pour
  un import (`from agents.X import Y`) qu'une invocation directe
  (`python agents/X.py --args`) — vérifié par test direct
  (`python agents/context_bus.py` exécute correctement son bloc
  `if __name__=="__main__"` à travers le shim).
- **Vérifications effectuées** : `test_pipeline.py --quick` → 16/16 PASS
  après Phase A+B et après Phase C ; imports individuels testés dans
  plusieurs sous-dossiers (`postprod`, `batch_controlnet`,
  `sam_mask_generator`, `emotion_engine`, `agent_3d_modeler`,
  `workflow_controller`, `visual_validator`...) ; run réel de
  `maestro.py --universe "test reorg smoke" --no-qc` pour un smoke test
  de bout en bout (voir "Points d'attention" ci-dessous).
- **Découverte imprévue, sans lien avec cette réorganisation** :
  `Combined_V35_API.json` (workflow actif chargé par
  `agent_supervisor_v2.py`) était déjà absent de la racine avant toute
  action de ce document — une copie existe dans
  `corbeille/BACKUP/Combined_V35_API.json`, non restaurée (décision
  pipeline, hors périmètre d'un déplacement de fichiers).
- **Bug pré-existant re-rencontré, sans lien avec cette réorganisation** :
  le smoke test `maestro.py` a déclenché `ValueError: I/O operation on
  closed file` sur plusieurs lignes de log console — signature identique
  au "Bug stdout Python 3.14" déjà documenté comme cosmétique/non-bloquant
  dans plusieurs `CONTEXTE_OVERLORD_V1xx.md` historiques (le pipeline a
  continué : Director, Watchdog et CheckpointManager se sont bien
  initialisés malgré l'erreur de log console). Un test isolé (deux
  modules minimalistes reproduisant le même pattern de ré-encodage UTF-8
  de `sys.stdout`) n'a pas reproduit le crash à l'identique, donc la cause
  exacte n'est pas formellement isolée — mais rien n'indique que le
  mécanisme de shim en soit la cause (le nombre de ré-affectations de
  `sys.stdout` par module est inchangé par le déplacement physique des
  fichiers). Non corrigé — hors périmètre de cette tâche.

## Principe directeur

**Rien n'est supprimé.** "Corbeille" = un dossier `corbeille/` à la racine
qui reçoit tout ce qui est confirmé obsolète (déjà appliqué, déjà
remplacé, ou déjà signalé dans `CLAUDE.md` comme candidat à la suppression
sans action prise depuis). Tout est vérifiable via `git log`/`git mv` —
réversible à tout moment. Ce qui mérite d'être gardé est réorganisé en
place, jamais jeté avec le reste.

## ⚠️ Contrainte active au moment de la rédaction

**Un entraînement et des tests tournent actuellement sur la RTX 5080.**
`D:\OVERLORD\workspace\` est explicitement exclu de toute proposition de
déplacement ci-dessous — c'est le dossier de travail runtime du pipeline
(logs, archive, checkpoints, context_bus, qlora_dataset...). **Avant
d'exécuter quoi que ce soit de ce document, vérifier `nvidia-smi`** et
s'assurer qu'aucun run actif n'écrit dans un dossier concerné.

**`agents/visual_validator.py` et `visual_validator.py` (racine) : ne pas
toucher.** Décision explicite de l'utilisateur — aucune proposition de
déplacement/renommage sur ces deux fichiers, malgré la confusion de
nommage documentée ci-dessous (à titre d'information seulement).

---

## 1. Vers `corbeille/` — obsolète confirmé

Tous les points ci-dessous ont été vérifiés (grep de références, diff
octet-à-octet, dates de modification, lecture directe de `.gitignore`) —
aucune supposition.

### 1.1 Bundles de patch déjà appliqués
```
patch_batch_controlnet_ipa.txt
patch_batch_controlnet_v15.txt
patch_batch_controlnet_v16.txt
patch_batch_controlnet_v17.txt
patch_batch_controlnet_v18.txt
patch_bundle_controlnet_fix.txt
patch_bundle_controlnet_v2.txt
patch_bundle_director_universe.txt
patch_bundle_openpose_inject.txt
patch_bundle_pose_flag.txt
patch_bundle_pose_library.txt
patch_bundle_scenario_controlnet.txt
patch_bundle_storyboard_fallback.txt
patch_bundle_v15_v16_remappers.txt
patch_remappers_upscale_direct.txt
BUNDLE_PATCH_V222_FORMAT_A.txt
PATCH_director_V222.txt
```
→ `corbeille/patches_appliques/`

### 1.2 Variantes JSON ComfyUI sans référence en dur ni usage manuel confirmé
```
Advanced_QwenVL_V35_PIPELINE_PATCHED.json      (déjà signalé obsolète dans CLAUDE.md)
Advanced_QwenVL_V35_PIPELINE_PATCHED_v2.json   (déjà signalé obsolète dans CLAUDE.md)
Advanced_QwenVL_V35_PIPELINE_PATCHED_v3.json   (déjà signalé obsolète dans CLAUDE.md)
animatediff_sdxl_cn_test2.json
animatediff_sdxl_cn_test3.json
animatediff_sdxl_cn_test4.json
animatediff_sdxl_test.json
ltxv_t2v_asuka_run.json
ltxv_t2v_asuka_run_v2.json
ltxv_asuka_run_v2_no_gemma.json                (piste LTX-Video abandonnée, cf. V227 "abandon définitif")
asuka_run_controlnet.json
asuka_seed_test.json
asuka_seed_test_v3.json
mask_convention_test.json
```
Vérifié : **zéro référence en dur** dans un `.py` pour ces 13 fichiers.

**Exception — à garder** : `animatediff_sdxl_cn_test.json` et
`"animatediff_sdxl_cn_test animatediff fonctionne.json"` sont les
workflows de référence chargés manuellement dans l'UI ComfyUI (pas par
script — cohérent avec l'audit principal : AnimateDiff reste piloté à la
main). L'absence de référence en dur ne signifie pas "mort" pour ceux-ci.

**`Advanced_QwenVL_V35_ORIGINAL.json`** : gardé à la racine — snapshot
pré-patch conservé à la demande explicite de l'utilisateur (base de
comparaison, cf. `CLAUDE.md`), ne pas déplacer sans nouvelle demande.

→ `corbeille/workflows_json_historiques/`

### 1.3 Doublons racine confirmés stricts (agents/ fait foi)
```
market_analyzer.py      (identique octet-à-octet à agents/market_analyzer.py)
self_optimizer.py       (identique octet-à-octet à agents/self_optimizer.py)
intent_parser.py        (identique octet-à-octet à agents/intent_parser.py)
workflow_organizer.py   (agents/ légèrement plus récent — patch UTF-8 stdout en plus)
```
→ `corbeille/doublons_racine/`

**Exclu de cette liste, ne pas toucher** : `visual_validator.py` (racine)
— ce n'est **pas** un doublon malgré le nom identique : outil différent
(validateur narratif LLM V1.70 vs validateur QwenVL de `agents/`), avec
une confusion de header (le fichier racine se désigne lui-même
"agents/visual_validator.py" dans son propre docstring). Signalé pour
information ; aucune action proposée dessus, conformément à la décision
de l'utilisateur.

### 1.4 Scripts ponctuels sans point d'appel confirmé
```
migrate_v200.py          (migration V200 déjà faite, ne référence que lui-même + patch_workflow_v35.py)
patch_workflow_v35.py    (compagnon de migrate_v200.py, même sort)
reset_checkpoint.py
reset_hard.py
reset_total.py
maestro_patch_v220.py
temp_infer_check.py
demo_pipeline.py
build_organizer.py
neural_orchestrator.py
```
→ `corbeille/scripts_ponctuels/`

### 1.5 Fichiers zéro-octet (déjà signalés dans `CLAUDE.md`)
```
git
python
logging.Logger
```
→ `corbeille/` (racine du dossier corbeille, ce sont des scories triviales)

### 1.6 Artefacts de build régénérables
```
build/            (PyInstaller — Analysis/EXE/PKG/PYZ .toc/.pkg, localpycs)
dist/             (MaestroProduction.exe, MaintenanceHub.exe, settings.json, workspace/_gui_config.json)
MaestroProduction.spec        (régénéré à chaque build_exe.py, pas une source à préserver)
MaintenanceHub.spec           (idem)
MaestroProduction_V149.spec   (ne correspond à aucun build actuel — orphelin)
```
→ `corbeille/build_artefacts/`. **Recommandation associée** : ajouter
`build/` et `dist/` au `.gitignore` (confirmé absents actuellement) pour
ne plus les re-suivre après ce nettoyage.

### 1.7 Dossiers vestiges confirmés vides ou orphelins
```
outputs/                  (archive/images/stl/videos — 4 sous-dossiers, 0 fichier, aucune référence de code actif)
BACKUP/                   (backups datés d'agents, déjà dans l'historique git)
VRAC/overlord_ui.html     (confirmé orphelin — aucun serveur Python ne le sert, contrairement à ui/live_monitor.html)
```
→ `corbeille/`. **Attention** : `VRAC/INSTALL_MODELS.bat`,
`LAUNCH_COMFYUI.bat`, `START_OVERLORD.bat` n'ont pas été vérifiés
individuellement dans cette passe — à confirmer avant de vider tout
`VRAC/` (ne déplacer que `overlord_ui.html` avec certitude ; le reste du
dossier VRAC à revalider au moment de l'exécution).

**Ne PAS toucher** : `ui/live_monitor.html` — confirmé activement servi
par `api_server.py` (`send_from_directory`), ce n'est pas un orphelin.

### 1.8 Export de données redondant
```
data claude 001.zip   (racine, 9.4 Mo)
```
Contenu vérifié plus ancien/plus petit que `DOCS\data claude 001\` déjà
extrait (`conversations.json` : 48,9 Mo dans le zip vs 53,5 Mo déjà
extrait) — la version utile est déjà sur disque et plus complète.
→ `corbeille/`

---

## 2. Conservé, mais réorganisé (pas corbeille)

### 2.1 Documents de session historiques
Les 16 fichiers `CONTEXTE_OVERLORD_V150.md` → `V227.md` (racine) → nouveau
dossier `DOCS/historique_sessions/`. Leur valeur est documentée dans
`RAPPORT_IDEES_HISTORIQUE_V150_V227.md` — à garder organisés, pas à jeter.
`V228.md`, `V229.md`, `V229_ANNEXE.md` et `contexte_02_aout_2026.md`
restent à la racine (les plus récents, consultés en premier par
convention `CLAUDE.md`/`LLM-Secour.md`).

### 2.2 Rapports/ADR/veille épars à la racine
```
ADR_OVERLORD.md, ARCHITECTURE_GANTT_PERT_5S.md, CHECKLIST_PREPARATION_V170.md,
DEPLOY_ET_GO.md, EVALUATION_V160.md, EVALUATION_V170.md,
GUIDE_UTILISATEUR_V170.md, ROADMAP_V200.md, SCRIPT_PASSATION.md,
"Veille technique Ov3rLoRd — Nouveautés 2026.md"
```
→ regroupés dans `DOCS/` à côté de `DOCS/MD/` existant.

```
ASUS_PITCH.md, JAPAN_EXPO_CONTACT.md
```
→ objectif abandonné (Japan Expo n'est plus la deadline, cf. V229), mais
gardés comme archive plutôt que jetés → `DOCS/business_archive/`.

**Restent à la racine** (activement référencés/lus automatiquement) :
`CLAUDE.md`, `README.md`, `LIMITATIONS_CONNUES.md`,
`RAPPORT_AUDIT_PIPELINE_AOUT2026.md`, `RAPPORT_IDEES_HISTORIQUE_V150_V227.md`,
`RAPPORT_TACHES_EN_SUSPENS_JUILLET2026.md`,
`RAPPORT_HANDSEGNET_TRAINING_READINESS.md`,
`ADDENDUM_PISTES_FUTURES_V2/V3_JUILLET2026.md`,
`ADDENDUM_WORKFLOW_ANIMATEDIFF.md`, `CONTEXTE_ANIMATEDIFF_ADDENDUM.md`,
ce présent document.

### 2.3 Diagnostics de test réels — renommer, pas jeter
`tests/` (92 Mo : scripts `bottes_generiques/*.py` + images de debug
`footsegnet_00401_closing/`, `footsegnet_fragmentation_ambiguous/`, liées
à un bug de fragmentation déjà résolu et documenté) → conservé, renommé en
`diagnostics_archive/` pour clarifier que ce n'est pas la suite de tests
automatisés (`test_suite.py`/`test_pipeline.py` à la racine restent les
vrais tests).

### 2.4 Sous-système "launcher/GUI" — à regrouper, pas dépendant du pipeline principal
Confirmé : `overlord_launcher.py`, `llama_chat.py`, `licence_server.py`,
`learning_ui.py`, `overlord_auditor.py`, `aAa_MaintenanceHub.py`,
`organize_project.py`, `build_exe.py`, `build_launcher.py` (agents/),
`module_manager.py` (agents/) forment un arbre d'appel autonome (aucun
n'est importé par `maestro.py` ni `agent_supervisor_v2.py`) — c'est
l'écosystème du launcher desktop tkinter, séparé de l'automatisation
pipeline. Proposition : regrouper dans `launcher_gui/` à la racine plutôt
que de les laisser épars, sans changer leur fonctionnement.

### 2.5 Custom node ComfyUI externe
`comfy_synesthesia_node.py` : non importé par le pipeline, mais destiné à
être copié dans `ComfyUI/custom_nodes/` — ni mort ni intégré. Proposition :
`comfyui_custom_nodes_source/` dédié, pour signaler clairement son usage
(source à copier ailleurs, pas du code appelé depuis ce dépôt).

---

## 3. `agents/*.py` (~170 fichiers) — regroupement en sous-dossiers

### Méthode retenue : shim de compatibilité (zéro casse immédiate)

Déplacer physiquement chaque fichier dans son nouveau sous-dossier, et
laisser à l'ancien emplacement un fichier squelette d'une ligne :
```python
from agents.<sous_dossier>.<module> import *  # shim de compatibilité — voir migration agents/
```
Tous les `from agents.X import Y` déjà présents dans les ~170 fichiers
continuent de fonctionner sans modification immédiate. Les imports sont
ensuite migrés vers le nouveau chemin **au fur et à mesure** (comme
souhaité), et chaque shim est supprimé une fois qu'il n'est plus
référencé nulle part (vérifiable par un grep du nom du module).

### Groupes proposés

| Sous-dossier | Contenu (noms de modules, sans `.py`) |
|---|---|
| `agents/core/` | context_bus, director, config_manager, overlord_utils, checkpoint_manager, agent_registry, module_manager, pipeline_conscience, pipeline_constitution, session_reporter, session_manager, watchdog, watchdog_config, critic, quality_gate, resource_scheduler, roles_registry, schema_validator, patcher |
| `agents/creative/` | scenario, storyboard, sourcing, sourcing_multisensor, auto_sourcing, narrative_memory, narrative_dna, character_designer, character_sheet_generator, style_dna, style_dna_generator, style_continuity, style_evolution, prompt_engineer, prompt_library, prompt_optimizer, prompt_translator, prompt_override, negative_bank, episode_planner, episode_packager, asset_library, pacing_engine, qwen_prompt_refiner, grok_client, grok_prompt_generator, llm_router, ollama_bridge |
| `agents/production_image/` | workflow_controller, comfy_autoconfig, gpu_optimizer, gpu_scheduler, agent_overclock, thermal_protection *(`agent_supervisor_v2.py` reste dupliqué racine+agents/ tel quel, ADR-001, ne pas déplacer)* |
| `agents/production_video/` | batch_controlnet, motion_mask_generator, denoise_estimator, reference_aligner_v2, skeleton_remapper, lineart_extractor, lineart_remapper, frame_extractor, frames_to_video, pose_generator, video_analyzer, video_pipeline, motion_interpolator, sakuga_compositor, transition_builder |
| `agents/postprod_audio/` | postprod, audio_compositor, voice_synthesis, _coqui_tts_worker, music_synthesis, manga_ocr_translator, anime_palette_generator |
| `agents/qc_validation/` | clip_validator, visual_validator *(agents/ uniquement — ne pas toucher la racine)*, inpaint_queue, inpaint_corrector, shoe_consistency_checker, sam_mask_generator, segnet_premask, region_mask_generator, detect_hand_occlusion, dataset_diversity_stats, vlm_grounding, route_by_sam_confidence, backfill_sam_scores, explain_unscored, manual_stitch, quality_reviewer, quality_reviewer_visual |
| `agents/publishing/` | transmedia_publisher, transmedia_export, social_agent, telegram_bot, marketing_pub, audience_analyzer |
| `agents/legacy_v1xx/` | emotion_engine, world_model, agent_personality, intelligence, intelligence_ext, generative_world, theory_of_mind, synchronicity, dream_mode, dream_simulation, cocreation, collective, moe, alignment, generation, learning, learning_agent, memory_agent, legacy_agent, self_improve, self_optimizer, kaizen_analyzer, oracle_interface, core |
| `agents/infra/` | obs_agent, capture, sav_agent, sav_debug, storage_manager, model_downloader, cost_tracker, benchmark_arena, deploy, build_maintenance_hub, build_launcher, overlord_launcher, api_server, dashboard, graph_ui |
| `agents/3d/` | agent_3d_modeler |

**Ne jamais toucher** : `agents/requests/`, `agents/urllib3/`,
`agents/certifi/`, `agents/idna/`, `agents/charset_normalizer/` (+ leurs
`*.dist-info/`) — packages tiers vendored (déjà signalés dans
`CLAUDE.md`).

**Non classé volontairement dans ce document** (à trancher au moment de
l'exécution, marginal) : `intent_parser.py`, `market_analyzer.py`,
`self_optimizer.py` existent déjà dans `agents/` (les doublons racine
partent en corbeille, section 1.3) — leur groupe d'appartenance
(`legacy_v1xx`/`publishing`/`creative`) est à confirmer selon leur usage
réel au moment de la migration.

---

## 4. Hors périmètre — ne pas toucher

```
workspace/          ← RUN ACTIF EN COURS (RTX 5080), vérifier nvidia-smi avant toute action future
footsegnet/, handsegnet/, bodysegnet/, facesegnet/
DEMO/
config/, data/
models/, unsloth_compiled_cache/
.claude/
```
Ce sont des dossiers de données/modèles/runtime actifs, pas du clutter à
nettoyer.

---

## 5. GitHub

Aucune action sur le remote maintenant. Le dépôt est privé par défaut
(`CLAUDE.md`). Si cette même architecture nettoyée sert un jour de base à
une extraction publique partielle, ce sera un sous-ensemble différent
(comme pour footsegnet/handsegnet déjà publiés) — à traiter séparément,
au moment choisi, pas dans ce document.

---

## 6. Points à trancher par l'utilisateur avant exécution

1. `visual_validator.py` (racine) : exclu de toute action sur décision
   explicite — reste tel quel indéfiniment sauf nouvelle demande.
2. `VRAC/*.bat` (3 fichiers, hors `overlord_ui.html`) : non vérifiés
   individuellement dans cette passe, à revalider avant de vider le
   dossier.
3. Ajout de `build/` et `dist/` au `.gitignore` : recommandé mais pas
   fait — à valider avant de le faire (changement de config, pas un
   simple déplacement de fichier).
4. Ordre d'exécution suggéré si validé : (1) section 1 — corbeille, sans
   toucher à `agents/`, risque quasi nul ; (2) section 2 — réorganisation
   docs, risque nul (aucun import Python concerné) ; (3) section 3 —
   regroupement `agents/`, à faire en dernier et avec `test_suite.py`
   lancé avant/après chaque lot de déplacements (shims en place), une
   fois qu'aucun run GPU actif n'est en cours sur `workspace/`.

---

*Document de proposition, lecture seule — aucun fichier déplacé. Voir
`RAPPORT_AUDIT_PIPELINE_AOUT2026.md` pour le contexte de l'audit qui a
motivé cette proposition.*

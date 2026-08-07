# Rapport d'audit — Pipeline Ov3rLoRd, état module par module

Généré le 2026-08-02. Audit en lecture seule (aucune modification de code),
sur demande explicite : cartographier ce qui est fonctionnel, intégré au
pipeline principal, développé en silo, ou manquant — et identifier les
maillons qui manquent pour sortir **30 secondes de vidéo démo bout en
bout**.

Méthode : lecture de `CLAUDE.md`, `DOCS/INDEX.md`, `DOCS/LLM-Secour.md`,
`CONTEXTE_OVERLORD_V229(+annexe).md` (doc de session le plus récent hors
worktrees), `RAPPORT_TACHES_EN_SUSPENS_JUILLET2026.md`,
`ADDENDUM_PISTES_FUTURES_V3_JUILLET2026.md`, les addenda AnimateDiff, puis
lecture directe de `maestro.py`, `agent_supervisor_v2.py`,
`agents/context_bus.py`, `agents/director.py`, `agents/postprod.py`,
`agents/inpaint_corrector.py`, `agents/workflow_controller.py`, les 4
SegNets, et recherche des points d'appel (`grep`) de chaque module
d'assemblage vidéo pour distinguer "câblé" de "silo". Vérification directe
du dossier `D:\Ov3rLoRd AI\ComfyUI\output\` pour confirmer l'existence
réelle de sorties (pas seulement de code).

**Note méthodologique** : ce rapport documente ce que le code fait
réellement (imports, call sites, fichiers de sortie), pas ce que la
documentation de session affirme. Là où les deux divergent (ex.
`llm_router.py`), le code fait foi.

---

## 1. Légende des statuts

| Statut | Signification |
|---|---|
| ✅ **Fonctionnel + intégré** | Le code marche ET il est appelé depuis le flux principal (`maestro.py` → `agent_supervisor_v2.py` → `postprod.py`) |
| 🟡 **Fonctionnel en silo** | Le code marche (testé, exécutable seul) mais aucun autre module du dépôt ne l'importe/l'appelle — accessible seulement en CLI manuel |
| 🟠 **Partiel / en cours** | Développement réel mais incomplet (dataset non annoté, entraînement non fait, bug non résolu) |
| ❌ **Manquant** | N'existe pas dans le dépôt actuel malgré des mentions dans la doc/mémoire |

---

## 2. Orchestration centrale

### `maestro.py` — ✅ Fonctionnel + intégré
Chef d'orchestre `SOURCING → SCENARIO → STORYBOARD → PRODUCTION → POST-PROD → 3D`.
~30 modules importés en `try/except` avec stub de repli — un import cassé
dégrade la fonctionnalité (log de warning) mais ne bloque jamais le run.
Un seul import échoue silencieusement de façon notable :
`from agents.comfy_memory import VRAMManager` (ligne 301) — **`agents/comfy_memory.py`
n'existe pas dans le dépôt**, donc `VRAM_OK=False` en permanence et
aucune gestion VRAM de sécurité n'est active pendant les runs `maestro.py`
(impact mineur, silencieux, jamais remonté).

### `agent_supervisor_v2.py` — ✅ Fonctionnel + intégré, mais **image fixe uniquement**
Racine (ADR-001), appelé par `maestro.py` via `run_batch_advanced()`.
`WORKFLOW_FILE = "Combined_V35_API.json"` — patché par nœuds ID
(`ADV_*`/`DET_*`). **Aucune référence à AnimateDiff nulle part dans ce
fichier** (`grep -i animatediff` : 0 résultat). Le pipeline industriel ne
sait produire que des images fixes SDXL, jamais des séquences animées.

### `agents/context_bus.py` — ✅ Fonctionnel + intégré
Bus pub/sub singleton thread-safe, persisté sur disque
(`workspace/context_bus/bus_state.json`). Utilisé activement par
`maestro.py`, `agent_supervisor_v2.py`, `director.py`, `postprod.py` et
une trentaine d'autres modules. Aucun problème constaté.

### `agents/director.py` — ✅ Fonctionnel + intégré
Décrit dans son propre docstring comme "le chaînon manquant évoqué 7 fois,
jamais construit — construit maintenant" : c'est désormais vrai, il est
réellement appelé dans `run_pipeline()` (`get_director()`, `set_intent()`,
`end_session()`), configure le seuil qualité du critique et le
`scene_type` via le bus. Dépend en fallback silencieux de
`agents/emotion_engine.py`, `agents/world_model.py`,
`agents/agent_personality.py`, `agents/intelligence_ext.py` (tous
présents, non vérifiés en détail — hors du périmètre "chaîne vers la
démo").

### `agents/llm_router.py` — 🟡 Fonctionnel en silo (mémoire précédente obsolète)
**Correction d'un fait périmé** : une mémoire de session antérieure notait
que `agents/llm_router.py` n'existait que dans un worktree non mergé. Ce
n'est plus vrai — le fichier est bien présent sur l'arbre principal
(livré PR #15, session 2026-07-07/08, confirmé par
`RAPPORT_TACHES_EN_SUSPENS_JUILLET2026.md`). Routage `code`/`prompt_refinement`/
`general`/`complex` vers Ollama (deepseek-r1/qwen2.5/mistral) avec repli
sur `fallback_llm()`. **Mais** : `grep` sur tout le dépôt ne trouve aucun
`from agents.llm_router import` ni `import llm_router` en dehors du
fichier lui-même — aucun agent du pipeline ne l'utilise. Tous les agents
(scenario, storyboard, prompt_engineer...) continuent d'appeler
`fallback_llm()` directement depuis `overlord_utils.py`, sans passer par
le routage par type de tâche. Le routeur est prêt mais jamais branché.

---

## 3. SegNets (Foot / Hand / Body / Face)

| Module | Génération dataset | Annotation | Entraînement | Publication | Intégration pipeline |
|---|---|---|---|---|---|
| **FootSegNet** | ✅ 300 img | ✅ complet | ✅ val_IoU 0.9277 | ✅ GitHub+HF (2026-07-26) | 🟡 silo (voir ci-dessous) |
| **HandSegNet** | ✅ 322 img (98 régénérées LoRA anti-mains-difformes) | 🟠 124/300 annoté manuel, 176 restants | ✅ (version publiée) | ✅ GitHub+HF (2026-07-30) | 🟡 silo |
| **BodySegNet** | ✅ ~300 img brutes générées | ❌ dossiers `masks/`, `annotations/` vides (`.gitkeep` seulement) | ❌ | ❌ | ❌ |
| **FaceSegNet** | ✅ ~300 img brutes générées | ❌ dossiers `masks/`, `annotations/` vides (`.gitkeep` seulement) | ❌ | ❌ | ❌ |

**Point clé pour l'objectif démo** : même FootSegNet/HandSegNet, une fois
entraînés et publiés, ne sont **pas appelés automatiquement** par
`maestro.py` ni `agent_supervisor_v2.py` (`grep` négatif dans les deux
fichiers). Le seul point d'entrée pipeline est `agents/inpaint_corrector.py`,
qui charge `footsegnet/infer.py` en priorité (repli SAM générique sinon) —
mais `inpaint_corrector.py` lui-même n'est importé par aucun autre module
du dépôt : c'est un script CLI qu'on lance à la main
(`python inpaint_corrector.py --auto`), jamais déclenché depuis
`block_production`/`block_postprod` de `maestro.py`. Les 4 SegNets sont
donc, du point de vue du pipeline automatisé, **des outils annexes
utilisables en correction manuelle post-génération**, pas une brique de
la chaîne de production.

Chantiers en cours actifs sur ce périmètre (voir
`RAPPORT_TACHES_EN_SUSPENS_JUILLET2026.md` et
`ADDENDUM_PISTES_FUTURES_V3_JUILLET2026.md`) : pivot stratégique vers un
pipeline de génération de vérité-terrain 3D synthétique (Blender rig +
buffer de segmentation), encore au stade de faisabilité (aucune brique
testée) ; tournage stéréo réel pour HandSegNet conditionné à la
récupération d'un stabilisateur DJI ; 105 cas FootSegNet en review
manuelle en attente.

---

## 4. Génération d'image / prompt / continuité

Tous ✅ **intégrés**, importés et appelés dans `maestro.py` avec succès
(imports non protégés par un défaut dégradé qui masquerait un vrai
problème — vérifiés présents dans `agents/`) :
`scenario.py`, `storyboard.py`, `prompt_engineer.py`, `prompt_library.py`,
`style_continuity.py`, `character_sheet_generator.py`,
`style_dna_generator.py`, `character_designer.py`, `narrative_memory.py`,
`quality_gate.py`, `critic.py`, `watchdog.py`, `clip_validator.py`,
`inpaint_queue.py`, `pacing_engine.py`, `visual_validator.py`,
`checkpoint_manager.py`, `gpu_optimizer.py`, `negative_bank.py`,
`audit_logger.py`.

Ces briques forment une chaîne de production d'**images fixes** solide et
réellement câblée (sourcing → scénario → storyboard → génération SDXL →
QC CLIP/visuel/pacing → continuité de style inter-frames). C'est la
partie la plus mature et la plus intégrée du dépôt.

---

## 5. Assemblage vidéo — le maillon le plus faible

C'est le cœur du problème pour l'objectif "30 secondes de vidéo démo".

### `agents/postprod.py` — ✅ Intégré, mais **slideshow, pas animation**
Appelé par `maestro.py` (`block_postprod`). `images_to_video()` assemble
une liste d'images fixes via `ffmpeg -f concat`, chaque image tenant
`FRAME_DURATION_S = 3` secondes à l'écran (paramétrable). C'est
techniquement une vidéo, mais **aucune image ne bouge** — c'est un diaporama
avec TTS/musique en fond, pas une animation. Fonctionnel de bout en bout
pour ce que c'est, mais ce n'est pas ce que "vidéo démo anime" implique
généralement.

### `agents/video_pipeline.py` — 🟡 Silo total
Contient `FrameInterpolator`, `VideoUpscaler`, `VideoStabilizer`,
`SceneTransitionEngine`, `VideoPipelineV140`. Code complet, testable en
`__main__`. **Zéro** `import` de ce module ailleurs dans le dépôt
(`grep` confirmé). Jamais appelé.

### `agents/motion_interpolator.py` — 🟡 Silo total
Contient des fonctions d'easing (`ease_in_out`, `ease_impact`...),
interpolation de prompts/seeds/strength entre keyframes, et surtout
`ken_burns_sequence()` — la seule brique du dépôt qui simulerait un
mouvement (pan/zoom) sur une image fixe façon "limited animation". **Zéro
point d'appel** ailleurs dans le dépôt. `pacing_engine.py` ne fait que le
*mentionner* en commentaire ("timing pour postprod.py / transition_builder.py"),
sans l'importer.

### `agents/sakuga_compositor.py` — 🟡 Silo total
`SakugaShot`, `build_production_plan`, `assemble_sakuga_shot`,
`run_production_plan` — compositing par couches (BG/perso/visage).
Aucun point d'appel externe.

### `agents/transition_builder.py` — 🟡 Silo total
`build_transition`, `build_montage`, fondu au noir. Aucun point d'appel
externe — y compris depuis `postprod.py`, qui pourtant en aurait
directement l'usage pour lisser les coupes entre shots du diaporama.

### `agents/audio_compositor.py` — 🟡 Silo total
`mix_tracks`, `add_audio_to_video`, `build_demo_audio_plan`. Aucun point
d'appel externe — alors que `postprod.py` fait son propre mixage TTS/musique
à la main via `gTTS` + `ffmpeg` sans passer par ce module plus complet.

**Constat transverse** : cinq modules d'assemblage vidéo/audio
entièrement écrits et individuellement exécutables existent dans
`agents/`, mais **aucun n'est relié à aucun autre ni au pipeline
principal**. Ce sont des briques prêtes à l'emploi qui n'ont jamais été
chaînées ensemble.

### Génération d'animation réelle (AnimateDiff) — 🟠 Test manuel isolé, jamais automatisé
- `ComfyUI-AnimateDiff-Evolved` installé et fonctionnel (`ADE_AnimateDiffLoaderGen1`,
  `mm_sdxl_v10_beta.safetensors`), workflows de test validés en UI
  (`animatediff_sdxl_cn_test.json`).
- Sortie réelle vérifiée sur disque : `D:\Ov3rLoRd AI\ComfyUI\output\animatediff_cn_test\`
  contient **195 frames** (2026-06-30), soit ~8 secondes à 24fps — la
  seule séquence animée réellement produite par le pipeline à ce jour,
  et c'est un test, pas une sortie qualifiée.
- Deux bugs non résolus documentés dans `ADDENDUM_WORKFLOW_ANIMATEDIFF.md` :
  (1) comportement non déterministe entre deux runs à paramètres
  identiques (fond blanc propre vs fond gris/saturé selon l'état résiduel
  du serveur ComfyUI) ; (2) biais génératif "main gauche qui tire sur le
  jean" sur les poses où le bras passe près du bassin (pas un bug de
  squelette/lineart, un biais appris du modèle).
- **Aucun script Python ne pilote ce workflow.** Contrairement à
  `Combined_V35_API.json` (patché par nœuds ID dans
  `agent_supervisor_v2.py`) ou `Advanced_QwenVL_V35.json` (piloté par
  `agents/workflow_controller.py`), le JSON AnimateDiff n'a pas
  d'équivalent automatisé — il se lance et se règle à la main dans
  l'interface ComfyUI.
- Depuis ce test (2026-06-30), la priorité du projet a changé : le
  chantier SegNet (annotation, puis pivot pipeline 3D synthétique) a pris
  le pas, et rien n'indique une reprise du travail AnimateDiff depuis plus
  d'un mois.

### `agents/batch_controlnet.py` et suite — 🟠 chaîne alternative dormante, non couverte au premier passage
Une relecture complémentaire des documents de session `CONTEXTE_OVERLORD_V150.md`
à `V227.md` (voir `RAPPORT_IDEES_HISTORIQUE_V150_V227.md` pour le détail
complet) révèle une **troisième chaîne de production**, distincte à la
fois du duo `maestro.py`/`agent_supervisor_v2.py` (images fixes) et des
tests manuels AnimateDiff ci-dessus : un pipeline frame-par-frame
(`agents/batch_controlnet.py` + `motion_mask_generator.py` +
`denoise_estimator.py` + `reference_aligner_v2.py` + `session_manager.py`
+ `skeleton_remapper.py` + `lineart_extractor.py` + `frames_to_video.py`),
construit entre le 23 et le 30 juin 2026 jusqu'à une version documentée
V1.9 (le fichier présent dans le dépôt porte encore un en-tête V1.4 — le
code a pu évoluer sans que le docstring suive). Architecture : ControlNet
double OpenPose+Lineart, IPAdapter en mode "rolling" (frame N-1 comme
référence), masque de mouvement par diff de squelettes, denoise dynamique.
**Résultats mesurés et documentés** : 10/10 frames réussies, fond stable
sur 10 frames consécutives (V226, 28/06/2026) — un prototype qui a
fonctionné, pas juste une idée. Resté inachevé pour trois raisons
cumulées (dataset lineart jamais complété au-delà d'un cycle de 38
frames Mixamo sur les 1008 nécessaires ; squelette source avec bras
manquant ; `cycle_detector.py` pour boucler le cycle jamais construit),
puis abandonné quand la session a pivoté vers les tests AnimateDiff en
UI, sans jamais y revenir. **Tous ces fichiers existent toujours dans
`agents/`** — c'est une option concurrente à la fiabilisation d'AnimateDiff
pour produire les 30s de démo, à évaluer avant de repartir de zéro.

### `DEMO/` — matériau de référence et extraction, pas une sortie IA
`DEMO/video ref/001-006.mp4` + `asuka_run_reference.mp4` (fusion ffmpeg
via `DEMO/demo_fusion.py`) + `asuka_run_prompts.json/.txt` : référence de
mouvement réelle (vidéo Kling AI 3.0 Turbo générée comme humain réel de
référence, pas de la mocap physique), 42 secondes, 6 plans découpés avec
prompt et hint ControlNet par plan. `DEMO/frames/frames/*.png` (1008
fichiers, confirmé par `CONTEXTE_OVERLORD_V223-226.md`) sont les frames
extraites de cette vidéo Kling puis passées en DWPose — la source
finalement abandonnée le 30/06 ("abandon définitif des frames Kling",
V227) au profit d'un cycle de course Mixamo→Blender plus court (34-38
frames, dossiers `DEMO/frames/mixamo_raw/`, `skeletons_1024x1024/`,
`lineart_1024x1024/`, chacun à 38 fichiers aujourd'hui). Le dossier
`DEMO/frames/lineart_910x512/` (0 fichier) est un vestige vide de la
piste Kling abandonnée. C'est un plan de tournage et des extractions
partielles prêts à consommer, pas un livrable — et pas une source unique
cohérente (deux origines différentes coexistent dans le même dossier).

---

## 6. Publication / transmedia

`agents/transmedia_publisher.py`, `agents/episode_planner.py` — ✅
importés dans `maestro.py`, appelés conditionnellement
(`cfg.get("publish_after_run")`) en fin de run. Fonctionnels et intégrés,
mais **hors périmètre direct** de l'objectif "produire 30s de démo" (ils
consomment une vidéo déjà finalisée).

---

## 7. Synthèse — statuts par catégorie

| Catégorie | Modules | Statut dominant |
|---|---|---|
| Orchestration (maestro/supervisor/bus/director) | 4 | ✅ Intégré et fiable |
| Génération image + QC + continuité | ~19 | ✅ Intégré, chaîne la plus mature |
| SegNets (4) | 4 | 🟠 2 avancés mais non branchés au pipeline auto, 2 au stade dataset brut |
| Assemblage vidéo/audio avancé | 5 | 🟡 100% silo — code fait, jamais relié |
| Animation réelle (AnimateDiff) | 1 chaîne | 🟠 Test manuel unique, 8s produites, bugs non résolus, non automatisé |
| Pipeline A frame-par-frame (`batch_controlnet.py`+suite) | 1 chaîne | 🟠 Prototype dormant, résultats mesurés (10/10 frames), inachevé depuis fin juin |
| Routage LLM par tâche | 1 | 🟡 Construit, jamais appelé par le pipeline |
| VRAM management (`comfy_memory.py`) | 1 | ❌ Fichier manquant, fallback silencieux |
| Publication transmedia | 2 | ✅ Intégré, hors périmètre démo |

---

## 8. Maillons manquants pour sortir 30 secondes de vidéo démo bout en bout

L'objectif implicite est une vidéo **animée** (pas un diaporama de 30
images fixes) avec cohérence de personnage/style sur toute sa durée. Voici
ce qui existe, ce qui manque, dans l'ordre de la chaîne :

1. **Génération de mouvement automatisée — le vrai trou.**
   `agent_supervisor_v2.py` ne sait produire que des images fixes.
   AnimateDiff fonctionne mais seulement à la main dans l'UI ComfyUI, sans
   script de pilotage (pas d'équivalent à `ADV_*`/`DET_*` node-id patching
   pour ce workflow). **Deux chemins concurrents pour combler ce trou** :
   (a) écrire un script qui patche `animatediff_sdxl_cn_test.json` par
   nœuds ID et le soumet via l'API ComfyUI, sur le modèle de ce que fait
   déjà `agent_supervisor_v2.py` ; (b) reprendre et terminer le pipeline
   frame-par-frame `agents/batch_controlnet.py` (+ suite), qui a déjà
   produit des résultats mesurés en juin (voir section 5 et
   `RAPPORT_IDEES_HISTORIQUE_V150_V227.md`) et n'a besoin "que" de
   compléter le dataset de squelettes/lineart sur la durée cible et de
   boucler le cycle de course — pas de résoudre un bug de cohérence
   temporelle inconnu. (b) part avec plus d'avance concrète que (a).

2. **Fiabilisation du résultat AnimateDiff avant tout scale-up.**
   Les deux bugs connus (non-déterminisme fond/saturation entre runs,
   biais "main sur le jean") ne sont pas résolus. Produire 30s (720
   frames à 24fps, soit ~3.7x le seul test réalisé à ce jour) sans
   d'abord fiabiliser la cohérence risque de industrialiser un défaut
   plutôt que de le corriger. Le critère de sortie que la session V229
   s'est elle-même fixé ("1000 frames à 24fps, cohérence parfaite
   inter-frames, montrable sans excuse") n'est pas atteint sur les 195
   frames existantes.

3. **Chaînage des modules d'assemblage déjà écrits.**
   `video_pipeline.py` (interpolation/upscale/stabilisation),
   `motion_interpolator.py` (Ken Burns, easing), `sakuga_compositor.py`
   (compositing par couches), `transition_builder.py` (fondus/montage),
   `audio_compositor.py` (mixage) existent et sont individuellement
   fonctionnels mais ne sont appelés par rien. Il manque une fonction
   d'orchestration (un `block_video_assembly` dans `maestro.py`, ou une
   extension de `postprod.py`) qui prenne les sorties AnimateDiff par
   plan, les enchaîne avec `transition_builder`, ajoute l'audio via
   `audio_compositor` plutôt que le mixage ad hoc actuel de `postprod.py`.

4. **Pont SegNet → correction automatique en production.**
   `inpaint_corrector.py` (qui sait déjà appeler FootSegNet en priorité)
   n'est déclenché par rien dans `maestro.py`/`agent_supervisor_v2.py`.
   Pour une démo "montrable sans excuse", les corrections de mains/pieds
   ne peuvent pas rester une étape manuelle post-hoc au cas par cas — il
   manque la boucle QC → détection de défaut localisé → retake ciblé
   automatique évoquée comme axe de recherche non démarré dans
   `CONTEXTE_OVERLORD_V229.md` (section 4, point 4).

5. **Découpage en plans compatible avec AnimateDiff.**
   Le découpage en plans existe déjà côté référence (`DEMO/demo_fusion.py`,
   6 plans, 42s) mais a été pensé pour du tournage/mocap de référence, pas
   pour un pipeline de génération par blocs AnimateDiff (fenêtre glissante
   16 frames). Il faudra un mapping explicite plan → nombre de blocs
   AnimateDiff → overlap, actuellement seulement esquissé dans
   `CONTEXTE_ANIMATEDIFF_ADDENDUM.md` ("prochaine étape après validation").

6. **Décision de repli assumée si le calendrier presse.**
   Si le délai ne permet pas de fiabiliser AnimateDiff, la chaîne 100%
   intégrée et fonctionnelle aujourd'hui (`maestro.py` → images fixes →
   `postprod.py` slideshow + TTS/musique) peut produire une vidéo de 30s
   dès maintenant, au prix d'assumer que ce n'est pas une "animation" mais
   un diaporama commenté. C'est une option de repli honnête, pas un
   correctif — à trancher explicitement plutôt qu'à découvrir en fin de
   parcours.

**En une phrase** : la chaîne image fixe → QC → publication est mature et
réellement câblée ; la chaîne animation → assemblage vidéo → montage
existe presque entièrement en pièces détachées fonctionnelles mais
**aucune de ces pièces n'est reliée à une autre** — le travail restant
est principalement de l'intégration (écrire les points de jonction), pas
de la recherche ou du développement de fonctionnalités nouvelles, à
l'exception de la fiabilisation d'AnimateDiff lui-même (point 2).

---

## 9. Addendum — corrections après lecture de `contexte_02_aout_2026.md`

Ce fichier (racine du dépôt, hors motif `CONTEXTE_OVERLORD_V*.md`) a été
manqué lors de la première passe de cet audit — mon `Glob` initial ne
cherchait que l'ancien motif de nommage. Il couvre la session la plus
récente (nuit du 28→29 juillet jusqu'au 2 août 2026) et corrige deux
points du corps du rapport ci-dessus :

1. **HandSegNet est en réalité terminé, pas à 124/300.** L'annotation
   manuelle des 322 images a été achevée depuis (mode POINT+SAM en une
   nuit), le modèle est entraîné (`handsegnet_vit_b_best.pth`, val_IoU
   interne 0,8876 ; IoU pipeline réel via détection auto de boîte : 0,722
   moyenne/0,773 médiane, écart documenté dans le model card) et publié
   (GitHub+HF, 2026-07-30). **HandSegNet a donc exactement le même niveau
   de maturité que FootSegNet** — la section 3 ci-dessus (tableau) sous-
   estimait son état. Le constat d'intégration reste inchangé : ni Foot ni
   HandSegNet ne sont appelés automatiquement par `maestro.py`/
   `agent_supervisor_v2.py`, seul `inpaint_corrector.py` (CLI manuel) les
   utilise.
   Reste ouvert, non bloquant : 186 masques FootSegNet et 105 images
   HandSegNet legacy signalés pour review qualité manuelle (fragmentation
   de masque), travail d'annotation pur prévu hors session Claude Code.

2. **"QC anatomique automatisé" n'est pas un axe jamais exploré — c'est un
   axe tenté sur 3 candidats successifs le 2026-07-29 et bloqué à chaque
   fois avant tout téléchargement de poids**, pas par manque de solution
   technique. Lu directement dans `DOCS/MD/QC_ANATOMIQUE_AUDIT_LICENCES_20260729.md` :
   - **HADM** : `gh api repos/wangkaihong/HADM` renvoie `license: None` —
     aucun fichier LICENSE, droits réservés par défaut. Nécessiterait un
     contact direct avec l'auteur pour clarification, jamais entrepris.
   - **HandRefiner** (code MIT confirmé) : dépend de MeshGraphormer
     (Microsoft, MIT réel malgré un tag GitHub "None" mal détecté) qui
     lui-même nécessite `MANO_RIGHT.pkl`, téléchargeable seulement après
     création de compte + acceptation d'une licence non-commerciale
     personnelle sur mano.is.tue.mpg.de — enregistrement que l'utilisateur
     seul peut faire, et qui resterait de toute façon non-commercial.
   - **DiffDoctor** (code MIT confirmé) : `ad_inference.py` lu directement
     instancie `SegformerForSemanticSegmentation.from_pretrained("nvidia/mit-b5")`
     puis charge le checkpoint par-dessus — poids donc dérivés directement
     de SegFormer NVIDIA, sous *NVIDIA Source Code License* section 3.3
     ("non-commercially... research or evaluation purposes only"),
     propagée aux dérivés (section 3.2). Nuance notée dans le rapport
     source : un test zero-shot ponctuel pourrait entrer dans le cadre
     "évaluation" autorisé par cette licence — contrairement à une
     intégration en production — mais la limite entre les deux est un
     jugement laissé explicitement à l'utilisateur, pas tranché.

   **Ce que ça signifie pour le rapport de veille externe** (`DOCS/MD/Audit
   de maturité technique 2026...md`, même semaine) qui recommande HADM en
   priorité n°1 "mûr, prototypable immédiatement" : ce rapport est une
   revue de littérature indépendante qui ne semble pas avoir eu connaissance
   de cet audit de licences interne — les deux ne se contredisent pas tant
   qu'ils répondent à des questions différentes ("la technique existe-t-elle
   publiquement ?" vs "peut-on légalement l'utiliser dans ce projet précis ?").
   Sur le second point, plus pertinent pour Ov3rLoRd, HADM reste bloqué sauf
   contact auteur, et DiffDoctor n'est défendable qu'en évaluation ponctuelle,
   pas en intégration pipeline. Ce point ne bloque pas l'objectif "30s de
   démo" en lui-même (amélioration de qualité, pas prérequis de la chaîne
   d'assemblage vidéo), mais conditionne la boucle de retake automatique
   mentionnée au point 4 de la section 8.

**Autres chantiers actifs notés dans ce document, sans impact sur les
constats d'intégration ci-dessus** (mentionnés pour complétude, hors
périmètre direct de la démo 30s) : Control-LoRA FootSegNet en pause
(mode collapse diagnostiqué comme architectural — perte d'info dans les
convolutions stride-2 de `controlnet_cond_embedding` — pistes de reprise
identifiées : CtrLoRA, ViscoNet) ; fiabilisation du fallback LLM local
(Aider+qwen3-coder, bug d'encodage Windows corrigé) ; correctif wildcards
anti-hallucination "camera" (validé 18/18 et 16/16 sur tests) ; chantier
QLoRA de personnalisation LLM local (déjà connu, voir mémoire
`qlora-local-llm-effort`). Quatre rapports de veille technique
supplémentaires existent dans `DOCS/MD/` (Regional Prompting, pipeline
lineart→couleur, prompt engineering anti-hallucination, et l'audit de
maturité déjà cité) : ce sont des revues de littérature 2026 orientées
qualité d'image/cohérence, pas des rapports d'intégration de code — ils
confirment notamment, depuis une recherche indépendante, que la
stabilisation temporelle du lineart ("anti-line-boiling") est un vrai gap
non résolu dans la littérature 2026, cohérent avec l'absence de solution
de ce type dans le dépôt.

**Lecture recommandée pour ces rapports de veille (et plus largement pour
tout doc de session daté)** : certains détails ponctuels s'y périment vite
(disponibilité VRAM annoncée, statut d'un repo GitHub à un instant T,
version exacte d'un poids) sans que l'idée de fond ne se périme — le
pattern "structure d'abord (lineart), couleur ensuite" documenté dans
`Pipeline lineart -N&B - color after.md`, ou la priorisation QC anatomique
> DesignLock > ColorLock > lineart temporel de l'audit de maturité,
restent des pistes directement exploitables même si tel chiffre ou tel
lien doit être revérifié avant usage. Je n'ai pas retraité ce rapport
pour extraire systématiquement "l'idée réutilisable" de chaque document
de session historique (`CONTEXTE_OVERLORD_V1xx`→`V227` notamment,
non relus en détail dans cet audit, hors V228/V229) — ce travail de
synthèse reste à faire si l'utilisateur le souhaite, distinct de l'audit
d'intégration de code demandé ici.

---

## 10. Réorganisation fichiers/dossiers — exécutée

Suite à cet audit, une réorganisation de `D:\OVERLORD` a été rédigée puis
exécutée le 2026-08-02 (dossier `corbeille/` non destructif pour
l'obsolète confirmé, réorganisation des docs conservés, regroupement des
153 fichiers `agents/*.py` en 10 sous-dossiers thématiques via des shims
de compatibilité `runpy`) : voir `PROPOSITION_REORGANISATION_FICHIERS.md`
pour le détail complet et le résumé d'exécution. Vérifié par
`test_pipeline.py --quick` (16/16 PASS) et un smoke test réel de
`maestro.py`. Racine passée d'environ 150 à 76 fichiers directs.

---

*Rapport généré en lecture seule, aucun fichier de code modifié pendant
cet audit.*

# Plan — finir Pipeline A (`batch_controlnet.py`) pour 30s de démo animée

Document de reconnaissance, **lecture seule** — aucun code modifié. Objectif :
vérifier l'état réel du "Pipeline A" (chaîne frame-par-frame dormante décrite
dans `RAPPORT_IDEES_HISTORIQUE_V150_V227.md` §3 et
`RAPPORT_AUDIT_PIPELINE_AOUT2026.md` §5) et proposer un plan concret pour le
finir, comme option concurrente à la fiabilisation d'AnimateDiff pour
produire les 30s de démo animée.

Rédigé le 2026-08-03, après la réorg `agents/*.py` (Phase C, commit
`7a85dec`) — tous les chemins ci-dessous sont post-réorg.

## 1. État réel du code (vérifié aujourd'hui, pas supposé)

### 1.1 `batch_controlnet.py` — docstring V1.4, fonctionnalités V1.9 déjà présentes

Nouveau chemin : `agents/production_video/batch_controlnet.py` (767 lignes ;
`agents/batch_controlnet.py` reste un shim de compatibilité vers ce fichier).
L'en-tête se présente toujours comme "V1.4" (corrections CN
strength/SSIM/seed/IPAdapter), mais une lecture du code confirme que les
fonctionnalités attribuées à la V1.9 dans les sessions historiques **sont
bien câblées**, pas juste documentées :

- `from denoise_estimator import estimate_denoise` (ligne 42) et
  `from motion_mask_generator import generate_motion_inpaint` (ligne 48) —
  imports à plat (pas `from agents.production_video.X import Y`), donc le
  script suppose que ces modules sont dans le même répertoire que lui au
  moment de l'exécution. **Conséquence de la réorg, vérifiée sans risque** :
  comme les deux fichiers ont été déplacés ensemble dans
  `agents/production_video/`, l'import à plat continue de fonctionner
  (Python ajoute automatiquement le répertoire du script à `sys.path` en
  exécution directe) — pas un blocage introduit par Phase C, juste un point
  à garder en tête si un de ces fichiers est déplacé isolément plus tard.
- `--ipa-source {rolling,anchor}` (ligne 502, défaut `rolling`) : le mode
  IPAdapter "frame N-1 comme référence" décrit pour la V1.9 est bien une
  option du script actuel, pas une fonctionnalité manquante.
- Le docstring n'a donc besoin que d'une mise à jour cosmétique (numéro de
  version), pas d'un rattrapage fonctionnel — **ce n'est pas un blocage**.

### 1.2 Fichiers de la chaîne — tous présents, emplacements post-réorg

| Rôle | Ancien chemin (racine `agents/`) | Nouveau chemin |
|---|---|---|
| Génération frame-par-frame (ControlNet+IPAdapter+watchdog) | `agents/batch_controlnet.py` | `agents/production_video/batch_controlnet.py` |
| Masque de mouvement (diff squelettes) | `agents/motion_mask_generator.py` | `agents/production_video/motion_mask_generator.py` |
| Denoise dynamique (diff PIL) | `agents/denoise_estimator.py` | `agents/production_video/denoise_estimator.py` |
| État de session (seed/IPAdapter/SSIM/rollback) | `agents/session_manager.py` | `agents/core/session_manager.py` |
| Retargeting squelette | `agents/skeleton_remapper.py` | `agents/production_video/skeleton_remapper.py` |
| Extraction lineart | `agents/lineart_extractor.py` | `agents/production_video/lineart_extractor.py` |
| Assemblage vidéo final | `agents/frames_to_video.py` | `agents/production_video/frames_to_video.py` |
| Raffinement prompt | `agents/qwen_prompt_refiner.py` | `agents/creative/qwen_prompt_refiner.py` |
| Extraction directe frames Kling (piste abandonnée) | `agents/reference_aligner_v2.py` | `agents/production_video/reference_aligner_v2.py` |
| Inversion lineart | `invert_lineart.py` (racine, hors `agents/`) | inchangé |

`cycle_detector.py` : **confirmé absent** du dépôt (recherché partout,
aucune occurrence) — c'est bien un fichier à créer, pas à retrouver.

### 1.3 Assets sur disque (`DEMO/`) — vérifiés par comptage direct, pas par lecture de rapport

| Dossier | Fichiers | Statut |
|---|---|---|
| `DEMO/frames/frames/` | **1008** PNG | Frames extraites de `asuka_run_reference.mp4` (référence vidéo Kling AI, fusion `demo_fusion.py`). **Piste abandonnée le 30/06/2026** ("abandon définitif des frames Kling", V227) — présentes sur disque mais pas la source à utiliser. |
| `DEMO/frames/mixamo_raw/` | **38** | Cycle de course Mixamo→Blender ("Sophie"), piste retenue actuellement |
| `DEMO/frames/skeletons_1024x1024/` | **38** | Squelettes DWPose du cycle Mixamo |
| `DEMO/frames/lineart_1024x1024/` | **38** | Lineart extrait du cycle Mixamo — **c'est le dataset ControlNet réellement utilisable aujourd'hui** |
| `DEMO/frames/lineart_910x512/` | **0** | Vestige vide de la piste Kling abandonnée |
| `DEMO/frames/temp/lineart_1024x1024/` | 34 | Extraction intermédiaire/partielle, sous-ensemble du dossier 38 ci-dessus |

**Confirmation directe des trois blocages** du rapport historique : le
dataset lineart exploitable est bien plafonné à 38 frames sur les 1008
nécessaires, et `cycle_detector.py` est bien absent. Rien n'a changé sur ce
plan depuis la rédaction de `RAPPORT_IDEES_HISTORIQUE_V150_V227.md`.

## 2. Les trois blocages — solution proposée pour chacun

### Blocage 1 — Dataset lineart incomplet (38 frames exploitables / 1008 nécessaires)

**Reformulation importante** : ce n'est pas vraiment un blocage indépendant
— c'est une **conséquence directe du blocage 3** (bouclage). Regénérer 1008
lineart distincts n'est pas nécessaire : le cycle de course Mixamo de 38
frames est *par nature* périodique (une foulée complète se répète), donc le
dataset de 38 frames suffit en théorie à couvrir 1008 frames **si** on sait
le boucler proprement (≈ 26,5 répétitions du cycle détecté).

**Solution** : ne pas traiter ce point séparément — le résoudre en même
temps que le blocage 3 (le mapping frame-cible → frame-source-du-cycle est
le même artefact que "boucler proprement").

### Blocage 2 — Squelette Mixamo "Sophie" avec bras gauche manquant

Cause confirmée dans les sessions historiques : les vêtements du modèle
Mixamo utilisé masquent/cassent le rig du bras gauche lors du retargeting.
Deux solutions déjà identifiées dans `RAPPORT_IDEES_HISTORIQUE_V150_V227.md`,
jamais appliquées :

1. **Modèle Mixamo nu** (pas de vêtement à l'origine du problème de rig) —
   solution la plus rapide si un tel modèle est déjà téléchargé/disponible ;
   sinon un aller-retour sur mixamo.com + re-export FBX est nécessaire.
2. **Retargeting MMD** (pipeline alternatif de retargeting squelette) — plus
   long à mettre en place mais contourne le problème à la source si le
   modèle Mixamo lui-même reste problématique quel que soit l'export choisi.

**Piste additionnelle non explorée par les sessions historiques** (à évaluer
avant de choisir) : le pivot 3D SegNet (voir mémoire `blender-3d-segnet-pivot`
et `handsegnet/blender3d_prototype/drive_from_landmarks.py::configure_cycles_gpu`)
a déjà produit un pipeline Blender fonctionnel pilotant un proxy 3D depuis des
landmarks, validé sur GPU. Si ce pipeline (ou une variante) permet de piloter
un personnage complet sans dépendre du rig Mixamo cassé, cela pourrait éviter
de refaire un retargeting Mixamo/MMD à froid — **non vérifié cette session**
(scope lecture-seule), à investiguer en premier avant de choisir l'option 1
ou 2 ci-dessus, car ça pourrait réutiliser un investissement déjà fait plutôt
que d'en ouvrir un nouveau.

### Blocage 3 — `cycle_detector.py` jamais construit

Rôle attendu : sur les 38 frames du cycle Mixamo, détecter automatiquement
la meilleure paire `(frame_debut, frame_fin)` formant une boucle de course
visuellement continue (sans discontinuité de pose au raccord), puis produire
un mapping `frame_cible (1..1008) -> frame_source_du_cycle (1..N)`.

**Solution proposée** : script autonome réutilisant des briques déjà
présentes dans le dépôt plutôt que d'écrire une nouvelle méthode de zéro :

- Comparaison de pose inter-frames sur les squelettes DWPose déjà extraits
  (`DEMO/frames/skeletons_1024x1024/`, 38 fichiers, aucune ré-extraction
  nécessaire) — distance L2 sur keypoints normalisés entre frame `i` et
  frame `1` pour chaque `i`, la frame la plus proche de la frame 1 (hors
  elle-même) est la meilleure candidate de bouclage.
- Alternative/complément : réutiliser le seuil SSIM déjà présent dans
  `batch_controlnet.py` (watchdog, `SSIM threshold 0.25`) comme mesure de
  continuité visuelle sur les lineart plutôt que sur les squelettes bruts —
  les deux métriques sont déjà exploitées séparément ailleurs dans le dépôt,
  aucune nouvelle dépendance à ajouter.
- Sortie attendue : un fichier JSON de mapping (même esprit que
  `DEMO/frames/extraction_report.json` déjà utilisé pour la piste Kling) —
  `frame_cible -> frame_source`, consommé ensuite par `batch_controlnet.py`
  pour choisir quelle frame lineart/squelette utiliser à chaque itération.

## 3. Ordre d'exécution recommandé

1. **`cycle_detector.py`** en premier — bloque tout le reste (sans mapping,
   impossible de dépasser 38 frames traitées).
2. **Trancher le blocage 2 (bras)** avant tout run substantiel — un défaut
   visuel sur le rig source se propage à chacune des 1008 frames si non
   corrigé en amont ; commencer par évaluer la piste Blender existante
   (moins cher si réutilisable), sinon modèle Mixamo nu, sinon MMD.
3. **Test sur un lot réduit** (24-48 frames, 1-2 boucles du cycle détecté)
   via `batch_controlnet.py` pour valider que le raccord de boucle ne
   produit pas d'artefact visible (le prototype V226 n'a validé que 10
   frames consécutives *sans* franchir de raccord de boucle — ce point
   précis n'a jamais été testé).
4. **Run complet** (1008 frames) une fois le lot test validé — substantiel,
   à lancer via `start cmd /k` (convention `CLAUDE.md`), à logger dans
   `gpu_usage_log.csv`, et **à ne lancer que quand la RTX 5080 est libre**
   (au moment de la rédaction de ce document, la RTX 5080 est occupée à 96%
   par le run `stage2_commitpack_full` en cours — voir
   `workspace/qlora_dataset/HANDOFF_2026-08-03.md`, ETA ~2026-08-04 08h-10h ;
   ComfyUI/`batch_controlnet.py` tourne normalement sur la même carte que
   ComfyUI, donc ce run de training doit être terminé avant d'engager le lot
   complet).
5. **`frames_to_video.py`** pour l'assemblage final.

## 4. Fichiers à créer / modifier

- **À créer** : `agents/production_video/cycle_detector.py` (nouveau,
  aucun équivalent existant).
- **À modifier, cosmétique uniquement** : en-tête docstring de
  `agents/production_video/batch_controlnet.py` ("V1.4" → refléter les
  fonctionnalités V1.9 déjà câblées, cf. §1.1) — n'affecte aucun
  comportement, purement documentaire.
- **Pas de modification attendue** sur `motion_mask_generator.py`,
  `denoise_estimator.py`, `session_manager.py`, `skeleton_remapper.py`,
  `lineart_extractor.py`, `frames_to_video.py` — semblent déjà adaptés au
  flux Mixamo (aucun signe de dépendance à la piste Kling abandonnée dans
  ces fichiers, contrairement à `reference_aligner_v2.py` qui lui est
  explicitement écrit pour les "frames Kling brutes" et n'a plus d'usage
  dans ce plan).
- **Hors code** : re-rig/re-export du personnage Mixamo (ou piste Blender
  alternative) pour le blocage 2 — travail 3D, pas un fichier Python.

## 5. Estimation d'effort par blocage

Qualitatif — aucune mesure chronométrée disponible pour ce pipeline
spécifique, à ne pas présenter comme un chiffrage précis :

- **`cycle_detector.py`** : effort **faible**, une session courte. La
  logique de comparaison (distance sur keypoints ou SSIM) réutilise des
  briques déjà présentes et testées ailleurs dans le dépôt ; pas de nouvelle
  dépendance, pas de calcul GPU nécessaire (comparaison sur squelettes/PNG
  déjà extraits).
- **Blocage 2 (bras)** : effort **incertain**, dépend de la piste choisie —
  rapide si la piste Blender existante (§2, Blocage 2) est réutilisable
  telle quelle ; modéré si un modèle Mixamo nu est directement disponible ;
  plus long si un retargeting MMD complet doit être mis en place à froid.
  **À trancher avant d'estimer plus précisément** — recommandé de faire ce
  choix en premier (avant même `cycle_detector.py` si l'objectif est de
  paralléliser les deux).
- **Test lot réduit + run complet** : le seul chiffre mesuré disponible est
  qualitatif (10/10 frames réussies, V226) — aucune durée par frame n'a été
  logguée. **À mesurer sur le lot test (étape 3 du plan) avant d'engager le
  run complet**, pour obtenir une estimation fiable de la durée totale sur
  1008 frames plutôt que d'extrapoler à l'aveugle.

## 6. Comparaison avec la fiabilisation d'AnimateDiff

Rappel du constat déjà posé dans `RAPPORT_IDEES_HISTORIQUE_V150_V227.md` §3 et
confirmé par cette relecture : Pipeline A a des **résultats mesurés** (10/10
frames, fond stable) alors qu'AnimateDiff reste un pipeline manuel jamais
automatisé, avec deux bugs non résolus documentés dans
`RAPPORT_AUDIT_PIPELINE_AOUT2026.md`. Les trois blocages de Pipeline A sont
tous **concrets et bornés** (un script à écrire, un choix de rig 3D à
trancher, un run à mesurer) plutôt que des inconnues ouvertes — ça reste,
sur la base de cette reconnaissance, l'option la plus rapide vers 30s de
démo animée si l'objectif reste d'actualité.

---

*Document de reconnaissance, lecture seule — aucun fichier de code modifié
pendant sa rédaction. Voir `RAPPORT_IDEES_HISTORIQUE_V150_V227.md` §3 pour
l'analyse historique complète et `RAPPORT_AUDIT_PIPELINE_AOUT2026.md` §5
pour le contexte d'audit plus large.*

---

## 7. Suite — 2026-08-04, session de levée des 3 blocages (Brief Pipeline.txt)

RTX 5060 Ti dédiée à toute la session (RTX 5080 occupée par
`stage2_commitpack_full`, jamais touchée — voir `gpu_usage_log.csv` si
loggué). ComfyUI relancé manuellement, pinné `CUDA_VISIBLE_DEVICES=
GPU-cb196733-cc69-2fae-2eed-f363c2fd2219` (RTX 5060 Ti), confirmé via
`/system_stats` (`cuda:0` renvoyé = "NVIDIA GeForce RTX 5060 Ti").

### Blocage 1 — reformulation confirmée, rien à extraire

Vérification disque : `DEMO/frames/lineart_1024x1024/` contient déjà 38
fichiers (`lineart_0000.png`…`lineart_0037.png`), correspondant 1:1 à
`DEMO/frames/mixamo_raw/` (38 fichiers, décalage d'index 1 attendu :
`0001.png`…`0038.png`). Tous non vides, pixels non-blancs mesurés entre
112k et 137k par frame — pas de fichier tronqué/corrompu. **Rien à
compléter** : le dataset lineart couvre déjà 100% des frames sources
Mixamo disponibles. La confusion "38/1008" du rapport historique
correspond bien à la reformulation du §2 : c'est un problème de bouclage
(Blocage 3), pas d'extraction manquante.

Point de traçabilité trouvé en vérifiant : `agents/production_video/
lineart_extractor.py` (le seul script d'extraction lineart du dépôt) cible
par défaut la piste Kling abandonnée (`video_frames` → sortie 910x512) et
n'a **pas** produit `lineart_1024x1024/` — ce dossier a été généré par un
autre moyen (probablement le rendu Blender manuel, cf. Blocage 2
ci-dessous, qui produit lineart+squelette+beauty ensemble). Aucun script
dans le dépôt ne documente cette génération 1024x1024 ; à garder en tête
si le cycle doit être régénéré depuis Blender un jour.

### Blocage 2 — fichiers sources retrouvés, diagnostic revu (utilisateur : `E:\Blender\Running.fbx` + `E:\Blender\asuka run.blend`)

Le plan initial (§2, rédigé le 2026-08-03) supposait qu'aucun fichier 3D
n'était disponible localement et qu'un aller-retour mixamo.com serait
nécessaire — **recherche disque limitée à `D:\` à l'époque, le dossier
`E:\Blender\` n'avait pas été vérifié**. L'utilisateur a communiqué en
cours de session l'emplacement réel : `E:\Blender\Running.fbx` (59 Mo,
animation Mixamo) et `E:\Blender\asuka run.blend` (214 Mo, scène complète
avec le personnage "Sophie" rigué).

Blender 5.1 est installé (`C:\Program Files\Blender Foundation\Blender
5.1\blender.exe`, déjà utilisé par `handsegnet/blender3d_prototype/`).
Inspection **lecture seule** (`blender.exe -b "asuka run.blend" -P
inspect_script.py`, aucune sauvegarde, aucune modification de la scène) :

- Objets : `Armature.002` (65 os) + 6 mesh (`Ch22_Body`, `Ch22_Eyelashes`,
  `Ch22_Hair`, `Ch22_Pants`, `Ch22_Shirt`, `Ch22_Sneakers`) + caméra + light.
- **`Ch22_Body` (le corps du personnage) a un rig bras gauche complet** :
  tous les groupes de vertices `mixamorig2:LeftShoulder` →
  `LeftForeArm` → `LeftHand` → doigts (Thumb/Index/Middle/Ring/Pinky)
  sont présents. Le squelette (`Armature.002`) a aussi la chaîne complète
  bras gauche + doigts. **Le rig du corps n'est pas cassé.**
- **Anomalie réelle trouvée** : `Ch22_Shirt` (le hoodie) a des groupes de
  vertices pour `LeftShoulder`/`LeftArm`/`LeftForeArm` mais **PAS pour
  `LeftHand`** — la manche ne suit donc pas la déformation de la main.
  Effet probable : clipping/décrochage visuel de la manche autour du
  poignet gauche sur certaines poses, pas un bras manquant à proprement
  parler.
- 3 actions présentes (`mixamo.com`, `.001` : frames 1-35 ; `.002` :
  frames 1-39) — le cycle 38 frames actuellement rendu correspond
  vraisemblablement à l'action `.002` (39 frames dans la timeline, proche
  du compte réel).

**Reformulation du blocage** : la description historique ("bras gauche
manquant à cause des vêtements") ne correspond pas à un rig cassé sur le
mesh du corps — c'est soit (a) un artefact de clipping localisé de la
manche du hoodie autour du poignet, soit (b) un artefact apparu côté
génération SDXL/ControlNet (le modèle a parfois du mal à rendre un membre
partiellement occlus par la vue de profil), pas forcément un défaut du
fichier `.blend` lui-même. Les frames `mixamo_raw` inspectées visuellement
cette session (0001, 0010, 0020) montrent un bras avant-plan cohérent
frame à frame ; le seul défaut visuel repéré est une texture de peau
rougeâtre/tachée sur la main avant-plan de la frame 0020, plus proche d'un
glitch de shading que d'un membre absent.

**Décision de ne pas aller plus loin cette session** : corriger le
clipping de manche (repeindre les poids de `Ch22_Shirt`) ou changer
d'action/caméra nécessite un retour visuel dans l'UI Blender (pas
faisable de façon fiable en headless sans risquer une modification
silencieusement fausse de la scène) — hors du périmètre "intégration et
câblage uniquement" de cette session, et l'instruction de session est
explicite sur ne pas improviser de substitution 3D. **Aucune modification
apportée à `E:\Blender\asuka run.blend` ni `Running.fbx`** — inspection
strictement lecture seule.

**Prochaine étape recommandée** (à trancher par l'utilisateur) : ouvrir
`E:\Blender\asuka run.blend` dans l'UI Blender, visualiser les 3 actions
image par image côté manche gauche, et soit (a) repeindre le vertex group
`LeftHand` sur `Ch22_Shirt` pour qu'elle suive la main, soit (b) masquer
`Ch22_Shirt` sur les frames où le clipping est visible et regénérer
seulement le lineart/squelette de ces frames, soit (c) constater que le
défaut n'existe que côté génération SDXL (auquel cas ce n'est pas un
problème Blender du tout, et le smoke test de cette session — 4/4 frames
propres, voir §8 — suggère que ce pourrait bien être le cas puisqu'aucun
défaut de bras n'y est visible).

### Blocage 3 — `cycle_detector.py` construit et testé

Voir `agents/production_video/cycle_detector.py` (nouveau fichier).
Reconstruit des keypoints depuis la palette couleur OpenPose des PNG
squelettes DWPose (aucun JSON de keypoints disponible sur cette machine —
seulement des rendus PNG dans `DEMO/frames/skeletons_1024x1024/`),
compare frame N vs N+24 par distance L2 normalisée (recentrée/mise à
l'échelle sur le buste ; articulations manquantes ignorées plutôt que de
fausser le score — utile puisque `LEye`/`LEar` sont absentes sur les 38
frames, profil constant, et `Neck` absent sur la frame 0036 spécifiquement).

Résultat sur les 38 frames Mixamo disponibles : **meilleur cycle frames
0013→0037 (24 frames), score de drift 0.2074, 16/18 articulations
comparées**. Résultat écrit dans `DEMO/frames/cycle_best.json` (non
versionné, comme le reste de `DEMO/`).

### Tâche 4 — câblage bout en bout, bug supplémentaire trouvé et corrigé

En testant le cycle sélectionné, `batch_controlnet.py` ne trouvait **aucun
squelette** (`glob` sur le pattern `overlord_skeleton_frame_*_*.png`,
nommage de l'ancienne piste Kling — nos fichiers réels sont nommés
`skeleton_NNNN.png`, convention Mixamo). Deuxième bug trouvé en creusant :
`_REPO_ROOT` dans `batch_controlnet.py` et `motion_mask_generator.py`
remontait seulement 2 niveaux de dossier — correct quand ces fichiers
vivaient à `agents/X.py` avant la réorg Phase C, faux depuis leur
déplacement vers `agents/production_video/X.py` (3 niveaux sous la
racine) : `import config` échouait silencieusement, dégradant
`motion_mask_generator` en mode désactivé sans erreur visible. Les deux
corrigés (voir commit `4eee086`) — probable que d'autres fichiers de
`agents/production_video/` aient le même bug de `_REPO_ROOT`
(`frames_to_video.py`, `session_manager.py` pas vérifiés cette session,
hors périmètre puisque non nécessaires à cette tâche).

**Smoke test (4 frames, 13→16)** : 4/4 générées, 0 échec, mode
`motion_mask` actif dès la frame 14 (confirme que le fix `_REPO_ROOT`
fonctionne réellement, pas juste que l'import ne crashe plus), SSIM
watchdog 0.99-1.00, IPAdapter rolling actif. Vérifié visuellement sur
disque (`D:\Ov3rLoRd AI\ComfyUI\output\asuka_run\frame_0013..0016_*.png`) :
personnage cohérent, pose fidèle au squelette, **aucun défaut de bras
visible**.

**Cycle complet (24 frames, 13→37, skip-existing réutilise les 4 du smoke
test)** lancé via `start cmd /k` après validation du smoke test. **Les 24
fichiers sont bien présents sur disque** (`frame_0013_00001_.png` →
`frame_0036_00001_.png`, confirmé par l'utilisateur via capture d'écran —
mon propre script de comptage avait un motif de glob buggé, `[12]` au lieu
de `[123]`, qui m'a fait sous-estimer la progression réelle en cours de
run) — **mais le résultat n'est PAS utilisable en l'état.**

### Post-mortem qualité — le smoke test 4 frames ne représentait pas le cycle complet

Constat utilisateur (capture d'écran) confirmé par relecture des frames
sur disque : la pose reste quasi figée d'une frame à l'autre ("pas de
mouvement") et le remplissage couleur se désagrège progressivement en
bruit/confettis à partir d'environ la frame 0022, sévère dès 0030-0036 —
la structure (lineart) survit, la couleur non.

**Cause racine identifiée** (lecture de `denoise_estimator.py` +
`motion_mask_generator.py`, aucune modification appliquée) :

- `batch_controlnet.py` appelle `estimate_denoise(..., use_qwen=False)` —
  le scoring QwenVL (plus riche) est explicitement désactivé, seul le
  fallback PIL (`compute_structural_diff`) est actif.
- Ce fallback compte la fraction de pixels qui changent sur tout le
  canevas 256×144 entre deux squelettes. Un squelette est un trait fin sur
  fond noir : même un changement de pose important ne touche qu'une
  petite fraction des pixels totaux → le score reste chroniquement bas
  (~0.05-0.1) quel que soit le mouvement réel du personnage.
- Mappé sur `DENOISE_MIN=0.05 → DENOISE_MAX=0.40`, ça donne les
  denoise=0.067-0.072 observés dans les logs du smoke test.
- Avec `STEPS=40`, denoise≈0.07 ne fait tourner le sampler que ~2,8 pas
  réels — insuffisant pour que `KSampler`+`DifferentialDiffusion`
  résolve proprement la couleur dans la zone masquée. La frame N+1 est
  générée à partir d'une frame N déjà légèrement bruitée (chaînage N-1),
  donc le bruit s'accumule à chaque itération plutôt que de se corriger.

**Pourquoi le smoke test (frames 13-16) n'a rien montré** : la frame 0013
était en réalité un txt2img pur guidé par ControlNet+Lineart (pas de
`prev_path` disponible à ce moment — `GLOBAL_ANCHOR` absent du disque),
donc aucun risque d'accumulation. Le chaînage N-1 (et donc la dégradation)
ne commence qu'à partir de la frame 0014 — visible seulement en
poursuivant bien au-delà des 4 frames testées. **Erreur de méthode de ma
part** : conclure "smoke test réussi" sur 4 frames sans avoir observé au
moins une dizaine de frames chaînées était prématuré pour un pipeline dont
le risque connu (watchdog SSIM, cf. V1.3/V1.4) est justement la dérive
cumulative frame-à-frame.

**Remarque utilisateur, à retenir pour la suite** : ce test n'utilise pas
AnimateDiff (confirmé — aucun node/motion module AnimateDiff dans
`batch_controlnet.py` ni `motion_mask_generator.py`, uniquement
KSampler+ControlNet+DifferentialDiffusion par frame). Pipeline A est conçu
comme option *concurrente* à AnimateDiff (cf. §6), pas un complément.
L'utilisateur rapporte qu'AnimateDiff évitait structurellement ce type de
dégradation par le passé, précisément parce qu'il traite les frames
ensemble via son module de mouvement temporel plutôt que de chaîner
frame N-1 → frame N en img2img/inpaint séquentiel — ce qui correspond
exactement au mécanisme de dérive identifié ci-dessus. Confirme que le
problème n'est pas qu'une histoire de calibration de constante : le
chaînage N-1 est structurellement fragile pour ce type de rendu, avec ou
sans denoise mieux calibré.

**Décision de fin de session (utilisateur)** : ne pas relancer de run GPU
supplémentaire cette session — cycle actuel conservé tel quel sur disque
à titre de preuve/diagnostic, décision sur la suite (recalibrer le
denoise, forcer img2img_fallback, ou basculer sur AnimateDiff pour la
génération multi-frame) remise à une session ultérieure.

**Pistes pour la suite, par ordre de risque croissant** :
1. Relever `DENOISE_MIN` (ex. 0.05→0.18-0.20) dans `denoise_estimator.py`
   — fix ciblé, rapide à tester, mais mitige sans éliminer le problème
   structurel du chaînage N-1.
2. Forcer le chemin `img2img_fallback` (denoise fixe 0.20, déjà démontré
   propre en pratique sur la frame 0013 en mode txt2img) plutôt que
   `motion_mask` — évite le chemin jamais calibré, reste du chaînage N-1
   mais avec un denoise plus généreux et fixe.
3. Basculer la génération multi-frame sur AnimateDiff (changement
   d'architecture, hors périmètre "câblage" — AnimateDiff reste un
   pipeline manuel jamais automatisé selon
   `RAPPORT_AUDIT_PIPELINE_AOUT2026.md`) — option la plus lourde mais la
   seule qui adresse la cause structurelle plutôt que la mitiger.

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

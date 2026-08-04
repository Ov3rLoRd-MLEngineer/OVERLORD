# Comparaison AnimateDiff (32 frames) vs AniSora V3.2 I2V (ancrage stylisé)

Date : 2026-08-04/05, session `BRIEF_SESSION_PIPELINE_04082026.md` (Bureau), tâche 1.

## Contexte d'exécution — deux OOM avant succès

- **Run 1 (RTX 5060 Ti, 1024x1536)** : lancé normalement, mais après 16m51s le
  premier step affichait une ETA de **10h57** (`1011.34s/it`) — signe clair de
  blocage/thrashing, pas d'une simple lenteur. Interrompu via `POST /interrupt`
  (confirmé : `execution_interrupted` sur le node KSampler), VRAM redescendue
  immédiatement après.
- **Run 2 (RTX 5080, même résolution 1024x1536)** : relancé sur RTX 5080 (2x
  plus rapide sur les tests ponctuels d'après la convention CLAUDE.md) —
  util. GPU stable 100 % pendant ~4 min, VRAM pinnée à 15,9 Go/16 Go, puis
  **`torch.AcceleratorError: CUDA error: out of memory`** signalé par
  l'utilisateur directement depuis la fenêtre ComfyUI.
- **Fix appliqué** : résolution ramenée à **512x768** (repli explicitement
  prévu par la consigne de session en cas d'OOM à résolution supérieure) +
  relance de l'instance ComfyUI RTX 5080 avec le flag **`--lowvram`**
  (offloading modèle agressif — substitut concret à "activer xformers" côté
  ComfyUI moderne, qui n'expose pas xformers comme option de workflow mais
  comme flag de lancement). Process ComfyUI précédent (PID corrompu après
  l'OOM, API ne répondant plus correctement) arrêté et relancé proprement.
- **Run 3 (RTX 5080, 512x768, `--lowvram`)** : **succès**, aucune erreur de
  nœud. VRAM stable ~11,7 Go/16 Go (util. 77-99 %, pas de blocage). **254,4 s**
  pour les 32 frames. 32/32 fichiers confirmés sur disque
  (`Anisora Test/animatediff_32frames/frame_00001_.png` à `frame_00032_.png`).

**Conséquence pour la comparaison ci-dessous** : le résultat AnimateDiff
analysé est à **512x768**, pas à la résolution native 1024x1536 des tests
16 frames précédents (`ADDENDUM_WORKFLOW_ANIMATEDIFF.md`) — la comparaison de
qualité absolue avec AniSora (480x720, résolution native du pipeline WAN) est
donc à lire avec cette réserve : une partie du flou observé ci-dessous est
probablement imputable à la résolution réduite, pas uniquement à
l'architecture SDXL+AnimateDiff elle-même.

## Workflow utilisé

`workspace/comfyui_workflows/animatediff_32frames_style_anchor.json` — dérivé
de `animatediff_sdxl_cn_test animatediff fonctionne.json` (le fichier "fonctionne"
identifié dans `ADDENDUM_WORKFLOW_ANIMATEDIFF.md`, pas la version sans
IPAdapter). Écarts nécessaires par rapport au fichier source :

- **`ADE_AnimateDiffLoaderGen2` → `ADE_AnimateDiffLoaderGen1`** : le fichier UI
  source référence Gen2, mais grep direct dans
  `ComfyUI-AnimateDiff-Evolved/animatediff/nodes.py` confirme que **seul Gen1
  est enregistré** sur cette installation (`NODE_CLASS_MAPPINGS` ne contient
  pas Gen2, seulement en commentaire `# Gen2 Nodes`) — cohérent avec la note
  déjà présente dans CLAUDE.md ("Gen2 indisponible sur ce poste"), le fichier
  UI exporté était donc déjà non exécutable tel quel via l'API.
- **`VHS_LoadImages` → `VHS_LoadImagesPath`** : le node `VHS_LoadImages`
  actuellement enregistré (`LoadImagesFromDirectoryUpload`) attend un nom de
  sous-dossier d'`input/` (menu déroulant), pas un chemin absolu libre — le
  fichier UI source utilisait une ancienne signature. `VHS_LoadImagesPath`
  (`LoadImagesFromDirectoryPath`) est la variante actuelle acceptant un chemin
  absolu (`directory` en `STRING` libre), utilisée ici pour pointer directement
  vers `DEMO/frames/skeletons_1024x1024` et `DEMO/frames/mixamo_raw` sans
  copie dans `input/`.
- Prompt positif/négatif remplacé par celui des tests AniSora de cette session
  (comparaison directe demandée par la consigne), au lieu des tags SDXL
  `score_9, score_8_up...` du fichier source.
- Image d'ancrage IPAdapter : `mask_test__00001_.png` (identique aux tests
  AniSora), au lieu de la première frame de `mixamo_raw/` utilisée dans le
  fichier source.
- 32 frames (`EmptyLatentImage.batch_size` + `image_load_cap` des deux
  `VHS_LoadImagesPath`), résolution 512x768 après le fix OOM (voir ci-dessus).
- Reste identique au fichier "fonctionne" : `fabricatedXL_v70` + LoRA Asuka
  (0.75/0.75), `mm_sdxl_v10_beta.safetensors`, 2x ControlNet (OpenPose
  strength 1.25 + Lineart strength 1.25, `resolution=512` sur le préprocesseur
  Lineart), IPAdapter (poids 0.70, plage 0.0-0.30), `KSampler` 40 steps,
  cfg 6.5, `euler_ancestral`/`normal` (écart volontaire à ADR-003, déjà
  documenté dans CLAUDE.md pour ce workflow spécifique).

Sortie : `SaveImage` directement vers
`output/Anisora Test/animatediff_32frames/frame_%05d.png` — **pas de MP4 à
extraire** contrairement à ce que supposait la consigne ("extraire via
ffmpeg") : ce pipeline AnimateDiff traite un batch de 32 frames en une seule
passe de diffusion et les enregistre déjà comme fichiers individuels via
`SaveImage` (aucun nœud `VHS_VideoCombine` dans le fichier source "fonctionne").
Écart appliqué sciemment plutôt que d'ajouter un aller-retour PNG→MP4→PNG
inutile.

## Inspection visuelle — frames 1, 8, 16, 24, 32

### Constat principal : artefact de fond coloré (pas de fond blanc pur)

Les 5 frames échantillonnées montrent toutes un **halo de couleur** autour du
personnage — dégradé jaune/orange sur le bord gauche, cyan/bleu clair
enveloppant le personnage, blanc au centre — malgré le prompt positif
explicite `"pure white background"` (hérité du fichier "fonctionne") et le
négatif listant `"gray background, dark background, gradient background"`.
**Ce n'est pas un nouveau bug** : `ADDENDUM_WORKFLOW_ANIMATEDIFF.md` documentait
déjà un comportement non déterministe similaire ("Run B : fond gris/cyan,
hoodie noir totalement saturé") sur ce même workflow à 16 frames, avec la
même config visuellement — confirme que le problème de fond n'a jamais été
réellement résolu, seulement observé de façon inconsistante d'un run à l'autre.

### Netteté / détail : nettement en retrait par rapport à AniSora

Comparé à la frame de référence AniSora ancrage stylisé (`TEST_ANISORA_V32_SMOKE.md`,
section "Ancrage stylisé SDXL") : les lignes de contour, les yeux, les plis du
hoodie et le design des sneakers sont **beaucoup plus flous et moins définis**
ici. Cheveux orange et pince rouge encore identifiables, mais le rendu global
est diffus/laiteux plutôt que net et "cel-shaded" comme sur AniSora. Une part
de cet écart est probablement imputable à la résolution forcée à 512x768
(voir réserve ci-dessus) — SDXL est généralement entraîné/optimisé pour des
résolutions plus élevées (1024 et au-delà), un modèle WAN comme AniSora est
nativement conçu pour ces résolutions vidéo plus basses.

### Cohérence temporelle intra-run (frames 1→32) : stable, pas de drift progressif

Malgré l'artefact de fond et le flou général, **le design du personnage reste
cohérent sur les 5 frames échantillonnées** : cheveux orange + pince rouge
visible à chaque frame, hoodie sombre, jean bleu, sneakers rouge/blanc
(silhouette reconnaissable même floue). Pas de dérive de couleur progressive
ni de changement de design perceptible entre la frame 1 et la frame 32 — dans
ce sens précis (stabilité du personnage sur la durée du batch), le mécanisme
AnimateDiff + ControlNet + IPAdapter remplit son rôle.

### Pieds / mains

Difficile à évaluer précisément à cause du flou général : les sneakers
gardent leur teinte rouge/blanc reconnaissable sur toutes les frames
échantillonnées (pas de fusion de couleur ni de disparition), mais les
contours précis (semelle, logo) ne sont pas nets. Les mains sont des masses
peu détaillées sur toutes les frames — impossible de vérifier le nombre de
doigts ou une éventuelle déformation à ce niveau de flou, contrairement aux
tests AniSora où les mains restaient suffisamment nettes pour une inspection
qualitative.

## Comparaison directe — tableau de synthèse

| Critère | AnimateDiff (SDXL, 32f, 512x768) | AniSora V3.2 I2V (ancrage stylisé, 37f, 480x720) |
|---|---|---|
| Fond | Halo coloré jaune/cyan, pas de blanc pur malgré le prompt | Blanc/quasi-uniforme, conforme au prompt |
| Netteté | Flou/laiteux, lignes peu définies | Net, "cel-shaded", cohérent avec le style anime |
| Cohérence intra-clip | Stable (pas de drift de design sur 32 frames) | Stable (pas de drift sur 37 frames) |
| Mains/pieds | Non évaluables précisément (flou) | Globalement corrects, 1 frame/5 avec léger flou |
| Temps de génération | 254,4 s (après fix, RTX 5080, `--lowvram`) | 182,5 s (RTX 5080, sans `--lowvram`) |
| Stabilité du pipeline | 2 OOM avant succès (1024x1536 sur les deux GPU) | Aucun OOM, VRAM crête ~9 Go/16 Go |

## Verdict

**AniSora V3.2 I2V (ancrage stylisé) reste nettement supérieur** sur cette
comparaison directe, à la fois en qualité visuelle (fond propre, netteté) et
en stabilité opérationnelle (aucun OOM, VRAM très en dessous du plafond). Le
pipeline AnimateDiff testé ici — hérité d'une session antérieure (juin 2026)
et jamais totalement stabilisé (cf. le comportement non déterministe déjà
documenté dans `ADDENDUM_WORKFLOW_ANIMATEDIFF.md`) — nécessiterait un travail
de fiabilisation significatif (résoudre l'artefact de fond, retrouver une
résolution correcte sans OOM, par exemple en désactivant l'IPAdapter comme le
suggérait déjà l'addendum de juin) avant d'être une alternative crédible à
AniSora pour ce pipeline. Aucune modification de code n'a été faite pour
tenter de corriger le fond coloré (hors périmètre "une tâche = un test" de
cette session) — piste à explorer si ce pipeline est repris.

## Ce qui reste ouvert

1. **Artefact de fond coloré non résolu** — cause non diagnostiquée
   (comportement déjà non déterministe en juin 2026, donc pas nécessairement
   lié aux changements de cette session : prompt, ancrage, 32 frames).
2. **Résultat à 512x768 seulement** — pas de comparaison possible avec la
   résolution native 1024x1536 pour cette exécution précise (les deux tests à
   cette résolution ont fini en OOM). Retester à 1024x1536 nécessiterait de
   désactiver l'IPAdapter (piste déjà identifiée dans
   `ADDENDUM_WORKFLOW_ANIMATEDIFF.md`, jamais vérifiée) ou de réduire le
   nombre de frames.
3. **`xformers` non testé littéralement** — ComfyUI moderne n'expose pas de
   nœud/flag "xformers" dédié dans cette installation (attention SDPA PyTorch
   déjà utilisée par défaut) ; le flag `--lowvram` (offloading modèle) a servi
   de substitut fonctionnel pour tenir en VRAM, conformément à l'intention de
   la consigne plutôt qu'à sa lettre exacte.

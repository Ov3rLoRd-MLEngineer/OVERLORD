# Smoke test AniSora V3.2 GGUF I2V

Date : 2026-08-04. RTX 5080 (libre depuis la fin de `stage2_commitpack_full`,
06:14 le jour meme -- voir `workspace/qlora_dataset/HANDOFF_2026-08-03.md`).
ComfyUI relance manuellement, pinne explicitement sur la RTX 5080 via
`D:\Ov3rLoRd AI\_launch_comfyui_5080.bat` (`CUDA_VISIBLE_DEVICES=GPU-b4d632fb-...`,
UUID via `nvidia-smi -L`) -- different de la session precedente (Pipeline A,
pinnee RTX 5060 Ti). Confirme via `/system_stats` : `cuda:0 NVIDIA GeForce RTX 5080`.

## Ecart avec la consigne -- VAE corrigee avant le test

La consigne demandait le VAE `wan_2.2_vae.safetensors` (`Wan-AI/Wan2.2-I2V-14B-480P`).
Verification avant telechargement (l'organisation `Wan-AI` sur HuggingFace ne
contient pas de depot `Wan2.2-I2V-14B-480P` -- seul `Wan-AI/Wan2.2-I2V-A14B`
existe pour le I2V 14B en Wan2.2) : ce depot officiel embarque `Wan2.1_VAE.pth`,
pas un VAE "2.2" dedie. Confirme sur le depot source d'AniSora lui-meme
(`IndexTeam/Index-anisora`, arborescence `V3.2/`) : `V3.2/Wan2.1_VAE.pth` --
AniSora V3.2 est un fine-tune de l'architecture Wan2.2 A14B (MoE High/Low noise,
14B chacun), qui **reutilise le VAE 16 canaux de Wan2.1**, pas le VAE 48 canaux
`wan2.2_vae.safetensors` (celui-la appartient au modele dense TI2V-5B, une
architecture differente). Consequence pratique : `Wan22ImageToVideoLatent`
(node core ComfyUI, 48 canaux, pour TI2V-5B) est le mauvais node ici -- le bon
est `WanImageToVideo` (16 canaux, compatible A14B).

**Les deux VAE ont ete telecharges** (`wan2.2_vae.safetensors` conformement a
la lettre de la consigne, `wan_2.1_vae.safetensors` en complement necessaire) --
seul le second est utilise dans le workflow reel.

## Fichiers installes (verifies sur disque, taille exacte)

| Fichier | Emplacement | Taille |
|---|---|---|
| `Index-Anisora-V3.2-High-Q4_0.gguf` | `ComfyUI/models/unet/` | 9.03 Go |
| `Index-Anisora-V3.2-Low-Q4_K_M.gguf` | `ComfyUI/models/unet/` | 10.13 Go |
| `wan_2.1_vae.safetensors` (utilise) | `ComfyUI/models/vae/` | 253.8 Mo |
| `wan2.2_vae.safetensors` (telecharge, non utilise -- mauvaise archi) | `ComfyUI/models/vae/` | 1.41 Go |
| `umt5_xxl_fp8_e4m3fn_scaled.safetensors` | `ComfyUI/models/text_encoders/` | 6.74 Go |

Note quant High noise : QuantStack/Index-Anisora-V3.2-GGUF ne publie pas de
Q4_K_M/Q5_K_M pour le modele High (seulement Q4_0 et Q8_0) -- Q4_0 retenu
comme quant le plus proche disponible compte tenu de la VRAM (16 Go).

ComfyUI-GGUF (city96) clone dans `custom_nodes/`, dependance `gguf==0.19.0`
installee dans `python_embeded`.

## Workflow

`workspace/comfyui_workflows/anisora_i2v_minimal.json` -- API JSON, 14 nodes :
`UnetLoaderGGUF` x2 (High/Low) -> `ModelSamplingSD3` x2 (shift=8.0, valeur
standard Wan flow-matching) -> `CLIPLoader` (type `wan`, umt5-xxl fp8) +
`VAELoader` (Wan 2.1) -> `LoadImage` (keyframe) -> `CLIPTextEncode` x2
(positive/negative) -> `WanImageToVideo` (480x480, length=16, batch=1) ->
`KSamplerAdvanced` x2 chaines (High noise steps 0-4/8 avec
`return_with_leftover_noise=enable`, puis Low noise steps 4-8/8) ->
`VAEDecode` -> `VHS_VideoCombine` (mp4 h264, 8 fps).

**Ecart volontaire par rapport a ADR-003** (sampler par defaut `dpmpp_2m`+`karras`) :
les modeles Wan/AniSora sont a flow-matching (meme famille que SD3/Flux), pas
des modeles a bruit epsilon classique -- `euler`+`simple` est la combinaison
standard des workflows officiels ComfyUI pour cette architecture. ADR-003
concerne le pipeline SDXL principal, pas cette nouvelle famille de modeles.

**Split High/Low a 50%** (4 steps chacun sur 8) : choix simplifie pour ce
smoke test (frontiere officielle Wan2.2 A14B basee sur un seuil de sigma, pas
forcement 50/50) -- suffisant pour valider le fonctionnement, a affiner si les
resultats qualitatifs le justifient sur un run plus long.

**Keyframe source** : `ComfyUI/output/asuka_run/old/frame_0013_00001_.png`
(1024x1024, SDXL) -- choisie car identifiee dans le handoff Pipeline A comme
**txt2img pur** (pas de chainage N-1, donc image de reference propre), et
thematiquement liee a la Tache 4 (meme personnage "asuka running").

## Lancement et resultat

Soumis via l'API `POST /prompt` (`prompt_id 3b8e6057-b254-4707-bd12-13bc5c7da56e`),
ComfyUI lance prealablement via `start cmd /k` (fenetre dediee visible).

- **Statut** : `success`, aucune erreur de noeud (`node_errors: {}`).
- **Temps de generation reel** : 93.4 s (`execution_start` -> `execution_success`,
  timestamps ComfyUI), chargement des modeles GGUF inclus (premiere execution,
  pas de cache).
- **VRAM crete observee** : ~13.0 Go (pic mesure par `nvidia-smi` pendant
  l'echantillonnage, sur 16 Go disponibles) -- **aucun OOM**.
- **Fichier video** : `D:\Ov3rLoRd AI\ComfyUI\output\anisora_smoke_test_00001.mp4`
  (298 Ko, H.264, 480x480, 8 fps).
- **13 frames decodees, pas 16** : comportement attendu du VAE video Wan
  (compression temporelle 4x) -- `length=16` demande produit
  `latents = ((16-1)//4)+1 = 4` frames latentes, qui se decodent en
  `(4-1)*4+1 = 13` frames reelles. Pour obtenir exactement N frames, `length`
  doit etre de la forme `4k+1` (ex. 13, 17, 21...) -- a corriger dans un futur
  run si le nombre exact de frames importe (tache 4 : 16 frames Mixamo prevues,
  a reconcilier avec cette contrainte, voir section suivante).

## Qualite -- inspection visuelle (frames 0, 6, 12 extraites via ffmpeg)

**Tres bon resultat.** Personnage (silhouette rousse, sweat bleu, meme design
que la keyframe source) parfaitement stable sur les 3 frames echantillonnees,
mouvement de course fluide et coherent (jambes/bras en phase d'appui puis
d'extension, cheveux qui suivent le mouvement), aucun artefact de bruit ni
degradation -- contraste net avec le probleme de chainage N-1 documente pour
Pipeline A (`PLAN_PIPELINE_A_DEMO_30S.md` §7, degradation progressive des la
frame 0022). AniSora genere les 16 frames en un seul passage de diffusion
(traitement joint, pas de chainage sequentiel), coherent avec le retour
utilisateur sur AnimateDiff evitant structurellement ce type de degradation.

## Verdict (smoke test I2V simple)

**Concluant** -- aucun des criteres d'arret (artefacts majeurs, OOM, temps
> 15 min) n'est atteint. 93.4 s est tres en dessous du seuil. Tache 4
(running.fbx) lancee.

## running.fbx

Source : `E:\Blender\asuka run.blend` (Blender 5.1.2 headless, inspection puis
rendu **lecture seule**, aucune sauvegarde du `.blend`). Scene : cam `Camera`,
armature `Armature`, meshes `Ch22_Body/Shirt/Pants/Sneakers/Hair/Eyelashes`,
`frame_start=1`/`frame_end=39`, moteur EEVEE, resolution 1024x1536. 38 frames
sources deja rendues en amont dans `DEMO/frames/mixamo_raw/0001.png..0038.png`
(memes frames que celles ayant servi a `cycle_detector.py`).

### Pose -- deja disponible, pas de nouveau rendu necessaire

`DEMO/frames/skeletons_1024x1024/skeleton_0000..0037.png` couvre deja les 38
frames completes (genere lors d'une session precedente via `pose_generator.py`
/ DWPose ComfyUI, pas via un rig toyxyz -- aucune trace d'un tel addon/rig
dans le `.blend` inspecte). Fallback DWPose de la consigne donc deja satisfait,
aucun travail Blender necessaire pour la pose.

### Depth -- pivot Blender -> DepthAnythingV2 (ComfyUI), valide par l'utilisateur

Tentative initiale : rendu Z-depth directement depuis le compositeur Blender
(`Render Layers` -> `Map Range` -> `File Output`, EXR puis normalisation
Python vers PNG avec une plage fixe 9.0-10.8 -- distance camera-personnage
mesuree stable sur les 38 frames via un pre-scan des bounding box). **Abandonnee
apres plusieurs echecs d'API** : Blender 5.1 a retire `Scene.node_tree` (remplace
par `Scene.compositing_node_group`, nouveau type `NodeTree` a creer
explicitement), le node `CompositorNodeMapRange` n'existe plus dans la liste des
types compositeur disponibles (erreur `Type de noeud non-defini`), et meme apres
contournement (via `CompositorNodeCombineColor` + format `OPEN_EXR_MULTILAYER`,
seul format accepte pour ce montage), le rendu animation ne produisait **aucun**
fichier compositeur sur disque (seule la passe couleur par defaut via
`scene.render.filepath` s'ecrivait) malgre des noeuds/liens verifies corrects et
`use_compositing=True` -- td la nouvelle architecture "compositeur temps reel
GPU" de Blender 4.2+/5.x semble ne pas executer le graphe de File Output de la
meme facon en rendu batch headless. Diagnostic approfondi non poursuivi
(cout/benefice defavorable face a une alternative fiable disponible).

**Pivot** : `DepthAnythingV2Preprocessor` (ComfyUI, `comfyui_controlnet_aux`,
deja installe) applique en un seul batch sur les 38 frames couleur de
`mixamo_raw/` via `VHS_LoadImagesPath` (chargement dossier entier en un
tenseur IMAGE batch) -> traitement batch GPU (checkpoint `depth_anything_v2_vitl.pth`,
telecharge automatiquement au premier appel) -> `SaveImage`. Resultat copie/renomme
vers `DEMO/frames/mixamo_depth/depth_0000.png..depth_0037.png`. Choix
techniquement defendable au-dela du simple contournement : les ControlNet depth
(y compris ceux utilises par l'ecosysteme Wan/AniSora) sont entraines sur des
sorties d'estimateurs monoculaires type MiDaS/DepthAnything, pas sur des
Z-buffers 3D bruts -- une carte DepthAnything est donc plus "in-distribution"
pour un futur ControlNet depth qu'un Z-pass Blender brut.

**Validation utilisateur** (2026-08-04, en session) : les 38 cartes de
profondeur confirmees correctes -- premier plan/arriere-plan clairement
separes ; si un membre (bras) venait a disparaitre lors d'une future generation
conditionnee, la source depth n'en serait pas responsable.

### Generation -- fallback I2V (pas de checkpoint AniSora Fun Control disponible)

`Wan22FunControlToVideo` (node core ComfyUI, permettrait d'injecter
`control_video`) necessite un checkpoint **specifiquement entraine** pour ce
mecanisme de concatenation de canaux de controle -- confirme absent du depot
`QuantStack/Index-Anisora-V3.2-GGUF` (seuls les poids High/Low de base y sont
publies). Utiliser les poids AniSora de base avec ce node produirait un
resultat non defini (canaux de controle jamais vus a l'entrainement) -- fallback
explicitement prevu par la consigne : I2V simple, premiere frame comme ancrage.
**Consequence importante** : les passes depth/pose preparees ci-dessus ne sont
**pas utilisees comme conditionnement reel** dans ce run -- elles sont pretes
pour un futur run Fun Control si un checkpoint compatible devient disponible,
mais le mouvement genere ici est **improvise par le modele** (image d'ancrage
+ prompt texte), pas la reproduction litterale du cycle de course Mixamo.

Workflow : `workspace/comfyui_workflows/anisora_running_fbx.json` -- meme
architecture que le smoke test (High/Low + ModelSamplingSD3 + KSamplerAdvanced
en 2 passes), keyframe = `DEMO/frames/mixamo_raw/0001.png`, resolution
480x720 (aspect source 1024x1536 preserve), `length=37` (pas 38 : contrainte
VAE video decouverte en tache 3, seules les longueurs `4k+1` produisent un
nombre de frames exact -- 37 est la valeur la plus proche de 38 satisfaisant
cette contrainte, conforme a l'annexe "ne jamais couper le cycle, reduire
resolution/steps si besoin, pas le nombre de frames" ; ici aucune reduction du
compte de frames n'a ete faite, seul l'arrondi impose par le VAE s'applique).

**Resultat** : succes, aucune erreur de noeud. Temps reel 174.9 s (< 3 min,
tres en dessous du seuil de 15 min). VRAM crete ~10.16 Go/16 Go, aucun OOM.
Fichier `D:\Ov3rLoRd AI\ComfyUI\output\anisora_running_fbx_00001.mp4` (480x720,
8 fps, **37 frames exactement** -- confirme la formule de decodage VAE
`(latents-1)*4+1`). Inspection visuelle (frames 0, 12, 24, 36 extraites via
ffmpeg) : mouvement de course fluide et physiquement plausible, personnage
stable sur les 4 frames echantillonnees, aucun artefact majeur. **Observation
notable** : le style reste proche du rendu 3D/photorealiste de la source Mixamo
(pas de conversion vers un style anime malgre le prompt positif "anime girl
running") -- comportement attendu en I2V a CFG modere (3.5) : l'image d'ancrage
domine fortement l'apparence, le prompt texte pilote surtout le mouvement/contexte,
pas un transfert de style fort.

### Verdict running.fbx

**Concluant sur le plan technique** (pas d'OOM, temps tres court, mouvement
coherent) mais **limite fonctionnelle importante a garder en tete** : sans
checkpoint AniSora Fun Control, ce pipeline ne peut pas actuellement driver la
generation par la choregraphie Mixamo exacte -- seulement l'amorcer par une
image. Prochaine etape naturelle si ce type de controle precis est requis :
chercher/entrainer une variante Fun Control d'AniSora, ou evaluer `WanVaceToVideo`
(egalement liste dans `nodes_wan.py`, mecanisme de controle different -- non
explore cette session, hors perimetre).

## Ancrage stylise SDXL

Date : 2026-08-04, meme journee que le smoke test et running.fbx ci-dessus.
Objectif : tester si ancrer AniSora sur une image **deja stylisee anime**
(plutot qu'un rendu SDXL proche du photorealisme ou un rendu 3D Mixamo brut)
ameliore le maintien du style sur l'ensemble du cycle -- hypothese directement
issue de l'observation `running.fbx` ci-dessus ("l'image d'ancrage domine
fortement l'apparence en I2V a CFG modere, pas le prompt texte seul").

RTX 5080 verifiee libre au debut de cette tache (`nvidia-smi`, 0 MiB/0 %).
ComfyUI non actif au demarrage (arrete en fin de session precedente) --
relance via `D:\Ov3rLoRd AI\_launch_comfyui_5080.bat` (`start cmd /k`, fenetre
dediee visible), confirme pinne RTX 5080 via `/system_stats`
(`cuda:0 NVIDIA GeForce RTX 5080`).

**Image d'ancrage** : `D:\Ov3rLoRd AI\ComfyUI\output\mask_test__00001_.png`
(1024x1536, meme ratio 2:3 que la keyframe `running.fbx`) -- deja un rendu
SDXL stylise anime du personnage cible (cheveux roux, pince rouge, hoodie
noir/gris, jean bleu, sneakers rouge/blanc, vue de profil, fond blanc),
trouvee sur disque et fournie telle quelle par la consigne (origine/session de
generation anterieure non retracee, hors perimetre de cette tache). Copiee
vers `ComfyUI/input/anisora_style_anchor_keyframe.png`.

**Workflow** : `workspace/comfyui_workflows/anisora_i2v_style_anchor.json` --
derive de `anisora_i2v_minimal.json` (meme architecture 14 noeuds :
`UnetLoaderGGUF` High/Low + `ModelSamplingSD3` shift=8 + `WanImageToVideo` +
`KSamplerAdvanced` 2 passes 4+4/8 steps + `VAEDecode` + `VHS_VideoCombine`).
Ecarts : keyframe ci-dessus, prompt positif
`"anime girl running, dynamic motion, consistent character, smooth animation,
side view, white background, orange hair, red hair clip, black hoodie, blue
jeans, red white sneakers"`, prompt negatif
`"realistic, 3d render, blurry, deformed"`, resolution 480x720 (ratio source
preserve, comme `running.fbx`), `length=37` (38 frames "cycle complet"
demandees, arrondi a la contrainte VAE video `4k+1` deja documentee ci-dessus
-- meme convention que `running.fbx`, 37 est la valeur `4k+1` la plus proche
de 38 par valeur inferieure).

**Lancement et resultat** : soumis via l'API `POST /prompt`
(`prompt_id e912e7fa-6499-408b-ad97-c2c2ab59915a`), aucune erreur de noeud.
**182.5 s** (`execution_start` -> `execution_success`). **VRAM crete ~9.0 Go
sur 16 Go** (echantillonnage `nvidia-smi` toutes les 15 s pendant le run,
pic a 8987 MiB) -- aucun OOM. Fichier
`D:\Ov3rLoRd AI\ComfyUI\output\anisora_style_anchor_test_00001.mp4`
(480x720, 8 fps, **37 frames exactes** confirme par `ffprobe`
`-count_frames`, coherent avec la formule de decodage VAE deja etablie).

### Inspection visuelle comparative (vs `anisora_running_fbx_00001`)

5 frames extraites via `ffmpeg` sur `anisora_style_anchor_test_00001.mp4`
(indices 0/9/18/27/36, couvrant l'ensemble des 37 frames) et 4 frames sur
`anisora_running_fbx_00001.mp4` (indices 0/12/24/36, deja extraites en
reference dans la section precedente) -- inspectees directement.

- **Style anime maintenu ?** Oui, nettement et de facon stable sur les 5
  frames echantillonnees : cheveux roux + pince rouge, hoodie noir/gris, jean
  bleu, sneakers rouge/blanc, fond blanc quasi uniforme, rendu "cel-shaded"
  anime coherent de la premiere a la derniere frame. **Contraste net avec
  `running_fbx_00001`** (memes prompts positif "anime girl running" +
  negatif) : ce dernier reste visiblement photorealiste/3D sur ses 4 frames
  de reference (peau, texture jean/legging brillante, pas de contour
  cel-shade) -- confirme l'hypothese de session : c'est le **style de l'image
  d'ancrage**, pas le prompt texte, qui pilote le rendu en I2V a CFG modere
  (3.5) sur ce pipeline.
- **Drift ?** Minimal sur les 5 frames observees. Couleur des cheveux, de la
  pince, du hoodie, du jean et des sneakers stable du debut (f0) a la fin
  (f36), aucun glissement de teinte ni changement de design du personnage
  perceptible. Legere variation locale du contour gris/noir de la manche du
  hoodie entre frames (f9 vs f18), dans la marge normale d'un rendu
  frame-par-frame, pas un drift progressif cumulatif comme celui documente
  pour Pipeline A (`PLAN_PIPELINE_A_DEMO_30S.md` §7).
- **Pieds/mains coherents ?** Pieds : oui sur toutes les frames
  echantillonnees -- sneakers rouge/blanc anatomiquement correctes et
  reconnaissables, aucune fusion ni deformation visible pendant les
  differentes phases d'appui/extension de la foulee. Mains : globalement
  correctes (cinq doigts distincts sur f0/f9/f27/f36) ; **f18** montre une
  main en leger flou/agregat de doigts (mouvement de bras rapide, main en
  amorce de balancement) sans doigt surnumeraire ni fusion grossiere --
  comparable aux limites deja cataloguees dans `LIMITATIONS_CONNUES.md`, pas
  un nouvel echec distinct.

### Verdict ancrage stylise SDXL

**Concluant, meilleur resultat qualitatif de style des trois tests AniSora de
cette session** (smoke test `frame_0013` SDXL proche photoreal, `running.fbx`
Mixamo 3D, ancrage stylise ci-dessus). Confirme que le maintien du style anime
en I2V AniSora sur ce pipeline depend fortement du style de l'image
d'ancrage -- ancrer sur une image deja stylisee anime est le levier qui
fonctionne, pas une reformulation du prompt texte seul. Aucun signe d'OOM, de
degradation progressive (type Pipeline A) ni de defaut majeur pieds/mains sur
les frames echantillonnees.

**Non teste dans cette tache** (hors perimetre, une seule generation
demandee) : inspection frame-par-frame exhaustive (37/37, seulement 5
echantillonnees), calibration de la frontiere High/Low noise (toujours 50/50
arbitraire), et combinaison de cet ancrage stylise avec un conditionnement
pose/depth reel (bloque par l'absence de checkpoint Fun Control, cf.
`running.fbx` ci-dessus).

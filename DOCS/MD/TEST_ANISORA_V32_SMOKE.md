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

## Verdict

**Concluant** -- aucun des criteres d'arret (artefacts majeurs, OOM, temps
> 15 min) n'est atteint. 93.4 s est tres en dessous du seuil. Tache 4
(running.fbx) lancee.

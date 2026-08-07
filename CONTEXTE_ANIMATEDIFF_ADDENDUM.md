# ADDENDUM AnimateDiff — À ajouter au CONTEXTE_OVERLORD_V226.md

## ÉTAT ANIMATEDIFF AU MOMENT DU SWITCH

### Ce qui fonctionne ✅
- ComfyUI-AnimateDiff-Evolved (Kosinkadink) v1.5.7 installé et actif
- mm_sdxl_v10_beta.safetensors en place (D:\Ov3rLoRd AI\ComfyUI\models\animatediff_models\)
- Test sans ControlNet : 16 frames générées, 11.6/16 Go VRAM ✅
- Workflow avec ControlNet batch en cours de génération au moment du switch

### Workflow AnimateDiff + ControlNet validé en UI
- Node : "AnimateDiff Loader 🎭🅐🅓①" (remplace ADE_AnimateDiffLoaderGen2 dans le JSON)
- VHS_LoadImages pour skeletons et lineart en batch
  - image_load_cap : 16
  - skip_first_images : 0
  - select_every_nth : 1
- Chemins : skeletons_1024x1024 et lineart_1024x1024
- EmptyLatentImage : 1024x1024 batch_size=16
- OpenPose CN : strength 1.25 / end 0.50
- Lineart CN : strength 1.25 / end 0.50
- KSampler : seed 527494254591352 / 40 steps / CFG 7.0 / dpmpp_2m / karras

### Résultats attendus dans la prochaine session
- D:\Ov3rLoRd AI\ComfyUI\output\animatediff_cn_test\
- 16 frames PNG à analyser pour cohérence temporelle et respect des poses

### Prochaine étape après validation
- Si OK : intégrer AnimateDiff dans batch_controlnet.py V2.0
  → Remplacer motion_mask par AnimateDiff sliding window 16 frames
  → overlap 2-4 frames entre blocs
- Reconstruire références depuis frames Kling brutes (bordures parasites)
- reference_aligner_v2.py : corriger mapping frame→lineart au-delà de 100

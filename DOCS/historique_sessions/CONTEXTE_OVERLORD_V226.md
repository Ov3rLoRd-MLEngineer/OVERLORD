# CONTEXTE_OVERLORD_V226.md
# Cerveau de Démarrage — Session 2026-06-28
# Pipeline Ov3rLoRd / Jérémy Gourlain
# Généré en fin de session — reprendre immédiatement sans questions superflues

---

## 0. CONTEXTE UTILISATEUR

**Jérémy Gourlain** — Le Havre, France. Développeur solo.
- BTS MUC + TFIC chimie industrielle
- Culture geek profonde : DBZ, EVA, Gundam, SAO Alicization, Gunnm, HxH...
- Objectif : film 24 minutes → pitch Khara (Noisy-le-Grand)
- Dévitalisation dentaire semaine prochaine

**Style de collaboration :**
- Toujours py -3.12 / create_file tool / ast.parse() / FORMAT A patcher
- "Ov3rLoRd" toujours (jamais OverLord)
- Force de proposition, pas d'initiatives non validées

---

## 1. ÉTAT RÉEL DU PIPELINE — V2.26

### Architecture validée
```
Source : frames Kling (D:\OVERLORD\DEMO\frames\frames\)
    ↓
DWPose → skeletons (D:\OVERLORD\DEMO\frames\skeletons\)
LineartExtractor → lineart_910x512 (D:\OVERLORD\DEMO\frames\lineart_910x512\)
    ↓
reference_aligner_v2.py → skeletons_1024x1024 + lineart_1024x1024
    ↓
batch_controlnet.py V1.9 → ComfyUI API
    → Frame 0    : txt2img (denoise 1.0, seed fixe)
    → Frames 1+  : motion_mask_generator.py (inpaint zones mouvement)
                   + denoise_estimator.py (denoise dynamique via diff PIL)
    ↓
frames_to_video.py → MP4 final
```

### Ce qui fonctionne ✅
- OpenPose (control-lora-openposeXL2-rank256) + Lineart (xinsir-controlnet-lineart-sdxl) ensemble
- `Use Image Preprocessor = false` — cause du bug historique
- RemBg PIL inline avant VAEEncode (seuil 200)
- Motion mask depuis diff squelettes (DifferentialDiffusion)
- Denoise dynamique estimée par diff PIL (0.05-0.40)
- Fond stable sur 10 frames ✅
- 10/10 succès sans WinError 32 ✅
- Résolution 1024x1024 (SDXL natif)
- PrepImageForClipVision pad pour IPA
- CLIP Skip -2

### Ce qui est en cours 🔧
- **AnimateDiff SDXL** — installation en cours (mm_sdxl_v10_beta.ckpt)
  → Remplacera le motion mask n-1 par cohérence temporelle sur 16 frames
  → Sliding window overlap 2-4 frames entre blocs
- **reference_aligner_v2.py** — bug lineart manquant au-delà de frame 0100
  → Les squelettes vont jusqu'à 0101+, lineart numérotés différemment
  → À corriger : mapping frame_num → lineart_num

### Ce qui reste à faire ❌
- Reconstruire les références depuis frames Kling brutes proprement
  (bordures Kling parasites dans le lineart actuel)
- Compléter lineart_1024x1024 au-delà de 100 frames
- frames_to_video.py pour assembler le MP4
- RemBg post-processing agent (batch sur toutes les frames générées)

---

## 2. AGENTS LIVRÉS SESSION 28/06/2026

| Agent | Version | Statut |
|-------|---------|--------|
| batch_controlnet.py | V1.9 | ✅ actif (racine + agents/) |
| motion_mask_generator.py | V1.1 | ✅ actif (agents/) |
| denoise_estimator.py | V1.0 | ✅ actif (agents/) |
| reference_aligner_v2.py | V1.0 | ✅ actif (agents/) |
| lineart_extractor.py | V1.1 | ✅ actif (agents/) |
| lineart_remapper.py | V1.0 | ✅ actif (agents/) |
| skeleton_remapper.py | V1.1 | ✅ actif (agents/) |
| frame_extractor.py | — | ✅ actif (agents/) |
| frames_to_video.py | — | ✅ actif (agents/) |

---

## 3. CONFIG COMFYUI VALIDÉE

```
Checkpoint    : fabricatedXL_v70.safetensors (NE JAMAIS MODIFIER)
LoRA          : asuka-langley-soryuu-classic-ponyxl-lora-nochekaiser.safetensors
LoRA weight   : 0.75
VAE           : taesdxl (permanent)
Résolution    : 1024x1024 (SDXL natif)
Steps         : 40
CFG           : 7.0
Sampler       : dpmpp_2m / karras
CLIP Skip     : -2 (CLIPSetLastLayer)

ControlNet 1  : control-lora-openposeXL2-rank256.safetensors
  strength    : 1.25 / start 0.0 / end 0.50
  preprocessor: NONE (Use Image Preprocessor = false)

ControlNet 2  : xinsir-controlnet-lineart-sdxl.safetensors
  strength    : 1.25 / start 0.0 / end 0.50
  preprocessor: LineartStandardPreprocessor (Use Image Preprocessor = false)

IPA           : ip-adapter-plus_sdxl_vit-h.safetensors
CLIP Vision   : model.safetensors (ViT-H-14)
IPA weight    : 0.70 / start 0.0 / end 0.30 / linear / K+V
PrepImage     : crop_position=pad (letterbox, pas de crop)

AnimateDiff   : mm_sdxl_v10_beta.ckpt (en cours d'installation)
  context     : 16 frames / sliding window overlap 2-4
```

---

## 4. PROMPTS VALIDÉS (PonyXL format)

```python
PROMPT_POS = (
    "score_9, score_8_up, score_7_up, source_anime, masterpiece, highly detailed, "
    "1girl, asuka shoryu langley, blue eyes, nike jordan sneakers, hoodie, "
    "detailed clothing textures, side view, profile, full body, run, "
    "concentrated expression, pure white background"
)
PROMPT_NEG = (
    "blurry, low quality, deformed, ugly, bad anatomy, bad eyes, bad hand, bad finger, "
    "extra limbs, watermark, text, logo, cartoon, anime, painting, 3d render, "
    "child, loli, overexposed, underexposed, plastic skin"
)
```

---

## 5. HARDWARE ET CHEMINS

```
GPU           : RTX 5080 16GB (13.7/16 Go utilisés avec IPA+ControlNet)
Python        : py -3.12 OBLIGATOIRE
ComfyUI       : D:\Ov3rLoRd AI\ComfyUI\ port 8188

Source frames : D:\OVERLORD\DEMO\frames\frames\
Skeletons src : D:\OVERLORD\DEMO\frames\skeletons\
Lineart src   : D:\OVERLORD\DEMO\frames\lineart_910x512\  (1008 fichiers)
Skel 1024     : D:\OVERLORD\DEMO\frames\skeletons_1024x1024\ (109 fichiers)
LA 1024       : D:\OVERLORD\DEMO\frames\lineart_1024x1024\  (101 fichiers)
Output        : D:\Ov3rLoRd AI\ComfyUI\output\asuka_run\
Tmp           : D:\OVERLORD\workspace\tmp\
GitHub        : https://github.com/g915tlk-design/OVERLORD.git
```

---

## 6. PROBLÈMES CONNUS

| Problème | Impact | Solution |
|----------|--------|----------|
| Dérive style frames 1-9 (motion mask) | Haut | AnimateDiff en cours |
| lineart_1024x1024 incomplet (101/1008) | Haut | Reconstruire depuis frames brutes |
| Bordures Kling dans lineart | Moyen | Reconstruire depuis frames brutes |
| reference_aligner_v2 mapping frame→lineart | Moyen | Corriger après AnimateDiff |
| Flip auto inversé (corrigé V1.9) | ✅ fixé | — |
| WinError 32 (corrigé V1.9) | ✅ fixé | — |

---

## 7. PROCHAINE SESSION — ORDRE D'ATTAQUE

```
1. Tester AnimateDiff SDXL dans ComfyUI UI manuellement
   → 16 frames avec squelettes OpenPose batch
   → Valider cohérence temporelle

2. Si OK → intégrer AnimateDiff dans batch_controlnet.py
   → Remplacer motion_mask par AnimateDiff sliding window

3. Reconstruire references depuis frames Kling brutes
   → lineart_extractor depuis D:\OVERLORD\DEMO\frames\frames\
   → reference_aligner_v2 avec mapping correct

4. frames_to_video.py → MP4 1 seconde (24 frames)
```

---

## 8. RÈGLES ABSOLUES

```
1.  py -3.12 TOUJOURS
2.  create_file tool UNIQUEMENT pour livraison
3.  ast.parse() AVANT toute livraison Python
4.  patcher.py FORMAT A — bundle groupé
5.  "Ov3rLoRd" toujours
6.  taesdxl permanent
7.  agent_supervisor_v2.py : racine + agents/
8.  Steps = 40 / CFG = 7.0 / 1024x1024
9.  Use Image Preprocessor = false (OpenPose ET Lineart)
10. EVA-01 exclu / single character / NoobAI exclu (usage commercial)
11. fabricatedXL_v70 NE JAMAIS MODIFIER
12. Combined_V35_API.json NE PAS RECRÉER
```

---

*Ov3rLoRd V2.26*
*"La connaissance est binaire, pas incertaine."*
*Généré le 2026-06-28*

# CONTEXTE_OVERLORD_V223.md
# Cerveau de Démarrage — Session 2026-06-24
# Pipeline Ov3rLoRd — Ov3rLoRd / Jérémy Gourlain

---

## 1. RÉSUMÉ DE L'ARCHITECTURE

### Vue d'ensemble
Pipeline de production anime IA autonome. Objectif : générer un court-métrage de 2 minutes style Evangelion (Asuka Run) pour démo Japan Expo 9-12 juillet 2026.

### Flux de données V2.23
```
Kling AI 3.0 Turbo (vidéos référence humain réel)
    ↓
demo_fusion.py (fusion 6 clips MP4 → asuka_run_reference.mp4 42s)
    ↓
frame_extractor.py (→ 1008 frames PNG @ 24fps)
    ↓
DWPose ComfyUI (→ 1008 squelettes overlord_skeleton_frame_XXXX_00001_.png)
    ↓
batch_controlnet.py V1.3 (SDXL + ControlNet OpenPose → 1008 frames Asuka)
    ↓
frames_to_video.py (1008 PNGs → asuka_run_FINAL.mp4)
```

### Agents principaux
| Agent | Chemin | Rôle |
|-------|--------|------|
| demo_fusion.py | D:\OVERLORD\DEMO\ | Fusion clips Kling |
| frame_extractor.py | D:\OVERLORD\agents\ | Extraction frames + DWPose |
| batch_controlnet.py | D:\OVERLORD\agents\ | Génération Asuka frames |
| frames_to_video.py | D:\OVERLORD\agents\ | Assemblage MP4 final |
| director.py | D:\OVERLORD\agents\ | Arbitrateur pipeline |
| patcher.py | D:\OVERLORD\ | Système de patch FORMAT A |

---

## 2. ÉTAT DES LIEUX

### Fonctionnel
- DWPose : 1008 squelettes générés (D:\OVERLORD\DEMO\frames\skeletons\)
- ControlNet SDXL : génère des frames Asuka de qualité pro
- batch_controlnet.py V1.3 : zones watchdog, flip auto, skip frames existantes
- LTX-Video ComfyUI : fonctionnel (T5-XXL mergé, stg.py patché)

### Problèmes en cours
- IP-Adapter : seul modèle dispo = ip-adapter-faceid-plusv2_sdxl.bin (FaceID, requiert insightface)
- Watchdog SSIM trop strict (0.55) → baisser à 0.25
- Seed : à valider manuellement dans ComfyUI
- Frames inversées : flip auto implémenté mais à valider

### Bugs résolus cette session
- LTX stg.py skip_block_list KeyError → .get("skip_block_list", [])
- CLIPLoader type stable_diffusion → sd3
- CFGGuider incompatible LTX → STGGuiderNode stg=0
- skimage manquant → pip install scikit-image
- VAE taesdxl.safetensors invalide → taesdxl sans extension
- Squelettes non trouvés → copier dans ComfyUI\input\
- IP-Adapter nom incorrect → ip-adapter-faceid-plusv2_sdxl.bin

---

## 3. CONFIG COMFYUI SDXL VALIDÉE

```
Checkpoint   : fabricatedXL_v70.safetensors
LoRA         : asuka-langley-soryuu-classic-ponyxl-lora-nochekaiser.safetensors
LoRA weight  : 0.75
ControlNet   : control-lora-openposeXL2-rank256.safetensors
CN strength  : 1.0 / CN end : 1.0
VAE          : taesdxl
Résolution   : 1344x768
Sampler      : dpmpp_2m / karras
CFG          : 6.0 / Steps : 40
CLIP Vision  : CLIP-ViT-bigG-14-laion2B-39B-b160k.safetensors
IP-Adapter   : ip-adapter-faceid-plusv2_sdxl.bin (nécessite insightface)
```

### Prompt positif
```
(masterpiece:1.4), (best quality:1.4), (ultra detailed:1.3), (absurdres:1.2), sharp focus,
1girl, solo, asuka langley soryu, perfect face, angry confident expression, blue eyes,
flowing red hair, long red hair dramatically swept back by wind,
iconic red plugsuit, glossy reflective plugsuit, skin-tight plugsuit, detailed plugsuit seams,
full body, perfect anatomy, side view, running at maximum speed, extreme dynamic running pose,
leaning aggressively forward, powerful sprint, explosive leg stride, dynamic arm pumping, motion blur,
heavy speed lines, intense movement, wind pressure effect, sense of extreme velocity,
anime style, cel shading, bold lines, evangelion aesthetic, vibrant colors,
pure white background
```

### Prompt négatif
```
worst quality, low quality, blurry, deformed, extra limbs,
multiple characters, ugly, bad anatomy, watermark, signature,
realistic, photograph, 3d render, multiple girls, nsfw
```

---

## 4. ZONES WATCHDOG batch_controlnet.py V1.3

| Frames | Zone | Watchdog | Maître |
|--------|------|----------|--------|
| 0→201 | Course 1 | ON SSIM>0.25 | frame 0 |
| 202→333 | Transition/Visage | OFF | None |
| 334→431 | Chute | OFF | frame 334 |
| 432→623 | Relèvement | OFF | None |
| 624→815 | Debout | OFF | None |
| 816→1007 | Course 2 | ON SSIM>0.25 | frame 816 |

---

## 5. SÉQUENCE ASUKA RUN

| Shot | Fichier | Durée | Frames | Contenu |
|------|---------|-------|--------|---------|
| 1 | 001.mp4 | 6s | 0→143 | Départ sprint |
| 2 | 002.mp4 | 6s | 144→287 | Visage / transition |
| 3 | 003.mp4 | 6s | 288→431 | Chute (réelle frame 334) |
| 4 | 004.mp4 | 8s | 432→623 | Relèvement push-up |
| 5 | 005.mp4 | 8s | 624→815 | Debout posture |
| 6 | 006.mp4 | 8s | 816→1007 | Reprise jogging |

Total : 42s = 1008 frames @ 24fps

---

## 6. ROADMAP TECHNIQUE

### Immédiat avant Japan Expo J-15
1. Valider seed ComfyUI manuellement
2. Corriger seuil watchdog → 0.25
3. Résoudre IP-Adapter (insightface OU ip-adapter-plus_sdxl_vit-h.safetensors)
4. Lancer batch complet 1008 frames
5. Assembler MP4 final avec frames_to_video.py
6. cycle_detector.py pour boucler cycle 24 frames course

### Court terme
- cycle_detector.py : meilleur cycle 24 frames dans Course 1
- Normalisation direction flip sur batch complet
- Audio sync EVA OST

### Long terme
- Pipeline 24 minutes pour pitch Khara (Noisy-le-Grand)
- Contact Japan Expo : JF/Sandrine SEFA

---

## 7. RÈGLES ABSOLUES

- Toujours py -3.12 (jamais 3.14)
- Patches via patcher.py FORMAT A uniquement
- ast.parse() validation avant toute livraison
- Fichiers via create_file uniquement
- LLM imports toujours en try/except
- Projet toujours "Ov3rLoRd"
- EVA-01 exclu (pas de LoRA)
- Single character par séquence
- taesdxl permanent (sdxl_vae.safetensors truncated)

---

## 8. CHEMINS SYSTÈME

```
ComfyUI       : D:\Ov3rLoRd AI\ComfyUI\
ComfyUI input : D:\Ov3rLoRd AI\ComfyUI\input\
ComfyUI output: D:\Ov3rLoRd AI\ComfyUI\output\asuka_run\
OVERLORD root : D:\OVERLORD\
DEMO dir      : D:\OVERLORD\DEMO\
Agents        : D:\OVERLORD\agents\
Squelettes    : D:\OVERLORD\DEMO\frames\skeletons\
GitHub        : https://github.com/g915tlk-design/OVERLORD.git
```

---

## 9. DÉPENDANCES

```batch
py -3.12 -m pip install scikit-image ultralytics platformdirs numexpr numba pillow numpy
py -3.12 -m pip install insightface  # pour IP-Adapter FaceID
```

## 10. HARDWARE

- RTX 5080 : GPU principal 16GB VRAM
- RTX 2070 : GPU secondaire
- RAM : 32GB / Python 3.12.3 / PyTorch 2.11.0+cu128 / ComfyUI 0.25.0

---
Généré le 2026-06-24 — batch_controlnet V1.3 — prochaine étape : seed + batch 1008 frames

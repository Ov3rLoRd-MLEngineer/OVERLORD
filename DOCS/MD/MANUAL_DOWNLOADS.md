# MANUAL_DOWNLOADS.md
# Téléchargements Manuels — OverLord Pipeline
# Ces fichiers nécessitent une authentification ou un accord de licence.

---

## ÉTAPE 0 — Prérequis : Compte CivitAI

Crée un compte gratuit sur https://civitai.com  
Va dans **Paramètres → API Keys** et génère une clé.  
Tu peux ensuite télécharger depuis CivitAI avec :

```
curl -L -H "Authorization: Bearer TA_CLE_API" "URL_ICI" -o "fichier.safetensors"
```

---

## 1. CHECKPOINTS SDXL (dossier : `ComfyUI\models\checkpoints\`)

### NoobAI-XL v1.0 — RECOMMANDÉ EN PRIORITÉ
- **Pourquoi** : Meilleur modèle anime SDXL actuellement. 10M+ téléchargements. Base de tout ton pipeline.
- **Lien** : https://civitai.com/models/833294/noobai-xl-nsfwpony
- **Fichier à télécharger** : `noobaiXLNSFWPony_epsilonPred10.safetensors` (~6.5 GB)
- **Note** : Choisis la version **Epsilon Pred 1.0** (compatible avec les paramètres actuels du workflow)
- **Commande CivitAI API** :
```
curl -L -H "Authorization: Bearer TA_CLE_API" "https://civitai.com/api/download/models/1166562" -o "noobaiXLNSFWPony_epsilonPred10.safetensors"
```

### Illustrious XL v0.1 — ALTERNATIVE
- **Pourquoi** : Concurrent direct de NoobAI. Excellent pour les illustrations.
- **Lien** : https://civitai.com/models/795765/illustrious-xl
- **Fichier** : `illustriousXL_v01.safetensors` (~6.5 GB)
- **Commande** :
```
curl -L -H "Authorization: Bearer TA_CLE_API" "https://civitai.com/api/download/models/889818" -o "illustriousXL_v01.safetensors"
```

---

## 2. CONTROLNET (dossier : `ComfyUI\models\controlnet\SDXL\`)

### NoobAI XL ControlNet OpenPose
- **Pourquoi** : Nœud 173 de ton workflow. Contrôle des poses des personnages.
- **Lien** : https://civitai.com/models/873388
- **Fichier** : `noobaiXLControlnet_openposeModel.safetensors` (~700 MB)
- **Commande** :
```
curl -L -H "Authorization: Bearer TA_CLE_API" "https://civitai.com/api/download/models/977516" -o "noobaiXLControlnet_openposeModel.safetensors"
```

---

## 3. IPADAPTER (dossier : `ComfyUI\models\ipadapter\`)

### noobIPAMARK1_mark1.safetensors
- **Pourquoi** : Nœuds 202/162. IPAdapter optimisé pour NoobAI. Cohérence de style entre frames.
- **Lien** : https://civitai.com/models/noobIPAMARK1 *(cherche "noobIPAMARK1" sur CivitAI)*
- **Alternative HuggingFace** : https://huggingface.co/h94/IP-Adapter/tree/main/sdxl_models
  - Fichier : `ip-adapter_sdxl.safetensors` (~1.1 GB) — version générique compatible

---

## 4. DETECTION (dossier : `ComfyUI\models\ultralytics\`)

### ntd11_anime_nsfw_segm_v5-variant1.pt  → `segm\`
- **Pourquoi** : Nœud 15. Segmentation spécialisée anime pour MaskDetailer.
- **Lien** : https://civitai.com/models/ntd11-anime-segm *(cherche "ntd11 anime segm" sur CivitAI)*
- **Alternative** : https://huggingface.co/segments-arnaud/yolov8-seg-anime

### Eyeful_v2-Individual.pt  → `bbox\`
- **Pourquoi** : Nœud 17. Détection des yeux pour le FaceDetailer oculaire.
- **Lien** : https://civitai.com/models/eyeful-v2 *(cherche "Eyeful v2" sur CivitAI)*

---

## 5. LORAS RECOMMANDÉS (dossier : `ComfyUI\models\loras\`)

### Detail Tweaker XL — ESSENTIEL
- **Pourquoi** : Booste les détails fins sur toutes les générations. 5M+ téléchargements.
- **Lien** : https://civitai.com/models/122359/detail-tweaker-xl
- **Fichier** : `add-detail-xl.safetensors` (~229 MB)
- **Usage dans config.json** : `"lora": "add-detail-xl.safetensors", "strength": 0.5`
- **Commande** :
```
curl -L -H "Authorization: Bearer TA_CLE_API" "https://civitai.com/api/download/models/135867" -o "add-detail-xl.safetensors"
```

### Anime Lineart Style XL
- **Pourquoi** : Style trait anime propre. Excellent pour la cohérence visuelle.
- **Lien** : https://civitai.com/models/330177 *(cherche "anime lineart xl" sur CivitAI)*
- **Fichier** : `~150 MB`

### Better Hands XL
- **Pourquoi** : Corrige le problème chronique des mains en SDXL anime.
- **Lien** : https://civitai.com/models/259266 *(cherche "better hands xl")*

### Flat Color Anime XL
- **Pourquoi** : Style celluloïd japonais — parfait pour l'animé. Compatible NoobAI.
- **Lien** : https://civitai.com/models/flat-color-anime *(cherche "flat color anime xl")*

---

## 6. SAM 3.1 (dossier : `ComfyUI\models\checkpoints\`)

### sam3.1_multiplex_fp16.safetensors
- **Pourquoi** : Nœud 12 de ton workflow. SAM 3.1 pour segmentation avancée.
- **Lien** : https://huggingface.co/facebook/sam2.1-hiera-base-plus
- **Commande alternative** :
```
curl -L "https://huggingface.co/facebook/sam2.1-hiera-base-plus/resolve/main/sam2.1_hiera_base_plus.pt" -o "sam2.1_hiera_base_plus.pt"
```
- **Note** : Le fichier exact `sam3.1_multiplex_fp16.safetensors` est un custom model — cherche sur CivitAI ou remplace par le SAM 2.1 officiel ci-dessus.

---

## 7. CLIP VISION ALTERNATIF

### CLIP-ViT-H-14-laion2B-s32B-b79K.safetensors  → `clip_vision\`
- **Pourquoi** : Nœud 185. Nécessite une conversion de .bin → .safetensors.
- **Lien** : https://huggingface.co/laion/CLIP-ViT-H-14-laion2B-s32B-b79K/tree/main
- **Commande** :
```
curl -L "https://huggingface.co/laion/CLIP-ViT-H-14-laion2B-s32B-b79K/resolve/main/open_clip_pytorch_model.bin" -o "CLIP-ViT-H-14.bin"
```
- **Conversion** (après téléchargement) :
```
python -c "
import torch
from safetensors.torch import save_file
weights = torch.load('CLIP-ViT-H-14.bin', map_location='cpu')
save_file(weights, 'CLIP-ViT-H-14-laion2B-s32B-b79K.safetensors')
print('Conversion OK')
"
```

---

## RÉSUMÉ VOLUMES

| Catégorie            | Fichiers | Volume approx |
|---|---|---|
| Checkpoints (1 modèle) | 1      | ~6.5 GB       |
| VAE                  | 1        | 335 MB        |
| ControlNet           | 2        | ~1.5 GB       |
| Upscalers            | 2        | 134 MB        |
| Détection YOLO       | 5        | ~220 MB       |
| SAM                  | 1        | 375 MB        |
| CLIP Vision          | 2        | ~7.6 GB       |
| IPAdapter            | 2        | ~2.2 GB       |
| LoRAs (4 recommandés)| 4        | ~700 MB       |
| **TOTAL**            | **20**   | **~20 GB**    |

---

## ORDRE D'INSTALLATION RECOMMANDÉ

1. `download_dependencies.bat` → installe tout l'automatisable (~10 GB)
2. Checkpoint NoobAI-XL (priorité absolue)
3. LoRA Detail Tweaker XL
4. ControlNet OpenPose NoobAI
5. Les autres LoRAs selon les besoins

---

## VÉRIFICATION FINALE

Lance cette commande pour vérifier que tous les modèles sont bien en place :

```
python -c "
import os
COMFY = r'D:\IA Local\ComfyUI Installation Local\ComfyUI_windows_portable\ComfyUI'
for rel, name in [
    (r'\models\checkpoints\noobaiXLNSFWPony_epsilonPred10.safetensors', 'NoobAI-XL'),
    (r'\models\vae\sdxl_vae.safetensors', 'VAE'),
    (r'\models\controlnet\SDXL\control-lora-canny-rank256.safetensors', 'ControlNet Canny'),
    (r'\models\ultralytics\bbox\face_yolov9c.pt', 'YOLO Face'),
    (r'\models\sams\sam_vit_b_01ec64.pth', 'SAM'),
    (r'\models\ipadapter\ip-adapter-faceid-plusv2_sdxl.bin', 'IPAdapter FaceID'),
]:
    exists = os.path.exists(COMFY + rel)
    print(f'  [{\"OK\" if exists else \"MANQUANT\"}] {name}')
"
```

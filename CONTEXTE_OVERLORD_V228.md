# CONTEXT V228 — Ov3rLoRd Pipeline — Session 2026-07-02

## REPRISE IMMÉDIATE

### Dernier test en cours (BLOQUÉ)
`sam_mask_generator.py` échoue en 0.02s côté ComfyUI — le cache réutilise l'ancien job.
**Fix livré mais pas encore testé** : nom de crop unique par timestamp + préfixe run_id aléatoire pour forcer le rechargement.

Commande à relancer après remplacement :
```
py -3.12 sam_mask_generator.py --image 2026-06-30-212153_fabricatedXL_v70_391065954874066.png --box "259,1049,200,409" --output test_sam_mask_v6.png --verbose
```

Résultat attendu : `Masque binaire : ~14% noir`, classes SAM `[0, 84, 119, 196, 220]`, chaussures 119+220 isolées.

---

## ÉTAT DU PIPELINE

### Architecture complète validée
```
Keypoints OpenPose (SavePoseKpsAsJsonFile)
    ↓
locate_feet_zone_from_keypoints() → boîte englobante (x,y,w,h)
    ↓
SAMPreprocessor (ComfyUI API) → segmentation multi-classes
    ↓
Post-traitement Python : seuillage par classes SAM + filtrage HSV jean
    ↓
Masque binaire (noir=régénérer, blanc=préserver)
    ↓
inpaint_corrector.py → ComfyUI inpaint → stitch dans frame originale
```

### Convention masque confirmée définitivement
**NOIR = zone à régénérer, BLANC = préserver** (confirmé par test MaskEditor ComfyUI)

---

## FICHIERS LIVRÉS CETTE SESSION

### `sam_mask_generator.py` → `D:\OVERLORD\agents\`
Agent SAM principal. Points clés :
- Nœud correct : `SAMPreprocessor` (pas `SAMModelLoader` qui n'existe pas dans cette install)
- Modèle : `sam_vit_b_01ec64.pth`
- Workflow : `LoadImage → SAMPreprocessor → ImageToMask → MaskToImage → SaveImage`
- **CRITIQUE** : images RGBA doivent être composées sur fond blanc avant envoi (convert("RGB") seul → pixels transparents noirs → SAM échoue silencieusement en 0.02s sans output)
- Post-traitement : seuillage par classes SAM (exclure fond dominant + classe la plus basse significative = jean)
- Filtrage HSV : force pixels bleu/cyan (hue 150-270°, sat > 0.25) en blanc (préservé)
- Recherche output : glob par mtime avec filtre `created_after` timestamp de soumission (évite de récupérer anciens fichiers)
- Crop unique par timestamp pour invalider cache ComfyUI
- CLI : `py -3.12 sam_mask_generator.py --image FRAME.png --box "x,y,w,h" --output mask.png --verbose`

### `inpaint_corrector_PATCHED.py` → `D:\OVERLORD\agents\inpaint_corrector.py`
- Appelle `generate_sam_mask()` en premier, repli sur masque rectangulaire si SAM échoue
- Masque PIL : blanc (255) = fond préservé, noir (0) = chaussures à régénérer
- Pas d'`InvertMask` dans le workflow ComfyUI (convention déjà correcte côté PIL)
- Config inpaint : `fabricatedXL_v70`, `taesdxl`, `dpmpp_2m/karras`, 25 steps, denoise=0.45, CFG=6.0
- Prompt positif shoe_mismatch : `"score_9, score_8_up, source_anime, nike air jordan 1 high-top sneakers, red black white colorway, swoosh logo, consistent on both feet, pure white background"`

### `Advanced_QwenVL_V35_PIPELINE_PATCHED_v3.json`
- OpenposePreprocessor : mode 0, résolution 1024, branché sur node 125
- Node 208 ajouté : `SavePoseKpsAsJsonFile` → `D:\Ov3rLoRd AI\ComfyUI\output\pose_keypoints_00001.json`

---

## ANALYSE SAM — CLASSES IDENTIFIÉES

Sur masque `__00005_` (image source RGBA composée sur blanc, crop 5% contexte) :
```
classe   0 :  0.0%  → résidu noir (ignorer)
classe  84 : 13.6%  → JEAN (à exclure du masque)
classe 119 :  8.2%  → CHAUSSURE ARRIÈRE-PLAN ✓ (à masquer)
classe 196 : 72.4%  → FOND BLANC (valeur dominante, à exclure)
classe 220 :  5.7%  → CHAUSSURE AVANT-PLAN ✓ (à masquer)
```

**Logique de seuillage correcte** :
1. Identifier valeur dominante = fond
2. Parmi les non-dominantes, filtrer celles > 1% de pixels = classes significatives
3. Exclure la plus basse significative = jean
4. Les restantes = chaussures → noir dans le masque

---

## BUGS IDENTIFIÉS ET RÉSOLUS

| Bug | Cause | Fix |
|-----|-------|-----|
| SAM échoue 0.02s | Image RGBA → convert("RGB") → fond noir | Composer RGBA sur blanc avant crop |
| Masque récupère ancien fichier | glob sans filtre de date | Filtre `created_after=submit_time` |
| Filtrage HSV dimension mismatch | Crop 511px vs masque 866px | Resize crop au format du masque avant HSV |
| Cache ComfyUI réutilise job | Même nom de fichier à chaque run | Nom crop = `_sam_crop_STEM_TIMESTAMP.png`, préfixe = `sam_mask_STEM_RUNID_` |
| Fichiers `py` et `0` dans agents | Guillemets mal interprétés par cmd | `del "D:\OVERLORD\agents\py" "D:\OVERLORD\agents\0"` |

## BUGS EN COURS (NON RÉSOLUS)

| Bug | Statut |
|-----|--------|
| SAM échoue encore 0.02s après fix RGBA | Fix livré, **pas encore testé** |

---

## RÉSULTATS VISUELS OBTENUS

| Test | Résultat |
|------|---------|
| MaskEditor manuel | Jordan rouges/blanches/noires générées → validation inpaint fonctionne |
| manual_stitch.py | Stitch fonctionnel, Jordan recollée avec légères traces de bordure |
| SAM v1 (5% ctx, fond blanc) | Partiel : talon + semelle mais pas tout |
| SAM v3 (5% ctx, fond blanc) | 5 classes, chaussures partiellement isolées |
| SAM v5 (5% ctx, RGBA→blanc) | **Meilleur** : classes 119+220 = deux chaussures sans jean, 14% noir |

---

## PROCHAINES ÉTAPES (dans l'ordre)

1. **IMMÉDIAT** : Confirmer que le fix cache fonctionne (run v6, attendre ~10s, vérifier `__00006_`)
2. **IMMÉDIAT** : Tester `inpaint_corrector.py --auto` avec le masque SAM pixel-perfect
3. **COURT TERME** : LoRA Jordan AJ1 (7 images rotation 360°, rank 4, fabricatedXL) — à lancer dès inpaint validé
4. **COURT TERME** : Qwen-VL comme juge du masque SAM (critic/corrector)
5. **PLANIFIÉ** : Exploitation couleur HSV pour valider masque (jean bleu cyan 150-270°)
6. **PLANIFIÉ** : Fine-tuning SAM sur images anime chaussures (200-500 images, stylet Huion, 2-6h GPU RTX 5080, 20-40h annotation)
7. **PLANIFIÉ** : Fusion AnimateDiff dans Advanced_QwenVL_V35 avec switch d'activation
8. **PLUS TARD** : LoRA Asuka, LoRA autres éléments

---

## CHEMINS SYSTÈME

```
Dossier racine       : D:\OVERLORD\
ComfyUI              : D:\Ov3rLoRd AI\ComfyUI\  (port 8188)
ComfyUI input        : D:\Ov3rLoRd AI\ComfyUI\input\
ComfyUI output       : D:\Ov3rLoRd AI\ComfyUI\output\
Ollama               : http://127.0.0.1:11434
Agents               : D:\OVERLORD\agents\
Frames Mixamo        : D:\OVERLORD\DEMO\frames\mixamo_raw\
Keypoints JSON       : D:\Ov3rLoRd AI\ComfyUI\output\pose_keypoints_00001.json
```

## RÈGLES ABSOLUES

- `Combined_V35_API.json` → NE JAMAIS RECRÉER
- `fabricatedXL_v70` → NE JAMAIS MODIFIER
- NoobAI → exclu (usage commercial)
- `taesdxl` → VAE permanent
- `py -3.12` → TOUJOURS (jamais python)
- `create_file` → UNIQUEMENT pour livraison Python
- Images RGBA → composer sur fond blanc avant SAMPreprocessor
- `dpmpp_2m/karras` → sampler pipeline confirmé
- AnimateDiff : `ADE_AnimateDiffLoaderGen1` obligatoire (Gen2 indisponible)

## TRANSCRIPTS DISPONIBLES

```
/mnt/transcripts/2026-07-01-20-06-40-overlord-animatediff-inpaint-pipeline.txt
/mnt/transcripts/2026-07-01-23-10-48-overlord-animatediff-sam-inpaint-pipeline.txt
```

# Plan cohérence temporelle — Pipeline Ov3rLoRd — 04/08/2026

## Diagnostic confirmé

La limite de ~37 frames / 45s avant dérapage stylistique est **structurelle et universelle** sur tous les modèles DiT (WAN 2.2, AniSora, Hunyuan, LTX). Ce n'est pas un bug de réglage. La réponse 2026 est un **empilement de techniques**, pas une solution unique.

Symptôme principal observé : drift de couleur des sneakers entre frames. Cause : absence de mécanisme de verrouillage colorimétrique inter-clips + pas de LoRA de personnage.

---

## Stack anti-dérive recommandé (ordre de priorité)

### Étape 1 — Immédiat : SVI 2.0 Pro + ColorMatch (sans entraînement)

**Stable Video Infinity 2.0 Pro** (ICLR 2026 Oral, EPFL) = LoRA WAN 2.2 I2V-A14B qui recycle les erreurs du DiT en signal de supervision. C'est le correctif le plus direct pour le drift.

- LoRA HIGH : `Kijai/WanVideo_comfy/LoRAs/Stable-Video-Infinity/v2.0/SVI_Wan2.2-I2V-A14B_lora_HIGH_v2.0_rank_128_fp16.safetensors`
- LoRA LOW : même repo, variante `_LOW_`
- **Impératif** : appliquer sur les DEUX experts MoE (HIGH + LOW). Un seul = résultat dégradé.
- Réglages : CFG 1.5, Shift 8, 6-8 steps, Euler/Simple, **seed différent par clip**
- Workflow ComfyUI : SVI-Shot (1 motion frame = dernière frame du clip précédent comme latent de conditionnement)

**ColorMatch (KJNodes)** après chaque clip :
- Référence = dernière frame stable du clip précédent
- Mode LAB (meilleur pour l'anime)
- Supprime la frame dupliquée de raccord

**Benchmark succès étape 1** : sneakers stables sur 60s. Si drift persiste → étape 2.

**Confirmation à l'échelle 2026-08-07** (session nuit 2026-08-06/07, `DEMO/output/miku_demo_3min_v2_keyframed.mp4`, 51 clips chaînés, 236s) :
au-delà de la fenêtre validée à 60s, le drift réapparaît nettement — comme
attendu par ce plan, pas une régression. Ajout d'un ancrage identité par
clip (`clip_vision_output` WAN natif sur keyframe SDXL par clip, priorité 3
session nuit) : corrige bien le changement de tenue/costume sur toute la
durée, mais **n'a aucun effet sur ce drift structurel** (prévisible : ce
n'est pas un mécanisme de verrouillage colorimétrique inter-frames, juste
un rappel d'identité). Progression observée par extraction de frames à
intervalles réguliers sur les clips bruts (avant tout upscale, donc pas un
artefact SeedVR2) : net et propre jusqu'à ~clip15 (60-70s), dérive visible
(flou + léger cast violet) dès ~clip20-24 (90-110s), nette à partir de
~clip28 (125s), sévère à partir de ~clip38 (170s) — accumulation graduelle
et continue, pas un saut isolé sur un clip particulier. Détail non noté
jusqu'ici : la dérive prend la forme d'un **vignettage violet/magenta sur
les bords** en plus de la perte de netteté généralisée. Confirme la
recommandation du plan : ne pas continuer à chercher un correctif côté
ancrage/keyframe/ColorMatch pour des chaînes >60s, l'étape 2 (LoRA
personnage) reste le prochain pas nécessaire, pas encore tentée.

### Étape 2 — LoRA de personnage (1-4h d'entraînement)

- Rang 32, entraînable sur RTX 5060 Ti 16Go via AI-Toolkit
- Dataset : feuille multi-angles du personnage (générer d'abord via fabricatedXL SDXL)
- Appliquer sur HIGH + LOW comme SVI
- IPAdapter WAN (`ComfyUI-IPAdapterWAN`) en appoint pour les changements de plan

**Benchmark succès étape 2** : identité stable sur changement de plan complet.

### Étape 3 — VACE inpainting masqué (si fond dérive)

- Module `Wan2_2_Fun_VACE_module_A14B_HIGH/LOW` (Kijai, FP8, ~3Go/module)
- Usage : verrouiller le fond par inpainting masqué entre clips
- Ne pas utiliser pour la cohérence principale (SVI est plus adapté)

### Étape 4 — Filet couleur ciblé (accessoires récalcitrants)

- `line2color` (Kataragi, controlnetXL) sur frames problématiques uniquement
- AniDoc (LucipherDev) en blocs de 14 frames max pour re-lock palette
- `comfyui-diffusion-cg` (Haoming02) pour drift latent SDXL

---

## Outils à installer dans ComfyUI Manager

| Outil | Repo | Usage |
|---|---|---|
| SVI LoRA HIGH+LOW | `Kijai/WanVideo_comfy` | Anti-drift principal |
| ColorMatch | KJNodes (déjà présent ?) | Verrouillage couleur inter-clips |
| ComfyUI-IPAdapterWAN | GitHub | Cohérence identité changements de plan |
| ComfyUI-AniDoc | LucipherDev | Re-colorisation 14f max |
| comfyui-diffusion-cg | Haoming02 | Correction drift latent |
| ComfyUI-EasyColorCorrector | regiellis | Palette locking |

---

## R&D à surveiller (pas encore intégrable)

- **FreqForcing** (arXiv 2607.27110) : anti-drift spectral sans entraînement, prometteur mais pas de node ComfyUI mûr
- **Helios / Relative RoPE** (arXiv 2603.04379) : correction drift par position relative
- **HiAR** (arXiv 2603.08703) : métriques de drift (HSV saturation + DINOv2 frame-to-frame) — utile pour mesurer objectivement les progrès
- **AniME (bilibili)** (arXiv 2508.18781) : multi-agent pour production anime longue durée — architecture pipeline à surveiller

---

## Parallélisation GPU pour les passes longues

- RTX 5080 (CUDA_VISIBLE_DEVICES=0) : frames ordre croissant (1→N)
- RTX 5060 Ti (CUDA_VISIBLE_DEVICES=1) : frames ordre décroissant (N→1)
- Point de jonction : frame N/2
- Applicable : SeedVR2 upscale, extraction depth/pose Blender, AnimateDiff batch
- Ne pas utiliser pour AniSora/SVI (génération séquentielle obligatoire, chaque clip dépend du précédent)

---

## Workflow pipeline cible (après intégration SVI)

```
Keyframe SDXL (fabricatedXL + LoRA style)
        ↓
AniSora V3.2 I2V + SVI LoRA (HIGH+LOW)
  → clip 1 (37 frames)
        ↓ [dernière frame comme motion frame]
AniSora V3.2 I2V + SVI LoRA (HIGH+LOW)
  → clip 2 (37 frames)
        ↓ ColorMatch (LAB, ref = frame 37 clip 1)
[répéter pour N clips]
        ↓
Assemblage ffmpeg (supprimer frames dupliquées de raccord)
        ↓
RIFE rife49 / GMFSS Fortuna (interpolation 2x)
        ↓
SeedVR2 7B (upscale 2x, block_swap=24, VAE tiling)
        ↓
Export final
```

---

## Notes CLAUDE.md à ajouter

- Préférer DepthAnythingV2 à l'API compositor Blender 5.1 (cassée) pour les depth maps — économie de tokens et plus fiable
- SVI LoRA : toujours appliquer sur HIGH ET LOW, jamais un seul
- ColorMatch : mode LAB pour l'anime, pas RGB
- Seed différent obligatoire par clip SVI (même seed = artefacts de répétition)
- Parallélisation GPU : SVI/AniSora = séquentiel obligatoire ; upscale/extraction = parallélisable

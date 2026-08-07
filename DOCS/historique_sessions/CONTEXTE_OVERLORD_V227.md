# CONTEXTE_OVERLORD_V227.md
# Cerveau de Démarrage — Session 2026-06-30
# Pipeline Ov3rLoRd / Jérémy Gourlain
# Généré en fin de session — reprendre immédiatement sans questions superflues

---

## 0. CONTEXTE UTILISATEUR

**Jérémy Gourlain** — Le Havre, France. Développeur solo.
- BTS MUC + TFIC chimie industrielle
- Culture geek profonde : DBZ, EVA, Gundam, SAO Alicization, Gunnm, HxH...
- Objectif : film 24 minutes → présentation (Japan Expo 9-12 juillet, contact SEFA JF/Sandrine)
- Dévitalisation dentaire semaine prochaine

**Style de collaboration :**
- Toujours py -3.12 / create_file tool / ast.parse() / FORMAT A patcher
- "Ov3rLoRd" toujours (jamais OverLord)
- Force de proposition, pas d'initiatives non validées
- Validation explicite avant chaque implémentation
- Workflow de test SÉPARÉ du workflow pipeline — ne jamais toucher au pipeline

---

## 1. DÉCISION ARCHITECTURALE MAJEURE DE CETTE SESSION

### Format de travail validé : 1024x1536
- Toutes les entrées et sorties sont en 1024x1536
- EmptyLatentImage : 1024x1536 batch=16
- Blender render : 1024x1024 → à migrer vers 1024x1536

### Source de référence : Mixamo → Blender
- **Abandon définitif des frames Kling** comme source de référence
- Source validée : Mixamo FBX (animation Running, Sophie, In Place, 24fps, 34 frames)
- Blender 5.1.2 installé sur le poste
- Render Blender → `D:\OVERLORD\DEMO\frames\mixamo_raw\` (34 PNG 1024x1024 actuellement)
- **À faire** : re-render en 1024x1536 dans Blender

### Workflow AnimateDiff validé (test)
Fichier : `animatediff_sdxl_cn_test.json`
```
VHS_LoadImages skeletons_1024x1024 → CN OpenPose
VHS_LoadImages mixamo_raw → LineArtPreprocessor → CN Lineart
VHS_LoadImages mixamo_raw → PrepImageForClipVision → IPAdapterAdvanced
EmptyLatentImage 1024x1536 batch=16
ADE_AnimateDiffLoaderGen2 mm_sdxl_v10_beta.safetensors
KSampler : euler_ancestral / normal / CFG 6.5 / 40 steps / denoise 1.0
SaveImage → animatediff_cn_test/frame
```

---

## 2. ÉTAT RÉEL DU PIPELINE — V2.27

### Architecture validée
```
Source : frames Mixamo (D:\OVERLORD\DEMO\frames\mixamo_raw\) [34 frames]
    ↓
reference_aligner_v2.py (extraction directe sans crop)
    → skeletons_1024x1024\ (OpenPose depuis mixamo_raw)
    → lineart_1024x1024\ (LineartStandard depuis mixamo_raw + invert)
    ↓
invert_lineart.py → inversion noir/blanc lineart
    ↓
ComfyUI AnimateDiff workflow (animatediff_sdxl_cn_test.json)
    → 16 frames par batch
    → sliding window overlap 2-4 frames entre blocs
    ↓
frames_to_video.py → MP4 final
```

### Ce qui fonctionne ✅
- AnimateDiff Evolved v1.5.7 installé, mm_sdxl_v10_beta.safetensors actif
- OpenPose extraction depuis mixamo_raw : skeletons propres (bras gauche manquant = vêtements Sophie)
- LineartStandard extraction + inversion : lineart correct
- Cycle de course 34 frames Mixamo : cohérence temporelle excellente
- fabricatedXL_v70 génère Asuka correctement même sans LoRA (modèle pré-entraîné)
- Format 1024x1536 validé comme format de travail
- invert_lineart.py : fonctionnel
- reference_aligner_v2.py mode extraction directe : fonctionnel

### Ce qui est en cours 🔧
- **Skeletons bras gauche manquant** → Sophie (Mixamo) a des vêtements qui cachent le bras
  → Solution : trouver modèle Mixamo sans vêtements (ou modèle Asuka R34 en FBX/PMX)
- **Re-render Blender en 1024x1536** → actuellement 1024x1024
- **LineArtPreprocessor inline ComfyUI** → testé dans workflow JSON, à valider
- **IPA frame par frame** via VHS_LoadImages → dans workflow JSON, à valider

### Ce qui reste à faire ❌
- Valider workflow animatediff_sdxl_cn_test.json avec IPA+LineArtPreprocessor
- Re-render Blender 1024x1536
- Modèle Mixamo nu (ou Asuka FBX) pour skeletons sans bras manquant
- frames_to_video.py pour assembler MP4
- Intégration dans batch_controlnet.py V2.0 (AnimateDiff sliding window)
- Reconstruire 1008 frames depuis cycle 34 frames (boucle 1-34 × 30)

---

## 3. AGENTS LIVRÉS SESSION 30/06/2026

| Agent | Version | Statut |
|-------|---------|--------|
| reference_aligner_v2.py | V3 extraction directe | ✅ actif (D:\OVERLORD\) |
| invert_lineart.py | V1.0 | ✅ actif (D:\OVERLORD\) |
| animatediff_sdxl_cn_test.json | V3 IPA+LineArt | ✅ à tester |

---

## 4. CONFIG COMFYUI VALIDÉE

```
Checkpoint    : fabricatedXL_v70.safetensors (NE JAMAIS MODIFIER)
LoRA          : asuka-langley-soryuu-classic-ponyxl-lora-nochekaiser.safetensors
LoRA weight   : 0.75 (optionnel — fabricatedXL déjà entraîné sur Asuka)
VAE           : taesdxl permanent (sdxl_vae.safetensors confirmé tronqué)
Résolution    : 1024x1536 (nouveau format validé)
Steps         : 40
CFG           : 6.5 (was 7.0)
Sampler       : euler_ancestral / normal (was dpmpp_2m/karras)
CLIP Skip     : -2 (CLIPSetLastLayer)

ControlNet 1  : control-lora-openposeXL2-rank256.safetensors
  strength    : 1.25 / start 0.0 / end 0.50
  preprocessor: NONE (Use Image Preprocessor = false)

ControlNet 2  : xinsir-controlnet-lineart-sdxl.safetensors
  strength    : 1.25 / start 0.0 / end 0.50
  preprocessor: LineArtPreprocessor inline ComfyUI (plus de lineart pré-généré)

IPA           : ip-adapter-plus_sdxl_vit-h.safetensors
CLIP Vision   : model.safetensors (ViT-H-14)
IPA weight    : 0.70 / start 0.0 / end 0.30 / linear / K+V
PrepImage     : crop_position=pad

AnimateDiff   : mm_sdxl_v10_beta.safetensors
  context     : 16 frames / sliding window overlap 2-4
  node        : ADE_AnimateDiffLoaderGen2
```

---

## 5. PROMPTS VALIDÉS (PonyXL format)

```python
PROMPT_POS = (
    "score_9, score_8_up, score_7_up, source_anime, masterpiece, highly detailed, "
    "1girl, asuka shoryu langley, blue eyes, nike jordan sneakers, black hoodie, "
    "blue jeans, detailed clothing textures, side view, profile, full body, run, "
    "concentrated expression, pure white background"
)
PROMPT_NEG = (
    "blurry, low quality, deformed, ugly, bad anatomy, bad eyes, bad hand, bad finger, "
    "extra limbs, watermark, text, logo, cartoon, anime, painting, 3d render, "
    "child, loli, overexposed, underexposed, plastic skin, "
    "gray background, dark background, gradient background"
)
# NOTE: "blue eyes" à retirer du prompt positif (contamine le fond)
# NOTE: Run 1 corps nu → retirer vêtements du prompt
```

---

## 6. HARDWARE ET CHEMINS

```
GPU           : RTX 5080 16GB
Python        : py -3.12 OBLIGATOIRE
Blender       : 5.1.2 installé (D:\Users\Ov3rL0rD\Desktop\asuka run.blend)
ComfyUI       : D:\Ov3rLoRd AI\ComfyUI\ port 8188

Source Mixamo : D:\OVERLORD\DEMO\frames\mixamo_raw\ (34 PNG 1024x1024)
Skeletons     : D:\OVERLORD\DEMO\frames\skeletons_1024x1024\ (34 fichiers)
Lineart       : D:\OVERLORD\DEMO\frames\lineart_1024x1024\ (34 fichiers, inversés)
Output AnimDiff: D:\Ov3rLoRd AI\ComfyUI\output\animatediff_cn_test\
Tmp           : D:\OVERLORD\workspace\tmp\
GitHub        : https://github.com/g915tlk-design/OVERLORD.git
FBX Mixamo    : Running.fbx (Sophie, 34 frames, 24fps, In Place)
```

---

## 7. DÉCISIONS TECHNIQUES IMPORTANTES DE CETTE SESSION

### AnimateDiff — trade-off cohérence vs qualité
- AnimateDiff lisse les hautes fréquences spatiales pour maintenir la cohérence temporelle
- C'est structurel, pas paramétrique (pas résolu par CFG/steps)
- **Plan multi-pass validé :**
  - Run 1 (corps nu) avec AnimateDiff → cohérence temporelle maximale, peu de détails
  - Run 2 (vêtements) frame par frame sans AnimateDiff → qualité détail maximale
  - Run 3 (FX + background) → idem
- AnimateDiff utilisé UNIQUEMENT pour Run 1

### Cycle Mixamo 34 frames → 1008 frames
- Le cycle de course est de 34 frames (35ème = identique à la 1ère, supprimée)
- Pour 1008 frames : boucler 1-34 × ~30 fois
- Principe animation studio : cycle en boucle, transitions entre cycles séparées

### Keyframes de reset anti-flickering
- Injecter une frame "propre" tous les 16 frames comme référence IPA forte (weight 0.9-1.0)
- Combiné avec le Run 1 corps nu → réduction maximale du bruit haute fréquence
- Analogie : inbetweeners travaillent entre les poses clés du animateur principal

### Source lineart
- Abandon du lineart pré-généré (référence_aligner_v2.py lineart)
- LineArtPreprocessor inline ComfyUI directement sur mixamo_raw → qualité supérieure

### Bras manquant skeleton
- Cause : vêtements de Sophie (Mixamo) occultent le bras gauche
- Solution court terme : accepter pour les tests
- Solution long terme : modèle nu Mixamo ou modèle Asuka FBX/PMX (communauté weeb/R34)
- Retargeting possible via Blender + mmd_tools addon (FBX → VMD → PMX)

---

## 8. ROADMAP TECHNIQUE — PROCHAINES ÉTAPES

```
PRIORITÉ 1 — Valider workflow animatediff_sdxl_cn_test.json V3
  → Charger dans ComfyUI, tester 16 frames
  → Vérifier IPA frame-par-frame + LineArtPreprocessor

PRIORITÉ 2 — Re-render Blender 1024x1536
  → Ouvrir asuka run.blend
  → Changer résolution 1024x1536
  → Ctrl+F12 → 34 nouvelles frames dans mixamo_raw

PRIORITÉ 3 — Modèle Mixamo nu
  → Télécharger personnage féminin minimal sur Mixamo
  → Appliquer animation Running
  → Re-render Blender → nouveaux skeletons sans bras manquant

PRIORITÉ 4 — Valider cycle 34 frames → 1008 frames
  → Script Python : copier/boucler les 34 frames × 30
  → Tester AnimateDiff sur 32 frames (2 cycles)

PRIORITÉ 5 — Intégrer dans batch_controlnet.py V2.0
  → Remplacer motion_mask par AnimateDiff sliding window
  → Overlap 2-4 frames entre blocs de 16

PRIORITÉ 6 — frames_to_video.py
  → Assembler MP4 depuis les frames générées
  → 24fps, codec H264
```

---

## 9. ROADMAP LONG TERME (à ne pas oublier)

```
- ControlNet Union : fusionner OpenPose + Lineart en un seul nœud (anti-écrasement)
- Depth CN (3ème layer, weight 0.8-1.2) → anti-flickering spatial
- ComfyUI 3D OpenPose Editor node → génération skeletons directe
- MMD + mmd_tools Blender addon → retargeting animations
- Keyframe reset injection tous les 16 frames (IPA weight 0.9-1.0)
- RemBg post-processing agent (batch sur toutes les frames générées)
- Agents V1.x réutilisables : emotion engine, world model, ContinuityGuard (phase scénario)
```

---

## 10. PROBLÈMES CONNUS

| Problème | Impact | Solution |
|----------|--------|----------|
| Bras gauche skeleton manquant | Moyen | Modèle Mixamo nu |
| mixamo_raw en 1024x1024 pas 1024x1536 | Moyen | Re-render Blender |
| "blue eyes" contamine le fond | Faible | Retirer du prompt positif |
| AnimateDiff qualité détail réduite | Structurel | Multi-pass Run 1/2/3 |
| Fond gris Blender contamine | Corrigé | World blanc #FFFFFF dans Blender |

---

## 11. RÈGLES ABSOLUES

```
1.  py -3.12 TOUJOURS
2.  create_file tool UNIQUEMENT pour livraison
3.  ast.parse() AVANT toute livraison Python
4.  patcher.py FORMAT A — bundle groupé
5.  "Ov3rLoRd" toujours
6.  taesdxl permanent
7.  agent_supervisor_v2.py : racine + agents/
8.  Steps = 40 / CFG = 6.5 / 1024x1536
9.  Use Image Preprocessor = false (OpenPose) / LineArtPreprocessor inline (Lineart)
10. EVA-01 exclu / single character / NoobAI exclu (usage commercial)
11. fabricatedXL_v70 NE JAMAIS MODIFIER
12. Combined_V35_API.json NE PAS RECRÉER
13. Workflow pipeline ≠ workflow test — NE JAMAIS TOUCHER AU PIPELINE
14. Validation explicite avant chaque implémentation
15. 1024x1536 format unique entrée/sortie
```

---

## 12. INSIGHTS TECHNIQUES SESSION (à conserver)

**Sur le flickering :**
- Analogie validée : bruit = onde par frame, hautes fréquences = détails fins
- AnimateDiff = harmonisateur d'ondes entre frames
- Noise warping = forcer continuité physique du bruit via optical flow
- Prior temporel global = ce que font les DiT spatio-temporels (Wan2.1, CogVideoX)
- Notre solution : multi-pass + keyframes reset + Run 1 corps nu

**Sur Mixamo/Blender :**
- FBX Mixamo contient mesh + armature séparés
- Retargeting possible : même squelette standard sur tous les persos Mixamo
- Blender : `Ctrl+Alt+Numpad0` = aligner caméra sur vue courante
- Blender render viewport : Vue → Rendre un playblast
- World blanc : Properties → World → Surface → Couleur #FFFFFF
- Freestyle render = contours uniquement (non utilisé, pour référence future)

**Sur fabricatedXL :**
- Modèle pré-entraîné sur Asuka → LoRA optionnel
- Qualité native très haute (images statiques de référence confirmées)
- Prompt "blue eyes" à supprimer (contamine le fond dans certains cas)

---

*Ov3rLoRd V2.27*
*"La connaissance est binaire, pas incertaine."*
*Généré le 2026-06-30*

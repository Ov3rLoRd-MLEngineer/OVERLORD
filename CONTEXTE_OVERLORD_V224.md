# CONTEXTE_OVERLORD_V224.md
# Cerveau de Démarrage — Session 2026-06-24
# Pipeline Ov3rLoRd / Jérémy Gourlain
# Généré en fin de session — reprendre immédiatement sans questions superflues

---

## 0. CONTEXTE UTILISATEUR

**Jérémy Gourlain** — Le Havre, France. Développeur solo.
- BTS MUC (commerce/management) + TFIC chimie industrielle
- Culture geek profonde : DBZ, EVA, Gundam, SAO Alicization, Gunnm, HxH...
- Collection physique : figurines Gundam + Megami Device → source de poses OpenPose
- Gundam Perfect Grade RX-78-2 + autres Gunpla pour poses physiques
- **Deadline absolue : Japan Expo 9-12 juillet 2026 (J-15)** — Contact JF/Sandrine (SEFA)
- Objectif démo : 2 minutes anime EVA qualité studio (Asuka Run)
- Objectif long terme : film 24 minutes → pitch Khara (Noisy-le-Grand)

**Style de collaboration :**
- Valide rapidement, passe à l'action
- Patches via patcher.py FORMAT A UNIQUEMENT — un seul bundle groupé
- Toujours "Ov3rLoRd" (jamais "OverLord")
- Je suis l'Architecte — force de proposition, initiative
- Toujours py -3.12 (jamais python ou py seul)
- Fichiers livrés via create_file tool UNIQUEMENT (jamais bash redirect)
- ast.parse() validation AVANT toute livraison Python

---

## 1. DEUX PIPELINES COEXISTANTS

### Pipeline A — Asuka Run (PRIORITÉ J-15)
Pipeline de production directe : 1008 frames Asuka → démo 42s Japan Expo.
Bypass complet de maestro. Utilise batch_controlnet.py directement.

### Pipeline B — Maestro Standard (production générale)
Pipeline complet sourcing→scenario→storyboard→production→postprod.
Utilise Advanced_QwenVL_V35.json (génération) + Detailer_V35.json (post-processing).
Vision long terme : structure calques séparés style Ankama Dofus/Wakfu début.

---

## 2. ARCHITECTURE PIPELINE A — ASUKA RUN V2.24

### Flux de données
```
Kling AI 3.0 Turbo (vidéos référence humain réel)
    ↓
demo_fusion.py (fusion 6 clips MP4 → asuka_run_reference.mp4 42s)
    ↓
frame_extractor.py (→ 1008 frames PNG @ 24fps)
    ↓
DWPose ComfyUI (→ 1008 squelettes overlord_skeleton_frame_XXXX_00001_.png)
    ↓
skeleton_remapper.py (→ redimensionne 912x912 → 1344x768 dans skeletons_1344x768/)
    ↓
batch_controlnet.py V1.4 (SDXL + ControlNet + IPAdapter rolling → 1008 frames Asuka)
    ↓
frames_to_video.py (1008 PNGs → asuka_run_FINAL.mp4)
```

### Séquence Asuka Run — 6 shots
| Shot | Fichier | Durée | Frames | Contenu | Seed shot |
|------|---------|-------|--------|---------|-----------|
| 1 | 001.mp4 | 6s | 0→143 | Départ sprint | À fixer |
| 2 | 002.mp4 | 6s | 144→287 | Visage / transition | À fixer |
| 3 | 003.mp4 | 6s | 288→431 | Chute (réelle frame 334) | À fixer |
| 4 | 004.mp4 | 8s | 432→623 | Relèvement push-up | À fixer |
| 5 | 005.mp4 | 8s | 624→815 | Debout posture | À fixer |
| 6 | 006.mp4 | 8s | 816→1007 | Reprise jogging | À fixer |
Total : 42s = 1008 frames @ 24fps

### Zones Watchdog batch_controlnet V1.4
| Frames | Zone | Watchdog | SSIM | Maître |
|--------|------|----------|------|--------|
| 0→143 | Course 1 | ON | >0.25 | frame 0 |
| 144→287 | Transition/Visage | OFF | - | None |
| 288→431 | Chute | OFF | - | frame 334 |
| 432→623 | Relèvement | OFF | - | None |
| 624→815 | Debout | OFF | - | None |
| 816→1007 | Course 2 | ON | >0.25 | frame 816 |

---

## 3. CONFIG COMFYUI SDXL VALIDÉE (Pipeline A)

```
Checkpoint   : fabricatedXL_v70.safetensors
LoRA         : asuka-langley-soryuu-classic-ponyxl-lora-nochekaiser.safetensors
LoRA weight  : 0.75
ControlNet   : control-lora-openposeXL2-rank256.safetensors
CN strength  : 0.85   ← V1.4 (corrigé depuis 1.0)
CN start     : 0.0
CN end       : 0.80   ← V1.4 (corrigé depuis 1.0 — libère 20% finaux)
VAE          : taesdxl
Résolution   : 1344x768
Sampler      : dpmpp_2m / karras
CFG          : 6.0
Steps        : 40
CLIP Vision  : model.safetensors (CLIP-ViT-H-14-laion2B-s32B-b79K)
               dans D:\Ov3rLoRd AI\ComfyUI\models\clip_vision\
IP-Adapter   : ip-adapter-plus_sdxl_vit-h.safetensors ← modèle actif
               (ip-adapter-faceid-plusv2_sdxl.bin nécessite insightface + modèle ONNX)
IPA weight   : 0.70 / start 0.0 / end 0.30 / weight_type linear / K+V
IPA mode     : rolling (frame N-1 comme source)
Seed         : par shot (SEEDS_BY_SHOT dans batch_controlnet.py — à fixer manuellement)
```

### Prompt positif batch_controlnet V1.4
```
(masterpiece:1.4), (best quality:1.4), (ultra detailed:1.3), (absurdres:1.2), sharp focus,
1girl, solo, asuka langley soryu, perfect face, angry confident expression, blue eyes,
flowing red hair, long red hair dramatically swept back by wind,
iconic red plugsuit, glossy reflective plugsuit, skin-tight plugsuit, detailed plugsuit seams,
TWO black stripes on thigh only,
full body, perfect anatomy, side view, running at maximum speed, extreme dynamic running pose,
leaning aggressively forward, powerful sprint, explosive leg stride, dynamic arm pumping, motion blur,
heavy speed lines, intense movement, wind pressure effect, sense of extreme velocity,
anime style, cel shading, bold lines, evangelion aesthetic, vibrant colors,
pure white background,
consistent character, same face, same hairstyle, same proportions, same outfit, same colors,
consistent anime style, fixed camera angle, same perspective
```

### Prompt négatif
```
worst quality, low quality, blurry, deformed, extra limbs,
multiple characters, ugly, bad anatomy, watermark, signature,
realistic, photograph, 3d render, multiple girls, nsfw,
three stripes, four stripes, stripes on arm
```

---

## 4. AGENTS PIPELINE A — LIVRÉS CETTE SESSION

| Agent | Chemin | Version | Statut | Rôle |
|-------|--------|---------|--------|------|
| `batch_controlnet.py` | agents/ | V1.4 | ✅ Livré | SDXL+CN+IPA+Watchdog+Seed/shot |
| `session_manager.py` | agents/ | V1.0 | ✅ Livré | État session, rollback, reprise drift |
| `skeleton_remapper.py` | agents/ | V1.0 | ✅ Livré | Remap 912x912→1344x768 |
| `qwen_prompt_refiner.py` | agents/ | V1.0 | ✅ Livré | Feedback visuel QwenVL inter-frames |
| `inpaint_corrector.py` | agents/ | V1.0 | ✅ Livré | Inpaint chirurgical zones défectueuses |

### Workflow ComfyUI test seed (Pipeline A)
```
asuka_seed_test_v3.json — à la racine D:\OVERLORD\
Workflow manuel pour fixer la seed avant batch.
Nodes : Checkpoint → LoRA → CLIPTextEncode×2 → ControlNet → IPAdapter → KSampler → VAE → Save
IPAdapter model : ip-adapter-plus_sdxl_vit-h.safetensors
CLIP Vision     : model.safetensors (ViT-H-14)
```

### Commandes Pipeline A
```batch
:: 1. Remapper les squelettes (FAIT — skeletons_1344x768/ peuplé)
py -3.12 agents\skeleton_remapper.py batch --input "D:\OVERLORD\DEMO\frames\skeletons" --output "D:\OVERLORD\DEMO\frames\skeletons_1344x768"

:: 2. Fixer la seed shot 1 après test ComfyUI manuel
py -3.12 agents\batch_controlnet.py --set-seed 1 <SEED>

:: 3. Pré-validation 3 frames shot 1
py -3.12 agents\batch_controlnet.py --shots 1 --prevalidation-only

:: 4. Batch complet shot 1
py -3.12 agents\batch_controlnet.py --shots 1 --skip-prevalidation --ipa-mode rolling

:: 5. Rapport session
py -3.12 agents\batch_controlnet.py --report

:: 6. Mode dry-run (test sans générer)
py -3.12 agents\batch_controlnet.py --dry-run --start 0 --end 5
```

---

## 5. ÉTAT EN FIN DE SESSION

### Fait ✅
- skeleton_remapper.py : 1008 squelettes remappés vers 1344x768 — validé visuellement
- batch_controlnet.py V1.4 : dry-run OK
- Workflow ComfyUI asuka_seed_test_v3.json : pipeline fonctionnel validé
- insightface installé (`"D:\Ov3rLoRd AI\python_embeded\python.exe" -m pip install insightface`)
- ip-adapter-plus_sdxl_vit-h.safetensors copié dans ComfyUI\models\ipadapter\
- model.safetensors (ViT-H-14) copié dans ComfyUI\models\clip_vision\
- Première frame test générée : qualité pro ✅ (frame inversée — flip auto corrige en batch)
- Session_manager.py, qwen_prompt_refiner.py, inpaint_corrector.py livrés

### En cours / À faire
- **PRIORITÉ 1** : Fixer seed manuellement dans ComfyUI (générer jusqu'à résultat proche frame 0 référence, noter la seed)
- **PRIORITÉ 2** : `py -3.12 agents\batch_controlnet.py --set-seed 1 <SEED>` puis pré-validation
- **PRIORITÉ 3** : Batch complet 1008 frames shot par shot
- **PRIORITÉ 4** : cycle_detector.py (meilleur cycle 24 frames dans Course 1 pour loop démo)
- **PRIORITÉ 5** : frames_to_video.py → asuka_run_FINAL.mp4

### Bugs Pipeline A
| Bug | Impact | Statut |
|-----|--------|--------|
| Seed non fixée → incohérence inter-frames | Haut | Action immédiate |
| Frame inversée (miroir) | Moyen | Flip auto actif en batch (zones course) |
| insightface FaceID : requiert modèle ONNX supplémentaire | Moyen | Basculé sur ip-adapter-plus_sdxl_vit-h ✅ |
| ip-adapter weight_type "original" non supporté | Résolu | Basculé sur "linear" ✅ |

---

## 6. ARCHITECTURE PIPELINE B — MAESTRO STANDARD

### Flux V2.21
```
maestro.py → sourcing → scenario → storyboard → production → QC → postprod
```

### Workflows ComfyUI actifs
```
D:\OVERLORD\Advanced_QwenVL_V35.json  ← Format UI (209 nodes) — génération principale
D:\OVERLORD\Detailer_V35.json          ← Format UI (140+ nodes) — post-processing
D:\OVERLORD\Combined_V35_API.json      ← Format API flat (74 nodes) — DOIT ÊTRE À LA RACINE
                                          (était absent — backup récupéré cette session)
```

**RÈGLE CRITIQUE** : `Combined_V35_API.json` est le workflow que supervisor charge via API.
Il doit être présent à `D:\OVERLORD\Combined_V35_API.json`.
Ne pas confondre avec Advanced_QwenVL_V35.json (format UI, non soumissible directement à l'API).

### Nodes critiques Combined_V35_API.json
```
Node 62  : Lora Loader (LoraManager) — injection LoRA principale
Node 303 : Lora Loader (LoraManager) — injection LoRA detailer
Node 112 : Seed (rgthree) — seed principale
Node 87  : CLIPTextEncode — prompt positif 1
Node 99  : CLIPTextEncode — prompt positif 2
Node 111 : CLIPTextEncode — prompt négatif
Node 75  : easy int — width
Node 77  : easy int — height
Node 116 : KSampler — génération
Node 334 : Image Saver — sauvegarde
```

### Constantes supervisor (agent_supervisor_v2.py)
```python
ADV_LORA_ID   = "62"    # Lora Loader (LoraManager) — format inputs["loras"]["__value__"]
ADV_SEED_ID   = "112"   # Seed (rgthree)
ADV_DIFF_ID   = "68"    # DifferentialDiffusion
ADV_POS_87    = "87"    # CLIPTextEncode positif
ADV_POS_99    = "99"    # CLIPTextEncode positif 2
ADV_NEG_ID    = "111"   # CLIPTextEncode négatif
ADV_WIDTH_ID  = "75"    # easy int width
ADV_HEIGHT_ID = "77"    # easy int height
DET_LORA_ID   = "303"   # Lora Loader detailer — format inputs["lora_stack"]["__value__"]
DET_SEED_ID   = "382"
DET_POS_ID    = "301"
DET_NEG_ID    = "380"
```

### agent_supervisor_v2.py patché V2.24
Livré cette session : `agent_supervisor_v2_patched.py`
Corrections apportées :
1. `set_lora_node()` universel — détecte le type de node et écrit au bon format :
   - `LoraLoader` natif → `inputs["lora_name"]` + `strength_model` + `strength_clip`
   - `Lora Loader (LoraManager)` (node 62) → `inputs["loras"]["__value__"] = [[name, sm, sc]]`
   - `LoraManager` avec lora_stack (node 303) → `inputs["lora_stack"]["__value__"]`
2. `strength_clip` ajouté (manquait)
3. Doublon bloc ControlNet OpenPose supprimé (était dupliqué lignes 373-396)

**Déploiement** : copier dans `D:\OVERLORD\agent_supervisor_v2.py` ET `D:\OVERLORD\agents\agent_supervisor_v2.py`

### Vision long terme Pipeline B — Style Ankama
```
Run 1 — Génération brute    : Combined_V35_API.json (SDXL + LoRA + ControlNet)
Run 2 — Détail/Correction   : Detailer_V35.json (FaceDetailer + inpaint mains)
Run 3 — Style post-process  : Detailer shaders GLSL (cel shading, outlines)
Run 4 — Assemblage          : frames_to_video.py
```
Chaque run produit des layers PNG séparés (bg/char/fx/inpaint) + sidecar _prompt.json.

---

## 7. HARDWARE ET CHEMINS

### Hardware
```
GPU principal : RTX 5080 16GB VRAM
GPU secondaire: RTX 2070 8GB
RAM           : 32GB
Python        : 3.12.3 (py -3.12 — OBLIGATOIRE)
Python 3.14   : installé mais NE PAS UTILISER (argparse incompatible avec maestro.py)
PyTorch       : 2.12.0+cu130
ComfyUI       : 0.25.0
```

### Chemins système
```
ComfyUI root  : D:\Ov3rLoRd AI\ComfyUI\
ComfyUI input : D:\Ov3rLoRd AI\ComfyUI\input\
ComfyUI output: D:\Ov3rLoRd AI\ComfyUI\output\asuka_run\
ComfyUI models: D:\Ov3rLoRd AI\ComfyUI\models\
  checkpoints : D:\Ov3rLoRd AI\ComfyUI\models\checkpoints\
  loras       : D:\Ov3rLoRd AI\ComfyUI\models\loras\
  controlnet  : D:\Ov3rLoRd AI\ComfyUI\models\controlnet\
  ipadapter   : D:\Ov3rLoRd AI\ComfyUI\models\ipadapter\
  clip_vision : D:\Ov3rLoRd AI\ComfyUI\models\clip_vision\
OVERLORD root : D:\OVERLORD\
DEMO dir      : D:\OVERLORD\DEMO\
Agents        : D:\OVERLORD\agents\
Squelettes src: D:\OVERLORD\DEMO\frames\skeletons\
Squelettes rmp: D:\OVERLORD\DEMO\frames\skeletons_1344x768\   ← PEUPLÉ ✅
Ancre IPA     : D:\OVERLORD\DEMO\frame_0000_00001_.png        ← frame référence Asuka sprint
Session state : D:\OVERLORD\DEMO\session_state.json
GitHub        : https://github.com/g915tlk-design/OVERLORD.git
```

### Modèles ComfyUI installés
```
Checkpoints : fabricatedXL_v70.safetensors
LoRAs       : asuka-langley-soryuu-classic-ponyxl-lora-nochekaiser.safetensors ✅
              mari-makinami-rebuild-ponyxl-lora-nochekaiser.safetensors
              rei-ayanami-classic-ponyxl-lora-nochekaiser.safetensors
ControlNet  : control-lora-openposeXL2-rank256.safetensors ✅
VAE         : taesdxl ✅ (sdxl_vae.safetensors tronqué — NE PAS UTILISER)
IP-Adapter  : ip-adapter-plus_sdxl_vit-h.safetensors ✅ (actif)
              ip-adapter-faceid-plusv2_sdxl.bin (FaceID — nécessite insightface ONNX)
CLIP Vision : model.safetensors (ViT-H-14-laion2B-s32B-b79K) ✅ (pour ip-adapter-plus)
              CLIP-ViT-bigG-14-laion2B-39B-b160k.safetensors (pour FaceID — incompatible plus)
```

---

## 8. AGENTS PIPELINE B — ÉTAT V2.24

### Agents actifs
| Agent | Statut | Rôle |
|-------|--------|------|
| `maestro.py` | ✅ Racine | Chef d'orchestre |
| `agent_supervisor_v2.py` | ✅ Patché V2.24 | Batch ComfyUI + injection LoRA corrigée |
| `director.py` | ✅ | Arbitrateur mode/arc |
| `scenario.py` | ✅ | Scénario LLM + UNIVERSE_SYSTEM_CONSTRAINTS |
| `storyboard.py` | ✅ | Storyboard 8 shots |
| `prompt_translator.py` | ✅ | Narratif → JSON intent |
| `negative_bank.py` | ✅ | Négatifs contextuels |
| `clip_validator.py` | ✅ | Cohérence CLIP inter-shots |
| `visual_validator.py` | ✅ | QwenVL validation par rôle |
| `inpaint_queue.py` | ✅ | Inpaint auto sur REJECT |
| `pacing_engine.py` | ✅ | Manifeste timing |
| `pose_generator.py` | ✅ Racine+agents | DWPose depuis image |
| `pose_library.py` | ✅ Racine+agents | Bibliothèque poses |
| `audit_logger.py` | ✅ | SQLite WAL |
| `overlord_utils.py` | ✅ | LLM utils + fallback |
| `context_bus.py` | ✅ | Singleton inter-agents |

### Nouveaux agents livrés cette session (Pipeline A)
| Agent | Statut |
|-------|--------|
| `session_manager.py` | ✅ agents/ |
| `skeleton_remapper.py` | ✅ agents/ |
| `batch_controlnet.py` V1.4 | ✅ agents/ |
| `qwen_prompt_refiner.py` | ✅ agents/ |
| `inpaint_corrector.py` | ✅ agents/ |

---

## 9. RÈGLES ABSOLUES

```
1.  py -3.12 TOUJOURS (jamais python ou py seul ou py -3.14)
2.  Fichiers livrés via create_file tool UNIQUEMENT (jamais bash redirect)
3.  ast.parse() validation AVANT toute livraison Python
4.  Patches via patcher.py FORMAT A UNIQUEMENT — un seul bundle groupé
5.  LLM imports toujours en try/except avec fallback
6.  Projet toujours "Ov3rLoRd" (jamais OverLord)
7.  EVA-01 exclu du scope démo (pas de LoRA entraîné)
8.  Single character par séquence (ControlNet OpenPose conflits multi-perso)
9.  taesdxl permanent (sdxl_vae.safetensors tronqué — NE PAS utiliser)
10. agent_supervisor_v2.py déployé aux DEUX endroits : racine + agents/
11. Combined_V35_API.json doit être à D:\OVERLORD\ (format API flat, pas UI)
12. Advanced_QwenVL_V35.json = format UI — ne pas soumettre directement à l'API
13. Nettoyer workspace\archive\ avant run de test (évite vidéos 700+ images)
14. Steps = 40 (batch_controlnet Pipeline A) | 35 (maestro Pipeline B)
15. IPAdapter weight_type = "linear" (pas "original" — non supporté par la version installée)
16. Seed par shot obligatoire avant batch complet (SEEDS_BY_SHOT dans batch_controlnet.py)
```

---

## 10. DÉPENDANCES INSTALLÉES CETTE SESSION

```batch
:: insightface (installé mais FaceID nécessite aussi modèle ONNX)
"D:\Ov3rLoRd AI\python_embeded\python.exe" -m pip install insightface

:: scikit-image (pour SSIM watchdog)
py -3.12 -m pip install scikit-image --break-system-packages
```

---

## 11. ROADMAP

### P0 — Immédiat (J-15 Japan Expo)
| # | Tâche | Statut |
|---|-------|--------|
| 1 | Fixer seed manuellement ComfyUI — noter valeur | 🔥 EN COURS |
| 2 | `--set-seed 1 <SEED>` puis pré-validation 3 frames | À faire |
| 3 | Batch complet shot 1 (frames 0→143) | À faire |
| 4 | Valider shot 1 → répéter pour shots 2-6 | À faire |
| 5 | cycle_detector.py — meilleur cycle 24 frames Course 1 | À faire |
| 6 | frames_to_video.py → asuka_run_FINAL.mp4 | À faire |
| 7 | Audio sync EVA OST | À faire |
| 8 | Déployer agent_supervisor_v2_patched.py (racine + agents/) | À faire |
| 9 | Remettre Combined_V35_API.json à la racine D:\OVERLORD\ | À faire |

### P1 — Court terme post-batch
- cycle_detector.py : détection cycle 24 frames pour loop démo
- Normalisation direction flip sur batch complet
- Test maestro Pipeline B avec supervisor patché

### P2 — Post Japan Expo
- Pipeline 24 minutes pour pitch Khara
- LoRA Asuka custom Kohya (à partir des 1008 frames validées)
- inpaint_queue V1.1 : remplacer frame originale si CLIP améliore
- Audio sync EVA OST
- Conversion Advanced_QwenVL_V35.json → format API pour load_workflow()
- Contact JF/Sandrine SEFA — suivi Japan Expo

---

## 12. NOTES TECHNIQUES IMPORTANTES

### IPAdapter — Compatibilité modèle/CLIP
```
ip-adapter-plus_sdxl_vit-h.safetensors → CLIP Vision : model.safetensors (ViT-H-14) ✅
ip-adapter-faceid-plusv2_sdxl.bin      → CLIP Vision : CLIP-ViT-bigG (ViT-G)
                                        + insightface package
                                        + modèle ONNX buffalo_l (non installé)
→ Garder ip-adapter-plus_sdxl_vit-h pour le batch — plus stable, pas de dépendances
```

### batch_controlnet.py V1.4 vs V1.3
```
V1.3 → V1.4 :
  CN strength : 1.0 → 0.85 (anti-rigidité, validé sources)
  CN end      : 1.0 → 0.80 (libère 20% finaux pour éclairage organique)
  SSIM seuil  : 0.55 → 0.25 (corrigé — 0.55 trop strict)
  IPA weight  : 0.5 → 0.70
  IPA end_at  : 1.0 → 0.30 (IPAdapter ancre style seulement)
  IPA source  : rolling (frame N-1) configurable --ipa-mode rolling/fixed/hybrid
  Seed        : SEED_BASE+frame → SEEDS_BY_SHOT (par shot, stable visuellement)
  Squelettes  : auto-détection dossier remappé skeletons_1344x768/
  Architecture: urllib natif conservé (V1.3) + wait_for_idle() polling /queue
  Flip auto   : conservé (zones course)
  Retry×3     : conservé avec seed différente par retry
```

### session_manager.py — Fonctions clés
```python
from agents.session_manager import (
    create_session,          # Nouvelle session
    load_session,            # Charger depuis JSON
    save_session,            # Sauvegarder
    update_frame,            # Màj statut frame (generated/validated/rejected/reprendre)
    get_ipadapter_source,    # Source IPA selon mode rolling/fixed/hybrid
    get_resume_frame,        # Depuis quel frame reprendre
    mark_shot_for_resume,    # Marquer shot pour reprise
    rollback_shot,           # Rollback dur à un frame
    get_prevalidation_frames,# [frame_start, mid, frame_end]
    prevalidation_passed,    # True si 3 frames pré-validation validées
    session_report,          # Rapport texte état session
)
```

### Injection LoRA dans Combined_V35_API.json
```python
# Node 62 — Lora Loader (LoraManager) — format correct
node["inputs"]["loras"]["__value__"] = [
    [lora_name, strength_model, strength_clip]
]
# Exemple Asuka
node["inputs"]["loras"]["__value__"] = [
    ["asuka-langley-soryuu-classic-ponyxl-lora-nochekaiser.safetensors", 0.75, 0.75]
]
```

---

*Ov3rLoRd V2.24*
*"La connaissance est binaire, pas incertaine."*
*Japan Expo 2026. J-15. 🔥*
*Généré le 2026-06-24 — Session batch_controlnet V1.4 + seed test + supervisor patch*

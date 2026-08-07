# CONTEXTE_OVERLORD_V225.md
# Cerveau de Démarrage — Session 2026-06-24 (après-midi)
# Pipeline Ov3rLoRd / Jérémy Gourlain
# Généré en fin de session — reprendre immédiatement sans questions superflues

---

## 0. CONTEXTE UTILISATEUR

**Jérémy Gourlain** — Le Havre, France. Développeur solo.
- BTS MUC (commerce/management) + TFIC chimie industrielle
- Culture geek profonde : DBZ, EVA, Gundam, SAO Alicization, Gunnm, HxH...
- Gundam Perfect Grade RX-78-2 + figurines Gundam/Megami Device → poses OpenPose
- Objectif : film 24 minutes → pitch Khara (Noisy-le-Grand)

**Style de collaboration :**
- Valide rapidement, passe à l'action
- Patches via patcher.py FORMAT A UNIQUEMENT — un seul bundle groupé
- Toujours "Ov3rLoRd" (jamais "OverLord")
- Architecte en chef — force de proposition, initiative
- Toujours py -3.12 (jamais python ou py seul)
- Fichiers livrés via create_file tool UNIQUEMENT (jamais bash redirect)
- ast.parse() validation AVANT toute livraison Python

---

## 1. ÉTAT RÉEL DU PROJET

### Ce qui fonctionne réellement
- ComfyUI 0.25.0 opérationnel port 8188
- fabricatedXL_v70.safetensors génère des images qualité studio
- LoRA Asuka classic (weight 0.75) fonctionne
- taesdxl VAE opérationnel (sdxl_vae.safetensors tronqué — permanent)
- DWPose : 1008 squelettes générés et remappés 1344x768
- batch_controlnet.py V1.5 : dry-run OK, cache-buster livré (patch V1.5)
- skeleton_remapper.py : skeletons_1344x768/ peuplé
- ip-adapter-plus_sdxl_vit-h.safetensors installé
- model.safetensors (ViT-H-14) installé dans clip_vision/

### Ce qui ne fonctionne PAS (bugs confirmés)

**BUG CRITIQUE 1 — ControlNet silencieusement ignoré**
- Symptôme : générer avec ou sans ControlNet = résultat identique
- Cause probable : control-lora-openposeXL2-rank256.safetensors non trouvé
  par ComfyUI → node bypassé silencieusement sans erreur
- À diagnostiquer : logs console ComfyUI lors soumission job
- À vérifier : chemin exact du modèle dans D:\Ov3rLoRd AI\ComfyUI\models\controlnet\

**BUG CRITIQUE 2 — Cache ComfyUI node LoadImage (PATCHÉ V1.5)**
- Symptôme : seule la frame 0 respectait le squelette, frames suivantes ignoraient
- Cause : ComfyUI cache le node LoadImage par nom de fichier
- Fix livré : noms fixes ov_skeleton_current.png / ov_ipa_ref_current.png
- Statut : patch livré, non encore testé en prod

**BUG FONDAMENTAL (jamais résolu) — 1 image = 1 pass ComfyUI**
- Depuis V1.0, une image = un seul passage ComfyUI
- Jérémy demande depuis le début : production multi-pass
- Jamais implémenté malgré documentation dans contextes successifs
- C'est LE problème architectural central

### Ce qui a été documenté mais jamais implémenté
- Multi-pass production (Run 1 brut → Run 2 détail → Run 3 style)
- Layers PNG séparés par shot (bg/char/fx/inpaint + sidecar _prompt.json)
- cycle_detector.py (détection meilleur cycle 24 frames)
- Combined_V35_API.json à remettre à la racine D:\OVERLORD\
- agent_supervisor_v2_patched.py à déployer (racine + agents/)

---

## 2. PRIORITÉS TECHNIQUES RÉELLES

### P0 — Diagnostiquer ControlNet (BLOQUANT)
Avant tout batch, confirmer que ControlNet fonctionne réellement.

**Diagnostic :**
```batch
:: 1. Vérifier que le modèle existe physiquement
dir "D:\Ov3rLoRd AI\ComfyUI\models\controlnet\"

:: 2. Soumettre un job et regarder les logs ComfyUI console
:: Si le log dit "ControlNet model loaded" → OK
:: Si rien → modèle non trouvé, bypassé silencieusement

:: 3. Test visuel définitif : générer une frame avec un squelette
::    complètement absurde (bras en X, jambes écartées)
::    Si l'image respecte la pose → ControlNet actif
::    Si l'image ignore la pose → ControlNet mort
```

**Cause probable :** Le nom `control-lora-openposeXL2-rank256.safetensors`
dans le code ne correspond pas au nom exact du fichier sur disque.
Vérifier la casse et l'orthographe exacte.

### P1 — Multi-pass production (LE vrai chantier)
Architecture cible :
```
Pass 1 — Génération brute    : SDXL + LoRA + ControlNet → PNG base
Pass 2 — Détail/Correction   : Detailer_V35.json → FaceDetailer + inpaint mains
Pass 3 — Style post-process  : cel shading, outlines, couleurs EVA
```
Chaque pass prend l'output du précédent comme input.
Un seul agent orchestrateur : multi_pass_producer.py

### P2 — Valider le cache-buster V1.5
Après fix ControlNet, tester 5 frames consécutives et vérifier
que chaque frame respecte son squelette.

---

## 3. ARCHITECTURE PIPELINE — ÉTAT RÉEL V2.25

### Pipeline A — Production directe frames (actif)
```
DWPose squelettes (1008, remappés 1344x768)
    ↓
batch_controlnet.py V1.5
    → Pass 1 : SDXL + LoRA + ControlNet (si diagnostiqué OK)
    → [Pass 2 : Detailer — À CONSTRUIRE]
    → [Pass 3 : Style — À CONSTRUIRE]
    ↓
frames_to_video.py → MP4
```

### Pipeline B — Maestro standard (secondaire)
```
maestro.py → sourcing → scenario → storyboard → production → postprod
```
Workflows disponibles :
- `D:\OVERLORD\Advanced_QwenVL_V35.json` — format UI (209 nodes)
- `D:\OVERLORD\Detailer_V35.json` — format UI (140+ nodes)
- `D:\OVERLORD\Combined_V35_API.json` — format API flat (74 nodes) — DOIT ÊTRE À LA RACINE

---

## 4. CONFIG COMFYUI VALIDÉE

```
Checkpoint   : fabricatedXL_v70.safetensors  (NE JAMAIS MODIFIER)
LoRA         : asuka-langley-soryuu-classic-ponyxl-lora-nochekaiser.safetensors
LoRA weight  : 0.75
ControlNet   : control-lora-openposeXL2-rank256.safetensors  ← À DIAGNOSTIQUER
CN strength  : 0.85 / CN start : 0.0 / CN end : 0.80
VAE          : taesdxl  (permanent — sdxl_vae.safetensors tronqué)
Résolution   : 1344x768
Sampler      : dpmpp_2m / karras
CFG          : 6.0
Steps        : 40
IP-Adapter   : ip-adapter-plus_sdxl_vit-h.safetensors
CLIP Vision  : model.safetensors (ViT-H-14)
IPA weight   : 0.70 / start 0.0 / end 0.30 / weight_type linear
```

---

## 5. HARDWARE ET CHEMINS

```
GPU principal : RTX 5080 16GB VRAM
GPU secondaire: RTX 2070 8GB
RAM           : 32GB
Python        : 3.12.x — py -3.12 OBLIGATOIRE (3.14 installé mais NE PAS UTILISER)
PyTorch       : 2.12.0+cu130
ComfyUI       : 0.25.0

ComfyUI root  : D:\Ov3rLoRd AI\ComfyUI\
ComfyUI input : D:\Ov3rLoRd AI\ComfyUI\input\
ComfyUI output: D:\Ov3rLoRd AI\ComfyUI\output\asuka_run\
controlnet    : D:\Ov3rLoRd AI\ComfyUI\models\controlnet\
ipadapter     : D:\Ov3rLoRd AI\ComfyUI\models\ipadapter\
clip_vision   : D:\Ov3rLoRd AI\ComfyUI\models\clip_vision\
OVERLORD root : D:\OVERLORD\
Agents        : D:\OVERLORD\agents\
Squelettes    : D:\OVERLORD\DEMO\frames\skeletons_1344x768\  (1008 fichiers)
Ancre IPA     : D:\OVERLORD\DEMO\frame_0000_00001_.png
GitHub        : https://github.com/g915tlk-design/OVERLORD.git
```

---

## 6. AGENTS LIVRÉS ET OPÉRATIONNELS

| Agent | Version | Chemin | Statut |
|-------|---------|--------|--------|
| batch_controlnet.py | V1.5 | agents/ | ✅ cache-buster, ControlNet à diagnostiquer |
| skeleton_remapper.py | V1.0 | agents/ | ✅ 1008 squelettes remappés |
| session_manager.py | V1.0 | agents/ | ✅ livré |
| frames_to_video.py | — | agents/ | ✅ livré |
| frame_extractor.py | — | agents/ | ✅ livré |
| maestro.py | — | racine | ✅ opérationnel |
| agent_supervisor_v2.py | V2.24 patché | racine + agents/ | ⚠ patched non déployé |
| director.py | — | agents/ | ✅ |
| overlord_utils.py | — | racine | ✅ |
| context_bus.py | — | agents/ | ✅ |
| patcher.py | V1.1 | racine | ✅ |

---

## 7. RÈGLES ABSOLUES

```
1.  py -3.12 TOUJOURS
2.  create_file tool UNIQUEMENT pour livraison
3.  ast.parse() AVANT toute livraison Python
4.  patcher.py FORMAT A UNIQUEMENT — bundle groupé
5.  LLM imports en try/except avec fallback
6.  "Ov3rLoRd" toujours (jamais OverLord)
7.  taesdxl permanent
8.  agent_supervisor_v2.py : racine + agents/ (les deux)
9.  Combined_V35_API.json : format API flat, à la racine D:\OVERLORD\
10. Advanced_QwenVL_V35.json : format UI — ne pas soumettre directement à l'API
11. Steps batch_controlnet = 40 | Steps maestro = 35
12. EVA-01 exclu (pas de LoRA)
13. Single character par séquence
```

---

## 8. PROCHAINE SESSION — ORDRE D'ATTAQUE

```
1. DIAGNOSTIQUER ControlNet
   → dir "D:\Ov3rLoRd AI\ComfyUI\models\controlnet\"
   → Comparer nom exact fichier vs CONTROLNET dans batch_controlnet.py
   → Test visuel avec squelette absurde

2. Si ControlNet mort → corriger le nom dans batch_controlnet.py (patch)
   Si ControlNet vivant → tester 5 frames avec cache-buster V1.5

3. Construire multi_pass_producer.py
   → Pass 1 brut → Pass 2 Detailer → output final
   → C'est le chantier central, jamais fait, demandé depuis le début

4. Déployer agent_supervisor_v2_patched.py
   → copier racine + agents/
```

---

## 9. CE QUI NE SERT À RIEN DE REDISCUTER

- Japan Expo : hors scope
- Seed par shot : secondaire tant que ControlNet non validé
- cycle_detector.py : après multi-pass
- youtube_publisher.py, EDL DaVinci : post-production lointaine
- LoRA Asuka custom Kohya : post-production lointaine

---

*Ov3rLoRd V2.25*
*"La connaissance est binaire, pas incertaine."*
*Généré le 2026-06-24*

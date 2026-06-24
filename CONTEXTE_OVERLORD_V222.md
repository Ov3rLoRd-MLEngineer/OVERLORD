# CONTEXTE_OVERLORD.md
## Cerveau de démarrage — Pipeline IA Anime Ov3rLoRd V2.22
### Studio Onibaku Gumi 鬼爆組
**Généré le : 24 juin 2026 — Fin de session**
**Auteur :** Claude Sonnet 4.6 (instance précédente)
**Destinataire :** Nouvelle instance Claude — reprendre immédiatement sans questions superflues

---

## 0. CONTEXTE UTILISATEUR

**Jérémy Gourlain** — Le Havre, France. Développeur solo.
- BTS MUC (commerce/management) + TFIC chimie industrielle
- Culture geek profonde : DBZ, EVA, Gundam, SAO Alicization, Gunnm, HxH...
- Collection physique : figurines Gundam + Megami Device → source de poses OpenPose
- Gunpla disponibles : RX-78-2 Perfect Grade (polarized) + Unicorn Perfectibility complet + RG montés
- **Deadline absolue : Japan Expo 9-12 juillet 2026** — Contact JF/Sandrine (SEFA)
- Objectif démo : 2 minutes anime EVA qualité studio sur tablette
- Objectif long terme : film 24 minutes → Khara (Noisy-le-Grand)
- Crédits API Grok à récupérer → utiliser pour génération prompts en production

**Style de collaboration :**
- Valide rapidement, passe à l'action
- Patches via patcher.py FORMAT A UNIQUEMENT — regrouper en un seul bundle
- Fonctionnement "dream mode" la nuit (pipeline autonome)
- Toujours "Ov3rLoRd" (jamais "OverLord")
- Toujours py -3.12 (jamais python ou py seul)

---

## 1. ARCHITECTURE V2.22

### 1.1 Phases
```
PHASE 0 — Run 0 : Bible Visuelle (UNE FOIS par projet)
  character_sheet_generator.py → 9 poses/expressions par personnage
  style_dna_generator.py       → image référence style pur

PHASE 1 — Sourcing → Scénario → Storyboard
  sourcing.py → scenario.py → storyboard.py
  storyboard.py appelle prompt_translator.py en fin de run_storyboard()

PHASE 2 — Production
  maestro.py → agent_supervisor_v2.py → ComfyUI API port 8188
  ControlNet OpenPose actif si --pose ou pose_library.py
  prompt_override.py → inject prompts manuels image par image si présent

PHASE 2.5 — Quality Control
  maestro.py::block_quality_control()
    → clip_validator.py     [seuil adaptatif depuis watchdog_config]
    → visual_validator.py   [QwenVL prompts dynamiques par scene_type]
    → inpaint_queue.py      [inpaint auto frames REJECT]
    → pacing_engine.py      [manifeste timing pour postprod]

PHASE 3 — Post-production
  postprod.py → transition_builder.py → audio_compositor.py
  postprod lit pacing_{run_id}.json pour les durées
```

### 1.2 Hardware validé
```
GPU       : RTX 5080 16GB (principale) | RTX 2070 8GB (futur serveur)
Steps     : 35 (validé — PAS 80)
CFG       : 7.0
Sampler   : dpmpp_2m_sde / karras
VAE       : taesdxl (sdxl_vae.safetensors tronqué)
Résolution: 1344×1984
ControlNet: OpenPoseXL2.safetensors | strength=0.85→1.0 à tester | end_percent=0.85→1.0 à tester
            aussi disponible : control-lora-openposXL2-rank256.safetensors (benchmark P2)
ComfyUI   : D:\Ov3rLoRd AI\ComfyUI\ port 8188 — version 0.25.0
Checkpoint: fabricatedXL_v70.safetensors (NE JAMAIS MODIFIER)
LoRAs EVA : asuka-langley-soryuu-classic-ponyxl-lora-nochekaiser.safetensors (weight=0.75 validé)
            mari-makinami-rebuild-ponyxl-lora-nochekaiser.safetensors
            rei-ayanami-classic-ponyxl-lora-nochekaiser.safetensors
LTX-Video : ltx-video-2b-v0.9.5.safetensors → D:\Ov3rLoRd AI\ComfyUI\models\checkpoints\ltx\
            (téléchargé session 24/06/2026 — ~7GB)
            Usage : génération vidéos de référence pour extraction DWPose
```

### 1.3 Racine et chemins
```
D:\OVERLORD\                    ← racine projet
D:\OVERLORD\agents\             ← tous les agents Python
D:\OVERLORD\workspace\          ← outputs, logs, archive, audit
D:\OVERLORD\workspace\poses\    ← skeletons OpenPose
  asuka_skeleton.png            ← pose figurine Asuka plugsuit+hoodie (validée)
  openpose_placeholder.png      ← copie dans ComfyUI\input\ aussi
D:\OVERLORD\workspace\poses\extracted\  ← frames + skeletons extraits par frame_extractor.py
D:\OVERLORD\workspace\reports\  ← rapports CLIP + pacing
D:\OVERLORD\workspace\inpaint\  ← masks + outputs inpaint
D:\OVERLORD\prompt_override.txt ← prompts manuels image par image (NE PAS SUPPRIMER)
D:\Ov3rLoRd AI\ComfyUI\        ← ComfyUI
D:\Ov3rLoRd AI\ComfyUI\input\openpose_placeholder.png ← DOIT EXISTER
Python 3.12.10 (py -3.12)      ← VERSION A UTILISER
Python 3.14 installé mais NE PAS UTILISER (argparse incompatible)
Ollama port 11434 | modèle : mistral
GitHub : https://github.com/g915tlk-design/OVERLORD.git
```

### 1.4 Commandes essentielles
```batch
:: Run standard
run.bat --media-type anime --universe "evangelion battle asuka" --no-qc
run.bat --media-type anime --universe "evangelion battle asuka"

:: Run Asuka Demo (V2.22 — scene_type actif)
run.bat --media-type anime --universe "evangelion asuka running" ^
        --scene-type action_dynamic ^
        --pose "workspace\poses\asuka_skeleton.png"

:: Run avec prompt override manuel
:: (poser le bon prompt_override_shotX.txt → prompt_override.txt avant le run)
copy prompt_override_shot1.txt prompt_override.txt
run.bat --media-type anime --universe "evangelion asuka running" ^
        --scene-type action_dynamic ^
        --pose "workspace\poses\asuka_skeleton.png"

:: Extraire frames d'une vidéo source (segment ciblé)
py -3.12 agents\frame_extractor.py --video "D:\refs\source.mp4" ^
         --start 20 --end 30 --character asuka --action running

:: Générer skeleton depuis image de référence
py -3.12 agents\pose_generator.py --image ma_ref.png --output workspace\poses\ma_pose.png

:: Lister la bibliothèque de poses
py -3.12 agents\pose_library.py --list

:: Vérifier watchdog_config pour un scene_type
py -3.12 watchdog_config.py action_dynamic

:: Vérifier prompt_override
py -3.12 agents\prompt_override.py --file prompt_override.txt --list

:: Git workflow
git add .
git commit -m "V2.22 — description"
git push

:: Reset checkpoint avant run frais
rmdir /s /q "workspace\checkpoints\anime_evangelion_asuka_running"

:: Vérifier ComfyUI
curl http://127.0.0.1:8188/system_stats

:: Vérifier le bus
py -3.12 -c "from agents.context_bus import get_bus; bus = get_bus(); print('universe:', bus.read('director.universe')); print('scene_type:', bus.read('director.scene_type'))"
```

---

## 2. ÉTAT DES AGENTS — V2.22

### 2.1 Agents actifs

| Agent | Version | Statut | Rôle |
|-------|---------|--------|------|
| `prompt_translator.py` | V1.1 | OK | Narratif → JSON intent + negative_bank |
| `character_sheet_generator.py` | V1.2 | OK | 9 poses + LoRa Asuka classic |
| `style_dna_generator.py` | V1.0 | OK | Style DNA par preset |
| `audit_logger.py` | V1.0 | OK | SQLite WAL audit |
| `clip_validator.py` | V1.0 | OK + PATCH V2.22 | Cosinus CLIP — seuil adaptatif depuis watchdog_config |
| `negative_bank.py` | V1.0 | OK | Banque négatifs contextuels |
| `inpaint_queue.py` | V1.0 | OK | Queue inpaint auto sur REJECT |
| `pacing_engine.py` | V1.0 | OK | Manifeste timing par shot |
| `visual_validator.py` | V1.0 | OK + PATCH V2.22 | QwenVL — prompts dynamiques par scene_type |
| `pose_generator.py` | V1.0 | OK | Génère skeleton DWPose depuis image |
| `pose_library.py` | V1.0 | OK | Bibliothèque poses par character/shot_type |
| `frame_extractor.py` | V1.0 | NEW V2.22 | Extrait frames vidéo → DWPose → pose_library |
| `prompt_override.py` | V1.0 | NEW V2.22 | Injecte prompts manuels image par image |
| `watchdog_config.py` | V1.0 | NEW V2.22 | Seuils adaptatifs par scene_type pour tous agents |

### 2.2 Patches appliqués session 24/06/2026 (BUNDLE_PATCH_V222.md)

| Fichier | Changement | Statut |
|---------|------------|--------|
| `director.py` | Publie scene_type + 7 clés watchdog sur bus | À APPLIQUER |
| `clip_validator.py` | Seuil cosinus depuis watchdog_config | À APPLIQUER |
| `visual_validator.py` | Prompts QwenVL dynamiques + échange bus | À APPLIQUER |
| `maestro.py` | --scene-type + --qwenvl-pos/neg CLI | À APPLIQUER |

### 2.3 Fichiers à la racine (PAS dans agents/)
```
maestro.py              ← chef d'orchestre
agent_supervisor_v2.py  ← AUSSI copié dans agents/
patcher.py              ← outil de patch
run.bat                 ← launcher
overlord_utils.py
overlord_utils_utf8.py
watchdog_config.py      ← NEW V2.22 (racine ET agents/)
prompt_override.py      ← NEW V2.22 (racine ET agents/)
pose_generator.py       ← aussi dans agents/
pose_library.py         ← aussi dans agents/
frame_extractor.py      ← NEW V2.22 (racine ET agents/)
```

---

## 3. DÉMO ASUKA RUN — STRUCTURE VALIDÉE

### 3.1 Séquence cible (30 secondes × 4 = 2 minutes)
```
Shot 1 — Départ course / accélération (plan large)         6s / 144 images
Shot 2 — Gros plan visage, concentration, vitesse BG       6s / 144 images
Shot 3 — Chute / contact sol (pose dynamique basse)        6s / 144 images
Shot 4 — Rattrapage / rebond (instant suspendu)            6s / 144 images
Shot 5 — Reprise course / accélération finale (miroir S1)  6s / 144 images
─────────────────────────────────────────────────────────────────────────────
TOTAL : 30 secondes / 720 images × 4 répétitions = 2 minutes / 2880 images
```

### 3.2 Fichiers prompts prêts
```
D:\OVERLORD\prompt_override_shot1.txt  ← 144 prompts validés (Grok source)
D:\OVERLORD\prompt_override_shot2.txt  ← 144 prompts — gros plan visage
D:\OVERLORD\prompt_override_shot3.txt  ← 144 prompts — chute/contact sol
D:\OVERLORD\prompt_override_shot4.txt  ← 144 prompts — rebond suspendu
D:\OVERLORD\prompt_override_shot5.txt  ← 144 prompts — sprint final miroir
```

### 3.3 Stratégie prompts
```
Base commune : asuka langley soryu, red plugsuit, only 1girl, no background...
Structure    : 12 phases biomécanique × 12 répétitions avec drift intensité
Négatif      : intégré en tête de chaque fichier (version Grok augmentée)
Injection    : copy prompt_override_shotX.txt prompt_override.txt avant run
```

### 3.4 Calcul rendu pessimiste
```
720 images × ~30s/image ComfyUI = ~6h rendu brut
+30% inpaint REJECT              = ~8h max
RTX 5080 — run nocturne autonome = livraison J+1 matin
```

---

## 4. NODES QWENVL — MAPPING CONFIRMÉ (screenshot 24/06/2026)

```
Node : QwenVL-Mod Prompt Enhancer
Modèle : Qwen3-VL-4B-Instruct | FP16 | device=auto

Zone 1 (haut — prompt court ComfyUI) :
  masterpiece, best quality, amazing quality, absurdres,
  1girl, solo, looking at viewer
  → injecté via agent_supervisor_v2.py

Zone 2 (bas — system prompt LLM) :
  ## Role
  You are a professional prompt engineer specialized in Booru-style
  tagging for SDXL-based anime models like NoobAI and IllustriousXL...
  → injecté via visual_validator.py patch V2.22
  → surchargeable via bus : qwenvl.prompt_positive / qwenvl.prompt_negative

Paramètres : max_tokens=512, temperature=0.7, top_p=0.9,
             repetition_penalty=1.1, keep_model_loaded=true
enhancement_style : Enhance
```

---

## 5. LTX-VIDEO — INTÉGRATION PIPELINE

```
Modèle    : ltx-video-2b-v0.9.5.safetensors (~7GB)
Chemin    : D:\Ov3rLoRd AI\ComfyUI\models\checkpoints\ltx\
Usage     : génération vidéos de référence pour extraction DWPose
Workflow  : ComfyUI custom node ComfyUI-LTXVideo
Install   : cd "D:\Ov3rLoRd AI\ComfyUI\custom_nodes"
            git clone https://github.com/Lightricks/ComfyUI-LTXVideo

Pipeline référence :
  LTX-Video prompt → vidéo 5-6s → frame_extractor.py (segment ciblé)
  → DWPose skeletons → pose_library.py → run.bat --pose

Prompt type pour référence Asuka running :
  "anime girl in red bodysuit running at full speed, dynamic motion,
   wide shot, single character, white background, clear figure"
```

---

## 6. BUGS ACTIFS

| Bug | Impact | Statut |
|-----|--------|--------|
| ValueError: I/O operation on closed file (logging) | Cosmétique | Post Japan Expo |
| ControlNet strength 0.85 peut-être trop faible | Moyen | À tester 1.0→1.2 |
| end_percent 0.85 → tester 1.0 | Moyen | À tester |
| Watchdog scans anciennes archives → vidéo 700+ images | Moyen | Nettoyer workspace\archive avant run |
| sdxl_vae.safetensors tronqué | Faible | taesdxl actif |
| Reddit HTTP 403 (API sans auth) | Faible | Sourcing RSS fonctionne |
| BUNDLE_PATCH_V222.md — 4 patches pas encore appliqués | BLOQUANT si --scene-type utilisé | À appliquer avant prochain run |

---

## 7. RÈGLES NON NÉGOCIABLES

```
1. Fichiers Python livrés via create_file tool + ast.parse() validé
2. Patches via patcher.py FORMAT A UNIQUEMENT — un seul bundle groupé
3. Toujours py -3.12 (jamais python ou py seul)
4. Combined_V35_API.json supprimé — NE PAS recréer
5. Steps RTX 5080 = 35. VAE = taesdxl. ControlNet = OpenPoseXL2.safetensors
6. "Ov3rLoRd" dans tous les banners
7. maestro.py à la RACINE
8. agent_supervisor_v2.py aux DEUX endroits (racine + agents/)
9. pose_generator.py, pose_library.py, frame_extractor.py,
   prompt_override.py, watchdog_config.py aux DEUX endroits aussi
10. Après chaque session : git add . && git commit -m "..." && git push
11. Nettoyer workspace\archive avant run de test
12. openpose_placeholder.png doit exister dans ComfyUI\input\
13. prompt_override.txt à la racine — copier le bon shotX avant chaque run
14. LTX-Video = vidéos de référence UNIQUEMENT — pas de production finale
```

---

## 8. ROADMAP

### P1 — Avant Japan Expo (J-15)
| # | Tâche | Statut |
|---|-------|--------|
| 1 | Appliquer BUNDLE_PATCH_V222.md via patcher.py | PRIORITÉ 1 |
| 2 | Installer ComfyUI-LTXVideo custom node | À faire |
| 3 | Générer vidéo référence Asuka running via LTX-Video | À faire |
| 4 | frame_extractor.py → skeletons DWPose depuis vidéo référence | À faire |
| 5 | Calibrer ControlNet strength (0.85 → 1.0 → 1.2) | À tester |
| 6 | Test run Shot 1 complet (144 images) avec prompt_override | À faire |
| 7 | Valider qualité → ajuster LoRa weight si besoin (0.75 → 0.85 ?) | À faire |
| 8 | Run complet 5 shots × 144 images (720 images) nocturne | Objectif |
| 9 | Montage 4× → démo 2 minutes | Objectif final |

### P2 — Post Japan Expo
- LoRa Asuka custom sur Kohya SS
- RX-78-2 Perfect Grade → poses stop motion → LoRa Gundam
- Unicorn/Banshee/Phenex — LoRa spécifiques
- benchmark control-lora-openposXL2-rank256 vs OpenPoseXL2
- inpaint_queue V1.1 : remplacer frame originale si CLIP améliore
- EDL DaVinci Resolve / ProRes export
- youtube_publisher.py
- Fix ValueError logging Python 3.12
- API Grok pour génération prompts automatisée

### P3 — Long terme
- Film 24 minutes → présentation Khara
- Multi-perso avec Regional Prompting
- Gundam séquences mécaniques

---

## 9. EXEMPLE INTERROGATION GROK (à réutiliser)

```
"Pour une séquence qui doit durer 6 secondes avec 24 images par seconde,
génère 12 prompts positifs différents qui décomposent précisément,
l'un après l'autre, [DESCRIPTION SHOT] en plan [TYPE PLAN],
pour le personnage Asuka Langley Soryu en plugsuit rouge.
Le plan doit rester identique sur les 12 prompts.
Format : un prompt par ligne, tags Booru-style SDXL."
```

---

*Ov3rLoRd V2.22 — Onibaku Gumi 鬼爆組*
*"La connaissance est binaire, pas incertaine."*
*Japan Expo 2026. 🔥*
*J-15. On est larges.*

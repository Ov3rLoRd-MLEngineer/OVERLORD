# CONTEXTE_OVERLORD.md
## Cerveau de démarrage — Pipeline IA Anime Ov3rLoRd V2.21
### Studio Onibaku Gumi 鬼爆組
**Généré le : 23 juin 2026 — Fin de session**
**Auteur :** Claude Sonnet 4.6 (instance précédente)
**Destinataire :** Nouvelle instance Claude — reprendre immédiatement sans questions superflues

---

## 0. CONTEXTE UTILISATEUR

**Jérémy Gourlain** — Le Havre, France. Développeur solo.
- BTS MUC (commerce/management) + TFIC chimie industrielle
- Culture geek profonde : DBZ, EVA, Gundam, SAO Alicization, Gunnm, HxH...
- Collection physique : figurines Gundam + Megami Device → source de poses OpenPose
- **Deadline absolue : Japan Expo 9-12 juillet 2026** — Contact JF/Sandrine (SEFA)
- Objectif démo : 2 minutes anime EVA qualité studio sur tablette
- Objectif long terme : film 24 minutes → Khara (Noisy-le-Grand)

**Style de collaboration :**
- Valide rapidement, passe à l'action
- Patches via patcher.py FORMAT A UNIQUEMENT — regrouper en un seul bundle
- Fonctionnement "dream mode" la nuit (pipeline autonome)
- Toujours "Ov3rLoRd" (jamais "OverLord")
- Je suis l'Architecte en chef — force de proposition, oeil critique
- Toujours py -3.12 (jamais python ou py seul)

---

## 1. ARCHITECTURE V2.21

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

PHASE 2.5 — Quality Control
  maestro.py::block_quality_control()
    → clip_validator.py     [cohérence CLIP cosinus inter-shots]
    → visual_validator.py   [QwenVL par rôle : asuka/rei/background/fx/anatomy]
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
ControlNet: OpenPoseXL2.safetensors | strength=0.85 | end_percent=0.85
            aussi disponible : control-lora-openposXL2-rank256.safetensors
ComfyUI   : D:\Ov3rLoRd AI\ComfyUI\ port 8188 — version 0.25.0
Checkpoint: fabricatedXL_v70.safetensors (NE JAMAIS MODIFIER)
LoRAs EVA : asuka-langley-soryuu-classic-ponyxl-lora-nochekaiser.safetensors (CORRECT)
            mari-makinami-rebuild-ponyxl-lora-nochekaiser.safetensors
            rei-ayanami-classic-ponyxl-lora-nochekaiser.safetensors
```

### 1.3 Racine et chemins
```
D:\OVERLORD\                    ← racine projet
D:\OVERLORD\agents\             ← tous les agents Python
D:\OVERLORD\workspace\          ← outputs, logs, archive, audit
D:\OVERLORD\workspace\poses\    ← skeletons OpenPose (NEW V2.21)
  asuka_skeleton.png            ← pose figurine Asuka plugsuit+hoodie (validée)
  openpose_placeholder.png      ← copie dans ComfyUI\input\ aussi
D:\OVERLORD\workspace\reports\  ← rapports CLIP + pacing
D:\OVERLORD\workspace\inpaint\  ← masks + outputs inpaint
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

:: Run avec ControlNet OpenPose
run.bat --media-type anime --universe "evangelion battle asuka" --no-qc --pose "workspace\poses\asuka_skeleton.png"

:: Générer skeleton depuis image de référence (figurine, screenshot...)
py -3.12 agents\pose_generator.py --image ma_ref.png --output workspace\poses\ma_pose.png

:: Enregistrer pose dans la bibliothèque
py -3.12 agents\pose_library.py --add workspace\poses\ma_pose.png --character asuka --shot-type standing --action combat

:: Lister la bibliothèque de poses
py -3.12 agents\pose_library.py --list

:: Git workflow
git add .
git commit -m "V2.21 — description"
git push

:: Reset checkpoint avant run frais
rmdir /s /q "workspace\checkpoints\anime_evangelion_battle_asuka"

:: Vérifier ComfyUI
curl http://127.0.0.1:8188/system_stats

:: Vérifier le bus
py -3.12 -c "from agents.context_bus import get_bus; bus = get_bus(); print('universe:', bus.read('director.universe')); print('lora:', bus.read('style.anchor_lora'))"

:: Dépendances Python 3.12
py -3.12 -m pip install requests pillow open_clip_torch pytrends feedparser
```

---

## 2. ÉTAT DES AGENTS — V2.21

### 2.1 Agents actifs

| Agent | Version | Statut | Rôle |
|-------|---------|--------|------|
| `prompt_translator.py` | V1.1 | OK | Narratif → JSON intent + negative_bank |
| `character_sheet_generator.py` | V1.2 | OK | 9 poses + LoRa Asuka classic |
| `style_dna_generator.py` | V1.0 | OK | Style DNA par preset |
| `audit_logger.py` | V1.0 | OK | SQLite WAL audit |
| `clip_validator.py` | V1.0 | OK | Cosinus CLIP inter-shots |
| `negative_bank.py` | V1.0 | OK | Banque négatifs contextuels |
| `inpaint_queue.py` | V1.0 | OK | Queue inpaint auto sur REJECT |
| `pacing_engine.py` | V1.0 | OK | Manifeste timing par shot |
| `visual_validator.py` | V1.0 | OK | QwenVL validation par rôle |
| `pose_generator.py` | V1.0 | OK | Génère skeleton DWPose depuis image |
| `pose_library.py` | V1.0 | OK | Bibliothèque poses par character/shot_type |

### 2.2 Patches appliqués session 23/06/2026

| Fichier | Changement |
|---------|------------|
| `maestro.py` | QC block + --no-qc + --pose CLI + quality_gate fix |
| `agent_supervisor_v2.py` | negative_bank + ControlNet OpenPose (nodes 500/501/502/503) |
| `postprod.py` | Lecture pacing manifest |
| `storyboard.py` | bus raw_shots + universe/character/openpose_path propagation + fallback EVA tags |
| `prompt_translator.py` | negative_bank contextuel + universe propagé |
| `scenario.py` | UNIVERSE_SYSTEM_CONSTRAINTS (contrainte dure EVA) + universe propagé |
| `style_continuity.py` | UNIVERSE_LORA_MAP + forçage LoRa depuis bus |
| `director.py` | Publication director.universe sur bus (10 clés) |
| `overlord_utils_utf8.py` | Fix Python 3.12 isatty/fileno argparse |
| `gpu_optimizer.py` | Steps 80→35, VAE sdxl→taesdxl |

### 2.3 Fichiers à la racine (PAS dans agents/)
```
maestro.py              ← chef d'orchestre
agent_supervisor_v2.py  ← AUSSI copié dans agents/
patcher.py              ← outil de patch
run.bat                 ← launcher (C:\Users\Ov3rL0rD\AppData\Local\Programs\Python\Python312\python.exe)
overlord_utils.py
overlord_utils_utf8.py
pose_generator.py       ← aussi dans agents/
pose_library.py         ← aussi dans agents/
```

---

## 3. RÉSULTATS VISUELS VALIDÉS

```
Session 23/06/2026 :
  Run 8/8 succès ComfyUI — LoRa Asuka forcée sur tous les jobs
  Ollama/mistral opérationnel — scenario score 78/100
  Storyboard 8 shots LLM (plus de fallback)
  ControlNet OpenPose actif (strength=0.85) — test en cours
  Watchdog actif — 2 FAIL luminosité (zones sombres normales)

Qualité confirmée :
  Image 7 : Asuka orange hair + blue eyes + twin tails + over-shoulder ✅✅
  Image 4 : EVA-01 derrière pilote, composition dramatique ✅✅
  Durée run : ~480s (8 images × ~30s/image ComfyUI + pipeline)

Pose OpenPose :
  asuka_skeleton.png généré depuis figurine plugsuit+hoodie
  ControlNet actif sur run en cours (résultat en attente)
```

---

## 4. BUGS ACTIFS

| Bug | Impact | Statut |
|-----|--------|--------|
| ValueError: I/O operation on closed file (logging) | Cosmétique | Post Japan Expo |
| ControlNet strength 0.85 peut-être trop faible | Moyen | À tester (essayer 1.0-1.2) |
| Watchdog scans anciennes archives → vidéo 700+ images | Moyen | Nettoyer workspace\archive avant run |
| sdxl_vae.safetensors tronqué | Faible | taesdxl actif |
| Reddit HTTP 403 (API sans auth) | Faible | Sourcing RSS fonctionne |

---

## 5. RÈGLES NON NÉGOCIABLES

```
1. Fichiers Python livrés via create_file tool + ast.parse() validé
2. Patches via patcher.py FORMAT A UNIQUEMENT — un seul bundle groupé
3. Toujours py -3.12 (jamais python ou py seul)
4. Combined_V35_API.json supprimé — NE PAS recréer
5. Steps RTX 5080 = 35. VAE = taesdxl. ControlNet = OpenPoseXL2.safetensors
6. "Ov3rLoRd" dans tous les banners
7. maestro.py à la RACINE
8. agent_supervisor_v2.py aux DEUX endroits (racine + agents/)
9. pose_generator.py et pose_library.py aux DEUX endroits aussi
10. Après chaque session : git add . && git commit -m "..." && git push
11. Nettoyer workspace\archive avant run de test (évite vidéos 700+ images)
12. openpose_placeholder.png doit exister dans ComfyUI\input\
```

---

## 6. ROADMAP

### P1 — Avant Japan Expo (J-16)
| # | Tâche | Statut |
|---|-------|--------|
| 1 | Calibrer strength ControlNet (0.85 → 1.0 → 1.2) | En cours |
| 2 | Bibliothèque poses : scanner figurines Gundam + Megami Device | À faire |
| 3 | Extraire frames EVA/Gundam officiels → DWPose → bibliothèque | À faire |
| 4 | Test run complet avec QC activé (sans --no-qc) | À faire |
| 5 | Démo 2 minutes EVA style assemblée | Objectif final |

### P2 — Post Japan Expo
- LoRa Asuka custom sur Kohya
- inpaint_queue V1.1 : remplacer frame originale si CLIP améliore
- EDL pour DaVinci Resolve / ProRes export
- youtube_publisher.py
- Fix ValueError logging Python 3.12
- control-lora-openposXL2-rank256 vs OpenPoseXL2 : benchmark

---

*Ov3rLoRd V2.21 — Onibaku Gumi 鬼爆組*
*"La connaissance est binaire, pas incertaine."*
*Japan Expo 2026. 🔥*

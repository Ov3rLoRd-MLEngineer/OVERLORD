# CONTEXTE_OVERLORD.md
## Cerveau de démarrage — Pipeline IA Anime Ov3rLoRd V2.20
### Studio Ov3rLoRd
**Généré le : 23 juin 2026 — Session de passation**
**Auteur :** Claude Sonnet 4.6 (instance précédente)
**Destinataire :** Nouvelle instance Claude — reprendre immédiatement sans questions superflues

---

## 0. CONTEXTE UTILISATEUR

**Jérémy Gourlain** — Le Havre, France. Développeur solo.
- BTS MUC (commerce/management) + TFIC chimie industrielle
- Culture geek profonde : DBZ, EVA, Gundam, SAO Alicization, Gunnm, HxH...
- **Deadline absolue : Japan Expo 9-12 juillet 2026** — Contact JF/Sandrine (SEFA)
- Objectif démo : 2 minutes anime EVA qualité studio sur tablette
- Objectif long terme : film 24 minutes → Khara (Noisy-le-Grand)

**Style de collaboration :**
- Valide rapidement, passe à l'action
- Patches via patcher.py FORMAT A ou B UNIQUEMENT
- Fonctionnement "dream mode" la nuit (pipeline autonome)
- Toujours appeler "Ov3rLoRd" (jamais "OverLord")
- Je suis l'Architecte en chef — force de proposition, oeil critique
- Toujours regrouper les patches en un seul bundle quand possible

---

## 1. ARCHITECTURE V2.20

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

PHASE 2.5 — Quality Control (V2.20)
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
Steps     : 35 (validé Jérémy — PAS 80)
CFG       : 7.0
Sampler   : dpmpp_2m_sde / karras
VAE       : taesdxl (sdxl_vae.safetensors tronqué ~15MB manquants)
Résolution: 1344×1984
ControlNet: weight 1.50 (validé)
ComfyUI   : D:\Ov3rLoRd AI\ComfyUI\ port 8188 — version 0.25.0
Checkpoint: fabricatedXL_v70.safetensors (NE JAMAIS MODIFIER)
LoRAs EVA : asuka-langley-soryuu-classic-ponyxl-lora-nochekaiser.safetensors (CORRECT)
            mari-makinami-rebuild-ponyxl-lora-nochekaiser.safetensors
            rei-ayanami-classic-ponyxl-lora-nochekaiser.safetensors
```

### 1.3 Racine et chemins
```
D:\OVERLORD\              ← racine projet (aussi sur GitHub)
D:\OVERLORD\agents\       ← tous les agents Python
D:\OVERLORD\workspace\    ← outputs, logs, archive, audit, characters, style
D:\OVERLORD\workspace\reports\  ← rapports CLIP + pacing manifestes
D:\OVERLORD\workspace\inpaint\  ← masks + outputs inpaint
D:\Ov3rLoRd AI\ComfyUI\  ← ComfyUI (espaces dans le chemin → raw strings)
Python 3.12.10 (py -3.12) ← VERSION A UTILISER (3.14 incompatible argparse)
Python 3.14 installé mais NE PAS UTILISER pour maestro.py
Ollama port 11434 | modèle : mistral
GitHub : https://github.com/g915tlk-design/OVERLORD.git
```

### 1.4 Commandes essentielles
```batch
:: Run pipeline
run.bat --media-type anime --universe "evangelion battle asuka" --no-qc
run.bat --media-type anime --universe "evangelion battle asuka"
run.bat --bible --media-type anime --universe "evangelion battle asuka"

:: Toujours utiliser py -3.12 pour tout
py -3.12 patcher.py patch_bundle.txt
py -3.12 maestro.py --media-type anime --universe "evangelion battle asuka"

:: Git workflow
git add .
git commit -m "V2.20 — description du changement"
git push

:: Vérifier ComfyUI
curl http://127.0.0.1:8188/system_stats

:: Vérifier le bus après un run
py -3.12 -c "from agents.context_bus import get_bus; bus = get_bus(); print('universe:', bus.read('director.universe')); print('lora:', bus.read('style.anchor_lora'))"

:: Reset checkpoint avant run frais
rmdir /s /q "workspace\checkpoints\anime_evangelion_battle_asuka"

:: Installer dépendances Python 3.12
py -3.12 -m pip install requests pillow open_clip_torch pytrends feedparser
```

---

## 2. ÉTAT DES AGENTS — V2.20

### 2.1 Agents livrés et validés

| Agent | Version | Statut | Rôle |
|-------|---------|--------|------|
| `prompt_translator.py` | V1.1 | OK Patché | Narratif → JSON intent + negative_bank |
| `character_sheet_generator.py` | V1.2 | OK Patché | 9 poses + LoRa Asuka classic corrigée |
| `style_dna_generator.py` | V1.0 | OK | Style DNA par preset |
| `audit_logger.py` | V1.0 | OK | SQLite WAL audit |
| `clip_validator.py` | V1.0 | OK Livré | Cosinus CLIP inter-shots |
| `negative_bank.py` | V1.0 | OK Livré | Banque négatifs contextuels |
| `inpaint_queue.py` | V1.0 | OK Livré | Queue inpaint auto sur REJECT |
| `pacing_engine.py` | V1.0 | OK Livré | Manifeste timing par shot |
| `visual_validator.py` | V1.0 | OK Livré | QwenVL validation par rôle |

### 2.2 Patches appliqués cette session

| Fichier | Changement |
|---------|------------|
| `maestro.py` | QC block + --no-qc + bus raw_shots + quality_gate fix |
| `agent_supervisor_v2.py` | negative_bank intégré dans patch_workflow |
| `postprod.py` | Lecture pacing manifest pour durées shots |
| `storyboard.py` | Publication raw_shots sur bus + universe/character propagation |
| `prompt_translator.py` | negative_bank contextuel + universe propagé |
| `scenario.py` | universe propagé dans script final |
| `style_continuity.py` | UNIVERSE_LORA_MAP + forçage LoRa depuis bus dans apply_continuity |
| `director.py` | Publication director.universe sur le bus (10 clés) |
| `overlord_utils_utf8.py` | Fix Python 3.12 isatty/fileno argparse |
| `gpu_optimizer.py` | Steps 80→35, VAE sdxl→taesdxl |

### 2.3 Fichiers à la racine (pas dans agents/)
```
maestro.py              ← chef d'orchestre principal
agent_supervisor_v2.py  ← aussi copié dans agents/ pour les imports
patcher.py              ← outil de patch
run.bat                 ← launcher py -3.12
overlord_utils.py       ← utils racine
overlord_utils_utf8.py  ← fix UTF-8
reset_total.py
```

---

## 3. RÉSULTATS VISUELS VALIDÉS

```
Session 23/06/2026 — Premier run complet avec ComfyUI :
  job0000 : personnage générique (LoRa mari — à corriger)
  job0001 : portrait féminin urbain (LoRa mari — à corriger)
  job0005 : Asuka orange hair + blue eyes + twin tails OK
  job0007 : Asuka plugsuit EVA-02 + EVA-01 derrière + FX OK OK OK
             → Qualité studio — niveau Japan Expo confirmé

Pipeline complet validé :
  sourcing → scenario → storyboard → production (ComfyUI) → postprod → MP4
  Durée run : ~27 secondes hors génération ComfyUI
  343 images assemblées en vidéo workspace\exports\
```

---

## 4. BUGS ACTIFS

| Bug | Impact | Statut |
|-----|--------|--------|
| director.universe non publié sur bus → LoRa random | Haut | Patch livré, à tester |
| ValueError: I/O operation on closed file logging | Cosmétique | Post Japan Expo |
| LoRa mari-makinami sur jobs 0-1 | Moyen | Fix en cours |
| sdxl_vae.safetensors tronqué | Faible | taesdxl actif |
| Steps GPU preset = 80 dans config (gpu_optimizer l'écrase à 35) | Faible | OK en pratique |

---

## 5. RÈGLES NON NÉGOCIABLES

```
1. Tout fichier livré via create_file tool
2. Validation ast.parse() AVANT toute livraison Python
3. Patches via patcher.py FORMAT A UNIQUEMENT
4. Regrouper les patches en un seul bundle quand plusieurs fichiers
5. Toujours py -3.12 (jamais python ou py seul)
6. Combined_V35_API.json supprimé — NE PAS recréer
7. Steps RTX 5080 = 35. ControlNet = 1.50. VAE = taesdxl
8. "Ov3rLoRd" dans tous les banners
9. maestro.py est à la RACINE (pas dans agents/)
10. agent_supervisor_v2.py est aux DEUX endroits (racine + agents/)
11. GitHub : git add . && git commit -m "message" && git push après chaque session
```

---

## 6. ROADMAP

### P1 — Avant Japan Expo (J-16)
| # | Tâche | Statut |
|---|-------|--------|
| 1 | Tester patch director_universe → LoRa Asuka forcée | En cours |
| 2 | ControlNet + OpenPose dans fallback workflow supervisor | A faire |
| 3 | Test run complet avec QC activé (sans --no-qc) | A faire |
| 4 | Démo 2 minutes EVA style | Objectif final |

### P2 — Post Japan Expo
- LoRa Asuka custom sur Kohya
- inpaint_queue V1.1 : remplacer frame originale si CLIP améliore
- EDL pour DaVinci Resolve
- youtube_publisher.py
- Fix ValueError logging Python 3.12

---

*Ov3rLoRd V2.20*
*"La connaissance est binaire, pas incertaine."*
*Japan Expo 2026.. 🔥*

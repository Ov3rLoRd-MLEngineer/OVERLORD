# CONTEXTE_OVERLORD.md
## Cerveau de démarrage — Pipeline IA Anime Ov3rLoRd V2.20
### Studio Onibaku Gumi 鬼爆組
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
- Préfère scripts directs aux patches quand FIND est incertain
- Fonctionnement "dream mode" la nuit (pipeline autonome)
- Toujours appeler **"Ov3rLoRd"** (jamais "OverLord")
- Je suis l'Architecte en chef — force de proposition, œil critique

---

## 1. ARCHITECTURE V2.20

### 1.1 Phases
```
PHASE 0 — Run 0 : Bible Visuelle (UNE FOIS par projet)
  character_sheet_generator.py → 9 poses/expressions par personnage
  style_dna_generator.py       → image référence style pur

PHASE 1 — Sourcing → Scénario → Storyboard
  sourcing.py → scenario.py → storyboard.py
  [storyboard.py V1.49s+patch] appelle prompt_translator.py en fin de run_storyboard()

PHASE 2 — Production
  maestro.py → agent_supervisor_v2.py → ComfyUI API port 8188

PHASE 2.5 — Quality Control (NEW V2.20)
  maestro.py::block_quality_control()
    → clip_validator.py     [cohérence CLIP cosinus inter-shots]
    → inpaint_queue.py      [inpaint auto frames REJECT]
    → pacing_engine.py      [manifeste timing pour postprod]

PHASE 3 — Post-production
  postprod.py → transition_builder.py → audio_compositor.py
  [postprod lit pacing_{run_id}.json pour les durées]
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
ComfyUI   : D:\Ov3rLoRd AI\ComfyUI\ port 8188
Checkpoint: fabricatedXL_v70.safetensors (NE JAMAIS MODIFIER)
LoRAs EVA : asuka-langley-soryuu-classic-ponyxl-lora-nochekaiser.safetensors
            mari-makinami-rebuild-ponyxl-lora-nochekaiser.safetensors
            rei-ayanami-classic-ponyxl-lora-nochekaiser.safetensors
```

### 1.3 Racine et chemins
```
D:\OVERLORD\              ← racine projet
D:\OVERLORD\agents\       ← tous les agents Python
D:\OVERLORD\workspace\    ← outputs, logs, archive, audit, characters, style
D:\OVERLORD\workspace\reports\  ← rapports CLIP + pacing manifestes (NEW)
D:\OVERLORD\workspace\inpaint\  ← masks + outputs inpaint (NEW)
D:\Ov3rLoRd AI\ComfyUI\  ← ComfyUI (espaces dans le chemin → raw strings)
Python 3.14 système
Ollama port 11434 | modèle : mistral
```

---

## 2. ÉTAT DES AGENTS — V2.20

### 2.1 Agents livrés session V2.10 (inchangés)

| Agent | Version | Statut | Rôle |
|-------|---------|--------|------|
| `prompt_translator.py` | V1.1 | ✅ Testé | Narratif → JSON intent + Pacing Engine |
| `character_sheet_generator.py` | V1.2 | ✅ Testé | 9 poses + mode --production |
| `style_dna_generator.py` | V1.0 | ✅ Déployé | Style DNA par preset |
| `audit_logger.py` | V1.0 | ✅ Déployé | SQLite WAL audit |

### 2.2 Nouveaux agents session V2.20

| Agent | Version | Statut | Rôle |
|-------|---------|--------|------|
| `clip_validator.py` | V1.0 | ✅ Livré | Cohérence cosinus CLIP inter-shots + fallback hash perceptuel |
| `negative_bank.py` | V1.0 | ✅ Livré | Banque négatifs par personnage / univers / shot_type / lighting |
| `inpaint_queue.py` | V1.0 | ✅ Livré | Queue inpaint auto sur frames REJECT (masque diff pixel + ComfyUI) |
| `pacing_engine.py` | V1.0 | ✅ Livré | Manifeste timing optimal par shot (durée + transitions) |

### 2.3 Patches session V2.20

| Fichier | Changements |
|---------|------------|
| `maestro.py` | + block_quality_control() [CLIP → inpaint → pacing] + flag --no-qc |
| Via `maestro_patch_v220.py` | Script de patch autonome avec backup + AST validation |

### 2.4 Fichiers supprimés (hérité V2.10)
- `Combined_V35_API.json` — supprimé par Jérémy (remplacé par workflow fallback dans supervisor)

---

## 3. RÉSULTATS VISUELS VALIDÉS (hérité V2.10)

```
workspace/characters/
  asuka_face.png           ✅ Qualité studio
  asuka_profile_left.png   ✅ OK
  asuka_back.png           ✅ OK
  [+ 6 autres poses V1.2]

workspace/style/
  style_dna_20260623_032618.png ✅ Style EVA sombre validé

Problème connu (mineur) :
  - LoRa mari-makinami tire vers Rebuild plutôt que classic
  → À traiter après Japan Expo
```

---

## 4. FLUX DE DONNÉES V2.20

```
maestro.py --bible
  → block_bible_visuelle()
      → character_sheet_generator
      → style_dna_generator
  → block_sourcing()
  → block_scenario()
  → block_storyboard()
      → storyboard._last_storyboard sauvegardé dans self
      → prompt_translator.translate_storyboard()
  → block_production()
      → agent_supervisor_v2.run_batch_advanced()
          → fallback workflow minimal
          → negative_bank.get_negative() [par shot]    ← NEW V2.20
          → ComfyUI API /prompt
          → audit_logger.log_frame()
  → block_quality_control()    ← NEW V2.20
      → clip_validator.validate_run()
          → mode CLIP (open_clip ViT-B-32) ou hash perceptuel (fallback)
          → workspace/reports/clip_report_{run_id}.json
      → si REJECT : inpaint_queue.process_clip_rejects()
          → masque diff pixel auto
          → ComfyUI inpaint (denoise=0.65)
          → workspace/inpaint/outputs/
      → pacing_engine.build_manifest_from_storyboard()
          → workspace/reports/pacing_{run_id}.json
  → block_postprod()
      → transition_builder (lit pacing manifest)
      → audio_compositor
  → workspace/exports/{run_id}_final.mp4
```

---

## 5. INTÉGRATIONS ENTRE AGENTS (NEW V2.20)

```python
# negative_bank.py — importé par supervisor et translator
from negative_bank import get_negative
neg = get_negative(character="asuka_plugsuit", universe="evangelion",
                   shot_type="close_up", lighting="dramatic")

# pacing_engine.py — importé par storyboard et postprod
from pacing_engine import get_recommended_duration, build_manifest_from_storyboard
dur = get_recommended_duration("close_up", "static", "emotional", "evangelion")

# clip_validator.py — appelé par maestro block_quality_control
from clip_validator import validate_run
report = validate_run(run_id)   # → dict {status, stats, pairs, rejects, warnings}

# inpaint_queue.py — appelé si clip report contient des REJECT
from inpaint_queue import process_clip_rejects
results = process_clip_rejects(run_id, clip_report, universe="evangelion")
```

---

## 6. ROADMAP — CE QUI RESTE À FAIRE

### P1 — Avant Japan Expo (J-16)
| # | Tâche | Notes |
|---|-------|-------|
| 1 | Appliquer `maestro_patch_v220.py` sur machine prod | `python maestro_patch_v220.py` |
| 2 | Copier 4 nouveaux agents dans `D:\OVERLORD\agents\` | clip_validator, negative_bank, inpaint_queue, pacing_engine |
| 3 | Intégrer `negative_bank` dans `agent_supervisor_v2.py` | Remplacer hardcoded negative par get_negative() |
| 4 | Test run complet V2.20 | Vérifier QC block dans les logs |
| 5 | Changer LoRa Asuka → classic dans character_sheet_generator | mineur |

### P2 — V2.X post-Japan Expo
| Agent | Rôle |
|-------|------|
| `postprod_v2.py` | Lire pacing manifest pour durées shots |
| `transition_builder_v2.py` | Utiliser transition_in/out du manifest |
| `audio_compositor_v2.py` | Sync audio sur pacing manifest |
| `youtube_publisher.py` | Export + upload automatique |
| `negative_bank_trainer.py` | Apprentissage auto depuis rejets CLIP |

### P3 — Post Japan Expo
- ProRes/DNxHR export master
- EDL pour DaVinci Resolve
- LoRa Asuka entraînée sur Kohya
- `inpaint_queue` V1.1 : remplacer frame originale si CLIP score améliore

---

## 7. RÈGLES NON NÉGOCIABLES

```
1. Tout fichier livré via create_file tool — JAMAIS bash redirection pour livraison
2. Validation syntaxe ast.parse() AVANT toute livraison Python
3. Tous les imports LLM wrappés en try/except avec fallback
4. _get_api_key() dans tout fichier appelant l'API Anthropic
5. Chemins Windows avec espaces → raw strings r"D:\Ov3rLoRd AI\..."
6. Toujours appeler le projet "Ov3rLoRd" dans les banners/titres
7. Combined_V35_API.json supprimé — NE PAS recréer, utiliser fallback supervisor
8. Steps RTX 5080 = 35 (PAS 80). ControlNet weight = 1.50. VAE = taesdxl
9. Patcher.py V1.1 : FORMAT A (find/replace) | FORMAT B (create/update bundles)
10. Scripts de fix directs (regex) préférés au patcher quand FIND incertain
11. (NEW) negative_bank doit être importé avec fallback dans tous les agents qui génèrent
12. (NEW) pacing manifest est LA source de vérité pour les durées en postprod
13. (NEW) CLIP seuils : WARNING=0.70 / REJECT=0.50 (modifiables via --thresholds)
14. (NEW) inpaint denoise=0.65 (conservateur — ne pas monter, risque incohérence)
```

---

## 8. COMMANDES ESSENTIELLES

```batch
:: DÉPLOIEMENT V2.20 (faire en premier)
copy clip_validator.py D:\OVERLORD\agents\
copy negative_bank.py  D:\OVERLORD\agents\
copy inpaint_queue.py  D:\OVERLORD\agents\
copy pacing_engine.py  D:\OVERLORD\agents\
python maestro_patch_v220.py

:: Run complet V2.20 avec Bible Visuelle
python agents\maestro.py --media-type anime --universe "evangelion battle asuka" --bible

:: Run sans QC (mode rapide test)
python agents\maestro.py --media-type anime --universe "evangelion battle asuka" --no-qc

:: CLIP Validator standalone
python agents\clip_validator.py --run-id RUN_ID

:: Negative Bank — test
python agents\negative_bank.py --character asuka_plugsuit --universe evangelion --shot-type close_up --lighting dramatic

:: Negative Bank — liste clés
python agents\negative_bank.py --list

:: Inpaint Queue — depuis rapport CLIP
python agents\inpaint_queue.py --run-id RUN_ID --clip-report workspace\reports\clip_report_RUN_ID.json

:: Inpaint Queue — frame unique
python agents\inpaint_queue.py --run-id RUN_ID --frame workspace\outputs\RUN_ID\frame_001.png

:: Pacing Engine — demo EVA
python agents\pacing_engine.py --run-id RUN_ID --universe evangelion

:: Pacing Engine — shot unique
python agents\pacing_engine.py --run-id RUN_ID --shot-type close_up --movement static --intent emotional

:: Audit rapport run
python agents\audit_logger.py --report RUN_ID

:: Vérifier ComfyUI
curl http://127.0.0.1:8188/system_stats

:: Reset complet + run
python reset_total.py
python agents\maestro.py --media-type anime --universe "evangelion battle asuka"
```

---

## 9. BUGS PENDING

| Bug | Impact | Notes |
|-----|--------|-------|
| LoRa mari-makinami → style Rebuild (pas classic) | Faible | Après Japan Expo |
| `sdxl_vae.safetensors` tronqué | Faible | taesdxl fonctionne |
| Prompts storyboard génériques par moments | Moyen | prompt_translator V1.1 corrige partiellement |
| Bug stdout Python 3.14 | Faible | Cosmétique, non bloquant |
| open_clip non installé → fallback hash perceptuel | Moyen | `pip install open_clip_torch --break-system-packages` |

---

## 10. INSTALL DÉPENDANCES V2.20

```batch
:: CLIP (optionnel — fallback hash perceptuel si absent)
pip install open_clip_torch --break-system-packages

:: PIL (nécessaire pour inpaint masques)
pip install Pillow --break-system-packages

:: Requests (déjà présent normalement)
pip install requests --break-system-packages
```

---

*Ov3rLoRd V2.20 — Onibaku Gumi 鬼爆組*
*"La connaissance est binaire, pas incertaine."*
*Japan Expo 2026. 鬼爆組. 🔥*

# Rapport de session — 02 au 04 août 2026
*Onibaku Gumi / Ov3rLoRd — Jérémy Gourlain*
*Document de reprise pour nouvelle conversation Claude*

---

## Contexte projet (rappel)

Pipeline de production anime IA local (studio Onibaku Gumi, Rouen). Stack : ComfyUI, fabricatedXL_v70 SDXL, dual-GPU RTX 5080 + RTX 5060 Ti 16Go, Python 3.12, D:\OVERLORD\. Objectif : démo technique 30s+ d'anime cohérent pour candidature Mistral (profil "Forward Deployed ML Engineer") ou studio. Deadline flexible : fin août sécurité, septembre/octobre disponibles.

---

## Ce qui a été accompli cette session

### LLM local — QLoRA (terminé, en service)

**Stage 1 — The Stack v1 Python (73,2 Go, 35 504 fichiers)**
- Run : `stage1_thestack_full`, 4438 steps, 6h22m, train_loss 0.9626
- Correctif fragmentation VRAM CUDA validé durablement (`group_by_length` + cache clear/step)
- Adaptateur : `training_stage1/runs/stage1_thestack_full/adapter_stage1/`

**Stage 2 — CommitPack Python (150 000 exemples, 323 Mo)**
- Run : `stage2_commitpack_full`, 18750 steps, 23h12m, train_loss 1.1527
- Adaptateur : `workspace/qlora_dataset/training_stage2/runs/stage2_commitpack_full/adapter_stage2_commitpack`
- Données source : `E:\data\commitpack\` (223 Go JSONL, 4,6M commits Python filtrés → 150k retenus)

**Déploiement Ollama (RTX 5060 Ti)**
- Modèle fusionné + converti GGUF : `ov3rlord-coder-stage2v2` (fp16, 8,1 Go)
- Confirmé sur GPU cb196733 (5060 Ti), num_ctx=32768, ~46 tok/s
- Piège réglé : désactiver ollama app.exe Startup (conflits avec launch_ollama.bat)
- VS Build Tools + CUDA toolkit installés (pour future quantisation Q4_K_M)

**Évaluation (Claude Opus via claude.ai + éval_verdict.txt)**
- `ov3rlord-coder-stage2v2` : Style 4.25/5, Factuel 2.38/5 — confabulation convaincante
- `qwen2.5-coder:14b` : Style 1.50/5, Factuel 3.00/5 — honnête mais aveugle au projet
- `stage2_commitpack` : Style 2.50/5, Factuel 0.63/5 — mode collapse diff, inutilisable tel quel
- **Décision confirmée** : RAG obligatoire pour le factuel, fine-tuning uniquement pour le style
- **Pistes anti-hallucination documentées** : R-Tuning Stage 3, Mask-DPO, RAGognizer, AutoRAG-LoRA

### RAG sémantique (en service)

- `agents/infra/rag_indexer.py` : 307 chunks (269 + CLAUDE-english.md), multilingual-e5-small
- `agents/infra/rag_query.py` : hybride BM25 + sémantique (fusion RRF)
- Intégration `agents/creative/llm_router.py` : injection RAG avant chaque appel LLM
- Limite connue : questions EN sur passages FR (angle mort partiel sur `dpmpp_2m`)
- **À faire** : augmenter à 500+ chunks (arborescence projet, ADRs, LIMITATIONS_CONNUES.md)

### Infrastructure code (commits en service)

- Réorg `agents/*.py` Phase C : 153 modules → 10 sous-dossiers + shims `runpy.run_path`
- 16/16 PASS `test_pipeline.py --quick` confirmé
- Collision `agents/core.py` / `agents/core/` résolue → `agents/core_legacy.py`
- `CLAUDE-english.md` créé + intégré au RAG
- `workspace/scripts/devstral_agent.py` : wrapper CLI anti-bug backticks Aider
- `workspace/qlora_dataset/evaluate_commitpack.py` : script éval 3 modèles prêt
- `workspace/scripts/aider_devstral.bat` : profil Aider devstral:24b (num_ctx=16384)
- Devstral:24b : bug backticks Aider documenté, wrapper Python fonctionnel en alternative
- `HANDOFF_2026-08-03.md` : handoff complet

### Pipeline AniSora V3.2 (validé, en cours d'amélioration)

**Installations ComfyUI**
- ComfyUI-GGUF (city96) installé
- AniSora V3.2 GGUF : High Q4_0 (9 Go) + Low Q4_K_M (10,1 Go) + text encoder
- VAE : wan_2.1_vae.safetensors (correcte pour l'architecture 14B)

**Tests réalisés**
1. Smoke test I2V simple : 93s, VRAM 13 Go, aucun artefact ✅
2. running.fbx → AniSora I2V (sans ancrage stylisé) : 175s, VRAM 10,2 Go, 37 frames, style 3D conservé (pas de stylisation anime) → cause comprise : l'image d'ancrage pilote le style, pas le prompt
3. `mask_test__00001_.png` (Asuka anime SDXL) comme ancrage : 37 frames, 182s, VRAM 9 Go, **style anime maintenu et stable** ✅ drift minimal, pieds cohérents, quelques flous de doigts

**Diagnostic clé : c'est l'image d'ancrage qui pilote le style en I2V, pas le prompt texte**

**Frames disponibles**
- `D:\OVERLORD\DEMO\frames\mixamo_raw\` : 0001.png → 0038.png (38 frames, cycle complet bouclable)
- `D:\OVERLORD\DEMO\frames\mixamo_depth\` : depth maps DepthAnythingV2 (38/38)
- `D:\OVERLORD\DEMO\frames\mixamo_pose\` : DWPose (38/38)
- Contrainte : cycle 0001→0038 doit rester intact pour la bouclabilité
- Contrainte VAE 4k+1 : AniSora génère 37 frames (pas 38). Solution : générer 41 frames et couper, ou adapter le cycle source

**Outputs AniSora**
- `D:\Ov3rLoRd AI\ComfyUI\output\Anisora Test\` (à créer avec sous-dossiers)
- Meilleur résultat actuel : test ancrage stylisé SDXL (commit e16d3b0)

### Recherches documentées dans DOCS/MD/

1. `Pipeline de production anime IA local en 2026.md` — état de l'art complet AniSora/WAN 2.2/Blender/RIFE/SeedVR2
2. `Dépasser la limite de cohérence temporelle.md` — SVI 2.0 Pro, VACE, ColorMatch, R&D arXiv
3. `PLAN_COHERENCE_TEMPORELLE_AOUT2026.md` — plan d'action actionnable (ce fichier)
4. `TEST_ANISORA_V32_SMOKE.md` — résultats tests AniSora
5. `COMPARAISON_ANIMATEDIFF_VS_ANISORA.md` — à compléter (tâche en cours)
6. `DATASETS_GEEK_UNIVERS_FF_SAO_HACK_HXH.md` — ressources assets 3D pour démo future

---

## Décisions architecturales prises

### Pipeline vidéo cible

```
Keyframe SDXL (fabricatedXL + LoRA style)
        ↓
AniSora V3.2 I2V + SVI LoRA HIGH+LOW (anti-drift)
        ↓ ColorMatch LAB inter-clips
[N clips de 37 frames enchaînés]
        ↓
Assemblage ffmpeg
        ↓
RIFE rife49 / GMFSS Fortuna
        ↓
SeedVR2 7B upscale
```

### AnimateDiff vs AniSora
- AnimateDiff : bonne cohérence courte distance (16 frames), drift couleur présent, résultats visuellement acceptables dans `animatediff_cn_test`
- AniSora : meilleure qualité, dépend de l'ancrage pour le style
- Les deux sont complémentaires : AniSora pour la génération principale, AnimateDiff exploitable en passes de correction

### Assets 3D pour démo finale (ordre de priorité)
1. **DBZ FighterZ** (Models Resource, FBX direct) → Goku vs Vegeta — cel-shading natif, priorité démo
2. Xenoverse 2 (même source, style plus 3D)
3. SAO Alicization Lycoris (Umodel UE4, Kirito/Alice, démo longue)
4. FF14 / Miqo'te (TexTools, réinstall nécessaire)
5. Miku dancing rig (Workshop Steam ID 2020615767, SteamCMD)
- Ordre : valider pipeline avec `running.fbx` + AniSora d'abord, puis DBZ FighterZ

### Modèles Ollama disponibles (RTX 5060 Ti)
- `qwen2.5-coder:14b-instruct-q4_K_M` — daily driver Aider
- `devstral:24b` — agentic coding (via wrapper Python, bug Aider backticks)
- `ov3rlord-coder-stage2v2` — style/conventions projet + RAG
- `qwen3-coder:30b-a3b-q4_K_M` — trop gros pour 5060 Ti seule (tensor split possible)
- `qwen2.5vl:7b` — vision (analyse screenshots ComfyUI)

---

## Ce qui est en cours / à faire (prochaine session)

### Tâche immédiate — Brief `BRIEF_SESSION_PIPELINE_04082026.md`

1. **AnimateDiff 32 frames** (5060 Ti) — test cohérence étendue + extraction frames
2. **SeedVR2 upscale** (5080) — upscaler meilleure séquence AniSora → 960x1440
3. **SVI 2.0 Pro installation et test** (5080) — LoRA anti-drift WAN 2.2, test 2 clips consécutifs
4. **RAG coverage augmentation** (CPU) — 307→500+ chunks, system prompt "cite ou refuse"
5. **CLAUDE.md** — nouvelles conventions (DepthAnythingV2, SVI, ColorMatch, parallélisation GPU)

### Chantiers en pause (non abandonnés)

- **Control-LoRA FootSegNet** : mode collapse, piste CtrLoRA à tester
- **QC anatomique** : bloqué licences, piste arXiv 2312.04236
- **186 masques FootSegNet fragmentés** : annotation manuelle 3-4h (toi seul, pas de Claude Code)
- **105 images HandSegNet legacy** : vérifier doublon avec critère fragmentation
- **Branche aider-experiments** : non mergée, contient route_by_sam_confidence.py
- **Ko-fi/GitHub Sponsors** : liens absents des README FootSegNet
- **R-Tuning Stage 3** : dataset refus calibrés, ~200-500 exemples, post-démo

### Candidatures cloud credits

- NVIDIA Inception (priorité 1)
- Nebius AI Lift
- Microsoft for Startups
- Fichiers : `cloud_credits_checklist.md` + `candidature_dossier.md` préparés, pas encore envoyés

---

## Commits de la session (résumé)

| Hash | Contenu |
|---|---|
| 7d17dea | Audit + corrections Stage 1 restauré + evaluate_stages_v4.py |
| 398e877 | Stage 2 relancé + éval V5 + handoff |
| 547ef15 | RAG sémantique (rag_indexer + rag_query) |
| 3eec7f9 | CLAUDE-english.md ajouté RAG (269→307 chunks) |
| 02dbc13 | Intégration RAG llm_router.py |
| 7a85dec | Réorg agents/ Phase C (316 fichiers, 16/16 PASS) |
| 72b8244 | Intégration RAG llm_router.call() |
| 86262a8 | CLAUDE-english.md dans RAG |
| 6cda792 | Profil Aider devstral:24b |
| fd42058 | PLAN_PIPELINE_A_DEMO_30S.md |
| 2910235 | Collision core.py/core/ résolue |
| d71ea26 | RAG_TEST_BILINGUE.md |
| a0b243b | devstral_agent.py |
| dec27be | evaluate_commitpack.py |
| 64be7e2 | Évaluation CommitPack (VERDICT_COMMITPACK.md) |
| c3257f4 | AniSora V3.2 GGUF installé |
| 6caad32 | Smoke test AniSora I2V |
| 091f72a | Test running.fbx → AniSora |
| e16d3b0 | Test AniSora ancrage stylisé SDXL ✅ |
| 5397b4b | Dataset CommitPack filtré (150k exemples) |
| f0881a5 | Stage 1 The Stack terminé |

---

## Points à vérifier en début de prochaine session

1. Lire `HANDOFF_2026-08-03.md` (handoff complet de session)
2. Vérifier `nvidia-smi` — les deux GPU libres
3. CommitPack sur G: — téléchargement terminé ? Si oui, copier Python + python-traceback vers `E:\data\commitpack\` (déjà fait selon session)
4. Startup ollama app.exe — désactivé ? (risque de conflit pinning GPU)
5. Pipeline A (`batch_controlnet.py`) abandonné au profit d'AniSora — ne pas relancer

---

## Informations pratiques

- Quota Claude : limité, économiser les interactions
- 5080 = génération/entraînement (CUDA_VISIBLE_DEVICES=0)
- 5060 Ti = inférence Ollama / ComfyUI secondaire (CUDA_VISIBLE_DEVICES=1)
- Écrans branchés sur 5060 Ti, pas sur 5080
- Règle 90%/92% contexte pour sessions longues Claude Code
- Toujours vérifier sur disque, jamais la sortie terminal
- Aider : toujours `PYTHONIOENCODING=utf-8` + `PYTHONUTF8=1`, vérifier via git log

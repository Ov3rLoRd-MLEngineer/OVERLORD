# ARCHITECTURE MULTI-AGENTS — Gantt / PERT / 5S
## Ov3rLoRd V2.x — Méthodologie de Production IA
*Mis à jour : 05/08/2026 — intègre sessions juin→août 2026*

---

## 1. CONTEXTE STRATÉGIQUE

**Objectif court terme :** Démo technique 30s+ d'anime cohérent — deadline fin août 2026 (ARE).
**Objectif pro :** Candidature Mistral (Forward Deployed ML Engineer).
**Objectif long terme :** Film anime 24 minutes (Gainax/Mappa tier).

**Infrastructure actuelle :**
- RTX 5080 (CUDA 0) : génération/entraînement/ComfyUI principal
- RTX 5060 Ti 16Go (CUDA 1) : Ollama / ComfyUI secondaire / inférence isolée
- D:\OVERLORD\ (dépôt git), E:\ (data/jeux/modèles), C:\ (système — en cours d'allègement)
- **RAM système 32 Go — GOULOT CONFIRMÉ (2026-08-06)** : voir section 4bis. Résolu dès upgrade 64 Go (kit en négociation).

**Principe directeur :** Pipeline previz 3D → stylisation anime IA. Un rendu Blender EEVEE pilote AniSora, pas l'inverse.

---

## 2. PIPELINE VIDÉO CIBLE (Workflow B — Priorité démo)

```
Script scène Python (Blender)
    → personnages riggés FBX/PMX + décor Poly Haven + caméra animée
    → rendu EEVEE (depth + DWPose + RGB) — RTX 5080, secondes/frame
            ↓
Keyframe SDXL stylisée (fabricatedXL_v70 + LoRA style)
            ↓
AniSora V3.2 I2V + SVI 2.0 Pro (HIGH+LOW) — anti-drift
    → clips de 37 frames
            ↓ ColorMatch LAB inter-clips (ColorMatchV2)
[N clips enchaînés — seed différent par clip]
            ↓
ComfyUI img2img (affinage/correction)        ← nouveau
            ↓
[AnimateDiff RETIRÉ — dégrade le résultat, artefacts dédoublement]
            ↓
ffmpeg minterpolate (interpolation — RIFE bloqué architecture)
            ↓
SeedVR2 7B (upscale 2x, block_swap=24, VAE tiling)
            ↓
Export final
```

**Workflow A (validé 05/08/2026) :** même chaîne sans previz Blender — keyframe SDXL directe sur pose DWPose. Opérationnel, utilisé pour les tests.

**Verdict AnimateDiff :** retiré de la chaîne principale. Comparaison directe 05/08 : dégradation nette (artefacts dédoublement de trait). Exploitable uniquement en passe de correction ciblée si besoin.

---

## 3. DIAGRAMME DE GANTT — Pipeline de Production

```
PHASE              AGENT/OUTIL                  T0   T1   T2   T3   T4   T5   T6   T7
──────────────────────────────────────────────────────────────────────────────────────
PREVIZ 3D          blender_scene.py             [==]
                   EEVEE render (depth/pose/RGB) [==]

KEYFRAME SDXL      ComfyUI (fabricatedXL+LoRA)       [=]

GÉNÉRATION VIDÉO   AniSora V3.2 I2V                      [====][====][====]
                   SVI 2.0 Pro HIGH+LOW                   [====][====][====]
                   ColorMatch LAB inter-clips                  [=]   [=]

AFFINAGE           ComfyUI img2img                                        [==]

POST-PROD          ffmpeg minterpolate                                         [=]
                   SeedVR2 7B upscale                                          [==]

CONTRÔLE           quality_reviewer (cible)     [----------------------------------]
                   watchdog (continu)            [====================================]

RAPPORT            session_reporter.py                                              [=]
──────────────────────────────────────────────────────────────────────────────────────
[===] = actif    [---] = en attente / cible non encore implémentée
T0-T7 = unités relatives (génération AniSora ~180s/clip RTX 5080)
```

**Parallélisation GPU :**
- RTX 5080 (CUDA 0) : AniSora/SVI/SeedVR2 — séquentiel obligatoire (chaque clip dépend du précédent)
- RTX 5060 Ti (CUDA 1) : Ollama inference / extraction DWPose / tâches CPU-légères
- Upscale SeedVR2 + extraction depth/pose Blender = parallélisable entre les deux GPU

---

## 4. DIAGRAMME PERT — Chemin Critique

```
        ┌──────────────────┐
        │  PREVIZ BLENDER  │ ~30s (EEVEE, script Python)
        └────────┬─────────┘
                 │
        ┌────────▼─────────┐      ┌──────────────────┐
        │  KEYFRAME SDXL   │ ~60s │  LoRA style      │ ~0s (déjà chargé)
        └────────┬─────────┘      └────────┬─────────┘
                 └──────────┬──────────────┘
                            │
        ┌───────────────────▼──────────────────┐
        │     AniSora V3.2 I2V + SVI LoRA      │ ~180s/clip ◄── GOULOT
        │     (37 frames, seed unique)          │
        └───────────────────┬──────────────────┘
                            │
                   ┌────────▼────────┐
                   │  ColorMatch LAB │ ~5s
                   └────────┬────────┘
                            │ [répéter N clips]
                   ┌────────▼────────┐
                   │ img2img affinage│ ~30s
                   └────────┬────────┘
                            │
                   ┌────────▼────────┐
                   │ ffmpeg + SeedVR2│ ~120s
                   └────────┬────────┘
                            │
                   ┌────────▼────────┐
                   │    EXPORT       │ ~5s
                   └─────────────────┘

CHEMIN CRITIQUE : Previz → Keyframe → AniSora×N → Post-prod
GOULOT : AniSora I2V (180s × N clips = ~1800s pour 10 clips)
SOLUTION : Parallélisation impossible sur AniSora (séquentiel SVI) → optimiser N clips
           et durée par clip plutôt que paralléliser
```

---

## 4bis. GOULOT RAM SYSTÈME 32 Go — confirmé 2026-08-06

Découvert en tentant de faire tourner le pipeline postprod frame-par-frame
(`agents/production_video/postprod_inpaint.py`, RTX 5060 Ti/port ComfyUI
8189) **en parallèle** de la génération SVI continue (RTX 5080/port 8188) :

- ComfyUI 8188 en mode `--lowvram` consomme à lui seul **~20-22 Go de RAM
  système** (le mode lowvram échange de la VRAM contre de la RAM système —
  attendu, mais laisse très peu de marge sur une machine à 32 Go).
- 4 tentatives de lancer la 2e instance ComfyUI (SDXL + IPAdapter + SAM +
  YOLO, ~10-14 Go nécessaires) en parallèle ont été tuées prématurément
  (RAM libre mesurée entre 0,2 et 1,7 Go pendant la génération SVI active).
- Fenêtre opportuniste identifiée : entre la fin d'une itération SVI
  (assemble/upscale) et le début de la suivante, la RAM libre remonte
  brièvement à ~19-25 Go — suffisant pour un test ponctuel, pas pour un
  fonctionnement continu.
- Redémarrer le process ComfyUI 8188 libère la RAM accumulée (20,8→25,4 Go
  libres observés après redémarrage le 2026-08-06) — hypothèse de
  gonflement/fragmentation progressive sur run long, non confirmée par une
  mesure de baseline (pas de relevé RAM en tout début de session).

**Décision (consignes 2026-08-06) : ne pas tenter de paralléliser les deux
pipelines ComfyUI.** Le postprod tourne en mode manuel/opportuniste
(fenêtres entre itérations, cf. `DOCS/MD/POSTPROD_PIPELINE_20260806.md`),
scope limité aux clips prioritaires (`--start-frame`/`--end-frame`), pas un
balayage systématique. Détail chiffré et budget GPU 8h combiné dans
`DOCS/MD/BUDGET_GPU_8H.md`.

**Résolution** : upgrade RAM 32→64 Go (kit en négociation, statut à
confirmer avec Jérémy) — lèverait ce goulot et permettrait la parallélisation
initialement visée.

---

## 5. ARCHITECTURE AGENTS (État réel V2.x)

```
D:\OVERLORD\agents\
├── core/           ← director.py, critic.py, watchdog.py, context_bus.py
├── creative/       ← scenario.py, storyboard.py, prompt_engineer.py, llm_router.py ✅ RAG intégré
├── infra/          ← rag_indexer.py ✅, rag_query.py ✅, session_reporter.py, agent_registry.py
├── production_video/ ← cycle_detector.py ✅, superviseur vidéo
├── segmentation/   ← HandSegNet ✅ (pub.), FootSegNet ✅ (pub.)
└── [shims runpy]   ← compatibilité Phase C
```

**LLM stack (RTX 5060 Ti) :**
- `ov3rlord-coder-stage2v2` (QLoRA Qwen3-4B, fp16, 8.1Go) — style/conventions projet
- RAG hybride BM25+sémantique, 682 chunks (multilingual-e5-small) ✅
- Garde-fou "cite ou refuse" actif ✅
- `qwen2.5-coder:14b-instruct-q4_K_M` — daily driver Aider
- `devstral:24b` — agentic coding (wrapper Python bug backticks)
- `qwen3-coder:30b-a3b-q4_K_M` — tensor split si besoin

---

## 6. CHEF D'ORCHESTRE — Cible V2.0 (inchangée, non implémentée)

```
┌─────────────────────────────────────────────────────────────────────┐
│                    CHEF D'ORCHESTRE                                  │
│  maestro.py + director.py + narrative_memory.py                     │
└───────────────────────────┬─────────────────────────────────────────┘
                            │
        ┌───────────────────┼───────────────────┐
        │                   │                   │
┌───────▼──────┐   ┌────────▼──────┐   ┌────────▼──────┐
│  NARRATEUR   │   │  STORYBOARDER │   │  CONCORDANCE  │
│ scenario.py  │──►│storyboard.py  │──►│ style_cont.py │
└──────────────┘   └───────────────┘   └───────┬───────┘
                                                │ VALIDE
                                        ┌───────▼───────┐
                                        │  PROMPT ENG.  │
                                        │ + RAG inject  │ ✅ opérationnel
                                        └───────┬───────┘
                                                │
                                        ┌───────▼───────┐
                                        │  DESSINATEUR  │
                                        │ AniSora+SVI   │ ✅ opérationnel
                                        └───────┬───────┘
                                                │
        ┌───────────────────────────────────────▼──────┐
        │              JURY DE QUALITÉ (cible V2.0)    │
        │  watchdog + critic + quality_reviewer         │
        │                                               │
        │  Score global pondéré :                       │
        │  - Netteté (watchdog)          : 30%          │
        │  - Cohérence style (SVI drift) : 30%          │
        │  - Concordance prompt (critic) : 25%          │
        │  - Narratif (director)         : 15%          │
        │                                               │
        │  SI score < 90% → REFUS → retry (max 3)      │
        └───────────────────────────────────────────────┘
```

---

## 7. ROADMAP DÉMO — Chemin critique vers fin août 2026

### Débloqué ✅
- AniSora V3.2 I2V validé (ancrage SDXL stylisé)
- SVI 2.0 Pro validé (2 clips, 74 frames, ColorMatch LAB)
- SeedVR2 upscale validé (480p→960p, aucun artefact)
- Workflow A validé bout en bout
- Assets FBX Goku/Vegeta riggés disponibles (E:\Data Demo\)
- MMD pipeline Blender validé (mmd_tools, import PMX/VMD)
- Migration C: → E: (23.7 Go récupérés)
- RAG 682 chunks, garde-fou actif

### En cours 🔄
- Workflow B (previz Blender complet) — bloqué motion : Mixamo retargeting ou VMD combat
- Extraction Umodel FighterZ (DBZ installé E:\jeux\)
- Project DIVA installé → VMD danse extractibles
- SAO Alicization Lycoris en cours de téléchargement → Umodel UE4

### À faire (démo) 📋
- Mixamo retargeting FBX FighterZ (compte Adobe, manuel Jérémy)
- Script previz Blender Python (caméra animée, 2 personnages, décor minimal)
- LoRA personnage rang 32 (étape 2 anti-drift, RTX 5060 Ti, AI-Toolkit)
- Raccord SVI (dette technique — motion frame smoothing)
- Commit git status chargé (trier avec Jérémy)

### Post-démo 🔮
- Director interactif (manette → animation Blender → AniSora) — Godot Engine
- Script karaoké TAS (séquences combat programmées, fenêtre annexe synchronisée)
- R-Tuning Stage 3 (dataset refus calibrés, 200-500 exemples)
- Candidatures cloud credits (NVIDIA Inception priorité 1)
- quality_reviewer.py (jury automatique 90%)
- 186 masques FootSegNet fragmentés (annotation manuelle Jérémy)
- Control-LoRA FootSegNet (mode collapse → piste CtrLoRA)

---

## 8. APPLICATION DES 5S — État au 05/08/2026

### Seiri (整理) — Trier ✅ Phase C accomplie
- 153 modules → 10 sous-dossiers agents/ (réorg Phase C, 16/16 PASS)
- Collision core.py/core/ résolue
- Shims runpy en place pour compatibilité

### Seiton (整頓) — Ranger ✅ Structure cible atteinte
```
D:\OVERLORD\
├── agents/         ← 10 sous-dossiers organisés
├── DOCS/MD/        ← documentation centralisée (CLAUDE.md, INDEX.md, ADRs)
├── DEMO/frames/    ← assets démo (pose, depth, keyframes)
├── workspace/      ← scripts, datasets, évals
└── maestro.py      ← point d'entrée racine
E:\Users\Ov3rL0rD\ ← .cache (12.5Go), .unsloth (5.3Go) — jonctions NTFS
```

### Seiso (清掃) — Nettoyer 🔄
- gpu_usage_log.csv + gpu_cost_estimate.py actifs ✅
- Log rotation : à implémenter
- Règle 90%/92% contexte pour sessions longues ✅
- git status chargé (suppressions BACKUP/, __pycache__) : à trier

### Seiketsu (清潔) — Standardiser ✅
- CLAUDE.md consolidé (conventions vidéo, SVI, ColorMatch, AnimateDiff, GPU)
- CLAUDE-english.md dans RAG ✅
- ADRs actifs (TTS Coqui XTTS-v2, MusicGen, AnimateDiff vs AniSora)
- Standards import protégé, logging, bus — inchangés et valides

### Shitsuke (躾) — Maintenir ✅
- Rituels session : nvidia-smi, launch_ollama.bat, test_pipeline.py --quick
- Règle : toujours vérifier sur disque, jamais la sortie terminal
- Aider : PYTHONIOENCODING=utf-8 + PYTHONUTF8=1, vérifier via git log
- Contexte 90%/92% stop rule pour Claude Code

---

## 9. SYSTÈME DE VALIDATION 90% — Cible V2.0 (inchangé)

```python
# agents/quality_reviewer.py (à créer)
class QualityReviewer:
    WEIGHTS = {
        "sharpness":     0.30,  # watchdog
        "style_drift":   0.30,  # SVI ColorMatch delta
        "prompt_match":  0.25,  # critic
        "narrative_fit": 0.15,  # director
    }
    MAX_RETRIES = 3
    TARGET_SCORE = 90.0
```

**Métriques drift objectifs (HiAR arXiv 2603.08703) :**
- HSV saturation delta inter-clips
- DINOv2 frame-to-frame similarity
- À implémenter post-démo pour mesurer les progrès SVI objectivement

---

## 10. R&D À SURVEILLER

| Technique | Référence | Statut |
|---|---|---|
| SVI 2.0 Pro | ICLR 2026 Oral, EPFL | ✅ Intégré |
| FreqForcing | arXiv 2607.27110 | Pas de node ComfyUI mûr |
| Helios/Relative RoPE | arXiv 2603.04379 | R&D |
| HiAR (métriques drift) | arXiv 2603.08703 | Utile post-démo |
| AniME bilibili | arXiv 2508.18781 | Architecture à surveiller |
| VACE inpainting | Kijai WAN module | Étape 3 anti-drift si besoin |

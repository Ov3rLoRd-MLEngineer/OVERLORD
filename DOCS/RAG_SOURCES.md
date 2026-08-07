# Sources factuelles projet — catalogue pour chargement à la demande

Ce catalogue existe parce que les sources prioritaires du projet (CLAUDE.md +
rapports d'audit + rapports de veille) totalisent environ 44 000 tokens —
plus que le `num_ctx=32768` disponible sur les modèles locaux servis par
Ollama sur la RTX 5060 Ti (`ov3rlord-coder-stage2v2`, `qwen3-coder:30b-a3b`).
Les tout charger en permanence via `read:` dans `.aider.conf.yml`
laisserait trop peu de place pour le code réel et la conversation.

**Noyau toujours chargé** (`.aider.conf.yml`, ~7000 tokens) : `CLAUDE.md`,
`DOCS/INDEX.md`, `DOCS/LLM-Secour.md`, ce fichier.

**Indexé par le RAG sémantique** (`agents/infra/rag_indexer.py`, en plus du
noyau ci-dessus) : `CLAUDE-english.md` — traduction anglaise de `CLAUDE.md`,
ajoutée le 2026-08-03 pour combler l'angle mort cross-lingue documenté dans
`workspace/qlora_dataset/HANDOFF_2026-08-03.md` (une question posée en
français dont la réponse n'existe qu'en anglais dans `CLAUDE.md` était mal
retrouvée par la recherche hybride). Une requête en anglais peut désormais
retrouver directement le passage pertinent dans `CLAUDE-english.md` plutôt
que de dépendre de la correspondance BM25/sémantique cross-langue.

**Le reste : à charger à la demande** avec `/read-only <chemin>` dans une
session Aider, selon le sujet de la tâche en cours.

## Rapports d'audit / bilan

| Fichier | Sujet | Taille (~tokens) |
|---|---|---|
| `RAPPORT_AUDIT_PIPELINE_AOUT2026.md` | Audit de la chaîne image/vidéo (image intégrée, vidéo/animation en silo), llm_router.py non câblé, pipeline batch_controlnet.py dormant | ~7000 |
| `RAPPORT_IDEES_HISTORIQUE_V150_V227.md` | Historique des idées/décisions à travers les sessions V150-V227 | ~5100 |

## Rapports de veille technique (`DOCS/MD/`)

| Fichier | Sujet | Taille (~tokens) |
|---|---|---|
| `Audit de maturité technique 2026 — Pipeline anime IA.md` | État de maturité du pipeline anime IA vs état de l'art 2026 | ~6800 |
| `Prompt engineering robuste anti-hallucination pour un pipeline SDXL ComfyUI de datasets synthétiques.md` | Techniques anti-hallucination prompt/dataset SDXL | ~5700 |
| `Regional Prompting.md` | Techniques de prompting régional (ComfyUI) | ~4500 |
| `Pipeline lineart -N&B - color after.md` | Pipeline lineart N&B puis colorisation | ~5200 |
| `QC_ANATOMIQUE_AUDIT_LICENCES_20260729.md` | QC anatomique + audit licences (2026-07-29) | ~2400 |

## Arborescence, ADRs, limitations et diagnostics (ajoutés le 2026-08-05)

| Fichier | Sujet |
|---|---|
| `workspace/rag_index/sources/arborescence_projet.md` | Inventaire brut (chemins + tailles) de `D:\OVERLORD\` sur 2 niveaux, tous `.py`/`.md`/`.json` significatifs — généré automatiquement, sans description par fichier (anti-hallucination), utile pour la recherche par nom/emplacement de fichier |
| `DOCS/ADR_OVERLORD.md` | Décisions d'architecture formelles (sampler, VAE, seeds, config...) |
| `DOCS/ADR_MUSIC.md` | ADR-012 synthèse musicale (MusicGen) |
| `DOCS/ADR_TTS.md` | ADR TTS (Coqui) |
| `LIMITATIONS_CONNUES.md` | Limitations connues des modèles génératifs (pas des bugs pipeline) — à consulter avant de rouvrir une investigation sur une image "ratée" |
| `workspace/qlora_dataset/VERDICT_COMMITPACK.md` | Verdict évaluation qualitative CommitPack (3 modèles, colonnes à noter manuellement) |
| `footsegnet/controlnet/DIAGNOSTIC_MODE_COLLAPSE_20260728.md` | Diagnostic mode collapse Control-LoRA FootSegNet (2026-07-28) |
| `DOCS/MD/PLAN_COHERENCE_TEMPORELLE_AOUT2026.md` | Plan anti-dérive stylistique vidéo (SVI, ColorMatch, limite ~37 frames structurelle) |

## Session pipeline SVI/AnimateDiff/RAG (ajoutés le 2026-08-05, tâche "RAG 515 → 600+ chunks")

| Fichier | Sujet |
|---|---|
| `workspace/rag_index/sources/agents_arborescence_phase_c.md` | Sous-dossiers `agents/` post-réorg Phase C (généré — angle mort de `arborescence_projet.md`, qui ne descend pas dans les sous-dossiers) |
| `DOCS/MD/HANDOFF_2026-08-04.md` | Handoff session AnimateDiff 32f/SeedVR2/SVI/RAG (2026-08-04/05) |
| `DOCS/MD/TEST_SVI_04082026.md` | Test SVI 2.0 Pro 2 clips (CFG/steps, ColorMatchV2, motion frame) |
| `DOCS/MD/TEST_SVI_2CLIPS.md` | Fusion ffmpeg des 2 clips SVI, rapport technique pré-validation visuelle |
| `DOCS/MD/COMPARAISON_ANIMATEDIFF_VS_ANISORA.md` | Comparaison directe AnimateDiff vs AniSora (verdict, OOM/fix `--lowvram`) |
| `DOCS/MD/TEST_ANISORA_V32_SMOKE.md` | Smoke test AniSora V3.2 (ancrage stylisé SDXL, SeedVR2 upscale) |
| `DOCS/MD/PLAN_PIPELINE_A_DEMO_30S.md` | Plan pipeline A démo 30s (bugs `_REPO_ROOT` post-Phase-C, `cycle_detector.py`) |
| `DOCS/MD/Dépasser la limite de cohérence temporelle.md` | Veille état de l'art 2026 (SVI, infinite video generation) |

## Usage recommandé

- Diagnostic/architecture pipeline → `RAPPORT_AUDIT_PIPELINE_AOUT2026.md`.
- Question sur une décision passée / contexte historique → `RAPPORT_IDEES_HISTORIQUE_V150_V227.md`.
- Prompt engineering / anti-hallucination SDXL → le rapport de veille correspondant.
- Ce catalogue est à mettre à jour manuellement si de nouveaux rapports de
  veille sont ajoutés dans `DOCS/MD/` — pas de mécanisme automatique.

## Limite connue

Ceci n'est **pas** un RAG sémantique (pas d'embeddings, pas de recherche par
similarité) — c'est un index de chargement manuel. Un modèle local ne sait
pas "chercher" dans ce catalogue tout seul ; c'est à l'utilisateur (ou à
l'agent qui pilote Aider) de choisir la bonne source selon la tâche. Le
diagnostic V4/V5 QLoRA (voir `workspace/qlora_dataset/HANDOFF_2026-08-02.md`)
recommandait "un mécanisme de récupération de contexte réel" — ceci est la
version minimale qui s'intègre nativement à Aider (`/read-only`), pas encore
une recherche automatique par pertinence.

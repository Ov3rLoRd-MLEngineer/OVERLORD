# Sources factuelles projet — catalogue pour chargement à la demande

Ce catalogue existe parce que les sources prioritaires du projet (CLAUDE.md +
rapports d'audit + rapports de veille) totalisent environ 44 000 tokens —
plus que le `num_ctx=32768` disponible sur les modèles locaux servis par
Ollama sur la RTX 5060 Ti (`ov3rlord-coder-stage2v2`, `qwen3-coder:30b-a3b`).
Les tout charger en permanence via `read:` dans `.aider.conf.yml`
laisserait trop peu de place pour le code réel et la conversation.

**Noyau toujours chargé** (`.aider.conf.yml`, ~7000 tokens) : `CLAUDE.md`,
`DOCS/INDEX.md`, `DOCS/LLM-Secour.md`, ce fichier.

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

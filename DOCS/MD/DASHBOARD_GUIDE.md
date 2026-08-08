# Guide — Maestro Dashboard (`maestro_dashboard.py`)

Tâche 7, 2026-08-08. Dashboard Flask dédié à l'orchestration parallèle SVI
(`maestro.py --parallel-svi`, tâche 5) — distinct de `api_server.py` (port
5757, HUD du pipeline créatif complet SOURCING→...→3D). Aucune
authentification (usage local uniquement).

## Lancement

```
start cmd /k py -3.12 agents/infra/maestro_dashboard.py
```

→ http://localhost:5000 (accessible depuis n'importe quel navigateur sur la
machine). Dépendance `flask` (déjà dans `requirements.txt` — installée dans
cette session car absente de l'interpréteur `py -3.12` par défaut :
`py -3.12 -m pip install flask`).

## Panels

| Panel | Source réelle | Refresh |
|---|---|---|
| **GPU** | `nvidia-smi` (les deux cartes, 5080 + 5060 Ti) : VRAM, température, utilisation | 5s |
| **Queue pipeline** | `workspace/pipeline_queue/{pending_postprod,completed}/*.json` — écrit par `maestro.py::run_parallel_svi_pipeline` (tâche 5) | 5s |
| **QC visuel** | `workspace/logs/qc_reports/qc_svi_*.json` (5 derniers) + miniatures réelles (frames extraites par `visual_qc_svi.py`, tâche 3) | 10s |
| **Logs** | 50 dernières lignes de `workspace/logs/parallel_svi.log` (créé par `get_logger("parallel_svi")` à chaque run `--parallel-svi`) | 5s |

## Contrôles — réellement câblés, pas des boutons décoratifs

Chaque action écrit dans `workspace/pipeline_queue/control.json`, **lu à
chaque itération** par `gen_worker()` dans
`maestro.py::run_parallel_svi_pipeline` :

- **Pause/Resume** : `{"paused": true}` — `gen_worker` boucle en attente
  (poll 3s) avant de soumettre le clip suivant. Le clip en cours de
  génération sur ComfyUI n'est pas interrompu (pas d'annulation de job
  ComfyUI en vol), seul le *suivant* est retardé.
- **Skip clip #N** : `{"skip_clip": N}` — le clip N est sauté (pas soumis à
  ComfyUI) si son tour arrive avant que le flag soit changé/effacé.
- **CFG / Steps à chaud** : `{"cfg": 1.8, "steps": 6}` — appliqué au
  **prochain** clip soumis (patché dans le JSON du workflow juste avant
  soumission par `_generate_svi_clip`, split HIGH/LOW recalculé
  automatiquement pour `steps`). `null`/vide = valeurs par défaut du fichier
  (CFG 1.5, 8 steps — SVI standard).

Testé réellement (2026-08-08) : cycle écriture/lecture confirmé via
`curl -X POST /api/control` → `GET /api/control` → valeurs bien persistées
et relues.

## Endpoints API

| Route | Méthode | Rôle |
|---|---|---|
| `/api/gpu` | GET | Snapshot des 2 GPU |
| `/api/queue` | GET | État pending/completed |
| `/api/logs` | GET | 50 dernières lignes |
| `/api/qc` | GET | 5 derniers rapports QC + miniatures |
| `/api/qc_thumb?path=...` | GET | Sert une miniature (chemin restreint à `_REPO_ROOT`) |
| `/api/control` | GET/POST | Lit/écrit le fichier de contrôle |

## Limite connue

Le panel Logs est vide tant qu'aucun run `--parallel-svi` n'a eu lieu
**après** l'ajout de `get_logger("parallel_svi")` dans `maestro.py` (fait
dans cette même session, tâche 7) — les runs de test de la tâche 5
utilisaient encore une sortie stdout redirigée manuellement, pas ce fichier.
Se peuplera automatiquement au prochain `--parallel-svi`.

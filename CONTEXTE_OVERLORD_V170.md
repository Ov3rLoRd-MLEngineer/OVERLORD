# CONTEXTE_OVERLORD_V170.md — Cerveau de Démarrage
## Document de référence pour reprise de développement

**Version courante :** V1.70 — "L'Autonomie"
**Date de verrouillage :** 20/06/2026
**Auteur :** Session Claude Sonnet 4.6 + Jérémy Gourlain (Ov3rLoRd / JackouiLL3)
**Statut :** Pipeline intelligent complet. GPU adaptatif. Continuité visuelle & narrative. Config centralisée. Versioning agents.

---

## 1. RÉSUMÉ EXÉCUTIF

Ov3rLoRd V1.70 est un pipeline de production anime IA pleinement autonome et auto-optimisant.
- **Détecte** son GPU et ajuste ses paramètres automatiquement (RTX 2070 → 5090)
- **Mémorise** les personnages et événements entre les épisodes
- **Maintient** la cohérence visuelle entre les 8 frames d'un run
- **Versionne** ses 95+ agents avec rollback automatique
- **Configure** ses 95+ agents depuis une base SQLite centralisée

---

## 2. ARCHITECTURE V1.70

### 2.1 Flux pipeline complet

```
python maestro.py --universe "evangelion" [--batch 3] [--use-prompt-library]
  ↓
[GPU_OPTIMIZER] Auto-detect GPU → preset (steps/résolution/VAE/sampler)
  ↓
[DIRECTOR] Intent → mode/arc/seuil
  ↓
[BLOC 1 — SOURCING] RSS + Trends → TrendReport
  ↓
[NARRATIVE_MEMORY] Inject contexte inter-épisodes dans cfg
  ↓
[BLOC 2 — SCÉNARIO] Ollama/Grok · retry x2 · fallback · prompts EN
  ↓
[NARRATIVE_MEMORY] Extraction personnages + enregistrement épisode
  ↓
[BLOC 3 — STORYBOARD] 8 shots · Parser V2
  ↓
[STYLE_CONTINUITY] Ancre de style → seed progressif · LoRa uniforme · palette
  ↓
[QUALITY_GATE] Validation workflow JSON · auto-fix si corrompu
  ↓
[PROMPT_ENGINEER] Upsampling Booru · sélection LoRa intelligente
  ↓
[BLOC 4 — PRODUCTION ComfyUI] 8 jobs · archive copy · bus enrichi
  ↓
[BLOC 5 — POST-PRODUCTION] Lit bus · ffmpeg assemblage · TTS optionnel
  ↓
[SESSION_REPORTER] Rapport JSON + MD + historique 50 runs
  ↓
[AGENT_REGISTRY] Scan + manifest update (en arrière-plan)
```

### 2.2 Tous les agents V1.50-V1.70

| Agent | Fichier | Statut |
|-------|---------|--------|
| Config centralisée | `agents/config_manager.py` | ✅ V1.70 |
| Versioning agents | `agents/agent_registry.py` | ✅ V1.70 |
| GPU adaptatif | `agents/gpu_optimizer.py` | ✅ V1.70 |
| Continuité visuelle | `agents/style_continuity.py` | ✅ V1.70 |
| Mémoire narrative | `agents/narrative_memory.py` | ✅ V1.70 |
| Tests unitaires | `test_suite_v170.py` | ✅ V1.70 |
| Prompt Engineer | `agents/prompt_engineer.py` | ✅ V1.60 |
| Quality Gate | `agents/quality_gate.py` | ✅ V1.60 |
| Session Reporter | `agents/session_reporter.py` | ✅ V1.60 |
| Auto Sourcing | `agents/auto_sourcing.py` | ✅ V1.60 |
| Grok Client | `agents/grok_client.py` | ✅ V1.50 |
| Prompt Library | `agents/prompt_library.py` | ✅ V1.50 |

### 2.3 Structure workspace V1.70

```
workspace/
├── archive/{run_id}/        ← Images (COPY depuis ComfyUI/output)
├── reports/                 ← Rapports JSON + MD par run
│   └── history.json         ← Historique 50 derniers runs
├── narrative/
│   └── memory.json          ← Personnages + épisodes (persistant)
├── registry/
│   ├── registry.json        ← Index tous les agents
│   ├── manifests/           ← manifest.json par agent
│   └── snapshots/           ← Versions stables pour rollback
├── config.db                ← SQLite config centralisée
├── style_anchor.json        ← Ancre de style du run courant
└── logs/
    ├── auto_sourcing.jsonl
    └── quality_gate.jsonl
```

---

## 3. GPU PROFILES V1.70

| GPU | VRAM | Steps | Résolution | VAE |
|-----|------|-------|------------|-----|
| RTX 2070 | 8GB | 50 | 1024×1536 | taesdxl |
| RTX 3060 | 12GB | 55 | 1024×1536 | sdxl_vae |
| RTX 3080 | 10GB | 65 | 1152×1728 | sdxl_vae |
| RTX 3090 | 24GB | 70 | 1280×1920 | sdxl_vae |
| RTX 4070 | 12GB | 65 | 1152×1728 | sdxl_vae |
| RTX 4080 | 16GB | 70 | 1216×1824 | sdxl_vae |
| RTX 4090 | 24GB | 80 | 1344×1984 | sdxl_vae |
| **RTX 5080** | **16GB** | **80** | **1344×1984** | **sdxl_vae** |
| RTX 5090 | 32GB | 100 | 1536×2304 | sdxl_vae |

Détection automatique au démarrage de chaque run.

---

## 4. CONFIGURATION

### 4.1 .env

```
OV_LLM_MODE=offline          # offline | online | auto | grok
OV_OLLAMA_MODEL=mistral
ANTHROPIC_API_KEY=
GROK_API_KEY=                # xai-VOTRE_CLE
```

### 4.2 Config centralisée (config_manager.py)

```python
from agents.config_manager import get_config
c = get_config()
# Lecture avec default
steps = c.get("comfyui.steps", 50)
# Écriture
c.set("comfyui.steps", 80)
# Preset GPU
c.apply_gpu_preset("rtx5080")
# Toutes les clés comfyui
print(c.get_all("comfyui"))
```

### 4.3 Versioning agents

```python
from agents.agent_registry import get_registry
reg = get_registry()
reg.scan()                      # Scanner tous les agents
reg.snapshot("scenario")        # Sauver version stable
reg.rollback("scenario")        # Restaurer si bug
reg.snapshot_all()              # Snapshot global
```

---

## 5. COMMANDES

```bash
# Pipeline standard
python maestro.py --universe "evangelion battle mecha girl"

# Avec tous les features V1.70
python maestro.py --universe "evangelion" --use-prompt-library --batch 3

# Tests
python test_suite_v170.py           # Tous les tests
python test_suite_v170.py --quick   # Imports + JSON seulement

# Agents autonomes
python agents\gpu_optimizer.py          # Détecter GPU + appliquer preset
python agents\config_manager.py         # Voir la config complète
python agents\agent_registry.py         # Scanner + manifests
python agents\narrative_memory.py       # État mémoire narrative
python agents\style_continuity.py       # Test continuité

# Sourcing autonome (arrière-plan)
start /B python agents\auto_sourcing.py --loop 3600 --universe "evangelion"

# Snapshot global avant mise à jour
python -c "from agents.agent_registry import get_registry; get_registry().snapshot_all()"
```

---

## 6. RÈGLES DE PILOTAGE

### Langue
- **Prompts LLM** : ANGLAIS OBLIGATOIRE
- **Logs humains** : FRANÇAIS
- **Code** : ANGLAIS

### Standards V1.70
```python
# Config centralisée — toujours passer par config_manager
from agents.config_manager import get_config
steps = get_config().get("comfyui.steps", 50)

# Snapshot avant patch d'un agent critique
from agents.agent_registry import get_registry
get_registry().snapshot("scenario")  # puis patcher

# Validation syntaxe OBLIGATOIRE
import ast; ast.parse(open("fichier.py").read())

# Cast int sur scores LLM TOUJOURS
score = int(data.get("score_global", 0))

# Images : copy, jamais rename
import shutil; shutil.copy2(src, dest)
```

---

## 7. ROADMAP V1.80+

| Feature | Priorité | Complexité |
|---------|----------|------------|
| Entraînement LoRa autonome (kohya_ss) | P1 | Haute |
| HUD live (api_server câblé HTML) | P2 | Moyenne |
| Agent RP scraper créateurs | P3 | Moyenne |
| Multi-GPU (5080 + 2070 parallèle) | P4 | Haute |
| Publication transmedia auto | P5 | Haute |

---

## 8. REPRISE SESSION

```
Je reprends Ov3rLoRd V1.70.
Pipeline autonome complet. GPU adaptatif. Continuité visuelle & narrative.

Contexte : [joindre CONTEXTE_OVERLORD_V170.md]
Fichiers  : [joindre les .py concernés]
```

---

*Document généré le 20/06/2026 — Session Claude Sonnet 4.6*
*Ov3rLoRd V1.70 — "L'Autonomie" — Pipeline intelligent et auto-optimisant*
*"L'usine se souvient. L'usine s'adapte. L'usine produit."*

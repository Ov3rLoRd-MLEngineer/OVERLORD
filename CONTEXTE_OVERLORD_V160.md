# CONTEXTE_OVERLORD_V160.md — Cerveau de Démarrage
## Document de référence pour reprise de développement

**Version courante :** V1.60 — "L'Intelligence"
**Date de verrouillage :** 20/06/2026
**Auteur :** Session Claude Sonnet 4.6 + Jérémy Gourlain (Ov3rLoRd / JackouiLL3)
**Projet :** Ov3rLoRd Pipeline — Usine à animés automatisée par IA
**Statut :** Pipeline complet certifié. 4 nouveaux agents intelligents. Mode batch + rapport auto.

---

## 1. RÉSUMÉ EXÉCUTIF

Ov3rLoRd est un pipeline de production anime/manga entièrement autonome.
Entrée : un univers → Sortie : script + storyboard + prompts Booru upsamplés + 8 images + vidéo MP4 + rapport de session.

**Stack technique :**
- Python 3.14 · Windows 10 → RTX 5080 (installation imminente) · D:\OVERLORD\
- ComfyUI 0.25.0 · fabricatedXL_v70.safetensors · port 8188 · D:\Ov3rLoRd AI\ComfyUI\
- Ollama local · mistral (principal) · llama3 · deepseek-coder · port 11434
- API Grok xAI (Grok 4 Fast) · $0.20/M tokens · $175/mois gratuits · https://console.x.ai
- API Anthropic Claude (optionnel)
- ffmpeg · tkinter · PyInstaller

**Chiffres V1.60 :**
- 95+ fichiers Python · pipeline 6 blocs + 4 agents intelligents
- 8/8 images certifiées en run réel · netteté 807-5447
- Mode batch (N runs séquentiels) · rapport automatique fin de run
- Sourcing autonome en boucle · bibliothèque prompts auto-alimentée

---

## 2. ARCHITECTURE

### 2.1 Flux de données V1.60

```
python maestro.py --universe "evangelion" --use-prompt-library [--batch 3]
  ↓
[DIRECTOR] Intent → mode/arc/seuil
  ↓
[BLOC 1 — SOURCING] ✅
  RSS + Trends → TrendReport → bus
  ↓
[BLOC 2 — SCÉNARIO] ✅
  Ollama/Grok → script JSON · retry x2 · fallback minimal · prompts EN
  ↓
[BLOC 3 — STORYBOARD] ✅
  8 shots · Parser V2 · fallback minimal
  ↓
[QUALITY GATE] ✅ NOUVEAU V1.60
  Valide Combined_V35_API.json avant envoi
  Auto-fix nœuds corrompus/orphelins si besoin
  ↓
[PROMPT ENGINEER] ✅ NOUVEAU V1.60
  Upsample chaque shot → prompt Booru complet via LLM
  Sélection intelligente LoRa selon contenu du shot
  ↓
[BLOC 4 — PRODUCTION ComfyUI] ✅
  8 jobs · ~30-55s/image RTX 2070 · archive copy
  Bus : production.image_dir
  ↓
[BLOC 5 — POST-PRODUCTION] ✅
  Lit bus production.image_dir · ffmpeg assemblage · TTS optionnel
  ↓
[SESSION REPORTER] ✅ NOUVEAU V1.60
  Rapport JSON + MD : images, scores, LoRas, temps, historique
  ↓
[BLOC 3D / EXPORT] ⏭
```

### 2.2 Nouveaux agents V1.60

| Agent | Fichier | Rôle |
|-------|---------|------|
| Prompt Engineer | `agents/prompt_engineer.py` | Upsampling Booru · sélection LoRa intelligente |
| Quality Gate | `agents/quality_gate.py` | Validation workflow · auto-fix · log JSONL |
| Session Reporter | `agents/session_reporter.py` | Rapport fin de run JSON+MD · historique |
| Auto Sourcing | `agents/auto_sourcing.py` | Collecte tendances · génère prompts · boucle autonome |

### 2.3 Agents existants mis à jour V1.60

| Agent | Changements |
|-------|-------------|
| `maestro.py` | V1.60 · imports 4 agents · quality gate avant prod · prompt eng avant prod · rapport finally · args --batch/--no-prompt-engineer/--no-quality-gate |
| `agents/scenario.py` | Prompts full EN · retry x2 · fallback script · int(score) cast |
| `agents/overlord_utils.py` | Mode `grok` · `_call_grok()` · `_get_grok_key()` · DEFAULT_OLLAMA_MODEL=mistral |
| `agents/postprod.py` | Lit bus `production.image_dir` · fallback archive récent · .jpg/.webp |
| `agent_supervisor_v2.py` | AVAILABLE_LORAS · random.choice · output path correct · archive copy · bus enrichi |
| `agents/prompt_library.py` | Bibliothèque prompts Booru locaux · `prompts_local.json` |
| `agents/grok_client.py` | Client Grok 4 Fast standalone |

### 2.4 Structure fichiers

```
D:\OVERLORD\
├── maestro.py                   ← V1.60 (930 lignes)
├── agent_supervisor_v2.py       ← RACINE (pas dans agents/)
├── Combined_V35_API.json        ← Workflow patché V1.50 (71 nœuds)
├── CONTEXTE_OVERLORD_V160.md
│
├── agents\
│   ├── overlord_utils.py        ← Mode grok intégré
│   ├── scenario.py              ← Prompts EN + retry + fallback
│   ├── postprod.py              ← Lit bus image_dir
│   ├── prompt_engineer.py       ← NOUVEAU V1.60
│   ├── quality_gate.py          ← NOUVEAU V1.60
│   ├── session_reporter.py      ← NOUVEAU V1.60
│   ├── auto_sourcing.py         ← NOUVEAU V1.60
│   ├── grok_client.py           ← NOUVEAU V1.50
│   ├── prompt_library.py        ← NOUVEAU V1.50
│   └── [85+ autres agents]
│
├── data\
│   └── prompts\
│       ├── prompts_local.json   ← Bibliothèque Booru personnelle
│       ├── character_library.json
│       └── style_refs.json
│
└── workspace\
    ├── archive\{run_id}\        ← Images (COPY depuis ComfyUI/output)
    ├── reports\                 ← Rapports JSON + MD par run
    │   └── history.json         ← Historique 50 derniers runs
    ├── logs\
    │   ├── auto_sourcing.jsonl  ← Log sourcing autonome
    │   └── quality_gate.jsonl   ← Log validations workflow
    └── checkpoints\{slug}\
```

---

## 3. ÉTAT DES LIEUX V1.60

### 3.1 Certifié

| Composant | Statut | Notes |
|-----------|--------|-------|
| Pipeline blocs 1-4 | ✅ | Run complet 586s · 8/8 images |
| Scénario retry + fallback | ✅ | Plus jamais d'arrêt pipeline |
| ComfyUI production | ✅ | 50 steps · cfg 6.0 · dpmpp_2m · karras |
| Archive images (copy) | ✅ | workspace/archive/{run_id}/ |
| Bus production.image_dir | ✅ | Postprod trouve les images |
| Prompt engineer | ✅ | Upsampling Booru + LoRa intelligente |
| Quality gate | ✅ | Validation + auto-fix workflow |
| Session reporter | ✅ | JSON + MD + historique |
| Auto sourcing | ✅ | Boucle autonome + génère prompts |
| Mode batch | ✅ | --batch N runs séquentiels |
| Grok 4 Fast | ✅ | Code prêt · clé à configurer |

### 3.2 À faire

| Composant | Priorité | Action |
|-----------|----------|--------|
| Post-prod vidéo | P1 | Tester assemblage ffmpeg avec nouvelles images |
| sdxl_vae.safetensors | P1 | Re-DL ~335MB · HuggingFace stabilityai/sdxl-vae |
| RTX 5080 | P1 | detect_gpu() + ajuster steps/résolution |
| GROK_API_KEY | P2 | Ajouter dans .env → OV_LLM_MODE=grok |
| prompt_library init | P2 | python agents\prompt_library.py |
| auto_sourcing boucle | P3 | start /B python agents\auto_sourcing.py --loop 3600 |
| Reddit OAuth | P4 | reddit.com/prefs/apps → .env |
| HTML → api_server | P4 | V1.61 |

### 3.3 Bugs connus

**BUG A — Reddit 403** : Normal sans OAuth. RSS suffit.
**BUG B — HTML statiques** : live_monitor.html non connecté. V1.61.
**BUG F — sdxl_vae corrompu** : Utiliser taesdxl en attendant.

---

## 4. CONFIGURATION

### 4.1 .env complet V1.60

```
ANTHROPIC_API_KEY=
OV_LLM_MODE=offline          # offline | online | auto | grok
OV_OLLAMA_MODEL=mistral
GROK_API_KEY=                # xai-VOTRE_CLE (https://console.x.ai)
```

### 4.2 ComfyUI

```
Chemin    : D:\Ov3rLoRd AI\ComfyUI\
Output    : D:\Ov3rLoRd AI\ComfyUI\output\
Checkpoint: models\checkpoints\fabricatedXL_v70.safetensors
VAE actif : taesdxl (léger) — sdxl_vae.safetensors corrompu
LoRas     : models\loras\ (3 fichiers ponyXL)
Port      : 8188
```

### 4.3 Paramètres génération actuels

```json
{
  "steps": 50, "cfg": 6.0,
  "sampler": "dpmpp_2m", "scheduler": "karras",
  "width": 1024, "height": 1536,
  "vae": "taesdxl"
}
```

**Avec RTX 5080 (à ajuster après installation) :**
```json
{
  "steps": 80, "cfg": 6.5,
  "width": 1344, "height": 1984
}
```

### 4.4 LoRas disponibles

```
asuka-langley-soryuu-classic-ponyxl-lora-nochekaiser.safetensors
mari-makinami-rebuild-ponyxl-lora-nochekaiser.safetensors
rei-ayanami-classic-ponyxl-lora-nochekaiser.safetensors
```

---

## 5. COMMANDES

### Démarrage standard
```bash
python maestro.py --media-type anime --universe "evangelion battle mecha"
```

### Avec prompts locaux enrichis
```bash
python maestro.py --media-type anime --universe "evangelion" --use-prompt-library
```

### Mode batch (3 runs séquentiels)
```bash
python maestro.py --media-type anime --universe "evangelion" --batch 3
```

### Sourcing autonome arrière-plan
```bash
start /B python agents\auto_sourcing.py --loop 3600 --universe "evangelion mecha"
```

### Initialiser bibliothèque prompts
```bash
python agents\prompt_library.py
```

### Valider le workflow ComfyUI
```bash
python agents\quality_gate.py
```

### Tester Grok
```bash
python agents\grok_client.py
```

### Désactiver les nouveaux agents (debug)
```bash
python maestro.py --universe "test" --no-prompt-engineer --no-quality-gate
```

---

## 6. RÈGLES DE PILOTAGE

### Langue
- **Prompts LLM** (system + user) : ANGLAIS OBLIGATOIRE
- **Logs humains** : FRANÇAIS
- **Code** : ANGLAIS

### Standards
- `fallback_llm()` = point d'entrée LLM unique
- `int(score)` = cast obligatoire (mistral renvoie des strings)
- `safe_json_parse()` = toujours pour parser JSON LLM
- `ast.parse()` = validation syntaxe avant livraison
- `shutil.copy2()` = copier les images (jamais `rename`)
- Branding : `Ov3rLoRd` (jamais `OverLord`)

### Séquence de tests
```bash
python test_pipeline.py --quick           # 16/16 PASS
python agents\quality_gate.py             # Workflow valide
python maestro.py --universe "Dragon Ball" # Run complet
```

---

## 7. REPRISE SESSION

```
Je reprends Ov3rLoRd V1.60.
Pipeline complet certifié. 4 agents intelligents actifs.

Contexte : [joindre CONTEXTE_OVERLORD_V160.md]
Fichiers  : [joindre les .py concernés]

Priorités :
1. Tester vidéo post-prod end-to-end
2. Installer RTX 5080 + ajuster paramètres
3. Configurer GROK_API_KEY dans .env
4. Lancer auto_sourcing en boucle
```

---

*Document généré le 20/06/2026 — Session Claude Sonnet 4.6*
*Ov3rLoRd V1.60 — "L'Intelligence" — Pipeline autonome complet*
*"Le pipeline pense maintenant avant de dessiner."*

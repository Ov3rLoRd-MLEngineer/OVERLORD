# CONTEXTE_OVERLORD_V150.md — Cerveau de Démarrage
## Document de référence pour reprise de développement

**Version courante :** V1.50 — La Production  
**Date de verrouillage :** 20/06/2026  
**Auteur :** Session Claude Sonnet 4.6 + Jérémy Gourlain (Ov3rLoRd / JackouiLL3)  
**Projet :** Ov3rLoRd Pipeline — Usine à animés automatisée par IA  
**Statut :** Pipeline certifié blocs 1-4. 8/8 images générées. Post-prod à connecter.

---

## 1. RÉSUMÉ EXÉCUTIF

Ov3rLoRd est un pipeline de production anime/manga entièrement automatisé.
Entrée : un univers (ex: "evangelion battle mecha girl") → Sortie : script + storyboard + 8 images ComfyUI + vidéo MP4 + publication transmedia.

**Stack technique :**
- Python 3.14 · Windows 10 → Windows 11 (migration prévue avec RTX 5080)
- ComfyUI 0.25.0 + fabricatedXL_v70.safetensors · port 8188 · `D:\Ov3rLoRd AI\ComfyUI\`
- Ollama local (LLM offline) port 11434 · modèles : mistral (principal), llama3, deepseek-coder
- API Anthropic Claude (optionnel)
- API Grok xAI (à intégrer — Grok 4 Fast $0.20/M tokens, $175/mois gratuits)
- ffmpeg (assemblage vidéo)
- tkinter (launcher GUI)
- PyInstaller (build EXE)

**Chiffres V1.50 :**
- 89+ fichiers Python · 5 .bat
- Pipeline blocs 1-4 certifié en run réel (20/06/2026)
- 8/8 images générées · netteté 807-5447 (excellent)
- 16/16 PASS sur test_pipeline.py --quick
- LLM : mode offline Ollama validé (mistral en principal)
- GPU actuel : RTX 2070 8GB · GPU cible : RTX 5080 16GB (installation imminente)

---

## 2. ARCHITECTURE

### 2.1 Structure des dossiers

```
D:\OVERLORD\
├── maestro.py                  ← Chef d'orchestre (POINT D'ENTRÉE UNIQUE)
├── overlord_utils_utf8.py      ← Force UTF-8 console
├── agent_supervisor_v2.py      ← Supervisor ComfyUI (RACINE, pas dans agents/)
├── Combined_V35_API.json       ← Workflow ComfyUI actif (patché V1.50)
├── patcher.py
├── build_exe.py
├── test_pipeline.py
├── test_integration.py
├── deploy.py
├── self_improve.py             ← PROTÉGÉ
├── .env                        ← PROTÉGÉ
│
├── agents\
│   ├── overlord_utils.py       ← Utilitaires centraux
│   ├── context_bus.py          ← Mémoire partagée singleton
│   ├── director.py
│   ├── sourcing.py
│   ├── scenario.py             ← MODIFIÉ V1.50 (prompts EN, retry x2, fallback)
│   ├── storyboard.py
│   ├── critic.py
│   ├── watchdog.py
│   ├── checkpoint_manager.py
│   ├── agent_supervisor_v2.py  ← ATTENTION : doublon possible (vrai fichier = racine)
│   └── [65+ autres agents]
│
├── workspace\
│   ├── logs\
│   ├── checkpoints\            ← Structuré par univers : anime_evangelion_battle_mecha_girl\
│   ├── scripts\                ← Scripts JSON générés
│   ├── storyboards\
│   ├── archive\                ← Images archivées par run_id (COPIE, original dans ComfyUI/output)
│   │   └── {run_id}\           ← Ex: maestro_20260620_061428_prod\
│   ├── backups\                ← Backups workflow JSON
│   └── context_bus\
│
└── workspace\outputs\images\   ← Fallback si ComfyUI output inaccessible
```

### 2.2 Flux de données principal

```
[USER] python maestro.py --media-type anime --universe "evangelion battle mecha girl"
  ↓
[DIRECTOR] set_intent() → mode BALANCE | seuil 73 | arc wonder
  ↓
[BLOC 1 — SOURCING]  ✅ CERTIFIÉ
  Reddit 403 normal · 60 RSS + 7 Trends → 67 mots-clés
  → Critique PASS score=80
  ↓
[BLOC 2 — SCÉNARIO]  ✅ CERTIFIÉ V1.50
  Ollama/mistral → retry x2 si JSON invalide → fallback minimal si tout échoue
  Prompts FULL ANGLAIS (meilleure fiabilité JSON mistral)
  Score 85/100 typique
  → Critique PASS score=80
  ↓
[BLOC 3 — STORYBOARD]  ✅ CERTIFIÉ
  8 shots générés · Parser V2 · fallback minimal
  → Critique PASS score=80
  ↓
[BLOC 4 — PRODUCTION ComfyUI]  ✅ CERTIFIÉ V1.50
  agent_supervisor_v2.py (RACINE) → POST http://127.0.0.1:8188/prompt
  Workflow : Combined_V35_API.json (71 nœuds, patché)
  8/8 images · ~30-55s/image RTX 2070 · netteté 807-5447
  Archive : workspace/archive/{run_id}/ (COPY, pas move)
  Bus : production.image_dir, supervisor.archived_images
  → Critique PASS score=80
  ↓
[BLOC 5 — POST-PRODUCTION]  ⚠️ À CONNECTER
  Doit lire bus.read("production.image_dir") pour trouver les images
  Actuellement : cherche au mauvais endroit → "Aucune image trouvée"
  ↓
[BLOC 6 — 3D / EXPORT]  ⏭ En attente
```

### 2.3 Workflow ComfyUI — Combined_V35_API.json

**Node IDs critiques (attendus par agent_supervisor_v2.py) :**

| Node | Type | Rôle | Patché V1.50 |
|------|------|------|--------------|
| 62 | LoraLoader | LoRa principale (random si vide) | ✅ |
| 87 | CLIPTextEncode | Positive prompt | ✅ |
| 99 | CLIPTextEncode | Positive prompt 2 | ✅ |
| 111 | CLIPTextEncode | Negative prompt | ✅ |
| 112 | Seed (rgthree) | Seed principal | ✅ |
| 75 | easy int | Width=1024 | ✅ |
| 77 | easy int | Height=1536 | ✅ |
| 334 | SaveImage | Sortie images | ✅ |
| 303 | LoraLoader | LoRa détailer (random si vide) | ✅ |
| 382 | Seed (rgthree) | Seed détailer | ✅ |
| 301 | CLIPTextEncode | Positive détailer | ✅ |
| 380 | CLIPTextEncode | Negative détailer | ✅ |
| 68 | DifferentialDiffusion | Modèle détailer | ✅ |
| 100 | VAELoader | taesdxl (VAE léger) | ✅ |
| 104 | EmptyLatentImage | 1024×1536 | ✅ |
| 108 | CheckpointLoaderSimple | fabricatedXL_v70.safetensors | ✅ |
| 116 | KSampler | 50 steps · cfg 6.0 · dpmpp_2m · karras | ✅ |

**LoRas disponibles (D:\Ov3rLoRd AI\ComfyUI\models\loras\) :**
```
asuka-langley-soryuu-classic-ponyxl-lora-nochekaiser.safetensors
mari-makinami-rebuild-ponyxl-lora-nochekaiser.safetensors
rei-ayanami-classic-ponyxl-lora-nochekaiser.safetensors
```
→ Choisie aléatoirement par le supervisor si le job n'en spécifie pas.

**VAE :** `taesdxl` (VAE léger intégré). Le `sdxl_vae.safetensors` est corrompu (taille invalide) — à re-télécharger (~335MB depuis HuggingFace) pour la qualité maximale.

### 2.4 agent_supervisor_v2.py — Localisation et config

```python
# FICHIER À LA RACINE D:\OVERLORD\ (pas dans agents/)
WORKFLOW_FILE = "Combined_V35_API.json"
COMFY_URL     = "http://127.0.0.1:8188"

# Output ComfyUI
comfy_out = Path(r"D:/Ov3rLoRd AI/ComfyUI/output")

# Archive (COPY, pas move)
ARCHIVE_DIR = Path("workspace/archive")

# LoRas par défaut
AVAILABLE_LORAS = [
    "asuka-langley-soryuu-classic-ponyxl-lora-nochekaiser.safetensors",
    "mari-makinami-rebuild-ponyxl-lora-nochekaiser.safetensors",
    "rei-ayanami-classic-ponyxl-lora-nochekaiser.safetensors",
]

# Paramètres qualité
# steps=50 · cfg=6.0 · sampler=dpmpp_2m · scheduler=karras
# width=1024 · height=1536

# Bus publié après run
# production.image_dir  → str(ARCHIVE_DIR / run_id)
# supervisor.archived_images → list[str] chemins images
```

### 2.5 scenario.py — Changements V1.50

```python
# Prompts FULL ANGLAIS (mistral produit du JSON plus propre)
# Retry x2 dans generate_script avant abandon
# _fallback_script() : script minimal valide si tout échoue
# Pipeline ne s'arrête JAMAIS sur un échec scénario
# score = int(review.get("score_global", 0))  ← cast obligatoire (mistral renvoie str)
```

---

## 3. ÉTAT DES LIEUX V1.50

### 3.1 Ce qui fonctionne (certifié run réel 20/06/2026)

| Composant | Statut | Notes |
|-----------|--------|-------|
| Pipeline blocs 1-4 | ✅ CERTIFIÉ | Run complète 586s |
| 8/8 images ComfyUI | ✅ OK | netteté 807-5447 |
| Watchdog frame analysis | ✅ OK | Détecte ruptures de style |
| scenario.py retry + fallback | ✅ OK | Plus jamais d'arrêt pipeline |
| score int cast | ✅ OK | Résout TypeError str vs int |
| Archive images (copy) | ✅ OK | workspace/archive/{run_id}/ |
| Bus production.image_dir | ✅ OK | Publié par supervisor |
| LoRa aléatoire | ✅ OK | random.choice(AVAILABLE_LORAS) |
| Paramètres qualité | ✅ OK | 50 steps, cfg 6.0, dpmpp_2m karras |

### 3.2 Ce qui est à faire (priorités V1.50)

| Composant | Statut | Action |
|-----------|--------|--------|
| Post-production | ⚠️ BLOQUÉ | Lire bus "production.image_dir" au lieu de chercher en dur |
| sdxl_vae.safetensors | ⚠️ CORROMPU | Re-télécharger ~335MB HuggingFace stabilityai/sdxl-vae |
| Grok 4 Fast | 📋 À INTÉGRER | Scénarios via API xAI ($0.20/M, $175 gratuits) |
| prompt_library.py | 📋 À CRÉER | Prompts locaux → jobs supervisor |
| QwenVL prompt engineer | 📋 À CRÉER | Upsampling Booru avant envoi ComfyUI |
| Reddit OAuth | ⚠️ 403 | Optionnel V1.51 |
| RTX 5080 presets | 📋 À ACTIVER | detect_gpu() + presets PRESETS_GPU_V150.md |

### 3.3 Bug post-production

**Symptôme :** `[POST-PROD] Aucune image trouvée`

**Cause :** postprod cherche les images au mauvais endroit. Les images sont dans :
```
workspace\archive\{run_id}\
```
Le bus publie `production.image_dir` depuis V1.50 supervisor.

**Fix à appliquer dans postprod.py :**
```python
from agents.context_bus import get_bus
bus = get_bus()
image_dir = bus.read("production.image_dir")
# Chercher les images dans image_dir
```

### 3.4 Bugs connus (hérités)

**BUG A — Reddit 403** : Normal sans OAuth. RSS suffit.

**BUG B — HTML non connectés** : live_monitor.html statique. V1.51 : câbler api_server.py.

**BUG C — Bannière "V1.49n"** : Cosmétique dans maestro.py.
```python
logger.info("    Ov3rLoRd Pipeline V1.49n")  # → changer en V1.50
```

**BUG D — Checkpoint --from-block** : Sans sourcing rejoué = pas de TrendReport.
Solution : toujours relancer from scratch, ou supprimer le checkpoint corrompu.
Chemin checkpoints : `workspace\checkpoints\{media_type}_{univers_slugifié}\`

**BUG E — v130_agent_personality.py** : Non injecté dans les prompts. V1.51.

**BUG F — sdxl_vae.safetensors corrompu** : Utiliser `taesdxl` en attendant.

---

## 4. PATCHES APPLIQUÉS EN SESSION V1.50

| Bundle | Fichier | Fix |
|--------|---------|-----|
| V1.50a | Combined_V35_API.json | Suppression nœuds LoraManager (62,303,97,369,391) → natifs |
| V1.50b | Combined_V35_API.json | Strings vides inline (TriggerWord Toggle) |
| V1.50c | Combined_V35_API.json | Suppression Reroute orphelin #391 |
| V1.50d | Combined_V35_API.json | lora_name valide + vae=taesdxl |
| V1.50e | Combined_V35_API.json | Paramètres qualité : 50 steps, cfg 6.0, dpmpp_2m, 1024×1536 |
| V1.50f | agent_supervisor_v2.py | Output path D:\Ov3rLoRd AI\ComfyUI\output |
| V1.50g | agent_supervisor_v2.py | archive copy (shutil.copy2) au lieu de rename/move |
| V1.50h | agent_supervisor_v2.py | AVAILABLE_LORAS + random.choice() |
| V1.50i | agent_supervisor_v2.py | Bus : production.image_dir + supervisor.archived_images |
| V1.50j | agent_supervisor_v2.py | Logs full anglais |
| V1.50k | agents/scenario.py | Prompts full anglais + retry x2 + fallback script |
| V1.50l | agents/scenario.py | int(score) cast (TypeError str vs int) |

---

## 5. ROADMAP TECHNIQUE

### V1.50 — EN COURS

**P1 — Connecter post-production ✅ partiellement**
Bus `production.image_dir` publié par supervisor.
→ Patch postprod.py pour lire ce bus.

**P2 — RTX 5080**
Après installation :
```python
from PRESETS_GPU_V150 import detect_gpu
profile = detect_gpu()  # → "rtx5080"
```
Ajuster dans Combined_V35_API.json :
- steps : 50 → 80
- width/height : 1024×1536 → 1344×1984 (possible avec 16GB VRAM)
- Activer presets Flux.1 (F1-F2, RTX 5080+)

**P3 — Grok 4 Fast pour les scénarios**
```python
# Dans agents/overlord_utils.py ou nouveau agents/grok_client.py
# OV_LLM_MODE=grok dans .env
# GROK_API_KEY=... dans .env
# Endpoint : https://api.x.ai/v1/chat/completions
# Modèle : grok-4-fast ($0.20/M input, $0.50/M output)
# $175/mois gratuits via data-sharing program
```

**P4 — prompt_library.py**
```
D:\OVERLORD\data\prompts\
├── prompts_local.json      ← tes prompts Booru personnels
├── style_refs.json         ← références visuelles
└── character_library.json  ← personnages récurrents
```
Agent qui charge ces fichiers et les injecte comme jobs enrichis dans le supervisor.

**P5 — QwenVL prompt engineer**
Agent `prompt_engineer.py` :
- Input : shot description du storyboard
- Appel QwenVL (déjà installé dans ComfyUI custom_nodes)
- System prompt Booru (fourni par Jérémy)
- Output : prompt upsamplé → injecté dans le job supervisor

**P6 — sdxl_vae.safetensors**
```
HuggingFace : stabilityai/sdxl-vae
Fichier : sdxl_vae.safetensors (~335MB)
Destination : D:\Ov3rLoRd AI\ComfyUI\models\vae\
```
Puis dans Combined_V35_API.json : `"vae_name": "sdxl_vae.safetensors"`

### V1.51 — Après stabilité V1.50

- Agent personnalités (Viktor/Mia/Élise/Atlas) injectés dans scenario + critic
- Reddit OAuth
- HTML → api_server.py câblage
- Entraînement LoRa autonome (kohya_ss CLI + dataset auto-généré)

### V2.0 — Long terme

Restructuration dossiers core/agents/ui/api + multi-GPU.

---

## 6. RÈGLES DE PILOTAGE

### 6.1 Standards de codage

**Branding :** Toujours `Ov3rLoRd` (jamais `OverLord`).

**Langue :**
- Prompts LLM (system + user) : **ANGLAIS OBLIGATOIRE** (meilleure fiabilité JSON)
- Logs humains (INFO/WARNING/ERROR) : **FRANÇAIS** 
- Code Python (variables, commentaires) : **ANGLAIS**

**LLM — point d'entrée unique :**
```python
from agents.overlord_utils import fallback_llm
result = fallback_llm(prompt, system="", max_tokens=1000, logger=log)
```

**JSON parsing — toujours safe_json_parse + cast int :**
```python
from agents.overlord_utils import safe_json_parse
ok, data, err = safe_json_parse(raw, logger=log)
score = int(data.get("score_global", 0))  # cast obligatoire
```

**Imports protégés :**
```python
try:
    from agents.narrative_memory import NarrativeMemory
    MEMORY_OK = True
except ImportError:
    MEMORY_OK = False
```

**Validation syntaxe avant livraison :**
```python
import ast; ast.parse(open("fichier.py").read())
```

### 6.2 Fichiers protégés

```python
PROTECTED_FILES = {"self_improve.py", "licence_server.py", "config.json", ".env"}
```

### 6.3 Séquence de tests obligatoire

```bash
# 1. Tests rapides
python test_pipeline.py --quick
# Attendu : 16/16 PASS

# 2. Pipeline complet
python maestro.py --media-type anime --universe "Dragon Ball"
# Attendu : Sourcing OK → Scénario OK → Storyboard OK → 8/8 images OK
```

### 6.4 Gestion checkpoints

Structure : `workspace\checkpoints\{media_type}_{univers_slugifié}\`
Ex : `workspace\checkpoints\anime_evangelion_battle_mecha_girl\`

Si pipeline plante et checkpoint corrompu :
```
del workspace\checkpoints\anime_evangelion_battle_mecha_girl\*
python maestro.py --media-type anime --universe "..."
```

### 6.5 Règles session Claude

**Pour reprendre :**
1. Nouvelle conversation Claude Sonnet 4.6
2. Joindre ce fichier CONTEXTE_OVERLORD_V150.md
3. Joindre les fichiers Python à modifier
4. `"Je reprends Ov3rLoRd V1.50. Priorité : [objectif précis]."`

**Ne pas faire :**
- Demander confirmation pour chaque action
- Code verbeux avec commentaires excessifs
- S'arrêter pour expliquer avant de faire

**Toujours faire :**
- Audit syntaxe `ast.parse()` avant livraison
- Livrer via `create_file`
- Branding `Ov3rLoRd`
- Rapport .md à chaque version majeure

---

## 7. INFORMATIONS PROJET

**Utilisateur :** Jérémy Gourlain — Ov3rLoRd / JackouiLL3  
**Machine actuelle :** Windows 10 · Python 3.14 · RTX 2070 8GB · D:\OVERLORD\ · D:\Ov3rLoRd AI\ComfyUI\  
**Machine cible :** RTX 5080 16GB (installation imminente) · SSD 2To dédié  
**Ollama modèles :** mistral · llama3 · deepseek-coder  
**ComfyUI version :** 0.25.0 · Revision 150  
**Checkpoint modèle :** fabricatedXL_v70.safetensors  
**LoRas :** 3x ponyXL nochekaiser (Asuka, Mari, Rei)  
**VAE actif :** taesdxl (léger) · sdxl_vae.safetensors corrompu à re-DL  
**Objectif :** Production anime IA autonome · plateforme Onibaku Gumi

---

## 8. COMMANDE DE REPRISE

```
Je reprends Ov3rLoRd V1.50.
Pipeline blocs 1-4 certifié. Post-production à connecter.

Contexte : [joindre CONTEXTE_OVERLORD_V150.md]
Fichiers à modifier : [joindre les .py concernés]

Priorités session :
1. Patch postprod.py → lire bus "production.image_dir"
2. RTX 5080 : detect_gpu() + ajuster Combined_V35_API.json
3. Grok 4 Fast : agents/grok_client.py + .env OV_LLM_MODE=grok
4. prompt_library.py : prompts locaux Booru → supervisor
5. QwenVL prompt engineer : upsampling avant ComfyUI
```

---

## 9. NEXT RUN ATTENDUE

Avec tous les patches V1.50 déployés, le prochain run complet devrait afficher :

```
[SUPERVISOR] Batch complete : 8/8 successes
[WATCHDOG/FRAME] job000X → PASS | nettete=XXXX | OK
[POST-PROD] Pipeline demarre — X images trouvees depuis workspace/archive/
[POST-PROD] OK Export → workspace/video/XXXX.mp4
[PIPELINE TERMINE] duree=~600s | sante=STABLE
```

---

*Document généré le 20/06/2026 — Session Claude Sonnet 4.6*  
*Ov3rLoRd Pipeline V1.50 — Blocs 1-4 certifiés — Post-prod en cours*  
*"8 images générées. L'usine tourne. La prochaine frontière : la vidéo."*

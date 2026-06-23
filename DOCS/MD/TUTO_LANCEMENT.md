# TUTO LANCEMENT — OverLord Pipeline v1.0.0-alpha
## Du zéro au premier anime généré par IA

**Temps estimé : 45 min à 2h** (selon la vitesse de ta connexion pour les modèles)

---

## ÉTAPE 0 — CE QU'IL FAUT AVOIR

| Élément | Requis | Notes |
|---|---|---|
| Windows 10/11 | ✓ | 64 bits |
| Python 3.10+ | ✓ | python.org |
| ComfyUI installé | ✓ | Déjà fait |
| 16+ Go RAM | ✓ | 64 Go = parfait |
| GPU NVIDIA | Recommandé | RTX 5080 vendredi ! |
| Connexion internet | ✓ | Pour les modèles |

**Vérifier Python :**
```
python --version
# Doit afficher Python 3.10.x ou supérieur
```

---

## ÉTAPE 1 — ORGANISATION DES FICHIERS

Ton dossier doit ressembler à ça :

```
C:\Users\Ov3rL0rD\Desktop\PIPELINE PROJECT\
│
├── launcher.py              ← Interface principale
├── maestro.py               ← Chef d'orchestre
├── neural_orchestrator.py   ← Cerveau neuronal
├── agent_supervisor_v2.py   ← Superviseur ComfyUI
├── comfy_synesthesia_node.py← Nœud synesthésie
├── llama_chat.py            ← Chat Llama standalone
├── learning_ui.py           ← Interface agent apprenant
├── licence_server.py        ← Serveur de licences
├── build_exe.py             ← Générateur .exe
├── download_dependencies.bat← Téléchargeur modèles
├── Combined_V35_API.json    ← Workflow ComfyUI
├── config.json              ← Configuration batch
│
└── agents\
    ├── context_bus.py           ← Context Window partagée
    ├── pipeline_constitution.py ← Constitution/valeurs
    ├── memory_agent.py          ← Agent mémoire
    ├── learning_agent.py        ← Agent auto-apprenant
    ├── sav_agent.py             ← Agent debug ComfyUI
    ├── ollama_bridge.py         ← Bridge LLM
    ├── obs_agent.py             ← Contrôle OBS
    ├── capture.py               ← Elgato + Webcam
    ├── comfy_memory.py          ← Gestion VRAM
    ├── checkpoint_manager.py    ← Sauvegarde/reprise
    ├── agent_3d_modeler.py      ← Modélisation 3D
    ├── workflow_organizer.py    ← Organisateur JSON
    ├── remote_gpu.py            ← GPU distant
    ├── gpu_scheduler.py         ← Ordonnanceur GPU
    ├── ray_cluster.py           ← Cluster multi-machines
    ├── roles_registry.py        ← Référentiel rôles
    ├── social_agent.py          ← Réseaux sociaux
    ├── marketing_pub.py         ← Marketing/Webmaster/Community
    ├── sys_agent.py             ← Maintenance système
    ├── legacy_agent.py          ← Agent successeur
    ├── multi_attention.py       ← Attention multi-tête
    ├── sourcing.py              ← Sourcing web
    ├── scenario.py              ← Scénariste IA
    ├── storyboard.py            ← Storyboard
    ├── postprod.py              ← Post-production
    ├── critic.py                ← Agent critique
    └── watchdog.py              ← Watchdog qualité
```

---

## ÉTAPE 2 — INSTALLATION DES DÉPENDANCES PYTHON

Ouvre un **Invite de commandes** (`cmd`) en tant qu'administrateur.

```
cd "C:\Users\Ov3rL0rD\Desktop\PIPELINE PROJECT"
```

### Installation minimale (obligatoire) :
```
pip install requests Pillow feedparser pytrends gTTS
pip install customtkinter pywin32
pip install flask cryptography
pip install trimesh
pip install psutil
```

### Installation recommandée (tout activer) :
```
pip install requests Pillow feedparser pytrends gTTS customtkinter pywin32
pip install flask cryptography trimesh psutil
pip install websocket-client obs-websocket-py
pip install opencv-python mutagen librosa
pip install tweepy
pip install google-auth google-auth-oauthlib google-api-python-client
pip install chromadb sentence-transformers
pip install ray[default]
```

### Vérification :
```
python -c "import requests, Pillow, flask, trimesh; print('OK')"
```

---

## ÉTAPE 3 — TÉLÉCHARGER LES MODÈLES

### Automatique (10 Go environ) :
```
download_dependencies.bat
```

Ça télécharge : VAE, ControlNet Canny, Upscalers, YOLO détection, SAM, CLIP Vision, IPAdapter FaceID.

**Laisse tourner — ça peut prendre 30-60 min selon ta connexion.**

### Manuel (obligatoire après) :
Va sur **civitai.com** et télécharge :
1. **NoobAI-XL v1.0** → `models/checkpoints/`
   - Cherche "NoobAI-XL" sur CivitAI
   - Télécharge `noobaiXLNSFWPony_epsilonPred10.safetensors`

Puis mets à jour le workflow :
```
python update_checkpoint.py "noobaiXLNSFWPony_epsilonPred10.safetensors"
```

---

## ÉTAPE 4 — ORGANISER LE WORKFLOW COMFYUI

```
python agents\workflow_organizer.py Combined_V35_API.json
```

→ Génère `Combined_V35_CANVAS.json`

Dans ComfyUI : **Charger** → `Combined_V35_CANVAS.json` → `Ctrl+A` → `Ctrl+F`

---

## ÉTAPE 5 — LANCER L'INTERFACE PRINCIPALE

```
python launcher.py
```

L'interface s'ouvre. Tu verras :

```
  ⬡  OverLord  v1.0.0-alpha  |  ⏱ 00:00:00  |  Nouveau projet
```

### Premiers réglages dans l'interface :

**Section MODÈLES :**
- Checkpoint → `noobaiXLNSFWPony_epsilonPred10.safetensors`
- VAE → `sdxl_vae.safetensors`
- LoRA → laisser vide pour commencer

**Section IMAGE :**
- W: `1024` | H: `1536` | Steps: `28` | CFG: `6`
- Sampler: `euler_ancestral` | Scheduler: `normal`

**Section PROMPTS :**
- Positif: `masterpiece, best quality, amazing quality, absurdres, 1girl, solo, looking at viewer, anime style`
- Négatif: `bad quality, worst quality, deformed, bad hands, watermark`

---

## ÉTAPE 6 — TON PREMIER TEST (ComfyUI seule)

1. Lance **ComfyUI** séparément :
```
D:\IA Local\ComfyUI Installation Local\ComfyUI_windows_portable\run_nvidia_gpu.bat
```

2. Dans l'interface OverLord, clique :
```
🖼  ComfyUI seule (config.json)
```

3. La console affiche en temps réel :
```
[17:02:01] ▶ Exécution démarrée
[17:02:02]   ⚙ Nœud actif : [108] Checkpoint
[17:02:04]   ⚙ Nœud actif : [116] KSampler
[17:02:05]   Step 1/28  [█-------------------]  3%
[17:02:14]   Step 28/28 [████████████████████] 100%
[17:02:15]   ✓ Génération terminée — 1 image sauvegardée
```

---

## ÉTAPE 7 — LANCER L'AUTO-APPRENTISSAGE

### Option A : Interface graphique
```
python learning_ui.py
```

Onglet **⚙ Contrôle** :
- Nombre d'épisodes : `10` (pour commencer)
- Intervalle : `60` secondes
- Type de média : `anime`
- Clique : **▶ DÉMARRER L'APPRENTISSAGE**

L'agent tourne en fond, chaque run améliore ses paramètres.

Pour lui parler → onglet **💬 Dialogue** :
- "Qu'as-tu appris jusqu'ici ?"
- "Quel est ton meilleur paramètre découvert ?"
- "Pourquoi tu préfères steps=32 ?"

### Option B : Ligne de commande
```
python -c "
from agents.learning_agent import LearningAgent
import logging
logging.basicConfig(level=logging.INFO)
agent = LearningAgent()
agent.run_learning_loop(n_episodes=5, interval_s=30)
"
```

---

## ÉTAPE 8 — PIPELINE COMPLET (Sourcing → Post-prod)

```
python maestro.py --media-type anime --universe "Dragon Ball Super Broly"
```

Avec l'orchestrateur neuronal :
```
python -c "
from agents.neural_orchestrator import NeuralOrchestrator
orch = NeuralOrchestrator()
result = orch.process(
    prompt='scène épique, guerrier anime, énergie ki',
    media_type='anime',
    universe='Dragon Ball'
)
print('Prompt optimisé :', result['positive'][:100])
"
```

### Reprendre après une interruption :
```
python maestro.py --resume
```

---

## ÉTAPE 9 — CHAT LLAMA (usage parallèle)

```
python llama_chat.py
```

Prérequis : **Ollama installé** sur ta machine.
- Télécharge Ollama : https://ollama.com
- Lance : `ollama pull llama3`
- Puis `python llama_chat.py`

---

## ÉTAPE 10 — SERVEUR DE LICENCES (pour la Beta)

```
python licence_server.py
```

**La clé admin s'affiche UNE SEULE FOIS — note-la !**

Accès mobile S10+ :
- WiFi local : `http://TON_IP:5001/dashboard`
- Via ngrok : télécharge ngrok.com → `ngrok http 5001`

---

## ÉTAPE 11 — ORGANISER LE WORKFLOW POUR COMFYUI

Le workflow est automatiquement organisé avec des groupes colorés :

```
python agents\workflow_organizer.py Combined_V35_API.json
```

Dans ComfyUI :
1. **Charger** → `Combined_V35_CANVAS.json`
2. `Ctrl+A` → `Ctrl+F` pour centrer
3. Les blocs sont organisés de gauche à droite par fonction

---

## ÉTAPE 12 — NŒUD SYNESTHÉSIE (dans ComfyUI)

1. Copier `comfy_synesthesia_node.py` dans :
```
ComfyUI\custom_nodes\overlord_synesthesia\__init__.py
```

2. Redémarrer ComfyUI

3. Dans l'interface ComfyUI, cherche le nœud :
```
OverLord / Synesthésie IA
```

4. Connecte un fichier audio → les visuels s'adaptent au son !

---

## COMMANDES DE RÉFÉRENCE RAPIDE

```bash
# Interface principale
python launcher.py

# Auto-apprentissage interface
python learning_ui.py

# Chat Llama
python llama_chat.py

# Pipeline complet
python maestro.py --media-type anime --universe "Mon Univers"

# Production ComfyUI seule
python agent_supervisor_v2.py config.json

# Reprendre après crash
python maestro.py --resume

# Organiser le workflow ComfyUI
python agents\workflow_organizer.py Combined_V35_API.json

# Serveur de licences
python licence_server.py

# Générer l'exe
python build_exe.py

# Dashboard système
python -c "from agents.sys_agent import SysAgent; SysAgent().print_dashboard()"

# Test orchestrateur neuronal
python agents\neural_orchestrator.py

# Test synesthésie
python comfy_synesthesia_node.py
```

---

## PROBLÈMES FRÉQUENTS

### "ModuleNotFoundError: No module named 'X'"
```
pip install X
```

### "ComfyUI ne répond pas"
1. Vérifier que ComfyUI tourne : ouvre http://127.0.0.1:8188
2. Relancer ComfyUI avec : `run_nvidia_gpu.bat`

### "CUDA out of memory"
Lancer ComfyUI avec :
```
python main.py --lowvram --cpu-vae --disable-smart-memory
```

### "Le modèle introuvable"
```
python update_checkpoint.py "nom_exact_du_fichier.safetensors"
```

### "La console est vide"
Le subprocess ne renvoie rien → vérifier que `maestro.py` est bien dans le même dossier que `launcher.py`.

### L'auto-apprentissage ne démarre pas
```
python -c "from agents.learning_agent import LearningAgent; print('OK')"
```
Si erreur → vérifier que `agents/learning_agent.py` existe.

---

## LANCER L'AUTO-APPRENTISSAGE EN PRIORITÉ

**Avant que la session se termine, lance ça maintenant :**

```
python learning_ui.py
```

→ Onglet **⚙ Contrôle**
→ Episodes : `0` (infini)
→ Intervalle : `120` secondes
→ **▶ DÉMARRER**

L'agent tourne en fond et apprend même pendant que tu fais autre chose.
Quand tu reviens, onglet **💬 Dialogue** pour voir ce qu'il a découvert.

---

## ARCHITECTURE EN UN COUP D'ŒIL

```
launcher.py
    │
    ├── neural_orchestrator.py   ← Cerveau (Context Bus + Constitution + RLHF)
    │       ├── context_bus.py   ← Mémoire partagée temps réel
    │       ├── pipeline_constitution.py ← Valeurs + résolution conflits
    │       └── multi_attention.py      ← Analyse parallèle
    │
    ├── maestro.py               ← Pipeline Sourcing→3D
    │       ├── sourcing.py / sourcing_multisensor.py
    │       ├── scenario.py
    │       ├── storyboard.py
    │       ├── agent_supervisor_v2.py (ComfyUI)
    │       └── postprod.py
    │
    ├── learning_ui.py           ← Interface agent apprenant
    │       └── learning_agent.py ← Boucle RLHF Plan→Act→Reflect→Learn
    │
    ├── llama_chat.py            ← Chat Llama standalone
    └── licence_server.py        ← Serveur licences + dashboard S10+
```

---

*OverLord Pipeline v1.0.0-alpha — 15/06/2026*
*36 fichiers Python | ~18 500 lignes | Conçu avec Claude (Anthropic)*

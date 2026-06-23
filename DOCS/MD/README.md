# OverLord Pipeline — v1.0.0-alpha
### Usine à Animés & Création Multimédia Automatisée

[![Version](https://img.shields.io/badge/version-1.0.0--alpha-purple)]()
[![Status](https://img.shields.io/badge/status-Alpha-orange)]()
[![Python](https://img.shields.io/badge/python-3.10%2B-blue)]()
[![GPU](https://img.shields.io/badge/GPU-RTX%205080%2016Go-green)]()

---

## Qu'est-ce que OverLord ?

OverLord est un pipeline de production audiovisuelle et 3D entièrement automatisé,
piloté par des agents IA. Il prend en entrée une idée, un univers, un prompt,
et produit en sortie des images animé, des vidéos, des storyboards, des modèles 3D,
et des fichiers d'impression résine — sans intervention humaine entre les étapes.

```
Idée / Tendances
      │
      ▼
 [SOURCING] → Reddit, RSS, Google Trends
      │
      ▼
 [SCÉNARIO] → Script complet (Claude/GPT/Llama)
      │
      ▼
 [STORYBOARD] → Shot list + prompts ComfyUI
      │
      ▼
 [PRODUCTION] → ComfyUI SDXL + FaceDetailer + LoRAs
      │
      ▼
 [POST-PROD] → ffmpeg + TTS + montage
      │
      ▼
 [3D / STL] → Shap-E / TripoSR / OpenSCAD → Anycubic Mono X 6Ks
```

---

## Installation rapide

### Prérequis
- Windows 10/11
- Python 3.10+
- ComfyUI >= 0.24 (déjà installé)
- CUDA (RTX GPU recommandé)

### 1. Cloner / Extraire le projet

```
C:\Users\TonNom\Desktop\PIPELINE PROJECT\
├── launcher.py
├── maestro.py
├── agent_supervisor_v2.py
├── Combined_V35_API.json
├── config.json
├── AGENTS\
│   ├── sourcing.py
│   ├── scenario.py
│   ├── storyboard.py
│   ├── postprod.py
│   ├── critic.py
│   ├── watchdog.py
│   ├── obs_agent.py
│   ├── capture.py
│   ├── comfy_memory.py
│   ├── checkpoint_manager.py
│   ├── sav_agent.py
│   ├── ollama_bridge.py
│   ├── agent_3d_modeler.py
│   └── workflow_organizer.py
└── llama_chat.py
```

### 2. Installer les dépendances Python

```bash
# Minimum absolu
pip install requests Pillow customtkinter pywin32 gTTS feedparser pytrends

# Recommandé (toutes fonctionnalités)
pip install requests Pillow customtkinter pywin32 gTTS feedparser pytrends \
            trimesh websocket-client obs-websocket-py opencv-python

# 3D (optionnel)
pip install shap-e
pip install git+https://github.com/VAST-AI-Research/TripoSR.git
```

### 3. Télécharger les modèles

```bash
# Lance le script de téléchargement automatique
download_dependencies.bat

# Puis télécharge manuellement (voir MANUAL_DOWNLOADS.md) :
# → NoobAI-XL v1.0 (checkpoint principal, 6.5 Go)
# → ip-adapter-faceid-plusv2_sdxl.bin
# → Modèles YOLO de détection
```

### 4. Lancer l'interface

```bash
python launcher.py
# ou
MaestroProduction.exe
```

### 5. Configurer le checkpoint

```bash
python update_checkpoint.py "noobaiXLNSFWPony_epsilonPred10.safetensors"
```

---

## Lancement rapide

### Production ComfyUI seule (test immédiat)
```bash
python agent_supervisor_v2.py config.json
```

### Pipeline complet
```bash
python maestro.py --media-type anime --universe "Dragon Ball Super Broly"
```

### Chat Llama
```bash
python llama_chat.py
```

### Organiser le workflow ComfyUI
```bash
python agents/workflow_organizer.py Combined_V35_API.json
# → génère Combined_V35_CANVAS.json à ouvrir dans ComfyUI
```

### Générer le .exe
```bash
python build_exe.py
# → dist/MaestroProduction.exe
```

---

## Architecture des agents

| Agent | Rôle | Dépendances |
|---|---|---|
| `maestro.py` | Chef d'orchestre | tous les agents |
| `agent_supervisor_v2.py` | Superviseur ComfyUI batch | requests |
| `sourcing.py` | Veille web (Reddit/RSS/Trends) | feedparser, pytrends |
| `scenario.py` | Scénariste IA + Script Doctor | API Anthropic/Ollama |
| `storyboard.py` | Shot list + prompts ComfyUI | API Anthropic/Ollama |
| `postprod.py` | Montage vidéo + TTS | ffmpeg, gTTS |
| `critic.py` | Validation inter-blocs | requests |
| `watchdog.py` | Surveillance VRAM + cohérence | Pillow |
| `sav_agent.py` | Debug ComfyUI | requests |
| `ollama_bridge.py` | Bridge LLM Online/Offline | requests |
| `obs_agent.py` | Contrôle OBS Studio | obs-websocket-py |
| `capture.py` | Elgato 4K + Webcam | opencv-python |
| `comfy_memory.py` | Gestion VRAM RTX 5080 | requests |
| `checkpoint_manager.py` | Sauvegarde/reprise pipeline | — |
| `agent_3d_modeler.py` | Modélisation 3D + STL | trimesh, shap-e |
| `workflow_organizer.py` | Organisation visuelle JSON | — |

---

## Configuration GPU recommandée (RTX 5080 + i7-8700K)

Lancer ComfyUI avec :
```bash
python main.py --disable-smart-memory --normalvram --cpu-vae \
               --use-pytorch-cross-attention --preview-method none \
               --disable-auto-launch
```

Estimation VRAM pipeline complet : ~14-15 Go / 16 Go disponibles.
`--cpu-vae` est obligatoire pour rester dans les limites.

---

## Notes Alpha

Cette version est une **Alpha fonctionnelle**. Le pipeline est opérationnel
de bout en bout mais certaines fonctionnalités avancées nécessitent encore
des dépendances externes (Blender, OpenSCAD, Ollama) qui ne sont pas
installées automatiquement.

### Fonctionnel en Alpha
- ✓ Pipeline complet Sourcing → Post-prod
- ✓ Interface graphique avec tous les paramètres
- ✓ Loopback qualité (Critique + Watchdog)
- ✓ Sauvegarde/reprise des travaux
- ✓ Chat Llama standalone
- ✓ Organisateur workflow ComfyUI
- ✓ Support OBS Studio
- ✓ Modélisation 3D (avec dépendances)

### Prévu pour la Beta
- UI redesign complet (thème moderne, effets de verre)
- Tests automatisés end-to-end
- Installateur Windows (.msi)
- Documentation vidéo

---

## Fichiers à ne PAS supprimer

```
Combined_V35_API.json    ← workflow ComfyUI (CRITIQUE)
node_catalog.json        ← catalogue des nœuds pour l'UI
settings.json            ← tes préférences (généré automatiquement)
config.json              ← jobs batch
```

---

*OverLord Pipeline v1.0.0-alpha — 15/06/2026*
*Développé avec Claude (Anthropic) — Architecture OverLord*

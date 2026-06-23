# GUIDE COMPLET — OverLord Pipeline v3.0 Alpha
## Document de formation IA & Manuel Utilisateur

---

## INTRODUCTION

OverLord est un pipeline de production audiovisuelle automatisée, piloté par intelligence artificielle.  
Il orchestre la génération d'images, vidéos, scénarios et storyboards depuis une interface unique,  
en enchaînant ComfyUI, des agents LLM, OBS Studio, et des outils de post-production.

**Ce document est conçu pour :**
- Former un opérateur humain à utiliser le pipeline
- Être ingéré par une IA pour qu'elle apprenne à piloter le pipeline de façon autonome

---

## ARCHITECTURE GLOBALE

```
[Interface Graphique launcher.py]
         │
         ▼
[maestro.py — Chef d'Orchestre]
         │
    ┌────┴────────────────────────────┐
    │                                 │
    ▼                                 ▼
[BLOC SSS]                    [PRODUCTION]
 sourcing.py                  agent_supervisor_v2.py
 scenario.py                  Combined_V35_API.json
 storyboard.py                ComfyUI (SDXL)
    │                                 │
    ▼                                 ▼
[CRITIQUE & WATCHDOG]         [POST-PRODUCTION]
 critic.py                    postprod.py
 watchdog.py                  ffmpeg + TTS
    │                                 │
    └──────────── OBS Studio ─────────┘
                  obs_agent.py
```

---

## SECTION 1 — L'INTERFACE GRAPHIQUE (launcher.py)

### Lancement
```bash
python launcher.py
# ou via l'exécutable :
MaestroProduction.exe
```

### 1.1 Barre de titre

| Élément | Rôle |
|---|---|
| `⬡ OverLord v3.0 Alpha` | Nom et version du pipeline |
| `⏱ 00:42:17` | Compteur de temps actif de la session (reprend d'une session à l'autre) |
| `Nouveau projet` | Nom du projet actif |
| `⚙` | Ouvre le panneau de configuration des nœuds ComfyUI |
| `☀ / 🌙` | Bascule entre thème clair et sombre |
| `🖼` | Ouvre les paramètres d'image de fond |
| `📌` | Crée un raccourci bureau avec les paramètres actuels |
| `🤖` | Ouvre le panneau SAV (diagnostic d'erreurs) |

### 1.2 Séparateur central

Le trait vertical entre le panneau gauche (paramètres) et droit (console) est **draggable** :  
clique dessus et glisse pour ajuster la largeur des deux colonnes.  
**Plage** : 260 px minimum à gauche, 620 px maximum.

---

## SECTION 2 — PANNEAU GAUCHE (paramètres)

### 2.1 MODE LLM

**Rôle :** Choisit quel moteur d'intelligence artificielle traite les requêtes  
de génération de scénarios, storyboards et diagnostics.

| Paramètre | Valeurs | Impact |
|---|---|---|
| Switch OFFLINE/ONLINE | OFFLINE = Ollama local / ONLINE = API cloud | OFFLINE : gratuit, plus lent. ONLINE : payant, plus puissant |
| Modèle Online | Claude Sonnet 4.6 / GPT-4o / Gemini 1.5 | Claude = meilleur pour l'écriture créative. GPT-4o = équilibré. Gemini = multimodal |
| Modèle Offline | Llama3 / Mistral / DeepSeek Coder | Llama3 = polyvalent. Mistral = compact et rapide. DeepSeek = code/debug |

**⚠ Si un modèle Ollama n'est pas installé :** une fenêtre propose de le télécharger automatiquement.  
Le téléchargement peut prendre 5-20 minutes selon la taille du modèle.

---

### 2.2 PIPELINE

**Rôle :** Définit le type de production et son contexte narratif.

| Paramètre | Valeurs | Impact |
|---|---|---|
| Type de média | anime, manga, comics, 3d, photoreal, art, game, short, film | Oriente le style visuel et les prompts générés automatiquement |
| Durée | 15 sec → 120 min, ou nombre d'images/planches | Détermine combien de shots le storyboard générera |
| Univers / Contexte | Texte libre (ex: "Dragon Ball Super Broly") | Nourrit le scénariste IA avec le contexte de l'univers cible |

**Recommandations durée :**
- Court animé (test) : `15 sec` → 5-10 images
- Épisode anime standard : `22 min (Épisode anime)` → 80-120 shots
- Chapitre manga : `24 planches` → 24 images haute résolution

---

### 2.3 MODÈLES

**Rôle :** Configure les modèles IA utilisés par ComfyUI pour générer les images.

| Paramètre | Description | Impact sur la qualité |
|---|---|---|
| **Checkpoint** | Modèle SDXL principal (.safetensors) | Détermine le style global. NoobAI-XL = meilleur anime. Illustrious = illustrations |
| **VAE** | Variational Autoencoder | Influence les couleurs et la netteté. sdxl_vae.safetensors = standard |
| **LoRA Principal** | Adaptation fine du style (nom du fichier) | Ajoute un style spécifique (personnage, artiste, ambiance) |
| **LoRA Detailer** | LoRA pour la phase d'amélioration des détails | Peut être différent du LoRA principal pour cibler les visages |
| **Force LoRA (strength)** | 0.0 → 2.0 | 0.7-1.0 = équilibré. >1.2 = style très marqué, risque d'artefacts |

**Conseils pratiques :**
- Commence à `strength = 0.8` et ajuste selon le résultat
- Un LoRA vide = génération avec le checkpoint seul (plus générique)
- Detail Tweaker XL à `strength = 0.5` améliore systématiquement les détails

---

### 2.4 IMAGE

**Rôle :** Contrôle les paramètres techniques de la génération d'images.

| Paramètre | Valeur recommandée | Impact |
|---|---|---|
| **W (Largeur)** | 1024 px | Résolution horizontale. SDXL optimal à 1024 |
| **H (Hauteur)** | 1536 px | Résolution verticale. Portrait = 1024x1536. Paysage = 1536x1024 |
| **Steps** | 28 | Nombre d'itérations de dénoising. Plus = meilleure qualité, plus lent |
| **CFG** | 6.0 | Guidance scale. 5-7 = équilibré. >10 = suraccroché au prompt, artefacts |
| **Sampler** | euler_ancestral | Algorithme de génération. Voir tableau ci-dessous |
| **Scheduler** | normal | Courbe de bruit. `karras` = meilleure qualité en moins de steps |
| **Denoise** | 1.0 | Force de dénoising. 1.0 = génération complète. <1.0 = img2img |
| **Seed** | -1 | Graine aléatoire. -1 = nouveau à chaque fois. Fixer pour reproduire |

**Guide des Samplers :**

| Sampler | Vitesse | Qualité | Usage recommandé |
|---|---|---|---|
| `euler_ancestral` | Rapide | Bonne | Production anime quotidienne — **défaut** |
| `euler` | Rapide | Bonne | Plus déterministe que ancestral |
| `dpm++_2m` | Moyen | Excellente | Portraits haute qualité |
| `dpm++_2m_sde` | Moyen | Très bonne | Créativité + qualité, moins déterministe |
| `dpm++_3m_sde` | Lent | Excellente | Qualité maximale, production lente |
| `lcm` | Très rapide | Correcte | Prototypage rapide (4-8 steps suffisent) |
| `ddim` | Moyen | Bonne | Reproductibilité parfaite (déterministe) |

**Résolutions SDXL recommandées :**

| Format | Largeur | Hauteur | Usage |
|---|---|---|---|
| Carré | 1024 | 1024 | Illustrations, avatars |
| Portrait 2:3 | 1024 | 1536 | Personnages, manga vertical |
| Portrait 9:16 | 768 | 1344 | Shorts, stories |
| Paysage 16:9 | 1344 | 768 | Scènes, arrière-plans |
| Cinemascope | 1536 | 640 | Plans cinématographiques |

---

### 2.5 PROMPTS

**Rôle :** Décrit ce que l'IA doit générer (positif) et éviter (négatif).

#### Prompt Positif
Décrit le contenu souhaité. Utilise le style Booru (tags séparés par des virgules).

**Structure recommandée :**
```
[QUALITÉ], [SUJET], [COMPOSITION], [STYLE], [COULEURS], [ÉCLAIRAGE]

masterpiece, best quality, amazing quality, absurdres,
1girl, solo, looking at viewer, portrait,
long silver hair, blue eyes, white dress,
anime style, detailed face, soft lighting
```

**Tags de qualité NoobAI-XL :**
- `masterpiece` → > 95e percentile de qualité
- `best quality` → > 85e percentile
- `good quality` → > 60e percentile
- `absurdres` → résolution maximale

#### Prompt Négatif
Décrit ce que l'IA doit éviter.

```
bad quality, worst quality, worst detail, sketch,
bad hands, extra fingers, bad anatomy, deformed,
watermark, signature, text, blurry, ugly
```

#### Prompt QwenVL (Agent Vision)
Instructions système pour l'agent Qwen VL qui améliore automatiquement les prompts.  
Ce texte définit **comment** l'IA doit transformer une description simple en prompt détaillé.  
**Ne modifie que si tu veux changer le comportement de l'agent.**

---

### 2.6 BLOC SSS — Sourcing · Scénario · Storyboard

**Rôle :** Les 3 agents IA qui préparent le contenu avant la production d'images.

| Bouton | Agent | Ce qu'il fait |
|---|---|---|
| `📡 Sourcing` | sourcing.py | Scrute Reddit, RSS, Google Trends pour identifier les tendances du moment |
| `✍ Scénario` | scenario.py | Génère un script complet (titre, actes, scènes, personnages) inspiré par le sourcing |
| `🎬 Storyboard` | storyboard.py | Décompose le script en shots avec prompts ComfyUI prêts à l'emploi |

**Le Bloc SSS structure automatiquement les LoRAs** pour chaque élément :
- LoRA de personnage principal
- LoRA de décor / background
- LoRA de style visuel
- LoRA d'effets spéciaux (sfx, fx)

**Usage workflow complet :**
1. Clique `📡 Sourcing` → attends le rapport de tendances
2. Clique `✍ Scénario` → le scénariste IA génère le script
3. Clique `🎬 Storyboard` → les shots sont générés avec leurs prompts
4. Clique `▶ LANCER LA PRODUCTION` → les shots deviennent des images

---

### 2.7 PROGRESSION (zone fixe)

**Rôle :** Affiche l'avancement de chaque bloc en temps réel.

Cette zone ne scrolle **pas** — elle reste toujours visible en bas du panneau.

| Barre | Bloc | Ce qu'elle mesure |
|---|---|---|
| `📡 Sourcing` | Sourcing | Scraping web + agrégation |
| `✍ Scénario` | Scénario | Génération + validation Script Doctor |
| `🎬 Storyboard` | Storyboard | Création de la shot list |
| `🏭 Production` | Production | Génération des images (node par node) |
| `🎞 Post-prod` | Post-production | Assemblage vidéo + audio |

La barre clignote (effet shimmer) pendant le traitement et affiche `0-100%`.

---

### 2.8 BOUTONS D'ACTION

| Bouton | Action |
|---|---|
| `▶ LANCER LA PRODUCTION` | Lance le pipeline complet (tous les blocs) |
| `⏹ ARRÊTER` | Interrompt proprement + sauvegarde d'urgence automatique |
| `🖼 ComfyUI seule` | Envoie directement config.json à ComfyUI (sans SSS) |
| `📌 Raccourci` | Crée un .lnk Windows avec les paramètres actuels |

---

## SECTION 3 — PANNEAU DROIT (Console)

**Rôle :** Affiche tous les logs du pipeline en temps réel.

### Code couleur des logs

| Couleur | Signification |
|---|---|
| 🟢 Vert clair | INFO — déroulement normal |
| 🟡 Jaune | WARNING — anomalie non bloquante |
| 🔴 Rouge | ERROR — erreur bloquante |
| 🟢 Vert foncé | SUCCESS — étape réussie |
| 🟣 Violet | BLOCK — changement de bloc du pipeline |
| ⬛ Gris foncé | DEBUG — détails techniques |
| 🔵 Bleu clair | SAV — action de l'agent de débogage |

### Logs ComfyUI en temps réel
Quand ComfyUI génère une image, la console affiche :
```
[17:02:02]   ⚙ Nœud actif : [108] Charger Point de Contrôle
[17:02:04]   ⚙ Nœud actif : [116] KSampler
[17:02:05]   Step 1/28  [█-------------------]  3%
[17:02:14]   Step 28/28 [████████████████████] 100%
[17:02:15]   ✓ Génération terminée — 1 image(s)
```

---

## SECTION 4 — PARAMÈTRES AVANCÉS (⚙)

### 4.1 Panneau des nœuds ComfyUI

Accessible via le bouton `⚙` dans la barre de titre.

**Filtre par catégorie :**
- `production` — nœuds utilisés à chaque génération (Checkpoint, LoRA, Seed, Sampler...)
- `detailer` — nœuds du workflow Detailer (FaceDetailer, MaskDetailer...)
- `avancé` — nœuds techniques (CLIP, VAE, KSampler brut...)
- `autre` — nœuds utilitaires (Switch, Concaténation...)

**Switch ON/OFF :** Clique sur une ligne pour activer/désactiver sa visibilité dans l'interface.  
"Sauvegarder" mémorise les préférences dans `settings.json`.

---

## SECTION 5 — FOND D'ÉCRAN ET TRANSPARENCE (🖼)

**Rôle :** Personnaliser l'apparence de l'interface.

| Paramètre | Description |
|---|---|
| Image de fond | Sélectionne un fichier jpg/png/webp comme fond |
| Opacité | 0 = panneaux opaques (image invisible). 1 = panneaux transparents (image visible) |

**Comment ça fonctionne :**  
L'image de fond reste toujours **derrière** les panneaux.  
Les panneaux (paramètres et console) deviennent semi-transparents selon le slider,  
laissant apparaître l'image.  
L'image n'est jamais altérée — c'est uniquement la transparence des panneaux qui change.

---

## SECTION 6 — AGENT SAV (🤖)

**Rôle :** Diagnostique et corrige automatiquement les erreurs ComfyUI.

### Utilisation
1. ComfyUI affiche une erreur dans son terminal
2. Copie le texte de l'erreur
3. Clique `🤖` dans la barre de titre
4. Colle l'erreur dans la zone de texte
5. Clique `🔍 Diagnostiquer`

Le SAV identifie :
- La cause racine
- Les nœuds impliqués
- Les étapes de correction
- Comment éviter que ça se reproduise

### Bug ControlNet — Correction automatique

**Problème connu :** Après une génération avec ControlNet actif,  
la 2e génération peut crasher ControlNet.

**Solution automatique dans le pipeline :**  
Le cycle ControlNet est géré automatiquement :
1. **Phase Reset** : envoi du workflow avec ControlNet désactivé
2. **Phase Warm** : attente 2.5s + interruption pour charger le cache
3. **Phase Production** : envoi du workflow avec ControlNet actif

Ce cycle s'applique à chaque génération automatiquement.

---

## SECTION 7 — OBS STUDIO

**Rôle :** Intégration avec OBS pour la capture et l'enregistrement.

### Connexion
OBS doit être ouvert avec le WebSocket activé :
- Menu OBS → Outils → obs-websocket Server Settings
- Enable WebSocket Server ✓
- Port : 4455

### Scènes recommandées à créer dans OBS

| Scène | Source | Usage |
|---|---|---|
| `OverLord - Référence` | Elgato 4K Pro | Capture de référence pour la génération |
| `OverLord - Webcam` | Webcam USB-C | Monitoring de l'opérateur |
| `OverLord - Green Screen` | Webcam + Chroma Key | Fond vert pour composition |
| `OverLord - ComfyUI Preview` | Fenêtre ComfyUI | Enregistrement des générations |
| `OverLord - Monitoring` | Multi-sources | Vue globale pendant la production |

### Flux de travail avec OBS
1. Ouvrir OBS avec les scènes configurées
2. Lancer `python launcher.py`
3. Le pipeline se connecte automatiquement à OBS
4. Chaque session de production est enregistrée automatiquement
5. Les frames Elgato peuvent être capturées comme références visuelles

---

## SECTION 8 — CHECKPOINT (REPRISE DES TRAVAUX)

**Rôle :** Sauvegarde automatique de l'état du pipeline pour reprise après interruption.

### Comportement automatique
- Après chaque bloc terminé : **sauvegarde automatique**
- Sur `⏹ ARRÊTER` ou Ctrl+C : **sauvegarde d'urgence**
- Au redémarrage : **détection et proposition de reprise**

### Reprendre un travail interrompu
```bash
python maestro.py --resume
# ou
python maestro.py --resume --run-id run_20250615_143022
```

### Structure des checkpoints
```
workspace/checkpoints/
└── anime_DragonBall/
    ├── run_20250615_143022.json   ← état complet
    └── run_20250615_150814.json
```

Chaque checkpoint contient : config, données de chaque bloc, erreurs, timestamp.

---

## SECTION 9 — GESTION MÉMOIRE RTX 5080

**Configuration optimale pour RTX 5080 (16 Go VRAM) + i7-8700K (64 Go RAM) :**

### Arguments ComfyUI recommandés
```bash
# Mode production (pipeline seul)
python main.py --disable-smart-memory --normalvram --cpu-vae \
               --use-pytorch-cross-attention --preview-method none \
               --disable-auto-launch

# Mode développement (avec interface)
python main.py --disable-smart-memory --lowvram --cpu-vae \
               --use-pytorch-cross-attention --preview-method latent2rgb
```

### Estimation VRAM par opération

| Opération | VRAM utilisée |
|---|---|
| Chargement SDXL | ~4-5 Go |
| Génération 1024x1536 (pic) | ~8-10 Go |
| FaceDetailer | +2 Go |
| IPAdapter FaceID | +1.5 Go |
| VAE encode/decode | +1.5 Go (→ 0 avec --cpu-vae) |
| **Total pipeline complet** | **~14-15 Go** |

**Avec --cpu-vae :** VAE déchargé sur le CPU → économie ~1.5 Go VRAM  
**Model offloading (--lowvram) :** les modèles inutilisés passent en RAM → économie ~4 Go VRAM  
**64 Go RAM :** largement suffisant pour accueillir tous les modèles offloadés

### Libération manuelle de la VRAM
L'API `/free` de ComfyUI est appelée automatiquement entre les jobs :
```python
requests.post("http://127.0.0.1:8188/free",
              json={"unload_models": True, "free_memory": True})
```

---

## SECTION 10 — LLAMA CHAT (USAGE PARALLÈLE)

**Rôle :** Interface de chat dédiée avec Llama via Ollama, indépendante du pipeline.

### Lancement
```bash
python llama_chat.py
```

### Presets système disponibles
| Preset | Usage |
|---|---|
| Assistant général | Aide générale en français |
| Expert ComfyUI | Déboguer et optimiser des workflows |
| Scénariste anime | Créer des histoires et arcs narratifs |
| Code Python | Développer et déboguer du code |
| Vide | Conversation libre sans instructions |

### Fonctionnalités
- **Streaming** : affichage mot à mot pendant la génération
- **Contexte** : nombre de messages précédents envoyés à l'IA (2 à 32)
- **Température** : 0 = déterministe, 2 = très créatif
- **Export** : sauvegarde la conversation en JSON
- **Lancer Ollama** : démarre le serveur Ollama directement depuis l'interface

---

## SECTION 11 — CAPTURE VIDÉO (Elgato + Webcam)

**Rôle :** Utiliser les périphériques vidéo comme sources de référence pour la génération IA.

### Utilisation dans le pipeline

```python
from agents.capture import CaptureDevice

# Lister les périphériques
dev = CaptureDevice("elgato_4k")
devices = dev.list_devices()

# Capturer une frame de référence
paths = dev.capture_reference(n_frames=3)

# La meilleure frame peut être utilisée comme image de référence
# dans ComfyUI via IPAdapter ou img2img
```

### Flux de travail recommandé
1. Filmer une scène réelle avec l'Elgato ou la webcam
2. `capture.py` extrait des frames clés
3. Ces frames sont passées au storyboard comme références visuelles
4. ComfyUI génère des images dans le style anime à partir de ces références
5. OBS enregistre le résultat final

---

## GLOSSAIRE

| Terme | Définition |
|---|---|
| **SDXL** | Stable Diffusion XL — modèle de génération d'images 1024px natif |
| **LoRA** | Low-Rank Adaptation — fine-tuning léger qui ajoute un style spécifique |
| **Checkpoint** | Fichier .safetensors contenant les poids d'un modèle SDXL |
| **VAE** | Variational Autoencoder — encode/décode entre espace latent et pixels |
| **CFG Scale** | Coefficient de guidage — force avec laquelle le prompt influence la génération |
| **Sampler** | Algorithme de dénoising itératif |
| **Denoise** | 1.0 = génération complète. <1.0 = modification d'une image existante |
| **ComfyUI** | Interface de workflow visuel pour Stable Diffusion |
| **FaceDetailer** | Nœud ComfyUI qui améliore automatiquement les visages générés |
| **IPAdapter** | Technique permettant d'utiliser une image comme référence de style |
| **Ollama** | Serveur local pour faire tourner des LLMs (Llama, Mistral...) |
| **OBS** | Open Broadcaster Software — logiciel de capture et streaming vidéo |
| **VRAM** | Mémoire vidéo de la GPU |
| **Checkpoint pipeline** | Sauvegarde de l'état du pipeline pour reprise |
| **Bloc SSS** | Sourcing + Scénario + Storyboard — les 3 agents de préparation |
| **Loopback** | Boucle de validation automatique qui relance si la qualité est insuffisante |
| **Handoff** | Transfert de données entre deux blocs du pipeline |

---

## FICHIERS CLÉS DU PROJET

| Fichier | Rôle |
|---|---|
| `launcher.py` | Interface graphique principale |
| `maestro.py` | Chef d'orchestre — coordonne tous les agents |
| `agent_supervisor_v2.py` | Superviseur ComfyUI — gère les jobs de génération |
| `Combined_V35_API.json` | Workflow ComfyUI fusionné (Advanced + Detailer) |
| `config.json` | Jobs batch pour la production ComfyUI seule |
| `settings.json` | Préférences utilisateur (thème, paramètres, sash position...) |
| `agents/sourcing.py` | Agent de veille web (Reddit, RSS, Google Trends) |
| `agents/scenario.py` | Agent scénariste + Script Doctor |
| `agents/storyboard.py` | Agent storyboard → shot list |
| `agents/critic.py` | Agent critique — valide les handoffs inter-blocs |
| `agents/watchdog.py` | Watchdog — surveillance VRAM et cohérence frames |
| `agents/obs_agent.py` | Agent OBS Studio |
| `agents/capture.py` | Module capture Elgato + webcam |
| `agents/comfy_memory.py` | Gestion mémoire RTX 5080 |
| `agents/checkpoint_manager.py` | Sauvegarde et reprise des travaux |
| `agents/sav_agent.py` | Agent SAV ComfyUI |
| `agents/ollama_bridge.py` | Bridge LLM (Claude/GPT/Gemini/Ollama) |
| `llama_chat.py` | Interface chat Llama standalone |
| `workspace/` | Dossier de travail (créé automatiquement) |
| `workspace/checkpoints/` | Sauvegardes des travaux en cours |
| `workspace/archive/` | Images générées archivées |
| `workspace/logs/` | Logs de chaque run |

---

*Document généré le 15/06/2026 — OverLord Pipeline v3.0 Alpha*  
*Pour former une IA sur ce pipeline, ingérer ce document avec `Combined_V35_API.json` et `node_catalog.json`.*

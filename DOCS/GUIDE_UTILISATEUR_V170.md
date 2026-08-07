# GUIDE UTILISATEUR — Ov3rLoRd Pipeline V1.70
## Manuel complet d'utilisation

---

## DÉMARRAGE RAPIDE (5 minutes)

```bash
# 1. Ouvrir un terminal dans D:\OVERLORD\
cd D:\OVERLORD

# 2. Lancer le launcher visuel
python overlord_launcher.py

# 3. OU directement en ligne de commande
python maestro.py --media-type anime --universe "evangelion battle mecha girl"
```

**Ce que vous verrez :**
```
[DIRECTOR] Intent: mode=BALANCE | seuil=73 | arc=wonder
[GPU] Optimisation auto : rtx5080
[SOURCING] Démarrage...
[SCÉNARIO] Script généré : 'Neo-Evangelion: Rebirth'
[STORYBOARD] 8 shots générés
[STYLE] Continuité appliquée à 8 jobs
[QUALITY_GATE] PASS — 71 nœuds
[PROMPT_ENG] 8 jobs enrichis
[SUPERVISOR] Batch started : 8 jobs
[SUPERVISOR] Batch complete : 8/8 successes
[POST-PROD] Pipeline démarré
[REPORTER] Rapport généré
PIPELINE TERMINÉ — duree=~580s | sante=STABLE
```

---

## LAUNCHER VISUEL (overlord_launcher.py)

### Lancement
```bash
python overlord_launcher.py
```

### Interface
- **Boutons colorés** : copient la commande dans le presse-papier au clic
- **Menu catégories** : Pipeline / Agents / Tests / ComfyUI / Maintenance
- **Thèmes** : DARK (par défaut) / NEON / RED
- **Mode CONFIG** (cadenas) : cliquer sur un bouton ouvre la fenêtre de personnalisation

### Personnaliser un bouton
1. Cliquer **🔓 CONFIG** (devient 🔒 rouge)
2. Cliquer le bouton à modifier
3. Changer le libellé, la commande, ou cliquer **📁 Parcourir .py**
4. Sauvegarder → config persistante dans `workspace/launcher_config.json`

### Utilisation
1. Ouvrir le launcher
2. Cliquer le bouton de la commande souhaitée → copiée dans le presse-papier
3. Coller dans votre terminal : `Ctrl+V` → `Enter`

---

## COMMANDES MAESTRO

### Syntaxe complète
```bash
python maestro.py
  [--media-type anime|manga|comics|3d|photoreal|art|game|short|film]
  [--universe "description de l'univers"]
  [--batch N]                    # N runs séquentiels
  [--from-block sourcing|scenario|storyboard|production|postprod|3d]
  [--use-prompt-library]         # Activer bibliothèque Booru locale
  [--no-prompt-engineer]         # Désactiver upsampling prompts
  [--no-quality-gate]            # Désactiver validation workflow
  [--lora "nom_du_fichier.safetensors"]
  [--episode N]                  # Numéro d'épisode (mémoire narrative)
  [--run-id "identifiant"]       # Forcer un run_id spécifique
```

### Exemples courants

**Run simple :**
```bash
python maestro.py --universe "dragon ball super"
```

**Avec prompt library :**
```bash
python maestro.py --universe "evangelion mecha" --use-prompt-library
```

**3 runs automatiques :**
```bash
python maestro.py --universe "one piece adventure" --batch 3
```

**Reprendre depuis un bloc spécifique :**
```bash
python maestro.py --universe "evangelion" --from-block production
```

**Mode debug (sans les nouveaux agents) :**
```bash
python maestro.py --universe "test" --no-prompt-engineer --no-quality-gate
```

---

## AGENTS AUTONOMES

### Auto Sourcing (arrière-plan)
Collecte les tendances et alimente la bibliothèque de prompts automatiquement.

```bash
# Lancer en arrière-plan (toutes les heures)
start /B python agents\auto_sourcing.py --loop 3600 --universe "evangelion"

# Run unique (test)
python agents\auto_sourcing.py --dry-run --universe "evangelion"

# Voir ce qui sera généré sans sauvegarder
python agents\auto_sourcing.py --dry-run --n-prompts 3
```

### GPU Optimizer
```bash
python agents\gpu_optimizer.py
# → Détecte votre GPU, affiche le profil, applique les paramètres optimaux
```

### Config Manager
```bash
python agents\config_manager.py
# → Affiche toute la configuration centralisée
```

```python
# Modifier un paramètre depuis Python
from agents.config_manager import get_config
c = get_config()
c.set("comfyui.steps", 80)           # Augmenter les steps
c.apply_gpu_preset("rtx5080")         # Appliquer preset RTX 5080
print(c.get_all("comfyui"))           # Voir tous les paramètres ComfyUI
```

### Narrative Memory
```bash
python agents\narrative_memory.py
# → Affiche les personnages mémorisés et les épisodes enregistrés
```

### Agent Registry
```bash
python agents\agent_registry.py
# → Scanne tous les agents, met à jour les manifests, détecte erreurs syntaxe

# Snapshot avant de modifier un agent critique
python -c "from agents.agent_registry import get_registry; get_registry().snapshot('scenario')"

# Rollback si un patch casse quelque chose
python -c "from agents.agent_registry import get_registry; get_registry().rollback('scenario')"
```

---

## CONFIGURATION

### .env (secrets uniquement)
```
# D:\OVERLORD\.env
ANTHROPIC_API_KEY=           # Claude (optionnel)
GROK_API_KEY=xai-VOTRE_CLE  # Grok 4 Fast ($175 gratuits : console.x.ai)
OV_LLM_MODE=offline          # offline | online | auto | grok
OV_OLLAMA_MODEL=mistral      # modèle Ollama local
```

### Activer Grok 4 Fast
1. Créer un compte sur https://console.x.ai
2. Générer une clé API → copier dans `.env` : `GROK_API_KEY=xai-...`
3. Changer le mode : `OV_LLM_MODE=grok`
4. Tester : `python agents\grok_client.py`

### Bibliothèque de prompts personnels
```bash
# Initialiser
python agents\prompt_library.py

# Éditer dans VSCode
code data\prompts\prompts_local.json
```

**Format d'un prompt dans la bibliothèque :**
```json
{
  "id": "001",
  "positive": "masterpiece, best quality, absurdres, 1girl, ...",
  "negative": "bad quality, worst quality, ...",
  "lora": "asuka-langley-soryuu-classic-ponyxl-lora-nochekaiser.safetensors",
  "strength": 0.9,
  "width": 1024,
  "height": 1536,
  "tags": ["evangelion", "action"],
  "source": "personal"
}
```

---

## TESTS

```bash
# Tests rapides (imports + JSON) — ~5 secondes
python test_suite_v170.py --quick

# Tests complets — ~30 secondes
python test_suite_v170.py

# Test pipeline legacy
python test_pipeline.py --quick

# Valider le workflow ComfyUI
python agents\quality_gate.py
```

**Résultat attendu :**
```
══════════════════════════════════════════════════════════
  Ov3rLoRd Test Suite V1.70
══════════════════════════════════════════════════════════
── Imports ─────────────────────────────────────────────────
  ✓ overlord_utils import + mode LLM (12ms)
  ✓ context_bus singleton read/write (3ms)
  ...
  BILAN : 24/24 PASS | 0 FAIL | 8.4s
```

---

## RÉSULTATS ET RAPPORTS

### Où trouver les images
```
D:\OVERLORD\workspace\archive\{run_id}\
ex: workspace\archive\maestro_20260620_061428_prod\
```

### Où trouver les rapports
```
D:\OVERLORD\workspace\reports\
├── 20260620_061428_maestro_20260620_061428.json  ← données complètes
├── 20260620_061428_maestro_20260620_061428.md    ← rapport lisible
└── history.json                                   ← historique 50 runs
```

### Où trouver les scripts générés
```
D:\OVERLORD\workspace\scripts\
└── 20260620_054702_Neo-Evangelion_Harmony_Vanguard.json
```

### Où trouver la vidéo assemblée
```
D:\OVERLORD\workspace\exports\
└── 20260620_061428_Neo-Evangelion.mp4
```

---

## MAINTENANCE

### Procédure avant mise à jour d'un agent
```bash
# 1. Snapshot de sauvegarde
python -c "from agents.agent_registry import get_registry; get_registry().snapshot('nom_agent')"

# 2. Appliquer le patch

# 3. Tester
python test_suite_v170.py --quick

# 4. Si ça casse → rollback immédiat
python -c "from agents.agent_registry import get_registry; get_registry().rollback('nom_agent')"
```

### Nettoyer les checkpoints bloqués
```bash
del /Q D:\OVERLORD\workspace\checkpoints\anime_evangelion_battle_mecha_girl\*
```

### Reset complet (garder les snapshots)
```bash
# NE PAS SUPPRIMER workspace\registry\snapshots\ !
rmdir /S /Q workspace\archive
rmdir /S /Q workspace\reports
rmdir /S /Q workspace\logs
mkdir workspace\archive
mkdir workspace\reports
mkdir workspace\logs
```

---

## RÉSOLUTION DE PROBLÈMES

| Symptôme | Cause probable | Solution |
|----------|----------------|----------|
| `400 Bad Request ComfyUI` | Workflow JSON corrompu | `python agents\quality_gate.py` → auto-fix |
| `Pas de TrendReport -- arret` | Checkpoint corrompu | Supprimer le checkpoint + relancer |
| `JSON invalide (tentative 1/2)` | LLM instable | Normal, retry automatique. Si persistent : `OV_LLM_MODE=grok` |
| `low quality score (0 < 80)` | Images non trouvées par watchdog | Vérifier chemin `D:\Ov3rLoRd AI\ComfyUI\output` |
| `shape invalid for input of size` | VAE corrompu | `vae_name: "taesdxl"` dans workflow JSON |
| `Value not in list: lora_name` | LoRa vide envoyée | AVAILABLE_LORAS dans supervisor — vérifier le fichier |
| Pipeline trop lent | Chargement modèle à froid | Normal pour job 1. S'améliore aux jobs suivants. |
| `Aucune image trouvée` postprod | Mauvais chemin archive | Bus `production.image_dir` — vérifier supervisor patch |

---

## GLOSSAIRE

| Terme | Définition |
|-------|------------|
| **Run** | Exécution complète du pipeline (1 universe → 8 images + vidéo) |
| **Shot** | Une image individuelle dans le storyboard (8 par run) |
| **Job** | La tâche ComfyUI correspondant à un shot |
| **LoRa** | Fichier de fine-tuning qui oriente le style/personnage |
| **Booru tags** | Format de tags Danbooru pour les prompts SDXL anime |
| **Anchor** | Ancre de style (seed base + LoRa) fixée pour tout un run |
| **Bus** | context_bus.py — mémoire partagée entre tous les agents |
| **Quality Gate** | Validation du workflow JSON avant envoi à ComfyUI |
| **Prompt Engineer** | Agent d'upsampling Booru des descriptions de shots |


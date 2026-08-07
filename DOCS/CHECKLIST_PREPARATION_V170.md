# CHECKLIST PRÉPARATION — Ov3rLoRd V1.70
## Liste de préparation ordonnée pour maîtriser le système

---

## PHASE 1 — Installation RTX 5080 (à faire maintenant)

- [ ] Éteindre la machine proprement
- [ ] Installer la RTX 5080
- [ ] Redémarrer → vérifier détection Windows
- [ ] Mettre à jour les drivers NVIDIA (dernière version)
- [ ] Télécharger et installer CUDA 12.x si nécessaire
- [ ] Vérifier dans ComfyUI : `--cuda-device 0` dans la commande de lancement

**Après installation :**
```bash
python agents\gpu_optimizer.py
# Doit afficher : GPU détecté : rtx5080 | VRAM : 16GB
# et patcher automatiquement Combined_V35_API.json (80 steps, 1344×1984)
```

---

## PHASE 2 — Déploiement V1.70 (après GPU)

Ordre de déploiement obligatoire :

- [ ] Copier `maestro.py` → `D:\OVERLORD\`
- [ ] Copier `agent_supervisor_v2.py` → `D:\OVERLORD\`
- [ ] Copier `Combined_V35_API.json` → `D:\OVERLORD\`
- [ ] Copier `overlord_launcher.py` → `D:\OVERLORD\`
- [ ] Copier `test_suite_v170.py` → `D:\OVERLORD\`
- [ ] Copier dans `D:\OVERLORD\agents\` :
  - [ ] `scenario.py`
  - [ ] `overlord_utils.py`
  - [ ] `postprod.py`
  - [ ] `grok_client.py`
  - [ ] `prompt_library.py`
  - [ ] `auto_sourcing.py`
  - [ ] `prompt_engineer.py`
  - [ ] `quality_gate.py`
  - [ ] `session_reporter.py`
  - [ ] `config_manager.py`
  - [ ] `agent_registry.py`
  - [ ] `gpu_optimizer.py`
  - [ ] `style_continuity.py`
  - [ ] `narrative_memory.py`

---

## PHASE 3 — Première exécution post-installation

```bash
# 1. Tests rapides
python test_suite_v170.py --quick
# Attendu : tous PASS

# 2. Détecter le GPU
python agents\gpu_optimizer.py
# Attendu : rtx5080 détecté, workflow patché

# 3. Initialiser la bibliothèque de prompts
python agents\prompt_library.py
# Crée data\prompts\prompts_local.json

# 4. Scanner les agents
python agents\agent_registry.py
# Attendu : tous les agents listés, 0 erreur syntaxe

# 5. Premier run
python maestro.py --media-type anime --universe "evangelion battle mecha girl"
# Attendu : Pipeline terminé, 8/8 images
```

---

## PHASE 4 — Configuration Grok (optionnel mais recommandé)

- [ ] Créer compte sur https://console.x.ai
- [ ] Générer une clé API (onglet "API Keys")
- [ ] Ajouter dans `D:\OVERLORD\.env` :
  ```
  GROK_API_KEY=xai-VOTRE_CLE_ICI
  OV_LLM_MODE=grok
  ```
- [ ] Tester : `python agents\grok_client.py`
- [ ] Si OK : les scénarios seront générés par Grok 4 Fast (meilleur que mistral local)

---

## PHASE 5 — Télécharger sdxl_vae.safetensors (qualité maximale)

- [ ] Aller sur https://huggingface.co/stabilityai/sdxl-vae
- [ ] Télécharger `sdxl_vae.safetensors` (~335MB)
- [ ] Copier dans `D:\Ov3rLoRd AI\ComfyUI\models\vae\`
- [ ] Dans `D:\OVERLORD\agents\config_manager.py`, changer le default :
  `"comfyui.vae": "sdxl_vae.safetensors"`
- [ ] Ou directement dans `Combined_V35_API.json` : node 100, `"vae_name": "sdxl_vae.safetensors"`

---

## PHASE 6 — Alimentation de la bibliothèque de prompts

- [ ] Lancer l'auto sourcing en arrière-plan :
  ```bash
  start /B python agents\auto_sourcing.py --loop 3600 --universe "evangelion mecha anime"
  ```
- [ ] Ajouter tes propres prompts dans `data\prompts\prompts_local.json`
- [ ] Format : voir section Bibliothèque dans GUIDE_UTILISATEUR_V170.md
- [ ] Tester : `python maestro.py --universe "evangelion" --use-prompt-library`

---

## PHASE 7 — Snapshot global de sécurité

```bash
# Après tout déploiement stable
python -c "
from agents.agent_registry import get_registry
reg = get_registry()
reg.scan()
reg.snapshot_all()
print('Snapshot global OK')
"
```

---

## OBJECTIFS D'APPRENTISSAGE PAR SEMAINE

### Semaine 1 — Maîtriser les commandes de base
- [ ] Lancer 10 runs complets avec des univers différents
- [ ] Observer les logs et identifier les blocs lents
- [ ] Personnaliser 5 boutons dans le launcher
- [ ] Ajouter 10 prompts personnels dans `prompts_local.json`

### Semaine 2 — Comprendre les agents
- [ ] Lire `scenario.py` en entier (identifier le retry et le fallback)
- [ ] Lire `prompt_engineer.py` (comprendre l'upsampling Booru)
- [ ] Lire `style_continuity.py` (comprendre les seeds progressifs)
- [ ] Demander une analyse de performance : "pourquoi tel job prend X secondes ?"

### Semaine 3 — Optimisation
- [ ] Comparer qualité image : taesdxl vs sdxl_vae
- [ ] Comparer scénarios : mistral vs Grok 4 Fast
- [ ] Ajuster les paramètres dans config_manager pour vos LoRas
- [ ] Tester `--batch 5` → analyser le rapport de session

### Semaine 4 — Contribution au code
- [ ] Identifier un agent à améliorer
- [ ] Faire un snapshot avant
- [ ] Appliquer une modification
- [ ] Tester et valider
- [ ] Documenter dans ADR si décision architecturale

---

## QUESTIONS À POSER À CLAUDE EN PRIORITÉ

Les analyses proactives que vous n'avez pas encore demandées :

1. "Analyse les logs de la dernière session et dis-moi quels blocs prennent le plus de temps."
2. "Pourquoi le job 1 est 3× plus lent que le job 7 ? Comment corriger ça ?"
3. "Génère les tests unitaires pour quality_reviewer.py une fois que je l'aurai créé."
4. "Fais un diagramme de séquence de ce que fait maestro.py lors d'un run complet."
5. "Analyse les dépendances circulaires dans mes agents via agent_registry."
6. "Comment réduire l'empreinte VRAM pendant la génération ? Mon RTX 5080 a 16GB mais le modèle charge parfois à 90%."
7. "Génère quality_reviewer.py selon l'architecture section 6 de ARCHITECTURE_GANTT_PERT_5S.md."


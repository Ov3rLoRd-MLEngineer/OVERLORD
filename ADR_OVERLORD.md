# ADR — Architecture Decision Records
## Ov3rLoRd Pipeline — Décisions & Justifications

**Version :** V1.70  
**Format :** ADR (Architecture Decision Record) — chaque décision documentée avec contexte, décision, conséquences, et alternatives rejetées.

---

## ADR-001 — agent_supervisor_v2.py à la racine (pas dans agents/)

**Statut :** Accepté  
**Date :** 20/06/2026

**Contexte :** Le supervisor est le point de contact direct avec ComfyUI. Il doit être exécutable standalone (`python agent_supervisor_v2.py`) sans résoudre les imports relatifs du dossier `agents/`.

**Décision :** Le fichier reste à `D:\OVERLORD\agent_supervisor_v2.py`.

**Conséquences :**
- Import depuis maestro.py : `import agent_supervisor_v2 as supervisor` (fonctionne depuis la racine)
- Risque : doublon potentiel si une copie existe dans `agents/`. Solution : ne jamais créer `agents/agent_supervisor_v2.py`.
- Avantage : exécution directe pour tests manuels sans `cd agents/`

**Alternatives rejetées :**
- Dans `agents/` avec `sys.path` manipulation → fragile
- Module Python avec `__init__.py` → complexité inutile au stade actuel

---

## ADR-002 — VAE taesdxl au lieu de sdxl_vae.safetensors

**Statut :** Temporaire (à réviser après re-DL)  
**Date :** 20/06/2026

**Contexte :** `sdxl_vae.safetensors` présent dans `D:\Ov3rLoRd AI\ComfyUI\models\vae\` est corrompu. Erreur : `shape '[512, 512, 3, 3]' is invalid for input of size 327523`. Taille fichier anormalement petite (< 100MB vs attendu ~335MB).

**Décision :** Utiliser `taesdxl` (Tiny AutoEncoder SDXL, intégré ComfyUI) jusqu'à re-téléchargement.

**Conséquences :**
- Images légèrement moins nettes (compression VAE moins précise)
- Pipeline fonctionnel à 100%
- Pas de téléchargement supplémentaire requis

**Action requise :** Re-DL `sdxl_vae.safetensors` (~335MB) depuis HuggingFace `stabilityai/sdxl-vae`, puis dans `Combined_V35_API.json` : `node 100 > vae_name = "sdxl_vae.safetensors"`

---

## ADR-003 — dpmpp_2m karras comme sampler par défaut

**Statut :** Accepté  
**Date :** 20/06/2026

**Contexte :** Choix du sampler pour fabricatedXL_v70 avec LoRas ponyXL.

**Décision :** `dpmpp_2m` + scheduler `karras` à 50 steps, cfg 6.0.

**Justification :**
- dpmpp_2m karras = meilleur ratio qualité/vitesse pour SDXL en 2025/2026
- Convergence rapide : bon résultat à 20 steps, excellent à 50
- Compatible avec les LoRas ponyXL nochekaiser (validé en tests)
- cfg 6.0 : évite la sur-saturation typique des modèles anime

**Alternative pour RTX 5080+ :** passer à `dpmpp_2m_sde` karras à 80 steps — légèrement plus varié, meilleur sur les détails fins.

**Ne pas utiliser :** euler_ancestral → trop aléatoire pour la continuité entre frames.

---

## ADR-004 — Stockage JSON au lieu de SQLite pour le workflow ComfyUI

**Statut :** Accepté  
**Date :** 20/06/2026

**Contexte :** Le workflow ComfyUI (`Combined_V35_API.json`) est chargé et patché à chaque run.

**Décision :** Fichier JSON plat à la racine, modifié directement par `agent_supervisor_v2.py`.

**Justification :**
- ComfyUI API attend un JSON, pas autre chose
- Éditable manuellement dans VSCode pour debug rapide
- Quality Gate valide le fichier avant chaque envoi
- Backup automatique dans `workspace/backups/` via `patch_workflow_v35.py`

**Conséquence :** Si le fichier est corrompu entre deux runs, Quality Gate auto-fixe. Si non récupérable, restaurer depuis `workspace/backups/`.

---

## ADR-005 — Config centralisée SQLite (config_manager.py)

**Statut :** Accepté — V1.70  
**Date :** 20/06/2026

**Contexte :** 95+ agents lisaient tous `.env` indépendamment. Pas de source de vérité unique. Modification d'un paramètre nécessitait d'éditer `.env` ET potentiellement plusieurs fichiers Python.

**Décision :** SQLite (`workspace/config.db`) comme source de vérité. `.env` reste souverain uniquement pour les **secrets** (API keys).

**Hiérarchie :** defaults DEFAULTS.py < config.db < .env < kwargs runtime

**Conséquence :** Tout agent doit importer `get_config()` pour lire ses paramètres. Le `.env` n'est plus le seul endroit de config.

---

## ADR-006 — Prompt engineering en anglais obligatoire

**Statut :** Accepté  
**Date :** 20/06/2026

**Contexte :** Ollama/mistral en mode offline produisait du JSON invalide quand les prompts system/user étaient en français. Apostrophes, accents et structures de phrases françaises perturbaient la génération JSON stricte.

**Décision :** Tous les prompts LLM (system + user) en anglais. Logs humains en français.

**Résultat observé :** Taux d'échec JSON invalide passé de ~40% à ~10% (retry x2 couvre le reste).

**Exception :** TTS gTTS utilise `lang="fr"` pour la voix — le contenu audio reste en français.

---

## ADR-007 — shutil.copy2 au lieu de rename pour l'archive images

**Statut :** Accepté  
**Date :** 20/06/2026

**Contexte :** Version initiale utilisait `img.rename(dest)` pour archiver les images depuis `ComfyUI/output/` vers `workspace/archive/`. Résultat : les originaux disparaissaient du dossier ComfyUI, rendant les runs suivants sans images à scorer.

**Décision :** `shutil.copy2(src, dest)` — copie avec préservation métadonnées. Les originaux restent dans `ComfyUI/output/`.

**Conséquence :** Espace disque doublé pour les images. Acceptable (images ~500KB-2MB chacune, 8 par run = ~16MB max par run).

---

## ADR-008 — Seeds progressifs pour la continuité visuelle

**Statut :** Accepté — V1.70  
**Date :** 20/06/2026

**Contexte :** Watchdog détectait des ruptures de style entre frames (drift > 0.4) causées par des seeds totalement aléatoires et des LoRas différentes par job.

**Décision :** `seed = base_seed + (i * 137)` — base fixe par run, incrément de 137 (nombre premier pour bonne distribution).

**Justification :** Seeds trop proches créent des images similaires (pas de variation). Seeds complètement aléatoires créent des ruptures. 137 de gap = variation contrôlée sans rupture.

**Règle :** LoRa identique sur tous les shots d'un run. Palette couleur injectée dans tous les prompts.

---

## ADR-009 — Fallback script en cas d'échec scénario

**Statut :** Accepté  
**Date :** 20/06/2026

**Contexte :** Version V1.49 : si le LLM renvoyait du JSON invalide après 2 tentatives, le pipeline s'arrêtait complètement (`Scenario echoue : json_parse_failed — arret`).

**Décision :** `_fallback_script()` génère un script minimal structuré valide. Le pipeline ne s'arrête JAMAIS sur un échec scénario.

**Conséquence :** Le flag `_fallback: true` est tracé dans `_meta` et sur le bus. Le reporter signale si le fallback a été utilisé.

---

## ADR-010 — Mémoire narrative persistante entre épisodes

**Statut :** Accepté — V1.70  
**Date :** 20/06/2026

**Contexte :** Chaque run était indépendant. Les personnages pouvaient changer de caractère entre épisodes. Impossible de construire une série cohérente.

**Décision :** `workspace/narrative/memory.json` persistant entre tous les runs. Extrait automatiquement les personnages et événements de chaque script généré.

**Injection :** Le contexte narratif des 3 derniers épisodes est injecté dans le prompt scénario du run suivant. Le LLM peut ainsi référencer les événements précédents.

**Limite :** Dépend de la qualité d'extraction du LLM. Si le scénario ne nomme pas explicitement les personnages établis, la continuité est partielle.


# kohya_ss vs `agents/production_image/lora_trainer.py` — 2026-08-09

Vérification demandée avant d'installer `kohya_ss` en préparation de H-007 (`DOCS/HERMES/`) : est-ce que `agents/production_image/lora_trainer.py`, déjà présent dans le dépôt (rank 32 par défaut), suffit, ou est-ce que `kohya_ss` apporte quelque chose que ce script n'a pas ?

## Verdict : `kohya_ss` n'est PAS redondant — c'est le moteur d'entraînement, `lora_trainer.py` n'en a aucun

Lecture complète de `agents/production_image/lora_trainer.py` (383 lignes) : le script ne contient **aucune boucle d'entraînement** (pas de `torch`, `diffusers`, `peft` importé nulle part). Ses fonctions :

| Fonction | Rôle réel |
|---|---|
| `prepare_dataset()` | Copie les images sources + écrit les captions `.txt` avec le trigger word |
| `auto_tag_images()` | Tagging WD14 (ou fallback LLM) |
| `build_kohya_config()` | Génère un JSON de config **au format attendu par kohya_ss** |
| `train_lora()` | `subprocess.Popen([sys.executable, KOHYA_PATH / "train_network.py", ...])` — lance kohya_ss comme process externe et parse sa sortie pour la progression |
| `integrate_lora()` | Copie le `.safetensors` produit vers `ComfyUI/models/loras/` |

`train_lora()` (ligne 198-202) échoue explicitement et proprement si `D:/kohya_ss/train_network.py` n'existe pas :
```python
train_script = KOHYA_PATH / "train_network.py"
if not train_script.exists():
    log.error(f"[TRAINER] kohya_ss non trouvé : {KOHYA_PATH}")
    log.error("[TRAINER] Installer : git clone https://github.com/bmaltais/kohya_ss")
    return None
```

**Conclusion** : `lora_trainer.py` = orchestrateur (dataset, captions, config, intégration). `kohya_ss` = moteur (le vrai entraînement LoRA SDXL). Les deux sont complémentaires, pas alternatifs. Sans `kohya_ss`, `lora_trainer.py` prépare tout correctement puis échoue proprement à l'étape training — c'est exactement le comportement observé avant cette installation (`D:/kohya_ss` absent).

## Installation effectuée

- `git clone https://github.com/bmaltais/kohya_ss.git` → `D:\kohya_ss\` (hors du dépôt `D:\OVERLORD`, comme ComfyUI).
- Submodule `sd-scripts` initialisé (`git submodule update --init --recursive`).
- **Venv isolé** créé dans `D:\kohya_ss\.venv\` — **PAS** dans l'environnement `py -3.12` partagé du dépôt. Raison : incident du 2026-08-09 où `pip install scenedetect` avait fait sauter numpy à 2.5.1 et cassé numba/scipy dans cet environnement partagé (voir mémoire `python312-numpy-shared-env-pitfall`) ; `kohya_ss` a des dépendances beaucoup plus lourdes/pinnées (torch 2.7.0+cu128, xformers, tensorflow, bitsandbytes) — risque de collision bien plus élevé.
- **Python 3.11, pas 3.12** pour ce venv — écart assumé et documenté : `D:\kohya_ss\.python-version` déclare `3.11` en amont (version testée/supportée par le projet upstream). La règle "Python 3.12 obligatoire" du `CLAUDE.md` du dépôt s'applique aux scripts qui **touchent le dépôt OVERLORD** ; `kohya_ss` est un outil externe invoqué en subprocess (même statut que ComfyUI), pas un script du dépôt — forcer 3.12 sur un outil dont l'upstream cible 3.11 aurait été un risque de compatibilité inutile sur une stack déjà lourde (torch/xformers/bitsandbytes).
- Dépendances installées via `pip install -r requirements_pytorch_windows.txt` (chaîne vers `requirements_windows.txt` puis `requirements.txt`) : torch 2.7.0+cu128, torchvision, xformers, bitsandbytes, tensorboard, tensorflow, onnxruntime-gpu + reste des deps kohya_ss.
- **Aucun run lancé** — ni `setup.bat`/`gui.bat` (installateur interactif, évité pour rester scriptable et ne rien lancer sur GPU), ni entraînement, ni `accelerate config`. Installation des dépendances uniquement.
- RTX 5080 (GPU 0) confirmée libre avant install (`nvidia-smi --query-compute-apps`, aucun process dessus) ; RTX 5060 Ti touchée uniquement par Ollama (déjà en cours, non affecté).

## Installation vérifiée fonctionnelle

```
D:\kohya_ss\.venv\Scripts\python.exe -c "import torch; print(torch.cuda.is_available(), torch.cuda.device_count())"
# -> True 2  (RTX 5080 + RTX 5060 Ti toutes deux visibles)
```
`torch 2.7.0+cu128`, `xformers 0.0.30`, `tensorflow 2.19.1`, `onnxruntime-gpu 1.19.2`, `bitsandbytes` (via `requirements.txt`) tous installés. Vérification limitée à `torch.cuda.is_available()` (négligeable en mémoire GPU, libéré immédiatement) — aucun entraînement, aucun chargement de modèle.

## Reste à faire avant un vrai run d'entraînement (hors scope de cette tâche — non corrigé ici)

Deux écarts concrets trouvés entre ce que `lora_trainer.py` suppose et la structure réelle de ce checkout de `kohya_ss` (repo upstream réorganisé depuis l'écriture de `lora_trainer.py`) :

1. **Chemin du script d'entraînement faux.** `KOHYA_PATH = Path("D:/kohya_ss")` et `train_script = KOHYA_PATH / "train_network.py"` (ligne 64 et 198) — mais ce fichier **n'existe pas** à cet emplacement. Les scripts d'entraînement vivent maintenant dans le submodule : `D:\kohya_ss\sd-scripts\train_network.py`. La racine `D:\kohya_ss\` ne contient plus qu'un `kohya_gui.py` (interface Gradio) et `local_train.py`. Même une fois `kohya_ss` installé, `lora_trainer.py::train_lora()` échouerait encore au check `train_script.exists()` sans corriger ce chemin.
2. **Script generique vs SDXL.** `sd-scripts/train_network.py` est le script LoRA générique (SD1.5/2.x). Le checkpoint cible ici est `fabricatedXL_v70.safetensors` (SDXL) — le script correct serait `sd-scripts/sdxl_train_network.py`, qui a des arguments différents (VAE séparé, double text encoder). `lora_trainer.py` ne fait actuellement aucune distinction.
3. **Interpréteur** (déjà noté) : `train_lora()` utilise `sys.executable` (l'interpréteur de l'appelant, probablement `py -3.12`) au lieu de `D:\kohya_ss\.venv\Scripts\python.exe` (le venv isolé fraîchement installé, qui a réellement torch/xformers/etc.).
4. `accelerate config` (une fois, interactif ou via config générée) — pas fait, pas nécessaire pour l'installation seule.

Ces trois premiers points rendraient un `--auto`/`train_lora()` réel non fonctionnel tel quel, **indépendamment du blocage H-003** — à corriger quand H-007 sera vraiment lancé, pas maintenant (hors scope : cette tâche était "installer kohya_ss", pas "adapter lora_trainer.py").

H-007 reste bloqué sur H-003 (aucun `.vrm`) même avec `kohya_ss` installé — voir `DOCS/HERMES/REGISTRE.md`.

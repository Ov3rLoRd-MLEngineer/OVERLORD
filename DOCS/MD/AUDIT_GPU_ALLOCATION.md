# Audit allocation GPU — 2026-08-08

Périmètre : cartographie de ce qui tourne sur CUDA:0 (RTX 5080) vs CUDA:1
(RTX 5060 Ti) à travers ComfyUI, les scripts Python du pipeline, et Ollama.
Base pour les tâches 2/4/5 (device splitting ComfyUI, workflow SVI+VACE,
orchestration parallèle maestro.py).

## 1. Cartographie physique

```
nvidia-smi -L
GPU 0: NVIDIA GeForce RTX 5080     (UUID: GPU-b4d632fb-e2f1-a6c5-5d66-792dd80d82bf)
GPU 1: NVIDIA GeForce RTX 5060 Ti  (UUID: GPU-cb196733-cc69-2fae-2eed-f363c2fd2219)
```

Le pinning multi-carte de ce dépôt se fait **exclusivement par UUID**, jamais
par index (`0`/`1`) — convention déjà actée dans [[ollama-gpu-pinning]] et
confirmée cohérente partout où elle est utilisée (`_launch_comfyui_5080.bat`,
`_launch_comfyui_5060ti.bat`).

**Découverte annexe, à vérifier par l'utilisateur** : `nvidia-smi
--query-compute-apps` liste au moment de cet audit les processus desktop
(`explorer.exe`, `msedge.exe`, `SearchApp.exe`, `claude.exe`, ...) sur
`GPU-cb196733...`, c'est-à-dire la **RTX 5060 Ti**, pas la 5080. Ceci
contredit la note existante dans `CLAUDE.md` (§Blender Cycles, test du
2026-07-29) qui affirme que la RTX 5080 est "la carte d'affichage
principale". Soit la config d'affichage a changé depuis ce test, soit
l'observation de juillet était déjà imprécise. **Ne pas trancher
unilatéralement ici** — si confirmé, ça change la lecture de "5060 Ti = carte
de service peu chargée" (§ Économie de session, CLAUDE.md) : elle porterait
alors déjà en continu la charge du bureau Windows/compositor en plus de
l'inférence Ollama.

## 2. ComfyUI — architecture actuelle : 2 instances séparées, pas de split intra-graphe

```
_launch_comfyui_5080.bat    → CUDA_VISIBLE_DEVICES=<UUID 5080>  --port 8188 (défaut)
_launch_comfyui_5060ti.bat  → CUDA_VISIBLE_DEVICES=<UUID 5060Ti> --port 8189
```

**Point structurant pour les tâches 2/4/5** : chaque instance ComfyUI est
lancée avec `CUDA_VISIBLE_DEVICES` restreint à **une seule** carte. Depuis
l'intérieur du process, l'autre GPU n'existe tout simplement pas (PyTorch ne
le voit pas). Conséquence directe :

- **Aucun split "device par node" n'est possible à l'intérieur d'un seul
  graphe/workflow JSON** envoyé à une seule instance — ni ComfyUI core, ni
  `comfyui_controlnet_aux` (OpenPose/DepthAnything/Canny/Lineart/Tile,
  utilisés par les preprocesseurs demandés en tâche 2) n'exposent de widget
  "device" par node. Recherché explicitement dans le pack installé
  (`D:\Ov3rLoRd AI\ComfyUI\custom_nodes\comfyui_controlnet_aux`) : aucun
  point d'entrée ne prend un paramètre GPU.
- **Seule exception trouvée** : `ComfyUI-SeedVR2_VideoUpscaler` (utilisé en
  tâche 5, upscale) expose bien un combo natif `device` sur son loader DiT
  (`src/interfaces/dit_model_loader.py:52`, options incluant `cuda:X: Offload
  to another GPU`). Mais cette option ne peut fonctionner que si l'instance
  qui l'exécute voit les deux cartes (donc **pas** sur les deux instances
  actuelles telles que lancées aujourd'hui, toutes deux restreintes à une
  seule carte via `CUDA_VISIBLE_DEVICES`).
- Aucun autre pack multi-GPU (type `ComfyUI-MultiGPU`/`DistributedGPU`)
  n'est installé dans `custom_nodes/`.

**Conclusion pour la tâche 2** : le "device splitting ControlNet sur CUDA:1"
demandé ne peut pas être un simple réglage de node dans le JSON existant. Il
faut soit (a) garder l'architecture 2-instances et faire tourner les
preprocesseurs ControlNet comme **sous-workflow séparé** sur l'instance 8189
(5060 Ti), en repassant les images conditioning à l'instance 8188 (5080) via
l'orchestrateur Python (pattern déjà utilisé par `postprod_inpaint.py`, cf.
§3), soit (b) relancer une instance ComfyUI **sans** restriction
`CUDA_VISIBLE_DEVICES` et installer un pack multi-GPU pour un vrai split
intra-graphe. (a) est cohérent avec l'existant, ne demande aucune nouvelle
dépendance — retenu comme approche par défaut pour la tâche 2, sauf avis
contraire.

`agent_supervisor_v2.py` (`COMFY_URL = "http://127.0.0.1:8188"`, ligne 66)
ne cible en dur que l'instance 5080. Aucune référence en dur au port 8189
trouvée dans ce fichier — la 2e instance n'est utilisée aujourd'hui que par
des scripts spécifiques (`postprod_inpaint.py`), pas par l'orchestrateur
principal.

## 3. Scripts Python — device explicite vs implicite

### Explicitement pinnés (CUDA_VISIBLE_DEVICES en dur ou via argparse)

| Fichier | Carte | Méthode |
|---|---|---|
| `handsegnet/annotate.py` | 5060 Ti | `os.environ.setdefault("CUDA_VISIBLE_DEVICES", "1")` |
| `handsegnet/_hand_box.py` | 5060 Ti | idem, commentaire explicite "GPU1 (5060 Ti)" |
| `handsegnet/prototype_circle_sam.py` / `_multi.py` | 5060 Ti | idem |
| `handsegnet/train.py` | configurable | `--device cuda:0/cuda:1/cpu`, argparse (pas de défaut carte forcé) |
| `footsegnet/controlnet/eval_checkpoint.py` | 5060 Ti | idem + `torch.Generator(device="cuda")` (suit le `CUDA_VISIBLE_DEVICES` déjà posé) |
| `footsegnet/controlnet/diagnostics/sweep_mask_only.py` / `sweep_conditioning_scale.py` | 5060 Ti (fallback) | `setdefault` + doc explicite : `CUDA_VISIBLE_DEVICES=0` attendu en préfixe shell pour forcer 5080 |
| `agents/qc_validation/backfill_sam_scores.py` | 5060 Ti | `setdefault(...,"1")` |
| `agents/production_video/postprod_inpaint.py` | 5060 Ti | `setdefault(...,"1")`, tourne via 2e instance ComfyUI (8189) |
| `agents/postprod_audio/voice_synthesis.py` | dynamique | détection runtime (évite `cuda:0` car ComfyUI dessus), commentaire explicite |
| `DEMO/run_demo_loop.py` | 5080 (subprocess) | `set CUDA_VISIBLE_DEVICES=0` injecté dans une commande `start cmd /k` |
| `workspace/scripts/devstral_agent.py` | 5060 Ti | `setdefault(...,"1")` |
| `workspace/qlora_dataset/training/scripts/train_qlora.py` | 5060 Ti | `setdefault(...,"1")` (trace historique pré-clarification, cf. [[reorg-preferences]]/CLAUDE.md §Économie) |
| `workspace/qlora_dataset/training/scripts/eval_adapter.py` | 5080 | `setdefault(...,"0")` |
| `workspace/qlora_dataset/scripts/train_stage1_thestack.py` / `train_stage1_commitpack.py` / `train_stage2_*.py` / `evaluate_stages_v4.py` / `evaluate_commitpack.py` | 5080 | `setdefault(...,"0")`, convention "run ponctuel bloquant" |
| `_launch_comfyui_5080.bat` | 5080 | `CUDA_VISIBLE_DEVICES=<UUID>` |
| `_launch_comfyui_5060ti.bat` | 5060 Ti | idem, `--port 8189` |
| `launch_ollama.bat` (hors dépôt, cf. [[ollama-gpu-pinning]]) | 5060 Ti | UUID + `OLLAMA_VULKAN=0` |

### Sans device explicite (dépendent de l'environnement au lancement)

- **`footsegnet/controlnet/train_control_lora.py`** — utilise `Accelerate`
  (`accelerator.device`), aucun `CUDA_VISIBLE_DEVICES` posé dans le script :
  si lancé depuis un terminal qui n'a pas positionné la variable, tombe sur
  le défaut système (GPU 0 = 5080). À vérifier avant tout run parallèle avec
  un autre process 5080-only.
- **`agent_supervisor_v2.py` / `maestro.py`** — pas de code torch direct
  (parlent HTTP à ComfyUI), donc pas concernés par le device torch — mais
  `agent_supervisor_v2.py` cible en dur `127.0.0.1:8188` (5080) uniquement
  (§2). Toute parallélisation (tâche 5) devra soit ajouter un 2e client HTTP
  vers `:8189`, soit paramétrer l'URL.
- **Scripts purement HTTP/PIL/numpy sans torch** (`sam_mask_generator.py`,
  `inpaint_corrector.py`, `footsegnet/_pose_box.py`, la plupart des scripts
  `agents/production_video/*` hors `postprod_inpaint.py`, `agents/creative/
  style_dna_generator.py`) — pas de device GPU à gérer directement, ils
  passent par l'API ComfyUI ou par CPU.
- **`unsloth_compiled_cache/*`** — code généré/compilé par Unsloth, utilise
  `os.environ.get("CUDA_VISIBLE_DEVICES", "0")` en lecture seule (jamais en
  écriture) : suit toujours l'environnement du process parent, jamais une
  source de contention indépendante.

## 4. Ollama

Déjà traité et fiabilisé en session antérieure ([[ollama-gpu-pinning]]) :
pinning par UUID obligatoire (`launch_ollama.bat`), `OLLAMA_VULKAN=0`
nécessaire (le backend Vulkan d'Ollama ignore `CUDA_VISIBLE_DEVICES`). Point
de vigilance répété dans ce dépôt (`overlord_utils.py:34`,
`agents/core/overlord_utils.py:34`) : le tray "ollama app.exe" (Startup
Windows) relance son propre `serve` **non pinné** à chaque redémarrage —
donc à vérifier avant tout run qui suppose Ollama sur 5060 Ti uniquement,
pas seulement au premier lancement de session.

## 5. Recommandations pour la suite de la session

1. **Tâche 2** : implémenter le split ControlNet via orchestration 2-instances
   (§2, option a), pas via modification du JSON du workflow existant seul.
2. **Tâche 4/5** : `agent_supervisor_v2.py` et `maestro.py` doivent gagner un
   2e endpoint HTTP configurable (`:8189`) pour dispatcher explicitement —
   actuellement tout est câblé en dur sur 8188.
3. Avant de lancer `train_control_lora.py` en parallèle d'autre chose sur la
   5080, poser `CUDA_VISIBLE_DEVICES` explicitement dans la commande de
   lancement (le script ne le fait pas lui-même).
4. Vérifier manuellement (côté utilisateur, pas actionnable par ce script)
   si la RTX 5060 Ti est bien la carte d'affichage active actuellement (§1)
   — impacte la charge de base réelle de "la carte de service".

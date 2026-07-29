# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Langue

Répondre **toujours en français** dans ce dépôt, quelle que soit la langue du message de l'utilisateur. Le code, les commits et les noms de fichiers peuvent rester en anglais ; seules les réponses conversationnelles doivent être en français.

## What this is

Ov3rLoRd is a personal, single-user pipeline that orchestrates a local **ComfyUI** instance to produce anime-style images/video autonomously: sourcing trends → scenario/script generation (LLM) → storyboard → ComfyUI image/video generation → post-production → publishing. It is not a library or service with external consumers — it's a production tool run locally by one person, developed iteratively session-by-session (see version docs below).

Everything runs on Windows. Two separate roots are involved:
- `D:\OVERLORD\` — this repo: orchestration code, agents, workflows, docs.
- `D:\Ov3rLoRd AI\ComfyUI\` — the ComfyUI install (models, `input/`, `output/`). Not part of this repo but constantly referenced by path. ComfyUI API runs at `http://127.0.0.1:8188`.

## Running things

There is no build step (pure Python + ComfyUI JSON workflows). Python 3.12 specifically is required by recent scripts:

```bash
# Correct interpreter for anything written/touched recently
py -3.12 script.py

# Full pipeline run (older entrypoint, French/English mixed CLI)
python maestro.py --universe "evangelion battle mecha girl"

# Supervisor (talks directly to ComfyUI, run standalone from repo root — see ADR-001)
python agent_supervisor_v2.py

# Tests
python test_suite.py --quick
python test_suite.py
python test_suite.py --agent scenario   # one agent

# GUI / HUD
python overlord_launcher.py        # tkinter desktop launcher
python api_server.py               # Flask HUD at http://localhost:5757
```

`requirements.txt` is minimal (`requests, flask, psutil, Pillow, numpy, gTTS, pydub`) — most "intelligence" is either local Ollama calls or thin wrappers, not heavyweight ML deps in this repo (ComfyUI itself owns the model runtime).

## Architecture

### Orchestration layers
- **`maestro.py`** — original chef d'orchestre: `SOURCING → SCENARIO → STORYBOARD → PRODUCTION → POST-PROD → 3D`. Imports everything from `agents.*` defensively (try/except with fallback stub functions) so a broken/missing agent degrades instead of crashing the whole run.
- **`agent_supervisor_v2.py`** — the industrial orchestrator that actually talks to the ComfyUI HTTP API, manages state machine, retries, image archiving, notifications. Deliberately kept at repo root, not inside `agents/`, so it can run standalone without relative-import gymnastics (see `ADR_OVERLORD.md` ADR-001 — do not move it into `agents/`).
- **`agents/`** — ~150 individual agent modules (sourcing, scenario, storyboard, quality gate/reviewer, prompt engineering, pose/mask/inpaint tooling, style continuity, narrative memory, GPU/thermal management, publishing, etc.). Each is designed to be optional/replaceable; callers wrap imports in try/except and fall back to stub behavior if a module fails to import.
- **`agents/context_bus.py`** — thread-safe singleton pub/sub-ish key/value bus (`get_bus().write(key, value, agent_id=, confidence=)` / `.read(key)`) used for inter-agent communication, persisted to `workspace/context_bus/bus_state.json`.
- **`agents/config_manager.py`** — centralized config: `from agents.config_manager import cfg; cfg.get("comfyui.steps", 50)`. Backed by SQLite at `workspace/config.db`. Precedence: `DEFAULTS (in-code) < config.db < .env < runtime kwargs`. `.env` stays authoritative only for **secrets** (API keys) — see ADR-005. GPU-specific overrides live in `GPU_PRESETS` in the same file.
- **`workspace/`** — all runtime state and outputs: `archive/`, `logs/`, `context_bus/`, `narrative/`, `config.db`, `state.json`/`pipeline_state*.bak`, `reports/`, etc. This is the pipeline's working directory, distinct from the ComfyUI output directory.

### ComfyUI workflow files
ComfyUI workflows are stored as exported API-format JSON at the repo root (e.g. `Advanced_QwenVL_V35*.json`, `animatediff_sdxl_cn_test*.json`, `Combined_V35_API.json`). These are patched programmatically (node IDs are hardcoded — see the `ADV_*`/`DET_*` node-id constants near the top of `agent_supervisor_v2.py`) rather than rebuilt from scratch. Node IDs are stable per workflow file; if you regenerate a workflow from the ComfyUI UI, node IDs can shift and every constant referencing them must be re-checked.

Numbered/lettered `_PIPELINE_PATCHED*`, `*_v2`, `*_v3` files and the many root-level `patch_*.txt` / `PATCH_*.txt` files are point-in-time patch outputs kept for traceability — treat the highest version number as current, older ones as history, not as alternatives to pick between.

**Prompt-upsampling ban list (hallucination guard)** : le seul système d'upsampling de prompt de type TIPO/DanTagGen du dépôt est le node `AILab_QwenVL_PromptEnhancer` (`custom_system_prompt`, widget index 7 — vérifié dans `AILab_QwenVL_PromptEnhancer.py::process()`, `base_instruction = custom_system_prompt.strip() or ...`), actuellement en `mode: 4` (bypass) partout où il apparaît.

Fichier **réellement actif** : `Advanced_QwenVL_V35.json` (racine, sans suffixe — tracké en git depuis le commit initial) est chargé en dur par `agents/workflow_controller.py` (`ADVANCED_WF`), exécutable en CLI manuel (`python agents/workflow_controller.py --pass ...`, hors chaîne automatisée maestro/supervisor). C'est ce fichier qui a reçu la section "Ban List" (`holding|object|cup|phone|cellphone|camera|bottle|weapon|gun`, ajoutée le 2026-07-30) — persistera tant qu'il n'est pas régénéré depuis l'UI ComfyUI (auquel cas re-appliquer la section). **Non câblé** dans le générateur automatique de HandSegNet (`generate_dataset.py` construit le prompt directement depuis les wildcards → `CLIPTextEncode`, sans étage LLM).

`Advanced_QwenVL_V35_PIPELINE_PATCHED_v3.json` (patché le 2026-07-29, AVANT la correction de portée ci-dessus) n'est référencé nulle part dans le code — fix appliqué au mauvais fichier initialement, corrigé.

`Advanced_QwenVL_V35_ORIGINAL.json` — comparaison nœud-par-nœud confirmée identique à `Advanced_QwenVL_V35.json` sur les 208 nœuds SAUF ce même node QwenVL (ban list absente) : c'est le snapshot pré-patch du même pipeline, pas un pipeline différent. Conservé à la demande explicite de l'utilisateur (base de référence pour tests en cours) — **pas encore protégé par la ban list**, décision volontairement laissée à l'utilisateur plutôt qu'appliquée unilatéralement (cf. rapport de session 2026-07-30).

`_PIPELINE_PATCHED.json`/`_PATCHED_v2.json`/`_PATCHED_v3.json` : candidats confirmés à la suppression par l'utilisateur (non référencés dans le code) — pas supprimés, en attente d'une action explicite de suppression.

### Decisions that constrain future changes
Many of these are logged formally in `ADR_OVERLORD.md` — read it before changing sampler defaults, storage strategy, config precedence, or seed strategy. The highlights, some superseded by later session logs (`CONTEXTE_OVERLORD_V2xx.md`, latest is highest number):
- `taesdxl` is the VAE in use (the real `sdxl_vae.safetensors` was corrupted; ADR-002) — don't swap this without checking whether it's been re-downloaded.
- Default sampler is `dpmpp_2m` + `karras`; `euler_ancestral` is explicitly avoided for multi-frame continuity (ADR-003) — except the AnimateDiff test workflow currently uses `euler_ancestral`/`normal` deliberately (see `ADDENDUM_WORKFLOW_ANIMATEDIFF.md`).
- Seeds for a run use `base_seed + i * 137` for controlled variation without visual drift between frames (ADR-008).
- Scenario/script generation always succeeds — `_fallback_script()` guarantees the pipeline never hard-stops on an LLM/JSON failure (ADR-009).
- LLM prompts (system + user) must be written in English even though logs/UI/TTS are French — French prompts measurably increased invalid-JSON rates from Ollama/Mistral (ADR-006).
- Image archiving uses `shutil.copy2`, never `rename`/move, so ComfyUI's own `output/` folder is never emptied by the pipeline (ADR-007).
- SAM-based masking: images must be composited onto a white background before `SAMPreprocessor` — passing raw RGBA silently fails in ~0.02s with no output. Mask convention is **black = regenerate, white = preserve** (confirmed via ComfyUI MaskEditor).
- AnimateDiff must use `ADE_AnimateDiffLoaderGen1` (Gen2 is unavailable on this machine).

### Session context docs
`CONTEXTE_OVERLORD_V*.md` files (V150 through the current highest number) are session handoff notes — each captures in-progress bugs, what was just fixed, and next steps at the time it was written. When resuming multi-session work, read the **highest-numbered** one first; treat older ones as historical record only, since defaults and conventions get superseded (e.g. VAE, sampler, checkpoint choices evolve across sessions and are only trustworthy as of the date at the top of each file). `ADDENDUM_*.md` files are supplements meant to be read alongside a specific `CONTEXTE_*` file (named in the addendum's own header).

### Repo hygiene notes
- Root contains many one-off `fix_*.py`, `scan_*.py`, `_peek*.py` scripts and stray zero-byte files (`git`, `python`, `logging.Logger`) left over from earlier debugging sessions — these are not part of any import graph; don't treat their presence as significant, and don't assume a same-named file is "the" implementation without checking `agents/` first (duplicate filenames exist between root and `agents/`, e.g. `reference_aligner_v2.py`, `invert_lineart.py`, `patcher.py` — root's `patcher.py` is V1.1 (supports two bundle formats), `agents/patcher.py` is the older V1.0, root is current).
- `agents/` also contains vendored third-party packages (`requests/`, `urllib3/`, `certifi/`, `idna/`, `charset_normalizer/`) alongside the actual agent modules — don't confuse these with project code when searching.

## Emplacements clés

Index des fichiers les plus souvent recherchés en début de session, pour éviter un aller-retour de recherche. Chemins vérifiés depuis `D:\OVERLORD\` ; ignorer tout chemin identique sous `.claude/worktrees/` ou `BACKUP/` (copies non fusionnées ou obsolètes, jamais la version courante).

**SegNets** (le même trio existe dans chacun de `footsegnet/`, `handsegnet/`, `bodysegnet/`, `facesegnet/`) :
- `<module>/annotate.py` — interface tkinter d'annotation manuelle (pré-remplissage SAM + brush/fill), voir `--by-confidence` pour trier par score SAM croissant
- `<module>/batch_premask.py` — pré-masquage automatique (bbox pose + SAM + fallback grounding VLM)
- `<module>/build_coco.py` — export du dataset annoté au format COCO
- `<module>/dataset/premasks/_provenance.csv` — journal de provenance par image (box_source, status, mask_pct, sam_score) ; lu par `agents/segnet_premask.py::load_sam_scores()`

**Control-LoRA FootSegNet → SDXL** (`footsegnet/controlnet/`, voir son propre `README.md` pour le flux complet) :
- `footsegnet/controlnet/prepare_dataset.py` — génération + pré-masque + assemblage des paires
- `footsegnet/controlnet/quality_sort.py` — tri exploitable / à corriger / à exclure (couverture, box_source, fragmentation de masque)
- `footsegnet/controlnet/train_control_lora.py` — entraînement (diffusers + peft)
- `footsegnet/controlnet/route_by_sam_confidence.py` — routage manuel/auto par seuil de score SAM natif
- `footsegnet/dataset/premasks/route_auto_sort.txt` / `route_manual_review.txt` — listes de routage du lot Control-LoRA (stems, un par ligne)
- `footsegnet/dataset/premasks/prepare_review_folder.py` + `README.md` — prépare un dossier de liens physiques pour ouvrir uniquement les stems de `route_manual_review.txt` dans `annotate.py`

**Pipeline core** :
- `maestro.py` — orchestrateur historique (SOURCING→SCENARIO→STORYBOARD→PRODUCTION→POST-PROD→3D)
- `agent_supervisor_v2.py` — orchestrateur industriel (parle à l'API ComfyUI), reste à la racine (ADR-001)
- `agents/director.py` — Le Réalisateur (mise en scène/direction narrative)
- `agents/context_bus.py` — bus pub/sub inter-agents (`get_bus().write()/.read()`)
- `agents/segnet_premask.py` — logique partagée de pré-masquage (`load_sam_scores`, `clean_mask`, `fill_mask_holes`, `run_batch`) derrière les 4 `batch_premask.py`
- `patcher.py` (racine, V1.1, courant) — agent de patch find/replace ou CREATE/UPDATE ; ne pas confondre avec `agents/patcher.py` (V1.0, plus ancien)
- `ADR_OVERLORD.md` — décisions d'architecture formelles (sampler, VAE, seeds, config...)

**Config** :
- `config.py` (racine) — chemins/constantes partagés (`FOOTSEGNET_ROOT`, `SAM_CHECKPOINT`, etc.), importé par la plupart des scripts SegNet/Control-LoRA
- `agents/config_manager.py` — config centralisée (`cfg.get(...)`), précédence DEFAULTS < `workspace/config.db` < `.env` < kwargs runtime
- `.env` (racine) — secrets/clés API uniquement (ADR-005)

**Non trouvé à l'emplacement attendu** : `agents/llm_router.py`, mentionné dans un doc de session antérieur, n'existe pas dans l'arborescence actuelle — seulement dans le worktree non fusionné `.claude/worktrees/llm-endpoints-config/`. À vérifier/récupérer si son routage par type de tâche (code/prompt_refinement/general/complex) est encore nécessaire.

## Gestion de contexte en session longue/autonome
- Surveille ton pourcentage d'utilisation de contexte tout du long.
- À 90% : commence à conclure proprement — termine l'étape en cours, ne démarre rien de nouveau.
- À 92% : arrête-toi complètement. Committe le travail en l'état (ou sauvegarde dans un état stable si un commit n'est pas pertinent), écris un résumé clair de où tu en es et ce qu'il reste à faire dans un fichier de handoff (ex. HANDOFF.md dans le worktree concerné).
- Ne laisse jamais un fichier à moitié écrit, un commit incomplet, ou un process GPU orphelin pour gagner quelques % de marge supplémentaire.

## Règles GPU (machine à 2 cartes : RTX 5080 + RTX 5060 Ti)

- **Ne jamais outrepasser une consigne d'occupation GPU établie.** Si une carte est indiquée comme occupée (test/entraînement en cours), c'est normalement voulu — vérifie `nvidia-smi` avant toute action GPU, puis adapte-toi en utilisant la carte libre plutôt que de forcer un partage de ressource ou d'attendre sans solution. Ne jamais tuer/redémarrer un process GPU pour libérer de la place sans consigne explicite de l'utilisateur (cf. session 2026-07-28 : deux process qui semblaient orphelins via `nvidia-smi` étaient en fait des zombies laissés par un crash antérieur — leur suppression était correcte mais restait une décision utilisateur, pas une initiative à prendre seul).
- **Epingler un rendu Blender à une carte précise** : le moteur Workbench (contexte OpenGL par défaut du système) n'est PAS pilotable — testé le 2026-07-29, la préférence Windows "GPU par application" (registre `UserGpuPreferences`) ne redirige pas ce contexte, le rendu reste sur la RTX 5080 (carte d'affichage principale) quoi qu'il arrive. Utiliser le moteur **Cycles** à la place : il expose une liste de devices CUDA/OptiX activables individuellement (`bpy.context.preferences.addons['cycles'].preferences.devices`, activer uniquement ceux dont le nom correspond à la carte visée) — seule méthode fiable trouvée sur cette machine. Voir `handsegnet/blender3d_prototype/drive_from_landmarks.py::configure_cycles_gpu` pour une implémentation de référence.

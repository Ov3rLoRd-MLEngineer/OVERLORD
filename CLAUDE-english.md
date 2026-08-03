# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Language

**Always respond in English** in this repository, regardless of the language of the user's message. Code, commits, and file names may remain in English; only conversational responses must be in English.

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
- **`maestro.py`** — original orchestrator: `SOURCING → SCENARIO → STORYBOARD → PRODUCTION → POST-PROD → 3D`. Imports everything from `agents.*` defensively (try/except with fallback stub functions) so a broken/missing agent degrades instead of crashing the whole run.
- **`agent_supervisor_v2.py`** — the industrial orchestrator that actually talks to the ComfyUI HTTP API, manages state machine, retries, image archiving, notifications. Deliberately kept at repo root, not inside `agents/`, so it can run standalone without relative-import gymnastics (see `DOCS/ADR_OVERLORD.md` ADR-001 — do not move it into `agents/`).
- **`agents/`** — ~150 individual agent modules (sourcing, scenario, storyboard, quality gate/reviewer, prompt engineering, pose/mask/inpaint tooling, style continuity, narrative memory, GPU/thermal management, publishing, etc.). Each is designed to be optional/replaceable; callers wrap imports in try/except and fall back to stub behavior if a module fails to import.
- **`agents/context_bus.py`** — thread-safe singleton pub/sub-ish key/value bus (`get_bus().write(key, value, agent_id=, confidence=)` / `.read(key)`) used for inter-agent communication, persisted to `workspace/context_bus/bus_state.json`.
- **`agents/config_manager.py`** — centralized config: `from agents.config_manager import cfg; cfg.get("comfyui.steps", 50)`. Backed by SQLite at `workspace/config.db`. Precedence: `DEFAULTS (in-code) < config.db < .env < runtime kwargs`. `.env` stays authoritative only for **secrets** (API keys) — see ADR-005. GPU-specific overrides live in `GPU_PRESETS` in the same file.
- **`workspace/`** — all runtime state and outputs: `archive/`, `logs/`, `context_bus/`, `narrative/`, `config.db`, `state.json`/`pipeline_state*.bak`, `reports/`, etc. This is the pipeline's working directory, distinct from the ComfyUI output directory.

### ComfyUI workflow files
ComfyUI workflows are stored as exported API-format JSON at the repo root (e.g. `Advanced_QwenVL_V35*.json`, `animatediff_sdxl_cn_test*.json`, `Combined_V35_API.json`). These are patched programmatically (node IDs are hardcoded — see the `ADV_*`/`DET_*` node-id constants near the top of `agent_supervisor_v2.py`) rather than rebuilt from scratch. Node IDs are stable per workflow file; if you regenerate a workflow from the ComfyUI UI, node IDs can shift and every constant referencing them must be re-checked.

Numbered/lettered `_PIPELINE_PATCHED*`, `*_v2`, `*_v3` files and the many root-level `patch_*.txt` / `PATCH_*.txt` files are point-in-time patch outputs kept for traceability — treat the highest version number as current, older ones as history, not as alternatives to pick between.

**Prompt-upsampling ban list (hallucination guard)** : The only TIPO/DanTagGen-style prompt upsampling system in the repo is the `AILab_QwenVL_PromptEnhancer` node (`custom_system_prompt`, widget index 7 — verified in `AILab_QwenVL_PromptEnhancer.py::process()`, `base_instruction = custom_system_prompt.strip() or ...`), currently set to `mode: 4` (bypass) wherever it appears.

**Actually active file**: `Advanced_QwenVL_V35.json` (root, no suffix — tracked in git since initial commit) is hardcoded and loaded by `agents/workflow_controller.py` (`ADVANCED_WF`), executable via manual CLI (`python agents/workflow_controller.py --pass ...`, outside the automated maestro/supervisor chain). This is the file that received the "Ban List" section (`holding|object|cup|phone|cellphone|camera|bottle|weapon|gun`, added 2026-07-30) — it will persist until regenerated from the ComfyUI UI (in which case re-apply the section). **Not wired** in the automated HandSegNet generator (`generate_dataset.py` builds the prompt directly from wildcards → `CLIPTextEncode`, without an LLM stage).

`Advanced_QwenVL_V35_PIPELINE_PATCHED_v3.json` (patched 2026-07-29, BEFORE the scope correction above) was not referenced anywhere in the code — fix was applied to the wrong file initially, now corrected. Moved to `corbeille/workflows_json_historiques/` during the 2026-08-02 reorganization (see `PROPOSITION_REORGANISATION_FICHIERS.md`).

`Advanced_QwenVL_V35_ORIGINAL.json` — node-by-node comparison confirmed identical to `Advanced_QwenVL_V35.json` across all 208 nodes EXCEPT the QwenVL node itself (ban list absent): this is the pre-patch snapshot of the same pipeline, not a different pipeline. Kept at the user's explicit request (baseline reference for ongoing tests) — **not yet protected by the ban list**, decision intentionally left to the user rather than applied unilaterally (cf. 2026-07-30 session report).

`_PIPELINE_PATCHED.json`/`_PATCHED_v2.json`/`_PATCHED_v3.json`: Confirmed candidates for deletion by the user (not referenced in code) — moved to `corbeille/workflows_json_historiques/` during the 2026-08-02 reorganization (not deleted, just moved out of the active path; see `PROPOSITION_REORGANISATION_FICHIERS.md`).

### Decisions that constrain future changes
Many of these are logged formally in `DOCS/ADR_OVERLORD.md` — read it before changing sampler defaults, storage strategy, config precedence, or seed strategy. Highlights, some superseded by later session logs (`CONTEXTE_OVERLORD_V2xx.md` — V150 through V227 now live in `DOCS/historique_sessions/`, V228+ stay at repo root since they're consulted first; latest is highest number):
- `taesdxl` is the VAE in use (the real `sdxl_vae.safetensors` was corrupted; ADR-002) — don't swap this without checking whether it's been re-downloaded.
- Default sampler is `dpmpp_2m` + `karras`; `euler_ancestral` is explicitly avoided for multi-frame continuity (ADR-003) — except the AnimateDiff test workflow currently uses `euler_ancestral`/`normal` deliberately (see `ADDENDUM_WORKFLOW_ANIMATEDIFF.md`).
- Seeds for a run use `base_seed + i * 137` for controlled variation without visual drift between frames (ADR-008).
- Scenario/script generation always succeeds — `_fallback_script()` guarantees the pipeline never hard-stops on an LLM/JSON failure (ADR-009).
- LLM prompts (system + user) must be written in English even though logs/UI/TTS are French — French prompts measurably increased invalid-JSON rates from Ollama/Mistral (ADR-006).
- Image archiving uses `shutil.copy2`, never `rename`/move, so ComfyUI's own `output/` folder is never emptied by the pipeline (ADR-007).
- SAM-based masking: images must be composited onto a white background before `SAMPreprocessor` — passing raw RGBA silently fails in ~0.02s with no output. Mask convention is **black = regenerate, white = preserve** (confirmed via ComfyUI MaskEditor).
- AnimateDiff must use `ADE_AnimateDiffLoaderGen1` (Gen2 is unavailable on this machine).

`LIMITATIONS_CONNUES.md` catalogs known generative-model limitations (e.g. bilateral-symmetry hand compositions collapsing into a mirrored decorative motif) that are **not pipeline bugs** — check it before reopening an investigation into a "failed" image, so the same non-actionable case doesn't get reprocessed every session.

### Session context docs
`CONTEXTE_OVERLORD_V*.md` files (V150 through the current highest number) are session handoff notes — each captures in-progress bugs, what was just fixed, and next steps at the time it was written. When resuming multi-session work, read the **highest-numbered** one first; treat older ones as historical record only, since defaults and conventions get superseded (e.g. VAE, sampler, checkpoint choices evolve across sessions and are only trustworthy as of the date at the top of each file). `ADDENDUM_*.md` files are supplements meant to be read alongside a specific `CONTEXTE_*` file (named in the addendum's own header).

### Repo hygiene notes
- Root contains many one-off `fix_*.py`, `scan_*.py`, `_peek*.py` scripts and stray zero-byte files (`git`, `python`, `logging.Logger`) left over from earlier debugging sessions — these are not part of any import graph; don't treat their presence as significant, and don't assume a same-named file is "the" implementation without checking `agents/` first (duplicate filenames exist between root and `agents/`, e.g. `reference_aligner_v2.py`, `invert_lineart.py`, `patcher.py` — root's `patcher.py` is V1.1 (supports two bundle formats), `agents/patcher.py` is the older V1.0, root is current).
- `agents/` also contains vendored third-party packages (`requests/`, `urllib3/`, `certifi/`, `idna/`, `charset_normalizer/`) alongside the actual agent modules — don't confuse these with project code when searching.

## Key Paths

Index of files most frequently searched at the start of a session to avoid search round-trips. Paths verified from `D:\OVERLORD\`; ignore any identical path under `.claude/worktrees/` or `BACKUP/` (unmerged or obsolete copies, never the current version).

**SegNets** (the same trio exists in each of `footsegnet/`, `handsegnet/`, `bodysegnet/`, `facesegnet/`):
- `<module>/annotate.py` — tkinter manual annotation interface (SAM pre-fill + brush/fill), see `--by-confidence` to sort by ascending SAM score
- `<module>/batch_premask.py` — automatic pre-masking (pose bbox + SAM + VLM grounding fallback)
- `<module>/build_coco.py` — export of the annotated dataset in COCO format
- `<module>/dataset/premasks/_provenance.csv` — per-image provenance log (box_source, status, mask_pct, sam_score); read by `agents/segnet_premask.py::load_sam_scores()`

**Control-LoRA FootSegNet → SDXL** (`footsegnet/controlnet/`, see its own `README.md` for the full workflow):
- `footsegnet/controlnet/prepare_dataset.py` — generation + pre-mask + pair assembly
- `footsegnet/controlnet/quality_sort.py` — sort usable / needs review / exclude (coverage, box_source, mask fragmentation)
- `footsegnet/controlnet/train_control_lora.py` — training (diffusers + peft)
- `footsegnet/controlnet/route_by_sam_confidence.py` — manual/auto routing by native SAM confidence score threshold
- `footsegnet/dataset/premasks/route_auto_sort.txt` / `route_manual_review.txt` — Control-LoRA batch routing lists (stems, one per line)
- `footsegnet/dataset/premasks/prepare_review_folder.py` + `README.md` — prepares a folder of hard links to open only the stems from `route_manual_review.txt` in `annotate.py`

**Pipeline core**:
- `maestro.py` — legacy orchestrator (SOURCING→SCENARIO→STORYBOARD→PRODUCTION→POST-PROD→3D)
- `agent_supervisor_v2.py` — industrial orchestrator (talks to ComfyUI API), stays at root (ADR-001)
- `agents/director.py` — The Director (staging / narrative direction)
- `agents/context_bus.py` — inter-agent pub/sub bus (`get_bus().write()/.read()`)
- `agents/segnet_premask.py` — shared pre-masking logic (`load_sam_scores`, `clean_mask`, `fill_mask_holes`, `run_batch`) behind the 4 `batch_premask.py` scripts
- `patcher.py` (root, V1.1, current) — find/replace or CREATE/UPDATE patch agent; do not confuse with `agents/patcher.py` (V1.0, older)
- `DOCS/ADR_OVERLORD.md` — formal architecture decisions (sampler, VAE, seeds, config...)

**Config**:
- `config.py` (root) — shared paths/constants (`FOOTSEGNET_ROOT`, `SAM_CHECKPOINT`, etc.), imported by most SegNet/Control-LoRA scripts
- `agents/config_manager.py` — centralized config (`cfg.get(...)`), precedence DEFAULTS < `workspace/config.db` < `.env` < runtime kwargs
- `.env` (root) — secrets/API keys only (ADR-005)

**`agents/llm_router.py`** — exists on the main tree (delivered PR #15, session 2026-07-07/08; the previous note stating it only existed in the `llm-endpoints-config` worktree was outdated, corrected on 2026-08-02). Task-type routing (code/prompt_refinement/general/complex) is functional but **not called by the pipeline** — `maestro.py`/`agent_supervisor_v2.py` and other agents continue calling `fallback_llm()` directly without going through this router (see `RAPPORT_AUDIT_PIPELINE_AOUT2026.md`).

## Long/Autonomous Session Context Management
- Monitor your context usage percentage throughout.
- At 90%: start wrapping up cleanly — finish the current step, do not start anything new.
- At 92%: stop completely. Commit the work as-is (or save in a stable state if a commit isn't appropriate), write a clear summary of where you stand and what remains to be done in a handoff file (e.g. `HANDOFF.md` in the relevant worktree).
- Never leave a half-written file, an incomplete commit, or an orphaned GPU process just to gain a few percentage points of extra margin.
- **Proactively signal when to close the session, even before the 90/92% threshold**: a natural milestone is reached (task delivered, isolated commit made), the next step depends on external waiting for several hours (download, long detached training — no need to keep the session open during this time), or the conversation has drifted far from the initial scope to the point where a fresh session would be more efficient. Objective: prevent sessions from dragging on by default due to a lack of explicit stop signals — the user is on a tight token/quota budget (see economy section below).

## Session and Token Economy

User constraint: token quota/cost to be minimized continuously, not just at the end of the session.

- **Favor local execution** (local GPU/LLM, scripts) over expensive round-trips when an equivalent result can be reached locally — see GPU allocation convention below.
- **GPU allocation by usage (RTX 5080 / RTX 5060 Ti)**: RTX 5080 dedicated to one-off tests/trainings/evaluations (QLoRA, sweeps, heavy diagnostics, one-shot benchmarks like baseline/adapter comparison) — confirmed ~2x faster (measured on reel_v3 and V4 evaluation). RTX 5060 Ti dedicated to **background/service** LLM inference (e.g., local Ollama fallback, serving). Logic refined on 2026-08-02: it's not "training vs inference" that determines the card, but "one-off run blocking a session where speed matters" (5080) vs "service running in the background" (5060 Ti). `training/scripts/eval_adapter.py` (Session 5) and `workspace/qlora_dataset/scripts/evaluate_stages_v4.py` (Session 2026-08-02) correctly use `cuda:0` — not a historical exception. Only `training/scripts/train_qlora.py` (Session 2-5, `cuda:1`) remains a historical trace prior to this clarification, not to be corrected retroactively.
- **Logs/reports produced by an external tool** (another LLM — Gemini, Claude.exe desktop, etc. — or third-party script launched outside this session): store them in `workspace/external_ai_sessions/<tool>/` rather than loose files on the Desktop, whenever they document work done on this repository. Ask the external tool to save directly to this location if possible; otherwise copy afterwards.
- **Never present a simulated/mock result as a real evaluation without explicitly stating so** — direct lesson learned: an evaluation script produced by an external tool turned out to be a hardcoded `simulate_generation()` function (no model loaded, no actual inference), presented as a legitimate qualitative comparison. Always verify that an evaluation script actually calls the model before citing its results.
- **Version/timestamp training `run_name`s** — direct lesson learned: a pipeline script reused the same `run_name` as an already successful full run with a hardcoded reduced `--max_steps`, silently overwriting the good final adapter (fortunately recoverable via intermediate `save_steps` checkpoints). A new run must never write to an existing run's output folder without explicit confirmation.
- Parallelize independent tool calls (reads, searches) rather than chaining them sequentially.
- Do not regenerate an already up-to-date dataset/report without a reason — check existing state before re-running an expensive script.

## GPU Rules (2-card machine: RTX 5080 + RTX 5060 Ti)

- **Never override an established GPU allocation rule.** If a card is indicated as occupied (test/training in progress), it is normally intentional — check `nvidia-smi` before any GPU action, then adapt by using the free card rather than forcing resource sharing or waiting without a solution. Never kill/restart a GPU process to free up space without explicit user instructions (cf. session 2026-07-28: two processes that looked orphaned via `nvidia-smi` were actually zombies left by a prior crash — terminating them was correct but remained a user decision, not an initiative to take alone).
- **Pin a Blender render to a specific card**: The Workbench engine (system default OpenGL context) cannot be controlled — tested on 2026-07-29, the Windows "GPU per application" preference (`UserGpuPreferences` registry) does not redirect this context, the render remains on the RTX 5080 (primary display card) no matter what. Use the **Cycles** engine instead: it exposes a list of individually activatable CUDA/OptiX devices (`bpy.context.preferences.addons['cycles'].preferences.devices`, activate only those whose name matches the target card) — the only reliable method found on this machine. See `handsegnet/blender3d_prototype/drive_from_landmarks.py::configure_cycles_gpu` for a reference implementation.

## Launching Detached Processes (Long Trainings)

For any long-running process launched in the background from a Claude Code session (detached QLoRA/LoRA training, long-running GPU script): launch via `start cmd /k py -3.12 <script> <args>` (dedicated new CMD window that stays open, progress visible live) rather than PowerShell `Start-Process`, which hides the window by default and provides no progress without redirecting to a log file and tailing it manually. The actual PID to monitor remains that of the `python.exe` process visible in that CMD window, not any stub PID returned by the launcher tool (cf. documented trap for `Start-Process` on a venv, `workspace/qlora_dataset/HANDOFF_2026-08-02.md`).

## GPU Time Tracking

For any **substantial** computation run (training, batch generation >50 images, diagnostic test >15min — NOT one-off VLM/grounding calls, too numerous and individually insignificant), add a line to `gpu_usage_log.csv` (repository root, create if absent, otherwise append):

```csv
date_iso,gpu,duree_minutes,module,description,cout_estime_usd,estime_retroactif
2026-07-28T14:30:00,RTX5080,95,footsegnet-controlnet,"test weights x50 collapse mode",1.90,false
```

`cout_estime_usd` = `duree_minutes/60 × reference hourly rate` — local RTX 5080/5060 Ts cost $0 in practice, this is a cloud-cost equivalent for comparison purposes only (reference rates: A100 ~$1.20/h, H100 ~$2.40/h). Consultable via `py -3.12 gpu_cost_estimate.py` (cumulative by GPU/module + total cost equivalent).

`estime_retroactif`: `false` for a line logged at the time the run executed (duration known with certainty); `true` for a line reconstructed afterwards from indirect traces (scratch job logs, file dates, throughput extrapolated from another run) — always specify the method and margin of uncertainty in `description` rather than presenting a reconstructed duration as a direct measurement.

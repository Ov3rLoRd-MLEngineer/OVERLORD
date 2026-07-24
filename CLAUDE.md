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
python test_suite_v170.py --quick
python test_suite_v170.py
python test_suite_v170.py --agent scenario   # one agent

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
- Root contains many one-off `fix_*.py`, `scan_*.py`, `_peek*.py` scripts and stray zero-byte files (`git`, `python`, `logging.Logger`) left over from earlier debugging sessions — these are not part of any import graph; don't treat their presence as significant, and don't assume a same-named file is "the" implementation without checking `agents/` first (duplicate filenames exist between root and `agents/`, e.g. `reference_aligner_v2.py`, `invert_lineart.py`).
- `agents/` also contains vendored third-party packages (`requests/`, `urllib3/`, `certifi/`, `idna/`, `charset_normalizer/`) alongside the actual agent modules — don't confuse these with project code when searching.

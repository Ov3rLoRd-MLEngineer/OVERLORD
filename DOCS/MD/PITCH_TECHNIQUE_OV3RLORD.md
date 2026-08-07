# Ov3rLoRd — Technical Summary

*One-page project summary, written 2026-08-07. Numbers below are pulled
directly from tracked logs and published model cards, not estimated for
this document — see the "Source" column.*

## What it is

Ov3rLoRd is a personal, single-operator pipeline that orchestrates a local
ComfyUI instance to produce anime-style images and video autonomously:
trend sourcing → scenario/script generation (local LLM) → storyboard →
image/video generation → post-production → publishing. Built and run
solo, iteratively, over ~230 documented development sessions. Everything
runs on local hardware (2× consumer GPU) — no cloud training or inference
spend.

## Key metrics

| Metric | Value | Source |
|---|---|---|
| FootSegNet validation IoU | **0.9277** (ground-truth box) | `footsegnet/huggingface/README.md` |
| HandSegNet validation IoU | **0.8876** (ground-truth box) / **0.722 mean** (automatic box, real end-to-end pipeline) | `handsegnet/huggingface/README.md` — both numbers reported deliberately, see Engineering practices below |
| Continuous anime video generated, single run | **51 clips, ~3 min 55 s**, identity-anchored throughout | `DEMO/output/miku_demo_3min_v2_keyframed.mp4`, `generation_log.csv` |
| Color drift reduction (ColorMatch LAB vs baseline) | **-4.9%** inter-frame Lab delta (6.73 vs 7.08 baseline) | `DOCS/MD/COMPARAISON_UNIFICATION_20260806.md`, 30 real generations measured |
| Cumulative tracked GPU compute | **~108 h** (RTX 5080 + RTX 5060 Ti) | `gpu_usage_log.csv`, 39 logged runs |
| Published open-source models | **2** (HandSegNet, FootSegNet — SAM ViT-B fine-tunes), GitHub + HuggingFace, Apache 2.0 | `github.com/Ov3rLoRd-MLEngineer` |
| Local LLM fine-tuning pipeline | QLoRA, 2-stage (code corpus + commit-message corpus), served via Ollama | `workspace/qlora_dataset/` |

## Technical stack

- **Image generation**: SDXL (ComfyUI, API-driven), custom ControlNet /
  Control-LoRA training, SAM ViT-B fine-tuned for anime-domain hand and
  foot segmentation (own datasets, own training loop).
- **Video generation**: WAN 2.2 I2V with SVI (Stable Video Infinity,
  dual-LoRA anti-drift) as primary path; AnimateDiff evaluated and
  benchmarked as an alternative (documented trade-off, not guesswork).
- **3D previz / motion**: Blender + MMD (VMD motion retargeting), procedural
  camera placement (spherical orbit, elevation variation), OpenPose
  skeleton export for future ControlNet conditioning.
- **LLM**: local Ollama serving (Qwen3, QLoRA-fine-tuned in two stages),
  RAG layer (682 indexed chunks) with an explicit anti-hallucination
  guardrail rather than unconstrained generation.
- **Infra**: dual-GPU workload split by task shape (one-off
  training/eval/benchmark runs on the faster card, continuous serving on
  the other) rather than by a fixed training/inference label — a
  distinction refined mid-project after measuring actual throughput.

## Engineering practices worth noting

- **Two different accuracy numbers reported for HandSegNet, not one
  flattering headline** — ground-truth-box IoU (0.8876) isolates model
  quality; automatic-box IoU (0.722 mean) reflects what the pipeline
  actually delivers end-to-end. The gap is documented and attributed
  explicitly to the upstream box-detection step, not hidden.
- **Cost discipline even at zero marginal cost**: every substantial GPU run
  is logged with an equivalent cloud-cost figure (`gpu_usage_log.csv`) purely
  for planning/comparison purposes, with retroactive estimates explicitly
  flagged as such versus directly measured runs.
- **Formal decision records** (ADRs) for architecture choices that would
  otherwise silently drift across a year-plus of iterative sessions
  (sampler choice, VAE, seed strategy, config precedence).
- **Known limitations documented as such**, not re-investigated every
  session — e.g. a catalogued list of generative-model failure modes that
  are load-bearing constraints, not open bugs.

## Links

- GitHub: `github.com/Ov3rLoRd-MLEngineer` (HandSegNet, FootSegNet —
  standalone inference, decoupled from the private pipeline)
- HuggingFace: `huggingface.co/Ov3rLoRd-MLEngineer`

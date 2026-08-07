# Arborescence agents/ post-reorganisation Phase C (2026-08-03)

Genere le 2026-08-05 pour combler un angle mort de couverture RAG :
`arborescence_projet.md` liste `agents/` a plat (156 fichiers, aucune
descente dans les sous-dossiers) et ne reflete donc pas la reorganisation
Phase C (commit `7a85dec`, 2026-08-03) qui a range les modules `agents/*.py`
en sous-paquets thematiques. Liste brute des sous-dossiers et de leur
contenu (hors paquets vendored tiers `requests/`, `urllib3/`, `certifi/`,
`idna/`, `charset_normalizer/`, et hors `__pycache__/`) -- pas de description
par fichier (meme discipline anti-hallucination que `arborescence_projet.md`).

## agents/core/ — orchestration/etat/qualite transverse

agent_registry.py, audit_logger.py, checkpoint_manager.py, config_manager.py,
context_bus.py, critic.py, director.py, overlord_utils.py, patcher.py,
pipeline_conscience.py, pipeline_constitution.py, quality_gate.py,
resource_scheduler.py, roles_registry.py, schema_validator.py,
session_manager.py, session_reporter.py, test_integration.py,
test_pipeline.py, watchdog.py, watchdog_config.py

Note : `agents/core.py` (V1.0, ancien) renomme en `agents/legacy_v1xx/core.py`
pour lever la collision avec le nouveau paquet `agents/core/` (voir
`reorg-preferences`, memoire session).

## agents/creative/ — scenario/prompt/narratif

agent_translator.py, asset_library.py, auto_sourcing.py, character_designer.py,
character_sheet_generator.py, episode_packager.py, episode_planner.py,
grok_client.py, grok_prompt_generator.py, llm_router.py, narrative_dna.py,
narrative_memory.py, negative_bank.py, ollama_bridge.py, pacing_engine.py,
prompt_engineer.py, prompt_library.py, prompt_optimizer.py, prompt_override.py,
prompt_translator.py, qwen_prompt_refiner.py, scenario.py, source_cleaner.py,
sourcing.py, sourcing_multisensor.py, storyboard.py, style_continuity.py,
style_dna.py, style_dna_generator.py, style_evolution.py

## agents/infra/ — infrastructure/outillage/RAG

api_server.py, benchmark_arena.py, build_launcher.py, build_maintenance_hub.py,
capture.py, cost_tracker.py, dashboard.py, deploy.py, error_recovery.py,
gpu_scheduler.py, graph_ui.py, model_downloader.py, module_manager.py,
obs_agent.py, overlord_launcher.py, **rag_indexer.py**, **rag_query.py**,
ray_cluster.py, remote_gpu.py, sav_agent.py, sav_debug.py, storage_manager.py,
sys_agent.py, workflow_organizer.py

## agents/production_image/ — generation image ComfyUI

agent_overclock.py, comfy_autoconfig.py, gpu_optimizer.py, lora_trainer.py,
thermal_protection.py, workflow_controller.py

## agents/production_video/ — generation/traitement video

batch_controlnet.py, **cycle_detector.py**, denoise_estimator.py,
frame_extractor.py, frames_to_video.py, lineart_extractor.py,
lineart_remapper.py, motion_interpolator.py, motion_mask_generator.py,
pose_generator.py, reference_aligner_v2.py, sakuga_compositor.py,
skeleton_remapper.py, transition_builder.py, video_analyzer.py,
video_pipeline.py

Note : `cycle_detector.py` **existe** dans ce sous-dossier (a verifier contre
`RAPPORT_AUDIT_PIPELINE_AOUT2026.md`/`PLAN_PIPELINE_A_DEMO_30S.md` qui le
listaient comme absent/bloquant -- possible mise a jour depuis l'audit, ou
fichier stub non fonctionnel ; a confirmer par lecture directe avant de lever
ce blocage dans un plan de demo).

## agents/postprod_audio/ — post-production audio/TTS

_coqui_tts_worker.py, anime_palette_generator.py, audio_compositor.py,
manga_ocr_translator.py, music_synthesis.py, postprod.py, voice_synthesis.py

## agents/publishing/ — diffusion/marketing

audience_analyzer.py, market_analyzer.py, marketing_pub.py, slack_monitor.py,
social_agent.py, telegram_bot.py, transmedia_export.py,
transmedia_publisher.py

## agents/qc_validation/ — controle qualite / masquage SegNet

backfill_sam_scores.py, clip_validator.py, dataset_diversity_stats.py,
detect_hand_occlusion.py, explain_unscored.py, inpaint_corrector.py,
inpaint_queue.py, manual_stitch.py, prepare_route_folders.py,
quality_reviewer.py, quality_reviewer_visual.py, region_mask_generator.py,
route_by_sam_confidence.py, sam_mask_generator.py, segnet_premask.py,
shoe_consistency_checker.py, visual_validator.py, vlm_grounding.py

## agents/legacy_v1xx/ — ancienne generation d'agents (V1.x, conserves)

agent_personality.py, alignment.py, cocreation.py, collective.py, core.py,
dream_mode.py, dream_simulation.py, emotion_engine.py, generation.py,
generative_world.py, intelligence.py, intelligence_ext.py, intent_parser.py,
kaizen_analyzer.py, learning.py, learning_agent.py, legacy_agent.py,
memory_agent.py, moe.py, oracle_interface.py, self_improve.py,
self_optimizer.py, synchronicity.py, theory_of_mind.py, world_model.py

## agents/3d/ — 3D

agent_3d_modeler.py

## agents/bin/ — binaires vendored

idna.exe, normalizer.exe (dependances de `agents/idna/`/`agents/charset_normalizer/`, pas du code projet)

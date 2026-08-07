"""
Script de migration ponctuel -- regroupe agents/*.py en sous-dossiers thematiques.
Cree un shim de compatibilite a l'ancien emplacement (base sur runpy.run_path,
qui fonctionne aussi bien pour `from agents.X import Y` que pour une invocation
directe `python agents/X.py --args`, car run_name=__name__ preserve le
comportement __main__ dans les deux cas).
Usage : py -3.12 _migrate_agents_subfolders.py
A supprimer une fois la migration terminee et verifiee.
"""
import os
import shutil
from pathlib import Path

AGENTS = Path(__file__).parent / "agents"

# module_name (sans .py) -> sous-dossier cible
MAPPING = {
    # core
    "agent_registry": "core", "audit_logger": "core", "checkpoint_manager": "core",
    "config_manager": "core", "context_bus": "core", "critic": "core",
    "director": "core", "overlord_utils": "core", "patcher": "core",
    "pipeline_conscience": "core", "pipeline_constitution": "core",
    "quality_gate": "core", "resource_scheduler": "core", "roles_registry": "core",
    "schema_validator": "core", "session_manager": "core", "session_reporter": "core",
    "watchdog": "core", "watchdog_config": "core", "test_integration": "core",
    "test_pipeline": "core",

    # creative
    "scenario": "creative", "storyboard": "creative", "sourcing": "creative",
    "sourcing_multisensor": "creative", "auto_sourcing": "creative",
    "narrative_memory": "creative", "narrative_dna": "creative",
    "character_designer": "creative", "character_sheet_generator": "creative",
    "style_dna": "creative", "style_dna_generator": "creative",
    "style_continuity": "creative", "style_evolution": "creative",
    "prompt_engineer": "creative", "prompt_library": "creative",
    "prompt_optimizer": "creative", "prompt_translator": "creative",
    "prompt_override": "creative", "negative_bank": "creative",
    "episode_planner": "creative", "episode_packager": "creative",
    "asset_library": "creative", "pacing_engine": "creative",
    "qwen_prompt_refiner": "creative", "grok_client": "creative",
    "grok_prompt_generator": "creative", "llm_router": "creative",
    "ollama_bridge": "creative", "source_cleaner": "creative",
    "agent_translator": "creative",

    # production_image
    "workflow_controller": "production_image", "comfy_autoconfig": "production_image",
    "gpu_optimizer": "production_image", "agent_overclock": "production_image",
    "thermal_protection": "production_image", "lora_trainer": "production_image",

    # production_video
    "batch_controlnet": "production_video", "motion_mask_generator": "production_video",
    "denoise_estimator": "production_video", "reference_aligner_v2": "production_video",
    "skeleton_remapper": "production_video", "lineart_extractor": "production_video",
    "lineart_remapper": "production_video", "frame_extractor": "production_video",
    "frames_to_video": "production_video", "pose_generator": "production_video",
    "video_analyzer": "production_video", "video_pipeline": "production_video",
    "motion_interpolator": "production_video", "sakuga_compositor": "production_video",
    "transition_builder": "production_video",

    # postprod_audio
    "postprod": "postprod_audio", "audio_compositor": "postprod_audio",
    "voice_synthesis": "postprod_audio", "_coqui_tts_worker": "postprod_audio",
    "music_synthesis": "postprod_audio", "manga_ocr_translator": "postprod_audio",
    "anime_palette_generator": "postprod_audio",

    # qc_validation
    "clip_validator": "qc_validation", "visual_validator": "qc_validation",
    "inpaint_queue": "qc_validation", "inpaint_corrector": "qc_validation",
    "shoe_consistency_checker": "qc_validation", "sam_mask_generator": "qc_validation",
    "segnet_premask": "qc_validation", "region_mask_generator": "qc_validation",
    "detect_hand_occlusion": "qc_validation", "dataset_diversity_stats": "qc_validation",
    "vlm_grounding": "qc_validation", "route_by_sam_confidence": "qc_validation",
    "backfill_sam_scores": "qc_validation", "explain_unscored": "qc_validation",
    "manual_stitch": "qc_validation", "quality_reviewer": "qc_validation",
    "quality_reviewer_visual": "qc_validation", "prepare_route_folders": "qc_validation",

    # publishing
    "transmedia_publisher": "publishing", "transmedia_export": "publishing",
    "social_agent": "publishing", "telegram_bot": "publishing",
    "marketing_pub": "publishing", "audience_analyzer": "publishing",
    "market_analyzer": "publishing", "slack_monitor": "publishing",

    # legacy_v1xx
    "emotion_engine": "legacy_v1xx", "world_model": "legacy_v1xx",
    "agent_personality": "legacy_v1xx", "intelligence": "legacy_v1xx",
    "intelligence_ext": "legacy_v1xx", "generative_world": "legacy_v1xx",
    "theory_of_mind": "legacy_v1xx", "synchronicity": "legacy_v1xx",
    "dream_mode": "legacy_v1xx", "dream_simulation": "legacy_v1xx",
    "cocreation": "legacy_v1xx", "collective": "legacy_v1xx", "moe": "legacy_v1xx",
    "alignment": "legacy_v1xx", "generation": "legacy_v1xx", "learning": "legacy_v1xx",
    "learning_agent": "legacy_v1xx", "memory_agent": "legacy_v1xx",
    "legacy_agent": "legacy_v1xx", "self_improve": "legacy_v1xx",
    "self_optimizer": "legacy_v1xx", "kaizen_analyzer": "legacy_v1xx",
    "oracle_interface": "legacy_v1xx", "core": "legacy_v1xx", "intent_parser": "legacy_v1xx",

    # infra
    "obs_agent": "infra", "capture": "infra", "sav_agent": "infra", "sav_debug": "infra",
    "storage_manager": "infra", "model_downloader": "infra", "cost_tracker": "infra",
    "benchmark_arena": "infra", "deploy": "infra", "build_maintenance_hub": "infra",
    "build_launcher": "infra", "overlord_launcher": "infra", "api_server": "infra",
    "dashboard": "infra", "graph_ui": "infra", "module_manager": "infra",
    "ray_cluster": "infra", "remote_gpu": "infra", "sys_agent": "infra",
    "gpu_scheduler": "infra", "error_recovery": "infra", "workflow_organizer": "infra",

    # 3d
    "agent_3d_modeler": "3d",
}

SHIM_TEMPLATE = '''"""Shim de compatibilite -- module deplace vers agents/{group}/{name}.py
Voir PROPOSITION_REORGANISATION_FICHIERS.md. Fonctionne pour `from agents.{name} import X`
ET pour une invocation directe (`python agents/{name}.py --args`) grace a runpy.run_path
qui preserve le __name__ d'execution (donc le bloc if __name__=="__main__" du fichier
reel se declenche normalement quand ce shim est lance comme script).
"""
import runpy as _runpy, os as _os
_target = _os.path.join(_os.path.dirname(__file__), "{group}", "{name}.py")
globals().update(_runpy.run_path(_target, run_name=__name__))
'''

def main():
    moved, skipped, errors = [], [], []
    groups = sorted(set(MAPPING.values()))
    for g in groups:
        d = AGENTS / g
        d.mkdir(exist_ok=True)
        init = d / "__init__.py"
        if not init.exists():
            init.write_text("", encoding="utf-8")

    for name, group in MAPPING.items():
        src = AGENTS / f"{name}.py"
        if not src.exists():
            skipped.append(f"{name}.py (introuvable)")
            continue
        dst = AGENTS / group / f"{name}.py"
        try:
            shutil.move(str(src), str(dst))
            shim = SHIM_TEMPLATE.format(group=group, name=name)
            src.write_text(shim, encoding="utf-8")
            moved.append(f"{name}.py -> {group}/")
        except Exception as e:
            errors.append(f"{name}.py: {e}")

    print(f"Deplaces : {len(moved)}")
    print(f"Ignores  : {len(skipped)}")
    for s in skipped:
        print(f"  - {s}")
    print(f"Erreurs  : {len(errors)}")
    for e in errors:
        print(f"  - {e}")

if __name__ == "__main__":
    main()

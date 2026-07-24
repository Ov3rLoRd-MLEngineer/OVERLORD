# ██████╗ ██╗   ██╗██████╗ ██████╗ ██╗      ██████╗ ██████╗ ██████╗
# ██╔═══██╗██║   ██║╚════██╗██╔══██╗██║     ██╔═══██╗██╔══██╗██╔══██╗
# ██║   ██║██║   ██║ █████╔╝██████╔╝██║     ██║   ██║██████╔╝██║  ██║
# ██║   ██║╚██╗ ██╔╝ ╚═══██╗██╔══██╗██║     ██║   ██║██╔══██╗██║  ██║
# ╚██████╔╝ ╚████╔╝ ██████╔╝██║  ██║███████╗╚██████╔╝██║  ██║██████╔╝
# ╚═════╝   ╚═══╝  ╚═════╝ ╚═╝  ╚═╝╚══════╝ ╚═════╝ ╚═╝  ╚═╝╚═════╝
# Ov3rLoRd -- pipeline de production anime autonome (ComfyUI)
# https://github.com/Ov3rLoRd-MLEngineer
#
"""
test_suite.py — Tests Unitaires Complets V1.70
Couvre tous les agents V1.50-V1.70.
Usage :
    python test_suite.py           # tous les tests
    python test_suite.py --quick   # tests rapides seulement
    python test_suite.py --agent scenario  # un agent spécifique
"""

import argparse
import json
import logging
import sys
import io
import time
from pathlib import Path

if hasattr(sys.stdout, "buffer"):
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

logging.basicConfig(level=logging.WARNING)
log = logging.getLogger("test_suite")

PASS  = "✓"
FAIL  = "✗"
WARN  = "⚠"
results = []


def test(name: str, fn):
    t0 = time.time()
    try:
        fn()
        dt = time.time() - t0
        results.append((PASS, name, dt, None))
        print(f"  {PASS} {name} ({dt*1000:.0f}ms)")
        return True
    except AssertionError as e:
        dt = time.time() - t0
        results.append((FAIL, name, dt, str(e)))
        print(f"  {FAIL} {name} — {e}")
        return False
    except Exception as e:
        dt = time.time() - t0
        results.append((FAIL, name, dt, str(e)))
        print(f"  {FAIL} {name} — {type(e).__name__}: {e}")
        return False


# ══════════════════════════════════════════════════════════════════════
# SECTION 1 — Imports de base
# ══════════════════════════════════════════════════════════════════════
def run_imports():
    print("\n── Imports ─────────────────────────────────────────────────")

    def t_overlord_utils():
        from agents.overlord_utils import fallback_llm, safe_json_parse, _get_llm_mode
        assert fallback_llm is not None
        mode = _get_llm_mode()
        assert mode in ("offline", "online", "auto", "grok"), f"Mode inconnu: {mode}"

    def t_context_bus():
        from agents.context_bus import get_bus
        b = get_bus()
        b.write("test.key", 42, agent_id="test")
        assert b.read("test.key") == 42, "Bus read/write failed"

    def t_director():
        from agents.director import get_director
        d = get_director("TestUniverse")
        i = d.set_intent(media_type="anime", universe="TestUniverse", episode=1)
        assert i.mode is not None

    def t_scenario_import():
        from agents.scenario import run_scenario, _fallback_script
        fb = _fallback_script("TestUniverse", "anime")
        assert fb.get("title"), "Fallback script sans titre"
        assert fb.get("acts"),  "Fallback script sans actes"
        assert fb.get("_fallback") is True

    def t_postprod_import():
        from agents.postprod import run_postprod, check_ffmpeg
        assert run_postprod is not None

    def t_supervisor_import():
        import agent_supervisor_v2 as sup
        assert hasattr(sup, "AVAILABLE_LORAS"), "AVAILABLE_LORAS manquant"
        assert len(sup.AVAILABLE_LORAS) >= 3, "Moins de 3 LoRas définies"
        assert hasattr(sup, "run_batch_advanced")

    test("overlord_utils import + mode LLM",  t_overlord_utils)
    test("context_bus singleton read/write",   t_context_bus)
    test("director set_intent",                t_director)
    test("scenario fallback_script",           t_scenario_import)
    test("postprod import",                    t_postprod_import)
    test("agent_supervisor_v2 AVAILABLE_LORAS", t_supervisor_import)


# ══════════════════════════════════════════════════════════════════════
# SECTION 2 — Nouveaux agents V1.50-V1.60
# ══════════════════════════════════════════════════════════════════════
def run_new_agents():
    print("\n── Nouveaux agents V1.50-V1.60 ────────────────────────────")

    def t_grok_client():
        from agents.grok_client import grok_available, _get_grok_key
        # Ne pas tester l'appel réseau — juste l'import et la clé
        avail = grok_available()
        key   = _get_grok_key()
        # Pas d'assertion dure — la clé peut être absente
        assert isinstance(avail, bool)

    def t_prompt_library_init():
        from agents.prompt_library import init_data_structure, load_prompts
        init_data_structure()
        prompts_file = Path("data/prompts/prompts_local.json")
        assert prompts_file.exists(), "prompts_local.json non créé"
        prompts = load_prompts()
        assert isinstance(prompts, list)

    def t_prompt_engineer():
        from agents.prompt_engineer import engineer_jobs, select_lora, _manual_enrich
        # Test sélection LoRa
        lora = select_lora("masterpiece, asuka langley, red plug suit")
        assert "asuka" in lora.lower(), f"LoRa incorrecte pour Asuka: {lora}"

        lora2 = select_lora("masterpiece, rei ayanami, white plug suit")
        assert "rei" in lora2.lower(), f"LoRa incorrecte pour Rei: {lora2}"

        # Test enrichissement manuel
        prompt = _manual_enrich("1girl battle scene", {"shot_type": "close-up", "emotion": "action"})
        assert "masterpiece" in prompt
        assert "close-up" in prompt or "action" in prompt

        # Test engineer_jobs sans LLM
        jobs = [{"positive": "", "_shot_meta": {"description": "test scene", "shot_type": "wide"}}]
        enriched = engineer_jobs(jobs)
        assert len(enriched) == 1
        assert enriched[0].get("positive"), "Job non enrichi"
        assert enriched[0].get("negative"), "Negative absent"

    def t_quality_gate():
        from agents.quality_gate import validate_workflow, auto_fix

        # Workflow valide minimal
        good_wf = {
            "1": {"class_type": "CheckpointLoaderSimple", "inputs": {"ckpt_name": "model.safetensors"}},
            "2": {"class_type": "CLIPTextEncode", "inputs": {"text": "test", "clip": ["1", 1]}},
        }
        result = validate_workflow(good_wf)
        assert result["valid"] is True, f"Workflow valide rejeté: {result['errors']}"

        # Workflow avec nœud fantôme
        bad_wf = {
            "1": {"class_type": None, "inputs": {}},
            "2": {"class_type": "KSampler", "inputs": {"model": ["99", 0]}},
        }
        result_bad = validate_workflow(bad_wf)
        assert result_bad["valid"] is False, "Workflow corrompu non détecté"
        assert len(result_bad["errors"]) > 0

        # Auto-fix
        fixed, n_fixes = auto_fix(bad_wf)
        assert n_fixes > 0, "Auto-fix n'a rien corrigé"
        assert "1" not in fixed, "Nœud fantôme non supprimé"

    def t_session_reporter():
        from agents.session_reporter import collect_run_data, generate_markdown_report
        fake_state = {"data": {"trend_report": {"media_type": "anime"}}, "completed": []}
        data = collect_run_data("test_run_001", fake_state)
        assert "run_id" in data
        assert "timestamp" in data
        md = generate_markdown_report(data)
        assert "Ov3rLoRd" in md
        assert "test_run_001" in md

    def t_auto_sourcing():
        from agents.auto_sourcing import _merge_prompts
        existing = [{"positive": "prompt A", "id": "001"}]
        new_p    = [{"positive": "prompt B", "id": "002"},
                    {"positive": "prompt A", "id": "003"}]  # duplicate
        merged = _merge_prompts(existing, new_p, max_total=100)
        assert len(merged) == 2, f"Déduplification échouée: {len(merged)} au lieu de 2"

    test("grok_client import + clé",       t_grok_client)
    test("prompt_library init + load",     t_prompt_library_init)
    test("prompt_engineer select + enrich", t_prompt_engineer)
    test("quality_gate validate + autofix", t_quality_gate)
    test("session_reporter collect + MD",  t_session_reporter)
    test("auto_sourcing merge_prompts",    t_auto_sourcing)


# ══════════════════════════════════════════════════════════════════════
# SECTION 3 — Agents V1.70
# ══════════════════════════════════════════════════════════════════════
def run_v170_agents():
    print("\n── Agents V1.70 ─────────────────────────────────────────────")

    def t_config_manager():
        from agents.config_manager import get_config
        c = get_config()
        # Valeurs par défaut
        assert c.get("comfyui.steps", 0) == 50, f"Steps par défaut incorrect: {c.get('comfyui.steps')}"
        assert c.get("comfyui.cfg", 0.0) == 6.0
        # Set/get
        c.set("test.value", 999)
        assert c.get("test.value", 0, scope="global") == 999
        # Coercion bool
        c.set("test.bool", "true")
        assert c.get("test.bool", False) is True
        # LoRas JSON
        loras = c.get("loras.available", [])
        assert isinstance(loras, list), f"LoRas pas une liste: {type(loras)}"
        assert len(loras) >= 3

    def t_gpu_optimizer():
        from agents.gpu_optimizer import detect_gpu, get_profile, GPU_PROFILES
        # Tous les profils GPU sont valides
        for name, profile in GPU_PROFILES.items():
            assert "steps" in profile,   f"Profil {name} sans steps"
            assert "width" in profile,   f"Profil {name} sans width"
            assert "sampler_name" in profile
        # detect_gpu retourne une clé valide (ou 'unknown')
        gpu = detect_gpu()
        assert gpu in GPU_PROFILES or gpu == "unknown", f"GPU key invalide: {gpu}"
        profile = get_profile(gpu)
        assert profile["steps"] > 0

    def t_style_continuity():
        from agents.style_continuity import apply_continuity, analyze_drift, EMOTION_PALETTES
        # Palettes définies
        assert "wonder" in EMOTION_PALETTES
        assert "tension" in EMOTION_PALETTES

        # Apply continuity
        jobs = [
            {"positive": "masterpiece, 1girl, action"},
            {"positive": "masterpiece, 1girl, portrait"},
            {"positive": "masterpiece, 1girl, wide shot"},
        ]
        enriched = apply_continuity(jobs, run_id="test_style")
        # Tous les seeds doivent être différents
        seeds = [j.get("seed") for j in enriched]
        assert len(set(seeds)) == len(seeds), "Seeds non uniques"
        # LoRa uniforme sur tout le run
        loras = [j.get("lora") for j in enriched if j.get("lora")]
        assert len(set(loras)) <= 1, f"LoRas non uniformes: {set(loras)}"

        # Analyze drift
        frame_reports = [
            {"drift": 0.1}, {"drift": 0.5},
            {"drift": 0.1}, {"drift": 0.1},
            {"drift": 0.6}, {"drift": 0.1},
        ]
        result = analyze_drift(frame_reports, threshold=0.4)
        assert len(result["drift_frames"]) == 2, f"Ruptures non détectées: {result['drift_frames']}"
        assert result["severity"] in ("high", "critical")

    def t_narrative_memory():
        from agents.narrative_memory import NarrativeMemory, LORA_CHARACTER_MAP
        # Map LoRa définie
        assert "asuka" in LORA_CHARACTER_MAP
        assert "rei" in LORA_CHARACTER_MAP

        mem = NarrativeMemory()
        # Enregistrer un personnage
        mem.register_character("Asuka Langley", "Protagonist", universe="evangelion")
        char = mem.get_character("asuka langley")
        assert char.get("name") == "Asuka Langley"
        assert "asuka" in char.get("lora", "").lower()

        # Contexte de continuation
        fake_script = {
            "title": "Test Episode",
            "logline": "Test logline",
            "synopsis": "Test synopsis",
            "characters": [{"name": "Rei Ayanami", "role": "supporting", "description": "Quiet"}],
            "acts": [],
        }
        mem.extract_from_script(fake_script, "test_001", universe="evangelion")
        ctx = mem.get_continuation_context("evangelion")
        assert "evangelion" in ctx.lower() or "Asuka" in ctx or "Rei" in ctx

    def t_agent_registry():
        from agents.agent_registry import AgentRegistry, _file_checksum
        reg = AgentRegistry()
        # Status sans scan
        status = reg.status()
        assert "total_agents" in status

        # Checksum sur un fichier existant
        test_file = Path("agents/overlord_utils.py")
        if test_file.exists():
            cs = _file_checksum(test_file)
            assert len(cs) == 16, f"Checksum longueur incorrecte: {len(cs)}"

    test("config_manager SQLite",     t_config_manager)
    test("gpu_optimizer profiles",    t_gpu_optimizer)
    test("style_continuity drift",    t_style_continuity)
    test("narrative_memory chars",    t_narrative_memory)
    test("agent_registry status",     t_agent_registry)


# ══════════════════════════════════════════════════════════════════════
# SECTION 4 — Safe JSON parse
# ══════════════════════════════════════════════════════════════════════
def run_json_tests():
    print("\n── safe_json_parse V2 ───────────────────────────────────────")
    from agents.overlord_utils import safe_json_parse

    def t_direct():
        ok, d, _ = safe_json_parse('{"title": "test", "score": 85}')
        assert ok and d["title"] == "test"

    def t_llama3_style():
        raw = 'Here is the JSON:\n{"title": "test", "score": "85"}\nHope this helps!'
        ok, d, _ = safe_json_parse(raw)
        assert ok and d["title"] == "test"

    def t_markdown():
        raw = '```json\n{"title": "test"}\n```'
        ok, d, _ = safe_json_parse(raw)
        assert ok and d["title"] == "test"

    def t_int_cast():
        ok, d, _ = safe_json_parse('{"score_global": "83"}')
        assert ok
        score = int(d.get("score_global", 0))
        assert score == 83

    def t_array():
        ok, d, _ = safe_json_parse('[{"id": "001"}, {"id": "002"}]')
        assert ok and isinstance(d, list) and len(d) == 2

    def t_invalid():
        ok, d, err = safe_json_parse("Pas de JSON ici du tout")
        assert not ok and d is None

    test("JSON direct",          t_direct)
    test("JSON style llama3",    t_llama3_style)
    test("JSON markdown blocks", t_markdown)
    test("score int cast",       t_int_cast)
    test("JSON array",           t_array)
    test("JSON invalide → False", t_invalid)




# ══════════════════════════════════════════════════════════════════════
# SECTION 5 — Quality Reviewer V1.70
# ══════════════════════════════════════════════════════════════════════
def run_quality_reviewer():
    print("\n── Quality Reviewer V1.70 ───────────────────────────────────")

    def t_import():
        from agents.quality_reviewer import get_reviewer, score_sharpness, score_narrative
        r = get_reviewer(target=80.0)
        assert r is not None
        assert r.target == 80.0

    def t_score_narrative():
        from agents.quality_reviewer import score_narrative
        job_full = {"_shot_meta": {"description": "test", "shot_type": "close-up",
                                    "emotion": "action", "characters": "Asuka", "act": 1}}
        score = score_narrative(job_full)
        assert score >= 90.0, f"Score narratif complet trop bas: {score}"

        job_empty = {"_shot_meta": {}}
        score_empty = score_narrative(job_empty)
        assert score_empty == 75.0, f"Score narratif vide incorrect: {score_empty}"

    def t_suggest_adjustment():
        from agents.quality_reviewer import get_reviewer
        r = get_reviewer(target=90.0)
        fake_result = {
            "score": 55.0, "pass": False, "target": 90.0,
            "detail": {"sharpness": 30.0, "style_drift": 80.0,
                       "prompt_match": 75.0, "narrative": 80.0},
            "image_path": "fake.png", "timestamp": "2026-06-20", "error": ""
        }
        job = {"positive": "masterpiece, 1girl", "seed": 42, "lora": ""}
        adjusted = r.suggest_adjustment(fake_result, job)
        assert "sharp focus" in adjusted["positive"], "Ajustement netteté non appliqué"
        assert adjusted["seed"] != 42, "Seed non modifié"

    def t_run_stats_empty():
        from agents.quality_reviewer import QualityReviewer
        r = QualityReviewer(target_score=90.0)
        stats = r.run_stats()
        assert stats["total"] == 0
        assert stats["pass_rate"] == 0.0

    def t_weights_sum():
        from agents.quality_reviewer import WEIGHTS
        total = sum(WEIGHTS.values())
        assert abs(total - 1.0) < 0.001, f"Somme des poids != 1.0 : {total}"

    test("quality_reviewer import + target",   t_import)
    test("score_narrative full vs empty",       t_score_narrative)
    test("suggest_adjustment sharpness fix",    t_suggest_adjustment)
    test("run_stats empty session",             t_run_stats_empty)
    test("WEIGHTS somme = 1.0",                 t_weights_sum)

# ══════════════════════════════════════════════════════════════════════
# MAIN
# ══════════════════════════════════════════════════════════════════════
if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Ov3rLoRd Test Suite V1.70")
    parser.add_argument("--quick",  action="store_true", help="Tests rapides seulement")
    parser.add_argument("--agent",  type=str, default="", help="Tester un agent spécifique")
    args = parser.parse_args()

    print("=" * 60)
    print("  Ov3rLoRd Test Suite V1.70")
    print("=" * 60)

    t0 = time.time()

    if args.quick:
        run_imports()
        run_json_tests()
    elif args.agent:
        print(f"\nTest ciblé : {args.agent}")
        run_imports()
    else:
        run_imports()
        run_json_tests()
        run_new_agents()
        run_v170_agents()
        run_quality_reviewer()

    # Bilan
    total    = len(results)
    passed   = sum(1 for r in results if r[0] == PASS)
    failed   = sum(1 for r in results if r[0] == FAIL)
    duration = time.time() - t0

    print("\n" + "=" * 60)
    print(f"  BILAN : {passed}/{total} PASS | {failed} FAIL | {duration:.1f}s")
    print("=" * 60)

    if failed > 0:
        print("\nÉchecs :")
        for r in results:
            if r[0] == FAIL:
                print(f"  {FAIL} {r[1]} — {r[3]}")
        sys.exit(1)
    else:
        print(f"\n  Tous les tests passent.")
        sys.exit(0)

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
test_integration.py — Tests flux de donnees end-to-end Ov3rLoRd V1.49
Verifie que les agents communiquent correctement entre eux.

Usage :
  python test_integration.py           # tous les tests
  python test_integration.py --quick   # tests sans LLM
  python test_integration.py --verbose # avec details
"""
import sys
import os
import time
import json
import logging
import argparse
from pathlib import Path
from datetime import datetime

# Force UTF-8 pour ce script
import io
if hasattr(sys.stdout, 'buffer'):
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

logging.basicConfig(level=logging.WARNING,
                    format="%(asctime)s [%(levelname)s] %(message)s")

RESULTS: list[dict] = []

def test(name: str):
    """Decorateur de test."""
    def decorator(fn):
        def wrapper(*args, **kwargs):
            start = time.perf_counter()
            try:
                fn(*args, **kwargs)
                elapsed = time.perf_counter() - start
                RESULTS.append({"name": name, "status": "PASS", "elapsed": elapsed})
                print(f"  [PASS] {name} ({elapsed:.2f}s)")
            except AssertionError as e:
                elapsed = time.perf_counter() - start
                RESULTS.append({"name": name, "status": "FAIL", "error": str(e), "elapsed": elapsed})
                print(f"  [FAIL] {name} : {e}")
            except Exception as e:
                elapsed = time.perf_counter() - start
                RESULTS.append({"name": name, "status": "ERROR", "error": str(e), "elapsed": elapsed})
                print(f"  [ERR ] {name} : {type(e).__name__}: {e}")
        return wrapper
    return decorator

# ── Tests Context Bus ─────────────────────────────────────────────────────────
@test("ContextBus : import et singleton")
def test_context_bus_import():
    from agents.context_bus import get_bus
    b1 = get_bus()
    b2 = get_bus()
    assert b1 is b2, "get_bus() doit retourner le meme singleton"

@test("ContextBus : write/read cycle")
def test_context_bus_rw():
    from agents.context_bus import get_bus
    bus = get_bus()
    bus.write("test.integration", "hello_v149", agent_id="test")
    val = bus.read("test.integration")
    assert val == "hello_v149", f"Attendu 'hello_v149', recu '{val}'"

@test("ContextBus : get_context_for filtre les cles")
def test_context_bus_context():
    from agents.context_bus import get_bus
    bus = get_bus()
    bus.write("director.emotion_arc", "tension", agent_id="director")
    ctx = bus.get_context_for("storyboard")
    assert isinstance(ctx, dict), "get_context_for doit retourner un dict"

# ── Tests Director ────────────────────────────────────────────────────────────
@test("Director : import et initialisation")
def test_director_import():
    from agents.director import get_director
    d = get_director("TestSeries_Integration")
    assert d is not None

@test("Director : set_intent produit une intention valide")
def test_director_intent():
    from agents.director import get_director
    d = get_director("TestSeries_Integration")
    intent = d.set_intent(media_type="anime", universe="TestUniverse", episode=1)
    assert hasattr(intent, "mode"),              "intent doit avoir .mode"
    assert hasattr(intent, "quality_threshold"), "intent doit avoir .quality_threshold"
    assert 50 <= intent.quality_threshold <= 100, f"Seuil hors plage : {intent.quality_threshold}"

@test("Director -> ContextBus : intention publiee sur le bus")
def test_director_publishes_to_bus():
    from agents.director import get_director
    from agents.context_bus import get_bus
    d   = get_director("TestSeries_Integration")
    d.set_intent(media_type="anime", universe="TestUniverse", episode=2)
    bus = get_bus()
    mode = bus.read("director.mode")
    assert mode is not None, "director.mode doit etre publie sur le bus"

# ── Tests EmotionEngine ───────────────────────────────────────────────────────
@test("EmotionEngine : import et parametres")
def test_emotion_engine():
    from agents.emotion_engine import get_emotion_engine
    eng = get_emotion_engine()
    params = eng.get_comfy_params("tension")
    assert "cfg" in params,     "params doit avoir cfg"
    assert "steps" in params,   "params doit avoir steps"
    assert "palette" in params, "params doit avoir palette"
    assert params["cfg"] > 0

@test("EmotionEngine : enrich_shot ajoute les parametres")
def test_emotion_enrich_shot():
    from agents.emotion_engine import get_emotion_engine
    eng  = get_emotion_engine()
    shot = {"prompt": "battle scene", "negative_prompt": "blur"}
    enriched = eng.enrich_shot(shot, "tension")
    assert "cfg_scale"   in enriched
    assert "emotion_tag" in enriched
    assert enriched["emotion_tag"] == "tension"

# ── Tests WorldModel ──────────────────────────────────────────────────────────
@test("WorldModel : import et enregistrement entite")
def test_world_model():
    from agents.world_model import get_world_model
    wm = get_world_model("test_integration_series")
    wm.register_entity("Goku", "character", {"hair_color": "black"})
    entity = wm.get_entity("Goku")
    assert entity.get("type") == "character"

@test("WorldModel : validate_and_fix_prompt enrichit le prompt")
def test_world_model_prompt():
    from agents.world_model import get_world_model
    wm = get_world_model("test_integration_series")
    wm.register_entity("Vegeta", "character", {"hair_color": "dark"})
    prompt, warns = wm.validate_and_fix_prompt("standing pose", "Vegeta")
    assert "dark" in prompt.lower(), f"Couleur non injectee : '{prompt}'"

# ── Tests API Server ──────────────────────────────────────────────────────────
@test("ApiServer : import Flask et app")
def test_api_server_import():
    try:
        from agents.api_server import app, FLASK_OK
        assert FLASK_OK, "Flask non disponible — pip install flask"
        client = app.test_client()
        resp   = client.get("/status")
        assert resp.status_code == 200
        data   = json.loads(resp.data)
        assert data["version"] == "V1.49"
    except ImportError as e:
        raise AssertionError(f"Import echoue : {e}")

# ── Tests Deploy ──────────────────────────────────────────────────────────────
@test("Deploy : import et validation args")
def test_deploy_import():
    import deploy
    assert hasattr(deploy, "deploy"), "deploy.py doit exposer la fonction deploy()"
    assert hasattr(deploy, "PROTECTED")

# ── Rapport ───────────────────────────────────────────────────────────────────
def print_report(verbose: bool = False):
    total  = len(RESULTS)
    passed = sum(1 for r in RESULTS if r["status"] == "PASS")
    failed = sum(1 for r in RESULTS if r["status"] in ("FAIL", "ERROR"))
    elapsed_total = sum(r["elapsed"] for r in RESULTS)

    print("\n" + "=" * 60)
    print(f"  Ov3rLoRd Integration Tests V1.49")
    print(f"  Resultat : {passed}/{total} PASS | {failed} ECHEC | {elapsed_total:.2f}s")
    print("=" * 60)

    if failed > 0:
        print("\n  Echecs :")
        for r in RESULTS:
            if r["status"] in ("FAIL", "ERROR"):
                print(f"    [{r['status']}] {r['name']}")
                if verbose and r.get("error"):
                    print(f"           {r['error']}")

    # Sauvegarde JSON
    out = Path("workspace/logs/integration_results.json")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(
        json.dumps({"timestamp": datetime.now().isoformat(), "results": RESULTS},
                   ensure_ascii=False, indent=2),
        encoding="utf-8"
    )
    print(f"\n  Rapport : {out}")
    return failed

def main():
    p = argparse.ArgumentParser()
    p.add_argument("--quick",   action="store_true", help="Sans tests LLM")
    p.add_argument("--verbose", action="store_true")
    args = p.parse_args()

    print("=" * 60)
    print("  Ov3rLoRd — Tests d'integration V1.49")
    print("=" * 60)

    # Tests toujours lances
    test_context_bus_import()
    test_context_bus_rw()
    test_context_bus_context()
    test_director_import()
    test_director_intent()
    test_director_publishes_to_bus()
    test_emotion_engine()
    test_emotion_enrich_shot()
    test_world_model()
    test_world_model_prompt()
    test_api_server_import()
    test_deploy_import()

    failed = print_report(verbose=args.verbose)
    sys.exit(0 if failed == 0 else 1)

if __name__ == "__main__":
    main()
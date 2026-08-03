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
test_pipeline.py — Suite de tests automatiques V1.42
Lance avant chaque run pour valider l'environnement.

Usage :
    python test_pipeline.py           # tous les tests
    python test_pipeline.py --quick   # tests rapides uniquement
    python test_pipeline.py --fix     # tente de corriger les problèmes
"""

import sys
import os
import json
import time
import argparse
import logging
from pathlib import Path
from datetime import datetime

import io
if hasattr(sys.stdout, 'buffer') and getattr(sys.stdout, 'encoding','').lower() != 'utf-8':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

# ── Charte graphique Ov3rLoRd ─────────────────────────────────────────
try:
    import colorama; colorama.init()
    C_GREEN  = "\033[92m"
    C_YELLOW = "\033[93m"
    C_RED    = "\033[91m"
    C_CYAN   = "\033[96m"
    C_BLUE   = "\033[94m"
    C_MAGENTA= "\033[95m"
    C_BOLD   = "\033[1m"
    C_DIM    = "\033[2m"
    C_RESET  = "\033[0m"
except ImportError:
    C_GREEN=C_YELLOW=C_RED=C_CYAN=C_BLUE=C_MAGENTA=C_BOLD=C_DIM=C_RESET=""


# Forcer le bon path
BASE_DIR = Path(__file__).resolve().parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

# Alias agents si nécessaire
_agents_lower = BASE_DIR / "agents"
_agents_upper = BASE_DIR / "AGENTS"
if not _agents_lower.exists() and _agents_upper.exists():
    import importlib, types
    _pkg = types.ModuleType("agents")
    _pkg.__path__ = [str(_agents_upper)]
    sys.modules["agents"] = _pkg

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)-8s] %(message)s",
    datefmt="%H:%M:%S"
)
log = logging.getLogger("test_pipeline")

# ── Résultats ─────────────────────────────────────────────────────────
PASS = "✓ PASS"
FAIL = "✗ FAIL"
WARN = "⚠ WARN"
SKIP = "○ SKIP"

results = []

def test(name: str, fn, quick: bool = False, is_quick: bool = False):
    """Exécute un test et enregistre le résultat."""
    if quick and not is_quick:
        results.append((SKIP, name, "skipped (--quick)"))
        return
    try:
        status, detail = fn()
        results.append((status, name, detail))
        log.info(f"{status} — {name}" + (f" : {detail}" if detail else ""))
    except Exception as e:
        results.append((FAIL, name, str(e)))
        log.error(f"{FAIL} — {name} : {e}")

# ── Tests ─────────────────────────────────────────────────────────────

def check_python_version():
    v = sys.version_info
    if v.major == 3 and v.minor >= 10:
        return PASS, f"Python {v.major}.{v.minor}.{v.micro}"
    return WARN, f"Python {v.major}.{v.minor} — recommandé 3.10+"

def check_agents_dir():
    agents = BASE_DIR / "agents"
    AGENTS = BASE_DIR / "AGENTS"
    if agents.exists():
        return PASS, f"{agents} — {len(list(agents.glob('*.py')))} fichiers"
    if AGENTS.exists():
        return WARN, "Dossier 'AGENTS' en majuscules — renommer en 'agents'"
    return FAIL, "Dossier agents/ introuvable"

def check_init_py():
    init = BASE_DIR / "agents" / "__init__.py"
    if not init.exists():
        return FAIL, "__init__.py manquant dans agents/"
    size = init.stat().st_size
    if size < 100:
        return FAIL, f"__init__.py vide ({size} octets)"
    return PASS, f"{size} octets"

def check_env_file():
    env = BASE_DIR / ".env"
    if not env.exists():
        return WARN, ".env absent — crée-le depuis .env.template"
    key = ""
    for line in env.read_text(encoding="utf-8").splitlines():
        if line.startswith("ANTHROPIC_API_KEY="):
            key = line.split("=", 1)[1].strip()
    if not key:
        key = os.environ.get("ANTHROPIC_API_KEY", "")
    if not key:
        return WARN, "ANTHROPIC_API_KEY non définie"
    if len(key) < 20:
        return FAIL, "ANTHROPIC_API_KEY semble invalide (trop courte)"
    return PASS, f"Clé détectée ({key[:8]}...)"

def check_api_key_env():
    key = os.environ.get("ANTHROPIC_API_KEY", "")
    if key:
        return PASS, f"Variable d'environnement définie ({key[:8]}...)"
    return WARN, "ANTHROPIC_API_KEY absent de l'environnement (setx requis)"

def check_import_agents():
    try:
        import agents
        return PASS, f"Package agents chargé : {agents.__file__}"
    except ImportError as e:
        return FAIL, str(e)

def check_import_sourcing():
    try:
        from agents.sourcing import run_sourcing
        return PASS, "run_sourcing importé"
    except ImportError as e:
        return FAIL, str(e)

def check_import_scenario():
    try:
        from agents.scenario import run_scenario
        return PASS, "run_scenario importé"
    except ImportError as e:
        return FAIL, str(e)

def check_import_critic():
    try:
        from agents.critic import CriticAgent, Verdict
        return PASS, "CriticAgent importé"
    except ImportError as e:
        return FAIL, str(e)

def check_import_watchdog():
    try:
        from agents.watchdog import Watchdog
        return PASS, "Watchdog importé"
    except ImportError as e:
        return FAIL, str(e)

def check_workspace():
    ws = BASE_DIR / "workspace"
    required = ["logs", "scripts", "storyboards", "checkpoints"]
    missing = [d for d in required if not (ws / d).exists()]
    if missing:
        for d in missing:
            (ws / d).mkdir(parents=True, exist_ok=True)
        return WARN, f"Dossiers créés : {missing}"
    return PASS, "workspace/ structure OK"

def check_comfyui():
    try:
        import requests
        r = requests.get("http://127.0.0.1:8188/system_stats", timeout=3)
        if r.status_code == 200:
            stats = r.json()
            devices = stats.get("devices", [])
            gpu = devices[0].get("name", "GPU") if devices else "?"
            return PASS, f"ComfyUI en ligne — GPU: {gpu}"
        return WARN, f"ComfyUI HTTP {r.status_code}"
    except Exception:
        return WARN, "ComfyUI hors ligne (normal si pas lancé)"

def check_ollama():
    try:
        import requests
        r = requests.get("http://localhost:11434/api/tags", timeout=3)
        if r.status_code == 200:
            models = [m["name"].split(":")[0] for m in r.json().get("models", [])]
            return PASS, f"Ollama en ligne — modèles: {models}"
        return WARN, "Ollama hors ligne"
    except Exception:
        return WARN, "Ollama non disponible (optionnel)"

def check_ffmpeg():
    import shutil
    if shutil.which("ffmpeg"):
        return PASS, "ffmpeg dans le PATH"
    return WARN, "ffmpeg absent — post-production désactivée"

def check_requirements():
    try:
        req_file = BASE_DIR / "requirements.txt"
        if not req_file.exists():
            return SKIP, "requirements.txt absent"
        reqs = req_file.read_text(encoding="utf-8").splitlines()
        missing = []
        for req in reqs:
            pkg = req.split(">=")[0].split("==")[0].strip()
            if not pkg or pkg.startswith("#"):
                continue
            try:
                __import__(pkg.replace("-", "_"))
            except ImportError:
                missing.append(pkg)
        if missing:
            return WARN, f"Packages manquants : {missing[:5]}"
        return PASS, f"{len(reqs)} packages vérifiés"
    except Exception as e:
        return WARN, str(e)

def check_maestro():
    maestro = BASE_DIR / "maestro.py"
    if not maestro.exists():
        return FAIL, "maestro.py introuvable à la racine"
    size = maestro.stat().st_size
    return PASS, f"maestro.py présent ({size//1024}Ko)"

# ── Runner ────────────────────────────────────────────────────────────
def main():
    parser = argparse.ArgumentParser(description="OverLord Pipeline Test Suite V1.42")
    parser.add_argument("--quick", action="store_true", help="Tests rapides uniquement")
    parser.add_argument("--fix",   action="store_true", help="Tenter de corriger les problèmes")
    args = parser.parse_args()

    print("\n" + "═"*60)
    print("  Ov3rLoRd Pipeline — Test Suite V1.42")
    print(f"  {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("═"*60 + "\n")

    q = args.quick

    # Tests critiques (toujours exécutés)
    test("Python version",         check_python_version,    is_quick=True)
    test("Dossier agents/",        check_agents_dir,        is_quick=True)
    test("__init__.py agents",     check_init_py,           is_quick=True)
    test("maestro.py racine",      check_maestro,           is_quick=True)
    test("Clé API (environ)",      check_api_key_env,       is_quick=True)
    test("Clé API (.env)",         check_env_file,          is_quick=True)
    test("Import agents",          check_import_agents,     is_quick=True)
    test("Import sourcing",        check_import_sourcing,   is_quick=True)
    test("Import scenario",        check_import_scenario,   is_quick=True)
    test("Import critic",          check_import_critic,     is_quick=True)
    test("Import watchdog",        check_import_watchdog,   is_quick=True)
    test("Workspace structure",    check_workspace,         is_quick=True)

    # Tests optionnels (skippés avec --quick)
    test("ComfyUI",                check_comfyui,           quick=q)
    test("Ollama local",           check_ollama,            quick=q)
    test("ffmpeg",                 check_ffmpeg,            quick=q)
    test("Requirements",           check_requirements,      quick=q)

    # Résumé
    passed = sum(1 for r in results if r[0] == PASS)
    warned = sum(1 for r in results if r[0] == WARN)
    failed = sum(1 for r in results if r[0] == FAIL)
    total  = len([r for r in results if r[0] != SKIP])

    print("\n" + "═"*60)
    print(f"  RÉSULTAT : {passed}/{total} PASS | {warned} WARN | {failed} FAIL")

    if failed == 0 and warned == 0:
        print("  ✓ Pipeline prêt — lance : python maestro.py --media-type anime")
    elif failed == 0:
        print("  ⚠ Pipeline fonctionnel avec avertissements")
        print("    Lance : python maestro.py --media-type anime")
    else:
        print("  ✗ Problèmes critiques détectés — corrige avant de lancer")

    print("═"*60 + "\n")

    # Sauvegarder le rapport
    report_dir = Path("workspace/logs")
    report_dir.mkdir(parents=True, exist_ok=True)
    report = {
        "timestamp": datetime.now().isoformat(),
        "results": [{"status": r[0], "test": r[1], "detail": r[2]} for r in results],
        "summary": {"passed": passed, "warned": warned, "failed": failed}
    }
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    (report_dir / f"test_{ts}.json").write_text(
        json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8"
    )

    return 0 if failed == 0 else 1

if __name__ == "__main__":
    sys.exit(main())

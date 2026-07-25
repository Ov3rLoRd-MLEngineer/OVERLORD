"""
self_improve.py — Moteur d'Auto-Amelioration Locale V1.43
Observe -> Reflect -> Propose -> Validate -> Apply -> Learn

FIX V1.49h :
  - break outside loop dans _basic_fix() ligne 396 corrige
  - box-drawing remplaces par ASCII dans les prints/logs
  - UTF-8 force au demarrage
"""

import ast
import json
import logging
import os
import shutil
import sys
import time
import hashlib
from pathlib import Path
from datetime import datetime
from typing import Optional

import io as _io
if hasattr(sys.stdout, 'buffer') and getattr(sys.stdout, 'encoding','').lower() != 'utf-8':
    sys.stdout = _io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
if hasattr(sys.stderr, 'buffer') and getattr(sys.stderr, 'encoding','').lower() != 'utf-8':
    sys.stderr = _io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')

try:
    import colorama; colorama.init()
    C_GREEN   = "\033[92m"
    C_YELLOW  = "\033[93m"
    C_RED     = "\033[91m"
    C_CYAN    = "\033[96m"
    C_BLUE    = "\033[94m"
    C_MAGENTA = "\033[95m"
    C_BOLD    = "\033[1m"
    C_DIM     = "\033[2m"
    C_RESET   = "\033[0m"
except ImportError:
    C_GREEN=C_YELLOW=C_RED=C_CYAN=C_BLUE=C_MAGENTA=C_BOLD=C_DIM=C_RESET=""


BASE_DIR = Path(__file__).resolve().parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))
_REPO_ROOT = BASE_DIR.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))
import config

try:
    from agents.overlord_utils import fallback_llm, safe_json_parse, get_api_key
    UTILS_OK = True
except ImportError:
    UTILS_OK = False

log = logging.getLogger("self_improve")

try:
    from agents.v130_intelligence_ext import IntelligenceExtV130
    _intel = IntelligenceExtV130()
    INTEL_OK = True
except Exception:
    INTEL_OK = False
    _intel = None

ARCHIVE_DRIVES = [
    Path("E:/OVERLORD_LOGS"),
    Path("G:/OVERLORD_LOGS"),
    config.WORKSPACE_DIR / "logs" / "improve",
]

def setup_improve_logging(run_id: str = None) -> logging.Logger:
    ts     = run_id or datetime.now().strftime("%Y%m%d_%H%M%S")
    logger = logging.getLogger(f"self_improve.{ts}")
    logger.setLevel(logging.DEBUG)
    fmt    = logging.Formatter("%(asctime)s [%(levelname)-8s] %(message)s",
                               "%Y-%m-%d %H:%M:%S")
    ch = logging.StreamHandler(sys.stdout)
    ch.setLevel(logging.INFO)
    ch.setFormatter(fmt)
    logger.addHandler(ch)

    local_dir = BASE_DIR / "workspace" / "logs" / "improve"
    local_dir.mkdir(parents=True, exist_ok=True)
    fh = logging.FileHandler(local_dir / f"improve_{ts}.log", encoding="utf-8")
    fh.setLevel(logging.DEBUG)
    fh.setFormatter(fmt)
    logger.addHandler(fh)

    for drive in ARCHIVE_DRIVES:
        try:
            drive.mkdir(parents=True, exist_ok=True)
            dh = logging.FileHandler(drive / f"improve_{ts}.log", encoding="utf-8")
            dh.setLevel(logging.DEBUG)
            dh.setFormatter(fmt)
            logger.addHandler(dh)
        except Exception:
            pass

    return logger


def write_structured_log(entry: dict):
    entry["timestamp"] = datetime.now().isoformat()
    line = json.dumps(entry, ensure_ascii=False) + "\n"
    destinations = [BASE_DIR / "workspace" / "self_improve" / "MASTER_LOG.jsonl"] + \
                   [d / "MASTER_LOG.jsonl" for d in ARCHIVE_DRIVES]
    for dest in destinations:
        try:
            dest.parent.mkdir(parents=True, exist_ok=True)
            with open(dest, "a", encoding="utf-8") as f:
                f.write(line)
        except Exception:
            pass


IMPROVE_DIR  = BASE_DIR / "workspace" / "self_improve"
BACKUP_DIR   = IMPROVE_DIR / "backups"
MEMORY_FILE  = IMPROVE_DIR / "improvement_memory.json"
METRICS_FILE = BASE_DIR / "workspace" / "logs"

MAX_PATCHES_PER_SESSION = 5
MAX_FILE_SIZE_CHANGE    = 0.30
PROTECTED_FILES = {
    "self_improve.py",
    "licence_server.py",
    "config.json",
    ".env",
}
ALLOWED_DIRS = {"agents", "."}


# ====================================================================
# 1. OBSERVE
# ====================================================================
class Observer:

    def get_creative_fatigue(self) -> dict:
        try:
            from agents.v130_intelligence_ext import CreativeFatigueDetector
            detector = CreativeFatigueDetector()
            fatigue  = detector.get_fatigue_level()
            level    = fatigue.get("level", "unknown")
            score    = fatigue.get("score", 0.0)
            log.info(f"[SELF-IMPROVE] Fatigue creative : {level} ({score:.0%})")
            return fatigue
        except Exception as e:
            log.debug(f"[SELF-IMPROVE] CreativeFatigue indisponible : {e}")
            return {"level": "unknown", "score": 0.0}

    def collect_run_metrics(self) -> dict:
        metrics = []
        logs_dir = METRICS_FILE
        if not logs_dir.exists():
            return {"test_metrics": metrics, "error_patterns": []}

        for log_file in sorted(logs_dir.glob("*.json"))[-20:]:
            try:
                data = json.loads(log_file.read_text(encoding="utf-8"))
                metrics.append({
                    "file":      log_file.name,
                    "timestamp": data.get("timestamp", ""),
                    "results":   data.get("results", []),
                    "summary":   data.get("summary", {}),
                })
            except Exception:
                pass

        error_patterns = []
        for log_file in sorted(logs_dir.glob("maestro_*.log"))[-5:]:
            try:
                content = log_file.read_text(encoding="utf-8", errors="ignore")
                errors  = [l for l in content.split('\n') if '[ERROR' in l]
                if errors:
                    error_patterns.append({"file": log_file.name, "errors": errors[:10]})
            except Exception:
                pass

        return {"test_metrics": metrics, "error_patterns": error_patterns}

    def scan_code_quality(self, agents_dir: Path = None) -> dict:
        issues   = {"critical": [], "warnings": [], "todos": []}
        scan_dir = agents_dir or BASE_DIR / "agents"
        if not scan_dir.exists():
            return issues

        for fpath in sorted(scan_dir.glob("*.py")):
            try:
                src   = fpath.read_text(encoding="utf-8")
                fname = fpath.name

                try:
                    ast.parse(src)
                except SyntaxError as e:
                    issues["critical"].append({"file": fname, "issue": f"SyntaxError: {e}"})

                if "ANTHROPIC_URL" in src and "x-api-key" not in src and "_get_api_key" not in src:
                    issues["critical"].append({"file": fname, "issue": "x-api-key manquant"})

                for line in src.split("\n"):
                    if line.strip().startswith("from agents") and \
                       "try:" not in src[max(0, src.find(line)-100):src.find(line)]:
                        issues["warnings"].append(
                            {"file": fname, "issue": f"Import sans try/except: {line.strip()}"}
                        )

                for i, line in enumerate(src.split("\n")):
                    for marker in ["TODO", "FIXME", "HACK"]:
                        if marker in line:
                            issues["todos"].append(
                                {"file": fname, "line": i+1, "text": line.strip()[:80]}
                            )
            except Exception as e:
                issues["warnings"].append({"file": fname, "issue": str(e)})

        return issues


# ====================================================================
# 2. REFLECT
# ====================================================================
class Reflector:

    def reflect(self, metrics: dict, code_issues: dict) -> dict:
        n_critical = len(code_issues.get("critical", []))
        n_warnings = len(code_issues.get("warnings", []))
        n_todos    = len(code_issues.get("todos", []))
        errors_sample = []
        for ep in metrics.get("error_patterns", [])[:3]:
            errors_sample.extend(ep.get("errors", [])[:3])

        prompt = (
            f"Tu es l'agent d'auto-amelioration d'Ov3rLoRd Pipeline.\n"
            f"Analyse l'etat du systeme et propose les 3 ameliorations les plus impactantes.\n\n"
            f"ETAT DU CODE :\n"
            f"- {n_critical} problemes critiques\n"
            f"- {n_warnings} avertissements\n"
            f"- {n_todos} TODOs non resolus\n\n"
            f"ERREURS RECENTES :\n"
            f"{chr(10).join(errors_sample[:6]) if errors_sample else 'Aucune erreur recente'}\n\n"
            f"PROBLEMES CRITIQUES :\n"
            f"{json.dumps(code_issues.get('critical', [])[:5], ensure_ascii=False)}\n\n"
            f"Retourne UNIQUEMENT ce JSON (pas de backticks) :\n"
            '{{"system_health":"critical|degraded|stable|optimal","health_score":0,'
            '"top_improvements":[{{"priority":1,"target_file":"nom.py","issue":"",'
            '"fix_type":"add_function|fix_import|add_error_handling|refactor",'
            '"fix_description":"","impact":"high|medium|low","safe_to_auto_apply":true}}],'
            '"learning_insight":""}}'
        )

        if UTILS_OK:
            raw = fallback_llm(prompt, max_tokens=1000, logger=log)
            ok, data, _ = safe_json_parse(raw, logger=log)
            if ok and data:
                return data

        improvements = []
        for issue in code_issues.get("critical", [])[:3]:
            improvements.append({
                "priority":           len(improvements) + 1,
                "target_file":        issue.get("file", ""),
                "issue":              issue.get("issue", ""),
                "fix_type":           "fix_auth" if "x-api-key" in issue.get("issue","") else "fix_syntax",
                "fix_description":    "Ajouter _get_api_key() et header x-api-key",
                "impact":             "high",
                "safe_to_auto_apply": True,
            })

        return {
            "system_health":    "critical" if n_critical > 0 else "stable",
            "health_score":     max(0, 100 - n_critical * 20 - n_warnings * 2),
            "top_improvements": improvements,
            "learning_insight": f"{n_critical} problemes critiques detectes",
        }


# ====================================================================
# 3. PROPOSE
# ====================================================================
class Proposer:

    def propose_fix(self, improvement: dict, current_code: str) -> Optional[str]:
        fname    = improvement.get("target_file", "")
        issue    = improvement.get("issue", "")
        fix_desc = improvement.get("fix_description", "")

        if not UTILS_OK:
            log.warning("[PROPOSER] LLM indisponible — correctif basique")
            return self._basic_fix(improvement, current_code)

        prompt = (
            f"Expert Python. Corrige ce fichier selon les instructions.\n\n"
            f"FICHIER : {fname}\n"
            f"PROBLEME : {issue}\n"
            f"CORRECTION : {fix_desc}\n\n"
            f"CODE ACTUEL :\n{current_code[:3000]}\n\n"
            f"REGLES :\n"
            f"1. Retourne UNIQUEMENT le code Python corrige, complet, sans backticks\n"
            f"2. Ne modifie QUE ce qui est necessaire\n"
            f"3. Conserve toute la logique existante\n"
            f"4. Code syntaxiquement valide"
        )

        raw = fallback_llm(prompt, max_tokens=4000, logger=log)
        if raw and len(raw) > 100:
            clean = raw.strip()
            if clean.startswith("```"):
                lines = clean.split("\n")
                clean = "\n".join(lines[1:-1] if lines[-1].strip() == "```" else lines[1:])
            return clean.strip()

        return self._basic_fix(improvement, current_code)

    def _basic_fix(self, improvement: dict, src: str) -> Optional[str]:
        """
        Correctifs automatiques sans LLM.
        FIX V1.49h : break dans deux boucles for imbriquees — syntaxe valide.
        """
        fix_type = improvement.get("fix_type", "")

        GET_API_KEY = '''
def _get_api_key() -> str:
    import os as _os
    from pathlib import Path as _P
    key = _os.environ.get("ANTHROPIC_API_KEY", "")
    if not key:
        for env in [_P(__file__).parent / ".env", _P(__file__).parent.parent / ".env"]:
            if env.exists():
                for line in env.read_text(encoding="utf-8").splitlines():
                    if line.startswith("ANTHROPIC_API_KEY="):
                        key = line.split("=",1)[1].strip().strip('"').strip("'")
                        break  # break dans for line -> valide
            if key:
                break  # break dans for env -> valide
    return key
'''

        if "x-api-key" in improvement.get("issue", "") or fix_type == "fix_auth":
            anchor = 'ANTHROPIC_URL = "https://api.anthropic.com/v1/messages"'
            if anchor in src and "_get_api_key" not in src:
                src = src.replace(anchor, anchor + "\n" + GET_API_KEY)
                for p in ['            headers={"Content-Type": "application/json"},',
                          'headers={"Content-Type": "application/json"},']:
                    if p in src:
                        indent = p[:len(p) - len(p.lstrip())]
                        src = src.replace(p,
                            indent + 'headers={\n' +
                            indent + '    "Content-Type": "application/json",\n' +
                            indent + '    "x-api-key": _get_api_key(),\n' +
                            indent + '    "anthropic-version": "2023-06-01",\n' +
                            indent + '},')
                        break
                return src
        return None


# ====================================================================
# 4. VALIDATE
# ====================================================================
class Validator:

    def validate(self, fname: str, original: str, patched: str) -> tuple:
        try:
            ast.parse(patched)
        except SyntaxError as e:
            return False, f"SyntaxError: {e}"

        orig_size  = len(original)
        patch_size = len(patched)
        if orig_size > 0:
            ratio = abs(patch_size - orig_size) / orig_size
            if ratio > MAX_FILE_SIZE_CHANGE:
                return False, f"Changement taille trop important : {ratio:.0%} (max {MAX_FILE_SIZE_CHANGE:.0%})"

        if fname in PROTECTED_FILES:
            return False, f"Fichier protege : {fname}"

        danger_patterns = [
            "os.system(", "subprocess.call(", "eval(", "exec(",
            "__import__('os').system", "shutil.rmtree(BASE",
        ]
        for pattern in danger_patterns:
            if pattern in patched and pattern not in original:
                return False, f"Pattern dangereux detecte : {pattern}"

        orig_tree   = ast.parse(original)
        patch_tree  = ast.parse(patched)
        orig_funcs  = {n.name for n in ast.walk(orig_tree)  if isinstance(n, ast.FunctionDef)}
        patch_funcs = {n.name for n in ast.walk(patch_tree) if isinstance(n, ast.FunctionDef)}
        missing     = orig_funcs - patch_funcs
        if missing:
            return False, f"Fonctions supprimees : {missing}"

        return True, "OK"


# ====================================================================
# 5. APPLY
# ====================================================================
class Applicator:

    def __init__(self):
        BACKUP_DIR.mkdir(parents=True, exist_ok=True)
        IMPROVE_DIR.mkdir(parents=True, exist_ok=True)

    def backup(self, fpath: Path) -> Path:
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_path = BACKUP_DIR / f"{fpath.stem}_{ts}{fpath.suffix}"
        shutil.copy2(fpath, backup_path)
        log.info(f"[APPLY] Backup : {backup_path.name}")
        return backup_path

    def apply(self, fpath: Path, patched_code: str) -> bool:
        try:
            self.backup(fpath)
            fpath.write_text(patched_code, encoding="utf-8")
            log.info(f"[APPLY] OK {fpath.name} patche")
            return True
        except Exception as e:
            log.error(f"[APPLY] Erreur : {e}")
            return False

    def rollback(self, fname: str) -> bool:
        backups = sorted(
            BACKUP_DIR.glob(f"{Path(fname).stem}_*{Path(fname).suffix}"),
            reverse=True
        )
        if not backups:
            log.error(f"[ROLLBACK] Aucun backup pour {fname}")
            return False
        latest = backups[0]
        dest   = BASE_DIR / fname
        if not dest.exists():
            dest = BASE_DIR / "agents" / fname
        shutil.copy2(latest, dest)
        log.info(f"[ROLLBACK] OK {fname} restaure depuis {latest.name}")
        return True


# ====================================================================
# 6. LEARN
# ====================================================================
class LearningMemory:

    def __init__(self):
        IMPROVE_DIR.mkdir(parents=True, exist_ok=True)
        self.memory = self._load()

    def _load(self) -> dict:
        if MEMORY_FILE.exists():
            try:
                return json.loads(MEMORY_FILE.read_text(encoding="utf-8"))
            except Exception:
                pass
        return {"sessions": [], "successful_patterns": [], "failed_patterns": [], "stats": {}}

    def save(self):
        MEMORY_FILE.write_text(
            json.dumps(self.memory, indent=2, ensure_ascii=False), encoding="utf-8"
        )

    def record_session(self, session: dict):
        self.memory["sessions"].append({"timestamp": datetime.now().isoformat(), **session})
        self.memory["sessions"] = self.memory["sessions"][-50:]
        stats = self.memory.setdefault("stats", {})
        stats["total_sessions"]    = len(self.memory["sessions"])
        stats["total_patches"]     = stats.get("total_patches", 0) + session.get("patches_applied", 0)
        stats["last_health_score"] = session.get("health_score", 0)
        self.save()
        log.info(f"[MEMORY] Session enregistree — {stats['total_patches']} patches au total")

    def get_context(self) -> str:
        stats  = self.memory.get("stats", {})
        return (
            f"Sessions precedentes : {stats.get('total_sessions', 0)} | "
            f"Patches appliques : {stats.get('total_patches', 0)} | "
            f"Dernier score sante : {stats.get('last_health_score', '?')}"
        )


# ====================================================================
# ORCHESTRATEUR
# ====================================================================
class SelfImprover:

    def __init__(self):
        self.observer   = Observer()
        self.reflector  = Reflector()
        self.proposer   = Proposer()
        self.validator  = Validator()
        self.applicator = Applicator()
        self.memory     = LearningMemory()

    def run(self, max_patches: int = 3, dry_run: bool = False) -> dict:
        run_id = datetime.now().strftime("%Y%m%d_%H%M%S")
        _log   = setup_improve_logging(run_id)
        sep    = "=" * 55
        _log.info(sep)
        _log.info("  Ov3rLoRd Self-Improve — Cycle demarre")
        _log.info(f"  Run ID : {run_id}")
        _log.info(f"  Memoire : {self.memory.get_context()}")
        _log.info(sep)

        session = {"patches_applied": 0, "patches_failed": 0, "improvements": []}

        log.info("[1/6] OBSERVE — Collecte des metriques...")
        metrics     = self.observer.collect_run_metrics()
        code_issues = self.observer.scan_code_quality()
        n_critical  = len(code_issues.get("critical", []))
        log.info(f"  -> {n_critical} critiques | {len(code_issues.get('warnings',[]))} warnings | "
                 f"{len(code_issues.get('todos',[]))} TODOs")

        log.info("[2/6] REFLECT — Analyse LLM des patterns...")
        reflection = self.reflector.reflect(metrics, code_issues)
        health     = reflection.get("health_score", 0)
        log.info(f"  -> Sante : {reflection.get('system_health','?').upper()} ({health}/100)")
        log.info(f"  -> Insight : {reflection.get('learning_insight','')}")

        if health >= 95:
            log.info("  -> Systeme optimal — aucune amelioration necessaire")
            return {"status": "optimal", "health_score": health}

        improvements = reflection.get("top_improvements", [])
        applied = 0

        for imp in improvements[:max_patches]:
            if applied >= MAX_PATCHES_PER_SESSION:
                break
            fname = imp.get("target_file", "")
            if not fname or fname in PROTECTED_FILES:
                continue

            log.info(f"[3-5/6] Amelioration {applied+1} : {fname}")
            log.info(f"  Probleme : {imp.get('issue','')}")
            log.info(f"  Fix : {imp.get('fix_description','')}")

            fpath = BASE_DIR / "agents" / fname
            if not fpath.exists():
                fpath = BASE_DIR / fname
            if not fpath.exists():
                log.warning(f"  Fichier introuvable : {fname}")
                continue

            original = fpath.read_text(encoding="utf-8")

            log.info("  [PROPOSE] Generation du correctif...")
            patched = self.proposer.propose_fix(imp, original)
            if not patched:
                log.warning("  Correctif non genere")
                session["patches_failed"] += 1
                continue

            log.info("  [VALIDATE] Verification...")
            is_valid, reason = self.validator.validate(fname, original, patched)
            if not is_valid:
                log.warning(f"  Correctif rejete : {reason}")
                session["patches_failed"] += 1
                continue

            log.info("  OK Correctif valide")

            if not dry_run:
                ok = self.applicator.apply(fpath, patched)
                if ok:
                    applied += 1
                    session["patches_applied"] += 1
                    session["improvements"].append(
                        {"file": fname, "issue": imp.get("issue",""), "status": "applied"}
                    )
                    write_structured_log({
                        "event":        "patch_applied",
                        "file":         fname,
                        "issue":        imp.get("issue",""),
                        "fix_type":     imp.get("fix_type",""),
                        "run_id":       run_id,
                        "health_before":health,
                    })
                    log.info(f"  OK Applique — {applied}/{max_patches}")
                else:
                    session["patches_failed"] += 1
            else:
                log.info("  [DRY-RUN] Correctif pret (non applique)")
                applied += 1

        log.info("[6/6] LEARN — Enregistrement en memoire...")
        session["health_score"] = health
        session["dry_run"]      = dry_run
        self.memory.record_session(session)

        _log.info(sep)
        _log.info(f"  Cycle termine : {session['patches_applied']} patches | {session['patches_failed']} echecs")
        _log.info(f"  Score sante : {health}/100")
        _log.info(sep)

        return {"status": "done", **session}

    def rollback(self, fname: str):
        return self.applicator.rollback(fname)

    def status(self) -> dict:
        code_issues = self.observer.scan_code_quality()
        n_critical  = len(code_issues.get("critical", []))
        n_warnings  = len(code_issues.get("warnings", []))
        return {
            "health_score": max(0, 100 - n_critical * 20 - n_warnings * 2),
            "critical":     n_critical,
            "warnings":     n_warnings,
            "memory":       self.memory.memory.get("stats", {}),
        }


# ====================================================================
# CLI
# ====================================================================
def main():
    import argparse
    parser = argparse.ArgumentParser(description="Ov3rLoRd Self-Improve V1.43")
    parser.add_argument("--mode", choices=["auto","reflect","status","rollback"],
                        default="status")
    parser.add_argument("--dry-run",     action="store_true")
    parser.add_argument("--max-patches", type=int, default=3)
    parser.add_argument("--rollback",    type=str, default="", metavar="FILENAME")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO,
                        format="%(asctime)s [%(levelname)-8s] %(message)s",
                        datefmt="%H:%M:%S")

    improver = SelfImprover()

    if args.mode == "status" or (args.mode == "rollback" and not args.rollback):
        s = improver.status()
        print(f"\n  Ov3rLoRd Self-Improve -- Status")
        print(f"  Score sante  : {s['health_score']}/100")
        print(f"  Critiques    : {s['critical']}")
        print(f"  Warnings     : {s['warnings']}")
        print(f"  Sessions     : {s['memory'].get('total_sessions', 0)}")
        print(f"  Patches total: {s['memory'].get('total_patches', 0)}\n")

    elif args.mode == "auto":
        result = improver.run(max_patches=args.max_patches, dry_run=args.dry_run)
        print(f"\n  Resultat : {result.get('status','?').upper()}")
        print(f"  Patches appliques : {result.get('patches_applied', 0)}")

    elif args.mode == "reflect":
        metrics     = improver.observer.collect_run_metrics()
        code_issues = improver.observer.scan_code_quality()
        reflection  = improver.reflector.reflect(metrics, code_issues)
        print(json.dumps(reflection, indent=2, ensure_ascii=False))

    elif args.mode == "rollback" and args.rollback:
        ok = improver.rollback(args.rollback)
        print(f"  Rollback {'OK' if ok else 'ECHEC'} pour {args.rollback}")


if __name__ == "__main__":
    main()

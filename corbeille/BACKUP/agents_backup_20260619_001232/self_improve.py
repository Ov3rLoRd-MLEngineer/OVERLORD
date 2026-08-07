"""
self_improve.py — Moteur d'Auto-Amélioration Locale V1.43
═══════════════════════════════════════════════════════════

CONCEPT : OverLord s'analyse lui-même, identifie ses faiblesses,
génère des correctifs, les valide, et les applique — en boucle.

Architecture inspirée de :
  - RLHF (Reinforcement Learning from Human Feedback)
  - Constitutional AI (Anthropic)
  - Self-Play (AlphaGo/AlphaCode)
  - Reflexion (Shinn et al. 2023)

Pipeline d'auto-amélioration :
  1. OBSERVE  → collecte métriques de tous les runs
  2. REFLECT  → analyse les patterns d'échec via LLM
  3. PROPOSE  → génère des correctifs ciblés
  4. VALIDATE → teste syntaxe + logique avant d'appliquer
  5. APPLY    → patch les fichiers avec backup automatique
  6. LEARN    → enregistre ce qui a marché dans la mémoire

Usage :
    python self_improve.py --mode auto      # boucle complète
    python self_improve.py --mode reflect   # analyse seulement
    python self_improve.py --mode propose   # génère correctifs
    python self_improve.py --mode rollback  # annule le dernier patch
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

BASE_DIR = Path(__file__).resolve().parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

try:
    from agents.overlord_utils import fallback_llm, safe_json_parse, get_api_key
    UTILS_OK = True
except ImportError:
    UTILS_OK = False

log = logging.getLogger("self_improve")

ARCHIVE_DRIVES = [
    Path("E:/OVERLORD_LOGS"),   # NVMe stockage chaud
    Path("G:/OVERLORD_LOGS"),   # HDD 1To archives
    Path("D:/OVERLORD/workspace/logs/improve"),  # Local pipeline
]

def setup_improve_logging(run_id: str = None) -> logging.Logger:
    """
    Configure le logging multi-destinations pour l'auto-amélioration.
    Écrit simultanément dans :
      - Console (INFO)
      - workspace/logs/improve/ (DEBUG complet)
      - Tous les drives configurés dans ARCHIVE_DRIVES
      - workspace/self_improve/MASTER_LOG.jsonl (log structuré)
    """
    ts      = run_id or datetime.now().strftime("%Y%m%d_%H%M%S")
    logger  = logging.getLogger(f"self_improve.{ts}")
    logger.setLevel(logging.DEBUG)
    fmt     = logging.Formatter("%(asctime)s [%(levelname)-8s] %(message)s", "%Y-%m-%d %H:%M:%S")

    # Console
    ch = logging.StreamHandler(sys.stdout)
    ch.setLevel(logging.INFO)
    ch.setFormatter(fmt)
    logger.addHandler(ch)

    # Local pipeline
    local_dir = BASE_DIR / "workspace" / "logs" / "improve"
    local_dir.mkdir(parents=True, exist_ok=True)
    fh = logging.FileHandler(local_dir / f"improve_{ts}.log", encoding="utf-8")
    fh.setLevel(logging.DEBUG)
    fh.setFormatter(fmt)
    logger.addHandler(fh)

    # Drives d'archive
    for drive in ARCHIVE_DRIVES:
        try:
            drive.mkdir(parents=True, exist_ok=True)
            dh = logging.FileHandler(drive / f"improve_{ts}.log", encoding="utf-8")
            dh.setLevel(logging.DEBUG)
            dh.setFormatter(fmt)
            logger.addHandler(dh)
            logger.debug(f"[LOGGING] Drive archive actif : {drive}")
        except Exception:
            pass  # Drive non disponible — on continue

    return logger


def write_structured_log(entry: dict):
    """
    Écrit une entrée JSONL dans le master log structuré.
    Format JSONL = 1 JSON par ligne, facile à parser/filtrer.
    Répliqué sur tous les drives disponibles.
    """
    entry["timestamp"] = datetime.now().isoformat()
    line = json.dumps(entry, ensure_ascii=False) + "\n"

    destinations = [
        BASE_DIR / "workspace" / "self_improve" / "MASTER_LOG.jsonl",
    ] + [d / "MASTER_LOG.jsonl" for d in ARCHIVE_DRIVES]

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

# ── Limites de sécurité ───────────────────────────────────────────────
MAX_PATCHES_PER_SESSION = 5      # jamais plus de 5 fichiers modifiés d'un coup
MAX_FILE_SIZE_CHANGE    = 0.30   # jamais +30% de taille (évite les injections massives)
PROTECTED_FILES = {              # fichiers qu'on ne touche JAMAIS automatiquement
    "self_improve.py",           # lui-même
    "licence_server.py",
    "config.json",
    ".env",
}
ALLOWED_DIRS = {"agents", "."}   # on ne touche que les agents et la racine


# ════════════════════════════════════════════════════════════════════
# 1. OBSERVE — Collecte des métriques
# ════════════════════════════════════════════════════════════════════
class Observer:
    """Analyse les logs de runs pour extraire les patterns d'échec."""

    def collect_run_metrics(self) -> list:
        """Lit tous les logs JSON de test et de run."""
        metrics = []
        logs_dir = METRICS_FILE
        if not logs_dir.exists():
            return metrics

        for log_file in sorted(logs_dir.glob("*.json"))[-20:]:  # 20 derniers
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

        # Aussi lire les logs texte pour extraire les ERROR
        error_patterns = []
        for log_file in sorted(logs_dir.glob("maestro_*.log"))[-5:]:
            try:
                content = log_file.read_text(encoding="utf-8", errors="ignore")
                errors = [l for l in content.split('\n') if '[ERROR' in l]
                if errors:
                    error_patterns.append({
                        "file": log_file.name,
                        "errors": errors[:10]
                    })
            except Exception:
                pass

        return {"test_metrics": metrics, "error_patterns": error_patterns}

    def scan_code_quality(self, agents_dir: Path = None) -> dict:
        """Scanne la qualité du code : TODOs, prints, imports fragiles."""
        issues = {"critical": [], "warnings": [], "todos": []}
        scan_dir = agents_dir or BASE_DIR / "agents"

        if not scan_dir.exists():
            return issues

        for fpath in sorted(scan_dir.glob("*.py")):
            try:
                src = fpath.read_text(encoding="utf-8")
                fname = fpath.name

                # Syntaxe
                try:
                    ast.parse(src)
                except SyntaxError as e:
                    issues["critical"].append({"file": fname, "issue": f"SyntaxError: {e}"})

                # Auth manquant
                if "ANTHROPIC_URL" in src and "x-api-key" not in src and "_get_api_key" not in src:
                    issues["critical"].append({"file": fname, "issue": "x-api-key manquant"})

                # Imports fragiles
                for line in src.split("\n"):
                    if line.strip().startswith("from agents") and "try:" not in src[max(0, src.find(line)-100):src.find(line)]:
                        issues["warnings"].append({"file": fname, "issue": f"Import sans try/except: {line.strip()}"})

                # TODOs
                for i, line in enumerate(src.split("\n")):
                    for marker in ["TODO", "FIXME", "HACK"]:
                        if marker in line:
                            issues["todos"].append({"file": fname, "line": i+1, "text": line.strip()[:80]})

            except Exception as e:
                issues["warnings"].append({"file": fname, "issue": str(e)})

        return issues


# ════════════════════════════════════════════════════════════════════
# 2. REFLECT — Analyse LLM des patterns
# ════════════════════════════════════════════════════════════════════
class Reflector:
    """Utilise le LLM pour analyser les problèmes et proposer des axes d'amélioration."""

    def reflect(self, metrics: dict, code_issues: dict) -> dict:
        """Génère une réflexion structurée sur l'état du système."""

        # Résumé compact pour le LLM
        n_critical = len(code_issues.get("critical", []))
        n_warnings = len(code_issues.get("warnings", []))
        n_todos    = len(code_issues.get("todos", []))
        errors_sample = []
        for ep in metrics.get("error_patterns", [])[:3]:
            errors_sample.extend(ep.get("errors", [])[:3])

        prompt = f"""Tu es l'agent d'auto-amélioration d'OverLord Pipeline.
Analyse l'état du système et propose les 3 améliorations les plus impactantes.

ÉTAT DU CODE :
- {n_critical} problèmes critiques
- {n_warnings} avertissements
- {n_todos} TODOs non résolus

ERREURS RÉCENTES (derniers runs) :
{chr(10).join(errors_sample[:6]) if errors_sample else "Aucune erreur récente"}

PROBLÈMES CRITIQUES :
{json.dumps(code_issues.get("critical", [])[:5], ensure_ascii=False)}

Retourne UNIQUEMENT ce JSON :
{{
  "system_health": "critical|degraded|stable|optimal",
  "health_score": 0-100,
  "top_improvements": [
    {{
      "priority": 1,
      "target_file": "nom_fichier.py",
      "issue": "description courte du problème",
      "fix_type": "add_function|fix_import|add_error_handling|refactor",
      "fix_description": "ce qu'il faut faire précisément",
      "impact": "high|medium|low",
      "safe_to_auto_apply": true
    }}
  ],
  "learning_insight": "observation clé sur les patterns du système"
}}"""

        if UTILS_OK:
            raw = fallback_llm(prompt, max_tokens=1000, logger=log)
            ok, data, _ = safe_json_parse(raw, logger=log)
            if ok and data:
                return data

        # Fallback déterministe si LLM indisponible
        improvements = []
        for issue in code_issues.get("critical", [])[:3]:
            improvements.append({
                "priority": len(improvements) + 1,
                "target_file": issue.get("file", ""),
                "issue": issue.get("issue", ""),
                "fix_type": "fix_auth" if "x-api-key" in issue.get("issue","") else "fix_syntax",
                "fix_description": "Ajouter _get_api_key() et header x-api-key",
                "impact": "high",
                "safe_to_auto_apply": True,
            })

        return {
            "system_health": "critical" if n_critical > 0 else "stable",
            "health_score": max(0, 100 - n_critical * 20 - n_warnings * 2),
            "top_improvements": improvements,
            "learning_insight": f"{n_critical} problèmes critiques détectés",
        }


# ════════════════════════════════════════════════════════════════════
# 3. PROPOSE — Génération des correctifs
# ════════════════════════════════════════════════════════════════════
class Proposer:
    """Génère le code de correctif pour chaque amélioration identifiée."""

    def propose_fix(self, improvement: dict, current_code: str) -> Optional[str]:
        """Génère le code corrigé pour un fichier donné."""
        fname = improvement.get("target_file", "")
        issue = improvement.get("issue", "")
        fix_desc = improvement.get("fix_description", "")

        if not UTILS_OK:
            log.warning("[PROPOSER] LLM indisponible — correctif automatique basique")
            return self._basic_fix(improvement, current_code)

        prompt = f"""Tu es un expert Python. Corrige ce fichier selon les instructions.

FICHIER : {fname}
PROBLÈME : {issue}
CORRECTION À APPLIQUER : {fix_desc}

CODE ACTUEL (extrait) :
{current_code[:3000]}

RÈGLES ABSOLUES :
1. Retourne UNIQUEMENT le code Python corrigé, complet, sans backticks ni explication
2. Ne modifie QUE ce qui est nécessaire pour corriger le problème
3. Conserve toute la logique existante
4. Le code doit être syntaxiquement valide
5. N'ajoute pas de commentaires supplémentaires sauf si nécessaire"""

        raw = fallback_llm(prompt, max_tokens=4000, logger=log)
        if raw and len(raw) > 100:
            # Nettoyer les backticks éventuels
            clean = raw.strip()
            if clean.startswith("```"):
                lines = clean.split("\n")
                clean = "\n".join(lines[1:-1] if lines[-1].strip() == "```" else lines[1:])
            return clean.strip()

        return self._basic_fix(improvement, current_code)

    def _basic_fix(self, improvement: dict, src: str) -> Optional[str]:
        """Correctifs automatiques sans LLM pour les cas simples."""
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
                        if key: break
        if key: break
    return key
'''

        if "x-api-key" in improvement.get("issue", "") or fix_type == "fix_auth":
            anchor = 'ANTHROPIC_URL = "https://api.anthropic.com/v1/messages"'
            if anchor in src and "_get_api_key" not in src:
                src = src.replace(anchor, anchor + "\n" + GET_API_KEY)
                for p in ['            headers={"Content-Type": "application/json"},',
                          'headers={"Content-Type": "application/json"},']:
                    if p in src:
                        indent = p[:len(p)-len(p.lstrip())]
                        src = src.replace(p, indent + 'headers={\n' +
                            indent + '    "Content-Type": "application/json",\n' +
                            indent + '    "x-api-key": _get_api_key(),\n' +
                            indent + '    "anthropic-version": "2023-06-01",\n' +
                            indent + '},')
                        break
                return src

        return None


# ════════════════════════════════════════════════════════════════════
# 4. VALIDATE — Validation avant application
# ════════════════════════════════════════════════════════════════════
class Validator:
    """Valide qu'un correctif est sûr avant de l'appliquer."""

    def validate(self, fname: str, original: str, patched: str) -> tuple:
        """
        Retourne (is_valid: bool, reason: str)
        """
        # 1. Syntaxe Python
        try:
            ast.parse(patched)
        except SyntaxError as e:
            return False, f"SyntaxError: {e}"

        # 2. Taille raisonnable
        orig_size   = len(original)
        patch_size  = len(patched)
        if orig_size > 0:
            ratio = abs(patch_size - orig_size) / orig_size
            if ratio > MAX_FILE_SIZE_CHANGE:
                return False, f"Changement de taille trop important : {ratio:.0%} (max {MAX_FILE_SIZE_CHANGE:.0%})"

        # 3. Fichiers protégés
        if fname in PROTECTED_FILES:
            return False, f"Fichier protégé : {fname}"

        # 4. Pas de code dangereux
        danger_patterns = [
            "os.system(", "subprocess.call(", "eval(", "exec(",
            "__import__('os').system", "shutil.rmtree(BASE",
        ]
        for pattern in danger_patterns:
            if pattern in patched and pattern not in original:
                return False, f"Pattern dangereux détecté : {pattern}"

        # 5. Les fonctions principales existent toujours
        orig_tree  = ast.parse(original)
        patch_tree = ast.parse(patched)
        orig_funcs  = {n.name for n in ast.walk(orig_tree)  if isinstance(n, ast.FunctionDef)}
        patch_funcs = {n.name for n in ast.walk(patch_tree) if isinstance(n, ast.FunctionDef)}
        missing = orig_funcs - patch_funcs
        if missing:
            return False, f"Fonctions supprimées : {missing}"

        return True, "OK"


# ════════════════════════════════════════════════════════════════════
# 5. APPLY — Application avec backup
# ════════════════════════════════════════════════════════════════════
class Applicator:
    """Applique les correctifs validés avec backup automatique."""

    def __init__(self):
        BACKUP_DIR.mkdir(parents=True, exist_ok=True)
        IMPROVE_DIR.mkdir(parents=True, exist_ok=True)

    def backup(self, fpath: Path) -> Path:
        """Sauvegarde le fichier avant modification."""
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_path = BACKUP_DIR / f"{fpath.stem}_{ts}{fpath.suffix}"
        shutil.copy2(fpath, backup_path)
        log.info(f"[APPLY] Backup : {backup_path.name}")
        return backup_path

    def apply(self, fpath: Path, patched_code: str) -> bool:
        """Applique le correctif avec backup."""
        try:
            backup_path = self.backup(fpath)
            fpath.write_text(patched_code, encoding="utf-8")
            log.info(f"[APPLY] ✓ {fpath.name} patché")
            return True
        except Exception as e:
            log.error(f"[APPLY] Erreur : {e}")
            return False

    def rollback(self, fname: str) -> bool:
        """Annule le dernier patch d'un fichier."""
        backups = sorted(BACKUP_DIR.glob(f"{Path(fname).stem}_*{Path(fname).suffix}"), reverse=True)
        if not backups:
            log.error(f"[ROLLBACK] Aucun backup trouvé pour {fname}")
            return False
        latest = backups[0]
        dest = BASE_DIR / fname
        if not dest.exists():
            dest = BASE_DIR / "agents" / fname
        shutil.copy2(latest, dest)
        log.info(f"[ROLLBACK] ✓ {fname} restauré depuis {latest.name}")
        return True


# ════════════════════════════════════════════════════════════════════
# 6. LEARN — Mémoire des améliorations
# ════════════════════════════════════════════════════════════════════
class LearningMemory:
    """Persiste ce qui a fonctionné pour éviter de refaire les mêmes erreurs."""

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
        MEMORY_FILE.write_text(json.dumps(self.memory, indent=2, ensure_ascii=False), encoding="utf-8")

    def record_session(self, session: dict):
        self.memory["sessions"].append({
            "timestamp": datetime.now().isoformat(),
            **session,
        })
        # Garder seulement les 50 dernières sessions
        self.memory["sessions"] = self.memory["sessions"][-50:]

        # Mettre à jour les stats
        stats = self.memory.setdefault("stats", {})
        stats["total_sessions"]    = len(self.memory["sessions"])
        stats["total_patches"]     = stats.get("total_patches", 0) + session.get("patches_applied", 0)
        stats["last_health_score"] = session.get("health_score", 0)

        self.save()
        log.info(f"[MEMORY] Session enregistrée — {stats['total_patches']} patches au total")

    def get_context(self) -> str:
        """Résumé de la mémoire pour enrichir le prompt de réflexion."""
        stats = self.memory.get("stats", {})
        recent = self.memory["sessions"][-5:] if self.memory["sessions"] else []
        return (
            f"Sessions précédentes : {stats.get('total_sessions', 0)} | "
            f"Patches appliqués : {stats.get('total_patches', 0)} | "
            f"Dernier score santé : {stats.get('last_health_score', '?')}"
        )


# ════════════════════════════════════════════════════════════════════
# ORCHESTRATEUR PRINCIPAL
# ════════════════════════════════════════════════════════════════════
class SelfImprover:
    """
    Orchestre le cycle complet d'auto-amélioration.
    Observe → Reflect → Propose → Validate → Apply → Learn
    """

    def __init__(self):
        self.observer   = Observer()
        self.reflector  = Reflector()
        self.proposer   = Proposer()
        self.validator  = Validator()
        self.applicator = Applicator()
        self.memory     = LearningMemory()

    def run(self, max_patches: int = 3, dry_run: bool = False) -> dict:
        """Lance un cycle complet d'auto-amélioration."""
        run_id = datetime.now().strftime("%Y%m%d_%H%M%S")
        _log   = setup_improve_logging(run_id)
        log.info("═"*55)
        log.info("  Ov3rLoRd Self-Improve — Cycle démarré")
        _log.info("═"*55)
        _log.info(f"  Run ID : {run_id}")
        log.info(f"  Mémoire : {self.memory.get_context()}")
        log.info("═"*55)

        session = {"patches_applied": 0, "patches_failed": 0, "improvements": []}

        # ── OBSERVE ──
        log.info("[1/6] OBSERVE — Collecte des métriques...")
        metrics      = self.observer.collect_run_metrics()
        code_issues  = self.observer.scan_code_quality()
        n_critical   = len(code_issues.get("critical", []))
        log.info(f"  → {n_critical} critiques | {len(code_issues.get('warnings',[]))} warnings | {len(code_issues.get('todos',[]))} TODOs")

        # ── REFLECT ──
        log.info("[2/6] REFLECT — Analyse LLM des patterns...")
        reflection = self.reflector.reflect(metrics, code_issues)
        health     = reflection.get("health_score", 0)
        log.info(f"  → Santé système : {reflection.get('system_health','?').upper()} ({health}/100)")
        log.info(f"  → Insight : {reflection.get('learning_insight','')}")

        if health >= 95:
            log.info("  → Système optimal — aucune amélioration nécessaire")
            return {"status": "optimal", "health_score": health}

        # ── PROPOSE + VALIDATE + APPLY ──
        improvements = reflection.get("top_improvements", [])
        applied = 0

        for imp in improvements[:max_patches]:
            if applied >= MAX_PATCHES_PER_SESSION:
                break

            fname = imp.get("target_file", "")
            if not fname or fname in PROTECTED_FILES:
                continue

            log.info(f"[3-5/6] Amélioration {applied+1} : {fname}")
            log.info(f"  Problème : {imp.get('issue','')}")
            log.info(f"  Fix : {imp.get('fix_description','')}")

            # Trouver le fichier
            fpath = BASE_DIR / "agents" / fname
            if not fpath.exists():
                fpath = BASE_DIR / fname
            if not fpath.exists():
                log.warning(f"  Fichier introuvable : {fname}")
                continue

            original = fpath.read_text(encoding="utf-8")

            # PROPOSE
            log.info("  [PROPOSE] Génération du correctif...")
            patched = self.proposer.propose_fix(imp, original)
            if not patched:
                log.warning("  Correctif non généré")
                session["patches_failed"] += 1
                continue

            # VALIDATE
            log.info("  [VALIDATE] Vérification...")
            is_valid, reason = self.validator.validate(fname, original, patched)
            if not is_valid:
                log.warning(f"  Correctif rejeté : {reason}")
                session["patches_failed"] += 1
                continue

            log.info(f"  ✓ Correctif validé")

            # APPLY
            if not dry_run:
                ok = self.applicator.apply(fpath, patched)
                if ok:
                    applied += 1
                    session["patches_applied"] += 1
                    session["improvements"].append({"file": fname, "issue": imp.get("issue",""), "status": "applied"})
                    write_structured_log({
                        "event": "patch_applied",
                        "file": fname,
                        "issue": imp.get("issue",""),
                        "fix_type": imp.get("fix_type",""),
                        "run_id": run_id,
                        "health_before": health,
                    })
                    log.info(f"  ✓ Appliqué — {applied}/{max_patches}")
                else:
                    session["patches_failed"] += 1
            else:
                log.info(f"  [DRY-RUN] Correctif prêt (non appliqué)")
                applied += 1

        # ── LEARN ──
        log.info("[6/6] LEARN — Enregistrement en mémoire...")
        session["health_score"] = health
        session["dry_run"]      = dry_run
        self.memory.record_session(session)

        log.info("═"*55)
        log.info(f"  Cycle terminé : {session['patches_applied']} patches appliqués | {session['patches_failed']} échecs")
        log.info(f"  Score santé : {health}/100")
        log.info("═"*55)

        return {"status": "done", **session}

    def rollback(self, fname: str):
        return self.applicator.rollback(fname)

    def status(self) -> dict:
        """Retourne l'état actuel sans rien modifier."""
        code_issues = self.observer.scan_code_quality()
        n_critical  = len(code_issues.get("critical", []))
        n_warnings  = len(code_issues.get("warnings", []))
        score       = max(0, 100 - n_critical * 20 - n_warnings * 2)
        return {
            "health_score": score,
            "critical":     n_critical,
            "warnings":     n_warnings,
            "memory":       self.memory.memory.get("stats", {}),
        }


# ════════════════════════════════════════════════════════════════════
# CLI
# ════════════════════════════════════════════════════════════════════
def main():
    import argparse
    parser = argparse.ArgumentParser(description="Ov3rLoRd Self-Improve V1.43")
    parser.add_argument("--mode", choices=["auto","reflect","status","rollback"],
                        default="status", help="Mode d'exécution")
    parser.add_argument("--dry-run", action="store_true", help="Simulation sans modification")
    parser.add_argument("--max-patches", type=int, default=3)
    parser.add_argument("--rollback", type=str, default="", metavar="FILENAME")
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)-8s] %(message)s",
        datefmt="%H:%M:%S"
    )

    improver = SelfImprover()

    if args.mode == "status" or (args.mode == "rollback" and not args.rollback):
        s = improver.status()
        print(f"\n  Ov3rLoRd Self-Improve — Status")
        print(f"  Score santé  : {s['health_score']}/100")
        print(f"  Critiques    : {s['critical']}")
        print(f"  Warnings     : {s['warnings']}")
        print(f"  Sessions     : {s['memory'].get('total_sessions', 0)}")
        print(f"  Patches total: {s['memory'].get('total_patches', 0)}\n")

    elif args.mode == "auto":
        result = improver.run(max_patches=args.max_patches, dry_run=args.dry_run)
        print(f"\n  Résultat : {result.get('status','?').upper()}")
        print(f"  Patches appliqués : {result.get('patches_applied', 0)}")

    elif args.mode == "reflect":
        metrics     = improver.observer.collect_run_metrics()
        code_issues = improver.observer.scan_code_quality()
        reflection  = improver.reflector.reflect(metrics, code_issues)
        print(json.dumps(reflection, indent=2, ensure_ascii=False))

    elif args.mode == "rollback" and args.rollback:
        ok = improver.rollback(args.rollback)
        print(f"  Rollback {'✓ réussi' if ok else '✗ échoué'} pour {args.rollback}")


if __name__ == "__main__":
    main()

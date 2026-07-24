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
agents/self_optimizer.py — Agent Auto-Optimiseur V1.70
L'agent qui analyse Ov3rLoRd lui-même et suggère ses propres améliorations.

Inspiré de la question : "si Ov3rLoRd pouvait s'inspirer de tout le bon
qu'il y a dans une IA performante, ce serait merveilleux."

Ce que fait cet agent :
  1. Analyse les logs de session pour détecter les patterns d'échec
  2. Compare les paramètres utilisés aux résultats obtenus
  3. Propose des améliorations concrètes au code des agents
  4. Génère des patches auto-appliqués après validation
  5. Apprend des runs passés pour anticiper les prochains

Principe : un système qui s'observe lui-même progresse plus vite
qu'un système observé de l'extérieur.

Usage :
  python agents/self_optimizer.py --analyze-session
  python agents/self_optimizer.py --suggest-patches
  python agents/self_optimizer.py --apply --patch patch_001.json
"""

import ast
import json
import logging
import sys
import io
from datetime import datetime
from pathlib import Path

if hasattr(sys.stdout, 'buffer'):
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

try:
    from agents.overlord_utils import fallback_llm, safe_json_parse
    UTILS_OK = True
except ImportError:
    UTILS_OK = False

try:
    from agents.context_bus import get_bus
    BUS_OK = True
except ImportError:
    BUS_OK = False

OPTIMIZER_DIR   = Path("workspace/self_optimizer")
PATCHES_DIR     = Path("workspace/self_optimizer/patches")
APPLIED_DIR     = Path("workspace/self_optimizer/applied")
SESSION_LOG     = Path("workspace/logs")
HISTORY_FILE    = Path("workspace/reports/history.json")

AGENTS_DIR      = Path("agents")


class AgentInspector:
    """Inspecte les agents sans les exécuter — analyse statique pure."""

    def __init__(self):
        self.log = logging.getLogger("self_optimizer.inspector")

    def scan_agent(self, path: Path) -> dict:
        """Analyse statique d'un agent."""
        try:
            src  = path.read_text(encoding='utf-8', errors='replace')
            tree = ast.parse(src)
        except Exception as e:
            return {"path": str(path), "error": str(e)}

        # Compter les métriques de qualité
        functions   = [n for n in ast.walk(tree)
                       if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))]
        classes     = [n for n in ast.walk(tree) if isinstance(n, ast.ClassDef)]
        try_blocks  = [n for n in ast.walk(tree) if isinstance(n, ast.Try)]
        log_calls   = sum(1 for n in ast.walk(tree)
                         if isinstance(n, ast.Call) and
                         hasattr(n.func, 'attr') and
                         n.func.attr in ('info','warning','error','debug'))
        bus_writes  = sum(1 for n in ast.walk(tree)
                         if isinstance(n, ast.Call) and
                         hasattr(n.func, 'attr') and
                         n.func.attr == 'write')
        has_fallback = any('fallback' in ast.dump(n).lower()
                          for n in ast.walk(tree)
                          if isinstance(n, ast.FunctionDef))
        has_docstring = (tree.body and
                         isinstance(tree.body[0], ast.Expr) and
                         isinstance(tree.body[0].value, ast.Constant))

        lines = src.splitlines()
        return {
            "path":          str(path),
            "name":          path.stem,
            "lines":         len(lines),
            "functions":     len(functions),
            "classes":       len(classes),
            "try_blocks":    len(try_blocks),
            "log_calls":     log_calls,
            "bus_writes":    bus_writes,
            "has_fallback":  has_fallback,
            "has_docstring": has_docstring,
            "quality_score": self._quality_score(
                len(functions), len(try_blocks), log_calls,
                has_fallback, has_docstring, len(lines)
            ),
        }

    def _quality_score(self, n_funcs, n_try, n_log,
                        has_fallback, has_doc, n_lines) -> int:
        score = 60
        if has_doc:      score += 10
        if has_fallback: score += 10
        if n_try > 0:    score += min(10, n_try * 3)
        if n_log > 0:    score += min(5,  n_log)
        if n_funcs > 0:  score += min(5,  n_funcs)
        return min(100, score)

    def scan_all(self) -> list[dict]:
        """Scanne tous les agents."""
        results = []
        for path in sorted(AGENTS_DIR.glob("*.py")):
            if not path.name.startswith("__"):
                results.append(self.scan_agent(path))
        return results


class SessionAnalyzer:
    """Analyse les sessions passées pour détecter les patterns."""

    def __init__(self):
        self.log = logging.getLogger("self_optimizer.session")

    def load_history(self) -> list:
        if not HISTORY_FILE.exists():
            return []
        try:
            return json.loads(HISTORY_FILE.read_text(encoding='utf-8'))
        except Exception:
            return []

    def detect_patterns(self, history: list) -> dict:
        """Détecte les patterns de succès et d'échec."""
        if len(history) < 3:
            return {"insufficient_data": True}

        # Taux de succès global
        successes = [r for r in history if r.get("images", 0) >= 8]
        failures  = [r for r in history if r.get("images", 0) < 8]

        # Durées moyennes par bloc
        durations = {}
        for run in history:
            for block, dur in run.get("block_durations", {}).items():
                durations.setdefault(block, []).append(dur)
        mean_durations = {
            k: round(sum(v) / len(v), 1)
            for k, v in durations.items()
        }

        # Score qualité moyen
        scores = [r.get("mean_score", 0) for r in history if r.get("mean_score")]

        return {
            "total_runs":    len(history),
            "success_rate":  round(len(successes) / len(history) * 100, 1),
            "mean_score":    round(sum(scores) / len(scores), 1) if scores else 0,
            "mean_durations": mean_durations,
            "bottleneck":    max(mean_durations, key=mean_durations.get)
                             if mean_durations else "unknown",
            "failure_rate":  round(len(failures) / len(history) * 100, 1),
        }


class PatchGenerator:
    """
    Génère des patches de code pour améliorer les agents.
    Un patch = modification ciblée d'un fichier agent validée par ast.parse().
    """

    def __init__(self):
        self.log = logging.getLogger("self_optimizer.patcher")

    def generate_patch(self, agent_name: str, issue: str,
                        suggestion: str) -> dict | None:
        """Génère un patch via LLM pour un agent spécifique."""
        if not UTILS_OK:
            return None

        agent_path = AGENTS_DIR / f"{agent_name}.py"
        if not agent_path.exists():
            self.log.warning(f"[OPTIMIZER] Agent introuvable : {agent_name}")
            return None

        src = agent_path.read_text(encoding='utf-8', errors='replace')

        system = (
            "You are an expert Python developer specializing in AI agent systems. "
            "Generate minimal, targeted code patches. "
            "Reply ONLY with valid JSON."
        )
        prompt = (
            f"Agent: {agent_name}.py\n"
            f"Issue detected: {issue}\n"
            f"Suggestion: {suggestion}\n\n"
            f"Agent code (first 500 chars): {src[:500]}\n\n"
            f"Generate a minimal patch to fix this issue.\n"
            f"Reply ONLY with JSON:\n"
            "{\n"
            '  "old_str": "exact string to replace (max 5 lines)",\n'
            '  "new_str": "replacement string",\n'
            '  "description": "what this patch does",\n'
            '  "safe": true/false\n'
            "}"
        )

        raw = fallback_llm(prompt, system=system, max_tokens=500, logger=self.log)
        ok, data, err = safe_json_parse(raw, logger=self.log)

        if not ok or not isinstance(data, dict):
            self.log.warning(f"[OPTIMIZER] Patch LLM échoué : {err}")
            return None

        if not data.get("safe", False):
            self.log.info(f"[OPTIMIZER] Patch marqué non-sûr, ignoré")
            return None

        # Valider que le patch ne casse pas la syntaxe
        old_str = data.get("old_str", "")
        new_str = data.get("new_str", "")
        if old_str and old_str in src:
            test_src = src.replace(old_str, new_str)
            try:
                ast.parse(test_src)
                patch_id = f"patch_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{agent_name}"
                return {
                    "id":          patch_id,
                    "agent":       agent_name,
                    "old_str":     old_str,
                    "new_str":     new_str,
                    "description": data.get("description", ""),
                    "issue":       issue,
                    "validated":   True,
                    "generated":   datetime.now().isoformat(),
                }
            except SyntaxError as e:
                self.log.warning(f"[OPTIMIZER] Patch syntaxe invalide : {e}")
                return None
        return None

    def apply_patch(self, patch: dict) -> bool:
        """Applique un patch validé sur un agent."""
        agent_path = AGENTS_DIR / f"{patch['agent']}.py"
        if not agent_path.exists():
            return False

        # Backup avant modification
        backup_path = APPLIED_DIR / f"{patch['agent']}_{patch['id']}.bak"
        APPLIED_DIR.mkdir(parents=True, exist_ok=True)
        backup_path.write_text(
            agent_path.read_text(encoding='utf-8', errors='replace'),
            encoding='utf-8'
        )

        src     = agent_path.read_text(encoding='utf-8', errors='replace')
        new_src = src.replace(patch["old_str"], patch["new_str"])

        # Validation syntaxe finale
        try:
            ast.parse(new_src)
        except SyntaxError as e:
            self.log.error(f"[OPTIMIZER] Patch rejeté (syntaxe) : {e}")
            return False

        agent_path.write_text(new_src, encoding='utf-8')
        self.log.info(
            f"[OPTIMIZER] Patch appliqué : {patch['agent']} "
            f"— {patch['description']}"
        )
        return True


class SelfOptimizer:
    """Orchestrateur principal de l'auto-optimisation."""

    def __init__(self):
        self.inspector = AgentInspector()
        self.analyzer  = SessionAnalyzer()
        self.patcher   = PatchGenerator()
        self.log       = logging.getLogger("self_optimizer")

    def run_full_analysis(self) -> dict:
        """Analyse complète : agents + sessions + recommandations."""
        self.log.info("[OPTIMIZER] Analyse complète en cours...")

        agents   = self.inspector.scan_all()
        history  = self.analyzer.load_history()
        patterns = self.analyzer.detect_patterns(history)

        # Trier par score qualité
        agents_sorted = sorted(agents, key=lambda a: a.get("quality_score", 0))

        # Agents à améliorer en priorité (score < 70)
        to_improve = [a for a in agents_sorted if a.get("quality_score", 0) < 70]

        # Recommandations
        recommendations = []

        for agent in to_improve[:5]:
            recs = []
            if not agent.get("has_fallback"):
                recs.append("Ajouter une fonction fallback()")
            if not agent.get("has_docstring"):
                recs.append("Ajouter une docstring de module")
            if agent.get("try_blocks", 0) == 0:
                recs.append("Encapsuler les appels LLM dans try/except")
            if agent.get("log_calls", 0) == 0:
                recs.append("Ajouter des appels logging.info()")
            if recs:
                recommendations.append({
                    "agent": agent["name"],
                    "score": agent["quality_score"],
                    "recs":  recs,
                })

        result = {
            "timestamp":         datetime.now().isoformat(),
            "agents_scanned":    len(agents),
            "agents_to_improve": len(to_improve),
            "session_patterns":  patterns,
            "recommendations":   recommendations,
            "top_agents":        [a["name"] for a in agents_sorted[-5:]],
            "weakest_agents":    [a["name"] for a in agents_sorted[:5]],
        }

        # Sauvegarder
        OPTIMIZER_DIR.mkdir(parents=True, exist_ok=True)
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        report_path = OPTIMIZER_DIR / f"analysis_{ts}.json"
        report_path.write_text(
            json.dumps(result, indent=2, ensure_ascii=False),
            encoding='utf-8'
        )

        if BUS_OK:
            try:
                bus = get_bus()
                bus.write("optimizer.agents_scanned",    len(agents), agent_id="optimizer")
                bus.write("optimizer.agents_to_improve", len(to_improve), agent_id="optimizer")
                bus.write("optimizer.last_run", result["timestamp"], agent_id="optimizer")
            except Exception:
                pass

        return result

    def print_report(self, result: dict):
        print(f"\n{'═'*60}")
        print(f"  AUTO-OPTIMISEUR — {result['timestamp'][:16]}")
        print(f"{'═'*60}")
        print(f"  Agents scannés      : {result['agents_scanned']}")
        print(f"  À améliorer         : {result['agents_to_improve']}")
        print(f"  Meilleurs agents    : {', '.join(result['top_agents'][:3])}")
        print(f"  Agents prioritaires : {', '.join(result['weakest_agents'][:3])}")

        sp = result.get("session_patterns", {})
        if not sp.get("insufficient_data"):
            print(f"\n  Patterns sessions :")
            print(f"    Taux succès  : {sp.get('success_rate',0)}%")
            print(f"    Score moyen  : {sp.get('mean_score',0)}")
            print(f"    Goulot       : {sp.get('bottleneck','?')}")

        if result.get("recommendations"):
            print(f"\n  Recommandations ({len(result['recommendations'])}) :")
            for r in result["recommendations"][:3]:
                print(f"    {r['agent']} (score={r['score']}) :")
                for rec in r["recs"][:2]:
                    print(f"      → {rec}")

        print(f"{'═'*60}")


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Ov3rLoRd Self Optimizer V1.70")
    parser.add_argument("--analyze-session", action="store_true")
    parser.add_argument("--suggest-patches", action="store_true")
    parser.add_argument("--apply",           action="store_true")
    parser.add_argument("--patch",           type=str, default=None)
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO,
                        format="%(asctime)s [%(levelname)s] %(message)s")

    opt = SelfOptimizer()

    if args.apply and args.patch:
        patch_path = Path(args.patch)
        if patch_path.exists():
            patch = json.loads(patch_path.read_text(encoding='utf-8'))
            ok = opt.patcher.apply_patch(patch)
            print(f"Patch {'appliqué ✓' if ok else 'rejeté ✗'}")
        else:
            print(f"Patch introuvable : {args.patch}")
    else:
        result = opt.run_full_analysis()
        opt.print_report(result)

"""
agents/legacy_agent.py — Agent Legacy Successeur
Agent IA capable de lire, comprendre et faire évoluer le codebase OverLord.

Principe du garde-fou :
  1. L'agent ANALYSE le code existant
  2. Il PROPOSE des modifications dans workspace/proposals/
  3. L'humain VALIDE (ou rejette) chaque proposition
  4. Si validé, l'agent APPLIQUE les changements
  5. L'agent DOCUMENTE ses raisonnements

L'agent ne modifie JAMAIS directement un fichier de production
sans validation humaine explicite.

Capacités :
  - Lecture et compréhension du codebase complet
  - Détection des TODO, FIXME, bugs potentiels
  - Proposition de nouvelles fonctionnalités
  - Refactoring suggéré
  - Documentation automatique
  - Auto-expérimentation dans un sandbox isolé
  - Dialogue sur ses choix techniques
"""

import ast
import json
import logging
import hashlib
import shutil
import subprocess
import threading
import time
from pathlib import Path
from datetime import datetime
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional
import requests

PROPOSALS_DIR  = Path("workspace/proposals")
SANDBOX_DIR    = Path("workspace/sandbox")
DECISIONS_FILE = Path("workspace/legacy_decisions.json")
ANTHROPIC_URL  = "https://api.anthropic.com/v1/messages"
CLAUDE_MODEL   = "claude-sonnet-4-6"
MAX_FILE_SIZE  = 100_000   # max 100Ko par fichier lu

PROJECT_ROOT   = Path(__file__).parent.parent


class ProposalStatus(Enum):
    PENDING  = "pending"    # en attente de validation
    APPROVED = "approved"   # validé par l'humain
    REJECTED = "rejected"   # rejeté
    APPLIED  = "applied"    # appliqué au code
    FAILED   = "failed"     # application échouée


class ProposalType(Enum):
    NEW_FEATURE   = "new_feature"
    BUG_FIX       = "bug_fix"
    REFACTOR      = "refactor"
    DOCUMENTATION = "documentation"
    OPTIMIZATION  = "optimization"
    EXPERIMENT    = "experiment"


@dataclass
class Proposal:
    id:           str
    type:         ProposalType
    title:        str
    description:  str
    target_file:  str
    original_code: str = ""
    proposed_code: str = ""
    rationale:    str  = ""
    risk_level:   str  = "low"    # low / medium / high
    status:       ProposalStatus = ProposalStatus.PENDING
    created_at:   str  = field(default_factory=lambda: datetime.utcnow().isoformat())
    validated_at: str  = ""
    applied_at:   str  = ""
    validation_note: str = ""

    def to_dict(self) -> dict:
        return {
            "id": self.id, "type": self.type.value,
            "title": self.title, "description": self.description,
            "target_file": self.target_file,
            "original_code": self.original_code[:500],
            "proposed_code": self.proposed_code[:500],
            "rationale": self.rationale, "risk_level": self.risk_level,
            "status": self.status.value,
            "created_at": self.created_at,
            "validated_at": self.validated_at,
            "applied_at": self.applied_at,
            "validation_note": self.validation_note,
        }


class CodebaseReader:
    """
    Lit et indexe le codebase OverLord pour l'agent Legacy.
    Ne lit jamais au-delà de MAX_FILE_SIZE par fichier.
    """

    SKIP_DIRS = {".git", "__pycache__", "node_modules", ".venv",
                 "dist", "build", "chromadb", "sandbox"}

    def __init__(self, root: Path = PROJECT_ROOT):
        self.root = root

    def list_files(self, ext: str = ".py") -> list[Path]:
        """Liste tous les fichiers Python du projet."""
        files = []
        for f in self.root.rglob(f"*{ext}"):
            if not any(skip in f.parts for skip in self.SKIP_DIRS):
                files.append(f)
        return sorted(files)

    def read_file(self, path: Path) -> str:
        """Lit un fichier avec limite de taille."""
        try:
            content = path.read_text(encoding="utf-8", errors="replace")
            if len(content) > MAX_FILE_SIZE:
                # Tronquer intelligemment aux 50 premières + 50 dernières lignes
                lines = content.split("\n")
                truncated = (
                    "\n".join(lines[:50]) + "\n\n... [TRONQUÉ] ...\n\n" +
                    "\n".join(lines[-50:])
                )
                return truncated
            return content
        except Exception:
            return ""

    def get_project_summary(self) -> dict:
        """Résumé du projet pour le contexte LLM."""
        files  = self.list_files()
        total  = 0
        by_dir = {}
        todos  = []

        for f in files:
            try:
                content = f.read_text(encoding="utf-8", errors="replace")
                lines   = len(content.split("\n"))
                total  += lines
                d       = str(f.relative_to(self.root).parent)
                by_dir[d] = by_dir.get(d, 0) + lines

                # Détecter les TODO/FIXME
                for i, line in enumerate(content.split("\n")):
                    if any(marker in line.upper() for marker in ["TODO","FIXME","HACK","XXX"]):
                        todos.append({
                            "file": str(f.relative_to(self.root)),
                            "line": i+1,
                            "text": line.strip()[:100],
                        })
            except Exception:
                pass

        return {
            "total_files":  len(files),
            "total_lines":  total,
            "by_directory": by_dir,
            "todos":        todos[:20],
            "files":        [str(f.relative_to(self.root)) for f in files[:30]],
        }

    def analyze_syntax(self, path: Path) -> dict:
        """Analyse syntaxique d'un fichier Python."""
        content = self.read_file(path)
        result  = {"valid": False, "errors": [], "classes": [], "functions": []}
        try:
            tree = ast.parse(content)
            result["valid"] = True
            for node in ast.walk(tree):
                if isinstance(node, ast.ClassDef):
                    result["classes"].append(node.name)
                elif isinstance(node, ast.FunctionDef):
                    result["functions"].append(node.name)
        except SyntaxError as e:
            result["errors"].append(f"Ligne {e.lineno}: {e.msg}")
        return result

    def find_improvement_targets(self) -> list[dict]:
        """Identifie des cibles d'amélioration potentielles."""
        targets = []
        for f in self.list_files():
            content = self.read_file(f)
            if not content:
                continue
            lines   = content.split("\n")
            issues  = []

            # Fonctions trop longues (> 80 lignes)
            in_func = False; func_start = 0; func_name = ""
            for i, line in enumerate(lines):
                if line.startswith("    def ") or line.startswith("def "):
                    if in_func and (i - func_start) > 80:
                        issues.append(f"Fonction '{func_name}' très longue ({i-func_start} lignes)")
                    in_func = True; func_start = i
                    func_name = line.strip().split("(")[0].replace("def ","")

            # Pas de docstring
            if '"""' not in content and "'''" not in content:
                issues.append("Aucune docstring détectée")

            # Pas de gestion d'erreur
            if "except Exception:" in content and "pass" in content:
                issues.append("except Exception: pass détecté (silencieux)")

            if issues:
                targets.append({
                    "file":   str(f.relative_to(self.root)),
                    "issues": issues,
                })
        return targets[:15]


class LegacyAgent:
    """
    Agent Legacy — Successeur IA du développement OverLord.

    Capacités :
    - Analyse du codebase complet
    - Génération de propositions avec garde-fou humain
    - Application des changements validés
    - Auto-expérimentation en sandbox
    - Dialogue technique sur les choix
    """

    SYSTEM_PROMPT = """Tu es l'Agent Legacy d'OverLord Pipeline — un assistant développeur IA
spécialisé dans ce projet spécifique. Tu as accès au codebase complet et tu proposes
des améliorations, des corrections de bugs et de nouvelles fonctionnalités.

TES PRINCIPES FONDAMENTAUX :
1. Tu ne modifies JAMAIS directement un fichier — tu proposes dans proposals/
2. Tu expliques TOUJOURS ton raisonnement technique
3. Tu évalues TOUJOURS le niveau de risque de tes propositions
4. Tu priorises la stabilité avant les nouvelles fonctionnalités
5. Tu apprends des retours humains pour améliorer tes futures propositions

STYLE :
- Technique et précis, pas de jargon inutile
- Confiant sur tes analyses, humble sur tes incertitudes
- Proactif : tu identifies des problèmes avant qu'on te le demande
"""

    def __init__(self, logger: logging.Logger = None):
        self.log      = logger or logging.getLogger("legacy")
        self.reader   = CodebaseReader()
        self._proposals: dict[str, Proposal] = {}
        self._decisions: list[dict] = []
        self._load_state()
        PROPOSALS_DIR.mkdir(parents=True, exist_ok=True)
        SANDBOX_DIR.mkdir(parents=True,   exist_ok=True)
        self.log.info(
            f"[LEGACY] Agent initialisé — "
            f"{len(self.reader.list_files())} fichiers en mémoire | "
            f"{len(self._proposals)} propositions existantes"
        )

    # ── Analyse du codebase ───────────────────────────────────────────

    def analyze_codebase(self) -> dict:
        """Analyse complète du projet et génère un rapport."""
        self.log.info("[LEGACY] Analyse du codebase...")
        summary  = self.reader.get_project_summary()
        targets  = self.reader.find_improvement_targets()

        analysis = {
            "timestamp":  datetime.utcnow().isoformat(),
            "summary":    summary,
            "targets":    targets,
            "syntax_ok":  [],
            "syntax_err": [],
        }

        # Vérifier la syntaxe de tous les fichiers
        for f in self.reader.list_files():
            result = self.reader.analyze_syntax(f)
            if result["valid"]:
                analysis["syntax_ok"].append(str(f.relative_to(PROJECT_ROOT)))
            else:
                analysis["syntax_err"].append({
                    "file": str(f.relative_to(PROJECT_ROOT)),
                    "errors": result["errors"]
                })

        self.log.info(
            f"[LEGACY] Analyse terminée — "
            f"{len(analysis['syntax_ok'])} OK | "
            f"{len(analysis['syntax_err'])} erreurs syntaxe | "
            f"{len(targets)} cibles d'amélioration"
        )
        return analysis

    # ── Génération de propositions ────────────────────────────────────

    def propose_improvement(self, target_file: str,
                             improvement_type: ProposalType = None,
                             context: str = "") -> Optional[Proposal]:
        """
        Génère une proposition d'amélioration pour un fichier.
        Utilise Claude pour analyser et proposer.
        """
        f_path  = PROJECT_ROOT / target_file
        if not f_path.exists():
            self.log.error(f"[LEGACY] Fichier introuvable : {target_file}")
            return None

        original_code = self.reader.read_file(f_path)
        analysis      = self.reader.analyze_syntax(f_path)

        prompt = (
            f"Tu es l'Agent Legacy d'OverLord Pipeline.\n"
            f"Analyse ce fichier et propose une amélioration concrète :\n\n"
            f"Fichier : {target_file}\n"
            f"Classes : {analysis.get('classes',[][:5])}\n"
            f"Fonctions : {analysis.get('functions',[])[:10]}\n"
            f"Contexte supplémentaire : {context or 'Aucun'}\n\n"
            f"Code source :\n```python\n{original_code[:3000]}\n```\n\n"
            f"Réponds en JSON valide uniquement :\n"
            f'{{"type":"new_feature|bug_fix|refactor|optimization|documentation",'
            f'"title":"titre court",'
            f'"description":"description en 2-3 phrases",'
            f'"proposed_code":"code Python complet proposé (si applicable, sinon vide)",'
            f'"rationale":"justification technique",'
            f'"risk_level":"low|medium|high"}}'
        )

        try:
            resp = requests.post(
                ANTHROPIC_URL,
                headers={"Content-Type": "application/json"},
                json={"model": CLAUDE_MODEL, "max_tokens": 2000,
                      "system": self.SYSTEM_PROMPT,
                      "messages": [{"role":"user","content":prompt}]},
                timeout=40
            )
            if resp.status_code != 200:
                return None
            raw = resp.json()["content"][0]["text"].strip()
            if raw.startswith("```"):
                raw = "\n".join(raw.split("\n")[1:-1])
            data = json.loads(raw)
        except Exception as e:
            self.log.error(f"[LEGACY] Génération proposition : {e}")
            return None

        proposal_id = hashlib.md5(
            f"{target_file}{datetime.utcnow().isoformat()}".encode()
        ).hexdigest()[:12]

        p_type = improvement_type or ProposalType(
            data.get("type","new_feature")
        )

        proposal = Proposal(
            id=proposal_id,
            type=p_type,
            title=data.get("title","Amélioration"),
            description=data.get("description",""),
            target_file=target_file,
            original_code=original_code[:2000],
            proposed_code=data.get("proposed_code",""),
            rationale=data.get("rationale",""),
            risk_level=data.get("risk_level","low"),
        )

        self._proposals[proposal_id] = proposal
        self._save_proposal(proposal)
        self.log.info(
            f"[LEGACY] ✓ Proposition créée : '{proposal.title}' "
            f"[{p_type.value}] risque={proposal.risk_level}"
        )
        return proposal

    def propose_new_agent(self, agent_name: str,
                           agent_description: str,
                           integrate_with: list[str] = None) -> Optional[Proposal]:
        """Propose le code d'un nouvel agent."""
        integrate_str = ", ".join(integrate_with or [])
        prompt = (
            f"Génère le code Python complet d'un nouvel agent pour OverLord Pipeline.\n\n"
            f"Nom         : {agent_name}\n"
            f"Description : {agent_description}\n"
            f"Intégration : {integrate_str or 'standalone'}\n\n"
            f"Le code doit :\n"
            f"- Suivre l'architecture des agents existants (logger, méthodes chat(), run())\n"
            f"- Avoir un docstring complet\n"
            f"- Être syntaxiquement valide\n"
            f"- Inclure un if __name__ == '__main__' pour les tests\n\n"
            f"Réponds en JSON : {{\"code\":\"code complet\","
            f"\"filename\":\"nom_fichier.py\","
            f"\"rationale\":\"justification\","
            f"\"risk_level\":\"low\"}}"
        )
        try:
            resp = requests.post(
                ANTHROPIC_URL,
                headers={"Content-Type": "application/json"},
                json={"model": CLAUDE_MODEL, "max_tokens": 3000,
                      "system": self.SYSTEM_PROMPT,
                      "messages": [{"role":"user","content":prompt}]},
                timeout=60
            )
            if resp.status_code != 200:
                return None
            raw = resp.json()["content"][0]["text"].strip()
            if raw.startswith("```"):
                raw = "\n".join(raw.split("\n")[1:-1])
            data = json.loads(raw)
        except Exception as e:
            self.log.error(f"[LEGACY] Génération agent : {e}")
            return None

        proposal_id = hashlib.md5(
            f"{agent_name}{datetime.utcnow().isoformat()}".encode()
        ).hexdigest()[:12]

        target = f"agents/{data.get('filename', agent_name.lower()+'.py')}"
        proposal = Proposal(
            id=proposal_id,
            type=ProposalType.NEW_FEATURE,
            title=f"Nouvel agent : {agent_name}",
            description=agent_description,
            target_file=target,
            proposed_code=data.get("code",""),
            rationale=data.get("rationale",""),
            risk_level=data.get("risk_level","low"),
        )
        self._proposals[proposal_id] = proposal
        self._save_proposal(proposal)
        self.log.info(f"[LEGACY] Proposition agent : {agent_name} → {target}")
        return proposal

    # ── Validation & Application ──────────────────────────────────────

    def list_pending(self) -> list[Proposal]:
        """Liste les propositions en attente de validation."""
        return [p for p in self._proposals.values()
                if p.status == ProposalStatus.PENDING]

    def approve(self, proposal_id: str,
                note: str = "") -> bool:
        """Valide une proposition (action humaine)."""
        p = self._proposals.get(proposal_id)
        if not p:
            self.log.error(f"[LEGACY] Proposition introuvable : {proposal_id}")
            return False
        p.status          = ProposalStatus.APPROVED
        p.validated_at    = datetime.utcnow().isoformat()
        p.validation_note = note
        self._save_proposal(p)
        self._record_decision("approve", proposal_id, note)
        self.log.info(f"[LEGACY] ✓ Proposition approuvée : {p.title}")
        return True

    def reject(self, proposal_id: str, reason: str = "") -> bool:
        """Rejette une proposition."""
        p = self._proposals.get(proposal_id)
        if not p:
            return False
        p.status          = ProposalStatus.REJECTED
        p.validated_at    = datetime.utcnow().isoformat()
        p.validation_note = reason
        self._save_proposal(p)
        self._record_decision("reject", proposal_id, reason)
        self.log.info(f"[LEGACY] ✗ Proposition rejetée : {p.title} — {reason}")
        return True

    def apply(self, proposal_id: str) -> bool:
        """
        Applique une proposition APPROUVÉE au codebase.
        Crée une sauvegarde avant modification.
        UNIQUEMENT si status == APPROVED.
        """
        p = self._proposals.get(proposal_id)
        if not p:
            self.log.error(f"[LEGACY] Proposition introuvable : {proposal_id}")
            return False
        if p.status != ProposalStatus.APPROVED:
            self.log.error(
                f"[LEGACY] Impossible d'appliquer : status={p.status.value} "
                f"(doit être APPROVED)"
            )
            return False
        if not p.proposed_code.strip():
            self.log.warning("[LEGACY] Pas de code à appliquer (documentation only?)")
            p.status     = ProposalStatus.APPLIED
            p.applied_at = datetime.utcnow().isoformat()
            self._save_proposal(p)
            return True

        target = PROJECT_ROOT / p.target_file

        # Backup
        if target.exists():
            backup = PROPOSALS_DIR / f"backup_{p.id}_{target.name}"
            shutil.copy2(str(target), str(backup))
            self.log.info(f"[LEGACY] Backup : {backup}")

        # Vérification syntaxe du code proposé
        try:
            ast.parse(p.proposed_code)
        except SyntaxError as e:
            self.log.error(f"[LEGACY] Code proposé syntaxiquement invalide : {e}")
            p.status = ProposalStatus.FAILED
            self._save_proposal(p)
            return False

        # Écriture
        try:
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(p.proposed_code, encoding="utf-8")
            p.status     = ProposalStatus.APPLIED
            p.applied_at = datetime.utcnow().isoformat()
            self._save_proposal(p)
            self.log.info(f"[LEGACY] ✅ Appliqué : {p.target_file}")
            return True
        except Exception as e:
            self.log.error(f"[LEGACY] Erreur application : {e}")
            p.status = ProposalStatus.FAILED
            self._save_proposal(p)
            return False

    # ── Sandbox ──────────────────────────────────────────────────────

    def test_in_sandbox(self, code: str, test_input: str = "") -> dict:
        """
        Exécute du code dans un sandbox isolé pour tester avant application.
        Timeout 10s, pas d'accès réseau.
        """
        sandbox_file = SANDBOX_DIR / f"test_{int(time.time())}.py"
        sandbox_file.write_text(code, encoding="utf-8")

        try:
            # Vérification syntaxe d'abord
            ast.parse(code)
        except SyntaxError as e:
            return {"success": False, "error": f"SyntaxError: {e}",
                    "output": ""}

        try:
            result = subprocess.run(
                ["python", str(sandbox_file)],
                input=test_input,
                capture_output=True, text=True,
                timeout=10,
                # Pas de réseau en sandbox (limité par l'OS)
            )
            return {
                "success":    result.returncode == 0,
                "output":     result.stdout[:1000],
                "error":      result.stderr[:500],
                "returncode": result.returncode,
            }
        except subprocess.TimeoutExpired:
            return {"success": False, "error": "Timeout 10s", "output": ""}
        except Exception as e:
            return {"success": False, "error": str(e), "output": ""}
        finally:
            sandbox_file.unlink(missing_ok=True)

    # ── Dialogue ─────────────────────────────────────────────────────

    def chat(self, message: str) -> str:
        """Interface de dialogue avec l'agent Legacy."""
        summary  = self.reader.get_project_summary()
        pending  = len(self.list_pending())
        n_files  = summary["total_files"]
        n_lines  = summary["total_lines"]
        todos    = summary.get("todos",[])

        context = (
            f"État du projet :\n"
            f"  - {n_files} fichiers Python | ~{n_lines} lignes\n"
            f"  - {pending} propositions en attente de validation\n"
            f"  - {len(todos)} TODO/FIXME détectés\n"
            f"  - {len(self._proposals)} propositions total\n"
        )
        if todos:
            context += "TODOs actuels :\n"
            for t in todos[:5]:
                context += f"  [{t['file']}:{t['line']}] {t['text']}\n"

        try:
            resp = requests.post(
                ANTHROPIC_URL,
                headers={"Content-Type": "application/json"},
                json={
                    "model": CLAUDE_MODEL, "max_tokens": 700,
                    "system": self.SYSTEM_PROMPT + "\n\n" + context,
                    "messages": [{"role":"user","content":message}]
                },
                timeout=35
            )
            if resp.status_code == 200:
                return resp.json()["content"][0]["text"].strip()
        except Exception as e:
            self.log.warning(f"[LEGACY/Chat] {e}")
        return f"[Contexte : {n_files} fichiers, {pending} propositions en attente]"

    # ── Persistance ───────────────────────────────────────────────────

    def _save_proposal(self, p: Proposal):
        path = PROPOSALS_DIR / f"{p.id}.json"
        path.write_text(
            json.dumps(p.to_dict(), indent=2, ensure_ascii=False),
            encoding="utf-8"
        )

    def _record_decision(self, action: str, proposal_id: str, note: str):
        self._decisions.append({
            "timestamp": datetime.utcnow().isoformat(),
            "action":    action,
            "proposal":  proposal_id,
            "note":      note,
        })
        DECISIONS_FILE.write_text(
            json.dumps(self._decisions, indent=2, ensure_ascii=False),
            encoding="utf-8"
        )

    def _load_state(self):
        # Charger propositions
        if PROPOSALS_DIR.exists():
            for f in PROPOSALS_DIR.glob("*.json"):
                if f.name.startswith("backup_"):
                    continue
                try:
                    data = json.loads(f.read_text(encoding="utf-8"))
                    p = Proposal(
                        id=data["id"], type=ProposalType(data["type"]),
                        title=data["title"], description=data["description"],
                        target_file=data["target_file"],
                        original_code=data.get("original_code",""),
                        proposed_code=data.get("proposed_code",""),
                        rationale=data.get("rationale",""),
                        risk_level=data.get("risk_level","low"),
                        status=ProposalStatus(data["status"]),
                        created_at=data.get("created_at",""),
                        validated_at=data.get("validated_at",""),
                        applied_at=data.get("applied_at",""),
                        validation_note=data.get("validation_note",""),
                    )
                    self._proposals[p.id] = p
                except Exception:
                    pass
        # Charger décisions
        if DECISIONS_FILE.exists():
            try:
                self._decisions = json.loads(
                    DECISIONS_FILE.read_text(encoding="utf-8")
                )
            except Exception:
                self._decisions = []

    def get_stats(self) -> dict:
        statuses = {}
        for p in self._proposals.values():
            statuses[p.status.value] = statuses.get(p.status.value, 0) + 1
        return {
            "total_proposals": len(self._proposals),
            "by_status":       statuses,
            "total_decisions": len(self._decisions),
        }


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    log = logging.getLogger("legacy_test")

    agent = LegacyAgent(log)

    # Analyse
    analysis = agent.analyze_codebase()
    log.info(f"Analyse : {analysis['summary']['total_files']} fichiers | "
              f"{len(analysis['targets'])} cibles | "
              f"{len(analysis['syntax_err'])} erreurs")

    # Stats
    stats = agent.get_stats()
    log.info(f"Propositions : {stats}")

    # Dialogue
    print("\n" + agent.chat("Quels sont les points d'amélioration prioritaires du projet ?"))
    print()
    print(agent.chat("Que penses-tu de l'architecture actuelle des agents ?"))

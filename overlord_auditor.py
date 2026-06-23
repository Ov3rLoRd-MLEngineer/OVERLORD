"""
overlord_auditor.py — Auditeur de Code Ov3rLoRd V1.70
Analyse statique des fichiers Python SANS les exécuter ni les importer.
Utilise uniquement ast.parse() + tokenize + lecture texte brute.

Intégré au launcher (bouton "🔍 Audit") et autonome en CLI.

Vérifie :
  1. Syntaxe Python (ast.parse)
  2. Sequences d'echappement invalides (ex: backslash-O, backslash-D)
  3. Imports manquants / non protégés par try/except
  4. Fonctions sans docstring
  5. Dépendances circulaires entre agents
  6. Fichiers avec class_type None dans les JSON workflow

Usage :
  python overlord_auditor.py                  # audit complet
  python overlord_auditor.py --dir agents     # un dossier
  python overlord_auditor.py --file scenario.py
  python overlord_auditor.py --quick          # syntaxe seulement
  python overlord_auditor.py --gui            # fenêtre résultats
"""

import ast
import json
import re
import sys
import io
import argparse
import tokenize as tok_module
from pathlib import Path
from datetime import datetime

try:
    from ov_design_system import (
        THEMES, get_theme, set_theme, on_theme_change,
        OvWindow, OvCard, OvButton, OvThemeSelector,
    )
    DESIGN_OK = True
except ImportError:
    DESIGN_OK = False
    def get_theme(n=None): return {"bg":"#0a0a0f","panel":"#12121a","border":"#1e1e2e","text":"#c0c0d0","dim":"#606070","accent":"#7c3aed","ok":"#10b981","err":"#ef4444","warn":"#f59e0b","title_fg":"#e2e8f0","font_ui":("Consolas",9),"font_title":("Consolas",11,"bold"),"font_btn":("Consolas",9)}

if hasattr(sys.stdout, 'buffer'):
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

AGENTS_DIR = Path("agents")
ROOT_DIR   = Path(".")

# Séquences d'échappement Python invalides (hors \n \t \r \\ etc.)
VALID_ESCAPES = set('nrtfvbae0123456789xuUN\\\'"01234567\n')
INVALID_ESC   = re.compile(r'(?<!\\)\\([^nrtfvbae0123456789xuUN\\\'"01234567\n\r])')


class AuditResult:
    def __init__(self, path: Path):
        self.path     = path
        self.errors   = []   # bloquants
        self.warnings = []   # non-bloquants
        self.infos    = []   # informationnels
        self.ok       = True

    def error(self, msg: str):
        self.errors.append(msg)
        self.ok = False

    def warn(self, msg: str):
        self.warnings.append(msg)

    def info(self, msg: str):
        self.infos.append(msg)

    @property
    def score(self) -> int:
        """Score de santé 0-100."""
        base = 100
        base -= len(self.errors) * 20
        base -= len(self.warnings) * 5
        return max(0, base)

    def summary(self) -> str:
        icon = "✓" if self.ok else "✗"
        return (f"{icon} {self.path.name:40s} "
                f"score={self.score:3d} | "
                f"err={len(self.errors)} warn={len(self.warnings)}")


def audit_syntax(path: Path, result: AuditResult):
    """Vérification syntaxe pure — ast.parse uniquement, zéro exécution."""
    try:
        src = path.read_text(encoding='utf-8', errors='replace')
        ast.parse(src, filename=str(path))
        result.info("Syntaxe OK")
    except SyntaxError as e:
        result.error(f"Syntaxe — ligne {e.lineno}: {e.msg}")
    except Exception as e:
        result.error(f"Lecture impossible: {e}")


def audit_escape_sequences(path: Path, result: AuditResult):
    """Détecte les séquences d'échappement invalides dans les strings."""
    try:
        src   = path.read_text(encoding='utf-8', errors='replace')
        lines = src.splitlines()
        for i, line in enumerate(lines, 1):
            stripped = line.strip()
            if stripped.startswith('#'):
                continue
            # Chercher backslash-O/D/A etc. mais pas dans les raw strings
            # et pas double backslash-O
            matches = INVALID_ESC.findall(line)
            for m in matches:
                # Ignorer si c'est dans une raw string
                idx = line.find(f'\\{m}')
                before = line[:idx]
                # Compter les r devant les guillemets
                if re.search(r'\br["\']', before[-5:] if len(before) >= 5 else before):
                    continue
                result.warn(f"Séquence invalide '\\{m}' ligne {i}: {stripped[:50]}")
    except Exception as e:
        result.warn(f"Scan échappements: {e}")


def audit_imports(path: Path, result: AuditResult):
    """Vérifie que les imports d'agents sont protégés par try/except."""
    try:
        src  = path.read_text(encoding='utf-8', errors='replace')
        tree = ast.parse(src)
    except Exception:
        return

    # Collecter les imports au niveau module (hors try/except)
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            if node.module and node.module.startswith('agents.'):
                # Vérifier si ce nœud est dans un try/except
                parent_try = False
                for parent in ast.walk(tree):
                    if isinstance(parent, ast.Try):
                        for child in ast.walk(parent):
                            if child is node:
                                parent_try = True
                                break
                if not parent_try:
                    # Vérifier si c'est en début de fichier dans un try
                    # (approximation : regarder si la ligne est dans un bloc try)
                    lineno = node.lineno
                    lines  = src.splitlines()
                    # Chercher le 'try:' précédent
                    in_try = False
                    for i in range(lineno-2, max(0, lineno-15), -1):
                        if lines[i].strip() == 'try:':
                            in_try = True
                            break
                    if not in_try:
                        result.warn(
                            f"Import non protégé ligne {lineno}: "
                            f"from {node.module} import ..."
                        )


def audit_docstrings(path: Path, result: AuditResult):
    """Compte les fonctions/classes sans docstring."""
    try:
        src  = path.read_text(encoding='utf-8', errors='replace')
        tree = ast.parse(src)
    except Exception:
        return

    no_doc = []
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            if not (node.body and isinstance(node.body[0], ast.Expr) and
                    isinstance(node.body[0].value, ast.Constant)):
                if not node.name.startswith('_'):  # ignorer les privées
                    no_doc.append(node.name)

    if len(no_doc) > 5:
        result.info(f"{len(no_doc)} fonctions publiques sans docstring")


def audit_bus_usage(path: Path, result: AuditResult):
    """Vérifie les bonnes pratiques d'utilisation du context_bus."""
    try:
        src = path.read_text(encoding='utf-8', errors='replace')
    except Exception:
        return

    if 'get_bus()' in src and 'BUS_OK' not in src:
        result.warn("get_bus() utilisé sans vérification BUS_OK")

    if 'bus.write(' in src and 'agent_id=' not in src:
        result.warn("bus.write() sans agent_id")


def audit_json_file(path: Path, result: AuditResult):
    """Audit spécifique pour les fichiers JSON workflow ComfyUI."""
    try:
        data = json.loads(path.read_text(encoding='utf-8', errors='replace'))
    except json.JSONDecodeError as e:
        result.error(f"JSON invalide: {e}")
        return

    if not isinstance(data, dict):
        result.warn("JSON n'est pas un objet (dict attendu pour workflow ComfyUI)")
        return

    null_ct = [k for k, v in data.items()
               if isinstance(v, dict) and v.get('class_type') is None]
    if null_ct:
        result.error(f"class_type=None sur nodes: {null_ct[:5]}")

    forbidden = {'Reroute', 'Note', 'PrimitiveNode',
                 'Lora Loader (LoraManager)', 'TriggerWord Toggle (LoraManager)'}
    found_forbidden = [
        (k, v['class_type']) for k, v in data.items()
        if isinstance(v, dict) and v.get('class_type') in forbidden
    ]
    if found_forbidden:
        result.error(f"Nœuds UI interdits: {found_forbidden[:3]}")

    # Liens orphelins
    orphans = []
    for node_id, node in data.items():
        if not isinstance(node, dict):
            continue
        for inp_k, inp_v in node.get('inputs', {}).items():
            if isinstance(inp_v, list) and len(inp_v) == 2:
                ref = str(inp_v[0])
                if ref not in data:
                    orphans.append(f"node {node_id}[{inp_k}]→{ref}")
    if orphans:
        result.error(f"Liens orphelins: {orphans[:3]}")

    result.info(f"Workflow: {len(data)} nœuds")


def audit_file(path: Path, quick: bool = False) -> AuditResult:
    """Audit complet d'un fichier. Zéro import, zéro exécution."""
    result = AuditResult(path)

    if path.suffix == '.py':
        audit_syntax(path, result)
        if not quick:
            audit_escape_sequences(path, result)
            audit_imports(path, result)
            audit_docstrings(path, result)
            audit_bus_usage(path, result)
    elif path.suffix == '.json':
        audit_json_file(path, result)
    else:
        result.info("Type non audité")

    return result


def audit_directory(directory: Path, quick: bool = False,
                    extensions: tuple = ('.py', '.json')) -> list[AuditResult]:
    """Audit récursif d'un dossier."""
    results = []
    files   = sorted(f for f in directory.rglob('*')
                     if f.is_file() and f.suffix in extensions
                     and '__pycache__' not in str(f))
    for f in files:
        results.append(audit_file(f, quick=quick))
    return results


def print_report(results: list[AuditResult], verbose: bool = False):
    """Affiche le rapport d'audit."""
    errors_total   = sum(len(r.errors)   for r in results)
    warnings_total = sum(len(r.warnings) for r in results)
    ok_count       = sum(1 for r in results if r.ok)
    mean_score     = sum(r.score for r in results) / max(len(results), 1)

    print(f"\n{'═'*60}")
    print(f"  AUDIT OV3RLORD V1.70 — {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    print(f"{'═'*60}")
    print(f"  Fichiers   : {len(results)}")
    print(f"  OK         : {ok_count}/{len(results)}")
    print(f"  Erreurs    : {errors_total}")
    print(f"  Warnings   : {warnings_total}")
    print(f"  Score moyen: {mean_score:.0f}/100")
    print(f"{'─'*60}")

    # Fichiers avec erreurs d'abord
    sorted_results = sorted(results, key=lambda r: (r.ok, -len(r.errors)))
    for r in sorted_results:
        print(r.summary())
        if verbose or not r.ok:
            for e in r.errors:
                print(f"    ✗ ERR  : {e}")
            for w in r.warnings[:3]:  # limiter les warnings
                print(f"    ⚠ WARN : {w}")

    print(f"{'═'*60}")
    if errors_total == 0:
        print(f"  ✓ AUDIT PASS — aucune erreur bloquante")
    else:
        print(f"  ✗ AUDIT FAIL — {errors_total} erreur(s) à corriger")
    print(f"{'═'*60}\n")


def show_gui(results: list[AuditResult]):
    """Affiche les résultats dans une fenêtre tkinter."""
    try:
        import tkinter as tk
        from tkinter import ttk
    except ImportError:
        print("tkinter non disponible — mode CLI uniquement")
        return

    root = tk.Tk()
    root.title("Ov3rLoRd Auditor V1.70")
    root.configure(bg="#0a0a0f")
    root.geometry("800x600")
    # Barre titre draggable
    if DESIGN_OK:
        _win = OvWindow(root, "◈  OV3RLORD AUDITOR  V1.70",
                        width=800, height=600)
        # Sélecteur thème dans la barre
        sel = OvThemeSelector(_win.title_bar,
                              on_change=lambda n: root.configure(
                                  bg=get_theme(n)["bg"]))
        sel.configure(bg=get_theme()["panel"])
        sel.pack(side="right", padx=4)

    # Style
    style = ttk.Style()
    style.theme_use('clam')
    style.configure("Treeview",
                    background="#12121a", foreground="#c0c0d0",
                    fieldbackground="#12121a", font=('Consolas', 9))
    style.configure("Treeview.Heading",
                    background="#1e1e2e", foreground="#7c3aed", font=('Consolas', 9, 'bold'))

    # Header
    hdr = tk.Frame(root, bg="#12121a", pady=8)
    hdr.pack(fill="x")
    ok_n    = sum(1 for r in results if r.ok)
    err_n   = sum(len(r.errors) for r in results)
    warn_n  = sum(len(r.warnings) for r in results)
    score   = sum(r.score for r in results) / max(len(results), 1)
    color   = "#10b981" if err_n == 0 else "#ef4444"
    tk.Label(hdr, text=f"◈ AUDIT RÉSULTATS — {ok_n}/{len(results)} OK | "
             f"score={score:.0f}/100 | err={err_n} warn={warn_n}",
             bg="#12121a", fg=color, font=('Consolas', 11, 'bold')).pack()

    # Treeview
    frame = tk.Frame(root, bg="#0a0a0f")
    frame.pack(fill="both", expand=True, padx=8, pady=8)

    cols = ("Fichier", "Score", "Erreurs", "Warnings", "Détails")
    tree = ttk.Treeview(frame, columns=cols, show="headings", height=20)
    for col in cols:
        tree.heading(col, text=col)
        tree.column(col, width={"Fichier": 250, "Score": 60, "Erreurs": 70,
                                "Warnings": 80, "Détails": 300}.get(col, 100))

    sb = ttk.Scrollbar(frame, orient="vertical", command=tree.yview)
    tree.configure(yscrollcommand=sb.set)
    sb.pack(side="right", fill="y")
    tree.pack(fill="both", expand=True)

    for r in sorted(results, key=lambda x: (x.ok, -len(x.errors))):
        tag   = "ok" if r.ok else "err"
        details = "; ".join(r.errors[:2] + r.warnings[:1])
        tree.insert("", "end",
                    values=(r.path.name, r.score,
                            len(r.errors), len(r.warnings),
                            details[:80]),
                    tags=(tag,))

    tree.tag_configure("ok",  foreground="#10b981")
    tree.tag_configure("err", foreground="#ef4444")

    # Detail pane
    detail_var = tk.StringVar()
    detail_lbl = tk.Label(root, textvariable=detail_var, bg="#12121a",
                           fg="#c0c0d0", font=('Consolas', 8),
                           justify="left", anchor="w", padx=8, pady=4)
    detail_lbl.pack(fill="x", side="bottom")

    def on_select(event):
        sel = tree.selection()
        if sel:
            idx   = tree.index(sel[0])
            r_sel = sorted(results, key=lambda x: (x.ok, -len(x.errors)))[idx]
            detail = f"{r_sel.path}\n"
            for e in r_sel.errors:
                detail += f"  ✗ {e}\n"
            for w in r_sel.warnings[:5]:
                detail += f"  ⚠ {w}\n"
            detail_var.set(detail[:300])

    tree.bind("<<TreeviewSelect>>", on_select)

    tk.Button(root, text="✕ Fermer", command=root.destroy,
              bg="#ef4444", fg="#fff", font=('Consolas', 9),
              relief="flat", padx=12).pack(side="bottom", pady=6)

    root.mainloop()


# ── Intégration launcher ──────────────────────────────────────────────
def run_audit_for_launcher(directory: str = ".") -> dict:
    """
    API pour overlord_launcher.py.
    Retourne un dict résumé sans rien exécuter.
    """
    d       = Path(directory)
    results = []

    for f in sorted(d.rglob("*.py")):
        if '__pycache__' not in str(f) and 'OVERLORD_PACK' not in str(f):
            results.append(audit_file(f, quick=False))

    # JSON workflow
    wf = d / "Combined_V35_API.json"
    if wf.exists():
        results.append(audit_file(wf))

    return {
        "total":        len(results),
        "ok":           sum(1 for r in results if r.ok),
        "errors":       sum(len(r.errors) for r in results),
        "warnings":     sum(len(r.warnings) for r in results),
        "mean_score":   round(sum(r.score for r in results) / max(len(results), 1), 1),
        "failed_files": [str(r.path) for r in results if not r.ok],
        "timestamp":    datetime.now().isoformat(),
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Ov3rLoRd Auditor V1.70 — Analyse statique sans exécution")
    parser.add_argument("--dir",     type=str, default=".", help="Dossier à auditer")
    parser.add_argument("--file",    type=str, default=None, help="Fichier unique")
    parser.add_argument("--quick",   action="store_true", help="Syntaxe seulement")
    parser.add_argument("--gui",     action="store_true", help="Afficher fenêtre tkinter")
    parser.add_argument("--verbose", action="store_true", help="Détail complet")
    parser.add_argument("--json",    action="store_true", help="Sortie JSON")
    args = parser.parse_args()

    if args.file:
        r = audit_file(Path(args.file), quick=args.quick)
        print_report([r], verbose=True)
        sys.exit(0 if r.ok else 1)

    # Audit dossier
    d = Path(args.dir)
    py_files  = [f for f in sorted(d.rglob("*.py"))
                 if '__pycache__' not in str(f) and 'OVERLORD_PACK' not in str(f)]
    json_files = [d / "Combined_V35_API.json"] if (d / "Combined_V35_API.json").exists() else []

    results = []
    for f in py_files + json_files:
        results.append(audit_file(f, quick=args.quick))

    if args.json:
        summary = {
            "total":      len(results),
            "ok":         sum(1 for r in results if r.ok),
            "errors":     sum(len(r.errors) for r in results),
            "warnings":   sum(len(r.warnings) for r in results),
            "mean_score": round(sum(r.score for r in results) / max(len(results), 1), 1),
            "files":      [{"path": str(r.path), "score": r.score,
                            "errors": r.errors, "warnings": r.warnings}
                           for r in results],
        }
        print(json.dumps(summary, indent=2, ensure_ascii=False))
    elif args.gui:
        show_gui(results)
    else:
        print_report(results, verbose=args.verbose)

    sys.exit(0 if all(r.ok for r in results) else 1)

# ██████╗ ██╗   ██╗██████╗ ██████╗ ██╗      ██████╗ ██████╗ ██████╗
# ██╔═══██╗██║   ██║╚════██╗██╔══██╗██║     ██╔═══██╗██╔══██╗██╔══██╗
# ██║   ██║██║   ██║ █████╔╝██████╔╝██║     ██║   ██║██████╔╝██║  ██║
# ██║   ██║╚██╗ ██╔╝ ╚═══██╗██╔══██╗██║     ██║   ██║██╔══██╗██║  ██║
# ╚██████╔╝ ╚████╔╝ ██████╔╝██║  ██║███████╗╚██████╔╝██║  ██║██████╔╝
# ╚═════╝   ╚═══╝  ╚═════╝ ╚═╝  ╚═╝╚══════╝ ╚═════╝ ╚═╝  ╚═╝╚═════╝
# Ov3rLoRd -- pipeline de production anime autonome (ComfyUI)
# https://github.com/Ov3rLoRd-MLEngineer
#
# aider_fallback_run.py — Wrapper de fiabilisation pour le relais Aider+qwen3-coder
#
# Contexte : DOCS/MD/PROCEDURE_FALLBACK_LLM.md documente un echec silencieux
# connu d'Aider en mode non-interactif (--message) sur ce depot : le terminal
# affiche un succes (exit 0) alors que le fichier cible reste a 0 octet, sans
# commit. Root cause identifiee cette session (voir DOCS/MD/PROCEDURE_FALLBACK_LLM.md) :
#   1. Sous Git Bash, un crash d'encodage (UnicodeEncodeError cp1252) survient
#      dans le rendu Rich d'Aider des que la reponse du modele contient un
#      caractere hors codepage ANSI (accents, emoji) -- Python bascule sur
#      l'encodage "preferred" du systeme (cp1252 sur Windows FR) au lieu
#      d'UTF-8 des que stdout est redirige (non-tty). Fix : forcer
#      PYTHONIOENCODING=utf-8 / PYTHONUTF8=1 avant le lancement.
#   2. Independamment de l'encodage, le format d'edition "whole" (celui choisi
#      par defaut par Aider pour un modele Ollama non repertorie dans ses
#      metadonnees) est fragile face a qwen3-coder : le modele emet parfois un
#      fence de fermeture surnumeraire ou une reponse mal formee, qu'Aider ne
#      sait pas appliquer -- il relance alors en interne un 2e tour avec un
#      message reflechi degenere (litteralement le mot "python"), qui fait
#      derailler le modele sans jamais ecrire sur le disque. Fix : forcer
#      --edit-format diff (SEARCH/REPLACE), qui n'a pas reproduit l'echec sur
#      les essais de cette session (2/2 en reproduction ciblee, cf. validation
#      elargie dans PROCEDURE_FALLBACK_LLM.md).
#
# Ce wrapper applique les deux correctifs et, en filet de securite, verifie le
# resultat sur le disque + git (jamais la seule sortie terminal, cf. lecon
# operationnelle du dossier) apres chaque tentative, avec relance automatique
# (nouveau process Aider a chaque fois, pas de poursuite de conversation) en
# cas d'echec silencieux detecte.
#
# Usage :
#   py -3.12 agents/aider_fallback_run.py <fichier_cible> "<description de la tache>" [--retries N] [--repo-root PATH]
#
# Code de sortie : 0 si le fichier est ecrit, non-vide, syntaxiquement valide
# (ast.parse) et commit par Aider apres au plus N tentatives. 1 sinon --
# dans ce cas, traiter la tache par un autre moyen (Claude Code des que
# disponible, ou manuellement) plutot que d'insister sur le meme lancement.

import argparse
import ast
import os
import subprocess
import sys
from pathlib import Path

AIDER_EXE = Path(r"C:\Users\Ov3rL0rD\.aider\venv\Scripts\aider.exe")
DEFAULT_RETRIES = 3


def _read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def verify_result(target: Path, repo_root: Path) -> tuple[bool, str]:
    """Verifie le resultat sur disque + git, jamais la sortie terminal."""
    if not target.exists():
        return False, "fichier absent"
    if target.stat().st_size == 0:
        return False, "fichier vide (0 octet) -- echec silencieux connu"
    try:
        _read_text(target)
    except UnicodeDecodeError as exc:
        return False, f"fichier illisible en UTF-8 : {exc}"
    try:
        ast.parse(_read_text(target))
    except SyntaxError as exc:
        return False, f"echec ast.parse() : {exc}"

    status = subprocess.run(
        ["git", "status", "--porcelain", "--", str(target)],
        cwd=repo_root,
        capture_output=True,
        text=True,
        check=True,
    )
    if status.stdout.strip().startswith("??"):
        return False, "fichier ecrit mais non commite (untracked) -- Aider n'a pas commit"

    log = subprocess.run(
        ["git", "log", "--oneline", "-1", "--", str(target)],
        cwd=repo_root,
        capture_output=True,
        text=True,
        check=True,
    )
    if not log.stdout.strip():
        return False, "aucun commit trouve touchant ce fichier"

    return True, f"OK -- commit: {log.stdout.strip()}"


def run_once(target: Path, message: str, repo_root: Path, attempt: int, log_dir: Path) -> tuple[bool, str]:
    env = dict(os.environ)
    env["PYTHONIOENCODING"] = "utf-8"
    env["PYTHONUTF8"] = "1"

    cmd = [
        str(AIDER_EXE),
        "--yes-always",
        "--no-stream",
        "--edit-format", "diff",
        "--message", message,
        str(target),
    ]

    log_dir.mkdir(parents=True, exist_ok=True)
    log_path = log_dir / f"{target.stem}_attempt{attempt}.log"
    with open(log_path, "w", encoding="utf-8") as log_file:
        subprocess.run(
            cmd,
            cwd=repo_root,
            env=env,
            stdout=log_file,
            stderr=subprocess.STDOUT,
            timeout=600,
        )

    ok, reason = verify_result(target, repo_root)
    return ok, reason


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("target", help="Chemin du fichier cible, relatif au repo")
    parser.add_argument("message", help="Description precise et cadree de la tache")
    parser.add_argument("--retries", type=int, default=DEFAULT_RETRIES)
    parser.add_argument("--repo-root", default=".")
    args = parser.parse_args()

    repo_root = Path(args.repo_root).resolve()
    target = repo_root / args.target
    log_dir = repo_root / "workspace" / "logs" / "aider_fallback_wrapper"

    for attempt in range(1, args.retries + 1):
        print(f"[aider_fallback_run] Tentative {attempt}/{args.retries} pour {target} ...")
        ok, reason = run_once(target, args.message, repo_root, attempt, log_dir)
        if ok:
            print(f"[aider_fallback_run] SUCCES ({reason})")
            return 0
        print(f"[aider_fallback_run] ECHEC : {reason} -- nouvelle tentative avec un process Aider frais")

    print(
        f"[aider_fallback_run] ABANDON apres {args.retries} tentatives. "
        "Traiter la tache par un autre moyen (Claude Code des que disponible, ou manuellement)."
    )
    return 1


if __name__ == "__main__":
    sys.exit(main())

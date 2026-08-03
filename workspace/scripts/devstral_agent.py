"""
workspace/scripts/devstral_agent.py -- wrapper CLI autour de l'API Ollama pour devstral:24b.

Contourne le bug decouvert avec Aider le 2026-08-03 (voir DOCS/LLM-Secour.md,
memoire "aider-qwen3coder-setup") : devstral:24b emet systematiquement des
fences markdown a 4 backticks au lieu des 3 attendus par le parseur Aider,
ce qui fait echouer silencieusement toute application d'edit. Ce script
evite le probleme a la racine en ne dependant d'AUCUNE fence markdown :
le modele est instruit de repondre entre deux marqueurs texte simples
(===DEVSTRAL_FILE_BEGIN===/===DEVSTRAL_FILE_END===), et c'est le script
lui-meme -- pas le modele -- qui calcule le diff unifie final via
difflib.unified_diff(). Le diff affiche a l'utilisateur est donc toujours
bien forme, quel que soit le nombre de backticks que le modele choisit.

Usage :
    py -3.12 workspace/scripts/devstral_agent.py --target <fichier> \
        --task <fichier_tache.txt> [--context <fichier> ...] [--yes]

Le fichier de tache est un fichier texte libre decrivant ce qu'il faut
faire. Les fichiers de contexte sont ajoutes en lecture seule au prompt
(jamais modifies). Le diff propose n'est applique sur disque qu'apres
confirmation interactive (y/n), sauf --yes (usage script, deconseille en
interactif). Chaque appel est journalise dans
workspace/logs/devstral_agent.log.
"""
import argparse
import ast
import datetime
import difflib
import json
import os
import sys
import urllib.error
import urllib.request
from pathlib import Path

OLLAMA_URL = "http://localhost:11434/api/chat"
MODEL = "devstral:24b"
NUM_CTX = 16384
REQUEST_TIMEOUT_S = 600

_REPO_ROOT = Path(__file__).resolve().parent.parent.parent
LOG_PATH = _REPO_ROOT / "workspace" / "logs" / "devstral_agent.log"

BEGIN_MARKER = "===DEVSTRAL_FILE_BEGIN==="
END_MARKER = "===DEVSTRAL_FILE_END==="

SYSTEM_PROMPT = f"""Tu es un assistant de code. On te donne le contenu complet d'un fichier
cible, une tache a effectuer dessus, et eventuellement des fichiers de
contexte en lecture seule (a ne jamais reproduire dans ta reponse).

Reponds UNIQUEMENT avec le contenu complet et final du fichier cible
modifie, entoure exactement de ces deux marqueurs sur leur propre ligne,
SANS AUCUNE fence markdown (pas de ```, pas de ```` ), sans aucun texte
avant ou apres les marqueurs :

{BEGIN_MARKER}
<contenu complet du fichier ici>
{END_MARKER}

Ne modifie que ce qui est necessaire pour accomplir la tache. Conserve le
reste du fichier a l'identique (indentation, commentaires, style, fin de
ligne)."""


def log(message: str) -> None:
    LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    ts = datetime.datetime.now().isoformat(timespec="seconds")
    with open(LOG_PATH, "a", encoding="utf-8") as f:
        f.write(f"[{ts}] {message}\n")


def call_ollama(system: str, user: str) -> str:
    payload = {
        "model": MODEL,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        "stream": False,
        "options": {"num_ctx": NUM_CTX},
    }
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        OLLAMA_URL, data=data, headers={"Content-Type": "application/json"}
    )
    with urllib.request.urlopen(req, timeout=REQUEST_TIMEOUT_S) as resp:
        body = json.loads(resp.read().decode("utf-8"))
    return body.get("message", {}).get("content", "")


def extract_file_content(response_text: str):
    if BEGIN_MARKER not in response_text or END_MARKER not in response_text:
        return None
    start = response_text.index(BEGIN_MARKER) + len(BEGIN_MARKER)
    end = response_text.index(END_MARKER)
    if end < start:
        return None
    content = response_text[start:end]
    if content.startswith("\n"):
        content = content[1:]
    return content


def build_user_prompt(task_text: str, target_path: str, target_content: str,
                       context_paths: list) -> str:
    parts = [f"Tache :\n{task_text.strip()}\n"]
    if context_paths:
        parts.append(
            "Fichiers de contexte (lecture seule, informatifs uniquement, "
            "ne pas les reproduire dans la reponse) :"
        )
        for cp in context_paths:
            try:
                text = Path(cp).read_text(encoding="utf-8")
            except OSError as e:
                text = f"(illisible : {e})"
            parts.append(f"--- {cp} ---\n{text}\n")
    parts.append(f"Fichier cible ({target_path}) :\n{target_content}")
    return "\n".join(parts)


def main() -> None:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.add_argument("--target", required=True, type=Path, help="Fichier a modifier")
    ap.add_argument("--task", required=True, type=Path,
                     help="Fichier texte libre decrivant la tache")
    ap.add_argument("--context", action="append", default=[],
                     help="Fichier de contexte en lecture seule (repetable)")
    ap.add_argument("--yes", action="store_true",
                     help="Applique sans confirmation interactive (usage script -- "
                          "deconseille en usage manuel, voir DOCS/LLM-Secour.md)")
    args = ap.parse_args()

    # NOTE (verifie session 2026-08-03, memoire "ollama-gpu-pinning") : ce
    # process n'est qu'un client HTTP vers un serveur Ollama deja lance
    # separement (port 11434) -- cette variable d'environnement n'a AUCUN
    # effet sur quelle carte sert reellement le modele. Le pinning reel se
    # fait cote serveur (UUID + OLLAMA_VULKAN=0) dans
    # D:\OVERLORD\launch_ollama.bat. Positionnee ici uniquement pour
    # documenter l'intention -- si Ollama n'a pas ete (re)lance via ce
    # script, devstral peut tourner sur la RTX 5080 (ComfyUI) sans qu'aucun
    # signal d'erreur ne le montre. Voir DOCS/LLM-Secour.md.
    os.environ.setdefault("CUDA_VISIBLE_DEVICES", "1")

    if not args.target.exists():
        print(f"ERREUR : fichier cible introuvable : {args.target}", file=sys.stderr)
        sys.exit(1)
    if not args.task.exists():
        print(f"ERREUR : fichier de tache introuvable : {args.task}", file=sys.stderr)
        sys.exit(1)

    task_text = args.task.read_text(encoding="utf-8")
    original_content = args.target.read_text(encoding="utf-8")
    user_prompt = build_user_prompt(task_text, str(args.target), original_content,
                                     args.context)

    print(f"[devstral_agent] Appel Ollama ({MODEL}, num_ctx={NUM_CTX})...")
    log(f"REQUEST target={args.target} task={args.task} context={args.context}")

    try:
        response_text = call_ollama(SYSTEM_PROMPT, user_prompt)
    except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, OSError) as e:
        print(f"ERREUR : appel Ollama echoue : {e}", file=sys.stderr)
        log(f"ERROR ollama call failed: {e}")
        sys.exit(1)

    new_content = extract_file_content(response_text)
    if new_content is None:
        print("ERREUR : reponse du modele sans marqueurs reconnus -- "
              "aucune modification proposee.", file=sys.stderr)
        print("--- Reponse brute du modele (2000 premiers caracteres) ---")
        print(response_text[:2000])
        log("ERROR markers not found in model response, no diff produced")
        sys.exit(1)

    diff_lines = list(difflib.unified_diff(
        original_content.splitlines(keepends=True),
        new_content.splitlines(keepends=True),
        fromfile=str(args.target),
        tofile=f"{args.target} (propose)",
    ))

    if not diff_lines:
        print("[devstral_agent] Aucune difference proposee par le modele.")
        log("NO-OP: model returned identical content")
        return

    print("".join(diff_lines))
    log(f"DIFF generated: {len(diff_lines)} lines for {args.target}")

    if args.target.suffix == ".py":
        try:
            ast.parse(new_content)
        except SyntaxError as e:
            print(f"/!\\ AVERTISSEMENT : le contenu propose ne parse pas comme "
                  f"Python valide ({e}) -- verifier attentivement avant "
                  f"d'appliquer.", file=sys.stderr)
            log(f"WARNING syntax error in proposed content: {e}")

    if args.yes:
        apply_change = True
    else:
        answer = input("Appliquer ce diff ? [y/N] ").strip().lower()
        apply_change = answer == "y"

    if apply_change:
        args.target.write_text(new_content, encoding="utf-8")
        print(f"[devstral_agent] Diff applique a {args.target}")
        log(f"APPLIED to {args.target}")
    else:
        print("[devstral_agent] Diff non applique (refuse ou non confirme).")
        log("DECLINED (no confirmation)")


if __name__ == "__main__":
    main()

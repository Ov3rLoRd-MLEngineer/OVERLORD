"""
Source C -- rapports de session Claude Code (transcripts complets sous
C:\\Users\\<user>\\.claude\\projects\\*\\*.jsonl -- un fichier par session,
regroupant sessions interactives et sessions "bg" lancees via .claude/jobs/).

Contrairement a Source A (diffs git isoles, sans raisonnement) et Source B
(dialogue Claude.ai, sans code produit), Source C vise des paires qui
combinent RAISONNEMENT (texte assistant visible a l'utilisateur, dans le
style demande par CLAUDE.md -- une phrase d'approche, mises a jour breves,
"result:" final) ET CODE PRODUIT dans le meme tour (contenu des appels
Write/Edit sur des fichiers .py/.md). Une paire est gardee seulement si elle
contient du texte de raisonnement (>= MIN_CHARS) ; le code est un bonus
appende quand present dans le meme tour -- ce choix est deliberement plus
strict que Source B pour eviter de simplement dupliquer son profil
(dialogue pur), voir docstring de `main()`.

Format de transcript (verifie manuellement avant d'ecrire ce script, voir
session de reference 2026-07-30) :
- chaque ligne est un evenement JSON independant, pas un message complet.
- un message humain reellement tape par l'utilisateur : `type=="user"`,
  `message.content` est une chaine (pas une liste), et `origin.kind=="human"`.
  Verifie sur deux transcripts (un petit run bg, un run interactif de 74 Mo) :
  aucune chaine `content` de ce type ne contient jamais de bloc
  `<system-reminder>` -- l'injection de contexte systeme ne pollue donc pas
  le cote instruction sur cette version du CLI, pas de nettoyage regex
  necessaire sur ce point precis (a revalider si le format de transcript
  change dans une version future du CLI).
- un resultat d'outil renvoye au modele est AUSSI `type=="user"` mais avec
  `message.content` une liste de blocs `type=="tool_result"` et pas de champ
  `origin` -- exclu explicitement (ce n'est pas une instruction humaine).
- un tour assistant peut etre reparti sur plusieurs evenements JSON
  consecutifs (un evenement par bloc thinking/tool_use/text) -- accumule
  jusqu'au prochain message humain reel.
- `isSidechain: true` marque un evenement appartenant a une conversation de
  sous-agent (outil Agent/Task) imbriquee dans le meme fichier -- exclu, ce
  n'est pas un tour de l'utilisateur principal.

Filtrage (meme discipline que la correction Session 4 sur Source B, voir
scripts/build_source_b.py) :
- PERSONAL_PATTERNS et has_tool_artifact()/clean_stray_markers() de
  build_source_b.py sont reimportes tels quels (pas redefinis) pour garantir
  une regle identique, pas une variante qui diverge avec le temps.
- SECRET_PATTERNS (nouveau ici) : filet de securite supplementaire par
  defense en profondeur -- meme si le perimetre d'extraction (texte assistant
  + payloads Write/Edit sur .py/.md seulement, jamais la sortie brute de
  Bash/Read/Grep) rend une fuite de secret peu probable, un secret colle par
  l'utilisateur dans une instruction puis cite par l'assistant resterait
  possible.
"""
import glob
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from build_source_b import PERSONAL_PATTERNS, has_tool_artifact, clean_stray_markers  # noqa: E402

PROJECTS_ROOT = os.path.expanduser(r"~\.claude\projects")
OUT_PATH = r"D:\OVERLORD\workspace\qlora_dataset\dataset_source_c.jsonl"
QA_DIR = r"D:\OVERLORD\workspace\qlora_dataset\_qa"
os.makedirs(QA_DIR, exist_ok=True)

MIN_CHARS = 5
OUTPUT_CHAR_CAP = 20000          # coherent avec DIFF_SIZE_CAP de Source A
CODE_SECTION_CHAR_CAP = 12000    # part du cap total reservee au code
EDIT_SNIPPET_CAP = 4000          # old_string / new_string, chacun

CODE_EXTENSIONS = {".py", ".md"}

EXCLUDE_PATH_SUBSTRINGS = [
    "__pycache__", ".pyc", ".env",
    "\\agents\\requests\\", "/agents/requests/",
    "\\agents\\urllib3\\", "/agents/urllib3/",
    "\\agents\\certifi\\", "/agents/certifi/",
    "\\agents\\idna\\", "/agents/idna/",
    "\\agents\\charset_normalizer\\", "/agents/charset_normalizer/",
    "workspace\\archive", "workspace/archive",
    "workspace\\backups", "workspace/backups",
]

# Session en cours d'ecriture au moment ou ce script tourne -- exclue pour
# eviter l'auto-reference et un JSONL potentiellement incomplet en fin de
# fichier (voir consigne de session : job daemonShort 9607911a).
CURRENT_SESSION_ID = "9607911a-1baf-4c33-a6cb-b05592542ab8"

# Filet de securite supplementaire (voir docstring module) -- formes de
# secrets couramment collees/citees dans un transcript de dev, au-dela du
# perimetre PERSONAL_PATTERNS deja oriente vie privee plutot que credentials.
SECRET_PATTERNS = [
    re.compile(r"sk-[A-Za-z0-9]{20,}"),
    re.compile(r"AKIA[0-9A-Z]{16}"),
    re.compile(r"ghp_[A-Za-z0-9]{30,}"),
    re.compile(r"xox[baprs]-[A-Za-z0-9-]{10,}"),
    re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----"),
]


def has_secret(text: str) -> bool:
    return any(p.search(text) for p in SECRET_PATTERNS)


def clean_relpath(file_path: str) -> str:
    """Chemin absolu -> chemin relatif lisible, prefixe repo/worktree retire."""
    norm = file_path.replace("\\", "/")
    m = re.search(r"(?:OVERLORD/(?:\.claude/worktrees/[^/]+/)?)(.+)$", norm, re.I)
    return m.group(1) if m else norm


def format_write(input_data: dict) -> str | None:
    fp = input_data.get("file_path", "")
    if os.path.splitext(fp)[1].lower() not in CODE_EXTENSIONS:
        return None
    if any(x.lower() in fp.lower() for x in EXCLUDE_PATH_SUBSTRINGS):
        return None
    content = input_data.get("content", "")
    if not content.strip():
        return None
    return f"[WRITE {clean_relpath(fp)}]\n{content}"


def format_edit(input_data: dict) -> str | None:
    fp = input_data.get("file_path", "")
    if os.path.splitext(fp)[1].lower() not in CODE_EXTENSIONS:
        return None
    if any(x.lower() in fp.lower() for x in EXCLUDE_PATH_SUBSTRINGS):
        return None
    old = input_data.get("old_string", "")[:EDIT_SNIPPET_CAP]
    new = input_data.get("new_string", "")[:EDIT_SNIPPET_CAP]
    if not new.strip():
        return None
    return f"[EDIT {clean_relpath(fp)}]\n--- avant\n{old}\n--- apres\n{new}"


def iter_session_files():
    for path in glob.glob(os.path.join(PROJECTS_ROOT, "*", "*.jsonl")):
        if CURRENT_SESSION_ID in path:
            continue
        yield path


def get_text_blocks(content):
    """content d'un message assistant : liste de blocs. Retourne
    (reasoning_parts, code_parts) pour ce seul evenement JSON."""
    reasoning, code = [], []
    for block in content:
        btype = block.get("type")
        if btype == "text":
            t = (block.get("text") or "").strip()
            if t:
                reasoning.append(t)
        elif btype == "tool_use":
            name = block.get("name")
            inp = block.get("input") or {}
            snippet = None
            if name == "Write":
                snippet = format_write(inp)
            elif name == "Edit":
                snippet = format_edit(inp)
            elif name == "NotebookEdit":
                fp = inp.get("notebook_path", "")
                src = inp.get("new_source", "")
                if src.strip():
                    snippet = f"[NOTEBOOKEDIT {clean_relpath(fp)}]\n{src}"
            if snippet:
                code.append(snippet)
    return reasoning, code


def flush_pair(instruction, reasoning_parts, code_parts, meta, out, seen, counters):
    if instruction is None:
        return
    instruction = instruction.strip()
    reasoning = "\n\n".join(reasoning_parts).strip()
    reasoning = clean_stray_markers(reasoning)

    if len(instruction) < MIN_CHARS or len(reasoning) < MIN_CHARS:
        counters["skipped_no_reasoning"] += 1
        return

    code_section = ""
    if code_parts:
        acc, total = [], 0
        for snippet in code_parts:
            if total >= CODE_SECTION_CHAR_CAP:
                break
            remaining = CODE_SECTION_CHAR_CAP - total
            piece = snippet if len(snippet) <= remaining else snippet[:remaining]
            acc.append(piece)
            total += len(piece)
        code_section = "\n\n".join(acc)

    output = reasoning if not code_section else reasoning + "\n\n" + code_section
    output = output[:OUTPUT_CHAR_CAP]

    combined = instruction + "\n" + output
    if any(p.search(combined) for p in PERSONAL_PATTERNS):
        counters["skipped_personal"] += 1
        return
    if has_secret(combined):
        counters["skipped_secret"] += 1
        return
    if has_tool_artifact(instruction) or has_tool_artifact(output):
        counters["skipped_tool_artifact"] += 1
        return

    key = hash((instruction, output))
    if key in seen:
        counters["skipped_duplicate"] += 1
        return
    seen.add(key)

    record = {
        "instruction": instruction,
        "input": "",
        "output": output,
        "meta": meta,
    }
    out.write(json.dumps(record, ensure_ascii=False) + "\n")
    counters["kept"] += 1


def process_file(path, out, seen, counters):
    session_id = os.path.splitext(os.path.basename(path))[0]
    project_dir = os.path.basename(os.path.dirname(path))

    pending_instruction = None
    reasoning_parts, code_parts = [], []

    with open(path, encoding="utf-8", errors="replace") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                d = json.loads(line)
            except (json.JSONDecodeError, ValueError):
                counters["skipped_bad_json"] += 1
                continue

            if d.get("isSidechain"):
                continue

            dtype = d.get("type")
            msg = d.get("message") or {}
            content = msg.get("content")

            if dtype == "user" and isinstance(content, str) and (d.get("origin") or {}).get("kind") == "human":
                meta = {
                    "source": "claude_code_session",
                    "project_dir": project_dir,
                    "session_id": session_id,
                }
                flush_pair(pending_instruction, reasoning_parts, code_parts, meta, out, seen, counters)
                pending_instruction = content
                reasoning_parts, code_parts = [], []
                continue

            if dtype == "assistant" and pending_instruction is not None and isinstance(content, list):
                r, c = get_text_blocks(content)
                reasoning_parts.extend(r)
                code_parts.extend(c)

    meta = {"source": "claude_code_session", "project_dir": project_dir, "session_id": session_id}
    flush_pair(pending_instruction, reasoning_parts, code_parts, meta, out, seen, counters)


def main():
    counters = {
        "kept": 0,
        "skipped_no_reasoning": 0,
        "skipped_personal": 0,
        "skipped_secret": 0,
        "skipped_tool_artifact": 0,
        "skipped_duplicate": 0,
        "skipped_bad_json": 0,
    }
    seen = set()
    files = list(iter_session_files())
    print(f"session_files_found={len(files)}")

    with open(OUT_PATH, "w", encoding="utf-8") as out:
        for i, path in enumerate(files, 1):
            process_file(path, out, seen, counters)
            if i % 10 == 0 or i == len(files):
                print(f"...{i}/{len(files)} fichiers traites, kept={counters['kept']}")

    for k, v in counters.items():
        print(f"{k}={v}")


if __name__ == "__main__":
    main()

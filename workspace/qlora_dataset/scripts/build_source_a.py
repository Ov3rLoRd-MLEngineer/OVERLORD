"""
Source A -- historique git du projet Ov3rLoRd.
Construit des paires (contexte de tache) -> (diff produit) au format
Alpaca (instruction / input / output), pour entrainement comportemental
QLoRA sur qwen3-coder.

- instruction = sujet du commit (une ligne)
- input       = corps du message de commit (contexte/rationale), si present
- output      = diff unifie, filtre des fichiers binaires/generes/secrets

Filtres appliques (voir CONTRAINTES de la session) :
- commits de fusion : deja exclus via `git log --no-merges`
- corrections triviales : nettoyage .pyc/__pycache__, insertion mecanique
  d'un en-tete/logo sur des dizaines de fichiers (pas de "comportement" a
  apprendre, juste du bruit repetitif)
- commits WIP explicitement marques (non "propres" par definition)
- tout commit touchant .env est exclu par securite (un des deux commits
  .env de l'historique documente une fuite de cle API live -- le diff
  afficherait l'ancien contenu du secret)
- taille de diff plafonnee a 20000 caracteres apres filtrage des chemins
  binaires/generes : au-dela ce sont des dumps mecaniques (import initial,
  renommage de marque sur tout le depot, etc.), pas des changements isoles
"""
import json
import re
import subprocess

REPO_ROOT = r"D:\OVERLORD"
OUT_PATH = r"D:\OVERLORD\workspace\qlora_dataset\dataset_source_a.jsonl"

DIFF_SIZE_CAP = 20000

# Chemins jamais inclus dans un diff, quel que soit le commit.
EXCLUDE_PATHSPECS = [
    ":(exclude)*.pyc",
    ":(exclude)**/__pycache__/**",
    ":(exclude).env",
    ":(exclude)*.env*",
    ":(exclude)*.png",
    ":(exclude)*.jpg",
    ":(exclude)*.jpeg",
    ":(exclude)*.safetensors",
    ":(exclude)*.pth",
    ":(exclude)*.ckpt",
    ":(exclude)*.bin",
]

# Commits explicitement exclus par securite (fuite de secret documentee
# dans le message de commit lui-meme -- le diff exposerait l'ancien .env).
SAFETY_EXCLUDE_HASHES = {
    "002445c09c96ea9f3af859dd82103a9acce70c5c",
    "04aa8e75fc59445790e85599c713d33e2d8d85d3",
}

TRIVIAL_SUBJECT_PATTERNS = [
    re.compile(r"\bpycache\b", re.I),
    re.compile(r"\.pyc\b", re.I),
    re.compile(r"\btypo\b", re.I),
    re.compile(r"en-t[eê]te.*logo|logo.*en-t[eê]te", re.I),
    re.compile(r"^WIP\b", re.I),
]


def run(args):
    return subprocess.run(
        args, cwd=REPO_ROOT, capture_output=True, text=True,
        encoding="utf-8", errors="replace",
    ).stdout


def is_trivial(subject: str) -> bool:
    return any(p.search(subject) for p in TRIVIAL_SUBJECT_PATTERNS)


def main():
    hashes = run(["git", "log", "--no-merges", "--pretty=format:%H"]).splitlines()

    kept = 0
    skipped_safety = 0
    skipped_trivial = 0
    skipped_size = 0
    skipped_empty = 0

    with open(OUT_PATH, "w", encoding="utf-8") as out:
        for h in hashes:
            if h in SAFETY_EXCLUDE_HASHES:
                skipped_safety += 1
                continue

            subject = run(["git", "log", "-1", "--pretty=%s", h]).strip()
            body = run(["git", "log", "-1", "--pretty=%b", h]).strip()

            if is_trivial(subject):
                skipped_trivial += 1
                continue

            diff = run(
                ["git", "show", "--no-color", "--pretty=format:", h, "--", "."]
                + EXCLUDE_PATHSPECS
            ).strip()

            if not diff:
                skipped_empty += 1
                continue
            if len(diff) > DIFF_SIZE_CAP:
                skipped_size += 1
                continue

            record = {
                "instruction": subject,
                "input": body,
                "output": diff,
                "meta": {"source": "git_history", "commit": h},
            }
            out.write(json.dumps(record, ensure_ascii=False) + "\n")
            kept += 1

    print(f"total_commits_non_merge={len(hashes)}")
    print(f"kept={kept}")
    print(f"skipped_safety_env={skipped_safety}")
    print(f"skipped_trivial={skipped_trivial}")
    print(f"skipped_empty_after_path_filter={skipped_empty}")
    print(f"skipped_over_size_cap={skipped_size}")


if __name__ == "__main__":
    main()

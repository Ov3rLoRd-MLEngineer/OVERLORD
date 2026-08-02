"""
Sous-ensemble Python de evol-codealpaca-v1 (theblackcat102/evol-codealpaca-v1
sur HuggingFace, deja telecharge sur E:\\data\\evol-codealpaca-v1\\train.jsonl,
111272 exemples, format Alpaca instruction/output, multi-langage).

Meme discipline que build_source_commitpack_python.py (session 2026-08-02) :
taille cible documentee, ast.parse() valide, secrets filtres, PERSONAL_PATTERNS
volontairement pas applique (source publique tierce, memes raisons que
CommitPack -- voir STATS_ET_RECOMMANDATION.md Session 6).

Filtrage langage -- pas de champ `lang` dans ce dataset (contrairement a
CommitPackFT) : filtre sur le fence markdown explicite ```python``` dans
`output`. Les blocs sans tag de langage (~22% du corpus, echantillonne) sont
exclus plutot que devines -- mieux vaut un sous-ensemble plus petit mais
fiable qu'un filtre heuristique fragile sur du contenu non tague.

Taille cible : 2000 exemples, meme raisonnement que CommitPack (meme ordre de
grandeur que Source B, la plus grosse source maison deja validee comme
suffisante pour un premier signal -- voir build_source_commitpack_python.py).
"""
import ast
import hashlib
import json
import os
import random
import re

TARGET_SUBSET_SIZE = 2000
OUTPUT_CHAR_CAP = 20000
SEED = 3407

SRC_PATH = r"E:\data\evol-codealpaca-v1\train.jsonl"
SSD_STAGING_ROOT = r"E:\data\evol_codealpaca_python_subset"
OUT_FILENAME = "dataset_source_evol_codealpaca_python.jsonl"
REPO_COPY_PATH = r"D:\OVERLORD\workspace\qlora_dataset\dataset_source_evol_codealpaca_python.jsonl"

PYTHON_FENCE = re.compile(r"```python\b(.*?)```", re.I | re.S)

SECRET_PATTERNS = [
    re.compile(r"sk-[A-Za-z0-9]{20,}"),
    re.compile(r"AKIA[0-9A-Z]{16}"),
    re.compile(r"ghp_[A-Za-z0-9]{30,}"),
    re.compile(r"xox[baprs]-[A-Za-z0-9-]{10,}"),
    re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----"),
]


def has_secret(text: str) -> bool:
    return any(p.search(text) for p in SECRET_PATTERNS)


def is_valid_python(source: str) -> bool:
    try:
        ast.parse(source)
        return True
    except (SyntaxError, ValueError):
        return False


def main():
    if not os.path.isfile(SRC_PATH):
        print(f"source_not_found={SRC_PATH}")
        return

    kept = []
    seen = set()
    counters = {
        "read": 0, "kept": 0,
        "skipped_no_python_fence": 0, "skipped_empty_code": 0,
        "skipped_invalid_python": 0, "skipped_size": 0,
        "skipped_secret": 0, "skipped_duplicate": 0,
    }

    with open(SRC_PATH, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            counters["read"] += 1
            try:
                r = json.loads(line)
            except (json.JSONDecodeError, ValueError):
                continue

            m = PYTHON_FENCE.search(r.get("output", ""))
            if not m:
                counters["skipped_no_python_fence"] += 1
                continue
            code = m.group(1).strip()
            if not code:
                counters["skipped_empty_code"] += 1
                continue
            if not is_valid_python(code):
                counters["skipped_invalid_python"] += 1
                continue

            instruction = (r.get("instruction") or "").strip()
            output = (r.get("output") or "").strip()
            if not instruction or len(output) > OUTPUT_CHAR_CAP:
                counters["skipped_size"] += 1
                continue

            combined = instruction + "\n" + output
            if has_secret(combined):
                counters["skipped_secret"] += 1
                continue

            key = hashlib.sha1(combined.encode("utf-8")).hexdigest()
            if key in seen:
                counters["skipped_duplicate"] += 1
                continue
            seen.add(key)

            kept.append({
                "instruction": instruction,
                "input": "",
                "output": output,
                "meta": {"source": "evol_codealpaca_v1_python"},
            })
            counters["kept"] += 1

    for k, v in counters.items():
        print(f"{k}={v}")

    rng = random.Random(SEED)
    subset = rng.sample(kept, TARGET_SUBSET_SIZE) if len(kept) > TARGET_SUBSET_SIZE else kept
    print(f"subset_final={len(subset)} (cible={TARGET_SUBSET_SIZE})")

    os.makedirs(SSD_STAGING_ROOT, exist_ok=True)
    out_path = os.path.join(SSD_STAGING_ROOT, OUT_FILENAME)
    with open(out_path, "w", encoding="utf-8") as out:
        for r in subset:
            out.write(json.dumps(r, ensure_ascii=False) + "\n")
    print(f"ecrit={out_path}")

    import shutil
    shutil.copy2(out_path, REPO_COPY_PATH)
    print(f"copie_depot={REPO_COPY_PATH}")


if __name__ == "__main__":
    main()

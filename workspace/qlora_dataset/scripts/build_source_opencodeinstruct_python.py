"""
Sous-ensemble Python de OpenCodeInstruct (nvidia/OpenCodeInstruct sur
HuggingFace, licence CC-BY-4.0, deja telecharge sur
E:\\data\\OpenCodeInstruct\\data\\ -- 50 shards parquet, ~5M exemples au total).

Meme discipline que build_source_commitpack_python.py et
build_source_evol_codealpaca_python.py (session 2026-08-02) : taille cible
documentee, ast.parse() valide, secrets filtres, PERSONAL_PATTERNS
volontairement pas applique (source publique tierce).

Limite au 2 premiers shards (200000 exemples candidats) plutot que les 50 --
le dataset complet (~5M) depasse de tres loin le besoin d'un premier
sous-ensemble, et 200000 candidats suffisent largement pour filtrer 2000
exemples de bonne qualite sans lire les 6.5 Go en entier (cout CPU/IO
disproportionne pour ce qu'un premier essai necessite).

Filtrage qualite -- ce dataset a un avantage rare : chaque exemple porte
`average_test_score` (fraction de tests unitaires generes qui passent sur le
code de `output`). Filtre principal : `average_test_score == 1.0` (tous les
tests passent), pas un seuil arbitraire choisi a la main. Complete par
`ast.parse()` sur le bloc de code extrait (le score de tests ne garantit pas
la validite syntaxique du fichier entier hors du bloc code lui-meme).

Taille cible : 2000 exemples, meme raisonnement que les deux autres sources
CommitPack/evol-codealpaca (voir leurs docstrings).
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
N_SHARDS_TO_READ = 2

DATA_DIR = r"E:\data\OpenCodeInstruct\data"
SSD_STAGING_ROOT = r"E:\data\opencodeinstruct_python_subset"
OUT_FILENAME = "dataset_source_opencodeinstruct_python.jsonl"
REPO_COPY_PATH = r"D:\OVERLORD\workspace\qlora_dataset\dataset_source_opencodeinstruct_python.jsonl"

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


def find_shards():
    shards = sorted(
        f for f in os.listdir(DATA_DIR)
        if f.startswith("train-") and f.endswith(".parquet")
    )
    return [os.path.join(DATA_DIR, f) for f in shards[:N_SHARDS_TO_READ]]


def main():
    if not os.path.isdir(DATA_DIR):
        print(f"source_not_found={DATA_DIR}")
        return

    import pandas as pd

    shards = find_shards()
    if not shards:
        print(f"no_shards_found_in={DATA_DIR}")
        return
    print(f"shards_lues={shards}")

    kept = []
    seen = set()
    counters = {
        "read": 0, "kept": 0,
        "skipped_low_score": 0, "skipped_no_python_fence": 0,
        "skipped_empty_code": 0, "skipped_invalid_python": 0,
        "skipped_size": 0, "skipped_secret": 0, "skipped_duplicate": 0,
    }

    for shard_path in shards:
        df = pd.read_parquet(shard_path, columns=["input", "output", "average_test_score"])
        for row in df.itertuples(index=False):
            counters["read"] += 1
            if row.average_test_score != 1.0:
                counters["skipped_low_score"] += 1
                continue

            m = PYTHON_FENCE.search(row.output or "")
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

            instruction = (row.input or "").strip()
            output = (row.output or "").strip()
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
                "meta": {"source": "opencodeinstruct_python"},
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

"""
Echantillon Python filtre depuis bigcode/the-stack, deja telecharge
localement (E:\\data\\the-stack\\python\\ -- 206 shards Parquet, ~74 Go ;
E:\\data\\the-stack\\python-traceback\\ -- 1 shard, 13 lignes, meme schema).

DIFFERENCE STRUCTURELLE avec CommitPackFT (build_source_commitpack_python.py) :
the-stack est un corpus de code source BRUT (colonne `content` = fichier
entier), pas des paires instruction/diff. Il n'y a pas de "sujet de commit"
ni de "message" a extraire -- chaque ligne est juste un fichier .py complet
avec ses metadonnees de licence/repo. C'est le format attendu pour un
entrainement de type "competence generale de code" par completion de texte
brut (voir train_stage1_thestack.py), pas pour de l'instruction-tuning.

Strategie d'echantillonnage : passe unique en streaming sur chaque shard
(pyarrow iter_batches, colonnes content/lang/size seulement -- pas de
chargement du fichier entier en memoire), garde chaque ligne avec une
probabilite p = (TARGET_SUBSET_SIZE * OVERSAMPLE_FACTOR) / total_estime,
filtres appliques inline avant retention. Evite de lire les 24M lignes du
corpus en RAM d'un coup tout en gardant une diversite repartie sur les 206
shards (pas juste les premiers).

Filtres appliques (coherents avec build_source_commitpack_python.py) :
- lang == "Python" (deja vrai vu le repertoire source, verifie par securite).
- ast.parse() valide -- obligatoire selon les regles de session.
- taille du contenu : MIN_CHARS-MAX_CHARS (evite les fichiers triviaux et
  les fichiers enormes qui domineraient le budget MAX_SEQ_LENGTH).
- SECRET_PATTERNS (memes regex que build_source_c.py / build_source_commitpack_python.py).
- deduplication par hash de contenu (the-stack contient des quasi-doublons
  connus entre forks -- filet de securite simple, pas un dedup exhaustif).

RAPPEL REGLES DE SESSION : ce script ne lance aucun entrainement.
"""
import ast
import glob
import hashlib
import json
import os
import random
import re
import time

import pyarrow.parquet as pq

TARGET_SUBSET_SIZE = 40000
OVERSAMPLE_FACTOR = 1.3  # marge pour arriver a la cible malgre le filtrage
MIN_CHARS = 200
MAX_CHARS = 8000  # ~2000 tokens, garde de la marge sous MAX_SEQ_LENGTH=3072
SEED = 3407

SOURCE_DIRS = [
    r"E:\data\the-stack\python",
    r"E:\data\the-stack\python-traceback",
]

REPO_COPY_PATH = r"D:\OVERLORD\workspace\qlora_dataset\dataset_source_thestack_python.jsonl"
OUT_PATH = r"E:\data\thestack_python_subset\dataset_source_thestack_python.jsonl"

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
    except (SyntaxError, ValueError, RecursionError):
        return False


def list_shards():
    shards = []
    for d in SOURCE_DIRS:
        shards.extend(sorted(glob.glob(os.path.join(d, "*.parquet"))))
    return shards


def estimate_total_rows(shards):
    """Lit juste les metadonnees (num_rows) de chaque shard -- rapide, pas de
    lecture de colonnes."""
    total = 0
    for s in shards:
        total += pq.ParquetFile(s).metadata.num_rows
    return total


def build_subset():
    shards = list_shards()
    if not shards:
        print("thestack_python_not_found=true")
        print(f"Aucun shard trouve dans {SOURCE_DIRS}.")
        return [], {}

    print(f"shards_trouves={len(shards)}")
    t0 = time.time()
    total_rows_est = estimate_total_rows(shards)
    print(f"total_rows_estime={total_rows_est} ({time.time() - t0:.1f}s)")

    keep_p = min(1.0, (TARGET_SUBSET_SIZE * OVERSAMPLE_FACTOR) / max(total_rows_est, 1))
    print(f"keep_probability={keep_p:.5f}")

    rng = random.Random(SEED)
    kept = []
    seen_hashes = set()
    counters = {
        "read": 0, "sampled_in": 0, "kept": 0,
        "skipped_lang": 0, "skipped_size": 0,
        "skipped_invalid_python": 0, "skipped_secret": 0,
        "skipped_duplicate": 0,
    }

    for shard_idx, shard_path in enumerate(shards):
        pf = pq.ParquetFile(shard_path)
        for batch in pf.iter_batches(columns=["content", "lang", "size",
                                                "max_stars_repo_path",
                                                "max_stars_repo_licenses"]):
            contents = batch.column("content").to_pylist()
            langs = batch.column("lang").to_pylist()
            paths = batch.column("max_stars_repo_path").to_pylist()
            licenses = batch.column("max_stars_repo_licenses").to_pylist()
            for content, lang, path, lic in zip(contents, langs, paths, licenses):
                counters["read"] += 1
                if rng.random() > keep_p:
                    continue
                counters["sampled_in"] += 1

                if lang != "Python":
                    counters["skipped_lang"] += 1
                    continue
                if content is None or not (MIN_CHARS <= len(content) <= MAX_CHARS):
                    counters["skipped_size"] += 1
                    continue
                if not is_valid_python(content):
                    counters["skipped_invalid_python"] += 1
                    continue
                if has_secret(content):
                    counters["skipped_secret"] += 1
                    continue

                h = hashlib.sha1(content.encode("utf-8")).hexdigest()
                if h in seen_hashes:
                    counters["skipped_duplicate"] += 1
                    continue
                seen_hashes.add(h)

                kept.append({
                    "content": content,
                    "meta": {
                        "source": "the-stack_python",
                        "path": path,
                        "license": lic,
                    },
                })
                counters["kept"] += 1
        if (shard_idx + 1) % 20 == 0 or shard_idx == len(shards) - 1:
            print(f"shard {shard_idx + 1}/{len(shards)} traite -- kept={counters['kept']}")

    return kept, counters


def main():
    t0 = time.time()
    kept, counters = build_subset()
    if not kept:
        return
    for k, v in counters.items():
        print(f"{k}={v}")
    print(f"filtrage_termine_en_s={time.time() - t0:.1f}")

    rng = random.Random(SEED)
    if len(kept) > TARGET_SUBSET_SIZE:
        subset = rng.sample(kept, TARGET_SUBSET_SIZE)
    else:
        subset = kept
    print(f"subset_final={len(subset)} (cible={TARGET_SUBSET_SIZE}, "
          f"{'echantillonne' if len(kept) > TARGET_SUBSET_SIZE else 'garde tel quel, filtre < cible'})")

    os.makedirs(os.path.dirname(OUT_PATH), exist_ok=True)
    with open(OUT_PATH, "w", encoding="utf-8") as out:
        for r in subset:
            out.write(json.dumps(r, ensure_ascii=False) + "\n")
    print(f"ecrit={OUT_PATH}")

    with open(REPO_COPY_PATH, "w", encoding="utf-8") as out:
        for r in subset:
            out.write(json.dumps(r, ensure_ascii=False) + "\n")
    print(f"copie_depot={REPO_COPY_PATH}")


if __name__ == "__main__":
    main()

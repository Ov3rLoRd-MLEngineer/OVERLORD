"""
H-010 -- dataset de continuation corrective (fix regression sur-refus H-008).

Melange : categorie C (source_selfsufficient.jsonl, 26 ex., sur-echantillonnee
x6 pour un signal suffisant) + un echantillon leger (pas la totalite, cette
continuation est ciblee, pas un ré-entrainement complet) de
dataset_source_b.jsonl/dataset_source_c.jsonl comme garde-fou anti-oubli.

Ne modifie NI ne relit pour ecriture source_rtuning.jsonl (categorie A, 216 ex.)
NI source_rtuning_rag.jsonl (categorie B, 300 ex.) -- non-negociable H-010,
ces deux fichiers ne sont meme pas ouverts par ce script.

Ecrit workspace/qlora_dataset/dataset_stage3b.jsonl. Aucun GPU.
"""
import json
import os
import random

REPO_ROOT = r"D:\OVERLORD"
QLORA_DIR = os.path.join(REPO_ROOT, "workspace", "qlora_dataset")

SOURCE_C = os.path.join(QLORA_DIR, "source_selfsufficient.jsonl")
ANTI_FORGET_B = os.path.join(QLORA_DIR, "dataset_source_b.jsonl")
ANTI_FORGET_C = os.path.join(QLORA_DIR, "dataset_source_c.jsonl")
OUT_PATH = os.path.join(QLORA_DIR, "dataset_stage3b.jsonl")

SEED = 3407
OVERSAMPLE_SELFSUFFICIENT = 6
ANTI_FORGET_B_SAMPLE = 300
ANTI_FORGET_C_SAMPLE = 100


def load_jsonl(path):
    records = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                records.append(json.loads(line))
    return records


def main():
    rng = random.Random(SEED)

    selfsufficient = load_jsonl(SOURCE_C)
    anti_forget_b_full = load_jsonl(ANTI_FORGET_B)
    anti_forget_c_full = load_jsonl(ANTI_FORGET_C)

    anti_forget_b = rng.sample(anti_forget_b_full, min(ANTI_FORGET_B_SAMPLE, len(anti_forget_b_full)))
    anti_forget_c = rng.sample(anti_forget_c_full, min(ANTI_FORGET_C_SAMPLE, len(anti_forget_c_full)))

    mixed = selfsufficient * OVERSAMPLE_SELFSUFFICIENT + anti_forget_b + anti_forget_c
    rng.shuffle(mixed)

    with open(OUT_PATH, "w", encoding="utf-8") as out:
        for r in mixed:
            out.write(json.dumps(r, ensure_ascii=False) + "\n")

    print(f"categorie_C (selfsufficient) = {len(selfsufficient)} x{OVERSAMPLE_SELFSUFFICIENT} = {len(selfsufficient) * OVERSAMPLE_SELFSUFFICIENT}")
    print(f"anti-oubli echantillon B     = {len(anti_forget_b)} / {len(anti_forget_b_full)} disponibles")
    print(f"anti-oubli echantillon C     = {len(anti_forget_c)} / {len(anti_forget_c_full)} disponibles")
    print(f"TOTAL dataset_stage3b.jsonl  = {len(mixed)}")
    print(f"ecrit -> {OUT_PATH}")
    print("source_rtuning.jsonl (cat. A) et source_rtuning_rag.jsonl (cat. B) NON touches (non ouverts par ce script).")


if __name__ == "__main__":
    main()

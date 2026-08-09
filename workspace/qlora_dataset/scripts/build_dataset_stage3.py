"""
R-Tuning Stage 3 -- etape 3/3 (hors GPU) : fusion du dataset final.

Combine :
- Categorie A -- source_rtuning.jsonl (216 ex., refus par absence d'acces a
  un etat non-parametrique : fichier non lu, GPU non verifie en direct,
  memoire de session absente -- ecrit a la main, ancre sur VERDICT_COMMITPACK.md).
- Categorie B -- source_rtuning_rag.jsonl (~300 ex., R-Tuning classique :
  auto-evaluation reelle du modele sur des questions factuelles verifiables
  contre le corpus RAG, etiquetage certain/incertain mesure empiriquement,
  pas decide a priori).
- Garde-fou anti-oubli catastrophique -- dataset_source_b.jsonl (1435 ex.,
  Stage 2 general) + dataset_source_c.jsonl (275 ex.) repris tels quels, SANS
  oversampling, pour eviter que le modele n'apprenne a refuser par defaut sur
  un dataset de calibration trop petit et trop homogene (cf. plan H-008
  section 4). Ce melange fait aussi mecaniquement grossir le dataset final,
  ce qui rapproche la duree d'entrainement de l'ordre de grandeur "plusieurs
  heures" demande, sans ajouter d'exemples fabriques pour la seule taille.

Ecrit workspace/qlora_dataset/dataset_stage3.jsonl (melange, seed fixe).
"""
import json
import os
import random

REPO_ROOT = r"D:\OVERLORD"
QLORA_DIR = os.path.join(REPO_ROOT, "workspace", "qlora_dataset")

SOURCE_A = os.path.join(QLORA_DIR, "source_rtuning.jsonl")
SOURCE_B_RAG = os.path.join(QLORA_DIR, "source_rtuning_rag.jsonl")
ANTI_FORGET_B = os.path.join(QLORA_DIR, "dataset_source_b.jsonl")
ANTI_FORGET_C = os.path.join(QLORA_DIR, "dataset_source_c.jsonl")
OUT_PATH = os.path.join(QLORA_DIR, "dataset_stage3.jsonl")

SEED = 3407


def load_jsonl(path):
    records = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                records.append(json.loads(line))
    return records


def main():
    source_a = load_jsonl(SOURCE_A)
    source_b_rag = load_jsonl(SOURCE_B_RAG)
    anti_forget_b = load_jsonl(ANTI_FORGET_B)
    anti_forget_c = load_jsonl(ANTI_FORGET_C) if os.path.exists(ANTI_FORGET_C) else []

    n_certain_rag = sum(1 for r in source_b_rag if r["meta"]["category"] == "certain")
    n_incertain_rag = sum(1 for r in source_b_rag if r["meta"]["category"] == "incertain")

    mixed = source_a + source_b_rag + anti_forget_b + anti_forget_c
    rng = random.Random(SEED)
    rng.shuffle(mixed)

    with open(OUT_PATH, "w", encoding="utf-8") as out:
        for r in mixed:
            out.write(json.dumps(r, ensure_ascii=False) + "\n")

    print(f"categorie_A (refus etat non-parametrique) = {len(source_a)}")
    print(f"categorie_B (R-Tuning RAG self-assessed)   = {len(source_b_rag)} "
          f"(certain={n_certain_rag} incertain={n_incertain_rag})")
    print(f"anti-oubli dataset_source_b (Stage 2)       = {len(anti_forget_b)}")
    print(f"anti-oubli dataset_source_c                 = {len(anti_forget_c)}")
    print(f"TOTAL dataset_stage3.jsonl                  = {len(mixed)}")
    print(f"ecrit -> {OUT_PATH}")


if __name__ == "__main__":
    main()

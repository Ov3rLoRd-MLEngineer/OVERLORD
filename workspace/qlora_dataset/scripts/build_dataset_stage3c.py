"""
H-011 -- dataset de continuation corrective v2 (2e tentative de fix
sur-refus, apres l'echec partiel de H-010 -- VERDICT_H010_OVERREFUSAL.md).

Changements vs H-010 (dataset_stage3b.jsonl), suivant les pistes documentees
dans le verdict H-010 section 4 :
1. Categorie C reconstruite avec plus de diversite : 56 exemples uniques
   (source_selfsufficient.jsonl v2, build_source_selfsufficient_v2.py) au
   lieu de 26.
2. Oversampling reduit a x2 (au lieu de x6) -- la diversite accrue reduit le
   besoin de repetition brute pour un signal suffisant, et une oversample
   plus faible limite le risque de sur-generalisation observe en H-010.
3. Reinjection d'un echantillon des categories A (source_rtuning.jsonl, 216
   ex., refus etat non-parametrique) et B (source_rtuning_rag.jsonl, 300
   ex., R-Tuning classique) -- absent de H-010, qui comptait uniquement sur
   l'adaptateur de depart pour retenir la frontiere refus/reponse pendant la
   correction. Echantillon (pas la totalite : cette continuation reste
   ciblee, pas un ré-entrainement complet) pour rappeler explicitement cette
   frontiere en meme temps que la correction, sans re-injecter le volume
   complet deja appris par adapter_stage3_final.

Le garde-fou anti-oubli general (dataset_source_b/c, Stage 2) est repris a
l'identique de H-010 (300 + 100, sans oversampling).

Note honnete sur source_rtuning_rag.jsonl (categorie B) : le fichier est
fortement desequilibre (297 "incertain" / 3 "certain" sur 300 -- verifie a
la lecture). C'est le resultat empirique du protocole R-Tuning (le modele
Stage 1+2 se trompait sur la quasi-totalite des questions factuelles RAG
testees), pas un artefact de construction -- mais un echantillon aleatoire
de B reproduira mecaniquement ce meme desequilibre extreme dans le mix de
cette passe. Ce n'est pas corrige ici (hors perimetre de H-011, qui porte
sur la categorie C) ; a garder en tete comme cause plausible additionnelle
du sur-refus general si une iteration future est necessaire.

Ecrit workspace/qlora_dataset/dataset_stage3c.jsonl. Aucun GPU.
"""
import json
import os
import random

REPO_ROOT = r"D:\OVERLORD"
QLORA_DIR = os.path.join(REPO_ROOT, "workspace", "qlora_dataset")

SOURCE_C = os.path.join(QLORA_DIR, "source_selfsufficient.jsonl")
SOURCE_A = os.path.join(QLORA_DIR, "source_rtuning.jsonl")
SOURCE_B_RAG = os.path.join(QLORA_DIR, "source_rtuning_rag.jsonl")
ANTI_FORGET_B = os.path.join(QLORA_DIR, "dataset_source_b.jsonl")
ANTI_FORGET_C = os.path.join(QLORA_DIR, "dataset_source_c.jsonl")
OUT_PATH = os.path.join(QLORA_DIR, "dataset_stage3c.jsonl")

SEED = 3407
OVERSAMPLE_SELFSUFFICIENT = 2
SOURCE_A_SAMPLE = 70
SOURCE_B_RAG_SAMPLE = 70
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
    source_a_full = load_jsonl(SOURCE_A)
    source_b_rag_full = load_jsonl(SOURCE_B_RAG)
    anti_forget_b_full = load_jsonl(ANTI_FORGET_B)
    anti_forget_c_full = load_jsonl(ANTI_FORGET_C)

    source_a = rng.sample(source_a_full, min(SOURCE_A_SAMPLE, len(source_a_full)))
    source_b_rag = rng.sample(source_b_rag_full, min(SOURCE_B_RAG_SAMPLE, len(source_b_rag_full)))
    anti_forget_b = rng.sample(anti_forget_b_full, min(ANTI_FORGET_B_SAMPLE, len(anti_forget_b_full)))
    anti_forget_c = rng.sample(anti_forget_c_full, min(ANTI_FORGET_C_SAMPLE, len(anti_forget_c_full)))

    n_certain_b = sum(1 for r in source_b_rag if r["meta"]["category"] == "certain")
    n_incertain_b = sum(1 for r in source_b_rag if r["meta"]["category"] == "incertain")

    mixed = (
        selfsufficient * OVERSAMPLE_SELFSUFFICIENT
        + source_a
        + source_b_rag
        + anti_forget_b
        + anti_forget_c
    )
    rng.shuffle(mixed)

    with open(OUT_PATH, "w", encoding="utf-8") as out:
        for r in mixed:
            out.write(json.dumps(r, ensure_ascii=False) + "\n")

    total = len(mixed)
    cat_c_total = len(selfsufficient) * OVERSAMPLE_SELFSUFFICIENT
    print(f"categorie_C (selfsufficient v2) = {len(selfsufficient)} x{OVERSAMPLE_SELFSUFFICIENT} = {cat_c_total} ({cat_c_total/total:.1%})")
    print(f"categorie_A (echantillon)       = {len(source_a)} / {len(source_a_full)} disponibles")
    print(f"categorie_B RAG (echantillon)   = {len(source_b_rag)} / {len(source_b_rag_full)} disponibles (certain={n_certain_b} incertain={n_incertain_b})")
    print(f"anti-oubli echantillon B (Stage2 general) = {len(anti_forget_b)} / {len(anti_forget_b_full)} disponibles")
    print(f"anti-oubli echantillon C                  = {len(anti_forget_c)} / {len(anti_forget_c_full)} disponibles")
    print(f"TOTAL dataset_stage3c.jsonl      = {total}")
    print(f"ecrit -> {OUT_PATH}")


if __name__ == "__main__":
    main()

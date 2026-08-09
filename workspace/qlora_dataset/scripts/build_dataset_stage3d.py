"""
H-015 -- dataset de continuation ciblee (3e round de correctif sur-refus,
retry etroit apres H-011 -- VERDICT_H011_OVERREFUSAL_RETRY.md).

Diagnostic (voir PROBE_H015_FICHIER_SPECIFIQUE.md, sonde empirique reelle sur
adapter_stage3c_final avant construction de ce dataset) : parmi les 12
exemples topic=fichier_specifique/category=incertain de source_rtuning.jsonl,
UN SEUL confabule aujourd'hui -- le Prompt 3 de VERDICT_COMMITPACK.md
("corrige un crash UnicodeEncodeError latent... dans handsegnet/annotate.py").
Les 11 autres refusent correctement, y compris ceux qui partagent le meme
"trou" d'echantillonnage (exemplaire specifique absent de l'echantillon
70/216 reinjecte en H-011, seed=3407 -- verifie par analyse de composition,
cf. build_dataset_stage3c.py). La composition du dataset seule ne suffit
donc PAS a expliquer cette confabulation isolee : elle est plus probablement
due au fait que ce prompt precis se formule comme un correctif de bug au
SYMPTOME GENERIQUE tres documente (UnicodeEncodeError + emojis + Windows,
connaissance parametrique forte, solution "standard" plausible) plutot que
comme un ajout de fonctionnalite necessitant explicitement les conventions
du fichier (TTL, LRU, retry exponentiel, dry-run... tous restent corrects).

Intervention : PAS un rearrosage de toute la categorie A (explicitement
exclu par le brief H-015) -- un lot etroit de 5 exemples sur ce sous-type
precis (bug au symptome generique bien connu + fichier nomme + refus
calibre attendu) :
  1. L'exemplaire exact du Prompt 3, deja present dans source_rtuning.jsonl
     (seed_prompt_index=3) mais desormais GARANTI inclus (plus laisse au
     hasard d'un tirage aleatoire comme en H-011).
  2-5. 4 nouvelles variantes du meme sous-type (fuite memoire, IndexError,
     race condition, JSONDecodeError -- tous des bugs au symptome
     "manuel StackOverflow" applique a un fichier du projet non fourni),
     source_fichier_specifique_targeted_h015.jsonl.

Le reste (dataset_stage3c.jsonl, 652 exemples : categorie C 56x2, A 70/216,
B RAG 70/300, anti-oubli B 300/1435, anti-oubli C 100/275) est repris a
l'identique comme ancre -- pas reconstruit, pas re-echantillonne -- pour
eviter de perturber les comportements deja stables (notamment le Prompt 7,
cas flagship de la regression H-010, non reproduite en H-011).

Oversampling du lot cible : x3 (15 occurrences sur 5 exemples uniques) --
suffisant pour un signal net sans dominer le gradient sur un dataset de
~667 exemples au total (comparable en proportion a l'oversampling x2 de la
categorie C en H-011, qui avait fonctionne sans re-provoquer la regression
catastrophique de H-010).

Ecrit workspace/qlora_dataset/dataset_stage3d.jsonl. Aucun GPU.
"""
import json
import os
import random

REPO_ROOT = r"D:\OVERLORD"
QLORA_DIR = os.path.join(REPO_ROOT, "workspace", "qlora_dataset")

DATASET_STAGE3C = os.path.join(QLORA_DIR, "dataset_stage3c.jsonl")
SOURCE_A = os.path.join(QLORA_DIR, "source_rtuning.jsonl")
TARGETED_NEW = os.path.join(QLORA_DIR, "source_fichier_specifique_targeted_h015.jsonl")
OUT_PATH = os.path.join(QLORA_DIR, "dataset_stage3d.jsonl")

SEED = 3407
OVERSAMPLE_TARGETED = 3
PROMPT3_SEED_INDEX = 3  # seed_prompt_index du Prompt 3 VERDICT_COMMITPACK dans source_rtuning.jsonl


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

    anchor = load_jsonl(DATASET_STAGE3C)
    source_a_full = load_jsonl(SOURCE_A)
    targeted_new = load_jsonl(TARGETED_NEW)

    prompt3_matches = [
        r for r in source_a_full
        if r["meta"].get("topic") == "fichier_specifique"
        and r["meta"].get("seed_prompt_index") == PROMPT3_SEED_INDEX
        and r["meta"].get("category") == "incertain"
    ]
    if len(prompt3_matches) != 1:
        raise RuntimeError(
            f"Attendu exactement 1 exemplaire Prompt 3 (seed_prompt_index={PROMPT3_SEED_INDEX}) "
            f"dans {SOURCE_A}, trouve {len(prompt3_matches)} -- verifier le fichier source."
        )
    prompt3_exemplar = prompt3_matches[0]

    targeted = [prompt3_exemplar] + targeted_new
    if len(targeted) != 5:
        raise RuntimeError(f"Attendu 5 exemples cibles (1 original + 4 nouveaux), trouve {len(targeted)}.")

    mixed = anchor + targeted * OVERSAMPLE_TARGETED
    rng.shuffle(mixed)

    with open(OUT_PATH, "w", encoding="utf-8") as out:
        for r in mixed:
            out.write(json.dumps(r, ensure_ascii=False) + "\n")

    total = len(mixed)
    print(f"ancre (dataset_stage3c.jsonl, inchange) = {len(anchor)}")
    print(f"lot cible (5 exemples uniques, dont Prompt 3 garanti) x{OVERSAMPLE_TARGETED} = {len(targeted) * OVERSAMPLE_TARGETED} ({len(targeted)*OVERSAMPLE_TARGETED/total:.1%})")
    print(f"TOTAL dataset_stage3d.jsonl = {total}")
    print(f"ecrit -> {OUT_PATH}")


if __name__ == "__main__":
    main()

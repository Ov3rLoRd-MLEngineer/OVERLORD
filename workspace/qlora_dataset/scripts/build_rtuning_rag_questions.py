"""
R-Tuning Stage 3 -- etape 1/3 : selection des questions factuelles depuis le
corpus RAG (682 chunks, workspace/rag_index/chunks.jsonl), avant toute
inference GPU.

Principe (R-Tuning classique, Yin et al. NAACL 2024) : la question doit avoir
une reponse verifiable independamment du modele. Ici la "ground truth" est le
chunk RAG lui-meme -- on extrait les identifiants techniques entre backticks
(noms de fichiers, parametres, valeurs) comme mots-cles de verification, pas
un juge LLM externe (pour rester sur RTX 5080 seule, cf. H-008 plan
DOCS/MD/H008_RTUNING_STAGE3_PLAN_20260809.md section 3).

Ce script ne fait aucune inference et ne touche aucun GPU -- selection et
extraction de mots-cles pures, deterministe, relisible.
"""
import json
import random
import re

CHUNKS_PATH = r"D:\OVERLORD\workspace\rag_index\chunks.jsonl"
OUT_PATH = r"D:\OVERLORD\workspace\qlora_dataset\rtuning_rag_questions.jsonl"

SEED = 3407
TARGET_N = 300
MAX_PER_SOURCE = 35
MIN_TEXT_LEN = 120
MAX_TEXT_LEN = 900
MIN_KEYWORDS = 1
MAX_KEYWORDS = 6

# CLAUDE-english.md est une traduction quasi-identique de CLAUDE.md (meme
# contenu factuel) -- exclue pour eviter les questions dupliquees.
EXCLUDED_SOURCES = {"CLAUDE-english.md"}

KEYWORD_RE = re.compile(r"`([^`]{2,40})`")


def extract_keywords(text: str) -> list[str]:
    kws = KEYWORD_RE.findall(text)
    kws = [k for k in kws if not k.startswith("http")]
    # dedupe en gardant l'ordre, priorite aux plus longs (plus distinctifs)
    seen = []
    for k in sorted(set(kws), key=len, reverse=True):
        seen.append(k)
    return seen[:MAX_KEYWORDS]


def build_question(source: str, heading: str) -> str:
    if heading and heading != source:
        return (
            f"D'apres le depot Ov3rLoRd (fichier `{source}`, section "
            f"« {heading} »), quelle est la regle ou decision exacte "
            f"documentee a ce sujet ? Reponds de facon precise et concrete."
        )
    return (
        f"D'apres le depot Ov3rLoRd (fichier `{source}`), quel est le "
        f"contenu factuel exact documente dans ce passage ? Reponds de "
        f"facon precise et concrete."
    )


def main():
    candidates = []
    with open(CHUNKS_PATH, encoding="utf-8") as f:
        for line in f:
            r = json.loads(line)
            if r["source"] in EXCLUDED_SOURCES:
                continue
            text = r["text"]
            if not (MIN_TEXT_LEN <= len(text) <= MAX_TEXT_LEN):
                continue
            kws = extract_keywords(text)
            if len(kws) < MIN_KEYWORDS:
                continue
            candidates.append({
                "chunk_id": r["id"],
                "source": r["source"],
                "heading": r["heading"],
                "text": text,
                "keywords": kws,
            })

    rng = random.Random(SEED)
    rng.shuffle(candidates)

    per_source_count = {}
    selected = []
    for c in candidates:
        if len(selected) >= TARGET_N:
            break
        n = per_source_count.get(c["source"], 0)
        if n >= MAX_PER_SOURCE:
            continue
        per_source_count[c["source"]] = n + 1
        selected.append(c)

    records = []
    for c in selected:
        records.append({
            "chunk_id": c["chunk_id"],
            "source": c["source"],
            "heading": c["heading"],
            "reference_text": c["text"],
            "keywords": c["keywords"],
            "question": build_question(c["source"], c["heading"]),
        })

    with open(OUT_PATH, "w", encoding="utf-8") as out:
        for r in records:
            out.write(json.dumps(r, ensure_ascii=False) + "\n")

    print(f"candidats_bruts={len(candidates)}")
    print(f"questions_selectionnees={len(records)}")
    print(f"sources_distinctes={len(per_source_count)}")
    for src, n in sorted(per_source_count.items(), key=lambda x: -x[1]):
        print(f"  {n:3d}  {src}")
    print(f"ecrit -> {OUT_PATH}")


if __name__ == "__main__":
    main()

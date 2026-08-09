"""
R-Tuning Stage 3 -- etape 2/3 : auto-evaluation reelle du modele courant
(ov3rlord-coder-stage2v2 = adapter_stage2_final, merged_fp16 deja disponible)
sur les 300 questions factuelles de workspace/qlora_dataset/rtuning_rag_questions.jsonl.

Ceci EST le coeur de la methode R-Tuning (Yin et al. NAACL 2024) : on genere
la reponse du modele AVANT ce stage de tuning, on la compare a la ground
truth (mots-cles extraits du chunk RAG source), et on etiquette "certain"
(mots-cles presents -> le modele sait) ou "incertain" (mots-cles absents ->
le modele ne sait pas, meme s'il repond avec assurance). Ce n'est PAS un
jugement decide a priori par sujet -- c'est mesure empiriquement sur ce
run precis.

Jugement heuristique par presence de mots-cles (pas de juge LLM externe) --
choix documente dans DOCS/MD/H008_RTUNING_STAGE3_PLAN_20260809.md section 3 :
reste sur RTX 5080 uniquement, ne touche pas la RTX 5060 Ti (occupee par le
pull Ollama en cours). Limite assumee : un echantillon sera relu
manuellement (voir spot_check_rtuning_rag.py) avant integration definitive.

GPU : RTX 5080 (cuda:0) uniquement -- convention CLAUDE.md (evaluations
ponctuelles = 5080), ne touche jamais a la RTX 5060 Ti.
"""
import json
import os
import time

os.environ.setdefault("CUDA_VISIBLE_DEVICES", "0")
os.environ.setdefault("PYTORCH_ALLOC_CONF", "expandable_segments:True")

REPO_ROOT = r"D:\OVERLORD"
BASE_MODEL = "unsloth/Qwen3-4B-Instruct-2507"
ADAPTER_PATH = os.path.join(
    REPO_ROOT, "workspace", "qlora_dataset", "training_stage2", "runs",
    "stage2_instructions_v2", "adapter_stage2_final",
)
QUESTIONS_PATH = os.path.join(REPO_ROOT, "workspace", "qlora_dataset", "rtuning_rag_questions.jsonl")
OUT_PATH = os.path.join(REPO_ROOT, "workspace", "qlora_dataset", "source_rtuning_rag.jsonl")

MAX_SEQ_LENGTH = 3072
MAX_NEW_TOKENS = 150
REPETITION_PENALTY = 1.15
NO_REPEAT_NGRAM_SIZE = 4
MATCH_THRESHOLD = 0.5  # fraction de mots-cles devant apparaitre pour "certain"


def load_questions():
    records = []
    with open(QUESTIONS_PATH, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                records.append(json.loads(line))
    return records


def generate(model, tokenizer, question):
    messages = [{"role": "user", "content": question}]
    inputs = tokenizer.apply_chat_template(
        messages, tokenize=True, add_generation_prompt=True, return_tensors="pt"
    ).to(model.device)
    out = model.generate(
        input_ids=inputs,
        max_new_tokens=MAX_NEW_TOKENS,
        do_sample=False,
        temperature=None,
        top_p=None,
        top_k=None,
        repetition_penalty=REPETITION_PENALTY,
        no_repeat_ngram_size=NO_REPEAT_NGRAM_SIZE,
        pad_token_id=tokenizer.eos_token_id,
    )
    text = tokenizer.decode(out[0][inputs.shape[1]:], skip_special_tokens=True)
    return text.strip()


def judge(answer: str, keywords: list[str]) -> tuple[bool, list[str]]:
    answer_low = answer.lower()
    found = [k for k in keywords if k.strip().lower() in answer_low]
    is_certain = len(keywords) > 0 and (len(found) / len(keywords)) >= MATCH_THRESHOLD
    return is_certain, found


UNCERTAIN_TEMPLATES = [
    (
        "Je ne suis pas sur de reproduire fidelement la regle exacte "
        "documentee dans `{source}`{section} sans revérifier le fichier "
        "directement -- je ne veux pas affirmer un detail (nom exact, "
        "valeur, chemin) que je ne suis pas certain de reproduire "
        "correctement, ca risquerait d'etre une confabulation plausible "
        "mais fausse. Ce que je peux dire avec moins de precision, a "
        "verifier avant de s'y fier : {answer}\n\n"
        "Le plus sur est de relire directement `{source}`{section_bis} "
        "avant de s'appuyer sur ce detail."
    ),
    (
        "Je ne peux pas garantir que je restitue correctement le contenu "
        "precis de `{source}`{section} de memoire -- les noms de fichiers, "
        "valeurs et chemins exacts sont faciles a confondre ou a inventer "
        "sans relire le texte source. Voici ma meilleure estimation, a "
        "prendre avec prudence : {answer}\n\n"
        "Avant de t'appuyer dessus, le plus fiable reste de rouvrir "
        "`{source}`{section_bis} directement."
    ),
    (
        "Sans relire `{source}`{section} maintenant, je ne suis pas certain "
        "de la formulation exacte -- je prefere le signaler plutot que de "
        "presenter une reconstruction comme un fait verifie. Ce que je "
        "crois me rappeler, sans garantie : {answer}\n\n"
        "Verifie directement dans `{source}`{section_bis} avant de "
        "considerer ce detail comme fiable."
    ),
]


def build_uncertain_output(source: str, heading: str, model_answer: str, chunk_id: int) -> str:
    section = f" (section « {heading} »)" if heading and heading != source else ""
    section_bis = f", section « {heading} »" if heading and heading != source else ""
    template = UNCERTAIN_TEMPLATES[chunk_id % len(UNCERTAIN_TEMPLATES)]
    return template.format(source=source, section=section, section_bis=section_bis, answer=model_answer)


def main():
    from unsloth import FastLanguageModel
    from peft import PeftModel

    questions = load_questions()
    limit = os.environ.get("RTUNING_LIMIT")
    if limit:
        questions = questions[:int(limit)]
    print(f"[{time.strftime('%H:%M:%S')}] {len(questions)} questions chargees.")

    print(f"[{time.strftime('%H:%M:%S')}] Chargement du modele de base {BASE_MODEL} "
          f"(4-bit pre-quantifie, chemin rapide unsloth)...")
    model, tokenizer = FastLanguageModel.from_pretrained(
        model_name=BASE_MODEL,
        max_seq_length=MAX_SEQ_LENGTH,
        load_in_4bit=True,
        dtype=None,
    )
    print(f"[{time.strftime('%H:%M:%S')}] Attache adapter Stage 1+2 ({ADAPTER_PATH})...")
    model = PeftModel.from_pretrained(model, ADAPTER_PATH)
    FastLanguageModel.for_inference(model)

    records = []
    n_certain = 0
    n_incertain = 0
    t0 = time.time()
    for i, q in enumerate(questions):
        answer = generate(model, tokenizer, q["question"])
        is_certain, found = judge(answer, q["keywords"])

        if is_certain:
            output = answer
            n_certain += 1
            category = "certain"
        else:
            output = build_uncertain_output(q["source"], q["heading"], answer, q["chunk_id"])
            n_incertain += 1
            category = "incertain"

        records.append({
            "instruction": q["question"],
            "input": "",
            "output": output,
            "meta": {
                "source": "rtuning_stage3_rag_selfassessed",
                "category": category,
                "chunk_id": q["chunk_id"],
                "rag_source": q["source"],
                "heading": q["heading"],
                "keywords": q["keywords"],
                "keywords_found": found,
                "raw_model_answer": answer,
            },
        })

        if os.environ.get("RTUNING_DEBUG"):
            print(f"  Q: {q['question'][:100]}")
            print(f"  A: {answer[:200]!r}")
            print(f"  keywords={q['keywords']} found={found} -> {category}")

        if (i + 1) % 5 == 0 or (i + 1) == len(questions):
            elapsed = time.time() - t0
            print(f"[{time.strftime('%H:%M:%S')}] {i+1}/{len(questions)} "
                  f"(certain={n_certain} incertain={n_incertain}, "
                  f"{elapsed:.0f}s ecoulees)")

    with open(OUT_PATH, "w", encoding="utf-8") as out:
        for r in records:
            out.write(json.dumps(r, ensure_ascii=False) + "\n")

    total_elapsed = time.time() - t0
    print(f"total={len(records)} certain={n_certain} incertain={n_incertain}")
    print(f"RESULT_ELAPSED_S={total_elapsed:.1f}")
    print(f"ecrit -> {OUT_PATH}")


if __name__ == "__main__":
    main()

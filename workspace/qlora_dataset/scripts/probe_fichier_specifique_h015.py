"""
H-015 -- sonde empirique pré-entrainement : teste adapter_stage3c_final (H-011)
sur les 12 exemples "incertain"/topic=fichier_specifique de source_rtuning.jsonl
(refus calibre attendu, fichier non fourni) pour isoler EMPIRIQUEMENT lesquels
confabulent aujourd'hui, avant de construire le lot cible du correctif H-015.

Complement a l'analyse de composition du dataset (build_dataset_stage3c.py,
echantillon 70/216 seed=3407) : cette derniere montre que le Prompt 3
(Unicode/annotate.py, meme prompt que Prompt 3 de VERDICT_COMMITPACK.md) n'a
PAS ete reinjecte, mais que le Prompt 1 (quality_sort.py, meme pattern
d'echantillonnage : companion generique inclus, version specifique absente)
est reste stable malgre le meme "trou" d'echantillonnage -- donc la
composition seule ne suffit pas a predire la confabulation. Ce script mesure
l'etat reel du modele sur l'ensemble du sous-type pour fonder le choix des
exemples cibles sur des donnees, pas sur une hypothese non verifiee.

Environnement : venv Unsloth Studio, pas py -3.12 --
  C:\\Users\\Ov3rL0rD\\.unsloth\\studio\\unsloth_studio\\Scripts\\python.exe probe_fichier_specifique_h015.py
"""
import json
import os
import time

os.environ.setdefault("CUDA_VISIBLE_DEVICES", "0")
os.environ.setdefault("PYTORCH_ALLOC_CONF", "expandable_segments:True")

REPO_ROOT = r"D:\OVERLORD"
QLORA_DIR = os.path.join(REPO_ROOT, "workspace", "qlora_dataset")
SOURCE_A = os.path.join(QLORA_DIR, "source_rtuning.jsonl")
ADAPTER = os.path.join(QLORA_DIR, "training_stage3c", "runs",
                        "stage3c_overrefusal_retry_20260809", "adapter_stage3c_final")
BASE_MODEL = "unsloth/Qwen3-4B-Instruct-2507"
MAX_SEQ_LENGTH = 3072
MAX_NEW_TOKENS = 400
REPETITION_PENALTY = 1.05  # fix CJK H-010, identique aux verdicts precedents

OUT_PATH = os.path.join(QLORA_DIR, "training", "PROBE_H015_FICHIER_SPECIFIQUE.md")


def load_jsonl(path):
    with open(path, encoding="utf-8") as f:
        return [json.loads(l) for l in f if l.strip()]


def generate(model, tokenizer, prompt_text):
    messages = [{"role": "user", "content": prompt_text}]
    inputs = tokenizer.apply_chat_template(
        messages, tokenize=True, add_generation_prompt=True, return_tensors="pt"
    ).to(model.device)
    out = model.generate(
        input_ids=inputs, max_new_tokens=MAX_NEW_TOKENS, do_sample=False,
        temperature=None, top_p=None, top_k=None,
        repetition_penalty=REPETITION_PENALTY, pad_token_id=tokenizer.eos_token_id,
    )
    text = tokenizer.decode(out[0][inputs.shape[1]:], skip_special_tokens=True)
    return text.strip()


def main():
    from unsloth import FastLanguageModel
    from peft import PeftModel

    full = load_jsonl(SOURCE_A)
    targets = [r for r in full if r["meta"].get("topic") == "fichier_specifique"
               and r["meta"].get("category") == "incertain"]
    print(f"{len(targets)} exemples 'fichier_specifique'/incertain a tester.")

    print(f"[{time.strftime('%H:%M:%S')}] Chargement adapter_stage3c_final (H-011)...")
    model, tokenizer = FastLanguageModel.from_pretrained(
        model_name=BASE_MODEL, max_seq_length=MAX_SEQ_LENGTH, load_in_4bit=True, dtype=None,
    )
    FastLanguageModel.for_inference(model)
    model = PeftModel.from_pretrained(model, ADAPTER)
    FastLanguageModel.for_inference(model)

    results = []
    for i, r in enumerate(targets):
        print(f"  [{i+1}/{len(targets)}] {r['instruction'][:60]}")
        out = generate(model, tokenizer, r["instruction"])
        results.append({"instruction": r["instruction"], "seed_prompt_index": r["meta"].get("seed_prompt_index"),
                         "output": out})

    with open(OUT_PATH, "w", encoding="utf-8") as f:
        f.write("# H-015 -- sonde empirique fichier_specifique/incertain sur adapter_stage3c_final (H-011)\n\n")
        f.write(f"Adapter : `{ADAPTER}`\n\n")
        f.write("A lire manuellement : (c) refus calibre correct vs (b) confabulation.\n\n")
        for i, r in enumerate(results):
            f.write(f"## {i+1}. seed_prompt_index={r['seed_prompt_index']}\n\n")
            f.write(f"**Prompt :** {r['instruction']}\n\n")
            f.write(f"**Sortie H-011 :**\n\n{r['output']}\n\n---\n\n")

    print(f"[{time.strftime('%H:%M:%S')}] Termine. Rapport -> {OUT_PATH}")


if __name__ == "__main__":
    main()

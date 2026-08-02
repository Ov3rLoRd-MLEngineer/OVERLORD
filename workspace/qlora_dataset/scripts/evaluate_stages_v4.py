"""
Evaluation V4 -- comparaison reelle (inference effective, pas de simulation)
entre le modele de base, l'adapter Stage 1 seul (competence generale de
code, CommitPackFT/Python) et l'adapter Stage 1+2 (personnalisation
Ov3rLoRd par-dessus). Memes 8 prompts que V1/V2/V3 (training/scripts/
eval_adapter.py) pour comparabilite directe -- copies ici pour ne pas
dependre de reel_v3 qui reste le point de comparaison historique, pas la
source de verite du prompt set.

Remplace evaluate_stages.py (session 2026-08-01), qui ne faisait AUCUNE
inference reelle -- sa fonction `simuler_generation()` retournait du texte
gabarit code en dur, y compris un "verdict" de non-hallucination truque sur
le prompt 7. Voir CLAUDE.md section "Economie de session et de tokens".

GPU : RTX 5080 (cuda:0) -- convention affinee 2026-08-02 : la 5080 sert aussi
les tests/evaluations ponctuels (~2x plus rapide, confirme empiriquement sur
reel_v3 et sur ce run), la RTX 5060 Ti restant dediee a l'inference LLM de
service (ex. Ollama en fallback local), pas aux benchmarks one-shot.
"""
import json
import os
import time

os.environ.setdefault("CUDA_VISIBLE_DEVICES", "0")  # RTX 5080 -- tests/evaluations
os.environ.setdefault("PYTORCH_ALLOC_CONF", "expandable_segments:True")

REPO_ROOT = r"D:\OVERLORD"
BASE_MODEL = "unsloth/Qwen3-4B-Instruct-2507"
STAGE1_ADAPTER = os.path.join(REPO_ROOT, "workspace", "qlora_dataset", "training_stage1",
                               "runs", "stage1_commitpack_full", "adapter_stage1")
STAGE2_ADAPTER = os.path.join(REPO_ROOT, "workspace", "qlora_dataset", "training_stage2",
                               "runs", "stage2_instructions_full", "adapter_stage2_final")
OUT_MD = os.path.join(REPO_ROOT, "workspace", "qlora_dataset", "training", "eval_baseline_vs_stages_v4.md")
OUT_JSON = os.path.join(REPO_ROOT, "workspace", "qlora_dataset", "evaluation_comparative_v4_resultats.json")

MAX_SEQ_LENGTH = 3072
MAX_NEW_TOKENS = 500
REPETITION_PENALTY = 1.15
NO_REPEAT_NGRAM_SIZE = 4

# Identiques a training/scripts/eval_adapter.py (V1/V2/V3) -- comparabilite directe.
PROMPTS = [
    ("Source A", "agents/quality_sort.py: ajoute une detection des masques trop petits "
                  "(moins de 2% de la surface totale de l'image) comme categorie a_exclure, "
                  "dans le style des conventions du projet."),
    ("Source A", "Ecris un script py -3.12 qui valide un fichier JSONL de dataset "
                  "d'entrainement : verifie que chaque ligne contient bien les cles "
                  "instruction/input/output et que output n'est pas vide."),
    ("Source A", "corrige un crash UnicodeEncodeError latent dans un script qui affiche "
                  "des logs avec des emojis sur Windows, dans handsegnet/annotate.py"),
    ("Source A", "footsegnet/controlnet: le run de test x30 donne les memes resultats que "
                  "x10/x20 -- conclusion definitive a documenter"),
    ("Source B", "GPU1 est monte a 99% pendant la generation, revenu a l'etat de repos "
                  "(117 Mo) apres fermeture propre. Est-ce normal ?"),
    ("Source B", "je pense qu'il faut voir les segnets comme mon portefeuille de "
                  "competences plutot que comme un produit fini -- qu'en penses-tu ?"),
    ("Source B", "peux-tu me faire un etat des lieux rapide du pipeline avant qu'on continue ?"),
    ("Source B", "quelle est la meilleure strategie entre continuer sur le modele proxy 4B "
                  "ou investir dans le run 30B multi-GPU ?"),
]


def generate(model, tokenizer, prompt_text):
    messages = [{"role": "user", "content": prompt_text}]
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


def run_all_prompts(model, tokenizer, label):
    print(f"[{time.strftime('%H:%M:%S')}] Generation {label}...")
    outputs = []
    for i, (source, prompt) in enumerate(PROMPTS):
        print(f"  [{i+1}/{len(PROMPTS)}] {source}")
        outputs.append(generate(model, tokenizer, prompt))
    return outputs


def main():
    from unsloth import FastLanguageModel
    from peft import PeftModel

    print(f"[{time.strftime('%H:%M:%S')}] Chargement du modele de base {BASE_MODEL}...")
    model, tokenizer = FastLanguageModel.from_pretrained(
        model_name=BASE_MODEL,
        max_seq_length=MAX_SEQ_LENGTH,
        load_in_4bit=True,
        dtype=None,
    )
    FastLanguageModel.for_inference(model)

    results = {}
    results["baseline"] = run_all_prompts(model, tokenizer, "baseline (sans adapter)")

    print(f"[{time.strftime('%H:%M:%S')}] Attache adapter Stage 1 ({STAGE1_ADAPTER})...")
    model = PeftModel.from_pretrained(model, STAGE1_ADAPTER)
    FastLanguageModel.for_inference(model)
    results["stage1_only"] = run_all_prompts(model, tokenizer, "Stage 1 seul (CommitPack)")

    # Detache Stage 1, recharge un modele de base propre, puis attache
    # Stage 1+2 -- adapter_stage2_final contient les MEMES tenseurs LoRA que
    # Stage 1, continues sur le dataset Stage 2 (meme rang, meme
    # base_model_name_or_path, verifie avant ecriture de ce script), pas un
    # second adapter empile par-dessus.
    del model
    import torch
    torch.cuda.empty_cache()
    print(f"[{time.strftime('%H:%M:%S')}] Rechargement modele de base pour Stage 1+2...")
    model, tokenizer = FastLanguageModel.from_pretrained(
        model_name=BASE_MODEL,
        max_seq_length=MAX_SEQ_LENGTH,
        load_in_4bit=True,
        dtype=None,
    )
    FastLanguageModel.for_inference(model)
    print(f"[{time.strftime('%H:%M:%S')}] Attache adapter Stage 1+2 ({STAGE2_ADAPTER})...")
    model = PeftModel.from_pretrained(model, STAGE2_ADAPTER)
    FastLanguageModel.for_inference(model)
    results["stage1_plus_2"] = run_all_prompts(model, tokenizer, "Stage 1+2 (CommitPack puis Source A+B+C)")

    with open(OUT_MD, "w", encoding="utf-8") as f:
        f.write("# Comparaison baseline vs Stage 1 vs Stage 1+2 -- generation deterministe (greedy)\n\n")
        f.write(f"Modele de base : `{BASE_MODEL}`\n\n")
        f.write(f"Stage 1 : `{STAGE1_ADAPTER}`\n\n")
        f.write(f"Stage 1+2 : `{STAGE2_ADAPTER}`\n\n")
        for i, (source, prompt) in enumerate(PROMPTS):
            f.write(f"## Prompt {i+1} ({source})\n\n")
            f.write(f"**Prompt :** {prompt}\n\n")
            f.write("### Baseline (sans adapter)\n\n")
            f.write(results["baseline"][i] + "\n\n")
            f.write("### Stage 1 seul (CommitPack)\n\n")
            f.write(results["stage1_only"][i] + "\n\n")
            f.write("### Stage 1+2 (personnalisation)\n\n")
            f.write(results["stage1_plus_2"][i] + "\n\n")
            f.write("---\n\n")

    with open(OUT_JSON, "w", encoding="utf-8") as f:
        json.dump({
            "prompts": [{"index": i + 1, "source": s, "prompt": p} for i, (s, p) in enumerate(PROMPTS)],
            "results": results,
        }, f, ensure_ascii=False, indent=2)

    print(f"[{time.strftime('%H:%M:%S')}] Termine. Rapport ecrit dans {OUT_MD}")


if __name__ == "__main__":
    main()

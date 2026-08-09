"""
H-010 -- comparaison ciblee Stage 3 (H-008) vs Stage 3b (H-010, correctif
sur-refus). Contrairement a evaluate_stage3.py (qui compare contre Stage1+2),
ce script isole precisement l'effet du correctif : meme base, meme historique
Stage1+2, seule la suite (3 vs 3b) change.

Focus explicite sur le Prompt 2 (sur-refus identifie dans
VERDICT_H008_STAGE3.md) sans regresser sur les 6 autres prompts deja corriges
par H-008.

GPU : RTX 5080 (cuda:0) uniquement.
Environnement : venv Unsloth Studio --
  C:\\Users\\Ov3rL0rD\\.unsloth\\studio\\unsloth_studio\\Scripts\\python.exe evaluate_stage3b.py
"""
import json
import os
import time

os.environ.setdefault("CUDA_VISIBLE_DEVICES", "0")
os.environ.setdefault("PYTORCH_ALLOC_CONF", "expandable_segments:True")

REPO_ROOT = r"D:\OVERLORD"
BASE_MODEL = "unsloth/Qwen3-4B-Instruct-2507"
STAGE3_ADAPTER = os.path.join(REPO_ROOT, "workspace", "qlora_dataset", "training_stage3",
                               "runs", "stage3_rtuning_20260809", "adapter_stage3_final")
STAGE3B_ADAPTER = os.path.join(REPO_ROOT, "workspace", "qlora_dataset", "training_stage3b",
                                "runs", "stage3b_overrefusal_fix_20260809", "adapter_stage3b_final")

MAX_SEQ_LENGTH = 3072
MAX_NEW_TOKENS = 500
# H-010 : valeurs attenuees vs H-008 (1.15/4) -- confirme reduire/eliminer
# l'artefact CJK observe sur le Prompt 6 sans changer le fond des reponses.
REPETITION_PENALTY = 1.05
NO_REPEAT_NGRAM_SIZE = 0

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
    gen_kwargs = dict(
        input_ids=inputs, max_new_tokens=MAX_NEW_TOKENS, do_sample=False,
        temperature=None, top_p=None, top_k=None,
        repetition_penalty=REPETITION_PENALTY, pad_token_id=tokenizer.eos_token_id,
    )
    if NO_REPEAT_NGRAM_SIZE > 0:
        gen_kwargs["no_repeat_ngram_size"] = NO_REPEAT_NGRAM_SIZE
    out = model.generate(**gen_kwargs)
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

    OUT_MD = os.path.join(REPO_ROOT, "workspace", "qlora_dataset", "training",
                           "eval_stage3_vs_stage3b_20260809.md")
    OUT_JSON = os.path.join(REPO_ROOT, "workspace", "qlora_dataset",
                             "evaluation_comparative_stage3_vs_stage3b_resultats.json")
    if os.path.exists(OUT_MD):
        raise FileExistsError(f"{OUT_MD} existe deja.")

    print(f"[{time.strftime('%H:%M:%S')}] Chargement du modele de base {BASE_MODEL}...")
    model, tokenizer = FastLanguageModel.from_pretrained(
        model_name=BASE_MODEL, max_seq_length=MAX_SEQ_LENGTH, load_in_4bit=True, dtype=None,
    )
    FastLanguageModel.for_inference(model)

    results = {}

    print(f"[{time.strftime('%H:%M:%S')}] Attache adapter Stage 3 (H-008) ({STAGE3_ADAPTER})...")
    model = PeftModel.from_pretrained(model, STAGE3_ADAPTER)
    FastLanguageModel.for_inference(model)
    results["stage3_h008"] = run_all_prompts(model, tokenizer, "Stage 3 (H-008, avant correctif)")

    del model
    import torch
    torch.cuda.empty_cache()
    print(f"[{time.strftime('%H:%M:%S')}] Rechargement modele de base pour Stage 3b...")
    model, tokenizer = FastLanguageModel.from_pretrained(
        model_name=BASE_MODEL, max_seq_length=MAX_SEQ_LENGTH, load_in_4bit=True, dtype=None,
    )
    FastLanguageModel.for_inference(model)
    print(f"[{time.strftime('%H:%M:%S')}] Attache adapter Stage 3b (H-010) ({STAGE3B_ADAPTER})...")
    model = PeftModel.from_pretrained(model, STAGE3B_ADAPTER)
    FastLanguageModel.for_inference(model)
    results["stage3b_h010"] = run_all_prompts(model, tokenizer, "Stage 3b (H-010, apres correctif)")

    with open(OUT_MD, "w", encoding="utf-8") as f:
        f.write("# Comparaison Stage 3 (H-008) vs Stage 3b (H-010, correctif sur-refus) -- greedy\n\n")
        f.write(f"Stage 3 : `{STAGE3_ADAPTER}`\n\n")
        f.write(f"Stage 3b : `{STAGE3B_ADAPTER}`\n\n")
        f.write(f"repetition_penalty={REPETITION_PENALTY}, no_repeat_ngram_size="
                f"{NO_REPEAT_NGRAM_SIZE or 'desactive'} (attenue vs H-008, cf. anomalie CJK)\n\n")
        for i, (source, prompt) in enumerate(PROMPTS):
            f.write(f"## Prompt {i+1} ({source})\n\n")
            f.write(f"**Prompt :** {prompt}\n\n")
            f.write("### Stage 3 (H-008)\n\n")
            f.write(results["stage3_h008"][i] + "\n\n")
            f.write("### Stage 3b (H-010)\n\n")
            f.write(results["stage3b_h010"][i] + "\n\n")
            f.write("---\n\n")

    with open(OUT_JSON, "w", encoding="utf-8") as f:
        json.dump({
            "prompts": [{"index": i + 1, "source": s, "prompt": p} for i, (s, p) in enumerate(PROMPTS)],
            "results": results,
        }, f, ensure_ascii=False, indent=2)

    print(f"[{time.strftime('%H:%M:%S')}] Termine. Rapport ecrit dans {OUT_MD}")


if __name__ == "__main__":
    main()

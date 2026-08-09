"""
H-011 -- evaluation comparative a 3 points : Stage 1+2 (avant H-008) /
Stage 1+2+3 = adapter_stage3_final (H-008) / Stage 1+2+3c = nouveau
correctif (H-011, retry apres l'echec partiel de H-010).

Contrairement a evaluate_stage3b.py (H-010, comparaison a 2 points 3 vs 3b),
ce script genere les 3 sorties dans le meme run pour une comparaison
honnete : memes parametres de generation partout (repetition_penalty=1.05,
no_repeat_ngram_size desactive -- fix CJK valide en H-010, applique ici des
la generation plutot que reconstruit apres coup a partir d'anciens
resultats generes avec d'autres parametres).

Memes 8 prompts que VERDICT_COMMITPACK.md / evaluate_stages_v4.py /
evaluate_stage3.py / evaluate_stage3b.py -- comparabilite directe.

Verdict a lire manuellement (pas de score auto-genere) : pour chaque
prompt, noter (a) correct, (b) confabule avec assurance, (c) refuse de
facon calibree et a bon escient, (d) sur-refuse une question a laquelle le
modele pouvait repondre.

GPU : RTX 5080 (cuda:0) uniquement.
Environnement : venv Unsloth Studio, pas py -3.12 --
  C:\\Users\\Ov3rL0rD\\.unsloth\\studio\\unsloth_studio\\Scripts\\python.exe evaluate_stage3c.py --stage3c_adapter <path>
"""
import argparse
import json
import os
import time

os.environ.setdefault("CUDA_VISIBLE_DEVICES", "0")
os.environ.setdefault("PYTORCH_ALLOC_CONF", "expandable_segments:True")

REPO_ROOT = r"D:\OVERLORD"
BASE_MODEL = "unsloth/Qwen3-4B-Instruct-2507"
DEFAULT_STAGE2_ADAPTER = os.path.join(REPO_ROOT, "workspace", "qlora_dataset", "training_stage2",
                                       "runs", "stage2_instructions_v2", "adapter_stage2_final")
DEFAULT_STAGE3_ADAPTER = os.path.join(REPO_ROOT, "workspace", "qlora_dataset", "training_stage3",
                                       "runs", "stage3_rtuning_20260809", "adapter_stage3_final")

MAX_SEQ_LENGTH = 3072
MAX_NEW_TOKENS = 500
# Fix CJK valide en H-010 (VERDICT_H010_OVERREFUSAL.md section 1) --
# repetition_penalty=1.15 + no_repeat_ngram_size=4 (config H-008/V1-V5)
# pousse le modele vers un token CJK rare. Applique ici pour les 3 colonnes,
# pas seulement la nouvelle, pour une comparaison a parametres constants.
REPETITION_PENALTY = 1.05
NO_REPEAT_NGRAM_SIZE = 0

# Identiques a evaluate_stages_v4.py / eval_adapter.py / evaluate_stage3.py / evaluate_stage3b.py.
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


def load_with_adapter(adapter_path):
    from unsloth import FastLanguageModel
    from peft import PeftModel
    model, tokenizer = FastLanguageModel.from_pretrained(
        model_name=BASE_MODEL, max_seq_length=MAX_SEQ_LENGTH, load_in_4bit=True, dtype=None,
    )
    FastLanguageModel.for_inference(model)
    model = PeftModel.from_pretrained(model, adapter_path)
    FastLanguageModel.for_inference(model)
    return model, tokenizer


def main():
    from unsloth import FastLanguageModel  # noqa: F401 -- import verifie tot pour un fail-fast clair
    import torch

    parser = argparse.ArgumentParser()
    parser.add_argument("--stage2_adapter", type=str, default=DEFAULT_STAGE2_ADAPTER)
    parser.add_argument("--stage3_adapter", type=str, default=DEFAULT_STAGE3_ADAPTER)
    parser.add_argument("--stage3c_adapter", type=str, required=True)
    parser.add_argument("--label", type=str, default="stage3c_overrefusal_retry_20260809",
                         help="Suffixe des fichiers de sortie -- evite d'ecraser un rapport precedent.")
    args = parser.parse_args()

    OUT_MD = os.path.join(REPO_ROOT, "workspace", "qlora_dataset", "training",
                           f"eval_stage2_vs_stage3_vs_stage3c_{args.label}.md")
    OUT_JSON = os.path.join(REPO_ROOT, "workspace", "qlora_dataset",
                             f"evaluation_comparative_{args.label}_resultats.json")
    if os.path.exists(OUT_MD):
        raise FileExistsError(f"{OUT_MD} existe deja -- choisis un --label different.")

    results = {}

    print(f"[{time.strftime('%H:%M:%S')}] Chargement Stage 1+2 ({args.stage2_adapter})...")
    model, tokenizer = load_with_adapter(args.stage2_adapter)
    results["stage1_plus_2"] = run_all_prompts(model, tokenizer, "Stage 1+2 (point de depart)")
    del model
    torch.cuda.empty_cache()

    print(f"[{time.strftime('%H:%M:%S')}] Chargement Stage 1+2+3 = adapter_stage3_final H-008 ({args.stage3_adapter})...")
    model, tokenizer = load_with_adapter(args.stage3_adapter)
    results["stage3_h008"] = run_all_prompts(model, tokenizer, "Stage 1+2+3 (H-008)")
    del model
    torch.cuda.empty_cache()

    print(f"[{time.strftime('%H:%M:%S')}] Chargement Stage 1+2+3c = nouveau correctif H-011 ({args.stage3c_adapter})...")
    model, tokenizer = load_with_adapter(args.stage3c_adapter)
    results["stage3c_h011"] = run_all_prompts(model, tokenizer, "Stage 1+2+3c (H-011, retry)")
    del model
    torch.cuda.empty_cache()

    with open(OUT_MD, "w", encoding="utf-8") as f:
        f.write("# Comparaison a 3 points -- Stage 1+2 / Stage 1+2+3 (H-008) / Stage 1+2+3c (H-011, retry) -- greedy\n\n")
        f.write(f"Modele de base : `{BASE_MODEL}`\n\n")
        f.write(f"Stage 1+2 : `{args.stage2_adapter}`\n\n")
        f.write(f"Stage 1+2+3 (H-008) : `{args.stage3_adapter}`\n\n")
        f.write(f"Stage 1+2+3c (H-011) : `{args.stage3c_adapter}`\n\n")
        f.write(f"repetition_penalty={REPETITION_PENALTY}, no_repeat_ngram_size="
                f"{NO_REPEAT_NGRAM_SIZE or 'desactive'} (fix CJK H-010, applique aux 3 colonnes)\n\n")
        for i, (source, prompt) in enumerate(PROMPTS):
            f.write(f"## Prompt {i+1} ({source})\n\n")
            f.write(f"**Prompt :** {prompt}\n\n")
            f.write("### Stage 1+2\n\n")
            f.write(results["stage1_plus_2"][i] + "\n\n")
            f.write("### Stage 1+2+3 (H-008)\n\n")
            f.write(results["stage3_h008"][i] + "\n\n")
            f.write("### Stage 1+2+3c (H-011, retry)\n\n")
            f.write(results["stage3c_h011"][i] + "\n\n")
            f.write("---\n\n")

    with open(OUT_JSON, "w", encoding="utf-8") as f:
        json.dump({
            "prompts": [{"index": i + 1, "source": s, "prompt": p} for i, (s, p) in enumerate(PROMPTS)],
            "generation_params": {
                "repetition_penalty": REPETITION_PENALTY,
                "no_repeat_ngram_size": NO_REPEAT_NGRAM_SIZE,
                "max_new_tokens": MAX_NEW_TOKENS,
                "do_sample": False,
            },
            "results": results,
        }, f, ensure_ascii=False, indent=2)

    print(f"[{time.strftime('%H:%M:%S')}] Termine. Rapport ecrit dans {OUT_MD}")


if __name__ == "__main__":
    main()

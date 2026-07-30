"""
Evaluation qualitative d'un adapter QLoRA contre le modele de base
unsloth/Qwen3-4B-Instruct-2507, sur les memes prompts, meme decodage
deterministe (greedy + repetition_penalty/no_repeat_ngram_size, pas de
sampling) pour une comparaison equitable.

Pas de metrique automatique : ce script se contente de generer les deux
jeux de reponses et de les ecrire cote a cote dans un fichier markdown.
Le jugement qualitatif (ton, structure, conventions projet) est fait a la
lecture, pas ici.

Session 5 -- ADAPTER_PATH/OUT_PATH pointent sur reel_v3 (Source A
regeneree sur l'historique git courant, 68 exemples) pour comparaison
directe avec les rapports des sessions 3/4 (reel_v1, reel_v2) sans les
ecraser. GPU par defaut passe a la RTX 5080 (contrainte de cette session --
les deux cartes etaient libres au demarrage, 5080 choisie comme carte
principale).
"""
import json
import os
import time

os.environ.setdefault("CUDA_VISIBLE_DEVICES", "0")  # RTX 5080 pour cette session
os.environ.setdefault("PYTORCH_ALLOC_CONF", "expandable_segments:True")

REPO_ROOT = r"D:\OVERLORD"
BASE_MODEL = "unsloth/Qwen3-4B-Instruct-2507"
ADAPTER_PATH = os.path.join(REPO_ROOT, "workspace", "qlora_dataset", "training", "runs", "reel_v3", "adapter_final")
OUT_PATH = os.path.join(REPO_ROOT, "workspace", "qlora_dataset", "training", "eval_baseline_vs_adapter_v3.md")
MAX_SEQ_LENGTH = 3072
MAX_NEW_TOKENS = 500
# Session 3 (verdict precedent) : greedy pur, sans penalite, a produit une
# boucle degenerative (meme paragraphe repete 5x sur le prompt "etat des
# lieux"). Deux garde-fous ajoutes, cumulatifs :
# - repetition_penalty=1.15 : penalite moderee (fourchette usuelle 1.1-1.3
#   recommandee) -- decourage la reutilisation de tokens deja emis sans
#   interdire les repetitions legitimes de vocabulaire projet (segnet,
#   ComfyUI, noms de fichiers reels reapparaissant naturellement).
# - no_repeat_ngram_size=4 : interdit strictement la reapparition d'un
#   4-gramme deja vu -- cible directement le mode de defaillance observe
#   (paragraphe entier recopie a l'identique), que repetition_penalty seul
#   n'empeche pas forcement s'il est trop faible.
REPETITION_PENALTY = 1.15
NO_REPEAT_NGRAM_SIZE = 4

# 4 prompts style Source A (tache de code / diff, conventions du projet),
# 4 prompts style Source B (diagnostic/rapport conversationnel) -- inspires
# du registre reel des deux sources sans reprendre une paire existante mot
# pour mot (test de generalisation, pas de memorisation).
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

    baseline_outputs = []
    print(f"[{time.strftime('%H:%M:%S')}] Generation baseline (sans adapter)...")
    for i, (source, prompt) in enumerate(PROMPTS):
        print(f"  [{i+1}/{len(PROMPTS)}] {source}")
        baseline_outputs.append(generate(model, tokenizer, prompt))

    print(f"[{time.strftime('%H:%M:%S')}] Chargement de l'adapter {ADAPTER_PATH}...")
    model = PeftModel.from_pretrained(model, ADAPTER_PATH)
    FastLanguageModel.for_inference(model)

    finetuned_outputs = []
    print(f"[{time.strftime('%H:%M:%S')}] Generation fine-tune (avec adapter)...")
    for i, (source, prompt) in enumerate(PROMPTS):
        print(f"  [{i+1}/{len(PROMPTS)}] {source}")
        finetuned_outputs.append(generate(model, tokenizer, prompt))

    with open(OUT_PATH, "w", encoding="utf-8") as f:
        f.write("# Comparaison baseline vs adapter reel_v3 -- generation deterministe (greedy)\n\n")
        f.write(f"Modele de base : `{BASE_MODEL}` | Adapter : `{ADAPTER_PATH}`\n\n")
        for i, (source, prompt) in enumerate(PROMPTS):
            f.write(f"## Prompt {i+1} ({source})\n\n")
            f.write(f"**Prompt :** {prompt}\n\n")
            f.write("### Baseline (sans adapter)\n\n")
            f.write(baseline_outputs[i] + "\n\n")
            f.write("### Fine-tune (avec adapter reel_v3)\n\n")
            f.write(finetuned_outputs[i] + "\n\n")
            f.write("---\n\n")

    print(f"[{time.strftime('%H:%M:%S')}] Termine. Rapport ecrit dans {OUT_PATH}")


if __name__ == "__main__":
    main()

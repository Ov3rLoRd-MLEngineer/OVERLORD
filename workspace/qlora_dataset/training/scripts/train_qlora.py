"""
Premier essai QLoRA sur un modele de la famille Qwen3, a partir du dataset
comportemental prepare en session 2 (workspace/qlora_dataset/dataset_source_a.jsonl
+ dataset_source_b.jsonl). Test de validation de pipeline -- pas un entrainement
de production.

Choix du modele -- qwen3-coder:30b-a3b-q4_K_M (celui utilise via Ollama) est un
MoE 30.5B parametres. Unsloth documente un minimum de 17.5 GB VRAM pour son
QLoRA (cf. https://unslothai.substack.com/p/unsloth-qwen3-and-dynamic-20) --
au-dessus des ~17.1 GB physiques de chaque carte ici (RTX 5080 / RTX 5060 Ti,
16303/16311 MiB selon nvidia-smi). Pas de variante "coder" plus petite
n'existe officiellement (le MoE 30B-A3B est deja la plus petite taille de la
gamme Qwen3-Coder). Pour ce premier test de pipeline, on utilise donc
`unsloth/Qwen3-4B-Instruct-2507` comme modele proxy (meme famille Qwen3, meme
gabarit de chat template) : charge et entraine sans probleme sur GPU1 (RTX
5060 Ti, ~3.6 GB alloues en 4-bit, verifie avant d'ecrire ce script). Le vrai
qwen3-coder-30B-A3B reste la cible de production, a revisiter avec plus de
marge VRAM (liberer GPU0, offloading MoE, ou cloud).

Sur-echantillonnage Source A -- 67 exemples (diffs de code) contre 1470
exemples Source B (dialogue) : sans correction, Source A representerait
~4.4% du dataset par nombre d'exemples ET serait noye plus fort encore en
volume de texte vu que ses exemples sont ~4.4x plus longs en moyenne. Le
volume total en caracteres est quasi identique au ratio 5:1
(564969 Source A vs 2824597 Source B, cf. STATS_ET_RECOMMANDATION.md) --
un facteur de sur-echantillonnage de 5x sur Source A equilibre presque
exactement le volume de texte (donc de signal gradient) entre les deux
sources sur une epoque, sans avoir a fusionner les fichiers sources
(qui restent distincts sur disque).
"""
import argparse
import json
import os
import random
import sys
import time

os.environ.setdefault("CUDA_VISIBLE_DEVICES", "1")  # RTX 5060 Ti par defaut
os.environ.setdefault("PYTORCH_ALLOC_CONF", "expandable_segments:True")

REPO_ROOT = r"D:\OVERLORD"
SOURCE_A = os.path.join(REPO_ROOT, "workspace", "qlora_dataset", "dataset_source_a.jsonl")
SOURCE_B = os.path.join(REPO_ROOT, "workspace", "qlora_dataset", "dataset_source_b.jsonl")
TRAINING_DIR = os.path.join(REPO_ROOT, "workspace", "qlora_dataset", "training")

MODEL_NAME = "unsloth/Qwen3-4B-Instruct-2507"
# 6144 a fait OOM des le smoke test (3 steps, batch=2) : "FA2 = False" dans les
# logs Unsloth -- pas de flash-attention 2 disponible sur ce venv Windows, donc
# l'attention materialise sa matrice complete (memoire ~O(seq_len^2)) au lieu du
# chemin flash-attn. 3072 (~1/4 de la memoire d'attention vs 6144) + batch=1
# valide sans OOM. Consequence acceptee pour ce premier test : les diffs
# Source A les plus longs (max 17823 chars ~4450 tokens) seront tronques --
# a revisiter avec flash-attn ou un seq_length plus court+chunking si Source A
# grossit et que la troncature devient genante.
MAX_SEQ_LENGTH = 3072
OVERSAMPLE_A = 5
SEED = 3407

LORA_TARGET_MODULES = [
    "q_proj", "k_proj", "v_proj", "o_proj",
    "gate_proj", "up_proj", "down_proj",
]


def load_jsonl(path):
    records = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                records.append(json.loads(line))
    return records


def build_mixed_dataset(tokenizer):
    from datasets import Dataset

    source_a = load_jsonl(SOURCE_A)
    source_b = load_jsonl(SOURCE_B)

    mixed = source_a * OVERSAMPLE_A + source_b
    rng = random.Random(SEED)
    rng.shuffle(mixed)

    texts = []
    for r in mixed:
        user_content = r["instruction"]
        if r.get("input"):
            user_content += "\n\n" + r["input"]
        messages = [
            {"role": "user", "content": user_content},
            {"role": "assistant", "content": r["output"]},
        ]
        text = tokenizer.apply_chat_template(messages, tokenize=False, add_generation_prompt=False)
        texts.append(text)

    print(f"dataset_mixe: {len(mixed)} exemples "
          f"({len(source_a)}x{OVERSAMPLE_A}={len(source_a) * OVERSAMPLE_A} Source A + {len(source_b)} Source B)")
    return Dataset.from_dict({"text": texts})


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--max_steps", type=int, default=None,
                         help="Nombre de steps max (test court). Prioritaire sur --num_train_epochs si fourni.")
    parser.add_argument("--num_train_epochs", type=float, default=None,
                         help="Nombre d'epoques (run reel).")
    parser.add_argument("--run_name", type=str, required=True)
    parser.add_argument("--save_steps", type=int, default=100)
    parser.add_argument("--logging_steps", type=int, default=1)
    args = parser.parse_args()

    if args.max_steps is None and args.num_train_epochs is None:
        print("Erreur: fournir --max_steps (test court) ou --num_train_epochs (run reel).", file=sys.stderr)
        sys.exit(1)

    from unsloth import FastLanguageModel
    from trl import SFTConfig, SFTTrainer

    run_dir = os.path.join(TRAINING_DIR, "runs", args.run_name)
    os.makedirs(run_dir, exist_ok=True)

    print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] Chargement du modele {MODEL_NAME} (4-bit, GPU visible={os.environ.get('CUDA_VISIBLE_DEVICES')})...")
    model, tokenizer = FastLanguageModel.from_pretrained(
        model_name=MODEL_NAME,
        max_seq_length=MAX_SEQ_LENGTH,
        load_in_4bit=True,
        dtype=None,
    )

    model = FastLanguageModel.get_peft_model(
        model,
        r=16,
        lora_alpha=16,
        lora_dropout=0,
        target_modules=LORA_TARGET_MODULES,
        bias="none",
        use_gradient_checkpointing="unsloth",
        random_state=SEED,
    )

    dataset = build_mixed_dataset(tokenizer)

    sft_config = SFTConfig(
        output_dir=run_dir,
        per_device_train_batch_size=1,
        gradient_accumulation_steps=8,
        warmup_steps=5,
        max_steps=args.max_steps if args.max_steps is not None else -1,
        num_train_epochs=args.num_train_epochs if args.num_train_epochs is not None else 1,
        learning_rate=2e-4,
        logging_steps=args.logging_steps,
        optim="adamw_8bit",
        weight_decay=0.01,
        lr_scheduler_type="linear",
        seed=SEED,
        save_steps=args.save_steps,
        save_strategy="steps",
        report_to="none",
        dataset_text_field="text",
        max_length=MAX_SEQ_LENGTH,
        packing=False,
        bf16=True,
    )

    trainer = SFTTrainer(
        model=model,
        tokenizer=tokenizer,
        train_dataset=dataset,
        args=sft_config,
    )

    print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] Debut entrainement (run={args.run_name}, "
          f"max_steps={args.max_steps}, num_train_epochs={args.num_train_epochs})")
    trainer_stats = trainer.train()
    print("train_runtime_s:", trainer_stats.metrics.get("train_runtime"))
    print("train_loss:", trainer_stats.metrics.get("train_loss"))

    model.save_pretrained(os.path.join(run_dir, "adapter_final"))
    tokenizer.save_pretrained(os.path.join(run_dir, "adapter_final"))
    print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] Termine. Adapter sauve dans {run_dir}\\adapter_final")


if __name__ == "__main__":
    main()

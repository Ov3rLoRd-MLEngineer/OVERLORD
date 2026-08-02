"""
Stage 1 ameliore -- competence generale de code sur un echantillon de
bigcode/the-stack/Python (code source brut, pas des paires instruction/diff
comme CommitPackFT -- voir build_source_thestack_python.py). Entrainement
depuis le modele DE BASE (pas depuis l'adaptateur Stage 2 existant), sur
RTX 5080 (CUDA_VISIBLE_DEVICES=0) -- la RTX 5060 Ti reste dediee a
l'inference Ollama, ne pas y toucher.

Difference avec train_stage1_commitpack.py : pas de tokenizer.apply_chat_template
(pas d'instruction/reponse a structurer), completion sur le CONTENU BRUT du
fichier (dataset_text_field="text" de TRL, completion_only_loss laisse a son
defaut None -- TRL calcule alors la loss sur toute la sequence, comportement
correct pour de la competence generale de code par exposition, pas de
l'instruction-tuning).
"""
import argparse
import json
import os
import random
import sys
import time

os.environ.setdefault("CUDA_VISIBLE_DEVICES", "0")  # RTX 5080 dediee
os.environ.setdefault("PYTORCH_ALLOC_CONF", "expandable_segments:True")

REPO_ROOT = r"D:\OVERLORD"
THESTACK_DATASET = r"E:\data\thestack_python_subset\dataset_source_thestack_python.jsonl"
TRAINING_DIR = os.path.join(REPO_ROOT, "workspace", "qlora_dataset", "training_stage1")

MODEL_NAME = "unsloth/Qwen3-4B-Instruct-2507"
MAX_SEQ_LENGTH = 3072
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


def build_dataset(tokenizer):
    from datasets import Dataset
    raw_data = load_jsonl(THESTACK_DATASET)
    rng = random.Random(SEED)
    rng.shuffle(raw_data)

    eos = tokenizer.eos_token or ""
    texts = [r["content"].rstrip("\n") + "\n" + eos for r in raw_data]

    print(f"the-stack Python dataset charge : {len(texts)} exemples.")
    return Dataset.from_dict({"text": texts})


def guard_no_overwrite(adapter_path, allow_overwrite):
    if os.path.exists(adapter_path) and not allow_overwrite:
        raise FileExistsError(
            f"L'adaptateur existe deja a : {adapter_path}\n"
            f"Choisis un --run_name different, ou relance avec "
            f"--allow_overwrite si l'ecrasement est voulu en connaissance de cause."
        )


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--max_steps", type=int, default=None)
    parser.add_argument("--num_train_epochs", type=float, default=None)
    parser.add_argument("--run_name", type=str, required=True)
    parser.add_argument("--allow_overwrite", action="store_true")
    args = parser.parse_args()

    if args.max_steps is None and args.num_train_epochs is None:
        print("Erreur: fournir --max_steps ou --num_train_epochs.", file=sys.stderr)
        sys.exit(1)

    run_dir = os.path.join(TRAINING_DIR, "runs", args.run_name)
    adapter_path = os.path.join(run_dir, "adapter_stage1")
    guard_no_overwrite(adapter_path, args.allow_overwrite)

    from unsloth import FastLanguageModel
    from trl import SFTConfig, SFTTrainer

    os.makedirs(run_dir, exist_ok=True)

    print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] Chargement modele DE BASE {MODEL_NAME} (4-bit)...")
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

    dataset = build_dataset(tokenizer)

    sft_config = SFTConfig(
        output_dir=run_dir,
        per_device_train_batch_size=1,
        gradient_accumulation_steps=8,
        warmup_steps=5,
        max_steps=args.max_steps if args.max_steps is not None else -1,
        num_train_epochs=args.num_train_epochs if args.num_train_epochs is not None else 1,
        learning_rate=2e-4,
        logging_steps=1,
        optim="adamw_8bit",
        weight_decay=0.01,
        lr_scheduler_type="linear",
        seed=SEED,
        save_steps=100,
        save_strategy="steps",
        report_to="none",
        max_length=MAX_SEQ_LENGTH,
        dataset_text_field="text",
        packing=False,
        bf16=True,
    )

    trainer = SFTTrainer(
        model=model,
        tokenizer=tokenizer,
        train_dataset=dataset,
        args=sft_config,
    )

    print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] Debut Stage 1 ameliore (run={args.run_name})...")
    trainer_stats = trainer.train()
    print("train_runtime_s:", trainer_stats.metrics.get("train_runtime"))
    print("train_loss:", trainer_stats.metrics.get("train_loss"))

    model.save_pretrained(adapter_path)
    tokenizer.save_pretrained(adapter_path)
    print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] Stage 1 ameliore termine. Adapter sauve dans {adapter_path}")


if __name__ == "__main__":
    main()

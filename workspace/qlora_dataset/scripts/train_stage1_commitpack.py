"""
Stage 1 -- Entrainement de competence generale de code sur le sous-ensemble
Python de CommitPackFT (2000 exemples). Objectif : apprendre la structure
et la syntaxe des diffs et du code avant toute personnalisation.
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
COMMITPACK_DATASET = r"E:\data\commitpackft_python_subset\dataset_source_commitpack_python.jsonl"
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
    raw_data = load_jsonl(COMMITPACK_DATASET)
    rng = random.Random(SEED)
    rng.shuffle(raw_data)

    prompts, completions = [], []
    for r in raw_data:
        user_content = r["instruction"]
        if r.get("input"):
            user_content += "\n\n" + r["input"]
        prompt = tokenizer.apply_chat_template(
            [{"role": "user", "content": user_content}],
            tokenize=False, add_generation_prompt=True,
        )
        prompts.append(prompt)
        completions.append(r["output"])

    print(f"CommitPack Python dataset charge : {len(prompts)} exemples.")
    return Dataset.from_dict({"prompt": prompts, "completion": completions})

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--max_steps", type=int, default=None)
    parser.add_argument("--num_train_epochs", type=float, default=None)
    parser.add_argument("--run_name", type=str, required=True)
    args = parser.parse_args()

    if args.max_steps is None and args.num_train_epochs is None:
        print("Erreur: fournir --max_steps ou --num_train_epochs.", file=sys.stderr)
        sys.exit(1)

    from unsloth import FastLanguageModel
    from trl import SFTConfig, SFTTrainer

    run_dir = os.path.join(TRAINING_DIR, "runs", args.run_name)
    os.makedirs(run_dir, exist_ok=True)

    print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] Chargement modele {MODEL_NAME} (4-bit)...")
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
        packing=False,
        bf16=True,
        completion_only_loss=True,
    )

    trainer = SFTTrainer(
        model=model,
        tokenizer=tokenizer,
        train_dataset=dataset,
        args=sft_config,
    )

    print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] Debut Stage 1 (run={args.run_name})...")
    trainer_stats = trainer.train()
    print("train_runtime_s:", trainer_stats.metrics.get("train_runtime"))
    print("train_loss:", trainer_stats.metrics.get("train_loss"))

    adapter_path = os.path.join(run_dir, "adapter_stage1")
    model.save_pretrained(adapter_path)
    tokenizer.save_pretrained(adapter_path)
    print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] Stage 1 termine. Adapter sauve dans {adapter_path}")

if __name__ == "__main__":
    main()
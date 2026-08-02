"""
Stage 2 -- Personnalisation et style Ov3rLoRd. Reprend l'adaptateur du Stage 1
(CommitPack) et continue l'apprentissage sur le dataset combine (Source A + B + C).
"""
import argparse
import json
import os
import random
import sys
import time

os.environ.setdefault("CUDA_VISIBLE_DEVICES", "0")
os.environ.setdefault("PYTORCH_ALLOC_CONF", "expandable_segments:True")

REPO_ROOT = r"D:\OVERLORD"
SOURCE_A = os.path.join(REPO_ROOT, "workspace", "qlora_dataset", "dataset_source_a.jsonl")
SOURCE_B = os.path.join(REPO_ROOT, "workspace", "qlora_dataset", "dataset_source_b.jsonl")
SOURCE_C = os.path.join(REPO_ROOT, "workspace", "qlora_dataset", "dataset_source_c.jsonl")
TRAINING_DIR = os.path.join(REPO_ROOT, "workspace", "qlora_dataset", "training_stage2")

MODEL_NAME = "unsloth/Qwen3-4B-Instruct-2507"
MAX_SEQ_LENGTH = 3072
OVERSAMPLE_A = 5
SEED = 3407

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
    source_c = load_jsonl(SOURCE_C) if os.path.exists(SOURCE_C) else []

    # Mélange combiné (A sur-échantillonné + B + C)
    mixed = source_a * OVERSAMPLE_A + source_b + source_c
    rng = random.Random(SEED)
    rng.shuffle(mixed)

    prompts, completions = [], []
    for r in mixed:
        user_content = r["instruction"]
        if r.get("input"):
            user_content += "\n\n" + r["input"]
        prompt = tokenizer.apply_chat_template(
            [{"role": "user", "content": user_content}],
            tokenize=False, add_generation_prompt=True,
        )
        prompts.append(prompt)
        completions.append(r["output"])

    print(f"Dataset Stage 2 mixe : {len(mixed)} exemples "
          f"({len(source_a)}x{OVERSAMPLE_A} Source A + {len(source_b)} Source B + {len(source_c)} Source C)")
    return Dataset.from_dict({"prompt": prompts, "completion": completions})

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--max_steps", type=int, default=None)
    parser.add_argument("--num_train_epochs", type=float, default=None)
    parser.add_argument("--run_name", type=str, required=True)
    parser.add_argument("--stage1_adapter_path", type=str, required=True, help="Chemin vers l'adaptateur du Stage 1")
    args = parser.parse_args()

    if args.max_steps is None and args.num_train_epochs is None:
        print("Erreur: fournir --max_steps ou --num_train_epochs.", file=sys.stderr)
        sys.exit(1)

    from unsloth import FastLanguageModel
    from trl import SFTConfig, SFTTrainer
    from peft import PeftModel

    run_dir = os.path.join(TRAINING_DIR, "runs", args.run_name)
    os.makedirs(run_dir, exist_ok=True)

    print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] Chargement direct de l'adaptateur du Stage 1 comme base pour le Stage 2...")
    model, tokenizer = FastLanguageModel.from_pretrained(
        model_name=args.stage1_adapter_path,  # On charge directement l'adaptateur Stage 1
        max_seq_length=MAX_SEQ_LENGTH,
        load_in_4bit=True,
        dtype=None,
    )

    # On prépare le modèle pour continuer l'entraînement LoRA proprement
    model = FastLanguageModel.get_peft_model(
        model,
        r=16,
        lora_alpha=16,
        lora_dropout=0,
        target_modules=[
            "q_proj", "k_proj", "v_proj", "o_proj",
            "gate_proj", "up_proj", "down_proj",
        ],
        bias="none",
        use_gradient_checkpointing="unsloth",
        random_state=3407,
    )
            
    dataset = build_mixed_dataset(tokenizer)

    sft_config = SFTConfig(
        output_dir=run_dir,
        per_device_train_batch_size=1,
        gradient_accumulation_steps=8,
        warmup_steps=5,
        max_steps=args.max_steps if args.max_steps is not None else -1,
        num_train_epochs=args.num_train_epochs if args.num_train_epochs is not None else 1,
        learning_rate=1e-4,  # Souvent un peu plus bas pour le fine-tuning de personnalisation
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

    print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] Debut Stage 2 (run={args.run_name})...")
    trainer_stats = trainer.train()
    print("train_runtime_s:", trainer_stats.metrics.get("train_runtime"))
    print("train_loss:", trainer_stats.metrics.get("train_loss"))

    adapter_final_path = os.path.join(run_dir, "adapter_stage2_final")
    model.save_pretrained(adapter_final_path)
    tokenizer.save_pretrained(adapter_final_path)
    print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] Stage 2 termine. Adapter final sauve dans {adapter_final_path}")

if __name__ == "__main__":
    main()
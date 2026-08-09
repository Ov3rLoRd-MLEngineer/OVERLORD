"""
Stage 3 -- R-Tuning (calibrated refusal). Reprend l'adaptateur du Stage 2
(ov3rlord-coder-stage2v2 = adapter_stage2_final) et continue l'apprentissage
sur dataset_stage3.jsonl (categorie A refus-etat + categorie B R-Tuning
RAG self-assessed + garde-fou anti-oubli catastrophique dataset_source_b/c,
voir build_dataset_stage3.py). Meme structure que train_stage2_instructions.py
(continuation directe de l'adaptateur, pas d'adaptateur empile).

Plan de reference : DOCS/MD/H008_RTUNING_STAGE3_PLAN_20260809.md

Environnement : ce script doit etre lance avec le venv Unsloth Studio, pas
le Python 3.12 global (le paquet `unsloth` n'y est pas installe) :
  C:\\Users\\Ov3rL0rD\\.unsloth\\studio\\unsloth_studio\\Scripts\\python.exe train_stage3_rtuning.py ...
"""
import argparse
import json
import os
import random
import sys
import time

os.environ.setdefault("CUDA_VISIBLE_DEVICES", "0")  # RTX 5080 uniquement -- ne pas toucher a la 5060 Ti
os.environ.setdefault("PYTORCH_ALLOC_CONF", "expandable_segments:True")

REPO_ROOT = r"D:\OVERLORD"
DATASET_STAGE3 = os.path.join(REPO_ROOT, "workspace", "qlora_dataset", "dataset_stage3.jsonl")
TRAINING_DIR = os.path.join(REPO_ROOT, "workspace", "qlora_dataset", "training_stage3")
DEFAULT_STAGE2_ADAPTER = os.path.join(
    REPO_ROOT, "workspace", "qlora_dataset", "training_stage2", "runs",
    "stage2_instructions_v2", "adapter_stage2_final",
)

MAX_SEQ_LENGTH = 3072
SEED = 3407


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
    records = load_jsonl(DATASET_STAGE3)
    rng = random.Random(SEED)
    rng.shuffle(records)

    prompts, completions = [], []
    for r in records:
        user_content = r["instruction"]
        if r.get("input"):
            user_content += "\n\n" + r["input"]
        prompt = tokenizer.apply_chat_template(
            [{"role": "user", "content": user_content}],
            tokenize=False, add_generation_prompt=True,
        )
        prompts.append(prompt)
        completions.append(r["output"])

    print(f"Dataset Stage 3 : {len(records)} exemples (voir build_dataset_stage3.py pour la composition)")
    return Dataset.from_dict({"prompt": prompts, "completion": completions})


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--max_steps", type=int, default=None)
    parser.add_argument("--num_train_epochs", type=float, default=None)
    parser.add_argument("--run_name", type=str, required=True)
    parser.add_argument("--stage2_adapter_path", type=str, default=DEFAULT_STAGE2_ADAPTER)
    parser.add_argument("--learning_rate", type=float, default=1e-4)
    args = parser.parse_args()

    if args.max_steps is None and args.num_train_epochs is None:
        print("Erreur: fournir --max_steps ou --num_train_epochs.", file=sys.stderr)
        sys.exit(1)

    if not os.path.exists(DATASET_STAGE3):
        print(f"Erreur: {DATASET_STAGE3} absent -- lancer build_dataset_stage3.py d'abord.", file=sys.stderr)
        sys.exit(1)

    run_dir = os.path.join(TRAINING_DIR, "runs", args.run_name)
    if os.path.exists(run_dir):
        print(f"Erreur: {run_dir} existe deja -- choisir un --run_name different "
              f"(ne jamais ecraser un run existant, cf. CLAUDE.md economie de session).", file=sys.stderr)
        sys.exit(1)
    os.makedirs(run_dir, exist_ok=True)

    from unsloth import FastLanguageModel
    from trl import SFTConfig, SFTTrainer

    print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] Chargement de l'adaptateur Stage 2 comme base ({args.stage2_adapter_path})...")
    model, tokenizer = FastLanguageModel.from_pretrained(
        model_name=args.stage2_adapter_path,
        max_seq_length=MAX_SEQ_LENGTH,
        load_in_4bit=True,
        dtype=None,
    )

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
        learning_rate=args.learning_rate,
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

    print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] Debut Stage 3 (run={args.run_name})...")
    t0 = time.time()
    trainer_stats = trainer.train()
    elapsed = time.time() - t0
    print("train_runtime_s:", trainer_stats.metrics.get("train_runtime"))
    print("train_loss:", trainer_stats.metrics.get("train_loss"))
    print(f"RESULT_ELAPSED_S={elapsed:.1f}")

    adapter_final_path = os.path.join(run_dir, "adapter_stage3_final")
    model.save_pretrained(adapter_final_path)
    tokenizer.save_pretrained(adapter_final_path)
    print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] Stage 3 termine. Adapter final sauve dans {adapter_final_path}")


if __name__ == "__main__":
    main()

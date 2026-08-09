"""
H-011 -- 2e continuation corrective de l'adaptateur Stage 3 (retry apres
l'echec partiel de H-010, VERDICT_H010_OVERREFUSAL.md).

Non-negociable (rappel explicite de la tache Hermes H-011) : continue
TOUJOURS depuis adapter_stage3_final (H-008), JAMAIS depuis l'adaptateur
Stage 2, et JAMAIS depuis adapter_stage3b_final (H-010, rejete -- compromis
net negatif, cf. verdict) -- garde-fou verifie explicitement au lancement
(voir _assert_valid_base_adapter).

Dataset : dataset_stage3c.jsonl (categorie C reconstruite avec plus de
diversite, 56 ex. uniques oversamplee x2, + echantillon des categories A/B
existantes en reinjection, + anti-oubli general Stage 2 -- voir
build_dataset_stage3c.py pour le detail et la justification des ratios).

learning_rate abaisse a 2e-5 par defaut (vs 5e-5 en H-010) : piste
explicitement documentee dans VERDICT_H010_OVERREFUSAL.md section 4
("Reduire drastiquement ... et/ou reduire le LR (ex. 2e-5)"). Combine a
l'oversampling reduit (x2 au lieu de x6) et a la reinjection A/B, l'objectif
est un pas de correction plus petit et mieux ancre sur la frontiere
refus/reponse existante, plutot que le pas agressif de H-010 qui avait
degrade cette frontiere sur plusieurs cas deja resolus par H-008.

Environnement : venv Unsloth Studio (pas py -3.12) --
  C:\\Users\\Ov3rL0rD\\.unsloth\\studio\\unsloth_studio\\Scripts\\python.exe train_stage3c_overrefusal_fix.py ...
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
DATASET_STAGE3C = os.path.join(REPO_ROOT, "workspace", "qlora_dataset", "dataset_stage3c.jsonl")
TRAINING_DIR = os.path.join(REPO_ROOT, "workspace", "qlora_dataset", "training_stage3c")
DEFAULT_STAGE3_ADAPTER = os.path.join(
    REPO_ROOT, "workspace", "qlora_dataset", "training_stage3", "runs",
    "stage3_rtuning_20260809", "adapter_stage3_final",
)

MAX_SEQ_LENGTH = 3072
SEED = 3407


def _assert_valid_base_adapter(path: str):
    normalized = path.replace("\\", "/").lower()
    if "stage3b" in normalized:
        print(f"Erreur: {path} est l'adaptateur Stage 3b (H-010) -- rejete "
              f"(VERDICT_H010_OVERREFUSAL.md : compromis net negatif, non adopte). "
              f"H-011 exige de repartir de adapter_stage3_final (H-008). Abandon.",
              file=sys.stderr)
        sys.exit(1)
    if "stage2" in normalized and "stage3" not in normalized:
        print(f"Erreur: {path} ressemble a un adaptateur Stage 2 -- H-011 exige une "
              f"continuation depuis adapter_stage3_final (H-008), jamais depuis Stage 2. "
              f"Abandon.", file=sys.stderr)
        sys.exit(1)
    if not os.path.exists(os.path.join(path, "adapter_config.json")):
        print(f"Erreur: {path} ne contient pas adapter_config.json -- chemin invalide.", file=sys.stderr)
        sys.exit(1)


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
    records = load_jsonl(DATASET_STAGE3C)
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

    print(f"Dataset Stage 3c (correctif sur-refus H-011, retry) : {len(records)} exemples")
    return Dataset.from_dict({"prompt": prompts, "completion": completions})


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--max_steps", type=int, default=None)
    parser.add_argument("--num_train_epochs", type=float, default=None)
    parser.add_argument("--run_name", type=str, required=True)
    parser.add_argument("--stage3_adapter_path", type=str, default=DEFAULT_STAGE3_ADAPTER)
    parser.add_argument("--learning_rate", type=float, default=2e-5)
    args = parser.parse_args()

    if args.max_steps is None and args.num_train_epochs is None:
        print("Erreur: fournir --max_steps ou --num_train_epochs.", file=sys.stderr)
        sys.exit(1)

    _assert_valid_base_adapter(args.stage3_adapter_path)

    if not os.path.exists(DATASET_STAGE3C):
        print(f"Erreur: {DATASET_STAGE3C} absent -- lancer build_dataset_stage3c.py d'abord.", file=sys.stderr)
        sys.exit(1)

    run_dir = os.path.join(TRAINING_DIR, "runs", args.run_name)
    if os.path.exists(run_dir):
        print(f"Erreur: {run_dir} existe deja -- choisir un --run_name different.", file=sys.stderr)
        sys.exit(1)
    os.makedirs(run_dir, exist_ok=True)

    from unsloth import FastLanguageModel
    from trl import SFTConfig, SFTTrainer

    print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] Chargement de l'adaptateur Stage 3 (H-008) comme base ({args.stage3_adapter_path})...")
    model, tokenizer = FastLanguageModel.from_pretrained(
        model_name=args.stage3_adapter_path,
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
        save_steps=50,
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

    print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] Debut Stage 3c (run={args.run_name}, lr={args.learning_rate})...")
    t0 = time.time()
    trainer_stats = trainer.train()
    elapsed = time.time() - t0
    print("train_runtime_s:", trainer_stats.metrics.get("train_runtime"))
    print("train_loss:", trainer_stats.metrics.get("train_loss"))
    print(f"RESULT_ELAPSED_S={elapsed:.1f}")

    adapter_final_path = os.path.join(run_dir, "adapter_stage3c_final")
    model.save_pretrained(adapter_final_path)
    tokenizer.save_pretrained(adapter_final_path)
    print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] Stage 3c termine. Adapter final sauve dans {adapter_final_path}")


if __name__ == "__main__":
    main()

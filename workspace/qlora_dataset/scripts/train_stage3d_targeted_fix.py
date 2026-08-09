"""
H-015 -- 3e continuation corrective, ciblee et etroite (retry apres H-011,
qui laissait un seul defaut reel non resolu sur le Prompt 3 -- voir
VERDICT_H011_OVERREFUSAL_RETRY.md section 5 et PROBE_H015_FICHIER_SPECIFIQUE.md).

Non-negociable (brief H-015) : continue TOUJOURS depuis adapter_stage3c_final
(H-011), JAMAIS depuis un checkpoint anterieur ou rejete -- garde-fou
verifie explicitement au lancement (voir _assert_valid_base_adapter).

Dataset : dataset_stage3d.jsonl -- dataset_stage3c.jsonl (652 exemples,
INCHANGE, ancre anti-regression) + lot cible etroit de 5 exemples
(sous-type "bug au symptome generique bien connu, fichier nomme non
fourni", cf. build_dataset_stage3d.py) oversample x3 (15 occurrences,
2.2% du total). PAS un re-echantillonnage de toute la categorie A --
explicitement exclu par le brief.

learning_rate abaisse a 1e-5 (vs 2e-5 en H-011) : le delta introduit ici
est beaucoup plus etroit (15/667 exemples nouveaux vs 652/652 en H-011,
qui partait d'un adaptateur n'ayant jamais vu ce dataset) -- un pas plus
petit limite le risque de perturber les comportements deja stables sur les
7 autres prompts de VERDICT_COMMITPACK.md, notamment le Prompt 7 (cas
flagship de la regression catastrophique H-010, non reproduite en H-011).

2 epochs (vs 3 en H-011) : assez pour 2 expositions au lot cible sans
sur-repeter l'ancre deja apprise par adapter_stage3c_final.

Environnement : venv Unsloth Studio, pas py -3.12 --
  C:\\Users\\Ov3rL0rD\\.unsloth\\studio\\unsloth_studio\\Scripts\\python.exe train_stage3d_targeted_fix.py ...
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
DATASET_STAGE3D = os.path.join(REPO_ROOT, "workspace", "qlora_dataset", "dataset_stage3d.jsonl")
TRAINING_DIR = os.path.join(REPO_ROOT, "workspace", "qlora_dataset", "training_stage3d")
DEFAULT_STAGE3C_ADAPTER = os.path.join(
    REPO_ROOT, "workspace", "qlora_dataset", "training_stage3c", "runs",
    "stage3c_overrefusal_retry_20260809", "adapter_stage3c_final",
)

MAX_SEQ_LENGTH = 3072
SEED = 3407


def _assert_valid_base_adapter(path: str):
    normalized = path.replace("\\", "/").lower()
    if "stage3c" not in normalized:
        print(f"Erreur: {path} n'est pas l'adaptateur Stage 3c (H-011) -- "
              f"H-015 exige de repartir de adapter_stage3c_final, jamais d'un checkpoint "
              f"anterieur (stage3/H-008) ou rejete (stage3b/H-010). Abandon.",
              file=sys.stderr)
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
    records = load_jsonl(DATASET_STAGE3D)
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

    print(f"Dataset Stage 3d (correctif cible H-015, Prompt 3 + sous-type) : {len(records)} exemples")
    return Dataset.from_dict({"prompt": prompts, "completion": completions})


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--max_steps", type=int, default=None)
    parser.add_argument("--num_train_epochs", type=float, default=2.0)
    parser.add_argument("--run_name", type=str, required=True)
    parser.add_argument("--stage3c_adapter_path", type=str, default=DEFAULT_STAGE3C_ADAPTER)
    parser.add_argument("--learning_rate", type=float, default=1e-5)
    args = parser.parse_args()

    _assert_valid_base_adapter(args.stage3c_adapter_path)

    if not os.path.exists(DATASET_STAGE3D):
        print(f"Erreur: {DATASET_STAGE3D} absent -- lancer build_dataset_stage3d.py d'abord.", file=sys.stderr)
        sys.exit(1)

    run_dir = os.path.join(TRAINING_DIR, "runs", args.run_name)
    if os.path.exists(run_dir):
        print(f"Erreur: {run_dir} existe deja -- choisir un --run_name different.", file=sys.stderr)
        sys.exit(1)
    os.makedirs(run_dir, exist_ok=True)

    from unsloth import FastLanguageModel
    from trl import SFTConfig, SFTTrainer

    print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] Chargement de l'adaptateur Stage 3c (H-011) comme base ({args.stage3c_adapter_path})...")
    model, tokenizer = FastLanguageModel.from_pretrained(
        model_name=args.stage3c_adapter_path,
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
        num_train_epochs=args.num_train_epochs,
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

    print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] Debut Stage 3d (run={args.run_name}, lr={args.learning_rate}, epochs={args.num_train_epochs})...")
    t0 = time.time()
    trainer_stats = trainer.train()
    elapsed = time.time() - t0
    print("train_runtime_s:", trainer_stats.metrics.get("train_runtime"))
    print("train_loss:", trainer_stats.metrics.get("train_loss"))
    print(f"RESULT_ELAPSED_S={elapsed:.1f}")

    adapter_final_path = os.path.join(run_dir, "adapter_stage3d_final")
    model.save_pretrained(adapter_final_path)
    tokenizer.save_pretrained(adapter_final_path)
    print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] Stage 3d termine. Adapter final sauve dans {adapter_final_path}")


if __name__ == "__main__":
    main()

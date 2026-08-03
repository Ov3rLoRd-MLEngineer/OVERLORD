"""
Stage 2 -- competence commit-message -> diff, en continuant depuis
l'adaptateur Stage 1 ameliore (`training_stage1/runs/stage1_thestack_full/
adapter_stage1/`, competence generale de code sur bigcode/the-stack), PAS
depuis le modele Qwen3-4B brut ni depuis l'ancien adaptateur
`stage1_commitpack_full` (CommitPackFT, 2000 ex., stage distinct deja
termine). Dataset : `dataset_source_commitpack_full_python.jsonl` (150 000
exemples, sous-ensemble stratifie du vrai CommitPack -- voir
build_source_commitpack_full_python.py et HANDOFF_2026-08-03.md. Nom reel
sur disque note `_full_python` -- la consigne de session disait
`_python_full`, verifie et corrige avant de coder).

DIFFERENCE AVEC train_stage1_thestack.py (CLM texte brut) : ce dataset est
au format paires instruction/diff (`instruction`=sujet de commit,
`input`=corps du message, `output`=diff unifie), pas du code source brut a
completer. Template applique via `tokenizer.apply_chat_template` (message
utilisateur = instruction (+ corps si present), reponse assistant = diff)
et `completion_only_loss=True` -- la loss ne porte que sur le diff produit,
pas sur le message utilisateur, coherent avec train_stage2_instructions.py
(instruction-tuning) et different du Stage 1 (perte sur toute la sequence).

CORRECTIF FRAGMENTATION VRAM (valide sur train_stage1_thestack.py,
2026-08-02, meme cause structurelle attendue ici) : les diffs de
CommitPack varient de quasi-vides a 20000 caracteres (plafond
DIFF_SIZE_CAP applique en amont par build_source_commitpack_full_python.py)
-- exactement le profil de variance de longueur de sequence qui a
declenche la fragmentation de l'allocateur CUDA sur le Stage 1 the-stack
(200-8000 caracteres). Applique preventivement plutot que d'attendre une
degradation identique :
1. `PYTORCH_ALLOC_CONF=garbage_collection_threshold:0.8` (pas
   `expandable_segments:True` -- confirme silencieusement ignore sur
   Windows, UserWarning verifie lors du diagnostic Stage 1).
2. `group_by_length=True` (LengthGroupedSampler HF, bucket par longueur
   similaire).
3. `PeriodicCacheClearCallback` : `gc.collect()` + `torch.cuda.empty_cache()`
   explicites a chaque step (CACHE_CLEAR_EVERY_N_STEPS=1, valeur validee
   par le diagnostic Stage 1 -- 25 etait bien trop lache).

Garde-fou anti-ecrasement (`guard_no_overwrite`, identique a
train_stage1_thestack.py) : `--run_name` obligatoire, refuse d'ecrire dans
un dossier d'adaptateur deja existant sans `--allow_overwrite` explicite.
Desactive automatiquement des que `--resume_from_checkpoint` est fourni
(reprendre un run existant n'est pas un ecrasement).

REPRISE (`--resume_from_checkpoint auto|<chemin checkpoint-N>`) : les
checkpoints HF Trainer (`save_steps`, poids+optimiseur+scheduler+position
dans les donnees) permettent de continuer un run borne plus tard sans tout
refaire depuis le debut -- `auto` prend le plus grand `checkpoint-N` de
`--run_name`. MISE EN GARDE : `--max_steps` est un total ABSOLU, pas un
delta (ex. reprendre a 6000 et viser 12000 -> `--max_steps 12000`). Le
schedule `lr_scheduler_type="linear"` est recalcule sur ce nouveau
`--max_steps` a chaque invocation -- si le premier run visait deja 6000
(LR decroissant jusqu'a ~0 pile a ce point), une reprise qui vise plus
loin ne retrouve pas la meme courbe qu'un run unique planifie sur la
duree totale des le depart (le LR restaure par le scheduler sauvegarde
peut ne pas correspondre exactement au nouveau total). Effet generalement
mineur en LoRA mais a garder en tete si la courbe de loss parait
inhabituelle juste apres une reprise.

RAPPEL REGLES DE SESSION : smoke test (`--max_steps 8`) obligatoire et
verifie sur disque avant tout lancement complet. RTX 5060 Ti non touchee
(CUDA_VISIBLE_DEVICES=0, RTX 5080 dediee, meme convention que les 2 autres
scripts train_stage*.py).
"""
import argparse
import gc
import json
import os
import random
import sys
import time

os.environ.setdefault("CUDA_VISIBLE_DEVICES", "0")  # RTX 5080 dediee -- RTX 5060 Ti (inference Ollama) non touchee
os.environ.setdefault("PYTORCH_ALLOC_CONF", "garbage_collection_threshold:0.8")  # voir CORRECTIF ci-dessus

# Ordre d'import volontaire : unsloth AVANT transformers (memes raisons que
# train_stage1_thestack.py -- patches d'optimisation appliques a l'import).
from unsloth import FastLanguageModel  # noqa: E402
from transformers import TrainerCallback  # noqa: E402
from trl import SFTConfig, SFTTrainer  # noqa: E402

REPO_ROOT = r"D:\OVERLORD"
COMMITPACK_DATASET = os.path.join(REPO_ROOT, "workspace", "qlora_dataset",
                                   "dataset_source_commitpack_full_python.jsonl")
TRAINING_DIR = os.path.join(REPO_ROOT, "workspace", "qlora_dataset", "training_stage2")
DEFAULT_STAGE1_ADAPTER = os.path.join(REPO_ROOT, "workspace", "qlora_dataset",
                                       "training_stage1", "runs", "stage1_thestack_full", "adapter_stage1")

MAX_SEQ_LENGTH = 3072  # coherent avec train_stage2_instructions.py -- diffs plafonnes 20000 car. en amont
CACHE_CLEAR_EVERY_N_STEPS = 1
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


def build_dataset(tokenizer, limit=None):
    from datasets import Dataset
    raw_data = load_jsonl(COMMITPACK_DATASET)
    rng = random.Random(SEED)
    rng.shuffle(raw_data)
    if limit is not None:
        raw_data = raw_data[:limit]

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

    print(f"Dataset Stage 2 CommitPack charge : {len(prompts)} exemples "
          f"(source: {COMMITPACK_DATASET}).")
    return Dataset.from_dict({"prompt": prompts, "completion": completions})


class PeriodicCacheClearCallback(TrainerCallback):
    """Identique a train_stage1_thestack.py -- voir CORRECTIF en tete de
    fichier pour le raisonnement (fragmentation de l'allocateur CUDA sur
    sequences de longueur tres variable)."""

    def __init__(self, every_n_steps):
        self.every_n_steps = every_n_steps

    def on_step_end(self, args, state, control, **kwargs):
        import torch
        alloc_mb = torch.cuda.memory_allocated() / 1024**2
        reserv_mb = torch.cuda.memory_reserved() / 1024**2
        print(f"[mem] step={state.global_step} allocated_mb={alloc_mb:.0f} reserved_mb={reserv_mb:.0f}", flush=True)
        if state.global_step > 0 and state.global_step % self.every_n_steps == 0:
            gc.collect()
            torch.cuda.empty_cache()
        return control


def find_latest_checkpoint(run_dir):
    if not os.path.isdir(run_dir):
        return None
    checkpoints = [d for d in os.listdir(run_dir) if d.startswith("checkpoint-")]
    if not checkpoints:
        return None
    checkpoints.sort(key=lambda d: int(d.split("-")[1]))
    return os.path.join(run_dir, checkpoints[-1])


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
    parser.add_argument("--stage1_adapter_path", type=str, default=DEFAULT_STAGE1_ADAPTER,
                         help="Chemin vers l'adaptateur Stage 1 (defaut: stage1_thestack_full/adapter_stage1)")
    parser.add_argument("--allow_overwrite", action="store_true")
    parser.add_argument("--dataset_limit", type=int, default=None,
                         help="Limite le nombre d'exemples charges (smoke test uniquement)")
    parser.add_argument("--save_steps", type=int, default=100)
    parser.add_argument("--resume_from_checkpoint", type=str, default=None,
                         help="Reprend un run existant : 'auto' (dernier checkpoint de --run_name) "
                              "ou un chemin explicite vers un dossier checkpoint-N. --max_steps doit "
                              "alors viser le total absolu souhaite (pas un delta) -- voir docstring "
                              "pour la mise en garde sur le scheduler LR lineaire.")
    args = parser.parse_args()

    if args.max_steps is None and args.num_train_epochs is None:
        print("Erreur: fournir --max_steps ou --num_train_epochs.", file=sys.stderr)
        sys.exit(1)

    if not os.path.isdir(args.stage1_adapter_path):
        print(f"Erreur: adaptateur Stage 1 introuvable a {args.stage1_adapter_path}", file=sys.stderr)
        sys.exit(1)

    run_dir = os.path.join(TRAINING_DIR, "runs", args.run_name)
    adapter_path = os.path.join(run_dir, "adapter_stage2_commitpack")

    resume_path = args.resume_from_checkpoint
    if resume_path == "auto":
        resume_path = find_latest_checkpoint(run_dir)
        if resume_path is None:
            print(f"Erreur: --resume_from_checkpoint auto mais aucun checkpoint-N trouve dans {run_dir}", file=sys.stderr)
            sys.exit(1)
        print(f"resume_from_checkpoint (auto) -> {resume_path}")

    if resume_path is None:
        # Run neuf : le garde-fou anti-ecrasement s'applique normalement.
        guard_no_overwrite(adapter_path, args.allow_overwrite)
    elif not os.path.isdir(resume_path):
        print(f"Erreur: checkpoint de reprise introuvable a {resume_path}", file=sys.stderr)
        sys.exit(1)

    os.makedirs(run_dir, exist_ok=True)

    print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] Chargement de l'adaptateur Stage 1 "
          f"({args.stage1_adapter_path}) comme base pour le Stage 2 CommitPack...")
    model, tokenizer = FastLanguageModel.from_pretrained(
        model_name=args.stage1_adapter_path,
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

    dataset = build_dataset(tokenizer, limit=args.dataset_limit)

    sft_config = SFTConfig(
        output_dir=run_dir,
        per_device_train_batch_size=1,
        gradient_accumulation_steps=8,
        warmup_steps=5,
        max_steps=args.max_steps if args.max_steps is not None else -1,
        num_train_epochs=args.num_train_epochs if args.num_train_epochs is not None else 1,
        learning_rate=2e-4,  # coherent avec les 2 stages "competence" (thestack, ancien commitpack) --
        # 1e-4 reste reserve au stage de personnalisation/style (Source A/B/C, dataset petit et fin)
        logging_steps=1,
        optim="adamw_8bit",
        weight_decay=0.01,
        lr_scheduler_type="linear",
        seed=SEED,
        save_steps=args.save_steps,
        save_strategy="steps",
        report_to="none",
        max_length=MAX_SEQ_LENGTH,
        group_by_length=True,
        packing=False,
        bf16=True,
        completion_only_loss=True,
    )

    trainer = SFTTrainer(
        model=model,
        tokenizer=tokenizer,
        train_dataset=dataset,
        args=sft_config,
        callbacks=[PeriodicCacheClearCallback(CACHE_CLEAR_EVERY_N_STEPS)],
    )

    print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] Debut Stage 2 CommitPack (run={args.run_name})"
          f"{' -- reprise depuis ' + resume_path if resume_path else ''}...")
    trainer_stats = trainer.train(resume_from_checkpoint=resume_path)
    print("train_runtime_s:", trainer_stats.metrics.get("train_runtime"))
    print("train_loss:", trainer_stats.metrics.get("train_loss"))

    model.save_pretrained(adapter_path)
    tokenizer.save_pretrained(adapter_path)
    print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] Stage 2 CommitPack termine. Adapter sauve dans {adapter_path}")


if __name__ == "__main__":
    main()

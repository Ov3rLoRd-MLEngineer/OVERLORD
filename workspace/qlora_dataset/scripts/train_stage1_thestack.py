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

CORRECTIF 2026-08-02 (retour d'experience direct, incident reproduit
identiquement 2 fois sur RTX 5080 16 Go) : le run degradait progressivement
de ~5s/step a 400-500s/step apres ~1000-1100 steps, VRAM quasi pleine
(15.7-15.9/16.3 Go), `power.draw` chutant a ~77W (signe de stall/contention,
pas de calcul efficace) -- fragmentation de l'allocateur CUDA sur un run
long a sequences de longueur tres variable (code source brut, 200-8000
caracteres, pas de packing). Cause racine confirmee : `expandable_segments:True`
(cense prevenir ce type de fragmentation) est **silencieusement ignore sur
Windows** (`UserWarning: expandable_segments not supported on this
platform`, verifie explicitement -- torch 2.10.0+cu130 sur cette machine).
Un simple redemarrage repoussait le mur d'environ 4h30 sans le resoudre
(reproduit a l'identique 2 fois). Correctifs appliques, aucun ne necessite
un GPU plus gros (contrainte utilisateur : pas de carte 32 Go disponible) :
1. `PYTORCH_ALLOC_CONF` remplace par des cles reellement supportees sur
   Windows (`garbage_collection_threshold`, `max_split_size_mb` -- verifie
   sans warning sur cette machine, contrairement a `expandable_segments`).
2. `MAX_SEQ_LENGTH` reduit 3072->2048 (marge VRAM supplementaire, le
   dataset the-stack est deja plafonne a 8000 caracteres/~2000 tokens en
   amont donc peu de troncature reelle attendue).
3. Callback `PeriodicCacheClearCallback` : `gc.collect()` +
   `torch.cuda.empty_cache()` explicites tous les CACHE_CLEAR_EVERY_N_STEPS
   steps, independamment de tout comportement d'allocateur specifique a la
   plateforme -- le filet de securite le plus direct et le moins fragile.
"""
import argparse
import gc
import json
import os
import random
import sys
import time

os.environ.setdefault("CUDA_VISIBLE_DEVICES", "0")  # RTX 5080 dediee
# expandable_segments:True retire -- non supporte sur Windows (silencieusement
# ignore, UserWarning verifie), remplace par des cles reellement actives ici.
# max_split_size_mb:256 retire (2e correctif) -- le smoke test a degrade des
# step ~20 avec cette valeur, plus vite qu'avant le correctif (step ~1100) :
# plafonner trop bas la taille de split force probablement plus de petites
# allocations/fragmentation, pas moins. garbage_collection_threshold seul +
# le callback de nettoyage explicite (voir PeriodicCacheClearCallback).
os.environ.setdefault("PYTORCH_ALLOC_CONF", "garbage_collection_threshold:0.8")

# Ordre d'import volontaire : unsloth AVANT transformers (patches
# d'optimisation d'Unsloth appliques a l'import -- sinon UserWarning
# "Unsloth should be imported before [transformers]" et perte des
# optimisations, verifie).
from unsloth import FastLanguageModel  # noqa: E402
from transformers import TrainerCallback  # noqa: E402
from trl import SFTConfig, SFTTrainer  # noqa: E402

REPO_ROOT = r"D:\OVERLORD"
THESTACK_DATASET = r"E:\data\thestack_python_subset\dataset_source_thestack_python.jsonl"
TRAINING_DIR = os.path.join(REPO_ROOT, "workspace", "qlora_dataset", "training_stage1")

MODEL_NAME = "unsloth/Qwen3-4B-Instruct-2507"
MAX_SEQ_LENGTH = 2048  # reduit de 3072 -- marge VRAM supplementaire (voir CORRECTIF ci-dessus)
CACHE_CLEAR_EVERY_N_STEPS = 1  # diagnostic confirme (2026-08-02) : "reserved" double en 2-3 steps, 25 etait bien trop lache
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


class PeriodicCacheClearCallback(TrainerCallback):
    """Filet de securite direct contre la fragmentation de l'allocateur CUDA
    (voir CORRECTIF en tete de fichier) -- independant de tout reglage
    d'allocateur specifique a la plateforme. Herite de TrainerCallback (pas
    juste un objet nu) : CallbackHandler.call_event appelle getattr(callback,
    event) SANS valeur par defaut pour tous les evenements (on_init_end,
    on_train_begin, etc.), pas seulement on_step_end -- sans heriter, ca
    plante des l'init avec AttributeError (verifie).

    DIAGNOSTIC 2026-08-02 (ajoute apres l'echec du premier correctif -- le
    smoke test degradait des step ~20 au lieu de ~1100 sur le run complet,
    donc max_split_size_mb:256 etait probablement contre-productif, pas la
    solution) : log allocated vs reserved a CHAQUE step pour distinguer une
    vraie fuite (les deux montent ensemble) d'une fragmentation classique
    (reserved monte, allocated reste stable/bas)."""

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
        group_by_length=True,  # 3e correctif : bucket par longueur similaire
        # (LengthGroupedSampler HF) -- le diagnostic per-step (allocated
        # stable ~3.78 Go, reserved oscille 4.2->7.8 Go et remonte meme avec
        # un clear a chaque step) pointe vers la variance de longueur de
        # sequence (code source brut, 200-8000 caracteres) comme cause
        # structurelle, pas juste un besoin de nettoyer plus souvent.
        dataset_text_field="text",
        packing=False,
        bf16=True,
    )

    trainer = SFTTrainer(
        model=model,
        tokenizer=tokenizer,
        train_dataset=dataset,
        args=sft_config,
        callbacks=[PeriodicCacheClearCallback(CACHE_CLEAR_EVERY_N_STEPS)],
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

"""
Pipeline Stage 1 + Stage 2 -- wrapper qui enchaine les deux scripts.

CORRECTION 2026-08-02 (retour d'expérience direct, voir CLAUDE.md section
"Économie de session et de tokens") : la version précédente hardcodait
`--run_name stage1_commitpack_full --max_steps 60`, un run_name IDENTIQUE à
celui d'un entraînement complet (250 steps/1 époque) déjà réussi et jugé bon
-- deux exécutions de ce pipeline ont silencieusement écrasé le dossier
`adapter_stage1/` du bon run avec une version très sous-entraînée (60 steps).
Récupéré via le checkpoint intermédiaire `checkpoint-250/` (save_steps=100
n'écrit jamais dans le même dossier), mais ça n'aurait pas dû arriver.

Deux garde-fous ajoutés :
1. `--max_steps`/`--num_train_epochs` doivent être fournis explicitement
   (pas de valeur par défaut silencieuse) et sont transmis tels quels aux
   deux étages -- pas de nombre de steps différent selon l'étage sans le
   demander explicitement.
2. Avant de lancer un étage, si le dossier de sortie de l'adaptateur existe
   déjà, le pipeline s'arrête avec une erreur explicite au lieu d'écraser
   -- `--allow_overwrite` lève ce garde-fou en connaissance de cause.
"""
import argparse
import os
import subprocess

def run_command(cmd):
    """Exécute une commande shell et s'arrête en cas d'erreur."""
    print(f"\n[EXÉCUTION] : {' '.join(cmd)}")
    result = subprocess.run(cmd)
    if result.returncode != 0:
        raise RuntimeError(f"Erreur lors de l'exécution de la commande : {' '.join(cmd)}")

def guard_no_overwrite(adapter_path, run_label, allow_overwrite):
    if os.path.exists(adapter_path) and not allow_overwrite:
        raise FileExistsError(
            f"L'adaptateur {run_label} existe déjà à : {adapter_path}\n"
            f"Choisis un --{run_label}_run_name différent, ou relance avec "
            f"--allow_overwrite si l'écrasement est voulu en connaissance de cause."
        )

def main():
    parser = argparse.ArgumentParser(description="Pipeline d'entraînement complet QLoRA (Stage 1 + Stage 2)")
    parser.add_argument("--python_path", type=str, default=r"C:\Users\Ov3rL0rD\.unsloth\studio\unsloth_studio\Scripts\python.exe", help="Chemin vers l'interpréteur Python")
    parser.add_argument("--base_dir", type=str, default=r"D:\OVERLORD\workspace\qlora_dataset", help="Dossier de travail principal")
    parser.add_argument("--stage1_run_name", type=str, required=True, help="run_name pour le Stage 1 (doit être nouveau, sauf --allow_overwrite)")
    parser.add_argument("--stage2_run_name", type=str, required=True, help="run_name pour le Stage 2 (doit être nouveau, sauf --allow_overwrite)")
    parser.add_argument("--max_steps", type=int, default=None, help="Transmis tel quel aux deux étages")
    parser.add_argument("--num_train_epochs", type=float, default=None, help="Transmis tel quel aux deux étages")
    parser.add_argument("--allow_overwrite", action="store_true", help="Autorise l'écrasement d'un adaptateur existant au même run_name")
    args = parser.parse_args()

    if args.max_steps is None and args.num_train_epochs is None:
        raise ValueError("Fournir --max_steps ou --num_train_epochs (transmis aux deux étages).")

    train_len_args = ["--max_steps", str(args.max_steps)] if args.max_steps is not None \
        else ["--num_train_epochs", str(args.num_train_epochs)]

    scripts_dir = os.path.join(args.base_dir, "scripts")
    stage1_script = os.path.join(scripts_dir, "train_stage1_commitpack.py")
    stage2_script = os.path.join(scripts_dir, "train_stage2_instructions.py")

    adapter_stage1_path = os.path.join(args.base_dir, "training_stage1", "runs", args.stage1_run_name, "adapter_stage1")
    adapter_stage2_path = os.path.join(args.base_dir, "training_stage2", "runs", args.stage2_run_name, "adapter_stage2_final")

    print("==================================================")
    print(" DÉBUT DU PIPELINE D'ENTRAÎNEMENT COMPLET")
    print("==================================================")

    # --- ÉTAPE 1 : Entraînement Stage 1 ---
    print("\n--- [ÉTAPE 1/2] Lancement de l'entraînement Stage 1 ---")
    guard_no_overwrite(adapter_stage1_path, "stage1", args.allow_overwrite)
    cmd_stage1 = [args.python_path, stage1_script, "--run_name", args.stage1_run_name] + train_len_args
    run_command(cmd_stage1)

    # --- ÉTAPE 2 : Entraînement Stage 2 (reprise depuis l'adaptateur Stage 1) ---
    print("\n--- [ÉTAPE 2/2] Lancement de l'entraînement Stage 2 (Continuer depuis Stage 1) ---")
    if not os.path.exists(adapter_stage1_path):
        raise FileNotFoundError(f"L'adaptateur du Stage 1 est introuvable à : {adapter_stage1_path}")
    guard_no_overwrite(adapter_stage2_path, "stage2", args.allow_overwrite)

    cmd_stage2 = [
        args.python_path, stage2_script,
        "--run_name", args.stage2_run_name,
        "--stage1_adapter_path", adapter_stage1_path,
    ] + train_len_args
    run_command(cmd_stage2)

    print("\n==================================================")
    print(" PIPELINE TERMINÉ AVEC SUCCÈS !")
    print("==================================================")

if __name__ == "__main__":
    main()
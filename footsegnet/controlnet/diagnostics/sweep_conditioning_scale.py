"""Diagnostic Control-LoRA : balayage de controlnet_conditioning_scale.

Reutilise load_pipeline()/generate()/FIXED_TEST_SET d'eval_checkpoint.py
(charge le pipeline UNE seule fois) pour generer, sur un checkpoint deja
entraine (aucun nouveau training), les 5 prompts de reference a plusieurs
valeurs de conditioning_scale -- objectif : trouver le point de bascule ou
le residu ControlNet casse la coherence de l'image, et si la
differenciation visible a faible echelle (cf. DIAGNOSTIC_MODE_COLLAPSE_
20260728.md, verification du 2026-07-29) est bien liee au masque ou n'est
qu'un artefact de faible magnitude.

N'importe PAS eval_checkpoint.py au niveau module tel quel (son
os.environ.setdefault("CUDA_VISIBLE_DEVICES", "1") s'executerait avant que
ce script ait pu forcer un autre GPU) -- ce script doit donc definir
CUDA_VISIBLE_DEVICES lui-meme AVANT d'importer eval_checkpoint.

Usage :
    CUDA_VISIBLE_DEVICES=0 py -3.12 diagnostics/sweep_conditioning_scale.py \
        --checkpoint output/control_lora_v1_fix50_test_samegpu/checkpoint-1500
"""

import argparse
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

# eval_checkpoint.py utilise os.environ.setdefault -- si CUDA_VISIBLE_DEVICES
# est deja positionne dans l'environnement (export avant d'appeler ce script),
# le setdefault ne l'ecrasera pas. Sinon, aligne sur le meme defaut (GPU1)
# que eval_checkpoint.py pour rester coherent avec la convention du fichier.
os.environ.setdefault("CUDA_VISIBLE_DEVICES", "1")

import eval_checkpoint as ec  # noqa: E402

# eval_checkpoint.py resout DATASET_DIR/EVAL_OUTPUT_DIR relativement a son
# PROPRE emplacement (HERE = Path(__file__).resolve().parent) -- ce script
# vit dans le worktree diagnostique (dataset/ non present, gitignore), pas
# dans l'arborescence principale ou vivent reellement dataset/ et
# eval_output/. Redirige explicitement vers l'arborescence principale
# plutot que de dupliquer tout le dataset dans le worktree.
ec.DATASET_DIR = Path("D:/OVERLORD/footsegnet/controlnet/dataset")
ec.EVAL_OUTPUT_DIR = Path("D:/OVERLORD/footsegnet/controlnet/eval_output")

SCALES = [0.15, 0.3, 0.5, 0.7, 0.85, 1.0]


def main() -> None:
    parser = argparse.ArgumentParser(description="Balayage conditioning_scale sur un checkpoint deja entraine")
    parser.add_argument("--checkpoint", required=True)
    parser.add_argument("--n-prompts", type=int, default=len(ec.FIXED_TEST_SET))
    parser.add_argument("--steps", type=int, default=30)
    parser.add_argument("--guidance-scale", type=float, default=7.0)
    parser.add_argument("--resolution", type=int, default=1024)
    parser.add_argument("--output-dir", default=str(ec.EVAL_OUTPUT_DIR / "scale_sweep"))
    args = parser.parse_args()

    checkpoint_dir = Path(args.checkpoint)
    if not checkpoint_dir.is_absolute():
        checkpoint_dir = (ec.HERE / checkpoint_dir).resolve()

    out_dir = Path(args.output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    slug = ec.checkpoint_slug(checkpoint_dir)

    print(f"[sweep] Chargement pipeline (une seule fois) -- checkpoint={slug}")
    pipe = ec.load_pipeline(checkpoint_dir)

    test_set = ec.FIXED_TEST_SET[: max(1, min(args.n_prompts, len(ec.FIXED_TEST_SET)))]
    print(f"[sweep] {len(test_set)} prompt(s) x {len(SCALES)} echelle(s) = {len(test_set) * len(SCALES)} images")

    for i, entry in enumerate(test_set):
        seed = ec.BASE_SEED + i * 137
        for scale in SCALES:
            print(f"[sweep] prompt={entry['stem']} scale={scale} seed={seed}")
            img = ec.generate(pipe, entry, seed, args.steps, args.guidance_scale,
                               args.resolution, conditioning_scale=scale)
            out_path = out_dir / f"{slug}__{entry['stem']}__scale{scale:.2f}.png"
            img.save(out_path)
            print(f"    -> {out_path}")

    print("[sweep] Termine.")


if __name__ == "__main__":
    main()

"""Diagnostic Control-LoRA : leve la reserve methodologique du sweep d'echelle
du 2026-07-29 (DIAGNOSTIC_MODE_COLLAPSE_20260728.md, section "Balayage de
conditioning_scale") -- dans ce sweep-la, chaque prompt du set fixe variait
aussi en texte ET en seed en plus du masque, donc la difference visuelle
observee entre prompts ne prouvait pas isolement que c'etait le masque
(et pas le texte/seed) qui pilotait la differenciation.

Ici : UN SEUL texte, UN SEUL seed, SEUL le masque de conditionnement varie
entre generations, a plusieurs echelles. Si la difference persiste dans ces
conditions controlees, c'est confirme comme un vrai signal lie au masque.

Aucun nouveau training -- reutilise un checkpoint deja entraine.

Usage :
    CUDA_VISIBLE_DEVICES=0 py -3.12 diagnostics/sweep_mask_only.py \
        --checkpoint output/control_lora_v1_fix50_test_samegpu/checkpoint-1500
"""

import argparse
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

os.environ.setdefault("CUDA_VISIBLE_DEVICES", "1")

import eval_checkpoint as ec  # noqa: E402

ec.DATASET_DIR = Path("D:/OVERLORD/footsegnet/controlnet/dataset")
ec.EVAL_OUTPUT_DIR = Path("D:/OVERLORD/footsegnet/controlnet/eval_output")

MANIFEST = ec.DATASET_DIR / "manifest_filtered.jsonl"

# Memes indices que la sonde de correlation (probe_mode_collapse.py) --
# choisis a l'origine pour leur diversite de masque, coherence de
# methodologie entre les deux diagnostics.
MASK_INDICES = [0, 100, 200, 300]

FIXED_TEXT = ec.FIXED_TEST_SET[0]["text"]
FIXED_SEED = ec.BASE_SEED

SCALES = [0.15, 0.30, 0.50, 0.70, 1.00]


def main() -> None:
    parser = argparse.ArgumentParser(description="Sweep d'echelle, masque seul comme variable (texte/seed fixes)")
    parser.add_argument("--checkpoint", required=True)
    parser.add_argument("--steps", type=int, default=30)
    parser.add_argument("--guidance-scale", type=float, default=7.0)
    parser.add_argument("--resolution", type=int, default=1024)
    parser.add_argument("--output-dir", default=str(ec.EVAL_OUTPUT_DIR / "mask_only_sweep"))
    args = parser.parse_args()

    checkpoint_dir = Path(args.checkpoint)
    if not checkpoint_dir.is_absolute():
        checkpoint_dir = (ec.HERE / checkpoint_dir).resolve()

    out_dir = Path(args.output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    slug = ec.checkpoint_slug(checkpoint_dir)

    entries = [json.loads(l) for l in MANIFEST.read_text(encoding="utf-8").splitlines() if l.strip()]
    masks = [entries[i]["conditioning_image"] for i in MASK_INDICES]
    print(f"[sweep_mask_only] texte fixe : {FIXED_TEXT[:80]}...")
    print(f"[sweep_mask_only] seed fixe : {FIXED_SEED}")
    print(f"[sweep_mask_only] masques testes : {masks}")

    print(f"[sweep_mask_only] Chargement pipeline -- checkpoint={slug}")
    pipe = ec.load_pipeline(checkpoint_dir)

    print(f"[sweep_mask_only] {len(masks)} masque(s) x {len(SCALES)} echelle(s) = {len(masks) * len(SCALES)} images")

    for mask_idx, cond_image in zip(MASK_INDICES, masks):
        entry = {"stem": f"mask{mask_idx:04d}", "conditioning_image": cond_image, "text": FIXED_TEXT}
        for scale in SCALES:
            print(f"[sweep_mask_only] mask_idx={mask_idx} scale={scale}")
            img = ec.generate(pipe, entry, FIXED_SEED, args.steps, args.guidance_scale,
                               args.resolution, conditioning_scale=scale)
            out_path = out_dir / f"{slug}__maskidx{mask_idx:04d}__scale{scale:.2f}.png"
            img.save(out_path)
            print(f"    -> {out_path}")

    print("[sweep_mask_only] Termine.")


if __name__ == "__main__":
    main()

# ██████╗ ██╗   ██╗██████╗ ██████╗ ██╗      ██████╗ ██████╗ ██████╗
# ██╔═══██╗██║   ██║╚════██╗██╔══██╗██║     ██╔═══██╗██╔══██╗██╔══██╗
# ██║   ██║██║   ██║ █████╔╝██████╔╝██║     ██║   ██║██████╔╝██║  ██║
# ██║   ██║╚██╗ ██╔╝ ╚═══██╗██╔══██╗██║     ██║   ██║██╔══██╗██║  ██║
# ╚██████╔╝ ╚████╔╝ ██████╔╝██║  ██║███████╗╚██████╔╝██║  ██║██████╔╝
# ╚═════╝   ╚═══╝  ╚═════╝ ╚═╝  ╚═╝╚══════╝ ╚═════╝ ╚═╝  ╚═╝╚═════╝
# Ov3rLoRd -- pipeline de production anime autonome (ComfyUI)
# https://github.com/Ov3rLoRd-MLEngineer
#
# eval_checkpoint.py — FootSegNet Control-LoRA -> évaluation visuelle d'un checkpoint
#
# Charge un checkpoint LoRA (format peft : adapter_config.json +
# adapter_model.safetensors, cf. output/<run>/checkpoint-N/) sur le
# ControlNetModel SDXL correspondant, génère sur un petit set FIXE de 5
# prompts (choisis dans dataset/manifest_filtered.jsonl pour leur diversité
# chaussure/pose/genre, masques manuels = vérité terrain), et sauve chaque
# image sous <checkpoint>__<prompt>.png pour comparaison visuelle facile
# entre plusieurs checkpoints/runs.
#
# Volontairement independant de train_control_lora.py (une autre session
# diagnostique un bug dessus au 2026-07-28, fichier hors limites -- meme en
# lecture) : l'architecture est reconstruite uniquement a partir de ce qui
# est deja documente dans README.md de ce dossier et dans adapter_config.json
# du checkpoint lui-meme (donnees, pas code) :
#   - ControlNetModel.from_unet(unet) -- backbone copie de l'UNet SDXL,
#     gele sauf les modules listes ci-dessous
#   - LoRA rang 64 (peft) sur les projections d'attention to_q/to_k/to_v/to_out.0
#   - controlnet_cond_embedding + controlnet_down_blocks.0-8 + controlnet_mid_block
#     entierement fine-tunes (modules_to_save de l'adapter, pas juste LoRA)
#   - VAE plein sdxl_vae.safetensors (pas taesdxl -- ADR-002 concerne
#     l'inference du pipeline de production, pas l'entrainement/eval de ce LoRA)
#
# --baseline genere en plus la meme image avec controlnet_conditioning_scale=0.0
# ("residus zero-init" -- la contribution du ControlNet aux skip-connections
# de l'UNet est annulee, peu importe l'adapter charge), pour un point de
# comparaison "sans ControlNet" a cote de chaque image conditionnee.
#
# Usage :
#   py -3.12 eval_checkpoint.py --checkpoint output/control_lora_v1_convergence_test/checkpoint-2000
#   py -3.12 eval_checkpoint.py --checkpoint <chemin> --baseline
#   py -3.12 eval_checkpoint.py --checkpoint <chemin> --steps 20 --n-prompts 2   (essai rapide)

import argparse
import json
import os
import sys
from pathlib import Path

# GPU 1 (RTX 5060 Ti) uniquement -- ne jamais toucher a la RTX 5080 (GPU 0),
# potentiellement occupee par un entrainement/diagnostic en cours. Doit etre
# fixe AVANT l'import de torch.
os.environ.setdefault("CUDA_VISIBLE_DEVICES", "1")

import torch  # noqa: E402
from PIL import Image  # noqa: E402
from diffusers import (  # noqa: E402
    AutoencoderKL,
    ControlNetModel,
    StableDiffusionXLControlNetPipeline,
    StableDiffusionXLPipeline,
)
from peft import PeftModel  # noqa: E402

_REPO_ROOT = Path(__file__).resolve().parent.parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))
import config  # noqa: E402

HERE = Path(__file__).resolve().parent
DATASET_DIR = HERE / "dataset"
EVAL_OUTPUT_DIR = HERE / "eval_output"   # dossier dedie, distinct de output/<run>/validation/

CHECKPOINT_FILE = config.CHECKPOINTS_DIR / "fabricatedXL_v70.safetensors"
VAE_FILE = config.COMFYUI_MODELS / "vae" / "sdxl_vae.safetensors"

# Set de test fixe -- 5 entrees de dataset/manifest_filtered.jsonl choisies le
# 2026-07-28 pour leur diversite (type de chaussure, pose, genre), toutes a
# masque manuel (verite terrain, pas de pre-masque auto). Fixe et code en dur
# (pas tire au hasard) pour que deux runs sur des checkpoints differents soient
# directement comparables image par image.
FIXED_TEST_SET = [
    {
        "stem": "footsegnet_00000",
        "conditioning_image": "conditioning_images/footsegnet_00000.png",
        "text": "score_9, score_8_up, source_anime, 1girl, solo, full body, side view, "
                "climbing stairs, kimono, ankle-length, knee-high black leather boots, "
                "city street at night, neon lights, both feet visible, clean footwear "
                "details, anime style",
    },
    {
        "stem": "footsegnet_00001",
        "conditioning_image": "conditioning_images/footsegnet_00001.png",
        "text": "score_9, score_8_up, source_anime, 1girl, solo, full body, jumping, "
                "both feet off the ground, business suit with slacks, barefoot, abstract "
                "gradient background, pastel colors, detailed bare feet, toes visible, "
                "anime style",
    },
    {
        "stem": "footsegnet_00002",
        "conditioning_image": "conditioning_images/footsegnet_00002.png",
        "text": "score_9, score_8_up, source_anime, 1girl, solo, full body, side view, "
                "leaning against a wall, one foot up, red tracksuit, traditional japanese "
                "geta sandals, convenience store interior, both feet visible, clean "
                "footwear details, anime style",
    },
    {
        "stem": "footsegnet_00012",
        "conditioning_image": "conditioning_images/footsegnet_00012.png",
        "text": "score_9, score_8_up, source_anime, 1boy, solo, full body, back view, "
                "running, dynamic pose, sundress, knee-length, white low-top canvas "
                "sneakers, shopping mall, tiled floor, heels and soles visible, anime style",
    },
    {
        "stem": "footsegnet_00040",
        "conditioning_image": "conditioning_images/footsegnet_00040.png",
        "text": "score_9, score_8_up, source_anime, 1girl, solo, full body, three-quarter "
                "view, standing on one foot, balancing, sweatpants and basketball jersey, "
                "gold strappy heels, grassy park, sunny day, dynamic lighting, feet in "
                "frame, anime style",
    },
]

BASE_SEED = 42   # cf. ADR-008 (CLAUDE.md) : base_seed + i * 137 pour une variation
                 # controlee et reproductible entre prompts, independant du --seed
                 # de train_control_lora.py (outil different, pas de lien attendu).


def load_pipeline(checkpoint_dir: Path) -> StableDiffusionXLControlNetPipeline:
    if not (checkpoint_dir / "adapter_config.json").exists():
        raise FileNotFoundError(
            f"{checkpoint_dir} ne contient pas adapter_config.json -- pas un "
            "checkpoint LoRA peft valide (cf. output/<run>/checkpoint-N/)")

    print(f"[eval_checkpoint] Chargement base SDXL : {CHECKPOINT_FILE.name}")
    donor = StableDiffusionXLPipeline.from_single_file(
        str(CHECKPOINT_FILE), torch_dtype=torch.float16, use_safetensors=True,
    )

    print(f"[eval_checkpoint] Chargement VAE plein : {VAE_FILE.name}")
    vae = AutoencoderKL.from_single_file(str(VAE_FILE), torch_dtype=torch.float16)

    print("[eval_checkpoint] Construction ControlNetModel (from_unet, backbone SDXL)")
    controlnet = ControlNetModel.from_unet(donor.unet)

    print(f"[eval_checkpoint] Chargement adapter LoRA : {checkpoint_dir}")
    controlnet = PeftModel.from_pretrained(controlnet, str(checkpoint_dir))
    # Fusionne les deltas LoRA (+ restaure les modules_to_save entierement
    # fine-tunes) dans un ControlNetModel "nu" : le pipeline SDXL ControlNet
    # de diffusers valide isinstance(self.controlnet, ControlNetModel) dans
    # check_inputs() et echoue sur un PeftModel non fusionne (assert False).
    controlnet = controlnet.merge_and_unload()
    # peft merge_and_unload() remonte certains poids fusionnes en float32
    # (calcul de fusion en precision superieure) independamment du dtype du
    # reste du pipeline -- realigne tout en fp16 pour eviter un mismatch
    # Half/Float au forward (mat1 and mat2 must have the same dtype).
    controlnet = controlnet.to(torch.float16)
    controlnet.eval()

    pipe = StableDiffusionXLControlNetPipeline(
        vae=vae,
        text_encoder=donor.text_encoder,
        text_encoder_2=donor.text_encoder_2,
        tokenizer=donor.tokenizer,
        tokenizer_2=donor.tokenizer_2,
        unet=donor.unet,
        controlnet=controlnet,
        scheduler=donor.scheduler,
    )
    pipe.to("cuda")
    pipe.set_progress_bar_config(disable=True)
    return pipe


def checkpoint_slug(checkpoint_dir: Path) -> str:
    """<run>__<checkpoint-N>, ex. control_lora_v1_convergence_test__checkpoint-2000."""
    return f"{checkpoint_dir.parent.name}__{checkpoint_dir.name}"


def generate(pipe, entry: dict, seed: int, steps: int, guidance_scale: float,
             resolution: int, conditioning_scale: float) -> Image.Image:
    cond_path = DATASET_DIR / entry["conditioning_image"]
    cond_image = Image.open(cond_path).convert("RGB").resize((resolution, resolution))
    generator = torch.Generator(device="cuda").manual_seed(seed)
    result = pipe(
        prompt=entry["text"],
        image=cond_image,
        num_inference_steps=steps,
        guidance_scale=guidance_scale,
        controlnet_conditioning_scale=conditioning_scale,
        width=resolution,
        height=resolution,
        generator=generator,
    )
    return result.images[0]


def main():
    parser = argparse.ArgumentParser(
        description="Evalue visuellement un checkpoint Control-LoRA FootSegNet sur un "
                     "set fixe de 5 prompts de reference.")
    parser.add_argument("--checkpoint", required=True,
                         help="Dossier du checkpoint (ex. output/control_lora_v1_convergence_test/checkpoint-2000)")
    parser.add_argument("--baseline", action="store_true",
                         help="Genere aussi chaque image avec controlnet_conditioning_scale=0.0 "
                              "(residus zero-init -- point de comparaison sans ControlNet)")
    parser.add_argument("--n-prompts", type=int, default=len(FIXED_TEST_SET),
                         help=f"Limite le nombre de prompts testes (defaut : {len(FIXED_TEST_SET)}, essai rapide avec 1-2)")
    parser.add_argument("--steps", type=int, default=30)
    parser.add_argument("--guidance-scale", type=float, default=7.0)
    parser.add_argument("--conditioning-scale", type=float, default=1.0,
                         help="Force du conditionnement ControlNet pour le run principal (defaut 1.0)")
    parser.add_argument("--resolution", type=int, default=1024)
    parser.add_argument("--output-dir", default=str(EVAL_OUTPUT_DIR))
    args = parser.parse_args()

    checkpoint_dir = Path(args.checkpoint)
    if not checkpoint_dir.is_absolute():
        checkpoint_dir = (HERE / checkpoint_dir).resolve()
    if not checkpoint_dir.exists():
        print(f"[eval_checkpoint] Checkpoint introuvable : {checkpoint_dir}")
        sys.exit(1)

    out_dir = Path(args.output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    slug = checkpoint_slug(checkpoint_dir)

    pipe = load_pipeline(checkpoint_dir)

    test_set = FIXED_TEST_SET[: max(1, min(args.n_prompts, len(FIXED_TEST_SET)))]
    print(f"[eval_checkpoint] {len(test_set)} prompt(s) -- checkpoint={slug}")

    manifest = []
    for i, entry in enumerate(test_set):
        seed = BASE_SEED + i * 137
        print(f"[eval_checkpoint] ({i + 1}/{len(test_set)}) {entry['stem']} (seed={seed})")

        img = generate(pipe, entry, seed, args.steps, args.guidance_scale,
                        args.resolution, args.conditioning_scale)
        out_path = out_dir / f"{slug}__{entry['stem']}.png"
        img.save(out_path)
        print(f"    -> {out_path}")
        manifest.append({"stem": entry["stem"], "seed": seed, "file": out_path.name,
                          "conditioning_scale": args.conditioning_scale})

        if args.baseline:
            baseline_img = generate(pipe, entry, seed, args.steps, args.guidance_scale,
                                     args.resolution, conditioning_scale=0.0)
            baseline_path = out_dir / f"{slug}__{entry['stem']}__baseline.png"
            baseline_img.save(baseline_path)
            print(f"    -> {baseline_path}  (baseline, conditioning_scale=0.0)")
            manifest.append({"stem": entry["stem"], "seed": seed, "file": baseline_path.name,
                              "conditioning_scale": 0.0})

    manifest_path = out_dir / f"{slug}__run_manifest.json"
    manifest_path.write_text(json.dumps({
        "checkpoint": str(checkpoint_dir),
        "steps": args.steps,
        "guidance_scale": args.guidance_scale,
        "resolution": args.resolution,
        "images": manifest,
    }, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"[eval_checkpoint] Termine -- manifest -> {manifest_path}")


if __name__ == "__main__":
    main()

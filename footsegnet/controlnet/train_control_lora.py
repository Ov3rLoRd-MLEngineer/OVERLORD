# train_control_lora.py — FootSegNet -> Control-LoRA SDXL (Ov3rLoRd Pipeline)
#
# Entraîne un Control-LoRA (pas un ControlNet plein) conditionnant SDXL
# (fabricatedXL_v70) sur la carte de segmentation pied/chaussure produite par
# prepare_dataset.py. "Control-LoRA" ici = diffusers.ControlNetModel.from_unet
# (architecture copiée de l'UNet SDXL) dont SEULS sont entraînés :
#   - les adaptateurs LoRA (peft) sur les projections d'attention (to_q/to_k/
#     to_v/to_out.0) du backbone copié — c'est la partie "LoRA" (rang faible,
#     peu de paramètres, réaliste pour un dataset encore modeste)
#   - controlnet_cond_embedding (petit encodeur de la carte de conditionnement,
#     initialisé aléatoirement par from_unet — DOIT être entraîné en entier,
#     rien à adapter par LoRA sur du hasard)
#   - controlnet_down_blocks / controlnet_mid_block (les "zero-convs" du
#     ControlNet original, initialisés à zéro — DOIVENT être entraînés en
#     entier : c'est le mécanisme qui laisse le signal de conditionnement
#     s'injecter progressivement dans l'UNet gelé)
# Tout le reste (backbone copié de l'UNet, UNet lui-même, VAE, text encoders)
# reste gelé. Sauvegarde via peft (modules_to_save) : un seul adapter_model
# .safetensors, pas une copie complète du ControlNet.
#
# Le VAE utilisé est sdxl_vae.safetensors (pas taesdxl, cf. ADR-002 du
# projet) : taesdxl est un décodeur distillé pour l'aperçu temps réel dans le
# pipeline d'inférence, PAS un encodeur fiable pour produire les latents
# cibles de l'entraînement (perte de fidélité). Le fichier a été re-téléchargé
# depuis la rédaction d'ADR-002 (présent dans ComfyUI/models/vae/) ; ce choix
# ne change PAS le VAE par défaut du reste du pipeline (ADR-002 reste en
# vigueur ailleurs), seulement celui de cet entraînement.
#
# Usage :
#   py -3.12 train_control_lora.py --test-run
#       -> sous-ensemble de --test-run-size paires (100-150), peu de steps,
#          pour valider la convergence (loss qui descend, preview cohérente)
#          AVANT de lancer un run complet.
#   py -3.12 train_control_lora.py --max-train-steps 8000
#       -> run complet sur tout le dataset (manifest.jsonl ou --manifest) --
#          NE PAS lancer sans avoir validé --test-run au préalable.

import argparse
import json
import math
import random
from pathlib import Path

import torch
import torch.nn.functional as F
from PIL import Image
from torch.utils.data import Dataset, DataLoader

FOOTSEGNET_ROOT  = Path(r"D:\OVERLORD\footsegnet")
CONTROLNET_ROOT  = FOOTSEGNET_ROOT / "controlnet"
CN_DATASET_ROOT  = CONTROLNET_ROOT / "dataset"
DEFAULT_MANIFEST = CN_DATASET_ROOT / "manifest.jsonl"
DEFAULT_OUTPUT   = CONTROLNET_ROOT / "output" / "control_lora_v1"

CHECKPOINT_PATH = Path(r"D:\Ov3rLoRd AI\ComfyUI\models\checkpoints\fabricatedXL_v70.safetensors")
VAE_PATH        = Path(r"D:\Ov3rLoRd AI\ComfyUI\models\vae\sdxl_vae.safetensors")   # cf. en-tête : pas taesdxl

LORA_TARGET_MODULES = ["to_q", "to_k", "to_v", "to_out.0"]
LORA_MODULES_TO_SAVE = ["controlnet_cond_embedding", "controlnet_down_blocks", "controlnet_mid_block"]


# ── Dataset ──────────────────────────────────────────────────────────────────

class ControlLoraDataset(Dataset):
    """Paires (image, carte de segmentation) issues de prepare_dataset.py.

    Convention image de conditionnement : BLANC=pied/chaussure, NOIR=fond
    (convention ML — cf. footsegnet/README.md), normalisée en [0, 1] (PAS
    [-1, 1]) — c'est la convention attendue par ControlNetModel.controlnet_cond
    (même convention que examples/controlnet/train_controlnet_sdxl.py de
    diffusers)."""

    def __init__(self, manifest_path: Path, dataset_root: Path,
                 max_samples: int | None = None, seed: int = 42):
        entries = []
        for line in manifest_path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line:
                entries.append(json.loads(line))
        if not entries:
            raise ValueError(f"Manifest vide ou introuvable : {manifest_path}")
        if max_samples is not None and max_samples < len(entries):
            rng = random.Random(seed)
            entries = rng.sample(entries, max_samples)
        self.entries = entries
        self.dataset_root = dataset_root

    def __len__(self) -> int:
        return len(self.entries)

    def __getitem__(self, idx: int) -> dict:
        entry = self.entries[idx]
        image = Image.open(self.dataset_root / entry["file_name"]).convert("RGB")
        cond = Image.open(self.dataset_root / entry["conditioning_image"]).convert("RGB")
        if cond.size != image.size:
            cond = cond.resize(image.size, Image.NEAREST)   # masque = pas d'interpolation floue

        import numpy as np
        pixel_values = torch.from_numpy(np.array(image)).permute(2, 0, 1).float() / 127.5 - 1.0
        cond_values = torch.from_numpy(np.array(cond)).permute(2, 0, 1).float() / 255.0

        return {
            "pixel_values": pixel_values,
            "conditioning_pixel_values": cond_values,
            "text": entry.get("text", ""),
            "width": image.width,
            "height": image.height,
        }


def collate_fn(batch: list[dict]) -> dict:
    return {
        "pixel_values": torch.stack([b["pixel_values"] for b in batch]),
        "conditioning_pixel_values": torch.stack([b["conditioning_pixel_values"] for b in batch]),
        "text": [b["text"] for b in batch],
        "width": [b["width"] for b in batch],
        "height": [b["height"] for b in batch],
    }


# ── Encodage texte SDXL (double tokenizer/text encoder) ─────────────────────

def encode_prompt(text_list: list[str], tokenizers, text_encoders, device) -> tuple[torch.Tensor, torch.Tensor]:
    """Reprend la convention SDXL standard : concatène les hidden_states
    avant-dernière couche des deux text encoders ; pooled_embeds = sortie
    poolée du 2e text encoder (text_encoder_2, avec projection)."""
    prompt_embeds_list = []
    pooled_prompt_embeds = None
    for tokenizer, text_encoder in zip(tokenizers, text_encoders):
        inputs = tokenizer(text_list, padding="max_length", max_length=tokenizer.model_max_length,
                            truncation=True, return_tensors="pt").input_ids.to(device)
        outputs = text_encoder(inputs, output_hidden_states=True)
        pooled_prompt_embeds = outputs[0]            # pooler_output du dernier encoder itéré
        prompt_embeds_list.append(outputs.hidden_states[-2])
    prompt_embeds = torch.cat(prompt_embeds_list, dim=-1)
    return prompt_embeds, pooled_prompt_embeds


def compute_time_ids(height: int, width: int, device, dtype) -> torch.Tensor:
    """add_time_ids SDXL : (original_size, crops_coords_top_left, target_size) —
    pas de crop appliqué ici (image entière), donc original == target, crop (0, 0)."""
    add_time_ids = list((height, width) + (0, 0) + (height, width))
    return torch.tensor([add_time_ids], device=device, dtype=dtype)


# ── Modèle ────────────────────────────────────────────────────────────────────

def build_models(weight_dtype: torch.dtype, lora_rank: int):
    from diffusers import StableDiffusionXLPipeline, ControlNetModel, AutoencoderKL
    from peft import LoraConfig, get_peft_model

    if not CHECKPOINT_PATH.exists():
        raise FileNotFoundError(f"Checkpoint SDXL introuvable : {CHECKPOINT_PATH}")

    print(f"[train_control_lora] Chargement checkpoint SDXL : {CHECKPOINT_PATH.name}")
    pipe = StableDiffusionXLPipeline.from_single_file(
        str(CHECKPOINT_PATH), torch_dtype=weight_dtype, use_safetensors=True,
    )
    tokenizer, tokenizer_2 = pipe.tokenizer, pipe.tokenizer_2
    text_encoder, text_encoder_2 = pipe.text_encoder, pipe.text_encoder_2
    unet = pipe.unet
    noise_scheduler = pipe.scheduler

    if VAE_PATH.exists():
        print(f"[train_control_lora] VAE dédié (pas taesdxl) : {VAE_PATH.name}")
        vae = AutoencoderKL.from_single_file(str(VAE_PATH), torch_dtype=torch.float32)
    else:
        print(f"[train_control_lora] WARN : {VAE_PATH} introuvable — repli sur le VAE "
              f"embarqué dans le checkpoint (peut être de moindre qualité, cf. ADR-002)")
        vae = pipe.vae
    del pipe

    print("[train_control_lora] Construction ControlNetModel depuis l'UNet SDXL...")
    controlnet = ControlNetModel.from_unet(unet)

    text_encoder.requires_grad_(False)
    text_encoder_2.requires_grad_(False)
    vae.requires_grad_(False)
    unet.requires_grad_(False)
    unet.enable_gradient_checkpointing()
    controlnet.enable_gradient_checkpointing()

    # peft.modules_to_save ne sait pas wrapper un nn.ModuleList directement
    # (pas de forward() propre) : controlnet_down_blocks est un ModuleList de
    # zero-convs, il faut donc lister chaque sous-module indexé individuellement.
    modules_to_save = []
    for name in LORA_MODULES_TO_SAVE:
        submodule = getattr(controlnet, name)
        if isinstance(submodule, torch.nn.ModuleList):
            modules_to_save.extend(f"{name}.{i}" for i in range(len(submodule)))
        else:
            modules_to_save.append(name)

    lora_config = LoraConfig(
        r=lora_rank, lora_alpha=lora_rank, lora_dropout=0.0,
        target_modules=LORA_TARGET_MODULES,
        modules_to_save=modules_to_save,
    )
    controlnet = get_peft_model(controlnet, lora_config)
    controlnet.print_trainable_parameters()

    return {
        "tokenizer": tokenizer, "tokenizer_2": tokenizer_2,
        "text_encoder": text_encoder, "text_encoder_2": text_encoder_2,
        "vae": vae, "unet": unet, "controlnet": controlnet,
        "noise_scheduler": noise_scheduler,
    }


# ── Validation (preview visuelle de convergence) ─────────────────────────────

@torch.no_grad()
def run_validation(models, sample: dict, device, weight_dtype, output_dir: Path, step: int) -> None:
    """Débruitage complet (DDIM-like via le scheduler configuré) d'UNE paire
    d'entraînement, pour vérifier visuellement la cohérence de sortie —
    PAS une métrique quantitative, juste un contrôle qualité humain."""
    controlnet, unet, vae = models["controlnet"], models["unet"], models["vae"]
    noise_scheduler = models["noise_scheduler"]
    was_training = controlnet.training
    controlnet.eval()

    cond = sample["conditioning_pixel_values"].unsqueeze(0).to(device, dtype=weight_dtype)
    height, width = sample["height"], sample["width"]
    prompt_embeds, pooled = encode_prompt(
        [sample["text"]], [models["tokenizer"], models["tokenizer_2"]],
        [models["text_encoder"], models["text_encoder_2"]], device,
    )
    prompt_embeds, pooled = prompt_embeds.to(weight_dtype), pooled.to(weight_dtype)
    add_time_ids = compute_time_ids(height, width, device, weight_dtype)
    added_cond_kwargs = {"text_embeds": pooled, "time_ids": add_time_ids}

    latents = torch.randn(
        (1, unet.config.in_channels, height // 8, width // 8), device=device, dtype=weight_dtype,
    )
    noise_scheduler.set_timesteps(30, device=device)
    latents = latents * noise_scheduler.init_noise_sigma

    for t in noise_scheduler.timesteps:
        latent_in = noise_scheduler.scale_model_input(latents, t)
        down_res, mid_res = controlnet(
            latent_in, t, encoder_hidden_states=prompt_embeds, controlnet_cond=cond,
            added_cond_kwargs=added_cond_kwargs, return_dict=False,
        )
        # cf. commentaire équivalent dans train() : accelerator.prepare(controlnet)
        # reconvertit sa sortie en fp32, incompatible avec l'UNet resté en bf16.
        down_res = [s.to(dtype=weight_dtype) for s in down_res]
        mid_res = mid_res.to(dtype=weight_dtype)
        noise_pred = unet(
            latent_in, t, encoder_hidden_states=prompt_embeds, added_cond_kwargs=added_cond_kwargs,
            down_block_additional_residuals=down_res, mid_block_additional_residual=mid_res,
        ).sample
        latents = noise_scheduler.step(noise_pred, t, latents).prev_sample

    image = vae.decode(latents.float() / vae.config.scaling_factor, return_dict=False)[0]
    image = (image / 2 + 0.5).clamp(0, 1).cpu().permute(0, 2, 3, 1).numpy()[0]

    import numpy as np
    out_img = Image.fromarray((image * 255).astype(np.uint8))
    val_dir = output_dir / "validation"
    val_dir.mkdir(parents=True, exist_ok=True)
    out_img.save(val_dir / f"step_{step:06d}.png")
    print(f"[train_control_lora] Preview de convergence -> {val_dir / f'step_{step:06d}.png'}")

    if was_training:
        controlnet.train()


# ── Boucle d'entraînement ─────────────────────────────────────────────────────

def train(args: argparse.Namespace) -> None:
    from accelerate import Accelerator
    from accelerate.utils import set_seed

    if args.seed is not None:
        set_seed(args.seed)

    accelerator = Accelerator(
        gradient_accumulation_steps=args.gradient_accumulation_steps,
        mixed_precision=args.mixed_precision,
    )
    device = accelerator.device
    weight_dtype = {"no": torch.float32, "fp16": torch.float16, "bf16": torch.bfloat16}[args.mixed_precision]

    manifest_path = Path(args.manifest)
    max_samples = args.test_run_size if args.test_run else args.max_samples
    dataset = ControlLoraDataset(manifest_path, CN_DATASET_ROOT, max_samples=max_samples, seed=args.seed or 42)
    print(f"[train_control_lora] Dataset : {len(dataset)} paire(s) "
          f"({'--test-run' if args.test_run else 'run complet'})")

    dataloader = DataLoader(
        dataset, batch_size=args.batch_size, shuffle=True,
        collate_fn=collate_fn, num_workers=args.num_workers,
    )

    models = build_models(weight_dtype, args.lora_rank)
    controlnet, unet, vae = models["controlnet"], models["unet"], models["vae"]
    text_encoder, text_encoder_2 = models["text_encoder"], models["text_encoder_2"]
    tokenizer, tokenizer_2 = models["tokenizer"], models["tokenizer_2"]
    noise_scheduler = models["noise_scheduler"]

    unet.to(device, dtype=weight_dtype)
    text_encoder.to(device, dtype=weight_dtype)
    text_encoder_2.to(device, dtype=weight_dtype)
    vae.to(device, dtype=torch.float32)   # VAE en fp32 (stabilité numérique standard SDXL)
    vae.enable_tiling()   # sans ça, l'encode fp32 d'images 1024x1536 sature 16GB de VRAM (OOM confirmé)

    trainable_params = [p for p in controlnet.parameters() if p.requires_grad]
    n_trainable = sum(p.numel() for p in trainable_params)
    print(f"[train_control_lora] Paramètres entraînables : {n_trainable:,}")

    if args.use_8bit_adam:
        import bitsandbytes as bnb
        optimizer_cls = bnb.optim.AdamW8bit
    else:
        optimizer_cls = torch.optim.AdamW
    optimizer = optimizer_cls(trainable_params, lr=args.learning_rate)

    max_train_steps = args.max_train_steps or (
        math.ceil(len(dataset) / args.batch_size) * args.num_epochs
    )

    controlnet, optimizer, dataloader = accelerator.prepare(controlnet, optimizer, dataloader)

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    val_sample = dataset[0]   # échantillon fixe pour comparer les previews au fil de l'entraînement

    global_step = 0
    running_loss = 0.0
    controlnet.train()
    print(f"[train_control_lora] Démarrage : {max_train_steps} steps, "
          f"batch_size={args.batch_size}, lr={args.learning_rate}, rank={args.lora_rank}")

    while global_step < max_train_steps:
        for batch in dataloader:
            with accelerator.accumulate(controlnet):
                pixel_values = batch["pixel_values"].to(device, dtype=torch.float32)
                cond_values = batch["conditioning_pixel_values"].to(device, dtype=weight_dtype)

                latents = vae.encode(pixel_values).latent_dist.sample()
                latents = latents * vae.config.scaling_factor
                latents = latents.to(weight_dtype)

                noise = torch.randn_like(latents)
                bsz = latents.shape[0]
                timesteps = torch.randint(
                    0, noise_scheduler.config.num_train_timesteps, (bsz,), device=device,
                ).long()
                noisy_latents = noise_scheduler.add_noise(latents, noise, timesteps)

                prompt_embeds, pooled_embeds = encode_prompt(
                    batch["text"], [tokenizer, tokenizer_2], [text_encoder, text_encoder_2], device,
                )
                prompt_embeds, pooled_embeds = prompt_embeds.to(weight_dtype), pooled_embeds.to(weight_dtype)
                add_time_ids = torch.cat([
                    compute_time_ids(h, w, device, weight_dtype)
                    for h, w in zip(batch["height"], batch["width"])
                ])
                added_cond_kwargs = {"text_embeds": pooled_embeds, "time_ids": add_time_ids}

                down_block_res_samples, mid_block_res_sample = controlnet(
                    noisy_latents, timesteps, encoder_hidden_states=prompt_embeds,
                    controlnet_cond=cond_values, added_cond_kwargs=added_cond_kwargs,
                    return_dict=False,
                )
                # accelerator.prepare(controlnet) enveloppe son forward dans l'autocast
                # bf16 d'Accelerate, qui reconvertit systématiquement la sortie en fp32
                # (accelerate.utils.operations.convert_to_fp32) -- l'UNet, lui, est casté
                # bf16 à la main sans passer par prepare(). Sans ce recast, les résidus
                # fp32 provoquent "Mixed dtype: expect parameter to have scalar type of
                # Float" au premier GroupNorm de l'UNet rencontré (confirmé en test-run).
                down_block_res_samples = [s.to(dtype=weight_dtype) for s in down_block_res_samples]
                mid_block_res_sample = mid_block_res_sample.to(dtype=weight_dtype)
                model_pred = unet(
                    noisy_latents, timesteps, encoder_hidden_states=prompt_embeds,
                    added_cond_kwargs=added_cond_kwargs,
                    down_block_additional_residuals=down_block_res_samples,
                    mid_block_additional_residual=mid_block_res_sample,
                ).sample

                loss = F.mse_loss(model_pred.float(), noise.float(), reduction="mean")
                accelerator.backward(loss)
                if accelerator.sync_gradients:
                    accelerator.clip_grad_norm_(trainable_params, 1.0)
                optimizer.step()
                optimizer.zero_grad()

            if accelerator.sync_gradients:
                global_step += 1
                running_loss += loss.detach().item()

                if global_step % args.log_every == 0:
                    avg_loss = running_loss / args.log_every
                    print(f"[train_control_lora] step {global_step}/{max_train_steps}  loss={avg_loss:.4f}")
                    running_loss = 0.0

                if args.validation_steps and global_step % args.validation_steps == 0 and accelerator.is_main_process:
                    run_validation(models, val_sample, device, weight_dtype, output_dir, global_step)

                if args.checkpointing_steps and global_step % args.checkpointing_steps == 0 and accelerator.is_main_process:
                    ckpt_dir = output_dir / f"checkpoint-{global_step}"
                    accelerator.unwrap_model(controlnet).save_pretrained(ckpt_dir)
                    print(f"[train_control_lora] Checkpoint -> {ckpt_dir}")

                if global_step >= max_train_steps:
                    break

    if accelerator.is_main_process:
        accelerator.unwrap_model(controlnet).save_pretrained(output_dir / "final")
        print(f"[train_control_lora] Terminé -> {output_dir / 'final'}")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="FootSegNet -> Control-LoRA SDXL : entraînement (diffusers + peft)"
    )
    parser.add_argument("--manifest", default=str(DEFAULT_MANIFEST),
                        help="Manifest JSONL (défaut : dataset\\manifest.jsonl — "
                             "utiliser manifest_filtered.jsonl après quality_sort.py --write-manifest)")
    parser.add_argument("--output-dir", default=str(DEFAULT_OUTPUT))
    parser.add_argument("--test-run", action="store_true",
                        help="Sous-ensemble réduit (--test-run-size) + peu de steps, "
                             "pour valider la convergence avant un run complet")
    parser.add_argument("--test-run-size", type=int, default=120,
                        help="Nombre de paires en mode --test-run (défaut: 120, plage 100-150)")
    parser.add_argument("--max-samples", type=int, default=None,
                        help="Limite le dataset complet à N paires (hors --test-run)")
    parser.add_argument("--lora-rank", type=int, default=64)
    parser.add_argument("--learning-rate", type=float, default=1e-4)
    parser.add_argument("--batch-size", type=int, default=1)
    parser.add_argument("--gradient-accumulation-steps", type=int, default=4)
    parser.add_argument("--num-epochs", type=int, default=10,
                        help="Utilisé pour dériver max-train-steps si --max-train-steps est absent")
    parser.add_argument("--max-train-steps", type=int, default=None,
                        help="Nombre total de steps d'optimisation (prioritaire sur --num-epochs). "
                             "REQUIS hors --test-run (pas de défaut de run complet implicite).")
    parser.add_argument("--mixed-precision", choices=["no", "fp16", "bf16"], default="bf16")
    parser.add_argument("--use-8bit-adam", action="store_true", default=True)
    parser.add_argument("--no-8bit-adam", dest="use_8bit_adam", action="store_false")
    parser.add_argument("--num-workers", type=int, default=2)
    parser.add_argument("--log-every", type=int, default=10)
    parser.add_argument("--validation-steps", type=int, default=50)
    parser.add_argument("--checkpointing-steps", type=int, default=200)
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args()

    if not args.test_run and args.max_train_steps is None:
        parser.error(
            "--max-train-steps est requis pour un run complet (hors --test-run) — "
            "pas de défaut implicite pour éviter un lancement accidentel d'un run long."
        )
    return args


if __name__ == "__main__":
    train(parse_args())

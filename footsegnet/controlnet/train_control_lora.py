# ██████╗ ██╗   ██╗██████╗ ██████╗ ██╗      ██████╗ ██████╗ ██████╗
# ██╔═══██╗██║   ██║╚════██╗██╔══██╗██║     ██╔═══██╗██╔══██╗██╔══██╗
# ██║   ██║██║   ██║ █████╔╝██████╔╝██║     ██║   ██║██████╔╝██║  ██║
# ██║   ██║╚██╗ ██╔╝ ╚═══██╗██╔══██╗██║     ██║   ██║██╔══██╗██║  ██║
# ╚██████╔╝ ╚████╔╝ ██████╔╝██║  ██║███████╗╚██████╔╝██║  ██║██████╔╝
# ╚═════╝   ╚═══╝  ╚═════╝ ╚═╝  ╚═╝╚══════╝ ╚═════╝ ╚═╝  ╚═╝╚═════╝
# Ov3rLoRd -- pipeline de production anime autonome (ComfyUI)
# https://github.com/Ov3rLoRd-MLEngineer
#
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

import sys
_REPO_ROOT = Path(__file__).resolve().parent.parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))
import config

FOOTSEGNET_ROOT  = config.FOOTSEGNET_ROOT
CONTROLNET_ROOT  = FOOTSEGNET_ROOT / "controlnet"
CN_DATASET_ROOT  = CONTROLNET_ROOT / "dataset"
DEFAULT_MANIFEST = CN_DATASET_ROOT / "manifest.jsonl"
DEFAULT_OUTPUT   = CONTROLNET_ROOT / "output" / "control_lora_v1"

CHECKPOINT_PATH = config.CHECKPOINTS_DIR / "fabricatedXL_v70.safetensors"
VAE_PATH        = config.COMFYUI_MODELS / "vae" / "sdxl_vae.safetensors"   # cf. en-tête : pas taesdxl

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

def _expand_modules_to_save(model, names: list[str]) -> list[str]:
    """peft ne peut pas envelopper un nn.ModuleList/ModuleDict avec modules_to_save
    (voir peft.utils.other.AuxiliaryTrainingWrapper.check_module) : `controlnet_down_blocks`
    est un ModuleList de convolutions zero-init individuelles. On l'éclate en ses
    enfants nommés (des nn.Conv2d, des feuilles valides) ; les autres noms (modules
    déjà feuille ou simplement non-ModuleList) sont laissés tels quels."""
    named = dict(model.named_modules())
    expanded = []
    for name in names:
        submodule = named.get(name)
        if isinstance(submodule, (torch.nn.ModuleList, torch.nn.ModuleDict)):
            expanded.extend(f"{name}.{child_name}" for child_name, _ in submodule.named_children())
        else:
            expanded.append(name)
    return expanded


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
    # scheduler DÉDIÉ à run_validation() : EulerDiscreteScheduler est stateful
    # (set_timesteps() réécrit self.timesteps sur l'objet). Si run_validation()
    # appelait set_timesteps(30, ...) sur noise_scheduler ci-dessus (le même
    # objet utilisé par add_noise() dans la boucle d'entraînement), self.timesteps
    # se retrouvait tronqué aux 30 valeurs d'inférence -> IndexError au step
    # d'entraînement suivant (timestep introuvable dans la liste réduite).
    val_scheduler = type(noise_scheduler).from_config(noise_scheduler.config)

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

    lora_config = LoraConfig(
        r=lora_rank, lora_alpha=lora_rank, lora_dropout=0.0,
        target_modules=LORA_TARGET_MODULES,
        modules_to_save=_expand_modules_to_save(controlnet, LORA_MODULES_TO_SAVE),
    )
    controlnet = get_peft_model(controlnet, lora_config)
    controlnet.print_trainable_parameters()

    return {
        "tokenizer": tokenizer, "tokenizer_2": tokenizer_2,
        "text_encoder": text_encoder, "text_encoder_2": text_encoder_2,
        "vae": vae, "unet": unet, "controlnet": controlnet,
        "noise_scheduler": noise_scheduler, "val_scheduler": val_scheduler,
    }


# ── Validation (preview visuelle de convergence) ─────────────────────────────

@torch.no_grad()
def run_validation(models, sample: dict, device, weight_dtype, output_dir: Path, step: int) -> None:
    """Débruitage complet (DDIM-like via le scheduler configuré) d'UNE paire
    d'entraînement, pour vérifier visuellement la cohérence de sortie —
    PAS une métrique quantitative, juste un contrôle qualité humain."""
    controlnet, unet, vae = models["controlnet"], models["unet"], models["vae"]
    noise_scheduler = models["val_scheduler"]   # copie dédiée -- ne JAMAIS réutiliser
                                                 # models["noise_scheduler"] ici (stateful, cf. build_models)
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
        down_res = [s.to(dtype=weight_dtype) for s in down_res]   # cf. commentaire dans train()
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


def _resolve_checkpoint_dir(output_dir: Path, resume_arg: str) -> Path:
    if resume_arg != "latest":
        ckpt_dir = Path(resume_arg)
        if not ckpt_dir.exists():
            raise FileNotFoundError(f"--resume-from-checkpoint introuvable : {ckpt_dir}")
        return ckpt_dir
    candidates = sorted(
        output_dir.glob("checkpoint-*"),
        key=lambda p: int(p.name.split("-")[-1]),
    )
    if not candidates:
        raise FileNotFoundError(f"--resume-from-checkpoint latest : aucun checkpoint-* dans {output_dir}")
    return candidates[-1]


def _load_checkpoint(controlnet, output_dir: Path, resume_arg: str) -> int:
    """Recharge les poids peft (LoRA + modules_to_save) d'un checkpoint sauvé par
    save_pretrained() dans la boucle d'entraînement, et reprend le compteur de
    steps depuis le nom du dossier (checkpoint-500 -> global_step=500).

    Limitation acceptée : l'état de l'optimiseur (moments Adam) n'est pas
    sauvegardé par save_pretrained()/ce script, donc il redémarre à zéro après
    un resume -- pas bloquant pour reprendre un entraînement interrompu, juste
    quelques steps de moins bonne convergence que si l'optimiseur avait été
    préservé."""
    from peft import set_peft_model_state_dict
    from safetensors.torch import load_file

    ckpt_dir = _resolve_checkpoint_dir(output_dir, resume_arg)
    weights_path = ckpt_dir / "adapter_model.safetensors"
    if not weights_path.exists():
        raise FileNotFoundError(f"adapter_model.safetensors introuvable dans {ckpt_dir}")

    state_dict = load_file(str(weights_path))
    set_peft_model_state_dict(controlnet, state_dict)
    global_step = int(ckpt_dir.name.split("-")[-1])
    print(f"[train_control_lora] Reprise depuis {ckpt_dir} -> global_step={global_step} "
          f"(etat optimiseur reinitialise, cf. limitation connue)")
    return global_step


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
    vae.enable_tiling()   # encode par tuiles spatiales -- l'encodeur VAE en fp32 pleine
                           # résolution est le pic mémoire du forward, pas l'UNet/ControlNet
                           # (RTX 5080 16GB : SDXL UNet + 2 text encoders + ControlNet+LoRA
                           # laissent peu de marge, cf. OOM observé sans ceci)

    # LR distinct pour les modules_to_save (controlnet_cond_embedding, down_blocks,
    # mid_block -- des "zero convolutions" pleine-resolution parties de zero-init)
    # vs les deltas LoRA (ajustement fin de poids deja pre-entraines). Diagnostic
    # du 2026-07-25 : un LR unique (1e-4) fait exploser les residus des
    # modules_to_save des le premier checkpoint (std ~35-58 vs 0 en zero-init,
    # deja mauvais a step 500, pas une derive progressive) -- les zero-convs du
    # ControlNet original sont concues pour croitre lentement, pas pour un LR
    # plus eleve. modules_to_save passe donc a un LR ~10x plus bas (pratique
    # standard ControlNet ~1e-5), LoRA garde le LR "learning-rate" habituel.
    lora_params = [p for n, p in controlnet.named_parameters() if p.requires_grad and "lora_" in n.lower()]
    mts_params = [p for n, p in controlnet.named_parameters() if p.requires_grad and "lora_" not in n.lower()]
    trainable_params = lora_params + mts_params
    n_trainable = sum(p.numel() for p in trainable_params)
    print(f"[train_control_lora] Paramètres entraînables : {n_trainable:,} "
          f"(LoRA={sum(p.numel() for p in lora_params):,} @ lr={args.learning_rate}, "
          f"modules_to_save={sum(p.numel() for p in mts_params):,} @ lr={args.modules_to_save_lr})")

    if args.use_8bit_adam:
        import bitsandbytes as bnb
        optimizer_cls = bnb.optim.AdamW8bit
    else:
        optimizer_cls = torch.optim.AdamW
    optimizer = optimizer_cls([
        {"params": lora_params, "lr": args.learning_rate},
        {"params": mts_params, "lr": args.modules_to_save_lr},
    ])

    max_train_steps = args.max_train_steps or (
        math.ceil(len(dataset) / args.batch_size) * args.num_epochs
    )

    controlnet, optimizer, dataloader = accelerator.prepare(controlnet, optimizer, dataloader)

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    val_sample = dataset[0]   # échantillon fixe pour comparer les previews au fil de l'entraînement

    global_step = 0
    if args.resume_from_checkpoint:
        global_step = _load_checkpoint(accelerator.unwrap_model(controlnet), Path(args.output_dir), args.resume_from_checkpoint)
    running_loss = 0.0
    running_mse = 0.0
    running_reg = 0.0
    controlnet.train()
    print(f"[train_control_lora] Démarrage : {max_train_steps} steps, "
          f"batch_size={args.batch_size}, lr={args.learning_rate}, rank={args.lora_rank}")

    while global_step < max_train_steps:
        for batch in dataloader:
            with accelerator.accumulate(controlnet):
                pixel_values = batch["pixel_values"].to(device, dtype=torch.float32)
                cond_values = batch["conditioning_pixel_values"].to(device, dtype=weight_dtype)

                with torch.no_grad():
                    latents = vae.encode(pixel_values).latent_dist.sample()
                    latents = latents * vae.config.scaling_factor
                latents = latents.to(weight_dtype)

                noise = torch.randn_like(latents)
                bsz = latents.shape[0]
                timesteps = torch.randint(
                    0, noise_scheduler.config.num_train_timesteps, (bsz,), device=device,
                ).long()
                noisy_latents = noise_scheduler.add_noise(latents, noise, timesteps)

                with torch.no_grad():
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
                # controlnet passe par accelerator.prepare() (autocast) alors que l'unet
                # gelé est casté manuellement en weight_dtype (pas prepare()) -- sans ce
                # cast explicite, les résidus (parfois remontés en fp32 par l'autocast,
                # cf. GroupNorm sur la liste "garder en fp32" de torch.autocast) et les
                # activations bf16 de l'unet se mélangent -> RuntimeError mixed dtype.
                down_block_res_samples = [s.to(dtype=weight_dtype) for s in down_block_res_samples]
                mid_block_res_sample = mid_block_res_sample.to(dtype=weight_dtype)
                model_pred = unet(
                    noisy_latents, timesteps, encoder_hidden_states=prompt_embeds,
                    added_cond_kwargs=added_cond_kwargs,
                    down_block_additional_residuals=down_block_res_samples,
                    mid_block_additional_residual=mid_block_res_sample,
                ).sample

                if args.mask_loss_weight != 1.0:
                    # Correctif candidat (non valide) -- cf. DIAGNOSTIC_MODE_COLLAPSE_20260728.md :
                    # la MSE non ponderee ne recompense pas le fait que le residu ControlNet
                    # depende du contenu du masque (masque pied/chaussure tres eparse, 1-8% du
                    # cadre -- son gradient est marginal face au reste de l'image). On sur-pondere
                    # ici l'erreur de reconstruction precisement la ou le masque le designe
                    # (redimensionne a la resolution latente, sans interpolation floue) pour forcer
                    # le modele a "lire" le masque plutot qu'apprendre un motif moyen generique.
                    mask_latent = F.interpolate(
                        cond_values.mean(dim=1, keepdim=True).float(),
                        size=noisy_latents.shape[-2:], mode="nearest",
                    )
                    weight_map = 1.0 + (args.mask_loss_weight - 1.0) * mask_latent
                    mse_loss = ((model_pred.float() - noise.float()) ** 2 * weight_map).mean()
                else:
                    mse_loss = F.mse_loss(model_pred.float(), noise.float(), reduction="mean")
                # Regularisation explicite sur la norme des residus ControlNet : diagnostic
                # 2026-07-25 a montre que ni un LR bas (1e-5/1e-6) ni un clip de gradient
                # serre (0.1) sur les modules_to_save n'empechent leur explosion -- la loss
                # MSE seule recompense structurellement des residus de grande magnitude,
                # quel que soit le rythme auquel on les y laisse arriver. Penalise donc
                # directement la magnitude (norme L2 moyenne) des residus eux-memes.
                reg_loss = sum(r.float().pow(2).mean() for r in down_block_res_samples) \
                    + mid_block_res_sample.float().pow(2).mean()
                loss = mse_loss + args.reg_weight * reg_loss
                accelerator.backward(loss)
                if accelerator.sync_gradients:
                    # Clip separe : un clip global sur trainable_params (LoRA+modules_to_save
                    # combines, 53M/19M params) dilue l'effet sur les modules_to_save (36
                    # tenseurs) face aux 544 tenseurs LoRA -- la norme combinee est rarement
                    # dominee par le petit groupe. Clip modules_to_save nettement plus serre
                    # (zero-convs zero-init, cf. diagnostic 2026-07-25 : explosion des residus
                    # deja a step 50-150 malgre LR reduit).
                    accelerator.clip_grad_norm_(lora_params, 1.0)
                    accelerator.clip_grad_norm_(mts_params, args.modules_to_save_clip_norm)
                optimizer.step()
                optimizer.zero_grad()

            if accelerator.sync_gradients:
                global_step += 1
                running_loss += loss.detach().item()
                running_mse += mse_loss.detach().item()
                running_reg += reg_loss.detach().item()

                if global_step % args.log_every == 0:
                    avg_loss = running_loss / args.log_every
                    avg_mse = running_mse / args.log_every
                    avg_reg = running_reg / args.log_every
                    print(f"[train_control_lora] step {global_step}/{max_train_steps}  "
                          f"loss={avg_loss:.4f} (mse={avg_mse:.4f}, reg={avg_reg:.2f}, "
                          f"reg*w={args.reg_weight * avg_reg:.4f})")
                    running_loss = 0.0
                    running_mse = 0.0
                    running_reg = 0.0

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
    parser.add_argument("--learning-rate", type=float, default=1e-4,
                        help="LR pour les deltas LoRA (ajustement de poids pre-entraines)")
    parser.add_argument("--modules-to-save-lr", type=float, default=1e-5,
                        help="LR pour les modules_to_save (zero-convs pleine-resolution, "
                             "partent de zero-init -- doit rester bas, pas eleve, cf. "
                             "diagnostic 2026-07-25 : explosion des residus a 1e-4)")
    parser.add_argument("--modules-to-save-clip-norm", type=float, default=1.0,
                        help="Clip de norme de gradient DEDIE aux modules_to_save (separe "
                             "du clip LoRA a 1.0) -- diagnostic 2026-07-25 : un clip serre "
                             "(0.1) seul aggrave l'explosion des residus, defaut remonte a "
                             "1.0 (= pas de restriction supplementaire vs le clip LoRA)")
    parser.add_argument("--reg-weight", type=float, default=0.0,
                        help="Poids de la regularisation L2 sur la norme des residus "
                             "ControlNet (down_block_res_samples + mid_block_res_sample) -- "
                             "0.0 = desactivee. Diagnostic 2026-07-25 : ni LR bas ni clip "
                             "serre n'empechent l'explosion des residus, cette regularisation "
                             "cible directement la magnitude plutot que la vitesse d'y arriver.")
    parser.add_argument("--mask-loss-weight", type=float, default=1.0,
                        help="[CORRECTIF CANDIDAT, NON VALIDE -- cf. DIAGNOSTIC_MODE_COLLAPSE_20260728.md] "
                             "Poids multiplicateur de la MSE dans la zone du masque de conditionnement "
                             "(resize nearest a la resolution latente). 1.0 = desactive, comportement "
                             "identique a avant ce correctif. Piste pour le mode collapse observe : "
                             "sur-ponderer l'erreur de reconstruction sous le masque force le modele a "
                             "le lire plutot qu'apprendre un residu generique independant du conditionnement.")
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
    parser.add_argument("--resume-from-checkpoint", default=None,
                        help="Reprend l'entraînement depuis un checkpoint sauvé par "
                             "--checkpointing-steps : chemin d'un dossier checkpoint-N, ou "
                             "'latest' pour le plus récent trouvé dans --output-dir. "
                             "Recharge les poids peft (LoRA + modules_to_save) et reprend "
                             "global_step à N ; l'état de l'optimiseur repart de zéro.")
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

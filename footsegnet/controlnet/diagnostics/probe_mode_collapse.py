"""Diagnostic Control-LoRA : sonde de mode collapse du conditionnement.

Charge un checkpoint peft (LoRA + modules_to_save) et calcule, pour un petit
jeu d'echantillons du dataset choisis pour etre tres differents les uns des
autres (indices espaces dans manifest_filtered.jsonl), la correlation de
Pearson croisee entre les composantes SPATIALES (residu - moyenne par canal)
du mid_block_res_sample produit par le ControlNet.

Si cette correlation reste tres elevee (> 0.9) malgre des images de
conditionnement tres differentes, le ControlNet produit un residu
quasi independant du conditionnement -> mode collapse (cf. rapport
DIAGNOSTIC_MODE_COLLAPSE_20260728.md pour l'analyse complete et la preuve
que les masques bruts correspondants, eux, ne sont PAS correles).

Usage :
    py -3.12 diagnostics/probe_mode_collapse.py <chemin_checkpoint>
    py -3.12 diagnostics/probe_mode_collapse.py output/control_lora_v1/checkpoint-2000
"""

import sys
from pathlib import Path

import numpy as np
import torch
from diffusers import ControlNetModel
from peft import LoraConfig, get_peft_model

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import train_control_lora as tcl

SAMPLE_INDICES = [0, 100, 200, 300, 400]


def spatial_only(r: torch.Tensor) -> torch.Tensor:
    return r - r.mean(dim=(2, 3), keepdim=True)


def main() -> None:
    if len(sys.argv) != 2:
        print(f"Usage: {sys.argv[0]} <checkpoint_dir>")
        sys.exit(1)
    checkpoint = sys.argv[1]

    weight_dtype = torch.bfloat16
    device = "cuda"

    models = tcl.build_models(weight_dtype, lora_rank=64)
    unet = models["unet"]
    text_encoder, text_encoder_2 = models["text_encoder"], models["text_encoder_2"]
    unet.to(device, dtype=weight_dtype)
    text_encoder.to(device, dtype=weight_dtype)
    text_encoder_2.to(device, dtype=weight_dtype)

    dataset = tcl.ControlLoraDataset(Path("dataset/manifest_filtered.jsonl"), tcl.CN_DATASET_ROOT, max_samples=None)
    fixed_text = dataset.entries[0]["text"]
    prompt_embeds, pooled = tcl.encode_prompt(
        [fixed_text], [models["tokenizer"], models["tokenizer_2"]], [text_encoder, text_encoder_2], device,
    )
    prompt_embeds, pooled = prompt_embeds.to(weight_dtype), pooled.to(weight_dtype)

    cn = ControlNetModel.from_unet(unet)
    lora_config = LoraConfig(
        r=64, lora_alpha=64, lora_dropout=0.0,
        target_modules=tcl.LORA_TARGET_MODULES,
        modules_to_save=tcl._expand_modules_to_save(cn, tcl.LORA_MODULES_TO_SAVE),
    )
    cn = get_peft_model(cn, lora_config).to(device, dtype=weight_dtype)
    global_step = tcl._load_checkpoint(cn, tcl.DEFAULT_OUTPUT, checkpoint)
    cn.eval()

    maps = {}
    for idx in SAMPLE_INDICES:
        sample = dataset[idx]
        height, width = sample["height"], sample["width"]
        cond = sample["conditioning_pixel_values"].unsqueeze(0).to(device, dtype=weight_dtype)
        add_time_ids = tcl.compute_time_ids(height, width, device, weight_dtype)
        added_cond_kwargs = {"text_embeds": pooled, "time_ids": add_time_ids}

        noise_scheduler = type(models["noise_scheduler"]).from_config(models["noise_scheduler"].config)
        noise_scheduler.set_timesteps(30, device=device)
        torch.manual_seed(42)   # meme bruit initial pour tous les echantillons -- seul cond varie
        latents0 = torch.randn((1, unet.config.in_channels, height // 8, width // 8), device=device, dtype=weight_dtype)
        latents0 = latents0 * noise_scheduler.init_noise_sigma
        t0 = noise_scheduler.timesteps[0]
        latent_in0 = noise_scheduler.scale_model_input(latents0, t0)

        with torch.no_grad():
            _, mid_res = cn(
                latent_in0, t0, encoder_hidden_states=prompt_embeds, controlnet_cond=cond,
                added_cond_kwargs=added_cond_kwargs, return_dict=False,
            )
        maps[idx] = spatial_only(mid_res.float()).abs().mean(dim=1)[0].cpu().numpy()

    flat = {i: maps[i].flatten() for i in SAMPLE_INDICES}
    corrs = []
    for a in range(len(SAMPLE_INDICES)):
        for b in range(a + 1, len(SAMPLE_INDICES)):
            corrs.append(np.corrcoef(flat[SAMPLE_INDICES[a]], flat[SAMPLE_INDICES[b]])[0, 1])
    corrs = np.array(corrs)

    print(f"PROBE checkpoint={checkpoint} step={global_step} "
          f"mean_corr={corrs.mean():.4f} min_corr={corrs.min():.4f} max_corr={corrs.max():.4f}")


if __name__ == "__main__":
    main()

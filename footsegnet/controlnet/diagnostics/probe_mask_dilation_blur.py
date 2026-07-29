"""Diagnostic Control-LoRA : dilater/flouter le masque avant
`controlnet_cond_embedding` retablit-il une vraie differenciation ?

Suite directe de diagnostics/probe_cond_embedding_trajectory.py
(2026-07-29) : ce diagnostic precedent a localise la perte d'info du masque
comme majoritairement ARCHITECTURALE (3 stride-2 dans
ControlNetConditioningEmbedding), specifique aux masques REELS (petits,
epars, 0.9-8.4% du cadre -- corr. gauche/droite ~0.99 des la sortie de
l'encodeur, quasi identique avant/apres entrainement). A l'inverse, des
masques massifs non locaux (test synthetique gauche/droite, 50% du cadre)
conservaient une vraie differenciation (corr. 0.79) a la sortie du meme
encodeur.

Hypothese testee ici : rendre un masque reel moins EPARS (dilatation
morphologique ou flou gaussien, applique AVANT le passage dans
controlnet_cond_embedding, comme un pre-traitement du masque -- pas un
changement d'architecture ni de loss) suffit-il a se rapprocher du regime
"masque massif" ou la differenciation survit ?

Reutilise directement get_cond_embedding_states()/trace_embedding()/
spatial_corr() de diagnostics/probe_cond_embedding_trajectory.py (meme
checkpoint, meme methodologie, meme masques reels idx 0/300) -- lecture
seule, train_control_lora.py non touche, aucun entrainement.

Usage :
    py -3.12 diagnostics/probe_mask_dilation_blur.py
    py -3.12 diagnostics/probe_mask_dilation_blur.py <checkpoint_dir>
"""

import sys
from pathlib import Path

import cv2
import numpy as np
import torch
import torch.nn.functional as F

sys.path.insert(0, str(Path(__file__).resolve().parent))
import probe_cond_embedding_trajectory as base   # noqa: E402  (fixe aussi tcl.CN_DATASET_ROOT a l'import)

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import train_control_lora as tcl   # noqa: E402

DEVICE = "cuda"
WEIGHT_DTYPE = torch.bfloat16
OUT_DIR = Path(__file__).resolve().parent / "mask_dilation_probe_outputs"

# Rayon du noyau morphologique en pixels (image 1024x1536) -- 0 = masque original.
DILATIONS_PX = [0, 10, 25, 60]
# Ecart-type du flou gaussien en pixels -- 0 = masque original.
BLUR_SIGMAS = [0, 8, 20, 50]


def dilate_mask(cond: torch.Tensor, radius_px: int) -> torch.Tensor:
    """cond: (1, 3, H, W) dans [0, 1], BLANC=objet. Dilatation morphologique
    (cv2.dilate, noyau elliptique) -- agrandit la zone blanche, contours
    encore nets."""
    if radius_px == 0:
        return cond
    arr = (cond[0, 0].float().cpu().numpy() * 255).astype(np.uint8)
    k = radius_px * 2 + 1
    kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (k, k))
    dilated = cv2.dilate(arr, kernel)
    out = torch.from_numpy(dilated.astype(np.float32) / 255.0)
    return out.unsqueeze(0).repeat(3, 1, 1).unsqueeze(0).to(cond.device, dtype=cond.dtype)


def blur_mask(cond: torch.Tensor, sigma: float) -> torch.Tensor:
    """Flou gaussien -- contours degrades (valeurs intermediaires, pas juste
    0/1), zone effective agrandie sans bord net."""
    if sigma == 0:
        return cond
    arr = (cond[0, 0].float().cpu().numpy() * 255).astype(np.uint8)
    k = (int(sigma * 3) | 1)   # noyau impair, ~3 sigma de rayon
    blurred = cv2.GaussianBlur(arr, (k, k), sigmaX=sigma)
    out = torch.from_numpy(blurred.astype(np.float32) / 255.0)
    return out.unsqueeze(0).repeat(3, 1, 1).unsqueeze(0).to(cond.device, dtype=cond.dtype)


def coverage_pct(cond: torch.Tensor) -> float:
    return float((cond[0, 0] > 0.5).float().mean().item() * 100)


def save_mask_montage(tag: str, entries: list[tuple[str, torch.Tensor, torch.Tensor]]) -> None:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    fig, axes = plt.subplots(2, len(entries), figsize=(3.2 * len(entries), 6.4))
    for col, (label, cond_a, cond_b) in enumerate(entries):
        axes[0, col].imshow(cond_a[0, 0].float().cpu().numpy(), cmap="gray", vmin=0, vmax=1)
        axes[0, col].set_title(f"{label}\nidx0, cov={coverage_pct(cond_a):.1f}%")
        axes[0, col].axis("off")
        axes[1, col].imshow(cond_b[0, 0].float().cpu().numpy(), cmap="gray", vmin=0, vmax=1)
        axes[1, col].set_title(f"idx300, cov={coverage_pct(cond_b):.1f}%")
        axes[1, col].axis("off")
    fig.suptitle(f"Masques -- {tag}")
    fig.tight_layout()
    out_path = OUT_DIR / f"masks_{tag}.png"
    fig.savefig(out_path, dpi=110)
    plt.close(fig)
    print(f"  -> montage masques sauve : {out_path}")


def main() -> None:
    checkpoint = Path(sys.argv[1]) if len(sys.argv) > 1 else base.DEFAULT_CHECKPOINT
    print(f"[probe_mask_dilation_blur] checkpoint = {checkpoint}")

    models = tcl.build_models(WEIGHT_DTYPE, lora_rank=64)
    controlnet = models["controlnet"].to(DEVICE, dtype=WEIGHT_DTYPE)
    unet = models["unet"]
    text_encoder, text_encoder_2 = models["text_encoder"], models["text_encoder_2"]
    text_encoder.to(DEVICE, dtype=WEIGHT_DTYPE)
    text_encoder_2.to(DEVICE, dtype=WEIGHT_DTYPE)

    global_step = tcl._load_checkpoint(controlnet, checkpoint.parent, str(checkpoint))
    controlnet.eval()
    print(f"[probe_mask_dilation_blur] checkpoint charge -> global_step={global_step}")

    _, trained_embed = base.get_cond_embedding_states(controlnet)

    dataset = tcl.ControlLoraDataset(base.MANIFEST, tcl.CN_DATASET_ROOT, max_samples=None)
    sample_a, sample_b = dataset[0], dataset[300]
    height, width = sample_a["height"], sample_a["width"]
    cond_a0 = sample_a["conditioning_pixel_values"].unsqueeze(0).to(DEVICE, dtype=WEIGHT_DTYPE)
    cond_b0 = sample_b["conditioning_pixel_values"].unsqueeze(0).to(DEVICE, dtype=WEIGHT_DTYPE)
    if cond_a0.shape != cond_b0.shape:
        cond_b0 = F.interpolate(cond_b0, size=cond_a0.shape[-2:], mode="nearest")
    print(f"[probe_mask_dilation_blur] masques reels idx0/idx300 ({width}x{height}) : "
          f"couverture originale = {coverage_pct(cond_a0):.2f}% / {coverage_pct(cond_b0):.2f}%")

    # ── Preparation du forward complet (texte/timestep fixes -- reprend probe_cond_embedding_trajectory.py) ──
    fixed_text = dataset.entries[0]["text"]
    prompt_embeds, pooled = tcl.encode_prompt(
        [fixed_text], [models["tokenizer"], models["tokenizer_2"]], [text_encoder, text_encoder_2], DEVICE,
    )
    prompt_embeds, pooled = prompt_embeds.to(WEIGHT_DTYPE), pooled.to(WEIGHT_DTYPE)
    add_time_ids = tcl.compute_time_ids(height, width, DEVICE, WEIGHT_DTYPE)
    added_cond_kwargs = {"text_embeds": pooled, "time_ids": add_time_ids}

    noise_scheduler = type(models["noise_scheduler"]).from_config(models["noise_scheduler"].config)
    noise_scheduler.set_timesteps(30, device=DEVICE)
    torch.manual_seed(42)
    latent = torch.randn((1, unet.config.in_channels, height // 8, width // 8), device=DEVICE, dtype=WEIGHT_DTYPE)
    t0 = noise_scheduler.timesteps[0]
    latent_in0 = noise_scheduler.scale_model_input(latent, t0)

    def probe_level(label: str, cond_a: torch.Tensor, cond_b: torch.Tensor) -> dict:
        with torch.no_grad():
            stages_a = base.trace_embedding(trained_embed, cond_a)
            stages_b = base.trace_embedding(trained_embed, cond_b)
            corr_conv_out = base.spatial_corr(stages_a["03_conv_out"], stages_b["03_conv_out"])

            _, mid_a = controlnet(
                latent_in0, t0, encoder_hidden_states=prompt_embeds, controlnet_cond=cond_a,
                added_cond_kwargs=added_cond_kwargs, return_dict=False,
            )
            _, mid_b = controlnet(
                latent_in0, t0, encoder_hidden_states=prompt_embeds, controlnet_cond=cond_b,
                added_cond_kwargs=added_cond_kwargs, return_dict=False,
            )
            corr_mid = base.spatial_corr(mid_a, mid_b)
        return {
            "label": label,
            "cov_a": coverage_pct(cond_a), "cov_b": coverage_pct(cond_b),
            "corr_conv_out": corr_conv_out, "corr_mid": corr_mid,
            "stages_a": stages_a, "stages_b": stages_b,
        }

    results = []

    print("\n=== Dilatation morphologique ===")
    montage_dilate = []
    for r in DILATIONS_PX:
        cond_a, cond_b = dilate_mask(cond_a0, r), dilate_mask(cond_b0, r)
        res = probe_level(f"dilate_r{r}px", cond_a, cond_b)
        results.append(res)
        montage_dilate.append((f"dilate r={r}px", cond_a, cond_b))
        print(f"  r={r:>3}px  cov={res['cov_a']:>6.2f}%/{res['cov_b']:>6.2f}%  "
              f"corr_conv_out={res['corr_conv_out']:>8.4f}  corr_mid_block_res={res['corr_mid']:>8.4f}")
    save_mask_montage("dilation", montage_dilate)

    print("\n=== Flou gaussien ===")
    montage_blur = []
    for s in BLUR_SIGMAS:
        cond_a, cond_b = blur_mask(cond_a0, s), blur_mask(cond_b0, s)
        res = probe_level(f"blur_s{s}px", cond_a, cond_b)
        results.append(res)
        montage_blur.append((f"blur sigma={s}px", cond_a, cond_b))
        print(f"  sigma={s:>3}px  cov={res['cov_a']:>6.2f}%/{res['cov_b']:>6.2f}%  "
              f"corr_conv_out={res['corr_conv_out']:>8.4f}  corr_mid_block_res={res['corr_mid']:>8.4f}")
    save_mask_montage("blur", montage_blur)

    # Heatmaps de la trajectoire complete pour le niveau le plus fort de chaque transformation
    # (comparaison directe avec real_trained.png du diagnostic precedent, meme fonction).
    strongest_dilate = results[len(DILATIONS_PX) - 1]
    strongest_blur = results[-1]
    base.save_heatmaps("dilation_strongest", strongest_dilate["stages_a"], strongest_dilate["stages_b"])
    base.save_heatmaps("blur_strongest", strongest_blur["stages_a"], strongest_blur["stages_b"])

    print("\n=== Reference (deja mesuree, diagnostic precedent) ===")
    print("  masque original (r=0/sigma=0)                    : corr_conv_out et corr_mid ci-dessus, ligne r=0/sigma=0")
    print("  masque synthetique gauche/droite (50% du cadre)   : corr_conv_out=0.7877  corr_mid_block_res=0.9936")


if __name__ == "__main__":
    main()

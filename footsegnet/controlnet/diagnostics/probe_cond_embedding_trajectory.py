"""Diagnostic Control-LoRA : ou l'information du masque se perd-elle dans le
reseau -- des l'encodeur controlnet_cond_embedding, ou plus loin ?

Contexte complet : DIAGNOSTIC_MODE_COLLAPSE_20260728.md, section "Prochaine
etape recommandee" (fin du fichier). Le diagnostic precedent a confirme un
mode collapse au niveau du residu final (mid_block_res_sample, correlation
~0.999+ entre masques quasi non correles) mais n'a jamais inspecte l'INTERIEUR
de controlnet_cond_embedding -- le petit encodeur (diffusers
ControlNetConditioningEmbedding, 4 convolutions + SiLU, cf.
diffusers/models/controlnets/controlnet.py:65-107) qui est le tout premier
point d'entree du masque dans le reseau, avant meme les zero-convs
(controlnet_down_blocks / controlnet_mid_block).

Ce script NE MODIFIE PAS train_control_lora.py : il l'importe et reutilise
build_models()/ControlLoraDataset/encode_prompt() tels quels, lecture seule,
aucun entrainement. Il exploite une propriete pratique de peft : quand tout
un module est enregistre dans `modules_to_save` (c'est le cas de
controlnet_cond_embedding ici, cf. LORA_MODULES_TO_SAVE), peft le remplace
par un `ModulesToSaveWrapper` qui garde a la fois :
  - `.original_module`  -> copie GELEE, jamais entrainee (init aleatoire de
    ControlNetModel.from_unet, requires_grad_(False) par peft) : c'est l'etat
    "avant tout entrainement" tel quel.
  - `.modules_to_save[adapter]` -> copie ENTRAINEE (chargee depuis un
    checkpoint via _load_checkpoint) : c'est l'etat "apres entrainement
    complet (mode collapse confirme)".
Comparer les deux sur les MEMES masques, en rejouant manuellement le forward
etape par etape (conv_in -> 3x(block+SiLU) -> conv_out), donne directement la
reponse "l'entrainement a-t-il fait disparaitre une differenciation qui
existait avant, ou l'architecture ne differencie-t-elle jamais rien meme a
l'etat brut ?"

Usage :
    py -3.12 diagnostics/probe_cond_embedding_trajectory.py
    py -3.12 diagnostics/probe_cond_embedding_trajectory.py <checkpoint_dir>
        (defaut : output/control_lora_v1_convergence_test/checkpoint-6000,
        le run complet 6000 steps jamais corrige -- le mode collapse "de
        production" que ce diagnostic cherche a expliquer)
"""

import sys
from pathlib import Path

import numpy as np
import torch
import torch.nn.functional as F

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import train_control_lora as tcl

# Cette session tourne dans un git worktree isole : le dataset et les
# checkpoints entraines sont volontairement exclus du repo (.gitignore) et
# n'existent que dans le checkout principal. On repointe les chemins de
# donnees vers le checkout principal ; le CODE reste celui du worktree
# (import train_control_lora depuis CE fichier, pas depuis le checkout
# principal) pour tester exactement la version en cours de revue.
MAIN_CONTROLNET_ROOT = Path("D:/OVERLORD/footsegnet/controlnet")
tcl.CN_DATASET_ROOT = MAIN_CONTROLNET_ROOT / "dataset"
MANIFEST = MAIN_CONTROLNET_ROOT / "dataset" / "manifest_filtered.jsonl"
DEFAULT_CHECKPOINT = MAIN_CONTROLNET_ROOT / "output" / "control_lora_v1_convergence_test" / "checkpoint-6000"

DEVICE = "cuda"
WEIGHT_DTYPE = torch.bfloat16
OUT_DIR = Path(__file__).resolve().parent / "cond_embedding_probe_outputs"


# ── Masques synthetiques (consigne : deux masques nettement differents) ──────

def make_half_mask(height: int, width: int, side: str) -> torch.Tensor:
    """Masque blanc=moitie gauche ou blanc=moitie droite, meme convention que
    ControlLoraDataset (RGB, [0, 1], BLANC=objet)."""
    arr = np.zeros((height, width, 3), dtype=np.float32)
    half = width // 2
    if side == "left":
        arr[:, :half, :] = 1.0
    elif side == "right":
        arr[:, half:, :] = 1.0
    else:
        raise ValueError(side)
    return torch.from_numpy(arr).permute(2, 0, 1)


# ── Rejeu manuel du forward de ControlNetConditioningEmbedding ──────────────
# Reproduit exactement diffusers/models/controlnets/controlnet.py:97-107
# (verifie dans site-packages, diffusers==0.38.0) pour capturer les
# activations a CHAQUE etape, pas seulement l'entree/la sortie.

def trace_embedding(module, x: torch.Tensor) -> dict[str, torch.Tensor]:
    stages = {}
    h = module.conv_in(x)
    h = F.silu(h)
    stages["01_conv_in"] = h
    for i, block in enumerate(module.blocks):
        h = block(h)
        h = F.silu(h)
        stages[f"02_block{i}"] = h
    stages["03_conv_out"] = module.conv_out(h)
    return stages


def spatial_corr(a: torch.Tensor, b: torch.Tensor) -> float:
    """Correlation de Pearson sur la composante spatiale (DC retiree par
    canal), meme methodologie que diagnostics/probe_mode_collapse.py pour
    rester comparable aux chiffres deja publies dans le rapport."""
    a = a.float()
    b = b.float()
    a = (a - a.mean(dim=(2, 3), keepdim=True)).flatten().cpu().numpy()
    b = (b - b.mean(dim=(2, 3), keepdim=True)).flatten().cpu().numpy()
    if a.std() < 1e-12 or b.std() < 1e-12:
        return float("nan")
    return float(np.corrcoef(a, b)[0, 1])


def cosine(a: torch.Tensor, b: torch.Tensor) -> float:
    return float(F.cosine_similarity(a.float().flatten(), b.float().flatten(), dim=0).item())


def get_cond_embedding_states(controlnet):
    """Renvoie (copie_gelee_jamais_entrainee, copie_entrainee_chargee) du
    sous-module controlnet_cond_embedding. Repose sur le fait que peft
    remplace un module entier enregistre dans modules_to_save par un
    ModulesToSaveWrapper qui garde original_module (gele) ET
    modules_to_save[adapter] (entraine) -- verifie dans
    site-packages/peft/utils/other.py (ModulesToSaveWrapper, peft==0.19.1)."""
    wrapper = controlnet.controlnet_cond_embedding
    if not hasattr(wrapper, "original_module"):
        raise RuntimeError(
            "controlnet_cond_embedding n'est pas un ModulesToSaveWrapper -- "
            "verifier LORA_MODULES_TO_SAVE / _expand_modules_to_save dans train_control_lora.py"
        )
    frozen = wrapper.original_module
    trained = wrapper.modules_to_save[wrapper.active_adapters[0]]
    return frozen, trained


def summarize(label: str, stages_a: dict, stages_b: dict) -> None:
    print(f"\n  [{label}]")
    print(f"  {'etape':<14}{'std(A)':>10}{'std(B)':>10}{'cos(A,B)':>12}{'corr_spatiale':>16}")
    for name in stages_a:
        a, b = stages_a[name], stages_b[name]
        print(f"  {name:<14}{a.float().std().item():>10.4f}{b.float().std().item():>10.4f}"
              f"{cosine(a, b):>12.4f}{spatial_corr(a, b):>16.4f}")


def save_heatmaps(tag: str, stages_a: dict, stages_b: dict) -> None:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    names = list(stages_a.keys())
    fig, axes = plt.subplots(1, len(names), figsize=(4 * len(names), 4))
    for ax, name in zip(axes, names):
        diff = (stages_a[name].float() - stages_b[name].float()).abs().mean(dim=1)[0].cpu().numpy()
        im = ax.imshow(diff, cmap="magma")
        ax.set_title(f"{name}\n|A-B| mean(canaux)")
        ax.axis("off")
        fig.colorbar(im, ax=ax, fraction=0.046)
    fig.suptitle(tag)
    fig.tight_layout()
    out_path = OUT_DIR / f"{tag}.png"
    fig.savefig(out_path, dpi=110)
    plt.close(fig)
    print(f"  -> heatmap sauvee : {out_path}")


def main() -> None:
    checkpoint = Path(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_CHECKPOINT
    print(f"[probe_cond_embedding_trajectory] checkpoint = {checkpoint}")

    models = tcl.build_models(WEIGHT_DTYPE, lora_rank=64)
    controlnet = models["controlnet"].to(DEVICE, dtype=WEIGHT_DTYPE)
    unet = models["unet"]
    text_encoder, text_encoder_2 = models["text_encoder"], models["text_encoder_2"]
    text_encoder.to(DEVICE, dtype=WEIGHT_DTYPE)
    text_encoder_2.to(DEVICE, dtype=WEIGHT_DTYPE)

    global_step = tcl._load_checkpoint(controlnet, checkpoint.parent, str(checkpoint))
    controlnet.eval()
    print(f"[probe_cond_embedding_trajectory] checkpoint charge -> global_step={global_step}")

    frozen_embed, trained_embed = get_cond_embedding_states(controlnet)

    # ── Masques synthetiques gauche/droite (consigne explicite de la tache) ──
    dataset = tcl.ControlLoraDataset(MANIFEST, tcl.CN_DATASET_ROOT, max_samples=None)
    ref_sample = dataset[0]
    height, width = ref_sample["height"], ref_sample["width"]
    mask_left = make_half_mask(height, width, "left").unsqueeze(0).to(DEVICE, dtype=WEIGHT_DTYPE)
    mask_right = make_half_mask(height, width, "right").unsqueeze(0).to(DEVICE, dtype=WEIGHT_DTYPE)

    print(f"\n=== Masques synthetiques gauche/droite ({width}x{height}) ===")
    with torch.no_grad():
        frozen_left = trace_embedding(frozen_embed, mask_left)
        frozen_right = trace_embedding(frozen_embed, mask_right)
        trained_left = trace_embedding(trained_embed, mask_left)
        trained_right = trace_embedding(trained_embed, mask_right)

    summarize("AVANT entrainement (original_module, init aleatoire, gele)", frozen_left, frozen_right)
    summarize(f"APRES entrainement (checkpoint step={global_step})", trained_left, trained_right)
    save_heatmaps("synthetic_frozen", frozen_left, frozen_right)
    save_heatmaps("synthetic_trained", trained_left, trained_right)

    # ── Masques reels tres differents (memes indices que probe_mode_collapse.py) ──
    print(f"\n=== Masques reels dataset (idx 0 vs idx 300, tres eloignes) ===")
    sample_a, sample_b = dataset[0], dataset[300]
    cond_a = sample_a["conditioning_pixel_values"].unsqueeze(0).to(DEVICE, dtype=WEIGHT_DTYPE)
    cond_b = sample_b["conditioning_pixel_values"].unsqueeze(0).to(DEVICE, dtype=WEIGHT_DTYPE)
    if cond_a.shape != cond_b.shape:
        cond_b = F.interpolate(cond_b, size=cond_a.shape[-2:], mode="nearest")
    with torch.no_grad():
        frozen_a = trace_embedding(frozen_embed, cond_a)
        frozen_b = trace_embedding(frozen_embed, cond_b)
        trained_a = trace_embedding(trained_embed, cond_a)
        trained_b = trace_embedding(trained_embed, cond_b)
    summarize("AVANT entrainement (masques reels)", frozen_a, frozen_b)
    summarize(f"APRES entrainement (masques reels, step={global_step})", trained_a, trained_b)
    save_heatmaps("real_frozen", frozen_a, frozen_b)
    save_heatmaps("real_trained", trained_a, trained_b)

    # ── Point d'injection : sample = conv_in(latent) + controlnet_cond_embedding(mask) ──
    # (diffusers/models/controlnets/controlnet.py:736-739) -- teste l'hypothese
    # "dilution par magnitude" : le residu latent domine-t-il l'embedding masque ?
    print("\n=== Point d'injection dans l'UNet (conv_in(latent) + cond_embedding(masque)) ===")
    torch.manual_seed(42)
    latent = torch.randn((1, unet.config.in_channels, height // 8, width // 8), device=DEVICE, dtype=WEIGHT_DTYPE)
    with torch.no_grad():
        latent_feat = controlnet.conv_in(latent)
        cond_out_trained_left = trained_embed(mask_left)
        cond_out_trained_right = trained_embed(mask_right)
    std_latent = latent_feat.float().std().item()
    std_cond = cond_out_trained_left.float().std().item()
    print(f"  std(conv_in(latent bruit alea))     = {std_latent:.5f}")
    print(f"  std(controlnet_cond_embedding(mask)) = {std_cond:.5f}  (checkpoint entraine)")
    print(f"  ratio embedding/latent                = {std_cond / max(std_latent, 1e-12):.5f}")
    print(f"  corr_spatiale(sample_left, sample_right) au point d'injection = "
          f"{spatial_corr(latent_feat + cond_out_trained_left, latent_feat + cond_out_trained_right):.4f}")
    print(f"  corr_spatiale(cond_embedding seul, gauche vs droite)           = "
          f"{spatial_corr(cond_out_trained_left, cond_out_trained_right):.4f}")

    # ── Trajectoire complete jusqu'au residu final (reprend probe_mode_collapse.py) ──
    print("\n=== Trajectoire complete jusqu'a mid_block_res_sample (residu final) ===")
    fixed_text = dataset.entries[0]["text"]
    prompt_embeds, pooled = tcl.encode_prompt(
        [fixed_text], [models["tokenizer"], models["tokenizer_2"]], [text_encoder, text_encoder_2], DEVICE,
    )
    prompt_embeds, pooled = prompt_embeds.to(WEIGHT_DTYPE), pooled.to(WEIGHT_DTYPE)
    add_time_ids = tcl.compute_time_ids(height, width, DEVICE, WEIGHT_DTYPE)
    added_cond_kwargs = {"text_embeds": pooled, "time_ids": add_time_ids}

    noise_scheduler = type(models["noise_scheduler"]).from_config(models["noise_scheduler"].config)
    noise_scheduler.set_timesteps(30, device=DEVICE)
    t0 = noise_scheduler.timesteps[0]
    latent_in0 = noise_scheduler.scale_model_input(latent, t0)

    with torch.no_grad():
        _, mid_left = controlnet(
            latent_in0, t0, encoder_hidden_states=prompt_embeds, controlnet_cond=mask_left,
            added_cond_kwargs=added_cond_kwargs, return_dict=False,
        )
        _, mid_right = controlnet(
            latent_in0, t0, encoder_hidden_states=prompt_embeds, controlnet_cond=mask_right,
            added_cond_kwargs=added_cond_kwargs, return_dict=False,
        )
    print(f"  corr_spatiale(mid_block_res_sample, gauche vs droite) = {spatial_corr(mid_left, mid_right):.4f}")
    print("  (a comparer aux ~0.999+ deja mesures sur masques du dataset dans DIAGNOSTIC_MODE_COLLAPSE_20260728.md)")


if __name__ == "__main__":
    main()

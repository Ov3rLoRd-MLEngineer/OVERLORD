"""Piste C -- Optical Flow warp RAFT (script autonome, PAS de node ComfyUI :
OpticalFlowLoader n'a aucun modele installe dans models/optical_flow sur
cette install, et il n'existe pas de node de warp pixel direct -- seulement
VOIDWarpedNoise qui warp du bruit latent, pas des pixels).

Utilise torchvision.models.optical_flow.raft_large (confirme disponible :
torch 2.12.0+cu130, torchvision 0.27.0+cu130). Calcule le flow forward entre
chaque paire de frames consecutives parmi les 10 frames de reference (dans
l'ordre frame_00001 -> frame_00037), puis warp chaque frame N+1 vers
l'alignement de la frame N via grid_sample (flow pixels, pas de nouvelle
dependance -- cv2 est disponible mais non utilise ici, grid_sample suffit).

Usage:
    "D:\\Ov3rLoRd AI\\python_embeded\\python.exe" DEMO/run_piste_C_raft_warp.py
"""
import os
import time

import numpy as np
import torch
import torch.nn.functional as F
from PIL import Image
from torchvision.models.optical_flow import Raft_Large_Weights, raft_large

REF_DIR = r"D:\OVERLORD\DEMO\frames\comparaison_unification_ref"
OUT_DIR = os.path.join(REF_DIR, "piste_C")
FRAME_IDS = [1, 5, 9, 13, 17, 21, 25, 29, 33, 37]

DEVICE = "cuda" if torch.cuda.is_available() else "cpu"


def load_frame(fid):
    path = os.path.join(REF_DIR, f"frame_{fid:05d}.png")
    img = Image.open(path).convert("RGB")
    arr = np.array(img).astype(np.float32) / 255.0  # HWC [0,1]
    t = torch.from_numpy(arr).permute(2, 0, 1).unsqueeze(0)  # 1,C,H,W
    return t, img.size  # (w,h)


def to_raft_input(t):
    # RAFT attend des images normalisees dans [-1, 1]
    return t * 2.0 - 1.0


def warp_with_flow(img_t, flow):
    # img_t: 1,C,H,W dans [0,1] ; flow: 1,2,H,W (dx, dy) en pixels, convention
    # RAFT flow[i->i+1](x) = deplacement de x dans image1 vers sa position
    # correspondante dans image2. Pour warper image2 vers l'alignement de
    # image1 : output(x) = image2(x + flow(x)).
    _, _, H, W = img_t.shape
    yy, xx = torch.meshgrid(torch.arange(H, device=img_t.device, dtype=torch.float32),
                             torch.arange(W, device=img_t.device, dtype=torch.float32),
                             indexing="ij")
    grid_x = xx + flow[0, 0]
    grid_y = yy + flow[0, 1]
    # normalisation [-1, 1] pour grid_sample
    grid_x_n = 2.0 * grid_x / max(W - 1, 1) - 1.0
    grid_y_n = 2.0 * grid_y / max(H - 1, 1) - 1.0
    grid = torch.stack([grid_x_n, grid_y_n], dim=-1).unsqueeze(0)  # 1,H,W,2
    warped = F.grid_sample(img_t, grid, mode="bilinear", padding_mode="border", align_corners=True)
    return warped


def main():
    os.makedirs(OUT_DIR, exist_ok=True)
    t0 = time.time()

    print(f"Chargement RAFT (raft_large, poids par defaut) sur {DEVICE}...", flush=True)
    weights = Raft_Large_Weights.DEFAULT
    model = raft_large(weights=weights, progress=True).to(DEVICE).eval()

    frames = {}
    for fid in FRAME_IDS:
        t, size = load_frame(fid)
        frames[fid] = (t.to(DEVICE), size)

    # Toutes les frames de reference font 480x720 (verifie au prealable) --
    # divisible par 8, aucun padding requis par RAFT.
    _, ref_size = frames[FRAME_IDS[0]]
    for fid, (_, size) in frames.items():
        if size != ref_size:
            raise SystemExit(f"frame {fid} a une taille differente ({size} vs {ref_size}) -- padding RAFT non implemente ici")

    # frame_00001 : gardee telle quelle (rien a aligner dessus)
    first_t, _ = frames[FRAME_IDS[0]]
    first_np = (first_t[0].clamp(0, 1).permute(1, 2, 0).cpu().numpy() * 255).astype(np.uint8)
    Image.fromarray(first_np).save(os.path.join(OUT_DIR, f"frame_{FRAME_IDS[0]:05d}.png"))
    print(f"[C] frame {FRAME_IDS[0]} copiee telle quelle (reference initiale)", flush=True)

    with torch.no_grad():
        for i in range(len(FRAME_IDS) - 1):
            fid_a, fid_b = FRAME_IDS[i], FRAME_IDS[i + 1]
            img_a, _ = frames[fid_a]
            img_b, _ = frames[fid_b]

            flow_preds = model(to_raft_input(img_a), to_raft_input(img_b))
            flow = flow_preds[-1]  # derniere iteration RAFT = la plus precise

            warped = warp_with_flow(img_b, flow)
            warped_np = (warped[0].clamp(0, 1).permute(1, 2, 0).cpu().numpy() * 255).astype(np.uint8)
            out_path = os.path.join(OUT_DIR, f"frame_{fid_b:05d}.png")
            Image.fromarray(warped_np).save(out_path)
            print(f"[C] frame {fid_b} warpee vers alignement frame {fid_a} -> {out_path}", flush=True)

    elapsed = time.time() - t0
    print(f"RESULT_OK: 10 frames piste C -> {OUT_DIR}")
    print(f"RESULT_ELAPSED_S: {elapsed:.1f}")
    print(f"RESULT_DEVICE: {DEVICE}")


if __name__ == "__main__":
    main()

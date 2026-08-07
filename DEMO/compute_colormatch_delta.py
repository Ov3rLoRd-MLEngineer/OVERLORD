"""Calcule le score ColorMatch inter-frames (delta moyen Lab, CIE76 euclidien)
entre frames consecutives d'une piste -- 9 deltas pour 10 frames. Utilise
skimage.color.rgb2lab (confirme disponible, scikit-image 0.26.0).

Usage:
    "D:\\Ov3rLoRd AI\\python_embeded\\python.exe" DEMO/compute_colormatch_delta.py
"""
import os

import numpy as np
from PIL import Image
from skimage.color import rgb2lab

REF_DIR = r"D:\OVERLORD\DEMO\frames\comparaison_unification_ref"
FRAME_IDS = [1, 5, 9, 13, 17, 21, 25, 29, 33, 37]


def lab_delta_series(frame_dir, label):
    paths = [os.path.join(frame_dir, f"frame_{fid:05d}.png") for fid in FRAME_IDS]
    missing = [p for p in paths if not os.path.exists(p)]
    if missing:
        return None, f"{label}: MANQUANT ({len(missing)}/10 fichiers absents, ex: {os.path.basename(missing[0])})"

    labs = []
    for p in paths:
        img = np.array(Image.open(p).convert("RGB")).astype(np.float64) / 255.0
        labs.append(rgb2lab(img))

    deltas = []
    for i in range(len(labs) - 1):
        d = np.sqrt(np.sum((labs[i + 1] - labs[i]) ** 2, axis=-1))
        deltas.append(float(d.mean()))

    mean_delta = float(np.mean(deltas))
    return {"deltas": deltas, "mean": mean_delta}, None


def main():
    print("Score ColorMatch inter-frames (delta E Lab moyen, CIE76) -- 9 deltas / piste\n")

    baseline, err = lab_delta_series(REF_DIR, "baseline (frames brutes, non traitees)")
    if err:
        print(err)
    else:
        print(f"BASELINE (frames SVI brutes, sans traitement) : delta moyen = {baseline['mean']:.4f}")
        print(f"  deltas par paire: {[round(d, 3) for d in baseline['deltas']]}\n")

    for piste in ["A", "B", "C", "D", "E1", "E2", "E3", "E4"]:
        d = os.path.join(REF_DIR, f"piste_{piste}")
        result, err = lab_delta_series(d, f"piste {piste}")
        if err:
            print(f"PISTE {piste}: {err}")
        else:
            print(f"PISTE {piste} : delta moyen = {result['mean']:.4f}")
            print(f"  deltas par paire: {[round(x, 3) for x in result['deltas']]}")


if __name__ == "__main__":
    main()

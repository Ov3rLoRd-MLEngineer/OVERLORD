"""Diagnostic Control-LoRA : diversite reelle des images de conditionnement.

Verifie, sur les memes indices d'echantillons que probe_mode_collapse.py
(0, 100, 200, 300, 400 dans manifest_filtered.jsonl), que les masques BRUTS
utilises comme controlnet_cond sont effectivement differents les uns des
autres (correlation de Pearson pixel-a-pixel faible). Sert de contre-preuve :
si les masques sont diversifies mais que le residu appris (probe_mode_collapse.py)
reste quasi identique quel que soit l'echantillon, la cause est le mode
collapse de l'entrainement -- pas un manque de diversite du dataset.

Ne necessite pas de GPU (chargement PIL/numpy seul).

Usage :
    py -3.12 diagnostics/check_conditioning_diversity.py
"""

import json
from pathlib import Path

import numpy as np
from PIL import Image

CONTROLNET_ROOT = Path(__file__).resolve().parent.parent
MANIFEST = CONTROLNET_ROOT / "dataset" / "manifest_filtered.jsonl"
DATASET_ROOT = CONTROLNET_ROOT / "dataset"
SAMPLE_INDICES = [0, 100, 200, 300, 400]


def main() -> None:
    entries = [json.loads(line) for line in MANIFEST.read_text(encoding="utf-8").splitlines() if line.strip()]
    print(f"Dataset : {len(entries)} paires. Indices testes : {SAMPLE_INDICES}")

    imgs = {}
    for idx in SAMPLE_INDICES:
        path = DATASET_ROOT / entries[idx]["conditioning_image"]
        arr = np.array(Image.open(path).convert("L").resize((128, 192))).astype(np.float32)
        imgs[idx] = arr.flatten()
        print(f"  idx={idx} {entries[idx]['conditioning_image']} couverture_blanc={(arr > 127).mean():.4f}")

    corrs = []
    print("\n=== Correlation croisee (Pearson) des masques BRUTS entre paires d'echantillons ===")
    for a in range(len(SAMPLE_INDICES)):
        for b in range(a + 1, len(SAMPLE_INDICES)):
            ia, ib = SAMPLE_INDICES[a], SAMPLE_INDICES[b]
            corr = np.corrcoef(imgs[ia], imgs[ib])[0, 1]
            corrs.append(corr)
            print(f"  idx{ia:04d} vs idx{ib:04d} : correlation = {corr:.4f}")

    corrs = np.array(corrs)
    print(f"\nCorrelation moyenne (hors diagonale) : {corrs.mean():.4f}")
    print(f"Correlation min : {corrs.min():.4f}  max : {corrs.max():.4f}")
    if corrs.mean() < 0.3:
        print("\n>>> Masques bruts DIVERSIFIES (faible correlation) -- si le residu appris est, lui, "
              "fortement correle entre ces memes echantillons (cf. probe_mode_collapse.py), "
              "le manque de diversite du dataset est ECARTE comme cause.")
    else:
        print("\n>>> Masques bruts eux-memes correles -- verifier si le manque de diversite du "
              "dataset explique (au moins en partie) la correlation observee sur le residu appris.")


if __name__ == "__main__":
    main()

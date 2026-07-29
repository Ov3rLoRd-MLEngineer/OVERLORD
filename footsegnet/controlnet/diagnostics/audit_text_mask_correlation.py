"""Diagnostic Control-LoRA : le texte du prompt correle-t-il deja avec la
position du masque de conditionnement dans le dataset d'entrainement ?

Hypothese (cf. DIAGNOSTIC_MODE_COLLAPSE_20260728.md, piste non testee du
diagnostic initial) : si le texte contient deja une information
positionnelle previsible a partir de la position du masque, le modele n'a
structurellement aucune raison d'apprendre a lire le masque -- le chemin
texte (deja traite par CLIP, gele) suffit a expliquer une bonne partie de
ce que la loss recompense, ce qui pourrait a lui seul expliquer le mode
collapse independamment de tout probleme de loss ou d'architecture
ControlNet.

Analyse statistique pure -- aucun entrainement, aucun GPU necessaire,
aucune modification du dataset ni du code d'entrainement.

Usage :
    py -3.12 diagnostics/audit_text_mask_correlation.py
"""

import json
import re
from collections import Counter
from pathlib import Path

import numpy as np
from PIL import Image
from scipy import stats

# Ce script vit dans le worktree diagnostique (dataset/ absent, gitignore) --
# le dataset reel vit dans l'arborescence principale.
CONTROLNET_ROOT = Path("D:/OVERLORD/footsegnet/controlnet")
MANIFEST = CONTROLNET_ROOT / "dataset" / "manifest_filtered.jsonl"
DATASET_ROOT = CONTROLNET_ROOT / "dataset"

STOPWORDS = {
    "score_9", "score_8_up", "source_anime", "1girl", "1boy", "solo", "anime",
    "style", "the", "a", "an", "with", "and", "of", "in", "on", "at", "to",
}


def load_entries() -> list[dict]:
    entries = [json.loads(l) for l in MANIFEST.read_text(encoding="utf-8").splitlines() if l.strip()]
    return entries


def mask_centroid_x(path: Path) -> float | None:
    """Centre de masse horizontal du masque (blanc=pied/chaussure), normalise [0,1]."""
    arr = np.array(Image.open(path).convert("L"), dtype=np.float32)
    if arr.sum() < 1e-6:
        return None
    w = arr.shape[1]
    xs = np.arange(w, dtype=np.float32)
    col_weight = arr.sum(axis=0)
    cx = (col_weight * xs).sum() / col_weight.sum()
    return float(cx / w)


def tokenize(text: str) -> list[str]:
    words = re.findall(r"[a-z][a-z\-]+", text.lower())
    return [w for w in words if w not in STOPWORDS and len(w) > 2]


def main() -> None:
    entries = load_entries()
    print(f"Dataset : {len(entries)} paires -- {MANIFEST}")

    records = []
    skipped = 0
    for entry in entries:
        cond_path = DATASET_ROOT / entry["conditioning_image"]
        cx = mask_centroid_x(cond_path)
        if cx is None:
            skipped += 1
            continue
        records.append({"text": entry.get("text", ""), "cx": cx})

    print(f"Masques exploitables : {len(records)} (ecartes -- masque vide/introuvable : {skipped})")

    # --- Classe gauche/droite (coupure au centre de l'image, 0.5) ---
    for r in records:
        r["side"] = "left" if r["cx"] < 0.5 else "right"
    n_left = sum(1 for r in records if r["side"] == "left")
    n_right = len(records) - n_left
    print(f"\nRepartition gauche/droite (coupure a 0.5) : left={n_left} right={n_right}")

    # --- Mots-cles positionnels explicites ---
    print("\n=== Mots-cles positionnels explicites ('left'/'right') ===")
    explicit_hits = [r for r in records if "left" in r["text"].lower() or "right" in r["text"].lower()]
    print(f"Occurrences de 'left'/'right' dans le texte : {len(explicit_hits)} / {len(records)} "
          f"({100 * len(explicit_hits) / len(records):.1f}% du dataset)")
    explicit_pvalue = 1.0
    if explicit_hits:
        correct = sum(
            1 for r in explicit_hits
            if ("left" in r["text"].lower() and r["side"] == "left")
            or ("right" in r["text"].lower() and r["side"] == "right")
        )
        explicit_pvalue = stats.binomtest(correct, len(explicit_hits), 0.5, alternative="greater").pvalue
        print(f"  Precision du mot-cle explicite quand present : {correct}/{len(explicit_hits)} "
              f"({100 * correct / len(explicit_hits):.1f}%) -- hasard = 50%, "
              f"p-value (test binomial, H0: p=0.5) = {explicit_pvalue:.4f}")

    # --- Classifieur mot-cle simple : baseline majoritaire vs mots-cles ---
    print("\n=== Classifieur baseline (majorite) ===")
    majority = "left" if n_left >= n_right else "right"
    baseline_acc = max(n_left, n_right) / len(records)
    print(f"Classe majoritaire : {majority} -- precision baseline = {100 * baseline_acc:.1f}%")

    # --- Correlation mot par mot : biais gauche/droite de chaque mot du vocabulaire ---
    # ATTENTION comparaisons multiples : des dizaines/centaines de mots sont testes ici --
    # un seuil de biais brut sans correction produirait mecaniquement des faux positifs par
    # pur bruit d'echantillonnage (n aussi bas que 15-25 par mot). p-value binomiale +
    # correction de Bonferroni (nombre de mots testes) pour un verdict honnete.
    word_side_counts: dict[str, Counter] = {}
    for r in records:
        for w in set(tokenize(r["text"])):
            word_side_counts.setdefault(w, Counter())[r["side"]] += 1

    scored = []
    for w, c in word_side_counts.items():
        total = c["left"] + c["right"]
        if total < 15:
            continue
        frac_left = c["left"] / total
        pvalue = stats.binomtest(c["left"], total, 0.5, alternative="two-sided").pvalue
        scored.append((w, total, frac_left, pvalue))
    scored.sort(key=lambda t: t[3])

    n_words_tested = len(scored)
    bonferroni_alpha = 0.05 / max(n_words_tested, 1)
    print(f"\n=== Mots testes (n_occurrences >= 15) : {n_words_tested} -- "
          f"seuil de Bonferroni (alpha=0.05) = {bonferroni_alpha:.6f} ===")
    print("Top 15 par p-value (les plus significatifs si correction appliquee) :")
    for w, total, frac_left, pvalue in scored[:15]:
        flag = " *** significatif apres Bonferroni ***" if pvalue < bonferroni_alpha else ""
        print(f"  {w:20s} n={total:4d}  %left={100*frac_left:5.1f}%  p={pvalue:.5f}{flag}")

    n_significant = sum(1 for _, _, _, p in scored if p < bonferroni_alpha)
    if not scored:
        print("  (aucun mot avec >=15 occurrences -- dataset trop petit ou vocabulaire trop diversifie)")

    # --- Verdict ---
    print("\n=== VERDICT ===")
    explicit_predictive = explicit_hits and explicit_pvalue < 0.05 and len(explicit_hits) >= 10
    coverage_explicit = len(explicit_hits) / len(records) if records else 0.0

    if n_significant > 0:
        print(f">>> CORRELATION texte<->position DETECTEE et statistiquement significative "
              f"(apres correction de Bonferroni) sur {n_significant} mot(s) du vocabulaire.")
    elif explicit_predictive:
        print(f">>> Mots-cles 'left'/'right' explicites moderement predictifs (p={explicit_pvalue:.4f}) "
              f"mais presents dans seulement {100*coverage_explicit:.1f}% du dataset -- signal faible "
              f"et de couverture trop limitee pour expliquer a lui seul le mode collapse observe sur "
              f"l'ensemble du dataset.")
    else:
        print(">>> AUCUNE CORRELATION SIGNIFICATIVE detectee entre le texte et la position "
              "gauche/droite du masque, une fois la correction pour comparaisons multiples appliquee. "
              "Cette piste est ECARTEE comme explication du mode collapse.")


if __name__ == "__main__":
    main()

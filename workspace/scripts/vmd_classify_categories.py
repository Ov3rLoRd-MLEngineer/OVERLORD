"""Classification fine des 34 VMD dynamiques (danse / combat / idle / expressif /
deplacement / inconnu) a partir de l'audit existant (vmd_audit_result.json +
vmd_audit_bear0830.json, deja produits par workspace/scripts/vmd_audit.py).

Heuristique : nom de fichier/dossier (mots-cles explicites) en premier, sinon
amplitude du bone centre (deplacement du personnage dans l'espace) + duree.
Pas de rendu Blender ici (couteux, 34 fichiers) -- classification automatique
signalee comme telle, pas une verification visuelle. A relire avant de faire
confiance a un tag "inconnu"->quelque chose sans le rejouer au moins une fois.
"""
import json
import os

FPS = 30.0
SHORT_THRESHOLD_S = 3.0

RESULT_JSON = os.path.join("workspace", "scripts", "vmd_audit_result.json")
BEAR_JSON = os.path.join("workspace", "scripts", "vmd_audit_bear0830.json")
OUT_CSV = os.path.join("DEMO", "vmd_classification.csv")

KEYWORDS = {
    "danse": ["dance", "danc"],
    "combat": ["combat", "battle", "fight", "punch", "kick", "bajiquan", "quan", "kung"],
    "deplacement": ["walk", "run", "march", "jog", "sprint"],
    "expressif": ["cry", "scared", "exciting", "muscle", "pee", "smell", "reaction", "laugh", "surpris"],
    "idle": ["idle", "wait", "stand"],
}


def classify(path, max_frame, unique_bones, amplitude):
    name = os.path.basename(path).lower()
    parent = os.path.basename(os.path.dirname(path)).lower()
    haystack = name + " " + parent

    for cat, kws in KEYWORDS.items():
        if any(kw in haystack for kw in kws):
            return cat, "nom de fichier/dossier"

    duration_s = max_frame / FPS
    # Heuristique amplitude/duree : longue duree + beaucoup de bones distincts +
    # amplitude moderee a elevee est le profil typique d'une choregraphie MMD
    # communautaire (majorite du pack bear0830/mmd, cf. ASSETS_INDEX.md).
    if duration_s >= 60 and unique_bones >= 100:
        return "danse", "heuristique amplitude/duree (probable, NON verifie visuellement)"

    return "inconnu", "aucun signal fiable (nom generique, duree/amplitude non concluantes)"


def main():
    with open(RESULT_JSON, encoding="utf-8") as f:
        result = json.load(f)
    with open(BEAR_JSON, encoding="utf-8") as f:
        bear = json.load(f)

    dynamic = [x for x in result if x["class"] == "dynamic"] + bear

    rows = []
    seen_fingerprints = {}
    for x in dynamic:
        path = x["path"]
        max_frame = x["max_frame"]
        unique_bones = x["unique_bones"]
        amplitude = x["center_amplitude"]
        duration_s = round(max_frame / FPS, 2)
        cat, basis = classify(path, max_frame, unique_bones, amplitude)
        too_short = duration_s < SHORT_THRESHOLD_S

        fingerprint = (max_frame, unique_bones, amplitude)
        dup_of = seen_fingerprints.get(fingerprint)
        if dup_of is None:
            seen_fingerprints[fingerprint] = path
        rows.append({
            "path": path,
            "name": os.path.basename(path),
            "category": cat,
            "category_basis": basis,
            "duration_s": duration_s,
            "unique_bones": unique_bones,
            "center_amplitude": amplitude,
            "too_short_lt3s": too_short,
            "duplicate_of": dup_of,
        })

    import csv
    os.makedirs(os.path.dirname(OUT_CSV), exist_ok=True)
    with open(OUT_CSV, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)

    from collections import Counter
    cat_counts = Counter(r["category"] for r in rows)
    print(f"{len(rows)} VMD classes -> {OUT_CSV}")
    print("Repartition:", dict(cat_counts))
    print("Trop courts (<3s):", [r["name"] for r in rows if r["too_short_lt3s"]])
    print("Doublons (fingerprint identique):", [r["name"] for r in rows if r["duplicate_of"]])


if __name__ == "__main__":
    main()

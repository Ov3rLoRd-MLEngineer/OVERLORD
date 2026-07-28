# ██████╗ ██╗   ██╗██████╗ ██████╗ ██╗      ██████╗ ██████╗ ██████╗
# ██╔═══██╗██║   ██║╚════██╗██╔══██╗██║     ██╔═══██╗██╔══██╗██╔══██╗
# ██║   ██║██║   ██║ █████╔╝██████╔╝██║     ██║   ██║██████╔╝██║  ██║
# ██║   ██║╚██╗ ██╔╝ ╚═══██╗██╔══██╗██║     ██║   ██║██╔══██╗██║  ██║
# ╚██████╔╝ ╚████╔╝ ██████╔╝██║  ██║███████╗╚██████╔╝██║  ██║██████╔╝
# ╚═════╝   ╚═══╝  ╚═════╝ ╚═╝  ╚═╝╚══════╝ ╚═════╝ ╚═╝  ╚═╝╚═════╝
# Ov3rLoRd -- pipeline de production anime autonome (ComfyUI)
# https://github.com/Ov3rLoRd-MLEngineer
#
# explain_unscored.py — caracterise route_unscored.txt (aucun score SAM)
#
# agents/prepare_route_folders.py journalise a part (route_unscored.txt) les
# images sans score SAM exploitable, sans les classer. Ce script croise cette
# liste avec dataset/masks_raw/ (annotations manuelles) et la derniere ligne
# de _provenance.csv par image pour repondre a UNE question : ce trou dans le
# scoring correspond-il a un etat de pipeline connu (annotation manuelle deja
# faite, pose non detectee, prononnance sans score journalise), ou reste-t-il
# des images vraiment inexpliquees (a investiguer) ?
#
# Purement en lecture -- ne modifie, ne deplace, ne supprime jamais aucun
# fichier.
#
# Categories :
#   - manuel        : dataset/masks_raw/<stem>.png existe (annotation deja
#                      faite -- attendu, pas un probleme)
#   - box_failed     : derniere ligne _provenance.csv status=BOX_FAILED
#                      (aucune bbox derivable, pose + fallback VLM ont
#                      tous les deux echoue -- aucun premask genere)
#   - ok_sans_score  : derniere ligne status=OK mais sam_score vide (premask
#                      genere, generalement via fallback qwenvl_grounding qui
#                      ne journalise pas toujours sam_score -- cf. PR #17)
#   - jamais_traite  : aucune ligne dans _provenance.csv du tout
#   - autre          : tout le reste (a investiguer en priorite si non vide)
#
# Usage :
#   py -3.12 agents/explain_unscored.py --module handsegnet

import argparse
import csv
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))
from agents.route_by_sam_confidence import MODULE_ROOTS   # noqa: E402


def main(module: str) -> None:
    dataset_dir = MODULE_ROOTS[module] / "dataset"
    premasks_dir = dataset_dir / "premasks"
    unscored_path = premasks_dir / "route_unscored.txt"
    prov_path = premasks_dir / "_provenance.csv"

    if not unscored_path.exists():
        print(f"[explain_unscored] {unscored_path} introuvable -- lancer d'abord "
              f"agents/prepare_route_folders.py --module {module}.")
        sys.exit(1)

    unscored = [s.strip() for s in unscored_path.read_text(encoding="utf-8").splitlines() if s.strip()]
    manual_stems = {p.stem for p in (dataset_dir / "masks_raw").glob("*.png")}

    last_row: dict[str, dict] = {}
    if prov_path.exists():
        with open(prov_path, encoding="utf-8-sig", newline="") as f:
            for row in csv.DictReader(f):
                last_row[Path(row["image"]).stem] = row   # derniere ligne = plus recente

    buckets: dict[str, list[str]] = {
        "manuel": [], "box_failed": [], "ok_sans_score": [], "jamais_traite": [], "autre": [],
    }
    for stem in unscored:
        if stem in manual_stems:
            buckets["manuel"].append(stem)
            continue
        row = last_row.get(stem)
        if row is None:
            buckets["jamais_traite"].append(stem)
        elif row.get("status") == "BOX_FAILED":
            buckets["box_failed"].append(stem)
        elif row.get("status") == "OK" and not row.get("sam_score"):
            buckets["ok_sans_score"].append(stem)
        else:
            buckets["autre"].append(stem)

    print(f"[explain_unscored] {module} -- {len(unscored)} image(s) dans {unscored_path.name}")
    print(f"  manuel (deja annote)                      : {len(buckets['manuel'])}")
    print(f"  box_failed (pose + fallback VLM echoues)  : {len(buckets['box_failed'])}")
    print(f"  ok_sans_score (premask genere, score non journalise) : {len(buckets['ok_sans_score'])}")
    print(f"  jamais_traite (aucune ligne provenance)   : {len(buckets['jamais_traite'])}")
    print(f"  autre (a investiguer)                     : {len(buckets['autre'])}")

    total_explained = len(unscored) - len(buckets["jamais_traite"]) - len(buckets["autre"])
    print(f"\n  {total_explained}/{len(unscored)} expliques par un etat de pipeline connu.")

    if buckets["jamais_traite"] or buckets["autre"]:
        print("\n  [!] Cas non expliques -- a investiguer :")
        for cat in ("jamais_traite", "autre"):
            for stem in buckets[cat]:
                print(f"    [{cat}] {stem}")
    else:
        print("  Aucun cas non explique.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Caracterise route_unscored.txt (croisement masks_raw/ + _provenance.csv) "
                     "-- lecture seule, ne modifie rien.")
    parser.add_argument("--module", required=True, choices=sorted(MODULE_ROOTS))
    args = parser.parse_args()
    main(args.module)

"""
Estime le cout cloud equivalent du temps GPU local cumule, a partir de
gpu_usage_log.csv (racine du depot). Convention du fichier de log documentee
dans CLAUDE.md, section "Traçage du temps GPU" - une ligne par run de calcul
substantiel (entrainement, generation batch >50 images, test de diagnostic
>15min), PAS les appels VLM/grounding ponctuels.

Les GPU locaux (RTX 5080/RTX 5060 Ti) coutent 0$ en pratique - l'estimation
sert uniquement de point de comparaison ("ce calcul aurait coute combien en
cloud"), pas une comptabilite reelle. Precision volontairement approximative.

Usage :
    py -3.12 gpu_cost_estimate.py
    py -3.12 gpu_cost_estimate.py --csv chemin/vers/log.csv
"""
import argparse
import csv
from collections import defaultdict
from pathlib import Path

DEFAULT_CSV = Path(__file__).parent / "gpu_usage_log.csv"

# Tarifs horaires de reference (cf. annexe traçage GPU) - utilises pour
# recalculer cout_estime_usd si une ligne l'a laisse vide.
CLOUD_RATES_USD_PER_HOUR = {
    "A100": 1.20,
    "H100": 2.40,
}
DEFAULT_RATE_NAME = "A100"


def load_rows(csv_path):
    with open(csv_path, encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f))


def resolve_cost(row, default_rate_name=DEFAULT_RATE_NAME):
    raw_cost = (row.get("cout_estime_usd") or "").strip()
    if raw_cost:
        return float(raw_cost)
    duree_h = float(row["duree_minutes"]) / 60.0
    return duree_h * CLOUD_RATES_USD_PER_HOUR[default_rate_name]


def summarize(rows):
    by_gpu = defaultdict(lambda: {"minutes": 0.0, "cost": 0.0})
    by_module = defaultdict(lambda: {"minutes": 0.0, "cost": 0.0})
    total_minutes, total_cost = 0.0, 0.0

    for row in rows:
        minutes = float(row["duree_minutes"])
        cost = resolve_cost(row)
        gpu, module = row["gpu"], row["module"]

        by_gpu[gpu]["minutes"] += minutes
        by_gpu[gpu]["cost"] += cost
        by_module[module]["minutes"] += minutes
        by_module[module]["cost"] += cost
        total_minutes += minutes
        total_cost += cost

    return by_gpu, by_module, total_minutes, total_cost


def print_report(rows):
    if not rows:
        print("Aucune ligne dans le log - rien a resumer.")
        return

    by_gpu, by_module, total_minutes, total_cost = summarize(rows)

    print(f"{len(rows)} run(s) logue(s)\n")

    print("=== Par GPU ===")
    for gpu, agg in sorted(by_gpu.items()):
        print(f"  {gpu:<12} {agg['minutes']/60:7.2f} h   ~${agg['cost']:.2f} equivalent cloud")

    print("\n=== Par module ===")
    for module, agg in sorted(by_module.items()):
        print(f"  {module:<32} {agg['minutes']/60:7.2f} h   ~${agg['cost']:.2f} equivalent cloud")

    print(f"\n=== Total ===\n  {total_minutes/60:.2f} h cumulees   ~${total_cost:.2f} equivalent cloud "
          f"(tarif de reference : {DEFAULT_RATE_NAME} ${CLOUD_RATES_USD_PER_HOUR[DEFAULT_RATE_NAME]:.2f}/h)")


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--csv", type=Path, default=DEFAULT_CSV, help="chemin du log CSV (defaut : gpu_usage_log.csv a la racine)")
    args = ap.parse_args()

    if not args.csv.exists():
        raise SystemExit(f"Log introuvable : {args.csv}")

    print_report(load_rows(args.csv))

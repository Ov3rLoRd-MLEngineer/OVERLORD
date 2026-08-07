"""Marque lora_priority=True pour une plage de frames deja loguees dans
DEMO/output/postprod_log.csv (consignes.txt 2026-08-06, point 4).

Candidat identifie par inspection visuelle directe (pas une heuristique) :
v2 (miku_demo_30s_v2.mp4), t=17.5s->19.0s, transition clip4->clip5 (plans
orbit), la Miku change de tenue (veste peplum+cravate -> robe sans manches
avec noeud) pendant la rotation camera, couleurs restees coherentes
(palette teal/noir/gris preservee). Cf. DOCS/MD/POSTPROD_PIPELINE_20260806.md
section "Candidat LoRA".

Usage (une fois la plage traitee par postprod_inpaint.py, frame globale =
nb de frames des videos avant v2 dans --videos + offset local ci-dessous) :
    py -3.12 agents/production_video/tag_lora_priority.py --start 1192 --end 1228
"""
import argparse
import csv
import os

POSTPROD_LOG = os.path.join("DEMO", "output", "postprod_log.csv")
CSV_FIELDS = ["frame", "hand_score", "foot_score", "inpaint_applied", "lora_priority", "elapsed_s", "final_path"]


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--start", type=int, required=True)
    p.add_argument("--end", type=int, required=True)
    p.add_argument("--log", default=POSTPROD_LOG)
    args = p.parse_args()

    if not os.path.exists(args.log):
        raise SystemExit(f"{args.log} introuvable -- rien a tagger pour l'instant")

    with open(args.log, encoding="utf-8") as f:
        rows = list(csv.DictReader(f))

    tagged = 0
    for row in rows:
        if args.start <= int(row["frame"]) <= args.end:
            row["lora_priority"] = "True"
            tagged += 1

    with open(args.log, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=CSV_FIELDS)
        w.writeheader()
        w.writerows(rows)

    print(f"RESULT: {tagged} ligne(s) taguee(s) lora_priority=True (frames {args.start}-{args.end})")


if __name__ == "__main__":
    main()

# ██████╗ ██╗   ██╗██████╗ ██████╗ ██╗      ██████╗ ██████╗ ██████╗
# ██╔═══██╗██║   ██║╚════██╗██╔══██╗██║     ██╔═══██╗██╔══██╗██╔══██╗
# ██║   ██║██║   ██║ █████╔╝██████╔╝██║     ██║   ██║██████╔╝██║  ██║
# ██║   ██║╚██╗ ██╔╝ ╚═══██╗██╔══██╗██║     ██║   ██║██╔══██╗██║  ██║
# ╚██████╔╝ ╚████╔╝ ██████╔╝██║  ██║███████╗╚██████╔╝██║  ██║██████╔╝
# ╚═════╝   ╚═══╝  ╚═════╝ ╚═╝  ╚═╝╚══════╝ ╚═════╝ ╚═╝  ╚═╝╚═════╝
# Ov3rLoRd -- pipeline de production anime autonome (ComfyUI)
# https://github.com/Ov3rLoRd-MLEngineer
#
# backfill_sam_scores.py — recalcule le score SAM natif manquant sur les
# lignes de provenance ecrites AVANT le commit 2fafc04 (2026-07-24 23:15:56,
# "segnet_premask: exploite le score de confiance natif de SAM").
#
# CONTEXTE (decision documentee, cf. session du 2026-07-28) : PR #20 a montre
# 124 lignes handsegnet status=OK sans sam_score, toutes fallback grounding
# VLM. Inspection de agents/segnet_premask.py::_infer_union() et
# handsegnet/infer.py::generate_part_mask() : le score SAM natif (scores[0]
# du predictor, deja calcule a CHAQUE prediction reussie) est deja journalise
# pour TOUTE bbox, quelle que soit sa source (dwpose ou grounding) -- aucun
# gap de code, le mecanisme existe deja et est source-agnostique. Verification
# des timestamps : les 124 lignes vont de 2026-07-24T00:23:46 a
# 2026-07-24T01:53:44, TOUTES anterieures au commit 2fafc04 (23:15:56) qui a
# introduit cette colonne -- confirme qu'il s'agit de lignes historiques
# ecrites par une version du pipeline sans ce logging, pas d'un trou dans le
# code actuel. Rien a "reinventer" : on recalcule juste, avec le code actuel,
# ce que le pipeline aurait journalise si ces lignes avaient ete ecrites apres
# le commit.
#
# METHODE : reutilise la bbox englobante deja enregistree dans
# _provenance.csv (colonnes x/y/w/h) et relance UNE prediction SAM dessus
# (meme fonction generate_part_mask/generate_foot_mask que le pipeline live,
# return_score=True) pour en extraire scores[0]. Le masque produit par cet
# appel est ECARTE (fichier temporaire supprime aussitot) -- le premask deja
# sur disque n'est PAS regenere/ecrase, conformement a la consigne de
# session. mask_pct de la nouvelle ligne provenance est recalcule depuis le
# premask EXISTANT sur disque (fidele a l'artefact reel), pas depuis le
# masque temporaire.
#
# LIMITE CONNUE (a assumer, pas a cacher) : pour les bbox multi-instance
# (box_source="qwenvl_grounding_multi(N)"), seule la bbox ENGLOBANTE est
# journalisee dans le CSV -- les N bbox individuelles ayant servi a
# l'union du masque original sont perdues. Le score recalcule ici correspond
# donc a la confiance de SAM sur la region englobante en UNE passe, pas au
# minimum des scores par instance comme le fait le pipeline live pour une
# nouvelle image (agents/segnet_premask.py::_infer_union, cf. son
# docstring). C'est un signal SAM natif reel et directement comparable sur
# la meme echelle 0-1 (meme predictor, meme checkpoint) au seuil 0.62 deja
# calibre en PR #17 -- juste pas une reproduction methodologique exacte du
# score multi-instance original. Recalculer les bbox individuelles
# demanderait de relancer le grounding VLM (cout GPU/API + risque de
# resultat different d'aujourd'hui), hors perimetre de ce backfill.
#
# Une nouvelle ligne est AJOUTEE (append, jamais d'edition en place -- meme
# convention que _provenance.csv partout ailleurs) avec box_source suffixe
# "_backfilled" pour tracabilite (reste compatible avec tout code verifiant
# box_source.startswith("qwenvl_grounding")).
#
# Usage :
#   py -3.12 agents/backfill_sam_scores.py --module handsegnet --dry-run
#   py -3.12 agents/backfill_sam_scores.py --module handsegnet
#   py -3.12 agents/backfill_sam_scores.py --module handsegnet --limit 5   (test rapide)

import argparse
import csv
import importlib
import os
import sys
import time
from datetime import datetime
from pathlib import Path

# GPU 1 (RTX 5060 Ti) uniquement -- ne jamais toucher a la RTX 5080 (GPU 0).
# Doit etre fixe AVANT l'import de torch (fait indirectement via infer.py).
os.environ.setdefault("CUDA_VISIBLE_DEVICES", "1")

import numpy as np  # noqa: E402
from PIL import Image  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))
from agents.route_by_sam_confidence import MODULE_ROOTS   # noqa: E402
from agents.segnet_premask import _append_provenance   # noqa: E402

# Nom de la fonction d'inference exposee par <module>/infer.py -- footsegnet
# est l'exception (generate_foot_mask), les 3 autres partagent generate_part_mask
# (cf. commit 2fafc04). Seul handsegnet est exerce cette session (perimetre
# de la tache) ; les autres entrees sont verifiees mais non testees ici.
INFER_FN_NAME = {
    "footsegnet": "generate_foot_mask",
    "handsegnet": "generate_part_mask",
    "bodysegnet": "generate_part_mask",
    "facesegnet": "generate_part_mask",
}


def _load_infer_fn(module: str):
    module_dir = MODULE_ROOTS[module]
    if str(module_dir) not in sys.path:
        sys.path.insert(0, str(module_dir))
    infer_module = importlib.import_module("infer")
    return getattr(infer_module, INFER_FN_NAME[module])


def main(module: str, limit: int | None, dry_run: bool) -> None:
    dataset_dir = MODULE_ROOTS[module] / "dataset"
    raw_dir = dataset_dir / "raw"
    premasks_dir = dataset_dir / "premasks"
    prov_path = premasks_dir / "_provenance.csv"

    last_row: dict[str, dict] = {}
    with open(prov_path, encoding="utf-8-sig", newline="") as f:
        for row in csv.DictReader(f):
            last_row[Path(row["image"]).stem] = row

    targets = sorted(
        (stem, row) for stem, row in last_row.items()
        if row.get("status") == "OK" and not row.get("sam_score")
    )
    if limit:
        targets = targets[:limit]

    print(f"[backfill_sam_scores] {module} : {len(targets)} ligne(s) OK sans sam_score a recalculer")
    if not targets:
        return

    infer_fn = _load_infer_fn(module)
    tmp_dir = premasks_dir / "_backfill_tmp"
    tmp_dir.mkdir(exist_ok=True)

    new_rows = []
    skipped = []
    try:
        for stem, row in targets:
            img_path = raw_dir / row["image"]
            premask_path = premasks_dir / f"{stem}.png"
            if not img_path.exists():
                skipped.append((stem, "image source introuvable"))
                continue
            if not premask_path.exists():
                skipped.append((stem, "premask existant introuvable (mask_pct incalculable)"))
                continue

            box = (int(row["x"]), int(row["y"]), int(row["w"]), int(row["h"]))
            tmp_out = tmp_dir / f"{stem}.png"
            t0 = time.time()
            result = infer_fn(frame_path=str(img_path), zone=box, output_path=str(tmp_out),
                              threshold=0.5, pipeline_convention=False, feather_px=0,
                              return_score=True)
            tmp_out.unlink(missing_ok=True)
            elapsed = time.time() - t0

            if result is None:
                skipped.append((stem, "inference SAM echouee sur la bbox enregistree"))
                continue
            _, sam_score = result

            mask_pct = float((np.array(Image.open(premask_path).convert("L")) > 127).mean() * 100)
            print(f"  {stem} : sam_score={sam_score:.3f} ({elapsed:.1f}s)")
            new_rows.append({
                "timestamp": datetime.now().isoformat(timespec="seconds"),
                "image": row["image"], "category": row["category"],
                "box_source": row["box_source"] + "_backfilled",
                "x": row["x"], "y": row["y"], "w": row["w"], "h": row["h"],
                "status": "OK", "mask_pct": round(mask_pct, 2),
                "iou_manual": row.get("iou_manual", ""),
                "sam_score": round(sam_score, 3),
                "elapsed_s": round(elapsed, 1),
            })
    finally:
        try:
            tmp_dir.rmdir()
        except OSError:
            pass   # fichiers residuels (echec en cours de boucle) -- laisse pour inspection

    if skipped:
        print(f"[backfill_sam_scores] {len(skipped)} ligne(s) ignoree(s) :")
        for stem, reason in skipped:
            print(f"    {stem} : {reason}")

    if dry_run:
        print(f"[backfill_sam_scores] --dry-run : {len(new_rows)} ligne(s) seraient ajoutees "
              f"a {prov_path} (aucune ecriture).")
        return

    if new_rows:
        _append_provenance(prov_path, new_rows)
        print(f"[backfill_sam_scores] {len(new_rows)} ligne(s) ajoutee(s) -> {prov_path}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Recalcule et journalise (append) le score SAM natif pour les lignes "
                     "OK de _provenance.csv anterieures au commit 2fafc04 (sam_score jamais "
                     "journalise) -- ne regenere pas les premasks existants.")
    parser.add_argument("--module", required=True, choices=sorted(MODULE_ROOTS))
    parser.add_argument("--limit", type=int, default=None, help="Limiter aux N premieres lignes (test)")
    parser.add_argument("--dry-run", action="store_true", help="N'ecrit rien, affiche juste ce qui serait fait")
    args = parser.parse_args()
    main(args.module, args.limit, args.dry_run)

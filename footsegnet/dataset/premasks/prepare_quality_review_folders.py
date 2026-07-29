"""
prepare_quality_review_folders.py — FootSegNet (Ov3rLoRd Pipeline)

Materialise en dossiers de revue visuelle les entrees "a_corriger" du
dernier passage de quality_sort.py (footsegnet/controlnet/quality_report.json),
sur le meme principe que prepare_review_folder.py (liens physiques Windows
via mklink /H vers dataset/raw/, aucune copie de donnees) mais source
differente : quality_sort.py (fragmentation/couverture/fallback VLM), pas
route_by_sam_confidence.py (score SAM).

Trois dossiers, pas un seul : les 186 cas se repartissent en trois familles
de defaut/priorite tres differentes (2026-07-29) :
  - _review_manual_fragmented/  : masques MANUELS (verite terrain, faisant
    partie des 300 images deja utilisees pour entrainer et publier le
    checkpoint HuggingFace, val_IoU=0.9277) signales fragmentes par le
    nouveau critere. PRIORITE HAUTE -- corriger ceux-la ameliore
    directement un futur re-entrainement sur le MEME jeu de 300 images.
  - _review_auto_fragmented/    : pre-masques auto fragmentes, partie de
    l'extension du dataset brut (315 images auto, au-dela des 300
    manuelles) -- ne concerne aucun entrainement deja publie, pertinent
    seulement pour une extension future du dataset d'entrainement.
  - _review_auto_other/         : pre-masques auto signales pour une autre
    raison (bbox via fallback grounding VLM, couverture hors plage) --
    meme portee que ci-dessus (extension future), mais type de correction
    different (recadrage/bbox, pas retrait de fragment parasite).

A relancer a chaque fois que quality_report.json change (py -3.12
footsegnet/controlnet/quality_sort.py --write-manifest au prealable) --
vide et recree les trois dossiers a chaque execution.

Usage :
    py -3.12 footsegnet/dataset/premasks/prepare_quality_review_folders.py
"""
import json
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent            # dataset/premasks/
DATASET_ROOT = HERE.parent                          # dataset/
RAW_DIR = DATASET_ROOT / "raw"
QUALITY_REPORT = DATASET_ROOT.parent / "controlnet" / "quality_report.json"

BUCKETS = {
    "_review_manual_fragmented": DATASET_ROOT / "_review_manual_fragmented",
    "_review_auto_fragmented": DATASET_ROOT / "_review_auto_fragmented",
    "_review_auto_other": DATASET_ROOT / "_review_auto_other",
}


def _bucket_of(entry: dict) -> str | None:
    if entry["category"] != "a_corriger":
        return None
    if entry.get("mask_source") == "manual":
        return "_review_manual_fragmented"
    if "components" in entry:
        return "_review_auto_fragmented"
    return "_review_auto_other"


def _hardlink_folder(dest_dir: Path, stems: list[str]) -> tuple[int, list[str]]:
    if dest_dir.exists():
        for f in dest_dir.iterdir():
            f.unlink()
    else:
        dest_dir.mkdir(parents=True)

    linked, missing = 0, []
    for stem in sorted(stems):
        src = RAW_DIR / f"{stem}.png"
        if not src.exists():
            missing.append(stem)
            continue
        dst = dest_dir / f"{stem}.png"
        result = subprocess.run(
            ["cmd", "/c", "mklink", "/H", str(dst), str(src)],
            capture_output=True, text=True,
        )
        if result.returncode != 0:
            print(f"[prepare_quality_review_folders]   echec lien pour {stem}: {result.stderr.strip()}")
            continue
        linked += 1
    return linked, missing


def main() -> None:
    if not QUALITY_REPORT.exists():
        print(f"[prepare_quality_review_folders] Introuvable : {QUALITY_REPORT} -- "
              f"lancer footsegnet/controlnet/quality_sort.py --write-manifest au prealable.")
        sys.exit(1)

    entries = json.loads(QUALITY_REPORT.read_text(encoding="utf-8"))
    buckets: dict[str, list[str]] = {name: [] for name in BUCKETS}
    for entry in entries:
        bucket = _bucket_of(entry)
        if bucket is not None:
            buckets[bucket].append(entry["stem"])

    total_linked = 0
    for name, dest_dir in BUCKETS.items():
        stems = buckets[name]
        linked, missing = _hardlink_folder(dest_dir, stems)
        total_linked += linked
        print(f"[prepare_quality_review_folders] {name}/ : {linked}/{len(stems)} lien(s) ({dest_dir})")
        if missing:
            print(f"  [!] introuvable(s) dans {RAW_DIR} : {missing}")

    print(f"[prepare_quality_review_folders] Total : {total_linked} lien(s) sur "
          f"{sum(len(s) for s in buckets.values())} entree(s) 'a_corriger'.")


if __name__ == "__main__":
    main()

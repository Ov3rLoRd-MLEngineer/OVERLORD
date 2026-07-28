# ██████╗ ██╗   ██╗██████╗ ██████╗ ██╗      ██████╗ ██████╗ ██████╗
# ██╔═══██╗██║   ██║╚════██╗██╔══██╗██║     ██╔═══██╗██╔══██╗██╔══██╗
# ██║   ██║██║   ██║ █████╔╝██████╔╝██║     ██║   ██║██████╔╝██║  ██║
# ██║   ██║╚██╗ ██╔╝ ╚═══██╗██╔══██╗██║     ██║   ██║██╔══██╗██║  ██║
# ╚██████╔╝ ╚████╔╝ ██████╔╝██║  ██║███████╗╚██████╔╝██║  ██║██████╔╝
# ╚═════╝   ╚═══╝  ╚═════╝ ╚═╝  ╚═╝╚══════╝ ╚═════╝ ╚═╝  ╚═╝╚═════╝
# Ov3rLoRd -- pipeline de production anime autonome (ComfyUI)
# https://github.com/Ov3rLoRd-MLEngineer
#
# prepare_route_folders.py — materialise le routage SAM confidence en dossiers
#
# Generalise footsegnet/dataset/premasks/prepare_review_folder.py (liens
# physiques Windows, pas de copie de donnees) : lit route_manual_review.txt /
# route_auto_sort.txt (produits par agents/route_by_sam_confidence.py, cf. PR
# #17) pour un module donne, et materialise DEUX dossiers de liens vers
# dataset/raw/ pour une revue visuelle facile :
#   - dataset/_route_review/  (score SAM < seuil calibre)
#   - dataset/_route_auto/    (score SAM >= seuil calibre)
#
# Calcule aussi et journalise a part (fichier route_unscored.txt, PAS un
# dossier -- ces images ne sont ni "review" ni "auto", volontairement non
# classees) les images de dataset/raw/ qui n'ont AUCUN score SAM exploitable
# (jamais passees par batch_premask, echec BOX_FAILED/INFER_FAILED, ou score
# non journalise -- cf. commentaire de tete de route_by_sam_confidence.py sur
# la couverture partielle des scores pour handsegnet).
#
# Ne touche jamais dataset/masks_raw/ (annotations manuelles) ni les PNG de
# dataset/premasks/ -- lecture seule sur route_*.txt et dataset/raw/, les
# dossiers _route_review//_route_auto/ ne contiennent que des liens physiques
# (mklink /H) recrees a chaque execution, jamais les fichiers reels.
#
# Usage :
#   py -3.12 agents/prepare_route_folders.py --module handsegnet

import argparse
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))
from agents.route_by_sam_confidence import MODULE_ROOTS   # noqa: E402


def _read_stems(path: Path) -> set[str]:
    if not path.exists():
        return set()
    return {s.strip() for s in path.read_text(encoding="utf-8").splitlines() if s.strip()}


def _hardlink_folder(dest_dir: Path, stems: set[str], raw_dir: Path) -> tuple[int, list[str]]:
    if dest_dir.exists():
        for f in dest_dir.iterdir():
            f.unlink()
    else:
        dest_dir.mkdir(parents=True)

    linked, missing = 0, []
    for stem in sorted(stems):
        src = raw_dir / f"{stem}.png"
        if not src.exists():
            missing.append(stem)
            continue
        dst = dest_dir / f"{stem}.png"
        result = subprocess.run(
            ["cmd", "/c", "mklink", "/H", str(dst), str(src)],
            capture_output=True, text=True,
        )
        if result.returncode != 0:
            print(f"[prepare_route_folders]   echec lien pour {stem}: {result.stderr.strip()}")
            continue
        linked += 1
    return linked, missing


def main(module: str) -> None:
    module_root = MODULE_ROOTS[module]
    dataset_dir = module_root / "dataset"
    premasks_dir = dataset_dir / "premasks"
    raw_dir = dataset_dir / "raw"

    manual_stems = _read_stems(premasks_dir / "route_manual_review.txt")
    auto_stems = _read_stems(premasks_dir / "route_auto_sort.txt")

    if not manual_stems and not auto_stems:
        print(f"[prepare_route_folders] {module} : route_manual_review.txt et "
              f"route_auto_sort.txt introuvables/vides dans {premasks_dir} -- "
              f"lancer d'abord agents/route_by_sam_confidence.py --module {module}.")
        sys.exit(1)

    raw_stems = {p.stem for p in raw_dir.glob("*.png")}
    unscored_stems = raw_stems - manual_stems - auto_stems

    review_dir = dataset_dir / "_route_review"
    auto_dir = dataset_dir / "_route_auto"

    linked_review, missing_review = _hardlink_folder(review_dir, manual_stems, raw_dir)
    linked_auto, missing_auto = _hardlink_folder(auto_dir, auto_stems, raw_dir)

    unscored_path = premasks_dir / "route_unscored.txt"
    unscored_path.write_text(
        "".join(f"{stem}\n" for stem in sorted(unscored_stems)), encoding="utf-8")

    print(f"[prepare_route_folders] {module} -- {len(raw_stems)} image(s) dans {raw_dir}")
    print(f"  _route_review/  : {linked_review}/{len(manual_stems)} lien(s) ({review_dir})")
    print(f"  _route_auto/    : {linked_auto}/{len(auto_stems)} lien(s) ({auto_dir})")
    print(f"  route_unscored.txt : {len(unscored_stems)} image(s) SANS score SAM exploitable "
          f"-- ni review ni auto, a traiter manuellement ({unscored_path})")
    if missing_review or missing_auto:
        print(f"  [!] introuvable(s) dans {raw_dir} : "
              f"review={missing_review} auto={missing_auto}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Materialise le routage SAM confidence (route_by_sam_confidence.py) "
                     "en dossiers de liens physiques _route_review/ et _route_auto/, et "
                     "journalise a part les images sans score SAM exploitable.")
    parser.add_argument("--module", required=True, choices=sorted(MODULE_ROOTS))
    args = parser.parse_args()
    main(args.module)

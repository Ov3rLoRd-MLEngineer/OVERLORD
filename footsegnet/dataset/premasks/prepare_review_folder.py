"""
prepare_review_folder.py — FootSegNet (Ov3rLoRd Pipeline)

annotate.py n'accepte pas de liste de stems en entree (seulement un dossier
--images, tout le contenu est liste). Ce script prepare un dossier ne
contenant QUE les images de route_manual_review.txt (liens physiques
Windows - mklink /H - donc aucune copie de donnees, aucun octet duplique),
pour pouvoir lancer annotate.py --by-confidence dessus sans ouvrir les 519
images du dataset complet.

Les liens pointent vers les fichiers reels de dataset/raw/ : annotate.py
peut les lire normalement, et --masks/--premasks continuent de pointer vers
les vrais dataset/masks_raw/ et dataset/premasks/ (aucun changement de ce
cote - les corrections s'ecrivent au bon endroit).

A relancer a chaque fois que route_manual_review.txt change (vide et
recree le dossier a chaque execution, pour ne jamais laisser une image
obsolete trainer si la liste a bouge).

Usage :
    py -3.12 footsegnet/dataset/premasks/prepare_review_folder.py
"""
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent          # dataset/premasks/
DATASET_ROOT = HERE.parent                       # dataset/
RAW_DIR = DATASET_ROOT / "raw"
REVIEW_DIR = DATASET_ROOT / "_review_manual"
ROUTE_MANUAL = HERE / "route_manual_review.txt"


def main():
    if not ROUTE_MANUAL.exists():
        print(f"[prepare_review_folder] Introuvable : {ROUTE_MANUAL}")
        sys.exit(1)

    stems = [s.strip() for s in ROUTE_MANUAL.read_text(encoding="utf-8").splitlines() if s.strip()]
    if not stems:
        print(f"[prepare_review_folder] {ROUTE_MANUAL} est vide - rien a faire.")
        sys.exit(0)

    # Vide le dossier (liens uniquement - supprimer un lien physique ne
    # touche jamais le fichier reel dans dataset/raw/).
    if REVIEW_DIR.exists():
        for f in REVIEW_DIR.iterdir():
            f.unlink()
    else:
        REVIEW_DIR.mkdir(parents=True)

    linked, missing = 0, []
    for stem in stems:
        src = RAW_DIR / f"{stem}.png"
        if not src.exists():
            missing.append(stem)
            continue
        dst = REVIEW_DIR / f"{stem}.png"
        result = subprocess.run(
            ["cmd", "/c", "mklink", "/H", str(dst), str(src)],
            capture_output=True, text=True,
        )
        if result.returncode != 0:
            print(f"[prepare_review_folder] echec lien pour {stem}: {result.stderr.strip()}")
            continue
        linked += 1

    print(f"[prepare_review_folder] {linked}/{len(stems)} image(s) lien(s) dans {REVIEW_DIR}")
    if missing:
        print(f"[prepare_review_folder] introuvable(s) dans {RAW_DIR} : {missing}")


if __name__ == "__main__":
    main()

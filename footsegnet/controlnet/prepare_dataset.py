# ██████╗ ██╗   ██╗██████╗ ██████╗ ██╗      ██████╗ ██████╗ ██████╗
# ██╔═══██╗██║   ██║╚════██╗██╔══██╗██║     ██╔═══██╗██╔══██╗██╔══██╗
# ██║   ██║██║   ██║ █████╔╝██████╔╝██║     ██║   ██║██████╔╝██║  ██║
# ██║   ██║╚██╗ ██╔╝ ╚═══██╗██╔══██╗██║     ██║   ██║██╔══██╗██║  ██║
# ╚██████╔╝ ╚████╔╝ ██████╔╝██║  ██║███████╗╚██████╔╝██║  ██║██████╔╝
# ╚═════╝   ╚═══╝  ╚═════╝ ╚═╝  ╚═╝╚══════╝ ╚═════╝ ╚═╝  ╚═╝╚═════╝
# Ov3rLoRd -- pipeline de production anime autonome (ComfyUI)
# https://github.com/Ov3rLoRd-MLEngineer
#
# prepare_dataset.py — FootSegNet -> Control-LoRA (Ov3rLoRd Pipeline)
#
# Orchestration bout-en-bout du dataset de conditionnement ControlNet
# (image, carte de segmentation pied/chaussure) :
#
#   1. GÉNÉRATION   generate_dataset.generate_batch() — nouvelles images brutes
#                    (réutilise le générateur FootSegNet existant, wildcards
#                    v2 : variété x4 + cohérence genre/vêtements)
#   2. PRÉ-MASQUE    agents.segnet_premask.run_batch() — masque auto via le
#                    SAM fine-tuné FootSegNet v1, bbox DWPose + fallback
#                    grounding VLM (même chaîne que footsegnet\batch_premask.py)
#   3. ASSEMBLAGE    paires (image, masque) prêtes à l'emploi dans
#                    controlnet\dataset\{images,conditioning_images}\ +
#                    manifest.jsonl (format consommé par train_control_lora.py)
#
# Le masque manuel (dataset\masks_raw\, vérité terrain annotée à la main)
# est TOUJOURS préféré au pré-masque auto quand les deux existent.
#
# Convention masque conditionnement : BLANC (255) = pied/chaussure, NOIR (0)
# = fond (convention ML — cf. footsegnet\README.md), pas la convention
# pipeline inpaint (infer.py y sort déjà en convention ML via
# pipeline_convention=False, utilisée par batch_premask/segnet_premask).
#
# Usage :
#   py -3.12 prepare_dataset.py --count 200                 (génère 200 images + assemble)
#   py -3.12 prepare_dataset.py --count 20 --premask-limit 20 (petit lot de test)
#   py -3.12 prepare_dataset.py --count 0                    (assemble seulement, pas de génération)
#   py -3.12 prepare_dataset.py --count 5 --dry-run          (prompts sans appel ComfyUI)

import argparse
import json
import shutil
import sys
from pathlib import Path

FOOTSEGNET_ROOT = Path(r"D:\OVERLORD\footsegnet")
REPO_ROOT = Path(r"D:\OVERLORD")
for _p in (str(FOOTSEGNET_ROOT), str(REPO_ROOT)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from generate_dataset import generate_batch, BASE_SEED       # noqa: E402
from infer import generate_foot_mask                          # noqa: E402
from _pose_box import foot_box_for_image                      # noqa: E402
from agents.segnet_premask import PremaskCategory, run_batch  # noqa: E402

CONTROLNET_ROOT = FOOTSEGNET_ROOT / "controlnet"
CN_DATASET_ROOT = CONTROLNET_ROOT / "dataset"
IMAGES_DIR      = CN_DATASET_ROOT / "images"
COND_DIR        = CN_DATASET_ROOT / "conditioning_images"
MANIFEST_PATH   = CN_DATASET_ROOT / "manifest.jsonl"

RAW_DIR           = FOOTSEGNET_ROOT / "dataset" / "raw"
MASKS_RAW_DIR      = FOOTSEGNET_ROOT / "dataset" / "masks_raw"
PREMASKS_DIR        = FOOTSEGNET_ROOT / "dataset" / "premasks"
RAW_MANIFEST_PATH  = RAW_DIR / "manifest.json"

DEFAULT_GROUNDING_OBJECT = "the character's shoes or feet"

FALLBACK_TEXT = ("score_9, score_8_up, source_anime, full body, "
                  "feet and shoes visible, anime style")


def _next_start_index() -> int:
    """Premier index libre après la dernière image existante dans dataset\\raw\\."""
    existing = []
    for p in RAW_DIR.glob("footsegnet_*.png"):
        suffix = p.stem.rsplit("_", 1)[-1]
        if suffix.isdigit():
            existing.append(int(suffix))
    return (max(existing) + 1) if existing else 0


def _load_raw_manifest() -> dict:
    if not RAW_MANIFEST_PATH.exists():
        return {}
    try:
        return json.loads(RAW_MANIFEST_PATH.read_text(encoding="utf-8")).get("images", {})
    except Exception:
        print(f"[controlnet_prep] WARN : manifest illisible ({RAW_MANIFEST_PATH})")
        return {}


def _foot_box(image_path: Path):
    # person_index="largest" : même choix que footsegnet\batch_premask.py —
    # cible le sujet principal, pas people[0] (personnage secondaire possible).
    return foot_box_for_image(image_path, person_index="largest")


def run_premask(limit: int | None, clean: bool, refine: bool, no_fallback: bool,
                 threshold: float, grounding_margin: int) -> list[dict]:
    """Génère les pré-masques manquants (dataset\\premasks\\) — même chaîne
    que footsegnet\\batch_premask.py, appelée directement pour rester dans
    un seul process (pas de subprocess)."""
    categories = [PremaskCategory(
        name=None,
        grounding_object=DEFAULT_GROUNDING_OBJECT,
        primary_box_fn=_foot_box,
        infer_kwargs={"refine": refine},
    )]
    return run_batch(
        "footsegnet", FOOTSEGNET_ROOT / "dataset", generate_foot_mask, categories,
        limit=limit, only=None, clean=clean, skip_existing=True, force=False,
        from_failures=False, threshold=threshold, grounding_margin=grounding_margin,
        no_fallback=no_fallback,
    )


def assemble_pairs(force: bool) -> tuple[int, int, list[str]]:
    """Copie les paires (image, masque) prêtes à l'emploi dans
    controlnet\\dataset\\ et écrit manifest.jsonl.

    Masque manuel (masks_raw\\, vérité terrain) prioritaire sur le pré-masque
    auto (premasks\\) quand les deux existent pour la même image.

    Returns:
        (nb paires masque manuel, nb paires masque auto, stems sans masque)
    """
    IMAGES_DIR.mkdir(parents=True, exist_ok=True)
    COND_DIR.mkdir(parents=True, exist_ok=True)
    raw_manifest = _load_raw_manifest()

    n_manual, n_auto = 0, 0
    missing: list[str] = []
    entries: list[dict] = []

    for img_path in sorted(RAW_DIR.iterdir()):
        if img_path.suffix.lower() != ".png" or img_path.name.startswith("_"):
            continue
        stem = img_path.stem
        manual_mask = MASKS_RAW_DIR / f"{stem}.png"
        auto_mask = PREMASKS_DIR / f"{stem}.png"

        if manual_mask.exists():
            mask_path, source = manual_mask, "manual"
        elif auto_mask.exists():
            mask_path, source = auto_mask, "auto"
        else:
            missing.append(stem)
            continue

        dest_img = IMAGES_DIR / f"{stem}.png"
        dest_mask = COND_DIR / f"{stem}.png"
        if force or not dest_img.exists() or not dest_mask.exists():
            shutil.copy2(img_path, dest_img)      # ADR-007 : copy2, jamais move
            shutil.copy2(mask_path, dest_mask)

        info = raw_manifest.get(img_path.name, {})
        entries.append({
            "file_name": f"images/{stem}.png",
            "conditioning_image": f"conditioning_images/{stem}.png",
            "text": info.get("prompt", FALLBACK_TEXT),
            "mask_source": source,
        })
        if source == "manual":
            n_manual += 1
        else:
            n_auto += 1

    MANIFEST_PATH.write_text(
        "\n".join(json.dumps(e, ensure_ascii=False) for e in entries),
        encoding="utf-8",
    )
    return n_manual, n_auto, missing


def main() -> None:
    parser = argparse.ArgumentParser(
        description="FootSegNet -> Control-LoRA : génération + pré-masque + "
                     "assemblage des paires (image, carte de segmentation)"
    )
    parser.add_argument("--count", type=int, default=0,
                        help="Nombre de nouvelles images à générer (0 = aucune génération, assemble seulement)")
    parser.add_argument("--start-index", type=int, default=None,
                        help="Index de départ (défaut : auto, après la dernière image existante)")
    parser.add_argument("--base-seed", type=int, default=BASE_SEED)
    parser.add_argument("--skip-premask", action="store_true",
                        help="Ne pas (re)générer les pré-masques auto (utilise dataset\\premasks\\ existant)")
    parser.add_argument("--premask-limit", type=int, default=None,
                        help="Limiter le nombre de pré-masques générés dans cette passe (test rapide)")
    parser.add_argument("--clean", action="store_true",
                        help="Nettoyage composantes connexes des pré-masques (cf. batch_premask.py)")
    parser.add_argument("--no-refine", dest="refine", action="store_false", default=True,
                        help="Désactive le raffinement itératif SAM (cf. infer.py)")
    parser.add_argument("--no-fallback", action="store_true",
                        help="Désactive le fallback grounding VLM (DWPose seul)")
    parser.add_argument("--threshold", type=float, default=0.5)
    parser.add_argument("--grounding-margin", type=int, default=20)
    parser.add_argument("--force", action="store_true",
                        help="Recopie même les paires déjà assemblées dans controlnet\\dataset\\")
    parser.add_argument("--dry-run", action="store_true",
                        help="Génération en dry-run (aucun appel ComfyUI) ; pré-masque/assemblage ignorés")
    args = parser.parse_args()

    if args.count > 0:
        start = args.start_index if args.start_index is not None else _next_start_index()
        print(f"[controlnet_prep] Génération de {args.count} image(s) à partir de l'index {start}")
        n = generate_batch(args.count, start, args.base_seed, args.dry_run)
        print(f"[controlnet_prep] {n}/{args.count} image(s) générée(s)")

    if args.dry_run:
        print("[controlnet_prep] --dry-run : pré-masque/assemblage ignorés (pas de nouvelle image réelle)")
        return

    if not args.skip_premask:
        print("[controlnet_prep] Génération des pré-masques auto (pose DWPose + fallback grounding VLM)...")
        run_premask(args.premask_limit, args.clean, args.refine, args.no_fallback,
                    args.threshold, args.grounding_margin)

    n_manual, n_auto, missing = assemble_pairs(args.force)
    print(f"\n[controlnet_prep] Dataset ControlNet : {n_manual} paire(s) masque manuel, "
          f"{n_auto} paire(s) masque auto, {n_manual + n_auto} au total, "
          f"{len(missing)} image(s) sans masque (ignorée(s))")
    print(f"[controlnet_prep] -> {CN_DATASET_ROOT}")
    if missing:
        preview = ", ".join(missing[:10])
        print(f"[controlnet_prep] Sans masque (ni manuel ni auto) : {preview}"
              f"{' ...' if len(missing) > 10 else ''}")


if __name__ == "__main__":
    main()

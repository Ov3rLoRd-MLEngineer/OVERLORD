# skeleton_remapper.py — Ov3rLoRd Pipeline
# Redimensionne et centre les squelettes DWPose (912x912 fond noir)
# vers la résolution cible 1344x768 de la génération SDXL
# py -3.12

import argparse
import os
from pathlib import Path

import numpy as np
from PIL import Image


# ─────────────────────────────────────────────
#  CORE : UN SQUELETTE
# ─────────────────────────────────────────────

def resize_skeleton_to_target(
    skeleton_path: str,
    target_w: int = 1344,
    target_h: int = 768,
    output_path: str | None = None,
    padding_ratio: float = 0.85,
    vertical_bias: float = 0.50,
) -> Image.Image:
    """
    Upscale direct 910x512 → target_w x target_h (LANCZOS).
    Pas de bounding box, pas de recentrage — position spatiale préservée.
    padding_ratio et vertical_bias conservés pour compatibilité CLI mais ignorés.
    """
    img = Image.open(skeleton_path).convert("RGB")
    result = img.resize((target_w, target_h), Image.LANCZOS)

    if output_path:
        result.save(output_path)

    return result


# ─────────────────────────────────────────────
#  BATCH : RÉPERTOIRE ENTIER
# ─────────────────────────────────────────────

def batch_resize_skeletons(
    input_dir: str,
    output_dir: str,
    target_w: int = 1344,
    target_h: int = 768,
    pattern: str = "*.png",
    overwrite: bool = False,
    verbose: bool = True,
) -> int:
    """
    Redimensionne tous les squelettes d'un répertoire.
    Retourne le nombre de fichiers traités.
    """
    input_dir  = Path(input_dir)
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    files = sorted(input_dir.glob(pattern))
    if not files:
        print(f"[skeleton_remapper] Aucun fichier trouvé dans {input_dir}")
        return 0

    count = 0
    skipped = 0

    for f in files:
        out = output_dir / f.name
        if out.exists() and not overwrite:
            skipped += 1
            continue

        try:
            resize_skeleton_to_target(str(f), target_w, target_h, str(out))
            count += 1
            if verbose and count % 50 == 0:
                print(f"[skeleton_remapper] {count}/{len(files)} traités...")
        except Exception as e:
            print(f"[skeleton_remapper] ERREUR {f.name} : {e}")

    if verbose:
        print(
            f"[skeleton_remapper] Terminé : {count} traités, "
            f"{skipped} ignorés (déjà existants)"
        )

    return count


# ─────────────────────────────────────────────
#  VALIDATION VISUELLE : 1 SQUELETTE
# ─────────────────────────────────────────────

def preview_remap(skeleton_path: str, output_path: str) -> None:
    """Génère un aperçu avec grille de référence pour vérification visuelle."""
    result = resize_skeleton_to_target(skeleton_path, 1344, 768)
    arr = np.array(result)

    # Grille de référence légère (lignes tous les 192px H, 128px V)
    for x in range(0, 1344, 192):
        arr[:, x] = np.clip(arr[:, x].astype(int) + 20, 0, 255)
    for y in range(0, 768, 128):
        arr[y, :] = np.clip(arr[y, :].astype(int) + 20, 0, 255)

    Image.fromarray(arr.astype(np.uint8)).save(output_path)
    print(f"[skeleton_remapper] Preview sauvé : {output_path}")


# ─────────────────────────────────────────────
#  CLI
# ─────────────────────────────────────────────

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Ov3rLoRd — Skeleton Remapper")
    subparsers = parser.add_subparsers(dest="command")

    # Commande : batch
    p_batch = subparsers.add_parser("batch", help="Traiter un répertoire complet")
    p_batch.add_argument("--input",    required=True, help="Répertoire squelettes source")
    p_batch.add_argument("--output",   required=True, help="Répertoire squelettes remappés")
    p_batch.add_argument("--width",    type=int, default=1344)
    p_batch.add_argument("--height",   type=int, default=768)
    p_batch.add_argument("--overwrite", action="store_true")

    # Commande : single
    p_single = subparsers.add_parser("single", help="Traiter un seul squelette")
    p_single.add_argument("--input",  required=True)
    p_single.add_argument("--output", required=True)
    p_single.add_argument("--width",  type=int, default=1344)
    p_single.add_argument("--height", type=int, default=768)

    # Commande : preview
    p_prev = subparsers.add_parser("preview", help="Générer un aperçu avec grille")
    p_prev.add_argument("--input",  required=True)
    p_prev.add_argument("--output", required=True)

    args = parser.parse_args()

    if args.command == "batch":
        batch_resize_skeletons(
            args.input, args.output, args.width, args.height,
            overwrite=args.overwrite
        )

    elif args.command == "single":
        resize_skeleton_to_target(args.input, args.width, args.height, args.output)
        print(f"[skeleton_remapper] Remappé : {args.output}")

    elif args.command == "preview":
        preview_remap(args.input, args.output)

    else:
        parser.print_help()

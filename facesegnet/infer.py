# infer.py — FaceSegNet (Ov3rLoRd Pipeline)
# Inférence du SAM ViT-B fine-tuné traits du visage.
# Même architecture que handsegnet\infer.py. Le modèle est agnostique à la
# classe : la boîte fournie (ex. zone œil/bouche depuis les landmarks) cible
# le trait voulu ; `part` ne sert qu'au nommage du fichier de sortie.
#
# Convention de sortie PAR DÉFAUT = pipeline ComfyUI :
#   NOIR (0) = zone à régénérer, BLANC (255) = zone à préserver.
#
# Usage :
#   py -3.12 infer.py --image FRAME.png --box "300,250,200,80" --part eyes --output mask.png
#   from infer import generate_part_mask
#   from infer import generate_sam_mask   # alias compatible inpaint_corrector

import argparse
import time
from pathlib import Path

import numpy as np
from PIL import Image, ImageFilter

# ── CONFIG ────────────────────────────────────────────────────────────────────
PROJECT      = "facesegnet"
PROJECT_ROOT = Path(r"D:\OVERLORD\facesegnet")
CKPT_BEST    = PROJECT_ROOT / "checkpoints" / f"{PROJECT}_vit_b_best.pth"
SAM_FALLBACK = Path(r"D:\Ov3rLoRd AI\ComfyUI\models\sams\sam_vit_b_01ec64.pth")
FEATHER_PX   = 4      # traits fins — feathering réduit vs corps entier

_predictor = None


def _load_predictor():
    global _predictor
    if _predictor is not None:
        return _predictor

    import torch
    from segment_anything import sam_model_registry, SamPredictor

    device = "cuda" if torch.cuda.is_available() else "cpu"
    if CKPT_BEST.exists():
        print(f"[{PROJECT}] Chargement checkpoint fine-tuné : {CKPT_BEST.name}")
        sam = sam_model_registry["vit_b"](checkpoint=None)
        state = torch.load(str(CKPT_BEST), map_location=device, weights_only=True)
        sam.load_state_dict(state)
    elif SAM_FALLBACK.exists():
        print(f"[{PROJECT}] WARN : checkpoint fine-tuné absent — repli sur SAM de base. "
              f"Lancer train.py.")
        sam = sam_model_registry["vit_b"](checkpoint=str(SAM_FALLBACK))
    else:
        raise FileNotFoundError(f"Aucun checkpoint : ni {CKPT_BEST} ni {SAM_FALLBACK}")
    sam.to(device)
    sam.eval()
    _predictor = SamPredictor(sam)
    return _predictor


def _prepare_rgb(frame_path: Path) -> Image.Image:
    """RGB avec alpha composé sur blanc (le RGBA brut casse SAM)."""
    img_raw = Image.open(str(frame_path))
    if img_raw.mode in ("RGBA", "LA") or (
        img_raw.mode == "P" and "transparency" in img_raw.info
    ):
        bg = Image.new("RGB", img_raw.size, (255, 255, 255))
        if img_raw.mode != "RGBA":
            img_raw = img_raw.convert("RGBA")
        bg.paste(img_raw, mask=img_raw.split()[3])
        return bg
    return img_raw.convert("RGB")


def generate_part_mask(
    frame_path: str,
    zone: tuple | None = None,
    output_path: str = None,
    threshold: float = 0.5,
    verbose: bool = False,
    part: str | None = None,
    pipeline_convention: bool = True,
    feather_px: int = FEATHER_PX,
    return_score: bool = False,
) -> str | tuple[str, float] | None:
    """
    Segmente un trait du visage ciblé par la boîte `zone`.

    Args:
        frame_path  : chemin de la frame à analyser
        zone        : (x, y, w, h) boîte englobante en pixels ; None = image entière
        output_path : chemin du masque (défaut: <frame>_<part>mask.png)
        threshold   : seuil sur la probabilité sigmoïde
        verbose     : affiche les étapes
        part        : étiquette libre ("eyes", "mouth", "nose", "eyebrows", "hairline")
        pipeline_convention : True → NOIR=régénérer/BLANC=préserver ; False → BLANC=objet
        feather_px  : flou gaussien de bord (0 = net)
        return_score : True → retourne (chemin, score SAM natif scores[0])
                      au lieu du chemin seul, pour trier/prioriser en aval

    Returns:
        Chemin du masque PNG (ou (chemin, score) si return_score), ou None si échec.
    """
    frame_path = Path(frame_path)
    if not frame_path.exists():
        print(f"[{PROJECT}] Frame non trouvée : {frame_path}")
        return None

    try:
        predictor = _load_predictor()
    except Exception as e:
        print(f"[{PROJECT}] Erreur chargement modèle : {e}")
        return None

    t0 = time.time()
    arr = np.array(_prepare_rgb(frame_path))
    ih, iw = arr.shape[:2]

    if zone is not None:
        x, y, w, h = zone
        box = np.array([max(0, x), max(0, y), min(iw, x + w), min(ih, y + h)],
                       dtype=np.float32)
    else:
        box = np.array([0, 0, iw, ih], dtype=np.float32)

    if verbose:
        print(f"[{PROJECT}] Segmentation {frame_path.name} part={part} box={box.tolist()}")

    try:
        import torch
        predictor.set_image(arr)
        with torch.no_grad():
            masks, scores, logits = predictor.predict(
                box=box, multimask_output=False, return_logits=True
            )
        # `masks[0]` (pas `logits[0]`) : predictor.predict(return_logits=True)
        # renvoie dans `masks` les logits déjà remis à l'échelle de l'image
        # d'origine (postprocess_masks) ; `logits` est la sortie brute basse
        # résolution (256x256) du mask_decoder, non upscalée.
        prob = 1.0 / (1.0 + np.exp(-masks[0].astype(np.float64)))
        obj = (prob >= threshold).astype(np.uint8)
    except Exception as e:
        print(f"[{PROJECT}] Erreur inférence : {e}")
        return None

    if pipeline_convention:
        out_arr = np.where(obj > 0, 0, 255).astype(np.uint8)
    else:
        out_arr = (obj * 255).astype(np.uint8)

    if out_arr.shape != (ih, iw):
        print(f"[{PROJECT}] Erreur : masque {out_arr.shape[::-1]} != "
              f"image source {(iw, ih)} — inférence annulée")
        return None

    mask_img = Image.fromarray(out_arr, mode="L")
    if feather_px > 0:
        mask_img = mask_img.filter(ImageFilter.GaussianBlur(feather_px))

    suffix = f"_{part}mask" if part else "_partmask"
    final_path = output_path or str(frame_path.parent / f"{frame_path.stem}{suffix}.png")
    mask_img.save(final_path)

    if verbose:
        pct = float(obj.sum()) / obj.size * 100
        print(f"[{PROJECT}] Masque : {pct:.1f}% objet — score={float(scores[0]):.3f} "
              f"— {time.time() - t0:.2f}s -> {final_path}")

    if return_score:
        return final_path, float(scores[0])
    return final_path


# Alias compatible avec agents\inpaint_corrector.py
generate_sam_mask = generate_part_mask


# ── CLI ───────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=f"{PROJECT} — inférence masque")
    parser.add_argument("--image",     required=True)
    parser.add_argument("--box",       default=None, help="'x,y,w,h' en pixels")
    parser.add_argument("--part",      default=None,
                        help="eyes / mouth / nose / eyebrows / hairline (nommage)")
    parser.add_argument("--output",    default=None)
    parser.add_argument("--threshold", type=float, default=0.5)
    parser.add_argument("--raw",       action="store_true",
                        help="Convention ML (BLANC=objet) au lieu de la convention pipeline")
    parser.add_argument("--feather",   type=int, default=FEATHER_PX)
    args = parser.parse_args()

    box = None
    if args.box:
        try:
            box = tuple(int(v) for v in args.box.split(","))
            assert len(box) == 4
        except Exception:
            print("Erreur : --box doit être au format 'x,y,w,h'")
            raise SystemExit(1)

    result = generate_part_mask(
        frame_path=args.image, zone=box, output_path=args.output,
        threshold=args.threshold, verbose=True, part=args.part,
        pipeline_convention=not args.raw, feather_px=args.feather,
    )
    print(f"\nMasque {PROJECT} : {result if result else 'ÉCHEC'}")

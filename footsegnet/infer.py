# infer.py — FootSegNet (Ov3rLoRd Pipeline)
# Inférence du SAM ViT-B fine-tuné pieds/chaussures, pour intégration directe
# dans le pipeline inpaint existant (agents\inpaint_corrector.py).
#
# generate_foot_mask() reprend la signature de
# agents\sam_mask_generator.generate_sam_mask() : c'est un drop-in replacement.
#
#   from infer import generate_foot_mask as generate_sam_mask
#   mask_path = generate_sam_mask(frame_path, zone, output_path)
#
# Convention de sortie PAR DÉFAUT = pipeline ComfyUI (test MaskEditor confirmé) :
#   NOIR (0)    = pied/chaussure → zone à régénérer (inpaint)
#   BLANC (255) = fond           → zone à préserver
# Passer pipeline_convention=False pour le masque ML brut (BLANC=objet).
#
# Contrairement à sam_mask_generator.py (qui passe par l'API ComfyUI +
# SAMPreprocessor générique + heuristiques HSV), l'inférence est locale
# (torch), directe, et le modèle est spécialisé — pas de post-traitement
# par classes de gris ni de filtrage jean nécessaire.
#
# Usage CLI :
#   py -3.12 infer.py --image FRAME.png --box "259,1049,200,409" --output mask.png
#   py -3.12 infer.py --image FRAME.png --output mask.png          (image entière)

import argparse
import time
from pathlib import Path

import numpy as np
from PIL import Image, ImageFilter

# ── CONFIG ────────────────────────────────────────────────────────────────────
FOOTSEGNET_ROOT = Path(r"D:\OVERLORD\footsegnet")
CKPT_BEST       = FOOTSEGNET_ROOT / "checkpoints" / "footsegnet_vit_b_best.pth"
SAM_FALLBACK    = Path(r"D:\Ov3rLoRd AI\ComfyUI\models\sams\sam_vit_b_01ec64.pth")
FEATHER_PX      = 8      # même feathering que sam_mask_generator.py

_predictor = None


def _load_predictor():
    """Charge le modèle une seule fois (singleton). Fine-tuné si dispo, sinon SAM de base."""
    global _predictor
    if _predictor is not None:
        return _predictor

    import torch
    from segment_anything import sam_model_registry, SamPredictor

    device = "cuda" if torch.cuda.is_available() else "cpu"
    if CKPT_BEST.exists():
        print(f"[footsegnet] Chargement checkpoint fine-tuné : {CKPT_BEST.name}")
        sam = sam_model_registry["vit_b"](checkpoint=None)
        state = torch.load(str(CKPT_BEST), map_location=device, weights_only=True)
        sam.load_state_dict(state)
    elif SAM_FALLBACK.exists():
        print(f"[footsegnet] WARN : checkpoint fine-tuné absent — repli sur SAM de base "
              f"({SAM_FALLBACK.name}). Lancer train_sam.py.")
        sam = sam_model_registry["vit_b"](checkpoint=str(SAM_FALLBACK))
    else:
        raise FileNotFoundError(
            f"Aucun checkpoint : ni {CKPT_BEST} ni {SAM_FALLBACK}"
        )
    sam.to(device)
    sam.eval()
    _predictor = SamPredictor(sam)
    return _predictor


def _prepare_rgb(frame_path: Path) -> Image.Image:
    """Ouvre l'image en RGB, en composant l'alpha éventuel sur fond blanc
    (même précaution que sam_mask_generator.py — le RGBA brut casse SAM)."""
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


def generate_foot_mask(
    frame_path: str,
    zone: tuple | None = None,
    output_path: str = None,
    threshold: float = 0.5,
    verbose: bool = False,
    pipeline_convention: bool = True,
    feather_px: int = FEATHER_PX,
    refine: bool = True,
) -> str | None:
    """
    Segmente les pieds/chaussures d'une frame avec le SAM fine-tuné.

    Drop-in replacement de sam_mask_generator.generate_sam_mask().

    Args:
        frame_path  : chemin de la frame à analyser
        zone        : (x, y, w, h) boîte englobante en pixels absolus
                      (depuis les keypoints OpenPose) ; None = image entière
        output_path : chemin de sauvegarde du masque (défaut: <frame>_footmask.png)
        threshold   : seuil sur la probabilité sigmoïde (défaut 0.5)
        verbose     : affiche les étapes
        pipeline_convention : True (défaut) → NOIR=régénérer, BLANC=préserver ;
                              False → BLANC=objet (convention ML/dataset)
        feather_px  : rayon du flou gaussien de bord (0 = masque net)
        refine      : True (défaut) → second appel predictor.predict() en
                      réinjectant les logits du 1er passage comme mask_input
                      (même box), pour laisser SAM corriger/étendre sa propre
                      sortie (usage natif de l'entrée mask_input du
                      mask_decoder, pas un hack) ; False → un seul passage
                      (comportement historique)

    Returns:
        Chemin du masque PNG généré, ou None si échec.
    """
    frame_path = Path(frame_path)
    if not frame_path.exists():
        print(f"[footsegnet] Frame non trouvée : {frame_path}")
        return None

    try:
        predictor = _load_predictor()
    except Exception as e:
        print(f"[footsegnet] Erreur chargement modèle : {e}")
        return None

    t0 = time.time()
    img = _prepare_rgb(frame_path)
    arr = np.array(img)
    ih, iw = arr.shape[:2]

    if zone is not None:
        x, y, w, h = zone
        box = np.array([
            max(0, x), max(0, y),
            min(iw, x + w), min(ih, y + h),
        ], dtype=np.float32)
    else:
        box = np.array([0, 0, iw, ih], dtype=np.float32)

    if verbose:
        print(f"[footsegnet] Segmentation {frame_path.name} box={box.tolist()}")

    try:
        import torch
        predictor.set_image(arr)
        with torch.no_grad():
            masks, scores, logits = predictor.predict(
                box=box, multimask_output=False, return_logits=True
            )
            if refine:
                # Raffinement : on réinjecte les logits du 1er passage comme
                # mask_input du 2e, avec la même box — SAM utilise alors sa
                # propre sortie comme point de départ pour corriger/étendre
                # le masque, au lieu de repartir de zéro.
                masks, scores, logits = predictor.predict(
                    box=box, mask_input=logits, multimask_output=False,
                    return_logits=True,
                )
        # Seuil sur la probabilité (logits → sigmoïde) plutôt que le seuil
        # binaire par défaut du predictor, pour exposer `threshold`.
        # `masks[0]` (pas `logits[0]`) : predictor.predict(return_logits=True)
        # renvoie dans `masks` les logits déjà remis à l'échelle de l'image
        # d'origine (postprocess_masks) ; `logits` est la sortie brute basse
        # résolution (256x256) du mask_decoder, non upscalée -- la seuiller
        # directement produirait un masque 256x256 au lieu de la résolution
        # de l'image source.
        prob = 1.0 / (1.0 + np.exp(-masks[0].astype(np.float64)))
        obj = (prob >= threshold).astype(np.uint8)
    except Exception as e:
        print(f"[footsegnet] Erreur inférence : {e}")
        return None

    if pipeline_convention:
        # NOIR = objet (à régénérer), BLANC = fond (à préserver)
        out_arr = np.where(obj > 0, 0, 255).astype(np.uint8)
    else:
        out_arr = (obj * 255).astype(np.uint8)

    if out_arr.shape != (ih, iw):
        print(f"[footsegnet] Erreur : masque {out_arr.shape[::-1]} != "
              f"image source {(iw, ih)} — inférence annulée")
        return None

    mask_img = Image.fromarray(out_arr, mode="L")
    if feather_px > 0:
        mask_img = mask_img.filter(ImageFilter.GaussianBlur(feather_px))

    final_path = output_path or str(frame_path.parent / f"{frame_path.stem}_footmask.png")
    mask_img.save(final_path)

    if verbose:
        pct = float(obj.sum()) / obj.size * 100
        refine_txt = "refine=on" if refine else "refine=off"
        print(f"[footsegnet] Masque : {pct:.1f}% pied/chaussure — "
              f"score SAM={float(scores[0]):.3f} — {refine_txt} — "
              f"{time.time() - t0:.2f}s")
        print(f"[footsegnet] → {final_path}")

    return final_path


# Alias : permet `from infer import generate_sam_mask` sans renommage côté appelant
generate_sam_mask = generate_foot_mask


# ── CLI ───────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="FootSegNet — inférence masque pieds/chaussures")
    parser.add_argument("--image",     required=True, help="Frame source à segmenter")
    parser.add_argument("--box",       default=None,
                        help="Boîte englobante 'x,y,w,h' en pixels (optionnel — défaut image entière)")
    parser.add_argument("--output",    default=None,  help="Chemin de sortie du masque")
    parser.add_argument("--threshold", type=float, default=0.5)
    parser.add_argument("--raw",       action="store_true",
                        help="Convention ML (BLANC=objet) au lieu de la convention pipeline")
    parser.add_argument("--feather",   type=int, default=FEATHER_PX,
                        help=f"Flou gaussien de bord en px (défaut: {FEATHER_PX}, 0=net)")
    parser.add_argument("--refine", action=argparse.BooleanOptionalAction, default=True,
                        help="Raffinement itératif : réinjecte les logits du 1er passage "
                             "comme mask_input du 2e (défaut: activé ; --no-refine pour désactiver)")
    args = parser.parse_args()

    box = None
    if args.box:
        try:
            box = tuple(int(v) for v in args.box.split(","))
            assert len(box) == 4
        except Exception:
            print("Erreur : --box doit être au format 'x,y,w,h' ex: '259,1049,200,409'")
            raise SystemExit(1)

    result = generate_foot_mask(
        frame_path=args.image,
        zone=box,
        output_path=args.output,
        threshold=args.threshold,
        verbose=True,
        pipeline_convention=not args.raw,
        feather_px=args.feather,
        refine=args.refine,
    )
    print(f"\nMasque FootSegNet : {result if result else 'ÉCHEC'}")

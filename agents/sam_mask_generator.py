# sam_mask_generator.py — Ov3rLoRd Pipeline
# Génère un masque pixel-perfect via SAM (Segment Anything Model)
# en passant par l'API ComfyUI. SAM est déjà installé via Impact Pack.
#
# Remplace le calcul de masque rectangulaire fixe dans inpaint_corrector.py
# pour tous les éléments qui nécessitent de l'inpaint (chaussures, veste,
# cheveux, accessoires, etc.) — la boîte englobante reste calculée depuis
# les keypoints OpenPose, mais SAM produit un masque qui suit précisément
# le contour de l'élément sans déborder sur les zones adjacentes.
#
# Architecture :
#   Keypoints OpenPose → boîte englobante → SAM → masque pixel-perfect
#
# Usage standalone :
#   py -3.12 sam_mask_generator.py \
#       --image FRAME.png \
#       --box "259,1049,200,409" \
#       --output mask_sam.png \
#       --verbose
#
# Usage depuis inpaint_corrector.py :
#   from sam_mask_generator import generate_sam_mask
#   mask_path = generate_sam_mask(frame_path, zone, output_path)

import json
import time
import sys
import argparse
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))
import config

try:
    import requests as _req
    HAS_REQUESTS = True
except ImportError:
    HAS_REQUESTS = False

try:
    from PIL import Image
    HAS_PIL = True
except ImportError:
    HAS_PIL = False

# ── CONFIG ────────────────────────────────────────────────────────────────────
COMFYUI_URL   = "http://127.0.0.1:8188"
COMFYUI_INPUT = str(config.COMFYUI_INPUT)
COMFYUI_OUTPUT = str(config.COMFYUI_OUTPUT)
SAM_MODEL     = "sam_vit_b_01ec64.pth"
DINO_MODEL    = "GroundingDINO_SwinB (938MB)"   # DINO pour détection auto par prompt texte
POLL_INTERVAL = 1.0   # secondes entre chaque vérification du job
POLL_TIMEOUT  = 120   # secondes max d'attente


def build_sam_workflow(
    image_name: str,
    box: tuple,
    mask_output_prefix: str = "sam_mask_",
    threshold: float = 0.5,
) -> dict:
    """
    Construit le workflow ComfyUI API pour SAM.

    Nœuds confirmés disponibles dans cette installation :
    - SAMLoader (pas SAMModelLoader)
    - SAMPreprocessor (image → image segmentée directement, sans SEGS intermédiaires)
    - MaskToImage / ImageToMask pour conversions

    SAMPreprocessor prend une image et produit une sortie IMAGE segmentée.
    On la convertit en masque binaire via ImageToMask.

    Note : SAMPreprocessor travaille sur l'image entière. Pour guider SAM
    vers la zone des pieds, on lui envoie un crop de l'image centré sur la
    boîte englobante (zone calculée depuis les keypoints OpenPose).
    """
    # Le crop est déjà préparé côté Python avant l'appel à ce workflow —
    # image_name pointe vers le crop, pas l'image entière.
    return {
        "1": {
            "class_type": "LoadImage",
            "inputs": {
                "image":  image_name,
                "upload": "image"
            }
        },
        "2": {
            "class_type": "SAMPreprocessor",
            "inputs": {
                "image": ["1", 0]
            }
        },
        "3": {
            "class_type": "ImageToMask",
            "inputs": {
                "image":   ["2", 0],
                "channel": "red"
            }
        },
        "4": {
            "class_type": "MaskToImage",
            "inputs": {
                "mask": ["3", 0]
            }
        },
        "5": {
            "class_type": "SaveImage",
            "inputs": {
                "images":          ["4", 0],
                "filename_prefix": mask_output_prefix
            }
        }
    }


def _upload_image(image_path: str) -> str | None:
    """Upload une image dans ComfyUI/input/ via l'API /upload/image."""
    if not HAS_REQUESTS:
        return None
    try:
        with open(image_path, "rb") as f:
            r = _req.post(
                f"{COMFYUI_URL}/upload/image",
                files={"image": (Path(image_path).name, f, "image/png")},
                data={"overwrite": "true"},
                timeout=30
            )
        r.raise_for_status()
        return r.json().get("name")
    except Exception as e:
        print(f"[sam_mask] Erreur upload : {e}")
        return None


def _submit_workflow(workflow: dict) -> str | None:
    """Soumet le workflow à ComfyUI et retourne le prompt_id."""
    if not HAS_REQUESTS:
        return None
    try:
        r = _req.post(
            f"{COMFYUI_URL}/prompt",
            json={"prompt": workflow},
            timeout=30
        )
        r.raise_for_status()
        return r.json().get("prompt_id")
    except Exception as e:
        print(f"[sam_mask] Erreur submit : {e}")
        return None


def _wait_for_completion(prompt_id: str, timeout: float = POLL_TIMEOUT) -> bool:
    """Attend la fin d'exécution du job ComfyUI."""
    if not HAS_REQUESTS:
        return False
    start = time.time()
    while time.time() - start < timeout:
        try:
            r = _req.get(f"{COMFYUI_URL}/history/{prompt_id}", timeout=10)
            r.raise_for_status()
            history = r.json()
            if prompt_id in history:
                return True
        except Exception:
            pass
        time.sleep(POLL_INTERVAL)
    print(f"[sam_mask] Timeout après {timeout}s")
    return False


def _find_output_image(prompt_id: str, prefix: str, created_after: float = 0) -> str | None:
    """
    Retrouve l'image de sortie produite par ComfyUI.
    Cherche d'abord via l'API historique, puis directement sur disque par glob.
    created_after : timestamp unix — ignore les fichiers plus anciens.
    """
    # Tentative 1 : API historique
    if HAS_REQUESTS:
        try:
            r = _req.get(f"{COMFYUI_URL}/history/{prompt_id}", timeout=10)
            r.raise_for_status()
            history = r.json()
            outputs = history.get(prompt_id, {}).get("outputs", {})
            for node_id, node_output in outputs.items():
                images = node_output.get("images", [])
                for img in images:
                    fname = img.get("filename", "")
                    if fname.startswith(prefix):
                        subfolder = img.get("subfolder", "")
                        for base in [Path(COMFYUI_OUTPUT) / subfolder, Path(COMFYUI_OUTPUT)]:
                            candidate = base / fname
                            if candidate.exists():
                                return str(candidate)
        except Exception:
            pass

    # Tentative 2 : glob par date de modification (uniquement fichiers récents)
    try:
        import glob as _glob
        pattern = str(Path(COMFYUI_OUTPUT) / "**" / f"{prefix}*.png")
        candidates = [
            p for p in _glob.glob(pattern, recursive=True)
            if Path(p).stat().st_mtime > created_after
        ]
        if candidates:
            candidates.sort(key=lambda p: Path(p).stat().st_mtime, reverse=True)
            return candidates[0]
    except Exception as e:
        print(f"[sam_mask] Erreur recherche disque : {e}")

    return None

    return None


def generate_sam_mask(
    frame_path: str,
    zone: tuple,
    output_path: str = None,
    threshold: float = 0.5,
    verbose: bool = False,
) -> str | None:
    """
    Pipeline complet : upload frame → SAM via ComfyUI API → masque pixel-perfect.

    La zone (x, y, w, h) calculée depuis les keypoints OpenPose est utilisée
    comme boîte englobante pour guider SAM. SAM affine ensuite le masque au
    niveau pixel pour suivre précisément le contour de l'élément (chaussure,
    veste, etc.) sans déborder sur les zones adjacentes.

    Convention de sortie : NOIR = zone à régénérer (inpaint), BLANC = préserver.
    Conforme à la convention ComfyUI confirmée par test MaskEditor.

    Args:
        frame_path  : chemin vers la frame générée à analyser
        zone        : (x, y, w, h) boîte englobante en pixels absolus
        output_path : chemin de sauvegarde du masque (optionnel)
        threshold   : seuil de confiance SAM (0.3–0.7, défaut 0.5)
        verbose     : affiche les étapes

    Returns:
        Chemin du masque généré, ou None si échec.
    """
    if not HAS_PIL or not HAS_REQUESTS:
        print("[sam_mask] PIL et requests requis")
        return None

    frame_path = Path(frame_path)
    if not frame_path.exists():
        print(f"[sam_mask] Frame non trouvée : {frame_path}")
        return None

    # 1. Crop l'image sur la zone englobante + contexte avant upload
    # On utilise l'image originale (avec fond blanc) — SAMPreprocessor fonctionne
    # mieux avec un fond blanc qu'avec un fond noir (qui produit un workflow vide).
    # Le contexte de 5% donne la meilleure séparation des classes observée en test.
    if verbose:
        print(f"[sam_mask] Crop de la zone {zone} depuis {frame_path.name}...")

    try:
        from PIL import Image as _PILImage
        img_raw = _PILImage.open(str(frame_path))

        # Si l'image a un canal alpha (fond transparent), composer sur blanc
        # avant d'envoyer à SAMPreprocessor qui n'accepte que du RGB.
        # Sans ça, convert("RGB") rend les pixels transparents noirs,
        # ce qui perturbe la segmentation SAM.
        if img_raw.mode in ("RGBA", "LA") or (img_raw.mode == "P" and "transparency" in img_raw.info):
            bg = _PILImage.new("RGB", img_raw.size, (255, 255, 255))
            if img_raw.mode != "RGBA":
                img_raw = img_raw.convert("RGBA")
            bg.paste(img_raw, mask=img_raw.split()[3])
            img = bg
        else:
            img = img_raw.convert("RGB")

        iw, ih = img.size
        x, y, w, h = zone
        ctx = int(min(iw, ih) * 0.05)
        x1 = max(0, x - ctx)
        y1 = max(0, y - ctx)
        x2 = min(iw, x + w + ctx)
        y2 = min(ih, y + h + ctx)
        crop = img.crop((x1, y1, x2, y2))
        crop_path = frame_path.parent / f"_sam_crop_{frame_path.stem}_{int(time.time())}.png"
        crop.save(str(crop_path))
        crop_box = (x1, y1, x2, y2)
    except Exception as e:
        print(f"[sam_mask] Erreur crop : {e}")
        return None

    # 2. Upload le crop dans ComfyUI
    if verbose:
        print(f"[sam_mask] Upload crop {crop_path.name}...")
    uploaded_name = _upload_image(str(crop_path))
    if not uploaded_name:
        print("[sam_mask] Échec upload")
        return None

    # 2. Construire et soumettre le workflow SAM
    # Préfixe unique par run pour invalider le cache ComfyUI
    import random
    run_id = random.randint(10000, 99999)
    prefix = f"sam_mask_{frame_path.stem}_{run_id}_"
    workflow = build_sam_workflow(
        image_name=uploaded_name,
        box=zone,
        mask_output_prefix=prefix,
        threshold=threshold,
    )

    if verbose:
        print(f"[sam_mask] Soumission workflow SAM (zone={zone})...")
    pid = _submit_workflow(workflow)
    if not pid:
        print("[sam_mask] Échec soumission workflow")
        return None

    if verbose:
        print(f"[sam_mask] Job soumis — pid={pid}, attente...")

    # Timestamp de soumission — pour filtrer les anciens fichiers
    submit_time = time.time()

    # Attendre un minimum avant de commencer à poller
    time.sleep(3.0)

    # 3. Attendre la fin
    if not _wait_for_completion(pid):
        print("[sam_mask] Job non terminé dans les délais")
        return None

    # 4. Récupérer le masque produit (uniquement fichiers créés après soumission)
    mask_file = _find_output_image(pid, prefix, created_after=submit_time)
    if not mask_file or not Path(mask_file).exists():
        print(f"[sam_mask] Masque non trouvé — aucun fichier '{prefix}*.png' créé après soumission")
        print(f"[sam_mask]   Vérifiez les logs ComfyUI pour d'éventuelles erreurs SAMPreprocessor")
        return None

    if verbose:
        print(f"[sam_mask] Masque SAM brut généré : {mask_file}")

    # 5. Post-traitement : convertir la segmentation multi-classes en masque
    # binaire propre (noir=zone à régénérer, blanc=préserver).
    # SAMPreprocessor produit plusieurs niveaux de gris (une valeur par classe
    # détectée). On isole les classes intermédiaires (ni fond, ni jean) qui
    # correspondent aux chaussures, en seuillant entre les deux extrêmes.
    try:
        import numpy as np
        from PIL import Image as _PILImage, ImageFilter as _IFilter

        raw = _PILImage.open(mask_file).convert("L")
        arr = np.array(raw)
        unique_vals = np.unique(arr)

        if len(unique_vals) >= 3:
            if verbose:
                for v in unique_vals:
                    pct_v = (arr == v).sum() / arr.size * 100
                    print(f"[sam_mask]   classe {v:3d} : {pct_v:.1f}%")

            dominant = unique_vals[np.argmax([np.sum(arr == v) for v in unique_vals])]

            if dominant < 50:
                # Fond noir : objets en valeurs > 30, on cible tout le non-fond
                non_bg = unique_vals[unique_vals > 30]
                if len(non_bg) >= 2:
                    binary = np.where(arr > 30, 0, 255).astype(np.uint8)
                else:
                    binary = np.where(arr < 128, 0, 255).astype(np.uint8)
            else:
                # Fond blanc (valeur dominante haute) :
                # On exclut le fond (valeur dominante) ET la classe la plus basse non-nulle
                # (qui correspond au jean, mélange sombre) et on ne garde que les
                # classes intermédiaires hautes (les chaussures avec texture claire).
                # Observé sur test : fond=196, jean=84, chaussure_arriere=119, chaussure_avant=220
                non_dom = unique_vals[unique_vals != dominant]  # exclure fond
                if len(non_dom) >= 3:
                    # Exclure les classes avec moins de 1% de pixels (résidus)
                    # et la classe la plus basse significative (jean sombre)
                    significant = non_dom[[
                        (arr == v).sum() / arr.size > 0.01
                        for v in non_dom
                    ]]
                    if len(significant) >= 2:
                        # Exclure la plus basse (jean) et garder le reste (chaussures)
                        shoe_classes = significant[1:]
                    else:
                        shoe_classes = significant
                    binary = np.where(np.isin(arr, shoe_classes), 0, 255).astype(np.uint8)
                elif len(non_dom) >= 2:
                    # Prendre les 2 classes les plus hautes hors fond
                    shoe_classes = non_dom[-2:]
                    binary = np.where(np.isin(arr, shoe_classes), 0, 255).astype(np.uint8)
                else:
                    lo = float(unique_vals[0]) + (float(unique_vals[-1]) - float(unique_vals[0])) * 0.15
                    hi = float(unique_vals[-1]) * 0.85
                    binary = np.where((arr > lo) & (arr < hi), 0, 255).astype(np.uint8)
        else:
            binary = np.where(arr < 128, 0, 255).astype(np.uint8)

        binary_img = _PILImage.fromarray(binary, mode="L")

        # Filtrage HSV : forcer en blanc (préservé) les pixels bleus du jean
        # même si SAM les a classés dans une zone intermédiaire.
        # Le jean anime a une teinte cyan/bleue distincte (hue 150-270°, sat > 0.25)
        # qui ne se confond pas avec les chaussures Jordan (rouge/blanc/noir).
        try:
            crop_img_rgb = _PILImage.open(str(crop_path)).convert("RGB")
            # Redimensionner le crop à la taille du masque SAM si différente
            mask_size = (arr.shape[1], arr.shape[0])  # (width, height)
            if crop_img_rgb.size != mask_size:
                crop_img_rgb = crop_img_rgb.resize(mask_size, _PILImage.LANCZOS)
            crop_arr = np.array(crop_img_rgb).astype(float) / 255.0
            r_, g_, b_ = crop_arr[:,:,0], crop_arr[:,:,1], crop_arr[:,:,2]
            maxc_ = np.maximum(np.maximum(r_, g_), b_)
            minc_ = np.minimum(np.minimum(r_, g_), b_)
            delta_ = maxc_ - minc_
            hue_ = np.zeros_like(r_)
            mr = (maxc_ == r_) & (delta_ > 0)
            mg = (maxc_ == g_) & (delta_ > 0)
            mb_ = (maxc_ == b_) & (delta_ > 0)
            hue_[mr] = 60 * ((g_[mr] - b_[mr]) / delta_[mr] % 6)
            hue_[mg] = 60 * ((b_[mg] - r_[mg]) / delta_[mg] + 2)
            hue_[mb_] = 60 * ((r_[mb_] - g_[mb_]) / delta_[mb_] + 4)
            sat_ = np.where(maxc_ > 0, delta_ / maxc_, 0)
            jean_pixels = (hue_ >= 150) & (hue_ <= 270) & (sat_ > 0.25)
            # Forcer ces pixels en blanc (préservé) dans le masque binaire
            binary_with_hsv = binary.copy()
            binary_with_hsv[jean_pixels] = 255
            binary_img = _PILImage.fromarray(binary_with_hsv, mode="L")
            jean_pct = jean_pixels.sum() / jean_pixels.size * 100
            if verbose:
                print(f"[sam_mask] Filtrage HSV : {jean_pct:.1f}% pixels jean forcés en préservé")
        except Exception as e_hsv:
            if verbose:
                print(f"[sam_mask] Filtrage HSV ignoré : {e_hsv}")

        binary_img = binary_img.filter(_IFilter.GaussianBlur(8))

        # Sauvegarder le masque post-traité
        final_path = output_path or mask_file.replace(".png", "_binary.png")
        binary_img.save(final_path)

        if verbose:
            pct = (binary == 0).sum() / binary.size * 100
            print(f"[sam_mask] Masque binaire : {pct:.1f}% noir (à régénérer)")

        return final_path

    except Exception as e:
        print(f"[sam_mask] Erreur post-traitement : {e} — retour masque brut")
        if output_path:
            import shutil
            shutil.copy2(mask_file, output_path)
            return output_path
        return mask_file


# ── CLI ───────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Ov3rLoRd — SAM Mask Generator")
    parser.add_argument("--image",     required=True, help="Frame source à segmenter")
    parser.add_argument("--box",       required=True,
                        help="Boîte englobante 'x,y,w,h' en pixels")
    parser.add_argument("--output",    default=None,  help="Chemin de sortie du masque")
    parser.add_argument("--threshold", type=float, default=0.5,
                        help="Seuil de confiance SAM (défaut: 0.5)")
    parser.add_argument("--verbose",   action="store_true")
    args = parser.parse_args()

    try:
        box = tuple(int(v) for v in args.box.split(","))
        assert len(box) == 4
    except Exception:
        print("Erreur : --box doit être au format 'x,y,w,h' ex: '259,1049,200,409'")
        raise SystemExit(1)

    result = generate_sam_mask(
        frame_path=args.image,
        zone=box,
        output_path=args.output,
        threshold=args.threshold,
        verbose=True,
    )
    print(f"\nMasque SAM : {result if result else 'ÉCHEC'}")

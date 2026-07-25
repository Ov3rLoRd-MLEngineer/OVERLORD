# inpaint_corrector.py — Ov3rLoRd Pipeline
# Inpaint chirurgical sur zones défectueuses (ex: 3 lignes cuisse)
# Intégration avec qwen_prompt_refiner pour ciblage automatique
# py -3.12

import json
import os
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))
import config

import io
if hasattr(sys.stdout, 'buffer') and getattr(sys.stdout, 'encoding','').lower() != 'utf-8':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

try:
    import numpy as np
    from PIL import Image, ImageDraw, ImageFilter
    HAS_PIL = True
except ImportError:
    HAS_PIL = False
    print("[inpaint_corrector] WARN : PIL non disponible")

try:
    import requests as _req
    HAS_REQUESTS = True
except ImportError:
    HAS_REQUESTS = False


COMFYUI_URL    = "http://127.0.0.1:8188"
COMFYUI_INPUT  = str(config.COMFYUI_INPUT)
COMFYUI_OUTPUT = str(config.COMFYUI_OUTPUT / "asuka_run")

INPAINT_STEPS     = 25
INPAINT_DENOISE   = 0.45    # Sur crop ciblé, 0.45 suffit — 0.60 donnait trop de liberté
INPAINT_CFG       = 6.0
INPAINT_CHECKPOINT = "fabricatedXL_v70.safetensors"
INPAINT_VAE        = "taesdxl"
INPAINT_SAMPLER    = "dpmpp_2m"
INPAINT_SCHEDULER  = "karras"

# FootSegNet — SAM ViT-B fine-tuné pieds/chaussures (D:\OVERLORD\footsegnet).
# Utilisé en priorité pour le masque shoe_mismatch si son checkpoint existe ;
# sinon repli sur le SAM générique via ComfyUI (sam_mask_generator).
FOOTSEGNET_DIR  = config.FOOTSEGNET_ROOT
FOOTSEGNET_CKPT = FOOTSEGNET_DIR / "checkpoints" / "footsegnet_vit_b_best.pth"

# Zones prédéfinies pour les défauts connus d'Asuka
# Format : {issue_keyword: (x_ratio, y_ratio, w_ratio, h_ratio)} sur image 1344x768
# NOTE : "shoe_mismatch" n'est PAS ici — sa zone est calculée dynamiquement
# par shoe_consistency_checker.py (via keypoints OpenPose), pas en ratio fixe,
# car la position des pieds change à chaque frame du cycle de course.
KNOWN_ISSUE_ZONES = {
    "thigh stripe":     (0.30, 0.45, 0.25, 0.20),  # Zone cuisse
    "three stripes":    (0.30, 0.45, 0.25, 0.20),  # Même zone
    "arm stripe":       (0.40, 0.20, 0.20, 0.25),  # Zone bras
    "extra character":  (0.50, 0.0,  0.50, 1.00),  # Moitié droite
    "face":             (0.60, 0.05, 0.35, 0.35),  # Zone visage
    "hands":            (0.45, 0.55, 0.30, 0.30),  # Zone mains/pieds
    "feet":             (0.20, 0.65, 0.40, 0.30),  # Zone pieds (repli fixe si pas de squelette)
}

ISSUE_PROMPTS = {
    "thigh stripe":     "red plugsuit, TWO black stripes on thigh only, no extra stripes",
    "three stripes":    "red plugsuit, exactly TWO black stripes on thigh, remove third stripe",
    "arm stripe":       "red plugsuit, clean arm, no stripes on arm",
    "extra character":  "single character, solo, white background",
    "face":             "asuka langley soryu, perfect face, blue eyes, angry expression",
    "hands":            "perfect hands, correct finger count, anime style",
    "feet":             "correct feet, evangelion boots, red plugsuit shoes",
    "shoe_mismatch":    "score_9, score_8_up, source_anime, nike air jordan 1 high-top sneakers, red black white colorway, swoosh logo, consistent on both feet, pure white background",
}


# ─── Création du masque ───────────────────────────────────────────────────────

def create_inpaint_mask(
    image_w: int,
    image_h: int,
    zone: tuple[float, float, float, float],
    feather_px: int = 20,
) -> "Image.Image":
    """
    Crée un masque d'inpaint pour une zone donnée (ratios 0-1).
    Blanc = zone à régénérer, noir = zone à préserver.
    """
    mask = Image.new("L", (image_w, image_h), 0)
    draw = ImageDraw.Draw(mask)

    x = int(zone[0] * image_w)
    y = int(zone[1] * image_h)
    w = int(zone[2] * image_w)
    h = int(zone[3] * image_h)

    draw.rectangle([x, y, x + w, y + h], fill=255)

    # Feathering (bords doux)
    if feather_px > 0:
        mask = mask.filter(ImageFilter.GaussianBlur(feather_px))

    return mask


# ─── Crop + Stitch ───────────────────────────────────────────────────────────
# Au lieu d'envoyer l'image entière 1024×1536 au modèle avec un masque qui
# ne couvre qu'une petite zone en bas, on :
# 1. Coupe (crop) une région centrée sur la zone à corriger + marge de contexte
# 2. Génère un masque adapté à ce crop
# 3. Envoie ce crop (petit, riche en contexte local) au modèle pour l'inpaint
# 4. Recolle (stitch) le résultat dans l'image originale
#
# Avantages :
# - Le modèle voit la chaussure en grand → meilleure qualité de correction
# - Le contexte local (bas du jean, fond blanc) reste présent → pas de fond gris
# - La zone inpaintée est minuscule dans l'image finale → transition propre

CROP_CONTEXT_RATIO = 0.08   # marge de contexte autour de la zone pieds (ratio de l'image)
CROP_MIN_SIZE      = 256    # taille minimale du crop pour que le modèle ait assez de résolution


def prepare_crop_for_inpaint(
    source_image_path: str,
    zone: tuple,
    context_ratio: float = CROP_CONTEXT_RATIO,
    align: int = 64,
) -> tuple | None:
    """
    Découpe une région autour de la zone pieds avec marge de contexte,
    alignée sur 'align' pixels (requis par le VAE SDXL).

    Returns:
        (crop_img, crop_mask, crop_box) où crop_box = (x, y, x2, y2)
        dans les coordonnées de l'image originale, ou None si erreur.
    """
    if not HAS_PIL:
        return None
    try:
        img = Image.open(source_image_path).convert("RGB")
        iw, ih = img.size
        zx, zy, zw, zh = zone

        ctx_x = int(iw * context_ratio)
        ctx_y = int(ih * context_ratio)

        x1 = max(0, zx - ctx_x)
        y1 = max(0, zy - ctx_y)
        x2 = min(iw, zx + zw + ctx_x)
        y2 = min(ih, zy + zh + ctx_y)

        # Aligner sur 'align' pixels (requis par le VAE SDXL)
        w = x2 - x1
        h = y2 - y1
        w = max(CROP_MIN_SIZE, (w // align) * align)
        h = max(CROP_MIN_SIZE, (h // align) * align)
        # Recentrer après alignement
        cx = x1 + (x2 - x1) // 2
        cy = y1 + (y2 - y1) // 2
        x1 = max(0, cx - w // 2)
        y1 = max(0, cy - h // 2)
        x2 = min(iw, x1 + w)
        y2 = min(ih, y1 + h)
        x1 = max(0, x2 - w)
        y1 = max(0, y2 - h)

        crop_box = (x1, y1, x2, y2)
        crop_img = img.crop(crop_box)

        # Masque dans les coordonnées du crop
        # Convention ComfyUI confirmée par test MaskEditor :
        # NOIR (0)   = zone à régénérer
        # BLANC (255) = zone à préserver
        # On initialise donc le masque en BLANC (tout préservé) et on peint
        # en NOIR uniquement la zone chaussures.
        mask_crop = Image.new("L", (x2 - x1, y2 - y1), 255)
        draw = ImageDraw.Draw(mask_crop)
        mx1 = max(0, zx - x1)
        my1 = max(0, zy - y1)
        mx2 = min(x2 - x1, zx + zw - x1)
        my2 = min(y2 - y1, zy + zh - y1)

        # Décaler le début du masque vers le bas de 55% de la hauteur de zone
        # pour ne couvrir que la semelle + corps de chaussure, pas la tige haute
        # qui touche le jean (si le jean est dans le masque = hallucination garantie)
        shoe_only_offset = int((my2 - my1) * 0.55)
        my1_shoe = my1 + shoe_only_offset

        draw.rectangle([mx1, my1_shoe, mx2, my2], fill=0)
        mask_crop = mask_crop.filter(ImageFilter.GaussianBlur(10))

        return crop_img, mask_crop, crop_box
    except Exception as e:
        print(f"[inpaint_corrector] Erreur crop : {e}")
        return None


def stitch_inpaint_result(
    original_path: str,
    inpainted_crop: "Image.Image",
    crop_box: tuple,
    mask_crop: "Image.Image",
    output_path: str,
) -> bool:
    """
    Recolle le crop inpainté dans l'image originale en utilisant le masque
    pour une transition douce (composite avec feathering).
    """
    if not HAS_PIL:
        return False
    try:
        original = Image.open(original_path).convert("RGB")
        result = original.copy()

        # Redimensionner le crop si ComfyUI l'a modifié
        cw = crop_box[2] - crop_box[0]
        ch = crop_box[3] - crop_box[1]
        if inpainted_crop.size != (cw, ch):
            inpainted_crop = inpainted_crop.resize((cw, ch), Image.LANCZOS)
        if mask_crop.size != (cw, ch):
            mask_crop = mask_crop.resize((cw, ch), Image.LANCZOS)

        result.paste(inpainted_crop, (crop_box[0], crop_box[1]), mask_crop)
        result.save(output_path)
        return True
    except Exception as e:
        print(f"[inpaint_corrector] Erreur stitch : {e}")
        return False


# ─── Build workflow inpaint (crop+stitch) ────────────────────────────────────

def build_inpaint_workflow(
    source_image_name: str,
    mask_image_name: str,
    positive_prompt: str,
    negative_prompt: str,
    seed: int = -1,
    lora_name: str | None = None,
    lora_weight: float = 0.75,
) -> dict:
    """
    Construit le payload ComfyUI pour un inpaint sur un CROP (pas l'image entière).
    Le crop et le masque adaptés ont déjà été préparés par prepare_crop_for_inpaint()
    et sauvegardés dans ComfyUI/input/ avant l'appel de cette fonction.
    """
    import random
    actual_seed = seed if seed != -1 else random.randint(0, 2**32 - 1)

    base = {
        "1": {
            "class_type": "CheckpointLoaderSimple",
            "inputs": {"ckpt_name": INPAINT_CHECKPOINT}
        },
        "2": {
            "class_type": "VAELoader",
            "inputs": {"vae_name": INPAINT_VAE}
        },
        "3": {
            "class_type": "LoadImage",
            "inputs": {"image": source_image_name, "upload": "image"}
        },
        "4": {
            "class_type": "LoadImage",
            "inputs": {"image": mask_image_name, "upload": "image"}
        },
        "4b": {
            "class_type": "ImageToMask",
            "inputs": {"image": ["4", 0], "channel": "red"}
        },
        "5": {
            "class_type": "VAEEncodeForInpaint",
            "inputs": {
                "pixels":       ["3", 0],
                "vae":          ["2", 0],
                "mask":         ["4b", 0],
                "grow_mask_by": 0,
            }
        },
    }

    node_idx = 6

    if lora_name:
        base[str(node_idx)] = {
            "class_type": "LoraLoader",
            "inputs": {
                "model":         ["1", 0],
                "clip":          ["1", 1],
                "lora_name":     lora_name,
                "strength_model": lora_weight,
                "strength_clip":  lora_weight,
            }
        }
        model_ref = [str(node_idx), 0]
        clip_ref  = [str(node_idx), 1]
        node_idx += 1
    else:
        model_ref = ["1", 0]
        clip_ref  = ["1", 1]

    base[str(node_idx)] = {
        "class_type": "CLIPTextEncode",
        "inputs": {"text": positive_prompt, "clip": clip_ref}
    }
    pos_ref = [str(node_idx), 0]
    node_idx += 1

    base[str(node_idx)] = {
        "class_type": "CLIPTextEncode",
        "inputs": {"text": negative_prompt, "clip": clip_ref}
    }
    neg_ref = [str(node_idx), 0]
    node_idx += 1

    base[str(node_idx)] = {
        "class_type": "KSampler",
        "inputs": {
            "model":        model_ref,
            "positive":     pos_ref,
            "negative":     neg_ref,
            "latent_image": ["5", 0],
            "seed":         actual_seed,
            "steps":        INPAINT_STEPS,
            "cfg":          INPAINT_CFG,
            "sampler_name": INPAINT_SAMPLER,
            "scheduler":    INPAINT_SCHEDULER,
            "denoise":      INPAINT_DENOISE,
        }
    }
    ksampler_ref = [str(node_idx), 0]
    node_idx += 1

    base[str(node_idx)] = {
        "class_type": "VAEDecode",
        "inputs": {"samples": ksampler_ref, "vae": ["2", 0]}
    }
    vae_decode_ref = [str(node_idx), 0]
    node_idx += 1

    base[str(node_idx)] = {
        "class_type": "SaveImage",
        "inputs": {
            "images": vae_decode_ref,
            "filename_prefix": "asuka_run/inpaint_",
        }
    }

    return base


# ─── Vérification + inpaint ciblé des chaussures (zone dynamique) ───────────
# Intégration avec shoe_consistency_checker.py — contrairement aux issues
# textuelles d'inpaint_corrector classique (zones fixes en ratio), la zone
# pieds est ici calculée dynamiquement à partir du squelette OpenPose de
# CHAQUE frame, car la pose change en permanence durant le cycle de course.

def review_and_inpaint_shoes(
    source_image_path: str,
    reference_shoe_path: str,
    frame_id: int,
    pose_keypoints: list | None = None,
    pose_json_path: str | None = None,
    image_w: int = 1024,
    image_h: int = 1536,
    seed: int = -1,
    auto_inpaint: bool = True,
    dry_run: bool = False,
    lora_name: str | None = "asuka-langley-soryuu-classic-ponyxl-lora-nochekaiser.safetensors",
    verbose: bool = False,
) -> dict:
    """
    Vérifie la cohérence des sneakers sur une frame et, selon auto_inpaint,
    déclenche directement la correction ou se contente de retourner le
    diagnostic pour validation manuelle.

    Mode automatique (auto_inpaint=True) :
        Qwen-VL juge → si mismatch → inpaint soumis immédiatement à ComfyUI

    Mode manuel (auto_inpaint=False) :
        Qwen-VL juge → diagnostic retourné (zone, issues, score) sans
        rien soumettre. Le studio peut alors ajuster la zone/le prompt
        avant d'appeler explicitement trigger_shoe_inpaint() avec le
        diagnostic validé.

    Returns:
        {
            "diagnosis": dict,       # sortie de check_shoe_consistency()
            "inpaint_triggered": bool,
            "inpaint_result": str | None,   # prompt_id ComfyUI si soumis
        }
    """
    try:
        from shoe_consistency_checker import check_shoe_consistency
    except ImportError:
        print("[inpaint_corrector] shoe_consistency_checker.py introuvable — "
              "place-le dans le même dossier (agents/)")
        return {"diagnosis": None, "inpaint_triggered": False, "inpaint_result": None}

    diagnosis = check_shoe_consistency(
        frame_path=source_image_path,
        reference_shoe_path=reference_shoe_path,
        pose_keypoints=pose_keypoints,
        pose_json_path=pose_json_path,
        image_w=image_w,
        image_h=image_h,
        verbose=verbose,
    )

    if diagnosis["passed"]:
        if verbose:
            print(f"[inpaint_corrector] Frame {frame_id:04d} — chaussures OK, pas d'inpaint")
        return {"diagnosis": diagnosis, "inpaint_triggered": False, "inpaint_result": None}

    if not auto_inpaint:
        if verbose:
            print(f"[inpaint_corrector] Frame {frame_id:04d} — mismatch détecté, "
                  f"en attente de validation manuelle (auto_inpaint=False)")
        return {"diagnosis": diagnosis, "inpaint_triggered": False, "inpaint_result": None}

    result_id = trigger_shoe_inpaint(
        source_image_path=source_image_path,
        zone=diagnosis["zone"],
        frame_id=frame_id,
        seed=seed,
        dry_run=dry_run,
        lora_name=lora_name,
    )
    return {"diagnosis": diagnosis, "inpaint_triggered": True, "inpaint_result": result_id}


def trigger_shoe_inpaint(
    source_image_path: str,
    zone: tuple,
    frame_id: int,
    seed: int = -1,
    dry_run: bool = False,
    lora_name: str | None = "asuka-langley-soryuu-classic-ponyxl-lora-nochekaiser.safetensors",
) -> str | None:
    """
    Soumet l'inpaint pour une zone pieds déjà calculée (pixels absolus).
    Utilise un crop+stitch : seule la région autour des pieds est envoyée
    au modèle, avec un contexte local suffisant pour que l'IA comprenne
    la scène (bas du jean, fond blanc) sans régénérer toute l'image.

    Returns:
        prompt_id ComfyUI, identifiant dry-run, ou None si échec
    """
    if not HAS_PIL:
        print("[inpaint_corrector] PIL requis pour l'inpaint")
        return None

    source_path = Path(source_image_path)
    if not source_path.exists():
        print(f"[inpaint_corrector] Source non trouvée : {source_image_path}")
        return None

    # ── 1. Générer le masque pixel-perfect ──
    # Priorité : FootSegNet (SAM ViT-B fine-tuné pieds/chaussures, inférence
    # locale torch) si son checkpoint entraîné existe. Sinon repli sur le SAM
    # générique via l'API ComfyUI (sam_mask_generator), puis repli
    # rectangulaire en dernier recours. Les deux produisent la même convention
    # de masque (NOIR=régénérer, BLANC=préserver).
    mask_name = f"mask_frame_{frame_id:04d}_shoe_mismatch.png"
    mask_path = Path(COMFYUI_INPUT) / mask_name

    sam_result = None
    if FOOTSEGNET_CKPT.exists():
        try:
            # Import par chemin explicite : "infer" est un nom trop générique
            # pour être ajouté au sys.path sans risque de collision.
            import importlib.util
            _spec = importlib.util.spec_from_file_location(
                "footsegnet_infer", str(FOOTSEGNET_DIR / "infer.py"))
            _footsegnet = importlib.util.module_from_spec(_spec)
            _spec.loader.exec_module(_footsegnet)
            sam_result = _footsegnet.generate_foot_mask(
                frame_path=source_image_path,
                zone=zone,
                output_path=str(mask_path),
                threshold=0.5,
                verbose=True,
            )
            if not sam_result:
                print("[inpaint_corrector] FootSegNet a échoué — repli SAM générique")
        except Exception as e:
            print(f"[inpaint_corrector] FootSegNet indisponible ({e}) — repli SAM générique")
            sam_result = None
    else:
        print(f"[inpaint_corrector] Checkpoint FootSegNet absent "
              f"({FOOTSEGNET_CKPT}) — SAM générique via ComfyUI")

    if not sam_result:
        try:
            from sam_mask_generator import generate_sam_mask
            sam_result = generate_sam_mask(
                frame_path=source_image_path,
                zone=zone,
                output_path=str(mask_path),
                threshold=0.5,
                verbose=True,
            )
            if not sam_result:
                print("[inpaint_corrector] SAM a échoué — repli sur masque rectangulaire")
                sam_result = None
        except ImportError:
            print("[inpaint_corrector] sam_mask_generator.py introuvable — repli rectangulaire")
            sam_result = None

    if not sam_result:
        # Repli : masque rectangulaire PIL (ancienne méthode)
        img = Image.open(source_image_path)
        iw, ih = img.size
        x, y, w, h = zone
        zone_ratio = (x / iw, y / ih, w / iw, h / ih)
        mask = create_inpaint_mask(iw, ih, zone_ratio)
        try:
            mask.save(str(mask_path))
        except Exception as e:
            print(f"[inpaint_corrector] Erreur sauvegarde masque repli : {e}")
            return None

    # ── 2. Sauvegarder crop + masque dans ComfyUI/input/ ──
    crop_name = f"crop_frame_{frame_id:04d}_shoe.png"
    mask_name = f"mask_frame_{frame_id:04d}_shoe_mismatch.png"
    crop_path = Path(COMFYUI_INPUT) / crop_name
    mask_path = Path(COMFYUI_INPUT) / mask_name

    try:
        crop_img.save(str(crop_path))
        # Sauvegarder aussi une copie du masque localement pour le stitch
        mask_crop.save(str(mask_path))
        # Version RGB pour ComfyUI (LoadImage attend RGB ou RGBA)
        mask_rgb = Image.merge("RGB", [mask_crop, mask_crop, mask_crop])
        mask_rgb.save(str(Path(COMFYUI_INPUT) / mask_name))
    except Exception as e:
        print(f"[inpaint_corrector] Erreur sauvegarde crop/masque : {e}")
        return None

    # Copie source complète dans input (pour le stitch final)
    src_name = source_path.name
    src_dst  = Path(COMFYUI_INPUT) / src_name
    if not src_dst.exists():
        import shutil
        shutil.copy2(source_image_path, str(src_dst))

    pos_prompt = ISSUE_PROMPTS.get(
        "shoe_mismatch",
        "nike air jordan sneakers, consistent colorway on both feet"
    )
    neg_prompt = "worst quality, blurry, deformed, extra limbs, mismatched shoes, nsfw, gray background, gray fill, gray rectangle, dark background, gradient background"

    wf = build_inpaint_workflow(
        source_image_name=crop_name,   # le crop, pas l'image entière
        mask_image_name=mask_name,
        positive_prompt=pos_prompt,
        negative_prompt=neg_prompt,
        seed=seed,
        lora_name=lora_name,
    )

    if dry_run or not HAS_REQUESTS:
        print(f"[inpaint_corrector] DRY RUN — inpaint shoe_mismatch frame {frame_id:04d} "
              f"zone={zone} crop={crop_box}")
        return f"dry_run_shoe_mismatch_{frame_id}"

    try:
        payload = {"prompt": wf}
        r = _req.post(f"{COMFYUI_URL}/prompt", json=payload, timeout=30)
        r.raise_for_status()
        pid = r.json().get("prompt_id")
        print(f"[inpaint_corrector] Inpaint 'shoe_mismatch' frame {frame_id:04d} "
              f"soumis (crop+stitch) — pid={pid}")
        # Stocker crop_box et mask_crop pour le stitch post-génération
        # (à appeler manuellement ou via le pipeline une fois le job terminé)
        _pending_stitches[pid] = {
            "source": source_image_path,
            "crop_box": crop_box,
            "mask_path": str(mask_path),
            "frame_id": frame_id,
        }
        return pid
    except Exception as e:
        print(f"[inpaint_corrector] ERREUR submit inpaint shoe_mismatch : {e}")
        return None


# Registre des stitches en attente (pid → infos pour recoller le crop)
_pending_stitches: dict = {}


def apply_stitch(prompt_id: str, inpainted_image_path: str) -> str | None:
    """
    Recolle le crop inpainté dans l'image originale une fois le job ComfyUI terminé.
    À appeler avec le chemin de l'image produite par ComfyUI (output/asuka_run/inpaint_...).

    Returns:
        Chemin de l'image finale recollée, ou None si erreur.
    """
    info = _pending_stitches.get(prompt_id)
    if not info:
        print(f"[inpaint_corrector] Aucun stitch en attente pour pid={prompt_id}")
        return None

    inpainted = Image.open(inpainted_image_path).convert("RGB")
    mask_crop = Image.open(info["mask_path"]).convert("L")

    output_path = str(Path(info["source"]).parent /
                      f"stitched_frame_{info['frame_id']:04d}.png")

    ok = stitch_inpaint_result(
        original_path=info["source"],
        inpainted_crop=inpainted,
        crop_box=info["crop_box"],
        mask_crop=mask_crop,
        output_path=output_path,
    )
    if ok:
        print(f"[inpaint_corrector] Stitch OK → {output_path}")
        del _pending_stitches[prompt_id]
        return output_path
    return None


# ─── Pipeline inpaint automatique depuis issues QwenVL (zones fixes) ────────

def auto_inpaint_from_issues(
    source_image_path: str,
    issues: list[str],
    frame_id: int,
    seed: int = -1,
    dry_run: bool = False,
    lora_name: str | None = "asuka-langley-soryuu-classic-ponyxl-lora-nochekaiser.safetensors",
) -> list[str]:
    """
    Lance un inpaint pour chaque issue détectée par QwenVL.
    Retourne la liste des fichiers de sortie produits.
    """
    if not HAS_PIL:
        print("[inpaint_corrector] PIL requis pour l'inpaint automatique")
        return []

    results = []
    source_path = Path(source_image_path)
    if not source_path.exists():
        print(f"[inpaint_corrector] Source non trouvée : {source_image_path}")
        return []

    img = Image.open(source_image_path)
    img_w, img_h = img.size

    for issue in issues:
        issue_lower = issue.lower()
        matched_key = None
        for key in KNOWN_ISSUE_ZONES:
            if key in issue_lower:
                matched_key = key
                break

        if matched_key is None:
            print(f"[inpaint_corrector] Issue '{issue}' non reconnue — SKIP")
            continue

        zone = KNOWN_ISSUE_ZONES[matched_key]
        pos_prompt = ISSUE_PROMPTS.get(
            matched_key,
            "(masterpiece:1.4), asuka langley soryu, red plugsuit, anime style"
        )
        neg_prompt = "worst quality, blurry, deformed, extra limbs, nsfw"

        # Génération du masque
        mask = create_inpaint_mask(img_w, img_h, zone)
        mask_name = f"mask_frame_{frame_id:04d}_{matched_key.replace(' ', '_')}.png"
        mask_path = Path(COMFYUI_INPUT) / mask_name

        try:
            mask.save(str(mask_path))
        except Exception as e:
            print(f"[inpaint_corrector] Erreur sauvegarde masque : {e}")
            continue

        # Copie source dans ComfyUI/input
        src_name = source_path.name
        src_dst  = Path(COMFYUI_INPUT) / src_name
        if not src_dst.exists():
            import shutil
            shutil.copy2(source_image_path, str(src_dst))

        # Build workflow
        wf = build_inpaint_workflow(
            source_image_name=src_name,
            mask_image_name=mask_name,
            positive_prompt=pos_prompt,
            negative_prompt=neg_prompt,
            seed=seed,
            lora_name=lora_name,
        )

        if dry_run or not HAS_REQUESTS:
            print(f"[inpaint_corrector] DRY RUN — inpaint {matched_key} frame {frame_id:04d}")
            results.append(f"dry_run_{matched_key}_{frame_id}")
            continue

        try:
            payload = {"prompt": wf}
            r = _req.post(f"{COMFYUI_URL}/prompt", json=payload, timeout=30)
            r.raise_for_status()
            pid = r.json().get("prompt_id")
            print(
                f"[inpaint_corrector] Inpaint '{matched_key}' frame {frame_id:04d} "
                f"soumis — pid={pid}"
            )
            results.append(pid)
        except Exception as e:
            print(f"[inpaint_corrector] ERREUR submit inpaint : {e}")

    return results


# ─── CLI ─────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Ov3rLoRd — Inpaint Corrector")
    parser.add_argument("--image",    required=True, help="Frame source à corriger")
    parser.add_argument("--issues",   nargs="+",     help="Issues à corriger (ex: 'thigh stripe')")
    parser.add_argument("--frame-id", type=int, default=0)
    parser.add_argument("--seed",     type=int, default=-1)
    parser.add_argument("--dry-run",  action="store_true")

    # Mode shoe-check : court-circuite le système d'issues textuelles fixes
    # au profit du diagnostic dynamique via squelette OpenPose
    parser.add_argument("--shoe-check", action="store_true",
                        help="Active le mode vérification/inpaint chaussures (zone dynamique)")
    parser.add_argument("--reference",  default=None,
                        help="Image de référence sneaker (requis avec --shoe-check)")
    parser.add_argument("--pose-json",  default=None,
                        help="Export POSE_KEYPOINT JSON de la frame (optionnel)")
    parser.add_argument("--width",      type=int, default=1024)
    parser.add_argument("--height",     type=int, default=1536)
    parser.add_argument("--auto",       action="store_true",
                        help="Inpaint immédiat si mismatch détecté (sinon diagnostic seul)")
    parser.add_argument("--verbose",    action="store_true")

    args = parser.parse_args()

    if args.shoe_check:
        if not args.reference:
            print("[inpaint_corrector] --reference requis avec --shoe-check")
            raise SystemExit(1)
        outcome = review_and_inpaint_shoes(
            source_image_path=args.image,
            reference_shoe_path=args.reference,
            frame_id=args.frame_id,
            pose_json_path=args.pose_json,
            image_w=args.width,
            image_h=args.height,
            seed=args.seed,
            auto_inpaint=args.auto,
            dry_run=args.dry_run,
            verbose=args.verbose,
        )
        print(f"\nDiagnostic :\n{json.dumps(outcome['diagnosis'], indent=2, ensure_ascii=False)}")
        print(f"\nInpaint déclenché : {outcome['inpaint_triggered']}")
        if outcome["inpaint_result"]:
            print(f"Résultat : {outcome['inpaint_result']}")
    else:
        issues = args.issues or ["thigh stripe"]
        results = auto_inpaint_from_issues(
            args.image, issues, args.frame_id,
            seed=args.seed, dry_run=args.dry_run
        )
        print(f"Jobs lancés : {results}")

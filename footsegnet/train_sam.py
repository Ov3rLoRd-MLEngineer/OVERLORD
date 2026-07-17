# train_sam.py — FootSegNet (Ov3rLoRd Pipeline)
# Fine-tuning de SAM ViT-B sur le dataset COCO pieds/chaussures.
#
# Stratégie (RTX 5080 16GB) :
#   - image_encoder (ViT-B) et prompt_encoder GELÉS (forward en no_grad + bf16)
#   - seul le mask_decoder (~4M params) est entraîné
#   - prompt = boîte englobante du masque GT avec jitter aléatoire (train)
#   - loss = BCEWithLogits + Dice, calculée en basse résolution (256x256)
#     sur la région valide (hors padding)
#
# Checkpoint de départ : sam_vit_b_01ec64.pth (installation ComfyUI).
# Sorties : checkpoints\footsegnet_vit_b_best.pth (meilleur IoU val)
#           checkpoints\footsegnet_vit_b_last.pth (dernière epoch)
#
# Usage :
#   py -3.12 train_sam.py
#   py -3.12 train_sam.py --epochs 50 --batch-size 2 --lr 5e-5
#   py -3.12 train_sam.py --resume D:\OVERLORD\footsegnet\checkpoints\footsegnet_vit_b_last.pth

import argparse
import json
import random
import time
from pathlib import Path

import numpy as np
from PIL import Image

import torch
import torch.nn.functional as F
from torch.utils.data import Dataset, DataLoader

from segment_anything import sam_model_registry
from segment_anything.utils.transforms import ResizeLongestSide

from build_coco import decode_rle

# ── CONFIG ────────────────────────────────────────────────────────────────────
FOOTSEGNET_ROOT = Path(r"D:\OVERLORD\footsegnet")
IMAGES_DIR      = FOOTSEGNET_ROOT / "dataset" / "images"
ANNOT_DIR       = FOOTSEGNET_ROOT / "dataset" / "annotations"
CKPT_DIR        = FOOTSEGNET_ROOT / "checkpoints"
SAM_CHECKPOINT  = Path(r"D:\Ov3rLoRd AI\ComfyUI\models\sams\sam_vit_b_01ec64.pth")

IMG_SIZE     = 1024      # taille d'entrée SAM (côté long)
LOWRES_SIZE  = 256       # résolution de sortie du mask_decoder
BOX_JITTER   = 12        # jitter max (px, coordonnées image d'origine) sur la boîte prompt
PIXEL_MEAN   = torch.tensor([123.675, 116.28, 103.53]).view(3, 1, 1)
PIXEL_STD    = torch.tensor([58.395, 57.12, 57.375]).view(3, 1, 1)


# ── Dataset ──────────────────────────────────────────────────────────────────

class FootSegCocoDataset(Dataset):
    """Lit instances_{split}.json (RLE non compressé) + images du split."""

    def __init__(self, split: str, jitter: bool):
        self.split = split
        self.jitter = jitter
        self.img_dir = IMAGES_DIR / split
        coco_path = ANNOT_DIR / f"instances_{split}.json"
        if not coco_path.exists():
            raise FileNotFoundError(
                f"{coco_path} introuvable — lancer build_coco.py d'abord"
            )
        coco = json.loads(coco_path.read_text(encoding="utf-8"))
        images_by_id = {im["id"]: im for im in coco["images"]}
        self.samples = []
        for ann in coco["annotations"]:
            im = images_by_id.get(ann["image_id"])
            if im is not None:
                self.samples.append((im, ann))
        self.transform = ResizeLongestSide(IMG_SIZE)

    def __len__(self) -> int:
        return len(self.samples)

    def __getitem__(self, idx: int) -> dict:
        im_info, ann = self.samples[idx]
        img_path = self.img_dir / im_info["file_name"]
        image = np.array(Image.open(str(img_path)).convert("RGB"))
        oh, ow = image.shape[:2]

        mask = decode_rle(ann["segmentation"]).astype(np.float32)   # HxW 0/1

        # Boîte prompt depuis la bbox GT, avec jitter en entraînement
        x, y, w, h = ann["bbox"]
        box = np.array([x, y, x + w, y + h], dtype=np.float32)
        if self.jitter:
            box += np.random.uniform(-BOX_JITTER, BOX_JITTER, size=4).astype(np.float32)
            box[0] = float(np.clip(box[0], 0, ow - 2))
            box[1] = float(np.clip(box[1], 0, oh - 2))
            box[2] = float(np.clip(box[2], box[0] + 1, ow))
            box[3] = float(np.clip(box[3], box[1] + 1, oh))

        # Redimensionnement côté long = 1024 + padding bas/droite (protocole SAM)
        image_resized = self.transform.apply_image(image)            # rh x rw x 3
        rh, rw = image_resized.shape[:2]
        img_t = torch.as_tensor(image_resized, dtype=torch.float32).permute(2, 0, 1)
        img_t = (img_t - PIXEL_MEAN) / PIXEL_STD
        img_t = F.pad(img_t, (0, IMG_SIZE - rw, 0, IMG_SIZE - rh))

        mask_t = torch.as_tensor(mask).unsqueeze(0).unsqueeze(0)     # 1x1xHxW
        mask_t = F.interpolate(mask_t, size=(rh, rw), mode="nearest")
        mask_t = F.pad(mask_t, (0, IMG_SIZE - rw, 0, IMG_SIZE - rh)).squeeze(0)  # 1x1024x1024

        valid = torch.zeros(1, IMG_SIZE, IMG_SIZE)
        valid[:, :rh, :rw] = 1.0

        box_resized = self.transform.apply_boxes(box.reshape(1, 4), (oh, ow))[0]

        return {
            "image": img_t,
            "mask": mask_t,
            "valid": valid,
            "box": torch.as_tensor(box_resized, dtype=torch.float32),
            "resized_hw": torch.tensor([rh, rw]),
        }


# ── Loss ─────────────────────────────────────────────────────────────────────

def dice_loss(logits: torch.Tensor, target: torch.Tensor, valid: torch.Tensor) -> torch.Tensor:
    probs = torch.sigmoid(logits) * valid
    target = target * valid
    num = 2.0 * (probs * target).sum(dim=(1, 2, 3))
    den = probs.sum(dim=(1, 2, 3)) + target.sum(dim=(1, 2, 3)) + 1e-6
    return (1.0 - num / den).mean()


def seg_loss(logits: torch.Tensor, target: torch.Tensor, valid: torch.Tensor) -> torch.Tensor:
    bce = F.binary_cross_entropy_with_logits(logits, target, reduction="none")
    bce = (bce * valid).sum() / valid.sum().clamp(min=1.0)
    return bce + dice_loss(logits, target, valid)


# ── Forward (encodeur gelé, décodeur entraîné) ───────────────────────────────

def forward_batch(sam, batch: dict, device: str, use_bf16: bool):
    images = batch["image"].to(device)
    boxes  = batch["box"].to(device)

    autocast_ctx = torch.autocast(device_type="cuda", dtype=torch.bfloat16,
                                  enabled=use_bf16)
    with torch.no_grad(), autocast_ctx:
        image_embeddings = sam.image_encoder(images)
        sparse_emb, dense_emb = sam.prompt_encoder(
            points=None, boxes=boxes, masks=None
        )

    # mask_decoder.predict_masks() de segment_anything suppose une image
    # unique (batch=1) répétée pour N prompts (repeat_interleave sur
    # tokens.shape[0]), pas un batch de N images distinctes avec un prompt
    # chacune — passer directement des tenseurs de batch B lève un mismatch
    # de taille (B*B vs B). On boucle donc par échantillon pour le décodeur
    # (léger, 4M params) sans toucher au package installé.
    logits_list = []
    with autocast_ctx:
        for i in range(images.shape[0]):
            low_res_logits, _iou = sam.mask_decoder(
                image_embeddings=image_embeddings[i:i + 1],
                image_pe=sam.prompt_encoder.get_dense_pe(),
                sparse_prompt_embeddings=sparse_emb[i:i + 1],
                dense_prompt_embeddings=dense_emb[i:i + 1],
                multimask_output=False,
            )
            logits_list.append(low_res_logits)
    low_res_logits = torch.cat(logits_list, dim=0)
    return low_res_logits.float()      # Bx1x256x256


def downsample_targets(batch: dict, device: str):
    gt = F.interpolate(batch["mask"].to(device), size=(LOWRES_SIZE, LOWRES_SIZE),
                       mode="nearest")
    valid = F.interpolate(batch["valid"].to(device),
                          size=(LOWRES_SIZE, LOWRES_SIZE), mode="nearest")
    return gt, valid


@torch.no_grad()
def evaluate(sam, loader: DataLoader, device: str, use_bf16: bool) -> float:
    sam.eval()
    ious = []
    for batch in loader:
        logits = forward_batch(sam, batch, device, use_bf16)
        gt, valid = downsample_targets(batch, device)
        pred = ((logits > 0).float() * valid)
        gt = gt * valid
        inter = (pred * gt).sum(dim=(1, 2, 3))
        union = ((pred + gt) > 0).float().sum(dim=(1, 2, 3)).clamp(min=1.0)
        ious.extend((inter / union).cpu().tolist())
    sam.train()
    return float(np.mean(ious)) if ious else 0.0


# ── Entraînement ─────────────────────────────────────────────────────────────

def train(args) -> None:
    if not torch.cuda.is_available():
        print("[train_sam] WARN : CUDA indisponible — entraînement CPU (très lent)")
    device = "cuda" if torch.cuda.is_available() else "cpu"
    use_bf16 = device == "cuda"

    torch.manual_seed(args.seed)
    np.random.seed(args.seed)
    random.seed(args.seed)

    ckpt = args.resume if args.resume else str(SAM_CHECKPOINT)
    print(f"[train_sam] Chargement SAM ViT-B depuis {ckpt}")
    sam = sam_model_registry["vit_b"](checkpoint=ckpt)
    sam.to(device)

    # Geler encodeur image + encodeur de prompts
    for p in sam.image_encoder.parameters():
        p.requires_grad = False
    for p in sam.prompt_encoder.parameters():
        p.requires_grad = False
    n_train = sum(p.numel() for p in sam.mask_decoder.parameters())
    print(f"[train_sam] Paramètres entraînés (mask_decoder) : {n_train / 1e6:.1f}M")

    train_ds = FootSegCocoDataset("train", jitter=True)
    val_ds   = FootSegCocoDataset("val",   jitter=False)
    print(f"[train_sam] train={len(train_ds)}  val={len(val_ds)}")

    # num_workers=0 : sûr sous Windows, dataset petit
    train_loader = DataLoader(train_ds, batch_size=args.batch_size, shuffle=True,
                              num_workers=0, drop_last=False)
    val_loader   = DataLoader(val_ds, batch_size=args.batch_size, shuffle=False,
                              num_workers=0)

    optimizer = torch.optim.AdamW(sam.mask_decoder.parameters(),
                                  lr=args.lr, weight_decay=args.weight_decay)
    scheduler = torch.optim.lr_scheduler.CosineAnnealingLR(optimizer,
                                                           T_max=args.epochs)

    CKPT_DIR.mkdir(parents=True, exist_ok=True)
    best_iou = 0.0
    sam.train()

    for epoch in range(1, args.epochs + 1):
        t0 = time.time()
        losses = []
        for step, batch in enumerate(train_loader, start=1):
            logits = forward_batch(sam, batch, device, use_bf16)
            gt, valid = downsample_targets(batch, device)
            loss = seg_loss(logits, gt, valid)

            optimizer.zero_grad(set_to_none=True)
            loss.backward()
            torch.nn.utils.clip_grad_norm_(sam.mask_decoder.parameters(), 1.0)
            optimizer.step()
            losses.append(loss.item())

            if step % 20 == 0:
                print(f"[train_sam]   epoch {epoch} step {step}/{len(train_loader)} "
                      f"loss={np.mean(losses[-20:]):.4f}")

        scheduler.step()
        val_iou = evaluate(sam, val_loader, device, use_bf16)
        print(f"[train_sam] epoch {epoch}/{args.epochs} — "
              f"loss={np.mean(losses):.4f}  val_IoU={val_iou:.4f}  "
              f"lr={scheduler.get_last_lr()[0]:.2e}  ({time.time() - t0:.0f}s)")

        torch.save(sam.state_dict(), str(CKPT_DIR / "footsegnet_vit_b_last.pth"))
        if val_iou > best_iou:
            best_iou = val_iou
            torch.save(sam.state_dict(), str(CKPT_DIR / "footsegnet_vit_b_best.pth"))
            print(f"[train_sam]   nouveau meilleur IoU ({best_iou:.4f}) — best sauvegardé")

    print(f"\n[train_sam] Terminé — meilleur IoU val : {best_iou:.4f}")
    print(f"[train_sam] Checkpoint : {CKPT_DIR / 'footsegnet_vit_b_best.pth'}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="FootSegNet — fine-tuning SAM ViT-B")
    parser.add_argument("--epochs",       type=int,   default=30)
    parser.add_argument("--batch-size",   type=int,   default=2,
                        help="2 tient confortablement sur 16GB (encodeur en no_grad+bf16)")
    parser.add_argument("--lr",           type=float, default=1e-4)
    parser.add_argument("--weight-decay", type=float, default=1e-4)
    parser.add_argument("--seed",         type=int,   default=1337)
    parser.add_argument("--resume",       default=None,
                        help="Checkpoint FootSegNet pour reprendre l'entraînement")
    args = parser.parse_args()
    train(args)

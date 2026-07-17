# train.py — HandSegNet (Ov3rLoRd Pipeline)
# Fine-tuning SAM ViT-B sur le dataset COCO mains/doigts/poignets.
# Même stratégie que footsegnet\train_sam.py (RTX 5080 16GB) :
#   encodeurs GELÉS (no_grad + bf16), seul le mask_decoder est entraîné,
#   prompt = bbox GT avec jitter, loss BCE+Dice en 256x256 sur région valide.
# L'entraînement est agnostique à la classe : chaque annotation COCO
# (une par catégorie et par image) est un échantillon indépendant.
#
# Usage :
#   py -3.12 train.py
#   py -3.12 train.py --epochs 50 --batch-size 2 --lr 5e-5

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
PROJECT        = "handsegnet"
PROJECT_ROOT   = Path(r"D:\OVERLORD\handsegnet")
IMAGES_DIR     = PROJECT_ROOT / "dataset" / "images"
ANNOT_DIR      = PROJECT_ROOT / "dataset" / "annotations"
CKPT_DIR       = PROJECT_ROOT / "checkpoints"
SAM_CHECKPOINT = Path(r"D:\Ov3rLoRd AI\ComfyUI\models\sams\sam_vit_b_01ec64.pth")

IMG_SIZE    = 1024
LOWRES_SIZE = 256
BOX_JITTER  = 12
PIXEL_MEAN  = torch.tensor([123.675, 116.28, 103.53]).view(3, 1, 1)
PIXEL_STD   = torch.tensor([58.395, 57.12, 57.375]).view(3, 1, 1)


# ── Dataset ──────────────────────────────────────────────────────────────────

class SegCocoDataset(Dataset):
    """Lit instances_{split}.json (RLE non compressé) — un échantillon par annotation."""

    def __init__(self, split: str, jitter: bool):
        self.split = split
        self.jitter = jitter
        self.img_dir = IMAGES_DIR / split
        coco_path = ANNOT_DIR / f"instances_{split}.json"
        if not coco_path.exists():
            raise FileNotFoundError(f"{coco_path} introuvable — lancer build_coco.py d'abord")
        coco = json.loads(coco_path.read_text(encoding="utf-8"))
        images_by_id = {im["id"]: im for im in coco["images"]}
        self.samples = [
            (images_by_id[ann["image_id"]], ann)
            for ann in coco["annotations"]
            if ann["image_id"] in images_by_id
        ]
        self.transform = ResizeLongestSide(IMG_SIZE)

    def __len__(self) -> int:
        return len(self.samples)

    def __getitem__(self, idx: int) -> dict:
        im_info, ann = self.samples[idx]
        image = np.array(Image.open(str(self.img_dir / im_info["file_name"])).convert("RGB"))
        oh, ow = image.shape[:2]

        mask = decode_rle(ann["segmentation"]).astype(np.float32)

        x, y, w, h = ann["bbox"]
        box = np.array([x, y, x + w, y + h], dtype=np.float32)
        if self.jitter:
            box += np.random.uniform(-BOX_JITTER, BOX_JITTER, size=4).astype(np.float32)
            box[0] = float(np.clip(box[0], 0, ow - 2))
            box[1] = float(np.clip(box[1], 0, oh - 2))
            box[2] = float(np.clip(box[2], box[0] + 1, ow))
            box[3] = float(np.clip(box[3], box[1] + 1, oh))

        image_resized = self.transform.apply_image(image)
        rh, rw = image_resized.shape[:2]
        img_t = torch.as_tensor(image_resized, dtype=torch.float32).permute(2, 0, 1)
        img_t = (img_t - PIXEL_MEAN) / PIXEL_STD
        img_t = F.pad(img_t, (0, IMG_SIZE - rw, 0, IMG_SIZE - rh))

        mask_t = torch.as_tensor(mask).unsqueeze(0).unsqueeze(0)
        mask_t = F.interpolate(mask_t, size=(rh, rw), mode="nearest")
        mask_t = F.pad(mask_t, (0, IMG_SIZE - rw, 0, IMG_SIZE - rh)).squeeze(0)

        valid = torch.zeros(1, IMG_SIZE, IMG_SIZE)
        valid[:, :rh, :rw] = 1.0

        box_resized = self.transform.apply_boxes(box.reshape(1, 4), (oh, ow))[0]

        return {
            "image": img_t,
            "mask": mask_t,
            "valid": valid,
            "box": torch.as_tensor(box_resized, dtype=torch.float32),
        }


# ── Loss ─────────────────────────────────────────────────────────────────────

def dice_loss(logits, target, valid):
    probs = torch.sigmoid(logits) * valid
    target = target * valid
    num = 2.0 * (probs * target).sum(dim=(1, 2, 3))
    den = probs.sum(dim=(1, 2, 3)) + target.sum(dim=(1, 2, 3)) + 1e-6
    return (1.0 - num / den).mean()


def seg_loss(logits, target, valid):
    bce = F.binary_cross_entropy_with_logits(logits, target, reduction="none")
    bce = (bce * valid).sum() / valid.sum().clamp(min=1.0)
    return bce + dice_loss(logits, target, valid)


# ── Forward (encodeur gelé, décodeur entraîné) ───────────────────────────────

def forward_batch(sam, batch, device, use_bf16):
    images = batch["image"].to(device)
    boxes  = batch["box"].to(device)

    autocast_ctx = torch.autocast(device_type="cuda", dtype=torch.bfloat16,
                                  enabled=use_bf16)
    with torch.no_grad(), autocast_ctx:
        image_embeddings = sam.image_encoder(images)
        sparse_emb, dense_emb = sam.prompt_encoder(points=None, boxes=boxes, masks=None)

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
    return low_res_logits.float()


def downsample_targets(batch, device):
    gt = F.interpolate(batch["mask"].to(device), size=(LOWRES_SIZE, LOWRES_SIZE),
                       mode="nearest")
    valid = F.interpolate(batch["valid"].to(device),
                          size=(LOWRES_SIZE, LOWRES_SIZE), mode="nearest")
    return gt, valid


@torch.no_grad()
def evaluate(sam, loader, device, use_bf16) -> float:
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
        print(f"[{PROJECT}] WARN : CUDA indisponible — entraînement CPU (très lent)")
    device = "cuda" if torch.cuda.is_available() else "cpu"
    use_bf16 = device == "cuda"

    torch.manual_seed(args.seed)
    np.random.seed(args.seed)
    random.seed(args.seed)

    ckpt = args.resume if args.resume else str(SAM_CHECKPOINT)
    print(f"[{PROJECT}] Chargement SAM ViT-B depuis {ckpt}")
    sam = sam_model_registry["vit_b"](checkpoint=ckpt)
    sam.to(device)

    for p in sam.image_encoder.parameters():
        p.requires_grad = False
    for p in sam.prompt_encoder.parameters():
        p.requires_grad = False
    n_train = sum(p.numel() for p in sam.mask_decoder.parameters())
    print(f"[{PROJECT}] Paramètres entraînés (mask_decoder) : {n_train / 1e6:.1f}M")

    train_ds = SegCocoDataset("train", jitter=True)
    val_ds   = SegCocoDataset("val",   jitter=False)
    print(f"[{PROJECT}] train={len(train_ds)}  val={len(val_ds)} (annotations)")

    # num_workers>0 : parallélise lecture PNG/décodage RLE/resize sur CPU
    # pendant que le GPU calcule (i7-8700K, 6 cœurs physiques/12 threads) ;
    # nécessite le garde if __name__ == "__main__" pour le spawn Windows.
    train_loader = DataLoader(train_ds, batch_size=args.batch_size, shuffle=True,
                              num_workers=6, pin_memory=True, drop_last=False)
    val_loader   = DataLoader(val_ds, batch_size=args.batch_size, shuffle=False,
                              num_workers=4, pin_memory=True)

    optimizer = torch.optim.AdamW(sam.mask_decoder.parameters(),
                                  lr=args.lr, weight_decay=args.weight_decay)
    scheduler = torch.optim.lr_scheduler.CosineAnnealingLR(optimizer, T_max=args.epochs)

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
                print(f"[{PROJECT}]   epoch {epoch} step {step}/{len(train_loader)} "
                      f"loss={np.mean(losses[-20:]):.4f}")

        scheduler.step()
        val_iou = evaluate(sam, val_loader, device, use_bf16)
        print(f"[{PROJECT}] epoch {epoch}/{args.epochs} — loss={np.mean(losses):.4f}  "
              f"val_IoU={val_iou:.4f}  lr={scheduler.get_last_lr()[0]:.2e}  "
              f"({time.time() - t0:.0f}s)")

        torch.save(sam.state_dict(), str(CKPT_DIR / f"{PROJECT}_vit_b_last.pth"))
        if val_iou > best_iou:
            best_iou = val_iou
            torch.save(sam.state_dict(), str(CKPT_DIR / f"{PROJECT}_vit_b_best.pth"))
            print(f"[{PROJECT}]   nouveau meilleur IoU ({best_iou:.4f}) — best sauvegardé")

    print(f"\n[{PROJECT}] Terminé — meilleur IoU val : {best_iou:.4f}")
    print(f"[{PROJECT}] Checkpoint : {CKPT_DIR / (PROJECT + '_vit_b_best.pth')}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=f"{PROJECT} — fine-tuning SAM ViT-B")
    parser.add_argument("--epochs",       type=int,   default=30)
    parser.add_argument("--batch-size",   type=int,   default=2)
    parser.add_argument("--lr",           type=float, default=1e-4)
    parser.add_argument("--weight-decay", type=float, default=1e-4)
    parser.add_argument("--seed",         type=int,   default=1337)
    parser.add_argument("--resume",       default=None)
    args = parser.parse_args()
    train(args)

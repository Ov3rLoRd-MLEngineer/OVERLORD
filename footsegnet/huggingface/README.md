---
license: apache-2.0
tags:
  - image-segmentation
  - segment-anything
  - sam
  - anime
  - illustration
  - pytorch
pipeline_tag: image-segmentation
library_name: pytorch
---

# FootSegNet

FootSegNet is a **SAM ViT-B fine-tune specialized in segmenting feet and
shoes on anime-style illustrations**. It exists because generic SAM
(`sam_vit_b_01ec64.pth`), when prompted with a rough foot region, is
unreliable on stylized/anime art — flat shading, thin ankle straps, and
non-photoreal proportions confuse it in ways it isn't confused on photos.
FootSegNet fine-tunes only SAM's mask decoder on a small hand-annotated
anime dataset to fix that, while keeping the rest of SAM (image encoder,
prompt encoder) frozen and untouched.

It was built as a component of a personal anime image/video generation
pipeline ([Ov3rLoRd](https://github.com/Ov3rLoRd-MLEngineer)), to drive
targeted inpainting of feet/shoes without disturbing the
rest of a frame — but the model itself is a plain SAM checkpoint with no
pipeline-specific code baked in, and works standalone for anyone who needs
foot/shoe masks on anime-style images (dataset curation, cutout tools,
your own inpainting pipeline, etc.).

## Results

| | |
|---|---|
| Base model | SAM ViT-B (`sam_vit_b_01ec64.pth`, Meta) |
| Training data | 300 hand-annotated anime images (1024×1536, fabricatedXL renders), pixel-perfect masks drawn with a stylus/mouse over a SAM pre-fill |
| Augmentation | horizontal flip × ±15° rotation → 1620 train samples from 270 base images (30 held out for validation, unaugmented) |
| Trainable parameters | mask decoder only, ~4M of the model's 93.7M total (image encoder + prompt encoder frozen) |
| Validation IoU | **0.9277** |
| Checkpoint size | 375 MB (`.pth`) / 375 MB (`.safetensors`, lossless conversion — see below) |

The validation IoU is measured against the same box-prompted setup used at
train time (ground-truth foot bounding box, no jitter) — see
[Limitations](#limitations) for what happens outside that setup.

## Usage

Requires `torch`, `torchvision`, `Pillow`, `numpy`, and Meta's
`segment-anything` package. `safetensors` is only needed if you use the
`.safetensors` checkpoint instead of the original `.pth`.

```bash
pip install torch torchvision pillow numpy
pip install git+https://github.com/facebookresearch/segment-anything.git
```

Minimal example (see `standalone_infer.py` in this repo for a complete,
dependency-free CLI script):

```python
import torch
from segment_anything import sam_model_registry, SamPredictor
from PIL import Image
import numpy as np

sam = sam_model_registry["vit_b"](checkpoint=None)
state_dict = torch.load("footsegnet_vit_b_best.pth", map_location="cpu", weights_only=True)
# or: from safetensors.torch import load_file; state_dict = load_file("footsegnet_vit_b_best.safetensors")
sam.load_state_dict(state_dict)
sam.to("cuda").eval()

predictor = SamPredictor(sam)
image = np.array(Image.open("character.png").convert("RGB"))
predictor.set_image(image)

# box = (x1, y1, x2, y2) around the foot/shoe region — see Limitations
box = np.array([517, 1109, 738, 1404])
masks, scores, _ = predictor.predict(box=box, multimask_output=False)
Image.fromarray((masks[0] * 255).astype("uint8")).save("foot_mask.png")
```

Output convention: **white (255) = foot/shoe, black (0) = background**
(standard segmentation convention). If you're wiring this into a
pipeline that expects the inverse (black = region to inpaint), invert
the mask yourself — the Ov3rLoRd pipeline's own `infer.py` does exactly
that for its internal use.

### Converting to safetensors

`convert_to_safetensors.py` in this repo does a lossless conversion of the
original `.pth` state dict (verified tensor-for-tensor identical after
round-trip — no quantization, no precision loss):

```bash
python convert_to_safetensors.py --input footsegnet_vit_b_best.pth --output footsegnet_vit_b_best.safetensors --verify
```

## Limitations

**This model needs a bounding box around the foot/shoe region — it is not
a full-image detector.** SAM is a promptable segmenter, not a classifier:
if you run it with a box covering the whole image, it will segment
whatever prominent subject best fits that box (typically the entire
character silhouette), not just the feet. In practice this means you need
an upstream step (pose estimation, manual annotation, an object detector)
to produce a rough foot bounding box first. In the original pipeline this
box comes from ankle keypoints (DWPose OpenPose-format output); that
upstream pose estimation is itself imperfect and is the main source of
end-to-end failures, not the segmentation step itself:

| Failure mode | Why |
|---|---|
| Loose/flowing garments (wide kimono, flowing dress) | occlude the leg silhouette — ankle keypoints become unreliable or the derived box misses the actual foot position |
| Low-angle / worm's-eye view shots | foreshortening distorts the leg-to-ankle geometry the pose estimator expects |
| Raised arm poses | can shift keypoint confidence/ordering enough to throw off the derived foot box |
| Legs close together / overlapping | ankle keypoints for the two feet can merge or swap |

Overall, upstream pose-based box derivation fails or produces a
significantly-off box in roughly **20–40% of cases**, depending heavily on
how atypical the pose is — this is a characteristic of the pose estimator
feeding the box, not of FootSegNet's segmentation quality once given a
reasonable box. If you supply your own boxes (manual annotation, a
detector trained on your domain), this failure mode doesn't apply to you.

Other things to know:
- Trained exclusively on a specific anime rendering style (fabricatedXL,
  1024×1536 full-body compositions) and not benchmarked outside that
  distribution — no claim is made about how it performs on other
  anime/illustration styles, and it is likely to degrade further on styles
  further from that distribution (chibi, western cartoon, photo).
- Validation set is small (30 images) and drawn from the same generation
  pipeline as training data, not an independent held-out distribution —
  treat the 0.9277 IoU as an optimistic estimate of in-distribution
  performance, not a general-purpose benchmark number.
- Single-instance box prompt per call: if a box covers two overlapping
  feet, you get one merged mask, not two instances.

## License

Apache 2.0. Attribution appreciated: *FootSegNet by Ov3rLoRd / Jérémy
Gourlain*.

## Support this project

If FootSegNet is useful to you, consider supporting further development:

- Ko-fi: `<placeholder — link to be added>`
- GitHub Sponsors: `<placeholder — link to be added>`

## Acknowledgements

Built on [Segment Anything](https://github.com/facebookresearch/segment-anything)
(Meta AI, Apache 2.0). Part of the [Ov3rLoRd](https://github.com/Ov3rLoRd-MLEngineer)
pipeline.

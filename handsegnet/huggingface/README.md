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

# HandSegNet

HandSegNet is a **SAM ViT-B fine-tune specialized in segmenting hands on
anime-style illustrations**. It exists because generic SAM
(`sam_vit_b_01ec64.pth`), when prompted with a rough hand region, is
unreliable on stylized/anime art — flat shading, gloves, overlapping
fingers, and non-photoreal proportions confuse it in ways it isn't confused
on photos. HandSegNet fine-tunes only SAM's mask decoder on a small
hand-annotated anime dataset to fix that, while keeping the rest of SAM
(image encoder, prompt encoder) frozen and untouched. Same architecture and
training recipe as [FootSegNet](https://huggingface.co/Ov3rLoRd-MLEngineer/footsegnet)
(sibling model, feet/shoes), released earlier from the same pipeline.

It was built as a component of a personal anime image/video generation
pipeline ([Ov3rLoRd](https://github.com/Ov3rLoRd-MLEngineer)), to drive
targeted inpainting of hands without disturbing the rest of a frame — but
the model itself is a plain SAM checkpoint with no pipeline-specific code
baked in, and works standalone for anyone who needs hand masks on
anime-style images (dataset curation, cutout tools, your own inpainting
pipeline, etc.).

## Results — read this before trusting the headline number

| | |
|---|---|
| Base model | SAM ViT-B (`sam_vit_b_01ec64.pth`, Meta) |
| Training data | 320 hand-annotated anime images (1024×1280, fabricatedXL renders), pixel-perfect masks drawn with a stylus/mouse over a SAM pre-fill |
| Augmentation | horizontal flip × ±15° rotation → 1728 train samples from 288 base images (32 held out for validation, unaugmented) |
| Trainable parameters | mask decoder only, ~4.1M of the model's 93.7M total (image encoder + prompt encoder frozen) |
| Validation IoU (ground-truth box) | **0.8876** |
| Validation IoU (automatic box, real pipeline) | **0.722 mean / 0.773 median** (min 0.083) |
| Checkpoint size | 375 MB (`.pth`) / 375 MB (`.safetensors`, lossless conversion — see below) |

**These are two different numbers measuring two different things, and the
gap between them matters more here than it did for FootSegNet:**

- **0.8876** is measured the same way FootSegNet's headline number was: the
  mask decoder is prompted with the **ground-truth hand bounding box**
  (+ small random jitter), i.e. "if you already know exactly where the hand
  is, how good is the segmentation." This isolates mask_decoder quality.
- **0.722 mean / 0.773 median** is measured with boxes produced by an
  **automatic upstream detector** (VLM grounding, asked to locate "the
  character's hands") instead of ground truth — i.e. closer to what you'd
  actually get running this model end-to-end without hand-supplying boxes
  yourself. It was measured over the same 32-image validation set.

Unlike feet (reliably boxed from ankle keypoints via pose estimation),
**hands don't have an equally reliable off-the-shelf box source** in the
pipeline this model was built in — no dedicated hand-pose detector was
available, so an open-vocabulary VLM grounding call was used instead, and
it is noticeably less reliable on scenes with two hands (missing one hand
entirely, or placing the box on a wristband/sleeve instead of the fingers,
happened repeatedly in the 32-image check). **This is not a statement
about mask_decoder quality — it's a statement about how much the box
source matters for hands specifically.** If you supply your own
well-localized per-hand boxes (manual annotation, a detector trained on
your domain, a hand-pose model), expect results closer to the 0.8876 number
than the 0.722 one.

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
state_dict = torch.load("handsegnet_vit_b_best.pth", map_location="cpu", weights_only=True)
# or: from safetensors.torch import load_file; state_dict = load_file("handsegnet_vit_b_best.safetensors")
sam.load_state_dict(state_dict)
sam.to("cuda").eval()

predictor = SamPredictor(sam)
image = np.array(Image.open("character.png").convert("RGB"))
predictor.set_image(image)

# box = (x1, y1, x2, y2) around ONE hand — see Limitations for why box quality matters
box = np.array([137, 612, 547, 1152])
masks, scores, _ = predictor.predict(box=box, multimask_output=False)
Image.fromarray((masks[0] * 255).astype("uint8")).save("hand_mask.png")
```

**Two hands in frame → two calls.** This model prompts SAM with a single
box per call, same as the underlying architecture. For a scene with both
hands visible, run inference once per hand box and union the two output
masks (`np.maximum(mask1, mask2)`) yourself — there is no built-in
multi-instance mode in this checkpoint.

Output convention: **white (255) = hand, black (0) = background** (standard
segmentation convention). If you're wiring this into a pipeline that
expects the inverse (black = region to inpaint), invert the mask yourself —
the Ov3rLoRd pipeline's own `infer.py` does exactly that for its internal
use.

### Converting to safetensors

`convert_to_safetensors.py` in this repo does a lossless conversion of the
original `.pth` state dict (verified tensor-for-tensor identical after
round-trip — no quantization, no precision loss):

```bash
python convert_to_safetensors.py --input handsegnet_vit_b_best.pth --output handsegnet_vit_b_best.safetensors --verify
```

## Limitations

**This model needs a bounding box around each hand — it is not a full-image
detector, and it is not multi-instance.** SAM is a promptable segmenter,
not a classifier: if you run it with a box covering the whole image, it
will segment whatever prominent subject best fits that box (typically the
entire character silhouette), not just a hand. You need an upstream step
(pose estimation, an object/hand detector, manual annotation) to produce a
box per hand first — see the Results section above for how much this
upstream step matters for hands specifically (0.888 with a good box vs.
0.722 mean with an imperfect automatic one).

Beyond the box-dependency itself, three recurring failure patterns were
identified during evaluation, specific to hand anatomy (not shared with
FootSegNet, whose defects are milder: soft/"melted" edges, small
over-segmentation — a simpler shape has fewer ways to go wrong):

| Pattern | What happens | When it shows up |
|---|---|---|
| Mirroring collapse | The two hands fuse into one symmetric decorative blob instead of two anatomically distinct hands — no individual fingers or thumbs delineated | Compositions where both hands touch or interlock (praying/cupping gestures, hands clasped together, especially when also holding an object) |
| Finger dropout | One or more individual fingers are missing or truncated in the predicted mask even though the box is correctly placed | Splayed/spread-fingers poses where fingers are clearly separated (not touching) — a different failure mode from mirroring, not caused by finger contact |
| Box misses a hand entirely | Upstream box detector (whatever you use) places the box on the wrong region (wrist, sleeve, accessory) or only finds one of two hands in frame | Two-hand compositions, hands partially occluded by an interaction (typing, holding an object), hands close together |

The first two are limits of the current training data/model itself and are
not expected to be fixed by more pipeline engineering. The third is a
property of whatever upstream box source you use, not of this checkpoint —
but it dominates real end-to-end error more than the first two combined in
the evaluation behind the 0.722 number above, so don't skip investing in a
good box source.

Other things to know:
- Trained exclusively on a specific anime rendering style (fabricatedXL,
  1024×1280 compositions) and not benchmarked outside that distribution —
  no claim is made about how it performs on other anime/illustration
  styles, and it is likely to degrade further on styles further from that
  distribution (chibi, western cartoon, photo).
- Validation set is small (32 images) and drawn from the same generation
  pipeline as training data, not an independent held-out distribution —
  treat both IoU numbers above as in-distribution estimates, not a
  general-purpose benchmark.
- Two known-bad training images (fully collapsed into the mirroring pattern
  above) were identified and excluded from both train and validation sets
  rather than "fixed" — the pattern itself remains present in the model's
  behavior on similar new inputs, exclusion only kept unrecoverable
  examples out of the training signal.

## License

Apache 2.0. Attribution appreciated: *HandSegNet by Ov3rLoRd / Jérémy
Gourlain*.

## Support this project

If HandSegNet is useful to you, consider supporting further development:

- Ko-fi: `<placeholder — link to be added>`
- GitHub Sponsors: `<placeholder — link to be added>`

## Acknowledgements

Built on [Segment Anything](https://github.com/facebookresearch/segment-anything)
(Meta AI, Apache 2.0). Part of the [Ov3rLoRd](https://github.com/Ov3rLoRd-MLEngineer)
pipeline. Sibling model: [FootSegNet](https://huggingface.co/Ov3rLoRd-MLEngineer/footsegnet).

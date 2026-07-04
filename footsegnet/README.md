# FootSegNet — segmentation sémantique pieds/chaussures (Ov3rLoRd Pipeline)

Fine-tuning de **SAM ViT-B** (`sam_vit_b_01ec64.pth`) sur un dataset custom de
200-500 images anime (fabricatedXL, 1024x1536) pour produire des masques
pieds/chaussures pixel-perfect, en remplacement du `SAMPreprocessor` générique
utilisé par `agents/sam_mask_generator.py`.

Tout s'exécute avec **py -3.12** depuis `D:\OVERLORD\footsegnet\`.

## Flux complet

```
1. GÉNÉRATION      py -3.12 generate_dataset.py --count 300
                   → dataset\raw\*.png  (1024x1536, fabricatedXL_v70, full body)

2. ANNOTATION      py -3.12 annotate.py
                   → pré-remplissage SAM (clics) + correction au stylet/souris
                   → dataset\masks_raw\<stem>.png  (BLANC=pied/chaussure, NOIR=fond)

3. BUILD COCO      py -3.12 build_coco.py --val-ratio 0.1
                   → split train/val + annotations\instances_{train,val}.json

4. ENTRAÎNEMENT    py -3.12 train_sam.py --epochs 30 --batch-size 2
                   → checkpoints\footsegnet_vit_b_best.pth

5. INFÉRENCE       from footsegnet.infer import generate_foot_mask
                   → masque convention pipeline (NOIR=régénérer, BLANC=préserver)
                   → branchement direct dans agents\inpaint_corrector.py
```

## Structure des dossiers

```
D:\OVERLORD\footsegnet\
├── README.md
├── generate_dataset.py        # génération batch via API ComfyUI
├── prompts_wildcards.txt      # templates de prompts avec tokens __wildcard__
├── wildcards\                 # listes résolues aléatoirement dans les templates
│   ├── shoes.txt
│   ├── backgrounds.txt
│   ├── poses.txt
│   └── outfits.txt
├── annotate.py                # interface d'annotation (SAM prefill + brush)
├── build_coco.py              # masques PNG → COCO JSON (RLE) + split train/val
├── train_sam.py               # fine-tuning SAM ViT-B (RTX 5080 16GB)
├── infer.py                   # inférence + intégration pipeline inpaint
├── dataset\
│   ├── raw\                   # images générées, avant annotation
│   │   └── manifest.json      # traçabilité prompt/seed par image
│   ├── masks_raw\             # masques annotés (avant split)
│   ├── images\
│   │   ├── train\
│   │   └── val\
│   ├── masks\
│   │   ├── train\
│   │   └── val\
│   └── annotations\
│       ├── instances_train.json   # COCO, catégorie unique "foot_shoe" (id=1)
│       └── instances_val.json
└── checkpoints\
    ├── footsegnet_vit_b_best.pth  # meilleur IoU validation
    └── footsegnet_vit_b_last.pth
```

## Conventions de masques (IMPORTANT)

Deux conventions coexistent — ne pas les mélanger :

| Contexte                          | Objet (pied/chaussure) | Fond   |
|-----------------------------------|------------------------|--------|
| Dataset / entraînement (standard ML) | BLANC (255)         | NOIR (0) |
| Pipeline inpaint ComfyUI (ADR interne) | NOIR (0) = régénérer | BLANC (255) = préserver |

`annotate.py`, `build_coco.py` et `train_sam.py` travaillent en convention ML.
`infer.py` sort **par défaut** en convention pipeline (NOIR=régénérer) pour être
un drop-in replacement de `generate_sam_mask()` ; passer `pipeline_convention=False`
pour obtenir le masque ML brut.

## Dépendances

Génération/annotation : `requests`, `Pillow`, `numpy` (déjà dans requirements.txt).
Annotation (prefill SAM) + entraînement + inférence :

```
py -3.12 -m pip install torch torchvision --index-url https://download.pytorch.org/whl/cu128
py -3.12 -m pip install git+https://github.com/facebookresearch/segment-anything.git
```

`annotate.py` fonctionne en mode brush pur si torch/segment-anything manquent.

## Intégration pipeline

Dans `agents/inpaint_corrector.py`, remplacer :

```python
from sam_mask_generator import generate_sam_mask
```

par :

```python
import sys; sys.path.insert(0, r"D:\OVERLORD\footsegnet")
from infer import generate_foot_mask as generate_sam_mask
```

Signature compatible : `generate_sam_mask(frame_path, zone, output_path, threshold, verbose)`.

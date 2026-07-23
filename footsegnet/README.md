# FootSegNet — segmentation sémantique pieds/chaussures (Ov3rLoRd Pipeline)

**Statut : v1 terminé.** Fine-tuning de **SAM ViT-B** (`sam_vit_b_01ec64.pth`)
sur 300 images anime annotées à la main (fabricatedXL, 1024x1536) pour produire
des masques pieds/chaussures pixel-perfect, en remplacement du
`SAMPreprocessor` générique utilisé par `agents/sam_mask_generator.py`.
Checkpoint entraîné disponible (`checkpoints/footsegnet_vit_b_best.pth`,
**val_IoU = 0.9277**), branché en production dans
`agents/inpaint_corrector.py` (repli automatique sur le SAM générique si le
checkpoint est absent). Préparation en cours pour publication HuggingFace —
voir `huggingface/` (model card, checkpoint `.safetensors`, script
d'inférence standalone sans dépendance au reste du pipeline).

Tout s'exécute avec **py -3.12** depuis `D:\OVERLORD\footsegnet\`.

## Flux complet

```
1. GÉNÉRATION      py -3.12 generate_dataset.py --count 300
                   → dataset\raw\*.png  (1024x1536, fabricatedXL_v70, full body)
                   [FAIT — 300 images]

2. ANNOTATION      py -3.12 annotate.py
                   → pré-remplissage SAM (clics) + correction au stylet/souris
                   → dataset\masks_raw\<stem>.png  (BLANC=pied/chaussure, NOIR=fond)
                   [FAIT — 300/300 masques annotés]

3. BUILD COCO      py -3.12 build_coco.py --val-ratio 0.1
                   → split train/val + annotations\instances_{train,val}.json
                   [FAIT — 270 images train (1620 avec flip+rotation ±15°), 30 val]

4. ENTRAÎNEMENT    py -3.12 train_sam.py --epochs 30 --batch-size 2
                   → checkpoints\footsegnet_vit_b_best.pth
                   [FAIT — val_IoU=0.9277, mask_decoder seul entraîné (~4M/93.7M params)]

5. INFÉRENCE       from footsegnet.infer import generate_foot_mask
                   → masque convention pipeline (NOIR=régénérer, BLANC=préserver)
                   → branchement direct dans agents\inpaint_corrector.py
                   [FAIT — branché en production, repli SAM générique si checkpoint absent]
```

**Limitation connue (honnête) :** le modèle segmente correctement une fois
qu'on lui fournit une boîte englobante pied/chaussure (dérivée des keypoints
de cheville DWPose) ; sans cette boîte (image entière en prompt), SAM segmente
le sujet entier au lieu des seuls pieds — ce n'est pas un détecteur plein
cadre. L'étape en amont (dérivation de la boîte depuis DWPose) échoue ou
produit une boîte significativement décalée dans environ **20-40% des cas**
selon la pose (kimono ample, robe qui flotte, contre-plongée, bras levé,
jambes rapprochées) — voir `huggingface/README.md` section Limitations pour
le détail. Ce taux d'échec concerne l'estimation de pose en amont, pas la
qualité de segmentation de FootSegNet une fois la boîte correcte fournie.

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
├── checkpoints\
│   ├── footsegnet_vit_b_best.pth  # meilleur IoU validation
│   └── footsegnet_vit_b_last.pth
└── huggingface\                # matériel de publication HuggingFace (non poussé sur GitHub tel quel)
    ├── README.md                   # model card (licence, résultats, limitations, usage)
    ├── standalone_infer.py         # inférence minimale, zéro dépendance au reste du pipeline
    └── convert_to_safetensors.py   # conversion .pth → .safetensors (sans perte, vérifiée)
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

## Publication HuggingFace

Modèle publiable sur HuggingFace (pas Civitai — plateforme pensée pour les
checkpoints Stable Diffusion, pas pour un utilitaire de segmentation).
Matériel de publication préparé dans `huggingface/` : model card, checkpoint
converti en `.safetensors`, script d'inférence standalone. Licence Apache 2.0
+ attribution *FootSegNet by Onibaku Gumi / Jérémy Gourlain*. À relire avant
mise en ligne effective (rien n'est publié automatiquement).

## Support ce projet

Si ce projet t'est utile, tu peux soutenir son développement :

- Ko-fi : `<placeholder — lien à ajouter>`
- GitHub Sponsors : `<placeholder — lien à ajouter>`

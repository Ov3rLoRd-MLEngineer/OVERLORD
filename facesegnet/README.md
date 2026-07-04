# FaceSegNet — segmentation visage (Ov3rLoRd Pipeline)

Déclinaison de FootSegNet (voir `D:\OVERLORD\footsegnet\README.md`) :
fine-tuning **SAM ViT-B** pour la segmentation des traits du visage anime.
**Multi-classes** :

| id | catégorie | couleur annotation |
|----|-----------|--------------------|
| 1  | eyes      | bleu               |
| 2  | mouth     | rouge              |
| 3  | nose      | vert               |
| 4  | eyebrows  | orange             |
| 5  | hairline  | violet             |

Format images : 1024x1024 (portrait rapproché — les traits doivent être grands).

## Flux

```
py -3.12 generate_dataset.py --count 300     → dataset\raw\*.png
py -3.12 annotate.py                         → dataset\masks_raw\<stem>__<cat>.png
py -3.12 build_coco.py --val-ratio 0.1       → annotations\instances_{train,val}.json
py -3.12 train.py --epochs 30                → checkpoints\facesegnet_vit_b_best.pth
from infer import generate_part_mask         → masque convention pipeline
```

Touches **1-5** dans `annotate.py` pour la catégorie active. Un masque PNG par
catégorie (`<stem>__<catégorie>.png`, BLANC=objet). Entraînement agnostique à
la classe (prompt = bbox) ; à l'inférence, la boîte fournie cible le trait
voulu (ex. zone visage depuis les keypoints OpenPose face).
`generate_sam_mask` fourni en alias pour `agents\inpaint_corrector.py`.

Structure, conventions et dépendances : identiques à FootSegNet.

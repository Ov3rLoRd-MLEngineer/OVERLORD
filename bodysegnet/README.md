# BodySegNet — segmentation corps/vêtements (Ov3rLoRd Pipeline)

Déclinaison de FootSegNet (voir `D:\OVERLORD\footsegnet\README.md`) :
fine-tuning **SAM ViT-B** pour la segmentation du corps et des vêtements anime.
**Multi-classes** :

| id | catégorie | couleur annotation |
|----|-----------|--------------------|
| 1  | torso     | rouge              |
| 2  | arms      | cyan               |
| 3  | legs      | vert               |
| 4  | clothes   | jaune              |

Format images : 1024x1536 (full body, comme FootSegNet).

## Flux

```
py -3.12 generate_dataset.py --count 300     → dataset\raw\*.png
py -3.12 annotate.py                         → dataset\masks_raw\<stem>__<cat>.png
py -3.12 build_coco.py --val-ratio 0.1       → annotations\instances_{train,val}.json
py -3.12 train.py --epochs 30                → checkpoints\bodysegnet_vit_b_best.pth
from infer import generate_part_mask         → masque convention pipeline
```

Touches **1-4** dans `annotate.py` pour la catégorie active. Un masque PNG par
catégorie (`<stem>__<catégorie>.png`, BLANC=objet). Note : `clothes` recouvre
généralement `torso`/`arms`/`legs` — les masques peuvent se chevaucher, c'est
attendu (une annotation COCO par catégorie, entraînées indépendamment).

Entraînement agnostique à la classe (prompt = bbox depuis keypoints OpenPose).
`generate_sam_mask` fourni en alias pour `agents\inpaint_corrector.py`.

Structure, conventions et dépendances : identiques à FootSegNet.

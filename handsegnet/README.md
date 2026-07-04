# HandSegNet — segmentation mains/doigts/poignets (Ov3rLoRd Pipeline)

Déclinaison de FootSegNet (voir `D:\OVERLORD\footsegnet\README.md` pour le
principe général) : fine-tuning **SAM ViT-B** sur dataset custom anime pour la
segmentation des mains. **Multi-classes** :

| id | catégorie | couleur annotation |
|----|-----------|--------------------|
| 1  | hand      | rouge              |
| 2  | fingers   | cyan               |
| 3  | wrist     | jaune              |

Format images : 1024x1280 (cadrage buste, mains proéminentes).

## Flux

```
py -3.12 generate_dataset.py --count 300     → dataset\raw\*.png
py -3.12 annotate.py                         → dataset\masks_raw\<stem>__<cat>.png
py -3.12 build_coco.py --val-ratio 0.1       → annotations\instances_{train,val}.json
py -3.12 train.py --epochs 30                → checkpoints\handsegnet_vit_b_best.pth
from infer import generate_part_mask         → masque convention pipeline
```

Un masque PNG **par catégorie** (BLANC=objet, NOIR=fond), nommé
`<stem>__<catégorie>.png`. Dans `annotate.py`, touches **1/2/3** pour choisir la
catégorie active ; le pré-remplissage SAM et le brush s'appliquent à celle-ci.

L'entraînement est agnostique à la classe (prompt = bbox de chaque annotation) ;
à l'inférence, c'est la boîte fournie (depuis les keypoints OpenPose) qui cible
la partie voulue. `generate_sam_mask` est fourni en alias pour compatibilité
avec `agents\inpaint_corrector.py`.

Structure des dossiers, conventions de masques et dépendances : identiques à
FootSegNet (`D:\OVERLORD\footsegnet\README.md`).

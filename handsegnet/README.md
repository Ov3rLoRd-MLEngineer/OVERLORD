# HandSegNet — segmentation mains (Ov3rLoRd Pipeline)

Déclinaison de FootSegNet (voir `D:\OVERLORD\footsegnet\README.md` pour le
principe général) : fine-tuning **SAM ViT-B** sur dataset custom anime pour la
segmentation des mains. **Mono-classe pour l'instant** (pas de distinction
poignet/main/doigts) :

| id | catégorie |
|----|-----------|
| 1  | hand      |

Format images : 1024x1280 (cadrage buste, mains proéminentes).

## Flux

```
py -3.12 generate_dataset.py --count 300     → dataset\raw\*.png
py -3.12 annotate.py                         → dataset\masks_raw\<stem>.png
py -3.12 build_coco.py --val-ratio 0.1       → annotations\instances_{train,val}.json
py -3.12 train.py --epochs 30                → checkpoints\handsegnet_vit_b_best.pth
from infer import generate_part_mask         → masque convention pipeline
```

Un seul masque PNG par image (BLANC=main, NOIR=fond), nommé `<stem>.png`.

L'entraînement est agnostique à la classe (prompt = bbox de chaque annotation) ;
à l'inférence, c'est la boîte fournie (depuis les keypoints OpenPose) qui cible
la partie voulue. `generate_sam_mask` est fourni en alias pour compatibilité
avec `agents\inpaint_corrector.py`. Une future extension multi-classes
(fingers/wrist) réintroduirait un masque par catégorie, comme avant ce
changement.

Structure des dossiers, conventions de masques et dépendances : identiques à
FootSegNet (`D:\OVERLORD\footsegnet\README.md`).

# HandSegNet — validation d'intégrité dataset + scaffold d'entraînement (2026-07-29)

Suite à la validation d'intégrité du dataset annoté et à l'inspection du scaffold
d'entraînement. **Mise à jour (même journée) : le dataset a été entièrement reconstruit**
— le manifeste précédent (540/10) datait d'une préparation v0 antérieure à la fin de
l'annotation manuelle (322/322 masques désormais disponibles dans `masks_raw/`). Voir
§1bis pour le détail du rebuild. Aucun entraînement réel n'a été lancé dans cette
session (GPU 5080 occupé par un autre job — Control-LoRA FootSegNet, ~100% util
continu). Ce rapport documente l'état constaté et ce qui reste à faire avant un
premier run.

## 1. Dataset — intégrité confirmée propre (état v0, 540/10 — historique)

Vérifications automatisées effectuées (script ad hoc, non committé) sur le manifeste
v0 (avant rebuild, section conservée pour historique — voir §1bis pour l'état actuel) :

- **Correspondance COCO ↔ disque** : 540 images train + 10 images val, chacune avec
  exactement 1 annotation, 0 image référencée manquante sur disque, 0 fichier orphelin
  sur disque non référencé dans `instances_{train,val}.json`.
- **Intégrité fichiers** : 550/550 images et masques ouvrables sans erreur
  (`Image.verify()` + `.load()`), 0 masque vide (`max()==0`), 0 mismatch de dimensions
  image/masque.
- **Cohérence bbox** : 0 bbox invalide (négative, hors-cadre, largeur/hauteur ≤ 0)
  sur les 550 annotations.
- **Cohérence RLE** : décodage `decode_rle()` (utilisé par `train.py`) comparé au PNG
  brut sur 5 échantillons aléatoires → IoU = 1.0 dans tous les cas (l'encodage COCO
  reflète exactement le masque annoté, pas de perte/désync introduite par
  `build_coco.py`).

**Verdict (v0) : dataset propre, mais construit sur un sous-ensemble incomplet de
l'annotation — voir §1bis pour le rebuild sur l'état complet.**

## 1bis. Rebuild complet sur les 322 masques annotés (2026-07-29)

Confirmé : `masks_raw/` contient désormais **322 masques** (vs 100 utilisés par le
manifeste v0 — l'annotation manuelle a continué après le premier build). Script
responsable du manifeste identifié : **`handsegnet/build_coco.py`** (pas de
`build_dataset.py` distinct — même rôle que `footsegnet/build_coco.py`, architecture
identique).

Rebuild relancé avec les paramètres par défaut (`py -3.12 build_coco.py`, pas
d'argument — `--val-ratio 0.1` / `--split-seed 1337`, identiques aux défauts déjà en
place) :

```
[build_coco] 322 paires — train=290 val=32
[build_coco] train : 290 flips horizontaux ajoutés
[build_coco] train : 1160 rotations ±15° ajoutées
[build_coco] instances_train.json : 1740 images, 1740 annotations
[build_coco] instances_val.json   : 32 images, 32 annotations
```

**Nouveau total réel : 1740 train + 32 val = 1772 images (322 uniques × ~5.5 en
moyenne — 290 en train ×6 variantes, 32 en val non augmentées).** Ratio val = 32/322 ≈
9.9%, cohérent avec le défaut `--val-ratio 0.1` — **même convention que FootSegNet**
(même formule `max(1, int(len*ratio))`, même défaut 0.1).

Re-validation post-rebuild (même méthodologie qu'en §1) : 1772/1772 fichiers
images+masques intègres, 0 masque vide, 0 mismatch dimension, 0 bbox invalide, 0
fichier manquant. **122 fichiers orphelins détectés** (61 images + 61 masques
correspondant à 16 images de base — 9 basculées train→val, 7 val→train par le nouveau
split aléatoire) et **supprimés** : c'étaient des résidus du build v0 laissés dans le
mauvais dossier de split, sans impact sur le manifeste JSON lui-même mais qui auraient
pollué un futur audit d'intégrité. Après nettoyage : 0 orphelin, 0 anomalie.

### handsegnet_00137 — la prémisse "masque vide" ne se vérifie pas

Vérification demandée sur `handsegnet_00137` : **son masque n'est pas vide**. Inspection
visuelle directe (image source + masque) : il s'agit de deux mains jointes (pose
"prière"/cœur, gantées), correctement segmentées — masque ~40% de couverture, forme
cohérente avec la photo. `_provenance.csv` indique un score SAM initial bas
(`sam_score=0.304`, `qwenvl_grounding_multi(2)`, `iou_manual` vide donc jamais
re-vérifié manuellement), ce qui explique probablement pourquoi cette image avait été
signalée comme suspecte — mais le masque final dans `masks_raw/` n'est ni vide ni
manifestement dégénéré. `build_coco.py` ne l'a donc **pas filtré** (aucun message
"masque vide, ignoré" dans la sortie), et l'image apparaît normalement dans
`instances_train.json` avec ses 6 variantes augmentées.
**Recommandation : ne pas l'exclure automatiquement** sur la base de cette
vérification — si une exclusion est toujours souhaitée, ce serait un choix éditorial
(faible confiance SAM d'origine) plutôt qu'une correction de bug, et nécessiterait une
review manuelle via `annotate.py --by-confidence` plutôt qu'un filtre automatique.
Scan complet de `masks_raw/` (322 fichiers) : **0 masque réellement vide** (0 pixel
non-nul), 50 masques à faible couverture (<2%, plausible pour des mains partiellement
hors-cadre) — aucun cas de masque à 0%.

### Point d'attention — diversité réelle (mise à jour)

Le nouveau manifeste est basé sur **322 images annotées uniques** (290 train + 32 val,
0 chevauchement de stem vérifié), contre 100 avant rebuild — l'écart avec FootSegNet
(~270 images uniques, référence prod val_IoU 0.9277) est donc désormais favorable à
HandSegNet plutôt que défavorable. `dataset/diversity_stats/summary.txt` (95.1%
frontal / 4.5% profil / 0.4% low-angle, sur un lot de 224 images) reste antérieur au
set final à 322 images et n'a pas été régénéré dans cette session — à relancer
(`agents/dataset_diversity_stats.py`) si un diagnostic de biais d'angle est nécessaire
après un premier run.

## 2. Scaffold d'entraînement — prêt, structurellement identique à FootSegNet

`handsegnet/train.py` (284 lignes) est un portage direct de `footsegnet/train_sam.py` :
même stratégie (encodeur + prompt_encoder gelés en bf16/no_grad, seul le
`mask_decoder` ~4M params entraîné, prompt = bbox GT + jitter ±12px, loss BCE+Dice en
256×256 sur la région valide hors padding). Les deux bugs connus déjà corrigés dans
cette version (voir mémoire `segnet-projects-status`) :
1. `downsample_targets` — plus de `.unsqueeze` en trop sur `valid`.
2. `mask_decoder.predict_masks()` (package `segment_anything` installé, pas vendored)
   — boucle par échantillon déjà en place pour éviter le mismatch BxB vs B avec
   `--batch-size > 1`.

Aucune modification de code n'est nécessaire pour lancer un run.

## 3. Hyperparamètres — copier tel quel, pas d'ajustement nécessaire au premier run

`handsegnet/train.py` a **déjà les mêmes défauts en dur que FootSegNet** :

| Paramètre | Défaut handsegnet/train.py | FootSegNet (référence prod, val_IoU 0.9277) |
|---|---|---|
| `--epochs` | 30 | 30 |
| `--batch-size` | 2 | 2 |
| `--lr` | 1e-4 | 1e-4 |
| `--weight-decay` | 1e-4 | 1e-4 |
| scheduler | CosineAnnealingLR (T_max=epochs) | idem |
| seed | 1337 | idem |
| prompt | bbox GT + jitter ±12px | idem |

Recommandation : **lancer avec les défauts tels quels pour ce premier run** — rien à
copier manuellement, `py -3.12 train.py` suffit. Le dataset HandSegNet (322 images
uniques) étant désormais du même ordre de grandeur que FootSegNet (~270), il n'y a
plus de raison particulière d'anticiper un ajustement anti-surapprentissage avant
d'avoir vu une première courbe val_IoU complète.

## 4. Point d'alerte — un checkpoint existe déjà mais son origine est ambiguë

`handsegnet/checkpoints/handsegnet_vit_b_best.pth` et `..._last.pth` existent
(375 Mo chacun, gitignorés donc générés en local, pas committés) :

- `best` modifié 2026-07-23 23:05:29
- `last` modifié 2026-07-23 23:18:51 (13 min après `best`)

Aucun log n'a été retrouvé pour ce run (recherché dans `workspace/logs/`,
`workspace/logs/training/` — vide — et par nom de fichier dans tout le dépôt). Les
deux fichiers sont des `state_dict` bruts (`torch.save(sam.state_dict(), ...)`, 314
clés = modèle SAM complet) : **aucune métadonnée d'epoch/loss/IoU n'est stockée dans
le fichier lui-même**, impossible de reconstituer a posteriori ce qui a été entraîné.

13 minutes entre `best` et `last` est court pour un run complet de 30 epochs sur 540
échantillons — plausible qu'il s'agisse d'un test de fumée (vérifier que la boucle
tourne sans crasher) plutôt qu'un entraînement réel mené à terme. **Aucune preuve
disponible dans un sens ou dans l'autre.**

Recommandation : au premier run réel, **ne pas passer `--resume`** (partir de
`sam_vit_b_01ec64.pth` comme FootSegNet), et rediriger la sortie vers un fichier log
(`> workspace\logs\training\handsegnet_<timestamp>.log 2>&1`, comme le fait
`schedule_training.bat`) pour ne plus perdre la trace epoch/loss/IoU d'un run.

## 5. État GPU actuel et sélection de device

- **RTX 5080 (index 0)** : occupé en continu (~100% util pendant toute cette session)
  par un job Control-LoRA FootSegNet (fichiers modifiés non commités
  `footsegnet/controlnet/quality_sort.py` et `train_control_lora.py`). **Ne pas
  toucher.**
- **RTX 5060 Ti (index 1)** : libre, 0 MiB, 0% util.

`handsegnet/train.py` a désormais un argument **`--device`** (défaut : auto-détection,
`cuda`/`cuda:0` si disponible sinon `cpu`) permettant de forcer explicitement
`cuda:0` / `cuda:1` / `cpu`, à la même convention que `footsegnet/huggingface/standalone_infer.py`
(`--device`, résolution `args.device or ("cuda" if torch.cuda.is_available() else "cpu")`).

Testé dans cette session : `py -3.12 train.py --device cuda:1 --epochs 0` (0 epoch —
charge le modèle SAM sur `cuda:1` et construit les datasets sans exécuter de step de
training réel) → `[handsegnet] Device : cuda:1` confirmé, chargement réussi,
`train=1740 val=32` cohérent avec le nouveau manifeste, checkpoints existants non
modifiés (timestamps inchangés), GPU 5080 non sollicité pendant le test (vérifié
avant/après via `nvidia-smi`).

## 6. Checklist — prêt à lancer dès que la 5080 se libère

- [x] Dataset reconstruit sur l'état complet de l'annotation (1740 train / 32 val,
      322 images uniques, 0 anomalie, orphelins v0 nettoyés)
- [x] `build_coco.py` réexécuté avec succès, COCO valide et re-vérifié (RLE, bbox,
      dimensions, correspondance disque)
- [x] `handsegnet_00137` vérifié individuellement — pas vide, inclus normalement (voir
      §1bis pour le détail et la recommandation)
- [x] `train.py` scaffold fonctionnel, bugs connus déjà corrigés
- [x] Hyperparamètres de départ identiques à la référence prod FootSegNet — aucun
      ajustement à faire avant le premier run
- [x] `--device` ajouté et testé sur `cuda:1` (5060 Ti) sans toucher la 5080
- [ ] Confirmer que la 5080 est libre (`nvidia-smi`) **ou** lancer directement sur la
      5060 Ti via `--device cuda:1` en attendant (compatible dès maintenant)
- [ ] Décider si on garde ou écrase les checkpoints du 23/07 (origine ambiguë — voir
      §4, dataset entre-temps changé donc un `--resume` dessus n'aurait de toute façon
      plus vraiment de sens) : recommandation = repartir de zéro, ne pas `--resume`
- [ ] Rediriger la sortie vers un fichier log horodaté (au lieu de laisser filer dans
      la console) pour ne pas reproduire l'absence de trace du run précédent

### Commande à lancer

```
cd D:\OVERLORD\handsegnet
py -3.12 train.py --device cuda:0 > ..\workspace\logs\training\handsegnet_%TS%.log 2>&1
```

(remplacer `cuda:0` par `cuda:1` pour lancer dès maintenant sur la 5060 Ti sans
attendre la libération de la 5080 ; ou `schedule_training.bat` depuis la racine si les
4 SegNets doivent tourner en séquence — celui-ci enchaîne aussi
footsegnet/facesegnet/bodysegnet et ne passe pas encore `--device`, à ne lancer que
si c'est bien l'intention).

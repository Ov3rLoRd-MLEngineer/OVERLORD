# R&D — HandSegNet Stage 3 (post-démo)

*Document de planification, pas de commit de code. Rédigé 2026-08-07, à relire
avant de lancer le moindre travail — rien ici n'est engagé.*

## Pourquoi ce document

HandSegNet v1 est en production (`val_IoU` = 0.8876 en boîte vérité-terrain,
0.722 mean / 0.773 median en boîte automatique réelle — voir
`handsegnet/huggingface/README.md` section Results). Trois défauts récurrents
sont déjà identifiés et documentés (même README, section Limitations) :

| Pattern | Symptôme | Cause probable |
|---|---|---|
| Mirroring collapse | Deux mains jointes fusionnent en un blob décoratif symétrique, aucun doigt individualisé | Le décodeur de masque n'a pas de contrainte structurelle main = 5 doigts articulés, il apprend une texture plausible plutôt qu'une anatomie |
| Finger dropout | Un ou plusieurs doigts manquants/tronqués alors que la boîte est correcte | Décodage de masque pixel-à-pixel sans modélisation explicite des articulations, les doigts fins sont sous-représentés dans le signal de perte |
| Box misses a hand | La boîte amont (VLM grounding faute de détecteur de pose main dédié) rate une main ou la place sur poignet/manche | Problème de détection amont, pas de segmentation — hors du scope architectural ci-dessous, mais aggravé par l'absence de tout signal squelette pour corriger une boîte légèrement décalée |

Les pistes ci-dessous visent spécifiquement les deux premiers patterns
(architecture/loss de segmentation) et, dans une moindre mesure, le troisième
(un signal squelette pourrait servir de garde-fou de plausibilité même sur une
boîte imparfaite). Aucune piste n'a été prototypée — c'est un plan de lecture
et d'évaluation, pas un chantier commencé.

## Piste 1 — Module JGR (Joint Graph Reasoning / graph convolution inter-articulations)

**Idée générale.** Représenter les 21 points-clés d'une main (ou les
articulations impliquées dans la segmentation) comme un graphe (nœuds =
articulations, arêtes = os) et faire passer un module de graph convolution
sur ce graphe pour propager de l'information structurelle entre
articulations voisines, avant/pendant le décodage. Contrairement à un
décodeur convolutif pixel-à-pixel classique, le module force implicitement
une cohérence "main articulée" plutôt qu'une simple texture plausible — piste
directement pertinente pour le pattern **mirroring collapse**, où le modèle
actuel produit une forme globalement main-shaped sans respecter la topologie
réelle des doigts.

**Où ça s'intègre dans HandSegNet.** Actuellement seul le mask decoder de SAM
ViT-B est fine-tuné (image encoder + prompt encoder gelés). Un module JGR
nécessiterait soit (a) une tête auxiliaire de régression de keypoints
entraînée en parallèle du masque (multi-tâche, keypoints + masque partagent
le graphe), soit (b) conditionner le décodeur de masque sur un graphe
d'articulations préalablement estimé par un modèle de pose main externe (ex.
MediaPipe Hands ou un détecteur dédié) — option (b) plus simple à intégrer
sans toucher à l'architecture SAM elle-même, mais dépend de la qualité de ce
détecteur externe sur du rendu anime (à valider, cf. `LIMITATIONS_CONNUES.md`
pour le précédent des artefacts de symétrie bilatérale déjà documentés comme
limite générative, pas de segmentation).

**Effort estimé.** Élevé si option (a) — nouvelle tête, nouvelle loss
multi-tâche, ré-annotation partielle du dataset avec des keypoints (les 322
masques actuels n'ont que des masques, pas de keypoints main). Moyen si
option (b) — dépend surtout de la disponibilité d'un détecteur de pose main
fiable sur du contenu anime.

## Piste 2 — CFAM (Channel/Feature Attention Module)

**Idée générale.** Module d'attention par canal appliqué aux feature maps
avant décodage, pour repondérer dynamiquement l'importance de chaque canal
selon le contenu de l'image plutôt qu'un poids fixe appris globalement.
Généralement peu coûteux (quelques couches denses/pooling additionnelles),
s'insère facilement en amont d'un décodeur existant sans changer sa sortie.

**Pertinence pour HandSegNet.** Piste la plus légère des quatre — candidate
naturelle pour une première itération Stage 3 à faible risque, sur le pattern
**finger dropout** : si certains canaux du décodeur portent davantage
d'information sur les structures fines (doigts) que d'autres (paume, fond),
une repondération dynamique pourrait limiter leur dilution par les canaux
dominants (masse de la paume). Hypothèse à vérifier empiriquement, pas
garantie — le gain de CFAM dans la littérature générale est documenté sur des
tâches de classification/détection, moins directement sur la préservation de
structures fines en segmentation binaire.

**Effort estimé.** Faible-moyen — ajout d'un bloc d'attention dans le mask
decoder existant, ré-entraînement sur le dataset actuel (pas besoin de
nouvelles annotations). Bon candidat pour un test rapide avant d'investir
dans les pistes plus lourdes (1, 3, 4).

## Piste 3 — Distribution-aware coordinate decoding

**Idée générale.** Technique de correction d'erreur de quantification post-
hoc (typiquement utilisée en pose estimation, ex. DARK) : au lieu de prendre
la coordonnée du maximum brut d'une heatmap, on modélise la distribution
locale autour du pic (souvent approximée gaussienne) pour extraire une
position sous-pixel plus précise, corrigeant le biais systématique introduit
par la résolution réduite de la heatmap.

**Pertinence pour HandSegNet.** S'applique nativement à une sortie de type
heatmap/keypoints, pas directement à une sortie de masque binaire comme
celle produite aujourd'hui par SAM. Cette piste n'a de sens **que si la
Piste 1 (ou une tête de keypoints quelconque) est adoptée en premier** — sans
sortie heatmap intermédiaire, il n'y a rien à décoder avec cette technique.
À traiter comme un raffinement de la Piste 1, pas une piste indépendante.

**Effort estimé.** Faible en soi (la technique de décodage est légère une
fois la heatmap disponible), mais entièrement dépendante de la Piste 1.

## Piste 4 — Skeletal constraint loss (longueur + orientation des os)

**Idée générale.** Terme de perte additionnel pénalisant les prédictions dont
la géométrie inter-articulations (distance entre deux keypoints connectés,
orientation relative) s'écarte de contraintes anatomiques plausibles
(longueurs d'os à peu près constantes pour une main donnée, angles
d'articulation dans une plage physiologique). Utilisé en pose estimation pour
éviter des squelettes prédits anatomiquement impossibles.

**Pertinence pour HandSegNet.** Directement complémentaire à la Piste 1 :
une fois qu'un signal squelette existe (graphe de keypoints), cette loss
pénaliserait explicitement les sorties qui ressemblent au pattern
**mirroring collapse** actuel (une "main" sans structure de doigts
individualisée violerait presque toutes les contraintes de longueur d'os).
Comme la Piste 3, dépend d'une représentation squelette préalable — même
prérequis que la Piste 1.

**Effort estimé.** Moyen une fois la Piste 1 en place (ajout d'un terme de
loss, pas de nouvelle architecture) ; nul en isolation puisque non applicable
sans squelette.

## Priorisation suggérée

1. **CFAM (Piste 2)** — seule piste indépendante des trois autres, faible
   coût, testable sur le dataset actuel sans nouvelle annotation. À tenter en
   premier pour calibrer si le gain justifie l'investissement dans le reste.
2. **JGR (Piste 1)** — piste structurante, prérequis des Pistes 3 et 4.
   Décision à prendre en fonction de la disponibilité d'un détecteur de pose
   main fiable sur du rendu anime (option b, plus rapide) avant d'envisager
   une tête entraînée from scratch (option a).
3. **Skeletal constraint loss (Piste 4)** puis **distribution-aware decoding
   (Piste 3)** — seulement si la Piste 1 est adoptée et produit un signal
   squelette exploitable.

## Piste dataset — frames du pipeline réel

Indépendamment des 4 pistes architecture/loss ci-dessus : augmenter le
dataset d'entraînement (322 images actuelles, fabricatedXL 1024×1280 statique)
avec des frames extraites du pipeline vidéo réel (SVI/AnimateDiff) —
mains en mouvement, occlusions partielles par un objet ou l'autre main,
angles de caméra non frontaux issus des clips générés plutôt que des poses
statiques de `generate_dataset.py`. Piste orthogonale aux 4 précédentes
(données vs architecture), combinable avec n'importe laquelle. Coût principal :
annotation manuelle de nouveaux masques (même flux `annotate.py` existant,
pas de nouvel outillage requis) — le goulot est le temps d'annotation, pas la
technique.

## FootSegNet — hors scope Stage 3

FootSegNet reste **volontairement exclu** de ce plan Stage 3. Ses défauts
observés (bords "fondus"/mous, léger sur-segmentation) sont plus bénins que
ceux de HandSegNet — une forme de pied a beaucoup moins de façons d'échouer
qu'une main articulée à 5 doigts — et son `val_IoU` (0.9277) est déjà
sensiblement au-dessus des deux chiffres HandSegNet. Le gain attendu de ces
quatre pistes sur FootSegNet est marginal par rapport à l'effort d'implémen-
tation ; à ne réenvisager que si un nouveau mode d'échec significatif de
FootSegNet apparaît (pas le cas à ce jour, cf. `handsegnet-yolo-primary-box`
et `qwenvl-grounding-fallback` en mémoire pour l'historique des correctifs
déjà appliqués côté détection de boîte, commun aux deux modèles).

## Références (venues citées par la demande initiale, non vérifiées ligne à ligne)

- JGR — graph convolution inter-articulations, *Sensors* 2024.
- CFAM — attention par canal, *MDPI Applied Sciences* 2020.
- Distribution-aware coordinate decoding (type DARK) — littérature pose
  estimation générale, pas une référence unique.
- Skeletal constraint loss — terme de perte anatomique, littérature pose
  estimation générale, pas une référence unique.

Aucune de ces références n'a été relue en détail pour ce document (nom de
venue repris tel que fourni) — à faire avant de lancer une implémentation,
pas avant de prioriser.

# Limitations connues

Ce fichier documente les limitations **connues et acceptées** du pipeline de
génération — des comportements du modèle/checkpoint qui ne sont pas des bugs
du pipeline (wildcards, workflow ComfyUI, post-traitement) mais des limites du
prior génératif actuel. Objectif : éviter de retraiter les mêmes cas en boucle
à chaque session en attendant une amélioration qui ne viendra pas d'un fix
côté pipeline.

À consulter avant de rouvrir une investigation sur une image "ratée" déjà
listée ici — si le cas correspond à une entrée existante, il est déjà
caractérisé et classé comme non actionnable pour l'instant.

## HandSegNet

### Mains jointes/qui se touchent dans une composition symétrique

Une composition à forte symétrie bilatérale où les deux mains se touchent ou
s'entremêlent (ex. `cupping hands together`) risque de **collapser en
mirroring** : le modèle hallucine un seul motif décoratif symétrique plutôt
que deux mains distinctes et anatomiquement cohérentes.

- **Cas observés** : `handsegnet_00137` (exclu du jeu d'entraînement),
  `handsegnet_00167` (**requalifié le 2026-07-29** — voir vérification
  ci-dessous : plus problématique que "partiel", candidat à l'exclusion),
  `handsegnet_00147` (mains jointes, pose menottée — masque val, IoU=0.45),
  `handsegnet_00071`, `handsegnet_00072` (mains gantées jointes tenant un
  objet — épée/fourreau — masque val, IoU=0.59 et 0.61 respectivement).
  Ces trois derniers cas viennent de l'évaluation qualitative du 2026-07-29
  (checkpoint `handsegnet_vit_b_best.pth` sur le set val, 32 images) — leur
  présence parmi les pires scores confirme que ce pattern est **récurrent**,
  pas limité aux deux cas déjà exclus du jeu d'entraînement.
- **Cause** : limite du prior génératif actuel sur les compositions à forte
  symétrie, pas un bug du pipeline (wildcards/workflow/prompt).
- **Statut** : pas de correctif satisfaisant identifié à ce jour. Amélioration
  probable avec les futures générations de modèles plutôt qu'un fix pipeline.
- **Consigne** : ne pas retraiter ces cas en boucle en attendant une solution.

#### Vérification `handsegnet_00167` (2026-07-29)

Relecture de l'image source (`handsegnet/dataset/raw/handsegnet_00167.png`) et de
son masque manuel (`handsegnet/dataset/masks/train/handsegnet_00167.png`,
identique à `masks_raw/`) après l'annotation de la nuit précédente
(provenance `circle_sam_multi_refine(2)`, sam_score 0.825, mask_pct 41.53 —
cf. `handsegnet/dataset/premasks/_provenance.csv`).

Constat : le masque traite la quasi-totalité de la zone des doigts comme une
seule masse indifférenciée — aucun doigt individuel n'est délimité en dehors
de deux petites pointes isolées en bas de l'image, et **aucun pouce n'est
distinguable sur l'une ou l'autre main**, alors que la pose (mains en coupe,
paumes vers le haut) devrait en montrer un de chaque côté. C'est cohérent
avec l'hypothèse de collapse en motif décoratif symétrique plutôt qu'un
simple contact/chevauchement de doigts.

**Verdict : le défaut n'est pas resté mineur — il s'avère plus problématique
qu'observé initialement.** Recommandation : traiter `handsegnet_00167` comme
`handsegnet_00137` (exclusion du jeu d'entraînement). L'exclusion effective
n'a **pas** été appliquée dans cette passe (hors périmètre — vérification
uniquement) ; à faire dans une session dédiée au dataset.

### Doigts écartés — décrochage partiel

Distinct du mirroring ci-dessus : ici les doigts sont **écartés, non en
contact** (ex. geste mains ouvertes type "jazz hands") — la boîte englobante
est correcte et il n'y a pas de fusion entre les deux mains, mais le modèle
échoue quand même à segmenter chaque doigt individuellement (décrochage
partiel — certains doigts manquent ou sont tronqués dans le masque prédit).
Mécanisme différent du mirroring : ce n'est pas un collapse en motif
symétrique déclenché par le contact entre mains, mais une difficulté propre
à la segmentation fine de doigts individuels bien séparés.

- **Cas observés** : `handsegnet_00259` (masque val, IoU=0.55 — évaluation
  qualitative du 2026-07-29, checkpoint `handsegnet_vit_b_best.pth`).
- **Cause** : limite du prior génératif actuel sur la segmentation de doigts
  individuels bien séparés, pas un bug du pipeline.
- **Statut** : un seul cas observé à ce jour — à surveiller, pas encore
  assez d'occurrences pour caractériser la fréquence ou envisager une
  exclusion.
- **Consigne** : ne pas confondre avec le mirroring ci-dessus lors du tri de
  futurs cas limites — vérifier si les doigts se touchent (mirroring) ou
  sont écartés (décrochage) avant de classer.

## HandSegNet — Limitations de pipeline (potentiellement corrigibles)

Contrairement aux sections ci-dessus (limites du **prior génératif**, non
actionables sans nouvelle génération de modèle), ce qui suit est un problème
de **pipeline d'inférence** — corrigible sans réentraîner le modèle. Séparé
volontairement du reste de ce fichier pour ne pas le classer par erreur
comme "non actionnable".

### Fragilité du grounding VLM sur les scènes multi-mains

Le pipeline d'inférence production (`batch_premask.py` / `infer.py`) dérive
la boîte englobante des mains via grounding VLM multi-instance
(`agents/vlm_grounding.py`, requête "the character's hands") — il n'existe
pas de détecteur de pose dédié aux mains dans ce dépôt (contrairement aux
pieds, dérivés de façon fiable via DWPose/chevilles). Sur une composition à
deux mains, ce grounding peut échouer à détecter une main, voire les deux.

- **Cas observés** (évaluation qualitative 2026-07-29, set val) :
  `handsegnet_00138` (échec total — la boîte se place sur le poignet/bracelet,
  rate les deux mains, IoU=0.08), `handsegnet_00095` (une seule main sur
  deux détectée par le grounding, la seconde absente du masque, IoU=0.42).
- **Impact mesuré** : IoU pipeline réel (boîte via grounding) = 0.722 moyenne
  / 0.773 médiane sur 32 images val, contre 0.888 en interne (`train.py`,
  boîte vérité-terrain + jitter) — l'écart provient très largement de ce
  goulot d'étranglement de détection, pas d'une baisse de qualité du
  mask_decoder lui-même.
- **Cause** : fiabilité insuffisante du grounding VLM générique sur des
  scènes à mains multiples/proches — PAS une limite du modèle HandSegNet
  entraîné.
- **Statut : ACTIONABLE.** Pistes non explorées dans cette session :
  ajuster le seuil de rejet de `grounding_boxes()`, tester une requête de
  grounding différente, utiliser un second modèle de grounding en repli, ou
  transposer à l'inférence la technique cercle-par-main déjà validée pour le
  pré-remplissage d'annotation (`handsegnet/annotate.py --pre-fill-vlm`,
  PR #24 — cf. aussi `prototype_circle_sam_multi.py`).
- **Consigne** : à traiter comme un chantier de pipeline normal (priorisable,
  testable, mesurable), pas comme une limitation acceptée à documenter et
  laisser de côté.

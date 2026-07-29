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
  ci-dessous : plus problématique que "partiel", candidat à l'exclusion).
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

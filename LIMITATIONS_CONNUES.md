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
  `handsegnet_00167` (partiel, sous surveillance — pas encore exclu, à
  requalifier si le motif se dégrade davantage sur de futures générations).
- **Cause** : limite du prior génératif actuel sur les compositions à forte
  symétrie, pas un bug du pipeline (wildcards/workflow/prompt).
- **Statut** : pas de correctif satisfaisant identifié à ce jour. Amélioration
  probable avec les futures générations de modèles plutôt qu'un fix pipeline.
- **Consigne** : ne pas retraiter ces cas en boucle en attendant une solution.

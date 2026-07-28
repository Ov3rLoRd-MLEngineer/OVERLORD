# Diagnostic Control-LoRA FootSegNet — mode collapse du conditionnement (2026-07-28)

## Contexte

Le run de départage (dataset complet, 549 paires, LR remonté, 6000 steps,
`output/control_lora_v1_convergence_test/`) a confirmé que la corrélation
croisée entre les composantes spatiales du résidu ControlNet reste ancrée
entre 0,994 et 0,9999 sur tout le parcours, sans bascule. L'hypothèse
"convergence tardive / manque de données" est écartée. Ce document
synthétise l'investigation architecturale (zero-init, loss, mécanisme de
conditionnement) qui en découle, en combinant :

- les scripts et logs de diagnostic produits sur `D:\OVERLORD\.claude\jobs\75074c9f\tmp\`
  (session du 2026-07-25 au 2026-07-28, non trackés par git — dossier de
  scratch d'exécution de tâches) ;
- deux vérifications complémentaires ciblées, dont les scripts réutilisables
  sont conservés dans `footsegnet/controlnet/diagnostics/`.

Contrainte GPU respectée : `nvidia-smi` vérifié avant toute action (GPU 0
libre, aucun process de calcul actif) ; aucun entraînement long relancé —
toutes les vérifications ci-dessous sont soit des relectures de checkpoints
existants (inférence seule), soit des tests déjà réalisés à quelques
centaines de steps maximum.

## Étape 0 — relecture du code

- **Zero-init** (`build_models`) : `ControlNetModel.from_unet(unet)` — comportement standard
  diffusers, `controlnet_down_blocks`/`controlnet_mid_block` initialisés à
  zéro par construction. `controlnet_cond_embedding` est initialisé
  aléatoirement (normal, ce n'est pas une zero-conv) et fait partie de
  `modules_to_save` pour être entraîné en entier — cf. commentaires
  d'en-tête de `train_control_lora.py`.
- **Loss** (`train()`, ligne ~474) : `mse_loss` (bruit prédit vs bruit
  réel) + `reg_weight * reg_loss` où `reg_loss` est la norme L2 moyenne des
  résidus ControlNet (`down_block_res_samples` + `mid_block_res_sample`).
  Ce `reg_loss` a été ajouté le 2026-07-25 (diagnostic antérieur) pour
  contenir une explosion de magnitude des `modules_to_save`, PAS pour
  encourager une quelconque fidélité du résidu au contenu du masque —
  aucun terme de la loss ne compare le résidu à l'image de conditionnement.
- **Conditionnement** : `controlnet_cond=cond_values` (normalisé [0,1],
  BLANC=pied/chaussure) injecté via l'appel `ControlNetModel.__call__`,
  puis les résidus retournés (`down_block_res_samples`,
  `mid_block_res_sample`) sont passés à l'UNet gelé via
  `down_block_additional_residuals`/`mid_block_additional_residual` — c'est
  exactement l'API et le flux utilisés par
  `diffusers/examples/controlnet/train_controlnet_sdxl.py` (référence
  officielle), aucun écart structurel constaté.

## Hypothèses testées

### 1. Zero-init mal implémenté — **ÉCARTÉE**

`diagnostics/probe_mode_collapse.py` (comparaison zero-init vs checkpoints
successifs, script `diag_residuals_compare.py` de la session précédente) et
la décomposition DC/spatiale (`dc_spatial_evolution_results.log`) montrent
une croissance progressive et monotone de l'énergie du résidu depuis un
niveau quasi nul :

| step | énergie DC (constante) | énergie spatiale (variation) |
|------|------------------------|-------------------------------|
| 50   | 96,3 %                 | 3,7 %                         |
| 150  | 91,1 %                 | 8,9 %                         |
| 300  | 84,9 %                 | 15,1 %                        |
| 600  | 81,1 %                 | 18,9 %                        |
| 1000 | 76,5 %                 | 23,5 %                        |

Pas de saut initial, pas de delta massif au tout début — le zero-init
fonctionne comme attendu. **Non retenue comme cause.**

### 2. Loss ne pénalise pas correctement l'écart de conditionnement — **CONFIRMÉE (cause principale)**

Preuve décisive : corrélation croisée (Pearson) des composantes spatiales
du résidu (`mid_block_res_sample`, DC retiré) entre 5 échantillons du
dataset complet (idx 0/100/200/300/400 de `manifest_filtered.jsonl`,
volontairement très espacés) comparée à la corrélation des **masques bruts
correspondants** :

| Comparaison                                         | Corrélation moyenne |
|------------------------------------------------------|----------------------|
| Masques de conditionnement **bruts** (5 échantillons) | **0,075** (quasi nulle, `diagnostics/check_conditioning_diversity.py`) |
| Résidu appris, checkpoint-150 (`reg_weight=0`, `lrsplit_test`) | 0,9999 |
| Résidu appris, checkpoint-150 (`reg_weight=0.01`, `reg_test`)  | 0,9999 |
| Résidu appris, checkpoint-1000 (`dcspatial_test`)     | 0,9999 |
| Résidu appris, run complet 549 paires — sonde à chaque 250 steps de 1250 à 6000 | 0,9946–0,9999 (jamais < 0,99, remonte vers 1 en fin de run — cf. `convergence_probe_log.txt`) |

Les masques d'entrée sont donc **réellement divers** (corrélation ~0,08,
parfois négative) — la couverture blanc va de 0,9 % à 8,4 % du cadre
(masques pied/chaussure très localisés). Le résidu appris, lui, reste
quasi identique (corrélation ~0,999+) **quel que soit le masque fourni, dès
150 steps, avec ou sans régularisation L2, et jusqu'au step 6000 sur le
dataset complet**. C'est un mode collapse confirmé, pas un artefact de
manque de diversité du dataset.

Test de départage supplémentaire (checkpoints déjà existants, réutilisés
sans relancer d'entraînement) : `lrsplit_test/checkpoint-150` a été
entraîné **avant** l'ajout du terme `reg_loss` au script (absent du code à
cette date, confirmé par l'absence du format de log `mse=.../reg=...` dans
`lrsplit_test.log` alors qu'il est présent dans `reg_test.log`) — donc sans
aucune régularisation de la magnitude du résidu. Sa corrélation
(0,9999) est **identique** à celle du checkpoint équivalent avec
`reg_weight=0.01` (`reg_test/checkpoint-150`, 0,9999). **La régularisation
L2 ajoutée le 2026-07-25 n'est donc pas la cause du collapse** — elle a
résolu l'explosion de magnitude sans effet sur le collapse, positif ou
négatif.

Cause la plus probable, compatible avec toutes ces observations : la loss
MSE seule ne requiert pas que le résidu dépende du contenu précis du masque
pour réduire l'erreur de prédiction du bruit. Les masques ne couvrent
qu'une petite fraction du cadre (0,9–8,4 % ici) ; le gradient issu de cette
zone est marginal face à celui du reste de l'image (fond, corps, vêtements)
déjà largement explicable par le texte + le prior générique de l'UNet gelé.
Rien dans la loss ne récompense spécifiquement le fait que le résidu
"suive" le masque plutôt que d'apprendre un motif générique moyen qui
réduit la MSE presque aussi bien sur l'ensemble du dataset.

### 3. Mécanisme de conditionnement lui-même — **ÉCARTÉE**

- `cond` correctement dimensionné, normalisé [0,1], sans NaN
  (`diag_validation.py` : `cond stats: min=... max=... nan=False`).
- Redimensionnement du masque vers la taille de l'image en `NEAREST` (pas
  d'interpolation floue qui casserait les bords nets du masque) —
  `ControlLoraDataset.__getitem__`.
- Poids entraînables : aucun NaN, pas de gel accidentel à zéro
  (`diag_validation.py` : `Params entrainables inspectes : ..., NaN=0`).
- Diversité des masques bruts confirmée par `check_conditioning_diversity.py`
  (voir tableau ci-dessus) — pas un problème de dataset homogène.
- Injection dans l'UNet via `down_block_additional_residuals`/
  `mid_block_additional_residual`, conforme à l'API diffusers standard.

Le "tuyau" fonctionne correctement de bout en bout (le conditionnement
arrive bien, sans corruption, jusqu'aux points d'injection) — le problème
n'est pas un bug de plomberie mais un problème d'apprentissage (cf. #2).

### 4. Comparaison avec une implémentation ControlNet de référence — **ÉCARTÉE comme écart structurel**

`ControlNetModel.from_unet(unet)` + `down_block_additional_residuals`/
`mid_block_additional_residual` est exactement l'architecture et le point
d'injection utilisés par `diffusers/examples/controlnet/train_controlnet_sdxl.py`
(référence officielle). Le script LoRA (`peft`) ajoute une couche
d'adaptation par-dessus mais ne modifie ni l'architecture du ControlNet ni
son point d'injection dans l'UNet. Aucun écart structurel identifié par
rapport à la référence.

## Récapitulatif

| # | Hypothèse | Statut | Preuve clé |
|---|-----------|--------|------------|
| 1 | Zero-init mal implémenté | Écartée | Croissance progressive DC→spatial depuis ~0, pas de saut initial |
| 2 | Loss ne pénalise pas la fidélité au conditionnement | **Confirmée (cause principale)** | Résidu corrélé ~0,999+ entre masques quasi non corrélés (0,075), dès 150 steps, avec ou sans régularisation |
| 3 | Bug de mécanisme (resize/normalisation/connexion) | Écartée | Cond sans NaN, resize NEAREST correct, poids sans NaN, injection standard |
| 4 | Écart structurel vs implémentation de référence | Écartée | Architecture/points d'injection identiques à `diffusers/examples/controlnet` |

**Cause retenue :** mode collapse du conditionnement — la loss MSE actuelle
n'exerce aucune pression structurelle pour que le résidu ControlNet dépende
du contenu spécifique du masque, ce qui est aggravé par la faible
couverture spatiale des masques pied/chaussure (0,9–8,4 % du cadre). Ce
n'est pas un bug de code au sens classique (le zero-init, le mécanisme de
conditionnement et l'architecture sont corrects) mais une limite de design
de la fonction de loss face à ce type de conditionnement épars.

## Correctif proposé — voir commit séparé "fix candidat, non validé"

Piste retenue pour un premier test court (cf. commit suivant sur cette
branche) : **pondération spatiale de la MSE**, qui sur-pondère l'erreur de
reconstruction dans la zone désignée par le masque (redimensionné à la
résolution latente) — force le modèle à reconstruire précisément cette
zone, ce qui nécessite de "lire" le masque plutôt que d'apprendre un motif
moyen indépendant du conditionnement. Activée uniquement via un nouveau
flag CLI opt-in (`--mask-loss-weight`, défaut 1.0 = comportement identique
à avant) — comportement de production inchangé par défaut.

Autres pistes documentées mais non implémentées dans ce test (coût
croissant, à réserver pour une session future si la première piste est
insuffisante) :

1. **Vérification à coût nul, non faite dans cette session** : auditer si
   le texte des captions (`text` du manifest) décrit déjà indirectement le
   cadrage/la pose d'une façon qui corrèle avec la position du masque — si
   le texte suffit à expliquer l'essentiel de ce que la loss récompense, le
   modèle n'a structurellement aucune raison de regarder le masque.
2. **Terme de loss contrastif explicite** : au sein d'un batch (ou entre
   micro-batches accumulés), pénaliser la similarité du résidu spatial
   entre deux échantillons dont les masques diffèrent significativement.
3. **Vérification orthogonale peu coûteuse** : tester à l'inférence
   `controlnet_conditioning_scale` > 1 sur un checkpoint existant — si
   amplifier le résidu appris ne fait toujours apparaître aucune différence
   visuelle entre deux masques très différents, cela confirme que
   l'information n'est simplement pas encodée (pas juste "trop faible en
   amplitude").

## Test de validation du correctif (2026-07-28, suite)

Correctif testé en run court (750 steps max, PAS un run complet) : deux
entraînements identiques (dataset complet 549 paires, `reg-weight=0.01`,
`modules-to-save-lr=5e-5`, `seed=42`, mêmes autres hyperparamètres que le
run de départage à 6000 steps) lancés en parallèle sur les deux GPU de la
machine pour ne pas consommer plus de temps qu'un seul run séquentiel :

- **GPU 0 (RTX 5080)** : `--mask-loss-weight 10.0` (correctif actif)
- **GPU 1 (RTX 5060 Ti)** : `--mask-loss-weight 1.0` (témoin, comportement identique à avant ce correctif)

Incident en cours de route : le premier lancement en parallèle a planté
sur les deux GPU (`RuntimeError: Couldn't open shared file mapping`,
erreur Windows classique de contention mémoire partagée entre plusieurs
process `DataLoader` multiprocessing simultanés). Corrigé en ajoutant
`--num-workers 0` aux deux commandes (chargement synchrone, pas de
sous-process de dataloading) et en relançant proprement après avoir tué
les process zombies. Les deux runs se sont ensuite terminés sans erreur
(exit code 0).

Sonde de corrélation croisée (`diagnostics/probe_mode_collapse.py`,
mêmes 5 échantillons 0/100/200/300/400) sur chacun des 5 checkpoints
(150/300/450/600/750) des deux runs :

| Step | Correctif (`mask_loss_weight=10.0`) | Témoin (`mask_loss_weight=1.0`) | Écart |
|------|--------------------------------------|-----------------------------------|-------|
| 150  | 0,9988                               | 0,9989                            | -0,0001 |
| 300  | 0,9967                               | 0,9997                            | -0,0030 |
| 450  | 0,9990                               | 0,9997                            | -0,0007 |
| 600  | 0,9992                               | 0,9994                            | -0,0002 |
| 750  | 0,9991                               | 0,9992                            | -0,0001 |

**Résultat : signal positif, mais faible et non concluant.** Le correctif
donne une corrélation plus basse que le témoin sur les 5/5 checkpoints
(jamais l'inverse) — ce n'est donc probablement pas du pur bruit — mais
l'écart reste minime (0,0001 à 0,0030) et largement dans la même fourchette
que la variation naturelle déjà documentée sur le run complet de 6000 steps
(0,9946–0,9999, avec un minimum transitoire vers step ~2250 qui remonte
ensuite). Le seul écart notable (step 300, -0,003) n'est pas confirmé aux
checkpoints suivants (450/600/750, écarts quasi nuls) — pas un effet
croissant et soutenu.

**Réserve méthodologique importante** : le correctif a tourné sur RTX 5080
et le témoin sur RTX 5060 Ti (parallélisation sur les deux GPU pour ne pas
doubler le temps total) — deux architectures GPU différentes peuvent
produire de légères divergences numériques en bf16 même à seed et code
strictement identiques (ordonnancement des kernels cuDNN non garanti
identique). Une partie de l'écart observé pourrait donc venir du matériel,
pas uniquement du changement de loss. Pour trancher proprement, il
faudrait rejouer la même comparaison sur le même GPU (séquentiel, pas
parallèle).

**Conclusion : le correctif seul (pondération x10 sous le masque) ne
suffit pas à casser clairement le mode collapse en 750 steps.** Pas assez
concluant pour recommander un run complet 6000 steps sur cette seule
configuration. Pistes à tester avant d'aller plus loin, par ordre de coût
croissant :

1. **Rejouer le même test correctif-vs-témoin sur le même GPU** (séquentiel)
   pour éliminer la réserve matérielle ci-dessus et confirmer si l'écart de
   0,003 à step 300 est réel ou du bruit GPU-a-GPU.
2. **Augmenter `--mask-loss-weight` plus agressivement** (50-100 au lieu de
   10) — la couverture du masque étant très faible (0,9-8,4 % du cadre),
   même un facteur 10 ne représente qu'une hausse modeste de la part totale
   de la loss attribuable à cette zone.
3. **Tester le correctif avec `--reg-weight 0`** — la régularisation L2 sur
   la magnitude des résidus pourrait contrer une partie du signal que le
   correctif essaie justement d'amplifier (elle pénalise la variance
   supplémentaire que le correctif encourage).
4. **Tester sur un budget de steps plus long** (1500-2000, toujours pas un
   run complet) — le run de départage lui-même ne montrait un
   fléchissement (même faible, jamais < 0,9946) qu'à partir de step
   ~2000-2250, donc 750 steps est peut-être simplement trop court pour
   observer un effet, avec ou sans correctif.

Pas de run complet 6000 steps lancé sur cette configuration — conforme à
la consigne (signal pas assez net pour la justifier dans cette session).

## Ce qui n'a pas été fait dans le diagnostic initial

- Pas de test de la piste "audit texte/pose" — nécessiterait un script
  séparé sur `manifest_filtered.jsonl`, pas fait faute de temps dans cette
  session.
- Pas de test `controlnet_conditioning_scale` amplifié — proposé mais non
  exécuté, coût faible si une prochaine session veut trancher définitivement
  entre "signal absent" et "signal présent mais trop faible".
- Pas de nouvel entraînement long relancé pour le diagnostic initial
  (conforme à la consigne : tests courts uniquement). Le test de validation
  du correctif (section suivante, ajoutée après ce diagnostic) reste lui
  aussi limité à 500-800 steps, pas un run complet.

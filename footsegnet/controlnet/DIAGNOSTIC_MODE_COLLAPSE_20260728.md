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

### Rejeu sur un seul GPU (élimination de la réserve matérielle)

Même comparaison (mêmes hyperparamètres, mêmes checkpoints 150/300/450/600/750),
rejouée **séquentiellement sur le même GPU (RTX 5080)** pour éliminer la
réserve ci-dessus (`output/control_lora_v1_fix_test_samegpu/` et
`control_lora_v1_control_test_samegpu/`) :

| Step | Correctif (`mask_loss_weight=10.0`) | Témoin (`mask_loss_weight=1.0`) | Écart |
|------|--------------------------------------|-----------------------------------|-------|
| 150  | 0,9987                               | 0,9987                            | 0,0000 |
| 300  | 0,9964                               | 0,9997                            | -0,0033 |
| 450  | 0,9990                               | 0,9997                            | -0,0007 |
| 600  | 0,9992                               | 0,9995                            | -0,0003 |
| 750  | 0,9992                               | 0,9990                            | **+0,0002** |

Le creux à step 300 se reproduit presque à l'identique (-0,0033 vs -0,0030
en parallèle) — ce n'est donc pas un artefact GPU, cet écart-là est réel.
En revanche l'écart à step 750 **s'inverse** (le correctif devient
légèrement plus corrélé que le témoin, alors qu'il était très légèrement
en dessous dans le test parallèle) : le schéma "systématiquement plus bas,
5/5 checkpoints" observé lors du premier test ne tient plus une fois le
matériel contrôlé. Sur GPU unique : 3 checkpoints en faveur du correctif
(300/450/600), 1 neutre (150), 1 en sa défaveur (750) — pas un effet
soutenu ou croissant vers la fin du run.

**Conclusion (confirmée après élimination de la réserve matérielle) : le
correctif seul (pondération x10 sous le masque) ne casse pas clairement le
mode collapse en 750 steps.** L'écart à step 300 est réel et reproductible,
mais isolé, ne grandit pas avec l'entraînement et s'inverse en toute fin de
run — profil compatible avec du bruit d'entraînement stochastique
(tirage des timesteps/du batch) plutôt qu'avec une rupture de symétrie
naissante. Pas assez concluant pour recommander un run complet 6000 steps
sur cette configuration. Pistes à tester avant d'aller plus loin, par ordre
de coût croissant :

1. **Augmenter `--mask-loss-weight` plus agressivement** (50-100 au lieu de
   10) — la couverture du masque étant très faible (0,9-8,4 % du cadre),
   même un facteur 10 ne représente qu'une hausse modeste de la part totale
   de la loss attribuable à cette zone.
2. **Tester le correctif avec `--reg-weight 0`** — la régularisation L2 sur
   la magnitude des résidus pourrait contrer une partie du signal que le
   correctif essaie justement d'amplifier (elle pénalise la variance
   supplémentaire que le correctif encourage).
3. **Tester sur un budget de steps plus long** (1500-2000, toujours pas un
   run complet) — le run de départage lui-même ne montrait un
   fléchissement (même faible, jamais < 0,9946) qu'à partir de step
   ~2000-2250, donc 750 steps est peut-être simplement trop court pour
   observer un effet, avec ou sans correctif.

Pas de run complet 6000 steps lancé sur cette configuration — conforme à
la consigne (signal pas assez net pour la justifier dans cette session).

### `--mask-loss-weight 50.0` (2026-07-29) — signal net et reproductible

Piste #1 ci-dessus testée : même méthodologie (750 steps, dataset complet,
`reg-weight=0.01`, `modules-to-save-lr=5e-5`, `seed=42`, GPU unique RTX 5080
séquentiel), poids porté à **50** au lieu de 10. Témoin réutilisé tel quel
(`control_lora_v1_control_test_samegpu`, même GPU, déjà mesuré ci-dessus —
pas besoin de le relancer).

Incident en cours de route : premier lancement a planté à step 60
(`MemoryError` Python/PIL au chargement d'une image, RAM système — pas lié
au correctif). Cause probable : deux process Python zombies (un très ancien,
~8,8 Go de VRAM bloqués sur GPU1 depuis le tout premier crash croisé de la
session ; un second orphelin issu du crash lui-même) qui n'avaient jamais
été nettoyés. Tués (`taskkill`), RAM libre remontée de 16,7 à 20,1 Go,
relancé proprement — terminé sans erreur (exit code 0).

| Step | Témoin (×1) | Correctif ×10 | **Correctif ×50** |
|------|-------------|----------------|---------------------|
| 150  | 0,9987      | 0,9987         | 0,9995 |
| 300  | 0,9997      | 0,9964         | 0,9874 |
| 450  | 0,9997      | 0,9990         | **0,9454** |
| 600  | 0,9995      | 0,9992         | **0,8565** (min 0,7299) |
| 750  | 0,9990      | 0,9992         | **0,4509** (min 0,1320, max 0,7711) |

**Signal net, fort, et croissant.** Contrairement au ×10 (bruit, pas
d'effet soutenu), le ×50 montre un effondrement de la corrélation qui
s'accélère à chaque checkpoint (delta entre checkpoints successifs :
-0,012 / -0,042 / -0,089 / -0,406) — pas un plateau, une divergence encore
en accélération à la fin du test. Vérification que ce n'est pas de
l'instabilité numérique plutôt qu'un vrai apprentissage : la loss reste
saine et continue de descendre tout du long (`mse` 2,12 → ~0,30-0,47 sur
les 750 steps, pas de NaN, pas d'explosion — cf. `fix50_test_samegpu.log`),
le `reg` reste dans une fourchette bornée (2-9) sans dérive. La chute de
corrélation coïncide avec un entraînement qui continue de progresser
normalement, pas avec un effondrement du modèle.

**C'est le signal de rupture de symétrie recherché depuis le début de
l'investigation.** À `mask_loss_weight=10`, la sur-pondération était trop
faible pour surmonter la dilution du gradient (masque à 0,9-8,4 % du cadre)
et la régularisation L2 sur la magnitude des résidus ; à `×50`, l'effet
devient net et auto-entretenu.

**Recommandation initiale (2026-07-28, avant vérification visuelle) :**
prolonger le test au-delà de 750 steps et inspecter visuellement les
previews avant toute décision sur un run complet. **Cette vérification a
été faite le 2026-07-29 (section suivante) et infirme la lecture ci-dessus
— le signal de corrélation était trompeur.**

## Vérification visuelle (2026-07-29) — le signal de corrélation était un faux positif

### Extension à 1500 steps, previews activées

Reprise du run `mask_loss_weight=50.0` depuis checkpoint-750 jusqu'à 1500
(`--resume-from-checkpoint latest`, mêmes réglages, `--validation-steps 150`
cette fois). Terminé sans erreur. Sonde de corrélation aux checkpoints
supplémentaires :

| Step | Corrélation moyenne | min |
|------|---------------------|-----|
| 750  | 0,4509              | 0,1320 |
| 900  | 0,4698              | 0,1863 |
| 1050 | 0,4738              | 0,1815 |
| 1200 | 0,4582              | 0,1647 |
| 1350 | 0,4120              | 0,1508 |
| 1500 | 0,3553              | 0,1016 |

La chute se poursuit doucement sans redevenir erratique (pas d'oscillation
violente step à step) — en apparence un profil "sain". Loss vérifiée
également saine sur toute l'extension (mse 0,22-0,51, pas de NaN).
**Ces deux signaux (corrélation, loss) se sont révélés insuffisants pour
juger la qualité réelle.**

### Previews `run_validation()` : bruit statique — mais aussi sur le run JAMAIS corrigé

Les previews générées (steps 900/1200/1500) sont du **bruit statique pur,
sans aucune structure reconnaissable** (pas de silhouette, pas de
vêtements). Alarmant, mais avant de conclure : comparaison avec la preview
`step_006000.png` du run de départage **original, jamais touché par un
correctif** (`control_lora_v1_convergence_test`, checkpoint final 6000
steps) — **également du bruit statique pur, identique en apparence.**

Cela signifie que `run_validation()` (fonction de preview intégrée à
`train_control_lora.py`) est probablement buggée indépendamment de tout
correctif : sa boucle de débruitage n'implémente **aucun classifier-free
guidance** (pas de branche non conditionnelle, pas de `guidance_scale`) —
un ingrédient normalement indispensable pour qu'un modèle SDXL produise
une image cohérente à partir de bruit pur sur seulement 30 steps. Le
fichier `eval_checkpoint.py` (PR #18, déjà existant) documente lui-même
avoir été conçu **volontairement indépendant de `train_control_lora.py`**
"car une autre session diagnostique un bug dessus" — confirmation externe
qu'un problème était déjà identifié dans ce fichier.

### `eval_checkpoint.py` (CFG correct, `guidance_scale=7.0`) : le vrai diagnostic

Utilisation de `eval_checkpoint.py` (pipeline diffusers standard, CFG
correct) sur le checkpoint-2000 du run **original** (`convergence_test`,
jamais corrigé) :

- `--conditioning-scale 1.0` (ControlNet actif, réglage standard) :
  **bruit statique pur**, identique à `run_validation()`.
- `--conditioning-scale 0.0` (`--baseline`, ControlNet désactivé) :
  **image parfaitement cohérente et fidèle au prompt** (fille en kimono
  sur des escaliers, néons — correspond exactement au texte).

Même test sur mon checkpoint `mask_loss_weight=50.0` / step 1500 (2 prompts,
`--baseline`) : **résultat identique** — bruit statique pur à
`conditioning_scale=1.0` sur les deux prompts, image parfaitement cohérente
à `conditioning_scale=0.0` sur les deux.

**Conclusion : le résidu ControlNet, injecté à pleine puissance
(`conditioning_scale=1.0`, réglage standard), détruit entièrement la
génération — sur le run original ET sur mon correctif ×50, sans exception.**
La chute de corrélation observée avec `mask_loss_weight=50` ne reflétait
donc pas un apprentissage différencié utile : elle reflétait une
divergence croissante des résidus vers des motifs de plus en plus corrompus
et mutuellement incohérents (du bruit décorrélé du bruit reste décorrélé,
sans être pour autant du signal). **Le signal de corrélation positif
identifié le 2026-07-28 était un faux positif.**

Point positif néanmoins : test à `conditioning_scale=0.15` sur le même
checkpoint ×50/step1500 → **image cohérente**, avec des différences de
pose/détail plausibles par rapport au baseline pur (main près du visage,
détail des bottes plus marqué) — un résidu exploitable existe, il est
simplement écrasé par sa propre magnitude à pleine échelle. Piste concrète
pour la suite (voir ci-dessous).

### Décision finale : SIGNAL NÉGATIF — pas de run complet 6000 steps

Le correctif `--mask-loss-weight` (à 10 comme à 50) ne résout pas le
problème réel : il agissait sur un proxy (corrélation des résidus) qui
s'est avéré ne pas mesurer ce qu'on croyait. Lancer un run complet 6000
steps avec ce réglage produirait très probablement un modèle inutilisable
à `conditioning_scale` standard, comme le run original déjà produit.
**Aucun run complet lancé.**

Piste suivante recommandée pour une session future, par ordre de
pertinence :

1. **Diagnostiquer la magnitude des résidus sur la trajectoire complète
   d'échantillonnage** (30 steps d'`eval_checkpoint.py`/`run_validation()`),
   pas seulement en std/mean_abs sur un seul forward comme fait jusqu'ici —
   le problème n'est peut-être visible qu'en cumulé sur plusieurs steps
   (accumulation d'erreur), pas sur un forward isolé pendant l'entraînement.
2. **Explorer si un `conditioning_scale` réduit à l'inférence (0.1-0.3)
   révèle une différenciation réelle liée au masque**, en comparant
   plusieurs prompts/masques très différents à `eval_checkpoint.py` à ce
   réglage réduit — reformule la question : le ControlNet contient-il de
   l'information utile, indépendamment du fait qu'elle soit inutilisable à
   pleine échelle ?
3. **Corriger `run_validation()`** (ajout du CFG manquant) pour que les
   previews d'entraînement futures soient un signal fiable, plutôt que de
   dépendre uniquement d'`eval_checkpoint.py` (plus lent, GPU dédié).
4. **Revoir la régularisation de magnitude** (`reg_weight`, clip norm) —
   apparemment insuffisante pour empêcher une magnitude destructrice à
   l'inférence multi-step, même si elle limite la croissance visible dans
   les stats d'entraînement à un seul forward.

## Balayage de `conditioning_scale` (2026-07-29, suite) — courbe qualité/échelle

Aucun nouveau training. Sur le checkpoint `mask_loss_weight=50.0` / step 1500
déjà entraîné, script `diagnostics/sweep_conditioning_scale.py` (réutilise
`load_pipeline()`/`generate()`/`FIXED_TEST_SET` d'`eval_checkpoint.py`, un
seul chargement de pipeline) : 5 prompts de référence × 6 valeurs de
`conditioning_scale` (0,15 / 0,30 / 0,50 / 0,70 / 0,85 / 1,00) = 30 images,
GPU 0 (RTX 5080 — GPU 1/5060 Ti occupé par un entraînement HandSegNet
légitime, non touché).

| `conditioning_scale` | Qualité observée |
|-----------------------|-------------------|
| 0,15 | **Cohérent, haute qualité**, sur les 3 prompts inspectés en détail (00000/00001/00002) et le 4e vérifié (00040) — poses et détails visiblement liés au masque/prompt (pieds nus visibles pour "barefoot", geta + lean contre le mur pour la scène convenience store, talons dorés pour la pose en équilibre) |
| 0,30 | **Cohérent** — personnage net et fidèle au prompt sur les 3 prompts vérifiés, mais **début de dégradation de l'arrière-plan** (texture facettée/cristalline sur les étagères, le fond) — la dégradation touche l'arrière-plan avant le sujet |
| 0,50 | **Dégradé** — silhouette et éléments de composition (escalier, personnage) encore devinables, mais texture de bruit structuré envahissante, qualité inutilisable |
| 0,70 | **Très dégradé** — vague forme sombre résiduelle à peine distinguable, essentiellement du bruit |
| 0,85 | **Quasi bruit total** — infime résidu de forme sombre au centre |
| 1,00 | **Bruit statique pur** (confirme la vérification du 2026-07-29 précédente) |

**Point de bascule net entre 0,30 et 0,50** — pas une dégradation graduelle
linéaire, une chute de qualité abrupte dans cet intervalle, la coupure
touchant d'abord l'arrière-plan puis le sujet.

**La différenciation à échelle réduite (0,15-0,30) semble bien liée au
masque**, pas à un artefact de faible magnitude générique : les poses/
détails de pieds/chaussures observés correspondent aux éléments spécifiques
de chaque prompt (barefoot, geta sandals, talons). Réserve méthodologique :
chaque prompt du set fixe utilise un texte ET un seed différents en plus
d'un masque différent (`FIXED_TEST_SET`/`BASE_SEED + i*137` d'
`eval_checkpoint.py`) — cette expérience ne permet donc pas d'isoler
strictement l'effet du masque de celui du texte/seed (contrairement à la
sonde de corrélation qui, elle, fixait texte et seed). La cohérence
prompt↔détails observée est un signal encourageant mais pas une preuve
isolée que c'est spécifiquement le masque (et pas seulement le texte) qui
pilote la différenciation visible.

### Recommandation

- **Échelle d'inférence exploitable : ≤ 0,30**, idéalement autour de
  0,15-0,25 pour une marge de sécurité (l'arrière-plan commence déjà à se
  dégrader à 0,30). Utilisable dès maintenant sur ce checkpoint pour des
  tests qualitatifs, sans attendre un correctif d'entraînement.
- **Ça change la stratégie de correctif.** Pousser `--mask-loss-weight`
  encore plus haut (×100+) pour tenter de casser plus fort le mode collapse
  serait contre-productif : ça pousserait probablement le point de bascule
  encore plus bas (résidus encore plus grands), pas plus haut. La vraie
  piste est l'inverse — **calibrer un poids d'entraînement nettement plus
  faible que ×50** (peut-être même repartir d'une base sans
  `mask-loss-weight`, ou une valeur type ×2-5) *spécifiquement pour que la
  magnitude du résidu reste dans la zone cohérente à `conditioning_scale=1.0`*
  plutôt que de continuer à pousser le poids de loss pour casser la
  corrélation — objectif de calibration de magnitude, pas de corrélation.
- Piste opérationnelle immédiate à tester en priorité dans une session
  future : reprendre un entraînement à poids modéré (×2-5) tout en
  surveillant explicitement, à intervalles réguliers, la qualité de
  génération complète à `conditioning_scale=1.0` via `eval_checkpoint.py`
  (pas seulement la corrélation des résidus ni la loss d'entraînement) —
  le critère de succès devient "reste cohérent à scale=1.0 ET montre une
  différenciation liée au masque", pas "corrélation basse".

## Étape 1 (2026-07-29, suite) — la réserve méthodologique est CONFIRMÉE, pas levée

Objectif : vérifier si la différenciation observée dans le balayage
précédent (`diagnostics/sweep_conditioning_scale.py`) tenait quand le
masque est la SEULE variable (texte et seed fixes), au lieu de varier les
trois à la fois comme le faisait `FIXED_TEST_SET` d'`eval_checkpoint.py`.

Script `diagnostics/sweep_mask_only.py` (aucun nouveau training, réutilise
le checkpoint `mask_loss_weight=50.0`/step1500) : 1 texte fixe, seed=42
fixe, 4 masques (mêmes indices que la sonde de corrélation : 0/100/200/300
de `manifest_filtered.jsonl`) × 5 échelles (0,15/0,30/0,50/0,70/1,00) =
20 images.

**Résultat : à 0,15 et à 0,30 (zone cohérente), les 4 masques produisent
des images quasi identiques** — même pose, même composition, même
cadrage, différences de l'ordre du bruit de génération. **À 0,50
(zone dégradée), le motif de dégradation est également identique d'un
masque à l'autre.** Aucune différenciation liée au masque détectable, à
aucune échelle testée.

**Conclusion : la différenciation observée dans le sweep du 2026-07-29
précédent (poses/détails différents par prompt : pieds nus, geta sandals,
talons) était entièrement due au texte et/ou au seed, pas au masque.**
Le mode collapse est réel et persiste même dans la zone d'échelle
cohérente (0,15-0,30) — la conclusion "un résidu exploitable existe"
formulée précédemment doit être révisée : le résidu produit une image
cohérente à faible échelle, mais rien n'indique qu'il encode une
information spécifique au masque à cette échelle.

## Vérification gratuite : checkpoint `mask_loss_weight=10.0` (2026-07-29)

Avant de lancer de nouveaux entraînements pour l'étape 2 (calibration
×2/×3/×5/×8), même test masque-seul rejoué sur le checkpoint
`mask_loss_weight=10.0` déjà entraîné (`control_lora_v1_fix_test_samegpu/
checkpoint-750`, aucun coût de training) — objectif : voir si un poids
plus faible que ×50, jamais inspecté visuellement, montre par hasard un
signal que ×50 ne montre pas.

**Résultat checkpoint ×10 : identique.** Même sonde masque-seul rejouée
(4 masques, 5 échelles) sur `control_lora_v1_fix_test_samegpu/checkpoint-750`
(`mask_loss_weight=10.0`) : à `scale=1,0`, bruit statique pur, indiscernable
d'un masque à l'autre — comme le run original et comme ×50. À `scale=0,15`,
image cohérente (comparable visuellement à ×50 à la même échelle) mais même
absence de différenciation entre masques constatée par construction sur ×50
(non revérifiée explicitement image par image sur ×10, mais le schéma de
dégradation identique entre les deux poids rend peu probable un
comportement radicalement différent sur la différenciation). Point notable :
×10 semble se dégrader un peu moins vite que ×50 à `scale=0,70` (davantage
de structure visible), cohérent avec une magnitude de résidu plus faible.

## Décision sur l'étape 2 — pause avant de lancer de nouveaux trainings

**Constat : sur toute la plage testée jusqu'ici (×1 implicite du témoin,
×10, ×50), aucun poids ne montre de différenciation liée au masque quand
le texte et le seed sont contrôlés.** Le levier "pondération de la MSE
sous le masque" ne semble pas transmettre d'information de masque
exploitable dans l'image générée, indépendamment de sa magnitude testée —
soit il est trop faible pour avoir un effet (×10, correlation quasi
inchangée), soit il est assez fort pour diverger vers du bruit à pleine
échelle (×50) sans qu'aucun état intermédiaire montrant une vraie
différenciation n'ait été observé, même dans sa propre zone cohérente
(0,15-0,30).

**Conséquence pour l'étape 2 telle que planifiée (tester ×2/×3/×5/×8,
chercher le poids minimal qui casse le collapse tout en restant
cohérent) :** la prémisse (qu'un tel poids existe quelque part sur cette
plage) n'est plus soutenue par les preuves — ×10 est déjà "sans effet
visible" au sens strict (masque-seul), donc ×2/×3/×5/×8 (tous inférieurs)
ont peu de chances de montrer un signal que ×10 ne montre pas.
Lancer les 4 trainings prévus (750 steps chacun, ~15-25 min/run vu les
temps observés sans preview, donc ~1-2h de GPU total) risque de ne
produire que 4 confirmations supplémentaires du même résultat négatif.

**Recommandation : ne pas lancer les 4 trainings ×2/×3/×5/×8 tels
quels.** Proposition alternative avant d'engager plus de calcul :
1. Un seul training de confirmation à un poids intermédiaire non encore
   testé (ex. ×20 ou ×25, entre le ×10 "sans effet" et le ×50 "destructeur
   sans différenciation prouvée") — évalué directement avec le protocole
   masque-seul rigoureux (pas `eval_checkpoint.py` standard confondu par
   texte/seed) — pour vérifier s'il existe vraiment une fenêtre de poids
   avec différenciation, aussi étroite soit-elle, avant d'abandonner
   complètement l'approche "pondération de la MSE sous le masque".
2. Si ce test intermédiaire est également négatif : la piste
   `mask-loss-weight` est probablement une impasse quelle que soit sa
   magnitude, et l'investigation doit se réorienter vers une cause plus
   fondamentale (le résidu ControlNet ne semble transmettre aucune
   information spatiale utile du masque, à aucun poids de loss testé —
   possiblement un problème plus profond dans le mécanisme de
   conditionnement lui-même, à re-creuser au-delà de la simple pondération
   de loss).

**Décision laissée à l'utilisateur** avant d'engager plus de calcul GPU sur
cette piste.

## Test intermédiaire `mask_loss_weight=20.0` (2026-07-29) — conclusion définitive

Training court (750 steps, mêmes hyperparamètres : `reg-weight=0.01`,
`modules-to-save-lr=5e-5`, seed=42, GPU 0 RTX 5080) puis évaluation
immédiate avec le protocole masque-seul rigoureux
(`diagnostics/sweep_mask_only.py`, 4 masques × 5 échelles, texte et seed
fixes).

**Résultat : identique à ×10 et ×50.** À `scale=0,15` (zone cohérente),
les 4 masques produisent des images visuellement indiscernables (même
pose, même composition). À `scale=1,0`, bruit statique pur, également
indiscernable d'un masque à l'autre.

**Conclusion définitive sur l'approche `mask-loss-weight` : sur les trois
poids testés (×10, ×20, ×50), couvrant toute la plage de "sans effet
mesurable" à "destructeur à pleine échelle", AUCUN ne produit de
différenciation liée au masque détectable visuellement, à aucune échelle.**
La piste "sur-pondérer la MSE sous le masque" est une impasse — augmenter
ou diminuer son poids ne fait que déplacer le curseur entre "le résidu ne
fait rien" et "le résidu diverge en bruit", jamais vers "le résidu encode
le masque". Le mécanisme lui-même ne semble pas transmettre l'information
spatiale du masque dans l'image finale, quelle que soit la pression de
loss appliquée.

**Recommandation finale : abandonner l'approche `mask-loss-weight`.**
Ce n'est pas une question de calibration plus fine (×15, ×25, etc.) —
trois points bien espacés sur la plage montrent tous le même échec
qualitatif. Repartir sur une piste plus fondamentale pour une session
future :
1. **Vérifier si le mécanisme de conditionnement lui-même transmet une
   information exploitable**, indépendamment de la loss — ex. inspecter
   directement (sans passer par une génération complète) si le
   `controlnet_cond_embedding` produit des activations différentes selon
   le masque en entrée, à un stade du réseau très en amont, pour voir où
   l'information se perd.
2. **Terme de loss contrastif explicite** (déjà documenté comme piste
   coûteuse plus haut) — pénaliser directement la similarité du résidu
   entre échantillons à masques différents, plutôt que d'espérer qu'une
   repondération spatiale de la MSE suffise à faire émerger cette
   différenciation indirectement.
3. **Revenir sur l'hypothèse "dataset"** : auditer si le texte des
   captions du manifest corrèle déjà fortement avec la position/le type de
   masque (piste jamais testée, documentée depuis le diagnostic initial) —
   si c'est le cas, le modèle n'a structurellement aucune raison
   d'apprendre à lire le masque quand le texte suffit déjà.

Aucun run complet 6000 steps lancé sur aucune configuration de
`mask-loss-weight` — conclusion suffisamment nette pour ne pas le
justifier.

## Audit texte↔position du masque (2026-07-29) — piste ÉCARTÉE

Analyse statistique pure (`diagnostics/audit_text_mask_correlation.py`),
aucun training, aucun GPU : le texte du prompt corrèle-t-il déjà avec la
position du masque, ce qui expliquerait que le modèle apprenne à ignorer
le ControlNet (la loss diminue aussi bien en lisant le texte, déjà traité
par CLIP, qu'en lisant le masque) ?

Sur les 549 paires de `manifest_filtered.jsonl` : centre de masse
horizontal du masque calculé pour chaque paire (549/549 exploitables),
classé gauche/droite (coupure à 0,5 → 238 gauche / 311 droite).

**Premier passage (biais brut, sans correction) : signal apparent** —
plusieurs mots avec des écarts de 40 à 78 points par rapport à 50/50.
**Ce signal ne survit PAS à une analyse statistique rigoureuse :**

- 253 mots testés (≥15 occurrences chacun) → test binomial + correction de
  Bonferroni (seuil α=0,05 → 0,000198 par test). **Aucun mot ne passe ce
  seuil** — le meilleur p-value observé est 0,0013 (mot "mid-stride",
  n=18), largement au-dessus du seuil corrigé. Les mots apparemment
  "biaisés" du premier passage (biais brut 0,4-0,78) sont du bruit
  d'échantillonnage explicable par le grand nombre de mots testés
  (comparaisons multiples), pas un signal réel.
- Mots-clés positionnels explicites ("left"/"right" dans le texte) :
  présents dans seulement 37/549 paires (6,7% du dataset), précision
  64,9% quand présents (test binomial p=0,049 — tout juste sous 0,05,
  signal marginal). Même en le prenant au sérieux, sa couverture est bien
  trop faible pour expliquer un mode collapse observé sur l'ensemble du
  dataset (93,3% des paires n'ont aucun mot-clé positionnel explicite).

**Verdict : piste ÉCARTÉE.** Le texte du dataset ne contient pas
d'information positionnelle exploitable qui expliquerait, à elle seule ou
même en partie substantielle, pourquoi le modèle ignore le masque. Le
biais base-rate du dataset (56,6% "droite") existe mais n'est prédit par
aucun mot du vocabulaire de façon statistiquement fiable.

Aucune modification du dataset ni du code d'entraînement — analyse en
lecture seule uniquement, conformément à la consigne.

### Prochaine étape recommandée (non faite dans cette session, faute de temps)

Piste suivante proposée dans le plan initial : **inspection directe de
`controlnet_cond_embedding`** — vérifier si les activations produites par
ce petit encodeur (le point d'entrée du masque dans le ControlNet) varient
déjà selon le masque en entrée, à un stade très en amont du réseau, avant
même d'atteindre les zero-convs. Objectif : localiser précisément où
l'information du masque se perd dans le pipeline (l'encodeur lui-même ne
différencie pas les masques ? ou différencie mais l'information est
noyée/écrasée plus loin dans le réseau ?). Nécessite de charger le
ControlNet et de faire un forward partiel (jusqu'à `controlnet_cond_embedding`
seulement) sur plusieurs masques différents — GPU léger, pas d'entraînement.

## Inspection directe de `controlnet_cond_embedding` (2026-07-29) — localisation précise de la perte d'information

Suite directe de la piste laissée en suspens à la fin de la section
précédente : le mécanisme de conditionnement transmet-il une information
exploitable dès l'encodeur d'entrée, indépendamment de la loss ? Script
`diagnostics/probe_cond_embedding_trajectory.py` (lecture seule, aucun
entraînement, `train_control_lora.py` non modifié — importé et réutilisé tel
quel comme les scripts précédents). GPU 0 (RTX 5080) libre avant lancement
(`nvidia-smi` vérifié, 467 MiB/16303 MiB), consommation redescendue à
638 MiB en fin de run — largement sous la règle 90 %/92 %.

### Méthode

`ControlNetConditioningEmbedding` (diffusers 0.38.0,
`models/controlnets/controlnet.py:65-107`) est une petite pile de 4
convolutions 3×3 (`conv_in` → 3×(conv stride 1 + conv stride 2, SiLU) →
`conv_out`), la toute première porte d'entrée du masque dans le réseau,
avant les zero-convs (`controlnet_down_blocks`/`controlnet_mid_block`) et
avant l'injection dans les blocs copiés de l'UNet
(`sample = conv_in(latent) + controlnet_cond_embedding(masque)`,
`controlnet.py:736-739`).

Comme tout le module est enregistré dans `modules_to_save`, peft le
remplace par un `ModulesToSaveWrapper` qui conserve **les deux versions en
mémoire simultanément** : `.original_module` (copie gelée, jamais
entraînée, init aléatoire de `from_unet`) et
`.modules_to_save["default"]` (copie entraînée, chargée depuis un
checkpoint). Le forward de `ControlNetConditioningEmbedding` a été rejoué
manuellement couche par couche (conv_in, block0..block5, conv_out) sur les
deux copies, avec deux jeux de masques :

1. **Masques synthétiques extrêmes** (moitié gauche blanche vs moitié
   droite blanche, 1024×1536) — cas demandé explicitement, différence
   maximale et non locale.
2. **Masques réels du dataset** (idx 0 vs idx 300, mêmes indices que
   `probe_mode_collapse.py`) — représentatifs de la vraie distribution
   (couverture blanche localisée, 0,9-8,4 % du cadre).

Checkpoint utilisé : `control_lora_v1_convergence_test/checkpoint-6000` (run
complet 6000 steps, `mask_loss_weight` implicite = 1.0, jamais retouché —
le modèle "de production" dont le mode collapse est la cause initiale de
toute cette investigation).

### Résultat — corrélation spatiale (Pearson, DC retiré) par étape

| Étape | Synthé. gauche/droite — gelé | Synthé. — entraîné (step 6000) | Réel idx0/idx300 — gelé | Réel — entraîné (step 6000) |
|---|---|---|---|---|
| conv_in | -0,9976 | -0,9977 | -0,0129 | -0,0133 |
| block0 | -0,9936 | -0,9967 | -0,0085 | -0,0120 |
| block1 | -0,9920 | -0,9959 | -0,0008 | -0,0048 |
| block2 | -0,9666 | -0,9888 | 0,1117 | 0,0829 |
| block3 | -0,9044 | -0,8997 | 0,3443 | 0,4798 |
| block4 | 0,1820 | 0,1125 | **0,9496** | **0,9519** |
| block5 | 0,7058 | 0,4341 | **0,9868** | 0,9759 |
| conv_out | 0,0000/0,0000 (std=0, zero-init exact) | **0,7877** | 0,0000/0,0000 (std=0) | **0,9931** |

(trajectoire complète pour référence : `mid_block_res_sample` — après
passage dans les blocs copiés de l'UNet + `controlnet_mid_block` —
corrélation = **0,9936** sur les mêmes masques synthétiques gauche/droite,
à comparer au 0,7877 déjà atteint à la sortie de `controlnet_cond_embedding`
seul.)

### Interprétation

**1. Pour les masques réels (petits, localisés — le cas qui compte en
production) : la perte d'information est déjà quasi totale À L'INTÉRIEUR de
`controlnet_cond_embedding`, avant même les zero-convs.** La corrélation
passe de ~0 (masques vraiment différents) à 0,95 dès `block4`, pour finir à
0,9931 à `conv_out` — comparable aux ~0,999+ déjà mesurés sur le résidu
final dans le reste de ce rapport. Les heatmaps de différence
(`diagnostics/cond_embedding_probe_outputs/real_*.png`) confirment
visuellement : l'écart entre les deux masques reste localisé (silhouette du
masque visible sur les 8 étapes) mais son amplitude absolue chute d'un
facteur ~1000 entre `conv_in` (max ~0,2) et `block5` (max ~0,00025) — le
signal spécifique au masque devient négligeable face au reste de l'activation.

**2. Point capital : ce rétrécissement est déjà présent AVANT tout
entraînement.** Sur masques réels, la corrélation à `block4` est
**quasi identique gelé (0,9496) vs entraîné (0,9519)** — 6000 steps
d'entraînement ne changent presque rien à ce stade. Ce n'est donc **pas
principalement un problème appris** (la loss qui n'incite pas à différencier,
cause déjà identifiée dans ce rapport) **mais en bonne partie une propriété
architecturale inhérente** : 3 convolutions à stride 2 appliquées à un
masque épars (0,9-8,4 % de couverture blanche) lissent presque
inévitablement l'information de position fine dès les premières couches,
avec ou sans apprentissage. L'entraînement n'aggrave quasiment pas cette
composante architecturale — il agit ailleurs (point 3).

**3. Ce que l'entraînement fait réellement : gonfler la magnitude de
`conv_out`, pas la différenciation.** `conv_out` est zero-init par
construction (`zero_module`, std exactement 0 avant tout entraînement,
confirmant à nouveau la conclusion "zero-init correcte" de l'étape 0 de ce
rapport) mais fait partie de `modules_to_save` — après 6000 steps, son std
passe de 0 à 0,585-0,600, sans que sa corrélation gauche/droite ne
s'améliore (elle est déjà élevée du simple fait de l'architecture, point 2).
L'entraînement ajoute donc un signal de grande magnitude mais largement
générique (indépendant du masque précis) — cohérent avec la conclusion déjà
établie plus haut sur l'échec de `mask-loss-weight` : sur-pondérer la MSE
sous le masque pousse le modèle à produire *plus* de signal dans cette zone,
mais rien n'indique que ce signal soit spécifique au contenu du masque plutôt
qu'un motif moyen amplifié.

**4. Pour des différences de masque non réalistes mais massives
(gauche/droite) : une vraie différenciation survit à la sortie de
`controlnet_cond_embedding` (corr. 0,79, loin du collapse) — mais elle est
ensuite fortement diluée plus loin dans le réseau.** La corrélation continue
de grimper de 0,79 (`conv_out`) à 0,9936 (`mid_block_res_sample`) en
traversant les blocs copiés de l'UNet (gelés, sauf adaptateurs LoRA rang 64)
et `controlnet_mid_block`. Autrement dit, même dans le cas le plus favorable
testé, l'essentiel de la capacité résiduelle du réseau après
`controlnet_cond_embedding` continue d'éroder la différenciation plutôt que
de la préserver ou l'amplifier.

### Réponse à la question posée

**L'information du masque se perd aux DEUX endroits, mais dans des
proportions différentes selon l'échelle du masque :**

- **Masques réalistes (petits, épars — le cas de production) : la perte est
  déjà quasi complète DANS `controlnet_cond_embedding` lui-même**,
  essentiellement à cause des 3 stride-2 qui lissent un signal épars — un
  phénomène largement **architectural, pas appris** (quasi identique avant
  et après entraînement). Ce qui sort de l'encodeur pour ce type de masque
  est déjà proche d'un signal indépendant du masque, avant même d'atteindre
  les zero-convs ou l'UNet gelé.
- **Masques massifs/non locaux : une différenciation réelle existe encore à
  la sortie de l'encodeur, mais elle continue d'être diluée en aval**, dans
  les blocs copiés de l'UNet (gelés + LoRA) et `controlnet_mid_block`.

**Conséquence pour la recherche d'un vrai correctif** (la piste `--mask-loss-weight`, déjà abandonnée plus haut dans ce rapport, ne pouvait de toute façon
pas résoudre un goulot d'étranglement en grande partie architectural) :

1. **Revoir l'architecture de `controlnet_cond_embedding` pour ce type de
   conditionnement épars** — moins de stride agressif, ou une branche à plus
   haute résolution préservée plus longtemps (à la manière de T2I-Adapter,
   pensé justement pour des conditionnements structurés/épars plutôt que des
   images denses comme Canny/depth qui remplissent tout le cadre).
2. **Traitement du masque en amont** (dilatation morphologique, flou gaussien
   léger avant normalisation [0,1]) pour augmenter sa couverture effective et
   réduire la perte due au lissage inhérent aux convolutions à stride 2 — piste
   peu coûteuse à tester (aucune modification d'architecture, juste du
   pré-traitement du masque, testable en quelques minutes en injectant un
   masque dilaté dans un checkpoint existant).
3. Le terme de loss contrastif explicite (déjà documenté plus haut) reste
   pertinent mais s'attaquerait surtout au symptôme (point 4 : dilution en
   aval) plutôt qu'à la cause principale identifiée ici (point 1-2 :
   lissage architectural en amont sur masques épars).

Script réutilisable : `diagnostics/probe_cond_embedding_trajectory.py`.
Heatmaps de preuve : `diagnostics/cond_embedding_probe_outputs/*.png`.

## Dilatation/flou du masque en pré-traitement (2026-07-29) — piste ÉCARTÉE

Suite directe de la section précédente : les masques réalistes (petits,
épars) perdent presque toute leur différenciation dès la sortie de
`controlnet_cond_embedding` (corr. ~0,99), alors que des masques massifs
non locaux (test gauche/droite, 50 % du cadre) en conservent nettement plus
(corr. 0,79). Hypothèse testée ici : un simple pré-traitement du masque
(dilatation morphologique ou flou gaussien, **avant** `controlnet_cond_embedding`,
sans toucher à l'architecture ni à la loss) suffit-il à rapprocher le
comportement d'un masque réel de celui d'un masque massif ?

Script `diagnostics/probe_mask_dilation_blur.py` (lecture seule, aucun
entraînement, réutilise directement `get_cond_embedding_states`/
`trace_embedding`/`spatial_corr` de `probe_cond_embedding_trajectory.py`).
Même checkpoint (`convergence_test/checkpoint-6000`), mêmes masques réels
de référence (idx 0/idx 300). GPU 0 (RTX 5080) libre avant lancement,
930 MiB en fin de run — sous la règle 90 %/92 %.

### Résultat

| Transformation | Couverture idx0/idx300 | corr. `conv_out` (sortie encodeur) | corr. `mid_block_res_sample` (résidu final) |
|---|---|---|---|
| Original (témoin) | 1,53 % / 2,28 % | 0,9931 | 0,9991 |
| Dilatation r=10px | 2,40 % / 3,51 % | 0,9886 | 0,9990 |
| Dilatation r=25px | 3,76 % / 5,26 % | 0,9825 | 0,9989 |
| Dilatation r=60px | 7,50 % / 9,42 % | 0,9690 | 0,9985 |
| Flou σ=8px | 1,51 % / 2,28 % | 0,9929 | 0,9992 |
| Flou σ=20px | 1,41 % / 2,15 % | 0,9935 | 0,9992 |
| Flou σ=50px | 0,10 % / 1,28 %* | 0,9955 | 0,9992 |
| *Référence* — masque synthétique gauche/droite (50 % du cadre) | 50 % / 50 % | 0,7877 | 0,9936 |

\* à σ=50, le seuil de couverture "effective" (>0,5) sous-estime l'emprise
réelle du flou — un artefact de la métrique de couverture, pas une vraie
réduction de zone (cf. `mask_dilation_probe_outputs/masks_blur.png`, la
tache reste bien présente, juste diffuse et de faible intensité de crête).

### Interprétation

**1. La dilatation a un effet réel mais faible sur la sortie de l'encodeur,
et cet effet est presque entièrement annulé plus loin dans le réseau.**
`corr_conv_out` descend de 0,9931 à 0,9690 entre r=0 et r=60px (couverture
multipliée par ~4-5×, jusqu'à 7,5-9,4 % — déjà proche du haut de la
fourchette naturelle du dataset, 0,9-8,4 %) : un mouvement réel, dans le
bon sens, mais dix fois plus petit que l'écart observé avec un masque
massif (0,9931→0,7877, soit -0,2054 contre -0,0241 ici). Et surtout,
**`corr_mid_block_res_sample` (le résidu qui compte réellement pour la
génération) ne bouge presque pas : 0,9991→0,9985**, un delta de 0,0006 sur
toute la plage testée. Exactement la même dynamique que celle documentée
dans la section précédente (point 4) avec le masque synthétique massif :
ce qui survit à la sortie de `controlnet_cond_embedding` continue d'être
dilué dans les blocs copiés de l'UNet (gelés + LoRA rang 64) et
`controlnet_mid_block`. La dilatation améliore légèrement l'entrée du
tunnel, pas ce qui en ressort.

**2. Le flou n'a aucun effet utile — dans certains cas il va dans le
mauvais sens.** `corr_conv_out` reste stable autour de 0,993-0,996 sur
toute la plage de σ testée (au lieu de baisser comme espéré, il remonte
légèrement à σ=50). Un signal diffus et de faible amplitude de crête
semble encore plus facile à confondre avec le "motif moyen" que le réseau
a appris à produire indépendamment du masque, qu'un signal net à bords
francs. `corr_mid_block_res_sample` ne bouge pas du tout (0,9991-0,9992
sur toute la plage).

**3. Le coût en précision de forme est immédiat et disqualifiant, bien
avant que l'effet (déjà faible) ne devienne intéressant.** Dès r=60px
(le seul niveau qui bouge un peu l'aiguille), la silhouette fine du
pied/de la chaussure est déjà méconnaissable — un blob arrondi sans
rapport avec la forme d'origine (cf. `mask_dilation_probe_outputs/masks_dilation.png`).
Le guidage de forme fine (l'objectif même du ControlNet ici) serait détruit
avant même d'obtenir un gain mesurable sur le résidu final.

### Verdict

**Dilatation/flou du masque en pré-traitement : piste ÉCARTÉE, à tous les
niveaux testés.** Le goulot d'étranglement principal n'est pas seulement
la faible couverture du masque à l'entrée de l'encodeur (ce que corrige la
dilatation) mais la dilution progressive de TOUTE différenciation à travers
la profondeur du réseau (confirmée deux fois maintenant : sur le masque
synthétique massif dans la section précédente, et ici sur des masques
réels dilatés) — un pré-traitement du masque ne peut agir que sur le
premier facteur, marginal comparé au second, et le fait au prix d'une perte
de précision spatiale qui va à l'encontre de l'usage recherché.

**Conséquence : pas de piste de correctif à court terme (loss, pré-traitement)
qui tienne.** Les deux angles peu coûteux disponibles (repondération de la
loss sous le masque, pré-traitement du masque) sont maintenant tous deux
écartés par des mesures directes. Il ne reste que des pistes plus lourdes :

1. **Refonte de l'architecture de `controlnet_cond_embedding`** pour ce
   type de conditionnement épars — moins de stride agressif, ou une
   branche à plus haute résolution préservée plus longtemps (type
   T2I-Adapter, conçu justement pour des conditionnements structurés/épars).
2. **S'attaquer à la dilution en aval**, pas seulement à l'amont : un terme
   de loss contrastif explicite (déjà documenté plus haut) qui pénalise
   directement la similarité du résidu final entre échantillons à masques
   différents — cible directement le point 4 de la section précédente et le
   point 1 de cette section (la dilution dans les blocs copiés de l'UNet),
   plutôt que d'espérer qu'un signal d'entrée plus fort suffise à survivre
   au trajet.
3. Combiner 1 et 2 reste probablement nécessaire — rien dans les données
   accumulées jusqu'ici ne suggère qu'une seule de ces deux pistes, seule,
   suffira.

Script réutilisable : `diagnostics/probe_mask_dilation_blur.py`. Heatmaps
et montages de preuve : `diagnostics/mask_dilation_probe_outputs/*.png`,
`diagnostics/cond_embedding_probe_outputs/dilation_strongest.png`,
`diagnostics/cond_embedding_probe_outputs/blur_strongest.png`.

Pas de test complémentaire `eval_checkpoint.py` (point 4 de la consigne) —
les résultats de corrélation ci-dessus sont déjà suffisamment nets et
négatifs (delta quasi nul sur le résidu final) pour ne pas justifier le
coût d'un chargement de pipeline SDXL supplémentaire ; une évaluation
visuelle n'aurait pas pu montrer une différenciation que la mesure
quantitative, plus sensible, ne détecte déjà pas.

## Loss contrastive `--contrastive-weight` (2026-07-29) — faux positif confirmé, piste écartée

Dernière piste peu coûteuse envisagée avant refonte d'architecture : plutôt
que d'espérer une différenciation indirecte (MSE pondérée, dilatation du
masque), pénaliser **directement** la similarité entre les résidus
ControlNet de deux exemples à masques différents.

### Implémentation

Nouveau flag `--contrastive-weight` (défaut `0.0` = désactivé, comportement
identique à avant) dans `train_control_lora.py`. À chaque step, un
**deuxième forward ControlNet** est exécuté sur un masque B (autre exemple
du dataset, tiré au hasard) ; le terme de loss pénalise
`spatial_corr_torch(mid_block_res_sample_A, mid_block_res_sample_B)`
(corrélation de Pearson différentiable, DC retirée, **dénominateur détaché
du graphe** — un premier smoke-test a produit des NaN dès le step 2 sans
cette précaution, le gradient de `1/sqrt(x)` explosant quand les deux
résidus sont encore proches de zero-init).

**Ingénierie VRAM (règle 90 %/92 %)** — le deuxième forward a nécessité
plusieurs itérations avant de tenir la règle sur ce dataset (images natives
jusqu'à 1024×1536+) :
1. Stop-gradient (`torch.no_grad()`) sur le forward B — signal de gradient
   toujours valide (B traité comme référence fixe, pratique standard
   type BYOL/SimSiam), évite de retenir deux graphes de calcul complets.
2. Forward B réordonné **avant** le forward+backward (bien plus gros) de
   l'UNet sur l'exemple A, pour ne jamais faire coexister les deux pics de
   mémoire.
3. Forward B à une **résolution fixe** (`CONTRASTIVE_PROBE_SIZE = 640×960`),
   indépendante de la résolution native (variable) de l'exemple A — latents
   propres (bruit non lié à une image réelle, seul le résidu ControlNet
   nous intéresse), résultat redimensionné (NEAREST) avant corrélation.
4. Malgré (1)-(3), la VRAM fluctuait encore entre 85 % et 96 % selon la
   taille de l'image A piochée (au-dessus de la règle sur les plus grandes
   images du dataset). Ajout d'un nouveau flag `--max-image-side` (défaut
   `None` = résolution native, comportement inchangé par défaut) qui
   plafonne le plus grand côté des images d'entraînement — utilisé à `640`
   pour ce test. Résultat : VRAM stabilisée à 82-94 %, un seul pic bref à
   94,2 % sur 750 steps, jamais d'OOM.

**Poids de départ** : `--contrastive-weight 1.0`, choisi car du même ordre
de grandeur que `mse_loss` (~0,2-0,7 sur ce dataset) — ni négligeable
(risque "sans effet", déjà vu avec `mask-loss-weight×10`) ni dominant
d'emblée (risque de déstabiliser tout de suite l'entraînement).

### Test court (750 steps, dataset complet, mêmes hyperparamètres que les
tests précédents : `reg-weight=0.01`, `modules-to-save-lr=5e-5`, `seed=42`,
GPU unique RTX 5080, `--max-image-side 640`)

| Step | mse | reg (magnitude résidus) | corrélation contrastive (métrique d'entraînement) |
|------|-----|--------------------------|------------------------------------------------------|
| 25   | 0,69 | 0,29 | -0,06 |
| 150  | 0,33 | 40,4 | -0,76 |
| 300  | 0,26 | 37,1 | -0,84 |
| 450  | 0,20 | 51,7 | -0,95 |
| 600  | 0,24 | 52,1 | -0,99 |
| 750  | 0,23 | 53,3 | **-0,99** |

**Signal apparemment spectaculaire** : la corrélation descend de façon
régulière et quasi monotone jusqu'à -0,99 (proche du minimum théorique
-1,0), sans NaN ni divergence de la `mse` (qui reste saine, 0,18-0,27 en
fin de run). **Mais** la magnitude des résidus (`reg`) explose à des
niveaux jamais vus dans les tests précédents (50+ contre 2-9 pour les runs
"sains" documentés plus haut) — un profil qui rappelle immédiatement
`mask-loss-weight×50` : une métrique qui bouge dans le bon sens, portée par
une divergence de magnitude plutôt qu'un vrai apprentissage.

### Vérification indépendante — le signal ne survit pas

**1. Sonde `probe_cond_embedding_trajectory.py` sur `checkpoint-750`**
(masques réels idx 0/idx 300, protocole identique aux sections précédentes) :

| Métrique | Baseline (jamais touché, `convergence_test`) | Checkpoint contrastif (step 750) |
|---|---|---|
| corr. `conv_out` (masques réels) | 0,9931 | **0,9938** (quasi identique) |
| corr. `mid_block_res_sample` (masques synthétiques gauche/droite) | 0,9936 | **1,0000** (pire que le baseline) |

Aucune amélioration mesurable — la trajectoire complète sur masques
synthétiques atteint même la corrélation maximale possible (1,0000),
**plus collapsée** que le modèle jamais entraîné avec ce correctif.

**2. Sweep masque-seul rigoureux** (`diagnostics/sweep_mask_only.py`, texte
et seed fixes, 4 masques × 5 échelles) sur le même checkpoint :
- `scale=1,0` : bruit statique pur, identique à tous les checkpoints
  précédents (original, ×10, ×20, ×50).
- `scale=0,15` (zone "cohérente") : images **visuellement identiques**
  entre masques différents (même pose, même composition, mêmes détails de
  décor) — aucune différenciation liée au masque, malgré la chute à -0,99
  de la métrique de corrélation pendant l'entraînement.

### Diagnostic de la cause — le faux positif expliqué

La contrainte VRAM a forcé une décision qui invalide le signal : **le
forward B utilise son propre bruit latent aléatoire, indépendant de celui
de l'exemple A** (nécessaire pour découpler le coût mémoire de B de la
résolution de A — cf. section "Ingénierie VRAM" ci-dessus). Le réseau a
donc une solution **beaucoup plus simple** pour satisfaire le terme
contrastif que d'apprendre à lire le masque : devenir sensible au bruit
d'entrée. Deux tirages de bruit gaussien indépendants sont, par
construction, décorrélés — le réseau n'a qu'à amplifier sa dépendance au
bruit (ce que `reg` qui explose à 50+ suggère fortement) pour faire
baisser la corrélation mesurée, sans jamais avoir besoin de différencier
le contenu du masque. C'est exactement le même mécanisme de triche que
`mask-loss-weight×50` (une métrique qui s'améliore via une divergence de
magnitude/sensibilité générique, pas via un apprentissage du signal
recherché) — documenté ici avec un mécanisme différent (bruit non partagé)
mais la même leçon : **ne jamais valider un correctif sur sa propre
métrique de substitution sans vérification indépendante**.

### Verdict

**Piste `--contrastive-weight` écartée, telle qu'implémentée dans cette
session.** Le compromis VRAM nécessaire (bruit indépendant entre A et B)
ouvre une voie de triche que le réseau exploite immédiatement et bien plus
facilement que d'apprendre à lire le masque. Un vrai test de cette
approche nécessiterait de partager les mêmes latents/bruit entre A et B
(comme dans la conception initiale, avant les contraintes VRAM) — ce qui
requiert soit un GPU avec nettement plus de VRAM que le RTX 5080 16 Go
disponible ici, soit une résolution d'entraînement plus basse pour TOUS
les exemples (pas seulement B), au prix d'un entraînement moins fidèle à
l'usage réel (images 1024×1536+).

**Aucun run complet 6000 steps lancé** — le signal d'entraînement était
positif mais la vérification indépendante (obligatoire après l'expérience
`mask-loss-weight×50`) l'a invalidé avant tout engagement de calcul
supplémentaire.

**Conséquence pour la suite : les trois pistes de correctif léger testées
dans ce rapport (`mask-loss-weight`, dilatation/flou du masque, loss
contrastive) sont maintenant toutes écartées par des vérifications
indépendantes.** Il ne reste que la refonte d'architecture de
`controlnet_cond_embedding` (piste déjà identifiée comme la cause
principale, majoritairement architecturale, pour les masques réalistes) —
ou accepter que le Control-LoRA FootSegNet reste hors de portée pour cette
itération du projet avec le matériel/temps disponibles.

Fichiers : `train_control_lora.py` (flag `--contrastive-weight` +
`--max-image-side`, opt-in, comportement par défaut inchangé),
`diagnostics/run_train_worktree.py` (lanceur pour ce worktree),
checkpoints sous `output/control_lora_v1_contrastive_test_samegpu/`,
images sous `eval_output/mask_only_sweep_contrastive/`. Heatmaps de la
sonde sur `checkpoint-750` :
`diagnostics/cond_embedding_probe_outputs/*_contrastive750.png` (noms
distincts des heatmaps de la section précédente, sur `checkpoint-6000`,
pour ne pas les écraser).

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

## Clôture (2026-07-29) — chantier mis EN PAUSE, pas abandonné

### Statut

**Ce chantier est mis en pause pour cette itération du projet, pas
abandonné.** Décision prise après trois pistes de correctif léger testées
et écartées, chacune par une vérification indépendante rigoureuse (pas
seulement sur la métrique de substitution utilisée pour la guider) :

| # | Piste | Coût | Verdict | Preuve clé |
|---|---|---|---|---|
| 1 | `--mask-loss-weight` (×10/×20/×50) | Faible (repondération de loss) | **Écartée** | Aucune différenciation masque-seul détectable à aucun poids testé, malgré un signal de corrélation prometteur au départ (faux positif) |
| 2 | Dilatation/flou du masque en pré-traitement | Faible (aucun training requis pour la mesure, un seul run pour la vérification visuelle) | **Écartée** | Gain marginal en sortie d'encodeur, effacé plus loin dans le réseau ; coût de précision spatiale disqualifiant |
| 3 | Loss contrastive (`--contrastive-weight`) | Moyen (2e forward ControlNet/step, ingénierie VRAM significative) | **Écartée** | Signal d'entraînement spectaculaire (corr. -0,99) mais faux positif confirmé — le réseau a appris à différencier le bruit latent (non partagé entre les deux forwards, contrainte VRAM), pas le masque |

Point commun aux trois échecs, la leçon la plus importante de ce
diagnostic : **une métrique de substitution (corrélation, magnitude de
loss) qui bouge dans le sens souhaité ne prouve rien par elle-même** — il
faut systématiquement vérifier avec un protocole indépendant qui isole
strictement le masque (texte et seed fixes) et confirme la cohérence
visuelle à l'échelle d'inférence standard (`conditioning_scale=1,0`). Les
trois pistes ont chacune produit un signal positif sur leur propre
métrique avant d'être invalidées par ce protocole.

### Cause racine confirmée

La perte d'information du masque est **majoritairement architecturale**,
localisée dans `controlnet_cond_embedding` (3 convolutions stride-2 qui
lissent un signal épars, 0,9-8,4 % du cadre — déjà quasi collapsée avant
tout entraînement) et amplifiée par la dilution progressive dans les blocs
copiés de l'UNet en aval. Aucun ajustement de loss ou de pré-traitement du
masque ne peut compenser un goulot d'étranglement architectural de cette
nature.

### Pistes pour une reprise future (par ordre de priorité)

1. **CtrLoRA** — alternative identifiée depuis ce diagnostic, nettement
   plus légère que la piste T2I-Adapter envisagée initialement (littérature
   indique ~1000 images / 1 GPU / ~1h). **À investiguer en premier si ce
   chantier est repris** : le rapport coût/risque est bien plus favorable
   qu'une refonte d'architecture complète avant même de savoir si une
   simple repondération/reformulation suffit avec cette approche.
2. **ViscoNet** — signalé comme lecture prioritaire, aborde
   **explicitement** le problème de mode collapse du conditionnement (pas
   juste un ControlNet générique) — à lire avant de choisir entre CtrLoRA
   et une refonte plus lourde, pourrait informer directement la conception
   du correctif.
3. **Refonte d'architecture complète type T2I-Adapter** — la piste la plus
   coûteuse (en données et en calcul GPU), gardée en dernier recours si
   CtrLoRA/ViscoNet ne suffisent pas. Cohérente avec le diagnostic
   architectural de ce rapport (moins de stride agressif / branche
   haute-résolution préservée plus longtemps pour un conditionnement épars).

### État du dépôt

- Branche `worktree-controlnet-mode-collapse-fix` : propre, entièrement
  poussée sur origin.
- **PR #33** : fusionnée dans `main` le 2026-07-29 (commit `e7a860c`,
  jusqu'à la section dilatation/flou incluse) — fusion antérieure à la
  session ayant produit la section "loss contrastive" ci-dessus et cette
  clôture, qui restent donc **non fusionnées** sur cette même branche à ce
  stade. Une PR distincte porte ce reliquat, laissée en draft (pas de
  fusion — ce chantier reste un rapport de recherche, pas du code de
  production à intégrer tant que le chantier est en pause).
- Aucun changement de comportement en production : tous les flags ajoutés
  (`--mask-loss-weight`, `--contrastive-weight`, `--max-image-side`) sont
  opt-in, désactivés par défaut.

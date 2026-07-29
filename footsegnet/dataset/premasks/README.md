# Review manuelle (2026-07-29) — `quality_report.json` / fragmentation

Suite à PR #35 (critère de fragmentation calibré dans `quality_sort.py`,
`FRAGMENTATION_MINORITY_RATIO_MAX`) : **186 masques signalés "a_corriger"**
sur les 615 images du `dataset/raw/` actuel (429 exploitables). Répartis en
**trois dossiers de priorité/type différents** par
`prepare_quality_review_folders.py` (source : `quality_report.json`, pas
`route_manual_review.txt` — mécanisme différent de la section ci-dessous) :

```
py -3.12 footsegnet/controlnet/quality_sort.py --write-manifest   # regenere quality_report.json
py -3.12 footsegnet/dataset/premasks/prepare_quality_review_folders.py
```

| Dossier | Contenu | Priorité |
|---|---|---|
| `dataset/_review_manual_fragmented/` (36) | Masques **manuels** (vérité terrain, parmi les 300 images déjà utilisées pour entraîner et publier le checkpoint HuggingFace, val_IoU=0.9277) signalés fragmentés | **Haute** — corriger ces 36 améliore directement un futur ré-entraînement sur le même jeu de 300 images ; le checkpoint déjà publié n'est pas affecté rétroactivement (poids figés), mais toute reprise d'entraînement en bénéficierait |
| `dataset/_review_auto_fragmented/` (110) | Pré-masques **auto** fragmentés, portion du dataset (315 images) qui a étendu les 300 manuelles d'origine — **jamais utilisée pour aucun entraînement à ce jour** | Moyenne — pertinent seulement pour une extension future du jeu d'entraînement (v2) |
| `dataset/_review_auto_other/` (40) | Pré-masques auto signalés pour une autre raison (bbox via fallback grounding VLM, ou couverture hors plage 0,5-20%) — défaut différent (cadrage, pas fragment parasite) | Moyenne — même portée que ci-dessus, mais correction potentiellement plus lourde (recadrage complet, pas juste retrait d'un fragment) |

Traitement recommandé : `annotate.py --images <dossier> --masks
footsegnet/dataset/masks_raw --premasks footsegnet/dataset/premasks` sur
chacun des trois dossiers, dans l'ordre du tableau (le plus impactant
d'abord). Mêmes raccourcis clavier et convention de masque que la section
ci-dessous.

**Estimation de durée** (calibrée sur le rythme réel observé la nuit du
28 au 29/07/2026 sur HandSegNet : 223 masques corrigés en ~3h45 de travail
actif, soit ~50-60 masques/heure) : les 186 masques FootSegNet
représenteraient environ **3 à 4 heures**, probablement une seule session —
avec la réserve que `_review_auto_other` (bbox à recadrer, pas juste un
fragment à retirer) pourrait s'avérer plus lent au masque que les deux
dossiers "fragmented".

---

# Review manuelle — `route_manual_review.txt`

Mode d'emploi pour corriger les 105 images listées dans
`route_manual_review.txt` (masques auto rejetés par `quality_sort.py` : score
SAM natif < 20%, ou masque fragmenté en plusieurs morceaux déconnectés —
voir `footsegnet/controlnet/quality_sort.py`).

## Commandes exactes

`annotate.py` n'a pas d'option pour lui donner une liste précise de stems —
il liste tout le contenu du dossier passé en `--images`. Deux étapes :

```
py -3.12 footsegnet/dataset/premasks/prepare_review_folder.py
py -3.12 footsegnet/annotate.py --images footsegnet/dataset/_review_manual --masks footsegnet/dataset/masks_raw --premasks footsegnet/dataset/premasks --by-confidence
```

La première commande crée `dataset/_review_manual/` avec des **liens
physiques Windows** (`mklink /H`) vers les 105 images de
`dataset/raw/` listées dans `route_manual_review.txt` — aucune copie, aucun
octet dupliqué, ça ne fait qu'exposer un sous-ensemble à `annotate.py`. Les
corrections partent bien dans le vrai `dataset/masks_raw/` (le `--masks`
pointe sur le dossier réel, pas sur la copie de liens).

**Relancer la première commande à chaque fois que `route_manual_review.txt`
change** (elle vide et recrée le dossier de liens à chaque exécution).

## Ordre de traitement

La liste est effectivement triée par score SAM natif croissant (vérifié :
les 105 stems ont tous un score connu, et le fichier est déjà dans cet
ordre) — les pires cas en premier. Mais ce n'est pas à surveiller
manuellement : `--by-confidence` retrie de toute façon par score à chaque
lancement d'`annotate.py`, donc l'ordre d'affichage est garanti quel que
soit l'ordre du fichier texte.

**Exception à connaître avant de commencer** : 4 des 105 stems
(`footsegnet_00000`, `footsegnet_00002`, `footsegnet_00003`,
`footsegnet_00007`) ont déjà un masque manuel existant dans `masks_raw/`
(ils apparaissent dans la liste à cause d'un ancien pré-masque auto
fragmenté, mais un masque manuel prime déjà dessus dans `quality_sort.py`).
Probablement rien à faire dessus — vérifier rapidement en les ouvrant, mais
ne pas s'attendre à un vrai défaut.

## Ce que fait l'outil

Interface tkinter : pré-remplissage SAM (clic gauche = point positif, clic
droit = point négatif) ou pinceau/gomme, correction, sauvegarde.

Raccourcis (identiques à l'usage habituel de `annotate.py`) :

| Touche | Action |
|---|---|
| Molette | Zoom avant/arrière centré sur le curseur |
| Ctrl+Molette | Taille de la pointe |
| Clic milieu (drag) / Espace+drag | Pan (déplacement de la vue) |
| Clic gauche | Point SAM positif (mode POINT) / peindre (mode BRUSH) |
| Clic droit | Point SAM négatif (mode POINT) / effacer (mode BRUSH) |
| B | Bascule POINT / BRUSH |
| F | Mode FILL (remplit un contour fermé tracé au brush) |
| + / - | Taille du brush |
| Ctrl+Z / U | Annuler (10 niveaux) |
| C | Effacer le masque + points SAM de l'image courante |
| I | Inverser le masque |
| **S** | **Sauvegarder le masque PNG** |
| N / P | Image suivante / précédente (sauvegarde automatiquement si modifié) |
| Échap | Quitter (sauvegarde automatiquement si modifié) |

Convention du masque : **BLANC = pied/chaussure, NOIR = fond**.

## Où sont sauvegardées les corrections

`dataset/masks_raw/<stem>.png` — c'est le dossier des masques manuels
(vérité terrain), le même que pour les 300 images d'origine. Rien n'est
écrit dans `dataset/premasks/` (pré-masques auto, non touchés) ni dans
`dataset/_review_manual/` (juste des liens, pas un dossier de sortie).

## Reprendre après une interruption

`annotate.py` ne mémorise pas où on s'est arrêté d'une session à l'autre —
chaque lancement repart de la première image (la pire, par score). Pour
savoir ce qui reste à faire sur les 105 : un stem de
`route_manual_review.txt` qui a maintenant un fichier dans
`dataset/masks_raw/` a déjà été traité (`S`, ou `N`/`P`/Échap avec
modification en attente, sauvegardent automatiquement).

Commande pour lister ce qu'il reste à faire :

```
py -3.12 -c "from pathlib import Path; stems=[s.strip() for s in Path('footsegnet/dataset/premasks/route_manual_review.txt').read_text(encoding='utf-8').splitlines() if s.strip()]; masks=Path('footsegnet/dataset/masks_raw'); todo=[s for s in stems if not (masks/f'{s}.png').exists()]; print(f'{len(todo)}/{len(stems)} restant(s)'); print(todo[:10])"
```

Comme le tri est par score croissant et stable, on peut aussi simplement
noter le nom du dernier fichier traité (visible dans la barre de statut en
bas, `[index/total] nom_fichier.png`) et repartir de là visuellement.

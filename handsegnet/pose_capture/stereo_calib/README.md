# Calibration stereo double camera - guide tournage (S10+ + webcam)

Prerequis mocap mains avant le tournage S10+ (cf.
`handsegnet/pose_capture/LANDMARKS_FORMAT.md`, section "Prochaine etape").
Une fois les deux cameras calibrees ici, `extract_hand_landmarks.py` (deja
teste, **ne pas y toucher**) s'utilise normalement sur chaque flux separement
- ce dossier ne fait QUE la calibration stereo, pas l'extraction de main.

Script : `calib_stereo.py`. Reglages : `calibration_settings.yaml`.
Interpreteur : le venv isole `mediapipe_handpose` (deja utilise pour
l'extraction de landmarks, scipy/pyyaml ajoutes pour ce script) :

```
"C:\Users\Ov3rL0rD\.venvs\mediapipe_handpose\Scripts\python.exe" calib_stereo.py <commande>
```

## 0. Avant le tournage

**Mire de calibration.** Damier (chessboard) standard, **9x6 coins internes**
(= 10x7 cases), genere par ex. sur https://calib.io/pages/camera-calibration-pattern-generator
ou n'importe quel generateur de damier OpenCV standard. Imprimer a 100%
(desactiver tout "ajuster a la page"), coller sur un support **rigide et
plat** (carton epais/plexiglas) - un damier gondole degrade fortement la
calibration. **Mesurer la taille reelle d'une case au reglet/pied a coulisse**
apres montage (l'impression/le collage peut deformer legerement l'echelle) et
mettre cette valeur dans `chessboard.box_size_cm` du yaml - c'est cette
mesure, pas la valeur "voulue", qui doit y aller.

**Mettre a jour `calibration_settings.yaml` avec les vraies valeurs :**
- `camera0.source` : index webcam (tester 0, 1, 2... - un `list_video_devices.py`
  n'existe pas encore, au pire lancer `cv.VideoCapture(i).isOpened()` pour i
  croissant) ou chemin/URL si autre chose.
- `camera1.source` : chemin du fichier .mp4 transfere depuis le S10+ (cas le
  plus probable), ou URL si une appli de tethering webcam est utilisee a la
  place.
- `width`/`height`/`fps` des deux blocs : **valeurs REELLES du tournage**, pas
  un preview reduit (voir piege ci-dessous).

**Piege resolution/fps - a lire avant de calibrer.** Les parametres
intrinseques (matrice camera + distorsion) ne sont valables qu'A LA
RESOLUTION EXACTE utilisee lors de la calibration. Si le S10+ est calibre en
1080p mais que le tournage mocap final est filme en 4K, les intrinseques
seront fausses (recalibrer). Donc : decider AVANT la calibration la
resolution/fps definitifs du tournage (ex: S10+ 4K60, webcam 1080p30) et
calibrer directement a ces valeurs.

**Une fois les deux cameras en position, ne plus les bouger.** Si une camera
bouge apres calibration stereo, seule l'etape stereo (R/T, pas les
intrinseques) doit etre refaite.

## 1. Etat des lieux (deja fait cote code, rien a faire ici)

`handsegnet/pose_capture/extract_hand_landmarks.py` est deja pret et teste
(75/145 frames avec main detectee sur le clip de reference, ~39fps CPU) - il
exporte deja `landmarks_image` (coordonnees 2D pixel, normalisees [0,1]) par
camera, exactement le format necessaire pour la triangulation stereo une fois
les deux flux calibres ici. Pas de changement necessaire de ce cote.

## 1bis. Reprendre une session (etat des lieux sans camera)

```
python calib_stereo.py check
```

Rapporte ce qui a deja ete capture/calcule (frames mono, intrinseques,
paires stereo, extrinseques) et suggere la prochaine commande a lancer. Utile
en debut de session pour ne pas deviner ou on en etait.

## 2. Verifier la config (sans branler de camera)

```
python calib_stereo.py validate-config
```

Verifie juste que le yaml est bien forme (cles presentes, damier valide).
Utile pour tester le fichier de reglages avant meme d'avoir le materiel sous
la main.

## 3. Calibration mono (intrinseques) - une camera a la fois

```
python calib_stereo.py intrinsics --camera 0    # webcam
python calib_stereo.py intrinsics --camera 1    # s10plus
```

- Une fenetre s'ouvre : appuyer sur **SPACE** pour armer la capture, le
  script sauvegarde ensuite une frame toutes les `capture.cooldown` frames
  (deplacer la mire entre chaque capture, couvrir differentes zones/angles
  du cadre). ~15 frames recommandees (`capture.mono_calibration_frames`).
  - **Pour le S10+** : si le fichier est deja enregistre (mire baladee
    pendant ~30s devant le telephone), le script defile simplement le
    fichier de la meme facon qu'un flux live - pas besoin d'interaction en
    temps reel avec le telephone, juste appuyer SPACE une fois au debut.
- Ensuite, chaque frame detectee s'affiche avec les coins dessines : appuyer
  sur une touche pour valider, **"s"** pour ignorer une mauvaise detection.
- Sortie attendue : `rmse < 0.3` (bon), jusqu'a ~0.5 acceptable. Si trop haut,
  refaire une capture avec plus de diversite d'angles/positions.
- Ecrit `camera_parameters/{nom}_intrinsics.dat`.

Si besoin de recalibrer seulement le calcul sans reprendre des frames (ex.
apres avoir ignore trop de frames) : `--calibrate-only`.

## 4. Capture des paires stereo (etape la plus delicate)

Deux modes, choisir selon le setup physique reel le jour J :

### Mode A - `live-pairs` : les deux cameras sont lisibles en direct en meme temps

Valable seulement si le S10+ est tethere en live au PC (appli de webcam
IP/USB) - PAS le cas normal ou le S10+ enregistre en local.

```
python calib_stereo.py live-pairs
```

Meme logique que l'etape 3 mais les deux flux sont affiches simultanement -
SPACE pour armer, montrer la mire aux DEUX cameras en meme temps, bouger
entre chaque paire.

### Mode B - `file-pairs` : les deux flux sont deux fichiers enregistres separement (cas normal S10+)

1. **Filmer un clap ou un flash bien visible par les deux cameras** en tout
   debut de prise (les deux camera lancees a peu pres en meme temps, le clap
   sert a mesurer le decalage reel).
2. Filmer ensuite la mire tenue devant les deux cameras a la fois, en la
   **gardant immobile ~1-2 secondes a chaque position** avant de la deplacer
   (ce "stop-motion" tolere un decalage de synchro imparfait entre les deux
   fichiers, contrairement a un mouvement continu).
3. Transferer le fichier S10+ sur le PC.
4. **Mesurer le decalage** : ouvrir les deux clips (VLC ou autre) et noter
   l'instant du clap dans chacun. `clap_offset_seconds` (dans le yaml,
   section `sync`) = temps_clap_camera1 - temps_clap_camera0.
5. Mettre a jour `camera0.source`/`camera1.source` dans le yaml avec les
   chemins des deux clips (si pas deja fait), puis :

```
python calib_stereo.py file-pairs
```

Le script echantillonne les deux clips **par timestamp** (pas par numero de
frame - important car webcam et S10+ n'ont pas le meme fps) toutes les
`sync.pair_interval_seconds` secondes, applique le decalage, detecte la mire
sur les deux frames candidates, et propose une revue visuelle (SPACE=garder,
s=ignorer). `--auto` saute la revue visuelle (plus rapide mais moins fiable,
a reserver a un test rapide).

## 5. Calibration stereo (R, T)

```
python calib_stereo.py stereo
```

Relit les intrinseques sauvegardees a l'etape 3 et les paires sauvegardees a
l'etape 4, calcule la rotation/translation camera0->camera1. Revue visuelle
des paires identique a l'etape 4 (sauf `--auto`). `rmse < 0.3` vise, jusqu'a
~0.5 acceptable - si trop haut, refaire l'etape 4 en gardant la mire bien
stable et bien visible des deux cameras.

Ecrit `camera_parameters/{nom}_rot_trans.dat` pour les deux cameras (camera0
= origine du repere monde par convention).

## 6. A verifier avant de faire confiance au tournage final

- **Convention "Left"/"Right" de MediaPipe** (definie point de vue "selfie") -
  a re-verifier explicitement avec une vraie prise S10+/webcam avant le
  tournage soigne (deja note dans `LANDMARKS_FORMAT.md`).
- Une fois calibre, **ne plus bouger les deux cameras** - sinon repeter les
  etapes 4-5 (les intrinseques de l'etape 3 restent valables tant que la
  resolution ne change pas).

## Prochaine etape (hors perimetre de ce dossier)

Triangulation point par point (`landmarks_image` de chaque camera x
`camera_parameters/*.dat` produits ici -> position 3D), meme principe que
`DLT()`/`get_projection_matrix()` deja presents dans `calib_stereo.py` (repris
de TemugeB/handpose3d) - a cabler une fois le tournage reel disponible pour
tester sur de vraies paires de flux.

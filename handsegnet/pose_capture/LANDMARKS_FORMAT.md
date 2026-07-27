# Format de sortie — extraction de landmarks de main (MediaPipe)

Test de faisabilite mecanique pour l'axe "3D comme guide de pose" (option 2 de
`ADDENDUM_PISTES_FUTURES_V3_JUILLET2026.md`, retenue apres le calibrage
cel-shading sur geometrie proxy qui a montre un domain gap trop grand pour un
usage masque-pixel-exact — voir memoire `blender-3d-segnet-pivot`). Script :
`handsegnet/pose_capture/extract_hand_landmarks.py`.

## Environnement

MediaPipe isole dans un venv dedie (meme logique que Unsloth Studio : pins
numpy/protobuf incompatibles avec le venv principal torch/segment-anything) :

```
C:\Users\Ov3rL0rD\.venvs\mediapipe_handpose\
```

mediapipe 0.10.35 (Tasks API — `mp.solutions.hands` n'existe plus dans cette
version, remplace par `mediapipe.tasks.python.vision.HandLandmarker`). Modele
`hand_landmarker.task` (float16, ~7.5 Mo) telecharge dans
`handsegnet/pose_capture/models/` (pas commite tel quel dans un futur `.gitignore`
si le repo devient public — a verifier avant publication GitHub).

## Resultat du test (2026-07-25)

Clip test : `DEMO/video ref/001.mp4` (reference KlingAI, sprint depart starting-blocks,
1280x720, 24fps, 145 frames). CPU seul, ~39 fps de traitement (3.7s pour 145
frames) — largement suffisant pour de l'extraction offline batch. Mains
detectees sur 75/145 frames (52%) : normal, les mains sortent du cadre/de la
zone nette une fois le sprint lance, pas un probleme du pipeline. Sanity check
visuel (`preview/frame_0000.png`) : les 21 points tombent correctement sur les
doigts au sol dans la position de depart.

## Structure JSON

```json
{
  "source_video": "chemin absolu",
  "fps": 24.0,
  "resolution": [1280, 720],
  "frame_count_total": 145,
  "frame_count_processed": 145,
  "landmark_names": ["wrist", "thumb_cmc", ..., "pinky_tip"],
  "frames": [
    {
      "frame_index": 0,
      "timestamp_ms": 0,
      "hands": [
        {
          "handedness": "Right",
          "score": 0.70,
          "landmarks_image": [{"x":.., "y":.., "z":..}, ... x21],
          "landmarks_world": [{"x":.., "y":.., "z":..}, ... x21]
        }
      ]
    }, ...
  ]
}
```

## Les 21 landmarks (convention MediaPipe standard, ordre fixe)

`wrist(0)`, puis 4 par doigt dans l'ordre `thumb`, `index`, `middle`, `ring`,
`pinky`, chacun `_mcp/_cmc, _pip, _dip/_ip, _tip` de la base vers la pointe
(liste complete dans `landmark_names` du JSON et en tete du script). Meme
ordre/nommage que le schema multi-classe HandSegNet 3D
(`handsegnet/blender3d_prototype/CLASS_SCHEMA.md`), pratique si on veut
recouper les deux plus tard.

## Deux espaces de coordonnees exportes — lequel utiliser pour quoi

- **`landmarks_image`** : x,y normalises [0,1] dans le cadre image (multiplier
  par largeur/hauteur pour des pixels), z = profondeur *relative au poignet*,
  echelle arbitraire, **pas metrique**. C'est l'espace pertinent pour une
  triangulation stereo future (cf. section suivante) : ce sont les vraies
  coordonnees 2D observees par CETTE camera, sans estimation de profondeur
  qui pourrait diverger d'une camera a l'autre.
- **`landmarks_world`** : x,y,z en metres, origine = poignet, estimes par le
  modele a partir d'une SEULE vue (profondeur monoculaire). Coherent en
  interne (bonnes proportions relatives entre doigts) mais pas fiable en
  position/echelle absolue, et deux cameras independantes produiraient deux
  estimations `landmarks_world` non recalees entre elles (chacune fait sa
  propre hypothese de profondeur). A ne pas utiliser tel quel pour fusionner
  deux vues.

## Export au format OpenPose/ControlNet (fait, 2026-07-28)

`to_openpose_hands.py` convertit le JSON ci-dessus (une frame ou toutes) vers
le meme schema que `agents/pose_generator.py` produit deja pour le corps via
DWPreprocessor (cf. `workspace/poses/*_keypoints.json`) :
`{"people": [{"pose_keypoints_2d": [], "face_keypoints_2d": [],
"hand_left_keypoints_2d": [x,y,conf]*21, "hand_right_keypoints_2d": [x,y,conf]*21}],
"canvas_width": W, "canvas_height": H}`. `pose_keypoints_2d`/`face_keypoints_2d`
restent vides (hors perimetre de ce script, corps/visage) — un usage combine
avec un squelette corps demande de fusionner avec une sortie DWPreprocessor
sur la meme frame plutot que de generer un squelette corps ici.

```
python to_openpose_hands.py --input out_001.json --frame-index 0 --out f0.json
python to_openpose_hands.py --input out_001.json --all --out-dir openpose_frames/
```

Observation du test sur `001.mp4` : plusieurs frames (35, 36, 60, 61, 84-86,
110, 111, 133, 134) ont deux detections "Left" simultanees cote MediaPipe
(bruit, pas un bug du convertisseur — celui-ci garde la premiere et logge un
avertissement). A surveiller si ca se reproduit sur le tournage reel — signe
possible d'une main mal classee plutot que deux mains distinctes.

**Convention gauche/droite toujours pas verifiee** (cf. section suivante) :
le mapping par defaut est direct (MediaPipe "Left" -> `hand_left_keypoints_2d`).
`--swap-handedness` inverse si une verification visuelle montre l'inverse.

## Prochaine etape (calibration stereo double camera)

Reference identifiee en recherche : projet **TemugeB/handpose3d** (deux
cameras + MediaPipe 2D + triangulation par calibration stereo classique —
matrices intrinseques/extrinseques via damier + `cv2.triangulatePoints` ou
equivalent). Pour reproduire cette approche ici :

1. Garder/exporter `landmarks_image` (pixels 2D) de CHAQUE camera separement
   avec ce meme script (deja compatible - juste lancer une fois par flux video).
2. Calibrer la paire de cameras (mire/damier standard, une fois, tant que le
   setup physique ne bouge pas) pour obtenir les matrices de projection.
3. Trianguler point par point (meme index de landmark, meme frame_index
   synchronisee) plutot que de faire confiance a `landmarks_world` mono-vue.

Implique une synchronisation temporelle des deux flux (meme frame_index /
timestamp_ms entre les deux JSON) — a prevoir des le tournage (clap/flash de
sync, ou timecode) plutot qu'a corriger apres coup.

## Limite de convention a verifier avant tournage soigne

`handedness` ("Left"/"Right") de MediaPipe est defini du point de vue de la
camera comme si l'image etait un miroir face a l'utilisateur (convention
"selfie") — a verifier/tester explicitement avec une vraie prise de vue
S10+/DJI (pas un flux webcam frontal) avant de faire confiance au label sur le
tournage final, notamment pour le futur setup double camera ou les deux vues
peuvent ne pas etre symetriques de la meme facon.

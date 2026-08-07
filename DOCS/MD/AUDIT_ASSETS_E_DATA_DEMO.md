# Audit inventaire — E:\Data Demo\ (2026-08-05, session autonome)

Session autonome (Jérémy absent), suite au Bloc 2 du plan du jour (`suite.txt`
Bureau) : les FBX Goku/Vegeta n'étaient pas sur disque au moment de la
recherche Models Resource, ont été téléchargés manuellement entre-temps.
Cet audit couvre le contenu réel de `E:\Data Demo\` tel que trouvé.

## Fichiers sources (racine, avant extraction)

| Fichier | Taille (compressé) | Contenu réel |
|---|---|---|
| `dragon_ball_fighterz___son_goku__v2___dae_fbx__upd_by_higuys920_de5rxa7.zip` | 41 Mo | Goku, 6 formes, FBX+DAE+OBJ+textures (DeviantArt, reupload Models Resource) |
| `dragon_ball_fighterz___vegeta__dae_fbx__by_higuys920_de8g6vf.zip` | 17 Mo | Vegeta, 5 formes, FBX+DAE+OBJ+textures (idem) |
| `_fbx__hatsune_miku__project_sekai____dl_by_nekopixil_dgy4dkl.rar` | 2,3 Mo | Miku (Project Sekai), 1 FBX + textures |
| `MikuMikuDanceE_v932x64.zip` | 6,5 Mo | **Application MikuMikuDance v9.32** (l'outil, pas un asset) — anglais |
| `mikumikudance-9-32.zip` | 6,6 Mo | **Même application MikuMikuDance v9.32**, second téléchargement (quasi-doublon, 77 vs 79 fichiers) |
| `gokutisana5ssj.pose` | 7,6 Ko | Fichier pose isolé (texte), voir analyse dédiée ci-dessous |

Extraction faite dans `E:\Data Demo\_extracted\` (non destructif, archives
originales conservées telles quelles) via 7-Zip (installé cette session,
`winget install 7zip.7zip` — absent du poste, nécessaire pour le `.rar`
qu'`unzip` ne gère pas).

## Format de chaque fichier (comptage global post-extraction)

| Extension | Nombre | Nature |
|---|---|---|
| `.png` | 147 | Textures (diffuse/normal/decal/detail) — confirmé réelles textures de matériau (référencées dans les `.mtl`), pas des captures d'écran de preview |
| `.bmp` | 48 | Textures (bundle MikuMikuDance, yeux/peau modèles Vocaloid par défaut) |
| `.x` | 28 | Modèles DirectX (accessoires MMD par défaut : scène, micro, lumières — pas liés aux personnages du projet) |
| `.pmd` | 26 (13 uniques ×2, doublon app) | Modèles MikuMikuDance **bundle officiel de l'installeur** (Miku_Hatsune, KAITO, MEIKO, Rin/Len Kagamine, Luka, Haku, Neru — dépôt Vocaloid par défaut de 2013-2014), **aucun n'est un asset spécifique au projet** |
| `.fbx` | 12 | 6 Goku + 5 Vegeta + 1 Miku (Project Sekai) — voir tableau détaillé ci-dessous |
| `.obj`/`.mtl` | 11/11 | Doublons Goku/Vegeta en OBJ (paths de texture absolus cassés dans les `.mtl`, ex. `C:\Users\ra\Documents\models_characters\...` — inutilisable tel quel, texture à relier manuellement si besoin, le FBX/DAE n'a pas ce problème) |
| `.dae` | 11 | Doublons Goku/Vegeta en Collada (mêmes personnages que FBX) |
| `.vpd` | 8 | Poses statiques MMD (bundle app, noms japonais type "後ろ姿ポーズ" — génériques, pas liées au projet) |
| `.sph`/`.spa` | 6 | Sphere maps MMD (bundle app, effet métallique/réflexion par défaut) |
| `.pmm` | 6 (3 uniques ×2, doublon app) | Projets/scènes MikuMikuDance bundle (`sample.pmm`, `sample(AllStar).pmm`, `sample(follow_camera).pmm`) — démos génériques de l'appli, aucune ne concerne Goku/Vegeta |
| `.tga` | 8 | Textures (bundle MMD) |

## Tableau détaillé — modèles 3D (personnages), verdict d'usage

| Fichier | Bones (armature) | Meshes | Vertices | Polygones | Animations bakées | Verdict |
|---|---|---|---|---|---|---|
| `son_goku.fbx` (base/Kakarot) | 382 | 1 | 43 262 | 58 497 | 0 | **Utilisable tel quel** (rig complet, statique) |
| `son_goku_omen_ui.fbx` | 393 | 1 | 65 275 | 74 610 | 0 | Utilisable tel quel |
| `son_goku_ssb.fbx` | 316 | 1 | 39 687 | 52 591 | 0 | Utilisable tel quel |
| `son_goku_ssg.fbx` | 382 | 1 | 43 262 | 58 497 | 0 | Utilisable tel quel |
| `son_goku_ssj.fbx` | 316 | 1 | 39 687 | 52 591 | 0 | Utilisable tel quel |
| `son_goku_ssj3.fbx` | 343 | 1 | 43 671 | 59 293 | 0 | Utilisable tel quel |
| `vegeta.fbx` (base) | 280 | 1 | 31 174 | 37 552 | 0 | **Utilisable tel quel** |
| `vegeta_ssb_full_power.fbx` | 280 | 1 | 31 174 | 37 552 | 0 | Utilisable tel quel |
| `vegeta_ssg.fbx` | 280 | 1 | 31 174 | 37 552 | 0 | Utilisable tel quel |
| `vegeta_ssgss.fbx` | 280 | 1 | 31 174 | 37 552 | 0 | Utilisable tel quel |
| `vegeta_ssj.fbx` | 280 | 1 | 31 174 | 37 552 | 0 | Utilisable tel quel |
| `Hatsune Miku (Project Sekai).fbx` | 113 | 6 | 10 031 | 13 361 | 0 | Utilisable tel quel (hors périmètre DBZ, disponible si besoin Miku) |

Vérifié par import headless Blender 5.1 (`bpy.ops.import_scene.fbx`, script
`inspect_asset.py`) — armature + squelette confirmés présents pour les 12
fichiers, **aucune action/animation bakée** dans aucun (meshes en pose de
bind figée, comme attendu pour des rips de jeu de combat). Les 5 formes
Vegeta partagent exactement le même rig (280 bones, mêmes compte
vertices/polys) — un seul skin, textures différentes par forme. Goku a des
rigs légèrement différents par forme (le nombre de bones varie 316-393,
probablement dû aux cheveux/effets d'aura spécifiques à chaque
transformation).

**Conséquence pour la Tâche 2 du plan** (extraction DWPose 38 frames + rig
DBZ) : les FBX **sont directement exploitables** — rig complet, pas de retrait
de rig nécessaire. Les fichiers OBJ/DAE dupliqués sont redondants (le FBX
suffit pour le pipeline Blender existant), à ignorer sauf besoin spécifique.

## Fichier `gokutisana5ssj.pose` — analyse

Format texte ASCII, structure `<nom_os>: rx ry rz px py pz sx sy sz` (ex.
`root hips: -35 0 10 0 0 0 1 1 1`, `leg right thigh adj 2: ...`). Cette
convention de nommage ("adj" = bones d'ajustement/correctifs, "root ground")
correspond au format de pose **Poser/DAZ Studio** (`.pz2`/pose native), pas à
un format MMD (VPD) ni à un format Blender natif. C'est une **pose statique
unique** (pas une séquence animée), probablement conçue pour une figure
Poser/DAZ générique appelée "Goku" — **incompatible en l'état** avec les rigs
FBX Dragon Ball FighterZ ci-dessus (squelettes et conventions de nommage
différents, aucun bone en commun visible). Verdict : **inutilisable sans
retargeting manuel lourd**, et de toute façon insuffisant seul (une pose
statique, pas une séquence d'action).

## Applications MikuMikuDance (les deux .zip)

Ce ne sont **pas des assets** mais l'installeur de l'application MikuMikuDance
v9.32 (英語版/version anglaise), téléchargé en double (deux noms de fichiers
différents, contenu quasi identique). Utile uniquement si le pipeline a
besoin de l'application elle-même (visualisation/édition MMD native) — pour
l'import Blender du contenu PMD, l'addon `mmd_tools` suffit (voir
`DOCS/MD/TEST_MMD_BLENDER_IMPORT.md`), l'application MMD n'est pas requise.
Les modèles `.pmd` qu'ils contiennent (Miku, KAITO, MEIKO, Rin/Len, Luka,
Haku, Neru) sont les **modèles Vocaloid par défaut de l'installeur** (dates
de fichier 2013-2014), pas des téléchargements liés au projet — utiles
uniquement comme cas de test pour valider le pipeline PMX/PMD → Blender (voir
tâche B), pas comme asset de production.

## Verdict global

| Catégorie | Utilisable tel quel | Nécessite rig/retargeting | Inutilisable |
|---|---|---|---|
| Goku/Vegeta FBX (11 fichiers) | ✅ | — | — |
| Miku Project Sekai FBX | ✅ (hors périmètre DBZ) | — | — |
| `gokutisana5ssj.pose` | — | — | ✅ (pose isolée, rig incompatible) |
| PMD Vocaloid bundle MMD | ✅ (comme cas de test pipeline) | — | — (pas pour la démo DBZ) |
| OBJ/DAE Goku/Vegeta | — | Redondants avec FBX | — |
| Applications MMD (2 zip) | ✅ (outil, pas asset) | — | — |

**Aucun asset spécifique au personnage DBZ n'a d'animation ou de séquence de
mouvement associée** — voir `DOCS/MD/AUDIT_ANIMATIONS_MMD.md` pour le détail
et la recommandation Tâche C.

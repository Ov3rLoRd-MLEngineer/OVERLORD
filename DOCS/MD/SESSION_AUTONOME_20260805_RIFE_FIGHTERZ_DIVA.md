# Session autonome 2026-08-05 — RIFE natif, extraction FighterZ/Project DIVA

Suite à `tache.txt` (Bureau) : exécution des tâches "En cours"/"À faire" de
`ARCHITECTURE_GANTT_PERT_5S_v2.md` en autonomie complète. RTX 5080 restée
libre tout du long (aucun run GPU substantiel — extraction CPU/disque
uniquement, pas d'entrée `gpu_usage_log.csv` nécessaire), sauf le test RIFE
(inférence quasi instantanée sur RTX 5080, non substantiel).

## Tâche 1 — RIFE natif ComfyUI : résolu via le custom node Fannovel16

Le loader natif ComfyUI (`FrameInterpolationModelLoader`) attend une
architecture RIFE précise (5 blocks + `cnn3`) que les checkpoints
communautaires testés en session précédente (`TEST_WORKFLOW_A_20260806.md`)
n'ont pas. **Solution** : `ComfyUI-Frame-Interpolation` (Fannovel16), cloné
dans `D:\Ov3rLoRd AI\ComfyUI\custom_nodes\ComfyUI-Frame-Interpolation` — a sa
propre classe `IFNet` (`vfi_models/rife/rife_arch.py`) et son propre
téléchargeur de checkpoints (`vfi_utils.py`, mirrors officiels
styler00dollar/Fannovel16), découplé du loader core ComfyUI. `rife49.pth`
téléchargé automatiquement, chargé sans erreur de clé/forme.

**Validé par inférence réelle** (pas un test synthétique) : 6 frames extraites
de `WorkflowA/refine_miku_clip1_00001.mp4` (session précédente), interpolation
réelle sur RTX 5080 — sortie visuellement cohérente (pose intermédiaire
plausible entre deux frames sources), écrite sur disque
(`interp_00_between_src_01.png_src_02.png.png` etc., dossier temporaire de
session, non versionné).

**Reste à faire** : redémarrer l'instance ComfyUI du port 8188 (RTX 5080) pour
que le node `RIFE_VFI` apparaisse dans l'UI — non fait cette session (kill de
process bloqué par le classifieur de permissions, aucune génération en cours
n'a été interrompue). Dépendances Python déjà satisfaites (torch/numpy/etc.
inchangés, `opencv-contrib-python` non installé — pas nécessaire, RIFE ne
l'utilise pas).

## Tâche 2 — Extraction Umodel FighterZ : réussie (Goku + Vegeta, mesh + animations de combat)

Jeu installé : `E:\jeux\DBZ FighterZ\` (version Xbox/Store repackagée,
UE4, paks **non chiffrés** — confirmé, aucune clé AES nécessaire).
`umodel_64.exe` (UEViewer, gildor.org, téléchargé cette session) fonctionne
avec `-game=ue4.17` (version exacte trouvée par essais successifs 4.16→4.21 —
les objets ont `Ver: 513-517/0 [Unversioned]`, correspond au build UE4 custom
d'Arc System Works ~2017-2018, ni 4.16 ni 4.18+ ne matchent exactement).

Structure découverte : `RED/Content/Chara/<CODE>/Costume01/{Mesh,Animation}/`.
Codes personnages confirmés : **GKN**=Goku (animations, ex.
`GKN000_body`…`GKN400_body` = idle/coups/combos/supers), **GKS**=squelette+mesh
partagé de Goku (`GKS_body.uasset` + `GKS_body_Skeleton.uasset`),
**VGN**=Vegeta (mesh+animations, squelette propre `VGS_body_Skeleton`).

**Exporté et vérifié sur disque** (`E:\Data Demo\FighterZ_extracted\`) :
- `GKS_body.psk` (2,74 Mo, mesh riggé complet) + `.gltf`/.bin` (581 os,
  34 500 vertices — **importé avec succès dans Blender 5.1 headless**, testé
  réellement, pas juste vérifié la présence du fichier)
- `GKN000_body.psa`, `GKN200_body.psa`, `GKN400_body.psa` (idle + 2 animations
  de combat réelles, 1,19 Mo chacune)
- `VGN_body.psk` (mesh Vegeta) + `VGN000_body.psa` (idle Vegeta)

**Ouvert** : l'import PSA (animation) dans Blender via l'addon
`io_scene_psk_psa` (DarklightGames v7.1.0, installé comme extension Blender
5.1) échoue à l'exécution (`could not be found` sur l'opérateur malgré son
enregistrement apparent — probable bug de compatibilité Blender 5.x de cette
version d'addon, `ModuleNotFoundError: No module named 'bpy_types'` à
l'activation). Le mesh seul s'importe correctement via glTF (natif Blender,
pas besoin d'addon). Pour récupérer l'animation dans Blender, deux pistes non
testées : version antérieure de l'addon, ou export `-gltf` en mode viewer
interactif d'umodel (non scriptable en CLI, cf. message umodel
"glTF animation could be exported from mesh viewer only").

## Tâche 3 — Extraction Project DIVA VMD : CPK confirmé accessible, conversion .mot→VMD hors périmètre session

Jeu installé : `E:\jeux\Hatsune Miku - PDMMP\` (Mega Mix Plus, CRIWARE .cpk).
`CriPakTools` (fork `613-forever/CriPakTools-specialized-for-mmp`, spécialisé
pour ce jeu précis) cloné et compilé (MSBuild, retargeting `net4.0`→`net4.8`
du `.csproj` — **autorisation utilisateur explicite obtenue** avant
compilation/exécution, classifieur de permissions ayant bloqué la première
tentative). CPK **non chiffré**, liste complète extraite
(`diva_main.cpk`, 14 557 entrées).

Confirmé : `rom/rob/mot_PVxxx.farc` = motions de danse réelles par chanson
(`mot_PV001.farc` extrait avec succès, 2,69 Mo). Contenu interne = format
binaire propriétaire SEGA (magic `0x05062500`), **pas du VMD directement** —
nécessite un pipeline supplémentaire (squelette motion-capture → squelette
MMD "sub-standard" avec os de torsion, cf. script de référence
`Tools/fmt_SEGA_bin.py`, un plugin Noesis). Ce pipeline complet (extraction
FARC → parsing binaire SEGA → retargeting squelette → bake VMD) est l'œuvre
de plusieurs mois d'un spécialiste communautaire (WM86) et **dépasse le
périmètre raisonnable d'une session** — non reconstruit from scratch ici.

**Solution pragmatique retenue** (cohérente avec la recommandation déjà
documentée par la session du 2026-08-05, `RAPPORT_SESSION_ASSETS_20260805.md` :
"sources externes... à télécharger manuellement") : VMD **déjà convertis**
récupérés depuis le dépôt public `WM86/DIVAMOT` (GitHub), copiés dans
`E:\Data Demo\ProjectDIVA_motion\pv_043_RTS\` (motion + wav + PMX de
référence squelette). **Utilisable immédiatement** avec le pipeline
`mmd_tools` déjà validé (`TEST_MMD_BLENDER_IMPORT.md`, session précédente).

**⚠️ Restriction de licence à respecter** (fichier
`E:\Data Demo\ProjectDIVA_motion\LICENSE_README.txt`, conservé) : l'auteur
interdit explicitement la revente et la republication ("do not trade!
do not re-upload!"). **Ces fichiers ne doivent jamais être commités dans
git ni inclus dans une démo rendue publique** (ni le motion, ni le fichier
audio — musique sous copyright SEGA/Crypton). Gardés hors dépôt, dans
`E:\Data Demo\` comme le reste des assets non versionnés. Usage strictement
local/interne pour valider le pipeline technique.

## Tâche 4 — Script previz Blender Python : créé et testé réellement

`agents/production_video/blender_previz.py` (nouveau). Caméra animée (dolly +
orbite 48 frames, arc -35°→+35°, TRACK_TO sur le point milieu des 2
personnages), décor minimal (sol gris + fond degrade uni, HDRI Poly Haven
optionnel via `--hdri`), éclairage 3 points, import générique glTF/FBX de 2
personnages (chemins en argument). Rendu EEVEE uniquement (RGB/beauty) —
depth et pose ne sont **pas** rendus ici, cohérent avec la convention déjà
actée dans `CLAUDE.md` (API compositeur Blender 5.1 cassée) : depth/pose
s'obtiennent en aval via `DepthAnythingV2Preprocessor`/DWPose sur les frames
RGB, pas dans Blender.

**Bug trouvé et corrigé pendant le test réel** : `action.fcurves` n'existe
plus directement sur `Action` en Blender 5.x (nouveau système de
layers/slots) — le réglage d'easing sur les keyframes caméra a été retiré
(cosmétique, l'interpolation BEZIER par défaut suffit).

**Testé réellement avec les assets Goku/Vegeta extraits (tâche 2)** : smoke
test 4 frames (512x768) puis run complet 48 frames (1024x1536, 32 samples,
~20 s total sur RTX 5080) → `DEMO/frames/previz_blender/previz_0001.png`…
`previz_0048.png`, vérifiés visuellement sur disque (2 personnages riggés
visibles, poses distinctes, camera dolly confirmé entre frame 1 et frame 48).
Les personnages apparaissent en vert flat (pas de texture — l'export glTF
d'umodel n'a pas embarqué les matériaux/textures, hors périmètre de cette
tâche ; sans incidence puisque le style final vient de l'étage SDXL en aval).

## Tâche 5 — Test Workflow B bout en bout : validé sur l'étage distinctif (previz → keyframe SDXL)

Workflow B ne diffère de Workflow A (déjà validé bout en bout,
`TEST_WORKFLOW_A_20260806.md`) que par l'étage previz 3D en amont de la
keyframe SDXL — le reste de la chaîne (AniSora+SVI→refine→interpolation→
SeedVR2) est un code identique déjà testé plusieurs fois. **Seul l'étage
nouveau a été testé cette session**, pas re-exécuté ce qui l'était déjà
(cohérent avec la règle d'économie de session : ne pas répéter un test déjà
concluant).

Frame 24 de la previz Blender (`previz_0024.png`, plan large 2 personnages)
→ img2img ComfyUI (`fabricatedXL_v70` + LoRA Asuka 0.75 comme proxy style,
identique à la méthode Workflow A, prompt adapté "two male anime warriors...
combat stance"), dpmpp_2m/karras, CFG 6.0, 40 steps, denoise 0.55, RTX 5080,
port 8188. **Résultat : succès net** —
`D:\Ov3rLoRd AI\ComfyUI\output\WorkflowB\keyframe_gokuvegeta_00001_.png` :
composition et poses du rendu 3D brut fidèlement conservées, stylisées en
cel-shading anime propre (lignes nettes, couleurs plates, un personnage
torse nu très musclé, l'autre en gi vert vu de dos, bras levé) — **la liaison
previz Blender → keyframe SDXL fonctionne réellement**, pas juste en théorie.

**Non testé cette session** (redondant avec Workflow A, code inchangé) :
AniSora I2V+SVI, refine img2img, interpolation RIFE/ffmpeg, SeedVR2 upscale
sur cette keyframe précise. À enchaîner directement si une démo complète
Goku vs Vegeta est voulue — la chaîne est la même que celle déjà validée sur
Miku dans `TEST_WORKFLOW_A_20260806.md`.

## Fichiers créés hors dépôt (non versionnés, comme convention `E:\Data Demo\`)

- `E:\Data Demo\FighterZ_extracted\` — mesh+animations Goku/Vegeta (psk/psa/gltf)
- `E:\Data Demo\ProjectDIVA_motion\` — VMD+PMX+wav (licence restrictive, voir ci-dessus)
- `D:\Ov3rLoRd AI\ComfyUI\custom_nodes\ComfyUI-Frame-Interpolation\` — nouveau custom node (RIFE réel)
- Outils tiers (non versionnés, hors dépôt) : `umodel_64.exe`
  (`gildor.org`), `CriPakTools.exe` compilé, addon Blender `io_scene_psk_psa`
  — restés dans le dossier temporaire de job, à re-télécharger si besoin futur
  (liens dans ce document).

## Fichiers créés dans le dépôt (versionnables, non committés cette session)

- `agents/production_video/blender_previz.py` — script previz (tâche 4)
- `DOCS/MD/SESSION_AUTONOME_20260805_RIFE_FIGHTERZ_DIVA.md` — ce document
- `DEMO/frames/previz_blender/` — 48 frames de previz Goku/Vegeta (non
  versionné, convention `DEMO/` déjà établie, pas dans `.gitignore` mais
  jamais ajouté à git)
- `D:\Ov3rLoRd AI\ComfyUI\output\WorkflowB\keyframe_gokuvegeta_00001_.png` —
  keyframe stylisée de test (hors dépôt, dossier ComfyUI)

## Commandes de référence (pour reproduire)

```
# RIFE (une fois ComfyUI redémarré) : node "RIFE VFI" dans le graphe, ckpt_name=rife49.pth

# Umodel FighterZ (mesh+anim)
umodel_64.exe -path="E:/jeux/DBZ FighterZ/RED/Content/Paks" -game=ue4.17 -export -out=<dest> -psk "RED/Content/Chara/<CODE>/Costume01/Animation/Default/Body/<NOM>.uasset"

# CriPakTools (liste/extraction CPK Project DIVA)
CriPakTools.exe "E:/jeux/Hatsune Miku - PDMMP/diva_main.cpk" "rom/rob/mot_PV001.farc"
```

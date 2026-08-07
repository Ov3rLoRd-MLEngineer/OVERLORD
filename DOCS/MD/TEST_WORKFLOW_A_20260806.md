# Test Workflow A — SDXL → AniSora+SVI → refine → AnimateDiff → RIFE+SeedVR2 (2026-08-05/06)

Session autonome, suite à `consignes.txt` (Bureau) : test bout-en-bout du
Workflow A sur la séquence MMD trouvée dans `E:\Data Demo\à trier\` (voir
audit ci-dessous), sur RTX 5080 (port ComfyUI 8188).

## Source : audit `E:\Data Demo\à trier\`

Nouvelle sous-arborescence apparue depuis l'audit `AUDIT_ASSETS_E_DATA_DEMO.md`
de la session précédente. 16 archives extraites (7-Zip). Contrairement à
l'audit précédent, **cette fois des VMD réels et des PMX de personnage sont
présents** :

### Modèles PMX exploitables
- `Tsatou式初音ミク_ver.1.00.pmx` — Miku, modèle bien connu, rig standard MMD
  complet. **Retenu pour ce test.**
- `Tsatou_Rock Cat Miku_Ver.1.00.pmx`, `Tsatou式初音ミク_熊猫豆沙包.pmx` — variantes Miku
- `Ruruka_magic_big/small.pmx` (Tears of Themis, 森亜るるか)
- `Dance hall.pmx`, `London Pier.pmx` — stages/décors, pas des personnages

### VMD — durée et postures (analysées via parseur binaire VMD dédié, `vmd_info.py`)

| Fichier | Frames (30fps) | Durée | Postures |
|---|---|---|---|
| `Look at my muscle.vmd` | 156 | **5.2 s** | idle → flex bras → idle (retenu) |
| `I must pee pee.vmd` | 165 | 5.5 s | idle → agitation → idle |
| `Smell yumi.vmd` | 138 | 4.6 s | — |
| `Salvadora da dance.vmd` | 333 | 11.1 s | dense, dansé |
| `Motion.vmd` (Doodle Dance) | 338 | 11.27 s | dense, dansé |
| Reactions courtes (Cry, exciting, scared) | 79-114 | 2.6-3.8 s | — |
| Poses (Pose Pack 27/28/38, `.pose` root) | — | 0 s (poses statiques) | non retenues |
| Caméras (Catch Catch, LADY CRAZY, JoyPolis) | — | — | camera/lighting only, pas des motions personnage |

**Aucun motion de combat DBZ-style trouvé** (confirmé prévisible dès l'audit
assets précédent) — mais **"Look at my muscle.vmd" correspond exactement au
gabarit demandé** : 5,2 s, structure idle → posture distincte → idle
(équivalent à "idle → attaque → recovery"). **Aucun téléchargement externe
nécessaire** malgré la carte blanche accordée — le contenu local suffisait.

### Validation pipeline PMX+VMD → Blender

Import headless (`mmd_tools`, déjà installé/validé session précédente) :
PMX + VMD importés sans erreur bloquante (3 bones cosmétiques de cheveux
manquants sur 510, sans impact sur la pose corporelle). Action Blender
`"Look at my muscle_bone"`, plage 1-157, conforme au VMD.

## Étape 1 — Keyframe SDXL stylisée

Rendu Blender (EEVEE, éclairage 3 points, fond blanc, 1024x1536) de la frame
80 (posture "flex bras" médiane) → img2img ComfyUI (`fabricatedXL_v70` +
LoRA Asuka 0.75 comme proxy style, dpmpp_2m/karras, CFG 6.0, 40 steps,
denoise 0.55). **Résultat net** : stylisation anime cel-shading réussie,
pose et design Miku bien préservés. ~25 s de génération.

## Étape 2 — AniSora I2V + SVI

Workflow `anisora_svi_shot.json` réutilisé tel quel (HIGH+LOW obligatoires,
ColorMatchV2 LAB bypass clip 1, CFG 1.5/Shift 8/8 steps Euler-simple, conforme
CLAUDE.md), seed neuf (583920174, différent des tests SVI précédents),
prompt adapté à Miku. 37 frames, 480x720, **195 s**. Résultat cohérent : le
personnage garde son design sur tout le clip, mouvement de bras plausible
en continuité de la pose d'ancrage (aucun drift visible, cf. comportement
SVI déjà documenté).

## Étape 3 — Img2img refine (ComfyUI)

Les 37 frames extraites (ffmpeg) puis rebatchées via `VHS_LoadImagesPath` →
img2img (même checkpoint/LoRA, denoise 0.3, CFG 5.0, 30 steps) → recombinées
en vidéo. **85 s**. Résultat : lignes plus nettes, détails affinés par
rapport à la sortie AniSora brute, design intact.

## Étape 4 — AnimateDiff (cohérence temporelle) — **dégrade le résultat**

Passe img2img (denoise 0.35) sur les 37 frames raffinées, modèle
`mm_sdxl_v10_beta.safetensors` (`ADE_AnimateDiffLoaderGen1`) + fenêtre de
contexte (`ADE_AnimateDiffUniformContextOptions`, context_length=16,
overlap=4 — **nécessaire** : sans cette fenêtre, le modèle plafonne à 32
frames et rejette un batch de 37 avec une erreur explicite). **95 s.**

**Constat direct à l'inspection visuelle** : la passe introduit un artefact
de **dédoublement de trait / fantôme** sur les bras (lignes de contour
doublées, léger halo chromatique), plus visible que sur la sortie de
l'étape 3. Cohérent avec le constat déjà documenté sur AnimateDiff dans
`COMPARAISON_ANIMATEDIFF_VS_ANISORA.md` (comportement non déterministe,
halo/artefact). **Dans ce rôle de "passe de cohérence" sur des frames déjà
générées, AnimateDiff dégrade plutôt qu'il n'améliore** sur ce test.

## Étape 5 — RIFE + SeedVR2

### Blocage RIFE natif ComfyUI, contourné

Le node natif `FrameInterpolationModelLoader`/`FrameInterpolate` de ComfyUI
(implémentation core, pas un custom node tiers) attend une architecture RIFE
précise (5 blocks + module `encode` avec `cnn3`, détection via
`detect_rife_config`). **Deux checkpoints communautaires téléchargés**
(`rife49.pth` puis `rife47.pth`, mirrors HuggingFace
`Isi99999/Frame_Interpolation_Models` et `MachineDelusions/RIFE`) se sont
révélés être une **architecture différente** (4 blocks, `encode.0/1` simple,
sans `cnn3`) — rejetés par le loader avec `ValueError: Unrecognized frame
interpolation model format`. Les deux fichiers supprimés après vérification
(inutilisables, pas de perte réelle).

**Contournement retenu, à signaler explicitement** : `ffmpeg minterpolate`
(mode `mci`/`aobmc`, motion-compensated) pour doubler le frame rate
(8→16fps, 37→71 frames) **à la place de RIFE**. Ce n'est **pas** un
équivalent qualitatif (flux optique classique, pas un modèle appris) — un
vrai RIFE (checkpoint compatible à retrouver, ou passer par le custom node
tiers Fannovel16 avec son propre chargeur) resterait supérieur pour une
version de production. Résultat fonctionnellement correct (frames
interpolées correctement alignées, pas d'artefact de duplication) mais
qualité d'interpolation inférieure à ce qu'aurait donné RIFE.

### SeedVR2 upscale

Premier essai `resolution=1536, batch_size=71` (tout en un batch) → **OOM**
("Allocation... Device limit 15.92 GiB, Free 0 bytes") sur RTX 5080. Repli
`resolution=960, batch_size=24` (batching interne automatique via
`uniform_batch_size=True`) → succès, **120 s**, sortie 960x1440, 71 frames,
16fps, 4.44 s. VRAM libérée correctement après l'OOM (vérifié
`nvidia-smi` avant relance, aucune action manuelle nécessaire).

## Comparaison directe — avec vs sans l'étape AnimateDiff

Un second passage complet (interpolation + SeedVR2) a été fait **en sautant
l'étape 4** directement depuis la sortie de l'étape 3 (refine), pour isoler
l'effet d'AnimateDiff sur le résultat final.

| | Avec AnimateDiff (chaîne complète) | Sans AnimateDiff (refine → interp → upscale) |
|---|---|---|
| Netteté des lignes | Dédoublement/fantôme visible sur les bras | Net, ligne unique, cel-shading propre |
| Artefacts couleur | Léger halo chromatique | Absent |
| Cohérence design | Bonne | Bonne (identique) |
| Flou de mouvement mains | Présent (amplifié par l'artefact fantôme) | Présent mais normal (mouvement rapide, pas un défaut) |

**Verdict net : la version sans AnimateDiff est visuellement supérieure.**

## Verdict global Workflow A

**Concluant techniquement sur toute la chaîne** (les 5 étapes s'exécutent
sans blocage, avec un contournement documenté pour RIFE) mais **le résultat
final le plus propre s'obtient en sautant l'étape 4 (AnimateDiff)** :

```
Keyframe SDXL → AniSora I2V+SVI → img2img refine → interpolation → SeedVR2 upscale
                                        (AnimateDiff en option dégradante, pas recommandee ici)
```

Fichiers produits (`D:\Ov3rLoRd AI\ComfyUI\output\WorkflowA\`) :
- `sdxl_keyframe_miku_00001_.png` — étape 1
- `svi_miku_clip1_00001.mp4` — étape 2
- `refine_miku_clip1_00001.mp4` — étape 3
- `animatediff_coherence_clip1_00001.mp4` — étape 4 (non recommandée)
- `final_miku_interp_seedvr2_00001_.mp4` — chaîne complète avec AnimateDiff
- `final_miku_norefine_seedvr2_00001_.mp4` — chaîne sans AnimateDiff (**meilleur résultat**)

## Ce qui reste ouvert

1. **RIFE réel non testé** — checkpoint compatible avec le loader natif
   ComfyUI non trouvé sur les mirrors essayés ; `ffmpeg minterpolate` utilisé
   en substitut fonctionnel mais qualitativement inférieur. Piste : le
   custom node tiers Fannovel16 (son propre système de téléchargement/mirrors
   documentés dans son wiki) ou trouver un checkpoint 5-blocks/`cnn3`
   correctement identifié.
2. **Pourquoi AnimateDiff dégrade ici** non diagnostiqué en profondeur —
   cohérent avec le comportement non déterministe déjà documenté, pas
   d'investigation supplémentaire dans le périmètre de cette tâche.
3. **Un seul test, une seule seed par étape** — pas de répétition pour
   vérifier la reproductibilité de l'artefact AnimateDiff.
4. **Motion "Look at my muscle" reste comique/générique**, pas un vrai motion
   de combat — si le Bloc 2 (DBZ FighterZ) reprend ce pipeline, il faudra
   soit ce même motion (proxy), soit une vraie motion combat retargetée
   (Mixamo ou MMD dédiée, cf. `AUDIT_ANIMATIONS_MMD.md` session précédente).

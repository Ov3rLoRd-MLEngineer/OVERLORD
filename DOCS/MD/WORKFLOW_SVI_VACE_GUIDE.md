# Guide — workflow SVI + VACE Fun Control (`anisora_svi_vace_full.json`)

Tâche 4, 2026-08-08. Ce document explique le workflow
`workspace/comfyui_workflows/anisora_svi_vace_full.json`, les décisions
d'architecture qui l'ont façonné, et ses limites actuelles honnêtes.

## Décision d'architecture : pourquoi ce n'est PAS AniSora + VACE

Demande initiale : combiner AniSora V3.2 + SVI LoRA + VACE Fun Control
(depth+pose) sur une seule chaîne. **Impossible tel quel** — investigation
complète avant d'écrire une seule ligne de JSON :

1. **Aucun split "device par node" pour VACE** (cf. `AUDIT_GPU_ALLOCATION.md`
   §2) — pas le blocage ici, juste rappel du contexte tâche 2/4.
2. **Les nodes VACE natifs de ComfyUI** (`WanVaceToVideo`,
   `Wan22FunControlToVideo`, dans `comfy_extras/nodes_wan.py`) exigent un
   checkpoint **entraîné** avec les canaux de contrôle VACE/Fun — un
   checkpoint standard (comme AniSora) ignore silencieusement ces entrées
   (`conditioning_set_values` stocke les clés mais rien ne les lit côté
   UNet non-VACE).
3. **Les fichiers "module" de Kijai** (`Wan2_2_Fun_VACE_module_A14B_HIGH/LOW`,
   ~3 Go chacun, mentionnés dans `PLAN_COHERENCE_TEMPORELLE_AOUT2026.md`) ne
   sont PAS des checkpoints autonomes — ce sont des patchs qui ne se
   chargent qu'via le node pack `ComfyUI-WanVideoWrapper` de Kijai
   (`WanVideoModelLoader` + `WanVideoVACEModelSelect`), absent de cette
   installation. Le loader natif de patchs de ComfyUI
   (`comfy_extras/nodes_model_patch.py::ModelPatchLoader`) ne reconnaît
   d'ailleurs pas ce format WAN VACE (seulement QwenImage/ZImage/SUPIR/
   MultiTalk).
4. **Le vrai chemin fonctionnel** (confirmé via l'exemple officiel
   `ComfyUI-WanVideoWrapper/example_workflows/
   wanvideo_2_2_Fun_control_example_03.json`) charge un checkpoint complet
   **Wan2.2-Fun-Control-A14B** (HIGH+LOW) — un fine-tune WAN2.2 différent
   d'AniSora, pas un module additif. AniSora et Fun-Control sont deux
   fine-tunes distincts du même backbone WAN2.2-I2V-A14B ; aucune variante
   publique ne combine les deux (recherché explicitement, rien trouvé).

**Décision retenue (validée avec l'utilisateur)** : construire la chaîne
réelle sur le backbone **Wan2.2-Fun-Control-A14B** (pas AniSora) + SVI LoRA
HIGH/LOW (compatible : même famille WAN2.2-A14B, LoRA générique non liée à
AniSora spécifiquement) + conditioning depth Mixamo réel. Le style
anime-spécifique d'AniSora ne s'applique pas sur cette chaîne précise — seul
le contrôle depth/pose + l'anti-drift SVI sont réels ici. `ComfyUI-WanVideoWrapper`
a été cloné dans `custom_nodes/` pour référence/R&D future mais **n'est pas
utilisé par ce workflow** : la version native ComfyUI (`UNETLoader` +
`Wan22FunControlToVideo`) reste dans le même écosystème de nodes que le
pipeline AniSora/SVI existant (`KSamplerAdvanced`, `ModelSamplingSD3`,
`LoraLoaderModelOnly`) — moins de risque de rupture que de tout recâbler
autour des nodes `WanVideoSampler`/`WanVideoModelLoader` de Kijai.

Checkpoint téléchargé : `Comfy-Org/Wan_2.2_ComfyUI_Repackaged`
(`split_files/diffusion_models/wan2.2_fun_control_{high,low}_noise_14B_fp8_scaled.safetensors`,
~14,3 Go chacun, ~28,6 Go total) → `models/diffusion_models/split_files/diffusion_models/`.
Choisi plutôt que les fichiers Kijai équivalents car c'est le repackaging
**officiel Comfy-Org**, garanti compatible avec les nodes natifs
`UNETLoader`/`Wan22FunControlToVideo` sans code additionnel.

## Ce qui est réellement câblé

```
UNETLoader (Fun-Control HIGH) ─→ LoraLoaderModelOnly (SVI HIGH) ─→ ModelSamplingSD3 (shift=8)
UNETLoader (Fun-Control LOW)  ─→ LoraLoaderModelOnly (SVI LOW)  ─→ ModelSamplingSD3 (shift=8)
CLIPLoader (umt5_xxl) ─→ CLIPTextEncode positive/negative
VAELoader (wan_2.1_vae)
LoadImage (keyframe reference, anisora_style_anchor_keyframe.png) ──┐
VHS_LoadImagesPath (DEMO/frames/mixamo_depth, control_video) ───────┼─→ Wan22FunControlToVideo
                                                                     ┘   (ref_image + control_video)
    ↓ positive/negative/latent
KSamplerAdvanced HIGH (steps 0→4, add_noise=enable)
    ↓
KSamplerAdvanced LOW  (steps 4→10000, add_noise=disable)
    ↓
VAEDecode → ColorMatchV2 (LAB, ref=keyframe) → VHS_VideoCombine
```

## Paramètres (expliqués)

| Paramètre | Valeur | Pourquoi |
|---|---|---|
| CFG | 1.5 | Valeur SVI recommandée (`PLAN_COHERENCE_TEMPORELLE_AOUT2026.md`) — un CFG classique (7-8) sur-contraint avec SVI actif |
| Shift (ModelSamplingSD3) | 8.0 | Idem, valeur SVI validée sur les tests 2026-08-04/05 |
| Steps totaux | 8 (4 HIGH + 4 LOW) | Dans la fourchette 6-8 demandée ; split identique au pattern déjà prouvé (`anisora_svi_shot.json`) |
| Sampler / scheduler | euler / simple | Pattern SVI existant, pas de raison de dévier |
| Seed | À changer par clip | **Obligatoire** (ADR/CLAUDE.md) — `noise_seed` codé en dur à `111111111` dans le fichier sauvegardé, à patcher par clip avant soumission (même logique que `agent_supervisor_v2.py`, seeds = `base_seed + i*137`, ADR-008) |
| control_video | `DEMO/frames/mixamo_depth/` (37 frames dispo) | Seule séquence Mixamo multi-frame réellement présente sur disque (voir limite ci-dessous) |
| ColorMatch | LAB (`reinhard_lab_gpu`), strength 1.0 | Convention établie CLAUDE.md — LAB systématique, jamais RGB |

## Limite honnête : pose non câblée (depth seul pour l'instant)

`Wan22FunControlToVideo` n'accepte qu'**un seul** flux `control_video` — pas
un slot depth + un slot pose séparés. Combiner les deux demande de les
composer en amont (ex. squelette dessiné en surimpression sur la depth map).
Recherche des assets Mixamo existants (2026-08-08) :

- `DEMO/frames/mixamo_depth/` — 37 frames depth réelles, **utilisées** ici.
- `DEMO/frames/video_3min_guides/clipNN_openpose.json` — keypoints réels,
  mais **un seul par clip** (keyframe), pas une séquence 37 frames alignée
  sur `mixamo_depth`.
- `DEMO/frames/{mixamo_raw,openpose_synthetic,skeletons_1024x1024,
  previz_blender,previz_shots_*,mmd_miku_pose}/` — tous **vides** au moment
  de cet audit (nettoyés en session précédente).

Aucune séquence pose 37-frames alignée sur les mêmes frames que
`mixamo_depth` n'existe actuellement. Composer un control_video depth+pose
correct nécessiterait un nouveau rendu Blender (même rig/caméra que
`mixamo_depth`) suivi d'une extraction DWPose (`pose_generator.py`) — non
fait ici pour ne pas ouvrir un chantier Blender non prévu dans cette tâche.
**Prochaine étape documentée, pas exécutée** : régénérer le rendu RGB de la
même animation Mixamo, extraire les squelettes via `pose_generator.py`,
composer depth+pose (ex. squelette en surimpression, alpha ~0.5) avant de
les charger dans `VHS_LoadImagesPath`.

## Smoke test (8 frames) — résultat réel, 2026-08-08

Testé avec `length=8`, `VHS_LoadImagesPath.image_load_cap=8` (patch
temporaire avant soumission — le fichier sauvegardé reste la version
"cycle complet" 37 frames). Soumis à l'instance 8188 (5080) après
téléchargement des deux checkpoints (~28,6 Go, `models/diffusion_models/
split_files/diffusion_models/`).

**Résultat : succès.** Graphe accepté et exécuté en 110 s, sortie
`Anisora Test/svi_vace_smoke/svi_vace_smoke_00001.mp4` (480×720, 8 fps).
Frames 0 et 4 inspectées visuellement : personnage cohérent (cheveux
orange, hoodie noir, jean bleu, sneakers rouge/blanc — conforme au
prompt), pose de course différente entre les deux frames (mouvement réel,
pas une image statique dupliquée), fond blanc propre, aucun artefact
visible.

**Point technique découvert (pas un bug)** : la sortie contient **5
frames**, pas 8. La VAE WAN compresse temporellement selon la formule
`((length-1)//4)+1` frames latentes, puis décode `(latent-1)*4+1` frames en
sortie — `length=8` donne 2 frames latentes → 5 frames décodées. `length=37`
(utilisé partout ailleurs dans ce dépôt, ADR-008) est un choix délibéré
car il fait un aller-retour exact par cette formule (37 → 10 latents → 37
frames). Pour un futur smoke test à frame-count exact, préférer une valeur
`4k+1` (5, 9, 13...) plutôt que 8. N'affecte pas la validité du test : le
graphe, le checkpoint, le LoRA SVI et le control depth fonctionnent tous
réellement.

**Deux corrections faites en testant** :
- `unet_name` avec séparateurs `/` rejeté par `UNETLoader`
  (`value_not_in_list`) — ComfyUI liste les fichiers avec des `\` sous
  Windows ; corrigé dans le JSON sauvegardé.
- Aucune autre erreur de graphe (VACE/Fun-Control, SVI LoRA, ColorMatch,
  VHS_VideoCombine tous acceptés du premier coup après le fix de chemin).

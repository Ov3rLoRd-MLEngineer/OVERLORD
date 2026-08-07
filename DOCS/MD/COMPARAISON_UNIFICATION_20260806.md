# Comparatif pistes d'unification hi-res — A/B/C/D

*Session 2026-08-06, Priorité 5 de `ANNEXE_SESSION_CLAUDE_CODE_20260806.md`.*

## Statut : 4/4 pistes mesurées — comparatif complet

Première tentative (mêmes RAM ~11 Go/32, pas de souci mémoire) : le tout
premier appel API ComfyUI a fait entrer le serveur (port 8188, PID 15088)
dans un deadlock HTTP confirmé (process vivant, GPU idle, aucune réponse
pendant 15+ min, vérifié par 3 méthodes indépendantes). Redémarré sur
confirmation explicite de Jérémy (règle du dépôt sur les process GPU
respectée — pas de redémarrage unilatéral). Après redémarrage, les 3 pistes
manquantes (A, B, D) ont tourné sans accroc : 30 générations (10 frames ×
3 pistes), **0 erreur**, 1878 s (31,3 min) de calcul GPU réel sur la
RTX 5080 (loggé `gpu_usage_log.csv`).

## Frames de référence sélectionnées

10 frames réelles (pas de synthèse) extraites du run SVI Workflow A déjà
validé : `D:\Ov3rLoRd AI\ComfyUI\output\WorkflowA\refine_frames_extracted\`
(37 frames disponibles), échantillonnées uniformément tous les ~4 frames :

```
frame_00001, frame_00005, frame_00009, frame_00013, frame_00017,
frame_00021, frame_00025, frame_00029, frame_00033, frame_00037
```

Copiées pour référence reproductible dans
`DEMO/frames/comparaison_unification_ref/` (10 fichiers PNG).

## Protocole des 4 pistes (à exécuter dans l'ordre A→B→C→D sur les mêmes frames)

| Piste | Méthode | Paramètres | Référence technique |
|---|---|---|---|
| A | ColorMatch LAB pré-hi-res | `ColorMatchV2`, méthode `reinhard_lab_gpu`, image_ref = keyframe SDXL d'origine | Déjà validé en prod pour l'inter-clips SVI (cf. règle permanente CLAUDE.md "ColorMatch (KJNodes) inter-clips : toujours LAB") — ici testé en pré-traitement AVANT hi-res fix plutôt qu'inter-clips |
| B | ControlNet Tile sur frame SVI | `denoise` 0.35–0.45, checkpoint fabricatedXL_v70, VAE taesdxl (convention du dépôt) | Même branche hires déjà présente et validée dans `Advanced_QwenVL_V35_ORIGINAL.json` (cf. `postprod_inpaint.py` docstring) |
| C | Optical Flow warp RAFT sur frames hi-res | RAFT (à identifier : node ComfyUI dédié ou script externe — aucun node RAFT confirmé installé dans `custom_nodes/` à ce jour, à vérifier avant exécution) | Nouveau pour ce pipeline, pas de précédent validé dans le dépôt |
| D | OpenPose synthétique Blender injecté dans hi-res fix | Sortie de `agents/production_video/export_skeleton_openpose.py` (Priorité 3, opérationnel pour assets mmd) en entrée ControlNet OpenPose | Dépend de la Priorité 3 — utilisable dès maintenant pour un asset mmd (Miku), pas encore pour FighterZ/SAO (squelettes bind-pose only, cf. `ASSETS_INDEX.md`) |

## Métrique de comparaison prévue

Score ColorMatch inter-frames (delta moyen Lab entre frames consécutives
post-traitement, méthode déjà utilisée pour le drift SVI) + inspection
visuelle (netteté, cohérence de silhouette/couleur). Pas de métrique DINOv2/
HSV automatisée cette session (cf. §10 `ARCHITECTURE_GANTT_PERT_5S_v2.md`,
prévu "post-démo").

## Pré-requis avant exécution (prochaine session)

1. Vérifier la présence d'un node RAFT dans `custom_nodes/` (piste C) — sinon
   soit installer `ComfyUI-Frame-Interpolation` (déjà présent pour RIFE, cf.
   `WAKE_UP_2026-08-06.md` point 2, à vérifier s'il inclut RAFT), soit
   substituer une alternative optical-flow disponible.
2. RAM système repassée sous ~20 Go libre pour absorber 4 runs ComfyUI
   séquentiels sans risquer le seuil de 28 Go.
3. Le bloc `[Ov3rLoRd] HiRes Fix` du workflow fusionné (Priorité 1, en cours
   cette session — voir état dans le handoff de session) peut servir de base
   commune aux pistes A/B/D une fois validé.

## Résultats mesurés (2026-08-06)

Scripts utilisés (conservés, jetables au sens où ils sont spécifiques à ce
comparatif) :
- `DEMO/run_comparaison_pistes_ABD.py` — pistes A/B/D via API ComfyUI (port
  8188), reprend le pattern `queue_prompt`/`wait_for_completion` de
  `DEMO/generate_svi_chain.py` et les paramètres checkpoint/VAE/upscale de
  `agents/production_video/postprod_inpaint.py::hires_fix_2k`.
- `DEMO/run_piste_C_raft_warp.py` — piste C, RAFT autonome (`python_embeded`).
- `DEMO/draw_openpose_skeleton.py` — génère l'image de conditionnement
  squelette pour la piste D à partir de
  `DEMO/frames/openpose_synthetic/mmd/miku/casual/frame_00001.json` (choisi
  par défaut faute de correspondance établie entre l'index de la capture mmd
  et les 10 frames SVI de référence — approximation documentée, pas une
  tentative de correspondance de pose fine).
- `DEMO/compute_colormatch_delta.py` — métrique delta E Lab (CIE76,
  `skimage.color.rgb2lab`) entre frames consécutives, 9 deltas / piste.

**Baseline (frames SVI brutes, aucun traitement)** : delta Lab moyen inter-frames
= **7.0751** (deltas par paire : 3.75, 5.87, 7.18, 8.60, 10.66, 9.21, 5.10,
6.65, 6.67). Sert de référence pour juger si une piste réduit ou non le
drift déjà présent dans la chaîne SVI.

| Piste | Statut | Score ColorMatch (delta Lab moyen) | vs baseline (7.0751) | Observation qualitative |
|---|---|---|---|---|
| A — ColorMatch LAB pré-hi-res | **RÉUSSI** | **6.7274** (deltas : 3.34, 5.29, 7.07, 8.53, 10.48, 8.62, 4.72, 6.31, 6.19) | **-4,9 %** (amélioration) | Vérifié visuellement (`piste_A/frame_00017.png`) : fond gris uniforme, fidèle à la frame source, pas d'artefact ni de dérive visible. Résultat cohérent avec l'attendu — c'est littéralement un correcteur de couleur, logique qu'il réduise le delta Lab inter-frames. |
| B — hi-res fix seul (UltimateSDUpscale, denoise 0.40) | **RÉUSSI** | **10.2666** (deltas : 7.50, 8.72, 10.44, 11.45, 13.41, 12.04, 8.95, 9.76, 10.12) | **+45,1 %** (dégradation nette) | Vérifié visuellement (`piste_B/frame_00017.png`) : plus net/détaillé que l'original, MAIS artefacts réels — texte fantôme halluciné en bas à droite du fond, teinte de fond qui dérive du gris neutre vers un violet/rose, petites hallucinations façon gouttes sur les vêtements. `denoise=0.40` (milieu de la plage 0.35-0.45 demandée pour ce test) est nettement plus élevé que le `0.16` utilisé en prod — le modèle régénère trop de contenu par tuile et introduit de la variance stochastique frame à frame, exactement ce que ce comparatif cherchait à détecter. |
| C — Optical Flow warp RAFT | **RÉUSSI** | **7.2055** (deltas : 3.51, 3.82, 6.27, 9.43, 11.10, 10.70, 7.33, 5.94, 6.76) | **+1,8 %** (neutre, non significatif) | Alignement spatial correct sur le corps/torse (silhouette stable), mais artefacts de traînée/fantôme nets sur les mains en mouvement rapide (échantillonnage épars, 1 frame/4). RAFT réaligne la géométrie, ne touche pas au grading colorimétrique — cohérent avec un score quasi inchangé. |
| D — OpenPose synthétique + hi-res fix | **RÉUSSI** | **10.4189** (deltas : 7.88, 9.00, 10.44, 11.68, 13.17, 12.33, 9.44, 9.77, 10.06) | **+47,3 %** (dégradation nette, pire que B) | Quasi identique à B (même branche hi-res, même `denoise=0.40`) — ajouter le conditionnement OpenPose (squelette Miku synthétique, `strength=1.25`) n'améliore PAS la cohérence colorimétrique par rapport à B seul ; il la dégrade même très légèrement. Le conditionnement de pose contraint la géométrie, pas la couleur — sans surprise au vu du constat piste C. |

## Verdict global : tranché

**Piste A (ColorMatch LAB) est la seule piste qui améliore réellement la
cohérence colorimétrique inter-clips** sur cet échantillon (-4,9 % vs
baseline), sans artefact visible. C'est aussi la moins chère en calcul (un
seul node, pas de re-génération SDXL).

**Pistes B et D (hi-res fix à `denoise=0.40`) dégradent nettement le score**
(+45 % et +47 %) et produisent des artefacts visuels réels (hallucinations,
dérive de teinte de fond) — confirmé visuellement, pas seulement chiffré.
**Nuance importante** : ce résultat est mesuré au `denoise=0.40` demandé pour
ce test (milieu de la plage 0.35-0.45), pas au `denoise=0.16` de la
configuration de production actuelle — il ne prouve pas que la branche
hi-res de prod dérive autant, seulement qu'à ce niveau de denoise plus
agressif, la dérive devient nette. Piste à retester à `denoise=0.16` si la
question se repose.

**Piste C (RAFT) est neutre sur l'axe couleur** — attendu, ce n'est pas son
rôle (réalignement géométrique, pas colorimétrique). Pourrait être combinée
à la piste A (correction couleur + réalignement spatial) plutôt que
comparée seule, hypothèse non testée cette session.

**Recommandation** : intégrer ColorMatch LAB (piste A) comme étage de
correction avant tout hi-res fix agressif, et éviter un `denoise` aussi
élevé que 0.40 pour la branche hi-res tant qu'un garde-fou colorimétrique
(type piste A) n'est pas en place en aval.

Sorties images : `DEMO/frames/comparaison_unification_ref/piste_{A,B,C,D}/`
(10 frames chacune, toutes réelles) ; `piste_D_skeleton.png` (image de
conditionnement OpenPose).

# Pipeline de post-production frame par frame — 2026-08-06

Origine : `consignes.txt` (Bureau, relayé le 2026-08-06). Objectif : corriger
systématiquement mains/pieds et hi-res-fixer chaque frame des sorties du
Workflow A (`DEMO/output/miku_demo_30s_v*.mp4`, cf. `DEMO_30S_MIKU_20260806.md`)
sur la RTX 5060 Ti, en parallèle de la génération SVI continue sur la RTX 5080
(`DEMO/run_demo_loop.py`), en constituant au passage un dataset candidat pour
un futur LoRA de personnage.

## 1. Bug cube Blender par défaut

Voir `DOCS/MD/BUGFIX_BLENDER_CUBE_DEFAULT.md` : déjà résolu par le code
existant (`clear_scene()` utilise `use_empty=True`), rien à corriger. Vérifié
visuellement sur un rendu previz réel (aucun cube, aucun objet résiduel).

## 2. Architecture du pipeline postprod

`agents/production_video/postprod_inpaint.py`, tourne sur une **2e instance
ComfyUI dédiée** (`_launch_comfyui_5060ti.bat`, port 8189, pinnée RTX 5060 Ti
par UUID GPU) pendant que le port 8188 (RTX 5080) reste réservé à la
génération SVI continue. `CUDA_VISIBLE_DEVICES=1` forcé en tête de script pour
tout l'inférence torch locale (YOLO mains, SAM HandSegNet/FootSegNet).

```
v1_fixed/v2/v3/... (24fps)
  -> extraction frames PNG (ffmpeg)
  -> easy imageRemBg (BEN2, ComfyUI) + add_background=white
     (recomposition fond blanc en un seul node -- corrige le blanc des yeux
     contaminé par un fond transparent/gris)
  -> HandSegNet : hand_yolov9c (bbox, multi-instance) -> SAM vit_b fine-tuné
     (masque + score par main, combinées par minimum pixel-a-pixel)
  -> FootSegNet : DWPose (bbox, via ComfyUI 8189) -> SAM vit_b fine-tuné
     (masque + score)
  -> inpaint main (si masque trouvé) : VAEEncodeForInpaint + IPAdapterAdvanced
     (image de référence = keyframe SDXL stylisée de l'itération, attn_mask
     restreint l'influence IPAdapter à la zone masquée) + KSampler
     (fabricatedXL_v70, denoise 0.45)
  -> inpaint pied (meme schema, prompt dedie), sequentiel apres le pass main
  -> hi-res fix 2K : UltimateSDUpscale (upscale_by=1.5, tuiles 512x512,
     dpmpp_2m_sde/karras, memes reglages que la branche hires deja validee
     dans Advanced_QwenVL_V35_ORIGINAL.json)
  -> sauvegarde PNG corrigee -> DEMO/postprod/frames_final/
  -> reassemblage MP4 (fonction disponible, pas encore invoquee en routine)
```

### Choix techniques et écarts par rapport à un pipeline idéal

- **Pas de LoRA de personnage appliqué à l'inpaint** (contrairement à
  `sdxl_keyframe_img2img.json` qui utilise la LoRA Asuka — non pertinente
  pour Miku). L'identité est portée uniquement par IPAdapter + la keyframe
  de référence. C'est un choix de portée assumé, pas un oubli : aucune LoRA
  Miku n'existe dans ce dépôt (le dataset produit ici sert justement à en
  entraîner une, cf. section 4).
- **VAE `taesdxl`** partout (ADR-002, `sdxl_vae` réel corrompu).
- **`easy imageRemBg` en mode `add_background="white"`** directement plutôt
  qu'un recompositing PIL manuel après coup : le node gère nativement la
  recomposition, plus simple et plus fiable que ré-implémenter la logique
  `_prepare_rgb` déjà utilisée ailleurs (handsegnet/footsegnet `infer.py`).
- **Deux passes d'inpaint séquentielles (main puis pied)**, pas une passe
  combinée : permet un score et un prompt dédiés par zone, et un flag
  `inpaint_applied` correct même quand une seule des deux zones est détectée.

## 3. Coordination GPU (rattrapage 5060Ti / 5080)

`DEMO/output/gpu_progress.json` (écrit par `run_demo_loop.py` après chaque
itération réussie) : `{svi_frames_available, svi_loop_done, last_run}`.

- **Ordre ascendant** (worker principal, 5060 Ti) : curseur mobile qui
  découvre dynamiquement les nouvelles vidéos `miku_demo_30s_v{N}[_fixed].mp4`
  apparues dans `DEMO/output/` (pas seulement une liste statique passée au
  lancement — sinon la notion de "rattrapage" n'aurait pas de sens sur un
  process long). Quand le curseur dépasse les frames disponibles et que la
  génération SVI n'est pas terminée (`svi_loop_done=False`) : écrit
  `DEMO/STOP_GENERATION.flag` puis attend (poll 30s par défaut).
- **`run_demo_loop.py`** vérifie `STOP_GENERATION.flag` en tête de boucle
  (donc après la fin de l'itération en cours, jamais en la coupant) : si
  présent, termine proprement, marque `svi_loop_done=True`, puis lance
  `postprod_inpaint.py --order desc` sur la RTX 5080 (fenêtre détachée,
  `CUDA_VISIBLE_DEVICES=0`) pour traiter le reste des frames en partant de la
  fin, à la rencontre du worker ascendant.
- **Ordre descendant** : instantané figé au lancement (pas de découverte
  dynamique — n'a de sens qu'une fois la génération arrêtée).

## 4. Cible dataset LoRA (14 400 frames) et candidat prioritaire

`run_demo_loop.py` compte les frames finales cumulées (ffprobe sur chaque
`miku_demo_30s_v{N}.mp4`) après chaque itération et arrête la boucle SVI dès
`>= 14400` frames (10 min @ 24fps), indépendamment de l'épuisement de la file
VMD (qui reste le 2e critère d'arrêt existant).

**Candidat `lora_priority` identifié par inspection visuelle directe**
(pas une heuristique automatique — confirmation demandée le cas échéant) :

- Vidéo : `DEMO/output/miku_demo_30s_v2.mp4`
- Fenêtre : **t≈17.5s → t≈19.0s**, transition clips 4→5 (plans "orbit
  around the character" — la caméra tourne autour du personnage)
- Constat : entre t=17.5s (tenue d'origine : veste peplum + cravate, jupe
  superposée) et t=19.0s (tenue différente : robe sans manches à nœud,
  jupe à volant unique, écouteurs visibles avec embout rose), la Miku change
  de tenue **pendant la rotation caméra** — correspond exactement à "le
  personnage se retourne avec changement de tenue" de la consigne. Couleurs
  restées cohérentes (palette teal/noir/gris préservée, pas de corruption).
  v1/v3/v4 échantillonnés en comparaison ne montrent pas ce phénomène aux
  mêmes points de mesure — semble spécifique à v2.
- Frame globale (à traiter) = `nb_frames(vidéos avant v2 dans l'ordre
  --videos) + round(17.5*24)` à `+ round(19.0*24)`, soit **≈420 à 456 en
  frames locales v2** (± quelques frames selon interpolation exacte).
- Outil de tag : `agents/production_video/tag_lora_priority.py --start N --end M`
  (marque `lora_priority=True` dans `postprod_log.csv` une fois la plage
  traitée par `postprod_inpaint.py`).
- **Limite assumée** : identification par échantillonnage visuel à 2
  images/vidéo puis bissection sur v2 uniquement — pas un balayage exhaustif
  des ~14 400 frames cibles (irréaliste en visionnage manuel). D'autres
  occurrences possibles sur v5+ ne sont pas couvertes par ce constat et
  devront être repérées au fil de l'eau si elles apparaissent.

## 5. Tests de validation

`py -3.12 agents/production_video/postprod_inpaint.py --videos
DEMO/output/miku_demo_30s_v1_fixed.mp4 --keyframe-ref <keyframe v2>
--out-dir DEMO/postprod_test --order asc --limit 1 --no-watch`

**Test 1** (avant correctif rattrapage) : bug trouvé et corrigé — sans
`gpu_progress.json` existant, l'ancienne logique de rattrapage se déclenchait
dès la frame 0 d'un test isolé (écriture indue de `STOP_GENERATION.flag`,
nettoyé). Corrigé par la réécriture en curseur mobile (section 3) : le
rattrapage n'est évalué qu'une fois les frames connues localement épuisées,
pas au premier tour.

Ce même test 1 a produit une frame complète (foot uniquement, aucune main
détectée sur la frame 0) : **369.8s bout-en-bout** pour une seule frame
(bg-removal + DWPose + SAM pied + inpaint pied + hi-res fix 2K). Inspection
visuelle du résultat : **bug critique trouvé**. `VAEEncodeForInpaint`
(`comfy_extras/nodes_mask.py`, calcul `m = 1 - mask.round()`, pixels
préservés où `m=1` c.-à-d. `mask=0`) attend en réalité **BLANC=zone à
effacer/régénérer, NOIR=zone à préserver** — l'exact inverse de la
"convention pipeline" du dépôt (NOIR=régénérer) utilisée par défaut dans
`handsegnet/footsegnet infer.py` et copiée depuis `inpaint_corrector.py`.
Résultat observé : tout le corps effacé (fond gris uniforme) sauf la petite
zone du masque (les bottes), au lieu de l'inverse attendu.

**Correctif** : appel de `generate_part_mask`/`generate_foot_mask` avec
`pipeline_convention=False` (BLANC=objet/zone cible, convention "ML" du
module) au lieu du défaut `True`, + combinaison multi-mains par
`np.maximum.reduce` au lieu de `np.minimum.reduce`.

**Tests 2-4** (après correctif) : trois tentatives de re-test se sont
terminées prématurément (`status: killed`, aucune trace d'erreur Python dans
les logs — la dernière meurt juste après l'avertissement `requests`, avant
même le premier appel réseau ComfyUI). Diagnostic : **RAM système quasi
totalement épuisée** — `Get-CimInstance Win32_OperatingSystem` : **0,3 à
1,7 Go libres sur 31,9 Go**. `Get-Process` identifie le processus ComfyUI
principal (port 8188, RTX 5080, `--lowvram`, PID 18828) comme responsable de
**~20,8 Go de RAM système à lui seul** (le mode `--lowvram` échange de la
VRAM contre de la RAM système — cohérent avec l'usage attendu, mais laisse
très peu de marge pour une 2e instance ComfyUI complète + torch/SAM/YOLO en
parallèle sur une machine à 32 Go).

**RAM système — constat affiné** : la RAM libre fluctue fortement selon la
phase de la boucle SVI (0,2-1,7 Go pendant la génération de clips SVI sur
8188, jusqu'à ~19-20 Go libres brièvement entre la fin d'une itération
(assemble) et le début de la suivante). Le pipeline postprod peut donc
s'exécuter **de façon opportuniste dans ces fenêtres**, pas en continu
pendant que 8188 génère activement. Pas de solution de contournement
appliquée (aucune action sur le process 8188) — juste une contrainte de
timing à respecter pour tout lancement manuel ou futur orchestrateur
combinant les deux pipelines.

**Test 5** (dans une fenêtre RAM favorable, ~19,5 Go libres, `--limit 1`,
frame 1 — frame 0 déjà loguée par le test 1 buggé) : **exécution complète
réussie**, plus de kill. Résultat : corps entier intact sur fond blanc,
mask polarity confirmée corrigée. Mais **2e bug trouvé** : les
pieds/bottes inpaintés apparaissaient comme un aplat gris quasi vide, sans
motif ni couleur (`INPAINT_DENOISE=0.45`, copié depuis `inpaint_corrector.py`,
beaucoup trop faible pour une zone **effacée** par `VAEEncodeForInpaint`
avant encodage — sans structure existante à préserver dans le masque, un
faible denoise ne laisse pas assez de pas de débruitage pour faire émerger
un motif, contrairement à un img2img classique où denoise=0.45 préserve
55% d'un contenu déjà présent).

**Correctif** : `INPAINT_DENOISE` porté à **0.90** (regeneration quasi
complète de la zone masquée, cohérent avec l'usage standard de
`VAEEncodeForInpaint`).

**Test 6** (nouvelle fenêtre RAM favorable, ~19,9 Go libres, `--limit 1`,
frame 0 re-testée après purge de `postprod_log.csv`) : **succès complet**.
Bottes correctement rendues (noir + liseré teal, fidèle au design d'origine),
corps entier intact, 2K net. Léger artefact de forme au niveau de la
semelle (bord irrégulier) — acceptable pour un pipeline automatique,
pas bloquant. Durée : **273,8s** pour une frame avec inpaint pied seul
(aucune main détectée sur les frames 0/1, cohérent avec la pose).

**Conclusion** : le pipeline est validé fonctionnellement de bout en bout
(bg-removal, masques SegNet, inpaint IPAdapter, hi-res fix 2K). L'exécution
**strictement en parallèle continu** avec la génération SVI reste contrainte
par la RAM système (fenêtres de ~15-20 Go libres uniquement entre
itérations, pas pendant) — un futur lancement à l'échelle devra soit
accepter ce fonctionnement par créneaux, soit être arbitré par Jérémy
(redémarrage 8188, mémoire virtuelle augmentée, ou fonctionnement
séquentiel complet), aucune décision unilatérale prise ici.

## 6. Limites connues / points d'attention

- **Coût GPU par frame** : **~274s mesurés** (test 6, résultat validé) pour
  une frame avec un seul passage d'inpaint (pied) + hi-res fix 2K (aucune
  main détectée sur les frames 0/1 testées -- estimation ~350-400s/frame
  avec les deux zones main+pied, non mesurée directement faute de frame de
  test avec main visible). Sur cette base, traiter 14 400 frames
  représenterait de l'ordre de **1100-1600h GPU cumulées** si chaque frame
  passe systématiquement par les deux zones + hi-res fix — un
  volume qui dépasse largement la fenêtre de la démo 30s initiale. À
  reconsidérer explicitement avec Jérémy avant de lancer un traitement à
  cette échelle (ex. limiter le postprod aux clips prioritaires identifiés
  section 4, plutôt que les 14 400 frames systématiquement).
- **RAM système** : voir section 5 — contrainte bloquante actuelle pour la
  validation en parallèle avec la génération SVI.
- `run_demo_loop.py` **redémarré proprement le 2026-08-06** (après la fin de
  l'itération v5 ; v6 venait tout juste de démarrer sa génération de clips,
  interrompue et relancée depuis zéro — coût minime, ~1 clip perdu). Le
  nouveau câblage `gpu_progress.json`/`STOP_GENERATION.flag`/cible 14 400
  frames est donc actif depuis cette relance ; `gpu_progress.json` sera écrit
  à la fin de l'itération v6 en cours.
- Réassemblage MP4 final (`reassemble_video()`) codé mais pas encore invoqué
  en routine dans `main()` — le pipeline s'arrête aujourd'hui aux PNG
  individuels dans `frames_final/`, à enchaîner manuellement ou dans une
  itération future une fois le débit/volume validés.

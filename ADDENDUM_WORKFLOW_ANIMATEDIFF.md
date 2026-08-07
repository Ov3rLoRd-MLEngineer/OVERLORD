# ADDENDUM_WORKFLOW_ANIMATEDIFF.md
# À ajouter au CONTEXTE_OVERLORD_V227.md
# Session nuit 2026-06-30 — validation workflow test AnimateDiff

---

## WORKFLOW DE TEST VALIDÉ — animatediff_sdxl_cn_test.json

### Paramètres confirmés fonctionnels (résultat "fond blanc propre")
```
VHS_LoadImages skeletons_1024x1024 :
  image_load_cap   : 0
  skip_first_images: 16  (frames 17-32 du cycle Mixamo)
  select_every_nth : 1

VHS_LoadImages mixamo_raw :
  image_load_cap   : 0
  skip_first_images: 16
  select_every_nth : 1

LineArtPreprocessor :
  coarse     : disable
  resolution : 512   ← IMPORTANT, pas 1536 comme supposé initialement

ADE_AnimateDiffLoaderGen1 (PAS Gen2, non dispo sur ce poste)
  model_name    : mm_sdxl_v10_beta.safetensors
  beta_schedule : autoselect

ControlNetApplyAdvanced (x2, OpenPose + Lineart)
  strength     : 1.25
  start_percent: 0.0
  end_percent  : 0.5

KSampler :
  seed     : 527494254591352 (fixed)
  steps    : 40
  cfg      : 6.5
  sampler  : euler_ancestral
  scheduler: normal
  denoise  : 1.0

EmptyLatentImage : 1024x1536, batch_size=16

Prompt positif : score_9, score_8_up, score_7_up, source_anime, masterpiece,
  highly detailed, 1girl, asuka shoryu langley, blue eyes, nike jordan sneakers,
  black hoodie, blue jeans, detailed clothing textures, side view, profile,
  full body, run, concentrated expression, pure white background

Prompt négatif : blurry, low quality, deformed, ugly, bad anatomy, bad eyes,
  bad hand, bad finger, extra limbs, watermark, text, logo, cartoon, anime,
  painting, 3d render, child, loli, overexposed, underexposed, plastic skin,
  gray background, dark background, gradient background
```

### ⚠️ COMPORTEMENT NON DÉTERMINISTE OBSERVÉ
Avec un JSON strictement identique (mêmes paramètres, même seed), deux runs
consécutifs ont donné des résultats différents :
- Run A : fond blanc propre, hoodie noir moins saturé, contrastes vêtements plus doux
- Run B : fond gris/cyan, hoodie noir totalement saturé, main gauche "tire" sur le jean

**Cause suspectée** : état mémoire résiduel de ComfyUI (cache CLIP/VAE/LoRA) qui
ne se réinitialise pas complètement entre les runs même sans changement de
paramètres visible dans l'UI ou le JSON exporté.

**RÈGLE DE PROCÉDURE ADOPTÉE** :
→ Toujours redémarrer ComfyUI complètement avant un run de comparaison
  scientifique entre deux configurations. Sinon les comparaisons ne sont pas
  fiables — l'état serveur peut différer silencieusement.
→ Documenter systématiquement : redémarré oui/non avant chaque run de test.

### Test en cours au moment de la pause
- `skip_first_images: 16` → `skip_first_images: 0` (frames 1-16 au lieu de 17-32)
- Objectif : déterminer si le fond gris est lié aux poses spécifiques de
  certaines frames (bras gauche près du bassin) ou à un problème de résolution
  LineArtPreprocessor (hypothèse initiale 1536 vs 512, infirmée — 512 est
  bien la valeur qui fonctionne, pas 1536).
- Résultat non encore obtenu au moment de la coupure de session.

---

## PROBLÈME IDENTIFIÉ — main gauche "tire sur le jean"

Sur les frames où le bras gauche de l'animation Mixamo "Running" passe près
du bassin (frames ~6-10 du cycle), fabricatedXL interprète à tort la position
comme "main qui tient/tire le jean" plutôt que "bras en mouvement de course".

**Vérifié** : ce n'est PAS un défaut du skeleton ni du lineart — les deux
montrent clairement la main dissociée du jean. C'est un biais purement
génératif du modèle (associations apprises depuis des millions d'images de
mode où cette posture = main sur la ceinture/poche).

**Pas de fix simple identifié.** Options à explorer plus tard :
- Tester une autre animation Mixamo avec mouvement de bras plus ample
- Retoucher manuellement les skeletons sur ces frames spécifiques (raccourcir
  le bras pour l'éloigner du bassin)
- Accepter et corriger en post (inpaint ciblé)

---

## QUESTIONS OUVERTES POUR PROCHAINE SESSION

1. Résultat du test `skip_first_images: 0` (frames 1-16) — fond blanc ou gris ?
2. Si le comportement non déterministe persiste après redémarrage systématique,
   investiguer plus profondément (version ComfyUI, extensions tierces qui
   gardent un état, ordre de chargement des modèles)
3. Comparer visuellement et choisir : préférence pour le rendu "fond blanc /
   hoodie moins saturé" (Run A) vs "fond gris / hoodie très saturé" (Run B) —
   le hoodie moins saturé semble donner un meilleur contraste de vêtements
   selon retour utilisateur, indépendamment du problème de fond
4. Reprendre les tests sur 32 frames sans IPA (l'OOM précédent venait de
   l'ajout IPA + VAEEncode, pas du nombre de frames lui-même)

---

*Ov3rLoRd — Addendum session nuit 2026-06-30*

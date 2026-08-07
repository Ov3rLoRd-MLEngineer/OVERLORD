# Test piste E — lineart N&B → recolorisation (2026-08-06)

Priorité 2 de `tache a faire.txt` (2026-08-06). Objectif : tester si une
déconstruction/reconstruction complète (extraction lineart → nettoyage →
recolorisation guidée par le keyframe SDXL → fusion) donne une meilleure
cohérence colorimétrique inter-frames que ColorMatch LAB seul (piste A,
validée `DOCS/MD/COMPARAISON_UNIFICATION_20260806.md`, 6.7274 vs baseline
7.0751, -4,9%).

## Pipeline testé

```
Frame SVI brute
    ↓
AnimeLineArtPreprocessor (comfyui_controlnet_aux)
    ↓
Nettoyage (cv2 : threshold + dilate sur les traits, PAS le fond — bug de
polarité corrigé en cours de session, voir section Incident ci-dessous)
    ↓
Recolorisation SDXL (fabricatedXL_v70 + taesdxl) :
  VAEEncode(lineart nettoyé) → KSampler denoise=0.85
  + ControlNet xinsir-controlnet-lineart-sdxl (strength=1.3, structure tenue
    tout du long) [+ IPAdapter Plus SDXL (image=keyframe, poids variable),
    charge manuellement CLIPVisionLoader("model.safetensors") +
    IPAdapterModelLoader plutot que IPAdapterUnifiedLoader (le seul preset
    testé ne trouvait pas le bon clip vision par nommage, cf. script)]
    ↓
Fusion multiply (image recolorisee x lineart nettoye, en Python/numpy)
    ↓
(E4 seulement) ColorMatchV2 LAB (image_ref=keyframe) — combinaison A+E
```

Script : `DEMO/run_piste_e_lineart.py`. 10 frames de référence identiques au
comparatif A/B/C/D (`DEMO/frames/comparaison_unification_ref/frame_000{01,05,09,...,37}.png`).

## Variantes

| Variante | IPAdapter | Poids | ColorMatch final |
|---|---|---|---|
| E1 | non | — | non |
| E2 | oui | 0.6 | non |
| E3 | oui | 0.9 | non |
| E4 | oui | 0.9 | oui (combinaison A+E) |

## Incident en cours de session : bug de polarité lineart (corrigé avant publication des résultats)

Premier run (669,4s, 40/40 générations "OK" API) : résultats **invalides**,
détectés par inspection visuelle (pas publiés tels quels) — `AnimeLineArtPreprocessor`
sort des traits **clairs sur fond sombre** (confirmé visuellement sur
`pisteE_lineart_raw_00001_.png`), pas l'inverse supposé initialement dans le
code. Le nettoyage (`inv = 255 - raw` AVANT le `cv2.dilate`) faisait donc
grossir le FOND (devenu clair après inversion) et rongeait les traits fins
jusqu'à quasi-disparition → image "nettoyée" quasi noire → `VAEEncode` partait
d'un canevas quasi noir, le `ControlNet` ne voyait quasi aucune structure, et
la fusion multiply finale noircissait le peu qui restait. Résultat : 4/4
variantes quasi identiques et quasi noires (delta Lab ~0.0006-0.0032, E4
~0.24 après correction ColorMatch) — un artefact du bug, pas une mesure de
cohérence réelle.

**Correctif** : seuiller/dilater directement dans la polarité native du
préprocesseur (traits = premier plan clair, cv2.dilate() les épaissit
correctement cette fois), une seule inversion finale pour obtenir la
convention "fond blanc / traits noirs" attendue en aval. Confirmé visuellement
(fond ~95% blanc, traits noirs préservés) avant relance complète.

Rappel méthodologique (déjà en mémoire long terme) : toujours vérifier qu'un
résultat "OK" côté API correspond à une sortie visuellement plausible avant
de publier une métrique — un statut HTTP 200 par génération ne garantit rien
sur le contenu produit.

## Résultats (après correctif, complétés session nuit 2026-08-06/07)

Les 5 frames perdues la première nuit par timeout de file ComfyUI partagée
(9, 13, 21, 29, 37 — toutes variantes — et 5/17/25/33 pour E4 seul) ont été
retraitées (`DEMO/retry_piste_e_missing.py`, ComfyUI dédié cette fois, 0
échec). Métriques calculées sur les 10 frames complètes via
`DEMO/compute_colormatch_delta.py` (étendu aux pistes E1-E4).

| Piste | Delta Lab moyen | vs baseline (7.0751) |
|---|---|---|
| Baseline (brut) | 7.0751 | — |
| A (ColorMatch LAB seul, référence) | 6.7274 | -4.9% |
| E1 (lineart seul, sans couleur) | 32.7880 | **+363%** |
| E2 (lineart + IPAdapter 0.6) | 53.1568 | **+651%** |
| E3 (lineart + IPAdapter 0.9) | 36.5167 | **+416%** |
| E4 (E3 + ColorMatch LAB) | 15.7012 | **+122%** |

Inspection visuelle (frame 9, `piste_E1` et `piste_E4`) confirme les chiffres,
ce n'est pas un artefact de métrique : **E1** produit un fond vert uni
aléatoire et des couleurs de peau/vêtements incohérentes (aucune source de
couleur sans IPAdapter, le modèle choisit librement à chaque frame) ; **E4**
(pourtant la meilleure variante piste E) reste très délavé, vignette
rose/violette parasite sur les bords, perte de saturation généralisée —
visuellement dégradé même après ColorMatch LAB final.

## Verdict piste E

**Rejetée.** La déconstruction/reconstruction complète (lineart → recolor
SDXL from-scratch denoise=0.85 → fusion) introduit largement PLUS de dérive
colorimétrique qu'elle n'en corrige, quelle que soit la variante — y compris
la meilleure combinaison (E4, IPAdapter 0.9 + ColorMatch LAB) qui reste
~2,2x pire que la simple frame brute non traitée. Cause probable : repartir
quasi de zéro (denoise=0.85) à chaque frame donne au sampler SDXL une large
liberté de réinterprétation par frame que ni IPAdapter (poids testés
jusqu'à 0.9) ni un ColorMatch final ne suffisent à discipliner. **Piste A
(ColorMatch LAB seul, déjà en production) reste la meilleure option
mesurée** parmi toutes les pistes testées (baseline/A/B/C/D/E1-E4) — cf.
`DOCS/MD/COMPARAISON_UNIFICATION_20260806.md` pour B/C/D. Ne pas réinvestir
dans cette direction sans changement structurel (ex. denoise beaucoup plus
faible, perdrait alors l'intérêt même de repartir du lineart).

## Comparaison préprocesseurs lineart (Priorité 5, session nuit 2026-08-06/07)

Objectif distinct de piste E ci-dessus : comparer `LineArtPreprocessor`
(modèle "réaliste") vs `AnimeLineArtPreprocessor` (déjà utilisé ci-dessus)
pour l'extraction de traits, avec nettoyage "technique scantrad" (levels/
threshold à 180, despeckle aire<8px, unsharp mask léger avant seuillage).
Mesure sur le lineart nettoyé lui-même (pas de recolor/fusion — piste E
ci-dessus a déjà montré que la chaîne recolor complète n'est pas viable ;
refaire un comparatif recolor x2 préprocesseurs n'aurait fait que payer deux
fois le même coût GPU pour la même conclusion). Script :
`DEMO/compare_lineart_preprocessors.py`.

| Préprocesseur | Delta Lab moyen (traits nettoyés) |
|---|---|
| LineArtPreprocessor (réaliste) | 5.7150 |
| AnimeLineArtPreprocessor | **1.4812** |

**Mais l'inspection visuelle nuance fortement ce chiffre** (frame 17) : à
threshold=180, `AnimeLineArtPreprocessor` donne un résultat **fragmenté et
incomplet** (contours en pointillés, jupe/plis manquants, bras droit
tronqué) — la faible variance inter-frames vient en bonne partie du fait
qu'il reste très peu de contenu, pas d'une meilleure stabilité du trait.
`LineArtPreprocessor` (réaliste) à la même valeur de seuil donne un rendu
nettement plus complet et détaillé (plis de tissu, mèches de cheveux,
ombrage), au prix d'une variance inter-frames plus élevée (probablement due
à des détails d'ombrage/texture plus sensibles à l'éclairage par frame).

**Verdict** : comparaison **non concluante en l'état** — le seuil 180
(recette scantrad générique) n'est pas calibré pour `AnimeLineArtPreprocessor`,
qui produit nativement des traits plus fins/doux nécessitant un seuil plus
bas (le pipeline piste E ci-dessus utilisait déjà threshold=40 pour ce même
préprocesseur, avec un résultat visuellement complet — cf. captures piste E
plus haut dans ce document). Pas de changement recommandé au préprocesseur
actuellement utilisé par piste E (`AnimeLineArtPreprocessor`, threshold=40)
sur la seule base de ce test. À refaire avec un balayage de seuils par
préprocesseur (ex. 40/80/120/180) si cette piste est reprise — hors budget
de cette session.

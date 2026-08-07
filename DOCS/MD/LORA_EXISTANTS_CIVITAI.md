# LoRA existants sur Civitai — personnages ciblés

*Créé le 2026-08-06, recherche web (pas de téléchargement — voir consigne
de session : documentation uniquement, LoRA trop volumineux et non
demandés explicitement pour récupération). Chiffres de téléchargements/
likes relevés le 2026-08-06, évoluent dans le temps.*

But : recenser les LoRA de personnages déjà publiés par la communauté, pour
évaluer s'il existe une alternative prête à l'emploi avant d'investir du
temps GPU local à en entraîner un depuis les assets 3D de
`ASSETS_INDEX.md`.

## Hatsune Miku

| LoRA | Auteur | Lien | Base model | Téléchargements | Likes | Recommandation |
|---|---|---|---|---|---|---|
| Hatsune Miku - v1.0 | AkiLora | https://civitai.com/models/647830/hatsune-miku | Pony (Pony Diffusion V6 XL) | 24.8K | 2.8K (147 avis, "Very Positive") | **Pertinent** — le plus téléchargé/noté des candidats trouvés, base Pony = famille SDXL, directement testable sur ce pipeline avec un checkpoint Pony. Bon candidat par défaut plutôt qu'un ré-entraînement. |
| Hatsune Miku Hassaku XL LoRA | swrneko | https://civitai.com/models/1867333/hatsune-miku-hassaku-xl-lora-by-swrneko | Illustrious | 561 | 52 | Secondaire — Illustrious natif (pas juste Pony-compatible), mais bien moins établi que le premier. À tester seulement si le style Illustrious spécifique est recherché. |

## Kirito (Kazuto Kirigaya, Sword Art Online)

| LoRA | Auteur | Lien | Base model | Téléchargements | Likes | Recommandation |
|---|---|---|---|---|---|---|
| Kazuto Kirigaya / Kirito / SAO (Pony XL / RKS) | Rakas | https://civitai.com/models/439238/kazuto-kirigaya-kirito-sword-art-online-sao-pony-xl-rks | Pony | 6,773 | 694 | **Pertinent** — meilleur compromis popularité/base SDXL parmi les candidats trouvés. |
| Kirito (ALO) \| Sword Art Online Illustrious XL | tannov97 | https://civitai.com/models/1835372/kirito-alo-or-sword-art-online-illustrious-xl | Illustrious | 761 | 237 | Secondaire — Illustrious natif, mais entraînement léger (575 steps/10 epochs) et audience plus restreinte ; couvre la tenue ALO spécifiquement. |
| Kazuto Kirigaya / Kirito \| Sword Art Online (5 styles : Alicization/ALO/GGO...) | — | https://civitai.com/models/404362/kazuto-kirigaya-kirito-or-sword-art-online | Illustrious | non relevé | non relevé | À considérer si besoin de couvrir plusieurs arcs/tenues en un seul LoRA — non vérifié en détail cette session. |

## Goku (Son Goku, Dragon Ball)

| LoRA | Auteur | Lien | Base model | Téléchargements | Likes | Recommandation |
|---|---|---|---|---|---|---|
| Son Goku - Dragon Ball - Illustrious | HellKaiza | https://civitai.com/models/1108143/son-goku-dragon-ball | Illustrious | 17.5K | 11.1K | **Très pertinent** — fort volume ET base SDXL native (Illustrious), couvre plusieurs formes/tenues à travers la franchise selon la description. Meilleur candidat "prêt à l'emploi" de toute la liste. |
| Vegeta - Dragon Ball - All Series (même auteur) | HellKaiza | https://civitai.com/models/1045337/vegeta-dragon-ball | Illustrious | 5,280 | 11.1K (total créateur) | Voir section Vegeta ci-dessous — même créateur, cohérence de style si les deux sont utilisés ensemble. |
| Son Goku - Dragon Ball - Flux1.D & SDXL | PhotobAIt | https://civitai.com/models/239649/son-goku-dragon-ball-flux1d-and-sdxl | Flux + SDXL (versions séparées) | non relevé | non relevé | Secondaire — existence d'une variante SDXL explicite en plus de Flux, non vérifiée en détail. |

## Vegeta (Dragon Ball)

| LoRA | Auteur | Lien | Base model | Téléchargements | Likes | Recommandation |
|---|---|---|---|---|---|---|
| Vegeta - Dragon Ball - All Series | HellKaiza | https://civitai.com/models/1045337/vegeta-dragon-ball | Illustrious v1.0 | 5,280 | ~11.1K (total créateur, chiffre modèle non isolé) | **Pertinent** — couvre plusieurs formes (base, SSJ, Super Vegeta, SSJ2, Majin Vegeta, Ultra Ego...) en un seul LoRA, base Illustrious = SDXL natif, même auteur que le Goku recommandé ci-dessus (cohérence de style probable). |
| Majin Vegeta XL | — | https://civitai.com/models/265630/majin-vegeta-xl | SDXL | non relevé | non relevé | Secondaire — utile seulement si la forme Majin Vegeta spécifiquement est nécessaire en dehors du LoRA "All Series". |

## Gon Freecss (Hunter x Hunter)

| LoRA | Auteur | Lien | Base model | Téléchargements | Likes | Recommandation |
|---|---|---|---|---|---|---|
| Gon Freecss / Hunter x Hunter - v1.0 | andinmaro146 | https://civitai.com/models/97335/gon-freecss-hunter-x-hunter | **SD 1.5** | 515.6K | 61K (72 avis "Very Positive") | **Chiffre très élevé, atypique pour ce créneau — vérifié deux fois par relecture de page, cohérent avec l'affichage Civitai ("515.6K"/"61K")**, mais reste **SD 1.5, pas SDXL** — nécessiterait une conversion/ré-entraînement pour ce pipeline (checkpoints SDXL en place). Pertinent comme référence de style/pose seulement, pas branchable tel quel. |
| Hunter X Hunter LORA (Style + Characters) | — | https://civitai.com/models/6859/hunter-x-hunter-lora-style-characters | SD 1.5 (Anything 4.5) | non relevé | non relevé | Secondaire — couvre Gon/Killua/Hisoka/Kurapika en un seul LoRA mais aussi SD1.5, poids conseillé 0.5-0.6. |
| **Aucun LoRA Illustrious/Pony/SDXL dédié à Gon trouvé** cette session (recherche ciblée infructueuse) | — | — | — | — | — | Écart notable par rapport à Killua (bien couvert en Pony/Illustrious, voir ci-dessous) — à re-vérifier dans une session future si le besoin devient concret. |

## Killua Zoldyck (Hunter x Hunter)

| LoRA | Auteur | Lien | Base model | Téléchargements | Likes | Recommandation |
|---|---|---|---|---|---|---|
| Killua Zoldyck \| Hunter X Hunter [PonyXL] - v1.0 | TwinklingSquid | https://civitai.com/models/389732/killua-zoldyck-hunter-x-hunter | Pony | 19.2K | 3.9K (116 avis "Very Positive") | **Très pertinent** — fort volume, base Pony (famille SDXL), directement testable. Meilleur candidat pour Killua. |
| Killua Zoldyck (HUNTER×HUNTER) LORA - v1.0 | — | https://civitai.com/models/257916/killua-zoldyck-hunterhunter-lora | SD 1.x | non relevé | non relevé | Secondaire — antérieur (SD1.x), moins pertinent pour ce pipeline SDXL. |
| Killua Zoldyck / Hunter x Hunter - v1.0 | — | https://civitai.com/models/94782/killua-zoldyck-hunter-x-hunter | non relevé | non relevé | non relevé | Non vérifié en détail cette session. |

## Synthèse

- **Miku, Kirito, Goku, Vegeta, Killua** : au moins un LoRA établi en base
  SDXL-compatible (Pony ou Illustrious) existe déjà avec un volume de
  téléchargements significatif — envisageable comme point de départ ou
  comparaison avant tout entraînement local depuis les assets 3D de
  `ASSETS_INDEX.md`.
- **Gon** : le LoRA le plus populaire trouvé est en SD1.5 uniquement ;
  aucune version Illustrious/Pony native repérée cette session. C'est le
  seul des 6 personnages où un entraînement SDXL local depuis les assets
  Models Resource (`E:\Data Demo\_extracted\hxh_Gon_MR\`) garderait un
  intérêt direct (pas de raccourci communautaire équivalent disponible).
- Aucun fichier LoRA n'a été téléchargé cette session (hors périmètre —
  documentation seulement, cf. consigne de tâche).

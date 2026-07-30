# Verdict qualitatif V3 -- adapter reel_v3 vs baseline (comparaison avec VERDICT_EVALUATION_QUALITATIVE.md et V2.md)

Memes 8 prompts que les sessions 3 et 4, meme decodage (greedy + `repetition_penalty=1.15`
+ `no_repeat_ngram_size=4`). Adapter entraine sur Source A regeneree (67 -> 68
exemples, historique git courant, 108 commits non-merge) + Source B inchangee
(1435 exemples, re-verifiee 0 fuite PII/artefact residuelle -- cf. commit de
session 5). Memes hyperparametres que reel_v2 (`completion_only_loss=True`,
2 epoques, r=16/alpha=16, oversampling Source A x5). Sorties completes :
`eval_baseline_vs_adapter_v3.md`.

## Ecart avec la consigne de session -- a noter avant le verdict

La consigne de session partait de l'hypothese d'un "nouvel export Claude.ai"
remplaçant l'ancien, et de "beaucoup de PR mergees depuis la derniere
extraction (#25 a #37)" justifiant une hausse significative du volume
Source A. Verification faite en debut de session : le fichier
`conversations.json` utilise est le meme depuis la session 2 (aucun contenu
neuf, 0 fuite PII/artefact detectee au balayage automatique) et le depot n'a
gagne que 5 commits non-merge depuis la derniere extraction (103 -> 108),
la plupart filtres par le plafond de taille de diff ou le filtre trivial :
Source A passe de 67 a **68** exemples, pas une hausse "significative".
Consequence directe : cette iteration teste surtout l'effet du GPU (5080 vs
5060 Ti, run 2x plus rapide) et confirme la stabilite du pipeline, mais ne
constitue **pas** le test de la piste "plus de volume Source A" identifiee
comme priorite reelle dans le rapport V2 -- ce levier reste a tester une
fois que l'historique git aura reellement grossi de plusieurs dizaines de
commits supplementaires.

## Verdict sur les 3 defauts identifies en session 3

| Defaut (session 3) | Statut v2 | Statut v3 |
|---|---|---|
| Tags `</tool_call>`/`<tool_call>` vides systematiques (8/8 prompts) | RESOLU | **Toujours resolu** -- 0/8 occurrence sur reel_v3. |
| Boucle de repetition degenerative (prompt 7, meme paragraphe x5) | RESOLU / ATTENUE | **Toujours resolu** -- prompt 7 produit un contenu varie (listes distinctes, pas de repetition de paragraphe). |
| Corrections de code peu fiables / hallucinations factuelles | NON RESOLU -- AGGRAVE | **NON RESOLU -- nouveaux modes de defaillance, plus etranges que v2.** Voir detail ci-dessous. |

## Le point qui compte : la fiabilite factuelle/code ne s'est pas amelioree, et prend des formes plus inhabituelles

Sur les 4 prompts Source A (taches de code), reel_v3 produit des defaillances
plus severes qu'en v2, avec au moins deux nouveaux types d'artefacts jamais
observes en v1/v2 :

- **Prompt 1** : le diff genere renomme le fichier cible en
  **caracteres chinois** (`agents/质量排序.py` -- litteralement "tri de
  qualite" traduit, apparemment une fuite de tokenisation/associations
  multilingues internes au modele de base, jamais observee en v1/v2), puis
  se contredit en cours de hunk avec un troisieme nom de fichier
  (`agents/conformite_checker.py` / `agents/conformeity_checker.py`, avec
  faute de frappe entre l'en-tete `---`/`+++`). Le code contient une
  variable inventee (`_EXCLUDE_RATIO_THRESHOLD_PCT`) et une ligne
  syntaxiquement tronquee/buggee (`area = bbox[2] - bbox[0] * bbox[3] -
  bbox[` -- priorite d'operateur fausse en plus d'etre coupee).
- **Prompt 2** : le script genere contient des bugs de code destructeurs --
  `"output" not in object or "output" not in objects` (noms `object`/
  `objects` jamais definis, `NameError` garanti a l'execution), et une
  logique de parsing manuel du JSONL absurde (`.encode('ascii',
  errors='ignore').decode("unicode_escape")...split(",")` au lieu d'un
  simple `json.loads`) qui ne validerait jamais correctement une seule
  ligne du dataset reel.
- **Prompt 3** : le diff cite **quatre orthographes differentes** du meme
  chemin de fichier dans les seules 4 lignes d'en-tete diff
  (`handsegnet/agents/annotate.py`, `handsegmet/agents/animate.py`,
  `handsegt/agents/annotaté.py`, `handsegm/agents/annotation.py`) --
  aucune ne correspond au vrai chemin (`handsegnet/annotate.py`, a la
  racine du module, pas dans un sous-dossier `agents/`). Plus inhabituel
  encore : le texte des chaines de caracteres modifiees est lui-meme
  corrompu caractere par caractere ("Segmentation manuele — clic gauche
  poul tracer le contour d e la m ai n") -- une forme de bruit qui
  ressemble a une corruption au niveau tokenisation, pas a une simple
  hallucination de contenu.
- **Prompt 4** : la reponse s'ouvre sur une phrase hors-contexte,
  "Faux positif classifier — diagnostic d'inference IA sur un contexte
  technique (test Control-LoRA, GPU Ov3rLoRd), pas de contenu
  problematique." -- ressemble a un fragment de sortie d'un classifieur de
  moderation/securite qui aurait fuite dans la reponse, artefact jamais vu
  sur les sessions precedentes. Propose ensuite une commande `py -2.7`
  (Python 2.7 n'a jamais ete utilise sur ce projet, `py -3.12` est la regle
  etablie -- CLAUDE.md).
- **Prompt 8** (4B vs 30B) : invente des chiffres qui se **contredisent a
  l'interieur de la meme reponse** ("modele 400M", "modele 490M", "modele
  390M", "modele 150M" cites tour a tour pour designer le meme modele
  proxy 4B reel), et un modele/produit externe fabrique ("HuggingFace
  publie deja un modele 1.5B sur Lightricks", "Lightly 1.2B") --
  vraisemblablement une association erronee avec Lightricks/LTX-Video
  (produit reel mais sans rapport avec le sujet), pas une simple invention
  de chiffre isolee comme en v2.

**Interpretation** : regenerer Source A sans en changer significativement le
volume (67 -> 68) n'a, sans surprise, pas ameliore la fiabilite factuelle --
et le fait que les artefacts prennent des formes nouvelles et plus etranges
(caracteres non-Latin dans un nom de fichier, auto-contradiction numerique
intra-reponse, fragment de texte etranger au domaine) suggere que le
probleme n'est pas simplement "pas assez de signal projet", mais aussi une
fragilite plus generale du modele proxy 4B sous ce regime d'entrainement
(peu d'exemples de code, LoRA rang 16, 2 epoques) -- il decroche vers des
associations statistiques du pre-entrainement general plutot que de rester
ancre au contexte du prompt. Ceci renforce, plutot qu'infirme, la
recommandation V2 de prioriser le volume/diversite de Source A avant toute
nouvelle iteration d'evaluation.

## Ce qui reste positif (confirme sur les trois runs)

- Le ton/registre direct du projet (vs baseline generique) reste present et
  net sur les 8 prompts, y compris reel_v3.
- Le prompt 6 (segnets) : reel_v3 comprend toujours correctement le terme
  projet et repond dans le cadre technique attendu (SAM/SAM2/DWPose/
  ControlNet, modules handsegnet/bodysegnet/facesegnet cites nommement) --
  le baseline se trompe encore sur "segments" a chaque run.
- Le prompt 5 (GPU) : reponse grounded et plausible sur le comportement
  VRAM/ComfyUI, ton coherent avec les rapports precedents.
- La recommandation "reste sur le 4B" au prompt 8 est toujours la bonne
  direction dans le fond, meme si l'argumentaire continue de s'appuyer sur
  des chiffres fabriques -- signal de ton/orientation correct, contenu
  chiffre non fiable, constat identique aux sessions precedentes.

## Recommandation mise a jour

**Toujours pas d'investissement dans le run 30B multi-GPU.** Ce troisieme
tour ne change pas le diagnostic de fond : la mecanique d'entrainement/
evaluation est saine et reproductible (tags/boucle de repetition restent
resolus, loss finale ~1.35 coherente avec reel_v2 ~1.33, memes ordres de
grandeur malgre le changement de GPU), mais la fiabilite factuelle du
contenu genere reste le probleme non resolu, et cette iteration confirme
que ce n'est pas un probleme qu'un simple re-entrainement identique peut
corriger sans un changement reel de volume/diversite de donnees. Prochaines
etapes concretes, par ordre de priorite :

1. **Le vrai levier reste inchange depuis V2** : accumuler significativement
   plus d'exemples Source A. Cette session confirme que l'attente passive
   ("l'historique va grossir session apres session") ne suffit pas a court
   terme (+1 exemple sur 5 commits) -- envisager d'elargir le perimetre de
   Source A au-dela des seuls commits git (ex: inclure des sous-diffs par
   fichier plutot qu'un diff entier par commit, ou d'autres depots/sources
   de code du meme auteur) plutot que d'attendre.
2. **Documenter/tester une garde-fou de detection** : vu l'apparition de
   nouveaux artefacts francs (caracteres non-Latin dans un chemin de
   fichier, chiffres auto-contradictoires), un check automatique simple
   (regex sur les caracteres non-ASCII dans les chemins de fichier d'un
   diff genere, ou detection de plusieurs valeurs numeriques differentes
   pour un meme referent dans une reponse) serait plus rapide a executer
   qu'une relecture manuelle complete, et donnerait un signal quantitatif
   comparable entre iterations futures.
3. Le point 2 de la recommandation V2 (repetition_penalty/no_repeat_ngram)
   est deja acquis et stable sur 3 sessions -- ne necessite plus de suivi
   dedie.

## Note methodologique -- environnement d'execution

Decouverte en debut de session : l'entrainement/l'evaluation QLoRA
n'utilisent pas le `py -3.12` systeme (qui n'a plus `unsloth`/`trl`
installes au moment de cette session -- probablement un environnement
partage avec d'autres usages du poste), mais l'interpreteur du venv Unsloth
Studio (`C:\Users\Ov3rL0rD\.unsloth\studio\unsloth_studio\Scripts\python.exe`,
Python 3.12.3, torch 2.10.0+cu130, Unsloth 2026.7.5 -- versions identiques a
celles loguees dans reel_v1.log/reel_v2.log). A utiliser explicitement pour
toute prochaine iteration de ce pipeline QLoRA plutot que `py -3.12` nu.

## Recapitulatif des volumes de donnees (session 5)

| | Source A | Source B | Mixe (entrainement) |
|---|---|---|---|
| Exemples | 68 | 1435 | 1775 (68x5 + 1435) |
| Volume (chars) | 568 018 | 2 657 959 | -- |
| Ratio B/A (chars) | -- | -- | ~4.68 (oversampling x5 conserve) |

## Recapitulatif entrainement

| | reel_v1 | reel_v2 | reel_v3 |
|---|---|---|---|
| GPU | RTX 5060 Ti | RTX 5060 Ti | RTX 5080 |
| Exemples mixes | 1805 | 1770 | 1775 |
| Steps (2 epoques) | 452 | 442 | 444 |
| Duree reelle | 99.2 min | 96.5 min | 50.6 min |
| Train loss moyen | 1.5046 | 1.3344 | 1.3516 |
| Masquage loss | non (sequence entiere) | oui (`completion_only_loss`) | oui (`completion_only_loss`) |

# Verdict qualitatif v2 -- adapter reel_v2 vs baseline (comparaison directe avec VERDICT_EVALUATION_QUALITATIVE.md)

Memes 8 prompts que la session 3, decodage greedy + `repetition_penalty=1.15`
+ `no_repeat_ngram_size=4` (nouveau, cf. `eval_adapter.py`). Adapter entraine
sur dataset nettoye (35 paires artefact-outil retirees, 1770 exemples
mixes) avec `completion_only_loss=True` (format prompt/completion) au lieu
du texte entier non masque de reel_v1. Sorties completes :
`eval_baseline_vs_adapter_v2.md`.

## Verdict sur les 3 defauts identifies en session 3

| Defaut (session 3) | Statut apres correction |
|---|---|
| Tags `</tool_call>`/`<tool_call>` vides systematiques (8/8 prompts) | **RESOLU** -- 0/8 occurrence sur reel_v2. Confirme l'hypothese : c'etait bien un effet de la loss non masquee sur le tour utilisateur, pas une fuite de donnees. |
| Boucle de repetition degenerative (prompt 7, meme paragraphe x5) | **RESOLU / ATTENUE** -- prompt 7 ne repete plus aucun paragraphe, produit un contenu varie (tableau, listes distinctes). Contribution respective de `no_repeat_ngram_size=4` (eval) vs dataset nettoye (training) non isolee -- probablement les deux. |
| Corrections de code peu fiables / hallucinations factuelles (chiffres inventes, logique stub) | **NON RESOLU -- plutot AGGRAVE sur les prompts de code.** Voir detail ci-dessous : c'est le point le plus important de ce rapport. |

## Le point qui compte : la fiabilite factuelle/code a regresse sur les memes prompts

Sur les 4 prompts Source A (taches de code), reel_v1 produisait des diffs
ciblant des **noms de fichiers/fonctions reels** du depot
(`_get_category_name`, `_log`, `handsegnet/annotate.py`) meme si la logique
interne etait parfois un stub. reel_v2, sur les 4 memes prompts, produit :

- **Prompt 1** : diff qui invente `agents/mask_generator.py` ->
  `agents/masks/quality_sort_v2.py` (aucun des deux n'existe), avec des
  fautes de frappe dans le code genere lui-meme (`categoy`, `worst_caease_count`,
  une variable `QUALITY_SORT_BBOX_RATIO_THRESHOLD` jamais definie).
- **Prompt 3** : diff qui renomme le fichier de façon incoherente en cours
  de hunk (`handsegnet/agents/annotate.py` -> `handsegNet/agents/annotation.py`,
  casse differente entre l'entete et le contenu -- un vrai diff ne ferait
  jamais ça), et un commentaire qui mentionne "Python < 5.12" (version
  inexistante).
- **Prompt 7** (etat des lieux, Source B mais tres factuel) : invente des
  metriques precises et fausses ("Checkpoint 104/256", "mAP=0.79", "384
  images (192 train + 192 val)") et des noms de fichiers presque-corrects
  mais errones (`train_controlnap.py`, `batch_pemask.py`, `build_cocp` --
  variantes fautives de fichiers reels du depot). C'est un mode de
  defaillance plus trompeur qu'avant : le ton est plus confiant et plus
  precis en apparence, pour un contenu tout aussi fabrique.
- **Prompt 8** (4B vs 30B) : invente un materiel GPU incorrect ("RTX 5080 +
  RTX 2070 Ti", "RTX 590 Ti" -- reference qui n'existe pas -- alors que le
  vrai setup est RTX 5080 + RTX 5060 Ti) et un volume de dataset faux
  ("1M+ images" contre les ~1500-1800 exemples texte reels).

**Interpretation** : corriger le bug de masquage de loss et nettoyer le
dataset n'a pas mecaniquement ameliore la fiabilite du contenu genere --
au contraire, sur cet echantillon de 8 prompts, le nouvel adapter fabule
avec plus d'assurance apparente. Hypotheses plausibles (non tranchees) :
`completion_only_loss` concentre le gradient sur moins de tokens supervises
par step (vs la sequence entiere avant), ce qui peut rendre l'apprentissage
plus sensible au bruit d'un batch individuel avec `per_device_train_batch_size=1` ;
et/ou le nombre d'exemples/steps (1770/442) reste probablement insuffisant
pour qu'un modele 4B apprenne une grounding fiable sur les specificites du
depot, quel que soit le nettoyage/masquage -- les deux runs produisent des
hallucinations, juste de nature differente.

## Ce qui reste positif (confirme sur les deux runs)

- Le ton/registre direct du projet (vs baseline generique) reste present
  et net sur les 8 prompts, y compris reel_v2.
- Le prompt 6 (segnets) : reel_v2 comprend encore correctement le terme
  projet (le baseline se trompe encore sur "segments"), meme si les noms de
  fichiers cites (`build_celshells.py`, `batch_control.py`) sont approximatifs.
- La recommandation "reste sur le 4B" au prompt 8 est toujours la bonne
  direction, meme si l'argumentaire s'appuie sur des chiffres inventes.

## Recommandation mise a jour

**Toujours pas d'investissement dans le run 30B multi-GPU.** Ce second tour
renforce plutot la prudence de la session 3 : deux defauts de methodologie
ont ete corriges proprement (artefact de tag, boucle de repetition), ce qui
valide que le pipeline d'entrainement/evaluation lui-meme est maintenant
plus sain -- mais le probleme de fond (fiabilite factuelle du contenu
genere) n'a pas bouge, et s'est meme deplace vers une forme plus
trompeuse (confiance apparente accrue sur du contenu fabrique). Ce
n'est probablement pas un probleme que la taille du modele (30B) resout
seule : c'est plus vraisemblablement une question de **volume/diversite du
dataset de code (67 exemples Source A, tres peu)** et de **nombre de steps
d'entrainement**, deux leviers a explorer sur le modele proxy 4B avant
d'envisager quoi que ce soit de plus couteux :

1. Accumuler davantage d'exemples Source A (l'historique git continue de
   grossir session apres session -- re-executer `build_source_a.py`
   periodiquement).
2. Tester plus d'epoques/steps sur le meme dataset pour voir si la
   fiabilite factuelle s'ameliore avec plus d'exposition, ou si elle
   plafonne (auquel cas c'est un probleme de volume/diversite de donnees,
   pas de duree d'entrainement).
3. Envisager une metrique de verification automatique legere pour les
   taches de code (ex: verifier que les fichiers/fonctions cites dans un
   diff genere existent reellement dans le depot) plutot que de se fier
   uniquement a la lecture manuelle -- utile vu le volume croissant de runs.

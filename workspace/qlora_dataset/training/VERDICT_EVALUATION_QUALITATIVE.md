# Verdict qualitatif -- adapter QLoRA reel_v1 vs baseline

Comparaison sur 8 prompts (4 style Source A / code, 4 style Source B /
diagnostic-rapport), decodage deterministe (greedy, meme seed implicite,
memes parametres) sur `unsloth/Qwen3-4B-Instruct-2507`. Sorties completes :
`eval_baseline_vs_adapter.md` (meme dossier).

## Verdict global

**L'adapter a un effet perceptible, reel et repetable sur le ton et la
structure -- ce n'est pas un cas de "loss qui baisse sans rien changer
qualitativement".** Sur les 8 prompts, la bascule de registre est nette et
constante : le baseline reste sur un ton "assistant generaliste" (listes a
puces generiques, emojis-titres, questions de clôture type "veux-tu que je
l'adapte ?", vocabulaire hors-sujet quand un terme du projet lui echappe).
Le fine-tune bascule systematiquement vers un registre direct, factuel,
truffe de vocabulaire et de structures reelles du projet (noms de fonctions
existants, noms de fichiers reels, format diff unifie, ton "rapport
d'architecte" sans fioritures).

**Mais le resultat n'est pas encore utilisable en l'etat** : un artefact de
formatage systematique et au moins deux categories de defauts de fond
(correction fonctionnelle douteuse, hallucination de chiffres precis, une
boucle de repetition degenerative) limitent serieusement la valeur pratique
immediate de cet adapter.

## Ce qui marche clairement (signal positif net)

- **Prompt 1 (quality_sort.py)** : le fine-tune produit un vrai diff unifie
  ciblant les noms de fonctions REELS du fichier (`_get_category_name`,
  `_get_bbox_from_mask`, convention `_nom_prive`) -- le baseline invente un
  module generique avec docstrings Google-style hors convention du depot.
  C'est la preuve la plus forte et la plus verifiable d'un vrai transfert
  de connaissance structurelle projet (ces noms viennent des diffs Source A).
- **Prompt 6 (segnets = portefeuille de competences)** : le baseline
  **comprend "segnets" comme une coquille de "segments"** et part sur un
  hors-sujet complet de coaching carriere generique. Le fine-tune comprend
  immediatement le terme du projet (FootSegNet/HandSegNet...) et repond dans
  le bon cadre technique. Ecart le plus spectaculaire des 8 prompts.
- **Prompt 4 (conclusion footsegnet x30)** et **Prompt 5 (diagnostic GPU)** :
  le fine-tune adopte le ton direct/actionnable du registre reel du projet
  (referme sur une action ou une question de suivi precise, pas une
  question de politesse generique) ; le baseline reste generique et
  "template RH/consulting".
- **Prompt 8 (4B vs 30B)** : le fine-tune raisonne dans le cadre concret
  reel de la session ("tu as deja le pipeline, le dataset, le materiel")
  plutot que le comparatif abstrait generique du baseline.

## Ce qui ne marche pas / limites reelles a documenter

- **Artefact systematique `</tool_call>` / `<tool_call>` vides en tete de
  chaque reponse fine-tune** (les 8/8 prompts). Hypothese la plus probable :
  une partie des exemples Source B provenant de sessions Claude Code
  agentiques (l'export Claude.ai contient des messages assistant ou le
  contenu reel est dans des blocs `tool_use`/`tool_result`, avec un champ
  `text` aplati contenant un transcript brut d'actions -- bullets `●`/`⎿`,
  "Searched for 1 pattern, read 1 file...") a fini dans le dataset comme
  `output` alors que ce n'est pas de la prose exploitable. Le modele a
  associe ce bruit structurel au token special `<tool_call>` du template
  Qwen3 (present dans son vocabulaire natif pour l'appel d'outils). **A
  corriger a la source (session 2, `build_source_b.py::get_text`)** avant
  toute nouvelle iteration -- cf. recommandation ci-dessous.
- **Correction fonctionnelle douteuse sur les taches de code** :
  - Prompt 1 : `_is_mask_too_small` retourne `return False` en dur -- la
    logique de seuil (2%) n'est jamais implementee, juste la structure.
  - Prompt 3 : le "fix" propose (`.encode('utf-8').decode('latin-1')`) est
    incorrect (n'aurait pas resolu un `UnicodeEncodeError` Windows), et un
    des hunks de diff ne change rien (`-`/`+` identiques).
  - Conclusion : l'adapter a bien appris la **forme** (diff, noms reels,
    ton), mais pas encore une fiabilite fonctionnelle du contenu genere --
    attendu sur seulement 452 steps/2 epoques et 67 exemples de code source.
- **Hallucination de chiffres precis** : Prompt 8 invente "300GB de VRAM",
  "1000 paires, 100 episodes, 1000 steps" (les vrais chiffres de cette
  session sont 1805 exemples / 452 steps / 2 epoques, VRAM ~17,5GB). Le
  raisonnement general est juste, les chiffres cites sont fabriques.
- **Boucle de repetition degenerative -- Prompt 7 (etat des lieux)** : le
  fine-tune repete "batch_controlnet.py -- le coeur du pipeline" et son
  bloc de bullets identiques 5 fois de suite mot pour mot. Confondu
  possible avec le choix de decodage (greedy, sans `repetition_penalty`
  dans `eval_adapter.py`) -- a re-tester avec penalite de repetition avant
  de conclure que c'est purement un defaut de l'adapter, mais le signal
  brut reste un point de vigilance reel meme en tenant compte de ce biais
  methodologique.

## Recommandation explicite

**Ne pas investir tout de suite dans le run 30B multi-GPU.** Le signal est
suffisamment positif pour valider l'approche QLoRA + ce dataset dans son
principe (le style/comportement change reellement, de façon coherente et
repetable, sur un modele bon marche a iterer) -- mais les defauts observes
(artefact de tags, contenu fonctionnellement peu fiable, hallucination de
chiffres, une boucle degenerative) sont des problemes de **dataset et de
methodologie d'evaluation**, pas des limites de capacite du 30B qu'un
modele plus gros resoudrait automatiquement. Investir dans le 30B
maintenant reviendrait a passer a l'echelle des defauts non corriges.

Avant d'aller plus loin :
1. **Nettoyer Source B** : filtrer/exclure les paires dont l'`output` vient
   d'un message assistant majoritairement `tool_use` (texte de narration
   trop mince), source probable de l'artefact `<tool_call>`.
2. **Re-tester le decodage** : ajouter `repetition_penalty`/
   `no_repeat_ngram_size` dans `eval_adapter.py` avant de re-juger le
   Prompt 7 -- isoler le defaut modele du defaut de decodage.
3. **Reiterer sur le meme modele proxy 4B** (pas besoin de plus de VRAM
   pour ça) avec le dataset nettoye, eventuellement quelques epoques
   supplementaires, puis refaire cette meme comparaison avant de rouvrir la
   question du 30B multi-GPU.

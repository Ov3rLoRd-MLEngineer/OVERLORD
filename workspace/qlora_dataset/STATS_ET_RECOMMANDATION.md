# Dataset QLoRA comportemental -- Session 2 -- Statistiques et recommandation

Généré le 2026-07-29. Préparation de données uniquement -- **aucun entraînement lancé**.
Mis à jour Session 6 (2026-07-30) : ajout de Source C, voir section dédiée en bas de fichier.

## Composition

| Fichier | Source | Format | Exemples |
|---|---|---|---|
| `dataset_source_a.jsonl` | Historique git du dépôt (103 commits non-merge, 68 exemples depuis régénération Session 5) | Alpaca (`instruction`=sujet commit, `input`=corps du message, `output`=diff) | **68** |
| `dataset_source_b.jsonl` | Export JSON conversations Claude.ai (18 conversations, 3787 messages) | Alpaca (`instruction`=message humain, `input`="", `output`=réponse assistant) | **1435** (nettoyé Session 4) |
| `dataset_source_c.jsonl` | Rapports de session Claude Code (`.claude/projects/*/*.jsonl`, 74 fichiers) | Alpaca (`instruction`=message humain, `input`="", `output`=raisonnement assistant + code produit Write/Edit) | **275** |
| **Total** | | | **1778** |

Les trois fichiers restent **séparés** (styles différents : diffs de code isolés vs. dialogue "rapport d'architecte" vs. raisonnement+code de session de dev) -- à charger comme trois datasets distincts dans Unsloth, pas concaténés.

## Filtrage appliqué

### Source A (git)
- Merges exclus (`--no-merges`).
- 2 commits exclus explicitement : fuite de clé API `.env` documentée dans l'historique (le diff aurait exposé l'ancien secret).
- 7 commits triviaux exclus (nettoyage `.pyc`/`__pycache__`, insertions mécaniques d'en-tête/logo sur des dizaines de fichiers, WIP).
- Diffs plafonnés à 20000 caractères après exclusion des chemins binaires/générés (`.pyc`, `.env*`, images, poids de modèle) -- 28 commits au-delà (imports en masse, renommage de marque sur tout le dépôt) exclus car ce sont des dumps mécaniques, pas des changements isolés représentatifs d'un comportement de code.

### Source B (Claude.ai)
- `users.json` (identité/email du compte) et `memories.json` (mémoire cross-conversations) exclus d'office du périmètre -- métadonnées de compte, pas des transcriptions de conversation.
- Filtre lexical (santé, contacts/relations, coordonnées, logistique Japan Expo non-technique) : 118 paires exclues.
- 172 paires exclues car trop courtes / contenu non textuel (upload d'image/pièce jointe sans texte).
- Une conversation entière exclue en bloc ("BlaBla", 347 messages) : discussion informelle explicitement nommée comme telle par l'utilisateur, contenant une fuite biographique (ancien employeur, ville, lien Google Maps) qu'aucun mot-clé ne couvrait.
- **5 audits successifs** sur le contenu conservé ont révélé des fuites non couvertes par les mots-clés initiaux, noyées dans des conversations par ailleurs très techniques : identité réelle recherchée sur LinkedIn par l'assistant, récit biographique complet (ancien poste en chimie industrielle, CDI manqué en 2018, accident du travail) sur 5 paires consécutives, statut chômage, litige bancaire personnel, ville de naissance/résidence. Chaque cas a été retiré individuellement (par UUID de message ou mot-clé ciblé) au fur et à mesure de la découverte.

**Limite à connaître** : ce filtrage est heuristique (regex + relecture manuelle ciblée sur les zones à risque), pas un audit exhaustif message par message des 1470 paires conservées. Le taux de récidive décroissant sur les 5 passes (fuites de moins en moins fréquentes et de moins en moins graves) est un signal encourageant mais pas une garantie absolue. Une relecture humaine rapide avant tout entraînement réel reste recommandée, en particulier sur les conversations les plus longues et les plus "casual" en ton (`Prioriser les tâches FootSegNet`, `Débogage cache sam_mask_generator V228`, `AnimateDiff frame analysis...`).

## Statistiques descriptives

| | Source A | Source B |
|---|---|---|
| Exemples | 67 | 1470 |
| `instruction` (moy/médiane, chars) | 79 / 78 | 719 / 314 |
| `output` (moy/médiane, chars) | 7579 / 6569 | 1201 / 884 |
| `output` max (chars) | 17823 | 9471 |
| Total/exemple (moy, ~tokens) | ~2108 | ~480 |
| Volume total (~tokens, estimation grossière ~4 chars/token) | ~141 000 | ~706 000 |
| **Combiné** | | **~847 000 tokens, 1537 exemples** |

## Recommandation

Le volume **justifie un premier essai QLoRA**, avec une nuance par source :

- **Source B (1470 exemples)** est largement suffisante pour un premier test de signal comportemental (le rappel de la session -- quelques centaines d'exemples suffisent pour un premier signal -- est dépassé de ~6x). C'est la source à utiliser en priorité pour un premier run : volume confortable, ton/structure de rapport cohérents à apprendre.
- **Source A (67 exemples)** est plus fine mais reste en dessous du seuil "quelques centaines" évoqué. Utilisable comme signal complémentaire ou pour un test qualitatif ciblé (style de diff/commit), mais pas suffisante seule pour un entraînement robuste -- l'historique va continuer à s'accumuler séance après séance et ce fichier pourra être régénéré (`scripts/build_source_a.py`) pour grossir naturellement.

Recommandation concrète : premier essai QLoRA sur Source B seule ou Source B dominante avec Source A en appoint (pondération/upsampling léger si mélangées en pratique, mais garder les deux fichiers séparés comme demandé). Revoir le volume Source A dans quelques mois de développement supplémentaire avant d'investir dans un run dédié à cette source.

## Reproductibilité

Scripts dans `scripts/` (`build_source_a.py`, `build_source_b.py`, `build_source_c.py`, `compute_stats.py`), exécutables via `py -3.12`. Les critères d'exclusion (mots-clés, UUIDs de messages, plafond de taille de diff) sont documentés en commentaire en tête de chaque script.

## Session 6 (2026-07-30) -- Source C : rapports de session Claude Code

### Origine et méthode

`dataset_source_c.jsonl` est construit à partir des transcripts complets de session Claude Code (`C:\Users\<user>\.claude\projects\*\*.jsonl` -- un fichier par session, 74 fichiers hors la session en cours d'écriture au moment du run, ~365 Mo au total, sessions interactives et sessions "bg" lancées via `.claude/jobs/` confondues -- ce sont les deux localisations citées dans la consigne de session, `.claude/jobs/` s'étant avéré ne contenir que des résumés condensés par transition d'état, `timeline.jsonl`, alors que le transcript complet référencé par son `linkScanPath` sous `.claude/projects/` est la source réellement riche en raisonnement + code).

Contrairement à Source A (diffs git isolés, sans raisonnement du tout) et Source B (dialogue Claude.ai, jamais de code produit dans le même tour), Source C vise des paires qui combinent les deux : `instruction` = message réellement tapé par l'utilisateur (`type=="user"`, `content` une chaîne, `origin.kind=="human"` -- distingue un vrai message humain d'un résultat d'outil renvoyé au modèle, qui porte aussi `type=="user"` mais `content` une liste de blocs `tool_result`), `output` = concaténation du texte assistant visible (blocs `text`, jamais `thinking` -- raisonnement interne du modèle, pas un rapport destiné à l'utilisateur, exclu par choix) **plus**, quand le même tour contient un appel `Write`/`Edit`/`NotebookEdit` sur un fichier `.py` ou `.md`, le code/contenu produit (texte intégral pour `Write`, bloc avant/après pour `Edit` -- volontairement diff-like plutôt que fichier entier, dans le même esprit que Source A). Une paire n'est gardée que si elle contient du texte de raisonnement non vide -- le code seul, sans raisonnement, ne suffit pas (ce serait redondant avec le rôle de Source A). Vérifié manuellement sur deux transcripts de tailles très différentes (un run bg court, un run interactif de 74 Mo) : aucun message humain de ce corpus ne contient de bloc `<system-reminder>` -- l'injection de contexte système ne pollue donc pas le côté instruction sur cette version du CLI, contrairement à une inquiétude initiale.

Les tours appartenant à un sous-agent (`isSidechain: true`, conversations internes de l'outil Agent/Task) sont exclus -- ce n'est pas l'utilisateur principal qui s'exprime.

### Filtrage appliqué

- **Discipline identique à la correction Session 4 sur Source B** : `PERSONAL_PATTERNS` et `has_tool_artifact()`/`clean_stray_markers()` de `build_source_b.py` sont réimportés tels quels (pas redéfinis en parallèle) pour garantir une règle strictement identique, plutôt qu'une variante qui diverge avec le temps -- 36 paires exclues pour contenu personnel, 4 pour artefact d'outil résiduel.
- **Filet de sécurité supplémentaire** (`SECRET_PATTERNS`, nouveau à cette source) : formes de secrets usuelles (clés `sk-`/`AKIA`/`ghp_`/`xox`, blocs `PRIVATE KEY`) -- 0 occurrence trouvée, cohérent avec le fait que le périmètre d'extraction ne capture jamais la sortie brute de `Bash`/`Read`/`Grep` (seul vecteur plausible d'une fuite de `.env`), seulement le texte assistant et les payloads `Write`/`Edit`.
- 25 doublons exacts retirés (sessions reprises/forkées loggant deux fois le même échange).
- Audit manuel complémentaire après filtrage automatique (mots-clés hors liste initiale : mot de passe, secret, carte bancaire, IBAN, salaire, impôts...) : aucune occurrence problématique trouvée sur les 275 exemples retenus -- contrairement à Source B, un seul passage a suffi ici, probablement parce que le contenu est technique par construction (transcripts de travail sur le dépôt) plutôt que du dialogue libre où une tangente personnelle peut se glisser.
- Plafond de sortie 20000 caractères (cohérent avec `DIFF_SIZE_CAP` de Source A) -- 1 seul exemple sur 275 atteint ce plafond.

### Statistiques

| | Source C |
|---|---|
| Exemples | 275 |
| `instruction` (moy/médiane, chars) | 187 / 58 |
| `output` (moy/médiane, chars) | 4936 / 2410 |
| `output` max (chars) | 20000 (plafond, 1 exemple) |
| Volume total (~tokens, ~4 chars/token) | ~352 000 |
| Exemples avec code produit (Write/Edit/.py ou .md) | 115 / 275 (~42%) |

### Comparaison au seuil 500-1000 recommandé

La consigne de session vise à rapprocher le **volume factuel/code** (catégorie de Source A, diffs/code à forte densité de signal, distincte du dialogue plus abondant mais moins dense de Source B) du seuil de quelques centaines à un millier d'exemples évoqué en Session 2.

**Source A + Source C combinées = 68 + 275 = 343 exemples.** C'est **5x le volume de Source A seule**, mais **toujours en dessous du bas de la fourchette 500-1000**. Raison identifiée : la majorité des 74 fichiers de session ne contiennent qu'une poignée de messages *réellement tapés par l'utilisateur* -- beaucoup de sessions "bg"/autonomes (`/loop`, sessions longues avec peu d'interaction, cf. la consigne même de cette session) n'ont qu'un seul message humain initial suivi de dizaines de tours purement autonomes (outils, pas de nouvelle instruction humaine), ce qui limite mécaniquement le nombre de paires extractibles quel que soit le volume brut de transcript traité (365 Mo pour seulement 355 tours humains bruts, 275 après filtrage).

**Recommandation** : ne pas forcer un seuil artificiel en assouplissant les critères de qualité (ce serait recréer le problème diagnostiqué en Session 4 -- artefacts d'outil réintroduits dans le dataset). Le volume continuera de croître session après session à mesure que de nouveaux transcripts s'accumulent, exactement comme Source A (`build_source_c.py` est ré-exécutable tel quel). Pour un premier essai QLoRA combinant les trois sources, garder Source B comme base dominante (volume), Source A et Source C comme signal complémentaire fin (comportement de code + raisonnement de session), avec un sur-échantillonnage léger des deux dernières si mélangées en pratique -- même logique que la recommandation Session 2, étendue à trois sources plutôt que deux.

## Session 6 (2026-07-30) -- Sous-ensemble Python CommitPackFT (préparation externe)

### Écart consigne / état réel

La consigne de session suppose les 5 bases externes (CommitPack, OpenCodeInstruct, Stack v2/v3, CodeAlpaca, Evol-Instruct-Code) en cours de téléchargement vers le HDD externe (`G:`, "Seagate 8To"), avec un script à préparer mais **pas exécuter** tant que les données ne sont pas confirmées présentes. Vérification faite à l'exécution (`Get-Volume`, contenu de `G:\Data` et `E:\data`, ligne de commande des process Python actifs) :

- `bigcode/the-stack` (le plus volumineux des 5) était **réellement en cours de téléchargement** vers `G:\Data\the-stack` (HDD) au moment de la vérification -- conforme à la consigne pour cette base.
- **CommitPackFT, OpenCodeInstruct et evol-codealpaca-v1 étaient déjà téléchargées et complètes, directement sur `E:\data\` (le SSD 2 To dédié "990Pro 2To"), pas sur le HDD.** Vérifié pour CommitPackFT : 277 répertoires de langage (`kilobytes.txt` liste 279 lignes dont l'en-tête et le total = cohérent), taille totale mesurée 1507 Mo vs. ~2 Go annoncés par le README HuggingFace du dataset (écart cohérent avec un arrondi) -- téléchargement complet, pas partiel.

Le script `build_source_commitpack_python.py` a donc été écrit pour vérifier plusieurs emplacements candidats (HDD supposé ET SSD réellement observé) plutôt que de coder en dur l'hypothèse de la consigne, et exécuté dans cette même session conformément à la clause conditionnelle de la consigne ("si le téléchargement est déjà présent, tu peux lancer l'extraction directement"). Aucune copie HDD->SSD n'a été nécessaire pour CommitPackFT (source déjà sur le SSD dédié) -- le script reste néanmoins générique pour ce cas si une future base atterrit bien sur le HDD comme prévu.

### Filtrage et résultat

CommitPackFT/Python complet : 56025 exemples (129.6 Mo de JSONL brut, mesuré). Filtres appliqués : `lang=="Python"` (déjà vrai), sujet non trivial, `old_contents != new_contents`, **`ast.parse()` validé sur `new_contents`** (obligatoire selon les règles de session -- 4755 exemples rejetés, ~8.5%, cohérent avec le fait connu que CommitPack contient des extraits Python 2 tronqués/invalides), diff plafonné à 20000 caractères (0 exemple au-delà -- les fichiers de CommitPackFT sont en pratique plus courts que les diffs les plus longs de Source A), `SECRET_PATTERNS` (mêmes regex que `build_source_c.py`, 4 exemples rejetés). 51266 exemples ont passé tous les filtres ; échantillon aléatoire (seed 3407) à **2000** exemples pour ce premier sous-ensemble.

**`PERSONAL_PATTERNS` (filtre vie privée de Source B/C) n'a volontairement PAS été appliqué ici** : un audit rapide montre 191/2000 exemples matchés, mais 189 sont le motif email générique déclenché par des métadonnées d'auteur open source légitimes et déjà publiques (`__author__`, `author_email` dans des `setup.py` de tiers -- ex. `raphael@hackebrot.de`, `kinnen@cqse.eu`), pas une fuite de données personnelles de l'utilisateur Ov3rLoRd. Appliquer ce filtre reviendrait à une erreur de catégorie (le motif protège l'identité de l'utilisateur dans son propre dialogue, pas les métadonnées d'auteurs tiers dans du code déjà public sous licence permissive) et dégraderait la qualité du sous-ensemble sans bénéfice de confidentialité réel.

Sortie : `E:\data\commitpackft_python_subset\dataset_source_commitpack_python.jsonl` (sur le SSD dédié) + copie de référence versionnée `workspace/qlora_dataset/dataset_source_commitpack_python.jsonl` (2000 lignes, format Alpaca identique à Source A : `instruction`=sujet de commit, `input`=corps du message, `output`=diff unifié).

### Statut

Préparation de données uniquement -- **aucun entraînement lancé** sur ce sous-ensemble. Script réexécutable (`py -3.12 workspace/qlora_dataset/scripts/build_source_commitpack_python.py`) une fois les 4 autres bases externes (OpenCodeInstruct, Stack v2/v3, CodeAlpaca, Evol-Instruct-Code) confirmées présentes et complètes, sur le même principe -- non fait dans cette session (hors périmètre de la consigne, qui ne visait que CommitPack).

## Session 2026-08-02 -- Sous-ensembles evol-codealpaca-v1 et OpenCodeInstruct

Suite de la préparation externe, mêmes principes que CommitPackFT/Python (taille cible 2000, `ast.parse()` validé, `SECRET_PATTERNS`, `PERSONAL_PATTERNS` volontairement pas appliqué -- sources publiques tierces, même raisonnement documenté ci-dessus).

| Source | Candidats lus | Filtre principal | Retenus (avant échantillonnage) | Sous-ensemble final |
|---|---|---|---|---|
| `evol-codealpaca-v1` (`E:\data\evol-codealpaca-v1\train.jsonl`, 111272 ex. total) | 111272 | fence ```` ```python ```` explicite (pas de champ `lang`) + `ast.parse()` | 49319 | **2000** |
| `OpenCodeInstruct` (NVIDIA, `E:\data\OpenCodeInstruct\data\`, ~5M ex. total, 50 shards parquet) | 200000 (2 premiers shards sur 50 -- largement suffisant, voir docstring du script) | `average_test_score == 1.0` (tous les tests unitaires générés passent) + fence Python + `ast.parse()` | 79676 | **2000** |

Écarts notés : `evol-codealpaca-v1` est multi-langage sans champ dédié (~45% Python d'après un échantillon de 20000, filtré sur le fence markdown explicite pour rester fiable plutôt que deviner) ; `OpenCodeInstruct` porte un score de qualité mesuré par exemple (`average_test_score`), filtre plus fort qu'une simple validation syntaxique -- utilisé en filtre principal plutôt qu'un seuil arbitraire.

Scan `PERSONAL_PATTERNS` (référence uniquement, non appliqué en filtre) : 23/2000 (evol-codealpaca) et 22/2000 (OpenCodeInstruct), taux comparable à CommitPackFT (~9.5%) -- cohérent avec des métadonnées d'auteurs publics dans du code/docstrings, pas une fuite de données personnelles de l'utilisateur.

Sorties : `E:\data\evol_codealpaca_python_subset\` et `E:\data\opencodeinstruct_python_subset\` (SSD dédié) + copies de référence versionnées dans `workspace/qlora_dataset/`. **Aucun entraînement lancé sur ces deux sous-ensembles** -- préparation uniquement, en attente d'une décision sur leur intégration au Stage 1 (actuellement CommitPack seul).

## Session 2026-08-03 -- Sous-ensemble Python du "vrai" CommitPack (pas CommitPackFT)

### Écart consigne / état réel

La consigne supposait un export Parquet avec un schéma déjà instruction/diff, sur la base du dataset CommitPackFT déjà traité. Vérification faite avant codage (comme demandé) : `E:\data\commitpack\python\` est en réalité **du JSONL brut** (458 shards, ~524 Mo chacun, 223.45 Go au total), avec le **même schéma de colonnes que CommitPackFT** (`commit`/`subject`/`message`/`old_contents`/`new_contents`/`old_file`/`new_file`/`repos`/`license`/`lang`/`returncode`/`stderr`) mais **aucun filtrage préalable** (c'est le corpus CommitPack complet, pas la version "FT" déjà nettoyée). C'est le "vrai" CommitPack 3.8 To (toutes langues) annoncé en attente de téléchargement dans `HANDOFF_2026-08-02.md` -- atterri directement sur `E:` (SSD dédié), comme CommitPackFT l'avait fait, pas sur le HDD `G:` supposé par la consigne d'origine. `E:\data\commitpack\python-traceback\` (1 shard, 15 Ko) exclu du périmètre après vérification : son champ `lang` vaut `"Python traceback"`, pas `"Python"` -- ce sont des dumps de traceback, pas du code source.

Nom de script et de sortie volontairement distincts de l'existant (`build_source_commitpack_full_python.py` / `dataset_source_commitpack_full_python.jsonl`, suffixe `_full_`) pour ne jamais écraser `dataset_source_commitpack_python.jsonl` (CommitPackFT, 2000 ex., déjà entraîné dans `training_stage1/runs/stage1_commitpack_full/`).

### Filtrage et résultat

Contrairement à toutes les sources précédentes (cible fixe choisie à l'avance), **aucun cap artificiel** n'a été appliqué au filtrage lui-même -- le volume final est décidé par les filtres de qualité, un sous-échantillonnage n'intervenant qu'en aval si le résultat dépasse 150 000 exemples.

- **Filtres** : `lang=="Python"` (0 rejet -- déjà vrai vu le répertoire source), sujet non trivial, `old_contents != new_contents`, `ast.parse()` validé sur `new_contents` (obligatoire), diff plafonné à 20000 caractères, `SECRET_PATTERNS`. Dédoublonnage par hash de commit **intra-shard seulement** (les 458 shards sont des partitions disjointes du même export, pas de recouvrement attendu).
- **Volume brut lu** : 6 429 891 lignes (commits) sur les 458 shards.
- **Rejets** : `skipped_invalid_python=1 354 976` (21.1% -- nettement plus élevé que les 8.5% de CommitPackFT, cohérent avec le fait que CommitPack brut n'est pas pré-nettoyé), `skipped_nochange=400 336`, `skipped_trivial=27 334`, `skipped_size=25 394`, `skipped_secret=458`, `skipped_duplicate=0`.
- **Total retenu avant sous-échantillonnage** : **4 621 393 exemples** (71.9% du volume lu) -- très au-dessus du seuil de 150 000, sous-échantillonnage déclenché.
- **Classification du type de commit** : heuristique (CommitPack n'a pas de champ structuré) -- préfixe conventionnel (`feat:`/`fix:`/`refactor:`/`perf:`) en priorité, sinon mots-clés anglais sur le sujet, sinon `other`. Répartition naturelle sur les 4.6M exemples retenus : `other` 60.4%, `fix` 19.9%, `feat` 17.1%, `refactor` 2.2%, `perf` 0.4% -- la part élevée d'`other` reflète le style réel des messages de commit open source (peu de convention stricte type Conventional Commits), pas un défaut du classifieur.
- **Sous-échantillonnage par réservoir stratifié** (Algorithme R, une passe supplémentaire bon marché sur les fichiers déjà filtrés) : cible proportionnelle à la répartition réelle par type jusqu'à 150 000 au total (`feat=25611, fix=29854, refactor=3341, perf=544, other=90650`) -- diversité préservée plutôt qu'une troncature aux X premiers exemples lus (biaisée par l'ordre des shards).
- **Durée** : 3358.1s (~56 min), 8 processus parallèles (12 coeurs logiques disponibles, 4 laissés libres pour ne pas affamer le Stage1 TheStack alors en cours sur la RTX 5080 avec délestage CPU).

Sortie : `E:\data\commitpack_full_python_subset\dataset_source_commitpack_full_python.jsonl` (SSD dédié) + copie de référence versionnée `workspace/qlora_dataset/dataset_source_commitpack_full_python.jsonl` -- **150 000 lignes, 323 Mo**, vérifiées sur disque (comptage de lignes aux deux emplacements, structure JSON et répartition par type recomptées depuis le fichier réel, pas seulement lues dans les logs de la console).

### Statut

Préparation de données uniquement -- **aucun entraînement lancé** sur ce sous-ensemble. Décision d'intégration au Stage 1 (à la place ou en complément de The Stack / CommitPackFT) non prise, hors périmètre de cette tâche.

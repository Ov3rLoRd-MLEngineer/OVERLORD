# Dataset QLoRA comportemental -- Session 2 -- Statistiques et recommandation

Généré le 2026-07-29. Préparation de données uniquement -- **aucun entraînement lancé**.

## Composition

| Fichier | Source | Format | Exemples |
|---|---|---|---|
| `dataset_source_a.jsonl` | Historique git du dépôt (103 commits non-merge) | Alpaca (`instruction`=sujet commit, `input`=corps du message, `output`=diff) | **67** |
| `dataset_source_b.jsonl` | Export JSON conversations Claude.ai (18 conversations, 3787 messages) | Alpaca (`instruction`=message humain, `input`="", `output`=réponse assistant) | **1470** |
| **Total** | | | **1537** |

Les deux fichiers restent **séparés** (styles différents : diffs de code isolés vs. dialogue "rapport d'architecte") -- à charger comme deux datasets distincts dans Unsloth, pas concaténés.

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

Scripts dans `scripts/` (`build_source_a.py`, `build_source_b.py`, `compute_stats.py`), exécutables via `py -3.12`. Les critères d'exclusion (mots-clés, UUIDs de messages, plafond de taille de diff) sont documentés en commentaire en tête de chaque script.

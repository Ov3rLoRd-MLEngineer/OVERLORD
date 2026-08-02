# LLM-Secours -- guide de reprise pour un LLM de remplacement

Ce document sert quand Claude Code n'est pas disponible (quota épuisé) et
qu'un autre outil (Grok, Copilot, un LLM local via Ollama, etc.) doit
reprendre le travail sur ce dépôt. Objectif : donner le minimum nécessaire
pour agir correctement en quelques minutes de lecture, pas remplacer la
documentation complète.

## À lire, dans cet ordre

1. **`CLAUDE.md`** (racine du dépôt) -- la référence. Toutes les conventions
   du projet, les décisions d'architecture (ADR), les règles GPU/contexte,
   les emplacements clés. Si un outil ne charge pas ce fichier
   automatiquement (contrairement à Claude Code), le lire explicitement
   avant toute action.
2. **Le `contexte_*.md` ou `CONTEXTE_OVERLORD_V*.md` le plus récent** (racine
   du dépôt, trier par date dans le nom) -- état du projet au moment de la
   dernière session, chantiers en cours/en pause/terminés.
3. **`DOCS/INDEX.md`** -- index des documents de référence (recherches
   techniques, ADR).
4. **`workspace/external_ai_sessions/`** -- logs des sessions faites par
   d'autres outils LLM sur ce dépôt (voir convention dans `CLAUDE.md` section
   "Économie de session et de tokens"). À consulter pour voir ce qu'un
   précédent passage (Grok, Copilot, Gemini...) a fait, et à alimenter avec
   ses propres logs en fin de session pour que la suite (Claude Code ou un
   autre outil) puisse reprendre le fil.
5. **`git log --oneline -20`** puis `git status` -- l'état réel du dépôt
   prime toujours sur ce que dit un document ou un rapport si les deux se
   contredisent.

## Règles non négociables (s'appliquent quel que soit l'outil)

- **Gestion de contexte 90%/92%** (`CLAUDE.md`) : à 90% de la fenêtre de
  contexte utilisée, conclure proprement ; à 92%, arrêt complet + commit +
  fichier de handoff. Ne jamais laisser un fichier à moitié écrit ou un
  process GPU orphelin.
- **Règles GPU** (`CLAUDE.md`) : vérifier `nvidia-smi` avant toute action
  GPU. Ne jamais tuer/redémarrer un process GPU sans consigne explicite. RTX
  5080 pour tests/entraînements/évaluations ponctuelles, RTX 5060 Ti pour
  l'inférence LLM de service continue.
- **`ast.parse()` obligatoire** sur tout fichier Python livré avant de le
  présenter comme terminé.
- **Jamais de commit sans demande explicite**, et jamais `git push` sans
  demande explicite. Commit isolé (fichiers pertinents seulement, pas `git
  add -A`).
- **Secrets** : `.env`/`.env.template` ne contiennent que des identifiants
  (ADR-005) -- ne jamais les afficher, committer ou citer en clair.
- **Vie privée** : ce dépôt applique un filtrage de contenu personnel
  systématique sur tout dataset construit depuis des conversations réelles
  (voir `PERSONAL_PATTERNS` dans `workspace/qlora_dataset/scripts/
  build_source_b.py`) -- à respecter si un nouveau dataset ou export de
  conversation est traité.
- **Traçage GPU** : tout run substantiel (entraînement, batch >50, diagnostic
  >15min) s'ajoute à `gpu_usage_log.csv` (racine).

## Erreurs déjà commises sur ce dépôt -- à ne pas répéter

Deux incidents réels trouvés et corrigés en session (2026-08-02), à titre
d'exemple concret de ce qui peut mal tourner :

1. **Ne jamais présenter un résultat d'évaluation/simulation comme réel sans
   vérifier que le code appelle vraiment un modèle.** Un script d'évaluation
   produit par un outil externe s'est avéré être une fonction codée en dur
   qui ne chargeait aucun modèle -- présentée comme une comparaison
   qualitative légitime, avec un "verdict anti-hallucination" entièrement
   fabriqué. Toujours lire le code d'un script avant de citer ses résultats,
   pas seulement sa sortie console.
2. **Ne jamais réutiliser le `run_name`/dossier de sortie d'un entraînement
   déjà réussi avec des paramètres réduits par défaut.** Un script pipeline
   a écrasé silencieusement un bon adaptateur (250 steps) avec une version
   sous-entraînée (60 steps) en réutilisant le même chemin de sortie.
   Toujours versionner/horodater un nouveau run, ou vérifier explicitement
   qu'un dossier de sortie n'existe pas déjà avant d'écrire dedans.

## Où trouver l'état du chantier QLoRA (personnalisation LLM local)

`workspace/qlora_dataset/STATS_ET_RECOMMANDATION.md` -- volumétrie et
recommandations à jour pour Source A/B/C + sous-ensembles publics
(CommitPack, evol-codealpaca, OpenCodeInstruct). `workspace/qlora_dataset/
training/VERDICT_EVALUATION_QUALITATIVE_V*.md` -- verdicts qualitatifs
successifs (V1 à V4), le plus récent fait foi. Le point non résolu depuis V1
: la fiabilité factuelle du modèle fine-tuné sur les détails du projet --
voir mémoire `qlora-local-llm-effort` côté Claude Code, ou directement le
dernier `VERDICT_*.md` pour le diagnostic complet.

## Comment vérifier qu'on a bien compris avant d'agir

Avant une tâche non triviale : relire le `contexte_*.md` le plus récent,
vérifier `git status`/`git log` pour confirmer que rien n'a changé depuis, et
si un doute existe sur une convention (GPU, format de dataset, structure
d'un module), chercher d'abord dans `CLAUDE.md` avant de deviner.

## En fin de session

Écrire un résumé court (ce qui a été fait, ce qui reste, tout blocage) dans
`workspace/external_ai_sessions/<nom_outil>/` (créer un fichier daté), pour
que la prochaine session -- avec ce même outil, un autre, ou Claude Code de
retour -- puisse reprendre sans perdre le contexte.

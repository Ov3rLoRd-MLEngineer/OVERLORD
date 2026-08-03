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

## Modèles de secours locaux pour Aider (génération de code)

Trois modèles locaux Ollama disponibles pour router des tâches de code vers
Aider quand Claude Code n'est pas disponible (quota épuisé). Lancement via
`workspace/scripts/aider_devstral.bat` pour le profil devstral ; les autres
utilisent le profil par défaut du dépôt (`~/.aider.conf.yml` :
`ollama_chat/qwen3-coder:30b-a3b-q4_K_M`, voir
`DOCS/MD/SETUP_AGENT_LOCAL_AIDER_QWEN3CODER.md`).

| Modèle | Rôle | num_ctx | Statut validé |
|---|---|---|---|
| `qwen3-coder:30b-a3b-q4_K_M` | Défaut du dépôt, premier jet sur tâches cadrées | 32768 | **Fiable** — plusieurs "Applied edit to..." confirmés sur historique réel (`.aider.chat.history.md`), voir `SETUP_AGENT_LOCAL_AIDER_QWEN3CODER.md` §5 |
| `ov3rlord-coder-stage2v2` | Fine-tune QLoRA maison (style Ov3rLoRd) | 32768 | Fiabilité **factuelle** non garantie sur les détails précis du projet (confabulation documentée, voir `VERDICT_EVALUATION_QUALITATIVE_V5.md` / mémoire `qlora-local-llm-effort`) — à coupler avec le RAG (`DOCS/RAG_SOURCES.md`), pas à utiliser seul pour des faits précis. Pas testé pour la fiabilité d'application de diff cette session. |
| `qwen2.5-coder:14b-instruct-q4_K_M` | Alternative plus légère (9 Go) que qwen3-coder | Non plafonné explicitement dans `~/.aider.model.settings.yml` — à faire avant usage réel (même piège `std::bad_alloc` que qwen3-coder si le num_ctx par défaut du modèle est trop grand) | **Non testé cette session** (modèle présent dans `ollama list`, jamais exercé sur une tâche réelle via Aider) — à valider avant adoption, ne pas présumer fiable sur la seule base de sa présence locale |
| `devstral:24b` | Alternative de secours (14 Go) | 16384 (`~/.aider.model.settings.yml`, pas 32768 — VRAM 5060 Ti trop juste avec un modèle de cette taille) | **⚠️ Cassé avec Aider** (3/3 tests échoués, fences 4 backticks) — voir limite connue ci-dessous. **Utilisable en contournement via `workspace/scripts/devstral_agent.py`** (appel direct API Ollama, pas de fence markdown, diff calculé par `difflib` — testé réellement, fonctionne, voir section dédiée). |

### Limite connue critique — devstral:24b émet des fences markdown à 4 backticks

Testé le 2026-08-03 sur une tâche minimale et réelle (ajouter un commentaire
d'une ligne dans `gpu_cost_estimate.py`, fichier non critique) : **3
tentatives sur 3 ont échoué silencieusement**, avec les deux `--edit-format`
concernés (`whole`, celui choisi par défaut par Aider pour ce modèle, et
`diff`/SEARCH-REPLACE, forcé explicitement pour un second essai) :

- Le modèle produit un texte de réponse cohérent et correct sur le fond (le
  commentaire proposé était pertinent, en français correctement accentué
  dans `.aider.chat.history.md` — le rendu console mojibake observé dans le
  terminal était un artefact d'affichage, pas une corruption réelle du
  texte).
- **Mais il entoure systématiquement son bloc de code de 4 backticks
  (` ```` `) au lieu des 3 attendus par le parseur Aider** (confirmé par
  `grep` direct sur `.aider.chat.history.md` : les fences des sessions
  qwen3-coder passées sont à 3 backticks, celles de devstral à 4, dans le
  même fichier). Résultat : Aider ne reconnaît pas le bloc comme une
  édition, n'affiche **aucune erreur**, ne modifie **aucun fichier sur
  disque**, ne crée **aucun commit** — juste un message de chat normal.
  Reproduit à l'identique même après avoir explicitement demandé au modèle
  d'utiliser des triple-backticks dans le prompt.
- **Piège de la même famille que celui déjà documenté pour qwen3-coder**
  (mémoire `aider-qwen3coder-setup` : succès affiché dans le terminal, mais
  rien d'appliqué en réalité) — confirme la règle "toujours vérifier `git
  status`/`git log`/le fichier réel après un run Aider, jamais se fier au
  texte affiché", ici avec une cause racine précise identifiée (longueur de
  fence) plutôt qu'un artefact de rendu terminal.
- **Vérifié aussi que le GPU pinning fonctionne correctement** pendant ces
  tests (`nvidia-smi` : devstral chargé à 13,9 Go sur la RTX 5060 Ti,
  RTX 5080 non touchée) — le problème est uniquement le format de sortie du
  modèle, pas l'infrastructure GPU/Ollama.
- Non testé : post-traitement de la réponse du modèle pour normaliser les
  fences avant qu'Aider ne les parse (nécessiterait de patcher Aider
  lui-même ou d'écrire un wrapper, hors périmètre d'une simple config Aider).

**Recommandation** : ne pas router de tâche réelle vers `devstral:24b` via
Aider sur cette machine tant que ce comportement n'est pas corrigé ou
contourné. `workspace/scripts/aider_devstral.bat` reste en place
(fonctionnel pour discuter/lire du code, juste pas pour appliquer des
edits) au cas où une future version d'Ollama/Aider ou un changement de
prompt système résoudrait le problème — à retester avant réactivation.

### Contournement fonctionnel — `workspace/scripts/devstral_agent.py`

Ajouté le 2026-08-03 : wrapper CLI qui appelle directement l'API Ollama
(`/api/chat`, sans passer par Aider) et **contourne le bug ci-dessus en ne
dépendant d'aucune fence markdown** — le modèle est instruit de répondre
entre deux marqueurs texte simples (`===DEVSTRAL_FILE_BEGIN===`/
`===DEVSTRAL_FILE_END===`), et c'est le script lui-même qui calcule le
diff unifié final via `difflib.unified_diff()`, pas le modèle. Le diff
affiché est donc toujours bien formé quel que soit le nombre de backticks
que le modèle choisit.

Usage :
```
py -3.12 workspace/scripts/devstral_agent.py --target <fichier> --task <fichier_tache.txt> [--context <fichier> ...] [--yes]
```

**Testé réellement (pas simulé)** sur une copie de `gpu_cost_estimate.py`
(commentaire d'une ligne demandé) : diff généré et appliqué avec succès,
vérifié sur disque après coup (`grep` sur le fichier modifié). Testé aussi
le chemin de refus (`n` à la confirmation, avec `--context CLAUDE.md`) :
diff affiché mais fichier inchangé, vérifié par hash SHA1 avant/après.

**Limite connue** : contrairement à un vrai diff ciblé (SEARCH/REPLACE),
le modèle régénère le **fichier entier** à chaque appel — testé deux fois
sur la même tâche, les deux runs ont introduit une modification
incidente non demandée (suppression de lignes vides entre définitions de
fonctions, style PEP8 différent) en plus du changement demandé. Ce n'est
pas un bug du script (le diff reflète fidèlement ce que le modèle a
réellement renvoyé) mais un risque inhérent à l'approche "fichier entier"
— **toujours lire le diff affiché avant de confirmer**, ne pas supposer
que seul le changement demandé sera présent. `--yes` (application sans
confirmation) est donc déconseillé en usage interactif, réservé à un
usage scripté où le diff est vérifié par un autre moyen (lint, tests).

### Critère de routage (une fois devstral fiable, ou en l'état pour les deux autres)

- **Tâche de code cadrée, fichier(s) identifié(s), pas de raisonnement
  architectural** → `qwen3-coder:30b-a3b-q4_K_M` (seul confirmé fiable
  aujourd'hui).
- **Question factuelle précise sur le projet** → coupler avec le RAG
  (`agents/infra/rag_query.py`) quel que soit le modèle, ne jamais faire
  confiance à `ov3rlord-coder-stage2v2` seul sur ce point.
- **Tâches multi-fichiers complexes** → à éviter pour tous les modèles
  locaux listés ici, quel que soit le num_ctx — réservé à Claude Code
  (raisonnement multi-étapes, voir `SETUP_AGENT_LOCAL_AIDER_QWEN3CODER.md`
  §4).

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

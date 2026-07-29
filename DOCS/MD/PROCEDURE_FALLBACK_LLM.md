# Procédure de secours — Aider + qwen3-coder (si Claude Code indisponible)

Objectif : relais court, actionnable sous pression, quand le quota Claude
Code est épuisé.

**Statut (2026-07-29, session de fiabilisation dédiée) : FIABLE via le
wrapper `agents/aider_fallback_run.py`, pas fiable en appel direct.**
L'échec silencieux documenté précédemment (fichier vide malgré un exit
code 0) a une cause identifiée et un correctif vérifié — voir §0. **N'appelle
jamais `aider.exe` directement pour ce cas d'usage : passe toujours par le
wrapper**, qui applique les deux correctifs et vérifie le résultat sur
disque + git avec relance automatique.

## 0. Diagnostic (pour référence — ne pas ré-inventer si ça recasse)

Deux bugs indépendants, confondus dans le constat initial ("3/3 échecs") :

1. **Crash d'encodage sous Git Bash** (`UnicodeEncodeError: 'charmap' codec`,
   déterministe, 100% reproductible avant fix). Cause : dès que `stdout` est
   redirigé (non-tty — le cas de tout run `--message`), Python bascule sur
   `locale.getpreferredencoding()` pour l'encodage de sortie plutôt que sur
   la page de codes de la console. Sur ce système (Windows FR), ça donne
   `cp1252`, indépendamment de la page de codes réelle de la console
   (`chcp` renvoyait 850 dans le Git Bash de test). Le rendu Rich d'Aider
   (mode "legacy Windows console") tente d'encoder la réponse du modèle
   (accents, emoji ⚠️/✅) via ce `cp1252` et plante avant même d'atteindre
   l'étape d'application de l'édition. **Fix vérifié** : forcer
   `PYTHONIOENCODING=utf-8` et `PYTHONUTF8=1` dans l'environnement avant le
   lancement — supprime le crash à 100% sur les essais de cette session (0
   crash sur 9 lancements Git Bash après fix, contre crash systématique
   avant). N'affecte pas PowerShell (déjà en UTF-8 par défaut sur cette
   machine, `chcp` → 65001), donc sans danger de l'appliquer partout.

2. **Édition non appliquée malgré une réponse valide du modèle** (le vrai
   "échec silencieux" — fichier à 0 octet, exit code 0, aucun message
   d'erreur visible). Cause : qwen3-coder produit occasionnellement une
   réponse dont le bloc d'édition (fence de fermeture surnuméraire en
   format "whole", ou bloc SEARCH/REPLACE mal formé en format "diff") n'est
   pas reconnu par le parseur d'Aider. Aider ne signale pas franchement
   l'échec — il relance en interne un 2e tour avec un message de réflexion
   dégénéré (le texte envoyé au modèle se réduit littéralement au mot
   `python`, un bug d'Aider 0.86.2 dans la construction de ce message), ce
   qui fait dérailler le modèle ("je ne vois pas de demande de
   modification..."). **Comportement probabiliste, pas déterministe** :
   sur les 9 tâches de validation de cette session, échec du 1ᵉʳ tour
   observé sur ~6/9, mais succès quasi systématique dans les 1-2 tours
   suivants (internes à Aider ou via une relance externe fraîche).
   **Pas de fix déterministe trouvé** côté configuration (le format
   `--edit-format diff` n'a pas éliminé le phénomène, juste changé sa forme).
   **Palliatif retenu** : ne jamais faire confiance à un seul lancement —
   le wrapper (§1) vérifie systématiquement le résultat sur disque + git et
   relance un **process Aider entièrement frais** (pas une poursuite de
   conversation) en cas d'échec silencieux détecté.
   - Validation : 9/9 tâches simples ont fini par produire un fichier
     réel, syntaxiquement valide (`ast.parse`) et commité, en 2 tentatives
     du wrapper au maximum (aucune n'a eu besoin des 3 autorisées).
   - Testé sur Git Bash et PowerShell natif — les deux fonctionnent une
     fois les deux fixes appliqués (le wrapper les applique automatiquement,
     plus besoin de bannir Git Bash comme le disait la version précédente
     de ce document).
   - **Quirk résiduel mineur, cosmétique uniquement** : sous PowerShell, le
     *message de commit* généré par Aider peut apparaître en mojibake
     (`vÃ©rifie` au lieu de `vérifie`) malgré `PYTHONIOENCODING=utf-8` — le
     contenu du fichier committé, lui, reste en UTF-8 correct (vérifié par
     lecture directe + `ast.parse` sur chaque cas rencontré). Cause exacte
     non investiguée plus loin (piste : encodage des arguments passés à
     `git commit -m` par Aider sous PowerShell) — sans impact sur la
     fiabilité, juste sur la lisibilité du message de commit.

## 1. Lancer une tâche (méthode recommandée — via le wrapper)

```powershell
cd D:\OVERLORD
py -3.12 agents\aider_fallback_run.py chemin\du\fichier.py "Description precise et cadree de la tache."
```

Fonctionne identiquement depuis Git Bash :

```bash
cd /d/OVERLORD
py -3.12 agents/aider_fallback_run.py chemin/du/fichier.py "Description precise et cadree de la tache."
```

Le wrapper :
- force `PYTHONIOENCODING=utf-8` / `PYTHONUTF8=1` (fix §0.1) ;
- lance Aider avec `--yes-always --no-stream --edit-format diff` ;
- vérifie après coup, sur disque + git (jamais la sortie terminal) : le
  fichier existe, n'est pas vide, est lisible en UTF-8, passe `ast.parse()`,
  et a bien été commité (pas juste `untracked`) ;
- si un de ces contrôles échoue, relance un **nouveau process Aider**
  (jusqu'à 3 tentatives, configurable via `--retries`) — jamais la même
  conversation ;
- écrit un log par tentative dans
  `workspace/logs/aider_fallback_wrapper/<fichier>_attempt<N>.log` ;
- code de sortie 0 seulement si le résultat est vérifié bon.

**Si le wrapper échoue après ses 3 tentatives** : ne pas insister avec
d'autres relances du même wrapper — c'est le signal que la tâche sort du
périmètre raisonnable (voir §2) ou qu'Ollama/le modèle a un problème plus
profond (`curl -s http://127.0.0.1:11434/api/tags` pour vérifier qu'Ollama
répond). Traiter la tâche par un autre moyen (Claude Code dès que
disponible, ou manuellement).

### Appel direct à `aider.exe` (déconseillé, dépannage seulement)

Si le wrapper lui-même est indisponible, l'appel direct reste possible mais
**exige la vérification manuelle systématique** (le bug §0.2 n'est pas
éliminé, seulement absorbé par la relance du wrapper) :

```powershell
$env:PYTHONIOENCODING = "utf-8"
$env:PYTHONUTF8 = "1"
& "C:\Users\Ov3rL0rD\.aider\venv\Scripts\aider.exe" --yes-always --no-stream --edit-format diff `
  --message "Description precise et cadree de la tache." `
  chemin\du\fichier.py
```

Puis, obligatoire, jamais optionnel :

```powershell
Get-Item chemin\du\fichier.py | Select-Object Length   # doit etre > 0
git log --oneline -1 -- chemin\du\fichier.py
git status --short -- chemin\du\fichier.py             # ne doit pas etre "??"
```

Si vide/non commité malgré un exit code 0 : c'est l'échec connu du §0.2,
pas une fausse alerte — relancer (nouveau process) ou passer au wrapper.

## 2. Quel type de tâche confier ici

- **Oui** : scripts utilitaires autonomes et bien cadrés, refactoring
  mécanique, code répétitif — cf. `SETUP_AGENT_LOCAL_AIDER_QWEN3CODER.md`
  §4/§5/§1ter pour les cas déjà validés (9 tâches de ce type validées cette
  session : vérif espace disque, comptage de lignes, lecture de variable
  d'env, décorateur retry, vérif de port TCP, etc.)
- **Non** : diagnostic multi-étapes, décisions sur des cas ambigus
  nécessitant un jugement contextuel (vérifications de licence, arbitrages
  sur des défauts génératifs, architecture nouvelle) — hors du périmètre
  pour lequel ce mécanisme a même été envisagé, pas seulement "risqué".

## 3. Après coup

Relire le diff produit avant de le considérer acquis — même en l'absence
de Claude Code, une relecture humaine rapide (`git diff HEAD~1`) reste plus
sûre qu'une confiance aveugle au message de succès du terminal (le wrapper
vérifie l'application de l'édition, pas sa qualité).

## Historique

- 2026-07-26 : premier test de fiabilité (`agents/gpu_vram_check.py`),
  verdict optimiste (échecs attribués à un artefact terminal Git Bash).
- 2026-07-29 (session 1) : test approfondi (`agents/disk_free_check.py`),
  3 tentatives sur 3 échouées sous Git Bash et PowerShell — verdict revu à
  la baisse, mécanisme déclaré non fiable en mode automatisé.
- 2026-07-29 (session 2, celle-ci) : cause racine identifiée pour les deux
  modes d'échec (§0), correctif appliqué et vérifié sur 9 tâches
  répétées sur les deux shells — mécanisme déclaré fiable **via le
  wrapper**, pas en appel direct.

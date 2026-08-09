# Commandes slash — hermes-agent (Nous Research)

Tâche H-013 (protocole Hermes). Application tierce, installée localement à
`C:\Users\Ov3rL0rD\AppData\Local\hermes\hermes-agent` (pas le dépôt OVERLORD).
Ce document couvre uniquement les commandes de cette appli — pas le pipeline
Ov3rLoRd. Toutes les lignes `source:` ci-dessous sont des chemins relatifs à
cette racine, pas à `D:\OVERLORD`.

Méthode : lecture directe du code (registre central + gestionnaires +
dispatchers), pas de supposition. Quand un comportement n'a pu être vérifié
qu'à la lecture (pas d'exécution réelle possible dans cet environnement — pas
de TUI interactive ni de gateway lancé), c'est noté **« non testé, déduit du
code »**. Aucun fichier de hermes-agent n'a été modifié.

## 0. Architecture du système de commandes (lis ça avant tout le reste)

Il n'y a **pas** trois systèmes de commandes séparés (CLI / TUI / gateway) —
il y en a **un seul registre**, consommé par trois surfaces :

- **Registre central** : `hermes_cli/commands.py::COMMAND_REGISTRY` (une
  liste de `CommandDef`, ~lignes 102-345). Chaque commande y déclare : nom
  canonique, alias, description, catégorie, `args_hint`, `subcommands`,
  `cli_only` / `gateway_only` (ou disponible partout), et une politique de
  comportement « agent occupé » (`busy_policy`).
- **Résolution** : `resolve_command(name)` (ligne 365) — mappe un nom ou un
  alias vers son `CommandDef`, insensible à la casse, `/` optionnel en tête.
- **Dispatch CLI/TUI** : `cli.py::process_command()` (ligne 9952) — résout
  la commande via `resolve_command`, puis un `elif canonical == "..."` géant
  vers la méthode `_handle_*_command` correspondante (la plupart dans
  `hermes_cli/cli_commands_mixin.py`, certaines directement dans `cli.py`).
- **Dispatch gateway** (Telegram/Discord/Slack/WhatsApp/Matrix/API...) :
  `gateway/run.py::_handle_message()` (~ligne 15304) — même logique de
  résolution (`_resolve_cmd`), puis un `if canonical == "..."` vers
  `self._handle_*_command` (dans `gateway/slash_commands.py`, un mixin de
  `GatewayRunner`, ~42-51 gestionnaires, ~3200 lignes).
- **`/help` et `/commands` (les deux surfaces) sont générés depuis le
  registre**, pas maintenus à la main : `gateway_help_lines()`
  (`hermes_cli/commands.py:552`) itère `COMMAND_REGISTRY` et produit une
  ligne par commande visible sur la surface courante ; c'est la fonction que
  consomme `_exec_help`/`_exec_commands` côté gateway
  (`hermes_cli/slash_exec.py:143,168`) ET `cli.py::show_help()` (ligne 7799,
  via `COMMANDS_BY_CATEGORY`, dérivé du même registre). **Donc pas de dérive
  possible entre le code et la sortie de `/help`** — voir section 3.

**Point de vigilance pour toi (Jérémy)** : `cli_only=True` = commande TUI/CLI
uniquement, invisible/indispatchable depuis Telegram etc. `gateway_only=True`
= l'inverse (rare, propre aux plateformes de messagerie : `/pause`,
`/approve`, `/deny`, `/platform`, `/restart`, `/sethome`, `/topic`,
`/start`, `/commands`). Le reste (majorité) marche des deux côtés. Deux
commandes CLI-only redeviennent visibles côté gateway si un réglage
`config.yaml` précis est activé (`gateway_config_gate`) : `/verbose`
(`display.tool_progress_command`) et `/skills` (`skills.write_approval`,
volet revue seulement, pas le hub complet).

Chiffres exacts extraits du registre (`len(COMMAND_REGISTRY)` = 95) :
**95 commandes canoniques**, **26 alias**, soit **121 noms invocables**.
33 CLI-only, 9 gateway-only, 51 disponibles sur les deux (+2 CLI-only
débloquées côté gateway par config).

---

## 1. Modèles & reasoning (section demandée en priorité — suite de H-012)

### `/model`

- **Syntaxe** :
  ```
  /model                                # liste/picker interactif (pas de config.yaml)
  /model <name>                         # change de modèle — session courante seulement
  /model <name> --once                  # un seul tour, puis restauration automatique
  /model <name> --session               # explicite, équivalent au défaut
  /model <name> --global                # persiste dans config.yaml (model.default/provider)
  /model <name> --provider <provider>   # change provider + modèle
  /model --provider <provider>          # change de provider, modèle auto-détecté
  /model --refresh                      # vide le cache disque de la liste de modèles
  ```
- **Effet réel** : sans flag, la commande stocke un override dans
  `self._session_model_overrides[session_key]` (gateway) ou en mémoire de
  process (CLI) — **rien n'est écrit sur disque**. `--global` appelle
  `switch_model(..., persist=True)` qui écrit `model.default` /
  `model.provider` dans `config.yaml` via `hermes_cli/model_switch.py`.
  `--once` prend un snapshot (`_snapshot_session_model_override`) et le
  restaure après le tour suivant. Sans argument, un picker interactif
  s'affiche sur les plateformes qui le supportent (Telegram/Discord ont
  `send_model_picker`), sinon une liste texte.
- **Persistant ou ponctuel** : **ponctuel par défaut** (session), seul
  `--global` persiste. `--once` est encore plus éphémère (un tour).
- **Source** :
  - Registre : `hermes_cli/commands.py:198-200`
  - Parseur partagé (session/global/once) : `hermes_cli/model_switch.py`
    (`parse_model_switch_args`, `resolve_persist_behavior`)
  - Gestionnaire gateway : `gateway/slash_commands.py:1671-2447`
  - Gestionnaire CLI : `cli.py:9426` (`_handle_model_switch`) — note son
    docstring : « Persistence defaults to off
    (`model.persist_switch_by_default` in config.yaml, default False) »,
    donc même un réglage config peut changer le défaut sans `--global`
    explicite — **à vérifier dans ton `config.yaml` actuel si le
    comportement observé surprend**.
- **Exemple** : `/model qwen3-coder --provider openrouter --global`

### `/reasoning`

- **Syntaxe** :
  ```
  /reasoning                       # affiche le niveau courant + l'état d'affichage
  /reasoning <level>                # change l'effort — session courante seulement
  /reasoning <level> --global       # persiste dans config.yaml (agent.reasoning_effort)
  /reasoning reset                  # supprime l'override de session
  /reasoning show | on               # affiche le raisonnement du modèle dans les réponses
  /reasoning hide | off              # le masque
  /reasoning full | all              # (CLI/TUI seulement) recap complet dans la boîte post-réponse
  /reasoning clamp | collapse | short # (CLI/TUI seulement) recap limité à 10 lignes
  ```
- **Niveaux valides** (source de vérité, déjà pointée en H-012) :
  `hermes_constants.py` ligne ~942, `VALID_REASONING_EFFORTS = ("minimal",
  "low", "medium", "high", "xhigh", "max", "ultra")` + `"none"` traité à part
  par les deux gestionnaires. `parse_reasoning_effort()` (même fichier) est
  le point d'entrée unique de validation, utilisé par les deux surfaces
  (CLI et gateway) — pas de double logique.
- **Effet réel** : sans `--global`, écrit un override en mémoire
  (`_set_session_reasoning_override`) et **évince l'agent en cache**
  (`_evict_cached_agent`) pour que le prochain message reconstruise l'agent
  avec le nouvel effort — donc effet visible dès le tour suivant, pas besoin
  de `/new`. `--global` écrit `agent.reasoning_effort` dans `config.yaml`.
  `show`/`hide` (alias `on`/`off`) sont un **réglage d'affichage séparé** de
  l'effort — persisté par plateforme via
  `display.platforms.<platform>.show_reasoning` côté gateway, et
  `display.show_reasoning` côté CLI (pas de scope session, toujours
  persisté sur disque dès le toggle).
  `full`/`clamp` (CLI/TUI uniquement, absents du gestionnaire gateway) ne
  touchent pas l'effort mais la longueur du récap affiché après coup ;
  persisté dans `display.reasoning_full` (bool).
- **Persistant ou ponctuel** : effort = ponctuel (session) sauf
  `--global` ; affichage (`show`/`hide`, `full`/`clamp`) = **toujours
  persisté sur disque**, pas de notion de session pour ces deux-là.
- **Source** :
  - Registre : `hermes_cli/commands.py:234-236`
  - Constantes/validation : `hermes_constants.py:~942` (`VALID_REASONING_EFFORTS`,
    `parse_reasoning_effort`)
  - Gestionnaire gateway : `gateway/slash_commands.py:3497-3496` (handler) +
    `gateway/slash_commands.py:3374-3457` (`_apply_reasoning_selection`,
    `_reasoning_picker_choices` — logique d'application partagée entre
    saisie tapée et picker interactif)
  - Gestionnaire CLI (avec `full`/`clamp`) :
    `hermes_cli/cli_commands_mixin.py:3193-3291`
- **Exemple** : `/reasoning ultra --global` puis `/reasoning show`

### `/fast`

- **Syntaxe** : `/fast [normal|fast|status] [--global]`
- **Effet réel** : bascule le mode « traitement prioritaire »
  (OpenAI Priority Processing / Anthropic Fast Mode). Session-scoped par
  défaut ; `--global` persiste `agent.service_tier` dans `config.yaml` —
  même schéma exact que `/model` et `/reasoning` (parité assumée dans le
  docstring).
- **Persistant ou ponctuel** : ponctuel sauf `--global`.
- **Source** : registre `hermes_cli/commands.py:237-239` ; gateway
  `gateway/slash_commands.py:3692` ; CLI
  `hermes_cli/cli_commands_mixin.py:3375`.

### `/codex-runtime` (alias `/codex_runtime`)

- **Syntaxe** : `/codex-runtime [auto|codex_app_server|on|off]`
- **Effet réel** : bascule entre le runtime par défaut de Hermes
  (`chat_completions`) et un sous-processus `codex` (app-server) pour les
  modèles OpenAI/Codex. `on`/`off` sont des synonymes de
  `codex_app_server`/`auto`. Change de valeur → agent en cache évincé pour
  cette session (rechargement au prochain message).
- **Persistant ou ponctuel** : persisté (écrit en config via
  `hermes_cli.codex_runtime_switch`), pas de notion de session pour ce
  réglage — contrairement à `/model`/`/reasoning`/`/fast`, pas de flag
  `--global` documenté : la commande persiste directement.
- **Source** : registre `hermes_cli/commands.py:201-204` ; CLI
  `cli.py:9703` ; gateway `gateway/slash_commands.py:2447`.

---

## 2. `/steer` — rappel H-012 + précision de portée trouvée ici

Déjà documenté en H-012 (`STEER_CHANNEL_NOTE`, marqueur persistant dans
l'historique). Complément trouvé en creusant le dispatcher :

- **Deux chemins bien distincts selon qu'un agent tourne ou non** :
  1. **Agent en cours d'exécution** (`busy_policy="dispatch"`,
     `busy_handler="steer"` dans le registre) : le texte est injecté
     **au milieu du tour actif** via `running_agent.steer(steer_text)`
     (`gateway/run.py:9072-9101`), qui l'enveloppe dans le marqueur
     `STEER_MARKER_OPEN`/`STEER_MARKER_CLOSE` (`agent/prompt_builder.py:661-671`)
     et l'ajoute en fin du dernier résultat d'outil — **c'est ce marqueur qui
     reste dans l'historique de façon persistante** (confirmé, ligne 659 :
     « the marker remains in immutable conversation history after
     delivery »).
  2. **Aucun agent actif** : le dispatcher central de `gateway/run.py`
     (canonical == "steer", ligne 15674) traite `/steer <texte>` comme un
     **message utilisateur normal** — pas de marqueur, pas d'injection
     mid-tour, juste `event.text = steer_payload` puis passage au flux
     normal. Sans payload : renvoie `"Usage: /steer <prompt> (no agent is
     running; sending as a normal message)"`.
- **Persistant** : oui pour le chemin (1) — le marqueur OOB reste dans
  l'historique de conversation immuable et est retransmis à chaque appel API
  suivant (c'est le comportement documenté comme voulu, pas un bug).
- **Source** : `agent/prompt_builder.py:650-689` ; dispatch
  `gateway/run.py:9036-9101` (mode busy) et `gateway/run.py:15674-15688`
  (fallback sans agent actif) ; registre `hermes_cli/commands.py:160-161`.

---

## 3. `/help` et `/commands` : couverture réelle vs registre

**Il n'existe pas d'écart entre `/help`/`/commands` et le code** — les deux
sont des vues générées automatiquement à partir du même
`COMMAND_REGISTRY`, sur les trois surfaces :

| Surface | Fonction | Source |
|---|---|---|
| Gateway `/help` | `_exec_help` → `gateway_help_lines()` | `hermes_cli/slash_exec.py:143` + `hermes_cli/commands.py:552` |
| Gateway `/commands` | `_exec_commands` (paginé, inclut aussi les commandes de skills) | `hermes_cli/slash_exec.py:168` |
| CLI/TUI `/help` | `show_help()` → `COMMANDS_BY_CATEGORY` | `cli.py:7799` (dérivé de `hermes_cli/commands.py:389-395`) |

Nuances trouvées :

- `gateway_help_lines()` ne liste que les commandes visibles sur la surface
  courante (`_is_gateway_available` — exclut les `cli_only` sauf gate
  config actif). Donc **`/help` côté Telegram n'affiche jamais** `/config`,
  `/tools`, `/skin`, `/pet`, etc. — c'est voulu (elles n'y sont pas
  exécutables), pas un oubli de doc.
  côté CLI, `show_help()` filtre symétriquement via
  `self._command_available(cmd)` (non lu en détail, mais même principe :
  exclut les commandes `gateway_only`).
- La description affichée par `/help` est le **résumé d'une ligne** du
  `CommandDef.description` — les nuances de persistance (`--global` vs
  session, ce que fait exactement `/steer`, etc.) **n'y figurent pas** :
  c'est exactement le trou que ce document comble. `/help` te dit *que*
  la commande existe et sa syntaxe minimale (`args_hint`), pas son
  comportement de fond — cohérent avec ton expérience de découverte "au fil
  des bugs".
- `/commands` (gateway seulement, absent en CLI où `/help` fait déjà tout
  tenir) est la version paginée et plus complète : elle ajoute aussi les
  commandes de **skills installées** (`get_skill_commands()`), que `/help`
  tronque à 10 avec un renvoi vers `/commands`.

**Conclusion pour la tâche** : pas de « écart » à corriger dans le code —
`/help` est structurellement synchronisé avec `COMMAND_REGISTRY` par
construction. L'écart est entre *« liste des commandes »* (ce que `/help`
donne) et *« comment elles se comportent »* (ce que ce document donne).

---

## 4. Référence complète par catégorie

Format : `/nom` (alias) — `args_hint` [surface] — effet — persistance —
source. Les descriptions sont reformulées à partir du docstring du
gestionnaire réel (jamais devinées) ; quand seul le docstring a pu être lu
(pas de trace d'exécution possible ici), c'est signalé.

### Session

| Commande | Alias | Surface | Effet | Persistance |
|---|---|---|---|---|
| `/new` | `/reset` | CLI+GW | Nouvelle session (ID + historique neufs) ; `<name>` optionnel définit le titre ; confirmation destructive avant exécution. Coupe aussi les délégations async en cours de la session sortante. | Ponctuel (rotation d'ID) mais **destructif** pour l'historique en cours |
| `/topic` | — | GW only | Active/inspecte les sessions par sujet Telegram DM. `[off|help|session-id]` | Persisté (liaison sujet↔session) |
| `/clear` | — | CLI only | Efface l'écran + nouvelle session (confirmation destructive) | Destructif, ponctuel |
| `/redraw` | — | CLI only | Force un redessin complet du terminal (récupération après dérive d'affichage, ex. changement d'onglet tmux) | Aucun effet sur l'état, purement visuel |
| `/history` | — | CLI only | Affiche l'historique de conversation | Lecture seule |
| `/save` | — | CLI only | Sauvegarde la conversation courante sur disque | Écrit un fichier |
| `/retry` | — | CLI+GW | Renvoie le dernier message utilisateur à l'agent | Ponctuel |
| `/prompt` | `/compose` | CLI only | Ouvre `$EDITOR` pour composer le prochain message (markdown), l'envoie à la fermeture | Ponctuel |
| `/undo` | — | CLI+GW | `[N]` — annule les N derniers tours utilisateur (soft-delete en base, `active=0`, récupérable) ; confirmation destructive ; évince l'agent en cache pour reconstruire le contexte tronqué | Persistant (marquage soft-delete en DB), mais réversible en théorie via la DB |
| `/title` | — | CLI+GW | `[nom]` — définit/affiche le titre de session | Persisté (SessionDB) |
| `/handoff` | — | CLI only | `<platform>` — transfère la session CLI vers une plateforme gateway (Telegram, Discord...) ; refuse si un agent tourne | Change l'état de session |
| `/branch` | `/fork` | CLI+GW | `[nom]` — clone l'historique de conversation dans une nouvelle session indépendante | Crée une nouvelle session persistée |
| `/compress` | `/compact` | CLI+GW | Compresse le contexte conversationnel ; `here [N]` garde les N derniers tours, `focus <sujet>`, `--preview/--dry-run` pour prévisualiser sans agir | Modifie l'historique effectif envoyé au modèle |
| `/rollback` | — | CLI+GW | Liste/diff/restaure des checkpoints filesystem ; `<N>` restaure (annule aussi le dernier tour de chat), `diff <N>` prévisualise, `<N> <fichier>` restaure un seul fichier | Modifie le filesystem du projet en cours |
| `/snapshot` | `/snap` | CLI only | `[create [label]|restore <id>|prune [N]]` — snapshots légers de la config/état Hermes (pas le filesystem projet, voir `/rollback`) | Écrit/lit des snapshots sur disque |
| `/stop` | — | CLI+GW | Tue tous les processus/délégations en arrière-plan ; distinct de l'interruption de tour (Ctrl+C) — inspiré de la séparation OpenAI Codex | Ponctuel |
| `/pause` | — | GW only | Stop d'urgence global (« `off` » pour reprendre) — bloque tout nouveau travail sur la gateway entière | Persiste tant que non levé |
| `/approve` | — | GW only | Débloque la/les commande(s) dangereuse(s) en attente ; `all` résout tout | Ponctuel |
| `/deny` | — | GW only | Rejette la/les commande(s) en attente ; `all`, `<raison>` optionnelle relayée à l'agent | Ponctuel |
| `/background` | `/bg`, `/btw` | CLI+GW | `<prompt>` — lance un nouvel agent dans une session séparée en arrière-plan ; le résultat revient au chat sans toucher l'historique de la session active | Ponctuel (nouvelle session isolée) |
| `/agents` | `/tasks` | CLI+GW | Affiche les agents actifs / tâches en cours | Lecture seule |
| `/journey` | `/learning`, `/memory-graph` | CLI only | `[list\|delete <id>\|edit <id>]` — timeline d'apprentissage (mémoire/skills appris) | Lecture + édition sur demande |
| `/queue` | `/q` | CLI+GW | `<prompt>` — met en file pour le prochain tour sans interrompre l'agent en cours | Ponctuel |
| `/steer` | — | CLI+GW | Voir section 2 dédiée | Persistant si agent actif (marqueur en historique) |
| `/goal` | — | CLI+GW | `[texte \| draft <texte> \| show \| gate add <cmd> \| pause \| resume \| clear \| status \| wait <pid> \| unwait]` — objectif permanent que l'agent poursuit sur plusieurs tours jusqu'à satisfaction | Persisté (état de session) tant que non `clear` |
| `/heartbeat` | `/hb` | CLI+GW | `[every <intervalle> <prompt> \| status \| pause \| resume \| clear]` — instruction récurrente réinjectée quand la session est inactive ; scope process, PAS un cron durable (voir `/cron` pour ça) | Persisté (état de session), en mémoire process |
| `/refine` | — | CLI+GW | `[instructions de focus]` — lance à la demande la revue mémoire/skills qui tourne normalement automatiquement en fin de tour ; écrit en arrière-plan sans toucher la conversation live | Écrit en mémoire/skills store (fork séparé) |
| `/moa` | — | CLI+GW | `<prompt>` — un seul prompt passé à travers le preset Mixture-of-Agents par défaut, puis restauration du modèle précédent. Sucre one-shot ; pour *changer* durablement vers un preset MoA, passer par `/model` (les presets MoA apparaissent comme provider virtuel) | Ponctuel, restauration automatique |
| `/subgoal` | — | CLI+GW | `[texte \| remove N \| clear]` — critères additionnels sur l'objectif actif, appliqués à la prochaine limite de tour | Persisté avec le `/goal` actif |
| `/status` | — | CLI+GW | Session, modèle, tokens, contexte — vue résumée une ligne | Lecture seule |
| `/egress` | — | CLI+GW | Statut du proxy de sortie Docker | Lecture seule |
| `/context` | `/ctx` | CLI+GW | Vue détaillée de la fenêtre de contexte (jauge, seuil de compression auto, débit cumulé) ; `all` ajoute le détail par skill/toolset | Lecture seule |
| `/sethome` | `/set-home` | GW only | Définit le chat courant comme canal « home » de la plateforme | Persisté |
| `/resume` | — | CLI+GW | `[nom]` — bascule vers une session précédente en cours de conversation | Change la session active |
| `/sessions` | — | CLI+GW | Liste/reprend des sessions précédentes (sans argument = table + instructions, avec argument = identique à `/resume`) | Lecture, ou changement de session |
| `/restart` | — | GW only | Redémarrage propre de la gateway après drain du travail actif | Redémarre le process |

### Configuration

| Commande | Alias | Surface | Effet | Persistance |
|---|---|---|---|---|
| `/export` | — | CLI only | `[profil] [-o sortie.tar.gz]` — exporte un profil (config, skills, thème) en archive partageable | Écrit un fichier |
| `/import` | — | CLI only | `<archive.tar.gz> [--name <nom>]` — importe un profil partagé comme nouveau profil | Crée un profil sur disque |
| `/config` | — | CLI only | Affiche la configuration active (`show_config()`) | Lecture seule — non lu en détail, **non testé** |
| `/model` | — | CLI+GW | Voir section 1 | Ponctuel sauf `--global` |
| `/codex-runtime` | `/codex_runtime` | CLI+GW | Voir section 1 | Persisté |
| `/personality` | — | CLI+GW | `[nom]` — liste ou définit une personnalité prédéfinie | Persisté (docstring confirme « set predefined personalities », détail du stockage **non vérifié en profondeur**) |
| `/statusbar` | `/sb` | CLI only | Bascule l'affichage de la barre d'état contexte/modèle | En mémoire process (`self._status_bar_visible`), **pas vu de persistance disque** — à confirmer, **non testé** |
| `/battery` | — | CLI only | Bascule l'indicateur de batterie coloré dans la barre d'état ; `on\|off\|status` | Persisté dans `display.battery` |
| `/timestamps` | `/ts` | CLI only | Bascule les horodatages `[HH:MM]` sur les messages et `/history` ; `on\|off\|status` | Persisté dans `display.timestamps` |
| `/diff` | — | CLI+GW | `[staged\|all\|session] [--stat] [chemin...]` — diff git du répertoire de travail ; `session` = tout ce que Hermes a modifié depuis le checkpoint de départ | Lecture seule |
| `/verbose` | — | CLI only (+ GW si `display.tool_progress_command` actif) | Cycle l'affichage de progression d'outils : off → new → all → verbose → off, par plateforme côté gateway | Persisté dans `display.platforms.<plateforme>.tool_progress` |
| `/focus` | — | CLI only | Bascule la « vue focus » (n'affiche que le prompt + la réponse finale) ; `on\|off\|status` ; se compose avec `/verbose` plutôt que d'ajouter un second mécanisme | Persisté — **mécanisme de stockage exact non vérifié**, **non testé** |
| `/footer` | — | CLI+GW | Bascule le pied de page runtime-metadata sur les réponses finales ; `on\|off\|status` | Persisté dans `display.runtime_footer.enabled` (global) ; overrides par plateforme existent dans `config.yaml` mais non modifiables par cette commande |
| `/yolo` | — | CLI+GW | Bascule le contournement des approbations de commandes dangereuses **pour la session courante uniquement** | **Volontairement non persisté** — routé via `enable_session_yolo`/`disable_session_yolo`, pas la variable d'env `HERMES_YOLO_MODE` (gelée au démarrage, exprès pour empêcher un skill injecté de la modifier en cours de session) |
| `/approvals` | — | CLI+GW | `[manual\|smart\|off]` — affiche/définit le mode d'approbation des commandes dangereuses, **portée profil** (pas session) | Persisté, portée profil entier |
| `/reasoning` | — | CLI+GW | Voir section 1 | Mixte (voir section 1) |
| `/fast` | — | CLI+GW | Voir section 1 | Ponctuel sauf `--global` |
| `/skin` | — | CLI only | `[nom]` — affiche/change le thème d'affichage | Persisté — **non vérifié en détail** |
| `/indicator` | — | CLI only | Choix du style d'indicateur d'activité TUI (kaomoji/emoji/unicode/ascii...) | Persisté — **non vérifié en détail** |
| `/voice` | — | CLI+GW | `[on\|off\|tts\|channel\|leave\|status]` — bascule le mode voix | Persisté — **non vérifié en détail** |
| `/wake` | — | CLI only | `[on\|off\|status]` — mot de réveil « Hey Hermes » ; l'état ÉCRIT `wake_word.enabled` dans `config.yaml` (le démarrage auto-arm ne fait que LIRE, pas écrire) | Persisté explicitement |
| `/busy` | — | CLI only | `[queue\|steer\|interrupt\|status]` — contrôle ce que fait Entrée pendant que Hermes travaille | Persisté — **non vérifié en détail** |

### Tools & Skills

| Commande | Alias | Surface | Effet | Persistance |
|---|---|---|---|---|
| `/tools` | — | CLI only | `[list\|disable\|enable] [nom...]` — sans argument affiche la liste ; `disable`/`enable` sauvegardent en config ET réinitialisent la session (évite la casse du cache de prompt en cours de conversation) | Persisté dans `config.yaml`, + reset de session forcé |
| `/toolsets` | — | CLI only | Liste les toolsets disponibles | Lecture seule |
| `/skills` | — | CLI only (+ GW si `skills.write_approval` actif, volet revue uniquement) | Recherche/installe/inspecte/gère les skills ; sous-commandes : `search, browse, inspect, install, audit, pending, approve, reject, diff, approval` | Installe des fichiers sur disque (hub complet CLI-only ; côté gateway seule la revue pending/approve/reject est exposée) |
| `/memory` | — | CLI+GW | `[pending\|approve\|reject\|approval] [id\|on\|off]` — revue des écritures mémoire en attente + bascule de la porte d'approbation | Le toggle de porte est persisté dans `config.yaml` et évince l'agent en cache |
| `/bundles` | — | CLI+GW | Liste les bundles de skills installés (alias `/<nom>` pour charger plusieurs skills d'un coup) | Lecture seule |
| `/pet` | — | CLI only | `/pet`, `/pet list`, `/pet <slug>`, `/pet scale <n>`, `/pet off` — mascotte petdex | Persisté dans `display.pet.enabled` + choix actif |
| `/hatch` | `/generate-pet` | CLI only | `<description>` — génère une nouvelle mascotte via appels au modèle d'image (~1 min), adoptée automatiquement comme mascotte active | Écrit des assets + config |
| `/learn` | — | CLI+GW | `<ce dont apprendre>` — distille un skill réutilisable depuis n'importe quelle source décrite (dossiers, URLs, cette conversation, notes) ; réécrit le tour courant vers un prompt guidé et laisse l'agent live faire le travail (lecture + `skill_manage`) | Écrit un nouveau skill sur disque |
| `/init` | — | CLI+GW | `[notes]` — génère ou met à jour `AGENTS.md` depuis un scan du projet, même mécanisme de fall-through que `/learn` | Écrit/modifie `AGENTS.md` |
| `/cron` | — | CLI only | `[subcommand]` — gère les tâches planifiées durables (contrairement à `/heartbeat`, qui est en mémoire process) ; `list, add, create, edit, pause, resume, run, remove` | Persisté (planification durable inter-process) |
| `/suggestions` | `/suggest` | CLI+GW | `[accept\|dismiss N\|catalog]` — revue des automatisations suggérées | Persisté (état des suggestions) |
| `/blueprint` | `/bp` | CLI+GW | `[nom] [slot=valeur...]` — met en place une automatisation depuis un template ; sans nom = liste le catalogue ; avec nom seul = amorce une conversation guidée (agent_seed) ; avec slots = crée directement | Crée une tâche planifiée persistée |
| `/curator` | — | CLI+GW | `[subcommand]` — maintenance de fond des skills (status/run/pin/archive/list-archived) | Modifie l'état des skills |
| `/kanban` | — | CLI+GW | `[subcommand]` — tableau kanban multi-profil (tasks/links/comments) ; délègue au CLI kanban partagé, tourne en thread pool ; `create` auto-souscrit le chat courant aux événements terminaux de la tâche | Écrit en base kanban (SQLite) |
| `/reload` | — | CLI only | Recharge les variables `.env` dans la session active | Effet en mémoire process |
| `/reload-mcp` | `/reload_mcp` | CLI+GW | Reconnecte les serveurs MCP + reconstruit l'agent en cache ; invalide le cache de prompt (schémas d'outils dans le system prompt) → coûteux en tokens au tour suivant, d'où une confirmation avant exécution côté gateway | Effet immédiat, pas de config écrite |
| `/reload-skills` | `/reload_skills` | CLI+GW | Rescanne `~/.hermes/skills/` ; NE vide PAS le cache de prompt (skills invoqués à l'exécution, pas dans le system prompt) ; si changement détecté, une note est mise en attente pour le prochain message | Léger, pas de config écrite |
| `/browser` | — | CLI only | `[connect\|disconnect\|status]` — connecte les outils navigateur à un navigateur Chromium live via CDP | Change l'état de connexion |
| `/plugins` | — | CLI only | Liste les plugins installés et leur statut (utilisateur vs. embarqués) | Lecture seule |

### Info

| Commande | Alias | Surface | Effet | Persistance |
|---|---|---|---|---|
| `/whoami` | — | CLI+GW | Affiche l'accès aux commandes slash de l'utilisateur courant sur ce scope (admin/user/illimité) — toujours accessible même sans permissions | Lecture seule |
| `/profile` | — | CLI+GW | Nom du profil actif + répertoire home | Lecture seule |
| `/commands` | — | GW only | Liste paginée commandes + skills (voir section 3) | Lecture seule |
| `/help` | — | CLI+GW | Liste des commandes disponibles (voir section 3) | Lecture seule |
| `/usage` | — | CLI+GW | Usage de tokens et limites de taux ; `reset [--force]` échange une réinitialisation Codex banquée | Lecture, sauf `reset` qui consomme un crédit réel |
| `/subscription` | `/upgrade` | CLI only | Affiche le plan Nous et permet de le changer dans le navigateur | Lecture + redirection navigateur |
| `/topup` | — | CLI+GW | Solde Nous + lien de gestion facturation ; ne facture/ne confirme JAMAIS rien elle-même, tout se passe sur le portail web | Lecture seule côté commande |
| `/insights` | — | CLI+GW | `[jours]` — analytique d'usage | Lecture seule |
| `/platforms` | `/gateway` | CLI only | Statut des plateformes gateway/messagerie | Lecture seule |
| `/platform` | — | GW only | `<pause\|resume\|list> [nom]` — pause/reprend/liste une plateforme gateway en échec, contrôle manuel | Modifie l'état de la plateforme (persisté tant que non repris) |
| `/copy` | — | CLI only | `[numéro]` — copie la dernière réponse assistant dans le presse-papiers | Ponctuel |
| `/paste` | — | CLI only | Vérifie explicitement le presse-papiers pour une image (fallback pour terminaux où le collage entre bracket ne se déclenche pas sur image, ex. VSCode/Windows Terminal+WSL2) | Ponctuel |
| `/image` | — | CLI only | `<chemin>` — attache une image locale au prochain prompt | Ponctuel |
| `/update` | — | CLI+GW | Met à jour Hermes Agent vers la dernière version ; côté CLI classique, quitte la session et relance en `hermes update` ; côté gateway, lance en détaché (survit au redémarrage) | Déclenche une mise à jour binaire/dépôt |
| `/version` | `/v` | CLI+GW | Affiche la version de Hermes Agent | Lecture seule |
| `/debug` | — | CLI+GW | `[nous\|local]` — upload un rapport de debug (infos système + logs) et renvoie des liens partageables ; côté gateway, seul le RÉSUMÉ est uploadé (pas les logs complets), pour la confidentialité de conversation | Upload distant (sauf `local`) |

### Exit

| Commande | Alias | Surface | Effet | Persistance |
|---|---|---|---|---|
| `/quit` | `/exit` | CLI only | Quitte le CLI ; `--delete` supprime aussi l'historique de session (transcripts + SQLite) | Destructif seulement avec `--delete` |

### Gateway-only additionnelles (démarrage/contrôle plateforme)

| Commande | Surface | Effet |
|---|---|---|
| `/start` | GW only | Accuse réception d'un ping de démarrage de plateforme, sans réponse visible (ex. Telegram `/start`) |

---

## 5. Réglage d'accès (pertinent pour comprendre les erreurs de permission)

`gateway/slash_access.py` détermine, par plateforme/scope, quelles commandes
un utilisateur non-admin peut lancer (`policy_for_source`). Le socle
toujours autorisé pour un non-admin est `{"help", "whoami"}`
(`_ALWAYS_ALLOWED_FOR_USERS`, cité dans `_handle_whoami_command`,
`gateway/slash_commands.py:415`) ; le reste dépend de
`policy.user_allowed_commands` configuré par l'admin. `/whoami` affiche
explicitement la liste effective pour l'utilisateur courant — c'est le
point d'entrée le plus rapide pour diagnostiquer un « command not allowed »
plutôt que de deviner depuis `config.yaml`.

---

## 6. Incertitudes notables (non résolues par la lecture seule)

- **`/config`, `/statusbar`, `/skin`, `/indicator`, `/voice`, `/busy`,
  `/focus`, `/personality`** : leur persistance disque exacte (clé
  `config.yaml`) n'a pas été vérifiée ligne par ligne comme pour
  `/reasoning`/`/model`/`/footer`/`/battery`/`/wake` — seuls les docstrings
  des gestionnaires ont été lus, pas le corps complet. Comportement
  probable par analogie avec les commandes voisines déjà vérifiées, mais à
  confirmer avant de s'appuyer dessus dans un futur ticket Hermes.
- **Aucun test d'exécution réel** n'a été possible dans cet environnement
  (pas de TUI interactive ni de gateway lancée pendant cette tâche) — tout
  ce document est déduit de la lecture du code source, jamais d'une
  observation en direct. Là où un docstring de développeur hermes-agent
  décrit explicitement le comportement (la majorité des cas), c'est traité
  comme fiable (c'est le code du projet, pas une supposition) ; le doute
  n'est signalé que quand même le docstring manque de détail.
- **Skill-commands et bundles** (`/<nom-de-skill>`, `/<slug-de-bundle>`) ne
  passent pas par `COMMAND_REGISTRY` — ce sont des commandes dynamiques
  générées à l'installation d'un skill/bundle, hors du périmètre H-013 (qui
  couvre les commandes slash *natives*).
- **Quick commands** (`config.yaml::quick_commands`) — mécanisme
  utilisateur-configurable qui court-circuite la boucle agent (pas de LLM),
  visible dans le fallback du dispatcher gateway
  (`gateway/run.py:15742-15769`) mais entièrement dépendant de la config
  personnelle de l'utilisateur, donc hors périmètre de ce document
  générique.

# H-020 — Diagnostic : régression du fix H-012 (reasoning_overrides / devstral:24b-64k)

Date : 2026-08-10. Application investiguée : `hermes-agent`
(`C:\Users\Ov3rL0rD\AppData\Local\hermes\hermes-agent`, HERMES_HOME =
`C:\Users\Ov3rL0rD\AppData\Local\hermes`, config active dans
`config.yaml` au même dossier).

## Résumé

**Le fix H-012 n'a jamais disparu.** `config.yaml` contient toujours,
intact et inchangé depuis sa dernière modification le 09/08 à 11:41, les 7
entrées `agent.reasoning_overrides` (`devstral:24b-64k`, `qwen3-coder:30b-a3b-64k`,
`qwen2.5-coder:14b-64k`, `llama3.1:64k`, `mistral:64k`, `qwen2.5-coder:7b-64k`,
`qwen2.5:64k` → `"none"`). Ce n'est donc **pas** un cas de "config
régénérée depuis un template" ni de "modifs locales non committées perdues"
— l'hypothèse structurelle posée dans le brief H-020 ne s'est pas
vérifiée.

**Cause réelle, confirmée par inspection directe de `state.db`** : le
client Desktop de hermes-agent envoie sa sélection d'effort de
raisonnement ("Effort" dropdown) **sur chaque nouvelle session**, pas
seulement quand l'utilisateur la modifie explicitement pour ce modèle.
Cette valeur devient un override **scope-session**, qui — par conception,
documentée dans le code — gagne toujours sur le défaut per-modèle de
`config.yaml`. Le 10/08 vers 22:02, une nouvelle session Desktop sur
`devstral:24b-64k` a été créée avec l'effort composer resté sur
`"medium"` (probablement hérité d'un modèle/provider précédent dans la
même session Desktop) ; ce `"medium"` a été baked dans le
`model_config.reasoning_config` persisté de la session et a court-circuité
le `"none"` de `config.yaml`, reproduisant l'erreur HTTP 400
`"devstral:24b-64k" does not support thinking`.

## Preuve

**1. `config.yaml` intact** (lu à 22:xx le 10/08, mtime disque : 09/08
11:41:00, jamais retouché depuis) :

```yaml
agent:
  reasoning_overrides:
    "devstral:24b-64k": "none"
    "qwen3-coder:30b-a3b-64k": "none"
    "qwen2.5-coder:14b-64k": "none"
    "llama3.1:64k": "none"
    "mistral:64k": "none"
    "qwen2.5-coder:7b-64k": "none"
    "qwen2.5:64k": "none"
```

**2. Le code de résolution (`hermes_constants.py::resolve_reasoning_config`)
lit bien cette clé correctement** — relu et confirmé fonctionnel, aucune
régression côté résolution de config. Mais sa propre docstring précise :
*"Session-scoped overrides (gateway `/reasoning --session`) are resolved
by the caller BEFORE this function — they always win."*

**3. `errors.log` / `agent.log`** — trace de la séquence réelle du 10/08 :

```
21:56:27  HTTP 404 model 'devstral:24b-64k' not found       (Ollama pas encore stabilisé au démarrage — transitoire)
21:59:29  HTTP 404 model 'devstral:24b-64k' not found       (idem)
22:02:57  conversation turn: session=20260810_220256_e07fa0 model=devstral:24b-64k platform=desktop history=0
22:03:00  HTTP 400 "devstral:24b-64k" does not support thinking   ← la régression signalée
```

**4. `state.db`, table `sessions`, ligne de la session fautive** (seule
ligne présente dans la table au moment de l'investigation) :

```json
{
  "model": "devstral:24b-64k",
  "provider": "custom:local",
  "reasoning_config": {"enabled": true, "effort": "medium"},
  "service_tier": "normal"
}
```

`"effort": "medium"` — pas `"none"` — confirme que `config.yaml` n'a
jamais été consulté pour cette session : un override scope-session l'a
court-circuité dès la création.

**5. Code confirmant le mécanisme** —
`tui_gateway/methods_session.py::session.create` (lignes 45-63) :

```python
# The desktop composer owns its model/effort/fast as plain UI state and ships
# it on every session.create. Honor each as a PER-SESSION override (built into
# the agent below) — never a global config write, so picking a model/effort
# for a new chat can't mutate the profile default. provider is optional
# (resolved at build).
...
create_reasoning_override = None
if effort := str(params.get("reasoning_effort") or "").strip():
    create_reasoning_override = parse_reasoning_effort(effort)
```

Et `tui_gateway/server.py:2789-2790`, au moment de persister la session :

```python
if (reasoning := session.get("create_reasoning_override")) is not None:
    model_config["reasoning_config"] = reasoning
```

`apps/desktop/src/lib/reasoning-effort.ts` confirme côté UI qu'un
`DEFAULT_REASONING_EFFORT = 'medium'` sert de repli quand le composer n'a
pas de valeur explicite — cohérent avec `"medium"` (pas `"high"` ni
autre) apparaissant systématiquement dans ce genre de cas.

## Pourquoi H-014 n'a pas empêché ça

H-014 (le clamp `resolve_ollama_effort` dans `CustomProfile`) est bien
committé et actif (`git log`, commit `4a920add2`,
`fix(providers): clamp reasoning_effort to Ollama's vocabulary for the
custom profile`) — malgré la mention "Non commité" dans le REGISTRE au
moment de la session H-014 ; il l'a manifestement été après coup. Mais ce
clamp corrige uniquement les valeurs **hors grammaire Ollama**
(`xhigh`/`ultra`/`minimal` → `high`/`medium`/`low`/`max`/`none`) — `"medium"`
est déjà dans la grammaire acceptée, donc il traverse le clamp sans
modification. Le vrai problème n'est pas la valeur, c'est que
**`devstral:24b-64k` ne déclare tout simplement pas la capacité
`"thinking"`**, et rien dans `CustomProfile` ne vérifiait cela avant
l'envoi — c'est exactement le point 6 signalé (non corrigé) dans le
diagnostic H-012 : *"l'absence, spécifiquement dans `CustomProfile`,
d'un clamp vers le sous-ensemble réellement accepté par Ollama — chose
que fait déjà... le profil `ollama-cloud`"*.

## Correctif appliqué

**Fichier modifié** : `plugins/model-providers/custom/__init__.py`
(dans le dépôt `hermes-agent`, PAS ce dépôt Ov3rLoRd).

Le point d'entrée `build_api_kwargs_extras` reçoit déjà `model=` en
paramètre (transmis par `agent/transports/chat_completions.py:674`) mais
ne s'en servait que pour rien — `CustomProfile` ignorait cette info.
Ajout d'une vérification de capacité **à l'endroit même où la valeur
part sur le réseau**, donc imperméable à la source de la valeur
(config globale, override per-modèle H-012, ou override scope-session
Desktop) :

```python
if self._is_verified_ollama(base_url):
    from agent.ollama_reasoning import resolve_ollama_effort
    _effort = resolve_ollama_effort(_effort)
    model = ctx.get("model")
    if self._model_supports_thinking(base_url, model) is not True:
        top_level["reasoning_effort"] = "none"
        extra_body["think"] = False
        return extra_body, top_level
top_level["reasoning_effort"] = _effort
```

+ méthode `_model_supports_thinking` (probe `/api/show` via l'utilitaire
existant `hermes_cli.models.ollama_model_supports_thinking`, déjà utilisé
côté agent pour Ollama Cloud — ici réutilisé tel quel pour Ollama local,
avec un cache process-vie par `(base_url, model)` pour ne pas ajouter un
aller-retour réseau à chaque tour).

Probe échouée (None) traitée comme "non" — ne jamais risquer d'envoyer
une valeur que le modèle pourrait rejeter (même logique de repli que le
reste du fichier).

## Preuve de test

Script de vérification exécuté avec `.venv/Scripts/python.exe` du dépôt
`hermes-agent`, contre le vrai serveur Ollama local (`localhost:11434`,
probe réseau réel, pas mocké) :

```
=== devstral:24b-64k, session override effort=medium (repro exacte H-020) ===
extra_body: {'think': False}
top_level: {'reasoning_effort': 'none'}
PASS: forced to none/think=False

=== gemma4:12b-64k (thinking-capable), effort=medium — doit rester inchangé ===
extra_body: {}
top_level: {'reasoning_effort': 'medium'}
PASS: gemma4:12b-64k still gets medium forwarded

=== devstral:24b-64k, override config-level effort=none (chemin H-012, inchangé) ===
extra_body: {'think': False}
top_level: {'reasoning_effort': 'none'}
PASS

ALL CHECKS PASSED
```

Suite de tests existante de la app (non-régression) :

```
tests/plugins/model_providers/test_custom_profile.py  ..... 22 passed
tests/plugins/model_providers/ + tests/providers/      ..... 232 passed
```

Script de vérification supprimé après usage (`_h020_test_capability_gate.py`,
temporaire, jamais commité).

## Ce qui n'a PAS été fait

- **Rien commité/poussé** dans le dépôt `hermes-agent` (règle non
  négociable de la session) — le correctif est appliqué sur le disque
  (`plugins/model-providers/custom/__init__.py`) mais reste un diff local
  tant que Jérémy ne confirme pas.
- La session Desktop bloquée (`20260810_220256_e07fa0`, tâche H-017) n'a
  pas été purgée manuellement dans `state.db` — le correctif s'applique
  **au moment de l'envoi**, donc il corrige aussi les tours suivants de
  cette même session (le `reasoning_config: {"effort": "medium"}` persisté
  ne posera plus de 400), mais seulement **après redémarrage du process
  hermes-agent en cours** pour qu'il recharge le fichier Python modifié
  (Python ne recharge pas un module déjà importé). Sans redémarrage, la
  prochaine tentative dans cette session échouera encore.
- Aucune modification de `config.yaml` — il était déjà correct, rien à y
  réappliquer.

## Recommandation

1. **Committer ce correctif** (`plugins/model-providers/custom/__init__.py`
   dans `hermes-agent`) une fois validé — contrairement à l'hypothèse de
   départ du brief, ce n'est *pas* un cas "jamais committé donc perdu",
   mais le fix H-014 (`4a920add2`) montre que committer les correctifs de
   ce genre a déjà été fait et n'a rien cassé ; le committer maintenant
   évite qu'un futur `git pull`/reset sur `hermes-agent` l'efface pour de
   vrai, cette fois pour la raison que le brief anticipait.
2. **Redémarrer hermes-agent** (Desktop + toute session gateway/TUI en
   cours) pour que ce correctif s'applique, y compris à la session H-017
   actuellement bloquée.
3. Le mécanisme "override scope-session gagne toujours" (documenté et
   voulu par conception, cf. commentaire `tui_gateway/server.py:1125-1129`)
   reste risqué pour **tout** futur modèle local ajouté sans capacité
   `thinking` : avec ce correctif, ce risque est maintenant couvert de
   façon générique (probe de capacité réelle, pas une liste de 7 noms à
   maintenir à la main) — `config.yaml.agent.reasoning_overrides` devient
   redondant pour Ollama local (ceinture-bretelles) mais reste utile tel
   quel pour les futurs endpoints `custom` non-Ollama (GLM/ARK, vLLM) où
   la probe `/api/show` ne s'applique pas.

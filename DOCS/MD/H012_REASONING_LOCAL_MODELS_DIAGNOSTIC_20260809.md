# H-012 — Diagnostic : reasoning/thinking sur les modèles locaux (hermes-agent)

Date : 2026-08-09. Application investiguée : `hermes-agent` (Nous Research,
open source MIT, `github.com/NousResearch/hermes-agent`), installée sous
`C:\Users\Ov3rL0rD\AppData\Local\hermes\hermes-agent` (config active dans
`C:\Users\Ov3rL0rD\AppData\Local\hermes\config.yaml`). Aucun fichier de ce
dépôt (Ov3rLoRd) n'est concerné par les points 1-6 ci-dessous — seul le point
7 touche `ov3rlord-coder-stage2v2`, servi localement via Ollama.

Toutes les causes ci-dessous sont **confirmées par reproduction directe**
(appels HTTP réels sur `localhost:11434`, lecture du code source réel), pas
supposées.

## 1-5. Erreurs 400 "does not support thinking" (mistral:64k, llama3.1:64k)

**Cause exacte confirmée** : `agent.reasoning_effort: "medium"` (global,
`config.yaml` ligne 958) est transmis tel quel à **tous** les modèles, y
compris ceux servis par le provider local (`providers.local`, alias
`custom`/`ollama`/`local`). Le profil `CustomProfile`
(`plugins/model-providers/custom/__init__.py::build_api_kwargs_extras`) ne
fait aucune vérification de capacité par modèle avant d'émettre le champ
top-level `reasoning_effort` — contrairement au profil `ollama-cloud` dédié
(`plugins/model-providers/ollama-cloud/__init__.py`) qui, lui, vérifie
`supports_reasoning` avant d'émettre quoi que ce soit.

**Reproduction minimale** (hors hermes-agent, requête brute sur Ollama) :

```
curl http://localhost:11434/v1/chat/completions -d '{"model":"mistral:latest","messages":[{"role":"user","content":"hi"}],"reasoning_effort":"medium"}'
→ HTTP 400 {"error":{"message":"\"mistral:latest\" does not support thinking", ...}}

curl http://localhost:11434/v1/chat/completions -d '{"model":"mistral:latest","messages":[{"role":"user","content":"hi"}]}'
→ HTTP 200 (sans le champ, aucune erreur)
```

C'est **Ollama lui-même** qui rejette la requête (validation serveur, pas un
bug de formatage côté hermes-agent) : il refuse `reasoning_effort` pour tout
modèle qui ne déclare pas la capacité `"thinking"` dans son `/api/tags`.

**Capacités réelles vérifiées** (`ollama list` / `/api/tags`, 9 tags -64k
créés en session précédente) :

| Modèle | `thinking` déclaré ? |
|---|---|
| gemma4:31b-64k | ✅ oui |
| gemma4:12b-64k | ✅ oui |
| qwen3-coder:30b-a3b-64k | ❌ non |
| qwen2.5-coder:14b-64k | ❌ non |
| llama3.1:64k | ❌ non |
| mistral:64k | ❌ non |
| qwen2.5-coder:7b-64k | ❌ non |
| qwen2.5:64k | ❌ non |
| devstral:24b-64k | ❌ non |

Le brief supposait que "les 6 autres variantes -64k" avaient toutes besoin
du même correctif que mistral:64k/llama3.1:64k — **7 des 9 en ont besoin,
pas 8** : `gemma4:12b-64k` et `gemma4:31b-64k` supportent réellement le
thinking et doivent garder l'effort global (`medium`).

**Correctif appliqué (config uniquement, aucun code hermes-agent modifié)** —
`C:\Users\Ov3rL0rD\AppData\Local\hermes\config.yaml`, section `agent:` :

```diff
   reasoning_overrides:
+    "devstral:24b-64k": "none"
+    "qwen3-coder:30b-a3b-64k": "none"
+    "qwen2.5-coder:14b-64k": "none"
+    "llama3.1:64k": "none"
+    "mistral:64k": "none"
+    "qwen2.5-coder:7b-64k": "none"
+    "qwen2.5:64k": "none"
```

`"none"` a été choisi (plutôt qu'un remap vers une valeur factice) parce que
c'est la **seule valeur qu'Ollama accepte inconditionnellement, sur tout
modèle, thinking-capable ou non** — vérifié par test direct (voir point 4
ci-dessous). `agent.reasoning_effort: "medium"` (le défaut global, utilisé
par le provider Anthropic) n'a **pas** été touché, conformément à la
consigne. La correspondance de clé (nom de modèle nu, ex. `"mistral:64k"`
sans préfixe `custom:local:`) est confirmée fonctionnelle par lecture directe
de `hermes_constants.py::resolve_per_model_reasoning_effort` /
`_canonical_model_variants` (résolution tolérante à l'orthographe, préfixe
provider optionnel — déjà documenté par l'exemple `"claude-opus-4.6": "high"`
présent dans le fichier avant ce patch).

**Preuve de test — 2 modèles locaux, avant/après** :

```
# mistral:latest (modèle de base non renommé) — reasoning_effort=none
curl .../v1/chat/completions -d '{"model":"mistral:latest",...,"reasoning_effort":"none"}'
→ HTTP 200, réponse générée normalement

# llama3.1:64k (variante -64k) — reasoning_effort=none
curl .../v1/chat/completions -d '{"model":"llama3.1:64k",...,"reasoning_effort":"none"}'
→ HTTP 200, réponse générée normalement

# mistral:64k (variante -64k) — reasoning_effort=none
curl .../v1/chat/completions -d '{"model":"mistral:64k",...,"reasoning_effort":"none"}'
→ HTTP 200, réponse générée normalement
```

Point 4 (cas séparé "invalid reasoning value") : ce n'est **pas** une
commande utilisateur invalide au sens propre du terme — voir point 6/7
ci-dessous, c'est la même famille de cause (valeur envoyée sans vérification
de ce qu'Ollama accepte réellement).

## 6. Bug UI "Ultra"

**Diagnostic** : "Ultra" n'est **pas** une valeur inventée par erreur dans
l'UI — c'est un niveau légitime et documenté dans l'abstraction propre de
hermes-agent :

- Backend : `hermes_constants.py::VALID_REASONING_EFFORTS = ("minimal",
  "low", "medium", "high", "xhigh", "max", "ultra")`
- UI desktop : `apps/desktop/src/lib/reasoning-effort.ts::REASONING_EFFORTS`
  — **identique**, les deux listes sont synchronisées (le commentaire du
  fichier UI dit explicitement "mirrors the backend's VALID_REASONING_EFFORTS").

Le menu Effort (Minimal/Low/Medium/High/Extra High/Max/Ultra) reflète donc le
code fidèlement — il n'y a pas de désynchronisation UI/backend à ce niveau.

**Le vrai problème** : ces 7 niveaux sont conçus pour l'éventail complet des
providers supportés par hermes-agent (OpenRouter, Nous Portal, GLM/ARK, etc.,
qui acceptent des échelles plus fines). **Ollama, lui, n'accepte qu'un
sous-ensemble de 5 valeurs** — confirmé par reproduction directe :

```
curl .../v1/chat/completions -d '{"model":"deepseek-r1:7b",...,"reasoning_effort":"ultra"}'
→ HTTP 400 {"error":{"message":"invalid reasoning value: 'ultra' (must be \"high\", \"medium\", \"low\", \"max\", or \"none\")"}}
```

(reproduit aussi avec `"xhigh"` et `"minimal"` — même erreur, même liste de
5 valeurs acceptées.) C'est le message exact rapporté dans le brief — donc
**confirmé comme le même mécanisme**, pas un bug UI distinct.

**Verdict sur "UI vs backend à corriger"** : ni l'un ni l'autre au sens où le
brief le pose — "Ultra" reste un alias valide côté hermes-agent (utile pour
OpenRouter/Nous/GLM), ce n'est donc pas une valeur à retirer de l'UI
globalement. Le vrai defect est l'absence, **spécifiquement dans
`CustomProfile`** (le profil qui couvre Ollama local), d'un clamp vers le
sous-ensemble {high, medium, low, max, none} réellement accepté par
Ollama — chose que fait déjà `lmstudio_reasoning.py` pour LM Studio (probe
`/api/v1/models`, clamp vers `allowed_options`) et le profil `ollama-cloud`
pour Ollama Cloud. **Non corrigé dans cette passe** (changement de code
hermes-agent, hors périmètre du correctif config appliqué ci-dessus) :
signalé comme piste pour un futur brief si Jérémy sélectionne manuellement
Ultra/Extra High/Minimal sur un modèle local **thinking-capable**
(`gemma4:12b-64k` ou `gemma4:31b-64k` — les 7 autres locaux sont désormais à
`"none"` donc jamais exposés à ce problème).

## 7. Balises `[OUT-OF-BAND USER MESSAGE...]`

**Confirmé : hypothèse (a), côté application — pas le modèle.**

Origine exacte : `agent/prompt_builder.py:661-666` définit
`STEER_MARKER_OPEN`/`STEER_MARKER_CLOSE` (texte identique, mot pour mot, à
celui rapporté par Jérémy). C'est le mécanisme `/steer` (interruption
mi-tour, pas une commande explicite forcément tapée — déclenché par
`AIAgent.steer(text)`, `run_agent.py:3286-3320`, appelé par le
gateway/CLI/TUI dès qu'un message est envoyé **pendant que l'agent exécute
un tool call**). Le texte est injecté **une seule fois**, à la fin du
prochain résultat d'outil
(`agent/agent_runtime_helpers.py::apply_pending_steer_to_tool_results` /
`agent/conversation_loop.py` — les deux points de drain vident
`agent._pending_steer` via `_drain_pending_steer()`, aucun bug de
double-injection trouvé dans ces deux chemins).

**Pourquoi ça "réapparaît identique à plusieurs tours sans retaper"** : ce
n'est pas une réinjection automatique — c'est un message historique normal.
Une fois écrite dans `messages[]`, la balise fait partie de l'historique de
conversation comme n'importe quel autre message, et hermes-agent (comme
tout client de chat) renvoie l'historique complet à chaque appel API
suivant. Le code anticipe explicitement cette confusion :
`STEER_CHANNEL_NOTE` (`prompt_builder.py:674-681`) instruit le modèle qu'une
occurrence ailleurs qu'au tour le plus récent est un replay historique, "not
a new delivery".

**Test décisif exécuté** (modèle appelé directement via l'API Ollama brute,
sans passer par hermes-agent, 3 prompts différents dont un demandant
explicitement au modèle de décrire/démontrer le format des messages
mi-tour) : dans les 3 cas, `ov3rlord-coder-stage2v2` n'a **jamais** reproduit
la chaîne exacte `[OUT-OF-BAND USER MESSAGE...]`. Le cas le plus proche a
confabulé un format **différent et fictif** (`[CONTEXT] (MID-TURN) -- ...`),
cohérent avec le comportement de confabulation déjà documenté
(`VERDICT_COMMITPACK.md`), pas avec une mémorisation verbatim.

Recherche élargie (grep, hors modèle) — **aucune occurrence** de
`OUT-OF-BAND`/`delivered once`/`not tool output`/`STEER_MARKER` dans :
`source_rtuning.jsonl` (216 ex. catégorie A H-008), `source_rtuning_rag.jsonl`
(300 ex. catégorie B RAG), `workspace/rag_index/chunks.jsonl` (682 chunks),
tous les `*.md` du dépôt (HANDOFF, DOCS/MD, etc.), `workspace/external_ai_sessions/`
(claude_desktop, gemini). Hypothèse (b) écartée avec un niveau de confiance
élevé, pas seulement "pas trouvé au premier coup d'œil".

## Ce qui n'a PAS été fait

- Aucun code de `hermes-agent` modifié (seul `config.yaml`, hors dépôt git de
  l'appli). Rien commité/poussé nulle part.
- Le clamp de valeurs pour `CustomProfile` (point 6, résiduel) n'a pas été
  codé — signalé, pas implémenté.
- La config du provider Anthropic (`agent.reasoning_effort: "medium"` global)
  n'a pas été touchée.

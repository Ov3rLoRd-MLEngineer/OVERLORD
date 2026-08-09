# Rapport de session longue autonome -- 09/08/2026

Session lancée sans présence de Jérémy (plusieurs heures). Ordre d'exécution suivi tel que
demandé : (1) vérification kohya_ss, (2) H-013, (3) H-014, (4) H-015 (GPU RTX 5080, en
parallèle des points 2/3 comme autorisé). **Aucun commit/push effectué** (règle non
négociable de la session) -- tout reste en working tree, dans les dépôts OVERLORD et
hermes-agent.

## 1. Vérification install kohya_ss (rapport jamais reçu en session précédente)

Rapport déjà écrit et complet, trouvé sur place : `DOCS/MD/KOHYA_SS_VS_LORA_TRAINER_20260809.md`
(daté du jour même). Install vérifiée fonctionnelle (`torch.cuda.is_available()` -> `True`,
2 GPU visibles, venv isolé `D:\kohya_ss\.venv`, Python 3.11 assumé). Rien à refaire. Le
rapport documente aussi 3 écarts connus entre `lora_trainer.py` et la structure réelle du
checkout kohya_ss (chemin `train_network.py` faux, script SDXL manquant, interpréteur non
isolé) -- hors scope de cette vérification, à corriger seulement quand H-007 sera vraiment
lancé (toujours bloqué sur H-003, aucun `.vrm`).

## 2. H-013 -- Documentation des commandes hermes-agent

**Statut : ✅ terminé.** Livrable : `DOCS/MD/HERMES_AGENT_COMMANDES.md` (422 lignes).

Découverte clé : la vraie source de vérité n'est pas le pointeur de départ
(`gateway/slash_commands.py`) mais `hermes_cli/commands.py::COMMAND_REGISTRY` (95 commandes
canoniques + 26 alias, consommé par 3 surfaces : CLI/TUI, gateway, mixins). `/help` existe
sur les deux surfaces et est généré directement depuis ce registre -- pas de dérive doc/code,
le vrai manque était la profondeur (persistance session vs `--global`, nuances `/steer`).
Section modèles/reasoning documentée en détail comme demandé, avec un bonus trouvé en
creusant : `/reasoning full`/`clamp` est CLI/TUI seulement, absent côté gateway. Aucun fichier
hermes-agent modifié (tâche 100% documentation).

## 3. H-014 -- Fix clamp reasoning_effort (Ultra/xhigh/minimal -> Ollama)

**Statut : ✅ fonctionnellement complet**, avec une note de transparence sur la manière dont
la tâche s'est terminée.

L'agent chargé de cette tâche a été interrompu par une limite de session API en cours de
travail ("Bug confirmé en direct. Maintenant la valeur clampée doit fonctionner :" --
coupé net). Plutôt que de relancer un agent complet (coût token), j'ai vérifié moi-même
l'état du travail déjà produit :

- `plugins/model-providers/custom/__init__.py` modifié : le clamp n'est appliqué que si
  `_is_verified_ollama(base_url)` est vrai (nouvelle fonction) -- décision plus prudente que
  ce que demandait le brief initial, parce que `CustomProfile` sert aussi des endpoints non-Ollama
  (GLM-5.2/ARK, vLLM, llama.cpp) qui ne sont pas connus pour rejeter "xhigh"/"ultra"/"minimal" ;
  clamper aveuglément aurait pu altérer un comportement qui fonctionnait déjà pour ces
  endpoints-là.
- Nouveau module `agent/ollama_reasoning.py::resolve_ollama_effort()` : mapping
  `ultra`/`xhigh` -> `max`, `minimal` -> `low`, valeurs déjà valides inchangées -- exactement
  la correspondance proposée dans le brief.
- 216 tests unitaires passants (`uv run --extra dev pytest`) : 22 dans
  `test_custom_profile.py`, 12 dans `tests/agent/test_ollama_reasoning.py` (nouveau fichier,
  couvre les 3 clamps + passthrough + normalisation casse/espaces), 182 sur l'ensemble
  `tests/plugins/model_providers/` (aucune régression sur les autres providers).
- **Test réel effectué par moi directement** (pas de simulation) : requête brute contre
  Ollama local (`http://localhost:11434/v1/chat/completions`, modèle `gemma4:12b-64k`,
  l'endpoint OpenAI-compatible réellement utilisé par hermes-agent) --
  `reasoning_effort=ultra` -> `HTTP 400` confirmé ("invalid reasoning value: 'ultra'..."),
  `reasoning_effort=max` (valeur clampée cible) -> `HTTP 200` avec réponse réelle générée.
  Preuve directe que le clamp élimine bien le 400 pour un choix qui existe dans le menu de
  l'utilisateur.

Diff non commité, reste en working tree de `hermes-agent`.

## 4. H-015 -- Itération ciblée sur la confabulation du Prompt 3

**Statut : ✅ net positif, `adapter_stage3d_final` adopté.** Verdict complet :
`workspace/qlora_dataset/training/VERDICT_H015_TARGETED_PROMPT3.md`.

Démarche suivie (résumé, détail dans le verdict) :
1. **Diagnostic empirique avant toute décision de dataset** : sonde réelle (pas de théorie
   non vérifiée) de `adapter_stage3c_final` sur les 12 exemples `fichier_specifique`/incertain
   de `source_rtuning.jsonl` -- confirme que le Prompt 3 est un échec **isolé**, pas un défaut
   systémique de ce sous-type (les 11 autres refusent correctement, y compris ceux qui
   partagent le même "trou" d'échantillonnage aléatoire de H-011).
2. **Lot ciblé de 5 exemples** (l'exemplaire exact du Prompt 3, désormais garanti inclus, +
   4 nouvelles variantes du même sous-type : fuite mémoire, IndexError, race condition,
   JSONDecodeError) -- pas de rééchantillonnage large de la catégorie A, conforme à
   l'interdiction explicite du brief.
3. Continuation stricte depuis `adapter_stage3c_final` (H-011, garde-fou vérifié dans le
   script), LR=1e-5 (réduit vs H-011), 2 epochs, 17.1 min sur RTX 5080, aucune divergence.
4. Comparaison réelle à 4 points sur les mêmes 8 prompts que tous les verdicts précédents.

Résultat honnête : **le Prompt 3 est corrigé sur le fond** (n'invente plus de module/code
cassé, refuse correctement en demandant le fichier -- l'objectif de la tâche) mais **pas une
victoire complète** -- sa réponse se termine par une phrase confuse/mal formée qui ne
correspond à rien dans le prompt d'origine (même type de dégradation rédactionnelle déjà vue
sur d'autres prompts en H-010/H-011, ici déplacée sur celui-ci). Aucune régression sur les 7
autres prompts, notamment le **Prompt 7 (cas flagship de la régression catastrophique H-010)**
qui reste stable pour la 2e fois consécutive. Bonus non visé : le Prompt 5, dont le texte
était confus depuis H-010, redevient parfaitement cohérent en H-015.

Piste documentée pour une itération future (non traitée ici, hors budget) : les dégradations
de rédaction apparaissent sur un prompt différent à chaque round (Prompt 5 puis Prompt 3/4) --
possible signe d'un problème général de cohérence de fin de réponse après plusieurs
continuations cumulées (Stage3 -> 3b rejeté -> 3c -> 3d), pas un défaut lié à un prompt
précis.

## 5. Ce qui reste à faire (aucune action bloquante)

- **Confirmer/committer les diffs H-014** (hermes-agent) et **adopter formellement
  `adapter_stage3d_final`** (H-015, remplace `adapter_stage3c_final` comme référence) --
  décisions qui restent à Jérémy, rien n'a été poussé.
- Piste de rédaction (H-015 section finale) à garder en tête si une H-016 ou suite est
  décidée -- éviter de re-cibler un prompt individuel à chaque round sans regarder la
  tendance générale.
- H-007 (LoRA personnage) toujours bloqué sur H-003 (pas de `.vrm`), kohya_ss n'est plus le
  facteur bloquant.

`DOCS/HERMES/REGISTRE.md` mis à jour au fil de la session (H-013/H-014/H-015 passés à ✅ avec
détail complet dans chaque ligne).

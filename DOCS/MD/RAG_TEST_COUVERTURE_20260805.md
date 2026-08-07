# Test couverture RAG 600+ chunks — "cite ou refuse" (2026-08-05)

Suite à l'augmentation 515 → **682 chunks** (`agents/infra/rag_indexer.py`,
nouvelles sources : arborescence `agents/` post-Phase-C, handoff/tests
SVI-AnimateDiff-AniSora du 2026-08-04/05, veille cohérence temporelle).
Test du comportement "cite ou refuse" (`NO_MATCH_INSTRUCTION` dans
`agents/infra/rag_query.py::format_context()`) sur 5 requêtes représentatives
via `py -3.12 agents/infra/rag_query.py "<question>" --top-k 3`.

## Requêtes sur sujet (doivent citer une source précise)

1. **"quel CFG et combien de steps pour SVI 2.0 Pro ?"**
   → top résultat `Dépasser la limite de cohérence temporelle.md` : "CFG 1.5,
   Shift 8, Steps 6" + confirmation croisée dans `TEST_SVI_04082026.md`
   (indirectement, même valeurs). Citable.
2. **"quelle méthode ColorMatch utiliser pour l'anime, LAB ou RGB ?"**
   → top résultat `TEST_SVI_04082026.md` : explique que `ColorMatch` v1
   n'a pas de mode LAB, c'est `ColorMatchV2`/`reinhard_lab_gpu` — plus précis
   que la règle courte de `CLAUDE.md` (2e résultat). Citable, source exacte.
3. **"quels sont les sous-dossiers du paquet agents après la réorganisation Phase C ?"**
   → top résultat le fichier généré aujourd'hui
   (`agents_arborescence_phase_c.md`), 2e résultat `RAPPORT_AUDIT_PIPELINE_AOUT2026.md`
   (confirme "10 sous-dossiers thématiques"). Citable — comble bien l'angle
   mort identifié en tâche 4.

## Requêtes hors-sujet / fausse prémisse (doivent refuser, pas halluciner)

4. **"quelle est la capitale de la France ?"** (hors périmètre projet)
   → passages retournés sans rapport (ancrage SDXL, règle de langue
   CLAUDE.md) — aucun ne répond à la question. Avec `NO_MATCH_INSTRUCTION`
   en tête de contexte, un LLM aval doit répondre "Information non
   disponible dans le contexte projet" plutôt que d'utiliser ses
   connaissances générales. Comportement attendu confirmé au niveau de la
   récupération (aucun passage pertinent remonté).
5. **"quel modèle OpenAI GPT est utilisé dans le pipeline de production ?"**
   (fausse prémisse — le pipeline utilise Ollama/modèles locaux, jamais
   d'API OpenAI, cf. `agents/creative/llm_router.py` et ADR-006)
   → passages retournés (ADR-TTS/gTTS, diagnostic mode collapse, verdict
   CommitPack) ne mentionnent aucun modèle OpenAI en usage — aucun ne
   confirme la prémisse de la question. Le garde-fou doit empêcher le LLM
   de construire une réponse plausible mais fausse à partir de
   connaissances générales sur OpenAI plutôt que du corpus projet.

## Conclusion

5/5 comportements attendus : les 3 requêtes sur sujet retrouvent une source
précise et citable dès le top résultat ; les 2 requêtes hors-sujet/fausse
prémisse ne remontent aucun passage qui permettrait de répondre — le
garde-fou anti-extrapolation (`NO_MATCH_INSTRUCTION`) a le contexte
nécessaire pour déclencher un refus plutôt qu'une confabulation. Limite
connue : ce test vérifie la *récupération* (les passages retournés), pas le
comportement final d'un LLM aval qui recevrait ce contexte — aucun modèle
n'a été appelé dans ce test (pas de dépendance API, cohérent avec la
consigne CLAUDE.md de ne jamais présenter une simulation comme une
évaluation réelle).

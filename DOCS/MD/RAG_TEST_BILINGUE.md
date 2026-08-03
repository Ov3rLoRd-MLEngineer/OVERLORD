# Test RAG bilingue — 5 requêtes techniques, anglais vs français

Test de suivi après l'ajout de `CLAUDE-english.md` au corpus RAG (session du
2026-08-03, commit `86262a8`, 269 → 307 chunks). Objectif : vérifier avec des
mesures fraîches si `CLAUDE-english.md` comble réellement l'angle mort
cross-lingue documenté dans `workspace/qlora_dataset/HANDOFF_2026-08-03.md`
(question posée en français dont la réponse n'existe qu'en anglais dans
`CLAUDE.md`), ou si un enrichissement supplémentaire est nécessaire.

Méthode : 5 termes techniques choisis pour leur présence documentée dans le
dépôt, interrogés en anglais puis en français (traduction naturelle, pas du
mot-à-mot), via `py -3.12 agents/infra/rag_query.py "<requête>" --top-k 5
--json` (index actuel, 307 chunks, 12 sources). Index non reconstruit pour ce
test — même état que le commit `86262a8`.

## Résumé — top-1 par requête

| # | Terme | Requête EN | top-1 EN (score) | Requête FR | top-1 FR (score) | Pertinent en FR ? |
|---|---|---|---|---|---|---|
| 1 | `dpmpp_2m` | "dpmpp_2m sampler default" | CLAUDE-english.md — *Decisions...* (0.033) | "sampler dpmpp_2m par défaut" | DOCS/MD/Audit maturité... — *Recommendations* (0.026) | **Non** — hors sujet |
| 2 | `taesdxl` | "taesdxl VAE" | CLAUDE-english.md — *Decisions...* (0.033) | "VAE taesdxl" | CLAUDE-english.md — *Decisions...* (0.033) | **Oui** — identique à l'EN |
| 3 | `CUDA_VISIBLE_DEVICES` | "CUDA_VISIBLE_DEVICES GPU pinning" | DOCS/LLM-Secour.md — *Règles non négociables* (0.031) | "épinglage GPU CUDA_VISIBLE_DEVICES" | DOCS/LLM-Secour.md — *Règles non négociables* (0.032) | **Oui** — doc FR pertinente native |
| 4 | `batch_controlnet` | "batch_controlnet pipeline" | DOCS/RAG_SOURCES.md — *Rapports d'audit* (0.033) | "pipeline batch_controlnet" | DOCS/RAG_SOURCES.md — *Rapports d'audit* (0.033) | **Oui** — identique EN/FR (sujet 100% francophone) |
| 5 | SAM confidence routing | "SAM confidence routing" | CLAUDE-english.md — *Key Paths* (0.033) | "routage par confiance SAM" | CLAUDE.md — *Emplacements clés* (0.033) | **Oui** — équivalent FR natif, même score |

**4 requêtes sur 5 trouvent une réponse pertinente en tête en français.**
Un seul cas concret d'angle mort persistant : `dpmpp_2m`.

## Cas 1 — `dpmpp_2m` : l'angle mort n'est que partiellement comblé

C'est le cas exact documenté dans `HANDOFF_2026-08-03.md` (avant l'ajout de
`CLAUDE-english.md`, la puce ADR-002/003 ressortait ~68e/268 sur une requête
française). Mesure fraîche sur l'index actuel (`--top-k 30`) :

```
EN "dpmpp_2m sampler default"     -> CLAUDE-english.md rang #1 (score 0.033)
FR "sampler dpmpp_2m par defaut"  -> CLAUDE-english.md rang #9 (score 0.023)
                                   -> CLAUDE.md          rang #11 (score 0.022)
```

**Amélioration réelle mais incomplète** : `CLAUDE-english.md` ajouté a fait
remonter le chunk correct de ~68e à 9e — un gain net et mesurable, la source
anglaise est maintenant elle-même bien mieux classée — mais ni elle ni
`CLAUDE.md` n'atteignent le top-5 pour cette formulation française
spécifique. Les deux premiers résultats FR (`DOCS/MD/Audit de maturité
technique 2026...` et `DOCS/MD/Prompt engineering robuste...`, scores 0.026)
sont **hors sujet** — ils parlent de DesignLock et de tags de prompt, pas de
sampler.

**Comparaison directe avec le cas 2 (`taesdxl`), même chunk source, résultat
opposé** — les deux termes vivent dans le même chunk `CLAUDE.md`/
`CLAUDE-english.md` ("Decisions that constrain future changes", la même
puce ADR-002/003 mentionne les deux). Pourtant :

- FR "VAE taesdxl" → ce chunk en position **#1** (score 0.033, identique à
  l'EN).
- FR "sampler dpmpp_2m par defaut" → le **même chunk** en position **#9**
  (score 0.023).

**Explication technique la plus probable** : la requête `VAE taesdxl` n'a
que 2 tokens, tous deux des identifiants exacts partagés mot-à-mot entre
français et anglais (`VAE` est utilisé tel quel en français technique,
`taesdxl` est un nom propre). BM25 a un signal fort, non dilué. La requête
`sampler dpmpp_2m par defaut` a 4 tokens dont 2 (`sampler`, `par defaut`)
n'ont pas de correspondance exacte forte côté texte source anglais
(`default`, pas `defaut` ; `sampler` seul est un terme plus généralement
diffus dans le corpus, moins discriminant qu'un identifiant unique comme
`taesdxl`) — le score RRF fusionné se retrouve dilué par des mots-clés
supplémentaires qui matchent mal, alors que la requête à 2 tokens n'a que du
signal fort. **Ce n'est donc pas un défaut de `CLAUDE-english.md` en soi,
mais un effet de longueur/composition de requête** qui touche plus ce terme
que les 4 autres testés ici.

## Autres observations utiles

- **Cas 3, 4, 5 : le RAG n'a pas besoin de `CLAUDE-english.md` pour bien
  répondre en français** — dans ces trois cas, une source française
  pertinente existe déjà nativement (`DOCS/LLM-Secour.md`,
  `RAPPORT_AUDIT_PIPELINE_AOUT2026.md`/`DOCS/RAG_SOURCES.md`, `CLAUDE.md`) et
  ressort en tête avec un score quasi identique à l'équivalent EN — la
  question du gap cross-lingue ne se pose que pour du contenu qui n'existe
  **que** dans une des deux langues, ce qui est le cas de la section ADR
  (rédigée en anglais dans `CLAUDE.md` par convention ADR-006) mais pas de
  la plupart du reste du dépôt.
- **Le gain de `CLAUDE-english.md` sur les requêtes anglaises est net et
  confirmé** (cas 1, 2, 5 : `CLAUDE-english.md` en tête, score identique ou
  quasi identique à `CLAUDE.md`) — l'objectif "une requête en anglais
  retrouve directement le passage" (noté dans `DOCS/RAG_SOURCES.md`) est
  bien atteint.
- **La piste "reformuler la question dans la langue du document cible"**
  (déjà documentée comme contournement dans `HANDOFF_2026-08-03.md`) reste
  la solution la plus fiable pour le cas `dpmpp_2m` en attendant un
  enrichissement — confirmé de nouveau ici (la requête EN sur exactement le
  même besoin d'information place le bon chunk en #1).

## Conclusion — enrichissement supplémentaire nécessaire ou pas ?

**Partiellement comblé, pas résolu.** `CLAUDE-english.md` :

- **Résout complètement** le cas où la requête est elle-même en anglais
  (objectif initial atteint).
- **Améliore mais ne résout pas** le cas résiduel où une requête française
  courte contient un identifiant technique rare (`dpmpp_2m`) noyé parmi des
  mots génériques sans équivalent lexical direct côté source anglaise — gain
  réel (68e → 9e) mais insuffisant pour un usage pratique (top-5).
- **N'était pas nécessaire** pour 3 des 5 termes testés (contenu déjà
  disponible nativement en français avec un score comparable).

**Recommandation** : ne pas complexifier maintenant (pas de double-retrieve
bilingue automatique, déjà écarté dans `HANDOFF_2026-08-03.md` comme
"retour sur investissement incertain vu la taille du corpus" — ce test ne
change pas ce calcul, un seul cas sur 5 est concerné). Si le cas `dpmpp_2m`
revient en pratique, la piste la moins chère est **d'ajouter un alias
français entre parenthèses directement dans la puce ADR-002/003 de
`CLAUDE.md`/`CLAUDE-english.md`** (ex. "sampler par défaut (`dpmpp_2m`)")
plutôt que d'ajouter une couche de traduction de requête — un changement de
quelques mots dans une source déjà indexée, pas une nouvelle dépendance.

---

*Index utilisé : 307 chunks / 12 sources, état du commit `86262a8`. Aucune
reconstruction d'index effectuée pour ce test.*

# Hermes — protocole d'orchestration multi-LLM
`DOCS/HERMES/HERMES.md` — ce fichier explique le système. Le REGISTRE et les briefs vivent à côté (arborescence §1).

## Ce que Hermes n'est pas

Ce n'est pas un outil, pas un script (v1), pas un projet. C'est un dossier de 2 fichiers + une discipline. Budget de mise en place : 30-60 min. Si vous êtes encore en train d'affiner un template après une heure, c'est de la sur-ingénierie — arrêtez et lancez le premier brief.

## Différence avec `LLM-Secours.md`

| | `LLM-Secours.md` | `Hermes` (ce fichier) |
|---|---|---|
| Déclencheur | Claude Code indisponible (quota épuisé) | Décision délibérée de ne pas consommer de quota Claude |
| Posture | Réactif — reprendre sans casser le dépôt | Proactif — répartir le travail avant d'en avoir besoin |
| Contenu | Règles non négociables, pièges déjà rencontrés, modèles locaux Aider | État d'avancement du plan, briefs sortants, table de routage |
| Portée | Tout outil qui touche au **dépôt** (code, commits) | Toute tâche, y compris hors dépôt (recherche, synthèse, brainstorm, writeup) |

**Un outil qui reprend via Hermes et qui va toucher au dépôt doit quand même lire `LLM-Secours.md`.** Les deux se complètent, ne se remplacent pas. `workspace/external_ai_sessions/` (LLM-Secours) reste le journal des sessions qui ont touché au code ; le REGISTRE Hermes est le tableau de bord du plan, à un niveau au-dessus.

## 1. Arborescence

```
DOCS/HERMES/
├── HERMES.md             ← ce fichier
├── REGISTRE.md           ← tableau d'état, une ligne par tâche du plan
├── OUTBOX/                ← briefs à envoyer, un .md par tâche
│   └── H-001_....md
├── INBOX/                 ← retours bruts collés depuis le web, avant intégration
│   └── H-001_retour.md
└── TEMPLATES/
    └── brief.md
```

## 2. `REGISTRE.md` — gabarit initial

Une ligne par tâche issue de `PLAN_MASTER_80J_AOUT_OCT2026.md`. Statuts : 📋 à faire · ⏳ en cours · ✅ fait · ❌ bloqué.

Règle : un ID une fois attribué n'est jamais réutilisé, même si la tâche est abandonnée (statut ❌ + note plutôt que suppression). Le REGISTRE se met à jour en fin de chaque session, Claude Code comme externe.

## 3. `TEMPLATES/brief.md` — gabarit à copier pour chaque `OUTBOX/H-0XX_....md`

Règle stricte : un brief doit être compréhensible **sans aucun autre document**. Si la tâche nécessite plus de contexte que 10 lignes, c'est qu'elle n'est pas assez découpée — la re-découper plutôt que d'agrandir le contexte.

## 4. Table de routage (résumé opérationnel)

| Besoin | Aller vers | Pourquoi |
|---|---|---|
| Touche au dépôt, code critique, intégration | **Claude Code** | Seul habilité à committer/pousser (voir `LLM-Secours.md`) |
| Long contexte, synthèse multi-docs | **Gemini (AI Studio)** | Fenêtre XXL — mais **toujours faire relire la sortie contre le dernier `contexte_*.md`/HANDOFF avant de l'exploiter** (cf. incident RTX 2070 du 09/08 : Gemini a mélangé des époques du projet malgré accès complet au contexte) |
| Question ancrée sur le lore/la bible du World | **NotebookLM** | Réponses sourcées au corpus, pas d'extrapolation |
| Writeup FR, candidature, dialogues PNJ FR | **Le Chat (Mistral)** | Bon en français, signal positif pour la candidature |
| Script isolé, algorithme, code hors dépôt critique | **DeepSeek** | Quasi illimité en gratuit |
| Batch de variations (prompts, noms, dialogues) | **Groq / Cerebras** | Vitesse, quotas cumulables |
| Répétitif, sensible, ou volume | **Ollama local (5060 Ti)** | Illimité, privé — voir aussi table des modèles locaux dans `LLM-Secours.md` |

## 5. Cycle d'une tâche

1. Ouvrir une ligne `H-0XX` dans `REGISTRE.md`, statut 📋.
2. Écrire le brief dans `OUTBOX/H-0XX_....md` (gabarit §3).
3. Envoyer au LLM cible, coller la réponse brute dans `INBOX/H-0XX_retour.md`.
4. **Ne jamais intégrer un retour INBOX tel quel** — c'est de la matière première non fiable. Claude Code (ou vous) vérifie/adapte avant d'écrire dans le dépôt réel. Si le retour touche au code, relire aussi `LLM-Secours.md` §"Erreurs déjà commises" avant de faire confiance à un résultat qui semble marcher.
5. Une fois intégré : statut ✅ dans REGISTRE, `Fichier retour` renseigné, purger `INBOX/H-0XX_retour.md` (garder trace dans le REGISTRE suffit).
6. Si bloqué : statut ❌ + une ligne de note dans REGISTRE (pas besoin d'un fichier séparé pour un blocage simple).

## 6. Ce qui n'est PAS dans ce fichier

Toutes les règles non négociables (contexte 90/92%, GPU, `ast.parse()`, commits, secrets, vie privée, traçage GPU) sont dans `CLAUDE.md` et rappelées dans `LLM-Secours.md` — elles s'appliquent identiquement à tout travail routé via Hermes dès qu'il touche au dépôt. Ne pas les dupliquer ici.

## 7. Hermes v2 (ne pas construire avant octobre, seulement si v1 a prouvé son utilité)

Script `agents/infra/hermes.py` qui lirait OUTBOX, appellerait directement les API gratuites (Gemini AI Studio, Groq, Cerebras, DeepSeek), écrirait INBOX, mettrait à jour REGISTRE automatiquement. Hors scope tant que le protocole manuel n'a pas tourné sur quelques tâches réelles.

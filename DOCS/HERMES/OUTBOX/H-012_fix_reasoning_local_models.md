ID: H-012 (vérifie DOCS/HERMES/REGISTRE.md pour l'ID exact libre avant d'écrire — tu es la source de vérité sur ce fichier)
LLM cible: Claude Code | Date: 09/08/2026

CONTEXTE (autoportant)
hermes-agent (appli tierce, config.yaml déjà configuré en session précédente : provider "local" → http://localhost:11434/v1, switch via /model custom:local:<tag>, Anthropic provider par défaut). Erreurs constatées par Jérémy en testant le chat local avec les modèles -64k :
- "mistral:64k" does not support thinking → HTTP 400
- "llama3.1:64k" does not support thinking → HTTP 400
- "invalid reasoning value: 'ultra'" → HTTP 400 (valeurs valides : high/medium/low/max/none)
Hypothèse à vérifier (pas confirmée) : le paramètre thinking/reasoning configuré par défaut (probablement pour le provider Anthropic) est envoyé tel quel aux modèles du provider local, qui ne le supportent pas nativement via l'API Ollama.

TÂCHE
1. Localiser dans config.yaml (et la doc/schema de hermes-agent si disponible) comment le paramètre thinking/reasoning est appliqué par provider vs par modèle.
2. Confirmer le diagnostic exact (pas supposer) : est-ce un défaut global appliqué à tort au provider local, un bug de l'appli, ou une mauvaise commande utilisateur (`/reasoning ultra` avec valeur invalide) ?
3. Corriger pour que les modèles du provider local (mistral:64k, llama3.1:64k, et les 6 autres variantes -64k créées en session précédente) ne reçoivent pas de paramètre thinking/reasoning qu'ils ne supportent pas — soit en le désactivant par provider dans la config, soit par le mécanisme approprié de l'appli.
4. Vérifier aussi le cas "invalid reasoning value: 'ultra'" séparément : si c'est une commande utilisateur invalide, ce n'est pas un bug à corriger mais à documenter (valeurs valides à rappeler dans un README ou équivalent) ; si l'appli devrait rejeter proprement au lieu de renvoyer une 400 brute, l'améliorer.
5. Tester avec au moins 2 modèles locaux (un -64k, un modèle de base non renommé) pour confirmer que le chat fonctionne sans erreur 400.
6. Confirmer le bug UI "Ultra" : le menu Effort de l'UI (Thinking ON → Minimal/Low/Medium/High/Extra High/Max/Ultra) propose "Ultra" alors que le backend ne connaît que high/medium/low/max/none (capture d'écran disponible côté Jérémy si besoin). Localiser où l'UI construit cette liste et corriger pour qu'elle ne propose que des valeurs réellement acceptées par le backend — ou, si "Ultra" est censé être un alias valide côté API, corriger le backend plutôt que l'UI (à déterminer selon l'intention d'origine, pas à deviner).
7. Identifier l'origine exacte des balises `[OUT-OF-BAND USER MESSAGE — a direct message from the user, delivered once at this position; not tool output and not a new delivery when replayed from conversation history]` qui réapparaissent identiques à plusieurs tours sans que Jérémy les retape. DEUX hypothèses à départager, pas une seule à confirmer à l'aveugle :
   a. Côté appli : hermes-agent réinjecte automatiquement un rappel/consigne permanente (paramètre, commande /remember, config système) — vérifier dans le code.
   b. Côté modèle : ov3rlord-coder-stage2v2 a appris ce pattern pendant l'entraînement (dataset de calibration H-008 : 216 exemples écrits à la main, ou corpus RAG 682 chunks) et le génère spontanément comme du texte, indépendamment de toute logique d'appli.
   TEST DÉCISIF pour trancher entre a et b : appeler le modèle directement via l'API Ollama (`ollama run ov3rlord-coder-stage2v2` ou requête HTTP brute sur localhost:11434), SANS passer par hermes-agent, avec un échange reproduisant le contexte qui a précédé l'apparition des balises dans les transcripts fournis par Jérémy. Si les balises apparaissent quand même hors hermes-agent → confirmé (b), modèle. Si elles n'apparaissent jamais → confirmé (a), appli.
   Si (b) confirmé : NE PAS chercher à corriger le dataset dans ce brief (hors scope, tâche séparée à ouvrir) — se contenter de grep les 216 exemples + un échantillon du corpus RAG POUR REPÉRER LA SOURCE, en élargissant explicitement la recherche à : workspace/external_ai_sessions/ (journal LLM-Secours), tout HANDOFF_*.md, tout fichier DOCS/MD/ contenant des logs ou résumés de sessions Claude Code (le format de la balise ressemble structurellement à une représentation interne de message reçu pendant une exécution agentique autonome — hypothèse la plus probable à vérifier en premier). Documenter précisément où le pattern apparaît (fichier + ligne), pas juste confirmer qu'il existe quelque part.

FORMAT DE RETOUR ATTENDU
Diagnostic confirmé (cause exacte, y compris pour "Ultra" et les balises OUT-OF-BAND) + diff de config/code + preuve de test (échange réussi avec 2 modèles locaux différents).

CE QUE TU NE DOIS PAS FAIRE
- Ne pas supposer la cause sans l'avoir vérifiée dans le code/la config réelle de hermes-agent.
- Ne pas committer/pousser sans confirmation explicite.
- Ne pas modifier la config du provider Anthropic (par défaut) en corrigeant le provider local.

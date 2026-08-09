ID: H-013 (vérifie DOCS/HERMES/REGISTRE.md pour l'ID exact libre avant d'écrire)
LLM cible: Claude Code | Date: 09/08/2026

CONTEXTE (autoportant)
hermes-agent (appli tierce installée en session précédente, config déjà touchée en H-012 : reasoning_overrides, agent/prompt_builder.py, hermes_constants.py connus). Jérémy découvre les commandes au fil des bugs (/model, /steer) plutôt que d'avoir une doc claire. Besoin : liste exhaustive des commandes slash disponibles et de ce que chacune fait réellement, pas juste leur existence.

TÂCHE
1. Grep le source de hermes-agent pour toutes les commandes slash supportées (pattern de parsing des commandes — chercher où `/model`, `/steer` sont gérés pour trouver le dispatcher central, puis lister tout ce qui passe par le même mécanisme).
2. Pour chaque commande trouvée : syntaxe exacte, ce qu'elle fait concrètement (pas juste le nom), et si elle a un effet persistant sur la conversation (comme /steer qui laisse une balise dans l'historique) ou ponctuel.
3. Vérifier si un `/help` ou équivalent existe déjà dans l'appli et si sa sortie est complète ou partielle par rapport à ce que le grep trouve.
4. Documenter spécifiquement les réglages liés aux modèles locaux et au reasoning (déjà touchés en H-012) : comment les invoquer/modifier via commande plutôt que config.yaml, si possible.

FORMAT DE RETOUR ATTENDU
Un fichier DOCS/MD/HERMES_AGENT_COMMANDES.md (markdown), une commande par section : syntaxe, effet réel, persistant ou non, exemple d'usage.

CE QUE TU NE DOIS PAS FAIRE
- Ne pas inventer d'effet de commande non vérifié dans le code — si le comportement exact n'est pas clair à la lecture, le tester plutôt que de deviner.
- Ne pas committer/pousser sans confirmation explicite.
- Ne pas modifier le comportement de hermes-agent dans cette tâche — documentation uniquement.

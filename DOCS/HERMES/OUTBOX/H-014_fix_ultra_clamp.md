ID: H-014
LLM cible: Claude Code | Date: 09/08/2026

CONTEXTE (autoportant)
Suite de H-012 : "Ultra" (et xhigh/minimal) sont des valeurs légitimes côté hermes_constants.py/UI, mais Ollama n'accepte que high/medium/low/max/none. Le CustomProfile ne clampe pas les valeurs hors de ce sous-ensemble avant l'appel API → 400. Laissé hors scope en H-012 (fix config uniquement à l'époque). Reste latent sur gemma4:12b-64k, gemma4:31b-64k, ov3rlord-coder-stage2v2 (les 3 modèles thinking) si "Ultra"/"xhigh"/"minimal" est sélectionné manuellement dans l'UI.

TÂCHE
1. Localiser où CustomProfile construit/envoie la valeur reasoning_effort vers l'API Ollama.
2. Ajouter un clamp : toute valeur hors {high, medium, low, max, none} envoyée à un modèle Ollama est ramenée à la valeur valide la plus proche (ultra/xhigh → max ; minimal → low, à confirmer/ajuster si une correspondance plus logique existe) avant l'appel API — pas d'erreur 400 côté utilisateur pour un choix qui existe dans son propre menu.
3. Tester avec "Ultra" sélectionné sur un modèle thinking (gemma4:12b-64k) : confirmer que ça fonctionne sans 400 après clamp.
4. Ne pas toucher aux valeurs déjà correctes (high/medium/low/max/none) — comportement inchangé pour elles.

FORMAT DE RETOUR ATTENDU
Diff du fix + preuve de test (échange réussi avec "Ultra" sélectionné).

CE QUE TU NE DOIS PAS FAIRE
- Ne pas committer/pousser sans confirmation explicite.
- Ne pas changer le menu UI (les valeurs proposées restent les mêmes) — uniquement le clamp avant l'appel API.

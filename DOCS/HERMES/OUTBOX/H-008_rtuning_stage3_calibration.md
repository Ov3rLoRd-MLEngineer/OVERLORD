ID: H-008 | LLM cible: Claude Code | Date: 09/08/2026

CONTEXTE (autoportant)
Projet Ov3rLoRd. Checkpoint QLoRA existant : ov3rlord-coder-stage2v2 (Qwen3-4B, Stage 1 = The Stack v1 Python, Stage 2 = CommitPack Python). Benchmark récent (8 prompts, 3 modèles) : ov3rlord-coder-stage2v2 excellent en style (4.25/5) mais confabulation systématique (2.38/5 factuel). Un système RAG (multilingual-e5-small, hybrid BM25+semantic, RRF fusion, ~682 chunks, intégré dans llm_router.py avec garde anti-extrapolation) couvre déjà une partie du problème. Approche complémentaire identifiée mais jamais implémentée : R-Tuning Stage 3 — entraînement QLoRA visant à calibrer le modèle pour qu'il reconnaisse et signale explicitement quand il ne sait pas / n'est pas sûr, plutôt que de confabuler avec assurance. GPU cible : RTX 5080 (GPU 0, réservé entraînement, libre — la 5060 Ti est occupée par un pull de modèle en arrière-plan).

TÂCHE
1. Rechercher la méthodologie R-Tuning (papier + implémentations de référence si disponibles) et produire un plan d'implémentation concret adapté à cette infra (Qwen3-4B QLoRA, un seul GPU 16GB) avant de coder quoi que ce soit — le soumettre pour validation rapide avant de lancer un entraînement long.
2. Construire un jeu de données de calibration : paires (prompt, réponse correcte/incorrecte, label de confiance) à partir des prompts de benchmark existants + du corpus déjà indexé dans le RAG (682 chunks) comme source de vérité pour juger correct/incorrect.
3. Adapter le pipeline QLoRA existant (celui des Stages 1/2) pour ce nouvel objectif de calibration, en partant du checkpoint ov3rlord-coder-stage2v2.
4. Lancer un premier run d'entraînement (ordre de grandeur attendu : plusieurs heures, comme les stages précédents) et logger la progression comme pour Stage 1/2 (gpu_usage_log.csv).
5. À la fin : évaluer sur les mêmes 8 prompts de benchmark que la session précédente, comparer le taux de confabulation avant/après.

FORMAT DE RETOUR ATTENDU
Plan d'implémentation (étape 1) soumis avant de coder. Puis : script(s) d'entraînement, dataset de calibration produit, résultats du run (loss, durée, GPU log), comparaison benchmark avant/après.

CE QUE TU NE DOIS PAS FAIRE
- Ne pas lancer l'entraînement long avant validation du plan de l'étape 1.
- Ne pas committer/pousser sans confirmation explicite.
- Ne pas toucher à la RTX 5060 Ti (pull gemma4:31b en cours).
- Ne pas dépasser le seuil de contexte 90/92% en session autonome sans s'arrêter et faire un point.
- Ne pas modifier le RAG existant (llm_router.py, garde anti-extrapolation) — cette tâche l'utilise en lecture seule comme source de vérité, ne le fait pas évoluer.

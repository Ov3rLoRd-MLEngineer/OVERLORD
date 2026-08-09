ID: H-002 | LLM cible: Claude Code (ou DeepSeek pour 1er jet, puis relecture Claude Code) | Date: 09/08/2026

CONTEXTE (autoportant)
Projet Ov3rLoRd, pipeline anime autonome. Besoin d'un module d'analyse de timing/découpage sur des épisodes de référence (2-3 épisodes), pour alimenter le découpage en plans (previz, tâche H-006 séparée). Approche validée en 3 étages, PAS de résumé frame-par-frame (trop coûteux en GPU) :
1. PySceneDetect pour détecter les coupures (cuts) entre plans.
2. Frame-diff pour estimer cadence/holds à l'intérieur d'un plan.
3. QwenVL appelé sur UNE SEULE keyframe par plan (pas sur chaque frame) — de l'ordre de 300 appels pour 2-3 épisodes, pas 34 000.
Un complément d'annotation humaine (50-100 plans, schéma à 14 champs) sera fait séparément par Jérémy — hors scope ici.

TÂCHE
Écrire un script Python 3.12 (jamais 3.14) qui :
1. Prend un fichier vidéo en entrée.
2. Détecte les cuts avec PySceneDetect et liste les plans (timecodes début/fin).
3. Pour chaque plan, calcule une métrique de frame-diff simple (moyenne des différences pixel entre frames consécutives) pour estimer la cadence.
4. Extrait UNE keyframe par plan (ex. frame médiane du plan) et prépare l'appel à QwenVL (stub acceptable si pas d'accès API — signaler clairement où brancher l'appel réel).
5. Sort un fichier JSON par épisode : liste de plans avec timecodes, métrique de cadence, chemin de la keyframe extraite, et un champ vide pour la sortie QwenVL à remplir.

FORMAT DE RETOUR ATTENDU
Script Python complet (fichier unique de préférence) + exemple de structure JSON de sortie.

CE QUE TU NE DOIS PAS FAIRE
- Ne pas inventer de chemins de fichiers, noms de fonctions ou conventions du dépôt non donnés ci-dessus.
- Ne pas committer/toucher au dépôt.
- Ne pas tenter d'appeler QwenVL sur chaque frame — uniquement 1 keyframe/plan.
- Ne pas implémenter l'annotation humaine à 14 champs — hors scope.

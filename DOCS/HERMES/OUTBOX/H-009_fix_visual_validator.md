ID: H-009 | LLM cible: Claude Code | Date: 09/08/2026

CONTEXTE (autoportant)
Item ouvert du HANDOFF_2026-08-08 (§1) : `visual_validator.py` a probablement le même bug de format Ollama que `visual_qc_svi.py`, qui a déjà été corrigé dans une session précédente. Jamais vérifié depuis. Aucune présence de Jérémy requise pour cette tâche, code isolé.

TÂCHE
1. Localiser `visual_qc_svi.py` dans le dépôt et identifier précisément le fix appliqué au format Ollama (diff/commit si possible via git log/git blame).
2. Localiser `visual_validator.py` et vérifier s'il présente le même symptôme (préciser le symptôme exact trouvé, ne pas juste supposer).
3. Si le même bug est confirmé : appliquer le même pattern de fix.
4. Si le bug n'est pas confirmé ou est différent : documenter précisément ce qui a été trouvé plutôt que d'appliquer un fix par analogie non vérifié.
5. Ajouter ou vérifier un test qui couvre ce cas pour éviter une régression silencieuse.

FORMAT DE RETOUR ATTENDU
Diagnostic clair (bug confirmé identique / différent / absent) + diff du fix appliqué le cas échéant + résultat du test.

CE QUE TU NE DOIS PAS FAIRE
- Ne pas appliquer un fix par analogie sans avoir vérifié que le symptôme est bien le même.
- Ne pas committer/pousser sans confirmation explicite.
- Ne pas toucher à d'autres fichiers que `visual_validator.py` (et son test) sans le signaler.

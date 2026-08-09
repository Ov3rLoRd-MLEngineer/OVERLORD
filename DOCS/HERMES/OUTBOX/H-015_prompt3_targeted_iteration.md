ID: H-015
LLM cible: Claude Code | Date: 09/08/2026

CONTEXTE (autoportant)
Suite de H-011 (adopté, adapter_stage3c_final = référence actuelle). Régression non résolue subsistante : Prompt 3 (fix crash Unicode dans un fichier précis) — H-008 refusait correctement en demandant le fichier ; H-010 ET H-011 confabulent tous les deux un correctif cassé (module inventé). Piste documentée dans VERDICT_H011_OVERREFUSAL_RETRY.md : échantillonnage ciblé plutôt qu'aléatoire pour ce sous-type précis de catégorie A (refus légitimes portant sur un fichier/état spécifique non fourni), au lieu de la catégorie C générique qui avait cassé l'équilibre en H-010.

TÂCHE
1. Relire VERDICT_H011_OVERREFUSAL_RETRY.md et isoler précisément ce qui distingue le Prompt 3 des cas de catégorie A déjà bien gérés (H-008/H-011 stables sur les autres) — pourquoi celui-ci confabule alors que le pattern général tient.
2. Construire un petit lot d'exemples ciblés sur ce sous-type précis (refus légitime face à une référence fichier/état spécifique manquante), PAS un rééchantillonnage générique de toute la catégorie A — viser la cause identifiée à l'étape 1, pas un arrosage large.
3. Continuer l'entraînement depuis adapter_stage3c_final (H-011) — jamais depuis un checkpoint antérieur ou rejeté.
4. Réévaluer sur les mêmes 8 prompts, comparaison à 4 points cette fois (Stage1+2 / H-008 / H-011 / ce nouveau run) — vérifier explicitement que le Prompt 3 est corrigé ET que les 7 autres résultats de H-011 ne régressent pas, notamment le Prompt 7 (flagship, stable depuis H-008).
5. Verdict honnête, même standard que H-010/H-011 : si le trade-off n'est pas net positif, ne pas adopter, documenter pourquoi.

FORMAT DE RETOUR ATTENDU
Diagnostic du Prompt 3, diff du dataset ciblé, paramètres d'entraînement, comparaison à 4 points, verdict d'adoption.

CE QUE TU NE DOIS PAS FAIRE
- Ne pas repartir d'un checkpoint autre que adapter_stage3c_final (H-011).
- Ne pas committer/pousser sans confirmation explicite.
- Ne pas rééchantillonner toute la catégorie A — cible étroite sur le sous-type identifié, pas un arrosage large comme la catégorie C en H-010.
- Ne pas passer sous silence une régression, même mineure, sur les 7 autres prompts déjà stables.

À FAIRE EN PARALLÈLE, SANS ATTENDRE LA FIN DE CETTE TÂCHE
Si une session/GPU est libre pendant que celle-ci tourne : traiter H-013 (doc commandes hermes-agent) et le fix Ultra/clamp (brief séparé, cf REGISTRE) — aucune des deux ne nécessite le GPU d'entraînement, elles peuvent avancer en parallèle sans attendre ce run.

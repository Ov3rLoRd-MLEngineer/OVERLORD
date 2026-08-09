ID: H-011 (vérifie DOCS/HERMES/REGISTRE.md pour l'ID exact libre avant d'écrire — tu es la source de vérité sur ce fichier)
LLM cible: Claude Code | Date: 09/08/2026

CONTEXTE (autoportant)
Suite de H-010 (échec partiel) : le correctif de sur-refus (catégorie C, 26 exemples sur-échantillonnés x6, continuation depuis adapter_stage3_final) a corrigé le cas ciblé mais cassé 2-3 cas déjà résolus par H-008, notamment Prompt 7 (retour à une confabulation sévère). adapter_stage3b_final n'a PAS été adopté. Checkpoint de référence actuel : adapter_stage3_final (H-008). Pistes documentées par toi-même dans le verdict H-010 : réduire le sur-échantillonnage à x2-3 au lieu de x6, LR plus bas, réinjecter un échantillon des catégories A/B (les 216 refus + 300 calibration RAG) pendant la correction plutôt que de compter sur l'adaptateur seul pour ne pas les oublier, plus de diversité dans la catégorie C (pas juste 26 exemples uniques répétés).

TÂCHE
1. Reconstruire la catégorie C avec plus de diversité (viser sensiblement plus que 26 exemples uniques si possible, sans forcer artificiellement).
2. Ré-entraîner en continuation depuis adapter_stage3_final (H-008) — jamais depuis adapter_stage3b_final (H-010, rejeté) ni Stage 2.
3. Appliquer les ajustements : sur-échantillonnage catégorie C réduit à x2-3, LR abaissé (proposer une valeur précise et la justifier), réinjection d'un échantillon des catégories A (216 refus) et B (300 calibration RAG) dans le mix d'entraînement de cette passe.
4. Réévaluer sur les mêmes 8 prompts de VERDICT_COMMITPACK.md, comparaison explicite à 3 points : Stage2 (avant H-008) / adapter_stage3_final (H-008) / ce nouveau run — pas seulement avant/après ce run.
5. Verdict clair : adopter ou non, avec le même niveau d'honnêteté que le rapport H-010 (pas de biais à vouloir que ça marche cette fois).
6. Appliquer aussi le fix CJK (paramètres de génération ajustés, déjà validé en H-010) dans ce nouveau run d'évaluation.

FORMAT DE RETOUR ATTENDU
Diff du dataset (catégorie C reconstruite + réinjection A/B), paramètres d'entraînement utilisés et justification, comparaison à 3 points sur les 8 prompts, verdict d'adoption.

CE QUE TU NE DOIS PAS FAIRE
- Ne pas repartir d'adapter_stage3b_final (rejeté) ni de Stage 2 — uniquement adapter_stage3_final (H-008).
- Ne pas committer/pousser sans confirmation explicite.
- Ne pas suréchantillonner au-delà de x3 sans le justifier explicitement.
- Ne pas passer sous silence une régression si le résultat est encore mitigé — même standard d'honnêteté que H-010.

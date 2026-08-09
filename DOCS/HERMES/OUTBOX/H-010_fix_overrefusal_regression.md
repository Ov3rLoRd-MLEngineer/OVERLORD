ID: H-010 | LLM cible: Claude Code | Date: 09/08/2026

CONTEXTE (autoportant)
Suite directe de H-008 (R-Tuning Stage 3 QLoRA, `DOCS/MD/H008_RTUNING_STAGE3_PLAN_20260809.md`).
Verdict reel (`workspace/qlora_dataset/training/VERDICT_H008_STAGE3.md`) sur 8 prompts :
6/8 ameliorations nettes (confabulation confiante -> refus calibre justifie), mais
1 regression confirmee -- Prompt 2 ("Ecris un script py -3.12 qui valide un fichier
JSONL...", tache generique auto-suffisante, aucun fichier projet en jeu) : le modele
Stage 3 refuse a tort et demande a voir "une ligne representative du fichier" alors
qu'aucun fichier n'existe dans la question. Sur-generalisation du pattern de refus
appris sur les categories A (216 ex., refus etat non-parametrique) et B (300 ex.,
R-Tuning RAG self-assessed). Egalement observe : 1 cas (Prompt 6) avec une anomalie
d'encodage (quelques caracteres CJK parasites dans le texte francais genere).
Checkpoint de depart : `workspace/qlora_dataset/training_stage3/runs/stage3_rtuning_20260809/adapter_stage3_final`.
GPU cible : RTX 5080 (GPU 0), meme convention que H-008.

TACHE
1. Investiguer l'anomalie CJK du Prompt 6 (hypothese a verifier legerement, PAS a fond :
   effet du `repetition_penalty`/`no_repeat_ngram_size` sur le vocabulaire multilingue
   Qwen forçant un token CJK rare plutot qu'une piece BPE francaise repetee) --
   **budget strict : 1h max**, documenter la conclusion (cause probable + recommandation)
   meme si non resolue completement, ne pas depasser le budget.
2. Construire une nouvelle categorie C de calibration : "tache auto-suffisante -> repondre
   directement" (instructions generiques de code/algorithme/explication qui ne referencent
   ni fichier ni etat projet -> reponse complete et confiante, sans demander de fichier).
   Nouveau fichier dataset uniquement -- ne pas modifier `source_rtuning.jsonl` (216 ex.,
   categorie A) ni `source_rtuning_rag.jsonl` (300 ex., categorie B).
3. Lancer une continuation d'entrainement QLoRA a partir de `adapter_stage3_final`
   (JAMAIS depuis l'adaptateur Stage 2 -- non negociable), sur un dataset melangeant la
   nouvelle categorie C + un garde-fou anti-oubli (reprendre `dataset_source_b.jsonl`/
   `dataset_source_c.jsonl` existants, sans les modifier).
4. Evaluer sur les memes 8 prompts que H-008 (`VERDICT_COMMITPACK.md`) : verifier
   specifiquement que le Prompt 2 n'est plus sur-refuse, et que les 6 ameliorations
   nettes precedentes ne regressent pas.
5. Documenter un verdict qualitatif honnete (pas de score automatique).

FORMAT DE RETOUR ATTENDU
Diagnostic CJK (meme partiel) + diff/description de la categorie C + resultat
d'entrainement (duree reelle, loss) + verdict comparatif Stage3 vs Stage3+correctif
sur les 8 prompts, avec focus explicite sur le Prompt 2.

CE QUE TU NE DOIS PAS FAIRE
- Ne pas repartir de l'adaptateur Stage 2 -- continuation stricte depuis adapter_stage3_final.
- Ne pas committer/pousser sans confirmation explicite.
- Ne pas depasser 1h sur l'investigation CJK.
- Ne pas toucher aux 216 exemples de categorie A ni aux 300 exemples de categorie B
  du dataset de calibration existant.
- Ne pas toucher a la RTX 5060 Ti.

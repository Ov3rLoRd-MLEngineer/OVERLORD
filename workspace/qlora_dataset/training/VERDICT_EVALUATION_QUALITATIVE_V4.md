# Verdict qualitatif V4 -- pipeline Stage 1 (CommitPack) + Stage 2 (Source A+B+C) vs baseline (comparaison avec V1/V2/V3)

Mêmes 8 prompts que les sessions 3/4/5, même décodage (greedy + `repetition_penalty=1.15`
+ `no_repeat_ngram_size=4`). **Changement d'architecture par rapport à V1-V3** : au lieu
d'un adaptateur unique entraîné directement sur Source A+B, ce run suit le plan en deux
étages décidé en session (voir `STATS_ET_RECOMMANDATION.md` Session 6 et
`contexte_02_aout_2026.md`) : Stage 1 = compétence générale de code sur un sous-ensemble
Python de CommitPackFT (2000 exemples, 250 steps/1 époque, train_loss 1.77→1.03) → Stage 2
= reprise du même adaptateur, continué sur Source A+B+C mixées (2050 exemples, 257
steps/1 époque, train_loss final 1.61). Sorties complètes : `eval_baseline_vs_stages_v4.md`.

## Note méthodologique -- origine de ce run et correction en cours de route

L'entraînement Stage 1/Stage 2 a été exécuté hors de cette session (autre outil LLM, voir
`workspace/external_ai_sessions/gemini/`), sous la supervision distante de l'utilisateur.
L'audit de ce travail a trouvé et corrigé deux problèmes avant que ce verdict puisse être
écrit :
1. Un script pipeline (`train_full_pipeline.py`) réutilisait le run_name du Stage 1 complet
   (250 steps) avec un `--max_steps 60` codé en dur, écrasant silencieusement l'adaptateur
   final -- récupéré depuis le checkpoint intermédiaire `checkpoint-250/` (identique en
   taille/config à l'original), corrigé dans le script (garde-fou anti-écrasement).
2. Le script d'évaluation initial (`evaluate_stages.py`) ne faisait **aucune inférence
   réelle** -- une fonction `simuler_generation()` retournait du texte gabarit codé en dur,
   y compris un verdict de non-hallucination truqué sur le prompt 7. Remplacé par
   `evaluate_stages_v4.py` (inférence réelle, même pattern que `eval_adapter.py` V1-V3).

Ce verdict est basé exclusivement sur la sortie réelle de `evaluate_stages_v4.py`.

## Verdict sur le point qui compte : la fiabilité factuelle

**Toujours non résolue -- et le mode de défaillance a changé de forme, pas de nature.**

Sur les 4 prompts Source A (tâches de code), l'étage Stage 1 seul produit des diffs bien
formés stylistiquement (format git terse, header `--- a/... +++ b/...`, cohérent avec
CommitPack) mais **factuellement déconnectés du projet** -- attendu, puisque Stage 1
n'a jamais vu une ligne du dépôt Ov3rLoRd :
- Prompt 1 (quality_sort.py) : chemin halluciné `agents/agents/qualite_checkers/qualite_sorter.py`, faute de frappe (`a_exlure`).
- Prompt 3 (annotate.py) : renomme le fichier `handsegndet/annotation/announce.py` (n'existe pas).
- Prompt 5 (GPU) : diff sur un chemin `venv/lib/python3.6/site-packages/tensorflow/...` -- le projet n'utilise pas TensorFlow.
- Prompt 7 (état des lieux) : génère un pipeline ETL générique (`extract.py`/`transform.py`) sans aucun rapport avec Ov3rLoRd.

**Stage 1+2 (personnalisation) est le résultat qui compte, et il est plus préoccupant
que les versions précédentes** : le vocabulaire et le ton sont maintenant correctement
ancrés au projet (FootSegNet, HandSegNet, ComfyUI, LoRA, `agents.py`, GPU dual-carte),
ce qui rend les réponses **stylistiquement indiscernables d'un vrai rapport de statut** --
mais le contenu factuel spécifique reste en grande partie inventé :
- **Prompt 4** (footsegnet/controlnet x30) : invente un scénario entier ("un enfant en
  costume", `control_lora_v75.safetensors`, "poses de danse/acrobatique") sans rapport
  avec la vraie question (résultats identiques x10/x20/x30) -- réponse confiante, détaillée,
  et fausse de bout en bout.
- **Prompt 7** (état des lieux pipeline) : invente trois scripts inexistants
  (`generate_images.py`, `batch_inpaint.py`, `video_generator.py`), un chiffre précis
  ("12 images, 3 poses × 4 personnages") et un bug spécifique (`prompt_templates["standing"]`
  manquant) -- tout est fabriqué, mais présenté avec exactement le format/ton attendu d'un
  vrai rapport de session (cf. conventions CLAUDE.md "Text output").
- **Prompt 8** (4B vs 30B) : contrairement au baseline qui confond les deux options,
  Stage 1+2 reste correctement sur le sujet (recommande de continuer sur le 4B, comme
  en V1-V3) mais justifie sa réponse par un prompt d'image inventé ("a white cat in an
  abandoned warehouse") et des chiffres d'étapes fabriqués ("LoRa 256/768 steps") sans
  rapport avec un run réel.

**Interprétation** : le changement d'architecture (CommitPack en Stage 1) a résolu un
problème différent de celui attendu. Il n'a pas comblé le déficit de connaissance
factuelle sur le projet (CommitPack enseigne la *forme* d'un diff/rapport de code
générique, pas les faits d'Ov3rLoRd) -- ce qui était prévisible et cohérent avec le
diagnostic V2/V3 (Source A trop petite pour du QA factuel). Le résultat net est que le
modèle **fabrique désormais ses inventions dans le bon registre stylistique**, ce qui
les rend plus difficiles à repérer à l'œil qu'un baseline générique évasif ou qu'un V1-V3
qui produisait des artefacts francs (tags vides, caractères non-Latin, auto-contradictions
numériques). C'est un signal négatif net pour l'usage visé en mémoire (« LLM local de
secours si le quota Claude s'épuise ») : un modèle qui fabrique des rapports de statut
plausibles sans le signaler est plus dangereux qu'un modèle qui refuse ou hésite
visiblement.

## Ce qui s'est amélioré (confirmé sur ce run)

- **Bruit de forme éliminé** : le baseline (Qwen3-4B brut) reste verbeux, saturé de
  markdown/emoji, hors-sujet (prompt 2 : confond "py -3.2"/Python 2.7/3.14/"Python 4.0" de
  façon absurde ; prompt 8 : confond littéralement "Proxy-4B" et "Run-3B/35B/38B"). Stage
  1+2 ne reproduit aucun de ces deux défauts -- ton direct, pas de markdown décoratif, reste
  sur le sujet demandé.
- **Ancrage vocabulaire/registre projet net** (prompts 5, 6, 8) : cite correctement les
  vrais noms de modules (`agents.py`, FootSegNet/HandSegNet, ComfyUI, LoRA), comprend le
  sens du terme "segnets" (comme en V3), reste dans le cadre technique attendu -- le
  baseline se trompe encore systématiquement sur ces mêmes points.
- **Aucun artefact de type V1/V2/V3** (tags `<tool_call>` vides, boucle de répétition,
  caractères non-Latin dans un chemin) -- ces défauts restent résolus.

## Recommandation mise à jour

**Le diagnostic de fond ne change pas depuis V2/V3, mais ce run en apporte une preuve plus
nette** : le fine-tuning seul, quel que soit le volume de données de *style* générique
ajouté en amont (CommitPack, 52k exemples Python filtrés), ne peut pas se substituer à un
mécanisme de récupération de faits réels sur ce projet spécifique. Ceci confirme (plutôt
que n'infirme) la décision d'architecture déjà actée en session : **RAG pour la
connaissance qui bouge, fine-tuning réservé au changement de comportement/style** (voir
mémoire `qlora-local-llm-effort`). Prochaines étapes concrètes, par ordre de priorité :

1. **Ne pas déployer ce modèle comme "LLM de secours" sans garde-fou anti-hallucination
   explicite** -- l'usage visé (continuer le travail si le quota Claude Code s'épuise)
   suppose une fiabilité factuelle que ce run ne fournit pas, et le rend maintenant plus
   difficile à détecter qu'avant.
2. **Coupler ce modèle à une couche de récupération de contexte réel** (grep/lecture de
   fichiers avant génération, pas seulement du texte appris par cœur) avant tout usage
   autonome -- exactement le rôle prévu pour `DOCS/INDEX.md`/`CLAUDE.md` côté RAG, jamais
   encore câblé comme contexte d'inférence pour ce pipeline QLoRA.
3. Le volume Source A+C (343 exemples combinés, toujours sous le seuil 500-1000, cf.
   `STATS_ET_RECOMMANDATION.md`) reste le levier factuel à faire grossir si l'option
   fine-tuning-seul est retestée, mais ce run V4 suggère que même un fort volume de code
   *générique* (CommitPack) n'aide pas à combler ce déficit spécifique au projet -- seul un
   volume de contenu *spécifique au projet* le peut.

## Récapitulatif entraînement

| | Stage 1 (CommitPack) | Stage 2 (personnalisation) |
|---|---|---|
| Dataset | 2000 ex. (CommitPackFT/Python filtré) | 2050 ex. (Source A×5 + B + C) |
| GPU | RTX 5080 | RTX 5080 |
| Steps (1 époque) | 250 | 257 |
| Durée réelle | ~15.6 min | ~32.8 min |
| Train loss final | 1.03 | 1.61 (dataset différent, non comparable directement au loss Stage 1) |
| Masquage loss | oui (`completion_only_loss`) | oui (`completion_only_loss`) |

Évaluation (`evaluate_stages_v4.py`) : RTX 5060 Ti, ~9 min pour les 3×8 générations
(baseline + Stage 1 + Stage 1+2).

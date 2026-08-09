# H-008 — R-Tuning Stage 3 : plan d'implémentation (étape 1, à valider avant tout entraînement)

Date : 2026-08-09. Brief source : `DOCS/HERMES/OUTBOX/H-008_rtuning_stage3_calibration.md`.

## 1. Méthodologie R-Tuning (référence)

Papier : Zhangyue Yin et al., *R-Tuning: Instructing Large Language Models to Say "I Don't Know"*, NAACL 2024 (Outstanding Paper) — [arXiv:2311.09677](https://arxiv.org/abs/2311.09677), code officiel [github.com/shizhediao/R-Tuning](https://github.com/shizhediao/R-Tuning).

Principe exact (pas une paraphrase approximative) :
1. On dispose d'un jeu de questions à réponse vérifiable (QA avec ground truth).
2. On fait générer ses propres réponses au modèle **avant** ce stage de tuning (le modèle courant, pas un juge externe).
3. On compare chaque réponse générée à la ground truth : si elle correspond → exemple **"certain"** (le modèle sait) ; si elle diverge → exemple **"uncertain"** (le modèle ne sait pas, même s'il a répondu avec assurance).
4. On fine-tune sur ce jeu ré-étiqueté : la sortie attendue devient une expression de confiance calibrée sur la propre capacité du modèle, pas sur une liste de sujets décrétés "difficiles" a priori.
5. Résultat rapporté par les auteurs : le refus calibré est une compétence qui se généralise au-delà des questions vues à l'entraînement.

Le point clé à ne pas perdre : **la certitude/incertitude est mesurée empiriquement (le modèle se trompe-t-il vraiment ?), pas décidée a priori par catégorie de sujet.**

## 2. État existant déjà présent dans le dépôt (vérifié avant d'écrire ce plan)

- `workspace/qlora_dataset/scripts/build_source_rtuning.py` existe déjà et a déjà produit `workspace/qlora_dataset/source_rtuning.jsonl` (216 exemples, 108 certain / 108 incertain, généré par une session antérieure).
- Ce dataset **n'est pas du R-Tuning au sens strict** : les catégories "incertain" sont écrites à la main (fichier non lu, GPU non vérifié en direct, mémoire de session absente, etc.), pas dérivées d'un vrai/faux mesuré sur les réponses du modèle. C'est un choix défendable et bien documenté (ancré sur les confabulations réelles de `VERDICT_COMMITPACK.md`), mais ça couvre un axe différent : le refus par **absence d'accès à un état non-parametrique** (fichier, GPU, session), pas le refus par **absence de connaissance paramétrique** que R-Tuning cible à l'origine.
- Aucun script `train_stage3*.py` n'existe encore. Aucune ligne H-008 dans `gpu_usage_log.csv` — aucun entraînement n'a été lancé.
- Checkpoint de départ confirmé : `ov3rlord-coder-stage2v2` = adaptateur `workspace/qlora_dataset/training_stage2/runs/stage2_instructions_v2/adapter_stage2_final` (un `merged_fp16` existe déjà au même endroit, réutilisable directement pour l'inférence sans recharger PEFT).
- RAG confirmé : `workspace/rag_index/chunks.jsonl`, 682 chunks `{id, source, heading, text}` indexant `CLAUDE.md`, les ADR, les rapports d'audit, etc. — exactement le type de contenu factuel vérifiable (sampler par défaut, VAE, convention GPU, etc.) sur lequel un vrai protocole R-Tuning peut s'appuyer comme ground truth.
- GPU vérifié à l'instant (`nvidia-smi`) : RTX 5080 (GPU 0) = 0 Mo utilisés, libre. RTX 5060 Ti = 482 Mo, `ollama ps` ne montre aucun modèle chargé actuellement (le pull en cours est un téléchargement, pas une charge GPU continue) — je ne la touche pas de toute façon, conformément à la consigne.

## 3. Proposition : hybride, pas un remplacement du travail déjà fait

Combiner deux catégories plutôt que de jeter les 216 exemples existants :

**Catégorie A — refus d'accès à un état non-parametrique** (déjà construite, `source_rtuning.jsonl`, 216 ex.). Conservée telle quelle : c'est précisément le mode de confabulation le plus grave et le plus documenté (`VERDICT_COMMITPACK.md`, invention de GPU/chemins/résultats de session).

**Catégorie B — calibration R-Tuning classique sur connaissance paramétrique du projet** (à construire, nouvelle) :
1. Générer ~150-200 questions factuelles vérifiables à partir des 682 chunks RAG (ex. "Quel VAE est utilisé sur ce dépôt et pourquoi ?", "Quel sampler par défaut, et quelle exception documentée ?") — une question par chunk ou groupe de chunks à contenu factuel dense (ADR, conventions GPU, sections de CLAUDE.md), en excluant les chunks non factuels (sections narratives/génériques).
2. Faire générer la réponse par le modèle **actuel** (`merged_fp16` de stage2v2, chargé via `FastLanguageModel` sur `cuda:0`/RTX 5080 — pas Ollama, pour ne pas toucher à la RTX 5060 Ti) sur chacune de ces questions, en greedy comme dans `evaluate_stages_v4.py`.
3. Juger correct/incorrect par un **matching heuristique de mots-clés/entités** extraites du chunk source (nom de fichier, nom de paramètre, valeur numérique, nom de sampler/VAE) plutôt qu'un juge LLM externe — pour rester sur RTX 5080 uniquement et éviter tout coût/latence supplémentaire. Limite assumée : heuristique, pas un juge sémantique ; un échantillon (~20 cas) sera relu manuellement avant de faire confiance à l'étiquetage automatique complet (cf. CLAUDE.md — ne jamais présenter un résultat auto-généré comme fiable sans vérification).
4. Reformater en paires `(instruction, output)` : "certain" → réponse factuelle directe (garder la génération du modèle si elle est jugée correcte, ou la réponse de référence extraite du chunk sinon) ; "incertain" → réponse calibrée style refus existant ("je ne suis pas sûr de X, je sais avec confiance Y, à vérifier dans {source}").

Total visé : ~350-420 exemples (216 A + ~150-200 B), toujours équilibré certain/incertain à l'intérieur de chaque catégorie.

## 4. Entraînement — config proposée

- Point de départ : `adapter_stage2_final` (stage2_instructions_v2), même schéma que `train_stage2_instructions.py` (continuation directe de l'adaptateur, pas un nouvel adaptateur empilé).
- Config LoRA identique à Stage 2 (r=16, alpha=16, dropout=0, mêmes `target_modules`) — cohérence avec l'existant, pas de raison de changer le rang pour un dataset de cette taille.
- **Garde-fou anti-oubli catastrophique** (le point le plus risqué vu la petite taille du dataset) : mélanger un sous-échantillon aléatoire non-oversamplé de `dataset_source_b.jsonl` (le dataset Stage 2 général) dans le mix Stage 3, dans une proportion modérée (ex. 1x le volume de calibration), pour éviter que le modèle n'apprenne à refuser par défaut ou ne régresse sur ses capacités de code déjà acquises. Sans ce garde-fou, un dataset 100% calibration/refus sur ~400 exemples risque de sur-généraliser le pattern "je ne suis pas sûr" à des questions où il pourrait répondre correctement.
- `learning_rate` plus bas que Stage 2 (proposition : 5e-5 au lieu de 1e-4) et peu d'epochs (2-3) — dataset petit, risque de sur-ajustement rapide sur un pattern de phrase répété (le modèle pourrait apprendre "toujours dire je ne suis pas sûr" au lieu de calibrer réellement).
- **Durée révisée à la baisse par rapport à l'estimation du brief** ("plusieurs heures, comme les stages précédents") : Stage 1/2 portaient sur 150k/200k exemples (~18-24h). Un dataset de ~400-800 exemples (avec le mix anti-oubli) à batch effectif 8 donne de l'ordre de 100-300 steps total sur 2-3 epochs — à ~5s/step (mesuré sur Stage 1/2), ça reste de l'ordre de **10-30 minutes**, pas des heures. Je le signale explicitement plutôt que de laisser courir l'hypothèse initiale du brief sans la corriger.

## 5. Évaluation

Réutiliser la méthode d'`evaluate_stages_v4.py` (inférence réelle, pas de simulation) en ajoutant une 4e colonne "Stage 1+2+3" sur les mêmes 8 prompts (`VERDICT_COMMITPACK.md`), + comparaison qualitative manuelle du taux de confabulation avant/après (même grille que le verdict existant : correct / confabulé / refus calibré correct / refus abusif). Nouveau label de sortie (ex. `v6_stage3`) pour ne pas écraser `evaluation_comparative_v5_stage2v2_resultats.json`.

## 6. Ce qui reste à valider avant de coder/lancer quoi que ce soit

1. **Le mix hybride A+B ci-dessus** (garder les 216 existants + ajouter ~150-200 nouveaux exemples R-Tuning classiques sur le RAG), plutôt que reconstruire uniquement l'un ou l'autre.
2. **Le jugement heuristique par mots-clés** pour classer correct/incorrect (plutôt qu'un juge LLM externe qui toucherait potentiellement à la RTX 5060 Ti ou ajouterait une dépendance non prévue par le brief).
3. **Le garde-fou anti-oubli catastrophique** (mélange avec un sous-échantillon de `dataset_source_b.jsonl`) — écart par rapport à un R-Tuning "pur" mais recommandé vu la petite taille du dataset de calibration.
4. **L'estimation de durée revue à ~10-30 min** plutôt que "plusieurs heures" — pas un blocage, juste une correction d'attente à confirmer que ça n'invalide pas l'intérêt de la tâche.

Aucun code de dataset/training supplémentaire n'a été écrit à ce stade ; aucun entraînement n'a été lancé. En attente de validation avant de poursuivre (étapes 2-5 du brief).

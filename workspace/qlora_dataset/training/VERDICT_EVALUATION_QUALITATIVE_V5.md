# Verdict qualitatif V5 -- run de confirmation Stage 2 (`stage2_instructions_v2`) vs V4

Run de reproduction, pas un changement d'architecture ni de données : Stage 2
relancé depuis Claude Code (le run V4 avait été fait par un outil externe)
avec exactement les mêmes données (Source A×5 + B + C, 2050 exemples), mêmes
hyperparamètres, même seed (3407), depuis le même adaptateur Stage 1 restauré
(`checkpoint-250`). Objectif : vérifier que le pipeline corrigé (garde-fou
anti-écrasement, run_name obligatoire) reproduit fidèlement le run original,
et obtenir une deuxième mesure indépendante du diagnostic V4. Sorties
complètes : `eval_baseline_vs_stages_v5_stage2v2.md`.

## Entraînement : reproductibilité confirmée

`train_loss` final **identique au bit près** entre `stage2_instructions_full`
(run original, outil externe) et `stage2_instructions_v2` (ce run) :
`1.6073992472678307` sur les deux runs, 257 steps, même durée (~32 min).
Taille de fichier adaptateur identique (132187888 octets). Le pipeline
corrigé produit donc un résultat d'entraînement strictement équivalent à
l'original -- pas de régression introduite par les garde-fous ajoutés.

## Inférence : pas reproductible au token près -- constat nouveau, pertinent pour le diagnostic

Contrairement à l'entraînement, la génération greedy **n'est pas identique**
entre l'évaluation V4 et celle-ci, alors que l'adaptateur Stage 1 utilisé est
strictement le même fichier sur disque dans les deux cas (`evaluate_stages_v4.py`
ne fixe pas de graine pour la génération -- cause probable : non-déterminisme
des noyaux CUDA sur `do_sample=False`, connu et documenté côté PyTorch/CUDA
en l'absence de `torch.use_deterministic_algorithms(True)`). Constat en soi
mineur, mais il **renforce le diagnostic factuel** ci-dessous : si le modèle
produit une hallucination différente à chaque exécution du même adaptateur
sur le même prompt, ce n'est pas un fait mémorisé de façon stable, c'est une
confabulation regénérée à chaque fois.

## Le diagnostic V4 est confirmé, avec une preuve supplémentaire

Sur les 4 prompts Source A, Stage 1 seul continue de halluciner des chemins
de fichiers sans rapport avec le projet (attendu, inchangé depuis V4).

Sur Stage 1+2, le style/ton/vocabulaire reste bien ancré au projet (comme en
V4), mais **le contenu factuel halluciné change d'un run à l'autre** sur les
prompts où V4 avait déjà identifié une fabrication :

- **Prompt 4** (footsegnet/controlnet x30) : V4 inventait un scénario
  "Control-LoRA / enfant en costume" ; V5 invente à la place "FootSegNet
  entraîné sur 48 images, limite architecturale". Deux histoires différentes,
  toutes deux confiantes, détaillées, et sans rapport vérifiable avec la
  vraie question (résultats identiques x10/x20/x30).
- **Prompt 6** (segnets = portefeuille de compétences) : V4 citait
  `agents.py` et une architecture multi-agents ; V5 invente "3 segments
  (ComfyUI/ControlNet, ComfyUI+LoRA, **ComfyHub**)" -- `ComfyHub` n'existe
  nulle part dans le projet, fabrication pure.
- **Prompt 7** (état des lieux) : V4 et V5 réutilisent tous deux
  `generate_images.py`/`batch_inpaint.py` (recurrence notable -- peut-être un
  nom plausible que le modèle génère systématiquement plutôt qu'un vrai
  souvenir), mais le reste du récit (bug précis, scripts manquants,
  roadmap) diffère entre les deux runs.
- **Prompt 8** (4B vs 30B) : **auto-contradiction dans la même réponse**,
  nouveau et plus net qu'en V4 -- le modèle mentionne tour à tour "Proxy-4B",
  "Proxy-LoRA 8B", "Run 32B", et une commande d'exemple citant
  `meta-llama/Llama-3.2-3B`, quatre tailles de modèle différentes pour
  désigner la même situation. Rappelle directement le mode de défaillance
  déjà documenté en V3 (chiffres auto-contradictoires intra-réponse).

## Conclusion

Ce run de confirmation ne change pas la recommandation V4 : ne pas déployer
ce modèle comme LLM de secours sans grounding factuel réel (RAG/lecture de
fichiers), le fine-tuning seul ne résout pas la fiabilité factuelle. Il
ajoute une preuve supplémentaire et plus directe -- la variabilité des
hallucinations d'un run à l'autre sur le même adaptateur confirme qu'il
s'agit de confabulation, pas de mémorisation, ce qui rend le risque encore
plus difficile à anticiper qu'un défaut stable et reproductible le serait.

## Récapitulatif

| | Stage 2 original (`stage2_instructions_full`, outil externe) | Stage 2 confirmation (`stage2_instructions_v2`, Claude Code) |
|---|---|---|
| GPU | RTX 5080 | RTX 5080 |
| Steps | 257 | 257 |
| Durée | ~32.8 min | ~32.2 min |
| Train loss final | 1.6073992472678307 | 1.6073992472678307 (identique) |
| Taille adapter_model.safetensors | 132187888 octets | 132187888 octets (identique) |

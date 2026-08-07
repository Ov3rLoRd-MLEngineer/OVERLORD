# Contexte Ov3rLoRd — 02 août 2026

Document de reprise après une session très longue (nuit du 28→29 juillet + suite jusqu'au 2 août). Objectif : permettre de reprendre le fil dans une nouvelle conversation sans perdre le contexte.

## Rappel projet

Jérémy Gourlain,(https://github.com/Ov3rLoRd-MLEngineer) studio Onibaku Gumi (鬼爆組, micro-entreprise, Rouen). Projet Ov3rLoRd : pipeline de production anime IA local (ComfyUI, SDXL, checkpoint fabricatedXL_v70/Illustrious, dual-GPU RTX 5080 + RTX 5060 Ti). Objectif : démo technique/visuelle publique convaincante pour candidater chez Mistral ou un studio, deadline fin août. **Dépôt de code privé par défaut** — seuls les modèles de segmentation (poids + inférence) sont publiés en open source, jamais le pipeline d'entraînement complet.

## Chantiers terminés

**HandSegNet — annotation, entraînement et publication complets.**
- 322/322 images annotées manuellement (mode POINT + SAM, une nuit de travail).
- Entraîné : `handsegnet_vit_b_best.pth`, val_IoU interne 0.8876 (box vérité-terrain).
- IoU pipeline réel (box via détection automatique) : 0.722 moyenne / 0.773 médiane — écart documenté et assumé dans le model card, pas caché.
- **Détection de boîte primaire remplacée** : grounding VLM (fragile sur scènes multi-mains) → `hand_yolov9c.pt` (Ultralytics, déjà présent dans ComfyUI/models/ultralytics/bbox/), VLM conservé en fallback. Gain net confirmé (+0.854 et +0.435 IoU sur les cas d'échec, régression négligeable ailleurs).
- **Publié** : GitHub `Ov3rLoRd-MLEngineer/handsegnet` (MIT) + HuggingFace `Ov3rLoRd-MLEngineer/handsegnet` (Apache 2.0, safetensors 375 Mo). Cross-liens avec FootSegNet mis à jour dans les deux sens.
- **À faire plus tard (non bloquant)** : harmoniser le branding — passer à `Ov3rLoRd-MLEngineer` sans mention "Onibaku Gumi" dans les model cards (incohérence signalée entre FootSegNet et HandSegNet, jamais corrigée).

**Wildcards anti-hallucination "camera".** Cause racine trouvée : le mot "camera" dans un prompt (même en contexte "reaching toward camera" = intention POV) active le prior Danbooru "objet photo tenu en main" → halluciné à 100% sur les cas testés. Corrigé dans `gestures.txt` et `prompts_wildcards.txt` (HandSegNet + FootSegNet) : remplacement par vocabulaire Danbooru propre (`pov_hands`, "close to viewer"). Validé à l'échelle sur un batch de test (18/18 HandSegNet, 16/16 FootSegNet propres).

**Fallback LLM local fiabilisé.** Bug identifié : Aider+qwen3-coder échouait silencieusement sous Windows (crash encodage cp1252 sous Git Bash ; fichier vide malgré `exit 0` sous PowerShell, bug probabiliste du parseur d'édition d'Aider 0.86.2). Fix : `PYTHONIOENCODING=utf-8`/`PYTHONUTF8=1` + wrapper `agents/aider_fallback_run.py` qui vérifie systématiquement le résultat sur disque/git (jamais la sortie terminal) et relance en cas d'échec détecté. Validé 9/9 sur tâches répétées. PR mergée.

**Limitations connues documentées** (`LIMITATIONS_CONNUES.md`) : collapse en mirroring bilatéral sur mains jointes/symétriques (cas confirmés : 00137, 00167, 00147, 00071, 00072 — limite du prior génératif, pas de fix satisfaisant identifié) ; décrochage de doigts sur geste "mains écartées" (00259) ; fragilité du grounding VLM sur scènes multi-mains (item séparé, actionnable — résolu depuis par l'intégration YOLO).

## Chantiers en pause (diagnostiqués, pas abandonnés)

**Control-LoRA FootSegNet — mode collapse.** Cause racine confirmée : perte d'info du masque majoritairement architecturale (3 convolutions stride-2 de `controlnet_cond_embedding`), amplifiée par dilution dans les blocs copiés de l'UNet. **Trois pistes légères testées et écartées par mesure directe** : pondération de loss sous le masque (mask-loss-weight, testé ×10/×20/×50 — jamais de vraie différenciation, juste divergence vers du bruit incohérent qui imitait un signal), dilatation/flou du masque en pré-traitement (gain en sortie d'encodeur effacé en aval), loss contrastive (faux positif confirmé — le réseau apprenait à distinguer un bruit d'implémentation, pas le masque). PR #33 en draft, rapport `DIAGNOSTIC_MODE_COLLAPSE_20260728.md` complet. **Pistes de reprise future, dans l'ordre** : CtrLoRA (~1000 images / 1 GPU / 1h selon la littérature — bien moins coûteux que prévu, à tester en premier) ; lecture de ViscoNet (arXiv 2312.03154, aborde explicitement le mode collapse) ; refonte architecture type T2I-Adapter en dernier recours (coûteux, ~164-600k images / 4×V100 / 3 jours pour un entraînement classique).

**QC anatomique automatisé — bloqué sur licences, 3 tentatives.** HADM (aucune licence détectée, droits réservés par défaut) ; HandRefiner (code MIT mais dépend de MANO, licence non-commerciale à enregistrement personnel obligatoire) ; DiffDoctor (code MIT mais poids dérivés de NVlabs/SegFormer-B5, licence "research/evaluation only"). Rapport `QC_ANATOMIQUE_AUDIT_LICENCES_20260729.md`. **Piste de reprise** : "Detecting and Restoring Non-Standard Hands" (YOLOv8+MediaPipe, arXiv 2312.04236) — architecture plus simple, potentiellement moins bloquée, jamais testée.

**FootSegNet — 186 masques signalés fragmentés** (nouveau critère de fragmentation restauré depuis un stash oublié de longue date, calibré le 27/07, seuil `FRAGMENTATION_MINORITY_RATIO_MAX=26%`). Dossiers prêts : `_review_manual_fragmented/` (36, priorité haute — masques déjà utilisés pour le checkpoint publié val_IoU=0.9277), `_review_auto_fragmented/` (110), `_review_auto_other/` (40, recadrage bbox plutôt que fragment). Commandes exactes dans le README généré à côté de `prepare_quality_review_folders.py`. Estimation : 3-4h de travail manuel. **Jérémy prévoit de s'en occuper d'ici 2-3 jours, sans session Claude Code (pur travail d'annotation).**

**HandSegNet — 105 images legacy** (`route_manual_review.txt`, mécanisme différent des 186 ci-dessus, à vérifier s'il fait doublon avec le nouveau critère de fragmentation avant de s'y atteler).

## Chantier en cours — personnalisation LLM local (QLoRA)

Objectif double, établi cette nuit : (1) un LLM local capable de prendre le relais si le quota Claude Code s'épuise, (2) exploration technique/apprentissage.

**Décision de fond validée** : injection de contexte (RAG-like via `.aider.conf.yml` + `CLAUDE.md` + `DOCS/INDEX.md`) pour tout ce qui doit rester à jour (conventions du projet, expert ComfyUI/prompt engineering) — **fine-tuning réservé au changement de comportement/style**, pas à l'injection de connaissance qui bouge.

**Trois itérations QLoRA complètes sur modèle proxy (Qwen3-4B-Instruct-2507, le vrai `qwen3-coder-30B-A3B` dépasse la VRAM d'une seule carte 16 Go — 17,5 Go minimum documenté par Unsloth) :**
- **V1** : transfert de ton/registre confirmé net (2 preuves solides : compréhension du terme "segnet", diff ciblant les vraies fonctions du fichier) mais 3 défauts — tags `<tool_call>` vides systématiques, hallucinations factuelles, boucle de répétition.
- **V2** : cause des tags trouvée (bug `completion_only_loss` absent — la loss se calculait sur input+output, pas la réponse seule) et corrigée. Répétition corrigée (`repetition_penalty` ajouté). **Hallucinations factuelles non résolues, plutôt aggravées** (le modèle plus "propre" formellement devient plus confiant dans ses inventions).
- **V3** : dataset entièrement régénéré sur nouvel export Claude.ai (finalement identique à l'ancien, aucun gain), Source A à peine grossie (68 exemples, +1). **Même conclusion : problème non résolu**, cause probable confirmée = Source A trop petite pour du QA factuelle sur du code.

**Comparaison chiffrée avec la littérature (recherchée et confirmée)** : QA factuelle spécifique à un domaine nécessite 500-1000 exemples ; Source A (68) est très en dessous même du plancher "style simple" (100-200) ; Source B (1435, conversationnel) est dans la bonne fourchette générale (500-5000), ce qui explique pourquoi le transfert de *ton* a marché dès la V1 alors que le *factuel* échoue systématiquement.

**Plan en cours d'exécution (pas encore terminé au moment de ce document) :**
1. Construire **Source C** = rapports de session Claude Code complets (raisonnement + code en contexte, pas juste les diffs finaux), filtrés des artefacts d'outils.
2. **5 bases de code externes en téléchargement** (démarré, plusieurs heures) : CommitPack/CommitPackFT (4 To, la plus pertinente — mêmes paires tâche→diff que Source A mais à grande échelle, licence permissive), OpenCodeInstruct (NVIDIA, CC-BY-4.0, 5M exemples), The Stack v2/v3, CodeAlpaca, Evol-Instruct-Code. Téléchargées sur HDD externe 8 To (40 Mo/s, jamais entraîner en lisant depuis là — extraire un sous-ensemble filtré Python vers le SSD 2 To dédié avant tout entraînement).
3. **Entraînement en deux étapes prévu** : Stage 1 = compétence générale de code sur sous-ensemble CommitPack filtré (base solide) → Stage 2 = reprise du même adaptateur, continué sur Source A+B+C (personnalisation Ov3rLoRd), pas un nouvel adaptateur de zéro.
4. Évaluation sur les mêmes 8 prompts que V1/V2/V3 pour comparabilité directe, focus sur la fiabilité factuelle (seul point jamais résolu).

**Deux prompts de session préparés et en partie envoyés** : un pour construire Source C + préparer le script d'extraction CommitPack (peut tourner pendant les téléchargements), un second à envoyer une fois les téléchargements terminés pour l'entraînement en deux étapes.

**Idée non développée, notée pour plus tard** : API personnelle façon `web_fetch` pour les LLM locaux (délester le besoin de captures d'écran coûteuses via Claude in Chrome).

## Rapports de recherche produits cette session (dans `DOCS/MD/`)

1. **Regional Prompting** — maturité 2026, VLM+masques recommandé pour zones anatomiques, Attention Couple pour scènes multi-personnages, transparence (LayerDiffuse cassé sur Illustrious/NoobAI, TKG-DM recommandé).
2. **Pipeline lineart→couleur** — décomposition structure/couleur validée par la littérature, Kataragi line2color/flatline directement exploitables, AniDoc/LVCD pour cohérence temporelle de séquence.
3. **Prompt engineering robuste anti-hallucination SDXL/ComfyUI** (celui utilisé pour construire `docs/comfyui_prompt_expert_context.md`, injecté via `llm_router.py`) — NAG, ban tags TIPO/DanTagGen, conventions ControlNet start/end percent, vocabulaire Danbooru.
4. **Audit de maturité technique 2026** — QC anatomique (HADM/DiffDoctor, bloqués licence), lineart temporel (gap confirmé, pas de solution mûre), ColorLock, outils vidéo (MatAnyone, SeedVR2, RIFE, VACE, blender-mcp — tableau de faisabilité VRAM détaillé), DesignLock (SAM+DINO+matching bipartite, directement réutilisable avec le stack existant).

## Conventions établies cette session (dans `CLAUDE.md`)

- **Règle de gestion de contexte 90%/92%** pour toute session longue/autonome : à 90% conclure proprement, à 92% arrêt complet + commit + fichier de handoff.
- Même discipline étendue à la **VRAM** pendant les runs d'entraînement.
- `gpu_usage_log.csv` + `gpu_cost_estimate.py` : traçage du temps GPU cumulé avec équivalent-coût cloud (~24,88h / ~29,86$ au dernier point mesuré).
- `DOCS/INDEX.md` : index des documents de référence, à maintenir à jour.
- Toujours recharger un PNG généré dans ComfyUI pour retrouver le prompt exact utilisé (métadonnées `tEXt` natives) avant de diagnostiquer un défaut de génération à l'aveugle.

## Divers / non prioritaire

- **Blender MCP** installé côté add-on (officiel Blender Lab, `blender.org/lab`) et connecteur Anthropic — fonctionnel, jamais encore utilisé pour une vraie tâche.
- **Claude in Chrome** activé mais à utiliser avec parcimonie (coût des captures d'écran) — préférer une solution API texte quand possible.
- **Recherche de crédits cloud** (NVIDIA Inception en priorité, puis Nebius AI Lift, Microsoft for Startups) : fichiers `cloud_credits_checklist.md` et `candidature_dossier.md` préparés, candidatures pas encore envoyées.
- **Matériel** : réflexion en cours sur un second PC (AM4/B550, ~480-570€) pour héberger la RTX 2070 + RTX 5060 Ti Dual (celle remplacée par la Prime sur la machine principale) comme serveur Ollama/annexe dédié, relié en RJ45 direct à la machine principale. Pas encore engagé.
- **Contrainte active au moment de ce document** : quota hebdomadaire Claude très limité. Privilégier les tâches longues/autonomes à faible fréquence d'interaction.

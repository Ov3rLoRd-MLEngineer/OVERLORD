# Veille technique Ov3rLoRd — Nouveautés 2026 pour pipeline anime IA solo (ComfyUI + SDXL)

## TL;DR
- **Les grandes nouveautés récentes se concentrent sur la vidéo anime (Wan 2.2 Animate, AniSora V3.x) et sur l'estimation de pose robuste (SDPose, sept. 2025, MIT) qui règle enfin le domain gap pose anime — mais le socle image reste SDXL/Illustrious, aucun successeur consumer ne l'ayant détrôné.**
- **Deux des vides identifiés par le projet restent LARGEMENT OUVERTS** : il n'existe toujours pas de FootSegNet/HandSegNet anime research-grade (juste des modèles YOLO communautaires imparfaits sur Civitai), ni de tracker de pose de PIED per-orteil équivalent à MediaPipe Hands (le standard reste 6 points COCO grossiers).
- **Deux découvertes à fort impact pour Ov3rLoRd** : SDPose (pose anime robuste, MIT) et See-through (SIGGRAPH 2026, décomposition en 19-23 couches de parties du corps depuis une seule image, avec pipeline de données bootstrap Live2D) — cette dernière valide directement l'approche 3D→2D du projet.

## Key Findings

1. **Génération image** : SDXL/Illustrious demeure le socle. Illustrious XL v3.0/v3.5 (Onoma AI) et Pony V7 (AuraFlow, 7B) sont sortis mais restent controversés ; l'écosystème réel tourne sur les fine-tunes (NoobAI, WAI-Illustrious, Nova Anime, Chenkin Noob). Aucun successeur SDXL consumer clairement supérieur.
2. **Génération vidéo anime** : vraie explosion. Wan 2.2 (juillet 2025, Apache 2.0) + Wan 2.2 Animate, et AniSora V3.1/V3.2 (Bilibili, Apache 2.0) sont les développements majeurs, tournables en 16 GB via GGUF/FP8.
3. **ControlNet/segmentation** : pas de rupture. Anime face segment existe depuis longtemps. Segmentation hand/foot anime : vide research-grade toujours ouvert.
4. **Pose anime** : SDPose (arXiv:2509.24980, sept. 2025) est LA nouveauté vérifiable — priors de diffusion pour robustesse out-of-domain, y compris anime. Pose de pied per-orteil : vide non comblé.
5. **Données synthétiques 3D→2D** : plusieurs papiers pertinents et récents (LinkTo-Anime, AnimeRun, See-through) confirmant et outillant l'approche Blender du projet.
6. **Image-to-3D** : Hunyuan3D 2.5/3.0, TRELLIS 2 côté généralistes ; côté anime stylisé, See-through (2.5D) et DrawingSpinUp sont les avancées.
7. **Fine-tuning local & LLM** : Unsloth reste la référence single-GPU ; nouveaux modèles agentic Qwen3-Coder, GLM, DeepSeek V4, Devstral-2 tournables sur 16 GB en quantifié.

## Details

### Axe 1 — Nouveaux modèles image/vidéo anime

**Image (SDXL et successeurs) — évolution incrémentale, pas de rupture.**
Le socle du projet (SDXL/fabricatedXL) reste parfaitement valide en 2026. Les développements datés :
- **Illustrious XL v3.0** (Onoma AI) : selon la note de version officielle Onoma AI, « We proudly introduce Illustrious XL 3.0, marking a groundbreaking leap with our first stabilized model supporting up to 2048x2048 native generation resolution… The dataset for Illustrious XL 3.0 has been meticulously updated to include content through October 2024 ». Nouveaux tokens de contrôle couleur (contrast, brightness, saturation…). La variante v3.0-ε (epsilon-prediction) est conçue comme base de fine-tuning robuste. **v3.5 vpred** sortie mai 2025. Attention : ces versions haut de gamme sont partiellement derrière le système « Stardust » payant d'Onoma, ce qui a freiné leur adoption communautaire.
- **Pony Diffusion V7** (base v7.0) : bascule sur l'architecture **AuraFlow (~7B paramètres, ~10M images, Apache 2.0)** au lieu de SDXL. Dataset rééquilibré (25% anime, 25% réalisme, 20% cartoon occidental…). Limites reconnues par l'auteur : tags qualité (score_9) beaucoup plus faibles que V6, VAE dépassé (pas de VAE 16-canaux), visages qui se dégradent selon le style ; une V7.1 est annoncée. **Important pour Ov3rLoRd : AuraFlow n'est PAS SDXL — les LoRA et ControlNet SDXL existants sont incompatibles.**
- **Écosystème réel** : la communauté 2026 fonctionne en « division du travail » sur des fine-tunes SDXL/Illustrious : **WAI-illustrious** (daily driver), **NoobAI-XL** (v-pred, tags précis), **Nova Anime XL** (IL v19.0, mai 2026), **Chenkin Noob XL** (v0.5, dataset jusqu'à janvier 2026). Ces modèles restent en 8-12 GB VRAM, parfaitement adaptés aux RTX 5080/5060 Ti.

**Verdict image** : rien ne justifie d'abandonner SDXL. Les vrais gains sont dans les fine-tunes Illustrious récents, pas dans un changement d'architecture (qui casserait tout l'écosystème LoRA/ControlNet du projet).

**Vidéo anime — vraie rupture 2025-2026.**
- **Wan 2.2** (Alibaba, sorti 28 juillet 2025, Apache 2.0) : architecture MoE (experts high-noise/low-noise). Selon willitrunai.com, « Wan Video 2.2 14B is a 14B 3D DiT model with a 9.4B T5-XXL text encoder. At FP16 with the text encoder on GPU, the full pipeline requires approximately 54–65 GB VRAM — datacenter territory » ; mais **les quantifications GGUF/FP8 le font tourner sur des cartes 16 GB** (voire 8 GB avec offload — benchmarks communautaires rapportent ~8 GB de pic sur RTX 4070 12 GB à 480p). Support natif ComfyUI.
- **Wan 2.2 Animate** : framework unifié d'animation/remplacement de personnage piloté par vidéo de performance (squelette spatialement aligné + expression faciale). Support natif ComfyUI, **16 GB VRAM minimum en FP8** (24 GB recommandé). Pipeline documenté avec Qwen-Image-Edit 2509 + SeedVR2 pour l'upscale.
- **AniSora (Bilibili, projet Index-AniSora)** : le modèle vidéo spécifiquement anime. V3 licencié Apache 2.0 (août 2025), basé sur CogVideoX-5B et Wan2.1-14B + RLHF. Selon le dépôt officiel GitHub bilibili/Index-anisora : « 2025/09/23 🔥We have released V3.2 weights, which is trained on the stronger wan2.2 model and can reduce the number of inference steps to 8 » et « 2025/09/25 🔥The 12GB VRAM available version of V3.1 has been uploaded to ModelScope ». Modèle anisora-anymask (31 oct. 2025) supportant masques temporels/spatiaux. C'est l'outil de choix pour l'anime, excellant sur les actions exagérées « anti-physique ».

**Verdict vidéo** : Wan 2.2 Animate + AniSora V3.2 sont les deux ajouts majeurs à intégrer, tous deux tournables sur les GPU du projet en quantifié (AniSora V3.1 en version 12 GB dédiée).

### Axe 2 — ControlNet et segmentation

Pas de rupture ControlNet majeure pour l'anime. L'écosystème repose toujours sur `comfyui_controlnet_aux` (Fannovel16), qui inclut anime_face_segment (UNet + isnetis), densepose, dwpose. Le préprocesseur **AnimeFace_SemSegPreprocessor** fait de la segmentation sémantique de visage anime.

**Segmentation hand/foot anime — le vide du projet reste LARGEMENT OUVERT.** La recherche ciblée confirme qu'il n'existe **aucun FootSegNet/HandSegNet anime research-grade** avec dataset et benchmark publiés. Ce qui existe :
- **Foot/Shoe Segmentation - ADetailer** (Civitai, user Pitpe11, publié 1er avril 2026, https://civitai.com/models/2511165) : modèle YOLO11n, 2 classes (feet, shoes), ~1.2k images, 100 epochs, installé dans `models/ultralytics/segm`. **Auto-décrit par l'auteur comme un test précoce sous-performant** (« By the training metrics, this model should not perform well in theory, and I'll count this release as an early test »). Format pickle (précaution sécurité). Pas de license claire. Censé fonctionner sur réaliste ET anime.
- **Hand Detailer/Segmentation - ADetailer** (Civitai, Pitpe11, publié mai 2025, mis à jour août 2025, YOLOv9c, https://civitai.com/models/329458).
- Solutions génériques non-anime : SAM/SegmentAnythingUltra V2, MeshGraphormer HandRefiner.

**Conclusion** : les modèles FootSegNet/HandSegNet développés en propre par Ov3rLoRd conservent leur raison d'être. Le seul concurrent apparu (foot/shoe ADetailer) est un détecteur YOLO grossier, pas une segmentation pixel-précise research-grade.

Note importante : **See-through** (voir axe 5) produit une couche « Footwear » distincte parmi 19-23 couches, mais la traite comme couche RGBA inpaintée pour animation 2.5D/Live2D, PAS comme masque de segmentation pixel-précis destiné au ground truth ControlNet — et sous licence non-commerciale (CC BY-NC-SA 4.0). Le paper reconnaît d'ailleurs des artefacts sur la chaussure (« we do not stratify it by default »).

Précurseur académique : « Body Part Segmentation of Anime Characters » (Ou et al. 2024, *Computer Animation and Virtual Worlds*, DOI 10.1002/cav.2295), formulation graph-cut basée pose — mais pas d'outil hand/foot standalone.

### Axe 3 — Estimation de pose anime/illustration

**SDPose (arXiv:2509.24980, 29 sept. 2025, MIT) — LA nouveauté majeure et directement pertinente.** Développé par Shuang Liang, Jing He, Chuanmeizhi Wang, Lejun Liao, Guo Zhang, Yingcong Chen et Yuan Yuan (Rama Alpaca Technology, Boston College, HKUST-GZ). Le principe : exploiter les priors latents d'un U-Net Stable Diffusion pour la robustesse out-of-domain, au lieu d'entraîner un backbone from scratch comme DWPose (qui, entraîné sur COCO-WholeBody humains réels, généralise mal sur l'anime).
- Résultats SOTA sur **HumanArt** et un nouveau benchmark **COCO-OOD** (extension style-transféré de COCO). Le paper montre explicitement une pose plus précise « across diverse animation styles and humanoid robots » vs baselines. Verbatim : « With only 1/5 of Sapiens' fine-tuning cost and a smaller backbone, SDPose matches its accuracy on COCO and achieves state-of-the-art results on COCO-OOD and HumanArt ».
- Supporte **body (17 keypoints)** ET **wholebody (133 keypoints incluant 6 keypoints de pied)**. Modèles sur HuggingFace : `teemosliang/SDPose-Wholebody` et `SDPose-Body`, démos Gradio/HF Spaces. Méthode top-down (nécessite un détecteur de personne en amont).

**C'est la réponse directe au problème DWPose du projet.** À tester en priorité comme préprocesseur de pose pour conditionnement anime.

Alternatives historiques confirmées (pas nouvelles) : Chen et al. WACV 2022 « Transfer Learning for Pose Estimation of Illustrated Characters » (AnimeDrawingsDataset), et l'approche classique Khungurn de données synthétiques 3D→2D.

**Tracking de pose de PIED per-orteil — vide NON comblé.** La recherche confirme qu'aucun tracker de pied/orteil dense (équivalent MediaPipe Hands à 21 points pour les mains, mais pour les orteils) n'existe en 2026, ni pour le réel ni pour l'anime. Le standard reste :
- MediaPipe BlazePose/Holistic : landmarks de pied grossiers (talon + gros orteil uniquement).
- CMU/OpenPose Human Foot Keypoint Dataset (2018) : 6 keypoints de pied seulement.
- SDPose : hérite du schéma COCO 6 points (pas d'articulation par orteil).
Le vide identifié par le projet est donc réel et confirmé — opportunité de R&D propre.

### Axe 4 — Données synthétiques 3D→2D (domain gap cel-shading)

Axe le mieux servi par la recherche récente, validant directement l'approche Blender/Object Index pass du projet :
- **LinkTo-Anime** (arXiv:2506.02733, 2025, Xiaoyi Feng et al., Macau University of Science and Technology & Link-To Shenzhen) : premier dataset de mouvement de personnage cel-anime généré par **rendu 3D**, avec optical flow avant/arrière, masques d'occlusion et squelette Mixamo. Verbatim : « The dataset comprises 395 video sequences, totally 24,230 training frames, 720 validation frames, and 4,320 test frames ».
- **AnimeRun** (arXiv:2211.05709) : correspondance visuelle 2D depuis films 3D open-source. **Détails de rendu directement applicables au projet** : rendu sous lighting « FLAT » du moteur Workbench de Blender, particules désactivées, depth-of-field et anti-aliasing désactivés pour des frontières nettes — exactement la recette pour réduire le domain gap 3D→2D flat.
- **See-through** (SIGGRAPH 2026, arXiv:2602.03749) : construit un « data engine » qui bootstrap des labels pixel-perfect (19 parties du corps + régions occluses + drawing order) depuis des modèles **Live2D** commerciaux, via GradCAM + SAM. Approche de génération de ground truth très instructive.
- Contexte général : « What Makes Synthetic Data Effective in Image Segmentation » (arXiv:2605.19289) analyse les facteurs (complexité compositionnelle + fidélité d'instance locale) qui déterminent l'efficacité des données synthétiques pour la segmentation — utile pour calibrer le pipeline Blender.

**Verdict** : l'intuition du projet (rendu 3D cel-shadé calibré pour ground truth gratuit) est activement validée par la littérature 2025-2026. La recette Blender de AnimeRun (FLAT/Workbench, AA off, DoF off, particules off) est à adopter directement.

### Axe 5 — Image-to-3D et reconstruction

**Généralistes (photoréalistes, moins adaptés au stylisé plat)** : Hunyuan3D 2.5 (avril 2025, non open-source, via Studio) et Hunyuan3D 3.0/3.5 (jusqu'à textures 8K PBR), TRELLIS 2 (Microsoft). Hunyuan3D-2 open-source demande ~11,5 GB VRAM pour la forme, ~24,5 GB pour forme+texture.

**Spécifique anime/stylisé** — là où sont les vraies avancées :
- **See-through** (SIGGRAPH 2026) : transforme une illustration statique en modèle **2.5D** manipulable, décomposé en jusqu'à 23 couches inpaintées (cheveux, visage, yeux, vêtements, accessoires). Module de cohérence des parties du corps basé diffusion + inférence de pseudo-profondeur. Optimisations mémoire pour low-VRAM (group offload, quantification NF4). Scripts d'entraînement et pipeline de données publiés (github.com/shitagaki-lab/see-through). Licence CC BY-NC-SA 4.0 (non-commerciale).
- **DrawingSpinUp** (arXiv:2409.08615) : animation 3D depuis un unique dessin de personnage.
- Antérieurs (pas nouveaux) : PAniC-3D (CVPR 2023, têtes anime depuis portrait), NOVA-3D (ACM MM Asia 2024), CharacterGen.

**Verdict** : pour un sujet anime stylisé, See-through (2.5D layer decomposition) est l'avancée 2026 la plus pertinente ; les reconstructions 3D full-mesh restent orientées photoréalisme/objets.

### Axe 6 — Fine-tuning local et LLM agentic

**Fine-tuning LoRA local** : l'écosystème est mature et stable. **Unsloth** reste la référence single-GPU ; sa doc officielle annonce « Train and RL 500+ models ~2x faster with ~70% less VRAM (no accuracy loss) », et pour le MoE Qwen3-30B-A3B elle indique un fine-tuning « with just 17.5 GB VRAM » — soit légèrement au-dessus des 16 GB de la 5080 (nécessitera offload ou un modèle plus petit). Unsloth est désormais intégré à Red Hat AI Training Hub (avril 2026). Alternatives : Axolotl et Torchtune (multi-GPU), LLaMA-Factory (UI web zéro-code). Standards 2026 : QLoRA 4-bit par défaut sur consumer, `target_modules="all-linear"`, r=α=16, DoRA (`use_dora=True`) pour la qualité. Un 7B-8B se fine-tune en 8-12 GB.

**Attention config double GPU** : Unsloth est single-GPU. Pour exploiter les deux cartes (5080 + 5060 Ti), il faut Axolotl ou Torchtune (data/model parallelism).

**LLM open-weight agentic pour 16 GB** :
- **Qwen3-Coder** (30B-A3B, MoE, Apache 2.0) : le Q4_K_M fait ~17,3 GB — cible directe 16 GB avec offload léger. Successeur Qwen3-Coder-Next (fév. 2026, MoE, ~58,7% SWE-bench Verified) mais lourd (130 GB disque).
- **Qwen 3.6 / Qwen3.6-35B-A3B** (MoE) : tourne sur 16 GB avec offload RAM (UD-Q3_K_M clean, UD-Q4_K_M avec KV-cache offload). Sur RTX 5080 16 GB : ~6 tok/s en quantification agressive selon insiderllm.com — utilisable, pas rapide.
- **Devstral-2 22B** : spécialiste agentic, tourne sur 16 GB (RTX 4060 Ti 16GB cité).
- **gpt-oss-20b** : recommandé comme pick sûr « fit-first » 16 GB.
- Frontière open (server-class, PAS local 16 GB) : DeepSeek V4-Flash (284B/13B actif, MIT, avril 2026), GLM-5.x, Kimi K2.x, MiniMax M2.5.

**Verdict** : Qwen3-Coder 30B-A3B (MoE, 3B actifs = rapide) reste le meilleur compromis codage agentic local sur 16 GB ; Devstral-2 22B en spécialiste. Garder une « API escape hatch » pour les tâches multi-fichiers lourdes (l'open local plafonne ~70% SWE-bench vs ~80% frontière).

### Axe 7 — Outils ComfyUI récents

- **Wan 2.2 Animate** natif ComfyUI (workflow officiel comfy.org + comfyui-wiki), avec node WanAnimateToVideo, DWPose Estimator pour prétraiter la vidéo de contrôle, Points Editor (KJNodes), Sam2Segmentation pour le masque de sujet. Node expérimental **ComfyUI-WanAnimate-Enhancer** (wallen0322) pour contrôle multi-dimensionnel (motion strength).
- **Comfyui-Anima-IPadapter** (circlestone-labs / Wenaka2004, mis à jour mai 2026) : IP-Adapter pour le modèle DiT Anima, cohérence de personnage via cross-attention découplée, embeddings Qwen3-VL, tourne dès 8 GB (option temps-réel +4 GB pour Qwen3-VL-Embedding-2B). Apache 2.0. **C'est l'ajout notable au-delà d'IPAdapter classique.**
- **Cohérence de personnage** : le consensus 2026 reste LoRA (fiabilité long terme) + IP-Adapter FaceID (rapidité), combinés + ControlNet pour la structure. Pas de solution magique nouvelle ; l'ingénierie « Character DNA » + LoRA dédié demeure la voie robuste.
- **Physique cheveux/tissu** : côté génératif, Wan 2.2 gère la simulation de mouvement (hair sway, clothing ripple) via prompts de mouvement et workflows de loop (First-Last Frame). **Il n'existe pas de node ComfyUI de simulation physique déterministe** ; la physique reste implicite dans les modèles vidéo. Pour une physique contrôlée, l'approche hybride (Blender/Maya + outils type jiggle physics — ex. Astral God Physics pour Maya, hors ComfyUI, puis rendu) reste nécessaire.

## Recommendations

**Étape 1 — Intégrations immédiates (gains sûrs, faible risque)** :
1. **Adopter SDPose** comme préprocesseur de pose anime (remplace/complète DWPose). MIT, 133 keypoints, robuste OOD — réponse directe au problème du projet. Benchmark de bascule : si SDPose bat DWPose sur vos poses anime extrêmes de test, l'adopter comme défaut.
2. **Ajouter Wan 2.2 Animate + AniSora V3.2** au pipeline vidéo (GGUF/FP8 sur la 5080 16 GB ; version 12 GB d'AniSora V3.1 disponible). AniSora pour l'anime pur, Wan Animate pour le motion transfer piloté par performance.
3. **Appliquer la recette de rendu AnimeRun** dans Blender (lighting FLAT/Workbench, AA off, DoF off, particules off) pour réduire le domain gap 3D→2D dès maintenant.

**Étape 2 — Explorations à moyen terme** :
4. **Étudier le data engine de See-through** (bootstrap de labels via SAM + propagation) comme modèle méthodologique pour générer du ground truth de segmentation — même si sa licence non-commerciale interdit un usage produit direct, la méthode est réutilisable.
5. **Continuer FootSegNet/HandSegNet en propre** : le vide research-grade n'est PAS comblé. Le seul concurrent (foot/shoe ADetailer YOLO11n) est un test précoce grossier. Envisager de publier vos modèles — il y a un vrai vide communautaire.
6. **Migrer le fine-tuning double-GPU vers Axolotl/Torchtune** si vous voulez exploiter la 5080 + 5060 Ti simultanément (Unsloth est single-GPU ; noter que le MoE 30B-A3B demande ~17,5 GB, au-delà de 16 GB seul).

**Étape 3 — Surveillance (ne rien précipiter)** :
7. **Ne PAS migrer hors SDXL** vers Pony V7/AuraFlow tant que l'écosystème ControlNet/LoRA AuraFlow n'est pas mûr (VAE 16-ch manquant, V7.1 en attente). Seuil de bascule : disponibilité de ControlNet anime natifs AuraFlow + parité LoRA.
8. **LLM codage** : garder Qwen3-Coder 30B-A3B local + escape hatch API. Réévaluer si un modèle 16 GB dépasse 65% SWE-bench Verified en local.
9. **Pose de pied per-orteil** : vide confirmé — opportunité de R&D propre (dataset synthétique Blender avec keypoints d'orteils exportés depuis le rig 3D, exactement la force du pipeline du projet).

## Caveats

- **Fiabilité des sources** : les VRAM/benchmarks proviennent souvent de blogs (thundercompute, willitrunai, insiderllm, apatero) plutôt que de sources primaires ; à vérifier sur votre matériel. Les chiffres SWE-bench et tok/s de LLM sont particulièrement volatils et parfois issus de rapports communautaires non reproductibles.
- **SDPose** : SOTA revendiqué sur benchmarks OOD, mais pas encore massivement adopté en production ComfyUI ; vérifier l'existence d'un node ComfyUI ou prévoir une intégration custom. Testé sur COCO-OOD (style-transféré), pas exclusivement anime pur.
- **See-through** : « conditionally accepted » à SIGGRAPH 2026 (preprint non encore camera-ready), licence non-commerciale — pas utilisable tel quel en produit commercial.
- **AniSora V2** nécessitait une demande par formulaire email ; les poids V3/V3.2 sont Apache 2.0 sur ModelScope/HuggingFace — vérifier les conditions exactes de la variante ciblée.
- **Modèles Civitai (foot/shoe, hand ADetailer)** : format pickle (risque sécurité), pas de benchmark formel, licences floues.
- **Illustrious v3.x** : partiellement derrière le paywall « Stardust » d'Onoma, ce qui limite l'accès aux poids complets.
- **Unsloth 30B-A3B (17,5 GB)** dépasse légèrement les 16 GB de la RTX 5080 seule ; prévoir offload CPU/RAM ou un modèle plus petit pour le fine-tuning local.
- Ne pas surinterpréter : l'axe image (SDXL) et l'axe ControlNet n'ont PAS connu de rupture — les « nouveautés » y sont des itérations, pas des changements de paradigme.
# Pipeline de production anime IA local en 2026 : état de l'art et feuille de route Ov3rLoRd

## TL;DR
- **AniSora V3.2 est le meilleur point de départ** : c'est un fine-tune anime de Wan 2.2 I2V 14B (modèles High + Low noise), avec inférence réduite à 8 étapes, qui tourne sur 16 Go de VRAM en GGUF Q4_K_M/Q5_K_M et se branche dans n'importe quel workflow Wan 2.2 I2V ComfyUI via l'Unet Loader (GGUF) — aucune node spéciale requise.
- **Le gap principal d'Ov3rLoRd n'est pas la génération d'images mais la cohérence temporelle et l'assemblage** : le stack actuel (SDXL fabricatedXL + AnimateDiff) est daté pour de la vidéo anime cohérente ; la voie rapide vers une démo convaincante de 30 s passe par Wan 2.2 / AniSora V3.2 en I2V, guidage Blender→depth/pose via Wan 2.2 Fun Control, LoRA de personnage + IPAdapter pour la cohérence, RIFE pour la fluidité et SeedVR2 pour l'upscale.
- **Une démo de 30 s est réaliste sur RTX 5080 + 5060 Ti en quelques jours** : les productions indie documentées en 2026 livrent des courts finis en 2–5 jours ; le vrai travail est le découpage en ~7–10 clips de 3–5 s, la cohérence de personnage et le montage, pas la puissance GPU.

## Key Findings

1. **AniSora V3.2 (Bilibili/Index-AniSora)** est un fine-tune de Wan 2.2 I2V 14B publié le 23/09/2025, avec modèles High/Low noise séparés et inférence réduite à 8 étapes. GGUF disponibles chez QuantStack (Q3 à Q8 ; Q4_K_M ≈ 10,1 Go, Q5_K_M ≈ 11,3 Go, Q8_0 ≈ 15,9 Go par composant) ; FP8 scaled chez Kijai. Il se charge dans les workflows Wan 2.2 I2V standard.
2. **Wan 2.2 5B TI2V** est plus léger (720p sur ~8–12 Go) mais qualité de mouvement inférieure au 14B ; pour l'anime, AniSora V3.2 (14B) donne de bien meilleurs résultats stylistiques que le 5B générique.
3. **Le guidage pose/depth natif d'AniSora n'est PAS exposé dans ComfyUI** : pour du contrôle OpenPose/depth/lineart, il faut passer par Wan 2.2 Fun Control ou VACE.
4. **La chaîne Blender → depth/pose → ComfyUI est mature** via le rig toyxyz (OpenPose+Depth+Canny), le Z-buffer/Mist de Blender, et Wan 2.2 Fun Control.
5. **La cohérence de personnage** se règle avec LoRA de personnage (entraîné) + IPAdapter en appoint ; le LoRA est la méthode fiable, l'IPAdapter suffit pour les rôles secondaires.
6. **RIFE (rife47/rife49)** double/quadruple les FPS de manière fiable et rapide ; combiné à SeedVR2 pour l'upscale, c'est le duo de post-production standard.

## Details

### 1. AniSora V3.2 — architecture, VRAM, workflows, limites

**Architecture et provenance.** AniSora V3.2 est un fine-tune anime de **Wan 2.2 I2V 14B**, publié le 23/09/2025. Le changelog du README GitHub officiel indique : *« We have released V3.2 weights, which is trained on the stronger wan2.2 model and can reduce the number of inference steps to 8. Just like version 3.1, it has added arbitrary-frame inference and character 3D video generation. »* Comme Wan 2.2, il utilise une architecture à deux experts (High noise + Low noise). Les versions antérieures reposaient sur CogVideoX-5B (V1) puis Wan 2.1 14B (V2), avec le premier framework RLHF pour la génération vidéo anime (AnimeReward + GAPO), travail accepté à IJCAI 2025.

- **GitHub** : https://github.com/bilibili/Index-anisora
- **HuggingFace officiel** : https://huggingface.co/IndexTeam/Index-anisora (V3.2 dans /tree/main/V3.2)
- **GGUF communautaire** : https://huggingface.co/QuantStack/Index-Anisora-V3.2-GGUF
- **FP8 scaled (Kijai)** : https://huggingface.co/Kijai/WanVideo_comfy_fp8_scaled/tree/main/I2V (sous-dossier AniSora/)

**Différences avec Wan 2.2 standard.** Structurellement identique à Wan 2.2 I2V 14B (mêmes tenseurs, d'où compatibilité directe avec les workflows I2V), mais entraîné sur un large corpus anime, ce qui améliore nettement la qualité stylistique, la cohérence de ligne (line integrity) et le rendu de mouvement anime. Un utilisateur HF résume : *« As far as I understand it, its just normal wan2.2 thats trained on anime no? »* — techniquement exact. La différence pratique est la fidélité au style 2D et la fluidité de mouvement anime, plus l'inférence 8 étapes distillée.

**Performance sur 16 Go de VRAM.** Un composant Q8_0 seul (15,9 Go) remplit quasiment une carte 16 Go ; comme V3.2 charge un modèle High ET un Low, **Q4_K_M (10,1 Go/composant) ou Q5_K_M (11,3 Go) sont les quants réalistes en 16 Go**, en laissant de la place pour l'encodeur texte UMT5-XXL, le VAE et les latents. Aucun benchmark de première main publiant les secondes/clip exactes sur RTX 5060 Ti 16 Go n'a été trouvé — ce point reste non vérifié. Points de repère indirects : le workflow Patreon « The Local Lab AI » (« Create Anime Series Using Anisora WAN Model in ComfyUI ») revendique *« Generate crisp AI-animated 2–3 second 480p videos in roughly 4 minutes on an RTX 4050 6GB VRAM GPU »* ; les repères Wan 2.2 14B FP8 génériques (WillItRunAI) donnent *« FP8 + T5 offload at 720p generates in 2–4 minutes per clip »* sur RTX 4080 Super 16 Go — l'inférence 8 étapes d'AniSora devrait descendre bien en dessous, mais c'est une extrapolation.

**Workflows ComfyUI et GGUF.** Le GGUF ne nécessite aucune node spéciale : *« The Anisora is Image-To-Video supported, so you can use it as Wan 2.2 i2v models in any Image-To-Video workflows, and use Unet Loader (GGUF) node to load the model files. »* On utilise donc l'Unet Loader (GGUF) de city96 (https://github.com/city96/ComfyUI-GGUF), placé dans les workflows Wan 2.2 I2V standard. Il existe aussi une node dédiée ComfyUI-AniSora, mais elle documente surtout du I2V simple. Le fine-tune LoRA d'AniSora extrait par Kijai n'a fonctionné que sur le modèle HIGH (il faut y ajouter le Lightning/lightx2v LoRA à la place du LOW).

**Résultats documentés et limites.** AniSora V3.2 ajoute l'inférence à trame arbitraire, la génération 3D de personnage (rotation 360°) et le style transfer. Un guide Apatero revendique 94 % de cohérence multi-vues sur les rotations 360° (à traiter comme du marketing non vérifié, testé sur cloud 24–32 Go). Limites connues : sur 16 Go il faut de l'offloading entre passes High/Low ; les débutants rapportent des résultats médiocres sans réglages fins ; le guidage pose/depth natif n'est pas dispo dans ComfyUI.

### 2. Wan 2.2 5B TI2V pour l'anime

Le **Wan 2.2 TI2V-5B** (texte-et-image-vers-vidéo, FP16) génère jusqu'à 832×480, 81 frames à 16 fps ; la carte modèle officielle Wan-AI/Wan2.2-TI2V-5B précise : *« Without specific optimization, TI2V-5B can generate a 5-second 720P video in under 9 minutes on a single consumer-grade GPU »* (grâce à une compression VAE 16×16×4). Sur RTX 4090 24 Go, WillItRunAI mesure un clip de 25 frames en 768×512 en *« approximately ~4m 23s at FP16 with 30 inference steps »* (30 étapes, pas 50). En GGUF/FP8, le 5B tourne sur 8–12 Go. **Sur une RTX 5060 Ti 16 Go**, le 5B rentre confortablement et permet des itérations rapides, mais sa **qualité de mouvement est inférieure au 14B** ; le fichier ti2v_5b est décrit comme « lower motion quality than the dedicated 14B I2V checkpoint ». Les clips restent limités à ~5 s / ≤120 frames.

**Verdict** : le 5B est excellent pour du prototypage rapide et le test de storyboard, mais pour la démo finale, AniSora V3.2 (14B) en GGUF Q4/Q5 donnera un rendu anime nettement supérieur sur la même carte 16 Go. ControlNet/OpenPose ne se branche pas nativement sur le TI2V ; il faut Wan 2.2 Fun Control (voir §3).

### 3. Pipeline Blender → OpenPose → ComfyUI

**Rig toyxyz.** L'outil de référence est *« Character bones that look like Openpose for blender »* (toyxyz, Gumroad, version ~101 en 2026, gratuit). Il fournit un rig exportant simultanément **OpenPose, Depth, Canny, Landmark, MediaPipeFace, doigts et CameraPose**, avec un addon « Openpose attach » pour attacher le rig OpenPose à un rig cible, un « Back_Blocker » pour les rotations de tête, et un « Auto bright » réglant la luminosité des os selon la distance caméra. Un addon compagnon convertit le mouvement caméra Blender en CameraCtrl.

**Depth maps depuis le Z-buffer Blender.** Deux voies : (a) le passe **Z-Depth vs Mist** de Blender (le Mist donne un dégradé normalisé 0–1 plus contrôlable que le Z brut) ; (b) le rig toyxyz qui sort déjà une depth « box » (LooseControlDepth). Des addons comme Blend Craft ou NodeFlow automatisent l'activation des passes. On rend une séquence d'images depth/pose, puis on l'injecte dans ComfyUI.

**Injection dans ComfyUI.** Le workflow « Blender to ComfyUI AI Renderer 2.0 » (RunComfy) formalise cette chaîne : piste Preprocess (depth/edges/pose depuis le rendu Blender) → génération vidéo Wan VACE. On utilise Depth Anything V2 ou les passes Blender directes, puis **Wan 2.2 Fun Control** : ses conditions multimodales couvrent *« Canny (line drawing), Depth, OpenPose (human pose), MLSD »* + contrôle de trajectoire, sur base Wan 2.2. Un workflow type charge une image source + une vidéo de contrôle, un préprocesseur DW Pose/OpenPose, les deux modèles Fun Control High/Low + un LoRA lightx2v (6 étapes, 3+3), scheduler DPM++ SDE. Pour un pipeline anime local, la meilleure pratique 2026 est : **Blender (rig toyxyz) → séquences pose+depth → Wan 2.2 Fun Control (+ LoRA style anime) → RIFE → SeedVR2**.

### 4. Cohérence temporelle et anti-flickering

**État de l'art.** Le flicker anime local se combat sur plusieurs fronts :
- **Éviter les causes** : SageAttention introduit un flicker temporel documenté (basculer sur sdpa le supprime) ; CFG trop élevé, seed changeant et motion strength trop forte génèrent du drift (verrouiller la seed, baisser le CFG de 8–9 à ~6, réduire denoise/motion de 10–20 %).
- **Nodes de lissage ComfyUI** : Pixel Deflicker (SuperBeasts.AI), FlowDenoise (débruitage temporel compensé en mouvement par flux optique), et les passes de « temporal consistency » légères.
- **Modèles conçus pour la stabilité** : Wan 2.2 améliore la cohérence temporelle vs 2.1 ; des workflows comme Stable Video Infinity 2.0 (Wan 2.2 I2V A14B + LoRA) font du overlap-blending entre passes pour éliminer les cassures.
- **Post-traitement** : Topaz Video AI (Proteus v5, anti_flicker high + face recovery) « détruit » le flicker facial selon un comparatif, mais SeedVR2 (open source, gratuit) est l'alternative locale recommandée.

**Alternatives à AnimateDiff pour SDXL.** C'est le point central : **AnimateDiff/SD1.5-SDXL est daté** pour la vidéo cohérente. Les guides 2026 le disent explicitement : *« Newer options like Wan2.1 skip AnimateDiff entirely and generate cleaner video »*. Pour du matériel 16–24 Go, les solutions qui **fonctionnent réellement** sont Wan 2.2 (5B ou 14B GGUF/FP8), AniSora V3.2, et Wan 2.2 Fun Control/VACE — pas AnimateDiff sur SDXL. AnimateDiff reste utilisable pour des « illustrations animées » stylisées courtes mais ne tient pas la cohérence sur du plan long.

### 5. Pipeline manga → anime

**Approches documentées.** Deux familles :
- **Storyboard assisté** : convertir des planches manga en storyboard structuré pour la vidéo (ex. AutoWeeb décrit script→storyboard→image-to-video ; une planche de dialogue de 8 cases devient 4–6 plans, une séquence d'action de 6 cases s'étend à 12–20 plans). Ces outils sont surtout SaaS.
- **Open source / ComfyUI** : la voie technique consiste à extraire lineart (ControlNet lineart preprocessor) et poses depuis les cases, puis animer via ControlNet → AnimateDiff (ancien) ou, mieux en 2026, via Wan Fun Control (lineart/pose). Un projet communautaire GitHub (issue Comfy-Org #14896, « Light in the Ruins », court anime de 25 s) documente une chaîne complète Script → Storyboard → Image Gen (ComfyUI) → Animation → Voiceover → Compositing. Des dépôts « ai-storyboard » (AID) fournissent des pipelines full-open-source de « manhua/manga → dynamic comic → video ».

**Réalité** : aucun studio indépendant majeur n'a publié un pipeline « chapitre manga → anime cohérent » entièrement automatisé et reproductible ; l'état de l'art est un assemblage manuel plan-par-plan où le manga sert de storyboard/référence de composition, avec extraction pose/lineart par case.

### 6. IPAdapter + WAN 2.2 / AniSora — cohérence de personnage

**Hiérarchie des méthodes** (du plus fiable au plus léger) :
1. **LoRA de personnage** entraîné (Wan 2.2 I2V ou T2V) : méthode fiable pour un personnage récurrent. Un LoRA T2V fonctionne souvent bien en I2V (il enseigne « qui » est le personnage). Attention au biais réaliste de Wan 2.2 : monter la force à 1.2, ajouter « ((realistic)) » en négatif. Le dataset doit enseigner l'identité sous mouvement, pas une pose figée. Entraînement : 1–4 h sur matériel capable.
2. **IPAdapter** : bon pour les rôles secondaires (un-deux plans) et l'ajustement à partir d'une seule image. Un praticien conclut : *« IPAdapter is pretty good. Not good enough to turn an image into different views for training a Lora. Might be good enough for bit-actors. »*
3. **Combiné** LoRA (personnages principaux) + IPAdapter (secondaires) + reference image en premier frame I2V.

Des workflows « Wan 2.2 Graybox to Rendered Sequence » (Playbook3D) atteignent une cohérence spatiale/temporelle + cohérence relative de personnage sans LoRA, en s'appuyant sur Flux Kontext depth LoRA + Wan 2.2 Fun Control depuis des séquences Blender graybox. Limite : sur Fun Control, quand le personnage tourne, vêtements/couleurs peuvent dériver.

### 7. RIFE et interpolation de frames

**État de l'art 2026.** RIFE (Real-Time Intermediate Flow Estimation) reste la référence, versions **rife47 et rife49 recommandées**. Intégration ComfyUI via ComfyUI-Frame-Interpolation (Fannovel16) qui embarque aussi **GMFSS Fortuna (spécialisé anime)**, FILM (grands mouvements), IFRNet, M2M, AMT, STMFNet, FLAVR. Une implémentation TensorRT (yuvraj108c) offre une interpolation ultra-rapide (testée juin 2026, ComfyUI v0.23). Practical-RIFE note que les versions 4.24+ conviennent bien au post-traitement des vidéos issues de modèles de diffusion.

**Gain réel.** Sur des clips anime IA générés à 16 fps, RIFE 2×–4× produit un 32–64 fps fluide sans altérer le timing, avec interpolation « face-safe » et edge-aware. C'est un gain quasi gratuit en fluidité perçue et la dernière étape standard avant l'export. GMFSS Fortuna est préférable à RIFE pur pour les mouvements très stylisés anime.

### 8. Outils complémentaires

- **ToonCrafter** (Jinbo Xing et al. ; The Chinese University of Hong Kong, City University of Hong Kong, Tencent AI Lab et Monash University ; ACM TOG / SIGGRAPH Asia 2024 ; arXiv:2405.17933) : interpolation générative entre **deux keyframes cartoon** (dérive de DynamiCrafter), *« can support generating videos of up to 16 frames with a resolution of 512x320 »* (~2 s), avec guidage sketch optionnel et colorisation par référence. Intégré via ComfyUI-DynamiCrafterWrapper / ComfyUI-ToonCrafter. Maturité : stable mais résolution/durée limitées ; la communauté a abaissé la consommation à *« ~10GB »* de VRAM. Utile pour combler des in-betweens entre poses clés dessinées.
- **MatAnyone** (NTU S-Lab, CVPR 2025 ; MatAnyone 2 CVPR 2026) : matting vidéo stable par propagation mémoire à partir d'**un seul masque initial**, flicker-free, edge refinement (cheveux). Node ComfyUI-MatAnyone (FuouM) avec MatAnyone2Video (v2), auto-masque via BiRefNet/RemBG. Gestion VRAM : `max_internal_size` (360/480) et `use_long_term` pour limiter la mémoire. Idéal pour isoler un personnage et compositer un décor séparé — clé pour la cohérence de fond.
- **SeedVR2** (ByteDance Seed ; Jianyi Wang et al. ; arXiv:2506.05301, soumis le 5 juin 2025, v2 révisée le 28 janvier 2026 ; Apache 2.0) : *« the first one-step diffusion model towards video restoration »*, décrit comme *« over 4× faster than existing diffusion-based [SeedVR] »*. Natif ComfyUI (PR #14424), variantes 3B/7B en FP16/FP8/INT8/GGUF. Sur 16 Go : block swap (0 blocs = 16 Go+, 12 blocs = 14–16 Go, 24 = 10–12 Go, 36 = 6–8 Go), VAE tiling, tile 2048px. Le 7B Q4 GGUF + 36 block swaps tourne sur 8 Go. Conserve la cohérence temporelle inter-frames, contrairement à l'upscale image-par-image. Maturité : production-ready, alternative locale gratuite à Topaz.

### 9. Pratiques des studios indépendants

Les productions indie 2026 documentées livrent des **courts finis (pas des tests) en 2–5 jours** selon la taille d'équipe. Exemples : un film de marque de 2 min produit en 3 jours vs ~2 mois en traditionnel (≈20× plus rapide) ; une équipe de 2 personnes produisant un épisode animé de 3 min sans pré-production. Le pipeline standard formalisé : script → storyboard → génération d'images → animation → voix → compositing (chaîne en 7 étapes). Pour un créateur solo, la recommandation communautaire est **ComfyUI + SD/Wan + API vidéo** ; le coût matériel est le seul coût si tout est local. La cohérence de personnage et le tool-switching restent les plus gros points de friction.

### 10. Positionnement Ov3rLoRd — gaps et solutions rapides

**Stack actuel** : fabricatedXL_v70 (SDXL), RTX 5080 + RTX 5060 Ti 16 Go, ComfyUI, FootSegNet/HandSegNet publiés, Blender MCP, AnimateDiff installé. **Cible** : 30 s de vidéo anime cohérente, bout en bout, pour démontrer une compétence technique (candidature Mistral / studio).

**Gaps identifiés :**
1. **Moteur vidéo daté** : AnimateDiff sur SDXL ne tient pas la cohérence temporelle sur des plans longs. C'est le gap n°1.
2. **Pas de modèle vidéo anime moderne** installé (AniSora V3.2 / Wan 2.2).
3. **Pas de chaîne de contrôle Blender→ComfyUI opérationnelle** (le rig toyxyz et Wan Fun Control ne sont pas mentionnés).
4. **Pas de solution de cohérence de personnage** (LoRA de personnage / IPAdapter).
5. **Pas de post-production** (RIFE, SeedVR2, MatAnyone).
6. **SDXL comme générateur de keyframes** est correct, mais il faut le relier à un moteur I2V.

**Solutions les plus rapides (ordre de priorité) :**
- **Semaine 1** : installer AniSora V3.2 GGUF (Q4_K_M ou Q5_K_M, High+Low) via ComfyUI-GGUF sur la 5080, en I2V depuis des keyframes SDXL fabricatedXL. Valider un clip anime de 3–5 s cohérent. Ajouter RIFE (rife49) + SeedVR2 (block swap) pour la sortie.
- **Semaine 2** : entraîner un LoRA de personnage Wan 2.2 (dataset d'identité sous mouvement) pour tenir la cohérence entre clips ; IPAdapter en appoint pour les rôles secondaires.
- **Semaine 3** : brancher Blender (rig toyxyz → pose+depth) sur Wan 2.2 Fun Control pour les plans nécessitant un contrôle de mouvement précis (là où FootSegNet/HandSegNet peuvent servir de masques/contrôles complémentaires). MatAnyone pour séparer personnage/décor.
- **Assemblage** : découper la démo de 30 s en ~7–10 plans de 3–5 s, storyboard depuis SDXL, montage final. C'est la structure indie 2–5 jours documentée.

**Benchmarks qui changeraient les recommandations :**
- Si un clip AniSora V3.2 Q5 sur la 5080 dépasse ~5–8 min/clip → basculer sur Wan 2.2 5B pour le prototypage, réserver le 14B au rendu final.
- Si la cohérence de personnage reste insuffisante avec IPAdapter seul → investir les 1–4 h d'entraînement LoRA (non négociable pour les personnages principaux).
- Si le flicker persiste → vérifier SageAttention (basculer sdpa), verrouiller la seed, ajouter Pixel Deflicker/FlowDenoise avant RIFE.

## Recommendations

1. **Abandonner AnimateDiff/SDXL comme moteur vidéo** et adopter AniSora V3.2 (I2V) comme cœur du pipeline, avec SDXL fabricatedXL conservé uniquement pour la génération des keyframes/character sheets. C'est le levier le plus fort pour une démo convaincante.
2. **Faire tourner le 14B AniSora en GGUF Q4_K_M/Q5_K_M sur la RTX 5080** (plus de VRAM), et réserver la 5060 Ti 16 Go au prototypage Wan 2.2 5B et au post-traitement (RIFE/SeedVR2) en parallèle.
3. **Entraîner un LoRA de personnage** dès que le moteur I2V est validé — c'est la seule méthode fiable pour la cohérence inter-clips, condition sine qua non d'une démo « cohérente ».
4. **Construire la chaîne Blender→Fun Control** uniquement pour les plans à mouvement complexe ; pour les plans simples, l'I2V AniSora depuis keyframe SDXL suffit et va plus vite.
5. **Standardiser la post-production** : Pixel Deflicker/FlowDenoise → RIFE rife49 (ou GMFSS Fortuna pour l'anime) → SeedVR2 upscale. MatAnyone pour la séparation personnage/décor.
6. **Structurer la démo en 7–10 plans courts** et livrer en style indie 2–5 jours ; documenter le pipeline (JSON ComfyUI reproductibles) — c'est précisément ce qui démontre la compétence technique visée.

## Caveats
- **Aucun benchmark de première main** ne publie les secondes/clip et la VRAM crête exactes d'AniSora V3.2 sur RTX 5060 Ti/5080 16 Go ; les estimations de temps sont des extrapolations de repères Wan 2.2 14B génériques.
- **Le guidage pose/depth/lineart/audio natif d'AniSora existe dans le code Python de Bilibili mais n'est pas exposé dans ComfyUI** ; pour du contrôle en ComfyUI il faut Wan 2.2 Fun Control/VACE, qui sont des familles de modèles distinctes (on ne peut pas combiner nativement le fine-tune anime AniSora et Fun Control dans une seule node supportée).
- Les chiffres marketing (94 % de cohérence multi-vues Apatero, revendications de vendeurs SaaS) sont **non vérifiés** et testés sur du matériel cloud 24–32 Go.
- Aucune trace publique d'un projet « Ov3rLoRd / Onibaku Gumi / Jérémy Gourlain » n'a été trouvée en ligne ; l'analyse de positionnement repose sur les éléments fournis dans la requête. À noter que « Onibaku » renvoie au duo de délinquants (Onizuka + Danma) de la série manga/anime *Shonan Junai Gumi* / GTO de Tooru Fujisawa — probable clin d'œil dans le nommage du projet.
- Les VRAM et temps de génération évoluent vite (Wan 2.7 sorti avril 2026) ; vérifier les versions avant tout achat/déploiement.
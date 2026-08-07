# État de l'art 2026 : dépasser la limite de cohérence temporelle en génération vidéo anime locale (pipeline Ov3rLoRd)

## TL;DR
- **La solution la plus mûre et directement applicable à votre pile (AniSora V3.2 / WAN 2.2 I2V, RTX 5080 + 5060 Ti 16 Go) est Stable Video Infinity (SVI) 2.0/2.0 Pro**, un LoRA d'« error recycling » entraîné spécifiquement pour WAN 2.2 I2V-A14B qui traite le problème de dérive à la racine (fine-tuning qui, selon le dépôt officiel, « recycles the Diffusion Transformer (DiT)'s self-generated errors into supervisory prompts, thereby encouraging DiT to actively identify and correct its own errors ») plutôt qu'avec des rustines de blending — à combiner avec les Context Windows de Kijai, un verrouillage colorimétrique en post (ColorMatch KJNodes) et un LoRA de personnage.
- **Aucune technique unique ne résout la dérive au-delà de ~37 frames ; la réponse 2026 est un empilement** : (1) SVI LoRA HIGH+LOW sur les deux experts MoE, (2) chaînage par motion-frames (1 frame pour SVI-Shot, 5 pour SVI-Film) avec padding VACE, (3) LoRA de personnage entraîné (rang 32 sur 12-16 Go) pour verrouiller l'identité, (4) ColorMatch/histogram-matching inter-clips pour le drift de couleur, (5) éventuellement une passe de re-colorisation lineart (AniDoc/LVCD) pour re-verrouiller la palette.
- **VACE (Fun-VACE A14B pour WAN 2.2) est fonctionnel et tient sur 16 Go en FP8/GGUF** (module ~3 Go en plus du backbone), et reste supérieur à WAN 2.2 Fun Control pour le contrôle multi-conditions ; mais pour la cohérence *inter-clips* longue durée, SVI + Context Windows est l'approche recommandée, VACE servant surtout à verrouiller l'arrière-plan par inpainting masqué.

## Key Findings

**1. Le problème est structurel, pas un bug de réglage.** WAN 2.x ne génère nativement pas plus de ~81 frames (au-delà, la vidéo boucle). Kijai (org Wan-AI) confirme les comptes optimaux : « A16B = 81 frames (16fps for 5s), 5B = 121 frames (24 fps for 5s) » ; le compte était littéralement codé en dur dans Wan2.1 I2V (PR #100 : « the Image2Video frames were hardcoded at 81! »). La dérive de couleur/anatomie/identité au-delà de ~30-45 s est le mode d'échec documenté et universel de toute la classe des modèles DiT (Sora, Veo, Kling, WAN, Hunyuan, CogVideoX, LTX) : la cohérence temporelle longue distance est leur faiblesse commune, et le coût quadratique de l'attention rend la génération longue durée coûteuse.

**2. Stable Video Infinity (SVI) est la percée la plus pertinente.** Publié par Wuyang Li, Wentao Pan, Po-Chien Luan, Yang Gao et Alexandre Alahi (VITA Lab de l'EPFL, arXiv 2510.09212, accepté ICLR 2026 Oral), SVI utilise l'« Error-Recycling Fine-Tuning » qui recycle les erreurs auto-générées du DiT en signal de supervision, au lieu de les combattre avec des rustines. Il existe une branche WAN 2.2 (`svi_wan22`) et des LoRA prêts pour ComfyUI.

**3. VACE pour WAN 2.2 est mûr et tient sur 16 Go.** Wan2.1-VACE a été ouvert le 14 mai 2025 (versions 14B et 1.3B) par Alibaba Cloud comme « the industry's first open-source model to provide a unified solution for various video generation and editing tasks ». Pour WAN 2.2, le module Fun-VACE A14B (HIGH+LOW) de Kijai existe en FP8 scaled (~3 Go par module) et en GGUF, s'intègre nativement et via WanVideoWrapper. Il surpasse Fun Control pour le contrôle multi-conditions (Depth+Pose chaînés, masquage).

**4. La re-colorisation lineart est disponible mais limitée.** AniDoc, LVCD et line2color (Kataragi) offrent une voie de décomposition temporelle, mais AniDoc plafonne à 14 frames par passe et LVCD est basé SVD (U-Net) sans contrôle sémantique.

**5. La cohérence inter-clips exige un LoRA de personnage, pas seulement une image de référence.** Le consensus 2026 : un LoRA de personnage entraîné (rang 32, entraînable sur 12-16 Go via AI-Toolkit) bat toute stratégie de prompt ou d'image de référence pour l'identité.

## Details

### 1. Overlap-blending / sliding window pour vidéo longue

**Mécanisme documenté (Kijai / ComfyUI natif).** Le node `WanVideo Context Options` (WanVideoWrapper) et son équivalent natif `WAN Context Windows (Manual)` implémentent le sliding window : un buffer contient les latents de toute la vidéo longue (4n+1 latents) ; une fenêtre de `context_length` frames subit une étape de sampling, puis se décale de `context_length − context_overlap` frames, en chevauchant la portion déjà traitée. Paramètres clés :
- `context_length` : nombre de frames par fenêtre (défaut historique AnimateDiff : 16 ; sur WAN, aligné sur la limite ~81).
- `context_overlap` : frames de chevauchement entre fenêtres — c'est le levier de cohérence.
- `context_stride` : à laisser à 1 (natif) / 4 (wrapper) ; les valeurs supérieures (héritage AnimateDiff) produisent du bruit sur WAN.

**État de maturité (décembre 2025 – juin 2026).** La documentation communautaire non officielle (« wanx-troopers ») est explicite : *« They're still iffy and fragile, especially for i2v »*. Les Context Windows fonctionnent bien si la caméra ne bouge pas et si l'arrière-plan est contrôlé, mais *« it is challenging to avoid background shifting between windows »*. Améliorations récentes :
- Décembre 2025 : PR de Kijai mergée dans ComfyUI natif ajoutant le support « freenoise » ; *« The context window blends are almost invisible, especially with freenoise enabled. »*
- Le node `WanVideo Encode Latent Batch` permet d'injecter une image de référence différente par fenêtre (branché sur `reference_latent`) — supporte MAGREF, HuMo, VACE, Phantom, Bindweave (expérimental).
- Juin 2026 : Kijai a ajouté `Context Windows Visualizer (KJ)` et le champ `cond_retain_index_list` (indices de latents à conserver, max ~16).
- Les workflows VACE avancés de Drozbay (`ComfyUI-WanVaceAdvanced`, `WanExperiments`, samplers RES4LYF) sont l'état de l'art pour le contrôle fin des fenêtres.

**Blending latent vs pixel.** Le blending des Context Windows se fait en espace latent (pendant le sampling). Pour le raccord *pixel-space* entre deux générations distinctes, la pratique communautaire (issue HunyuanVideoWrapper #476) utilise un `ColorMatch` sur la frame de recouvrement pour corriger le drift de grading/luminosité, plus la suppression de la frame dupliquée en fin de clip.

**Recommandation overlap.** Pour du I2V WAN 2.2, l'approche par **motion-frames de SVI** (voir §2) est plus fiable que le sliding window pur : chaîner en réinjectant les 1 ou 5 dernières frames du clip précédent comme latents de conditionnement.

### 2. Infinite video generation — état de l'art 2026

| Méthode | Base | ComfyUI | 16 Go ? | Verdict pour Ov3rLoRd |
|---|---|---|---|---|
| **Stable Video Infinity 2.0/Pro** | WAN 2.1 **et 2.2 I2V** | ✅ officiel (SVI-Shot) + Kijai | ✅ via FP8/GGUF | **Recommandé n°1** |
| StreamingT2V | modèle propre | ❌ pas d'intégration native | — | R&D, non applicable |
| FreeNoise | rééchantillonnage bruit | partiellement (intégré comme option « freenoise » dans les Context Windows) | ✅ | Utile en complément |
| FIFO-Diffusion | file diagonale de denoising | ❌ pas de node ComfyUI mûr | — | R&D |

**Stable Video Infinity — détails techniques vérifiés.**
- **Repo** : `github.com/vita-epfl/Stable-Video-Infinity` (ICLR 26 Oral). Branche `main` = base WAN 2.1 ; branche `svi_wan22` = base **WAN 2.2** (SVI 2.0 et 2.0 Pro). Les checkpoints officiels (`vita-video-gen/svi-model` sur HuggingFace) confirment la répartition en variantes via des fichiers distincts (`svi-film-transitions`, `svi-tom`, `svi-talk`, `svi-dance`).
- **Chronologie** : SVI 2.0 (04/12/2025), workflow ComfyUI WanVideoWrapper (07/12/2025), SVI 2.0 Pro (26/12/2025, capacité « 50 clips / 250 s »).
- **LoRA HuggingFace (Kijai)** : `huggingface.co/Kijai/WanVideo_comfy/tree/main/LoRAs/Stable-Video-Infinity/v2.0` — fichiers `SVI_Wan2.2-I2V-A14B_lora_HIGH_v2.0_rank_128_fp16.safetensors` et `..._LOW_...` (+ variantes PRO). Chaque LoRA ~1,23 Go, rang 128. **Impératif MoE** : appliquer le LoRA sur les DEUX experts (HIGH-noise et LOW-noise).
- **Variantes et overlap de chaînage (vérifié README officiel)** :
  - **SVI-Shot** : 1 motion frame (dernière frame) + padding VACE via l'image de référence. *Seul workflow ComfyUI officiellement open-sourcé.*
  - **SVI-Film** : *« uses 5 motion frames (last 5 frames) for i2v, not 1 »* — meilleure continuité de mouvement.
  - **SVI-Tom** : partage le workflow de Film mais 1 motion frame.
  - **SVI-Dance** : conditionné squelette/pose (lignée UniAnimate-DiT) ; une version « Wan 2.2 Animate SVI » est annoncée.
- **VRAM 16 Go** : pas de chiffre officiel SVI (env. de référence = A100 80 Go), mais SVI n'est qu'un LoRA ; le coût réel est celui de WAN 2.2 14B I2V. En **FP8 ~16 Go « confortable »** ; en **GGUF Q4/Q5 avec offload T5 sur CPU, ~6-8 Go à 480p**. Un utilisateur RTX 5060 Ti 16 Go rapporte WAN 2.2 Q8 GGUF, 5 s @1024×574 en ~7 min avec Sage Attention. Les installateurs communautaires (The Local Lab) livrent SVI 2.0 en GGUF (jusqu'à Q3_K_S) + LoRA de distillation LightX2V, ciblant explicitement les cartes low-VRAM.
- **Réglages communautaires** : CFG 1.5, Shift 8, Steps 6, Euler/Simple ; les auteurs recommandent *« more sampling steps than 4/8 »* si quantifié ; **seed différent par clip impératif**.
- **Attention** : le LoRA SVI ne peut pas utiliser directement le workflow WAN 2.1 original — il exige des réglages de padding modifiés.

### 3. IPAdapter + LoRA pour la cohérence de personnage inter-clips

**IPAdapter WAN existe en 2026** : l'extension `ComfyUI-IPAdapterWAN` injecte des embeddings de visage de référence pendant le sampling, réduisant l'identity drift et le face warping non traités nativement par WAN 2.1/2.2. C'est un mécanisme attention-based par réattention aux features du visage de référence à chaque étape.

**Mais le consensus 2026 privilégie le LoRA de personnage.** Retour d'expérience documenté (40+ LoRA WAN 2.2 entraînés, AI-Toolkit sur 12 Go / ComfyUI sur 24 Go) : *« putting the same effort into a LoRA that you put into your prompts will give you more reliable character consistency than any prompt or reference image strategy can »*. Points clés :
- Un LoRA rang 32 est entraînable de façon fiable sur 12 Go de VRAM.
- L'identité dépend surtout de l'expert LOW-noise (raffinement) mais il faut aussi la composition de l'expert HIGH-noise.
- Astuce upstream : générer d'abord une feuille de personnage multi-angles cohérente avec un modèle d'édition (ex. Qwen Image Edit), puis construire le dataset WAN sur cette source d'identité plus propre.

**Alternatives à référence unique** : Phantom (WanVideo, single/multi-sujet, ~4 Go VRAM pour 1 sujet à 480p, ~8 Go pour 2) et MAGREF/Bindweave, tous supportés par le mécanisme `reference_latent` des Context Windows. Pour un usage rigoureux d'identité, le LoRA reste supérieur.

**Workflow recommandé Ov3rLoRd** : LoRA de personnage entraîné sur fabricatedXL-cohérent + AniSora V3.2 I2V, LoRA appliqué sur HIGH et LOW, avec injection Phantom/MAGREF par fenêtre pour les changements de plan.

### 4. VACE (Video Aware Conditioning Enhancement)

**Maturité 2026** : VACE est le modèle « all-in-one » d'édition/génération vidéo d'Alibaba Tongyi Lab, ouvert le 14 mai 2025 (Wan2.1-VACE 14B et 1.3B), « the industry's first open-source model to provide a unified solution for various video generation and editing tasks ». Pour WAN 2.2, c'est le module **Fun-VACE A14B** (entraîné sur WAN 2.2 T2V A14B).
- **VRAM / intégration** : modules `Wan2_2_Fun_VACE_module_A14B_HIGH/LOW` en FP8 scaled ~**3,05 Go chacun** (chez Kijai), plus le backbone WAN 2.2 T2V ; existe aussi en GGUF (Q4/Q8). Chargement natif ou via WanVideoWrapper. La doc communautaire indique un plancher pratique de **12 Go VRAM** pour VACE 14B (SwarmUI/ComfyUI). Tient donc sur vos 16 Go.
- **VACE vs Fun Control** : VACE permet de **chaîner plusieurs conditions VACE** (Depth + Pose + masquage), là où Fun Control est limité par le préprocesseur. VACE surpasse Fun Control pour les scènes à fort mouvement (combats, rotations 360°, restylage). *Réserve* : sur WAN 2.2, certaines fonctions VACE (préservation d'identité) ont d'abord été cassées dans les portages expérimentaux ; utiliser le Fun-VACE A14B officiel.
- **Efficacité anime** : VACE n'est pas spécialisé anime ; pour votre cas, son meilleur usage est le **verrouillage de l'arrière-plan par inpainting masqué** (masquer le fond d'une vidéo existante pour l'empêcher de dériver entre fenêtres) et le contrôle de mouvement précis, en complément d'AniSora pour le rendu du style.
- **Comparaison SVI** : pour la cohérence *inter-clips* longue durée, SVI (fine-tuning anti-dérive) est plus adapté que VACE (contrôle par conditions) ; les deux sont combinables (SVI-Shot utilise justement un padding VACE).

### 5. Approches de décomposition temporelle (lineart → recolor → cel-shading)

Voie pertinente pour *corriger* le drift post-génération en re-verrouillant la palette sur un lineart stable.
- **AniDoc** (`ComfyUI-AniDoc`, LucipherDev) : colorise des séquences de lineart d'après une image de référence, avec cohérence temporelle. **Limite forte** : le modèle attend **14 frames par passe** (basé SVD) — il faut prétraiter la séquence en blocs de 14, ce qui le rend peu pratique pour du 30-45 s continu. Télécharge auto SVD-img2vid-xt + AniDoc + CoTracker.
- **LVCD** (`luckyhzt/LVCD`, ACM TOG) : premier framework de colorisation lineart vidéo par diffusion, avec **Reference Attention** + un **Overlapped Blending Module** et **Prev-Reference Attention** pour l'échantillonnage séquentiel qui étend le modèle au-delà de sa longueur fixe. C'est théoriquement le plus proche de votre besoin (long, cohérent), mais basé SVD (U-Net), sans contrôle texte/sémantique et faible sur les grands mouvements.
- **line2color (Kataragi)** : ControlNet SDXL (`kataragi/controlnetXL_line2color`) qui colorise du lineart (ligne noire sur fond blanc, préprocesseur = none). Version fp16 (2,5 Go) plus fidèle que la version LoRA (377 Mo). C'est un colorisateur *image* — utilisable frame par frame avec votre fabricatedXL SDXL, mais sans cohérence temporelle propre (à coupler avec AnimateDiff/ControlNet tile).
- **AnimeColor** (arXiv 2507.20158) : colorisation par DiT, positionné comme surpassant LVCD/AniDoc/ToonCrafter — à surveiller, pas encore de node ComfyUI mûr.

**Verdict** : la décomposition lineart est un filet de sécurité en post, pas une solution primaire de cohérence longue durée. Pour Ov3rLoRd, la voie la plus rentable est de générer proprement avec SVI puis d'appliquer un ColorMatch, en réservant AniDoc/LVCD aux plans problématiques courts.

### 6. Gestion du drift de couleur spécifiquement

C'est votre symptôme le plus net (sneakers qui changent de coloris). Outils open source ComfyUI 2026 :
- **ColorMatch (KJNodes, Kijai)** : transfert de couleur (Reinhard, Pitié, MVGD + histogram matching). C'est l'outil de référence pour corriger le drift de grading entre clips — brancher la dernière frame stable comme référence sur chaque nouveau clip.
- **ColorMatchImage (ComfyUI-Image-Filters)** et **ColorPaletteExtractor / EasyColorCorrector (regiellis)** : extraction de palette, histogram/LAB matching, avec détection anime vs photo et préservation des skin tones ; option `lock_input_image`.
- **comfyui-diffusion-cg (Haoming02)** : color grading en manipulant le tenseur de bruit latent — corrige les dérives de saturation/contraste propres à l'espace latent SDXL.
- **Recherche** : la R&D 2026 (Helios, FreqForcing) identifie que le drift se manifeste d'abord par des dérives de **saturation HSV** et de statistiques RGB — d'où l'intérêt d'un monitoring HSV et d'un re-lock par histogramme.

**Recette anti-drift couleur pour Ov3rLoRd** : (a) définir une palette de personnage de référence (extractor) ; (b) après chaque clip SVI, ColorMatch sur la première frame vers la dernière frame du clip précédent (espace LAB) ; (c) pour un verrouillage dur des couleurs d'accessoires (sneakers), envisager un masque VACE + inpainting de la zone, ou une passe line2color sur les frames dérivées.

### 7. Temporal attention et cohérence longue distance : comparaison des modèles sur 16 Go

- **WAN 2.2 14B I2V (AniSora V3.2)** : le backbone WAN 2.2 (Alibaba Tongyi Lab, publié le 28 juillet 2025, Apache 2.0, architecture MoE, trois modèles T2V-A14B / I2V-A14B / TI2V-5B) « can generate a 5-second high-definition video in a single pass ». Montre les résultats les plus cohérents parmi les I2V auto-hébergeables, meilleur que LTX-Video pour les clips longs. FP8 ~16 Go, GGUF dès 6-8 Go. **Reste votre meilleur choix pour l'anime** (AniSora est un fine-tune WAN 2.2 spécialisé). AniSora V3.2 a été publié le 23/09/2025, « trained on the stronger wan2.2 model and can reduce the number of inference steps to 8 » ; une variante V3.1 « 12GB VRAM available » existe sur ModelScope ; un modèle `anisora-anymask` (masques temporel+spatial pour I2V) a été publié le 31/10/2025.
- **HunyuanVideo 1.5** (Tencent, publié le 20 novembre 2025, 8,3 Md paramètres) : tourne sur un **minimum de 14 Go de VRAM via model offloading** (la cible ComfyUI native est 24 Go), unifie T2V/I2V, utilise une attention SSTA (Selective and Sliding Tile Attention) offrant un speedup 1,87× sur du 10 s 720p vs FlashAttention-3 ; très adopté par la communauté ComfyUI, excelle sur le mouvement naturel/physique. Licence restreinte (>100 M MAU). Supporté par les Context Windows (le fix Kijai de déc. 2025 couvre Hunyuan 1.5). Moins spécialisé anime que WAN/AniSora.
- **LTX-2.3** (Lightricks, open janvier 2026, Apache 2.0, 18 M+ téléchargements HF) : champion vitesse/accessibilité, audio-vidéo natif en une passe, conditionnement IC-LoRA (depth/pose/edge). Support Context Windows pour LTX 2.x en cours (PR ComfyUI #13325, avril 2026). Moins bon en qualité photoréaliste/visage que WAN.
- **CogVideoX / CogVideoX-1.5** : le 5B tourne sur 24 Go standard ; cohérence correcte mais exige plutôt H100 pour 720p à vitesse utilisable. Non recommandé sur 16 Go.

**Conclusion** : sur 16 Go et pour l'anime, aucun modèle ne bat WAN 2.2 + AniSora V3.2 en 2026 pour votre cas ; le gain de cohérence longue durée viendra de SVI et des LoRA, pas d'un changement de backbone. HunyuanVideo 1.5 est le seul candidat sérieux à tester en parallèle (offload 14 Go).

### 8. Pratiques des studios indépendants / solo pour 30 s+

Le workflow réel observé chez les indés en 2026 est le **chaînage de clips courts avec hand-off de latents**, pas la génération monolithique :
- **Génération par « passes »** : ex. le workflow SVI 2.0 (RunComfy) organise 5 passes qui se passent les latents de mouvement, avec overlap blending et un render final qui recoud le tout.
- **Storyboard engines** (ex. « Muse Studio », « Storyboard Engine ») : jusqu'à 4 prompts séquentiels, un clip par action, recousus, avec ColorMatch pour la fidélité colorimétrique + RIFE pour lisser + LoRA de personnage.
- **Compromis acceptés (retour terrain)** : un testeur note que le style anime *« is slowly lost as the video extends each time (roughly every 5 seconds) … the colour balance and style also seems to change »* et qu'il n'a pas réussi à dépasser 15-20 s en continu, d'où le splicing de plusieurs clips de même source. C'est exactement votre limite — la parade est le chaînage + relock, pas la génération continue.
- **Direction multi-agents** (R&D bilibili) : **AniME: Adaptive Multi-Agent Planning for Long Animation Generation** (Lisai Zhang et al., bilibili, soumis le 26/08/2025, arXiv 2508.18781) — « a director-oriented multi-agent system… The director agent keeps a global memory for the whole workflow… integrating customized Model Context Protocol (MCP) ». Piste d'architecture pour automatiser le pipeline, pas un outil clé-en-main.

### 9. R&D documentée récente (arXiv 2025-2026) applicable en solo

Familles de méthodes anti-dérive, par ordre d'applicabilité :
- **Error Recycling — SVI** (arXiv 2510.09212, ICLR 26 Oral) : **déjà utilisable** (LoRA WAN 2.2). La plus directement applicable.
- **Self-Forcing / Rolling Forcing** (arXiv 2506.08009 ; 2509.25161) : réduisent l'écart train/test en auto-régressif temps réel ; Rolling Forcing génère des vidéos longues en temps réel. Code de recherche, pas de node ComfyUI mûr.
- **FreqForcing** (arXiv 2607.27110) : « Spectral Self-Anchoring » — préserve la cohérence sur des vidéos à l'échelle de la minute (120 s), meilleure stabilité couleur/mouvement que Self-Forcing, Rolling Forcing, LongLive, Deep Forcing ; sans entraînement additionnel. Très pertinent conceptuellement (le drift se lit dans l'énergie spectrale de l'attention).
- **Helios** (arXiv 2603.04379) : « Easy Anti-Drifting » sans self-forcing ni error-bank, via **Relative RoPE** (le décalage de position est une source majeure de dérive) — technique légère, potentiellement portable.
- **HiAR** (arXiv 2603.08703) : denoising hiérarchique auto-régressif + **suite de métriques de drift** (MUSIQ, CLIP-IQA, DINOv2 frame-to-frame, LPIPS, saturation HSV, netteté Laplacienne) — utile pour *mesurer objectivement* votre dérive.
- **A2RD** (arXiv 2605.06924), **VideoWeaver** (arXiv 2606.08091), **LongLive**, **LoViC**, **BindWeave** : approches segment-based / agentiques / mémoire — pistes d'architecture pipeline.

## Recommendations

**Étape 1 — Correctif immédiat (jours), sans changer de backbone.**
1. Installer les LoRA **SVI 2.0 Pro WAN 2.2 I2V-A14B (HIGH + LOW)** depuis `Kijai/WanVideo_comfy` et les appliquer sur les deux experts MoE d'AniSora V3.2. Utiliser le workflow SVI-Shot officiel (1 motion frame + padding VACE) sur la RTX 5080 (24 Go), GGUF Q8/FP8 sur la 5060 Ti 16 Go.
2. Réglages de départ : CFG 1.5, Shift 8, 6-8 steps (Euler/Simple), **seed différent par clip**. Générer en 480p pour la revue, 720p pour le final.
3. Insérer un **ColorMatch (KJNodes)** en fin de chaque clip, référence = dernière frame stable du clip précédent (espace LAB).
- *Benchmark de succès* : dépasser 60 s sans dérive visible des sneakers ni du visage. Si le drift persiste → Étape 2.

**Étape 2 — Verrouillage d'identité (1-2 semaines).**
4. Entraîner un **LoRA de personnage rang 32** (AI-Toolkit) sur une feuille multi-angles générée en amont (Qwen Image Edit / fabricatedXL), l'appliquer sur HIGH+LOW en plus de SVI.
5. Pour les changements de plan, injecter la référence par **Phantom / MAGREF via `WanVideo Encode Latent Batch` → `reference_latent`** des Context Windows.
- *Benchmark* : identité stable sur un changement de plan complet. Si le fond dérive → activer **VACE inpainting masqué** du background.

**Étape 3 — Filet de sécurité colorimétrique et post (au besoin).**
6. Pour les accessoires qui dérivent malgré tout (sneakers), passe ciblée **line2color (Kataragi) frame-par-frame** ou masque VACE + inpainting de la zone, sur les seuls plans problématiques.
7. Réserver **AniDoc/LVCD** aux plans courts nécessitant un re-lock de palette (attention : AniDoc = blocs de 14 frames).
8. Instrumenter la dérive avec la **suite de métriques HiAR** (saturation HSV + DINOv2 frame-to-frame) pour objectiver les progrès.

**Étape 4 — Veille / R&D (continue).**
9. Tester **HunyuanVideo 1.5** en parallèle (offload 14 Go) comme backbone alternatif pour les plans à fort mouvement.
10. Suivre **FreqForcing** et **Helios (Relative RoPE)** — si un portage ComfyUI apparaît, ce sont les candidats anti-dérive les plus prometteurs sans réentraînement.
11. Surveiller la sortie annoncée **« Wan 2.2 Animate SVI »** (SVI-Dance nouvelle génération).

*Seuils de décision* : rester sur WAN 2.2/AniSora tant que la cohérence à 60 s est atteignable via SVI+LoRA. Envisager un changement de backbone seulement si un modèle open démontre un « Drift Score » (métrique HiAR) nettement inférieur sur des séquences anime >30 s à VRAM égale.

## Caveats
- **Fragilité des Context Windows en I2V** : documentée comme « iffy and fragile » ; le shift d'arrière-plan entre fenêtres reste le point faible. SVI (motion-frames) est plus robuste que le sliding window pur.
- **Aucun chiffre VRAM officiel pour SVI** : le ~16 Go dérive du backbone WAN 2.2 14B FP8 ; sur la 5060 Ti 16 Go, prévoir GGUF Q5-Q8 + offload T5, temps de génération de plusieurs minutes par clip de 5 s.
- **Pas de workflow ComfyUI natif officiel pour AniSora** (bilibili ne livre que des scripts Python) ; l'usage passe par WanVideoWrapper de Kijai, le GGUF `QuantStack/Index-Anisora-V3.2-GGUF`, ou des workflows communautaires (certains payants ; certaines allégations VRAM/vitesse sont marketing).
- **SVI-Film/Tom non pleinement open-sourcés** : seul SVI-Shot a un workflow ComfyUI officiel ; Film/Tom sont sensibles à la quantification/distillation.
- **La R&D la plus avancée (FreqForcing, Helios, A2RD, Rolling Forcing) n'a pas d'intégration ComfyUI mûre** en 2026 — ce sont des pistes, pas des outils prêts à l'emploi. Les numéros arXiv en 26xx sont des prépublications 2026 récentes, à vérifier avant intégration.
- **AnimateDiff est en fin de pertinence** pour la vidéo longue face aux DiT (WAN/Hunyuan) ; son sliding window reste conceptuellement utile mais dépassé en qualité.
- Plusieurs sources chiffrées (installateurs Patreon/Gumroad) sont commerciales ; les chiffres de vitesse/VRAM annoncés sont à traiter comme des estimations marketing non vérifiées indépendamment.
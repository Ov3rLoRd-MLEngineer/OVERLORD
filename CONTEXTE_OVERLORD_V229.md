# CONTEXTE_OVERLORD_V229.md
# Cerveau de Démarrage — Session 2026-07-07
# Pipeline Ov3rLoRd / Jérémy Gourlain
# Généré en fin de session — reprendre immédiatement sans questions superflues

---

## 0. CORRECTIONS DE CONTEXTE (IMPORTANTES)

- **Khara (Noisy-le-Grand) n'est PAS une cible de pitch** — c'est une association rencontrée à Japan Expo, sans lien avec le projet. Références studios pour l'ambition : Gainax, Mappa, etc. Cible recrutement : **Mistral**.
- **Japan Expo abandonnée comme deadline** — remplacée par un critère de sortie qualité : **1000 frames à 24fps, cohérence parfaite inter-frames, montrable sans excuse**.
- Positionnement stratégique validé : Bilibili (AniSora, updream, Index) est verrouillé sur le marché sinophone. Le marché occidental des outils de production anime IA est **libre** — on n'affronte pas Bilibili, on occupe un terrain qu'ils ne couvrent pas. "Le judoka ne bat pas le sumo — il joue un autre sport."
- Étagement économique réaliste confirmé : SegNets publiés → ~100€/mois de soutien communautaire (Ko-fi/GitHub Sponsors, objectif à 2-4 mois) → portfolio → emploi (le vrai levier). Aucun fantasme de valorisation — les chiffres type "pipeline = 450k€" (Copilot) sont de la flatterie non calibrée, à ignorer.

---

## 1. ÉTAT ACTUEL — PROJET SEGNET FAMILY (PRIORITÉ ABSOLUE)

### ADR validée : architecture modulaire (pas de modèle multi-classes unique)
4 modules spécialisés : **FootSegNet** (prioritaire), HandSegNet, FaceSegNet, BodySegNet.
Tous livrés sur main : `generate_dataset.py`, `annotate.py`, `build_coco.py`, `train.py`/`train_sam.py`, `infer.py` + structure dataset COCO complète.

### Avancement
- **300 images générées et vérifiées pour CHACUN des 4 datasets** (hallucinations et images sans contexte supprimées/régénérées)
- **FootSegNet : 50/300 images annotées pixel-perfect** au stylet Huion (masques binaires BLANC=objet, qualité validée — contours nets, pas de fuites)
- Augmentation automatique : flip horizontal dans les 4 `build_coco.py` (train seulement, val propre, options `--augment-val`/`--no-augment`). Rotation ±15° discutée, à ajouter au moment voulu.
- Distinction gauche/droite : **Option A validée** — post-traitement géométrique par position X (couvre ~90% des cas). Cas atypiques (high kick 180°, vue de dos) annotés explicitement dans le dataset pour la robustesse. Distinction native en V2 si demande communautaire.
- Entraînement : fine-tuning du mask_decoder seul, encodeur ViT-B gelé bf16, tient sur RTX 5080 16GB. `schedule_training.bat` prêt (logs par module dans `workspace\logs\training\`).
- `inpaint_corrector.py` déjà branché sur `footsegnet\infer.py` avec repli automatique (SAM générique si checkpoint absent).

### Publication (stratégie validée)
- **Un module à la fois**, FootSegNet d'abord (2-3 semaines après entraînement concluant), HandSegNet ensuite. Chaque sortie = un événement.
- Licence : **Apache 2.0 + attribution** ("FootSegNet by Ov3rLoRd / Jérémy Gourlain") + page donations Ko-fi/GitHub Sponsors. Adoption maximale > restriction commerciale : la valeur commerciale c'est Jérémy, pas le modèle seul.
- Communication : post r/comfyui avec gif avant/après (SAM générique vs FootSegNet), carte de dataset Hugging Face propre (méthodologie, benchmark IoU vs SAM base).

---

## 2. INFRASTRUCTURE MISE EN PLACE CETTE SESSION

### Claude Code (opérationnel)
- v2.1.199, compte Pro, dossier racine `D:\OVERLORD` + `--add-dir "D:\Ov3rLoRd AI"`
- `launch_claude.bat` + raccourci bureau "Claude OVERLORD"
- CLAUDE.md généré par /init, règle "toujours en français" active
- `gh` CLI installé et authentifié (g915tlk-design) → PR automatiques
- 8 PR mergées cette session (SegNets, flip, zoom/pan annotate, fallback LLM, llm_endpoints, llm_router, ADR TTS/Music)

### Dual/Tri-GPU
- RTX 5080 16GB (GPU 0) → ComfyUI + affichage
- RTX 2070 8GB (GPU 1) → Ollama, épinglée par **UUID** (`CUDA_VISIBLE_DEVICES` par index NON honoré par cette version d'Ollama — piège corrigé, Ollama volait 6.6GB à la 5080)
- `launch_ollama.bat` corrigé avec UUID + raccourci bureau
- **RTX 5060 Ti 16GB achetée (Asus Dual OC, 499€90 Grosbill, ~18€/mois)** — à installer, remplacera la 2070. Elgato 4K prévue sur le 3ème PCIe (capture Twitch + source de data future).
- Crashs écran occasionnels = probablement TDR Windows (GPU compute sans écran) — ajuster le registre TDR si ça persiste pendant les entraînements overnight.
- Alim 1000W : marge OK (~660W en charge avec les 3 cartes).

### LLM locaux
- Ollama : mistral, qwen2.5:7b, deepseek-r1:7b installés et testés sur la 2070
- `fallback_llm()` : séquence mistral → qwen2.5 → deepseek-r1, 30s timeout/modèle, `_strip_think()` pour deepseek. Dans les DEUX `overlord_utils.py` (racine + agents/).
- `config/llm_endpoints.json` : Ollama (actif) + GLM-5.2 Z.ai (placeholder, désactivé par défaut, mode `OV_LLM_MODE=glm`)
- `agents/llm_router.py` : routage par type de tâche — "code"→deepseek, "prompt_refinement"→qwen, "general"→mistral, "complex"→GLM-5.2 si activé. Repli auto sur fallback_llm().
- Bug préexistant noté : fallback_llm() d'agents/ ignore son paramètre model pour la séquence Ollama (contourné par appel direct dans le router, non corrigé).

### Audio (ADR-011 et ADR-012 déployées)
- **TTS** : Coqui XTTS-v2 principal (CPML — gratuit sous seuil de revenu), gTTS fallback. `CoquiTTSSynthesizer` dans `v140_voice_synthesis.py`, synthèse isolée en sous-processus (`_coqui_tts_worker.py`) après découverte d'un segfault natif GPT2+appel LLM même processus. Testé cuda:1. transformers épinglé 4.57.6 (conflit ComfyUI corrigé), FFmpeg partagé installé (BtbN 8.1 winget).
- **Music** : MusicGen small via transformers, séquentiel (jamais concurrent ComfyUI), **flag non-commercial obligatoire** (CC-BY-NC Meta) propagé jusqu'au publisher (`check_music_license()` bloque toute publication monétisée). Suno = usage manuel hors pipeline uniquement (pas d'API officielle). audiocraft installé --no-deps (spacy/thinc ne compilent pas en 3.12, non nécessaire).

---

## 3. VEILLE TECHNIQUE — DÉCOUVERTES MAJEURES (recherche Fable 5 du 07/07)

### Intégrations prioritaires (outils existants)
| Priorité | Outil | Usage | Note |
|---|---|---|---|
| **HAUTE** | **Matanyone** | Propagation de masque vidéo par tracking : FootSegNet seed frame 1 → Matanyone propage sur 1000 frames, re-seed FootSegNet tous les 50-100 frames contre la dérive | VRAM /2 récemment, dispo dans Wan2GP |
| **HAUTE** | **ComfyUI-Frame-Interpolation** (RIFE/TLB-VFI) | "Shooting on twos" : générer 12fps → interpoler 24fps = /2 sur le temps de génération | Standard anime réel |
| **HAUTE** | **SeedVR2** | Upscaler vidéo référence 2026, préserve structure, excellente cohérence personnage | Pour la passe finale démo |
| MOYENNE | **AniSora V3.2** (Bilibili) | Modèle vidéo anime natif, entraîné sur Wan2.2, 8 steps, version 12GB dispo ModelScope. Variante "anymask" = masques spatio-temporels (≈ notre multi-pass en natif) | À benchmarker vs AnimateDiff sur Asuka Run. Reward models anime (AnimeReward) publiés = juge qualité gratuit |
| MOYENNE | **VACE** (Alibaba) | Video re-render avec préservation posture/motion/structure — le retake vidéo natif | Écosystème Wan |
| MOYENNE | **Wan 2.2 5B TI2V** | Seul modèle vidéo "frontier" tenant en 16GB consumer | |
| MOYENNE | **blender-mcp** | Claude pilote Blender en langage naturel (scènes, caméra, rendus, assets Poly Haven) — remplace les manips Blender manuelles | **Première install post-FootSegNet, effort quasi nul** |
| MOYENNE | **ComfyUI-MCP** | Même principe pour ComfyUI — piloter les workflows en langage naturel | À évaluer après blender-mcp |
| BASSE | FlashVSR, Scail 2, Topaz Proteus v5 | Alternatives/références | Topaz = référence anti-flicker, payant → solution maison préférée (voir axes recherche) |

### Complémentarité manette/Unity vs blender-mcp
Deux modes du même outil : manette = capture de mouvement organique temps réel humain (ADR Unity validée, post-démo). blender-mcp = mise en scène précise par langage naturel (caméra, props, rendus). Le workflow hybride de l'ADR reste bon — blender-mcp en automatise la moitié Blender.

---

## 4. AXES DE RECHERCHE ORIGINAUX (gaps identifiés, personne ne les couvre en juin 2026)

1. **DesignLock / ModelSheet Enforcer** ⭐ LANCÉ COMME AXE PRINCIPAL — conformité topologique au design (nombre/position des lignes : plugsuit, sneakers). Aucune solution existante, les LoRA n'apprennent qu'une approximation statistique. Architecture fusionnée validée :
   - Références canoniques (designs ORIGINAUX auto-générés ComfyUI par forçage progressif, ou sources libres) → extraction lineart canonique
   - Pour les angles : modèle 3D du prop (Meshy AI depuis photos 360° pour les tests internes UNIQUEMENT — StockX/Games Workshop = designs protégés, JAMAIS en publié/monétisé) → blender-mcp projette le lineart sous l'angle de la frame
   - LoRA propose (statistique), lineart canonique impose (ControlNet), SegNets localisent, QC topologique vérifie
   - **Injection via la déstructuration-redessin** (voir point 2)
   - Proof of concept : LoRA Jordan AJ1 (déjà dans les next steps V228) — démo interne only
2. **Déstructuration-redessin (genga→douga IA)** — décomposer la frame N en croquis structurel, redessiner entièrement avec mémoire bidirectionnelle (frame N-1 rendue + croquis N+1). N'existe nulle part. Réorganisation philosophique des briques existantes (lineart + IPA) : "clean-up d'un croquis" au lieu de "génération guidée". Véhicule naturel du DesignLock.
3. **Module de timing anime** — timing chart automatique (8/12/24fps variable, hold frames, plans fixes avec seulement bouche/yeux animés via FaceSegNet en dialogue = limited animation japonaise). Algorithmique, peu coûteux, différenciation conceptuelle majeure ("eux ils ont compris l'anime").
4. **QC anatomique avec retake ciblé** — "frame 347, main 6 doigts → inpaint auto zone main frames 340-355". Boucle détection→localisation (SegNets)→retake. Extension naturelle du pipeline inpaint existant.
5. **Line stabilizer temporel (anti "line boiling")** — le Topaz maison : optical flow + fenêtre glissante + moyenne adaptative par région segmentée. Faisable OpenCV + modèle léger, spécialisé anime (aplats + contours nets = propriétés exploitables). Phénomène déjà observé dans nos tests.
6. **ColorLock** — verrouillage palette par région sémantique (iro shitei). Sous-ensemble du DesignLock, les SegNets fournissent les régions.
7. **RGBA multi-couches vidéo natif** — génération directe en couches alpha (BG/char/FX). Vision long terme, LayerDiffuse ne le fait qu'en statique.

**Principe transversal validé : les SegNets sont l'infrastructure de TOUT le reste** (localisation pour DesignLock, ColorLock, QC, timing facial, retakes). Chaque module renforce les autres.

**Solutions maison préférées aux outils payants partout où c'est faisable** (décision de principe, contraintes financières).

---

## 5. OPTIMISATION TOKENS (pratiques validées, source : vidéo + croisement sources 2026)

- Principe clé : chaque message relit tout l'historique — le coût se compose exponentiellement (cas documenté : 98,5% des tokens d'une session = relecture d'historique)
- `/clear` entre tâches non liées + `/rename` avant. **Résumé manuel + nouvelle session > /compact tardif** (= la pratique CONTEXTE_VX.md, validée par l'écosystème entier)
- `/compact` proactif vers 50-60% si on continue la MÊME tâche (40% de la vidéo jugé trop agressif — tranché)
- CLAUDE.md < 3000 tokens — **audit à faire** (celui généré par /init est riche), déplacer le non-essentiel vers des fichiers à la demande
- `/model` : choisir EN DÉBUT de session (le switch invalide le cache). Haiku micro-tâches, Sonnet défaut, `/model opusplan` pour gros chantiers. Fable 5 : promo terminée le 7 juillet au soir — retour Sonnet.
- **Images = 15-20k tokens chacune** → coller le TEXTE du terminal plutôt que des screenshots quand possible ; screenshots réservés au réellement visuel (UI, masques, rendus)
- `/btw` pour les questions parenthèses (ne polluent pas l'historique)
- Pointer fichiers/lignes précis ("modifie agents/llm_router.py lignes 40-80") vs exploration aveugle du repo 150 agents
- Instructions de brièveté dans CLAUDE.md ("25 mots max entre tool calls, 100 mots réponse finale") — à ajouter
- MCP/skills inutiles désactivés (5-15% du contexte permanent)
- Éditer un prompt raté plutôt qu'empiler les corrections. Regrouper les questions en un message.
- `/context` pour diagnostiquer, status line pour visualiser en continu — à configurer
- Sous-agents : uniquement pour tâches ISOLÉES (recherche, fichier unique), jamais pour tâches liées au contexte principal (double lecture)
- Caveman : écarté (concision forcée dégrade le raisonnement complexe)

**Actions Claude Code en attente** : compresser CLAUDE.md + ajouter section compact instructions + brièveté + configurer status line.

---

## 6. VEILLE HEBDOMADAIRE — SITES POUR trend_scout.py (agent futur)

Accessibles librement : github.com/deepbeepmeep/Wan2GP (**le changelog = veille condensée à lui seul**), github.com/bilibili/Index-anisora (releases), huggingface.co trending, docs.comfy.org + blog, runcomfy.com/comfyui-nodes, r/comfyui + r/StableDiffusion (RSS/API), arxiv cs.CV, aibase.com/news (actus IA Chine en premier).
Avec credentials Jérémy : civitai.com/civitai.red (API + token perso, tri Most Downloaded mensuel), Discord **Banodoco** (LE hub vidéo IA, techniques avant Reddit), X (Kijai, cubiq, LatentHeart, deepbeepmeep).
Méthode manuelle en attendant : 15 min/semaine, noter ce qui revient 2×, soumettre à Claude pour tri "on a / on n'a pas / ça vaut le coup".

---

## 7. CONFIG COMFYUI VALIDÉE (inchangée)

```
Checkpoint    : fabricatedXL_v70.safetensors (NE JAMAIS MODIFIER)
VAE           : taesdxl permanent
Sampler       : dpmpp_2m/karras (pipeline) — euler_ancestral/normal (test AnimateDiff uniquement)
Résolution    : 1024x1536 (single character full body) / 1024x1280 (handsegnet) / 1024x1024 (facesegnet)
Steps         : 40 / CFG 6.5 (workflow test) — 25 steps / denoise 0.45 / CFG 6.0 (inpaint)
Seeds         : base + i*137 (ADR-008), bases par dataset : foot=?, hand=515151, face=616161, body=717171
ControlNet    : OpenPose rank256 1.25 + Lineart xinsir 1.25 (start 0.0 / end 0.50)
IPA           : ip-adapter-plus_sdxl_vit-h, weight 0.70, pad
AnimateDiff   : ADE_AnimateDiffLoaderGen1 OBLIGATOIRE (Gen2 indisponible), mm_sdxl_v10_beta
Masques       : NOIR=régénérer, BLANC=préserver (pipeline) / BLANC=objet (dataset ML) — deux conventions, ne pas mélanger
RGBA          : composer sur fond blanc avant SAMPreprocessor
```

## 8. RÈGLES ABSOLUES (inchangées + ajouts)

```
1.  py -3.12 TOUJOURS
2.  create_file UNIQUEMENT pour livraison
3.  ast.parse() AVANT toute livraison Python
4.  patcher.py FORMAT A
5.  "Ov3rLoRd" toujours
6.  taesdxl permanent / fabricatedXL_v70 NE JAMAIS MODIFIER / Combined_V35_API.json NE PAS RECRÉER
7.  agent_supervisor_v2.py : racine + agents/
8.  NoobAI exclu (commercial) / EVA-01 exclu / single character
9.  Workflow pipeline ≠ workflow test
10. Validation explicite avant chaque implémentation
11. Prompts LLM en anglais (ADR-006), logs/UI en français
12. shutil.copy2 jamais rename (ADR-007)
13. NOUVELLES : designs protégés (Nike, Games Workshop...) = démo interne UNIQUEMENT, jamais publié/monétisé
14. Flag non-commercial MusicGen propagé jusqu'au publisher (ADR-012)
15. Modèle Claude Code choisi EN DÉBUT de session (cache)
```

## 9. CHEMINS SYSTÈME (ajouts)

```
Racine           : D:\OVERLORD\          ComfyUI : D:\Ov3rLoRd AI\ComfyUI\ (port 8188)
SegNets          : D:\OVERLORD\{footsegnet,handsegnet,facesegnet,bodysegnet}\
Config LLM       : D:\OVERLORD\config\llm_endpoints.json
Ollama           : http://127.0.0.1:11434 (RTX 2070 par UUID)
Lanceurs         : launch_claude.bat / launch_ollama.bat / schedule_training.bat (racine)
Logs training    : D:\OVERLORD\workspace\logs\training\
GitHub           : github.com/g915tlk-design/OVERLORD (gh CLI authentifié)
```

## 10. PROCHAINES ÉTAPES (ordre)

```
1. IMMÉDIAT   : Annotation FootSegNet 250 images restantes (stylet Huion, ~7 jours au rythme constaté)
2. IMMÉDIAT   : Installer RTX 5060 Ti (remplace 2070) quand 2 minutes — mettre à jour l'UUID dans launch_ollama.bat après install
3. COURT      : build_coco.py --val-ratio 0.1 → schedule_training.bat overnight (surveiller crashs TDR)
4. COURT      : Évaluer IoU vs SAM base → si concluant : carte HF + post r/comfyui + Ko-fi → PUBLICATION FootSegNet
5. COURT      : Audit CLAUDE.md + optimisations tokens (section 5)
6. COURT      : blender-mcp (install triviale, gain immédiat)
7. MOYEN      : Matanyone + Frame-Interpolation + SeedVR2 dans le pipeline
8. MOYEN      : Annotation HandSegNet → même cycle
9. MOYEN      : Benchmark AniSora V3.2 12GB vs AnimateDiff sur Asuka Run
10. RECHERCHE : DesignLock proof of concept (LoRA Jordan AJ1, interne) + déstructuration-redessin
11. FUTUR     : trend_scout.py, ComfyUI-MCP, module timing anime, Unity manette (post-démo)
```

---

*Ov3rLoRd V2.29*
*"Le judoka ne bat pas le sumo — il joue un autre sport."*
*Généré le 2026-07-07 — 50/300 annotations FootSegNet, l'infrastructure est prête, le moteur est démarré.*

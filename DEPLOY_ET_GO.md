# DEPLOY & GO — Ov3rLoRd V1.70
## Un document, tout ce qu'il faut, dans l'ordre

---

## ÉTAPE 1 — Télécharger ces fichiers (navigateur Chrome)

### Modèles manquants (priorité absolue)

```
VAE (corrompu — RE-DL obligatoire) :
https://huggingface.co/stabilityai/sdxl-vae/blob/main/sdxl_vae.safetensors
→ D:\Ov3rLoRd AI\ComfyUI\models\vae\SDXL\sdxl_vae.safetensors

LoRa Gundam :
https://civitai.com/models/780308
→ D:\Ov3rLoRd AI\ComfyUI\models\loras\

LoRa Hatsune Miku :
https://civitai.com/models/647830
→ D:\Ov3rLoRd AI\ComfyUI\models\loras\
```

### Détecteurs YOLO (pour les ADetailers)

```
Visages :
https://huggingface.co/Bingsu/adetailer/blob/main/face_yolov9c.pt
→ D:\Ov3rLoRd AI\ComfyUI\models\ultralytics\bbox\

Mains :
https://huggingface.co/Bingsu/adetailer/blob/main/hand_yolov9c.pt
→ D:\Ov3rLoRd AI\ComfyUI\models\ultralytics\bbox\

Yeux :
https://civitai.com/models/178518
→ D:\Ov3rLoRd AI\ComfyUI\models\ultralytics\bbox\

Corps :
https://docs.ultralytics.com/models/yolo11/#segmentation-coco  (yolo11m-seg.pt)
→ D:\Ov3rLoRd AI\ComfyUI\models\ultralytics\segm\
```

### Upscaler

```
https://huggingface.co/FacehugmanIII/4x_foolhardy_Remacri
→ D:\Ov3rLoRd AI\ComfyUI\models\upscale_models\4x_foolhardy_Remacri.pth
```

### SAM (déjà présent normalement, vérifier)

```
https://github.com/facebookresearch/segment-anything#model-checkpoints  (sam_vit_b)
→ D:\Ov3rLoRd AI\ComfyUI\models\sams\sam_vit_b_01ec64.pth
```

---

## ÉTAPE 2 — Extraire le pack

```
OVERLORD_V170_DEPLOY.zip
→ Extraire dans D:\OVERLORD\
→ Écraser tous les fichiers existants
```

---

## ÉTAPE 3 — Vérifier la structure

```
D:\OVERLORD\
├── maestro.py
├── agent_supervisor_v2.py
├── overlord_launcher.py
├── overlord_auditor.py
├── api_server.py
├── ov_design_system.py
├── workflow_controller.py     ← NOUVEAU
├── demo_pipeline.py
├── migrate_v200.py
├── install.bat
├── Combined_V35_API.json
├── Advanced_QwenVL_V35.json   ← TES FICHIERS (à copier ici)
├── Detailer_V35.json          ← TES FICHIERS (à copier ici)
├── .env                       ← À créer (voir étape 4)
└── agents\
    ├── scenario.py
    ├── overlord_utils.py
    ├── postprod.py
    ├── config_manager.py
    ├── agent_registry.py
    ├── gpu_optimizer.py
    ├── style_continuity.py
    ├── narrative_memory.py
    ├── quality_gate.py
    ├── quality_reviewer.py
    ├── quality_reviewer_visual.py
    ├── prompt_engineer.py
    ├── session_reporter.py
    ├── auto_sourcing.py
    ├── grok_client.py
    ├── prompt_library.py
    ├── agent_overclock.py
    ├── dream_mode.py
    ├── transmedia_publisher.py
    ├── lora_trainer.py
    ├── character_designer.py
    ├── episode_planner.py
    ├── agent_translator.py
    ├── resource_scheduler.py
    ├── kaizen_analyzer.py
    ├── sakuga_compositor.py
    ├── slack_monitor.py
    ├── motion_interpolator.py
    ├── intent_parser.py
    ├── market_analyzer.py
    ├── self_optimizer.py
    ├── region_mask_generator.py
    └── workflow_controller.py
```

---

## ÉTAPE 4 — Créer le fichier .env

Créer `D:\OVERLORD\.env` avec ce contenu :

```
ANTHROPIC_API_KEY=
OV_LLM_MODE=offline
OV_OLLAMA_MODEL=mistral
GROK_API_KEY=
TELEGRAM_TOKEN=
TELEGRAM_CHAT_ID=
```

---

## ÉTAPE 5 — Console (cmd en admin dans D:\OVERLORD\)

Copier-coller dans l'ordre :

```batch
:: 1. Dépendances Python
pip install requests flask psutil Pillow numpy gTTS pydub --quiet

:: 2. Vérifier Ollama
ollama pull mistral

:: 3. Créer la structure workspace
mkdir workspace\logs workspace\scripts workspace\storyboards
mkdir workspace\checkpoints workspace\archive workspace\narrative
mkdir workspace\registry\manifests workspace\registry\snapshots
mkdir workspace\reports workspace\backups workspace\postprod
mkdir workspace\exports workspace\masks workspace\demo
mkdir workspace\publish workspace\market workspace\sakuga
mkdir workspace\self_optimizer\patches workspace\self_optimizer\applied
mkdir data\prompts ui

:: 4. Détecter la RTX 5080 et patcher le workflow
python agents\gpu_optimizer.py

:: 5. Initialiser la config centralisée
python agents\config_manager.py

:: 6. Initialiser les fiches personnages (Asuka/Rei/Mari)
python agents\character_designer.py --init

:: 7. Initialiser la bibliothèque de prompts
python agents\prompt_library.py

:: 8. Scanner et snapshoter tous les agents
python agents\agent_registry.py

:: 9. Audit rapide (doit donner 100/100)
python overlord_auditor.py --quick

:: 10. Tests rapides
python test_suite_v170.py --quick
```

---

## ÉTAPE 6 — Vérifier ComfyUI

```batch
:: Démarrer ComfyUI (dans son propre terminal)
D:\Ov3rLoRd AI\ComfyUI\run_nvidia_gpu.bat

:: Vérifier que l'API répond
python agents\workflow_controller.py --status
:: Résultat attendu : ComfyUI : EN LIGNE | Queue : 0 job(s)
```

---

## ÉTAPE 7 — Premier run RTX 5080

```batch
:: Run de validation — Evangelion
python maestro.py --media-type anime --universe "evangelion battle mecha girl"

:: Regarder les logs — attendu :
:: [GPU] rtx5080 détecté
:: [SUPERVISOR] Batch complete : 8/8 successes
:: [REPORTER] Rapport généré
```

---

## ÉTAPE 8 — HUD et interfaces (optionnel, dans des terminaux séparés)

```batch
:: Terminal 1 — HUD web (http://localhost:5757)
pip install flask
python api_server.py

:: Terminal 2 — Launcher visuel
python overlord_launcher.py

:: Terminal 3 — Intent parser interactif (tester la compréhension naturelle)
python agents\intent_parser.py --interactive
```

---

## ÉTAPE 9 — Plan de la démo (lire avant de produire)

```batch
:: Voir le plan complet de la démo 2 minutes
python demo_pipeline.py --plan

:: Générer les prompts de la scène 1 (Evangelion)
python demo_pipeline.py --scene 1

:: Plan Sakuga pour la scène Evangelion
python agents\sakuga_compositor.py --demo
```

---

## ÉTAPE 10 — Mode nuit (lancer le soir)

```batch
:: Production autonome jusqu'à 8h du matin
python agents\dream_mode.py --stop-at 08:00 --cooldown 60
```

---

## COMMANDES DE RÉFÉRENCE RAPIDE

```batch
:: Audit
python overlord_auditor.py --quick
python overlord_auditor.py --gui

:: Runs
python maestro.py --universe "evangelion battle mecha"
python maestro.py --universe "evangelion" --use-prompt-library
python maestro.py --universe "evangelion" --batch 3
python maestro.py --plan-series "Evangelion: New Saga" --series-episodes 12

:: Intent naturel
python agents\intent_parser.py --parse "je veux quelque chose d epique comme Rubilax"

:: Workflow ComfyUI
python agents\workflow_controller.py --list-passes
python agents\workflow_controller.py --status
python agents\workflow_controller.py --pass background --positive "tokyo-3 cityscape"

:: Masques régionaux
python agents\region_mask_generator.py --layout character_center
python agents\region_mask_generator.py --zone eyes --width 1024 --height 1536

:: Analyse
python agents\kaizen_analyzer.py
python agents\self_optimizer.py
python agents\slack_monitor.py
python agents\market_analyzer.py --opportunities

:: Traducteur
python agents\agent_translator.py --glossary
python agents\agent_translator.py --booru "fille combat epique fond detruit"

:: Monitoring hardware
python agents\agent_overclock.py --profile turbo --comfyui
```

---

## CHECKLIST RAPIDE — avant de revenir vers Claude

- [ ] sdxl_vae.safetensors téléchargé (~335MB)
- [ ] LoRa Gundam téléchargée
- [ ] LoRa Hatsune Miku téléchargée
- [ ] Détecteurs YOLO copiés (face, hand, eyes, body)
- [ ] Pack extrait dans D:\OVERLORD\
- [ ] Advanced_QwenVL_V35.json copié à la racine D:\OVERLORD\
- [ ] Detailer_V35.json copié à la racine D:\OVERLORD\
- [ ] .env créé
- [ ] `pip install` OK
- [ ] `python overlord_auditor.py --quick` → 100/100
- [ ] `python test_suite_v170.py --quick` → tous PASS
- [ ] `python agents\workflow_controller.py --status` → EN LIGNE
- [ ] Premier run maestro.py → 8/8 images

---

## EN CAS DE PROBLÈME

| Symptôme | Solution |
|----------|----------|
| `ComfyUI HORS LIGNE` | Lancer `run_nvidia_gpu.bat` d'abord |
| `400 Bad Request ComfyUI` | `python agents\quality_gate.py` → auto-fix |
| `VAE error shape invalid` | sdxl_vae corrompu → utiliser taesdxl temporairement |
| `LoRa introuvable` | Vérifier nom exact dans `D:\Ov3rLoRd AI\ComfyUI\models\loras\` |
| `JSON invalide LLM` | Normal, retry automatique. Si persistant : `OV_LLM_MODE=grok` |
| Tests échouent | `python overlord_auditor.py --verbose` pour le détail |

---

*Ov3rLoRd V1.70 — — L'usine est prête.*

---

## BONUS — Analyse vidéo de référence (rotoscoping assisté)

```batch
:: Extraire le storyboard depuis une vidéo existante
python agentsideo_analyzer.py --video ma_reference.mp4

:: Avec analyse LLM (génère les prompts ComfyUI automatiquement)
python agentsideo_analyzer.py --video ma_reference.mp4 --analyze

:: Extraire les keyframes pour OpenPose
python agentsideo_analyzer.py --video ma_reference.mp4 --extract-keyframes

:: Extraire toutes les frames pour entraîner un LoRA de style
python agentsideo_analyzer.py --video ma_reference.mp4 --full-fps
```

Résultat : workspace/video_analysis/{nom}_storyboard.json
→ Prêt à injecter dans le pipeline Ov3rLoRd

---

## NOUVEAUX AGENTS — Phase 0 + Post-prod

```batch
:: Générer toutes les palettes couleur anime
python agentsnime_palette_generator.py --generate-all
:: → workspace/palettes/ + D:\ComfyUI\models\colors
:: Lister les palettes disponibles
python agentsnime_palette_generator.py --list

:: Suggérer une palette pour un univers
python agentsnime_palette_generator.py --suggest "evangelion battle"

:: Nettoyer sources manga
python agents\source_cleaner.py --input manga\ --type manga --batch

:: Nettoyer sources vidéo (décomposition couches)
python agents\source_cleaner.py --input sources\ --scan

:: Analyse vidéo de référence + storyboard
python agentsideo_analyzer.py --video reference.mp4 --analyze

:: Transitions entre scènes
python agents	ransition_builder.py --list-types
python agents	ransition_builder.py --montage workspace\scenes\ --output final.mp4

:: Plan audio démo
python agentsudio_compositor.py --plan

:: Mixer voix Blue Yeti + musique
python agentsudio_compositor.py --mix --voice voice.wav --music bgm.mp3

:: Ajouter audio à vidéo finale
python agentsudio_compositor.py --video montage.mp4 --voice voice.wav --output final_audio.mp4
```

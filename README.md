# Ov3rLoRd Pipeline V1.70 — Pack de Déploiement
## Onibaku Gumi — AI Anime Production

**Date :** 20/06/2026  
**Statut :** Prêt au déploiement post-RTX 5080

---

## DÉPLOIEMENT RAPIDE

```
1. Copier tout le contenu de ce dossier dans D:\OVERLORD\
   (écraser les fichiers existants)

2. Renommer .env.template en .env et remplir vos clés API

3. En tant qu'administrateur :
   install.bat

4. Premier run :
   python maestro.py --universe "evangelion battle mecha girl"

5. HUD web (optionnel) :
   pip install flask
   python api_server.py
   → http://localhost:5757
```

---

## CONTENU DU PACK

### Racine D:\OVERLORD\
| Fichier | Rôle |
|---------|------|
| `maestro.py` | Chef d'orchestre V1.70 (1013 lignes) |
| `agent_supervisor_v2.py` | Supervisor ComfyUI + Quality Reviewer |
| `overlord_launcher.py` | GUI tkinter — boutons configurables |
| `api_server.py` | HUD web Flask — pilotage distant |
| `test_suite_v170.py` | 29 tests unitaires |
| `Combined_V35_API.json` | Workflow ComfyUI patché V1.50 |
| `patch_workflow_v35.py` | Script de patch workflow |
| `install.bat` | Installation complète |
| `.env.template` | Template configuration |
| `requirements.txt` | Dépendances Python |

### agents/
| Agent | Rôle | Version |
|-------|------|---------|
| `overlord_utils.py` | Utilitaires LLM centraux | V1.70 |
| `scenario.py` | Scénariste + retry + fallback | V1.70 |
| `postprod.py` | Post-production vidéo | V1.70 |
| `config_manager.py` | Config SQLite centralisée | V1.70 NEW |
| `agent_registry.py` | Versioning + manifest + rollback | V1.70 NEW |
| `gpu_optimizer.py` | Preset GPU adaptatif (2070→5090) | V1.70 NEW |
| `style_continuity.py` | Cohérence visuelle inter-frames | V1.70 NEW |
| `narrative_memory.py` | Mémoire personnages inter-épisodes | V1.70 NEW |
| `quality_gate.py` | Validation workflow JSON | V1.60 |
| `quality_reviewer.py` | Jury 4 critères pondérés | V1.70 NEW |
| `prompt_engineer.py` | Upsampling Booru + LoRa intelligente | V1.60 |
| `session_reporter.py` | Rapport JSON+MD fin de run | V1.60 |
| `auto_sourcing.py` | Sourcing autonome en boucle | V1.60 |
| `grok_client.py` | Client Grok 4 Fast xAI | V1.60 |
| `prompt_library.py` | Bibliothèque prompts Booru locaux | V1.60 |
| `agent_overclock.py` | Monitoring hardware + profils perf | V1.70 NEW |
| `dream_mode.py` | Production autonome nuit | V1.70 NEW |
| `transmedia_publisher.py` | Export YouTube/TikTok/Instagram | V1.70 NEW |
| `lora_trainer.py` | Entraînement LoRa autonome (V2.0) | V1.70 NEW |
| `schema_validator.py` | Validation schéma JSON | V1.60 |

### ui/
| Fichier | Rôle |
|---------|------|
| `live_monitor.html` | HUD web temps réel (servi par api_server.py) |

### Documentation
| Fichier | Contenu |
|---------|---------|
| `CONTEXTE_OVERLORD_V170.md` | **LIRE EN PREMIER** — reprise session |
| `GUIDE_UTILISATEUR_V170.md` | Manuel complet toutes commandes |
| `CHECKLIST_PREPARATION_V170.md` | To-do list ordonnée post-install |
| `ADR_OVERLORD.md` | Pourquoi chaque décision architecturale |
| `ARCHITECTURE_GANTT_PERT_5S.md` | Gantt/PERT/5S + analyse performance |
| `ROADMAP_V200.md` | Plan 6 sprints vers V2.0 |
| `EVALUATION_V160.md` | Évaluation prompt engineering (91/100) |

---

## COMMANDES ESSENTIELLES

```bash
# Installation complète
install.bat

# Tests
python test_suite_v170.py --quick
python test_suite_v170.py

# Run standard
python maestro.py --universe "evangelion battle mecha girl"

# HUD visuel
python overlord_launcher.py

# HUD web (accès distant)
python api_server.py
# → http://VOTRE_IP:5757

# Mode nuit autonome
python agents\dream_mode.py --stop-at 08:00

# Monitoring hardware
python agents\agent_overclock.py --profile turbo

# Pub transmedia
python agents\transmedia_publisher.py --platforms youtube tiktok
```

---

*Ov3rLoRd V1.70 — Onibaku Gumi 鬼爆組*  
*"L'usine pense. L'usine apprend. L'usine publie."*

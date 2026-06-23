# ROADMAP V2.0 — Ov3rLoRd Pipeline
## Plan technique complet — Sprints et livrables

**Vision V2.0 :** Production anime IA autonome à 90% de cohérence.
**Horizon :** 6-8 semaines après stabilisation V1.70.

---

## SPRINT 1 — Stabilisation V1.70 (Semaine 1)

**Objectif :** Tout ce qui est livré tourne sans erreur sur la RTX 5080.

| Tâche | Fichier | Priorité |
|-------|---------|----------|
| Déployer V1.70 complet | Tous les fichiers livrés | P0 |
| Tester post-RTX 5080 | `python test_suite_v170.py` | P0 |
| Valider GPU auto-detect | `python agents/gpu_optimizer.py` | P0 |
| Premier run complet V1.70 | `python maestro.py --universe "evangelion"` | P0 |
| Snapshot global initial | `agent_registry.snapshot_all()` | P1 |
| Lancer auto_sourcing | `--loop 3600` en arrière-plan | P1 |
| Configurer Grok 4 Fast | `.env GROK_API_KEY=...` | P2 |
| Re-DL sdxl_vae.safetensors | HuggingFace stabilityai | P2 |

**Livrable :** 8/8 images · score jury > 80 · rapport auto · HUD web actif

---

## SPRINT 2 — Quality Reviewer Rodage (Semaine 2)

**Objectif :** Atteindre 80% de taux de PASS sur le jury de qualité.

| Tâche | Description |
|-------|-------------|
| Analyser les logs quality_reviews.jsonl | Identifier les critères qui échouent le plus |
| Ajuster les poids WEIGHTS si nécessaire | Ex: sharpness 30% → 25% si taesdxl trop pénalisant |
| Tester `suggest_adjustment()` en conditions réelles | Observer les prompts ajustés après refus |
| Calibrer le seuil | 80 → 85 si le taux de PASS > 70% sur 50 runs |
| Intégrer score_prompt_match avec image réelle | Activer PIL + numpy pour analyse pixel |

**Livrable :** Journal de calibration + poids optimaux documentés dans ADR

---

## SPRINT 3 — Architecture V2.0 Core (Semaines 3-4)

**Objectif :** Restructuration dossiers + quality_reviewer en boucle serrée.

### 3.1 Restructuration dossiers (Seiri + Seiton)

```bash
# Script de migration
python scripts/migrate_v200.py
# Crée core/ pipeline/ intelligence/ production/ infra/ ui/ tests/
# Déplace les fichiers, met à jour les imports
# Garde l'ancien layout en backup
```

### 3.2 Boucle de validation serrée

```python
# Dans agent_supervisor_v2.py V2.0
# Boucle : generate → review → adjust → regenerate
for attempt in range(MAX_RETRIES):
    image = comfyui.generate(job)
    review = reviewer.evaluate(image, job)
    if review["score"] >= TARGET_SCORE:
        archive(image)
        break
    job = reviewer.suggest_adjustment(review, job)
    log_retry(attempt, review)
archive(best_attempt)  # même si aucun PASS
```

### 3.3 Nouveaux agents V2.0

| Agent | Rôle | Complexité |
|-------|------|------------|
| `transmedia_publisher.py` | Export YouTube/TikTok/Insta | Moyenne |
| `lora_trainer.py` | Entraînement LoRa via kohya_ss | Haute |
| `character_designer.py` | Génération fiche personnage cohérente | Moyenne |
| `episode_planner.py` | Planning d'une série (10 épisodes) | Haute |
| `market_analyzer.py` | Agent Stratège CSO | Haute |

---

## SPRINT 4 — Entraînement LoRa Autonome (Semaines 5-6)

**Objectif :** L'IA génère ses propres LoRas depuis les images produites.

### Pipeline LoRa autonome

```
[Sélection images] → [Tagger automatique] → [Kohya SS CLI] → [Validation] → [Intégration]
     ↓                      ↓                     ↓                ↓              ↓
workspace/archive/  WD14 tagger auto     kohya_ss/train.py   quality gate   AVAILABLE_LORAS
(meilleurs runs)   génère .txt tags     ~2-4h RTX 5080      score > 85     mise à jour
```

### Fichier cible : `agents/lora_trainer.py`

```python
class LoraTrainer:
    def prepare_dataset(self, image_dir, n_images=50) -> Path
    def tag_images(self, dataset_dir) -> int  # WD14 tagger
    def train(self, dataset_dir, trigger_word, steps=1500) -> Path
    def validate(self, lora_path) -> float  # score qualité
    def integrate(self, lora_path, name)  # ajoute à AVAILABLE_LORAS
```

**Prérequis :**
- kohya_ss installé : `git clone https://github.com/bmaltais/kohya_ss`
- WD14 tagger : `pip install wd14-tagger` ou API CivitAI
- Dataset minimal : 30-50 images de haute qualité par LoRa

---

## SPRINT 5 — Multi-GPU (Semaine 7)

**Objectif :** RTX 5080 (génération) + RTX 2070 (post-processing/upscale).

```python
# Dans gpu_optimizer.py V2.0
GPU_TOPOLOGY = {
    "primary":   {"id": 0, "role": "generation",    "model": "rtx5080"},
    "secondary": {"id": 1, "role": "postprocessing", "model": "rtx2070"},
}
# ComfyUI sur cuda:0 (5080) — génération principale
# Upscaler / Real-ESRGAN sur cuda:1 (2070) — post-production parallèle
```

---

## SPRINT 6 — Publication & Branding (Semaine 8)

**Objectif :** Onibaku Gumi visible sur les réseaux.

### transmedia_publisher.py

```python
class TransmediaPublisher:
    def export_youtube(self, video_path, title, description, tags) -> str
    def export_tiktok(self, clips: list, music_path=None) -> list
    def export_instagram(self, images: list, caption: str) -> list
    def generate_thumbnail(self, image_path, title: str) -> Path
    def create_reel(self, images: list, duration_s=30) -> Path
```

**Stratégie de contenu automatique :**
- Dream mode la nuit → 8-16 épisodes produits
- Matin : sélection automatique des meilleures images (score > 85)
- Publication automatique avec captions générées par Grok
- Hashtags dynamiques depuis auto_sourcing.keywords

---

## MÉTRIQUES CIBLES V2.0

| Métrique | V1.70 actuel | Cible V2.0 |
|----------|-------------|------------|
| Cohérence visuelle | ~60-70% | **90%** |
| Taux PASS jury | Non mesuré | **80%+** |
| Temps par run | ~580s | **~300s (5080)** |
| Images/nuit (dream) | 0 (non déployé) | **48-80** |
| LoRas disponibles | 3 (manuelles) | **10+ (auto-générées)** |
| Univers en bibliothèque | Variable | **500+ prompts** |

---

## RISQUES ET MITIGATIONS

| Risque | Probabilité | Mitigation |
|--------|-------------|------------|
| sdxl_vae corrompu après re-DL | Faible | Vérifier checksum SHA256 |
| Kohya SS incompatible CUDA 12+ | Moyenne | Tester sur branche stable |
| RAM insuffisante pour lora_trainer | Moyenne | 32GB DDR4 limite à batch_size=1 |
| API Grok rate limit | Faible | Fallback Ollama automatique |
| Ruptures style > 3 par run | Moyenne | Calibrer WEIGHTS quality_reviewer |

---

## COMMANDES V2.0 CIBLES

```bash
# Run standard V2.0
python maestro.py --universe "evangelion" --use-prompt-library

# Mode nuit (8h de production)
python agents/dream_mode.py --stop-at 08:00 --cooldown 60

# Entraîner une nouvelle LoRa depuis les meilleures images
python agents/lora_trainer.py --trigger "onibaku_style" --steps 1500

# Publier les résultats
python agents/transmedia_publisher.py --platform tiktok --runs-dir workspace/archive/

# HUD distant
python api_server.py --host 0.0.0.0 --port 5757
# → http://IP_MACHINE:5757 depuis n'importe quel appareil
```

---

*Roadmap générée le 20/06/2026 — Session Claude Sonnet 4.6*
*"L'usine pense. L'usine apprend. L'usine publie."*

---

## HORS-SÉRIE — Projets Parallèles Onibaku Gumi

### OPP-LIVRE — "Ov3rLoRd Was Here" — Le Livre
**Format :** Interview IA × Humain → livre édité
**Concept :** Claude interviewe Jérémy Gourlain sur la création d'Ov3rLoRd.
L'IA structure, rédige, met en forme. L'humain valide et signe.
Un format qui n'a pas encore été fait avec la bonne histoire.
**Timing :** Après Japan Expo 2026 — la matière sera suffisante.
**Audience :** Jeunes créateurs cherchant un modèle hors sentier balisé.
**Production :** 1 session longue d'interview + 2-3 sessions d'édition.
**Note :** "Ov3rLoRd Was Here" — déjà gravé sur une poutre des docks du Havre.
C'est le titre.

### OPP-ANTHROPIC — Présentation Ov3rLoRd
**Action :** Envoyer une présentation simple d'Ov3rLoRd à Anthropic.
Pas un pitch commercial — une démonstration d'usage avancé.
Pipeline 61 fichiers, 5 jours, méthode industrielle × IA créative.
**Canal :** Page contact professionnelle Anthropic + potentiel programme utilisateurs avancés.

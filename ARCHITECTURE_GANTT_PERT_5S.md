# ARCHITECTURE MULTI-AGENTS — Gantt / PERT / 5S
## Ov3rLoRd V1.70 → V2.0 — Méthodologie de Production IA

---

## 1. CONTEXTE STRATÉGIQUE

**Objectif :** 90% de cohérence entre chaque frame/planche/asset.
**Principe :** Une armée d'agents spécialisés, chacun focalisé sur une tâche précise, plutôt qu'un système généraliste qui fait tout à moitié.
**Contrainte temps :** Pas un problème. 60s → 120s par cycle si le résultat est cohérent à 90%. Ajustement continu du ratio.

---

## 2. DIAGRAMME DE GANTT — Pipeline de Production

Le Gantt Ov3rLoRd modélise les tâches séquentielles ET parallèles du pipeline.

```
PHASE           AGENT(S)                    T0    T1    T2    T3    T4    T5    T6
─────────────────────────────────────────────────────────────────────────────────
SOURCING        auto_sourcing (continu)     [====================================]
                sourcing.py (par run)       [===]
                
SCÉNARIO        scenario.py                       [====]
                narrative_memory (contexte) [----][====]
                
STORYBOARD      storyboard.py                           [====]
                style_continuity (ancre)                [====]
                
VALIDATION      quality_gate.py                               [=]
                
PROMPT ENG.     prompt_engineer.py × 8                        [===]
                (8 jobs en parallèle possible)
                
PRODUCTION      ComfyUI × 8 jobs                                   [============]
                (séquentiel RTX 2070, parallèle RTX 5080+)
                
CONTRÔLE        watchdog (continu)          [====================================]
                critic (aux transitions)    [-]   [-]   [-]         [-]
                quality_reviewer (NEW)                               [-][-][-]
                
POST-PROD       postprod.py                                               [====]
                
RAPPORT         session_reporter.py                                            [=]
─────────────────────────────────────────────────────────────────────────────────
[===] = actif    [---] = en attente    T0-T6 = ~2min chacun (RTX 2070, 50 steps)
```

**Durée totale actuelle :** ~580-600s (RTX 2070)
**Durée cible RTX 5080 :** ~300-350s (80 steps, même nombre d'agents)

---

## 3. DIAGRAMME PERT — Chemin Critique

Le PERT identifie les dépendances et le **chemin critique** (tâches qui bloquent tout si elles prennent du retard).

```
          ┌─────────────┐
          │  SOURCING   │ t=30s
          └──────┬──────┘
                 │
          ┌──────▼──────┐
          │  SCÉNARIO   │ t=40s  ◄── CHEMIN CRITIQUE
          └──────┬──────┘
                 │
          ┌──────▼──────┐         ┌─────────────────┐
          │ STORYBOARD  │ t=30s   │ STYLE ANCHOR    │ t=5s (parallèle)
          └──────┬──────┘         └────────┬────────┘
                 │                         │
          ┌──────▼─────────────────────────▼──────┐
          │         PROMPT ENGINEER × 8           │ t=60s (8 × 7s)
          └──────────────────┬────────────────────┘
                             │
          ┌──────────────────▼────────────────────┐
          │      PRODUCTION COMFYUI × 8 jobs      │ t=360s ◄── GOULOT
          └──────────────────┬────────────────────┘
                             │
                    ┌────────▼────────┐
                    │  POST-PROD      │ t=30s
                    └────────┬────────┘
                             │
                    ┌────────▼────────┐
                    │   REPORTER      │ t=5s
                    └─────────────────┘

CHEMIN CRITIQUE : Scénario → Storyboard → Prompt Eng → Production → Post-prod
GOULOT D'ÉTRANGLEMENT : Production ComfyUI (60% du temps total)
SOLUTION : Multi-GPU ou augmenter steps (qualité) plutôt que nombre de jobs
```

---

## 4. NOUVELLE ARCHITECTURE MULTI-AGENTS (Cible V2.0)

Basée sur ton insight : **agents spécialisés + boucle de validation par consensus**.

```
┌─────────────────────────────────────────────────────────────────────┐
│                    CHEF D'ORCHESTRE                                  │
│  maestro.py + director.py + narrative_memory.py                     │
│  → Définit l'intention, le style, la continuité                     │
└───────────────────────────────┬─────────────────────────────────────┘
                                │
        ┌───────────────────────┼───────────────────────┐
        │                       │                       │
┌───────▼──────┐       ┌────────▼──────┐      ┌────────▼──────┐
│  NARRATEUR   │       │  STORYBOARDER │      │  CONCORDANCE  │
│ scenario.py  │       │storyboard.py  │      │ ARTISTIQUE    │
│              │──────►│               │─────►│ style_cont.py │
│ Génère le    │       │ Traduit en    │      │ + quality_gate│
│ script       │       │ 8 shots       │      │               │
└──────────────┘       └───────────────┘      └───────┬───────┘
                                                       │ VALIDE
                                               ┌───────▼───────┐
                                               │  PROMPT ENG.  │
                                               │prompt_eng.py  │
                                               │               │
                                               │ Upsampling    │
                                               │ Booru + LoRa  │
                                               └───────┬───────┘
                                                       │
                                               ┌───────▼───────┐
                                               │  DESSINATEUR  │
                                               │ ComfyUI       │
                                               │ supervisor    │
                                               └───────┬───────┘
                                                       │
        ┌──────────────────────────────────────────────▼──────┐
        │              JURY DE QUALITÉ (NEW V2.0)             │
        │  watchdog + critic + quality_reviewer + style_cont  │
        │                                                      │
        │  Score global = moyenne pondérée :                   │
        │  - Netteté (watchdog)          : 30%                 │
        │  - Cohérence style (style)     : 30%                 │
        │  - Concordance prompt (critic) : 25%                 │
        │  - Narratif (director)         : 15%                 │
        │                                                      │
        │  SI score < 90% → REFUS → retour au Dessinateur     │
        │  SI score ≥ 90% → ACCEPTÉ → Post-production         │
        └─────────────────────────────────────────────────────┘
```

**Le principe des 10% :** 
- 10% du temps = refus et reprise immédiate (boucle courte)
- 90% du temps = production acceptée et passage à la suite
- Cible : jamais plus de 3 tentatives par shot

---

## 5. APPLICATION DES 5S JAPONAIS

Les 5S (Seiri, Seiton, Seiso, Seiketsu, Shitsuke) appliqués à l'architecture agents.

### Seiri (整理) — Trier : Éliminer ce qui est inutile

**État actuel :** 95+ fichiers Python dont certains sont des doublons ou dead code.
```
À ÉLIMINER (V2.0) :
- v130_pipeline_api.py     → doublon de api_server.py
- v130_dashboard.py        → remplacé par overlord_launcher.py
- v130_cocreation.py       → non connecté, fonctionnalité floue
- agents/__pycache__/      → à gitignore

À FUSIONNER :
- narrative_dna.py + narrative_memory.py → un seul agent cohérent
- agent_supervisor_v2.py → à terme dans agents/ proprement
```

**Action :** `agent_registry.py scan()` révèle les agents jamais importés = candidats à l'élimination.

### Seiton (整頓) — Ranger : Une place pour chaque chose

**Structure cible V2.0 :**
```
D:\OVERLORD\
├── core/                    ← Agents fondamentaux (director, critic, watchdog)
│   ├── director.py
│   ├── critic.py
│   ├── watchdog.py
│   ├── context_bus.py
│   └── config_manager.py
│
├── pipeline/                ← Blocs du pipeline
│   ├── sourcing.py
│   ├── scenario.py
│   ├── storyboard.py
│   ├── prompt_engineer.py
│   ├── quality_gate.py
│   └── postprod.py
│
├── intelligence/            ← Agents "cerveau"
│   ├── narrative_memory.py
│   ├── style_continuity.py
│   ├── auto_sourcing.py
│   └── prompt_library.py
│
├── production/              ← Agents de rendu
│   ├── agent_supervisor_v2.py
│   └── gpu_optimizer.py
│
├── infra/                   ← Infrastructure
│   ├── agent_registry.py
│   ├── session_reporter.py
│   ├── overlord_utils.py
│   └── grok_client.py
│
├── ui/                      ← Interfaces
│   ├── overlord_launcher.py
│   ├── api_server.py
│   ├── live_monitor.html
│   └── analytics_dashboard.html
│
├── tests/                   ← Tests
│   ├── test_suite_v170.py
│   └── test_pipeline.py
│
└── maestro.py               ← Chef d'orchestre (racine, toujours)
```

### Seiso (清掃) — Nettoyer : Maintenance régulière

**Agents de nettoyage automatique :**
- `quality_gate.py` → valide le workflow avant chaque run
- `agent_registry.py` → scan hebdomadaire, manifests à jour
- `session_reporter.py` → historique 50 runs, nettoie les anciens
- Log rotation : `workspace/logs/` → garder 30 jours

**Règle :** Chaque run laisse `workspace/archive/{run_id}/` propre et documenté.

### Seiketsu (清潔) — Standardiser : Mêmes règles partout

**Standards non négociables :**
```python
# 1. Tout agent = même structure d'import protégé
try:
    from agents.context_bus import get_bus
    BUS_OK = True
except ImportError:
    BUS_OK = False

# 2. Tout agent = logging cohérent
log = logging.getLogger("nom_agent")

# 3. Tout agent = publie sur le bus
bus.write("agent_name.key", value, agent_id="agent_name")

# 4. Tout agent = gère ses erreurs
try:
    result = do_something()
except Exception as e:
    log.error(f"[AGENT] Erreur : {e}")
    return fallback_value

# 5. Tout score = int
score = int(data.get("score_global", 0))
```

**Standardisation V2.0 :** Chaque agent doit avoir un manifest.json (agent_registry).

### Shitsuke (躾) — Maintenir : Discipline dans la durée

**Rituels de maintenance Ov3rLoRd :**
- **Avant chaque session dev :** `python test_suite_v170.py --quick`
- **Avant de modifier un agent critique :** `get_registry().snapshot("agent_name")`
- **Après session :** Mettre à jour CONTEXTE.md, push ADR si nouvelle décision
- **Hebdomadaire :** `get_registry().scan()` + `get_registry().snapshot_all()`
- **Mensuel :** Nettoyer `workspace/archive/` (garder 10 derniers runs)

---

## 6. SYSTÈME DE VALIDATION À 90% — Implémentation Cible

```python
# agents/quality_reviewer.py (à créer V2.0)
class QualityReviewer:
    """
    Jury multi-critères pour chaque image produite.
    Score global = moyenne pondérée.
    Seuil : 90 pour PASS, < 90 = REFUS + retry immédiat.
    """
    
    WEIGHTS = {
        "sharpness":    0.30,  # watchdog
        "style_drift":  0.30,  # style_continuity
        "prompt_match": 0.25,  # critic (concordance prompt/image)
        "narrative_fit": 0.15, # director (cohérence narrative)
    }
    
    MAX_RETRIES = 3  # jamais plus de 3 tentatives par shot
    TARGET_SCORE = 90.0
    
    def evaluate(self, image_path, job, anchor) -> dict:
        scores = {
            "sharpness":    self._score_sharpness(image_path),
            "style_drift":  self._score_style(image_path, anchor),
            "prompt_match": self._score_prompt_match(image_path, job),
            "narrative_fit": self._score_narrative(job),
        }
        global_score = sum(s * self.WEIGHTS[k] for k, s in scores.items())
        return {
            "score": global_score,
            "pass":  global_score >= self.TARGET_SCORE,
            "detail": scores,
        }
```

**Workflow de production avec boucle de validation :**
```
Pour chaque shot i de 1 à 8 :
  attempt = 0
  while attempt < 3 :
    image = comfyui.generate(job[i])
    review = quality_reviewer.evaluate(image, job[i], anchor)
    if review["pass"] :
      archive(image)
      break
    else :
      log "Refus shot {i} score={review['score']} — retry {attempt+1}/3"
      job[i] = prompt_engineer.adjust(job[i], review)  # Ajuster le prompt
      attempt += 1
  if attempt == 3 :
    log "Shot {i} : meilleure tentative conservée (score insuffisant)"
    archive(best_attempt)
```

---

## 7. ANALYSE PERFORMANCE — Pourquoi Job 1 = 54s vs Job 7 = 18s

**Observation V1.60 :** Les premiers jobs sont beaucoup plus lents que les suivants.

**Cause racine :**
```
Job 1 : ComfyUI charge tout depuis zéro
  - CheckpointLoader : 4-6s (chargement fabricatedXL_v70 en VRAM)
  - CLIPTextEncode   : 2-3s (chargement modèle CLIP)
  - VAE              : 1-2s (chargement taesdxl)
  - KSampler         : 38-42s (50 steps × ~0.8s/step RTX 2070)
  TOTAL : ~50-54s

Job 7 : Tout est déjà en VRAM
  - CheckpointLoader : ~0s (modèle en cache)
  - CLIPTextEncode   : ~0s (CLIP en cache)
  - VAE              : ~0s (taesdxl en cache)
  - KSampler         : 18-22s (50 steps × ~0.4s/step — GPU "chaud")
  TOTAL : ~18-22s
```

**Solutions :**
1. **Warm-up run :** Envoyer un prompt minimal avant le vrai batch pour charger les modèles en VRAM
2. **Persistance modèle :** ComfyUI `--lowvram` vs `--highvram` — forcer `--highvram` si 8GB suffisent
3. **Batch natif ComfyUI :** Envoyer tous les 8 jobs d'un coup (queue) plutôt que séquentiellement → meilleure utilisation GPU

**Optimisation VRAM RTX 2070 (8GB) :**
```
fabricatedXL_v70 : ~5.5GB
CLIP             : ~0.6GB
taesdxl          : ~0.05GB
OS + overhead    : ~0.8GB
TOTAL            : ~7GB / 8GB disponible → limite atteinte
→ Ne PAS charger plusieurs modèles simultanément
→ KSampler à 50 steps = optimal (plus = gain marginal)
```

**Avec RTX 5080 (16GB) :**
```
fabricatedXL_v70 : ~5.5GB
LoRa ×2          : ~0.4GB
CLIP             : ~0.6GB
sdxl_vae         : ~0.35GB
OS + overhead    : ~0.8GB
TOTAL            : ~7.65GB / 16GB → 8GB libres !
→ Possible : batch_size=2 (2 images simultanées)
→ Possible : upscaler Tile en post-prod
→ Possible : Flux.1 (10GB minimum)
```

---

## 8. RECOMMANDATIONS COACH — Tes AXES DE PROGRESSION

**Sur l'architecture :**
Ton instinct est juste sur les agents spécialisés. La clé que tu as identifiée — "un agent de concordance artistique qui valide avant le dessinateur" — c'est exactement le pattern Quality Gate + Critic combinés en boucle. L'implémentation cible est dans la section 6 ci-dessus.

**Sur le Gantt/PERT :**
Tu viens de l'industrie donc tu sais : le chemin critique en production c'est ComfyUI (60% du temps). Tout le reste optimisable à la marge. L'investissement en RTX 5080 divise ce chemin critique par 2-3×. C'est ton meilleur levier.

**Sur le 5S :**
Le Seiri (trier) est ton prochain chantier : agent_registry scan va te révéler 15-20 fichiers jamais importés nulle part. Élimine-les. Un pipeline à 70 agents bien connectés vaut mieux qu'un pipeline à 95 agents dont 25 sont fantômes.

**Sur la régularité 90% :**
Le ratio actuel en V1.70 est estimé à 60-70% (pas de quality_reviewer encore, seeds progressifs stabilisent le style mais prompt matching est non mesuré). La boucle de validation section 6 + quality_reviewer.py = l'agent qui te fera passer à 90%. C'est la prochaine priorité absolue après la 5080.


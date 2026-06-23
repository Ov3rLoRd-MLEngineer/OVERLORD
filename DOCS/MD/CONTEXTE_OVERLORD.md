# CONTEXTE_OVERLORD.md — Cerveau de Démarrage
## Document de référence pour reprise de développement
**Version courante :** V1.48 — La Reconnexion  
**Date de verrouillage :** 18/06/2026  
**Auteur :** Session Claude Sonnet 4.6 + Jérémy Gourlain (Ov3rLoRd)  
**Projet :** Ov3rLoRd Pipeline — Usine à animés automatisée par IA  

---

## 1. RÉSUMÉ EXÉCUTIF

Ov3rLoRd est un pipeline de production anime/manga entièrement automatisé.
Il prend en entrée un univers (ex : "Dragon Ball Super Broly") et produit
en sortie un épisode complet : script → storyboard → images ComfyUI → vidéo MP4
→ SRT → thumbnail → publication transmedia (YouTube/Reddit/Instagram).

**Stack technique :**
- Python 3.14 (Windows, D:\OVERLORD\)
- ComfyUI + Stable Diffusion XL (génération images)
- API Anthropic Claude (scénario, critique, optimisation)
- Ollama local (fallback LLM offline : llama3, mistral)
- ffmpeg (assemblage vidéo)
- Flask (API REST locale)
- ChromaDB + NetworkX (mémoire persistante)
- tkinter (launcher GUI)

**Chiffres V1.48 :**
- 89 fichiers Python | 5 .bat | 5 .html
- 45 234 lignes de code
- 0 erreur de syntaxe critique
- ~65 agents dans `agents/`

---

## 2. ARCHITECTURE

### 2.1 Structure des dossiers

```
D:\OVERLORD\
├── maestro.py              ← Chef d'orchestre principal (POINT D'ENTRÉE)
├── director.py             ← Réalisateur (V1.48 — nouveau)
├── oracle_interface.py     ← Interface CLI naturelle
├── overlord_launcher.py    ← GUI gaming tkinter (compile en OverLord.exe)
├── launcher.py             ← Interface tkinter originale V1.30
├── test_pipeline.py        ← 16 tests automatiques (lancer avant chaque build)
├── self_improve.py         ← Auto-amélioration du code
├── overlord_utils.py       ← Utilitaires centraux (get_api_key, retry, etc.)
├── [autres fichiers racine]
│
├── agents\                 ← Tous les agents (65+ fichiers)
│   ├── context_bus.py      ← La Context Window partagée (CENTRAL — V1.10)
│   ├── director.py         ← Le Réalisateur (V1.48 — NOUVEAU)
│   ├── sourcing.py         ← Veille tendances (Reddit + RSS + Google Trends)
│   ├── scenario.py         ← Scénariste LLM avec loopback qualité
│   ├── storyboard.py       ← Shot list ComfyUI (enrichie par emotion_engine V1.48)
│   ├── critic.py           ← Validateur transitions + personnalité V1.48
│   ├── watchdog.py         ← Monitoring thread daemon
│   ├── checkpoint_manager.py ← Sauvegarde/reprise de run
│   ├── v130_emotion_engine.py ← Émotions → paramètres ComfyUI (V1.30 récupéré)
│   ├── v130_world_model.py    ← Registre entités + ContinuityGuard (V1.30)
│   ├── v130_agent_personality.py ← Viktor/Mia/Élise/Atlas (V1.30)
│   ├── v130_intelligence_ext.py  ← CreativeFatigueDetector + Hivemind (V1.30)
│   ├── v130_generative_world.py  ← AgingSystem + ConsequenceEngine (V1.30)
│   ├── narrative_memory.py       ← Graphe NetworkX continuité narrative (V1.44)
│   ├── style_dna.py              ← Hash LoRA+palette verrouillé par série (V1.44)
│   ├── asset_library.py          ← Bibliothèque personnages/décors (V1.46)
│   ├── pipeline_conscience.py    ← Auto-adaptation paramètres (V1.45)
│   ├── episode_packager.py       ← Assemblage MP4+SRT+thumbnail (V1.46)
│   ├── transmedia_export.py      ← Publication YouTube/Reddit/Instagram (V1.47)
│   ├── cost_tracker.py           ← Suivi coûts API temps réel (V1.46)
│   ├── error_recovery.py         ← Récupération auto sur crash (V1.47)
│   ├── prompt_optimizer.py       ← Optimisation prompts ComfyUI (V1.47)
│   ├── audience_analyzer.py      ← Feedback Reddit → adaptation contenu (V1.47)
│   ├── style_evolution.py        ← Style visuel évolutif par arc (V1.47)
│   ├── benchmark_arena.py        ← Comparaison LoRAs automatique (V1.47)
│   ├── session_manager.py        ← Plusieurs séries en parallèle (V1.47)
│   ├── module_manager.py         ← Activer/désactiver agents (V1.46)
│   ├── comfy_autoconfig.py       ← Scan modèles → update JSON (V1.45)
│   ├── telegram_bot.py           ← Notifs push + commandes distantes (V1.45)
│   └── [v110_*, v120_*, v130_*, v140_*] ← Modules hérités V1.10-V1.40
│
├── workspace\              ← Données runtime (créé automatiquement)
│   ├── logs\
│   ├── checkpoints\
│   ├── scripts\            ← Scripts JSON générés par scenario.py
│   ├── storyboards\        ← Shot lists JSON
│   ├── episodes\           ← Épisodes assemblés
│   ├── conscience\         ← Métriques pipeline_conscience
│   ├── director\           ← Intentions de run
│   ├── self_improve\       ← MASTER_LOG.jsonl + backups
│   ├── narrative\          ← Graphes NetworkX par série
│   ├── style_dna\          ← DNA visuels par série
│   └── asset_library\      ← Bibliothèques assets
│
├── START_OVERLORD.bat      ← Menu principal (v1.45)
├── INSTALL_MODELS.bat      ← Installation dépendances (v1.45)
├── LAUNCH_COMFYUI.bat      ← Lancement ComfyUI (v1.45)
└── overlord_ui.html        ← Interface web Cyborg-Zen 8 thèmes
```

### 2.2 Flux de données principal

```
[USER] python maestro.py --media-type anime --universe "Dragon Ball"
  ↓
[DIRECTOR] set_intent() — consulte conscience+world+emotion+personality
  → publie intention sur context_bus (mode, arc émotionnel, seuil qualité)
  ↓
[BLOC 1 — SOURCING]
  sourcing.py → Reddit OAuth2 + RSS + Google Trends → TrendReport JSON
  audience_analyzer.py → enrichit avec feedback Reddit
  → context_bus.write("sourcing.trend_report", ...)
  ↓ [CRITIQUE : score=100 → PASS]
  ↓
[BLOC 2 — SCÉNARIO]
  scenario.py → LLM (Claude ou Ollama fallback) → ScriptDocument JSON
  prompt_optimizer.py → améliore les prompts visuels
  → Loopback qualité (MAX 3 itérations, seuil dynamique depuis Director)
  ↓ [CRITIQUE : score≥seuil → PASS, sinon REJECT → retry]
  ↓
[BLOC 3 — STORYBOARD]
  storyboard.py → ShotList JSON (30-60 plans)
  director.get_emotion_for_shot() → enrichit chaque plan émotionnellement
  v130_world_model.validate_and_fix_prompt() → cohérence narrative
  quality_gate.html → validation humaine optionnelle (approve/reject par plan)
  ↓
[BLOC 4 — PRODUCTION ComfyUI]
  agent_supervisor_v2.py → envoie les jobs à ComfyUI via API
  watchdog.py → surveille frame par frame
  error_recovery.py → récupère sur crash GPU OOM / ComfyUI freeze
  ↓
[BLOC 5 — POST-PRODUCTION]
  postprod.py → TTS (gTTS) + musique + mixage ffmpeg
  episode_packager.py → MP4 + SRT + thumbnail + metadata JSON
  ↓
[BLOC 6 — 3D / EXPORT]
  agent_3d_modeler.py → modèles 3D optionnels
  transmedia_export.py → YouTube + Reddit + Instagram + Webtoon
  ↓
[POST-RUN]
  pipeline_conscience.analyze_and_adapt() → ajuste les seuils pour le prochain run
  director.close_run() → clôture, met à jour le world model
  self_improve.run() → optionnel, patches automatiques si bugs détectés
```

### 2.3 Le Director (V1.48 — NOUVEAU, crucial)

```python
from agents.director import get_director, ProductionMode

d = get_director("Dragon Ball Ov3rLoRd")
intent = d.set_intent(media_type="anime", universe="Dragon Ball", episode=3)

# Ce que le Director décide automatiquement :
# - intent.mode : FACTORY/BALANCE/ATELIER/DREAM
# - intent.emotion_arc : "tension" pour ep 4-7
# - intent.quality_threshold : 70-90 selon historique
# - intent.personality_lead : "viktor"/"elise"/"mia"/"atlas"
# - intent.creative_risk : 0.0-1.0

# Tous publiés sur context_bus → lisibles par tous les agents
```

### 2.4 Le Context Bus (V1.10, activé V1.48)

```python
from agents.context_bus import get_bus
bus = get_bus()  # Singleton

# Écrire
bus.write("director.emotion_arc", "catharsis", agent_id="director", confidence=0.9)

# Lire
arc = bus.read("director.emotion_arc")  # → "catharsis"

# Contexte pour un agent spécifique
ctx = bus.get_context_for("storyboard")  # Retourne les clés les plus pertinentes

# Consensus entre agents
consensus = bus.get_consensus("quality.score")
```

**IMPORTANT :** Les modules V1.44-V1.47 n'utilisent PAS encore le context_bus.
Seul director.py l'utilise activement (V1.48). C'est la prochaine priorité.

---

## 3. ÉTAT DES LIEUX V1.48

### 3.1 Ce qui fonctionne immédiatement (sans setup complexe)

- `python maestro.py --media-type anime --universe "X"` → pipeline complet
- `python oracle_interface.py` → CLI Oracle
- `python test_pipeline.py --quick` → validation environnement 30 secondes
- `python self_improve.py --mode status` → état de santé du code
- `overlord_ui.html` → interface web (ouvrir dans navigateur)
- `analytics_dashboard.html` → métriques (importer run_history.jsonl)
- `quality_gate.html` → validation storyboard avant production
- `storyboard_visualizer.html` → preview interactif storyboard
- `live_monitor.html` → dashboard temps réel
- `START_OVERLORD.bat` → menu principal

### 3.2 Ce qui nécessite setup

| Fonctionnalité | Prérequis |
|---|---|
| Génération scénario/storyboard | Crédits Anthropic API + `ANTHROPIC_API_KEY` dans .env |
| Fallback LLM offline | Ollama installé + llama3 pull |
| Génération images | ComfyUI installé + modèles SDXL |
| Assemblage vidéo | ffmpeg dans le PATH |
| Bot Telegram | `TELEGRAM_TOKEN` + `TELEGRAM_CHAT_ID` dans .env |
| Mémoire narrative | `pip install networkx chromadb` |
| Reddit authentifié | `REDDIT_CLIENT_ID` + `REDDIT_CLIENT_SECRET` dans .env |
| Export Reddit | `pip install praw` |
| GUI launcher .exe | `python build_launcher.py` (PyInstaller) |

### 3.3 Bugs connus et non résolus

**BUG 1 — Reddit 403 (partiellement résolu)**
`sourcing.py` tente OAuth2 si credentials présents, sinon fallback User-Agent.
Sans credentials Reddit dans .env, tous les subreddits retournent 403.
→ Solution partielle : RSS et Google Trends fonctionnent sans auth.
→ Solution complète : créer une app Reddit sur reddit.com/prefs/apps.

**BUG 2 — context_bus non utilisé par 80% des agents**
Director publie sur le bus. Les agents V1.44-V1.47 ne lisent pas le bus.
Ils fonctionnent en isolation. La vraie mémoire partagée n'est pas active.
→ Priorité V1.49 : câbler les 20 agents principaux au context_bus.

**BUG 3 — Interfaces HTML déconnectées du Python**
`live_monitor.html`, `analytics_dashboard.html` simulent des données.
Il n'y a pas de serveur Flask qui les alimente en temps réel.
→ Priorité V1.49 : `api_server.py` (80 lignes Flask) qui expose /api/status, /api/logs, /api/run.

**BUG 4 — Pas de test d'intégration end-to-end**
`test_pipeline.py` teste les imports, pas les flux de données réels.
On n'a jamais validé que les données passent correctement de sourcing → scenario → storyboard.
→ Priorité V1.49 : `test_integration.py` avec données mock.

**BUG 5 — Déploiement manuel**
Mettre à jour D:\OVERLORD nécessite d'extraire un ZIP et copier les fichiers.
Aucun mécanisme automatique. Risque d'oublier un fichier.
→ Priorité V1.49 : `deploy.py` qui compare et applique sélectivement.

**BUG 6 — maestro.py : _start_time non défini**
Dans director close_run, on calcule `time.time() - getattr(run_pipeline, '_start_time', time.time())`.
La variable `_start_time` n'est jamais assignée à la fonction.
→ Fix : ajouter `run_pipeline._start_time = time.time()` au début de run_pipeline().

**BUG 7 — agents/ encore en MAJUSCULES possible**
Sur Windows, si le dossier est `AGENTS\` (majuscules), Python 3.14 ne trouve pas le module `agents`.
→ Vérifier : `dir D:\OVERLORD` doit montrer `agents` en minuscules.
→ Fix si besoin : renommer via explorateur Windows en passant par `agents_tmp`.

### 3.4 Précisions sur les modules V1.30 récupérés

Ces modules sont fonctionnels syntaxiquement mais leurs connexions sont partielles :

`v130_emotion_engine.py` — branché dans storyboard.py (V1.48) ✓  
`v130_world_model.py` — branché dans Director (V1.48) ✓  
`v130_agent_personality.py` — importé dans critic.py (V1.48) — pas encore injecté dans les prompts  
`v130_intelligence_ext.py` — CreativeFatigueDetector dans self_improve (V1.48) ✓  
`v130_generative_world.py` — branché dans Director (V1.48) ✓  
`v130_dream_mode.py` — standalone, pas connecté au pipeline  
`v130_cocreation.py` — standalone, pas connecté  
`v130_narrative_dna.py` — standalone, à fusionner avec narrative_memory.py  
`v130_dashboard.py` — dashboard tkinter 9 onglets, standalone  
`v130_pipeline_api.py` — API REST Flask, à activer comme serveur  

---

## 4. ROADMAP TECHNIQUE

### V1.49 — Priorité absolue (3 éléments)

**4.1 `api_server.py`** (80 lignes Flask)
Pont entre le Python et les interfaces HTML.
```python
# endpoints à créer :
GET /api/status          → état pipeline, services, métriques
GET /api/logs            → dernières lignes de log
POST /api/run            → déclencher un run
GET /api/director/intent → intention du Director actuel
GET /api/costs           → rapport cost_tracker
WebSocket /ws/logs       → streaming logs temps réel
```
Démarré automatiquement par maestro.py ou oracle_interface.py.
Les 5 pages HTML s'y connectent → elles deviennent vraiment vivantes.

**4.2 `deploy.py`** (100 lignes)
```python
# Logique :
# 1. Lire le contenu du ZIP patch
# 2. Comparer hash MD5 avec fichiers locaux D:\OVERLORD
# 3. Afficher diff (fichiers modifiés/ajoutés/supprimés)
# 4. Backup automatique avant écrasement
# 5. Appliquer sélectivement
# Usage : python deploy.py OverLord_Pipeline_V149_FULL.zip
```

**4.3 `test_integration.py`** (200 lignes)
```python
# Tests de flux de données réels (sans API externe) :
# - sourcing fallback → produce valid TrendReport
# - TrendReport → scenario fallback → valid ScriptDocument
# - ScriptDocument → storyboard fallback → valid ShotList
# - ShotList → episode_packager (sans ffmpeg) → metadata JSON
# - director.set_intent() → publie sur context_bus → lisible
# Durée cible : 30 secondes
```

### V1.50 — Connexions context_bus

Câbler les 20 agents principaux au context_bus :
```python
# Pattern à répliquer dans chaque agent :
from agents.context_bus import get_bus
bus = get_bus()

# En début de fonction principale :
bus.write(f"{agent_name}.started", True, agent_id=agent_name)

# Lire l'intention du Director :
threshold = bus.read("director.quality_threshold") or 70
emotion   = bus.read("director.emotion_arc") or "neutral"

# En fin de fonction :
bus.write(f"{agent_name}.result", result_summary, agent_id=agent_name)
```

Agents prioritaires à câbler :
1. `scenario.py` — lire director.quality_threshold, director.emotion_arc
2. `storyboard.py` — lire director.world_context, écrire shots count
3. `critic.py` — lire director.critic_strictness, écrire score
4. `sourcing.py` — écrire trend_report summary
5. `self_improve.py` — lire et écrire health_score

### V1.51 — Personality dans les prompts

`v130_agent_personality.py` est importé mais pas encore injecté.
Objectif : chaque agent LLM reçoit un system_prompt enrichi par sa personnalité.

```python
# Dans scenario.py, generate_script() :
from agents.v130_agent_personality import get_personality_manager
pm = get_personality_manager()
base_system = "Tu es un scénariste..."
enriched_system = pm.inject("viktor", base_system)  # Viktor le perfectionniste
# → system prompt enrichi avec la voix de Viktor

# Dans critic.py :
enriched_system = pm.inject("elise", base_system)  # Élise la critique sévère
```

### V1.52 — Restructuration V2.0 (optionnel, long terme)

Structure de dossiers proposée pour V2.0 :
```
D:\OVERLORD\
├── core\           maestro, critic, watchdog, checkpoint, context_bus, director
├── agents\creative\  sourcing, scenario, storyboard, postprod
├── agents\intelligence\  narrative_memory, style_dna, emotion_engine, world_model...
├── agents\tools\   cost_tracker, error_recovery, module_manager...
├── agents\legacy\  v110_*, v120_*, v130_*, v140_*
├── ui\             overlord_ui.html, live_monitor.html, overlord_launcher.py
├── api\            api_server.py, v130_pipeline_api.py
├── tests\          test_pipeline.py, test_integration.py
└── scripts\        deploy.py, build_exe.py, START_OVERLORD.bat
```
⚠️ NE PAS FAIRE avant V1.52 — casse tous les imports. Attendre que le pipeline soit stable.

---

## 5. RÈGLES DE PILOTAGE

### 5.1 Standards de codage

**Branding :** Toujours `Ov3rLoRd` (jamais `OverLord`) dans banners, titres, prints, logs.

**Authentification API :**
Chaque fichier qui appelle `https://api.anthropic.com/v1/messages` DOIT avoir :
```python
def _get_api_key() -> str:
    import os as _os
    from pathlib import Path as _P
    key = _os.environ.get("ANTHROPIC_API_KEY", "")
    if not key:
        for env in [_P(__file__).parent.parent / ".env", _P(".env")]:
            if env.exists():
                for line in env.read_text(encoding="utf-8").splitlines():
                    if line.startswith("ANTHROPIC_API_KEY="):
                        key = line.split("=",1)[1].strip().strip('"').strip("'")
                        if key: break
    return key

# Dans requests.post() :
headers={
    "Content-Type": "application/json",
    "x-api-key": _get_api_key(),
    "anthropic-version": "2023-06-01",
}
```

**Imports inter-agents — TOUJOURS protégés :**
```python
# ✓ CORRECT
try:
    from agents.narrative_memory import NarrativeMemory
    MEMORY_OK = True
except ImportError:
    MEMORY_OK = False
    NarrativeMemory = None

# ✗ INCORRECT — crashe si le module manque
from agents.narrative_memory import NarrativeMemory
```

**Fallbacks obligatoires :**
Chaque module principal doit fonctionner sans ses dépendances optionnelles.
Pattern systématique : `if FEATURE_OK: ... else: fallback_simple`.

**LLM avec fallback Ollama :**
```python
# Utiliser overlord_utils.fallback_llm() — jamais appeler l'API directement
from agents.overlord_utils import fallback_llm
result = fallback_llm(prompt, max_tokens=1000, logger=log)
# → Essaie Claude, puis Ollama/llama3, puis Ollama/mistral, puis ""
```

**Validation syntaxe avant livraison :**
```python
import ast
ast.parse(open('fichier.py').read())  # Doit passer sans erreur
```

**Logging standardisé :**
```python
log = logging.getLogger("nom_module")  # Toujours en minuscules
log.info(f"[NOM_MODULE] Message clair")
# Jamais de print() dans les agents (sauf __main__)
```

### 5.2 Précautions de sécurité

**Clé API :**
- JAMAIS coller la clé API dans le chat ou dans le code source
- Toujours via `setx ANTHROPIC_API_KEY "sk-ant-..."` dans le terminal Windows
- Stocker dans `.env` à la racine (jamais versionné)
- Si la clé est exposée accidentellement : révoquer immédiatement sur console.anthropic.com

**self_improve.py — fichiers protégés :**
```python
PROTECTED_FILES = {
    "self_improve.py",      # Ne peut pas se modifier lui-même
    "licence_server.py",
    "config.json",
    ".env",
}
# MAX_PATCHES_PER_SESSION = 5
# MAX_FILE_SIZE_CHANGE = 0.30  # Jamais +30% de taille
```

**deploy.py (à créer) :**
Toujours faire un backup avant d'écraser un fichier existant.
Jamais supprimer un fichier non présent dans le patch.

### 5.3 Gestion de la conversation Claude

**Problème de quota :**
La conversation accumule des tokens. Plus elle est longue, plus chaque échange coûte.
Une conversation de 200 messages peut consommer 10x plus qu'une conversation fraîche
pour produire la même quantité de code.

**Bonne pratique :**
- Commencer une nouvelle conversation pour chaque version majeure
- Coller `CONTEXTE_OVERLORD.md` au début de la nouvelle session
- Joindre les fichiers à modifier plutôt que de les recopier dans le chat
- Demander des batches de code denses plutôt que des échanges itératifs

**Pour reprendre le développement :**
1. Nouvelle conversation Claude
2. Coller ce fichier `CONTEXTE_OVERLORD.md`
3. "Je reprends le développement d'Ov3rLoRd V1.48. Voici le contexte."
4. Demander directement la V1.49 : `api_server.py` + `deploy.py` + `test_integration.py`

### 5.4 Tests avant livraison

Séquence obligatoire avant chaque build EXE ou archive FULL :
```bash
# 1. Validation syntaxe
python -c "import ast; [ast.parse(open(f).read()) for f in __import__('glob').glob('agents/*.py')]"

# 2. Tests rapides
python test_pipeline.py --quick

# 3. Test import Director (nouveau en V1.48)
python -c "from agents.director import get_director; d=get_director(); d.print_status()"

# 4. Test context_bus
python -c "from agents.context_bus import get_bus; bus=get_bus(); bus.write('test','ok'); print(bus.read('test'))"
```

---

## 6. INFORMATIONS SUR L'UTILISATEUR

**Utilisateur :** Jérémy Gourlain  
**Pseudo projet :** Ov3rLoRd / JackouiLL3  
**Contexte :** Développeur créateur, travaille en sessions longues (24h+), utilise 100% du quota  
**Matériel :** Windows 10, Python 3.14, GPU NVIDIA (ComfyUI), drives D: (pipeline) + G: (archives 1To)  
**Style de travail :** Initiatives validées d'avance, réponses denses sans bavardage, rythme rapide  
**Connexion franco-japonaise :** Ex-membre association franco-japonaise Compiègne/Shirakawa-shi  
**Objectif long terme :** Production anime automatisée + plateforme de création IA  

**Ce qu'il ne faut PAS faire en session :**
- Demander confirmation pour chaque action (les initiatives sont validées)
- Produire du code verbeux avec commentaires excessifs
- S'arrêter pour expliquer ce qu'on va faire (juste le faire)
- Répéter ce qui a déjà été dit

**Ce qu'il faut TOUJOURS faire :**
- Audit syntaxe avant livraison
- Archive ZIP à chaque version
- Rapport .md à chaque version
- Branding `Ov3rLoRd` (jamais `OverLord`)

---

## 7. FICHIERS DE RÉFÉRENCE DANS L'ARCHIVE V1.48

L'archive `OverLord_Pipeline_V148_FULL.zip` contient TOUT le projet V1.48.
Les rapports précédents :
- `RAPPORT_V141.md` → debug complet V1.40
- `RAPPORT_V142.md` → overlord_utils, test_pipeline, fallback Ollama
- `RAPPORT_V144.md` → narrative_memory, style_dna, Reddit OAuth2
- `RAPPORT_V145.md` → Pipeline Conscience, ComfyUI AutoConfig, Telegram, Launcher GUI
- `RAPPORT_V146.md` → episode_packager, quality_gate, asset_library, cost_tracker
- `RAPPORT_V147.md` → transmedia, benchmark_arena, session_manager, prompt_optimizer, error_recovery, style_evolution, audience_analyzer, live_monitor
- `RAPPORT_V148.md` → Director, context_bus activé, reconnexion V1.30
- `ANALYSE_STRATEGIQUE_V147.md` → vision long terme, auto-critique, restructuration
- `EVALUATION_PROMPT_ENGINEERING.md` → évaluation Jérémy (score 83/100)
- `CONTEXTE_OVERLORD.md` → CE FICHIER

---

## 8. COMMANDE DE REPRISE

Pour reprendre immédiatement là où on s'est arrêtés :

```
Je reprends le développement d'Ov3rLoRd Pipeline.
Version actuelle : V1.48 — La Reconnexion.
Contexte : [coller ce fichier]

Prochaine version : V1.49
Objectifs dans l'ordre :
1. api_server.py — pont Flask HTML↔Python (80 lignes)
2. deploy.py — déploiement automatique depuis ZIP (100 lignes)  
3. test_integration.py — tests flux de données end-to-end (200 lignes)
4. Corriger BUG 6 dans maestro.py (_start_time non défini)

Commence par api_server.py.
```

---

*Document généré le 18/06/2026 — Session Claude Sonnet 4.6*  
*Ov3rLoRd Pipeline V1.48 — 45 234 lignes — 0 erreur critique*  
*"Un pipeline de production anime qui aspire à être un atelier d'artiste."*

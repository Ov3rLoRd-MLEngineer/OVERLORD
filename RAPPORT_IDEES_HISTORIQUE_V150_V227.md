# Pistes et idées encore utiles — relecture CONTEXTE_OVERLORD_V150 à V227

Généré le 2026-08-02, en complément de `RAPPORT_AUDIT_PIPELINE_AOUT2026.md`.
Objectif différent de ce dernier : celui-ci ne cartographie pas l'état du
code, il relit les 15 documents de session `CONTEXTE_OVERLORD_V150.md` à
`V227.md` (racine du dépôt, hors worktrees/BACKUP — plage couverte :
20/06/2026 → 30/06/2026) pour en extraire les **idées, pistes et diagnostics
qui restent exploitables aujourd'hui**, même quand le contexte précis dans
lequel ils ont été écrits (deadline Japan Expo, hardware RTX 2070/5080,
Python 3.14, etc.) ne l'est plus. Organisé par thème, pas par ordre
chronologique.

**Lecture recommandée** : un chiffre ou un statut de fichier cité ici peut
être daté ; l'idée de fond, elle, reste la plupart du temps valable. Chaque
piste indique sa source (version + date) pour retrouver le contexte complet
si besoin.

---

## 1. Le constat le plus important : un diagnostic vieux d'un mois, jamais résolu

**`CONTEXTE_OVERLORD_V225.md` (24/06/2026) nomme explicitement "LE
problème architectural central" du pipeline** :

> BUG FONDAMENTAL (jamais résolu) — 1 image = 1 pass ComfyUI. Depuis V1.0,
> une image = un seul passage ComfyUI. Jérémy demande depuis le début :
> production multi-pass. Jamais implémenté malgré documentation dans
> contextes successifs.

**Ce diagnostic reste vrai aujourd'hui** (2026-08-02, confirmé par
`RAPPORT_AUDIT_PIPELINE_AOUT2026.md`) : `agent_supervisor_v2.py` ne produit
toujours que des images fixes en un seul passage KSampler par job. L'agent
`multi_pass_producer.py` envisagé dès V225 pour orchestrer Run1
(brut)→Run2(détail)→Run3(style) n'a jamais été construit — aucune trace
dans le dépôt actuel. C'est la piste la plus ancienne et la plus
consistante de tous ces documents : elle est citée comme prioritaire à
V225 (24/06), reprise et affinée à V227 (30/06, voir section 2), puis
apparemment abandonnée quand la priorité a basculé vers les SegNets
(juillet). **Elle mérite d'être reconsidérée avant de repartir sur
AnimateDiff from scratch** — c'est un chemin alternatif déjà largement
pensé, pas une idée neuve à inventer.

---

## 2. Le plan multi-pass concret proposé pour AnimateDiff (V227, jamais construit)

`CONTEXTE_OVERLORD_V227.md` documente un compromis découvert empiriquement :
AnimateDiff lisse les hautes fréquences spatiales pour maintenir la
cohérence temporelle — **structurel, pas paramétrique** (pas réglable par
CFG/steps). Le plan de contournement proposé, validé en session mais
jamais codé :

- **Run 1 (corps nu) avec AnimateDiff** → cohérence temporelle maximale,
  peu de détails fins.
- **Run 2 (vêtements) frame par frame SANS AnimateDiff** → détail maximal,
  appliqué par-dessus le Run 1 comme guide de pose/mouvement.
- **Run 3 (FX + background)** → idem, couche séparée.

Complété par une idée d'anti-flickering non testée : **injecter une frame
"propre" tous les 16 frames comme référence IPAdapter forte (weight
0.9-1.0)** — analogie avec les inbetweeners qui travaillent entre les poses
clés de l'animateur principal. Cette paire d'idées (multi-pass + keyframe
de reset périodique) reste directement actionnable : elle correspond très
exactement au type de solution que le rapport de veille récent (`DOCS/MD/
Audit de maturité technique 2026...md`) confirme comme non résolu
publiquement en 2026 pour le lineart temporel — c'est-à-dire que
l'utilisateur avait déjà, en juin, correctement anticipé un gap que la
recherche externe confirme un mois plus tard n'avoir toujours pas de
solution "clé en main".

---

## 3. Une chaîne de production dormante et substantiellement construite (`batch_controlnet.py` — "Pipeline A")

**Découverte importante de cette relecture** : entre le 23/06 et le
30/06/2026 (V222→V227), un pipeline de production frame-par-frame
entièrement distinct de `agent_supervisor_v2.py` a été construit
spécifiquement pour produire une démo animée, en contournant `maestro.py`
("bypass complet de maestro", V224). Il est allé jusqu'à la version V1.9
(doc), et **ses fichiers existent toujours dans le dépôt actuel** :

```
agents/batch_controlnet.py        (en-tête encore marqué V1.4 dans le fichier —
                                    le code a peut-être évolué sans que le
                                    docstring suive, à vérifier avant usage)
agents/motion_mask_generator.py
agents/denoise_estimator.py
agents/reference_aligner_v2.py
agents/session_manager.py          (create/load/save session, resume, rollback par shot)
agents/skeleton_remapper.py
agents/lineart_extractor.py
agents/frames_to_video.py
agents/qwen_prompt_refiner.py
invert_lineart.py                  (racine)
```

Architecture V1.9 (la plus aboutie documentée, V226) : squelettes DWPose +
lineart extrait → ControlNet double (OpenPose rank256 + Lineart xinsir,
strength 1.25/end 0.50) + IPAdapter en mode "rolling" (frame N-1 comme
référence) + masque de mouvement généré par diff de squelettes + denoise
dynamique estimé par diff PIL. Résultats obtenus et documentés : **10/10
frames réussies sans erreur, fond stable sur 10 frames consécutives**
(V226) — donc pas juste une idée, un prototype qui a produit des résultats
mesurés.

**Pourquoi c'est resté inachevé** : trois blocages cumulés, pas un abandon
de principe — (1) le lineart source (`lineart_1024x1024/`) n'a jamais
dépassé une fraction du total nécessaire (38 fichiers présents aujourd'hui
sur le dossier `DEMO/frames/`, correspondant au cycle Mixamo de 34-38
frames, pas aux 1008 frames de la démo complète) ; (2) le squelette Mixamo
utilisé (modèle "Sophie") a un bras gauche manquant à cause de ses
vêtements — solution identifiée (modèle Mixamo nu, ou retargeting MMD) mais
jamais appliquée ; (3) `cycle_detector.py` (détection du meilleur cycle de
24 frames à boucler) n'a jamais été construit, ce qui bloquait le passage
du cycle de 34 frames aux 1008 frames finaux. La session a ensuite pivoté
vers le test direct d'AnimateDiff dans l'UI ComfyUI (même V227, puis
l'addendum du 30/06 déjà couvert dans le rapport principal), sans jamais
revenir clore Pipeline A.

**Pourquoi le signaler ici** : si l'objectif est de sortir 30s de démo
animée rapidement, **finir ce pipeline (déjà à 90% construit, avec des
résultats mesurés) peut être plus rapide que fiabiliser AnimateDiff
depuis les deux bugs non résolus** documentés dans le rapport principal —
à évaluer comme option concurrente, pas juste comme curiosité historique.

---

## 4. Idées de qualité/architecture toujours pertinentes, jamais implémentées

- **Production par couches séparées (bg/char/fx + sidecar `_prompt.json`)**
  — vision "style Ankama Dofus/Wakfu" énoncée dès `CONTEXTE_OVERLORD.md`
  V1.70 (22/06) et reprise à V2.24 (24/06, "Vision long terme Pipeline B").
  C'est exactement ce que `agents/sakuga_compositor.py` a fini par
  implémenter plus tard (confirmé dans l'audit principal) — mais jamais
  câblé au pipeline. Le lien entre l'intention d'origine et le module
  existant aujourd'hui n'était pas évident sans cette relecture : ce n'est
  pas du code mort sans objectif, c'est une brique construite pour une
  vision précise, restée sans les deux autres pièces (les passes
  successives + le point de branchement dans `maestro.py`).
- **`prompt_translator.py`** (narratif → JSON d'intention : `shot_type`,
  `lighting`, `acting_intent`, `camera_movement`, prompts positif/négatif)
  — livré et testé dès V2.10 (23/06), appelé en fin de `run_storyboard()`.
  Confirmé toujours listé comme agent actif jusqu'à V2.24. À revérifier
  s'il est toujours appelé aujourd'hui (non vérifié dans l'audit principal,
  qui s'est concentré sur les modules vidéo) — piste de vérification rapide
  si utile.
- **ControlNet Union** (fusionner OpenPose + Lineart en un seul nœud pour
  éviter que l'un écrase l'autre) et **Depth ControlNet en 3ᵉ couche**
  (anti-flickering spatial, weight 0.8-1.2) — notés comme roadmap long
  terme à V227, jamais suivis. Pistes concrètes et peu coûteuses à tester
  si le chantier AnimateDiff/batch_controlnet reprend.
- **Retargeting MMD** (`mmd_tools` addon Blender, FBX→VMD→PMX) pour obtenir
  un squelette Mixamo sans occlusion de vêtements — solution identifiée
  pour le bug "bras gauche manquant" (section 3), jamais appliquée.
- **RemBg post-processing en batch** sur toutes les frames générées — noté
  comme manquant à V227 ("RemBg post-processing agent"), pas confirmé
  construit depuis (à vérifier si besoin, hors périmètre de cet audit).

---

## 5. Gotchas techniques ComfyUI qui resteront valables pour tout futur chantier vidéo/animation

- **Cache `LoadImage` par nom de fichier** (bug documenté V225, patché
  "V1.5") : ComfyUI met en cache un node `LoadImage` par nom de fichier —
  si on réutilise le même nom entre deux soumissions avec un contenu
  différent, ComfyUI resert l'ancien résultat. Deux mitigations
  rencontrées dans l'historique du dépôt : noms **fixes** réécrits à
  chaque frame (`ov_skeleton_current.png`, approche V225/batch_controlnet)
  vs noms **uniques horodatés** (approche retenue plus tard dans
  `sam_mask_generator.py`, cf. mémoire `CLAUDE.md`). Les deux marchent ;
  le point à retenir est que **ce n'est pas un bug isolé au SAM masking**,
  c'est un comportement général de ComfyUI à anticiper systématiquement
  dès qu'un script soumet des images différentes sous un chemin réutilisé.
- **ControlNet bypassé silencieusement si le nom de modèle ne correspond
  pas exactement au fichier sur disque** (BUG CRITIQUE 1, V225) — aucune
  erreur visible, juste un résultat identique avec ou sans ControlNet.
  Checklist de diagnostic documentée : vérifier le fichier existe
  physiquement, chercher "model loaded" dans les logs console ComfyUI,
  test visuel définitif avec un squelette délibérément absurde.
- **`Use Image Preprocessor = false`** nécessaire pour OpenPose ET Lineart
  quand le squelette/lineart est déjà pré-généré en amont (V226) — sinon
  ComfyUI relance un préprocesseur sur une image qui n'en a pas besoin.
- **IPAdapter `weight_type`** : `"linear"` fonctionne sur cette install,
  `"original"` n'est pas supporté (V224/226) — à re-tester si la version
  des custom nodes IPAdapter change.
- **FizzNodes `BatchPromptSchedule`** casse le JSON envoyé via l'API Python
  — toujours encoder le schedule avec `json.dumps()` avant envoi, ou en
  Base64 en repli (`CONTEXTE_OVERLORD.md` V1.70, 22/06). Pertinent si un
  futur chantier relance le "prompt travel" par frame pour AnimateDiff.

---

## 6. Pistes business/produit toujours valables (hors code)

- **Formaliser l'architecture d'agents comme framework générique**,
  au-delà du pipeline anime : `director.py` = chef de projet,
  `intent_parser.py` = account manager, `self_optimizer.py` = lead tech,
  `market_analyzer.py` = business developer, `quality_reviewer.py`/
  `critic.py` = QA (`CONTEXTE_SESSION_SUIVANTE`, 20/06). Idée non reprise
  depuis mais potentiellement vendable indépendamment du pipeline anime
  lui-même — mentionnée ici parce qu'elle n'apparaît dans aucune mémoire
  ni rapport ultérieur.
- **Grok 4 Fast reste sous-exploité** : `agents/grok_client.py` existe et
  fonctionne (confirmé livré dès V1.50), mais `agents/llm_router.py`
  (audité dans le rapport principal comme "construit, jamais appelé") ne
  route vers aucun mode Grok — seulement Ollama et GLM. Un budget gratuit
  ($175/mois via data-sharing program, mentionné plusieurs fois) semble ne
  jamais avoir été consommé pour la génération de scénario/prompts en
  production. À vérifier si le programme gratuit est toujours actif avant
  de s'appuyer dessus (offre datée de juin 2026).
- **Le projet "Ov3rLoRd Was Here"** (livre d'entretiens rétrospectif,
  `CONTEXTE_SESSION_SUIVANTE`, 20/06) — idée créative non technique,
  jamais reprise dans les documents ultérieurs, toujours valable comme
  projet à part si l'utilisateur veut la raviver un jour.

---

## 7. Explicitement obsolète — à ne pas réappliquer par erreur

Pour éviter qu'une future session reprenne un réglage périmé trouvé dans
un de ces documents :

- **Japan Expo (9-12 juillet) comme deadline** — abandonnée explicitement
  et remplacée par un critère de sortie qualité ("1000 frames 24fps,
  cohérence parfaite, montrable sans excuse"), voir `CONTEXTE_OVERLORD_V229.md`.
- **Khara (Noisy-le-Grand) comme cible de pitch** — ce n'est qu'une
  association rencontrée à Japan Expo, sans lien avec le projet (corrigé
  explicitement dans V229). Cible recrutement actuelle : Mistral.
  Nombreux docs V150-V227 la citent encore comme cible du "film 24 minutes"
  — periné.
- **Python 3.14** comme interpréteur — abandonné dès V2.21 (23/06) au
  profit de `py -3.12` (argparse incompatible sous 3.14), lui-même
  aujourd'hui documenté comme obligatoire dans `CLAUDE.md`.
- **Steps=35/CFG=7.0/résolution 1344×1984 ou 1344×768** (RTX 5080,
  V2.10-V2.26) — les paramètres ComfyUI ont changé plusieurs fois de
  session en session (sampler `dpmpp_2m_sde` puis `euler_ancestral`,
  résolution 1024×1536 finalement retenue V227) ; les valeurs actuelles
  vivent dans `agents/config_manager.py`/`GPU_PRESETS`, seule source de
  vérité à jour — ne pas piocher un chiffre isolé dans un vieux contexte.
- **`Combined_V35_API.json` supprimé puis un fallback minimal utilisé**
  (V2.10-V2.26) — épisode réglé depuis : le fichier a été restauré
  (mentionné en V2.24) et `agent_supervisor_v2.py` actuel le charge
  normalement comme `WORKFLOW_FILE`.
- **`pose_library.py`** — mentionné "livré" à V2.21/V2.22 mais introuvable
  dans le dépôt actuel (ni racine, ni `agents/`, ni aucun worktree) : soit
  jamais réellement committé, soit supprimé depuis sans trace. Ne pas
  supposer son existence sans vérifier.
- **Séquence "Asuka Run" à 720/1008 images en prompt-schedule pur**
  (V2.22-V2.24, sans AnimateDiff, juste ControlNet+IPAdapter frame par
  frame avec drift de prompt) — remplacée dans les faits par les tentatives
  ultérieures (motion mask puis AnimateDiff), mais voir section 3 : le
  code de cette approche n'a pas été supprimé et reste une option viable,
  pas un choix explicitement invalidé.

---

## 8. Complément — passe sur `D:\OVERLORD\DOCS\`

Sur demande explicite de vérification, relecture de l'ensemble de
`DOCS/` (hors `DOCS/data claude 001/*.json` — export brut de conversations
Claude.ai déjà synthétisé dans `RAPPORT_TACHES_EN_SUSPENS_JUILLET2026.md`,
volontairement non relu en détail ici : ce sont des données sources, pas
des documents de référence). Contenu : `DOCS/INDEX.md`, `DOCS/LLM-Secour.md`
et les rapports `DOCS/MD/*` déjà couverts dans l'audit principal, plus les
documents suivants, non lus avant cette relecture.

### Le même diagnostic qu'aujourd'hui, posé un mois et demi plus tôt

`DOCS/MD/ANALYSE_STRATEGIQUE_V147.md` (18/06/2026, auto-critique honnête
demandée par l'utilisateur) contient une conclusion qui **anticipe
exactement** le constat central de `RAPPORT_AUDIT_PIPELINE_AOUT2026.md` :

> La prochaine étape critique n'est pas d'ajouter de nouveaux modules.
> C'est de connecter ce qui existe. Les outils ne se parlent pas encore
> vraiment.

Écrit à V1.47 (88 modules), toujours vrai à V229+ (155 modules). Le
pipeline a grandi d'environ 75% en volume de code depuis ce diagnostic sans
que le diagnostic lui-même cesse d'être exact — le mécanisme qui produit
des modules plus vite qu'il ne les relie semble structurel au mode de
travail (sessions denses de génération de code), pas un oubli ponctuel.
Signal à prendre au sérieux si l'objectif reste de sortir un livrable
plutôt que d'accumuler des capacités.

Le même document propose une restructuration `core/agents/ui/api/tests/
scripts` (vs la structure plate actuelle), explicitement reportée à
"V2.0, pas avant" — jamais faite depuis (la structure est toujours plate
aujourd'hui). Reste une idée valide si la maintenabilité devient un
problème concret, mais un an de report constant suggère que ce n'est pas
le bon levier à activer maintenant non plus.

### Outils de diagnostic jamais construits, toujours pertinents

`DOCS/MD/PROPOSITIONS_AGENTS_AAA.md` (V1.50) propose plusieurs agents
utilitaires — aucun n'existe dans le dépôt actuel (vérifié : pas de fichier
`aAa_*.py`). Les deux plus directement utiles si le chantier animation/
AnimateDiff/`batch_controlnet.py` reprend :
- **`aAa_ComfyUIHealthCheck`** : vérifie ComfyUI en ligne, les nœuds du
  workflow, les LoRA/checkpoints référencés, la VRAM disponible, et lance
  une génération minimale de validation (1 step, 64×64) — aurait
  directement évité le "BUG CRITIQUE 1" de `CONTEXTE_OVERLORD_V225.md`
  (ControlNet bypassé silencieusement faute de fichier trouvé, découvert
  seulement après plusieurs runs).
- **`aAa_WorkflowValidator`** : compare les `node_id` référencés dans le
  code Python (`ADV_LORA_ID = "62"`, etc.) avec ceux réellement présents
  dans le JSON du workflow — aurait attrapé plusieurs des bugs de
  nœud-introuvable documentés à travers V222-V226.

### Origine réelle de `agents/comfy_memory.py` (le fichier manquant)

L'audit principal note que `maestro.py` importe `agents.comfy_memory`
(`VRAMManager`) mais que le fichier n'existe pas dans le dépôt actuel.
`DOCS/MD/README.md` (la toute première doc du projet, v1.0.0-alpha,
15/06/2026) confirme que ce module a réellement existé au tout début
("gestion VRAM RTX 5080") — ce n'est pas une référence fantôme jamais
implémentée, c'est un module perdu au fil des réécritures successives du
projet (probablement lors d'une des nombreuses restructurations entre
l'alpha et V1.40+). Anecdotique mais ça répond à la question "a-t-il
jamais existé ?" avec un oui.

### `episode_packager.py` — un second module d'assemblage vidéo en silo

`DOCS/MD/RAPPORT_V146.md` (18/06/2026) présente `episode_packager.py`
comme "le maillon manquant du pipeline" : assemblage ffmpeg + génération
SRT + chapitres YouTube + thumbnail + métadonnées. Le fichier existe
toujours dans `agents/` aujourd'hui, mais — comme les cinq modules
d'assemblage vidéo déjà identifiés dans l'audit principal — **aucun
import ne le référence nulle part dans le dépôt actuel**. `postprod.py`
(lui, réellement appelé par `maestro.py`) fait une version plus simple du
même travail (TTS + ffmpeg concat) sans jamais déléguer à
`episode_packager.py`. Un sixième module d'assemblage à ajouter à la liste
des pièces prêtes mais jamais reliées.

### ADR_MUSIC.md / ADR_TTS.md — les propositions à l'origine des ADR-011/012

`DOCS/ADR_MUSIC.md` et `DOCS/ADR_TTS.md` (04/07/2026, statut "Proposé")
sont les documents de comparaison qui ont mené aux décisions déjà connues
(Coqui XTTS-v2 + gTTS fallback ; MusicGen non-commercial + flag propagé au
publisher). Rien de nouveau par rapport à ce qui est déjà su, mais utile
de savoir où retrouver le raisonnement complet (tableaux de comparaison
VRAM/licence/qualité) si une révision de ces choix est un jour nécessaire
— notamment le rappel que **F5-TTS et Suno restent explicitement écartés**
de toute automatisation (licence Emilia CC-BY-NC pour F5-TTS ; absence
d'API officielle pour Suno, l'usage automatisé violerait ses CGU).

### Docs d'installation obsolètes — confirment une trajectoire, rien à en tirer

`DOCS/MD/README.md`, `GUIDE_OVERLORD.md`, `README_INSTALLATION.md`,
`MANUAL_DOWNLOADS.md`, `TUTO_LANCEMENT.md` datent tous de la période
v1.0.0-alpha (15/06/2026) et recommandent **NoobAI-XL** comme checkpoint
principal — explicitement exclu depuis dans `CLAUDE.md` ("NoobAI exclu,
usage commercial"). Confirment simplement que cette exclusion est un choix
tardif et déjà bien retranscrit dans la documentation actuelle ; aucune
piste technique à en tirer, entièrement supersédés par `CLAUDE.md`.

---

*Rapport généré en lecture seule à partir des 15 documents
`CONTEXTE_OVERLORD_V150.md` à `V227.md` (racine du dépôt) et de l'ensemble
de `DOCS/` (hors export brut `DOCS/data claude 001/*.json`), en complément
de `RAPPORT_AUDIT_PIPELINE_AOUT2026.md`. Aucun fichier de code modifié.*

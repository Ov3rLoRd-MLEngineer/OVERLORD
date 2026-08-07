# Budget GPU 8h — SVI + postprod combinés

Origine : `consignes (2).txt` (Bureau, 2026-08-06). Rééquilibrage suite au
constat que le postprod pleine échelle (14 400 frames × ~274-400s/frame)
était hors budget temps, et que la RAM système (32 Go) interdit une
parallélisation continue des deux pipelines ComfyUI (cf.
`DOCS/MD/ARCHITECTURE_GANTT_PERT_5S_v2.md` section 4bis).

## 1. Décision : arrêt du postprod pleine échelle

Le pipeline `postprod_inpaint.py` (validé fonctionnellement, cf.
`DOCS/MD/POSTPROD_PIPELINE_20260806.md`) **n'est plus lancé en balayage
systématique sur les 14 400 frames cibles**. Il reste utilisable
manuellement, en ciblant une plage précise via les nouvelles options
`--start-frame`/`--end-frame` :

```
py -3.12 agents/production_video/postprod_inpaint.py ^
  --videos DEMO/output/miku_demo_30s_v2.mp4 ^
  --keyframe-ref "D:\Ov3rLoRd AI\ComfyUI\output\DemoMiku30s\keyframes\sdxl_keyframe_v2_00001_.png" ^
  --out-dir DEMO/postprod --order asc --start-frame 420 --end-frame 456 --no-watch
```

Cible **candidat 1 (prioritaire)** : `miku_demo_30s_v2.mp4`, frames locales
**420-456** (t≈17.5-19s, transition clips 4→5, changement de tenue pendant
le plan orbit — cf. `POSTPROD_PIPELINE_20260806.md` section 4). Candidats
suivants : sélection manuelle par Jérémy après revue des itérations v1-v8+.

Aucune tentative de faire tourner le postprod en continu/parallèle avec la
génération SVI — décision explicite (consigne), documentée comme goulot RAM
confirmé plutôt que contournée.

## 2. Règle des 8h

**Budget** : 8 heures de génération GPU maximum au total, SVI (RTX 5080,
ComfyUI 8188) + postprod (RTX 5060 Ti, ComfyUI 8189) combinés, pour cette
tâche démo Miku.

**Mécanisme d'arrêt automatique** : `DEMO/run_demo_loop.py` (RTX 5080)
maintient un compteur cumulé persisté dans `DEMO/output/gpu_budget_state.json`
(`cumulative_seconds`), mis à jour après chaque itération réussie (temps réel
mesuré par `time.time()`, pas une estimation). Si le cumul atteint 8h, la
boucle écrit `DEMO/STOP_LOOP.flag` et s'arrête proprement (avant de lancer
une nouvelle itération, ou juste après en avoir terminé une) — même
mécanisme que le seuil 14 400 frames déjà en place, indépendant de lui.

## 3. Calcul du budget consommé (au 2026-08-06, avant redémarrage 8188)

Reconstruit précisément depuis les timestamps réels de `DEMO/output/loop_log.txt`
(keyframe + chaîne SVI + assemble/upscale par itération) et les entrées déjà
présentes dans `gpu_usage_log.csv`. Méthode : somme des durées individuelles
mesurées (pas des empans horloge murale globaux, pour éviter tout double
comptage sur les jobs partagés en file ComfyUI — ex. les retraitements
SeedVR2 v1/v2 qui tournaient en parallèle logique de la génération v3 sur la
même instance ComfyUI, donc déjà inclus dans leurs propres mesures de
segment, pas dans l'empan v3).

| Module | Durée (min) |
|---|---|
| demo-30s-miku-svi-chain (v1, clips2-7+upscale initial) | 22.65 |
| demo-30s-miku-v1-reprocess-seedvr2-segments | 21.47 |
| demo-30s-miku-v2-svi-chain (keyframe+7 clips) | 24.4 |
| demo-30s-miku-v2-reprocess-seedvr2-segments | 20.88 |
| demo-30s-miku-v3-svi-chain (keyframe+7 clips) | 35.2 |
| demo-30s-miku-v3-seedvr2-segments | 17.14 |
| demo-30s-miku-v4-full-iteration | 31.2 |
| demo-30s-miku-v5-full-iteration | 33.9 |
| demo-30s-miku-v6-full-iteration | 39.0 |
| demo-30s-miku-v7-full-iteration | 33.3 |
| postprod-inpaint-validation-tests (6 tentatives, 3 abouties) | 15.3 |
| **TOTAL** | **294.44 min = 4,91 h** |

**Budget restant (au moment du calcul) : 3,09 h (185,56 min).**

v8 était en cours de génération au moment de ce calcul (interrompu par le
redémarrage ComfyUI 8188 demandé, relancé depuis zéro par
`run_demo_loop.py`) — non inclus dans le total ci-dessus pour éviter un
double comptage (le travail partiel de la 1ère tentative est perdu/refait).
Le compteur `gpu_budget_state.json` est initialisé avec ce total (294,44 min)
comme baseline et s'incrémente à partir de la itération v8 relancée.

**Note sur le périmètre** : le test AnimateDiff du 2026-08-05 matin
(39,5 min, RTX 5060 Ti, `animatediff-32frames` dans `gpu_usage_log.csv`)
n'est **pas inclus** dans ce budget — pipeline distinct (exploratoire, avant
le début de la tâche démo Miku Workflow A), pas de la géneration SVI ni du
postprod de cette tâche.

## 4. Projection

À ~33-35 min/itération SVI en moyenne (v4-v7), le budget restant (~185 min)
permet encore **~5-6 itérations**. Mais la file `DEMO/vmd_queue.json` ne
contient plus qu'**1 VMD non utilisé après v8** (`Cry.vmd`) — la file VMD
s'épuisera donc probablement **avant** le budget 8h, indépendamment du
nouveau seuil. Les deux mécanismes d'arrêt (VMD épuisée, budget 8h, cible
14 400 frames) restent actifs en parallèle, le premier atteint déclenche
l'arrêt.

## 5. Actions effectuées

- `gpu_usage_log.csv` : 7 lignes ajoutées rétroactivement (v2/v3 chaînes SVI
  manquantes, v4-v7 itérations jamais loguées au fil de l'eau, tests postprod
  agrégés) — marquées `estime_retroactif=true` sauf le postprod (mesure
  directe des runs aboutis).
- `DEMO/run_demo_loop.py` : mécanisme de budget 8h ajouté (`GPU_BUDGET_*`,
  `read_gpu_budget()`/`write_gpu_budget()`), câblé en tête de boucle (arrêt
  si déjà dépassé) et en fin d'itération réussie (arrêt si dépassé après
  ajout du temps de l'itération qui vient de se terminer).
- `agents/production_video/postprod_inpaint.py` : options `--start-frame`/
  `--end-frame` ajoutées pour cibler une plage précise (implique
  `--no-watch`), au lieu d'un balayage complet depuis 0.
- ComfyUI 8188 (RTX 5080) redémarré à la demande explicite de l'utilisateur
  pour libérer la RAM accumulée (20,8→25,4 Go libres après redémarrage) —
  `run_demo_loop.py` relancé proprement ensuite (reprend l'itération v8
  depuis zéro, coût minime).
- `DOCS/MD/ARCHITECTURE_GANTT_PERT_5S_v2.md` : section 4bis ajoutée (goulot
  RAM 32 Go confirmé, résolu à l'upgrade 64 Go).

## 6. Fin de boucle (2026-08-06, après relance)

La boucle autonome s'est terminée **naturellement** peu après ce rapport,
avant même d'approcher le budget 8h : `File d'attente VMD epuisee` après
l'itération **v9** (`Cry.vmd`, dernier VMD restant). Budget GPU consommé au
moment de l'arrêt : **5,89h/8h** (`gpu_budget_state.json`).

**Bug trouvé et corrigé** : le compteur `cumulative_frames` (cible
14 400 frames) était une variable locale réinitialisée à 0 à chaque
démarrage de `main()` — le redémarrage propre de `run_demo_loop.py` (section
5) l'a donc remis à zéro au lieu de reprendre le total réel déjà produit
(v1-v7). Conséquence : le log affichait `cumul 1544/14400` à la fin de v9
(seulement v8+v9 comptés) au lieu du vrai total. **Vérifié par ffprobe** :
9 vidéos (`v1_fixed` à `v9`) × 772 frames chacune = **6948 frames réelles**
produites au total (48% de la cible 14 400, jamais atteinte — la file VMD
s'est épuisée avant). `DEMO/output/gpu_progress.json` corrigé manuellement
(1544→6948) et `run_demo_loop.py` corrigé pour semer `cumulative_frames`
depuis l'état persisté au lieu de 0 à chaque démarrage — pas d'impact sur ce
run (déjà terminé), mais évite la récidive si la file VMD est réalimentée et
la boucle relancée.

**État final** : boucle terminée, aucun process `run_demo_loop.py` actif.
9 itérations complètes (v1 à v9), 6948 frames finales @24fps produites,
5,89h de budget GPU consommées sur 8h. Reprise possible en ajoutant des VMD
à `DEMO/vmd_queue.json` et relançant `py -3.12 DEMO/run_demo_loop.py`.

# Rapport — Tâches en suspens, oubliées ou jamais refermées (export Claude.ai)

Généré le 2026-07-27 par lecture de l'export `data claude 001/conversations.json`
(18 conversations au total, 14 retenues comme liées au projet Ov3rLoRd après
filtrage par mots-clés — les 4 écartées sont des conversations sans titre,
très courtes ou vides, sans occurrence des mots-clés du projet).

Méthode : extraction texte de chaque conversation retenue, recherche de
signaux d'items en suspens (TODO, "reste à faire", "à ne pas oublier",
"non résolu", pistes mentionnées une seule fois, bugs signalés sans
confirmation), puis vérification manuelle du contexte et, quand possible,
de l'état actuel du dépôt (existence de fichiers, contenu) pour distinguer
ce qui est réellement encore ouvert de ce qui a été résolu depuis sans que
la conversation d'origine le montre. Les 4 points listés comme déjà connus
résolus (FootSegNet publié, Aider+Qwen3-Coder, llm_router.py PR #15,
règle de fragmentation SAM dans quality_sort.py) ont été exclus.

Classement par pertinence probable décroissante, pas chronologique.

---

## Encore clairement actifs / à traiter

### 1. Tournage stéréo réel pour HandSegNet — pas encore fait
**Origine :** "Reprise Ov3rLoRd — diagnostic Control-LoRA et pipeline mouvement", 2026-07-25.
**Dernière mention :** 2026-07-25 (même conversation, jusqu'au 2026-07-27, aucune mise à jour sur ce point précis dans la suite de la session).
Le pivot pipeline 3D→pose (Blender abandonné comme source de masque pixel-exact,
MediaPipe Hands intégré et testé sur vidéo démo) est acté, mais l'étape suivante —
tournage réel de séquences de main (Samsung S10+ 4K60fps + stabilisateur DJI,
calibration stéréo double caméra façon TemugeB/handpose3d) — n'a pas eu lieu :
elle est explicitement conditionnée à la récupération du stabilisateur DJI.
176 masques HandSegNet restent à produire par ce nouveau pipeline (ou par
annotation manuelle en repli).
**Statut :** probablement toujours actif — c'est la prochaine étape planifiée du chantier HandSegNet, pas un oubli, mais reste concrètement non démarré faute de matériel.

### 2. 105 cas de review manuelle FootSegNet (`annotate.py --by-confidence`)
**Origine :** "Reprise Ov3rLoRd — diagnostic Control-LoRA et pipeline mouvement", message du 2026-07-27 (16:39).
**Dernière mention :** 2026-07-27 16:49 — dernier message de la conversation, encore explicitement listé comme "en attente de ta décision".
Après le routage automatique/manuel par confiance SAM (script `route_by_sam_confidence.py`),
105 cas restent à revoir manuellement dans `annotate.py --by-confidence`. Confirmé
par l'assistant lui-même : "je m'arrête ici comme demandé — la review manuelle
des 105 cas reste à faire de ton côté."
**Statut :** actif, le plus récent et le plus concret de tous les points — probablement la tâche la plus immédiatement pertinente.

### 3. Cas SAM score=0.239 dans le lot Control-LoRA (300 images), jamais trié
**Origine :** "Reprise Ov3rLoRd — diagnostic Control-LoRA et pipeline mouvement", message d'ouverture, 2026-07-25.
**Dernière mention :** 2026-07-25 uniquement — mentionné une seule fois ("point d'attention transverse... jamais vérifié/exclu — à traiter à l'occasion"), jamais repris dans le reste de la conversation jusqu'au 2026-07-27.
**Statut :** vraisemblablement toujours en suspens — c'est exactement le type de point mentionné une fois puis perdu de vue que la tâche demandait de repérer.

### 4. Branche `aider-experiments` non mergée sur `main`
**Origine :** "Reprise Ov3rLoRd — diagnostic Control-LoRA et pipeline mouvement", message du 2026-07-27 (16:39-16:43).
**Dernière mention :** 2026-07-27 16:49, dernier message de la conversation — toujours listée comme "pas encore mergée sur main".
Contient le `.gitignore` et `CLAUDE.md` mis à jour, `route_by_sam_confidence.py`
et le fix `quality_sort.py` (fragmentation — celui-ci déjà connu comme résolu
et exclu du présent rapport, mais le merge de la branche entière reste ouvert).
**Statut :** confirmé actif — `git status` au moment de la rédaction de ce rapport montre la branche `aider-experiments` toujours checked-out avec `CLAUDE.md`/`.gitignore` modifiés en local, non mergés.

### 5. Liens Ko-fi / GitHub Sponsors non insérés dans les README FootSegNet
**Origine :** "Reprise Ov3rLoRd — diagnostic Control-LoRA et pipeline mouvement", 2026-07-25 ("priorité à ne pas oublier").
**Dernière mention :** 2026-07-25 ; la mémoire de session confirme que la publication FootSegNet elle-même est allée en ligne le 2026-07-26 mais que les Sponsors restent "en attente".
**Statut :** sous-tâche résiduelle après une publication par ailleurs terminée — toujours ouverte à la date du rapport, mais impact faible.

---

## Probablement encore vrais, mais secondaires

### 6. Ajout du pourcentage de contexte à la statusline Claude Code
**Origine :** "Reprise Ov3rLoRd — diagnostic Control-LoRA et pipeline mouvement", 2026-07-27 16:49 — dernier message de la conversation source.
Décision prise de charger une session libre pour modifier `~/.claude/settings.json`
et le script de statusline existant. Le prompt a été rédigé mais rien n'indique
qu'il ait été exécuté.
**Statut :** ouvert mais mineur (confort d'usage, pas de blocage projet).

### 7. Connecter `audience_analyzer.py`, `style_evolution.py`, `benchmark_arena.py`, `prompt_optimizer.py`, `error_recovery.py` au `context_bus`
**Origine :** "(Projet OVERLORD) : V1.49 - Lock", 2026-06-18 ("feuille de route mise à jour — reste à faire pour clore V1.49").
**Dernière mention :** 2026-06-18 uniquement.
Vérifié à la date du rapport : les 5 fichiers existent bien dans `agents/`,
mais aucun ne référence `context_bus` ou `get_bus()` — le point est donc
factuellement toujours vrai plus d'un mois après.
**Statut :** techniquement encore ouvert, mais daté de la clôture de V1.49 (le projet est aujourd'hui largement au-delà, V228+) — probablement dépassé par l'évolution de l'architecture plutôt qu'un oubli actif à corriger en urgence.

### 8. `output_filter.py` jamais créé (contamination du titre par le sourcing RSS, ex. "Conan")
**Origine :** "Ov3rLoRd initialization et priorités V2.0", 2026-06-23 (table "Bugs PENDING").
**Dernière mention :** 2026-06-23 uniquement.
Vérifié : `agents/output_filter.py` n'existe toujours pas dans le dépôt actuel.
**Statut :** toujours vrai mais periphérique (sourcing RSS, "universe lock partiel"), impact classé "faible" dès l'origine, jamais remonté depuis.

---

## Probablement obsolètes / abandonnés silencieusement

### 9. Roadmap V1.43+ : "interface UI Cyborg-Zen", "Data Armor 3D", "réseau benchmarks Matrix Globe"
**Origine :** "(Archive de référence) : V1.48 - Lock", 2026-06-17 ("Ce qu'il reste à faire (V1.43+)").
**Dernière mention :** 2026-06-17 uniquement — jamais repris dans aucune conversation ultérieure.
Sur les 5 items de cette liste : Reddit OAuth2 semble fait (module `praw`
utilisé dans `agents/transmedia_export.py`), Style DNA Lock semble fait
(`agents/style_dna_generator.py` existe). En revanche, aucune trace dans le
dépôt actuel d'une "UI Cyborg-Zen", d'un "Data Armor 3D" ni d'un "Matrix Globe"
de benchmarks réseau.
**Statut :** probablement abandonné sans décision explicite — plus d'un mois sans remontée, aucun fichier correspondant. À confirmer avant de relancer, plutôt qu'à traiter comme prioritaire.

### 10. "Prompts storyboard encore génériques par moments" (Ollama peut retourner vide)
**Origine :** "Ov3rLoRd initialization et priorités V2.0", 2026-06-23 (table "Bugs PENDING").
**Dernière mention :** 2026-06-23 uniquement.
L'ADR-009 (garantie de fallback script) traite l'échec dur mais pas
nécessairement le caractère générique des prompts réussis.
**Statut :** vraisemblablement toujours vrai à la marge, mais jamais remonté depuis plus d'un mois — signal faible, à re-vérifier seulement si le symptôme réapparaît.

### 11. Mystère des "279 steps" dans un run d'entraînement FootSegNet
**Origine :** "Prioriser les tâches FootSegNet", 2026-07-09.
**Dernière mention :** 2026-07-09, explicitement qualifié par l'assistant lui-même de "reste non résolu mais sans conséquence" (le run final a produit un résultat propre).
**Statut :** curiosité non résolue mais assumée comme sans impact — à classer, ne pas traiter.

---

## Points vérifiés et exclus du rapport (déjà résolus)

- Bug d'import `No module named 'agents'` (2026-06-17) — résolu depuis longtemps, toute l'architecture actuelle en dépend sans problème.
- PR #12 (pipeline Control-LoRA prep) — conflits de merge résolus et PR mergée, confirmé dans la conversation du 2026-07-24.
- Format des keypoints DWPose / `shoe_consistency_checker.py` — la gestion `pose_keypoints_2d` (normalisée ou non) est bien implémentée dans le fichier actuel.
- `ray_cluster.py`, `remote_gpu.py`, agents V1.48 listés comme "à copier" — tous présents dans `agents/` avec une implémentation substantielle (pas des stubs).
- Renommage "Onibaku Gumi" → "OVERLORD" — confirmé effectué avant les PR #11/#12.
- `fix_comfy_free.py` (répétition d'images ComfyUI) — le correctif (`POST /free`) est bien présent dans `maestro.py`.
- llm_router.py / PR #15, publication FootSegNet (GitHub+HuggingFace), setup Aider+Qwen3-Coder, règle de fragmentation SAM dans `quality_sort.py` — exclus sur consigne (déjà connus comme résolus).

---

**Nombre de conversations traitées :** 14 sur 18 (4 écartées par le filtre mots-clés : conversations vides ou sans lien détecté avec Ov3rLoRd).
**Nombre de points en suspens retenus :** 11 (5 actifs/prioritaires, 3 secondaires, 3 probablement obsolètes).

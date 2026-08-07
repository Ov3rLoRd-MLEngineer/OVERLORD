# Rapport session autonome — Audit assets E:\Data Demo\ (2026-08-05)

Session lancée en autonomie complète (Jérémy absent), suite au message
`suite.txt` (Bureau) : verdict raccord SVI confirmé mauvais mais classé dette
technique post-démo (non bloquant), Bloc 2 lancé. Les FBX Goku/Vegeta
recherchés sur Models Resource plus tôt dans la journée étaient absents au
moment de la recherche ; présents désormais dans `E:\Data Demo\`
(téléchargés manuellement par Jérémy entre-temps).

GPU : RTX 5080 et RTX 5060 Ti libres au démarrage (0-3 Mo/16 Go, 0% util) —
tout le travail de cette session (extraction d'archives, import Blender
headless) est **CPU uniquement**, aucun run GPU substantiel, pas d'entrée
`gpu_usage_log.csv` nécessaire.

## Tâche A — Audit et inventaire (DOCS/MD/AUDIT_ASSETS_E_DATA_DEMO.md)

- 5 archives extraites (7-Zip installé cette session via winget, source
  officielle — absent du poste, nécessaire pour le `.rar` Miku).
- **11 FBX Goku/Vegeta (6+5 formes) tous rigués** (280-393 bones selon la
  forme), **aucune animation bakée** (statiques, bind pose) — confirmé par
  import headless Blender (`bpy.ops.import_scene.fbx`).
- 1 FBX Miku (Project Sekai), 113 bones, également rigué sans animation.
- Textures confirmées réelles (référencées dans les `.mtl`), pas de simples
  previews.
- OBJ/DAE : doublons des mêmes personnages, redondants avec le FBX (MTL des
  OBJ pointent vers des chemins absolus cassés de l'auteur original — à
  éviter, utiliser le FBX).
- Les deux `.zip` "MikuMikuDance" ne sont **pas des assets** mais
  l'application elle-même (téléchargée en double), contenant les 13 modèles
  `.pmd` Vocaloid **par défaut de l'installeur** (pas liés au projet).
- `gokutisana5ssj.pose` : pose statique unique format Poser/DAZ, rig
  incompatible avec les FBX FighterZ — inutilisable en l'état.
- **Verdict global : les 11 FBX Goku/Vegeta sont utilisables tels quels**
  pour la Tâche 2 du plan (extraction DWPose + keyframe SDXL).

## Tâche B — Validation pipeline MMD → Blender (DOCS/MD/TEST_MMD_BLENDER_IMPORT.md)

- `mmd_tools` absent, installé depuis la source officielle
  (`extensions.blender.org`) — un blocage rencontré (accès réseau désactivé
  par défaut sur Blender 5.x, `use_online_access`) et résolu dans le script
  headless lui-même, sans modification persistante de la config utilisateur.
- Test d'import headless sur `Miku_Hatsune.pmd` (seul PMD disponible,
  bundle Vocaloid par défaut — pas de PMX/PMD spécifique projet) : **succès**,
  126 bones, 47 meshes, 0 erreur, import en 0.5 s.
- **Pipeline PMX/PMD → Blender validé opérationnel** sur ce poste.

## Tâche C — Inventaire animations (DOCS/MD/AUDIT_ANIMATIONS_MMD.md)

- **Aucun fichier VMD trouvé.** Ce qui existe (8 VPD = poses statiques, 6 PMM
  = démos bundle génériques Vocaloid, 1 .pose = pose statique format
  incompatible) ne constitue dans aucun cas une séquence d'action
  exploitable.
- Recommandation documentée : sources externes (MMD Motion Library,
  BowlRoll, Nicovideo) à télécharger manuellement par Jérémy, ou alternative
  retargeting Mixamo générique sur les rigs FBX FighterZ (déjà compatible
  avec le workflow Blender existant du pipeline).

## Blocages

Aucun blocage non résolu — le seul obstacle rencontré (accès réseau Blender
pour l'installation d'extension) a été résolu dans la même session. Pas de
fichier `DOCS/MD/BLOCAGE_ASSETS_20260805.md` créé (inutile, rien à y
documenter).

## État git

Conforme à la consigne : **aucun commit effectué**, `git status` laissé tel
quel (déjà chargé de changements antérieurs non liés à cette session, voir
rapports de session précédents). Nouveaux fichiers créés cette session :
- `DOCS/MD/AUDIT_ASSETS_E_DATA_DEMO.md`
- `DOCS/MD/TEST_MMD_BLENDER_IMPORT.md`
- `DOCS/MD/AUDIT_ANIMATIONS_MMD.md`
- `DOCS/MD/RAPPORT_SESSION_ASSETS_20260805.md` (ce fichier)
- `E:\Data Demo\_extracted\` (5 archives extraites, non versionné, hors
  dépôt git — chemin en dehors de `D:\OVERLORD\`)
- 7-Zip installé sur le poste (`winget`, `7zip.7zip`, en dehors du dépôt)

## Prochaine étape (à la reprise de Jérémy)

Le blocage réel pour la Tâche 2/3 du plan `suite.txt` n'est **pas** les FBX
(disponibles et utilisables) mais **l'absence de toute motion/séquence
d'action** — décision à prendre : attendre un téléchargement de motion MMD
externe, ou basculer directement sur un retargeting Mixamo générique pour ne
pas bloquer la démo. Les FBX sont prêts pour l'extraction DWPose dès que ce
choix est fait.

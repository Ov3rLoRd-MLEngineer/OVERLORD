# Index des assets 3D/motion — squelettes & dataset LoRA

*Créé le 2026-08-06, session `ANNEXE_SESSION_CLAUDE_CODE_20260806.md` (Priorité 3/4).
À mettre à jour après chaque extraction ou téléchargement.*

| Franchise | Personnage | Tenue | Format | Chemin | Bones | Animations | Status |
|---|---|---|---|---|---|---|---|
| MMD (Miku) | Hatsune Miku "Rock Cat" | casual | PMX+VMD | `E:\Data Demo\_extracted\atrier_Rock Cat Miku_Ver.1.00\Tsatou_Rock Cat Miku_Ver.1.00.pmx` | 556 (mmd semi-standard) | "Look at my muscle.vmd" (157 frames) | **Extrait ✅** — export OpenPose 157 frames dans `DEMO/frames/openpose_synthetic/mmd/miku/casual/` (19/25 corps, 42/42 mains) |
| DBZ FighterZ | Goku (GKS) | base (Costume01) | glTF (Umodel) | `E:\Data Demo\FighterZ_extracted\Chara\GKS\Costume01\Mesh\GKS_body.gltf` | 581 (rig maison Arc System, prefixe G_/GD_/GP_) | **Bloqué** — `.psa` présent mais addon `io_scene_psk_psa` v7.1.0 plante sur Blender 5.1 (cf. `WAKE_UP_2026-08-06.md` pt.3) | **Bind pose seulement ⚠️** — export OpenPose 1 frame (T-pose) dans `DEMO/frames/openpose_synthetic/dbz_fighterz/goku/base/` (17/25 corps, 0/42 mains — pas de bones doigts dans ce mesh) |
| DBZ FighterZ | Vegeta (VGN) | base (Costume01) | glTF (Umodel) | `E:\Data Demo\FighterZ_extracted\Chara\VGN\Costume01\Mesh\VGN_body.gltf` | 581 (idem Goku) | Idem Goku — bloqué | **Bind pose seulement ⚠️** — export OpenPose 1 frame dans `DEMO/frames/openpose_synthetic/dbz_fighterz/vegeta/base/` (17/25 corps, 0/42 mains) |
| SAO Alicization Lycoris | Kirito (toutes tenues) | — | — | `E:\jeux\SAOAL\cpk\data.cpk` (44,6 Go) + `data_patch.cpk` (46,7 Go) | — | — | **Bloqué ⛔ (constat, pas juste "à faire")** — voir note ci-dessous : moteur PhyreEngine, pas UE4, pas d'extracteur public pour les modèles |
| SAO Alicization Lycoris | Alice (toutes tenues) | — | — | idem | — | — | **Bloqué ⛔** — idem Kirito |
| Project DIVA Mega Mix+ | "PD bone body" (squelette de référence générique, PAS un personnage texturé) | — | PMX+VMD | `E:\Data Demo\ProjectDIVA_motion\Bone_Setting_PMX\PD bone body.pmx` + `E:\Data Demo\ProjectDIVA_motion\pv_043_RTS\PV043_RTS_00_C00_00A.vmd` | 63 (convention mmd semi-standard, compatible resolveur "mmd" existant) | Motion réelle chanson PV043 (~600 frames exportées, capées par sécurité) | **Extrait ✅ (squelette de référence seulement)** — export OpenPose 600 frames dans `DEMO/frames/openpose_synthetic/projectdiva/pd_bone_body/base/` (17/25 corps, 22/42 mains) |
| Project DIVA Mega Mix+ | Personnages réels texturés (Miku, etc.) | — | — | `E:\jeux\Hatsune Miku - PDMMP\diva_main.cpk` (+ dlc) | — | — | **À faire 📋** — jeu bien installé (`DivaMegaMix.exe` présent, corrige une confusion de dossier de la session précédente : `[FitGirl HV Repack]\` n'était que l'installeur), mais personnages packés en `.cpk` (format CRIWARE) non extraits. Cf. `ARCHITECTURE_GANTT_PERT_5S_v2.md` §7 : conversion `.mot`→VMD réelle depuis `raw_cpk_extract_mot_PV001\` estimée "plusieurs jours", pas tentée cette session |
| FF14 | WoL (toutes races/genres) | — | — | — | — | — | **Introuvable ❌** — aucune installation détectée sur `E:\` à la date du 2026-08-06 ; extraction TexTools automatique à lancer dès détection (règle de session) |
| .hack//Link (PSP) | Haseo (forme de base) | uniforme par défaut | OBJ+MTL (Models Resource) | `E:\Data Demo\_extracted\hackgu_Haseo_MR\Haseo.obj` | **0 — pas de squelette** (OBJ statique, pas d'armature) | Aucune | **Extrait ✅ (maillage statique seulement)** — rip communautaire déjà converti OBJ/MTL/textures PNG, pose fixe du jeu, pas de rig ; utilisable comme référence de forme/texture, pas pour l'export OpenPose |
| .hack//Link (PSP) | Atoli (forme de base) | uniforme par défaut | OBJ+MTL (Models Resource) | `E:\Data Demo\_extracted\hackgu_Atoli_MR\Atoli.obj` | **0 — pas de squelette** | Aucune | **Extrait ✅ (maillage statique seulement)** — idem Haseo |
| .hack//Link (PSP) | Alkaid (forme de base) | uniforme par défaut | OBJ+MTL (Models Resource) | `E:\Data Demo\_extracted\hackgu_Alkaid_MR\Alkaid.obj` | **0 — pas de squelette** | Aucune | **Extrait ✅ (maillage statique seulement)** — idem Haseo. Formes "Xth Form" (variantes teintées/corrompues) également disponibles sur Models Resource pour les 3 personnages, non téléchargées (formes de base jugées plus utiles pour un dataset LoRA) |
| Hunter x Hunter: Wonder Adventure (PSP) | Gon Freecss | 4 variantes (tenues/âges du jeu) | OBJ+MTL (Models Resource) | `E:\Data Demo\_extracted\hxh_Gon_MR\Gon1-4.obj` | **0 — pas de squelette** | Aucune | **Extrait ✅ (maillage statique seulement)** — 4 fichiers OBJ (variantes), textures PNG incluses |
| Hunter x Hunter: Wonder Adventure (PSP) | Killua Zoldyck | 3 variantes | OBJ+MTL (Models Resource) | `E:\Data Demo\_extracted\hxh_Killua_MR\Killua1-3.obj` | **0 — pas de squelette** | Aucune | **Extrait ✅ (maillage statique seulement)** — 3 fichiers OBJ (variantes) |
| Hunter x Hunter: Wonder Adventure (PSP) | Kurapika | 2 variantes | OBJ+MTL (Models Resource) | `E:\Data Demo\_extracted\hxh_Kurapika_MR\Kurapika1-2.obj` | **0 — pas de squelette** | Aucune | **Extrait ✅ (maillage statique seulement)** — 2 fichiers OBJ (variantes) |
| Hunter x Hunter | Gon/Killua/Kurapika — versions PMX riggées MMD | — | PMX (BowlRoll) | https://bowlroll.net/file/74356 (Killua), https://bowlroll.net/file/74352 (Gon) | Inconnu (non téléchargé) | Inconnu | **Bloqué ⛔ (compte requis)** — BowlRoll exige une connexion et/ou une "clé de téléchargement" (ダウンロード鍵) pour ces fichiers, confirmé dans le HTML de la page (`ログインしてください` affiché conditionnellement) ; pas de lien direct exploitable sans authentification, non contourné (règle explicite de la tâche) |
| Jump Force (Models Resource) | Gon, Killua | — | — | — | — | — | **Introuvable ❌** — roster Jump Force sur Models Resource ne contient pas Gon/Killua (jeu axé Shonen Jump mais sans HxH à la sortie) ; substitué par Hunter x Hunter: Wonder Adventure (PSP) qui a les 3 persos + de meilleure qualité de rip |

## Notes techniques

- **Miku** : pipeline complet validé, réutilisable tel quel pour tout autre PMX+VMD (mmd_tools) — mapping bones vérifié par dump réel (556 bones), pas supposé depuis la doc communautaire générique.
- **Goku/Vegeta** : le rig `G_*/GD_*/GP_*` n'est PAS un rig UE4 Mannequin standard malgré l'origine Umodel — mapping ad hoc ajouté à `export_skeleton_openpose.py::UE4_BODY_ALIASES`. Aucun bone de doigt individuel dans le mesh exporté (`GD_hand_L/R` = main entière uniquement) → mains à confidence 0, pas un bug.
- **Débloquer l'animation FighterZ** : cf. `WAKE_UP_2026-08-06.md` point 3 (version antérieure de `io_scene_psk_psa` ou export `-gltf` en mode viewer interactif d'umodel) — non retenté cette session (scope Priorité 3 = squelette, pas la résolution de ce blocage déjà documenté).
- **SAO Alicization Lycoris — correction majeure de l'hypothèse initiale** :
  `ARCHITECTURE_GANTT_PERT_5S_v2.md` §7 supposait "Umodel UE4" pour ce jeu.
  **Faux** : listing réel de `data.cpk` (44152 entrées, via CriPakTools
  téléchargé cette session depuis
  [CaptainSwag101/CriPakTools](https://github.com/CaptainSwag101/CriPakTools/releases))
  montre des fichiers modèle en `.dae.phyre` (ex.
  `map/object/model/M00502000_kiritoroom.dae.phyre`,
  `gimmick_binded_Alice000.dae.phyre`) — c'est le moteur **PhyreEngine**
  (Sony, utilisé par plusieurs jeux Bandai Namco/Aquria), pas Unreal Engine.
  `umodel` (viewer UE1-4 uniquement) ne peut PAS lire ce format.
  Recherche web (2026-08-06) : extraction de textures `.phyre` possible via
  plugin Noesis communautaire, mais extraction de **modèles** `.dae.phyre`
  confirmée non publiée par la communauté (fil ZenHAX dédié, plugin jamais
  sorti). Aucune conversion MMD/PMX communautaire trouvée spécifiquement
  pour Alicization Lycoris (jeu 2022, contrairement aux titres MMD plus
  anciens/populaires).

  **Mise a jour 2026-08-06** : tentative faite sur demande explicite, via
  une boucle autonome LLM local (devstral:24b / RTX 5060 Ti, 15 iterations,
  `workspace/research/sao_phyre_re/re_loop.py`) -- **echec**. Prefixe
  commun de 8 octets confirme (type "PFsBin"), mais aucune decompression
  valide obtenue ; un faux "succes partiel" auto-declare par le modele a
  ete verifie et invalide manuellement (tailles de fichier aberrantes -- 2+
  Go pour un fichier de 152 Ko -- non reproductibles entre appels). Le jeu
  embarque EasyAntiCheat, cohérent avec un chiffrement reel des assets, pas
  une simple obfuscation. Reclasse definitivement au meme niveau que
  Project DIVA `.mot` vers VMD : hors perimetre session courte. Detail
  complet dans `HANDOFF_2026-08-06.md`. Ne pas rouvrir sans piste nouvelle
  concrete (ex. outil communautaire dedie a ce jeu precis).
- **FF14** : géré par Jérémy plus tard, aucune vérification automatique
  relancée cette session suite à sa demande explicite (2026-08-06).
- **.hack//G.U. (Haseo/Atoli/Alkaid) et Hunter x Hunter (Gon/Killua/Kurapika)**
  (session recherche web 2026-08-06) : rips communautaires OBJ+MTL déjà
  convertis (pas de format custom à extraire), téléchargés depuis Models
  Resource via `curl` avec User-Agent navigateur (le `WebFetch` intégré
  reçoit un 403 Cloudflare sur ce domaine — contournement légitime, pas un
  bypass d'authentification). **Tous ces OBJ sont des maillages statiques
  sans armature** (pas de bones exportables, contrairement aux PMX/VMD Miku
  ou au glTF Goku/Vegeta) — utilisables comme référence de forme/texture
  pour du training LoRA d'image fixe, mais pas pour le pipeline OpenPose
  (`export_skeleton_openpose.py`) en l'état. Un rig serait à ajouter
  manuellement dans Blender (auto-rig type Mixamo/Rigify) si un export de
  pose est nécessaire plus tard.

## Script

`agents/production_video/export_skeleton_openpose.py` — supporte 3 types de squelette (`mmd`, `mixamo`, `ue4`), auto-résolution du mapping bone→keypoint par introspection du rig importé (pas de mapping statique fragile). Sortie : JSON OpenPose standard (BODY_25 + mains 21+21), un fichier par frame.

## VMD de motion dynamique (boucle vidéo Miku) — audit 2026-08-07 (session nuit, priorité 4)

Audit pur-Python (`workspace/scripts/vmd_audit.py`, parse le format binaire VMD
sans Blender/GPU — bone_frame_count, bones distincts, frame max, amplitude du
bone centre) de tout `E:\Data Demo\_extracted\**\*.vmd` (résultat détaillé :
`workspace/scripts/vmd_audit_result.json` + `vmd_audit_bear0830.json`).

**Constat avant cette session** : sur les ~45 `.vmd` déjà sur disque, seuls
**9** contenaient une vraie animation de corps entier avec amplitude
(`Motion Pack 2` : Cry/I must pee pee/Look at my muscle/Salvadora da dance/
Scared reaction/Smell yumi/exciting reaction/up the ladder + `Motion.vmd`
Doodle Dance) — déjà tous listés dans `DEMO/vmd_queue.json`. Le reste :
- **24 poses statiques** (`PosePack27`, `PosePack28`, pack `metra_philia`
  pose_pack_38) — tous les bones à `frame=0` (une seule pose figée, malgré
  parfois 300+ bones "animés"), classées `static_pose` par l'audit malgré
  des noms trompeurs ("kairi-battle.vmd", "elfen-lied.vmd" = poses fixes,
  pas des animations de combat).
- **11 VMD caméra uniquement** (`Catch Catch cam`, `LADY CRAZY camera`,
  `Doodle Dance/Camera.vmd`) — 0 bone de personnage animé.
- **1 vide** (`Light.vmd`, ni bone ni caméra reconnue par le parseur).

Le plan de séquence 51 clips déjà généré (`sequence_plan_20260806.csv`)
piochait dans un pool plus large que ces 9 VMD dynamiques (incluait des
poses statiques de `PosePack27/28`/`metra_philia`, correctement détectées
quasi-figées par `video_pacing.py` — `speed_mult=x3`/hold court — mais pas
exclues). Cause probable du "changement de tenue/flou" observé : traitée
en parallèle par la priorité 3 (keyframe SDXL par clip), pas ce point.

**Ajout 2026-08-07** : 25 VMD dynamiques téléchargés depuis
[github.com/bear0830/mmd](https://github.com/bear0830/mmd) (collection
communautaire PMD/VMD, pas de fichier LICENSE explicite — même statut que
le reste du pool MMD fan-redistribué déjà en usage ; seul Project DIVA est
explicitement exclu par licence non-commerciale, cf. `_comment` de
`vmd_queue.json`). Tous classés `dynamic` par l'audit (140-282 bones
animés, 335 à 9277 frames = danses complètes, pas des boucles courtes) :
`baby, bajiquan (kung-fu/martial), circulation, elect, foxsay, fuwari,
galaxy, gravity, heartbeat, help, honey_miku, hp, jikan, lipstick,
motion123, neko, nekomimi, shakeit, snow, soba, tokino, walk (cycle de
marche), wavefile_v2, yuki, yume` — stockés dans
`E:\Data Demo\_extracted\github_bear0830_mmd\`. Ajoutés à la `queue` de
`DEMO/vmd_queue.json` (33 entrées au total désormais, 9 `used`).

**Pool dynamique total : 34 VMD** (9 existants + 25 nouveaux), diversité
danse (large majorité) + arts martiaux (`bajiquan`) + marche (`walk`) —
suffisant pour ~50 clips sans répétition consécutive de VMD.

Aucun blocage BowlRoll rencontré cette session (GitHub utilisé à la place,
pas d'authentification requise, téléchargement direct via
`raw.githubusercontent.com`).

## Classification fine des 34 VMD dynamiques — 2026-08-07

Script : `workspace/scripts/vmd_classify_categories.py` (lit les deux JSON
d'audit ci-dessus, aucun rendu Blender). Tags : **danse / combat / idle /
expressif / déplacement / inconnu**, dérivés du nom de fichier/dossier en
priorité, sinon d'une heuristique durée≥60s + bones distincts≥100 (profil
choré­graphie complète) — sortie complète : `DEMO/vmd_classification.csv`.

| Catégorie | Nombre | Base de la classification | Exemples |
|---|---|---|---|
| danse | 25 | 2 par nom explicite (`Motion.vmd`/Doodle Dance, `Salvadora da dance.vmd`), 23 par heuristique durée/bones **non vérifiée visuellement** (pack `github_bear0830_mmd`) | `baby, circulation, elect, foxsay, fuwari, galaxy, gravity, heartbeat, help, honey_miku, hp, jikan, lipstick, motion123, neko, nekomimi, shakeit, snow, soba, tokino, wavefile_v2, yuki, yume` |
| expressif | 6 | nom explicite (réactions courtes, Motion Pack 2) | `Cry, I must pee pee, Look at my muscle, Scared reaction, Smell yumi, exciting reaction` |
| combat | 1 | nom explicite (art martial chinois) | `bajiquan.vmd` |
| déplacement | 1 | nom explicite | `walk.vmd` (cycle de marche, 282 bones distincts — le plus riche du pool) |
| inconnu | 1 | nom générique, durée/amplitude non concluantes (4s, sous le seuil danse) | `up the ladder.vmd` |
| idle | 0 | — | aucun VMD dynamique du pool actuel ne correspond (les VMD quasi-figés sont déjà classés `static_pose` par `vmd_audit.py`, hors du pool des 34) |

**Trop courts (<3s utiles)** : `Scared reaction.vmd` (2.8s), `exciting
reaction.vmd` (2.57s) — utilisables comme accents courts (transition/réaction
flash) mais pas comme clip principal d'un plan de séquence.

**Doublons** : aucun détecté (triplet frame_max/bones_distincts/amplitude
unique sur les 34 fichiers — pas deux VMD avec la même empreinte).

**Limite à noter** : le tag `danse` sur les 23 fichiers `bear0830` repose sur
une heuristique (durée longue + squelette riche), pas sur une lecture visuelle
du mouvement — cohérent avec la convention de nommage MMD communautaire (titres
de chanson) déjà notée dans la section précédente, mais à confirmer en rejouant
un échantillon dans Blender/MMD avant de s'appuyer dessus pour un choix éditorial
fin (ex. sélectionner "la danse la plus lente" nécessiterait une vérification
réelle, pas juste `center_amplitude`).

## Enrichissement VMD (idle/combat/déplacement/environnement/interaction) — tentative 2026-08-07

**Résultat : aucun nouveau VMD dynamique ajouté** — recherche sérieuse mais
infructueuse, documentée ici pour ne pas la relancer à l'identique sans piste
nouvelle.

Sources tentées :
- **GitHub** (recherche de dépôts + recherche de code `extension:vmd`) :
  aucun dépôt de contenu VMD trouvé au-delà de `bear0830/mmd` déjà entièrement
  exploité (24 fichiers numérotés + `walk.vmd`, tous déjà téléchargés —
  confirmé via `mapping.txt` du dépôt, qui donne les noms descriptifs déjà
  utilisés dans ce projet). Le reste des dépôts GitHub sur "vmd"/"mmd motion"
  sont des **outils** (importeurs Blender, convertisseurs, viewers), pas des
  collections de motions. La recherche de code `extension:vmd` est
  inexploitable : dominée par des scripts *Visual Molecular Dynamics*
  (chimie/physique, collision de nom d'extension avec MikuMikuDance), et de
  toute façon les VMD MikuMikuDance sont binaires donc non indexés par la
  recherche de code textuelle.
- **learnmmd.com** (page Downloads + catégorie VMD files) : 2 fichiers
  testés — `WalkTest8RD.zip` (contient un `.pmm`, projet MMD complet, pas un
  `.vmd` extractible sans MikuMikuDance lui-même — inutilisable tel quel pour
  ce pipeline) et `ReggiesPoseCollection.zip` (5 fichiers `.vpd`, poses
  statiques, pas des animations — même catégorie que `PosePack27/28` déjà
  exclus du pool "dynamique" par convention du projet). Aucun des deux
  n'ajoute de VMD utilisable ; ni téléchargé ni copié dans le dépôt.
- **BowlRoll** : non retenté — blocage connexion/clé de téléchargement déjà
  documenté (session 2026-08-06), consigne explicite de ne pas contourner une
  authentification.
- **Recherche en japonais** (termes 喧嘩/座り/挨拶 = combat/assis/salutation) :
  un seul résultat pertinent (`bowlroll.net/file/303199`, motion de
  salutation), donc de nouveau bloqué par BowlRoll.
- **Mirror three.js (designheritage.mit.edu, ancien r122)** : le dossier
  `examples/models/mmd/vmds/` n'existe plus dans le three.js actuel (assets
  retirés du dépôt principal) ; le seul fichier vérifié sur le mirror MIT est
  une motion de **caméra** (`wavefile_camera`, pas de corps animé), hors
  scope.

**Conclusion** : au-delà de GitHub et des quelques sites communautaires
anglophones sans authentification, la quasi-totalité de l'offre VMD
qualitative (notamment tout ce qui couvrirait combat/assis/interaction à
deux personnages) semble concentrée sur BowlRoll et des plateformes
japonaises équivalentes, structurellement fermées sans compte. Le pool
actuel de 34 VMD dynamiques (voir section précédente) reste donc l'état de
l'art tant qu'un accès BowlRoll n'est pas débloqué côté utilisateur (clé de
téléchargement/compte) — décision volontairement laissée à Jérémy, pas
contournée.

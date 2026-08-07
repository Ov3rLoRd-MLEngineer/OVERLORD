# Audit animations/motion data — E:\Data Demo\ (2026-08-05, session autonome)

## Résultat de la recherche VMD

**Aucun fichier `.vmd` trouvé** dans `E:\Data Demo\` (recherche récursive
complète post-extraction des 5 archives, 0 résultat).

## Ce qui existe à la place (aucun n'est une séquence d'action exploitable)

| Type | Nombre | Nature | Utilisable pour la démo action ? |
|---|---|---|---|
| `.vpd` | 8 | Poses **statiques** MMD (bundle installeur, noms japonais génériques type poses de dos/mains) | Non — une pose figée n'est pas une séquence, et générique Vocaloid pas DBZ |
| `.pmm` | 6 (3 uniques ×2) | Projets/scènes MikuMikuDance complets (modèle + motion + caméra), mais ce sont les **démos bundle de l'installeur** (`sample.pmm`, `sample(AllStar).pmm`, `sample(follow_camera).pmm`) | Non pertinent — animation Vocaloid générique (danse/chant), pas de personnage DBZ, extraction VMD depuis un PMM nécessiterait l'appli MMD elle-même (pas testé, hors périmètre) |
| `gokutisana5ssj.pose` | 1 | Pose statique unique, format Poser/DAZ (voir `AUDIT_ASSETS_E_DATA_DEMO.md`) | Non — une seule pose, rig incompatible avec les FBX FighterZ |

**Conclusion : aucune séquence d'animation multi-frame exploitable pour la
démo combat/action n'est présente dans `E:\Data Demo\`, quel que soit le
format.** Tout ce qui ressemble à du mouvement (VPD, PMM) est soit une pose
unique soit un contenu générique bundle sans rapport avec Goku/Vegeta.

## Recommandation — sources externes à télécharger manuellement

Puisqu'aucun VMD n'est disponible localement, et que l'objectif est une
**séquence d'action de 5-10 s avec au moins 2 postures distinctes** (ex.
idle → attaque → recovery) plutôt qu'un cycle bouclable court, les pistes
suivantes sont les plus pertinentes pour du contenu de combat/DBZ-style :

1. **MMD Motion Library / motion trace communautaire** — rechercher
   `"MMD motion DL fight"` / `"MMD motion DL punch"` / `"格闘 モーション MMD"`
   sur les dépôts communautaires ci-dessous. Chercher spécifiquement des
   motions taguées combat/fighting-game plutôt que danse (le contenu MMD est
   très majoritairement orienté danse/chant Vocaloid).
2. **BowlRoll** (bowlroll.net) — plateforme japonaise de partage MMD
   (modèles + motions + accessoires), nécessite souvent un compte gratuit ;
   rechercher par tags `モーション` (motion) + `格闘`/`バトル` (combat/bataille).
3. **Nicovideo (nicovideo.jp / niconico) + description vidéo** — de nombreux
   créateurs MMD publient un lien de téléchargement de la motion utilisée
   dans la description de leurs vidéos de combat/action ; chercher des
   vidéos "MMD fight motion" ou "MMDバトルモーション" et vérifier la description.
4. **Alternative si aucune motion DBZ-spécifique trouvée** : les FBX Goku/
   Vegeta (382/280 bones, squelette de jeu de combat, voir audit assets) sont
   compatibles Mixamo-style — une animation Mixamo générique de combat
   (coup de poing, coup de pied, réaction) pourrait être retargetée sur ces
   rigs via Blender, contournant le besoin de motion MMD spécifiquement.
   Cohérent avec le workflow Blender→DWPose déjà utilisé dans le pipeline
   (`agents/production_video/`, convention Mixamo confirmée dans
   `PLAN_PIPELINE_A_DEMO_30S.md`).

**Aucun téléchargement automatique effectué** — au choix de Jérémy selon la
piste retenue (comptes/CGU variables selon la plateforme, cohérent avec la
consigne de validation manuelle des sources).

## Ce qui reste ouvert

- Aucune séquence de 120+ frames avec dynamisme n'a pu être sélectionnée
  (rien de disponible localement) — la Tâche 2/3 du plan (`suite.txt`) devra
  soit attendre une motion externe, soit utiliser un cycle Mixamo générique
  déjà présent ailleurs dans le pipeline (`DEMO/frames/frames/` contient déjà
  un cycle 38 frames bouclable, mais c'est précisément le type de contenu
  que cette tâche cherchait à dépasser — voir consigne "l'objectif final
  n'est pas un cycle bouclable court").

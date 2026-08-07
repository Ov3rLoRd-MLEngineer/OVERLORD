# Test import MMD → Blender (mmd_tools) — 2026-08-05, session autonome

## Contexte

Pas de fichiers PMX dans `E:\Data Demo\`, mais 13 fichiers `.pmd` (bundle
Vocaloid par défaut de l'installeur MikuMikuDance v9.32 — voir
`DOCS/MD/AUDIT_ASSETS_E_DATA_DEMO.md`). Test retenu sur `Miku_Hatsune.pmd`
(modèle officiel Vocaloid le plus représentatif, 474 Ko) pour valider le
pipeline d'import, indépendamment de la pertinence pour la démo DBZ.

## Étape 1 — Vérification addon `mmd_tools`

**Absent** de l'installation Blender 5.1.2 de ce poste
(`bpy.context.preferences.addons` vide pour toute clé contenant "mmd").

### Installation effectuée

Source officielle : dépôt d'extensions intégré à Blender
(`extensions.blender.org`, "MMD Tools" par l'équipe MMD-Blender,
https://extensions.blender.org/add-ons/mmd-tools/) — pas de zip GitHub tiers
téléchargé manuellement, installation via le gestionnaire d'extensions natif.

Blocage rencontré puis résolu : `bpy.ops.extensions.package_install()` a
échoué au premier essai —
`RuntimeError: Online access required to install or update. Enable online
access in System preferences` (nouvelle protection vie privée de Blender
4.2+/5.x, accès réseau désactivé par défaut). Résolu en activant
`bpy.context.preferences.system.use_online_access = True` **dans le même
script Python headless** avant l'appel à `package_install` — changement non
persisté (pas de `wm.save_userpref()` appelé, `--factory-startup` ignore de
toute façon les préférences utilisateur sauvegardées), donc sans effet sur
la configuration Blender de l'utilisateur en dehors de ce test.

Installation réussie : `bpy.ops.extensions.package_install(repo_index=...,
pkg_id="mmd_tools")` → `{'FINISHED'}`, module enregistré sous
`bl_ext.blender_org.mmd_tools`. Note de compatibilité : la page officielle
annonce un support Blender 4.2 → 5.0 ; testé et fonctionnel sur **Blender
5.1.2** (aucune erreur rencontrée sur ce test précis), à garder en tête si
un comportement plus avancé de l'addon (physique, morphs complexes) posait
problème plus tard.

## Étape 2 — Test d'import headless

Commande :
```
blender --background --factory-startup --python test_mmd_import.py -- "Miku_Hatsune.pmd"
```

Script : active l'addon (`bpy.ops.preferences.addon_enable`, nécessaire à
chaque lancement headless puisque `--factory-startup` ne charge pas l'état
"addons activés" sauvegardé), puis
`bpy.ops.mmd_tools.import_model(filepath=..., types={"MESH", "ARMATURE",
"PHYSICS", "MORPHS", "DISPLAY"})`.

### Résultat : succès, aucune erreur

Log interne mmd_tools confirmé :
- Conversion PMD → PMX interne réussie ("Finish converting pmd into pmx"),
  45 rigid bodies + 27 joints convertis (physique de cheveux/jupe MMD
  standard).
- 10 faces nettoyées automatiquement (doublons mineurs, normal pour un
  modèle de 2013).
- IK mis à jour sur 7 chaînes (cheveux ×2, cravate, genoux/chevilles ×2) —
  comportement standard mmd_tools, pas une erreur.
- **Import final : 0.5 s.**

### Vérification squelette (bones count > 0)

| Métrique | Valeur |
|---|---|
| Armature | 1 |
| **Bones** | **126** (> 0, conforme au critère de validation demandé) |
| Meshes | 47 (MMD découpe par matériau, normal) |
| Vertices totaux | 10 132 |
| Erreur | Aucune |

## Verdict

**Pipeline MMD (PMD) → Blender opérationnel** sur ce poste, addon installé
et fonctionnel via la voie officielle. Testé uniquement sur un modèle
Vocaloid bundle (pas de PMX/PMD spécifique au projet DBZ disponible) — si
Jérémy fournit un jour un modèle PMX/PMD spécifique (Goku/Vegeta MMD-style),
le même script (`test_mmd_import.py`, conservé) devrait fonctionner à
l'identique. Non testé : import VMD (aucun fichier VMD disponible, voir
`DOCS/MD/AUDIT_ANIMATIONS_MMD.md`), export vers un format intermédiaire
utilisable par le reste du pipeline Ov3rLoRd (FBX/glTF) — mmd_tools sait le
faire (`mmd_tools.export_pmx` / Blender export FBX natif après import) mais
pas vérifié dans ce test.

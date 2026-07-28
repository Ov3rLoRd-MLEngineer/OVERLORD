# Structure de classes — prototype pipeline 3D HandSegNet

Extraite du buffer Object Index Blender (voir `build_and_render.py`). Chaque classe
correspond a un `pass_index` distinct assigne aux objets 3D de la scene ; le rendu
produit un masque binaire separe par classe en plus du mask couleur combine et de
la silhouette union (mono-classe, pour comparaison directe au dataset HandSegNet
reel actuel qui est mono-classe "hand").

| id | classe      | objets 3D couverts                          | fichier de sortie              |
|----|-------------|----------------------------------------------|---------------------------------|
| 1  | wrist       | boite poignet                                | `seg_class_1_wrist.png`         |
| 2  | palm        | boite paume                                   | `seg_class_2_palm.png`          |
| 3  | thumb       | 3 phalanges pouce                             | `seg_class_3_thumb.png`         |
| 4  | index       | 3 phalanges index                             | `seg_class_4_index.png`         |
| 5  | middle      | 3 phalanges majeur                            | `seg_class_5_middle.png`        |
| 6  | ring        | 3 phalanges annulaire                         | `seg_class_6_ring.png`          |
| 7  | pinky       | 3 phalanges auriculaire                       | `seg_class_7_pinky.png`         |

Sorties supplementaires (non-classes, pour verification/compat) :
- `seg_idcolor.png` — les 7 classes superposees en fausses couleurs (verif visuelle rapide)
- `seg_binary.png` — union des 7 classes = silhouette "main" complete, meme convention
  que le masque mono-classe HandSegNet actuel (BLANC=main, NOIR=fond)

## Pourquoi ce decoupage (poignet / paume / 5 doigts individuels) et pas plus fin

Correspond exactement a la demande : distinguer poignet, paume, et chaque doigt
individuellement — pas de decoupage par phalange (proximale/intermediaire/distale
par doigt, ce qui donnerait 17 classes). Les 3 phalanges d'un meme doigt partagent
le meme `pass_index` : elles sont fusionnees en une seule classe "doigt".

Avec l'annotation manuelle, rester mono-classe etait un choix delibere pour limiter
le cout (cf. `handsegnet/README.md`, "future extension multi-classes... reintroduirait
un masque par categorie, comme avant ce changement"). Avec le rendu 3D, ce cout
n'existe quasiment plus : passer a 7 classes n'a demande qu'un `pass_index` different
par objet + une passe de rendu de plus par classe (~0.7s/classe sur cette scene de
test) — d'ou la decision d'exploiter cette granularite des maintenant plutot que
d'attendre. Si un besoin de granularite par phalange apparait plus tard (ex. pour
un futur rig avec flexion articulee par phalange), le meme mecanisme s'etend
directement en donnant un `pass_index` propre a chaque phalange au lieu de le
partager par doigt — aucun changement structurel necessaire, juste plus d'ID.

## Occlusion

Le buffer Object Index reflete ce qui est reellement visible depuis la camera :
quand le pouce passe devant la paume, le pixel appartient au pouce dans le mask
paume ET dans le mask pouce (pas de double-compte, pas de fuite) — verifie
visuellement sur `seg_class_2_palm.png` (encoche a l'endroit ou le pouce recouvre
la paume). Ce comportement correct-par-construction est un avantage direct du
rendu 3D par rapport a l'annotation manuelle multi-classe (qui devrait gerer les
occlusions a la main, polygone par polygone).

## Limite actuelle (assumee, hors-scope de cette etape)

Le style visuel reste du rendu 3D brut (pas de cel-shading), et la geometrie est
un proxy schematique (boites + ellipsoides), pas un mesh anatomique detaille.
Ces deux points sont le "domain gap" deja identifie dans
`ADDENDUM_PISTES_FUTURES_V3_JUILLET2026.md` et restent volontairement non
attaques a cette etape (consigne : rester concentre sur la geometrie propre +
structure multi-classe avant le style visuel).

## Mise a jour v3 (2026-07-28) : proxy geometrique en metaballs

Le point ci-dessus ("geometrie = proxy schematique boites + ellipsoides") a ete
attaque et en grande partie resolu par `build_and_render_v3.py`. Diagnostic
precis pose la session precedente (memoire projet `blender-3d-segnet-pivot`,
verdict du calibrage cel-shading) : ce n'etait pas le shader qui bloquait mais
les jointures boite/ellipsoide - chaque phalange ellipsoide restait une surface
distincte qui se touche a peine ("collier de perles"), et le poignet/la paume
en boites avaient des angles droits inexistants en anatomie reelle. Sous
Freestyle, ces jointures/angles artificiels etaient dessines comme des aretes
qui ne correspondent a rien de reel.

**Fix v3** : chaque classe (poignet, paume, chaque doigt) devient un objet
METABALL (surface implicite qui fusionne nativement a l'intersection) au lieu
d'un ou plusieurs objets mesh. Chaque doigt = 3 elements CAPSULE dans le MEME
objet metaball (fusion interne continue, effilee vers la pointe, plus de bosse
par phalange). Poignet/paume = 1 element ELLIPSOID chacun (arrondi, plus
d'angle droit). Comparaison directe `render_beauty.png`/`render_celshaded.png`
avant/apres dans ce dossier (ecrases par la derniere execution - v2 archive
dans `build_and_render.py`, non touche, reste la version "boites+ellipsoides"
de reference si besoin de comparer a nouveau).

Toujours 7 objets **separes** (pas un metaball global pour toute la main) :
deliberement choisi, pas une limite - fusionner tout en un seul objet aurait
aussi fusionne les FRONTIERES entre classes, hors de propos ici car (1)
`MetaElement` n'a pas de `material_index` dans cette version de Blender (verifie
empiriquement) donc pas d'alternative pour retrouver les 7 masques autrement
qu'avec l'Object Index actuel (qui reste une propriete PAR OBJET), et (2) une
ligne visible base-de-doigt/paume ou poignet/paume correspond a une vraie
crease anatomique, contrairement aux bosses intra-doigt qui, elles, ne
correspondaient a rien de reel - le probleme cible etait specifiquement
intra-partie.

**Piege technique rencontre et corrige** : un element metaball ISOLE (sans
voisin pour renforcer le champ pres du bord) rend a environ 55% de sa taille
`size_x/y/z` nominale au seuil (`threshold`) par defaut de 0.6 - mesure
empirique : 0.6->~55%, 0.3->~74%, 0.1->~85% de la taille demandee. Poignet et
paume (chacun un seul element) laissaient donc un vrai vide visible entre eux
et avec les doigts au premier rendu v3. Fix : `threshold=0.3` sur ces deux
objets + demi-extents elargis avec une marge de recouvrement volontaire (meme
principe que `OVERLAP` pour les capsules de doigt, qui elles n'avaient pas ce
probleme car deja chevauchantes par construction).

**Piege Freestyle rencontre et corrige** : le maillage d'un metaball est
tessellise par marching cubes - meme lisse en apparence, les facettes creent
de petits angles reels entre polygones que Freestyle "crease" detecte comme
bruit parasite (petits traits epars le long des doigts). Le sens du parametre
`crease_angle` est contre-intuitif : une valeur PLUS HAUTE rend la detection
PLUS sensible (170 deg a produit un hachurage dense, pire que le defaut
~150 deg) - abaisse a 100 deg pour n'accrocher que les vraies cassures.

**Bug distinct trouve et corrige dans la meme session** : les 5 doigts
convergeaient tous au MEME point au premier essai (bug herite de v2, pas
introduit par le passage aux metaballs : `EditBone.use_connect=True` force le
`head` de l'os enfant a coincider avec le `tail` du parent, ce qui ecrasait
silencieusement les positions `base` individuelles par doigt definies dans
`FINGER_SPECS` - confirme via introspection directe des bones apres
construction). Fix : `use_connect=False` pour la 1ere phalange de chaque
doigt uniquement (sa base n'est pas la pointe de la paume, contrairement aux
phalanges suivantes qui elles s'enchainent reellement) - `b.use_connect =
(i > 0)` dans `build_rig()`. Resultat : doigts repartis le long de la largeur
de la paume, pouce positionne sur le cote comme une vraie main, au lieu d'un
eventail issu d'un point unique.

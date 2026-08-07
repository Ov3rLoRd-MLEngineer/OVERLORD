# ADDENDUM V3 — Pivot stratégique : pipeline 3D synthétique

Mise à jour de ADDENDUM_PISTES_FUTURES_V2_JUILLET2026.md. Contient une
décision de priorisation majeure (nouveau chantier n°1) + état d'avancement
complet des travaux en cours. À transmettre à Claude Code.

---

## DÉCISION STRATÉGIQUE — Nouvelle priorité n°1

**Pivot validé : le pipeline de génération de données synthétiques via
rendu 3D devient la priorité de développement immédiate**, avant de
finir l'annotation manuelle de HandSegNet à la main.

### Raisonnement (débattu et tranché dans cette session)

- HandSegNet, réalisé par annotation manuelle comme FootSegNet, ne
  démontre techniquement rien de nouveau pour le portfolio — c'est une
  répétition de la même méthode déjà prouvée. Pas d'urgence à le finir
  ainsi.
- Un pipeline de génération de vérité terrain automatique (masques 3D →
  2D sans travail de stylet) est une compétence différenciante bien plus
  forte : ça résout structurellement le vrai goulot d'étranglement de
  tout le projet (le temps d'annotation manuelle), pour tous les SegNets
  présents et futurs, pas juste un seul.
- Les 124 masques HandSegNet déjà annotés à la main ne sont PAS perdus —
  vérité terrain valide et réutilisable quel que soit le pipeline qui
  complète les 176 restants plus tard.
- Budget de risque confirmé large : ~36 jours avant la deadline
  personnelle de fin août, quota Claude Code confortable, crédit
  promotionnel disponible (~85€, à vérifier la portée exacte dans les
  paramètres de facturation), possibilité de mobiliser Fable 5 si
  nécessaire pour les tâches les plus exigeantes.
- Réserve maintenue (pas résolue, juste acceptée comme risque géré) :
  aucune brique technique de ce chantier n'a encore été testée
  (rig+groom capillaire+export de buffer de segmentation+calibration
  cel-shading+orchestration Blender-MCP) — plusieurs inconnues cumulées,
  risque de sous-estimation du temps réel. Le budget temporel large sert
  justement de filet pour ce risque, pas une négation du risque.

### Cible initiale du prototype : HandSegNet (pas Foot ni Full Body)

Choix justifié : la main est l'objet 3D le plus complexe à rig-and-groom
correctement (~21 os articulés pour les doigts seuls, déformations de
peau non triviales). Réussir la démonstration sur ce cas le plus dur
prouve la méthode de façon robuste — elle s'appliquera d'autant plus
facilement ensuite à pied/corps/visage, structurellement plus simples.
Choix qui, en prime, referme la boucle HandSegNet "par le haut" plutôt
que par la complétion manuelle.

---

## Pipeline 3D synthétique — architecture envisagée (à détailler/tester)

### Principe général
Génération de vérité terrain par rendu 3D contrôlé : si chaque partie
anatomique (main, doigts, cheveux, etc.) est un objet 3D identifié
séparément dans la scène, le moteur de rendu peut produire un **buffer
de segmentation parfait** en même temps que l'image — masque gratuit,
zéro travail de stylet. Principe déjà établi en recherche ML (cf.
datasets synthétiques type SURREAL/BEDLAM pour humains synthétiques).
Généralisable à TOUS les futurs SegNets (foot, hand, face, body) et à
des axes annexes (mouvement capillaire, flux de vêtement, rotation
d'objets, flux d'air) — pas seulement les mains.

### Le vrai piège technique identifié : le "domain gap"
Un modèle entraîné uniquement sur des rendus 3D bruts ne généralisera
probablement pas bien sur les vraies images SDXL en style anime plat du
pipeline (même problème que "SAM générique entraîné sur photos réelles
généralise mal sur anime", qui a motivé FootSegNet au départ). Deux
approches identifiées, à arbitrer par le test :

1. **Cel-shading calibré poussé** — rapprocher le rendu 3D du style
   visuel SDXL réel du pipeline (fabricatedXL) autant que possible côté
   shader, pour que le masque ET l'image de référence servent
   directement à l'entraînement. Applicable en théorie aussi au
   photoréalisme (calibrer vers un autre style cible).
2. **Le 3D comme guide de mouvement/pose uniquement** — le rendu 3D ne
   sert que de référence structurelle (via ControlNet), l'image finale
   reste générée par SDXL classique ; pas de masque pixel-exact direct
   depuis le rendu, mais pas de problème de domain gap non plus.

### Extension identifiée en cours de réflexion : Onibi 3D
Une fois le LoRA "Onibi" entraîné et stable (cohérence de personnage,
construite par sélection d'images + inpaint + LoRA classique — méthode
déjà actée), il devient possible de construire un modèle 3D riggé de la
mascotte et de lui appliquer la texture visuelle apprise par le LoRA —
analogue au pipeline VTuber, mais avec un rendu visuel bien plus qualitatif
et fidèle au style du LoRA plutôt qu'un rig 3D générique.

### Prérequis techniques à vérifier/construire (ordre suggéré)
1. Test de faisabilité minimal : un seul objet riggé simple (une main),
   export d'un buffer de segmentation depuis Blender, comparaison
   visuelle brute avant tout travail de shader.
2. `blender-mcp` — déjà identifié dans le contexte comme piste
   ("Claude pilote Blender via MCP"), à activer/tester concrètement
   pour automatiser le pipeline de rendu.
3. Setup capillaire physique (Hair/Particle system Blender) pour l'axe
   mouvement de cheveux, en parallèle ou après le prototype main.
4. Calibration du cel-shading vs échantillon réel du dataset FootSegNet/
   HandSegNet existant, pour mesurer objectivement le domain gap avant/
   après.

---

## FAIT depuis la dernière note (V2)

- **Ollama déplacé** : modèles migrés de `C:\Users\Ov3rL0rD\.ollama\` vers
  `D:\OVERLORD\ollama_models`, variable `OLLAMA_MODELS` positionnée
  (`setx`), fichiers physiquement transférés (37Go).
- **Régénération HandSegNet terminée** : 98/98 images régénérées avec le
  LoRA anti-mains-difformes (sdxl-wrong-lora, poids 0.5) intégré à
  `generate_dataset.py`, 0 échec. Dataset complet à 322/322 fichiers sur
  disque. Manifest trace la provenance LoRA par image. Isolation GPU1
  confirmée de bout en bout, GPU0/training jamais impacté.
- **Test LoRA anti-mains-difformes validé** : méthodologie rigoureuse sur
  12 seeds reproduits à l'identique (baseline vs LoRA), 33% d'amélioration
  nette, 0% de dégradation, poids 0.5 = 0.7 (pas de différence
  perceptible) → 0.5 retenu.
- **Training Control-LoRA FootSegNet en cours** : bug de scheduler
  partagé (stateful, pollué par la validation) diagnostiqué et corrigé
  (scheduler dédié pour la validation), mécanisme `--resume-from-checkpoint`
  ajouté et validé. Run relancé depuis checkpoint-500, dépassé step 1000/2000
  sans nouveau crash au moment de la rédaction. Loss stable en descente
  progressive (~0.10-0.19).
- **Protocole de délégation locale (Ollama)** : posé plusieurs fois,
  jamais encore déclenché faute de tâche assez mécanique/bornée pour le
  justifier honnêtement (l'agent a refusé de forcer l'usage sur une tâche
  qui ne s'y prêtait pas — bon signal de fiabilité du protocole).
- **IPAdapter clarifié** : outil de transfert de style/apparence à partir
  d'une image de référence (pas un outil de mouvement). Pertinent pour la
  cohérence Onibi (image de référence fixe recommandée, éviter le
  "drift"). Le mouvement capillaire reste hors de portée d'IPAdapter —
  d'où la piste 3D synthétique ci-dessus.
- **LoRA candidats identifiés pour la suite** (téléchargement en cours/à
  faire, sources vérifiées) : Detail Tweaker XL (Civitai #122359),
  unaestheticXL Negative TI (Civitai #119032), Perfect Eyes XL (Civitai
  #118427, utile pour FaceSegNet), DetailedEyes_XL (Civitai #120723).

---

## Points d'attention ouverts (reportés de V2, toujours valables)

1. Liens Ko-fi/GitHub Sponsors à insérer dans les README dès approbation.
2. Extraction du repo GitHub public FootSegNet — toujours pas fait.
3. Upload effectif sur HuggingFace — compte créé, rien encore uploadé.
4. Cas SAM score=0.239 dans le lot Control-LoRA de 300 — à vérifier/exclure.
5. **HandSegNet reste à 124/300 annoté manuellement + 98 nouvelles
   images régénérées non annotées** — repris uniquement une fois le
   pipeline 3D synthétique opérationnel (ou en parallèle si le temps
   déborde vraiment), pas abandonné.

## Nouveau point ouvert

6. **Agent local de supervision pendant les creux de quota Claude Code**
   — évoqué comme filet de sécurité pour le chantier 3D (garder ~20% du
   quota Claude Code pour la supervision d'un agent local pendant les
   phases de recharge). Lié à la piste "LoRA expert du projet"/Unsloth
   Studio déjà notée, mais avec un usage plus immédiat et concret cette
   fois (continuité de développement, pas juste un outil en réserve) —
   à prioriser en parallèle du démarrage du chantier 3D plutôt qu'après.

# QC anatomique automatisé — audit de licences (2026-07-29)

Objectif de session : valider le domain gap anime pour un futur filtre QC
anatomique automatisé (détection de mains/membres malformés), en commençant
par un test zero-shot sur HADM. **Le test zero-shot n'a pas pu être lancé**
— bloqué à l'étape de vérification des licences avant tout téléchargement,
sur deux modèles successifs. Aucun poids téléchargé, aucune inférence
lancée, aucune modification du pipeline de production.

## 1. HADM (github.com/wangkaihong/HADM) — écarté

- **Licence : aucune détectée.** `gh api repos/wangkaihong/HADM` → `license: None`.
  Pas de fichier `LICENSE`, aucune mention dans le README, poids hébergés
  sur Dropbox (pas de tag de licence HuggingFace/GitHub associé). Droits
  réservés par défaut — pas d'autorisation d'usage/redistribution, même
  interne, sans contact avec l'auteur.
- **Environnement lourd et daté** (secondaire, non bloquant en soi mais
  confirme que la piste était coûteuse) : `conda python=3.8`,
  `torch==1.12.1+cu116`, `apex`, `deepspeed==0.6.5`, `mmcv-full`,
  `xformers` figé à `v0.0.18` — stack CUDA 11.6 de 2022, support GPU
  Blackwell (RTX 5080/5060 Ti) non garanti sans reconstruction complète.

## 2. Alternatives identifiées (rapport d'audit de la veille) — vérifiées directement

Vérification **directe** (contenu réel du fichier `LICENSE` de chaque dépôt,
pas seulement le tag GitHub auto-détecté — celui-ci s'est justement révélé
trompeur pour MeshGraphormer, voir §3) :

| Dépôt | Licence GitHub (tag auto) | Licence réelle (fichier LICENSE lu) |
|---|---|---|
| `ali-vilab/DiffDoctor` | MIT | MIT confirmé (Copyright 2025 Alibaba TongYi) |
| `wenquanlu/HandRefiner` | MIT | MIT confirmé (Copyright 2023 Wenquan Lu) |

Les deux sont propres. Choix de continuer avec **HandRefiner** en priorité
(spécifique mains, torch 2.0.0 — plus léger que HADM, colle directement aux
patterns déjà documentés dans `LIMITATIONS_CONNUES.md` : mirroring,
décrochage de doigts).

## 3. HandRefiner — bloqué à son tour, sur une dépendance transitive

HandRefiner (MIT) s'appuie sur **MeshGraphormer** (Microsoft) pour la
reconstruction du mesh 3D de la main — c'est cette étape de reconstruction
qui sert de signal de détection (une main dont le mesh ne se fitte pas
correctement est le signal de malformation).

- **MeshGraphormer** : tag GitHub auto-détecté = `None`, mais le fichier
  `LICENSE` réel est bien MIT (Copyright Microsoft Corporation) — juste mal
  reconnu par le détecteur GitHub (indentation inhabituelle). Le code est
  donc utilisable.
- **MAIS le modèle de main pré-entraîné (`graphormer_hand_state_dict.bin`,
  entraîné sur FreiHAND) nécessite `MANO_RIGHT.pkl`**, téléchargeable
  uniquement après création d'un compte et acceptation de licence sur
  [mano.is.tue.mpg.de](https://mano.is.tue.mpg.de/license) — licence
  **"Software Copyright License for non-commercial scientific research
  purposes"** (texte exact du README MeshGraphormer, section License).
- **Deux problèmes concrets** :
  1. L'enregistrement/acceptation de licence MANO est une action
     personnelle (compte, identité, clic d'acceptation) — je ne peux pas
     la faire à ta place.
  2. Même une fois obtenu, ce poids resterait sous licence non-commerciale
     — incompatible avec toute utilisation future du pipeline Ov3rLoRd qui
     sortirait du cadre recherche non-commerciale (ex. si le projet
     génère un jour du contenu monétisé, même indirectement via le filtre
     QC).

**Conséquence : le test zero-shot HandRefiner sur les cas HandSegNet prévus
(00138, 00224, 00137/00167, + cas bons 00274/00108/00044/00079) n'a pas pu
être lancé.** Ce n'est pas un verdict sur le domain gap (ni confirmé ni
infirmé pour ce modèle) — c'est un blocage d'accès en amont.

À titre indicatif, sans que ce soit un test réel : les auteurs de
HandRefiner eux-mêmes, dans leur FAQ README ("Can I use it for Anime
hands?"), anticipent déjà que "there is a great chance that the mesh
reconstruction stage may fail" sur du style cartoon/anime — cohérent avec
la piste MANO/FreiHAND (entraîné sur des mains photoréalistes), mais à
prendre comme un indice, pas une mesure.

## 4. Recommandation pour la suite (session future, pas maintenant)

Conformément à la consigne : documenter clairement et proposer **DiffDoctor**
comme piste de secours pour une prochaine session, plutôt que d'enchaîner
maintenant.

- `ali-vilab/DiffDoctor` (MIT confirmé) — architecture plus simple en
  apparence : un checkpoint de détecteur d'artefacts autonome
  (`ad_pytorch_model.bin`, via `git lfs`, dans `checkpoints/`), inférence
  seule (`ad_inference.py`) qui ne semble **pas** nécessiter les poids
  FLUX.1 (ceux-ci ne servent qu'à l'étape "Treat" = entraînement du modèle
  de diffusion, hors scope QC). Aucune dépendance de type MANO/SMPL repérée
  dans un premier survol du README — **à vérifier plus en détail avant
  téléchargement** (ne pas supposer que c'est propre juste parce que rien
  n'est apparu dans ce survol rapide) : lire `ad_inference.py` et le code
  du détecteur pour confirmer qu'aucun sous-composant à licence restrictive
  n'est chargé silencieusement, torch 2.3.1 (bien plus récent, meilleure
  chance de compatibilité Blackwell).
- Piste HADM : reste possible si contact direct avec l'auteur
  (`wangkaihong`) pour clarifier la licence — non entrepris cette session,
  décision volontairement laissée à l'utilisateur.

## 5. Ce qui n'a PAS été fait (hors scope suite au blocage)

- Téléchargement de poids (HADM, HandRefiner, MeshGraphormer, MANO) — rien.
- ÉTAPE 3 de la session prévue (scaffolding annotation + script de
  fine-tuning) — non commencée : prématurée sans baseline zero-shot établie,
  et conditionnée par un domain gap "confirmé significatif" qui n'a pas pu
  être mesuré.
- Aucune modification du pipeline de production.

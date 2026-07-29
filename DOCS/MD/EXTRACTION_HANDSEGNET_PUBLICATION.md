# Extraction HandSegNet → repo public + publication HuggingFace

Note pour Claude Code. Objectif : extraire HandSegNet du repo privé `OVERLORD`
vers un nouveau repo public `Ov3rLoRd-MLEngineer/handsegnet`, propre et
autonome, puis publier les poids sur HuggingFace. Même formule que FootSegNet
(voir `EXTRACTION_FOOTSEGNET_PUBLICATION.md` dans ce dossier) — checkpoint
seul publié (poids + inférence + conversion), pipeline d'entraînement/dataset
reste privé.

Contexte : le README HuggingFace (model card), la LICENSE (MIT, code) et la
LICENSE_WEIGHTS (Apache 2.0, poids) sont déjà rédigés et préparés dans
`handsegnet/huggingface/` (2026-07-29) — voir ce dossier en premier avant de
rédiger quoi que ce soit ici, il s'agit d'extraire et nettoyer, pas de
rédiger le contenu.

**IMPORTANT — ne rien publier/pousser sans validation explicite du contenu
final du model card par l'utilisateur.** Ce document prépare le terrain ; il
ne déclenche aucune mise en ligne effective.

---

## 0. État au 2026-07-29 — ce qui est déjà prêt dans `handsegnet/huggingface/`

- [x] `README.md` — model card HF complète, rédigée et cohérente avec les
      métriques réelles (val_IoU 0.8876 interne / 0.722 moyenne pipeline
      réel — **distinction explicite faite dans le texte**, cf. section
      "Results" du fichier)
- [x] `LICENSE` — MIT, pour le code du futur repo GitHub
- [x] `LICENSE_WEIGHTS.txt` — Apache 2.0, pour les poids publiés sur HF
- [x] `requirements.txt` — dépendances minimales (torch/torchvision à
      installer séparément, puis Pillow/numpy/safetensors/segment-anything)
- [x] `convert_to_safetensors.py` — testé, conversion sans perte confirmée
      (314 tenseurs, 93.7M paramètres, 375 MB, vérification bit-à-bit OK)
- [x] `handsegnet_vit_b_best.safetensors` — déjà généré dans ce dossier
      (2026-07-29, depuis `handsegnet/checkpoints/handsegnet_vit_b_best.pth`)
- [x] `standalone_infer.py` — testé en conditions réelles (image + box
      manuels, GPU 5060 Ti, masque de sortie plausible)

## 1. Points d'attention spécifiques à HandSegNet (différents de FootSegNet)

- **Le model card est explicite sur les DEUX métriques** (0.8876 box
  vérité-terrain vs 0.722 moyenne / 0.773 médiane box automatique) — ne pas
  simplifier en gardant uniquement le premier chiffre lors d'une éventuelle
  réécriture, ce serait trompeur (cf. section "Results — read this before
  trusting the headline number").
- **Pas de lien vers `LIMITATIONS_CONNUES.md`** dans le model card : ce
  fichier vit dans le repo privé `OVERLORD`, inaccessible aux utilisateurs
  du repo public — la consigne de session demandait d'y renvoyer, mais un
  lien vers un fichier privé serait cassé pour tout lecteur externe. Le
  contenu pertinent (mirroring, décrochage de doigts, échecs de boîte) a
  été **résumé directement dans la section Limitations du model card**
  (tableau "Pattern / What happens / When it shows up") plutôt que
  référencé — à signaler si l'utilisateur préfère un traitement différent.
- **Pas de paramètre `refine`** dans `standalone_infer.py` (contrairement à
  la version FootSegNet) : `handsegnet/infer.py` n'implémente pas la double
  passe SAM (logits réinjectés), donc les métriques publiées (0.8876/0.722)
  reflètent une inférence à passe unique — ajouter un `refine` non testé
  aurait rendu le model card incohérent avec ses propres chiffres.
- **Modèle frère** : le model card référence FootSegNet
  (`https://huggingface.co/Ov3rLoRd-MLEngineer/footsegnet`) — vérifier que
  cette URL est bien la bonne avant publication.

## 2. Créer le repo public vide

```bash
# Sur github.com : créer Ov3rLoRd-MLEngineer/handsegnet (public)
cd D:\
git clone https://github.com/Ov3rLoRd-MLEngineer/handsegnet.git handsegnet-public
cd handsegnet-public
```

## 3. Copier uniquement les fichiers pertinents

```bash
# Depuis D:\OVERLORD\handsegnet\, copier SEULEMENT :
#   - infer.py (renommer/adapter en inference minimal si besoin, ou
#     réutiliser standalone_infer.py déjà autonome — préférer ce dernier,
#     infer.py dépend de config.py du monorepo)
#   - handsegnet/huggingface/standalone_infer.py, convert_to_safetensors.py,
#     requirements.txt, LICENSE, LICENSE_WEIGHTS.txt, README.md
#   - un script de démo minimal (à créer si absent : demo_infer.py, ou
#     réutiliser standalone_infer.py directement comme point d'entrée)
# NE PAS copier :
#   - train.py, build_coco.py, annotate.py, batch_premask.py (pipeline
#     d'entraînement/dataset — reste privé)
#   - dataset brut (images, masques) sauf 2-3 exemples pour la démo
#   - tout fichier référençant context_bus, director, agents/ du pipeline
#   - EXCLUDED_STEMS.txt, _provenance.csv (métadonnées internes)
```

## 4. Nettoyage — vérifications automatiques

```bash
grep -rn "D:\\\\OVERLORD" .
grep -rn "D:\\\\Ov3rLoRd" .
grep -rniE "api[_-]?key|token|secret|password" .
grep -rn "from agents" .
grep -rn "context_bus" .
grep -rn "director" .
```

Tout résultat positif doit être corrigé avant de continuer.

## 5. Test d'autonomie — clone à blanc

```bash
cd D:\
git clone https://github.com/Ov3rLoRd-MLEngineer/handsegnet.git handsegnet-test-clean
cd handsegnet-test-clean
pip install -r requirements.txt
python standalone_infer.py --image examples/sample.png --checkpoint handsegnet_vit_b_best.safetensors --box "x,y,w,h" --output mask.png
```

Doit fonctionner SANS accès à `D:\OVERLORD\` ni à aucun module du pipeline
privé. Si ça échoue : une dépendance cachée a été oubliée à l'étape 4.

## 6. Publication HuggingFace

```bash
huggingface-cli login
huggingface-cli repo create handsegnet --type model
```

- [ ] Upload des poids (`.safetensors` — déjà généré, voir §0)
- [ ] Upload du README HF (déjà rédigé — vérifier une dernière fois les
      placeholders Ko-fi/Sponsors)
- [ ] Ajouter le lien vers le repo GitHub dans la model card
- [ ] Ajouter le lien vers la page HuggingFace dans le `README.md` GitHub

## 7. Vérification finale

- [ ] Les deux pages (GitHub + HuggingFace) se renvoient l'une à l'autre,
      et vers FootSegNet (modèle frère) et vice-versa
- [ ] Le repo GitHub public ne contient aucune référence à OVERLORD, au
      pipeline complet, ou à un chemin local
- [ ] Le clone à blanc (étape 5) fonctionne toujours après l'upload final
- [ ] Relire une dernière fois le README pour repérer tout détail interne
      resté par erreur

---

## Rappel pour plus tard (ne pas oublier)

Dès que GitHub Sponsors passe en "approuvé" : ajouter le lien dans le README
GitHub et la model card HF, **sur les 4 repos** (footsegnet ×2, handsegnet ×2).

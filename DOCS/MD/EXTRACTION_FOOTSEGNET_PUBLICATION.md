# Extraction FootSegNet → repo public + publication HuggingFace

Note pour Claude Code. Objectif : extraire FootSegNet du repo privé `OVERLORD`
vers un nouveau repo public `Ov3rLoRd-MLEngineer/footsegnet`, propre et
autonome, puis publier les poids sur HuggingFace.

Contexte : le README HuggingFace (model card) et la licence Apache 2.0 sont
déjà rédigés et validés (PR #11 mergée dans OVERLORD). Il s'agit ici
d'extraire et nettoyer, pas de rédiger le contenu.

---

## 0. Pré-requis à vérifier avant de lancer

- [ ] Confirmer l'emplacement exact du README HF déjà rédigé et de la LICENSE
      dans le repo OVERLORD (chemin probable : `footsegnet/HUGGINGFACE_README.md`
      ou équivalent — à localiser).
- [ ] Confirmer quels fichiers Python constituent le cœur de FootSegNet
      (probablement `footsegnet/model.py`, `train.py`, `infer.py`,
      `dataset.py`/`build_coco.py`, `annotate.py`) — **exclure**
      `footsegnet/controlnet/` (projet Control-LoRA séparé, pas mûr).
- [ ] Vérifier si le lien Ko-fi est déjà finalisé (URL réelle) — GitHub
      Sponsors reste en attente d'approbation, ne pas inclure ce lien pour
      l'instant.

---

## 1. Créer le repo public vide

```bash
# Sur github.com : créer Ov3rLoRd-MLEngineer/footsegnet (public, MIT ou Apache 2.0
# selon ce qui est déjà dans la LICENSE rédigée)
cd D:\
git clone https://github.com/Ov3rLoRd-MLEngineer/footsegnet.git footsegnet-public
cd footsegnet-public
```

## 2. Copier uniquement les fichiers pertinents

```bash
# Depuis D:\OVERLORD\footsegnet\, copier SEULEMENT :
#   - model.py, train.py, infer.py, dataset.py / build_coco.py, annotate.py
#   - un script de démo minimal (à créer si absent : demo_infer.py)
# NE PAS copier :
#   - footsegnet/controlnet/ (projet séparé)
#   - tout fichier référençant context_bus, director, agents/ du pipeline
#   - dataset brut (images, masques) sauf 2-3 exemples pour la démo
```

## 3. Nettoyage — vérifications automatiques

```bash
# Chercher les chemins absolus D:\OVERLORD dans tous les fichiers copiés
grep -rn "D:\\\\OVERLORD" .
grep -rn "D:\\\\Ov3rLoRd" .

# Chercher d'éventuelles clés/tokens oubliés
grep -rniE "api[_-]?key|token|secret|password" .

# Chercher des imports vers des modules du pipeline privé (agents/, context_bus, director)
grep -rn "from agents" .
grep -rn "context_bus" .
grep -rn "director" .
```

Tout résultat positif doit être corrigé (chemin relatif, variable d'env, ou
suppression de la dépendance) avant de continuer.

## 4. Ajouter les fichiers de packaging

- [ ] `requirements.txt` — dépendances minimales réelles de FootSegNet
      uniquement (torch, segment-anything, pillow, numpy... pas les libs
      Ollama/ComfyUI/audio du pipeline complet)
- [ ] `LICENSE` — **MIT pour le code** du repo GitHub (scripts d'entraînement/
      inférence). L'Apache 2.0 déjà validée dans le README HF s'applique aux
      **poids** publiés sur HuggingFace (clause brevet pertinente pour un
      modèle réutilisable en aval) — donc deux licences différentes, une par
      repo, à ne pas confondre lors du copier-coller du README.
- [ ] `README.md` — copier le README HuggingFace déjà rédigé, en adaptant
      les liens : lien vers la page HuggingFace du modèle, lien Ko-fi (si
      URL finale disponible), **pas de ligne GitHub Sponsors pour l'instant**
- [ ] `.gitignore` — exclure checkpoints lourds, caches, fichiers temporaires

## 5. Test d'autonomie — clone à blanc

```bash
cd D:\
git clone https://github.com/Ov3rLoRd-MLEngineer/footsegnet.git footsegnet-test-clean
cd footsegnet-test-clean
pip install -r requirements.txt
# Lancer le script de démo/inférence sur l'image d'exemple fournie
# Doit fonctionner SANS accès à D:\OVERLORD\ ni à aucun module du pipeline privé
python demo_infer.py --image examples/sample.jpg
```

Si ça échoue : une dépendance cachée vers OVERLORD a été oubliée à l'étape 3.

## 6. Publication HuggingFace

```bash
huggingface-cli login
# Créer le repo modèle : Ov3rLoRd-MLEngineer/footsegnet
huggingface-cli repo create footsegnet --type model
```

- [ ] Upload des poids (`.safetensors` de préférence à `.pt`/`.pth`)
- [ ] Upload du README HF (model card déjà rédigée — vérifier une dernière
      fois les placeholders Ko-fi/Sponsors)
- [ ] Ajouter le lien vers le repo GitHub dans la model card
- [ ] Ajouter le lien vers la page HuggingFace dans le `README.md` GitHub

## 7. Vérification finale

- [ ] Les deux pages (GitHub + HuggingFace) se renvoient l'une à l'autre
- [ ] Le repo GitHub public ne contient aucune référence à OVERLORD, au
      pipeline complet, ou à un chemin local
- [ ] Le clone à blanc (étape 5) fonctionne toujours après l'upload final
- [ ] Relire une dernière fois le README pour repérer tout détail interne
      resté par erreur (noms de fichiers internes, TODO privés, etc.)

---

## Rappel pour plus tard (ne pas oublier)

Dès que GitHub Sponsors passe en "approuvé" (pas de mail encore reçu au
25/07/2026) : ajouter le lien dans le README GitHub et la model card HF,
sur les deux repos.

# ADDENDUM V2 — État d'avancement et pistes restantes

Mise à jour de ADDENDUM_PISTES_FUTURES_JUILLET2026.md. Ce document reflète ce
qui a été fait depuis, ce qui est en cours, et ce qui reste à faire. À
transmettre à Claude Code pour cadrer les prochaines sessions.

---

## FAIT depuis la dernière note

### Identité / publication
- Renommage complet du studio **Onibaku Gumi → Ov3rLoRd** sur tout le repo
  (66 fichiers), y compris logos ASCII, bannières de lancement (`ov_console.py`
  / `ascii_banner()` dans `maestro.py`), localisation corrigée en **Rouen**
  (pas Le Havre, qui reste la ville natale dans les bios perso — distinction
  faite consciemment).
- Pseudo GitHub changé : **`Ov3rLoRd-MLEngineer`** (statut réaliste choisi :
  junior/associate ML Engineer, pas de titre gonflé).
- Compte **HuggingFace créé** sous le même pseudo, profil complété (AI & ML
  interests renseigné, nom complet corrigé).
- Compte **Ko-fi créé**. **GitHub Sponsors soumis, en attente d'approbation**
  (statut "Pending" au moment de la rédaction).
- Décision de structure de repos : `OVERLORD` (dépôt de travail complet)
  reste **privé/invitation uniquement**. Chaque projet mûr sera extrait vers
  son **propre repo public séparé** sous `Ov3rLoRd-MLEngineer` (pas un seul
  repo monolithique) — la découvrabilité groupée se fait via le profil GitHub,
  pas via la fusion des repos. FootSegNet est le premier candidat à extraire.
- PR #11 (matériel de publication HuggingFace FootSegNet) et PR #12 (pipeline
  Control-LoRA) **mergées et poussées sur `origin/main`**.
- README HuggingFace FootSegNet rédigé et jugé prêt (model card complète,
  résultats, limitations honnêtes, licence Apache 2.0, attribution Ov3rLoRd /
  Jérémy Gourlain). **Placeholders Ko-fi/GitHub Sponsors encore à remplacer
  par les vrais liens** avant publication effective.

### Restructuration complète du repo (terminée)
- 251 fichiers `.py` traités (footsegnet, handsegnet, facesegnet, bodysegnet,
  agents/, racine) : logo ASCII + lien GitHub ajoutés en commentaire pur
  (jamais imprimé — vérifié).
- 24 renommages de fichiers vXX vers leur nom final, toutes leurs références
  mises à jour (10 fichiers dépendants corrigés en cascade).
- 19 scripts jetables supprimés après validation explicite.
- **7 bugs UnicodeEncodeError latents corrigés** (flèches → et emojis dans des
  chaînes affichées à la console, cp1252). Pattern maintenant connu et
  activement recherché à chaque nouveau lot — un balayage dédié plus large
  (❌✅⏭📁 et autres emojis dans `agents/*.py` non encore tous audités) reste
  une piste identifiée mais non traitée, à faire en lot séparé si besoin.
- Incident documenté et réparé : un test `--help` a réellement exécuté
  `maestro_patch_v220.py` (pas d'argparse dans ce fichier), cassant
  temporairement `maestro.py` — restauré et documenté dans le fichier
  concerné plutôt que corrigé silencieusement.
- Merge final propre : 227 fichiers intégrés dans `main`, un seul conflit réel
  (bytecode `.pyc`, écarté sans risque), tout vérifié et poussé.

### Tri par confiance native SAM (active learning)
- Le score de confiance déjà produit par SAM (`scores[0]`) est maintenant
  exposé et enregistré dans `_provenance.csv` (colonne `sam_score`) pour les
  4 SegNets.
- `annotate.py --by-confidence` (footsegnet + handsegnet) ouvre les images
  par score croissant — priorise la correction manuelle sur les cas où le
  modèle est le moins sûr de lui, plutôt qu'un ordre alphabétique.
- Migration automatique des anciens `_provenance.csv` sans cette colonne.
- Testé et validé : le tri est cohérent avec l'IoU manuel (pire cas identifié
  en premier).

### HandSegNet
- **v0 entraîné sur 100 masques** (avant regénération des 75 supprimés pour
  doigts incohérents) : **val_IoU = 0.8633** — meilleur point de départ que
  le v0 FootSegNet (0.8098 sur 100 aussi), probablement dû à moins de
  diversité de pose/angle dans ce lot précis (confirmé par
  `dataset_diversity_stats.py` : FootSegNet a 40.7% de vues non-frontales
  contre 4.9% pour HandSegNet).
- **Décision actée : ne PAS publier HandSegNet v0** — reste privé jusqu'à
  maturité complète (300 masques, même rigueur que FootSegNet), cohérent
  avec la règle "publier quand exploitable, pas avant".
- `batch_premask.py` handsegnet corrigé (était resté multi-classe
  fingers/hand/wrist malgré le passage mono-classe de `annotate.py` — fixé,
  testé, 124/124 pré-masques générés, 0 échec).
- 124/300 masques annotés à date (avant regénération des 75 manquants).

### Wildcards v2 (footsegnet)
- Variété multipliée ×4 (21 → 85 templates), nouvelle catégorie `lighting.txt`.
- **Cohérence genre/vêtements** : outfits/shoes éclatés en pools
  neutral/feminine/masculine/cross, avec résolution consciente du genre du
  template dans `generate_dataset.py` (12% de chance explicite du pool
  cross) — évite les associations vêtement/style non-intentionnelles tout en
  gardant la liberté créative (homme en jupe/talons reste possible si
  volontaire).

### Pipeline Control-LoRA FootSegNet — construit et testé
- `footsegnet/controlnet/` : `prepare_dataset.py` (génération + pré-masque
  auto + assemblage), `quality_sort.py` (tri exploitable/à corriger/à
  exclure), `train_control_lora.py` (ControlNetModel diffusers + LoRA peft
  SDXL, mode `--test-run`), README dédié.
- Fallback grounding VLM + vérification par crop (filtre les bbox fantômes)
  intégrés dans le module de grounding partagé (`agents/vlm_grounding.py`,
  `agents/segnet_premask.py`), réutilisé par les 4 SegNets.
- **Deux runs de génération effectués** : 15 images (test initial) + 300
  images (lot principal) → **615 paires au total** dans
  `footsegnet/controlnet/dataset/` (300 masque manuel + 315 masque auto),
  0 image sans masque.
- Run de 300 : 0 échec, provenance 240 dwpose / 46 multi-instance /
  14 grounding pur, score SAM moyen 0.797 (médiane 0.816, **min 0.239 — cas à
  vérifier**, probablement à exclure ou corriger via
  `annotate.py --by-confidence`).
- **Prochaine étape immédiate** : `quality_sort.py --write-manifest` sur les
  615 paires, puis test de convergence sur sous-ensemble avant run
  d'entraînement complet.

### Outillage LLM local (préparatoire, pas encore exploité)
- **Unsloth Studio installé** (retenu plutôt qu'ASUS Multi-LM Tuner — licence
  Apache 2.0, indépendant du matériel, plus efficace en VRAM/kernels Triton,
  intégration native Claude Code). Installation vérifiée dans un venv
  totalement isolé (`C:\Users\Ov3rL0rD\.unsloth\studio\`, torch 2.10/cu130),
  sans impact sur le venv principal du projet (torch 2.11/cu128). Interface
  accessible sur `http://127.0.0.1:8888`, mot de passe initial à créer par
  l'utilisateur. **Aucun entraînement lancé** — outil prêt, piste "LoRA
  expert du projet" toujours en attente de priorisation.
- Clarification technique actée : le memory offloading NVMe (ZeRO-offload)
  s'applique à l'entraînement LLM/transformers texte, **pas** à la génération
  image/vidéo SDXL (architecture différente, contraintes VRAM différentes).

### Architecture de déploiement/portabilité (EN COURS, lancée juste avant cette note)
- Tâche envoyée à Claude Code, en 3 étapes séquentielles avec validation
  entre chacune :
  1. Audit des chemins absolus codés en dur (`D:\OVERLORD\...`,
     `D:\Ov3rLoRd AI\ComfyUI\...`) dans tout le repo — rapport seul, rien
     modifié.
  2. Config centralisée (réutiliser `.env.template` du pack V1.70 si
     pertinent) — un seul endroit pour définir les racines de chemins.
  3. Script de déploiement/setup : détection des disques disponibles,
     récupération/liaison des données existantes plutôt que repartir de
     zéro, écriture de la config résultante.
- Objectif : portabilité du pipeline en cas de changement de disque/machine,
  et système de sauvegarde/restauration facile — **pas encore de rapport
  reçu à la date de cette note**.

---

## PAS FAIT — reste dans le tiroir (inchangé depuis V1, sauf note)

- **DWPose fine-tuné sur anime + outil pose_editor** — toujours pertinent,
  liste des catégories d'échec enrichie cette semaine (ajout : manches
  amples masquant les mains, mains qui se chevauchent/s'entremêlent en
  poses jointes/croisées — observé sur HandSegNet).
- **LoRA "expert du projet"** — infrastructure prête (Unsloth Studio
  installé), dataset toujours à construire à partir des décisions
  documentées par l'utilisateur (pas des outputs Claude bruts).
- **Distillation légale domaine anime/ML** — Qwen 2.5/2.5-VL confirmé comme
  source autorisée (Apache 2.0), Llama à écarter (licence interdit
  explicitement), GLM à vérifier au cas par cas.
- **Image → 3D (TripoSR/InstantMesh + blender-mcp)** — toujours en attente,
  aucun développement lancé.
- **Multi-LLM cross-vérification pour dataset** — toujours écarté par défaut
  (risque de model collapse), sauf garde-fou humain ponctuel intégré.
- **Génération multi-GPU répartie** (5080 + 5060Ti en parallèle sur deux
  instances ComfyUI) — évoqué, jugé non rentable pour un run ponctuel de
  génération (~40 min), mais **potentiellement rentable pour un futur
  entraînement Control-LoRA overnight** (plusieurs heures) — à
  reconsidérer si le temps d'entraînement complet s'avère très long.
- **Agent de veille technique hebdomadaire** (nouveaux modèles
  Ollama/HuggingFace) — pas construit.
- **Agent personnel (Mistral local) pour démarches administratives** — pas
  construit.

---

## Points d'attention ouverts à traiter bientôt

1. **Liens Ko-fi/GitHub Sponsors** à insérer dans les README (footsegnet
   principal + huggingface/) dès que le lien Ko-fi est récupéré et que
   GitHub Sponsors est approuvé.
2. **Extraction du repo GitHub public FootSegNet** sous
   `Ov3rLoRd-MLEngineer` — pas encore fait, en attente après validation
   finale du README.
3. **Upload effectif sur HuggingFace** (checkpoint `.safetensors` + model
   card + script standalone) — compte créé, rien encore uploadé.
4. **Cas SAM score=0.239** dans le lot Control-LoRA de 300 — à identifier et
   vérifier/exclure avant l'entraînement.
5. **75 masques HandSegNet à regénérer** (doigts incohérents sur le premier
   lot de 300) — pas encore relancé.

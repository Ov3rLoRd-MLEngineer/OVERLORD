# Setup agent local de code — Aider + Qwen3-Coder (soulager Claude Code)

Objectif : mettre en place un agent de génération de code local (Ollama +
Qwen3-Coder 30B-A3B, orchestré par Aider) pour absorber les tâches de code
routinières, réservant Claude Code à la relecture/fix ciblé et aux problèmes
complexes (moins de tokens consommés sur l'abonnement).

Périmètre : usage général, pas restreint au pipeline Ov3rLoRd.

---

## 0. Contexte matériel (rappel)

- GPU 0 : RTX 5080 16 Go (ComfyUI/display)
- GPU 1 : RTX 5060 Ti 16 Go (remplace l'ancienne RTX 2070, pinning Ollama existant)
- Ollama tourne déjà en local (port 11434) avec mistral, qwen2.5:7b,
  deepseek-r1:7b pour le pipeline Ov3rLoRd (llm_router.py) — **le nouvel
  agent de code partage la même instance Ollama**, pas une nouvelle installation.

## 1. Vérifier la faisabilité VRAM avant tout engagement

```bash
ollama pull qwen3-coder:30b-a3b-q4_K_M
# Vérifier la taille réelle et si elle tient sur une carte 16 Go sans offload
ollama run qwen3-coder:30b-a3b-q4_K_M --verbose
```

- [x] **Testé le 2026-07-26.** Pas d'OOM matériel : `q4_K_M` tient sur la
      5060 Ti seule (Option B confirmée, pas besoin de quantification plus
      légère). Le vrai piège n'était pas la VRAM mais le **contexte par
      défaut du modèle (262144 tokens)** — charge le modèle en entier en
      mémoire pour le KV cache et fait planter l'allocation
      (`std::bad_alloc`) même avec assez de VRAM/RAM libres. Fix : toujours
      forcer `num_ctx` explicitement (32768 retenu, cf. étape 2). À
      `num_ctx=32768` : ~14,4 Go/16 Go sur la 5060 Ti (67% GPU / 33% offload
      CPU), confirmé isolé de la 5080 même avec une autre session utilisant
      activement celle-ci en parallèle.
      Deux bugs de lancement trouvés et corrigés dans `launch_ollama.bat` :
      (1) ne jamais relancer Ollama via `Start-Process -FilePath "ollama"`
      direct depuis PowerShell — la variable `CUDA_VISIBLE_DEVICES` ne se
      propage pas au process enfant dans ce cas, toujours passer par le
      `.bat` ; (2) ajout de `GGML_CUDA_NO_PINNED=1` en dur dans le script —
      contourne un échec d'allocation de buffer host "pinned" CUDA
      spécifique à Windows sur cette machine.
- [x] Pas de conflit observé avec les modèles pipeline existants (mistral,
      qwen2.5:7b, deepseek-r1:7b) — Ollama charge/décharge à la demande,
      testé sans contention sur la 5060 Ti.

## 2. Installer et configurer Aider

```bash
pip install aider-chat --break-system-packages
```

**Corrigé le 2026-07-26 :** `pip install aider-chat --break-system-packages`
tel quel casse le pipeline — Aider épingle `huggingface-hub==1.4.1` en dur,
alors que `transformers` (utilisé par le pipeline, ex. QwenVL grounding)
exige `<1.0`. Conflit dur, pas juste un warning (`import transformers`
lève une `ImportError` une fois `huggingface-hub` monté à 1.4.1). Installer
Aider dans un **venv isolé** à la place (même pattern que Unsloth
Studio/MediaPipe) :

```bash
py -3.12 -m venv C:\Users\Ov3rL0rD\.aider\venv
C:\Users\Ov3rL0rD\.aider\venv\Scripts\python.exe -m pip install aider-chat
```

Config Aider (globale, `~/.aider.conf.yml`) :

```yaml
model: ollama_chat/qwen3-coder:30b-a3b-q4_K_M
```

`ollama_chat/` est recommandé par la doc Aider (pas `ollama/`). Plafond de
contexte (`~/.aider.model.settings.yml`) — nécessaire sinon Aider peut
demander jusqu'au défaut du modèle (262144 tokens, cf. étape 1) :

```yaml
- name: ollama_chat/qwen3-coder:30b-a3b-q4_K_M
  extra_params:
    num_ctx: 32768
```

```bash
setx OLLAMA_API_BASE http://127.0.0.1:11434
```

- [x] Testé sur un petit repo jetable : diff propre, commit cohérent, code
      correct du premier coup.
- [x] Testé sur Ov3rLoRd sur la branche `aider-experiments` (conservée,
      pas mergée sur main). **Piège trouvé** : sur le vrai repo (pas sur le
      mini-repo jetable), les 2 premiers essais ont échoué silencieusement
      — fichier créé vide (0 octet), aucun commit, alors que le terminal
      affichait un message de succès. Cause : artefact de rendu terminal
      Git Bash/`rich` (sortie qui semble "boucler"), pas un vrai défaut du
      modèle — confirmé en inspectant le fichier réel après coup. **Leçon
      opérationnelle : ne jamais faire confiance au texte affiché dans le
      terminal après un `--message` run ; vérifier systématiquement
      `git log` + le contenu du fichier.** Lancer Aider depuis `cmd.exe`
      plutôt que Git Bash éviterait probablement l'artefact.
- [ ] Plan de repli (Devstral-2 22B) : pas nécessaire pour l'instant, q4_K_M
      fonctionne correctement une fois le contexte plafonné et le résultat
      vérifié sur disque plutôt que dans le terminal.

## 3. Workflow génération locale → relecture Claude Code

Le principe : Aider/Qwen3-Coder génère le premier jet, Claude Code ne lit que
le diff (pas de génération complète) pour la relecture — beaucoup moins de
tokens consommés qu'une génération from scratch.

Séquence type :
1. Décrire la tâche à Aider (`aider` en CLI, dans le repo concerné)
2. Aider génère le code + diff + commit local
3. Copier le diff (`git diff HEAD~1`) et le soumettre à Claude Code avec un
   prompt du type : *"Relis ce diff, vérifie la logique, signale les bugs ou
   incohérences — ne réécris pas le fichier entier, propose des corrections
   ciblées si besoin."*
4. Si Claude Code signale des problèmes : soit renvoyer le retour à Aider
   pour une nouvelle passe, soit laisser Claude Code faire une correction
   ciblée (edit minimal, pas une régénération complète).

## 4. Critère de routage (quand utiliser quoi)

- **Aider/Qwen3-Coder en premier jet** : scripts utilitaires, refactoring
  mécanique, code répétitif, tâches bien cadrées avec spec claire.
- **Claude Code direct (sans passer par Aider)** : diagnostic complexe
  (ex. Control-LoRA), architecture nouvelle, décisions qui demandent du
  raisonnement multi-étapes ou une compréhension fine du contexte du projet.
- **Claude Code en relecture uniquement** : cas intermédiaire — Aider génère,
  Claude Code valide/corrige sans réécrire.

## 5. Test de validation avant adoption large

- [x] Tâche choisie : `agents/gpu_vram_check.py` (script utilitaire autonome,
      non-critique).
- [x] Faite via Aider+Qwen3-Coder, relue par Claude Code : diff correct,
      1 seul défaut mineur trouvé (`import sys` inutilisé), corrigé par un
      edit ciblé d'une ligne — pas de réécriture.
- [x] Comparaison avec `agents/ollama_status_check.py` (tâche comparable,
      écrite directement par Claude Code) :
      - **Qualité** : les deux fonctionnels du premier coup une fois le
        pipeline stabilisé. Le code Claude Code est un peu plus complet
        (deux tables : modèles installés + modèle chargé) sans que ça soit
        demandé plus précisément — différence de scope, pas de qualité pure.
      - **Fiabilité** : Aider a nécessité 3 tentatives sur le vrai repo à
        cause d'un artefact terminal (voir étape 2), 0 tentative
        supplémentaire côté Claude Code.
      - **Tokens Claude Code consommés** : la relecture du diff Aider
        (~54 lignes) coûte nettement moins que la génération complète d'un
        fichier équivalent from scratch — l'écart se creusera avec des
        fichiers plus gros/complexes, ici modeste vu la petite taille des
        deux scripts.
- [x] Critère de routage (étape 4) ajusté : le principe initial tient
      (utilitaires/tâches cadrées → Aider), avec une réserve opérationnelle
      ajoutée — voir la leçon terminal à l'étape 2. Ne pas router vers Aider
      sans un moyen de vérifier le résultat sur disque (pas seulement lire
      la sortie terminal).

---

## 6. Amélioration future (v2) — auto-bascule selon charge GPU

Une fois le workflow de base validé (étape 5), envisager une couche de
décision automatique plutôt qu'une config fixe :

- Un script vérifie l'utilisation de la 5080 (`nvidia-smi`) juste avant
  l'appel Aider.
- Si la 5080 est libre (pas de rendu ComfyUI en cours) → utiliser le tag
  Ollama configuré en split double-GPU (qualité maximale, `q4_K_M`).
- Si la 5080 est occupée → basculer sur le tag 5060 Ti seule (quantification
  plus légère, `q4_K_S`/`q3_K_M`).
- Même logique de routage que `llm_router.py` existant, avec la charge GPU
  comme critère supplémentaire en plus du type de tâche.

Ne pas construire ça avant d'avoir validé la qualité de base — complexité à
ajouter seulement si le gain est confirmé utile en usage réel.

## 7. Piste future (hors périmètre actuel) — fine-tuning double-GPU

Ollama sert des modèles déjà entraînés ; il ne fait pas de fine-tuning. Si un
jour l'idée est d'entraîner/fine-tuner un modèle de code sur les données du
projet en exploitant réellement les deux GPU (parallélisme data/modèle),
Unsloth (single-GPU) ne convient pas — il faudra Axolotl ou Torchtune. Pas
d'action requise maintenant, aucun fine-tuning de Qwen3-Coder n'est prévu à
ce stade (usage tel quel).

## Rappel

Objectif réaliste : réduction de la dépendance à l'abonnement Claude Code sur
les tâches routinières, pas suppression totale — les tâches complexes (comme
le diagnostic Control-LoRA en cours) restent mieux traitées directement par
Claude Code.

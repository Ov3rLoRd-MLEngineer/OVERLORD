# Procédure de secours — Aider + qwen3-coder (si Claude Code indisponible)

Objectif : relais court, actionnable sous pression, quand le quota Claude
Code est épuisé. **Lire l'avertissement en premier — ce mécanisme n'est
PAS fiable en mode automatisé à ce jour (2026-07-29)**, voir
`SETUP_AGENT_LOCAL_AIDER_QWEN3CODER.md` §1ter pour le détail complet.

## ⚠️ Avertissement — à lire avant d'en dépendre

Testé le 2026-07-29 sur une tâche réelle simple : **3 tentatives sur 3 ont
échoué à produire un fichier réellement écrit et commité**, malgré un
modèle qui génère souvent du code correct (crash d'encodage sous Git Bash,
fichier vide silencieux sous PowerShell, dérail du modèle sur un
second tour). Ne traite pas ce mécanisme comme un pilote automatique. Après
CHAQUE lancement, quelle que soit la sortie affichée dans le terminal :

```bash
# Ne jamais faire confiance au texte du terminal seul
cat <fichier_attendu>          # doit contenir du code reel, pas 0 octet
git log --oneline -1 -- <fichier_attendu>
git status --short -- <fichier_attendu>
```

Si le fichier est vide ou non commité malgré un message de succès affiché :
c'est l'échec connu, pas une fausse alerte — relancer ou traiter la tâche
soi-même/attendre Claude Code.

## 1. Pré-requis (déjà en place, ne pas réinstaller)

- Ollama tourne en local (`http://127.0.0.1:11434`) — **vérifier avant
  tout lancement** :
  ```bash
  curl -s http://127.0.0.1:11434/api/tags
  ```
  Si pas de réponse : lancer `launch_ollama.bat` (racine du dépôt) — jamais
  `Start-Process -FilePath "ollama"` direct depuis PowerShell (le pinning
  GPU ne se propage pas, cf. `SETUP_AGENT_LOCAL_AIDER_QWEN3CODER.md` §1).
- Aider est installé dans un venv isolé :
  `C:\Users\Ov3rL0rD\.aider\venv\Scripts\aider.exe`
- Config déjà en place dans ce dépôt (`.aider.conf.yml`,
  `.aider.model.settings.yml`) — injecte automatiquement `CLAUDE.md` et
  `DOCS/INDEX.md` en lecture seule à chaque lancement depuis `D:\OVERLORD`.
  Rien à reconfigurer.

## 2. Lancer une tâche

**Toujours depuis PowerShell natif, jamais Git Bash** (crash d'encodage
confirmé sous Git Bash le 2026-07-29) :

```powershell
cd D:\OVERLORD
& "C:\Users\Ov3rL0rD\.aider\venv\Scripts\aider.exe" --yes-always --no-pretty --no-stream `
  --message "Description precise et cadree de la tache." `
  chemin/du/fichier.py
```

- `--yes-always` : auto-accepte les éditions (pas de confirmation manuelle
  — nécessaire en mode non-interactif, mais voir l'avertissement ci-dessus).
- `--no-pretty --no-stream` : évite le rendu Rich (source du crash Git
  Bash ; n'a pas résolu le problème de fiabilité sous PowerShell, gardé
  quand même car ça évite au moins un des 2 modes d'échec connus).
- Rediriger la sortie vers un fichier log (`*> log.txt` en PowerShell) pour
  pouvoir la relire sans dépendre du terminal.

## 3. Vérifier (obligatoire, pas optionnel)

Refaire les 3 commandes de la section "Avertissement" ci-dessus. Si le
résultat est vide/non commité : ne pas insister sur la même commande,
traiter la tâche par un autre moyen (Claude Code dès que disponible, ou
manuellement).

## 4. Quel type de tâche confier ici (si le mécanisme fonctionne ce jour-là)

- **Oui** : scripts utilitaires autonomes et bien cadrés, refactoring
  mécanique, code répétitif — cf. `SETUP_AGENT_LOCAL_AIDER_QWEN3CODER.md`
  §4/§5 pour les cas déjà validés.
- **Non** : diagnostic multi-étapes, décisions sur des cas ambigus
  nécessitant un jugement contextuel (vérifications de licence, arbitrages
  sur des défauts génératifs, architecture nouvelle) — hors du périmètre
  pour lequel ce mécanisme a même été envisagé, pas seulement "risqué".

## 5. Après coup

Relire le diff produit avant de le considérer acquis — même en l'absence
de Claude Code, une relecture humaine rapide (`git diff HEAD~1`) reste plus
sûre qu'une confiance aveugle au message de succès du terminal.

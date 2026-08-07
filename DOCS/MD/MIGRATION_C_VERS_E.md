# Migration C: → E: — ménage disque (2026-08-05/06, session autonome)

## Contexte

C: n'avait que 52 Go libres (180 Go utilisés). E: dispose de 1541 Go libres.
Consigne (`consignes.txt` Bureau) : auditer C: au-delà des 4 dossiers déjà
identifiés, migrer ces 4 éléments vers `E:\Users\Ov3rL0rD\` avec des
redirections propres, tester Ollama/Python/Blender après coup.

## Audit — 10+ plus gros consommateurs sur C:

| Emplacement | Taille | Nature |
|---|---|---|
| `AppData\Local\Programs` | 10,9 Go | Applications installées (Ollama app, etc. — binaires, pas à déplacer) |
| `.cache\huggingface` | 12,3 Go | Cache HuggingFace (modèles sentence-transformers, etc.) — **migré** |
| `.unsloth` | 5,3 Go | Venv isolé Unsloth Studio — **migré** |
| `AppData\Local\pip\cache` | 5,89 Go | Cache wheels pip — **migré** |
| `AppData\Local\uv` | 5,36 Go | Cache `uv` (installeur pip-compatible) — **non migré, hors périmètre** de la consigne (4 dossiers nommés), candidat pour une prochaine passe si besoin (`UV_CACHE_DIR`) |
| `AppData\Local\Microsoft` | 5,11 Go | Cache apps Microsoft (Edge/Teams...) — hors périmètre |
| `Downloads` | 5,66 Go | Fichiers utilisateur — hors périmètre (contenu à trier par Jérémy) |
| `AppData\Local\Programs\Ollama` | 2,74 Go | Binaire application Ollama — pas à déplacer (comme Python, cf. consigne) |
| `AppData\Local\CrashDumps` | 2,0 Go | Dumps de crash Windows — candidat de nettoyage simple (suppression, pas migration), hors périmètre de cette tâche |
| `AppData\Local\tts` | 1,75 Go | Cache Coqui TTS | hors périmètre |
| `ProgramData\Microsoft` | 3,9 Go | Système Windows — hors périmètre |
| `Program Files\Microsoft Visual Studio` | 7,29 Go | Application installée — hors périmètre |
| `Program Files\NVIDIA GPU Computing Toolkit` | 4,21 Go | CUDA toolkit — hors périmètre |

**Modèles Ollama (`D:\OVERLORD\models`, 106 Go)** : déjà hors C: avant cette
session — `OLLAMA_MODELS` (User) pointait déjà vers `D:\OVERLORD\models`.
`C:\Users\Ov3rL0rD\.ollama` et `AppData\Local\Ollama` sont à 0 octet,
confirmant qu'aucun modèle ne traîne sur C:. **Aucune action nécessaire pour
ce point** — déjà résolu avant cette session (probablement session
antérieure, cf. mémoire `ollama-gpu-pinning`).

## Migrations effectuées

Méthode pour chacune : `robocopy /MIR` (copie miroir) vers
`E:\Users\Ov3rL0rD\<nom>` → vérification stricte (nombre de fichiers + somme
des tailles identiques entre source et destination) → **renommage** (pas
suppression, voir note sécurité ci-dessous) de l'original en
`<nom>_old_to_delete` → création de la jonction/variable d'env pointant vers
E:.

### 1. `.cache` → jonction NTFS

- Copié : 148 fichiers, 12,501 Go, vérification OK (comptage + taille
  identiques).
- `C:\Users\Ov3rL0rD\.cache` renommé en `.cache_old_to_delete`, jonction NTFS
  créée à la place vers `E:\Users\Ov3rL0rD\.cache`.
- Choix jonction (pas `XDG_CACHE_HOME`) : cette variable n'est pas fiable sur
  Windows pour tous les outils (dépend de si l'outil utilise `platformdirs`/
  `appdirs` avec support Windows explicite) ; la jonction est transparente au
  niveau système de fichiers, fonctionne pour tout outil sans dépendre de
  son support d'une variable d'environnement spécifique.
- **Testé** : `sentence_transformers` importé avec succès, cache HF lu via
  la jonction (`hub/`, `token`, etc. visibles).

### 2. `.unsloth` → jonction NTFS

- Copié : 67 897 fichiers (venv complet), 5,298 Go, vérification OK.
- Renommé en `.unsloth_old_to_delete`, jonction créée vers
  `E:\Users\Ov3rL0rD\.unsloth`.
- Jonction plutôt que variable d'env : un venv Python contient des chemins
  absolus dans certains scripts (`pyvenv.cfg`, `Scripts\activate`) — la
  jonction préserve le chemin logique `C:\Users\Ov3rL0rD\.unsloth\...`
  inchangé, seul le stockage physique bouge.
- **Testé** : `C:\Users\Ov3rL0rD\.unsloth\studio\unsloth_studio\Scripts\
  python.exe --version` → `Python 3.12.3`, fonctionne via la jonction.

### 3. Ollama — déjà résolu, aucune action

`OLLAMA_MODELS` (User) déjà positionné sur `D:\OVERLORD\models` avant cette
session. **Problème distinct découvert en testant** (voir section
"Anomalie découverte" ci-dessous) : le process Ollama actuellement en cours
d'exécution ne reflète pas ce chemin (`ollama list` retourne une liste
vide alors que 69 blobs/106 Go existent sur D:).

### 4. Cache pip + `PYTHONUSERBASE`

- `AppData\Local\pip` (5,893 Go, 2787 fichiers) copié vers
  `E:\Users\Ov3rL0rD\pip`. **1 fichier a échoué** (`ERREUR 5, Accès refusé` —
  `sgmllib3k-1.0.0-py3-none-any.whl`, 6,1 Ko) : `Get-Acl`/`icacls` confirment
  un problème de permissions sur ce fichier spécifique (ACL restrictive
  préexistante, cause non investiguée plus avant — hors périmètre pour un
  fichier de cache disposable). Sans conséquence : c'est un cache pip
  (régénérable automatiquement par un futur `pip install` si ce wheel est
  redemandé), pas une perte de données réelle.
- `PIP_CACHE_DIR` (User) = `E:\Users\Ov3rL0rD\pip\cache`.
- `PYTHONUSERBASE` (User) = `E:\Users\Ov3rL0rD\Python` — **rien à migrer
  ici** : aucun `AppData\Roaming\Python` n'existait (pas d'usage actuel de
  `pip install --user` sur ce poste, le projet utilise des venvs). Variable
  positionnée en prévention pour un usage futur.
- `AppData\Local\pip` renommé en `pip_old_to_delete`.
- **Testé** : `reg query HKCU\Environment` confirme la persistance ; un
  process `cmd /c` avec la variable positionnée confirme que `pip cache dir`
  et `pip cache list` lisent correctement le nouvel emplacement E:.
- **Installation Python elle-même non touchée** (conforme à la consigne —
  trop risqué), uniquement le cache et la variable de packages utilisateur.

## Tests post-migration

| Composant | Résultat |
|---|---|
| Python (import HF cache via jonction) | ✅ OK |
| Venv Unsloth (via jonction) | ✅ OK |
| Blender (lancement headless) | ✅ OK (`5.1.2`, inchangé — sans dépendance aux 4 dossiers migrés) |
| pip (cache dir/list, nouvel emplacement) | ✅ OK |
| **Ollama** | ⚠️ **Anomalie découverte** (voir ci-dessous) — non causée par cette migration |

## Anomalie découverte (préexistante, sans lien avec cette migration)

`ollama list` retourne une liste **vide** alors que
`D:\OVERLORD\models\manifests\` contient de nombreux modèles enregistrés
(llama3, mistral, qwen2.5-coder, `ov3rlord-coder-stage2v2`, etc.) et
`D:\OVERLORD\models\blobs\` pèse 106 Go. `curl http://127.0.0.1:11434/api/tags`
confirme côté API : `{"models":[]}`.

**Cause probable** : le process `ollama.exe`/`ollama app.exe` actuellement
actif a été lancé (au démarrage de Windows, tray app) **avant** que la
variable `OLLAMA_MODELS` ne soit positionnée à la bonne valeur, ou sans
hériter correctement de cette variable — cohérent avec la mémoire de session
antérieure documentant que le tray app "relance son propre serve non pinné
à chaque reboot". Un process Windows ne relit pas le registre après son
démarrage ; il faut un redémarrage du process pour qu'il reprenne la
variable actuelle.

**Non corrigé dans cette session** : `taskkill` sur les process Ollama
(PID 16000 `ollama app.exe`, PID 17220 `ollama.exe`) a été **bloqué par le
classificateur de sécurité automatique** (action jugée trop risquée pour
être exécutée sans confirmation explicite en mode autonome). Aucune
génération n'était en cours (`ollama ps` vide) au moment du test, donc un
redémarrage serait sans risque de perte de travail, mais nécessite l'action
manuelle de Jérémy (fermer l'icône Ollama dans la barre des tâches Windows
et la relancer, ou `taskkill /F /PID 16000 /PID 17220` puis relancer
`ollama app.exe`) — **ou une confirmation explicite pour que Claude Code le
fasse**.

## Nettoyage final — effectué (confirmation explicite de Jérémy)

Les 3 dossiers de sauvegarde ont été supprimés après validation explicite :
`.cache_old_to_delete` (12,50 Go) supprimé intégralement en un seul passage.
`.unsloth_old_to_delete` et `AppData\Local\pip_old_to_delete` ont nécessité
un second passage — un fichier bloqué dans chacun (`Accès refusé`,
verrou/ACL transitoire, cause non investiguée plus avant) :
- `...\yaml\_yaml.cp312-win_amd64.pyd` (248 Ko)
- `...\sgmllib3k-1.0.0-py3-none-any.whl` (6 Ko, le même fichier ACL-protégé
  identifié dès la copie initiale)

Ces 2 fichiers résiduels (~254 Ko au total, négligeable) sont les seuls
restes des 3 dossiers — tout le reste a été supprimé avec succès.

## Espace disque — avant/après

| | Avant migration | Après (avant nettoyage final) | Après nettoyage final |
|---|---|---|---|
| C: libre | 52,0 Go | 51,5 Go | **68,2 Go** (+16,2 Go net) |
| E: libre | 1541,1 Go | 1515,7 Go | 1515,7 Go (stable) |

## Action restante pour Jérémy

**Redémarrer Ollama** (fermer/relancer l'app depuis la barre des tâches, ou
tuer PID 16000+17220 et relancer) pour qu'il reprenne
`OLLAMA_MODELS=D:\OVERLORD\models` et retrouve ses modèles — ce redémarrage
de process reste bloqué pour une exécution autonome par le classificateur
de sécurité, contrairement à la suppression de fichiers qui a pu être
validée explicitement.

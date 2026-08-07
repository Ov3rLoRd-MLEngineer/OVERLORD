# Undervolt CPU/GPU — état session nuit 2026-08-06/07

Priorité 2 de `session nuit.txt`. Suit `resume_ram_undervolt.md` (Bureau,
résumé établi le 06/08/2026) : i7-8700K + RTX 5080 + RTX 5060 Ti.

## Ce qui a été fait cette session

- **ThrottleStop 9.7** installé via `winget install TechPowerUp.ThrottleStop`
  (source officielle winget, hash vérifié) ->
  `C:\Users\Ov3rL0rD\AppData\Local\Microsoft\WinGet\Packages\TechPowerUp.ThrottleStop_Microsoft.Winget.Source_8wekyb3d8bbwe\ThrottleStop.exe`
- **MSI Afterburner 4.6.6** installé via `winget install Guru3D.Afterburner`
  (source officielle winget, hash vérifié) ->
  `C:\Program Files (x86)\MSI Afterburner\MSIAfterburner.exe`

## Ce qui n'a PAS été fait, et pourquoi

**L'undervolt lui-même (offsets FIVR CPU, courbe V/F GPU) n'a pas été
appliqué cette nuit.** Ce n'est pas un oubli : ThrottleStop (offset FIVR) et
MSI Afterburner (courbe V/F, Ctrl+F) sont tous les deux des outils **pilotés
uniquement par une interface graphique** — aucun des deux n'expose de
ligne de commande pour régler un offset de tension ou une courbe V/F
(`MSIAfterburner.exe` accepte des switches de profil `-Profile1..5` mais pas
de reglage direct de tension ; `ThrottleStop.exe` charge un `.INI` au
demarrage mais les offsets FIVR ne s'ecrivent de façon fiable que via la
fenêtre FIVR de l'appli elle-même).

Deux options existaient pour appliquer les valeurs quand même : automatiser
les clics GUI en aveugle, ou écrire directement les valeurs dans les fichiers
de config sans passer par l'UI. Les deux ont été écartées : `resume_ram_
undervolt.md` demande explicitement de **valider chaque palier par un stress
test avant de passer au suivant** (Cinebench/Prime95 puis remonter de +10mV
en cas de crash) — une procédure conçue pour une supervision en direct.
Faite en aveugle sur une machine sans personne pour constater un hang/BSOD
et agir (redémarrage physique si besoin), c'est exactement le type d'incident
qu'on vient de vivre cette nuit (crash Kernel-Power Id=41 à 21:54:49,
probablement lié à la RAM déjà documentée) — je n'ai pas voulu risquer d'en
ajouter un second, sans supervision, sur un axe (tension CPU/GPU) où un échec
peut aller jusqu'au hang matériel. Le planificateur de tâches Windows pour
l'auto-démarrage de ThrottleStop a aussi été tenté puis bloqué par le
classifieur auto-mode (action jugée sensible en autonomie).

## Prêt à appliquer (valeurs de `resume_ram_undervolt.md`)

| Étape | Outil | Valeur de départ | Ordre |
|---|---|---|---|
| 1. CPU core | ThrottleStop (FIVR) | -100 mV | 1er (le plus simple, réversible instantanément) |
| 2. CPU cache/ring | ThrottleStop (FIVR) | -50 mV | avec l'étape 1 |
| 3. RTX 5080 | MSI Afterburner (courbe V/F, Ctrl+F) | -25 mV (aplatir les points au-dessus du voltage de boost stabilisé) | 2e (plus grosse consommatrice) |
| 4. RTX 5060 Ti | MSI Afterburner (courbe V/F) | -25 mV | 3e |

Procédure de validation (à faire avec supervision, cf. doc source) : stress
test dédié après chaque étape (Cinebench R23 boucle 30 min + Prime95 Small
FFTs pour le CPU ; une session ComfyUI complète pour le GPU, "meilleur stress
test réel que FurMark" dixit le doc source), paliers de -10 mV en cas de
stabilité confirmée, +10 mV immédiat en cas de crash/BSOD.

`workspace/scripts/system_monitor.py` tourne déjà en continu cette nuit
(Priorité 1) et loggue tout crash/BSOD/TDR dans `DEMO/output/system_crashes.csv`
+ `CRASH_ALERT.flag` — utile si l'undervolt est appliqué une prochaine session,
pour corréler un éventuel incident à l'horaire du changement.

## Prochaine étape

Session interactive (ou instruction explicite d'automatiser malgré le risque
identifié ci-dessus) pour appliquer les 4 étapes une par une avec
observation en direct des stress tests.

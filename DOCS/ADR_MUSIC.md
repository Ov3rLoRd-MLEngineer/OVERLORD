# ADR-MUSIC — Choix du moteur Text-to-Music

**Statut :** Proposé
**Date :** 04/07/2026
**Portée :** post-production audio (`agents/postprod.py`), étape `PUBLICATION` de `maestro.py`.

---

## Contexte

Le pipeline ne génère actuellement aucune musique/OST — les sorties post-prod se limitent à l'image/vidéo et à la voix (gTTS, cf. `ADR_TTS.md`). Le besoin : générer une bande-son (thème d'ambiance ou OST de scène) correspondant au ton anime des épisodes produits, intégrable dans l'étape POST-PROD sans supervision humaine constante, et sans mettre en danger la monétisation potentielle du contenu publié (étape `PUBLICATION`).

Trois candidats évalués : **MusicGen (Meta)**, **AudioCraft (framework Meta englobant MusicGen/AudioGen/EnCodec)**, **Suno (API)**.

## Alternatives comparées

| Critère | MusicGen (Meta) | AudioCraft (framework) | Suno (API) |
|---|---|---|---|
| Qualité OST anime | Correcte pour boucles d'ambiance/thème court instrumental ; faible sur structures longues (couplet/refrain) et voix chantée | Identique à MusicGen (AudioCraft est le framework qui héberge le modèle — pas un modèle distinct) | Très bonne — pistes complètes avec voix, structure couplet/refrain, styles variés, qualité proche production commerciale |
| VRAM (cible RTX 5080) | small (~300M) ~4 Go ; medium (~1.5B) ~8-10 Go ; large (~3.3B) proche de saturer 16 Go en fp16 | Idem MusicGen selon la taille de modèle choisie | Aucune — génération cloud, zéro charge locale |
| Licence commerciale | **CC-BY-NC 4.0 sur les poids pré-entraînés** — usage recherche/non-commercial uniquement, pas de droit de revente ni d'usage commercial direct | Code du framework en MIT, mais les checkpoints pré-entraînés (MusicGen/AudioGen/EnCodec) restent sous la même licence CC-BY-NC | Droits d'usage commercial accordés sur les sorties pour les offres payantes (Pro/Premier) selon les CGU Suno — mais **pas d'API officielle publique** : les accès programmatiques existants sont des wrappers non officiels qui contournent l'UI web, ce qui viole les CGU si automatisé dans un pipeline |
| Contrôle style/durée | Prompt texte + tag de genre, durée limitée (~30s par défaut, extensible par génération continue avec perte de cohérence) | Idem | Bon contrôle style/genre via tags, durée jusqu'à plusieurs minutes, mais pas de véritable API pour piloter ces paramètres sans passer par l'UI |
| Intégration pipeline post-prod (offline, autonome) | Bonne — inference locale via `transformers` (`MusicgenForConditionalGeneration`) ou AudioCraft, scriptable | Bonne, mêmes bibliothèques | Mauvaise sans API officielle : nécessite automatisation navigateur ou wrapper tiers, fragile et hors ToS |

## Décision recommandée

**Aucun des trois candidats n'est directement adoptable tel quel pour un usage en production monétisée.** Décision pragmatique en deux temps :

1. **Court terme — usage non-commercial/interne uniquement :** utiliser **MusicGen** (petit ou moyen modèle, via `transformers`) pour générer des pistes d'ambiance de prototypage/preview, taguées explicitement comme non-commerciales dans les métadonnées de sortie (même logique que le flag `_fallback: true` d'ADR-009). L'agent de publication doit **bloquer** toute vidéo publiée/monétisée contenant une piste MusicGen tant que ce flag est actif.
2. **Suno API rejetée pour l'automatisation :** en l'absence d'API officielle documentée et stable, l'intégrer dans un pipeline autonome reviendrait à automatiser un accès non sanctionné par Suno (violation CGU, risque de bannissement de compte). Suno reste utilisable **manuellement** (génération via l'UI web, export, puis import manuel dans `workspace/` par l'utilisateur) pour des morceaux destinés à être réellement publiés/monétisés, en dehors du pipeline automatisé.
3. **AudioCraft** n'apporte rien de plus que MusicGen pour ce projet — c'est le framework qui héberge le modèle, pas une alternative de licence ou de qualité différente. Pas de décision séparée nécessaire : le choix se limite au modèle (MusicGen) et à sa taille.

## Conséquences

- Aucune musique générée localement ne peut être utilisée dans une vidéo monétisée sans franchir l'une des deux voies : (a) négocier une licence commerciale avec Meta pour MusicGen (non proposée publiquement à ce jour pour un usage individuel), ou (b) utiliser une piste produite manuellement via Suno sous licence payante Suno, injectée hors pipeline automatisé.
- Le flag « non-commercial » doit être propagé jusqu'à l'agent de publication pour éviter qu'une piste MusicGen se retrouve, par erreur, dans une vidéo monétisée.
- Contention VRAM : MusicGen medium/large tournant en parallèle de ComfyUI sur la RTX 5080 (16 Go visés) reste à valider — prévoir, comme pour la TTS, une exécution séquentielle plutôt que concurrente tant que non testé.
- Le pipeline perd en autonomie sur ce module précis : la meilleure option qualité (Suno) ne peut pas être branchée en `agents/` sans risque de violation de CGU, ce qui casse le principe « le pipeline ne s'arrête jamais / tourne seul » pour cette étape spécifique — accepté comme limite connue plutôt que contournée par un usage risqué de l'API non officielle.

## Prochaines étapes

1. Intégrer `transformers.MusicgenForConditionalGeneration` (modèle `small` d'abord) dans un nouvel agent `agents/music_synthesis.py`, avec le flag de licence non-commerciale dans les métadonnées de sortie.
2. Ajouter la vérification de ce flag dans l'agent de publication (bloquer/avertir avant toute mise en ligne monétisée).
3. Benchmarker VRAM/latence de MusicGen medium sur la config actuelle, puis sur RTX 5080 dès disponible, en conditions de contention avec ComfyUI actif.
4. Documenter la procédure manuelle Suno (génération UI → export → dépôt dans `workspace/`) comme voie officielle pour toute musique destinée à un contenu monétisé.
5. Revisiter cette ADR si Meta publie une voie de licence commerciale pour MusicGen, si Suno ouvre une API officielle avec CGU compatibles avec l'automatisation, ou si un modèle concurrent sous licence commerciale claire apparaît (à surveiller : les modèles de musique générative sous licence de type « gratuit sous seuil de revenu », sur le modèle de la CPML de Coqui pour la TTS).
6. Une fois validé en production, documenter dans `ADR_OVERLORD.md` avec numéro d'ADR séquentiel (ADR-012).

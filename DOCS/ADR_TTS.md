# ADR-TTS — Choix du moteur Text-to-Speech

**Statut :** Proposé
**Date :** 04/07/2026
**Portée :** `agents/v140_voice_synthesis.py` (déjà scaffoldé avec `GTTSSynthesizer` et `ElevenLabsSynthesizer`), post-production audio (`agents/postprod.py`), `agents/module_manager.py`.

---

## Contexte

Le pipeline utilise aujourd'hui **gTTS** (`lang="fr"`, cf. ADR-006) comme moteur de synthèse vocale par défaut — simple, gratuit, mais robotique, sans clonage de voix, et dépendant de l'API Google (nécessite une connexion réseau). `agents/v140_voice_synthesis.py` contient déjà un stub `ElevenLabsSynthesizer` (API payante cloud) et mentionne Coqui TTS en commentaire sans implémentation.

Le besoin réel : des voix de personnages anime/JP crédibles (timbre, prosodie, émotion), idéalement avec clonage à partir d'un court échantillon de référence par personnage, générées **localement** (cohérent avec la philosophie du projet — tout tourne sur la machine locale, cf. `config_manager.py`), sans bloquer le pipeline (principe ADR-009 : le pipeline ne doit jamais s'arrêter), et sans risque de licence si les vidéos produites sont publiées/monétisées (étape `PUBLICATION` de `maestro.py`).

Trois candidats évalués : **Coqui TTS (XTTS-v2)**, **Bark (Suno AI)**, **F5-TTS**.

## Alternatives comparées

| Critère | Coqui TTS (XTTS-v2) | Bark | F5-TTS |
|---|---|---|---|
| Qualité voix anime/JP | Bonne, prosodie contrôlable, clonage 6-10s | Variable — bons emotes/rires mais hallucine parfois (mots ratés, répétitions) | Très bonne prosodie/naturel, mais support JP surtout via fine-tunes communautaires |
| Clonage de voix | Oui, zero-shot à partir d'un sample de référence | Non — presets de voix fixes ou embeddings, pas de clonage direct | Oui, zero-shot, très efficace |
| VRAM | ~4-6 Go (fp16) | ~5 Go (modèle large) | ~4-5 Go |
| Latence / temps réel | RTF ~0.2-0.3x sur GPU récent → proche temps réel | Lent — génération token-par-token, souvent plusieurs fois le temps réel | Rapide (flow-matching non autoregressif), RTF parmi les meilleurs du marché |
| Stabilité pipeline non supervisé | Bonne — sortie déterministe par seed | Risque : hallucinations = audio incohérent silencieusement produit, mauvais pour un pipeline sans supervision humaine | Bonne |
| Licence commerciale | Coqui Public Model License (CPML) sur les poids XTTS-v2 : usage commercial gratuit sous un seuil de revenu annuel, accord payant au-delà | MIT — permissif, commercial sans restriction | **Poids pré-entraînés entraînés sur le dataset Emilia (CC-BY-NC)** → usage commercial des poids officiels non autorisé sans ré-entraînement sur données propres |
| Intégration Python 3.12 | Fork communautaire maintenu (`coqui-tts` sur PyPI, Coqui AI ayant cessé son activité fin 2024/2025) compatible 3.9-3.12 | Compatible 3.12 via PyTorch récent | À vérifier au cas par cas selon version torch/torchaudio épinglée |
| Maintenance amont | Communautaire (risque : rythme de mise à jour ralenti depuis la fermeture de Coqui AI) | Actif (Suno AI) | Actif (recherche académique) |

## Décision recommandée

**Adopter Coqui TTS (XTTS-v2)** comme moteur principal, en conservant **gTTS comme fallback** existant (cohérent avec le principe déjà en place ADR-009 / séquence de fallback utilisée par `fallback_llm`, cf. mémoire projet).

Justification :
- F5-TTS est écarté malgré ses qualités techniques : les poids pré-entraînés distribués sont issus du dataset Emilia (CC-BY-NC), ce qui interdit leur usage commercial direct — incompatible avec une chaîne de publication qui pourrait être monétisée. Une option resterait de ré-entraîner un checkpoint sur des données possédées en propre, mais c'est hors de portée immédiate.
- Bark est écarté pour la production automatisée : sa tendance à halluciner (mots incorrects, répétitions, silences) est incompatible avec un pipeline qui ne doit jamais s'arrêter ni produire silencieusement un résultat incohérent (ADR-009). Il reste utilisable ponctuellement pour des effets non-verbaux (rires, soupirs) en génération manuelle supervisée.
- XTTS-v2 offre le meilleur compromis clonage de voix / latence / VRAM, et sa licence CPML est gratuite pour un usage commercial sous le seuil de revenu — ce qui couvre la situation actuelle du projet (usage personnel/solo).
- ElevenLabs (déjà stubé dans le code) reste une option de secours ponctuelle en cas d'échec local, mais n'est pas retenue comme moteur principal : dépendance cloud payante contraire à la philosophie « tout tourne localement » du projet.

## Conséquences

- Ajouter `coqui-tts` à `requirements.txt` (vérifier compatibilité de version torch avec le GPU en place — RTX 2070 actuellement, RTX 5080 en preset cible dans `config_manager.py`).
- Contention VRAM à surveiller : XTTS-v2 (~4-6 Go) tournant en parallèle de ComfyUI/SDXL sur la même carte peut saturer une RTX 2070 (8 Go). Prévoir une exécution séquentielle (TTS après la génération d'images, pas en parallèle) tant que le GPU n'est pas upgradé.
- Le clonage de voix nécessite un échantillon de référence (6-10s) par personnage récurrent — à intégrer à la mémoire narrative (`workspace/narrative/memory.json`, cf. ADR-010) pour garder une voix cohérente entre épisodes.
- Si le canal de publication venait à dépasser le seuil de revenu CPML, revoir l'accord de licence Coqui avant de continuer à utiliser XTTS-v2 commercialement.
- Le fork communautaire étant moins actif que ne l'était Coqui AI, surveiller l'obsolescence du dépôt (risque de dérive silencieuse si plus de mises à jour de sécurité).

## Prochaines étapes

1. `pip install coqui-tts` sous py-3.12, vérifier la résolution des dépendances torch/torchaudio sans conflit avec les paquets déjà utilisés par ComfyUI.
2. Télécharger le checkpoint XTTS-v2, tester sur une ligne de dialogue JP/anime type et mesurer RTF + VRAM réels sur la machine actuelle.
3. Tester la contention VRAM en lançant XTTS-v2 pendant une génération ComfyUI active (pire cas) pour valider ou infirmer le besoin d'exécution séquentielle.
4. Implémenter `CoquiTTSSynthesizer` dans `agents/v140_voice_synthesis.py`, sur le même modèle que `GTTSSynthesizer`/`ElevenLabsSynthesizer`.
5. Câbler la chaîne de fallback dans `agents/module_manager.py` : Coqui → gTTS si échec/OOM/timeout (même logique que la séquence de fallback LLM déjà en place).
6. Documenter dans `ADR_OVERLORD.md` une fois validé en production, avec numéro d'ADR séquentiel (ADR-011).

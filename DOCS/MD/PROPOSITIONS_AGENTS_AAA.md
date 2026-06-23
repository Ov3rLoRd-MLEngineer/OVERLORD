# Propositions Agents aAa V1.50

## Agents déjà présents
- aAa_Auditeur.py — audit syntaxique des fichiers Python
- organize_project.py — organisation du dossier projet

## PROPOSITIONS NOUVEAUX AGENTS

### aAa_DependencyChecker.py
**Rôle :** Vérifie que toutes les dépendances Python sont installées
et compatibles avec Python 3.14.
**Ce qu'il fait :**
- Lit tous les `import` de chaque fichier Python du projet
- Compare avec `pip list`
- Signale les manquants + les versions incompatibles
- Génère un `requirements.txt` à jour
**Valeur :** Évite les ImportError surprises au lancement.

### aAa_CircularImportDetector.py
**Rôle :** Détecte les imports circulaires (A importe B qui importe A).
**Ce qu'il fait :**
- Construit le graphe de dépendances entre tous les agents
- Détecte les cycles
- Propose des refactorisations (ex: déplacer une fonction dans overlord_utils)
**Valeur :** Les imports circulaires causent des ImportError silencieux
difficiles à diagnostiquer.

### aAa_LogAnalyzer.py
**Rôle :** Analyse les logs `workspace/logs/*.log` pour détecter
les patterns d'erreurs récurrents.
**Ce qu'il fait :**
- Parse tous les fichiers .log du workspace
- Classe les erreurs par fréquence et sévérité
- Identifie les modules qui crashent le plus
- Génère un rapport de santé du pipeline
- Peut envoyer un résumé via Telegram
**Valeur :** Tu vois en 30 secondes quel bloc du pipeline pose problème
sans lire 500 lignes de logs.

### aAa_ComfyUIHealthCheck.py
**Rôle :** Diagnostic complet de ComfyUI avant un run.
**Ce qu'il fait :**
- Vérifie que ComfyUI répond sur http://127.0.0.1:8188
- Liste les nodes manquants vs le workflow Combined_V35_API.json
- Vérifie les LoRA et checkpoints référencés dans config.json
- Mesure la VRAM disponible vs la config de génération
- Teste une génération minimale (1 step, 64x64) pour validation
**Valeur :** Évite de lancer un run de 200 images pour découvrir
qu'un node manque au step 1.

### aAa_ContextBusMonitor.py
**Rôle :** Moniteur temps réel du Context Bus.
**Ce qu'il fait :**
- Lit workspace/context_bus/bus_state.json en continu
- Affiche les métriques clés dans une mini-fenêtre tkinter
- Graphes temps réel : shots générés, score qualité, agent actif
- Alerte si une métrique dépasse un seuil (ex: qualité < 50)
**Valeur :** C'est lui qui fera "travailler les graphes" que tu vois
vides actuellement. À intégrer dans le Hub.

### aAa_WorkflowValidator.py
**Rôle :** Valide le fichier Combined_V35_API.json avant compilation EXE.
**Ce qu'il fait :**
- Parse le JSON du workflow ComfyUI
- Vérifie que tous les node_id référencés dans agent_supervisor_v2.py
  existent dans le workflow
- Signale les node_id obsolètes (ADV_LORA_ID = "62" existe-t-il ?)
- Compare la résolution config vs les nodes KSampler
**Valeur :** Évite les "node not found" silencieux en production.

### aAa_PatchVerifier.py
**Rôle :** Vérifie qu'un bundle de patch est correct AVANT application.
**Ce qu'il fait :**
- Parse un bundle .txt et liste les fichiers qui seront modifiés
- Vérifie la syntaxe Python de chaque [CONTENU:]
- Calcule le ratio taille (pour prédire les blocages du patcher)
- Suggère CREATE vs UPDATE selon la taille du fichier existant
**Valeur :** Évite les échecs de patch découverts après coup.

---

## PRIORITÉ D'IMPLÉMENTATION

1. **aAa_ContextBusMonitor** — résout directement le problème des
   graphes vides (électroencéphalogramme plat)
2. **aAa_LogAnalyzer** — utile immédiatement pour debugger
3. **aAa_ComfyUIHealthCheck** — critique avant chaque run production
4. **aAa_PatchVerifier** — évite les bundles bloqués
5. **aAa_DependencyChecker** — utile pour la V1.50 + nouveaux agents
6. **aAa_CircularImportDetector** — utile si nouveaux agents ajoutés
7. **aAa_WorkflowValidator** — utile si le workflow change

## INTÉGRATION DANS LE HUB

Chaque agent aAa expose une fonction `run_from_hub(root, logger)`.
Le Hub les appelle via un onglet dédié avec :
- Bouton "Lancer"
- Zone de log en temps réel
- Résumé des résultats

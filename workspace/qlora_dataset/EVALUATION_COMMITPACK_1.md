# ÉVALUATION STRUCTURÉE — VERDICT_COMMITPACK

Évaluation réalisée le 2026-08-04 par Claude Opus 4.6 à la demande de Jérémy Gourlain (Onibaku Gumi 鬼爆組).

Axes de notation :
- **Style (/5)** : registre Ov3rLoRd (tutoiement, ton direct, références projet, code inline quand pertinent, pas de verbiage corporate), respect du format attendu par le prompt.
- **Factuel (/5)** : exactitude technique, pertinence de la réponse par rapport à la demande, absence d'hallucination, présence de contenu actionnable.

---

## Prompt 1 — `quality_sort.py` : détection masques < 2%

| Modèle | Style | Factuel | Commentaire |
|---|:-:|:-:|---|
| **ov3rlord-coder-stage2v2** | 4 | 3 | Bon ton projet (tutoiement, référence ADR-12, changelog intégré). Le code proposé est fonctionnel dans l'esprit mais contient des approximations : `pixels.sum()` sur un masque L ne donne pas le nombre de pixels non-nuls mais la somme des intensités — il faudrait `np.count_nonzero(pixels > 127)` ou équivalent. Le seuil 2% est correctement implémenté dans la logique. Le format avant/après avec diff inline est adapté au contexte. Perd un point en style à cause du `"Maux de tête"` dans le log qui est un artefact bizarre. |
| **qwen2.5-coder:14b** | 2 | 3 | Vouvoiement, ton didactique avec sections "Explications" et "Remarques" qui ne correspondent pas au registre Ov3rLoRd. Le code est techniquement correct (utilise `cv2.countNonZero`, propre) mais complètement décontextualisé — il ne s'intègre pas dans `quality_sort.py`, propose un script standalone avec `__main__` et des fonctions qui n'existent pas dans le projet. Correct sur le fond algorithmique, hors-sujet sur l'intégration. |
| **stage2_commitpack** | 3 | 1 | Le format diff `--- a/ +++ b/` est stylistiquement cohérent avec le corpus CommitPack. Cependant : le fichier cible est `src/agents/quality_score.py` (pas `quality_sort.py`), le diff ne fait qu'ajouter un `print("DEBUG")` et deux `TODO` sans implémenter la détection demandée. Hallucination du chemin fichier, aucune logique de seuil 2% présente. |

---

## Prompt 2 — Script de validation JSONL

| Modèle | Style | Factuel | Commentaire |
|---|:-:|:-:|---|
| **ov3rlord-coder-stage2v2** | 4 | 3 | Ton projet respecté, script complet avec argparse, gestion d'erreurs par codes, rapport de validation. Bon registre (commentaires en français, noms de variables cohérents). Problèmes factuels : utilise `eval()` pour parser du JSON (faille de sécurité majeure + non-standard — `json.loads()` est la bonne approche), et le `unicode_escape` est un pattern fragile inutile pour du JSONL standard. L'architecture est surconçue pour la demande (système de codes d'erreur à 4 chiffres) mais fonctionnelle. La variable `count_total` est utilisée dans le print final hors scope. |
| **qwen2.5-coder:14b** | 2 | 4 | Vouvoiement, ton tuto. Mais le code est propre et correct : `json.loads()`, vérification des 3 clés, check `output.strip()` non vide, gestion `JSONDecodeError`. Simple, fonctionnel, pas de faille. Perd en style car `input()` pour le chemin fichier au lieu de `argparse` (le prompt spécifie `py -3.12`, ce qui implique un script CLI), et ton trop pédagogique. |
| **stage2_commitpack** | 3 | 2 | Format diff CommitPack cohérent. Le script généré utilise `json.loads()` (bien), mais hallucine les noms de clés : vérifie `inputs`/`outputs` au lieu de `input`/`output` comme demandé dans le prompt. Hallucine aussi un header de copyright NVIDIA fictif. Le fichier de sortie est nommé `.jsonl` alors que c'est un `.py`. La logique "Empty outputs allowed only when no input" n'est pas demandée et ajoute de la complexité non requise. Code tronqué en fin. |

---

## Prompt 3 — UnicodeEncodeError emojis Windows dans `handsegnet/annotate.py`

| Modèle | Style | Factuel | Commentaire |
|---|:-:|:-:|---|
| **ov3rlord-coder-stage2v2** | 4 | 3 | Bon diagnostic du problème (encodage console Windows). Ton direct, identification correcte de la cause racine. Cependant la réponse s'arrête à l'annonce de la correction sans livrer le code corrigé — c'est une réponse tronquée ou un engagement sans exécution. Le diagnostic est juste mais incomplet en livrable. |
| **qwen2.5-coder:14b** | 2 | 4 | Ton didactique, vouvoiement, mais techniquement solide. La solution `codecs.getwriter('utf8')(sys.stdout.buffer)` est le fix classique et correct pour ce problème sur Windows. Propose aussi `logging` comme alternative (pertinent). Les suggestions "modifier les paramètres régionaux Windows" sont du bruit inutile. Trop verbeux mais le cœur technique est bon. |
| **stage2_commitpack** | 2 | 0 | Le diff hallucine le fichier (`annotation.py` au lieu de `annotate.py`, `handsegmet` au lieu de `handsegnet`). Le contenu du diff — une fonction `get_annotated_image_path` — n'a aucun rapport avec le problème d'encodage Unicode. Zéro pertinence factuelle. Le format diff reste stylistiquement reconnaissable mais c'est le seul point positif. |

---

## Prompt 4 — Conclusion définitive run x30 = x10/x20 dans FootSegNet

| Modèle | Style | Factuel | Commentaire |
|---|:-:|:-:|---|
| **ov3rlord-coder-stage2v2** | 4 | 2 | Bon ton projet, format diff markdown pour le README. Cependant hallucine des détails techniques précis : mentionne un modèle "Control-LTX-10B" qui n'existe pas dans le projet (le projet utilise control-lora-openposeXL2-rank256 / Wan 2.2), invente des temps de run (8.4s, ~307s, ~369s), et la conclusion "le modèle ne gagne jamais en vitesse avec la taille du calcul" est une affirmation non fondée sur les données réelles du prompt. Style OK, contenu largement fabriqué. |
| **qwen2.5-coder:14b** | 1 | 2 | Ton corporate consultant avec liste à puces "1. Validation de la cohérence, 2. Analyse des paramètres…" — exactement le genre de réponse qu'un manager recevrait d'un cabinet de conseil sans valeur ajoutée. Aucun code, aucune documentation concrète proposée. Le point 6 "Validation par des experts" est absurde dans le contexte d'un solo ML engineer. Factuellement pas faux mais totalement inutile — ne répond pas à la demande de "documenter une conclusion définitive". |
| **stage2_commitpack** | 3 | 1 | Format diff cohérent CommitPack. Mais le diff porte sur un fichier `footsegnet/tests/test_controlnet.py` dont le contenu (suppression d'un décorateur pytest parametrize) n'a qu'un lien superficiel avec le prompt. Le diff semble avoir extrait un pattern "x10/x20/x30 parametrize" du corpus mais ne documente rien. |

---

## Prompt 5 — GPU1 à 99% puis repos, est-ce normal ?

| Modèle | Style | Factuel | Commentaire |
|---|:-:|:-:|---|
| **ov3rlord-coder-stage2v2** | 4 | 2 | Bon ton (tutoiement, diagnostic structuré, proposition de vérifier les logs). Cependant hallucine lourdement : invente un GPU2 "1080 Ti" et un GPU1 "RTX 4080" alors que le setup réel est RTX 5080 + RTX 5060 Ti. Invente `train.py` avec `Epoch [4/15]`, un fichier de log daté 2026-09-15 (date future), et un paramètre `memory_limit=3GB`. Le diagnostic "répartition multi-GPU PyTorch automatique" est plausible en théorie mais non fondé sur les données. La réponse correcte à "99% pendant la génération, repos après fermeture = est-ce normal ?" est simplement "oui, c'est le comportement attendu". |
| **qwen2.5-coder:14b** | 2 | 4 | Vouvoiement, ton générique. Mais la réponse est factuellement correcte et concise : oui c'est normal, le GPU monte en charge pendant la génération et revient au repos après. Les 3 points de vérification sont raisonnables. Simple, correct, pas de hallucination. |
| **stage2_commitpack** | 2 | 0 | Diff sur `Python/PyGame.py` — un fichier PyGame qui n'a absolument aucun rapport avec une question sur l'utilisation GPU. Hallucination complète du contexte. Le diff lui-même (changer `fill((0, 0, 255))` en `fill(0)`) est syntaxiquement valide en PyGame mais totalement hors-sujet. |

---

## Prompt 6 — SegNets comme portefeuille de compétences (question conceptuelle)

| Modèle | Style | Factuel | Commentaire |
|---|:-:|:-:|---|
| **ov3rlord-coder-stage2v2** | 5 | 3 | Excellent registre projet : tutoiement, reformulation critique de la question, distinction portfolio/agent composé avec exemples concrets tirés du projet (Ov3rLoRd API, ComfyUI batch, Plan ADR/CoPilot). C'est exactement le style attendu d'un pair technique qui challenge constructivement. Le contenu a du sens conceptuellement mais hallucine quelques détails (Sora Video comme composant Ov3rLoRd, la mention de DeepSeek/Mistral comme "monstres" en fin de réponse est un raccourci approximatif). Meilleure réponse des 3 sur le style. |
| **qwen2.5-coder:14b** | 1 | 1 | Interprète "segnets" comme des certifications professionnelles (!) — contresens total. La réponse est un discours RH générique sur le portefeuille de compétences, la collaboration, le leadership. Aucune compréhension du contexte technique (les SegNets sont les réseaux de segmentation du pipeline Ov3rLoRd). Hors-sujet complet, ton corporate inapproprié. |
| **stage2_commitpack** | 2 | 0 | Hallucine un fichier Django `segnet/models.py` avec un modèle `Segnet` et `Competence` en ORM. Le lien avec le prompt est purement lexical ("segnet" + "compétence" → modèle Django). Les TODO ajoutés montrent une capacité à simuler un développeur qui réfléchit, mais le contenu est entièrement fabriqué et ne répond pas à une question conceptuelle. |

---

## Prompt 7 — État des lieux rapide du pipeline

| Modèle | Style | Factuel | Commentaire |
|---|:-:|:-:|---|
| **ov3rlord-coder-stage2v2** | 5 | 1 | Style parfait : tree structure, version V3/V4, propositions d'action, "Dis-moi quelle direction tu choisis". C'est exactement le format et le ton qu'on attend d'un assistant de projet intégré. Malheureusement le contenu est quasi entièrement halluciné : `pipeline_v3_config.json`, `ollama_run.py`, `step0_download.py` à `step6_verify.py`, `sampe_generator_v2.py`, `pipeline_v4_config.json` — aucun de ces fichiers n'existe dans le projet réel. L'architecture 4-pass réelle (Run 1–4: body/pose, clothing, FX/background, composite+audio) n'apparaît nulle part. C'est une confabulation structurellement convaincante. |
| **qwen2.5-coder:14b** | 1 | 3 | Refuse de répondre en invoquant son statut d'assistant sans accès. C'est techniquement honnête (il n'a pas le contexte) mais c'est un refus inutile — le modèle fine-tuné devrait au minimum tenter de répondre avec ce qu'il sait. La suggestion "consultez Jenkins/GitLab CI" est déconnectée du contexte solo. Le seul point positif est l'absence de hallucination. |
| **stage2_commitpack** | 2 | 0 | Diff de 3 lignes sur `pipeline.py` qui supprime un header de compatibilité Python 2 (`from __future__ import print_function`). Aucun rapport avec un état des lieux. Hallucination du fichier et du contenu. |

---

## Prompt 8 — Stratégie 4B proxy vs 30B multi-GPU

| Modèle | Style | Factuel | Commentaire |
|---|:-:|:-:|---|
| **ov3rlord-coder-stage2v2** | 4 | 2 | Bon ton (tutoiement, structure décisionnelle, commandes concrètes). La recommandation "continuer sur le checkpoint existant plutôt que repartir de zéro" est un conseil pertinent en général. Cependant hallucine des détails précis : commande `train_controlnet.py` avec des chemins inventés, un checkpoint nommé `controlnet-control-lora-checkpoint-00300-step--checkpoint=1800`, un crash GPU spécifique non mentionné dans le prompt. Le raisonnement de fond est bon (risque/coût du 30B vs itération sur le 4B) mais les détails factuels sont fabriqués. |
| **qwen2.5-coder:14b** | 1 | 3 | Réponse type MBA avec structure "Continuer 4B / Investir 30B / Conclusion". Vouvoiement, ton consultant. Factuellement pas faux dans les principes généraux (scaling, coût, personnalisation) mais aucune connaissance du contexte projet — ne mentionne ni le hardware réel (5080/5060 Ti), ni les contraintes VRAM, ni le modèle spécifique (Qwen3-4B). Le point "N'oubliez pas votre équipe" est déplacé pour un solo engineer. |
| **stage2_commitpack** | 3 | 1 | Format diff cohérent. Hallucine `strategies/benchmarking.py` avec un modèle `gpt-neo-30b` (inexistant dans le projet). Le TODO "find the best strategy between this one and the proxy model" montre que le modèle a capté l'intention du prompt et l'a transformée en commentaire de code — ce qui est un comportement intéressant stylistiquement (c'est exactement ce qu'un dev ferait en placeholder) mais ne constitue pas une réponse. |

---

## SYNTHÈSE GLOBALE

### Moyennes par modèle

| Modèle | Style moyen | Factuel moyen | Profil |
|---|:-:|:-:|---|
| **ov3rlord-coder-stage2v2** | **4.25** | **2.38** | Excellent transfert de style (tutoiement, références projet, ton pair-à-pair, format adapté). Confabulation convaincante systématique : invente des fichiers, chemins, configurations, et détails techniques plausibles mais faux. Le modèle a parfaitement appris *comment* parler mais hallucine *de quoi* il parle. **Le RAG est non optionnel.** |
| **qwen2.5-coder:14b** | **1.50** | **3.00** | Ton générique assistant/consultant, vouvoiement systématique, structure tuto inadaptée au registre Ov3rLoRd. Factuellement plus fiable car plus conservateur (dit "je ne sais pas" ou reste dans les généralités plutôt que de fabriquer). Contresens majeur sur Prompt 6 (SegNets = certifications). |
| **stage2_commitpack** | **2.50** | **0.63** | Format diff CommitPack parfaitement appris — chaque réponse est un diff minimal cohérent syntaxiquement. Mais le contenu est quasi systématiquement halluciné : fichiers inventés, chemins erronés, aucune pertinence avec le prompt dans 7 cas sur 8. Le modèle a appris le *format* du corpus (diffs) sans apprendre le *contenu* attendu. Pattern d'hallucination structurelle le plus sévère des 3. |

### Observations clés

**1. Validation du diagnostic initial du document :** L'observation notée en en-tête ("l'adaptateur Stage 2 produit systématiquement un diff court mais hallucine le contexte fichier") est confirmée sur les 8 prompts sans exception. C'est un cas d'école de mode collapse sur le format.

**2. Le fine-tune ov3rlord-coder-stage2v2 a réussi le transfert de style mais pas la fidélité factuelle :** Le modèle 4B a intégré le registre du projet (ton, vocabulaire, conventions de nommage, structure de réponse) de façon remarquable. Le problème est entièrement du côté factuel — il confabule des détails techniques spécifiques avec une confiance qui rend la détection difficile sans vérification. C'est exactement le profil qui justifie le RAG sémantique déjà déployé.

**3. qwen2.5-coder:14b est le baseline conservateur :** Plus fiable factuellement car il ne prétend pas connaître le projet, mais totalement inutile en termes d'intégration projet. Son seul avantage est de ne pas mentir — ce qui en fait un bon choix pour des tâches génériques mais pas pour un assistant contextualisé.

**4. Recommandation opérationnelle :** Le pipeline `ov3rlord-coder-stage2v2 + RAG (multilingual-e5-small, hybrid BM25+semantic, 307 chunks)` est la bonne architecture. Le modèle fournit le style, le RAG fournit les faits. Le stage2_commitpack (adaptateur pur CommitPack) est inutilisable en l'état pour toute tâche autre que la génération de diffs — il pourrait servir comme composant spécialisé dans un pipeline de code review automatisé, mais pas comme assistant conversationnel.

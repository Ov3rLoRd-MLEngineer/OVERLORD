# DOCS/INDEX.md — Point d'entrée documentation Ov3rLoRd

Index volontairement court (destiné à être injecté en contexte, ex. agent de
code local Aider+Qwen3-Coder — voir `DOCS/MD/SETUP_AGENT_LOCAL_AIDER_QWEN3CODER.md`
§1bis). Ne remplace pas `CLAUDE.md` (conventions/règles, à lire en premier) —
complète avec les pointeurs vers la documentation de référence la plus à jour.

## À lire en premier
- `CLAUDE.md` (racine) — conventions du dépôt : langue, règles GPU, ast.parse()
  obligatoire, py -3.12, worktrees, gestion de contexte 90%/92%.
- `ADR_OVERLORD.md` (racine) — décisions d'architecture formelles (sampler,
  VAE, seeds, config, storage) : lire avant de changer un défaut établi.
- `LIMITATIONS_CONNUES.md` (racine) — limites génératives connues et
  acceptées (mirroring, décrochage de doigts...) + limites de pipeline
  actionnables séparées — consulter avant de rouvrir une investigation sur
  une image "ratée".

## Contexte de session le plus récent
- `CONTEXTE_OVERLORD_V229.md` (racine) — dernier "cerveau de démarrage"
  technique/pipeline. **Numéro le plus haut = le plus à jour** ; les
  `CONTEXTE_OVERLORD_V1xx/V2xx` antérieurs sont un historique, pas des
  alternatives.
- `CONTEXTE_OVERLORD_V229_ANNEXE.md` (racine) — annexe business/hardware/
  stratégie au V229, à lire en complément.
- `RAPPORT_HANDSEGNET_TRAINING_READINESS.md` (racine) — état HandSegNet
  (dataset, entraînement, checkpoint) le plus récent.
- `DOCS/MD/QC_ANATOMIQUE_AUDIT_LICENCES_20260729.md` — audit de licences en
  cours pour un futur filtre QC anatomique (HADM/HandRefiner/DiffDoctor,
  tous bloqués à ce jour — voir le fichier pour le détail).

## Publication de modèles (formule établie)
- `DOCS/MD/EXTRACTION_FOOTSEGNET_PUBLICATION.md` — playbook de référence
  (GitHub MIT + HuggingFace Apache 2.0, checkpoint seul, pipeline
  d'entraînement privé).
- `DOCS/MD/EXTRACTION_HANDSEGNET_PUBLICATION.md` — même playbook adapté,
  matériel déjà préparé dans `handsegnet/huggingface/`.

## Outillage agent local
- `DOCS/MD/SETUP_AGENT_LOCAL_AIDER_QWEN3CODER.md` — Aider + Qwen3-Coder en
  relais de secours (venv isolé, num_ctx=32768, critères de routage).

## Historique (ne pas traiter comme référence courante)
- `DOCS/MD/PROJECT_MAP.md`, `DOCS/MD/GUIDE_OVERLORD.md`, `DOCS/MD/RAPPORT_V14x.md`,
  `ADDENDUM_PISTES_FUTURES_V2/V3_JUILLET2026.md` — captures ponctuelles
  antérieures, non maintenues ; utiles pour l'historique, pas pour l'état
  courant du dépôt.

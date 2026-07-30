# Index des publications publiques

Modèles issus du pipeline Ov3rLoRd publiés publiquement (code MIT sur
GitHub, poids Apache 2.0 sur HuggingFace). Voir `DOCS/MD/EXTRACTION_*_PUBLICATION.md`
pour la méthodologie d'extraction de chaque modèle.

| Modèle | GitHub (code, MIT) | HuggingFace (poids, Apache 2.0) | Publié le |
|---|---|---|---|
| FootSegNet | [Ov3rLoRd-MLEngineer/footsegnet](https://github.com/Ov3rLoRd-MLEngineer/footsegnet) | [Ov3rLoRd-MLEngineer/footsegnet](https://huggingface.co/Ov3rLoRd-MLEngineer/footsegnet) | 2026-07-26 |
| HandSegNet | [Ov3rLoRd-MLEngineer/handsegnet](https://github.com/Ov3rLoRd-MLEngineer/handsegnet) | [Ov3rLoRd-MLEngineer/handsegnet](https://huggingface.co/Ov3rLoRd-MLEngineer/handsegnet) | 2026-07-30 |

Chaque repo public ne contient que les outils d'inférence/conversion
(`standalone_infer.py`, `convert_to_safetensors.py`) — le pipeline
d'entraînement complet (`train.py`, `build_coco.py`, `annotate.py`,
`generate_dataset.py`) reste privé dans ce dépôt, car couplé à
`config.py`/`agents.*`.

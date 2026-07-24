# FootSegNet → Control-LoRA SDXL (Ov3rLoRd Pipeline)

Conditionne la génération SDXL (`fabricatedXL_v70`) sur une carte de
segmentation pied/chaussure produite par **FootSegNet v1** (SAM ViT-B
fine-tuné, val IoU ≈ 0.93), pour permettre de générer des poses/vêtements
tout en gardant un contrôle explicite sur le cadrage et la forme des
pieds/chaussures.

**Control-LoRA, pas ControlNet plein** : le dataset annoté à la main reste
modeste (300 images) même complété par des pré-masques auto. Un ControlNet
SDXL complet (~1.5 md de paramètres entraînables) est disproportionné pour ce
volume de données et cette VRAM (RTX 5080 16 Go). On entraîne à la place des
adaptateurs LoRA (rang faible) sur un `ControlNetModel` dont le backbone
(copié de l'UNet SDXL) reste gelé — voir l'en-tête de `train_control_lora.py`
pour le détail exact de ce qui est gelé/entraîné.

Tout s'exécute avec **py -3.12** depuis `D:\OVERLORD\footsegnet\controlnet\`.

## Flux complet

```
1. PRÉPARATION DATASET   py -3.12 prepare_dataset.py --count 200
                          -> génère 200 nouvelles images (wildcards v2 :
                             variété x4 + cohérence genre/vêtements),
                             pré-masque automatiquement (pose DWPose +
                             fallback grounding VLM, SAM FootSegNet v1),
                             assemble les paires dans dataset\{images,
                             conditioning_images}\ + manifest.jsonl

2. TRI QUALITÉ            py -3.12 quality_sort.py --write-manifest
                          -> classe chaque paire exploitable / à corriger /
                             à exclure avec RAISON documentée
                             (quality_report.txt), écrit
                             dataset\manifest_filtered.jsonl (retire les
                             "à exclure")

3. TEST DE CONVERGENCE    py -3.12 train_control_lora.py --test-run \
                             --manifest dataset\manifest_filtered.jsonl
                          -> sous-ensemble de 100-150 paires, peu de steps,
                             preview visuelle périodique
                             (output\control_lora_v1\validation\) — vérifier
                             que la loss descend ET que la preview devient
                             visuellement cohérente AVANT l'étape 4

4. RUN COMPLET             py -3.12 train_control_lora.py \
                             --manifest dataset\manifest_filtered.jsonl \
                             --max-train-steps 8000
                          -> NE PAS lancer sans avoir validé l'étape 3.
                             --max-train-steps est obligatoire (pas de
                             défaut implicite) pour éviter un lancement
                             accidentel.
```

## Structure des dossiers

```
D:\OVERLORD\footsegnet\controlnet\
├── README.md
├── prepare_dataset.py      # génération + pré-masque + assemblage des paires
├── quality_sort.py         # tri exploitable / à corriger / à exclure
├── train_control_lora.py   # entraînement Control-LoRA (diffusers + peft)
├── dataset\
│   ├── images\              # images sources (copie de dataset\raw\)
│   ├── conditioning_images\ # cartes de segmentation (BLANC=pied/chaussure)
│   ├── manifest.jsonl       # toutes les paires assemblées
│   └── manifest_filtered.jsonl  # après quality_sort.py --write-manifest
├── quality_report.txt      # raison de chaque exclusion/avertissement
├── quality_report.json     # même contenu, machine-readable
└── output\
    └── control_lora_v1\
        ├── validation\      # previews PNG périodiques (contrôle qualité humain)
        ├── checkpoint-N\    # checkpoints intermédiaires (adapter LoRA)
        └── final\           # adapter LoRA final (peft : adapter_config.json
                              #  + adapter_model.safetensors)
```

## Format des données

Une paire = une ligne dans `manifest.jsonl` :

```json
{"file_name": "images/footsegnet_00301.png",
 "conditioning_image": "conditioning_images/footsegnet_00301.png",
 "text": "score_9, score_8_up, source_anime, 1girl, solo, full body, ...",
 "mask_source": "manual" | "auto"}
```

- `file_name` / `conditioning_image` : chemins relatifs à `dataset\`.
- `text` : prompt résolu (wildcards déjà substitués) issu de
  `dataset\raw\manifest.json` — sert de caption d'entraînement.
- `mask_source` : `manual` = masque annoté à la main (`masks_raw\`, vérité
  terrain) ; `auto` = pré-masque FootSegNet v1 (`premasks\`, via pose DWPose
  + fallback grounding VLM quand la pose échoue).

Convention de la carte de conditionnement : **BLANC (255) = pied/chaussure,
NOIR (0) = fond** (convention ML/dataset — cf. `footsegnet\README.md`), PAS
la convention pipeline inpaint (`infer.py` y sort en `pipeline_convention=False`
pour ce cas d'usage).

## Cohérence genre/vêtements (wildcards v2)

`footsegnet\wildcards\outfits_{neutral,feminine,masculine,cross}.txt` et
`shoes_{neutral,feminine,masculine,cross}.txt` remplacent les anciens
`outfits.txt`/`shoes.txt` (pool global unique). `generate_dataset.py`
résout `__outfits__`/`__shoes__` selon le genre du template (`1girl`/`1boy`,
détecté dans le texte du prompt) :

- pool `neutral` + pool genré du template (`feminine` ou `masculine`) —
  tirage normal ;
- `CROSS_PROBABILITY` (12 %, cf. `generate_dataset.py`) de tirer à la place
  dans le pool `cross` — association délibérément "cross-gender" (ex. homme
  en jupe/talons), **assumée et documentée**, pas une collision accidentelle
  entre deux pools indépendants.

Objectif : éviter que le Control-LoRA apprenne une corrélation
genre↔vêtement non intentionnelle causée par un simple biais
d'échantillonnage, tout en gardant la liberté créative existante (rien n'est
interdit, juste plus conscient).

`wildcards\lighting.txt` (nouveau, 30 entrées) est maintenant piochée dans
tous les templates via `__lighting__` — auparavant seulement inline dans 1
template sur 8.

## Tri qualité — catégories

`quality_sort.py` classe chaque image de `dataset\raw\` (indépendamment de
l'assemblage `prepare_dataset.py`, à partir de `masks_raw\` +
`premasks\_provenance.csv`) :

| Catégorie      | Condition                                                             |
|----------------|------------------------------------------------------------------------|
| `exploitable`  | masque manuel, OU pré-masque via bbox DWPose avec couverture plausible |
| `a_corriger`   | pré-masque via fallback grounding VLM (DWPose a échoué), OU couverture masque hors plage plausible (`--min-pct`/`--max-pct`) |
| `a_exclure`    | aucune bbox dérivable (pose atypique), échec d'inférence SAM, ou aucun masque disponible |

Chaque ligne du rapport documente la raison précise (pas de rejet
silencieux) — voir `quality_report.txt` après exécution.

## Dépendances

En plus de `torch`/`segment-anything` déjà requis par FootSegNet v1 (voir
`footsegnet\README.md`) :

```
py -3.12 -m pip install diffusers accelerate peft bitsandbytes
```

Versions validées dans cet environnement au moment de l'écriture :
`diffusers==0.38.0`, `transformers==4.57.6`, `accelerate==1.14.0`,
`peft==0.19.1`, `bitsandbytes==0.49.2`, `torch==2.11.0+cu128` (CUDA
disponible).

## Notes d'implémentation

- **VAE** : `train_control_lora.py` utilise `sdxl_vae.safetensors`
  (ComfyUI\models\vae\), pas `taesdxl`. ADR-002 impose taesdxl pour
  *l'inférence* du pipeline (le VAE plein était corrompu à l'époque) ; pour
  *l'entraînement*, un décodeur distillé temps réel comme taesdxl est
  inadapté à encoder les latents cibles (perte de fidélité). Le fichier
  `sdxl_vae.safetensors` est présent et a été vérifié disponible avant ce
  choix — ADR-002 reste inchangé pour le reste du pipeline.
- **Checkpoint** : chargé directement depuis le fichier ComfyUI
  (`StableDiffusionXLPipeline.from_single_file`), pas de conversion au
  format diffusers nécessaire.
- **Sortie** : adapter LoRA au format `peft` (diffusers `ControlNetModel`).
  Ce n'est PAS le format `control-lora-*-rank256.safetensors` de Stability AI
  utilisé par les custom nodes ComfyUI existants (`control-lora-canny-rank256
  .safetensors`, etc. dans ComfyUI\models\controlnet\) — une conversion serait
  nécessaire pour une intégration ComfyUI, hors périmètre de cette
  préparation (scripts de génération/tri/entraînement uniquement).
- **Seeds** : `generate_dataset.py` suit toujours `base_seed + i * 137`
  (ADR-008). L'entraînement a son propre `--seed` (défaut 42), indépendant.

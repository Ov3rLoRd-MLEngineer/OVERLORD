# Installation & Premier Lancement — Usine à Animés

## Structure du dossier de travail

```
PIPELINE PROJECT/
├── maestro.py                   ← Chef d'orchestre (point d'entrée principal)
├── agent_supervisor_v2.py       ← Superviseur ComfyUI (déjà en ta possession)
├── Combined_V35_API.json        ← Workflow ComfyUI fusionné (déjà en ta possession)
├── config.json                  ← Jobs batch pour la production seule
├── requirements.txt             ← Dépendances Python
├── agents/
│   ├── __init__.py
│   ├── sourcing.py              ← Agent veilleur web
│   ├── scenario.py              ← Agent scénariste + Script Doctor
│   ├── storyboard.py            ← Agent storyboard
│   └── postprod.py              ← Montage, TTS, lip-sync
└── workspace/                   ← Créé automatiquement
    ├── logs/
    ├── archive/
    ├── scripts/
    ├── storyboards/
    ├── postprod/
    ├── exports/
    ├── sourcing_cache/
    ├── pipeline_state.json
    └── failed_jobs.json
```

## Étape 1 — Installer les dépendances

```bash
pip install requests Pillow feedparser pytrends gTTS
```

## Étape 2 — Test immédiat (Black Box ComfyUI seule)

Lance uniquement la production ComfyUI avec le config.json fourni :

```bash
python agent_supervisor_v2.py config.json
```

## Étape 3 — Pipeline complet (avec sourcing + scénario)

Nécessite une clé API Anthropic (pour les agents scénariste/storyboard).
Ajoute ta clé dans les headers des fichiers agents/scenario.py et agents/storyboard.py.

```bash
python maestro.py --media-type anime --universe "Dragon Ball Super Broly"
```

## Étape 4 — Pipeline depuis un type de média spécifique

```bash
# Animé court
python maestro.py --media-type anime --universe "Dragon Ball" --lora "mon_lora.safetensors"

# Manga
python maestro.py --media-type manga --universe "One Piece arc Wano"

# Reprendre depuis le storyboard (si scénario déjà généré)
python maestro.py --from-block storyboard

# Production seule depuis config.json
python agent_supervisor_v2.py config.json
```

## Modes de lancement

| Commande | Effet |
|---|---|
| `python maestro.py` | Pipeline complet (sourcing → post-prod) |
| `python maestro.py --from-block scenario` | Reprendre depuis le scénario |
| `python maestro.py --media-type manga` | Forcer le type manga |
| `python agent_supervisor_v2.py config.json` | Production ComfyUI seule |
| `python agent_supervisor_v2.py config.json --no-resume` | Forcer un redémarrage |

## Dépendances optionnelles par phase

| Phase | Outil | Commande |
|---|---|---|
| Sourcing RSS | feedparser | `pip install feedparser` |
| Google Trends | pytrends | `pip install pytrends` |
| TTS basique | gTTS | `pip install gTTS` |
| TTS qualité | ElevenLabs | Clé API requise |
| Lip-sync | SadTalker | Installation GPU séparée |
| Montage | ffmpeg | Télécharger sur ffmpeg.org |
| Mémoire | ChromaDB | `pip install chromadb` (Phase 5) |
| Watermark | invisible-watermark | `pip install invisible-watermark` (Phase 4) |

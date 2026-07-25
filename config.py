"""
config.py — racines de chemins centralisees pour Ov3rLoRd.
Importer ce module plutot que de redefinir un chemin en dur dans un script.

OVERLORD_ROOT est auto-detecte (emplacement de ce fichier) et n'a normalement
pas besoin d'etre surcharge. COMFYUI_ROOT est hors du repo (autre disque
possible) et doit etre surcharge via la variable d'environnement
COMFYUI_ROOT (.env) si l'installation ComfyUI n'est pas a l'emplacement
historique.
"""

import os
from pathlib import Path


def _load_env_file(path):
    """Parse minimaliste de .env (KEY=value, memes regles que agents/config_manager.py) --
    pas de dependance python-dotenv, rien ne charge .env dans os.environ ailleurs dans
    le repo pour OVERLORD_ROOT/COMFYUI_ROOT."""
    values = {}
    if path.exists():
        for line in path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                values[k.strip()] = v.strip().strip('"').strip("'")
    return values


def _cfg(name, default, env_vals):
    """Precedence : variable d'environnement reelle > .env > defaut."""
    return os.environ.get(name) or env_vals.get(name) or default


_ENV_VALS = _load_env_file(Path(__file__).resolve().parent / ".env")

OVERLORD_ROOT = Path(_cfg("OVERLORD_ROOT", str(Path(__file__).resolve().parent), _ENV_VALS))

COMFYUI_ROOT = Path(_cfg("COMFYUI_ROOT", r"D:\Ov3rLoRd AI\ComfyUI", _ENV_VALS))

# --- ComfyUI ---
COMFYUI_INPUT = COMFYUI_ROOT / "input"
COMFYUI_OUTPUT = COMFYUI_ROOT / "output"
COMFYUI_MODELS = COMFYUI_ROOT / "models"
CHECKPOINTS_DIR = COMFYUI_MODELS / "checkpoints"
LORAS_DIR = COMFYUI_MODELS / "loras"
SAM_CHECKPOINT = COMFYUI_MODELS / "sams" / "sam_vit_b_01ec64.pth"

# --- Ov3rLoRd ---
WORKSPACE_DIR = OVERLORD_ROOT / "workspace"
DEMO_DIR = OVERLORD_ROOT / "DEMO"
FOOTSEGNET_ROOT = OVERLORD_ROOT / "footsegnet"
HANDSEGNET_ROOT = OVERLORD_ROOT / "handsegnet"
FACESEGNET_ROOT = OVERLORD_ROOT / "facesegnet"
BODYSEGNET_ROOT = OVERLORD_ROOT / "bodysegnet"

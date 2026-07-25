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

OVERLORD_ROOT = Path(os.environ.get("OVERLORD_ROOT", str(Path(__file__).resolve().parent)))

COMFYUI_ROOT = Path(os.environ.get("COMFYUI_ROOT", r"D:\Ov3rLoRd AI\ComfyUI"))

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

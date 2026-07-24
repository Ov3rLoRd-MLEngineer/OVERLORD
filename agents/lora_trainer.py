# ██████╗ ██╗   ██╗██████╗ ██████╗ ██╗      ██████╗ ██████╗ ██████╗
# ██╔═══██╗██║   ██║╚════██╗██╔══██╗██║     ██╔═══██╗██╔══██╗██╔══██╗
# ██║   ██║██║   ██║ █████╔╝██████╔╝██║     ██║   ██║██████╔╝██║  ██║
# ██║   ██║╚██╗ ██╔╝ ╚═══██╗██╔══██╗██║     ██║   ██║██╔══██╗██║  ██║
# ╚██████╔╝ ╚████╔╝ ██████╔╝██║  ██║███████╗╚██████╔╝██║  ██║██████╔╝
# ╚═════╝   ╚═══╝  ╚═════╝ ╚═╝  ╚═╝╚══════╝ ╚═════╝ ╚═╝  ╚═╝╚═════╝
# Ov3rLoRd -- pipeline de production anime autonome (ComfyUI)
# https://github.com/Ov3rLoRd-MLEngineer
#
"""
agents/lora_trainer.py — Entraînement LoRa Autonome V1.70
L'IA entraîne ses propres LoRas depuis ses meilleures productions.
Pipeline complet : sélection images → tagging → kohya_ss → validation → intégration.

Prérequis :
  - kohya_ss installé : git clone https://github.com/bmaltais/kohya_ss
  - pip install wd14-tagger (ou API CivitAI pour tagging)
  - RTX 5080 recommandée (16GB VRAM) — RTX 2070 possible avec batch_size=1

Usage :
  python agents/lora_trainer.py --trigger "my_character" --steps 1500
  python agents/lora_trainer.py --auto  # sélection et entraînement automatiques
"""

import json
import logging
import os
import shutil
import subprocess
import sys
import io
from datetime import datetime
from pathlib import Path

if hasattr(sys.stdout, 'buffer'):
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

try:
    from agents.config_manager import get_config
    CFG_OK = True
except ImportError:
    CFG_OK = False

try:
    from agents.context_bus import get_bus
    BUS_OK = True
except ImportError:
    BUS_OK = False

try:
    from agents.overlord_utils import fallback_llm, safe_json_parse
    UTILS_OK = True
except ImportError:
    UTILS_OK = False

LORA_DIR     = Path(r"D:/Ov3rLoRd AI/ComfyUI/models/loras")
DATASET_DIR  = Path("workspace/lora_datasets")
OUTPUT_DIR   = Path("workspace/lora_outputs")
KOHYA_PATH   = Path("D:/kohya_ss")  # à adapter
TRAINER_LOG  = Path("workspace/logs/lora_training.jsonl")

# Paramètres d'entraînement par défaut (RTX 5080 16GB)
DEFAULT_TRAIN_CONFIG = {
    "pretrained_model":  r"D:/Ov3rLoRd AI/ComfyUI/models/checkpoints/fabricatedXL_v70.safetensors",
    "network_module":    "networks.lora",
    "network_dim":       32,
    "network_alpha":     16,
    "learning_rate":     "1e-4",
    "unet_lr":           "1e-4",
    "text_encoder_lr":   "1e-5",
    "max_train_steps":   1500,
    "train_batch_size":  1,
    "resolution":        "1024,1024",
    "mixed_precision":   "fp16",
    "save_precision":    "fp16",
    "optimizer_type":    "AdamW8bit",
    "lr_scheduler":      "cosine_with_restarts",
    "lr_warmup_steps":   100,
    "save_every_n_steps": 500,
    "caption_extension": ".txt",
}


def prepare_dataset(source_images: list[Path], trigger_word: str,
                    min_score: float = 80.0,
                    target_n: int = 50,
                    logger=None) -> Path:
    """
    Prépare un dataset d'entraînement depuis les images sélectionnées.
    Copie les images + crée des fichiers .txt de captions avec le trigger word.
    """
    log = logger or logging.getLogger("lora_trainer")

    ts       = datetime.now().strftime("%Y%m%d_%H%M%S")
    ds_dir   = DATASET_DIR / f"{trigger_word}_{ts}" / "images"
    ds_dir.mkdir(parents=True, exist_ok=True)

    copied = 0
    for img in source_images[:target_n]:
        if img.exists():
            dest = ds_dir / img.name
            shutil.copy2(img, dest)
            # Caption de base avec le trigger word
            caption_file = dest.with_suffix(".txt")
            caption_file.write_text(
                f"{trigger_word}, masterpiece, best quality, anime style, 1girl",
                encoding='utf-8'
            )
            copied += 1

    log.info(f"[TRAINER] Dataset préparé : {copied} images dans {ds_dir}")
    return ds_dir.parent  # retourne le dossier parent (contient le sous-dossier images/)


def auto_tag_images(dataset_dir: Path, logger=None) -> int:
    """
    Tag automatique des images via WD14 tagger si disponible.
    Sinon : génère des captions via LLM depuis les noms de fichiers.
    """
    log    = logger or logging.getLogger("lora_trainer")
    images = list((dataset_dir / "images").glob("*.png")) + \
             list((dataset_dir / "images").glob("*.jpg"))

    # Essayer WD14 tagger
    try:
        result = subprocess.run(
            ["python", "-m", "wd14_tagger", "--input", str(dataset_dir / "images"),
             "--threshold", "0.35", "--caption-extension", ".txt"],
            capture_output=True, timeout=300
        )
        if result.returncode == 0:
            log.info(f"[TRAINER] WD14 tagger OK — {len(images)} images taguées")
            return len(images)
    except Exception:
        pass

    # Fallback : LLM génère des tags depuis le nom de fichier
    if UTILS_OK:
        log.info("[TRAINER] Fallback LLM pour le tagging...")
        for img in images[:20]:  # Limiter pour la vitesse
            caption_file = img.with_suffix(".txt")
            if caption_file.exists() and len(caption_file.read_text()) > 30:
                continue  # déjà taguée
            system = "You are an anime image tagger. Reply with comma-separated Danbooru tags only."
            prompt = f"Generate Booru tags for an anime image named: {img.stem}. Include: 1girl, style, pose, expression tags. Reply ONLY with comma-separated tags."
            raw = fallback_llm(prompt, system=system, max_tokens=100, logger=log)
            if raw.strip():
                caption_file.write_text(raw.strip(), encoding='utf-8')

    tagged = sum(1 for img in images if img.with_suffix(".txt").exists())
    log.info(f"[TRAINER] {tagged}/{len(images)} images avec captions")
    return tagged


def build_kohya_config(dataset_dir: Path, output_dir: Path,
                        trigger_word: str, steps: int = 1500) -> Path:
    """Génère le fichier de config kohya_ss."""
    config = DEFAULT_TRAIN_CONFIG.copy()
    config.update({
        "max_train_steps":  steps,
        "output_dir":       str(output_dir),
        "output_name":      f"ovlrd_{trigger_word}",
        "logging_dir":      str(output_dir / "logs"),
        "train_data_dir":   str(dataset_dir),
    })

    # Ajuster pour la VRAM disponible
    if CFG_OK:
        c = get_config()
        vram = c.get("gpu.vram_gb", 8, scope="global")
        if vram <= 8:
            config["train_batch_size"] = 1
            config["gradient_checkpointing"] = True
        elif vram >= 16:
            config["train_batch_size"] = 2
            config["network_dim"] = 64

    config_path = output_dir / "train_config.json"
    output_dir.mkdir(parents=True, exist_ok=True)
    config_path.write_text(json.dumps(config, indent=2), encoding='utf-8')
    return config_path


def train_lora(dataset_dir: Path, trigger_word: str,
               steps: int = 1500, logger=None) -> Path | None:
    """Lance l'entraînement kohya_ss."""
    log = logger or logging.getLogger("lora_trainer")

    ts         = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_dir = OUTPUT_DIR / f"{trigger_word}_{ts}"
    config     = build_kohya_config(dataset_dir, output_dir, trigger_word, steps)

    train_script = KOHYA_PATH / "train_network.py"
    if not train_script.exists():
        log.error(f"[TRAINER] kohya_ss non trouvé : {KOHYA_PATH}")
        log.error("[TRAINER] Installer : git clone https://github.com/bmaltais/kohya_ss")
        return None

    log.info(f"[TRAINER] Entraînement démarré — {steps} steps · trigger='{trigger_word}'")

    if BUS_OK:
        try:
            get_bus().write("lora.training", True, agent_id="lora_trainer")
            get_bus().write("lora.trigger", trigger_word, agent_id="lora_trainer")
            get_bus().write("lora.steps", steps, agent_id="lora_trainer")
        except Exception:
            pass

    try:
        proc = subprocess.Popen(
            [sys.executable, str(train_script), "--config_file", str(config)],
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            text=True, encoding='utf-8', errors='replace',
            cwd=str(KOHYA_PATH)
        )
        step_current = 0
        for line in proc.stdout:
            line = line.strip()
            if "step" in line.lower() and "/" in line:
                # Parser la progression : "step 100/1500"
                import re
                m = re.search(r'(\d+)/(\d+)', line)
                if m:
                    step_current = int(m.group(1))
                    if step_current % 100 == 0:
                        log.info(f"[TRAINER] Step {step_current}/{steps} "
                                 f"({step_current/steps*100:.0f}%)")
                        if BUS_OK:
                            try:
                                get_bus().write("lora.step_current", step_current,
                                                agent_id="lora_trainer")
                            except Exception:
                                pass

        proc.wait()
        if proc.returncode != 0:
            log.error(f"[TRAINER] Entraînement échoué (code {proc.returncode})")
            return None

    except Exception as e:
        log.error(f"[TRAINER] Exception : {e}")
        return None

    # Trouver le fichier .safetensors produit
    safetensors = list(output_dir.glob("*.safetensors"))
    if not safetensors:
        log.error("[TRAINER] Aucun .safetensors produit")
        return None

    lora_path = safetensors[-1]  # dernière checkpoint
    log.info(f"[TRAINER] LoRa produite : {lora_path.name}")
    return lora_path


def integrate_lora(lora_path: Path, display_name: str, logger=None) -> bool:
    """Copie la LoRa dans ComfyUI/models/loras/ et met à jour AVAILABLE_LORAS."""
    log = logger or logging.getLogger("lora_trainer")

    if not LORA_DIR.exists():
        log.error(f"[TRAINER] Dossier LoRa introuvable : {LORA_DIR}")
        return False

    dest = LORA_DIR / lora_path.name
    shutil.copy2(lora_path, dest)
    log.info(f"[TRAINER] LoRa intégrée : {dest}")

    # Mettre à jour config_manager
    if CFG_OK:
        try:
            c = get_config()
            loras = c.get("loras.available", [])
            if lora_path.name not in loras:
                loras.append(lora_path.name)
                c.set("loras.available", loras)
                log.info(f"[TRAINER] AVAILABLE_LORAS mis à jour : {len(loras)} LoRas")
        except Exception as e:
            log.warning(f"[TRAINER] Mise à jour config échouée : {e}")

    # Log
    TRAINER_LOG.parent.mkdir(parents=True, exist_ok=True)
    with open(TRAINER_LOG, 'a', encoding='utf-8') as f:
        f.write(json.dumps({
            "ts":           datetime.now().isoformat(),
            "name":         lora_path.name,
            "display_name": display_name,
            "path":         str(dest),
        }, ensure_ascii=False) + '\n')

    if BUS_OK:
        try:
            get_bus().write("lora.training",    False, agent_id="lora_trainer")
            get_bus().write("lora.last_trained", lora_path.name, agent_id="lora_trainer")
        except Exception:
            pass

    return True


def run_auto_training(archive_dir: Path = None, trigger_word: str = "ovlrd_custom",
                       steps: int = 1500, min_score: float = 80.0,
                       logger=None) -> dict:
    """Pipeline complet autonome : sélection → dataset → tag → train → intégrer."""
    log = logger or logging.getLogger("lora_trainer")
    log.info(f"[TRAINER] Pipeline autonome — trigger='{trigger_word}' steps={steps}")

    # Trouver les images sources
    if not archive_dir:
        ar = Path("workspace/archive")
        runs = sorted(ar.iterdir(), key=lambda p: p.stat().st_mtime, reverse=True) if ar.exists() else []
        sources = []
        for run_dir in runs[:5]:  # 5 derniers runs
            sources.extend(list(run_dir.rglob("*.png"))[:10])
    else:
        sources = list(archive_dir.rglob("*.png"))

    if len(sources) < 20:
        log.warning(f"[TRAINER] Pas assez d'images sources ({len(sources)} < 20)")
        return {"error": "not_enough_images", "found": len(sources)}

    log.info(f"[TRAINER] {len(sources)} images sources trouvées")

    # 1. Préparer dataset
    ds_dir = prepare_dataset(sources, trigger_word, min_score=min_score, logger=log)

    # 2. Tagger
    tagged = auto_tag_images(ds_dir, logger=log)
    if tagged < 15:
        log.warning(f"[TRAINER] Trop peu d'images taguées ({tagged})")

    # 3. Entraîner
    lora_path = train_lora(ds_dir, trigger_word, steps=steps, logger=log)
    if not lora_path:
        return {"error": "training_failed"}

    # 4. Intégrer
    integrated = integrate_lora(lora_path, trigger_word, logger=log)

    return {
        "success":      integrated,
        "lora_name":    lora_path.name,
        "trigger_word": trigger_word,
        "steps":        steps,
        "dataset_size": tagged,
        "timestamp":    datetime.now().isoformat(),
    }


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Ov3rLoRd LoRa Trainer V1.70")
    parser.add_argument("--trigger",  type=str, default="ovlrd_style",
                        help="Mot déclencheur de la LoRa")
    parser.add_argument("--steps",    type=int, default=1500)
    parser.add_argument("--auto",     action="store_true",
                        help="Pipeline entièrement autonome")
    parser.add_argument("--min-score", type=float, default=80.0)
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO,
                        format="%(asctime)s [%(levelname)s] %(message)s")

    if args.auto:
        result = run_auto_training(trigger_word=args.trigger, steps=args.steps,
                                    min_score=args.min_score)
        print(json.dumps(result, indent=2, ensure_ascii=False))
    else:
        print("=== LoRa Trainer V1.70 ===")
        print(f"Kohya SS path : {KOHYA_PATH}")
        print(f"LoRa output   : {LORA_DIR}")
        print(f"Trigger word  : {args.trigger}")
        print(f"Steps         : {args.steps}")
        print()
        print("Prérequis :")
        print("  git clone https://github.com/bmaltais/kohya_ss D:/kohya_ss")
        print("  pip install wd14-tagger")
        print()
        print("Lancer avec --auto pour le pipeline complet autonome.")

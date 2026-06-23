"""
agents/v140_model_downloader.py -- Ov3rLoRd V1.40 -- Agent Telechargement Modeles
Detecte les modeles manquants dans ComfyUI et les telecharge automatiquement.
V1.49o : overlord_utils centralise, context_bus connecte, datetime.UTC corrige.
"""

import os
import json
import time
import logging
import threading
import hashlib
from pathlib import Path
from dataclasses import dataclass, field
from typing import Optional, Callable
from datetime import datetime, timezone

try:
    import requests
    REQUESTS_OK = True
except ImportError:
    REQUESTS_OK = False

try:
    from tqdm import tqdm
    TQDM_OK = True
except ImportError:
    TQDM_OK = False

try:
    from agents.overlord_utils import fallback_llm, safe_json_parse
    UTILS_OK = True
except ImportError:
    UTILS_OK = False
    fallback_llm    = None
    safe_json_parse = None

try:
    from agents.context_bus import get_bus
    BUS_OK = True
except ImportError:
    BUS_OK = False

DOWNLOAD_DIR = Path("workspace/model_downloads")
MODELS_DIR   = Path("D:/IA Local/ComfyUI Installation Local/ComfyUI_windows_portable/ComfyUI/models")
CLAUDE_MODEL = "claude-sonnet-4-6"
log          = logging.getLogger("model_downloader")


def _llm(prompt: str, system: str = "", max_tokens: int = 400) -> str:
    if UTILS_OK and fallback_llm:
        return fallback_llm(prompt, system=system, model=CLAUDE_MODEL, max_tokens=max_tokens)
    return ""


# ── Catalogue de modeles connus ───────────────────────────────────────
MODEL_CATALOG = {
    "sdxl_vae": {
        "name":    "SDXL VAE officiel",
        "url":     "https://huggingface.co/stabilityai/sdxl-vae/resolve/main/sdxl_vae.safetensors",
        "dest":    "vae/sdxl_vae.safetensors",
        "size_mb": 335,
        "auth":    False,
    },
    "face_yolov9c": {
        "name":    "YOLO Face Detection v9",
        "url":     "https://huggingface.co/Bingsu/adetailer/resolve/main/face_yolov9c.pt",
        "dest":    "ultralytics/bbox/face_yolov9c.pt",
        "size_mb": 51,
        "auth":    False,
    },
    "sam_vit_b": {
        "name":    "SAM ViT-B Base",
        "url":     "https://dl.fbaipublicfiles.com/segment_anything/sam_vit_b_01ec64.pth",
        "dest":    "sams/sam_vit_b_01ec64.pth",
        "size_mb": 375,
        "auth":    False,
    },
    "4x_ultrasharp": {
        "name":    "4x UltraSharp upscaler",
        "url":     "https://huggingface.co/Kim2091/AnimeSharp/resolve/main/4x-UltraSharp.pth",
        "dest":    "upscale_models/4x-UltraSharp.pth",
        "size_mb": 67,
        "auth":    False,
    },
}


@dataclass
class DownloadTask:
    model_id:  str
    name:      str
    url:       str
    dest_path: Path
    size_mb:   float      = 0
    auth:      bool       = False
    status:    str        = "pending"  # pending|downloading|done|failed|skipped
    progress:  float      = 0.0
    error:     str        = ""
    started_at:float      = field(default_factory=time.time)
    finished_at:float     = 0.0


class ModelDownloader:

    def __init__(self, models_dir: Path = None, logger: logging.Logger = None):
        self.log       = logger or log
        self.models_dir= models_dir or MODELS_DIR
        self._tasks:   dict[str, DownloadTask] = {}
        self._lock     = threading.Lock()
        DOWNLOAD_DIR.mkdir(parents=True, exist_ok=True)

    def scan_missing(self) -> list[str]:
        """Detecte les modeles du catalogue absents du dossier ComfyUI."""
        missing = []
        for model_id, info in MODEL_CATALOG.items():
            dest = self.models_dir / info["dest"]
            if not dest.exists():
                missing.append(model_id)
                self.log.info(f"[DOWNLOADER] Manquant : {info['name']} -> {dest}")
        return missing

    def download(self, model_id: str,
                 on_progress: Callable = None) -> DownloadTask:
        info = MODEL_CATALOG.get(model_id)
        if not info:
            self.log.error(f"[DOWNLOADER] Modele inconnu : {model_id}")
            return DownloadTask(model_id=model_id, name=model_id,
                                url="", dest_path=Path("."), status="failed",
                                error="modele non catalogue")

        dest_path = self.models_dir / info["dest"]
        task      = DownloadTask(
            model_id  = model_id,
            name      = info["name"],
            url       = info["url"],
            dest_path = dest_path,
            size_mb   = info.get("size_mb", 0),
            auth      = info.get("auth", False),
        )

        with self._lock:
            self._tasks[model_id] = task

        if dest_path.exists():
            task.status = "skipped"
            self.log.info(f"[DOWNLOADER] Deja present : {info['name']}")
            return task

        if info.get("auth"):
            task.status = "failed"
            task.error  = f"Authentification requise. Telecharge manuellement : {info['url']}"
            self.log.warning(f"[DOWNLOADER] Auth requise pour {info['name']}")
            return task

        if not REQUESTS_OK:
            task.status = "failed"
            task.error  = "pip install requests"
            return task

        try:
            dest_path.parent.mkdir(parents=True, exist_ok=True)
            task.status = "downloading"
            self.log.info(f"[DOWNLOADER] Debut : {info['name']} ({info.get('size_mb',0)} MB)")

            resp = requests.get(info["url"], stream=True, timeout=30)
            resp.raise_for_status()
            total   = int(resp.headers.get("content-length", 0))
            written = 0

            with open(dest_path, "wb") as f:
                for chunk in resp.iter_content(chunk_size=1024*1024):
                    if chunk:
                        f.write(chunk)
                        written += len(chunk)
                        if total:
                            task.progress = written / total
                            if on_progress:
                                on_progress(model_id, task.progress)

            task.status      = "done"
            task.progress    = 1.0
            task.finished_at = time.time()
            self.log.info(f"[DOWNLOADER] OK {info['name']} -> {dest_path}")

            if BUS_OK:
                try:
                    get_bus().write(f"downloader.{model_id}", "done",
                                    agent_id="model_downloader")
                    get_bus().write("downloader.last_model", info["name"],
                                    agent_id="model_downloader")
                except Exception:
                    pass

        except Exception as e:
            task.status = "failed"
            task.error  = str(e)
            self.log.error(f"[DOWNLOADER] Echec {info['name']} : {e}")

        return task

    def download_missing(self) -> dict:
        """Telecharge tous les modeles manquants du catalogue."""
        missing = self.scan_missing()
        if not missing:
            self.log.info("[DOWNLOADER] Tous les modeles sont presents")
            return {"missing": 0, "downloaded": 0, "failed": []}

        self.log.info(f"[DOWNLOADER] {len(missing)} modele(s) manquant(s)")
        results = {"missing": len(missing), "downloaded": 0, "failed": []}

        for model_id in missing:
            task = self.download(model_id)
            if task.status == "done":
                results["downloaded"] += 1
            elif task.status == "failed":
                results["failed"].append({"id": model_id, "error": task.error})

        if BUS_OK:
            try:
                get_bus().write("downloader.missing_count", len(missing),
                                agent_id="model_downloader")
                get_bus().write("downloader.downloaded",    results["downloaded"],
                                agent_id="model_downloader")
            except Exception:
                pass

        return results

    def suggest_model(self, description: str) -> str:
        """Utilise le LLM pour suggerer le meilleur modele selon une description."""
        catalog_str = json.dumps(
            {k: {"name":v["name"],"size_mb":v.get("size_mb",0)} for k,v in MODEL_CATALOG.items()},
            ensure_ascii=False
        )
        prompt = (f"Catalogue de modeles disponibles :\n{catalog_str}\n\n"
                  f"L'utilisateur a besoin de : {description}\n"
                  f"Quel model_id recommandes-tu ? Reponds UNIQUEMENT avec le model_id exact.")
        raw = _llm(prompt, max_tokens=50)
        return raw.strip().lower() if raw else ""

    def get_status(self) -> dict:
        with self._lock:
            return {
                mid: {
                    "name":     t.name,
                    "status":   t.status,
                    "progress": round(t.progress * 100, 1),
                    "error":    t.error,
                }
                for mid, t in self._tasks.items()
            }


if __name__ == "__main__":
    import sys, io
    if hasattr(sys.stdout, "buffer"):
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    logging.basicConfig(level=logging.INFO)
    dl = ModelDownloader()
    missing = dl.scan_missing()
    print(f"Modeles manquants : {missing}")
    print("Pour telecharger : dl.download_missing()")
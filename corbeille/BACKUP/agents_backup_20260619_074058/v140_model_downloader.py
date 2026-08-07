"""
agents/v140_model_downloader.py — Ov3rLoRd V1.40 — Agent Téléchargement Modèles

Détecte les modèles manquants dans ComfyUI et les télécharge automatiquement.
Si le téléchargement direct est impossible (login requis), guide l'utilisateur
avec le lien exact et le dossier de destination.

Fonctionnement :
  1. Scanne les dossiers ComfyUI/models/ pour détecter les manquants
  2. Tente le téléchargement automatique (HuggingFace, GitHub, liens directs)
  3. Si impossible : affiche le lien le plus pertinent + dossier exact
  4. Intégré dans INSTALL_MODELS.bat et le launcher

Sources de téléchargement :
  - HuggingFace Hub (gratuit, pas de compte requis pour la plupart)
  - GitHub Releases
  - CivitAI (compte requis pour certains — guide utilisateur)

pip install huggingface_hub tqdm requests
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
import requests

DOWNLOADER_DIR = Path("workspace/model_downloader")
ANTHROPIC_URL  = "https://api.anthropic.com/v1/messages"

def _get_api_key() -> str:
    import os as _os
    from pathlib import Path as _P
    key = _os.environ.get("ANTHROPIC_API_KEY", "")
    if not key:
        for env in [_P(__file__).parent / ".env", _P(".env")]:
            if env.exists():
                for line in env.read_text(encoding="utf-8").splitlines():
                    if line.startswith("ANTHROPIC_API_KEY="):
                        key = line.split("=",1)[1].strip().strip('"').strip("'")
                        if key: break
            if key: break
    return key

CLAUDE_MODEL   = "claude-sonnet-4-6"

# ══════════════════════════════════════════════════════════════════════
# CATALOGUE DES MODÈLES REQUIS
# ══════════════════════════════════════════════════════════════════════

MODEL_CATALOG = {

    # ── Checkpoints SDXL ─────────────────────────────────────────────
    "noobai_sdxl": {
        "name":        "NoobAI-XL (Pony/SDXL)",
        "filename":    "noobaiXLNSFWPony_epsilonPred10.safetensors",
        "dest_folder": "models/checkpoints",
        "size_gb":     6.5,
        "required":    True,
        "auto_dl":     False,  # CivitAI → login requis
        "civitai_id":  "833294",
        "civitai_url": "https://civitai.com/models/833294",
        "hf_repo":     None,
        "description": "Checkpoint principal OverLord — modèle anime SDXL",
        "tags":        ["checkpoint","sdxl","anime","pony"],
    },

    # ── VAE ──────────────────────────────────────────────────────────
    "sdxl_vae": {
        "name":        "SDXL VAE",
        "filename":    "sdxl_vae.safetensors",
        "dest_folder": "models/vae",
        "size_gb":     0.33,
        "required":    True,
        "auto_dl":     True,
        "hf_repo":     "stabilityai/sdxl-vae",
        "hf_file":     "sdxl_vae.safetensors",
        "description": "VAE officiel SDXL — améliore la qualité des couleurs",
        "tags":        ["vae","sdxl"],
    },

    # ── Upscalers ────────────────────────────────────────────────────
    "4x_ultrasharp": {
        "name":        "4x-UltraSharp Upscaler",
        "filename":    "4x-UltraSharp.pth",
        "dest_folder": "models/upscale_models",
        "size_gb":     0.07,
        "required":    True,
        "auto_dl":     True,
        "direct_url":  "https://huggingface.co/lokCX/4x-Ultrasharp/resolve/main/4x-UltraSharp.pth",
        "description": "Upscaler x4 haute qualité — référence dans la communauté",
        "tags":        ["upscaler","esrgan"],
    },

    "4x_realesrgan": {
        "name":        "4x-RealESRGAN-anime",
        "filename":    "4x_NMKD-Superscale-SP_178000_G.pth",
        "dest_folder": "models/upscale_models",
        "size_gb":     0.07,
        "required":    False,
        "auto_dl":     True,
        "direct_url":  "https://huggingface.co/gemasai/4x_NMKD-Superscale-SP_178000_G/resolve/main/4x_NMKD-Superscale-SP_178000_G.pth",
        "description": "Upscaler anime spécialisé",
        "tags":        ["upscaler","anime"],
    },

    # ── ControlNet ────────────────────────────────────────────────────
    "controlnet_canny_sdxl": {
        "name":        "ControlNet Canny SDXL",
        "filename":    "controlnet-canny-sdxl-1.0.safetensors",
        "dest_folder": "models/controlnet",
        "size_gb":     2.5,
        "required":    False,
        "auto_dl":     True,
        "hf_repo":     "diffusers/controlnet-canny-sdxl-1.0",
        "hf_file":     "diffusion_pytorch_model.fp16.safetensors",
        "hf_rename":   "controlnet-canny-sdxl-1.0.safetensors",
        "description": "ControlNet Canny pour SDXL — contrôle des contours",
        "tags":        ["controlnet","sdxl","canny"],
    },

    "controlnet_openpose_sdxl": {
        "name":        "ControlNet OpenPose SDXL",
        "filename":    "controlnet-openpose-sdxl.safetensors",
        "dest_folder": "models/controlnet",
        "size_gb":     2.5,
        "required":    False,
        "auto_dl":     True,
        "hf_repo":     "thibaud/controlnet-openpose-sdxl-1.0",
        "hf_file":     "OpenPoseXL2.safetensors",
        "hf_rename":   "controlnet-openpose-sdxl.safetensors",
        "description": "ControlNet poses pour SDXL",
        "tags":        ["controlnet","sdxl","pose"],
    },

    # ── AnimateDiff ───────────────────────────────────────────────────
    "animatediff_v2": {
        "name":        "AnimateDiff Motion Module v2",
        "filename":    "mm_sd_v15_v2.ckpt",
        "dest_folder": "models/animatediff_models",
        "size_gb":     1.7,
        "required":    False,
        "auto_dl":     True,
        "hf_repo":     "guoyww/animatediff",
        "hf_file":     "mm_sd_v15_v2.ckpt",
        "description": "Module AnimateDiff v2 — animation de personnages",
        "tags":        ["animatediff","animation","video"],
    },

    # ── Clip Skip / CLIP ──────────────────────────────────────────────
    "clip_vit_l": {
        "name":        "CLIP ViT-L/14",
        "filename":    "clip_vision_g.safetensors",
        "dest_folder": "models/clip_vision",
        "size_gb":     3.5,
        "required":    False,
        "auto_dl":     True,
        "hf_repo":     "stabilityai/stable-diffusion-xl-base-1.0",
        "hf_file":     "text_encoder/model.safetensors",
        "hf_rename":   "clip_vision_g.safetensors",
        "description": "CLIP Vision pour IP-Adapter et img2img avancé",
        "tags":        ["clip","vision"],
    },

    # ── LLM pour les agents ───────────────────────────────────────────
    "llava_gguf": {
        "name":        "LLaVA 1.5 7B (GGUF quantifié)",
        "filename":    "llava-v1.5-7b-Q4_K_M.gguf",
        "dest_folder": "models/LLavacheckpoints",
        "size_gb":     4.1,
        "required":    False,
        "auto_dl":     True,
        "direct_url":  "https://huggingface.co/mys/ggml_llava-v1.5-7b/resolve/main/ggml-model-q4_k.gguf",
        "description": "Vision-Language Model pour l'auto-étiquetage des images",
        "tags":        ["llm","vision","captioning"],
    },
}


# ══════════════════════════════════════════════════════════════════════
# SCANNER DE MODÈLES
# ══════════════════════════════════════════════════════════════════════

@dataclass
class ModelStatus:
    """État d'un modèle."""
    model_id:    str
    name:        str
    filename:    str
    dest_folder: str
    present:     bool
    file_size_gb:float = 0.0
    status:      str   = "unknown"  # "present","missing","downloading","failed","manual_required"
    download_progress: float = 0.0
    error:       str   = ""


class ModelScanner:
    """Scanne les dossiers ComfyUI pour détecter les modèles manquants."""

    def __init__(self, comfyui_root: str = "", logger: logging.Logger = None):
        self.log          = logger or logging.getLogger("model_scanner")
        self.comfyui_root = self._find_comfyui_root(comfyui_root)

    def _find_comfyui_root(self, hint: str = "") -> Optional[Path]:
        """Trouve le dossier racine de ComfyUI."""
        candidates = [
            hint,
            r"D:\ComfyUI_windows_portable",
            r"D:\ComfyUI",
            r"D:\AI\ComfyUI_windows_portable",
            r"C:\ComfyUI_windows_portable",
            r"C:\ComfyUI",
        ]
        # Lire le chemin sauvegardé par LAUNCH_COMFYUI.bat
        cfg = Path("D:/OVERLORD/comfy_path.cfg")
        if cfg.exists():
            try:
                line = cfg.read_text().strip()
                if "=" in line:
                    candidates.insert(0, line.split("=",1)[1].strip())
            except Exception:
                pass

        for c in candidates:
            if c:
                p = Path(c)
                if p.exists() and (p / "models").exists():
                    self.log.info(f"[SCANNER] ComfyUI trouvé : {p}")
                    return p
        self.log.warning("[SCANNER] ComfyUI non trouvé — spécifie le chemin manuellement")
        return None

    def scan(self) -> dict[str, ModelStatus]:
        """Scanne tous les modèles du catalogue et retourne leur état."""
        results = {}
        if not self.comfyui_root:
            self.log.error("[SCANNER] Impossible de scanner — ComfyUI non trouvé")
            return results

        for model_id, config in MODEL_CATALOG.items():
            dest  = self.comfyui_root / config["dest_folder"]
            fpath = dest / config["filename"]

            if fpath.exists():
                size_gb = fpath.stat().st_size / 1e9
                status  = ModelStatus(
                    model_id=model_id, name=config["name"],
                    filename=config["filename"],
                    dest_folder=str(dest),
                    present=True, file_size_gb=round(size_gb,2),
                    status="present",
                )
            else:
                status = ModelStatus(
                    model_id=model_id, name=config["name"],
                    filename=config["filename"],
                    dest_folder=str(dest),
                    present=False, status="missing",
                )
            results[model_id] = status

        missing  = sum(1 for s in results.values() if not s.present)
        present  = sum(1 for s in results.values() if s.present)
        self.log.info(f"[SCANNER] {present} présents | {missing} manquants")
        return results

    def get_dest_path(self, model_id: str) -> Optional[Path]:
        """Retourne le chemin de destination pour un modèle."""
        if not self.comfyui_root:
            return None
        config = MODEL_CATALOG.get(model_id, {})
        return self.comfyui_root / config.get("dest_folder","models")


# ══════════════════════════════════════════════════════════════════════
# TÉLÉCHARGEUR
# ══════════════════════════════════════════════════════════════════════

class ModelDownloader:
    """Télécharge les modèles depuis HuggingFace ou liens directs."""

    def __init__(self, scanner: ModelScanner,
                 progress_cb: Callable = None,
                 logger: logging.Logger = None):
        self.log        = logger or logging.getLogger("model_dl")
        self.scanner    = scanner
        self.progress_cb= progress_cb or (lambda model_id, pct, msg: None)
        self._active    = {}  # model_id → thread
        DOWNLOADER_DIR.mkdir(parents=True, exist_ok=True)

    def download(self, model_id: str,
                  force: bool = False) -> dict:
        """
        Télécharge un modèle. Retourne immédiatement,
        le téléchargement tourne en arrière-plan.
        """
        config = MODEL_CATALOG.get(model_id)
        if not config:
            return {"error": f"Modèle inconnu : {model_id}"}

        dest_dir = self.scanner.get_dest_path(model_id)
        if not dest_dir:
            return {"error": "ComfyUI non trouvé — configure le chemin"}

        dest_dir.mkdir(parents=True, exist_ok=True)
        dest_file = dest_dir / config["filename"]

        if dest_file.exists() and not force:
            return {"status": "already_present", "path": str(dest_file)}

        if not config.get("auto_dl", False):
            return self._manual_instructions(model_id, config, dest_dir)

        # Lancer le téléchargement en background
        t = threading.Thread(
            target=self._download_worker,
            args=(model_id, config, dest_dir),
            daemon=True
        )
        self._active[model_id] = t
        t.start()
        return {
            "status":      "downloading",
            "model_id":    model_id,
            "name":        config["name"],
            "dest":        str(dest_file),
            "size_gb":     config.get("size_gb", 0),
        }

    def _download_worker(self, model_id: str,
                          config: dict, dest_dir: Path):
        """Thread de téléchargement."""
        name      = config["name"]
        filename  = config["filename"]
        dest_file = dest_dir / filename
        tmp_file  = dest_dir / f"{filename}.tmp"

        self.log.info(f"[DL] Début : {name}")
        self.progress_cb(model_id, 0.0, f"Démarrage : {name}")

        try:
            # Priorité 1 : HuggingFace Hub
            if config.get("hf_repo"):
                success = self._dl_huggingface(
                    model_id, config, dest_dir, tmp_file, dest_file
                )
                if success:
                    return

            # Priorité 2 : URL directe
            if config.get("direct_url"):
                success = self._dl_direct(
                    model_id, config["direct_url"],
                    tmp_file, dest_file, name
                )
                if success:
                    return

            # Échec
            self.log.error(f"[DL] Échec : {name}")
            self.progress_cb(model_id, -1.0, f"Échec — voir instructions manuelles")

        except Exception as e:
            self.log.error(f"[DL] Exception {name} : {e}")
            self.progress_cb(model_id, -1.0, str(e))
        finally:
            self._active.pop(model_id, None)
            if tmp_file.exists():
                tmp_file.unlink()

    def _dl_huggingface(self, model_id: str, config: dict,
                         dest_dir: Path, tmp_file: Path,
                         dest_file: Path) -> bool:
        """Téléchargement via HuggingFace Hub."""
        try:
            from huggingface_hub import hf_hub_download
            hf_file  = config.get("hf_file", config["filename"])
            hf_name  = config.get("hf_rename", hf_file)
            self.log.info(f"[DL/HF] {config['hf_repo']}/{hf_file}")
            self.progress_cb(model_id, 5.0, f"Connexion HuggingFace...")

            downloaded = hf_hub_download(
                repo_id   = config["hf_repo"],
                filename  = hf_file,
                local_dir = str(dest_dir),
            )
            # Renommer si nécessaire
            dl_path = Path(downloaded)
            final   = dest_dir / hf_name
            if dl_path != final and dl_path.exists():
                dl_path.rename(final)

            self.log.info(f"[DL/HF] ✓ {final}")
            self.progress_cb(model_id, 100.0, f"✓ Téléchargé : {hf_name}")
            return True

        except ImportError:
            self.log.warning("[DL/HF] pip install huggingface_hub")
            return False
        except Exception as e:
            self.log.warning(f"[DL/HF] {e}")
            return False

    def _dl_direct(self, model_id: str, url: str,
                    tmp_file: Path, dest_file: Path,
                    name: str) -> bool:
        """Téléchargement via URL directe avec barre de progression."""
        try:
            headers = {"User-Agent": "OverLord-Pipeline/1.40"}
            r = requests.get(url, stream=True, timeout=30, headers=headers)
            if r.status_code != 200:
                self.log.warning(f"[DL/URL] HTTP {r.status_code}")
                return False

            total = int(r.headers.get("content-length", 0))
            done  = 0
            self.progress_cb(model_id, 2.0, f"Téléchargement : {name}")

            with open(tmp_file, "wb") as f:
                for chunk in r.iter_content(chunk_size=1024*1024):  # 1 Mo
                    if chunk:
                        f.write(chunk)
                        done += len(chunk)
                        if total:
                            pct = done / total * 100
                            self.progress_cb(model_id, pct,
                                             f"{name} — {done//1e6:.0f}/{total//1e6:.0f} Mo")

            tmp_file.rename(dest_file)
            self.log.info(f"[DL/URL] ✓ {dest_file}")
            self.progress_cb(model_id, 100.0, f"✓ {name}")
            return True

        except Exception as e:
            self.log.error(f"[DL/URL] {e}")
            return False

    def _manual_instructions(self, model_id: str,
                              config: dict, dest_dir: Path) -> dict:
        """Génère les instructions manuelles pour les modèles qui nécessitent un login."""
        civitai_url = config.get("civitai_url","")
        hf_repo     = config.get("hf_repo","")

        msg = (
            f"\n{'═'*55}\n"
            f"  TÉLÉCHARGEMENT MANUEL REQUIS : {config['name']}\n"
            f"{'═'*55}\n"
            f"\n  Pourquoi manuel ?\n"
            f"  → Ce modèle nécessite un compte CivitAI (gratuit)\n"
            f"\n  ▶ ÉTAPE 1 : Télécharger\n"
        )
        if civitai_url:
            msg += f"  Lien : {civitai_url}\n"
            msg += f"  (Crée un compte gratuit sur civitai.com si pas encore fait)\n"
        if hf_repo:
            msg += f"  Alternative HF : https://huggingface.co/{hf_repo}\n"

        msg += (
            f"\n  ▶ ÉTAPE 2 : Placer dans le bon dossier\n"
            f"  Fichier   : {config['filename']}\n"
            f"  Dossier   : {dest_dir}\n"
            f"\n  ▶ ÉTAPE 3 : Vérifier dans OverLord\n"
            f"  Relancer : python AGENTS\\v140_model_downloader.py\n"
            f"{'═'*55}\n"
        )
        self.log.info(msg)
        return {
            "status":        "manual_required",
            "name":          config["name"],
            "filename":      config["filename"],
            "dest_folder":   str(dest_dir),
            "civitai_url":   civitai_url,
            "instructions":  msg,
        }

    def is_downloading(self, model_id: str) -> bool:
        t = self._active.get(model_id)
        return t is not None and t.is_alive()


# ══════════════════════════════════════════════════════════════════════
# AGENT PRINCIPAL
# ══════════════════════════════════════════════════════════════════════

class ModelDownloaderAgent:
    """
    Agent de gestion des modèles manquants.
    Détecte, télécharge automatiquement ou guide l'utilisateur.
    """

    def __init__(self, comfyui_root: str = "",
                 logger: logging.Logger = None):
        self.log        = logger or logging.getLogger("model_agent")
        self.scanner    = ModelScanner(comfyui_root, self.log)
        self.downloader = ModelDownloader(
            self.scanner,
            progress_cb=self._on_progress,
            logger=self.log
        )
        self._statuses:  dict[str, ModelStatus] = {}
        self._progress:  dict[str, float]        = {}

    def _on_progress(self, model_id: str, pct: float, msg: str):
        self._progress[model_id] = pct
        self.log.info(f"[DL/{model_id}] {pct:.0f}% — {msg}")

    def check_and_download_all(self,
                                auto_download: bool = True,
                                required_only: bool = False) -> dict:
        """
        Scan complet + téléchargement de tous les manquants.
        Retourne un rapport détaillé.
        """
        self.log.info("[AGENT] Scan des modèles...")
        self._statuses = self.scanner.scan()

        missing = {mid: s for mid, s in self._statuses.items()
                   if not s.present}

        if required_only:
            missing = {mid: s for mid, s in missing.items()
                       if MODEL_CATALOG[mid].get("required", False)}

        report = {
            "total":    len(self._statuses),
            "present":  sum(1 for s in self._statuses.values() if s.present),
            "missing":  len(missing),
            "auto_dl":  [],
            "manual":   [],
            "errors":   [],
        }

        for model_id, status in missing.items():
            config = MODEL_CATALOG[model_id]
            self.log.info(f"[AGENT] Manquant : {status.name}")

            if auto_download and config.get("auto_dl", False):
                result = self.downloader.download(model_id)
                if result.get("status") == "downloading":
                    report["auto_dl"].append({
                        "model_id": model_id,
                        "name":     status.name,
                        "size_gb":  config.get("size_gb",0),
                    })
                else:
                    report["errors"].append(result)
            else:
                result = self.downloader._manual_instructions(
                    model_id, config,
                    self.scanner.get_dest_path(model_id) or Path(".")
                )
                report["manual"].append({
                    "model_id":    model_id,
                    "name":        status.name,
                    "civitai_url": result.get("civitai_url",""),
                    "dest_folder": result.get("dest_folder",""),
                    "filename":    status.filename,
                    "instructions":result.get("instructions",""),
                })

        return report

    def get_status_report(self) -> str:
        """Rapport textuel de l'état des modèles."""
        if not self._statuses:
            self._statuses = self.scanner.scan()

        lines = [
            "═" * 60,
            "  ÉTAT DES MODÈLES COMFYUI — OverLord Pipeline",
            "═" * 60,
        ]
        for mid, status in self._statuses.items():
            icon   = "✅" if status.present else "❌"
            req    = " [REQUIS]" if MODEL_CATALOG[mid].get("required") else ""
            size   = f" ({status.file_size_gb:.1f}Go)" if status.present else f" ({MODEL_CATALOG[mid].get('size_gb',0):.1f}Go attendu)"
            lines.append(f"  {icon} {status.name}{req}{size}")
            if not status.present:
                config = MODEL_CATALOG[mid]
                if config.get("auto_dl"):
                    lines.append(f"      → Téléchargement automatique disponible")
                else:
                    lines.append(f"      → Manuel requis : {config.get('civitai_url','')}")
        lines.append("═" * 60)
        return "\n".join(lines)

    def interactive_setup(self):
        """Mode interactif en console pour guider l'utilisateur."""
        print(self.get_status_report())

        report = self.check_and_download_all(auto_download=False, required_only=False)

        if report["missing"] == 0:
            print("\n✅ Tous les modèles sont présents !")
            return

        print(f"\n{report['missing']} modèle(s) manquant(s) :")
        print(f"  • {len([m for m in MODEL_CATALOG.values() if m.get('auto_dl')])} peuvent être téléchargés automatiquement")
        print(f"  • {len([m for m in MODEL_CATALOG.values() if not m.get('auto_dl')])} nécessitent un téléchargement manuel\n")

        choice = input("Télécharger automatiquement les modèles disponibles ? [O/n] : ").strip().lower()
        if choice in ("", "o", "oui", "y", "yes"):
            print("\nLancement des téléchargements...")
            report = self.check_and_download_all(auto_download=True)
            print(f"\n✓ {len(report['auto_dl'])} téléchargement(s) lancé(s) en arrière-plan")

        if report.get("manual"):
            print(f"\n{'─'*55}")
            print(f"  {len(report['manual'])} modèle(s) à télécharger manuellement :")
            print(f"{'─'*55}")
            for m in report["manual"]:
                print(f"\n  📥 {m['name']}")
                print(f"     Lien    : {m['civitai_url']}")
                print(f"     Fichier : {m['filename']}")
                print(f"     Dossier : {m['dest_folder']}")


# ══════════════════════════════════════════════════════════════════════
# WIDGET TKINTER (intégrable dans le launcher)
# ══════════════════════════════════════════════════════════════════════

class ModelManagerWidget:
    """
    Widget tkinter pour gérer les modèles depuis le launcher.
    S'intègre dans l'onglet tutoriel ou en panneau dédié.
    """

    def __init__(self, parent, comfyui_root: str = ""):
        import tkinter as tk
        from tkinter import ttk

        self.agent  = ModelDownloaderAgent(comfyui_root)
        self._rows  = {}
        P = {
            "bg":"#050508","surf":"#0C0C18","surf2":"#141422",
            "ok":"#10B981","warn":"#F59E0B","err":"#EF4444",
            "text":"#E0E0F8","textd":"#6868A8","accent":"#7C3AED",
            "btn":"#7C3AED","btnfg":"#FFFFFF","logfg":"#98FFA8",
        }
        self.P     = P
        self.frame = tk.Frame(parent, bg=P["bg"])

        # Header
        hdr = tk.Frame(self.frame, bg=P["surf"], height=48)
        hdr.pack(fill="x")
        hdr.pack_propagate(False)
        tk.Label(hdr, text="  📦  Gestionnaire de Modèles ComfyUI",
                 font=("Segoe UI",11,"bold"),
                 bg=P["surf"], fg=P["accent"]).pack(side="left", fill="y", padx=8)
        tk.Button(hdr, text="🔍 Scanner + Télécharger",
                  bg=P["btn"], fg=P["btnfg"],
                  font=("Segoe UI",9,"bold"),
                  relief="flat", bd=0, cursor="hand2",
                  padx=10, pady=6,
                  command=self._run_scan).pack(side="right", padx=10)

        # Scroll area
        import tkinter as tk2
        canvas  = tk2.Canvas(self.frame, bg=P["bg"], highlightthickness=0)
        sb      = tk2.Scrollbar(self.frame, orient="vertical", command=canvas.yview)
        canvas.configure(yscrollcommand=sb.set)
        sb.pack(side="right", fill="y")
        canvas.pack(fill="both", expand=True)
        self._inner = tk2.Frame(canvas, bg=P["bg"])
        cw = canvas.create_window((0,0), window=self._inner, anchor="nw")
        self._inner.bind("<Configure>",
                          lambda e: canvas.configure(
                              scrollregion=canvas.bbox("all")))
        canvas.bind("<Configure>",
                     lambda e: canvas.itemconfig(cw, width=e.width))

        self._status_lbl = tk2.Label(
            self._inner,
            text="Clique sur 'Scanner + Télécharger' pour analyser les modèles",
            font=("Segoe UI",9), bg=P["bg"], fg=P["textd"]
        )
        self._status_lbl.pack(anchor="w", padx=16, pady=10)

    def pack(self, **kwargs):
        self.frame.pack(**kwargs)

    def _run_scan(self):
        import tkinter as tk
        self._status_lbl.configure(text="⏳ Scan en cours...", fg=self.P["warn"])
        for w in self._inner.winfo_children()[1:]:
            w.destroy()

        def _do():
            report = self.agent.check_and_download_all(auto_download=True)
            self.frame.after(0, lambda: self._show_results(report))

        threading.Thread(target=_do, daemon=True).start()

    def _show_results(self, report: dict):
        import tkinter as tk
        P = self.P
        self._status_lbl.configure(
            text=f"✓ {report['present']} présents | ⬇ {len(report['auto_dl'])} en dl | "
                 f"✋ {len(report['manual'])} manuels",
            fg=P["ok"]
        )

        for mid, status in self.agent._statuses.items():
            config = MODEL_CATALOG[mid]
            card   = tk.Frame(self._inner, bg=P["surf2"], padx=12, pady=8)
            card.pack(fill="x", padx=14, pady=2)

            hdr = tk.Frame(card, bg=P["surf2"])
            hdr.pack(fill="x")

            icon  = "✅" if status.present else ("⬇" if config.get("auto_dl") else "✋")
            color = P["ok"] if status.present else (P["warn"] if config.get("auto_dl") else P["err"])
            tk.Label(hdr, text=f"  {icon}  {status.name}",
                     font=("Segoe UI",9,"bold"),
                     bg=P["surf2"], fg=color).pack(side="left")

            if config.get("required") and not status.present:
                tk.Label(hdr, text=" REQUIS",
                         font=("Segoe UI",7,"bold"),
                         bg=P["err"], fg="white", padx=4).pack(side="left", padx=4)

            size_str = (f"{status.file_size_gb:.1f} Go"
                        if status.present
                        else f"~{config.get('size_gb',0):.1f} Go")
            tk.Label(hdr, text=size_str,
                     font=("Segoe UI",8), bg=P["surf2"],
                     fg=P["textd"]).pack(side="right")

            tk.Label(card, text=config.get("description",""),
                     font=("Segoe UI",8),
                     bg=P["surf2"], fg=P["textd"],
                     anchor="w").pack(fill="x")

            if not status.present and not config.get("auto_dl"):
                url = config.get("civitai_url","")
                if url:
                    tk.Button(card, text=f"🌐 Télécharger sur CivitAI",
                              font=("Segoe UI",8),
                              bg=P["surf2"], fg=P["accent"],
                              relief="flat", cursor="hand2",
                              command=lambda u=url: __import__("webbrowser").open(u)
                              ).pack(anchor="w", pady=(2,0))
                    tk.Label(card,
                             text=f"📁 Destination : {self.agent.scanner.get_dest_path(mid)}",
                             font=("Consolas",7),
                             bg=P["surf2"], fg=P["logfg"],
                             anchor="w").pack(fill="x")


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)

    print("=== V1.40 MODEL DOWNLOADER AGENT ===\n")
    agent = ModelDownloaderAgent()

    if agent.scanner.comfyui_root:
        agent.interactive_setup()
    else:
        print("ComfyUI non trouvé automatiquement.")
        path = input("Chemin vers ComfyUI (ex: D:\\ComfyUI_windows_portable) : ").strip()
        if path:
            agent = ModelDownloaderAgent(comfyui_root=path)
            agent.interactive_setup()
        else:
            print("Annulé.")

    print("\nUsage dans le code :")
    print("  from agents.v140_model_downloader import ModelDownloaderAgent")
    print("  agent = ModelDownloaderAgent('D:/ComfyUI_windows_portable')")
    print("  report = agent.check_and_download_all()")
    print("  print(agent.get_status_report())")

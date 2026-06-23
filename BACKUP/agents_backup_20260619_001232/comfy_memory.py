"""
agents/comfy_memory.py — Gestionnaire VRAM/RAM pour RTX 5080 + i7-8700K
Optimise l'utilisation des 16 Go VRAM et 64 Go RAM système.

Stratégies implémentées :
  - Model offloading automatique VRAM → RAM entre les générations
  - Détection OOM et retry avec offloading forcé
  - Arguments CLI ComfyUI optimaux pour cette config
  - Monitoring VRAM en temps réel
"""

import subprocess, json, logging, time, requests
from pathlib import Path

COMFY_URL = "http://127.0.0.1:8188"

# Arguments CLI recommandés pour RTX 5080 16Go + i7-8700K 64Go RAM
COMFY_ARGS_OPTIMAL = [
    "--disable-smart-memory",       # Laisse ComfyUI gérer manuellement (plus prévisible)
    "--lowvram",                    # Active le mode low VRAM (offload agressif)
    "--cpu-vae",                    # VAE sur CPU pour libérer VRAM pour l'UNet
    "--use-pytorch-cross-attention",# Plus stable que xformers sur RTX 50xx
    "--preview-method", "latent2rgb", # Preview légère sans decode complet
]

# Pour production max qualité (quand le pipeline tourne seul, pas d'UI ComfyUI)
COMFY_ARGS_PRODUCTION = [
    "--disable-smart-memory",
    "--normalvram",                 # 16Go : on peut se permettre normal
    "--use-pytorch-cross-attention",
    "--preview-method", "none",     # Pas de preview = +10% vitesse
    "--disable-auto-launch",        # Pas de navigateur
    "--port", "8188",
]


class VRAMManager:
    """
    Monitore et optimise l'utilisation VRAM pendant le pipeline.
    Compatible RTX 5080 (16 Go VRAM) + i7-8700K + 64 Go RAM.
    """

    def __init__(self, logger: logging.Logger = None):
        self.log = logger or logging.getLogger("vram")
        self._last_stats = {}

    def get_system_stats(self) -> dict:
        """Récupère les stats système depuis ComfyUI."""
        try:
            r = requests.get(f"{COMFY_URL}/system_stats", timeout=5)
            if r.status_code == 200:
                return r.json()
        except Exception:
            pass
        return {}

    def get_vram_usage(self) -> dict:
        """Retourne l'utilisation VRAM en Mo."""
        stats = self.get_system_stats()
        devices = stats.get("devices", [])
        if not devices:
            return {"used": 0, "total": 0, "free": 0, "pct": 0}

        dev   = devices[0]  # GPU principal
        total = dev.get("vram_total", 0)
        free  = dev.get("vram_free",  0)
        used  = total - free
        pct   = (used / total * 100) if total > 0 else 0

        return {
            "used_mb":  used,
            "total_mb": total,
            "free_mb":  free,
            "pct":      round(pct, 1),
            "device":   dev.get("name", "GPU"),
        }

    def log_vram(self):
        """Log l'état VRAM actuel."""
        v = self.get_vram_usage()
        if v["total_mb"] > 0:
            bar = "█" * int(v["pct"] / 5) + "░" * (20 - int(v["pct"] / 5))
            level = logging.WARNING if v["pct"] > 85 else logging.INFO
            self.log.log(level,
                f"[VRAM] {v['device']} | "
                f"{v['used_mb']/1024:.1f}/{v['total_mb']/1024:.1f} Go "
                f"[{bar}] {v['pct']}%"
            )
        return v

    def free_vram(self):
        """Force le déchargement des modèles de la VRAM via l'API ComfyUI."""
        try:
            # ComfyUI API : libérer la mémoire
            r = requests.post(f"{COMFY_URL}/free",
                              json={"unload_models": True, "free_memory": True},
                              timeout=10)
            if r.status_code == 200:
                self.log.info("[VRAM] Modèles déchargés de la VRAM → RAM ✓")
                time.sleep(1)
                return True
        except Exception as e:
            self.log.warning(f"[VRAM] Impossible de libérer : {e}")
        return False

    def check_oom_risk(self, threshold_pct: float = 90.0) -> bool:
        """Retourne True si risque d'OOM détecté."""
        v = self.get_vram_usage()
        if v["pct"] > threshold_pct:
            self.log.warning(
                f"[VRAM] ⚠ Risque OOM : {v['pct']}% utilisé "
                f"({v['used_mb']/1024:.1f} Go / {v['total_mb']/1024:.1f} Go)"
            )
            return True
        return False

    def pre_generation_check(self) -> bool:
        """
        Vérifie et prépare la VRAM avant une génération.
        Libère si nécessaire. Retourne False si OOM inévitable.
        """
        v = self.log_vram()
        if v.get("pct", 0) > 80:
            self.log.warning("[VRAM] Utilisation élevée — libération préventive...")
            self.free_vram()
            time.sleep(2)
            v = self.log_vram()
            if v.get("pct", 0) > 90:
                self.log.error("[VRAM] VRAM insuffisante même après libération")
                return False
        return True

    def handle_oom(self, retry_fn, max_retries: int = 2):
        """
        Wrapper pour gérer les OOM avec retry automatique.
        retry_fn : callable sans argument qui exécute la génération
        """
        for attempt in range(max_retries + 1):
            try:
                return retry_fn()
            except Exception as e:
                err = str(e).lower()
                if "out of memory" in err or "cuda" in err or "oom" in err:
                    self.log.error(
                        f"[VRAM] OOM détecté (tentative {attempt+1}/{max_retries+1})"
                    )
                    self.free_vram()
                    time.sleep(3)
                    if attempt == max_retries:
                        self.log.error("[VRAM] OOM irrécupérable après tous les retries")
                        raise
                else:
                    raise


def get_comfy_launch_command(comfy_path: str,
                              mode: str = "production") -> list:
    """
    Retourne la commande de lancement ComfyUI optimisée.

    mode : "production" (pipeline seul) | "dev" (avec interface)
    """
    python = str(Path(comfy_path) / "python_embeded" / "python.exe")
    main   = str(Path(comfy_path) / "ComfyUI" / "main.py")

    base = [python, "-s", main, "--windows-standalone-build"]

    if mode == "production":
        return base + COMFY_ARGS_PRODUCTION
    else:
        return base + COMFY_ARGS_OPTIMAL


def write_comfy_config(comfy_path: str):
    """
    Écrit un fichier de config ComfyUI optimisé pour RTX 5080 + 64Go RAM.
    """
    config = {
        "preview_method":        "latent2rgb",
        "use_split_cross_attention": False,
        "disable_smart_memory":  True,
        "default_vae_dtype":     "fp32",
        "attention_split_size":  512,
        # Offloading : décharge vers RAM quand modèle pas utilisé
        "auto_launch":           False,
    }
    cfg_path = Path(comfy_path) / "ComfyUI" / "user" / "default" / "comfy.settings.json"
    cfg_path.parent.mkdir(parents=True, exist_ok=True)

    try:
        existing = {}
        if cfg_path.exists():
            existing = json.loads(cfg_path.read_text(encoding="utf-8"))
        existing.update(config)
        cfg_path.write_text(json.dumps(existing, indent=2), encoding="utf-8")
        print(f"[VRAM] Config ComfyUI écrite : {cfg_path}")
        return True
    except Exception as e:
        print(f"[VRAM] Erreur écriture config : {e}")
        return False


# Paramètres recommandés pour les workflows avec RTX 5080
WORKFLOW_PARAMS_5080 = {
    "generation": {
        "steps":    28,
        "cfg":      6.0,
        "sampler":  "euler_ancestral",
        "scheduler":"normal",
        "width":    1024,
        "height":   1536,
        # FaceDetailer optimisé
        "face_denoise": 0.26,
        "face_steps":   14,
        "face_cfg":     6,
        # UltimateSDUpscale : tiles compatibles 16Go
        "tile_width":   512,
        "tile_height":  512,
        "overlap":      64,
    },
    "memory_notes": [
        "SDXL 1024x1536 : ~8-10 Go VRAM en pointe",
        "FaceDetailer : +2 Go supplémentaires",
        "UltimateSDUpscale : +3-4 Go (tiles 512x512)",
        "IPAdapter FaceID : +1.5 Go",
        "Total estimé pipeline complet : 14-15 Go / 16 Go disponibles",
        "Solution : --cpu-vae libère ~1.5 Go = pipeline dans les limites",
        "RAM 64 Go : largement suffisant pour le model offloading",
    ]
}

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    manager = VRAMManager()
    print("=== État VRAM actuel ===")
    v = manager.log_vram()
    print()
    print("=== Commande de lancement recommandée (production) ===")
    cmd = get_comfy_launch_command(
        r"D:\IA Local\ComfyUI Installation Local\ComfyUI_windows_portable",
        mode="production"
    )
    print(" ".join(cmd))
    print()
    print("=== Notes mémoire RTX 5080 ===")
    for note in WORKFLOW_PARAMS_5080["memory_notes"]:
        print(f"  • {note}")

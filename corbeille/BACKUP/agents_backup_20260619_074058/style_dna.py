"""
agents/style_dna.py — Style DNA Lock V1.44
Empreinte génétique visuelle d'une série.
Hash LoRA + palette + prompts → verrouillé dans ChromaDB.
Cohérence visuelle garantie sur 50+ épisodes.

Usage :
    from agents.style_dna import StyleDNA
    dna = StyleDNA("Dragon Ball OverLord")
    dna.lock(lora="dbz_xl_v2.safetensors", palette=["orange","blue","gold"],
             style_prompt="anime cel shading, dynamic action, Toriyama style")
    prompt = dna.apply_to_prompt("Goku fights in desert at sunset")
"""

import json
import hashlib
import logging
from pathlib import Path
from datetime import datetime

# ── Charte graphique Ov3rLoRd ─────────────────────────────────────────
try:
    import colorama; colorama.init()
    C_GREEN  = "\033[92m"
    C_YELLOW = "\033[93m"
    C_RED    = "\033[91m"
    C_CYAN   = "\033[96m"
    C_BLUE   = "\033[94m"
    C_MAGENTA= "\033[95m"
    C_BOLD   = "\033[1m"
    C_DIM    = "\033[2m"
    C_RESET  = "\033[0m"
except ImportError:
    C_GREEN=C_YELLOW=C_RED=C_CYAN=C_BLUE=C_MAGENTA=C_BOLD=C_DIM=C_RESET=""


log = logging.getLogger("style_dna")
DNA_DIR = Path("workspace/style_dna")


class StyleDNA:
    """
    Verrouille l'ADN visuel d'une série et l'applique à chaque génération.
    Une fois locké, tous les prompts héritent automatiquement du style.
    """

    def __init__(self, series_name: str, logger: logging.Logger = None):
        self.log      = logger or log
        self.series   = series_name
        self.dna_id   = hashlib.md5(series_name.encode()).hexdigest()[:8]
        self.dna_path = DNA_DIR / f"{self.dna_id}.json"
        DNA_DIR.mkdir(parents=True, exist_ok=True)
        self.dna = self._load()

    def _load(self) -> dict:
        if self.dna_path.exists():
            try:
                return json.loads(self.dna_path.read_text(encoding="utf-8"))
            except Exception:
                pass
        return {"series": self.series, "locked": False, "versions": []}

    def _save(self):
        self.dna_path.write_text(json.dumps(self.dna, ensure_ascii=False, indent=2), encoding="utf-8")

    def lock(self, lora: str = "", palette: list = None, style_prompt: str = "",
             negative_prompt: str = "", cfg_scale: float = 7.0,
             sampler: str = "DPM++ 2M Karras", steps: int = 25,
             width: int = 1024, height: int = 576,
             char_loras: dict = None) -> str:
        """
        Verrouille le style visuel de la série.
        Retourne le DNA hash unique.

        char_loras : {"Goku": "goku_lora_v1.safetensors", "Vegeta": "vegeta_v2.safetensors"}
        """
        dna_content = {
            "lora":            lora,
            "palette":         palette or [],
            "style_prompt":    style_prompt,
            "negative_prompt": negative_prompt or "bad quality, blurry, deformed, watermark, text, ugly",
            "cfg_scale":       cfg_scale,
            "sampler":         sampler,
            "steps":           steps,
            "width":           width,
            "height":          height,
            "char_loras":      char_loras or {},
        }

        dna_hash = hashlib.sha256(json.dumps(dna_content, sort_keys=True).encode()).hexdigest()[:16]

        version = {
            "hash":       dna_hash,
            "locked_at":  datetime.now().isoformat(),
            "content":    dna_content,
            "active":     True,
        }

        # Désactiver les versions précédentes
        for v in self.dna.get("versions", []):
            v["active"] = False

        self.dna["versions"].append(version)
        self.dna["locked"]      = True
        self.dna["active_hash"] = dna_hash
        self.dna["active_dna"]  = dna_content
        self._save()

        self.log.info(f"[DNA] ✓ Style verrouillé pour '{self.series}' — hash={dna_hash}")
        return dna_hash

    def apply_to_prompt(self, base_prompt: str, character: str = "") -> dict:
        """
        Injecte le style DNA dans un prompt ComfyUI.
        Retourne le dict complet prêt pour la génération.
        """
        if not self.dna.get("locked"):
            self.log.warning(f"[DNA] Style non verrouillé pour '{self.series}'")
            return {
                "positive": base_prompt,
                "negative": "bad quality, blurry, deformed",
                "lora": "", "cfg_scale": 7.0, "steps": 25,
                "width": 1024, "height": 576,
            }

        active = self.dna["active_dna"]
        palette_str = ", ".join(active.get("palette", []))

        # Construire le prompt enrichi
        parts = [base_prompt]
        if active.get("style_prompt"):
            parts.append(active["style_prompt"])
        if palette_str:
            parts.append(f"color palette: {palette_str}")

        positive = ", ".join(parts)

        # LoRA personnage spécifique
        char_lora = ""
        if character and character in active.get("char_loras", {}):
            char_lora = active["char_loras"][character]

        return {
            "positive":  positive,
            "negative":  active.get("negative_prompt", ""),
            "lora":      char_lora or active.get("lora", ""),
            "cfg_scale": active.get("cfg_scale", 7.0),
            "sampler":   active.get("sampler", "DPM++ 2M Karras"),
            "steps":     active.get("steps", 25),
            "width":     active.get("width", 1024),
            "height":    active.get("height", 576),
            "dna_hash":  self.dna.get("active_hash", ""),
        }

    def verify_consistency(self, job: dict) -> tuple:
        """
        Vérifie qu'un job de génération respecte le DNA verrouillé.
        Retourne (is_consistent: bool, warnings: list)
        """
        if not self.dna.get("locked"):
            return True, []

        active   = self.dna["active_dna"]
        warnings = []

        if active.get("lora") and active["lora"] not in job.get("lora",""):
            warnings.append(f"LoRA attendu '{active['lora']}' absent du job")

        for color in active.get("palette", []):
            if color.lower() not in job.get("positive","").lower():
                warnings.append(f"Couleur DNA manquante dans le prompt : {color}")

        if job.get("width") != active.get("width") or job.get("height") != active.get("height"):
            warnings.append(f"Résolution incohérente : {job.get('width')}x{job.get('height')} vs DNA {active.get('width')}x{active.get('height')}")

        return len(warnings) == 0, warnings

    def get_history(self) -> list:
        return self.dna.get("versions", [])

    def status(self) -> dict:
        return {
            "series":      self.series,
            "locked":      self.dna.get("locked", False),
            "active_hash": self.dna.get("active_hash", ""),
            "versions":    len(self.dna.get("versions", [])),
            "lora":        self.dna.get("active_dna", {}).get("lora", ""),
            "palette":     self.dna.get("active_dna", {}).get("palette", []),
        }


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    dna = StyleDNA("Dragon Ball OverLord")
    h = dna.lock(
        lora="dbz_overlord_xl_v1.safetensors",
        palette=["orange", "blue", "gold", "red"],
        style_prompt="anime cel shading, high detail, dynamic action poses, Akira Toriyama art style, vibrant colors",
        char_loras={"Goku": "goku_sdxl_v2.safetensors", "Vegeta": "vegeta_sdxl_v1.safetensors"},
        width=1024, height=576, steps=28, cfg_scale=7.5,
    )
    print(f"DNA verrouillé : {h}")
    job = dna.apply_to_prompt("Goku powers up against Broly in the desert at sunset", character="Goku")
    print(json.dumps(job, indent=2, ensure_ascii=False))
    ok, warns = dna.verify_consistency(job)
    print(f"Cohérence : {'✓' if ok else '✗'} | Warnings : {warns}")

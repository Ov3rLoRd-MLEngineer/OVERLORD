# ██████╗ ██╗   ██╗██████╗ ██████╗ ██╗      ██████╗ ██████╗ ██████╗
# ██╔═══██╗██║   ██║╚════██╗██╔══██╗██║     ██╔═══██╗██╔══██╗██╔══██╗
# ██║   ██║██║   ██║ █████╔╝██████╔╝██║     ██║   ██║██████╔╝██║  ██║
# ██║   ██║╚██╗ ██╔╝ ╚═══██╗██╔══██╗██║     ██║   ██║██╔══██╗██║  ██║
# ╚██████╔╝ ╚████╔╝ ██████╔╝██║  ██║███████╗╚██████╔╝██║  ██║██████╔╝
# ╚═════╝   ╚═══╝  ╚═════╝ ╚═╝  ╚═╝╚══════╝ ╚═════╝ ╚═╝  ╚═╝╚═════╝
# Ov3rLoRd -- pipeline de production anime autonome (ComfyUI)
# https://github.com/Ov3rLoRd-MLEngineer
#
r"""
╔══════════════════════════════════════════════════════════════════════╗
║         Ov3rLoRd — prompt_override.py  V1.0                         ║
║         Studio Ov3rLoRd                                   ║
║  Injecte des prompts manuels dans le pipeline                        ║
║  Supporte : 1 prompt global OU N prompts numerotes (image par image) ║
╚══════════════════════════════════════════════════════════════════════╝

Format du fichier prompt_override.txt :

  MODE GLOBAL (1 prompt pour toutes les images) :
    positive: asuka langley soryu, red plugsuit, running, dynamic motion
    negative: worst quality, low quality, extra limbs

  MODE PAR IMAGE (24 prompts pour 24 images) :
    001: asuka langley soryu, red plugsuit, starting run, wind in hair
    001_neg: worst quality, blurry
    002: asuka langley soryu, red plugsuit, stride wide, motion blur legs
    002_neg: worst quality, extra limbs
    ...

  MODE MIXTE (global + overrides specifiques) :
    positive: asuka langley soryu, red plugsuit, only 1girl
    negative: worst quality, low quality, extra limbs, background
    042: asuka mid-fall, dynamic pose, red plugsuit
    043: asuka catching fall, red plugsuit, hand on ground

Usage :
  py -3.12 agents\prompt_override.py --file prompt_override.txt --list
  py -3.12 agents\prompt_override.py --file prompt_override.txt --get 001
  py -3.12 agents\prompt_override.py --file prompt_override.txt --export prompts.json
"""

import os
import sys
import re
import json
import argparse
import logging
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))
import config

# ── Banniere ───────────────────────────────────────────────────────────────────
BANNER = r"""
╔══════════════════════════════════════════════════════╗
║   Ov3rLoRd — Prompt Override V1.0  ✍                ║
║   Controle total sur chaque image                    ║
╚══════════════════════════════════════════════════════╝
"""

PROJECT_ROOT   = config.OVERLORD_ROOT
DEFAULT_FILE   = PROJECT_ROOT / "prompt_override.txt"
DEFAULT_EXPORT = PROJECT_ROOT / "workspace" / "prompts_override.json"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
log = logging.getLogger("prompt_override")


# ══════════════════════════════════════════════════════════════════════════════
# Parser du fichier override
# ══════════════════════════════════════════════════════════════════════════════

class PromptOverride:
    """
    Lit et expose les prompts depuis un fichier texte structuré.
    Utilisable en import direct par agent_supervisor_v2.py et maestro.py.
    """

    def __init__(self, filepath: Path):
        self.filepath   = Path(filepath)
        self.global_pos = ""
        self.global_neg = ""
        self.per_image  = {}   # {"001": {"pos": "...", "neg": "..."}, ...}
        self._load()

    def _load(self) -> None:
        if not self.filepath.exists():
            log.warning(f"Fichier override introuvable : {self.filepath}")
            return

        with open(self.filepath, "r", encoding="utf-8") as fh:
            lines = fh.readlines()

        for raw in lines:
            line = raw.strip()
            if not line or line.startswith("#"):
                continue

            # Global positive
            m = re.match(r"^positive\s*:\s*(.+)$", line, re.IGNORECASE)
            if m:
                self.global_pos = m.group(1).strip()
                continue

            # Global negative
            m = re.match(r"^negative\s*:\s*(.+)$", line, re.IGNORECASE)
            if m:
                self.global_neg = m.group(1).strip()
                continue

            # Par image — negative  (ex: 001_neg: ...)
            m = re.match(r"^(\d{1,4})_neg\s*:\s*(.+)$", line, re.IGNORECASE)
            if m:
                idx = m.group(1).zfill(3)
                self.per_image.setdefault(idx, {"pos": "", "neg": ""})
                self.per_image[idx]["neg"] = m.group(2).strip()
                continue

            # Par image — positive  (ex: 001: ...)
            m = re.match(r"^(\d{1,4})\s*:\s*(.+)$", line)
            if m:
                idx = m.group(1).zfill(3)
                self.per_image.setdefault(idx, {"pos": "", "neg": ""})
                self.per_image[idx]["pos"] = m.group(2).strip()
                continue

        log.info(
            f"Override chargé : global={'oui' if self.global_pos else 'non'} "
            f"| {len(self.per_image)} prompts par image"
        )

    # ── API publique ───────────────────────────────────────────────────────────

    def get_positive(self, image_index: int) -> str:
        """
        Retourne le prompt positif pour l'image donnee.
        Priorite : per_image[idx] > global_pos > ""
        """
        idx = str(image_index).zfill(3)
        if idx in self.per_image and self.per_image[idx]["pos"]:
            return self.per_image[idx]["pos"]
        return self.global_pos

    def get_negative(self, image_index: int) -> str:
        """
        Retourne le prompt negatif pour l'image donnee.
        Priorite : per_image[idx] > global_neg > ""
        """
        idx = str(image_index).zfill(3)
        if idx in self.per_image and self.per_image[idx]["neg"]:
            return self.per_image[idx]["neg"]
        return self.global_neg

    def has_override(self, image_index: int) -> bool:
        """True si une entree specifique existe pour cette image."""
        return str(image_index).zfill(3) in self.per_image

    def is_active(self) -> bool:
        """True si le fichier existe et contient au moins un prompt."""
        return bool(self.global_pos or self.per_image)

    def export_json(self, output_path: Path) -> None:
        """Exporte tous les prompts resolus en JSON (utile pour debug)."""
        data = {
            "global": {
                "positive": self.global_pos,
                "negative": self.global_neg,
            },
            "per_image": self.per_image,
        }
        output_path.parent.mkdir(parents=True, exist_ok=True)
        with open(output_path, "w", encoding="utf-8") as fh:
            json.dump(data, fh, indent=2, ensure_ascii=False)
        log.info(f"Export JSON -> {output_path}")

    def summary(self) -> str:
        lines = [
            f"Fichier      : {self.filepath}",
            f"Global pos   : {self.global_pos[:80] + '...' if len(self.global_pos) > 80 else self.global_pos or '(vide)'}",
            f"Global neg   : {self.global_neg[:80] + '...' if len(self.global_neg) > 80 else self.global_neg or '(vide)'}",
            f"Par image    : {len(self.per_image)} entrees",
        ]
        if self.per_image:
            keys = sorted(self.per_image.keys())
            lines.append(f"Index couverts : {keys[0]} -> {keys[-1]}")
        return "\n".join(lines)


# ══════════════════════════════════════════════════════════════════════════════
# Exemple de fichier override (genere si absent)
# ══════════════════════════════════════════════════════════════════════════════

EXAMPLE_OVERRIDE = """\
# ============================================================
# Ov3rLoRd — prompt_override.txt
# ============================================================
# Lignes commencant par # = commentaires ignores
#
# FORMAT GLOBAL (s applique a toutes les images sauf override specifique) :
positive: asuka langley soryu, red plugsuit, only 1girl, dynamic pose, athletic, wind in hair, no background, white background, masterpiece, best quality
negative: worst quality, low quality, extra limbs, extra fingers, deformed, blurry, watermark, text, 2girls, male, nsfw
#
# FORMAT PAR IMAGE (override image par image) :
# 001: asuka langley soryu, red plugsuit, starting run, looking forward, determination
# 001_neg: worst quality, static pose
# 002: asuka langley soryu, red plugsuit, mid-stride, arms pumping, speed lines
# 002_neg: worst quality, standing still
# ...
"""


def generate_example(output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as fh:
        fh.write(EXAMPLE_OVERRIDE)
    log.info(f"Fichier exemple genere : {output_path}")


# ══════════════════════════════════════════════════════════════════════════════
# CLI
# ══════════════════════════════════════════════════════════════════════════════

def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description="Ov3rLoRd — Prompt Override Manager"
    )
    p.add_argument("--file",    default=str(DEFAULT_FILE), help="Fichier prompt_override.txt")
    p.add_argument("--list",    action="store_true",       help="Affiche le resume")
    p.add_argument("--get",     type=int, default=None,    help="Affiche les prompts pour l image N")
    p.add_argument("--export",  default=None,              help="Exporte en JSON vers ce chemin")
    p.add_argument("--example", action="store_true",       help="Genere un fichier exemple")
    return p


def main() -> int:
    print(BANNER)
    parser = build_parser()
    args   = parser.parse_args()

    if args.example:
        generate_example(Path(args.file))
        return 0

    override = PromptOverride(Path(args.file))

    if args.list:
        print("\n" + "=" * 60)
        print(override.summary())
        print("=" * 60 + "\n")

    if args.get is not None:
        idx = args.get
        print(f"\nImage {idx:04d} :")
        print(f"  POSITIVE : {override.get_positive(idx) or '(global)'}")
        print(f"  NEGATIVE : {override.get_negative(idx) or '(global)'}")
        print(f"  Override specifique : {'oui' if override.has_override(idx) else 'non (global)'}\n")

    if args.export:
        override.export_json(Path(args.export))

    if not any([args.list, args.get is not None, args.export, args.example]):
        parser.print_help()

    return 0


if __name__ == "__main__":
    sys.exit(main())

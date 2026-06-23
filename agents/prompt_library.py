"""
agents/prompt_library.py — Bibliothèque de prompts locaux V1.50
Charge tes prompts Booru personnels et les injecte comme jobs enrichis
dans le supervisor, sans dépendance externe.

Structure attendue :
  D:\\OVERLORD\\data\\prompts\\
  ├── prompts_local.json       ← prompts Booru personnels
  ├── character_library.json   ← personnages récurrents
  └── style_refs.json          ← références visuelles

Format prompts_local.json :
[
  {
    "id": "001",
    "positive": "masterpiece, best quality, absurdres, 1girl, ...",
    "negative": "bad quality, worst quality, ...",
    "lora": "asuka-langley-soryuu-classic-ponyxl-lora-nochekaiser.safetensors",
    "strength": 0.9,
    "width": 1024,
    "height": 1536,
    "tags": ["evangelion", "mecha", "action"],
    "source": "personal"
  }
]
"""

import json
import logging
import random
from pathlib import Path

try:
    from agents.context_bus import get_bus
    BUS_OK = True
except ImportError:
    BUS_OK = False

DATA_DIR         = Path("data/prompts")
PROMPTS_FILE     = DATA_DIR / "prompts_local.json"
CHARACTERS_FILE  = DATA_DIR / "character_library.json"
STYLE_REFS_FILE  = DATA_DIR / "style_refs.json"

DEFAULT_NEGATIVE = (
    "bad quality, worst quality, bad anatomy, deformed, blurry, "
    "extra limbs, bad hands, mutated hands, "
    "text, watermark, logo, censored, "
    "artist name, signature, patreon, twitter username"
)

AVAILABLE_LORAS = [
    "asuka-langley-soryuu-classic-ponyxl-lora-nochekaiser.safetensors",
    "mari-makinami-rebuild-ponyxl-lora-nochekaiser.safetensors",
    "rei-ayanami-classic-ponyxl-lora-nochekaiser.safetensors",
]


def _load_json(path: Path, logger=None) -> list | dict:
    log = logger or logging.getLogger("prompt_library")
    if not path.exists():
        log.warning(f"[PROMPT_LIB] Fichier absent : {path}")
        return []
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception as e:
        log.error(f"[PROMPT_LIB] Erreur lecture {path} : {e}")
        return []


def load_prompts(tags_filter: list = None,
                 logger: logging.Logger = None) -> list[dict]:
    """
    Charge prompts_local.json.
    Si tags_filter fourni, retourne seulement les prompts matchant au moins 1 tag.
    """
    log = logger or logging.getLogger("prompt_library")
    prompts = _load_json(PROMPTS_FILE, log)

    if not prompts:
        log.info("[PROMPT_LIB] Aucun prompt local — utilisation des defaults")
        return []

    if tags_filter:
        filtered = [
            p for p in prompts
            if any(t in p.get("tags", []) for t in tags_filter)
        ]
        log.info(f"[PROMPT_LIB] {len(filtered)}/{len(prompts)} prompts après filtre {tags_filter}")
        return filtered

    log.info(f"[PROMPT_LIB] {len(prompts)} prompts charges depuis {PROMPTS_FILE}")
    return prompts


def prompts_to_jobs(prompts: list[dict],
                    universe: str = "",
                    n_jobs: int = 8,
                    logger: logging.Logger = None) -> list[dict]:
    """
    Convertit les prompts locaux en jobs supervisor.
    Si moins de prompts que n_jobs, complète par tirage aléatoire.
    """
    log = logger or logging.getLogger("prompt_library")

    if not prompts:
        log.warning("[PROMPT_LIB] Aucun prompt — jobs vides (supervisor utilisera defaults)")
        return [{"positive": "", "negative": DEFAULT_NEGATIVE} for _ in range(n_jobs)]

    # Compléter si nécessaire
    pool = prompts.copy()
    while len(pool) < n_jobs:
        pool.append(random.choice(prompts))
    selected = random.sample(pool, n_jobs)

    jobs = []
    for p in selected:
        job = {
            "positive":    p.get("positive", ""),
            "negative":    p.get("negative", DEFAULT_NEGATIVE),
            "lora":        p.get("lora", random.choice(AVAILABLE_LORAS)),
            "strength":    p.get("strength", 1.0),
            "det_lora":    p.get("det_lora", random.choice(AVAILABLE_LORAS)),
            "det_strength":p.get("det_strength", 0.8),
            "width":       p.get("width", 1024),
            "height":      p.get("height", 1536),
            "seed":        p.get("seed", -1),
            "_source":     p.get("source", "local"),
            "_id":         p.get("id", "?"),
        }
        jobs.append(job)

    log.info(f"[PROMPT_LIB] {len(jobs)} jobs construits depuis prompts locaux")
    return jobs


def get_character(name: str, logger: logging.Logger = None) -> dict:
    """Retourne un personnage par nom depuis character_library.json."""
    log = logger or logging.getLogger("prompt_library")
    chars = _load_json(CHARACTERS_FILE, log)
    if isinstance(chars, list):
        for c in chars:
            if c.get("name", "").lower() == name.lower():
                return c
    return {}


def get_style_ref(style_name: str, logger: logging.Logger = None) -> dict:
    """Retourne une référence de style par nom depuis style_refs.json."""
    log = logger or logging.getLogger("prompt_library")
    styles = _load_json(STYLE_REFS_FILE, log)
    if isinstance(styles, list):
        for s in styles:
            if s.get("name", "").lower() == style_name.lower():
                return s
    return {}


def run_prompt_library(universe: str = "", n_jobs: int = 8,
                       tags_filter: list = None,
                       logger: logging.Logger = None) -> list[dict]:
    """
    Point d'entrée principal.
    Retourne n_jobs prêts pour agent_supervisor_v2.run_batch_advanced().
    """
    log = logger or logging.getLogger("prompt_library")
    log.info(f"[PROMPT_LIB] Chargement — univers={universe} | n_jobs={n_jobs}")

    # Filtre auto depuis l'univers si pas de filtre explicite
    if not tags_filter and universe:
        tags_filter = universe.lower().split()

    prompts = load_prompts(tags_filter=tags_filter, logger=log)
    jobs    = prompts_to_jobs(prompts, universe=universe, n_jobs=n_jobs, logger=log)

    if BUS_OK:
        try:
            get_bus().write("prompt_library.jobs_count", len(jobs), agent_id="prompt_library")
            get_bus().write("prompt_library.source",
                            "local" if prompts else "default",
                            agent_id="prompt_library")
        except Exception:
            pass

    return jobs


def init_data_structure():
    """Crée la structure data/prompts/ avec des fichiers exemples."""
    DATA_DIR.mkdir(parents=True, exist_ok=True)

    if not PROMPTS_FILE.exists():
        example = [
            {
                "id": "001",
                "positive": (
                    "masterpiece, best quality, absurdres, highly detailed, "
                    "1girl, solo, looking at viewer, anime style, "
                    "detailed face, expressive eyes, dynamic pose, "
                    "vibrant colors, sharp lineart, cinematic lighting, "
                    "evangelion plug suit, mecha background"
                ),
                "negative": DEFAULT_NEGATIVE,
                "lora": "asuka-langley-soryuu-classic-ponyxl-lora-nochekaiser.safetensors",
                "strength": 0.9,
                "width": 1024,
                "height": 1536,
                "tags": ["evangelion", "mecha", "action", "girl"],
                "source": "personal"
            },
            {
                "id": "002",
                "positive": (
                    "masterpiece, best quality, absurdres, "
                    "1girl, solo, portrait, close-up, "
                    "blue hair, red eyes, serious expression, "
                    "rei ayanami, evangelion, white plug suit, "
                    "sharp focus, anime style, detailed eyes"
                ),
                "negative": DEFAULT_NEGATIVE,
                "lora": "rei-ayanami-classic-ponyxl-lora-nochekaiser.safetensors",
                "strength": 0.85,
                "width": 1024,
                "height": 1536,
                "tags": ["evangelion", "rei", "portrait", "girl"],
                "source": "personal"
            },
        ]
        PROMPTS_FILE.write_text(
            json.dumps(example, indent=2, ensure_ascii=False), encoding="utf-8"
        )
        print(f"[INIT] Créé : {PROMPTS_FILE}")

    if not CHARACTERS_FILE.exists():
        example = [
            {
                "name": "Asuka Langley",
                "series": "Evangelion",
                "tags": "asuka langley, red hair, blue eyes, evangelion, plug suit, tsundere",
                "lora": "asuka-langley-soryuu-classic-ponyxl-lora-nochekaiser.safetensors",
                "lora_strength": 0.9
            },
            {
                "name": "Rei Ayanami",
                "series": "Evangelion",
                "tags": "rei ayanami, blue hair, red eyes, evangelion, white plug suit, quiet",
                "lora": "rei-ayanami-classic-ponyxl-lora-nochekaiser.safetensors",
                "lora_strength": 0.85
            },
        ]
        CHARACTERS_FILE.write_text(
            json.dumps(example, indent=2, ensure_ascii=False), encoding="utf-8"
        )
        print(f"[INIT] Créé : {CHARACTERS_FILE}")

    if not STYLE_REFS_FILE.exists():
        example = [
            {
                "name": "ponyxl_anime",
                "description": "PonyXL anime style — vibrant, sharp lineart, Booru tags",
                "base_tags": "masterpiece, best quality, absurdres, highly detailed, anime style",
                "negative_base": DEFAULT_NEGATIVE,
                "recommended_cfg": 6.0,
                "recommended_steps": 50,
                "sampler": "dpmpp_2m",
                "scheduler": "karras"
            }
        ]
        STYLE_REFS_FILE.write_text(
            json.dumps(example, indent=2, ensure_ascii=False), encoding="utf-8"
        )
        print(f"[INIT] Créé : {STYLE_REFS_FILE}")


if __name__ == "__main__":
    import sys, io
    if hasattr(sys.stdout, "buffer"):
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    logging.basicConfig(level=logging.INFO)

    print("=== Initialisation structure data/prompts/ ===")
    init_data_structure()

    print("\n=== Test chargement prompts ===")
    jobs = run_prompt_library(universe="evangelion mecha girl", n_jobs=4)
    for i, j in enumerate(jobs):
        print(f"Job {i+1}: lora={j.get('lora','?')[:30]}... | {j.get('positive','')[:60]}...")

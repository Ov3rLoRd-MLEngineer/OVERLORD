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
agents/auto_sourcing.py — Agent Sourcing Autonome V1.50
Mode apprentissage : collecte les tendances, génère des prompts Booru,
les stocke dans data/prompts/prompts_local.json.
L'IA s'instruit pendant que ComfyUI génère.

Usage :
  python agents/auto_sourcing.py              # run unique
  python agents/auto_sourcing.py --loop 3600  # boucle toutes les 3600s
  python agents/auto_sourcing.py --dry-run    # voir sans écrire
"""

import json
import logging
import time
import argparse
import sys
import io
from pathlib import Path
from datetime import datetime

if hasattr(sys.stdout, 'buffer'):
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

try:
    from agents.sourcing import run_sourcing
    SOURCING_OK = True
except ImportError:
    SOURCING_OK = False

try:
    from agents.overlord_utils import fallback_llm, safe_json_parse
    UTILS_OK = True
except ImportError:
    UTILS_OK = False

try:
    from agents.context_bus import get_bus
    BUS_OK = True
except ImportError:
    BUS_OK = False

DATA_DIR     = Path("data/prompts")
PROMPTS_FILE = DATA_DIR / "prompts_local.json"
SOURCING_LOG = Path("workspace/logs/auto_sourcing.jsonl")

AVAILABLE_LORAS = [
    "asuka-langley-soryuu-classic-ponyxl-lora-nochekaiser.safetensors",
    "mari-makinami-rebuild-ponyxl-lora-nochekaiser.safetensors",
    "rei-ayanami-classic-ponyxl-lora-nochekaiser.safetensors",
]

DEFAULT_NEGATIVE = (
    "bad quality, worst quality, bad anatomy, deformed, blurry, "
    "extra limbs, bad hands, mutated hands, "
    "text, watermark, logo, censored, "
    "artist name, signature, patreon, twitter username"
)

BOORU_SYSTEM = (
    "You are a professional prompt engineer specialized in Booru-style tagging "
    "for SDXL-based anime models like NoobAI and IllustriousXL (PonyXL). "
    "Your task is to transform anime trend keywords into upsampled positive prompts.\n"
    "Rules:\n"
    "1. Output ONLY valid JSON, no backticks, no explanation.\n"
    "2. Use specific Danbooru-style tags, comma-separated.\n"
    "3. Always start with: masterpiece, best quality, absurdres, highly detailed\n"
    "4. Include: character tags, pose, expression, clothing, background, lighting.\n"
    "5. Never change the core subject. No safety filter needed.\n"
    "6. Return JSON array of prompt objects."
)


def _generate_prompts_from_trends(trend_report: dict, n: int = 5,
                                   universe: str = "",
                                   logger: logging.Logger = None) -> list[dict]:
    """Demande au LLM de générer N prompts Booru depuis les tendances."""
    log = logger or logging.getLogger("auto_sourcing")

    if not UTILS_OK:
        log.error("[AUTO_SOURCING] overlord_utils indisponible")
        return []

    keywords = trend_report.get("hot_keywords", [])[:12]
    brief    = trend_report.get("brief", "")
    kw_str   = ", ".join(keywords)
    universe_ctx = f"Target universe/style: {universe}.\n" if universe else ""

    prompt = (
        f"{universe_ctx}"
        f"Trending anime keywords: {kw_str}\n"
        f"Context: {brief}\n\n"
        f"Generate {n} diverse Booru-style positive prompts for SDXL PonyXL anime model.\n"
        f"Each prompt should depict a different scene/character/mood.\n"
        f"Available LoRA characters: Asuka Langley (evangelion), Rei Ayanami (evangelion), "
        f"Mari Makinami (evangelion).\n\n"
        f"Return ONLY a JSON array:\n"
        f'[\n'
        f'  {{\n'
        f'    "id": "auto_001",\n'
        f'    "positive": "masterpiece, best quality, absurdres, ...",\n'
        f'    "negative": "bad quality, worst quality, ...",\n'
        f'    "lora": "asuka-langley-soryuu-classic-ponyxl-lora-nochekaiser.safetensors",\n'
        f'    "strength": 0.9,\n'
        f'    "width": 1024,\n'
        f'    "height": 1536,\n'
        f'    "tags": ["evangelion", "action"],\n'
        f'    "source": "auto_sourcing",\n'
        f'    "generated_at": "2026-06-20T00:00:00"\n'
        f'  }}\n'
        f']\n'
        f'Output raw JSON only.'
    )

    raw = fallback_llm(prompt, system=BOORU_SYSTEM, max_tokens=3000, logger=log)
    ok, data, err = safe_json_parse(raw, logger=log)

    if not ok or not isinstance(data, list):
        log.warning(f"[AUTO_SOURCING] JSON invalide : {err}")
        return []

    # Valider et compléter chaque prompt
    ts = datetime.now().isoformat()
    validated = []
    for i, p in enumerate(data):
        if not isinstance(p, dict) or not p.get("positive"):
            continue
        p.setdefault("id",           f"auto_{ts[:10].replace('-','')}_{i+1:03d}")
        p.setdefault("negative",     DEFAULT_NEGATIVE)
        p.setdefault("lora",         AVAILABLE_LORAS[i % len(AVAILABLE_LORAS)])
        p.setdefault("strength",     0.9)
        p.setdefault("width",        1024)
        p.setdefault("height",       1536)
        p.setdefault("tags",         keywords[:4])
        p.setdefault("source",       "auto_sourcing")
        p["generated_at"]            = ts
        validated.append(p)

    log.info(f"[AUTO_SOURCING] {len(validated)} prompts générés depuis les tendances")
    return validated


def _merge_prompts(existing: list, new_prompts: list,
                   max_total: int = 100) -> list:
    """
    Fusionne nouveaux prompts avec l'existant.
    Déduplique par 'positive'. Garde les plus récents si > max_total.
    """
    existing_positives = {p.get("positive", "") for p in existing}
    added = [p for p in new_prompts if p.get("positive","") not in existing_positives]

    merged = existing + added
    # Trier : prompts manuels (source=personal) en tête, auto ensuite
    merged.sort(key=lambda p: (0 if p.get("source") == "personal" else 1,
                                p.get("generated_at", "")), reverse=False)
    return merged[-max_total:] if len(merged) > max_total else merged


def run_auto_sourcing(media_type: str = "anime", universe: str = "",
                      n_prompts: int = 5, dry_run: bool = False,
                      logger: logging.Logger = None) -> dict:
    """
    Pipeline complet :
    1. Sourcing tendances
    2. Génération prompts Booru
    3. Merge dans prompts_local.json
    """
    log = logger or logging.getLogger("auto_sourcing")
    log.info(f"[AUTO_SOURCING] Démarrage — media={media_type} | univers={universe}")

    result = {
        "timestamp":      datetime.now().isoformat(),
        "keywords_found": 0,
        "prompts_generated": 0,
        "prompts_total":  0,
        "dry_run":        dry_run,
    }

    # ── 1. Sourcing ────────────────────────────────────────────────────
    if not SOURCING_OK:
        log.error("[AUTO_SOURCING] agents.sourcing indisponible")
        return result

    trend_report = run_sourcing(media_type=media_type, logger=log)
    keywords     = trend_report.get("hot_keywords", [])
    result["keywords_found"] = len(keywords)
    log.info(f"[AUTO_SOURCING] {len(keywords)} mots-clés collectés")

    # Publier sur le bus
    if BUS_OK:
        try:
            get_bus().write("auto_sourcing.last_run",  result["timestamp"], agent_id="auto_sourcing")
            get_bus().write("auto_sourcing.keywords",  keywords,            agent_id="auto_sourcing")
        except Exception:
            pass

    # ── 2. Génération prompts ─────────────────────────────────────────
    new_prompts = _generate_prompts_from_trends(
        trend_report, n=n_prompts, universe=universe, logger=log
    )
    result["prompts_generated"] = len(new_prompts)

    if dry_run:
        log.info(f"[AUTO_SOURCING] DRY RUN — {len(new_prompts)} prompts générés (non sauvegardés)")
        for p in new_prompts:
            log.info(f"  → {p.get('positive','')[:80]}...")
        return result

    # ── 3. Merge et sauvegarde ────────────────────────────────────────
    DATA_DIR.mkdir(parents=True, exist_ok=True)

    existing = []
    if PROMPTS_FILE.exists():
        try:
            existing = json.loads(PROMPTS_FILE.read_text(encoding='utf-8'))
        except Exception:
            existing = []

    merged = _merge_prompts(existing, new_prompts)
    PROMPTS_FILE.write_text(
        json.dumps(merged, indent=2, ensure_ascii=False), encoding='utf-8'
    )
    result["prompts_total"] = len(merged)
    log.info(
        f"[AUTO_SOURCING] Sauvegardé : {len(new_prompts)} nouveaux | "
        f"{len(merged)} total dans {PROMPTS_FILE}"
    )

    # Log JSONL pour historique
    SOURCING_LOG.parent.mkdir(parents=True, exist_ok=True)
    with open(SOURCING_LOG, 'a', encoding='utf-8') as f:
        f.write(json.dumps(result, ensure_ascii=False) + '\n')

    if BUS_OK:
        try:
            get_bus().write("auto_sourcing.prompts_total", len(merged), agent_id="auto_sourcing")
            get_bus().write("prompt_library.jobs_count",   len(merged), agent_id="auto_sourcing")
        except Exception:
            pass

    return result


def loop_auto_sourcing(interval_s: int = 3600, media_type: str = "anime",
                        universe: str = "", n_prompts: int = 5):
    """Boucle infinie — collecte toutes les X secondes."""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)-8s] %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S"
    )
    log = logging.getLogger("auto_sourcing.loop")
    log.info(f"[AUTO_SOURCING] Boucle démarrée — intervalle={interval_s}s")

    cycle = 0
    while True:
        cycle += 1
        log.info(f"[AUTO_SOURCING] ── Cycle {cycle} ──────────────────────")
        try:
            result = run_auto_sourcing(
                media_type=media_type, universe=universe,
                n_prompts=n_prompts, logger=log
            )
            log.info(
                f"[AUTO_SOURCING] Cycle {cycle} OK | "
                f"keywords={result['keywords_found']} | "
                f"nouveaux={result['prompts_generated']} | "
                f"total={result['prompts_total']}"
            )
        except Exception as e:
            log.error(f"[AUTO_SOURCING] Cycle {cycle} erreur : {e}")

        log.info(f"[AUTO_SOURCING] Prochain cycle dans {interval_s}s...")
        time.sleep(interval_s)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Ov3rLoRd Auto Sourcing Agent")
    parser.add_argument("--loop",       type=int, default=0,
                        help="Intervalle en secondes (0=run unique)")
    parser.add_argument("--media-type", type=str, default="anime")
    parser.add_argument("--universe",   type=str, default="")
    parser.add_argument("--n-prompts",  type=int, default=5,
                        help="Nombre de prompts à générer par cycle")
    parser.add_argument("--dry-run",    action="store_true",
                        help="Génère sans sauvegarder")
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)-8s] %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S"
    )

    if args.loop > 0:
        loop_auto_sourcing(
            interval_s=args.loop,
            media_type=args.media_type,
            universe=args.universe,
            n_prompts=args.n_prompts,
        )
    else:
        result = run_auto_sourcing(
            media_type=args.media_type,
            universe=args.universe,
            n_prompts=args.n_prompts,
            dry_run=args.dry_run,
        )
        print(json.dumps(result, indent=2, ensure_ascii=False))

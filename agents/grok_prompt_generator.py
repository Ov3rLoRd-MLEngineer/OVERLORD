r"""
Ov3rLoRd - grok_prompt_generator.py V1.0
Studio Ov3rLoRd

Agent de generation automatique de prompts via API xAI (Grok).
Remplace le workflow manuel : question Grok -> copier-coller -> fichier.

Usage :
  py -3.12 agents\grok_prompt_generator.py --shot 1 --character asuka
  py -3.12 agents\grok_prompt_generator.py --all
  py -3.12 agents\grok_prompt_generator.py --shot 1 --dry-run

Produit :
  prompt_override_shot{N}.txt  pret a etre consomme par prompt_override.py
"""

import os
import sys
import json
import time
import logging
import argparse
from pathlib import Path
from datetime import datetime

_REPO_ROOT = Path(__file__).resolve().parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))
import config

# ── Banniere ───────────────────────────────────────────────────────────────────
BANNER = r"""
╔══════════════════════════════════════════════════════════════╗
║   Ov3rLoRd — Grok Prompt Generator V1.0  🤖                 ║
║   xAI API -> prompts biomechaniques -> prompt_override.txt   ║
╚══════════════════════════════════════════════════════════════╝
"""

# ── Config ─────────────────────────────────────────────────────────────────────
PROJECT_ROOT = config.OVERLORD_ROOT
GROK_API_URL = "https://api.x.ai/v1/chat/completions"
GROK_MODEL   = "grok-3"

# Shots de la demo Asuka Run
SHOTS_CONFIG = {
    1: {
        "action": "depart course et acceleration depuis la ligne de depart jusqu'au plein sprint",
        "plan":   "plan large (wide shot), full body visible",
        "notes":  "progression : position accroupie -> explosion -> premieres foulee -> plein sprint",
    },
    2: {
        "action": "gros plan visage avec concentration montante, vitesse floue en arriere-plan",
        "plan":   "gros plan (close-up), visage uniquement, shallow depth of field",
        "notes":  "progression : calme -> tension -> concentration -> intensite maximale -> flow state",
    },
    3: {
        "action": "chute et contact avec le sol, pose dynamique basse",
        "plan":   "plan large (wide shot), full body, angle bas dramatique",
        "notes":  "progression : desequilibre -> chute -> impact -> roulade -> debut releve",
    },
    4: {
        "action": "rattrapage et rebond depuis le sol, instant suspendu puis reprise",
        "plan":   "plan large (wide shot), full body, angle cinematique",
        "notes":  "progression : suspension -> compression comme ressort -> explosion vers le haut -> reprise sprint",
    },
    5: {
        "action": "reprise course et acceleration finale, miroir du shot 1 mais plus puissant",
        "plan":   "plan large (wide shot), full body, composition miroir du shot 1",
        "notes":  "progression : premier foulee post-chute -> acceleration -> sprint transcendant le shot 1",
    },
}

# Prompt negatif standard (constant pour tous les shots)
NEGATIVE_PROMPT = (
    "multiple girls, 2girls, 3girls, other characters, background, scenery, "
    "landscape, city, crowd, audience, extra person, blurry background, "
    "bad anatomy, deformed, mutated, extra limbs, extra arms, extra legs, "
    "bad hands, malformed hands, fused fingers, too many fingers, missing fingers, "
    "ugly, disfigured, low quality, worst quality, lowres, blurry, out of focus, "
    "jpeg artifacts, grainy, wrong clothing, casual clothes, dress, skirt, jacket, "
    "non-canon outfit, text, watermark, signature, logo, extra hair, bad hair, "
    "extra twintails, poorly drawn face, bad eyes, heterochromia, nude, naked, "
    "nsfw, exposed skin, bad proportions, missing body parts, floating limbs, "
    "disconnected limbs, poorly drawn hands, cloned face, duplicate, error, cropped"
)

# Base character tags (constant)
BASE_CHAR = (
    "1girl, solo, asuka langley soryu, neon genesis evangelion, "
    "red hair, long twintails, blue eyes, red plugsuit, glossy bodysuit, "
    "tight clothing, shiny clothes, detailed face, beautiful detailed eyes, "
    "masterpiece, best quality, absurdres, very aesthetic, extremely detailed, "
    "sharp focus, asuka langley soryu only, respecting openpose controlnet reference pose"
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
log = logging.getLogger("grok_prompt_generator")


# ══════════════════════════════════════════════════════════════════════════════
# API Key
# ══════════════════════════════════════════════════════════════════════════════

def get_api_key() -> str:
    """
    Cherche la cle API xAI dans :
      1. Variable env XAI_API_KEY
      2. Fichier .env a la racine du projet
      3. Fichier .env dans le dossier courant
    """
    # Env direct
    key = os.environ.get("XAI_API_KEY", "")
    if key:
        return key

    # Fichiers .env
    for env_path in [PROJECT_ROOT / ".env", Path(".env")]:
        if env_path.exists():
            with open(env_path, encoding="utf-8") as fh:
                for line in fh:
                    line = line.strip()
                    if line.startswith("XAI_API_KEY"):
                        parts = line.split("=", 1)
                        if len(parts) == 2:
                            return parts[1].strip().strip('"').strip("'")

    return ""


# ══════════════════════════════════════════════════════════════════════════════
# Construction du prompt systeme Grok
# ══════════════════════════════════════════════════════════════════════════════

def build_system_prompt() -> str:
    return (
        "You are an expert anime production prompt engineer specialized in "
        "Booru-style tagging for SDXL-based models (NoobAI, IllustriousXL, PonyXL). "
        "You generate precise, biomechanically accurate prompt sequences for "
        "frame-by-frame animation. "
        "Your prompts are always in English, comma-separated tags, no sentences. "
        "You understand motion decomposition, athletic movement, and anime aesthetics. "
        "You always output ONLY the requested prompts, numbered, one per line. "
        "No explanations, no preamble, no markdown. Just the numbered prompts."
    )


def build_user_prompt(shot_num: int, character: str, frames: int = 12) -> str:
    cfg = SHOTS_CONFIG[shot_num]
    return (
        f"Generate exactly {frames} different positive prompts that precisely decompose, "
        f"one after the other, the following action for a {frames}-frame animation sequence.\n\n"
        f"CHARACTER: {character} in her classic red plugsuit\n"
        f"ACTION: {cfg['action']}\n"
        f"SHOT TYPE: {cfg['plan']}\n"
        f"PROGRESSION: {cfg['notes']}\n\n"
        f"RULES:\n"
        f"- Each prompt must describe ONE specific moment in the motion sequence\n"
        f"- Prompts must be in chronological order (frame 1 to {frames})\n"
        f"- Each prompt must be different from the others\n"
        f"- Use Booru-style comma-separated tags only\n"
        f"- Include motion-specific tags (motion blur, speed lines, dynamic pose, etc.)\n"
        f"- Keep the same camera angle throughout: {cfg['plan']}\n"
        f"- Do NOT include character identity tags (I will add them)\n"
        f"- Do NOT include quality tags (I will add them)\n\n"
        f"OUTPUT FORMAT (exactly {frames} lines):\n"
        f"1: [motion tags for frame 1]\n"
        f"2: [motion tags for frame 2]\n"
        f"...\n"
        f"{frames}: [motion tags for frame {frames}]"
    )


# ══════════════════════════════════════════════════════════════════════════════
# Appel API xAI
# ══════════════════════════════════════════════════════════════════════════════

def call_grok_api(system_prompt: str, user_prompt: str, api_key: str,
                  temperature: float = 0.7, max_tokens: int = 2000) -> str:
    """
    Appelle l'API xAI et retourne le texte de la reponse.
    Raise RuntimeError si echec.
    """
    import urllib.request
    import urllib.error

    payload = {
        "model":       GROK_MODEL,
        "temperature": temperature,
        "max_tokens":  max_tokens,
        "messages": [
            {"role": "system",  "content": system_prompt},
            {"role": "user",    "content": user_prompt},
        ],
    }

    data = json.dumps(payload).encode("utf-8")
    req  = urllib.request.Request(
        GROK_API_URL,
        data=data,
        headers={
            "Content-Type":  "application/json",
            "Authorization": f"Bearer {api_key}",
        },
        method="POST",
    )

    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            result = json.loads(resp.read())
            return result["choices"][0]["message"]["content"].strip()
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"HTTP {e.code}: {body}")
    except Exception as e:
        raise RuntimeError(f"API error: {e}")


# ══════════════════════════════════════════════════════════════════════════════
# Parsing de la reponse Grok
# ══════════════════════════════════════════════════════════════════════════════

def parse_grok_response(response: str, expected: int = 12) -> list:
    """
    Parse la reponse Grok numerotee en liste de strings.
    Robuste aux variations de format (1., 1:, 1 -, etc.)
    """
    import re
    lines  = response.strip().split("\n")
    phases = []

    for line in lines:
        line = line.strip()
        if not line:
            continue
        # Supprimer le numero de debut : "1:", "1.", "1 -", "1)"
        cleaned = re.sub(r"^\d+[\s]*[:.)\-]\s*", "", line).strip()
        if cleaned:
            phases.append(cleaned)

    if len(phases) < expected:
        log.warning(f"Grok a retourne {len(phases)} phases au lieu de {expected} — padding")
        while len(phases) < expected:
            phases.append(phases[-1] if phases else "dynamic pose, motion blur")

    return phases[:expected]


# ══════════════════════════════════════════════════════════════════════════════
# Generation du fichier prompt_override
# ══════════════════════════════════════════════════════════════════════════════

INTENSITY_DRIFT = [
    "",
    ", cinematic lighting",
    ", dramatic lighting, dynamic composition",
    ", epic cinematic shot, intense atmosphere",
    ", ultra dynamic, peak speed, epic wide",
    ", maximum intensity, climax, epic",
]


def generate_override_file(shot_num: int, phases: list,
                            output_path: Path, total_images: int = 144) -> Path:
    """
    Genere le fichier prompt_override_shotN.txt avec les phases Grok.
    144 images = 12 phases x 12 repetitions avec drift d'intensite.
    """
    lines = [
        "# ============================================================",
        f"# Ov3rLoRd — prompt_override_shot{shot_num}.txt",
        f"# {SHOTS_CONFIG[shot_num]['action'].title()}",
        f"# {total_images} images / 6 secondes / 24fps",
        f"# Genere par grok_prompt_generator.py V1.0 — {datetime.now().strftime('%Y-%m-%d %H:%M')}",
        "# Ov3rLoRd",
        "# ============================================================",
        "",
        f"negative: {NEGATIVE_PROMPT}",
        "",
    ]

    for img_idx in range(1, total_images + 1):
        phase_idx = (img_idx - 1) % len(phases)
        bloc_idx  = min((img_idx - 1) // len(phases), len(INTENSITY_DRIFT) - 1)
        drift     = INTENSITY_DRIFT[bloc_idx]
        prompt    = f"{BASE_CHAR}, {phases[phase_idx]}{drift}"
        lines.append(f"{img_idx:03d}: {prompt}")

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as fh:
        fh.write("\n".join(lines))

    log.info(f"Fichier genere : {output_path} ({total_images} prompts)")
    return output_path


# ══════════════════════════════════════════════════════════════════════════════
# Workflow complet pour un shot
# ══════════════════════════════════════════════════════════════════════════════

def process_shot(shot_num: int, character: str, api_key: str,
                 output_dir: Path, dry_run: bool = False,
                 phases_per_cycle: int = 12) -> Path:
    """
    Pipeline complet pour un shot :
      1. Construit le prompt Grok
      2. Appelle l'API (ou simule en dry-run)
      3. Parse la reponse
      4. Genere le fichier override
    """
    log.info(f"\n{'='*60}")
    log.info(f"  Shot {shot_num} — {SHOTS_CONFIG[shot_num]['action'][:50]}...")
    log.info(f"{'='*60}")

    system_prompt = build_system_prompt()
    user_prompt   = build_user_prompt(shot_num, character, phases_per_cycle)

    log.info(f"Prompt utilisateur :\n{user_prompt}\n")

    if dry_run:
        log.info("🔵  [DRY-RUN] Simulation sans appel API")
        phases = [
            f"DRY_RUN_phase_{i+1}, dynamic pose, motion blur, wide shot, full body"
            for i in range(phases_per_cycle)
        ]
    else:
        log.info(f"Appel API xAI ({GROK_MODEL})...")
        t0       = time.time()
        response = call_grok_api(system_prompt, user_prompt, api_key)
        elapsed  = time.time() - t0
        log.info(f"Reponse recue en {elapsed:.1f}s")
        log.debug(f"Reponse brute :\n{response}")
        phases = parse_grok_response(response, phases_per_cycle)

    log.info(f"{len(phases)} phases parsees")
    for i, p in enumerate(phases, 1):
        log.info(f"  Phase {i:02d}: {p[:80]}")

    output_path = output_dir / f"prompt_override_shot{shot_num}.txt"
    generate_override_file(shot_num, phases, output_path)

    return output_path


# ══════════════════════════════════════════════════════════════════════════════
# CLI
# ══════════════════════════════════════════════════════════════════════════════

def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description="Ov3rLoRd — Grok Prompt Generator"
    )
    p.add_argument("--shot",       type=int, default=None,
                   choices=[1, 2, 3, 4, 5],
                   help="Numero du shot a generer (1-5)")
    p.add_argument("--all",        action="store_true",
                   help="Generer tous les 5 shots")
    p.add_argument("--character",  type=str, default="asuka langley soryu",
                   help="Nom du personnage")
    p.add_argument("--phases",     type=int, default=12,
                   help="Nombre de phases par cycle (defaut: 12)")
    p.add_argument("--images",     type=int, default=144,
                   help="Nombre total d'images par shot (defaut: 144)")
    p.add_argument("--output-dir", type=str, default=str(PROJECT_ROOT),
                   help="Dossier de sortie des fichiers override")
    p.add_argument("--dry-run",    action="store_true",
                   help="Simulation sans appel API")
    p.add_argument("--api-key",    type=str, default=None,
                   help="Cle API xAI (sinon lu depuis XAI_API_KEY ou .env)")
    p.add_argument("--delay",      type=float, default=2.0,
                   help="Delai entre les appels API en secondes (defaut: 2.0)")
    return p


def main() -> int:
    print(BANNER)
    parser = build_parser()
    args   = parser.parse_args()

    if not args.shot and not args.all:
        parser.print_help()
        return 1

    # Resolution API key
    api_key = args.api_key or get_api_key()
    if not api_key and not args.dry_run:
        log.error(
            "Cle API xAI introuvable.\n"
            "Solutions :\n"
            "  1. Ajouter XAI_API_KEY=sk-... dans D:\\OVERLORD\\.env\n"
            "  2. Passer --api-key sk-...\n"
            "  3. Utiliser --dry-run pour tester sans API"
        )
        return 1

    output_dir = Path(args.output_dir)
    shots      = [1, 2, 3, 4, 5] if args.all else [args.shot]
    generated  = []

    for i, shot_num in enumerate(shots):
        try:
            path = process_shot(
                shot_num    = shot_num,
                character   = args.character,
                api_key     = api_key,
                output_dir  = output_dir,
                dry_run     = args.dry_run,
                phases_per_cycle = args.phases,
            )
            generated.append(path)

            # Delai entre appels pour eviter rate limiting
            if not args.dry_run and i < len(shots) - 1:
                log.info(f"Pause {args.delay}s avant prochain shot...")
                time.sleep(args.delay)

        except Exception as e:
            log.error(f"Shot {shot_num} echec : {e}")
            if not args.all:
                return 1

    # Resume
    print("\n" + "=" * 62)
    print(f"  GENERATION TERMINEE")
    print(f"  {len(generated)}/{len(shots)} shots generes")
    for p in generated:
        print(f"  -> {p}")
    print("=" * 62 + "\n")

    if generated and not args.dry_run:
        print("ETAPE SUIVANTE :")
        print(f"  copy {generated[0].name} prompt_override.txt")
        print(f"  run.bat --media-type anime --universe \"evangelion asuka running\" ^")
        print(f"          --scene-type action_dynamic ^")
        print(f"          --pose \"workspace\\poses\\asuka_skeleton.png\"")

    return 0


if __name__ == "__main__":
    sys.exit(main())

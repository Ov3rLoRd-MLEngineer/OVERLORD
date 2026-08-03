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
agents/prompt_engineer.py — Agent Prompt Engineer V1.60
Upsampling Booru-style des prompts storyboard avant envoi à ComfyUI.
Utilise fallback_llm (Ollama/Grok/Claude) selon config .env.
Injecté comme bloc entre storyboard et production dans maestro.py.
"""

import logging
import re
import random
from pathlib import Path

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

AVAILABLE_LORAS = [
    "asuka-langley-soryuu-classic-ponyxl-lora-nochekaiser.safetensors",
    "mari-makinami-rebuild-ponyxl-lora-nochekaiser.safetensors",
    "rei-ayanami-classic-ponyxl-lora-nochekaiser.safetensors",
]

LORA_CHARACTER_TAGS = {
    "asuka-langley-soryuu-classic-ponyxl-lora-nochekaiser.safetensors": [
        "asuka langley", "asuka", "red hair", "blue eyes", "evangelion",
        "plug suit", "red plug suit", "tsundere", "aggressive", "pilot",
    ],
    "rei-ayanami-classic-ponyxl-lora-nochekaiser.safetensors": [
        "rei ayanami", "rei", "blue hair", "red eyes", "evangelion",
        "white plug suit", "quiet", "pale skin", "short hair", "stoic",
    ],
    "mari-makinami-rebuild-ponyxl-lora-nochekaiser.safetensors": [
        "mari makinami", "mari", "brown hair", "green eyes", "evangelion",
        "plug suit", "glasses", "cheerful", "energetic", "playful",
    ],
}

BOORU_SYSTEM = (
    "You are a professional prompt engineer specialized in Booru-style tagging "
    "for SDXL-based anime models (PonyXL/NoobAI/IllustriousXL).\n"
    "## Role\n"
    "Transform a simple scene description into a single upsampled positive prompt.\n"
    "## Output Format (Strict)\n"
    "1. Start with quality tokens: masterpiece, best quality, absurdres, highly detailed\n"
    "2. Add 15-40 specific Danbooru-style tags, comma-separated\n"
    "Your response must contain ONLY the upsampled prompt string. "
    "No headers, no explanation, no backticks, no markdown. "
    "Just the comma-separated tag string.\n"
    "## Logic\n"
    "- Add details: eyes, hair, skin, clothing, pose, expression, background, lighting\n"
    "- Action scenes: add dynamic pose, motion blur, speed lines, intense expression\n"
    "- Emotional scenes: add matching facial expression, color palette, lighting mood\n"
    "- Never change the core subject. No safety filter applied."
)

DEFAULT_NEGATIVE = (
    "bad quality, worst quality, bad anatomy, deformed, blurry, "
    "extra limbs, bad hands, mutated hands, fused fingers, "
    "text, watermark, logo, censored, "
    "artist name, signature, patreon, twitter username, "
    "low resolution, pixelated, jpeg artifacts"
)


def select_lora(positive: str) -> str:
    """Sélectionne la LoRa la plus adaptée selon les tags du prompt."""
    pos_lower = positive.lower()
    scores = {lora: sum(1 for tag in tags if tag in pos_lower)
              for lora, tags in LORA_CHARACTER_TAGS.items()}
    best_lora = max(scores, key=scores.get)
    return best_lora if scores[best_lora] > 0 else random.choice(AVAILABLE_LORAS)


def _manual_enrich(description: str, shot_meta: dict = None) -> str:
    """Enrichissement sans LLM — prompt minimal garanti."""
    base = f"masterpiece, best quality, absurdres, highly detailed, {description}"
    if shot_meta:
        emotion    = shot_meta.get("emotion", "").lower()
        shot_type  = shot_meta.get("shot_type", "").lower()
        if "action" in emotion or "fight" in emotion or "battle" in emotion:
            base += ", dynamic pose, action shot, speed lines, intense expression, dramatic lighting"
        elif "sad" in emotion or "melancholy" in emotion:
            base += ", sad expression, soft lighting, melancholic mood, muted colors"
        elif "happy" in emotion or "joy" in emotion:
            base += ", smile, bright lighting, warm colors, cheerful expression"
        if "close" in shot_type:
            base += ", close-up, detailed face, sharp focus, depth of field"
        elif "wide" in shot_type:
            base += ", wide shot, establishing shot, full body, scenic background"
        elif "medium" in shot_type:
            base += ", medium shot, upper body, character focus"
    base += ", anime style, vibrant colors, sharp lineart, cinematic lighting"
    return base


def upsample_prompt(description: str, shot_meta: dict = None,
                    logger: logging.Logger = None) -> str:
    """Upsampling d'une description de scène en prompt Booru complet."""
    log = logger or logging.getLogger("prompt_engineer")

    if not UTILS_OK or not description or len(description) < 5:
        return _manual_enrich(description or "anime scene", shot_meta)

    meta_ctx = ""
    if shot_meta:
        if shot_meta.get("emotion"):
            meta_ctx += f"Emotion/mood: {shot_meta['emotion']}. "
        if shot_meta.get("shot_type"):
            meta_ctx += f"Shot type: {shot_meta['shot_type']}. "
        if shot_meta.get("characters"):
            meta_ctx += f"Characters: {shot_meta['characters']}. "

    user_prompt = (
        f"Scene: {description}\n"
        f"{meta_ctx}"
        "Output ONLY the upsampled Booru tag string."
    )

    raw = fallback_llm(user_prompt, system=BOORU_SYSTEM, max_tokens=400, logger=log)
    cleaned = re.sub(r'```[a-z]*\n?', '', raw.strip()).strip().rstrip('`').strip()

    if len(cleaned) < 20:
        log.warning("[PROMPT_ENG] Réponse LLM trop courte — fallback manuel")
        return _manual_enrich(description, shot_meta)

    if "masterpiece" not in cleaned:
        cleaned = "masterpiece, best quality, absurdres, highly detailed, " + cleaned

    return cleaned


def engineer_jobs(jobs: list, script: dict = None,
                  logger: logging.Logger = None) -> list:
    """
    Enrichit chaque job avec un prompt Booru upsamplé + LoRa intelligente.
    Retourne la liste enrichie prête pour agent_supervisor_v2.
    """
    log = logger or logging.getLogger("prompt_engineer")
    log.info(f"[PROMPT_ENG] Upsampling {len(jobs)} jobs...")

    enriched = []
    for i, job in enumerate(jobs):
        j = job.copy()
        shot_meta   = j.get("_shot_meta", {})
        description = (
            shot_meta.get("description") or
            shot_meta.get("visual_notes") or
            j.get("positive", "") or
            f"anime scene {i+1}, dynamic composition, evangelion style"
        )

        upsampled = upsample_prompt(description, shot_meta=shot_meta, logger=log)
        j["positive"] = upsampled

        if not j.get("lora"):
            j["lora"] = select_lora(upsampled)

        j.setdefault("negative",    DEFAULT_NEGATIVE)
        j.setdefault("width",       1024)
        j.setdefault("height",      1536)
        j.setdefault("strength",    0.9)

        log.info(f"[PROMPT_ENG] Job {i+1}/{len(jobs)} | lora={j['lora'][:35]}...")
        enriched.append(j)

    if BUS_OK:
        try:
            get_bus().write("prompt_engineer.jobs_enriched", len(enriched),
                            agent_id="prompt_engineer")
        except Exception:
            pass

    log.info(f"[PROMPT_ENG] OK — {len(enriched)} jobs enrichis")
    return enriched


if __name__ == "__main__":
    import sys, io
    if hasattr(sys.stdout, "buffer"):
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    logging.basicConfig(level=logging.INFO)
    test = [{"positive": "", "_shot_meta": {"description": "Asuka in red plug suit, cockpit, battle", "shot_type": "close-up", "emotion": "intense, determined"}}]
    result = engineer_jobs(test)
    for j in result:
        print(f"LoRa: {j['lora'][:50]}")
        print(f"Prompt: {j['positive'][:120]}")

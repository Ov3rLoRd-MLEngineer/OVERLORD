"""
agents/grok_client.py — Grok 4 Fast API client V1.50
Fallback LLM via xAI API ($0.20/M input, $0.50/M output).
$175/mois gratuits via data-sharing program : https://console.x.ai
Activé via .env : OV_LLM_MODE=grok ou OV_LLM_MODE=auto
"""

import os
import json
import logging
import requests
from pathlib import Path

GROK_API_URL  = "https://api.x.ai/v1/chat/completions"
GROK_MODEL    = "grok-4-fast"
GROK_TIMEOUT  = 60
MAX_TOKENS    = 4000

def _get_grok_key() -> str:
    key = os.getenv("GROK_API_KEY", "")
    if not key:
        env_path = Path(".env")
        if env_path.exists():
            for line in env_path.read_text(encoding="utf-8").splitlines():
                if line.startswith("GROK_API_KEY="):
                    key = line.split("=", 1)[1].strip()
                    break
    return key


def grok_llm(prompt: str, system: str = "",
             max_tokens: int = MAX_TOKENS,
             logger: logging.Logger = None) -> str:
    """Appel Grok 4 Fast — retourne le texte brut ou '' si erreur."""
    log = logger or logging.getLogger("grok_client")

    api_key = _get_grok_key()
    if not api_key:
        log.warning("[GROK] GROK_API_KEY absent dans .env — fallback Ollama")
        return ""

    messages = []
    if system:
        messages.append({"role": "system", "content": system})
    messages.append({"role": "user", "content": prompt})

    try:
        resp = requests.post(
            GROK_API_URL,
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type":  "application/json",
            },
            json={
                "model":      GROK_MODEL,
                "messages":   messages,
                "max_tokens": max_tokens,
            },
            timeout=GROK_TIMEOUT,
        )
        if resp.status_code == 200:
            data = resp.json()
            text = data["choices"][0]["message"]["content"]
            usage = data.get("usage", {})
            log.debug(
                f"[GROK] OK | "
                f"in={usage.get('prompt_tokens',0)} "
                f"out={usage.get('completion_tokens',0)} tokens"
            )
            return text
        log.error(f"[GROK] HTTP {resp.status_code} : {resp.text[:300]}")
        return ""
    except requests.Timeout:
        log.error(f"[GROK] Timeout ({GROK_TIMEOUT}s)")
        return ""
    except Exception as e:
        log.error(f"[GROK] Exception : {e}")
        return ""


def grok_available() -> bool:
    """Vérifie si Grok est configuré et joignable."""
    return bool(_get_grok_key())


if __name__ == "__main__":
    import sys, io
    if hasattr(sys.stdout, "buffer"):
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    logging.basicConfig(level=logging.INFO)

    if not grok_available():
        print("GROK_API_KEY manquant dans .env")
        print("Ajouter : GROK_API_KEY=xai-VOTRE_CLE")
        print("Obtenir $175 gratuits : https://console.x.ai")
    else:
        result = grok_llm(
            prompt='Write a 3-sentence anime synopsis about a mecha pilot girl. Reply ONLY with JSON: {"title": "...", "synopsis": "..."}',
            system="You are a professional anime screenwriter. Reply ONLY with valid JSON.",
        )
        print("Réponse Grok :", result[:200])

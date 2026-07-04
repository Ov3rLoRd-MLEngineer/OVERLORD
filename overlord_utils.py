"""
overlord_utils.py — Utilitaires LLM centralisés Ov3rLoRd V1.70
Fournit fallback_llm() et safe_json_parse() pour tous les agents.
Tente Ollama en premier, puis API Anthropic en fallback.
"""
import sys
import io
import os
import json
import logging
import re
from pathlib import Path

# Fix UTF-8
if hasattr(sys.stdout, 'buffer') and getattr(sys.stdout, 'encoding', '').lower() != 'utf-8':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
if hasattr(sys.stderr, 'buffer') and getattr(sys.stderr, 'encoding', '').lower() != 'utf-8':
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')
os.environ.setdefault("PYTHONIOENCODING", "utf-8")
os.environ.setdefault("PYTHONUTF8", "1")

OLLAMA_URL  = os.environ.get("OLLAMA_URL",  "http://127.0.0.1:11434")
OLLAMA_MODEL = os.environ.get("OLLAMA_MODEL", "mistral")
# Séquence de modèles Ollama essayés dans l'ordre par fallback_llm()
# (serveur Ollama sur RTX 2070 via launch_ollama.bat CUDA_VISIBLE_DEVICES=1)
OLLAMA_MODELS = ["mistral", "qwen2.5:7b", "deepseek-r1:7b"]
OLLAMA_TIMEOUT_S = 30   # timeout PAR modèle de la séquence
ANTHROPIC_KEY = os.environ.get("ANTHROPIC_API_KEY", "")

_log = logging.getLogger("overlord_utils")

_LLM_ENDPOINTS_CACHE = None


def _load_llm_endpoints_config() -> dict:
    """Charge config/llm_endpoints.json (source externe de config LLM :
    endpoints Ollama / GLM-5.2 (Z.ai) etc.). Cherché en remontant depuis ce
    fichier vers la racine du repo. Retourne {} si absent ou invalide
    (fallback_llm() continue alors avec les constantes par défaut)."""
    global _LLM_ENDPOINTS_CACHE
    if _LLM_ENDPOINTS_CACHE is not None:
        return _LLM_ENDPOINTS_CACHE
    _LLM_ENDPOINTS_CACHE = {}
    p = Path(__file__).resolve()
    for _ in range(4):
        p = p.parent
        cfg_path = p / "config" / "llm_endpoints.json"
        if cfg_path.exists():
            try:
                _LLM_ENDPOINTS_CACHE = json.loads(cfg_path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError) as e:
                _log.warning(f"[LLM] config/llm_endpoints.json invalide : {e}")
            break
    return _LLM_ENDPOINTS_CACHE


def _get_api_key() -> str:
    """Récupère la clé API Anthropic depuis .env ou l'environnement."""
    key = os.environ.get("ANTHROPIC_API_KEY", "")
    if not key:
        env_path = os.path.join(os.path.dirname(__file__), ".env")
        if os.path.exists(env_path):
            with open(env_path, encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if line.startswith("ANTHROPIC_API_KEY="):
                        key = line.split("=", 1)[1].strip().strip('"').strip("'")
                        break
    return key


def _strip_think(text: str) -> str:
    """Retire les blocs <think>...</think> (deepseek-r1) de la réponse —
    sinon ils polluent safe_json_parse() et les prompts en aval."""
    if text and "<think>" in text:
        text = re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL)
    return text.strip() if text else ""


def fallback_llm(
    prompt: str,
    system: str = "",
    model: str = None,
    max_tokens: int = 1500,
    logger=None,
    timeout: int = OLLAMA_TIMEOUT_S,
) -> str:
    """
    Appelle un LLM avec fallback automatique :
    1. Ollama : mistral → qwen2.5:7b → deepseek-r1:7b en séquence,
       `timeout` secondes PAR modèle (défaut 30s)
    2. API Anthropic (claude-sonnet-4-6)
    3. Chaîne vide si tout échoue

    Args:
        prompt    : prompt utilisateur
        system    : prompt système optionnel
        model     : forcer un modèle Ollama spécifique (essayé en premier,
                    la séquence par défaut reste en secours)
        max_tokens: limite de tokens
        logger    : logger optionnel
        timeout   : timeout en secondes PAR modèle Ollama

    Returns:
        str : réponse du LLM ou "" en cas d'échec
    """
    log = logger or _log
    _cfg = _load_llm_endpoints_config()

    messages = []
    if system:
        messages.append({"role": "system", "content": system})
    messages.append({"role": "user", "content": prompt})

    # ── Tentative 1 : séquence Ollama (30s par modèle) ────────────────
    _ollama_cfg = _cfg.get("ollama", {})
    ollama_url = _ollama_cfg.get("url", OLLAMA_URL) if _ollama_cfg.get("enabled", True) else OLLAMA_URL
    ollama_models = _ollama_cfg.get("models") or OLLAMA_MODELS

    sequence = []
    if model:
        sequence.append(model)
    for m in [OLLAMA_MODEL] + ollama_models:
        if m and m not in sequence:
            sequence.append(m)

    try:
        import requests

        for _model in sequence:
            try:
                resp = requests.post(
                    f"{ollama_url}/api/chat",
                    json={
                        "model":    _model,
                        "messages": messages,
                        "stream":   False,
                        "options":  {"num_predict": max_tokens},
                    },
                    timeout=timeout,
                )
                if resp.status_code == 200:
                    data = resp.json()
                    text = _strip_think(
                        data.get("message", {}).get("content", ""))
                    if text:
                        log.debug(f"[LLM] Ollama/{_model} OK ({len(text)} chars)")
                        return text
                    log.warning(f"[LLM] Ollama/{_model} réponse vide — modèle suivant")
                else:
                    log.warning(f"[LLM] Ollama/{_model} HTTP {resp.status_code} — modèle suivant")
            except Exception as e:
                log.warning(f"[LLM] Ollama/{_model} : {str(e)[:100]} — modèle suivant")
        log.warning("[LLM] Séquence Ollama épuisée")
    except Exception as e:
        log.warning(f"[LLM] Ollama indisponible : {e}")

    # ── Tentative 2 : GLM (Z.ai API), si configuré et activé ──────────
    _glm_cfg = _cfg.get("glm", {})
    if _glm_cfg.get("enabled"):
        glm_key = os.environ.get(_glm_cfg.get("api_key_env", "ZAI_API_KEY"), "").strip()
        if not glm_key:
            glm_key = _glm_cfg.get("api_key", "")
        if glm_key and not glm_key.startswith("PLACEHOLDER"):
            try:
                import requests
                resp = requests.post(
                    _glm_cfg.get("url", "https://api.z.ai/api/paas/v4/chat/completions"),
                    headers={
                        "Authorization": f"Bearer {glm_key}",
                        "Content-Type":  "application/json",
                    },
                    json={
                        "model":      _glm_cfg.get("model", "glm-5.2"),
                        "messages":   messages,
                        "max_tokens": max_tokens,
                    },
                    timeout=_glm_cfg.get("timeout", timeout),
                )
                if resp.status_code == 200:
                    data = resp.json()
                    text = _strip_think(
                        data.get("choices", [{}])[0].get("message", {}).get("content", ""))
                    if text:
                        log.debug(f"[LLM] GLM/{_glm_cfg.get('name', 'GLM-5.2')} OK ({len(text)} chars)")
                        return text
                    log.warning("[LLM] GLM réponse vide — fallback suivant")
                else:
                    log.warning(f"[LLM] GLM HTTP {resp.status_code} — fallback suivant")
            except Exception as e:
                log.warning(f"[LLM] GLM (Z.ai) : {e}")
        else:
            log.debug("[LLM] GLM activé mais clé absente/placeholder — skip")

    # ── Tentative 3 : API Anthropic ───────────────────────────────────
    api_key = _get_api_key()
    if api_key:
        try:
            import requests
            headers = {
                "x-api-key":         api_key,
                "anthropic-version": "2023-06-01",
                "content-type":      "application/json",
            }
            body = {
                "model":      "claude-sonnet-4-6",
                "max_tokens": max_tokens,
                "messages":   [{"role": "user", "content": prompt}],
            }
            if system:
                body["system"] = system

            resp = requests.post(
                "https://api.anthropic.com/v1/messages",
                headers=headers,
                json=body,
                timeout=timeout,
            )
            if resp.status_code == 200:
                data = resp.json()
                text = data.get("content", [{}])[0].get("text", "").strip()
                if text:
                    log.debug(f"[LLM] Anthropic API OK ({len(text)} chars)")
                    return text
        except Exception as e:
            log.warning(f"[LLM] Anthropic API : {e}")
    else:
        log.debug("[LLM] Pas de clé Anthropic — skip API")

    log.error("[LLM] Tous les backends LLM ont échoué")
    return ""


def safe_json_parse(
    raw: str,
    logger=None,
) -> tuple[bool, dict | list, str]:
    """
    Parse du JSON de façon robuste depuis une réponse LLM.

    Stratégies :
    1. Parse direct
    2. Extraction du premier bloc JSON trouvé
    3. Nettoyage des balises markdown (```json ... ```)

    Returns:
        (ok: bool, data: dict|list, error: str)
    """
    log = logger or _log

    if not raw or not raw.strip():
        return False, {}, "Réponse vide"

    # Stratégie 1 : parse direct
    try:
        data = json.loads(raw)
        return True, data, ""
    except json.JSONDecodeError:
        pass

    # Stratégie 2 : nettoyer les balises markdown
    cleaned = re.sub(r"```(?:json)?\s*", "", raw)
    cleaned = re.sub(r"```\s*$", "", cleaned, flags=re.MULTILINE).strip()
    try:
        data = json.loads(cleaned)
        return True, data, ""
    except json.JSONDecodeError:
        pass

    # Stratégie 3 : extraire le premier objet/tableau JSON
    for pattern in [r'\{[^{}]*(?:\{[^{}]*\}[^{}]*)*\}', r'\[[^\[\]]*\]']:
        match = re.search(pattern, raw, re.DOTALL)
        if match:
            try:
                data = json.loads(match.group())
                return True, data, ""
            except json.JSONDecodeError:
                pass

    # Stratégie 4 : extraire entre la première { et la dernière }
    start = raw.find('{')
    end   = raw.rfind('}')
    if start != -1 and end > start:
        try:
            data = json.loads(raw[start:end+1])
            return True, data, ""
        except json.JSONDecodeError:
            pass

    error = f"JSON invalide après toutes les tentatives ({len(raw)} chars)"
    log.debug(f"[UTILS] {error} | début : {raw[:100]}")
    return False, {}, error


def force_utf8_console():
    """Force UTF-8 sur stdout/stderr — compatibilité overlord_utils_utf8."""
    pass  # Déjà appliqué au chargement du module


if __name__ == "__main__":
    logging.basicConfig(level=logging.DEBUG)
    print("Test fallback_llm...")
    r = fallback_llm("Dis bonjour en français en un mot.")
    print(f"Réponse : {r}")
    print()
    print("Test safe_json_parse...")
    ok, data, err = safe_json_parse('{"title": "Test", "score": 85}')
    print(f"OK={ok} data={data}")
    ok2, data2, err2 = safe_json_parse("```json\n{\"key\": \"value\"}\n```")
    print(f"OK={ok2} data={data2}")

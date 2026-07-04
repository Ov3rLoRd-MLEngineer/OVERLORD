"""
agents/overlord_utils.py -- Utilitaires centraux Ov3rLoRd V1.49s
FIX V1.49s : safe_json_parse() V2 -- extraction JSON robuste par parsing de parentheses.
  Resout le probleme llama3 qui enveloppe le JSON dans du texte conversationnel.
  Avant : json.loads() echoue sur "Extra data" si du texte suit le JSON.
  Apres : on extrait le premier objet JSON complet en comptant les accolades.
"""

import json
import logging
import os
import re
import time
from pathlib import Path

log = logging.getLogger("overlord_utils")

ANTHROPIC_URL        = "https://api.anthropic.com/v1/messages"
OLLAMA_URL           = "http://localhost:11434"
GROK_URL             = "https://api.x.ai/v1/chat/completions"
GROK_MODEL           = "grok-4-fast"
DEFAULT_MODEL        = "claude-sonnet-4-6"
DEFAULT_OLLAMA_MODEL = "mistral"
# Sequence de modeles Ollama essayes dans l'ordre par fallback_llm()
# (serveur Ollama sur RTX 2070 via launch_ollama.bat CUDA_VISIBLE_DEVICES=1)
OLLAMA_MODEL_SEQUENCE = ["mistral", "qwen2.5:7b", "deepseek-r1:7b"]
OLLAMA_TIMEOUT_S      = 30   # timeout PAR modele de la sequence

_LLM_ENDPOINTS_CACHE = None


def _load_llm_endpoints_config() -> dict:
    """Charge config/llm_endpoints.json (source externe de config LLM :
    endpoints Ollama / GLM-5.2 (Z.ai) etc.). Cherche en remontant depuis ce
    fichier vers la racine du repo. Retourne {} si absent/invalide (les
    fonctions appelantes retombent alors sur les constantes par defaut)."""
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
                log.warning(f"[LLM] config/llm_endpoints.json invalide : {e}")
            break
    return _LLM_ENDPOINTS_CACHE


def _get_ollama_endpoint() -> tuple:
    """(url, sequence de modeles, timeout) Ollama, avec override par
    config/llm_endpoints.json (section 'ollama') si present et active."""
    cfg = _load_llm_endpoints_config().get("ollama", {})
    if not cfg.get("enabled", True):
        return OLLAMA_URL, OLLAMA_MODEL_SEQUENCE, OLLAMA_TIMEOUT_S
    return (
        cfg.get("url", OLLAMA_URL),
        cfg.get("models") or OLLAMA_MODEL_SEQUENCE,
        cfg.get("timeout", OLLAMA_TIMEOUT_S),
    )


def _get_glm_config() -> dict:
    """Config GLM (Z.ai) depuis config/llm_endpoints.json. La cle API vient
    en priorite de la variable d'environnement (api_key_env) ou du .env,
    jamais du JSON qui ne doit contenir qu'un placeholder."""
    cfg = dict(_load_llm_endpoints_config().get("glm", {}))
    env_var = cfg.get("api_key_env", "ZAI_API_KEY")
    key = os.environ.get(env_var, "").strip() or _read_env_value(env_var).strip()
    if not key:
        placeholder = cfg.get("api_key", "")
        key = "" if placeholder.startswith("PLACEHOLDER") else placeholder
    cfg["api_key"] = key
    return cfg


def get_api_key(env_file: Path = None) -> str:
    key = os.environ.get("ANTHROPIC_API_KEY", "")
    if key:
        return key
    search_paths = []
    if env_file:
        search_paths.append(Path(env_file))
    p = Path(__file__).resolve()
    for _ in range(4):
        p = p.parent
        search_paths.append(p / ".env")
    for env_path in search_paths:
        if env_path.exists():
            try:
                for line in env_path.read_text(encoding="utf-8").splitlines():
                    if line.startswith("ANTHROPIC_API_KEY="):
                        key = line.split("=", 1)[1].strip().strip('"').strip("'")
                        if key:
                            return key
            except Exception:
                pass
    return ""


def build_headers(api_key: str = None) -> dict:
    key = api_key or get_api_key()
    return {
        "Content-Type":      "application/json",
        "x-api-key":         key,
        "anthropic-version": "2023-06-01",
    }


def retry_api(fn, retries: int = 3, delay: float = 2.0):
    for attempt in range(retries):
        try:
            return fn()
        except Exception as e:
            if attempt < retries - 1:
                time.sleep(delay * (attempt + 1))
            else:
                raise


def safe_json_parse(raw: str, **kwargs) -> tuple:
    """
    Parse JSON robuste V2 -- extraction par comptage de parentheses.

    FIX V1.49s : resout le probleme llama3/Ollama qui enveloppe le JSON
    dans du texte conversationnel (ex: "Voici le storyboard : {...} Bonne chance!").
    json.loads() echoue avec "Extra data" sur ce pattern.
    La V2 extrait le premier objet JSON complet en tracant les accolades/crochets.

    FIX V1.49r : accepte **kwargs silencieux (logger=log dans scenario.py etc.).
    Retourne (success: bool, data, error_msg: str).
    """
    if not raw:
        return False, None, "chaine vide"

    clean = raw.strip()

    # 1. Blocs markdown ```json ... ``` ou ``` ... ```
    if "```json" in clean:
        clean = clean.split("```json", 1)[1].split("```", 1)[0].strip()
    elif "```" in clean:
        clean = clean.split("```", 1)[1].split("```", 1)[0].strip()

    # 2. Essai direct (JSON pur, pas de texte parasite)
    for i, c in enumerate(clean):
        if c in "{[":
            try:
                data = json.loads(clean[i:])
                return True, data, ""
            except json.JSONDecodeError:
                break

    # 3. Extraction robuste : trouver le premier JSON complet
    #    en comptant les accolades/crochets ouvrantes/fermantes
    for start_char, end_char in [("{", "}"), ("[", "]")]:
        idx = clean.find(start_char)
        if idx == -1:
            continue
        depth   = 0
        in_str  = False
        escape  = False
        for i, c in enumerate(clean[idx:], idx):
            if escape:
                escape = False
                continue
            if c == "\\":
                escape = True
                continue
            if c == '"' and not escape:
                in_str = not in_str
                continue
            if not in_str:
                if c == start_char:
                    depth += 1
                elif c == end_char:
                    depth -= 1
                    if depth == 0:
                        candidate = clean[idx:i + 1]
                        try:
                            data = json.loads(candidate)
                            return True, data, ""
                        except json.JSONDecodeError as e:
                            return False, None, str(e)

    return False, None, "aucun JSON valide trouve"


def _read_env_value(key: str) -> str:
    p = Path(__file__).resolve()
    for _ in range(4):
        p = p.parent
        env_path = p / ".env"
        if env_path.exists():
            try:
                for line in env_path.read_text(encoding="utf-8").splitlines():
                    line = line.strip()
                    if line.startswith(f"{key}="):
                        return line.split("=", 1)[1].strip().strip('"').strip("'")
            except Exception:
                pass
    return ""


def _get_llm_mode() -> str:
    mode = os.environ.get("OV_LLM_MODE", "").lower().strip()
    if mode in ("online", "offline", "auto", "grok", "glm"):
        return mode
    mode = _read_env_value("OV_LLM_MODE").lower()
    if mode in ("online", "offline", "auto", "grok", "glm"):
        return mode
    return "auto" if get_api_key() else "offline"


def _get_ollama_model() -> str:
    m = os.environ.get("OV_OLLAMA_MODEL", "").strip()
    if m:
        return m
    m = _read_env_value("OV_OLLAMA_MODEL").strip()
    return m if m else DEFAULT_OLLAMA_MODEL


def _get_grok_key() -> str:
    key = os.environ.get("GROK_API_KEY", "").strip()
    if key:
        return key
    return _read_env_value("GROK_API_KEY").strip()


def _call_grok(prompt: str, system: str = "",
               max_tokens: int = 1000) -> str:
    import requests
    key = _get_grok_key()
    if not key:
        raise ValueError("GROK_API_KEY absent dans .env")
    messages = []
    if system:
        messages.append({"role": "system", "content": system})
    messages.append({"role": "user", "content": prompt})
    resp = requests.post(
        GROK_URL,
        headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
        json={"model": GROK_MODEL, "messages": messages, "max_tokens": max_tokens},
        timeout=60
    )
    if resp.status_code == 200:
        return resp.json()["choices"][0]["message"]["content"]
    raise RuntimeError(f"Grok HTTP {resp.status_code} : {resp.text[:200]}")


def _call_glm(prompt: str, system: str = "",
             max_tokens: int = 1000) -> str:
    """Appelle GLM-5.2 via l'API Z.ai. Endpoint/modele/cle lus depuis
    config/llm_endpoints.json (section 'glm'), cle surchargeable par
    ZAI_API_KEY (env ou .env)."""
    import requests
    cfg = _get_glm_config()
    if not cfg.get("enabled"):
        raise ValueError("GLM desactive dans config/llm_endpoints.json (enabled=false)")
    key = cfg.get("api_key", "")
    if not key:
        raise ValueError(
            f"{cfg.get('api_key_env', 'ZAI_API_KEY')} absent (.env / config/llm_endpoints.json)")
    messages = []
    if system:
        messages.append({"role": "system", "content": system})
    messages.append({"role": "user", "content": prompt})
    resp = requests.post(
        cfg.get("url", "https://api.z.ai/api/paas/v4/chat/completions"),
        headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
        json={"model": cfg.get("model", "glm-5.2"), "messages": messages,
              "max_tokens": max_tokens},
        timeout=cfg.get("timeout", 60),
    )
    if resp.status_code == 200:
        return _strip_think(resp.json()["choices"][0]["message"]["content"])
    raise RuntimeError(f"GLM HTTP {resp.status_code} : {resp.text[:200]}")


def _call_claude(prompt: str, system: str = "",
                 model: str = DEFAULT_MODEL,
                 max_tokens: int = 1000) -> str:
    import requests
    key = get_api_key()
    if not key:
        raise ValueError("ANTHROPIC_API_KEY absent")
    body = {
        "model":      model,
        "max_tokens": max_tokens,
        "messages":   [{"role": "user", "content": prompt}],
    }
    if system:
        body["system"] = system
    resp = requests.post(
        ANTHROPIC_URL, headers=build_headers(key), json=body, timeout=60)
    if resp.status_code == 200:
        content = resp.json().get("content", [])
        return "".join(c.get("text", "") for c in content
                       if c.get("type") == "text")
    raise RuntimeError(f"Claude HTTP {resp.status_code} : {resp.text[:200]}")


def _strip_think(text: str) -> str:
    """Retire les blocs <think>...</think> (deepseek-r1) de la reponse —
    sinon ils polluent safe_json_parse() et les prompts en aval."""
    if text and "<think>" in text:
        text = re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL)
    return text.strip() if text else ""


def _call_ollama(prompt: str, system: str = "",
                 model: str = None,
                 max_tokens: int = 1000,
                 timeout: int = OLLAMA_TIMEOUT_S) -> str:
    import requests
    ollama_url, _, _ = _get_ollama_endpoint()
    ollama_model = _get_ollama_model()
    if model and "claude" not in model.lower() and "/" not in model:
        ollama_model = model
    messages = []
    if system:
        messages.append({"role": "system", "content": system})
    messages.append({"role": "user", "content": prompt})
    try:
        resp = requests.post(
            f"{ollama_url}/api/chat",
            json={"model": ollama_model, "messages": messages,
                  "stream": False,
                  "options": {"num_predict": max_tokens}},
            timeout=timeout)
        if resp.status_code == 200:
            return _strip_think(resp.json().get("message", {}).get("content", ""))
    except Exception:
        pass
    full_prompt = f"{system}\n\n{prompt}" if system else prompt
    resp = requests.post(
        f"{ollama_url}/api/generate",
        json={"model": ollama_model, "prompt": full_prompt,
              "stream": False,
              "options": {"num_predict": max_tokens}},
        timeout=timeout)
    if resp.status_code == 200:
        return _strip_think(resp.json().get("response", ""))
    raise RuntimeError(f"Ollama HTTP {resp.status_code}")


def _call_ollama_sequence(prompt: str, system: str = "",
                          model: str = None,
                          max_tokens: int = 1000,
                          logger: logging.Logger = None) -> str:
    """
    Essaie les modeles Ollama en SEQUENCE avec un timeout par modele :
    mistral -> qwen2.5:7b -> deepseek-r1:7b par defaut (OLLAMA_MODEL_SEQUENCE),
    surchargeable par config/llm_endpoints.json (section 'ollama').
    Si `model` force un modele Ollama valide, il passe en tete de sequence ;
    OV_OLLAMA_MODEL (env/.env) est aussi insere en tete s'il differe.
    Retourne la premiere reponse non vide, "" si tous echouent.
    """
    _log = logger or log
    _, ollama_models, ollama_timeout = _get_ollama_endpoint()
    sequence = []
    if model and "claude" not in model.lower() and "/" not in model:
        sequence.append(model)
    for m in [_get_ollama_model()] + ollama_models:
        if m and m not in sequence:
            sequence.append(m)
    for m in sequence:
        try:
            result = _call_ollama(prompt, system=system, model=m,
                                  max_tokens=max_tokens,
                                  timeout=ollama_timeout)
            if result:
                _log.debug(f"[LLM] Ollama/{m} OK ({len(result)} chars)")
                return result
            _log.warning(f"[LLM] Ollama/{m} reponse vide -- modele suivant")
        except Exception as e:
            _log.warning(f"[LLM] Ollama/{m} echoue : {str(e)[:100]} -- modele suivant")
    return ""


def is_ollama_available(model: str = None) -> bool:
    import requests
    try:
        r = requests.get(f"{OLLAMA_URL}/api/tags", timeout=3)
        if r.status_code != 200:
            return False
        if model:
            models = [m.get("name", "") for m in r.json().get("models", [])]
            return any(model in m for m in models)
        return True
    except Exception:
        return False


def fallback_llm(prompt: str, system: str = "",
                 model: str = DEFAULT_MODEL,
                 max_tokens: int = 1000,
                 logger: logging.Logger = None) -> str:
    """
    Point d'entree LLM principal.
    offline -> Ollama direct
    online  -> Claude uniquement
    auto    -> Claude puis Ollama si echec
    """
    _log     = logger or log
    llm_mode = _get_llm_mode()

    # ── Mode Grok ────────────────────────────────────────────────────────
    if llm_mode == "grok":
        try:
            result = _call_grok(prompt, system=system, max_tokens=max_tokens)
            _log.debug(f"[LLM] Grok/{GROK_MODEL} OK ({len(result)} chars)")
            return result
        except Exception as e:
            _log.warning(f"[LLM] Grok echoue : {str(e)[:120]} -- fallback Ollama")
            result = _call_ollama_sequence(prompt, system=system,
                                           max_tokens=max_tokens, logger=_log)
            if result:
                return result
            _log.error("[LLM] Sequence Ollama epuisee apres Grok")
            return ""

    # ── Mode GLM-5.2 (Z.ai) ──────────────────────────────────────────────
    if llm_mode == "glm":
        try:
            result = _call_glm(prompt, system=system, max_tokens=max_tokens)
            _log.debug(f"[LLM] GLM-5.2 OK ({len(result)} chars)")
            return result
        except Exception as e:
            _log.warning(f"[LLM] GLM echoue : {str(e)[:120]} -- fallback Ollama")
            result = _call_ollama_sequence(prompt, system=system,
                                           max_tokens=max_tokens, logger=_log)
            if result:
                return result
            _log.error("[LLM] Sequence Ollama epuisee apres GLM")
            return ""

    if llm_mode == "offline":
        result = _call_ollama_sequence(prompt, system=system,
                                       max_tokens=max_tokens, logger=_log)
        if not result:
            _log.error("[LLM] Sequence Ollama epuisee en mode offline")
        return result

    key = get_api_key()
    if key:
        try:
            result = _call_claude(prompt, system=system,
                                   model=model, max_tokens=max_tokens)
            _log.debug(f"[LLM] Claude/{model} OK ({len(result)} chars)")
            return result
        except Exception as e:
            if llm_mode == "online":
                _log.error(
                    "[LLM] Claude indisponible et mode=online -- aucun fallback")
                return ""
            _log.warning(
                f"[LLM] Claude echoue : {str(e)[:120]} -- tentative Ollama")

    if llm_mode == "online":
        _log.error("[LLM] Claude indisponible et mode=online -- aucun fallback")
        return ""

    if is_ollama_available():
        result = _call_ollama_sequence(prompt, system=system,
                                       max_tokens=max_tokens, logger=_log)
        if result:
            _log.info(f"[LLM] Fallback Ollama OK ({len(result)} chars)")
            return result
        _log.error("[LLM] Sequence Ollama epuisee")
    else:
        _log.warning("[LLM] Serveur Ollama injoignable sur " + OLLAMA_URL)
    return ""


def ensure_workspace(base: Path = None) -> Path:
    ws = (base or Path(".")) / "workspace"
    for sub in ["logs", "scripts", "storyboards", "checkpoints",
                 "archive", "narrative", "asset_library", "generation",
                 "v120_learning", "dream_mode", "context_bus"]:
        (ws / sub).mkdir(parents=True, exist_ok=True)
    return ws


def ensure_env_file(base: Path = None) -> Path:
    env_path = (base or Path(".")) / ".env"
    if not env_path.exists():
        env_path.write_text(
            "# Ov3rLoRd -- Configuration\n"
            "ANTHROPIC_API_KEY=\n"
            "# LLM mode : online | offline | auto | grok\n"
            "OV_LLM_MODE=offline\n"
            "# Modele Ollama\n"
            "OV_OLLAMA_MODEL=mistral\n"
            "# Grok xAI ($175/mois gratuits : https://console.x.ai)\n"
            "GROK_API_KEY=\n",
            encoding="utf-8")
        log.info(f"[UTILS] .env cree : {env_path}")
    return env_path


if __name__ == "__main__":
    import sys, io
    if hasattr(sys.stdout, "buffer"):
        sys.stdout = io.TextIOWrapper(
            sys.stdout.buffer, encoding="utf-8", errors="replace")
    logging.basicConfig(level=logging.INFO)
    print(f"Mode LLM      : {_get_llm_mode()}")
    print(f"Modele Ollama : {_get_ollama_model()}")
    print(f"Cle API       : {'presente' if get_api_key() else 'absente'}")
    print(f"Ollama dispo  : {is_ollama_available()}")
    print(f"Grok key      : {'presente' if _get_grok_key() else 'absente — ajouter GROK_API_KEY dans .env'}")

    # Test V2 : JSON avec texte parasite (cas llama3)
    test_llama3 = '''Here is the storyboard JSON:
{
  "shots": [{"shot_id": "S01", "description": "Goku powers up"}]
}
Let me know if you need more!'''
    ok, data, err = safe_json_parse(test_llama3, logger=None)
    print(f"safe_json_parse V2 (llama3 style) : ok={ok} | shots={len(data.get('shots',[]))}")

    ok2, d2, e2 = safe_json_parse('{"simple": true}')
    print(f"safe_json_parse V2 (direct)        : ok={ok2} | data={d2}")
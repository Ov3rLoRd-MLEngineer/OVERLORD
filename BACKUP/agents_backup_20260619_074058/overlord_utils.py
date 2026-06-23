"""
agents/overlord_utils.py — Utilitaires transversaux V1.49
Mise a jour V1.49 :
  - _get_reddit_headers()  : headers Reddit anonymes (manquait, importe par audience_analyzer)
  - get_api_key()          : alias public de _get_api_key pour compatibilite
  - read_bus() / write_bus(): helpers context_bus pour les agents qui ne veulent
                              pas importer context_bus directement
  - log_banner()           : remplacement des caracteres box-drawing par ASCII
"""

import json
import logging
import os
import time
from pathlib import Path
from typing import Any

log = logging.getLogger("overlord_utils")

# ── Cle API ──────────────────────────────────────────────────────────
def get_api_key() -> str:
    """Lit la cle Anthropic depuis l'environnement ou .env."""
    key = os.environ.get("ANTHROPIC_API_KEY", "")
    if not key:
        for candidate in [
            Path(__file__).parent.parent / ".env",
            Path(__file__).parent / ".env",
            Path(".env"),
        ]:
            if candidate.exists():
                for line in candidate.read_text(encoding="utf-8").splitlines():
                    if line.startswith("ANTHROPIC_API_KEY="):
                        key = line.split("=", 1)[1].strip().strip('"').strip("'")
                        if key:
                            break
            if key:
                break
    return key

# Alias prive — certains agents importent _get_api_key (pattern V1.30)
_get_api_key = get_api_key

def build_headers() -> dict:
    """Headers Anthropic standardises pour tous les agents."""
    return {
        "Content-Type":      "application/json",
        "x-api-key":         get_api_key(),
        "anthropic-version": "2023-06-01",
    }

# ── Headers Reddit ────────────────────────────────────────────────────
def _get_reddit_headers(user_agent: str = "Ov3rLoRd-Pipeline/1.49") -> dict:
    """
    Retourne les headers pour les requetes Reddit anonymes.
    Si REDDIT_CLIENT_ID est defini dans l'env, utilise OAuth2 basique.
    Sinon retourne un User-Agent simple (acces public).
    """
    client_id = os.environ.get("REDDIT_CLIENT_ID", "")
    secret    = os.environ.get("REDDIT_CLIENT_SECRET", "")

    if client_id and secret:
        # OAuth2 application-only (sans compte utilisateur)
        import requests as _req
        import base64 as _b64
        try:
            creds = _b64.b64encode(f"{client_id}:{secret}".encode()).decode()
            r = _req.post(
                "https://www.reddit.com/api/v1/access_token",
                headers={
                    "Authorization": f"Basic {creds}",
                    "User-Agent":    user_agent,
                },
                data={"grant_type": "client_credentials"},
                timeout=10,
            )
            if r.status_code == 200:
                token = r.json().get("access_token", "")
                if token:
                    return {
                        "Authorization": f"Bearer {token}",
                        "User-Agent":    user_agent,
                    }
        except Exception as e:
            log.warning(f"[UTILS] Reddit OAuth2 echoue : {e} — fallback anonyme")

    # Acces public anonyme
    return {"User-Agent": user_agent}

# ── Retry avec backoff exponentiel ───────────────────────────────────
def retry_api(fn, max_retries: int = 3, base_delay: float = 2.0,
              logger: logging.Logger = None):
    """
    Execute fn() avec retry + backoff exponentiel.
    fn doit retourner (success: bool, result: Any).
    """
    _log = logger or logging.getLogger("overlord_utils.retry")
    last_result = None

    for attempt in range(max_retries + 1):
        try:
            success, result = fn()
            if success:
                return True, result
            last_result = result
        except Exception as e:
            last_result = str(e)
            _log.warning(f"[RETRY] Tentative {attempt+1}/{max_retries+1} echouee : {e}")

        if attempt < max_retries:
            delay = base_delay * (2 ** attempt)
            _log.info(f"[RETRY] Attente {delay:.0f}s avant retry {attempt+2}...")
            time.sleep(delay)

    _log.error(f"[RETRY] Echec definitif apres {max_retries+1} tentatives")
    return False, last_result

# ── Parse JSON robuste ────────────────────────────────────────────────
def safe_json_parse(raw: str, logger: logging.Logger = None) -> tuple:
    """
    Parse JSON avec nettoyage automatique des backticks et espaces.
    Retourne (success: bool, data: dict|None, error: str|None)
    """
    _log = logger or logging.getLogger("overlord_utils.json")

    if not raw or not raw.strip():
        return False, None, "Reponse vide"

    clean = raw.strip().lstrip('\ufeff')

    if clean.startswith("```"):
        lines = clean.split("\n")
        clean = "\n".join(lines[1:-1] if lines[-1].strip() == "```" else lines[1:])
        clean = clean.strip()

    try:
        return True, json.loads(clean), None
    except json.JSONDecodeError:
        pass

    for start_char, end_char in [('{', '}'), ('[', ']')]:
        start = clean.find(start_char)
        end   = clean.rfind(end_char)
        if start != -1 and end != -1 and end > start:
            try:
                return True, json.loads(clean[start:end+1]), None
            except json.JSONDecodeError:
                pass

    _log.error(f"[JSON] Parse echoue. Debut : {clean[:100]}")
    return False, None, f"JSON invalide : {clean[:80]}"

# ── Fallback LLM ─────────────────────────────────────────────────────
def fallback_llm(prompt: str, system: str = "",
                 model: str = "claude-sonnet-4-6",
                 max_tokens: int = 2000,
                 logger: logging.Logger = None) -> str:
    """
    Appel LLM avec fallback automatique :
    1. Claude (Anthropic API)
    2. Ollama local (llama3 ou mistral)
    3. Chaine vide avec warning

    Consulte le context_bus pour le modele prefere si disponible.
    """
    import requests
    _log = logger or logging.getLogger("overlord_utils.llm")

    # Lire le modele prefere depuis le bus (conscience ou cost_tracker peuvent le modifier)
    preferred = read_bus("conscience.preferred_llm") or read_bus("cost.preferred_model") or ""
    if preferred and preferred not in ("claude-sonnet-4-6", model):
        if preferred.startswith("ollama/"):
            # Forcer le fallback Ollama directement
            _log.info(f"[LLM] Modele prefere depuis bus : {preferred} — skip Claude")
            ollama_model = preferred.replace("ollama/", "")
            result = _try_ollama(prompt, system, ollama_model, max_tokens, _log)
            if result:
                return result
        else:
            model = preferred

    # Tentative 1 : Claude
    key = get_api_key()
    if key:
        try:
            body = {
                "model": model, "max_tokens": max_tokens,
                "messages": [{"role": "user", "content": prompt}],
            }
            if system:
                body["system"] = system

            def _call_claude():
                r = requests.post(
                    "https://api.anthropic.com/v1/messages",
                    headers=build_headers(), json=body, timeout=60
                )
                if r.status_code == 200:
                    content = r.json().get("content", [])
                    return True, " ".join(b["text"] for b in content if b.get("type") == "text")
                _log.warning(f"[LLM] Claude HTTP {r.status_code}: {r.text[:100]}")
                return False, ""

            ok, result = retry_api(_call_claude, max_retries=2, base_delay=3.0, logger=_log)
            if ok and result:
                _log.debug(f"[LLM] Claude OK ({len(result)} chars)")
                return result
        except Exception as e:
            _log.warning(f"[LLM] Claude exception : {e}")

    # Tentative 2 : Ollama local
    for ollama_model in ["llama3", "mistral", "deepseek-coder", "phi3"]:
        result = _try_ollama(prompt, system, ollama_model, max_tokens, _log)
        if result:
            return result

    _log.error("[LLM] Tous les LLM indisponibles — retour vide")
    return ""

def _try_ollama(prompt: str, system: str, model: str,
                max_tokens: int, _log: logging.Logger) -> str:
    """Tente un appel Ollama. Retourne la reponse ou chaine vide."""
    import requests
    try:
        r = requests.get("http://localhost:11434/api/tags", timeout=3)
        if r.status_code != 200:
            return ""
        installed = [m["name"].split(":")[0] for m in r.json().get("models", [])]
        if not any(model in m for m in installed):
            return ""
        full_prompt = f"{system}\n\n{prompt}" if system else prompt
        r2 = requests.post(
            "http://localhost:11434/api/generate",
            json={"model": model, "prompt": full_prompt,
                  "stream": False, "options": {"num_predict": max_tokens}},
            timeout=120
        )
        if r2.status_code == 200:
            result = r2.json().get("response", "")
            if result:
                _log.info(f"[LLM] Fallback Ollama/{model} OK")
                return result
    except Exception:
        pass
    return ""

# ── Helpers Context Bus ───────────────────────────────────────────────
def read_bus(key: str, default=None):
    """
    Lit une valeur depuis le context_bus sans crasher si absent.
    Pratique pour les agents qui ne veulent pas importer context_bus.
    """
    try:
        from agents.context_bus import get_bus
        val = get_bus().read(key)
        return val if val is not None else default
    except Exception:
        return default

def write_bus(key: str, value, agent_id: str = "overlord_utils",
              confidence: float = 0.8):
    """Ecrit une valeur sur le context_bus sans crasher si absent."""
    try:
        from agents.context_bus import get_bus
        get_bus().write(key, value, agent_id=agent_id, confidence=confidence)
        return True
    except Exception:
        return False

# ── Banniere agent ────────────────────────────────────────────────────
def log_banner(agent_name: str, version: str = "V1.49",
               logger: logging.Logger = None):
    """Banniere de demarrage standardisee — ASCII uniquement."""
    _log = logger or logging.getLogger(agent_name)
    sep = "=" * 50
    _log.info(sep)
    _log.info(f"  Ov3rLoRd | {agent_name.upper()} | {version}")
    _log.info(sep)

# ── Workspace ─────────────────────────────────────────────────────────
def ensure_workspace(*paths: str) -> list:
    """Cree les dossiers workspace necessaires et retourne leurs Path."""
    created = []
    for p in paths:
        path = Path(p)
        path.mkdir(parents=True, exist_ok=True)
        created.append(path)
    return created

# ── Auto-creation .env ────────────────────────────────────────────────
def ensure_env_file(base_dir: Path = None) -> Path:
    """Verifie l'existence du .env — le cree depuis .env.template si absent."""
    base = base_dir or Path(__file__).parent.parent
    env  = base / ".env"
    tmpl = base / ".env.template"

    if not env.exists():
        if tmpl.exists():
            import shutil
            shutil.copy(tmpl, env)
            print(f"[OVERLORD] .env cree depuis .env.template — renseigne ANTHROPIC_API_KEY")
        else:
            env.write_text(
                "# Ov3rLoRd Pipeline — Configuration\n"
                "ANTHROPIC_API_KEY=\n"
                "TELEGRAM_TOKEN=\n"
                "TELEGRAM_CHAT_ID=\n"
                "COMFY_URL=http://127.0.0.1:8188\n"
                "REDDIT_CLIENT_ID=\n"
                "REDDIT_CLIENT_SECRET=\n"
                "REDDIT_USERNAME=\n"
                "REDDIT_PASSWORD=\n",
                encoding="utf-8"
            )
            print(f"[OVERLORD] .env cree — renseigne ANTHROPIC_API_KEY dans {env}")
    return env
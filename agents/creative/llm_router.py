"""
agents/llm_router.py — Routeur de taches LLM Ov3rLoRd
Lit config/llm_endpoints.json et route chaque appel vers le modele le plus
adapte au type de tache, avec repli automatique sur fallback_llm() (sequence
complete Ollama puis GLM/Anthropic selon le mode configure) si l'appel direct
au modele cible echoue ou renvoie une reponse vide.
"""
import logging

try:
    from agents.overlord_utils import (
        fallback_llm, _call_ollama, _call_glm,
        _load_llm_endpoints_config, _get_ollama_endpoint,
    )
    UTILS_OK = True
except ImportError:
    UTILS_OK = False
    fallback_llm = None
    _call_ollama = None
    _call_glm = None
    _load_llm_endpoints_config = None
    _get_ollama_endpoint = None

log = logging.getLogger("llm_router")

# Modele Ollama cible par type de tache.
TASK_MODELS = {
    "code":              "deepseek-r1:7b",
    "prompt_refinement": "qwen2.5:7b",
    "general":           "mistral",
}
COMPLEX_OLLAMA_FALLBACK = "deepseek-r1:7b"


def _glm_enabled() -> bool:
    """True si config/llm_endpoints.json active GLM-5.2 (section 'glm')."""
    if not _load_llm_endpoints_config:
        return False
    try:
        return bool(_load_llm_endpoints_config().get("glm", {}).get("enabled"))
    except Exception:
        return False


def call(task_type: str, prompt: str, system: str = None,
          max_tokens: int = 1500, logger: logging.Logger = None) -> str:
    """
    Route `prompt` vers le modele associe a `task_type` :
      "code"               -> deepseek-r1:7b
      "prompt_refinement"  -> qwen2.5:7b
      "general"            -> mistral
      "complex"            -> GLM-5.2 (si config/llm_endpoints.json: glm.enabled=true),
                              sinon deepseek-r1:7b
    Tout `task_type` inconnu retombe sur "general".

    Si l'appel direct au modele cible echoue ou renvoie une reponse vide,
    repli automatique sur fallback_llm() (sequence Ollama complete puis
    GLM/Anthropic selon le mode configure).

    Returns:
        str : reponse du LLM, ou "" si le routage ET le repli echouent.
    """
    _log = logger or log
    if not UTILS_OK:
        _log.error("[ROUTER] agents.overlord_utils indisponible -- routage impossible")
        return ""

    system = system or ""
    use_glm = task_type == "complex" and _glm_enabled()

    if use_glm:
        try:
            result = _call_glm(prompt, system=system, max_tokens=max_tokens)
            if result:
                _log.debug(f"[ROUTER] {task_type} -> GLM-5.2 OK ({len(result)} chars)")
                return result
            _log.warning(f"[ROUTER] {task_type} -> GLM-5.2 reponse vide -- repli fallback_llm()")
        except Exception as e:
            _log.warning(f"[ROUTER] {task_type} -> GLM-5.2 echoue ({str(e)[:100]}) -- repli fallback_llm()")
        return fallback_llm(prompt, system=system, max_tokens=max_tokens, logger=_log)

    target_model = (COMPLEX_OLLAMA_FALLBACK if task_type == "complex"
                     else TASK_MODELS.get(task_type, TASK_MODELS["general"]))
    _, _, ollama_timeout = _get_ollama_endpoint()

    # fallback_llm() ignore le parametre model pour la sequence Ollama : le
    # routage cible passe donc par _call_ollama() direct ; fallback_llm() ne
    # sert qu'au repli complet en cas d'echec/reponse vide.
    try:
        result = _call_ollama(prompt, system=system, model=target_model,
                               max_tokens=max_tokens, timeout=ollama_timeout)
        if result:
            _log.debug(f"[ROUTER] {task_type} -> {target_model} OK ({len(result)} chars)")
            return result
        _log.warning(f"[ROUTER] {task_type} -> {target_model} reponse vide -- repli fallback_llm()")
    except Exception as e:
        _log.warning(f"[ROUTER] {task_type} -> {target_model} echoue ({str(e)[:100]}) -- repli fallback_llm()")

    result = fallback_llm(prompt, system=system, max_tokens=max_tokens, logger=_log)
    if result:
        _log.info(f"[ROUTER] {task_type} -> repli fallback_llm() OK ({len(result)} chars)")
    else:
        _log.error(f"[ROUTER] {task_type} : routage direct ET repli fallback_llm() ont echoue")
    return result


if __name__ == "__main__":
    logging.basicConfig(level=logging.DEBUG)
    for tt in ("general", "code", "prompt_refinement", "complex"):
        print(f"--- task_type={tt} ---")
        r = call(tt, "Dis juste OK.")
        print(f"-> {r!r}")

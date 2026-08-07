"""
agents/ollama_bridge.py — Ollama Bridge
Gère la communication avec l'API Ollama locale et les APIs LLM online.
"""
import json, logging, requests, subprocess
import os
from enum import Enum

OLLAMA_URL = "http://localhost:11434"
ANTHROPIC_URL = "https://api.anthropic.com/v1/messages"

class LLMMode(Enum):
    ONLINE  = "online"
    OFFLINE = "offline"

ONLINE_MODELS  = ["claude-sonnet-4-6", "gpt-4o", "gemini-1.5-pro"]
OFFLINE_MODELS = ["llama3", "mistral", "deepseek-coder"]

ONLINE_LABELS  = {
    "claude-sonnet-4-6": "Claude Sonnet 4.6",
    "gpt-4o":            "GPT-4o",
    "gemini-1.5-pro":    "Gemini 1.5 Pro",
}
OFFLINE_LABELS = {
    "llama3":          "Llama 3",
    "mistral":         "Mistral",
    "deepseek-coder":  "DeepSeek Coder",
}


class OllamaBridge:
    def __init__(self, logger: logging.Logger = None,
                 api_keys: dict = None):
        self.log      = logger or logging.getLogger("ollama")
        self.api_keys = api_keys or {}    # {"openai": "sk-...", "google": "AIza..."}
        self.mode     = LLMMode.OFFLINE
        self.model    = "llama3"

    def set_mode(self, mode: LLMMode, model: str):
        self.mode  = mode
        self.model = model
        self.log.info(f"[BRIDGE] Mode={mode.value} | Modèle={model}")

    # ── Vérification Ollama ───────────────────────────────────────────
    def is_ollama_running(self) -> bool:
        try:
            r = requests.get(f"{OLLAMA_URL}/api/tags", timeout=3)
            return r.status_code == 200
        except Exception:
            return False

    def list_installed_models(self) -> list:
        try:
            r = requests.get(f"{OLLAMA_URL}/api/tags", timeout=5)
            if r.status_code == 200:
                return [m["name"].split(":")[0] for m in r.json().get("models", [])]
        except Exception:
            pass
        return []

    def is_model_installed(self, model_name: str) -> bool:
        installed = self.list_installed_models()
        return any(model_name.lower() in m.lower() for m in installed)

    def pull_model(self, model_name: str) -> bool:
        """Télécharge un modèle Ollama via subprocess."""
        self.log.info(f"[BRIDGE] Pull Ollama : {model_name}")
        try:
            result = subprocess.run(
                ["ollama", "pull", model_name],
                capture_output=True, text=True, timeout=600
            )
            if result.returncode == 0:
                self.log.info(f"[BRIDGE] {model_name} installé ✓")
                return True
            self.log.error(f"[BRIDGE] Pull échoué : {result.stderr[:200]}")
            return False
        except FileNotFoundError:
            self.log.error("[BRIDGE] Commande 'ollama' introuvable — installer Ollama d'abord")
            return False
        except subprocess.TimeoutExpired:
            self.log.error("[BRIDGE] Timeout pull (600s)")
            return False

    # ── Complétion unifiée ────────────────────────────────────────────
    def complete(self, prompt: str, system: str = "",
                 max_tokens: int = 2000) -> str:
        if self.mode == LLMMode.OFFLINE:
            return self._ollama_complete(prompt, system, max_tokens)
        return self._online_complete(prompt, system, max_tokens)

    def _ollama_complete(self, prompt: str, system: str, max_tokens: int) -> str:
        if not self.is_ollama_running():
            self.log.error("[BRIDGE] Ollama non démarré")
            return ""
        try:
            payload = {
                "model":  self.model,
                "prompt": f"{system}\n\n{prompt}" if system else prompt,
                "stream": False,
                "options": {"num_predict": max_tokens},
            }
            r = requests.post(f"{OLLAMA_URL}/api/generate",
                              json=payload, timeout=120)
            if r.status_code == 200:
                return r.json().get("response", "")
            self.log.error(f"[BRIDGE] Ollama HTTP {r.status_code}")
            return ""
        except Exception as e:
            self.log.error(f"[BRIDGE] Erreur Ollama : {e}")
            return ""

    def _online_complete(self, prompt: str, system: str, max_tokens: int) -> str:
        if self.model.startswith("claude"):
            return self._anthropic_complete(prompt, system, max_tokens)
        if self.model.startswith("gpt"):
            return self._openai_complete(prompt, system, max_tokens)
        if self.model.startswith("gemini"):
            return self._google_complete(prompt, system, max_tokens)
        return ""

    def _anthropic_complete(self, prompt, system, max_tokens):
        body = {"model": self.model, "max_tokens": max_tokens,
                "messages": [{"role":"user","content":prompt}]}
        if system:
            body["system"] = system
        try:
            r = requests.post(ANTHROPIC_URL,
                              headers={"Content-Type":"application/json"},
                              json=body, timeout=60)
            if r.status_code == 200:
                return r.json()["content"][0]["text"]
        except Exception as e:
            self.log.error(f"[BRIDGE/Anthropic] {e}")
        return ""

    def _openai_complete(self, prompt, system, max_tokens):
        key = self.api_keys.get("openai","")
        if not key:
            self.log.error("[BRIDGE/OpenAI] Clé API manquante")
            return ""
        msgs = []
        if system:
            msgs.append({"role":"system","content":system})
        msgs.append({"role":"user","content":prompt})
        try:
            r = requests.post(
                "https://api.openai.com/v1/chat/completions",
                headers={"Authorization":f"Bearer {key}","Content-Type":"application/json"},
                json={"model":self.model,"messages":msgs,"max_tokens":max_tokens},
                timeout=60
            )
            if r.status_code == 200:
                return r.json()["choices"][0]["message"]["content"]
        except Exception as e:
            self.log.error(f"[BRIDGE/OpenAI] {e}")
        return ""

    def _google_complete(self, prompt, system, max_tokens):
        key = self.api_keys.get("google","")
        if not key:
            self.log.error("[BRIDGE/Google] Clé API manquante")
            return ""
        full = f"{system}\n\n{prompt}" if system else prompt
        try:
            url = (f"https://generativelanguage.googleapis.com/v1beta/models/"
                   f"{self.model}:generateContent?key={key}")
            r = requests.post(url,
                json={"contents":[{"parts":[{"text":full}]}],
                      "generationConfig":{"maxOutputTokens":max_tokens}},
                timeout=60)
            if r.status_code == 200:
                return r.json()["candidates"][0]["content"]["parts"][0]["text"]
        except Exception as e:
            self.log.error(f"[BRIDGE/Google] {e}")
        return ""

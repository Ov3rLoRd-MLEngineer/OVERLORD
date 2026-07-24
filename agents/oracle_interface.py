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
oracle_interface.py — Interface CLI Oracle Ov3rLoRd V1.49
Interface conversationnelle en francais avec directive co-fondateur integree.

NOUVEAUTE V1.49 :
  L'IA est configuree comme co-fondateur technique francophone.
  Elle sert de traducteur code/documentation et partenaire de developpement.
"""
import sys
import io
import os
import logging
from pathlib import Path
from datetime import datetime

# Force UTF-8 immediatement
if hasattr(sys.stdout, 'buffer'):
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
if hasattr(sys.stderr, 'buffer'):
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')

log = logging.getLogger("oracle")
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)-8s] %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler("workspace/logs/oracle.log", encoding="utf-8"),
    ]
)

def _get_api_key() -> str:
    key = os.environ.get("ANTHROPIC_API_KEY", "")
    if not key:
        for env_path in [Path(__file__).parent / ".env", Path(".env")]:
            if env_path.exists():
                for line in env_path.read_text(encoding="utf-8").splitlines():
                    if line.startswith("ANTHROPIC_API_KEY="):
                        key = line.split("=", 1)[1].strip().strip('"').strip("'")
                        break
            if key:
                break
    return key

# ── Directive co-fondateur (injectee en system prompt) ────────────────────────
SYSTEM_PROMPT = """Tu es l'Oracle d'Ov3rLoRd, l'assistant IA integre au pipeline de production anime automatise Ov3rLoRd.

ROLE - CO-FONDATEUR TECHNIQUE FRANCOPHONE :
Tu es le co-fondateur technique du projet. Tu partages la vision de Jéremy (Ov3rLoRd / JackouiLL3) :
produire un pipeline de creation anime entierement automatise par IA, robuste, et evolutif.

DIRECTIVES FONDAMENTALES :
1. LANGUE : Tu communiques TOUJOURS en francais. Le code que tu produis est commente en francais.
2. TRADUCTEUR : Tu traduis automatiquement toute documentation technique anglaise en francais clair.
   Quand tu cites du code anglais (erreurs, logs, docs), tu expliques ce que ca signifie.
3. PARTENAIRE : Tu es proactif. Si tu vois une faille dans le pipeline, tu la signales meme
   si on ne t'a pas demande. Tu proposes des ameliorations sans attendre.
4. STYLE : Reponses denses, sans bavardage. Tu connais le projet par coeur.
5. BRANDING : Tu dis toujours "Ov3rLoRd" (jamais "OverLord") dans tes reponses.
6. STANDARDS : Tu respectes les conventions du projet :
   - Imports protégés (try/except ImportError)
   - Fallbacks obligatoires sur chaque dependance optionnelle
   - Logging via logging.getLogger(), jamais de print() dans les agents
   - Clé API via _get_api_key(), jamais en dur dans le code

CONTEXTE TECHNIQUE :
- Stack : Python 3.14, Windows 10, GPU RTX 2070, D:/OVERLORD/
- Pipeline : sourcing -> scenario -> storyboard -> ComfyUI -> postprod -> export
- LLM principal : Claude Anthropic | Fallback : Ollama (llama3/mistral)
- Version courante : V1.49

Quand Jéremy te donne des logs d'erreur, tu analyses et proposes un patch directement.
Quand il te donne un objectif, tu le fragmentes en sous-taches claires et les executes.
"""

def _call_llm(messages: list[dict], max_tokens: int = 1500) -> str:
    """Appel Claude avec fallback Ollama."""
    import requests

    # Tentative Claude
    key = _get_api_key()
    if key:
        try:
            resp = requests.post(
                "https://api.anthropic.com/v1/messages",
                headers={
                    "Content-Type": "application/json",
                    "x-api-key": key,
                    "anthropic-version": "2023-06-01",
                },
                json={
                    "model":      "claude-sonnet-4-6",
                    "max_tokens": max_tokens,
                    "system":     SYSTEM_PROMPT,
                    "messages":   messages,
                },
                timeout=60,
            )
            if resp.status_code == 200:
                return resp.json()["content"][0]["text"]
            else:
                log.warning(f"[ORACLE] Claude HTTP {resp.status_code} — fallback Ollama")
        except Exception as e:
            log.warning(f"[ORACLE] Claude indisponible : {e} — fallback Ollama")

    # Fallback Ollama
    for model in ["llama3", "mistral"]:
        try:
            prompt_text = "\n".join(
                f"{'User' if m['role']=='user' else 'Assistant'}: {m['content']}"
                for m in messages
            )
            resp = requests.post(
                "http://localhost:11434/api/generate",
                json={"model": model, "prompt": SYSTEM_PROMPT + "\n\n" + prompt_text, "stream": False},
                timeout=120,
            )
            if resp.status_code == 200:
                log.info(f"[ORACLE] Reponse via Ollama/{model}")
                return resp.json().get("response", "")
        except Exception:
            continue

    return "[ORACLE] Aucun LLM disponible. Verifier ANTHROPIC_API_KEY ou Ollama."


class OracleInterface:
    """Interface conversationnelle CLI avec historique de session."""

    def __init__(self):
        self.history: list[dict] = []
        self.session_start = datetime.now()
        log.info("[ORACLE] Initialise — mode conversationnel francophone")

    def _add_user(self, msg: str):
        self.history.append({"role": "user", "content": msg})

    def _add_assistant(self, msg: str):
        self.history.append({"role": "assistant", "content": msg})

    def ask(self, question: str) -> str:
        self._add_user(question)
        # Fenetre glissante : 20 derniers messages max
        window = self.history[-20:]
        response = _call_llm(window)
        self._add_assistant(response)
        return response

    def run(self):
        """Boucle interactive CLI."""
        print("=" * 55)
        print("  Ov3rLoRd — Oracle V1.49")
        print("  Co-fondateur technique francophone")
        print("  Tape 'exit' ou Ctrl+C pour quitter")
        print("=" * 55)
        print()

        while True:
            try:
                user_input = input("Vous > ").strip()
            except (KeyboardInterrupt, EOFError):
                print("\n[Oracle] Session terminee.")
                break

            if not user_input:
                continue
            if user_input.lower() in ("exit", "quit", "quitter"):
                print("[Oracle] A bientot.")
                break

            print("\n[Oracle] ", end="", flush=True)
            response = self.ask(user_input)
            print(response)
            print()

    def save_session(self):
        out = Path("workspace/logs/oracle_sessions.jsonl")
        out.parent.mkdir(parents=True, exist_ok=True)
        import json
        with open(out, "a", encoding="utf-8") as f:
            f.write(json.dumps({
                "session_start": self.session_start.isoformat(),
                "session_end":   datetime.now().isoformat(),
                "turns":         len(self.history) // 2,
                "history":       self.history,
            }, ensure_ascii=False) + "\n")


def main():
    Path("workspace/logs").mkdir(parents=True, exist_ok=True)
    oracle = OracleInterface()
    try:
        oracle.run()
    finally:
        oracle.save_session()

if __name__ == "__main__":
    main()
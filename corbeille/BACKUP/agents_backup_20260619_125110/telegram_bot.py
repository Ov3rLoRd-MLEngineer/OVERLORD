"""
agents/telegram_bot.py — Notifications Telegram V1.49
FIX V1.49l : bloc try sans except corrige (erreur syntaxe ligne 18 du bundle precedent).
Les messages Telegram conservent leurs emojis (interface utilisateur).
Les logs Python sont en ASCII.
"""
import json
import logging
import os
import subprocess
import sys
import threading
from pathlib import Path
from datetime import datetime

log = logging.getLogger("telegram_bot")

try:
    from telegram import Update
    from telegram.ext import Application, CommandHandler, ContextTypes
    TG_OK = True
except ImportError:
    TG_OK = False


def _get_token() -> tuple:
    token = os.environ.get("TELEGRAM_TOKEN", "")
    chat  = os.environ.get("TELEGRAM_CHAT_ID", "")
    if not token:
        env = Path(__file__).parent.parent / ".env"
        if env.exists():
            for line in env.read_text(encoding="utf-8").splitlines():
                if line.startswith("TELEGRAM_TOKEN="):
                    token = line.split("=", 1)[1].strip()
                if line.startswith("TELEGRAM_CHAT_ID="):
                    chat  = line.split("=", 1)[1].strip()
    return token, chat


def send_notification(message: str, logger=None) -> bool:
    """Envoie une notification Telegram sans bot polling."""
    _log = logger or log
    token, chat_id = _get_token()
    if not token or not chat_id:
        _log.debug("[TELEGRAM] Token/Chat ID manquant — notification ignoree")
        return False
    try:
        import requests
        ts  = datetime.now().strftime("%d/%m %H:%M")
        msg = "\U0001f916 *Ov3rLoRd* `" + ts + "`\n" + message
        r   = requests.post(
            "https://api.telegram.org/bot" + token + "/sendMessage",
            json={"chat_id": chat_id, "text": msg, "parse_mode": "Markdown"},
            timeout=10,
        )
        if r.status_code == 200:
            _log.info("[TELEGRAM] Notification envoyee OK")
            return True
        _log.warning("[TELEGRAM] HTTP " + str(r.status_code) + ": " + r.text[:100])
    except Exception as e:
        _log.warning("[TELEGRAM] Erreur : " + str(e))
    return False


class OverLordBot:

    def __init__(self, base_dir: Path = None):
        self.base            = base_dir or Path(__file__).parent.parent
        self.token, self.chat_id = _get_token()

    async def _cmd_start(self, update: Update, ctx: ContextTypes.DEFAULT_TYPE):
        await update.message.reply_text(
            "\U0001f916 *Ov3rLoRd Bot V1.49*\n\nCommandes :\n"
            "/status \u2014 Etat du pipeline\n"
            "/run [media] \u2014 Lancer un run\n"
            "/improve \u2014 Lancer self-improve\n"
            "/logs \u2014 Derniers logs",
            parse_mode="Markdown"
        )

    async def _cmd_status(self, update: Update, ctx: ContextTypes.DEFAULT_TYPE):
        comfy  = "\u274c"
        ollama = "\u274c"
        try:
            import requests as _r
            if _r.get("http://127.0.0.1:8188/system_stats", timeout=2).status_code == 200:
                comfy = "\u2705"
        except Exception:
            pass
        try:
            import requests as _r
            if _r.get("http://localhost:11434/api/tags", timeout=2).status_code == 200:
                ollama = "\u2705"
        except Exception:
            pass

        cp_dir   = self.base / "workspace" / "checkpoints"
        last_run = "\u2014"
        if cp_dir.exists():
            cps = sorted(cp_dir.glob("*.json"),
                         key=lambda f: f.stat().st_mtime, reverse=True)
            if cps:
                last_run = cps[0].stem

        await update.message.reply_text(
            "\U0001f4ca *Status Ov3rLoRd V1.49*\n"
            "ComfyUI : " + comfy + "\n"
            "Ollama  : " + ollama + "\n"
            "Dernier run : `" + last_run + "`",
            parse_mode="Markdown"
        )

    async def _cmd_run(self, update: Update, ctx: ContextTypes.DEFAULT_TYPE):
        args  = ctx.args
        media = args[0] if args else "anime"
        await update.message.reply_text(
            "\u25b6\ufe0f Lancement pipeline `" + media + "`...",
            parse_mode="Markdown"
        )
        def _launch():
            result = subprocess.run(
                [sys.executable, str(self.base / "maestro.py"), "--media-type", media],
                capture_output=True, text=True, timeout=600
            )
            send_notification("Pipeline `" + media + "` termine \u2014 code=" + str(result.returncode))
        threading.Thread(target=_launch, daemon=True).start()

    async def _cmd_improve(self, update: Update, ctx: ContextTypes.DEFAULT_TYPE):
        await update.message.reply_text("\u27f3 Self-improve lance...", parse_mode="Markdown")
        def _run():
            result = subprocess.run(
                [sys.executable, str(self.base / "self_improve.py"), "--mode", "auto"],
                capture_output=True, text=True, timeout=120
            )
            send_notification("Self-improve termine\n`" + result.stdout[-200:] + "`")
        threading.Thread(target=_run, daemon=True).start()

    async def _cmd_logs(self, update: Update, ctx: ContextTypes.DEFAULT_TYPE):
        logs_dir = self.base / "workspace" / "logs"
        if not logs_dir.exists():
            await update.message.reply_text("Aucun log disponible.")
            return
        log_files = sorted(logs_dir.glob("*.log"),
                           key=lambda f: f.stat().st_mtime, reverse=True)
        if not log_files:
            await update.message.reply_text("Aucun log disponible.")
            return
        last_lines = log_files[0].read_text(encoding="utf-8", errors="ignore").split('\n')[-10:]
        msg = "\U0001f4cb *Derniers logs* :\n```\n" + "\n".join(last_lines) + "\n```"
        await update.message.reply_text(msg, parse_mode="Markdown")

    def run(self):
        if not TG_OK:
            log.error("[TELEGRAM] python-telegram-bot non installe : pip install python-telegram-bot")
            return
        if not self.token:
            log.error("[TELEGRAM] TELEGRAM_TOKEN manquant dans .env")
            return
        app = Application.builder().token(self.token).build()
        app.add_handler(CommandHandler("start",   self._cmd_start))
        app.add_handler(CommandHandler("status",  self._cmd_status))
        app.add_handler(CommandHandler("run",     self._cmd_run))
        app.add_handler(CommandHandler("improve", self._cmd_improve))
        app.add_handler(CommandHandler("logs",    self._cmd_logs))
        log.info("[TELEGRAM] Bot demarre \u2014 en attente de commandes...")
        app.run_polling()


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    bot = OverLordBot()
    bot.run()
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
overlord_utils_utf8.py -- Helper UTF-8 global Ov3rLoRd V1.49q
A importer en PREMIER dans maestro.py et oracle_interface.py.
Force stdout/stderr en UTF-8 pour tout le pipeline.
"""
import sys
import io
import os

def force_utf8_console():
    """
    Force l'encodage UTF-8 sur stdout/stderr.
    A appeler une fois au demarrage du process principal.
    Idempotent : sans effet si deja en UTF-8.
    """
    # Python 3.14 : argparse appelle can_colorize() -> os.isatty(fileno())
    # sur le wrapper TextIOWrapper, ce qui leve ValueError si le fd est ferme.
    # Solution : ne remplacer que si on N'EST PAS dans un terminal interactif
    # (cas pipeline / subprocess). En terminal interactif, l'encodage est
    # deja correct ou on laisse Python gerer.
    def _needs_wrap(stream):
        if getattr(stream, 'encoding', '').lower() == 'utf-8':
            return False
        if not hasattr(stream, 'buffer'):
            return False
        # Ne pas wrapper si c'est un vrai TTY -- Python 3.14 argparse en a besoin
        try:
            if os.isatty(stream.buffer.fileno()):
                return False
        except Exception:
            pass
        return True

    if _needs_wrap(sys.stdout):
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
    if _needs_wrap(sys.stderr):
        sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')

    # Variables d'environnement pour les sous-process lances par ce process
    os.environ.setdefault("PYTHONIOENCODING", "utf-8")
    os.environ.setdefault("PYTHONUTF8", "1")

# Auto-application a l'import
force_utf8_console()

if __name__ == "__main__":
    print("overlord_utils_utf8.py OK -- UTF-8 force")
    print(f"Encodage stdout : {sys.stdout.encoding}")
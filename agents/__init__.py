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
agents/__init__.py -- Package agents Ov3rLoRd V1.49p
Expose les imports les plus utilises pour faciliter les imports courts.
FIX : recree directement (ratio 13.2x bloquait le patcher en UPDATE).
"""

# Imports optionnels -- ne pas crasher si un agent manque
try:
    from agents.overlord_utils import get_api_key, fallback_llm, build_headers
    __all__ = ["get_api_key", "fallback_llm", "build_headers"]
except ImportError:
    __all__ = []

# Version du package
__version__ = "1.49p"
__project__ = "Ov3rLoRd"
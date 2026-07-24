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
ov_console.py — Console Colorisée Ov3rLoRd V1.70
Source unique pour tous les prints colorés dans les agents.

Couleurs ANSI compatibles Windows 10+ (cmd et PowerShell).
À importer dans tous les agents qui affichent des infos console.

Usage :
  from ov_console import cprint, banner, ascii_banner, progress, result_line

  cprint("Fichier chargé", "ok", detail="maestro.py")
  cprint("Erreur critique", "err", detail="timeout ComfyUI")
  cprint("Attention", "warn", detail="3 retries restants")
  cprint("En cours", "info", detail="batch 3/8")

  ascii_banner()             # bannière ASCII complète, au lancement
  banner("OV3RLORD V1.70")   # bannière encadrée compacte
  progress("Images générées", 6, 8)
  result_line(ok=7, err=1)
"""

import sys
import os
from datetime import datetime

# Activer les couleurs ANSI sur Windows
if sys.platform == "win32":
    os.system("")  # Active le mode VT100 sur cmd/PowerShell Windows 10+

# ── Codes ANSI ────────────────────────────────────────────────────────

class C:
    # Reset
    RESET   = "\033[0m"
    BOLD    = "\033[1m"
    DIM     = "\033[2m"

    # Couleurs texte
    BLACK   = "\033[30m"
    RED     = "\033[31m"
    GREEN   = "\033[32m"
    YELLOW  = "\033[33m"
    BLUE    = "\033[34m"
    MAGENTA = "\033[35m"
    CYAN    = "\033[36m"
    WHITE   = "\033[37m"

    # Couleurs vives
    BRED    = "\033[91m"
    BGREEN  = "\033[92m"
    BYELLOW = "\033[93m"
    BBLUE   = "\033[94m"
    BMAGENTA= "\033[95m"
    BCYAN   = "\033[96m"
    BWHITE  = "\033[97m"

    # Fonds
    BG_RED    = "\033[41m"
    BG_GREEN  = "\033[42m"
    BG_YELLOW = "\033[43m"
    BG_BLUE   = "\033[44m"
    BG_BLACK  = "\033[40m"


# ── Palette Ov3rLoRd ─────────────────────────────────────────────────

PALETTE = {
    # Niveaux de log
    "ok":      (C.BGREEN,   "✓"),
    "err":     (C.BRED,     "✗"),
    "warn":    (C.BYELLOW,  "⚠"),
    "info":    (C.BCYAN,    "●"),
    "debug":   (C.DIM,      "·"),
    "run":     (C.BMAGENTA, "▶"),
    "stop":    (C.BRED,     "■"),
    "wait":    (C.BYELLOW,  "…"),
    "gpu":     (C.BGREEN,   "⚡"),
    "agent":   (C.BCYAN,    "◈"),
    "file":    (C.BBLUE,    "📄"),
    "patch":   (C.BMAGENTA, "🔧"),
    "score":   (C.BGREEN,   "★"),
    "time":    (C.CYAN,     "⏱"),
    "title":   (C.BWHITE,   "══"),
}

# ── Fonctions d'affichage ─────────────────────────────────────────────

def _ts() -> str:
    return f"{C.DIM}{datetime.now().strftime('%H:%M:%S')}{C.RESET}"


def cprint(message: str, level: str = "info",
           detail: str = None, ts: bool = True):
    """
    Print colorisé principal.

    Args:
        message : texte principal
        level   : ok / err / warn / info / debug / run / gpu / file / patch
        detail  : info secondaire (nom de fichier, valeur, etc.)
        ts      : afficher l'horodatage

    Exemples :
        cprint("Batch terminé", "ok", detail="8/8 images")
        cprint("ComfyUI", "err", detail="400 Bad Request")
        cprint("maestro.py", "file", detail="chargé 2847 lignes")
        cprint("RTX 5080", "gpu", detail="VRAM 7.2/16GB — 45%")
    """
    color, icon = PALETTE.get(level, (C.WHITE, "·"))

    parts = []
    if ts:
        parts.append(_ts())

    parts.append(f"{color}{icon}{C.RESET}")
    parts.append(f"{color}{C.BOLD}{message}{C.RESET}")

    if detail:
        # Coloriser les détails selon leur contenu
        detail_colored = _colorize_detail(detail)
        parts.append(f"{C.DIM}→{C.RESET} {detail_colored}")

    print(" ".join(parts))


def _colorize_detail(detail: str) -> str:
    """
    Colorise automatiquement les détails :
    - Nombres → cyan
    - Noms de fichiers .py/.json/.md → bleu
    - Pourcentages → selon valeur
    - OK/PASS/✓ → vert | ERR/FAIL/✗ → rouge
    """
    import re

    # OK/PASS/succès → vert
    detail = re.sub(
        r'\b(OK|PASS|✓|success|validé|terminé)\b',
        lambda m: f"{C.BGREEN}{m.group()}{C.RESET}",
        detail, flags=re.IGNORECASE
    )

    # ERR/FAIL/erreur → rouge
    detail = re.sub(
        r'\b(ERR|FAIL|ERREUR|✗|error|échoué|bloqué)\b',
        lambda m: f"{C.BRED}{m.group()}{C.RESET}",
        detail, flags=re.IGNORECASE
    )

    # Avertissements → jaune
    detail = re.sub(
        r'\b(WARN|warning|attention|⚠)\b',
        lambda m: f"{C.BYELLOW}{m.group()}{C.RESET}",
        detail, flags=re.IGNORECASE
    )

    # Noms de fichiers → bleu
    detail = re.sub(
        r'[\w/\\]+\.(py|json|md|txt|log|bat|zip|safetensors|pt)',
        lambda m: f"{C.BBLUE}{m.group()}{C.RESET}",
        detail
    )

    # Fractions N/M → cyan/cyan
    detail = re.sub(
        r'(\d+)/(\d+)',
        lambda m: f"{C.BCYAN}{m.group(1)}{C.RESET}/{C.BCYAN}{m.group(2)}{C.RESET}",
        detail
    )

    # Nombres isolés → cyan
    detail = re.sub(
        r'(?<![/\w])(\d+\.?\d*)(?![/\w])',
        lambda m: f"{C.CYAN}{m.group()}{C.RESET}",
        detail
    )

    # Pourcentages → vert si >70, jaune si 40-70, rouge si <40
    def color_pct(m):
        val = float(m.group(1))
        c   = C.BGREEN if val >= 70 else (C.BYELLOW if val >= 40 else C.BRED)
        return f"{c}{m.group()}{C.RESET}"

    detail = re.sub(r'(\d+\.?\d*)%', color_pct, detail)

    return detail


def banner(title: str, subtitle: str = None, width: int = 60):
    """Bannière encadrée style Ov3rLoRd."""
    line  = "═" * width
    print()
    print(f"{C.BRED}{C.BOLD}╔{line}╗{C.RESET}")
    pad   = (width - len(title)) // 2
    print(f"{C.BRED}{C.BOLD}║{' '*pad}{C.BWHITE}{title}{C.BRED}"
          f"{' '*(width-pad-len(title))}║{C.RESET}")
    if subtitle:
        pad2 = (width - len(subtitle)) // 2
        print(f"{C.BRED}║{C.DIM}{' '*pad2}{subtitle}"
              f"{' '*(width-pad2-len(subtitle))}{C.BRED}║{C.RESET}")
    print(f"{C.BRED}{C.BOLD}╚{line}╝{C.RESET}")
    print()


def section(title: str, width: int = 60):
    """Séparateur de section."""
    line = "─" * (width - len(title) - 3)
    print(f"\n{C.BCYAN}{C.BOLD}── {title} {line}{C.RESET}")


def progress(label: str, current: int, total: int,
             unit: str = "", bar_width: int = 20):
    """
    Barre de progression colorée.
    progress("Images", 6, 8, "img")
    → ● Images  ████████████████░░░░  6/8 img  75%
    """
    pct      = current / max(total, 1)
    filled   = int(bar_width * pct)
    bar      = "█" * filled + "░" * (bar_width - filled)

    pct_val  = pct * 100
    bar_col  = C.BGREEN if pct_val >= 70 else (C.BYELLOW if pct_val >= 40 else C.BRED)
    pct_col  = C.BGREEN if pct_val >= 70 else (C.BYELLOW if pct_val >= 40 else C.BRED)

    print(
        f"{_ts()} {C.BCYAN}●{C.RESET} "
        f"{C.BOLD}{label:15s}{C.RESET}  "
        f"{bar_col}{bar}{C.RESET}  "
        f"{C.CYAN}{current}{C.RESET}/{C.CYAN}{total}{C.RESET} {unit}  "
        f"{pct_col}{pct_val:.0f}%{C.RESET}"
    )


def result_line(ok: int, err: int, warn: int = 0,
                label: str = "Résultat"):
    """
    Ligne de résultat finale colorée.
    result_line(7, 1) → Résultat : ✓ 7 OK  ✗ 1 ERR
    """
    parts = [f"{C.BOLD}{label} :{C.RESET}"]

    if ok > 0:
        parts.append(f"{C.BGREEN}✓ {ok} OK{C.RESET}")
    if warn > 0:
        parts.append(f"{C.BYELLOW}⚠ {warn} WARN{C.RESET}")
    if err > 0:
        parts.append(f"{C.BRED}✗ {err} ERR{C.RESET}")

    print("  ".join(parts))


def kv(key: str, value, key_width: int = 20):
    """
    Affiche une paire clé/valeur avec valeur colorisée.
    kv("Fichiers traités", "8/8") → Fichiers traités   : 8/8
    """
    val_str     = str(value)
    val_colored = _colorize_detail(val_str)
    print(f"  {C.DIM}{key:<{key_width}}{C.RESET}: {val_colored}")


def file_status(filepath: str, status: str = "ok",
                detail: str = None):
    """
    Affiche le statut d'un fichier.
    file_status("agents/maestro.py", "ok", "patché 2 blocs")
    """
    color = C.BGREEN if status == "ok" else \
            C.BRED   if status == "err" else C.BYELLOW
    icon  = "✓" if status == "ok" else "✗" if status == "err" else "⚠"

    line  = (f"  {color}{icon}{C.RESET} "
             f"{C.BBLUE}{filepath}{C.RESET}")
    if detail:
        line += f"  {C.DIM}{detail}{C.RESET}"
    print(line)


# ── Bannière ASCII ──────────────────────────────────────────────────────

ASCII_LOGO = r""" ██████╗ ██╗   ██╗██████╗ ██████╗ ██╗      ██████╗ ██████╗ ██████╗
██╔═══██╗██║   ██║╚════██╗██╔══██╗██║     ██╔═══██╗██╔══██╗██╔══██╗
██║   ██║██║   ██║ █████╔╝██████╔╝██║     ██║   ██║██████╔╝██║  ██║
██║   ██║╚██╗ ██╔╝ ╚═══██╗██╔══██╗██║     ██║   ██║██╔══██╗██║  ██║
╚██████╔╝ ╚████╔╝ ██████╔╝██║  ██║███████╗╚██████╔╝██║  ██║██████╔╝
 ╚═════╝   ╚═══╝  ╚═════╝ ╚═╝  ╚═╝╚══════╝ ╚═════╝ ╚═╝  ╚═╝╚═════╝"""


def ascii_banner(tagline: str = "L'usine pense. L'usine apprend. L'usine publie."):
    """Bannière ASCII pleine (police ANSI Shadow), affichée au lancement."""
    print()
    for line in ASCII_LOGO.splitlines():
        print(f"{C.BRED}{C.BOLD}{line}{C.RESET}")
    if tagline:
        pad = max((68 - len(tagline)) // 2, 0)
        print(f"\n{' '*pad}{C.DIM}\"{tagline}\"{C.RESET}\n")


# ── Démo ──────────────────────────────────────────────────────────────

if __name__ == "__main__":
    ascii_banner()

    section("DÉMARRAGE PIPELINE")
    cprint("ComfyUI",         "ok",   detail="EN LIGNE port 8188")
    cprint("RTX 5080",        "gpu",  detail="VRAM 7.2/16GB — 45%")
    cprint("maestro.py",      "file", detail="chargé 2847 lignes")
    cprint("fabricatedXL",    "info", detail="checkpoint chargé")

    section("PRODUCTION")
    cprint("Batch 1/3",       "run",  detail="universe: evangelion battle")
    progress("Images",         6,  8, "img")
    progress("Qualité",       74, 100, "%")
    cprint("quality_gate",    "ok",  detail="score 82/100 — PASS")
    cprint("yolo_hand.pt",    "warn",detail="WARN confidence 28% — seuil bas")

    section("PATCHER V1.1")
    file_status("maestro.py",              "ok",  "patch 1/2 — get_logger corrigé")
    file_status("maestro.py",              "ok",  "patch 2/2 — checkpoint storyboard")
    file_status("agents/dream_mode.py",    "err", "fichier introuvable")

    section("RÉSULTAT")
    kv("Images générées", "8/8")
    kv("Score moyen",     "83%")
    kv("Temps total",     "22 min")
    kv("Erreurs",         "0")
    print()
    result_line(ok=7, err=1, warn=2)
    print()

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
build_maintenance_hub.py — Compile aAa_MaintenanceHub.py en EXE V1.49
Usage : python build_maintenance_hub.py
Produit : dist/aAa_MaintenanceHub.exe (standalone, sans console)
"""
import subprocess
import sys
from pathlib import Path

_ROOT   = Path(__file__).parent
_TARGET = _ROOT / "aAa_MaintenanceHub.py"
_ICON   = _ROOT / "overlord_icon.ico"  # optionnel

def build():
    print("=" * 55)
    print("  Ov3rLoRd -- Build Maintenance Hub EXE V1.49")
    print("=" * 55)

    if not _TARGET.exists():
        print(f"ERREUR : {_TARGET} introuvable.")
        sys.exit(1)

    try:
        import PyInstaller
        print(f"PyInstaller {PyInstaller.__version__} detecte OK")
    except ImportError:
        print("PyInstaller manquant -- pip install pyinstaller")
        sys.exit(1)

    cmd = [
        sys.executable, "-m", "PyInstaller",
        "--onefile",           # EXE standalone
        "--windowed",          # pas de fenetre console
        "--name", "aAa_MaintenanceHub",
        "--distpath", str(_ROOT / "dist"),
        "--workpath", str(_ROOT / "build"),
        "--specpath", str(_ROOT / "build"),
        "--clean",
    ]

    # Icone optionnelle
    if _ICON.exists():
        cmd += ["--icon", str(_ICON)]
        print(f"Icone : {_ICON.name}")
    else:
        print("Icone overlord_icon.ico absente -- EXE sans icone (normal)")

    cmd.append(str(_TARGET))

    print(f"\nCommande : {' '.join(cmd)}\n")
    result = subprocess.run(cmd, cwd=str(_ROOT))

    if result.returncode == 0:
        exe = _ROOT / "dist" / "aAa_MaintenanceHub.exe"
        size_mb = exe.stat().st_size / 1_048_576 if exe.exists() else 0
        print("\n" + "=" * 55)
        print(f"  EXE genere : {exe}")
        print(f"  Taille     : {size_mb:.1f} MB")
        print("=" * 55)
    else:
        print("\nERREUR : build echoue (voir logs ci-dessus)")
        sys.exit(1)

if __name__ == "__main__":
    build()
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
build_launcher.py — Compile overlord_launcher.py en OverLord.exe
Usage : python build_launcher.py
"""
import subprocess, sys, shutil
from pathlib import Path

import io
if hasattr(sys.stdout, 'buffer') and getattr(sys.stdout, 'encoding','').lower() != 'utf-8':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

print("═"*55)
print("  Ov3rLoRd — Build Launcher EXE v1.45")
print("═"*55)

try:
    import PyInstaller
    print(f"  PyInstaller {PyInstaller.__version__} ✓")
except ImportError:
    subprocess.run([sys.executable, "-m", "pip", "install", "pyinstaller"], check=True)

sep = ";" if sys.platform == "win32" else ":"
add_data = [
    ("agents",                 "agents"),
    ("config.json",            "."),
    ("settings.json",          "."),
    ("Combined_V35_API.json",  "."),
    ("maestro.py",             "."),
    ("oracle_interface.py",    "."),
    ("self_improve.py",        "."),
    ("overlord_utils.py",      "."),
    ("test_pipeline.py",       "."),
]

data_args = []
for src, dst in add_data:
    if Path(src).exists():
        data_args += ["--add-data", f"{src}{sep}{dst}"]

cmd = [
    sys.executable, "-m", "PyInstaller",
    "--noconfirm", "--onefile", "--windowed",
    "--name", "OverLord",
    "--clean",
    "--hidden-import", "tkinter",
    "--hidden-import", "tkinter.ttk",
    "--hidden-import", "requests",
] + data_args + ["overlord_launcher.py"]

print(f"\n  Build en cours...")
result = subprocess.run(cmd)

if result.returncode == 0:
    print(f"\n{'═'*55}")
    print(f"  ✓ BUILD RÉUSSI → dist/Ov3rLoRd.exe")
    print(f"{'═'*55}")
else:
    print(f"\n  ✗ BUILD ÉCHOUÉ (code={result.returncode})")

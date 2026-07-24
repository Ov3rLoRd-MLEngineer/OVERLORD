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
build_exe.py -- Compilation EXE PyInstaller Ov3rLoRd V1.49q
Genere 2 EXE : MaestroProduction | MaintenanceHub
OrganizeProject est integre dans le Hub (pas d'EXE separe).
Lancer depuis D:\\\\OVERLORD\\\\ :
    python build_exe.py
    python build_exe.py --clean
"""

import subprocess
import sys
import os
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parent

BUILDS = [
    {
        "name":    "MaestroProduction",
        "script":  "launcher.py",
        "icon":    "assets/icon_maestro.ico",
        "console": False,
        "desc":    "GUI principale du pipeline de production",
        "root_files": [
            "overlord_utils_utf8.py",
            "maestro.py",
            "Combined_V35_API.json",
            "node_catalog.json",
            "config.json",
        ],
        "hiddenimports": [
            "agents.overlord_utils",
            "agents.context_bus",
            "agents.director",
            "agents.sourcing",
            "agents.scenario",
            "agents.storyboard",
            "agents.postprod",
            "agents.critic",
            "agents.watchdog",
            "agents.checkpoint_manager",
            "agents.pipeline_conscience",
            "agents.emotion_engine",
            "agents.world_model",
            "agents.generative_world",
            "agents.roles_registry",
            "agents.cost_tracker",
            "agents.narrative_memory",
            "PIL._tkinter_finder",
            "customtkinter",
        ],
    },
    {
        "name":    "MaintenanceHub",
        "script":  "aAa_MaintenanceHub.py",
        "icon":    "assets/icon_hub.ico",
        "console": False,
        "desc":    "Hub de maintenance + chat Ollama + OrganizeProject",
        "root_files": [
            "overlord_utils_utf8.py",
            "patcher.py",
            "test_pipeline.py",
            "organize_project.py",
            "aAa_Auditeur.py",
        ],
        "hiddenimports": [
            "agents.overlord_utils",
            "agents.context_bus",
            "organize_project",
            "customtkinter",
            "PIL._tkinter_finder",
        ],
    },
]


def sep(title=""):
    line = "=" * 55
    if title:
        print(f"\n{line}\n  {title}\n{line}")
    else:
        print(line)


def check_pyinstaller() -> bool:
    try:
        import PyInstaller
        print(f"[BUILD] PyInstaller {PyInstaller.__version__} detecte")
        return True
    except ImportError:
        print("[BUILD] ERREUR : pip install pyinstaller")
        return False


def protect_utf8_file() -> bool:
    src = ROOT / "overlord_utils_utf8.py"
    bad = ROOT / "agents" / "overlord_utils_utf8.py"
    if bad.exists():
        print(f"[BUILD] overlord_utils_utf8.py detecte dans agents/ -- suppression")
        bad.unlink()
    if not src.exists():
        print(f"[BUILD] ERREUR : overlord_utils_utf8.py absent de la racine")
        return False
    print(f"[BUILD] overlord_utils_utf8.py OK ({src.stat().st_size} octets)")
    return True


def build_spec(cfg: dict) -> str:
    name    = cfg["name"]
    script  = str(ROOT / cfg["script"]).replace("\\", "/")
    icon_p  = ROOT / cfg.get("icon", "")
    icon_v  = f"'{str(icon_p).replace(chr(92),'/')}'" if icon_p.exists() else "None"
    console = "True" if cfg.get("console") else "False"

    datas = [f"('{str(ROOT / 'agents').replace(chr(92),'/')}', 'agents')"]
    for fname in cfg.get("root_files", []):
        fp = ROOT / fname
        if fp.exists():
            datas.append(f"('{str(fp).replace(chr(92),'/')}', '.')")

    hidden = ", ".join(f"'{h}'" for h in cfg.get("hiddenimports", []))

    return f"""# -*- mode: python ; coding: utf-8 -*-
# {name}.spec -- Ov3rLoRd V1.49q -- auto-genere
block_cipher = None
a = Analysis(
    ['{script}'],
    pathex=['{str(ROOT).replace(chr(92), "/")}'],
    binaries=[],
    datas=[{', '.join(datas)}],
    hiddenimports=[{hidden}],
    hookspath=[],
    hooksconfig={{}},
    runtime_hooks=[],
    excludes=['matplotlib', 'IPython', 'jupyter'],
    cipher=block_cipher, noarchive=False,
)
pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)
exe = EXE(
    pyz, a.scripts, a.binaries, a.zipfiles, a.datas, [],
    name='{name}', debug=False, bootloader_ignore_signals=False,
    strip=False, upx=True, upx_exclude=[], runtime_tmpdir=None,
    console={console}, disable_windowed_traceback=False,
    argv_emulation=False, target_arch=None,
    codesign_identity=None, entitlements_file=None, icon={icon_v},
)
"""


def build_one(cfg: dict, clean: bool = False) -> bool:
    name   = cfg["name"]
    script = ROOT / cfg["script"]
    print(f"\n  [{name}]  {cfg.get('desc','')}")
    if not script.exists():
        print(f"  ERREUR : {script.name} introuvable")
        return False

    spec_path = ROOT / f"{name}.spec"
    spec_path.write_text(build_spec(cfg), encoding="utf-8")
    print(f"  .spec   : {spec_path.name}")

    cmd = [sys.executable, "-m", "PyInstaller", "--noconfirm"]
    if clean:
        cmd.append("--clean")
    cmd.append(str(spec_path))

    print(f"  Build   : en cours...")
    try:
        r = subprocess.run(cmd, cwd=str(ROOT), capture_output=True,
                           text=True, encoding="utf-8", errors="replace")
        for line in r.stdout.splitlines():
            if any(k in line for k in ["ERROR","WARNING","completed","Building EXE"]):
                if "WARNING" not in line or "Hidden" not in line:
                    print(f"          {line.strip()}")
        if r.returncode == 0:
            exe = ROOT / "dist" / f"{name}.exe"
            if exe.exists():
                print(f"  OK      : dist/{name}.exe ({exe.stat().st_size//1024//1024} MB)")
                return True
        print(f"  ECHEC   : code={r.returncode}")
        return False
    except Exception as e:
        print(f"  ERREUR  : {e}")
        return False


def main():
    import argparse
    p = argparse.ArgumentParser()
    p.add_argument("--clean", action="store_true")
    p.add_argument("--one",   action="store_true",
                   help="MaestroProduction seulement")
    args = p.parse_args()

    sep("Ov3rLoRd Build System V1.49q")
    print(f"  Racine  : {ROOT}")
    print(f"  Python  : {sys.version.split()[0]}")

    if not check_pyinstaller(): return 1
    if not protect_utf8_file(): return 1

    builds  = [BUILDS[0]] if args.one else BUILDS
    results = {}
    sep()
    print(f"  {len(builds)} EXE : {', '.join(b['name'] for b in builds)}")

    for cfg in builds:
        results[cfg["name"]] = build_one(cfg, clean=args.clean)

    sep("Rapport")
    ok = sum(1 for v in results.values() if v)
    for name, success in results.items():
        print(f"  [{'OK  ' if success else 'FAIL'}] {name}")
    print(f"\n  Total   : {ok}/{len(results)} EXE compiles")
    sep()
    return 0 if ok == len(results) else 1


if __name__ == "__main__":
    sys.exit(main())

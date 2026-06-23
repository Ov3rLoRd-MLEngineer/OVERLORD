"""
build_organizer.py — Compile organize_project.py en .exe
Usage : python build_organizer.py
→ dist\\OrganizeProject.exe
"""
import sys
import subprocess

def build():
    print("=== Build OrganizeProject.exe ===")
    cmd = [
        sys.executable, "-m", "PyInstaller",
        "--noconfirm",
        "--onefile",
        "--console",
        "--name", "OrganizeProject",
        "--clean",
        "organize_project.py",
    ]
    print(f"Commande : {' '.join(cmd)}\n")
    result = subprocess.run(cmd)
    if result.returncode == 0:
        print("\n✓ OrganizeProject.exe généré dans dist\\")
        print("  Double-clique dessus depuis le dossier PIPELINE PROJECT")
        print("  ou : OrganizeProject.exe --dry-run  (simulation)")
    else:
        print("\n✗ Échec. Vérifie : pip install pyinstaller")

if __name__ == "__main__":
    build()

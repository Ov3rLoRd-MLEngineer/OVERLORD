"""
setup.py — Ov3rLoRd Pipeline
Deploiement/redemarrage sur une nouvelle machine ou apres changement de disque.

Detecte les disques disponibles, localise ou demande l'emplacement de
l'installation ComfyUI, propose de recuperer des donnees existantes
(anciens datasets/checkpoints SegNet trouves sur un autre disque) plutot
que de repartir de zero, ecrit la configuration resultante dans .env
(lu par config.py), puis valide que les chemins essentiels existent.

Usage :
    py -3.12 setup.py                          interactif
    py -3.12 setup.py --check                  validation seule, n'ecrit rien
    py -3.12 setup.py --comfyui-root PATH --yes non-interactif (scripts/CI)
"""

import argparse
import shutil
import string
import subprocess
import sys
from pathlib import Path

try:
    import psutil
    HAS_PSUTIL = True
except ImportError:
    HAS_PSUTIL = False

REPO_ROOT = Path(__file__).resolve().parent
DEFAULT_ENV_PATH = REPO_ROOT / ".env"

SEGNET_PROJECTS = ["footsegnet", "handsegnet", "facesegnet", "bodysegnet"]
DATASET_SUBDIRS = ["raw", "images", "masks", "masks_raw", "premasks"]


# ── Detection disques ────────────────────────────────────────────────────────

def list_drives():
    """Liste les lecteurs disponibles avec espace libre/total (Go)."""
    drives = []
    if HAS_PSUTIL:
        for part in psutil.disk_partitions(all=False):
            try:
                usage = psutil.disk_usage(part.mountpoint)
            except (PermissionError, OSError):
                continue
            drives.append({
                "mountpoint": part.mountpoint,
                "total_gb": usage.total / (1024 ** 3),
                "free_gb": usage.free / (1024 ** 3),
            })
    else:
        for letter in string.ascii_uppercase:
            root = Path(f"{letter}:/")
            if not root.exists():
                continue
            try:
                usage = shutil.disk_usage(root)
            except OSError:
                continue
            drives.append({
                "mountpoint": str(root),
                "total_gb": usage.total / (1024 ** 3),
                "free_gb": usage.free / (1024 ** 3),
            })
    return drives


# ── Detection ComfyUI ────────────────────────────────────────────────────────

def _looks_like_comfyui(path):
    """Un dossier ComfyUI plausible a models/ et (input/ ou output/)."""
    return (path / "models").is_dir() and ((path / "input").is_dir() or (path / "output").is_dir())


def _scan_for_comfyui(path, depth, candidates, seen):
    if depth < 0:
        return
    try:
        entries = list(path.iterdir())
    except (PermissionError, OSError):
        return
    for entry in entries:
        if not entry.is_dir():
            continue
        resolved = str(entry.resolve()).lower()
        if resolved in seen:
            continue
        if "comfyui" in entry.name.lower() and _looks_like_comfyui(entry):
            seen.add(resolved)
            candidates.append(entry)
        if depth > 0:
            _scan_for_comfyui(entry, depth - 1, candidates, seen)


def find_comfyui_candidates(drives, max_depth=3):
    """Cherche des dossiers ComfyUI plausibles sur les disques detectes."""
    candidates = []
    seen = set()
    for d in drives:
        _scan_for_comfyui(Path(d["mountpoint"]), max_depth, candidates, seen)
    return candidates


def validate_comfyui_root(path):
    """Verifie les sous-chemins essentiels sous COMFYUI_ROOT. Retourne (ok, manquants)."""
    path = Path(path)
    checks = {
        "models/checkpoints": path / "models" / "checkpoints",
        "models/loras": path / "models" / "loras",
        "models/sams/sam_vit_b_01ec64.pth": path / "models" / "sams" / "sam_vit_b_01ec64.pth",
        "input": path / "input",
        "output": path / "output",
    }
    missing = [name for name, p in checks.items() if not p.exists()]
    return (len(missing) == 0, missing)


# ── Recuperation de donnees existantes ───────────────────────────────────────

def dataset_is_empty(overlord_root, project_name):
    """Vrai si le dataset local du projet SegNet n'a que des .gitkeep (rien de reel)."""
    dataset_dir = Path(overlord_root) / project_name / "dataset"
    if not dataset_dir.exists():
        return True
    for sub in DATASET_SUBDIRS:
        d = dataset_dir / sub
        if not d.exists():
            continue
        for f in d.rglob("*"):
            if f.is_file() and f.name != ".gitkeep":
                return False
    return True


def find_data_sources(current_root, drives):
    """Cherche d'autres racines Ov3rLoRd (config.py + au moins un projet SegNet)
    sur les disques, en excluant la racine courante -- pour proposer une
    recuperation de donnees plutot qu'un depart a zero."""
    current_resolved = str(Path(current_root).resolve()).lower()
    candidates = []
    for d in drives:
        root = Path(d["mountpoint"])
        try:
            entries = list(root.iterdir())
        except (PermissionError, OSError):
            continue
        for entry in entries:
            if not entry.is_dir():
                continue
            if str(entry.resolve()).lower() == current_resolved:
                continue
            if (entry / "config.py").exists() and any((entry / p).is_dir() for p in SEGNET_PROJECTS):
                candidates.append(entry)
    return candidates


def link_or_copy_dir(source, dest, mode="link"):
    """Recupere un dossier de donnees depuis une ancienne installation.
    mode='link' : jonction Windows (mklink /J) -- pas d'espace disque double,
                  pas de droits admin requis (contrairement a un symlink).
    mode='copy' : copie reelle (shutil.copytree) -- plus lent, double l'espace.
    Retourne (ok, message)."""
    source, dest = Path(source), Path(dest)
    if not source.exists():
        return False, f"source introuvable : {source}"
    if dest.exists():
        return False, f"destination deja existante, non ecrasee : {dest}"
    dest.parent.mkdir(parents=True, exist_ok=True)

    if mode == "link":
        result = subprocess.run(
            ["cmd", "/c", "mklink", "/J", str(dest), str(source)],
            capture_output=True, text=True,
        )
        if result.returncode == 0:
            return True, f"jonction creee : {dest} -> {source}"
        return False, f"echec jonction ({result.stderr.strip()}), essayer mode='copy'"

    try:
        shutil.copytree(source, dest)
        return True, f"copie : {source} -> {dest}"
    except OSError as e:
        return False, f"echec copie : {e}"


# ── Ecriture .env ─────────────────────────────────────────────────────────────

def write_env(updates, env_path=DEFAULT_ENV_PATH):
    """Met a jour les cles de `updates` dans .env, en preservant toutes les
    autres lignes existantes (secrets inclus). Ne supprime jamais une ligne
    qui n'est pas explicitement remplacee."""
    lines = []
    if env_path.exists():
        lines = env_path.read_text(encoding="utf-8").splitlines()

    new_lines = []
    seen = set()
    for line in lines:
        stripped = line.strip()
        if "=" in stripped and not stripped.startswith("#"):
            key = stripped.split("=", 1)[0].strip()
            if key in updates:
                new_lines.append(f"{key}={updates[key]}")
                seen.add(key)
                continue
        new_lines.append(line)

    for key, val in updates.items():
        if key not in seen:
            new_lines.append(f"{key}={val}")

    env_path.write_text("\n".join(new_lines) + "\n", encoding="utf-8")


# ── Validation finale ─────────────────────────────────────────────────────────

def validate_all():
    """Reimporte config.py a chaud (apres ecriture de .env) et verifie
    l'existence des chemins essentiels. Retourne {nom: (chemin, existe)}."""
    import importlib
    if "config" in sys.modules:
        del sys.modules["config"]
    sys.path.insert(0, str(REPO_ROOT))
    import config as _config

    checks = {
        "OVERLORD_ROOT": _config.OVERLORD_ROOT,
        "COMFYUI_ROOT": _config.COMFYUI_ROOT,
        "COMFYUI_INPUT": _config.COMFYUI_INPUT,
        "COMFYUI_OUTPUT": _config.COMFYUI_OUTPUT,
        "CHECKPOINTS_DIR": _config.CHECKPOINTS_DIR,
        "SAM_CHECKPOINT": _config.SAM_CHECKPOINT,
    }
    return {name: (path, Path(path).exists()) for name, path in checks.items()}


# ── CLI ────────────────────────────────────────────────────────────────────────

def _ask(prompt, default_yes=True):
    suffix = "[O/n]" if default_yes else "[o/N]"
    resp = input(f"{prompt} {suffix} ").strip().lower()
    if not resp:
        return default_yes
    return resp in ("o", "oui", "y", "yes")


def main():
    parser = argparse.ArgumentParser(description="Ov3rLoRd -- setup/deploiement")
    parser.add_argument("--check", action="store_true",
                         help="Validation seule (n'ecrit rien, n'invite a rien)")
    parser.add_argument("--comfyui-root", type=str, default=None,
                         help="Force le chemin ComfyUI sans invite interactive")
    parser.add_argument("--yes", action="store_true",
                         help="Repond oui automatiquement aux confirmations (non-interactif)")
    parser.add_argument("--no-recover", action="store_true",
                         help="Ne propose pas la recuperation de donnees existantes")
    args = parser.parse_args()

    print("=" * 66)
    print("  Ov3rLoRd -- Setup / Deploiement")
    print("=" * 66)
    print(f"  OVERLORD_ROOT (auto-detecte) : {REPO_ROOT}")
    print()

    if args.check:
        results = validate_all()
        ok = True
        for name, (path, exists) in results.items():
            status = "OK" if exists else "MANQUANT"
            if not exists:
                ok = False
            print(f"  [{status:8}] {name:16} {path}")
        sys.exit(0 if ok else 1)

    # 1. Disques disponibles
    drives = list_drives()
    print(f"  Disques detectes : {len(drives)}")
    for d in drives:
        print(f"    {d['mountpoint']:8} {d['free_gb']:.1f} Go libres / {d['total_gb']:.1f} Go")
    print()

    # 2. COMFYUI_ROOT
    if args.comfyui_root:
        comfyui_root = Path(args.comfyui_root)
    else:
        from config import COMFYUI_ROOT as current_comfyui_root
        if current_comfyui_root.exists() and validate_comfyui_root(current_comfyui_root)[0]:
            print(f"  ComfyUI deja configure et valide : {current_comfyui_root}")
            keep = args.yes or _ask("  Garder cet emplacement ?")
            comfyui_root = current_comfyui_root if keep else None
        else:
            comfyui_root = None

        if comfyui_root is None:
            print("  Recherche de ComfyUI sur les disques disponibles...")
            candidates = find_comfyui_candidates(drives)
            if candidates:
                print(f"  {len(candidates)} candidat(s) trouve(s) :")
                for i, c in enumerate(candidates):
                    print(f"    [{i}] {c}")
                if args.yes:
                    comfyui_root = candidates[0]
                else:
                    choice = input("  Numero a utiliser (ou chemin personnalise) : ").strip()
                    comfyui_root = candidates[int(choice)] if choice.isdigit() else Path(choice)
            else:
                print("  Aucun candidat trouve automatiquement.")
                if args.yes:
                    print("  [ERR] --yes sans --comfyui-root et aucun candidat trouve.")
                    sys.exit(1)
                comfyui_root = Path(input("  Chemin de l'installation ComfyUI : ").strip())

    ok, missing = validate_comfyui_root(comfyui_root)
    if not ok:
        print(f"  [WARN] Sous-dossiers manquants sous {comfyui_root} : {', '.join(missing)}")
        if not (args.yes or _ask("  Continuer quand meme ?", default_yes=False)):
            sys.exit(1)
    else:
        print(f"  [OK] {comfyui_root} valide (models/checkpoints, loras, sams, input, output)")
    print()

    # 3. Recuperation de donnees existantes (datasets/checkpoints SegNet)
    if not args.no_recover:
        empty_projects = [p for p in SEGNET_PROJECTS if dataset_is_empty(REPO_ROOT, p)]
        if empty_projects:
            print(f"  Datasets vides (nouvelle installation) : {', '.join(empty_projects)}")
            sources = find_data_sources(REPO_ROOT, drives)
            if sources:
                print(f"  {len(sources)} ancienne(s) installation(s) Ov3rLoRd trouvee(s) :")
                for i, s in enumerate(sources):
                    print(f"    [{i}] {s}")
                use_source = None
                if args.yes:
                    use_source = sources[0]
                elif _ask("  Recuperer les donnees depuis l'une d'elles ?", default_yes=False):
                    choice = input("  Numero a utiliser : ").strip()
                    if choice.isdigit():
                        use_source = sources[int(choice)]
                if use_source:
                    for proj in empty_projects:
                        src_dataset = use_source / proj / "dataset"
                        if not src_dataset.exists():
                            continue
                        dest_dataset = REPO_ROOT / proj / "dataset"
                        mode = "link"
                        ok, msg = link_or_copy_dir(src_dataset, dest_dataset, mode=mode)
                        print(f"    [{proj}] {msg}")
        print()

    # 4. Ecriture .env
    updates = {"COMFYUI_ROOT": str(comfyui_root)}
    write_env(updates)
    print(f"  [OK] .env mis a jour : COMFYUI_ROOT={comfyui_root}")
    print()

    # 5. Validation finale
    print("  Validation finale :")
    results = validate_all()
    all_ok = True
    for name, (path, exists) in results.items():
        status = "OK" if exists else "MANQUANT"
        if not exists:
            all_ok = False
        print(f"    [{status:8}] {name:16} {path}")

    print()
    if all_ok:
        print("  Setup termine -- tous les chemins essentiels existent.")
        sys.exit(0)
    else:
        print("  [ERR] Setup incomplet -- des chemins essentiels sont manquants.")
        sys.exit(1)


if __name__ == "__main__":
    main()

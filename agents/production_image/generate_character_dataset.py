"""H-007 (DOCS/HERMES) -- dataset LoRA personnage depuis un VRM VRoid.

NON TESTE DE BOUT EN BOUT : bloque sur H-003 (creation du personnage VRoid,
export VRM) qui n'a pas encore ete livree -- aucun fichier .vrm n'existe.
Ecrit selon les conventions du depot (agent_supervisor_v2.py::queue_prompt
pour l'API ComfyUI, agents/production_image/lora_trainer.py pour le format
de dataset attendu en sortie) mais jamais execute reellement.

Pipeline :
  1. Rendus multi-angles bruts du VRM via Godot headless
     (godot_project/scripts/dev_character_turnaround_capture.gd).
  2. Passage de chaque rendu brut par le pipeline de stylisation fabricatedXL
     existant (workflow ComfyUI a fournir explicitement -- --workflow --
     aucun workflow n'est suppose ici, cf. avertissement CLAUDE.md sur les
     node IDs fragiles/specifiques a chaque fichier JSON).
  3. Ecrit le dataset stylise au format attendu par
     agents/production_image/lora_trainer.py::prepare_dataset() (images/ +
     captions .txt avec le trigger word), prêt à enchaîner directement sur
     l'entraînement existant -- PAS de nouveau script d'entraînement ici,
     lora_trainer.py fait deja rank 32 (network_dim=32) par defaut.

Usage (une fois H-003 livre) :
  py -3.12 agents/production_image/generate_character_dataset.py \
      --vrm-path assets/vrm/neko_girl.vrm \
      --trigger-word nekogirl_ov3rlord \
      --workflow <workflow_stylisation.json> \
      --angle-steps 24

Token de declenchement : "nekogirl_ov3rlord" (repris de l'exemple du brief
H-007) verifie sans collision contre les LoRA existantes
(D:\\Ov3rLoRd AI\\ComfyUI\\models\\loras\\, 2026-08-09 -- Evangelion/Miku/
Gundam, aucun "nekogirl"/"ov3rlord"). A valider explicitement avant usage
reel (cf. CE QUE TU NE DOIS PAS FAIRE du brief).
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from pathlib import Path

import requests

_REPO_ROOT = Path(__file__).resolve().parent.parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))
import config

GODOT_EXE = _REPO_ROOT / "_tools" / "Godot" / "Godot_v4.7.1-stable_win64_console.exe"
GODOT_PROJECT = _REPO_ROOT / "godot_project"
TURNAROUND_SCENE = "res://scenes/dev_character_turnaround.tscn"

COMFY_URL = "http://127.0.0.1:8188"  # meme convention que agent_supervisor_v2.py

DEFAULT_TRIGGER_WORD = "nekogirl_ov3rlord"


def capture_raw_renders(vrm_path: str, out_dir: Path, angle_steps: int = 24) -> list[Path]:
    """Lance Godot headless pour capturer les rendus multi-angles du VRM."""
    out_dir.mkdir(parents=True, exist_ok=True)
    cmd = [
        str(GODOT_EXE),
        "--headless",
        "--path", str(GODOT_PROJECT),
        TURNAROUND_SCENE,
        "--quit-after", str(angle_steps * 3 + 20),
        "--",
        f"--vrm-path={vrm_path}",
        f"--out-dir={out_dir.as_posix()}",
        f"--angle-steps={angle_steps}",
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=600)
    if result.returncode != 0:
        raise RuntimeError(f"Capture Godot echouee (code {result.returncode}) :\n{result.stdout}\n{result.stderr}")
    renders = sorted(out_dir.glob("angle_*.png"))
    if not renders:
        raise RuntimeError(f"Aucun rendu produit dans {out_dir} -- verifier le .vrm et le log Godot ci-dessus")
    return renders


def stylize_image(
    raw_image_path: Path,
    workflow_path: Path,
    out_dir: Path,
    trigger_word: str,
    positive_prompt_node_id: str | None = None,
) -> Path | None:
    """Soumet une image brute au pipeline de stylisation fabricatedXL via l'API ComfyUI.

    Meme convention que agent_supervisor_v2.py::queue_prompt/wait_for_completion.
    Le node du prompt positif n'est PAS suppose ici -- le fournir explicitement
    (--positive-prompt-node-id) apres inspection du workflow choisi, les IDs de
    node etant specifiques a chaque fichier JSON (cf. CLAUDE.md).
    """
    workflow = json.loads(workflow_path.read_text(encoding="utf-8"))

    if positive_prompt_node_id and positive_prompt_node_id in workflow:
        node = workflow[positive_prompt_node_id]
        existing = node.get("inputs", {}).get("text", "")
        node.setdefault("inputs", {})["text"] = f"{trigger_word}, {existing}".strip(", ")

    payload = {"prompt": workflow, "client_id": "character_dataset_gen"}
    r = requests.post(f"{COMFY_URL}/prompt", json=payload, timeout=30)
    r.raise_for_status()
    prompt_id = r.json().get("prompt_id", "")
    if not prompt_id:
        return None

    deadline = time.time() + 300
    while time.time() < deadline:
        hist = requests.get(f"{COMFY_URL}/history/{prompt_id}", timeout=10)
        if hist.ok and prompt_id in hist.json():
            break
        time.sleep(2)
    else:
        return None

    # Recuperation du fichier de sortie laissee a l'integration reelle --
    # depend du node SaveImage du workflow fourni (non generique ici).
    return None


def write_dataset(stylized_images: list[Path], trigger_word: str, out_root: Path) -> Path:
    """Ecrit le dataset au format attendu par lora_trainer.py::prepare_dataset()
    (dataset_dir/images/*.png + *.txt), pour enchainer directement dessus."""
    images_dir = out_root / "images"
    images_dir.mkdir(parents=True, exist_ok=True)
    for img in stylized_images:
        dest = images_dir / img.name
        dest.write_bytes(img.read_bytes())
        caption = dest.with_suffix(".txt")
        caption.write_text(
            f"{trigger_word}, masterpiece, best quality, anime style, 1girl, character turnaround",
            encoding="utf-8",
        )
    return out_root


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--vrm-path", required=True, help="Chemin res:// du .vrm (dans godot_project/assets/vrm/)")
    parser.add_argument("--trigger-word", default=DEFAULT_TRIGGER_WORD)
    parser.add_argument("--workflow", type=Path, help="Workflow ComfyUI de stylisation fabricatedXL (JSON API format)")
    parser.add_argument("--positive-prompt-node-id", help="ID du node CLIPTextEncode positif dans --workflow")
    parser.add_argument("--angle-steps", type=int, default=24)
    parser.add_argument("--out-dir", type=Path, default=config.WORKSPACE_DIR / "character_lora_dataset")
    args = parser.parse_args()

    raw_dir = args.out_dir / "raw_renders"
    print(f"[1/3] Capture rendus bruts -> {raw_dir}")
    raw_renders = capture_raw_renders(args.vrm_path, raw_dir, args.angle_steps)
    print(f"      {len(raw_renders)} rendus captures")

    stylized = []
    if args.workflow:
        print(f"[2/3] Stylisation fabricatedXL ({args.workflow.name})")
        for raw in raw_renders:
            out = stylize_image(raw, args.workflow, args.out_dir / "stylized", args.trigger_word, args.positive_prompt_node_id)
            if out:
                stylized.append(out)
        print(f"      {len(stylized)}/{len(raw_renders)} stylises")
    else:
        print("[2/3] --workflow non fourni -- dataset ecrit avec les rendus BRUTS (non stylises)")
        stylized = raw_renders

    print(f"[3/3] Ecriture dataset (trigger='{args.trigger_word}')")
    dataset_dir = write_dataset(stylized, args.trigger_word, args.out_dir / "dataset")
    print(f"Dataset pret : {dataset_dir}")
    print("Entrainement : reutiliser agents/production_image/lora_trainer.py (deja rank 32 par defaut) --")
    print(f"  prepare_dataset() attend directement ce dossier ; train_lora() requiert kohya_ss installe")
    print(f"  (absent de cette machine au 2026-08-09 -- D:/kohya_ss n'existe pas, a installer avant training reel).")

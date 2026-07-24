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
patch_workflow_v35.py -- Ov3rLoRd V1.49
Remplace les noeuds LoraManager par des equivalents natifs ComfyUI.
Usage : python patch_workflow_v35.py
Backup automatique avant modification.
"""

import json
import copy
import shutil
import sys
from pathlib import Path
from datetime import datetime

WORKFLOW_FILE = Path("Combined_V35_API.json")
BACKUP_DIR    = Path("workspace/backups")


def backup(src: Path) -> Path:
    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    ts   = datetime.now().strftime("%Y%m%d_%H%M%S")
    dest = BACKUP_DIR / f"{src.stem}_{ts}.json"
    shutil.copy2(src, dest)
    return dest


def patch(wf: dict) -> dict:
    wf = copy.deepcopy(wf)

    # ── Node 62 : Lora Loader (LoraManager) -> LoraLoader natif ──────
    # Slots aval : 0=MODEL, 1=CLIP, 2=trigger_text(->97), 3=trigger_text(->105)
    wf["62"] = {
        "inputs": {
            "lora_name":      "",
            "strength_model": 1.0,
            "strength_clip":  1.0,
            "model": ["108", 0],
            "clip":  ["86",  0],
        },
        "class_type": "LoraLoader",
        "_meta": {"title": "Lora Loader [patched]"},
    }

    # Node 9001 : placeholder texte vide pour slots 2 et 3 de l'ancien 62
    wf["9001"] = {
        "inputs": {},
        "class_type": "PrimitiveNode",
        "_meta": {"title": "TriggerWords Placeholder A"},
    }
    wf["97"]["inputs"]["trigger_words"]  = ["9001", 0]
    wf["105"]["inputs"]["string_b"]      = ["9001", 0]

    # ── Node 303 : Lora Loader (LoraManager) -> LoraLoader natif ─────
    # Slots aval : 0=MODEL, 1=CLIP, 2=trigger_text(->369)
    wf["303"] = {
        "inputs": {
            "lora_name":      "",
            "strength_model": 1.0,
            "strength_clip":  1.0,
            "model": ["395", 0],
            "clip":  ["349", 0],
        },
        "class_type": "LoraLoader",
        "_meta": {"title": "Lora Loader Det [patched]"},
    }

    # Node 9002 : placeholder texte vide pour slot 2 de l'ancien 303
    wf["9002"] = {
        "inputs": {},
        "class_type": "PrimitiveNode",
        "_meta": {"title": "TriggerWords Placeholder B"},
    }
    wf["369"]["inputs"]["trigger_words"] = ["9002", 0]

    # ── Node 97 : TriggerWord Toggle -> PrimitiveNode texte vide ─────
    # Sortie slot 0 -> nodes 87 (string_a) et 99 (string_b)
    wf["97"] = {
        "inputs": {},
        "class_type": "PrimitiveNode",
        "_meta": {"title": "TriggerWord Toggle [patched]"},
    }

    # ── Node 369 : TriggerWord Toggle -> PrimitiveNode texte vide ────
    # Sortie slot 0 -> node 408 (string_a)
    wf["369"] = {
        "inputs": {},
        "class_type": "PrimitiveNode",
        "_meta": {"title": "TriggerWord Toggle Det [patched]"},
    }

    return wf


def validate(wf: dict):
    errors = []
    lora_mgr = [k for k, v in wf.items()
                if "LoraManager" in str(v.get("class_type", ""))
                or "TriggerWord" in str(v.get("class_type", ""))]
    if lora_mgr:
        errors.append(f"LoraManager restants : {lora_mgr}")

    null_ct = [k for k, v in wf.items() if v.get("class_type") is None]
    if null_ct:
        errors.append(f"class_type None : {null_ct}")

    expected = ["62", "87", "99", "111", "112", "75", "77",
                "334", "303", "382", "301", "380", "68"]
    missing  = [n for n in expected if n not in wf]
    if missing:
        errors.append(f"Node IDs manquants : {missing}")

    return errors


def main():
    if not WORKFLOW_FILE.exists():
        print(f"[ERREUR] {WORKFLOW_FILE} introuvable a la racine.")
        sys.exit(1)

    print(f"[BACKUP] {WORKFLOW_FILE} ...", end=" ")
    bk = backup(WORKFLOW_FILE)
    print(f"OK -> {bk}")

    wf_raw = json.loads(WORKFLOW_FILE.read_text(encoding="utf-8"))
    print(f"[PATCH] Application du patch LoraManager ...")
    wf_patched = patch(wf_raw)

    errors = validate(wf_patched)
    if errors:
        print("[ERREUR] Validation echouee :")
        for e in errors:
            print(f"  - {e}")
        sys.exit(1)

    WORKFLOW_FILE.write_text(
        json.dumps(wf_patched, indent=2, ensure_ascii=False),
        encoding="utf-8"
    )
    print(f"[OK] {WORKFLOW_FILE} patche et valide.")
    print(f"     {len(wf_patched)} noeuds | 0 LoraManager | 0 class_type None")
    print(f"[INFO] Pour restaurer : copier {bk.name} depuis workspace/backups/")


if __name__ == "__main__":
    main()

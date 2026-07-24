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
update_checkpoint.py — Met à jour le checkpoint dans Combined_V35_API.json
Usage : python update_checkpoint.py "noobaiXLNSFWPony_epsilonPred10.safetensors"
"""
import sys, json
from pathlib import Path

if len(sys.argv) < 2:
    print("Usage: python update_checkpoint.py <nom_du_checkpoint.safetensors>")
    print("Exemple: python update_checkpoint.py noobaiXLNSFWPony_epsilonPred10.safetensors")
    sys.exit(1)

new_ckpt = sys.argv[1]
wf_file  = Path("Combined_V35_API.json")

if not wf_file.exists():
    print(f"Fichier non trouvé : {wf_file}")
    sys.exit(1)

with open(wf_file, encoding="utf-8") as f:
    wf = json.load(f)

updated = 0
for nid, node in wf.items():
    if node.get("class_type") == "CheckpointLoaderSimple":
        old = node["inputs"].get("ckpt_name","")
        node["inputs"]["ckpt_name"] = new_ckpt
        print(f"Nœud {nid} : {old} → {new_ckpt}")
        updated += 1

with open(wf_file, "w", encoding="utf-8") as f:
    json.dump(wf, f, indent=2, ensure_ascii=False)

# Mettre à jour aussi le modelname dans Image Saver
for nid, node in wf.items():
    if node.get("class_type") == "Image Saver":
        stem = Path(new_ckpt).stem
        node["inputs"]["modelname"] = stem
        print(f"Nœud {nid} modelname → {stem}")

with open(wf_file, "w", encoding="utf-8") as f:
    json.dump(wf, f, indent=2, ensure_ascii=False)

print(f"\n✓ {updated} checkpoint(s) mis à jour dans {wf_file}")

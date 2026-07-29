"""Lance train_control_lora.py (celui DE CE WORKTREE, avec les modifications
en cours de revue) contre le dataset/output du checkout principal.

Necessaire uniquement parce que cette session tourne dans un git worktree
isole : CN_DATASET_ROOT/DEFAULT_OUTPUT dans train_control_lora.py sont
calcules a partir de __file__ (donc pointent vers footsegnet/controlnet/dataset
DE CE WORKTREE, vide -- dataset/checkpoints sont gitignores et n'existent que
dans D:\\OVERLORD\\footsegnet\\controlnet). Repointe ces deux constantes AVANT
d'appeler train() -- ne modifie pas train_control_lora.py lui-meme (qui reste
correct et autonome quand execute depuis le checkout principal).

Usage : identique a train_control_lora.py, ex.
    py -3.12 diagnostics/run_train_worktree.py --test-run --max-train-steps 5 \
        --contrastive-weight 1.0 --output-dir <chemin absolu>
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import train_control_lora as tcl   # noqa: E402

MAIN_CONTROLNET_ROOT = Path("D:/OVERLORD/footsegnet/controlnet")
tcl.CN_DATASET_ROOT = MAIN_CONTROLNET_ROOT / "dataset"
tcl.DEFAULT_MANIFEST = tcl.CN_DATASET_ROOT / "manifest_filtered.jsonl"
tcl.DEFAULT_OUTPUT = MAIN_CONTROLNET_ROOT / "output" / "control_lora_v1"

if __name__ == "__main__":
    tcl.train(tcl.parse_args())

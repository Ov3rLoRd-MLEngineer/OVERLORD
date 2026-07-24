# convert_to_safetensors.py — FootSegNet
#
# Convertit un checkpoint .pth (torch.save(state_dict)) en .safetensors,
# pour publication HuggingFace (format recommandé : pas de pickle, chargement
# memory-mapped, pas d'exécution de code arbitraire à l'inférence).
#
# Le state_dict de FootSegNet (torch.nn.Module.state_dict() de segment_anything)
# est un simple OrderedDict[str, Tensor] : la conversion est sans perte, bit à
# bit identique aux tensors d'origine (pas de quantification/compression).
#
# Usage :
#   py -3.12 convert_to_safetensors.py
#   py -3.12 convert_to_safetensors.py --input ..\checkpoints\footsegnet_vit_b_best.pth --output footsegnet_vit_b_best.safetensors
#   py -3.12 convert_to_safetensors.py --verify   (recharge et compare tensor par tensor)

import argparse
from pathlib import Path

import torch
from safetensors.torch import save_file, load_file

DEFAULT_INPUT  = Path(__file__).resolve().parent.parent / "checkpoints" / "footsegnet_vit_b_best.pth"
DEFAULT_OUTPUT = Path(__file__).resolve().parent / "footsegnet_vit_b_best.safetensors"


def convert(input_path: Path, output_path: Path, verify: bool) -> None:
    if not input_path.exists():
        raise FileNotFoundError(f"Checkpoint introuvable : {input_path}")

    print(f"[convert] Chargement {input_path} ...")
    state_dict = torch.load(str(input_path), map_location="cpu", weights_only=True)

    if not isinstance(state_dict, dict):
        raise TypeError(
            "Le fichier .pth ne contient pas un state_dict brut (dict[str, Tensor]) — "
            "vérifier s'il s'agit d'un checkpoint complet (avec optimizer, epoch, etc.) "
            "et extraire la clé appropriée (ex: ckpt['model_state_dict']) avant conversion."
        )

    # safetensors refuse les tensors qui partagent le même stockage mémoire
    # (ça arrive avec certains buffers liés/tied weights) — on clone
    # systématiquement pour repartir d'un stockage propre par tensor.
    tensors = {k: v.clone().contiguous() for k, v in state_dict.items()}

    n_params = sum(t.numel() for t in tensors.values())
    print(f"[convert] {len(tensors)} tenseurs, {n_params / 1e6:.1f}M paramètres")

    output_path.parent.mkdir(parents=True, exist_ok=True)
    save_file(tensors, str(output_path), metadata={"format": "pt"})
    print(f"[convert] -> {output_path}  ({output_path.stat().st_size / 1e6:.1f} MB)")

    if verify:
        print("[convert] Vérification (recharge + comparaison bit à bit)...")
        reloaded = load_file(str(output_path))
        assert set(reloaded.keys()) == set(tensors.keys()), "Clés différentes après recharge"
        for k in tensors:
            if not torch.equal(reloaded[k], tensors[k]):
                raise AssertionError(f"Tenseur différent après conversion : {k}")
        print("[convert] OK — conversion sans perte confirmée (tous les tenseurs identiques).")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="FootSegNet — conversion checkpoint .pth vers .safetensors")
    parser.add_argument("--input",  type=Path, default=DEFAULT_INPUT,
                        help=f"Checkpoint source (défaut: {DEFAULT_INPUT})")
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT,
                        help=f"Fichier .safetensors de sortie (défaut: {DEFAULT_OUTPUT})")
    parser.add_argument("--verify", action="store_true",
                        help="Recharge le fichier produit et compare chaque tenseur à l'original")
    args = parser.parse_args()

    convert(args.input, args.output, args.verify)

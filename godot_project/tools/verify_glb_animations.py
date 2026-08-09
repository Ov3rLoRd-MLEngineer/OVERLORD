"""H-005 (DOCS/HERMES) -- verification post-export d'un GLB Godot.

Le point critique documente dans le brief H-005 est que l'export glTF runtime
de Godot peut omettre silencieusement des pistes d'animation. Ce script ouvre
le .glb produit et confirme explicitement la presence (ou l'absence) de
canaux d'animation cibles sur les joints du squelette -- pas une supposition.

Usage :
    py -3.12 godot_project/tools/verify_glb_animations.py <chemin.glb>
"""

from __future__ import annotations

import sys

from pygltflib import GLTF2


def verify(glb_path: str) -> bool:
    gltf = GLTF2().load(glb_path)

    print(f"Fichier : {glb_path}")
    print(f"Nodes   : {len(gltf.nodes or [])}")
    print(f"Skins   : {len(gltf.skins or [])}")
    print(f"Animations : {len(gltf.animations or [])}")

    if not gltf.animations:
        print("VERDICT: seam glTF confirme -- aucune animation dans le GLB exporte.")
        return False

    node_names = {i: (n.name or f"node_{i}") for i, n in enumerate(gltf.nodes or [])}
    ok = True
    for anim_idx, anim in enumerate(gltf.animations):
        print(f"\nAnimation [{anim_idx}] '{anim.name}' -- {len(anim.channels)} canal/canaux")
        if not anim.channels:
            print("  VIDE -- aucune piste malgre l'entree d'animation presente.")
            ok = False
            continue
        for ch in anim.channels:
            target_node = ch.target.node
            target_path = ch.target.path
            name = node_names.get(target_node, f"node_{target_node}")
            print(f"  -> cible: '{name}' (node {target_node}), propriete: {target_path}")

    print(f"\nVERDICT: {'export animations OK' if ok else 'seam glTF confirme, bascule VMC recommandee'}")
    return ok


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print(__doc__)
        sys.exit(2)
    success = verify(sys.argv[1])
    sys.exit(0 if success else 1)

"""
agents/workflow_organizer.py — Agent Organisateur de Workflow ComfyUI
Convertit le format API (dict plat) en format Canvas organisé visuellement
avec des groupes colorés, des blocs logiques et un ordonnancement propre.

Résultat : un fichier .json ouvrable dans ComfyUI avec :
  - Blocs colorés (groups) regroupant les nœuds par fonction
  - Positions calculées automatiquement de gauche à droite
  - Sous-blocs imbriqués (ex: Advanced → KSampler / Advanced → FaceDetailer)
  - Connexions (links) reconstruites depuis les inputs
  - Nœuds collapsed pour les éléments secondaires

Usage :
  python agents/workflow_organizer.py Combined_V35_API.json
  → génère Combined_V35_CANVAS.json ouvrable dans ComfyUI
"""

import json
import sys
import logging
from pathlib import Path
from datetime import datetime

# ── Palette de couleurs par catégorie ────────────────────────────────
COLORS = {
    "model":       "#3D5A80",   # Bleu ardoise — checkpoint/LoRA
    "sampling":    "#5C4033",   # Brun chaud   — KSampler / paramètres
    "prompt":      "#2D6A4F",   # Vert forêt   — CLIP / texte
    "detailer":    "#6B4226",   # Brun terre   — FaceDetailer / Mask
    "routing":     "#444444",   # Gris foncé   — Switch / Reroute
    "output":      "#1B4332",   # Vert foncé   — Image Saver / preview
    "utility":     "#3D405B",   # Bleu nuit    — Math / String / Misc
    "seed":        "#4A1942",   # Violet foncé — Seeds
    "detection":   "#7B2D00",   # Orange brun  — YOLO / SAM
    "advanced":    "#023E8A",   # Bleu roi     — bloc Advanced complet
    "detailer_wf": "#5F0F40",   # Bordeaux     — bloc Detailer complet
    "control":     "#1A472A",   # Vert foncé   — centre de contrôle
}

# ── Blocs logiques du workflow ────────────────────────────────────────
# Chaque bloc définit : titre, couleur, nœuds qu'il contient
BLOCKS = [
    {
        "title":   "🎛 Centre de Contrôle",
        "color":   COLORS["control"],
        "col":     0,
        "nodes":   ["112", "75", "77", "83", "64", "80"],
        "sub":     [
            {"title": "Seed & Dimensions", "nodes": ["112","75","77","83"]},
            {"title": "Paramètres Sampler", "nodes": ["64","80"]},
        ]
    },
    {
        "title":   "🤖 Modèle Principal",
        "color":   COLORS["model"],
        "col":     1,
        "nodes":   ["108","86","62","97"],
        "sub":     [
            {"title": "Checkpoint", "nodes": ["108"]},
            {"title": "CLIP & LoRA", "nodes": ["86","62","97"]},
        ]
    },
    {
        "title":   "✍ Prompts & Texte",
        "color":   COLORS["prompt"],
        "col":     2,
        "nodes":   ["87","99","98","101","103","105","107","111"],
        "sub":     [
            {"title": "Prompt Positif",    "nodes": ["87","99","98","101","103"]},
            {"title": "CLIP Encodage",     "nodes": ["107","111"]},
            {"title": "Concaténation",     "nodes": ["105"]},
        ]
    },
    {
        "title":   "⚡ Génération SDXL",
        "color":   COLORS["sampling"],
        "col":     3,
        "nodes":   ["68","24","100","102","104","116","106","85"],
        "sub":     [
            {"title": "Latent & Switch",   "nodes": ["102","104","100"]},
            {"title": "Modèle Switch",     "nodes": ["68","24"]},
            {"title": "KSampler",          "nodes": ["116"]},
            {"title": "VAE Decode",        "nodes": ["106"]},
            {"title": "Switch Prompt",     "nodes": ["85"]},
        ]
    },
    {
        "title":   "👁 FaceDetailer (Advanced)",
        "color":   COLORS["detailer"],
        "col":     4,
        "nodes":   ["11","16","29","22","31","36","169","95"],
        "sub":     [
            {"title": "Détecteurs",        "nodes": ["16","29","11"]},
            {"title": "Pipe Detailer",     "nodes": ["22","31"]},
            {"title": "FaceDetailer",      "nodes": ["36"]},
            {"title": "Sortie & Preview",  "nodes": ["169","95"]},
        ]
    },
    {
        "title":   "🏭 Image Saver",
        "color":   COLORS["output"],
        "col":     5,
        "nodes":   ["70","72","76","84","88"],
        "sub": []
    },
    # ── Bloc Detailer (+300) ──
    {
        "title":   "🔬 Modèle Detailer",
        "color":   COLORS["model"],
        "col":     6,
        "nodes":   ["395","349","303","382","369"],
        "sub":     [
            {"title": "Checkpoint Detailer",  "nodes": ["395"]},
            {"title": "CLIP & LoRA Detailer", "nodes": ["349","303","369"]},
            {"title": "Seed Detailer",         "nodes": ["382"]},
        ]
    },
    {
        "title":   "✍ Prompts Detailer",
        "color":   COLORS["prompt"],
        "col":     7,
        "nodes":   ["301","380","407","408","414","415","312","398"],
        "sub":     [
            {"title": "CLIP Detailer",     "nodes": ["301","380"]},
            {"title": "Texte & Regex",     "nodes": ["407","408","414","415"]},
            {"title": "Paramètres",        "nodes": ["312","398"]},
        ]
    },
    {
        "title":   "🎯 Détection & Segmentation",
        "color":   COLORS["detection"],
        "col":     8,
        "nodes":   ["317","392","383","391"],
        "sub":     [
            {"title": "Détecteurs YOLO",   "nodes": ["317","392"]},
            {"title": "SAM Loader",        "nodes": ["383"]},
            {"title": "Reroute",           "nodes": ["391"]},
        ]
    },
    {
        "title":   "🔩 Pipeline Detailer",
        "color":   COLORS["detailer_wf"],
        "col":     9,
        "nodes":   ["393","394","401","403","405","406","409","410","416","396","397","399"],
        "sub":     [
            {"title": "Switches",          "nodes": ["393","394","401","403","405"]},
            {"title": "Pipes",             "nodes": ["409","410"]},
            {"title": "DiffDiff & Tailles","nodes": ["416","396","397","399"]},
            {"title": "Edit Pipe",         "nodes": ["406"]},
        ]
    },
    {
        "title":   "👁 FaceDetailer & Mask",
        "color":   COLORS["detailer"],
        "col":     10,
        "nodes":   ["331","359","339","423","334"],
        "sub":     [
            {"title": "Edit DetailerPipe", "nodes": ["331"]},
            {"title": "FaceDetailer Det.", "nodes": ["359"]},
            {"title": "MaskDetailer",      "nodes": ["339"]},
            {"title": "Sortie & Saver",    "nodes": ["423","334"]},
        ]
    },
]

# Nœuds dont la taille est réduite (collapsed)
COLLAPSE_IDS = {
    "70","72","76","84","88",   # primitives de taille
    "391",                       # Reroute
    "369",                       # TriggerWord Detailer
}

# Taille standard des nœuds en canvas
NODE_W = 240
NODE_H = 120
COL_W  = 280   # largeur d'une colonne
COL_H  = 140   # hauteur d'une ligne
GROUP_PAD = 30  # marge intérieure des groupes


class WorkflowOrganizer:
    """
    Convertit un workflow au format API ComfyUI en format Canvas
    avec des groupes visuels organisés.
    """

    def __init__(self, logger: logging.Logger = None):
        self.log = logger or logging.getLogger("wf_organizer")

    def api_to_canvas(self, api_workflow: dict,
                       original_canvas: dict = None) -> dict:
        """
        Convertit le format API (dict par ID) en format Canvas ComfyUI.

        api_workflow    : le Combined_V35_API.json
        original_canvas : le Advanced_QwenVL_V35.json (optionnel, pour récupérer
                          les connexions/links existants)

        Retourne un dict au format canvas ComfyUI.
        """
        self.log.info(f"[ORGANIZER] Conversion de {len(api_workflow)} nœuds...")

        # Construire l'index des positions
        positions = self._calculate_positions()

        # Construire les nœuds canvas
        canvas_nodes = []
        node_id_map  = {}  # str_id → int_id (pour les liens)

        for nid_str, node_data in api_workflow.items():
            nid_int = int(nid_str)
            pos     = positions.get(nid_str, [9999, 9999])
            size    = [NODE_W, 80] if nid_str in COLLAPSE_IDS else [NODE_W, NODE_H]

            canvas_node = {
                "id":            nid_int,
                "type":          node_data.get("class_type", "unknown"),
                "pos":           pos,
                "size":          size,
                "flags":         {"collapsed": nid_str in COLLAPSE_IDS},
                "order":         nid_int,
                "mode":          0,
                "inputs":        self._build_inputs(node_data),
                "outputs":       [],
                "properties":    {"Node name for S&R": node_data.get("class_type","")},
                "widgets_values": self._extract_widget_values(node_data),
                "_meta":         node_data.get("_meta", {"title": node_data.get("class_type","")}),
            }
            canvas_nodes.append(canvas_node)
            node_id_map[nid_str] = nid_int

        # Construire les liens
        links, link_id = self._build_links(api_workflow, node_id_map)

        # Construire les groupes visuels
        groups = self._build_groups(positions)

        # Assembler le canvas complet
        canvas = {
            "id":           1,
            "revision":     1,
            "last_node_id": max(int(nid) for nid in api_workflow.keys()) + 1,
            "last_link_id": link_id,
            "nodes":        canvas_nodes,
            "links":        links,
            "groups":       groups,
            "definitions":  {},
            "config":       {},
            "extra":        {
                "ds": {"scale": 0.5, "offset": [0, 0]},
                "_meta": {
                    "title":       "Ov3rLoRd — Combined V35",
                    "description": "Workflow fusionné Advanced + Detailer — OverLord Pipeline",
                    "version":     "1.0",
                    "organized_at": datetime.utcnow().isoformat(),
                }
            },
            "version":      0.4,
        }

        n_nodes  = len(canvas_nodes)
        n_groups = len(groups)
        n_links  = len(links)
        self.log.info(
            f"[ORGANIZER] ✓ Canvas généré — "
            f"{n_nodes} nœuds | {n_groups} groupes | {n_links} liens"
        )
        return canvas

    def _calculate_positions(self) -> dict:
        """Calcule les positions X,Y de chaque nœud dans le canvas."""
        positions = {}
        y_start   = 200

        for block in BLOCKS:
            col   = block["col"]
            x_base = col * (COL_W + 60) + 100
            nodes = block["nodes"]

            if block["sub"]:
                # Avec sous-blocs
                y_cur = y_start + GROUP_PAD
                for sub in block["sub"]:
                    for i, nid in enumerate(sub["nodes"]):
                        positions[nid] = [
                            x_base + GROUP_PAD,
                            y_cur + i * COL_H
                        ]
                    y_cur += len(sub["nodes"]) * COL_H + 40
            else:
                # Sans sous-blocs
                for i, nid in enumerate(nodes):
                    positions[nid] = [
                        x_base + GROUP_PAD,
                        y_start + GROUP_PAD + i * COL_H
                    ]

        return positions

    def _build_groups(self, positions: dict) -> list:
        """Génère les groupes visuels colorés pour ComfyUI."""
        groups = []
        gid    = 1

        for block in BLOCKS:
            nodes  = block["nodes"]
            color  = block["color"]
            col    = block["col"]
            x_base = col * (COL_W + 60) + 80

            # Calculer la bounding box du bloc
            node_positions = [positions[nid] for nid in nodes if nid in positions]
            if not node_positions:
                continue

            xs    = [p[0] for p in node_positions]
            ys    = [p[1] for p in node_positions]
            x_min = min(xs) - GROUP_PAD
            y_min = min(ys) - GROUP_PAD - 40  # espace pour le titre
            x_max = max(xs) + NODE_W + GROUP_PAD
            y_max = max(ys) + NODE_H + GROUP_PAD

            # Groupe principal
            groups.append({
                "id":       gid,
                "title":    block["title"],
                "bounding": [x_min, y_min, x_max - x_min, y_max - y_min],
                "color":    color,
                "flags":    {"pinned": True},
            })
            gid += 1

            # Sous-groupes
            if block.get("sub"):
                sub_y = y_min + 50
                for sub in block["sub"]:
                    sub_nodes = sub["nodes"]
                    sub_positions = [positions[nid] for nid in sub_nodes if nid in positions]
                    if not sub_positions:
                        continue
                    sy_min = min(p[1] for p in sub_positions) - 20
                    sy_max = max(p[1] for p in sub_positions) + NODE_H + 20
                    sx_min = x_min + 10
                    sx_max = x_max - 10

                    # Couleur légèrement plus claire pour les sous-groupes
                    sub_color = self._lighten_color(color)

                    groups.append({
                        "id":       gid,
                        "title":    sub["title"],
                        "bounding": [sx_min, sy_min, sx_max - sx_min, sy_max - sy_min],
                        "color":    sub_color,
                        "flags":    {"pinned": True},
                    })
                    gid += 1

        return groups

    def _lighten_color(self, hex_color: str) -> str:
        """Éclaircit légèrement une couleur hex pour les sous-groupes."""
        try:
            h  = hex_color.lstrip("#")
            r  = min(255, int(h[0:2], 16) + 30)
            g  = min(255, int(h[2:4], 16) + 30)
            b  = min(255, int(h[4:6], 16) + 30)
            return f"#{r:02x}{g:02x}{b:02x}"
        except Exception:
            return hex_color

    def _build_inputs(self, node_data: dict) -> list:
        """Construit la liste des inputs d'un nœud canvas depuis le format API."""
        inputs_api = node_data.get("inputs", {})
        canvas_inputs = []

        for name, value in inputs_api.items():
            if isinstance(value, list) and len(value) == 2:
                # Connexion vers un autre nœud : [node_id, slot]
                canvas_inputs.append({
                    "name":   name,
                    "type":   "*",
                    "link":   None,  # sera rempli par _build_links
                    "_src":   value,  # temporaire pour construction des liens
                })
            elif not name.startswith("__"):
                # Valeur widget (pas une connexion)
                canvas_inputs.append({
                    "name":  name,
                    "type":  "*",
                    "link":  None,
                })
        return canvas_inputs

    def _extract_widget_values(self, node_data: dict) -> list:
        """Extrait les valeurs widgets pour le format canvas."""
        values = []
        for name, value in node_data.get("inputs", {}).items():
            if name.startswith("__"):
                continue
            if not (isinstance(value, list) and len(value) == 2
                    and isinstance(value[0], str) and value[0].isdigit()):
                values.append(value)
        return values

    def _build_links(self, api_workflow: dict,
                      node_id_map: dict) -> tuple:
        """
        Reconstruit les liens (connexions) entre nœuds
        depuis les inputs du format API.

        Retourne (links_list, last_link_id)
        """
        links    = []
        link_id  = 1

        # Map nœud → liste de (slot_out, type_out)
        # On doit associer chaque output slot à son type
        # Approximation : on numérote les outputs dans l'ordre

        # D'abord, identifier tous les "sources" référencées
        # Format API input connexion : [str(src_node_id), slot_index]
        for dst_nid_str, dst_node in api_workflow.items():
            dst_nid_int = int(dst_nid_str)
            inputs      = dst_node.get("inputs", {})

            # Indexer les inputs pour trouver le slot destination
            slot_dst = 0
            for name, value in inputs.items():
                if name.startswith("__"):
                    continue

                if (isinstance(value, list) and len(value) == 2
                        and isinstance(value[0], str)
                        and value[0] in api_workflow):

                    src_nid_str = value[0]
                    src_slot    = int(value[1])
                    src_nid_int = int(src_nid_str)

                    # Déterminer le type depuis le class_type source
                    src_class   = api_workflow[src_nid_str].get("class_type", "")
                    link_type   = self._guess_link_type(src_class, src_slot, name)

                    link = [link_id, src_nid_int, src_slot,
                             dst_nid_int, slot_dst, link_type]
                    links.append(link)
                    link_id += 1

                slot_dst += 1

        return links, link_id

    def _guess_link_type(self, class_type: str,
                          src_slot: int, input_name: str) -> str:
        """
        Devine le type d'un lien depuis le class_type source
        et le nom de l'input destination.
        """
        name_l = input_name.lower()

        type_map = {
            "model":        "MODEL",
            "clip":         "CLIP",
            "vae":          "VAE",
            "conditioning": "CONDITIONING",
            "positive":     "CONDITIONING",
            "negative":     "CONDITIONING",
            "latent":       "LATENT",
            "image":        "IMAGE",
            "mask":         "MASK",
            "samples":      "LATENT",
        }
        for kw, t in type_map.items():
            if kw in name_l:
                return t

        # Par class_type source
        ct = class_type.lower()
        if "checkpoint" in ct:
            slot_types = {0: "MODEL", 1: "CLIP", 2: "VAE"}
            return slot_types.get(src_slot, "MODEL")
        if "lora" in ct:
            slot_types = {0: "MODEL", 1: "CLIP", 2: "STRING", 3: "STRING"}
            return slot_types.get(src_slot, "MODEL")
        if "ksampler" in ct:
            return "LATENT"
        if "vaedecode" in ct or "vae" in ct:
            return "IMAGE"
        if "clip" in ct and "encode" in ct:
            return "CONDITIONING"
        if "seed" in ct:
            return "INT"
        if "easy int" in ct or "primitiveint" in ct:
            return "INT"
        if "easy float" in ct or "primitivefloat" in ct:
            return "FLOAT"
        if "switch" in ct:
            return "*"
        return "*"

    def organize_file(self, api_path: str,
                       canvas_path: str = None,
                       original_canvas_path: str = None) -> str:
        """
        Point d'entrée principal.
        Lit le fichier API, organise, sauvegarde en format canvas.
        """
        self.log.info(f"[ORGANIZER] Lecture : {api_path}")

        with open(api_path, encoding="utf-8") as f:
            api_wf = json.load(f)

        original = None
        if original_canvas_path and Path(original_canvas_path).exists():
            with open(original_canvas_path, encoding="utf-8") as f:
                original = json.load(f)

        canvas = self.api_to_canvas(api_wf, original)

        # Chemin de sortie
        if canvas_path is None:
            stem       = Path(api_path).stem.replace("_API","")
            canvas_path = str(Path(api_path).parent / f"{stem}_CANVAS.json")

        with open(canvas_path, "w", encoding="utf-8") as f:
            json.dump(canvas, f, indent=2, ensure_ascii=False)

        size_kb = Path(canvas_path).stat().st_size // 1024
        self.log.info(
            f"[ORGANIZER] ✓ Canvas sauvegardé : {canvas_path} ({size_kb} Ko)"
        )
        self.log.info(
            f"[ORGANIZER] → Ouvrir dans ComfyUI : Charger → {Path(canvas_path).name}"
        )
        return canvas_path


# ── Rapport textuel de l'organisation ────────────────────────────────
def print_organization_report(canvas: dict):
    """Affiche un résumé lisible de l'organisation du canvas."""
    print()
    print("═" * 60)
    print("  ORGANISATION DU WORKFLOW COMFYUI")
    print("═" * 60)

    groups = canvas.get("groups", [])
    nodes  = canvas.get("nodes",  [])
    links  = canvas.get("links",  [])

    # Trier les groupes par position X
    groups_sorted = sorted(groups, key=lambda g: g["bounding"][0])

    # Groupes principaux (pas les sous-groupes)
    main_groups = [g for g in groups_sorted
                   if not any(
                       g["bounding"][0] > og["bounding"][0] and
                       g["bounding"][1] > og["bounding"][1] and
                       g["bounding"][0]+g["bounding"][2] < og["bounding"][0]+og["bounding"][2]
                       for og in groups_sorted if og is not g
                   )]

    print(f"\n  {len(groups)} groupes  |  {len(nodes)} nœuds  |  {len(links)} liens\n")
    print(f"  Flux de gauche à droite :")
    print()

    for i, g in enumerate(groups_sorted[:15]):  # 15 premiers
        x, y = g["bounding"][0], g["bounding"][1]
        w, h = g["bounding"][2], g["bounding"][3]
        col  = g["color"]
        print(f"  [{i+1:2}] {g['title']:<42} pos=({x:4},{y:4}) {w}×{h}px  {col}")

    if len(groups_sorted) > 15:
        print(f"  ... et {len(groups_sorted)-15} sous-groupes")

    print()
    print("═" * 60)
    print("  Ouvrir dans ComfyUI : Charger le fichier _CANVAS.json")
    print("  Ctrl+A pour tout sélectionner → Ctrl+F pour recentrer")
    print("═" * 60)


# ── CLI ───────────────────────────────────────────────────────────────
if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO,
                         format="%(asctime)s [%(levelname)s] %(message)s")
    log = logging.getLogger("organizer")

    # Chemin par défaut
    api_path = sys.argv[1] if len(sys.argv) > 1 else "Combined_V35_API.json"
    orig_path = sys.argv[2] if len(sys.argv) > 2 else None

    if not Path(api_path).exists():
        print(f"Fichier non trouvé : {api_path}")
        print("Usage : python agents/workflow_organizer.py Combined_V35_API.json")
        sys.exit(1)

    organizer = WorkflowOrganizer(log)
    canvas_path = organizer.organize_file(api_path, original_canvas_path=orig_path)

    # Charger et afficher le rapport
    with open(canvas_path, encoding="utf-8") as f:
        canvas = json.load(f)
    print_organization_report(canvas)
    print(f"\n  Fichier généré : {canvas_path}\n")

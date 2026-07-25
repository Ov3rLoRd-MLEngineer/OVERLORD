# ██████╗ ██╗   ██╗██████╗ ██████╗ ██╗      ██████╗ ██████╗ ██████╗
# ██╔═══██╗██║   ██║╚════██╗██╔══██╗██║     ██╔═══██╗██╔══██╗██╔══██╗
# ██║   ██║██║   ██║ █████╔╝██████╔╝██║     ██║   ██║██████╔╝██║  ██║
# ██║   ██║╚██╗ ██╔╝ ╚═══██╗██╔══██╗██║     ██║   ██║██╔══██╗██║  ██║
# ╚██████╔╝ ╚████╔╝ ██████╔╝██║  ██║███████╗╚██████╔╝██║  ██║██████╔╝
# ╚═════╝   ╚═══╝  ╚═════╝ ╚═╝  ╚═╝╚══════╝ ╚═════╝ ╚═╝  ╚═╝╚═════╝
# Ov3rLoRd -- pipeline de production anime autonome (ComfyUI)
# https://github.com/Ov3rLoRd-MLEngineer
#
# quality_sort.py — FootSegNet -> Control-LoRA (Ov3rLoRd Pipeline)
#
# Classe chaque paire (image, masque) du dataset FootSegNet en :
#   - "exploitable"   : utilisable telle quelle pour l'entraînement Control-LoRA
#   - "a_corriger"    : probablement exploitable mais mérite une relecture
#                       (fallback grounding VLM utilisé, taux de couverture
#                       du masque suspect)
#   - "a_exclure"     : à ne pas utiliser (aucun masque, échec de génération)
#
# Chaque décision est journalisée avec sa RAISON (pas de rejet silencieux) —
# réutilise dataset\premasks\_provenance.csv produit par
# agents\segnet_premask.run_batch() (box_source, status, mask_pct) plutôt que
# de recalculer un IoU (analyze_errors.py compare à un masque MANUEL de
# référence, absent ici par construction — ce script trie des images encore
# jamais vues/annotées).
#
# Usage :
#   py -3.12 quality_sort.py
#   py -3.12 quality_sort.py --min-pct 0.5 --max-pct 20
#   py -3.12 quality_sort.py --write-manifest      (filtre controlnet\dataset\manifest.jsonl)

import argparse
import csv
import json
from pathlib import Path

import numpy as np
from PIL import Image

import sys
_REPO_ROOT = Path(__file__).resolve().parent.parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))
import config

FOOTSEGNET_ROOT = config.FOOTSEGNET_ROOT
RAW_DIR         = FOOTSEGNET_ROOT / "dataset" / "raw"
MASKS_RAW_DIR   = FOOTSEGNET_ROOT / "dataset" / "masks_raw"
PREMASKS_DIR    = FOOTSEGNET_ROOT / "dataset" / "premasks"
PROVENANCE_CSV  = PREMASKS_DIR / "_provenance.csv"

CONTROLNET_ROOT  = FOOTSEGNET_ROOT / "controlnet"
CN_MANIFEST_PATH = CONTROLNET_ROOT / "dataset" / "manifest.jsonl"
REPORT_PATH      = CONTROLNET_ROOT / "quality_report.txt"
REPORT_JSON_PATH = CONTROLNET_ROOT / "quality_report.json"

EXPLOITABLE, A_CORRIGER, A_EXCLURE = "exploitable", "a_corriger", "a_exclure"

DEFAULT_MIN_PCT = 0.5    # en dessous : masque suspicieusement petit (occlusion probable)
DEFAULT_MAX_PCT = 20.0   # au dessus : masque suspicieusement large (bbox mal centrée)


def _latest_provenance_rows() -> dict[str, dict]:
    """Dernière ligne de _provenance.csv par image (une image peut avoir
    plusieurs passages si batch_premask a été relancé plusieurs fois)."""
    rows: dict[str, dict] = {}
    if not PROVENANCE_CSV.exists():
        return rows
    with open(PROVENANCE_CSV, encoding="utf-8-sig", newline="") as f:
        for row in csv.DictReader(f):
            rows[row["image"]] = row   # écrase avec la ligne la plus récente
    return rows


def _mask_pct_from_file(mask_path: Path) -> float | None:
    try:
        arr = np.array(Image.open(mask_path).convert("L"))
        return float((arr > 127).mean() * 100)
    except Exception:
        return None


def classify(stem: str, provenance: dict, min_pct: float, max_pct: float) -> tuple[str, str, dict]:
    """Retourne (catégorie, raison, détails) pour une image du dataset raw."""
    manual_mask = MASKS_RAW_DIR / f"{stem}.png"
    auto_mask = PREMASKS_DIR / f"{stem}.png"

    if manual_mask.exists():
        pct = _mask_pct_from_file(manual_mask)
        pct_txt = f"{pct:.2f}%" if pct is not None else "?"
        return EXPLOITABLE, f"masque manuel (vérité terrain), couverture {pct_txt}", \
            {"mask_source": "manual", "mask_pct": pct, "box_source": ""}

    row = provenance.get(f"{stem}.png")

    if row is not None:
        status = row.get("status", "")
        box_source = row.get("box_source", "")
        mask_pct_txt = row.get("mask_pct", "")
        mask_pct = float(mask_pct_txt) if mask_pct_txt not in ("", None) else None
        details = {"mask_source": "auto", "mask_pct": mask_pct, "box_source": box_source}

        if status == "BOX_FAILED":
            return A_EXCLURE, "aucune bbox dérivable (pose non détectée par DWPose ET " \
                "échec du fallback grounding VLM) — pose atypique ou personnage non " \
                "reconnaissable", details
        if status == "INFER_FAILED":
            return A_EXCLURE, "inférence SAM échouée sur la bbox trouvée", details
        if status != "OK":
            return A_EXCLURE, f"statut de génération inattendu ({status})", details

        if box_source.startswith("qwenvl_grounding"):
            return A_CORRIGER, f"bbox obtenue par fallback grounding VLM ({box_source}) " \
                "— DWPose n'a pas détecté la pose, cadrage à vérifier avant usage", details

        if mask_pct is not None and mask_pct < min_pct:
            return A_CORRIGER, f"masque très petit ({mask_pct:.2f}% < {min_pct}%) " \
                "— pied/chaussure probablement occlus ou bbox mal centrée", details
        if mask_pct is not None and mask_pct > max_pct:
            return A_CORRIGER, f"masque très large ({mask_pct:.2f}% > {max_pct}%) " \
                "— bbox probablement surdimensionnée ou cadrage atypique (gros plan)", details

        pct_txt = f"{mask_pct:.2f}%" if mask_pct is not None else "?"
        return EXPLOITABLE, f"bbox DWPose, masque de couverture plausible ({pct_txt})", details

    if auto_mask.exists():
        # Pré-masque présent mais sans ligne de provenance (généré avant
        # l'introduction de _provenance.csv, ou CSV perdu) — estimation
        # directe depuis le fichier, moins fiable (pas de box_source connu).
        pct = _mask_pct_from_file(auto_mask)
        details = {"mask_source": "auto", "mask_pct": pct, "box_source": "unknown"}
        if pct is None:
            return A_EXCLURE, "pré-masque illisible", details
        if pct < min_pct or pct > max_pct:
            return A_CORRIGER, f"provenance non tracée (masque pré-existant), couverture " \
                f"hors plage plausible ({pct:.2f}%)", details
        return A_CORRIGER, f"provenance non tracée (masque pré-existant), couverture " \
            f"plausible ({pct:.2f}%) mais source de bbox inconnue", details

    return A_EXCLURE, "aucun masque disponible (ni manuel ni pré-masque auto — " \
        "lancer prepare_dataset.py au préalable)", \
        {"mask_source": None, "mask_pct": None, "box_source": ""}


def sort_dataset(min_pct: float, max_pct: float) -> list[dict]:
    provenance = _latest_provenance_rows()
    results = []
    for img_path in sorted(RAW_DIR.iterdir()):
        if img_path.suffix.lower() != ".png" or img_path.name.startswith("_"):
            continue
        stem = img_path.stem
        category, reason, details = classify(stem, provenance, min_pct, max_pct)
        results.append({"stem": stem, "category": category, "reason": reason, **details})
    return results


def write_report(results: list[dict], min_pct: float, max_pct: float) -> None:
    CONTROLNET_ROOT.mkdir(parents=True, exist_ok=True)
    counts = {EXPLOITABLE: 0, A_CORRIGER: 0, A_EXCLURE: 0}
    for r in results:
        counts[r["category"]] += 1

    lines = [
        "FootSegNet -> Control-LoRA — tri qualité des paires (image, masque)",
        f"seuils couverture masque : min={min_pct}%  max={max_pct}%",
        f"{len(results)} image(s) analysée(s)",
        "",
        f"exploitable telle quelle : {counts[EXPLOITABLE]}",
        f"à corriger manuellement  : {counts[A_CORRIGER]}",
        f"à exclure                : {counts[A_EXCLURE]}",
        "",
    ]
    for category, title in ((A_EXCLURE, "À EXCLURE"),
                             (A_CORRIGER, "À CORRIGER MANUELLEMENT"),
                             (EXPLOITABLE, "EXPLOITABLE TELLE QUELLE")):
        subset = [r for r in results if r["category"] == category]
        lines.append(f"── {title} ({len(subset)}) " + "─" * max(0, 40 - len(title)))
        for r in subset:
            lines.append(f"  {r['stem']}  —  {r['reason']}")
        lines.append("")

    REPORT_PATH.write_text("\n".join(lines), encoding="utf-8")
    REPORT_JSON_PATH.write_text(
        json.dumps(results, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    print(f"[quality_sort] exploitable={counts[EXPLOITABLE]}  "
          f"a_corriger={counts[A_CORRIGER]}  a_exclure={counts[A_EXCLURE]}")
    print(f"[quality_sort] Rapport -> {REPORT_PATH}")
    print(f"[quality_sort] Rapport (JSON) -> {REPORT_JSON_PATH}")


def write_filtered_manifest(results: list[dict], include_a_corriger: bool) -> None:
    """Réécrit controlnet\\dataset\\manifest.jsonl en retirant les entrées
    'a_exclure' (et 'a_corriger' sauf --include-a-corriger). Le manifest
    original n'est PAS modifié en place : sortie séparée manifest_filtered.jsonl."""
    if not CN_MANIFEST_PATH.exists():
        print(f"[quality_sort] {CN_MANIFEST_PATH} introuvable — lancer prepare_dataset.py "
              f"avant --write-manifest")
        return

    keep_categories = {EXPLOITABLE} | ({A_CORRIGER} if include_a_corriger else set())
    kept_stems = {r["stem"] for r in results if r["category"] in keep_categories}

    kept, dropped = 0, 0
    out_lines = []
    for line in CN_MANIFEST_PATH.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        entry = json.loads(line)
        stem = Path(entry["file_name"]).stem
        if stem in kept_stems:
            out_lines.append(json.dumps(entry, ensure_ascii=False))
            kept += 1
        else:
            dropped += 1

    filtered_path = CN_MANIFEST_PATH.with_name("manifest_filtered.jsonl")
    filtered_path.write_text("\n".join(out_lines), encoding="utf-8")
    print(f"[quality_sort] manifest filtré : {kept} conservée(s), {dropped} écartée(s) -> {filtered_path}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="FootSegNet -> Control-LoRA : tri qualité des paires (image, masque)"
    )
    parser.add_argument("--min-pct", type=float, default=DEFAULT_MIN_PCT,
                        help=f"Couverture masque minimale plausible en %% (défaut: {DEFAULT_MIN_PCT})")
    parser.add_argument("--max-pct", type=float, default=DEFAULT_MAX_PCT,
                        help=f"Couverture masque maximale plausible en %% (défaut: {DEFAULT_MAX_PCT})")
    parser.add_argument("--write-manifest", action="store_true",
                        help="Écrit controlnet\\dataset\\manifest_filtered.jsonl (exclut 'a_exclure')")
    parser.add_argument("--include-a-corriger", action="store_true",
                        help="Avec --write-manifest : garde aussi les entrées 'a_corriger'")
    args = parser.parse_args()

    results = sort_dataset(args.min_pct, args.max_pct)
    write_report(results, args.min_pct, args.max_pct)
    if args.write_manifest:
        write_filtered_manifest(results, args.include_a_corriger)

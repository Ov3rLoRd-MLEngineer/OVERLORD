# ██████╗ ██╗   ██╗██████╗ ██████╗ ██╗      ██████╗ ██████╗ ██████╗
# ██╔═══██╗██║   ██║╚════██╗██╔══██╗██║     ██╔═══██╗██╔══██╗██╔══██╗
# ██║   ██║██║   ██║ █████╔╝██████╔╝██║     ██║   ██║██████╔╝██║  ██║
# ██║   ██║╚██╗ ██╔╝ ╚═══██╗██╔══██╗██║     ██║   ██║██╔══██╗██║  ██║
# ╚██████╔╝ ╚████╔╝ ██████╔╝██║  ██║███████╗╚██████╔╝██║  ██║██████╔╝
# ╚═════╝   ╚═══╝  ╚═════╝ ╚═╝  ╚═╝╚══════╝ ╚═════╝ ╚═╝  ╚═╝╚═════╝
# Ov3rLoRd -- pipeline de production anime autonome (ComfyUI)
# https://github.com/Ov3rLoRd-MLEngineer
#
# detect_hand_occlusion.py — separe le lot "auto" multi-instance en deux
# paquets (occlusion probable / biais probable) via qwen2.5vl:7b
#
# CONTEXTE (session du 2026-07-28) : l'echantillonnage visuel manuel (12/138
# images "auto" multi-instance HandSegNet) a trouve 50% de degradation, deux
# causes distinctes melangees : le biais anticipe (une main nette, une
# degradee, score tire vers le haut malgre le defaut -- 1/12) et l'occlusion
# par un objet tenu (masque flou par nature du cas, pas par defaut du tri --
# 5/12). Objectif : separer automatiquement ces deux paquets pour permettre
# une revue differenciee.
#
# CONNEXION OLLAMA : reutilise integralement agents/vlm_grounding.py
# (load_ollama_url(), _call_vlm(), DEFAULT_MODEL="qwen2.5vl:7b") -- meme URL
# (config/llm_endpoints.json, fallback http://127.0.0.1:11434), meme format
# JSON force, meme temperature=0.0, AUCUN num_ctx personnalise (options ne
# contient que temperature, comme le reste du pipeline -- pas de raison de
# l'augmenter). Le pattern "description d'abord, verdict ensuite" reprend
# PROMPT_VERIFY_TEMPLATE (meme fichier) qui a deja fait ses preuves pour
# limiter la complaisance du modele.
#
# ECART AVEC LA CONSIGNE INITIALE (a documenter) : la consigne suggerait
# d'utiliser le crop existant dans dataset/premasks/_qc/ ("le crop de la
# bbox si disponible"). Verifie plutot que suppose : ces fichiers
# (*_compare.png) sont en realite des panneaux COMPOSITES 2 volets
# (source+bbox annotee | masque cote a cote, 824x512 type), pas des crops
# simples de la bbox -- les envoyer tels quels au VLM lui montrerait aussi le
# masque binaire a cote, source de confusion. Ce script genere donc son
# PROPRE crop directement depuis dataset/raw/<stem>.png avec la bbox deja
# enregistree dans _provenance.csv (meme logique que
# agents/vlm_grounding.py::verify_crop()).
#
# ATTENTION GPU (2026-07-28) : le pinning CUDA_VISIBLE_DEVICES par UUID de
# launch_ollama.bat s'est revele NON fiable lors de cette session -- le
# worker d'inference (llama-server.exe) s'est charge sur la RTX 5080 (GPU 0,
# occupee par une autre session) au lieu de la RTX 5060 Ti (GPU 1) prevue.
# CE SCRIPT N'A DONC PAS ETE EXECUTE EN CONDITIONS REELLES sur les 138
# images -- seule la logique de selection/crop a ete verifiee (voir
# --dry-run, qui ne fait AUCUN appel Ollama). Verifier `ollama ps` (colonne
# PROCESSOR) et le tableau des process nvidia-smi (colonne GPU) AVANT tout
# lancement reel pour confirmer que le worker est bien sur GPU 1.
#
# Usage :
#   py -3.12 agents/detect_hand_occlusion.py --module handsegnet --dry-run
#   py -3.12 agents/detect_hand_occlusion.py --module handsegnet
#   py -3.12 agents/detect_hand_occlusion.py --module handsegnet --limit 5   (test reel restreint)

import argparse
import csv
import io
import json
import sys
import time
from datetime import datetime
from pathlib import Path

from PIL import Image

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))
from agents.route_by_sam_confidence import MODULE_ROOTS   # noqa: E402
from agents.vlm_grounding import DEFAULT_MODEL, DEFAULT_TIMEOUT, _call_vlm, load_ollama_url   # noqa: E402

# Description neutre de l'objet inspecte -- passee au prompt, PAS de couleur
# (meme lecon que vlm_grounding : une description trop precise declenche la
# complaisance du modele).
DEFAULT_OBJECT_DESC = "hand(s)"

PROMPT_OCCLUSION_TEMPLATE = """You are inspecting a cropped region from an anime illustration, focused on {obj}.

FIRST describe what the crop actually shows (how many hands are visible, what they are doing, what if anything they are holding), THEN judge: is either hand significantly occluded or obscured by a held object (cup, phone, camera, lighter, food, etc.) such that its shape or fingers are not clearly visible?

Be strict: only answer true if an object genuinely hides a meaningful part of a hand. Fingers simply curled, a fist, or a hand behind another hand does NOT count as occlusion by an object.

Reply with a JSON object only:
{{"description": "<short description of what the crop shows>", "occluded_by_object": true | false}}"""

OCCLUSION_BUCKET = "probable-occlusion"
BIAS_BUCKET = "probable-biais-reel"


def _multi_instance_auto_stems(module: str) -> list[tuple[str, dict]]:
    """Stems classes 'auto' (route_auto_sort.txt, seuil calibre en PR #17)
    ET dont la derniere ligne de provenance est multi-instance -- sous-
    ensemble concerne par le biais potentiel (cf. contexte en tete de
    fichier), pas tout le lot auto."""
    dataset_dir = MODULE_ROOTS[module] / "dataset"
    premasks_dir = dataset_dir / "premasks"
    auto_path = premasks_dir / "route_auto_sort.txt"
    prov_path = premasks_dir / "_provenance.csv"

    auto_stems = {s.strip() for s in auto_path.read_text(encoding="utf-8").splitlines() if s.strip()}

    last_row: dict[str, dict] = {}
    with open(prov_path, encoding="utf-8-sig", newline="") as f:
        for row in csv.DictReader(f):
            last_row[Path(row["image"]).stem] = row

    result = []
    for stem in sorted(auto_stems):
        row = last_row.get(stem)
        if row and row.get("box_source", "").startswith("qwenvl_grounding_multi("):
            result.append((stem, row))
    return result


def _crop_bbox(raw_dir: Path, stem: str, row: dict) -> bytes | None:
    """Crop de dataset/raw/<stem>.png sur la bbox englobante deja enregistree
    (colonnes x/y/w/h de _provenance.csv) -- PAS le panneau composite _qc/
    (cf. ecart documente en tete de fichier). Retourne les octets PNG, ou
    None si l'image source est introuvable ou la zone degeneree."""
    img_path = raw_dir / row["image"]
    if not img_path.exists():
        return None
    x, y, w, h = int(row["x"]), int(row["y"]), int(row["w"]), int(row["h"])
    with Image.open(img_path) as im:
        im = im.convert("RGB")
        x1, y1 = max(0, x), max(0, y)
        x2, y2 = min(im.width, x + w), min(im.height, y + h)
        if x2 - x1 < 4 or y2 - y1 < 4:
            return None
        crop = im.crop((x1, y1, x2, y2))
        buf = io.BytesIO()
        crop.save(buf, format="PNG")
        return buf.getvalue()


def _ask_occlusion(crop_bytes: bytes, obj: str, model: str, timeout: int,
                   ollama_url: str) -> dict:
    """Un appel Ollama, meme mecanique que agents.vlm_grounding._call_vlm().
    Retourne {"description": str, "occluded_by_object": bool} ou
    {"error": str} si l'appel/parse echoue."""
    prompt = PROMPT_OCCLUSION_TEMPLATE.format(obj=obj)
    data, err = _call_vlm(crop_bytes, prompt, model, timeout, ollama_url)
    if data is None:
        return {"error": err}
    occluded = data.get("occluded_by_object")
    if not isinstance(occluded, bool):
        return {"error": f"champ occluded_by_object inexploitable : {data!r}"}
    return {"description": str(data.get("description", "")).strip(),
            "occluded_by_object": occluded}


def main(module: str, limit: int | None, dry_run: bool, obj: str,
        model: str, timeout: int) -> None:
    dataset_dir = MODULE_ROOTS[module] / "dataset"
    raw_dir = dataset_dir / "raw"
    premasks_dir = dataset_dir / "premasks"

    targets = _multi_instance_auto_stems(module)
    if limit:
        targets = targets[:limit]

    print(f"[detect_hand_occlusion] {module} : {len(targets)} image(s) auto multi-instance a inspecter")

    if dry_run:
        print("[detect_hand_occlusion] --dry-run : verification de la selection/crop uniquement, "
              "AUCUN appel Ollama.")
        ok, bad = 0, []
        for stem, row in targets:
            crop_bytes = _crop_bbox(raw_dir, stem, row)
            if crop_bytes is None:
                bad.append(stem)
            else:
                ok += 1
        print(f"[detect_hand_occlusion] crops generables : {ok}/{len(targets)}")
        if bad:
            print(f"[detect_hand_occlusion] echecs de crop : {bad}")
        return

    ollama_url = load_ollama_url()
    print(f"[detect_hand_occlusion] Ollama : {ollama_url}  modele={model}")

    results = []
    for i, (stem, row) in enumerate(targets, 1):
        crop_bytes = _crop_bbox(raw_dir, stem, row)
        if crop_bytes is None:
            print(f"  ({i}/{len(targets)}) {stem} : crop impossible (image/bbox invalide) — ignore")
            continue

        t0 = time.time()
        verdict = _ask_occlusion(crop_bytes, obj, model, timeout, ollama_url)
        elapsed = time.time() - t0

        if "error" in verdict:
            print(f"  ({i}/{len(targets)}) {stem} : ERREUR — {verdict['error']}")
            results.append({"stem": stem, "bucket": "error", "error": verdict["error"],
                            "elapsed_s": round(elapsed, 1)})
            continue

        bucket = OCCLUSION_BUCKET if verdict["occluded_by_object"] else BIAS_BUCKET
        print(f"  ({i}/{len(targets)}) {stem} : {bucket} ({elapsed:.1f}s) — {verdict['description'][:80]}")
        results.append({
            "stem": stem, "bucket": bucket,
            "occluded_by_object": verdict["occluded_by_object"],
            "description": verdict["description"],
            "sam_score": row.get("sam_score", ""),
            "box_source": row.get("box_source", ""),
            "elapsed_s": round(elapsed, 1),
        })

    manifest_path = premasks_dir / "occlusion_manifest.json"
    manifest_path.write_text(json.dumps({
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "module": module, "model": model, "object_desc": obj,
        "total": len(targets), "results": results,
    }, indent=2, ensure_ascii=False), encoding="utf-8")

    counts = {}
    for r in results:
        counts[r["bucket"]] = counts.get(r["bucket"], 0) + 1
    print(f"\n[detect_hand_occlusion] Termine : {counts}")
    print(f"[detect_hand_occlusion] Manifest -> {manifest_path}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Separe le lot 'auto' multi-instance en occlusion probable / biais probable "
                     "via qwen2.5vl:7b (crop de la bbox deja enregistree, pas l'image complete).")
    parser.add_argument("--module", required=True, choices=sorted(MODULE_ROOTS))
    parser.add_argument("--limit", type=int, default=None, help="Limiter aux N premieres images (test)")
    parser.add_argument("--dry-run", action="store_true",
                         help="Verifie seulement la selection/generation des crops, aucun appel Ollama")
    parser.add_argument("--object", default=DEFAULT_OBJECT_DESC, dest="obj",
                         help=f"Description neutre de l'objet inspecte (defaut: {DEFAULT_OBJECT_DESC!r})")
    parser.add_argument("--model", default=DEFAULT_MODEL)
    parser.add_argument("--timeout", type=int, default=DEFAULT_TIMEOUT)
    args = parser.parse_args()
    main(args.module, args.limit, args.dry_run, args.obj, args.model, args.timeout)

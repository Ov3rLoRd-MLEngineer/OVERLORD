"""Compare LineArtPreprocessor (realiste) vs AnimeLineArtPreprocessor (deja
valide piste E) sur les 10 frames de reference, avec nettoyage "technique
scantrad" (Priorite 5, session_nuit.txt 2026-08-06/07) :
  1. Levels/threshold (elimine le gris residuel)
  2. Despeckle (retire les artefacts isoles < aire minimale)
  3. Unsharp mask leger (renforce les traits fins, applique AVANT le seuillage
     sur le niveau de gris -- apres binarisation un unsharp n'a plus de sens)

Ne relance PAS la chaine recolorisation/fusion complete de piste E (cout GPU
diffusion x2 preprocesseurs x10 frames non justifie pour une simple
comparaison de nettoyage de traits) : mesure le delta Lab directement sur le
lineart nettoye (coherence temporelle des traits eux-memes, pas du rendu
final) + inspection visuelle. Reutilise les 10 frames sources deja presentes
dans DEMO/frames/comparaison_unification_ref/ (comparatif A/B/C/D/piste E).

Usage (ComfyUI doit tourner, port 8188) :
    py -3.12 DEMO/compare_lineart_preprocessors.py
"""
import json
import os
import time
import urllib.request

import cv2
import numpy as np
from PIL import Image
from skimage.color import rgb2lab

COMFY = "http://127.0.0.1:8188"
COMFY_INPUT_DIR = r"D:\Ov3rLoRd AI\ComfyUI\input"
COMFY_OUTPUT_DIR = r"D:\Ov3rLoRd AI\ComfyUI\output"
REF_DIR = r"D:\OVERLORD\DEMO\frames\comparaison_unification_ref"
OUT_DIR = os.path.join(REF_DIR, "piste_lineart_compare")
FRAME_IDS = [1, 5, 9, 13, 17, 21, 25, 29, 33, 37]

PREPROCESSORS = {
    "LineArtPreprocessor_realiste": "LineArtPreprocessor",
    "AnimeLineArtPreprocessor": "AnimeLineArtPreprocessor",
}


def queue_prompt(workflow, client_id):
    body = json.dumps({"prompt": workflow, "client_id": client_id}).encode("utf-8")
    req = urllib.request.Request(f"{COMFY}/prompt", data=body, headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.load(resp)


def wait_for_completion(prompt_id, timeout=60, poll=1.5):
    start = time.time()
    while time.time() - start < timeout:
        with urllib.request.urlopen(f"{COMFY}/history/{prompt_id}", timeout=30) as resp:
            hist = json.load(resp)
        if prompt_id in hist:
            entry = hist[prompt_id]
            status = entry.get("status", {})
            if status.get("completed") is True:
                return entry
            if status.get("status_str") == "error":
                raise RuntimeError(f"ComfyUI execution error: {json.dumps(status)}")
        time.sleep(poll)
    raise TimeoutError(f"prompt {prompt_id} pas termine apres {timeout}s")


def run_preprocessor(class_type, image_name, node_id="2"):
    node_inputs = {"image": ["1", 0], "resolution": 1024}
    if class_type == "LineArtPreprocessor":
        node_inputs["coarse"] = "disable"
    wf = {
        "1": {"class_type": "LoadImage", "inputs": {"image": image_name}},
        node_id: {"class_type": class_type, "inputs": node_inputs},
        "3": {"class_type": "SaveImage", "inputs": {"images": [node_id, 0], "filename_prefix": f"lineart_compare/{class_type}"}},
    }
    r = queue_prompt(wf, f"lineart-compare-{class_type}")
    if r.get("node_errors"):
        raise RuntimeError(f"node_errors: {json.dumps(r['node_errors'])}")
    entry = wait_for_completion(r["prompt_id"])
    info = entry["outputs"]["3"]["images"][0]
    return info.get("fullpath") or os.path.join(COMFY_OUTPUT_DIR, info.get("subfolder", ""), info["filename"])


def normalize_to_white_bg_black_lines(raw_bgr):
    """Detecte automatiquement la polarite (fond clair vs fond sombre --
    la lecon piste E : ne jamais supposer) via la luminosite moyenne, et
    renvoie toujours la convention fond blanc / traits noirs."""
    gray = cv2.cvtColor(raw_bgr, cv2.COLOR_BGR2GRAY)
    mean_val = gray.mean()
    if mean_val < 127:
        # fond sombre (majorite de pixels sombres) -> traits clairs sur fond sombre, inverser
        gray = 255 - gray
    return gray


def unsharp_mask(gray, amount=0.6, sigma=1.2):
    blurred = cv2.GaussianBlur(gray, (0, 0), sigma)
    sharpened = cv2.addWeighted(gray.astype(np.float32), 1 + amount, blurred.astype(np.float32), -amount, 0)
    return np.clip(sharpened, 0, 255).astype(np.uint8)


def despeckle(binary_black_on_white, min_area=8):
    """Retire les composantes connexes isolees (traits = pixels noirs, donc
    on despeckle sur l'inverse pour traiter les ilots noirs isoles comme du
    bruit)."""
    ink = (255 - binary_black_on_white)  # traits = blanc ici pour connectedComponents
    n, labels, stats, _ = cv2.connectedComponentsWithStats((ink > 0).astype(np.uint8), connectivity=8)
    cleaned_ink = np.zeros_like(ink)
    for lbl in range(1, n):
        if stats[lbl, cv2.CC_STAT_AREA] >= min_area:
            cleaned_ink[labels == lbl] = 255
    return 255 - cleaned_ink


def scantrad_cleanup(raw_path, out_path, threshold=180):
    raw = cv2.imread(raw_path)
    gray = normalize_to_white_bg_black_lines(raw)
    sharp = unsharp_mask(gray, amount=0.6, sigma=1.2)
    _, levels = cv2.threshold(sharp, threshold, 255, cv2.THRESH_BINARY)  # levels/threshold
    cleaned = despeckle(levels, min_area=8)
    cv2.imwrite(out_path, cleaned)
    return cleaned


def lab_delta_series(frame_paths):
    labs = []
    for p in frame_paths:
        img = np.array(Image.open(p).convert("RGB")).astype(np.float64) / 255.0
        labs.append(rgb2lab(img))
    deltas = [float(np.sqrt(np.sum((labs[i + 1] - labs[i]) ** 2, axis=-1)).mean()) for i in range(len(labs) - 1)]
    return deltas, float(np.mean(deltas))


def main():
    os.makedirs(OUT_DIR, exist_ok=True)
    results = {}
    for label, class_type in PREPROCESSORS.items():
        cleaned_dir = os.path.join(OUT_DIR, label)
        os.makedirs(cleaned_dir, exist_ok=True)
        cleaned_paths = []
        for fid in FRAME_IDS:
            src = os.path.join(REF_DIR, f"frame_{fid:05d}.png")
            if not os.path.exists(src):
                print(f"[{label}] frame {fid} MANQUANTE ({src}) -- abandon de cette piste")
                cleaned_paths = None
                break
            comfy_name = f"lineart_src_{fid:05d}.png"
            import shutil
            shutil.copy2(src, os.path.join(COMFY_INPUT_DIR, comfy_name))
            t0 = time.time()
            raw_path = run_preprocessor(class_type, comfy_name)
            cleaned_path = os.path.join(cleaned_dir, f"frame_{fid:05d}_clean.png")
            scantrad_cleanup(raw_path, cleaned_path)
            print(f"[{label}] frame {fid} OK en {time.time()-t0:.1f}s -> {cleaned_path}")
            cleaned_paths.append(cleaned_path)
        if cleaned_paths:
            deltas, mean_delta = lab_delta_series(cleaned_paths)
            results[label] = {"deltas": deltas, "mean": mean_delta}
            print(f"RESULT {label}: delta Lab moyen (traits nettoyes) = {mean_delta:.4f}")

    print("\n=== RESUME ===")
    for label, r in results.items():
        print(f"{label}: delta_lab_moyen={r['mean']:.4f} deltas={[round(d,3) for d in r['deltas']]}")


if __name__ == "__main__":
    main()

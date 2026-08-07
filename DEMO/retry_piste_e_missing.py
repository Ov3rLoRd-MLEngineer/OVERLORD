"""Retente les frames piste E perdues la nuit derniere par timeout de file
ComfyUI partagee (9, 13, 21, 29, 37 -- cf. DOCS/MD/TEST_PISTE_E_LINEART_20260806.md
section Resultats). Reutilise telles quelles les fonctions deja validees de
run_piste_e_lineart.py (meme logique, meme correctif de polarite lineart) --
seul le sous-ensemble de frames et le timeout d'extraction lineart changent
(120s -> 240s, la cause du timeout etait la contention de file, pas un
graphe lent).

Usage: "D:\\Ov3rLoRd AI\\python_embeded\\python.exe" DEMO/retry_piste_e_missing.py
"""
import json
import os
import shutil
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import run_piste_e_lineart as pe

MISSING_FRAME_IDS = [9, 13, 21, 29, 37]
# E4 seul (lineart + E1/E2/E3 deja OK la nuit derniere, seule l'etape
# ColorMatchV2 finale de E4 avait timeout) : E3 et E4 partagent exactement le
# meme recolor_graph (meme seed, meme poids IPAdapter 0.9) -- reutiliser la
# sortie E3 deja sur disque comme entree du ColorMatch plutot que refaire tout
# le recolor (deterministe, evite un aller-retour GPU redondant).
E4_ONLY_FRAME_IDS = [5, 17, 25, 33]


def extract_lineart_patient(fid, frame_path, timeout=240):
    frame_name = pe.upload(frame_path, f"cmpE_src_{fid:06d}.png")
    wf = {
        "1": {"class_type": "LoadImage", "inputs": {"image": frame_name}},
        "2": {"class_type": "AnimeLineArtPreprocessor", "inputs": {
            "image": ["1", 0], "resolution": pe.LINEART_PREPROC_RESOLUTION,
        }},
        "3": {"class_type": "SaveImage", "inputs": {
            "images": ["2", 0], "filename_prefix": "CmpUnification/pisteE_lineart_raw",
        }},
    }
    raw_path = pe.run_graph(wf, f"cmpE-lineart-retry-f{fid}", "3", timeout=timeout)
    import numpy as np
    import cv2
    from PIL import Image
    raw = np.array(Image.open(raw_path).convert("L"))
    _, thresh = cv2.threshold(raw, 40, 255, cv2.THRESH_BINARY)
    dilated = cv2.dilate(thresh, np.ones((2, 2), np.uint8), iterations=1)
    clean = 255 - dilated
    os.makedirs(pe.LINEART_CLEAN_DIR, exist_ok=True)
    clean_path = os.path.join(pe.LINEART_CLEAN_DIR, f"frame_{fid:05d}.png")
    Image.fromarray(clean).convert("RGB").save(clean_path)
    return clean_path, clean


def main():
    log = {v: {"ok": [], "errors": []} for v in pe.VARIANTS}
    keyframe_name = pe.upload(pe.KEYFRAME, "cmpE_keyframe_ref.png")
    t0 = time.time()

    for fid in MISSING_FRAME_IDS:
        frame_path = os.path.join(pe.REF_DIR, f"frame_{fid:05d}.png")
        try:
            clean_path, clean_arr = extract_lineart_patient(fid, frame_path)
            print(f"[lineart] frame {fid} OK -> {clean_path}", flush=True)
        except Exception as e:
            print(f"[lineart] frame {fid} ECHEC: {e}", flush=True)
            for v in pe.VARIANTS:
                log[v]["errors"].append((fid, f"lineart extraction failed: {e}"))
            continue

        clean_name = pe.upload(clean_path, f"cmpE_linclean_{fid:06d}.png")
        seed = 700000000 + fid

        for vname, vcfg in pe.VARIANTS.items():
            out_path = os.path.join(pe.REF_DIR, f"piste_{vname}", f"frame_{fid:05d}.png")
            try:
                wf = pe.recolor_graph(fid, clean_name, keyframe_name, seed, vcfg["ipadapter"], vcfg["weight"])
                recolored_path = pe.run_graph(wf, f"cmpE-{vname}-retry-f{fid}", "15", timeout=600)

                fused_local = os.path.join(pe.REF_DIR, f"piste_{vname}", f"_fused_{fid:05d}.png")
                pe.multiply_blend(recolored_path, clean_arr, fused_local)

                if vcfg["colormatch"]:
                    fused_name = pe.upload(fused_local, f"cmpE_fused_{vname}_{fid:06d}.png")
                    wf_cm = pe.colormatch_graph(fused_name, keyframe_name)
                    cm_path = pe.run_graph(wf_cm, f"cmpE-{vname}-cm-retry-f{fid}", "4", timeout=120)
                    shutil.copy2(cm_path, out_path)
                else:
                    shutil.copy2(fused_local, out_path)
                os.remove(fused_local)

                log[vname]["ok"].append(fid)
                print(f"[{vname}] frame {fid} OK -> {out_path}", flush=True)
            except Exception as e:
                log[vname]["errors"].append((fid, str(e)))
                print(f"[{vname}] frame {fid} ECHEC: {e}", flush=True)

    for fid in E4_ONLY_FRAME_IDS:
        e3_path = os.path.join(pe.REF_DIR, "piste_E3", f"frame_{fid:05d}.png")
        out_path = os.path.join(pe.REF_DIR, "piste_E4", f"frame_{fid:05d}.png")
        if not os.path.exists(e3_path):
            print(f"[E4] frame {fid} ECHEC: piste_E3 source absente ({e3_path})", flush=True)
            log["E4"]["errors"].append((fid, "piste_E3 source absente"))
            continue
        try:
            fused_name = pe.upload(e3_path, f"cmpE_fused_E4_retry_{fid:06d}.png")
            wf_cm = pe.colormatch_graph(fused_name, keyframe_name)
            cm_path = pe.run_graph(wf_cm, f"cmpE-E4-cm-retry2-f{fid}", "4", timeout=120)
            shutil.copy2(cm_path, out_path)
            log["E4"]["ok"].append(fid)
            print(f"[E4] frame {fid} OK (depuis E3) -> {out_path}", flush=True)
        except Exception as e:
            log["E4"]["errors"].append((fid, str(e)))
            print(f"[E4] frame {fid} ECHEC: {e}", flush=True)

    print(f"RESULT_SUMMARY: {json.dumps(log)}")
    print(f"RESULT_ELAPSED_S: {time.time()-t0:.1f}")


if __name__ == "__main__":
    main()

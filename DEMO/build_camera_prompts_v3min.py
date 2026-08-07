"""Derive un fichier --camera-prompts-file (JSON {clip_index: phrase}) pour
generate_svi_chain.py a partir de :
  - DEMO/frames/sequence_plan_20260806.csv (clip, vmd, shot_type, angle_deg, duration_s)
  - DEMO/frames/video_3min_guides/clip_render_log.csv (elevation_deg, speed_mult,
    ajoutes par agents/production_video/render_clip_guides.py)

Ne fait AUCUN rendu/generation : traduit shot_type + angle azimut + elevation
en phrase camera en langue anglaise (consigne ADR-006 : prompts LLM/generation
en anglais), pour le pipeline video 3 minutes (Priorite 1, tache_a_faire
2026-08-06). Reste volontairement du texte descriptif (pas de ControlNet
pixel-precis injecte dans la chaine SVI/WAN cette session -- cf.
DOCS/MD/TEST_VIDEO_3MIN_20260806.md pour la justification de ce choix de
portee) : reprend le canal deja valide (camera prompt texte) de
generate_svi_chain.py plutot que d'introduire un ControlNet WAN non teste sur
un budget GPU de plusieurs heures.

Usage :
    py -3.12 DEMO/build_camera_prompts_v3min.py \
        --sequence-csv DEMO/frames/sequence_plan_20260806.csv \
        --render-log DEMO/frames/video_3min_guides/clip_render_log.csv \
        --out DEMO/camera_prompts_v3min.json
"""
import argparse
import csv
import json

SHOT_PHRASES = {
    "wide": "wide shot, full body visible",
    "zoom_in": "camera zooming in",
    "zoom_out": "camera zooming out, pulling back",
    "orbit": "camera orbiting around the character",
    "closeup": "close-up shot on face and upper body",
    "closeup_wide": "close-up shot, slightly wider framing, upper body visible",
}

# Azimut (angle_deg, convention setup_shot_camera : 0=face, +/-180=dos) -> 8 secteurs.
AZIMUTH_SECTORS = [
    (22.5, "seen from the front"),
    (67.5, "seen from the front-right, three-quarter view"),
    (112.5, "seen from the right side, profile view"),
    (157.5, "seen from the back-right"),
    (180.1, "seen from behind"),
]


def azimuth_phrase(angle_deg):
    a = abs(angle_deg) % 360.0
    if a > 180.0:
        a = 360.0 - a
    for threshold, phrase in AZIMUTH_SECTORS:
        if a <= threshold:
            return phrase
    return "seen from behind"


def elevation_phrase(elevation_deg):
    if elevation_deg <= -6.0:
        return "low angle shot, camera looking up"
    if elevation_deg >= 12.0:
        return "elevated camera angle, looking down slightly"
    return ""


def compose(shot_type, angle_deg, elevation_deg):
    parts = [SHOT_PHRASES.get(shot_type, shot_type), azimuth_phrase(angle_deg)]
    elev = elevation_phrase(elevation_deg)
    if elev:
        parts.append(elev)
    return ", ".join(parts)


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--sequence-csv", required=True)
    p.add_argument("--render-log", required=True)
    p.add_argument("--out", required=True)
    args = p.parse_args()

    with open(args.sequence_csv, encoding="utf-8") as f:
        seq_rows = {int(r["clip"]): r for r in csv.DictReader(f)}
    with open(args.render_log, encoding="utf-8") as f:
        log_rows = {int(r["clip"]): r for r in csv.DictReader(f)}

    missing = sorted(set(seq_rows) - set(log_rows))
    if missing:
        raise SystemExit(f"clips presents dans sequence-csv mais absents de render-log (guides pas encore rendus ?) : {missing}")

    prompts = {}
    for clip_i, seq_row in sorted(seq_rows.items()):
        log_row = log_rows[clip_i]
        elevation_deg = float(log_row["elevation_deg"])
        prompts[str(clip_i)] = compose(seq_row["shot_type"], float(seq_row["angle_deg"]), elevation_deg)

    with open(args.out, "w", encoding="utf-8") as f:
        json.dump(prompts, f, ensure_ascii=False, indent=2)
    print(f"RESULT: {len(prompts)} phrases camera -> {args.out}")
    for k in list(prompts)[:5]:
        print(f"  clip {k}: {prompts[k]}")


if __name__ == "__main__":
    main()

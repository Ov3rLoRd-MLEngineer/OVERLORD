"""Retraitement immediat de miku_demo_30s_v1.mp4 suite au verdict Jeremy
(2026-08-06) : SeedVR2 degrade au-dela de ~8s/64 frames traitees en un seul
passage. Les 8 premieres secondes (frames 1-64) de la sortie existante sont
validees et reutilisees telles quelles ; le reste (frames 65-259) est
re-upscale depuis la source brute (miku_demo_30s_v1_merged.mp4, pre-upscale)
en segments <=64 frames via le pipeline corrige.

Usage :
    py -3.12 DEMO/fix_v1_reprocess.py
"""
import os

from assemble_and_upscale import upscale_in_segments
from upscale_segments_lib import (
    BOUNDARY_SCORE_THRESHOLD,
    boundary_score,
    colormatch_correct_segment,
    concat_copy,
    extract_frame_range,
    extract_single_frame,
    interpolate_to_final_fps,
    probe_frame_count,
)

OUT_DIR = os.path.join("DEMO", "output")
GOOD_FRAMES = 64  # 8s @ 8fps, valide par Jeremy
RUN_NAME = "v1fix"


def main():
    final_v1 = os.path.abspath(os.path.join(OUT_DIR, "miku_demo_30s_v1.mp4"))
    merged_v1 = os.path.abspath(os.path.join(OUT_DIR, "miku_demo_30s_v1_merged.mp4"))
    total_frames = probe_frame_count(merged_v1)
    print(f"RESULT source: {total_frames} frames total, garde 1-{GOOD_FRAMES}, retraite {GOOD_FRAMES+1}-{total_frames}", flush=True)

    tmp_dir = os.path.join(OUT_DIR, f"_segments_{RUN_NAME}")
    os.makedirs(tmp_dir, exist_ok=True)

    # 1) Portion deja validee (frames 1-64, 0-indexe 0-63) : extraite telle
    #    quelle depuis la sortie DEJA upscalee (960x1440), pas re-upscalee.
    good_segment = os.path.join(tmp_dir, "good_1_64.mp4")
    extract_frame_range(final_v1, 0, GOOD_FRAMES, good_segment)
    print(f"RESULT good segment (reutilise, non retraite): {good_segment}", flush=True)

    # 2) Reste (frames 65-259) depuis la source BRUTE (480x720, pre-upscale) :
    #    extrait puis passe par le pipeline segmente <=64 frames.
    rest_raw = os.path.join(tmp_dir, "rest_raw.mp4")
    n_rest = total_frames - GOOD_FRAMES
    extract_frame_range(merged_v1, GOOD_FRAMES, n_rest, rest_raw)
    print(f"RESULT rest raw extrait: {n_rest} frames -> {rest_raw}", flush=True)

    upscaled_rest_segments = upscale_in_segments(rest_raw, OUT_DIR, RUN_NAME, resolution=960)

    # 3) Frontiere critique : jonction entre la portion deja-bonne (frame 64,
    #    deja 960x1440) et le premier segment nouvellement upscale.
    good_last_frame = os.path.join(tmp_dir, "good_last.png")
    extract_single_frame(good_segment, GOOD_FRAMES - 1, good_last_frame)
    first_new_frame = os.path.join(tmp_dir, "first_new.png")
    extract_single_frame(upscaled_rest_segments[0], 0, first_new_frame)
    score = boundary_score(good_last_frame, first_new_frame)
    status = "OK" if score <= BOUNDARY_SCORE_THRESHOLD else "BAS -> correction ColorMatchV2"
    print(f"RESULT boundary good->seg1: score={score:.4f} ({status})", flush=True)
    if score > BOUNDARY_SCORE_THRESHOLD:
        corr_prefix = f"DemoMiku30s/{RUN_NAME}/segments/{RUN_NAME}_seg01_colormatch_vs_good"
        upscaled_rest_segments[0] = colormatch_correct_segment(
            upscaled_rest_segments[0], good_last_frame, f"demo30s-{RUN_NAME}", corr_prefix,
        )
        print(f"RESULT correction jonction good/nouveau appliquee -> {upscaled_rest_segments[0]}", flush=True)

    # 4) Reassemblage complet + interpolation finale 24fps.
    all_segments = [good_segment] + upscaled_rest_segments
    reassembled_8fps = os.path.join(OUT_DIR, "miku_demo_30s_v1_fixed_8fps.mp4")
    concat_copy(all_segments, reassembled_8fps)
    print(f"RESULT reassembled 8fps: {reassembled_8fps}", flush=True)

    final_path = os.path.join(OUT_DIR, "miku_demo_30s_v1_fixed.mp4")
    interpolate_to_final_fps(reassembled_8fps, final_path)
    print(f"RESULT final (24fps): {os.path.abspath(final_path)}", flush=True)


if __name__ == "__main__":
    main()

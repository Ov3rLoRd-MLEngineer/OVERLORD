"""Concatene les clips SVI d'un manifeste (genere par generate_svi_chain.py)
en un seul MP4, puis lance l'upscale SeedVR2 en segments <=64 frames (regle
du 2026-08-06, verdict Jeremy : SeedVR2 degrade visuellement au-dela de ~8s/
64 frames traitees en un seul passage), avec verification de concordance de
style a chaque frontiere de segment (correction ColorMatchV2 si score bas),
puis reassemblage + interpolation 24fps final.

Pipeline :
    concat clips SVI (8fps brut)
      -> decoupage en segments <=64 frames
      -> SeedVR2 par segment (960x1440)
      -> score de concordance a chaque frontiere -> correction si besoin
      -> concat segments upscales
      -> interpolation 8fps -> 24fps (ffmpeg minterpolate, RIFE indisponible)

Interface CLI inchangee par rapport a la version pre-refactor : run_demo_loop.py
et donc toutes les iterations futures (v3+) de la boucle autonome heritent du
fix automatiquement, sans modification de leur cote.

Usage :
    py -3.12 DEMO/assemble_and_upscale.py --run-name v1 --out-dir DEMO/output
"""
import argparse
import glob
import json
import os
import shutil

from upscale_segments_lib import (
    COMFY_OUTPUT_DIR,
    SEGMENT_MAX_FRAMES,
    BOUNDARY_SCORE_THRESHOLD,
    boundary_score,
    colormatch_correct_segment,
    concat_copy,
    extract_single_frame,
    interpolate_to_final_fps,
    probe_frame_count,
    split_into_segments,
    upscale_segment,
)


def find_already_upscaled(run_name, seg_index):
    """Reprise apres echec (ex. OOM VRAM par fragmentation sur un run long,
    cf. CLAUDE.md 'runs longs degradent par fragmentation VRAM') : si ce
    segment a deja ete upscale + eventuellement corrige lors d'une tentative
    precedente, retrouve le fichier de sortie deja produit dans l'arborescence
    ComfyUI plutot que de repayer le cout GPU pour rien. La correction
    ColorMatchV2 (si appliquee) prime sur le fichier upscale brut."""
    seg_dir = os.path.join(COMFY_OUTPUT_DIR, "DemoMiku30s", run_name, "segments")
    for kind in ("colormatch", "upscaled"):
        pattern = os.path.join(seg_dir, f"{run_name}_seg{seg_index:02d}_{kind}_*.mp4")
        matches = sorted(glob.glob(pattern))
        if matches:
            return matches[-1]
    return None


def concat_clip_manifest(manifest, out_path):
    clip_indices = sorted(int(k) for k in manifest.keys())
    ordered_paths = [manifest[str(i)] for i in clip_indices]
    concat_copy(ordered_paths, out_path)


def upscale_in_segments(raw_video_path, out_dir, run_name, resolution, max_frames=SEGMENT_MAX_FRAMES):
    """Coeur reutilisable : decoupe raw_video_path en segments <=max_frames,
    upscale chacun, corrige les frontieres a faible concordance, retourne la
    liste ordonnee des chemins de segments upscales (corriges le cas echeant)."""
    tmp_dir = os.path.join(out_dir, f"_segments_{run_name}")
    segments = split_into_segments(raw_video_path, tmp_dir, prefix=f"{run_name}_raw", max_frames=max_frames)
    print(f"RESULT split: {len(segments)} segment(s) (<= {max_frames} frames chacun)", flush=True)

    upscaled = []
    prev_last_frame_png = None
    for seg in segments:
        cur_last_frame_png = os.path.join(tmp_dir, f"{run_name}_seg{seg['index']:02d}_last.png")
        cur_first_frame_png = os.path.join(tmp_dir, f"{run_name}_seg{seg['index']:02d}_first.png")
        already = find_already_upscaled(run_name, seg["index"])
        if already and os.path.exists(cur_last_frame_png) and os.path.exists(cur_first_frame_png):
            up_path = already
            print(f"RESULT upscale segment {seg['index']}/{len(segments)} : deja fait (reprise) -> {up_path}",
                  flush=True)
            upscaled.append(up_path)
            prev_last_frame_png = cur_last_frame_png
            continue

        prefix = f"DemoMiku30s/{run_name}/segments/{run_name}_seg{seg['index']:02d}_upscaled"
        up_path, dt = upscale_segment(seg["path"], resolution, f"demo30s-{run_name}", prefix)
        print(f"RESULT upscale segment {seg['index']}/{len(segments)} "
              f"({seg['n_frames']} frames): {dt:.1f}s -> {up_path}", flush=True)

        extract_single_frame(up_path, 0, cur_first_frame_png)

        if prev_last_frame_png is not None:
            score = boundary_score(prev_last_frame_png, cur_first_frame_png)
            status = "OK" if score <= BOUNDARY_SCORE_THRESHOLD else "BAS -> correction ColorMatchV2"
            print(f"RESULT boundary seg{seg['index']-1}->seg{seg['index']}: score={score:.4f} ({status})", flush=True)
            if score > BOUNDARY_SCORE_THRESHOLD:
                corr_prefix = f"DemoMiku30s/{run_name}/segments/{run_name}_seg{seg['index']:02d}_colormatch"
                up_path = colormatch_correct_segment(up_path, prev_last_frame_png, f"demo30s-{run_name}", corr_prefix)
                print(f"RESULT correction appliquee -> {up_path}", flush=True)

        n_frames = probe_frame_count(up_path)
        prev_last_frame_png = cur_last_frame_png
        extract_single_frame(up_path, n_frames - 1, prev_last_frame_png)

        upscaled.append(up_path)

    return upscaled


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--run-name", required=True)
    p.add_argument("--out-dir", default=os.path.join("DEMO", "output"))
    p.add_argument("--resolution", type=int, default=960)
    p.add_argument("--max-segment-frames", type=int, default=SEGMENT_MAX_FRAMES)
    args = p.parse_args()

    manifest_path = os.path.join(args.out_dir, f"svi_{args.run_name}_clip_manifest.json")
    with open(manifest_path, encoding="utf-8") as f:
        manifest = json.load(f)

    merged_path = os.path.abspath(os.path.join(args.out_dir, f"miku_demo_30s_{args.run_name}_merged.mp4"))
    concat_clip_manifest(manifest, merged_path)
    n_frames = probe_frame_count(merged_path)
    print(f"RESULT concat: {merged_path} ({n_frames} frames, {n_frames/8.0:.1f}s @ 8fps)", flush=True)

    upscaled_segments = upscale_in_segments(merged_path, args.out_dir, args.run_name, args.resolution, args.max_segment_frames)

    reassembled_8fps = os.path.join(args.out_dir, f"miku_demo_30s_{args.run_name}_upscaled_8fps.mp4")
    concat_copy(upscaled_segments, reassembled_8fps)
    print(f"RESULT reassembled 8fps: {reassembled_8fps}", flush=True)

    final_path = os.path.join(args.out_dir, f"miku_demo_30s_{args.run_name}.mp4")
    interpolate_to_final_fps(reassembled_8fps, final_path)
    print(f"RESULT final (24fps): {os.path.abspath(final_path)}", flush=True)


if __name__ == "__main__":
    main()

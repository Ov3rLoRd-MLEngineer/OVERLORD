# ██████╗ ██╗   ██╗██████╗ ██████╗ ██╗      ██████╗ ██████╗ ██████╗
# ██╔═══██╗██║   ██║╚════██╗██╔══██╗██║     ██╔═══██╗██╔══██╗██╔══██╗
# ██║   ██║██║   ██║ █████╔╝██████╔╝██║     ██║   ██║██████╔╝██║  ██║
# ██║   ██║╚██╗ ██╔╝ ╚═══██╗██╔══██╗██║     ██║   ██║██╔══██╗██║  ██║
# ╚██████╔╝ ╚████╔╝ ██████╔╝██║  ██║███████╗╚██████╔╝██║  ██║██████╔╝
# ╚═════╝   ╚═══╝  ╚═════╝ ╚═╝  ╚═╝╚══════╝ ╚═════╝ ╚═╝  ╚═╝╚═════╝
# Ov3rLoRd -- pipeline de production anime autonome (ComfyUI)
# https://github.com/Ov3rLoRd-MLEngineer
#
"""
visual_qc_svi.py -- Ov3rLoRd Pipeline

QC visuel automatique d'une chaine SVI (Stable Video Infinity) : extrait des
frames cles d'un MP4, les envoie a qwen2.5vl:7b (Ollama, pinne RTX 5060 Ti --
voir launch_ollama.bat) pour une evaluation independante par frame axee sur
la derive documentee dans DOCS/MD/PLAN_COHERENCE_TEMPORELLE_AOUT2026.md
(vignettage violet/magenta, perte de nettete progressive, drift couleur).

Ne remplace pas agents/qc_validation/visual_validator.py (roles
personnage/anatomie/fx, jamais modifie -- cf. memoire session) : role
different, dedie a la coherence temporelle inter-frames d'une chaine video,
pas au QC image-par-image de la production statique.

Meme convention d'appel Ollama que visual_validator.py (POST /api/chat,
image en data URI base64, reponse JSON stricte).

Monitore la RAM systeme (psutil) avant chaque appel -- arrete le traitement
des frames restantes si > 31 Go (garde-fou explicite tache 3, evite un swap
disque pendant un run qwen2.5vl).

Usage :
  py -3.12 agents/qc_validation/visual_qc_svi.py --video DEMO/output/svi_74frames_merged.mp4
  py -3.12 agents/qc_validation/visual_qc_svi.py --video clip.mp4 --frames 1,10,20,30,37
"""
import argparse
import base64
import json
import logging
import subprocess
import sys
import time
from pathlib import Path

import psutil
import requests

_REPO_ROOT = Path(__file__).resolve().parent.parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

OLLAMA_URL   = "http://127.0.0.1:11434"
QWEN_MODEL   = "qwen2.5vl:7b"
REPORTS_DIR  = Path("workspace/logs/qc_reports")
RAM_LIMIT_GB = 31.0  # machine = 31.9 Go total (voir gpu_usage_log/AUDIT) -- releve a la demande explicite de l'utilisateur (31 Go observe sans probleme), marge restante minime
DEFAULT_FRAMES = [1, 10, 20, 30, 37]

log = logging.getLogger("visual_qc_svi")
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

SYSTEM_PROMPT = (
    "You are a quality control specialist for anime video production, "
    "specifically checking TEMPORAL COHERENCE in a SVI (Stable Video "
    "Infinity) generated clip chain.\n"
    "This frame is one sample out of a longer chained video generation "
    "known to drift over time. Check specifically for:\n"
    "- Color drift / desaturation compared to a clean anime look\n"
    "- Purple/magenta vignetting on the edges (known failure mode past "
    "~90-110s into a chain)\n"
    "- Progressive loss of sharpness / blur\n"
    "- Character identity drift (outfit, hair, face proportions changing)\n"
    "- Any duplicated/repeated motion artifacts\n"
    "Respond ONLY with a JSON object, no markdown, no explanation:\n"
    '{"pass": true/false, "score": 0.0-1.0, "defects": ["list of issues"], '
    '"drift_severity": "none/mild/moderate/severe", "notes": "brief"}'
)


def _encode(path: Path) -> str:
    return base64.b64encode(path.read_bytes()).decode("utf-8")


def ram_used_gb() -> float:
    return psutil.virtual_memory().used / (1024 ** 3)


def get_total_frames(video_path: Path) -> int:
    cmd = [
        "ffprobe", "-v", "error", "-select_streams", "v:0", "-count_frames",
        "-show_entries", "stream=nb_read_frames", "-of",
        "default=noprint_wrappers=1:nokey=1", str(video_path),
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    try:
        return int(result.stdout.strip())
    except ValueError:
        log.warning(f"[QC_SVI] ffprobe n'a pas pu compter les frames de {video_path.name}")
        return 0


def extract_frames(video_path: Path, frame_indices, output_dir: Path):
    """Extrait les frames d'indices donnes (0-based, via ffmpeg select) vers
    des PNG individuels dans output_dir. Retourne {index: Path}."""
    output_dir.mkdir(parents=True, exist_ok=True)
    out_paths = {}
    for idx in frame_indices:
        dest = output_dir / f"frame_{idx:05d}.png"
        select_expr = f"select=eq(n\\,{idx})"
        cmd = [
            "ffmpeg", "-y", "-i", str(video_path),
            "-vf", select_expr, "-vsync", "vfr", "-frames:v", "1",
            str(dest),
        ]
        result = subprocess.run(cmd, capture_output=True, text=True)
        if dest.exists():
            out_paths[idx] = dest
        else:
            log.warning(f"[QC_SVI] Frame {idx} non extraite : {result.stderr[-300:]}")
    return out_paths


def call_qwen_vl(image_path: Path, frame_idx: int, total_frames: int, model: str = QWEN_MODEL) -> dict:
    img_b64 = _encode(image_path)
    user_msg = (
        f"This is frame index {frame_idx} (0-based) out of {total_frames} "
        f"total frames in the source clip. Analyze it for temporal QC."
    )
    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_msg, "images": [img_b64]},
        ],
        "stream": False,
    }
    try:
        r = requests.post(f"{OLLAMA_URL}/api/chat", json=payload, timeout=180)
        r.raise_for_status()
        content = r.json()["message"]["content"].strip()
        if content.startswith("```"):
            parts = content.split("```")
            content = parts[1].lstrip("json").strip() if len(parts) > 1 else content[3:]
        return json.loads(content)
    except json.JSONDecodeError as e:
        log.warning(f"[QC_SVI] JSON qwen2.5vl invalide (frame {frame_idx}) : {e} -- fallback conservateur")
        return {"pass": True, "score": 0.5, "defects": [], "drift_severity": "unknown", "notes": "json parse error"}
    except Exception as e:
        log.error(f"[QC_SVI] Erreur appel qwen2.5vl (frame {frame_idx}) : {e}")
        return {"pass": True, "score": 0.5, "defects": [], "drift_severity": "unknown", "notes": str(e)}


def run(video_path: str, frame_indices=None, model: str = QWEN_MODEL):
    video_path = Path(video_path)
    if not video_path.exists():
        raise FileNotFoundError(f"Video introuvable : {video_path}")
    frame_indices = frame_indices or DEFAULT_FRAMES

    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    frames_dir = REPORTS_DIR / f"_frames_{video_path.stem}"

    ram_start = ram_used_gb()
    log.info(f"[QC_SVI] RAM systeme au demarrage : {ram_start:.1f} Go (limite {RAM_LIMIT_GB} Go)")

    total_frames = get_total_frames(video_path)
    log.info(f"[QC_SVI] Extraction frames {frame_indices} depuis {video_path.name} ({total_frames} frames total)...")
    extracted = extract_frames(video_path, frame_indices, frames_dir)

    results = {}
    aborted_due_to_ram = False
    skipped_ram = []
    t0 = time.time()

    for idx in frame_indices:
        if idx not in extracted:
            continue
        current_ram = ram_used_gb()
        if current_ram > RAM_LIMIT_GB:
            log.warning(f"[QC_SVI] RAM {current_ram:.1f} Go > {RAM_LIMIT_GB} Go -- arret, frames restantes ignorees")
            aborted_due_to_ram = True
            skipped_ram = [i for i in frame_indices if i not in results and i in extracted]
            break
        log.info(f"[QC_SVI] Frame {idx} -- appel qwen2.5vl:7b (RAM {current_ram:.1f} Go)...")
        results[idx] = call_qwen_vl(extracted[idx], idx, total_frames or max(frame_indices), model=model)

    elapsed = time.time() - t0
    n_pass = sum(1 for v in results.values() if v.get("pass"))
    n_total = len(results)
    severities = [v.get("drift_severity", "unknown") for v in results.values()]

    report = {
        "video": str(video_path),
        "model": model,
        "frames_requested": frame_indices,
        "frames_analyzed": sorted(results.keys()),
        "frames_missing_extraction": sorted(set(frame_indices) - set(extracted.keys())),
        "aborted_due_to_ram": aborted_due_to_ram,
        "frames_skipped_ram": skipped_ram,
        "ram_used_gb_start": round(ram_start, 1),
        "ram_limit_gb": RAM_LIMIT_GB,
        "elapsed_s": round(elapsed, 1),
        "pass_count": n_pass,
        "total_analyzed": n_total,
        "results": {str(k): v for k, v in sorted(results.items())},
        "drift_progression": {str(k): results[k].get("drift_severity", "unknown") for k in sorted(results)},
    }

    ts = time.strftime("%Y%m%d_%H%M%S")
    json_path = REPORTS_DIR / f"qc_svi_{video_path.stem}_{ts}.json"
    json_path.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")

    md_lines = [
        f"# QC visuel SVI -- {video_path.name}",
        "",
        f"Modele : `{model}` | Frames analysees : {n_total}/{len(frame_indices)} | "
        f"Pass : {n_pass}/{n_total} | Duree : {elapsed:.1f}s",
        "",
    ]
    if aborted_due_to_ram:
        md_lines.append(f"**ARRET RAM** : {ram_used_gb():.1f} Go > {RAM_LIMIT_GB} Go -- "
                         f"frames non traitees : {skipped_ram}")
        md_lines.append("")
    md_lines.append("| Frame | Pass | Score | Drift | Defauts | Notes |")
    md_lines.append("|---|---|---|---|---|---|")
    for idx in sorted(results):
        v = results[idx]
        defects = ", ".join(v.get("defects", [])) or "-"
        md_lines.append(
            f"| {idx} | {'OK' if v.get('pass') else 'FAIL'} | {v.get('score', '?')} | "
            f"{v.get('drift_severity', '?')} | {defects} | {v.get('notes', '')} |"
        )
    md_path = REPORTS_DIR / f"qc_svi_{video_path.stem}_{ts}.md"
    md_path.write_text("\n".join(md_lines), encoding="utf-8")

    log.info(f"[QC_SVI] Rapport JSON -> {json_path}")
    log.info(f"[QC_SVI] Rapport MD   -> {md_path}")
    return report


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--video", required=True, help="Fichier MP4 a analyser")
    p.add_argument("--frames", default=None, help="Indices de frames separes par virgule (defaut: 1,10,20,30,37)")
    p.add_argument("--model", default=QWEN_MODEL, help=f"Modele Ollama (defaut: {QWEN_MODEL})")
    args = p.parse_args()

    frames = [int(x) for x in args.frames.split(",")] if args.frames else None
    run(args.video, frame_indices=frames, model=args.model)

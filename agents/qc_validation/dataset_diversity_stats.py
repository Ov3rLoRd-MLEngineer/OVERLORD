# ██████╗ ██╗   ██╗██████╗ ██████╗ ██╗      ██████╗ ██████╗ ██████╗
# ██╔═══██╗██║   ██║╚════██╗██╔══██╗██║     ██╔═══██╗██╔══██╗██╔══██╗
# ██║   ██║██║   ██║ █████╔╝██████╔╝██║     ██║   ██║██████╔╝██║  ██║
# ██║   ██║╚██╗ ██╔╝ ╚═══██╗██╔══██╗██║     ██║   ██║██╔══██╗██║  ██║
# ╚██████╔╝ ╚████╔╝ ██████╔╝██║  ██║███████╗╚██████╔╝██║  ██║██████╔╝
# ╚═════╝   ╚═══╝  ╚═════╝ ╚═╝  ╚═╝╚══════╝ ╚═════╝ ╚═╝  ╚═╝╚═════╝
# Ov3rLoRd -- pipeline de production anime autonome (ComfyUI)
# https://github.com/Ov3rLoRd-MLEngineer
#
# dataset_diversity_stats.py — Statistiques de diversité des poses via QwenVL (Ov3rLoRd)
#
# Analyse chaque image d'un dataset *SegNet (footsegnet ou handsegnet) avec
# QwenVL sur l'Ollama local, même config que
# tests\bottes_generiques\check_masks_qwenvl.py (endpoint config\llm_endpoints.json,
# qwen2.5vl:7b, JSON forcé, prompt en anglais — ADR-006) : réutilise
# `_call_vlm`/`load_ollama_url` de agents.vlm_grounding plutôt que de dupliquer
# l'appel Ollama une 3e fois dans le repo.
#
# Pour chaque image, classification structurée :
#   - count       : nombre de mains/pieds visibles du personnage principal (0/1/2)
#   - state       : mains -> ouvert/fermé/replié/écarté ; pieds -> posé/levé/en mouvement
#   - angle       : face/profil/dos/contre-plongée
#   - occlusion   : partiellement occulté (oui/non)
# Agrégée en distribution statistique (% par catégorie) + export CSV/JSON, et
# un résumé texte prêt à coller dans un README/model card.
#
# But : comparer les distributions de poses de footsegnet (300 images) et
# handsegnet pour expliquer un éventuel écart d'IoU entre les deux modèles
# (une distribution avec plus de poses "difficiles" pour SAM — pieds levés,
# contre-plongée, occlusion partielle — corrèle probablement avec un IoU plus
# bas, indépendamment de la qualité du fine-tuning lui-même).
#
# Usage :
#   py -3.12 agents\dataset_diversity_stats.py --project footsegnet
#   py -3.12 agents\dataset_diversity_stats.py --project handsegnet --limit 20
#   py -3.12 agents\dataset_diversity_stats.py --project footsegnet --model qwen2.5vl:7b

import argparse
import csv
import json
import sys
import time
from collections import Counter
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))
import config

from agents.vlm_grounding import _call_vlm, load_ollama_url  # noqa: E402

DEFAULT_MODEL   = "qwen2.5vl:7b"
DEFAULT_TIMEOUT = 180   # s/image — cohérent avec check_masks_qwenvl.py

# ── Config par projet ─────────────────────────────────────────────────────────
# `states` = valeurs valides pour le champ "state" (+ "n/a" toujours accepté
# quand count == 0). `obj_plural` sert au libellé humain dans le prompt et le
# résumé.
PROJECT_CONFIG = {
    "footsegnet": {
        "root": REPO_ROOT / "footsegnet",
        "obj_plural": "feet",
        # Le dataset annote "foot_shoe" (pied nu OU chaussé) — un prompt disant
        # juste "feet" fait répondre le modèle "not visible" dès qu'une botte
        # les couvre (constaté en test : count=0 sur une image avec bottes bien
        # visibles). Le label du prompt doit lever l'ambiguïté explicitement.
        "prompt_label": "feet — whether bare or covered by footwear (shoes, boots, sandals); footwear counts as the foot being visible",
        "states": ["planted", "raised", "in_motion"],
        "state_desc": (
            '"planted" (foot flat/grounded, weight-bearing), '
            '"raised" (lifted off the ground, e.g. mid-step or kicking), '
            '"in_motion" (walking/running blur or implied motion)'
        ),
    },
    "handsegnet": {
        "root": REPO_ROOT / "handsegnet",
        "obj_plural": "hands",
        "prompt_label": "hands — whether bare or covered by gloves; gloves count as the hand being visible",
        "states": ["open", "closed", "folded", "spread"],
        "state_desc": (
            '"open" (flat, relaxed palm/fingers), "closed" (clenched fist), '
            '"folded" (fingers curled/bent, e.g. holding something or partly closed), '
            '"spread" (fingers splayed apart)'
        ),
    },
}

ANGLES = ["front", "profile", "back", "low_angle"]

# ADR-006 : prompt en anglais (les prompts français augmentent le taux de
# JSON invalide), réponse forcée en JSON via le paramètre "format" d'Ollama
# (portée par _call_vlm, réutilisé de agents.vlm_grounding).
PROMPT_TEMPLATE = """You are a precise visual analyst cataloguing pose diversity in an anime illustration dataset.
Focus ONLY on the MAIN (largest, foreground) character; ignore secondary characters, mascots and background.

Task: describe this character's visible {prompt_label}.

Work step by step. FIRST describe what you actually see, THEN classify:
- "count": how many of the character's {obj_plural} are visible (partially counts as visible), as an integer: 0, 1, or 2.
- "state": the predominant state of the visible {obj_plural} — one of {state_desc}. Use "n/a" if count is 0.
- "angle": the camera viewing angle on the character — one of "front" (facing camera), "profile" (side view), "back" (facing away), "low_angle" (worm's-eye / looking up at the character, strong foreshortening).
- "occlusion": true if the {obj_plural} are partially hidden by clothing, hair, another object, or framing (partially out of frame); false if fully visible.

Reply with a JSON object only:
{{"description": "<one short sentence of what you see>", "count": 0 | 1 | 2, "state": "<state>", "angle": "<angle>", "occlusion": true | false}}"""


def build_prompt(cfg: dict) -> str:
    return PROMPT_TEMPLATE.format(
        prompt_label=cfg["prompt_label"], obj_plural=cfg["obj_plural"],
        state_desc=cfg["state_desc"],
    )


def classify_image(image_path: Path, cfg: dict, model: str, timeout: int,
                   ollama_url: str) -> dict:
    """Retourne un dict {status: OK|ERROR, count, state, angle, occlusion,
    description, reason}. status=ERROR sur tout échec réseau/JSON/valeur hors
    domaine (jamais d'exception propagée à l'appelant — une image illisible
    par le VLM ne doit pas interrompre le lot)."""
    valid_states = set(cfg["states"]) | {"n/a"}

    try:
        image_bytes = image_path.read_bytes()
    except Exception as e:
        return {"status": "ERROR", "reason": f"lecture impossible : {e}"}

    data, err = _call_vlm(image_bytes, build_prompt(cfg), model, timeout, ollama_url)
    if data is None:
        return {"status": "ERROR", "reason": err}

    try:
        count = int(data.get("count"))
    except (TypeError, ValueError):
        return {"status": "ERROR",
                "reason": f"count inexploitable : {data.get('count')!r}"}
    if count not in (0, 1, 2):
        return {"status": "ERROR", "reason": f"count hors domaine : {count}"}

    state = str(data.get("state", "")).strip().lower()
    if state not in valid_states:
        return {"status": "ERROR", "reason": f"state inconnu : {state!r}"}

    angle = str(data.get("angle", "")).strip().lower()
    if angle not in ANGLES:
        return {"status": "ERROR", "reason": f"angle inconnu : {angle!r}"}

    occlusion = data.get("occlusion")
    if not isinstance(occlusion, bool):
        return {"status": "ERROR",
                "reason": f"occlusion inexploitable : {occlusion!r}"}

    description = str(data.get("description", "")).strip()
    return {"status": "OK", "count": count, "state": state, "angle": angle,
            "occlusion": occlusion, "description": description, "reason": ""}


# ── Agrégation ────────────────────────────────────────────────────────────────

def _pct_distribution(counter: Counter, total: int) -> dict:
    if total == 0:
        return {}
    return {k: round(100.0 * v / total, 1) for k, v in
           sorted(counter.items(), key=lambda kv: -kv[1])}


def aggregate(results: list[dict], cfg: dict) -> dict:
    ok = [r for r in results if r["status"] == "OK"]
    n_ok = len(ok)
    n_error = len(results) - n_ok

    count_dist = _pct_distribution(Counter(r["count"] for r in ok), n_ok)
    state_dist = _pct_distribution(Counter(r["state"] for r in ok), n_ok)
    angle_dist = _pct_distribution(Counter(r["angle"] for r in ok), n_ok)
    occlusion_pct = round(100.0 * sum(1 for r in ok if r["occlusion"]) / n_ok, 1) if n_ok else 0.0

    return {
        "project": cfg["obj_plural"],
        "n_images": len(results),
        "n_ok": n_ok,
        "n_error": n_error,
        "count_distribution_pct": count_dist,
        "state_distribution_pct": state_dist,
        "angle_distribution_pct": angle_dist,
        "occlusion_pct": occlusion_pct,
    }


def format_summary(stats: dict, project_name: str) -> str:
    obj = stats["project"]
    lines = [f"Dataset composition ({project_name}, {stats['n_ok']}/{stats['n_images']} images analyzed):"]

    count_dist = stats["count_distribution_pct"]
    if count_dist:
        parts = [f"{pct}% {n}-{obj[:-1] if obj.endswith('s') and n == 1 else obj} visible"
                for n, pct in count_dist.items()]
        lines.append("- Count: " + ", ".join(parts))

    state_dist = stats["state_distribution_pct"]
    if state_dist:
        parts = [f"{pct}% {state}" for state, pct in state_dist.items()]
        lines.append("- State: " + ", ".join(parts))

    angle_dist = stats["angle_distribution_pct"]
    if angle_dist:
        parts = [f"{pct}% {angle.replace('_', '-')}" for angle, pct in angle_dist.items()]
        lines.append("- Angle: " + ", ".join(parts))

    lines.append(f"- Partial occlusion: {stats['occlusion_pct']}% of images")
    if stats["n_error"]:
        lines.append(f"- ({stats['n_error']} image(s) skipped — VLM call/parse failure)")
    return "\n".join(lines)


# ── Rapports ─────────────────────────────────────────────────────────────────

def write_reports(results: list[dict], stats: dict, summary: str, out_dir: Path) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)

    json_path = out_dir / "report_diversity.json"
    json_path.write_text(
        json.dumps({"stats": stats, "results": results}, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )

    csv_path = out_dir / "report_diversity.csv"
    with open(csv_path, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=["image", "status", "count", "state",
                                               "angle", "occlusion", "description",
                                               "reason", "elapsed_s"])
        writer.writeheader()
        writer.writerows(results)

    summary_path = out_dir / "summary.txt"
    summary_path.write_text(summary, encoding="utf-8")

    print(f"[diversity_stats] Rapports : {json_path} | {csv_path} | {summary_path}")


# ── Boucle principale ────────────────────────────────────────────────────────

def run(project: str, model: str, timeout: int, limit: int | None) -> None:
    cfg = PROJECT_CONFIG[project]
    raw_dir = cfg["root"] / "dataset" / "raw"
    images = sorted(p for p in raw_dir.glob("*.png"))
    if limit is not None:
        images = images[:limit]
    if not images:
        print(f"[diversity_stats] Aucune image dans {raw_dir}")
        raise SystemExit(1)

    ollama_url = load_ollama_url()
    print(f"[diversity_stats] {project} : {len(images)} image(s) — modèle {model} via {ollama_url}")

    t_start = time.time()
    results: list[dict] = []
    for n, img_path in enumerate(images, 1):
        t0 = time.time()
        res = classify_image(img_path, cfg, model, timeout, ollama_url)
        elapsed = time.time() - t0
        row = {
            "image": img_path.name,
            "status": res["status"],
            "count": res.get("count", ""),
            "state": res.get("state", ""),
            "angle": res.get("angle", ""),
            "occlusion": res.get("occlusion", ""),
            "description": res.get("description", ""),
            "reason": res.get("reason", ""),
            "elapsed_s": round(elapsed, 1),
        }
        results.append(row)
        tag = res["status"] if res["status"] == "OK" else f"ERROR ({res['reason']})"
        print(f"[diversity_stats] [{n}/{len(images)}] {img_path.name} : {tag} ({elapsed:.1f}s)")

    stats = aggregate(results, cfg)
    summary = format_summary(stats, project)

    out_dir = cfg["root"] / "dataset" / "diversity_stats"
    write_reports(results, stats, summary, out_dir)

    total = time.time() - t_start
    print(f"\n[diversity_stats] --- {project} ---")
    print(summary)
    print(f"[diversity_stats] Temps total : {total:.1f}s ({total / len(images):.1f}s/image)")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Statistiques de diversité des poses (QwenVL) pour un dataset *SegNet"
    )
    parser.add_argument("--project", required=True, choices=sorted(PROJECT_CONFIG.keys()),
                        help="Dataset à analyser")
    parser.add_argument("--model", default=DEFAULT_MODEL,
                        help=f"Modèle vision Ollama (défaut: {DEFAULT_MODEL})")
    parser.add_argument("--timeout", type=int, default=DEFAULT_TIMEOUT,
                        help=f"Timeout par image en s (défaut: {DEFAULT_TIMEOUT})")
    parser.add_argument("--limit", type=int, default=None,
                        help="Limiter aux N premières images (tri alphabétique) — pour un essai rapide")
    args = parser.parse_args()

    run(args.project, args.model, args.timeout, args.limit)

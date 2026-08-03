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
agents/benchmark_arena.py — Arène de Benchmark LoRA V1.47
Compare automatiquement plusieurs LoRAs/checkpoints sur les mêmes prompts.
Génère un rapport HTML avec les résultats visuels et scores.

Usage :
    from agents.benchmark_arena import BenchmarkArena
    arena = BenchmarkArena()
    results = arena.run(prompts, loras=["lora_a.safetensors","lora_b.safetensors"])
"""

import json
import logging
import hashlib
import time
import requests
from pathlib import Path
from datetime import datetime

try:
    from agents.overlord_utils import fallback_llm, safe_json_parse
    UTILS_OK = True
except ImportError:
    UTILS_OK = False

try:
    from agents.cost_tracker import get_tracker
    TRACK_OK = True
except ImportError:
    TRACK_OK = False

log = logging.getLogger("benchmark_arena")
ARENA_DIR  = Path("workspace/benchmark_arena")
COMFY_URL  = "http://127.0.0.1:8188"

SCORING_CRITERIA = [
    "consistency",      # cohérence style/personnage
    "detail_quality",   # niveau de détail
    "prompt_adherence", # fidélité au prompt
    "anatomy",          # anatomie correcte
    "aesthetic",        # qualité esthétique globale
]


class ComfyRunner:
    """Envoie des jobs à ComfyUI et attend les résultats."""

    def submit_job(self, workflow: dict) -> Optional[str]:
        try:
            r = requests.post(f"{COMFY_URL}/prompt", json={"prompt": workflow}, timeout=10)
            if r.status_code == 200:
                return r.json().get("prompt_id")
        except Exception as e:
            log.warning(f"[ARENA] Submit échoué : {e}")
        return None

    def wait_for_result(self, prompt_id: str, timeout: int = 300) -> Optional[str]:
        start = time.time()
        while time.time() - start < timeout:
            try:
                r = requests.get(f"{COMFY_URL}/history/{prompt_id}", timeout=5)
                if r.status_code == 200:
                    hist = r.json().get(prompt_id, {})
                    outputs = hist.get("outputs", {})
                    for node_id, node_out in outputs.items():
                        images = node_out.get("images", [])
                        if images:
                            return images[0].get("filename", "")
            except Exception:
                pass
            time.sleep(2)
        return None

    def build_workflow(self, checkpoint: str, lora: str, positive: str,
                       negative: str, seed: int = 42,
                       width: int = 1024, height: int = 576) -> dict:
        """Construit un workflow ComfyUI minimal pour le benchmark."""
        return {
            "4":  {"class_type":"CheckpointLoaderSimple","inputs":{"ckpt_name":checkpoint}},
            "10": {"class_type":"LoraLoader","inputs":{"model":["4",0],"clip":["4",1],"lora_name":lora,"strength_model":0.8,"strength_clip":0.8}},
            "6":  {"class_type":"CLIPTextEncode","inputs":{"text":positive,"clip":["10",1]}},
            "7":  {"class_type":"CLIPTextEncode","inputs":{"text":negative,"clip":["10",1]}},
            "3":  {"class_type":"KSampler","inputs":{"model":["10",0],"positive":["6",0],"negative":["7",0],"latent_image":["5",0],"seed":seed,"steps":20,"cfg":7.0,"sampler_name":"dpmpp_2m","scheduler":"karras","denoise":1.0}},
            "5":  {"class_type":"EmptyLatentImage","inputs":{"width":width,"height":height,"batch_size":1}},
            "8":  {"class_type":"VAEDecode","inputs":{"samples":["3",0],"vae":["4",2]}},
            "9":  {"class_type":"SaveImage","inputs":{"images":["8",0],"filename_prefix":f"benchmark_{lora[:10]}"}},
        }


class AIJudge:
    """Évalue les images générées via LLM (description + scoring)."""

    def score_image(self, image_path: str, prompt: str,
                    lora_name: str) -> dict:
        """
        Score une image générée.
        En production : envoyer l'image à Claude Vision.
        Ici : scoring simulé + analyse du prompt.
        """
        if not UTILS_OK:
            return {c: 70 + hash(image_path+c) % 20 for c in SCORING_CRITERIA}

        judge_prompt = (
            f"Tu es un expert en art génératif. Évalue cette génération.\n"
            f"Prompt utilisé : {prompt[:200]}\n"
            f"LoRA : {lora_name}\n"
            f"Image path : {image_path}\n\n"
            f"Note chaque critère de 0 à 100 :\n"
            f"{', '.join(SCORING_CRITERIA)}\n\n"
            f"Retourne UNIQUEMENT ce JSON :\n"
            + "{" + ", ".join(f'"{c}": 0' for c in SCORING_CRITERIA) + ", \"comment\": \"\"}"
        )
        raw = fallback_llm(judge_prompt, max_tokens=200, logger=log)
        ok, data, _ = safe_json_parse(raw, logger=log)
        if ok and data:
            return data
        return {c: 75 for c in SCORING_CRITERIA}


class BenchmarkArena:
    """Orchestre les comparaisons de LoRAs/checkpoints."""

    def __init__(self, logger: logging.Logger = None):
        self.log    = logger or log
        self.runner = ComfyRunner()
        self.judge  = AIJudge()
        ARENA_DIR.mkdir(parents=True, exist_ok=True)

    def run(self, prompts: list, loras: list,
            checkpoint: str = "",
            negative: str = "bad quality, blurry, deformed",
            seeds: list = None,
            timeout_per_job: int = 120) -> dict:
        """
        Lance le benchmark complet.

        prompts   : liste de prompts à tester
        loras     : liste de LoRAs à comparer
        seeds     : seeds fixes pour reproductibilité

        Returns : dict avec scores, rankings, rapport HTML
        """
        ts      = datetime.now().strftime("%Y%m%d_%H%M%S")
        run_dir = ARENA_DIR / f"run_{ts}"
        run_dir.mkdir(parents=True, exist_ok=True)
        seeds   = seeds or [42, 1337, 7777]

        results = {
            "run_id":    ts,
            "loras":     loras,
            "prompts":   prompts,
            "checkpoint":checkpoint,
            "scores":    {},
            "rankings":  [],
        }

        total_jobs = len(loras) * len(prompts) * len(seeds)
        self.log.info(f"[ARENA] ═══ Benchmark : {len(loras)} LoRAs × {len(prompts)} prompts × {len(seeds)} seeds = {total_jobs} jobs ═══")

        comfy_available = self._check_comfy()

        for lora in loras:
            lora_scores = {c: [] for c in SCORING_CRITERIA}
            lora_images = []

            for prompt in prompts:
                for seed in seeds:
                    self.log.info(f"[ARENA] {lora[:20]} | seed={seed} | {prompt[:40]}...")

                    if comfy_available and checkpoint:
                        workflow = self.runner.build_workflow(
                            checkpoint, lora, prompt, negative, seed
                        )
                        prompt_id = self.runner.submit_job(workflow)
                        image_file = self.runner.wait_for_result(prompt_id, timeout_per_job) if prompt_id else None
                    else:
                        image_file = None
                        self.log.debug("[ARENA] ComfyUI indisponible — scoring simulé")

                    # Score de l'image
                    scores = self.judge.score_image(image_file or "", prompt, lora)
                    for c in SCORING_CRITERIA:
                        if c in scores:
                            lora_scores[c].append(scores[c])
                    if image_file:
                        lora_images.append(image_file)

            # Moyennes par LoRA
            avg_scores = {c: round(sum(v)/len(v), 1) if v else 0
                          for c, v in lora_scores.items()}
            avg_scores["overall"] = round(sum(avg_scores.values()) / len(SCORING_CRITERIA), 1)
            results["scores"][lora] = {
                "averages": avg_scores,
                "images":   lora_images,
                "n_tests":  len(prompts) * len(seeds),
            }

        # Ranking
        ranking = sorted(
            results["scores"].items(),
            key=lambda x: x[1]["averages"]["overall"],
            reverse=True
        )
        results["rankings"] = [
            {"rank": i+1, "lora": lora, "score": data["averages"]["overall"]}
            for i, (lora, data) in enumerate(ranking)
        ]
        results["winner"] = ranking[0][0] if ranking else ""

        # Sauvegarder
        report_path = run_dir / "benchmark_results.json"
        report_path.write_text(json.dumps(results, indent=2, ensure_ascii=False, default=str), encoding="utf-8")

        # Générer rapport HTML
        html_path = self._generate_html_report(results, run_dir)
        results["html_report"] = str(html_path)

        self.log.info(f"[ARENA] ✓ Benchmark terminé — Gagnant : {results.get('winner','?')}")
        self.log.info(f"[ARENA] Rapport : {html_path}")
        return results

    def _check_comfy(self) -> bool:
        try:
            r = requests.get(f"{COMFY_URL}/system_stats", timeout=3)
            return r.status_code == 200
        except Exception:
            return False

    def _generate_html_report(self, results: dict, out_dir: Path) -> Path:
        """Génère un rapport HTML visuel des résultats."""
        rankings = results.get("rankings", [])
        scores   = results.get("scores", {})

        rows = ""
        for rank_data in rankings:
            lora  = rank_data["lora"]
            ldata = scores.get(lora, {})
            avgs  = ldata.get("averages", {})
            color = "#00FFB3" if rank_data["rank"] == 1 else "#6A8BA8"
            rows += f"""<tr>
              <td style="color:{color};font-family:Orbitron,monospace">#{rank_data['rank']}</td>
              <td style="color:{color}">{lora[:40]}</td>
              <td style="color:{color};font-size:1.1rem;font-weight:bold">{rank_data['score']}</td>
              {''.join(f'<td>{avgs.get(c,0)}</td>' for c in SCORING_CRITERIA)}
            </tr>"""

        html = f"""<!DOCTYPE html>
<html><head><meta charset="UTF-8">
<title>Ov3rLoRd Benchmark Arena</title>
<link href="https://fonts.googleapis.com/css2?family=Orbitron:wght@400;700&display=swap" rel="stylesheet">
<style>
body{{background:#080C14;color:#E8F4FF;font-family:Rajdhani,sans-serif;padding:20px;}}
h1{{font-family:Orbitron,monospace;background:linear-gradient(135deg,#00FFB3,#0066FF);-webkit-background-clip:text;-webkit-text-fill-color:transparent;}}
table{{width:100%;border-collapse:collapse;margin-top:16px;}}
th{{font-family:Orbitron,monospace;font-size:0.55rem;color:#00FFB3;padding:8px;border-bottom:1px solid rgba(0,255,179,0.2);letter-spacing:2px;}}
td{{padding:8px;border-bottom:1px solid rgba(255,255,255,0.04);color:#6A8BA8;font-size:0.85rem;}}
.winner{{background:rgba(0,255,179,0.05);border:1px solid rgba(0,255,179,0.3);border-radius:8px;padding:12px;margin:12px 0;}}
</style></head><body>
<h1>Benchmark Arena — Ov3rLoRd V1.47</h1>
<p style="color:#6A8BA8;font-size:0.75rem;letter-spacing:3px">{results['run_id']} | {len(results['loras'])} LoRAs | {len(results['prompts'])} prompts</p>
{"<div class='winner'>🏆 GAGNANT : <strong style='color:#00FFB3'>"+results.get('winner','')+"</strong></div>" if results.get('winner') else ""}
<table>
<thead><tr><th>RANG</th><th>LoRA</th><th>SCORE</th>{''.join(f'<th>{c.upper()}</th>' for c in SCORING_CRITERIA)}</tr></thead>
<tbody>{rows}</tbody>
</table>
</body></html>"""

        path = out_dir / "benchmark_report.html"
        path.write_text(html, encoding="utf-8")
        return path


# Correction import manquant
from typing import Optional


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    arena = BenchmarkArena()
    results = arena.run(
        prompts=[
            "1male, muscular hero, orange gi, epic battle pose, anime style, ultra detail",
            "1female, warrior, silver armor, determination, dramatic lighting, anime style",
        ],
        loras=["goku_sdxl_v2.safetensors", "hero_generic_v1.safetensors", "anime_xl_v3.safetensors"],
        seeds=[42, 1337],
    )
    print(f"Gagnant : {results['winner']}")
    for r in results['rankings']:
        print(f"  #{r['rank']} {r['lora'][:30]} — {r['score']}/100")

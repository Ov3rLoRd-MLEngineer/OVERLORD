"""
inpaint_queue.py V1.0
Ov3rLoRd — Onibaku Gumi 鬼爆組
Queue d'inpainting automatique sur frames rejetées par clip_validator.
Stratégie : masque automatique par seuil de différence + re-génération via ComfyUI.
Intégration : appelé par maestro.py si clip_validator retourne des REJECT.
"""

import os
import sys
import json
import time
import logging
import requests
import uuid
from pathlib import Path
from datetime import datetime

# ── PIL pour manipulation masque ───────────────────────────────────────────────
try:
    from PIL import Image, ImageChops, ImageFilter, ImageOps
    PIL_AVAILABLE = True
except ImportError:
    PIL_AVAILABLE = False

# ── Import interne ─────────────────────────────────────────────────────────────
try:
    from audit_logger import AuditLogger
    AUDIT_AVAILABLE = True
except ImportError:
    AUDIT_AVAILABLE = False

try:
    from negative_bank import get_negative
    NEGBANK_AVAILABLE = True
except ImportError:
    NEGBANK_AVAILABLE = False

# ── Configuration ──────────────────────────────────────────────────────────────
PROJECT_ROOT     = Path(r"D:\OVERLORD")
WORKSPACE        = PROJECT_ROOT / "workspace"
COMFYUI_URL      = "http://127.0.0.1:8188"
INPAINT_DIR      = WORKSPACE / "inpaint"
MAX_RETRIES      = 3
POLL_INTERVAL    = 2.0    # secondes entre polls ComfyUI
DIFF_THRESHOLD   = 30     # seuil pixel diff pour masque auto (0-255)
INPAINT_DENOISE  = 0.65   # denoising strength inpaint (conservateur)

logging.basicConfig(
    level=logging.INFO,
    format="[INPAINT] %(asctime)s %(levelname)s — %(message)s",
    datefmt="%H:%M:%S"
)
log = logging.getLogger("inpaint_queue")


# ══════════════════════════════════════════════════════════════════════════════
class InpaintQueue:
    """
    Traite automatiquement les frames rejetées par clip_validator.
    Workflow :
      1. Génère masque automatique (diff pixel entre frame et référence)
      2. Envoie job inpaint à ComfyUI
      3. Poll résultat
      4. Sauvegarde dans inpaint/outputs/
    """

    def __init__(self, run_id: str):
        self.run_id  = run_id
        self.queue   = []
        self.results = []
        INPAINT_DIR.mkdir(parents=True, exist_ok=True)
        (INPAINT_DIR / "masks").mkdir(parents=True, exist_ok=True)
        (INPAINT_DIR / "outputs").mkdir(parents=True, exist_ok=True)

    # ── Chargement depuis rapport CLIP ────────────────────────────────────────
    def load_from_clip_report(self, report: dict) -> int:
        """
        Extrait les frames REJECT du rapport clip_validator.
        Retourne le nombre de frames à traiter.
        """
        rejects = report.get("rejects", [])
        for entry in rejects:
            pair  = entry.get("pair", "")
            parts = pair.split(" → ")
            if len(parts) == 2:
                self.queue.append({
                    "frame":        parts[1].strip(),
                    "reference":    parts[0].strip(),
                    "cosine_score": entry.get("cosine", 0.0),
                })
        log.info(f"{len(self.queue)} frame(s) REJECT chargée(s) dans la queue")
        return len(self.queue)

    def add_frame(
        self,
        frame_path:     "str | Path",
        reference_path: "str | Path" = None,
        prompt:         str = "",
        negative:       str = "",
    ) -> None:
        """Ajout manuel d'une frame à traiter."""
        self.queue.append({
            "frame":        str(frame_path),
            "reference":    str(reference_path) if reference_path else "",
            "prompt":       prompt,
            "negative":     negative,
            "cosine_score": 0.0,
        })

    # ── Génération masque auto ────────────────────────────────────────────────
    def _generate_mask(self, frame_path: Path, ref_path: "Path | None") -> "Path | None":
        """
        Masque par différence pixel entre frame courante et référence.
        Fallback : None (inpaint total) si PIL absent ou ref manquante.
        """
        mask_path = INPAINT_DIR / "masks" / f"mask_{frame_path.stem}.png"

        if not PIL_AVAILABLE:
            log.warning("PIL absent — masque blanc (inpaint complet)")
            return None

        try:
            img_b = Image.open(frame_path).convert("RGB")

            if ref_path and Path(ref_path).exists():
                img_a = Image.open(ref_path).convert("RGB").resize(img_b.size)
                diff  = ImageChops.difference(img_a, img_b).convert("L")
                mask  = diff.point(lambda p: 255 if p > DIFF_THRESHOLD else 0)
                mask  = mask.filter(ImageFilter.MaxFilter(9))
            else:
                mask = Image.new("L", img_b.size, 255)

            mask.save(str(mask_path))
            log.info(f"Masque généré → {mask_path.name}")
            return mask_path

        except Exception as e:
            log.error(f"Erreur génération masque: {e}")
            return None

    # ── Workflow ComfyUI inpaint minimal ─────────────────────────────────────
    def _build_inpaint_workflow(
        self,
        image_path: Path,
        mask_path:  "Path | None",
        prompt:     str,
        negative:   str,
    ) -> dict:
        """Workflow ComfyUI minimal pour inpainting SDXL fabricatedXL."""
        wf = {
            "1": {
                "class_type": "CheckpointLoaderSimple",
                "inputs": {"ckpt_name": "fabricatedXL_v70.safetensors"}
            },
            "2": {
                "class_type": "CLIPTextEncode",
                "inputs": {
                    "text": prompt or "masterpiece, best quality, anime style",
                    "clip": ["1", 1]
                }
            },
            "3": {
                "class_type": "CLIPTextEncode",
                "inputs": {
                    "text": negative or "bad anatomy, blurry",
                    "clip": ["1", 1]
                }
            },
            "4": {
                "class_type": "LoadImage",
                "inputs": {"image": str(image_path)}
            },
            "5": {
                "class_type": "VAEEncode",
                "inputs": {
                    "pixels": ["4", 0],
                    "vae":    ["1", 2]
                }
            },
            "6": {
                "class_type": "KSampler",
                "inputs": {
                    "model":        ["1", 0],
                    "positive":     ["2", 0],
                    "negative":     ["3", 0],
                    "latent_image": ["5", 0],
                    "seed":         int(time.time()) % 999999,
                    "steps":        20,
                    "cfg":          7.0,
                    "sampler_name": "dpmpp_2m_sde",
                    "scheduler":    "karras",
                    "denoise":      INPAINT_DENOISE,
                }
            },
            "7": {
                "class_type": "VAEDecode",
                "inputs": {"samples": ["6", 0], "vae": ["1", 2]}
            },
            "8": {
                "class_type": "SaveImage",
                "inputs": {
                    "images":            ["7", 0],
                    "filename_prefix":   f"inpaint_{self.run_id}"
                }
            },
        }

        if mask_path and Path(mask_path).exists():
            wf["9"] = {
                "class_type": "LoadImage",
                "inputs": {"image": str(mask_path)}
            }
            wf["5"]["class_type"]              = "VAEEncodeForInpaint"
            wf["5"]["inputs"]["mask"]          = ["9", 0]
            wf["5"]["inputs"]["grow_mask_by"]  = 6

        return wf

    # ── Soumission ComfyUI ────────────────────────────────────────────────────
    def _submit_to_comfyui(self, workflow: dict) -> "str | None":
        try:
            client_id = str(uuid.uuid4())
            r = requests.post(
                f"{COMFYUI_URL}/prompt",
                json={"prompt": workflow, "client_id": client_id},
                timeout=30,
            )
            r.raise_for_status()
            pid = r.json().get("prompt_id")
            log.info(f"Job soumis → prompt_id={pid}")
            return pid
        except Exception as e:
            log.error(f"Erreur soumission ComfyUI: {e}")
            return None

    # ── Poll résultat ─────────────────────────────────────────────────────────
    def _poll_result(self, prompt_id: str, timeout: int = 300) -> "Path | None":
        deadline = time.time() + timeout
        while time.time() < deadline:
            try:
                r = requests.get(f"{COMFYUI_URL}/history/{prompt_id}", timeout=10)
                r.raise_for_status()
                hist = r.json()
                if prompt_id in hist:
                    for node_out in hist[prompt_id].get("outputs", {}).values():
                        images = node_out.get("images", [])
                        if images:
                            info = images[0]
                            return (
                                Path(r"D:\Ov3rLoRd AI\ComfyUI\output")
                                / info.get("subfolder", "")
                                / info.get("filename", "")
                            )
            except Exception as e:
                log.warning(f"Poll erreur: {e}")
            time.sleep(POLL_INTERVAL)
        log.error(f"Timeout ({timeout}s) pour prompt_id={prompt_id}")
        return None

    # ── Traitement queue ──────────────────────────────────────────────────────
    def process(
        self,
        default_prompt:   str = "",
        default_negative: str = "",
        universe:         str = "evangelion",
        character:        str = "asuka_plugsuit",
    ) -> list:
        """Traite toutes les frames de la queue. Retourne la liste des résultats."""
        if not self.queue:
            log.info("Queue vide — rien à traiter")
            return []

        log.info(f"=== InpaintQueue — {len(self.queue)} frame(s) — Run {self.run_id} ===")

        if not default_negative and NEGBANK_AVAILABLE:
            default_negative = get_negative(character=character, universe=universe)

        for i, job in enumerate(self.queue):
            log.info(f"[{i+1}/{len(self.queue)}] {job['frame']}")

            frame_path = Path(job["frame"])
            if not frame_path.exists():
                alt = WORKSPACE / "outputs" / self.run_id / frame_path.name
                if alt.exists():
                    frame_path = alt
                else:
                    log.warning(f"Frame introuvable : {frame_path}")
                    self.results.append({**job, "status": "SKIP", "reason": "not found"})
                    continue

            ref_path  = Path(job.get("reference", "")) if job.get("reference") else None
            mask_path = self._generate_mask(frame_path, ref_path)
            prompt    = job.get("prompt")   or default_prompt
            negative  = job.get("negative") or default_negative
            wf        = self._build_inpaint_workflow(frame_path, mask_path, prompt, negative)

            success = False
            for attempt in range(1, MAX_RETRIES + 1):
                pid = self._submit_to_comfyui(wf)
                if not pid:
                    time.sleep(2)
                    continue
                result_path = self._poll_result(pid)
                if result_path:
                    dest = INPAINT_DIR / "outputs" / f"{frame_path.stem}_inpainted.png"
                    try:
                        if PIL_AVAILABLE and result_path.exists():
                            Image.open(result_path).save(str(dest))
                    except Exception:
                        dest = result_path

                    self.results.append({
                        **job,
                        "status":      "OK",
                        "attempt":     attempt,
                        "output_path": str(dest),
                        "prompt_id":   pid,
                    })

                    if AUDIT_AVAILABLE:
                        try:
                            AuditLogger().log_event(
                                run_id=self.run_id,
                                event_type="inpaint_success",
                                data=json.dumps({"frame": job["frame"], "attempt": attempt}),
                            )
                        except Exception:
                            pass

                    success = True
                    break

            if not success:
                self.results.append({**job, "status": "FAIL", "reason": "max retries"})
                log.error(f"{frame_path.name} — échec après {MAX_RETRIES} tentatives")

        report_path = WORKSPACE / "reports" / f"inpaint_report_{self.run_id}.json"
        report_path.parent.mkdir(parents=True, exist_ok=True)
        with open(report_path, "w", encoding="utf-8") as f:
            json.dump({
                "run_id":    self.run_id,
                "timestamp": datetime.now().isoformat(),
                "total":     len(self.queue),
                "ok":        sum(1 for r in self.results if r["status"] == "OK"),
                "fail":      sum(1 for r in self.results if r["status"] == "FAIL"),
                "results":   self.results,
            }, f, indent=2, ensure_ascii=False)
        log.info(f"Rapport inpaint → {report_path}")
        return self.results


# ══════════════════════════════════════════════════════════════════════════════
def process_clip_rejects(
    run_id:      str,
    clip_report: dict,
    prompt:      str = "",
    negative:    str = "",
    universe:    str = "evangelion",
    character:   str = "asuka_plugsuit",
) -> list:
    """Point d'entrée public pour maestro.py."""
    iq    = InpaintQueue(run_id)
    count = iq.load_from_clip_report(clip_report)
    if count == 0:
        return []
    return iq.process(
        default_prompt=prompt,
        default_negative=negative,
        universe=universe,
        character=character,
    )


# ══════════════════════════════════════════════════════════════════════════════
if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Inpaint Queue — Ov3rLoRd")
    parser.add_argument("--run-id",      required=True)
    parser.add_argument("--clip-report", default="")
    parser.add_argument("--frame",       default="")
    parser.add_argument("--prompt",      default="")
    parser.add_argument("--negative",    default="")
    parser.add_argument("--universe",    default="evangelion")
    parser.add_argument("--character",   default="asuka_plugsuit")
    args = parser.parse_args()

    iq = InpaintQueue(args.run_id)

    if args.clip_report and Path(args.clip_report).exists():
        with open(args.clip_report, "r", encoding="utf-8") as f:
            iq.load_from_clip_report(json.load(f))
    elif args.frame:
        iq.add_frame(args.frame, prompt=args.prompt, negative=args.negative)
    else:
        print("Fournir --clip-report ou --frame")
        sys.exit(1)

    results = iq.process(
        default_prompt=args.prompt,
        default_negative=args.negative,
        universe=args.universe,
        character=args.character,
    )
    print(json.dumps(results, indent=2, ensure_ascii=False))

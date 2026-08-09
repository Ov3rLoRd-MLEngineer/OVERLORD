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
visual_validator.py V1.0
Ov3rLoRd -- Ov3rLoRd
Validation visuelle par QwenVL via Ollama.
Roles specialises : asuka, rei, background, fx, anatomy, generic.
Retourne PASS/FAIL + defauts detectes -> feed direct inpaint_queue.
"""

import json
import logging
import requests
import base64
from pathlib import Path
from datetime import datetime
import os
import sys

# ── QwenVL prompts dynamiques V2.22 ───────────────────────────────────────────
try:
    sys.path.insert(0, str(Path(__file__).parent.parent))
    from watchdog_config import load_config as _load_wd, qwenvl_prompts_for_scene
    _WD_CFG     = _load_wd()
    _SCENE_TYPE = _WD_CFG.get("scene_type", "default")
    try:
        from agents.context_bus import get_bus as _get_bus
        _bus          = _get_bus()
        _CHARACTER    = _bus.read("director.character") or "asuka"
        _override_pos = _bus.read("qwenvl.prompt_positive") or ""
        _override_neg = _bus.read("qwenvl.prompt_negative") or ""
    except Exception:
        _CHARACTER    = "asuka"
        _override_pos = ""
        _override_neg = ""
    _QWEN_PROMPTS = qwenvl_prompts_for_scene(_SCENE_TYPE, _CHARACTER)
    if _override_pos:
        _QWEN_PROMPTS["positive"] = _override_pos
    if _override_neg:
        _QWEN_PROMPTS["negative"] = _override_neg
except Exception:
    _QWEN_PROMPTS = {
        "positive": "correct anatomy, single character, masterpiece quality",
        "negative": "extra limbs, deformed, multiple characters, low quality",
        "focus":    "overall quality",
    }

QWENVL_SYSTEM = (
    "You are a quality control expert for anime production. "
    "Analyze the image and check: "
    f"EXPECT: {_QWEN_PROMPTS['positive']}. "
    f"REJECT IF: {_QWEN_PROMPTS['negative']}. "
    f"FOCUS ON: {_QWEN_PROMPTS['focus']}. "
    'Reply with JSON: {"pass": true/false, "score": 0-100, "issues": [...]}'
)

try:
    from agents.inpaint_queue import InpaintQueue
    INPAINT_OK = True
except Exception:
    INPAINT_OK = False

try:
    from agents.audit_logger import AuditLogger
    AUDIT_OK = True
except Exception:
    AUDIT_OK = False

OLLAMA_URL     = "http://127.0.0.1:11434"
QWEN_MODEL     = "qwen2.5vl:7b"
REPORTS_DIR    = Path("workspace/reports")
PASS_THRESHOLD = 0.6

log = logging.getLogger("visual_validator")

# ══════════════════════════════════════════════════════════════════════
# Prompts systeme specialises par role

SYSTEM_PROMPTS = {

    "asuka": (
        "You are a quality control specialist for Neon Genesis Evangelion anime production.\n"
        "Your task: verify that the image correctly depicts Asuka Langley Soryu.\n"
        "Required traits to check:\n"
        "- Hair: orange/auburn, medium length, usually twin braids or loose\n"
        "- Eyes: vivid blue, confident or aggressive expression\n"
        "- Build: slim, teenage girl\n"
        "- Plugsuit (if present): red/dark red, form-fitting\n"
        "- No blue hair, no wrong eye color, no other EVA characters\n"
        "Respond ONLY with a JSON object, no markdown, no explanation:\n"
        '{"pass": true/false, "score": 0.0-1.0, "defects": ["list of issues"], '
        '"inpaint_zones": ["face", "hair", "body", "outfit"], "notes": "brief"}'
    ),

    "rei": (
        "You are a quality control specialist for Neon Genesis Evangelion anime production.\n"
        "Your task: verify that the image correctly depicts Rei Ayanami.\n"
        "Required traits to check:\n"
        "- Hair: short blue or blue-grey\n"
        "- Eyes: red/crimson, pale skin, calm or distant expression\n"
        "- Plugsuit (if present): white or light blue\n"
        "- No orange hair, no wrong eye color\n"
        "Respond ONLY with a JSON object, no markdown, no explanation:\n"
        '{"pass": true/false, "score": 0.0-1.0, "defects": ["list of issues"], '
        '"inpaint_zones": ["face", "hair", "body", "outfit"], "notes": "brief"}'
    ),

    "background": (
        "You are a quality control specialist for anime background art.\n"
        "Your task: verify composition, perspective, and visual consistency.\n"
        "Check:\n"
        "- Correct perspective lines (no warping or impossible geometry)\n"
        "- No floating disconnected objects\n"
        "- Consistent light source direction\n"
        "- No text, watermark, or signature artifacts\n"
        "- Style consistency (anime illustration, not photorealistic)\n"
        "Respond ONLY with a JSON object, no markdown, no explanation:\n"
        '{"pass": true/false, "score": 0.0-1.0, "defects": ["list of issues"], '
        '"inpaint_zones": ["background", "lighting", "perspective"], "notes": "brief"}'
    ),

    "fx": (
        "You are a quality control specialist for anime visual effects.\n"
        "Your task: verify that FX elements (AT Field, explosions, energy beams, "
        "impact frames, light shafts) are coherent and well-integrated.\n"
        "Check:\n"
        "- FX does not completely obscure the main character face\n"
        "- Color coherence with overall scene lighting\n"
        "- No obvious repeating tile patterns in energy effects\n"
        "- FX edges blend naturally with background\n"
        "Respond ONLY with a JSON object, no markdown, no explanation:\n"
        '{"pass": true/false, "score": 0.0-1.0, "defects": ["list of issues"], '
        '"inpaint_zones": ["fx_layer", "edges", "blending"], "notes": "brief"}'
    ),

    "anatomy": (
        "You are a quality control specialist for anime character anatomy.\n"
        "Your task: detect anatomy errors with high precision.\n"
        "Check strictly:\n"
        "- Hands: correct number of fingers (exactly 5 per hand), no fused or extra fingers\n"
        "- Arms: correct count (exactly 2), correct proportions\n"
        "- Face: exactly two eyes, correct placement, no melting or distorted features\n"
        "- Body: no missing limbs, no duplicated body parts, no impossible bends\n"
        "- Neck: normal length and position\n"
        "Respond ONLY with a JSON object, no markdown, no explanation:\n"
        '{"pass": true/false, "score": 0.0-1.0, "defects": ["list of issues"], '
        '"inpaint_zones": ["hands", "face", "arms", "body"], "notes": "brief"}'
    ),

    "generic": (
        "You are a quality control specialist for anime image production.\n"
        "Check: anatomy errors, watermarks, style consistency, blurriness, "
        "artifacts, and composition issues.\n"
        "Respond ONLY with a JSON object, no markdown, no explanation:\n"
        '{"pass": true/false, "score": 0.0-1.0, "defects": ["list of issues"], '
        '"inpaint_zones": [], "notes": "brief"}'
    ),
}


# ══════════════════════════════════════════════════════════════════════
class VisualValidator:
    """
    Valide une image via QwenVL (Ollama).
    Si FAIL et auto_inpaint=True : alimente inpaint_queue directement.

    Usage :
        vv = VisualValidator()
        result = vv.validate("workspace/archive/RUN/frame.png",
                             role="asuka", run_id="RUN_001")
    """

    def __init__(self, model: str = QWEN_MODEL, threshold: float = PASS_THRESHOLD):
        self.model     = model
        self.threshold = threshold
        REPORTS_DIR.mkdir(parents=True, exist_ok=True)

    @staticmethod
    def _encode(path: Path) -> str:
        return base64.b64encode(path.read_bytes()).decode("utf-8")

    def _call_qwen(self, image_path: Path, role: str, extra_prompt: str = "") -> dict:
        system  = SYSTEM_PROMPTS.get(role, SYSTEM_PROMPTS["generic"])
        img_b64 = self._encode(image_path)

        user_msg = f"Analyze this image for quality control. Role: {role}."
        if extra_prompt:
            user_msg += f" Additional context: {extra_prompt}"

        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user_msg, "images": [img_b64]},
            ],
            "stream": False,
        }

        try:
            r = requests.post(f"{OLLAMA_URL}/api/chat", json=payload, timeout=120)
            r.raise_for_status()
            content = r.json()["message"]["content"].strip()
            if content.startswith("```"):
                parts   = content.split("```")
                content = parts[1].lstrip("json").strip() if len(parts) > 1 else content[3:]
            return json.loads(content)
        except json.JSONDecodeError as e:
            log.warning(f"[VV] JSON QwenVL invalide: {e} -- fallback PASS conservateur")
            return {"pass": True, "score": 0.5, "defects": [],
                    "inpaint_zones": [], "notes": "json parse error"}
        except Exception as e:
            log.error(f"[VV] Erreur appel QwenVL: {e}")
            return {"pass": True, "score": 0.5, "defects": [],
                    "inpaint_zones": [], "notes": str(e)}

    def validate(
        self,
        image_path:   "str | Path",
        role:          str  = "generic",
        run_id:        str  = "",
        shot_id:       str  = "",
        prompt:        str  = "",
        extra_prompt:  str  = "",
        auto_inpaint:  bool = True,
    ) -> dict:
        image_path = Path(image_path)
        if not image_path.exists():
            log.error(f"[VV] Image introuvable: {image_path}")
            return {"pass": False, "score": 0.0,
                    "defects": ["image not found"], "inpaint_zones": [], "notes": ""}

        log.info(f"[VV] Validation role={role} -- {image_path.name}")
        result = self._call_qwen(image_path, role, extra_prompt)

        result.setdefault("pass",          True)
        result.setdefault("score",         0.5)
        result.setdefault("defects",       [])
        result.setdefault("inpaint_zones", [])
        result.setdefault("notes",         "")

        if result["score"] < self.threshold:
            result["pass"] = False

        status = "PASS" if result["pass"] else "FAIL"
        log.info(f"[VV] {status} | score={result['score']:.2f} | defects={len(result['defects'])}")
        for d in result["defects"]:
            log.warning(f"[VV]   defect: {d}")

        # Audit
        if AUDIT_OK and run_id:
            try:
                AuditLogger().log_event(
                    run_id=run_id,
                    event_type=f"vv_{status.lower()}",
                    data=json.dumps({
                        "image":   str(image_path),
                        "role":    role,
                        "score":   result["score"],
                        "defects": result["defects"],
                    }),
                )
            except Exception:
                pass

        # Auto-inpaint si FAIL
        if not result["pass"] and auto_inpaint and INPAINT_OK and run_id:
            log.info(f"[VV] FAIL -> inpaint auto: {image_path.name}")
            try:
                iq = InpaintQueue(run_id)
                iq.add_frame(frame_path=image_path, prompt=prompt)
                iq.process()
            except Exception as e:
                log.error(f"[VV] Inpaint auto erreur: {e}")

        # Rapport JSON
        try:
            rp = REPORTS_DIR / f"vv_{run_id}_{image_path.stem}.json"
            with open(rp, "w", encoding="utf-8") as f:
                json.dump({
                    "timestamp": datetime.now().isoformat(),
                    "image":     str(image_path),
                    "role":      role,
                    "run_id":    run_id,
                    "shot_id":   shot_id,
                    "result":    result,
                }, f, indent=2, ensure_ascii=False)
        except Exception:
            pass

        return result

    def validate_run(
        self,
        run_id:       str,
        image_dir:    "str | Path",
        role_map:     dict = None,
        default_role: str  = "anatomy",
        auto_inpaint: bool = True,
    ) -> dict:
        """
        Valide toutes les images d'un run.
        role_map : {"S01": "asuka", "S02": "background", ...}
        """
        image_dir = Path(image_dir)
        if not image_dir.exists():
            log.error(f"[VV] Dossier introuvable: {image_dir}")
            return {"run_id": run_id, "total": 0, "pass": 0, "fail": 0, "results": []}

        images  = sorted(image_dir.glob("*.png")) + sorted(image_dir.glob("*.jpg"))
        summary = {"run_id": run_id, "total": len(images),
                   "pass": 0, "fail": 0, "results": []}

        log.info(f"[VV] Batch {run_id} -- {len(images)} images")

        for img in images:
            shot_id = img.stem.split("_")[0] if "_" in img.stem else img.stem
            role    = (role_map or {}).get(shot_id, default_role)
            r       = self.validate(
                image_path=img, role=role, run_id=run_id,
                shot_id=shot_id, auto_inpaint=auto_inpaint,
            )
            summary["results"].append({"image": img.name, "role": role, **r})
            if r["pass"]:
                summary["pass"] += 1
            else:
                summary["fail"] += 1

        log.info(f"[VV] Batch -- PASS:{summary['pass']} FAIL:{summary['fail']}/{summary['total']}")
        return summary


# ══════════════════════════════════════════════════════════════════════
def validate_run(run_id: str, image_dir: str,
                 role_map: dict = None,
                 default_role: str = "anatomy") -> dict:
    """Point d'entree public pour maestro.py."""
    return VisualValidator().validate_run(
        run_id=run_id, image_dir=image_dir,
        role_map=role_map, default_role=default_role,
    )


# ══════════════════════════════════════════════════════════════════════
if __name__ == "__main__":
    import argparse
    logging.basicConfig(
        level=logging.INFO,
        format="[VV] %(asctime)s %(levelname)s -- %(message)s"
    )
    parser = argparse.ArgumentParser(description="Visual Validator -- Ov3rLoRd")
    parser.add_argument("--image",        default="",  help="Image a valider")
    parser.add_argument("--role",         default="generic",
                        choices=list(SYSTEM_PROMPTS.keys()))
    parser.add_argument("--run-id",       default="test")
    parser.add_argument("--no-inpaint",   action="store_true")
    parser.add_argument("--batch",        default="", help="Dossier batch")
    parser.add_argument("--default-role", default="anatomy")
    args = parser.parse_args()

    vv = VisualValidator()
    if args.batch:
        out = vv.validate_run(
            run_id=args.run_id, image_dir=args.batch,
            default_role=args.default_role,
            auto_inpaint=not args.no_inpaint,
        )
    else:
        if not args.image:
            print("Fournir --image ou --batch")
            raise SystemExit(1)
        out = vv.validate(
            image_path=args.image, role=args.role,
            run_id=args.run_id, auto_inpaint=not args.no_inpaint,
        )
    print(json.dumps(out, indent=2, ensure_ascii=False))

"""
agents/comfy_autoconfig.py — ComfyUI Auto-Configurateur V1.49
FIX V1.49k : context_bus + ASCII log (emoji check remplace).
"""
import json
import logging
import requests
from pathlib import Path

try:
    from agents.context_bus import get_bus
    BUS_OK = True
except ImportError:
    BUS_OK = False

log = logging.getLogger("comfy_autoconfig")
COMFY_URL   = "http://127.0.0.1:8188"
CONFIG_FILE = Path("comfy_path.cfg")


def get_comfy_path() -> Path | None:
    if CONFIG_FILE.exists():
        for line in CONFIG_FILE.read_text().splitlines():
            if line.startswith("COMFY_PATH="):
                p = Path(line.split("=",1)[1].strip())
                if p.exists():
                    return p
    for candidate in [
        Path("D:/ComfyUI_windows_portable"), Path("D:/ComfyUI"),
        Path("C:/ComfyUI_windows_portable"), Path("C:/ComfyUI"),
    ]:
        if candidate.exists():
            return candidate
    return None


def scan_models(comfy_path: Path) -> dict:
    models_dir = comfy_path / "models"
    found = {"checkpoints":[],"loras":[],"vae":[],"controlnet":[],"upscale_models":[]}
    for key in found:
        folder = models_dir / key
        if folder.exists():
            found[key] = ([f.name for f in folder.glob("*.safetensors")] +
                          [f.name for f in folder.glob("*.ckpt")] +
                          [f.name for f in folder.glob("*.pth")])
    return found


def get_comfy_models_api() -> dict:
    try:
        r = requests.get(f"{COMFY_URL}/object_info", timeout=5)
        if r.status_code == 200:
            data  = r.json()
            ckpts = (data.get("CheckpointLoaderSimple",{})
                        .get("input",{}).get("required",{}).get("ckpt_name",[]))
            return {"checkpoints": ckpts[0] if ckpts else []}
    except Exception:
        pass
    return {}


def update_workflow(workflow_path: Path, models: dict, logger=None) -> int:
    _log = logger or log
    if not workflow_path.exists():
        _log.warning(f"[AUTOCONFIG] Workflow introuvable : {workflow_path}")
        return 0
    try:
        wf = json.loads(workflow_path.read_text(encoding="utf-8"))
    except Exception as e:
        _log.error(f"[AUTOCONFIG] Erreur lecture workflow : {e}")
        return 0

    updated    = 0
    checkpoints = models.get("checkpoints", [])
    if not checkpoints:
        _log.warning("[AUTOCONFIG] Aucun checkpoint trouve")
        return 0

    best_ckpt = checkpoints[0]
    for ckpt in checkpoints:
        if "noob" in ckpt.lower() or "pony" in ckpt.lower():
            best_ckpt = ckpt
            break

    for nid, node in wf.items():
        ct = node.get("class_type","")
        if ct == "CheckpointLoaderSimple":
            old = node["inputs"].get("ckpt_name","")
            if old not in checkpoints and checkpoints:
                node["inputs"]["ckpt_name"] = best_ckpt
                # FIX : emoji remplace par ASCII
                _log.info(f"[AUTOCONFIG] Noeud {nid} : {old} -> {best_ckpt}")
                updated += 1
        elif ct == "Image Saver" and best_ckpt:
            node["inputs"]["modelname"] = Path(best_ckpt).stem
        elif ct in ("VAELoader","VAEDecode"):
            vaes = models.get("vae",[])
            if vaes and node["inputs"].get("vae_name","") not in vaes:
                node["inputs"]["vae_name"] = vaes[0]
                updated += 1

    if updated:
        workflow_path.write_text(json.dumps(wf, indent=2, ensure_ascii=False), encoding="utf-8")
        # FIX : emoji OK remplace par ASCII
        _log.info(f"[AUTOCONFIG] OK {updated} noeuds mis a jour dans {workflow_path.name}")
    return updated


def run_autoconfig(logger=None) -> dict:
    _log   = logger or log
    _log.info("[AUTOCONFIG] Demarrage scan modeles ComfyUI...")
    result = {"status":"ok","models":{},"updated":0,"warnings":[]}

    api_models = get_comfy_models_api()
    if api_models.get("checkpoints"):
        _log.info(f"[AUTOCONFIG] API ComfyUI -> {len(api_models['checkpoints'])} checkpoints")
        result["models"] = api_models

    comfy_path = get_comfy_path()
    if comfy_path:
        disk_models = scan_models(comfy_path)
        for k,v in disk_models.items():
            if v:
                _log.info(f"[AUTOCONFIG] {k} : {len(v)} fichier(s)")
        result["models"].update(disk_models)
    else:
        result["warnings"].append("ComfyUI non trouve — scan disque impossible")

    wf_path = Path("Combined_V35_API.json")
    if wf_path.exists() and result["models"].get("checkpoints"):
        result["updated"] = update_workflow(wf_path, result["models"], _log)
    else:
        result["warnings"].append("Combined_V35_API.json introuvable ou aucun checkpoint")

    # Publier sur le bus
    if BUS_OK:
        try:
            bus = get_bus()
            bus.write("autoconfig.checkpoints",
                      len(result["models"].get("checkpoints",[])), agent_id="autoconfig")
            bus.write("autoconfig.updated",    result["updated"],  agent_id="autoconfig")
            bus.write("autoconfig.status",     result["status"],   agent_id="autoconfig")
        except Exception:
            pass

    _log.info(f"[AUTOCONFIG] OK Termine — {result['updated']} noeuds mis a jour")
    return result


if __name__ == "__main__":
    import sys, io
    if hasattr(sys.stdout,'buffer'):
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
    logging.basicConfig(level=logging.INFO)
    r = run_autoconfig()
    print(json.dumps(r, indent=2, ensure_ascii=False))
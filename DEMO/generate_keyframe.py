"""Genere une keyframe SDXL stylisee (etape 1 du Workflow A) pour un nouveau
PMX+VMD : rendu Blender previz (pose de reference) -> img2img SDXL.

Usage :
    py -3.12 DEMO/generate_keyframe.py --run-name v2 \
        --pmx "E:/Data Demo/_extracted/.../Tsatou....pmx" \
        --vmd "E:/Data Demo/_extracted/.../Salvadora da dance.vmd" \
        --seed 111111111
"""
import argparse
import json
import os
import shutil
import subprocess
import time
import urllib.request

COMFY = "http://127.0.0.1:8188"
COMFY_INPUT_DIR = r"D:\Ov3rLoRd AI\ComfyUI\input"
KEYFRAME_TEMPLATE = os.path.join("workspace", "comfyui_workflows", "sdxl_keyframe_img2img.json")
BLENDER_EXE = r"C:\Program Files\Blender Foundation\Blender 5.1\blender.exe"
BLENDER_SCRIPT = os.path.join("agents", "production_video", "blender_previz.py")


def render_pose_reference(pmx, vmd, out_dir, run_name):
    out_dir = os.path.abspath(out_dir)
    os.makedirs(out_dir, exist_ok=True)
    cmd = [
        BLENDER_EXE, "-b", "-P", BLENDER_SCRIPT, "--",
        "--mode", "mmd", "--pmx", pmx, "--vmd", vmd,
        "--shot-plan", "zoom_in:0",
        "--out", out_dir, "--res", "1024", "1536", "--samples", "32",
    ]
    r = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace", cwd=os.getcwd())
    if r.returncode != 0:
        raise RuntimeError(f"Blender previz a echoue:\n{r.stdout[-3000:]}\n{r.stderr[-3000:]}")
    out_png = os.path.join(out_dir, "previz_clip01_zoom_in.png")
    renamed = os.path.join(out_dir, f"keyframe_source_{run_name}.png")
    shutil.copy2(out_png, renamed)
    return renamed


def queue_prompt(workflow, client_id):
    body = json.dumps({"prompt": workflow, "client_id": client_id}).encode("utf-8")
    req = urllib.request.Request(f"{COMFY}/prompt", data=body, headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.load(resp)


def wait_for_completion(prompt_id, timeout=300, poll=3):
    start = time.time()
    while time.time() - start < timeout:
        with urllib.request.urlopen(f"{COMFY}/history/{prompt_id}", timeout=30) as resp:
            hist = json.load(resp)
        if prompt_id in hist:
            entry = hist[prompt_id]
            status = entry.get("status", {})
            if status.get("completed") is True:
                return entry
            if status.get("status_str") == "error":
                raise RuntimeError(f"ComfyUI execution error: {json.dumps(status)}")
        time.sleep(poll)
    raise TimeoutError(f"prompt {prompt_id} pas termine apres {timeout}s")


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--run-name", required=True)
    p.add_argument("--pmx", required=True)
    p.add_argument("--vmd", required=True)
    p.add_argument("--seed", type=int, required=True)
    p.add_argument("--out-dir", default=os.path.join("DEMO", "frames", "keyframes"))
    args = p.parse_args()

    print(f"[keyframe {args.run_name}] rendu Blender previz pose reference...", flush=True)
    previz_png = render_pose_reference(args.pmx, args.vmd, args.out_dir, args.run_name)
    print(f"[keyframe {args.run_name}] previz -> {previz_png}", flush=True)

    comfy_input_name = f"keyframe_source_{args.run_name}.png"
    shutil.copy2(previz_png, os.path.join(COMFY_INPUT_DIR, comfy_input_name))

    with open(KEYFRAME_TEMPLATE, encoding="utf-8") as f:
        wf = json.load(f)
    wf["3"]["inputs"]["image"] = comfy_input_name
    wf["7"]["inputs"]["seed"] = args.seed
    wf["9"]["inputs"]["filename_prefix"] = f"DemoMiku30s/keyframes/sdxl_keyframe_{args.run_name}"

    client_id = f"demo30s-keyframe-{args.run_name}"
    r = queue_prompt(wf, client_id)
    if r.get("node_errors"):
        raise RuntimeError(f"node_errors keyframe: {json.dumps(r['node_errors'])}")
    prompt_id = r["prompt_id"]
    print(f"[keyframe {args.run_name}] PROMPT_ID={prompt_id}, en attente...", flush=True)
    t0 = time.time()
    entry = wait_for_completion(prompt_id)
    dt = time.time() - t0

    out_node = entry["outputs"]["9"]
    info = out_node["images"][0]
    if "fullpath" in info:
        keyframe_path = info["fullpath"]
    else:
        keyframe_path = os.path.join(r"D:\Ov3rLoRd AI\ComfyUI\output", info.get("subfolder", ""), info["filename"])
    print(f"RESULT keyframe: {dt:.1f}s -> {keyframe_path}")


if __name__ == "__main__":
    main()

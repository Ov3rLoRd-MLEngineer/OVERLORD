"""
Validation empirique du fix camera/objet-non-specifie-hallucine (branche
fix-wildcards-camera-hallucination) sur un vrai batch ComfyUI FootSegNet -
adapte de handsegnet/validate_wildcard_fix.py (meme logique, deja validee
18/18 sur HandSegNet), jamais fait tourner a l'echelle sur ce module.

Reutilise directement les fonctions de generate_dataset.py (meme
construction de workflow, meme submit/poll ComfyUI) pour rester fidele au
chemin de code de production, mais redirige la sortie vers un dossier de
test dedie (dataset/wildcard_fix_validation/, gitignore) plutot que
dataset/raw/ - ce batch sert a verifier le fix, pas a alimenter le dataset
d'entrainement.

Selectionne des index dans une plage haute (>=10000, tres au-dela des ~641
index deja generes en production) pour garantir des seeds jamais generes,
puis biaise la selection vers les deux points corriges sur ce module plutot
qu'un tirage uniforme :
- "feet close to viewer" (footsegnet/prompts_wildcards.txt L18, ex "feet
  close to camera")
- "a high shelf" (footsegnet/wildcards/poses.txt L56, ex "tip-toe reaching
  for something overhead")

Usage :
    py -3.12 footsegnet/validate_wildcard_fix.py --scan --count 18
    py -3.12 footsegnet/validate_wildcard_fix.py --indices 10001,10305,...
    py -3.12 footsegnet/validate_wildcard_fix.py --scan --count 18 --check-only
"""
import argparse
import json
import random
import sys
import time
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import generate_dataset as gd  # noqa: E402  (reutilise workflow/submit/poll)

TEST_DIR = gd.FOOTSEGNET_ROOT / "dataset" / "wildcard_fix_validation"
TEST_MANIFEST = TEST_DIR / "manifest.json"

BANNED_SUBSTRINGS = ["camera", "something overhead"]
TARGET_A = "feet close to viewer"
TARGET_B = "a high shelf"


def find_biased_indices(count, scan_start=10000, scan_end=20000):
    """Parcourt une plage d'index jamais generee et classe chaque index
    selon qu'il declenche feet-close-to-viewer / high-shelf / les deux,
    puis retourne un melange biaise vers ces points plutot qu'un tirage
    uniforme (objectif : test cible, pas representatif du dataset reel)."""
    templates = gd.load_templates()
    both, a_only, b_only = [], [], []
    for i in range(scan_start, scan_end):
        seed = gd.BASE_SEED + i * gd.SEED_STRIDE
        rng = random.Random(seed)
        template = rng.choice(templates)
        prompt = gd.resolve_prompt(template, rng)
        has_a = TARGET_A in prompt
        has_b = TARGET_B in prompt
        if has_a and has_b:
            both.append(i)
        elif has_a:
            a_only.append(i)
        elif has_b:
            b_only.append(i)
        if len(both) + len(a_only) + len(b_only) >= count * 3:
            break

    n_both = min(len(both), max(1, count // 6))
    n_a = min(len(a_only), max(1, count * 2 // 5))
    n_b = count - n_both - n_a
    n_b = min(n_b, len(b_only))

    chosen = both[:n_both] + a_only[:n_a] + b_only[:n_b]
    return sorted(chosen)


def scan_png_metadata(png_path):
    """Relit les metadonnees PNG embarquees par ComfyUI (le prompt API-format
    est stocke dans le chunk 'prompt') et cherche les fragments bannis dans
    le texte CLIPTextEncode effectivement envoye - pas le texte source, la
    valeur reellement resolue au moment de la generation."""
    from PIL import Image

    img = Image.open(png_path)
    raw_prompt_json = img.info.get("prompt")
    if not raw_prompt_json:
        return {"ok": False, "reason": "pas de metadonnee 'prompt' dans le PNG", "hits": []}

    workflow = json.loads(raw_prompt_json)
    hits = []
    for node in workflow.values():
        if node.get("class_type") == "CLIPTextEncode":
            text = node.get("inputs", {}).get("text", "")
            for banned in BANNED_SUBSTRINGS:
                if banned.lower() in text.lower():
                    hits.append({"banned": banned, "text": text})
    return {"ok": not hits, "reason": None, "hits": hits}


def generate_one(index):
    seed = gd.BASE_SEED + index * gd.SEED_STRIDE
    rng = random.Random(seed)
    templates = gd.load_templates()
    template = rng.choice(templates)
    prompt = gd.resolve_prompt(template, rng)

    dest_name = f"footsegnet_val_{index:05d}.png"
    dest_path = TEST_DIR / dest_name
    print(f"[validate] index={index} seed={seed}")
    print(f"[validate]   prompt: {prompt}")

    wf = gd.build_txt2img_workflow(prompt, seed, f"footsegnet/wildcard_fix_val_{index:05d}_")
    submit_time = time.time()
    pid = gd.submit(wf)
    if not pid:
        print(f"[validate]   echec soumission - SKIP index {index}")
        return None

    out = gd.wait_and_fetch(pid, submit_time)
    if not out:
        print(f"[validate]   image non produite - SKIP index {index}")
        return None

    import shutil
    shutil.copy2(out, str(dest_path))
    print(f"[validate]   OK -> {dest_path}")
    return {"index": index, "seed": seed, "prompt": prompt, "template": template, "dest": str(dest_path)}


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--scan", action="store_true", help="selectionne automatiquement des index biaises (cf. find_biased_indices)")
    ap.add_argument("--count", type=int, default=18)
    ap.add_argument("--indices", type=str, default="", help="liste explicite d'index separes par des virgules (prioritaire sur --scan)")
    ap.add_argument("--check-only", action="store_true",
                     help="n'affiche que les index/prompts selectionnes, ne genere rien (dry-run local, pas d'appel ComfyUI)")
    args = ap.parse_args()

    if args.indices:
        indices = [int(x) for x in args.indices.split(",") if x.strip()]
    elif args.scan:
        indices = find_biased_indices(args.count)
    else:
        raise SystemExit("Fournis --indices ou --scan")

    print(f"[validate] {len(indices)} index selectionnes : {indices}")

    if args.check_only:
        for i in indices:
            seed = gd.BASE_SEED + i * gd.SEED_STRIDE
            rng = random.Random(seed)
            templates = gd.load_templates()
            template = rng.choice(templates)
            prompt = gd.resolve_prompt(template, rng)
            print(f"  [{i}] seed={seed} :: {prompt}")
        return

    TEST_DIR.mkdir(parents=True, exist_ok=True)

    manifest = {"images": {}}
    if TEST_MANIFEST.exists():
        manifest = json.loads(TEST_MANIFEST.read_text(encoding="utf-8"))

    results = []
    for i in indices:
        r = generate_one(i)
        if r:
            manifest["images"][Path(r["dest"]).name] = r
            results.append(r)
            TEST_MANIFEST.write_text(json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8")

    print(f"\n[validate] {len(results)}/{len(indices)} images generees dans {TEST_DIR}")

    print("\n[validate] Scan metadonnees PNG (fragments bannis: "
          f"{BANNED_SUBSTRINGS}) :")
    n_clean = 0
    for r in results:
        report = scan_png_metadata(r["dest"])
        status = "OK" if report["ok"] else "HIT"
        if report["ok"]:
            n_clean += 1
        else:
            print(f"  [{status}] {Path(r['dest']).name} : {report['hits']}")
    print(f"[validate] {n_clean}/{len(results)} images propres (aucun fragment banni dans le prompt effectif)")


if __name__ == "__main__":
    main()

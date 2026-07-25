# qwen_prompt_refiner.py — Ov3rLoRd Pipeline
# Analyse une frame générée avec QwenVL et produit un prompt corrigé
# pour la frame suivante — feedback adaptatif visuel
# py -3.12

import base64
import json
import os
from pathlib import Path

# ─── Import LLM avec fallback ─────────────────────────────────────────────────
try:
    import requests as _req
    HAS_REQUESTS = True
except ImportError:
    HAS_REQUESTS = False

try:
    import ollama as _ollama
    HAS_OLLAMA = True
except ImportError:
    HAS_OLLAMA = False

# ─── Constantes ───────────────────────────────────────────────────────────────

OLLAMA_URL      = "http://127.0.0.1:11434"
OLLAMA_MODEL    = "qwen2.5vl:7b"   # ou "llava" comme fallback si qwen VL absent
FALLBACK_MODEL  = "llava"

ASUKA_REFERENCE = {
    "character": "Asuka Langley Soryu",
    "hair":      "long auburn/red hair with two pigtails, swept back dynamically",
    "eyes":      "blue eyes",
    "suit":      "iconic red plugsuit, glossy/reflective material, TWO black stripes on thigh only",
    "style":     "cel shading, bold lines, evangelion anime aesthetic",
}

ANALYSIS_SYSTEM_PROMPT = """You are a visual quality inspector for an anime production pipeline.
You analyze a generated frame and compare it to the Asuka Langley Soryu reference.
You respond ONLY with a JSON object, no markdown, no explanation.

Reference character:
- Long auburn/red hair, pigtails, swept back by wind
- Blue eyes
- Red plugsuit with glossy reflective material
- TWO black stripes on thigh ONLY (not three, not on arms)
- No watermarks, no duplicate characters

Respond with this exact JSON structure:
{
  "passed": true/false,
  "issues": ["list of detected issues"],
  "prompt_additions": ["phrases to ADD to next frame prompt"],
  "prompt_removals": ["phrases to REMOVE or negate"],
  "confidence": 0.0-1.0,
  "notes": "brief observation"
}"""


def image_to_base64(image_path: str) -> str:
    with open(image_path, "rb") as f:
        return base64.b64encode(f.read()).decode("utf-8")


# ─── Analyse via Ollama (local) ───────────────────────────────────────────────

def analyze_frame_ollama(
    image_path: str,
    model: str = OLLAMA_MODEL,
) -> dict | None:
    """Analyse une frame via Ollama QwenVL ou LLaVA."""
    if not Path(image_path).exists():
        print(f"[qwen_refiner] Image non trouvée : {image_path}")
        return None

    img_b64 = image_to_base64(image_path)

    payload = {
        "model": model,
        "prompt": (
            f"{ANALYSIS_SYSTEM_PROMPT}\n\n"
            "Analyze this anime frame. Is the character Asuka Langley Soryu? "
            "Are there visual issues? Respond ONLY with JSON."
        ),
        "images": [img_b64],
        "stream": False,
        "options": {"temperature": 0.1},
    }

    try:
        r = _req.post(f"{OLLAMA_URL}/api/generate", json=payload, timeout=60)
        r.raise_for_status()
        raw = r.json().get("response", "")
        return _parse_json_response(raw)
    except Exception as e:
        print(f"[qwen_refiner] Ollama {model} erreur : {e}")

    # Fallback sur llava si qwen VL absent
    if model != FALLBACK_MODEL:
        print(f"[qwen_refiner] Fallback sur {FALLBACK_MODEL}...")
        return analyze_frame_ollama(image_path, model=FALLBACK_MODEL)

    return None


def _parse_json_response(raw: str) -> dict | None:
    """Parse une réponse JSON potentiellement entourée de markdown."""
    raw = raw.strip()
    # Nettoyage markdown
    for fence in ["```json", "```"]:
        raw = raw.replace(fence, "")
    raw = raw.strip()
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        # Tentative extraction du premier bloc JSON
        start = raw.find("{")
        end   = raw.rfind("}") + 1
        if start >= 0 and end > start:
            try:
                return json.loads(raw[start:end])
            except Exception:
                pass
    print(f"[qwen_refiner] Impossible de parser la réponse : {raw[:200]}")
    return None


# ─── Application des corrections au prompt ────────────────────────────────────

def apply_corrections(
    base_prompt: str,
    analysis: dict,
    max_additions: int = 3,
) -> str:
    """
    Applique les corrections suggérées par QwenVL au prompt de base.
    Limite à max_additions pour éviter la dérive de prompt long.
    """
    if not analysis:
        return base_prompt

    additions = analysis.get("prompt_additions", [])[:max_additions]
    removals  = analysis.get("prompt_removals",  [])

    result = base_prompt

    # Ajoute les corrections en tête de prompt (poids implicitement plus fort)
    if additions:
        correction_block = ", ".join(additions)
        result = f"({correction_block}:1.3), " + result

    # Suppression des termes problématiques
    for term in removals:
        result = result.replace(term, "")

    # Nettoyage doubles virgules
    while ",," in result:
        result = result.replace(",,", ",")
    result = result.strip(", ")

    return result


# ─── Pipeline complet : analyser + corriger ────────────────────────────────────

def refine_prompt_for_next_frame(
    current_frame_path: str,
    base_prompt: str,
    frame_id: int,
    shot_id: int,
) -> tuple[str, dict | None]:
    """
    Analyse la frame courante et retourne le prompt corrigé pour la suivante.

    Retourne:
        (prompt_corrigé, analyse_dict)
    """
    print(f"[qwen_refiner] Analyse frame {frame_id:04d} (shot {shot_id})...")

    analysis = analyze_frame_ollama(current_frame_path)

    if analysis is None:
        print(f"[qwen_refiner] Analyse échouée — prompt inchangé")
        return base_prompt, None

    issues = analysis.get("issues", [])
    passed = analysis.get("passed", True)
    conf   = analysis.get("confidence", 0.0)

    if issues:
        print(f"[qwen_refiner] Issues détectées (conf={conf:.2f}) :")
        for iss in issues:
            print(f"  - {iss}")
    else:
        print(f"[qwen_refiner] Frame OK (conf={conf:.2f})")

    corrected = apply_corrections(base_prompt, analysis)

    if corrected != base_prompt:
        print(f"[qwen_refiner] Prompt modifié pour frame {frame_id + 1:04d}")

    return corrected, analysis


# ─── Rapport d'analyse batch ──────────────────────────────────────────────────

def generate_analysis_report(analyses: list[dict], output_path: str) -> None:
    """Génère un rapport JSON des analyses de frames pour audit."""
    report = {
        "total_frames_analyzed": len(analyses),
        "passed": sum(1 for a in analyses if a.get("analysis", {}) and
                      a.get("analysis", {}).get("passed", True)),
        "with_issues": sum(1 for a in analyses if a.get("analysis", {}) and
                           a.get("analysis", {}).get("issues")),
        "frames": analyses,
    }
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2, ensure_ascii=False)
    print(f"[qwen_refiner] Rapport sauvé : {output_path}")


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Ov3rLoRd — QwenVL Prompt Refiner")
    parser.add_argument("--image", required=True, help="Chemin de la frame à analyser")
    parser.add_argument("--frame-id", type=int, default=0)
    parser.add_argument("--shot-id",  type=int, default=1)
    parser.add_argument("--model", default=OLLAMA_MODEL)
    args = parser.parse_args()

    BASE_PROMPT = (
        "(masterpiece:1.4), (best quality:1.4), 1girl, solo, asuka langley soryu, "
        "red plugsuit, TWO black stripes on thigh only, running, anime style"
    )

    corrected, analysis = refine_prompt_for_next_frame(
        args.image, BASE_PROMPT, args.frame_id, args.shot_id
    )
    print(f"\nPrompt corrigé :\n{corrected}")
    if analysis:
        print(f"\nAnalyse complète :\n{json.dumps(analysis, indent=2)}")

"""
denoise_estimator.py — Ov3rLoRd Pipeline
Estime la denoise optimale entre deux frames via comparaison
structurelle des squelettes/lineart + validation QwenVL.

Usage standalone :
    py -3.12 agents/denoise_estimator.py --skel-prev SK_N-1 --skel-cur SK_N
                                          --la-prev LA_N-1  --la-cur LA_N

Usage depuis batch_controlnet.py :
    from denoise_estimator import estimate_denoise
    denoise = estimate_denoise(skel_prev, skel_cur, la_prev, la_cur)
"""

import os
import json
import base64
import argparse
import urllib.request
import urllib.error

try:
    import numpy as np
    from PIL import Image
    HAS_PIL = True
except ImportError:
    HAS_PIL = False

# ── CONFIG ────────────────────────────────────────────────────────────────────
OLLAMA_URL   = "http://127.0.0.1:11434"
QWEN_MODEL   = "qwen2.5vl:7b"      # ajuster selon modèle installé

# Plage denoise mappée depuis score de changement QwenVL
DENOISE_MIN  = 0.05   # pose quasi-identique
DENOISE_MAX  = 0.40   # changement de pose majeur
DENOISE_FALLBACK = 0.20   # fallback si QwenVL indisponible

# Seuil diff pixel pour fallback PIL (sans QwenVL)
PIL_DIFF_THRESHOLD = 15   # valeur pixel considérée comme "changement"


# ── FALLBACK PIL : diff structurelle pure ─────────────────────────────────────
def compute_structural_diff(img1_path: str, img2_path: str,
                             size: tuple = (256, 144)) -> float:
    """
    Compare deux images (squelettes ou lineart) par diff pixel normalisée.
    Retourne un score 0.0 (identiques) → 1.0 (totalement différentes).
    """
    if not HAS_PIL:
        return 0.5
    try:
        a = np.array(Image.open(img1_path).convert("L").resize(size)).astype(float)
        b = np.array(Image.open(img2_path).convert("L").resize(size)).astype(float)
        diff = np.abs(a - b)
        changed = (diff > PIL_DIFF_THRESHOLD).sum()
        total = size[0] * size[1]
        return float(changed / total)
    except Exception as e:
        print(f"[denoise_estimator] PIL diff error: {e}")
        return 0.5


def score_to_denoise(score: float) -> float:
    """Mappe un score 0.0→1.0 sur la plage DENOISE_MIN→DENOISE_MAX."""
    clamped = max(0.0, min(1.0, score))
    denoise = DENOISE_MIN + clamped * (DENOISE_MAX - DENOISE_MIN)
    return round(denoise, 3)


# ── QWENVL : estimation visuelle ─────────────────────────────────────────────
def img_to_base64(path: str) -> str:
    with open(path, "rb") as f:
        return base64.b64encode(f.read()).decode("utf-8")


def ask_qwen_diff(skel_prev: str, skel_cur: str,
                  la_prev: str, la_cur: str) -> float:
    """
    Envoie 4 images à QwenVL et demande un score de changement 0.0→1.0.
    Retourne le score ou -1.0 si erreur.
    """
    prompt = (
        "You are analyzing pose changes between animation frames.\n"
        "I will show you 4 images in order:\n"
        "1. OpenPose skeleton frame N-1\n"
        "2. OpenPose skeleton frame N\n"
        "3. Lineart frame N-1\n"
        "4. Lineart frame N\n\n"
        "Compare the pose and contour changes between N-1 and N.\n"
        "Respond with ONLY a JSON object: {\"change_score\": <float 0.0 to 1.0>}\n"
        "Where 0.0 = identical poses, 1.0 = completely different poses.\n"
        "Consider: joint positions, body orientation, limb angles, contour shape.\n"
        "No explanation, JSON only."
    )

    images_b64 = []
    for path in [skel_prev, skel_cur, la_prev, la_cur]:
        if path and os.path.exists(path):
            images_b64.append(img_to_base64(path))
        else:
            print(f"[denoise_estimator] Image manquante: {path}")
            return -1.0

    payload = {
        "model": QWEN_MODEL,
        "messages": [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": prompt},
                ] + [
                    {"type": "image_url",
                     "image_url": {"url": f"data:image/png;base64,{b64}"}}
                    for b64 in images_b64
                ]
            }
        ],
        "stream": False,
        "options": {"temperature": 0.0}
    }

    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        f"{OLLAMA_URL}/api/chat",
        data=data,
        headers={"Content-Type": "application/json"}
    )

    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            resp = json.loads(r.read())
        content = resp.get("message", {}).get("content", "")

        # Parser le JSON de la réponse
        import re
        match = re.search(r'\{[^}]*"change_score"\s*:\s*([0-9.]+)[^}]*\}', content)
        if match:
            score = float(match.group(1))
            return max(0.0, min(1.0, score))
        else:
            print(f"[denoise_estimator] QwenVL parse error: {repr(content[:100])}")
            return -1.0

    except urllib.error.URLError as e:
        print(f"[denoise_estimator] QwenVL unavailable: {e}")
        return -1.0
    except Exception as e:
        print(f"[denoise_estimator] QwenVL error: {e}")
        return -1.0


# ── FONCTION PRINCIPALE ───────────────────────────────────────────────────────
def estimate_denoise(skel_prev: str, skel_cur: str,
                     la_prev: str = None, la_cur: str = None,
                     use_qwen: bool = True,
                     verbose: bool = False) -> float:
    """
    Estime la denoise optimale entre deux frames.

    Stratégie :
    1. Tente QwenVL pour une estimation visuelle riche (si use_qwen=True)
    2. Fallback : diff pixel PIL sur squelettes + lineart
    3. Fallback final : DENOISE_FALLBACK

    Args:
        skel_prev : chemin squelette frame n-1
        skel_cur  : chemin squelette frame n
        la_prev   : chemin lineart frame n-1 (optionnel)
        la_cur    : chemin lineart frame n   (optionnel)
        use_qwen  : activer QwenVL (défaut True)
        verbose   : afficher détails

    Returns:
        float : valeur denoise recommandée (DENOISE_MIN..DENOISE_MAX)
    """
    if not skel_prev or not skel_cur:
        return DENOISE_FALLBACK

    # ── Tentative QwenVL ──
    if use_qwen and la_prev and la_cur:
        score = ask_qwen_diff(skel_prev, skel_cur, la_prev, la_cur)
        if score >= 0.0:
            denoise = score_to_denoise(score)
            if verbose:
                print(f"[denoise_estimator] QwenVL score={score:.3f} → denoise={denoise}")
            return denoise
        else:
            if verbose:
                print("[denoise_estimator] QwenVL failed, fallback PIL")

    # ── Fallback PIL ──
    if HAS_PIL:
        skel_score = compute_structural_diff(skel_prev, skel_cur)

        if la_prev and la_cur and os.path.exists(la_prev) and os.path.exists(la_cur):
            la_score = compute_structural_diff(la_prev, la_cur)
            # Pondération : squelette 60% / lineart 40%
            combined = skel_score * 0.6 + la_score * 0.4
        else:
            combined = skel_score

        denoise = score_to_denoise(combined)
        if verbose:
            la_str = f"{la_score:.3f}" if (la_prev and la_cur) else "N/A"
            print(f"[denoise_estimator] PIL skel={skel_score:.3f} "
                  f"la={la_str} combined={combined:.3f} → denoise={denoise}")
        return denoise

    # ── Fallback final ──
    if verbose:
        print(f"[denoise_estimator] Fallback fixe → denoise={DENOISE_FALLBACK}")
    return DENOISE_FALLBACK


# ── CLI ───────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Ov3rLoRd — Denoise Estimator")
    parser.add_argument("--skel-prev", required=True, help="Squelette frame N-1 (chemin absolu ou relatif)")
    parser.add_argument("--skel-cur",  required=True, help="Squelette frame N (chemin absolu ou relatif)")
    parser.add_argument("--la-prev",   default=None,  help="Lineart frame N-1")
    parser.add_argument("--la-cur",    default=None,  help="Lineart frame N")
    parser.add_argument("--no-qwen",   action="store_true", help="Forcer fallback PIL")
    parser.add_argument("--verbose",   action="store_true")
    args = parser.parse_args()

    def absp(p):
        return os.path.abspath(p) if p else None

    result = estimate_denoise(
        absp(args.skel_prev), absp(args.skel_cur),
        absp(args.la_prev), absp(args.la_cur),
        use_qwen=not args.no_qwen,
        verbose=True
    )
    print(f"\n→ Denoise recommandée : {result}")

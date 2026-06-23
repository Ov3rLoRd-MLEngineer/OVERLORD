"""
agents/style_continuity.py — Agent Continuité Visuelle V1.70
Analyse les ruptures de style détectées par le watchdog et génère
des correctifs de prompt pour les shots suivants.
But : cohérence visuelle entre les 8 frames d'un run.

Problème observé V1.60 :
  [WATCHDOG] Rupture style : frame 0->1 (drift=0.450)
  [WATCHDOG] Rupture style : frame 4->5 (drift=0.441)
→ Les seeds différents + LoRas aléatoires créent des discontinuités.

Solution : fixer le style anchor (seed, LoRa, palette) pour tout le run,
et ajuster les prompts dérivants AVANT envoi à ComfyUI.
"""

import json
import logging
import random
from pathlib import Path

try:
    from agents.context_bus import get_bus
    BUS_OK = True
except ImportError:
    BUS_OK = False

try:
    from agents.config_manager import get_config
    CFG_OK = True
except ImportError:
    CFG_OK = False

STYLE_ANCHOR_FILE = Path("workspace/style_anchor.json")

AVAILABLE_LORAS = [
    "asuka-langley-soryuu-classic-ponyxl-lora-nochekaiser.safetensors",
    "mari-makinami-rebuild-ponyxl-lora-nochekaiser.safetensors",
    "rei-ayanami-classic-ponyxl-lora-nochekaiser.safetensors",
]

# LoRa fixes par univers -- evite le random.choice sur des runs cibles
UNIVERSE_LORA_MAP = {
    "evangelion": "asuka-langley-soryuu-classic-ponyxl-lora-nochekaiser.safetensors",
    "asuka":      "asuka-langley-soryuu-classic-ponyxl-lora-nochekaiser.safetensors",
    "rei":        "rei-ayanami-classic-ponyxl-lora-nochekaiser.safetensors",
    "mari":       "mari-makinami-rebuild-ponyxl-lora-nochekaiser.safetensors",
}

# Tags de cohérence à injecter dans tous les prompts d'un run
COHERENCE_TAGS = [
    "consistent style",
    "same character design",
    "unified color palette",
    "anime style",
    "sharp lineart",
]

# Palettes émotionnelles → couleurs cohérentes
EMOTION_PALETTES = {
    "wonder":     ["vibrant blue", "golden yellow", "white highlights"],
    "tension":    ["deep red", "dark blue", "sharp contrast"],
    "catharsis":  ["warm orange", "soft purple", "golden hour"],
    "melancholy": ["muted grey", "pale blue", "desaturated"],
    "action":     ["electric blue", "neon green", "high contrast"],
    "peaceful":   ["soft green", "warm white", "pastel pink"],
}


class StyleAnchor:
    """
    Ancre de style pour un run complet.
    Fixe seed de base, LoRa, palette, et tags de cohérence.
    """

    def __init__(self, run_id: str, emotion_arc: str = "wonder"):
        self.run_id       = run_id
        self.emotion_arc  = emotion_arc
        self.base_seed    = random.randint(1000, 99999)
        self.lora         = random.choice(AVAILABLE_LORAS)
        self.palette      = EMOTION_PALETTES.get(emotion_arc, EMOTION_PALETTES["wonder"])
        self.coherence_suffix = ", ".join(COHERENCE_TAGS)
        self.palette_str  = ", ".join(self.palette)

    def to_dict(self) -> dict:
        return {
            "run_id":            self.run_id,
            "emotion_arc":       self.emotion_arc,
            "base_seed":         self.base_seed,
            "lora":              self.lora,
            "palette":           self.palette,
            "coherence_suffix":  self.coherence_suffix,
            "palette_str":       self.palette_str,
        }

    def save(self):
        STYLE_ANCHOR_FILE.parent.mkdir(parents=True, exist_ok=True)
        STYLE_ANCHOR_FILE.write_text(
            json.dumps(self.to_dict(), indent=2, ensure_ascii=False),
            encoding="utf-8"
        )

    @classmethod
    def load(cls, run_id: str) -> "StyleAnchor | None":
        if STYLE_ANCHOR_FILE.exists():
            try:
                data = json.loads(STYLE_ANCHOR_FILE.read_text(encoding="utf-8"))
                if data.get("run_id") == run_id:
                    anchor = cls.__new__(cls)
                    anchor.run_id          = data["run_id"]
                    anchor.emotion_arc     = data["emotion_arc"]
                    anchor.base_seed       = data["base_seed"]
                    anchor.lora            = data["lora"]
                    anchor.palette         = data["palette"]
                    anchor.coherence_suffix = data["coherence_suffix"]
                    anchor.palette_str     = data["palette_str"]
                    return anchor
            except Exception:
                pass
        return None


def create_anchor(run_id: str, logger: logging.Logger = None) -> StyleAnchor:
    """Crée et sauvegarde une ancre de style pour le run."""
    log = logger or logging.getLogger("style_continuity")

    # Lire l'arc émotionnel depuis le bus
    emotion_arc = "wonder"
    if BUS_OK:
        try:
            arc = get_bus().read("director.emotion_arc")
            if arc:
                emotion_arc = arc
        except Exception:
            pass

    # Lire l'univers depuis le bus pour forcer la bonne LoRa
    universe = ""
    if BUS_OK:
        try:
            universe = get_bus().read("director.universe") or ""
        except Exception:
            pass
    # Chercher une correspondance partielle dans UNIVERSE_LORA_MAP
    forced_lora = ""
    for key, lora in UNIVERSE_LORA_MAP.items():
        if key in universe.lower():
            forced_lora = lora
            break

    anchor = StyleAnchor(run_id=run_id, emotion_arc=emotion_arc)
    if forced_lora:
        anchor.lora = forced_lora
    anchor.save()

    log.info(f"[STYLE] Ancre créée — seed={anchor.base_seed} | "
             f"lora={anchor.lora[:35]}... | arc={emotion_arc}")

    if BUS_OK:
        try:
            get_bus().write("style.anchor_lora",    anchor.lora,       agent_id="style")
            get_bus().write("style.base_seed",      anchor.base_seed,  agent_id="style")
            get_bus().write("style.palette",        anchor.palette,    agent_id="style")
            get_bus().write("style.emotion_arc",    emotion_arc,       agent_id="style")
        except Exception:
            pass

    return anchor


def apply_continuity(jobs: list, run_id: str,
                     logger: logging.Logger = None) -> list:
    """
    Applique la continuité de style à tous les jobs d'un run.
    - Seed progressif (base + idx) pour variation contrôlée
    - LoRa identique sur tous les shots
    - Tags de cohérence + palette injectés dans chaque prompt
    - Negative renforcé contre la discontinuité
    """
    log = logger or logging.getLogger("style_continuity")

    anchor = StyleAnchor.load(run_id)
    if not anchor:
        anchor = create_anchor(run_id, logger=log)

    # V2.20 : verifier la LoRa forcee depuis le bus meme si anchor deja chargee
    if BUS_OK:
        try:
            universe = get_bus().read("director.universe") or ""
            for key, lora in UNIVERSE_LORA_MAP.items():
                if key in universe.lower():
                    if anchor.lora != lora:
                        log.info(f"[STYLE] LoRa forcee depuis univers '{universe}' -> {lora[:40]}")
                        anchor.lora = lora
                        anchor.save()
                    break
        except Exception:
            pass

    log.info(f"[STYLE] Application continuité à {len(jobs)} jobs | lora={anchor.lora[:40]}")

    continuity_negative_add = (
        ", inconsistent style, style change, different art style, "
        "inconsistent character design, color inconsistency"
    )

    enriched = []
    for i, job in enumerate(jobs):
        j = job.copy()

        # Seed progressif : base + step faible pour variation contrôlée
        j["seed"] = anchor.base_seed + (i * 137)  # 137 = nombre premier → bonne distribution

        # LoRa uniforme sur tout le run -- toujours forcer l'ancre
        j["lora"]     = anchor.lora
        j["det_lora"] = anchor.lora

        # Injecter palette + cohérence dans le prompt positif
        positive = j.get("positive", "")
        if positive and anchor.palette_str not in positive:
            j["positive"] = f"{positive}, {anchor.palette_str}, {anchor.coherence_suffix}"

        # Renforcer le négatif contre les ruptures
        negative = j.get("negative", "")
        if continuity_negative_add not in negative:
            j["negative"] = negative + continuity_negative_add

        enriched.append(j)
        log.debug(f"[STYLE] Job {i+1} seed={j['seed']} | lora={j['lora'][:30]}...")

    log.info(f"[STYLE] Continuité appliquée — "
             f"seed_range=[{anchor.base_seed}, {anchor.base_seed + (len(jobs)-1)*137}]")
    return enriched


def analyze_drift(frame_reports: list, threshold: float = 0.4,
                  logger: logging.Logger = None) -> dict:
    """
    Analyse les rapports watchdog pour détecter et quantifier les ruptures.
    Retourne les frames à régénérer et les corrections suggérées.
    """
    log = logger or logging.getLogger("style_continuity")

    if not frame_reports or len(frame_reports) < 2:
        return {"drift_frames": [], "severity": "none", "regen_needed": False}

    drifts = []
    for i in range(1, len(frame_reports)):
        drift = frame_reports[i].get("drift", 0.0)
        if drift > threshold:
            drifts.append({
                "frame":     i,
                "drift":     drift,
                "severity":  "high" if drift > 0.5 else "medium",
            })

    severity = "none"
    if drifts:
        max_drift = max(d["drift"] for d in drifts)
        severity  = "critical" if max_drift > 0.6 else "high" if max_drift > 0.5 else "medium"

    result = {
        "drift_frames":   [d["frame"] for d in drifts],
        "drift_details":  drifts,
        "severity":       severity,
        "regen_needed":   len(drifts) > len(frame_reports) // 2,
        "mean_drift":     sum(d["drift"] for d in drifts) / len(drifts) if drifts else 0.0,
    }

    if drifts:
        log.warning(f"[STYLE] {len(drifts)} ruptures détectées | "
                    f"sévérité={severity} | frames={result['drift_frames']}")
    else:
        log.info("[STYLE] Aucune rupture de style détectée")

    if BUS_OK:
        try:
            get_bus().write("style.drift_count",    len(drifts),  agent_id="style")
            get_bus().write("style.drift_severity", severity,     agent_id="style")
        except Exception:
            pass

    return result


if __name__ == "__main__":
    import sys, io
    if hasattr(sys.stdout, "buffer"):
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    logging.basicConfig(level=logging.INFO)

    print("=== Style Continuity V1.70 ===")
    test_jobs = [
        {"positive": "masterpiece, 1girl, action", "negative": "bad quality"},
        {"positive": "masterpiece, 1girl, portrait", "negative": "bad quality"},
        {"positive": "masterpiece, 1girl, wide shot", "negative": "bad quality"},
    ]
    enriched = apply_continuity(test_jobs, run_id="test_run")
    for i, j in enumerate(enriched):
        print(f"Job {i+1}: seed={j['seed']} | {j['positive'][:60]}...")

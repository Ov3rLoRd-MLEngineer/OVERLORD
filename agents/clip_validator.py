"""
clip_validator.py V1.0
Ov3rLoRd
Validation cohérence visuelle inter-shots par distance cosinus CLIP.
Intégration : appelé par maestro.py après block_production().
"""

import os
import sys
import json
import logging
import sqlite3
from pathlib import Path
from datetime import datetime

# ── Watchdog config adaptatif V2.22 ───────────────────────────────────────────
try:
    sys.path.insert(0, str(Path(__file__).parent.parent))
    from watchdog_config import load_config as _load_watchdog_cfg
    _WD_CFG = _load_watchdog_cfg()
    CLIP_THRESHOLD = _WD_CFG.get("clip_threshold", 0.80)
except Exception:
    CLIP_THRESHOLD = 0.80

# ── Imports optionnels CLIP ────────────────────────────────────────────────────
try:
    import torch
    import open_clip
    from PIL import Image
    import numpy as np
    CLIP_AVAILABLE = True
except ImportError:
    CLIP_AVAILABLE = False

# ── Imports internes ───────────────────────────────────────────────────────────
try:
    from audit_logger import AuditLogger
    AUDIT_AVAILABLE = True
except ImportError:
    AUDIT_AVAILABLE = False

import config

# ── Configuration ──────────────────────────────────────────────────────────────
PROJECT_ROOT   = config.OVERLORD_ROOT
WORKSPACE      = PROJECT_ROOT / "workspace"
AUDIT_DB       = WORKSPACE / "audit" / "overlord_audit.db"
REPORTS_DIR    = WORKSPACE / "reports"
CLIP_MODEL     = "ViT-B-32"
CLIP_PRETRAIN  = "openai"
COSINE_WARNING = 0.70   # seuil alerte
COSINE_REJECT  = 0.50   # seuil rejet

logging.basicConfig(
    level=logging.INFO,
    format="[CLIP] %(asctime)s %(levelname)s — %(message)s",
    datefmt="%H:%M:%S"
)
log = logging.getLogger("clip_validator")


# ══════════════════════════════════════════════════════════════════════════════
class CLIPValidator:
    """
    Calcule la distance cosinus CLIP entre frames consécutives d'un run.
    Produit un rapport JSON + log dans l'audit SQLite.
    """

    def __init__(self, run_id: str):
        self.run_id   = run_id
        self.device   = "cuda" if (CLIP_AVAILABLE and torch.cuda.is_available()) else "cpu"
        self.model    = None
        self.preprocess = None
        self.tokenizer  = None
        REPORTS_DIR.mkdir(parents=True, exist_ok=True)

    # ── Chargement modèle ──────────────────────────────────────────────────────
    def _load_model(self):
        if not CLIP_AVAILABLE:
            log.warning("open_clip / torch non disponible — mode dégradé (hash perceptuel)")
            return False
        if self.model is not None:
            return True
        log.info(f"Chargement CLIP {CLIP_MODEL} sur {self.device}...")
        self.model, _, self.preprocess = open_clip.create_model_and_transforms(
            CLIP_MODEL, pretrained=CLIP_PRETRAIN
        )
        self.model.eval().to(self.device)
        log.info("Modèle CLIP prêt.")
        return True

    # ── Encodage image ─────────────────────────────────────────────────────────
    def _encode_image(self, path: Path) -> "np.ndarray | None":
        try:
            img = Image.open(path).convert("RGB")
            tensor = self.preprocess(img).unsqueeze(0).to(self.device)
            with torch.no_grad():
                feat = self.model.encode_image(tensor)
                feat = feat / feat.norm(dim=-1, keepdim=True)
            return feat.cpu().numpy()[0]
        except Exception as e:
            log.error(f"Encodage échoué {path.name}: {e}")
            return None

    # ── Fallback hash perceptuel (sans CLIP) ──────────────────────────────────
    def _perceptual_hash(self, path: Path) -> "np.ndarray | None":
        """Hash 64-bits via PIL — fallback si CLIP absent."""
        try:
            from PIL import Image as PILImage
            img = PILImage.open(path).convert("L").resize((8, 8), PILImage.LANCZOS)
            pixels = list(img.getdata())
            avg = sum(pixels) / len(pixels)
            bits = np.array([1 if p >= avg else 0 for p in pixels], dtype=float)
            return bits
        except Exception as e:
            log.error(f"Hash perceptuel échoué {path.name}: {e}")
            return None

    # ── Cosinus ───────────────────────────────────────────────────────────────
    @staticmethod
    def _cosine(a: "np.ndarray", b: "np.ndarray") -> float:
        denom = (np.linalg.norm(a) * np.linalg.norm(b))
        if denom == 0:
            return 0.0
        return float(np.dot(a, b) / denom)

    # ── Récupération frames depuis audit DB ───────────────────────────────────
    def _get_frames_from_db(self) -> list:
        """Retourne la liste des chemins de frames du run_id depuis l'audit SQLite."""
        frames = []
        if not AUDIT_DB.exists():
            log.warning("audit.db introuvable — scan workspace/outputs à la place")
            return frames
        try:
            conn = sqlite3.connect(str(AUDIT_DB))
            cur  = conn.cursor()
            cur.execute(
                "SELECT frame_path FROM frames WHERE run_id=? ORDER BY frame_index ASC",
                (self.run_id,)
            )
            rows = cur.fetchall()
            conn.close()
            frames = [Path(r[0]) for r in rows if Path(r[0]).exists()]
            log.info(f"{len(frames)} frames récupérées depuis audit DB")
        except Exception as e:
            log.error(f"Erreur lecture audit DB: {e}")
        return frames

    # ── Scan dossier outputs (fallback) ───────────────────────────────────────
    def _scan_output_dir(self) -> list:
        out_dir = WORKSPACE / "outputs" / self.run_id
        if not out_dir.exists():
            candidates = list((WORKSPACE / "outputs").glob(f"*{self.run_id}*"))
            if not candidates:
                log.error(f"Dossier outputs introuvable pour run {self.run_id}")
                return []
            out_dir = candidates[0]
        frames = sorted(out_dir.glob("*.png")) + sorted(out_dir.glob("*.jpg"))
        log.info(f"{len(frames)} frames scannées dans {out_dir}")
        return frames

    # ── Validation principale ─────────────────────────────────────────────────
    def validate(self) -> dict:
        log.info(f"=== CLIP Validator — Run {self.run_id} ===")

        use_clip  = self._load_model()
        encode_fn = self._encode_image if use_clip else self._perceptual_hash

        # Récupération frames
        frames = self._get_frames_from_db()
        if not frames:
            frames = self._scan_output_dir()
        if len(frames) < 2:
            log.warning("Moins de 2 frames — validation impossible")
            return {"run_id": self.run_id, "status": "SKIP", "reason": "< 2 frames"}

        # Encodage
        log.info(f"Encodage {len(frames)} frames...")
        embeddings = []
        for f in frames:
            emb = encode_fn(f)
            if emb is not None:
                embeddings.append((f.name, emb))

        if len(embeddings) < 2:
            return {"run_id": self.run_id, "status": "ERROR", "reason": "encodage insuffisant"}

        # Calcul distances
        results  = []
        warnings = []
        rejects  = []

        for i in range(len(embeddings) - 1):
            name_a, emb_a = embeddings[i]
            name_b, emb_b = embeddings[i + 1]
            score = self._cosine(emb_a, emb_b)
            entry = {
                "pair":   f"{name_a} → {name_b}",
                "cosine": round(score, 4),
                "status": "OK"
            }
            if score < COSINE_REJECT:
                entry["status"] = "REJECT"
                rejects.append(entry)
                log.warning(f"  ❌ REJET  {entry['pair']} — cosine={score:.3f}")
            elif score < COSINE_WARNING:
                entry["status"] = "WARNING"
                warnings.append(entry)
                log.warning(f"  ⚠️  ALERTE {entry['pair']} — cosine={score:.3f}")
            else:
                log.info(f"  ✅ OK     {entry['pair']} — cosine={score:.3f}")
            results.append(entry)

        # Statistiques
        scores = [r["cosine"] for r in results]
        stats  = {
            "mean":   round(sum(scores) / len(scores), 4),
            "min":    round(min(scores), 4),
            "max":    round(max(scores), 4),
            "n_ok":   len([r for r in results if r["status"] == "OK"]),
            "n_warn": len(warnings),
            "n_rej":  len(rejects),
        }

        global_status = "OK"
        if rejects:
            global_status = "REJECT"
        elif warnings:
            global_status = "WARNING"

        report = {
            "run_id":    self.run_id,
            "timestamp": datetime.now().isoformat(),
            "mode":      "CLIP" if use_clip else "perceptual_hash",
            "status":    global_status,
            "stats":     stats,
            "pairs":     results,
            "rejects":   rejects,
            "warnings":  warnings,
        }

        # Sauvegarde rapport JSON
        report_path = REPORTS_DIR / f"clip_report_{self.run_id}.json"
        with open(report_path, "w", encoding="utf-8") as f:
            json.dump(report, f, indent=2, ensure_ascii=False)
        log.info(f"Rapport sauvegardé → {report_path}")

        # Log audit
        if AUDIT_AVAILABLE:
            try:
                al = AuditLogger()
                al.log_event(
                    run_id=self.run_id,
                    event_type="clip_validation",
                    data=json.dumps(stats)
                )
            except Exception:
                pass

        log.info(
            f"=== Résultat global : {global_status} | mean={stats['mean']} "
            f"| rejets={stats['n_rej']} | alertes={stats['n_warn']} ==="
        )
        return report


# ══════════════════════════════════════════════════════════════════════════════
def validate_run(run_id: str) -> dict:
    """Point d'entrée public pour maestro.py."""
    validator = CLIPValidator(run_id)
    return validator.validate()


# ══════════════════════════════════════════════════════════════════════════════
if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="CLIP Validator — Ov3rLoRd")
    parser.add_argument("--run-id", required=True, help="ID du run à valider")
    parser.add_argument("--thresholds", nargs=2, type=float,
                        metavar=("WARN", "REJECT"),
                        help="Seuils custom (défaut: 0.70 0.50)")
    args = parser.parse_args()

    if args.thresholds:
        COSINE_WARNING = args.thresholds[0]
        COSINE_REJECT  = args.thresholds[1]

    report = validate_run(args.run_id)
    print(json.dumps(report, indent=2, ensure_ascii=False))

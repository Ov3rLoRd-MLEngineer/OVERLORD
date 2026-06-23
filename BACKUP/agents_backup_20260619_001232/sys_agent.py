"""
agents/sys_agent.py — Agent Maintenance Système
Gestion des disques (NVMe/HDD), optimisation Windows, sécurité, monitoring.

Surveille :
  - NVMe 2To système/pipeline
  - NVMe 2To stockage chaud
  - SSD 500Go Windows/Jeux
  - HDD 8To archives

pip install psutil wmi  (Windows)
"""

import json
import logging
import subprocess
import shutil
import os
import threading
import time
from pathlib import Path
from datetime import datetime
from dataclasses import dataclass

try:
    import psutil
    PSUTIL_OK = True
except ImportError:
    PSUTIL_OK = False

REPORT_DIR = Path("workspace/sys_reports")

# Configuration disques (adapte les lettres de lecteur)
DISK_CONFIG = {
    "C:":  {"label": "Windows/Jeux",       "target_gb": 500,  "critical_pct": 90},
    "D:":  {"label": "Système/Pipeline",   "target_gb": 2000, "critical_pct": 85},
    "E:":  {"label": "Stockage chaud",     "target_gb": 2000, "critical_pct": 80},
    "G:":  {"label": "Archives HDD 8To",  "target_gb": 8000, "critical_pct": 95},
}


@dataclass
class DiskInfo:
    letter:     str
    label:      str
    total_gb:   float
    used_gb:    float
    free_gb:    float
    used_pct:   float
    status:     str   # ok / warning / critical


class SysAgent:
    """Agent de maintenance système pour la station OverLord."""

    def __init__(self, logger: logging.Logger = None):
        self.log = logger or logging.getLogger("sys_agent")
        REPORT_DIR.mkdir(parents=True, exist_ok=True)

    # ── Monitoring disques ────────────────────────────────────────────

    def get_disk_info(self) -> list[DiskInfo]:
        """Retourne l'état de tous les disques configurés."""
        disks = []
        if not PSUTIL_OK:
            self.log.warning("[SYS] pip install psutil")
            return disks

        for letter, cfg in DISK_CONFIG.items():
            try:
                usage = psutil.disk_usage(letter + "\\")
                total = usage.total / 1e9
                used  = usage.used  / 1e9
                free  = usage.free  / 1e9
                pct   = usage.percent
                crit  = cfg["critical_pct"]
                status = "critical" if pct >= crit else "warning" if pct >= crit-10 else "ok"
                disks.append(DiskInfo(
                    letter=letter, label=cfg["label"],
                    total_gb=round(total,1), used_gb=round(used,1),
                    free_gb=round(free,1), used_pct=round(pct,1),
                    status=status,
                ))
            except Exception:
                disks.append(DiskInfo(
                    letter=letter, label=cfg["label"],
                    total_gb=0, used_gb=0, free_gb=0,
                    used_pct=0, status="unavailable",
                ))
        return disks

    def get_system_stats(self) -> dict:
        """Retourne les stats CPU/RAM/GPU/Température."""
        stats = {
            "timestamp": datetime.utcnow().isoformat(),
            "cpu_pct":   0.0, "ram_pct": 0.0,
            "ram_total_gb": 0.0, "ram_used_gb": 0.0,
            "gpu_vram_pct": 0.0,
        }
        if not PSUTIL_OK:
            return stats
        try:
            stats["cpu_pct"]       = psutil.cpu_percent(interval=0.5)
            ram = psutil.virtual_memory()
            stats["ram_pct"]       = ram.percent
            stats["ram_total_gb"]  = round(ram.total / 1e9, 1)
            stats["ram_used_gb"]   = round(ram.used  / 1e9, 1)
        except Exception:
            pass
        # GPU via ComfyUI API
        try:
            import requests as req
            r = req.get("http://127.0.0.1:8188/system_stats", timeout=3)
            if r.status_code == 200:
                devices = r.json().get("devices",[])
                if devices:
                    d = devices[0]
                    total = d.get("vram_total",1)
                    free  = d.get("vram_free",1)
                    stats["gpu_vram_pct"] = round((total-free)/total*100, 1)
                    stats["gpu_vram_used_mb"] = total - free
                    stats["gpu_vram_total_mb"] = total
                    stats["gpu_name"] = d.get("name","GPU")
        except Exception:
            pass
        return stats

    # ── Rapports ─────────────────────────────────────────────────────

    def generate_health_report(self) -> dict:
        """Rapport de santé complet."""
        disks  = self.get_disk_info()
        stats  = self.get_system_stats()
        alerts = []

        for disk in disks:
            if disk.status == "critical":
                alerts.append(f"⚠ CRITIQUE : {disk.letter} ({disk.label}) à {disk.used_pct}%")
            elif disk.status == "warning":
                alerts.append(f"ℹ  Attention : {disk.letter} ({disk.label}) à {disk.used_pct}%")

        if stats.get("ram_pct",0) > 85:
            alerts.append(f"⚠ RAM saturée : {stats['ram_pct']}%")
        if stats.get("cpu_pct",0) > 90:
            alerts.append(f"⚠ CPU surchargé : {stats['cpu_pct']}%")

        report = {
            "timestamp": datetime.utcnow().isoformat(),
            "status":    "critical" if any("CRITIQUE" in a for a in alerts)
                         else "warning" if alerts else "ok",
            "alerts":    alerts,
            "disks":     [d.__dict__ for d in disks],
            "system":    stats,
        }

        # Sauvegarder
        ts   = datetime.now().strftime("%Y%m%d_%H%M")
        path = REPORT_DIR / f"health_{ts}.json"
        path.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
        self.log.info(
            f"[SYS] Rapport santé : {report['status'].upper()} | "
            f"{len(alerts)} alerte(s)"
        )
        return report

    # ── Maintenance ───────────────────────────────────────────────────

    def clean_workspace(self, dry_run: bool = True,
                         max_age_days: int = 30) -> dict:
        """Nettoie les fichiers temporaires anciens."""
        workspace = Path("workspace")
        if not workspace.exists():
            return {"deleted": 0, "freed_mb": 0}

        cutoff  = time.time() - max_age_days * 86400
        deleted = 0
        freed   = 0

        clean_patterns = [
            workspace / "radio_cache"  / "*.mp3",
            workspace / "audio_cache"  / "*.mp3",
            workspace / "3d_previews"  / "*.png",
            workspace / "obs_captures" / "*.png",
        ]

        for pattern in clean_patterns:
            parent = pattern.parent
            glob   = pattern.name
            if parent.exists():
                for f in parent.glob(glob):
                    if f.stat().st_mtime < cutoff:
                        size = f.stat().st_size
                        if not dry_run:
                            f.unlink()
                        freed   += size
                        deleted += 1

        result = {"deleted": deleted,
                   "freed_mb": round(freed/1e6, 1),
                   "dry_run": dry_run}
        self.log.info(
            f"[SYS] Nettoyage {'(simulation)' if dry_run else ''}: "
            f"{deleted} fichiers | {result['freed_mb']} Mo libérés"
        )
        return result

    def transfer_to_archive(self, src_dir: str, dest_drive: str = "G:",
                             min_age_days: int = 7, dry_run: bool = True) -> dict:
        """
        Transfère les fichiers anciens vers le HDD d'archive (G:).
        Utile pour migrer les archives vers le HDD 8To.
        """
        src    = Path(src_dir)
        dest   = Path(dest_drive) / src.name
        cutoff = time.time() - min_age_days * 86400

        if not src.exists():
            return {"error": f"Source introuvable : {src_dir}"}

        moved = 0; total_size = 0
        files = [f for f in src.rglob("*")
                 if f.is_file() and f.stat().st_mtime < cutoff]

        for f in files:
            rel  = f.relative_to(src)
            dst  = dest / rel
            size = f.stat().st_size
            if not dry_run:
                dst.parent.mkdir(parents=True, exist_ok=True)
                shutil.move(str(f), str(dst))
            moved      += 1
            total_size += size

        result = {"moved": moved,
                   "total_gb": round(total_size/1e9, 2),
                   "dest": str(dest), "dry_run": dry_run}
        self.log.info(
            f"[SYS] Archivage {'(simulation)' if dry_run else ''}: "
            f"{moved} fichiers → {dest_drive}"
        )
        return result

    def optimize_pipeline_disk(self) -> dict:
        """
        Recommandations d'organisation disque pour le pipeline OverLord.
        Basé sur la config matérielle (NVMe 2To + NVMe 2To + SSD 500Go + HDD 8To).
        """
        recommendations = {
            "C: (SSD 500Go — Windows/Jeux)": [
                "Windows + drivers GPU",
                "Jeux Steam/Epic (fichiers de jeu uniquement)",
                "NE PAS mettre ComfyUI ici (espace limité)",
            ],
            "D: (NVMe 2To — Système/Pipeline)": [
                "ComfyUI installation complète",
                "Python + environnements virtuels",
                "Modèles SDXL, VAE, LoRAs (2-5 Go chacun)",
                "Projet OverLord (code + workspace actif)",
                "Base ChromaDB (mémoire des agents)",
                "Cible : 500 Go pour les modèles, 200 Go pour le workspace",
            ],
            "E: (NVMe 2To — Stockage chaud)": [
                "Outputs récents (images, vidéos, STL)",
                "Assets de production en cours",
                "Cache audio/radio/captures",
                "Archives des 3 derniers mois",
                "Taille recommandée workspace/archive : 500 Go max",
            ],
            "G: (HDD 8To — Archives froides)": [
                "Productions terminées (> 1 mois)",
                "Backups des modèles (copie de sécurité)",
                "Anciennes versions du codebase",
                "Bases locales manga/anime/musique",
                "Accès lent — ne pas utiliser pour la production active",
            ],
        }
        recs_str = json.dumps(recommendations, indent=2, ensure_ascii=False)
        self.log.info("[SYS] Recommandations disque générées")
        return recommendations

    # ── Monitoring continu ────────────────────────────────────────────

    def start_monitoring(self, interval_s: int = 300,
                          alert_callback=None):
        """Lance le monitoring en tâche de fond."""
        def _loop():
            while True:
                report = self.generate_health_report()
                if report.get("alerts") and alert_callback:
                    alert_callback(report["alerts"])
                time.sleep(interval_s)

        t = threading.Thread(target=_loop, daemon=True)
        t.start()
        self.log.info(f"[SYS] Monitoring démarré (intervalle {interval_s}s)")
        return t

    def print_dashboard(self):
        """Affiche un dashboard texte du système."""
        disks  = self.get_disk_info()
        stats  = self.get_system_stats()
        print("\n" + "═"*55)
        print("  OverLord — Dashboard Système")
        print("═"*55)
        print(f"  CPU : {stats.get('cpu_pct',0):.0f}% | "
              f"RAM : {stats.get('ram_pct',0):.0f}% "
              f"({stats.get('ram_used_gb',0):.1f}/{stats.get('ram_total_gb',0):.0f} Go)")
        if "gpu_vram_pct" in stats:
            print(f"  GPU : {stats['gpu_vram_pct']:.0f}% VRAM utilisée")
        print()
        for d in disks:
            bar = "█"*int(d.used_pct/5) + "░"*(20-int(d.used_pct/5))
            icon = "⚠" if d.status=="critical" else "○" if d.status=="warning" else "✓"
            print(f"  {icon} {d.letter:<4} {d.label:<22} "
                  f"[{bar}] {d.used_pct:.0f}%  "
                  f"{d.free_gb:.0f} Go libres")
        print("═"*55 + "\n")


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    agent = SysAgent()
    agent.print_dashboard()
    report = agent.generate_health_report()
    print(f"Status : {report['status'].upper()}")
    for alert in report.get("alerts",[]):
        print(f"  {alert}")

    recs = agent.optimize_pipeline_disk()
    for disk, items in recs.items():
        print(f"\n{disk} :")
        for item in items:
            print(f"  • {item}")

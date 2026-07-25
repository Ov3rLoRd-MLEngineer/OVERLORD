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
storage_manager.py — Gestionnaire de Stockage Automatique OverLord
Surveille D: et déplace automatiquement vers E: puis G: selon les seuils.

Règles :
  D: SSD 1To  → si > 50% → déplace les outputs vers E:
  E: SSD 2To  → si > 80% → déplace les archives vers G:
  G: HDD 8To  → stockage froid — jamais déplacé

Lance en arrière-plan au démarrage d'OverLord.
Interface graphique tkinter pour visualiser l'état des disques.

Usage :
  python storage_manager.py          → interface graphique
  python storage_manager.py --daemon → mode silencieux en arrière-plan
  python storage_manager.py --status → rapport rapide en console
"""

import os
import sys
import shutil
import json
import time
import threading
import logging
from pathlib import Path
from datetime import datetime, timedelta
from dataclasses import dataclass

_REPO_ROOT = Path(__file__).resolve().parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))
import config

# ══════════════════════════════════════════════════════════════════════
# CONFIGURATION
# ══════════════════════════════════════════════════════════════════════

CONFIG_FILE = config.OVERLORD_ROOT / "config.json"

DISK_RULES = {
    "D:": {
        "label":          "SSD 1To — Pipeline",
        "threshold_pct":  50,         # → déplacer vers E: si > 50%
        "move_to":        "E:",
        "source_dirs":    [str(config.OVERLORD_ROOT / "outputs")],
        "keep_recent_days": 3,        # garder les 3 derniers jours sur D:
    },
    "E:": {
        "label":          "SSD 2To — Stockage chaud",
        "threshold_pct":  80,         # → déplacer vers G: si > 80%
        "move_to":        "G:",
        "source_dirs":    ["E:/OVERLORD_HOT"],
        "keep_recent_days": 90,       # garder les 90 derniers jours sur E:
    },
    "G:": {
        "label":          "HDD 8To — Archives froides",
        "threshold_pct":  90,         # alerte seulement, pas de déplacement
        "move_to":        None,
        "source_dirs":    ["G:/OVERLORD_COLD"],
        "keep_recent_days": 0,        # garder indéfiniment
    },
}

TRANSFERABLE_EXTENSIONS = {
    ".png", ".jpg", ".jpeg", ".webp",   # images
    ".mp4", ".avi", ".mkv", ".webm",   # vidéos
    ".mp3", ".wav", ".flac",            # audio
    ".stl", ".obj", ".fbx",             # 3D
    ".zip", ".rar", ".7z",              # archives
}

CHECK_INTERVAL_S  = 300   # vérifier toutes les 5 minutes
LOG_FILE          = config.WORKSPACE_DIR / "sys_reports" / "storage_manager.log"


# ══════════════════════════════════════════════════════════════════════
# MODÈLE DE DONNÉES
# ══════════════════════════════════════════════════════════════════════

@dataclass
class DiskStatus:
    drive:      str
    label:      str
    total_gb:   float
    used_gb:    float
    free_gb:    float
    used_pct:   float
    available:  bool
    threshold:  float
    status:     str   # "ok" / "warning" / "critical" / "unavailable"

    @property
    def color_code(self) -> str:
        if not self.available:   return "grey"
        if self.status == "ok": return "green"
        if self.status == "warning": return "orange"
        return "red"


# ══════════════════════════════════════════════════════════════════════
# MOTEUR DE STOCKAGE
# ══════════════════════════════════════════════════════════════════════

class StorageEngine:
    """Moteur de surveillance et de déplacement automatique."""

    def __init__(self, logger: logging.Logger = None):
        self.log        = logger or logging.getLogger("storage")
        self._transfers: list[dict] = []
        self._lock       = threading.Lock()
        self._listeners  = []

    def add_listener(self, cb):
        self._listeners.append(cb)

    def _emit(self, event: str, data: dict):
        for cb in self._listeners:
            try: cb(event, data)
            except Exception: pass

    # ── État des disques ──────────────────────────────────────────────

    def get_disk_status(self, drive: str) -> DiskStatus:
        """Retourne l'état d'un disque."""
        cfg = DISK_RULES.get(drive, {})
        label = cfg.get("label", drive)
        threshold = cfg.get("threshold_pct", 80)

        drive_path = drive + "\\"
        if not Path(drive_path).exists():
            return DiskStatus(
                drive=drive, label=label,
                total_gb=0, used_gb=0, free_gb=0,
                used_pct=0, available=False,
                threshold=threshold, status="unavailable"
            )
        try:
            total, used, free = shutil.disk_usage(drive_path)
            total_gb = total / 1e9
            used_gb  = used  / 1e9
            free_gb  = free  / 1e9
            used_pct = used / total * 100

            if used_pct >= threshold + 10:
                status = "critical"
            elif used_pct >= threshold:
                status = "warning"
            else:
                status = "ok"

            return DiskStatus(
                drive=drive, label=label,
                total_gb=round(total_gb,1), used_gb=round(used_gb,1),
                free_gb=round(free_gb,1),  used_pct=round(used_pct,1),
                available=True, threshold=threshold, status=status,
            )
        except Exception as e:
            self.log.warning(f"[STORAGE] {drive} status : {e}")
            return DiskStatus(
                drive=drive, label=label,
                total_gb=0, used_gb=0, free_gb=0,
                used_pct=0, available=False,
                threshold=threshold, status="unavailable"
            )

    def get_all_status(self) -> dict[str, DiskStatus]:
        return {drive: self.get_disk_status(drive)
                for drive in DISK_RULES.keys()}

    # ── Détection des fichiers à déplacer ─────────────────────────────

    def find_movable_files(self, source_dirs: list[str],
                            keep_recent_days: int = 3) -> list[Path]:
        """
        Trouve les fichiers éligibles au déplacement :
        - Extension transférable
        - Plus anciens que keep_recent_days
        - Pas déjà en cours de génération
        """
        cutoff   = datetime.now() - timedelta(days=max(0, keep_recent_days))
        movable  = []

        for src_dir in source_dirs:
            p = Path(src_dir)
            if not p.exists():
                continue
            for f in p.rglob("*"):
                if not f.is_file():
                    continue
                if f.suffix.lower() not in TRANSFERABLE_EXTENSIONS:
                    continue
                try:
                    mtime = datetime.fromtimestamp(f.stat().st_mtime)
                    if mtime < cutoff:
                        movable.append(f)
                except Exception:
                    pass

        # Trier du plus ancien au plus récent
        movable.sort(key=lambda f: f.stat().st_mtime)
        return movable

    # ── Transfert ─────────────────────────────────────────────────────

    def transfer_files(self, files: list[Path],
                        dest_root: str,
                        dry_run: bool = False) -> dict:
        """
        Déplace une liste de fichiers vers dest_root.
        Préserve la structure de sous-dossiers relative.
        """
        dest_path = Path(dest_root)
        if not dry_run:
            dest_path.mkdir(parents=True, exist_ok=True)

        moved = 0; errors = 0; total_bytes = 0

        for f in files:
            try:
                # Construire le chemin destination
                # Exemple : D:/OVERLORD/outputs/images/run_001.png
                #        → E:/OVERLORD_HOT/images/run_001.png
                parts = f.parts
                # Trouver la partie relative après "outputs" ou "OVERLORD_HOT"
                anchor_keywords = ["outputs","OVERLORD_HOT","OVERLORD_COLD"]
                rel_start = 0
                for i, part in enumerate(parts):
                    if any(kw in part for kw in anchor_keywords):
                        rel_start = i + 1
                        break

                rel = Path(*parts[rel_start:]) if rel_start > 0 else Path(f.name)
                dest = dest_path / rel
                size = f.stat().st_size

                if not dry_run:
                    dest.parent.mkdir(parents=True, exist_ok=True)
                    shutil.move(str(f), str(dest))

                moved += 1
                total_bytes += size
                self.log.debug(f"[STORAGE] → {f.name} → {dest_path.name}")

            except Exception as e:
                self.log.warning(f"[STORAGE] Move {f.name} : {e}")
                errors += 1

        result = {
            "moved":    moved,
            "errors":   errors,
            "total_gb": round(total_bytes / 1e9, 3),
            "dry_run":  dry_run,
            "dest":     str(dest_root),
            "ts":       datetime.utcnow().isoformat(),
        }
        with self._lock:
            self._transfers.append(result)
        self.log.info(
            f"[STORAGE] {'(simulation) ' if dry_run else ''}"
            f"{moved} fichiers déplacés → {dest_root} "
            f"({result['total_gb']:.2f} Go)"
        )
        self._emit("transfer_done", result)
        return result

    # ── Vérification et action automatique ────────────────────────────

    def check_and_act(self, dry_run: bool = False) -> list[dict]:
        """
        Vérifie l'état de tous les disques et agit si nécessaire.
        C'est la méthode principale appelée périodiquement.
        """
        actions_taken = []
        all_status    = self.get_all_status()

        for drive, rule in DISK_RULES.items():
            status = all_status.get(drive)
            if not status or not status.available:
                continue
            if status.used_pct < status.threshold:
                continue

            dest_drive = rule.get("move_to")
            if not dest_drive:
                # Pas de déplacement possible → alerte seulement
                self.log.warning(
                    f"[STORAGE] ⚠ {drive} à {status.used_pct:.0f}% "
                    f"(seuil {status.threshold}%) — aucune destination configurée"
                )
                self._emit("alert", {
                    "drive":   drive,
                    "used_pct":status.used_pct,
                    "message": f"{drive} presque plein ({status.used_pct:.0f}%)"
                })
                continue

            # Vérifier que la destination est disponible
            dest_status = all_status.get(dest_drive)
            if not dest_status or not dest_status.available:
                self.log.warning(
                    f"[STORAGE] {drive} > seuil mais {dest_drive} non disponible"
                )
                self._emit("alert", {
                    "drive":   drive,
                    "message": f"Déplacement impossible : {dest_drive} non connecté"
                })
                continue

            # Trouver les fichiers à déplacer
            source_dirs = rule.get("source_dirs", [])
            keep_days   = rule.get("keep_recent_days", 3)
            movable     = self.find_movable_files(source_dirs, keep_days)

            if not movable:
                self.log.info(
                    f"[STORAGE] {drive} > seuil mais aucun fichier déplaçable trouvé"
                )
                continue

            # Destination
            dest_map = {
                "E:": "E:/OVERLORD_HOT",
                "G:": "G:/OVERLORD_COLD",
            }
            dest_root = dest_map.get(dest_drive, f"{dest_drive}/OVERLORD")

            self.log.info(
                f"[STORAGE] {drive} à {status.used_pct:.0f}% "
                f"({status.used_gb:.1f}/{status.total_gb:.1f} Go) "
                f"— déplacement de {len(movable)} fichiers vers {dest_root}"
            )

            # Transférer par paquets de 100 Mo max
            batch       = []
            batch_bytes = 0
            MAX_BATCH   = 100 * 1e6  # 100 Mo par passe

            for f in movable:
                try:
                    size = f.stat().st_size
                    batch.append(f)
                    batch_bytes += size
                    if batch_bytes >= MAX_BATCH:
                        result = self.transfer_files(batch, dest_root, dry_run)
                        actions_taken.append(result)
                        batch = []; batch_bytes = 0
                        # Re-vérifier si on est revenu sous le seuil
                        new_status = self.get_disk_status(drive)
                        if new_status.used_pct < status.threshold - 5:
                            break
                except Exception:
                    pass

            if batch:
                result = self.transfer_files(batch, dest_root, dry_run)
                actions_taken.append(result)

        return actions_taken

    def get_transfer_history(self, n: int = 10) -> list[dict]:
        with self._lock:
            return list(self._transfers[-n:])

    def generate_report(self) -> str:
        """Rapport texte de l'état du stockage."""
        lines = [
            f"RAPPORT STOCKAGE — {datetime.now().strftime('%d/%m/%Y %H:%M')}",
            "=" * 55,
        ]
        for drive, status in self.get_all_status().items():
            if not status.available:
                lines.append(f"  {drive} — Non connecté ({status.label})")
                continue
            bar    = "█" * int(status.used_pct/5) + "░" * (20-int(status.used_pct/5))
            icon   = "⚠" if status.status in ("warning","critical") else "✓"
            lines.append(
                f"  {icon} {drive} [{bar}] {status.used_pct:.0f}%  "
                f"{status.used_gb:.0f}/{status.total_gb:.0f} Go  "
                f"({status.label})"
            )
        lines.append("=" * 55)
        history = self.get_transfer_history(3)
        if history:
            lines.append("Derniers transferts :")
            for t in history:
                lines.append(
                    f"  → {t['moved']} fichiers "
                    f"({t['total_gb']:.2f} Go) vers {t['dest']} "
                    f"[{t['ts'][:16]}]"
                )
        return "\n".join(lines)


# ══════════════════════════════════════════════════════════════════════
# INTERFACE GRAPHIQUE
# ══════════════════════════════════════════════════════════════════════

def run_gui():
    """Interface graphique pour le gestionnaire de stockage."""
    import tkinter as tk
    from tkinter import ttk

    P = {
        "bg":"#050508","surf":"#0C0C18","surf2":"#141422",
        "ok":"#10B981","warn":"#F59E0B","err":"#EF4444",
        "text":"#E0E0F8","textd":"#7070A8",
        "accent":"#7C3AED","btn":"#7C3AED","btnfg":"#FFFFFF",
    }

    engine = StorageEngine()
    root   = tk.Tk()
    root.title("Ov3rLoRd — Gestionnaire de Stockage")
    root.configure(bg=P["bg"])
    root.geometry("700x500")
    root.resizable(True, True)

    # Titre
    tk.Label(root,
             text="  💾  Gestionnaire de Stockage OverLord",
             font=("Segoe UI",12,"bold"), bg=P["surf"], fg=P["accent"]
             ).pack(fill="x", ipady=10)

    # Cartes disques
    disks_frame = tk.Frame(root, bg=P["bg"])
    disks_frame.pack(fill="x", padx=12, pady=8)

    disk_cards = {}
    for i, (drive, rule) in enumerate(DISK_RULES.items()):
        card = tk.Frame(disks_frame, bg=P["surf2"], padx=14, pady=12)
        card.pack(side="left", fill="x", expand=True, padx=4)
        tk.Label(card, text=f"  {drive}", font=("Segoe UI",13,"bold"),
                 bg=P["surf2"], fg=P["text"]).pack(anchor="w")
        tk.Label(card, text=rule["label"], font=("Segoe UI",8),
                 bg=P["surf2"], fg=P["textd"]).pack(anchor="w")
        pct_var  = tk.StringVar(value="—")
        free_var = tk.StringVar(value="—")
        status_var = tk.StringVar(value="⚫ Non connecté")
        bar_canvas = tk.Canvas(card, height=10, bg=P["surf2"],
                                highlightthickness=0)
        bar_canvas.pack(fill="x", pady=4)
        tk.Label(card, textvariable=pct_var,
                 font=("Segoe UI",16,"bold"),
                 bg=P["surf2"], fg=P["text"]).pack(anchor="w")
        tk.Label(card, textvariable=free_var, font=("Segoe UI",8),
                 bg=P["surf2"], fg=P["textd"]).pack(anchor="w")
        tk.Label(card, textvariable=status_var, font=("Segoe UI",8),
                 bg=P["surf2"], fg=P["ok"]).pack(anchor="w")
        disk_cards[drive] = {
            "card":       card,
            "pct_var":    pct_var,
            "free_var":   free_var,
            "status_var": status_var,
            "bar":        bar_canvas,
        }

    # Log
    tk.Label(root, text="Journal des transferts",
             font=("Segoe UI",9,"bold"), bg=P["bg"], fg=P["textd"]
             ).pack(anchor="w", padx=12, pady=(8,2))
    log_frame = tk.Frame(root, bg=P["bg"])
    log_frame.pack(fill="both", expand=True, padx=12, pady=(0,8))
    log_text = tk.Text(log_frame, font=("Consolas",8), bg="#020208",
                        fg="#A0FFA8", relief="flat", state="disabled")
    log_sc = tk.Scrollbar(log_frame, command=log_text.yview)
    log_text.configure(yscrollcommand=log_sc.set)
    log_sc.pack(side="right", fill="y")
    log_text.pack(fill="both", expand=True)

    # Boutons
    btn_f = tk.Frame(root, bg=P["bg"])
    btn_f.pack(fill="x", padx=12, pady=4)
    tk.Button(btn_f, text="🔄 Actualiser", bg=P["surf2"], fg=P["text"],
              font=("Segoe UI",9), relief="flat", bd=0, cursor="hand2",
              padx=10, pady=6, command=lambda: update_display()
              ).pack(side="left", padx=4)
    tk.Button(btn_f, text="▶ Libérer l'espace maintenant",
              bg=P["btn"], fg=P["btnfg"],
              font=("Segoe UI",9,"bold"), relief="flat", bd=0,
              cursor="hand2", padx=12, pady=6,
              command=lambda: free_space(dry_run=False)
              ).pack(side="left", padx=4)
    tk.Button(btn_f, text="👁 Simulation (dry-run)",
              bg=P["surf2"], fg=P["text"],
              font=("Segoe UI",9), relief="flat", bd=0,
              cursor="hand2", padx=10, pady=6,
              command=lambda: free_space(dry_run=True)
              ).pack(side="left", padx=4)

    self_lbl = tk.Label(btn_f, text="⚙ Surveillance automatique : Active",
                         font=("Segoe UI",8), bg=P["bg"], fg=P["ok"])
    self_lbl.pack(side="right", padx=8)

    def log_line(msg: str):
        ts = datetime.now().strftime("%H:%M:%S")
        log_text.configure(state="normal")
        log_text.insert("end", f"[{ts}] {msg}\n")
        log_text.see("end")
        log_text.configure(state="disabled")

    def update_display():
        all_status = engine.get_all_status()
        for drive, dc in disk_cards.items():
            st = all_status.get(drive)
            if not st or not st.available:
                dc["pct_var"].set("N/A")
                dc["free_var"].set("Non connecté")
                dc["status_var"].set("⚫ Non connecté")
                dc["card"].configure(bg=P["surf2"])
                continue

            dc["pct_var"].set(f"{st.used_pct:.0f}%")
            dc["free_var"].set(f"{st.free_gb:.0f} Go libres / {st.total_gb:.0f} Go")

            color = {"ok":P["ok"],"warning":P["warn"],"critical":P["err"]}.get(
                st.status, P["textd"])
            icon  = {"ok":"✅","warning":"⚠️","critical":"🔴"}.get(st.status,"⚫")
            dc["status_var"].set(f"{icon} {st.status.upper()}")

            # Barre de progression
            dc["bar"].delete("all")
            w = dc["bar"].winfo_width() or 200
            fill_w = int(w * st.used_pct / 100)
            dc["bar"].create_rectangle(0,0,w,10,fill=P["surf2"],outline="")
            if fill_w > 0:
                dc["bar"].create_rectangle(0,0,fill_w,10,fill=color,outline="")

    def free_space(dry_run: bool = False):
        mode = "SIMULATION" if dry_run else "TRANSFERT RÉEL"
        log_line(f"── {mode} démarré ──")
        def _run():
            actions = engine.check_and_act(dry_run=dry_run)
            if actions:
                for a in actions:
                    log_line(
                        f"→ {a['moved']} fichiers "
                        f"({a['total_gb']:.2f} Go) vers {Path(a['dest']).name}"
                    )
            else:
                log_line("Aucune action nécessaire — disques dans les normes.")
            update_display()
        import threading
        threading.Thread(target=_run, daemon=True).start()

    # Surveillance automatique en arrière-plan
    def _auto_check():
        while True:
            time.sleep(CHECK_INTERVAL_S)
            try:
                actions = engine.check_and_act(dry_run=False)
                if actions:
                    for a in actions:
                        log_line(
                            f"AUTO → {a['moved']} fichiers déplacés "
                            f"vers {Path(a['dest']).name}"
                        )
                    root.after(100, update_display)
            except Exception:
                pass

    threading.Thread(target=_auto_check, daemon=True).start()

    # Mise à jour au démarrage
    root.after(200, update_display)
    root.after(500, lambda: log_line(
        "Gestionnaire de stockage démarré. "
        f"Vérification automatique toutes les {CHECK_INTERVAL_S//60} minutes."
    ))

    root.mainloop()


# ══════════════════════════════════════════════════════════════════════
# CLI
# ══════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO,
                         format="%(asctime)s %(message)s")

    args = sys.argv[1:]

    if "--status" in args:
        engine = StorageEngine()
        print(engine.generate_report())

    elif "--daemon" in args:
        engine = StorageEngine()
        print(f"[STORAGE] Mode daemon — vérification toutes les {CHECK_INTERVAL_S}s")
        while True:
            try:
                engine.check_and_act(dry_run=False)
            except Exception as e:
                print(f"[STORAGE] Erreur : {e}")
            time.sleep(CHECK_INTERVAL_S)

    elif "--free" in args:
        engine = StorageEngine()
        dry = "--dry-run" in args
        print(f"Libération de l'espace {'(simulation) ' if dry else ''}...")
        actions = engine.check_and_act(dry_run=dry)
        if actions:
            for a in actions:
                print(f"  → {a['moved']} fichiers ({a['total_gb']:.2f} Go) vers {a['dest']}")
        else:
            print("  Aucune action nécessaire.")

    else:
        # Interface graphique par défaut
        try:
            run_gui()
        except ImportError:
            # Fallback console si tkinter absent
            engine = StorageEngine()
            print(engine.generate_report())

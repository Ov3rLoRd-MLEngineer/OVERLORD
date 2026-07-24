"""
overlord_launcher.py — Launcher Gaming Ov3rLoRd v1.45
Style ASUS ROG/Strix : gros boutons, dégradés, coins arrondis, resizable.
Se compile en OverLord.exe via build_launcher.py.

Inspirations : ASUS ROG Armoury Crate, MSI Dragon Center, NZXT CAM
"""

import subprocess
import sys
import os
import json
import threading
import time
from pathlib import Path
from datetime import datetime

try:
    import tkinter as tk
    from tkinter import ttk, messagebox, filedialog
    TK_OK = True
except ImportError:
    TK_OK = False
    print("[ERREUR] tkinter non disponible")
    sys.exit(1)

BASE_DIR = Path(__file__).resolve().parent

# ── Palette ROG/Gaming ────────────────────────────────────────────────
THEMES = {
    "rog_dark": {
        "bg":       "#0D0D0D",
        "bg2":      "#141414",
        "bg3":      "#1C1C1C",
        "accent1":  "#CC0000",
        "accent2":  "#FF4400",
        "text":     "#FFFFFF",
        "text2":    "#888888",
        "success":  "#00FF88",
        "warning":  "#FFAA00",
        "name":     "ROG Dark",
    },
    "overlord_cyber": {
        "bg":       "#080C14",
        "bg2":      "#0D1520",
        "bg3":      "#121C2A",
        "accent1":  "#00FFB3",
        "accent2":  "#0066FF",
        "text":     "#E8F4FF",
        "text2":    "#6A8BA8",
        "success":  "#00FFB3",
        "warning":  "#FFAA00",
        "name":     "Ov3rLoRd Cyber",
    },
    "strix_purple": {
        "bg":       "#0A0010",
        "bg2":      "#100020",
        "bg3":      "#180030",
        "accent1":  "#AA00FF",
        "accent2":  "#FF00AA",
        "text":     "#FFFFFF",
        "text2":    "#9966BB",
        "success":  "#00FF88",
        "warning":  "#FFAA00",
        "name":     "Strix Purple",
    },
    "msi_dragon": {
        "bg":       "#0A0000",
        "bg2":      "#150000",
        "bg3":      "#200000",
        "accent1":  "#FF0000",
        "accent2":  "#FF6600",
        "text":     "#FFFFFF",
        "text2":    "#AA6666",
        "success":  "#00FF88",
        "warning":  "#FFAA00",
        "name":     "MSI Dragon",
    },
}

SETTINGS_FILE = BASE_DIR / "settings.json"


def load_settings() -> dict:
    if SETTINGS_FILE.exists():
        try:
            return json.loads(SETTINGS_FILE.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {"launcher_theme": "overlord_cyber", "launcher_scale": 1.0}


def save_settings(s: dict):
    try:
        existing = load_settings()
        existing.update(s)
        SETTINGS_FILE.write_text(json.dumps(existing, indent=2, ensure_ascii=False), encoding="utf-8")
    except Exception:
        pass


class GamingButton(tk.Canvas):
    """
    Bouton gaming personnalisé : coins arrondis, dégradé, glow hover.
    Inspiré ASUS ROG Armoury Crate.
    """

    def __init__(self, parent, text, command=None, icon="", theme=None,
                 width=220, height=52, **kwargs):
        super().__init__(parent, width=width, height=height,
                         highlightthickness=0, **kwargs)
        self.text    = text
        self.icon    = icon
        self.command = command
        self.theme   = theme or THEMES["overlord_cyber"]
        self.w       = width
        self.h       = height
        self._hovered = False
        self._pressed = False

        self.configure(bg=self.theme["bg2"], cursor="hand2")
        self.bind("<Enter>",    self._on_enter)
        self.bind("<Leave>",    self._on_leave)
        self.bind("<Button-1>", self._on_press)
        self.bind("<ButtonRelease-1>", self._on_release)
        self._draw()

    def _draw(self):
        self.delete("all")
        t  = self.theme
        r  = 10  # rayon des coins

        if self._pressed:
            fill = t["accent2"]
            text_color = "#000000"
        elif self._hovered:
            fill = t["accent1"]
            text_color = "#000000"
        else:
            fill = t["bg3"]
            text_color = t["text"]

        border_color = t["accent1"] if self._hovered else t["accent2"] + "88"

        # Fond arrondi
        self._rounded_rect(2, 2, self.w-2, self.h-2, r, fill=fill, outline=border_color, width=1)

        # Ligne déco gauche (style ROG)
        if not self._pressed:
            self.create_rectangle(2, 2, 5, self.h-2, fill=t["accent1"], outline="")

        # Texte + icône
        label = f"{self.icon}  {self.text}" if self.icon else self.text
        self.create_text(
            self.w // 2, self.h // 2,
            text=label,
            fill=text_color,
            font=("Orbitron", 9, "bold") if self._hovered else ("Segoe UI", 9, "bold"),
            anchor="center"
        )

        # Glow effect (simulation)
        if self._hovered:
            self.create_rectangle(2, self.h-4, self.w-2, self.h-2,
                                  fill=t["accent1"], outline="")

    def _rounded_rect(self, x1, y1, x2, y2, r, **kwargs):
        points = [
            x1+r, y1, x2-r, y1,
            x2, y1, x2, y1+r,
            x2, y2-r, x2, y2,
            x2-r, y2, x1+r, y2,
            x1, y2, x1, y2-r,
            x1, y1+r, x1, y1,
        ]
        self.create_polygon(points, smooth=True, **kwargs)

    def _on_enter(self, e):
        self._hovered = True
        self._draw()

    def _on_leave(self, e):
        self._hovered = False
        self._draw()

    def _on_press(self, e):
        self._pressed = True
        self._draw()

    def _on_release(self, e):
        self._pressed = False
        self._hovered = True
        self._draw()
        if self.command:
            self.command()


class StatusBar(tk.Frame):
    """Barre de statut en bas — affiche ComfyUI, Ollama, pipeline."""

    def __init__(self, parent, theme, **kwargs):
        super().__init__(parent, bg=theme["bg"], **kwargs)
        self.theme = theme
        self._items = {}
        self._create()

    def _create(self):
        statuses = [
            ("pipeline", "PIPELINE", "●"),
            ("comfyui",  "COMFYUI",  "●"),
            ("ollama",   "OLLAMA",   "●"),
            ("oracle",   "ORACLE",   "●"),
        ]
        for key, label, dot in statuses:
            f = tk.Frame(self, bg=self.theme["bg"], padx=8)
            f.pack(side="left")
            dot_lbl = tk.Label(f, text=dot, fg=self.theme["text2"],
                               bg=self.theme["bg"], font=("Segoe UI", 8))
            dot_lbl.pack(side="left")
            txt_lbl = tk.Label(f, text=label, fg=self.theme["text2"],
                               bg=self.theme["bg"], font=("Segoe UI", 7))
            txt_lbl.pack(side="left", padx=2)
            self._items[key] = (dot_lbl, txt_lbl)

        self._clock = tk.Label(self, text="", fg=self.theme["text2"],
                               bg=self.theme["bg"], font=("Courier New", 7))
        self._clock.pack(side="right", padx=10)
        self._update_clock()

    def _update_clock(self):
        self._clock.config(text=datetime.now().strftime("%d/%m/%Y %H:%M:%S"))
        self.after(1000, self._update_clock)

    def set_status(self, key: str, online: bool):
        if key in self._items:
            color = self.theme["success"] if online else self.theme["text2"]
            self._items[key][0].config(fg=color)
            self._items[key][1].config(fg=color)


class OverLordLauncher:
    """
    Launcher gaming principal.
    Layout : Header | Grid de boutons | Log panel | Status bar
    Resizable comme l'explorateur Windows (resize coin bas-droit).
    """

    def __init__(self):
        self.settings = load_settings()
        theme_key = self.settings.get("launcher_theme", "overlord_cyber")
        self.theme = THEMES.get(theme_key, THEMES["overlord_cyber"])

        self.root = tk.Tk()
        self.root.title("Ov3rLoRd Pipeline v1.45")
        self.root.configure(bg=self.theme["bg"])
        self.root.minsize(780, 560)
        self.root.geometry("900x660")

        # Icône (si disponible)
        try:
            self.root.iconbitmap(str(BASE_DIR / "icon.ico"))
        except Exception:
            pass

        # Resizable — coin bas-droit via grip tkinter standard
        self.root.resizable(True, True)

        self._build_ui()
        self._check_services()

    def _build_ui(self):
        t = self.theme

        # ── HEADER ──
        header = tk.Frame(self.root, bg=t["bg2"], height=70)
        header.pack(fill="x", side="top")
        header.pack_propagate(False)

        tk.Label(
            header, text="Ov3rLoRd",
            font=("Orbitron", 22, "bold"),
            fg=t["accent1"], bg=t["bg2"]
        ).pack(side="left", padx=20, pady=10)

        tk.Label(
            header, text="Pipeline v1.45  |  Cyborg-Zen",
            font=("Segoe UI", 9), fg=t["text2"], bg=t["bg2"]
        ).pack(side="left", pady=18)

        # Boutons header droite
        hbf = tk.Frame(header, bg=t["bg2"])
        hbf.pack(side="right", padx=10)

        for label, cmd in [("⚙", self._open_settings), ("✕", self.root.quit)]:
            b = tk.Button(hbf, text=label, command=cmd,
                          bg=t["bg3"], fg=t["text"], relief="flat",
                          font=("Segoe UI", 11), width=3, cursor="hand2",
                          activebackground=t["accent1"], activeforeground="#000")
            b.pack(side="left", padx=2, pady=15)

        # Ligne accent
        tk.Frame(self.root, bg=t["accent1"], height=2).pack(fill="x")

        # ── SELECTOR THÈME ──
        theme_bar = tk.Frame(self.root, bg=t["bg3"], height=30)
        theme_bar.pack(fill="x")
        tk.Label(theme_bar, text="THÈME :", fg=t["text2"], bg=t["bg3"],
                 font=("Segoe UI", 7)).pack(side="left", padx=8, pady=6)

        for tk_name, td in THEMES.items():
            def _set(tn=tk_name):
                self.settings["launcher_theme"] = tn
                save_settings(self.settings)
                messagebox.showinfo("Thème", f"Thème '{THEMES[tn]['name']}' appliqué au prochain lancement.")
            btn = tk.Button(theme_bar, text=td["name"],
                            bg=td["accent1"], fg="#000",
                            relief="flat", font=("Segoe UI", 7, "bold"),
                            cursor="hand2", command=_set, padx=6, pady=2)
            btn.pack(side="left", padx=3, pady=4)

        # ── CONTENU PRINCIPAL ──
        main = tk.Frame(self.root, bg=t["bg"])
        main.pack(fill="both", expand=True, padx=12, pady=8)

        # Colonne gauche : boutons modules
        left = tk.Frame(main, bg=t["bg"])
        left.pack(side="left", fill="y", padx=(0, 8))

        tk.Label(left, text="◈ MODULES", fg=t["accent1"], bg=t["bg"],
                 font=("Orbitron", 8), pady=8).pack(anchor="w")

        self._modules = [
            ("▶  MAESTRO PIPELINE",    "▶",  self._launch_maestro,     True),
            ("   Oracle CLI",          "◉",  self._launch_oracle,      False),
            ("   Interface Principale","⬡",  self._launch_main,        False),
            ("   Self-Improve",        "⟳",  self._launch_self_improve,False),
            ("   Test Pipeline",       "✔",  self._launch_test,        False),
            ("   Gestionnaire Stock.", "⊞",  self._launch_storage,     False),
            ("   Dashboard v1.20",     "▦",  self._launch_dash120,     False),
            ("   Graphe Neuronal",     "⬡",  self._launch_graph,       False),
            ("   Chat Llama",          "◎",  self._launch_llama,       False),
            ("   Serveur Licences",    "⚿",  self._launch_licence,     False),
            ("   Agent Apprenant",     "✦",  self._launch_learning,    False),
        ]

        for label, icon, cmd, primary in self._modules:
            th = {**t}
            if primary:
                th["bg3"] = t["accent2"]
                th["accent1"] = "#FFFFFF"
            btn = GamingButton(left, text=label, command=cmd,
                               theme=th, width=240, height=44)
            btn.pack(pady=3, anchor="w")

        # Colonne droite : logs + stats
        right = tk.Frame(main, bg=t["bg"])
        right.pack(side="left", fill="both", expand=True)

        tk.Label(right, text="◈ LOGS", fg=t["accent1"], bg=t["bg"],
                 font=("Orbitron", 8), pady=8).pack(anchor="w")

        # Zone log scrollable
        log_frame = tk.Frame(right, bg=t["bg3"], bd=1, relief="flat")
        log_frame.pack(fill="both", expand=True)

        self._log_text = tk.Text(
            log_frame, bg=t["bg3"], fg=t["text2"],
            font=("Courier New", 8), state="disabled",
            wrap="word", relief="flat", bd=0,
            insertbackground=t["accent1"]
        )
        scrollbar = tk.Scrollbar(log_frame, command=self._log_text.yview,
                                 bg=t["bg2"], troughcolor=t["bg"])
        self._log_text.configure(yscrollcommand=scrollbar.set)
        scrollbar.pack(side="right", fill="y")
        self._log_text.pack(fill="both", expand=True, padx=4, pady=4)

        # Stats rapides
        stats_frame = tk.Frame(right, bg=t["bg2"], height=60)
        stats_frame.pack(fill="x", pady=(6, 0))
        stats_frame.pack_propagate(False)

        self._stat_labels = {}
        for key, label in [("blocs", "BLOCS"), ("score", "SCORE"), ("patches", "PATCHES")]:
            f = tk.Frame(stats_frame, bg=t["bg2"])
            f.pack(side="left", expand=True, padx=10, pady=8)
            tk.Label(f, text=label, fg=t["text2"], bg=t["bg2"],
                     font=("Orbitron", 6)).pack()
            lbl = tk.Label(f, text="—", fg=t["accent1"], bg=t["bg2"],
                           font=("Orbitron", 14, "bold"))
            lbl.pack()
            self._stat_labels[key] = lbl

        # ── STATUS BAR ──
        sep = tk.Frame(self.root, bg=t["accent1"], height=1)
        sep.pack(fill="x")

        self._status_bar = StatusBar(self.root, t)
        self._status_bar.pack(fill="x", side="bottom", ipady=4)

        # Grip de resize (coin bas-droit)
        grip = ttk.Sizegrip(self.root)
        grip.pack(side="bottom", anchor="se")

        self._log("Ov3rLoRd Launcher v1.45 démarré")
        self._log(f"Dossier : {BASE_DIR}")

    def _log(self, msg: str, level: str = "INFO"):
        ts = datetime.now().strftime("%H:%M:%S")
        colors = {"INFO": self.theme["text2"], "OK": self.theme["success"],
                  "WARN": self.theme["warning"], "ERR": self.theme["accent2"]}
        self._log_text.configure(state="normal")
        self._log_text.insert("end", f"[{ts}] [{level}] {msg}\n")
        self._log_text.configure(state="disabled")
        self._log_text.see("end")

    def _run(self, script: str, args: list = None):
        """Lance un script Python dans un thread séparé."""
        def _exec():
            self._log(f"Lancement : {script}")
            cmd = [sys.executable, str(BASE_DIR / script)] + (args or [])
            try:
                result = subprocess.run(cmd, capture_output=True, text=True,
                                        encoding="utf-8", errors="replace")
                if result.returncode == 0:
                    self._log(f"✓ {script} terminé", "OK")
                else:
                    self._log(f"✗ {script} code={result.returncode}", "ERR")
                    if result.stderr:
                        for line in result.stderr.split('\n')[:5]:
                            if line.strip():
                                self._log(f"  {line}", "ERR")
            except Exception as e:
                self._log(f"Exception : {e}", "ERR")
        threading.Thread(target=_exec, daemon=True).start()

    def _launch_maestro(self):
        from tkinter.simpledialog import askstring
        media = askstring("Maestro", "Media type (anime/manga/3d/art) :", initialvalue="anime")
        if not media:
            return
        universe = askstring("Maestro", "Univers (ex: Dragon Ball) :", initialvalue="")
        args = ["--media-type", media]
        if universe:
            args += ["--universe", universe]
        self._run("maestro.py", args)

    def _launch_oracle(self):        self._run("oracle_interface.py")
    def _launch_main(self):          self._run("launcher.py")
    def _launch_self_improve(self):  self._run("self_improve.py", ["--mode", "auto", "--dry-run"])
    def _launch_test(self):          self._run("test_pipeline.py", ["--quick"])
    def _launch_storage(self):       self._run("storage_manager.py")
    def _launch_dash120(self):       self._run("agents/dashboard.py")
    def _launch_graph(self):         self._run("agents/graph_ui.py")
    def _launch_llama(self):         self._run("llama_chat.py")
    def _launch_licence(self):       self._run("licence_server.py")
    def _launch_learning(self):      self._run("learning_ui.py")

    def _check_services(self):
        """Vérifie ComfyUI et Ollama en arrière-plan."""
        def _check():
            try:
                import requests
                r = requests.get("http://127.0.0.1:8188/system_stats", timeout=2)
                self._status_bar.set_status("comfyui", r.status_code == 200)
            except Exception:
                self._status_bar.set_status("comfyui", False)
            try:
                import requests
                r = requests.get("http://localhost:11434/api/tags", timeout=2)
                self._status_bar.set_status("ollama", r.status_code == 200)
            except Exception:
                self._status_bar.set_status("ollama", False)
            self._status_bar.set_status("oracle", True)
            self._log("Vérification des services terminée", "OK")
        threading.Thread(target=_check, daemon=True).start()

    def _open_settings(self):
        win = tk.Toplevel(self.root)
        win.title("Paramètres — Ov3rLoRd")
        win.configure(bg=self.theme["bg"])
        win.geometry("420x340")
        win.resizable(False, False)

        tk.Label(win, text="⚙ PARAMÈTRES", fg=self.theme["accent1"],
                 bg=self.theme["bg"], font=("Orbitron", 10, "bold"),
                 pady=10).pack()
        tk.Frame(win, bg=self.theme["accent1"], height=1).pack(fill="x")

        rows = [
            ("Dossier base", str(BASE_DIR)),
            ("Version", "V1.45"),
            ("Thème actif", THEMES[self.settings.get("launcher_theme","overlord_cyber")]["name"]),
        ]
        for label, value in rows:
            f = tk.Frame(win, bg=self.theme["bg2"])
            f.pack(fill="x", padx=16, pady=4)
            tk.Label(f, text=label, fg=self.theme["text2"], bg=self.theme["bg2"],
                     font=("Segoe UI", 8), width=16, anchor="w").pack(side="left", padx=8, pady=6)
            tk.Label(f, text=value, fg=self.theme["text"], bg=self.theme["bg2"],
                     font=("Segoe UI", 8)).pack(side="left")

        tk.Button(win, text="Fermer", command=win.destroy,
                  bg=self.theme["accent1"], fg="#000",
                  relief="flat", font=("Segoe UI", 9, "bold"),
                  padx=20, pady=6, cursor="hand2").pack(pady=16)

    def run(self):
        self.root.mainloop()


if __name__ == "__main__":
    launcher = OverLordLauncher()
    launcher.run()

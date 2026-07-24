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
overlord_launcher.py — Ov3rLoRd Command Launcher V1.70
Fenêtre tkinter séparée avec boutons de commandes préconfigurés.
- Clic normal : copie la commande dans le presse-papier
- Mode CONFIG (cadenas) : clic sur bouton = sélectionner un .py de référence
- Menu déroulant par catégorie
- Thèmes HUD (dark/neon/red)
- Config sauvegardée dans workspace/launcher_config.json

Lancement : python overlord_launcher.py
"""

import json
import os
import subprocess
import sys
import tkinter as tk
from tkinter import filedialog, messagebox, ttk
from pathlib import Path

# ── Config ────────────────────────────────────────────────────────────
CONFIG_FILE = Path("workspace/launcher_config.json")
CONFIG_FILE.parent.mkdir(parents=True, exist_ok=True)

# Presets par défaut
DEFAULT_BUTTONS = [
    # (id, label, command, category, color_key)
    ("pipeline_full",    "▶ Pipeline Complet",
     'python maestro.py --media-type anime --universe "evangelion battle mecha girl"',
     "pipeline", "accent"),
    ("pipeline_lib",     "▶ + PromptLib",
     'python maestro.py --media-type anime --universe "evangelion" --use-prompt-library',
     "pipeline", "accent"),
    ("pipeline_batch",   "▶▶▶ Batch x3",
     'python maestro.py --media-type anime --universe "evangelion" --batch 3',
     "pipeline", "accent"),
    ("pipeline_sb",      "▶ From Storyboard",
     'python maestro.py --media-type anime --universe "evangelion" --from-block storyboard',
     "pipeline", "accent"),
    ("pipeline_debug",   "▶ No Engineer/Gate",
     'python maestro.py --media-type anime --universe "evangelion" --no-prompt-engineer --no-quality-gate',
     "pipeline", "warn"),
    ("sourcing_loop",    "⟳ Auto Sourcing",
     "python agents/auto_sourcing.py --loop 3600",
     "agents", "info"),
    ("sourcing_dry",     "⟳ Sourcing Dry",
     "python agents/auto_sourcing.py --dry-run",
     "agents", "info"),
    ("gpu_opt",          "⚡ GPU Optimizer",
     "python agents/gpu_optimizer.py",
     "agents", "info"),
    ("init_lib",         "📚 Init PromptLib",
     "python agents/prompt_library.py",
     "agents", "info"),
    ("quality_gate",     "🔍 Quality Gate",
     "python agents/quality_gate.py",
     "agents", "info"),
    ("narrative",        "🧠 Narrative Memory",
     "python agents/narrative_memory.py",
     "agents", "info"),
    ("registry",         "📦 Agent Registry",
     "python agents/agent_registry.py",
     "agents", "info"),
    ("config_mgr",       "⚙ Config Manager",
     "python agents/config_manager.py",
     "agents", "info"),
    ("tests_quick",      "✓ Tests Rapides",
     "python test_suite.py --quick",
     "tests", "ok"),
    ("tests_full",       "✓✓ Tests Complets",
     "python test_suite.py",
     "tests", "ok"),
    ("tests_pipeline",   "✓ Pipeline Test",
     "python test_pipeline.py --quick",
     "tests", "ok"),
    ("comfyui_start",    "🖼 Start ComfyUI",
     'start "" "D:\\\\Ov3rLoRd AI\\\\ComfyUI\\\\run_nvidia_gpu.bat"',
     "comfyui", "accent"),
    ("snapshot_all",     "💾 Snapshot Agents",
     "python -c \"from agents.agent_registry import get_registry; get_registry().snapshot_all(); print('OK')\"",
     "maintenance", "warn"),
    ("audit_quick",      "🔍 Audit Rapide",
     "python overlord_auditor.py --quick",
     "maintenance", "info"),
    ("audit_full",       "🔍 Audit Complet",
     "python overlord_auditor.py --verbose",
     "maintenance", "info"),
    ("audit_gui",        "🔍 Audit GUI",
     "python overlord_auditor.py --gui",
     "maintenance", "info"),
    ("del_checkpoints",  "🗑 Clear Checkpoints",
     r"del /Q workspace\checkpoints\*\*",
     "maintenance", "warn"),
]

CATEGORIES = ["pipeline", "agents", "tests", "comfyui", "maintenance"]
CAT_LABELS = {
    "pipeline":    "🎬 Pipeline",
    "agents":      "🤖 Agents",
    "tests":       "✅ Tests",
    "comfyui":     "🖼 ComfyUI",
    "maintenance": "🔧 Maintenance",
}

# ── Thèmes HUD ────────────────────────────────────────────────────────
try:
    from ov_design_system import (
        THEMES, get_theme, set_theme, on_theme_change,
        OvWindow, OvCard, OvMetric, OvButton,
        OvProgressBar, OvThemeSelector, OvPulseIndicator,
        OvScrollFrame,
    )
    DESIGN_OK = True
except ImportError:
    DESIGN_OK = False
    # Fallback : thème dark minimal si design system absent
    THEMES = {
        "dark":  {"bg":"#0a0a0f","panel":"#12121a","border":"#1e1e2e",
                  "text":"#c0c0d0","text_dim":"#606070","title_fg":"#e2e8f0",
                  "accent":"#7c3aed","accent_hover":"#9d5cf0",
                  "ok":"#10b981","ok_hover":"#34d399","warn":"#f59e0b",
                  "warn_hover":"#fbbf24","info":"#3b82f6","info_hover":"#60a5fa",
                  "danger":"#ef4444","copy_flash":"#10b981","btn_text":"#ffffff",
                  "font_ui":("Consolas",9),"font_title":("Consolas",12,"bold"),
                  "font_btn":("Consolas",9),"font_mono":("Consolas",8)},
    }
    def get_theme(n=None): return THEMES.get(n or "dark", THEMES["dark"])
    def set_theme(n): pass
    def on_theme_change(cb): pass
class OvLauncher:

    def __init__(self):
        self.root = tk.Tk()
        self.root.title("Ov3rLoRd Launcher V1.70")
        self.root.resizable(True, True)
        self.root.minsize(520, 400)
        # Barre titre draggable si design system disponible
        if DESIGN_OK:
            self._ov_window = OvWindow(
                self.root, "◈  OV3RLORD LAUNCHER  V1.70",
                width=620, height=600
            )
            on_theme_change(self._on_global_theme_change)
        else:
            self._ov_window = None

        self.config_mode = False
        self.current_theme = tk.StringVar(value="dark")
        self.current_cat   = tk.StringVar(value="pipeline")
        self.buttons_data  = []  # (id, label, command, category, color_key)
        self.btn_widgets   = {}  # id → Button widget
        self._copy_timers  = {}

        self._load_config()
        self._build_ui()
        self._apply_theme()
        self._refresh_buttons()

        # Centrer la fenêtre
        self.root.update_idletasks()
        w, h = 600, 580
        x = (self.root.winfo_screenwidth()  - w) // 2
        y = (self.root.winfo_screenheight() - h) // 2
        self.root.geometry(f"{w}x{h}+{x}+{y}")

    # ── Config persistence ─────────────────────────────────────────────

    def _load_config(self):
        if CONFIG_FILE.exists():
            try:
                data = json.loads(CONFIG_FILE.read_text(encoding="utf-8"))
                self.buttons_data = data.get("buttons", [])
                saved_theme = data.get("theme", "dark")
                self.current_theme.set(saved_theme)
                return
            except Exception:
                pass
        self.buttons_data = [list(b) for b in DEFAULT_BUTTONS]

    def _on_global_theme_change(self, theme_name: str):
        """Synchronisation thème depuis le design system global."""
        self.current_theme.set(theme_name)
        self._apply_theme()
        self._save_config()

    def _save_config(self):
        CONFIG_FILE.write_text(
            json.dumps({
                "buttons": self.buttons_data,
                "theme":   self.current_theme.get(),
            }, indent=2, ensure_ascii=False),
            encoding="utf-8"
        )

    def _get_theme(self) -> dict:
        return THEMES.get(self.current_theme.get(), THEMES["dark"])

    # ── UI ─────────────────────────────────────────────────────────────

    def _build_ui(self):
        t = self._get_theme()

        # ── Barre titre ────────────────────────────────────────────────
        self.title_bar = tk.Frame(self.root, height=36)
        self.title_bar.pack(fill="x", side="top")

        self.lbl_title = tk.Label(
            self.title_bar,
            text="◈  OV3RLORD LAUNCHER  V1.70",
            anchor="w", padx=10,
        )
        self.lbl_title.pack(side="left", fill="y")

        # Sélecteur thème
        self.lbl_theme = tk.Label(self.title_bar, text="THEME:", padx=6)
        self.lbl_theme.pack(side="right", padx=(0,4))

        for th in THEMES:
            b = tk.Button(
                self.title_bar, text=th.upper(), width=6,
                command=lambda t=th: self._set_theme(t), relief="flat", bd=0,
            )
            b.pack(side="right", padx=2, pady=4)
            setattr(self, f"_theme_btn_{th}", b)

        # Bouton config (cadenas)
        self.btn_config = tk.Button(
            self.title_bar, text="🔓 CONFIG", width=9,
            command=self._toggle_config, relief="flat", bd=0,
        )
        self.btn_config.pack(side="right", padx=8)

        # ── Sélecteur catégorie ────────────────────────────────────────
        self.cat_bar = tk.Frame(self.root, height=32)
        self.cat_bar.pack(fill="x", side="top")

        self.cat_btns = {}
        for cat in CATEGORIES:
            b = tk.Button(
                self.cat_bar,
                text=CAT_LABELS.get(cat, cat),
                command=lambda c=cat: self._select_cat(c),
                relief="flat", bd=0, padx=8, pady=4,
            )
            b.pack(side="left", padx=2, pady=2)
            self.cat_btns[cat] = b

        # ── Zone centrale (scrollable) ─────────────────────────────────
        self.main_frame = tk.Frame(self.root)
        self.main_frame.pack(fill="both", expand=True, padx=8, pady=4)

        self.canvas = tk.Canvas(self.main_frame, highlightthickness=0)
        self.scrollbar = tk.Scrollbar(self.main_frame, orient="vertical",
                                       command=self.canvas.yview)
        self.canvas.configure(yscrollcommand=self.scrollbar.set)
        self.scrollbar.pack(side="right", fill="y")
        self.canvas.pack(side="left", fill="both", expand=True)

        self.btn_frame = tk.Frame(self.canvas)
        self._canvas_window = self.canvas.create_window(
            (0, 0), window=self.btn_frame, anchor="nw"
        )
        self.btn_frame.bind("<Configure>", self._on_frame_configure)
        self.canvas.bind("<Configure>", self._on_canvas_configure)
        self.canvas.bind("<MouseWheel>", self._on_mousewheel)

        # ── Barre de statut ────────────────────────────────────────────
        self.status_bar = tk.Frame(self.root, height=24)
        self.status_bar.pack(fill="x", side="bottom")

        self.lbl_mode = tk.Label(self.status_bar, text="MODE : COPIE", padx=8, anchor="w")
        self.lbl_mode.pack(side="left")
        # Indicateur pulsé actif
        if DESIGN_OK:
            self._pulse = OvPulseIndicator(self.status_bar)
            self._pulse.pack(side="left", padx=4)
        else:
            self._pulse = None

        self.lbl_status = tk.Label(self.status_bar, text="Prêt.", padx=8, anchor="e")
        self.lbl_status.pack(side="right")

        # Commande affichée
        self.cmd_var = tk.StringVar(value="")
        self.lbl_cmd = tk.Label(
            self.status_bar, textvariable=self.cmd_var,
            anchor="w", padx=4,
        )
        self.lbl_cmd.pack(side="left", fill="x", expand=True)

    def _on_frame_configure(self, _=None):
        self.canvas.configure(scrollregion=self.canvas.bbox("all"))

    def _on_canvas_configure(self, event):
        self.canvas.itemconfig(self._canvas_window, width=event.width)

    def _on_mousewheel(self, event):
        self.canvas.yview_scroll(-1 * (event.delta // 120), "units")

    # ── Thème ──────────────────────────────────────────────────────────

    def _set_theme(self, theme_name: str):
        self.current_theme.set(theme_name)
        self._apply_theme()
        self._save_config()

    def _apply_theme(self):
        t = self._get_theme()
        bg, panel, text = t["bg"], t["panel"], t["text"]
        dim = t["text_dim"]

        self.root.configure(bg=bg)
        self.title_bar.configure(bg=panel)
        self.cat_bar.configure(bg=bg)
        self.main_frame.configure(bg=bg)
        self.canvas.configure(bg=bg)
        self.btn_frame.configure(bg=bg)
        self.status_bar.configure(bg=panel)

        self.lbl_title.configure(bg=panel, fg=t["title_fg"], font=t["font_title"])
        self.lbl_mode.configure(bg=panel, fg=t["text_dim"], font=t["font_ui"])
        self.lbl_status.configure(bg=panel, fg=t["text_dim"], font=t["font_ui"])
        self.lbl_cmd.configure(bg=panel, fg=dim, font=t["font_mono"])
        self.btn_config.configure(
            bg=t["warn"], fg="#000000", activebackground=t["warn_hover"],
            font=t["font_ui"]
        )
        self.lbl_theme.configure(bg=panel, fg=dim, font=t["font_ui"])

        for th_name, colors in THEMES.items():
            btn = getattr(self, f"_theme_btn_{th_name}", None)
            if btn:
                is_active = th_name == self.current_theme.get()
                btn.configure(
                    bg=colors["accent"] if is_active else panel,
                    fg="#ffffff",
                    activebackground=colors["accent_hover"],
                    font=t["font_ui"],
                )

        # Catégories
        active_cat = self.current_cat.get()
        for cat, btn in self.cat_btns.items():
            is_active = cat == active_cat
            btn.configure(
                bg=t["accent"] if is_active else t["panel"],
                fg=t["btn_text"] if is_active else t["text"],
                activebackground=t["accent_hover"],
                font=t["font_ui"],
            )

        # Reboucler sur les boutons existants
        self._refresh_buttons()

    # ── Catégorie ──────────────────────────────────────────────────────

    def _select_cat(self, cat: str):
        self.current_cat.set(cat)
        self._apply_theme()

    # ── Boutons ────────────────────────────────────────────────────────

    def _refresh_buttons(self):
        t = self._get_theme()
        cat = self.current_cat.get()

        # Vider le frame
        for w in self.btn_frame.winfo_children():
            w.destroy()
        self.btn_widgets = {}

        filtered = [b for b in self.buttons_data if b[3] == cat]

        for btn_data in filtered:
            bid, label, command, bcat, color_key = btn_data
            color    = t.get(color_key, t["accent"])
            color_hv = t.get(f"{color_key}_hover", color)

            row = tk.Frame(self.btn_frame, bg=t["bg"])
            row.pack(fill="x", padx=4, pady=2)

            # Bouton principal
            btn = tk.Button(
                row,
                text=label,
                anchor="w", padx=10,
                relief="flat", bd=0,
                font=t["font_btn"],
                cursor="hand2",
            )
            btn.pack(side="left", fill="x", expand=True, ipady=6)

            # Preview commande
            lbl_preview = tk.Label(
                row,
                text=command[:55] + ("…" if len(command) > 55 else ""),
                anchor="w", padx=6,
                font=t["font_mono"],
            )
            lbl_preview.pack(side="left", fill="x", expand=True)

            # Couleurs
            btn.configure(bg=color, fg=t["btn_text"],
                           activebackground=color_hv,
                           activeforeground=t["btn_text"])
            lbl_preview.configure(bg=t["bg"], fg=t["text_dim"])

            # Hover
            btn.bind("<Enter>",  lambda e, b=btn, c=color_hv: b.configure(bg=c))
            btn.bind("<Leave>",  lambda e, b=btn, c=color: b.configure(bg=c))

            # Binding selon mode
            btn.bind("<Button-1>", lambda e, bi=bid, cmd=command, b=btn:
                      self._on_btn_click(bi, cmd, b))

            self.btn_widgets[bid] = (btn, lbl_preview, color, color_hv, command)

        # Bouton + (ajouter)
        if self.config_mode:
            add_btn = tk.Button(
                self.btn_frame,
                text="＋  Ajouter un bouton",
                relief="flat", bd=0,
                font=t["font_btn"],
                command=lambda: self._add_button(cat),
            )
            add_btn.configure(bg=t["border"], fg=t["text_dim"],
                               activebackground=t["accent"])
            add_btn.pack(fill="x", padx=4, pady=4, ipady=8)

        self._on_frame_configure()

    def _on_btn_click(self, btn_id: str, command: str, widget):
        if self.config_mode:
            self._configure_button(btn_id)
        else:
            self._copy_command(command, widget)

    def _copy_command(self, command: str, widget):
        """Copie la commande dans le presse-papier et flash le bouton."""
        t = self._get_theme()
        try:
            self.root.clipboard_clear()
            self.root.clipboard_append(command)
            self.root.update()
        except Exception:
            pass

        self.cmd_var.set(f"✓ Copié : {command[:60]}{'…' if len(command)>60 else ''}")
        self.lbl_status.configure(text="Copié !", fg=t["copy_flash"])

        # Flash vert
        orig_bg = widget.cget("bg")
        widget.configure(bg=t["copy_flash"], fg="#000000")

        def restore():
            try:
                widget.configure(bg=orig_bg, fg=t["btn_text"])
                self.lbl_status.configure(text="Prêt.", fg=t["text_dim"])
            except Exception:
                pass

        self.root.after(600, restore)

    # ── Mode Configuration ─────────────────────────────────────────────

    def _toggle_config(self):
        t = self._get_theme()
        self.config_mode = not self.config_mode
        if self.config_mode:
            self.btn_config.configure(text="🔒 CONFIG", bg=t["danger"])
            self.lbl_mode.configure(text="MODE : CONFIGURATION", fg=t["danger"])
        else:
            self.btn_config.configure(text="🔓 CONFIG", bg=t["warn"])
            self.lbl_mode.configure(text="MODE : COPIE", fg=t["text_dim"])
            self._save_config()
        self._refresh_buttons()

    def _configure_button(self, btn_id: str):
        """En mode config : clic ouvre le dialog de configuration du bouton."""
        t = self._get_theme()

        # Trouver le bouton dans la liste
        btn_data = next((b for b in self.buttons_data if b[0] == btn_id), None)
        if not btn_data:
            return

        # Fenêtre de config
        win = tk.Toplevel(self.root)
        win.title(f"Configurer — {btn_data[1]}")
        win.configure(bg=t["bg"])
        win.resizable(False, False)
        win.grab_set()

        def lbl(text, row):
            tk.Label(win, text=text, bg=t["bg"], fg=t["text"],
                     font=t["font_ui"], anchor="w").grid(
                row=row, column=0, sticky="w", padx=12, pady=4)

        lbl("Libellé :", 0)
        e_label = tk.Entry(win, font=t["font_btn"], width=30)
        e_label.insert(0, btn_data[1])
        e_label.grid(row=0, column=1, padx=12, pady=4)
        e_label.configure(bg=t["panel"], fg=t["text"],
                           insertbackground=t["text"], relief="flat")

        lbl("Commande :", 1)
        e_cmd = tk.Entry(win, font=t["font_mono"], width=50)
        e_cmd.insert(0, btn_data[2])
        e_cmd.grid(row=1, column=1, padx=12, pady=4)
        e_cmd.configure(bg=t["panel"], fg=t["text"],
                         insertbackground=t["text"], relief="flat")

        def browse_py():
            path = filedialog.askopenfilename(
                title="Sélectionner un fichier Python",
                filetypes=[("Python files", "*.py"), ("All files", "*.*")],
                initialdir=str(Path.cwd()),
            )
            if path:
                rel = os.path.relpath(path, Path.cwd())
                name = Path(path).stem
                e_cmd.delete(0, "end")
                e_cmd.insert(0, f"python {rel}")
                if not e_label.get() or e_label.get() == btn_data[1]:
                    e_label.delete(0, "end")
                    e_label.insert(0, f"▶ {name}")

        lbl("Couleur :", 2)
        color_var = tk.StringVar(value=btn_data[4])
        color_frame = tk.Frame(win, bg=t["bg"])
        color_frame.grid(row=2, column=1, sticky="w", padx=12, pady=4)
        for ck in ["accent", "ok", "warn", "info", "danger"]:
            rb = tk.Radiobutton(
                color_frame, text=ck, variable=color_var, value=ck,
                bg=t["bg"], fg=t.get(ck, t["text"]),
                selectcolor=t["panel"], activebackground=t["bg"],
                font=t["font_ui"],
            )
            rb.pack(side="left", padx=4)

        # Boutons action
        btn_row = tk.Frame(win, bg=t["bg"])
        btn_row.grid(row=4, column=0, columnspan=2, pady=12)

        def browse():
            browse_py()

        def save_btn():
            idx = next((i for i, b in enumerate(self.buttons_data) if b[0] == btn_id), None)
            if idx is not None:
                self.buttons_data[idx] = [
                    btn_id, e_label.get(), e_cmd.get(),
                    btn_data[3], color_var.get()
                ]
            self._save_config()
            self._refresh_buttons()
            win.destroy()

        def delete_btn():
            if messagebox.askyesno("Supprimer", f"Supprimer '{btn_data[1]}' ?"):
                self.buttons_data = [b for b in self.buttons_data if b[0] != btn_id]
                self._save_config()
                self._refresh_buttons()
                win.destroy()

        for text, cmd, color in [
            ("📁 Parcourir .py", browse, t["info"]),
            ("💾 Sauvegarder",   save_btn, t["ok"]),
            ("🗑 Supprimer",     delete_btn, t["danger"]),
            ("✕ Annuler",       win.destroy, t["text_dim"]),
        ]:
            b = tk.Button(btn_row, text=text, command=cmd, relief="flat", bd=0,
                          bg=color, fg="#ffffff", padx=8,
                          font=t["font_btn"], cursor="hand2")
            b.pack(side="left", padx=4, ipady=4)

        win.geometry(f"600x230+{self.root.winfo_x()+60}+{self.root.winfo_y()+60}")

    def _add_button(self, cat: str):
        """Ajouter un nouveau bouton dans la catégorie courante."""
        import time
        new_id = f"custom_{int(time.time())}"
        self.buttons_data.append([new_id, "▶ Nouveau", "python ", cat, "accent"])
        self._refresh_buttons()
        self._configure_button(new_id)

    def run(self):
        self.root.mainloop()


if __name__ == "__main__":
    app = OvLauncher()
    app.run()

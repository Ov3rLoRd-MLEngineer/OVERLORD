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
ov_design_system.py — Système de Design Ov3rLoRd V1.70
Source unique de vérité pour tous les HUD tkinter.
Importer ce module depuis overlord_launcher.py et overlord_auditor.py.

Usage :
  from ov_design_system import OvTheme, OvWindow, THEMES, apply_theme
"""

import tkinter as tk
from tkinter import ttk
import threading

# ── Thèmes ────────────────────────────────────────────────────────────

THEMES = {
    "dark": {
        # Fonds
        "bg":           "#0a0a0f",
        "panel":        "#12121a",
        "card":         "#15151f",
        "border":       "#1e1e2e",
        "border_active":"#7c3aed",
        # Textes
        "text":         "#c0c0d0",
        "text_dim":     "#505060",
        "text_bright":  "#e8e8f0",
        "title_fg":     "#e2e8f0",
        # Accents
        "accent":       "#7c3aed",
        "accent_hover": "#9d5cf0",
        "accent_dim":   "#3d1d77",
        # États
        "ok":           "#10b981",
        "ok_hover":     "#34d399",
        "warn":         "#f59e0b",
        "warn_hover":   "#fbbf24",
        "err":          "#ef4444",
        "err_hover":    "#f87171",
        "info":         "#3b82f6",
        "info_hover":   "#60a5fa",
        # Spéciaux
        "copy_flash":   "#10b981",
        "pulse_active": "#7c3aed",
        "btn_text":     "#ffffff",
        "scrollbar":    "#1e1e2e",
        # Fonts
        "font_ui":      ("Consolas", 9),
        "font_title":   ("Consolas", 12, "bold"),
        "font_btn":     ("Consolas", 9),
        "font_mono":    ("Consolas", 8),
        "font_label":   ("Consolas", 9),
    },
    "neon": {
        "bg":           "#030310",
        "panel":        "#08081a",
        "card":         "#0a0a1e",
        "border":       "#001133",
        "border_active":"#00ffff",
        "text":         "#88ddff",
        "text_dim":     "#224466",
        "text_bright":  "#ccffff",
        "title_fg":     "#00ffff",
        "accent":       "#cc00ff",
        "accent_hover": "#ee44ff",
        "accent_dim":   "#440055",
        "ok":           "#00ff88",
        "ok_hover":     "#44ffaa",
        "warn":         "#ffcc00",
        "warn_hover":   "#ffdd44",
        "err":          "#ff0055",
        "err_hover":    "#ff4477",
        "info":         "#00ccff",
        "info_hover":   "#44ddff",
        "copy_flash":   "#00ff88",
        "pulse_active": "#cc00ff",
        "btn_text":     "#000010",
        "scrollbar":    "#001133",
        "font_ui":      ("Consolas", 9),
        "font_title":   ("Consolas", 12, "bold"),
        "font_btn":     ("Consolas", 9),
        "font_mono":    ("Consolas", 8),
        "font_label":   ("Consolas", 9),
    },
    "red": {
        "bg":           "#0d0305",
        "panel":        "#180508",
        "card":         "#1a060a",
        "border":       "#3a1010",
        "border_active":"#ff2200",
        "text":         "#d0a0a0",
        "text_dim":     "#604040",
        "text_bright":  "#ffcccc",
        "title_fg":     "#ff4422",
        "accent":       "#cc2200",
        "accent_hover": "#ee4422",
        "accent_dim":   "#550a00",
        "ok":           "#cc8800",
        "ok_hover":     "#ee9922",
        "warn":         "#ff6600",
        "warn_hover":   "#ff8833",
        "err":          "#ff0000",
        "err_hover":    "#ff3333",
        "info":         "#aa3300",
        "info_hover":   "#cc5522",
        "copy_flash":   "#ff6600",
        "pulse_active": "#cc2200",
        "btn_text":     "#ffffff",
        "scrollbar":    "#3a1010",
        "font_ui":      ("Consolas", 9),
        "font_title":   ("Consolas", 12, "bold"),
        "font_btn":     ("Consolas", 9),
        "font_mono":    ("Consolas", 8),
        "font_label":   ("Consolas", 9),
    },
}

_current_theme = "dark"
_theme_listeners: list = []


def get_theme(name: str = None) -> dict:
    return THEMES.get(name or _current_theme, THEMES["dark"])


def set_theme(name: str):
    global _current_theme
    _current_theme = name
    for cb in _theme_listeners:
        try:
            cb(name)
        except Exception:
            pass


def on_theme_change(callback):
    """Enregistrer un callback appelé quand le thème change."""
    _theme_listeners.append(callback)


# ── Fenêtre draggable sans barre titre OS ────────────────────────────

class OvWindow:
    """
    Fenêtre Ov3rLoRd avec barre titre personnalisée.
    Draggable, redimensionnable, thème unifié.
    Clic sur la barre = glisser. Double-clic = maximiser/restaurer.
    """

    def __init__(self, root: tk.Tk | tk.Toplevel, title: str,
                 width: int = 620, height: int = 600,
                 resizable: bool = True, theme: str = None):
        self.root      = root
        self.title_str = title
        self.theme_name = theme or _current_theme
        self._maximized = False
        self._normal_geo = None
        self._drag_x = 0
        self._drag_y = 0

        # Fenêtre sans décoration OS
        root.overrideredirect(True)
        root.resizable(False, False)
        root.minsize(400, 300)

        # Centrer
        sw = root.winfo_screenwidth()
        sh = root.winfo_screenheight()
        x  = (sw - width) // 2
        y  = (sh - height) // 2
        root.geometry(f"{width}x{height}+{x}+{y}")

        self._build_chrome()
        self._build_resize_grip()
        self._apply_theme()

        # S'enregistrer pour les changements de thème
        on_theme_change(lambda name: self._apply_theme(name))

    def _build_chrome(self):
        t = get_theme(self.theme_name)

        # ── Barre titre custom ────────────────────────────────────────
        self.title_bar = tk.Frame(self.root, height=32, cursor="fleur")
        self.title_bar.pack(fill="x", side="top")
        self.title_bar.pack_propagate(False)

        # Icône + Titre
        self.lbl_icon  = tk.Label(self.title_bar, text="◈", padx=6)
        self.lbl_icon.pack(side="left")

        self.lbl_title = tk.Label(
            self.title_bar, text=self.title_str, anchor="w", padx=4
        )
        self.lbl_title.pack(side="left", fill="x", expand=True)

        # Boutons fenêtre (─ □ ✕)
        self.btn_frame = tk.Frame(self.title_bar)
        self.btn_frame.pack(side="right", padx=2)

        self.btn_min  = tk.Label(self.btn_frame, text=" ─ ", cursor="hand2", padx=4)
        self.btn_min.pack(side="left")
        self.btn_min.bind("<Button-1>", self._minimize)

        self.btn_max  = tk.Label(self.btn_frame, text=" □ ", cursor="hand2", padx=4)
        self.btn_max.pack(side="left")
        self.btn_max.bind("<Button-1>", self._toggle_maximize)

        self.btn_close = tk.Label(self.btn_frame, text=" ✕ ", cursor="hand2", padx=4)
        self.btn_close.pack(side="left")
        self.btn_close.bind("<Button-1>", lambda e: self.root.destroy())

        # Drag bindings
        self.title_bar.bind("<ButtonPress-1>",   self._drag_start)
        self.title_bar.bind("<B1-Motion>",        self._drag_motion)
        self.title_bar.bind("<Double-Button-1>",  self._toggle_maximize)
        self.lbl_title.bind("<ButtonPress-1>",   self._drag_start)
        self.lbl_title.bind("<B1-Motion>",        self._drag_motion)
        self.lbl_title.bind("<Double-Button-1>",  self._toggle_maximize)
        self.lbl_icon.bind("<ButtonPress-1>",    self._drag_start)
        self.lbl_icon.bind("<B1-Motion>",         self._drag_motion)

        # Hover effects
        for btn, hover_color, normal_color in [
            (self.btn_min,   "#444460", "panel"),
            (self.btn_max,   "#444460", "panel"),
            (self.btn_close, "#cc2222", "panel"),
        ]:
            btn.bind("<Enter>",  lambda e, b=btn, c=hover_color: b.configure(bg=c))
            btn.bind("<Leave>",  lambda e, b=btn: b.configure(
                bg=get_theme(self.theme_name)["panel"]))

        # Séparateur
        self.separator = tk.Frame(self.root, height=1)
        self.separator.pack(fill="x", side="top")

    def _build_resize_grip(self):
        """Poignée de redimensionnement coin bas-droit."""
        self.grip = tk.Label(self.root, text="⠿", cursor="size_nw_se",
                              font=("Consolas", 8))
        self.grip.place(relx=1.0, rely=1.0, anchor="se", x=-2, y=-2)
        self.grip.bind("<ButtonPress-1>",  self._resize_start)
        self.grip.bind("<B1-Motion>",       self._resize_motion)
        self._resize_start_x = 0
        self._resize_start_y = 0
        self._resize_start_w = 0
        self._resize_start_h = 0

    def _drag_start(self, event):
        self._drag_x = event.x_root - self.root.winfo_x()
        self._drag_y = event.y_root - self.root.winfo_y()

    def _drag_motion(self, event):
        if not self._maximized:
            x = event.x_root - self._drag_x
            y = event.y_root - self._drag_y
            self.root.geometry(f"+{x}+{y}")

    def _resize_start(self, event):
        self._resize_start_x = event.x_root
        self._resize_start_y = event.y_root
        self._resize_start_w = self.root.winfo_width()
        self._resize_start_h = self.root.winfo_height()

    def _resize_motion(self, event):
        dw = event.x_root - self._resize_start_x
        dh = event.y_root - self._resize_start_y
        new_w = max(400, self._resize_start_w + dw)
        new_h = max(300, self._resize_start_h + dh)
        self.root.geometry(f"{new_w}x{new_h}")

    def _minimize(self, event=None):
        self.root.overrideredirect(False)
        self.root.iconify()
        self.root.bind("<Map>", self._on_restore)

    def _on_restore(self, event=None):
        self.root.overrideredirect(True)
        self.root.unbind("<Map>")

    def _toggle_maximize(self, event=None):
        if self._maximized:
            self.root.geometry(self._normal_geo)
            self.btn_max.configure(text=" □ ")
            self._maximized = False
        else:
            self._normal_geo = self.root.geometry()
            sw = self.root.winfo_screenwidth()
            sh = self.root.winfo_screenheight()
            self.root.geometry(f"{sw}x{sh}+0+0")
            self.btn_max.configure(text=" ❐ ")
            self._maximized = True

    def _apply_theme(self, theme_name: str = None):
        self.theme_name = theme_name or self.theme_name
        t = get_theme(self.theme_name)

        self.root.configure(bg=t["bg"])
        self.title_bar.configure(bg=t["panel"])
        self.separator.configure(bg=t["border_active"])
        self.lbl_icon.configure(bg=t["panel"],  fg=t["accent"],
                                  font=t["font_title"])
        self.lbl_title.configure(bg=t["panel"], fg=t["title_fg"],
                                   font=t["font_title"])
        self.btn_frame.configure(bg=t["panel"])
        self.btn_min.configure(bg=t["panel"],   fg=t["text_dim"],
                                 font=t["font_ui"])
        self.btn_max.configure(bg=t["panel"],   fg=t["text_dim"],
                                 font=t["font_ui"])
        self.btn_close.configure(bg=t["panel"], fg=t["err"],
                                   font=t["font_ui"])
        self.grip.configure(bg=t["bg"], fg=t["text_dim"])


# ── Widgets réutilisables ─────────────────────────────────────────────

class OvCard(tk.Frame):
    """Card avec titre et bordure, thème synchronisé."""
    def __init__(self, parent, title: str = "", theme: str = None, **kw):
        t = get_theme(theme)
        super().__init__(parent, bg=t["card"],
                         highlightbackground=t["border"],
                         highlightthickness=1, **kw)
        self._theme = theme
        if title:
            tk.Label(self, text=title.upper(), bg=t["card"],
                     fg=t["accent"], font=t["font_label"],
                     anchor="w", padx=8, pady=4).pack(fill="x")
            tk.Frame(self, height=1, bg=t["border"]).pack(fill="x")

    def apply_theme(self, theme: str):
        t = get_theme(theme)
        self._theme = theme
        self.configure(bg=t["card"], highlightbackground=t["border"])


class OvMetric(tk.Frame):
    """Ligne clé/valeur dans une card."""
    def __init__(self, parent, key: str, value: str = "—",
                 value_color: str = None, theme: str = None, **kw):
        t = get_theme(theme)
        super().__init__(parent, bg=t["card"], **kw)
        self._theme = theme

        self.lbl_key = tk.Label(self, text=key, bg=t["card"],
                                 fg=t["text_dim"], font=t["font_ui"],
                                 anchor="w", padx=8)
        self.lbl_key.pack(side="left")

        col = value_color or t["text"]
        self.lbl_val = tk.Label(self, text=value, bg=t["card"],
                                 fg=col, font=t["font_ui"],
                                 anchor="e", padx=8)
        self.lbl_val.pack(side="right")

    def set(self, value: str, color: str = None):
        t = get_theme(self._theme)
        self.lbl_val.configure(text=value)
        if color:
            self.lbl_val.configure(fg=t.get(color, color))

    def apply_theme(self, theme: str):
        t = get_theme(theme)
        self._theme = theme
        self.configure(bg=t["card"])
        self.lbl_key.configure(bg=t["card"], fg=t["text_dim"])
        self.lbl_val.configure(bg=t["card"])


class OvButton(tk.Button):
    """Bouton Ov3rLoRd avec hover et flash."""
    def __init__(self, parent, text: str, color_key: str = "accent",
                 theme: str = None, on_click=None, **kw):
        t = get_theme(theme)
        self._theme     = theme
        self._color_key = color_key
        self._root_ref  = parent

        bg    = t.get(color_key, t["accent"])
        bghv  = t.get(f"{color_key}_hover", bg)

        super().__init__(
            parent, text=text,
            bg=bg, fg=t["btn_text"],
            activebackground=bghv,
            activeforeground=t["btn_text"],
            font=t["font_btn"],
            relief="flat", bd=0,
            cursor="hand2",
            padx=8, pady=5,
            **kw
        )
        if on_click:
            self.configure(command=on_click)

        self.bind("<Enter>", lambda e: self.configure(bg=bghv))
        self.bind("<Leave>", lambda e: self.configure(bg=bg))

    def flash(self, color_key: str = "copy_flash", duration_ms: int = 500):
        t    = get_theme(self._theme)
        orig = t.get(self._color_key, t["accent"])
        flash_c = t.get(color_key, t["ok"])
        self.configure(bg=flash_c, fg="#000000")
        self.after(duration_ms, lambda: self.configure(
            bg=orig, fg=get_theme(self._theme)["btn_text"]
        ))

    def apply_theme(self, theme: str):
        t = get_theme(theme)
        self._theme = theme
        bg   = t.get(self._color_key, t["accent"])
        bghv = t.get(f"{self._color_key}_hover", bg)
        self.configure(bg=bg, fg=t["btn_text"],
                       activebackground=bghv, font=t["font_btn"])


class OvProgressBar(tk.Frame):
    """Barre de progression thémée."""
    def __init__(self, parent, height: int = 5,
                 color_key: str = "accent", theme: str = None, **kw):
        t = get_theme(theme)
        super().__init__(parent, bg=t["border"], height=height, **kw)
        self._theme = theme
        self._ck    = color_key
        self._bar   = tk.Frame(self, bg=t.get(color_key, t["accent"]), height=height)
        self._bar.place(x=0, y=0, relheight=1.0, relwidth=0.0)

    def set(self, pct: float, color_key: str = None):
        t  = get_theme(self._theme)
        ck = color_key or self._ck
        self._bar.configure(bg=t.get(ck, t["accent"]))
        self._bar.place(relwidth=max(0.0, min(1.0, pct / 100.0)))

    def apply_theme(self, theme: str):
        t = get_theme(theme)
        self._theme = theme
        self.configure(bg=t["border"])
        self._bar.configure(bg=t.get(self._ck, t["accent"]))


class OvThemeSelector(tk.Frame):
    """Sélecteur de thème unifié — à mettre dans toutes les fenêtres."""
    def __init__(self, parent, current_theme: str = "dark",
                 on_change=None, **kw):
        t = get_theme(current_theme)
        super().__init__(parent, bg=t["panel"], **kw)
        self._on_change = on_change

        tk.Label(self, text="THEME:", bg=t["panel"],
                 fg=t["text_dim"], font=t["font_ui"],
                 padx=4).pack(side="left")

        self._btns = {}
        for theme_name in THEMES:
            th = THEMES[theme_name]
            btn = tk.Label(
                self, text=theme_name.upper(),
                bg=th["accent"] if theme_name == current_theme else t["panel"],
                fg="#ffffff", padx=6, pady=2,
                font=t["font_ui"], cursor="hand2",
                relief="flat",
            )
            btn.pack(side="left", padx=2, pady=3)
            btn.bind("<Button-1>", lambda e, n=theme_name: self._select(n))
            self._btns[theme_name] = btn

    def _select(self, name: str):
        set_theme(name)
        self._refresh()
        if self._on_change:
            self._on_change(name)

    def _refresh(self):
        t = get_theme()
        self.configure(bg=t["panel"])
        for name, btn in self._btns.items():
            is_active = (name == _current_theme)
            th = THEMES[name]
            btn.configure(
                bg=th["accent"] if is_active else t["panel"],
                fg="#ffffff",
                font=t["font_ui"],
            )


class OvPulseIndicator(tk.Label):
    """Indicateur pulsé (point vert clignotant = actif)."""
    def __init__(self, parent, theme: str = None, **kw):
        t = get_theme(theme)
        super().__init__(parent, text="●", bg=t["panel"],
                         fg=t["text_dim"], font=("Consolas", 10), **kw)
        self._theme   = theme
        self._active  = False
        self._pulse   = False
        self._after_id = None

    def set_active(self, active: bool):
        self._active = active
        if active:
            self._start_pulse()
        else:
            self._stop_pulse()
            t = get_theme(self._theme)
            self.configure(fg=t["text_dim"])

    def _start_pulse(self):
        t = get_theme(self._theme)
        self._pulse = not self._pulse
        color = t["ok"] if self._pulse else t["accent"]
        self.configure(fg=color)
        self._after_id = self.after(600, self._start_pulse)

    def _stop_pulse(self):
        if self._after_id:
            self.after_cancel(self._after_id)
            self._after_id = None
        self._pulse = False

    def apply_theme(self, theme: str):
        t = get_theme(theme)
        self._theme = theme
        self.configure(bg=t["panel"])
        if not self._active:
            self.configure(fg=t["text_dim"])


# ── Scrollable frame ──────────────────────────────────────────────────

class OvScrollFrame(tk.Frame):
    """Frame avec scrollbar verticale, thémée."""
    def __init__(self, parent, theme: str = None, **kw):
        t = get_theme(theme)
        super().__init__(parent, bg=t["bg"], **kw)
        self._theme = theme

        self.canvas = tk.Canvas(self, bg=t["bg"],
                                 highlightthickness=0)
        self.scrollbar = tk.Scrollbar(self, orient="vertical",
                                       command=self.canvas.yview)
        self.canvas.configure(yscrollcommand=self.scrollbar.set)

        self.scrollbar.pack(side="right", fill="y")
        self.canvas.pack(side="left", fill="both", expand=True)

        self.inner = tk.Frame(self.canvas, bg=t["bg"])
        self._win  = self.canvas.create_window(
            (0, 0), window=self.inner, anchor="nw"
        )

        self.inner.bind("<Configure>",
                         lambda e: self.canvas.configure(
                             scrollregion=self.canvas.bbox("all")))
        self.canvas.bind("<Configure>",
                          lambda e: self.canvas.itemconfig(
                              self._win, width=e.width))
        self.canvas.bind("<MouseWheel>",
                          lambda e: self.canvas.yview_scroll(
                              -1 * (e.delta // 120), "units"))

    def apply_theme(self, theme: str):
        t = get_theme(theme)
        self._theme = theme
        self.configure(bg=t["bg"])
        self.canvas.configure(bg=t["bg"])
        self.inner.configure(bg=t["bg"])


if __name__ == "__main__":
    # Démo du design system
    root = tk.Tk()
    win  = OvWindow(root, "◈ OV3RLORD DESIGN SYSTEM V1.70",
                    width=500, height=400)

    t = get_theme()
    main = tk.Frame(root, bg=t["bg"])
    main.pack(fill="both", expand=True, padx=8, pady=8)

    # Sélecteur de thème
    selector = OvThemeSelector(
        main, on_change=lambda n: win._apply_theme(n)
    )
    selector.pack(fill="x", pady=(0, 8))

    # Cards de démo
    card1 = OvCard(main, "PIPELINE")
    card1.pack(fill="x", pady=3)
    OvMetric(card1, "État",      "EN COURS", "ok").pack(fill="x")
    OvMetric(card1, "Images OK", "8",        "ok").pack(fill="x")
    bar = OvProgressBar(card1, color_key="ok")
    bar.pack(fill="x", padx=8, pady=4)
    bar.set(75, "ok")

    card2 = OvCard(main, "GPU")
    card2.pack(fill="x", pady=3)
    OvMetric(card2, "RTX 5080", "78°C", "warn").pack(fill="x")
    OvMetric(card2, "VRAM",     "7.2/16GB").pack(fill="x")
    bar2 = OvProgressBar(card2, color_key="accent")
    bar2.pack(fill="x", padx=8, pady=4)
    bar2.set(45)

    # Boutons
    btn_frame = tk.Frame(main, bg=t["bg"])
    btn_frame.pack(fill="x", pady=8)
    b1 = OvButton(btn_frame, "▶ Lancer", "ok",
                   on_click=lambda: b1.flash())
    b1.pack(side="left", padx=4)
    b2 = OvButton(btn_frame, "■ Stop", "err")
    b2.pack(side="left", padx=4)
    b3 = OvButton(btn_frame, "⟳ Refresh", "info")
    b3.pack(side="left", padx=4)

    # Indicateur pulsé
    pulse = OvPulseIndicator(main)
    pulse.pack(pady=4)
    pulse.set_active(True)

    root.mainloop()

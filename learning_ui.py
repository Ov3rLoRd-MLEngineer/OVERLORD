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
learning_ui.py — Interface Graphique Agent Auto-Apprenant
Dashboard de l'IA Maestro qui apprend à maîtriser le pipeline.

Fonctionnalités :
  - Console de dialogue avec l'agent (chat temps réel)
  - Dashboard de progression (courbes de score, stats)
  - Contrôle de la boucle d'apprentissage (Start/Stop/Config)
  - Visualisation des connaissances acquises
  - Historique des épisodes avec leçons
  - Indicateur d'état (Idle/Running/Reflecting/Evolving)
"""

import sys
import json
import threading
import queue
import time
import tkinter as tk
from tkinter import ttk, messagebox
from pathlib import Path
from datetime import datetime

# Importer l'agent
try:
    sys.path.insert(0, str(Path(__file__).parent / "agents"))
    from learning_agent import LearningAgent, LearningState, MEMORY_DIR
    AGENT_OK = True
except Exception as e:
    AGENT_OK = False
    print(f"[WARN] learning_agent.py : {e}")

SETTINGS_FILE = Path("learning_settings.json")
APP_NAME      = "Ov3rLoRd — Agent Apprenant"

PAL = {
    "dark": dict(
        bg="#080810",       surf="#10101A",      surf2="#18182A",
        surf3="#202030",    border="#303050",
        accent="#7C3AED",   accent2="#A855F7",   accentg="#5B21B6",
        text="#E0E0F8",     textd="#7070A8",      textm="#404060",
        ok="#10B981",       warn="#F59E0B",        err="#EF4444",
        logbg="#05050D",    logtxt="#A0FFA8",
        chat_user="#1A1A40",chat_user_fg="#A0C8FF",
        chat_ai="#102010",  chat_ai_fg="#A0FFA8",
        btn="#7C3AED",      btn_fg="#FFFFFF",
        bar_bg="#1A1A2E",   bar_fill="#7C3AED",
    ),
    "light": dict(
        bg="#F0EFF8",       surf="#FFFFFF",      surf2="#F5F4FF",
        surf3="#EEEEFF",    border="#D0CCF0",
        accent="#6D28D9",   accent2="#7C3AED",   accentg="#A78BFA",
        text="#1A1A30",     textd="#5A5A80",      textm="#9090B0",
        ok="#059669",       warn="#D97706",        err="#DC2626",
        logbg="#0F0F20",    logtxt="#A0FFA8",
        chat_user="#E8E8FF",chat_user_fg="#3030A0",
        chat_ai="#E8FFE8",  chat_ai_fg="#206020",
        btn="#6D28D9",      btn_fg="#FFFFFF",
        bar_bg="#E0E0F0",   bar_fill="#6D28D9",
    )
}

def load_settings():
    try:
        if SETTINGS_FILE.exists():
            return json.loads(SETTINGS_FILE.read_text(encoding="utf-8"))
    except Exception: pass
    return {"theme": "dark", "n_episodes": 20, "interval_s": 60,
            "auto_start": False, "media_type": "anime"}

def save_settings(cfg):
    SETTINGS_FILE.write_text(json.dumps(cfg, indent=2), encoding="utf-8")


class MiniProgressBar(tk.Canvas):
    """Barre de progression minimaliste pour le dashboard."""
    def __init__(self, parent, P, height=12, **kw):
        super().__init__(parent, height=height, highlightthickness=0, bd=0, **kw)
        self.P = P; self._v = 0.0
        self.bind("<Configure>", lambda e: self._draw())

    def set(self, v):
        self._v = max(0.0, min(1.0, v)); self._draw()

    def _draw(self):
        P = self.P; w = self.winfo_width() or 200; h = self.h if hasattr(self,"h") else 12
        self.delete("all")
        self.create_rectangle(0, 0, w, h, fill=P["bar_bg"], outline="")
        fw = int(w * self._v)
        if fw > 0:
            self.create_rectangle(0, 0, fw, h, fill=P["bar_fill"], outline="")
        pct = int(self._v * 100)
        self.create_text(w//2, h//2, text=f"{pct}%",
                         fill=P["text"], font=("Segoe UI", 7))


class LearningUI:
    def __init__(self):
        self.cfg     = load_settings()
        self.theme   = self.cfg.get("theme", "dark")
        self.P       = PAL[self.theme]
        self.q       = queue.Queue()
        self._agent  = None
        self._thread = None
        self._running = False
        self._chat_history = []
        self._score_history = []   # pour le mini-graphe

        self._build_window()
        self._build_ui()
        self._apply_theme()
        self._init_agent()
        self._poll()

    def _build_window(self):
        self.root = tk.Tk()
        self.root.title(APP_NAME)
        self.root.geometry("1100x750")
        self.root.minsize(800, 500)
        self.root.configure(bg=self.P["bg"])
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)
        sw = self.root.winfo_screenwidth(); sh = self.root.winfo_screenheight()
        self.root.geometry(f"1100x750+{(sw-1100)//2}+{(sh-750)//2}")

    def _build_ui(self):
        P = self.P

        # ── Titlebar ──
        self.titlebar = tk.Frame(self.root, height=48)
        self.titlebar.pack(fill="x")
        self.titlebar.pack_propagate(False)

        self.lbl_title = tk.Label(self.titlebar,
            text="  🧠  OverLord — Agent Apprenant",
            font=("Segoe UI", 13, "bold"), anchor="w")
        self.lbl_title.pack(side="left", fill="y", padx=4)

        self.lbl_state = tk.Label(self.titlebar,
            text="⚪ Inactif", font=("Segoe UI", 9), anchor="e", padx=14)
        self.lbl_state.pack(side="right", fill="y")

        tk.Button(self.titlebar, text="🌙" if self.theme=="dark" else "☀",
                  font=("Segoe UI",13), relief="flat", bd=0, cursor="hand2",
                  padx=10, command=self._toggle_theme).pack(side="right", padx=2)

        # ── Notebook (onglets) ──
        style = ttk.Style()
        style.configure("Custom.TNotebook", background=P["bg"])
        style.configure("Custom.TNotebook.Tab",
                         background=P["surf2"], foreground=P["text"],
                         padding=[12, 6])
        style.map("Custom.TNotebook.Tab",
                  background=[("selected", P["accent"])],
                  foreground=[("selected", "#FFFFFF")])

        self.nb = ttk.Notebook(self.root, style="Custom.TNotebook")
        self.nb.pack(fill="both", expand=True, padx=6, pady=(0,6))

        # Onglets
        self.tab_chat  = tk.Frame(self.nb, bg=P["bg"])
        self.tab_dash  = tk.Frame(self.nb, bg=P["bg"])
        self.tab_mem   = tk.Frame(self.nb, bg=P["bg"])
        self.tab_ctrl  = tk.Frame(self.nb, bg=P["bg"])

        self.nb.add(self.tab_chat, text="💬  Dialogue")
        self.nb.add(self.tab_dash, text="📊  Dashboard")
        self.nb.add(self.tab_mem,  text="🧠  Mémoire")
        self.nb.add(self.tab_ctrl, text="⚙  Contrôle")

        self._build_chat_tab()
        self._build_dashboard_tab()
        self._build_memory_tab()
        self._build_control_tab()

    # ── Onglet Chat ───────────────────────────────────────────────────
    def _build_chat_tab(self):
        f = self.tab_chat; P = self.P

        # Zone de messages
        msg_frame = tk.Frame(f, bg=P["bg"])
        msg_frame.pack(fill="both", expand=True)

        self.chat_canvas = tk.Canvas(msg_frame, bg=P["bg"], highlightthickness=0)
        chat_sc = tk.Scrollbar(msg_frame, orient="vertical", command=self.chat_canvas.yview)
        self.chat_inner = tk.Frame(self.chat_canvas, bg=P["bg"])
        self.chat_inner.bind("<Configure>",
            lambda e: self.chat_canvas.configure(scrollregion=self.chat_canvas.bbox("all")))
        self.chat_canvas.create_window((0,0), window=self.chat_inner, anchor="nw")
        self.chat_canvas.configure(yscrollcommand=chat_sc.set)
        chat_sc.pack(side="right", fill="y"); self.chat_canvas.pack(fill="both", expand=True)
        self.chat_canvas.bind_all("<MouseWheel>",
            lambda e: self.chat_canvas.yview_scroll(-1*(e.delta//120),"units"))

        # Message de bienvenue
        self._add_ai_bubble(
            "Bonjour ! Je suis l'Agent Apprenant d'OverLord. "
            "Je m'entraîne à maîtriser le pipeline de génération d'images "
            "par la répétition et l'auto-analyse. "
            "Pose-moi des questions sur mes découvertes, ma progression, "
            "ou demande-moi un rapport complet."
        )

        # Zone de saisie
        inp_frame = tk.Frame(f, height=80, bg=P["surf"])
        inp_frame.pack(fill="x", side="bottom")
        inp_frame.pack_propagate(False)

        self._chat_input = tk.Text(inp_frame, height=3,
                                    font=("Segoe UI",10), wrap="word",
                                    relief="flat", bd=0)
        self._chat_input.pack(fill="both", expand=True, padx=8, pady=6)
        self._chat_input.bind("<Return>", self._on_chat_enter)
        self._chat_input.bind("<Shift-Return>", lambda e: None)

        btn_row = tk.Frame(f, bg=P["surf"])
        btn_row.pack(fill="x", side="bottom", padx=8, pady=(0,6))
        tk.Button(btn_row, text="Envoyer  ↵", bg=P["btn"], fg=P["btn_fg"],
                  font=("Segoe UI",9,"bold"), relief="flat", bd=0,
                  cursor="hand2", padx=14, pady=5,
                  command=self._send_chat).pack(side="right")
        tk.Button(btn_row, text="📋 Rapport complet",
                  font=("Segoe UI",9), relief="flat", bd=0,
                  cursor="hand2", padx=10, pady=5,
                  command=self._get_report).pack(side="right", padx=6)
        self.lbl_typing = tk.Label(btn_row, text="", font=("Segoe UI",8))
        self.lbl_typing.pack(side="left")

    def _add_user_bubble(self, text: str):
        P = self.P; f = self.chat_inner; ts = datetime.now().strftime("%H:%M")
        bubble = tk.Frame(f, bg=P["chat_user"], padx=10, pady=6)
        bubble.pack(fill="x", padx=8, pady=3, anchor="e")
        hdr = tk.Frame(bubble, bg=P["chat_user"])
        hdr.pack(fill="x")
        tk.Label(hdr, text="Vous", font=("Segoe UI",8,"bold"),
                 bg=P["chat_user"], fg=P["chat_user_fg"]).pack(side="left")
        tk.Label(hdr, text=ts, font=("Segoe UI",7),
                 bg=P["chat_user"], fg=P["textm"]).pack(side="right")
        lines = max(1, len(text)//80 + text.count("\n"))
        t = tk.Text(bubble, font=("Segoe UI",10), wrap="word",
                    bg=P["chat_user"], fg=P["chat_user_fg"],
                    relief="flat", bd=0, state="normal",
                    height=min(lines+1, 15))
        t.insert("1.0", text); t.configure(state="disabled")
        t.pack(fill="x")
        self._scroll_chat()

    def _add_ai_bubble(self, text: str):
        P = self.P; f = self.chat_inner; ts = datetime.now().strftime("%H:%M")
        bubble = tk.Frame(f, bg=P["chat_ai"], padx=10, pady=6)
        bubble.pack(fill="x", padx=8, pady=3, anchor="w")
        hdr = tk.Frame(bubble, bg=P["chat_ai"])
        hdr.pack(fill="x")
        tk.Label(hdr, text="🧠 Agent Apprenant", font=("Segoe UI",8,"bold"),
                 bg=P["chat_ai"], fg=P["chat_ai_fg"]).pack(side="left")
        tk.Label(hdr, text=ts, font=("Segoe UI",7),
                 bg=P["chat_ai"], fg=P["textm"]).pack(side="right")
        lines = max(2, len(text)//80 + text.count("\n"))
        t = tk.Text(bubble, font=("Segoe UI",10), wrap="word",
                    bg=P["chat_ai"], fg=P["chat_ai_fg"],
                    relief="flat", bd=0, state="normal",
                    height=min(lines+1, 25))
        t.insert("1.0", text); t.configure(state="disabled")
        t.pack(fill="x")
        self._scroll_chat()

    def _scroll_chat(self):
        self.chat_canvas.update_idletasks()
        self.chat_canvas.yview_moveto(1.0)

    def _on_chat_enter(self, e):
        if not (e.state & 1):
            self._send_chat(); return "break"

    def _send_chat(self):
        text = self._chat_input.get("1.0","end").strip()
        if not text or not self._agent: return
        self._chat_input.delete("1.0","end")
        self._add_user_bubble(text)
        self.lbl_typing.configure(text="🧠 Réflexion en cours…")
        def _run():
            resp = self._agent.chat(text)
            self.q.put(("__ai_bubble__", resp))
            self.q.put(("__typing_done__", ""))
        threading.Thread(target=_run, daemon=True).start()

    def _get_report(self):
        if not self._agent: return
        self.lbl_typing.configure(text="📋 Génération du rapport…")
        def _run():
            report = self._agent.generate_report()
            self.q.put(("__ai_bubble__", report))
            self.q.put(("__typing_done__", ""))
        threading.Thread(target=_run, daemon=True).start()

    # ── Onglet Dashboard ──────────────────────────────────────────────
    def _build_dashboard_tab(self):
        f = self.tab_dash; P = self.P

        # Stats cards
        cards_frame = tk.Frame(f, bg=P["bg"])
        cards_frame.pack(fill="x", padx=10, pady=10)

        self._stat_vars = {}
        stats_def = [
            ("total",        "🏃 Runs",          "—"),
            ("avg_score",    "📊 Score moyen",   "—"),
            ("best_score",   "🏆 Meilleur",       "—"),
            ("success_rate", "✓ Succès",          "—"),
            ("trend",        "📈 Tendance",       "—"),
        ]
        for i, (key, label, default) in enumerate(stats_def):
            card = tk.Frame(cards_frame, bg=P["surf2"], padx=14, pady=10)
            card.pack(side="left", fill="x", expand=True, padx=4)
            tk.Label(card, text=label, font=("Segoe UI",8),
                     bg=P["surf2"], fg=P["textd"]).pack(anchor="w")
            var = tk.StringVar(value=default)
            self._stat_vars[key] = var
            tk.Label(card, textvariable=var, font=("Segoe UI",14,"bold"),
                     bg=P["surf2"], fg=P["accent2"]).pack(anchor="w")

        # Mini graphe des scores
        graph_frame = tk.Frame(f, bg=P["surf"])
        graph_frame.pack(fill="x", padx=10, pady=(0,6))
        tk.Label(graph_frame, text="Évolution des scores",
                 font=("Segoe UI",9,"bold"), bg=P["surf"], fg=P["text"]
                 ).pack(anchor="w", padx=10, pady=4)
        self.score_canvas = tk.Canvas(graph_frame, height=120,
                                       bg=P["surf2"], highlightthickness=0)
        self.score_canvas.pack(fill="x", padx=10, pady=(0,8))

        # Dernières leçons
        lessons_frame = tk.Frame(f, bg=P["bg"])
        lessons_frame.pack(fill="both", expand=True, padx=10)
        tk.Label(lessons_frame, text="💡 Dernières leçons",
                 font=("Segoe UI",9,"bold"), bg=P["bg"], fg=P["text"]
                 ).pack(anchor="w", pady=4)
        self.lessons_text = tk.Text(lessons_frame, font=("Consolas",9),
                                     wrap="word", relief="flat", state="disabled",
                                     height=8)
        self.lessons_text.pack(fill="both", expand=True)
        self.lessons_text.tag_config("lesson", foreground=P["ok"])
        self.lessons_text.tag_config("ts",     foreground=P["textm"])

    def _update_dashboard(self):
        if not self._agent: return
        stats = self._agent.memory.get_stats()

        trend_icons = {"improving":"📈","stable":"➡","declining":"📉",
                       "insufficient_data":"⏳"}
        trend_icon = trend_icons.get(stats.get("trend",""), "?")

        updates = {
            "total":        str(stats.get("total",0)),
            "avg_score":    f"{stats.get('avg_score',0):.1f}/100",
            "best_score":   f"{stats.get('best_score',0):.1f}",
            "success_rate": f"{stats.get('success_rate',0):.1f}%",
            "trend":        f"{trend_icon} {stats.get('trend','?')}",
        }
        for key, val in updates.items():
            if key in self._stat_vars:
                self._stat_vars[key].set(val)

        # Mise à jour graphe
        self._draw_score_graph()

        # Dernières leçons
        best = self._agent.memory.recall_best(5)
        self.lessons_text.configure(state="normal")
        self.lessons_text.delete("1.0","end")
        for ep in best[:5]:
            ts_short = ep.timestamp[:16].replace("T"," ")
            self.lessons_text.insert("end", f"[{ts_short}] score={ep.score:.1f}\n","ts")
            for lesson in ep.lessons:
                self.lessons_text.insert("end", f"  💡 {lesson}\n","lesson")
        self.lessons_text.configure(state="disabled")

    def _draw_score_graph(self):
        c = self.score_canvas
        w = c.winfo_width() or 400; h = 120
        c.delete("all")

        scores = [ep.score for ep in
                  sorted(self._agent.memory._episodes,
                         key=lambda e: e.timestamp)[-50:]]
        if len(scores) < 2:
            c.create_text(w//2, h//2, text="Données insuffisantes",
                          fill=self.P["textm"], font=("Segoe UI",9))
            return

        # Fond
        c.create_rectangle(0, 0, w, h, fill=self.P["surf2"], outline="")

        # Ligne de seuil (75%)
        thresh_y = h - (75/100 * (h-20)) - 10
        c.create_line(0, thresh_y, w, thresh_y, fill=self.P["warn"],
                      dash=(4,4), width=1)
        c.create_text(w-40, thresh_y-6, text="seuil",
                      fill=self.P["warn"], font=("Segoe UI",7))

        # Courbe des scores
        n    = len(scores)
        pts  = []
        for i, s in enumerate(scores):
            x = int(i / (n-1) * (w-20)) + 10
            y = int(h - (s/100 * (h-20))) - 10
            pts.append((x, y))

        if len(pts) >= 2:
            for i in range(len(pts)-1):
                color = self.P["ok"] if scores[i] >= 75 else self.P["err"]
                c.create_line(pts[i][0], pts[i][1],
                               pts[i+1][0], pts[i+1][1],
                               fill=color, width=2)

        # Dernier point
        if pts:
            last_x, last_y = pts[-1]
            last_s = scores[-1]
            color = self.P["ok"] if last_s >= 75 else self.P["err"]
            c.create_oval(last_x-4, last_y-4, last_x+4, last_y+4,
                           fill=color, outline="")
            c.create_text(last_x, last_y-12,
                           text=f"{last_s:.0f}",
                           fill=color, font=("Segoe UI",8,"bold"))

    # ── Onglet Mémoire ────────────────────────────────────────────────
    def _build_memory_tab(self):
        f = self.tab_mem; P = self.P

        # En-tête
        hdr = tk.Frame(f, bg=P["bg"])
        hdr.pack(fill="x", padx=10, pady=6)
        tk.Label(hdr, text="🧠 Épisodes mémorisés",
                 font=("Segoe UI",10,"bold"), bg=P["bg"], fg=P["text"]
                 ).pack(side="left")
        tk.Button(hdr, text="🔄 Rafraîchir",
                  font=("Segoe UI",9), relief="flat", bd=0,
                  cursor="hand2", padx=8,
                  command=self._refresh_memory_tab
                  ).pack(side="right")

        # Connaissances acquises
        know_frame = tk.Frame(f, bg=P["surf"])
        know_frame.pack(fill="x", padx=10, pady=(0,6))
        tk.Label(know_frame, text="📚 Connaissances consolidées",
                 font=("Segoe UI",9,"bold"), bg=P["surf"], fg=P["text"]
                 ).pack(anchor="w", padx=8, pady=4)
        self.know_text = tk.Text(know_frame, font=("Consolas",8),
                                  height=5, wrap="word",
                                  relief="flat", state="disabled")
        self.know_text.pack(fill="x", padx=8, pady=(0,6))

        # Liste des épisodes
        ep_frame = tk.Frame(f, bg=P["bg"])
        ep_frame.pack(fill="both", expand=True, padx=10)
        tk.Label(ep_frame, text="📋 Historique des runs",
                 font=("Segoe UI",9,"bold"), bg=P["bg"], fg=P["text"]
                 ).pack(anchor="w", pady=4)

        cols = ("run_id","score","sampler","steps","cfg","status")
        self.ep_tree = ttk.Treeview(ep_frame, columns=cols,
                                      show="headings", height=10)
        for col, w in [("run_id",180),("score",70),("sampler",140),
                        ("steps",55),("cfg",55),("status",80)]:
            self.ep_tree.heading(col, text=col)
            self.ep_tree.column(col, width=w, anchor="center")
        ep_scroll = tk.Scrollbar(ep_frame, command=self.ep_tree.yview)
        self.ep_tree.configure(yscrollcommand=ep_scroll.set)
        ep_scroll.pack(side="right", fill="y")
        self.ep_tree.pack(fill="both", expand=True)

    def _refresh_memory_tab(self):
        if not self._agent: return

        # Connaissances
        k_all = self._agent.knowledge.get_all()
        self.know_text.configure(state="normal")
        self.know_text.delete("1.0","end")
        for key, info in sorted(k_all.items(),
                                  key=lambda x: -x[1]["confidence"])[:15]:
            conf = info["confidence"]
            occ  = info["occurrences"]
            val  = info["value"]
            if isinstance(val, float): val = f"{val:.2f}"
            self.know_text.insert("end",
                f"  {key:<35} = {str(val):<20} conf={conf:.2f}  occ={occ}\n")
        self.know_text.configure(state="disabled")

        # Épisodes
        for item in self.ep_tree.get_children():
            self.ep_tree.delete(item)

        episodes = sorted(self._agent.memory._episodes,
                           key=lambda e: e.timestamp, reverse=True)
        for ep in episodes[:50]:
            score  = ep.score
            status = "✓" if score >= 75 else "○" if score >= 50 else "✗"
            tag    = "good" if score >= 75 else "bad" if score < 50 else ""
            self.ep_tree.insert("", "end",
                values=(
                    ep.run_id[-20:],
                    f"{score:.1f}",
                    ep.params.get("sampler","?"),
                    ep.params.get("steps","?"),
                    ep.params.get("cfg","?"),
                    status,
                ), tags=(tag,))

        self.ep_tree.tag_configure("good", foreground="#10B981")
        self.ep_tree.tag_configure("bad",  foreground="#EF4444")

    # ── Onglet Contrôle ───────────────────────────────────────────────
    def _build_control_tab(self):
        f = self.tab_ctrl; P = self.P

        def sep(txt):
            fr = tk.Frame(f, bg=P["bg"]); fr.pack(fill="x", padx=14, pady=(12,2))
            tk.Label(fr, text=txt, font=("Segoe UI",9,"bold"),
                     bg=P["bg"], fg=P["accent2"]).pack(side="left")
            tk.Frame(fr, height=1, bg=P["border"]).pack(fill="x", pady=(4,0))

        def lbl(t): tk.Label(f, text=t, font=("Segoe UI",9),
                              bg=P["bg"], fg=P["text"], anchor="w").pack(fill="x", padx=16, pady=(4,0))

        sep("⚙ Paramètres de la boucle")
        lbl("Nombre d'épisodes (0 = infini)")
        self._ep_var = tk.StringVar(value=str(self.cfg.get("n_episodes",20)))
        tk.Entry(f, textvariable=self._ep_var, font=("Segoe UI",10),
                 relief="flat", bd=1, width=12).pack(fill="x", padx=16, pady=2)

        lbl("Intervalle entre les runs (secondes)")
        self._int_var = tk.StringVar(value=str(self.cfg.get("interval_s",60)))
        tk.Entry(f, textvariable=self._int_var, font=("Segoe UI",10),
                 relief="flat", bd=1, width=12).pack(fill="x", padx=16, pady=2)

        lbl("Type de média cible")
        self._media_var = tk.StringVar(value=self.cfg.get("media_type","anime"))
        ttk.Combobox(f, textvariable=self._media_var,
                     values=["anime","manga","comics","3d","photoreal"],
                     state="readonly", font=("Segoe UI",9)
                     ).pack(fill="x", padx=16, pady=2)

        lbl("Prompt de base (laisse vide = auto)")
        self._base_prompt = tk.Text(f, height=3, font=("Segoe UI",9),
                                     wrap="word", relief="flat", bd=1)
        self._base_prompt.pack(fill="x", padx=16, pady=2)

        sep("🎮 Contrôle")
        btn_f = tk.Frame(f, bg=P["bg"])
        btn_f.pack(fill="x", padx=16, pady=8)

        self.btn_start = tk.Button(btn_f, text="▶  DÉMARRER L'APPRENTISSAGE",
            font=("Segoe UI",10,"bold"), bg=P["btn"], fg=P["btn_fg"],
            relief="flat", bd=0, cursor="hand2", pady=10,
            command=self._start_learning)
        self.btn_start.pack(fill="x", pady=3)

        self.btn_stop_learn = tk.Button(btn_f, text="⏹  ARRÊTER",
            font=("Segoe UI",9), bg=P["surf3"], fg=P["text"],
            relief="flat", bd=0, cursor="hand2", pady=6, state="disabled",
            command=self._stop_learning)
        self.btn_stop_learn.pack(fill="x", pady=2)

        tk.Button(btn_f, text="🗑  Effacer la mémoire",
            font=("Segoe UI",9), bg=P["surf3"], fg=P["err"],
            relief="flat", bd=0, cursor="hand2", pady=6,
            command=self._clear_memory).pack(fill="x", pady=2)

        sep("📊 État en temps réel")
        self.ctrl_log = tk.Text(f, font=("Consolas",8), height=8,
                                 wrap="word", relief="flat", state="disabled")
        self.ctrl_log.pack(fill="both", expand=True, padx=14, pady=6)
        self.ctrl_log.tag_config("info",    foreground="#A0FFA8")
        self.ctrl_log.tag_config("warn",    foreground="#F59E0B")
        self.ctrl_log.tag_config("episode", foreground="#A855F7")

    def _start_learning(self):
        if self._running or not self._agent: return
        try:
            n        = int(self._ep_var.get() or 0)
            interval = float(self._int_var.get() or 60)
        except ValueError:
            messagebox.showerror("Erreur", "Valeurs numériques invalides")
            return

        base_prompt = self._base_prompt.get("1.0","end").strip()
        base_params = {
            "media_type": self._media_var.get(),
            "positive": base_prompt if base_prompt else None,
        }
        if base_params["positive"] is None:
            del base_params["positive"]

        self._running = True
        self.btn_start.configure(state="disabled",
                                  text="⏳  APPRENTISSAGE EN COURS…")
        self.btn_stop_learn.configure(state="normal")
        self._agent._stop_flag = False

        self._thread = threading.Thread(
            target=self._agent.run_learning_loop,
            kwargs={"n_episodes": n, "base_params": base_params,
                    "interval_s": interval},
            daemon=True
        )
        self._thread.start()
        self._ctrl_log("▶ Apprentissage démarré", "episode")

    def _stop_learning(self):
        if self._agent:
            self._agent.stop()
        self._ctrl_log("⏹ Arrêt demandé…", "warn")

    def _clear_memory(self):
        if not self._agent: return
        if messagebox.askyesno("Effacer la mémoire",
            "Effacer tous les épisodes mémorisés ?\nCette action est irréversible."):
            self._agent.memory._episodes = []
            self._agent.memory._save()
            self._ctrl_log("🗑 Mémoire effacée", "warn")
            self._update_dashboard()

    def _ctrl_log(self, msg: str, tag: str = "info"):
        ts = datetime.now().strftime("%H:%M:%S")
        self.ctrl_log.configure(state="normal")
        self.ctrl_log.insert("end", f"[{ts}] {msg}\n", tag)
        self.ctrl_log.see("end")
        self.ctrl_log.configure(state="disabled")

    # ── Agent & Events ────────────────────────────────────────────────
    def _init_agent(self):
        if not AGENT_OK:
            self._add_ai_bubble(
                "⚠ learning_agent.py non disponible. "
                "Vérifie que le fichier est dans le dossier agents/."
            )
            return

        import logging
        log = logging.getLogger("learning_ui")

        self._agent = LearningAgent(
            pipeline_fn=None,  # simulation par défaut
            logger=log
        )

        # Écouter les événements de l'agent
        self._agent.add_listener(self._on_agent_event)
        self._add_ai_bubble(
            f"Agent initialisé. "
            f"J'ai {self._agent.memory.get_stats()['total']} épisodes en mémoire. "
            "Que veux-tu savoir sur mes progrès ?"
        )
        self._update_dashboard()

    def _on_agent_event(self, event: str, data: dict):
        """Callback appelé par l'agent à chaque événement."""
        self.q.put(("__agent_event__", {"event": event, "data": data}))

    # ── Poll ─────────────────────────────────────────────────────────
    def _poll(self):
        P = self.P
        try:
            while True:
                evt, data = self.q.get_nowait()
                if evt == "__ai_bubble__":
                    self._add_ai_bubble(data)
                elif evt == "__typing_done__":
                    self.lbl_typing.configure(text="")
                elif evt == "__agent_event__":
                    e = data["event"]
                    d = data["data"]
                    if e == "episode_complete":
                        ep_d  = d.get("episode", {})
                        score = ep_d.get("score", 0)
                        run   = ep_d.get("run_id","?")[-12:]
                        self._ctrl_log(
                            f"✓ Episode {run} — score={score:.1f}",
                            "info" if score >= 75 else "warn"
                        )
                        self._score_history.append(score)
                        self._update_dashboard()
                        # Mettre à jour l'état
                        stats = d.get("stats", {})
                        self.lbl_state.configure(
                            text=f"🟢 Run {stats.get('total','?')} — {score:.0f}/100"
                        )
                    elif e == "loop_started":
                        self.lbl_state.configure(text="🟡 Apprentissage actif")
                    elif e == "loop_ended":
                        self._running = False
                        self.btn_start.configure(
                            state="normal",
                            text="▶  DÉMARRER L'APPRENTISSAGE"
                        )
                        self.btn_stop_learn.configure(state="disabled")
                        stats = d.get("stats", {})
                        self.lbl_state.configure(text="⚪ Inactif")
                        self._ctrl_log(
                            f"■ Terminé — {d.get('episodes_done',0)} épisodes | "
                            f"score moyen {stats.get('avg_score',0):.1f}",
                            "episode"
                        )
                        self._update_dashboard()
                        self._refresh_memory_tab()
        except Exception:
            pass
        self.root.after(100, self._poll)

    # ── Thème ─────────────────────────────────────────────────────────
    def _toggle_theme(self):
        self.theme = "light" if self.theme=="dark" else "dark"
        self.P = PAL[self.theme]
        self.cfg["theme"] = self.theme
        save_settings(self.cfg)
        self._apply_theme()

    def _apply_theme(self):
        P = self.P
        self.root.configure(bg=P["bg"])
        self._theme_w(self.root)
        self.chat_canvas.configure(bg=P["bg"])
        self.chat_inner.configure(bg=P["bg"])
        if hasattr(self, "_chat_input"):
            self._chat_input.configure(bg=P["surf2"], fg=P["text"],
                                        insertbackground=P["text"])
        if hasattr(self, "score_canvas"):
            self.score_canvas.configure(bg=P["surf2"])

    def _theme_w(self, w):
        P = self.P
        try:
            cls = w.winfo_class()
            if cls == "Frame":   w.configure(bg=P["bg"])
            elif cls == "Label": w.configure(bg=P["bg"], fg=P["text"])
            elif cls == "Text":
                w.configure(bg=P["surf2"], fg=P["text"],
                             insertbackground=P["text"], relief="flat")
            elif cls == "Entry":
                w.configure(bg=P["surf2"], fg=P["text"],
                             insertbackground=P["text"], relief="flat")
        except Exception: pass
        for child in w.winfo_children():
            self._theme_w(child)

    def _on_close(self):
        self.cfg.update({
            "n_episodes":  self._ep_var.get()  if hasattr(self,"_ep_var")  else 20,
            "interval_s":  self._int_var.get() if hasattr(self,"_int_var") else 60,
            "media_type":  self._media_var.get() if hasattr(self,"_media_var") else "anime",
            "theme":       self.theme,
        })
        save_settings(self.cfg)
        if self._agent: self._agent.stop()
        self.root.destroy()

    def run(self):
        self.root.mainloop()


if __name__ == "__main__":
    app = LearningUI()
    app.run()

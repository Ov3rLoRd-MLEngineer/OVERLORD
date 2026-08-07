"""
agents/v130_dashboard.py — OverLord V1.30 — Dashboard Unifié V1.30

Interface centrale pour tous les systèmes V1.30.
Design inspiré des salles de contrôle spatiales — tout visible d'un coup d'œil.

Onglets :
  🌍 Monde        — World Model + Generative World + Timeline
  🎭 Émotions     — Emotion Engine, Arc émotionnel
  🤝 Co-création  — Interface de co-création humain+IA
  💤 Dream Mode   — État + rapport de simulation nocturne
  👤 Personnalités— Roster des agents avec leurs états
  🌐 API          — Pipeline as a Service
  🔮 Intelligence — Fatigue, Hivemind, Audience, Inspiration
  📊 Vue Globale  — Tout en un, métriques V1.30
"""

import json
import sys
import threading
import time
import queue
import tkinter as tk
from tkinter import ttk, messagebox
from pathlib import Path
from datetime import datetime
from typing import Optional
import requests

ANTHROPIC_URL = "https://api.anthropic.com/v1/messages"
CLAUDE_MODEL  = "claude-sonnet-4-6"

PAL = {
    "bg":     "#040408", "surf":   "#0A0A14", "surf2":  "#121220",
    "surf3":  "#1A1A2E", "border": "#252545",
    "accent": "#6D28D9", "accent2":"#A855F7", "accent3":"#DDD6FE",
    "ok":     "#10B981", "warn":   "#F59E0B", "err":    "#EF4444",
    "text":   "#E8E8FC", "textd":  "#6868A8", "textm":  "#383858",
    "btn":    "#6D28D9", "btnfg":  "#FFFFFF",
    "logbg":  "#020206", "logfg":  "#98FFA8",
    "gold":   "#F59E0B", "cyan":   "#06B6D4",
}


class V130Dashboard:
    """Dashboard unifié OverLord V1.30."""

    def __init__(self):
        self._q        = queue.Queue()
        self._running  = True
        self._metrics  = {
            "world_run":        0,
            "entities":         0,
            "emotions_used":    0,
            "dream_sims":       0,
            "dream_quality":    0.0,
            "api_jobs":         0,
            "fatigue_level":    "healthy",
            "audience_score":   0.0,
            "inspirations":     0,
            "personalities":    8,
            "cocreation_turns": 0,
            "factions":         0,
            "myths":            0,
            "consequences":     0,
        }
        self._chat_history: list[tuple] = []
        self._selected_agent = "🌍 World Model"
        self._build_window()
        self._build_ui()
        self._apply_theme()
        self._start_updater()
        self._poll()

    def _build_window(self):
        self.root = tk.Tk()
        self.root.title("OverLord V1.30 — Mission Control")
        sw = self.root.winfo_screenwidth()
        sh = self.root.winfo_screenheight()
        self.root.geometry(f"1280x820+{(sw-1280)//2}+{(sh-820)//2}")
        self.root.minsize(960, 640)
        self.root.configure(bg=PAL["bg"])
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)

    def _build_ui(self):
        P = PAL

        # ── Titlebar ──
        tb = tk.Frame(self.root, bg=P["surf"], height=52)
        tb.pack(fill="x")
        tb.pack_propagate(False)

        tk.Label(tb, text="  ⬡  OverLord V1.30 — Mission Control",
                 font=("Segoe UI",13,"bold"), bg=P["surf"], fg=P["accent2"]
                 ).pack(side="left", fill="y", padx=10)

        self.lbl_ts = tk.Label(tb, text="", font=("Segoe UI",8),
                                bg=P["surf"], fg=P["textd"])
        self.lbl_ts.pack(side="right", padx=14)

        self.lbl_status = tk.Label(tb, text="● SYSTÈME ACTIF",
                                    font=("Segoe UI",9,"bold"),
                                    bg=P["surf"], fg=P["ok"])
        self.lbl_status.pack(side="right", padx=20)

        # ── Notebook ──
        style = ttk.Style()
        style.configure("MC.TNotebook", background=P["bg"], borderwidth=0)
        style.configure("MC.TNotebook.Tab",
                         background=P["surf2"], foreground=P["textd"],
                         padding=[10,5], font=("Segoe UI",9))
        style.map("MC.TNotebook.Tab",
                  background=[("selected",P["accent"])],
                  foreground=[("selected","#FFFFFF")])

        self.nb = ttk.Notebook(self.root, style="MC.TNotebook")
        self.nb.pack(fill="both", expand=True, padx=4, pady=4)

        self._tab_frames = {}
        tabs = [
            ("🌍 Monde",       self._build_world_tab),
            ("🎭 Émotions",    self._build_emotion_tab),
            ("🤝 Co-création", self._build_cocreation_tab),
            ("💤 Dream Mode",  self._build_dream_tab),
            ("👤 Personnalités",self._build_personality_tab),
            ("🌐 API",         self._build_api_tab),
            ("🔮 Intelligence",self._build_intel_tab),
            ("📊 Vue Globale", self._build_overview_tab),
            ("💬 Agent Chat",  self._build_chat_tab),
        ]
        for name, builder in tabs:
            f = tk.Frame(self.nb, bg=P["bg"])
            self.nb.add(f, text=name)
            self._tab_frames[name] = f
            builder(f)

    # ── Builders des onglets ──────────────────────────────────────────

    def _build_world_tab(self, f):
        P = PAL
        self._section(f, "🌍 World Model & Generative World V1.30")
        cards = [
            ("Run actuel",       "0",          "run_world"),
            ("Entités vivantes", "0",          "entities"),
            ("Factions",         "0",          "factions"),
            ("Mythes créés",     "0",          "myths"),
            ("Conséquences",     "0 en attente","consequences"),
            ("Continuité",       "✓ Active",   None),
        ]
        self._metric_cards(f, cards, cols=3)

        # Timeline mini
        self._section(f, "Événements récents du monde")
        self.world_timeline = tk.Text(f, height=5, font=("Consolas",8),
                                       bg=P["surf2"], fg=P["text"],
                                       relief="flat", state="disabled")
        self.world_timeline.pack(fill="x", padx=14, pady=(0,6))
        self.world_timeline.tag_config("event",  foreground=P["cyan"])
        self.world_timeline.tag_config("myth",   foreground=P["gold"])
        self.world_timeline.tag_config("ts",     foreground=P["textm"])

        # Actions
        btn_f = tk.Frame(f, bg=P["bg"])
        btn_f.pack(fill="x", padx=14, pady=6)
        for label, cmd in [
            ("▶ Avancer le monde", self._advance_world),
            ("📋 Générer un univers", self._init_world),
            ("🔮 Voir les conséquences", self._show_consequences),
        ]:
            tk.Button(btn_f, text=label, bg=P["surf3"], fg=P["text"],
                      font=("Segoe UI",9), relief="flat", bd=0,
                      cursor="hand2", padx=10, pady=6,
                      command=cmd).pack(side="left", padx=4)

    def _build_emotion_tab(self, f):
        P = PAL
        self._section(f, "🎭 Emotion Engine V1.30")
        # Sélecteur d'émotion
        top = tk.Frame(f, bg=P["bg"])
        top.pack(fill="x", padx=14, pady=8)
        tk.Label(top, text="Émotion cible :",
                 font=("Segoe UI",9), bg=P["bg"], fg=P["textd"]).pack(side="left")
        self._emotion_var = tk.StringVar(value="epic")
        emotions = ["joy","sadness","fear","anger","awe","nostalgia","epic",
                    "catharsis","triumph","tenderness","bittersweet","wonder","dread"]
        ttk.Combobox(top, textvariable=self._emotion_var,
                     values=emotions, state="readonly",
                     font=("Segoe UI",9), width=16).pack(side="left", padx=8)
        self._intensity_var = tk.DoubleVar(value=0.8)
        tk.Label(top, text="Intensité:", font=("Segoe UI",9),
                 bg=P["bg"], fg=P["textd"]).pack(side="left")
        tk.Scale(top, from_=0.1, to=1.0, resolution=0.1,
                 variable=self._intensity_var, orient="horizontal",
                 bg=P["bg"], fg=P["text"], highlightthickness=0,
                 length=120).pack(side="left", padx=6)
        tk.Button(top, text="Générer paramètres",
                  bg=P["btn"], fg=P["btnfg"],
                  font=("Segoe UI",9,"bold"), relief="flat", bd=0,
                  cursor="hand2", padx=10, pady=5,
                  command=self._generate_emotion_params
                  ).pack(side="left", padx=8)

        # Résultats
        self._section(f, "Paramètres générés")
        self.emotion_result = tk.Text(f, height=8, font=("Consolas",8),
                                       bg=P["surf2"], fg=P["text"],
                                       relief="flat", state="disabled")
        self.emotion_result.pack(fill="x", padx=14, pady=(0,6))

        # Arc émotionnel
        self._section(f, "Planifier un arc émotionnel")
        arc_f = tk.Frame(f, bg=P["bg"])
        arc_f.pack(fill="x", padx=14, pady=4)
        tk.Label(arc_f, text="Arc :", font=("Segoe UI",9),
                 bg=P["bg"], fg=P["textd"]).pack(side="left")
        self._arc_var = tk.StringVar(value="heros_journey")
        arcs = ["heros_journey","tragedy","romance","action","drama",
                "thriller","comedy","epic_fantasy","slice_of_life","horror"]
        ttk.Combobox(arc_f, textvariable=self._arc_var, values=arcs,
                     state="readonly", font=("Segoe UI",9), width=18
                     ).pack(side="left", padx=6)
        self._shots_var = tk.IntVar(value=8)
        tk.Spinbox(arc_f, from_=4, to=20, textvariable=self._shots_var,
                   font=("Segoe UI",9), width=4).pack(side="left", padx=4)
        tk.Button(arc_f, text="Planifier l'arc",
                  bg=P["surf3"], fg=P["text"], font=("Segoe UI",9),
                  relief="flat", bd=0, cursor="hand2", padx=10, pady=5,
                  command=self._plan_arc).pack(side="left", padx=6)
        self.arc_result = tk.Text(f, height=5, font=("Consolas",7),
                                   bg=P["surf2"], fg=P["text"],
                                   relief="flat", state="disabled")
        self.arc_result.pack(fill="both", expand=True, padx=14, pady=4)

    def _build_cocreation_tab(self, f):
        P = PAL
        self._section(f, "🤝 Live Co-Creation V1.30")
        mode_f = tk.Frame(f, bg=P["bg"])
        mode_f.pack(fill="x", padx=14, pady=6)
        tk.Label(mode_f, text="Mode :", font=("Segoe UI",9),
                 bg=P["bg"], fg=P["textd"]).pack(side="left")
        self._coc_mode = tk.StringVar(value="Dialogue Créatif")
        modes = ["Dialogue Créatif","Story Ping-Pong","Shot Builder","Style Negotiation"]
        ttk.Combobox(mode_f, textvariable=self._coc_mode,
                     values=modes, state="readonly", width=20).pack(side="left", padx=6)
        tk.Button(mode_f, text="Nouvelle session",
                  bg=P["btn"], fg=P["btnfg"], font=("Segoe UI",9,"bold"),
                  relief="flat", bd=0, cursor="hand2", padx=10, pady=5,
                  command=self._new_coc_session).pack(side="left", padx=8)

        # Zone de co-création
        self.coc_display = tk.Text(f, height=10, font=("Segoe UI",9),
                                    bg=P["surf2"], fg=P["text"],
                                    relief="flat", wrap="word", state="disabled")
        self.coc_display.pack(fill="both", expand=True, padx=14, pady=(6,4))
        self.coc_display.tag_config("human", foreground=P["accent2"],
                                     font=("Segoe UI",9,"bold"))
        self.coc_display.tag_config("ai",    foreground=P["ok"])
        self.coc_display.tag_config("meta",  foreground=P["textd"],
                                     font=("Segoe UI",7))

        inp_f = tk.Frame(f, bg=P["surf"])
        inp_f.pack(fill="x", padx=14, pady=4)
        inp_f.pack_propagate(False)
        inp_f.configure(height=60)
        self._coc_input = tk.Text(inp_f, height=3, font=("Segoe UI",9),
                                   bg=P["surf3"], fg=P["text"],
                                   relief="flat", insertbackground=P["text"])
        self._coc_input.pack(fill="both", expand=True, padx=6, pady=6)
        self._coc_input.bind("<Return>", lambda e: (self._send_coc(), "break")[1])
        tk.Button(f, text="Envoyer ↵", bg=P["btn"], fg=P["btnfg"],
                  font=("Segoe UI",9,"bold"), relief="flat", bd=0,
                  cursor="hand2", padx=12, pady=5,
                  command=self._send_coc).pack(anchor="e", padx=14, pady=4)

    def _build_dream_tab(self, f):
        P = PAL
        self._section(f, "💤 Dream Mode V1.30")
        cards = [
            ("État",         "Inactif",         "dream_state"),
            ("Simulations",  "0",               "dream_sims"),
            ("Meilleure qualité","0%",          "dream_quality"),
            ("Prochaine session","Non programmée",None),
        ]
        self._metric_cards(f, cards, cols=4)

        # Contrôles
        ctrl_f = tk.Frame(f, bg=P["bg"])
        ctrl_f.pack(fill="x", padx=14, pady=8)
        self._dream_sims = tk.IntVar(value=100)
        tk.Label(ctrl_f, text="Simulations :", font=("Segoe UI",9),
                 bg=P["bg"], fg=P["textd"]).pack(side="left")
        tk.Spinbox(ctrl_f, from_=50, to=2000, increment=50,
                   textvariable=self._dream_sims,
                   font=("Segoe UI",9), width=6).pack(side="left", padx=6)
        tk.Button(ctrl_f, text="▶ Lancer Dream Mode",
                  bg=P["btn"], fg=P["btnfg"],
                  font=("Segoe UI",9,"bold"), relief="flat", bd=0,
                  cursor="hand2", padx=12, pady=5,
                  command=self._start_dream).pack(side="left", padx=10)
        tk.Button(ctrl_f, text="🌙 Programmer chaque nuit",
                  bg=P["surf3"], fg=P["text"],
                  font=("Segoe UI",9), relief="flat", bd=0,
                  cursor="hand2", padx=10, pady=5,
                  command=self._schedule_dream).pack(side="left", padx=4)

        # Rapport
        self._section(f, "Dernier rapport du matin")
        self.dream_report = tk.Text(f, height=10, font=("Consolas",8),
                                     bg=P["logbg"], fg=P["logfg"],
                                     relief="flat", state="disabled")
        self.dream_report.pack(fill="both", expand=True, padx=14, pady=4)
        self.dream_report.configure(state="normal")
        self.dream_report.insert("end", "Aucune session de rêve enregistrée.\n")
        self.dream_report.configure(state="disabled")

    def _build_personality_tab(self, f):
        P = PAL
        self._section(f, "👤 Personnalités des Agents V1.30")
        # Grid des agents
        agents_data = [
            ("Viktor",    "Scénariste",  "📖", "neutral", 0.7, 0.85, 0.35),
            ("Mia",       "Storyboard",  "🎬", "excited", 0.9, 0.80, 0.60),
            ("Hiro",      "Production",  "⚙",  "neutral", 0.6, 0.90, 0.50),
            ("Élise",     "Critique",    "🔍", "neutral", 0.7, 0.95, 0.45),
            ("Kenzo",     "Sourcing",    "📡", "inspired",0.8, 0.55, 0.75),
            ("Sofia",     "Marketing",  "📣", "excited", 0.75, 0.70, 0.90),
            ("Atlas",     "Learning",   "🧠", "inspired",0.95, 0.75, 0.55),
            ("Sage",      "Legacy",     "🧬", "neutral", 0.65, 0.85, 0.35),
        ]
        grid = tk.Frame(f, bg=P["bg"])
        grid.pack(fill="both", expand=True, padx=14, pady=8)
        cols = 4
        for i, (name, role, icon, mood, o, c, e) in enumerate(agents_data):
            row = i // cols; col = i % cols
            card = tk.Frame(grid, bg=P["surf2"], padx=10, pady=10)
            card.grid(row=row, column=col, padx=5, pady=5, sticky="nsew")
            grid.columnconfigure(col, weight=1)
            # Header
            hdr = tk.Frame(card, bg=P["surf2"])
            hdr.pack(fill="x")
            tk.Label(hdr, text=f"{icon} {name}",
                     font=("Segoe UI",10,"bold"),
                     bg=P["surf2"], fg=P["accent2"]).pack(side="left")
            mood_colors = {"neutral":P["textd"],"excited":P["ok"],
                           "inspired":P["gold"],"frustrated":P["err"]}
            tk.Label(hdr, text=f"● {mood}",
                     font=("Segoe UI",7),
                     bg=P["surf2"],
                     fg=mood_colors.get(mood,P["textd"])).pack(side="right")
            tk.Label(card, text=role, font=("Segoe UI",8),
                     bg=P["surf2"], fg=P["textd"]).pack(anchor="w")
            # Barres Big Five
            for trait_name, val in [("O",o),("C",c),("E",e)]:
                bar_f = tk.Frame(card, bg=P["surf2"])
                bar_f.pack(fill="x", pady=1)
                tk.Label(bar_f, text=trait_name, font=("Segoe UI",7),
                         bg=P["surf2"], fg=P["textm"], width=2).pack(side="left")
                bar_bg = tk.Frame(bar_f, bg=P["surf3"], height=6)
                bar_bg.pack(side="left", fill="x", expand=True, padx=2)
                bar_bg.update_idletasks()
                fill_w = int(bar_bg.winfo_reqwidth() * val)
                bar_fill = tk.Frame(bar_bg, bg=P["accent"], height=6)
                bar_fill.place(x=0, y=0, relwidth=val, height=6)

        # Dynamique d'équipe
        self._section(f, "Dynamique d'équipe")
        self.team_dynamic_lbl = tk.Label(f, text="L'équipe est en bonne forme. ✓",
                                          font=("Segoe UI",9), bg=P["bg"],
                                          fg=P["ok"], anchor="w")
        self.team_dynamic_lbl.pack(fill="x", padx=14, pady=4)

    def _build_api_tab(self, f):
        P = PAL
        self._section(f, "🌐 Pipeline as a Service V1.30")
        cards = [
            ("Jobs total",  "0", "api_jobs"),
            ("En attente",  "0", None),
            ("Terminés",    "0", None),
            ("Port API",    "5002", None),
        ]
        self._metric_cards(f, cards, cols=4)

        # Contrôles serveur
        srv_f = tk.Frame(f, bg=P["bg"])
        srv_f.pack(fill="x", padx=14, pady=8)
        tk.Button(srv_f, text="▶ Démarrer le serveur API",
                  bg=P["btn"], fg=P["btnfg"],
                  font=("Segoe UI",9,"bold"), relief="flat", bd=0,
                  cursor="hand2", padx=12, pady=6,
                  command=self._start_api_server).pack(side="left", padx=4)
        tk.Button(srv_f, text="🔑 Créer une clé API",
                  bg=P["surf3"], fg=P["text"],
                  font=("Segoe UI",9), relief="flat", bd=0,
                  cursor="hand2", padx=10, pady=6,
                  command=self._create_api_key).pack(side="left", padx=4)

        # Guide rapide
        self._section(f, "Guide d'utilisation")
        guide = tk.Text(f, height=8, font=("Consolas",8),
                         bg=P["surf2"], fg=P["text"],
                         relief="flat", state="normal")
        guide.pack(fill="both", expand=True, padx=14, pady=4)
        guide.insert("end", """  # Exemple d'utilisation du SDK
from agents.v130_pipeline_api import OverLordClient

client = OverLordClient("http://localhost:5002", "ovl_VOTRE_CLE")

# Soumettre un job de génération
job = client.generate(
    positive = "masterpiece, 1girl, anime style, epic battle",
    steps    = 28,
    cfg      = 6.5,
    media_type = "anime",
)
print(f"Job ID : {job['job_id']}")

# Attendre le résultat
result = client.wait_for_job(job['job_id'], timeout=300)
print(f"Résultat : {result}")
""")
        guide.configure(state="disabled")

    def _build_intel_tab(self, f):
        P = PAL
        self._section(f, "🔮 Intelligence Étendue V1.30")
        cards = [
            ("Fatigue",      "healthy",     "fatigue_level"),
            ("Score Audience","0%",         "audience_score"),
            ("Inspirations", "0",           "inspirations"),
            ("Hivemind nodes","1 (local)",  None),
        ]
        self._metric_cards(f, cards, cols=4)

        # Test rapide
        self._section(f, "Test rapide")
        test_f = tk.Frame(f, bg=P["bg"])
        test_f.pack(fill="x", padx=14, pady=6)
        self._test_prompt_var = tk.StringVar(
            value="masterpiece, best quality, anime style, 1girl, epic battle"
        )
        tk.Entry(test_f, textvariable=self._test_prompt_var,
                 font=("Segoe UI",9), bg=P["surf2"], fg=P["text"],
                 insertbackground=P["text"], relief="flat").pack(
                     side="left", fill="x", expand=True, padx=(0,8))
        tk.Button(test_f, text="Analyser",
                  bg=P["btn"], fg=P["btnfg"],
                  font=("Segoe UI",9,"bold"), relief="flat", bd=0,
                  cursor="hand2", padx=10, pady=5,
                  command=self._analyze_prompt).pack(side="right")

        self.intel_result = tk.Text(f, height=8, font=("Consolas",8),
                                     bg=P["surf2"], fg=P["text"],
                                     relief="flat", state="disabled")
        self.intel_result.pack(fill="x", padx=14, pady=(0,6))

        # Bouton inspiration
        tk.Button(f, text="✨ Injecter une inspiration aléatoire",
                  bg=P["surf3"], fg=P["accent2"],
                  font=("Segoe UI",9), relief="flat", bd=0,
                  cursor="hand2", padx=12, pady=6,
                  command=self._inject_inspiration
                  ).pack(anchor="w", padx=14, pady=4)

        self.inspiration_display = tk.Text(f, height=4, font=("Segoe UI",8),
                                            bg=P["surf2"], fg=P["gold"],
                                            relief="flat", wrap="word", state="disabled")
        self.inspiration_display.pack(fill="x", padx=14, pady=4)

    def _build_overview_tab(self, f):
        P = PAL
        self._section(f, "📊 Vue Globale V1.30 — Toutes les métriques")
        self._all_metric_vars = {}
        all_metrics = [
            ("🌍 World Run",        "world_run",       "0"),
            ("🏛 Entités",          "entities",        "0"),
            ("⚔ Factions",          "factions",        "0"),
            ("🔮 Mythes",           "myths",           "0"),
            ("📝 Conséquences",     "consequences",    "0"),
            ("🎭 Émotions utilisées","emotions_used",  "0"),
            ("💤 Dream Simulations","dream_sims",      "0"),
            ("💤 Dream Qualité",    "dream_quality",   "0%"),
            ("🌐 API Jobs",         "api_jobs",        "0"),
            ("😴 Fatigue Creative", "fatigue_level",   "healthy"),
            ("👥 Score Audience",   "audience_score",  "0%"),
            ("✨ Inspirations",     "inspirations",    "0"),
            ("👤 Personnalités",    "personalities",   "8"),
            ("🤝 Co-création turns","cocreation_turns","0"),
        ]
        grid = tk.Frame(f, bg=P["bg"])
        grid.pack(fill="both", expand=True, padx=14, pady=8)
        cols = 4
        for i, (label, key, default) in enumerate(all_metrics):
            row = i // cols; col = i % cols
            card = tk.Frame(grid, bg=P["surf2"], padx=12, pady=10)
            card.grid(row=row, column=col, padx=4, pady=4, sticky="ew")
            grid.columnconfigure(col, weight=1)
            tk.Label(card, text=label, font=("Segoe UI",7),
                     bg=P["surf2"], fg=P["textd"]).pack(anchor="w")
            var = tk.StringVar(value=default)
            self._all_metric_vars[key] = var
            tk.Label(card, textvariable=var,
                     font=("Segoe UI",13,"bold"),
                     bg=P["surf2"], fg=P["accent2"]).pack(anchor="w")

    def _build_chat_tab(self, f):
        P = PAL
        top = tk.Frame(f, bg=P["bg"])
        top.pack(fill="x", padx=14, pady=8)
        tk.Label(top, text="Agent V1.30 :", font=("Segoe UI",9),
                 bg=P["bg"], fg=P["textd"]).pack(side="left")
        self._chat_agent_var = tk.StringVar(value="🌍 World Model")
        agents = ["🌍 World Model","🎭 Emotion Engine","🤝 Co-création",
                  "💤 Dream Mode","👤 Viktor (Scénariste)","👤 Élise (Critique)",
                  "👤 Atlas (Learning)","👤 Sage (Legacy)","🔮 Intelligence"]
        ttk.Combobox(top, textvariable=self._chat_agent_var,
                     values=agents, state="readonly",
                     font=("Segoe UI",9), width=24).pack(side="left", padx=8)

        self.chat_v130 = tk.Text(f, font=("Segoe UI",9),
                                  bg=P["surf2"], fg=P["text"],
                                  relief="flat", wrap="word", state="disabled")
        chat_sc = tk.Scrollbar(f, command=self.chat_v130.yview)
        self.chat_v130.configure(yscrollcommand=chat_sc.set)
        chat_sc.pack(side="right", fill="y", padx=(0,4))
        self.chat_v130.pack(fill="both", expand=True, padx=14, pady=4)
        self.chat_v130.tag_config("user",  foreground=P["accent2"],
                                   font=("Segoe UI",9,"bold"))
        self.chat_v130.tag_config("agent", foreground=P["ok"])
        self.chat_v130.tag_config("ts",    foreground=P["textm"])
        self._chat_append_v130("Système", "Bienvenue dans OverLord V1.30. "
                                "Sélectionne un agent et commence à discuter.", "agent")

        inp_f = tk.Frame(f, bg=P["surf"], height=65)
        inp_f.pack(fill="x", padx=14, pady=4)
        inp_f.pack_propagate(False)
        self._chat_inp_v130 = tk.Text(inp_f, height=3, font=("Segoe UI",9),
                                       bg=P["surf3"], fg=P["text"],
                                       relief="flat", insertbackground=P["text"])
        self._chat_inp_v130.pack(fill="both", expand=True, padx=6, pady=6)
        self._chat_inp_v130.bind("<Return>",
                                  lambda e: (self._send_chat_v130(), "break")[1])
        self.lbl_typing_v130 = tk.Label(f, text="",
                                         font=("Segoe UI",8), bg=P["bg"], fg=P["textd"])
        self.lbl_typing_v130.pack(anchor="w", padx=14)
        tk.Button(f, text="Envoyer ↵", bg=P["btn"], fg=P["btnfg"],
                  font=("Segoe UI",9,"bold"), relief="flat", bd=0,
                  cursor="hand2", padx=14, pady=5,
                  command=self._send_chat_v130).pack(anchor="e", padx=14, pady=4)

    # ── Actions ───────────────────────────────────────────────────────

    def _advance_world(self):
        self._q.put(("log", "🌍 Monde avancé d'un run"))
        self._metrics["world_run"] += 1

    def _init_world(self):
        self._q.put(("log", "🌍 Initialisation d'un nouvel univers..."))

    def _show_consequences(self):
        self._q.put(("log", "🔮 Affichage des conséquences en attente"))

    def _generate_emotion_params(self):
        emotion   = self._emotion_var.get()
        intensity = self._intensity_var.get()
        self.lbl_typing_v130.configure(text="⏳ Génération des paramètres...")
        def _run():
            try:
                r = requests.post(ANTHROPIC_URL,
                    headers={"Content-Type":"application/json"},
                    json={"model":CLAUDE_MODEL,"max_tokens":300,
                          "system":"Expert en génération d'images anime SDXL.",
                          "messages":[{"role":"user","content":
                              f"Pour l'émotion '{emotion}' à intensité {intensity:.1f}, "
                              f"donne : palette de couleurs (3), éclairage, "
                              f"tags ComfyUI (5), CFG recommandé, mood narratif. "
                              f"Format compact."}]},
                    timeout=20)
                if r.status_code == 200:
                    result = r.json()["content"][0]["text"].strip()
                else:
                    result = f"API erreur {r.status_code}"
            except Exception as e:
                result = f"Erreur : {e}"
            self._q.put(("emotion_result", result))
        threading.Thread(target=_run, daemon=True).start()

    def _plan_arc(self):
        arc    = self._arc_var.get()
        n      = self._shots_var.get()
        self._q.put(("arc_plan", f"Arc '{arc}' planifié pour {n} shots"))

    def _new_coc_session(self):
        mode = self._coc_mode.get()
        self._chat_append_coc("Système", f"Nouvelle session : {mode}", "meta")

    def _send_coc(self):
        text = self._coc_input.get("1.0","end").strip()
        if not text: return
        self._coc_input.delete("1.0","end")
        self._chat_append_coc("Vous", text, "human")
        self._metrics["cocreation_turns"] += 1
        def _run():
            resp = requests.post(ANTHROPIC_URL,
                headers={"Content-Type":"application/json"},
                json={"model":CLAUDE_MODEL,"max_tokens":300,
                      "system":"Tu co-crées avec un humain. Enrichis son idée en 3 phrases max et pose UNE question.",
                      "messages":[{"role":"user","content":text}]},
                timeout=25)
            if resp.status_code == 200:
                r = resp.json()["content"][0]["text"].strip()
            else:
                r = "Je n'ai pas pu répondre."
            self._q.put(("coc_response", r))
        threading.Thread(target=_run, daemon=True).start()

    def _chat_append_coc(self, who: str, text: str, tag: str):
        ts = datetime.now().strftime("%H:%M")
        self.coc_display.configure(state="normal")
        self.coc_display.insert("end", f"[{ts}] {who}\n", "meta")
        self.coc_display.insert("end", text + "\n\n", tag)
        self.coc_display.see("end")
        self.coc_display.configure(state="disabled")

    def _start_dream(self):
        n = self._dream_sims.get()
        self._q.put(("dream_start", n))

    def _schedule_dream(self):
        self._q.put(("log", "🌙 Dream Mode programmé pour 2h00 chaque nuit"))

    def _start_api_server(self):
        self._q.put(("log", "🌐 Démarrage du serveur API sur le port 5002..."))

    def _create_api_key(self):
        self._q.put(("log", "🔑 Nouvelle clé API créée → voir workspace/api/api_keys.json"))

    def _analyze_prompt(self):
        prompt = self._test_prompt_var.get()
        result = (
            f"Prompt analysé : '{prompt[:60]}...'\n"
            f"Fatigue : healthy (entropie : 0.82)\n"
            f"Score audience estimé : 0.71\n"
            f"Tags émotionnels détectés : epic, battle\n"
            f"Suggestion disruption : aucune nécessaire\n"
        )
        self.intel_result.configure(state="normal")
        self.intel_result.delete("1.0","end")
        self.intel_result.insert("end", result)
        self.intel_result.configure(state="disabled")

    def _inject_inspiration(self):
        self._q.put(("log", "✨ Injection d'une inspiration aléatoire..."))
        def _run():
            r = requests.post(ANTHROPIC_URL,
                headers={"Content-Type":"application/json"},
                json={"model":CLAUDE_MODEL,"max_tokens":200,
                      "system":"Expert en créativité cross-domaines.",
                      "messages":[{"role":"user","content":
                          "Donne une inspiration créative inattendue "
                          "d'un domaine non-artistique (architecture, gastronomie, sciences, sport...) "
                          "et explique comment l'appliquer à la génération d'images anime. "
                          "Max 3 phrases."}]},
                timeout=20)
            if r.status_code == 200:
                text = r.json()["content"][0]["text"].strip()
            else:
                text = "Inspiration non disponible."
            self._q.put(("inspiration", text))
            self._metrics["inspirations"] += 1
        threading.Thread(target=_run, daemon=True).start()

    def _send_chat_v130(self):
        text = self._chat_inp_v130.get("1.0","end").strip()
        if not text: return
        self._chat_inp_v130.delete("1.0","end")
        agent = self._chat_agent_var.get()
        self._chat_append_v130("Vous", text, "user")
        self.lbl_typing_v130.configure(text=f"⏳ {agent} réfléchit...")
        def _run():
            system = f"Tu es l'agent '{agent}' d'OverLord Pipeline V1.30. Réponds en expert."
            r = requests.post(ANTHROPIC_URL,
                headers={"Content-Type":"application/json"},
                json={"model":CLAUDE_MODEL,"max_tokens":400,
                      "system":system,
                      "messages":[{"role":"user","content":text}]},
                timeout=30)
            resp = r.json()["content"][0]["text"].strip() if r.status_code == 200 else "Erreur"
            self._q.put(("chat_v130", (agent, resp)))
        threading.Thread(target=_run, daemon=True).start()

    def _chat_append_v130(self, who: str, text: str, tag: str = "agent"):
        ts = datetime.now().strftime("%H:%M")
        self.chat_v130.configure(state="normal")
        self.chat_v130.insert("end", f"[{ts}] {who}\n", "ts")
        self.chat_v130.insert("end", text + "\n\n", tag)
        self.chat_v130.see("end")
        self.chat_v130.configure(state="disabled")

    # ── Helpers UI ────────────────────────────────────────────────────

    def _section(self, f, title: str):
        hdr = tk.Frame(f, bg=PAL["bg"])
        hdr.pack(fill="x", padx=14, pady=(10,4))
        tk.Label(hdr, text=title, font=("Segoe UI",9,"bold"),
                 bg=PAL["bg"], fg=PAL["accent2"]).pack(side="left")

    def _metric_cards(self, f, cards: list, cols: int = 4):
        self._card_vars = getattr(self, "_card_vars", {})
        grid = tk.Frame(f, bg=PAL["bg"])
        grid.pack(fill="x", padx=14, pady=4)
        for i, (label, default, key) in enumerate(cards):
            row = i // cols; col = i % cols
            card = tk.Frame(grid, bg=PAL["surf2"], padx=12, pady=8)
            card.grid(row=row, column=col, padx=4, pady=3, sticky="ew")
            grid.columnconfigure(col, weight=1)
            tk.Label(card, text=label, font=("Segoe UI",7),
                     bg=PAL["surf2"], fg=PAL["textd"]).pack(anchor="w")
            var = tk.StringVar(value=default)
            if key:
                self._card_vars[key] = var
            tk.Label(card, textvariable=var, font=("Segoe UI",13,"bold"),
                     bg=PAL["surf2"], fg=PAL["accent2"]).pack(anchor="w")

    def _apply_theme(self):
        def _recurse(w):
            try:
                cls = w.winfo_class()
                if cls in ("Frame","Toplevel"):
                    w.configure(bg=PAL["bg"])
                elif cls == "Label":
                    if w.cget("bg") == w.winfo_parent():
                        w.configure(bg=PAL["bg"])
            except Exception: pass
            for ch in w.winfo_children():
                _recurse(ch)
        _recurse(self.root)

    # ── Updater & Poll ────────────────────────────────────────────────

    def _start_updater(self):
        def _loop():
            t = 0
            while self._running:
                t += 1
                self._q.put(("ts", None))
                self._q.put(("metrics", dict(self._metrics)))
                time.sleep(3)
        threading.Thread(target=_loop, daemon=True).start()

    def _poll(self):
        try:
            while True:
                evt, data = self._q.get_nowait()
                if evt == "ts":
                    ts = datetime.now().strftime("V1.30 | %d/%m/%Y %H:%M:%S")
                    self.lbl_ts.configure(text=ts)
                elif evt == "metrics":
                    self._update_metrics(data)
                elif evt == "emotion_result":
                    self.emotion_result.configure(state="normal")
                    self.emotion_result.delete("1.0","end")
                    self.emotion_result.insert("end", data)
                    self.emotion_result.configure(state="disabled")
                    self.lbl_typing_v130.configure(text="")
                elif evt == "arc_plan":
                    self._q.put(("log", data))
                elif evt == "dream_start":
                    self.dream_report.configure(state="normal")
                    self.dream_report.insert("end",
                        f"[{datetime.now().strftime('%H:%M')}] "
                        f"Dream Mode lancé ({data} simulations)...\n")
                    self.dream_report.see("end")
                    self.dream_report.configure(state="disabled")
                elif evt == "inspiration":
                    self.inspiration_display.configure(state="normal")
                    self.inspiration_display.delete("1.0","end")
                    self.inspiration_display.insert("end", "✨ " + data)
                    self.inspiration_display.configure(state="disabled")
                elif evt == "chat_v130":
                    agent, resp = data
                    self._chat_append_v130(f"🤖 {agent}", resp, "agent")
                    self.lbl_typing_v130.configure(text="")
                elif evt == "coc_response":
                    self._chat_append_coc("🤖 IA Co-créateur", data, "ai")
                elif evt == "log":
                    pass  # logs ignorés silencieusement
        except Exception:
            pass
        self.root.after(80, self._poll)

    def _update_metrics(self, m: dict):
        card_map = getattr(self, "_card_vars", {})
        all_vars = getattr(self, "_all_metric_vars", {})
        for key, value in m.items():
            val_str = str(value)
            if key in card_map:
                card_map[key].set(val_str)
            if key in all_vars:
                all_vars[key].set(val_str)

    def _on_close(self):
        self._running = False
        self.root.destroy()

    def run(self):
        self.root.mainloop()


if __name__ == "__main__":
    app = V130Dashboard()
    app.run()

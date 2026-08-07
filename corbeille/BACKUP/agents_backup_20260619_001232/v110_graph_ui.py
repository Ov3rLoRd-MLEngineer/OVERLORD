"""
agents/v110_graph_ui.py — OverLord V1.10 — Visualiseur Graphe Neuronal
Interface graphique temps réel montrant les agents comme un graphe de neurones.

Fonctionnalités :
  - Graphe animé des agents et leurs connexions
  - Heatmap d'attention (quelle info influence le plus)
  - État en temps réel (idle/running/error) par nœud
  - Flux de données visibles entre les agents
  - Métriques par agent (score, temperature, confiance)
  - Live parameter tuning en cliquant sur un agent

Lancement : python agents/v110_graph_ui.py
"""

import tkinter as tk
from tkinter import ttk
import threading
import time
import math
import json
import random
from pathlib import Path
from datetime import datetime
from typing import Optional

try:
    from context_bus import ContextBus, ContextLayer, get_bus
    BUS_OK = True
except ImportError:
    BUS_OK = False

try:
    from v110_core import get_v110, CircuitBreakerRegistry
    V110_OK = True
except ImportError:
    V110_OK = False


# ── Couleurs & Style ──────────────────────────────────────────────────
PAL = {
    "bg":       "#050508",
    "canvas":   "#08080F",
    "node_idle":"#1A1A2E",
    "node_run": "#2D1B69",
    "node_ok":  "#0D3B2E",
    "node_err": "#3B0D0D",
    "node_text":"#E0E0F8",
    "edge":     "#2A2A4A",
    "edge_active":"#7C3AED",
    "accent":   "#7C3AED",
    "accent2":  "#A855F7",
    "ok":       "#10B981",
    "warn":     "#F59E0B",
    "err":      "#EF4444",
    "text":     "#E0E0F8",
    "textd":    "#7070A8",
}

# ── Définition du graphe neuronal ────────────────────────────────────

AGENTS = {
    "sourcing":       {"label": "📡 Sourcing",      "layer": 0, "color": "#1A3A5C"},
    "memory":         {"label": "📚 Mémoire",       "layer": 0, "color": "#1A3A5C"},
    "scenario":       {"label": "✍ Scénario",       "layer": 1, "color": "#2D1B69"},
    "storyboard":     {"label": "🎬 Storyboard",    "layer": 2, "color": "#2D1B69"},
    "production":     {"label": "🏭 Production",    "layer": 3, "color": "#3B2800"},
    "detailer":       {"label": "👁 Detailer",      "layer": 3, "color": "#3B2800"},
    "postprod":       {"label": "🎞 Post-prod",     "layer": 4, "color": "#1A2A1A"},
    "3d":             {"label": "🧊 3D/STL",        "layer": 4, "color": "#1A2A1A"},
    "critic":         {"label": "🔍 Critique",      "layer": 5, "color": "#3B1A00"},
    "marketing":      {"label": "📣 Marketing",     "layer": 5, "color": "#1A1A3B"},
    "neural_orch":    {"label": "⬡ Orchestrateur",  "layer": 6, "color": "#4A0E8F"},
    "learning":       {"label": "🧠 Apprenant",     "layer": 6, "color": "#4A0E8F"},
}

EDGES = [
    ("sourcing",    "scenario"),
    ("sourcing",    "memory"),
    ("memory",      "scenario"),
    ("scenario",    "storyboard"),
    ("storyboard",  "production"),
    ("storyboard",  "detailer"),
    ("production",  "critic"),
    ("detailer",    "critic"),
    ("critic",      "postprod"),
    ("postprod",    "marketing"),
    ("postprod",    "3d"),
    ("critic",      "learning"),
    ("learning",    "neural_orch"),
    ("neural_orch", "sourcing"),   # boucle feedback
    ("neural_orch", "scenario"),
    ("neural_orch", "production"),
]


class NeuralGraphVisualizer:
    """Visualiseur du graphe neuronal OverLord."""

    def __init__(self):
        self.root = tk.Tk()
        self.root.title("OverLord V1.10 — Graphe Neuronal")
        self.root.configure(bg=PAL["bg"])
        self.root.geometry("1200x750")
        self.root.minsize(900, 600)

        self._agent_states: dict  = {a: "idle" for a in AGENTS}
        self._agent_scores: dict  = {a: 0.0    for a in AGENTS}
        self._agent_temps:  dict  = {a: 0.7    for a in AGENTS}
        self._active_edges: set   = set()
        self._packets:      list  = []   # particules animées sur les edges
        self._attention:    dict  = {a: 0.0 for a in AGENTS}
        self._node_positions: dict = {}
        self._selected_agent: Optional[str] = None
        self._paused  = False
        self._t       = 0.0
        self._lock    = threading.Lock()

        self._build_ui()
        self._calculate_positions()
        self._start_simulation()
        self._animate()

    def _build_ui(self):
        P = PAL

        # Titlebar
        tb = tk.Frame(self.root, bg=P["bg"], height=42)
        tb.pack(fill="x")
        tb.pack_propagate(False)
        tk.Label(tb, text="  ⬡  OverLord — Graphe Neuronal V1.10",
                 font=("Segoe UI",12,"bold"), bg=P["bg"], fg=P["accent2"]
                 ).pack(side="left", fill="y", padx=8)

        self.lbl_time = tk.Label(tb, text="",
                                  font=("Segoe UI",9), bg=P["bg"], fg=P["textd"])
        self.lbl_time.pack(side="right", padx=14)

        btn_style = {"relief":"flat","bd":0,"cursor":"hand2","padx":10,"pady":4,
                     "bg":P["node_run"],"fg":P["text"],"font":("Segoe UI",9)}
        tk.Button(tb, text="⏸ Pause", command=self._toggle_pause,
                  **btn_style).pack(side="right", padx=4)
        tk.Button(tb, text="🔄 Reset", command=self._reset_states,
                  **btn_style).pack(side="right")

        # Corps
        body = tk.Frame(self.root, bg=P["bg"])
        body.pack(fill="both", expand=True)

        # Canvas principal
        canvas_frame = tk.Frame(body, bg=P["bg"])
        canvas_frame.pack(side="left", fill="both", expand=True)
        self.canvas = tk.Canvas(canvas_frame, bg=P["canvas"],
                                 highlightthickness=0, bd=0)
        self.canvas.pack(fill="both", expand=True)
        self.canvas.bind("<Configure>", lambda e: (
            self._calculate_positions(), self._draw()
        ))
        self.canvas.bind("<Button-1>",  self._on_click)
        self.canvas.bind("<Motion>",    self._on_hover)

        # Panneau de droite (détails + heatmap)
        right = tk.Frame(body, bg=P["bg"], width=280)
        right.pack(side="right", fill="y")
        right.pack_propagate(False)

        # Titre panneau
        tk.Label(right, text="DÉTAILS",
                 font=("Segoe UI",9,"bold"), bg=P["bg"],
                 fg=P["textd"]).pack(anchor="w", padx=10, pady=(10,4))

        # Infos agent sélectionné
        self.detail_frame = tk.Frame(right, bg=PAL["node_idle"],
                                      padx=10, pady=8)
        self.detail_frame.pack(fill="x", padx=8)
        self.lbl_agent  = tk.Label(self.detail_frame, text="Clique sur un agent",
                                    font=("Segoe UI",10,"bold"),
                                    bg=PAL["node_idle"], fg=P["text"], anchor="w")
        self.lbl_agent.pack(fill="x")
        self.lbl_detail = tk.Label(self.detail_frame, text="",
                                    font=("Segoe UI",8),
                                    bg=PAL["node_idle"], fg=P["textd"],
                                    anchor="w", justify="left")
        self.lbl_detail.pack(fill="x")

        # Attention heatmap
        tk.Label(right, text="CARTE D'ATTENTION",
                 font=("Segoe UI",9,"bold"), bg=P["bg"],
                 fg=P["textd"]).pack(anchor="w", padx=10, pady=(16,4))

        self.heat_frame = tk.Frame(right, bg=P["bg"])
        self.heat_frame.pack(fill="x", padx=8)
        self._heat_bars = {}
        for agent_id, info in AGENTS.items():
            row = tk.Frame(self.heat_frame, bg=P["bg"])
            row.pack(fill="x", pady=1)
            tk.Label(row, text=info["label"][:12],
                     font=("Segoe UI",7), bg=P["bg"], fg=P["textd"],
                     width=13, anchor="w").pack(side="left")
            bar_bg = tk.Frame(row, bg=P["node_idle"], height=10, width=120)
            bar_bg.pack(side="left", padx=2)
            bar_bg.pack_propagate(False)
            bar_fill = tk.Frame(bar_bg, bg=P["accent"], height=10, width=0)
            bar_fill.place(x=0, y=0, height=10, width=0)
            self._heat_bars[agent_id] = (bar_bg, bar_fill)

        # Légende
        tk.Label(right, text="LÉGENDE",
                 font=("Segoe UI",9,"bold"), bg=P["bg"],
                 fg=P["textd"]).pack(anchor="w", padx=10, pady=(16,4))
        for color, label in [
            (P["node_idle"],  "Inactif"),
            (P["node_run"],   "En cours"),
            (P["node_ok"],    "Terminé ✓"),
            (P["node_err"],   "Erreur ✗"),
            (P["edge_active"],"Signal actif"),
        ]:
            row = tk.Frame(right, bg=P["bg"])
            row.pack(anchor="w", padx=10, pady=1)
            tk.Frame(row, bg=color, width=14, height=10).pack(side="left", padx=(0,6))
            tk.Label(row, text=label, font=("Segoe UI",8),
                     bg=P["bg"], fg=P["textd"]).pack(side="left")

        # Stats globales
        self.lbl_stats = tk.Label(right, text="",
                                   font=("Segoe UI",8), bg=P["bg"],
                                   fg=P["textd"], justify="left", anchor="w")
        self.lbl_stats.pack(anchor="w", padx=10, pady=(16,0))

    def _calculate_positions(self):
        """Calcule les positions des nœuds selon la couche (layout en colonnes)."""
        w  = self.canvas.winfo_width()  or 900
        h  = self.canvas.winfo_height() or 600
        pad_x = 80; pad_y = 60

        # Grouper par couche
        layers: dict[int, list] = {}
        for aid, info in AGENTS.items():
            l = info["layer"]
            layers.setdefault(l, []).append(aid)

        n_layers = max(layers.keys()) + 1
        col_w    = (w - 2*pad_x) / max(n_layers - 1, 1)

        self._node_positions = {}
        for layer_idx, agents_in_layer in layers.items():
            x = pad_x + layer_idx * col_w
            n = len(agents_in_layer)
            for j, aid in enumerate(agents_in_layer):
                y = pad_y + (j + 0.5) * (h - 2*pad_y) / n
                self._node_positions[aid] = (x, y)

    def _draw(self):
        """Dessine le graphe complet."""
        c  = self.canvas
        c.delete("all")
        w  = c.winfo_width()  or 900
        h  = c.winfo_height() or 600

        if not self._node_positions:
            self._calculate_positions()

        # ── Dessiner les edges ──
        for src, dst in EDGES:
            if src not in self._node_positions or dst not in self._node_positions:
                continue
            x1, y1 = self._node_positions[src]
            x2, y2 = self._node_positions[dst]
            active  = (src, dst) in self._active_edges
            color   = PAL["edge_active"] if active else PAL["edge"]
            width   = 2 if active else 1

            # Courbe de Bézier approximée
            mx = (x1 + x2) / 2 + (y2-y1)*0.1
            my = (y1 + y2) / 2

            c.create_line(x1, y1, mx, my, x2, y2,
                          fill=color, width=width,
                          smooth=True, arrow=tk.LAST,
                          arrowshape=(8,10,4))

        # ── Dessiner les particules (signaux) ──
        with self._lock:
            for pkt in list(self._packets):
                src, dst, t = pkt["src"], pkt["dst"], pkt["t"]
                if src not in self._node_positions or dst not in self._node_positions:
                    continue
                x1,y1 = self._node_positions[src]
                x2,y2 = self._node_positions[dst]
                px = x1 + (x2-x1)*t
                py = y1 + (y2-y1)*t
                r  = 4
                c.create_oval(px-r, py-r, px+r, py+r,
                               fill=PAL["accent2"], outline="")

        # ── Dessiner les nœuds ──
        NODE_W, NODE_H = 110, 44
        for aid, info in AGENTS.items():
            if aid not in self._node_positions:
                continue
            x, y   = self._node_positions[aid]
            state  = self._agent_states.get(aid, "idle")
            score  = self._agent_scores.get(aid, 0.0)
            attn   = self._attention.get(aid, 0.0)
            selected = (aid == self._selected_agent)

            # Couleur selon état
            state_colors = {
                "idle":     info["color"],
                "running":  PAL["node_run"],
                "ok":       PAL["node_ok"],
                "error":    PAL["node_err"],
            }
            bg_color = state_colors.get(state, info["color"])

            # Halo d'attention
            if attn > 0.1:
                halo_r = int(NODE_W//2 + attn * 20)
                halo_a = int(attn * 60)
                c.create_oval(x-halo_r, y-halo_r//2-5,
                               x+halo_r, y+halo_r//2+5,
                               outline=PAL["accent2"],
                               width=max(1, int(attn*3)),
                               fill="")

            # Corps du nœud (rectangle arrondi simulé)
            r = 8
            x0, y0 = x-NODE_W//2, y-NODE_H//2
            x1, y1 = x+NODE_W//2, y+NODE_H//2
            c.create_rectangle(x0+r, y0, x1-r, y1, fill=bg_color, outline="")
            c.create_rectangle(x0, y0+r, x1, y1-r, fill=bg_color, outline="")
            for cx, cy in [(x0+r,y0+r),(x1-r,y0+r),(x0+r,y1-r),(x1-r,y1-r)]:
                c.create_oval(cx-r,cy-r,cx+r,cy+r, fill=bg_color, outline="")

            # Bordure si sélectionné
            if selected:
                c.create_rectangle(x0-2, y0-2, x1+2, y1+2,
                                    outline=PAL["accent2"], width=2, fill="")

            # Label
            c.create_text(x, y-6, text=info["label"],
                          font=("Segoe UI",8,"bold"),
                          fill=PAL["node_text"])

            # Score (barre sous le label)
            if score > 0:
                bar_w   = int((NODE_W-20) * score)
                bar_color = PAL["ok"] if score > 0.75 else PAL["warn"] if score > 0.5 else PAL["err"]
                c.create_rectangle(x-NODE_W//2+10, y+10,
                                    x-NODE_W//2+10+bar_w, y+14,
                                    fill=bar_color, outline="")
                c.create_text(x+NODE_W//2-18, y+12,
                               text=f"{score*100:.0f}",
                               font=("Segoe UI",6), fill=PAL["textd"])

            # Indicateur état
            state_icons = {"idle":"○","running":"●","ok":"✓","error":"✗"}
            icon_colors = {"idle":PAL["textd"],"running":PAL["accent2"],
                           "ok":PAL["ok"],"error":PAL["err"]}
            c.create_text(x+NODE_W//2-8, y-NODE_H//2+8,
                          text=state_icons.get(state,"○"),
                          font=("Segoe UI",8),
                          fill=icon_colors.get(state,PAL["textd"]))

    def _on_click(self, event):
        """Sélectionne un agent au clic."""
        NODE_W, NODE_H = 110, 44
        for aid, (x, y) in self._node_positions.items():
            if (abs(event.x - x) < NODE_W//2 and
                abs(event.y - y) < NODE_H//2):
                self._selected_agent = aid
                self._update_detail_panel(aid)
                return
        self._selected_agent = None
        self.lbl_agent.configure(text="Clique sur un agent")
        self.lbl_detail.configure(text="")

    def _on_hover(self, event):
        """Survol — met en évidence les connexions."""
        pass   # réservé pour une future version

    def _update_detail_panel(self, agent_id: str):
        """Met à jour le panneau de détails."""
        info    = AGENTS.get(agent_id, {})
        state   = self._agent_states.get(agent_id, "idle")
        score   = self._agent_scores.get(agent_id, 0.0)
        temp    = self._agent_temps.get(agent_id, 0.7)
        attn    = self._attention.get(agent_id, 0.0)

        self.lbl_agent.configure(
            text=info.get("label", agent_id),
            bg=info.get("color", PAL["node_idle"])
        )
        self.detail_frame.configure(bg=info.get("color", PAL["node_idle"]))
        self.lbl_detail.configure(
            bg=info.get("color", PAL["node_idle"]),
            text=(
                f"État        : {state.upper()}\n"
                f"Score       : {score*100:.1f}/100\n"
                f"Température : {temp:.2f}\n"
                f"Attention   : {attn:.3f}\n"
                f"Couche      : {AGENTS[agent_id].get('layer',0)}"
            )
        )

    def _update_heatmap(self):
        """Met à jour la heatmap d'attention."""
        max_attn = max(self._attention.values(), default=1.0) or 1.0
        for aid, (bg, fill) in self._heat_bars.items():
            attn  = self._attention.get(aid, 0.0)
            ratio = attn / max_attn
            width = int(120 * ratio)
            color = PAL["accent"] if ratio > 0.5 else PAL["warn"] if ratio > 0.2 else PAL["textd"]
            fill.place(x=0, y=0, height=10, width=width)
            fill.configure(bg=color)

    def _update_stats(self):
        """Met à jour les stats globales."""
        running = sum(1 for s in self._agent_states.values() if s=="running")
        ok      = sum(1 for s in self._agent_states.values() if s=="ok")
        err     = sum(1 for s in self._agent_states.values() if s=="error")
        avg_sc  = sum(self._agent_scores.values()) / max(len(self._agent_scores),1)
        self.lbl_stats.configure(text=(
            f"Actifs  : {running}\n"
            f"Succès  : {ok}\n"
            f"Erreurs : {err}\n"
            f"Score ø : {avg_sc*100:.1f}/100\n"
            f"T : {datetime.now().strftime('%H:%M:%S')}"
        ))

    def _toggle_pause(self):
        self._paused = not self._paused

    def _reset_states(self):
        with self._lock:
            self._agent_states = {a: "idle" for a in AGENTS}
            self._agent_scores = {a: 0.0    for a in AGENTS}
            self._active_edges = set()
            self._packets      = []

    # ── Simulation / Données réelles ──────────────────────────────────

    def _start_simulation(self):
        """Démarre la simulation (ou connexion aux données réelles)."""
        def _loop():
            agents = list(AGENTS.keys())
            while True:
                if self._paused:
                    time.sleep(0.5)
                    continue

                # Si context bus disponible → données réelles
                if BUS_OK:
                    try:
                        bus   = get_bus()
                        snap  = bus.snapshot()
                        atmap = bus.get_attention_map()
                        total_w = sum(a["raw"] for a in atmap) or 1
                        with self._lock:
                            for a in atmap:
                                if a["agent"] in self._attention:
                                    self._attention[a["agent"]] = a["raw"]/total_w
                    except Exception:
                        pass
                else:
                    # Simulation visuelle
                    with self._lock:
                        # Activer aléatoirement quelques agents
                        agent = random.choice(agents)
                        self._agent_states[agent] = "running"
                        self._attention[agent]    = random.uniform(0.3, 1.0)

                        # Edge actif
                        edge = random.choice(EDGES)
                        self._active_edges.add(edge)
                        if len(self._active_edges) > 3:
                            self._active_edges.pop()

                        # Particule
                        if random.random() > 0.3:
                            self._packets.append({
                                "src": edge[0], "dst": edge[1], "t": 0.0
                            })

                        # Terminer aléatoirement des agents
                        if random.random() > 0.7:
                            other = random.choice(agents)
                            if self._agent_states[other] == "running":
                                self._agent_states[other] = "ok"
                                self._agent_scores[other] = random.uniform(0.6, 0.98)
                                self._attention[other]    *= 0.7

                time.sleep(0.4)

        t = threading.Thread(target=_loop, daemon=True)
        t.start()

    def _animate(self):
        """Boucle d'animation principale."""
        if not self._paused:
            self._t += 0.02

            with self._lock:
                # Avancer les particules
                for pkt in self._packets:
                    pkt["t"] += 0.04
                # Supprimer les particules arrivées
                self._packets = [p for p in self._packets if p["t"] < 1.0]

            self._draw()
            self._update_heatmap()
            self._update_stats()

            now = datetime.now().strftime("%H:%M:%S")
            self.lbl_time.configure(text=f"⏱ {now}")

            # Mettre à jour le panneau si agent sélectionné
            if self._selected_agent:
                self._update_detail_panel(self._selected_agent)

        self.root.after(40, self._animate)   # ~25 FPS

    def run(self):
        self.root.mainloop()


if __name__ == "__main__":
    app = NeuralGraphVisualizer()
    app.run()

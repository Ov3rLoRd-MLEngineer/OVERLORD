"""
agents/v110_graph_ui.py — Ov3rLoRd V1.10 — Visualiseur Graphe Neuronal
FIX V1.49k : import context_bus corrige (from agents.context_bus au lieu de from context_bus).
"""

import tkinter as tk
from tkinter import ttk
import sys
import io
import threading
import time
import math
import json
import random
from pathlib import Path
from datetime import datetime
from typing import Optional

if hasattr(sys.stdout, 'buffer') and getattr(sys.stdout,'encoding','').lower() != 'utf-8':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

# FIX : import chemin corrige agents.context_bus
try:
    from agents.context_bus import get_bus
    BUS_OK = True
except ImportError:
    try:
        from context_bus import get_bus
        BUS_OK = True
    except ImportError:
        BUS_OK = False

try:
    from agents.v110_core import get_v110, CircuitBreakerRegistry
    V110_OK = True
except ImportError:
    V110_OK = False

PAL = {
    "bg":         "#050508", "canvas":    "#08080F",
    "node_idle":  "#1A1A2E", "node_run":  "#2D1B69",
    "node_ok":    "#0D3B2E", "node_err":  "#3B0D0D",
    "node_text":  "#E0E0F8", "edge":      "#2A2A4A",
    "edge_active":"#7C3AED", "accent":    "#7C3AED",
    "accent2":    "#A855F7", "ok":        "#10B981",
    "warn":       "#F59E0B", "err":       "#EF4444",
    "text":       "#E0E0F8", "textd":     "#7070A8",
}

# Emojis dans AGENTS : intentionnels (labels de l'interface graphique)
AGENTS = {
    "sourcing":    {"label": "Sourcing",     "layer": 0, "color": "#1A3A5C"},
    "memory":      {"label": "Memoire",      "layer": 0, "color": "#1A3A5C"},
    "scenario":    {"label": "Scenario",     "layer": 1, "color": "#2D1B69"},
    "storyboard":  {"label": "Storyboard",   "layer": 2, "color": "#2D1B69"},
    "production":  {"label": "Production",   "layer": 3, "color": "#3B2800"},
    "detailer":    {"label": "Detailer",     "layer": 3, "color": "#3B2800"},
    "postprod":    {"label": "Post-prod",    "layer": 4, "color": "#1A2A1A"},
    "3d":          {"label": "3D/STL",       "layer": 4, "color": "#1A2A1A"},
    "critic":      {"label": "Critique",     "layer": 5, "color": "#3B1A00"},
    "marketing":   {"label": "Marketing",    "layer": 5, "color": "#1A1A3B"},
    "neural_orch": {"label": "Orchestrateur","layer": 6, "color": "#4A0E8F"},
    "learning":    {"label": "Apprenant",    "layer": 6, "color": "#4A0E8F"},
}

EDGES = [
    ("sourcing","scenario"),   ("sourcing","memory"),
    ("memory","scenario"),     ("scenario","storyboard"),
    ("storyboard","production"),("storyboard","detailer"),
    ("production","critic"),   ("detailer","critic"),
    ("critic","postprod"),     ("postprod","marketing"),
    ("postprod","3d"),         ("critic","learning"),
    ("learning","neural_orch"),("neural_orch","sourcing"),
    ("neural_orch","scenario"),("neural_orch","production"),
]

NODE_W, NODE_H = 110, 44


class NeuralGraphVisualizer:

    def __init__(self):
        self.root = tk.Tk()
        self.root.title("Ov3rLoRd V1.10 — Graphe Neuronal")
        self.root.configure(bg=PAL["bg"])
        self.root.geometry("1200x750")
        self.root.minsize(900, 600)

        self._agent_states:   dict = {a: "idle" for a in AGENTS}
        self._agent_scores:   dict = {a: 0.0    for a in AGENTS}
        self._agent_temps:    dict = {a: 0.7    for a in AGENTS}
        self._active_edges:   set  = set()
        self._packets:        list = []
        self._attention:      dict = {a: 0.0 for a in AGENTS}
        self._node_positions: dict = {}
        self._selected_agent: Optional[str] = None
        self._paused = False
        self._t      = 0.0
        self._lock   = threading.Lock()

        self._build_ui()
        self._calculate_positions()
        self._start_simulation()
        self._animate()

    def _build_ui(self):
        P = PAL
        tb = tk.Frame(self.root, bg=P["bg"], height=42)
        tb.pack(fill="x")
        tb.pack_propagate(False)
        tk.Label(tb, text="  Ov3rLoRd — Graphe Neuronal V1.10",
                 font=("Segoe UI",12,"bold"), bg=P["bg"], fg=P["accent2"]
                 ).pack(side="left", fill="y", padx=8)
        self.lbl_time = tk.Label(tb, text="", font=("Segoe UI",9),
                                  bg=P["bg"], fg=P["textd"])
        self.lbl_time.pack(side="right", padx=14)
        btn_style = {"relief":"flat","bd":0,"cursor":"hand2","padx":10,"pady":4,
                     "bg":P["node_run"],"fg":P["text"],"font":("Segoe UI",9)}
        tk.Button(tb, text="Pause", command=self._toggle_pause,
                  **btn_style).pack(side="right", padx=4)
        tk.Button(tb, text="Reset", command=self._reset_states,
                  **btn_style).pack(side="right")

        body = tk.Frame(self.root, bg=P["bg"])
        body.pack(fill="both", expand=True)

        canvas_frame = tk.Frame(body, bg=P["bg"])
        canvas_frame.pack(side="left", fill="both", expand=True)
        self.canvas = tk.Canvas(canvas_frame, bg=P["canvas"],
                                 highlightthickness=0, bd=0)
        self.canvas.pack(fill="both", expand=True)
        self.canvas.bind("<Configure>", lambda e: (
            self._calculate_positions(), self._draw()
        ))
        self.canvas.bind("<Button-1>", self._on_click)

        right = tk.Frame(body, bg=P["bg"], width=280)
        right.pack(side="right", fill="y")
        right.pack_propagate(False)

        tk.Label(right, text="DETAILS", font=("Segoe UI",9,"bold"),
                 bg=P["bg"], fg=P["textd"]).pack(anchor="w", padx=10, pady=(10,4))
        self.detail_frame = tk.Frame(right, bg=PAL["node_idle"], padx=10, pady=8)
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

        tk.Label(right, text="CARTE D'ATTENTION", font=("Segoe UI",9,"bold"),
                 bg=P["bg"], fg=P["textd"]).pack(anchor="w", padx=10, pady=(16,4))
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
            fill_bar = tk.Frame(bar_bg, bg=P["accent"], height=10, width=0)
            fill_bar.place(x=0, y=0, height=10, width=0)
            self._heat_bars[agent_id] = (bar_bg, fill_bar)

        tk.Label(right, text="STATS", font=("Segoe UI",9,"bold"),
                 bg=P["bg"], fg=P["textd"]).pack(anchor="w", padx=10, pady=(16,4))
        self.lbl_stats = tk.Label(right, text="", font=("Segoe UI",8),
                                   bg=P["bg"], fg=P["text"],
                                   anchor="w", justify="left")
        self.lbl_stats.pack(anchor="w", padx=10)

    def _calculate_positions(self):
        w = self.canvas.winfo_width()  or 900
        h = self.canvas.winfo_height() or 650
        layers   = {}
        for aid, info in AGENTS.items():
            l = info["layer"]
            layers.setdefault(l,[]).append(aid)
        n_layers = max(layers.keys()) + 1
        for layer_idx, agents_in_layer in layers.items():
            x = int(w * (layer_idx + 0.5) / n_layers)
            n = len(agents_in_layer)
            for i, aid in enumerate(agents_in_layer):
                y = int(h * (i + 0.5) / n)
                self._node_positions[aid] = (x, y)

    def _draw(self):
        c = self.canvas
        c.delete("all")
        # Aretes
        for src, dst in EDGES:
            if src not in self._node_positions or dst not in self._node_positions:
                continue
            x1,y1 = self._node_positions[src]
            x2,y2 = self._node_positions[dst]
            active = (src,dst) in self._active_edges
            color  = PAL["edge_active"] if active else PAL["edge"]
            width  = 2 if active else 1
            c.create_line(x1,y1,x2,y2, fill=color, width=width, smooth=True)

        # Particules
        with self._lock:
            packets = list(self._packets)
        for pkt in packets:
            if pkt["src"] not in self._node_positions:
                continue
            if pkt["dst"] not in self._node_positions:
                continue
            x1,y1 = self._node_positions[pkt["src"]]
            x2,y2 = self._node_positions[pkt["dst"]]
            t = pkt["t"]
            px = x1 + (x2-x1)*t
            py = y1 + (y2-y1)*t
            c.create_oval(px-4,py-4,px+4,py+4, fill=PAL["accent2"], outline="")

        # Noeuds
        for aid, (x,y) in self._node_positions.items():
            info     = AGENTS[aid]
            state    = self._agent_states.get(aid,"idle")
            score    = self._agent_scores.get(aid,0.0)
            selected = self._selected_agent == aid
            attn     = self._attention.get(aid,0.0)

            state_colors = {
                "idle":    info["color"],
                "running": PAL["node_run"],
                "ok":      PAL["node_ok"],
                "error":   PAL["node_err"],
            }
            bg_color = state_colors.get(state, info["color"])
            if attn > 0.5:
                r_val = min(255, int(int(bg_color[1:3],16)*1.3))
                bg_color = f"#{r_val:02x}{bg_color[3:]}"

            x0,y0 = x-NODE_W//2, y-NODE_H//2
            x1b,y1b = x+NODE_W//2, y+NODE_H//2
            r = 8
            c.create_rectangle(x0+r,y0, x1b-r,y1b, fill=bg_color, outline="")
            c.create_rectangle(x0,y0+r, x1b,y1b-r, fill=bg_color, outline="")
            for cx,cy in [(x0+r,y0+r),(x1b-r,y0+r),(x0+r,y1b-r),(x1b-r,y1b-r)]:
                c.create_oval(cx-r,cy-r,cx+r,cy+r, fill=bg_color, outline="")
            if selected:
                c.create_rectangle(x0-2,y0-2,x1b+2,y1b+2,
                                    outline=PAL["accent2"],width=2,fill="")
            c.create_text(x,y-6, text=info["label"],
                          font=("Segoe UI",8,"bold"), fill=PAL["node_text"])
            if score > 0:
                bar_w    = int((NODE_W-20)*score)
                bar_col  = PAL["ok"] if score>0.75 else PAL["warn"] if score>0.5 else PAL["err"]
                c.create_rectangle(x-NODE_W//2+10,y+10, x-NODE_W//2+10+bar_w,y+14,
                                    fill=bar_col,outline="")
            state_icons = {"idle":"o","running":"*","ok":"+","error":"x"}
            icon_colors = {"idle":PAL["textd"],"running":PAL["accent2"],
                           "ok":PAL["ok"],"error":PAL["err"]}
            c.create_text(x+NODE_W//2-8,y-NODE_H//2+8,
                          text=state_icons.get(state,"o"),
                          font=("Segoe UI",8),
                          fill=icon_colors.get(state,PAL["textd"]))

    def _on_click(self, event):
        for aid,(x,y) in self._node_positions.items():
            if abs(event.x-x)<NODE_W//2 and abs(event.y-y)<NODE_H//2:
                self._selected_agent = aid
                self._update_detail_panel(aid)
                return
        self._selected_agent = None
        self.lbl_agent.configure(text="Clique sur un agent")
        self.lbl_detail.configure(text="")

    def _update_detail_panel(self, agent_id: str):
        info  = AGENTS.get(agent_id,{})
        state = self._agent_states.get(agent_id,"idle")
        score = self._agent_scores.get(agent_id,0.0)
        temp  = self._agent_temps.get(agent_id,0.7)
        attn  = self._attention.get(agent_id,0.0)
        self.lbl_agent.configure(text=info.get("label",agent_id),
                                  bg=info.get("color",PAL["node_idle"]))
        self.detail_frame.configure(bg=info.get("color",PAL["node_idle"]))
        self.lbl_detail.configure(
            bg=info.get("color",PAL["node_idle"]),
            text=(f"Etat        : {state.upper()}\n"
                  f"Score       : {score*100:.1f}/100\n"
                  f"Temperature : {temp:.2f}\n"
                  f"Attention   : {attn:.3f}\n"
                  f"Couche      : {AGENTS[agent_id].get('layer',0)}")
        )

    def _update_heatmap(self):
        max_attn = max(self._attention.values(), default=1.0) or 1.0
        for aid,(bg,fill) in self._heat_bars.items():
            attn  = self._attention.get(aid,0.0)
            ratio = attn / max_attn
            width = int(120*ratio)
            color = PAL["accent"] if ratio>0.5 else PAL["warn"] if ratio>0.2 else PAL["textd"]
            fill.place(x=0,y=0,height=10,width=width)
            fill.configure(bg=color)

    def _update_stats(self):
        running = sum(1 for s in self._agent_states.values() if s=="running")
        ok      = sum(1 for s in self._agent_states.values() if s=="ok")
        err     = sum(1 for s in self._agent_states.values() if s=="error")
        avg_sc  = sum(self._agent_scores.values()) / max(len(self._agent_scores),1)
        self.lbl_stats.configure(text=(
            f"Actifs  : {running}\n"
            f"Succes  : {ok}\n"
            f"Erreurs : {err}\n"
            f"Score o : {avg_sc*100:.1f}/100\n"
            f"T : {datetime.now().strftime('%H:%M:%S')}"
        ))

    def _toggle_pause(self):
        self._paused = not self._paused

    def _reset_states(self):
        with self._lock:
            self._agent_states = {a:"idle" for a in AGENTS}
            self._agent_scores = {a:0.0    for a in AGENTS}
            self._active_edges = set()
            self._packets      = []

    def _start_simulation(self):
        def _loop():
            agents = list(AGENTS.keys())
            while True:
                if self._paused:
                    time.sleep(0.5)
                    continue
                if BUS_OK:
                    try:
                        bus  = get_bus()
                        snap = bus.snapshot() if hasattr(bus,"snapshot") else {}
                        atmap = bus.get_attention_map() if hasattr(bus,"get_attention_map") else []
                        total_w = sum(a.get("raw",0) for a in atmap) or 1
                        with self._lock:
                            for a in atmap:
                                if a.get("agent","") in self._attention:
                                    self._attention[a["agent"]] = a.get("raw",0)/total_w
                    except Exception:
                        pass
                else:
                    with self._lock:
                        agent = random.choice(agents)
                        self._agent_states[agent] = "running"
                        self._attention[agent]    = random.uniform(0.3,1.0)
                        edge = random.choice(EDGES)
                        self._active_edges.add(edge)
                        if len(self._active_edges) > 3:
                            self._active_edges.pop()
                        if random.random() > 0.3:
                            self._packets.append({"src":edge[0],"dst":edge[1],"t":0.0})
                        if random.random() > 0.7:
                            other = random.choice(agents)
                            if self._agent_states[other] == "running":
                                self._agent_states[other] = "ok"
                                self._agent_scores[other] = random.uniform(0.6,0.98)
                                self._attention[other]   *= 0.7
                time.sleep(0.4)

        threading.Thread(target=_loop, daemon=True).start()

    def _animate(self):
        if not self._paused:
            self._t += 0.02
            with self._lock:
                for pkt in self._packets:
                    pkt["t"] += 0.04
                self._packets = [p for p in self._packets if p["t"] < 1.0]
            self._draw()
            self._update_heatmap()
            self._update_stats()
            self.lbl_time.configure(text=datetime.now().strftime("%H:%M:%S"))
            if self._selected_agent:
                self._update_detail_panel(self._selected_agent)
        self.root.after(40, self._animate)

    def run(self):
        self.root.mainloop()


if __name__ == "__main__":
    app = NeuralGraphVisualizer()
    app.run()
"""
agents/v120_dashboard.py — OverLord V1.20 — Dashboard Unifié
Interface tout-en-un pour superviser l'ensemble du pipeline V1.20.

Onglets :
  🧠 Neural     — Context Bus, Constitution, Orchestrateur
  🎯 MoE        — Mixture of Experts, Sparse Attention, RoPE
  📈 Learning   — Reward, Policy Gradient, Experience Replay, Curriculum
  🛡 Alignment  — CAI, Débat, Incertitude, Anomalies
  👥 Collective  — Parlement, Nouveaux Agents
  🎬 Generation  — Scheduler, LoRA, Cohérence, Temporel
  📊 Metrics    — Toutes les métriques en temps réel
  💬 Agent Chat  — Discuter avec n'importe quel agent
"""

import json
import sys
import threading
import time
import queue
import tkinter as tk
from tkinter import ttk
from pathlib import Path
from datetime import datetime
from typing import Optional
import requests

# Imports V1.20
sys.path.insert(0, str(Path(__file__).parent))

ANTHROPIC_URL = "https://api.anthropic.com/v1/messages"
CLAUDE_MODEL  = "claude-sonnet-4-6"

PAL = {
    "bg":      "#050508",
    "surf":    "#0C0C18",
    "surf2":   "#14142A",
    "surf3":   "#1E1E38",
    "border":  "#2A2A50",
    "accent":  "#7C3AED",
    "accent2": "#A855F7",
    "ok":      "#10B981",
    "warn":    "#F59E0B",
    "err":     "#EF4444",
    "text":    "#E0E0F8",
    "textd":   "#7070A8",
    "textm":   "#404068",
    "btn":     "#7C3AED",
    "btnfg":   "#FFFFFF",
    "logbg":   "#020208",
    "logfg":   "#A0FFA8",
}

AGENT_CHATS = {
    "🧠 Orchestrateur":      "neural_orchestrator",
    "🎬 Career Manager":     "career_manager",
    "📰 Attaché de Presse":  "press_attache",
    "🔬 Innovateur":         "structural_innovator",
    "💰 Monétisation":       "monetization",
    "⚖️ Conformité Légale":  "legal_compliance",
    "🔭 Talent Scout":       "talent_scout",
    "🧬 Agent Legacy":       "legacy_successor",
    "📚 Mémoire":            "memory_archivist",
    "🎭 Marketing":          "marketing_strategist",
    "🌐 Webmaster":          "webmaster",
    "💫 Community Mgr":      "community_manager",
}


def _llm_chat(agent_role: str, message: str,
              context: dict = None) -> str:
    """Appel LLM pour le chat d'agent."""
    from agents.roles_registry import get_system_prompt
    system = get_system_prompt(agent_role) if agent_role else ""

    if not system:
        system = (
            f"Tu es l'agent '{agent_role}' d'OverLord Pipeline V1.20. "
            f"Tu réponds en te basant sur tes compétences spécialisées."
        )
    if context:
        system += f"\n\nContexte actuel du pipeline : {json.dumps(context, ensure_ascii=False)[:500]}"

    try:
        r = requests.post(
            ANTHROPIC_URL,
            headers={"Content-Type": "application/json"},
            json={"model": CLAUDE_MODEL, "max_tokens": 600,
                  "system": system,
                  "messages": [{"role": "user", "content": message}]},
            timeout=30
        )
        if r.status_code == 200:
            return r.json()["content"][0]["text"].strip()
    except Exception as e:
        return f"[Erreur connexion LLM: {e}]"
    return "[Réponse non disponible]"


class V120Dashboard:
    """Dashboard unifié OverLord V1.20."""

    def __init__(self):
        self._q       = queue.Queue()
        self._running = True
        self._chat_agent = "neural_orchestrator"
        self._metrics = {
            "moe_calls":        0,
            "parliament_votes": 0,
            "cai_revisions":    0,
            "learning_episodes":0,
            "curriculum_level": 1,
            "anomalies":        0,
            "consistency_score":1.0,
            "context_entries":  0,
            "new_agents":       6,
        }
        self._chat_history: list[tuple] = []
        self._build_window()
        self._build_ui()
        self._apply_theme()
        self._start_metrics_updater()
        self._poll()

    def _build_window(self):
        self.root = tk.Tk()
        self.root.title("OverLord V1.20 — Dashboard Neuronal Unifié")
        sw = self.root.winfo_screenwidth()
        sh = self.root.winfo_screenheight()
        self.root.geometry(f"1200x800+{(sw-1200)//2}+{(sh-800)//2}")
        self.root.minsize(900, 600)
        self.root.configure(bg=PAL["bg"])
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)

    def _build_ui(self):
        P = PAL

        # ── Titlebar ──
        tb = tk.Frame(self.root, bg=P["surf"], height=48)
        tb.pack(fill="x")
        tb.pack_propagate(False)
        tk.Label(tb, text="  ⬡  OverLord Pipeline V1.20 — Dashboard Unifié",
                 font=("Segoe UI",12,"bold"), bg=P["surf"], fg=P["accent2"]
                 ).pack(side="left", fill="y", padx=8)
        self.lbl_ts = tk.Label(tb, text="", font=("Segoe UI",8),
                                bg=P["surf"], fg=P["textd"])
        self.lbl_ts.pack(side="right", padx=14)

        # ── Notebook ──
        style = ttk.Style()
        style.configure("V120.TNotebook", background=P["bg"], borderwidth=0)
        style.configure("V120.TNotebook.Tab",
                         background=P["surf2"], foreground=P["textd"],
                         padding=[10,5], font=("Segoe UI",9))
        style.map("V120.TNotebook.Tab",
                  background=[("selected",P["accent"])],
                  foreground=[("selected","#FFFFFF")])

        self.nb = ttk.Notebook(self.root, style="V120.TNotebook")
        self.nb.pack(fill="both", expand=True, padx=4, pady=4)

        # Créer les onglets
        self._tabs = {}
        tabs_def = [
            ("🧠 Neural",     self._build_neural_tab),
            ("🎯 MoE",        self._build_moe_tab),
            ("📈 Learning",   self._build_learning_tab),
            ("🛡 Alignment",  self._build_alignment_tab),
            ("👥 Collective", self._build_collective_tab),
            ("🎬 Generation", self._build_generation_tab),
            ("📊 Métriques",  self._build_metrics_tab),
            ("💬 Agent Chat", self._build_chat_tab),
        ]
        for tab_name, builder in tabs_def:
            frame = tk.Frame(self.nb, bg=P["bg"])
            self.nb.add(frame, text=tab_name)
            self._tabs[tab_name] = frame
            builder(frame)

    # ── Onglets ───────────────────────────────────────────────────────

    def _build_neural_tab(self, f):
        self._section(f, "⬡ Architecture Neuronale V1.20")
        cards = [
            ("Context Bus",    "Mémoire partagée temps réel\nEntrées actives : —\nPoids max : —"),
            ("Constitution",   "Valeurs + Résolution conflits\nRègles actives : 9\nViolations : 0"),
            ("Orchestrateur",  "MHA + CoT + RLHF\nRuns traités : —\nScore moyen : —"),
            ("Thought Chain",  "Raisonnement visible\nÉtapes enregistrées : —"),
        ]
        self._card_grid(f, cards)
        self._log_widget(f, "neural_log")

    def _build_moe_tab(self, f):
        self._section(f, "🎯 Mixture of Experts V1.20")
        cards = [
            ("Experts actifs",    "6 experts spécialisés\nTop K = 2\nConsultations : —"),
            ("Sparse Attention",  "Fenêtre : 20 + 5 globaux\nComplexité : O(N×log N)"),
            ("RoPE",              "Position temporelle\nSession : —min\nPhase : —"),
            ("Flash Attention",   "Tiles : 16 entrées\nDomaines : —\nHits cache : —"),
        ]
        self._card_grid(f, cards)
        # Rankings MoE
        tk.Label(f, text="Rankings Experts",
                 font=("Segoe UI",9,"bold"), bg=PAL["bg"], fg=PAL["textd"]
                 ).pack(anchor="w", padx=14, pady=(8,2))
        self.moe_list = tk.Text(f, height=5, font=("Consolas",8),
                                 bg=PAL["surf2"], fg=PAL["text"],
                                 relief="flat", state="disabled")
        self.moe_list.pack(fill="x", padx=14, pady=(0,8))
        self._update_moe_list()

    def _update_moe_list(self):
        experts = [
            ("narrative_master", 0.85, 0.82, 12),
            ("visual_director",  0.90, 0.88, 18),
            ("tech_optimizer",   0.80, 0.79, 9),
            ("trend_analyst",    0.75, 0.71, 7),
            ("quality_critic",   0.88, 0.86, 15),
            ("creative_innovator",0.78,0.74,11),
        ]
        self.moe_list.configure(state="normal")
        self.moe_list.delete("1.0","end")
        for name, w, sr, nc in sorted(experts, key=lambda x:-x[1]):
            bar = "█" * int(w*15) + "░" * (15-int(w*15))
            self.moe_list.insert("end",
                f"  {name:<22} [{bar}] w={w:.2f} sr={sr:.2f} calls={nc}\n")
        self.moe_list.configure(state="disabled")

    def _build_learning_tab(self, f):
        self._section(f, "📈 Système d'Apprentissage V1.20")
        cards = [
            ("Reward Shaping",    "γ = 0.95\nSignaux émis : —\nRécompense totale : —"),
            ("Policy Gradient",   "lr = 0.05\nPolicies : —\nMeilleur sampler : —"),
            ("Experience Replay", "Buffer : 0/2000\nQualité moy. : —\nRejeux : —"),
            ("Curriculum",        "Niveau actuel : 1/5\nNom : Débutant\nRuns : —"),
        ]
        self._card_grid(f, cards)
        # Barre de progression curriculum
        tk.Label(f, text="Progression Curriculum",
                 font=("Segoe UI",9,"bold"), bg=PAL["bg"], fg=PAL["textd"]
                 ).pack(anchor="w", padx=14, pady=(8,2))
        levels_frame = tk.Frame(f, bg=PAL["bg"])
        levels_frame.pack(fill="x", padx=14)
        levels = ["Débutant","Intermédiaire","Avancé","Expert","Maître"]
        self._curr_labels = []
        for i, lv in enumerate(levels):
            cell = tk.Frame(levels_frame, bg=PAL["surf3"], padx=8, pady=4)
            cell.pack(side="left", expand=True, fill="x", padx=2)
            lbl = tk.Label(cell, text=f"{i+1}. {lv}",
                           font=("Segoe UI",7), bg=PAL["surf3"], fg=PAL["textd"])
            lbl.pack()
            self._curr_labels.append((cell, lbl))
        # Marquer le niveau actuel
        self._curr_labels[0][0].configure(bg=PAL["accent"])
        self._curr_labels[0][1].configure(bg=PAL["accent"], fg="white")
        self._log_widget(f, "learning_log")

    def _build_alignment_tab(self, f):
        self._section(f, "🛡 Alignement & Safety V1.20")
        cards = [
            ("Constitutional AI", "Critiques : 0\nAméliorations : 0\nTaux : —%"),
            ("Debate Protocol",   "Débats : 0\nConsensus : —\nConfiance : —"),
            ("Uncertainty",       "ECE : —\nSurconfiance : —\nCalibrés : —"),
            ("Anomaly Detection", "Métriques : 0\nAnomalies : 0\nSanté : ✓"),
        ]
        self._card_grid(f, cards)
        tk.Label(f, text="Anomalies récentes",
                 font=("Segoe UI",9,"bold"), bg=PAL["bg"], fg=PAL["textd"]
                 ).pack(anchor="w", padx=14, pady=(8,2))
        self.anomaly_text = tk.Text(f, height=4, font=("Consolas",8),
                                     bg=PAL["surf2"], fg=PAL["warn"],
                                     relief="flat", state="disabled")
        self.anomaly_text.pack(fill="x", padx=14, pady=(0,8))
        self.anomaly_text.configure(state="normal")
        self.anomaly_text.insert("end", "  aucune anomalie détectée\n")
        self.anomaly_text.configure(state="disabled")

    def _build_collective_tab(self, f):
        self._section(f, "👥 Intelligence Collective V1.20")
        cards = [
            ("Parlement",          "Votes : 0\nDernière décision : —\nConsensus : —"),
            ("Communication",      "Vocabulaire : 0 tokens\nCompressions : 0"),
            ("Nouveaux Agents",    "6 agents métier\nCarrière, Presse, Innovation\nMonétisation, Légal, Scout"),
            ("Spécialisation",     "Auto-adaptation active\nExperts : 6\nTop expert : —"),
        ]
        self._card_grid(f, cards)
        # Liste des nouveaux agents
        tk.Label(f, text="Nouveaux Agents Disponibles",
                 font=("Segoe UI",9,"bold"), bg=PAL["bg"], fg=PAL["textd"]
                 ).pack(anchor="w", padx=14, pady=(8,2))
        agents_grid = tk.Frame(f, bg=PAL["bg"])
        agents_grid.pack(fill="x", padx=14)
        new_agents = [
            ("🎬", "Career Manager",    "Stratégie artistique"),
            ("📰", "Attaché de Presse","Image médiatique"),
            ("🔬", "Innovateur",        "Architecture future"),
            ("💰", "Monétisation",      "Revenus & ROI"),
            ("⚖️", "Légal",            "Conformité & droits"),
            ("🔭", "Talent Scout",      "Veille & benchmark"),
        ]
        for i, (icon, name, desc) in enumerate(new_agents):
            col = i % 3
            row = i // 3
            card = tk.Frame(agents_grid, bg=PAL["surf2"], padx=10, pady=8)
            card.grid(row=row, column=col, padx=4, pady=4, sticky="ew")
            agents_grid.columnconfigure(col, weight=1)
            tk.Label(card, text=f"{icon} {name}",
                     font=("Segoe UI",8,"bold"),
                     bg=PAL["surf2"], fg=PAL["accent2"]).pack(anchor="w")
            tk.Label(card, text=desc, font=("Segoe UI",7),
                     bg=PAL["surf2"], fg=PAL["textd"]).pack(anchor="w")

    def _build_generation_tab(self, f):
        self._section(f, "🎬 Génération Avancée V1.20")
        cards = [
            ("Diffusion Scheduler","Types connus : 10\nAppris : 0\nQualité moy : —"),
            ("LoRA Composer",      "Catalog : 13 LoRAs\nMax combo : 4\nConflits : 0"),
            ("Style Consistency",  "Signature : non définie\nShots : 0\nCohérence : —"),
            ("Temporal Coherence", "Frames : 0\nErreurs : 0\nTaux : —%"),
        ]
        self._card_grid(f, cards)
        tk.Label(f, text="Résolutions disponibles",
                 font=("Segoe UI",9,"bold"), bg=PAL["bg"], fg=PAL["textd"]
                 ).pack(anchor="w", padx=14, pady=(8,2))
        res_frame = tk.Frame(f, bg=PAL["bg"])
        res_frame.pack(fill="x", padx=14)
        resolutions = [
            ("Portrait V",   "832×1216", "TikTok/Stories"),
            ("Portrait HD",  "896×1152", "Portrait standard"),
            ("Landscape",    "1216×832", "YouTube"),
            ("Square",       "1024×1024","Instagram"),
            ("Wide",         "1344×768", "16:9/Cinéma"),
            ("Poster",       "896×1536", "Affiche/Print"),
        ]
        for i, (name, res, platform) in enumerate(resolutions):
            col = i % 3
            row = i // 3
            card = tk.Frame(res_frame, bg=PAL["surf3"], padx=8, pady=6)
            card.grid(row=row, column=col, padx=3, pady=3, sticky="ew")
            res_frame.columnconfigure(col, weight=1)
            tk.Label(card, text=name, font=("Segoe UI",8,"bold"),
                     bg=PAL["surf3"], fg=PAL["text"]).pack(anchor="w")
            tk.Label(card, text=res, font=("Consolas",9),
                     bg=PAL["surf3"], fg=PAL["accent2"]).pack(anchor="w")
            tk.Label(card, text=platform, font=("Segoe UI",7),
                     bg=PAL["surf3"], fg=PAL["textd"]).pack(anchor="w")

    def _build_metrics_tab(self, f):
        self._section(f, "📊 Métriques Temps Réel")
        # Grid de stats
        self._metric_vars = {}
        stats_def = [
            ("moe_calls",        "🎯 Appels MoE",        "0"),
            ("parliament_votes", "👥 Votes Parlement",   "0"),
            ("cai_revisions",    "🛡 Révisions CAI",     "0"),
            ("learning_episodes","📈 Épisodes Learning", "0"),
            ("curriculum_level", "🎓 Niveau Curriculum", "1/5"),
            ("anomalies",        "⚠️ Anomalies",         "0"),
            ("consistency_score","🎬 Cohérence Style",   "100%"),
            ("context_entries",  "🧠 Context Bus",       "0 entrées"),
            ("new_agents",       "👤 Nouveaux Agents",   "6"),
        ]
        grid_f = tk.Frame(f, bg=PAL["bg"])
        grid_f.pack(fill="both", expand=True, padx=14, pady=8)
        cols = 3
        for i, (key, label, default) in enumerate(stats_def):
            row = i // cols; col = i % cols
            card = tk.Frame(grid_f, bg=PAL["surf2"], padx=16, pady=12)
            card.grid(row=row, column=col, padx=6, pady=6, sticky="ew")
            grid_f.columnconfigure(col, weight=1)
            tk.Label(card, text=label, font=("Segoe UI",8),
                     bg=PAL["surf2"], fg=PAL["textd"]).pack(anchor="w")
            var = tk.StringVar(value=default)
            self._metric_vars[key] = var
            tk.Label(card, textvariable=var,
                     font=("Segoe UI",16,"bold"),
                     bg=PAL["surf2"], fg=PAL["accent2"]).pack(anchor="w")

        # Log global
        tk.Label(f, text="Journal global", font=("Segoe UI",9,"bold"),
                 bg=PAL["bg"], fg=PAL["textd"]).pack(anchor="w", padx=14, pady=(8,2))
        self.global_log = tk.Text(f, height=8, font=("Consolas",8),
                                   bg=PAL["logbg"], fg=PAL["logfg"],
                                   relief="flat", state="disabled")
        self.global_log.pack(fill="both", expand=True, padx=14, pady=(0,8))

    def _build_chat_tab(self, f):
        """Onglet de dialogue avec les agents."""
        P = PAL
        # Sélecteur d'agent
        top = tk.Frame(f, bg=P["bg"])
        top.pack(fill="x", padx=14, pady=8)
        tk.Label(top, text="Agent :", font=("Segoe UI",9),
                 bg=P["bg"], fg=P["textd"]).pack(side="left")
        self._chat_agent_var = tk.StringVar(value="🧠 Orchestrateur")
        agent_combo = ttk.Combobox(top, textvariable=self._chat_agent_var,
                                    values=list(AGENT_CHATS.keys()),
                                    state="readonly", font=("Segoe UI",9), width=22)
        agent_combo.pack(side="left", padx=8)
        agent_combo.bind("<<ComboboxSelected>>",
                         lambda e: setattr(self, "_chat_agent",
                                           AGENT_CHATS[self._chat_agent_var.get()]))

        # Zone de messages
        msg_frame = tk.Frame(f, bg=P["bg"])
        msg_frame.pack(fill="both", expand=True, padx=14)
        self.chat_box = tk.Text(msg_frame, font=("Segoe UI",9),
                                 bg=P["surf2"], fg=P["text"],
                                 relief="flat", wrap="word",
                                 state="disabled")
        chat_sc = tk.Scrollbar(msg_frame, command=self.chat_box.yview)
        self.chat_box.configure(yscrollcommand=chat_sc.set)
        chat_sc.pack(side="right", fill="y")
        self.chat_box.pack(fill="both", expand=True)
        self.chat_box.tag_config("user", foreground=P["accent2"],
                                  font=("Segoe UI",9,"bold"))
        self.chat_box.tag_config("agent", foreground=P["ok"])
        self.chat_box.tag_config("ts",    foreground=P["textm"])
        self._chat_append("🤖", "Sélectionne un agent et pose-lui une question.", "agent")

        # Input
        inp_frame = tk.Frame(f, bg=P["surf"], height=70)
        inp_frame.pack(fill="x", padx=14, pady=6)
        inp_frame.pack_propagate(False)
        self._chat_input = tk.Text(inp_frame, height=3, font=("Segoe UI",9),
                                    bg=P["surf3"], fg=P["text"],
                                    relief="flat", insertbackground=P["text"],
                                    wrap="word")
        self._chat_input.pack(fill="both", expand=True, padx=6, pady=6)
        self._chat_input.bind("<Return>", self._on_chat_enter)
        self._chat_input.bind("<Shift-Return>", lambda e: None)
        self.lbl_typing = tk.Label(f, text="",
                                    font=("Segoe UI",8), bg=P["bg"], fg=P["textd"])
        self.lbl_typing.pack(anchor="w", padx=14)
        tk.Button(f, text="Envoyer ↵", bg=P["btn"], fg=P["btnfg"],
                  font=("Segoe UI",9,"bold"), relief="flat", bd=0,
                  cursor="hand2", padx=14, pady=5,
                  command=self._send_chat).pack(anchor="e", padx=14, pady=4)

    def _on_chat_enter(self, e):
        if not (e.state & 1):
            self._send_chat(); return "break"

    def _send_chat(self):
        text = self._chat_input.get("1.0","end").strip()
        if not text: return
        self._chat_input.delete("1.0","end")
        agent_label = self._chat_agent_var.get()
        agent_id    = AGENT_CHATS.get(agent_label, "neural_orchestrator")
        self._chat_append("Vous", text, "user")
        self.lbl_typing.configure(text=f"⏳ {agent_label} réfléchit…")
        def _run():
            resp = _llm_chat(agent_id, text)
            self._q.put(("chat_response", (agent_label, resp)))
        threading.Thread(target=_run, daemon=True).start()

    def _chat_append(self, who: str, text: str, tag: str = "agent"):
        ts = datetime.now().strftime("%H:%M")
        self.chat_box.configure(state="normal")
        self.chat_box.insert("end", f"[{ts}] {who}\n", "ts")
        self.chat_box.insert("end", text + "\n\n", tag)
        self.chat_box.see("end")
        self.chat_box.configure(state="disabled")

    # ── Widgets helpers ───────────────────────────────────────────────

    def _section(self, f: tk.Frame, title: str):
        hdr = tk.Frame(f, bg=PAL["bg"])
        hdr.pack(fill="x", padx=14, pady=(10,4))
        tk.Label(hdr, text=title, font=("Segoe UI",10,"bold"),
                 bg=PAL["bg"], fg=PAL["accent2"]).pack(side="left")
        tk.Frame(hdr, height=1, bg=PAL["border"]).pack(fill="x", pady=(6,0))

    def _card_grid(self, f: tk.Frame, cards: list[tuple]):
        grid = tk.Frame(f, bg=PAL["bg"])
        grid.pack(fill="x", padx=14, pady=4)
        for i, (title, text) in enumerate(cards):
            card = tk.Frame(grid, bg=PAL["surf2"], padx=10, pady=8)
            card.grid(row=0, column=i, padx=4, sticky="ew")
            grid.columnconfigure(i, weight=1)
            tk.Label(card, text=title, font=("Segoe UI",8,"bold"),
                     bg=PAL["surf2"], fg=PAL["accent2"]).pack(anchor="w")
            tk.Label(card, text=text, font=("Segoe UI",7),
                     bg=PAL["surf2"], fg=PAL["textd"],
                     justify="left").pack(anchor="w")

    def _log_widget(self, f: tk.Frame, name: str):
        lf = tk.Frame(f, bg=PAL["bg"])
        lf.pack(fill="both", expand=True, padx=14, pady=4)
        log = tk.Text(lf, height=5, font=("Consolas",8),
                       bg=PAL["logbg"], fg=PAL["logfg"],
                       relief="flat", state="disabled")
        log.pack(fill="both", expand=True)
        setattr(self, name, log)
        return log

    # ── Thème ─────────────────────────────────────────────────────────

    def _apply_theme(self):
        P = PAL
        def _recurse(w):
            try:
                cls = w.winfo_class()
                if cls in ("Frame","Labelframe"):
                    w.configure(bg=P["bg"])
                elif cls == "Label":
                    w.configure(bg=P.get("bg","#050508"))
                elif cls == "Text":
                    w.configure(insertbackground=P["text"])
            except Exception: pass
            for ch in w.winfo_children():
                _recurse(ch)
        _recurse(self.root)

    # ── Métriques ─────────────────────────────────────────────────────

    def _start_metrics_updater(self):
        def _loop():
            t = 0
            while self._running:
                t += 1
                # Simuler des métriques en évolution
                updates = {
                    "moe_calls":        t * 3,
                    "parliament_votes": t // 5,
                    "cai_revisions":    t // 8,
                    "learning_episodes":t * 2,
                    "curriculum_level": f"{min(5, 1+t//20)}/5",
                    "anomalies":        t // 50,
                    "consistency_score":f"{max(75, 100-t//20):.0f}%",
                    "context_entries":  t * 7,
                }
                self._q.put(("metrics_update", updates))
                self._q.put(("log_line",
                    f"[{datetime.now().strftime('%H:%M:%S')}] "
                    f"MoE:{updates['moe_calls']} | "
                    f"Learning:{updates['learning_episodes']} | "
                    f"Cohérence:{updates['consistency_score']}"
                ))
                self._q.put(("ts_update", None))
                time.sleep(5)
        threading.Thread(target=_loop, daemon=True).start()

    # ── Poll ──────────────────────────────────────────────────────────

    def _poll(self):
        try:
            while True:
                evt, data = self._q.get_nowait()
                if evt == "metrics_update" and hasattr(self, "_metric_vars"):
                    for key, val in data.items():
                        if key in self._metric_vars:
                            self._metric_vars[key].set(str(val))
                elif evt == "log_line" and hasattr(self, "global_log"):
                    self.global_log.configure(state="normal")
                    self.global_log.insert("end", data + "\n")
                    self.global_log.see("end")
                    self.global_log.configure(state="disabled")
                elif evt == "ts_update":
                    self.lbl_ts.configure(
                        text=datetime.now().strftime("V1.20 | %d/%m/%Y %H:%M:%S")
                    )
                elif evt == "chat_response":
                    agent_label, resp = data
                    self._chat_append(f"🤖 {agent_label}", resp, "agent")
                    self.lbl_typing.configure(text="")
        except Exception:
            pass
        self.root.after(100, self._poll)

    def _on_close(self):
        self._running = False
        self.root.destroy()

    def run(self):
        self.root.mainloop()


if __name__ == "__main__":
    app = V120Dashboard()
    app.run()

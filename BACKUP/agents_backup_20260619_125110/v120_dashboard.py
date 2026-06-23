"""
agents/v120_dashboard.py -- Ov3rLoRd V1.20 -- Dashboard Unifie
Interface tout-en-un pour superviser le pipeline V1.20.
V1.49 : overlord_utils centralise, context_bus connecte, ASCII dans les logs Python.
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

if hasattr(sys.stdout, 'buffer') and getattr(sys.stdout,'encoding','').lower() != 'utf-8':
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

try:
    from agents.roles_registry import get_system_prompt
except ImportError:
    def get_system_prompt(role="default", **kw):
        return "Tu es un assistant IA Ov3rLoRd."

try:
    from agents.overlord_utils import fallback_llm, get_api_key
    UTILS_OK = True
except ImportError:
    UTILS_OK = False
    fallback_llm = None
    get_api_key  = None

try:
    from agents.context_bus import get_bus
    BUS_OK = True
except ImportError:
    BUS_OK = False

# Import optionnel des modules V1.20
try:
    from agents.v120_moe        import MoEV120
    from agents.v120_learning   import LearningV120
    from agents.v120_alignment  import AlignmentV120
    from agents.v120_collective import CollectiveIntelligence
    from agents.v120_generation import GenerationV120
    V120_OK = True
except ImportError:
    V120_OK = False

CLAUDE_MODEL = "claude-sonnet-4-6"

PAL = {
    "bg":      "#050508", "panel":   "#0A0A12", "card":    "#10101A",
    "border":  "#1E1E30", "accent":  "#7C3AED", "accent2": "#A855F7",
    "ok":      "#10B981", "warn":    "#F59E0B", "err":     "#EF4444",
    "text":    "#E0E0F8", "textd":   "#7070A8", "blue":    "#3B82F6",
}


def _llm_chat(message: str, role: str = "default") -> str:
    """Appel LLM centralise pour le chat du dashboard."""
    system = get_system_prompt(role=role)
    if UTILS_OK and fallback_llm:
        return fallback_llm(message, system=system, model=CLAUDE_MODEL, max_tokens=800)
    return "[LLM indisponible]"


def _get_bus_snapshot() -> dict:
    """Recupere un snapshot du context_bus pour les metriques."""
    if not BUS_OK:
        return {}
    try:
        bus  = get_bus()
        snap = bus.snapshot() if hasattr(bus,"snapshot") else {}
        return {k: v.get("value") for k,v in snap.items()}
    except Exception:
        return {}


class DashboardV120:
    """Dashboard unifie pour superviser le pipeline V1.20."""

    def __init__(self):
        self.root = tk.Tk()
        self.root.title("Ov3rLoRd V1.20 — Dashboard Unifie")
        self.root.configure(bg=PAL["bg"])
        self.root.geometry("1400x800")
        self.root.minsize(1000, 600)
        self._queue: queue.Queue = queue.Queue()
        self._build_ui()
        self._start_update_loop()

    def _build_ui(self):
        P = PAL

        # Header
        hdr = tk.Frame(self.root, bg=P["panel"], height=48)
        hdr.pack(fill="x")
        hdr.pack_propagate(False)
        tk.Label(hdr, text="  Ov3rLoRd V1.20 -- Dashboard Unifie",
                 font=("Segoe UI",14,"bold"), bg=P["panel"], fg=P["accent2"]
                 ).pack(side="left", padx=12, pady=10)
        self.lbl_time = tk.Label(hdr, text="",
                                  font=("Segoe UI",9), bg=P["panel"], fg=P["textd"])
        self.lbl_time.pack(side="right", padx=12)

        # Notebook
        style = ttk.Style()
        style.theme_use("default")
        style.configure("TNotebook",     background=P["bg"],    borderwidth=0)
        style.configure("TNotebook.Tab", background=P["panel"], foreground=P["textd"],
                        font=("Segoe UI",9,"bold"), padding=[10,5])
        style.map("TNotebook.Tab",
                  background=[("selected", P["card"])],
                  foreground=[("selected", P["accent2"])])

        nb = ttk.Notebook(self.root)
        nb.pack(fill="both", expand=True, padx=4, pady=4)

        self._tabs = {}
        tab_defs = [
            ("metrics",    "Metriques"),
            ("bus",        "Context Bus"),
            ("chat",       "Oracle Chat"),
            ("v120",       "V1.20 Modules"),
        ]
        for key, label in tab_defs:
            frame = tk.Frame(nb, bg=P["bg"])
            nb.add(frame, text=f"  {label}  ")
            self._tabs[key] = frame

        self._build_metrics_tab()
        self._build_bus_tab()
        self._build_chat_tab()
        self._build_v120_tab()

    def _build_metrics_tab(self):
        tab = self._tabs["metrics"]
        P   = PAL

        top = tk.Frame(tab, bg=P["bg"])
        top.pack(fill="x", padx=12, pady=8)
        tk.Label(top, text="Metriques temps reel (depuis context_bus)",
                 font=("Segoe UI",10,"bold"), bg=P["bg"], fg=P["text"]).pack(anchor="w")

        self._metrics_text = tk.Text(tab, bg=P["card"], fg=P["text"],
                                      font=("Consolas",9), wrap="word",
                                      relief=tk.FLAT, state=tk.DISABLED)
        self._metrics_text.pack(fill="both", expand=True, padx=12, pady=4)

        btn_frame = tk.Frame(tab, bg=P["bg"])
        btn_frame.pack(fill="x", padx=12, pady=4)
        tk.Button(btn_frame, text="Rafraichir",
                  bg=P["panel"], fg=P["accent2"], relief=tk.FLAT, cursor="hand2",
                  font=("Segoe UI",9), command=self._refresh_metrics
                  ).pack(side="left", padx=4)

    def _refresh_metrics(self):
        snap  = _get_bus_snapshot()
        lines = ["=== Context Bus Snapshot ===\n"]
        groups = {}
        for k, v in sorted(snap.items()):
            prefix = k.split(".")[0]
            groups.setdefault(prefix, []).append((k, v))
        for prefix, items in sorted(groups.items()):
            lines.append(f"\n[{prefix.upper()}]")
            for k, v in items:
                lines.append(f"  {k:<40} {str(v)[:60]}")

        self._metrics_text.config(state=tk.NORMAL)
        self._metrics_text.delete("1.0", tk.END)
        self._metrics_text.insert(tk.END, "\n".join(lines))
        self._metrics_text.config(state=tk.DISABLED)

    def _build_bus_tab(self):
        tab = self._tabs["bus"]
        P   = PAL
        tk.Label(tab, text="Context Bus — Ecriture / Lecture directe",
                 font=("Segoe UI",10,"bold"), bg=P["bg"], fg=P["text"]
                 ).pack(anchor="w", padx=12, pady=8)

        write_frame = tk.Frame(tab, bg=P["card"], padx=10, pady=8)
        write_frame.pack(fill="x", padx=12, pady=4)
        tk.Label(write_frame, text="Ecrire sur le bus :",
                 bg=P["card"], fg=P["textd"], font=("Segoe UI",8)).pack(anchor="w")
        key_row = tk.Frame(write_frame, bg=P["card"])
        key_row.pack(fill="x")
        tk.Label(key_row, text="Cle :", bg=P["card"], fg=P["text"],
                 font=("Consolas",9)).pack(side="left")
        self._bus_key = tk.Entry(key_row, bg=P["bg"], fg=P["text"],
                                  font=("Consolas",9), relief=tk.FLAT, width=30)
        self._bus_key.pack(side="left", padx=4)
        tk.Label(key_row, text="Valeur :", bg=P["card"], fg=P["text"],
                 font=("Consolas",9)).pack(side="left", padx=(8,0))
        self._bus_val = tk.Entry(key_row, bg=P["bg"], fg=P["text"],
                                  font=("Consolas",9), relief=tk.FLAT, width=30)
        self._bus_val.pack(side="left", padx=4)
        tk.Button(key_row, text="Ecrire", bg=P["accent"], fg=P["text"],
                  relief=tk.FLAT, cursor="hand2", font=("Segoe UI",9),
                  command=self._bus_write).pack(side="left", padx=4)

        self._bus_log = tk.Text(tab, bg=P["card"], fg=P["text"],
                                 font=("Consolas",8), wrap="word",
                                 relief=tk.FLAT, height=15, state=tk.DISABLED)
        self._bus_log.pack(fill="both", expand=True, padx=12, pady=4)

    def _bus_write(self):
        key = self._bus_key.get().strip()
        val = self._bus_val.get().strip()
        if not key or not BUS_OK:
            return
        try:
            get_bus().write(key, val, agent_id="dashboard")
            self._log_bus(f"[OK] Ecrit : {key} = {val}")
        except Exception as e:
            self._log_bus(f"[ERR] {e}")

    def _log_bus(self, msg: str):
        self._bus_log.config(state=tk.NORMAL)
        ts = datetime.now().strftime("%H:%M:%S")
        self._bus_log.insert(tk.END, f"[{ts}] {msg}\n")
        self._bus_log.see(tk.END)
        self._bus_log.config(state=tk.DISABLED)

    def _build_chat_tab(self):
        tab = self._tabs["chat"]
        P   = PAL

        tk.Label(tab, text="Oracle Chat -- Discuter avec les agents Ov3rLoRd",
                 font=("Segoe UI",10,"bold"), bg=P["bg"], fg=P["text"]
                 ).pack(anchor="w", padx=12, pady=8)

        role_frame = tk.Frame(tab, bg=P["bg"])
        role_frame.pack(fill="x", padx=12, pady=2)
        tk.Label(role_frame, text="Role :", bg=P["bg"], fg=P["textd"],
                 font=("Segoe UI",9)).pack(side="left")
        self._role_var = tk.StringVar(value="default")
        roles = ["default","director","scenario","storyboard","critic","watchdog"]
        role_cb = ttk.Combobox(role_frame, textvariable=self._role_var,
                                values=roles, state="readonly",
                                font=("Segoe UI",9), width=15)
        role_cb.pack(side="left", padx=4)

        self._chat_log = tk.Text(tab, bg=P["card"], fg=P["text"],
                                  font=("Segoe UI",9), wrap="word",
                                  relief=tk.FLAT, state=tk.DISABLED)
        self._chat_log.pack(fill="both", expand=True, padx=12, pady=4)
        self._chat_log.tag_config("user",      foreground=P["accent2"])
        self._chat_log.tag_config("assistant", foreground=P["ok"])
        self._chat_log.tag_config("system",    foreground=P["textd"])

        input_frame = tk.Frame(tab, bg=P["bg"])
        input_frame.pack(fill="x", padx=12, pady=4)
        self._chat_input = tk.Entry(input_frame, bg=P["card"], fg=P["text"],
                                     font=("Segoe UI",10), relief=tk.FLAT)
        self._chat_input.pack(side="left", fill="x", expand=True, padx=(0,4))
        self._chat_input.bind("<Return>", lambda e: self._send_chat())
        tk.Button(input_frame, text="Envoyer",
                  bg=P["accent"], fg=P["text"], relief=tk.FLAT, cursor="hand2",
                  font=("Segoe UI",9,"bold"), command=self._send_chat
                  ).pack(side="left")

    def _append_chat(self, msg: str, tag: str):
        self._chat_log.config(state=tk.NORMAL)
        self._chat_log.insert(tk.END, msg + "\n", tag)
        self._chat_log.see(tk.END)
        self._chat_log.config(state=tk.DISABLED)

    def _send_chat(self):
        msg = self._chat_input.get().strip()
        if not msg:
            return
        self._chat_input.delete(0, tk.END)
        self._append_chat(f"Vous : {msg}", "user")
        role = self._role_var.get()

        def _reply():
            response = _llm_chat(msg, role=role)
            self.root.after(0, self._append_chat,
                            f"[{role}] : {response}", "assistant")

        threading.Thread(target=_reply, daemon=True).start()

    def _build_v120_tab(self):
        tab = self._tabs["v120"]
        P   = PAL

        status = "V1.20 modules charges" if V120_OK else "V1.20 modules non charges (import manquant)"
        color  = P["ok"] if V120_OK else P["warn"]
        tk.Label(tab, text=status, font=("Segoe UI",10,"bold"),
                 bg=P["bg"], fg=color).pack(anchor="w", padx=12, pady=8)

        modules_info = [
            ("v120_moe",        "Mixture of Experts (Router, Sparse Attention, RoPE)"),
            ("v120_learning",   "Apprentissage (Reward, Replay, Curriculum)"),
            ("v120_alignment",  "Alignement (CAI, Debat, Anomalie)"),
            ("v120_collective", "Collective (Parlement, Specialisation, Nouveaux agents)"),
            ("v120_generation", "Generation (Scheduler, LoRA, Style, Temporel)"),
        ]
        for mod, desc in modules_info:
            row = tk.Frame(tab, bg=P["card"], pady=4)
            row.pack(fill="x", padx=12, pady=2)
            tk.Label(row, text=mod, font=("Consolas",9,"bold"),
                     bg=P["card"], fg=P["accent2"], width=20, anchor="w"
                     ).pack(side="left", padx=8)
            tk.Label(row, text=desc, font=("Segoe UI",8),
                     bg=P["card"], fg=P["textd"]).pack(side="left")

    def _start_update_loop(self):
        def _loop():
            while True:
                time.sleep(5)
                self.root.after(0, self._update_time)
        threading.Thread(target=_loop, daemon=True).start()

    def _update_time(self):
        self.lbl_time.configure(text=datetime.now().strftime("%H:%M:%S"))

    def run(self):
        self._update_time()
        self.root.mainloop()


if __name__ == "__main__":
    app = DashboardV120()
    app.run()
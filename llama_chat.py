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
llama_chat.py — Interface Chat Llama (standalone)
Interface graphique dédiée pour discuter avec Llama via Ollama.
Usage indépendant du pipeline principal.

Lancement : python llama_chat.py
"""

import tkinter as tk
from tkinter import ttk, scrolledtext
import threading, queue, json, time, requests
from pathlib import Path
from datetime import datetime

OLLAMA_URL    = "http://localhost:11434"
SETTINGS_FILE = Path("llama_chat_settings.json")
APP_NAME      = "Llama Chat — OverLord"

MODELS_DEFAULT = ["llama3", "llama3.1", "llama3.2", "mistral",
                  "mistral-nemo", "deepseek-coder", "deepseek-r1",
                  "phi3", "gemma2", "qwen2.5", "codellama"]

PAL = {
    "dark":  dict(bg="#0F0F14", surf="#16161E", surf2="#1E1E28",
                  border="#2A2A3A", accent="#7C3AED", accent2="#A855F7",
                  text="#E0E0F0", textd="#7070A0", textm="#404060",
                  user_bg="#1E1E40", user_fg="#A0C8FF",
                  ai_bg="#1A2A1A",   ai_fg="#A0FFA8",
                  sys_fg="#F59E0B",  input_bg="#1A1A22",
                  btn="#7C3AED",     btn_fg="#FFFFFF"),
    "light": dict(bg="#F5F4FF", surf="#FFFFFF", surf2="#EEEEFF",
                  border="#D0CCF0", accent="#6D28D9", accent2="#7C3AED",
                  text="#1A1A2E", textd="#5A5A80", textm="#9090B0",
                  user_bg="#E8E8FF", user_fg="#3030A0",
                  ai_bg="#E8FFE8",   ai_fg="#206020",
                  sys_fg="#D97706",  input_bg="#F0EEFF",
                  btn="#6D28D9",     btn_fg="#FFFFFF"),
}

SYSTEM_PRESETS = {
    "Assistant général":
        "Tu es un assistant IA intelligent et utile. Réponds en français par défaut.",
    "Expert ComfyUI":
        ("Tu es un expert ComfyUI et Stable Diffusion. Tu connais parfaitement les nœuds, "
         "les workflows, les LoRAs, les checkpoints SDXL et les techniques de génération d'images IA. "
         "Tu aides à déboguer et optimiser des pipelines de production."),
    "Scénariste anime":
        ("Tu es un scénariste spécialisé dans les œuvres transmédias (anime, manga, comics, jeux vidéo). "
         "Tu crées des histoires originales et captivantes avec des arcs narratifs solides."),
    "Code Python":
        ("Tu es un développeur Python expert. Tu écris du code propre, modulaire et bien commenté. "
         "Tu expliques tes choix techniques et anticipes les erreurs courantes."),
    "Vide (sans système)": "",
}

def load_settings():
    try:
        if SETTINGS_FILE.exists():
            return json.loads(SETTINGS_FILE.read_text(encoding="utf-8"))
    except Exception: pass
    return {"theme": "dark", "model": "llama3", "system": "Assistant général",
            "temperature": 0.7, "context_length": 8, "stream": True}

def save_settings(cfg):
    SETTINGS_FILE.write_text(json.dumps(cfg, indent=2, ensure_ascii=False), encoding="utf-8")


class LlamaChat:
    def __init__(self):
        self.cfg      = load_settings()
        self.theme    = self.cfg.get("theme", "dark")
        self.P        = PAL[self.theme]
        self.history  = []   # [{"role": "user"|"assistant"|"system", "content": str}]
        self.q        = queue.Queue()
        self._typing  = False

        self._build_window()
        self._build_ui()
        self._apply_theme()
        self._check_ollama()
        self._poll()

    def _build_window(self):
        self.root = tk.Tk()
        self.root.title(APP_NAME)
        self.root.geometry("900x700")
        self.root.minsize(600, 400)
        self.root.configure(bg=self.P["bg"])
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)
        sw = self.root.winfo_screenwidth()
        sh = self.root.winfo_screenheight()
        self.root.geometry(f"900x700+{(sw-900)//2}+{(sh-700)//2}")

    def _build_ui(self):
        P = self.P

        # ── Titlebar ──
        self.titlebar = tk.Frame(self.root, height=48)
        self.titlebar.pack(fill="x")
        self.titlebar.pack_propagate(False)

        tk.Label(self.titlebar, text="  🦙  Llama Chat",
                 font=("Segoe UI", 13, "bold"), anchor="w"
                 ).pack(side="left", fill="y", padx=4)

        self.lbl_status = tk.Label(self.titlebar, text="● Vérification…",
                                    font=("Segoe UI", 8), anchor="e", padx=10)
        self.lbl_status.pack(side="right", fill="y")

        for txt, cmd in [("🌙" if self.theme=="dark" else "☀", self._toggle_theme),
                          ("🗑 Effacer", self._clear_chat),
                          ("💾 Exporter", self._export_chat)]:
            tk.Button(self.titlebar, text=txt, font=("Segoe UI", 9),
                      relief="flat", bd=0, cursor="hand2", padx=10, pady=4,
                      command=cmd).pack(side="right", padx=2)

        # ── Corps principal ──
        body = tk.Frame(self.root)
        body.pack(fill="both", expand=True)

        # Sidebar gauche (paramètres)
        self.sidebar = tk.Frame(body, width=220)
        self.sidebar.pack(side="left", fill="y")
        self.sidebar.pack_propagate(False)
        self._build_sidebar()

        # Séparateur
        tk.Frame(body, width=1).pack(side="left", fill="y")

        # Zone chat droite
        self.chat_frame = tk.Frame(body)
        self.chat_frame.pack(side="left", fill="both", expand=True)
        self._build_chat()

    def _build_sidebar(self):
        s = self.sidebar
        P = self.P

        def lbl(t): tk.Label(s, text=t, font=("Segoe UI", 8, "bold"),
                              anchor="w").pack(fill="x", padx=10, pady=(10,2))
        def sep(): tk.Frame(s, height=1).pack(fill="x", padx=10, pady=2)

        lbl("Modèle")
        self._model_var = tk.StringVar(value=self.cfg.get("model", "llama3"))
        self._model_cb  = ttk.Combobox(s, textvariable=self._model_var,
                                         values=MODELS_DEFAULT,
                                         state="normal", font=("Segoe UI", 8))
        self._model_cb.pack(fill="x", padx=10, pady=2)

        tk.Button(s, text="🔄 Actualiser", font=("Segoe UI", 8),
                  relief="flat", bd=0, cursor="hand2", pady=3,
                  command=self._refresh_models).pack(fill="x", padx=10, pady=2)

        sep()
        lbl("Prompt système")
        self._sys_var = tk.StringVar(value=self.cfg.get("system", "Assistant général"))
        sys_cb = ttk.Combobox(s, textvariable=self._sys_var,
                               values=list(SYSTEM_PRESETS.keys()),
                               state="readonly", font=("Segoe UI", 8))
        sys_cb.pack(fill="x", padx=10, pady=2)
        sys_cb.bind("<<ComboboxSelected>>", self._on_sys_change)

        self._sys_txt = tk.Text(s, height=5, font=("Segoe UI", 8),
                                wrap="word", relief="flat", bd=1)
        self._sys_txt.insert("1.0", SYSTEM_PRESETS.get(self._sys_var.get(), ""))
        self._sys_txt.pack(fill="x", padx=10, pady=2)

        sep()
        lbl("Température")
        self._temp_var = tk.DoubleVar(value=self.cfg.get("temperature", 0.7))
        tk.Scale(s, from_=0.0, to=2.0, resolution=0.05, orient="horizontal",
                 variable=self._temp_var, font=("Segoe UI", 7),
                 highlightthickness=0
                 ).pack(fill="x", padx=10)

        lbl("Contexte (nb messages)")
        self._ctx_var = tk.IntVar(value=self.cfg.get("context_length", 8))
        tk.Scale(s, from_=2, to=32, resolution=2, orient="horizontal",
                 variable=self._ctx_var, font=("Segoe UI", 7),
                 highlightthickness=0
                 ).pack(fill="x", padx=10)

        sep()
        # Streaming toggle
        self._stream_var = tk.BooleanVar(value=self.cfg.get("stream", True))
        tk.Checkbutton(s, text="Streaming (affichage mot à mot)",
                       variable=self._stream_var,
                       font=("Segoe UI", 8), relief="flat"
                       ).pack(fill="x", padx=10, pady=4)

        sep()
        tk.Button(s, text="▶ Lancer Ollama", font=("Segoe UI", 8, "bold"),
                  relief="flat", bd=0, cursor="hand2", pady=6,
                  command=self._start_ollama
                  ).pack(fill="x", padx=10, pady=2)

    def _build_chat(self):
        f = self.chat_frame
        P = self.P

        # Zone de messages scrollable
        self.msg_frame = tk.Frame(f)
        self.msg_frame.pack(fill="both", expand=True)

        self.chat_canvas = tk.Canvas(self.msg_frame, highlightthickness=0, bd=0)
        chat_scroll = tk.Scrollbar(self.msg_frame, orient="vertical",
                                    command=self.chat_canvas.yview)
        self.chat_inner = tk.Frame(self.chat_canvas)
        self.chat_inner.bind("<Configure>",
            lambda e: self.chat_canvas.configure(
                scrollregion=self.chat_canvas.bbox("all")))
        self.chat_canvas.create_window((0,0), window=self.chat_inner, anchor="nw")
        self.chat_canvas.configure(yscrollcommand=chat_scroll.set)
        chat_scroll.pack(side="right", fill="y")
        self.chat_canvas.pack(fill="both", expand=True)
        self.chat_canvas.bind_all("<MouseWheel>",
            lambda e: self.chat_canvas.yview_scroll(-1*(e.delta//120),"units"))

        # Zone de saisie
        input_frame = tk.Frame(f, height=100)
        input_frame.pack(fill="x", side="bottom")
        input_frame.pack_propagate(False)

        self._input = tk.Text(input_frame, height=4, font=("Segoe UI", 10),
                              wrap="word", relief="flat", bd=1)
        self._input.pack(fill="both", expand=True, padx=8, pady=(6,2))
        self._input.bind("<Return>",        self._on_enter)
        self._input.bind("<Shift-Return>",  lambda e: None)  # Shift+Enter = newline

        btn_row = tk.Frame(f)
        btn_row.pack(fill="x", padx=8, pady=(0,6))

        self.btn_send = tk.Button(btn_row, text="Envoyer  ↵",
            font=("Segoe UI", 9, "bold"), relief="flat", bd=0,
            cursor="hand2", padx=16, pady=6, command=self._send)
        self.btn_send.pack(side="right")

        self.btn_stop = tk.Button(btn_row, text="⏹ Stop",
            font=("Segoe UI", 9), relief="flat", bd=0,
            cursor="hand2", padx=10, pady=6, state="disabled",
            command=self._stop_gen)
        self.btn_stop.pack(side="right", padx=6)

        # Indicateur de frappe
        self.lbl_typing = tk.Label(btn_row, text="",
                                    font=("Segoe UI", 8), anchor="w")
        self.lbl_typing.pack(side="left")

    # ── Messages ─────────────────────────────────────────────────────
    def _add_message(self, role: str, content: str, streaming: bool = False):
        P   = self.P
        f   = self.chat_inner
        ts  = datetime.now().strftime("%H:%M")

        colors = {
            "user":      (P["user_bg"], P["user_fg"], "Vous", "right"),
            "assistant": (P["ai_bg"],   P["ai_fg"],   "🦙 Llama", "left"),
            "system":    (P["bg"],      P["sys_fg"],  "Système",  "left"),
        }
        bg, fg, sender, side = colors.get(role, (P["surf"], P["text"], role, "left"))

        bubble = tk.Frame(f, bg=bg, padx=10, pady=6)
        bubble.pack(fill="x", padx=8, pady=3, anchor="e" if side=="right" else "w")

        header = tk.Frame(bubble, bg=bg)
        header.pack(fill="x")
        tk.Label(header, text=sender, font=("Segoe UI", 8, "bold"),
                 bg=bg, fg=fg).pack(side="left")
        tk.Label(header, text=ts, font=("Segoe UI", 7),
                 bg=bg, fg=P["textm"]).pack(side="right")

        txt = tk.Text(bubble, font=("Segoe UI", 10), wrap="word",
                      bg=bg, fg=fg, relief="flat", bd=0,
                      state="normal", cursor="arrow",
                      height=1)
        txt.insert("1.0", content)
        txt.configure(state="disabled")
        # Auto-height
        lines = content.count("\n") + max(1, len(content)//80)
        txt.configure(height=min(lines + 1, 30))
        txt.pack(fill="x")

        self._scroll_bottom()
        return txt  # retourner pour streaming

    def _add_streaming_bubble(self) -> tk.Text:
        """Crée une bulle vide pour le streaming."""
        P  = self.P
        bg = P["ai_bg"]; fg = P["ai_fg"]
        f  = self.chat_inner
        ts = datetime.now().strftime("%H:%M")

        bubble = tk.Frame(f, bg=bg, padx=10, pady=6)
        bubble.pack(fill="x", padx=8, pady=3, anchor="w")

        header = tk.Frame(bubble, bg=bg)
        header.pack(fill="x")
        tk.Label(header, text="🦙 Llama", font=("Segoe UI", 8, "bold"),
                 bg=bg, fg=fg).pack(side="left")
        tk.Label(header, text=ts, font=("Segoe UI", 7),
                 bg=bg, fg=P["textm"]).pack(side="right")

        txt = tk.Text(bubble, font=("Segoe UI", 10), wrap="word",
                      bg=bg, fg=fg, relief="flat", bd=0,
                      state="normal", cursor="arrow", height=2)
        txt.pack(fill="x")
        self._scroll_bottom()
        return txt, bubble

    def _scroll_bottom(self):
        self.chat_canvas.update_idletasks()
        self.chat_canvas.yview_moveto(1.0)

    # ── Envoi ─────────────────────────────────────────────────────────
    def _on_enter(self, e):
        if not (e.state & 1):  # sans Shift
            self._send()
            return "break"

    def _send(self):
        if self._typing:
            return
        text = self._input.get("1.0", "end").strip()
        if not text:
            return
        self._input.delete("1.0", "end")

        # Afficher message utilisateur
        self._add_message("user", text)
        self.history.append({"role": "user", "content": text})

        self._typing = True
        self.btn_send.configure(state="disabled")
        self.btn_stop.configure(state="normal")
        self.lbl_typing.configure(text="🦙 Llama réfléchit…")
        self._stop_flag = False
        self._stream_widget = None

        threading.Thread(target=self._generate, args=(text,), daemon=True).start()

    def _generate(self, user_text: str):
        model   = self._model_var.get()
        temp    = self._temp_var.get()
        ctx_n   = self._ctx_var.get()
        stream  = self._stream_var.get()
        sys_txt = self._sys_txt.get("1.0", "end").strip()

        # Construire le contexte (N derniers messages)
        messages = []
        if sys_txt:
            messages.append({"role": "system", "content": sys_txt})
        messages += self.history[-ctx_n:]

        payload = {
            "model":    model,
            "messages": messages,
            "stream":   stream,
            "options":  {"temperature": temp},
        }

        try:
            if stream:
                self.q.put(("__stream_start__", ""))
                r = requests.post(f"{OLLAMA_URL}/api/chat",
                                   json=payload, stream=True, timeout=120)
                full_response = ""
                for line in r.iter_lines():
                    if self._stop_flag:
                        break
                    if line:
                        data = json.loads(line)
                        token = data.get("message", {}).get("content", "")
                        full_response += token
                        self.q.put(("__token__", token))
                        if data.get("done"):
                            break
                self.history.append({"role": "assistant", "content": full_response})
                self.q.put(("__stream_end__", ""))
            else:
                r = requests.post(f"{OLLAMA_URL}/api/chat",
                                   json=payload, timeout=120)
                if r.status_code == 200:
                    content = r.json().get("message",{}).get("content","")
                    self.history.append({"role": "assistant", "content": content})
                    self.q.put(("__message__", content))
                else:
                    self.q.put(("__error__", f"HTTP {r.status_code}"))
        except Exception as e:
            self.q.put(("__error__", str(e)))
        finally:
            self.q.put(("__done__", ""))

    def _stop_gen(self):
        self._stop_flag = True

    # ── Poll ─────────────────────────────────────────────────────────

    def _poll(self):
        try:
            while True:
                evt, data = self.q.get_nowait()
                if evt == "__stream_start__":
                    txt_widget, bubble = self._add_streaming_bubble()
                    self._stream_widget = txt_widget
                elif evt == "__token__":
                    if hasattr(self, "_stream_widget") and self._stream_widget:
                        self._stream_widget.insert("end", data)
                        # Ajuster hauteur
                        content = self._stream_widget.get("1.0","end")
                        lines   = content.count("\n") + max(1, len(content)//80)
                        self._stream_widget.configure(height=min(lines+1,30))
                        self._scroll_bottom()
                elif evt == "__stream_end__":
                    self._stream_widget = None
                elif evt == "__message__":
                    self._add_message("assistant", data)
                elif evt == "__error__":
                    self._add_message("system", f"❌ Erreur : {data}")
                elif evt == "__done__":
                    self._typing = False
                    self.btn_send.configure(state="normal")
                    self.btn_stop.configure(state="disabled")
                    self.lbl_typing.configure(text="")
        except Exception:
            pass
        self.root.after(50, self._poll)

    # ── Ollama ───────────────────────────────────────────────────────
    def _check_ollama(self):
        def _check():
            try:
                r = requests.get(f"{OLLAMA_URL}/api/tags", timeout=3)
                if r.status_code == 200:
                    models = [m["name"].split(":")[0] for m in r.json().get("models",[])]
                    self.q.put(("__ollama_ok__", models))
                else:
                    self.q.put(("__ollama_err__", ""))
            except Exception:
                self.q.put(("__ollama_err__", ""))
        threading.Thread(target=_check, daemon=True).start()
        self.root.after(200, self._check_ollama_result)

    def _check_ollama_result(self):
        try:
            evt, data = self.q.get_nowait()
            if evt == "__ollama_ok__":
                n = len(data) if isinstance(data, list) else 0
                self.lbl_status.configure(text=f"● Ollama en ligne ({n} modèles)",
                                           fg=self.P.get("ok","#10B981"))
                if isinstance(data, list) and data:
                    self._model_cb.configure(values=data)
            elif evt == "__ollama_err__":
                self.lbl_status.configure(text="● Ollama hors ligne",
                                           fg=self.P.get("err","#EF4444"))
        except Exception:
            pass

    def _refresh_models(self):
        self.lbl_status.configure(text="● Actualisation…")
        self._check_ollama()

    def _start_ollama(self):
        import subprocess as sp
        try:
            sp.Popen(["ollama", "serve"], creationflags=sp.CREATE_NO_WINDOW)
            self._add_message("system", "Ollama démarré. Attente 3s…")
            self.root.after(3000, self._check_ollama)
        except FileNotFoundError:
            self._add_message("system",
                "❌ 'ollama' introuvable. Installe depuis https://ollama.com")

    def _on_sys_change(self, e=None):
        preset = self._sys_var.get()
        txt    = SYSTEM_PRESETS.get(preset, "")
        self._sys_txt.delete("1.0","end")
        self._sys_txt.insert("1.0", txt)

    # ── Utilitaires ──────────────────────────────────────────────────
    def _clear_chat(self):
        for w in self.chat_inner.winfo_children():
            w.destroy()
        self.history = []
        self._add_message("system", "Conversation effacée. Nouvelle session démarrée.")

    def _export_chat(self):
        ts   = datetime.now().strftime("%Y%m%d_%H%M%S")
        path = Path(f"llama_chat_export_{ts}.json")
        path.write_text(
            json.dumps(self.history, indent=2, ensure_ascii=False),
            encoding="utf-8"
        )
        self._add_message("system", f"Conversation exportée : {path}")

    def _toggle_theme(self):
        self.theme = "light" if self.theme=="dark" else "dark"
        self.P     = PAL[self.theme]
        self.cfg["theme"] = self.theme
        save_settings(self.cfg)
        self._apply_theme()

    def _apply_theme(self):
        P = self.P
        self.root.configure(bg=P["bg"])
        self._theme_w(self.root)
        self.chat_canvas.configure(bg=P["bg"])
        self.chat_inner.configure(bg=P["bg"])
        self._input.configure(bg=P["input_bg"], fg=P["text"],
                               insertbackground=P["text"])
        self.btn_send.configure(bg=P["btn"], fg=P["btn_fg"],
                                activebackground=P["accent2"])
        self.btn_stop.configure(bg=P["surf2"], fg=P["text"])

    def _theme_w(self, w):
        P = self.P
        try:
            cls = w.winfo_class()
            if cls == "Frame":  w.configure(bg=P["bg"])
            elif cls == "Label": w.configure(bg=P["bg"], fg=P["text"])
            elif cls == "Checkbutton": w.configure(bg=P["bg"], fg=P["text"],
                                                    selectcolor=P["surf2"],
                                                    activebackground=P["bg"])
        except Exception: pass
        for c in w.winfo_children():
            self._theme_w(c)

    def _on_close(self):
        self.cfg.update({
            "model":          self._model_var.get(),
            "system":         self._sys_var.get(),
            "temperature":    self._temp_var.get(),
            "context_length": self._ctx_var.get(),
            "stream":         self._stream_var.get(),
            "theme":          self.theme,
        })
        save_settings(self.cfg)
        self.root.destroy()

    def run(self):
        self.root.mainloop()


if __name__ == "__main__":
    app = LlamaChat()
    app.run()

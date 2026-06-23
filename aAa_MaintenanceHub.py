"""
aAa_MaintenanceHub.py — Hub de Maintenance Ov3rLoRd V1.49
Interface graphique tkinter pour gerer les outils de maintenance :
  - Patcher     (patcher.py)             -> racine du projet
  - Auditeur    (aAa_Auditeur.py)        -> sous-dossier aAa_Auditeur/
  - SyntaxCheck (aAa_SyntaxCheck.py)     -> sous-dossier aAa_SyntaxCheck/

Compilable en EXE :
  python build_maintenance_hub.py
Ou directement :
  python aAa_MaintenanceHub.py
"""

import sys
import io
import os
import subprocess
import threading
import tkinter as tk
from tkinter import ttk, scrolledtext, filedialog, messagebox
from pathlib import Path
from datetime import datetime

# Force UTF-8
if hasattr(sys.stdout, 'buffer'):
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

# ── Chemins des agents ────────────────────────────────────────────────────────
# Le hub est a la racine de D:\OVERLORD\
# Les agents aAa sont dans leurs sous-dossiers respectifs
_ROOT        = Path(__file__).resolve().parent
PATCHER_PATH = _ROOT / "patcher.py"
AUDITEUR_DIR = _ROOT / "aAa_Auditeur"
AUDITEUR_PY  = AUDITEUR_DIR / "aAa_Auditeur.py"
SYNTAX_DIR   = _ROOT / "aAa_SyntaxCheck"
SYNTAX_PY    = SYNTAX_DIR / "aAa_SyntaxCheck.py"

# ── Palette ───────────────────────────────────────────────────────────────────
C = {
    "bg":          "#0d0d14",
    "panel":       "#13131e",
    "card":        "#1a1a2a",
    "border":      "#2a2a45",
    "blue":        "#0077ff",
    "cyan":        "#00ccff",
    "green":       "#00e676",
    "red":         "#ff3355",
    "gold":        "#ffd700",
    "purple":      "#bb86fc",
    "text":        "#e8e8f4",
    "dim":         "#7777aa",
}

ENV_UTF8 = {**os.environ, "PYTHONIOENCODING": "utf-8", "PYTHONUTF8": "1"}


# ── Widget : console de logs ───────────────────────────────────────────────────
class Console(tk.Frame):

    def __init__(self, parent, **kw):
        super().__init__(parent, bg=C["card"], **kw)
        self._txt = scrolledtext.ScrolledText(
            self, bg="#09090f", fg=C["green"],
            font=("Consolas", 9), wrap=tk.WORD,
            insertbackground=C["green"], relief=tk.FLAT,
        )
        self._txt.pack(fill=tk.BOTH, expand=True, padx=2, pady=2)
        self._txt.config(state=tk.DISABLED)
        # Tags couleur
        for name, col in [("ok", C["green"]), ("err", C["red"]),
                           ("warn", C["gold"]), ("info", C["cyan"]),
                           ("dim", C["dim"])]:
            self._txt.tag_config(name, foreground=col)

    def write(self, text: str, tag: str = None):
        """Ecriture thread-safe depuis n'importe quel thread."""
        def _do():
            self._txt.config(state=tk.NORMAL)
            self._txt.insert(tk.END, text + "\n", tag or "")
            self._txt.see(tk.END)
            self._txt.config(state=tk.DISABLED)
        self._txt.after(0, _do)

    def clear(self):
        def _do():
            self._txt.config(state=tk.NORMAL)
            self._txt.delete("1.0", tk.END)
            self._txt.config(state=tk.DISABLED)
        self._txt.after(0, _do)

    def write_line(self, line: str):
        """Detecte automatiquement le tag selon le contenu de la ligne."""
        lo = line.lower()
        if "[ok" in lo or "succes" in lo or "ok ]" in lo:
            tag = "ok"
        elif "[err" in lo or "erreur" in lo or "error" in lo or "echec" in lo:
            tag = "err"
        elif "[warn" in lo or "warning" in lo or "timeout" in lo:
            tag = "warn"
        elif "[info" in lo or "patch" in lo or "audit" in lo:
            tag = "info"
        else:
            tag = None
        self.write(line, tag)


# ── Execution d'un script en subprocess ───────────────────────────────────────
class Runner:

    def __init__(self, console: Console, status_cb=None):
        self._console   = console
        self._status_cb = status_cb
        self._proc      = None
        self._lock      = threading.Lock()

    def _set_status(self, msg: str, color: str = None):
        if self._status_cb:
            self._status_cb(msg, color)

    def run(self, cmd: list, cwd: Path = None):
        """Lance la commande dans un thread daemon."""
        if self._proc and self._proc.poll() is None:
            messagebox.showwarning("Hub", "Un process est deja en cours.")
            return
        self._console.clear()
        ts  = datetime.now().strftime("%H:%M:%S")
        self._console.write(f"[{ts}] >> {' '.join(str(c) for c in cmd)}", "dim")
        self._set_status("En cours...", C["gold"])

        def _worker():
            try:
                self._proc = subprocess.Popen(
                    [str(c) for c in cmd],
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                    text=True,
                    encoding="utf-8",
                    errors="replace",
                    env=ENV_UTF8,
                    cwd=str(cwd or _ROOT),
                )
                for line in self._proc.stdout:
                    self._console.write_line(line.rstrip())
                self._proc.wait()
                rc  = self._proc.returncode
                msg = f"Termine (code {rc})"
                col = C["green"] if rc == 0 else C["red"]
                self._console.write(f"\n{msg}", "ok" if rc == 0 else "err")
                self._set_status(msg, col)
            except FileNotFoundError as e:
                self._console.write(f"INTROUVABLE : {e}", "err")
                self._set_status("Erreur : fichier introuvable", C["red"])
            except Exception as e:
                self._console.write(f"ERREUR : {e}", "err")
                self._set_status(f"Erreur : {e}", C["red"])

        threading.Thread(target=_worker, daemon=True).start()

    def stop(self):
        if self._proc and self._proc.poll() is None:
            self._proc.terminate()
            self._console.write("Process arrete par l'utilisateur.", "warn")
            self._set_status("Arrete", C["red"])


# ── Onglet Patcher ────────────────────────────────────────────────────────────
class TabPatcher(tk.Frame):

    def __init__(self, parent, runner: Runner):
        super().__init__(parent, bg=C["bg"])
        self._runner = runner
        self._build()

    def _build(self):
        # Ligne 1 : chemin du bundle
        row1 = tk.Frame(self, bg=C["bg"])
        row1.pack(fill=tk.X, padx=12, pady=(12, 4))
        tk.Label(row1, text="Bundle :", bg=C["bg"], fg=C["text"],
                 font=("Consolas", 10)).pack(side=tk.LEFT, padx=(0, 6))
        self._bundle_var = tk.StringVar(value="patch_bundle.txt")
        self._bundle_entry = tk.Entry(
            row1, textvariable=self._bundle_var,
            bg=C["card"], fg=C["text"], insertbackground=C["blue"],
            font=("Consolas", 10), relief=tk.FLAT, width=40,
        )
        self._bundle_entry.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 6))
        tk.Button(
            row1, text="Parcourir", bg=C["panel"], fg=C["cyan"],
            font=("Consolas", 9), relief=tk.FLAT, cursor="hand2",
            command=self._browse,
        ).pack(side=tk.LEFT)

        # Ligne 2 : options
        row2 = tk.Frame(self, bg=C["bg"])
        row2.pack(fill=tk.X, padx=12, pady=4)
        self._dryrun = tk.BooleanVar(value=False)
        self._backup = tk.BooleanVar(value=True)
        tk.Checkbutton(
            row2, text="Dry-run (simulation)", variable=self._dryrun,
            bg=C["bg"], fg=C["text"], selectcolor=C["card"],
            activebackground=C["bg"], font=("Consolas", 9),
        ).pack(side=tk.LEFT, padx=(0, 16))
        tk.Checkbutton(
            row2, text="Backup auto", variable=self._backup,
            bg=C["bg"], fg=C["text"], selectcolor=C["card"],
            activebackground=C["bg"], font=("Consolas", 9),
        ).pack(side=tk.LEFT)

        # Ligne 3 : boutons
        row3 = tk.Frame(self, bg=C["bg"])
        row3.pack(fill=tk.X, padx=12, pady=8)
        self._btn(row3, "Appliquer le patch", C["green"],  self._apply).pack(side=tk.LEFT, padx=(0, 8))
        self._btn(row3, "Dry-run rapide",     C["blue"],   self._dryrun_quick).pack(side=tk.LEFT, padx=(0, 8))
        self._btn(row3, "Stop",               C["red"],    self._runner.stop).pack(side=tk.LEFT)

        # Info chemin patcher
        tk.Label(
            self, text=f"patcher.py : {PATCHER_PATH}",
            bg=C["bg"], fg=C["dim"], font=("Consolas", 8),
        ).pack(anchor=tk.W, padx=12)

    def _btn(self, parent, label, color, cmd):
        return tk.Button(
            parent, text=label, bg=C["panel"], fg=color,
            font=("Consolas", 9, "bold"), relief=tk.FLAT,
            cursor="hand2", padx=10, pady=6, command=cmd,
            activebackground=C["card"], activeforeground=color,
        )

    def _browse(self):
        path = filedialog.askopenfilename(
            title="Choisir le bundle de patches",
            filetypes=[("Fichiers texte", "*.txt"), ("Tous", "*.*")],
        )
        if path:
            self._bundle_var.set(path)

    def _build_cmd(self) -> list:
        cmd = [sys.executable, str(PATCHER_PATH), "--bundle", self._bundle_var.get()]
        if self._dryrun.get():
            cmd.append("--dry-run")
        if not self._backup.get():
            cmd.append("--no-backup")
        return cmd

    def _apply(self):
        bundle = Path(self._bundle_var.get())
        if not bundle.exists() and not bundle.is_absolute():
            bundle = _ROOT / bundle
        if not bundle.exists():
            messagebox.showerror("Hub", f"Bundle introuvable :\n{bundle}")
            return
        self._runner.run(self._build_cmd(), cwd=_ROOT)

    def _dryrun_quick(self):
        old = self._dryrun.get()
        self._dryrun.set(True)
        self._apply()
        self._dryrun.set(old)


# ── Onglet Auditeur ───────────────────────────────────────────────────────────
class TabAuditeur(tk.Frame):

    def __init__(self, parent, runner: Runner):
        super().__init__(parent, bg=C["bg"])
        self._runner = runner
        self._build()

    def _build(self):
        # Info chemin
        tk.Label(
            self, text=f"Script : {AUDITEUR_PY}",
            bg=C["bg"], fg=C["dim"], font=("Consolas", 8),
        ).pack(anchor=tk.W, padx=12, pady=(10, 2))

        info = (
            "Lance aAa_Auditeur.py dans son dossier.\n"
            "Audite les 20 premiers .py du dossier aAa_Auditeur/\n"
            "et produit rapport_erreurs.txt dans ce meme dossier."
        )
        tk.Label(
            self, text=info, bg=C["bg"], fg=C["text"],
            font=("Consolas", 9), justify=tk.LEFT,
        ).pack(anchor=tk.W, padx=12, pady=(0, 10))

        row = tk.Frame(self, bg=C["bg"])
        row.pack(fill=tk.X, padx=12, pady=4)

        # Dossier cible (dossier dans lequel l'auditeur tournera)
        tk.Label(row, text="Dossier a auditer :", bg=C["bg"], fg=C["text"],
                 font=("Consolas", 9)).pack(side=tk.LEFT, padx=(0, 6))
        self._target_var = tk.StringVar(value=str(AUDITEUR_DIR))
        tk.Entry(
            row, textvariable=self._target_var,
            bg=C["card"], fg=C["text"], insertbackground=C["blue"],
            font=("Consolas", 9), relief=tk.FLAT, width=38,
        ).pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 6))
        tk.Button(
            row, text="...", bg=C["panel"], fg=C["cyan"],
            font=("Consolas", 9), relief=tk.FLAT, cursor="hand2",
            command=self._browse_dir,
        ).pack(side=tk.LEFT)

        row2 = tk.Frame(self, bg=C["bg"])
        row2.pack(fill=tk.X, padx=12, pady=8)
        self._btn(row2, "Lancer l'audit",     C["green"],  self._run).pack(side=tk.LEFT, padx=(0, 8))
        self._btn(row2, "Ouvrir le rapport",  C["blue"],   self._open_report).pack(side=tk.LEFT, padx=(0, 8))
        self._btn(row2, "Stop",               C["red"],    self._runner.stop).pack(side=tk.LEFT)

    def _btn(self, parent, label, color, cmd):
        return tk.Button(
            parent, text=label, bg=C["panel"], fg=color,
            font=("Consolas", 9, "bold"), relief=tk.FLAT,
            cursor="hand2", padx=10, pady=6, command=cmd,
            activebackground=C["card"], activeforeground=color,
        )

    def _browse_dir(self):
        d = filedialog.askdirectory(title="Dossier a auditer")
        if d:
            self._target_var.set(d)

    def _run(self):
        if not AUDITEUR_PY.exists():
            messagebox.showerror("Hub", f"Introuvable :\n{AUDITEUR_PY}")
            return
        cwd = Path(self._target_var.get())
        if not cwd.exists():
            messagebox.showerror("Hub", f"Dossier introuvable :\n{cwd}")
            return
        self._runner.run([sys.executable, str(AUDITEUR_PY)], cwd=cwd)

    def _open_report(self):
        cwd    = Path(self._target_var.get())
        report = cwd / "rapport_erreurs.txt"
        if not report.exists():
            messagebox.showinfo("Hub", "Aucun rapport trouve. Lance d'abord l'audit.")
            return
        os.startfile(str(report))  # Windows : ouvre avec le bloc-notes


# ── Onglet SyntaxCheck ────────────────────────────────────────────────────────
class TabSyntaxCheck(tk.Frame):

    def __init__(self, parent, runner: Runner):
        super().__init__(parent, bg=C["bg"])
        self._runner = runner
        self._build()

    def _build(self):
        tk.Label(
            self, text=f"Script : {SYNTAX_PY}",
            bg=C["bg"], fg=C["dim"], font=("Consolas", 8),
        ).pack(anchor=tk.W, padx=12, pady=(10, 2))

        info = (
            "Verifie la syntaxe de tous les .py via ast.parse()\n"
            "sans executer le code. Plus rapide que l'Auditeur.\n"
            "Lance dans le dossier cible choisi."
        )
        tk.Label(
            self, text=info, bg=C["bg"], fg=C["text"],
            font=("Consolas", 9), justify=tk.LEFT,
        ).pack(anchor=tk.W, padx=12, pady=(0, 10))

        row = tk.Frame(self, bg=C["bg"])
        row.pack(fill=tk.X, padx=12, pady=4)
        tk.Label(row, text="Dossier cible :", bg=C["bg"], fg=C["text"],
                 font=("Consolas", 9)).pack(side=tk.LEFT, padx=(0, 6))
        self._target_var = tk.StringVar(value=str(_ROOT / "agents"))
        tk.Entry(
            row, textvariable=self._target_var,
            bg=C["card"], fg=C["text"], insertbackground=C["blue"],
            font=("Consolas", 9), relief=tk.FLAT, width=38,
        ).pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 6))
        tk.Button(
            row, text="...", bg=C["panel"], fg=C["cyan"],
            font=("Consolas", 9), relief=tk.FLAT, cursor="hand2",
            command=self._browse_dir,
        ).pack(side=tk.LEFT)

        row2 = tk.Frame(self, bg=C["bg"])
        row2.pack(fill=tk.X, padx=12, pady=8)
        self._btn(row2, "Verifier la syntaxe", C["green"], self._run).pack(side=tk.LEFT, padx=(0, 8))
        self._btn(row2, "Scan rapide agents/", C["blue"],  self._scan_agents).pack(side=tk.LEFT, padx=(0, 8))
        self._btn(row2, "Stop",                C["red"],   self._runner.stop).pack(side=tk.LEFT)

    def _btn(self, parent, label, color, cmd):
        return tk.Button(
            parent, text=label, bg=C["panel"], fg=color,
            font=("Consolas", 9, "bold"), relief=tk.FLAT,
            cursor="hand2", padx=10, pady=6, command=cmd,
            activebackground=C["card"], activeforeground=color,
        )

    def _browse_dir(self):
        d = filedialog.askdirectory(title="Dossier a analyser")
        if d:
            self._target_var.set(d)

    def _run(self):
        if not SYNTAX_PY.exists():
            messagebox.showerror("Hub", f"Introuvable :\n{SYNTAX_PY}")
            return
        cwd = Path(self._target_var.get())
        if not cwd.exists():
            messagebox.showerror("Hub", f"Dossier introuvable :\n{cwd}")
            return
        self._runner.run([sys.executable, str(SYNTAX_PY)], cwd=cwd)

    def _scan_agents(self):
        """Raccourci : scan le dossier agents/ directement."""
        self._target_var.set(str(_ROOT / "agents"))
        self._run()


# ── Fenetre principale ─────────────────────────────────────────────────────────
class MaintenanceHub(tk.Tk):

    def __init__(self):
        super().__init__()
        self.title("Ov3rLoRd — Maintenance Hub V1.49")
        self.geometry("820x600")
        self.minsize(700, 480)
        self.configure(bg=C["bg"])
        self._build()

    def _build(self):
        # ── Header ────────────────────────────────────────────────────────────
        hdr = tk.Frame(self, bg=C["panel"], height=44)
        hdr.pack(fill=tk.X)
        hdr.pack_propagate(False)
        tk.Label(
            hdr, text="Ov3rLoRd  Maintenance Hub",
            bg=C["panel"], fg=C["blue"],
            font=("Consolas", 14, "bold"),
        ).pack(side=tk.LEFT, padx=14, pady=8)
        tk.Label(
            hdr, text="V1.49",
            bg=C["panel"], fg=C["dim"],
            font=("Consolas", 10),
        ).pack(side=tk.LEFT)

        # ── Corps ─────────────────────────────────────────────────────────────
        body = tk.Frame(self, bg=C["bg"])
        body.pack(fill=tk.BOTH, expand=True, padx=8, pady=8)

        # Notebook (onglets)
        style = ttk.Style()
        style.theme_use("default")
        style.configure("TNotebook",          background=C["bg"],    borderwidth=0)
        style.configure("TNotebook.Tab",      background=C["panel"], foreground=C["dim"],
                        font=("Consolas", 10, "bold"), padding=[14, 6])
        style.map("TNotebook.Tab",
                  background=[("selected", C["card"])],
                  foreground=[("selected", C["blue"])])

        nb = ttk.Notebook(body)
        nb.pack(fill=tk.BOTH, expand=True, side=tk.TOP)

        # Console partagee (en bas)
        console_frame = tk.Frame(body, bg=C["bg"])
        console_frame.pack(fill=tk.BOTH, expand=True, side=tk.BOTTOM, pady=(6, 0))
        tk.Label(
            console_frame, text="CONSOLE",
            bg=C["bg"], fg=C["dim"], font=("Consolas", 8, "bold"),
        ).pack(anchor=tk.W)
        self._console = Console(console_frame)
        self._console.pack(fill=tk.BOTH, expand=True)

        # Runner partage
        self._runner = Runner(self._console, status_cb=self._set_status)

        # Onglets
        tab_patcher = TabPatcher(nb, self._runner)
        tab_audit   = TabAuditeur(nb, self._runner)
        tab_syntax  = TabSyntaxCheck(nb, self._runner)

        nb.add(tab_patcher, text="  Patcher  ")
        nb.add(tab_audit,   text="  Auditeur  ")
        nb.add(tab_syntax,  text="  SyntaxCheck  ")

        # Ajuster la hauteur du notebook vs console
        nb.configure(height=220)

        # ── Status bar ────────────────────────────────────────────────────────
        self._status_var = tk.StringVar(value="Pret.")
        self._status_col = tk.StringVar(value=C["dim"])
        sb = tk.Frame(self, bg=C["panel"], height=24)
        sb.pack(fill=tk.X, side=tk.BOTTOM)
        sb.pack_propagate(False)
        self._status_lbl = tk.Label(
            sb, textvariable=self._status_var,
            bg=C["panel"], fg=C["dim"],
            font=("Consolas", 9), anchor=tk.W,
        )
        self._status_lbl.pack(side=tk.LEFT, padx=10)
        self._clock_lbl = tk.Label(
            sb, text="",
            bg=C["panel"], fg=C["dim"],
            font=("Consolas", 9),
        )
        self._clock_lbl.pack(side=tk.RIGHT, padx=10)
        self._tick()

    def _set_status(self, msg: str, color: str = None):
        def _do():
            self._status_lbl.config(text=msg, fg=color or C["dim"])
        self.after(0, _do)

    def _tick(self):
        self._clock_lbl.config(text=datetime.now().strftime("%H:%M:%S"))
        self.after(1000, self._tick)


if __name__ == "__main__":
    app = MaintenanceHub()
    app.mainloop()
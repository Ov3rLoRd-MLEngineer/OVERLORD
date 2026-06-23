"""
launcher.py v3 -- OverLord Pipeline GUI
FIX V1.49p : _session_elapsed et _session_start initialises dans __init__
             (AttributeError a la fermeture de l'app).
"""
import sys, os, json, threading, queue, subprocess, time, io
from pathlib import Path
from datetime import datetime

def resource_path(rel):
    base = getattr(sys, "_MEIPASS", Path(__file__).parent)
    return str(Path(base) / rel)

try:
    import customtkinter as ctk
    CTK_OK = True
except ImportError:
    CTK_OK = False

import tkinter as tk
from tkinter import ttk, messagebox, filedialog

try:
    from PIL import Image, ImageTk
    PIL_OK = True
except ImportError:
    PIL_OK = False

try:
    sys.path.insert(0, str(Path(__file__).parent / "agents"))
    from sav_agent     import SAVAgent
    from ollama_bridge import OllamaBridge, LLMMode, ONLINE_LABELS, OFFLINE_LABELS
    AGENTS_OK = True
except Exception as e:
    AGENTS_OK = False
    # Fallbacks pour les labels si ollama_bridge absent
    ONLINE_LABELS  = {"claude-sonnet-4-6":"Claude Sonnet 4.6","gpt-4o":"GPT-4o"}
    OFFLINE_LABELS = {"llama3":"Llama 3","mistral":"Mistral","deepseek-coder":"DeepSeek Coder"}

SETTINGS_FILE  = Path("settings.json")
NODE_CATALOG_F = resource_path("node_catalog.json")
WORKFLOW_FILE  = resource_path("Combined_V35_API.json")
MAESTRO_SCRIPT = resource_path("maestro.py")
APP_NAME, APP_VERSION = "OverLord", "v1.0.0-alpha"
WIN_W, WIN_H   = 1240, 820
SASH_MIN, SASH_MAX = 260, 620

MEDIA_TYPES    = ["anime","manga","comics","3d","photoreal","art","game","short","film"]
DURATION_TYPES = ["15 sec (Short/Reel)","30 sec","1 min","2 min","5 min",
                  "10 min (Episode court)","22 min (Episode anime)","44 min (Episode long)",
                  "90 min (Film)","120 min (Long metrage)",
                  "10 images","25 images","50 images","100 images","200 images",
                  "8 planches (manga)","24 planches (chapitre)","180 planches (volume)",
                  "22 pages (comics issue)","1 illustration","Serie (nb libre)"]
SAMPLERS       = ["euler_ancestral","euler","dpm++_2m","dpm++_2m_sde","dpm++_3m_sde","dpm++_sde","dpm_fast","lcm","ddim","uni_pc"]
SCHEDULERS     = ["normal","karras","exponential","sgm_uniform"]
DEFAULT_CKPTS  = ["noobaiXLNSFWPony_epsilonPred10.safetensors",
                  "illustriousXL_v01.safetensors","fabricatedXL_v70.safetensors"]
DEFAULT_VAES   = ["sdxl_vae.safetensors",""]
DEFAULT_POS    = "masterpiece, best quality, amazing quality, absurdres, 1girl, solo, looking at viewer,"
DEFAULT_NEG    = "bad quality, worst quality, worst detail, sketch, bad hands, bad anatomy, deformed, watermark"
DEFAULT_QWEN   = ("## Role\nYou are a professional prompt engineer specialized in "
                  "Booru-style tagging for SDXL anime models like NoobAI.\n"
                  "Expand the user input into a comprehensive positive prompt.\n"
                  "Output ONLY comma-separated tags, no headers, no explanations.")

PAL = {
    "dark": dict(bg="#0C0C10",surf="#13131A",surf2="#1A1A24",surf3="#22222E",
                 border="#2D2D3E",accent="#7C3AED",accent2="#A855F7",accentg="#5B21B6",
                 text="#E8E8F2",textd="#8080A0",textm="#404060",
                 ok="#10B981",warn="#F59E0B",err="#EF4444",
                 logbg="#08080C",logtxt="#A0FFA8",
                 btnpri="#7C3AED",btnhov="#6D28D9",btntxt="#FFFFFF",sash="#7C3AED"),
    "light": dict(bg="#F2F0FA",surf="#FFFFFF",surf2="#F8F6FF",surf3="#EDE9FA",
                  border="#D0CCEE",accent="#6D28D9",accent2="#7C3AED",accentg="#A78BFA",
                  text="#18182E",textd="#5A5A80",textm="#9090B0",
                  ok="#059669",warn="#D97706",err="#DC2626",
                  logbg="#0C0C18",logtxt="#A0FFA8",
                  btnpri="#6D28D9",btnhov="#5B21B6",btntxt="#FFFFFF",sash="#6D28D9"),
}

DEF = dict(theme="dark",sash_x=400,media_type="anime",duration="short",universe="",
           checkpoint=DEFAULT_CKPTS[0],vae=DEFAULT_VAES[0],lora="",det_lora="",
           strength="1.0",width="1024",height="1536",steps="28",cfg="6",
           sampler="euler_ancestral",scheduler="normal",denoise="1.0",seed="-1",
           positive=DEFAULT_POS,negative=DEFAULT_NEG,qwen_prompt=DEFAULT_QWEN,
           bg_image="",bg_opacity=0.35,llm_mode="offline",
           llm_online="claude-sonnet-4-6",llm_offline="llama3",
           api_key_openai="",api_key_google="",visible_nodes={},
           session_elapsed=0.0, current_project="Nouveau projet")

def load_settings():
    try:
        if SETTINGS_FILE.exists():
            return {**DEF, **json.loads(SETTINGS_FILE.read_text(encoding="utf-8"))}
    except Exception: pass
    return dict(DEF)

def save_settings(cfg):
    SETTINGS_FILE.write_text(json.dumps(cfg,indent=2,ensure_ascii=False),encoding="utf-8")

def load_node_catalog():
    try: return json.loads(Path(NODE_CATALOG_F).read_text(encoding="utf-8"))
    except Exception: return []

def create_shortcut(name, target, args):
    try:
        import win32com.client
        desk = Path(os.path.expanduser("~"))/"Desktop"
        sc = win32com.client.Dispatch("WScript.Shell").CreateShortcut(str(desk/f"{name}.lnk"))
        sc.TargetPath=target; sc.Arguments=args
        sc.WorkingDirectory=str(Path(target).parent); sc.save(); return True
    except Exception:
        bat = Path(os.path.expanduser("~"))/"Desktop"/f"{name}.bat"
        bat.write_text(f'@echo off\n"{target}" {args}\npause\n',encoding="utf-8"); return True


# ── AnimatedProgressBar ───────────────────────────────────────────────
class AnimatedProgressBar(tk.Canvas):
    def __init__(self, parent, P, height=18, **kw):
        super().__init__(parent, height=height, highlightthickness=0, bd=0, **kw)
        self.P=P; self.h=height; self._v=0.0; self._anim=False
        self._phase=0.0; self._after=None
        self.bind("<Configure>", lambda e: self._draw())

    def set(self, v, label=""):
        self._v=max(0.0,min(1.0,v)); self._label=label
        self._anim=(0.0<self._v<1.0); self._draw()
        if self._anim and not self._after: self._tick()

    def reset(self):
        self._v=0.0; self._label=""; self._anim=False
        if self._after: self.after_cancel(self._after); self._after=None
        self._draw()

    def _tick(self):
        if not self._anim: self._after=None; return
        self._phase=(self._phase+0.04)%1.0; self._draw()
        self._after=self.after(40, self._tick)

    def _draw(self):
        P=self.P; w=self.winfo_width() or 200; h=self.h
        self.delete("all")
        self.create_rectangle(0,2,w,h-2,fill=P["surf3"],outline="")
        fw=int(w*self._v)
        if fw>2:
            self.create_rectangle(0,2,fw,h-2,fill=P["accent"],outline="")
        if self._anim and fw>10:
            sx=int((fw-40)*self._phase)
            self.create_rectangle(sx,2,sx+30,h-2,fill=P["accent2"],outline="",stipple="gray50")
        pct=int(self._v*100)
        txt=f"{pct}%" if self._v>0 else "-"
        self.create_text(w//2,h//2,text=txt,fill=P["text"],font=("Segoe UI",7,"bold"))


# ── DraggableSash ─────────────────────────────────────────────────────
class DraggableSash(tk.Frame):
    def __init__(self, parent, P, on_drag, **kw):
        super().__init__(parent,width=8,cursor="sb_h_double_arrow",bg=P["sash"],**kw)
        self._on_drag=on_drag; self._x0=None
        self.bind("<ButtonPress-1>", lambda e: setattr(self,"_x0",e.x_root))
        self.bind("<B1-Motion>", lambda e: self._on_drag(e.x_root))
        self.bind("<Enter>", lambda e: self.configure(bg=P["accent2"]))
        self.bind("<Leave>", lambda e: self.configure(bg=P["sash"]))


# ════════════════════════════════════════════════════════════════════
class OverLordApp:
    def __init__(self):
        self.cfg=load_settings(); self.theme=self.cfg.get("theme","dark")
        self.P=PAL[self.theme]; self.node_catalog=load_node_catalog()
        self.log_queue=queue.Queue(); self.running=False; self._proc=None; self._timer_running=False
        self.vars={}; self._bg_photo=None; self._sash_x=self.cfg.get("sash_x",400)
        self._node_vars={}; self._cat_filter=None; self._titlebar_btns=[]

        # FIX V1.49p : initialiser AVANT _build_window (utilises dans _on_close et _tick_timer)
        self._session_start   = time.time()
        self._session_elapsed = float(self.cfg.get("session_elapsed", 0.0))
        self._timer_running   = True

        self.sav    = SAVAgent()     if AGENTS_OK else None
        self.bridge = OllamaBridge() if AGENTS_OK else None
        self._build_window(); self._build_ui()
        self._apply_theme_all(); self._restore_settings(); self._poll_logs()

    def _build_window(self):
        self.root=tk.Tk(); self.root.title(f"  {APP_NAME}  {APP_VERSION}")
        self.root.geometry(f"{WIN_W}x{WIN_H}"); self.root.minsize(760,500)
        self.root.protocol("WM_DELETE_WINDOW",self._on_close)
        self.root.update_idletasks()
        sw=self.root.winfo_screenwidth(); sh=self.root.winfo_screenheight()
        self.root.geometry(f"{WIN_W}x{WIN_H}+{(sw-WIN_W)//2}+{(sh-WIN_H)//2}")

    def _build_ui(self):
        P=self.P
        self.bg_canvas=tk.Canvas(self.root,highlightthickness=0,bd=0)
        self.bg_canvas.place(x=0,y=0,relwidth=1,relheight=1)
        self.root.bind("<Configure>",self._on_resize)
        self.titlebar=tk.Frame(self.root,height=52)
        self.titlebar.pack(fill="x",side="top"); self.titlebar.pack_propagate(False)
        self.lbl_title=tk.Label(self.titlebar,text=f"  {APP_NAME}  {APP_VERSION}",
            font=("Segoe UI",13,"bold"),anchor="w")
        self.lbl_title.pack(side="left",fill="y",padx=4)
        self._titlebar_btns=[]
        for icon,cmd in [("SAV",self._open_sav_panel),("SC",self._create_shortcut_dialog),
                          ("BG",self._open_bg_settings),
                          ("Theme",self._toggle_theme),
                          ("Noeuds",self._open_node_settings)]:
            b=tk.Button(self.titlebar,text=icon,font=("Segoe UI",10),
                        relief="flat",bd=0,cursor="hand2",command=cmd,padx=10,pady=4)
            b.pack(side="right",padx=2); self._titlebar_btns.append(b)
        self.btn_theme=self._titlebar_btns[3]
        self.main=tk.Frame(self.root); self.main.pack(fill="both",expand=True)
        self.left_frame=tk.Frame(self.main)
        self.left_frame.place(x=0,y=0,width=self._sash_x,relheight=1.0)
        self.sash=DraggableSash(self.main,P,self._on_sash_drag)
        self.sash.place(x=self._sash_x,y=0,width=8,relheight=1.0)
        self.right_frame=tk.Frame(self.main)
        self.right_frame.place(x=self._sash_x+8,y=0,relheight=1.0)
        self._upd_right(); self._build_left(); self._build_right()

    def _upd_right(self):
        total=self.main.winfo_width() or WIN_W
        rw=max(200,total-self._sash_x-8)
        self.right_frame.place(x=self._sash_x+8,y=0,width=rw,relheight=1.0)

    def _on_sash_drag(self,x_root):
        ox=self.main.winfo_rootx(); nx=max(SASH_MIN,min(SASH_MAX,x_root-ox))
        self._sash_x=nx; self.left_frame.place(width=nx)
        self.sash.place(x=nx); self._upd_right()

    def _on_resize(self,e=None): self._upd_right(); self._draw_bg()

    def _build_left(self):
        f=self.left_frame
        self.bottom_fixed = tk.Frame(f)
        self.bottom_fixed.pack(side="bottom", fill="x")
        scroll_zone = tk.Frame(f)
        scroll_zone.pack(side="top", fill="both", expand=True)
        cv=tk.Canvas(scroll_zone,highlightthickness=0,bd=0)
        sc=tk.Scrollbar(scroll_zone,orient="vertical",command=cv.yview)
        self.form=tk.Frame(cv)
        self.form.bind("<Configure>",lambda e: cv.configure(scrollregion=cv.bbox("all")))
        cv.create_window((0,0),window=self.form,anchor="nw")
        cv.configure(yscrollcommand=sc.set)
        cv.pack(side="left",fill="both",expand=True); sc.pack(side="right",fill="y")
        cv.bind_all("<MouseWheel>",lambda e: cv.yview_scroll(-1*(e.delta//120),"units"))
        self._left_cv=cv

        def sep(txt=""):
            fr=tk.Frame(self.form); fr.pack(fill="x",padx=12,pady=(14,2))
            if txt: tk.Label(fr,text=txt,font=("Segoe UI",9,"bold"),anchor="w").pack(side="left")
            tk.Frame(fr,height=1).pack(fill="x",pady=(4,0))

        def lbl(t): tk.Label(self.form,text=t,font=("Segoe UI",9),anchor="w").pack(fill="x",padx=16,pady=(5,0))

        def entry(key,default=""):
            v=tk.StringVar(value=str(default)); self.vars[key]=v
            e=tk.Entry(self.form,textvariable=v,font=("Segoe UI",9),relief="flat",bd=1)
            e.pack(fill="x",padx=16,pady=2); return v

        def combo(key,choices,default=""):
            v=tk.StringVar(value=default or(choices[0] if choices else "")); self.vars[key]=v
            cb=ttk.Combobox(self.form,textvariable=v,values=choices,state="readonly",font=("Segoe UI",9))
            cb.pack(fill="x",padx=16,pady=2); return v

        def txt_area(key,default="",height=4):
            t=tk.Text(self.form,height=height,font=("Segoe UI",9),wrap="word",relief="flat",bd=1)
            t.insert("1.0",default); t.pack(fill="x",padx=16,pady=2); self.vars[key]=t; return t

        sep("LLM MODE")
        llm_row=tk.Frame(self.form); llm_row.pack(fill="x",padx=16,pady=4)
        tk.Label(llm_row,text="Offline",font=("Segoe UI",9)).pack(side="left")
        self._llm_btn=tk.Button(llm_row,text="  OFFLINE",font=("Segoe UI",8,"bold"),
            relief="flat",bd=0,cursor="hand2",padx=10,pady=3,command=self._toggle_llm_mode)
        self._llm_btn.pack(side="left",padx=8)
        tk.Label(llm_row,text="Online",font=("Segoe UI",9)).pack(side="left")
        ol_labs  = list(ONLINE_LABELS.values())
        off_labs = list(OFFLINE_LABELS.values())
        lbl("Modele Online"); combo("llm_online",ol_labs,self.cfg.get("llm_online","claude-sonnet-4-6"))
        lbl("Modele Offline (Ollama local)"); v_off=combo("llm_offline",off_labs,self.cfg.get("llm_offline","llama3"))
        v_off.trace_add("write",self._check_ollama_model)

        sep("PIPELINE")
        lbl("Type de media"); combo("media_type",MEDIA_TYPES,self.cfg.get("media_type","anime"))
        lbl("Duree / Quantite")
        dur_row = tk.Frame(self.form); dur_row.pack(fill="x", padx=16, pady=2)
        dur_val_var = tk.StringVar(value=str(self.cfg.get("duration_value","22")))
        self.vars["duration_value"] = dur_val_var
        tk.Entry(dur_row, textvariable=dur_val_var, font=("Segoe UI",10),
                 relief="flat", bd=1, width=8).pack(side="left")
        DURATION_UNITS = ["secondes","minutes","heures","images","planches manga",
                          "pages comics","illustrations","plans storyboard","scenes"]
        dur_unit_var = tk.StringVar(value=self.cfg.get("duration_unit","minutes"))
        self.vars["duration_unit"] = dur_unit_var
        ttk.Combobox(dur_row, textvariable=dur_unit_var, values=DURATION_UNITS,
                     state="readonly", font=("Segoe UI",9), width=16).pack(side="left", padx=6)
        self.lbl_duration_calc = tk.Label(dur_row, text="", font=("Segoe UI",7), anchor="w")
        self.lbl_duration_calc.pack(side="left", padx=4)
        def _update_dur(*_):
            try:
                val  = float(dur_val_var.get() or 0)
                unit = dur_unit_var.get()
                if unit == "secondes":  shots = max(1, int(val / 3))
                elif unit == "minutes": shots = max(1, int(val * 20))
                elif unit == "heures":  shots = max(1, int(val * 1200))
                else:                   shots = max(1, int(val))
                self.lbl_duration_calc.configure(text=f"~{shots} shots")
            except Exception:
                self.lbl_duration_calc.configure(text="")
        dur_val_var.trace_add("write", _update_dur)
        dur_unit_var.trace_add("write", _update_dur)
        _update_dur()
        lbl("Univers / Contexte"); entry("universe",self.cfg.get("universe",""))

        sep("MODELES")
        lbl("Checkpoint (.safetensors)"); combo("checkpoint",DEFAULT_CKPTS,self.cfg.get("checkpoint",DEFAULT_CKPTS[0]))
        lbl("VAE"); combo("vae",DEFAULT_VAES,self.cfg.get("vae",DEFAULT_VAES[0]))
        lbl("LoRA Principal"); entry("lora",self.cfg.get("lora",""))
        lbl("LoRA Detailer"); entry("det_lora",self.cfg.get("det_lora",""))
        lbl("Force LoRA"); entry("strength",self.cfg.get("strength","1.0"))

        sep("IMAGE")
        row1=tk.Frame(self.form); row1.pack(fill="x",padx=16,pady=2)
        for lab,key,dv in [("W","width","1024"),("H","height","1536"),("Steps","steps","28"),("CFG","cfg","6")]:
            c=tk.Frame(row1); c.pack(side="left",fill="x",expand=True,padx=2)
            tk.Label(c,text=lab,font=("Segoe UI",8)).pack(anchor="w")
            v=tk.StringVar(value=self.cfg.get(key,dv)); self.vars[key]=v
            tk.Entry(c,textvariable=v,font=("Segoe UI",9),relief="flat",bd=1,width=7).pack(fill="x")
        row2=tk.Frame(self.form); row2.pack(fill="x",padx=16,pady=2)
        for lab,key,choices in [("Sampler","sampler",SAMPLERS),("Scheduler","scheduler",SCHEDULERS)]:
            c=tk.Frame(row2); c.pack(side="left",fill="x",expand=True,padx=2)
            tk.Label(c,text=lab,font=("Segoe UI",8)).pack(anchor="w")
            v=tk.StringVar(value=self.cfg.get(key,choices[0])); self.vars[key]=v
            ttk.Combobox(c,textvariable=v,values=choices,state="readonly",font=("Segoe UI",8),width=12).pack(fill="x")
        row3=tk.Frame(self.form); row3.pack(fill="x",padx=16,pady=2)
        for lab,key,dv in [("Denoise","denoise","1.0"),("Seed","seed","-1")]:
            c=tk.Frame(row3); c.pack(side="left",fill="x",expand=True,padx=2)
            tk.Label(c,text=lab,font=("Segoe UI",8)).pack(anchor="w")
            v=tk.StringVar(value=self.cfg.get(key,dv)); self.vars[key]=v
            tk.Entry(c,textvariable=v,font=("Segoe UI",9),relief="flat",bd=1,width=10).pack(fill="x")

        sep("PROMPTS")
        lbl("Prompt Positif"); txt_area("positive",self.cfg.get("positive",DEFAULT_POS),height=5)
        lbl("Prompt Negatif"); txt_area("negative",self.cfg.get("negative",DEFAULT_NEG),height=4)
        lbl("Prompt QwenVL (Vision Agent)"); txt_area("qwen_prompt",self.cfg.get("qwen_prompt",DEFAULT_QWEN),height=5)

        sep("BLOC SSS -- Sourcing / Scenario / Storyboard")
        sss=tk.Frame(self.form); sss.pack(fill="x",padx=16,pady=6)
        for lab,bk in [("Sourcing","sourcing"),("Scenario","scenario"),("Storyboard","storyboard")]:
            tk.Button(sss,text=lab,font=("Segoe UI",8),relief="flat",bd=0,cursor="hand2",
                      pady=5,padx=8,command=lambda b=bk:self._launch_block(b)
                      ).pack(side="left",padx=3)

        sep("MODELISATION 3D")
        lbl("Mode 3D")
        combo("mode_3d", ["render (visuel)","print (STL resine)","both"],
              self.cfg.get("mode_3d","render (visuel)"))
        lbl("Prompt 3D")
        txt_area("prompt_3d", self.cfg.get("prompt_3d","Un personnage anime en tenue epique"), height=3)
        lbl("Dimensions STL (mm)  W x D x H")
        dim_row = tk.Frame(self.form); dim_row.pack(fill="x",padx=16,pady=2)
        for dkey, dlbl, ddef in [("stl_w","W",""),("stl_d","D",""),("stl_h","H","")]:
            c = tk.Frame(dim_row); c.pack(side="left",padx=3)
            tk.Label(c,text=dlbl,font=("Segoe UI",8)).pack(anchor="w")
            v = tk.StringVar(value=self.cfg.get(dkey,ddef)); self.vars[dkey]=v
            tk.Entry(c,textvariable=v,font=("Segoe UI",9),width=6,relief="flat",bd=1).pack()
        lbl("Moteur 3D")
        combo("engine_3d",
              ["Auto (meilleur disponible)","Shap-E (local)","TripoSR (image->3D)",
               "Meshy API (cloud)","OpenSCAD (parametrique)"],
              self.cfg.get("engine_3d","Auto (meilleur disponible)"))
        lbl("Cle API Meshy"); entry("meshy_api_key", self.cfg.get("meshy_api_key",""))
        d3_row = tk.Frame(self.form); d3_row.pack(fill="x",padx=16,pady=6)
        for lab,cmd in [("Generer 3D",self._launch_3d),
                         ("Valider STL",self._validate_stl),
                         ("Preparer slicer",self._prepare_slicer)]:
            tk.Button(d3_row,text=lab,font=("Segoe UI",8),relief="flat",bd=0,
                      cursor="hand2",pady=5,padx=6,command=cmd).pack(side="left",padx=2)

        tk.Frame(self.form, height=10).pack()

        bf_outer = self.bottom_fixed
        tk.Frame(bf_outer, height=2).pack(fill="x", padx=0, pady=0)
        hdr_prog = tk.Frame(bf_outer); hdr_prog.pack(fill="x", padx=12, pady=(8,2))
        tk.Label(hdr_prog, text="PROGRESSION", font=("Segoe UI",9,"bold"), anchor="w").pack(side="left")
        self.prog_bars={}; self.prog_lbls={}
        for bk,lab in [("sourcing","Sourcing"),("scenario","Scenario"),
                        ("storyboard","Storyboard"),("production","Production"),("postprod","Post-prod")]:
            row=tk.Frame(bf_outer); row.pack(fill="x",padx=16,pady=1)
            tk.Label(row,text=lab,font=("Segoe UI",8),width=15,anchor="w").pack(side="left")
            bar=AnimatedProgressBar(row,self.P,height=16)
            bar.pack(side="left",fill="x",expand=True,padx=4)
            ls=tk.Label(row,text="-",font=("Segoe UI",7),width=6); ls.pack(side="left")
            self.prog_bars[bk]=bar; self.prog_lbls[bk]=ls
        tk.Frame(bf_outer, height=1).pack(fill="x", padx=12, pady=(6,2))
        bf=tk.Frame(bf_outer); bf.pack(fill="x",padx=16,pady=6)
        self.btn_run=tk.Button(bf,text="LANCER LA PRODUCTION",
            font=("Segoe UI",10,"bold"),relief="flat",bd=0,cursor="hand2",pady=10,
            command=self._launch_pipeline); self.btn_run.pack(fill="x",pady=2)
        self.btn_stop=tk.Button(bf,text="ARRETER",font=("Segoe UI",9),
            relief="flat",bd=0,cursor="hand2",pady=5,state="disabled",
            command=self._stop_pipeline); self.btn_stop.pack(fill="x",pady=1)
        btn_row2 = tk.Frame(bf); btn_row2.pack(fill="x", pady=2)
        self.btn_comfy=tk.Button(btn_row2,text="ComfyUI seule",
            font=("Segoe UI",8),relief="flat",bd=0,cursor="hand2",pady=5,
            command=self._launch_comfy_only); self.btn_comfy.pack(side="left",fill="x",expand=True,padx=(0,2))
        self.btn_sc=tk.Button(btn_row2,text="Raccourci",
            font=("Segoe UI",8),relief="flat",bd=0,cursor="hand2",pady=5,
            command=self._create_shortcut_dialog); self.btn_sc.pack(side="left",fill="x",expand=True,padx=(2,0))
        tk.Frame(bf_outer, height=6).pack()

    def _build_right(self):
        f=self.right_frame
        hdr=tk.Frame(f,height=44); hdr.pack(fill="x"); hdr.pack_propagate(False)
        tk.Label(hdr,text="CONSOLE  OverLord",font=("Consolas",10,"bold"),
                 anchor="w",padx=14).pack(side="left",fill="y")
        self.lbl_sav=tk.Label(hdr,text="SAV OK" if AGENTS_OK else "SAV -",
                               font=("Segoe UI",8),anchor="e",padx=10)
        self.lbl_sav.pack(side="right",fill="y")
        tk.Button(hdr,text="Effacer",font=("Segoe UI",8),relief="flat",bd=0,
                  cursor="hand2",padx=10,
                  command=lambda:(self.log_text.configure(state="normal"),
                                  self.log_text.delete("1.0","end"),
                                  self.log_text.configure(state="disabled"))
                  ).pack(side="right",padx=4)
        lf=tk.Frame(f); lf.pack(fill="both",expand=True,padx=6,pady=(0,6))
        self.log_text=tk.Text(lf,font=("Consolas",9),wrap="word",
                              relief="flat",bd=0,state="disabled",cursor="arrow")
        sc=tk.Scrollbar(lf,command=self.log_text.yview)
        self.log_text.configure(yscrollcommand=sc.set)
        sc.pack(side="right",fill="y"); self.log_text.pack(fill="both",expand=True)
        for tag,fg in [("INFO","#A0FFA8"),("WARNING","#F59E0B"),("ERROR","#EF4444"),
                        ("SUCCESS","#10B981"),("BLOCK","#A855F7"),("DIM","#404060"),("SAV","#60D0FF")]:
            self.log_text.tag_config(tag,foreground=fg,
                font=("Consolas",9,"bold") if tag=="BLOCK" else ("Consolas",9))
        self._log("OverLord pret","SUCCESS")

    def _draw_bg(self):
        if not PIL_OK: return
        p=self.cfg.get("bg_image","")
        if not p or not Path(p).exists(): self.bg_canvas.delete("all"); return
        try:
            w=self.root.winfo_width() or WIN_W; h=self.root.winfo_height() or WIN_H
            img=Image.open(p).convert("RGB").resize((w,h),Image.LANCZOS)
            self._bg_photo=ImageTk.PhotoImage(img)
            self.bg_canvas.delete("all")
            self.bg_canvas.create_image(0,0,anchor="nw",image=self._bg_photo)
        except Exception as e: print(f"[BG] {e}")

    def _open_bg_settings(self):
        P=self.P; dlg=tk.Toplevel(self.root)
        dlg.title("Fond d'ecran"); dlg.geometry("460x270"); dlg.configure(bg=P["bg"]); dlg.resizable(False,False)
        tk.Label(dlg,text="Image de fond (.jpg/.png/.webp)",bg=P["bg"],fg=P["text"],
                 font=("Segoe UI",9)).pack(fill="x",padx=20,pady=(12,0))
        path_var=tk.StringVar(value=self.cfg.get("bg_image",""))
        row=tk.Frame(dlg,bg=P["bg"]); row.pack(fill="x",padx=20,pady=3)
        tk.Entry(row,textvariable=path_var,font=("Segoe UI",9),bg=P["surf2"],
                 fg=P["text"],relief="flat").pack(side="left",fill="x",expand=True)
        tk.Button(row,text="Parcourir",font=("Segoe UI",9),bg=P["surf3"],fg=P["text"],
                  relief="flat",cursor="hand2",padx=6,
                  command=lambda:path_var.set(filedialog.askopenfilename(
                      filetypes=[("Images","*.jpg *.jpeg *.png *.webp *.bmp")]
                  ) or path_var.get())).pack(side="left",padx=4)
        def apply():
            self.cfg["bg_image"]=path_var.get(); save_settings(self.cfg); self._draw_bg(); dlg.destroy()
        tk.Button(dlg,text="Appliquer",bg=P["accent"],fg="white",
                  font=("Segoe UI",10,"bold"),relief="flat",bd=0,cursor="hand2",
                  pady=8,command=apply).pack(fill="x",padx=20,pady=10)

    def _toggle_llm_mode(self):
        cur=self.cfg.get("llm_mode","offline")
        new="online" if cur=="offline" else "offline"
        self.cfg["llm_mode"]=new
        self._llm_btn.configure(text="  ONLINE" if new=="online" else "  OFFLINE")
        self._log(f"LLM -> {new.upper()}","INFO")

    def _check_ollama_model(self,*_):
        if not AGENTS_OK or not self.bridge: return
        if self.cfg.get("llm_mode","offline")!="offline": return
        model=self._get_var("llm_offline")
        if hasattr(self.bridge,"is_model_installed") and not self.bridge.is_model_installed(model):
            if messagebox.askyesno("Modele non installe",
                f"Le modele '{model}' n'est pas installe.\n"
                "Voulez-vous lancer le telechargement ?"):
                self._log(f"[BRIDGE] Pull : {model}","SAV")
                threading.Thread(target=lambda:(self.bridge.pull_model(model),
                    self._log(f"[BRIDGE] {model} installe","SUCCESS")),daemon=True).start()

    def _open_sav_panel(self):
        P=self.P; dlg=tk.Toplevel(self.root)
        dlg.title("SAV -- Diagnostic ComfyUI"); dlg.geometry("640x500"); dlg.configure(bg=P["bg"])
        tk.Label(dlg,text="Coller les logs d'erreur ComfyUI :",bg=P["bg"],fg=P["text"],
                 font=("Segoe UI",9)).pack(fill="x",padx=16,pady=(12,2))
        eb=tk.Text(dlg,height=10,font=("Consolas",8),bg=P["surf2"],fg=P["text"],relief="flat")
        eb.pack(fill="both",expand=True,padx=16,pady=4)
        rb=tk.Text(dlg,height=7,font=("Consolas",8),bg=P["logbg"],fg="#60D0FF",
                   relief="flat",state="disabled")
        rb.pack(fill="x",padx=16,pady=4)
        def run():
            log_txt=eb.get("1.0","end").strip()
            if not log_txt: messagebox.showinfo("SAV","Collez d'abord les logs."); return
            rb.configure(state="normal"); rb.delete("1.0","end")
            rb.insert("1.0","Analyse...\n"); rb.configure(state="disabled")
            def _d():
                txt=json.dumps(self.sav.diagnose_with_llm(log_txt,{}),indent=2,ensure_ascii=False) if self.sav else "Agent SAV non disponible."
                rb.configure(state="normal"); rb.delete("1.0","end"); rb.insert("1.0",txt); rb.configure(state="disabled")
            threading.Thread(target=_d,daemon=True).start()
        tk.Button(dlg,text="Diagnostiquer",bg=P["accent"],fg="white",
                  font=("Segoe UI",10,"bold"),relief="flat",bd=0,cursor="hand2",
                  pady=8,command=run).pack(fill="x",padx=16,pady=6)

    def _open_node_settings(self):
        P=self.P; dlg=tk.Toplevel(self.root)
        dlg.title("Parametres Noeuds"); dlg.geometry("780x620"); dlg.configure(bg=P["bg"])
        hdr=tk.Frame(dlg,bg=P["surf"],height=50); hdr.pack(fill="x"); hdr.pack_propagate(False)
        tk.Label(hdr,text="Noeuds du Workflow -- Ordre d'execution et Visibilite",
                 font=("Segoe UI",10,"bold"),bg=P["surf"],fg=P["text"],anchor="w",padx=16
                 ).pack(side="left",fill="y")
        fr=tk.Frame(dlg,bg=P["bg"]); fr.pack(fill="x",padx=16,pady=6)
        tk.Label(fr,text="Categorie:",bg=P["bg"],fg=P["textd"],font=("Segoe UI",9)).pack(side="left")
        self._cat_filter=tk.StringVar(value="tous")
        outer=tk.Frame(dlg,bg=P["bg"]); outer.pack(fill="both",expand=True,padx=16,pady=4)
        cv=tk.Canvas(outer,bg=P["bg"],highlightthickness=0)
        sc=tk.Scrollbar(outer,orient="vertical",command=cv.yview)
        inner=tk.Frame(cv,bg=P["bg"])
        inner.bind("<Configure>",lambda e:cv.configure(scrollregion=cv.bbox("all")))
        cv.create_window((0,0),window=inner,anchor="nw"); cv.configure(yscrollcommand=sc.set)
        sc.pack(side="right",fill="y"); cv.pack(side="left",fill="both",expand=True)
        self._node_cv=cv; self._node_inner=inner
        for cat in ["tous","production","detailer","avance","autre"]:
            tk.Radiobutton(fr,text=cat,variable=self._cat_filter,value=cat,
                           bg=P["bg"],fg=P["text"],selectcolor=P["accentg"],
                           activebackground=P["bg"],font=("Segoe UI",9),
                           command=lambda:self._refresh_nodes(inner)
                           ).pack(side="left",padx=5)
        self._build_node_rows(inner)
        ft=tk.Frame(dlg,bg=P["surf"],height=50); ft.pack(fill="x",side="bottom"); ft.pack_propagate(False)
        for txt,cmd in [("Sauvegarder",lambda:self._save_nodes(dlg)),
                        ("Tout ON",lambda:[v.set(True) for v in self._node_vars.values()]),
                        ("Prod seul",self._preset_prod)]:
            tk.Button(ft,text=txt,bg=P["accent"] if "Sauv" in txt else P["surf3"],
                      fg="white" if "Sauv" in txt else P["text"],
                      font=("Segoe UI",9),relief="flat",bd=0,cursor="hand2",
                      padx=14,pady=8,command=cmd).pack(side="right",padx=4,pady=8)

    def _build_node_rows(self,parent,cat="tous"):
        P=self.P
        for w in parent.winfo_children(): w.destroy()
        self._node_vars={}
        nodes=[n for n in self.node_catalog if cat=="tous" or n.get("category")==cat]
        cur=None
        for node in nodes:
            c=node.get("category","autre")
            if c!=cur:
                cur=c
                tk.Frame(parent,bg=P["border"],height=1).pack(fill="x",pady=(8,2))
                tk.Label(parent,text=f"  -- {c.upper()} --",bg=P["bg"],fg=P["accent2"],
                         font=("Segoe UI",8,"bold"),anchor="w").pack(fill="x",padx=8)
            saved=self.cfg.get("visible_nodes",{}).get(node["id"],node.get("default_visible",False))
            var=tk.BooleanVar(value=saved); self._node_vars[node["id"]]=var
            row=tk.Frame(parent,bg=P["surf"] if saved else P["bg"],cursor="hand2")
            row.pack(fill="x",pady=1)
            def _tog(r=row,v=var): v.set(not v.get()); r.configure(bg=P["surf"] if v.get() else P["bg"])
            row.bind("<Button-1>",lambda e,fn=_tog:fn())
            tk.Checkbutton(row,variable=var,bg=row.cget("bg"),activebackground=row.cget("bg"),
                           selectcolor=P["accentg"],relief="flat",bd=0,
                           command=lambda r=row,v=var:r.configure(bg=P["surf"] if v.get() else P["bg"])
                           ).pack(side="left",padx=6)
            for txt,w2,fg,fnt in [(node["id"],5,P["textm"],("Consolas",8)),
                                   (node.get("label",node["id"]),26,P["text"],("Segoe UI",9)),
                                   (c,10,P["accent2"],("Segoe UI",8)),
                                   (node.get("description","")[:48],36,P["textd"],("Segoe UI",8))]:
                tk.Label(row,text=txt,font=fnt,bg=row.cget("bg"),fg=fg,
                         width=w2,anchor="w",padx=3).pack(side="left")

    def _refresh_nodes(self,parent):
        cat=self._cat_filter.get() if self._cat_filter else "tous"
        self._build_node_rows(parent,cat)
        self._node_cv.configure(scrollregion=self._node_cv.bbox("all"))

    def _preset_prod(self):
        [self._node_vars[n["id"]].set(n.get("category")=="production")
         for n in self.node_catalog if n["id"] in self._node_vars]

    def _save_nodes(self,dlg):
        self.cfg["visible_nodes"]={k:v.get() for k,v in self._node_vars.items()}
        save_settings(self.cfg); self._log("Parametres noeuds sauvegardes","SUCCESS"); dlg.destroy()

    def _create_shortcut_dialog(self):
        P=self.P; dlg=tk.Toplevel(self.root)
        dlg.title("Raccourci Bureau"); dlg.geometry("480x220"); dlg.configure(bg=P["bg"])
        nv=tk.StringVar(value="OverLord Production")
        tk.Entry(dlg,textvariable=nv,font=("Segoe UI",10),bg=P["surf2"],fg=P["text"],relief="flat").pack(fill="x",padx=20,pady=4)
        def do():
            ok=create_shortcut(nv.get(),sys.executable,f'"{MAESTRO_SCRIPT}" {self._build_args()}')
            if ok: messagebox.showinfo("OK",f"Raccourci '{nv.get()}' cree"); dlg.destroy()
        tk.Button(dlg,text="Creer",bg=P["accent"],fg="white",font=("Segoe UI",10,"bold"),
                  relief="flat",bd=0,cursor="hand2",pady=8,command=do).pack(fill="x",padx=20,pady=12)

    def _build_args(self):
        p=[]; m=self._get_var("media_type")
        if m: p.append(f'--media-type "{m}"')
        u=self._get_var("universe")
        if u: p.append(f'--universe "{u}"')
        l=self._get_var("lora")
        if l: p.append(f'--lora "{l}"')
        return " ".join(p)

    def _get_var(self,key):
        v=self.vars.get(key)
        if v is None: return ""
        if isinstance(v,tk.Text): return v.get("1.0","end").strip()
        return v.get().strip()

    def _save_current(self):
        for k,var in self.vars.items():
            if isinstance(var,tk.Text): self.cfg[k]=var.get("1.0","end").strip()
            elif isinstance(var,(tk.StringVar,tk.DoubleVar,tk.BooleanVar)):
                try: self.cfg[k]=var.get()
                except Exception: pass
        save_settings(self.cfg)

    def _build_wf(self):
        try:
            with open(WORKFLOW_FILE,encoding="utf-8") as f: wf=json.load(f)
        except Exception as e: self._log(f"Workflow introuvable : {e}","ERROR"); return None
        import random
        seed=int(self._get_var("seed") or -1)
        if seed<0: seed=random.randint(1,999_999_999_999)
        ckpt=self._get_var("checkpoint") or DEFAULT_CKPTS[0]
        for nid,node in wf.items():
            if node.get("class_type")=="CheckpointLoaderSimple": node["inputs"]["ckpt_name"]=ckpt
        for nid,val in [("112",seed),("382",seed)]:
            if nid in wf: wf[nid]["inputs"]["seed"]=val
        w=int(self._get_var("width") or 1024); h=int(self._get_var("height") or 1536)
        if "75" in wf: wf["75"]["inputs"]["value"]=w
        if "77" in wf: wf["77"]["inputs"]["value"]=h
        lora=self._get_var("lora"); st=float(self._get_var("strength") or 1.0)
        if "62" in wf:
            wf["62"]["inputs"]["loras"]={"__value__":[{"lora":lora,"strength":st,"enabled":True}]} if lora else {"__value__":[]}
        pos=self._get_var("positive"); neg=self._get_var("negative")
        for nid,key,val in [("87","string_b",pos),("99","string_a",pos),
                             ("111","text",neg),("301","text",pos),("380","text",neg)]:
            if nid in wf: wf[nid]["inputs"][key]=val
        steps=int(self._get_var("steps") or 28); cfg_v=float(self._get_var("cfg") or 6)
        if "64" in wf:
            wf["64"]["inputs"].update({"steps":steps,"cfg":cfg_v,
                "sampler":self._get_var("sampler") or "euler_ancestral",
                "scheduler":self._get_var("scheduler") or "normal"})
        return wf

    def _launch_pipeline(self):
        if self.running: return
        self._save_current(); self._reset_progress()
        self._log("="*40,"BLOCK"); self._log("PIPELINE DEMARRE","BLOCK"); self._log("="*40,"BLOCK")
        self._set_running(True)
        cfg={k:self._get_var(k) for k in ["media_type","duration","universe","lora","det_lora","positive","negative","checkpoint"]}
        cfg["strength"]=float(self._get_var("strength") or 1.0)
        cfg["width"]=int(self._get_var("width") or 1024); cfg["height"]=int(self._get_var("height") or 1536)
        threading.Thread(target=self._run_pipeline_thread,args=(cfg,),daemon=True).start()

    def _launch_comfy_only(self):
        if self.running: return
        self._save_current(); wf=self._build_wf()
        if not wf: return
        if self.sav and hasattr(self.sav,"detect_bugs"):
            bugs=self.sav.detect_bugs(wf)
            if bugs: self._log(f"[SAV] Bugs detectes : {bugs}","SAV")
        self._set_running(True); self._log("Production ComfyUI","BLOCK")
        def run():
            try:
                import requests as req
                r=req.post("http://127.0.0.1:8188/prompt",json={"prompt":wf},timeout=30)
                if r.status_code==200:
                    pid=r.json().get("prompt_id","?")
                    self.log_queue.put(("SUCCESS",f"Envoye  prompt_id={pid}"))
                    self._update_progress("production",0.05)
                    self._start_live_monitor(pid)
                else: self.log_queue.put(("ERROR",f"HTTP {r.status_code}: {r.text[:200]}"))
            except Exception as e: self.log_queue.put(("ERROR",str(e)))
            finally: self.log_queue.put(("__done__",""))
        threading.Thread(target=run,daemon=True).start()

    def _launch_block(self,block):
        if self.running: return
        self._save_current(); self._log(f"Bloc : {block}","BLOCK")
        self._update_progress(block,0.05)
        args=[sys.executable,MAESTRO_SCRIPT,"--from-block",block,
              "--media-type",self._get_var("media_type") or "anime"]
        if self._get_var("universe"): args+=["--universe",self._get_var("universe")]
        self._set_running(True)
        threading.Thread(target=self._subprocess_thread,args=(args,block),daemon=True).start()

    def _subprocess_thread(self,args,block=None):
        try:
            env = os.environ.copy()
            env["PYTHONUNBUFFERED"] = "1"
            env["PYTHONIOENCODING"] = "utf-8"
            proc=subprocess.Popen(args,stdout=subprocess.PIPE,stderr=subprocess.PIPE,
                                  text=True,encoding="utf-8",errors="replace",bufsize=1,env=env)
            def _read_stderr(p):
                for line in p.stderr:
                    line = line.rstrip()
                    if line:
                        self.log_queue.put(("WARNING" if "warn" in line.lower() else "ERROR" if "error" in line.lower() else "DIM", f"[stderr] {line}"))
            threading.Thread(target=_read_stderr, args=(proc,), daemon=True).start()
            self._proc=proc
            for line in proc.stdout:
                line=line.rstrip()
                if not line: continue
                ll=line.lower()
                lvl=("ERROR" if "error" in ll or "erreur" in ll
                     else "WARNING" if "warn" in ll
                     else "SUCCESS" if "termine" in ll
                     else "BLOCK" if "bloc" in ll
                     else "DIM" if "[debug]" in ll else "INFO")
                self.log_queue.put((lvl,line))
                for bk in ["sourcing","scenario","storyboard","production","postprod"]:
                    if bk in ll: self._update_progress(bk,0.5)
                if "termine" in ll:
                    if block: self._update_progress(block,1.0)
            proc.wait(); code=proc.returncode
            self.log_queue.put(("SUCCESS" if code==0 else "ERROR",f"Termine (code={code})"))
            if code==0:
                for bk in self.prog_bars: self._update_progress(bk,1.0)
        except Exception as e: self.log_queue.put(("ERROR",str(e)))
        finally: self._proc=None; self.log_queue.put(("__done__",""))

    def _run_pipeline_thread(self,cfg):
        try:
            tmp=Path("workspace/_gui_config.json"); tmp.parent.mkdir(exist_ok=True)
            tmp.write_text(json.dumps(cfg,ensure_ascii=False),encoding="utf-8")
            args=[sys.executable,MAESTRO_SCRIPT,"--config",str(tmp),"--media-type",cfg.get("media_type","anime")]
            if cfg.get("universe"): args+=["--universe",cfg["universe"]]
            if cfg.get("lora"):     args+=["--lora",cfg["lora"]]
            self._subprocess_thread(args)
        except Exception as e: self.log_queue.put(("ERROR",str(e))); self.log_queue.put(("__done__",""))

    def _start_live_monitor(self, prompt_id: str):
        import json as _json
        def _monitor():
            last_node = ""; beats = 0
            while self.running:
                time.sleep(2); beats += 1
                try:
                    import urllib.request as _ur
                    with _ur.urlopen(f"http://127.0.0.1:8188/history/{prompt_id}", timeout=5) as r:
                        hist = _json.loads(r.read())
                        if prompt_id in hist:
                            status = hist[prompt_id].get("status", {})
                            if status.get("completed"):
                                outputs = hist[prompt_id].get("outputs", {})
                                n_imgs  = sum(len(v.get("images",[])) for v in outputs.values())
                                self.log_queue.put(("SUCCESS", f"Generation terminee -- {n_imgs} image(s)"))
                                self._update_progress("production", 1.0)
                                break
                            elif status.get("status_str") == "error":
                                self.log_queue.put(("ERROR", "Erreur ComfyUI"))
                                break
                            elif beats % 5 == 0:
                                self.log_queue.put(("DIM", f"En cours... ({beats*2}s)"))
                except Exception: pass
        threading.Thread(target=_monitor, daemon=True).start()

    def _stop_pipeline(self):
        if self._proc:
            try: self._proc.terminate()
            except Exception: pass
        self._log("Arret demande.","WARNING")

    def _set_running(self,state):
        self.running=state
        self.btn_run.configure(state="disabled" if state else "normal",
            text="EN COURS..." if state else "LANCER LA PRODUCTION")
        self.btn_stop.configure(state="normal" if state else "disabled")

    def _update_progress(self,block,value):
        def _do():
            if block in self.prog_bars:
                self.prog_bars[block].set(value)
                self.prog_lbls[block].configure(text="OK" if value>=1.0 else f"{int(value*100)}%")
        self.root.after(0,_do)

    def _reset_progress(self):
        for bk in self.prog_bars: self.prog_bars[bk].reset(); self.prog_lbls[bk].configure(text="-")

    def _log(self,msg,level="INFO"): self.log_queue.put((level,msg))

    def _poll_logs(self):
        try:
            while True:
                level,msg=self.log_queue.get_nowait()
                if level=="__done__": self._set_running(False); continue
                ts=datetime.now().strftime("%H:%M:%S")
                self.log_text.configure(state="normal")
                self.log_text.insert("end",f"[{ts}] ","DIM")
                self.log_text.insert("end",f"{msg}\n",level)
                self.log_text.see("end"); self.log_text.configure(state="disabled")
        except queue.Empty: pass
        self.root.after(80,self._poll_logs)

    def _toggle_theme(self):
        self.theme="light" if self.theme=="dark" else "dark"
        self.P=PAL[self.theme]; self.cfg["theme"]=self.theme
        save_settings(self.cfg); self._apply_theme_all()
        for bar in self.prog_bars.values(): bar.P=self.P

    def _apply_theme_all(self):
        P=self.P; self.root.configure(bg=P["bg"])
        self._theme_w(self.root)
        self.log_text.configure(bg=P["logbg"],fg=P["logtxt"],insertbackground=P["text"])
        self.bg_canvas.configure(bg=P["bg"])
        self.titlebar.configure(bg=P["surf"]); self.lbl_title.configure(bg=P["surf"],fg=P["text"])
        for b in self._titlebar_btns: b.configure(bg=P["surf"],fg=P["text"],activebackground=P["surf3"])
        self.btn_run.configure(bg=P["btnpri"],fg=P["btntxt"],activebackground=P["btnhov"])
        for b in [self.btn_stop,self.btn_comfy,self.btn_sc]: b.configure(bg=P["surf3"],fg=P["text"])
        self.sash.configure(bg=P["sash"]); self._draw_bg()

    def _theme_w(self,w):
        P=self.P; cls=w.winfo_class()
        try:
            if cls=="Frame": w.configure(bg=P["bg"])
            elif cls=="Label": w.configure(bg=P["bg"],fg=P["text"])
            elif cls=="Entry": w.configure(bg=P["surf2"],fg=P["text"],insertbackground=P["text"],relief="flat")
            elif cls=="Text": w.configure(bg=P["surf2"],fg=P["text"],insertbackground=P["text"],relief="flat")
        except Exception: pass
        for child in w.winfo_children(): self._theme_w(child)

    def _restore_settings(self):
        for key,var in self.vars.items():
            val=self.cfg.get(key,"")
            if isinstance(var,tk.Text): var.delete("1.0","end"); var.insert("1.0",str(val))
            elif isinstance(var,(tk.StringVar,tk.DoubleVar,tk.BooleanVar)):
                try: var.set(val)
                except Exception: pass
        mode=self.cfg.get("llm_mode","offline")
        self._llm_btn.configure(text="  ONLINE" if mode=="online" else "  OFFLINE")
        self._draw_bg()

    def _on_close(self):
        self._save_current()
        self.cfg["sash_x"] = self._sash_x
        # FIX V1.49p : _session_elapsed et _session_start initialises dans __init__
        self.cfg["session_elapsed"] = (
            self._session_elapsed + (time.time() - self._session_start)
        )
        self._timer_running = False
        save_settings(self.cfg)
        self.root.destroy()

    def _tick_timer(self):
        if not self._timer_running:
            return
        elapsed = self._session_elapsed + (time.time() - self._session_start)
        h = int(elapsed // 3600)
        m = int((elapsed % 3600) // 60)
        s = int(elapsed % 60)
        time_str = f"{h:02d}:{m:02d}:{s:02d}"
        project = self.cfg.get("current_project", "Nouveau projet")
        self.root.title(f"  {APP_NAME}  {APP_VERSION}  |  {time_str}  |  {project}")
        self.root.after(1000, self._tick_timer)

    def _launch_3d(self):
        prompt = self.vars.get("prompt_3d", tk.StringVar()).get() if isinstance(self.vars.get("prompt_3d"), tk.StringVar) else ""
        mode   = self.vars.get("mode_3d",   tk.StringVar()).get()  if isinstance(self.vars.get("mode_3d"),   tk.StringVar) else "render"
        self._log(f"[3D] Lancement -- mode={mode}")
        def _run():
            try:
                import sys as _s, os as _o
                _s.path.insert(0, str(Path(__file__).parent / "agents"))
                from agent_3d_modeler import Agent3DModeler
                result = Agent3DModeler().run_3d_pipeline(prompt=prompt, mode=mode)
                self._log(f"[3D] OK {result.get('output_path','?')}")
            except ImportError:
                self._log("[3D] agent_3d_modeler.py introuvable")
            except Exception as e:
                self._log(f"[3D] Erreur : {e}")
        threading.Thread(target=_run, daemon=True).start()

    def _validate_stl(self):
        path = filedialog.askopenfilename(title="Choisir un fichier STL",
                                           filetypes=[("STL files","*.stl")])
        if not path: return
        self._log(f"[STL] Validation : {path}")
        try:
            import trimesh
            mesh = trimesh.load(path)
            self._log(f"[STL] Etanche:{mesh.is_watertight} | Volume:{abs(float(mesh.volume))/1000:.2f}cm3 | Faces:{len(mesh.faces)}")
        except ImportError: self._log("[STL] pip install trimesh")
        except Exception as e: self._log(f"[STL] {e}")

    def _prepare_slicer(self):
        path = filedialog.askopenfilename(title="Choisir un fichier STL",
                                           filetypes=[("STL files","*.stl")])
        if not path: return
        for slicer in [r"C:\Program Files\CHITUBOX\CHITUBOX.exe",
                        r"C:\Program Files\Lychee Slicer 5\Lychee Slicer.exe",
                        r"C:\Program Files\Prusa3D\PrusaSlicer\prusa-slicer.exe"]:
            if os.path.exists(slicer):
                subprocess.Popen([slicer, path])
                self._log(f"[STL] Ouvert dans {os.path.basename(slicer)}")
                return
        self._log("[STL] Aucun slicer trouve (Chitubox, Lychee, PrusaSlicer)")

    def run(self):
        self._tick_timer()
        self.root.mainloop()


if __name__=="__main__":
    if not CTK_OK: print("Conseil : pip install customtkinter")
    if not PIL_OK: print("Conseil : pip install Pillow")
    app=OverLordApp(); app.run()
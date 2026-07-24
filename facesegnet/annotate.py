# ██████╗ ██╗   ██╗██████╗ ██████╗ ██╗      ██████╗ ██████╗ ██████╗
# ██╔═══██╗██║   ██║╚════██╗██╔══██╗██║     ██╔═══██╗██╔══██╗██╔══██╗
# ██║   ██║██║   ██║ █████╔╝██████╔╝██║     ██║   ██║██████╔╝██║  ██║
# ██║   ██║╚██╗ ██╔╝ ╚═══██╗██╔══██╗██║     ██║   ██║██╔══██╗██║  ██║
# ╚██████╔╝ ╚████╔╝ ██████╔╝██║  ██║███████╗╚██████╔╝██║  ██║██████╔╝
# ╚═════╝   ╚═══╝  ╚═════╝ ╚═╝  ╚═╝╚══════╝ ╚═════╝ ╚═╝  ╚═╝╚═════╝
# Ov3rLoRd -- pipeline de production anime autonome (ComfyUI)
# https://github.com/Ov3rLoRd-MLEngineer
#
# annotate.py — FaceSegNet (Ov3rLoRd Pipeline)
# Interface d'annotation multi-classes (tkinter) : pré-remplissage SAM par
# points + correction au stylet/souris. Même architecture que
# handsegnet\annotate.py, avec 5 catégories visage.
#
# Un masque PNG PAR CATÉGORIE : dataset\masks_raw\<stem>__<catégorie>.png
# (BLANC=objet, NOIR=fond). Le stylet Windows Ink est vu comme la souris.
#
# Contrôles :
#   Molette             : zoom avant/arrière centré sur le curseur
#   Ctrl+Molette        : taille de la pointe (cercle d'aperçu visible au curseur)
#   Clic milieu (drag)  : pan (déplacement de la vue)
#   Espace + drag       : pan (alternative stylet)
#   Ctrl+Z              : annuler le dernier clic (masque + point SAM)
#   1..5                : catégorie active (eyes/mouth/nose/eyebrows/hairline)
#   Clic gauche         : mode POINT → point SAM positif  |  mode BRUSH → peindre
#                         |  mode FILL → remplir la zone fermée sous le clic
#   Clic droit          : mode POINT → point SAM négatif  |  mode BRUSH → effacer
#   B                   : bascule POINT / BRUSH
#   F                   : mode FILL (remplissage d'un contour fermé tracé au brush)
#   + / -               : taille du brush (alternative clavier)
#   U                   : annuler (10 niveaux)   C : effacer catégorie active
#   I                   : inverser catégorie active
#   S                   : sauvegarder tous les masques
#   N / P               : image suivante / précédente (sauvegarde auto)
#   Échap               : quitter
#
# Usage :
#   py -3.12 annotate.py

import argparse
import tkinter as tk
from pathlib import Path

import cv2
import numpy as np
from PIL import Image, ImageTk
from scipy.ndimage import binary_fill_holes

# ── CONFIG ────────────────────────────────────────────────────────────────────
PROJECT_ROOT   = Path(r"D:\OVERLORD\facesegnet")
DEFAULT_IMAGES = PROJECT_ROOT / "dataset" / "raw"
DEFAULT_MASKS  = PROJECT_ROOT / "dataset" / "masks_raw"
SAM_CHECKPOINT = Path(r"D:\Ov3rLoRd AI\ComfyUI\models\sams\sam_vit_b_01ec64.pth")

# (nom, couleur overlay RGB) — l'ordre définit les touches 1..N
CATEGORIES = [
    ("eyes",     (60, 120, 255)),
    ("mouth",    (255, 60, 60)),
    ("nose",     (60, 255, 120)),
    ("eyebrows", (255, 160, 40)),
    ("hairline", (200, 80, 255)),
]

OVERLAY_ALPHA = 110
UNDO_LEVELS   = 10
DEFAULT_BRUSH = 8      # traits fins (sourcils, contour des yeux)
ZOOM_MAX      = 8.0
ZOOM_STEP     = 1.2
FILL_LEAK_RATIO = 0.5   # si floodFill remplit plus que ça, on suppose une fuite

# ── SAM (optionnel) ──────────────────────────────────────────────────────────
_sam_predictor = None
SAM_AVAILABLE = False
try:
    import torch
    from segment_anything import sam_model_registry, SamPredictor
    SAM_AVAILABLE = SAM_CHECKPOINT.exists()
    if not SAM_CHECKPOINT.exists():
        print(f"[annotate] Checkpoint SAM introuvable : {SAM_CHECKPOINT}")
except ImportError:
    print("[annotate] torch/segment-anything absents — mode brush pur")


def get_sam_predictor():
    global _sam_predictor
    if _sam_predictor is None and SAM_AVAILABLE:
        device = "cuda" if torch.cuda.is_available() else "cpu"
        print(f"[annotate] Chargement SAM ViT-B sur {device}...")
        sam = sam_model_registry["vit_b"](checkpoint=str(SAM_CHECKPOINT))
        sam.to(device)
        _sam_predictor = SamPredictor(sam)
        print("[annotate] SAM prêt")
    return _sam_predictor


# ── Application ──────────────────────────────────────────────────────────────

class AnnotatorApp:
    def __init__(self, root: tk.Tk, images_dir: Path, masks_dir: Path):
        self.root = root
        self.images_dir = images_dir
        self.masks_dir = masks_dir
        self.masks_dir.mkdir(parents=True, exist_ok=True)

        exts = {".png", ".jpg", ".jpeg", ".webp"}
        self.image_paths = sorted(
            p for p in images_dir.iterdir()
            if p.suffix.lower() in exts and not p.name.startswith("_")
        )
        if not self.image_paths:
            raise SystemExit(f"[annotate] Aucune image dans {images_dir}")

        self.index = 0
        self.cat_idx = 0
        self.mode = "point" if SAM_AVAILABLE else "brush"
        self.brush_size = DEFAULT_BRUSH
        self.dirty = False

        self.img_pil: Image.Image | None = None
        self.masks: dict[str, np.ndarray] = {}     # nom → uint8 HxW (255=objet)
        self.sam_points: list[tuple[int, int, int]] = []
        self.sam_image_set = False
        self.undo_stack: list[tuple[str, np.ndarray, list]] = []
        self._tk_img = None
        self._painting = False
        self._overlay: Image.Image | None = None   # composition pleine résolution

        # État de vue (zoom/pan)
        self.zoom = 1.0
        self.fit_zoom = 1.0
        self.view_x = 0.0
        self.view_y = 0.0
        self.cw = 1
        self.ch = 1
        self._pan_anchor = None
        self._space_down = False

        self.canvas = tk.Canvas(root, bg="#202020", highlightthickness=0)
        self.canvas.pack(fill="both", expand=True)
        self.status = tk.Label(root, anchor="w", font=("Consolas", 10))
        self.status.pack(fill="x")

        try:
            root.state("zoomed")   # démarre en plein écran (Windows)
        except tk.TclError:
            pass
        root.update_idletasks()

        self.canvas.bind("<Configure>",       self.on_canvas_resize)
        self.canvas.bind("<Button-1>",        self.on_left_click)
        self.canvas.bind("<B1-Motion>",       self.on_left_drag)
        self.canvas.bind("<ButtonRelease-1>", self.on_release)
        self.canvas.bind("<Button-3>",        self.on_right_click)
        self.canvas.bind("<B3-Motion>",       self.on_right_drag)
        self.canvas.bind("<ButtonRelease-3>", self.on_release)
        self.canvas.bind("<Button-2>",        self.on_pan_start)
        self.canvas.bind("<B2-Motion>",       self.on_pan_move)
        self.canvas.bind("<ButtonRelease-2>", self.on_pan_end)
        self.canvas.bind("<Motion>",          self.on_motion)
        root.bind_all("<MouseWheel>",         self.on_wheel)
        root.bind("<KeyPress-space>",         self.on_space_down)
        root.bind("<KeyRelease-space>",       self.on_space_up)
        root.bind("<Key>", self.on_key)

        self.load_image(0)

    # ── Catégories ────────────────────────────────────────────────────────────

    def cat_name(self) -> str:
        return CATEGORIES[self.cat_idx][0]

    def cat_color(self) -> tuple:
        return CATEGORIES[self.cat_idx][1]

    def active_mask(self) -> np.ndarray:
        return self.masks[self.cat_name()]

    def mask_path(self, cat: str) -> Path:
        return self.masks_dir / f"{self.image_paths[self.index].stem}__{cat}.png"

    # ── Navigation / chargement ──────────────────────────────────────────────

    def load_image(self, index: int):
        self.index = index % len(self.image_paths)
        path = self.image_paths[self.index]
        self.img_pil = Image.open(str(path)).convert("RGB")
        w, h = self.img_pil.size
        self.cw = max(1, self.canvas.winfo_width())
        self.ch = max(1, self.canvas.winfo_height())
        self.fit_zoom = min(self.cw / w, self.ch / h)
        self.zoom = self.fit_zoom
        self.view_x = 0.0
        self.view_y = 0.0
        self.clamp_view()   # centre l'image si son ratio ne remplit pas le canvas

        self.masks = {}
        for cat, _color in CATEGORIES:
            mp = self.mask_path(cat)
            if mp.exists():
                m = Image.open(str(mp)).convert("L")
                if m.size != (w, h):
                    m = m.resize((w, h), Image.NEAREST)
                self.masks[cat] = (np.array(m) > 127).astype(np.uint8) * 255
            else:
                self.masks[cat] = np.zeros((h, w), dtype=np.uint8)

        self.sam_points = []
        self.sam_image_set = False
        self.undo_stack = []
        self.dirty = False
        self.refresh(full=True)

    def save_masks(self):
        for cat, _color in CATEGORIES:
            arr = self.masks[cat]
            if arr.any() or self.mask_path(cat).exists():
                Image.fromarray(arr, mode="L").save(str(self.mask_path(cat)))
        self.dirty = False
        self.refresh_status()
        print(f"[annotate] Sauvegardé : {self.image_paths[self.index].stem}__<cat>.png")

    # ── Vue (zoom / pan) ─────────────────────────────────────────────────────

    def canvas_to_image(self, ex: float, ey: float) -> tuple[int, int]:
        return int(self.view_x + ex / self.zoom), int(self.view_y + ey / self.zoom)

    def image_to_canvas(self, ix: float, iy: float) -> tuple[float, float]:
        return (ix - self.view_x) * self.zoom, (iy - self.view_y) * self.zoom

    def on_canvas_resize(self, event):
        """Suit la taille réelle du canvas (fenêtre redimensionnée/maximisée)
        pour que le zoom remplisse tout l'espace disponible, pas une zone figée."""
        if self.img_pil is None or event.width < 2 or event.height < 2:
            return
        was_fit = abs(self.zoom - self.fit_zoom) < 1e-6
        self.cw, self.ch = event.width, event.height
        w, h = self.img_pil.size
        self.fit_zoom = min(self.cw / w, self.ch / h)
        if was_fit:
            self.zoom = self.fit_zoom
        self.clamp_view()
        self.render_view()

    def clamp_view(self):
        w, h = self.img_pil.size
        vw = self.cw / self.zoom
        vh = self.ch / self.zoom
        # Si la vue est plus large/haute que l'image (dézoomé ou ratio différent
        # du canvas), on centre au lieu d'ancrer en haut-gauche.
        if vw >= w:
            self.view_x = -(vw - w) / 2.0
        else:
            self.view_x = max(0.0, min(self.view_x, w - vw))
        if vh >= h:
            self.view_y = -(vh - h) / 2.0
        else:
            self.view_y = max(0.0, min(self.view_y, h - vh))

    # ── Affichage ────────────────────────────────────────────────────────────

    def compose_overlay(self):
        """Recompose l'overlay pleine résolution (mis en cache pour le zoom/pan)."""
        w, h = self.img_pil.size
        overlay = self.img_pil.copy()
        for cat, color in CATEGORIES:
            arr = self.masks[cat]
            if not arr.any():
                continue
            color_layer = Image.new("RGB", (w, h), color)
            alpha = Image.fromarray(
                (arr.astype(np.uint16) * OVERLAY_ALPHA // 255).astype(np.uint8),
                mode="L",
            )
            overlay.paste(color_layer, (0, 0), alpha)
        self._overlay = overlay

    def refresh(self, full: bool = False):
        self.compose_overlay()
        self.render_view()

    def render_view(self):
        """Dessine la portion visible de l'overlay selon zoom/pan."""
        z = self.zoom
        x2 = self.view_x + self.cw / z
        y2 = self.view_y + self.ch / z
        crop = self._overlay.crop((int(self.view_x), int(self.view_y),
                                   int(round(x2)), int(round(y2))))
        resample = Image.NEAREST if z >= 2.0 else Image.BILINEAR
        disp = crop.resize((self.cw, self.ch), resample)

        self._tk_img = ImageTk.PhotoImage(disp)
        self.canvas.delete("all")
        self.canvas.create_image(0, 0, anchor="nw", image=self._tk_img)

        for x, y, label in self.sam_points:
            cx, cy = self.image_to_canvas(x, y)
            if -10 <= cx <= self.cw + 10 and -10 <= cy <= self.ch + 10:
                color = "#00ff00" if label == 1 else "#ff8800"
                self.canvas.create_oval(cx - 5, cy - 5, cx + 5, cy + 5,
                                        outline=color, width=2)
        self.refresh_status()

    def refresh_status(self):
        cats_txt = "  ".join(
            f"[{i + 1}:{name}{'*' if i == self.cat_idx else ''}]"
            for i, (name, _c) in enumerate(CATEGORIES)
        )
        pct = float((self.active_mask() > 0).sum()) / self.active_mask().size * 100
        sam_txt = "SAM:on" if SAM_AVAILABLE else "SAM:off"
        saved = "modifié*" if self.dirty else "sauvegardé"
        self.status.config(text=(
            f"[{self.index + 1}/{len(self.image_paths)}] "
            f"{self.image_paths[self.index].name}  {cats_txt}  "
            f"mode={self.mode.upper()} pointe={self.brush_size}px "
            f"zoom={self.zoom * 100:.0f}%  "
            f"masque({self.cat_name()})={pct:.1f}%  {sam_txt}  {saved}"
        ))

    # ── Aperçu de la pointe ──────────────────────────────────────────────────

    def draw_brush_cursor(self, ex: float, ey: float):
        """Cercle d'aperçu de la pointe à sa taille réelle, couleur de la
        catégorie active + contour noir pour rester visible partout."""
        self.canvas.delete("brushcur")
        r = max(1.0, self.brush_size * self.zoom)
        rgb = self.cat_color()
        color = f"#{rgb[0]:02x}{rgb[1]:02x}{rgb[2]:02x}"
        self.canvas.create_oval(ex - r - 1, ey - r - 1, ex + r + 1, ey + r + 1,
                                outline="#000000", width=1, tags="brushcur")
        self.canvas.create_oval(ex - r, ey - r, ex + r, ey + r,
                                outline=color, width=1, tags="brushcur")

    def on_motion(self, event):
        if self.mode == "brush" and not self._space_down:
            self.draw_brush_cursor(event.x, event.y)
        else:
            self.canvas.delete("brushcur")

    # ── Molette : zoom / taille de pointe ────────────────────────────────────

    def on_wheel(self, event):
        ex = self.canvas.winfo_pointerx() - self.canvas.winfo_rootx()
        ey = self.canvas.winfo_pointery() - self.canvas.winfo_rooty()
        if not (0 <= ex < self.cw and 0 <= ey < self.ch):
            return

        if event.state & 0x0004:   # Ctrl → réglage de la pointe, aperçu immédiat
            step = 2 if event.delta > 0 else -2
            self.brush_size = max(2, min(200, self.brush_size + step))
            self.draw_brush_cursor(ex, ey)
            self.refresh_status()
            return

        factor = ZOOM_STEP if event.delta > 0 else 1.0 / ZOOM_STEP
        ix = self.view_x + ex / self.zoom
        iy = self.view_y + ey / self.zoom
        self.zoom = max(self.fit_zoom, min(ZOOM_MAX, self.zoom * factor))
        self.view_x = ix - ex / self.zoom
        self.view_y = iy - ey / self.zoom
        self.clamp_view()
        self.render_view()
        if self.mode == "brush":
            self.draw_brush_cursor(ex, ey)

    # ── Pan (clic milieu ou Espace+drag) ─────────────────────────────────────

    def on_pan_start(self, event):
        self._pan_anchor = (event.x, event.y, self.view_x, self.view_y)

    def on_pan_move(self, event):
        if self._pan_anchor is None:
            return
        ax, ay, vx, vy = self._pan_anchor
        self.view_x = vx - (event.x - ax) / self.zoom
        self.view_y = vy - (event.y - ay) / self.zoom
        self.clamp_view()
        self.render_view()

    def on_pan_end(self, _event):
        self._pan_anchor = None

    def on_space_down(self, _event):
        self._space_down = True
        self.canvas.delete("brushcur")

    def on_space_up(self, _event):
        self._space_down = False
        self._pan_anchor = None

    # ── Undo ─────────────────────────────────────────────────────────────────

    def push_undo(self):
        self.undo_stack.append(
            (self.cat_name(), self.active_mask().copy(), list(self.sam_points)))
        if len(self.undo_stack) > UNDO_LEVELS:
            self.undo_stack.pop(0)

    def undo(self):
        """Annule le dernier clic : restaure le masque ET les points SAM."""
        if self.undo_stack:
            cat, m, pts = self.undo_stack.pop()
            self.masks[cat] = m
            self.sam_points = pts
            self.dirty = True
            self.refresh()

    # ── SAM prefill (appliqué à la catégorie active) ─────────────────────────

    def run_sam(self):
        predictor = get_sam_predictor()
        if predictor is None or not self.sam_points:
            return
        if not self.sam_image_set:
            predictor.set_image(np.array(self.img_pil))
            self.sam_image_set = True

        pts = np.array([[x, y] for x, y, _ in self.sam_points], dtype=np.float32)
        labels = np.array([l for _, _, l in self.sam_points], dtype=np.int32)
        masks, scores, _ = predictor.predict(
            point_coords=pts, point_labels=labels, multimask_output=True
        )
        best = masks[int(np.argmax(scores))]
        self.masks[self.cat_name()] = best.astype(np.uint8) * 255
        self.dirty = True
        self.refresh()

    # ── Brush ────────────────────────────────────────────────────────────────

    def paint(self, ex: float, ey: float, value: int):
        x, y = self.canvas_to_image(ex, ey)
        mask = self.active_mask()
        h, w = mask.shape
        r = self.brush_size
        x0, x1 = max(0, x - r), min(w, x + r + 1)
        y0, y1 = max(0, y - r), min(h, y + r + 1)
        if x0 >= x1 or y0 >= y1:
            return
        yy, xx = np.ogrid[y0:y1, x0:x1]
        circle = (xx - x) ** 2 + (yy - y) ** 2 <= r * r
        mask[y0:y1, x0:x1][circle] = value
        self.dirty = True
        cr = r * self.zoom
        rgb = self.cat_color()
        color = f"#{rgb[0]:02x}{rgb[1]:02x}{rgb[2]:02x}" if value else "#3060ff"
        self.canvas.create_oval(ex - cr, ey - cr, ex + cr, ey + cr,
                                fill=color, outline="", stipple="gray50")

    # ── Flood fill (catégorie active) ─────────────────────────────────────────

    def flood_fill_at(self, ex: float, ey: float):
        """Remplit la zone entourée par un contour fermé tracé au brush, dans
        le masque de la catégorie active. cv2.floodFill part du point cliqué
        et se propage sur les pixels à 0, borné par le tracé à 255. Si le
        tracé a une fuite (trou d'1px issu de la connectivité 4 de
        floodFill), le remplissage déborde sur une trop grande portion de
        l'image : on retente alors avec scipy.ndimage.binary_fill_holes, qui
        comble les trous fermés du masque sans dépendre d'un point de départ."""
        x, y = self.canvas_to_image(ex, ey)
        mask = self.active_mask()
        h, w = mask.shape
        if not (0 <= x < w and 0 <= y < h) or mask[y, x] == 255:
            return

        self.push_undo()

        filled = mask.copy()
        ff_mask = np.zeros((h + 2, w + 2), dtype=np.uint8)
        cv2.floodFill(filled, ff_mask, (x, y), 255, loDiff=0, upDiff=0)
        leaked = (filled > mask).sum() > FILL_LEAK_RATIO * mask.size

        if leaked:
            mask[:] = binary_fill_holes(mask > 0).astype(np.uint8) * 255
        else:
            mask[:] = filled

        self.dirty = True
        self.refresh()

    # ── Événements ───────────────────────────────────────────────────────────

    def on_left_click(self, event):
        if self._space_down:                      # Espace+drag = pan
            self.on_pan_start(event)
            return
        if self.mode == "point" and SAM_AVAILABLE:
            self.push_undo()                      # snapshot avant le clic (Ctrl+Z)
            x, y = self.canvas_to_image(event.x, event.y)
            self.sam_points.append((x, y, 1))
            self.run_sam()
        elif self.mode == "fill":
            self.flood_fill_at(event.x, event.y)
        else:
            self._painting = True
            self.push_undo()
            self.paint(event.x, event.y, 255)

    def on_right_click(self, event):
        if self._space_down:
            self.on_pan_start(event)
            return
        if self.mode == "point" and SAM_AVAILABLE:
            self.push_undo()
            x, y = self.canvas_to_image(event.x, event.y)
            self.sam_points.append((x, y, 0))
            self.run_sam()
        elif self.mode == "fill":
            return
        else:
            self._painting = True
            self.push_undo()
            self.paint(event.x, event.y, 0)

    def on_left_drag(self, event):
        if self._space_down and self._pan_anchor is not None:
            self.on_pan_move(event)
            return
        if self.mode == "brush" and self._painting:
            self.paint(event.x, event.y, 255)

    def on_right_drag(self, event):
        if self._space_down and self._pan_anchor is not None:
            self.on_pan_move(event)
            return
        if self.mode == "brush" and self._painting:
            self.paint(event.x, event.y, 0)

    def on_release(self, _event):
        self._pan_anchor = None
        if self._painting:
            self._painting = False
            self.refresh()

    def on_key(self, event):
        key = event.keysym.lower()
        if key == "z" and (event.state & 0x0004):   # Ctrl+Z : annuler dernier clic
            self.undo()
            return
        if key.isdigit() and key != "0":
            idx = int(key) - 1
            if idx < len(CATEGORIES):
                self.cat_idx = idx
                self.sam_points = []       # points SAM liés à une seule catégorie
                self.refresh()
        elif key == "b":
            if self.mode != "brush":
                self.mode = "brush"
            else:
                self.mode = "point" if SAM_AVAILABLE else "brush"
            self.canvas.delete("brushcur")
            self.refresh_status()
        elif key == "f":
            self.mode = "fill"
            self.canvas.delete("brushcur")
            self.refresh_status()
        elif key in ("plus", "equal", "kp_add"):
            self.brush_size = min(200, self.brush_size + 4)
            self.refresh_status()
        elif key in ("minus", "kp_subtract"):
            self.brush_size = max(2, self.brush_size - 4)
            self.refresh_status()
        elif key == "u":
            self.undo()
        elif key == "c":
            self.push_undo()
            self.active_mask()[:] = 0
            self.sam_points = []
            self.dirty = True
            self.refresh()
        elif key == "i":
            self.push_undo()
            self.masks[self.cat_name()] = 255 - self.active_mask()
            self.dirty = True
            self.refresh()
        elif key == "s":
            self.save_masks()
        elif key == "n":
            if self.dirty:
                self.save_masks()
            self.load_image(self.index + 1)
        elif key == "p":
            if self.dirty:
                self.save_masks()
            self.load_image(self.index - 1)
        elif key == "escape":
            if self.dirty:
                self.save_masks()
            self.root.destroy()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="FaceSegNet — annotation multi-classes")
    parser.add_argument("--images", default=str(DEFAULT_IMAGES))
    parser.add_argument("--masks",  default=str(DEFAULT_MASKS))
    args = parser.parse_args()

    root = tk.Tk()
    root.title("FaceSegNet Annotator — Ov3rLoRd")
    app = AnnotatorApp(root, Path(args.images), Path(args.masks))
    root.mainloop()

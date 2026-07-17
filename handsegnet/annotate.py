# annotate.py — HandSegNet (Ov3rLoRd Pipeline)
# Interface d'annotation légère (tkinter) pour créer les masques de mains.
# Mono-classe pour l'instant (une seule catégorie "hand", pas de distinction
# poignet/main/doigts) — même architecture que footsegnet\annotate.py.
#
# Flux : pré-remplissage SAM (clics de points) → correction au stylet/souris
#        (brush) → export masque PNG (BLANC=main, NOIR=fond).
#
# Le stylet Windows Ink est vu par tkinter comme la souris — un stylet sur
# écran/tablette fonctionne donc directement pour peindre (sans pression).
#
# SAM local via segment-anything + torch (checkpoint sam_vit_b_01ec64.pth de
# l'installation ComfyUI). Si torch/segment-anything sont absents, l'outil
# bascule en mode brush pur (annotation 100% manuelle).
#
# Contrôles :
#   Molette             : zoom avant/arrière centré sur le curseur
#   Ctrl+Molette        : taille de la pointe (cercle d'aperçu visible au curseur)
#   Clic milieu (drag)  : pan (déplacement de la vue)
#   Espace + drag       : pan (alternative stylet)
#   Ctrl+Z              : annuler le dernier clic (masque + point SAM)
#   Clic gauche         : mode POINT → point SAM positif  |  mode BRUSH → peindre
#                         |  mode FILL → remplir la zone fermée sous le clic
#   Clic droit          : mode POINT → point SAM négatif  |  mode BRUSH → effacer
#   B                   : bascule POINT / BRUSH
#   F                   : mode FILL (remplissage d'un contour fermé tracé au brush)
#   + / -               : taille du brush (alternative clavier)
#   U                   : annuler (10 niveaux)
#   C                   : effacer le masque + points SAM
#   I                   : inverser le masque
#   S                   : sauvegarder le masque PNG
#   N / P               : image suivante / précédente (sauvegarde auto si modifié)
#   Échap               : quitter
#
# Usage :
#   py -3.12 annotate.py
#   py -3.12 annotate.py --images D:\OVERLORD\handsegnet\dataset\raw --masks D:\OVERLORD\handsegnet\dataset\masks_raw

import argparse
import tkinter as tk
from pathlib import Path

import cv2
import numpy as np
from PIL import Image, ImageTk
from scipy.ndimage import binary_fill_holes

# ── CONFIG ────────────────────────────────────────────────────────────────────
PROJECT_ROOT   = Path(r"D:\OVERLORD\handsegnet")
DEFAULT_IMAGES = PROJECT_ROOT / "dataset" / "raw"
DEFAULT_MASKS  = PROJECT_ROOT / "dataset" / "masks_raw"
SAM_CHECKPOINT = Path(r"D:\Ov3rLoRd AI\ComfyUI\models\sams\sam_vit_b_01ec64.pth")

OVERLAY_COLOR = (255, 60, 60)   # rouge semi-transparent sur les zones masquées
OVERLAY_ALPHA = 110
UNDO_LEVELS   = 10
DEFAULT_BRUSH = 16
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
    """Charge SAM ViT-B une seule fois (lazy)."""
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
        self.mode = "point" if SAM_AVAILABLE else "brush"
        self.brush_size = DEFAULT_BRUSH
        self.dirty = False

        # État image courante (initialisé par load_image)
        self.img_pil: Image.Image | None = None
        self.mask: np.ndarray | None = None       # uint8 HxW, 255=objet
        self.sam_points: list[tuple[int, int, int]] = []   # (x, y, label)
        self.sam_image_set = False
        self.undo_stack: list[tuple[np.ndarray, list]] = []
        self._tk_img = None
        self._painting = False
        self._overlay: Image.Image | None = None   # composition pleine résolution

        # État de vue (zoom/pan)
        self.zoom = 1.0
        self.fit_zoom = 1.0
        self.view_x = 0.0      # coin haut-gauche de la vue, en coordonnées image
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

        mask_path = self.mask_path()
        if mask_path.exists():
            m = Image.open(str(mask_path)).convert("L")
            if m.size != (w, h):
                m = m.resize((w, h), Image.NEAREST)
            self.mask = (np.array(m) > 127).astype(np.uint8) * 255
        else:
            self.mask = np.zeros((h, w), dtype=np.uint8)

        self.sam_points = []
        self.sam_image_set = False
        self.undo_stack = []
        self.dirty = False
        self.refresh(full=True)

    def mask_path(self) -> Path:
        return self.masks_dir / f"{self.image_paths[self.index].stem}.png"

    def save_mask(self):
        Image.fromarray(self.mask, mode="L").save(str(self.mask_path()))
        self.dirty = False
        self.refresh_status()
        print(f"[annotate] Sauvegardé : {self.mask_path()}")

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
        if self.mask.any():
            color_layer = Image.new("RGB", (w, h), OVERLAY_COLOR)
            alpha = Image.fromarray(
                (self.mask.astype(np.uint16) * OVERLAY_ALPHA // 255).astype(np.uint8),
                mode="L",
            )
            overlay.paste(color_layer, (0, 0), alpha)
        self._overlay = overlay

    def refresh(self, full: bool = False):
        """Recompose l'overlay puis redessine la vue courante."""
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
        pct = float((self.mask > 0).sum()) / self.mask.size * 100
        sam_txt = "SAM:on" if SAM_AVAILABLE else "SAM:off"
        saved = "modifié*" if self.dirty else "sauvegardé"
        self.status.config(text=(
            f"[{self.index + 1}/{len(self.image_paths)}] "
            f"{self.image_paths[self.index].name}  |  mode={self.mode.upper()}  "
            f"pointe={self.brush_size}px  zoom={self.zoom * 100:.0f}%  |  "
            f"masque(hand)={pct:.1f}%  |  {sam_txt}  |  {saved}   "
            f"(Molette:zoom  Ctrl+Molette:pointe  ClicMilieu/Espace:pan  "
            f"Ctrl+Z:annuler  B:mode  S:save  N/P:nav)"
        ))

    # ── Aperçu de la pointe ──────────────────────────────────────────────────

    def draw_brush_cursor(self, ex: float, ey: float):
        """Cercle d'aperçu de la pointe à sa taille réelle (double contour
        noir/blanc pour rester visible sur fond clair et foncé)."""
        self.canvas.delete("brushcur")
        r = max(1.0, self.brush_size * self.zoom)
        self.canvas.create_oval(ex - r - 1, ey - r - 1, ex + r + 1, ey + r + 1,
                                outline="#000000", width=1, tags="brushcur")
        self.canvas.create_oval(ex - r, ey - r, ex + r, ey + r,
                                outline="#ffffff", width=1, tags="brushcur")

    def on_motion(self, event):
        if self.mode == "brush" and not self._space_down:
            self.draw_brush_cursor(event.x, event.y)
        else:
            self.canvas.delete("brushcur")

    # ── Molette : zoom / taille de pointe ────────────────────────────────────

    def on_wheel(self, event):
        # Position du curseur relative au canvas (bind_all → coords widget focus)
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

        # Zoom centré sur le curseur : le point image sous le curseur reste fixe
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
        self.undo_stack.append((self.mask.copy(), list(self.sam_points)))
        if len(self.undo_stack) > UNDO_LEVELS:
            self.undo_stack.pop(0)

    def undo(self):
        """Annule le dernier clic : restaure le masque ET les points SAM."""
        if self.undo_stack:
            self.mask, self.sam_points = self.undo_stack.pop()
            self.dirty = True
            self.refresh()

    # ── SAM prefill ──────────────────────────────────────────────────────────

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
        # Le résultat SAM remplace le masque courant — corrections au brush ensuite
        self.mask = best.astype(np.uint8) * 255
        self.dirty = True
        self.refresh()

    # ── Brush ────────────────────────────────────────────────────────────────

    def paint(self, ex: float, ey: float, value: int):
        x, y = self.canvas_to_image(ex, ey)
        h, w = self.mask.shape
        r = self.brush_size
        x0, x1 = max(0, x - r), min(w, x + r + 1)
        y0, y1 = max(0, y - r), min(h, y + r + 1)
        if x0 >= x1 or y0 >= y1:
            return
        yy, xx = np.ogrid[y0:y1, x0:x1]
        circle = (xx - x) ** 2 + (yy - y) ** 2 <= r * r
        self.mask[y0:y1, x0:x1][circle] = value
        self.dirty = True
        # Feedback immédiat léger pendant le drag (refresh complet au relâchement)
        cr = r * self.zoom
        color = "#ff4040" if value else "#3060ff"
        self.canvas.create_oval(ex - cr, ey - cr, ex + cr, ey + cr,
                                fill=color, outline="", stipple="gray50")

    # ── Flood fill ───────────────────────────────────────────────────────────

    def flood_fill_at(self, ex: float, ey: float):
        """Remplit la zone entourée par un contour fermé tracé au brush.
        cv2.floodFill part du point cliqué
        et se propage sur les pixels à 0, borné par le tracé à 255. Si le
        tracé a une fuite (trou d'1px issu de la connectivité 4 de
        floodFill), le remplissage déborde sur une trop grande portion de
        l'image : on retente alors avec scipy.ndimage.binary_fill_holes, qui
        comble les trous fermés du masque sans dépendre d'un point de départ."""
        x, y = self.canvas_to_image(ex, ey)
        mask = self.mask
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
        if key == "b":
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
            self.mask[:] = 0
            self.sam_points = []
            self.dirty = True
            self.refresh()
        elif key == "i":
            self.push_undo()
            self.mask = 255 - self.mask
            self.dirty = True
            self.refresh()
        elif key == "s":
            self.save_mask()
        elif key == "n":
            if self.dirty:
                self.save_mask()
            self.load_image(self.index + 1)
        elif key == "p":
            if self.dirty:
                self.save_mask()
            self.load_image(self.index - 1)
        elif key == "escape":
            if self.dirty:
                self.save_mask()
            self.root.destroy()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="HandSegNet — annotation masques mains")
    parser.add_argument("--images", default=str(DEFAULT_IMAGES),
                        help="Dossier des images à annoter")
    parser.add_argument("--masks",  default=str(DEFAULT_MASKS),
                        help="Dossier de sortie des masques PNG")
    args = parser.parse_args()

    root = tk.Tk()
    root.title("HandSegNet Annotator — Ov3rLoRd")
    app = AnnotatorApp(root, Path(args.images), Path(args.masks))
    root.mainloop()

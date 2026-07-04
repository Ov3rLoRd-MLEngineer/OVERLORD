# annotate.py — FootSegNet (Ov3rLoRd Pipeline)
# Interface d'annotation légère (tkinter) pour créer les masques pieds/chaussures.
#
# Flux : pré-remplissage SAM (clics de points) → correction au stylet/souris
#        (brush) → export masque PNG (BLANC=pied/chaussure, NOIR=fond).
#
# Le stylet Windows Ink est vu par tkinter comme la souris — un stylet sur
# écran/tablette fonctionne donc directement pour peindre (sans pression).
#
# SAM local via segment-anything + torch (checkpoint sam_vit_b_01ec64.pth de
# l'installation ComfyUI). Si torch/segment-anything sont absents, l'outil
# bascule en mode brush pur (annotation 100% manuelle).
#
# Contrôles :
#   Clic gauche         : mode POINT → point SAM positif  |  mode BRUSH → peindre
#   Clic droit          : mode POINT → point SAM négatif  |  mode BRUSH → effacer
#   B                   : bascule POINT / BRUSH
#   + / -               : taille du brush
#   U                   : annuler (10 niveaux)
#   C                   : effacer le masque + points SAM
#   I                   : inverser le masque
#   S                   : sauvegarder le masque PNG
#   N / P               : image suivante / précédente (sauvegarde auto si modifié)
#   Échap               : quitter
#
# Usage :
#   py -3.12 annotate.py
#   py -3.12 annotate.py --images D:\OVERLORD\footsegnet\dataset\raw --masks D:\OVERLORD\footsegnet\dataset\masks_raw

import argparse
import tkinter as tk
from pathlib import Path

import numpy as np
from PIL import Image, ImageTk

# ── CONFIG ────────────────────────────────────────────────────────────────────
FOOTSEGNET_ROOT = Path(r"D:\OVERLORD\footsegnet")
DEFAULT_IMAGES  = FOOTSEGNET_ROOT / "dataset" / "raw"
DEFAULT_MASKS   = FOOTSEGNET_ROOT / "dataset" / "masks_raw"
SAM_CHECKPOINT  = Path(r"D:\Ov3rLoRd AI\ComfyUI\models\sams\sam_vit_b_01ec64.pth")

MAX_CANVAS_W = 820
MAX_CANVAS_H = 1100
OVERLAY_COLOR = (255, 40, 40)   # rouge semi-transparent sur les zones masquées
OVERLAY_ALPHA = 110
UNDO_LEVELS   = 10

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
        self.brush_size = 24
        self.dirty = False

        # État image courante (initialisé par load_image)
        self.img_pil: Image.Image | None = None
        self.mask: np.ndarray | None = None       # uint8 HxW, 255=objet
        self.scale = 1.0
        self.sam_points: list[tuple[int, int, int]] = []   # (x, y, label)
        self.sam_image_set = False
        self.undo_stack: list[np.ndarray] = []
        self._tk_img = None
        self._painting = False

        self.canvas = tk.Canvas(root, bg="#202020", highlightthickness=0)
        self.canvas.pack(fill="both", expand=True)
        self.status = tk.Label(root, anchor="w", font=("Consolas", 10))
        self.status.pack(fill="x")

        self.canvas.bind("<Button-1>",        self.on_left_click)
        self.canvas.bind("<B1-Motion>",       self.on_left_drag)
        self.canvas.bind("<ButtonRelease-1>", self.on_release)
        self.canvas.bind("<Button-3>",        self.on_right_click)
        self.canvas.bind("<B3-Motion>",       self.on_right_drag)
        self.canvas.bind("<ButtonRelease-3>", self.on_release)
        root.bind("<Key>", self.on_key)

        self.load_image(0)

    # ── Navigation / chargement ──────────────────────────────────────────────

    def load_image(self, index: int):
        self.index = index % len(self.image_paths)
        path = self.image_paths[self.index]
        self.img_pil = Image.open(str(path)).convert("RGB")
        w, h = self.img_pil.size
        self.scale = min(MAX_CANVAS_W / w, MAX_CANVAS_H / h, 1.0)

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

    # ── Affichage ────────────────────────────────────────────────────────────

    def refresh(self, full: bool = False):
        """Recompose image + overlay masque + points SAM sur le canvas."""
        w, h = self.img_pil.size
        dw, dh = int(w * self.scale), int(h * self.scale)

        overlay = self.img_pil.copy()
        color_layer = Image.new("RGB", (w, h), OVERLAY_COLOR)
        alpha = Image.fromarray(
            (self.mask.astype(np.uint16) * OVERLAY_ALPHA // 255).astype(np.uint8), mode="L"
        )
        overlay.paste(color_layer, (0, 0), alpha)
        disp = overlay.resize((dw, dh), Image.BILINEAR)

        self._tk_img = ImageTk.PhotoImage(disp)
        self.canvas.delete("all")
        self.canvas.config(width=dw, height=dh)
        self.canvas.create_image(0, 0, anchor="nw", image=self._tk_img)

        for x, y, label in self.sam_points:
            cx, cy = x * self.scale, y * self.scale
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
            f"brush={self.brush_size}px  |  masque={pct:.1f}%  |  {sam_txt}  |  {saved}   "
            f"(B:mode  S:save  U:undo  C:clear  I:invert  N/P:nav  +/-:brush)"
        ))

    # ── Undo ─────────────────────────────────────────────────────────────────

    def push_undo(self):
        self.undo_stack.append(self.mask.copy())
        if len(self.undo_stack) > UNDO_LEVELS:
            self.undo_stack.pop(0)

    def undo(self):
        if self.undo_stack:
            self.mask = self.undo_stack.pop()
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
        self.push_undo()
        # Le résultat SAM remplace le masque courant — corrections au brush ensuite
        self.mask = best.astype(np.uint8) * 255
        self.dirty = True
        self.refresh()

    # ── Brush ────────────────────────────────────────────────────────────────

    def canvas_to_image(self, ex: float, ey: float) -> tuple[int, int]:
        return int(ex / self.scale), int(ey / self.scale)

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
        cr = r * self.scale
        color = "#ff4040" if value else "#3060ff"
        self.canvas.create_oval(ex - cr, ey - cr, ex + cr, ey + cr,
                                fill=color, outline="", stipple="gray50")

    # ── Événements ───────────────────────────────────────────────────────────

    def on_left_click(self, event):
        if self.mode == "point" and SAM_AVAILABLE:
            x, y = self.canvas_to_image(event.x, event.y)
            self.sam_points.append((x, y, 1))
            self.run_sam()
        else:
            self._painting = True
            self.push_undo()
            self.paint(event.x, event.y, 255)

    def on_right_click(self, event):
        if self.mode == "point" and SAM_AVAILABLE:
            x, y = self.canvas_to_image(event.x, event.y)
            self.sam_points.append((x, y, 0))
            self.run_sam()
        else:
            self._painting = True
            self.push_undo()
            self.paint(event.x, event.y, 0)

    def on_left_drag(self, event):
        if self.mode == "brush" and self._painting:
            self.paint(event.x, event.y, 255)

    def on_right_drag(self, event):
        if self.mode == "brush" and self._painting:
            self.paint(event.x, event.y, 0)

    def on_release(self, _event):
        if self._painting:
            self._painting = False
            self.refresh()

    def on_key(self, event):
        key = event.keysym.lower()
        if key == "b":
            self.mode = "brush" if self.mode == "point" else "point"
            if self.mode == "point" and not SAM_AVAILABLE:
                self.mode = "brush"
            self.refresh_status()
        elif key in ("plus", "equal", "kp_add"):
            self.brush_size = min(150, self.brush_size + 4)
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
    parser = argparse.ArgumentParser(description="FootSegNet — annotation masques pieds/chaussures")
    parser.add_argument("--images", default=str(DEFAULT_IMAGES),
                        help="Dossier des images à annoter")
    parser.add_argument("--masks",  default=str(DEFAULT_MASKS),
                        help="Dossier de sortie des masques PNG")
    args = parser.parse_args()

    root = tk.Tk()
    root.title("FootSegNet Annotator — Ov3rLoRd")
    app = AnnotatorApp(root, Path(args.images), Path(args.masks))
    root.mainloop()

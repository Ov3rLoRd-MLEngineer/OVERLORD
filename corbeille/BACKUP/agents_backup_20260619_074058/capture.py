"""
agents/capture.py — Module Capture Vidéo
Gère Elgato 4K Pro (carte de capture HDMI) et webcam USB-C.

Usages dans le pipeline :
  1. Capturer une référence visuelle pour guider la génération IA
  2. Extraire des frames pour le style transfer
  3. Green screen / fond vert pour composition
  4. Enregistrement de sessions de travail
"""

import logging, threading, time
from pathlib import Path
from datetime import datetime

CAPTURE_DIR = Path("workspace/captures")

try:
    import cv2
    CV2_OK = True
except ImportError:
    CV2_OK = False
    print("[CAPTURE] pip install opencv-python pour activer la capture vidéo")

try:
    from PIL import Image
    PIL_OK = True
except ImportError:
    PIL_OK = False


class CaptureDevice:
    """
    Représente un périphérique de capture (Elgato ou webcam).
    Détecté automatiquement via OpenCV.
    """

    # Index OpenCV typiques sur Windows
    DEVICE_HINTS = {
        "elgato_4k":  {"index": 1, "name": "Elgato 4K Pro",
                        "resolution": (3840, 2160), "fps": 30},
        "webcam_usbc":{"index": 0, "name": "Webcam USB-C",
                        "resolution": (1920, 1080), "fps": 30},
    }

    def __init__(self, device_type: str = "webcam_usbc",
                 logger: logging.Logger = None):
        self.log      = logger or logging.getLogger("capture")
        self.dtype    = device_type
        self.hints    = self.DEVICE_HINTS.get(device_type, self.DEVICE_HINTS["webcam_usbc"])
        self.cap      = None
        self._running = False

    def list_devices(self) -> list:
        """Détecte tous les périphériques vidéo disponibles."""
        if not CV2_OK:
            return []
        devices = []
        for idx in range(6):
            cap = cv2.VideoCapture(idx, cv2.CAP_DSHOW)  # DirectShow sur Windows
            if cap.isOpened():
                w   = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
                h   = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
                fps = cap.get(cv2.CAP_PROP_FPS)
                # Détecter Elgato par résolution max
                name = f"Elgato 4K Pro" if w >= 3840 else f"Caméra {idx} ({w}x{h})"
                devices.append({"index": idx, "name": name,
                                 "width": w, "height": h, "fps": fps})
                cap.release()
        self.log.info(f"[CAPTURE] {len(devices)} périphérique(s) détecté(s)")
        return devices

    def open(self, index: int = None) -> bool:
        """Ouvre le périphérique de capture."""
        if not CV2_OK:
            self.log.error("[CAPTURE] opencv-python non installé")
            return False
        idx = index if index is not None else self.hints["index"]
        self.cap = cv2.VideoCapture(idx, cv2.CAP_DSHOW)
        if not self.cap.isOpened():
            self.log.error(f"[CAPTURE] Impossible d'ouvrir le périphérique {idx}")
            return False
        # Configurer la résolution
        w, h = self.hints["resolution"]
        self.cap.set(cv2.CAP_PROP_FRAME_WIDTH,  w)
        self.cap.set(cv2.CAP_PROP_FRAME_HEIGHT, h)
        self.cap.set(cv2.CAP_PROP_FPS, self.hints["fps"])
        actual_w = int(self.cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        actual_h = int(self.cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        self.log.info(f"[CAPTURE] {self.hints['name']} ouvert — {actual_w}x{actual_h}")
        return True

    def capture_frame(self, save_path: str = None) -> str | None:
        """Capture une frame et la sauvegarde."""
        if not self.cap or not self.cap.isOpened():
            self.log.error("[CAPTURE] Périphérique non ouvert")
            return None
        ret, frame = self.cap.read()
        if not ret:
            self.log.error("[CAPTURE] Impossible de lire la frame")
            return None
        CAPTURE_DIR.mkdir(parents=True, exist_ok=True)
        if save_path is None:
            ts = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
            save_path = str(CAPTURE_DIR / f"frame_{ts}.png")
        cv2.imwrite(save_path, frame)
        self.log.info(f"[CAPTURE] Frame sauvegardée : {save_path}")
        return save_path

    def capture_reference(self, n_frames: int = 3,
                           output_dir: str = None) -> list:
        """
        Capture N frames espacées d'1s pour sélectionner la meilleure
        comme référence visuelle pour la génération IA.
        """
        if not self.open():
            return []
        CAPTURE_DIR.mkdir(parents=True, exist_ok=True)
        out_dir = Path(output_dir or CAPTURE_DIR)
        paths   = []
        for i in range(n_frames):
            ts   = datetime.now().strftime("%Y%m%d_%H%M%S")
            path = str(out_dir / f"ref_{i:02d}_{ts}.png")
            saved = self.capture_frame(path)
            if saved:
                paths.append(saved)
            if i < n_frames - 1:
                time.sleep(1)
        self.close()
        self.log.info(f"[CAPTURE] {len(paths)} frames de référence capturées")
        return paths

    def record_session(self, output_path: str = None,
                        duration_s: int = 0,
                        stop_event: threading.Event = None) -> str | None:
        """
        Enregistre une session vidéo.
        duration_s=0 : enregistrement jusqu'à stop_event.set() ou Ctrl+C
        """
        if not CV2_OK:
            return None
        if not self.open():
            return None
        CAPTURE_DIR.mkdir(parents=True, exist_ok=True)
        if output_path is None:
            ts = datetime.now().strftime("%Y%m%d_%H%M%S")
            output_path = str(CAPTURE_DIR / f"session_{ts}.mp4")

        w   = int(self.cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        h   = int(self.cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        fps = self.cap.get(cv2.CAP_PROP_FPS) or 30.0

        fourcc = cv2.VideoWriter_fourcc(*"mp4v")
        writer = cv2.VideoWriter(output_path, fourcc, fps, (w, h))

        self.log.info(f"[CAPTURE] Enregistrement démarré → {output_path}")
        self._running = True
        start = time.time()

        try:
            while self._running:
                ret, frame = self.cap.read()
                if not ret:
                    break
                writer.write(frame)
                if duration_s > 0 and time.time() - start >= duration_s:
                    break
                if stop_event and stop_event.is_set():
                    break
        except KeyboardInterrupt:
            pass
        finally:
            writer.release()
            self.close()

        elapsed = time.time() - start
        self.log.info(f"[CAPTURE] Enregistrement terminé — {elapsed:.1f}s → {output_path}")
        return output_path

    def extract_frames_for_pipeline(self, video_path: str,
                                     n_frames: int = 10,
                                     output_dir: str = None) -> list:
        """
        Extrait N frames uniformément réparties d'une vidéo
        pour les utiliser comme références dans le pipeline IA.
        Compatible avec les fichiers Elgato 4K.
        """
        if not CV2_OK:
            return []
        out_dir = Path(output_dir or CAPTURE_DIR / "extracted")
        out_dir.mkdir(parents=True, exist_ok=True)

        cap     = cv2.VideoCapture(video_path)
        total   = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
        step    = max(1, total // n_frames)
        paths   = []

        for i in range(n_frames):
            cap.set(cv2.CAP_PROP_POS_FRAMES, i * step)
            ret, frame = cap.read()
            if ret:
                path = str(out_dir / f"frame_{i:04d}.png")
                cv2.imwrite(path, frame)
                paths.append(path)
        cap.release()
        self.log.info(f"[CAPTURE] {len(paths)} frames extraites de {video_path}")
        return paths

    def stop(self):
        self._running = False

    def close(self):
        if self.cap:
            self.cap.release()
            self.cap = None


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    dev = CaptureDevice("webcam_usbc")
    devices = dev.list_devices()
    print(f"Périphériques détectés : {len(devices)}")
    for d in devices:
        print(f"  [{d['index']}] {d['name']} — {d['width']}x{d['height']} @ {d['fps']}fps")

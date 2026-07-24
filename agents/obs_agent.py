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
agents/obs_agent.py — Agent OBS Studio OverLord
Contrôle OBS Studio via WebSocket (obs-websocket v5, inclus OBS >= 28).

Fonctionnalités :
  - Connexion WebSocket OBS (port 4455)
  - Contrôle des scènes (switch, list)
  - Capture de frames depuis n'importe quelle source
  - Enregistrement automatique des sessions
  - Streaming Twitch/YouTube pendant la production
  - Intégration Elgato 4K Pro + Webcam USB-C via scènes OBS
  - Loopback qualité : capture le résultat final pour analyse IA

Prérequis :
  - OBS Studio >= 28 installé
  - obs-websocket activé dans OBS (Outils → obs-websocket Server Settings)
  - pip install obs-websocket-py websocket-client

Usage dans le pipeline :
  obs = OBSAgent()
  obs.connect()
  frame_path = obs.capture_reference_frame("Elgato 4K")
  obs.start_recording()
  ...
  obs.stop_recording()
"""

import json
import logging
import time
import base64
import threading
import requests
from pathlib import Path
from datetime import datetime
from enum import Enum

OBS_WS_HOST    = "localhost"
OBS_WS_PORT    = 4455
OBS_WS_PASS    = ""          # mot de passe OBS WebSocket (vide si non configuré)
CAPTURE_DIR    = Path("workspace/obs_captures")
RECORDING_DIR  = Path("workspace/obs_recordings")

# Noms de scènes recommandés dans OBS pour ce pipeline
SCENE_NAMES = {
    "reference":   "OverLord - Référence",      # Elgato 4K seule
    "webcam":      "OverLord - Webcam",          # Webcam USB-C seule
    "greenscreen": "OverLord - Green Screen",    # Webcam + chroma key
    "comfyui":     "OverLord - ComfyUI Preview", # Fenêtre ComfyUI
    "final":       "OverLord - Résultat Final",  # Sortie pipeline
    "monitor":     "OverLord - Monitoring",      # Vue multi-sources
}

# Sources OBS recommandées
SOURCE_NAMES = {
    "elgato":   "Elgato 4K Pro",
    "webcam":   "Webcam USB-C",
    "comfyui":  "ComfyUI Window",
}


class OBSStatus(Enum):
    DISCONNECTED = "disconnected"
    CONNECTED    = "connected"
    RECORDING    = "recording"
    STREAMING    = "streaming"
    ERROR        = "error"


class OBSAgent:
    """
    Agent de contrôle OBS Studio pour le pipeline OverLord.
    Utilise l'API WebSocket obs-websocket v5.
    """

    def __init__(self, host: str = OBS_WS_HOST,
                 port: int = OBS_WS_PORT,
                 password: str = OBS_WS_PASS,
                 logger: logging.Logger = None):
        self.host     = host
        self.port     = port
        self.password = password
        self.log      = logger or logging.getLogger("obs")
        self.status   = OBSStatus.DISCONNECTED
        self._ws      = None
        self._req_id  = 0
        self._lock    = threading.Lock()

        CAPTURE_DIR.mkdir(parents=True, exist_ok=True)
        RECORDING_DIR.mkdir(parents=True, exist_ok=True)

        # Tentative d'import obs-websocket-py
        try:
            import obsws_python as obs
            self._obs_lib = obs
            self._lib_ok  = True
        except ImportError:
            self._obs_lib = None
            self._lib_ok  = False
            self.log.warning(
                "[OBS] obs-websocket-py non installé.\n"
                "       pip install obs-websocket-py\n"
                "       Fonctionnement en mode dégradé (HTTP screenshots uniquement)"
            )

    # ── Connexion ─────────────────────────────────────────────────────
    def connect(self) -> bool:
        """Connecte à OBS Studio via WebSocket."""
        if not self._lib_ok:
            self.log.error("[OBS] Impossible de connecter : lib manquante")
            return False
        try:
            self._client = self._obs_lib.ReqClient(
                host=self.host,
                port=self.port,
                password=self.password,
                timeout=10
            )
            # Test de connexion
            version = self._client.get_version()
            obs_ver = version.obs_version
            ws_ver  = version.obs_web_socket_version
            self.status = OBSStatus.CONNECTED
            self.log.info(
                f"[OBS] Connecté ✓ — OBS {obs_ver} | WebSocket {ws_ver}"
            )
            return True
        except Exception as e:
            self.status = OBSStatus.ERROR
            self.log.error(f"[OBS] Connexion échouée : {e}")
            self.log.info(
                "[OBS] Vérifie :\n"
                "  1. OBS Studio est ouvert\n"
                "  2. Outils → obs-websocket Server Settings → Enable\n"
                "  3. Port = 4455 | Mot de passe configuré si nécessaire"
            )
            return False

    def disconnect(self):
        """Déconnecte proprement d'OBS."""
        try:
            if hasattr(self, "_client"):
                self._client.base_client.ws.close()
        except Exception:
            pass
        self.status = OBSStatus.DISCONNECTED
        self.log.info("[OBS] Déconnecté")

    def is_connected(self) -> bool:
        return self.status in (OBSStatus.CONNECTED, OBSStatus.RECORDING,
                                OBSStatus.STREAMING)

    # ── Scènes ────────────────────────────────────────────────────────
    def list_scenes(self) -> list:
        """Liste toutes les scènes OBS."""
        if not self.is_connected(): return []
        try:
            resp   = self._client.get_scene_list()
            scenes = [s["sceneName"] for s in resp.scenes]
            self.log.info(f"[OBS] Scènes disponibles : {scenes}")
            return scenes
        except Exception as e:
            self.log.error(f"[OBS] list_scenes : {e}")
            return []

    def switch_scene(self, scene_name: str) -> bool:
        """Bascule vers une scène OBS."""
        if not self.is_connected(): return False
        try:
            self._client.set_current_program_scene(scene_name)
            self.log.info(f"[OBS] Scène active → {scene_name}")
            return True
        except Exception as e:
            self.log.error(f"[OBS] switch_scene '{scene_name}' : {e}")
            return False

    def get_current_scene(self) -> str:
        """Retourne le nom de la scène active."""
        if not self.is_connected(): return ""
        try:
            return self._client.get_current_program_scene().current_program_scene_name
        except Exception:
            return ""

    # ── Sources ───────────────────────────────────────────────────────
    def list_sources(self, scene_name: str = None) -> list:
        """Liste les sources d'une scène (ou la scène active)."""
        if not self.is_connected(): return []
        try:
            scene = scene_name or self.get_current_scene()
            resp  = self._client.get_scene_item_list(scene)
            sources = [item["sourceName"] for item in resp.scene_items]
            self.log.info(f"[OBS] Sources dans '{scene}' : {sources}")
            return sources
        except Exception as e:
            self.log.error(f"[OBS] list_sources : {e}")
            return []

    def set_source_visibility(self, scene_name: str,
                               source_name: str, visible: bool) -> bool:
        """Active/désactive une source dans une scène."""
        if not self.is_connected(): return False
        try:
            # Trouver l'ID de la source
            resp  = self._client.get_scene_item_list(scene_name)
            item_id = None
            for item in resp.scene_items:
                if item["sourceName"] == source_name:
                    item_id = item["sceneItemId"]
                    break
            if item_id is None:
                self.log.warning(f"[OBS] Source '{source_name}' non trouvée")
                return False
            self._client.set_scene_item_enabled(scene_name, item_id, visible)
            self.log.info(
                f"[OBS] Source '{source_name}' → {'visible' if visible else 'masquée'}"
            )
            return True
        except Exception as e:
            self.log.error(f"[OBS] set_source_visibility : {e}")
            return False

    # ── Capture de frames ─────────────────────────────────────────────
    def capture_frame(self, source_name: str = None,
                       save_path: str = None) -> str | None:
        """
        Capture une frame depuis une source OBS spécifique.
        Si source_name=None, capture la scène active complète.
        Retourne le chemin de l'image sauvegardée.
        """
        if not self.is_connected():
            self.log.error("[OBS] Non connecté — impossible de capturer")
            return None

        ts   = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
        path = save_path or str(CAPTURE_DIR / f"obs_frame_{ts}.png")

        try:
            if source_name:
                # Capture d'une source spécifique
                resp = self._client.get_source_screenshot(
                    name=source_name,
                    img_format="png",
                    width=1920,
                    height=1080,
                    quality=100
                )
            else:
                # Screenshot de la scène entière
                resp = self._client.get_virtual_cam_status()
                resp = self._client.save_source_screenshot(
                    source_name=self.get_current_scene(),
                    img_format="png",
                    img_file_path=path
                )
                self.log.info(f"[OBS] Frame capturée : {path}")
                return path

            # Décoder le base64
            img_data = resp.image_data
            if img_data.startswith("data:image"):
                img_data = img_data.split(",", 1)[1]
            img_bytes = base64.b64decode(img_data)
            with open(path, "wb") as f:
                f.write(img_bytes)
            self.log.info(f"[OBS] Frame source '{source_name}' → {path}")
            return path

        except Exception as e:
            self.log.error(f"[OBS] capture_frame : {e}")
            return None

    def capture_reference_frame(self, source: str = None,
                                 scene: str = None) -> str | None:
        """
        Capture une frame de référence pour la génération IA.
        Bascule vers la scène de référence, attend la stabilisation,
        capture, puis revient à la scène précédente.
        """
        prev_scene = self.get_current_scene()

        # Basculer vers la scène de référence
        target_scene = scene or SCENE_NAMES.get("reference")
        if target_scene and target_scene in self.list_scenes():
            self.switch_scene(target_scene)
            time.sleep(1.0)  # Stabilisation

        path = self.capture_frame(source_name=source or SOURCE_NAMES.get("elgato"))

        # Revenir à la scène précédente
        if prev_scene and prev_scene != target_scene:
            self.switch_scene(prev_scene)

        return path

    def capture_sequence(self, source: str = None,
                          n_frames: int = 5,
                          interval_s: float = 1.0) -> list:
        """
        Capture une séquence de N frames espacées.
        Idéal pour sélectionner la meilleure frame de référence.
        """
        paths = []
        for i in range(n_frames):
            ts   = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
            path = str(CAPTURE_DIR / f"seq_{i:02d}_{ts}.png")
            captured = self.capture_frame(source, path)
            if captured:
                paths.append(captured)
            if i < n_frames - 1:
                time.sleep(interval_s)
        self.log.info(f"[OBS] Séquence : {len(paths)}/{n_frames} frames capturées")
        return paths

    # ── Enregistrement ────────────────────────────────────────────────
    def start_recording(self, output_path: str = None) -> bool:
        """Démarre l'enregistrement OBS."""
        if not self.is_connected(): return False
        try:
            # Configurer le dossier de sortie si spécifié
            if output_path:
                self._client.set_record_directory(output_path)

            self._client.start_record()
            self.status = OBSStatus.RECORDING
            self._record_start = time.time()
            self.log.info(f"[OBS] ● Enregistrement démarré → {output_path or 'dossier OBS par défaut'}")
            return True
        except Exception as e:
            self.log.error(f"[OBS] start_recording : {e}")
            return False

    def stop_recording(self) -> str | None:
        """Arrête l'enregistrement et retourne le chemin du fichier."""
        if self.status != OBSStatus.RECORDING: return None
        try:
            resp = self._client.stop_record()
            self.status = OBSStatus.CONNECTED
            duration = time.time() - getattr(self, "_record_start", time.time())
            output_path = getattr(resp, "output_path", None)
            self.log.info(
                f"[OBS] ■ Enregistrement arrêté — "
                f"Durée: {duration:.1f}s | Fichier: {output_path}"
            )
            return output_path
        except Exception as e:
            self.log.error(f"[OBS] stop_recording : {e}")
            return None

    def toggle_recording(self) -> bool:
        """Bascule l'enregistrement (start/stop)."""
        if self.status == OBSStatus.RECORDING:
            return self.stop_recording() is not None
        else:
            return self.start_recording()

    def get_recording_status(self) -> dict:
        """Retourne l'état de l'enregistrement."""
        if not self.is_connected(): return {}
        try:
            resp = self._client.get_record_status()
            return {
                "active":     resp.output_active,
                "paused":     resp.output_paused,
                "bytes":      resp.output_bytes,
                "duration_ms": resp.output_duration,
                "timecode":   resp.output_timecode,
            }
        except Exception as e:
            self.log.error(f"[OBS] get_recording_status : {e}")
            return {}

    # ── Streaming ─────────────────────────────────────────────────────
    def start_streaming(self) -> bool:
        """Démarre le streaming (Twitch/YouTube configuré dans OBS)."""
        if not self.is_connected(): return False
        try:
            self._client.start_stream()
            self.status = OBSStatus.STREAMING
            self.log.info("[OBS] 🔴 Streaming démarré")
            return True
        except Exception as e:
            self.log.error(f"[OBS] start_streaming : {e}")
            return False

    def stop_streaming(self) -> bool:
        """Arrête le streaming."""
        if not self.is_connected(): return False
        try:
            self._client.stop_stream()
            self.status = OBSStatus.CONNECTED
            self.log.info("[OBS] ⬛ Streaming arrêté")
            return True
        except Exception as e:
            self.log.error(f"[OBS] stop_streaming : {e}")
            return False

    def get_stream_status(self) -> dict:
        """Retourne l'état du streaming."""
        if not self.is_connected(): return {}
        try:
            resp = self._client.get_stream_status()
            return {
                "active":     resp.output_active,
                "bytes":      resp.output_bytes,
                "duration_ms": resp.output_duration,
                "congestion": resp.output_congestion,
                "reconnecting": resp.output_reconnecting,
            }
        except Exception as e:
            return {}

    # ── Filtres & Effets ──────────────────────────────────────────────
    def set_chroma_key(self, source_name: str,
                        enabled: bool = True,
                        color: str = "green") -> bool:
        """
        Active/désactive le chroma key (green screen) sur une source.
        Utile pour la webcam USB-C avec fond vert.
        """
        if not self.is_connected(): return False
        filter_name = "Chroma Key OverLord"
        try:
            if enabled:
                # Créer ou activer le filtre
                try:
                    self._client.create_source_filter(
                        source_name=source_name,
                        filter_name=filter_name,
                        filter_kind="chroma_key_filter_v2",
                        filter_settings={
                            "key_color_type": color,
                            "similarity":     400,
                            "smoothness":     80,
                            "spill":          100,
                            "opacity":        100,
                        }
                    )
                except Exception:
                    pass  # Filtre existe déjà
                self._client.set_source_filter_enabled(
                    source_name, filter_name, True
                )
                self.log.info(f"[OBS] Chroma key activé sur '{source_name}'")
            else:
                self._client.set_source_filter_enabled(
                    source_name, filter_name, False
                )
                self.log.info(f"[OBS] Chroma key désactivé sur '{source_name}'")
            return True
        except Exception as e:
            self.log.error(f"[OBS] set_chroma_key : {e}")
            return False

    # ── Intégration pipeline ──────────────────────────────────────────
    def setup_pipeline_scenes(self) -> bool:
        """
        Configure automatiquement les scènes OBS pour le pipeline OverLord.
        Crée les scènes si elles n'existent pas déjà.
        """
        if not self.is_connected(): return False
        existing = self.list_scenes()
        created  = []

        for scene_key, scene_name in SCENE_NAMES.items():
            if scene_name not in existing:
                try:
                    self._client.create_scene(scene_name)
                    created.append(scene_name)
                    self.log.info(f"[OBS] Scène créée : {scene_name}")
                except Exception as e:
                    self.log.warning(f"[OBS] Impossible de créer '{scene_name}' : {e}")

        if created:
            self.log.info(f"[OBS] {len(created)} scène(s) créée(s) pour OverLord")
        else:
            self.log.info("[OBS] Toutes les scènes OverLord sont déjà configurées")

        return True

    def record_generation_session(self, session_name: str,
                                   pipeline_fn,
                                   stop_event: threading.Event = None) -> dict:
        """
        Enregistre une session de génération complète.
        Lance l'enregistrement OBS, exécute pipeline_fn, arrête l'enregistrement.

        pipeline_fn : callable sans argument qui exécute le pipeline
        Retourne : {"recording": chemin_video, "pipeline_result": résultat}
        """
        ts         = datetime.now().strftime("%Y%m%d_%H%M%S")
        output_dir = str(RECORDING_DIR)

        self.log.info(f"[OBS] Démarrage session enregistrée : {session_name}")

        # Basculer vers scène monitoring
        monitor_scene = SCENE_NAMES.get("monitor")
        if monitor_scene in self.list_scenes():
            self.switch_scene(monitor_scene)

        # Démarrer l'enregistrement
        rec_ok = self.start_recording(output_dir)
        if not rec_ok:
            self.log.warning("[OBS] Enregistrement non disponible — pipeline continue")

        # Exécuter le pipeline
        pipeline_result = None
        try:
            pipeline_result = pipeline_fn()
        except Exception as e:
            self.log.error(f"[OBS] Erreur pipeline : {e}")

        # Arrêter l'enregistrement
        recording_path = None
        if rec_ok:
            recording_path = self.stop_recording()

        return {
            "session_name":    session_name,
            "recording":       recording_path,
            "pipeline_result": pipeline_result,
            "timestamp":       ts,
        }

    # ── Statistiques ─────────────────────────────────────────────────
    def get_stats(self) -> dict:
        """Retourne les statistiques OBS (CPU, framerate, dropped frames)."""
        if not self.is_connected(): return {}
        try:
            resp = self._client.get_stats()
            return {
                "cpu_usage":       resp.cpu_usage,
                "memory_usage":    resp.memory_usage,
                "framerate":       resp.active_fps,
                "render_total":    resp.render_total_frames,
                "render_skipped":  resp.render_skipped_frames,
                "output_total":    resp.output_total_frames,
                "output_skipped":  resp.output_skipped_frames,
            }
        except Exception as e:
            self.log.error(f"[OBS] get_stats : {e}")
            return {}

    # ── Context manager ───────────────────────────────────────────────
    def __enter__(self):
        self.connect()
        return self

    def __exit__(self, *_):
        self.disconnect()


# ── Wrapper pour le pipeline sans OBS (fallback) ─────────────────────
class OBSAgentDummy:
    """
    Version sans OBS pour les environnements sans OBS installé.
    Toutes les méthodes retournent des valeurs neutres sans erreur.
    """
    def __init__(self, *a, **kw):
        self.status = OBSStatus.DISCONNECTED
        logging.getLogger("obs").info(
            "[OBS] Mode dégradé — OBS non disponible. "
            "Installe OBS Studio + pip install obs-websocket-py pour activer."
        )

    def connect(self): return False
    def disconnect(self): pass
    def is_connected(self): return False
    def list_scenes(self): return []
    def switch_scene(self, *a): return False
    def capture_frame(self, *a, **kw): return None
    def capture_reference_frame(self, *a, **kw): return None
    def capture_sequence(self, *a, **kw): return []
    def start_recording(self, *a): return False
    def stop_recording(self): return None
    def start_streaming(self): return False
    def stop_streaming(self): return False
    def setup_pipeline_scenes(self): return False
    def get_stats(self): return {}
    def record_generation_session(self, name, fn, **kw):
        return {"session_name": name, "recording": None,
                "pipeline_result": fn(), "timestamp": ""}
    def __enter__(self): return self
    def __exit__(self, *_): pass


def create_obs_agent(host=OBS_WS_HOST, port=OBS_WS_PORT,
                     password=OBS_WS_PASS,
                     logger=None) -> OBSAgent | OBSAgentDummy:
    """
    Factory : retourne un OBSAgent réel si obs-websocket-py est installé,
    sinon un OBSAgentDummy qui ne bloque pas le pipeline.
    """
    try:
        import obsws_python  # noqa
        return OBSAgent(host, port, password, logger)
    except ImportError:
        return OBSAgentDummy(logger=logger)


# ── Script de configuration OBS (à exécuter une fois) ────────────────
OBS_SETUP_INSTRUCTIONS = """
╔══════════════════════════════════════════════════════════════════╗
║  CONFIGURATION OBS POUR OverLord Pipeline                       ║
╠══════════════════════════════════════════════════════════════════╣
║                                                                  ║
║  1. Installer OBS Studio >= 28                                   ║
║     https://obsproject.com                                       ║
║                                                                  ║
║  2. Activer obs-websocket                                        ║
║     Outils → obs-websocket Server Settings                       ║
║     ✓ Enable WebSocket Server                                    ║
║     Port : 4455                                                  ║
║     Mot de passe : (laisser vide ou noter dans config)          ║
║                                                                  ║
║  3. Configurer les sources                                       ║
║     Créer une scène "OverLord - Référence"                      ║
║     ➕ Source → Video Capture Device → Elgato 4K Pro            ║
║     ➕ Source → Video Capture Device → Webcam USB-C             ║
║                                                                  ║
║  4. Installer le package Python                                  ║
║     pip install obs-websocket-py                                 ║
║                                                                  ║
║  5. Tester la connexion                                          ║
║     python agents/obs_agent.py                                   ║
║                                                                  ║
╚══════════════════════════════════════════════════════════════════╝
"""


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    print(OBS_SETUP_INSTRUCTIONS)

    log = logging.getLogger("obs_test")
    agent = create_obs_agent(logger=log)

    if agent.connect():
        print("\n=== Connexion réussie ===")
        scenes  = agent.list_scenes()
        print(f"Scènes : {scenes}")
        stats   = agent.get_stats()
        print(f"Stats OBS : {stats}")

        # Configurer les scènes OverLord
        agent.setup_pipeline_scenes()

        # Test capture
        frame = agent.capture_frame()
        if frame:
            print(f"Frame capturée : {frame}")

        agent.disconnect()
    else:
        print("\nOBS non disponible — vérifie la configuration ci-dessus")

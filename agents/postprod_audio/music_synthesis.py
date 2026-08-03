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
agents/music_synthesis.py -- Ov3rLoRd -- Text-to-Music (ADR-012 / DOCS/ADR_MUSIC.md)
Génération de bande-son d'ambiance via MusicGen (transformers.MusicgenForConditionalGeneration),
modèle `small` par défaut.

Contraintes issues de l'ADR :
  - Poids MusicGen sous licence CC-BY-NC 4.0 (recherche/non-commercial uniquement) :
    toute piste générée ici est marquée non-commerciale dans ses métadonnées de sortie
    (sidecar JSON + ledger `workspace/logs/music_licenses.jsonl`), et l'agent de
    publication (`agents/transmedia_publisher.py`) doit bloquer toute mise en ligne
    monétisée qui inclurait une de ces pistes.
  - Génération séquentielle, jamais concurrente de ComfyUI : passe par
    `agents/resource_scheduler.py` (agent "music_synthesis", même logique que
    dream_mode/postprod) plutôt que de charger le modèle en parallèle d'une
    génération d'image en cours.
  - Échec/OOM = fallback silencieux (cohérent avec ADR-009 : le pipeline ne
    s'arrête jamais) -- retourne None, ne lève jamais d'exception vers l'appelant.
"""

import json
import logging
from pathlib import Path
from datetime import datetime, timezone

try:
    from agents.resource_scheduler import get_scheduler
    SCHEDULER_OK = True
except ImportError:
    SCHEDULER_OK = False

try:
    from agents.context_bus import get_bus
    BUS_OK = True
except ImportError:
    BUS_OK = False

MUSIC_DIR   = Path("workspace/music_synthesis")
LICENSE_LOG = Path("workspace/logs/music_licenses.jsonl")
log         = logging.getLogger("music_synthesis")

MUSICGEN_MODELS = {
    "small":  "facebook/musicgen-small",
    "medium": "facebook/musicgen-medium",
    "large":  "facebook/musicgen-large",
}

# Licence des poids pré-entraînés MusicGen -- cf. DOCS/ADR_MUSIC.md.
# Ne JAMAIS passer à True sans négociation de licence commerciale avec Meta.
MUSICGEN_LICENSE      = "CC-BY-NC-4.0"
MUSICGEN_COMMERCIAL_OK = False

DEFAULT_SAMPLE_RATE = 32000  # sample_rate natif de MusicGen


class MusicSynthesis:
    """Wrapper MusicGen -- chargement paresseux, un seul modèle en mémoire à la fois."""

    def __init__(self, model_size: str = "small", logger: logging.Logger = None):
        if model_size not in MUSICGEN_MODELS:
            model_size = "small"
        self.model_size = model_size
        self.model_id   = MUSICGEN_MODELS[model_size]
        self.log        = logger or log
        self._model     = None
        self._processor = None
        self._device    = None
        MUSIC_DIR.mkdir(parents=True, exist_ok=True)

    def _ensure_loaded(self) -> bool:
        """Charge le modèle/processor à la demande. Retourne False si indisponible."""
        if self._model is not None:
            return True
        try:
            import torch
            from transformers import MusicgenForConditionalGeneration, AutoProcessor

            self._device    = "cuda" if torch.cuda.is_available() else "cpu"
            self._processor = AutoProcessor.from_pretrained(self.model_id)
            self._model     = MusicgenForConditionalGeneration.from_pretrained(
                self.model_id
            ).to(self._device)
            self.log.info(f"[MUSIC] Modèle chargé : {self.model_id} sur {self._device}")
            return True
        except Exception as e:
            self.log.warning(f"[MUSIC] Chargement modèle échoué ({self.model_id}) : {e}")
            self._model = None
            self._processor = None
            return False

    def generate(self, prompt: str, duration_s: float = 15.0,
                 shot_id: str = "") -> "MusicTrack | None":
        """
        Génère une piste d'ambiance à partir d'un prompt texte.
        Fallback silencieux (retourne None) sur échec, OOM, ou absence de dépendances.
        Ne tourne jamais en parallèle de ComfyUI (token resource_scheduler requis).
        """
        if not prompt:
            return None

        token = None
        if SCHEDULER_OK:
            token = get_scheduler().request("music_synthesis", timeout=600.0)
            if token is None:
                self.log.warning("[MUSIC] Timeout scheduler -- VRAM indisponible, génération annulée")
                return None

        try:
            return self._generate_locked(prompt, duration_s, shot_id)
        except Exception as e:
            self._handle_failure(e)
            return None
        finally:
            if SCHEDULER_OK and token is not None:
                get_scheduler().release(token)

    def _generate_locked(self, prompt: str, duration_s: float,
                          shot_id: str) -> "MusicTrack | None":
        if not self._ensure_loaded():
            return None

        import torch

        # ~50 tokens/s de sortie audio pour MusicGen -- approximation documentée HF.
        max_new_tokens = max(1, int(duration_s * 50))

        inputs = self._processor(text=[prompt], padding=True, return_tensors="pt").to(self._device)
        with torch.no_grad():
            audio_values = self._model.generate(**inputs, max_new_tokens=max_new_tokens)

        sample_rate = getattr(self._model.config.audio_encoder, "sampling_rate", DEFAULT_SAMPLE_RATE)
        waveform = audio_values[0, 0].detach().cpu().numpy()

        ts       = datetime.now(tz=timezone.utc).strftime("%Y%m%d_%H%M%S_%f")
        stem     = f"{shot_id or 'music'}_{ts}"
        out_path = MUSIC_DIR / f"{stem}.wav"

        import scipy.io.wavfile as wavfile
        wavfile.write(str(out_path), rate=int(sample_rate), data=waveform)

        track = MusicTrack(
            path=out_path,
            prompt=prompt,
            duration_s=duration_s,
            model_id=self.model_id,
            shot_id=shot_id,
        )
        self._write_metadata(track)
        self.log.info(f"[MUSIC] Piste générée : {out_path.name} ({duration_s}s, {self.model_id})")
        return track

    def _handle_failure(self, exc: Exception):
        msg = str(exc)
        is_oom = "out of memory" in msg.lower() or exc.__class__.__name__ == "OutOfMemoryError"
        if is_oom:
            self.log.warning(f"[MUSIC] OOM pendant la génération -- fallback silencieux : {msg}")
            try:
                import torch
                torch.cuda.empty_cache()
            except Exception:
                pass
        else:
            self.log.warning(f"[MUSIC] Échec génération -- fallback silencieux : {msg}")
        # Libère le modèle pour retenter proprement au prochain appel.
        self._model = None
        self._processor = None
        if BUS_OK:
            try:
                get_bus().write("music.last_generation_failed", True, agent_id="music_synthesis")
            except Exception:
                pass

    def _write_metadata(self, track: "MusicTrack"):
        """Écrit le sidecar JSON + le ledger de licence -- source de vérité pour le publisher."""
        meta = track.to_metadata()
        sidecar = track.path.with_suffix(".json")
        try:
            sidecar.write_text(json.dumps(meta, indent=2, ensure_ascii=False), encoding="utf-8")
        except Exception as e:
            self.log.warning(f"[MUSIC] Écriture sidecar échouée : {e}")

        try:
            LICENSE_LOG.parent.mkdir(parents=True, exist_ok=True)
            with open(LICENSE_LOG, "a", encoding="utf-8") as f:
                f.write(json.dumps(meta, ensure_ascii=False) + "\n")
        except Exception as e:
            self.log.warning(f"[MUSIC] Écriture ledger licence échouée : {e}")

        if BUS_OK:
            try:
                get_bus().write("music.last_track", str(track.path), agent_id="music_synthesis")
                get_bus().write("music.last_track_non_commercial", True, agent_id="music_synthesis")
            except Exception:
                pass


class MusicTrack:
    """Piste générée + métadonnées de licence associées."""

    def __init__(self, path: Path, prompt: str, duration_s: float,
                 model_id: str, shot_id: str = ""):
        self.path       = path
        self.prompt     = prompt
        self.duration_s = duration_s
        self.model_id   = model_id
        self.shot_id    = shot_id
        self.generated_at = datetime.now(tz=timezone.utc).isoformat()

    def to_metadata(self) -> dict:
        return {
            "path":               str(self.path),
            "shot_id":            self.shot_id,
            "prompt":             self.prompt,
            "duration_s":         self.duration_s,
            "model":              self.model_id,
            "engine":             "transformers.MusicgenForConditionalGeneration",
            "license":            MUSICGEN_LICENSE,
            "non_commercial":     True,
            "commercial_use_allowed": MUSICGEN_COMMERCIAL_OK,
            "generated_at":       self.generated_at,
            "notice": (
                "Généré avec Meta MusicGen (poids CC-BY-NC 4.0). Usage non-commercial "
                "uniquement -- voir DOCS/ADR_MUSIC.md. Ne pas inclure dans un contenu "
                "monétisé sans piste de remplacement sous licence commerciale."
            ),
        }


def get_track_metadata(audio_path: Path) -> dict | None:
    """
    Lit le sidecar JSON d'une piste générée. Utilisé par l'agent de publication
    pour décider si une piste peut accompagner une vidéo monétisée.
    """
    audio_path = Path(audio_path)
    sidecar = audio_path.with_suffix(".json")
    if sidecar.exists():
        try:
            return json.loads(sidecar.read_text(encoding="utf-8"))
        except Exception:
            return None

    # Fallback : chercher dans le ledger si le sidecar a disparu.
    if LICENSE_LOG.exists():
        try:
            for line in LICENSE_LOG.read_text(encoding="utf-8", errors="replace").splitlines():
                rec = json.loads(line)
                if rec.get("path") == str(audio_path):
                    return rec
        except Exception:
            pass
    return None


def is_non_commercial_track(audio_path: Path) -> bool:
    """True si la piste est marquée non-commerciale (ou si son statut est inconnu -- fail-safe)."""
    meta = get_track_metadata(audio_path)
    if meta is None:
        # Statut inconnu : on ne peut pas garantir une licence commerciale -> traité comme bloquant.
        return True
    return bool(meta.get("non_commercial", True)) and not meta.get("commercial_use_allowed", False)


if __name__ == "__main__":
    import sys, io
    if hasattr(sys.stdout, "buffer"):
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    logging.basicConfig(level=logging.INFO)
    ms = MusicSynthesis(model_size="small")
    track = ms.generate("calm ambient anime ost, soft piano, melancholic", duration_s=10.0, shot_id="test")
    print(f"Track générée : {track.path if track else None}")

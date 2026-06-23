"""
agents/sourcing_multisensor.py — SSS Multi-Sensoriel OverLord
Sourcing qui va au-delà du web : audio, manga local, radio, IA croisée.

Sources ingérées :
  1. Base locale (animes/mangas/mp3) — catalogue indexé
  2. Analyse audio (librosa) — mood, BPM, genre → influence visuelle
  3. Flux radio/streaming (icecast, YouTube audio) — tendances live
  4. LLMs locaux croisés (Ollama) — brainstorming multi-IA
  5. Web classique (Reddit, RSS, Trends) — baseline

Sortie : brief enrichi multi-sensoriel avec suggestions visuelles,
         tonalités sonores, références manga et prompts ComfyUI enrichis.

pip install librosa yt-dlp mutagen pillow requests
"""

import json
import logging
import threading
import hashlib
import time
import subprocess
import re
from pathlib import Path
from datetime import datetime
from dataclasses import dataclass, field
from typing import Optional
import requests

# ── Dépendances optionnelles ──────────────────────────────────────────
try:
    import librosa
    import numpy as np
    LIBROSA_OK = True
except ImportError:
    LIBROSA_OK = False

try:
    from mutagen import File as MutagenFile
    MUTAGEN_OK = True
except ImportError:
    MUTAGEN_OK = False

ASSET_DB_FILE  = Path("workspace/asset_catalog.json")
AUDIO_CACHE    = Path("workspace/audio_cache")
RADIO_CACHE    = Path("workspace/radio_cache")
OLLAMA_URL     = "http://localhost:11434"
ANTHROPIC_URL  = "https://api.anthropic.com/v1/messages"
CLAUDE_MODEL   = "claude-sonnet-4-6"


@dataclass
class MediaAsset:
    """Un asset de la base locale."""
    path:       str
    type:       str          # "anime", "manga", "music", "sfx", "image"
    title:      str = ""
    artist:     str = ""
    genre:      str = ""
    mood:       str = ""
    bpm:        float = 0.0
    key:        str = ""     # tonalité musicale
    tags:       list = field(default_factory=list)
    color_palette: list = field(default_factory=list)  # pour les images/manga
    analyzed:   bool = False
    hash:       str = ""


class LocalAssetCatalog:
    """
    Catalogue indexé de la base locale (animes, mangas, mp3).
    Scan récursif + analyse audio/image.
    """

    EXTENSIONS = {
        "anime":   [".mp4",".mkv",".avi",".webm"],
        "manga":   [".cbz",".cbr",".pdf",".jpg",".jpeg",".png",".webp"],
        "music":   [".mp3",".flac",".wav",".ogg",".aac",".m4a"],
        "sfx":     [".wav",".mp3",".ogg"],
    }

    def __init__(self, base_dirs: list[str] = None,
                 logger: logging.Logger = None):
        self.log      = logger or logging.getLogger("catalog")
        self.base_dirs = [Path(d) for d in (base_dirs or [])]
        self._assets: dict[str, MediaAsset] = {}
        self._load_catalog()
        AUDIO_CACHE.mkdir(parents=True, exist_ok=True)

    def scan(self, force: bool = False) -> int:
        """Scanne les dossiers et indexe les nouveaux fichiers."""
        new_count = 0
        for base in self.base_dirs:
            if not base.exists():
                self.log.warning(f"[CATALOG] Dossier introuvable : {base}")
                continue
            self.log.info(f"[CATALOG] Scan : {base}")
            for ftype, exts in self.EXTENSIONS.items():
                for ext in exts:
                    for fpath in base.rglob(f"*{ext}"):
                        fhash = hashlib.md5(str(fpath).encode()).hexdigest()[:12]
                        if fhash not in self._assets or force:
                            asset = MediaAsset(
                                path=str(fpath),
                                type=ftype,
                                title=fpath.stem,
                                hash=fhash,
                            )
                            self._extract_metadata(asset)
                            self._assets[fhash] = asset
                            new_count += 1
        self._save_catalog()
        self.log.info(f"[CATALOG] {new_count} nouveaux assets | Total : {len(self._assets)}")
        return new_count

    def _extract_metadata(self, asset: MediaAsset):
        """Extrait les métadonnées selon le type."""
        p = Path(asset.path)

        # Tags ID3/Vorbis pour audio
        if MUTAGEN_OK and asset.type in ("music","sfx"):
            try:
                m = MutagenFile(str(p))
                if m:
                    tags = m.tags or {}
                    asset.artist = str(tags.get("TPE1", tags.get("ARTIST",[""]))[0] if hasattr(tags.get("TPE1",[""]),"__iter__") else "")
                    asset.genre  = str(tags.get("TCON", tags.get("GENRE", [""]))[0]  if hasattr(tags.get("TCON",[""]),"__iter__") else "")
                    asset.title  = str(tags.get("TIT2", tags.get("TITLE", [p.stem]))[0] if hasattr(tags.get("TIT2",[p.stem]),"__iter__") else p.stem)
            except Exception:
                pass

        # Analyse audio avec librosa
        if LIBROSA_OK and asset.type == "music" and not asset.analyzed:
            try:
                y, sr = librosa.load(str(p), duration=60)  # 60s max
                tempo, _ = librosa.beat.beat_track(y=y, sr=sr)
                asset.bpm = round(float(tempo), 1)

                # Mood approximatif depuis le chroma
                chroma = librosa.feature.chroma_stft(y=y, sr=sr)
                energy = float(np.mean(librosa.feature.rms(y=y)))
                zcr    = float(np.mean(librosa.feature.zero_crossing_rate(y=y)))

                if energy > 0.1 and asset.bpm > 120:
                    asset.mood = "energetic"
                elif energy < 0.05:
                    asset.mood = "ambient"
                elif asset.bpm > 100:
                    asset.mood = "upbeat"
                else:
                    asset.mood = "melodic"

                # Tonalité
                chroma_avg = chroma.mean(axis=1)
                keys = ["C","C#","D","D#","E","F","F#","G","G#","A","A#","B"]
                asset.key = keys[int(chroma_avg.argmax())]
                asset.analyzed = True
            except Exception as e:
                self.log.debug(f"[CATALOG] Audio analyze {p.name}: {e}")

    def search(self, query: str = "", mood: str = "",
               genre: str = "", asset_type: str = "",
               n: int = 10) -> list[MediaAsset]:
        """Recherche dans le catalogue."""
        results = list(self._assets.values())
        if asset_type:
            results = [a for a in results if a.type == asset_type]
        if mood:
            results = [a for a in results if mood.lower() in a.mood.lower()]
        if genre:
            results = [a for a in results if genre.lower() in a.genre.lower()]
        if query:
            q = query.lower()
            results = [a for a in results
                       if q in a.title.lower() or q in a.artist.lower()
                       or any(q in t for t in a.tags)]
        return results[:n]

    def get_mood_summary(self) -> dict:
        """Résumé des moods dans le catalogue audio."""
        moods = {}
        for a in self._assets.values():
            if a.mood:
                moods[a.mood] = moods.get(a.mood, 0) + 1
        return moods

    def _save_catalog(self):
        ASSET_DB_FILE.parent.mkdir(parents=True, exist_ok=True)
        data = {k: {
            "path":  v.path, "type":   v.type, "title":  v.title,
            "artist":v.artist,"genre":  v.genre, "mood":   v.mood,
            "bpm":   v.bpm,  "key":    v.key,   "tags":   v.tags,
            "analyzed":v.analyzed, "hash": v.hash,
        } for k, v in self._assets.items()}
        ASSET_DB_FILE.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")

    def _load_catalog(self):
        if ASSET_DB_FILE.exists():
            try:
                data = json.loads(ASSET_DB_FILE.read_text(encoding="utf-8"))
                self._assets = {k: MediaAsset(**v) for k, v in data.items()}
            except Exception:
                self._assets = {}


class RadioListener:
    """
    Écoute des flux radio/streaming pour détecter les tendances en temps réel.
    Captures des segments audio → analyse mood → influence le sourcing.
    """

    STREAMS = {
        "anison_fm":     "https://anison.fm/anison.m3u",
        "j-pop_forever": "http://www.j-popforever.com/stream",
        "lofi_chill":    "https://lofi.stream.laut.fm/lofi",
    }

    def __init__(self, logger: logging.Logger = None):
        self.log = logger or logging.getLogger("radio")
        RADIO_CACHE.mkdir(parents=True, exist_ok=True)

    def capture_segment(self, stream_url: str, duration_s: int = 30,
                         stream_name: str = "radio") -> Optional[str]:
        """
        Capture un segment audio depuis un flux radio.
        Utilise ffmpeg pour enregistrer N secondes.
        """
        ts       = datetime.now().strftime("%Y%m%d_%H%M%S")
        out_path = str(RADIO_CACHE / f"{stream_name}_{ts}.mp3")
        cmd = [
            "ffmpeg", "-i", stream_url,
            "-t", str(duration_s),
            "-acodec", "mp3", "-ab", "128k",
            "-y", out_path, "-loglevel", "quiet"
        ]
        try:
            result = subprocess.run(cmd, timeout=duration_s + 10,
                                     capture_output=True)
            if Path(out_path).exists():
                self.log.info(f"[RADIO] Segment capturé : {out_path}")
                return out_path
        except Exception as e:
            self.log.debug(f"[RADIO] Capture {stream_name} : {e}")
        return None

    def analyze_segment(self, audio_path: str) -> dict:
        """Analyse un segment capturé."""
        if not LIBROSA_OK:
            return {"mood": "unknown", "bpm": 0}
        try:
            y, sr = librosa.load(audio_path, duration=30)
            tempo, _ = librosa.beat.beat_track(y=y, sr=sr)
            energy    = float(np.mean(librosa.feature.rms(y=y)))
            mood = "energetic" if energy > 0.08 and tempo > 120 else "chill"
            return {"mood": mood, "bpm": round(float(tempo), 1),
                    "energy": round(energy, 4)}
        except Exception as e:
            self.log.debug(f"[RADIO] Analyze : {e}")
            return {"mood": "unknown", "bpm": 0}

    def get_live_mood(self, stream_name: str = "anison_fm") -> dict:
        """Retourne le mood live d'une station radio."""
        url = self.STREAMS.get(stream_name, "")
        if not url:
            return {"mood": "unknown"}
        path = self.capture_segment(url, duration_s=20, stream_name=stream_name)
        if path:
            result = self.analyze_segment(path)
            result["stream"] = stream_name
            return result
        return {"mood": "unknown", "stream": stream_name}


class MultiSensorSourcer:
    """
    Agent SSS Multi-Sensoriel — orchestrateur de toutes les sources.
    Croise web + audio + manga + radio + LLMs pour un brief ultra-enrichi.
    """

    def __init__(self, catalog_dirs: list[str] = None,
                 logger: logging.Logger = None,
                 use_radio: bool = False):
        self.log       = logger or logging.getLogger("multisensor")
        self.catalog   = LocalAssetCatalog(catalog_dirs or [], logger=self.log)
        self.radio     = RadioListener(logger=self.log)
        self.use_radio = use_radio
        self._trending_cache = {}

    def full_source(self, query: str = "",
                    media_type: str = "anime",
                    universe: str   = "",
                    n_llm_rounds: int = 2) -> dict:
        """
        Sourcing complet multi-sensoriel.

        Phases :
          1. Tendances web (Reddit/Trends/RSS)
          2. Catalogue local (références pertinentes)
          3. Analyse audio (mood dominant)
          4. Radio live (optionnel)
          5. Croisement LLM (brainstorming)
          6. Synthèse finale
        """
        self.log.info(f"[SSS] Sourcing multi-sensoriel : '{query}' | {media_type}")
        results = {
            "query":        query,
            "media_type":   media_type,
            "universe":     universe,
            "timestamp":    datetime.utcnow().isoformat(),
            "web_trends":   {},
            "local_refs":   [],
            "audio_mood":   {},
            "radio_live":   {},
            "llm_insights": [],
            "brief":        "",
            "prompt_enrichments": [],
        }

        threads = []
        def _web():
            results["web_trends"] = self._fetch_web_trends(query, media_type)
        def _local():
            results["local_refs"] = self._search_local(query, media_type)
        def _audio():
            results["audio_mood"] = self._analyze_local_audio(media_type)

        for fn in [_web, _local, _audio]:
            t = threading.Thread(target=fn, daemon=True)
            t.start(); threads.append(t)

        # Radio en parallèle si activée
        if self.use_radio:
            def _radio():
                results["radio_live"] = self.radio.get_live_mood()
            t = threading.Thread(target=_radio, daemon=True)
            t.start(); threads.append(t)

        for t in threads:
            t.join(timeout=30)

        # Croisement LLM (séquentiel car Ollama = 1 thread)
        for round_n in range(n_llm_rounds):
            insight = self._llm_cross(results, round_n + 1)
            if insight:
                results["llm_insights"].append(insight)

        # Synthèse finale
        results["brief"] = self._synthesize(results)
        results["prompt_enrichments"] = self._generate_prompt_tags(results)

        self.log.info(
            f"[SSS] Brief généré — "
            f"web:{bool(results['web_trends'])} | "
            f"local:{len(results['local_refs'])} refs | "
            f"mood:{results['audio_mood'].get('dominant','?')} | "
            f"insights:{len(results['llm_insights'])}"
        )
        return results

    def _fetch_web_trends(self, query: str, media_type: str) -> dict:
        """Tendances web classiques."""
        trends = {}
        # Google Trends via pytrends
        try:
            from pytrends.request import TrendReq
            pt = TrendReq(hl="fr-FR", tz=360)
            terms = [query] if query else [media_type, "anime 2025", "manga trending"]
            pt.build_payload(terms[:5], timeframe="now 7-d")
            interest = pt.interest_over_time()
            if not interest.empty:
                trends["google_score"] = float(interest[terms[0]].mean()) if terms[0] in interest else 0
        except Exception:
            pass
        # Reddit
        try:
            r = requests.get(
                "https://www.reddit.com/r/anime/hot.json?limit=10",
                headers={"User-Agent": "OverLord/1.0"},
                timeout=10
            )
            if r.status_code == 200:
                posts = r.json()["data"]["children"]
                trends["reddit_hot"] = [
                    p["data"]["title"] for p in posts[:5]
                ]
        except Exception:
            pass
        return trends

    def _search_local(self, query: str, media_type: str) -> list[dict]:
        """Recherche dans le catalogue local."""
        asset_type_map = {
            "anime":  "anime",
            "manga":  "manga",
            "3d":     "music",
            "film":   "anime",
        }
        atype = asset_type_map.get(media_type, "")
        assets = self.catalog.search(
            query=query,
            asset_type=atype,
            n=8
        )
        return [
            {"title": a.title, "type": a.type, "mood": a.mood,
             "genre": a.genre, "bpm": a.bpm, "path": a.path}
            for a in assets
        ]

    def _analyze_local_audio(self, media_type: str) -> dict:
        """Analyse les assets audio du catalogue pour extraire le mood dominant."""
        music_assets = self.catalog.search(asset_type="music", n=50)
        if not music_assets:
            return {"dominant": "unknown", "bpm_avg": 0, "moods": {}}

        moods = {}
        bpms  = []
        for a in music_assets:
            if a.mood:
                moods[a.mood] = moods.get(a.mood, 0) + 1
            if a.bpm > 0:
                bpms.append(a.bpm)

        dominant = max(moods, key=moods.get) if moods else "unknown"
        bpm_avg  = round(sum(bpms)/len(bpms), 1) if bpms else 0

        return {
            "dominant":  dominant,
            "bpm_avg":   bpm_avg,
            "moods":     moods,
            "total_tracks": len(music_assets),
        }

    def _llm_cross(self, results: dict, round_n: int) -> str:
        """
        Croisement des sources via LLM.
        Round 1 : brainstorming depuis les données.
        Round 2 : raffinement et insights inattendus.
        """
        web_summary = json.dumps(results.get("web_trends",{})
                                  , ensure_ascii=False)[:500]
        local_titles = [r.get("title","") for r in results.get("local_refs",[])][:5]
        mood_info    = results.get("audio_mood",{})
        prev_insights = results.get("llm_insights",[])

        if round_n == 1:
            prompt = (
                f"Tu es un créateur de contenus anime/manga expert en tendances culturelles. "
                f"À partir de ces données croisées, génère 3 concepts créatifs originaux :\n\n"
                f"Tendances web : {web_summary}\n"
                f"Références locales : {local_titles}\n"
                f"Mood musical dominant : {mood_info.get('dominant','?')} "
                f"(BPM moyen : {mood_info.get('bpm_avg',0)})\n\n"
                f"Univers cible : {results.get('universe','libre')}\n"
                f"Type de média : {results.get('media_type','anime')}\n\n"
                f"Propose 3 concepts en 2 phrases chacun. Sois créatif et inattendu."
            )
        else:
            prev = "\n".join(prev_insights)
            prompt = (
                f"Tu analyses ces concepts créatifs générés au round 1 :\n{prev}\n\n"
                f"Identifie 2 connexions inattendues ou synergies entre ces idées "
                f"et les données sources. Propose comment les fusionner en un concept "
                f"unique et fort pour un {results.get('media_type','anime')}."
            )

        # Essayer Claude d'abord, puis Ollama
        try:
            resp = requests.post(
                ANTHROPIC_URL,
                headers={
                "Content-Type": "application/json",
                "x-api-key": _get_api_key(),
                "anthropic-version": "2023-06-01",
            },
                json={
                    "model": CLAUDE_MODEL, "max_tokens": 400,
                    "messages": [{"role":"user","content": prompt}]
                },
                timeout=30
            )
            if resp.status_code == 200:
                return resp.json()["content"][0]["text"].strip()
        except Exception:
            pass

        # Fallback Ollama
        try:
            resp = requests.post(
                f"{OLLAMA_URL}/api/generate",
                json={"model":"llama3","prompt":prompt,"stream":False},
                timeout=60
            )
            if resp.status_code == 200:
                return resp.json().get("response","")
        except Exception:
            pass
        return ""

    def _synthesize(self, results: dict) -> str:
        """Synthèse finale du brief multi-sensoriel."""
        lines = [
            f"=== BRIEF MULTI-SENSORIEL — {datetime.now().strftime('%d/%m/%Y %H:%M')} ===",
            f"Média cible     : {results['media_type']}",
            f"Univers         : {results.get('universe','libre')}",
            "",
        ]
        if results.get("web_trends",{}).get("reddit_hot"):
            lines.append("Tendances Reddit :")
            for t in results["web_trends"]["reddit_hot"][:3]:
                lines.append(f"  • {t}")
        if results.get("local_refs"):
            lines.append(f"\nRéférences locales ({len(results['local_refs'])}) :")
            for r in results["local_refs"][:3]:
                lines.append(f"  • {r['title']} ({r['type']}, mood:{r['mood']})")
        mood = results.get("audio_mood",{})
        if mood.get("dominant"):
            lines.append(f"\nAtmosphère sonore : {mood['dominant']} @ {mood.get('bpm_avg',0)} BPM")
        if results.get("llm_insights"):
            lines.append("\nInsights créatifs :")
            for insight in results["llm_insights"]:
                lines.append(f"  → {insight[:200]}")
        return "\n".join(lines)

    def _generate_prompt_tags(self, results: dict) -> list[str]:
        """Génère des tags ComfyUI supplémentaires depuis les données multi-sensorielles."""
        tags = []
        mood = results.get("audio_mood",{}).get("dominant","")
        bpm  = results.get("audio_mood",{}).get("bpm_avg", 0)

        # Mood musical → style visuel
        mood_to_visual = {
            "energetic":  ["dynamic angle", "action pose", "motion blur", "vibrant colors"],
            "ambient":    ["soft lighting", "dreamy atmosphere", "pastel colors", "bokeh"],
            "upbeat":     ["cheerful expression", "bright colors", "sunny", "smile"],
            "melodic":    ["emotional expression", "cinematic", "warm tones"],
        }
        tags.extend(mood_to_visual.get(mood, []))

        # BPM → énergie de la scène
        if bpm > 140:   tags.append("intense scene")
        elif bpm > 100: tags.append("dynamic composition")
        elif bpm < 70:  tags.append("peaceful atmosphere")

        # Genres manga locaux → style
        local_genres = [r.get("genre","") for r in results.get("local_refs",[])]
        if "action" in " ".join(local_genres).lower():
            tags.append("battle scene")
        if "romance" in " ".join(local_genres).lower():
            tags.append("soft romantic lighting")

        return list(set(tags))

    def scan_catalog(self, force: bool = False) -> int:
        """Lance le scan du catalogue local."""
        return self.catalog.scan(force=force)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    log = logging.getLogger("sss_test")

    # Test avec dossiers locaux (adapte les chemins)
    catalog_dirs = [
        r"D:\Animes", r"D:\Mangas", r"D:\Musique",
    ]
    sourcer = MultiSensorSourcer(catalog_dirs=catalog_dirs, logger=log)
    n = sourcer.scan_catalog()
    log.info(f"Catalogue : {n} assets")

    brief = sourcer.full_source(
        query="Dragon Ball",
        media_type="anime",
        universe="Shonen épique",
        n_llm_rounds=1,
    )
    print("\n" + brief["brief"])
    print("\nTags additionnels :", brief["prompt_enrichments"])

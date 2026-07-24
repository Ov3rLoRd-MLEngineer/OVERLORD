"""
agents/synchronicity.py -- Ov3rLoRd V1.40 -- Synchronicity Engine
Timeline unifiee audio/video/sous-titres a la milliseconde.
V1.49o : overlord_utils centralise, context_bus connecte.
"""

import json
import time
import subprocess
import logging
from pathlib import Path
from datetime import timedelta, timezone, datetime
from dataclasses import dataclass, field
from typing import Optional

try:
    from agents.overlord_utils import fallback_llm, safe_json_parse
    UTILS_OK = True
except ImportError:
    UTILS_OK = False
    fallback_llm    = None
    safe_json_parse = None

try:
    from agents.context_bus import get_bus
    BUS_OK = True
except ImportError:
    BUS_OK = False

SYNC_DIR     = Path("workspace/synchronicity")
CLAUDE_MODEL = "claude-sonnet-4-6"
log          = logging.getLogger("synchronicity")


def _llm(prompt: str, system: str = "", max_tokens: int = 300) -> str:
    if UTILS_OK and fallback_llm:
        return fallback_llm(prompt, system=system, model=CLAUDE_MODEL, max_tokens=max_tokens)
    return ""


# ── Structures de donnees ─────────────────────────────────────────────
@dataclass
class SyncPoint:
    time_ms:   float
    type:      str    # dialogue|music_beat|vfx|subtitle|chapter
    content:   str    = ""
    duration_ms:float = 0.0
    shot_id:   str    = ""
    metadata:  dict   = field(default_factory=dict)

    def to_srt_time(self) -> str:
        td = timedelta(milliseconds=self.time_ms)
        h  = int(td.total_seconds() // 3600)
        m  = int((td.total_seconds() % 3600) // 60)
        s  = int(td.total_seconds() % 60)
        ms = int(self.time_ms % 1000)
        return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"


@dataclass
class TimelineTrack:
    name:   str
    type:   str    # video|audio|subtitle|effect
    points: list[SyncPoint] = field(default_factory=list)

    def add(self, point: SyncPoint):
        self.points.append(point)
        self.points.sort(key=lambda p: p.time_ms)

    @property
    def duration_ms(self) -> float:
        if not self.points:
            return 0.0
        last = self.points[-1]
        return last.time_ms + last.duration_ms


class Timeline:
    """Timeline unifiee de tous les elements de production."""

    def __init__(self, project_title: str):
        self.title  = project_title
        self.tracks: dict[str, TimelineTrack] = {
            "video":    TimelineTrack("video",    "video"),
            "dialogue": TimelineTrack("dialogue", "audio"),
            "music":    TimelineTrack("music",    "audio"),
            "subtitle": TimelineTrack("subtitle", "subtitle"),
            "vfx":      TimelineTrack("vfx",      "effect"),
        }

    def add_shot(self, shot_id: str, start_ms: float, duration_ms: float):
        self.tracks["video"].add(SyncPoint(
            time_ms=start_ms, type="shot",
            shot_id=shot_id, duration_ms=duration_ms
        ))

    def add_dialogue(self, text: str, start_ms: float, duration_ms: float,
                     shot_id: str = ""):
        self.tracks["dialogue"].add(SyncPoint(
            time_ms=start_ms, type="dialogue",
            content=text, duration_ms=duration_ms, shot_id=shot_id
        ))
        self.tracks["subtitle"].add(SyncPoint(
            time_ms=start_ms, type="subtitle",
            content=text, duration_ms=duration_ms
        ))

    def add_music_beat(self, beat_type: str, start_ms: float):
        self.tracks["music"].add(SyncPoint(
            time_ms=start_ms, type="music_beat", content=beat_type
        ))

    @property
    def total_duration_ms(self) -> float:
        durations = [t.duration_ms for t in self.tracks.values() if t.points]
        return max(durations) if durations else 0.0

    def export_srt(self) -> str:
        lines = []
        idx   = 1
        for pt in self.tracks["subtitle"].points:
            if not pt.content:
                continue
            end_ms  = pt.time_ms + pt.duration_ms
            end_pt  = SyncPoint(time_ms=end_ms, type="end", content="")
            lines.append(f"{idx}")
            lines.append(f"{pt.to_srt_time()} --> {end_pt.to_srt_time()}")
            lines.append(pt.content)
            lines.append("")
            idx += 1
        return "\n".join(lines)

    def to_dict(self) -> dict:
        return {
            "title":          self.title,
            "total_duration_ms": self.total_duration_ms,
            "tracks": {
                name: [{"time_ms":p.time_ms,"type":p.type,"content":p.content[:80]}
                        for p in track.points[:20]]
                for name, track in self.tracks.items()
            },
        }


class SyncEngine:
    """Construit la timeline depuis le storyboard et les assets produits."""

    def __init__(self, logger: logging.Logger = None):
        self.log = logger or log
        SYNC_DIR.mkdir(parents=True, exist_ok=True)

    def build_from_shotlist(self, shotlist: dict,
                             dialogue_map: dict = None) -> Timeline:
        title    = shotlist.get("project_title", "Ov3rLoRd")
        timeline = Timeline(title)
        cursor   = 0.0

        for shot in shotlist.get("shots", []):
            shot_id      = shot.get("shot_id","")
            duration_ms  = shot.get("duration_seconds", 3) * 1000

            timeline.add_shot(shot_id, cursor, duration_ms)

            # Dialogue si disponible
            dialogue = (dialogue_map or {}).get(shot_id,"")
            if dialogue:
                timeline.add_dialogue(dialogue, cursor + 200,
                                      duration_ms - 400, shot_id)

            cursor += duration_ms

        self.log.info(
            f"[SYNC] Timeline construite : {len(shotlist.get('shots',[]))} shots | "
            f"{cursor/1000:.1f}s total"
        )

        if BUS_OK:
            try:
                get_bus().write("sync.total_duration_s", round(cursor/1000, 1),
                                agent_id="synchronicity")
                get_bus().write("sync.shot_count",
                                len(shotlist.get("shots",[])), agent_id="synchronicity")
            except Exception:
                pass

        return timeline

    def enhance_with_llm(self, timeline: Timeline, mood: str = "") -> Timeline:
        """Utilise le LLM pour suggerer des points de synchronisation optimaux."""
        tl_summary = json.dumps(timeline.to_dict(), ensure_ascii=False)[:600]
        prompt = (
            f"Timeline de production (mood={mood}) :\n{tl_summary}\n\n"
            f"Suggere 3 points de synchronisation cles (music beats, transitions dramatiques).\n"
            f"JSON : [{{\"time_s\":0.0,\"type\":\"music_beat|vfx|chapter\","
            f"\"content\":\"description\"}}]"
        )
        raw = _llm(prompt, max_tokens=200)
        if raw and safe_json_parse:
            ok, data, _ = safe_json_parse(raw)
            if ok and isinstance(data, list):
                for pt in data:
                    timeline.add_music_beat(
                        pt.get("content",""),
                        pt.get("time_s", 0) * 1000
                    )
        return timeline

    def export(self, timeline: Timeline, output_dir: Path = None) -> dict:
        out     = output_dir or SYNC_DIR
        out.mkdir(parents=True, exist_ok=True)
        ts      = datetime.now(tz=timezone.utc).strftime("%Y%m%d_%H%M%S")
        results = {}

        srt_path = out / f"{ts}_subtitles.srt"
        srt_path.write_text(timeline.export_srt(), encoding="utf-8")
        results["srt"] = str(srt_path)

        meta_path = out / f"{ts}_timeline.json"
        meta_path.write_text(
            json.dumps(timeline.to_dict(), ensure_ascii=False, indent=2),
            encoding="utf-8"
        )
        results["timeline"] = str(meta_path)

        self.log.info(f"[SYNC] Export : {srt_path.name}")
        if BUS_OK:
            try:
                get_bus().write("sync.srt_path", str(srt_path), agent_id="synchronicity")
            except Exception:
                pass

        return results


if __name__ == "__main__":
    import sys, io
    if hasattr(sys.stdout, "buffer"):
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    logging.basicConfig(level=logging.INFO)
    fake_shotlist = {
        "project_title": "Dragon Ball Ov3rLoRd",
        "shots": [
            {"shot_id":"S01_SH001","duration_seconds":4,"emotion":"wonder"},
            {"shot_id":"S01_SH002","duration_seconds":3,"emotion":"tension"},
            {"shot_id":"S01_SH003","duration_seconds":5,"emotion":"catharsis"},
        ]
    }
    engine   = SyncEngine()
    timeline = engine.build_from_shotlist(fake_shotlist,
                                           dialogue_map={"S01_SH001":"Goku contemple l'horizon."})
    results  = engine.export(timeline)
    print(f"SRT : {results.get('srt')}")
    print(f"Duree : {timeline.total_duration_ms/1000:.1f}s")
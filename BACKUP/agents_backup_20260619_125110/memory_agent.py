"""
agents/memory_agent.py — Agent Mémoire & Archiviste OverLord
Archive continue de l'évolution du projet, des logs, décisions et apprentissages.

Fonctionnalités :
  - Ingestion automatique de tous les logs du pipeline
  - Indexation sémantique (ChromaDB) pour recherche intelligente
  - Timeline du projet (qui a fait quoi, quand, pourquoi)
  - Résumés de session générés par LLM
  - Réponse aux questions sur l'historique : "qu'est-il arrivé hier ?"
  - Connexion aux logs de tous les agents (SAV, learning, OBS...)
  - Mise à jour continue en tâche de fond

pip install chromadb sentence-transformers watchdog
"""

import json
import logging
import threading
import time
import hashlib
from pathlib import Path
from datetime import datetime, timedelta
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional
import requests

MEMORY_DIR   = Path("workspace/memory")
LOGS_DIR     = Path("workspace/logs")
ARCHIVE_DIR  = Path("workspace/archive")
TIMELINE_FILE = MEMORY_DIR / "timeline.json"
SUMMARIES_FILE = MEMORY_DIR / "session_summaries.json"
ANTHROPIC_URL  = "https://api.anthropic.com/v1/messages"
CLAUDE_MODEL   = "claude-sonnet-4-6"


class EntryType(Enum):
    LOG_LINE    = "log_line"
    DECISION    = "decision"
    BUG_FIX     = "bug_fix"
    MILESTONE   = "milestone"
    FILE_CHANGE = "file_change"
    SESSION     = "session"
    LESSON      = "lesson"
    ERROR       = "error"


@dataclass
class MemoryEntry:
    id:         str
    type:       EntryType
    timestamp:  str
    source:     str          # agent source (sav, maestro, learning...)
    content:    str          # contenu brut
    summary:    str = ""     # résumé LLM si long
    tags:       list = field(default_factory=list)
    importance: int  = 5     # 1-10


class MemoryDB:
    """Base de données mémoire avec ChromaDB ou JSON fallback."""

    def __init__(self, memory_dir: Path = MEMORY_DIR):
        self.dir = memory_dir
        self.dir.mkdir(parents=True, exist_ok=True)
        self._entries: list[MemoryEntry] = []
        self._use_chroma = False
        self._raw_file   = memory_dir / "entries.json"

        try:
            import chromadb
            from sentence_transformers import SentenceTransformer
            self._chroma  = chromadb.PersistentClient(path=str(memory_dir / "chroma"))
            self._col     = self._chroma.get_or_create_collection("memories")
            self._encoder = SentenceTransformer("all-MiniLM-L6-v2")
            self._use_chroma = True
        except ImportError:
            pass

        self._load()

    def add(self, entry: MemoryEntry):
        self._entries.append(entry)
        if self._use_chroma:
            try:
                emb = self._encoder.encode(entry.content[:500]).tolist()
                self._col.upsert(
                    ids=[entry.id],
                    embeddings=[emb],
                    documents=[entry.content[:500]],
                    metadatas=[{
                        "type":      entry.type.value,
                        "source":    entry.source,
                        "timestamp": entry.timestamp,
                        "importance": entry.importance,
                    }]
                )
            except Exception:
                pass
        if len(self._entries) % 50 == 0:
            self._save()

    def search(self, query: str, n: int = 10,
               entry_type: EntryType = None) -> list[MemoryEntry]:
        """Recherche sémantique dans la mémoire."""
        if self._use_chroma and query:
            try:
                emb = self._encoder.encode(query).tolist()
                where = {"type": entry_type.value} if entry_type else None
                results = self._col.query(
                    query_embeddings=[emb],
                    n_results=min(n, max(1, len(self._entries))),
                    where=where,
                )
                ids = results.get("ids", [[]])[0]
                return [e for e in self._entries if e.id in ids]
            except Exception:
                pass
        # Fallback : recherche textuelle simple
        q = query.lower()
        matches = [e for e in self._entries if q in e.content.lower()]
        return sorted(matches, key=lambda e: e.importance, reverse=True)[:n]

    def get_recent(self, hours: int = 24, n: int = 50) -> list[MemoryEntry]:
        """Entrées récentes."""
        cutoff = (datetime.utcnow() - timedelta(hours=hours)).isoformat()
        recent = [e for e in self._entries if e.timestamp >= cutoff]
        return sorted(recent, key=lambda e: e.timestamp, reverse=True)[:n]

    def get_by_source(self, source: str, n: int = 20) -> list[MemoryEntry]:
        entries = [e for e in self._entries if e.source == source]
        return sorted(entries, key=lambda e: e.timestamp, reverse=True)[:n]

    def get_milestones(self) -> list[MemoryEntry]:
        return [e for e in self._entries
                if e.type == EntryType.MILESTONE]

    def stats(self) -> dict:
        by_type = {}
        for e in self._entries:
            by_type[e.type.value] = by_type.get(e.type.value, 0) + 1
        return {
            "total":       len(self._entries),
            "by_type":     by_type,
            "oldest":      min((e.timestamp for e in self._entries), default=""),
            "newest":      max((e.timestamp for e in self._entries), default=""),
            "chroma_active": self._use_chroma,
        }

    def _save(self):
        try:
            self._raw_file.write_text(
                json.dumps([{
                    "id":       e.id, "type": e.type.value,
                    "timestamp":e.timestamp, "source": e.source,
                    "content":  e.content[:1000], "summary": e.summary,
                    "tags":     e.tags, "importance": e.importance,
                } for e in self._entries[-2000:]],  # garder les 2000 dernières
                           indent=2, ensure_ascii=False),
                encoding="utf-8"
            )
        except Exception:
            pass

    def _load(self):
        if self._raw_file.exists():
            try:
                data = json.loads(self._raw_file.read_text(encoding="utf-8"))
                self._entries = [
                    MemoryEntry(
                        id=d["id"], type=EntryType(d["type"]),
                        timestamp=d["timestamp"], source=d["source"],
                        content=d["content"], summary=d.get("summary",""),
                        tags=d.get("tags",[]), importance=d.get("importance",5),
                    ) for d in data
                ]
            except Exception:
                self._entries = []


class MemoryAgent:
    """
    Agent Mémoire — Archive vivante du projet OverLord.
    Tourne en tâche de fond, ingère tous les logs, répond aux questions.
    """

    def __init__(self, logger: logging.Logger = None):
        self.log  = logger or logging.getLogger("memory")
        self.db   = MemoryDB()
        self._watched_logs: dict[str, int] = {}  # path → dernier offset lu
        self._running       = False
        self._watch_thread  = None
        self._timeline      = self._load_timeline()
        MEMORY_DIR.mkdir(parents=True, exist_ok=True)
        self.log.info(
            f"[MEMORY] Agent initialisé — "
            f"{self.db.stats()['total']} entrées en mémoire"
        )

    # ── Ingestion ─────────────────────────────────────────────────────

    def ingest_log_line(self, line: str, source: str = "pipeline",
                         importance: int = 3) -> MemoryEntry:
        """Ingère une ligne de log."""
        line = line.strip()
        if not line:
            return None

        # Détecter l'importance automatiquement
        ll = line.lower()
        if any(w in ll for w in ["error","erreur","critical","fatal"]):
            importance = 9
            etype = EntryType.ERROR
        elif any(w in ll for w in ["bug","fix","corrig"]):
            importance = 8
            etype = EntryType.BUG_FIX
        elif any(w in ll for w in ["✓","terminé","success","alpha","beta","milestone"]):
            importance = 7
            etype = EntryType.MILESTONE
        elif any(w in ll for w in ["décision","choix","on va","on fait"]):
            importance = 7
            etype = EntryType.DECISION
        elif any(w in ll for w in ["appris","leçon","découvert"]):
            importance = 6
            etype = EntryType.LESSON
        else:
            etype = EntryType.LOG_LINE

        entry_id = hashlib.md5(
            f"{source}{line}{datetime.utcnow().isoformat()}".encode()
        ).hexdigest()[:16]

        entry = MemoryEntry(
            id=entry_id, type=etype,
            timestamp=datetime.utcnow().isoformat(),
            source=source, content=line,
            importance=importance,
        )
        self.db.add(entry)
        return entry

    def record_decision(self, decision: str, context: str = "",
                         source: str = "human") -> MemoryEntry:
        """Enregistre une décision importante."""
        content = f"DÉCISION: {decision}"
        if context:
            content += f"\nCONTEXTE: {context}"
        entry = MemoryEntry(
            id=hashlib.md5(content.encode()).hexdigest()[:16],
            type=EntryType.DECISION,
            timestamp=datetime.utcnow().isoformat(),
            source=source, content=content,
            importance=8,
            tags=["decision", "important"],
        )
        self.db.add(entry)
        self._add_timeline_event("decision", decision, source)
        self.log.info(f"[MEMORY] Décision archivée : {decision[:80]}")
        return entry

    def record_milestone(self, title: str, description: str = "") -> MemoryEntry:
        """Enregistre un jalon du projet."""
        content = f"MILESTONE: {title}\n{description}"
        entry = MemoryEntry(
            id=hashlib.md5(f"milestone{title}".encode()).hexdigest()[:16],
            type=EntryType.MILESTONE,
            timestamp=datetime.utcnow().isoformat(),
            source="system", content=content,
            importance=10,
            tags=["milestone"],
        )
        self.db.add(entry)
        self._add_timeline_event("milestone", title, "system")
        self.log.info(f"[MEMORY] Milestone : {title}")
        return entry

    # ── Surveillance des fichiers de log ─────────────────────────────

    def watch_log_file(self, log_path: str, source: str):
        """Ajoute un fichier log à surveiller."""
        self._watched_logs[log_path] = 0
        self.log.info(f"[MEMORY] Surveillance : {log_path}")

    def watch_all_pipeline_logs(self):
        """Surveille automatiquement tous les logs du pipeline."""
        log_sources = [
            (LOGS_DIR / "*.log",      "pipeline"),
            (LOGS_DIR / "*.txt",      "pipeline"),
            (Path("workspace/learning/"),  "learning"),
            (Path("workspace/obs_recordings/"), "obs"),
        ]
        for pattern, source in log_sources:
            parent = Path(str(pattern).replace("/*","").replace("/*.log","").replace("/*.txt",""))
            if parent.is_dir():
                for f in parent.glob("*.log"):
                    self.watch_log_file(str(f), source)

    def _poll_logs(self):
        """Lit les nouveaux logs depuis les fichiers surveillés."""
        for log_path, offset in list(self._watched_logs.items()):
            p = Path(log_path)
            if not p.exists():
                continue
            try:
                with open(p, encoding="utf-8", errors="replace") as f:
                    f.seek(offset)
                    new_content = f.read()
                    new_offset  = f.tell()
                if new_content:
                    for line in new_content.split("\n"):
                        if line.strip():
                            self.ingest_log_line(line,
                                source=p.stem.split("_")[0])
                    self._watched_logs[log_path] = new_offset
            except Exception:
                pass

    # ── Surveillance des fichiers du projet ──────────────────────────

    def watch_project_files(self, project_dir: str):
        """Surveille les modifications de fichiers Python du projet."""
        try:
            from watchdog.observers import Observer
            from watchdog.events import FileSystemEventHandler

            class _Handler(FileSystemEventHandler):
                def __init__(self_, agent):
                    self_.agent = agent
                def on_modified(self_, event):
                    if event.src_path.endswith(".py"):
                        fname = Path(event.src_path).name
                        self_.agent.ingest_log_line(
                            f"FICHIER MODIFIÉ: {fname}",
                            source="filesystem", importance=4
                        )
                def on_created(self_, event):
                    if event.src_path.endswith(".py"):
                        fname = Path(event.src_path).name
                        self_.agent.ingest_log_line(
                            f"NOUVEAU FICHIER: {fname}",
                            source="filesystem", importance=6
                        )

            observer = Observer()
            observer.schedule(_Handler(self), project_dir, recursive=True)
            observer.start()
            self.log.info(f"[MEMORY] Surveillance fichiers : {project_dir}")
        except ImportError:
            self.log.info("[MEMORY] pip install watchdog pour surveillance fichiers")

    # ── Boucle de fond ───────────────────────────────────────────────

    def start(self, project_dir: str = None):
        """Démarre la surveillance en tâche de fond."""
        self._running = True
        self.watch_all_pipeline_logs()
        if project_dir:
            self.watch_project_files(project_dir)
        self._watch_thread = threading.Thread(
            target=self._background_loop, daemon=True
        )
        self._watch_thread.start()
        self.log.info("[MEMORY] Agent démarré en tâche de fond ✓")

    def stop(self):
        self._running = False
        self.db._save()
        self.log.info("[MEMORY] Agent arrêté — mémoire sauvegardée")

    def _background_loop(self):
        """Boucle principale : poll logs + sauvegarde périodique."""
        save_counter = 0
        while self._running:
            self._poll_logs()
            save_counter += 1
            if save_counter >= 60:   # sauvegarde toutes les ~5 min
                self.db._save()
                self._save_timeline()
                save_counter = 0
            time.sleep(5)

    # ── Requêtes & Résumés ───────────────────────────────────────────

    def ask(self, question: str) -> str:
        """
        Répond à une question sur l'historique du projet.
        Utilise la recherche sémantique + LLM.
        """
        relevant = self.db.search(question, n=15)
        recent   = self.db.get_recent(hours=24, n=10)
        milestones = self.db.get_milestones()[-5:]

        context_parts = [
            "=== ENTRÉES PERTINENTES ===",
            *[f"[{e.source}] {e.timestamp[:16]} | {e.content[:200]}"
              for e in relevant],
            "\n=== RÉCENT (24h) ===",
            *[f"[{e.source}] {e.timestamp[:16]} | {e.content[:150]}"
              for e in recent[:5]],
            "\n=== JALONS DU PROJET ===",
            *[f"[{e.timestamp[:10]}] {e.content[:100]}" for e in milestones],
        ]
        context = "\n".join(context_parts)

        try:
            resp = requests.post(
                ANTHROPIC_URL,
                headers={
                "Content-Type": "application/json",
                "x-api-key": _get_api_key(),
                "anthropic-version": "2023-06-01",
            },
                json={
                    "model": CLAUDE_MODEL, "max_tokens": 600,
                    "system": (
                        "Tu es le Memory Archivist d'OverLord Pipeline. "
                        "Tu as accès à l'historique complet du projet. "
                        "Tu réponds aux questions sur ce qui s'est passé de façon "
                        "précise, chronologique et avec des références aux sources. "
                        "Tu parles à la première personne ('J'ai enregistré...')."
                    ),
                    "messages": [{
                        "role": "user",
                        "content": f"Question : {question}\n\nContexte mémoire :\n{context}"
                    }]
                },
                timeout=30
            )
            if resp.status_code == 200:
                return resp.json()["content"][0]["text"].strip()
        except Exception as e:
            self.log.warning(f"[MEMORY/Ask] LLM : {e}")

        # Fallback texte simple
        if relevant:
            lines = [f"• [{e.source}] {e.content[:150]}" for e in relevant[:5]]
            return "Entrées pertinentes trouvées :\n" + "\n".join(lines)
        return "Aucune entrée correspondante trouvée en mémoire."

    def generate_session_summary(self) -> str:
        """Génère un résumé de la session actuelle."""
        recent = self.db.get_recent(hours=8, n=30)
        if not recent:
            return "Aucune activité enregistrée dans les dernières 8 heures."

        entries_text = "\n".join(
            f"[{e.source}] {e.content[:200]}" for e in recent
        )
        try:
            resp = requests.post(
                ANTHROPIC_URL,
                headers={
                "Content-Type": "application/json",
                "x-api-key": _get_api_key(),
                "anthropic-version": "2023-06-01",
            },
                json={
                    "model": CLAUDE_MODEL, "max_tokens": 500,
                    "system": (
                        "Tu es le Memory Archivist. Génère un résumé concis "
                        "de la session de travail à partir des logs fournis. "
                        "Format : date, nb actions, principales réalisations, "
                        "bugs rencontrés, décisions prises."
                    ),
                    "messages": [{
                        "role": "user",
                        "content": f"Logs de la session :\n{entries_text}"
                    }]
                },
                timeout=30
            )
            if resp.status_code == 200:
                summary = resp.json()["content"][0]["text"].strip()
                # Sauvegarder le résumé
                self._save_session_summary(summary)
                return summary
        except Exception as e:
            self.log.warning(f"[MEMORY/Summary] {e}")

        return f"Session de {len(recent)} événements enregistrés."

    def get_project_timeline(self) -> list[dict]:
        """Retourne la timeline complète du projet."""
        return sorted(self._timeline, key=lambda e: e.get("timestamp",""))

    # ── Timeline ─────────────────────────────────────────────────────

    def _add_timeline_event(self, etype: str, content: str, source: str):
        self._timeline.append({
            "timestamp": datetime.utcnow().isoformat(),
            "type":      etype,
            "content":   content,
            "source":    source,
        })
        if len(self._timeline) % 10 == 0:
            self._save_timeline()

    def _load_timeline(self) -> list:
        if TIMELINE_FILE.exists():
            try:
                return json.loads(TIMELINE_FILE.read_text(encoding="utf-8"))
            except Exception:
                pass
        return []

    def _save_timeline(self):
        TIMELINE_FILE.write_text(
            json.dumps(self._timeline, indent=2, ensure_ascii=False),
            encoding="utf-8"
        )

    def _save_session_summary(self, summary: str):
        summaries = []
        if SUMMARIES_FILE.exists():
            try:
                summaries = json.loads(SUMMARIES_FILE.read_text(encoding="utf-8"))
            except Exception:
                pass
        summaries.append({
            "timestamp": datetime.utcnow().isoformat(),
            "summary":   summary,
        })
        SUMMARIES_FILE.write_text(
            json.dumps(summaries[-50:], indent=2, ensure_ascii=False),
            encoding="utf-8"
        )


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    log = logging.getLogger("memory_test")
    agent = MemoryAgent(log)

    # Test
    agent.record_milestone("Alpha v1.0.0", "Pipeline complet 26 fichiers")
    agent.record_decision("Utiliser Ray pour le cluster", "Plus simple que Celery")
    agent.ingest_log_line("[maestro] ✓ Pipeline terminé en 142s", "maestro", 7)
    agent.ingest_log_line("[ERROR] VRAM OOM sur nœud GPU-1", "gpu_scheduler", 9)

    stats = agent.db.stats()
    log.info(f"Mémoire : {stats}")

    q = "Quelles erreurs ont été rencontrées ?"
    log.info(f"\nQuestion : {q}")
    log.info(f"Réponse  : {agent.ask(q)}")

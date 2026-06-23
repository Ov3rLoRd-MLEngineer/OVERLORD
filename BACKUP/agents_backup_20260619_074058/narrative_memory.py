"""
agents/narrative_memory.py — Memoire Narrative Persistante V1.44 + Context Bus V1.49
Graphe de continuite entre episodes. Publie le contexte narratif sur le bus.
FIX V1.49 : emojis remplaces par ASCII, context_bus connecte.
"""

import json
import logging
import hashlib
from pathlib import Path
from datetime import datetime
from typing import Optional

try:
    import colorama; colorama.init()
    C_GREEN  = "\033[92m"; C_YELLOW = "\033[93m"; C_RED    = "\033[91m"
    C_CYAN   = "\033[96m"; C_BLUE   = "\033[94m"; C_MAGENTA= "\033[95m"
    C_BOLD   = "\033[1m";  C_DIM    = "\033[2m";  C_RESET  = "\033[0m"
except ImportError:
    C_GREEN=C_YELLOW=C_RED=C_CYAN=C_BLUE=C_MAGENTA=C_BOLD=C_DIM=C_RESET=""

try:
    import networkx as nx
    NX_OK = True
except ImportError:
    NX_OK = False

try:
    import chromadb
    CHROMA_OK = True
except ImportError:
    CHROMA_OK = False

try:
    from agents.context_bus import get_bus
    BUS_OK = True
except ImportError:
    BUS_OK = False

log = logging.getLogger("narrative_memory")
MEMORY_DIR = Path("workspace/narrative")


class NarrativeMemory:

    def __init__(self, series_name: str, logger: logging.Logger = None):
        self.log          = logger or log
        self.series       = series_name
        self._world_model = None
        try:
            from agents.v130_world_model import get_world
            self._world_model = get_world(series_name)
            self.log.info("[NARRATIVE] WorldModel V1.30 connecte")
        except Exception:
            pass

        self.series_id   = hashlib.md5(series_name.encode()).hexdigest()[:8]
        self.memory_path = MEMORY_DIR / self.series_id
        self.memory_path.mkdir(parents=True, exist_ok=True)
        self.graph_file  = self.memory_path / "graph.json"

        if NX_OK:
            self.G = nx.DiGraph()
            self._load_graph()
        else:
            self.G = None
            self.log.warning("[NARRATIVE] networkx non installe — pip install networkx")

        self._json_store = self._load_json_store()

        self._chroma = None
        if CHROMA_OK:
            try:
                client       = chromadb.PersistentClient(path=str(self.memory_path / "chroma"))
                self._chroma = client.get_or_create_collection(f"narrative_{self.series_id}")
            except Exception as e:
                self.log.warning(f"[NARRATIVE] ChromaDB indisponible : {e}")

        self.log.info(f"[NARRATIVE] Serie '{series_name}' — {self._node_count()} noeuds charges")

    def _load_graph(self):
        if not self.graph_file.exists():
            return
        try:
            data = json.loads(self.graph_file.read_text(encoding="utf-8"))
            if NX_OK:
                self.G = nx.node_link_graph(data)
        except Exception as e:
            self.log.warning(f"[NARRATIVE] Erreur chargement graphe : {e}")

    def _save_graph(self):
        try:
            if NX_OK and self.G:
                data = nx.node_link_data(self.G)
                self.graph_file.write_text(
                    json.dumps(data, ensure_ascii=False, indent=2, default=str),
                    encoding="utf-8"
                )
        except Exception as e:
            self.log.warning(f"[NARRATIVE] Erreur sauvegarde graphe : {e}")
        self._save_json_store()

    def _load_json_store(self) -> dict:
        path = self.memory_path / "store.json"
        if path.exists():
            try:
                return json.loads(path.read_text(encoding="utf-8"))
            except Exception:
                pass
        return {"characters": {}, "locations": {}, "events": {}, "relations": []}

    def _save_json_store(self):
        path = self.memory_path / "store.json"
        path.write_text(
            json.dumps(self._json_store, ensure_ascii=False, indent=2, default=str),
            encoding="utf-8"
        )

    def _node_count(self) -> int:
        if NX_OK and self.G:
            return self.G.number_of_nodes()
        return sum(len(v) for v in self._json_store.values() if isinstance(v, dict))

    def add_character(self, name: str, attrs: dict = None):
        attrs = attrs or {}
        attrs.update({"type":"character","name":name,"updated_at":datetime.now().isoformat()})
        if NX_OK and self.G is not None:
            self.G.add_node(f"char_{name}", **attrs)
        self._json_store["characters"][name] = attrs
        self._save_graph()
        self.log.debug(f"[NARRATIVE] Personnage : {name} | status={attrs.get('status','?')}")
        self._publish_summary()

    def add_location(self, name: str, attrs: dict = None):
        attrs = attrs or {}
        attrs.update({"type":"location","name":name})
        if NX_OK and self.G is not None:
            self.G.add_node(f"loc_{name}", **attrs)
        self._json_store["locations"][name] = attrs
        self._save_graph()

    def add_event(self, episode: str, description: str,
                  characters: list = None, location: str = None,
                  consequences: list = None, attrs: dict = None):
        event_id = f"ev_{episode}_{hashlib.md5(description.encode()).hexdigest()[:6]}"
        ev_attrs = {
            "type":         "event",
            "episode":      episode,
            "description":  description,
            "characters":   characters or [],
            "location":     location or "",
            "consequences": consequences or [],
            "timestamp":    datetime.now().isoformat(),
            **(attrs or {}),
        }

        if NX_OK and self.G is not None:
            self.G.add_node(event_id, **ev_attrs)
            for char in (characters or []):
                char_node = f"char_{char}"
                if char_node not in self.G:
                    self.G.add_node(char_node, type="character", name=char)
                self.G.add_edge(char_node, event_id, relation="apparait_dans")
            if location:
                loc_node = f"loc_{location}"
                if loc_node not in self.G:
                    self.G.add_node(loc_node, type="location", name=location)
                self.G.add_edge(event_id, loc_node, relation="se_passe_a")

        self._json_store["events"][event_id] = ev_attrs
        self._save_graph()

        if self._chroma:
            try:
                self._chroma.add(
                    documents=[description],
                    metadatas=[{"episode": episode, "characters": str(characters)}],
                    ids=[event_id],
                )
            except Exception:
                pass

        self.log.info(f"[NARRATIVE] Evenement ep{episode} : {description[:60]}")
        return event_id

    def add_relation(self, char1: str, char2: str, relation_type: str, episode: str = ""):
        if NX_OK and self.G is not None:
            self.G.add_edge(f"char_{char1}", f"char_{char2}",
                            relation=relation_type, since_episode=episode)
        self._json_store["relations"].append(
            {"from":char1,"to":char2,"type":relation_type,"episode":episode}
        )
        self._save_graph()

    def kill_character(self, name: str, episode: str, killer: str = ""):
        # FIX : emoji ☠ remplace par ASCII
        if name in self._json_store["characters"]:
            self._json_store["characters"][name]["status"]    = "mort"
            self._json_store["characters"][name]["died_in"]   = episode
            self._json_store["characters"][name]["killed_by"] = killer
        if NX_OK and self.G is not None:
            node = f"char_{name}"
            if node in self.G:
                self.G.nodes[node]["status"]  = "mort"
                self.G.nodes[node]["died_in"] = episode
        self._save_graph()
        self.log.info(f"[NARRATIVE] [MORT] {name} mort en ep{episode}"
                      + (f" (par {killer})" if killer else ""))
        self._publish_summary()

    def get_scene_context(self, episode: str, characters: list = None,
                          location: str = None) -> dict:
        context = {
            "series":    self.series, "episode": episode,
            "warnings":  [],
            "characters_context": {}, "location_context": {},
            "recent_events": [], "active_relations": [],
        }

        for char in (characters or []):
            char_data = self._json_store["characters"].get(char, {})
            if char_data.get("status") == "mort":
                # FIX : emoji ⚠ remplace par [ALERTE]
                context["warnings"].append(
                    f"[ALERTE CONTINUITE] {char} est mort en ep{char_data.get('died_in','?')} "
                    f"— ne peut pas apparaitre !"
                )
            context["characters_context"][char] = char_data

        if location:
            context["location_context"] = self._json_store["locations"].get(location, {})

        events = list(self._json_store["events"].values())
        events.sort(key=lambda e: e.get("timestamp",""), reverse=True)
        context["recent_events"] = events[:5]

        for rel in self._json_store["relations"]:
            if rel["from"] in (characters or []) or rel["to"] in (characters or []):
                context["active_relations"].append(rel)

        if self._chroma and characters:
            try:
                query   = f"episode {episode} {' '.join(characters or [])}"
                results = self._chroma.query(query_texts=[query], n_results=3)
                if results["documents"]:
                    context["semantic_context"] = results["documents"][0]
            except Exception:
                pass

        for w in context["warnings"]:
            self.log.warning(f"[NARRATIVE] {w}")

        if self._world_model:
            try:
                world_ctx = self._world_model.get_context_for_run()
                context["world_model"] = world_ctx
                for char in (characters or []):
                    test_prompt = f"{char} appears in scene"
                    validated = self._world_model.validate_and_fix_prompt(test_prompt)
                    if validated.get("fixed"):
                        context["warnings"].append(
                            f"[WORLD] Continuite : {validated.get('fixes_applied','')}"
                        )
            except Exception:
                pass

        # Publier le contexte sur le bus
        if BUS_OK:
            try:
                bus = get_bus()
                bus.write("narrative.episode",   episode,               agent_id="narrative")
                bus.write("narrative.warnings",  context["warnings"],   agent_id="narrative")
                bus.write("narrative.characters",
                          list(context["characters_context"].keys()),   agent_id="narrative")
            except Exception:
                pass

        return context

    def _publish_summary(self):
        """Publie le resume de la memoire sur le bus."""
        if not BUS_OK:
            return
        try:
            s   = self.summary()
            bus = get_bus()
            bus.write("narrative.characters_count", s["characters"], agent_id="narrative")
            bus.write("narrative.events_count",     s["events"],     agent_id="narrative")
        except Exception:
            pass

    def get_character_arc(self, name: str) -> dict:
        char_data   = self._json_store["characters"].get(name, {})
        appearances = [ev for ev in self._json_store["events"].values()
                       if name in ev.get("characters",[])]
        appearances.sort(key=lambda e: e.get("episode",""))
        return {
            "character":   name,
            "data":        char_data,
            "appearances": appearances,
            "relations":   [r for r in self._json_store["relations"]
                            if r["from"] == name or r["to"] == name],
        }

    def export_for_llm(self) -> str:
        # FIX : box-drawing === remplace par ASCII ===
        lines = [f"=== MEMOIRE NARRATIVE : {self.series} ==="]
        alive = {k:v for k,v in self._json_store["characters"].items()
                 if v.get("status") != "mort"}
        dead  = {k:v for k,v in self._json_store["characters"].items()
                 if v.get("status") == "mort"}

        if alive:
            lines.append(f"Personnages actifs ({len(alive)}) : {', '.join(alive.keys())}")
        if dead:
            lines.append(f"Morts (NE PAS FAIRE REAPPARAITRE) : {', '.join(dead.keys())}")

        rels = self._json_store["relations"][:5]
        if rels:
            lines.append("Relations : " + " | ".join(
                f"{r['from']} {r['type']} {r['to']}" for r in rels
            ))

        events = sorted(self._json_store["events"].values(),
                        key=lambda e: e.get("timestamp",""), reverse=True)[:3]
        if events:
            lines.append("Evenements recents :")
            for ev in events:
                lines.append(f"  ep{ev.get('episode','?')} : {ev.get('description','')[:80]}")

        return "\n".join(lines)

    def summary(self) -> dict:
        return {
            "series":     self.series,
            "characters": len(self._json_store["characters"]),
            "locations":  len(self._json_store["locations"]),
            "events":     len(self._json_store["events"]),
            "relations":  len(self._json_store["relations"]),
            "nx_nodes":   self.G.number_of_nodes() if NX_OK and self.G else 0,
            "nx_edges":   self.G.number_of_edges() if NX_OK and self.G else 0,
        }


def enrich_prompt_with_memory(prompt: str, series_name: str,
                               episode: str, characters: list = None) -> str:
    try:
        mem     = NarrativeMemory(series_name)
        context = mem.export_for_llm()
        if context.strip():
            return f"{context}\n\nRESPECTE ABSOLUMENT la continuite ci-dessus.\n\n{prompt}"
    except Exception as e:
        log.warning(f"[NARRATIVE] Enrichissement prompt echoue : {e}")
    return prompt


if __name__ == "__main__":
    import sys, io
    if hasattr(sys.stdout,'buffer'):
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
    logging.basicConfig(level=logging.INFO)
    mem = NarrativeMemory("Dragon Ball Ov3rLoRd")
    mem.add_character("Goku",  {"status":"vivant","pouvoir":"Ultra Instinct"})
    mem.add_character("Broly", {"status":"vivant","pouvoir":"Super Saiyan Legendaire"})
    mem.add_character("Raditz",{"status":"mort"})
    mem.add_location("Plaine Desertique", {"ambiance":"post-apocalyptique"})
    mem.add_event("1","Goku affronte Broly",characters=["Goku","Broly"],location="Plaine Desertique")
    mem.add_relation("Goku","Broly","rival",episode="1")
    print(mem.export_for_llm())
    print("\nSummary :", json.dumps(mem.summary(), indent=2))
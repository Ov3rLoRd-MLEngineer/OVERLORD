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
agents/narrative_memory.py — Mémoire Narrative Inter-Épisodes V1.70
Maintient la cohérence des personnages, lieux et événements
entre les différents runs/épisodes du pipeline Ov3rLoRd.

Stockage : workspace/narrative/memory.json (persistant entre runs)
Intégration : injecté dans scenario.py pour contexte de suite logique.

Fonctionnalités :
- Registre des personnages vus (nom, description, LoRa associée)
- Timeline des événements par univers
- Continuité narrative (épisode N connaît les épisodes précédents)
- Extraction automatique depuis les scripts générés
"""

import json
import logging
import re
from datetime import datetime
from pathlib import Path

try:
    from agents.context_bus import get_bus
    BUS_OK = True
except ImportError:
    BUS_OK = False

MEMORY_DIR  = Path("workspace/narrative")
MEMORY_FILE = MEMORY_DIR / "memory.json"

LORA_CHARACTER_MAP = {
    "asuka":  "asuka-langley-soryuu-classic-ponyxl-lora-nochekaiser.safetensors",
    "asuka langley": "asuka-langley-soryuu-classic-ponyxl-lora-nochekaiser.safetensors",
    "rei":    "rei-ayanami-classic-ponyxl-lora-nochekaiser.safetensors",
    "rei ayanami": "rei-ayanami-classic-ponyxl-lora-nochekaiser.safetensors",
    "mari":   "mari-makinami-rebuild-ponyxl-lora-nochekaiser.safetensors",
    "mari makinami": "mari-makinami-rebuild-ponyxl-lora-nochekaiser.safetensors",
}


class NarrativeMemory:

    def __init__(self):
        MEMORY_DIR.mkdir(parents=True, exist_ok=True)
        self._data = self._load()

    def _load(self) -> dict:
        if MEMORY_FILE.exists():
            try:
                return json.loads(MEMORY_FILE.read_text(encoding="utf-8"))
            except Exception:
                pass
        return {
            "universes":  {},
            "characters": {},
            "events":     [],
            "episodes":   [],
            "last_update": None,
        }

    def _save(self):
        self._data["last_update"] = datetime.now().isoformat()
        MEMORY_FILE.write_text(
            json.dumps(self._data, indent=2, ensure_ascii=False),
            encoding="utf-8"
        )

    # ── Personnages ───────────────────────────────────────────────────

    def register_character(self, name: str, description: str = "",
                           lora: str = None, universe: str = ""):
        """Enregistre ou met à jour un personnage."""
        key = name.lower().strip()
        # Résolution LoRa automatique
        if not lora:
            for alias, lora_file in LORA_CHARACTER_MAP.items():
                if alias in key:
                    lora = lora_file
                    break

        if key not in self._data["characters"]:
            self._data["characters"][key] = {
                "name":        name,
                "description": description,
                "lora":        lora,
                "universe":    universe,
                "appearances": 0,
                "first_seen":  datetime.now().isoformat(),
            }
        else:
            char = self._data["characters"][key]
            if description and not char.get("description"):
                char["description"] = description
            if lora:
                char["lora"] = lora
        self._data["characters"][key]["appearances"] += 1
        self._save()

    def get_character(self, name: str) -> dict:
        return self._data["characters"].get(name.lower().strip(), {})

    def get_lora_for_character(self, name: str) -> str | None:
        char = self.get_character(name)
        return char.get("lora")

    def get_main_characters(self, universe: str = "", n: int = 5) -> list:
        """Retourne les N personnages les plus fréquents (par univers)."""
        chars = self._data["characters"].values()
        if universe:
            chars = [c for c in chars if universe.lower() in c.get("universe","").lower()]
        return sorted(chars, key=lambda c: c.get("appearances", 0), reverse=True)[:n]

    # ── Épisodes ──────────────────────────────────────────────────────

    def register_episode(self, run_id: str, script: dict, universe: str = ""):
        """Enregistre un épisode et extrait les données narratives."""
        episode = {
            "run_id":    run_id,
            "universe":  universe,
            "title":     script.get("title", "?"),
            "logline":   script.get("logline", ""),
            "genre":     script.get("genre", []),
            "synopsis":  script.get("synopsis", "")[:300],
            "timestamp": datetime.now().isoformat(),
        }
        self._data["episodes"].append(episode)

        # Extraire personnages du script
        chars = script.get("characters", [])
        for char in chars:
            name = char.get("name", "")
            desc = char.get("description", "")
            role = char.get("role", "")
            if name:
                self.register_character(
                    name=name,
                    description=f"{role}: {desc}" if role else desc,
                    universe=universe
                )

        # Extraire univers
        if universe and universe not in self._data["universes"]:
            self._data["universes"][universe] = {
                "first_seen": datetime.now().isoformat(),
                "episodes":   0,
            }
        if universe:
            self._data["universes"][universe]["episodes"] = self._data["universes"][universe].get("episodes", 0) + 1

        self._save()

    def get_previous_episodes(self, universe: str = "", n: int = 3) -> list:
        """Retourne les N épisodes précédents pour contexte narratif."""
        episodes = self._data["episodes"]
        if universe:
            episodes = [e for e in episodes if universe.lower() in e.get("universe","").lower()]
        return episodes[-n:] if episodes else []

    def get_continuation_context(self, universe: str = "") -> str:
        """
        Génère un contexte de continuation pour le LLM scénariste.
        Injecté dans le prompt du scénario pour assurer la cohérence.
        """
        prev = self.get_previous_episodes(universe, n=3)
        chars = self.get_main_characters(universe, n=5)

        if not prev and not chars:
            return ""

        lines = ["## Narrative Continuity Context\n"]

        if chars:
            lines.append("### Established Characters")
            for c in chars:
                lora_note = f" [LoRA: {c['lora'][:40]}...]" if c.get("lora") else ""
                lines.append(f"- **{c['name']}**: {c.get('description','')[:80]}{lora_note}")
            lines.append("")

        if prev:
            lines.append("### Previous Episodes (most recent first)")
            for ep in reversed(prev):
                lines.append(f"- **{ep['title']}**: {ep.get('logline','')[:100]}")
            lines.append("")

        lines.append("### Continuity Rules")
        lines.append("- Keep character personalities consistent with established profiles")
        lines.append("- Reference or build upon previous events if dramatically relevant")
        lines.append("- Maintain visual style consistency (same universe aesthetic)")
        lines.append("")

        return "\n".join(lines)

    # ── Extraction automatique ────────────────────────────────────────

    def extract_from_script(self, script: dict, run_id: str,
                            universe: str = "",
                            logger: logging.Logger = None):
        """Extrait et mémorise toutes les données narratives d'un script."""
        log = logger or logging.getLogger("narrative_memory")
        self.register_episode(run_id, script, universe)

        # Extraire personnages des actes aussi
        for act in script.get("acts", []):
            for scene in act.get("scenes", []):
                desc = scene.get("description", "")
                # Chercher des noms dans les descriptions
                for alias in LORA_CHARACTER_MAP:
                    if alias in desc.lower():
                        self.register_character(alias.title(), universe=universe)

        n_chars = len(self._data["characters"])
        n_eps   = len(self._data["episodes"])
        log.info(f"[MEMORY] Script mémorisé | {n_chars} personnages | {n_eps} épisodes")

        if BUS_OK:
            try:
                get_bus().write("memory.characters_count", n_chars, agent_id="narrative_memory")
                get_bus().write("memory.episodes_count",   n_eps,   agent_id="narrative_memory")
            except Exception:
                pass

    def status(self) -> dict:
        return {
            "characters": len(self._data["characters"]),
            "episodes":   len(self._data["episodes"]),
            "universes":  list(self._data["universes"].keys()),
            "last_update": self._data.get("last_update"),
        }


# Singleton
_memory: NarrativeMemory | None = None

def get_narrative_memory() -> NarrativeMemory:
    global _memory
    if _memory is None:
        _memory = NarrativeMemory()
    return _memory


if __name__ == "__main__":
    import sys, io
    if hasattr(sys.stdout, "buffer"):
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    logging.basicConfig(level=logging.INFO)

    mem = get_narrative_memory()
    print("=== Narrative Memory V1.70 ===")
    status = mem.status()
    for k, v in status.items():
        print(f"  {k}: {v}")

    # Simuler un épisode
    fake_script = {
        "title":     "Evangelion: The First Battle",
        "logline":   "Asuka pilots Unit-02 in a desperate last stand",
        "synopsis":  "Asuka faces the 14th Angel alone while Rei recovers.",
        "characters": [
            {"name": "Asuka Langley", "role": "protagonist", "description": "Fierce pilot of Unit-02"},
            {"name": "Rei Ayanami",   "role": "supporting",  "description": "Quiet first child"},
        ],
        "acts": [],
    }
    mem.extract_from_script(fake_script, run_id="test_001", universe="evangelion")
    ctx = mem.get_continuation_context("evangelion")
    print("\nContexte généré pour le prochain épisode :")
    print(ctx[:400])

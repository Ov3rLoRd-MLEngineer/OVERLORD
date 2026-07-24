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
agents/world_model.py -- World Model et ContinuityGuard Ov3rLoRd V1.30
FIX V1.49  : SyntaxError 'break outside loop' corrige.
FIX V1.49m : datetime.UTC non disponible -> timezone.utc, context_bus connecte.
FIX V1.49p : end_run() alias ajoute, validate_and_fix_prompt() retourne dict
             (director.py attend {fixed, fixed_prompt, violations}).
"""
import logging
import json
from pathlib import Path
from datetime import datetime, timezone

try:
    from agents.context_bus import get_bus
    BUS_OK = True
except ImportError:
    BUS_OK = False

log = logging.getLogger("world_model")


def _get_api_key() -> str:
    import os as _os
    key = _os.environ.get("ANTHROPIC_API_KEY", "")
    if not key:
        for env_path in [Path(__file__).parent.parent / ".env", Path(".env")]:
            if env_path.exists():
                for line in env_path.read_text(encoding="utf-8").splitlines():
                    if line.startswith("ANTHROPIC_API_KEY="):
                        key = line.split("=", 1)[1].strip().strip('"').strip("'")
                        break
            if key:
                break
    return key


class WorldModel:
    """Registre des entites + ContinuityGuard pour la coherence narrative."""

    def __init__(self, series_name: str = "default"):
        self.series_name    = series_name
        self.entities:      dict[str, dict] = {}
        self.locations:     dict[str, dict] = {}
        self.continuity_log:list[dict]      = []
        self._storage = Path(f"workspace/narrative/{series_name}_world.json")
        self._load()
        log.info(f"[WORLD] Modele charge -- {len(self.entities)} entites, "
                 f"{len(self.locations)} lieux.")

    def _load(self):
        if self._storage.exists():
            try:
                data = json.loads(self._storage.read_text(encoding="utf-8"))
                self.entities  = data.get("entities",  {})
                self.locations = data.get("locations", {})
            except Exception as e:
                log.warning(f"[WORLD] Impossible de charger le modele : {e}")

    def _save(self):
        try:
            self._storage.parent.mkdir(parents=True, exist_ok=True)
            self._storage.write_text(
                json.dumps({"entities":  self.entities,
                            "locations": self.locations},
                           ensure_ascii=False, indent=2),
                encoding="utf-8"
            )
        except Exception as e:
            log.warning(f"[WORLD] Sauvegarde echouee : {e}")

    def register_entity(self, name: str, entity_type: str,
                         attributes: dict = None):
        self.entities[name] = {
            "type":       entity_type,
            "attributes": attributes or {},
            "first_seen": datetime.now(tz=timezone.utc).isoformat(),
        }
        self._save()
        log.info(f"[WORLD] Entite enregistree : {name} ({entity_type})")
        if BUS_OK:
            try:
                bus = get_bus()
                bus.write("world.entity_count", len(self.entities), agent_id="world_model")
                bus.write("world.last_entity",  name,               agent_id="world_model")
            except Exception:
                pass

    def register_location(self, name: str, attributes: dict = None):
        self.locations[name] = {
            "attributes": attributes or {},
            "added_at":   datetime.now(tz=timezone.utc).isoformat(),
        }
        self._save()

    def validate_and_fix_prompt(self, prompt: str,
                                 character: str = None) -> dict:
        """
        FIX V1.49p : retourne maintenant un dict au lieu d'un tuple.
        director.py attend : {fixed:bool, fixed_prompt:str, violations:list}
        narrative_memory.py continuera de fonctionner via validate_and_fix_prompt()
        car il utilise .get("fixed") et .get("fixes_applied").
        """
        violations   = []
        fixed_prompt = prompt
        fixed        = False

        if character and character in self.entities:
            attrs = self.entities[character].get("attributes", {})
            color = attrs.get("hair_color")
            if color and color.lower() not in prompt.lower():
                fixed_prompt = f"{color} hair, {prompt}"
                violations.append(f"Couleur cheveux ajoutee pour {character} : {color}")
                fixed = True
            if attrs.get("status") == "mort":
                violations.append(
                    f"[ALERTE] {character} est mort -- ne peut pas apparaitre !"
                )

        if violations and BUS_OK:
            try:
                get_bus().write("world.continuity_warnings", violations,
                                agent_id="world_model")
            except Exception:
                pass

        return {
            "fixed":        fixed,
            "fixed_prompt": fixed_prompt,
            "prompt":       fixed_prompt,  # alias pour compatibilite
            "violations":   violations,
            "fixes_applied":"\n".join(violations),
        }

    def get_context_for_run(self) -> dict:
        """Resume compact pour injection dans les prompts LLM et director.py."""
        alive = [n for n, e in self.entities.items()
                 if e.get("attributes",{}).get("status","vivant") != "mort"]
        return {
            "series":        self.series_name,
            "entities":      list(self.entities.keys()),
            "alive":         alive,
            "locations":     list(self.locations.keys()),
            "entity_count":  len(self.entities),
            "location_count":len(self.locations),
            "run_id":        None,
        }

    def end_run(self, run_result: dict = None):
        """
        Alias no-op pour compatibilite director.py.
        Pourrait sauvegarder les resultats du run dans le futur.
        """
        run_result = run_result or {}
        log.info(f"[WORLD] Run termine -- "
                 f"health={run_result.get('pipeline_health','?')}")
        # Sauvegarder etat si necessaire
        self._save()

    def get_entity(self, name: str) -> dict:
        return self.entities.get(name, {})

    def list_entities(self) -> list[str]:
        return list(self.entities.keys())


_world_instances: dict[str, WorldModel] = {}


def get_world(series_name: str = "default") -> WorldModel:
    """Alias utilise par narrative_memory.py."""
    return get_world_model(series_name)


def get_world_model(series_name: str = "default") -> WorldModel:
    if series_name not in _world_instances:
        _world_instances[series_name] = WorldModel(series_name)
    return _world_instances[series_name]


if __name__ == "__main__":
    import sys, io
    if hasattr(sys.stdout, 'buffer'):
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    logging.basicConfig(level=logging.INFO)
    wm = get_world_model("test_series")
    wm.register_entity("Goku", "character",
                        {"hair_color":"black","power_level":9000})
    result = wm.validate_and_fix_prompt("fighting stance, dynamic pose", "Goku")
    print(f"fixed        : {result['fixed']}")
    print(f"fixed_prompt : {result['fixed_prompt']}")
    print(f"violations   : {result['violations']}")
    ctx = wm.get_context_for_run()
    print(f"context      : {ctx}")
    wm.end_run({"pipeline_health":"STABLE"})
    print("WorldModel OK")
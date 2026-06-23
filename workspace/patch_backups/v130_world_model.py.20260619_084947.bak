"""
v130_world_model.py — World Model & ContinuityGuard Ov3rLoRd V1.30
Registre des entités narratives avec validation de cohérence.
FIX V1.49 : SyntaxError 'break outside loop' ligne 64 corrigé.
"""
import logging
import json
from pathlib import Path
from datetime import datetime

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
                        break  # break dans for line -> valide
            if key:
                break  # break dans for env_path -> valide
    return key


class WorldModel:
    """Registre des entités + ContinuityGuard pour la cohérence narrative."""

    def __init__(self, series_name: str = "default"):
        self.series_name = series_name
        self.entities: dict[str, dict] = {}
        self.locations: dict[str, dict] = {}
        self.continuity_log: list[dict] = []
        self._storage = Path(f"workspace/narrative/{series_name}_world.json")
        self._load()
        log.info(f"[WORLD] Modèle chargé — {len(self.entities)} entités, {len(self.locations)} lieux.")

    def _load(self):
        if self._storage.exists():
            try:
                data = json.loads(self._storage.read_text(encoding="utf-8"))
                self.entities  = data.get("entities", {})
                self.locations = data.get("locations", {})
            except Exception as e:
                log.warning(f"[WORLD] Impossible de charger le modèle : {e}")

    def _save(self):
        try:
            self._storage.parent.mkdir(parents=True, exist_ok=True)
            self._storage.write_text(
                json.dumps({"entities": self.entities, "locations": self.locations}, ensure_ascii=False, indent=2),
                encoding="utf-8"
            )
        except Exception as e:
            log.warning(f"[WORLD] Sauvegarde échouée : {e}")

    def register_entity(self, name: str, entity_type: str, attributes: dict = None):
        self.entities[name] = {
            "type":       entity_type,
            "attributes": attributes or {},
            "first_seen": datetime.now(datetime.UTC).isoformat() if hasattr(datetime, 'UTC') else datetime.utcnow().isoformat(),
        }
        self._save()
        log.info(f"[WORLD] Entité enregistrée : {name} ({entity_type})")

    def validate_and_fix_prompt(self, prompt: str, character: str = None) -> tuple[str, list[str]]:
        warnings = []
        if character and character in self.entities:
            attrs = self.entities[character].get("attributes", {})
            color = attrs.get("hair_color")
            if color and color.lower() not in prompt.lower():
                prompt = f"{color} hair, {prompt}"
                warnings.append(f"Couleur cheveux ajoutée pour {character} : {color}")
        return prompt, warnings

    def get_entity(self, name: str) -> dict:
        return self.entities.get(name, {})

    def list_entities(self) -> list[str]:
        return list(self.entities.keys())


_world_instances: dict[str, WorldModel] = {}

def get_world_model(series_name: str = "default") -> WorldModel:
    if series_name not in _world_instances:
        _world_instances[series_name] = WorldModel(series_name)
    return _world_instances[series_name]


if __name__ == "__main__":
    import sys, io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    logging.basicConfig(level=logging.INFO)
    wm = get_world_model("test_series")
    wm.register_entity("Goku", "character", {"hair_color": "black", "power_level": 9000})
    prompt, warns = wm.validate_and_fix_prompt("fighting stance, dynamic pose", "Goku")
    print(f"Prompt enrichi : {prompt}")
    print(f"Warnings : {warns}")
    print("WorldModel OK")
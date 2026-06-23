"""
agents/v130_generative_world.py — OverLord V1.30 — Generative World

L'univers de ta production existe EN DEHORS des runs.
Les personnages vieillissent. Les événements du run 1 ont des conséquences au run 50.
Le monde se souvient. C'est la différence entre un générateur de contenu
et un générateur de franchise.

Ce module complète le WorldModel (v130_world_model.py) en ajoutant :
  - Aging System       : les entités évoluent avec le temps
  - Consequence Engine : chaque événement génère des conséquences futures
  - Faction Dynamics   : guerres, alliances, trahisons qui évoluent
  - Economy Engine     : ressources, pouvoir, influence qui circulent
  - Weather/Climate    : atmosphère du monde qui évolue
  - Myth Generator     : légendes et prophéties créées en jeu
"""

import json
import random
import time
import logging
from pathlib import Path
from datetime import datetime
from dataclasses import dataclass, field
from typing import Optional
import requests

WORLD_GEN_DIR = Path("workspace/generative_world")
ANTHROPIC_URL = "https://api.anthropic.com/v1/messages"

def _get_api_key() -> str:
    import os as _os
    from pathlib import Path as _P
    key = _os.environ.get("ANTHROPIC_API_KEY", "")
    if not key:
        for env in [_P(__file__).parent.parent / ".env", _P(".env")]:
            if env.exists():
                for line in env.read_text(encoding="utf-8").splitlines():
                    if line.startswith("ANTHROPIC_API_KEY="):
                        key = line.split("=",1)[1].strip().strip('"').strip("'")
                        if key: break
    return key

CLAUDE_MODEL  = "claude-sonnet-4-6"


def _llm(prompt: str, system: str = "", max_tokens: int = 400) -> str:
    try:
        body = {"model": CLAUDE_MODEL, "max_tokens": max_tokens,
                "messages": [{"role": "user", "content": prompt}]}
        if system:
            body["system"] = system
        r = requests.post(ANTHROPIC_URL,
                          headers={
                "Content-Type": "application/json",
                "x-api-key": _get_api_key(),
                "anthropic-version": "2023-06-01",
            },
                          json=body, timeout=25)
        if r.status_code == 200:
            return r.json()["content"][0]["text"].strip()
    except Exception:
        pass
    return ""


# ══════════════════════════════════════════════════════════════════════
# AGING SYSTEM
# ══════════════════════════════════════════════════════════════════════

class AgingSystem:
    """
    Les entités vieillissent et évoluent avec le temps.
    Run 1 : Kael a 17 ans, apprenti.
    Run 20: Kael a 19 ans, guerrier confirmé.
    Run 50: Kael a 22 ans, légendaire, cicatrice supplémentaire.
    """

    AGE_STAGES = {
        "child":     (0, 12,  ["childlike expression", "small body", "innocent eyes"]),
        "teen":      (13, 17, ["young face", "youthful", "growth spurt"]),
        "young":     (18, 25, ["young adult", "peak physical condition", "energetic"]),
        "adult":     (26, 40, ["mature face", "experienced look", "confident"]),
        "middle":    (41, 55, ["middle aged", "slight wrinkles", "wise expression"]),
        "elder":     (56, 999,["elderly", "weathered face", "white hair possible"]),
    }

    BATTLE_SCARS = [
        "scar on left cheek", "scar over right eye", "scar on chin",
        "battle-worn armor", "missing finger", "burn scar on arm",
        "grey streak in hair from stress",
    ]

    def __init__(self):
        self._ages:    dict[str, float] = {}   # entity_id → âge
        self._scars:   dict[str, list]  = {}   # entity_id → liste de cicatrices
        self._growth:  dict[str, list]  = {}   # entity_id → historique des changements

    def set_age(self, entity_id: str, age: float):
        self._ages[entity_id] = age

    def age_entity(self, entity_id: str,
                    years: float = 0.1) -> dict:
        """Fait vieillir une entité de N années et retourne les changements visuels."""
        if entity_id not in self._ages:
            self._ages[entity_id] = 18.0
        old_age = self._ages[entity_id]
        new_age = old_age + years
        self._ages[entity_id] = new_age

        changes = []
        old_stage = self._get_stage(old_age)
        new_stage = self._get_stage(new_age)

        # Changement de stade ?
        if old_stage != new_stage:
            _, _, new_tags = self.AGE_STAGES[new_stage]
            changes.append({
                "type":    "stage_change",
                "from":    old_stage,
                "to":      new_stage,
                "new_tags":new_tags,
            })

        if entity_id not in self._growth:
            self._growth[entity_id] = []
        if changes:
            self._growth[entity_id].append({
                "age": new_age, "changes": changes, "ts": time.time()
            })
        return {"old_age": old_age, "new_age": new_age, "changes": changes}

    def add_scar(self, entity_id: str,
                  scar: str = None) -> str:
        """Ajoute une cicatrice à un personnage."""
        if entity_id not in self._scars:
            self._scars[entity_id] = []
        if scar is None:
            # Choisir une cicatrice non encore attribuée
            existing = self._scars[entity_id]
            available = [s for s in self.BATTLE_SCARS if s not in existing]
            scar = random.choice(available) if available else "additional battle scar"
        self._scars[entity_id].append(scar)
        return scar

    def get_visual_tags(self, entity_id: str) -> list[str]:
        """Retourne les tags visuels actuels (âge + cicatrices)."""
        age   = self._ages.get(entity_id, 18)
        stage = self._get_stage(age)
        _, _, stage_tags = self.AGE_STAGES[stage]
        scars = self._scars.get(entity_id, [])
        return stage_tags + scars

    def _get_stage(self, age: float) -> str:
        for stage, (min_a, max_a, _) in self.AGE_STAGES.items():
            if min_a <= age <= max_a:
                return stage
        return "adult"


# ══════════════════════════════════════════════════════════════════════
# CONSEQUENCE ENGINE
# ══════════════════════════════════════════════════════════════════════

@dataclass
class Consequence:
    """Une conséquence d'un événement passé."""
    source_event:  str
    trigger_run:   int       # run où ça se déclenche
    description:   str
    affected_entities: list
    impact_type:   str       # "character_change","world_change","plot_point"
    executed:      bool = False


class ConsequenceEngine:
    """
    Chaque événement génère des conséquences futures automatiquement.
    Run 5  : L'armée de l'Est est vaincue.
    Run 12 : Le général vaincu réapparaît avec une armée de l'ombre.
    Run 20 : La paix signée au run 5 expire. Conflit relancé.
    """

    def __init__(self):
        self._consequences: list[Consequence] = []
        self._current_run = 0

    def plan_consequences(self, event: dict,
                           current_run: int) -> list[Consequence]:
        """
        Génère les conséquences futures d'un événement via LLM.
        """
        prompt = (
            f"Événement du run {current_run} : {json.dumps(event, ensure_ascii=False)}\n\n"
            f"Génère 2-3 conséquences futures qui se déclencheront dans les prochains runs. "
            f"Pense à des conséquences inattendues mais cohérentes.\n"
            f"Réponds en JSON : [{{'description':'...','trigger_run_delta':3,"
            f"'impact_type':'character_change|world_change|plot_point',"
            f"'affected':['entity1']}}]"
        )
        result = _llm(prompt, max_tokens=400)
        consequences = []
        try:
            if result.startswith("```"):
                result = "\n".join(result.split("\n")[1:-1])
            data = json.loads(result)
            for d in data:
                c = Consequence(
                    source_event   = event.get("title","?"),
                    trigger_run    = current_run + d.get("trigger_run_delta", 5),
                    description    = d.get("description",""),
                    affected_entities = d.get("affected",[]),
                    impact_type    = d.get("impact_type","plot_point"),
                )
                consequences.append(c)
                self._consequences.append(c)
        except Exception:
            pass
        return consequences

    def get_due_consequences(self, current_run: int) -> list[Consequence]:
        """Retourne les conséquences qui se déclenchent au run actuel."""
        due = [c for c in self._consequences
               if c.trigger_run <= current_run and not c.executed]
        for c in due:
            c.executed = True
        return due

    def get_upcoming(self, next_n_runs: int = 10) -> list[dict]:
        """Retourne ce qui est prévu dans les prochains runs."""
        upcoming = [c for c in self._consequences
                    if not c.executed and
                    c.trigger_run <= self._current_run + next_n_runs]
        return [{"run": c.trigger_run, "description": c.description,
                  "type": c.impact_type} for c in upcoming]


# ══════════════════════════════════════════════════════════════════════
# FACTION DYNAMICS
# ══════════════════════════════════════════════════════════════════════

@dataclass
class Faction:
    """Une faction dans l'univers."""
    id:        str
    name:      str
    power:     float = 0.5    # 0-1, puissance relative
    stability: float = 0.8    # 0-1, stabilité interne
    alignment: str   = "neutral"  # "heroic","villainous","neutral","chaotic"
    allies:    list  = field(default_factory=list)
    enemies:   list  = field(default_factory=list)
    territory: str   = ""
    visual_tags: list = field(default_factory=list)


class FactionDynamics:
    """
    Gère les dynamiques entre factions : alliances, guerres, trahisons.
    Ces dynamiques évoluent automatiquement entre les runs.
    """

    def __init__(self):
        self._factions: dict[str, Faction] = {}
        self._events:   list[dict] = []

    def register(self, faction: Faction):
        self._factions[faction.id] = faction

    def evolve(self, current_run: int) -> list[dict]:
        """Fait évoluer les dynamiques de factions pour un run."""
        events = []
        factions = list(self._factions.values())
        if len(factions) < 2:
            return events

        # Chance de changement d'alliance (5% par run)
        for f in factions:
            if random.random() < 0.05:
                other = random.choice([x for x in factions if x.id != f.id])
                if other.id in f.allies:
                    # Trahison
                    f.allies.remove(other.id)
                    f.enemies.append(other.id)
                    events.append({
                        "type": "betrayal",
                        "faction_a": f.name,
                        "faction_b": other.name,
                        "description": f"{f.name} trahit {other.name}",
                        "run": current_run,
                    })
                elif other.id in f.enemies and random.random() < 0.3:
                    # Paix
                    f.enemies.remove(other.id)
                    events.append({
                        "type": "peace",
                        "faction_a": f.name,
                        "faction_b": other.name,
                        "description": f"Paix entre {f.name} et {other.name}",
                        "run": current_run,
                    })

            # Fluctuation de puissance
            f.power = max(0.1, min(1.0, f.power + random.gauss(0, 0.05)))

        self._events.extend(events)
        return events

    def get_political_map(self) -> dict:
        """Carte politique actuelle."""
        return {
            fid: {
                "name":      f.name,
                "power":     round(f.power, 2),
                "alignment": f.alignment,
                "allies":    [self._factions[a].name for a in f.allies if a in self._factions],
                "enemies":   [self._factions[e].name for e in f.enemies if e in self._factions],
            }
            for fid, f in self._factions.items()
        }

    def get_context_for_prompt(self) -> str:
        """Résumé des tensions politiques pour les prompts."""
        tensions = []
        for f in self._factions.values():
            if f.enemies:
                enemy_names = [self._factions[e].name
                                for e in f.enemies if e in self._factions]
                tensions.append(f"{f.name} vs {', '.join(enemy_names)}")
        return "; ".join(tensions[:3]) if tensions else "Paix relative"


# ══════════════════════════════════════════════════════════════════════
# MYTH GENERATOR
# ══════════════════════════════════════════════════════════════════════

class MythGenerator:
    """
    Génère des légendes, prophéties et mythes qui émergent de l'histoire.
    Ces éléments enrichissent les futurs scénarios.
    """

    def __init__(self):
        self._myths: list[dict] = []

    def generate_from_event(self, event: dict,
                             universe_name: str = "l'univers") -> dict:
        """Génère un mythe/légende depuis un événement marquant."""
        prompt = (
            f"Dans {universe_name}, cet événement s'est produit :\n"
            f"'{event.get('description','?')}'\n\n"
            f"Des générations plus tard, comment cet événement est-il devenu "
            f"une légende, un mythe ou une prophécie ? "
            f"Génère une courte légende poétique de 3-4 phrases qui déforme "
            f"légèrement la vérité historique (comme les vrais mythes)."
        )
        myth_text = _llm(prompt, max_tokens=200)
        myth = {
            "source_event": event.get("title","?"),
            "myth_text":    myth_text,
            "type":         random.choice(["légende","prophécie","chanson de guerre","conte"]),
            "created_at":   datetime.utcnow().isoformat(),
        }
        self._myths.append(myth)
        return myth

    def get_prophecy_for_prompt(self) -> str:
        """Retourne une prophécie à injecter dans un prompt narratif."""
        if not self._myths:
            return ""
        myth = random.choice(self._myths)
        return f"Prophécie ancienne: '{myth['myth_text'][:80]}...'"

    def get_all_myths(self) -> list[dict]:
        return list(self._myths)


# ══════════════════════════════════════════════════════════════════════
# GENERATIVE WORLD — FAÇADE
# ══════════════════════════════════════════════════════════════════════

class GenerativeWorld:
    """
    Monde génératif complet — la franchise vivante d'OverLord.
    Intègre tous les sous-systèmes d'évolution du monde.
    """

    def __init__(self, world_name: str = "default",
                 logger: logging.Logger = None):
        self.log         = logger or logging.getLogger("gen_world")
        self.world_name  = world_name
        self.aging       = AgingSystem()
        self.consequences= ConsequenceEngine()
        self.factions    = FactionDynamics()
        self.myths       = MythGenerator()
        self._current_run = 0
        self._world_log:  list[dict] = []
        WORLD_GEN_DIR.mkdir(parents=True, exist_ok=True)
        self._load()

    def advance_run(self, events: list[dict] = None) -> dict:
        """
        Fait avancer le monde d'un run.
        Applique le vieillissement, les conséquences, l'évolution des factions.
        """
        self._current_run += 1
        run_id = self._current_run
        changes = {
            "run_id":       run_id,
            "aging":        [],
            "consequences": [],
            "faction_events":[],
            "new_myths":    [],
        }

        # 1. Vieillissement (~0.1 an par run = ~10 runs/an fictif)
        for entity_id, age in self.aging._ages.items():
            result = self.aging.age_entity(entity_id, years=0.1)
            if result["changes"]:
                changes["aging"].append(result)

        # 2. Conséquences dues
        due = self.consequences.get_due_consequences(run_id)
        for c in due:
            changes["consequences"].append({
                "description": c.description,
                "type":        c.impact_type,
                "entities":    c.affected_entities,
            })

        # 3. Planifier les conséquences des nouveaux événements
        for event in (events or []):
            new_cons = self.consequences.plan_consequences(event, run_id)
            # Générer un mythe si événement majeur
            if event.get("impact") == "major":
                myth = self.myths.generate_from_event(event, self.world_name)
                changes["new_myths"].append(myth.get("myth_text","")[:80])

        # 4. Évolution des factions
        faction_events = self.factions.evolve(run_id)
        changes["faction_events"] = faction_events

        self._world_log.append(changes)
        self._save()
        self.log.info(
            f"[GEN_WORLD] Run {run_id} | "
            f"Conséquences: {len(due)} | "
            f"Factions: {len(faction_events)} événements"
        )
        return changes

    def get_world_prompt_context(self) -> str:
        """
        Génère le contexte du monde à injecter dans les prompts.
        Vision rapide de l'état actuel du monde.
        """
        political = self.factions.get_context_for_prompt()
        prophecy  = self.myths.get_prophecy_for_prompt()
        upcoming  = self.consequences.get_upcoming(next_n_runs=5)

        context = f"[MONDE — Run {self._current_run}]\n"
        if political:
            context += f"Tensions : {political}\n"
        if prophecy:
            context += f"{prophecy}\n"
        if upcoming:
            context += f"À venir : {upcoming[0]['description'][:60]}\n"
        return context

    def get_character_current_state(self, entity_id: str) -> dict:
        """État actuel d'un personnage (âge, cicatrices, position narrative)."""
        return {
            "entity_id":   entity_id,
            "age":         self.aging._ages.get(entity_id, 18),
            "visual_tags": self.aging.get_visual_tags(entity_id),
            "run":         self._current_run,
        }

    def initialize_from_brief(self, brief: str) -> dict:
        """Initialise le monde génératif depuis un brief narratif."""
        # Créer quelques factions de base via LLM
        prompt = (
            f"Pour cet univers : '{brief}'\n\n"
            f"Crée 2-3 factions/groupes qui s'affrontent. "
            f"Réponds en JSON : [{{'name':'...','alignment':'heroic|villainous|neutral',"
            f"'power':0.6,'territory':'...','visual_tags':['...']}}]"
        )
        result = _llm(prompt, max_tokens=400)
        factions_created = []
        try:
            if result.startswith("```"):
                result = "\n".join(result.split("\n")[1:-1])
            data = json.loads(result)
            for i, fd in enumerate(data):
                f = Faction(
                    id=f"faction_{i}",
                    name=fd.get("name","?"),
                    power=fd.get("power",0.5),
                    alignment=fd.get("alignment","neutral"),
                    territory=fd.get("territory",""),
                    visual_tags=fd.get("visual_tags",[]),
                )
                self.factions.register(f)
                factions_created.append(f.name)
        except Exception:
            pass

        self.log.info(f"[GEN_WORLD] Monde '{self.world_name}' initialisé : {factions_created}")
        return {
            "factions": factions_created,
            "world_name": self.world_name,
        }

    def get_dashboard(self) -> dict:
        return {
            "world_name":       self.world_name,
            "current_run":      self._current_run,
            "total_factions":   len(self.factions._factions),
            "total_myths":      len(self.myths._myths),
            "consequences_pending": len([c for c in self.consequences._consequences
                                          if not c.executed]),
            "tracked_entities": len(self.aging._ages),
            "political_status": self.factions.get_context_for_prompt(),
        }

    def _save(self):
        data = {
            "world_name":    self.world_name,
            "current_run":   self._current_run,
            "aging_ages":    self.aging._ages,
            "aging_scars":   self.aging._scars,
            "myths":         self.myths._myths[-20:],
            "faction_events":self.factions._events[-50:],
        }
        (WORLD_GEN_DIR / f"{self.world_name}.json").write_text(
            json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8"
        )

    def _load(self):
        f = WORLD_GEN_DIR / f"{self.world_name}.json"
        if f.exists():
            try:
                data = json.loads(f.read_text(encoding="utf-8"))
                self._current_run      = data.get("current_run", 0)
                self.aging._ages       = data.get("aging_ages", {})
                self.aging._scars      = data.get("aging_scars", {})
                self.myths._myths      = data.get("myths", [])
            except Exception:
                pass


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    world = GenerativeWorld("test_universe")

    print("=== V1.30 GENERATIVE WORLD TEST ===\n")

    # Initialiser
    result = world.initialize_from_brief(
        "Un royaume médiéval fantastique divisé entre l'Ordre de la Lumière et la Confrérie des Ombres"
    )
    print(f"Factions créées : {result['factions']}")

    # Simuler quelques runs
    for run in range(3):
        events = [{"title": f"Bataille run {run}", "description": "Affrontement majeur",
                   "impact": "major" if run == 1 else "minor"}]
        changes = world.advance_run(events)
        print(f"\nRun {run+1}: {len(changes['faction_events'])} événements faction | "
              f"{len(changes['consequences'])} conséquences")

    # Context pour prompt
    print(f"\nContexte monde :\n{world.get_world_prompt_context()}")
    print(f"\nDashboard : {world.get_dashboard()}")

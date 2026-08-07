"""
agents/v130_world_model.py — OverLord V1.30 — World Model

La fonctionnalité la plus profonde de V1.30.
L'IA construit et maintient une représentation interne PERSISTANTE
de l'univers créatif qu'elle produit — entre les runs, entre les sessions.

Analogie directe avec moi (Claude) :
  Je maintiens un modèle interne du monde pendant une conversation.
  Je me souviens que tu m'as dit que tu aimais le style dark fantasy,
  que le personnage principal s'appelle Kael, qu'il a perdu sa soeur.
  Ces informations influencent TOUTES mes réponses suivantes.

OverLord V1.30 fait la même chose mais pour la production créative :

  Run 1  : Kael est introduit. cheveux noirs, cicatrice oeil gauche.
  Run 12 : Kael a vaincu le général Frost. Il a une armure maintenant.
  Run 25 : La ville de Solaris a été détruite. Elle n'existe plus.
  Run 50 : Kael a 5 ans de plus. Sa cicatrice s'est étendue.

Sans World Model → chaque run repart de zéro, les personnages se contredisent.
Avec World Model → une vraie franchise cohérente qui se construit run après run.

Composants :
  - EntityRegistry    : tous les personnages, lieux, objets avec leur état
  - TimelineEngine    : chronologie des événements de l'univers
  - RelationshipGraph : qui connaît qui, alliances, conflits
  - LoreDatabase      : règles de l'univers (magie, technologie, société)
  - WorldStateTracker : l'état actuel du monde à chaque run
  - ContinuityGuard   : détecte et prévient les contradictions
"""

import json
import hashlib
import time
import logging
import threading
from pathlib import Path
from datetime import datetime
from dataclasses import dataclass, field
from typing import Any, Optional
from enum import Enum
import requests

WORLD_DIR     = Path("workspace/world_model")
ANTHROPIC_URL = "https://api.anthropic.com/v1/messages"
CLAUDE_MODEL  = "claude-sonnet-4-6"


def _llm(prompt: str, system: str = "", max_tokens: int = 600) -> str:
    try:
        body = {"model": CLAUDE_MODEL, "max_tokens": max_tokens,
                "messages": [{"role": "user", "content": prompt}]}
        if system:
            body["system"] = system
        r = requests.post(ANTHROPIC_URL,
                          headers={"Content-Type": "application/json"},
                          json=body, timeout=30)
        if r.status_code == 200:
            return r.json()["content"][0]["text"].strip()
    except Exception:
        pass
    return ""


# ══════════════════════════════════════════════════════════════════════
# TYPES D'ENTITÉS
# ══════════════════════════════════════════════════════════════════════

class EntityType(Enum):
    CHARACTER = "character"
    LOCATION  = "location"
    OBJECT    = "object"
    FACTION   = "faction"
    EVENT     = "event"
    CONCEPT   = "concept"   # magie, technologie, règle de l'univers


class EntityStatus(Enum):
    ALIVE     = "alive"
    DEAD      = "dead"
    UNKNOWN   = "unknown"
    DESTROYED = "destroyed"
    TRANSFORMED = "transformed"


@dataclass
class Entity:
    """Une entité dans l'univers (personnage, lieu, objet...)."""
    id:            str
    name:          str
    type:          EntityType
    status:        EntityStatus = EntityStatus.ALIVE
    description:   str = ""
    visual_tags:   list = field(default_factory=list)   # tags ComfyUI pour ce personnage
    lore:          dict = field(default_factory=dict)   # infos narratives
    relationships: dict = field(default_factory=dict)  # {entity_id: relation_type}
    first_appearance: int = 0   # numéro de run
    last_seen:     int = 0
    arc_stage:     str = "introduction"  # introduction/development/climax/resolution
    modifications: list = field(default_factory=list)  # historique des changements

    def add_modification(self, run_id: int, change: str, new_value: Any = None):
        self.modifications.append({
            "run":    run_id,
            "change": change,
            "value":  new_value,
            "ts":     datetime.utcnow().isoformat(),
        })
        self.last_seen = run_id

    def to_prompt_context(self) -> str:
        """Convertit l'entité en contexte injectables dans un prompt."""
        ctx = f"{self.name} ({self.type.value}, {self.status.value})"
        if self.visual_tags:
            ctx += f" | Visual: {', '.join(self.visual_tags[:6])}"
        if self.description:
            ctx += f" | {self.description[:100]}"
        return ctx

    def to_dict(self) -> dict:
        return {
            "id": self.id, "name": self.name,
            "type": self.type.value, "status": self.status.value,
            "description": self.description,
            "visual_tags": self.visual_tags,
            "lore": self.lore,
            "relationships": self.relationships,
            "first_appearance": self.first_appearance,
            "last_seen": self.last_seen,
            "arc_stage": self.arc_stage,
            "modifications": self.modifications[-10:],
        }


# ══════════════════════════════════════════════════════════════════════
# REGISTRE D'ENTITÉS
# ══════════════════════════════════════════════════════════════════════

class EntityRegistry:
    """
    Registre central de toutes les entités de l'univers.
    Persiste entre les runs et les sessions.
    """

    def __init__(self, world_dir: Path):
        self._entities: dict[str, Entity] = {}
        self._lock     = threading.Lock()
        self._file     = world_dir / "entities.json"
        self._load()

    def register(self, name: str, entity_type: EntityType,
                  description: str = "",
                  visual_tags: list = None,
                  lore: dict = None,
                  run_id: int = 0) -> Entity:
        """Enregistre une nouvelle entité dans l'univers."""
        eid  = hashlib.md5(f"{name}{entity_type.value}".encode()).hexdigest()[:12]
        with self._lock:
            if eid in self._entities:
                return self._entities[eid]
            entity = Entity(
                id=eid, name=name, type=entity_type,
                description=description,
                visual_tags=visual_tags or [],
                lore=lore or {},
                first_appearance=run_id,
                last_seen=run_id,
            )
            self._entities[eid] = entity
        self._save()
        return entity

    def update(self, entity_id: str, run_id: int,
               **kwargs) -> Optional[Entity]:
        """Met à jour une entité et enregistre le changement."""
        with self._lock:
            entity = self._entities.get(entity_id)
            if not entity:
                return None
            for key, value in kwargs.items():
                old_value = getattr(entity, key, None)
                if old_value != value:
                    entity.add_modification(run_id, f"{key}: {old_value} → {value}", value)
                    setattr(entity, key, value)
        self._save()
        return entity

    def get(self, entity_id: str) -> Optional[Entity]:
        return self._entities.get(entity_id)

    def find_by_name(self, name: str) -> Optional[Entity]:
        name_l = name.lower()
        for e in self._entities.values():
            if e.name.lower() == name_l or name_l in e.name.lower():
                return e
        return None

    def get_all(self, entity_type: EntityType = None) -> list[Entity]:
        with self._lock:
            entities = list(self._entities.values())
        if entity_type:
            entities = [e for e in entities if e.type == entity_type]
        return entities

    def get_active_characters(self) -> list[Entity]:
        return [e for e in self.get_all(EntityType.CHARACTER)
                if e.status == EntityStatus.ALIVE]

    def _save(self):
        with self._lock:
            data = {eid: e.to_dict() for eid, e in self._entities.items()}
        self._file.write_text(
            json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8"
        )

    def _load(self):
        if not self._file.exists():
            return
        try:
            data = json.loads(self._file.read_text(encoding="utf-8"))
            for eid, d in data.items():
                e = Entity(
                    id=d["id"], name=d["name"],
                    type=EntityType(d["type"]),
                    status=EntityStatus(d["status"]),
                    description=d.get("description",""),
                    visual_tags=d.get("visual_tags",[]),
                    lore=d.get("lore",{}),
                    relationships=d.get("relationships",{}),
                    first_appearance=d.get("first_appearance",0),
                    last_seen=d.get("last_seen",0),
                    arc_stage=d.get("arc_stage","introduction"),
                    modifications=d.get("modifications",[]),
                )
                self._entities[eid] = e
        except Exception:
            pass


# ══════════════════════════════════════════════════════════════════════
# TIMELINE ENGINE
# ══════════════════════════════════════════════════════════════════════

@dataclass
class WorldEvent:
    """Un événement dans la chronologie de l'univers."""
    id:         str
    run_id:     int
    timestamp:  str
    title:      str
    description:str
    entities_involved: list   # IDs des entités concernées
    world_impact: str         # "minor" / "major" / "catastrophic"
    consequences: list        # liste de conséquences déjà réalisées


class TimelineEngine:
    """
    Moteur de chronologie — maintient l'ordre des événements
    et leurs relations causales.
    """

    def __init__(self, world_dir: Path):
        self._events: list[WorldEvent] = []
        self._file   = world_dir / "timeline.json"
        self._load()

    def record(self, run_id: int, title: str, description: str,
               entities: list = None, impact: str = "minor") -> WorldEvent:
        """Enregistre un événement dans la chronologie."""
        event = WorldEvent(
            id=hashlib.md5(f"{run_id}{title}".encode()).hexdigest()[:8],
            run_id=run_id,
            timestamp=datetime.utcnow().isoformat(),
            title=title,
            description=description,
            entities_involved=entities or [],
            world_impact=impact,
            consequences=[],
        )
        self._events.append(event)
        self._save()
        return event

    def get_history(self, since_run: int = 0, n: int = 20) -> list[WorldEvent]:
        events = [e for e in self._events if e.run_id >= since_run]
        return sorted(events, key=lambda e: e.run_id)[-n:]

    def get_entity_history(self, entity_id: str) -> list[WorldEvent]:
        return [e for e in self._events if entity_id in e.entities_involved]

    def to_narrative_context(self, last_n: int = 5) -> str:
        """Résume les derniers événements pour injection dans les prompts."""
        recent = self.get_history(n=last_n)
        if not recent:
            return "Début de l'histoire."
        lines = [f"Run {e.run_id}: {e.title} — {e.description[:80]}"
                 for e in recent]
        return "\n".join(lines)

    def _save(self):
        data = [{
            "id": e.id, "run_id": e.run_id, "timestamp": e.timestamp,
            "title": e.title, "description": e.description,
            "entities_involved": e.entities_involved,
            "world_impact": e.world_impact, "consequences": e.consequences,
        } for e in self._events[-500:]]
        self._file.write_text(
            json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8"
        )

    def _load(self):
        if not self._file.exists():
            return
        try:
            data = json.loads(self._file.read_text(encoding="utf-8"))
            self._events = [WorldEvent(**d) for d in data]
        except Exception:
            pass


# ══════════════════════════════════════════════════════════════════════
# LORE DATABASE
# ══════════════════════════════════════════════════════════════════════

class LoreDatabase:
    """
    Base de règles de l'univers : magie, technologie, société, géographie.
    Ces règles sont IMMUABLES sauf modification explicite du créateur.
    """

    def __init__(self, world_dir: Path):
        self._rules: dict[str, dict] = {}
        self._file  = world_dir / "lore.json"
        self._load()

    def define_rule(self, category: str, name: str,
                    description: str, constraints: list = None):
        """Définit une règle de l'univers."""
        if category not in self._rules:
            self._rules[category] = {}
        self._rules[category][name] = {
            "description": description,
            "constraints": constraints or [],
            "created_at":  datetime.utcnow().isoformat(),
        }
        self._save()

    def get_rules_context(self, category: str = None) -> str:
        """Retourne les règles pour injection dans un prompt système."""
        if category:
            rules = self._rules.get(category, {})
            categories = {category: rules}
        else:
            categories = self._rules

        lines = []
        for cat, rules in categories.items():
            lines.append(f"\n[{cat.upper()}]")
            for name, rule in rules.items():
                lines.append(f"  {name}: {rule['description']}")
                for c in rule.get("constraints", [])[:2]:
                    lines.append(f"    → {c}")
        return "\n".join(lines) if lines else "Aucune règle définie."

    def check_violation(self, action: str) -> dict:
        """Vérifie si une action viole les règles du lore via LLM."""
        if not self._rules:
            return {"violation": False}
        rules_str = self.get_rules_context()
        prompt = (
            f"Règles de l'univers :\n{rules_str}\n\n"
            f"Action proposée : '{action}'\n\n"
            f"Cette action viole-t-elle une règle de l'univers ?\n"
            f"Réponds en JSON : {{\"violation\": true/false, "
            f"\"rule_violated\": \"nom ou null\", \"explanation\": \"...\"}}"
        )
        result = _llm(prompt, max_tokens=200)
        try:
            if result.startswith("```"):
                result = "\n".join(result.split("\n")[1:-1])
            return json.loads(result)
        except Exception:
            return {"violation": False}

    def _save(self):
        self._file.write_text(
            json.dumps(self._rules, indent=2, ensure_ascii=False), encoding="utf-8"
        )

    def _load(self):
        if self._file.exists():
            try:
                self._rules = json.loads(self._file.read_text(encoding="utf-8"))
            except Exception:
                pass


# ══════════════════════════════════════════════════════════════════════
# CONTINUITY GUARD
# ══════════════════════════════════════════════════════════════════════

class ContinuityGuard:
    """
    Détecte et prévient les contradictions dans l'univers.

    Exemples de contradictions :
    - Personnage mort au run 5 qui réapparaît au run 12
    - Lieu détruit qui est décrit comme intact
    - Personnage décrit avec cheveux blonds alors que sa fiche dit noirs
    - Événement historique inversé dans le dialogue
    """

    def __init__(self, registry: EntityRegistry,
                 timeline: TimelineEngine,
                 lore: LoreDatabase,
                 logger: logging.Logger = None):
        self.log      = logger or logging.getLogger("continuity")
        self.registry = registry
        self.timeline = timeline
        self.lore     = lore
        self._violations: list[dict] = []

    def check_prompt(self, prompt: str, run_id: int) -> dict:
        """
        Vérifie un prompt contre l'état du monde.
        Retourne les contradictions potentielles.
        """
        issues = []

        # Vérifier les personnages mentionnés
        for char in self.registry.get_all(EntityType.CHARACTER):
            if char.name.lower() in prompt.lower():
                # Personnage mort qui est évoqué ?
                if char.status == EntityStatus.DEAD:
                    if "esprit" not in prompt.lower() and "souvenir" not in prompt.lower():
                        issues.append({
                            "type":    "dead_character_active",
                            "entity":  char.name,
                            "message": f"{char.name} est mort au run {char.last_seen}",
                            "severity":"high",
                        })
                # Vérifier les tags visuels
                for tag in char.visual_tags[:3]:
                    antonym = self._find_antonym_in_prompt(tag, prompt)
                    if antonym:
                        issues.append({
                            "type":    "visual_inconsistency",
                            "entity":  char.name,
                            "message": f"{char.name} devrait avoir '{tag}' mais le prompt contient '{antonym}'",
                            "severity":"medium",
                        })

        # Vérifier les lieux détruits
        for loc in self.registry.get_all(EntityType.LOCATION):
            if (loc.name.lower() in prompt.lower() and
                    loc.status == EntityStatus.DESTROYED):
                issues.append({
                    "type":    "destroyed_location",
                    "entity":  loc.name,
                    "message": f"{loc.name} a été détruit au run {loc.last_seen}",
                    "severity":"medium",
                })

        if issues:
            self._violations.extend(issues)
            self.log.warning(
                f"[CONTINUITY] {len(issues)} contradiction(s) détectée(s) au run {run_id}"
            )

        return {
            "run_id":     run_id,
            "issues":     issues,
            "has_issues": len(issues) > 0,
            "auto_fix":   len(issues) > 0,
        }

    def _find_antonym_in_prompt(self, tag: str, prompt: str) -> Optional[str]:
        """Détecte si un antonyme d'un tag est présent dans le prompt."""
        antonyms = {
            "black hair": ["blonde hair", "white hair", "red hair", "silver hair"],
            "blue eyes":  ["red eyes", "green eyes", "yellow eyes"],
            "tall":       ["short", "petite"],
            "muscular":   ["slim", "thin", "slender"],
            "young":      ["old", "elderly", "aged"],
            "cheerful":   ["melancholic", "sad", "gloomy"],
        }
        tag_l = tag.lower()
        prompt_l = prompt.lower()
        for src, opposites in antonyms.items():
            if src in tag_l:
                for opp in opposites:
                    if opp in prompt_l:
                        return opp
        return None

    def auto_fix_prompt(self, prompt: str, issues: list) -> str:
        """Corrige automatiquement un prompt pour éliminer les contradictions."""
        if not issues:
            return prompt
        issue_str = "\n".join(
            f"- {i['message']}" for i in issues[:5]
        )
        world_ctx = self._build_world_context()
        fixed = _llm(
            f"Corrige ce prompt pour éliminer les contradictions avec l'état du monde :\n\n"
            f"PROMPT ORIGINAL :\n{prompt}\n\n"
            f"CONTRADICTIONS :\n{issue_str}\n\n"
            f"ÉTAT DU MONDE :\n{world_ctx}\n\n"
            f"Retourne UNIQUEMENT le prompt corrigé, sans explication.",
            max_tokens=400
        )
        return fixed if fixed and len(fixed) > 20 else prompt

    def _build_world_context(self) -> str:
        chars = self.registry.get_active_characters()[:5]
        return "\n".join(c.to_prompt_context() for c in chars)

    def get_violation_report(self) -> dict:
        by_type = {}
        for v in self._violations:
            t = v["type"]
            by_type[t] = by_type.get(t, 0) + 1
        return {
            "total_violations": len(self._violations),
            "by_type":          by_type,
            "recent":           self._violations[-5:],
        }


# ══════════════════════════════════════════════════════════════════════
# WORLD STATE TRACKER
# ══════════════════════════════════════════════════════════════════════

class WorldStateTracker:
    """
    Snapshot de l'état du monde à chaque run.
    Permet de "revenir en arrière" ou de comparer des états du monde.
    """

    def __init__(self, world_dir: Path):
        self._states: list[dict] = []
        self._file   = world_dir / "world_states.json"
        self._load()

    def snapshot(self, run_id: int, registry: EntityRegistry,
                 timeline: TimelineEngine, notes: str = "") -> dict:
        """Prend un snapshot de l'état du monde."""
        chars = registry.get_all(EntityType.CHARACTER)
        locs  = registry.get_all(EntityType.LOCATION)
        events = timeline.get_history(n=5)

        state = {
            "run_id":     run_id,
            "timestamp":  datetime.utcnow().isoformat(),
            "notes":      notes,
            "n_characters": len(chars),
            "alive_chars":  len([c for c in chars if c.status == EntityStatus.ALIVE]),
            "n_locations":  len(locs),
            "recent_events":[e.title for e in events],
            "character_summary": [
                {"name": c.name, "status": c.status.value, "arc": c.arc_stage}
                for c in chars[:10]
            ],
        }
        self._states.append(state)
        self._save()
        return state

    def get_state(self, run_id: int) -> Optional[dict]:
        for s in reversed(self._states):
            if s["run_id"] <= run_id:
                return s
        return None

    def get_world_summary(self) -> str:
        """Résumé de l'évolution du monde pour l'UI."""
        if not self._states:
            return "Monde non initialisé."
        first = self._states[0]
        last  = self._states[-1]
        return (
            f"Monde vivant depuis le run {first['run_id']} jusqu'au run {last['run_id']}.\n"
            f"Personnages : {last['alive_chars']} vivants / {last['n_characters']} total.\n"
            f"Lieux : {last['n_locations']}.\n"
            f"Derniers événements : {', '.join(last['recent_events'][:3])}."
        )

    def _save(self):
        self._file.write_text(
            json.dumps(self._states[-100:], indent=2, ensure_ascii=False),
            encoding="utf-8"
        )

    def _load(self):
        if self._file.exists():
            try:
                self._states = json.loads(self._file.read_text(encoding="utf-8"))
            except Exception:
                pass


# ══════════════════════════════════════════════════════════════════════
# WORLD MODEL — FAÇADE PRINCIPALE
# ══════════════════════════════════════════════════════════════════════

class WorldModel:
    """
    Le World Model d'OverLord — cerveau persistant de l'univers créatif.

    Point d'entrée unique pour tout ce qui touche à la cohérence narrative
    et à la continuité entre les runs.
    """

    def __init__(self, project_name: str = "default",
                 logger: logging.Logger = None):
        self.log          = logger or logging.getLogger("world_model")
        self.project_name = project_name
        self.world_dir    = WORLD_DIR / project_name
        self.world_dir.mkdir(parents=True, exist_ok=True)

        self.registry  = EntityRegistry(self.world_dir)
        self.timeline  = TimelineEngine(self.world_dir)
        self.lore      = LoreDatabase(self.world_dir)
        self.tracker   = WorldStateTracker(self.world_dir)
        self.guard     = ContinuityGuard(
            self.registry, self.timeline, self.lore, self.log
        )
        self._current_run = self._get_last_run() + 1

        self.log.info(
            f"[WORLD] Monde '{project_name}' chargé | "
            f"Run actuel : {self._current_run} | "
            f"{len(self.registry.get_all())} entités | "
            f"{len(self.timeline.get_history())} événements"
        )

    def _get_last_run(self) -> int:
        states = self.tracker._states
        return states[-1]["run_id"] if states else 0

    # ── API PRINCIPALE ────────────────────────────────────────────────

    def start_run(self, run_id: int = None) -> dict:
        """Démarre un nouveau run et retourne le contexte du monde."""
        if run_id:
            self._current_run = run_id
        ctx = self.get_context_for_run()
        self.log.info(f"[WORLD] Run {self._current_run} démarré")
        return ctx

    def get_context_for_run(self) -> dict:
        """
        Retourne tout le contexte nécessaire pour un run cohérent.
        Ce contexte est injecté dans les prompts de tous les agents.
        """
        chars       = self.registry.get_active_characters()
        recent_hist = self.timeline.to_narrative_context(last_n=5)
        lore_rules  = self.lore.get_rules_context()

        return {
            "run_id":         self._current_run,
            "project":        self.project_name,
            "characters":     [c.to_prompt_context() for c in chars[:8]],
            "recent_history": recent_hist,
            "lore_rules":     lore_rules,
            "world_state":    self.tracker.get_world_summary(),
            "n_chars":        len(chars),
        }

    def validate_and_fix_prompt(self, prompt: str) -> dict:
        """Valide un prompt et corrige les contradictions."""
        check  = self.guard.check_prompt(prompt, self._current_run)
        if check["has_issues"]:
            fixed = self.guard.auto_fix_prompt(prompt, check["issues"])
            return {
                "original": prompt,
                "fixed":    fixed,
                "modified": fixed != prompt,
                "issues":   check["issues"],
            }
        return {"original": prompt, "fixed": prompt,
                "modified": False, "issues": []}

    def record_run_events(self, events: list[dict]) -> list:
        """Enregistre les événements d'un run dans la timeline."""
        recorded = []
        for evt in events:
            e = self.timeline.record(
                run_id=self._current_run,
                title=evt.get("title","Événement"),
                description=evt.get("description",""),
                entities=evt.get("entities",[]),
                impact=evt.get("impact","minor"),
            )
            recorded.append(e)
        return recorded

    def update_character(self, name: str, **changes) -> Optional[Entity]:
        """Met à jour l'état d'un personnage."""
        char = self.registry.find_by_name(name)
        if char:
            return self.registry.update(char.id, self._current_run, **changes)
        return None

    def end_run(self, notes: str = "") -> dict:
        """Finalise un run et prend un snapshot du monde."""
        snapshot = self.tracker.snapshot(
            self._current_run, self.registry, self.timeline, notes
        )
        self._current_run += 1
        return snapshot

    def initialize_universe(self, universe_brief: str) -> dict:
        """
        Initialise un nouvel univers depuis un brief narratif.
        Utilise le LLM pour extraire les entités et les règles.
        """
        prompt = (
            f"Crée la bible d'un univers créatif à partir de ce brief :\n"
            f"'{universe_brief}'\n\n"
            f"Extrais et structure :\n"
            f"1. 3-5 personnages principaux (nom, description, traits visuels)\n"
            f"2. 2-3 lieux importants\n"
            f"3. 3 règles fondamentales de l'univers\n"
            f"4. Le conflit central\n\n"
            f"Réponds en JSON :\n"
            f'{{"characters":[{{"name":"...","description":"...","visual_tags":["..."]}}],'
            f'"locations":[{{"name":"...","description":""}}],'
            f'"rules":[{{"category":"magie|societe|technologie","name":"...","description":"...","constraints":["..."]}}],'
            f'"central_conflict":"..."}}'
        )
        result = _llm(prompt, max_tokens=1000)
        try:
            if result.startswith("```"):
                result = "\n".join(result.split("\n")[1:-1])
            data = json.loads(result)

            # Enregistrer les personnages
            for char in data.get("characters", []):
                self.registry.register(
                    name=char["name"],
                    entity_type=EntityType.CHARACTER,
                    description=char.get("description",""),
                    visual_tags=char.get("visual_tags",[]),
                    run_id=0,
                )
            # Enregistrer les lieux
            for loc in data.get("locations", []):
                self.registry.register(
                    name=loc["name"],
                    entity_type=EntityType.LOCATION,
                    description=loc.get("description",""),
                    run_id=0,
                )
            # Enregistrer les règles de lore
            for rule in data.get("rules", []):
                self.lore.define_rule(
                    category=rule.get("category","general"),
                    name=rule["name"],
                    description=rule["description"],
                    constraints=rule.get("constraints",[]),
                )
            # Événement fondateur
            self.timeline.record(
                run_id=0,
                title="Création de l'univers",
                description=data.get("central_conflict",""),
                impact="catastrophic",
            )
            self.log.info(
                f"[WORLD] Univers initialisé : "
                f"{len(data.get('characters',[]))} perso | "
                f"{len(data.get('locations',[]))} lieux | "
                f"{len(data.get('rules',[]))} règles"
            )
            return data
        except Exception as e:
            self.log.error(f"[WORLD] Init univers : {e}")
            return {}

    def get_injection_prompt(self) -> str:
        """
        Génère le bloc de texte à injecter dans TOUS les system prompts.
        C'est ce qui rend tous les agents conscients de l'état du monde.
        """
        ctx   = self.get_context_for_run()
        chars = "\n".join(f"  - {c}" for c in ctx["characters"][:5])
        return (
            f"\n\n=== ÉTAT DU MONDE (Run {ctx['run_id']}) ===\n"
            f"Projet : {ctx['project']}\n"
            f"Personnages actifs :\n{chars}\n"
            f"Histoire récente :\n{ctx['recent_history']}\n"
            f"Règles de l'univers :\n{ctx['lore_rules'][:300]}\n"
            f"=== FIN ÉTAT DU MONDE ==="
        )

    def get_dashboard(self) -> dict:
        chars = self.registry.get_all()
        return {
            "project":          self.project_name,
            "current_run":      self._current_run,
            "total_entities":   len(chars),
            "alive_characters": len([c for c in chars
                                      if c.type==EntityType.CHARACTER
                                      and c.status==EntityStatus.ALIVE]),
            "total_events":     len(self.timeline._events),
            "lore_rules":       sum(len(v) for v in self.lore._rules.values()),
            "violations":       self.guard.get_violation_report()["total_violations"],
            "world_summary":    self.tracker.get_world_summary(),
        }


# ── Manager multi-projets ──────────────────────────────────────────────
_worlds: dict[str, WorldModel] = {}

def get_world(project_name: str = "default",
               logger: logging.Logger = None) -> WorldModel:
    """Retourne ou crée un WorldModel pour un projet."""
    if project_name not in _worlds:
        _worlds[project_name] = WorldModel(project_name, logger)
    return _worlds[project_name]


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    log = logging.getLogger("world_test")

    world = WorldModel("dragon_ball_test", log)

    print("=== TEST WORLD MODEL V1.30 ===\n")

    # Initialiser l'univers
    brief = (
        "Un guerrier nommé Kael possède un pouvoir ancestral qu'il ne maîtrise pas encore. "
        "Il voyage dans un monde post-apocalyptique où la magie est interdite par l'Empire. "
        "Son but : retrouver sa soeur disparue et renverser le tyran."
    )
    data = world.initialize_universe(brief)
    if data:
        print(f"Univers créé : {len(data.get('characters',[]))} personnages")
        for c in data.get('characters',[])[:3]:
            print(f"  • {c['name']}: {c.get('description','')[:60]}")

    # Simuler un run
    ctx = world.start_run(run_id=1)
    print(f"\nContexte Run 1 : {ctx['n_chars']} personnages actifs")

    # Valider un prompt
    test_prompt = "Kael avec les cheveux blonds combat dans la ville de Solaris"
    result = world.validate_and_fix_prompt(test_prompt)
    print(f"\nValidation prompt :")
    print(f"  Issues : {len(result['issues'])}")
    print(f"  Modifié : {result['modified']}")

    # Dashboard
    dash = world.get_dashboard()
    print(f"\nDashboard : {dash}")

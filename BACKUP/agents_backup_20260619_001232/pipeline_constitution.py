"""
agents/pipeline_constitution.py — Constitution OverLord
L'ADN du pipeline — équivalent de mes valeurs et règles constitutionnelles.

Chez Claude, une "constitution" guide TOUTES mes réponses de façon cohérente,
peu importe quelle tête d'attention est active. OverLord aura la même chose :
des valeurs partagées que TOUS les agents appliquent, et un mécanisme de
résolution de conflits quand deux agents sont en désaccord.

Structure inspirée de l'alignment de Claude :
  - Valeurs fondamentales (hiérarchisées)
  - Règles de qualité non-négociables
  - Protocoles de résolution de conflits
  - Seuils de décision
  - Personnalité du pipeline
"""

import json
import logging
import requests
from pathlib import Path
from datetime import datetime
from dataclasses import dataclass, field
from typing import Optional
from enum import Enum

CONSTITUTION_FILE = Path("workspace/constitution.json")
CONFLICTS_LOG     = Path("workspace/conflicts.json")
ANTHROPIC_URL     = "https://api.anthropic.com/v1/messages"
CLAUDE_MODEL      = "claude-sonnet-4-6"


class Priority(Enum):
    ABSOLUTE   = 0   # jamais violé, quoi qu'il arrive
    CRITIQUE   = 1   # violé uniquement en cas d'urgence système
    HAUTE      = 2   # fortement préféré
    NORMALE    = 3   # guideline standard
    OPTIONNELLE = 4  # si les ressources le permettent


@dataclass
class ConstitutionalRule:
    id:          str
    title:       str
    description: str
    priority:    Priority
    applies_to:  list[str]   # ["all"] ou ["sourcing", "storyboard"...]
    metric:      str = ""    # comment mesurer le respect
    violation_action: str = "warn"  # warn / block / reject / escalate


@dataclass
class ConflictResolution:
    """Résultat d'une résolution de conflit entre agents."""
    agent_a:    str
    agent_b:    str
    key:        str
    value_a:    object
    value_b:    object
    winner:     str
    resolution: str
    method:     str   # "rule", "confidence", "llm", "human"
    reasoning:  str = ""


class PipelineConstitution:
    """
    La Constitution d'OverLord.
    Analogue à ma propre hiérarchie de valeurs :
      1. Sécurité (ne pas casser le système)
      2. Cohérence (ne pas se contredire)
      3. Qualité (produire le meilleur résultat)
      4. Efficacité (utiliser les ressources intelligemment)
      5. Créativité (innover dans le cadre des règles)
    """

    # ─── VALEURS FONDAMENTALES (immuables) ───────────────────────────
    CORE_VALUES = {
        "stabilité":    "Le pipeline ne doit jamais crasher sans sauvegarde d'état",
        "cohérence":    "Un personnage, un style, un univers doivent rester cohérents",
        "qualité":      "Aucun output sous le seuil de qualité ne quitte le pipeline",
        "transparence": "Chaque décision doit être traçable et explicable",
        "progression":  "Le pipeline doit apprendre de chaque run",
    }

    # ─── RÈGLES CONSTITUTIONNELLES ───────────────────────────────────
    DEFAULT_RULES: list[ConstitutionalRule] = [

        # ABSOLUES
        ConstitutionalRule(
            id="CONST-001",
            title="Sauvegarde avant toute action destructive",
            description="Tout agent doit sauvegarder l'état courant avant de modifier, "
                        "supprimer ou remplacer un fichier ou un paramètre critique.",
            priority=Priority.ABSOLUTE,
            applies_to=["all"],
            metric="checkpoint_exists_before_action",
            violation_action="block",
        ),
        ConstitutionalRule(
            id="CONST-002",
            title="Cohérence des personnages",
            description="Un personnage défini dans le scénario doit avoir les mêmes "
                        "caractéristiques visuelles dans TOUS les shots. "
                        "L'agent production NE PEUT PAS modifier les tags d'un personnage "
                        "sans validation du storyboard.",
            priority=Priority.ABSOLUTE,
            applies_to=["production", "storyboard", "postprod"],
            metric="character_consistency_score >= 0.85",
            violation_action="reject",
        ),
        ConstitutionalRule(
            id="CONST-003",
            title="Seuil de qualité minimum",
            description=f"Aucune image avec un score qualité < 60/100 ne peut passer "
                        f"en post-production sans validation humaine explicite.",
            priority=Priority.CRITIQUE,
            applies_to=["production", "critic"],
            metric="quality_score >= 60",
            violation_action="escalate",
        ),

        # HAUTE PRIORITÉ
        ConstitutionalRule(
            id="CONST-004",
            title="Respect du mood audio dans les visuels",
            description="Si le sourcing multi-sensoriel a identifié un mood audio dominant, "
                        "le storyboard et la production DOIVENT l'intégrer dans les paramètres "
                        "visuels (palette, énergie, composition).",
            priority=Priority.HAUTE,
            applies_to=["storyboard", "production"],
            metric="audio_mood_reflected_in_visual_tags",
            violation_action="warn",
        ),
        ConstitutionalRule(
            id="CONST-005",
            title="Priorité au feedback humain",
            description="Les préférences humaines explicites (via human_feedback.py) "
                        "ont priorité sur les paramètres appris automatiquement par l'agent. "
                        "Un humain dit 'évite le rouge' → aucun agent ne génère de rouge.",
            priority=Priority.HAUTE,
            applies_to=["all"],
            metric="human_prefs_applied",
            violation_action="block",
        ),
        ConstitutionalRule(
            id="CONST-006",
            title="Trace de raisonnement obligatoire",
            description="Chaque décision impactante (choix de LoRA, prompt, angle caméra) "
                        "doit être accompagnée d'un raisonnement en 1-2 phrases "
                        "accessible via thought_chain.",
            priority=Priority.HAUTE,
            applies_to=["storyboard", "production", "critic"],
            metric="thought_chain_entry_exists",
            violation_action="warn",
        ),

        # NORMALES
        ConstitutionalRule(
            id="CONST-007",
            title="Diversité des angles de caméra",
            description="Un épisode ne doit pas contenir plus de 40% de shots avec "
                        "le même angle (éviter la monotonie visuelle).",
            priority=Priority.NORMALE,
            applies_to=["storyboard"],
            metric="angle_diversity_score >= 0.6",
            violation_action="warn",
        ),
        ConstitutionalRule(
            id="CONST-008",
            title="Équilibre GPU/CPU",
            description="Les tâches CPU légères (sourcing, scénario) ne doivent pas "
                        "bloquer la file GPU. Le scheduler doit maintenir le GPU actif "
                        "à > 70% pendant une production.",
            priority=Priority.NORMALE,
            applies_to=["gpu_scheduler", "production"],
            metric="gpu_utilization >= 0.70",
            violation_action="warn",
        ),
        ConstitutionalRule(
            id="CONST-009",
            title="Archivage systématique",
            description="Tout output (image, vidéo, STL, rapport) doit être archivé "
                        "avec ses métadonnées (paramètres, timestamp, scores) "
                        "dans memory_agent avant suppression du workspace.",
            priority=Priority.NORMALE,
            applies_to=["all"],
            metric="archive_entry_exists",
            violation_action="warn",
        ),
    ]

    def __init__(self, logger: logging.Logger = None):
        self.log     = logger or logging.getLogger("constitution")
        self._rules  = {r.id: r for r in self.DEFAULT_RULES}
        self._conflicts: list[ConflictResolution] = []
        self._custom_prefs: dict = {}   # préférences humaines persistantes
        self._load()

    # ── Validation ───────────────────────────────────────────────────

    def validate(self, agent: str, action: str,
                 context: dict = None) -> dict:
        """
        Valide qu'une action d'un agent respecte la constitution.
        Retourne : {valid, violations, warnings, required_actions}
        """
        context   = context or {}
        violations = []
        warnings   = []
        required   = []

        relevant_rules = [
            r for r in self._rules.values()
            if "all" in r.applies_to or agent in r.applies_to
        ]

        for rule in sorted(relevant_rules, key=lambda r: r.priority.value):
            result = self._check_rule(rule, agent, action, context)
            if result["violated"]:
                if rule.priority in (Priority.ABSOLUTE, Priority.CRITIQUE):
                    violations.append({
                        "rule":    rule.id,
                        "title":   rule.title,
                        "action":  rule.violation_action,
                        "message": result.get("message",""),
                    })
                else:
                    warnings.append({
                        "rule":  rule.id,
                        "title": rule.title,
                        "message": result.get("message",""),
                    })
                if rule.violation_action == "block":
                    required.append(f"BLOQUÉ par {rule.id} : {rule.title}")

        return {
            "valid":    len(violations) == 0,
            "agent":    agent,
            "action":   action,
            "violations": violations,
            "warnings":   warnings,
            "required":   required,
            "timestamp":  datetime.utcnow().isoformat(),
        }

    def _check_rule(self, rule: ConstitutionalRule,
                    agent: str, action: str,
                    context: dict) -> dict:
        """Évalue si une règle est respectée dans ce contexte."""
        # CONST-005 : préférences humaines
        if rule.id == "CONST-005":
            for pref_key, pref_val in self._custom_prefs.items():
                if isinstance(pref_val, dict) and pref_val.get("type") == "avoid":
                    avoided = pref_val.get("value","")
                    prompt  = str(context.get("positive",""))
                    if avoided.lower() in prompt.lower():
                        return {"violated": True,
                                "message": f"Tag interdit détecté : '{avoided}'"}
        # CONST-003 : qualité minimum
        if rule.id == "CONST-003":
            score = context.get("quality_score", 100)
            if score < 60:
                return {"violated": True,
                        "message": f"Score qualité {score} < 60"}
        # Par défaut : pas de violation détectée
        return {"violated": False}

    # ── Résolution de conflits ────────────────────────────────────────

    def resolve_conflict(self, agent_a: str, value_a,
                          agent_b: str, value_b,
                          key: str,
                          confidence_a: float = 0.5,
                          confidence_b: float = 0.5) -> ConflictResolution:
        """
        Résout un conflit entre deux agents sur la même valeur.
        Méthodes (par ordre) :
          1. Règles constitutionnelles (une règle dicte la priorité)
          2. Confiance (l'agent plus confiant l'emporte)
          3. LLM arbitrage (si trop proche)
          4. Escalade humaine (si critique)
        """
        self.log.info(
            f"[CONSTITUTION] Conflit : {agent_a}({value_a}) vs "
            f"{agent_b}({value_b}) sur '{key}'"
        )

        # Méthode 1 : règles constitutionnelles
        priority_map = {
            "human_feedback": 10,    # humain > tout
            "critic":         8,
            "watchdog":       7,
            "scenario":       6,
            "storyboard":     5,
            "production":     4,
            "sourcing":       3,
        }
        p_a = priority_map.get(agent_a, 1)
        p_b = priority_map.get(agent_b, 1)

        if abs(p_a - p_b) >= 3:   # différence de priorité significative
            winner  = agent_a if p_a > p_b else agent_b
            value_w = value_a if p_a > p_b else value_b
            res = ConflictResolution(
                agent_a=agent_a, agent_b=agent_b, key=key,
                value_a=value_a, value_b=value_b,
                winner=winner, resolution=str(value_w),
                method="rule",
                reasoning=f"Priorité constitutionnelle : {winner} ({max(p_a,p_b)}) > {min(p_a,p_b)}",
            )
            self._conflicts.append(res)
            return res

        # Méthode 2 : confiance
        if abs(confidence_a - confidence_b) >= 0.2:
            winner  = agent_a if confidence_a > confidence_b else agent_b
            value_w = value_a if confidence_a > confidence_b else value_b
            res = ConflictResolution(
                agent_a=agent_a, agent_b=agent_b, key=key,
                value_a=value_a, value_b=value_b,
                winner=winner, resolution=str(value_w),
                method="confidence",
                reasoning=f"Confiance : {confidence_a:.2f} vs {confidence_b:.2f}",
            )
            self._conflicts.append(res)
            return res

        # Méthode 3 : LLM arbitrage
        reasoning = self._llm_arbitrate(
            agent_a, value_a, agent_b, value_b, key
        )
        winner  = agent_a  # default en cas d'échec LLM
        value_w = value_a
        if reasoning and agent_b in reasoning.lower():
            winner  = agent_b
            value_w = value_b
        elif reasoning and "combine" in reasoning.lower():
            value_w = f"{value_a} + {value_b}"
            winner  = "consensus"

        res = ConflictResolution(
            agent_a=agent_a, agent_b=agent_b, key=key,
            value_a=value_a, value_b=value_b,
            winner=winner, resolution=str(value_w),
            method="llm", reasoning=reasoning or "LLM indisponible",
        )
        self._conflicts.append(res)
        self._save_conflicts()
        return res

    def _llm_arbitrate(self, agent_a, val_a, agent_b, val_b, key) -> str:
        prompt = (
            f"Deux agents IA sont en désaccord sur la valeur de '{key}' :\n"
            f"  {agent_a} propose : '{val_a}'\n"
            f"  {agent_b} propose : '{val_b}'\n\n"
            f"En tant qu'arbitre constitutionnel d'OverLord Pipeline, "
            f"choisis quelle valeur adopter en 1 phrase. "
            f"Justifie en termes de cohérence narrative et qualité visuelle."
        )
        try:
            resp = requests.post(
                ANTHROPIC_URL,
                headers={"Content-Type": "application/json"},
                json={"model": CLAUDE_MODEL, "max_tokens": 150,
                      "messages": [{"role":"user","content":prompt}]},
                timeout=20
            )
            if resp.status_code == 200:
                return resp.json()["content"][0]["text"].strip()
        except Exception:
            pass
        return ""

    # ── Préférences humaines ─────────────────────────────────────────

    def set_preference(self, key: str, value,
                        pref_type: str = "prefer"):
        """
        Enregistre une préférence humaine dans la constitution.
        Ces préférences ont priorité absolue sur les agents.

        pref_type : "prefer" | "avoid" | "require" | "forbid"
        """
        self._custom_prefs[key] = {
            "value":    value,
            "type":     pref_type,
            "set_at":   datetime.utcnow().isoformat(),
        }
        self._save()
        self.log.info(f"[CONSTITUTION] Préférence : {pref_type} '{key}' = {value}")

    def get_active_preferences(self) -> dict:
        return dict(self._custom_prefs)

    def get_system_prompt_extension(self, agent_role: str) -> str:
        """
        Retourne les directives constitutionnelles à ajouter
        au system_prompt d'un agent — comme mes guidelines dans chaque réponse.
        """
        relevant_rules = [
            r for r in self._rules.values()
            if "all" in r.applies_to or agent_role in r.applies_to
        ]
        rules_text = "\n".join(
            f"[{r.priority.name}] {r.title} : {r.description[:100]}"
            for r in sorted(relevant_rules, key=lambda r: r.priority.value)[:5]
        )
        prefs_text = "\n".join(
            f"PRÉFÉRENCE HUMAINE : {k} = {v['type']} '{v['value']}'"
            for k, v in self._custom_prefs.items()
        )
        return (
            f"\n\n=== CONSTITUTION OVERLORD ===\n"
            f"Valeurs : {', '.join(self.CORE_VALUES.keys())}\n"
            f"Règles applicables :\n{rules_text}\n"
            + (f"\nPréférences humaines (PRIORITÉ ABSOLUE) :\n{prefs_text}" if prefs_text else "")
            + "\n=== FIN CONSTITUTION ==="
        )

    # ── Persistance ───────────────────────────────────────────────────

    def _save(self):
        CONSTITUTION_FILE.parent.mkdir(parents=True, exist_ok=True)
        data = {
            "core_values":   self.CORE_VALUES,
            "custom_prefs":  self._custom_prefs,
            "saved_at":      datetime.utcnow().isoformat(),
        }
        CONSTITUTION_FILE.write_text(
            json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8"
        )

    def _save_conflicts(self):
        data = [
            {"agent_a": c.agent_a, "agent_b": c.agent_b,
             "key": c.key, "winner": c.winner,
             "method": c.method, "reasoning": c.reasoning}
            for c in self._conflicts[-100:]
        ]
        CONFLICTS_LOG.write_text(
            json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8"
        )

    def _load(self):
        if CONSTITUTION_FILE.exists():
            try:
                data = json.loads(CONSTITUTION_FILE.read_text(encoding="utf-8"))
                self._custom_prefs = data.get("custom_prefs", {})
            except Exception:
                pass


# ── Singleton ─────────────────────────────────────────────────────────
_constitution: Optional[PipelineConstitution] = None

def get_constitution(logger=None) -> PipelineConstitution:
    global _constitution
    if _constitution is None:
        _constitution = PipelineConstitution(logger)
    return _constitution


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    log = logging.getLogger("const_test")

    const = PipelineConstitution(log)
    print("=== CONSTITUTION OVERLORD ===")
    print(f"Valeurs : {list(const.CORE_VALUES.keys())}")
    print(f"Règles  : {len(const._rules)}")
    print()

    # Test validation
    result = const.validate("production", "generate_image", {"quality_score": 45})
    print(f"Validation score=45 : valid={result['valid']}")
    for v in result["violations"]:
        print(f"  VIOLATION : {v['rule']} — {v['title']}")

    # Test préférence humaine
    const.set_preference("couleur_interdite", "rouge_criard", pref_type="avoid")
    result2 = const.validate("production", "generate_image",
                              {"positive": "red background, vibrant red"})
    print(f"\nValidation avec rouge : valid={result2['valid']}")

    # Test résolution de conflit
    res = const.resolve_conflict(
        "storyboard", "angle_dramatique_bas",
        "production",  "angle_neutre",
        "camera_angle",
        confidence_a=0.7, confidence_b=0.6
    )
    print(f"\nConflit résolu : winner={res.winner} | méthode={res.method}")
    print(f"  Raisonnement : {res.reasoning[:80]}")

    # Extension système
    ext = const.get_system_prompt_extension("storyboard")
    print(f"\nExtension système (storyboard) :\n{ext[:300]}")

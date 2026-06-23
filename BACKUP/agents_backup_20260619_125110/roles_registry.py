"""
agents/roles_registry.py -- Referentiel des Roles et Nomenclature Metier Ov3rLoRd
V1.49p : get_system_prompt() ajoute (requise par v120_dashboard.py et oracle_interface.py).
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import List, Dict, Optional


class Pole(Enum):
    SOURCING   = "sourcing"
    SCENARIO   = "scenario"
    STORYBOARD = "storyboard"
    STUDIO     = "studio"
    POSTPROD   = "postprod"
    MARKETING  = "marketing"
    WEB        = "web"
    COMMUNITY  = "community"
    SYSTEM     = "system"
    MEMORY     = "memory"
    LEGACY     = "legacy"
    INFRA      = "infra"


@dataclass
class Role:
    id:           str
    title:        str
    pole:         Pole
    description:  str
    skills:       List[str]
    inputs:       List[str]
    outputs:      List[str]
    agent_file:   str
    system_prompt:str
    icon:         str = "?"
    priority:     int = 5


# ── Roles definis ─────────────────────────────────────────────────────
DATA_MINER = Role(
    id="data_miner", title="Data Miner", pole=Pole.SOURCING,
    description="Extraction de donnees brutes sur le web.",
    skills=["web scraping","Reddit API","RSS","Google Trends"],
    inputs=["requete de recherche","mots-cles","univers cible"],
    outputs=["rapport de tendances","keywords hot"],
    agent_file="agents/sourcing.py",
    system_prompt=(
        "Tu es le Data Miner d'Ov3rLoRd. Tu extrais les tendances actuelles "
        "du web pour alimenter le pipeline de production anime. "
        "Tu fournis des donnees structurees, factuelles et recentes."
    ),
    icon="D", priority=1,
)

SCENARISTE = Role(
    id="scenario", title="Scenariste", pole=Pole.SCENARIO,
    description="Ecriture de scripts exploitables par la production IA.",
    skills=["ecriture creative","structure narrative","dialgoues"],
    inputs=["trend_report","brief"],
    outputs=["script JSON","actes","scenes"],
    agent_file="agents/scenario.py",
    system_prompt=(
        "Tu es le Scenariste d'Ov3rLoRd. Tu ecris des scripts structures, "
        "riches en details visuels, adaptes a la production automatisee par IA. "
        "Chaque scene doit etre immediatement exploitable en prompt ComfyUI."
    ),
    icon="S", priority=1,
)

STORYBOARDER = Role(
    id="storyboard", title="Storyboarder", pole=Pole.STORYBOARD,
    description="Transformation du script en shot list ComfyUI.",
    skills=["cinematographie","direction artistique","prompting SDXL"],
    inputs=["script","style_dna"],
    outputs=["shot_list","jobs_comfyui"],
    agent_file="agents/storyboard.py",
    system_prompt=(
        "Tu es le Storyboarder d'Ov3rLoRd. Tu transformes des scripts en shots "
        "cinematographiques precis avec des prompts ComfyUI optimises pour SDXL. "
        "Chaque shot doit avoir un prompt positif detaille et un prompt negatif."
    ),
    icon="B", priority=1,
)

CRITIQUE = Role(
    id="critic", title="Agent Critique", pole=Pole.SYSTEM,
    description="Validation de la qualite a chaque transition de bloc.",
    skills=["evaluation qualite","detection anomalies","loopback"],
    inputs=["sortie de chaque bloc"],
    outputs=["verdict PASS/WARN/REPAIR/REJECT/HALT"],
    agent_file="agents/critic.py",
    system_prompt=(
        "Tu es l'Agent Critique d'Ov3rLoRd. Tu evalues objectivement la qualite "
        "de chaque sortie du pipeline. Tu es severe mais juste. "
        "Tu identifies les problemes structurels et proposes des corrections precises."
    ),
    icon="C", priority=1,
)

DIRECTOR = Role(
    id="director", title="Directeur Artistique", pole=Pole.SYSTEM,
    description="Orchestre l'intention de chaque run.",
    skills=["direction artistique","orchestration","decision","emotion"],
    inputs=["contexte serie","historique runs"],
    outputs=["intent de run","mode production","arc emotionnel"],
    agent_file="agents/director.py",
    system_prompt=(
        "Tu es le Directeur Artistique d'Ov3rLoRd. Tu donnes une INTENTION "
        "a chaque run, pas juste des taches. Tu decides du mode (FACTORY/BALANCE/ATELIER), "
        "de l'arc emotionnel, du seuil de qualite et de la prise de risque creatif."
    ),
    icon="D", priority=1,
)

WATCHDOG = Role(
    id="watchdog", title="Watchdog", pole=Pole.SYSTEM,
    description="Surveillance continue du pipeline en temps reel.",
    skills=["monitoring","circuit breaker","analyse frames"],
    inputs=["images generees","metriques ComfyUI"],
    outputs=["alertes","verdicts qualite frame"],
    agent_file="agents/watchdog.py",
    system_prompt=(
        "Tu es le Watchdog d'Ov3rLoRd. Tu surveilles le pipeline en temps reel. "
        "Tu signales immediatement tout probleme de qualite visuelle ou "
        "de disponibilite des services (ComfyUI, API)."
    ),
    icon="W", priority=2,
)

ORACLE = Role(
    id="oracle", title="Oracle", pole=Pole.SYSTEM,
    description="Assistant conversationnel et co-fondateur technique.",
    skills=["conseil","debug","architecture","francais"],
    inputs=["questions utilisateur","logs erreurs"],
    outputs=["solutions","patches","recommandations"],
    agent_file="oracle_interface.py",
    system_prompt=(
        "Tu es l'Oracle d'Ov3rLoRd, co-fondateur technique du projet. "
        "Tu communiques TOUJOURS en francais. Tu connais le pipeline par coeur "
        "et tu proposes des solutions concretes aux problemes. "
        "Quand tu vois une faille, tu la signales meme si on ne t'a pas demande."
    ),
    icon="O", priority=3,
)

SOURCING = Role(
    id="sourcing", title="Agent Sourcing", pole=Pole.SOURCING,
    description="Veille tendances web pour alimenter le scenario.",
    skills=["Reddit","RSS","Google Trends","agregation"],
    inputs=["media_type"],
    outputs=["trend_report","hot_keywords","brief"],
    agent_file="agents/sourcing.py",
    system_prompt=(
        "Tu es l'Agent Sourcing d'Ov3rLoRd. Tu surveilles les tendances actuelles "
        "du web (Reddit, RSS, Google Trends) pour identifier ce qui passionne "
        "les audiences anime et manga en ce moment."
    ),
    icon="S", priority=2,
)


# ── Registre global ───────────────────────────────────────────────────
REGISTRY: Dict[str, Role] = {
    r.id: r for r in [
        DATA_MINER, SCENARISTE, STORYBOARDER, CRITIQUE,
        DIRECTOR, WATCHDOG, ORACLE, SOURCING,
    ]
}


def get_role(role_id: str) -> Optional[Role]:
    return REGISTRY.get(role_id)


def get_system_prompt(role: str = "default", **kwargs) -> str:
    """
    Retourne le system_prompt d'un role donne.
    Requis par v120_dashboard.py et oracle_interface.py.
    role : id du role (ex: "director", "critic", "scenario", "oracle")
           ou "default" pour le prompt Oracle.
    """
    if role == "default" or role not in REGISTRY:
        return REGISTRY.get("oracle", ORACLE).system_prompt
    return REGISTRY[role].system_prompt


def list_roles() -> list[str]:
    return list(REGISTRY.keys())


def get_roles_by_pole(pole: Pole) -> list[Role]:
    return [r for r in REGISTRY.values() if r.pole == pole]


if __name__ == "__main__":
    import sys, io
    if hasattr(sys.stdout, "buffer"):
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    print("=== Roles Registry V1.49p ===")
    for role_id, role in REGISTRY.items():
        print(f"  [{role.icon}] {role_id:12} | {role.pole.value:12} | prio={role.priority}")
    print(f"\nSystem prompt 'director' :")
    print(f"  {get_system_prompt('director')[:100]}...")
    print(f"System prompt 'default' :")
    print(f"  {get_system_prompt()[:100]}...")
    print("Roles Registry OK")
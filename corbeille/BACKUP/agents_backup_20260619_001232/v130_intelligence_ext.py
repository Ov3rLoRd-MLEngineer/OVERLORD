"""
agents/v130_intelligence_ext.py — OverLord V1.30 — Intelligence Étendue

4 modules complémentaires réunis :

1. Creative Fatigue Detection  — briser les patterns répétitifs automatiquement
2. Hivemind Protocol           — apprentissage fédéré inter-instances
3. Audience Simulation         — tester avant de publier
4. Inspiration Injection       — références cross-domaines inattendues
"""

import json
import math
import time
import random
import hashlib
import logging
import threading
from pathlib import Path
from datetime import datetime
from dataclasses import dataclass, field
from typing import Optional
import requests

INTEL_EXT_DIR = Path("workspace/intelligence_ext")
ANTHROPIC_URL = "https://api.anthropic.com/v1/messages"
CLAUDE_MODEL  = "claude-sonnet-4-6"


def _llm(prompt: str, system: str = "", max_tokens: int = 400) -> str:
    try:
        body = {"model": CLAUDE_MODEL, "max_tokens": max_tokens,
                "messages": [{"role": "user", "content": prompt}]}
        if system:
            body["system"] = system
        r = requests.post(ANTHROPIC_URL,
                          headers={"Content-Type": "application/json"},
                          json=body, timeout=25)
        if r.status_code == 200:
            return r.json()["content"][0]["text"].strip()
    except Exception:
        pass
    return ""


# ══════════════════════════════════════════════════════════════════════
# 1. CREATIVE FATIGUE DETECTION
# ══════════════════════════════════════════════════════════════════════

class CreativeFatigueDetector:
    """
    Détecte quand le pipeline se répète et force l'innovation.

    Mesure l'entropie des outputs : si les dernières images partagent
    trop de tags communs, le pipeline est en "fatigue créative".

    Actions automatiques :
    - MILD   : injecter 2-3 tags inattendus dans le prochain prompt
    - MEDIUM : switcher vers un sampler/style rarement utilisé
    - SEVERE : forcer une rupture complète de style
    """

    FATIGUE_THRESHOLDS = {
        "healthy":    0.7,   # entropie > 0.7 → diversité normale
        "mild":       0.5,   # 0.5-0.7 → légère répétition
        "medium":     0.35,  # 0.35-0.5 → fatigue notable
        "severe":     0.0,   # < 0.35 → fatigue sévère
    }

    # Tags de rupture par catégorie
    DISRUPTION_TAGS = {
        "style":      ["watercolor aesthetic","oil painting style","sketch art",
                        "pixel art elements","low poly","impressionist"],
        "lighting":   ["neon noir","bioluminescent","golden hour", "moonlit",
                        "candlelight","harsh fluorescent","northern lights"],
        "composition":["dutch angle extreme","birds eye view","fisheye lens",
                        "silhouette only","negative space dominant","split screen"],
        "mood":       ["surreal dreamscape","hyper realistic","minimalist",
                        "psychedelic","vaporwave","brutalist"],
        "unexpected": ["underwater scene","zero gravity","microscopic scale",
                        "architectural ruins","forest spirits","desert mirage"],
    }

    def __init__(self, window_size: int = 10, logger: logging.Logger = None):
        self.log         = logger or logging.getLogger("fatigue")
        self.window_size = window_size
        self._prompt_history: list[list[str]] = []   # historique des tags
        self._fatigue_history: list[float]    = []
        INTEL_EXT_DIR.mkdir(parents=True, exist_ok=True)

    def record_prompt(self, prompt: str):
        """Enregistre les tags d'un prompt généré."""
        tags = [t.strip().lower() for t in prompt.split(",") if t.strip()]
        self._prompt_history.append(tags)
        if len(self._prompt_history) > self.window_size:
            self._prompt_history.pop(0)

    def compute_entropy(self) -> float:
        """
        Mesure l'entropie (diversité) des derniers prompts.
        1.0 = parfaite diversité | 0.0 = tous identiques
        """
        if len(self._prompt_history) < 3:
            return 1.0

        # Compter la fréquence de chaque tag
        all_tags:  list = []
        for tags in self._prompt_history:
            all_tags.extend(tags)

        if not all_tags:
            return 1.0

        freq: dict[str, int] = {}
        for t in all_tags:
            freq[t] = freq.get(t, 0) + 1

        total = len(all_tags)
        probs = [c/total for c in freq.values()]
        # Entropie de Shannon normalisée
        entropy = -sum(p * math.log2(p) for p in probs if p > 0)
        max_entropy = math.log2(len(freq)) if len(freq) > 1 else 1
        return entropy / max_entropy if max_entropy > 0 else 1.0

    def get_fatigue_level(self) -> tuple[str, float]:
        """Retourne le niveau de fatigue et le score d'entropie."""
        entropy = self.compute_entropy()
        self._fatigue_history.append(entropy)

        for level in ["severe","medium","mild","healthy"]:
            if entropy >= self.FATIGUE_THRESHOLDS[level]:
                return level, entropy
        return "severe", entropy

    def get_disruption(self, level: str) -> dict:
        """Retourne les éléments de rupture selon le niveau de fatigue."""
        if level == "mild":
            # Injecter 2 tags inattendus
            category = random.choice(list(self.DISRUPTION_TAGS.keys()))
            tags = random.sample(self.DISRUPTION_TAGS[category], 2)
            return {
                "level":    level,
                "action":   "inject_tags",
                "tags":     tags,
                "message":  f"Diversification douce : ajout de {tags}",
            }
        elif level == "medium":
            # Changer le style principal
            new_style = random.choice(self.DISRUPTION_TAGS["style"])
            new_light = random.choice(self.DISRUPTION_TAGS["lighting"])
            return {
                "level":    level,
                "action":   "style_shift",
                "new_style":    new_style,
                "new_lighting": new_light,
                "message":  f"Shift de style : {new_style} + {new_light}",
            }
        else:  # severe
            # Rupture complète
            all_disruptors = []
            for tags in self.DISRUPTION_TAGS.values():
                all_disruptors.extend(tags)
            radical_tags = random.sample(all_disruptors, 4)
            return {
                "level":    level,
                "action":   "radical_break",
                "radical_tags": radical_tags,
                "message":  f"RUPTURE CRÉATIVE : {radical_tags}",
            }

    def apply_disruption(self, prompt: str) -> tuple[str, dict]:
        """
        Applique automatiquement la disruption nécessaire au prompt.
        Retourne le prompt modifié et les infos de disruption.
        """
        level, entropy = self.get_fatigue_level()
        if level == "healthy":
            return prompt, {"level": "healthy", "entropy": entropy, "action": "none"}

        disruption = self.get_disruption(level)
        self.log.info(f"[FATIGUE] Niveau={level} entropy={entropy:.3f} | {disruption['message']}")

        if disruption["action"] == "inject_tags":
            new_prompt = ", ".join(disruption["tags"]) + ", " + prompt
        elif disruption["action"] == "style_shift":
            new_prompt = (f"{disruption['new_style']}, {disruption['new_lighting']}, "
                          + ", ".join(t for t in prompt.split(",")
                                      if "style" not in t and "lighting" not in t
                                      and t.strip())[:300])
        else:  # radical_break
            new_prompt = (", ".join(disruption["radical_tags"]) + ", " +
                          ", ".join(prompt.split(",")[:4]))

        disruption["entropy"] = entropy
        return new_prompt.strip(", "), disruption

    def get_report(self) -> dict:
        level, entropy = self.get_fatigue_level()
        return {
            "current_entropy": round(entropy, 4),
            "fatigue_level":   level,
            "history_length":  len(self._prompt_history),
            "avg_entropy":     round(
                sum(self._fatigue_history) / max(len(self._fatigue_history),1), 4
            ),
        }


# ══════════════════════════════════════════════════════════════════════
# 2. HIVEMIND PROTOCOL
# ══════════════════════════════════════════════════════════════════════

class HivemindProtocol:
    """
    Protocole Hivemind — apprentissage fédéré entre instances OverLord.

    Plusieurs instances OverLord (tes machines, bêta-testeurs) partagent
    leurs DÉCOUVERTES sans partager leurs données privées.

    Principe du Federated Learning :
    - Chaque instance entraîne son modèle localement
    - Elle partage uniquement les "deltas" (ce qu'elle a appris)
    - Le serveur agrège les deltas → meilleure politique globale
    - Toutes les instances bénéficient de l'apprentissage de toutes

    Implémentation légère : partage de "knowledge vectors" via HTTP.
    """

    def __init__(self, node_id: str = None, server_url: str = "",
                 logger: logging.Logger = None):
        self.log       = logger or logging.getLogger("hivemind")
        self.node_id   = node_id or hashlib.md5(
            str(time.time()).encode()
        ).hexdigest()[:8]
        self.server_url = server_url   # URL du serveur d'agrégation
        self._local_knowledge: dict = {}   # connaissances locales
        self._shared_pool:     dict = {}   # connaissances reçues du réseau
        INTEL_EXT_DIR.mkdir(parents=True, exist_ok=True)
        self._load()

    def learn(self, key: str, value: float, confidence: float = 0.7):
        """Enregistre une connaissance locale."""
        self._local_knowledge[key] = {
            "value":      value,
            "confidence": confidence,
            "updated_at": time.time(),
            "source":     self.node_id,
        }

    def get_knowledge(self, key: str) -> float:
        """
        Retourne la meilleure valeur connue (locale + réseau).
        Pondérée par la confiance.
        """
        candidates = []
        if key in self._local_knowledge:
            k = self._local_knowledge[key]
            candidates.append((k["value"], k["confidence"]))
        if key in self._shared_pool:
            for entry in self._shared_pool[key]:
                candidates.append((entry["value"], entry["confidence"]))

        if not candidates:
            return 0.5   # valeur par défaut

        total_w = sum(c for _, c in candidates)
        if total_w == 0:
            return candidates[0][0]
        return sum(v*c for v,c in candidates) / total_w

    def push_to_network(self) -> dict:
        """
        Pousse les connaissances locales vers le réseau hivemind.
        Ne partage pas les données brutes — uniquement les "deltas".
        """
        if not self.server_url:
            self.log.debug("[HIVEMIND] Pas de serveur configuré — mode local")
            return {"pushed": 0}

        # Filtrer les connaissances à haute confiance
        to_share = {
            k: v for k, v in self._local_knowledge.items()
            if v["confidence"] >= 0.75
        }
        try:
            r = requests.post(
                f"{self.server_url}/api/hivemind/push",
                json={"node_id": self.node_id, "knowledge": to_share},
                timeout=10
            )
            if r.status_code == 200:
                self.log.info(f"[HIVEMIND] {len(to_share)} connaissances partagées")
                return {"pushed": len(to_share)}
        except Exception as e:
            self.log.debug(f"[HIVEMIND] Push échoué : {e}")
        return {"pushed": 0}

    def pull_from_network(self) -> dict:
        """Récupère les connaissances agrégées du réseau."""
        if not self.server_url:
            return {"pulled": 0}
        try:
            r = requests.get(
                f"{self.server_url}/api/hivemind/pull",
                params={"node_id": self.node_id},
                timeout=10
            )
            if r.status_code == 200:
                pool = r.json().get("knowledge_pool", {})
                self._shared_pool.update(pool)
                self._save()
                self.log.info(f"[HIVEMIND] {len(pool)} connaissances reçues")
                return {"pulled": len(pool)}
        except Exception as e:
            self.log.debug(f"[HIVEMIND] Pull échoué : {e}")
        return {"pulled": 0}

    def get_network_insights(self) -> dict:
        """Résumé des insights provenant du réseau."""
        return {
            "local_knowledge":  len(self._local_knowledge),
            "network_pool":     len(self._shared_pool),
            "node_id":          self.node_id,
            "has_server":       bool(self.server_url),
            "top_network_keys": list(self._shared_pool.keys())[:5],
        }

    def _save(self):
        data = {"local": self._local_knowledge, "shared": self._shared_pool}
        (INTEL_EXT_DIR / f"hivemind_{self.node_id}.json").write_text(
            json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8"
        )

    def _load(self):
        f = INTEL_EXT_DIR / f"hivemind_{self.node_id}.json"
        if f.exists():
            try:
                data = json.loads(f.read_text(encoding="utf-8"))
                self._local_knowledge = data.get("local", {})
                self._shared_pool     = data.get("shared", {})
            except Exception:
                pass


# ══════════════════════════════════════════════════════════════════════
# 3. AUDIENCE SIMULATION
# ══════════════════════════════════════════════════════════════════════

@dataclass
class AudienceSegment:
    """Un segment d'audience simulé."""
    name:             str
    age_range:        tuple[int, int]
    interests:        list[str]
    platform_prefs:   list[str]
    content_appetite: str    # "binge","casual","selective"
    attention_span_s: int    # durée d'attention en secondes
    emotion_triggers: list[str]   # ce qui les touche
    size_factor:      float = 1.0  # taille relative du segment


# Segments d'audience typiques
DEFAULT_SEGMENTS = [
    AudienceSegment(
        name="Otaku Core", age_range=(16,28),
        interests=["anime","manga","gaming","cosplay"],
        platform_prefs=["YouTube","Twitter/X","Reddit/r/anime"],
        content_appetite="binge", attention_span_s=1200,
        emotion_triggers=["nostalgie","épique","twist narratif","fanservice"],
        size_factor=1.5,
    ),
    AudienceSegment(
        name="Casual Viewer", age_range=(18,35),
        interests=["divertissement","pop culture","réseaux sociaux"],
        platform_prefs=["TikTok","Instagram","YouTube Shorts"],
        content_appetite="casual", attention_span_s=60,
        emotion_triggers=["humour","action rapide","esthétique","clips courts"],
        size_factor=3.0,
    ),
    AudienceSegment(
        name="Anime Purist", age_range=(20,40),
        interests=["anime classique","culture japonaise","critique"],
        platform_prefs=["MAL","Letterboxd","forums spécialisés"],
        content_appetite="selective", attention_span_s=2400,
        emotion_triggers=["qualité narrative","cohérence visuelle","originalité"],
        size_factor=0.8,
    ),
    AudienceSegment(
        name="Gen Z Creator", age_range=(15,24),
        interests=["création de contenu","tendances","IA","tech"],
        platform_prefs=["TikTok","Instagram","YouTube"],
        content_appetite="casual", attention_span_s=45,
        emotion_triggers=["innovation","IA impressionnante","relatable","viral"],
        size_factor=2.5,
    ),
]


class AudienceSimulator:
    """
    Simule comment différentes audiences vont réagir à un contenu.
    Permet de tester AVANT de publier.
    """

    def __init__(self, segments: list = None, logger: logging.Logger = None):
        self.log      = logger or logging.getLogger("audience")
        self.segments = segments or DEFAULT_SEGMENTS

    def simulate(self, content: dict) -> dict:
        """
        Simule l'impact d'un contenu sur toutes les audiences.

        content : {
            "title": str, "type": str, "duration_s": int,
            "style": str, "emotion": str, "tags": list
        }
        """
        results = {}
        for seg in self.segments:
            score = self._score_segment(content, seg)
            results[seg.name] = score

        # Score global pondéré par la taille des segments
        total_weight = sum(s.size_factor for s in self.segments)
        global_score = sum(
            results[s.name]["engagement"] * s.size_factor
            for s in self.segments
        ) / total_weight

        # Générer des recommandations via LLM
        content_str = json.dumps(content, ensure_ascii=False)
        results_str = json.dumps({k:v["engagement"] for k,v in results.items()})
        recommendations = _llm(
            f"Contenu : {content_str[:200]}\n"
            f"Scores par audience : {results_str}\n"
            f"Donne 3 recommandations concrètes pour améliorer l'engagement. "
            f"Max 2 phrases chacune.",
            max_tokens=300
        )
        return {
            "global_score":      round(global_score, 3),
            "by_segment":        results,
            "best_segment":      max(results, key=lambda k: results[k]["engagement"]),
            "worst_segment":     min(results, key=lambda k: results[k]["engagement"]),
            "recommendations":   recommendations,
            "publish_ready":     global_score >= 0.65,
        }

    def _score_segment(self, content: dict, seg: AudienceSegment) -> dict:
        """Score un contenu pour un segment d'audience."""
        content_tags = [t.lower() for t in content.get("tags", [])]
        content_dur  = content.get("duration_s", 60)
        content_emo  = content.get("emotion", "")
        content_style= content.get("style", "anime")

        # Correspondance intérêts
        interest_match = sum(
            1 for interest in seg.interests
            if any(interest.lower() in tag for tag in content_tags)
        ) / max(len(seg.interests), 1)

        # Correspondance durée/attention span
        if content_dur <= seg.attention_span_s:
            duration_score = 1.0
        else:
            duration_score = max(0, 1 - (content_dur - seg.attention_span_s) / seg.attention_span_s)

        # Correspondance triggers émotionnels
        emotion_match = sum(
            1 for trigger in seg.emotion_triggers
            if trigger.lower() in content_emo.lower() or
               any(trigger.lower() in tag for tag in content_tags)
        ) / max(len(seg.emotion_triggers), 1)

        engagement = (interest_match * 0.4 + duration_score * 0.3 + emotion_match * 0.3)
        engagement = min(1.0, max(0.0, engagement + random.gauss(0, 0.05)))

        return {
            "engagement":      round(engagement, 3),
            "interest_match":  round(interest_match, 3),
            "duration_ok":     content_dur <= seg.attention_span_s,
            "platforms":       seg.platform_prefs[:2],
            "recommendation":  "publier" if engagement > 0.65 else "améliorer",
        }

    def quick_test(self, title: str, style: str = "anime",
                    emotion: str = "epic", tags: list = None) -> dict:
        """Test rapide d'un concept."""
        return self.simulate({
            "title":    title,
            "type":     "anime_short",
            "duration_s": 120,
            "style":    style,
            "emotion":  emotion,
            "tags":     tags or [],
        })


# ══════════════════════════════════════════════════════════════════════
# 4. INSPIRATION INJECTION
# ══════════════════════════════════════════════════════════════════════

class InspirationInjector:
    """
    Injecte des inspirations de domaines inattendus dans le pipeline.

    Un créateur humain s'inspire de tout : architecture, cuisine, musique,
    sport, mode, nature. Pourquoi pas l'IA ?

    Périodiquement, l'IA ingère une référence d'un domaine étranger
    et cherche des connexions avec le projet en cours.

    Résultat : des idées qu'aucun humain seul n'aurait eu.
    """

    INSPIRATION_DOMAINS = {
        "architecture": [
            "Brutalisme soviétique — béton massif, géométrie répétitive",
            "Art déco — symétrie, dorures, verticalité",
            "Architecture organique Gaudí — courbes naturelles, mosaïques",
            "Minimalisme japonais — espace vide, matériaux naturels",
            "Architecture paramétrique — formes impossibles générées par algorithme",
        ],
        "musique": [
            "Jazz modal — improvisation sur des modes, pas des accords",
            "Musique concrète — sons quotidiens transformés en composition",
            "Gamelan indonésien — polyrythmie, harmoniques métalliques",
            "Metal progressif — structures complexes, changements de tempo",
            "Ambient drone — notes tenues, évolution lente",
        ],
        "gastronomie": [
            "Cuisine moléculaire — transformation des textures et des attentes",
            "Fermentation — transformation lente, profondeur de saveur",
            "Fusion asiatique-méditerranéenne — contraste inattendu qui fonctionne",
            "Présentation minimaliste — un élément, beaucoup d'espace",
            "Cuisine de ferme — authenticité, imperfection esthétique",
        ],
        "mode": [
            "Deconstructivism Margiela — coutures apparentes, inachevé volontaire",
            "Streetwear japonais — oversized, layers, couleurs neutres",
            "Haute couture surréaliste — vêtements comme sculpture",
            "Military surplus aesthetics — fonctionnalité devenue style",
        ],
        "nature": [
            "Bioluminescence des profondeurs — lumière dans l'obscurité totale",
            "Formations cristallines — symétrie parfaite de la croissance",
            "Champignons mycelium — réseau invisible, intelligence distribuée",
            "Aurora borealis — lumière qui danse, imprévisible",
            "Murmuration d'étourneaux — intelligence collective, patterns fluides",
        ],
        "sciences": [
            "Fractales — auto-similarité à toutes les échelles",
            "Physique quantique — superposition, incertitude, intrication",
            "Neuroplasticité — le cerveau se réécrit selon l'usage",
            "Théorie du chaos — petites causes, grands effets",
        ],
        "sport": [
            "Kata de karaté — précision absolue, beauté de la répétition",
            "Parkour — trouver la beauté dans les obstacles urbains",
            "Surf de gros — trouver l'harmonie avec une force immense",
            "Plongeon synchronisé — deux corps, un mouvement",
        ],
    }

    def __init__(self, logger: logging.Logger = None):
        self.log      = logger or logging.getLogger("inspiration")
        self._history: list[dict] = []

    def inject(self, current_project: dict,
               n_connections: int = 2) -> dict:
        """
        Injecte une inspiration aléatoire et génère des connexions avec le projet.
        """
        # Choisir un domaine et une inspiration aléatoire
        domain      = random.choice(list(self.INSPIRATION_DOMAINS.keys()))
        inspiration = random.choice(self.INSPIRATION_DOMAINS[domain])

        self.log.info(f"[INSPIRATION] Domaine : {domain} | '{inspiration[:50]}...'")

        # Générer les connexions via LLM
        project_str = json.dumps(current_project, ensure_ascii=False)[:300]
        prompt      = (
            f"Projet actuel : {project_str}\n\n"
            f"Inspiration externe — {domain.upper()} :\n'{inspiration}'\n\n"
            f"Génère {n_connections} connexions créatives INATTENDUES entre cette inspiration "
            f"et le projet. Des connexions visuelles, narratives ou techniques "
            f"qu'un humain n'aurait pas pensé seul.\n"
            f"Sois spécifique et actionnable. Chaque connexion en 1-2 phrases."
        )
        connections_text = _llm(prompt, max_tokens=300)
        connections = [c.strip() for c in connections_text.split("\n")
                       if c.strip() and len(c.strip()) > 10][:n_connections]

        # Générer des tags ComfyUI inspirés
        tags_prompt = (
            f"Inspiration : '{inspiration}'\n"
            f"Génère 4 tags ComfyUI qui capturent l'essence visuelle de cette inspiration "
            f"dans un contexte anime/manga. Tags courts, précis, utilisables."
        )
        tags_text = _llm(tags_prompt, max_tokens=80)
        tags = [t.strip().strip(",-") for t in tags_text.split(",") if t.strip()][:4]

        result = {
            "domain":      domain,
            "inspiration": inspiration,
            "connections": connections,
            "visual_tags": tags,
            "timestamp":   datetime.utcnow().isoformat(),
        }
        self._history.append(result)
        return result

    def inject_batch(self, current_project: dict,
                      n_domains: int = 3) -> list[dict]:
        """Injecte plusieurs inspirations de domaines différents."""
        domains = random.sample(list(self.INSPIRATION_DOMAINS.keys()), n_domains)
        results = []
        for domain in domains:
            inspiration = random.choice(self.INSPIRATION_DOMAINS[domain])
            results.append({
                "domain":      domain,
                "inspiration": inspiration,
                "visual_tags": [],  # générés à la demande
            })
        return results

    def get_history(self, n: int = 5) -> list[dict]:
        return self._history[-n:]

    def synthesize_inspirations(self, inspirations: list[dict],
                                  project: dict) -> str:
        """Synthétise plusieurs inspirations en un concept unifié."""
        insp_str = "\n".join(
            f"- {i['domain']}: {i['inspiration'][:80]}"
            for i in inspirations[:4]
        )
        return _llm(
            f"Projet : {project.get('title','?')}\n\n"
            f"Inspirations multiples :\n{insp_str}\n\n"
            f"Comment fusionner ces inspirations en un concept créatif unique et cohérent ?\n"
            f"Max 3 phrases, très concret et visuel.",
            max_tokens=200
        )


# ══════════════════════════════════════════════════════════════════════
# FAÇADE INTELLIGENCE ÉTENDUE V1.30
# ══════════════════════════════════════════════════════════════════════

class IntelligenceExtV130:
    """Façade unifiée pour les 4 modules d'intelligence étendue."""

    def __init__(self, hivemind_server: str = "",
                 logger: logging.Logger = None):
        self.log        = logger or logging.getLogger("intel_ext")
        self.fatigue    = CreativeFatigueDetector(logger=self.log)
        self.hivemind   = HivemindProtocol(server_url=hivemind_server, logger=self.log)
        self.audience   = AudienceSimulator(logger=self.log)
        self.inspiration= InspirationInjector(logger=self.log)

    def process_prompt(self, prompt: str, project: dict = None) -> dict:
        """
        Traitement complet d'un prompt :
        1. Détection de fatigue + disruption si nécessaire
        2. Injection d'inspiration (10% du temps)
        3. Test audience rapide
        """
        # 1. Fatigue
        self.fatigue.record_prompt(prompt)
        final_prompt, disruption = self.fatigue.apply_disruption(prompt)

        # 2. Inspiration (20% du temps)
        injection = None
        if random.random() < 0.20 and project:
            injection = self.inspiration.inject(project, n_connections=1)
            if injection.get("visual_tags"):
                extra = ", ".join(injection["visual_tags"][:2])
                final_prompt = extra + ", " + final_prompt

        # 3. Test audience rapide
        audience_result = self.audience.quick_test(
            title=project.get("title","?") if project else "?",
            tags=[t.strip() for t in final_prompt.split(",")[:5]],
        )

        return {
            "original_prompt": prompt,
            "final_prompt":    final_prompt,
            "disruption":      disruption,
            "injection":       injection,
            "audience_score":  audience_result["global_score"],
            "publish_ready":   audience_result["publish_ready"],
        }

    def sync_hivemind(self):
        """Synchronise avec le réseau hivemind (push + pull)."""
        pushed = self.hivemind.push_to_network()
        pulled = self.hivemind.pull_from_network()
        self.log.info(
            f"[HIVEMIND] Sync : {pushed['pushed']} envoyés | {pulled['pulled']} reçus"
        )

    def get_dashboard(self) -> dict:
        return {
            "fatigue":    self.fatigue.get_report(),
            "hivemind":   self.hivemind.get_network_insights(),
            "inspiration":{"history": len(self.inspiration._history)},
        }


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    intel = IntelligenceExtV130()

    print("=== V1.30 INTELLIGENCE ÉTENDUE TEST ===\n")

    # Test Creative Fatigue
    prompts = [
        "masterpiece, best quality, anime style, 1girl, blue hair, school uniform",
        "masterpiece, best quality, anime style, 1girl, blue hair, school uniform, smile",
        "masterpiece, best quality, anime style, 1girl, blue hair, sailor uniform, cute",
        "masterpiece, best quality, anime style, 1girl, blue hair, school uniform, blush",
    ]
    for p in prompts:
        intel.fatigue.record_prompt(p)
    level, entropy = intel.fatigue.get_fatigue_level()
    print(f"Fatigue : niveau={level} | entropie={entropy:.3f}")
    fixed, disruption = intel.fatigue.apply_disruption(prompts[-1])
    print(f"Disruption : {disruption['message']}")
    print(f"Prompt modifié : {fixed[:80]}...")

    # Test Audience Simulation
    print("\n--- Simulation Audience ---")
    result = intel.audience.quick_test(
        "Dragon Ball Super — IA Generation",
        style="anime", emotion="epic",
        tags=["action","dragon ball","epic","ki energy","battle"]
    )
    print(f"Score global : {result['global_score']:.3f}")
    for seg, data in result["by_segment"].items():
        print(f"  {seg:<20} engagement={data['engagement']:.3f}")
    print(f"Prêt à publier : {result['publish_ready']}")

    # Test Inspiration
    print("\n--- Injection d'Inspiration ---")
    insp = intel.inspiration.inject(
        {"title":"Anime épique IA","style":"shonen"},
        n_connections=2
    )
    print(f"Domaine : {insp['domain']}")
    print(f"Inspiration : {insp['inspiration'][:80]}")
    print(f"Tags visuels : {insp['visual_tags']}")
    print(f"Connexions :")
    for c in insp['connections']:
        print(f"  → {c[:100]}")

    # Hivemind
    print(f"\n--- Hivemind ---")
    intel.hivemind.learn("optimal_cfg_anime", 6.5, confidence=0.85)
    intel.hivemind.learn("best_sampler_action", "euler_ancestral", confidence=0.80)
    print(f"Connaissances locales : {intel.hivemind.get_network_insights()}")

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
agents/market_analyzer.py — Agent Stratège Marché V1.70
Analyse le marché IA créatif, identifie les opportunités,
et génère des recommandations stratégiques pour Ov3rLoRd.

Fonctions :
  - Veille technologique (nouveaux modèles, outils, tendances)
  - Analyse concurrentielle (autres pipelines anime IA)
  - Identification de niches inexploitées
  - Recommandations business actionnables
  - Rapport hebdomadaire automatique

Usage :
  python agents/market_analyzer.py --analyze
  python agents/market_analyzer.py --opportunities
  python agents/market_analyzer.py --weekly-report
"""

import json
import logging
import sys
import io
from datetime import datetime
from pathlib import Path

if hasattr(sys.stdout, 'buffer'):
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

try:
    from agents.overlord_utils import fallback_llm, safe_json_parse
    UTILS_OK = True
except ImportError:
    UTILS_OK = False

try:
    from agents.context_bus import get_bus
    BUS_OK = True
except ImportError:
    BUS_OK = False

MARKET_DIR = Path("workspace/market")
MARKET_LOG = Path("workspace/logs/market_analyzer.jsonl")

# ── Positionnement Ov3rLoRd ───────────────────────────────────────

OV3RLORD_POSITIONING = {
    "unique_value": (
        "Premier pipeline de production anime IA entièrement autonome "
        "développé par un créateur indépendant européen. "
        "Seul système à combiner Gantt/PERT/5S industriels + Sakuga japonais + IA génératrice."
    ),
    "target_markets": [
        "Studios d'animation indépendants (Europe, Japon)",
        "Créateurs de contenu anime sur YouTube/TikTok",
        "Startups de contenu narratif (manhwa, webtoon, light novel)",
        "Agences créatives cherchant des assets visuels rapides",
        "Éducation : cours de production IA créative",
        "Hardware makers (ROG/Nvidia) pour content marketing",
    ],
    "competitive_advantages": [
        "Architecture multi-agents cohérente (55+ composants)",
        "Pipeline end-to-end sans intervention humaine sur le rendu",
        "Méthode Sakuga intégrée (cohérence du mouvement)",
        "Documentation industrielle complète (ADR, Gantt, PERT, 5S)",
        "Fondateur avec double culture : industrie + anime depuis origine",
    ],
    "current_gaps": [
        "Pas encore de product public (démo en cours)",
        "Un seul GPU (RTX 5080) — scalabilité limitée",
        "LoRas manquantes pour Gundam et Miku",
        "Pas de interface no-code pour non-techniciens",
        "Pas de pricing défini",
    ],
}

# ── Opportunités identifiées ─────────────────────────────────────────

OPPORTUNITY_MAP = {
    "immédiat": [
        {
            "id":       "OPP-001",
            "title":    "ASUS ROG Content Partnership",
            "desc":     "Démo 2min EVA/Gundam/Miku générée sur ROG hardware = contenu marketing authentique",
            "effort":   "Moyen (6 semaines prod)",
            "revenue":  "Hardware en prêt + visibilité + potentiel cash deal",
            "next":     "Envoyer ASUS_PITCH.md cette semaine",
            "status":   "READY",
        },
        {
            "id":       "OPP-002",
            "title":    "Japan Expo 2026 — Réseau Pro",
            "desc":     "Contact SEFA + démo tablette + réseautage studios JP",
            "effort":   "Faible (19 jours, visiteur pro)",
            "revenue":  "Contacts, visibilité, feedback marché",
            "next":     "Mail JF/Sandrine cette semaine",
            "status":   "READY",
        },
    ],
    "court_terme": [
        {
            "id":       "OPP-003",
            "title":    "Freelance IA Architecture — Studios Indé",
            "desc":     "Construire des pipelines Ov3rLoRd adaptés pour studios tiers",
            "effort":   "1-2 semaines par client",
            "revenue":  "5 000 - 15 000€ par mission",
            "next":     "Portfolio démo + page LinkedIn/GitHub",
            "status":   "POST-DEMO",
        },
        {
            "id":       "OPP-004",
            "title":    "Ov3rLoRd SaaS — Accès Pipeline",
            "desc":     "API/interface pour créateurs qui veulent générer sans setup technique",
            "effort":   "4-6 semaines dev interface",
            "revenue":  "Abonnement 49-199€/mois",
            "next":     "Définir MVP après démo validée",
            "status":   "POST-DEMO",
        },
        {
            "id":       "OPP-005",
            "title":    "Formation Gantt/PERT/5S × IA",
            "desc":     "Seule méthode enseignée combinant management industriel et pipeline IA créatif",
            "effort":   "3-4 semaines contenu",
            "revenue":  "Cours 300-800€, audience potentielle : créateurs, studios, écoles",
            "next":     "Outline du programme après Japan Expo",
            "status":   "PLANNED",
        },
    ],
    "moyen_terme": [
        {
            "id":       "OPP-006",
            "title":    "Partenariat Studio Japonais",
            "desc":     "Apporter la méthode Ov3rLoRd à un studio JP pour production assistée IA",
            "effort":   "6-12 mois de relation",
            "revenue":  "Deal de licence ou co-production",
            "next":     "Japan Expo 2027 — stand avec démo live",
            "status":   "VISION",
        },
        {
            "id":       "OPP-007",
            "title":    "Livre — Mon Histoire par l'IA",
            "desc":     "Interview par IA, édité en livre sur la création d'Ov3rLoRd",
            "effort":   "Contenu = session unique, édition = 2-3 mois",
            "revenue":  "Droits d'auteur + crédibilité",
            "next":     "Après Japan Expo 2026, matière suffisante",
            "status":   "VISION",
        },
    ],
}

# ── Veille technologique ─────────────────────────────────────────────

TECH_WATCHLIST = {
    "à_surveiller": [
        "Flux.1 (Black Forest Labs) — 10GB VRAM, qualité supérieure",
        "Stable Diffusion 3.5 — meilleur sur le texte dans l'image",
        "AnimateDiff v3 — cohérence temporelle pour l'animation",
        "Kling AI — vidéo IA 1080p depuis image",
        "Sora / Runway Gen-3 — texte vers vidéo longue durée",
        "ComfyUI workflow sharing — marché de templates",
    ],
    "à_intégrer_v200": [
        "AnimateDiff → remplace le tweening manuel dans sakuga_compositor",
        "Flux.1 → alternative à SDXL si VRAM > 10GB (RTX 5090)",
        "ControlNet Canny → cohérence de pose entre frames",
        "IP-Adapter → cohérence visage entre shots",
    ],
    "menaces": [
        "Runway/Kling/Sora : vidéo IA de bout en bout → rend le pipeline image-par-image obsolète",
        "Adobe Firefly intégré à Premiere : pipeline dans les outils pro existants",
    ],
    "réponse_stratégique": (
        "La menace vidéo IA de bout en bout est réelle à 18-24 mois. "
        "La réponse d'Ov3rLoRd : être le pipeline de CONTRÔLE CRÉATIF précis "
        "que ces outils ne permettent pas. Rubilax ne peut pas être généré "
        "par un prompt texte générique. La méthode Sakuga + contrôle frame-by-frame "
        "reste notre avantage défensif."
    ),
}


def generate_opportunity_report(logger=None) -> str:
    """Génère un rapport d'opportunités formaté."""
    log = logger or logging.getLogger("market_analyzer")

    lines = [
        f"# RAPPORT MARCHÉ — Ov3rLoRd",
        f"## {datetime.now().strftime('%Y-%m-%d %H:%M')}",
        "",
        f"## POSITIONNEMENT",
        f"{OV3RLORD_POSITIONING['unique_value']}",
        "",
        f"## OPPORTUNITÉS PAR HORIZON",
    ]

    for horizon, opps in OPPORTUNITY_MAP.items():
        lines.append(f"\n### {horizon.upper().replace('_',' ')}")
        for opp in opps:
            status_icons = {
                "READY":      "🟢",
                "POST-DEMO":  "🟡",
                "PLANNED":    "🔵",
                "VISION":     "⚪",
            }
            icon = status_icons.get(opp["status"], "•")
            lines.append(f"\n**{icon} {opp['id']} — {opp['title']}**")
            lines.append(f"  {opp['desc']}")
            lines.append(f"  Effort : {opp['effort']}")
            lines.append(f"  Revenue : {opp['revenue']}")
            lines.append(f"  Prochaine action : **{opp['next']}**")

    lines += [
        "",
        "## VEILLE TECH",
        "",
        "### À intégrer V2.0",
    ]
    for item in TECH_WATCHLIST["à_intégrer_v200"]:
        lines.append(f"- {item}")

    lines += [
        "",
        "### Réponse stratégique aux menaces",
        TECH_WATCHLIST["réponse_stratégique"],
    ]

    report = "\n".join(lines)
    MARKET_DIR.mkdir(parents=True, exist_ok=True)
    ts   = datetime.now().strftime("%Y%m%d_%H%M%S")
    path = MARKET_DIR / f"market_report_{ts}.md"
    path.write_text(report, encoding='utf-8')
    log.info(f"[MARKET] Rapport → {path.name}")
    return report


def run_market_analysis(logger=None) -> dict:
    """Analyse complète avec enrichissement LLM si disponible."""
    log = logger or logging.getLogger("market_analyzer")

    result = {
        "timestamp":      datetime.now().isoformat(),
        "positioning":    OV3RLORD_POSITIONING,
        "opportunities":  OPPORTUNITY_MAP,
        "tech_watchlist": TECH_WATCHLIST,
        "immediate_actions": [
            opp["next"] for opps in OPPORTUNITY_MAP.values()
            for opp in opps if opp["status"] == "READY"
        ],
    }

    if BUS_OK:
        try:
            bus = get_bus()
            bus.write("market.immediate_actions",
                      len(result["immediate_actions"]), agent_id="market")
            bus.write("market.last_analysis",
                      result["timestamp"], agent_id="market")
        except Exception:
            pass

    return result


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Ov3rLoRd Market Analyzer V1.70")
    parser.add_argument("--analyze",      action="store_true")
    parser.add_argument("--opportunities",action="store_true")
    parser.add_argument("--weekly-report",action="store_true")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO,
                        format="%(asctime)s [%(levelname)s] %(message)s")

    if args.opportunities or args.weekly_report or args.analyze:
        report = generate_opportunity_report()
        print(report[:3000])
    else:
        result = run_market_analysis()
        print(f"\n{'═'*60}")
        print(f"  MARKET ANALYZER V1.70")
        print(f"{'═'*60}")
        print(f"  Actions immédiates : {len(result['immediate_actions'])}")
        for a in result["immediate_actions"]:
            print(f"    → {a}")
        print(f"\n  Opportunités totales :")
        for horizon, opps in OPPORTUNITY_MAP.items():
            print(f"    {horizon}: {len(opps)} opportunités")
        print(f"\n  Menaces à surveiller :")
        for m in TECH_WATCHLIST["menaces"]:
            print(f"    ⚠ {m[:70]}")
        print(f"{'═'*60}")

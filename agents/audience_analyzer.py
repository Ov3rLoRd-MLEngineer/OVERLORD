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
agents/audience_analyzer.py — Analyseur d'Audience V1.47
Analyse le feedback Reddit/social pour adapter le contenu de la prochaine production.
Identifie ce que le public aime, déteste, demande — et l'injecte dans le pipeline.

Usage :
    from agents.audience_analyzer import AudienceAnalyzer
    analyzer = AudienceAnalyzer("Dragon Ball Ov3rLoRd")
    insights = analyzer.analyze(subreddits=["anime","dragonball"])
    trending = analyzer.get_content_recommendations()
"""

import json
import logging
import time
import requests
from pathlib import Path
from datetime import datetime, timedelta
from collections import Counter

try:
    from agents.overlord_utils import fallback_llm, safe_json_parse, _get_reddit_headers
    UTILS_OK = True
except ImportError:
    UTILS_OK = False

log = logging.getLogger("audience_analyzer")
AUDIENCE_DIR = Path("workspace/audience")

SENTIMENT_KEYWORDS = {
    "positive": ["amazing","love","great","awesome","perfect","beautiful","epic","masterpiece","wow","incredible","best","fire","goat"],
    "negative": ["bad","ugly","weird","wrong","terrible","hate","boring","lazy","disappointing","worse","trash","mid"],
    "request":  ["want","need","please","more","when","next","sequel","episode","series","continue","make","could you","would love"],
    "character":["goku","vegeta","broly","gohan","piccolo","frieza","cell","buu","jiren","hit"],
}


class RedditAnalyzer:
    """Analyse les discussions Reddit sur la série."""

    def get_posts(self, subreddits: list, keywords: list = None,
                  limit: int = 25) -> list:
        posts = []
        try:
            headers = _get_reddit_headers() if UTILS_OK else {"User-Agent":"Ov3rLoRd/1.47"}
        except Exception:
            headers = {"User-Agent":"Ov3rLoRd/1.47"}

        for sub in subreddits:
            try:
                url  = f"https://www.reddit.com/r/{sub}/hot.json?limit={limit}"
                r    = requests.get(url, headers=headers, timeout=10)
                if r.status_code != 200:
                    continue
                for child in r.json()["data"]["children"]:
                    d = child["data"]
                    title = d.get("title","")
                    if keywords:
                        if not any(kw.lower() in title.lower() for kw in keywords):
                            continue
                    posts.append({
                        "source":   f"r/{sub}",
                        "title":    title,
                        "score":    d.get("score",0),
                        "comments": d.get("num_comments",0),
                        "text":     d.get("selftext","")[:500],
                        "url":      d.get("url",""),
                        "created":  datetime.utcfromtimestamp(d.get("created_utc",0)).isoformat(),
                    })
                time.sleep(0.5)
            except Exception as e:
                log.warning(f"[AUDIENCE] Reddit r/{sub} : {e}")
        return posts

    def get_comments(self, post_url: str, limit: int = 20) -> list:
        """Récupère les commentaires d'un post populaire."""
        try:
            json_url = post_url.rstrip("/") + ".json?limit=" + str(limit)
            r = requests.get(json_url, headers={"User-Agent":"Ov3rLoRd/1.47"}, timeout=10)
            if r.status_code == 200:
                data = r.json()
                if len(data) >= 2:
                    return [c["data"].get("body","")
                            for c in data[1]["data"]["children"]
                            if c["kind"] == "t1"]
        except Exception:
            pass
        return []


class SentimentEngine:
    """Analyse le sentiment des textes sans modèle ML (règles + LLM)."""

    def analyze_batch(self, texts: list) -> dict:
        """Analyse un lot de textes et retourne les insights agrégés."""
        sentiment_scores = {"positive": 0, "negative": 0, "neutral": 0}
        topics   = Counter()
        requests_list = []
        char_mentions = Counter()

        for text in texts:
            t_lower = text.lower()

            # Sentiment basique
            pos = sum(1 for k in SENTIMENT_KEYWORDS["positive"] if k in t_lower)
            neg = sum(1 for k in SENTIMENT_KEYWORDS["negative"] if k in t_lower)
            if pos > neg:   sentiment_scores["positive"] += 1
            elif neg > pos: sentiment_scores["negative"] += 1
            else:           sentiment_scores["neutral"]  += 1

            # Requêtes
            for kw in SENTIMENT_KEYWORDS["request"]:
                if kw in t_lower:
                    requests_list.append(text[:100])
                    break

            # Personnages mentionnés
            for char in SENTIMENT_KEYWORDS["character"]:
                if char in t_lower:
                    char_mentions[char] += 1

            # Topics (mots fréquents)
            for word in t_lower.split():
                if len(word) > 4 and word.isalpha():
                    topics[word] += 1

        total = max(sum(sentiment_scores.values()), 1)
        return {
            "sentiment": {k: round(v/total*100,1) for k,v in sentiment_scores.items()},
            "top_topics":  [w for w,_ in topics.most_common(10)],
            "char_mentions": dict(char_mentions.most_common(5)),
            "requests_sample": requests_list[:5],
            "total_analyzed": len(texts),
        }


class AudienceAnalyzer:
    """Analyse complète de l'audience et génère des recommandations de contenu."""

    def __init__(self, series: str, logger: logging.Logger = None):
        self.log     = logger or log
        self.series  = series
        self.reddit  = RedditAnalyzer()
        self.sentiment = SentimentEngine()
        AUDIENCE_DIR.mkdir(parents=True, exist_ok=True)
        self.report_path = AUDIENCE_DIR / f"{series.replace(' ','_')}_audience.json"

    def analyze(self, subreddits: list = None,
                keywords: list = None) -> dict:
        """Lance l'analyse complète de l'audience."""
        subs  = subreddits or ["anime","manga","dragonball","OnePiece","AIGeneratedArt"]
        kws   = keywords or [self.series.split()[0], "AI anime", "generated anime"]

        self.log.info(f"[AUDIENCE] Analyse pour '{self.series}'...")

        # Collecte Reddit
        posts = self.reddit.get_posts(subs, kws, limit=20)
        self.log.info(f"[AUDIENCE] {len(posts)} posts collectés")

        # Textes à analyser
        texts = [p["title"] + " " + p.get("text","") for p in posts]

        # Analyse sentiment
        sentiment_data = self.sentiment.analyze_batch(texts)

        # Top posts (plus engageants)
        top_posts = sorted(posts, key=lambda p: p["score"]+p["comments"]*2, reverse=True)[:5]

        report = {
            "series":     self.series,
            "analyzed_at":datetime.now().isoformat(),
            "posts_count":len(posts),
            "sentiment":  sentiment_data,
            "top_posts":  top_posts,
            "subreddits": subs,
        }

        # Recommandations LLM
        if UTILS_OK and texts:
            report["recommendations"] = self._generate_recommendations(report)

        # Sauvegarder
        self.report_path.write_text(
            json.dumps(report, indent=2, ensure_ascii=False, default=str),
            encoding="utf-8"
        )
        self.log.info(f"[AUDIENCE] ✓ Rapport sauvegardé")
        return report

    def _generate_recommendations(self, report: dict) -> dict:
        sentiment = report.get("sentiment",{})
        topics    = report.get("sentiment",{}).get("top_topics",[])
        chars     = report.get("sentiment",{}).get("char_mentions",{})
        requests_ = report.get("sentiment",{}).get("requests_sample",[])

        prompt = (
            f"Analyse de l'audience pour '{self.series}'.\n"
            f"Sentiment : {sentiment.get('sentiment',{})}\n"
            f"Topics trending : {topics[:5]}\n"
            f"Personnages populaires : {list(chars.keys())[:3]}\n"
            f"Requêtes du public : {requests_[:3]}\n\n"
            f"Génère des recommandations pour le prochain épisode. JSON uniquement :\n"
            '{"next_episode_focus":"","characters_to_feature":[],"themes":[],"avoid":[],"title_suggestion":""}'
        )
        raw = fallback_llm(prompt, max_tokens=300, logger=self.log)
        ok, data, _ = safe_json_parse(raw, logger=self.log)
        return data if ok else {}

    def get_content_recommendations(self) -> dict:
        """Retourne les recommandations du dernier rapport."""
        if self.report_path.exists():
            try:
                data = json.loads(self.report_path.read_text(encoding="utf-8"))
                return data.get("recommendations", {})
            except Exception:
                pass
        return {}

    def inject_into_sourcing(self, trend_report: dict) -> dict:
        """Enrichit un TrendReport avec les insights audience."""
        recs = self.get_content_recommendations()
        if not recs:
            return trend_report
        extra_kws = recs.get("themes", []) + recs.get("characters_to_feature", [])
        trend_report["hot_keywords"] = (trend_report.get("hot_keywords",[]) + extra_kws)[:20]
        trend_report["audience_focus"] = recs.get("next_episode_focus","")
        return trend_report


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    analyzer = AudienceAnalyzer("Dragon Ball Ov3rLoRd")
    report   = analyzer.analyze(
        subreddits=["dragonball","anime"],
        keywords=["Dragon Ball","Goku","Broly"]
    )
    s = report["sentiment"]
    print(f"Posts analysés : {report['posts_count']}")
    print(f"Sentiment : {s.get('sentiment',{})}")
    print(f"Topics : {s.get('top_topics',{})[:5]}")
    print(f"Personnages : {s.get('char_mentions',{})}")
    if report.get("recommendations"):
        print(f"Recommandations : {report['recommendations']}")

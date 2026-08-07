"""
agents/sourcing.py — Agent Veilleur "OverLord"
Scrute les tendances web sans dépendance à des API payantes.
Sources : Reddit JSON API (public), RSS actualités, Google Trends via pytrends.

Sortie : TrendReport — dict structuré consommé par scenario.py
"""

import json
import time
import logging
import hashlib
import requests
from datetime import datetime
from pathlib import Path

# Optionnel — pip install pytrends feedparser
try:
    from pytrends.request import TrendReq
    PYTRENDS_OK = True
except ImportError:
    PYTRENDS_OK = False

try:
    import feedparser
    FEEDPARSER_OK = True
except ImportError:
    FEEDPARSER_OK = False


# ============================================================
# CONFIG
# ============================================================
CACHE_DIR = Path("workspace/sourcing_cache")
CACHE_TTL = 3600  # secondes avant qu'un cache soit considéré périmé

# Subreddits à surveiller (gratuit, pas de clé API)
REDDIT_SUBS = [
    "anime",
    "manga",
    "dragonball",
    "OnePiece",
    "Naruto",
    "webtoons",
    "comicbooks",
    "Marvel",
    "gamedev",
    "blender",
    "learnart",
    "worldnews",
    "technology",
    "artificial",
]

# Flux RSS gratuits
RSS_FEEDS = {
    "crunchyroll":   "https://www.crunchyroll.com/rss/anime",
    "animenewsnet":  "https://www.animenewsnetwork.com/all/rss.xml",
    "kotaku":        "https://kotaku.com/rss",
    "ign":           "https://feeds.ign.com/ign/all",
    "techcrunch":    "https://techcrunch.com/feed/",
    "theVerge":      "https://www.theverge.com/rss/index.xml",
}

# Mots-clés Google Trends à surveiller
TREND_KEYWORDS = [
    "anime 2025",
    "manga trending",
    "dragon ball",
    "webtoon",
    "AI art",
    "animated short film",
    "comic book",
]

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 OverLord-Pipeline/1.0"
    )
}


# ============================================================
# CACHE
# ============================================================
def _cache_path(key: str) -> Path:
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    safe = hashlib.md5(key.encode()).hexdigest()
    return CACHE_DIR / f"{safe}.json"

def _cache_get(key: str) -> dict | None:
    p = _cache_path(key)
    if not p.exists():
        return None
    data = json.loads(p.read_text(encoding="utf-8"))
    if time.time() - data.get("_ts", 0) > CACHE_TTL:
        return None
    return data

def _cache_set(key: str, data: dict):
    data["_ts"] = time.time()
    _cache_path(key).write_text(
        json.dumps(data, ensure_ascii=False, indent=2),
        encoding="utf-8"
    )


# ============================================================
# AGENT REDDIT
# ============================================================
def scrape_reddit(subreddits: list = None,
                  limit: int = 10,
                  logger: logging.Logger = None) -> list:
    """
    Récupère les posts trending de chaque subreddit via l'API JSON publique.
    Pas de clé API nécessaire.
    """
    log = logger or logging.getLogger("sourcing.reddit")
    subs = subreddits or REDDIT_SUBS
    results = []

    for sub in subs:
        cache_key = f"reddit_{sub}_{limit}"
        cached = _cache_get(cache_key)
        if cached:
            results.extend(cached.get("posts", []))
            continue

        try:
            url  = f"https://www.reddit.com/r/{sub}/hot.json?limit={limit}"
            resp = requests.get(url, headers=HEADERS, timeout=15)
            if resp.status_code != 200:
                log.warning(f"Reddit r/{sub} → HTTP {resp.status_code}")
                continue

            posts = []
            for child in resp.json()["data"]["children"]:
                d = child["data"]
                posts.append({
                    "source":    f"reddit/r/{sub}",
                    "title":     d.get("title", ""),
                    "score":     d.get("score", 0),
                    "comments":  d.get("num_comments", 0),
                    "url":       d.get("url", ""),
                    "flair":     d.get("link_flair_text", ""),
                    "created":   datetime.utcfromtimestamp(
                                     d.get("created_utc", 0)
                                 ).isoformat(),
                })

            _cache_set(cache_key, {"posts": posts})
            results.extend(posts)
            log.debug(f"Reddit r/{sub} → {len(posts)} posts")
            time.sleep(1)  # politesse Reddit

        except Exception as e:
            log.warning(f"Reddit r/{sub} erreur : {e}")

    return results


# ============================================================
# AGENT RSS
# ============================================================
def scrape_rss(feeds: dict = None,
               logger: logging.Logger = None) -> list:
    """Agrège les articles depuis les flux RSS définis."""
    log = logger or logging.getLogger("sourcing.rss")

    if not FEEDPARSER_OK:
        log.warning("feedparser non installé — pip install feedparser")
        return []

    sources = feeds or RSS_FEEDS
    results = []

    for name, url in sources.items():
        cache_key = f"rss_{name}"
        cached = _cache_get(cache_key)
        if cached:
            results.extend(cached.get("articles", []))
            continue

        try:
            feed = feedparser.parse(url)
            articles = []
            for entry in feed.entries[:10]:
                articles.append({
                    "source":  f"rss/{name}",
                    "title":   entry.get("title", ""),
                    "summary": entry.get("summary", "")[:300],
                    "link":    entry.get("link", ""),
                    "date":    entry.get("published", ""),
                })
            _cache_set(cache_key, {"articles": articles})
            results.extend(articles)
            log.debug(f"RSS {name} → {len(articles)} articles")

        except Exception as e:
            log.warning(f"RSS {name} erreur : {e}")

    return results


# ============================================================
# AGENT GOOGLE TRENDS
# ============================================================
def scrape_trends(keywords: list = None,
                  geo: str = "FR",
                  logger: logging.Logger = None) -> list:
    """Récupère les tendances Google via pytrends."""
    log = logger or logging.getLogger("sourcing.trends")

    if not PYTRENDS_OK:
        log.warning("pytrends non installé — pip install pytrends")
        return []

    kws = keywords or TREND_KEYWORDS
    results = []

    try:
        pt = TrendReq(hl="fr-FR", tz=60)
        # Batch par 5 (limite pytrends)
        for i in range(0, len(kws), 5):
            batch = kws[i:i+5]
            cache_key = f"trends_{'_'.join(batch)}_{geo}"
            cached = _cache_get(cache_key)
            if cached:
                results.extend(cached.get("trends", []))
                continue

            pt.build_payload(batch, cat=0, timeframe="now 7-d", geo=geo)
            df = pt.interest_over_time()

            trends = []
            if not df.empty:
                for kw in batch:
                    if kw in df.columns:
                        avg_interest = int(df[kw].mean())
                        trends.append({
                            "keyword":       kw,
                            "avg_interest":  avg_interest,
                            "geo":           geo,
                            "source":        "google_trends",
                        })

            _cache_set(cache_key, {"trends": trends})
            results.extend(trends)
            log.debug(f"Trends batch {batch} → {len(trends)} items")
            time.sleep(2)

    except Exception as e:
        log.warning(f"Google Trends erreur : {e}")

    return results


# ============================================================
# AGENT AGRÉGATEUR — pont Sourcing → Scénario
# ============================================================
def aggregate(reddit_posts: list,
              rss_articles: list,
              trends: list,
              media_type: str = "anime",
              logger: logging.Logger = None) -> dict:
    """
    Synthétise toutes les sources en un TrendReport structuré.
    Ce dict est la sortie directe vers scenario.py.

    media_type : "anime" | "manga" | "3d" | "photoreal" | "art" | "comics" | "game"
    """
    log = logger or logging.getLogger("sourcing.aggregator")

    # Top Reddit par score
    top_reddit = sorted(reddit_posts, key=lambda x: x.get("score", 0), reverse=True)[:10]

    # Top tendances Google
    top_trends = sorted(trends, key=lambda x: x.get("avg_interest", 0), reverse=True)[:5]

    # Extraction des thèmes clés (simple : titres les plus fréquents)
    all_titles = (
        [p["title"] for p in top_reddit] +
        [a["title"] for a in rss_articles[:10]]
    )
    keywords_found = _extract_keywords(all_titles)

    report = {
        "generated_at":  datetime.utcnow().isoformat(),
        "media_type":    media_type,
        "top_reddit":    top_reddit[:5],
        "top_rss":       rss_articles[:5],
        "top_trends":    top_trends,
        "hot_keywords":  keywords_found[:15],
        "brief": (
            f"Tendances actuelles ({media_type}) : "
            f"{', '.join(keywords_found[:5])}. "
            f"Posts viraux : {top_reddit[0]['title'] if top_reddit else 'N/A'}."
        ),
        "raw_count": {
            "reddit":  len(reddit_posts),
            "rss":     len(rss_articles),
            "trends":  len(trends),
        }
    }

    log.info(
        f"Agrégation : {len(reddit_posts)} Reddit | "
        f"{len(rss_articles)} RSS | {len(trends)} Trends | "
        f"→ {len(keywords_found)} mots-clés extraits"
    )
    return report


def _extract_keywords(titles: list) -> list:
    """Extrait les mots-clés les plus fréquents des titres (sans NLTK)."""
    stopwords = {
        "the","a","an","of","in","is","it","to","and","for","on",
        "with","that","this","are","was","be","at","by","from",
        "le","la","les","de","du","un","une","des","et","en","est",
        "que","qui","il","elle","dans","sur","pour","par","avec",
    }
    freq = {}
    for title in titles:
        for word in title.lower().split():
            word = word.strip(".,!?\"'():[]")
            if len(word) > 3 and word not in stopwords:
                freq[word] = freq.get(word, 0) + 1

    return [w for w, _ in sorted(freq.items(), key=lambda x: -x[1])]


# ============================================================
# POINT D'ENTRÉE PRINCIPAL
# ============================================================
def run_sourcing(media_type: str = "anime",
                 logger: logging.Logger = None) -> dict:
    """
    Lance tous les agents de sourcing et retourne un TrendReport.
    Appelé par maestro.py dans le bloc SOURCING.
    """
    log = logger or logging.getLogger("sourcing")
    log.info(f"[SOURCING] Démarrage — media_type={media_type}")

    reddit   = scrape_reddit(logger=log)
    rss      = scrape_rss(logger=log)
    trends   = scrape_trends(logger=log)
    report   = aggregate(reddit, rss, trends, media_type=media_type, logger=log)

    log.info(f"[SOURCING] Terminé — brief: {report['brief'][:80]}...")
    return report


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    report = run_sourcing("anime")
    print(json.dumps(report, indent=2, ensure_ascii=False))

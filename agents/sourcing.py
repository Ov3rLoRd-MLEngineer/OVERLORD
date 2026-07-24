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
agents/sourcing.py — Agent Veilleur Ov3rLoRd V1.49
Scrute Reddit, RSS, Google Trends et publie sur le context_bus.
Dependances : pip install pytrends feedparser requests
"""

import json
import time
import logging
import hashlib
import requests
from datetime import datetime, timezone
from pathlib import Path

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

try:
    from agents.overlord_utils import _get_reddit_headers as _reddit_hdrs
    UTILS_OK = True
except ImportError:
    UTILS_OK = False
    _reddit_hdrs = None

try:
    from agents.context_bus import get_bus
    BUS_OK = True
except ImportError:
    BUS_OK = False

# ── Config ────────────────────────────────────────────────────────────
CACHE_DIR = Path("workspace/sourcing_cache")
CACHE_TTL = 3600

REDDIT_SUBS = [
    "anime","manga","dragonball","OnePiece","Naruto","webtoons",
    "comicbooks","Marvel","gamedev","blender","learnart",
    "worldnews","technology","artificial",
]

RSS_FEEDS = {
    "crunchyroll":  "https://www.crunchyroll.com/rss/anime",
    "animenewsnet": "https://www.animenewsnetwork.com/all/rss.xml",
    "kotaku":       "https://kotaku.com/rss",
    "ign":          "https://feeds.ign.com/ign/all",
    "techcrunch":   "https://techcrunch.com/feed/",
    "theVerge":     "https://www.theverge.com/rss/index.xml",
}

TREND_KEYWORDS = [
    "anime 2025","manga trending","dragon ball",
    "webtoon","AI art","animated short film","comic book",
]

HEADERS = {"User-Agent": "Mozilla/5.0 Ov3rLoRd-Pipeline/1.49"}

# Headers Reddit : via overlord_utils si disponible, sinon local
def _get_reddit_headers() -> dict:
    if UTILS_OK and _reddit_hdrs:
        return _reddit_hdrs()
    return {"User-Agent": "Ov3rLoRd-Pipeline/1.49 by Ov3rL0rD"}


# ── Cache ─────────────────────────────────────────────────────────────
def _cache_path(key: str) -> Path:
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    return CACHE_DIR / f"{hashlib.md5(key.encode()).hexdigest()}.json"

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
        json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8"
    )


# ── Reddit ────────────────────────────────────────────────────────────
def scrape_reddit(subreddits: list = None, limit: int = 10,
                  logger: logging.Logger = None) -> list:
    log  = logger or logging.getLogger("sourcing.reddit")
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
            resp = requests.get(url, headers=_get_reddit_headers(), timeout=15)
            if resp.status_code != 200:
                log.warning(f"Reddit r/{sub} -> HTTP {resp.status_code}")
                continue
            posts = []
            for child in resp.json()["data"]["children"]:
                d = child["data"]
                posts.append({
                    "source":   f"reddit/r/{sub}",
                    "title":    d.get("title", ""),
                    "score":    d.get("score", 0),
                    "comments": d.get("num_comments", 0),
                    "url":      d.get("url", ""),
                    "flair":    d.get("link_flair_text", ""),
                    "created":  datetime.fromtimestamp(
                                    d.get("created_utc", 0), tz=timezone.utc
                                ).isoformat(),
                })
            _cache_set(cache_key, {"posts": posts})
            results.extend(posts)
            log.debug(f"Reddit r/{sub} -> {len(posts)} posts")
            time.sleep(1)
        except Exception as e:
            log.warning(f"Reddit r/{sub} erreur : {e}")

    return results


# ── RSS ───────────────────────────────────────────────────────────────
def scrape_rss(feeds: dict = None, logger: logging.Logger = None) -> list:
    log = logger or logging.getLogger("sourcing.rss")
    if not FEEDPARSER_OK:
        log.warning("feedparser non installe — pip install feedparser")
        return []

    sources = feeds or RSS_FEEDS
    results = []

    for name, url in sources.items():
        cache_key = f"rss_{name}"
        cached = _cache_get(cache_key)
        if cached:
            results.extend(cached.get("articles", [])); continue
        try:
            feed     = feedparser.parse(url)
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
            log.debug(f"RSS {name} -> {len(articles)} articles")
        except Exception as e:
            log.warning(f"RSS {name} erreur : {e}")

    return results


# ── Google Trends ─────────────────────────────────────────────────────
def scrape_trends(keywords: list = None, geo: str = "FR",
                  logger: logging.Logger = None) -> list:
    log = logger or logging.getLogger("sourcing.trends")
    if not PYTRENDS_OK:
        log.warning("pytrends non installe — pip install pytrends")
        return []

    kws     = keywords or TREND_KEYWORDS
    results = []

    try:
        pt = TrendReq(hl="fr-FR", tz=60)
        for i in range(0, len(kws), 5):
            batch     = kws[i:i+5]
            cache_key = f"trends_{'_'.join(batch)}_{geo}"
            cached    = _cache_get(cache_key)
            if cached:
                results.extend(cached.get("trends", [])); continue

            pt.build_payload(batch, cat=0, timeframe="now 7-d", geo=geo)
            df     = pt.interest_over_time()
            trends = []
            if not df.empty:
                for kw in batch:
                    if kw in df.columns:
                        trends.append({
                            "keyword":      kw,
                            "avg_interest": int(df[kw].mean()),
                            "geo":          geo,
                            "source":       "google_trends",
                        })
            _cache_set(cache_key, {"trends": trends})
            results.extend(trends)
            log.debug(f"Trends {batch} -> {len(trends)} items")
            time.sleep(2)
    except Exception as e:
        log.warning(f"Google Trends erreur : {e}")

    return results


# ── Aggregateur ───────────────────────────────────────────────────────
def aggregate(reddit_posts: list, rss_articles: list, trends: list,
              media_type: str = "anime",
              logger: logging.Logger = None) -> dict:
    log = logger or logging.getLogger("sourcing.aggregator")

    top_reddit = sorted(reddit_posts, key=lambda x: x.get("score", 0), reverse=True)[:10]
    top_trends = sorted(trends, key=lambda x: x.get("avg_interest", 0), reverse=True)[:5]
    all_titles = [p["title"] for p in top_reddit] + [a["title"] for a in rss_articles[:10]]
    keywords_found = _extract_keywords(all_titles)

    report = {
        "generated_at": datetime.now(tz=timezone.utc).isoformat(),
        "media_type":   media_type,
        "top_reddit":   top_reddit[:5],
        "top_rss":      rss_articles[:5],
        "top_trends":   top_trends,
        "hot_keywords": keywords_found[:15],
        "brief": (
            f"Tendances actuelles ({media_type}) : "
            f"{', '.join(keywords_found[:5])}. "
            f"Posts viraux : {top_reddit[0]['title'] if top_reddit else 'N/A'}."
        ),
        "raw_count": {
            "reddit": len(reddit_posts),
            "rss":    len(rss_articles),
            "trends": len(trends),
        },
    }

    log.info(
        f"Agregation : {len(reddit_posts)} Reddit | "
        f"{len(rss_articles)} RSS | {len(trends)} Trends | "
        f"-> {len(keywords_found)} mots-cles"
    )
    return report


def _extract_keywords(titles: list) -> list:
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


# ── Point d'entree ────────────────────────────────────────────────────
def run_sourcing(media_type: str = "anime",
                 logger: logging.Logger = None) -> dict:
    log = logger or logging.getLogger("sourcing")
    log.info(f"[SOURCING] Demarrage — media_type={media_type}")

    reddit = scrape_reddit(logger=log)
    rss    = scrape_rss(logger=log)
    trends = scrape_trends(logger=log)
    report = aggregate(reddit, rss, trends, media_type=media_type, logger=log)

    # Publier sur le context_bus
    if BUS_OK:
        try:
            bus = get_bus()
            bus.write("sourcing.brief",        report["brief"][:200],      agent_id="sourcing")
            bus.write("sourcing.hot_keywords", report["hot_keywords"][:10], agent_id="sourcing")
            bus.write("sourcing.media_type",   media_type,                  agent_id="sourcing")
            bus.write("sourcing.top_reddit",   report["top_reddit"][:3],    agent_id="sourcing")
        except Exception as e:
            log.warning(f"[SOURCING] Publication bus echouee : {e}")

    log.info(f"[SOURCING] Termine — brief: {report['brief'][:80]}...")
    return report


if __name__ == "__main__":
    import sys, io
    if hasattr(sys.stdout,'buffer'):
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
    logging.basicConfig(level=logging.INFO)
    report = run_sourcing("anime")
    print(json.dumps(report, indent=2, ensure_ascii=False))
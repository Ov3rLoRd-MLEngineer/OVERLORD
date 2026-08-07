"""
agents/marketing_pub.py — Agents Marketing, Webmaster & Community Manager
Trois agents métier avec interface de chat dédiée.

Marketing Strategist : campagnes, copywriting, visuels ads
Webmaster           : SEO, pages web, déploiement
Community Manager   : posts réseaux, calendrier, réponses

Chaque agent a son propre prompt système et peut dialoguer
via l'interface de chat de learning_ui.py.
"""

import json
import logging
import requests
import threading
from pathlib import Path
from datetime import datetime, timedelta
from dataclasses import dataclass, field

ANTHROPIC_URL = "https://api.anthropic.com/v1/messages"
CLAUDE_MODEL  = "claude-sonnet-4-6"
OLLAMA_URL    = "http://localhost:11434"
OUTPUT_DIR    = Path("workspace/marketing")
WEB_DIR       = Path("workspace/web")
SOCIAL_DIR    = Path("workspace/social")


def llm_call(prompt: str, system: str, max_tokens: int = 1000,
             model: str = CLAUDE_MODEL) -> str:
    """Appel LLM unifié — Claude d'abord, Ollama en fallback."""
    try:
        resp = requests.post(
            ANTHROPIC_URL,
            headers={"Content-Type": "application/json"},
            json={"model": model, "max_tokens": max_tokens,
                  "system": system,
                  "messages": [{"role":"user","content":prompt}]},
            timeout=40
        )
        if resp.status_code == 200:
            return resp.json()["content"][0]["text"].strip()
    except Exception:
        pass
    try:
        resp = requests.post(
            f"{OLLAMA_URL}/api/generate",
            json={"model":"mistral","prompt":f"{system}\n\n{prompt}","stream":False},
            timeout=90
        )
        if resp.status_code == 200:
            return resp.json().get("response","").strip()
    except Exception:
        pass
    return ""


# ══════════════════════════════════════════════════════════════════════
# AGENT MARKETING
# ══════════════════════════════════════════════════════════════════════

class MarketingAgent:
    """
    Marketing Strategist — campagnes, copywriting, visuels ads.
    Génère les assets marketing depuis le contenu produit par le pipeline.
    """

    SYSTEM = (
        "Tu es un Marketing Strategist expert en promotion de contenu créatif numérique "
        "(anime, gaming, divertissement IA). Tu maîtrises le copywriting percutant, "
        "les stratégies multi-canales (YouTube, TikTok, X/Twitter, Instagram, Reddit) "
        "et l'analyse des métriques de performance. Tes réponses sont concrètes, "
        "actionnables, avec des exemples prêts à copier-coller."
    )

    def __init__(self, logger: logging.Logger = None):
        self.log = logger or logging.getLogger("marketing")
        OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    # ── Génération de contenu ─────────────────────────────────────────

    def generate_campaign(self, content_title: str,
                           content_type: str = "anime_short",
                           target_platforms: list = None,
                           budget: str = "0€ (organique)") -> dict:
        """Génère un plan de campagne marketing complet."""
        platforms = target_platforms or ["YouTube","TikTok","X/Twitter","Reddit/r/anime"]
        platforms_str = ", ".join(platforms)

        prompt = (
            f"Crée un plan marketing complet pour ce contenu :\n"
            f"  Titre     : {content_title}\n"
            f"  Type      : {content_type}\n"
            f"  Plateformes : {platforms_str}\n"
            f"  Budget    : {budget}\n\n"
            f"Fournis : hooks par plateforme, timing de publication, "
            f"hashtags recommandés, call-to-action, métriques cibles."
        )
        result = llm_call(prompt, self.SYSTEM, max_tokens=1200)
        campaign = {
            "title":     content_title,
            "type":      content_type,
            "platforms": platforms,
            "budget":    budget,
            "plan":      result,
            "generated": datetime.utcnow().isoformat(),
        }
        self._save(f"campaign_{self._slug(content_title)}.json", campaign)
        self.log.info(f"[MARKETING] Campagne générée : {content_title}")
        return campaign

    def write_hooks(self, content_summary: str,
                    platform: str = "TikTok") -> list[str]:
        """Génère 5 hooks d'accroche pour une plateforme."""
        prompt = (
            f"Écris 5 hooks d'accroche différents pour {platform} "
            f"pour ce contenu :\n{content_summary}\n\n"
            f"Chaque hook doit être <150 caractères, percutant, "
            f"adapté au style {platform}. Numérote-les."
        )
        result = llm_call(prompt, self.SYSTEM, max_tokens=400)
        hooks = [line.strip() for line in result.split("\n")
                 if line.strip() and line[0].isdigit()]
        return hooks

    def write_description(self, content: str, platform: str = "YouTube",
                           include_seo: bool = True) -> str:
        """Rédige une description optimisée SEO."""
        seo_note = " Inclure des mots-clés SEO naturels." if include_seo else ""
        prompt = (
            f"Rédige une description {platform} optimisée pour :\n{content}\n\n"
            f"Style {platform}, entre 200-500 mots selon la plateforme.{seo_note} "
            f"Inclure hashtags pertinents à la fin."
        )
        return llm_call(prompt, self.SYSTEM, max_tokens=600)

    def generate_ad_copy(self, product: str, audience: str,
                          format: str = "carrousel") -> dict:
        """Génère des copies publicitaires pour différents formats."""
        prompt = (
            f"Génère des copies publicitaires pour :\n"
            f"  Produit/Contenu : {product}\n"
            f"  Audience cible  : {audience}\n"
            f"  Format          : {format}\n\n"
            f"Inclure : titre (max 30 car), description (max 90 car), "
            f"CTA, variante A et variante B."
        )
        result = llm_call(prompt, self.SYSTEM, max_tokens=500)
        return {"product": product, "audience": audience,
                "format": format, "copy": result}

    def analyze_competitor(self, competitor_url: str = "",
                            competitor_name: str = "") -> dict:
        """Analyse rapide d'un concurrent."""
        prompt = (
            f"Analyse le positionnement marketing de '{competitor_name}' "
            f"dans l'écosystème anime/manga/créatif IA. "
            f"Points forts, faiblesses, opportunités de différenciation. "
            f"Comment OverLord Pipeline peut se différencier ?"
        )
        return {"competitor": competitor_name,
                "analysis": llm_call(prompt, self.SYSTEM, max_tokens=600)}

    def chat(self, message: str, context: dict = None) -> str:
        """Interface de dialogue avec l'agent Marketing."""
        ctx = f"\nContexte projet : {json.dumps(context, ensure_ascii=False)}" if context else ""
        return llm_call(message + ctx, self.SYSTEM, max_tokens=600)

    def _save(self, filename: str, data: dict):
        (OUTPUT_DIR / filename).write_text(
            json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8"
        )

    def _slug(self, s: str) -> str:
        import re
        return re.sub(r'[^a-z0-9_]','_', s.lower())[:30]


# ══════════════════════════════════════════════════════════════════════
# AGENT WEBMASTER
# ══════════════════════════════════════════════════════════════════════

class WebmasterAgent:
    """
    Webmaster — SEO, pages web, déploiement, analytics.
    Génère des pages HTML optimisées pour publier le contenu du pipeline.
    """

    SYSTEM = (
        "Tu es un Webmaster expert en SEO et développement web pour sites de contenu créatif "
        "numérique. Tu génères du HTML/CSS/JS propre et sémantique, optimisé Core Web Vitals. "
        "Tu maîtrises les meta tags, Open Graph, Schema.org, sitemap XML. "
        "Tes pages sont accessibles, rapides (< 100ms LCP) et optimisées pour le référencement."
    )

    PAGE_TEMPLATE = """<!DOCTYPE html>
<html lang="fr">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{title} | OverLord Pipeline</title>
<meta name="description" content="{description}">
<meta property="og:title" content="{title}">
<meta property="og:description" content="{description}">
<meta property="og:image" content="{og_image}">
<meta property="og:type" content="video.movie">
<meta name="twitter:card" content="summary_large_image">
<link rel="canonical" href="{canonical_url}">
<style>
  :root {{
    --bg: #0a0a12; --surface: #16161e; --accent: #7c3aed;
    --text: #e0e0f0; --textd: #7070a0; --radius: 12px;
  }}
  * {{ box-sizing: border-box; margin: 0; padding: 0; }}
  body {{ background: var(--bg); color: var(--text);
          font-family: 'Segoe UI', system-ui, sans-serif; }}
  .hero {{ padding: 60px 20px; text-align: center; max-width: 900px; margin: 0 auto; }}
  .hero h1 {{ font-size: clamp(1.8rem, 5vw, 3rem); color: var(--accent); margin-bottom: 16px; }}
  .hero p {{ font-size: 1.1rem; color: var(--textd); max-width: 600px; margin: 0 auto 24px; }}
  .badge {{ display: inline-block; background: var(--accent); color: white;
             padding: 6px 16px; border-radius: 20px; font-size: 0.85rem; margin: 4px; }}
  .content {{ max-width: 900px; margin: 40px auto; padding: 0 20px; }}
  .video-embed {{ width: 100%; aspect-ratio: 16/9; border-radius: var(--radius);
                   overflow: hidden; background: var(--surface); }}
  .cta {{ display: inline-block; background: var(--accent); color: white;
           padding: 14px 28px; border-radius: var(--radius); text-decoration: none;
           font-weight: 700; margin: 20px 0; transition: opacity .2s; }}
  .cta:hover {{ opacity: 0.85; }}
  footer {{ text-align: center; padding: 40px 20px;
             color: var(--textd); font-size: 0.8rem; }}
</style>
</head>
<body>
<main>
  <div class="hero">
    <h1>{title}</h1>
    <p>{description}</p>
    {badges_html}
    <a class="cta" href="{video_url}">▶ Regarder</a>
  </div>
  <div class="content">
    {content_html}
  </div>
</main>
<footer>
  <p>Créé par OverLord Pipeline v1.0.0-alpha • {date}</p>
</footer>
<script type="application/ld+json">
{schema_json}
</script>
</body>
</html>"""

    def __init__(self, logger: logging.Logger = None):
        self.log = logger or logging.getLogger("webmaster")
        WEB_DIR.mkdir(parents=True, exist_ok=True)

    def generate_page(self, title: str, description: str,
                       content: str = "", tags: list = None,
                       video_url: str = "#",
                       og_image: str = "") -> str:
        """Génère une page HTML complète pour une production."""
        tags = tags or []
        badges = " ".join(f'<span class="badge">{t}</span>' for t in tags[:6])
        slug   = self._slug(title)

        # Générer le contenu enrichi via LLM
        if not content:
            content_raw = llm_call(
                f"Rédige 3 paragraphes engageants en HTML pour présenter : {title}. "
                f"Description : {description}. Style : enthousiaste, fan anime.",
                self.SYSTEM, max_tokens=400
            )
            content = content_raw

        # Schema.org VideoObject
        schema = {
            "@context": "https://schema.org",
            "@type": "VideoObject",
            "name": title,
            "description": description,
            "thumbnailUrl": og_image or "",
            "uploadDate": datetime.utcnow().strftime("%Y-%m-%d"),
            "creator": {"@type": "Organization", "name": "OverLord Pipeline"},
        }

        html = self.PAGE_TEMPLATE.format(
            title=title, description=description,
            badges_html=badges, video_url=video_url,
            og_image=og_image,
            canonical_url=f"/content/{slug}/",
            content_html=content,
            date=datetime.now().strftime("%d/%m/%Y"),
            schema_json=json.dumps(schema, indent=2, ensure_ascii=False),
        )

        out_path = WEB_DIR / f"{slug}.html"
        out_path.write_text(html, encoding="utf-8")
        self.log.info(f"[WEBMASTER] Page générée : {out_path}")
        return str(out_path)

    def generate_sitemap(self, base_url: str = "https://example.com") -> str:
        """Génère un sitemap XML depuis les pages existantes."""
        pages = list(WEB_DIR.glob("*.html"))
        urls  = []
        for p in pages:
            slug = p.stem
            urls.append(
                f"  <url>\n"
                f"    <loc>{base_url}/content/{slug}/</loc>\n"
                f"    <lastmod>{datetime.utcnow().strftime('%Y-%m-%d')}</lastmod>\n"
                f"    <changefreq>weekly</changefreq>\n"
                f"    <priority>0.8</priority>\n"
                f"  </url>"
            )
        sitemap = (
            '<?xml version="1.0" encoding="UTF-8"?>\n'
            '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
            + "\n".join(urls) +
            "\n</urlset>"
        )
        out = WEB_DIR / "sitemap.xml"
        out.write_text(sitemap, encoding="utf-8")
        self.log.info(f"[WEBMASTER] Sitemap : {len(urls)} pages")
        return str(out)

    def seo_audit(self, html_content: str) -> dict:
        """Audit SEO rapide d'une page."""
        issues = []
        score  = 100
        if "<h1>" not in html_content.lower():
            issues.append("H1 manquant"); score -= 20
        if "meta name=\"description\"" not in html_content:
            issues.append("Meta description manquante"); score -= 15
        if "canonical" not in html_content:
            issues.append("Balise canonical manquante"); score -= 10
        if "og:image" not in html_content:
            issues.append("Open Graph image manquante"); score -= 10
        if "application/ld+json" not in html_content:
            issues.append("Schema.org absent"); score -= 10
        return {"score": max(0, score), "issues": issues,
                "status": "bon" if score >= 80 else "à améliorer"}

    def chat(self, message: str, context: dict = None) -> str:
        ctx = f"\nContexte : {json.dumps(context, ensure_ascii=False)}" if context else ""
        return llm_call(message + ctx, self.SYSTEM, max_tokens=500)

    def _slug(self, s: str) -> str:
        import re
        return re.sub(r'[^a-z0-9-]','-', s.lower())[:40].strip('-')


# ══════════════════════════════════════════════════════════════════════
# AGENT COMMUNITY MANAGER
# ══════════════════════════════════════════════════════════════════════

@dataclass
class SocialPost:
    platform:  str
    content:   str
    hashtags:  list = field(default_factory=list)
    media_url: str  = ""
    scheduled: str  = ""  # ISO datetime
    status:    str  = "draft"


class CommunityManagerAgent:
    """
    Community Manager — posts, calendrier éditorial, réponses communauté.
    Adapte le ton et le format à chaque plateforme.
    """

    SYSTEM = (
        "Tu es un Community Manager passionné par la culture anime/manga et le contenu créatif IA. "
        "Tu maîtrises les codes de chaque plateforme : énergique et concis sur X/Twitter, "
        "visuel et inspirant sur Instagram, technique et détaillé sur Reddit, "
        "fun et dynamique sur TikTok. Tu crées de l'engagement authentique, "
        "tu réponds aux commentaires avec empathie et tu gères les critiques avec professionnalisme."
    )

    PLATFORM_LIMITS = {
        "X/Twitter":    280,
        "Instagram":    2200,
        "TikTok":       150,
        "Reddit":       40000,
        "Discord":      2000,
        "YouTube":      500,
        "LinkedIn":     3000,
    }

    def __init__(self, logger: logging.Logger = None):
        self.log   = logger or logging.getLogger("community")
        self._posts: list[SocialPost] = []
        SOCIAL_DIR.mkdir(parents=True, exist_ok=True)

    def create_post(self, content_title: str, content_summary: str,
                     platform: str = "X/Twitter",
                     tone: str = "enthousiaste") -> SocialPost:
        """Crée un post optimisé pour une plateforme."""
        limit   = self.PLATFORM_LIMITS.get(platform, 280)
        prompt  = (
            f"Crée un post {platform} pour ce contenu :\n"
            f"Titre : {content_title}\nRésumé : {content_summary}\n\n"
            f"Ton : {tone}\nLimite : {limit} caractères\n"
            f"Inclure des hashtags pertinents (5 max).\n"
            f"Format : d'abord le texte du post, puis une ligne 'HASHTAGS:' avec les tags."
        )
        result   = llm_call(prompt, self.SYSTEM, max_tokens=400)
        hashtags = []
        post_text = result

        if "HASHTAGS:" in result:
            parts    = result.split("HASHTAGS:")
            post_text = parts[0].strip()
            hashtags  = [h.strip() for h in parts[1].strip().split()
                         if h.startswith("#")]

        post = SocialPost(
            platform=platform,
            content=post_text[:limit],
            hashtags=hashtags,
        )
        self._posts.append(post)
        return post

    def create_multi_platform(self, content_title: str,
                               content_summary: str,
                               platforms: list = None) -> dict[str, SocialPost]:
        """Crée des posts adaptés pour toutes les plateformes en parallèle."""
        platforms = platforms or ["X/Twitter","Reddit","TikTok","Instagram"]
        results   = {}

        def _make(platform):
            results[platform] = self.create_post(
                content_title, content_summary, platform
            )

        threads = [threading.Thread(target=_make, args=(p,), daemon=True)
                   for p in platforms]
        for t in threads: t.start()
        for t in threads: t.join(timeout=30)

        self.log.info(
            f"[COMMUNITY] {len(results)} posts créés pour : "
            f"{', '.join(results.keys())}"
        )
        return results

    def generate_editorial_calendar(self, content_list: list[str],
                                     start_date: str = None,
                                     frequency: str = "daily") -> list[dict]:
        """Génère un calendrier éditorial."""
        if not start_date:
            start_date = datetime.now().strftime("%Y-%m-%d")

        start     = datetime.fromisoformat(start_date)
        calendar  = []
        freq_days = {"daily":1, "twice_weekly":3, "weekly":7}.get(frequency, 1)

        for i, content in enumerate(content_list):
            pub_date = start + timedelta(days=i * freq_days)
            calendar.append({
                "date":      pub_date.strftime("%Y-%m-%d"),
                "content":   content,
                "platforms": ["X/Twitter", "Reddit"],
                "status":    "planned",
            })

        out = SOCIAL_DIR / "editorial_calendar.json"
        out.write_text(json.dumps(calendar, indent=2, ensure_ascii=False),
                       encoding="utf-8")
        self.log.info(f"[COMMUNITY] Calendrier : {len(calendar)} publications")
        return calendar

    def write_community_response(self, comment: str, context: str = "",
                                  tone: str = "amical") -> str:
        """Génère une réponse à un commentaire de la communauté."""
        prompt = (
            f"Rédige une réponse {tone} à ce commentaire :\n"
            f"'{comment}'\n\n"
            f"Contexte : {context or 'créateur de contenu anime IA'}\n"
            f"Max 280 caractères, authentique, pas de formules génériques."
        )
        return llm_call(prompt, self.SYSTEM, max_tokens=150)

    def moderate_comment(self, comment: str) -> dict:
        """Évalue si un commentaire nécessite une modération."""
        prompt = (
            f"Évalue ce commentaire pour modération :\n'{comment}'\n\n"
            f"Réponds en JSON : {{\"action\": \"approve|flag|remove\", "
            f"\"reason\": \"raison\", \"response_suggested\": \"réponse si needed\"}}"
        )
        result = llm_call(prompt, self.SYSTEM, max_tokens=200)
        try:
            return json.loads(result)
        except Exception:
            return {"action": "approve", "reason": "Commentaire neutre"}

    def get_engagement_report(self) -> dict:
        """Rapport sur les posts créés."""
        by_platform = {}
        for post in self._posts:
            by_platform[post.platform] = by_platform.get(post.platform, 0) + 1
        return {
            "total_posts":   len(self._posts),
            "by_platform":   by_platform,
            "drafts":        sum(1 for p in self._posts if p.status == "draft"),
            "published":     sum(1 for p in self._posts if p.status == "published"),
        }

    def chat(self, message: str, context: dict = None) -> str:
        ctx = f"\nContexte : {json.dumps(context, ensure_ascii=False)}" if context else ""
        return llm_call(message + ctx, self.SYSTEM, max_tokens=500)

    def save_posts(self):
        data = [{
            "platform": p.platform, "content": p.content,
            "hashtags": p.hashtags, "status": p.status,
            "scheduled": p.scheduled,
        } for p in self._posts]
        (SOCIAL_DIR / "posts.json").write_text(
            json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8"
        )


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    log = logging.getLogger("agents_test")

    # Test Marketing
    mkt = MarketingAgent(log)
    campaign = mkt.generate_campaign(
        "Dragon Ball Super — Court Métrage IA",
        content_type="anime_short",
        target_platforms=["YouTube","TikTok","X/Twitter"]
    )
    print(f"\n[MARKETING] Plan :\n{campaign['plan'][:300]}...")

    # Test Community
    cm = CommunityManagerAgent(log)
    posts = cm.create_multi_platform(
        "Dragon Ball Super — Court Métrage IA",
        "Un court métrage anime généré par IA en moins de 2h",
        platforms=["X/Twitter","Reddit"]
    )
    for platform, post in posts.items():
        print(f"\n[{platform}] {post.content[:100]}...")
        if post.hashtags:
            print(f"  Tags : {' '.join(post.hashtags)}")

    # Test Webmaster
    wb = WebmasterAgent(log)
    page = wb.generate_page(
        "Dragon Ball Super — Court Métrage IA",
        "Premier anime généré entièrement par IA avec OverLord Pipeline",
        tags=["anime","IA","ComfyUI","SDXL","DragonBall"]
    )
    print(f"\n[WEBMASTER] Page : {page}")
    audit = wb.seo_audit(open(page).read() if Path(page).exists() else "")
    print(f"  SEO Score : {audit['score']}/100 | Issues : {audit['issues']}")

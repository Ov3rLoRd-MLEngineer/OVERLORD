"""
agents/social_agent.py — Agent Réseaux Sociaux OverLord
Connexion aux plateformes via leurs APIs officielles.

IMPORTANT — Pourquoi pas email/mdp direct ?
  - Gmail/Meta/Twitter bloquent et bannissent les connexions directes
  - Risque de sécurité : stocker des mdp en clair = vulnérabilité critique
  - Solution propre : APIs officielles + OAuth (tokens, pas mdp)

SETUP PAR PLATEFORME :

  GMAIL :
    1. console.cloud.google.com → Nouveau projet → "OverLord"
    2. APIs & Services → Gmail API → Activer
    3. Credentials → OAuth 2.0 → Télécharger credentials.json
    4. pip install google-auth google-auth-oauthlib google-api-python-client

  TWITTER/X :
    1. developer.twitter.com → New App → "OverLord Pipeline"
    2. Récupérer : API Key, API Secret, Access Token, Access Secret
    3. pip install tweepy

  INSTAGRAM (via Facebook Graph API) :
    1. developers.facebook.com → New App → Business
    2. Ajouter Instagram Graph API
    3. Récupérer le Page Access Token longue durée
    4. pip install requests

  FACEBOOK :
    1. Même app que Instagram (Meta unifié)
    2. Ajouter Pages API
    3. Même token
"""

import json
import logging
import threading
import time
from pathlib import Path
from datetime import datetime
from dataclasses import dataclass, field
from typing import Optional
import requests

CONFIG_FILE = Path("workspace/social_config.json")
POSTS_LOG   = Path("workspace/social_posts.json")


@dataclass
class SocialPost:
    platform:   str
    content:    str
    media_url:  str = ""
    post_id:    str = ""
    timestamp:  str = field(default_factory=lambda: datetime.utcnow().isoformat())
    status:     str = "pending"  # pending/sent/failed
    error:      str = ""


def load_social_config() -> dict:
    if CONFIG_FILE.exists():
        try:
            return json.loads(CONFIG_FILE.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {}


def save_social_config(cfg: dict):
    CONFIG_FILE.parent.mkdir(parents=True, exist_ok=True)
    CONFIG_FILE.write_text(
        json.dumps(cfg, indent=2, ensure_ascii=False), encoding="utf-8"
    )


# ══════════════════════════════════════════════════════════════════════
# GMAIL
# ══════════════════════════════════════════════════════════════════════

class GmailAgent:
    """
    Envoie et lit des emails via l'API Gmail officielle.
    Setup : credentials.json depuis Google Cloud Console.
    """

    SCOPES = [
        "https://www.googleapis.com/auth/gmail.send",
        "https://www.googleapis.com/auth/gmail.readonly",
        "https://www.googleapis.com/auth/gmail.modify",
    ]

    def __init__(self, credentials_path: str = "credentials.json",
                 logger: logging.Logger = None):
        self.log         = logger or logging.getLogger("gmail")
        self.creds_path  = credentials_path
        self._service    = None
        self._connected  = False

    def connect(self) -> bool:
        """Authentification OAuth Gmail."""
        try:
            from google.auth.transport.requests import Request
            from google.oauth2.credentials import Credentials
            from google_auth_oauthlib.flow import InstalledAppFlow
            from googleapiclient.discovery import build

            token_path = Path("workspace/gmail_token.json")
            creds      = None

            if token_path.exists():
                creds = Credentials.from_authorized_user_file(str(token_path), self.SCOPES)

            if not creds or not creds.valid:
                if creds and creds.expired and creds.refresh_token:
                    creds.refresh(Request())
                else:
                    flow = InstalledAppFlow.from_client_secrets_file(
                        self.creds_path, self.SCOPES
                    )
                    # Lance le navigateur pour l'auth — UNE SEULE FOIS
                    creds = flow.run_local_server(port=0)
                token_path.parent.mkdir(parents=True, exist_ok=True)
                token_path.write_text(creds.to_json())

            self._service   = build("gmail", "v1", credentials=creds)
            self._connected = True
            self.log.info("[GMAIL] ✓ Connecté via OAuth")
            return True

        except ImportError:
            self.log.error("[GMAIL] pip install google-auth google-auth-oauthlib google-api-python-client")
            return False
        except Exception as e:
            self.log.error(f"[GMAIL] Connexion : {e}")
            return False

    def send(self, to: str, subject: str, body: str,
              html: bool = False) -> bool:
        """Envoie un email."""
        if not self._connected:
            if not self.connect():
                return False
        import base64
        from email.mime.text import MIMEText

        mime_type = "html" if html else "plain"
        msg       = MIMEText(body, mime_type, "utf-8")
        msg["To"]      = to
        msg["Subject"] = subject

        raw = base64.urlsafe_b64encode(msg.as_bytes()).decode()
        try:
            self._service.users().messages().send(
                userId="me", body={"raw": raw}
            ).execute()
            self.log.info(f"[GMAIL] ✓ Email envoyé → {to}")
            return True
        except Exception as e:
            self.log.error(f"[GMAIL] Envoi : {e}")
            return False

    def get_unread(self, max_results: int = 10) -> list[dict]:
        """Récupère les emails non lus."""
        if not self._connected:
            if not self.connect():
                return []
        try:
            result = self._service.users().messages().list(
                userId="me", labelIds=["UNREAD"], maxResults=max_results
            ).execute()
            messages = result.get("messages", [])
            emails   = []
            for msg in messages:
                data = self._service.users().messages().get(
                    userId="me", id=msg["id"], format="metadata",
                    metadataHeaders=["From","Subject","Date"]
                ).execute()
                headers = {h["name"]: h["value"]
                           for h in data.get("payload",{}).get("headers",[])}
                emails.append({
                    "id":      msg["id"],
                    "from":    headers.get("From",""),
                    "subject": headers.get("Subject",""),
                    "date":    headers.get("Date",""),
                    "snippet": data.get("snippet",""),
                })
            return emails
        except Exception as e:
            self.log.error(f"[GMAIL] get_unread : {e}")
            return []

    def send_production_report(self, recipient: str,
                                run_summary: dict) -> bool:
        """Envoie un rapport de production par email."""
        subject = f"OverLord Pipeline — Rapport {datetime.now().strftime('%d/%m/%Y %H:%M')}"
        html_body = f"""
<html><body style="font-family:Arial;background:#0A0A12;color:#E0E0F0;padding:20px">
<h2 style="color:#7C3AED">⬡ OverLord Pipeline — Rapport de Production</h2>
<table style="width:100%;border-collapse:collapse">
  <tr><td style="padding:8px;border-bottom:1px solid #2A2A3E"><b>Run ID</b></td>
      <td>{run_summary.get("run_id","?")}</td></tr>
  <tr><td style="padding:8px;border-bottom:1px solid #2A2A3E"><b>Média</b></td>
      <td>{run_summary.get("media_type","?")}</td></tr>
  <tr><td style="padding:8px;border-bottom:1px solid #2A2A3E"><b>Images générées</b></td>
      <td>{run_summary.get("images_generated",0)}</td></tr>
  <tr><td style="padding:8px;border-bottom:1px solid #2A2A3E"><b>Score qualité</b></td>
      <td>{run_summary.get("quality_score",0):.1f}/100</td></tr>
  <tr><td style="padding:8px"><b>Durée</b></td>
      <td>{run_summary.get("duration_s",0):.0f}s</td></tr>
</table>
<p style="color:#7070A8;margin-top:20px;font-size:12px">OverLord Pipeline v1.0.0-alpha</p>
</body></html>"""
        return self.send(recipient, subject, html_body, html=True)


# ══════════════════════════════════════════════════════════════════════
# TWITTER / X
# ══════════════════════════════════════════════════════════════════════

class TwitterAgent:
    """
    Tweete via l'API Twitter/X officielle (Tweepy).
    Nécessite un compte développeur : developer.twitter.com
    """

    def __init__(self, api_key: str = "", api_secret: str = "",
                 access_token: str = "", access_secret: str = "",
                 bearer_token: str = "",
                 logger: logging.Logger = None):
        self.log          = logger or logging.getLogger("twitter")
        self.api_key      = api_key
        self.api_secret   = api_secret
        self.access_token = access_token
        self.access_secret= access_secret
        self.bearer_token = bearer_token
        self._client      = None
        self._api_v1      = None

    def connect(self) -> bool:
        try:
            import tweepy
            # Client v2 (pour tweeter)
            self._client = tweepy.Client(
                bearer_token    = self.bearer_token,
                consumer_key    = self.api_key,
                consumer_secret = self.api_secret,
                access_token    = self.access_token,
                access_token_secret = self.access_secret,
                wait_on_rate_limit = True,
            )
            # API v1.1 (pour uploader des médias)
            auth = tweepy.OAuthHandler(self.api_key, self.api_secret)
            auth.set_access_token(self.access_token, self.access_secret)
            self._api_v1 = tweepy.API(auth)
            self.log.info("[TWITTER] ✓ Connecté")
            return True
        except ImportError:
            self.log.error("[TWITTER] pip install tweepy")
            return False
        except Exception as e:
            self.log.error(f"[TWITTER] Connexion : {e}")
            return False

    def tweet(self, text: str, image_path: str = "") -> dict:
        """Publie un tweet avec ou sans image."""
        if not self._client:
            if not self.connect():
                return {"error": "non connecté"}
        try:
            media_ids = []
            if image_path and Path(image_path).exists():
                media    = self._api_v1.media_upload(image_path)
                media_ids = [media.media_id]

            # Limiter à 280 caractères
            text = text[:280]
            resp = self._client.create_tweet(
                text=text,
                media_ids=media_ids if media_ids else None,
            )
            tweet_id = resp.data.get("id","?")
            self.log.info(f"[TWITTER] ✓ Tweet publié : {tweet_id}")
            return {"tweet_id": tweet_id, "text": text}
        except Exception as e:
            self.log.error(f"[TWITTER] Tweet : {e}")
            return {"error": str(e)}

    def get_mentions(self, max_results: int = 10) -> list[dict]:
        """Récupère les mentions récentes."""
        if not self._client:
            return []
        try:
            me   = self._client.get_me()
            user_id = me.data.id
            resp = self._client.get_users_mentions(
                id=user_id, max_results=max_results
            )
            return [{"id": t.id, "text": t.text}
                    for t in (resp.data or [])]
        except Exception as e:
            self.log.error(f"[TWITTER] mentions : {e}")
            return []

    def thread(self, tweets: list[str],
                image_paths: list[str] = None) -> list[dict]:
        """Publie un fil de tweets."""
        image_paths = image_paths or []
        results     = []
        reply_to    = None

        for i, text in enumerate(tweets):
            img = image_paths[i] if i < len(image_paths) else ""
            if not self._client:
                if not self.connect():
                    break

            try:
                media_ids = []
                if img and Path(img).exists():
                    media     = self._api_v1.media_upload(img)
                    media_ids = [media.media_id]

                kwargs = {
                    "text": text[:280],
                    "media_ids": media_ids if media_ids else None,
                }
                if reply_to:
                    kwargs["in_reply_to_tweet_id"] = reply_to

                resp     = self._client.create_tweet(**kwargs)
                tweet_id = resp.data.get("id","?")
                reply_to = tweet_id
                results.append({"tweet_id": tweet_id, "position": i+1})
                time.sleep(1)   # éviter le rate limit
            except Exception as e:
                self.log.error(f"[TWITTER] Thread {i+1} : {e}")
                break

        self.log.info(f"[TWITTER] ✓ Fil publié : {len(results)}/{len(tweets)} tweets")
        return results


# ══════════════════════════════════════════════════════════════════════
# INSTAGRAM (Graph API)
# ══════════════════════════════════════════════════════════════════════

class InstagramAgent:
    """
    Publie sur Instagram via l'API Graph Meta officielle.
    Nécessite un compte Business/Creator + Page Facebook liée.
    """

    BASE_URL = "https://graph.instagram.com"

    def __init__(self, access_token: str = "",
                 ig_user_id: str = "",
                 logger: logging.Logger = None):
        self.log          = logger or logging.getLogger("instagram")
        self.access_token = access_token
        self.ig_user_id   = ig_user_id

    def post_image(self, image_url: str, caption: str = "") -> dict:
        """
        Publie une image sur Instagram.
        image_url : URL publique de l'image (pas un chemin local)
        → Pour un fichier local, uploader d'abord sur un hébergement
        """
        if not self.access_token or not self.ig_user_id:
            self.log.error("[INSTAGRAM] access_token et ig_user_id requis")
            return {"error": "config manquante"}
        try:
            # Étape 1 : créer le container média
            r1 = requests.post(
                f"https://graph.facebook.com/v18.0/{self.ig_user_id}/media",
                params={
                    "image_url":    image_url,
                    "caption":      caption[:2200],
                    "access_token": self.access_token,
                }
            )
            r1.raise_for_status()
            container_id = r1.json().get("id")

            # Étape 2 : publier le container
            time.sleep(5)  # laisser Instagram traiter
            r2 = requests.post(
                f"https://graph.facebook.com/v18.0/{self.ig_user_id}/media_publish",
                params={
                    "creation_id":  container_id,
                    "access_token": self.access_token,
                }
            )
            r2.raise_for_status()
            post_id = r2.json().get("id","?")
            self.log.info(f"[INSTAGRAM] ✓ Post publié : {post_id}")
            return {"post_id": post_id, "caption": caption[:50]}
        except Exception as e:
            self.log.error(f"[INSTAGRAM] Post : {e}")
            return {"error": str(e)}

    def get_insights(self) -> dict:
        """Récupère les statistiques du compte."""
        try:
            r = requests.get(
                f"https://graph.facebook.com/v18.0/{self.ig_user_id}/insights",
                params={
                    "metric":       "impressions,reach,profile_views",
                    "period":       "day",
                    "access_token": self.access_token,
                }
            )
            return r.json()
        except Exception as e:
            self.log.error(f"[INSTAGRAM] Insights : {e}")
            return {}


# ══════════════════════════════════════════════════════════════════════
# FACEBOOK (Graph API)
# ══════════════════════════════════════════════════════════════════════

class FacebookAgent:
    """
    Publie sur une Page Facebook via l'API Graph Meta officielle.
    """

    def __init__(self, page_access_token: str = "",
                 page_id: str = "",
                 logger: logging.Logger = None):
        self.log   = logger or logging.getLogger("facebook")
        self.token = page_access_token
        self.page_id = page_id

    def post(self, message: str, image_url: str = "",
              link: str = "") -> dict:
        """Publie sur la Page Facebook."""
        if not self.token or not self.page_id:
            self.log.error("[FACEBOOK] page_access_token et page_id requis")
            return {"error": "config manquante"}
        try:
            if image_url:
                r = requests.post(
                    f"https://graph.facebook.com/v18.0/{self.page_id}/photos",
                    params={
                        "url":          image_url,
                        "message":      message,
                        "access_token": self.token,
                    }
                )
            else:
                payload = {"message": message, "access_token": self.token}
                if link:
                    payload["link"] = link
                r = requests.post(
                    f"https://graph.facebook.com/v18.0/{self.page_id}/feed",
                    params=payload,
                )
            r.raise_for_status()
            post_id = r.json().get("id","?")
            self.log.info(f"[FACEBOOK] ✓ Post publié : {post_id}")
            return {"post_id": post_id}
        except Exception as e:
            self.log.error(f"[FACEBOOK] Post : {e}")
            return {"error": str(e)}

    def get_page_insights(self) -> dict:
        """Statistiques de la page."""
        try:
            r = requests.get(
                f"https://graph.facebook.com/v18.0/{self.page_id}/insights",
                params={
                    "metric":       "page_impressions,page_reach,page_fans",
                    "period":       "day",
                    "access_token": self.token,
                }
            )
            return r.json()
        except Exception as e:
            return {"error": str(e)}


# ══════════════════════════════════════════════════════════════════════
# AGENT SOCIAL UNIFIÉ
# ══════════════════════════════════════════════════════════════════════

class SocialAgent:
    """
    Agent unifié qui gère toutes les plateformes.
    Configure une fois, publie partout.
    """

    def __init__(self, logger: logging.Logger = None):
        self.log     = logger or logging.getLogger("social")
        self._config = load_social_config()
        self._posts: list[SocialPost] = []

        # Initialiser les agents selon la config disponible
        gmail_cfg = self._config.get("gmail",{})
        self.gmail = GmailAgent(
            credentials_path=gmail_cfg.get("credentials_path","credentials.json"),
            logger=self.log
        ) if gmail_cfg else None

        tw_cfg = self._config.get("twitter",{})
        self.twitter = TwitterAgent(
            api_key       = tw_cfg.get("api_key",""),
            api_secret    = tw_cfg.get("api_secret",""),
            access_token  = tw_cfg.get("access_token",""),
            access_secret = tw_cfg.get("access_secret",""),
            bearer_token  = tw_cfg.get("bearer_token",""),
            logger        = self.log,
        ) if tw_cfg else None

        ig_cfg = self._config.get("instagram",{})
        self.instagram = InstagramAgent(
            access_token = ig_cfg.get("access_token",""),
            ig_user_id   = ig_cfg.get("ig_user_id",""),
            logger       = self.log,
        ) if ig_cfg else None

        fb_cfg = self._config.get("facebook",{})
        self.facebook = FacebookAgent(
            page_access_token = fb_cfg.get("page_access_token",""),
            page_id           = fb_cfg.get("page_id",""),
            logger            = self.log,
        ) if fb_cfg else None

    def configure(self, platform: str, **kwargs):
        """Configure une plateforme et sauvegarde."""
        self._config[platform] = kwargs
        save_social_config(self._config)
        self.log.info(f"[SOCIAL] {platform} configuré ✓")
        # Réinitialiser l'agent
        self.__init__(logger=self.log)

    def publish_all(self, text: str,
                     image_url: str = "",
                     image_path: str = "",
                     platforms: list[str] = None) -> dict:
        """
        Publie sur toutes les plateformes configurées.
        platforms=None → toutes les plateformes disponibles.
        """
        platforms = platforms or ["twitter","instagram","facebook"]
        results   = {}

        for platform in platforms:
            if platform == "twitter" and self.twitter:
                results["twitter"] = self.twitter.tweet(text, image_path)
            elif platform == "instagram" and self.instagram and image_url:
                results["instagram"] = self.instagram.post_image(
                    image_url, text
                )
            elif platform == "facebook" and self.facebook:
                results["facebook"] = self.facebook.post(text, image_url)

        self.log.info(
            f"[SOCIAL] Publication multi-plateforme : "
            f"{[p for p,r in results.items() if 'error' not in r]}"
        )
        return results

    def publish_production_result(self, run_summary: dict,
                                   best_image_url: str = "",
                                   best_image_path: str = "") -> dict:
        """
        Publie automatiquement le résultat d'une production OverLord.
        Génère les textes adaptés à chaque plateforme.
        """
        media_type = run_summary.get("media_type","anime")
        score      = run_summary.get("quality_score", 0)
        universe   = run_summary.get("universe","")

        # Twitter : court et percutant
        tw_text = (
            f"✨ Nouvelle création IA OverLord Pipeline !\n"
            f"Type : #{media_type}\n"
            + (f"Univers : {universe}\n" if universe else "")
            + f"Score qualité : {score:.0f}/100\n"
            f"#AIArt #AnimeAI #OverLord #GenerativeAI"
        )

        # Instagram : plus descriptif
        ig_text = (
            f"🎌 Nouvelle production IA — {media_type.title()}\n\n"
            + (f"Univers : {universe}\n" if universe else "")
            + f"Généré avec OverLord Pipeline — notre usine à animés IA.\n"
            f"Score de qualité automatique : {score:.0f}/100\n\n"
            f"#AIArt #AnimeAI #OverLord #GenerativeAI #StableDiffusion #ComfyUI"
        )

        results = {}
        if self.twitter:
            results["twitter"] = self.twitter.tweet(tw_text, best_image_path)
        if self.instagram and best_image_url:
            results["instagram"] = self.instagram.post_image(best_image_url, ig_text)
        if self.facebook:
            results["facebook"] = self.facebook.post(ig_text, best_image_url)

        return results

    def get_status(self) -> dict:
        return {
            "gmail":     self.gmail is not None,
            "twitter":   self.twitter is not None,
            "instagram": self.instagram is not None,
            "facebook":  self.facebook is not None,
            "configured": list(self._config.keys()),
        }


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    agent = SocialAgent()
    print("Status :", agent.get_status())

    print("""
=== CONFIGURATION RAPIDE ===

# Twitter/X
agent.configure("twitter",
    api_key       = "xxx",
    api_secret    = "xxx",
    access_token  = "xxx",
    access_secret = "xxx",
    bearer_token  = "xxx",
)

# Instagram
agent.configure("instagram",
    access_token = "xxx",  # Page Access Token longue durée
    ig_user_id   = "xxx",  # ID du compte Instagram Business
)

# Facebook
agent.configure("facebook",
    page_access_token = "xxx",
    page_id           = "xxx",
)

# Gmail
agent.configure("gmail",
    credentials_path = "credentials.json",  # téléchargé depuis Google Cloud
)

# Publier partout
results = agent.publish_all(
    "Nouvelle création OverLord Pipeline !",
    image_url  = "https://ton-serveur.com/image.jpg",
    image_path = "workspace/archive/image.png",
)
""")

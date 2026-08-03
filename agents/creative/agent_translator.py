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
agents/agent_translator.py — Agent Traducteur Multilingue V1.70
Gère les échanges FR/EN/JP dans le pipeline Ov3rLoRd.

Règles :
  1. Prompts LLM internes → ANGLAIS (meilleure fiabilité JSON)
  2. Si l'interlocuteur performe mieux en anglais → anglais
  3. Si l'interlocuteur performe mieux en français → français
  4. Support japonais : kanji, hiragana, katakana, romaji, calligraphie standard

Le français directif et simplifié garde une richesse sémantique
que l'anglais directif perd — utilisé pour les prompts créatifs complexes.

Usage :
  from agents.agent_translator import translate, detect_language, to_booru_en
  prompt_en = to_booru_en("fille en combinaison de pilote rouge, combat épique")
  jp_text   = translate("Bienvenue dans Ov3rLoRd", target="ja")
"""

import logging
import re
import sys
import io
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

# ── Dictionnaires statiques — zéro appel LLM pour les cas courants ───

# Termes anime/Booru FR → EN (enrichissement prompt sans LLM)
BOORU_FR_EN = {
    "fille":             "1girl",
    "garçon":            "1boy",
    "combat":            "battle, action shot",
    "épique":            "epic, dramatic",
    "pilote":            "pilot",
    "combinaison":       "plug suit",
    "rouge":             "red",
    "bleu":              "blue",
    "blanc":             "white",
    "noir":              "black",
    "cheveux longs":     "long hair",
    "cheveux courts":    "short hair",
    "yeux bleus":        "blue eyes",
    "yeux rouges":       "red eyes",
    "regard intense":    "intense gaze, sharp eyes",
    "regard déterminé":  "determined expression",
    "fond urbain":       "urban background, cityscape",
    "fond détruit":      "destroyed city, ruins",
    "coucher de soleil": "sunset, golden hour",
    "nuit":              "night scene, moonlight",
    "mechas":            "giant mecha, robot",
    "explosion":         "explosion, blast",
    "maîtrise":          "masterpiece",
    "haute qualité":     "best quality",
    "très détaillé":     "highly detailed",
    "style anime":       "anime style",
}

# Phrases clés Ov3rLoRd en japonais (calligraphie + romaji)
OV3RLORD_JP = {
    "Ov3rLoRd":          {"kanji": "", "romaji": "Ov3rLoRd",
                               "meaning": "Groupe de l'explosion démonique"},
    "Production IA":         {"kanji": "AI制作", "romaji": "AI Seisaku",
                               "meaning": "Production par IA"},
    "Animation autonome":    {"kanji": "自律アニメーション", "romaji": "Jiritsu Animation",
                               "meaning": "Animation autonome"},
    "Bienvenue":             {"kanji": "ようこそ", "romaji": "Yōkoso"},
    "Pipeline de création":  {"kanji": "制作パイプライン", "romaji": "Seisaku Pipeline"},
    "Usine à animés":        {"kanji": "アニメ工場", "romaji": "Anime Kōjō"},
    "Intelligence artificielle": {"kanji": "人工知能", "romaji": "Jinkō Chino"},
    "Personnage":            {"kanji": "キャラクター", "romaji": "Kyarakutā"},
    "Scénario":              {"kanji": "シナリオ", "romaji": "Shinario"},
    "Storyboard":            {"kanji": "絵コンテ", "romaji": "Ekonte"},
    "Generateur d'images":   {"kanji": "画像生成AI", "romaji": "Gazō Seisei AI"},
}

# Détection de langue simple (heuristique)
def detect_language(text: str) -> str:
    """Détecte la langue dominante : 'fr', 'en', 'ja'."""
    text = text.lower()

    # Japonais : présence de caractères JP
    jp_chars = sum(1 for c in text if '\u3040' <= c <= '\u9fff')
    if jp_chars > 3:
        return "ja"

    # Marqueurs français
    fr_markers = ["le ", "la ", "les ", "de ", "du ", "des ", "un ", "une ",
                  "est ", "sont ", "avec ", "pour ", "dans ", "sur ", "à ",
                  "je ", "tu ", "il ", "nous ", "vous ", "ils ", "très ",
                  "ça ", "c'est ", "qu'", "d'", "l'"]
    fr_score = sum(1 for m in fr_markers if m in text)

    # Marqueurs anglais
    en_markers = ["the ", "a ", "an ", "is ", "are ", "with ", "for ",
                  "in ", "on ", "at ", "to ", "of ", "and ", "or ",
                  "this ", "that ", "it ", "we ", "you ", "they "]
    en_score = sum(1 for m in en_markers if m in text)

    if fr_score > en_score and fr_score > 2:
        return "fr"
    if en_score > fr_score and en_score > 2:
        return "en"
    return "en"  # défaut anglais


def to_booru_en(french_prompt: str) -> str:
    """
    Convertit un prompt créatif français en tags Booru anglais.
    Utilise d'abord le dictionnaire statique, puis LLM si nécessaire.
    """
    result = french_prompt.lower()
    replacements_done = []

    for fr, en in BOORU_FR_EN.items():
        if fr in result:
            result = result.replace(fr, en)
            replacements_done.append(fr)

    # Ajouter les quality tokens si absents
    if "masterpiece" not in result and "maîtrise" not in french_prompt.lower():
        result = "masterpiece, best quality, highly detailed, " + result

    return result


def translate(text: str, target: str = "en",
              context: str = "general",
              logger=None) -> str:
    """
    Traduit un texte vers la langue cible.
    target : 'en' | 'fr' | 'ja'
    context : 'general' | 'booru' | 'technical' | 'creative'

    Pour le japonais : retourne kanji + romaji entre parenthèses.
    """
    log = logger or logging.getLogger("agent_translator")

    # Cas trivial : même langue
    src_lang = detect_language(text)
    if src_lang == target:
        return text

    # Booru FR → EN : dictionnaire statique (rapide, sans LLM)
    if target == "en" and context == "booru":
        return to_booru_en(text)

    # Lookup statique pour les termes Ov3rLoRd
    if target == "ja":
        for term, jp_data in OV3RLORD_JP.items():
            if term.lower() in text.lower():
                kanji  = jp_data.get("kanji", "")
                romaji = jp_data.get("romaji", "")
                return f"{kanji}（{romaji}）"

    # LLM pour les cas complexes
    if not UTILS_OK:
        log.warning("[TRANSLATOR] overlord_utils indisponible — traduction impossible")
        return text

    lang_names = {"en": "English", "fr": "French", "ja": "Japanese"}
    target_name = lang_names.get(target, target)

    jp_note = ""
    if target == "ja":
        jp_note = (
            "For Japanese: provide kanji/kana AND romaji in parentheses. "
            "Format: 日本語テキスト（Romaji text）. "
            "Use natural, polite Japanese appropriate for professional context. "
        )

    system = (
        f"You are a professional translator specializing in anime, technology, and creative content. "
        f"Translate the given text to {target_name}. "
        f"{jp_note}"
        f"Reply ONLY with the translated text, nothing else."
    )
    prompt = f"Translate to {target_name}:\n\n{text}"

    result = fallback_llm(prompt, system=system, max_tokens=500, logger=log)
    return result.strip() if result.strip() else text


def optimize_prompt_language(prompt: str, target_llm: str = "mistral",
                              logger=None) -> str:
    """
    Optimise la langue d'un prompt selon le LLM cible.
    mistral → anglais (meilleure fiabilité JSON)
    claude  → anglais ou français selon complexité
    grok    → anglais
    """
    log = logger or logging.getLogger("agent_translator")
    src_lang = detect_language(prompt)

    # Pour tous les LLM en mode JSON strict → anglais obligatoire
    if src_lang == "fr":
        log.debug(f"[TRANSLATOR] Prompt FR → EN pour {target_llm}")
        result = translate(prompt, target="en", context="technical", logger=log)
        return result

    return prompt


def get_jp_glossary() -> dict:
    """Retourne le glossaire japonais complet du projet."""
    glossary = dict(OV3RLORD_JP)
    # Termes techniques supplémentaires
    extras = {
        "Evangelion":       {"kanji": "エヴァンゲリオン", "romaji": "Evangerion"},
        "Gundam":           {"kanji": "ガンダム", "romaji": "Gandamu"},
        "Hatsune Miku":     {"kanji": "初音ミク", "romaji": "Hatsune Miku"},
        "Anime":            {"kanji": "アニメ", "romaji": "Anime"},
        "Manga":            {"kanji": "漫画", "romaji": "Manga"},
        "Mecha":            {"kanji": "メカ", "romaji": "Meka"},
        "Pilot":            {"kanji": "パイロット", "romaji": "Pairotto"},
        "Ov3rLoRd":         {"kanji": "オーバーロード", "romaji": "Ōbārōdo"},
        "Maître":           {"kanji": "主", "romaji": "Aruji"},
        "Victoire":         {"kanji": "勝利", "romaji": "Shōri"},
    }
    glossary.update(extras)
    return glossary


def print_jp_glossary():
    """Affiche le glossaire japonais formaté."""
    g = get_jp_glossary()
    print(f"\n{'─'*60}")
    print(f"  GLOSSAIRE JAPONAIS — Ov3rLoRd")
    print(f"{'─'*60}")
    for term, data in g.items():
        kanji  = data.get("kanji", "—")
        romaji = data.get("romaji", "—")
        meaning = data.get("meaning", "")
        print(f"  {term:30s} → {kanji:20s} ({romaji})")
        if meaning:
            print(f"  {'':30s}   {meaning}")
    print(f"{'─'*60}")


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Ov3rLoRd Agent Traducteur V1.70")
    parser.add_argument("--translate", type=str, default=None, help="Texte à traduire")
    parser.add_argument("--target",    type=str, default="en",
                        choices=["en", "fr", "ja"])
    parser.add_argument("--booru",     type=str, default=None,
                        help="Convertir prompt FR en tags Booru EN")
    parser.add_argument("--detect",    type=str, default=None,
                        help="Détecter la langue d'un texte")
    parser.add_argument("--glossary",  action="store_true",
                        help="Afficher le glossaire japonais")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO,
                        format="%(asctime)s [%(levelname)s] %(message)s")

    if args.glossary:
        print_jp_glossary()

    elif args.booru:
        result = to_booru_en(args.booru)
        print(f"Input  : {args.booru}")
        print(f"Output : {result}")

    elif args.detect:
        lang = detect_language(args.detect)
        names = {"en": "Anglais", "fr": "Français", "ja": "Japonais"}
        print(f"Langue détectée : {names.get(lang, lang)}")

    elif args.translate:
        result = translate(args.translate, target=args.target)
        print(f"[{args.target.upper()}] {result}")

    else:
        print("=== Agent Traducteur V1.70 ===")
        print()
        print("Tests statiques (sans LLM) :")
        print(f"  FR→EN detect : '{detect_language('bonjour je suis une fille')}'")
        print(f"  EN detect    : '{detect_language('hello this is a test')}'")
        print(f"  Booru FR→EN  : '{to_booru_en('fille combat épique fond détruit')[:60]}'")
        print()
        print("Glossaire partiel :")
        for k, v in list(OV3RLORD_JP.items())[:4]:
            print(f"  {k} → {v['kanji']} ({v['romaji']})")
        print()
        print("Utiliser --glossary pour le glossaire complet")

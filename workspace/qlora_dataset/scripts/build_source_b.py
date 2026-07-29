"""
Source B -- export JSON des conversations Claude.ai (D:\\OVERLORD\\DOCS\\data claude 001).

Construit des paires (question/tache utilisateur) -> (reponse/raisonnement
assistant) au format Alpaca, pour entrainement comportemental QLoRA.

Perimetre volontairement limite a conversations.json : memories.json (memoire
cross-conversations Claude.ai) et users.json (identite/email du compte) sont
des metadonnees de compte, pas des transcriptions de conversation -- exclus
d'office, jamais lus au-dela de la verification de structure. reflections/
idem (nature differente, hors perimetre "conversations").

Filtrage du contenu personnel (obligatoire avant tout traitement) :
- une paire est ENTIEREMENT exclue (humain + assistant) des qu'un des deux
  messages matche un motif de la liste PERSONAL_PATTERNS (sante, contacts/
  relations, logistique Japan Expo non-technique, coordonnees) -- exclusion
  cote paire, pas de tentative de "nettoyer" le texte in place (plus sur).
- conversations vides (0 message) ignorees.

Extraction du texte par message : seuls les blocs `content` de type "text"
sont concatenes (le champ `text` aplati contient un placeholder generique
"This block is not supported..." des qu'un message contient des blocs
tool_use/tool_result -- plomberie du bac a sable Claude.ai, pas du
raisonnement/contenu a apprendre). Fallback sur le champ `text` si aucun
bloc "text" n'est present.

Pairage : messages tries par created_at, chaque message humain est associe
a la concatenation des messages assistant qui suivent jusqu'au prochain
message humain.
"""
import json
import re

SRC_PATH = r"D:\OVERLORD\DOCS\data claude 001\conversations.json"
OUT_PATH = r"D:\OVERLORD\workspace\qlora_dataset\dataset_source_b.jsonl"
QA_DIR = r"D:\OVERLORD\workspace\qlora_dataset\_qa"

import os
os.makedirs(QA_DIR, exist_ok=True)

MIN_CHARS = 5  # ignore messages essentiellement vides (placeholder only, etc.)

# Conversations exclues en bloc (pas au niveau paire) : "BlaBla" est
# explicitement nommee comme discussion informelle par l'utilisateur lui-meme
# (archive de reference V1.70, mais hors sujet technique) et contient au moins
# une fuite biographique reelle (ancien employeur, ville, lien Google Maps)
# noyee dans une discussion de worldbuilding anime -- aucun mot-cle de la
# liste PERSONAL_PATTERNS ne la declenche. Vu ce mode d'echec (contenu
# personnel sans marqueur lexical fiable), exclusion de la conversation
# entiere plutot que du seul message concerne.
EXCLUDED_CONVERSATION_NAMES = {
    "BlaBla - (Archive de référence) : V1.70 - Lock",
}

# Paires individuelles exclues par uuid du message humain qui les ouvre.
# "Prioriser les tâches FootSegNet" (843 messages, sinon tres majoritairement
# technique) contient un aparte biographique continu (financement personnel,
# pseudo Klebosol -> ancien poste en chimie industrielle, CDI manque en 2018,
# accident du travail) qui s'etend sur 5 paires consecutives sans qu'un seul
# mot-cle de PERSONAL_PATTERNS couvre chacune d'entre elles individuellement
# (ex. la paire 496/497 ne contient ni CAIC/Merck/Klebosol/chimie, juste "le
# CDI de 2018" et un chiffre de salaire). Exclusion explicite du bloc de
# messages plutot que de continuer a chasser des mots-cles au cas par cas.
EXCLUDED_MESSAGE_UUIDS = {
    "019f9266-86ab-7077-951a-51472d65e2bf",
    "019f9278-9ceb-7d69-8e83-ff2179b4cf79",
    "019f9280-336b-79bc-b6a5-f1c4a9227b42",
    "019f9291-a536-76de-8138-a1e8289e7f39",
    "019f9299-3c34-7f5b-9beb-0e71ae6ab83c",
    # 715 -- reference a l'age reel (41 ans) et souvenir de college.
    "019f0ca6-75d1-76b8-a165-12b87db2bbe2",
    # 1083/1235 -- statut chomage/recherche de revenu, situation personnelle.
    "019f3ea9-9bb7-75b1-b926-7f168505a538",
    "019f7126-3e8f-7766-8496-7461524379b4",
    # 1231/1232 -- litige bancaire/legal personnel (mise en demeure, remboursement).
    "019f710b-7027-77c1-a757-879d2e88143c",
    "019f710f-ee7b-710b-a9d5-1337e7fd651c",
    # 1082 -- ville de naissance/residence personnelle + droits chomage.
    "019f3ebc-4bb6-70e6-801d-676b45f3c33a",
}

PERSONAL_PATTERNS = [
    # sante
    re.compile(r"m[ée]decin", re.I),
    re.compile(r"\bdocteur\b", re.I),
    re.compile(r"h[oô]pital", re.I),
    re.compile(r"sympt[oô]me", re.I),
    re.compile(r"\bmaladie\b", re.I),
    re.compile(r"ordonnance", re.I),
    re.compile(r"pharmacie", re.I),
    re.compile(r"anxi[ée]t[ée]", re.I),
    re.compile(r"d[ée]pression", re.I),
    re.compile(r"\bpsy(chologue|chiatre)?\b", re.I),
    re.compile(r"th[ée]rapeute", re.I),
    re.compile(r"fatigue chronique", re.I),
    re.compile(r"probl[eè]me de sant[ée]", re.I),
    re.compile(r"\bdouleur\b", re.I),
    # contacts / relations (formes possessives seulement -- "frere"/"soeur"
    # nus ne sont pas bloques pour ne pas ecraser du contenu narratif
    # fictif, ex. personnages d'anime lies par la fratrie)
    re.compile(r"\bma copine\b|\bmon copain\b|\bma femme\b|\bmon mari\b", re.I),
    re.compile(r"\bmes parents\b|\bma m[eè]re\b|\bmon p[eè]re\b", re.I),
    re.compile(r"\b(mon|ma|ton|ta)\s+(demi-)?fr[eè]re\b|\b(mon|ma|ton|ta)\s+(demi-)?s[oœ]ur\b", re.I),
    # historique professionnel/personnel reel de l'utilisateur (chimie,
    # avant Ov3rLoRd) -- termes tres specifiques, hors sujet Ov3rLoRd, donc
    # risque de faux positif quasi nul sur ce corpus
    re.compile(r"compi[eè]gne", re.I),
    re.compile(r"\bCAIC\b"),
    re.compile(r"\bmerck\b", re.I),
    re.compile(r"trosly", re.I),
    re.compile(r"klebosol", re.I),
    re.compile(r"franco-japonaise", re.I),
    re.compile(r"\btefic\b", re.I),
    re.compile(r"shirakawa", re.I),
    re.compile(r"\bchimie\b", re.I),  # ancien metier reel de l'utilisateur, aparte biographique
    re.compile(r"allocation[s]?\s+ch[oô]mage", re.I),
    re.compile(r"mise en demeure", re.I),
    re.compile(r"\banniversaire\b", re.I),
    re.compile(r"num[ée]ro de t[ée]l[ée]phone", re.I),
    re.compile(r"\b0[1-9](?:[ .-]?\d{2}){4}\b"),  # numero FR
    re.compile(r"[\w.+-]+@(?!example\.)[\w-]+\.\w+"),  # email (hors placeholders)
    re.compile(r"j[ée]r[ée]my\s*gourlain", re.I),
    re.compile(r"\bj[ée]r[ée]my\b", re.I),  # prenom reel utilise en signature/adresse directe
    re.compile(r"\bgourlain\b", re.I),
    re.compile(r"\bthomas\b", re.I),  # frere de l'utilisateur, mentionne nommement
    re.compile(r"g915tlk", re.I),
    re.compile(r"compte bancaire", re.I),
    re.compile(r"transf[ée]rer.{0,20}fonds", re.I),
    # logistique Japan Expo non-technique (vs. usage "deadline" projet)
    re.compile(r"billet.{0,20}japan expo|japan expo.{0,20}billet", re.I),
    re.compile(r"\bh[ôo]tel\b", re.I),
    re.compile(r"\bcovoiturage\b", re.I),
    re.compile(r"\bvillepinte\b", re.I),
    re.compile(r"\bRER\b"),
    re.compile(r"\bparking\b", re.I),
    re.compile(r"horaires? d'ouverture", re.I),
]


def get_text(m: dict) -> str:
    blocks = m.get("content") or []
    parts = [b.get("text", "") for b in blocks if b.get("type") == "text" and b.get("text")]
    if parts:
        return "\n".join(parts).strip()
    return (m.get("text") or "").strip()


def is_personal(text: str) -> bool:
    return any(p.search(text) for p in PERSONAL_PATTERNS)


def main():
    with open(SRC_PATH, encoding="utf-8") as f:
        conversations = json.load(f)

    kept = 0
    skipped_personal = 0
    skipped_short = 0
    skipped_empty_conv = 0
    skipped_excluded_conv = 0

    excluded_preview = []

    with open(OUT_PATH, "w", encoding="utf-8") as out:
        for conv in conversations:
            msgs = conv.get("chat_messages") or []
            if not msgs:
                skipped_empty_conv += 1
                continue
            if conv.get("name") in EXCLUDED_CONVERSATION_NAMES:
                skipped_excluded_conv += len(msgs)
                continue

            msgs = sorted(msgs, key=lambda m: m["created_at"])

            i = 0
            n = len(msgs)
            while i < n:
                m = msgs[i]
                if m["sender"] != "human":
                    i += 1
                    continue
                if m["uuid"] in EXCLUDED_MESSAGE_UUIDS:
                    skipped_personal += 1
                    j = i + 1
                    while j < n and msgs[j]["sender"] == "assistant":
                        j += 1
                    i = j if j > i else i + 1
                    continue
                human_text = get_text(m)
                j = i + 1
                assistant_parts = []
                while j < n and msgs[j]["sender"] == "assistant":
                    assistant_parts.append(get_text(msgs[j]))
                    j += 1
                assistant_text = "\n\n".join(p for p in assistant_parts if p).strip()

                if len(human_text) < MIN_CHARS or len(assistant_text) < MIN_CHARS:
                    skipped_short += 1
                    i = j if j > i else i + 1
                    continue

                if is_personal(human_text) or is_personal(assistant_text):
                    skipped_personal += 1
                    excluded_preview.append(
                        f"[conv={conv.get('name','')!r} uuid={conv['uuid'][:8]}] "
                        f"H: {human_text[:80]!r}"
                    )
                    i = j if j > i else i + 1
                    continue

                record = {
                    "instruction": human_text,
                    "input": "",
                    "output": assistant_text,
                    "meta": {
                        "source": "claude_ai_export",
                        "conversation": conv.get("name", ""),
                        "conversation_uuid": conv["uuid"],
                        "message_uuid": m["uuid"],
                    },
                }
                out.write(json.dumps(record, ensure_ascii=False) + "\n")
                kept += 1
                i = j if j > i else i + 1

    with open(os.path.join(QA_DIR, "excluded_personal_preview.txt"), "w", encoding="utf-8") as f:
        f.write("\n".join(excluded_preview))

    print(f"conversations_total={len(conversations)}")
    print(f"conversations_vides={skipped_empty_conv}")
    print(f"messages_conversation_exclue_en_bloc={skipped_excluded_conv}")
    print(f"paires_gardees={kept}")
    print(f"paires_exclues_personnel={skipped_personal}")
    print(f"paires_exclues_trop_courtes={skipped_short}")


if __name__ == "__main__":
    main()

"""
Sous-ensemble Python de CommitPackFT -- prepare (mais n'entraine rien) un
premier lot d'exemples Alpaca (instruction=sujet de commit, input=corps du
message, output=diff unifie) a partir du dataset public CommitPackFT
(bigcode/commitpackft sur HuggingFace), filtre langage=Python.

CONTEXTE DE SESSION -- ecart entre la consigne et l'etat reel observe :
la consigne de session suppose que les 5 bases externes (dont CommitPack)
sont en cours de telechargement vers le HDD externe (G:\\, "Seagate 8To",
~40 Mo/s en pratique -- goulot d'etranglement documente, jamais lire
directement dessus pour un entrainement). A l'execution de ce script,
CommitPackFT etait deja telechargee et *complete* directement sur le SSD
dedie E:\\ ("990Pro 2To") -- seul `bigcode/the-stack` (dataset bien plus
volumineux) etait effectivement en cours de telechargement vers le HDD au
moment de la verification. CANDIDATE_SOURCE_DIRS ci-dessous couvre donc les
deux cas (HDD suppose ET SSD reellement observe) pour rester correct si la
disposition change (ex. reexecution future une fois le HDD utilise pour de
premiers datasets) ; SSD_STAGING_ROOT reste la destination de reference,
copie sautee si la source est deja sur ce meme volume.

Taille cible du premier sous-ensemble -- 2000 exemples, apres filtrage.
Raisonnement : CommitPackFT/Python complet est 56025 exemples (135.8 Mo de
JSONL brut, mesure a l'execution) -- bien plus que les trois sources
maison combinees (Source A+B+C = 1778 exemples, cf. STATS_ET_RECOMMANDATION.md
Session 6). Un premier sous-ensemble du meme ordre de grandeur que Source B
(1435, la plus grosse source existante et deja validee comme "signal
suffisant pour un premier essai") permet de tester l'integration d'un
dataset de code public generique sans que son volume ecrase par un facteur
30x le signal comportemental specifique au projet si les sources sont
un jour melangees -- le sur-echantillonnage dans train_qlora.py reste la
methode pour ponderer les sources entre elles, mais partir d'un sous-ensemble
deja raisonnable evite d'avoir a sous-echantillonner un enorme fichier a
l'entrainement. Revoir a la hausse une fois un premier essai qualitatif fait
sur ce lot (meme demarche que Source A : le fichier est regenere via ce
script, pas ecrit a la main).

Filtres appliques :
- lang == "Python" (deja vrai vu le repertoire source, verifie par securite).
- sujets triviaux exclus (meme esprit que build_source_a.py -- "typo", "wip",
  sujet trop court pour porter une intention).
- old_contents/new_contents identiques (aucun changement reel, artefact de
  filtrage upstream) exclus.
- new_contents doit parser avec ast.parse() -- obligatoire selon les regles
  de session ("ast.parse() validé"), et filtre de qualite reel : CommitPackFT
  contient des extraits Python tronques/invalides (connu du dataset public).
- diff unifie plafonne a 20000 caracteres (coherent avec DIFF_SIZE_CAP de
  Source A) -- les diffs au-dela sont des reecritures massives de fichier,
  pas des changements isoles representatifs.
- SECRET_PATTERNS (memes regex que build_source_c.py) applique par defense
  en profondeur, meme si le code vient de depots publics.
- deduplication par hash de commit.

Selection : apres filtrage, echantillon aleatoire (seed fixe = 3407, memes
seed que train_qlora.py pour tracabilite) jusqu'a TARGET_SUBSET_SIZE, ou tout
le filtre gardee si son volume est deja sous la cible.

RAPPEL REGLES DE SESSION : ce script ne lance aucun entrainement. Il ne fait
que lire un dataset deja telecharge et ecrire un sous-ensemble JSONL filtre.
"""
import ast
import difflib
import glob
import hashlib
import json
import os
import random
import re
import shutil
import time

TARGET_SUBSET_SIZE = 2000
DIFF_SIZE_CAP = 20000
SEED = 3407

SSD_STAGING_ROOT = r"E:\data\commitpackft_python_subset"
OUT_FILENAME = "dataset_source_commitpack_python.jsonl"
REPO_COPY_PATH = r"D:\OVERLORD\workspace\qlora_dataset\dataset_source_commitpack_python.jsonl"

# Ordre de priorite : premier chemin trouve ET complet est utilise. Couvre le
# scenario suppose par la consigne (HDD, glob large car l'arborescence exacte
# du script de telechargement de Jeremy n'est pas connue a l'avance) et le
# scenario reellement observe (SSD, chemin exact verifie a la main).
CANDIDATE_SOURCE_GLOBS = [
    r"G:\**\commitpackft\data\python\data.jsonl",   # HDD, suppose par la consigne
    r"H:\**\commitpackft\data\python\data.jsonl",    # autre HDD/disque externe possible
    r"E:\data\commitpackft\data\python\data.jsonl",  # SSD -- emplacement reellement observe 2026-07-30
]

TRIVIAL_SUBJECT_PATTERNS = [
    re.compile(r"^\s*(fix|update|wip|typo|misc|cleanup|minor)\s*$", re.I),
    re.compile(r"^\s*\.\s*$"),
]

SECRET_PATTERNS = [
    re.compile(r"sk-[A-Za-z0-9]{20,}"),
    re.compile(r"AKIA[0-9A-Z]{16}"),
    re.compile(r"ghp_[A-Za-z0-9]{30,}"),
    re.compile(r"xox[baprs]-[A-Za-z0-9-]{10,}"),
    re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----"),
]


def find_source_file():
    """Verification unique, non bloquante (pas de boucle/sleep ici -- voir
    docstring module). Reexecuter ce script plus tard, quand le
    telechargement externe aura progresse, est le mecanisme de verification
    "periodique" demande par la consigne, pas une attente active interne."""
    for pattern in CANDIDATE_SOURCE_GLOBS:
        matches = glob.glob(pattern, recursive=True)
        for m in matches:
            if os.path.isfile(m) and os.path.getsize(m) > 0:
                return m
    return None


def is_trivial(subject: str) -> bool:
    return any(p.match(subject.strip()) for p in TRIVIAL_SUBJECT_PATTERNS)


def has_secret(text: str) -> bool:
    return any(p.search(text) for p in SECRET_PATTERNS)


def is_valid_python(source: str) -> bool:
    try:
        ast.parse(source)
        return True
    except (SyntaxError, ValueError):
        return False


def split_body(subject: str, message: str) -> str:
    if message.startswith(subject):
        return message[len(subject):].lstrip("\n").strip()
    return message.strip()


def make_diff(old_contents: str, new_contents: str, path: str) -> str:
    diff_lines = difflib.unified_diff(
        old_contents.splitlines(keepends=True),
        new_contents.splitlines(keepends=True),
        fromfile=f"a/{path}", tofile=f"b/{path}",
    )
    return "".join(diff_lines)


def build_subset(source_path: str):
    kept = []
    seen_commits = set()
    counters = {
        "read": 0, "kept": 0,
        "skipped_lang": 0, "skipped_trivial": 0, "skipped_nochange": 0,
        "skipped_invalid_python": 0, "skipped_size": 0, "skipped_secret": 0,
        "skipped_duplicate": 0,
    }

    with open(source_path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            counters["read"] += 1
            try:
                r = json.loads(line)
            except (json.JSONDecodeError, ValueError):
                continue

            if r.get("lang") != "Python":
                counters["skipped_lang"] += 1
                continue

            commit = r.get("commit", "")
            key = hashlib.sha1(commit.encode("utf-8")).hexdigest()
            if key in seen_commits:
                counters["skipped_duplicate"] += 1
                continue

            subject = (r.get("subject") or "").strip()
            if not subject or is_trivial(subject):
                counters["skipped_trivial"] += 1
                continue

            old_c, new_c = r.get("old_contents", ""), r.get("new_contents", "")
            if old_c == new_c:
                counters["skipped_nochange"] += 1
                continue

            if not is_valid_python(new_c):
                counters["skipped_invalid_python"] += 1
                continue

            diff = make_diff(old_c, new_c, r.get("new_file") or r.get("old_file") or "file.py")
            if len(diff) > DIFF_SIZE_CAP:
                counters["skipped_size"] += 1
                continue

            body = split_body(subject, r.get("message") or "")
            combined = subject + "\n" + body + "\n" + diff
            if has_secret(combined):
                counters["skipped_secret"] += 1
                continue

            seen_commits.add(key)
            kept.append({
                "instruction": subject,
                "input": body,
                "output": diff,
                "meta": {
                    "source": "commitpackft_python",
                    "commit": commit,
                    "file": r.get("new_file") or r.get("old_file") or "",
                    "license": r.get("license", ""),
                },
            })
            counters["kept"] += 1

    return kept, counters


def main():
    source_path = find_source_file()
    if source_path is None:
        print("commitpack_python_not_found=true")
        print("CommitPackFT/Python introuvable aux emplacements candidats "
              "(voir CANDIDATE_SOURCE_GLOBS). Rien a faire -- reexecuter ce "
              "script une fois le telechargement externe termine.")
        return

    print(f"source_found={source_path}")
    print(f"source_size_mb={os.path.getsize(source_path) / 1024 / 1024:.1f}")

    t0 = time.time()
    kept, counters = build_subset(source_path)
    for k, v in counters.items():
        print(f"{k}={v}")
    print(f"filtrage_termine_en_s={time.time() - t0:.1f}")

    rng = random.Random(SEED)
    if len(kept) > TARGET_SUBSET_SIZE:
        subset = rng.sample(kept, TARGET_SUBSET_SIZE)
    else:
        subset = kept
    print(f"subset_final={len(subset)} (cible={TARGET_SUBSET_SIZE}, "
          f"{'echantillonne' if len(kept) > TARGET_SUBSET_SIZE else 'garde tel quel, filtre < cible'})")

    source_drive = os.path.splitdrive(source_path)[0].upper()
    ssd_drive = os.path.splitdrive(SSD_STAGING_ROOT)[0].upper()

    if source_drive == ssd_drive:
        # Deja sur le SSD dedie (cas reellement observe le 2026-07-30) --
        # aucune copie HDD->SSD necessaire, on ecrit le sous-ensemble
        # directement dans le repertoire de stage sur ce meme volume.
        os.makedirs(SSD_STAGING_ROOT, exist_ok=True)
        out_path = os.path.join(SSD_STAGING_ROOT, OUT_FILENAME)
        print(f"source_deja_sur_ssd_dedie={ssd_drive} -- pas de copie HDD->SSD necessaire")
    else:
        # Cas suppose par la consigne : source sur HDD externe (~40 Mo/s),
        # jamais lire depuis la dedans pour un entrainement -- le
        # sous-ensemble filtre (bien plus petit que la source brute) est
        # ecrit sur le SSD dedie.
        os.makedirs(SSD_STAGING_ROOT, exist_ok=True)
        out_path = os.path.join(SSD_STAGING_ROOT, OUT_FILENAME)
        print(f"copie_hdd_vers_ssd: {source_drive} -> {ssd_drive}")

    with open(out_path, "w", encoding="utf-8") as out:
        for r in subset:
            out.write(json.dumps(r, ensure_ascii=False) + "\n")
    print(f"ecrit={out_path}")

    # Copie de reference dans le depot (petite -- sous-ensemble filtre, pas
    # le dataset brut) pour rester coherente avec Source A/B/C, deja
    # versionnees dans workspace/qlora_dataset/.
    shutil.copy2(out_path, REPO_COPY_PATH)
    print(f"copie_depot={REPO_COPY_PATH}")


if __name__ == "__main__":
    main()

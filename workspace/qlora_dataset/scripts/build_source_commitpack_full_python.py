"""
Sous-ensemble Python du "vrai" CommitPack (bigcode/commitpack, PAS
CommitPackFT) -- prepare (mais n'entraine rien) un lot d'exemples Alpaca
(instruction=sujet de commit, input=corps du message, output=diff unifie)
depuis le corpus brut confirme sur E:\\data\\commitpack\\python\\ (458 shards
JSONL, ~223 Go). `python-traceback\\` (1 shard, 15 Ko) volontairement exclu
du perimetre -- son champ `lang` vaut "Python traceback" (dumps de
traceback), pas "Python" ; verifie par smoke test avant le run complet.

ECART CONSIGNE / REALITE (verifie avant de coder, comme demande) : la
consigne supposait un format Parquet et un schema instruction/diff deja
prepare comme CommitPackFT. Verification faite -- c'est en realite du JSONL
brut (memes noms de colonnes que CommitPackFT : commit/subject/message/
old_contents/new_contents/old_file/new_file/repos/license/lang/returncode/
stderr), un shard par ~524 Mo. Champ reel `lang`, pas `language`.

DISTINCT DE `build_source_commitpack_python.py` (CommitPackFT, 56025 lignes
completes, deja filtre a 2000 exemples et deja entraine dans l'adaptateur
`training_stage1/runs/stage1_commitpack_full/`). Nom de fichier volontairement
different (`_full_`) pour ne jamais ecraser cette sortie existante deja
utilisee par un run reel -- voir CLAUDE.md "un nouveau run ne doit jamais
ecrire dans le dossier de sortie d'un run existant sans confirmation
explicite", meme logique appliquee a un fichier de donnees source.

PAS DE CAP ARTIFICIEL : contrairement a build_source_commitpack_python.py
(cible fixe 2000) et build_source_thestack_python.py (cible fixe 40000),
ce script garde TOUT ce qui passe les filtres de qualite -- le volume final
est decide par le filtrage, pas par une constante choisie a l'avance. Le
sous-echantillonnage n'intervient qu'en aval, uniquement si le total
depasse TARGET_MAX_IF_EXCEEDED (150000), et alors par diversite de type de
commit (feat/fix/refactor/perf/other, classification heuristique sur le
sujet -- CommitPack n'a pas de champ de type structure) plutot que par
troncature (garder les X premiers lus serait biaise par l'ordre des shards).

ARCHITECTURE (memoire bornee sur un corpus de 223 Go) :
1. Un processus par shard (multiprocessing, WORKERS=8 sur 12 coeurs
   logiques -- 4 laisses libres pour ne pas affamer le Stage1 TheStack en
   cours sur la RTX 5080, qui delest une partie de son calcul sur CPU,
   cf. HANDOFF_2026-08-02). Chaque worker applique tous les filtres
   (dont ast.parse + generation de diff, couteux) et ECRIT directement son
   resultat filtre dans un fichier JSONL temporaire -- jamais garde en RAM
   dans le processus principal. Seuls des compteurs (entiers) remontent.
2. Compteurs globaux agreges (vrais totaux, aucune approximation) ->
   decision garder-tout ou sous-echantillonner.
3. Si sous-echantillonnage necessaire : deuxieme passe, sequentielle et bon
   marche (les fichiers temporaires sont deja filtres, donc petits), avec
   un tirage par reservoir (Algorithme R, non biaise) par type de commit,
   cible = repartition proportionnelle aux vrais totaux par type jusqu'a
   150000 au total.
4. Fichiers temporaires par worker supprimes apres fusion finale.

Filtres appliques (coherents avec build_source_commitpack_python.py) :
- lang == "Python" (deja vrai vu le repertoire source, verifie par securite).
- dedup par hash de commit -- intra-shard seulement (les shards sont des
  partitions disjointes du meme export, pas de recouvrement attendu entre
  shards ; meme limite documentee dans build_source_thestack_python.py :
  "filet de securite simple, pas un dedup exhaustif").
- sujets triviaux exclus (typo/wip/...).
- old_contents == new_contents exclus (aucun changement reel).
- new_contents doit parser avec ast.parse() -- obligatoire selon les regles
  de session, et filtre de qualite reel (CommitPack brut contient des
  extraits Python 2/tronques invalides, cf. constat deja fait sur
  CommitPackFT).
- diff unifie plafonne a 20000 caracteres (coherent avec DIFF_SIZE_CAP des
  autres sources).
- SECRET_PATTERNS (memes regex que les autres build_source_*.py).

RAPPEL REGLES DE SESSION : ce script ne lance aucun entrainement. Il ne fait
que lire un dataset deja telecharge et ecrire un sous-ensemble JSONL filtre.
Aucun appel GPU -- ne touche ni la RTX 5080 (Stage1 en cours) ni la RTX 5060
Ti (verifie via nvidia-smi avant lancement, hors de ce script, comme demande
par la consigne de session).
"""
import ast
import difflib
import glob
import hashlib
import json
import multiprocessing
import os
import random
import re
import shutil
import time

TARGET_MAX_IF_EXCEEDED = 150_000
DIFF_SIZE_CAP = 20_000
MAX_CHARS_FOR_PARSE = 300_000  # evite de perdre du temps ast.parse sur des fichiers generes enormes
SEED = 3407
WORKERS = 8  # 12 coeurs logiques -- 4 laisses libres pour le Stage1 TheStack en cours (RTX 5080 + offload CPU)

SSD_STAGING_ROOT = r"E:\data\commitpack_full_python_subset"
TEMP_DIR = os.path.join(SSD_STAGING_ROOT, "_shards_filtered")
OUT_FILENAME = "dataset_source_commitpack_full_python.jsonl"
REPO_COPY_PATH = r"D:\OVERLORD\workspace\qlora_dataset\dataset_source_commitpack_full_python.jsonl"
FILTER_LOG_PATH = os.path.join(SSD_STAGING_ROOT, "filter_log.txt")

# Ordre de priorite : premier repertoire racine trouve est utilise (memes
# emplacements candidats que les autres build_source_*.py -- HDD suppose par
# la consigne, SSD reellement observe le 2026-08-03).
CANDIDATE_ROOT_GLOBS = [
    r"G:\**\commitpack",
    r"H:\**\commitpack",
    r"E:\data\commitpack",
]
# "python-traceback" delibrement exclu : verifie a l'execution (smoke test)
# -- son champ `lang` vaut "Python traceback" (dumps de traceback), pas
# "Python", donc 100% filtre par lang=="Python" de toute facon ; l'inclure
# ne ferait que gaspiller un worker sur un shard de 15 Ko sans rien garder.
SHARD_SUBDIRS = ["python"]

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

CONVENTIONAL_TYPE_RE = re.compile(r"^\s*(feat|fix|refactor|perf)(\([^)]*\))?!?\s*:\s", re.I)
FIX_KEYWORDS = re.compile(r"\b(fix(e[sd])?|fixing|bug ?fix|resolve[sd]?|patch(e[sd])?)\b", re.I)
FEAT_KEYWORDS = re.compile(r"\b(add(s|ed|ing)?|implement(s|ed|ing)?|introduce[sd]?|new feature)\b", re.I)
REFACTOR_KEYWORDS = re.compile(r"\b(refactor(s|ed|ing)?|clean ?up|restructure[sd]?|simplif(y|ied|ies))\b", re.I)
PERF_KEYWORDS = re.compile(r"\b(perf(ormance)?|optimi[sz](e[sd]?|ing)|speed ?up|faster)\b", re.I)
COMMIT_TYPES = ("feat", "fix", "refactor", "perf", "other")


def log(msg: str):
    print(msg, flush=True)
    with open(FILTER_LOG_PATH, "a", encoding="utf-8") as f:
        f.write(msg + "\n")


def find_shard_root():
    for pattern in CANDIDATE_ROOT_GLOBS:
        for m in glob.glob(pattern, recursive=True):
            if os.path.isdir(m) and any(
                os.path.isdir(os.path.join(m, d)) for d in SHARD_SUBDIRS
            ):
                return m
    return None


def list_shards(root: str):
    shards = []
    for d in SHARD_SUBDIRS:
        shards.extend(sorted(glob.glob(os.path.join(root, d, "*.jsonl"))))
    return shards


def is_trivial(subject: str) -> bool:
    return any(p.match(subject.strip()) for p in TRIVIAL_SUBJECT_PATTERNS)


def has_secret(text: str) -> bool:
    return any(p.search(text) for p in SECRET_PATTERNS)


def is_valid_python(source: str) -> bool:
    if len(source) > MAX_CHARS_FOR_PARSE:
        return False
    try:
        ast.parse(source)
        return True
    except (SyntaxError, ValueError, RecursionError):
        return False


def classify_commit_type(subject: str) -> str:
    m = CONVENTIONAL_TYPE_RE.match(subject)
    if m:
        return m.group(1).lower()
    if FIX_KEYWORDS.search(subject):
        return "fix"
    if FEAT_KEYWORDS.search(subject):
        return "feat"
    if REFACTOR_KEYWORDS.search(subject):
        return "refactor"
    if PERF_KEYWORDS.search(subject):
        return "perf"
    return "other"


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


def process_shard(shard_path: str):
    """Execute dans un processus worker. Ecrit directement son resultat
    filtre sur disque (jamais retourne en memoire au processus principal --
    seuls des compteurs le sont) pour rester borne en RAM quel que soit le
    volume total du corpus."""
    out_path = os.path.join(TEMP_DIR, os.path.basename(shard_path) + ".filtered.jsonl")
    seen_commits = set()
    counters = {
        "read": 0, "kept": 0,
        "skipped_lang": 0, "skipped_trivial": 0, "skipped_nochange": 0,
        "skipped_invalid_python": 0, "skipped_size": 0, "skipped_secret": 0,
        "skipped_duplicate": 0, "skipped_badjson": 0,
    }
    for t in COMMIT_TYPES:
        counters[f"kept_{t}"] = 0

    with open(shard_path, encoding="utf-8") as f, open(out_path, "w", encoding="utf-8") as out:
        for line in f:
            line = line.strip()
            if not line:
                continue
            counters["read"] += 1
            try:
                r = json.loads(line)
            except (json.JSONDecodeError, ValueError):
                counters["skipped_badjson"] += 1
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
            commit_type = classify_commit_type(subject)
            out.write(json.dumps({
                "instruction": subject,
                "input": body,
                "output": diff,
                "meta": {
                    "source": "commitpack_full_python",
                    "commit": commit,
                    "file": r.get("new_file") or r.get("old_file") or "",
                    "license": r.get("license", ""),
                    "repos": r.get("repos", ""),
                    "commit_type": commit_type,
                },
            }, ensure_ascii=False) + "\n")
            counters["kept"] += 1
            counters[f"kept_{commit_type}"] += 1

    return shard_path, out_path, counters


def merge_all(temp_paths, final_path):
    with open(final_path, "w", encoding="utf-8") as out:
        for p in temp_paths:
            with open(p, encoding="utf-8") as f:
                shutil.copyfileobj(f, out)


def reservoir_sample_by_type(temp_paths, target_per_type: dict, seed: int):
    """Algorithme R par type de commit, une seule passe sequentielle sur les
    fichiers deja filtres (donc petits -- le travail couteux, ast.parse et
    diff, est deja fait). Tirage non biaise, borne en memoire a
    sum(target_per_type)."""
    rng = random.Random(seed)
    reservoirs = {t: [] for t in target_per_type}
    seen = {t: 0 for t in target_per_type}
    for p in temp_paths:
        with open(p, encoding="utf-8") as f:
            for line in f:
                rec = json.loads(line)
                t = rec["meta"]["commit_type"]
                cap = target_per_type.get(t, 0)
                if cap == 0:
                    continue
                seen[t] += 1
                res = reservoirs[t]
                if len(res) < cap:
                    res.append(rec)
                else:
                    j = rng.randint(0, seen[t] - 1)
                    if j < cap:
                        res[j] = rec
    return reservoirs


def main():
    os.makedirs(TEMP_DIR, exist_ok=True)
    open(FILTER_LOG_PATH, "w", encoding="utf-8").close()  # nouveau log a chaque run

    root = find_shard_root()
    if root is None:
        log("commitpack_full_python_not_found=true")
        log("CommitPack (racine 'commitpack') introuvable aux emplacements "
            "candidats (voir CANDIDATE_ROOT_GLOBS). Rien a faire.")
        return

    shards = list_shards(root)
    if not shards:
        log(f"root_found={root} mais aucun shard *.jsonl dans {SHARD_SUBDIRS}")
        return

    total_source_bytes = sum(os.path.getsize(s) for s in shards)
    log(f"root_found={root}")
    log(f"shards_trouves={len(shards)}")
    log(f"source_size_gb={total_source_bytes / 1024**3:.2f}")
    log(f"workers={WORKERS}")

    t0 = time.time()
    counters = {
        "read": 0, "kept": 0,
        "skipped_lang": 0, "skipped_trivial": 0, "skipped_nochange": 0,
        "skipped_invalid_python": 0, "skipped_size": 0, "skipped_secret": 0,
        "skipped_duplicate": 0, "skipped_badjson": 0,
    }
    for t in COMMIT_TYPES:
        counters[f"kept_{t}"] = 0
    temp_paths = []

    with multiprocessing.Pool(processes=WORKERS) as pool:
        done = 0
        for shard_path, out_path, shard_counters in pool.imap_unordered(process_shard, shards):
            done += 1
            temp_paths.append(out_path)
            for k, v in shard_counters.items():
                counters[k] += v
            elapsed = time.time() - t0
            rate = done / elapsed if elapsed > 0 else 0
            eta_s = (len(shards) - done) / rate if rate > 0 else float("nan")
            log(f"shard {done}/{len(shards)} ok ({os.path.basename(shard_path)}) "
                f"kept_cumul={counters['kept']} elapsed_s={elapsed:.0f} eta_s={eta_s:.0f}")

    log(f"filtrage_termine_en_s={time.time() - t0:.1f}")
    for k, v in counters.items():
        log(f"{k}={v}")

    total_kept = counters["kept"]
    log(f"total_kept={total_kept}")
    for t in COMMIT_TYPES:
        pct = 100 * counters[f"kept_{t}"] / total_kept if total_kept else 0
        log(f"repartition_{t}={counters[f'kept_{t}']} ({pct:.1f}%)")

    os.makedirs(SSD_STAGING_ROOT, exist_ok=True)
    final_path = os.path.join(SSD_STAGING_ROOT, OUT_FILENAME)

    if total_kept <= TARGET_MAX_IF_EXCEEDED:
        log(f"sous_echantillonnage=non (total <= {TARGET_MAX_IF_EXCEEDED}, tout est garde)")
        merge_all(temp_paths, final_path)
    else:
        log(f"sous_echantillonnage=oui (total > {TARGET_MAX_IF_EXCEEDED}, "
            f"tirage par reservoir proportionnel a la diversite de type de commit)")
        target_per_type = {}
        allocated = 0
        types_sorted = sorted(COMMIT_TYPES, key=lambda t: counters[f"kept_{t}"])
        for i, t in enumerate(types_sorted):
            if i == len(types_sorted) - 1:
                # le plus gros type absorbe le reste pour totaliser exactement
                # la cible -- borne par son propre total reel (ne peut pas
                # fournir plus qu'il n'en existe si le reste, improbable mais
                # possible apres arrondis/plafonds des types plus petits,
                # depasse son propre compte).
                target_per_type[t] = min(TARGET_MAX_IF_EXCEEDED - allocated, counters[f"kept_{t}"])
            else:
                share = round(TARGET_MAX_IF_EXCEEDED * counters[f"kept_{t}"] / total_kept)
                share = min(share, counters[f"kept_{t}"])
                target_per_type[t] = share
                allocated += share
        for t in COMMIT_TYPES:
            log(f"cible_{t}={target_per_type.get(t, 0)}")

        reservoirs = reservoir_sample_by_type(temp_paths, target_per_type, SEED)
        with open(final_path, "w", encoding="utf-8") as out:
            for t in COMMIT_TYPES:
                for rec in reservoirs.get(t, []):
                    out.write(json.dumps(rec, ensure_ascii=False) + "\n")

    final_size = os.path.getsize(final_path)
    with open(final_path, encoding="utf-8") as f:
        final_lines = sum(1 for _ in f)
    log(f"ecrit={final_path}")
    log(f"final_lignes={final_lines}")
    log(f"final_taille_mo={final_size / 1024**2:.1f}")

    shutil.copy2(final_path, REPO_COPY_PATH)
    log(f"copie_depot={REPO_COPY_PATH}")

    for p in temp_paths:
        try:
            os.remove(p)
        except OSError:
            pass
    log(f"temp_fichiers_nettoyes={len(temp_paths)}")
    log("termine=true")


if __name__ == "__main__":
    main()

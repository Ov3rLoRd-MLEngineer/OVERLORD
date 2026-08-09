"""
H-010 -- Categorie C : "tache auto-suffisante -> repondre directement".

Objectif : corriger la regression de sur-refus identifiee dans le verdict
H-008 (`workspace/qlora_dataset/training/VERDICT_H008_STAGE3.md`, Prompt 2) --
le modele Stage 3 a generalise a tort le pattern de refus (categories A et B,
qui portent toutes les deux sur des questions necessitant un etat non
verifie) a des taches generiques auto-suffisantes qui ne referencent ni
fichier ni etat projet. Cette categorie C ne contient QUE des exemples
"repondre directement, avec confiance, sans demander de fichier" -- c'est le
contrepoids manquant.

Toutes les instructions ci-dessous sont volontairement generiques
(algorithme, script utilitaire autonome, concept, code fourni inline) --
aucune ne mentionne un fichier du depot ou un etat de session, donc aucune
ne justifie un refus calibre.

Ce fichier ne modifie ni source_rtuning.jsonl (categorie A) ni
source_rtuning_rag.jsonl (categorie B) -- nouveau fichier independant.
Ne lance aucun entrainement, aucun GPU.
"""
import json

OUT_PATH = r"D:\OVERLORD\workspace\qlora_dataset\source_selfsufficient.jsonl"


EXAMPLES = [
    # --- 1. Script utilitaire autonome (mirroir direct du cas de regression) ---
    {
        "instruction": (
            "Ecris un script py -3.12 qui valide un fichier JSONL de dataset "
            "d'entrainement : verifie que chaque ligne contient bien les cles "
            "instruction/input/output et que output n'est pas vide."
        ),
        "output": (
            "```python\n"
            "#!/usr/bin/env python3\n"
            "import argparse\n"
            "import json\n"
            "import sys\n\n\n"
            "def validate_jsonl(path: str) -> int:\n"
            "    errors = 0\n"
            "    with open(path, encoding=\"utf-8\") as f:\n"
            "        for i, line in enumerate(f, start=1):\n"
            "            line = line.strip()\n"
            "            if not line:\n"
            "                continue\n"
            "            try:\n"
            "                row = json.loads(line)\n"
            "            except json.JSONDecodeError as e:\n"
            "                print(f\"ligne {i}: JSON invalide -- {e}\", file=sys.stderr)\n"
            "                errors += 1\n"
            "                continue\n"
            "            missing = [k for k in (\"instruction\", \"input\", \"output\") if k not in row]\n"
            "            if missing:\n"
            "                print(f\"ligne {i}: cles manquantes {missing}\", file=sys.stderr)\n"
            "                errors += 1\n"
            "                continue\n"
            "            if not str(row[\"output\"]).strip():\n"
            "                print(f\"ligne {i}: 'output' vide\", file=sys.stderr)\n"
            "                errors += 1\n"
            "    return errors\n\n\n"
            "if __name__ == \"__main__\":\n"
            "    parser = argparse.ArgumentParser()\n"
            "    parser.add_argument(\"dataset\")\n"
            "    args = parser.parse_args()\n"
            "    n_errors = validate_jsonl(args.dataset)\n"
            "    print(f\"{n_errors} ligne(s) invalide(s)\")\n"
            "    sys.exit(1 if n_errors else 0)\n"
            "```\n"
            "Cette tache est auto-suffisante -- le format attendu (instruction/"
            "input/output) est entierement specifie dans la demande, pas besoin "
            "de voir un fichier existant pour l'ecrire."
        ),
    },
    {
        "instruction": (
            "Ecris un script py -3.12 qui prend un dossier en argument et "
            "renomme tous les fichiers .PNG (majuscules) en .png (minuscules)."
        ),
        "output": (
            "```python\n"
            "import argparse\n"
            "from pathlib import Path\n\n\n"
            "def normalize_extensions(folder: str) -> int:\n"
            "    count = 0\n"
            "    for p in Path(folder).glob(\"*.PNG\"):\n"
            "        p.rename(p.with_suffix(\".png\"))\n"
            "        count += 1\n"
            "    return count\n\n\n"
            "if __name__ == \"__main__\":\n"
            "    parser = argparse.ArgumentParser()\n"
            "    parser.add_argument(\"folder\")\n"
            "    args = parser.parse_args()\n"
            "    n = normalize_extensions(args.folder)\n"
            "    print(f\"{n} fichier(s) renomme(s)\")\n"
            "```"
        ),
    },
    {
        "instruction": "Ecris une fonction Python qui deduplique une liste tout en preservant l'ordre d'apparition.",
        "output": (
            "```python\n"
            "def dedupe_preserve_order(items: list) -> list:\n"
            "    seen = set()\n"
            "    result = []\n"
            "    for item in items:\n"
            "        if item not in seen:\n"
            "            seen.add(item)\n"
            "            result.append(item)\n"
            "    return result\n"
            "```\n"
            "Complexite O(n) grace au `set` pour le test d'appartenance, contrairement "
            "a `list(dict.fromkeys(items))` qui marche aussi mais est moins explicite."
        ),
    },
    {
        "instruction": "Implemente une recherche binaire iterative en Python sur une liste triee.",
        "output": (
            "```python\n"
            "def binary_search(arr: list, target) -> int:\n"
            "    lo, hi = 0, len(arr) - 1\n"
            "    while lo <= hi:\n"
            "        mid = (lo + hi) // 2\n"
            "        if arr[mid] == target:\n"
            "            return mid\n"
            "        elif arr[mid] < target:\n"
            "            lo = mid + 1\n"
            "        else:\n"
            "            hi = mid - 1\n"
            "    return -1\n"
            "```\n"
            "Retourne l'index si trouve, -1 sinon. Complexite O(log n), suppose `arr` deja trie."
        ),
    },
    {
        "instruction": "Ecris une regex Python qui valide un format d'email simple (utilisateur@domaine.tld).",
        "output": (
            "```python\n"
            "import re\n\n"
            "EMAIL_RE = re.compile(r\"^[\\w.+-]+@[\\w-]+\\.[a-zA-Z]{2,}$\")\n\n"
            "def is_valid_email(s: str) -> bool:\n"
            "    return bool(EMAIL_RE.match(s))\n"
            "```\n"
            "Regex simplifiee (pas RFC 5322 complet) : suffisante pour un filtrage "
            "basique, pas pour une validation stricte de tous les cas limites."
        ),
    },
    {
        "instruction": "Ecris une fonction Python qui convertit une duree en secondes vers un format HH:MM:SS.",
        "output": (
            "```python\n"
            "def seconds_to_hhmmss(total_seconds: int) -> str:\n"
            "    hours, remainder = divmod(int(total_seconds), 3600)\n"
            "    minutes, seconds = divmod(remainder, 60)\n"
            "    return f\"{hours:02d}:{minutes:02d}:{seconds:02d}\"\n"
            "```"
        ),
    },
    {
        "instruction": "Ecris une fonction Python qui aplati (flatten) une liste imbriquee de profondeur arbitraire.",
        "output": (
            "```python\n"
            "from collections.abc import Iterable\n\n\n"
            "def flatten(nested) -> list:\n"
            "    result = []\n"
            "    for item in nested:\n"
            "        if isinstance(item, Iterable) and not isinstance(item, (str, bytes)):\n"
            "            result.extend(flatten(item))\n"
            "        else:\n"
            "            result.append(item)\n"
            "    return result\n"
            "```\n"
            "Recursif, exclut explicitement `str`/`bytes` du deplissement (sinon "
            "chaque caractere serait traite comme un element iterable)."
        ),
    },
    {
        "instruction": "Ecris un script py -3.12 qui compte le nombre de lignes de code (hors lignes vides et commentaires) dans un fichier .py donne en argument.",
        "output": (
            "```python\n"
            "import argparse\n\n\n"
            "def count_loc(path: str) -> int:\n"
            "    count = 0\n"
            "    with open(path, encoding=\"utf-8\") as f:\n"
            "        for line in f:\n"
            "            stripped = line.strip()\n"
            "            if stripped and not stripped.startswith(\"#\"):\n"
            "                count += 1\n"
            "    return count\n\n\n"
            "if __name__ == \"__main__\":\n"
            "    parser = argparse.ArgumentParser()\n"
            "    parser.add_argument(\"path\")\n"
            "    args = parser.parse_args()\n"
            "    print(count_loc(args.path))\n"
            "```\n"
            "Heuristique simple (ne gere pas les docstrings multi-lignes comme "
            "commentaires) -- suffisant pour un comptage approximatif."
        ),
    },

    # --- 2. Code fourni inline (le contexte est deja dans la question) ---
    {
        "instruction": (
            "Voici une fonction Python : \n\n"
            "```python\n"
            "def compute_average(numbers):\n"
            "    return sum(numbers) / len(numbers)\n"
            "```\n"
            "Corrige-la pour qu'elle ne plante pas sur une liste vide."
        ),
        "output": (
            "```python\n"
            "def compute_average(numbers):\n"
            "    if not numbers:\n"
            "        return 0.0\n"
            "    return sum(numbers) / len(numbers)\n"
            "```\n"
            "Le code original leve `ZeroDivisionError` sur une liste vide "
            "(`len(numbers) == 0`) -- ajout d'un garde qui retourne 0.0 dans ce cas "
            "(alternative possible : lever une exception explicite si un resultat "
            "silencieux n'est pas souhaite, a adapter selon l'usage)."
        ),
    },
    {
        "instruction": (
            "Ce code Python a un bug : \n\n"
            "```python\n"
            "def get_first_n(items, n):\n"
            "    result = []\n"
            "    for i in range(n):\n"
            "        result.append(items[i])\n"
            "    return result\n"
            "```\n"
            "Il plante si n > len(items). Corrige-le."
        ),
        "output": (
            "```python\n"
            "def get_first_n(items, n):\n"
            "    return items[:n]\n"
            "```\n"
            "Le slicing Python ne leve jamais d'`IndexError` meme si `n` depasse la "
            "longueur de la liste -- il retourne simplement tous les elements "
            "disponibles. Plus court et plus sur que la boucle manuelle originale."
        ),
    },
    {
        "instruction": (
            "Explique ce que fait ce bout de code JavaScript et traduis-le en Python "
            "equivalent :\n\n"
            "```javascript\n"
            "const unique = arr => [...new Set(arr)];\n"
            "```"
        ),
        "output": (
            "Ce code retourne les elements uniques d'un tableau, en s'appuyant sur "
            "`Set` (qui elimine les doublons) puis en le reconvertissant en tableau "
            "via le spread operator `...`.\n\n"
            "Equivalent Python :\n"
            "```python\n"
            "def unique(arr):\n"
            "    return list(set(arr))\n"
            "```\n"
            "Attention : comme en JS, l'ordre d'origine n'est pas garanti preserve. "
            "Pour preserver l'ordre : `list(dict.fromkeys(arr))`."
        ),
    },

    # --- 3. Questions conceptuelles generales (pas de fichier projet en jeu) ---
    {
        "instruction": "Quelle est la difference entre une liste et un tuple en Python ?",
        "output": (
            "Une **liste** (`list`) est mutable (on peut modifier, ajouter, "
            "supprimer des elements apres creation) et s'ecrit avec des crochets "
            "`[1, 2, 3]`. Un **tuple** est immutable (une fois cree, son contenu "
            "ne change plus) et s'ecrit avec des parentheses `(1, 2, 3)`.\n\n"
            "Consequences pratiques : les tuples sont hashables (utilisables comme "
            "cles de dictionnaire ou elements de `set`, contrairement aux listes), "
            "generalement un peu plus rapides a creer/iterer, et communiquent "
            "l'intention \"cette collection ne doit pas changer\"."
        ),
    },
    {
        "instruction": "Explique la difference entre `is` et `==` en Python.",
        "output": (
            "`==` compare l'**egalite de valeur** (est-ce que le contenu est "
            "identique ?), en appelant `__eq__`. `is` compare l'**identite "
            "d'objet** (est-ce litteralement le meme objet en memoire ?).\n\n"
            "Exemple classique : `a = [1, 2]; b = [1, 2]` -> `a == b` est `True` "
            "(meme contenu) mais `a is b` est `False` (deux objets distincts). "
            "`is` est fiable pour comparer a `None`/`True`/`False` (singletons), "
            "mais ne doit pas etre utilise pour comparer des valeurs generales "
            "(nombres, chaines, listes)."
        ),
    },
    {
        "instruction": "Qu'est-ce qu'une race condition et comment l'eviter typiquement ?",
        "output": (
            "Une race condition survient quand plusieurs threads/processus accedent "
            "et modifient une ressource partagee en meme temps, et que le resultat "
            "final depend de l'ordre imprevisible d'execution -- ce qui peut produire "
            "un etat incoherent ou un bug intermittent difficile a reproduire.\n\n"
            "Mitigations typiques : verrous (`threading.Lock`), structures de "
            "donnees thread-safe (`queue.Queue`), operations atomiques fournies par "
            "le langage/l'OS, ou eviter le partage d'etat mutable entre threads en "
            "privilegiant le passage de messages (pas d'etat partage = pas de race "
            "condition possible sur cet etat)."
        ),
    },
    {
        "instruction": "Quelle est la complexite temporelle du tri par insertion, et dans quel cas est-il un bon choix malgre sa complexite ?",
        "output": (
            "Le tri par insertion a une complexite O(n²) dans le cas moyen et pire "
            "cas, O(n) dans le meilleur cas (liste deja triee).\n\n"
            "Il reste un bon choix pour : (1) de tres petites listes (l'overhead "
            "d'un tri plus sophistique comme quicksort/mergesort ne vaut pas le "
            "cout en dessous d'un certain seuil, souvent utilise comme optimisation "
            "interne dans les tris hybrides type Timsort) ; (2) des donnees "
            "presque deja triees (proche du meilleur cas O(n)) ; (3) un tri en "
            "place avec peu de memoire supplementaire, de maniere stable (preserve "
            "l'ordre relatif des elements egaux)."
        ),
    },
    {
        "instruction": "Explique la difference entre un generateur (generator) et une liste en Python, avec un exemple.",
        "output": (
            "Une liste stocke tous ses elements en memoire d'un coup. Un generateur "
            "produit ses valeurs a la demande (lazy evaluation), une par une, sans "
            "tout garder en memoire.\n\n"
            "```python\n"
            "# Liste : calcule et stocke les 10 millions de carres immediatement\n"
            "squares_list = [x**2 for x in range(10_000_000)]\n\n"
            "# Generateur : ne calcule un carre que quand on le demande\n"
            "squares_gen = (x**2 for x in range(10_000_000))\n"
            "```\n"
            "Le generateur est beaucoup plus econome en memoire pour de grandes "
            "sequences ou des flux infinis, mais ne peut etre parcouru qu'une seule "
            "fois (contrairement a une liste, reutilisable)."
        ),
    },
    {
        "instruction": "Qu'est-ce que le pattern Singleton et quand l'eviter ?",
        "output": (
            "Le Singleton garantit qu'une classe n'a qu'une seule instance "
            "accessible globalement dans le programme (ex. une connexion base de "
            "donnees unique, un logger central).\n\n"
            "A eviter quand : (1) ca introduit un etat global cache, rendant le "
            "code plus difficile a tester (impossible d'isoler des tests unitaires "
            "sans reinitialiser l'etat partage) ; (2) le besoin reel est juste "
            "\"une seule instance par defaut\" mais pas \"impossible d'en creer une "
            "seconde\" -- l'injection de dependance explicite est souvent "
            "preferable, plus flexible et plus testable qu'un vrai Singleton."
        ),
    },

    # --- 4. Petites taches de manipulation de donnees generiques ---
    {
        "instruction": "Ecris une fonction Python qui verifie si une chaine est un palindrome (en ignorant la casse et les espaces).",
        "output": (
            "```python\n"
            "def is_palindrome(s: str) -> bool:\n"
            "    cleaned = \"\".join(s.split()).lower()\n"
            "    return cleaned == cleaned[::-1]\n"
            "```"
        ),
    },
    {
        "instruction": "Ecris une fonction Python qui fusionne deux dictionnaires, en donnant priorite aux valeurs du second en cas de cle commune.",
        "output": (
            "```python\n"
            "def merge_dicts(a: dict, b: dict) -> dict:\n"
            "    return {**a, **b}\n"
            "```\n"
            "Le deuxieme dictionnaire (`b`) ecrase les cles communes du premier "
            "(`a`), conformement a l'ordre du unpacking. Equivalent explicite : "
            "`merged = a.copy(); merged.update(b)`."
        ),
    },
    {
        "instruction": "Ecris une fonction Python qui groupe une liste de dictionnaires par la valeur d'une cle donnee.",
        "output": (
            "```python\n"
            "from collections import defaultdict\n\n\n"
            "def group_by(items: list[dict], key: str) -> dict:\n"
            "    grouped = defaultdict(list)\n"
            "    for item in items:\n"
            "        grouped[item[key]].append(item)\n"
            "    return dict(grouped)\n"
            "```\n"
            "Exemple : `group_by([{\"cat\": \"a\", \"v\": 1}, {\"cat\": \"b\", \"v\": 2}, "
            "{\"cat\": \"a\", \"v\": 3}], \"cat\")` -> `{\"a\": [...], \"b\": [...]}`."
        ),
    },
    {
        "instruction": "Ecris un script py -3.12 en ligne de commande qui compte le nombre d'occurrences de chaque mot dans un texte passe via stdin.",
        "output": (
            "```python\n"
            "import sys\n"
            "from collections import Counter\n\n\n"
            "def word_counts(text: str) -> Counter:\n"
            "    words = text.lower().split()\n"
            "    return Counter(words)\n\n\n"
            "if __name__ == \"__main__\":\n"
            "    text = sys.stdin.read()\n"
            "    for word, count in word_counts(text).most_common():\n"
            "        print(f\"{word}: {count}\")\n"
            "```\n"
            "Usage : `echo \"a b a c b a\" | py -3.12 word_counts.py`."
        ),
    },
    {
        "instruction": "Ecris une fonction Python qui retourne le n-ieme nombre de Fibonacci, de maniere iterative (pas recursive).",
        "output": (
            "```python\n"
            "def fibonacci(n: int) -> int:\n"
            "    if n < 0:\n"
            "        raise ValueError(\"n doit etre >= 0\")\n"
            "    a, b = 0, 1\n"
            "    for _ in range(n):\n"
            "        a, b = b, a + b\n"
            "    return a\n"
            "```\n"
            "Complexite O(n) et O(1) en memoire, contrairement a la version "
            "recursive naive qui est O(2^n) sans memoisation."
        ),
    },
    {
        "instruction": "Implemente un tri rapide (quicksort) en Python, version simple non optimisee pour la lisibilite.",
        "output": (
            "```python\n"
            "def quicksort(arr: list) -> list:\n"
            "    if len(arr) <= 1:\n"
            "        return arr\n"
            "    pivot = arr[len(arr) // 2]\n"
            "    left = [x for x in arr if x < pivot]\n"
            "    middle = [x for x in arr if x == pivot]\n"
            "    right = [x for x in arr if x > pivot]\n"
            "    return quicksort(left) + middle + quicksort(right)\n"
            "```\n"
            "Version lisible (pas in-place, cree de nouvelles listes) -- complexite "
            "moyenne O(n log n), pire cas O(n²) sur des donnees deja triees avec ce "
            "choix de pivot naif."
        ),
    },
    {
        "instruction": "Ecris une fonction Python qui parse une chaine CSV simple (une ligne, separee par des virgules, sans guillemets imbriques) en liste.",
        "output": (
            "```python\n"
            "def parse_csv_line(line: str) -> list[str]:\n"
            "    return [field.strip() for field in line.split(\",\")]\n"
            "```\n"
            "Attention : c'est un parsing naif qui ne gere pas les virgules a "
            "l'interieur de champs entre guillemets -- pour un vrai fichier CSV "
            "avec ce cas, utiliser le module standard `csv` plutot que `split(\",\")`."
        ),
    },
    {
        "instruction": "Quelle est la difference entre un decorateur Python et une fonction d'ordre superieur ?",
        "output": (
            "Une **fonction d'ordre superieur** est un terme general : toute "
            "fonction qui prend une fonction en argument et/ou retourne une "
            "fonction. Un **decorateur** est un cas particulier de fonction "
            "d'ordre superieur, avec une syntaxe dediee (`@mon_decorateur`) pour "
            "l'appliquer a la definition d'une fonction/methode/classe.\n\n"
            "```python\n"
            "def mon_decorateur(func):\n"
            "    def wrapper(*args, **kwargs):\n"
            "        print(f\"Appel de {func.__name__}\")\n"
            "        return func(*args, **kwargs)\n"
            "    return wrapper\n\n"
            "@mon_decorateur\n"
            "def dire_bonjour():\n"
            "    print(\"Bonjour\")\n"
            "```\n"
            "Tout decorateur est une fonction d'ordre superieur, mais l'inverse "
            "n'est pas vrai (ex. `map`/`filter` sont des fonctions d'ordre "
            "superieur, pas des decorateurs)."
        ),
    },
    {
        "instruction": "Ecris une fonction Python qui calcule l'ecart-type d'une liste de nombres, sans utiliser numpy.",
        "output": (
            "```python\n"
            "def stddev(numbers: list[float]) -> float:\n"
            "    n = len(numbers)\n"
            "    if n < 2:\n"
            "        return 0.0\n"
            "    mean = sum(numbers) / n\n"
            "    variance = sum((x - mean) ** 2 for x in numbers) / (n - 1)\n"
            "    return variance ** 0.5\n"
            "```\n"
            "Ecart-type d'echantillon (division par n-1, correction de Bessel), "
            "pas d'ecart-type de population (n) -- a adapter selon le besoin exact."
        ),
    },
]


def main():
    with open(OUT_PATH, "w", encoding="utf-8") as out:
        for ex in EXAMPLES:
            out.write(json.dumps({
                "instruction": ex["instruction"],
                "input": "",
                "output": ex["output"],
                "meta": {
                    "source": "h010_selfsufficient_overrefusal_fix",
                    "category": "selfsufficient_direct_answer",
                },
            }, ensure_ascii=False) + "\n")

    print(f"total={len(EXAMPLES)}")
    print(f"ecrit -> {OUT_PATH}")


if __name__ == "__main__":
    main()

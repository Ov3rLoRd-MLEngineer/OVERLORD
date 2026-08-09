"""
H-011 -- Categorie C v2 : reconstruction avec plus de diversite.

Contexte (VERDICT_H010_OVERREFUSAL.md, section 4) : la categorie C v1
(source_selfsufficient.jsonl, 26 exemples, build_source_selfsufficient.py)
etait trop peu diverse -- oversamplee x6, elle a pousse le modele a
sur-generaliser "reponds directement avec confiance" au point de regresser
sur des cas de refus deja bien calibres par H-008 (Prompts 1/3/7 de
VERDICT_H010_OVERREFUSAL.md). Piste documentee : augmenter la diversite
plutot que l'oversampling brut.

Ce fichier reprend les 26 exemples v1 tels quels (importes depuis
build_source_selfsufficient.py, non modifies) et ajoute 30 nouveaux exemples
couvrant des axes absents de v1 :
- scripts autonomes multi-langage (bash, PowerShell, SQL, regex) au lieu de
  Python uniquement,
- corrections de bugs inline sur des patterns differents (argument par
  defaut mutable, off-by-one, is vs ==, recursion sans cas de base, mutation
  pendant iteration, formatage de chaine),
- questions conceptuelles CS/Python sur des sujets non couverts par v1 (GIL,
  multiprocessing vs threading, context managers, staticmethod/classmethod,
  collisions de hachage, complexite des operations de liste, walrus
  operator, copie superficielle/profonde, dataclasses, __slots__),
- structures de donnees/algorithmes generiques supplementaires (LRU cache,
  anagrammes, run-length encoding, chunking, distance de Hamming, fusion
  d'intervalles).

Toutes ces instructions restent volontairement generiques : aucune ne
mentionne un fichier du depot ou un etat de session, donc aucune ne justifie
un refus calibre -- meme critere que v1.

Total vise : 26 + 30 = 56 exemples uniques (plus du double de v1, sans
repeter/paraphraser les 26 existants). N'ecrit ni ne relit
source_rtuning.jsonl (categorie A) ni source_rtuning_rag.jsonl (categorie
B). Ecrase source_selfsufficient.jsonl (meme chemin que v1 -- c'est la
reconstruction demandee, pas un fichier parallele ; historique visible via
git diff). Aucun GPU.
"""
import json
import sys
import os

sys.path.insert(0, os.path.dirname(__file__))
from build_source_selfsufficient import EXAMPLES as EXAMPLES_V1  # noqa: E402

OUT_PATH = r"D:\OVERLORD\workspace\qlora_dataset\source_selfsufficient.jsonl"


NEW_EXAMPLES = [
    # --- 5. Scripts autonomes multi-langage (au-dela de Python) ---
    {
        "instruction": "Ecris un script bash qui trouve recursivement tous les fichiers de plus de 100 Mo dans le repertoire courant et affiche leur chemin et leur taille.",
        "output": (
            "```bash\n"
            "#!/usr/bin/env bash\n"
            "find . -type f -size +100M -exec du -h {} \\; | sort -rh\n"
            "```\n"
            "`-size +100M` filtre les fichiers de plus de 100 Mo, `du -h` affiche une "
            "taille lisible, `sort -rh` trie du plus gros au plus petit."
        ),
    },
    {
        "instruction": "Ecris une commande PowerShell qui liste les 5 fichiers les plus volumineux d'un dossier donne.",
        "output": (
            "```powershell\n"
            "Get-ChildItem -Path $folder -File | Sort-Object Length -Descending | "
            "Select-Object -First 5 Name, @{Name='SizeMB';Expression={[math]::Round($_.Length/1MB,2)}}\n"
            "```\n"
            "`Sort-Object Length -Descending` trie par taille decroissante, "
            "`Select-Object -First 5` ne garde que les 5 premiers."
        ),
    },
    {
        "instruction": "Ecris une requete SQL qui selectionne les 3 lignes les plus recentes de la table `events`, en supposant une colonne `created_at`.",
        "output": (
            "```sql\n"
            "SELECT *\n"
            "FROM events\n"
            "ORDER BY created_at DESC\n"
            "LIMIT 3;\n"
            "```"
        ),
    },
    {
        "instruction": "Ecris une fonction Python qui calcule recursivement la taille totale (en octets) d'un dossier et de tout son contenu.",
        "output": (
            "```python\n"
            "import os\n\n\n"
            "def dir_size(path: str) -> int:\n"
            "    total = 0\n"
            "    for entry in os.scandir(path):\n"
            "        if entry.is_file(follow_symlinks=False):\n"
            "            total += entry.stat().st_size\n"
            "        elif entry.is_dir(follow_symlinks=False):\n"
            "            total += dir_size(entry.path)\n"
            "    return total\n"
            "```\n"
            "`follow_symlinks=False` evite de suivre des liens symboliques qui "
            "pourraient creer une boucle infinie."
        ),
    },
    {
        "instruction": "Ecris une regex Python qui extrait toutes les adresses IPv4 d'un bloc de texte.",
        "output": (
            "```python\n"
            "import re\n\n"
            "IPV4_RE = re.compile(r\"\\b(?:\\d{1,3}\\.){3}\\d{1,3}\\b\")\n\n"
            "def find_ipv4(text: str) -> list[str]:\n"
            "    return IPV4_RE.findall(text)\n"
            "```\n"
            "Simplifiee (ne verifie pas que chaque groupe est <= 255) -- suffisant "
            "pour une extraction basique, pas une validation stricte."
        ),
    },
    {
        "instruction": "Ecris un script py -3.12 qui surveille un dossier par polling et affiche le nom de chaque nouveau fichier qui y apparait, sans dependance externe.",
        "output": (
            "```python\n"
            "import os\n"
            "import time\n\n\n"
            "def watch_folder(folder: str, interval: float = 1.0):\n"
            "    known = set(os.listdir(folder))\n"
            "    while True:\n"
            "        time.sleep(interval)\n"
            "        current = set(os.listdir(folder))\n"
            "        for new_file in current - known:\n"
            "            print(f\"nouveau fichier: {new_file}\")\n"
            "        known = current\n\n\n"
            "if __name__ == \"__main__\":\n"
            "    import sys\n"
            "    watch_folder(sys.argv[1])\n"
            "```\n"
            "Polling simple (pas d'API watchdog du systeme) -- suffisant pour un usage "
            "occasionnel, pas optimal pour une surveillance haute frequence."
        ),
    },
    {
        "instruction": "Ecris un script bash qui sauvegarde un dossier dans une archive tar.gz horodatee.",
        "output": (
            "```bash\n"
            "#!/usr/bin/env bash\n"
            "src=\"$1\"\n"
            "stamp=$(date +%Y%m%d_%H%M%S)\n"
            "tar -czf \"backup_${stamp}.tar.gz\" \"$src\"\n"
            "echo \"Archive creee: backup_${stamp}.tar.gz\"\n"
            "```\n"
            "Usage : `./backup.sh mon_dossier`."
        ),
    },
    {
        "instruction": "Ecris un script py -3.12 qui lit un fichier YAML et l'affiche formate en JSON (module pyyaml).",
        "output": (
            "```python\n"
            "import argparse\n"
            "import json\n"
            "import yaml\n\n\n"
            "def yaml_to_json(path: str) -> str:\n"
            "    with open(path, encoding=\"utf-8\") as f:\n"
            "        data = yaml.safe_load(f)\n"
            "    return json.dumps(data, indent=2, ensure_ascii=False)\n\n\n"
            "if __name__ == \"__main__\":\n"
            "    parser = argparse.ArgumentParser()\n"
            "    parser.add_argument(\"path\")\n"
            "    args = parser.parse_args()\n"
            "    print(yaml_to_json(args.path))\n"
            "```\n"
            "`yaml.safe_load` plutot que `yaml.load` -- evite l'execution de tags "
            "Python arbitraires sur un fichier YAML non fiable."
        ),
    },

    # --- 6. Correction de bug inline (nouveaux patterns, aucun ne recoupe v1) ---
    {
        "instruction": (
            "Ce code Python a un bug subtil : \n\n"
            "```python\n"
            "def append_item(item, acc=[]):\n"
            "    acc.append(item)\n"
            "    return acc\n"
            "```\n"
            "Des appels successifs accumulent des elements d'un appel a l'autre alors que "
            "chaque appel devrait repartir d'une liste vide. Corrige-le."
        ),
        "output": (
            "```python\n"
            "def append_item(item, acc=None):\n"
            "    if acc is None:\n"
            "        acc = []\n"
            "    acc.append(item)\n"
            "    return acc\n"
            "```\n"
            "Le bug classique : un argument par defaut mutable (`acc=[]`) n'est evalue "
            "qu'une seule fois, a la definition de la fonction, et cette meme liste est "
            "reutilisee a chaque appel qui ne fournit pas `acc` explicitement. Le fix "
            "standard est `acc=None` puis creation d'une nouvelle liste a l'interieur."
        ),
    },
    {
        "instruction": (
            "Ce code Python a un bug : \n\n"
            "```python\n"
            "def last_n(items, n):\n"
            "    result = []\n"
            "    for i in range(len(items) - n, len(items)):\n"
            "        result.append(items[i])\n"
            "    return result\n"
            "```\n"
            "Il plante avec un IndexError negatif si n > len(items). Corrige-le."
        ),
        "output": (
            "```python\n"
            "def last_n(items, n):\n"
            "    return items[-n:] if n > 0 else []\n"
            "```\n"
            "Le slicing negatif de Python (`items[-n:]`) gere nativement le cas ou `n` "
            "depasse la longueur de la liste (retourne toute la liste), evitant le calcul "
            "manuel d'index qui devenait negatif dans la version originale."
        ),
    },
    {
        "instruction": (
            "Ce code Python a un bug : \n\n"
            "```python\n"
            "def factorial(n):\n"
            "    return n * factorial(n - 1)\n"
            "```\n"
            "Il plante par depassement de la profondeur de recursion. Corrige-le."
        ),
        "output": (
            "```python\n"
            "def factorial(n):\n"
            "    if n <= 1:\n"
            "        return 1\n"
            "    return n * factorial(n - 1)\n"
            "```\n"
            "Il manquait le cas de base (`n <= 1`) : sans lui, la recursion ne s'arrete "
            "jamais et descend jusqu'a des `n` negatifs, jusqu'a `RecursionError`."
        ),
    },
    {
        "instruction": (
            "Ce code Python a un bug : \n\n"
            "```python\n"
            "def remove_negatives(d):\n"
            "    for key, value in d.items():\n"
            "        if value < 0:\n"
            "            del d[key]\n"
            "    return d\n"
            "```\n"
            "Il leve `RuntimeError: dictionary changed size during iteration`. Corrige-le."
        ),
        "output": (
            "```python\n"
            "def remove_negatives(d):\n"
            "    for key in list(d.keys()):\n"
            "        if d[key] < 0:\n"
            "            del d[key]\n"
            "    return d\n"
            "```\n"
            "On ne peut pas modifier un dict pendant qu'on itere directement dessus. "
            "`list(d.keys())` cree une copie figee des cles avant la boucle, sur laquelle "
            "on peut supprimer des entrees du dict original sans erreur."
        ),
    },
    {
        "instruction": (
            "Ce code Python a un bug : \n\n"
            "```python\n"
            "name = \"Jeremy\"\n"
            "age = 30\n"
            "print(\"%s a %s ans\" % name, age)\n"
            "```\n"
            "Il leve un `TypeError`. Corrige-le."
        ),
        "output": (
            "```python\n"
            "name = \"Jeremy\"\n"
            "age = 30\n"
            "print(\"%s a %s ans\" % (name, age))\n"
            "```\n"
            "L'operateur `%` de formatage attend un seul objet a droite : soit une valeur "
            "unique, soit un tuple regroupant plusieurs valeurs entre parentheses. Sans "
            "les parentheses, Python essaie d'appeler `print` avec un deuxieme argument "
            "positionnel separe, ce qui ne correspond pas a sa signature."
        ),
    },
    {
        "instruction": (
            "Ce code Python a un bug : \n\n"
            "```python\n"
            "def get_config_value(config, key):\n"
            "    if config[key] == None:\n"
            "        return \"valeur par defaut\"\n"
            "    return config[key]\n"
            "```\n"
            "Un reviewer signale que `== None` n'est pas idiomatique et peut cacher des bugs. Corrige-le."
        ),
        "output": (
            "```python\n"
            "def get_config_value(config, key):\n"
            "    if config[key] is None:\n"
            "        return \"valeur par defaut\"\n"
            "    return config[key]\n"
            "```\n"
            "`is None` est la convention Python (PEP 8) : `None` est un singleton, donc "
            "`is` (comparaison d'identite) est a la fois plus explicite et plus sur que "
            "`==`, qui pourrait etre redefini par `__eq__` sur une classe personnalisee et "
            "donner un resultat inattendu face a `None`."
        ),
    },

    # --- 7. Questions conceptuelles CS/Python (axes non couverts par v1) ---
    {
        "instruction": "Qu'est-ce que le GIL (Global Interpreter Lock) en Python et quel impact a-t-il sur le multithreading ?",
        "output": (
            "Le GIL est un verrou global qui garantit qu'un seul thread execute du "
            "bytecode Python a la fois dans un meme processus CPython, meme sur une "
            "machine multi-coeur.\n\n"
            "Consequence pratique : le multithreading Python n'accelere pas les taches "
            "**CPU-bound** (calcul pur), car les threads se partagent le meme coeur "
            "d'execution a tour de role. En revanche, il reste utile pour les taches "
            "**I/O-bound** (attente reseau/disque), car le GIL est libere pendant les "
            "operations bloquantes d'I/O. Pour du parallelisme CPU reel, il faut passer "
            "par `multiprocessing` (plusieurs processus, chacun avec son propre GIL)."
        ),
    },
    {
        "instruction": "Quand choisir `multiprocessing` plutot que `threading` en Python, et inversement ?",
        "output": (
            "**`threading`** : adapte aux taches I/O-bound (requetes reseau, lecture "
            "disque, appels API) -- le GIL est libere pendant l'attente, donc plusieurs "
            "threads progressent en parallele. Overhead de creation faible, memoire "
            "partagee directement entre threads (attention aux race conditions).\n\n"
            "**`multiprocessing`** : necessaire pour les taches CPU-bound (calcul "
            "intensif) car chaque processus a son propre interpreteur et son propre GIL, "
            "permettant un vrai parallelisme sur plusieurs coeurs. Overhead plus eleve "
            "(demarrage de processus, serialisation des donnees echangees via pickle), "
            "memoire non partagee par defaut."
        ),
    },
    {
        "instruction": "Qu'est-ce qu'un context manager Python (`with ...`) et comment en implementer un simple ?",
        "output": (
            "Un context manager garantit qu'une ressource est correctement initialisee "
            "puis liberee, meme en cas d'exception, via les methodes `__enter__` et "
            "`__exit__`.\n\n"
            "```python\n"
            "class Timer:\n"
            "    def __enter__(self):\n"
            "        import time\n"
            "        self.start = time.time()\n"
            "        return self\n\n"
            "    def __exit__(self, exc_type, exc_val, exc_tb):\n"
            "        import time\n"
            "        print(f\"Duree: {time.time() - self.start:.3f}s\")\n"
            "        return False  # ne supprime pas une eventuelle exception\n\n"
            "with Timer():\n"
            "    faire_un_calcul()\n"
            "```\n"
            "Alternative plus courte : le decorateur `@contextlib.contextmanager` sur une "
            "fonction generateur avec un seul `yield`."
        ),
    },
    {
        "instruction": "Quelle est la difference entre `@staticmethod` et `@classmethod` en Python ?",
        "output": (
            "`@staticmethod` : une fonction rattachee a la classe pour l'organisation du "
            "code, mais qui ne recoit ni l'instance (`self`) ni la classe (`cls`) -- "
            "equivalente a une fonction independante placee dans l'espace de noms de la "
            "classe.\n\n"
            "`@classmethod` : recoit la classe elle-meme comme premier argument (`cls`), "
            "utile pour les constructeurs alternatifs (ex. `MaClasse.from_json(data)`) ou "
            "pour acceder/modifier un attribut de classe, tout en respectant l'heritage "
            "(`cls` pointe vers la sous-classe reelle si appele dessus, contrairement a "
            "une reference en dur au nom de la classe)."
        ),
    },
    {
        "instruction": "Qu'est-ce qu'une collision de hachage et comment une table de hachage la gere-t-elle typiquement ?",
        "output": (
            "Une collision survient quand deux cles differentes produisent le meme "
            "hash (ou le meme index apres reduction modulo la taille de la table), donc "
            "revendiquent le meme emplacement de stockage.\n\n"
            "Deux strategies courantes : **chainage separe** (chaque case de la table "
            "contient une liste des elements qui y ont collisionne, parcourue "
            "sequentiellement lors d'une recherche) et **adressage ouvert** (en cas de "
            "collision, on cherche la prochaine case libre selon une regle de sondage -- "
            "lineaire, quadratique, ou double hachage). Le dict Python (CPython) utilise "
            "une variante d'adressage ouvert."
        ),
    },
    {
        "instruction": "Quelle est la complexite en O() des operations courantes sur une liste Python : append, insert(0, x), et acces par index ?",
        "output": (
            "- `list.append(x)` : **O(1) amorti** -- la liste sur-alloue de la memoire, "
            "donc la plupart des ajouts ne demandent pas de reallocation.\n"
            "- `list.insert(0, x)` : **O(n)** -- tous les elements existants doivent etre "
            "decales d'une position pour faire de la place au debut.\n"
            "- `list[i]` (acces par index) : **O(1)** -- les listes Python sont des "
            "tableaux contigus, l'acces par index est un calcul d'adresse direct, pas un "
            "parcours.\n\n"
            "Consequence pratique : pour des insertions/suppressions frequentes en tete, "
            "`collections.deque` (O(1) des deux cotes) est bien plus adaptee qu'une liste."
        ),
    },
    {
        "instruction": "Que fait l'operateur walrus `:=` en Python, avec un exemple ?",
        "output": (
            "L'operateur walrus (`:=`, introduit en Python 3.8) assigne une valeur a une "
            "variable **et** retourne cette valeur dans la meme expression, evitant de "
            "calculer/appeler une chose deux fois.\n\n"
            "```python\n"
            "# Sans walrus : appelle la fonction deux fois\n"
            "data = fetch_data()\n"
            "if data:\n"
            "    process(data)\n\n"
            "# Avec walrus : un seul appel, assignation et test combines\n"
            "if (data := fetch_data()):\n"
            "    process(data)\n"
            "```\n"
            "Usage frequent aussi dans les comprehensions, ex. "
            "`[y for x in data if (y := transform(x)) is not None]`."
        ),
    },
    {
        "instruction": "Quelle est la difference entre une copie superficielle (shallow copy) et une copie profonde (deep copy) en Python ?",
        "output": (
            "Une **copie superficielle** (`copy.copy()`) cree un nouvel objet conteneur, "
            "mais les elements a l'interieur restent des references vers les memes objets "
            "que l'original -- modifier un objet mutable imbrique affecte les deux copies.\n\n"
            "Une **copie profonde** (`copy.deepcopy()`) recree recursivement tous les "
            "objets imbriques, donnant une structure totalement independante de "
            "l'original.\n\n"
            "```python\n"
            "import copy\n"
            "original = {\"liste\": [1, 2, 3]}\n"
            "shallow = copy.copy(original)\n"
            "shallow[\"liste\"].append(4)\n"
            "print(original[\"liste\"])  # [1, 2, 3, 4] -- affecte aussi l'original !\n"
            "```"
        ),
    },
    {
        "instruction": "Qu'est-ce qu'une dataclass Python et quel boilerplate remplace-t-elle ?",
        "output": (
            "`@dataclasses.dataclass` genere automatiquement `__init__`, `__repr__` et "
            "`__eq__` a partir des annotations de type declarees dans la classe, evitant "
            "d'ecrire ce code repetitif a la main.\n\n"
            "```python\n"
            "from dataclasses import dataclass\n\n"
            "@dataclass\n"
            "class Point:\n"
            "    x: float\n"
            "    y: float\n\n"
            "p = Point(1.0, 2.0)\n"
            "print(p)          # Point(x=1.0, y=2.0) -- __repr__ genere\n"
            "print(p == Point(1.0, 2.0))  # True -- __eq__ genere\n"
            "```\n"
            "Options utiles : `frozen=True` (immutabilite), `order=True` (comparaisons "
            "`<`/`>` generees)."
        ),
    },
    {
        "instruction": "Qu'est-ce que `__slots__` en Python et pourquoi l'utiliser ?",
        "output": (
            "Par defaut, chaque instance Python stocke ses attributs dans un dictionnaire "
            "interne (`__dict__`), flexible mais couteux en memoire. Declarer `__slots__` "
            "sur une classe fixe explicitement la liste des attributs autorises et "
            "supprime ce dictionnaire par instance, au profit d'un stockage plus compact.\n\n"
            "```python\n"
            "class Point:\n"
            "    __slots__ = (\"x\", \"y\")\n"
            "    def __init__(self, x, y):\n"
            "        self.x = x\n"
            "        self.y = y\n"
            "```\n"
            "Interet principal : reduire l'empreinte memoire quand on cree un tres grand "
            "nombre d'instances. Contrepartie : on ne peut plus ajouter dynamiquement un "
            "attribut non declare dans `__slots__`."
        ),
    },

    # --- 8. Structures de donnees / algorithmes generiques supplementaires ---
    {
        "instruction": "Implemente un cache LRU (Least Recently Used) simple en Python avec `collections.OrderedDict`, capacite fixe.",
        "output": (
            "```python\n"
            "from collections import OrderedDict\n\n\n"
            "class LRUCache:\n"
            "    def __init__(self, capacity: int):\n"
            "        self.capacity = capacity\n"
            "        self.cache = OrderedDict()\n\n"
            "    def get(self, key):\n"
            "        if key not in self.cache:\n"
            "            return None\n"
            "        self.cache.move_to_end(key)\n"
            "        return self.cache[key]\n\n"
            "    def put(self, key, value):\n"
            "        if key in self.cache:\n"
            "            self.cache.move_to_end(key)\n"
            "        self.cache[key] = value\n"
            "        if len(self.cache) > self.capacity:\n"
            "            self.cache.popitem(last=False)\n"
            "```\n"
            "`move_to_end` marque une entree comme recemment utilisee ; `popitem(last=False)` "
            "evince l'entree la moins recemment utilisee quand la capacite est depassee."
        ),
    },
    {
        "instruction": "Ecris une fonction Python qui verifie si deux chaines sont des anagrammes l'une de l'autre.",
        "output": (
            "```python\n"
            "from collections import Counter\n\n\n"
            "def are_anagrams(a: str, b: str) -> bool:\n"
            "    a_clean = a.replace(\" \", \"\").lower()\n"
            "    b_clean = b.replace(\" \", \"\").lower()\n"
            "    return Counter(a_clean) == Counter(b_clean)\n"
            "```\n"
            "`Counter` compte les occurrences de chaque caractere ; deux chaines sont "
            "anagrammes si et seulement si leurs comptages sont identiques."
        ),
    },
    {
        "instruction": "Ecris une fonction Python qui effectue un encodage par plages (run-length encoding) d'une chaine, ex. 'aaabbc' -> 'a3b2c1'.",
        "output": (
            "```python\n"
            "def run_length_encode(s: str) -> str:\n"
            "    if not s:\n"
            "        return \"\"\n"
            "    result = []\n"
            "    current = s[0]\n"
            "    count = 1\n"
            "    for ch in s[1:]:\n"
            "        if ch == current:\n"
            "            count += 1\n"
            "        else:\n"
            "            result.append(f\"{current}{count}\")\n"
            "            current = ch\n"
            "            count = 1\n"
            "    result.append(f\"{current}{count}\")\n"
            "    return \"\".join(result)\n"
            "```"
        ),
    },
    {
        "instruction": "Ecris une fonction Python qui decoupe (chunk) une liste en sous-listes de taille n.",
        "output": (
            "```python\n"
            "def chunk(items: list, n: int) -> list[list]:\n"
            "    return [items[i:i + n] for i in range(0, len(items), n)]\n"
            "```\n"
            "Le dernier chunk peut etre plus court que `n` si `len(items)` n'est pas un "
            "multiple exact de `n` -- comportement attendu, pas un bug."
        ),
    },
    {
        "instruction": "Ecris une fonction Python qui calcule la distance de Hamming entre deux chaines de meme longueur (nombre de positions differentes).",
        "output": (
            "```python\n"
            "def hamming_distance(a: str, b: str) -> int:\n"
            "    if len(a) != len(b):\n"
            "        raise ValueError(\"les deux chaines doivent avoir la meme longueur\")\n"
            "    return sum(ca != cb for ca, cb in zip(a, b))\n"
            "```"
        ),
    },
    {
        "instruction": "Ecris une fonction Python qui fusionne une liste d'intervalles (tuples start, end) qui se chevauchent.",
        "output": (
            "```python\n"
            "def merge_intervals(intervals: list[tuple[int, int]]) -> list[tuple[int, int]]:\n"
            "    if not intervals:\n"
            "        return []\n"
            "    sorted_intervals = sorted(intervals, key=lambda pair: pair[0])\n"
            "    merged = [sorted_intervals[0]]\n"
            "    for start, end in sorted_intervals[1:]:\n"
            "        last_start, last_end = merged[-1]\n"
            "        if start <= last_end:\n"
            "            merged[-1] = (last_start, max(last_end, end))\n"
            "        else:\n"
            "            merged.append((start, end))\n"
            "    return merged\n"
            "```\n"
            "Trie d'abord par debut d'intervalle, puis fusionne au fil de l'eau : "
            "`start <= last_end` signifie que l'intervalle courant chevauche le dernier "
            "intervalle fusionne."
        ),
    },
]


def main():
    all_examples = list(EXAMPLES_V1) + NEW_EXAMPLES
    with open(OUT_PATH, "w", encoding="utf-8") as out:
        for ex in all_examples:
            out.write(json.dumps({
                "instruction": ex["instruction"],
                "input": "",
                "output": ex["output"],
                "meta": {
                    "source": "h011_selfsufficient_overrefusal_fix_v2",
                    "category": "selfsufficient_direct_answer",
                },
            }, ensure_ascii=False) + "\n")

    print(f"v1 (repris tel quel) = {len(EXAMPLES_V1)}")
    print(f"v2 (nouveaux)        = {len(NEW_EXAMPLES)}")
    print(f"total                = {len(all_examples)}")
    print(f"ecrit -> {OUT_PATH}")


if __name__ == "__main__":
    main()

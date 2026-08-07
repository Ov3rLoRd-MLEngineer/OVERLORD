"""
Source R-Tuning Stage 3 -- dataset de refus calibres (certain/incertain).

Objectif : calibrer un futur Stage 3 (au-dessus de l'adaptateur Stage 2
CommitPack) pour qu'il dise explicitement "je ne sais pas / je ne peux pas
confirmer sans verifier" sur les questions qui exigent un etat projet
qu'il n'a pas (contenu reel d'un fichier, sortie nvidia-smi en direct,
historique de session, resultat de run non fourni) -- plutot que de
confabuler une reponse plausible mais fausse, comme observe dans
`workspace/qlora_dataset/VERDICT_COMMITPACK.md`.

Grounding (pas invente) :
- `VERDICT_COMMITPACK.md` (8 prompts x 3 modeles, genere le 2026-08-04 via
  inference reelle Ollama + adaptateur PEFT local) documente deja une
  "Observation objective" : l'adaptateur stage2_commitpack produit
  systematiquement un diff plausible en forme mais hallucine le fichier/
  contexte (Prompt 5 -- question GPU -- repond par un diff Python/PyGame.py ;
  Prompt 6 -- question conceptuelle Segnets -- diff Django segnet/models.py ;
  Prompt 7 -- etat des lieux pipeline -- invente une arborescence
  "overlord-pipelines/pipeline_v3_config.json" qui n'existe pas dans ce
  depot ; Prompt 8 -- question de strategie -- invente des chemins de
  checkpoint plausibles mais fictifs).
- `ov3rlord-coder-stage2v2` (modele deploye sur Ollama) va plus loin sur le
  Prompt 5 : il invente du materiel qui n'existe pas sur cette machine
  ("GPU2 (1080 Ti)", "GPU1 (RTX 4080)") alors que le vrai setup est
  RTX 5080 + RTX 5060 Ti (CLAUDE.md) -- confabulation convaincante (ton
  assure, aucun signal d'incertitude), le profil exact que R-Tuning cible.
- `qwen2.5-coder:14b` (Prompt 7) illustre a l'inverse un refus calibre
  correct spontane : "je n'ai pas acces aux details techniques specifiques
  de vos pipelines" -- reference de style pour les exemples "incertain"
  ci-dessous, meme si le reste de ses reponses est trop generique pour
  servir de reference "certain" (Style 1.50/5 rapporte dans
  RAPPORT_SESSION_02_04_AOUT_2026.md -- correct mais peu utile).

Methode (explicite, pas un score auto-genere -- cf CLAUDE.md section
"Economie de session" sur les faux verdicts) :
1. **8 exemples source ("seed")**, un par prompt reel de VERDICT_COMMITPACK.md
   (`SEED_PROMPTS`) : la version "incertain" est un refus calibre ecrit a la
   main qui repond a la VRAIE question posee ce jour-la, la version
   "certain" est le meme sujet reduit a la partie generale/repondable sans
   etat cache. `meta.seed_prompt_index` trace la provenance.
2. **10 categories generiques de "questions qui exigent un etat non
   verifie"** (`CATEGORIES`), chacune directement calquee sur un pattern de
   confabulation reellement observe dans le fichier source (fichier non lu,
   materiel/GPU non verifie en direct, arborescence de projet non verifiee,
   conclusion "definitive" a partir d'un echantillon insuffisant, "memoire"
   d'une session passee, signature d'API non verifiee sur la version
   installee, limite generative vs bug de pipeline non tranchee, ligne de
   bug non lue, recommandation strategique sans contraintes reelles, compte
   de fichiers non recompte sur disque). Chaque categorie est instanciee sur
   plusieurs sujets concrets tires du vocabulaire reel du depot (fichiers
   cites dans CLAUDE.md) pour rester realiste, sans pretendre que ce sont
   des cas reellement rencontres.

Ce fichier ne lance aucun entrainement et ne touche aucun GPU -- generation
de texte pure, deterministe, relisible ligne par ligne.
"""
import json

OUT_PATH = r"D:\OVERLORD\workspace\qlora_dataset\source_rtuning.jsonl"

UNCERTAIN_PREFIX = "incertain"
CERTAIN_PREFIX = "certain"


# ---------------------------------------------------------------------------
# 1. Exemples source, ancres sur les 8 prompts reels de VERDICT_COMMITPACK.md
# ---------------------------------------------------------------------------

SEED_PROMPTS = [
    {
        "index": 1,
        "topic": "fichier_specifique",
        "incertain_instruction": (
            "agents/quality_sort.py: ajoute une detection des masques trop "
            "petits (moins de 2% de la surface totale de l'image) comme "
            "categorie a_exclure, dans le style des conventions du projet."
        ),
        "incertain_output": (
            "Je ne peux pas ecrire ce diff de maniere fiable sans avoir lu "
            "le contenu actuel de `agents/quality_sort.py` -- je ne connais "
            "ni la structure exacte de la fonction de scoring, ni les noms "
            "des categories deja definies (`a_doubtful`, `a_incomplete`, "
            "...), ni le format du chargement du masque. Inventer un diff "
            "sur une base supposee risquerait de cibler des lignes qui "
            "n'existent pas ou de casser une convention deja en place. "
            "Peux-tu me montrer le fichier (ou la fonction concernee) ? "
            "Sur le fond, l'approche generale est claire : calculer la "
            "surface du masque (`pixels.sum()` ou equivalent), comparer au "
            "seuil `0.02 * hauteur * largeur`, et retourner la nouvelle "
            "categorie si en dessous -- je peux ecrire ce diff des que j'ai "
            "le fichier reel."
        ),
        "certain_instruction": (
            "En Python, comment detecter en general qu'un masque binaire "
            "occupe moins de 2% de la surface totale d'une image, "
            "independamment d'un fichier de projet precis ?"
        ),
        "certain_output": (
            "```python\n"
            "import numpy as np\n\n"
            "def is_mask_too_small(mask: np.ndarray, threshold: float = 0.02) -> bool:\n"
            "    \"\"\"mask : array 2D, valeurs non nulles = pixels du masque.\"\"\"\n"
            "    total_pixels = mask.shape[0] * mask.shape[1]\n"
            "    mask_pixels = int(np.count_nonzero(mask))\n"
            "    return (mask_pixels / total_pixels) < threshold\n"
            "```\n"
            "Le principe : compter les pixels non nuls du masque (pas la "
            "somme brute des valeurs si le masque n'est pas strictement "
            "binaire 0/1), diviser par la surface totale, comparer au "
            "seuil. C'est independant de tout fichier -- l'integration "
            "concrete (nom de la categorie, endroit exact dans le pipeline "
            "de scoring) depend du code reel du projet."
        ),
    },
    {
        "index": 3,
        "topic": "fichier_specifique",
        "incertain_instruction": (
            "corrige un crash UnicodeEncodeError latent dans un script qui "
            "affiche des logs avec des emojis sur Windows, dans "
            "handsegnet/annotate.py"
        ),
        "incertain_output": (
            "Je ne peux pas corriger `handsegnet/annotate.py` sans en voir "
            "le contenu actuel -- je ne sais pas ou se trouvent les appels "
            "`print()`/logging concernes, ni si le fichier configure deja "
            "un encodage de sortie. Proposer un correctif a l'aveugle "
            "risquerait de modifier la mauvaise section ou de dupliquer une "
            "protection deja presente. Peux-tu me montrer le fichier, ou au "
            "moins la trace d'erreur complete (traceback) ? Ce que je peux "
            "confirmer sans le fichier : la cause generale de ce type de "
            "crash et le correctif standard (voir ci-dessous) -- je peux "
            "l'appliquer au bon endroit des que j'ai le fichier reel."
        ),
        "certain_instruction": (
            "Quelle est la cause generale d'un UnicodeEncodeError quand un "
            "script Python affiche des emojis dans un terminal Windows, et "
            "comment le corrige-t-on typiquement ?"
        ),
        "certain_output": (
            "La cause habituelle : la console Windows (ou une redirection "
            "vers un fichier/pipe) utilise par defaut un encodage historique "
            "(`cp1252`/`cp437`) plutot qu'UTF-8, et cet encodage ne peut pas "
            "representer les caracteres emoji. `print()` leve alors "
            "`UnicodeEncodeError: 'charmap' codec can't encode character...`.\n\n"
            "Corrections standard, de la plus locale a la plus globale :\n"
            "- Forcer l'UTF-8 en tete de script : "
            "`sys.stdout.reconfigure(encoding=\"utf-8\")` (Python 3.7+).\n"
            "- Ou definir la variable d'environnement `PYTHONIOENCODING=utf-8` "
            "avant de lancer le script.\n"
            "- Eviter les emojis dans les logs destines a etre rediriges "
            "vers un fichier si l'encodage cible n'est pas garanti."
        ),
    },
    {
        "index": 5,
        "topic": "materiel_gpu",
        "incertain_instruction": (
            "GPU1 est monte a 99% pendant la generation, revenu a l'etat de "
            "repos (117 Mo) apres fermeture propre. Est-ce normal ?"
        ),
        "incertain_output": (
            "Je ne peux pas confirmer si c'est normal sans voir une sortie "
            "`nvidia-smi` reelle (au moment du pic et apres fermeture), ni "
            "savoir quel GPU/quelle carte est physiquement \"GPU1\" sur ta "
            "machine -- je ne dois pas inventer un modele de carte ou un "
            "comportement de repartition que je n'ai pas verifie. En "
            "revanche, sur le principe general : un GPU qui retombe a un "
            "usage memoire minimal apres la fermeture propre d'un process "
            "est le comportement attendu (le contexte CUDA et l'allocateur "
            "sont liberes a la sortie du process). Si tu peux me coller la "
            "sortie `nvidia-smi` avant/pendant/apres, je peux verifier "
            "precisement."
        ),
        "certain_instruction": (
            "En general, pourquoi l'usage VRAM d'un GPU retombe-t-il apres "
            "la fin d'un script d'entrainement ou de generation, "
            "independamment du materiel exact ?"
        ),
        "certain_output": (
            "Quand un process Python qui utilise CUDA se termine (fermeture "
            "propre, pas un crash), le driver NVIDIA libere le contexte "
            "CUDA associe a ce process : les tenseurs alloues sur le GPU, "
            "le cache de l'allocateur (PyTorch garde normalement un cache "
            "memoire pour eviter des `cudaMalloc` repetes), et les buffers "
            "de kernel sont tous rendus au systeme. C'est pour ca qu'on "
            "voit l'usage VRAM retomber a un niveau proche de zero (le "
            "residuel restant vient generalement du driver/contexte "
            "d'affichage, pas du script). Un usage qui reste eleve apres "
            "fermeture propre indiquerait plutot un process zombie ou une "
            "fuite au niveau du driver, pas un comportement normal."
        ),
    },
    {
        "index": 6,
        "topic": "conceptuel_projet",
        "incertain_instruction": (
            "je pense qu'il faut voir les segnets comme mon portefeuille de "
            "competences plutot que comme un produit fini -- qu'en "
            "penses-tu ?"
        ),
        "incertain_output": (
            "C'est un jugement de positionnement produit/carriere, pas une "
            "question factuelle verifiable -- je peux donner un avis "
            "argumente, mais je ne veux pas le presenter comme une "
            "conclusion certaine ni inventer des details sur l'etat actuel "
            "des SegNets que je n'ai pas verifies (nombre de modeles "
            "publies, avancement de chacun). Ce que je sais avec confiance "
            "(cf CLAUDE.md/memoire projet) : FootSegNet et HandSegNet sont "
            "publies publiquement (GitHub MIT + HuggingFace Apache 2.0) -- "
            "au-dela, je prefere verifier l'etat courant (`DOCS/INDEX.md`, "
            "`DOCS/MD/INDEX_PUBLICATIONS.md` s'il existe) avant d'affirmer "
            "combien de SegNets sont \"finis\" plutot que de le supposer."
        ),
        "certain_instruction": (
            "En general, quelle est la difference entre presenter un outil "
            "technique comme un \"produit fini\" et comme une \"preuve de "
            "competence\" dans un portfolio ?"
        ),
        "certain_output": (
            "Un \"produit fini\" implique une promesse de stabilite, de "
            "support et de perimetre defini pour un utilisateur externe -- "
            "on s'engage sur une roadmap et une maintenance. Une \"preuve "
            "de competence\" (portfolio) n'a pas cette contrainte : "
            "l'objectif est de demontrer une capacite technique (choix "
            "d'architecture, rigueur d'evaluation, code lisible) a un "
            "public qui evalue le savoir-faire plutot que d'attendre un "
            "usage en production. Le meme depot peut remplir les deux "
            "roles a des degres differents selon les composants -- ce qui "
            "compte est d'etre honnete sur lequel des deux statuts "
            "s'applique a chaque piece, plutot que de presenter tout comme "
            "fini par defaut."
        ),
    },
    {
        "index": 7,
        "topic": "etat_pipeline",
        "incertain_instruction": (
            "peux-tu me faire un etat des lieux rapide du pipeline avant "
            "qu'on continue ?"
        ),
        "incertain_output": (
            "Je n'ai pas d'acces direct et a jour a l'arborescence du "
            "depot dans cet echange -- je ne dois pas inventer une "
            "structure de dossiers ou des fichiers de configuration "
            "(je ne vais pas presenter un `overlord-pipelines/` ou un "
            "`pipeline_v3_config.json` sans avoir verifie qu'ils existent "
            "reellement). Pour un etat des lieux fiable, le plus sur est de "
            "lister l'arborescence reelle (`git status`, `ls`) et de lire "
            "`CLAUDE.md` + le `CONTEXTE_OVERLORD_V*.md` le plus recent -- "
            "je peux le faire immediatement si tu me donnes acces, ou tu "
            "peux me coller le dernier etat connu."
        ),
        "certain_instruction": (
            "De facon generale, quelles sont les etapes typiques d'un "
            "pipeline de production d'images/videos IA (sourcing -> "
            "scenario -> generation -> post-production) ?"
        ),
        "certain_output": (
            "Un pipeline de ce type suit generalement : (1) **sourcing** -- "
            "identifier des tendances/references qui orientent le contenu "
            "a produire ; (2) **scenario/script** -- generer une trame "
            "narrative structuree (souvent via un LLM) ; (3) **storyboard** "
            "-- decouper la trame en plans/keyframes concrets ; "
            "(4) **generation** -- produire les images/frames via un moteur "
            "de diffusion (texte-vers-image, image-vers-video) ; "
            "(5) **post-production** -- upscale, interpolation, correction "
            "colorimetrique, montage/assemblage ; (6) **publication** -- "
            "export final et diffusion. L'ordre exact et les etapes "
            "presentes varient selon le projet -- ceci est le schema "
            "generique, pas l'etat verifie d'un pipeline particulier."
        ),
    },
    {
        "index": 4,
        "topic": "conclusion_definitive",
        "incertain_instruction": (
            "footsegnet/controlnet: le run de test x30 donne les memes "
            "resultats que x10/x20 -- conclusion definitive a documenter"
        ),
        "incertain_output": (
            "Je ne peux pas ecrire une conclusion \"definitive\" sans voir "
            "les chiffres reels des trois runs (temps mesures, nombre "
            "d'images, variance entre executions) -- affirmer une cause "
            "(\"le modele est saturé\", \"aucun gain possible\") sans ces "
            "donnees serait une extrapolation presentee a tort comme un "
            "fait verifie. Peux-tu me montrer les logs/temps mesures des "
            "trois runs ? Ce que je peux dire sans les chiffres : trois "
            "resultats identiques sur x10/x20/x30 est un indice de "
            "plateau, mais ca ne devient une conclusion fiable qu'apres "
            "avoir exclu une erreur de mesure (meme seed, meme cache, "
            "meme charge machine au moment de chaque run)."
        ),
        "certain_instruction": (
            "En general, que signifie le fait que plusieurs runs "
            "successifs d'un benchmark donnent le meme resultat malgre une "
            "charge croissante (x10, x20, x30) ?"
        ),
        "certain_output": (
            "C'est generalement l'indice d'un plateau/goulot d'etranglement "
            "qui ne depend pas du parametre qu'on fait varier (ici le "
            "facteur x10/x20/x30) -- une autre ressource (temps de chargement "
            "du modele, I/O disque, latence reseau, etape sequentielle non "
            "parallelisable) domine le temps total et masque l'effet du "
            "parametre teste. Avant de conclure a une limite structurelle du "
            "modele lui-meme, il faut cependant exclure les causes triviales : "
            "cache chaud identique sur les trois runs, meme charge machine "
            "concurrente, mesure qui inclut un temps fixe (chargement) "
            "disproportionne par rapport au travail variable mesure."
        ),
    },
    {
        "index": 8,
        "topic": "recommandation_strategique",
        "incertain_instruction": (
            "quelle est la meilleure strategie entre continuer sur le "
            "modele proxy 4B ou investir dans le run 30B multi-GPU ?"
        ),
        "incertain_output": (
            "Je ne peux pas trancher \"la meilleure strategie\" sans "
            "connaitre les contraintes reelles (budget/temps GPU "
            "disponible, deadline, ecart de qualite mesure entre les deux "
            "options, risque de crash memoire deja observe ou non) -- "
            "inventer un verdict avec une justification plausible mais non "
            "verifiee (checkpoints, logs de crash precis) serait "
            "trompeur. Peux-tu preciser : combien de temps GPU reste "
            "disponible avant la deadline, et as-tu deja une mesure de "
            "qualite (pas juste un ressenti) sur le modele 4B actuel ? "
            "Avec ca je peux donner une recommandation concrete."
        ),
        "certain_instruction": (
            "Quels criteres generaux faut-il rassembler avant de trancher "
            "entre continuer un petit modele (proxy) et investir dans un "
            "run beaucoup plus gros et couteux ?"
        ),
        "certain_output": (
            "Criteres generalement necessaires avant de trancher : "
            "(1) le gain de qualite mesure (pas suppose) du plus gros "
            "modele sur un echantillon representatif ; (2) le cout reel "
            "(temps GPU, argent si cloud, risque d'echec/crash) du run "
            "plus gros rapporte a ce gain ; (3) le temps disponible avant "
            "une deadline -- un gain marginal qui arrive trop tard n'a pas "
            "de valeur ; (4) si le petit modele suffit deja pour l'usage "
            "vise (parfois le gain de qualite du plus gros modele est "
            "invisible pour le cas d'usage reel) ; (5) la reversibilite -- "
            "un petit modele qu'on peut ameliorer iterativement est moins "
            "risque qu'un run couteux qu'on ne peut relancer qu'une fois."
        ),
    },
    {
        "index": 2,
        "topic": "code_general_sans_etat_cache",
        "incertain_instruction": (
            "Le validateur JSONL que tu m'as ecrit hier tournait sur quel "
            "fichier de dataset exactement, et combien de lignes en erreur "
            "avait-il trouvees ?"
        ),
        "incertain_output": (
            "Je n'ai pas de memoire persistante entre sessions/conversations "
            "-- je ne peux pas confirmer quel fichier a ete valide \"hier\" "
            "ni quel a ete le resultat sans que tu me le donnes ou que je "
            "le retrouve dans un fichier de sortie/log reel sur disque. "
            "Inventer un nom de fichier et un nombre de lignes en erreur "
            "serait une confabulation. Si tu as garde la sortie du script "
            "(`--output` du validateur) ou le terminal, colle-la moi et je "
            "peux l'interpreter directement."
        ),
        "certain_instruction": (
            "Ecris un script py -3.12 qui valide un fichier JSONL de "
            "dataset d'entrainement : verifie que chaque ligne contient "
            "bien les cles instruction/input/output et que output n'est "
            "pas vide."
        ),
        "certain_output": (
            "```python\n"
            "#!/usr/bin/env python3\n"
            "import argparse\n"
            "import json\n"
            "import sys\n\n\n"
            "def validate_jsonl(path: str) -> int:\n"
            "    \"\"\"Retourne le nombre de lignes invalides.\"\"\"\n"
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
            "```"
        ),
    },
]


# ---------------------------------------------------------------------------
# 2. Categories generiques instanciees sur des sujets concrets du depot
# ---------------------------------------------------------------------------

CATEGORIES = [
    {
        "topic": "fichier_specifique",
        "subjects": [
            ("footsegnet/batch_premask.py", "un fallback grounding VLM quand SAM echoue"),
            ("agents/context_bus.py", "un TTL d'expiration sur les cles ecrites"),
            ("handsegnet/annotate.py", "un raccourci clavier pour trier par confiance SAM"),
            ("agent_supervisor_v2.py", "une etape de retry exponentiel sur les erreurs ComfyUI"),
            ("agents/config_manager.py", "un override de config par variable d'environnement"),
            ("footsegnet/controlnet/quality_sort.py", "une categorie a_exclure pour fragmentation de masque"),
            ("agents/production_video/cycle_detector.py", "un score de drift pondere par articulation"),
            ("agents/infra/rag_query.py", "un cache LRU sur les requetes recentes"),
            ("maestro.py", "un mode dry-run qui n'appelle pas ComfyUI"),
            ("agents/director.py", "une nouvelle transition narrative"),
        ],
        "incertain_instruction": "{file}: ajoute {feature}, dans le style des conventions du projet.",
        "incertain_output": (
            "Je ne peux pas ecrire ce diff sans avoir lu le contenu actuel "
            "de `{file}` -- je ne connais ni sa structure exacte, ni les "
            "conventions locales deja en place (nommage, gestion d'erreur, "
            "logging). Inventer un patch sur une base supposee risquerait "
            "de cibler des lignes qui n'existent pas ou de dupliquer une "
            "fonctionnalite deja presente. Peux-tu me montrer le fichier "
            "(ou la fonction concernee) ? Je peux ecrire le diff exact des "
            "que je l'ai."
        ),
        "certain_instruction": (
            "Independamment d'un fichier de projet precis, quelle est "
            "l'approche generale pour ajouter {feature} a un module Python "
            "existant sans connaitre son implementation exacte ?"
        ),
        "certain_output": (
            "L'approche generale, quel que soit le fichier reel : "
            "(1) identifier le point d'entree logique existant le plus "
            "proche (fonction/classe deja responsable du comportement "
            "voisin) plutot que de creer un chemin parallele ; (2) ajouter "
            "la nouvelle logique comme une extension isolee (nouvelle "
            "fonction/parametre) pour limiter le risque de regression sur "
            "le comportement existant ; (3) suivre le style de gestion "
            "d'erreur deja utilise dans le module (try/except explicite, "
            "logging, valeurs de repli) plutot que d'en introduire un "
            "nouveau ; (4) ajouter un test ou une verification manuelle "
            "cible avant de considerer le changement termine. Le detail "
            "precis (nom de fonction, emplacement exact) depend du code "
            "reel, non disponible ici."
        ),
    },
    {
        "topic": "materiel_gpu",
        "subjects": [
            ("la RTX 5080", "88", "un batch de generation ComfyUI"),
            ("la RTX 5060 Ti", "95", "un run Ollama qwen2.5vl"),
            ("GPU0", "70", "un entrainement QLoRA"),
            ("GPU1", "60", "un upscale SeedVR2"),
            ("la carte principale", "99", "un rendu AniSora"),
            ("la seconde carte", "45", "une extraction DepthAnythingV2"),
            ("le GPU d'inference Ollama", "80", "un appel qwen3-coder"),
            ("le GPU d'entrainement", "97", "un run Stage 2 CommitPack"),
            ("la carte 16 Go la moins utilisee", "30", "un preprocessing ControlNet"),
            ("la carte affichee en premier par nvidia-smi", "55", "un test AnimateDiff"),
        ],
        "incertain_instruction": (
            "{gpu} est montee a {pct}% pendant {task}, la temperature a "
            "l'air elevee -- c'est preoccupant ?"
        ),
        "incertain_output": (
            "Je ne peux pas juger sans une sortie `nvidia-smi` reelle (le "
            "pourcentage seul ne dit rien sur la temperature, et je ne "
            "connais pas les limites thermiques exactes de ta carte) -- je "
            "ne vais pas inventer un seuil de temperature \"normal\" precis "
            "sans le verifier pour ton materiel exact. Colle-moi la sortie "
            "`nvidia-smi --query-gpu=temperature.gpu,utilization.gpu,power.draw "
            "--format=csv` et je peux l'interpreter directement. En regle "
            "generale seulement : un GPU consumer moderne est concu pour "
            "tenir 100% d'utilisation en continu jusqu'a ~83-90°C sans "
            "dommage (throttling automatique au-dela) -- mais ca varie par "
            "modele, a verifier plutot que supposer."
        ),
        "certain_instruction": (
            "En general, a partir de quel principe un GPU NVIDIA moderne "
            "protege-t-il son materiel en cas de surchauffe, par exemple "
            "pendant {task} ?"
        ),
        "certain_output": (
            "Le mecanisme general s'appelle le thermal throttling : le "
            "driver/firmware du GPU reduit automatiquement sa frequence "
            "(et donc sa consommation/chaleur) des qu'une temperature "
            "seuil (typiquement autour de 83-90°C selon le modele) est "
            "approchee, pour eviter d'atteindre la limite critique ou le "
            "GPU couperait le calcul en urgence. Cote logiciel, on observe "
            "ce phenomene comme une baisse de performance (frames/s, "
            "steps/s) sans erreur explicite -- la carte ne \"casse\" pas, "
            "elle ralentit. Le point de coupure d'urgence est different "
            "(plus haut) et signale generalement un arret brutal du "
            "process, pas juste un ralentissement."
        ),
    },
    {
        "topic": "arborescence_projet",
        "subjects": [
            ("le module de scoring qualite", "quality_engine"),
            ("le nouvel orchestrateur video", "video_orchestrator"),
            ("le sous-systeme de publication", "publisher"),
            ("le gestionnaire de cache RAG", "rag_cache"),
            ("le module de detection de drift", "drift_detector"),
            ("le nouveau dashboard", "dashboard"),
            ("le sous-systeme de retry GPU", "gpu_retry"),
            ("le module d'evaluation qualitative", "eval_module"),
            ("le gestionnaire de queue de rendu", "render_queue"),
            ("le module de synthese vocale", "tts_module"),
        ],
        "incertain_instruction": (
            "Peux-tu me faire un etat des lieux rapide sur {module} "
            "({slug}) avant qu'on continue ?"
        ),
        "incertain_output": (
            "Je n'ai pas d'acces direct et a jour a l'arborescence du depot "
            "dans cet echange -- je ne dois pas inventer une structure de "
            "dossiers, des noms de fichiers ou un pourcentage d'avancement "
            "pour `{slug}`. Pour un etat des lieux fiable : liste "
            "l'arborescence reelle (`git status`, `ls -R` cible), ou lis "
            "`CLAUDE.md` + le dernier `CONTEXTE_OVERLORD_V*.md` -- je peux "
            "le faire immediatement si tu me donnes acces au depot, ou "
            "colle-moi le dernier etat connu."
        ),
        "certain_instruction": (
            "De facon generale, quelles informations minimales faut-il "
            "pour donner un etat des lieux fiable d'un module logiciel en "
            "cours de developpement, comme {module} pourrait l'etre ?"
        ),
        "certain_output": (
            "Au minimum : (1) l'arborescence reelle des fichiers du module "
            "(pas une supposition) ; (2) le dernier commit/changement qui "
            "l'a touche (`git log` cible) pour savoir si le travail est "
            "recent ou stale ; (3) l'etat des tests/verifications associes "
            "(passent-ils actuellement ?) ; (4) tout document de suivi "
            "existant (handoff, TODO, ADR) qui capture les decisions "
            "deja prises. Sans au moins le point (1), toute description de "
            "\"ce qui est fait\" est une supposition, pas un etat des "
            "lieux."
        ),
    },
    {
        "topic": "conclusion_definitive",
        "subjects": [
            ("le batch de 50 images", "identique au batch de 20"),
            ("le run d'upscale x2", "identique au run x1.5"),
            ("le test de denoise 0.15", "identique au test 0.10"),
            ("le sweep de steps 20/30/40", "les memes artefacts"),
            ("le comparatif ColorMatch LAB vs RGB", "des resultats proches"),
            ("le test SVI seed fixe vs seed variable", "des sorties similaires"),
            ("le benchmark CPU vs GPU du RAG", "des temps comparables"),
            ("le test de deux quantifications GGUF", "une qualite equivalente"),
            ("le comparatif AnimateDiff vs AniSora sur ce prompt", "des artefacts similaires"),
            ("le test de deux seeds SDXL", "des visages presque identiques"),
        ],
        "incertain_instruction": (
            "{test} donne {resultat} -- conclusion definitive a documenter ?"
        ),
        "incertain_output": (
            "Je ne peux pas ecrire une conclusion \"definitive\" sans voir "
            "les mesures reelles (valeurs exactes, nombre d'echantillons, "
            "conditions de test identiques ou non) -- affirmer une cause "
            "sans ces donnees serait une extrapolation presentee a tort "
            "comme un fait verifie. Peux-tu partager les chiffres/images "
            "concernes ? Sans eux, je peux seulement dire ce qu'il faudrait "
            "verifier avant de conclure : meme seed/cache/charge machine "
            "sur les runs compares, et un echantillon assez grand pour "
            "exclure le hasard."
        ),
        "certain_instruction": (
            "En general, quelles conditions faut-il reunir avant de "
            "conclure que deux resultats de test sont \"equivalents\" de "
            "facon fiable -- par exemple pour {test} ?"
        ),
        "certain_output": (
            "Conditions generales : (1) memes parametres d'entree hors la "
            "variable testee (meme seed si applicable, meme prompt, meme "
            "donnee source) ; (2) un echantillon assez grand pour ne pas "
            "confondre un resultat equivalent avec une coincidence sur un "
            "seul cas ; (3) une metrique de comparaison explicite (pas "
            "juste une impression visuelle) quand c'est possible ; (4) "
            "l'exclusion des causes triviales de similarite (ex. cache "
            "partage entre les deux runs, meme graine aleatoire par "
            "erreur). Sans ces garanties, \"resultats identiques\" peut "
            "aussi bien signifier \"le parametre teste n'a aucun effet\" "
            "que \"le test n'a pas reellement varie ce qu'on croit avoir "
            "varie\"."
        ),
    },
    {
        "topic": "memoire_session",
        "subjects": [
            ("le run QLoRA", "reel_v2"),
            ("le test SVI", "clip3"),
            ("le comparatif de checkpoints", "checkpoint-4400 vs checkpoint-4438"),
            ("l'evaluation qualitative", "V4"),
            ("le sweep de mode collapse", "run_x50"),
            ("la session de fine-tuning", "stage2_instructions_v2"),
            ("le test de fallback Aider", "devstral_test3"),
            ("le run d'entrainement HandSegNet", "epoch25"),
            ("le test de coherence temporelle", "miku_demo_3min_v2"),
            ("le benchmark GGUF", "Q4_K_M vs Q5_K_M"),
        ],
        "incertain_instruction": (
            "Tu te souviens de ce qu'a donne {item} ({label}) qu'on avait "
            "lance il y a quelques jours ?"
        ),
        "incertain_output": (
            "Je n'ai pas de memoire persistante entre sessions/conversations "
            "distinctes -- je ne peux pas confirmer le resultat de "
            "`{label}` sans qu'il soit fourni dans cet echange ou "
            "retrouvable dans un fichier reel (log, checkpoint, rapport). "
            "Inventer un chiffre ou une conclusion serait une "
            "confabulation. Si tu as garde le log ou le fichier de sortie "
            "correspondant, colle-le moi ou indique son chemin -- je peux "
            "le lire et l'interpreter directement."
        ),
        "certain_instruction": (
            "Quelle est la bonne pratique generale pour retrouver de "
            "facon fiable le resultat final d'un run passe (par exemple "
            "pour {item}), sans compter sur la memoire de la conversation ?"
        ),
        "certain_output": (
            "Bonnes pratiques generales : (1) journaliser chaque run dans "
            "un fichier structure persistant (CSV/JSON) avec date, "
            "parametres et resultat final des sa completion, pas seulement "
            "dans la sortie console ; (2) nommer les runs de facon unique "
            "et horodatee pour eviter qu'un nouveau run n'ecrase le suivi "
            "d'un ancien ; (3) sauvegarder les checkpoints/artefacts "
            "intermediaires (pas seulement le resultat final) pour pouvoir "
            "verifier apres coup ; (4) toujours lire le fichier de suivi "
            "reel avant d'affirmer un resultat, plutot que de se fier a un "
            "souvenir de conversation qui peut etre errone ou absent."
        ),
    },
    {
        "topic": "api_non_verifiee",
        "subjects": [
            ("ComfyUI", "SAMPreprocessor", "un parametre threshold"),
            ("diffusers", "StableDiffusionXLPipeline", "un argument denoising_end"),
            ("transformers", "AutoModel.from_pretrained", "un flag load_in_4bit"),
            ("peft", "get_peft_model", "un parametre target_modules en regex"),
            ("Ollama API", "/api/chat", "un champ keep_alive par requete"),
            ("KJNodes", "ColorMatch", "un mode de blending additionnel"),
            ("unsloth", "FastLanguageModel.from_pretrained", "un argument max_seq_length dynamique"),
            ("OpenCV", "cv2.inpaint", "un algorithme supplementaire au-dela de TELEA/NS"),
            ("numpy", "np.count_nonzero", "un parametre axis par defaut different de None"),
            ("gTTS", "gTTS()", "un parametre de vitesse de parole natif"),
        ],
        "incertain_instruction": (
            "Est-ce que la fonction `{fonction}` (bibliotheque {lib}) "
            "accepte bien {param} dans la version installee sur ce depot ?"
        ),
        "incertain_output": (
            "Je ne peux pas confirmer ca sans verifier la version reellement "
            "installee pour `{lib}` -- les signatures de fonctions changent "
            "entre versions, et affirmer qu'un parametre existe sans l'avoir "
            "verifie risquerait de te faire ecrire un appel qui plante. "
            "Verifie avec `pip show {lib}` puis `help({fonction})` ou "
            "`inspect.signature(...)` dans un interpreteur, ou consulte le "
            "changelog officiel de la version installee -- colle-moi le "
            "resultat et je peux confirmer si `{param}` est bien disponible."
        ),
        "certain_instruction": (
            "Comment verifier de facon fiable la signature d'une fonction "
            "Python installee localement (par exemple `{fonction}` dans "
            "`{lib}`), sans supposer sa version ?"
        ),
        "certain_output": (
            "```python\n"
            "import inspect\n"
            "import ma_lib\n\n"
            "print(inspect.signature(ma_lib.ma_fonction))\n"
            "```\n"
            "Alternatives : `help(ma_lib.ma_fonction)` en interactif, ou "
            "`pip show ma_lib` pour connaitre la version exacte installee "
            "puis consulter le changelog/documentation de cette version "
            "precise (pas la doc \"latest\" en ligne, qui peut correspondre "
            "a une version plus recente que celle reellement installee). "
            "C'est la seule facon fiable de confirmer qu'un parametre "
            "existe -- deviner a partir du nom de la fonction ou d'un "
            "souvenir d'une autre version est une source frequente de bugs. "
            "Pour `{lib}` specifiquement, la meme methode s'applique : rien "
            "ne remplace une verification directe sur la version installee."
        ),
    },
    {
        "topic": "limite_generative_vs_bug",
        "subjects": [
            ("les mains a six doigts", "sur un plan rapproche"),
            ("les pieds qui se chevauchent", "en position accroupie"),
            ("un halo colore de fond", "en generation AnimateDiff"),
            ("un flou sur les doigts", "en mouvement rapide"),
            ("un vignettage violet sur les bords", "apres 90 secondes de clip"),
            ("une texture de cheveux qui se dedouble", "sur un profil 3/4"),
            ("des chaussures qui changent de couleur", "entre deux clips"),
            ("un visage qui derive legerement", "sur un changement de plan"),
            ("des doigts fusionnes", "en tenant un objet"),
            ("une perte de nettete progressive", "sur une chaine de clips longue"),
        ],
        "incertain_instruction": (
            "Cette image/ce clip a un defaut : {defaut} {contexte} -- c'est "
            "un bug du pipeline a corriger, non ?"
        ),
        "incertain_output": (
            "Je ne peux pas trancher sans voir le resultat reel et sans "
            "verifier s'il correspond a une limite deja documentee -- ce "
            "projet distingue explicitement les limites generatives connues "
            "et acceptees (voir `LIMITATIONS_CONNUES.md`) des vrais bugs de "
            "pipeline actionnables, et confondre les deux fait perdre du "
            "temps a rouvrir une investigation non actionnable. Peux-tu "
            "partager l'image/le clip, et as-tu verifie `LIMITATIONS_CONNUES.md` "
            "pour ce symptome precis ? Si le cas n'y est pas deja catalogue, "
            "ca vaut le coup d'investiguer -- sinon, inutile de reproduire "
            "le meme diagnostic."
        ),
        "certain_instruction": (
            "Quelle est la difference generale entre une limite connue "
            "d'un modele generatif et un bug de pipeline actionnable -- "
            "par exemple pour {defaut} {contexte} ?"
        ),
        "certain_output": (
            "Une **limite generative connue** est un defaut qui vient du "
            "modele lui-meme (biais d'entrainement, difficulte structurelle "
            "d'une architecture donnee sur un type de contenu) -- elle se "
            "reproduit de facon coherente quel que soit le reglage du "
            "pipeline, et changer le code ne la corrige pas (seul un "
            "changement de modele, un LoRA cible, ou un post-traitement "
            "specifique peut l'attenuer). Un **bug de pipeline** est une "
            "erreur dans le code/la configuration qui produit un resultat "
            "incorrect alors que le modele sous-jacent est capable de "
            "produire le bon resultat dans d'autres conditions -- corriger "
            "le code resout le probleme. La distinction se verifie en "
            "pratique : si le meme defaut apparait avec des reglages/seeds "
            "differents et resiste aux corrections de code, c'est plus "
            "probablement une limite du modele qu'un bug."
        ),
    },
    {
        "topic": "ligne_bug_non_lue",
        "subjects": [
            ("un KeyError", "agents/context_bus.py", "142"),
            ("un IndexError", "footsegnet/quality_sort.py", "88"),
            ("un TypeError sur None", "agents/director.py", "310"),
            ("un ZeroDivisionError", "agents/dataset_diversity_stats.py", "57"),
            ("un FileNotFoundError", "workspace/qlora_dataset/scripts/train_stage2_commitpack.py", "204"),
            ("un AttributeError", "agents/production_video/batch_controlnet.py", "76"),
            ("un JSONDecodeError", "agents/config_manager.py", "121"),
            ("un RuntimeError CUDA", "handsegnet/train.py", "289"),
            ("un ImportError", "agents/infra/graph_ui.py", "43"),
            ("un ValueError de shape", "agents/segnet_premask.py", "63"),
        ],
        "incertain_instruction": (
            "Il y a {bug} dans `{file}`, a peu pres ligne {line} -- "
            "corrige-le."
        ),
        "incertain_output": (
            "Je ne veux pas corriger une ligne precise de `{file}` sans "
            "l'avoir lue -- \"a peu pres ligne {line}\" peut avoir change "
            "depuis, et un correctif ecrit a l'aveugle risque de cibler le "
            "mauvais code ou de manquer la vraie cause (souvent en amont de "
            "la ligne ou l'exception se declenche). Colle-moi le traceback "
            "complet et/ou le contenu du fichier autour de cette ligne, et "
            "je peux corriger precisement. Sur le principe general de ce "
            "type d'erreur, je peux deja expliquer la cause typique (voir "
            "ci-dessous)."
        ),
        "certain_instruction": (
            "Quelle est la cause generale d'{bug_general} en Python et "
            "comment le diagnostique-t-on, independamment d'un fichier "
            "precis ?"
        ),
        "certain_output": (
            "Diagnostiquer une exception Python de facon fiable suit "
            "toujours la meme methode generale : (1) lire le traceback "
            "complet, pas seulement la derniere ligne -- la ligne ou "
            "l'exception est levee n'est pas toujours la cause reelle, "
            "parfois une valeur invalide a ete produite plus haut dans "
            "l'appel ; (2) verifier l'hypothese implicite qui a ete violee "
            "(une cle censee exister, un index dans les bornes, une "
            "variable non None) a l'endroit precis ou elle est utilisee ; "
            "(3) reproduire le cas minimal qui declenche l'erreur avant de "
            "corriger, pour confirmer que le correctif regle bien le bon "
            "probleme plutot que de masquer le symptome (ex. un `try/except` "
            "large qui avale l'erreur sans la resoudre)."
        ),
    },
    {
        "topic": "recommandation_strategique",
        "subjects": [
            ("continuer le fine-tuning QLoRA local", "passer a une API cloud payante"),
            ("garder la RTX 5060 Ti pour Ollama", "migrer vers une instance cloud dediee"),
            ("continuer sur SDXL", "migrer vers un modele de diffusion plus recent"),
            ("garder le pipeline sequentiel actuel", "investir dans une parallelisation GPU"),
            ("continuer avec le dataset actuel", "generer un dataset synthetique plus grand"),
            ("garder AniSora", "tester un autre modele I2V"),
            ("continuer le RAG local", "investir dans une base vectorielle dediee"),
            ("garder Aider+qwen3-coder en secours", "adopter un autre outil de code local"),
            ("continuer sur un seul GPU par tache", "paralleliser systematiquement sur les deux GPU"),
            ("garder les checkpoints actuels", "relancer un entrainement complet"),
        ],
        "incertain_instruction": (
            "Entre {option_a} et {option_b}, quelle est la meilleure "
            "strategie ?"
        ),
        "incertain_output": (
            "Je ne peux pas trancher sans connaitre les contraintes reelles "
            "(budget/temps disponible, deadline, gain de qualite deja "
            "mesure entre les deux options, risque deja observe) -- donner "
            "un verdict avec une justification inventee serait trompeur. "
            "Peux-tu preciser la deadline, le budget (temps GPU/argent) "
            "disponible, et si tu as deja une mesure (pas juste un "
            "ressenti) comparant les deux options ? Avec ca je peux donner "
            "une recommandation concrete plutot qu'un avis generique."
        ),
        "certain_instruction": (
            "Quels criteres generaux faut-il reunir avant de trancher "
            "entre \"{option_a}\" et \"{option_b}\", independamment du "
            "contexte precis ?"
        ),
        "certain_output": (
            "Criteres generalement necessaires : (1) le gain mesure (pas "
            "suppose) de la nouvelle option sur un echantillon "
            "representatif du cas d'usage reel ; (2) le cout complet du "
            "changement (temps, argent, risque d'echec/regression) rapporte "
            "a ce gain ; (3) le temps disponible avant une deadline -- un "
            "gain qui arrive trop tard n'a pas de valeur ; (4) si l'option "
            "actuelle est deja suffisante pour l'objectif vise, au-dela "
            "duquel un gain supplementaire reste invisible en pratique ; "
            "(5) la reversibilite -- une option qu'on peut ajuster "
            "iterativement est moins risquee qu'un changement couteux et "
            "difficile a annuler."
        ),
    },
    {
        "topic": "compte_fichiers_non_verifie",
        "subjects": [
            ("handsegnet/dataset/premasks/", "masques valides"),
            ("footsegnet/controlnet/dataset/", "paires image/mask exploitables"),
            ("DEMO/frames/lineart_1024x1024/", "frames extraites"),
            ("workspace/qlora_dataset/", "exemples JSONL retenus apres filtrage"),
            ("bodysegnet/dataset/premasks/", "masques a corriger (route_manual_review)"),
            ("facesegnet/dataset/", "images annotees"),
            ("DEMO/frames/mixamo_depth/", "cartes de profondeur generees"),
            ("workspace/rag_index/", "chunks indexes"),
            ("E:\\data\\commitpack\\python\\", "shards JSONL non filtres"),
            ("footsegnet/dataset/premasks/", "images routees en revue manuelle"),
        ],
        "incertain_instruction": (
            "Combien de fichiers correspondant a « {item} » reste-t-il "
            "dans `{dossier}` apres le dernier filtrage ?"
        ),
        "incertain_output": (
            "Je ne peux pas donner un chiffre fiable sans recompter "
            "reellement le contenu de `{dossier}` -- un rapport ou une "
            "conversation anterieure peut etre perime (fichiers ajoutes/"
            "supprimes depuis), et annoncer un nombre suppose serait "
            "trompeur pour une decision qui en depend (ex. lancer un "
            "entrainement). La commande fiable : `ls {dossier} | wc -l` "
            "(ou l'equivalent PowerShell `(Get-ChildItem {dossier}).Count`) "
            "lancee maintenant. Peux-tu l'executer et me coller le "
            "resultat, ou me donner acces au dossier ?"
        ),
        "certain_instruction": (
            "Quelle est la bonne pratique generale pour verifier un compte "
            "de fichiers dans un dataset (ex. `{dossier}`) avant de s'y "
            "fier pour une decision (ex. lancer un entrainement) ?"
        ),
        "certain_output": (
            "Toujours recompter directement sur disque au moment de la "
            "decision (`ls | wc -l`, ou un script de comptage dedie), "
            "jamais se fier a un chiffre lu dans un rapport ou un message "
            "anterieur -- l'etat du disque a pu changer depuis (nouveaux "
            "fichiers ajoutes, filtrage relance, suppression manuelle). "
            "Si le compte doit etre croise avec un critere de qualite "
            "(ex. \"masques valides\" et pas juste \"fichiers presents\"), "
            "verifier aussi que le critere de comptage correspond bien a "
            "la definition voulue (un fichier present n'est pas forcement "
            "un masque valide/non vide)."
        ),
    },
]


def build_seed_records():
    records = []
    for seed in SEED_PROMPTS:
        records.append({
            "instruction": seed["incertain_instruction"],
            "input": "",
            "output": seed["incertain_output"],
            "meta": {
                "source": "rtuning_stage3_verdict_commitpack",
                "category": UNCERTAIN_PREFIX,
                "topic": seed["topic"],
                "seed_prompt_index": seed["index"],
            },
        })
        records.append({
            "instruction": seed["certain_instruction"],
            "input": "",
            "output": seed["certain_output"],
            "meta": {
                "source": "rtuning_stage3_verdict_commitpack",
                "category": CERTAIN_PREFIX,
                "topic": seed["topic"],
                "seed_prompt_index": seed["index"],
            },
        })
    return records


def build_category_records():
    records = []
    for cat in CATEGORIES:
        topic = cat["topic"]
        for subject in cat["subjects"]:
            if topic == "fichier_specifique":
                file_, feature = subject
                fmt = {"file": file_, "feature": feature}
            elif topic == "materiel_gpu":
                gpu, pct, task = subject
                fmt = {"gpu": gpu, "pct": pct, "task": task}
            elif topic == "arborescence_projet":
                module, slug = subject
                fmt = {"module": module, "slug": slug}
            elif topic == "conclusion_definitive":
                test, resultat = subject
                fmt = {"test": test, "resultat": resultat}
            elif topic == "memoire_session":
                item, label = subject
                fmt = {"item": item, "label": label}
            elif topic == "api_non_verifiee":
                lib, fonction, param = subject
                fmt = {"lib": lib, "fonction": fonction, "param": param}
            elif topic == "limite_generative_vs_bug":
                defaut, contexte = subject
                fmt = {"defaut": defaut, "contexte": contexte}
            elif topic == "ligne_bug_non_lue":
                bug, file_, line = subject
                fmt = {"bug": bug, "file": file_, "line": line,
                       "bug_general": bug}
            elif topic == "recommandation_strategique":
                option_a, option_b = subject
                fmt = {"option_a": option_a, "option_b": option_b}
            elif topic == "compte_fichiers_non_verifie":
                dossier, item = subject
                fmt = {"dossier": dossier, "item": item}
            else:
                raise ValueError(f"categorie inconnue: {topic}")

            incertain_instruction = cat["incertain_instruction"].format(**fmt)
            incertain_output = cat["incertain_output"].format(**fmt)
            certain_instruction = cat["certain_instruction"].format(**fmt)
            certain_output = cat["certain_output"].format(**fmt)

            records.append({
                "instruction": incertain_instruction,
                "input": "",
                "output": incertain_output,
                "meta": {
                    "source": "rtuning_stage3_verdict_commitpack",
                    "category": UNCERTAIN_PREFIX,
                    "topic": topic,
                    "seed_prompt_index": None,
                },
            })
            records.append({
                "instruction": certain_instruction,
                "input": "",
                "output": certain_output,
                "meta": {
                    "source": "rtuning_stage3_verdict_commitpack",
                    "category": CERTAIN_PREFIX,
                    "topic": topic,
                    "seed_prompt_index": None,
                },
            })
    return records


def main():
    records = build_seed_records() + build_category_records()

    n_certain = sum(1 for r in records if r["meta"]["category"] == CERTAIN_PREFIX)
    n_incertain = sum(1 for r in records if r["meta"]["category"] == UNCERTAIN_PREFIX)

    assert 200 <= len(records) <= 300, (
        f"cible 200-300 exemples, obtenu {len(records)} -- ajuster le "
        f"nombre de sujets par categorie"
    )
    assert n_certain == n_incertain, (
        f"desequilibre certain/incertain : {n_certain} vs {n_incertain}"
    )

    with open(OUT_PATH, "w", encoding="utf-8") as out:
        for r in records:
            out.write(json.dumps(r, ensure_ascii=False) + "\n")

    print(f"total={len(records)}")
    print(f"certain={n_certain}")
    print(f"incertain={n_incertain}")
    print(f"seeds={len(SEED_PROMPTS)} (x2 = {len(SEED_PROMPTS) * 2})")
    print(f"categories={len(CATEGORIES)}")
    print(f"ecrit -> {OUT_PATH}")


if __name__ == "__main__":
    main()

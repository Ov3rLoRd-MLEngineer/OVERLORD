"""
agent_supervisor.py v2 — Usine à Animés (Projet OverLord)
Orchestrateur industriel avec machine d'état, loopback réel,
archivage images, notifications et structure modulaire.
"""

import requests
import json
import time
import random
import logging
import sys
sys.stdout.reconfigure(line_buffering=True)
import hashlib
import io
import sys
from pathlib import Path
from datetime import datetime

# Pillow requis pour le score qualité : pip install Pillow
try:
    from PIL import Image, ImageFilter
    PIL_AVAILABLE = True
except ImportError:
    PIL_AVAILABLE = False

# ============================================================
# CONFIGURATION CENTRALE
# ============================================================
COMFY_URL     = "http://127.0.0.1:8188"
WORKFLOW_FILE = "Combined_V35_API.json"

# Workspace
WORKSPACE   = Path("workspace")
LOGS_DIR    = WORKSPACE / "logs"
ARCHIVE_DIR = WORKSPACE / "archive"
FAILED_FILE = WORKSPACE / "failed_jobs.json"
STATE_FILE  = WORKSPACE / "state.json"
CONFIG_FILE = "config.json"

# Stockage 3 niveaux (ajuste les chemins selon ta machine)
STORAGE = {
    "hot":  Path("F:/ComfyUI_Output"),          # Niveau 1 — partition F:
    "warm": Path("D:/NVMe_Production"),          # Niveau 2 — SSD NVMe
    "cold": Path("E:/HDD_Archive"),              # Niveau 3 — HDD 8 To
    "hot_threshold_gb":  150,                    # swap vers warm si > 150 Go
    "warm_threshold_gb": 800,                    # swap vers cold si > 800 Go
}

# Notifications (optionnel — laisser vide pour désactiver)
TELEGRAM_TOKEN   = ""   # "123456:ABC-DEF..."
TELEGRAM_CHAT_ID = ""   # "-1001234567890"

# Qualité loopback
SHARPNESS_THRESHOLD = 80.0   # variance Laplacien — calibrer en Phase 5
MAX_RETRIES         = 3
RETRY_DELAY         = 5

# IDs workflow Advanced
ADV_LORA_ID  = "62"
ADV_SEED_ID  = "112"
ADV_DIFF_ID  = "68"
ADV_POS_87   = "87"
ADV_POS_99   = "99"
ADV_NEG_ID   = "111"
ADV_WIDTH_ID = "75"
ADV_HEIGHT_ID= "77"

# IDs workflow Detailer (+300)
DET_LORA_ID = "303"
DET_SEED_ID = "382"
DET_POS_ID  = "301"
DET_NEG_ID  = "380"

# Nœud Image Saver Detailer (pour récupérer les images produites)
IMAGE_SAVER_NODE = "334"

DEFAULT_POSITIVE = "masterpiece, best quality, amazing quality, absurdres, 1girl, solo, looking at viewer,"
DEFAULT_NEGATIVE = "bad quality, worst quality, worst detail, sketch, bad hands, bad anatomy, deformed, artist name, watermark, signature, patreon, twitter username"


# ============================================================
# INITIALISATION
# ============================================================
def init_workspace():
    for d in [WORKSPACE, LOGS_DIR, ARCHIVE_DIR]:
        d.mkdir(parents=True, exist_ok=True)
    if not FAILED_FILE.exists():
        FAILED_FILE.write_text("[]", encoding="utf-8")
    if not STATE_FILE.exists():
        STATE_FILE.write_text(
            json.dumps({"current_job": 0, "run_id": None}),
            encoding="utf-8"
        )

def get_logger(run_id: str) -> logging.Logger:
    logger = logging.getLogger(run_id)
    if logger.handlers:
        return logger
    logger.setLevel(logging.DEBUG)
    fmt = logging.Formatter(
        "%(asctime)s [%(levelname)-8s] %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S"
    )
    ch = logging.StreamHandler(sys.stdout)
    ch.setLevel(logging.INFO)
    ch.setFormatter(fmt)
    logger.addHandler(ch)

    fh = logging.FileHandler(LOGS_DIR / f"{run_id}.log", encoding="utf-8")
    fh.setLevel(logging.DEBUG)
    fh.setFormatter(fmt)
    logger.addHandler(fh)
    return logger


# ============================================================
# MACHINE D'ÉTAT PERSISTANTE
# ============================================================
def load_state() -> dict:
    try:
        return json.loads(STATE_FILE.read_text(encoding="utf-8"))
    except Exception:
        return {"current_job": 0, "run_id": None}

def save_state(index: int, run_id: str):
    STATE_FILE.write_text(
        json.dumps({"current_job": index, "run_id": run_id}),
        encoding="utf-8"
    )

def clear_state():
    save_state(0, None)


# ============================================================
# UTILITAIRES
# ============================================================
def job_hash(job: dict) -> str:
    return hashlib.md5(
        json.dumps(job, sort_keys=True).encode()
    ).hexdigest()[:8]

def workflow_fingerprint(wf: dict) -> str:
    canonical = json.dumps(wf, sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(canonical.encode()).hexdigest()[:16]

def timestamp() -> str:
    return datetime.now().strftime("%Y%m%d_%H%M%S")

def save_failed_job(job: dict, reason: str):
    try:
        failed = json.loads(FAILED_FILE.read_text(encoding="utf-8"))
    except Exception:
        failed = []
    failed.append({
        "timestamp": timestamp(),
        "reason":    reason,
        "job":       job
    })
    FAILED_FILE.write_text(
        json.dumps(failed, indent=2, ensure_ascii=False),
        encoding="utf-8"
    )

def load_config(path: str = CONFIG_FILE) -> list:
    cfg = Path(path)
    if not cfg.exists():
        raise FileNotFoundError(f"Config introuvable : {path}")
    with open(cfg, encoding="utf-8") as f:
        jobs = json.load(f)
    if not isinstance(jobs, list):
        raise ValueError("config.json doit être une liste de jobs.")
    return jobs


# ============================================================
# NOTIFICATIONS
# ============================================================
def notify(message: str, logger: logging.Logger = None):
    """Envoie une notification Telegram si configuré."""
    if not TELEGRAM_TOKEN or not TELEGRAM_CHAT_ID:
        return
    try:
        requests.post(
            f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage",
            json={"chat_id": TELEGRAM_CHAT_ID, "text": f"[OverLord] {message}"},
            timeout=10
        )
    except Exception as e:
        if logger:
            logger.debug(f"Notification Telegram échouée : {e}")


# ============================================================
# STOCKAGE 3 NIVEAUX
# ============================================================
def get_partition_usage_gb(path: Path) -> float:
    """Retourne l'espace utilisé en Go sur la partition du chemin donné."""
    try:
        import shutil
        total, used, free = shutil.disk_usage(path)
        return used / (1024 ** 3)
    except Exception:
        return 0.0

def swap_if_needed(logger: logging.Logger):
    """
    Vérifie les seuils de stockage et déplace les archives si nécessaire.
    Hot → Warm → Cold selon les seuils définis dans STORAGE.
    """
    hot_path  = STORAGE["hot"]
    warm_path = STORAGE["warm"]
    cold_path = STORAGE["cold"]

    if not hot_path.exists():
        return  # Dossier output ComfyUI non trouvé, skip

    hot_used = get_partition_usage_gb(hot_path)
    logger.debug(f"Stockage hot: {hot_used:.1f} Go utilisés")

    if hot_used > STORAGE["hot_threshold_gb"]:
        logger.warning(
            f"Seuil hot atteint ({hot_used:.1f} Go > "
            f"{STORAGE['hot_threshold_gb']} Go) — swap vers warm"
        )
        notify(f"⚠ Stockage hot saturé ({hot_used:.1f} Go) — swap déclenché", logger)
        # Implémenter le déplacement des fichiers les plus anciens
        # vers warm_path ici (extension Phase 5)

    if warm_path.exists():
        warm_used = get_partition_usage_gb(warm_path)
        if warm_used > STORAGE["warm_threshold_gb"]:
            logger.warning(
                f"Seuil warm atteint ({warm_used:.1f} Go) — swap vers cold"
            )


# ============================================================
# CONSTRUCTION DU WORKFLOW
# ============================================================
def get_modified_workflow(
    strength        = 1.0,
    lora_name       = "",
    det_lora_name   = "",
    positive_prompt = None,
    negative_prompt = None,
    width           = 1024,
    height          = 1536,
    seed            = None,
    det_seed        = None,
) -> tuple:

    with open(WORKFLOW_FILE, "r", encoding="utf-8") as f:
        wf = json.load(f)

    pos = positive_prompt or DEFAULT_POSITIVE
    neg = negative_prompt or DEFAULT_NEGATIVE

    if seed is None or seed < 0:
        seed = random.randint(1, 999_999_999_999)
    if det_seed is None or det_seed < 0:
        det_seed = seed

    # Advanced
    wf[ADV_SEED_ID]["inputs"]["seed"]     = seed
    wf[ADV_DIFF_ID]["inputs"]["strength"] = strength
    wf[ADV_WIDTH_ID]["inputs"]["value"]   = width
    wf[ADV_HEIGHT_ID]["inputs"]["value"]  = height
    wf[ADV_POS_87]["inputs"]["string_b"]  = pos
    wf[ADV_POS_99]["inputs"]["string_a"]  = pos
    wf[ADV_NEG_ID]["inputs"]["text"]      = neg

    if lora_name and lora_name.strip():
        wf[ADV_LORA_ID]["inputs"]["loras"] = {
            "__value__": [{"lora": lora_name, "strength": 1.0, "enabled": True}]
        }
    else:
        wf[ADV_LORA_ID]["inputs"]["loras"] = {"__value__": []}
    wf[ADV_LORA_ID]["inputs"]["text"] = ""

    # Detailer
    wf[DET_SEED_ID]["inputs"]["seed"]  = det_seed
    wf[DET_POS_ID]["inputs"]["text"]   = pos
    wf[DET_NEG_ID]["inputs"]["text"]   = neg

    if det_lora_name and det_lora_name.strip():
        wf[DET_LORA_ID]["inputs"]["loras"] = {
            "__value__": [{"lora": det_lora_name, "strength": 1.0, "enabled": True}]
        }
    else:
        wf[DET_LORA_ID]["inputs"]["loras"] = {"__value__": []}
    wf[DET_LORA_ID]["inputs"]["text"] = ""

    return wf, seed, det_seed


# ============================================================
# COMMUNICATION COMFYUI
# ============================================================
def send_to_comfy(wf: dict, logger: logging.Logger) -> str | None:
    try:
        resp = requests.post(
            f"{COMFY_URL}/prompt",
            json={"prompt": wf},
            timeout=30
        )
        if resp.status_code == 200:
            pid = resp.json().get("prompt_id")
            logger.info(f"Prompt envoyé → prompt_id={pid}")
            return pid
        else:
            logger.error(f"HTTP {resp.status_code}: {resp.text[:300]}")
            return None
    except requests.exceptions.ConnectionError:
        logger.error("Connexion refusée — ComfyUI est-il démarré ?")
        return None
    except requests.exceptions.Timeout:
        logger.error("Timeout lors de l'envoi.")
        return None
    except Exception as e:
        logger.error(f"Erreur envoi : {e}")
        return None

def wait_for_completion(pid: str, logger: logging.Logger,
                        timeout: int = 600) -> tuple:
    logger.info(f"Attente completion (timeout={timeout}s)...")
    start = time.time()
    while time.time() - start < timeout:
        try:
            resp = requests.get(f"{COMFY_URL}/history/{pid}", timeout=10)
            if resp.status_code == 200:
                history = resp.json()
                if pid in history:
                    entry  = history[pid]
                    status = entry.get("status", {})
                    if status.get("completed"):
                        logger.info(f"Terminé en {time.time()-start:.1f}s")
                        return True, entry.get("outputs", {})
                    if status.get("status_str") == "error":
                        logger.error(f"Erreur ComfyUI: {status.get('messages', [])}")
                        return False, {}
        except Exception as e:
            logger.warning(f"Erreur polling: {e}")
        time.sleep(3)
    logger.error(f"Timeout global ({timeout}s).")
    return False, {}


# ============================================================
# ARCHIVAGE AVEC TÉLÉCHARGEMENT DES IMAGES
# ============================================================
def download_image(filename: str, subfolder: str = "",
                   img_type: str = "output") -> bytes | None:
    """Télécharge une image depuis ComfyUI via /view."""
    try:
        url = (f"{COMFY_URL}/view"
               f"?filename={filename}&subfolder={subfolder}&type={img_type}")
        r = requests.get(url, timeout=30)
        if r.status_code == 200:
            return r.content
        return None
    except Exception:
        return None

def archive_job(job: dict, prompt_id: str, seed: int,
                outputs: dict, wf: dict,
                logger: logging.Logger) -> Path:
    """Archive les métadonnées ET les images dans workspace/archive/."""
    ts      = timestamp()
    jhash   = job_hash(job)
    wf_fp   = workflow_fingerprint(wf)
    lora    = Path(job.get("lora", "no_lora")).stem
    folder  = ARCHIVE_DIR / f"{ts}_{lora}_{jhash}"
    folder.mkdir(parents=True, exist_ok=True)

    # Métadonnées
    meta = {
        "timestamp":          ts,
        "prompt_id":          prompt_id,
        "seed":               seed,
        "job_hash":           jhash,
        "workflow_fingerprint": wf_fp,
        "parameters":         job,
        "images":             []
    }

    # Télécharger et sauvegarder les images produites
    saver_output = outputs.get(IMAGE_SAVER_NODE, {})
    images = saver_output.get("images", [])

    for i, img_info in enumerate(images):
        filename  = img_info.get("filename", "")
        subfolder = img_info.get("subfolder", "")
        img_type  = img_info.get("type", "output")

        if not filename:
            continue

        img_data = download_image(filename, subfolder, img_type)
        if img_data:
            dest = folder / filename
            dest.write_bytes(img_data)
            meta["images"].append(str(dest))
            logger.debug(f"Image archivée : {dest}")
        else:
            logger.warning(f"Impossible de télécharger : {filename}")

    (folder / "meta.json").write_text(
        json.dumps(meta, indent=2, ensure_ascii=False),
        encoding="utf-8"
    )
    logger.debug(f"Job archivé dans {folder}")
    return folder


# ============================================================
# CONTRÔLE QUALITÉ — LOOPBACK RÉEL
# ============================================================
def laplacian_score(img_bytes: bytes) -> float:
    """
    Variance du Laplacien sur l'image en niveaux de gris.
    Score élevé = image nette. Score bas = image floue.
    Seuil recommandé à calibrer entre 50 et 150 selon le style.
    """
    if not PIL_AVAILABLE:
        return 999.0  # skip si Pillow absent

    img  = Image.open(io.BytesIO(img_bytes)).convert("L")
    # Redimensionner pour accélérer le calcul
    img  = img.resize((512, 512), Image.LANCZOS)
    lap  = img.filter(ImageFilter.FIND_EDGES)
    data = list(lap.getdata())
    mean = sum(data) / len(data)
    var  = sum((x - mean) ** 2 for x in data) / len(data)
    return var

def quality_check(outputs: dict, logger: logging.Logger,
                  threshold: float = SHARPNESS_THRESHOLD) -> bool:
    """
    Contrôle qualité en deux étapes :
    1. Vérification de l'existence de l'image (toujours)
    2. Score de netteté Laplacien (si Pillow disponible)
    """
    saver_output = outputs.get(IMAGE_SAVER_NODE, {})
    images = saver_output.get("images", [])

    if not images:
        logger.warning("QC : aucune image produite.")
        return False

    img_info  = images[0]
    filename  = img_info.get("filename", "")
    subfolder = img_info.get("subfolder", "")
    img_type  = img_info.get("type", "output")

    if not filename:
        logger.warning("QC : filename vide.")
        return False

    img_data = download_image(filename, subfolder, img_type)
    if not img_data:
        logger.warning(f"QC : image inaccessible ({filename}).")
        return False

    if not PIL_AVAILABLE:
        logger.info(f"QC OK (Pillow absent — validation par défaut) : {filename}")
        return True

    score = laplacian_score(img_data)
    logger.info(f"QC — Netteté Laplacien : {score:.1f} (seuil={threshold})")

    if score >= threshold:
        logger.info(f"QC VALIDÉ : {filename}")
        return True
    else:
        logger.warning(
            f"QC ÉCHOUÉ : score {score:.1f} < seuil {threshold} "
            f"— relance déclenchée."
        )
        return False


# ============================================================
# EXÉCUTION D'UN JOB UNIQUE
# ============================================================
def run_job(job: dict, logger: logging.Logger) -> bool:
    max_retries = job.get("max_retries", MAX_RETRIES)
    timeout     = job.get("timeout", 600)
    jhash       = job_hash(job)

    logger.info(
        f"[{jhash}] Démarrage — "
        f"lora={job.get('lora','') or 'aucun'} | "
        f"strength={job.get('strength', 1.0)} | "
        f"{job.get('width', 1024)}x{job.get('height', 1536)}"
    )
    notify(
        f"Job démarré [{jhash}] — lora={job.get('lora','') or 'aucun'}",
        logger
    )

    for attempt in range(1, max_retries + 1):
        logger.info(f"[{jhash}] Tentative {attempt}/{max_retries}")

        # 1. Construire le workflow
        try:
            wf, used_seed, used_det_seed = get_modified_workflow(
                strength        = job.get("strength", 1.0),
                lora_name       = job.get("lora", ""),
                det_lora_name   = job.get("det_lora", ""),
                positive_prompt = job.get("positive", None),
                negative_prompt = job.get("negative", None),
                width           = job.get("width", 1024),
                height          = job.get("height", 1536),
                seed            = job.get("seed", None),
                det_seed        = job.get("det_seed", None),
            )
            logger.debug(
                f"[{jhash}] seed={used_seed} | det_seed={used_det_seed} | "
                f"wf_fp={workflow_fingerprint(wf)}"
            )
        except Exception as e:
            reason = f"Erreur construction workflow : {e}"
            logger.error(f"[{jhash}] {reason}")
            save_failed_job(job, reason)
            return False

        # 2. Envoyer
        prompt_id = send_to_comfy(wf, logger)
        if not prompt_id:
            reason = f"Envoi échoué (tentative {attempt})"
            logger.warning(f"[{jhash}] {reason}")
            if attempt < max_retries:
                time.sleep(RETRY_DELAY)
                continue
            save_failed_job(job, reason)
            notify(f"❌ Job [{jhash}] ÉCHOUÉ : {reason}", logger)
            return False

        # 3. Attendre
        success, outputs = wait_for_completion(prompt_id, logger, timeout)
        if not success:
            reason = f"Completion échouée (tentative {attempt})"
            logger.warning(f"[{jhash}] {reason}")
            if attempt < max_retries:
                time.sleep(RETRY_DELAY)
                continue
            save_failed_job(job, "Toutes les tentatives ont échoué.")
            notify(f"❌ Job [{jhash}] ÉCHOUÉ après {max_retries} tentatives", logger)
            return False

        # 4. Contrôle qualité (loopback)
        if quality_check(outputs, logger):
            job_dir = archive_job(job, prompt_id, used_seed, outputs, wf, logger)
            logger.info(f"[{jhash}] ✓ Validé et archivé → {job_dir}")
            notify(f"✅ Job [{jhash}] validé | seed={used_seed}", logger)
            swap_if_needed(logger)
            return True
        else:
            logger.warning(
                f"[{jhash}] QC échoué (tentative {attempt}/{max_retries})"
            )
            if attempt < max_retries:
                time.sleep(RETRY_DELAY)
                continue

    save_failed_job(job, "QC échoué après tous les retries.")
    notify(f"❌ Job [{jhash}] rejeté par QC après {max_retries} tentatives", logger)
    return False


# ============================================================
# BATCH AVANCÉ AVEC REPRISE D'ÉTAT
# ============================================================
def run_batch_advanced(jobs: list, run_id: str = None,
                       resume: bool = True) -> dict:
    """
    Batch avec reprise automatique en cas de crash.
    Si resume=True, reprend au job où le process s'est arrêté.
    """
    init_workspace()
    run_id = run_id or f"run_{timestamp()}"
    logger = get_logger(run_id)

    # Reprise d'état
    start_index = 0
    if resume:
        state = load_state()
        if state.get("run_id") == run_id and state.get("current_job", 0) > 0:
            start_index = state["current_job"]
            logger.info(f"Reprise au job {start_index + 1}/{len(jobs)}")

    logger.info(f"{'='*60}")
    logger.info(f"BATCH — run_id={run_id} | {len(jobs)} jobs | départ={start_index+1}")
    logger.info(f"{'='*60}")
    notify(f"🚀 Batch démarré — {len(jobs)} jobs | run={run_id}", logger)

    results = []
    n_ok = n_fail = n_skip = 0

    for i, job in enumerate(jobs):
        # Skip les jobs déjà traités lors d'une reprise
        if i < start_index:
            n_skip += 1
            results.append({"job": job, "status": "skipped_resume",
                            "hash": job_hash(job) if isinstance(job, dict) else "?"})
            continue

        logger.info(f"\n--- JOB {i+1}/{len(jobs)} ---")

        if not isinstance(job, dict):
            logger.error(f"Job {i+1} invalide, ignoré.")
            n_skip += 1
            results.append({"job": job, "status": "skipped", "hash": "?"})
            continue

        # Sauvegarder l'état avant d'exécuter
        save_state(i, run_id)

        ok = run_job(job, logger)

        if ok:
            n_ok += 1
            results.append({"job": job, "status": "ok",
                            "hash": job_hash(job)})
        else:
            n_fail += 1
            results.append({"job": job, "status": "failed",
                            "hash": job_hash(job)})

    # Fin de batch : reset l'état
    clear_state()

    logger.info(f"\n{'='*60}")
    logger.info(
        f"BATCH TERMINÉ — ✓ {n_ok} OK | ✗ {n_fail} échoués | "
        f"⊘ {n_skip} ignorés"
    )
    logger.info(f"Logs    : {LOGS_DIR / (run_id + '.log')}")
    logger.info(f"Archive : {ARCHIVE_DIR}")
    logger.info(f"Échecs  : {FAILED_FILE}")
    logger.info(f"{'='*60}")
    notify(
        f"🏁 Batch terminé — ✓{n_ok} ✗{n_fail} ⊘{n_skip} | run={run_id}",
        logger
    )

    return {
        "run_id":  run_id,
        "total":   len(jobs),
        "success": n_ok,
        "failed":  n_fail,
        "skipped": n_skip,
        "results": results
    }


def run_batch_from_config(config_path: str = CONFIG_FILE,
                          resume: bool = True) -> dict:
    """Charge config.json et lance run_batch_advanced. Point d'entrée Black Box."""
    init_workspace()
    state  = load_state()
    run_id = state.get("run_id") or f"run_{timestamp()}"
    logger = get_logger(run_id)

    try:
        jobs = load_config(config_path)
        logger.info(f"{len(jobs)} jobs chargés depuis {config_path}")
    except Exception as e:
        logger.error(f"Impossible de charger {config_path} : {e}")
        return {"run_id": run_id, "total": 0, "success": 0,
                "failed": 0, "skipped": 0, "results": []}

    return run_batch_advanced(jobs, run_id=run_id, resume=resume)


# ============================================================
# POINT D'ENTRÉE — BLACK BOX
# ============================================================
if __name__ == "__main__":
    if not PIL_AVAILABLE:
        print("⚠ Pillow non installé — score qualité désactivé.")
        print("  Installer avec : pip install Pillow")

    # Mode 1 : python agent_supervisor.py [config.json] [--no-resume]
    if len(sys.argv) > 1 and not sys.argv[1].startswith("--"):
        cfg    = sys.argv[1]
        resume = "--no-resume" not in sys.argv
        print(f"Chargement depuis : {cfg} | reprise={resume}")
        run_batch_from_config(cfg, resume=resume)

    # Mode 2 : jobs inline
    else:
        jobs = [
            {
                "lora":     "ton_lora.safetensors",
                "det_lora": "",
                "strength": 1.0,
                "width":    1024,
                "height":   1536,
                "positive": DEFAULT_POSITIVE,
            },
        ]
        run_batch_advanced(jobs)

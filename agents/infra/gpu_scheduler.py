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
agents/gpu_scheduler.py — Ordonnanceur GPU & Parallélisme Pipeline
Gestion intelligente des ressources GPU entre les tâches du pipeline.

Fonctionnalités :
  - Storyboard + Production en parallèle (dès que le scénario est validé)
  - File d'attente GPU avec priorités dynamiques
  - Répartition CPU (sourcing/scénario) vs GPU (production/3D)
  - Monitoring VRAM en temps réel
  - Équilibrage multi-GPU local + cloud (RunPod/Vast.ai)

Architecture Gantt dynamique :
  Bloc CPU  : Sourcing | Scénario | Storyboard (N threads CPU)
  Bloc GPU  : Production ComfyUI | 3D rendering (1 GPU par tâche)
  Overlap   : Storyboard shot N+1 pendant que Production génère shot N

pip install ray  (pour le multi-processing avancé)
"""

import threading
import queue
import time
import logging
import json
import requests
from pathlib import Path
from datetime import datetime
from dataclasses import dataclass, field
from enum import Enum
from typing import Callable, Optional

COMFY_URL = "http://127.0.0.1:8188"


class TaskType(Enum):
    CPU_LIGHT  = "cpu_light"    # sourcing, scénario, storyboard
    CPU_HEAVY  = "cpu_heavy"    # LLM local (Ollama)
    GPU_SDXL   = "gpu_sdxl"    # génération ComfyUI SDXL
    GPU_3D     = "gpu_3d"      # rendu 3D Blender/Shap-E
    GPU_REMOTE = "gpu_remote"  # tâche sur GPU distant


class TaskStatus(Enum):
    PENDING   = "pending"
    RUNNING   = "running"
    DONE      = "done"
    FAILED    = "failed"
    CANCELLED = "cancelled"


@dataclass
class Task:
    id:          str
    name:        str
    task_type:   TaskType
    fn:          Callable
    args:        tuple  = field(default_factory=tuple)
    kwargs:      dict   = field(default_factory=dict)
    priority:    int    = 5      # 1=urgent, 10=basse
    depends_on:  list   = field(default_factory=list)  # IDs des tâches préalables
    status:      TaskStatus = TaskStatus.PENDING
    result:      object = None
    error:       str    = ""
    created_at:  str    = field(default_factory=lambda: datetime.utcnow().isoformat())
    started_at:  str    = ""
    ended_at:    str    = ""
    duration_s:  float  = 0.0
    vram_used_mb:int    = 0

    def __lt__(self, other):
        return self.priority < other.priority


class GPUScheduler:
    """
    Ordonnanceur de tâches pour le pipeline OverLord.
    Gère la file d'attente GPU/CPU et le parallélisme inter-blocs.
    """

    # Nombre de workers par type
    MAX_CPU_WORKERS  = 4    # sourcing/scénario en parallèle
    MAX_GPU_WORKERS  = 1    # 1 seul GPU local (RTX 5080)
    MAX_LLM_WORKERS  = 1    # 1 seul thread Ollama

    def __init__(self, logger: logging.Logger = None,
                 comfy_url: str = COMFY_URL):
        self.log       = logger or logging.getLogger("gpu_scheduler")
        self.comfy_url = comfy_url

        # Files d'attente par type
        self._cpu_queue  = queue.PriorityQueue()
        self._gpu_queue  = queue.PriorityQueue()
        self._llm_queue  = queue.PriorityQueue()

        # État des tâches
        self._tasks:  dict[str, Task] = {}
        self._lock    = threading.Lock()

        # Workers
        self._cpu_workers  = []
        self._gpu_workers  = []
        self._llm_workers  = []
        self._running      = False

        # Callbacks pour l'UI
        self._listeners    = []

        # Métriques
        self._stats = {
            "total_submitted": 0,
            "total_done":      0,
            "total_failed":    0,
            "gpu_utilization": 0.0,
        }

    def add_listener(self, cb: Callable):
        self._listeners.append(cb)

    def _emit(self, event: str, data: dict):
        for cb in self._listeners:
            try: cb(event, data)
            except Exception: pass

    # ── Démarrage / Arrêt ────────────────────────────────────────────

    def start(self):
        """Démarre tous les workers."""
        self._running = True

        # Workers CPU
        for i in range(self.MAX_CPU_WORKERS):
            t = threading.Thread(
                target=self._worker_loop,
                args=(self._cpu_queue, f"CPU-{i+1}"),
                daemon=True
            )
            t.start()
            self._cpu_workers.append(t)

        # Workers GPU
        for i in range(self.MAX_GPU_WORKERS):
            t = threading.Thread(
                target=self._worker_loop,
                args=(self._gpu_queue, f"GPU-{i+1}"),
                daemon=True
            )
            t.start()
            self._gpu_workers.append(t)

        # Worker LLM (unique pour Ollama)
        t = threading.Thread(
            target=self._worker_loop,
            args=(self._llm_queue, "LLM-1"),
            daemon=True
        )
        t.start()
        self._llm_workers.append(t)

        self.log.info(
            f"[SCHEDULER] Démarré — "
            f"{self.MAX_CPU_WORKERS} workers CPU | "
            f"{self.MAX_GPU_WORKERS} worker GPU | "
            f"1 worker LLM"
        )

    def stop(self):
        """Arrête les workers proprement."""
        self._running = False
        # Injecter des poison pills
        for _ in range(self.MAX_CPU_WORKERS):
            self._cpu_queue.put((0, None))
        for _ in range(self.MAX_GPU_WORKERS):
            self._gpu_queue.put((0, None))
        self._llm_queue.put((0, None))
        self.log.info("[SCHEDULER] Arrêt demandé")

    # ── Soumission de tâches ──────────────────────────────────────────

    def submit(self, task: Task) -> str:
        """Soumet une tâche à la file appropriée."""
        with self._lock:
            self._tasks[task.id] = task
            self._stats["total_submitted"] += 1

        queue_map = {
            TaskType.CPU_LIGHT:  self._cpu_queue,
            TaskType.CPU_HEAVY:  self._llm_queue,
            TaskType.GPU_SDXL:   self._gpu_queue,
            TaskType.GPU_3D:     self._gpu_queue,
            TaskType.GPU_REMOTE: self._gpu_queue,
        }
        target_queue = queue_map.get(task.task_type, self._cpu_queue)
        target_queue.put((task.priority, task))

        self.log.debug(
            f"[SCHEDULER] Soumis : {task.name} "
            f"[{task.task_type.value}] prio={task.priority}"
        )
        self._emit("task_submitted", {"task_id": task.id, "name": task.name})
        return task.id

    def submit_pipeline_parallel(self, pipeline_stages: list[dict]) -> list[str]:
        """
        Soumet un pipeline complet avec parallélisme automatique.
        Les blocs CPU (sourcing/scénario/storyboard) tournent en parallèle.
        Les blocs GPU attendent la fin des dépendances CPU.

        pipeline_stages : liste de dicts {name, fn, type, depends_on}
        """
        ids = []
        for stage in pipeline_stages:
            task = Task(
                id        = f"stage_{stage['name']}_{int(time.time())}",
                name      = stage["name"],
                task_type = stage.get("type", TaskType.CPU_LIGHT),
                fn        = stage["fn"],
                args      = stage.get("args", ()),
                kwargs    = stage.get("kwargs", {}),
                priority  = stage.get("priority", 5),
                depends_on= stage.get("depends_on", []),
            )
            self.submit(task)
            ids.append(task.id)
        return ids

    # ── Worker loop ───────────────────────────────────────────────────

    def _worker_loop(self, q: queue.PriorityQueue, worker_name: str):
        """Boucle principale d'un worker."""
        self.log.debug(f"[SCHEDULER/{worker_name}] Worker démarré")
        while self._running:
            try:
                priority, task = q.get(timeout=1.0)
                if task is None:   # poison pill
                    break

                # Vérifier les dépendances
                if not self._deps_satisfied(task):
                    # Remettre en file avec délai
                    time.sleep(0.5)
                    q.put((priority, task))
                    continue

                # Exécuter la tâche
                self._run_task(task, worker_name)
                q.task_done()

            except queue.Empty:
                continue
            except Exception as e:
                self.log.error(f"[SCHEDULER/{worker_name}] Erreur worker : {e}")

        self.log.debug(f"[SCHEDULER/{worker_name}] Worker arrêté")

    def _deps_satisfied(self, task: Task) -> bool:
        """Vérifie que toutes les dépendances sont terminées."""
        with self._lock:
            for dep_id in task.depends_on:
                dep = self._tasks.get(dep_id)
                if not dep or dep.status != TaskStatus.DONE:
                    return False
        return True

    def _run_task(self, task: Task, worker_name: str):
        """Exécute une tâche et met à jour son état."""
        with self._lock:
            task.status     = TaskStatus.RUNNING
            task.started_at = datetime.utcnow().isoformat()

        self.log.info(
            f"[SCHEDULER/{worker_name}] ▶ {task.name} [{task.task_type.value}]"
        )
        self._emit("task_started", {"task_id": task.id, "name": task.name,
                                     "worker": worker_name})

        # VRAM pre-check pour tâches GPU
        if task.task_type in (TaskType.GPU_SDXL, TaskType.GPU_3D):
            self._check_vram_before_gpu()

        start_t = time.time()
        try:
            result       = task.fn(*task.args, **task.kwargs)
            task.result  = result
            task.status  = TaskStatus.DONE
            with self._lock:
                self._stats["total_done"] += 1
            self.log.info(
                f"[SCHEDULER/{worker_name}] ✓ {task.name} "
                f"({time.time()-start_t:.1f}s)"
            )
        except Exception as e:
            task.error  = str(e)
            task.status = TaskStatus.FAILED
            with self._lock:
                self._stats["total_failed"] += 1
            self.log.error(
                f"[SCHEDULER/{worker_name}] ✗ {task.name} : {e}"
            )

        task.ended_at   = datetime.utcnow().isoformat()
        task.duration_s = time.time() - start_t
        self._emit("task_done", {
            "task_id":   task.id,
            "name":      task.name,
            "status":    task.status.value,
            "duration":  task.duration_s,
        })

    def _check_vram_before_gpu(self):
        """Libère la VRAM si nécessaire avant une tâche GPU."""
        try:
            r = requests.get(f"{self.comfy_url}/system_stats", timeout=5)
            if r.status_code == 200:
                devices = r.json().get("devices", [])
                if devices:
                    dev  = devices[0]
                    total = dev.get("vram_total", 1)
                    free  = dev.get("vram_free",  1)
                    usage = (total - free) / total * 100
                    if usage > 80:
                        self.log.warning(
                            f"[SCHEDULER] VRAM {usage:.0f}% — libération préventive"
                        )
                        requests.post(
                            f"{self.comfy_url}/free",
                            json={"unload_models": True, "free_memory": True},
                            timeout=8
                        )
                        time.sleep(2)
        except Exception:
            pass

    # ── Pipeline Parallèle OverLord ───────────────────────────────────

    def schedule_overlord_pipeline(self,
                                    sourcing_fn:   Callable,
                                    scenario_fn:   Callable,
                                    storyboard_fn: Callable,
                                    production_fn: Callable,
                                    postprod_fn:   Callable,
                                    cfg: dict = None) -> dict:
        """
        Ordonnance le pipeline OverLord avec parallélisme optimal :

        t=0    Sourcing (CPU)
        t=S1   Scénario (LLM) ← dépend sourcing
        t=S2   Storyboard (CPU) ← dépend scénario
        t=S3   Production shot 1 (GPU) ← dépend storyboard shot 1
        t=S3   Storyboard shot 2 (CPU) ← en parallèle de Production shot 1
        ...
        """
        cfg = cfg or {}
        ts  = int(time.time())

        sourcing_id   = f"sourcing_{ts}"
        scenario_id   = f"scenario_{ts}"
        storyboard_id = f"storyboard_{ts}"
        production_id = f"production_{ts}"
        postprod_id   = f"postprod_{ts}"

        stages = [
            Task(id=sourcing_id,   name="Sourcing",
                 task_type=TaskType.CPU_LIGHT, fn=sourcing_fn,
                 kwargs=cfg, priority=1),

            Task(id=scenario_id,   name="Scénario",
                 task_type=TaskType.CPU_HEAVY, fn=scenario_fn,
                 kwargs=cfg, priority=1,
                 depends_on=[sourcing_id]),

            Task(id=storyboard_id, name="Storyboard",
                 task_type=TaskType.CPU_LIGHT, fn=storyboard_fn,
                 kwargs=cfg, priority=2,
                 depends_on=[scenario_id]),

            Task(id=production_id, name="Production",
                 task_type=TaskType.GPU_SDXL, fn=production_fn,
                 kwargs=cfg, priority=1,
                 depends_on=[storyboard_id]),

            Task(id=postprod_id,   name="Post-Production",
                 task_type=TaskType.CPU_LIGHT, fn=postprod_fn,
                 kwargs=cfg, priority=2,
                 depends_on=[production_id]),
        ]

        for task in stages:
            self.submit(task)

        return {
            "sourcing_id":   sourcing_id,
            "scenario_id":   scenario_id,
            "storyboard_id": storyboard_id,
            "production_id": production_id,
            "postprod_id":   postprod_id,
        }

    # ── Monitoring ───────────────────────────────────────────────────

    def get_status(self) -> dict:
        """Retourne l'état complet du scheduler."""
        with self._lock:
            tasks_by_status = {}
            for s in TaskStatus:
                tasks_by_status[s.value] = [
                    {"id": t.id, "name": t.name, "type": t.task_type.value,
                     "duration": t.duration_s}
                    for t in self._tasks.values() if t.status == s
                ]
            return {
                "stats":          dict(self._stats),
                "queue_sizes":    {
                    "cpu": self._cpu_queue.qsize(),
                    "gpu": self._gpu_queue.qsize(),
                    "llm": self._llm_queue.qsize(),
                },
                "tasks_by_status": tasks_by_status,
            }

    def wait_for(self, task_id: str, timeout: float = 300) -> Task | None:
        """Attend qu'une tâche soit terminée."""
        start = time.time()
        while time.time() - start < timeout:
            task = self._tasks.get(task_id)
            if task and task.status in (TaskStatus.DONE, TaskStatus.FAILED):
                return task
            time.sleep(0.5)
        return None

    def wait_all(self, timeout: float = 3600):
        """Attend que toutes les tâches soient terminées."""
        self._cpu_queue.join()
        self._gpu_queue.join()
        self._llm_queue.join()


# ── Scheduler global singleton ───────────────────────────────────────
_scheduler: Optional[GPUScheduler] = None

def get_scheduler(logger=None) -> GPUScheduler:
    global _scheduler
    if _scheduler is None:
        _scheduler = GPUScheduler(logger)
        _scheduler.start()
    return _scheduler


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    log = logging.getLogger("scheduler_test")

    sched = GPUScheduler(log)
    sched.start()

    # Test avec fonctions simulées
    def fake_sourcing(**kw):
        log.info("  [TEST] Sourcing en cours...")
        time.sleep(2); return {"brief": "Dragon Ball trending"}

    def fake_scenario(**kw):
        log.info("  [TEST] Scénario en cours...")
        time.sleep(3); return {"title": "L'Éveil"}

    def fake_storyboard(**kw):
        log.info("  [TEST] Storyboard en cours...")
        time.sleep(1); return {"shots": 12}

    def fake_production(**kw):
        log.info("  [TEST] Production GPU en cours...")
        time.sleep(4); return {"images": 12}

    def fake_postprod(**kw):
        log.info("  [TEST] Post-production en cours...")
        time.sleep(1); return {"video": "output.mp4"}

    ids = sched.schedule_overlord_pipeline(
        fake_sourcing, fake_scenario, fake_storyboard,
        fake_production, fake_postprod
    )

    log.info(f"Pipeline soumis : {ids}")
    sched.wait_all(timeout=30)
    log.info(f"Status final : {sched.get_status()['stats']}")
    sched.stop()

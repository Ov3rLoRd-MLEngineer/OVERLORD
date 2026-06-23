"""
agents/remote_gpu.py — Agent GPU Distant & Rendu Distribué
Connexion aux GPUs distants (RunPod, Vast.ai, Lambda Labs)
et gestion du cluster de rendu multi-machines.

Modes :
  1. GPU Local seul (RTX 5080)
  2. GPU Local + Cloud (overflow vers RunPod quand VRAM saturée)
  3. Cluster local (plusieurs machines sur le même réseau)
  4. Cluster full-cloud (armée de GPUs RunPod/Vast.ai)

pip install runpod vastai paramiko ray
"""

import json
import logging
import subprocess
import threading
import time
import requests
from pathlib import Path
from enum import Enum
from dataclasses import dataclass, field
from typing import Optional

COMFY_PORT    = 8188
REMOTE_CONFIG = Path("workspace/remote_gpu_config.json")


class GPUProvider(Enum):
    LOCAL    = "local"
    RUNPOD   = "runpod"
    VAST_AI  = "vast_ai"
    LAMBDA   = "lambda_labs"
    SSH      = "ssh_machine"    # machine locale sur le réseau
    RAY      = "ray_cluster"    # cluster Ray


@dataclass
class GPUNode:
    """Représente un nœud GPU (local ou distant)."""
    id:          str
    provider:    GPUProvider
    name:        str
    host:        str            # IP ou hostname
    port:        int    = COMFY_PORT
    ssh_user:    str    = ""
    ssh_key:     str    = ""
    api_key:     str    = ""
    vram_gb:     float  = 16.0
    status:      str    = "unknown"  # online/offline/busy
    current_job: str    = ""
    jobs_done:   int    = 0
    priority:    int    = 1    # 1=local prioritaire, 2=cloud


class RemoteGPUAgent:
    """
    Gestionnaire de GPUs locaux et distants.
    Dispatche les jobs vers les nœuds disponibles.
    """

    def __init__(self, logger: logging.Logger = None):
        self.log   = logger or logging.getLogger("remote_gpu")
        self._nodes: dict[str, GPUNode] = {}
        self._lock  = threading.Lock()
        self._load_config()

        # Toujours ajouter le nœud local
        if "local" not in self._nodes:
            self._nodes["local"] = GPUNode(
                id="local", provider=GPUProvider.LOCAL,
                name="RTX 5080 Local", host="127.0.0.1",
                port=COMFY_PORT, vram_gb=16.0, priority=1,
            )

    def _load_config(self):
        if REMOTE_CONFIG.exists():
            try:
                data = json.loads(REMOTE_CONFIG.read_text(encoding="utf-8"))
                for node_data in data.get("nodes", []):
                    node = GPUNode(**node_data)
                    node.provider = GPUProvider(node_data.get("provider","local"))
                    self._nodes[node.id] = node
            except Exception as e:
                self.log.warning(f"[REMOTE] Config chargement : {e}")

    def _save_config(self):
        REMOTE_CONFIG.parent.mkdir(parents=True, exist_ok=True)
        data = {"nodes": [
            {k: (v.value if isinstance(v, Enum) else v)
             for k, v in node.__dict__.items()}
            for node in self._nodes.values()
        ]}
        REMOTE_CONFIG.write_text(json.dumps(data, indent=2), encoding="utf-8")

    # ── Gestion des nœuds ────────────────────────────────────────────

    def add_ssh_node(self, host: str, user: str, key_path: str,
                      name: str = None, vram_gb: float = 8.0) -> str:
        """Ajoute une machine locale accessible en SSH."""
        node_id = f"ssh_{host.replace('.','_')}"
        self._nodes[node_id] = GPUNode(
            id=node_id, provider=GPUProvider.SSH,
            name=name or f"SSH {host}", host=host,
            ssh_user=user, ssh_key=key_path,
            vram_gb=vram_gb, priority=2,
        )
        self._save_config()
        self.log.info(f"[REMOTE] Nœud SSH ajouté : {name or host}")
        return node_id

    def add_runpod_node(self, api_key: str, pod_id: str,
                         host: str, vram_gb: float = 24.0) -> str:
        """Ajoute un pod RunPod (GPU cloud)."""
        node_id = f"runpod_{pod_id[:8]}"
        self._nodes[node_id] = GPUNode(
            id=node_id, provider=GPUProvider.RUNPOD,
            name=f"RunPod {pod_id[:8]}", host=host,
            api_key=api_key, vram_gb=vram_gb, priority=3,
        )
        self._save_config()
        self.log.info(f"[REMOTE] Nœud RunPod ajouté : {host}")
        return node_id

    def add_vast_node(self, api_key: str, instance_id: str,
                       host: str, vram_gb: float = 24.0) -> str:
        """Ajoute une instance Vast.ai."""
        node_id = f"vast_{instance_id[:8]}"
        self._nodes[node_id] = GPUNode(
            id=node_id, provider=GPUProvider.VAST_AI,
            name=f"Vast.ai {instance_id[:8]}", host=host,
            api_key=api_key, vram_gb=vram_gb, priority=3,
        )
        self._save_config()
        self.log.info(f"[REMOTE] Nœud Vast.ai ajouté : {host}")
        return node_id

    # ── Ping & Disponibilité ─────────────────────────────────────────

    def ping_node(self, node: GPUNode) -> bool:
        """Vérifie qu'un nœud ComfyUI est accessible."""
        url = f"http://{node.host}:{node.port}/system_stats"
        try:
            r = requests.get(url, timeout=5)
            if r.status_code == 200:
                node.status = "online"
                return True
        except Exception:
            pass
        node.status = "offline"
        return False

    def ping_all(self) -> dict:
        """Ping tous les nœuds en parallèle."""
        results = {}
        threads = []
        def _ping(node):
            results[node.id] = self.ping_node(node)
        for node in self._nodes.values():
            t = threading.Thread(target=_ping, args=(node,), daemon=True)
            t.start(); threads.append(t)
        for t in threads:
            t.join(timeout=8)
        online = sum(1 for v in results.values() if v)
        self.log.info(f"[REMOTE] Ping : {online}/{len(results)} nœuds en ligne")
        return results

    def get_available_node(self,
                            min_vram_gb: float = 8.0,
                            prefer_local: bool = True) -> Optional[GPUNode]:
        """Retourne le meilleur nœud disponible."""
        candidates = [
            n for n in sorted(self._nodes.values(), key=lambda x: x.priority)
            if n.status == "online"
            and n.current_job == ""
            and n.vram_gb >= min_vram_gb
        ]
        if not candidates:
            # Relancer les pings
            self.ping_all()
            candidates = [
                n for n in sorted(self._nodes.values(), key=lambda x: x.priority)
                if n.status == "online" and n.current_job == ""
                and n.vram_gb >= min_vram_gb
            ]
        return candidates[0] if candidates else None

    # ── Dispatch de jobs ComfyUI ─────────────────────────────────────

    def submit_workflow(self, workflow: dict,
                         node: GPUNode = None,
                         min_vram_gb: float = 8.0) -> dict:
        """
        Envoie un workflow ComfyUI vers le meilleur nœud disponible.
        Si pas de nœud local disponible, dispatch vers le cloud.
        """
        if node is None:
            node = self.get_available_node(min_vram_gb)
            if node is None:
                self.log.error("[REMOTE] Aucun nœud GPU disponible")
                return {"error": "no_gpu_available"}

        url    = f"http://{node.host}:{node.port}/prompt"
        with self._lock:
            node.current_job = f"job_{int(time.time())}"

        self.log.info(
            f"[REMOTE] Envoi workflow → {node.name} "
            f"({node.host}:{node.port})"
        )

        try:
            r = requests.post(url, json={"prompt": workflow}, timeout=30)
            if r.status_code == 200:
                pid = r.json().get("prompt_id","?")
                self.log.info(f"[REMOTE] ✓ Job {pid} sur {node.name}")
                return {"node_id": node.id, "prompt_id": pid,
                         "node_name": node.name}
            else:
                with self._lock:
                    node.current_job = ""
                return {"error": f"HTTP {r.status_code}"}
        except Exception as e:
            with self._lock:
                node.current_job = ""
            self.log.error(f"[REMOTE] Erreur envoi : {e}")
            return {"error": str(e)}

    def poll_job(self, node_id: str, prompt_id: str,
                  timeout_s: float = 600) -> dict:
        """Attend la fin d'un job ComfyUI sur un nœud."""
        node = self._nodes.get(node_id)
        if not node:
            return {"done": False, "error": "node_not_found"}

        url_history = f"http://{node.host}:{node.port}/history/{prompt_id}"
        start = time.time()

        while time.time() - start < timeout_s:
            try:
                r = requests.get(url_history, timeout=8)
                if r.status_code == 200:
                    hist = r.json()
                    if prompt_id in hist:
                        status = hist[prompt_id].get("status", {})
                        if status.get("completed"):
                            with self._lock:
                                node.current_job = ""
                                node.jobs_done  += 1
                            outputs = hist[prompt_id].get("outputs", {})
                            return {"done": True, "outputs": outputs,
                                     "node": node.name}
                        if status.get("status_str") == "error":
                            with self._lock:
                                node.current_job = ""
                            return {"done": False, "error": "comfyui_error"}
            except Exception:
                pass
            time.sleep(3)

        with self._lock:
            node.current_job = ""
        return {"done": False, "error": "timeout"}

    def submit_and_wait(self, workflow: dict,
                         min_vram_gb: float = 8.0,
                         timeout_s: float = 600) -> dict:
        """Submit + poll en une seule méthode (bloquant)."""
        result = self.submit_workflow(workflow, min_vram_gb=min_vram_gb)
        if "error" in result:
            return result
        return self.poll_job(result["node_id"], result["prompt_id"], timeout_s)

    # ── Cluster SSH ───────────────────────────────────────────────────

    def start_comfyui_on_node(self, node: GPUNode,
                               comfy_path: str) -> bool:
        """Lance ComfyUI sur une machine distante via SSH."""
        if node.provider != GPUProvider.SSH:
            return False
        cmd = (
            f"ssh -i {node.ssh_key} {node.ssh_user}@{node.host} "
            f"'cd {comfy_path} && "
            f"nohup python main.py --port {node.port} "
            f"--disable-auto-launch > comfyui.log 2>&1 &'"
        )
        try:
            result = subprocess.run(cmd, shell=True, capture_output=True,
                                     text=True, timeout=30)
            if result.returncode == 0:
                time.sleep(5)  # laisser démarrer
                return self.ping_node(node)
        except Exception as e:
            self.log.error(f"[REMOTE/SSH] Démarrage {node.name} : {e}")
        return False

    # ── RunPod API ────────────────────────────────────────────────────

    def create_runpod_instance(self, api_key: str,
                                gpu_type: str = "NVIDIA RTX 4090",
                                image:     str = "ashleykza/comfyui:latest"
                                ) -> dict:
        """
        Crée une instance RunPod avec ComfyUI préinstallé.
        Retourne l'ID et l'IP du pod.
        """
        try:
            import runpod
            runpod.api_key = api_key
            pod = runpod.create_pod(
                name        = "overlord-comfyui",
                image_name  = image,
                gpu_type_id = gpu_type,
                cloud_type  = "SECURE",
                ports       = f"{COMFY_PORT}/http",
            )
            pod_id = pod.get("id","")
            self.log.info(f"[REMOTE/RunPod] Pod créé : {pod_id}")
            return pod
        except ImportError:
            self.log.error("[REMOTE/RunPod] pip install runpod")
            return {}
        except Exception as e:
            self.log.error(f"[REMOTE/RunPod] Erreur création : {e}")
            return {}

    def terminate_runpod_instance(self, api_key: str, pod_id: str):
        """Termine un pod RunPod (stop facturation)."""
        try:
            import runpod
            runpod.api_key = api_key
            runpod.terminate_pod(pod_id)
            self.log.info(f"[REMOTE/RunPod] Pod {pod_id} terminé ✓")
        except Exception as e:
            self.log.error(f"[REMOTE/RunPod] Erreur terminaison : {e}")

    # ── État global ───────────────────────────────────────────────────

    def get_fleet_status(self) -> dict:
        """Retourne l'état complet de la flotte GPU."""
        return {
            "total_nodes":  len(self._nodes),
            "online":       sum(1 for n in self._nodes.values() if n.status=="online"),
            "busy":         sum(1 for n in self._nodes.values() if n.current_job),
            "total_vram":   sum(n.vram_gb for n in self._nodes.values()),
            "total_jobs":   sum(n.jobs_done for n in self._nodes.values()),
            "nodes": [
                {
                    "id":       n.id,
                    "name":     n.name,
                    "provider": n.provider.value,
                    "status":   n.status,
                    "vram_gb":  n.vram_gb,
                    "busy":     bool(n.current_job),
                    "jobs":     n.jobs_done,
                }
                for n in sorted(self._nodes.values(), key=lambda x: x.priority)
            ]
        }

    def list_nodes(self) -> list:
        """Liste simple des nœuds pour l'UI."""
        return [
            f"[{n.status.upper():<7}] {n.name:<25} "
            f"{n.vram_gb:.0f}Go VRAM | {n.provider.value}"
            for n in sorted(self._nodes.values(), key=lambda x: x.priority)
        ]


# ── Instructions d'installation ────────────────────────────────────────
SETUP_GUIDE = """
═══════════════════════════════════════════════════════════
  GUIDE DISTRIBUTED RENDERING — OverLord Pipeline
═══════════════════════════════════════════════════════════

MODE 1 : Cluster Local (plusieurs machines sur le même WiFi/Ethernet)
─────────────────────────────────────────────────────────────────────
Sur chaque machine distante (ex: PC de jeu avec RTX 3080) :
  1. Installer ComfyUI
  2. Lancer : python main.py --listen 0.0.0.0 --port 8188 --disable-auto-launch
  3. Sur ta machine principale :
     agent = RemoteGPUAgent()
     agent.add_ssh_node(host="192.168.1.X", user="user", key_path="C:/id_rsa")

MODE 2 : GPU Cloud RunPod
──────────────────────────
  pip install runpod
  1. Créer un compte sur https://runpod.io
  2. Générer une clé API dans Account Settings
  3. agent.create_runpod_instance(api_key="rp_xxxx")
  4. Récupérer l'IP du pod et l'ajouter : agent.add_runpod_node(...)

MODE 3 : GPU Cloud Vast.ai (moins cher pour les longues sessions)
──────────────────────────────────────────────────────────────────
  1. Créer un compte sur https://vast.ai
  2. Chercher une instance avec "ComfyUI" dans le template
  3. Récupérer IP:port et ajouter : agent.add_vast_node(...)

COÛTS APPROXIMATIFS (juin 2026) :
  RTX 4090 24Go  : ~0.40-0.70$/h sur RunPod/Vast.ai
  RTX 3090 24Go  : ~0.20-0.40$/h
  A100 80Go      : ~1.50-2.50$/h (pour les jobs très lourds)

═══════════════════════════════════════════════════════════
"""

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    log = logging.getLogger("remote_gpu_test")
    print(SETUP_GUIDE)

    agent = RemoteGPUAgent(log)
    agent.ping_all()
    fleet = agent.get_fleet_status()

    print(f"\nFlotte GPU : {fleet['total_nodes']} nœud(s)")
    for line in agent.list_nodes():
        print(f"  {line}")

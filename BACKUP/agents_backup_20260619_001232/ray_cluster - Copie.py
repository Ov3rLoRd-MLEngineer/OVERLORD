"""
agents/ray_cluster.py — Cluster Ray & Rendu Distribué
Interconnexion de plusieurs pipelines sur plusieurs machines.
Local (WiFi/Ethernet) ou via tunnel WireGuard (internet).

Architecture :
  Machine principale (RTX 5080) → Ray Head Node
  Autres machines               → Ray Worker Nodes
  Tunnel internet               → WireGuard VPN (IP privées partagées)

Chaque nœud du cluster peut :
  - Exécuter des tâches CPU (sourcing, scénario, storyboard)
  - Exécuter des jobs ComfyUI (si GPU présent)
  - Recevoir et retourner des résultats via Ray

pip install ray[default]
pip install wgconfig  (pour WireGuard)
"""

import json
import logging
import subprocess
import time
import socket
import threading
from pathlib import Path
from datetime import datetime
from dataclasses import dataclass, field
from typing import Optional, Callable
import requests

CLUSTER_CONFIG = Path("workspace/cluster_config.json")
WIREGUARD_DIR  = Path("workspace/wireguard")

# Ports utilisés
RAY_HEAD_PORT    = 6379   # Redis/GCS
RAY_DASHBOARD    = 8265   # Dashboard Ray
RAY_CLIENT_PORT  = 10001  # Client Ray
COMFY_PORT       = 8188


@dataclass
class ClusterNode:
    id:          str
    hostname:    str
    ip:          str
    role:        str     # "head" | "worker"
    gpu_name:    str  = ""
    gpu_vram_gb: float = 0.0
    cpu_cores:   int  = 0
    ram_gb:      float = 0.0
    status:      str  = "unknown"
    ray_started: bool = False
    comfy_port:  int  = COMFY_PORT
    wg_ip:       str  = ""   # IP WireGuard si tunnel internet


class RayClusterManager:
    """
    Gestionnaire du cluster Ray pour OverLord Pipeline.
    Distribue les tâches sur plusieurs machines GPU.
    """

    def __init__(self, logger: logging.Logger = None):
        self.log   = logger or logging.getLogger("ray_cluster")
        self._nodes: dict[str, ClusterNode] = {}
        self._ray_ok   = False
        self._ray_init = False
        self._lock     = threading.Lock()
        self._load_config()

        try:
            import ray
            self._ray = ray
            self._ray_ok = True
        except ImportError:
            self.log.warning("[CLUSTER] pip install ray[default] pour le cluster distribué")

    def _load_config(self):
        if CLUSTER_CONFIG.exists():
            try:
                data = json.loads(CLUSTER_CONFIG.read_text(encoding="utf-8"))
                for n in data.get("nodes",[]):
                    self._nodes[n["id"]] = ClusterNode(**n)
            except Exception:
                pass

    def _save_config(self):
        CLUSTER_CONFIG.parent.mkdir(parents=True, exist_ok=True)
        data = {"nodes": [n.__dict__ for n in self._nodes.values()]}
        CLUSTER_CONFIG.write_text(json.dumps(data,indent=2,ensure_ascii=False),encoding="utf-8")

    # ── Gestion du cluster ────────────────────────────────────────────

    def add_node(self, hostname: str, ip: str, role: str = "worker",
                  gpu_vram_gb: float = 0.0, gpu_name: str = "",
                  wg_ip: str = "") -> ClusterNode:
        """Ajoute un nœud au cluster."""
        node = ClusterNode(
            id=f"{role}_{hostname}", hostname=hostname, ip=ip,
            role=role, gpu_name=gpu_name, gpu_vram_gb=gpu_vram_gb,
            wg_ip=wg_ip,
        )
        self._nodes[node.id] = node
        self._save_config()
        self.log.info(f"[CLUSTER] Nœud ajouté : {hostname} ({role}) | GPU: {gpu_name or 'CPU only'}")
        return node

    def start_head_node(self, port: int = RAY_HEAD_PORT) -> bool:
        """Démarre le nœud maître Ray sur cette machine."""
        if not self._ray_ok:
            self.log.error("[CLUSTER] Ray non installé")
            return False
        try:
            if not self._ray_init:
                self._ray.init(
                    address="auto" if self._ray_init else None,
                    dashboard_host="0.0.0.0",
                    dashboard_port=RAY_DASHBOARD,
                    ignore_reinit_error=True,
                    logging_level=logging.WARNING,
                )
                self._ray_init = True

            local_ip = socket.gethostbyname(socket.gethostname())
            head_node = self.add_node(
                hostname=socket.gethostname(),
                ip=local_ip, role="head",
                gpu_vram_gb=16.0, gpu_name="RTX 5080",
            )
            head_node.ray_started = True
            head_node.status      = "online"

            self.log.info(
                f"[CLUSTER] ✓ Head Node démarré\n"
                f"  Dashboard : http://localhost:{RAY_DASHBOARD}\n"
                f"  Adresse   : {local_ip}:{port}"
            )
            return True
        except Exception as e:
            self.log.error(f"[CLUSTER] Head node : {e}")
            return False

    def connect_worker(self, head_ip: str,
                        head_port: int = RAY_HEAD_PORT) -> bool:
        """
        Connecte cette machine au cluster comme worker.
        À lancer sur les machines secondaires.
        """
        if not self._ray_ok:
            self.log.error("[CLUSTER] Ray non installé")
            return False
        try:
            self._ray.init(
                address=f"{head_ip}:{head_port}",
                ignore_reinit_error=True,
                logging_level=logging.WARNING,
            )
            self._ray_init = True
            self.log.info(f"[CLUSTER] ✓ Worker connecté à {head_ip}:{head_port}")
            return True
        except Exception as e:
            self.log.error(f"[CLUSTER] Connection worker : {e}")
            return False

    def start_worker_on_remote(self, node: ClusterNode,
                                head_ip: str) -> bool:
        """Lance Ray worker sur une machine distante via SSH."""
        ip = node.wg_ip or node.ip
        cmd = (
            f"ssh {node.hostname} "
            f"'ray start --address={head_ip}:{RAY_HEAD_PORT} "
            f"--num-gpus={1 if node.gpu_vram_gb > 0 else 0} "
            f"--block &'"
        )
        try:
            result = subprocess.run(cmd, shell=True, capture_output=True,
                                     text=True, timeout=30)
            if result.returncode == 0:
                node.ray_started = True
                node.status      = "online"
                self.log.info(f"[CLUSTER] Worker démarré sur {node.hostname}")
                return True
        except Exception as e:
            self.log.error(f"[CLUSTER] SSH worker {node.hostname} : {e}")
        return False

    # ── Tâches distribuées ────────────────────────────────────────────

    def submit_distributed(self, fn: Callable, *args,
                            n_gpus: float = 0,
                            n_cpus: float = 1,
                            **kwargs):
        """
        Soumet une fonction à exécuter sur le cluster Ray.
        Ray choisit automatiquement le nœud le plus disponible.
        """
        if not self._ray_ok or not self._ray_init:
            self.log.warning("[CLUSTER] Ray non disponible — exécution locale")
            return fn(*args, **kwargs)

        @self._ray.remote(num_gpus=n_gpus, num_cpus=n_cpus)
        def _remote_fn(*a, **kw):
            return fn(*a, **kw)

        future = _remote_fn.remote(*args, **kwargs)
        self.log.debug(f"[CLUSTER] Tâche soumise : {fn.__name__}")
        return future

    def get_result(self, future, timeout: float = 300):
        """Récupère le résultat d'une tâche distribuée."""
        if not self._ray_ok or not self._ray_init:
            return future   # déjà le résultat en mode local
        try:
            return self._ray.get(future, timeout=timeout)
        except Exception as e:
            self.log.error(f"[CLUSTER] get_result : {e}")
            return None

    def map_distributed(self, fn: Callable, items: list,
                         n_gpus: float = 0) -> list:
        """Distribue une liste de tâches sur le cluster."""
        if not self._ray_ok or not self._ray_init:
            return [fn(item) for item in items]

        @self._ray.remote(num_gpus=n_gpus, num_cpus=1)
        def _remote(item):
            return fn(item)

        futures = [_remote.remote(item) for item in items]
        results = self._ray.get(futures)
        self.log.info(f"[CLUSTER] {len(results)} tâches distribuées terminées")
        return results

    def submit_comfyui_batch(self, workflows: list[dict],
                              timeout_per_job: float = 300) -> list[dict]:
        """
        Distribue un batch de workflows ComfyUI sur tous les nœuds GPU.
        Chaque workflow est assigné au nœud GPU le plus libre.
        """
        gpu_nodes = [n for n in self._nodes.values()
                     if n.gpu_vram_gb > 0 and n.status == "online"]
        if not gpu_nodes:
            self.log.warning("[CLUSTER] Aucun nœud GPU en ligne — exécution locale")
            gpu_nodes = [self._nodes.get("head_" + socket.gethostname())]
            gpu_nodes = [n for n in gpu_nodes if n]

        results = []
        for i, wf in enumerate(workflows):
            node = gpu_nodes[i % len(gpu_nodes)]
            url  = f"http://{node.wg_ip or node.ip}:{node.comfy_port}/prompt"
            try:
                r = requests.post(url, json={"prompt": wf}, timeout=30)
                if r.status_code == 200:
                    pid = r.json().get("prompt_id","?")
                    results.append({"node": node.hostname,
                                     "prompt_id": pid, "status": "submitted"})
                    self.log.info(f"[CLUSTER] Job {i+1}/{len(workflows)} → {node.hostname}")
                else:
                    results.append({"node": node.hostname, "status": "failed"})
            except Exception as e:
                results.append({"node": node.hostname,
                                  "status": "error", "error": str(e)})
        return results

    # ── WireGuard ────────────────────────────────────────────────────

    def generate_wireguard_config(self, nodes: list[dict]) -> dict:
        """
        Génère les configurations WireGuard pour relier les machines sur internet.
        Retourne les configs à copier sur chaque machine.

        nodes : [{"name":"PC_salon","public_key":"xxx","endpoint":"IP:port"}]
        """
        WIREGUARD_DIR.mkdir(parents=True, exist_ok=True)

        # Subnet WireGuard : 10.99.0.0/24
        # Head node : 10.99.0.1
        # Workers   : 10.99.0.2, 10.99.0.3...
        configs = {}
        base_ip = "10.99.0"

        head_conf = (
            "[Interface]\n"
            f"Address = {base_ip}.1/24\n"
            "ListenPort = 51820\n"
            "PrivateKey = <COLLE_TA_CLE_PRIVEE_ICI>\n\n"
        )

        for i, node in enumerate(nodes):
            worker_ip = f"{base_ip}.{i+2}"
            peer_block = (
                f"[Peer]  # {node['name']}\n"
                f"PublicKey = {node.get('public_key','COLLE_LA_CLE_PUBLIQUE')}\n"
                f"AllowedIPs = {worker_ip}/32\n"
                f"Endpoint = {node.get('endpoint','IP_PUBLIQUE:51820')}\n"
                "PersistentKeepalive = 25\n\n"
            )
            head_conf += peer_block

            worker_conf = (
                "[Interface]\n"
                f"Address = {worker_ip}/24\n"
                "PrivateKey = <COLLE_TA_CLE_PRIVEE_ICI>\n\n"
                f"[Peer]  # Head OverLord\n"
                f"PublicKey = <CLE_PUBLIQUE_HEAD>\n"
                f"Endpoint = <IP_PUBLIQUE_HEAD>:51820\n"
                f"AllowedIPs = {base_ip}.0/24\n"
                "PersistentKeepalive = 25\n"
            )
            configs[node["name"]] = {
                "wg_ip":  worker_ip,
                "config": worker_conf,
            }
            path = WIREGUARD_DIR / f"wg0_{node['name']}.conf"
            path.write_text(worker_conf, encoding="utf-8")

        configs["head"] = {"wg_ip": f"{base_ip}.1", "config": head_conf}
        head_path = WIREGUARD_DIR / "wg0_head.conf"
        head_path.write_text(head_conf, encoding="utf-8")

        self.log.info(
            f"[CLUSTER/WG] Configs WireGuard générées → {WIREGUARD_DIR}\n"
            "  Installation : copie wg0.conf dans C:\\Program Files\\WireGuard\\\n"
            "  Démarrage    : wg-quick up wg0"
        )
        return configs

    # ── Monitoring ────────────────────────────────────────────────────

    def get_cluster_status(self) -> dict:
        """Retourne l'état complet du cluster."""
        status = {
            "ray_available": self._ray_ok,
            "ray_connected": self._ray_init,
            "nodes":         len(self._nodes),
            "online":        sum(1 for n in self._nodes.values() if n.status=="online"),
            "total_vram_gb": sum(n.gpu_vram_gb for n in self._nodes.values()),
            "nodes_list":    [
                {
                    "id":       n.id, "hostname": n.hostname,
                    "role":     n.role, "status": n.status,
                    "gpu":      n.gpu_name, "vram_gb": n.gpu_vram_gb,
                    "wg_ip":    n.wg_ip or n.ip,
                }
                for n in sorted(self._nodes.values(),
                                key=lambda x: 0 if x.role=="head" else 1)
            ]
        }
        if self._ray_ok and self._ray_init:
            try:
                res = self._ray.cluster_resources()
                status["ray_resources"] = {
                    k: v for k, v in res.items()
                    if k in ("CPU","GPU","memory")
                }
            except Exception:
                pass
        return status

    def print_cluster_dashboard(self):
        st = self.get_cluster_status()
        print("\n" + "═"*60)
        print(f"  OverLord — Cluster Dashboard")
        print("═"*60)
        print(f"  Ray    : {'✓ Actif' if st['ray_connected'] else '✗ Inactif'}")
        print(f"  Nœuds  : {st['online']}/{st['nodes']} en ligne")
        print(f"  VRAM   : {st['total_vram_gb']:.0f} Go total")
        if "ray_resources" in st:
            r = st["ray_resources"]
            print(f"  CPU    : {r.get('CPU',0):.0f} cœurs | "
                  f"GPU : {r.get('GPU',0):.0f} | "
                  f"RAM : {r.get('memory',0)/1e9:.0f} Go")
        print()
        for n in st["nodes_list"]:
            icon = "⭐" if n["role"]=="head" else "○"
            gpu_str = f"{n['gpu']} {n['vram_gb']:.0f}Go" if n["gpu"] else "CPU only"
            print(f"  {icon} {n['hostname']:<20} {n['status']:<8} {gpu_str}")
        print("═"*60)
        if st["ray_connected"]:
            print(f"  Dashboard Ray : http://localhost:{RAY_DASHBOARD}")
        print()

    def stop(self):
        """Arrête proprement le cluster Ray."""
        if self._ray_ok and self._ray_init:
            try:
                self._ray.shutdown()
                self.log.info("[CLUSTER] Ray arrêté ✓")
            except Exception:
                pass


# ── Script de configuration rapide ────────────────────────────────────
SETUP_GUIDE = """
╔══════════════════════════════════════════════════════════════╗
║  GUIDE CLUSTER RAY — OverLord Pipeline                      ║
╠══════════════════════════════════════════════════════════════╣
║                                                              ║
║  1. INSTALLER RAY                                            ║
║     pip install ray[default]                                ║
║                                                              ║
║  2. DÉMARRER LE HEAD NODE (ta machine RTX 5080)             ║
║     python -c "                                              ║
║       from agents.ray_cluster import RayClusterManager      ║
║       c = RayClusterManager()                               ║
║       c.start_head_node()                                   ║
║     "                                                        ║
║                                                              ║
║  3. CONNECTER UN WORKER (autre machine, même réseau)        ║
║     Sur la machine worker :                                  ║
║     python -c "                                              ║
║       from agents.ray_cluster import RayClusterManager      ║
║       c = RayClusterManager()                               ║
║       c.connect_worker('192.168.1.X')  # IP de ta machine  ║
║     "                                                        ║
║                                                              ║
║  4. TUNNEL INTERNET (WIREGUARD)                             ║
║     Installer WireGuard : https://www.wireguard.com         ║
║     Générer les configs : c.generate_wireguard_config(...)  ║
║     Copier wg0.conf sur chaque machine                      ║
║                                                              ║
║  5. DASHBOARD                                                ║
║     http://localhost:8265                                    ║
║                                                              ║
╚══════════════════════════════════════════════════════════════╝
"""


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    print(SETUP_GUIDE)

    cluster = RayClusterManager()
    cluster.print_cluster_dashboard()

    # Exemple ajout de nœuds
    cluster.add_node("PC-Salon",    "192.168.1.50", "worker",
                      gpu_vram_gb=8.0, gpu_name="RTX 3080")
    cluster.add_node("PC-Bureau",   "192.168.1.51", "worker",
                      gpu_vram_gb=0,  gpu_name="")
    cluster.print_cluster_dashboard()

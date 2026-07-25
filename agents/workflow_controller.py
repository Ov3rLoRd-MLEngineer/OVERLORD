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
agents/workflow_controller.py — Contrôleur de Workflow ComfyUI V1.70
Pilote les workflows Advanced_QwenVL et Detailer via l'API ComfyUI.
Gère le Fast Groups Bypasser pour activer/désactiver les blocs.

Architecture :
  - Advanced_QwenVL = génération principale (personnage, BG, RegionalPrompting)
  - Detailer_V35    = post-traitement (yeux, mains, visage, inpaint, upscale)

Le Fast Groups Bypasser contrôle tout via OPT_CONNECTION.
On modifie les widgets_values du nœud Bypasser pour activer/désactiver
des groupes entiers sans toucher au câblage.

Usage :
  from agents.workflow_controller import WorkflowController
  ctrl = WorkflowController()
  
  # Générer un background pur
  ctrl.run_background_pass(
      prompt="tokyo-3 cityscape, destroyed buildings, sunset, no characters",
      output_name="bg_scene_01"
  )
  
  # Générer Asuka sans background
  ctrl.run_character_pass(
      character="asuka",
      prompt="asuka langley, red plug suit, battle stance",
      pose_image="workspace/poses/pose_01.png"
  )
"""

import json
import logging
import time
import urllib.request
import urllib.parse
import urllib.error
import sys
import io
from pathlib import Path
from datetime import datetime

if hasattr(sys.stdout, 'buffer'):
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

try:
    from agents.context_bus import get_bus
    BUS_OK = True
except ImportError:
    BUS_OK = False

try:
    from agents.config_manager import get_config
    CFG_OK = True
except ImportError:
    CFG_OK = False

try:
    from agents.region_mask_generator import generate_regional_mask, generate_layer_mask
    MASK_OK = True
except ImportError:
    MASK_OK = False

_REPO_ROOT = Path(__file__).resolve().parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))
import config

COMFYUI_URL    = "http://127.0.0.1:8188"
COMFYUI_INPUT  = config.COMFYUI_INPUT
COMFYUI_OUTPUT = config.COMFYUI_OUTPUT

ADVANCED_WF = Path("Advanced_QwenVL_V35.json")
DETAILER_WF = Path("Detailer_V35.json")

# ── Paramètres par défaut optimisés pour la production studio ─────────

DEFAULTS = {
    "checkpoint":   "fabricatedXL_v70.safetensors",
    "vae":          "sdxl_vae.safetensors",
    "width":        1024,
    "height":       1536,
    "steps":        28,
    "cfg":          6.0,
    "sampler":      "euler_ancestral",
    "scheduler":    "normal",
    "denoise":      1.0,
    "negative":     (
        "bad quality, worst quality, worst detail, sketch, "
        "bad hands, bad anatomy, deformed, artist name, "
        "watermark, signature, patreon, twitter username"
    ),
}

# ── Configuration des passes de production ───────────────────────────

# Quels groupes activer pour chaque type de passe
PASS_CONFIGS = {
    "background": {
        "description": "Background pur — aucun personnage",
        "enable": [],
        "disable": [
            "Enable Load Image", "Enable Regional Prompting",
            "Enable Hand ADetailer", "Enable Body ADetailer",
            "Enable Face ADetailer", "Enable Eyes ADetailer",
            "Enable IP-Adapter Style & Composition", "Enable Clip Vision",
            "Enable OpenPose", "Enable Any ControlNet",
            "Enable IP-Adapter Advanced", "Enable IP-Adapter FaceID",
            "Enable Remove Background", "Enable Z-TIPO",
        ],
        "prompt_suffix": ", no humans, no characters, background only, scenery",
        "neg_suffix":    ", person, character, girl, boy, human",
    },
    "character_base": {
        "description": "Personnage nu sans background",
        "enable": ["Enable Face ADetailer"],
        "disable": [
            "Enable Load Image", "Enable Regional Prompting",
            "Enable Hand ADetailer", "Enable Body ADetailer",
            "Enable Eyes ADetailer", "Enable IP-Adapter Style & Composition",
            "Enable Any ControlNet", "Enable IP-Adapter Advanced",
            "Enable Remove Background",
        ],
        "prompt_suffix": ", simple white background, full body",
        "neg_suffix":    ", background, scenery, clothing, dress, uniform",
    },
    "character_clothed": {
        "description": "Personnage avec vêtements",
        "enable": ["Enable Face ADetailer", "Enable Hand ADetailer"],
        "disable": [
            "Enable Load Image", "Enable Regional Prompting",
            "Enable Body ADetailer", "Enable Eyes ADetailer",
            "Enable IP-Adapter Style & Composition",
            "Enable IP-Adapter Advanced", "Enable Remove Background",
        ],
        "prompt_suffix": ", white background, full body",
        "neg_suffix":    ", background, scenery",
    },
    "character_openpose": {
        "description": "Personnage avec pose contrainte (OpenPose)",
        "enable": ["Enable Face ADetailer", "Enable Hand ADetailer", "Enable OpenPose"],
        "disable": [
            "Enable Load Image", "Enable Regional Prompting",
            "Enable Body ADetailer", "Enable Eyes ADetailer",
            "Enable IP-Adapter Style & Composition",
            "Enable IP-Adapter Advanced", "Enable Remove Background",
        ],
        "prompt_suffix": ", white background, full body",
        "neg_suffix":    ", background, scenery",
    },
    "regional_multi_char": {
        "description": "Regional Prompting — plusieurs personnages",
        "enable": ["Enable Regional Prompting", "Enable Face ADetailer"],
        "disable": [
            "Enable Load Image", "Enable Hand ADetailer",
            "Enable Body ADetailer", "Enable Eyes ADetailer",
            "Enable IP-Adapter Style & Composition",
            "Enable IP-Adapter Advanced", "Enable Remove Background",
        ],
        "prompt_suffix": "",
        "neg_suffix": "",
    },
    "rembg": {
        "description": "Suppression background (BEN2)",
        "enable": ["Enable Remove Background"],
        "disable": [
            "Enable Load Image", "Enable Regional Prompting",
            "Enable Hand ADetailer", "Enable Body ADetailer",
            "Enable Face ADetailer", "Enable Eyes ADetailer",
        ],
        "prompt_suffix": "",
        "neg_suffix": "",
    },
    "detail_eyes": {
        "description": "Detailer — yeux uniquement",
        "workflow": "detailer",
        "enable": ["Enable Eyes ADetailer", "Enable Use SAMLoader", "Enable Face ADetailer"],
        "disable": [
            "Enable Hand ADetailer", "Enable Body ADetailer",
            "Enable Inpaint", "Enable Outpaint", "Enable HiresFix",
            "Enable Ultimate SD Upscale",
        ],
    },
    "detail_hands": {
        "description": "Detailer — mains uniquement",
        "workflow": "detailer",
        "enable": ["Enable Hand ADetailer", "Enable Use SAMLoader"],
        "disable": [
            "Enable Eyes ADetailer", "Enable Body ADetailer",
            "Enable Face ADetailer", "Enable Inpaint",
            "Enable Outpaint", "Enable HiresFix",
        ],
    },
    "detail_face": {
        "description": "Detailer — visage complet",
        "workflow": "detailer",
        "enable": ["Enable Face ADetailer", "Enable Eyes ADetailer", "Enable Use SAMLoader"],
        "disable": [
            "Enable Hand ADetailer", "Enable Body ADetailer",
            "Enable Inpaint", "Enable Outpaint", "Enable HiresFix",
        ],
    },
    "detail_inpaint": {
        "description": "Detailer — inpaint zone masquée",
        "workflow": "detailer",
        "enable": ["Enable Inpaint", "Enable Mask ADetailer"],
        "disable": [
            "Enable Eyes ADetailer", "Enable Hand ADetailer",
            "Enable Body ADetailer", "Enable Face ADetailer",
            "Enable Outpaint", "Enable HiresFix",
        ],
    },
    "upscale": {
        "description": "Upscale ×1.5 final",
        "workflow": "detailer",
        "enable": ["Enable Ultimate SD Upscale", "Enable Color Match"],
        "disable": [
            "Enable Eyes ADetailer", "Enable Hand ADetailer",
            "Enable Body ADetailer", "Enable Face ADetailer",
            "Enable Inpaint", "Enable Outpaint",
        ],
    },
    "full_detail": {
        "description": "Détail complet — toute la chaîne",
        "workflow": "detailer",
        "enable": [
            "Enable Face ADetailer", "Enable Eyes ADetailer",
            "Enable Hand ADetailer", "Enable Use SAMLoader",
            "Enable Color Match", "Enable Compression Removal",
        ],
        "disable": ["Enable Inpaint", "Enable Outpaint"],
    },
}

# ── LoRas personnages ─────────────────────────────────────────────────

CHARACTER_LORAS = {
    "asuka": {
        "lora":     "asuka-langley-soryuu-classic-ponyxl-lora-nochekaiser.safetensors",
        "strength": 0.9,
        "trigger":  "asuka langley, asuka langley soryu",
        "base_tags": "1girl, red hair, blue eyes, hair clips, evangelion",
    },
    "rei": {
        "lora":     "rei-ayanami-classic-ponyxl-lora-nochekaiser.safetensors",
        "strength": 0.85,
        "trigger":  "rei ayanami",
        "base_tags": "1girl, short blue hair, red eyes, pale skin, evangelion",
    },
    "mari": {
        "lora":     "mari-makinami-rebuild-ponyxl-lora-nochekaiser.safetensors",
        "strength": 0.88,
        "trigger":  "mari makinami",
        "base_tags": "1girl, brown hair, green eyes, glasses, evangelion",
    },
}


class WorkflowController:
    """Pilote les workflows ComfyUI pour la production studio."""

    def __init__(self, comfyui_url: str = COMFYUI_URL):
        self.url    = comfyui_url.rstrip("/")
        self.log    = logging.getLogger("workflow_controller")
        self._queue: list = []

    # ── Communication ComfyUI ─────────────────────────────────────────

    def _api_get(self, endpoint: str) -> dict | None:
        try:
            with urllib.request.urlopen(
                f"{self.url}/{endpoint}", timeout=10
            ) as resp:
                return json.loads(resp.read())
        except Exception as e:
            self.log.error(f"[CTRL] GET /{endpoint} : {e}")
            return None

    def _api_post(self, endpoint: str, data: dict) -> dict | None:
        try:
            payload = json.dumps(data).encode("utf-8")
            req     = urllib.request.Request(
                f"{self.url}/{endpoint}",
                data=payload,
                headers={"Content-Type": "application/json"},
                method="POST"
            )
            with urllib.request.urlopen(req, timeout=30) as resp:
                return json.loads(resp.read())
        except Exception as e:
            self.log.error(f"[CTRL] POST /{endpoint} : {e}")
            return None

    def is_alive(self) -> bool:
        result = self._api_get("system_stats")
        return result is not None

    def get_queue_size(self) -> int:
        q = self._api_get("queue")
        if q:
            return len(q.get("queue_running", [])) + len(q.get("queue_pending", []))
        return 0

    def wait_for_idle(self, timeout: int = 600, poll: float = 2.0):
        """Attendre que la queue ComfyUI soit vide."""
        start = time.time()
        while time.time() - start < timeout:
            if self.get_queue_size() == 0:
                return True
            time.sleep(poll)
        self.log.warning(f"[CTRL] Timeout ({timeout}s) en attente idle")
        return False

    # ── Construction du prompt API ────────────────────────────────────

    def _load_workflow(self, wf_path: Path) -> dict:
        """Charge un workflow JSON frontend."""
        data = json.loads(wf_path.read_text(encoding="utf-8"))
        return data

    def _find_node(self, workflow: dict, node_type: str) -> dict | None:
        """Trouve le premier nœud d'un type donné."""
        for node in workflow.get("nodes", []):
            if node.get("type") == node_type:
                return node
        return None

    def _find_bypasser(self, workflow: dict) -> dict | None:
        return self._find_node(workflow, "Fast Groups Bypasser (rgthree)")

    def _set_bypasser_value(self, bypasser: dict,
                             label: str, value: str):
        """
        Active/désactive un groupe dans le Fast Groups Bypasser.
        Le bypasser stocke ses valeurs comme liste de dicts dans widgets_values.
        """
        wv = bypasser.get("widgets_values", [])
        if not isinstance(wv, list):
            return

        for item in wv:
            if isinstance(item, dict) and item.get("label") == label:
                item["value"] = value
                return

        # Si non trouvé par dict, essayer le format liste plate
        # Le format varie selon la version de rgthree
        self.log.debug(f"[CTRL] Label '{label}' non trouvé dans bypasser")

    def _configure_pass(self, workflow: dict, pass_name: str):
        """Configure le workflow pour un type de passe donné."""
        config = PASS_CONFIGS.get(pass_name, {})
        bypasser = self._find_bypasser(workflow)
        if not bypasser:
            self.log.warning("[CTRL] Fast Groups Bypasser non trouvé")
            return

        # Activer les groupes requis
        for group in config.get("enable", []):
            self._set_bypasser_value(bypasser, group, "yes")

        # Désactiver les groupes non nécessaires
        for group in config.get("disable", []):
            self._set_bypasser_value(bypasser, group, "no")

    def _build_api_prompt(self, workflow: dict,
                           positive: str, negative: str = "",
                           seed: int = -1, steps: int = None,
                           cfg: float = None,
                           width: int = None, height: int = None,
                           lora: str = "", lora_strength: float = 0.9,
                           **kwargs) -> dict:
        """
        Construit le prompt API depuis le workflow frontend.
        Injecte les paramètres dans les nœuds appropriés.
        """
        nodes     = workflow.get("nodes", [])
        api_nodes = {}

        for node in nodes:
            nid    = str(node["id"])
            ntype  = node.get("type", "")
            wv     = node.get("widgets_values", [])

            # Paramètres principaux via Input Parameters
            if ntype == "Input Parameters (Image Saver)" and wv:
                new_wv = list(wv)
                if seed != -1 and len(new_wv) > 0:
                    new_wv[0] = seed
                if steps and len(new_wv) > 2:
                    new_wv[2] = steps or DEFAULTS["steps"]
                if cfg and len(new_wv) > 3:
                    new_wv[3] = cfg or DEFAULTS["cfg"]
                api_nodes[nid] = {
                    "inputs":     self._wv_to_inputs(ntype, new_wv),
                    "class_type": ntype,
                }

            # Dimensions
            elif ntype == "easy int":
                title = node.get("title", "")
                if title in ("Width", "Height") and wv:
                    val = (width or DEFAULTS["width"]) if "Width" in title \
                          else (height or DEFAULTS["height"])
                    api_nodes[nid] = {
                        "inputs":     {"value": val},
                        "class_type": "easy int",
                    }

            # Prompts
            elif ntype == "CLIPTextEncode" and wv:
                title  = node.get("title", "")
                prompt = positive if "POSITIVE" in title.upper() \
                         else negative or DEFAULTS["negative"]
                if not title:
                    prompt = positive if len(positive) > len(DEFAULTS["negative"]) \
                             else negative or DEFAULTS["negative"]
                api_nodes[nid] = {
                    "inputs":     {"text": prompt},
                    "class_type": "CLIPTextEncode",
                }

            # Checkpoint
            elif ntype == "CheckpointLoaderSimple" and wv:
                if wv[0] != "sam3.1_multiplex_fp16.safetensors":
                    api_nodes[nid] = {
                        "inputs":     {"ckpt_name": DEFAULTS["checkpoint"]},
                        "class_type": "CheckpointLoaderSimple",
                    }

            # LoRa
            elif ntype == "Lora Loader (LoraManager)" and wv and lora:
                api_nodes[nid] = {
                    "inputs":     {
                        "lora_stack": lora,
                        "strength":   lora_strength,
                    },
                    "class_type": "Lora Loader (LoraManager)",
                }

        return {"prompt": api_nodes}

    def _wv_to_inputs(self, node_type: str,
                       widgets_values: list) -> dict:
        """Convertit widgets_values en dict d'inputs API."""
        # Mapping simplifié pour les nœuds les plus courants
        mappings = {
            "Input Parameters (Image Saver)": [
                "seed", "control_after_generate", "steps", "cfg",
                "sampler_name", "scheduler", "denoise"
            ],
        }
        keys = mappings.get(node_type, [])
        result = {}
        for i, key in enumerate(keys):
            if i < len(widgets_values):
                result[key] = widgets_values[i]
        return result

    # ── Passes de production ──────────────────────────────────────────

    def run_pass(self, pass_name: str,
                  positive: str,
                  negative: str = "",
                  character: str = None,
                  pose_image: str = None,
                  regional_mask: str = None,
                  seed: int = -1,
                  steps: int = None,
                  wait: bool = True,
                  output_name: str = None,
                  logger=None) -> dict:
        """
        Lance une passe de production.
        
        Args:
            pass_name : type de passe (voir PASS_CONFIGS)
            positive  : prompt positif
            negative  : prompt négatif (auto si vide)
            character : nom du personnage ('asuka', 'rei', 'mari')
            pose_image : chemin vers l'image de pose OpenPose
            seed      : -1 = aléatoire
        """
        log = logger or self.log
        pc  = PASS_CONFIGS.get(pass_name, {})

        if not self.is_alive():
            log.error("[CTRL] ComfyUI non accessible — vérifier http://127.0.0.1:8188")
            return {"error": "comfyui_unreachable"}

        log.info(f"[CTRL] Passe '{pass_name}' : {pc.get('description','')}")

        # Sélectionner le workflow
        wf_type = pc.get("workflow", "advanced")
        wf_path = DETAILER_WF if wf_type == "detailer" else ADVANCED_WF

        if not wf_path.exists():
            log.error(f"[CTRL] Workflow non trouvé : {wf_path}")
            return {"error": f"workflow_not_found: {wf_path}"}

        workflow = self._load_workflow(wf_path)
        self._configure_pass(workflow, pass_name)

        # LoRa du personnage
        lora, lora_strength = "", 0.9
        char_tags = ""
        if character and character in CHARACTER_LORAS:
            char_data     = CHARACTER_LORAS[character]
            lora          = char_data["lora"]
            lora_strength = char_data["strength"]
            char_tags     = char_data.get("trigger", "") + ", " + \
                            char_data.get("base_tags", "")

        # Enrichir le prompt
        prompt_suffix = pc.get("prompt_suffix", "")
        neg_suffix    = pc.get("neg_suffix", "")
        full_positive = f"{char_tags}, {positive}{prompt_suffix}".strip(", ")
        full_negative = (negative or DEFAULTS["negative"]) + neg_suffix

        # Image de pose OpenPose
        if pose_image and COMFYUI_INPUT.exists():
            src = Path(pose_image)
            if src.exists():
                dest = COMFYUI_INPUT / "load_openpose.png"
                import shutil
                shutil.copy2(src, dest)
                log.info(f"[CTRL] Pose image → {dest.name}")

        # Masque régional
        if regional_mask and COMFYUI_INPUT.exists():
            src = Path(regional_mask)
            if src.exists():
                import shutil
                shutil.copy2(src, COMFYUI_INPUT / "redgreenregion.png")

        # Construire le prompt API
        api_prompt = self._build_api_prompt(
            workflow, full_positive, full_negative,
            seed=seed, steps=steps,
            lora=lora, lora_strength=lora_strength,
        )

        # Envoyer à ComfyUI
        result = self._api_post("prompt", api_prompt)
        if not result:
            log.error("[CTRL] Envoi prompt échoué")
            return {"error": "prompt_failed"}

        prompt_id = result.get("prompt_id", "")
        log.info(f"[CTRL] ✓ Prompt envoyé : {prompt_id}")

        if BUS_OK:
            try:
                bus = get_bus()
                bus.write("ctrl.last_pass",      pass_name,  agent_id="workflow_ctrl")
                bus.write("ctrl.last_prompt_id", prompt_id,  agent_id="workflow_ctrl")
                bus.write("ctrl.character",      character or "", agent_id="workflow_ctrl")
            except Exception:
                pass

        if wait and prompt_id:
            log.info("[CTRL] En attente de complétion...")
            self.wait_for_idle()
            log.info("[CTRL] Passe terminée")

        return {
            "pass":      pass_name,
            "prompt_id": prompt_id,
            "character": character,
            "positive":  full_positive[:100],
        }

    # ── Raccourcis passes communes ────────────────────────────────────

    def run_background_pass(self, prompt: str, **kwargs) -> dict:
        """Background pur — aucun personnage."""
        return self.run_pass("background", positive=prompt, **kwargs)

    def run_character_pass(self, character: str, prompt: str,
                            clothed: bool = True, **kwargs) -> dict:
        """Personnage avec ou sans vêtements."""
        pass_name = "character_clothed" if clothed else "character_base"
        return self.run_pass(pass_name, positive=prompt,
                              character=character, **kwargs)

    def run_openpose_pass(self, character: str, prompt: str,
                           pose_image: str, **kwargs) -> dict:
        """Personnage contraint par OpenPose."""
        return self.run_pass("character_openpose", positive=prompt,
                              character=character, pose_image=pose_image, **kwargs)

    def run_detail_chain(self, image_path: str,
                          passes: list = None, **kwargs) -> dict:
        """
        Chaîne de détail complète sur une image existante.
        passes : liste ordonnée de passes Detailer
        """
        if passes is None:
            passes = ["detail_face", "detail_eyes", "detail_hands", "upscale"]

        results = []
        for pass_name in passes:
            self.log.info(f"[CTRL] Détail pass : {pass_name}")
            r = self.run_pass(pass_name, positive="", **kwargs)
            results.append(r)

        return {"chain": passes, "results": results}

    def run_rembg(self, image_path: str, **kwargs) -> dict:
        """Suppression background BEN2."""
        if COMFYUI_INPUT.exists():
            import shutil
            shutil.copy2(image_path, COMFYUI_INPUT / "load_image.png")
        return self.run_pass("rembg", positive="", **kwargs)


# Singleton
_controller: WorkflowController | None = None

def get_controller() -> WorkflowController:
    global _controller
    if _controller is None:
        _controller = WorkflowController()
    return _controller


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Ov3rLoRd Workflow Controller")
    parser.add_argument("--list-passes", action="store_true")
    parser.add_argument("--status",      action="store_true")
    parser.add_argument("--pass",        type=str, dest="pass_name")
    parser.add_argument("--positive",    type=str, default="")
    parser.add_argument("--character",   type=str, default=None)
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO,
                        format="%(asctime)s [%(levelname)s] %(message)s")

    ctrl = get_controller()

    if args.list_passes:
        print(f"\n{'─'*60}")
        print(f"  PASSES DISPONIBLES ({len(PASS_CONFIGS)})")
        print(f"{'─'*60}")
        for name, config in PASS_CONFIGS.items():
            wf = config.get("workflow", "advanced")
            print(f"  {name:30s} [{wf:8s}] {config.get('description','')}")
        print(f"{'─'*60}")

    elif args.status:
        alive = ctrl.is_alive()
        queue = ctrl.get_queue_size() if alive else 0
        print(f"ComfyUI : {'EN LIGNE' if alive else 'HORS LIGNE'}")
        print(f"Queue   : {queue} job(s) en attente")

    elif args.pass_name:
        result = ctrl.run_pass(
            args.pass_name,
            positive=args.positive,
            character=args.character,
        )
        print(json.dumps(result, indent=2, ensure_ascii=False))

    else:
        parser.print_help()

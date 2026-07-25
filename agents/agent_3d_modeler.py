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
agents/agent_3d_modeler.py — Agent de Modélisation 3D OverLord
Génère des modèles 3D depuis du texte ou des images 2D.

Moteurs supportés :
  - Shap-E (OpenAI) : texte → mesh 3D, pip install shap-e
  - TripoSR : image 2D → mesh 3D, pip install tsr
  - Meshy API : texte → mesh 3D haute qualité (API cloud, clé requise)
  - OpenSCAD : modélisation paramétrique scriptée
  - Blender headless : nettoyage, subdivision, UV, rendu preview

Sortie :
  - .obj / .stl / .glb selon le mode
  - Preview PNG (rendu Blender ou miniature)
  - Rapport qualité maillage (watertight, manifold, volume)

Compatible Anycubic Mono X 6Ks :
  - Volume max : 196 x 122 x 200 mm
  - Résolution XY : 17 µm
  - Export STL → Chitubox/Lychee pour slicing résine
"""

import json
import logging
import subprocess
import shutil
import time
import math
import requests
from pathlib import Path
from datetime import datetime
from enum import Enum

import sys
import io
if hasattr(sys.stdout, 'buffer') and getattr(sys.stdout, 'encoding','').lower() != 'utf-8':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

OUTPUT_3D_DIR = Path("workspace/3d_output")
PREVIEW_3D_DIR = Path("workspace/3d_previews")

# Specs Anycubic Mono X 6Ks
ANYCUBIC_6KS = {
    "name":          "Anycubic Mono X 6Ks",
    "volume_mm":     (196.0, 122.0, 200.0),   # X, Y, Z en mm
    "resolution_xy": 0.017,                     # 17 microns
    "resolution_z":  0.05,                      # 50 microns standard
    "screen_px":     (11520, 5120),             # 6K
    "resin_types":   ["Standard", "ABS-Like", "Water-Washable",
                      "Flexible", "Plant-Based"],
    "format_out":    [".pwmx", ".ctb", ".photon"],
    "format_in":     [".stl", ".obj", ".3mf"],
}

class Engine3D(Enum):
    SHAP_E    = "shap_e"
    TRIPOSR   = "triposr"
    MESHY_API = "meshy_api"
    OPENSCAD  = "openscad"
    BLENDER   = "blender"
    MANUAL    = "manual"   # import d'un fichier existant


class MeshQuality(Enum):
    VALID      = "valid"
    FIXABLE    = "fixable"
    INVALID    = "invalid"


class Agent3DModeler:
    """
    Orchestrateur de génération 3D pour le pipeline OverLord.
    Sélectionne automatiquement le meilleur moteur selon la tâche.
    """

    def __init__(self, logger: logging.Logger = None,
                 meshy_api_key: str = "",
                 blender_path: str = "blender"):
        self.log          = logger or logging.getLogger("3d_modeler")
        self.meshy_key    = meshy_api_key
        self.blender_path = blender_path

        OUTPUT_3D_DIR.mkdir(parents=True, exist_ok=True)
        PREVIEW_3D_DIR.mkdir(parents=True, exist_ok=True)

        # Détecter les moteurs disponibles
        self._engines = self._detect_engines()
        self.log.info(
            f"[3D] Moteurs disponibles : "
            f"{[e for e, ok in self._engines.items() if ok]}"
        )

    def _detect_engines(self) -> dict:
        engines = {}

        # Shap-E
        try:
            import shap_e  # noqa
            engines["shap_e"] = True
        except ImportError:
            engines["shap_e"] = False

        # TripoSR
        try:
            import tsr  # noqa
            engines["triposr"] = True
        except ImportError:
            engines["triposr"] = False

        # OpenSCAD
        engines["openscad"] = shutil.which("openscad") is not None

        # Blender
        engines["blender"] = (shutil.which(self.blender_path) is not None or
                               Path(self.blender_path).exists())

        # Meshy API
        engines["meshy_api"] = bool(self.meshy_key)

        # trimesh (validation maillage)
        try:
            import trimesh  # noqa
            engines["trimesh"] = True
        except ImportError:
            engines["trimesh"] = False

        return engines

    # ─── GÉNÉRATION TEXTE → 3D ───────────────────────────────────────

    def text_to_3d(self, prompt: str,
                   style: str = "anime",
                   target: str = "render",
                   seed: int = None) -> dict:
        """
        Génère un modèle 3D depuis un prompt texte.

        prompt : description du modèle
        style  : "anime" | "realistic" | "cartoon" | "mechanical"
        target : "render" (qualité visuelle) | "print" (imprimabilité STL)
        seed   : graine aléatoire pour reproductibilité

        Retourne un dict avec les chemins des fichiers générés.
        """
        self.log.info(f"[3D] text_to_3d — prompt='{prompt[:60]}' style={style} target={target}")
        ts     = datetime.now().strftime("%Y%m%d_%H%M%S")
        name   = self._safe_name(prompt[:30])
        outdir = OUTPUT_3D_DIR / f"{ts}_{name}"
        outdir.mkdir(parents=True, exist_ok=True)

        result = {
            "prompt":   prompt,
            "style":    style,
            "target":   target,
            "outdir":   str(outdir),
            "mesh":     None,
            "stl":      None,
            "preview":  None,
            "quality":  None,
            "engine":   None,
        }

        # Sélection du moteur
        if self._engines.get("meshy_api") and target == "print":
            # Meshy = meilleure qualité pour impression
            result = self._meshy_text_to_3d(prompt, style, outdir, result)
        elif self._engines.get("shap_e"):
            result = self._shape_text_to_3d(prompt, outdir, result, seed)
        elif self._engines.get("openscad") and "simple" in prompt.lower():
            result = self._openscad_from_prompt(prompt, outdir, result)
        else:
            self.log.warning(
                "[3D] Aucun moteur text→3D disponible. "
                "Installer : pip install shap-e  ou  pip install trimesh"
            )
            result["engine"] = "none"
            return result

        # Post-traitement : nettoyage Blender si disponible
        if result.get("mesh") and self._engines.get("blender"):
            result = self._blender_cleanup(result["mesh"], outdir, result)

        # Validation maillage
        if result.get("mesh"):
            result["quality"] = self._validate_mesh(result["mesh"])

        # Conversion STL si target=print
        if target == "print" and result.get("mesh"):
            stl_path = self._convert_to_stl(result["mesh"], outdir)
            result["stl"] = stl_path
            if stl_path:
                self._check_print_compatibility(stl_path, result)

        self.log.info(
            f"[3D] Génération terminée — "
            f"mesh={result.get('mesh','N/A')} | "
            f"qualité={result.get('quality','?')}"
        )
        return result

    # ─── GÉNÉRATION IMAGE → 3D ───────────────────────────────────────

    def image_to_3d(self, image_path: str,
                    target: str = "render",
                    remove_bg: bool = True) -> dict:
        """
        Génère un modèle 3D depuis une image 2D via TripoSR.
        Idéal pour créer un modèle 3D depuis une génération ComfyUI.

        image_path : chemin de l'image d'entrée (PNG/JPG)
        target     : "render" | "print"
        remove_bg  : supprimer le fond avant la reconstruction
        """
        self.log.info(f"[3D] image_to_3d — source={image_path}")
        ts     = datetime.now().strftime("%Y%m%d_%H%M%S")
        name   = Path(image_path).stem[:20]
        outdir = OUTPUT_3D_DIR / f"{ts}_{name}_3d"
        outdir.mkdir(parents=True, exist_ok=True)

        result = {
            "source_image": image_path,
            "target":       target,
            "outdir":       str(outdir),
            "mesh":         None,
            "stl":          None,
            "preview":      None,
            "quality":      None,
            "engine":       None,
        }

        if not self._engines.get("triposr"):
            self.log.warning(
                "[3D] TripoSR non installé.\n"
                "       pip install tsr\n"
                "       ou  pip install git+https://github.com/VAST-AI-Research/TripoSR.git"
            )
            # Fallback : Meshy API si disponible
            if self._engines.get("meshy_api"):
                return self._meshy_image_to_3d(image_path, outdir, result)
            return result

        return self._triposr_image_to_3d(image_path, outdir, result, remove_bg)

    # ─── SHAP-E ──────────────────────────────────────────────────────

    def _shape_text_to_3d(self, prompt: str, outdir: Path,
                           result: dict, seed: int = None) -> dict:
        """Génération 3D via Shap-E (OpenAI, local)."""
        result["engine"] = "shap_e"
        try:
            import torch
            import shap_e
            from shap_e.diffusion.sample import sample_latents
            from shap_e.diffusion.gaussian_diffusion import diffusion_from_config
            from shap_e.models.download import load_model, load_config
            from shap_e.util.notebooks import decode_latent_mesh

            self.log.info("[3D/Shap-E] Chargement des modèles...")
            device = torch.device("cuda" if torch.cuda.is_available() else "cpu")

            xm      = load_model("transmitter",    device=device)
            model   = load_model("text300M",       device=device)
            diffusion = diffusion_from_config(load_config("diffusion"))

            self.log.info(f"[3D/Shap-E] Génération : '{prompt}'")
            if seed is not None:
                torch.manual_seed(seed)

            latents = sample_latents(
                batch_size=1,
                model=model,
                diffusion=diffusion,
                guidance_scale=15.0,
                model_kwargs={"texts": [prompt]},
                progress=True,
                clip_denoised=True,
                use_fp16=True,
                use_karras=True,
                karras_steps=64,
                sigma_min=1e-3,
                sigma_max=160,
                s_churn=0,
            )

            # Exporter le mesh
            mesh_path = str(outdir / "mesh.obj")
            t = decode_latent_mesh(xm, latents[0]).tri_mesh()
            with open(mesh_path, "w") as f:
                t.write_obj(f)

            result["mesh"] = mesh_path
            self.log.info(f"[3D/Shap-E] ✓ Mesh généré : {mesh_path}")

        except Exception as e:
            self.log.error(f"[3D/Shap-E] Erreur : {e}")
        return result

    # ─── TRIPOSR ─────────────────────────────────────────────────────

    def _triposr_image_to_3d(self, image_path: str, outdir: Path,
                              result: dict, remove_bg: bool) -> dict:
        """Reconstruction 3D depuis image via TripoSR."""
        result["engine"] = "triposr"
        try:
            import torch
            from PIL import Image
            import tsr
            from tsr.system import TSR
            from tsr.utils import remove_background, resize_foreground

            self.log.info("[3D/TripoSR] Chargement du modèle...")
            device = "cuda" if torch.cuda.is_available() else "cpu"
            model  = TSR.from_pretrained(
                "stabilityai/TripoSR",
                config_name="config.yaml",
                weight_name="model.ckpt",
            ).to(device)
            model.renderer.set_chunk_size(8192)

            self.log.info(f"[3D/TripoSR] Reconstruction depuis {image_path}")
            img = Image.open(image_path).convert("RGBA")

            if remove_bg:
                img = remove_background(img)
                img = resize_foreground(img, 0.85)

            with torch.no_grad():
                scene_codes = model([img], device=device)

            # Exporter mesh
            mesh_path = str(outdir / "mesh.obj")
            meshes = model.extract_mesh(scene_codes, has_vertex_color=False)
            meshes[0].export(mesh_path)

            result["mesh"] = mesh_path
            self.log.info(f"[3D/TripoSR] ✓ Mesh généré : {mesh_path}")

        except Exception as e:
            self.log.error(f"[3D/TripoSR] Erreur : {e}")
        return result

    # ─── MESHY API ───────────────────────────────────────────────────

    def _meshy_text_to_3d(self, prompt: str, style: str,
                           outdir: Path, result: dict) -> dict:
        """Génération 3D haute qualité via Meshy API (cloud)."""
        result["engine"] = "meshy_api"
        base_url = "https://api.meshy.ai/v2"
        headers  = {"Authorization": f"Bearer {self.meshy_key}",
                    "Content-Type": "application/json"}

        # Mapper le style OverLord vers les styles Meshy
        style_map = {
            "anime":      "anime",
            "realistic":  "realistic",
            "cartoon":    "cartoon",
            "mechanical": "realistic",
        }

        try:
            # Créer la tâche
            payload = {
                "mode":          "preview",
                "prompt":        prompt,
                "art_style":     style_map.get(style, "anime"),
                "negative_prompt": "low quality, blurry, broken mesh",
            }
            resp = requests.post(f"{base_url}/text-to-3d",
                                  headers=headers, json=payload, timeout=30)
            resp.raise_for_status()
            task_id = resp.json()["result"]
            self.log.info(f"[3D/Meshy] Tâche créée : {task_id}")

            # Polling jusqu'à completion
            for _ in range(60):   # timeout 10 min
                time.sleep(10)
                r = requests.get(f"{base_url}/text-to-3d/{task_id}",
                                  headers=headers, timeout=10)
                data = r.json()
                status = data.get("status")
                self.log.debug(f"[3D/Meshy] Status : {status} ({data.get('progress',0)}%)")

                if status == "SUCCEEDED":
                    # Télécharger le mesh
                    model_url = data.get("model_urls", {}).get("obj")
                    if model_url:
                        mesh_resp = requests.get(model_url, timeout=60)
                        mesh_path = str(outdir / "mesh.obj")
                        with open(mesh_path, "wb") as f:
                            f.write(mesh_resp.content)
                        result["mesh"] = mesh_path

                    # Télécharger la preview
                    thumb_url = data.get("thumbnail_url")
                    if thumb_url:
                        thumb_resp = requests.get(thumb_url, timeout=30)
                        preview_path = str(PREVIEW_3D_DIR / f"{task_id}_preview.png")
                        with open(preview_path, "wb") as f:
                            f.write(thumb_resp.content)
                        result["preview"] = preview_path

                    self.log.info(f"[3D/Meshy] ✓ Mesh téléchargé : {mesh_path}")
                    break

                elif status in ("FAILED", "EXPIRED"):
                    self.log.error(f"[3D/Meshy] Tâche échouée : {data.get('task_error')}")
                    break

        except Exception as e:
            self.log.error(f"[3D/Meshy] Erreur : {e}")
        return result

    def _meshy_image_to_3d(self, image_path: str, outdir: Path,
                            result: dict) -> dict:
        """Reconstruction 3D depuis image via Meshy API."""
        result["engine"] = "meshy_api_image"
        # Encoder l'image en base64
        import base64
        with open(image_path, "rb") as f:
            img_b64 = base64.b64encode(f.read()).decode()
        ext = Path(image_path).suffix.lstrip(".")
        data_url = f"data:image/{ext};base64,{img_b64}"

        headers = {"Authorization": f"Bearer {self.meshy_key}",
                   "Content-Type": "application/json"}
        try:
            resp = requests.post(
                "https://api.meshy.ai/v1/image-to-3d",
                headers=headers,
                json={"image_url": data_url, "enable_pbr": True},
                timeout=30
            )
            resp.raise_for_status()
            task_id = resp.json()["result"]
            self.log.info(f"[3D/Meshy Image→3D] Tâche : {task_id}")

            for _ in range(60):
                time.sleep(10)
                r = requests.get(
                    f"https://api.meshy.ai/v1/image-to-3d/{task_id}",
                    headers=headers, timeout=10
                )
                data = r.json()
                if data.get("status") == "SUCCEEDED":
                    url = data.get("model_urls", {}).get("glb")
                    if url:
                        glb_resp = requests.get(url, timeout=60)
                        path = str(outdir / "mesh.glb")
                        with open(path, "wb") as f:
                            f.write(glb_resp.content)
                        result["mesh"] = path
                    break

        except Exception as e:
            self.log.error(f"[3D/Meshy Image→3D] Erreur : {e}")
        return result

    # ─── OPENSCAD ────────────────────────────────────────────────────

    def _openscad_from_prompt(self, prompt: str, outdir: Path,
                               result: dict) -> dict:
        """
        Génère du code OpenSCAD depuis un prompt et l'exporte en STL.
        Utilise un LLM pour générer le script OpenSCAD.
        """
        result["engine"] = "openscad"
        scad_code = self._prompt_to_openscad(prompt)
        if not scad_code:
            return result

        scad_path = outdir / "model.scad"
        scad_path.write_text(scad_code, encoding="utf-8")
        self.log.info(f"[3D/OpenSCAD] Script généré : {scad_path}")

        stl_path = str(outdir / "mesh.stl")
        try:
            subprocess.run(
                ["openscad", "-o", stl_path, str(scad_path)],
                capture_output=True, text=True, timeout=120
            )
            if Path(stl_path).exists():
                result["mesh"] = stl_path
                result["stl"]  = stl_path
                self.log.info(f"[3D/OpenSCAD] ✓ STL généré : {stl_path}")
            else:
                self.log.error("[3D/OpenSCAD] STL non généré")
        except Exception as e:
            self.log.error(f"[3D/OpenSCAD] Erreur : {e}")
        return result

    def _prompt_to_openscad(self, prompt: str) -> str | None:
        """Demande à Claude de générer du code OpenSCAD valide."""
        try:
            resp = requests.post(
                "https://api.anthropic.com/v1/messages",
                headers={"Content-Type": "application/json"},
                json={
                    "model": "claude-sonnet-4-6",
                    "max_tokens": 1500,
                    "system": (
                        "Tu es un expert OpenSCAD. Génère du code OpenSCAD valide et "
                        "compilable pour créer le modèle décrit. "
                        "Réponds UNIQUEMENT avec le code OpenSCAD, sans explication, "
                        "sans backticks, sans commentaires excessifs."
                    ),
                    "messages": [{
                        "role": "user",
                        "content": (
                            f"Génère le code OpenSCAD pour créer : {prompt}\n\n"
                            "Le modèle doit être :\n"
                            "- Watertight (fermé de tous les côtés)\n"
                            "- Orienté pour l'impression résine (axe Z vers le haut)\n"
                            "- Dans un volume max de 196x122x200 mm\n"
                            "- Avec une résolution suffisante ($fn=64 minimum)"
                        )
                    }]
                },
                timeout=30
            )
            if resp.status_code == 200:
                code = resp.json()["content"][0]["text"].strip()
                if code.startswith("```"):
                    code = "\n".join(code.split("\n")[1:-1])
                return code
        except Exception as e:
            self.log.error(f"[3D/OpenSCAD/LLM] Erreur : {e}")
        return None

    def generate_openscad(self, scad_code: str,
                           output_name: str = "model") -> str | None:
        """Compile un script OpenSCAD en STL directement."""
        if not self._engines.get("openscad"):
            self.log.error("[3D/OpenSCAD] OpenSCAD non installé")
            return None
        ts       = datetime.now().strftime("%Y%m%d_%H%M%S")
        outdir   = OUTPUT_3D_DIR / f"{ts}_{output_name}"
        outdir.mkdir(parents=True, exist_ok=True)
        scad_p   = outdir / f"{output_name}.scad"
        stl_p    = outdir / f"{output_name}.stl"
        scad_p.write_text(scad_code, encoding="utf-8")
        try:
            r = subprocess.run(
                ["openscad", "-o", str(stl_p), str(scad_p)],
                capture_output=True, text=True, timeout=300
            )
            if stl_p.exists():
                self.log.info(f"[3D/OpenSCAD] ✓ {stl_p}")
                return str(stl_p)
            self.log.error(f"[3D/OpenSCAD] Erreur compilation : {r.stderr[:200]}")
        except Exception as e:
            self.log.error(f"[3D/OpenSCAD] {e}")
        return None

    # ─── BLENDER HEADLESS ────────────────────────────────────────────

    def _blender_cleanup(self, mesh_path: str, outdir: Path,
                          result: dict) -> dict:
        """Nettoie et optimise un mesh via Blender en mode headless."""
        clean_path = str(outdir / "mesh_clean.obj")
        script = f"""
import bpy, bmesh, sys
bpy.ops.wm.read_homefile(use_empty=True)
bpy.ops.import_scene.obj(filepath=r"{mesh_path}")
obj = bpy.context.selected_objects[0]
bpy.context.view_layer.objects.active = obj

# Nettoyage géométrie
bpy.ops.object.mode_set(mode='EDIT')
bm = bmesh.from_edit_mesh(obj.data)
bmesh.ops.remove_doubles(bm, verts=bm.verts, dist=0.001)
bmesh.ops.fill_holes(bm, faces=bm.faces, sides=0)
bmesh.update_edit_mesh(obj.data)
bpy.ops.object.mode_set(mode='OBJECT')

# Appliquer modificateurs
bpy.ops.object.modifier_add(type='SOLIDIFY')
obj.modifiers['Solidify'].thickness = 0.002
bpy.ops.object.convert(target='MESH')

# Exporter
bpy.ops.export_scene.obj(filepath=r"{clean_path}", use_selection=True)
print("BLENDER_OK:" + r"{clean_path}")
"""
        script_path = outdir / "_blender_cleanup.py"
        script_path.write_text(script, encoding="utf-8")
        try:
            r = subprocess.run(
                [self.blender_path, "--background", "--python", str(script_path)],
                capture_output=True, text=True, timeout=120
            )
            if "BLENDER_OK" in r.stdout and Path(clean_path).exists():
                result["mesh"] = clean_path
                self.log.info(f"[3D/Blender] ✓ Mesh nettoyé : {clean_path}")
        except Exception as e:
            self.log.warning(f"[3D/Blender] Nettoyage ignoré : {e}")
        return result

    def render_preview(self, mesh_path: str,
                        angles: list = None) -> list:
        """
        Génère des previews PNG du mesh depuis plusieurs angles.
        Retourne la liste des chemins des images.
        """
        if not self._engines.get("blender"):
            self.log.warning("[3D/Blender] Non disponible pour le rendu preview")
            return []

        angles    = angles or [0, 45, 90, 135, 180, 270]
        ts        = datetime.now().strftime("%Y%m%d_%H%M%S")
        out_dir   = PREVIEW_3D_DIR / ts
        out_dir.mkdir(parents=True, exist_ok=True)
        previews  = []

        for angle in angles:
            out_path = str(out_dir / f"preview_{angle:03d}.png")
            script   = f"""
import bpy, math
bpy.ops.wm.read_homefile(use_empty=True)

# Importer le mesh
ext = r"{Path(mesh_path).suffix}".lower()
if ext == '.obj':
    bpy.ops.import_scene.obj(filepath=r"{mesh_path}")
elif ext == '.stl':
    bpy.ops.import_mesh.stl(filepath=r"{mesh_path}")
elif ext == '.glb':
    bpy.ops.import_scene.gltf(filepath=r"{mesh_path}")

obj = bpy.context.selected_objects[0] if bpy.context.selected_objects else None
if not obj:
    print("NO_OBJ"); exit()

# Centrer et normaliser
bpy.ops.object.select_all(action='SELECT')
bpy.ops.object.origin_set(type='ORIGIN_GEOMETRY')
obj.location = (0, 0, 0)

# Caméra orbitale
cam_data = bpy.data.cameras.new("Camera")
cam      = bpy.data.objects.new("Camera", cam_data)
bpy.context.scene.collection.objects.link(cam)
bpy.context.scene.camera = cam
r_rad = math.radians({angle})
cam.location = (3 * math.cos(r_rad), 3 * math.sin(r_rad), 2)
cam.data.lens = 50
bpy.ops.object.select_all(action='DESELECT')
cam.select_set(True)
bpy.ops.view3d.camera_to_view_selected() if False else None

# Pointer la caméra vers l'origine
import mathutils
direction = mathutils.Vector((0,0,0)) - cam.location
rot = direction.to_track_quat('-Z', 'Y')
cam.rotation_euler = rot.to_euler()

# Éclairage HDRI-like
bpy.ops.object.light_add(type='SUN', location=(5, 5, 10))
bpy.data.lights['Sun'].energy = 3

# Matériau clay render
mat = bpy.data.materials.new("Clay")
mat.use_nodes = True
bsdf = mat.node_tree.nodes["Principled BSDF"]
bsdf.inputs['Base Color'].default_value = (0.8, 0.7, 0.6, 1)
bsdf.inputs['Roughness'].default_value  = 0.8
if obj.data.materials:
    obj.data.materials[0] = mat
else:
    obj.data.materials.append(mat)

# Rendu
scene = bpy.context.scene
scene.render.engine           = 'CYCLES'
scene.cycles.samples          = 64
scene.render.resolution_x     = 512
scene.render.resolution_y     = 512
scene.render.filepath         = r"{out_path}"
scene.render.image_settings.file_format = 'PNG'
bpy.ops.render.render(write_still=True)
print("RENDER_OK:{out_path}")
"""
            script_path = out_dir / f"_render_{angle}.py"
            script_path.write_text(script, encoding="utf-8")
            try:
                r = subprocess.run(
                    [self.blender_path, "--background", "--python", str(script_path)],
                    capture_output=True, text=True, timeout=180
                )
                if Path(out_path).exists():
                    previews.append(out_path)
                    self.log.info(f"[3D/Blender] Preview {angle}° → {out_path}")
            except Exception as e:
                self.log.warning(f"[3D/Blender] Rendu {angle}° : {e}")

        return previews

    # ─── VALIDATION MAILLAGE ─────────────────────────────────────────

    def _validate_mesh(self, mesh_path: str) -> dict:
        """
        Valide la qualité du maillage pour l'impression 3D.
        Utilise trimesh si disponible, sinon analyse basique.
        """
        report = {
            "path":        mesh_path,
            "is_watertight": False,
            "is_manifold":   False,
            "volume_mm3":    0.0,
            "bounds_mm":     (0, 0, 0),
            "fits_printer":  False,
            "issues":        [],
            "quality":       MeshQuality.INVALID.value,
        }

        if not self._engines.get("trimesh"):
            self.log.warning("[3D/Validate] trimesh non installé — pip install trimesh")
            report["issues"].append("trimesh non disponible — validation partielle")
            report["quality"] = MeshQuality.FIXABLE.value
            return report

        try:
            import trimesh
            mesh = trimesh.load(mesh_path)

            report["is_watertight"] = bool(mesh.is_watertight)
            report["is_manifold"]   = bool(mesh.is_volume)
            report["volume_mm3"]    = float(abs(mesh.volume)) if mesh.is_volume else 0.0

            bounds = mesh.bounding_box.extents   # X, Y, Z en unités du mesh
            # Supposer que 1 unité = 1 mm (standard pour l'impression)
            report["bounds_mm"] = (
                round(float(bounds[0]), 2),
                round(float(bounds[1]), 2),
                round(float(bounds[2]), 2),
            )

            # Vérifier compatibilité Anycubic Mono X 6Ks
            max_x, max_y, max_z = ANYCUBIC_6KS["volume_mm"]
            bx, by, bz = report["bounds_mm"]
            fits = (bx <= max_x and by <= max_y and bz <= max_z)
            report["fits_printer"] = fits

            if not fits:
                report["issues"].append(
                    f"Modèle trop grand : {bx}x{by}x{bz} mm "
                    f"(max {max_x}x{max_y}x{max_z} mm)"
                )

            if not report["is_watertight"]:
                report["issues"].append("Maillage non watertight (trous détectés)")

            if not report["is_manifold"]:
                report["issues"].append("Maillage non manifold (arêtes dégénérées)")

            # Résumé qualité
            if report["is_watertight"] and report["is_manifold"] and fits:
                report["quality"] = MeshQuality.VALID.value
            elif report["is_watertight"] or report["is_manifold"]:
                report["quality"] = MeshQuality.FIXABLE.value

            self.log.info(
                f"[3D/Validate] {Path(mesh_path).name} — "
                f"watertight={report['is_watertight']} | "
                f"volume={report['volume_mm3']:.1f} mm³ | "
                f"fits={fits} | qualité={report['quality']}"
            )

        except Exception as e:
            self.log.error(f"[3D/Validate] Erreur : {e}")
            report["issues"].append(str(e))

        return report

    def _check_print_compatibility(self, stl_path: str, result: dict):
        """Vérifie et ajoute des recommandations pour l'impression résine."""
        quality = result.get("quality", {})
        if not quality:
            return

        recs = []

        # Épaisseur minimale pour résine
        bounds = quality.get("bounds_mm", (0, 0, 0))
        min_dim = min(b for b in bounds if b > 0) if any(b > 0 for b in bounds) else 0
        if min_dim < 0.5:
            recs.append("⚠ Paroi très fine (< 0.5 mm) — risque de casse en résine")

        # Orientation recommandée
        bx, by, bz = bounds
        if bz > 150:
            recs.append("📐 Pièce haute — prévoir des supports importants")

        # Volume et temps d'impression estimé
        vol = quality.get("volume_mm3", 0)
        if vol > 0:
            # Estimation grossière : résine consommée et temps
            resin_ml = vol / 1000  # 1 cm³ ≈ 1 mL
            time_h   = (bz / 50) * 2  # ~2h pour 50mm de hauteur avec 0.05mm layers
            recs.append(f"🧴 Résine estimée : ~{resin_ml:.1f} mL")
            recs.append(f"⏱ Temps impression estimé : ~{time_h:.1f}h")

        recs.append(
            f"🖨 Imprimante : {ANYCUBIC_6KS['name']} "
            f"— résolution {ANYCUBIC_6KS['resolution_xy']*1000:.0f} µm XY"
        )

        result["print_recommendations"] = recs
        for r in recs:
            self.log.info(f"[3D/Print] {r}")

    # ─── CONVERSION STL ──────────────────────────────────────────────

    def _convert_to_stl(self, mesh_path: str, outdir: Path) -> str | None:
        """Convertit OBJ/GLB/PLY en STL pour l'impression."""
        if mesh_path.endswith(".stl"):
            return mesh_path

        stl_path = str(outdir / "model_print.stl")
        if not self._engines.get("trimesh"):
            self.log.warning("[3D/Convert] trimesh requis — pip install trimesh")
            return None
        try:
            import trimesh
            mesh = trimesh.load(mesh_path)
            mesh.export(stl_path)
            self.log.info(f"[3D/Convert] ✓ STL : {stl_path}")
            return stl_path
        except Exception as e:
            self.log.error(f"[3D/Convert] Erreur : {e}")
            return None

    # ─── EXPORT POUR SLICER ──────────────────────────────────────────

    def prepare_for_slicer(self, stl_path: str,
                            scale_mm: tuple = None,
                            orientation_z_up: bool = True) -> dict:
        """
        Prépare le STL pour le slicing Anycubic Mono X 6Ks.
        Gère le redimensionnement et l'orientation.

        scale_mm : (x, y, z) dimensions finales souhaitées en mm
        Retourne un dict avec les fichiers prêts et les instructions Chitubox.
        """
        if not self._engines.get("trimesh"):
            return {"stl": stl_path, "ready": False,
                    "note": "Ouvrir dans Chitubox/Lychee manuellement"}
        try:
            import trimesh
            import numpy as np
            mesh    = trimesh.load(stl_path)
            outdir  = Path(stl_path).parent

            # Redimensionner si demandé
            if scale_mm:
                current = mesh.bounding_box.extents
                scale   = [scale_mm[i] / current[i] if current[i] > 0 else 1.0
                           for i in range(3)]
                mesh.apply_scale(scale)
                self.log.info(f"[3D/Slicer] Redimensionné → {scale_mm} mm")

            # Centrer sur le plateau
            bounds = mesh.bounding_box.centroid
            mesh.apply_translation(-bounds)

            # Poser sur le plateau (Z min = 0)
            z_min = mesh.bounds[0][2]
            mesh.apply_translation([0, 0, -z_min])

            # Sauvegarder le STL final
            final_stl = str(outdir / "ready_for_slicer.stl")
            mesh.export(final_stl)

            bounds_final = tuple(round(float(e), 2) for e in mesh.bounding_box.extents)
            max_dim      = ANYCUBIC_6KS["volume_mm"]

            instructions = [
                f"Fichier prêt : {final_stl}",
                f"Dimensions : {bounds_final[0]} x {bounds_final[1]} x {bounds_final[2]} mm",
                f"Plateau {ANYCUBIC_6KS['name']} : {max_dim[0]} x {max_dim[1]} x {max_dim[2]} mm",
                "→ Ouvrir dans Chitubox Pro ou Lychee Slicer",
                "→ Paramètres résine recommandés :",
                "   • Couche normale : 0.05 mm",
                "   • Couche fond : 0.02 mm (3 couches)",
                "   • Temps exposition normale : 2-3 sec",
                "   • Temps exposition fond : 30-45 sec",
                "   • Anti-aliasing : ON",
            ]

            self.log.info(f"[3D/Slicer] ✓ Prêt pour impression")
            for inst in instructions:
                self.log.info(f"  {inst}")

            return {
                "stl":         final_stl,
                "ready":       True,
                "dimensions":  bounds_final,
                "instructions": instructions,
            }

        except Exception as e:
            self.log.error(f"[3D/Slicer] Erreur : {e}")
            return {"stl": stl_path, "ready": False, "error": str(e)}

    # ─── PIPELINE COMPLET ────────────────────────────────────────────

    def run_3d_pipeline(self, prompt: str,
                         source_image: str = None,
                         mode: str = "render",
                         scale_mm: tuple = None,
                         logger: logging.Logger = None) -> dict:
        """
        Pipeline 3D complet : génération → nettoyage → validation → export.

        prompt       : description textuelle du modèle
        source_image : image 2D source (optionnel, prioritaire sur prompt si fourni)
        mode         : "render" (visuel anime/3D) | "print" (STL imprimante résine)
        scale_mm     : (x, y, z) dimensions finales pour l'impression
        """
        log = logger or self.log
        log.info(f"[3D/Pipeline] Démarrage — mode={mode}")

        # 1. Génération
        if source_image and Path(source_image).exists():
            result = self.image_to_3d(source_image, target=mode)
        else:
            result = self.text_to_3d(prompt, target=mode)

        if not result.get("mesh"):
            log.error("[3D/Pipeline] Génération mesh échouée")
            return result

        # 2. Previews (pour tout mode)
        if self._engines.get("blender"):
            previews = self.render_preview(result["mesh"],
                                            angles=[0, 45, 90, 270])
            result["previews"] = previews

        # 3. Export STL + validation pour impression
        if mode == "print":
            # Convertir en STL si nécessaire
            if not result.get("stl"):
                outdir = Path(result["outdir"])
                result["stl"] = self._convert_to_stl(result["mesh"], outdir)

            # Préparer pour le slicer
            if result.get("stl"):
                slicer_result = self.prepare_for_slicer(
                    result["stl"],
                    scale_mm=scale_mm,
                )
                result["slicer"] = slicer_result

        log.info(
            f"[3D/Pipeline] ✓ Terminé\n"
            f"  Mesh     : {result.get('mesh','N/A')}\n"
            f"  STL      : {result.get('stl','N/A')}\n"
            f"  Qualité  : {result.get('quality',{}).get('quality','?')}\n"
            f"  Previews : {len(result.get('previews',[]))} images"
        )
        return result

    # ─── Utilitaires ─────────────────────────────────────────────────

    def _safe_name(self, s: str) -> str:
        return "".join(c if c.isalnum() or c in "-_" else "_" for c in s)[:40]


# ── Installations requises ────────────────────────────────────────────
INSTALL_GUIDE = """
=== Installation pour la modélisation 3D ===

# Obligatoire (validation et conversion maillage)
pip install trimesh

# Génération texte → 3D (local, recommandé)
pip install shap-e

# Reconstruction image → 3D (local)
pip install git+https://github.com/VAST-AI-Research/TripoSR.git

# Génération haute qualité (API cloud)
# → Obtenir une clé sur https://www.meshy.ai
# → Ajouter dans les paramètres du launcher

# OpenSCAD (modélisation paramétrique)
# → https://openscad.org/downloads.html
# Ajouter openscad.exe au PATH Windows

# Blender (nettoyage, rendu preview)
# → https://www.blender.org/download/
# Ajouter blender.exe au PATH Windows ou configurer le chemin
"""

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    print(INSTALL_GUIDE)

    agent = Agent3DModeler()
    print(f"Moteurs disponibles : {[k for k,v in agent._engines.items() if v]}")

    # Test OpenSCAD (si installé)
    if agent._engines.get("openscad"):
        stl = agent.generate_openscad(
            'sphere(r=10, $fn=64);',
            output_name="test_sphere"
        )
        if stl:
            quality = agent._validate_mesh(stl)
            print(f"Test sphère : {quality['quality']}")
            slicer = agent.prepare_for_slicer(stl)
            for inst in slicer.get("instructions", []):
                print(f"  {inst}")

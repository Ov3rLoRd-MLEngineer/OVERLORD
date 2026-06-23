@echo off
:: ════════════════════════════════════════════════════════════════════
:: download_dependencies.bat
:: Téléchargement automatique des dépendances OverLord Pipeline
::
:: PRÉREQUIS :
::   - Python installé (python --version >= 3.10)
::   - ComfyUI déjà installé dans D:\IA Local\ComfyUI Installation Local\ComfyUI_windows_portable
::   - Connexion internet
::
:: USAGE :
::   1. Ouvrir CMD en tant qu'administrateur
::   2. Naviguer dans le dossier : cd "C:\Users\Ov3rL0rD\Desktop\PIPELINE PROJECT"
::   3. Lancer : download_dependencies.bat
:: ════════════════════════════════════════════════════════════════════

setlocal EnableDelayedExpansion
chcp 65001 > nul
title OverLord — Téléchargement des Dépendances

:: ── CONFIG : chemin ComfyUI (adapte si nécessaire) ──────────────────
set COMFY=D:\IA Local\ComfyUI Installation Local\ComfyUI_windows_portable\ComfyUI
set PYTHON=D:\IA Local\ComfyUI Installation Local\ComfyUI_windows_portable\python_embeded\python.exe

:: Vérifier que ComfyUI existe
if not exist "%COMFY%" (
    echo [ERREUR] ComfyUI non trouve a : %COMFY%
    echo Modifie la variable COMFY dans ce script.
    pause
    exit /b 1
)

echo.
echo  ██████╗ ██╗   ██╗███████╗██████╗ ██╗      ██████╗ ██████╗ ██████╗
echo  ██╔══██╗██║   ██║██╔════╝██╔══██╗██║     ██╔═══██╗██╔══██╗██╔══██╗
echo  ██║  ██║██║   ██║█████╗  ██████╔╝██║     ██║   ██║██████╔╝██║  ██║
echo  ██║  ██║╚██╗ ██╔╝██╔══╝  ██╔══██╗██║     ██║   ██║██╔══██╗██║  ██║
echo  ██████╔╝ ╚████╔╝ ███████╗██║  ██║███████╗╚██████╔╝██║  ██║██████╔╝
echo  ╚═════╝   ╚═══╝  ╚══════╝╚═╝  ╚═╝╚══════╝ ╚═════╝ ╚═╝  ╚═╝╚═════╝
echo.
echo  Pipeline Automatise End-to-End — Installation des dependances
echo  ════════════════════════════════════════════════════════════════
echo.

:: ── ÉTAPE 1 : Dépendances Python du pipeline ────────────────────────
echo [1/6] Installation des packages Python du pipeline...
echo.

pip install requests>=2.31.0 ^
            Pillow>=10.0.0 ^
            customtkinter>=5.2.0 ^
            pywin32>=306 ^
            feedparser>=6.0.10 ^
            pytrends>=4.9.2 ^
            gTTS>=2.5.0 ^
            pyinstaller>=6.0.0

if errorlevel 1 (
    echo [ERREUR] Installation pip echouee.
    pause
    exit /b 1
)
echo [OK] Packages Python installes.
echo.

:: ── ÉTAPE 2 : ffmpeg ────────────────────────────────────────────────
echo [2/6] Verification ffmpeg...
where ffmpeg >nul 2>&1
if errorlevel 1 (
    echo [INFO] ffmpeg non trouve. Telechargement via winget...
    winget install --id Gyan.FFmpeg -e --source winget
    if errorlevel 1 (
        echo [WARN] winget indisponible ou echec.
        echo        Telecharge manuellement : https://www.gyan.dev/ffmpeg/builds/
        echo        Choisis : ffmpeg-release-essentials.zip
        echo        Extrais et ajoute le dossier bin\ a ton PATH.
    )
) else (
    echo [OK] ffmpeg deja installe.
)
echo.

:: ── ÉTAPE 3 : Création des dossiers ComfyUI ─────────────────────────
echo [3/6] Creation des dossiers de modeles ComfyUI...
mkdir "%COMFY%\models\checkpoints"     2>nul
mkdir "%COMFY%\models\vae"             2>nul
mkdir "%COMFY%\models\controlnet\SDXL" 2>nul
mkdir "%COMFY%\models\upscale_models"  2>nul
mkdir "%COMFY%\models\sams"            2>nul
mkdir "%COMFY%\models\clip_vision"     2>nul
mkdir "%COMFY%\models\ipadapter"       2>nul
mkdir "%COMFY%\models\ultralytics\bbox" 2>nul
mkdir "%COMFY%\models\ultralytics\segm" 2>nul
mkdir "%COMFY%\models\loras"           2>nul
echo [OK] Dossiers crees.
echo.

:: ── ÉTAPE 4 : Téléchargement des modèles (CMD) ─────────────────────
echo [4/6] Telechargement des modeles...
echo       (Taille totale approximative : ~10.5 GB)
echo       (Utilise Ctrl+C pour annuler un telechargement individuel)
echo.

:: Utiliser Python + requests pour les téléchargements (plus fiable que curl sur Windows)
%PYTHON% -c "
import sys, urllib.request, os

def download(url, dest, name):
    dest_path = os.path.join(dest, os.path.basename(dest if dest.endswith(name) else os.path.join(dest, name)))
    if os.path.exists(dest_path):
        print(f'  [SKIP] Deja present : {name}')
        return True
    os.makedirs(dest, exist_ok=True)
    print(f'  Telechargement : {name}')
    print(f'  Source : {url[:70]}...')
    try:
        def progress(count, bs, total):
            pct = min(count*bs*100//total, 100) if total > 0 else 0
            bar = '#'*(pct//5) + '-'*(20-pct//5)
            print(f'\r  [{bar}] {pct}%  ', end='', flush=True)
        urllib.request.urlretrieve(url, dest_path, reporthook=progress)
        print(f'\r  [OK] {name}' + ' '*30)
        return True
    except Exception as e:
        print(f'\r  [ERREUR] {name} : {e}')
        return False

COMFY = r'%COMFY%'
errors = []

models = [
    # ── VAE ──────────────────────────────────────────────────────────
    ('https://huggingface.co/stabilityai/sdxl-vae/resolve/main/sdxl_vae.safetensors',
     COMFY + r'\models\vae\sdxl_vae.safetensors',
     'sdxl_vae.safetensors  [VAE officiel SDXL - 335 MB]'),

    # ── CONTROLNET ───────────────────────────────────────────────────
    ('https://huggingface.co/stabilityai/control-lora/resolve/main/control-LoRAs-rank256/control-lora-canny-rank256.safetensors',
     COMFY + r'\models\controlnet\SDXL\control-lora-canny-rank256.safetensors',
     'control-lora-canny-rank256.safetensors  [ControlNet Canny SDXL - 774 MB]'),

    # ── UPSCALE ──────────────────────────────────────────────────────
    ('https://huggingface.co/FacehuggerR/4x_foolhardy_Remacri/resolve/main/4x_foolhardy_Remacri.pth',
     COMFY + r'\models\upscale_models\4x_foolhardy_Remacri.pth',
     '4x_foolhardy_Remacri.pth  [Upscaler 4x - 67 MB]'),

    ('https://huggingface.co/Kim2091/AnimeSharp/resolve/main/4x-UltraSharp.pth',
     COMFY + r'\models\upscale_models\4x-UltraSharp.pth',
     '4x-UltraSharp.pth  [Upscaler anime 4x - 67 MB]'),

    # ── DETECTION YOLO ────────────────────────────────────────────────
    ('https://huggingface.co/Bingsu/adetailer/resolve/main/face_yolov9c.pt',
     COMFY + r'\models\ultralytics\bbox\face_yolov9c.pt',
     'face_yolov9c.pt  [Detection visages - 51 MB]'),

    ('https://huggingface.co/Bingsu/adetailer/resolve/main/hand_yolov8s.pt',
     COMFY + r'\models\ultralytics\bbox\hand_yolov8s.pt',
     'hand_yolov8s.pt  [Detection mains v8 - 23 MB]'),

    ('https://huggingface.co/Bingsu/adetailer/resolve/main/hand_yolov9c.pt',
     COMFY + r'\models\ultralytics\bbox\hand_yolov9c.pt',
     'hand_yolov9c.pt  [Detection mains v9 - 51 MB]'),

    ('https://github.com/ultralytics/assets/releases/download/v8.3.0/yolo11m-seg.pt',
     COMFY + r'\models\ultralytics\segm\yolo11m-seg.pt',
     'yolo11m-seg.pt  [Segmentation corps YOLO11 - 39 MB]'),

    # ── SAM ──────────────────────────────────────────────────────────
    ('https://dl.fbaipublicfiles.com/segment_anything/sam_vit_b_01ec64.pth',
     COMFY + r'\models\sams\sam_vit_b_01ec64.pth',
     'sam_vit_b_01ec64.pth  [SAM Base Meta - 375 MB]'),

    # ── CLIP VISION ──────────────────────────────────────────────────
    ('https://huggingface.co/h94/IP-Adapter/resolve/main/sdxl_models/image_encoder/model.safetensors',
     COMFY + r'\models\clip_vision\CLIP-ViT-bigG-14-laion2B-39B-b160k.safetensors',
     'CLIP-ViT-bigG-14-laion2B.safetensors  [CLIP Vision SDXL - 3.7 GB]'),

    # ── IPADAPTER ────────────────────────────────────────────────────
    ('https://huggingface.co/h94/IP-Adapter-FaceID/resolve/main/ip-adapter-faceid-plusv2_sdxl.bin',
     COMFY + r'\models\ipadapter\ip-adapter-faceid-plusv2_sdxl.bin',
     'ip-adapter-faceid-plusv2_sdxl.bin  [IPAdapter FaceID v2 SDXL - 1.05 GB]'),
]

print(f'  {len(models)} modeles a telecharger...')
print()
for url, dest, label in models:
    dest_dir  = os.path.dirname(dest)
    dest_name = os.path.basename(dest)
    print(f'>>> {label}')
    ok = download(url, dest_dir, dest_name)
    if not ok:
        errors.append(label)
    print()

if errors:
    print('ECHECS :')
    for e in errors:
        print(f'  - {e}')
    sys.exit(1)
else:
    print('Tous les modeles telecharges avec succes.')
"

if errorlevel 1 (
    echo.
    echo [WARN] Certains telechargements ont echoue.
    echo        Consulte la liste des liens manuels plus bas.
)

:: ── ÉTAPE 5 : Custom Nodes ComfyUI ──────────────────────────────────
echo.
echo [5/6] Installation des custom nodes ComfyUI...
echo       (via ComfyUI-Manager CLI si disponible)
echo.

set CUSTOM=%COMFY%\custom_nodes

:: Vérifier git
where git >nul 2>&1
if errorlevel 1 (
    echo [WARN] git non trouve. Installe git : https://git-scm.com/download/win
    echo        Les custom nodes devront etre installes manuellement via ComfyUI-Manager.
    goto :skip_nodes
)

:: Cloner les custom nodes essentiels
echo  Clonage des custom nodes essentiels...
echo.

set NODES=^
    "https://github.com/ltdrdata/ComfyUI-Impact-Pack|ComfyUI-Impact-Pack|CRITIQUE - FaceDetailer SAM Detailer" ^
    "https://github.com/yolain/ComfyUI-Easy-Use|comfyui-easy-use|CRITIQUE - Nœuds easy int float hiresFix" ^
    "https://github.com/cubiq/ComfyUI_IPAdapter_plus|ComfyUI_IPAdapter_plus|IPAdapter FaceID Style" ^
    "https://github.com/rgthree/rgthree-comfy|rgthree-comfy|Seed Image Comparer Reroute" ^
    "https://github.com/kijai/ComfyUI-KJNodes|comfyui-kjnodes|GLSLShader WidgetToString" ^
    "https://github.com/Fannovel16/comfyui_controlnet_aux|comfyui_controlnet_aux|Preprocessors Canny OpenPose" ^
    "https://github.com/willmiao/ComfyUI-Lora-Manager|comfyui-lora-manager|Lora Loader Manager" ^
    "https://github.com/ssitu/ComfyUI_UltimateSDUpscale|comfyui_ultimatesdupscale|UltimateSDUpscale" ^
    "https://github.com/alexopus/ComfyUI-Image-Saver|ComfyUI-Image-Saver|Image Saver metadonnees" ^
    "https://github.com/Kosinkadink/ComfyUI-Advanced-ControlNet|ComfyUI-Advanced-ControlNet|ControlNetApplyAdvanced" ^
    "https://github.com/ltdrdata/ComfyUI-Impact-Subpack|ComfyUI-Impact-Subpack|MaskDetailer extensions" ^
    "https://github.com/pamparamm/ComfyUI-ppm|ComfyUI-ppm|AttentionCouplePPM" ^
    "https://github.com/longgui0318/ComfyUI-QwenVL|ComfyUI-QwenVL|Agent Qwen VL"

for %%N in (%NODES%) do (
    for /F "tokens=1,2,3 delims=|" %%A in ("%%~N") do (
        set REPO=%%A
        set FOLDER=%%B
        set DESC=%%C
        if exist "%CUSTOM%\!FOLDER!" (
            echo   [SKIP] !FOLDER! deja present
        ) else (
            echo   Clonage : !FOLDER! ^(!DESC!^)
            git clone --depth=1 "!REPO!" "%CUSTOM%\!FOLDER!" 2>nul
            if errorlevel 1 (
                echo   [ERREUR] Echec clone : !FOLDER!
            ) else (
                echo   [OK] !FOLDER!
            )
        )
    )
)

:: Post-install Impact Pack
if exist "%CUSTOM%\ComfyUI-Impact-Pack\install.py" (
    echo.
    echo   Post-installation Impact Pack...
    "%PYTHON%" "%CUSTOM%\ComfyUI-Impact-Pack\install.py"
)

:skip_nodes
echo.

:: ── ÉTAPE 6 : Résumé et liens manuels ───────────────────────────────
echo [6/6] Installation terminee !
echo.
echo ════════════════════════════════════════════════════════════════════
echo  VERIFICATION FINALE
echo ════════════════════════════════════════════════════════════════════
echo.

%PYTHON% -c "
import os
COMFY = r'%COMFY%'
checks = [
    (r'\models\vae\sdxl_vae.safetensors',                           'VAE SDXL'),
    (r'\models\controlnet\SDXL\control-lora-canny-rank256.safetensors', 'ControlNet Canny'),
    (r'\models\upscale_models\4x_foolhardy_Remacri.pth',            'Upscaler Remacri'),
    (r'\models\upscale_models\4x-UltraSharp.pth',                   'Upscaler UltraSharp'),
    (r'\models\ultralytics\bbox\face_yolov9c.pt',                   'YOLO Face v9'),
    (r'\models\ultralytics\bbox\hand_yolov8s.pt',                   'YOLO Hand v8'),
    (r'\models\ultralytics\bbox\hand_yolov9c.pt',                   'YOLO Hand v9'),
    (r'\models\ultralytics\segm\yolo11m-seg.pt',                    'YOLO11 Segm'),
    (r'\models\sams\sam_vit_b_01ec64.pth',                          'SAM Base'),
    (r'\models\clip_vision\CLIP-ViT-bigG-14-laion2B-39B-b160k.safetensors', 'CLIP ViT-bigG'),
    (r'\models\ipadapter\ip-adapter-faceid-plusv2_sdxl.bin',        'IPAdapter FaceID v2'),
]
ok = fail = 0
for rel, name in checks:
    path = COMFY + rel
    exists = os.path.exists(path)
    icon = 'OK  ' if exists else 'MANQ'
    size = f'{os.path.getsize(path)/1024/1024:.0f} MB' if exists else 'absent'
    print(f'  [{icon}] {name:<45} {size}')
    if exists: ok += 1
    else: fail += 1
print()
print(f'  Presents : {ok}/{ok+fail}  |  Manquants : {fail}')
"

echo.
echo ════════════════════════════════════════════════════════════════════
echo  TELECHARGEMENTS MANUELS REQUIS (liens directs ci-dessous)
echo  Voir le fichier MANUAL_DOWNLOADS.md pour les instructions
echo ════════════════════════════════════════════════════════════════════
echo.
echo  Ces fichiers ne sont pas telechargeable automatiquement
echo  (authentification CivitAI ou accord de licence requis).
echo.
echo  Destination des checkpoints :
echo  %COMFY%\models\checkpoints\
echo.
echo  Destination des LoRAs :
echo  %COMFY%\models\loras\
echo.
echo  Voir MANUAL_DOWNLOADS.md pour tous les liens.
echo.
pause

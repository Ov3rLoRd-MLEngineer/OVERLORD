@echo off
chcp 65001 >nul
title Ov3rLoRd — Installation des dépendances v1.45
cd /d "%~dp0"

echo.
echo  ================================================================
echo    Ov3rLoRd Pipeline v1.45 — Installation
echo  ================================================================
echo.

:: Vérifier Python
python --version >nul 2>&1
if errorlevel 1 (
    echo [ERREUR] Python introuvable. Installe Python 3.10+ depuis python.org
    pause
    exit /b 1
)
for /f "tokens=2" %%v in ('python --version 2^>^&1') do set PYVER=%%v
echo  [OK] Python %PYVER% détecté
echo.

:MENU
echo  ┌──────────────────────────────────────────────┐
echo  │  Que voulez-vous installer ?                 │
echo  ├──────────────────────────────────────────────┤
echo  │  [1]  Dépendances essentielles               │
echo  │  [2]  Dépendances recommandées               │
echo  │  [3]  Dépendances V1.45 (narrative, dna...)  │
echo  │  [4]  Tout installer (1+2+3)                 │
echo  │  [5]  Modèles à télécharger manuellement     │
echo  │  [6]  Vérifier les installations             │
echo  │  [0]  Quitter                                │
echo  └──────────────────────────────────────────────┘
echo.
set /p CHOICE=  Votre choix [0-6] : 

if "%CHOICE%"=="1" goto :ESSENTIAL
if "%CHOICE%"=="2" goto :RECOMMENDED
if "%CHOICE%"=="3" goto :V145
if "%CHOICE%"=="4" goto :ALL
if "%CHOICE%"=="5" goto :MODELS
if "%CHOICE%"=="6" goto :CHECK
if "%CHOICE%"=="0" exit /b 0
goto :MENU

:ESSENTIAL
echo.
echo  [1/4] Packages essentiels...
python -m pip install requests Pillow feedparser pytrends customtkinter flask cryptography trimesh psutil colorama python-dotenv --quiet
if errorlevel 1 ( echo [ERREUR] Installation partielle. Vérifie ta connexion. ) else ( echo [OK] Essentiels installés. )
goto :DONE

:RECOMMENDED
echo.
echo  [2/4] Packages recommandés...
python -m pip install tweepy google-auth google-auth-oauthlib google-api-python-client chromadb sentence-transformers pywin32 websocket-client opencv-python --quiet
if errorlevel 1 ( echo [ERREUR] Certains packages ont échoué. ) else ( echo [OK] Recommandés installés. )
python -m pip install nvidia-ml-py tbb --quiet
goto :DONE

:V145
echo.
echo  [3/4] Packages V1.45...
python -m pip install networkx imageio imageio-ffmpeg librosa discord.py python-telegram-bot flask-limiter pyinstaller pyfiglet --quiet
if errorlevel 1 ( echo [ERREUR] Installation V1.45 partielle. ) else ( echo [OK] V1.45 installés. )
goto :DONE

:ALL
echo.
echo  Installation complète (5-15 minutes)...
python -m pip install requests Pillow feedparser pytrends customtkinter flask cryptography trimesh psutil colorama python-dotenv tweepy google-auth google-auth-oauthlib google-api-python-client chromadb sentence-transformers pywin32 websocket-client opencv-python nvidia-ml-py tbb imageio imageio-ffmpeg librosa discord.py python-telegram-bot flask-limiter networkx pyinstaller pyfiglet --quiet
if errorlevel 1 ( echo [ERREUR] Installation incomplète. ) else ( echo [OK] Installation complète. )
goto :DONE

:CHECK
echo.
echo  Vérification des packages clés...
python -c "import requests,flask,chromadb,colorama,networkx; print('[OK] Packages clés présents')" 2>nul
if errorlevel 1 echo [WARN] Certains packages manquent — lance l'option [4]
python -c "import torch; print('[OK] PyTorch:', torch.__version__)" 2>nul || echo [WARN] PyTorch absent
python -c "import cv2; print('[OK] OpenCV:', cv2.__version__)" 2>nul || echo [WARN] OpenCV absent
goto :DONE

:MODELS
echo.
echo  ================================================================
echo    MODÈLES À TÉLÉCHARGER MANUELLEMENT
echo  ================================================================
echo.
echo  CHECKPOINT (obligatoire) :
echo  → https://civitai.com/models/833294
echo  → noobaiXLNSFWPony_epsilonPred10.safetensors
echo  → [ComfyUI]\models\checkpoints\
echo.
echo  VAE :
echo  → sdxl_vae.safetensors → [ComfyUI]\models\vae\
echo.
echo  UPSCALER :
echo  → 4x-UltraSharp.pth → [ComfyUI]\models\upscale_models\
echo.
echo  Après téléchargement :
echo  python update_checkpoint.py "noobaiXLNSFWPony_epsilonPred10.safetensors"
echo.
goto :DONE

:DONE
echo.
pause
goto :MENU

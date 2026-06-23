@echo off
chcp 65001 >nul
title Ov3rLoRd — ComfyUI v1.45
cd /d "%~dp0"

echo.
echo  ================================================================
echo    Ov3rLoRd Pipeline v1.45 — Lancement ComfyUI
echo  ================================================================
echo.

:: Lire chemin sauvegardé
set COMFY_PATH=
if exist "comfy_path.cfg" (
    for /f "tokens=1,* delims==" %%A in (comfy_path.cfg) do (
        if "%%A"=="COMFY_PATH" set COMFY_PATH=%%B
    )
)

:: Détection automatique si pas de config
if "%COMFY_PATH%"=="" (
    if exist "D:\ComfyUI_windows_portable\run_nvidia_gpu.bat"          set COMFY_PATH=D:\ComfyUI_windows_portable
    if exist "D:\ComfyUI\run_nvidia_gpu.bat"                           set COMFY_PATH=D:\ComfyUI
    if exist "D:\AI\ComfyUI_windows_portable\run_nvidia_gpu.bat"       set COMFY_PATH=D:\AI\ComfyUI_windows_portable
    if exist "D:\IA Local\ComfyUI_windows_portable\run_nvidia_gpu.bat" set COMFY_PATH=D:\IA Local\ComfyUI_windows_portable
    if exist "C:\ComfyUI_windows_portable\run_nvidia_gpu.bat"          set COMFY_PATH=C:\ComfyUI_windows_portable
)

if not "%COMFY_PATH%"=="" goto :FOUND

:: Saisie manuelle
echo  ComfyUI non détecté automatiquement.
echo  Entrez le chemin complet (contenant run_nvidia_gpu.bat) :
echo.
set /p COMFY_PATH=  Chemin ComfyUI : 
if "%COMFY_PATH%"=="" ( echo [ERREUR] Chemin vide. & pause & exit /b 1 )

:FOUND
if not exist "%COMFY_PATH%\run_nvidia_gpu.bat" (
    echo [ERREUR] run_nvidia_gpu.bat introuvable dans : %COMFY_PATH%
    echo Supprime comfy_path.cfg et réessaie.
    pause & exit /b 1
)

:: Sauvegarder
echo COMFY_PATH=%COMFY_PATH%> "comfy_path.cfg"
echo  [OK] ComfyUI : %COMFY_PATH%
echo.

:MENU
echo  ┌──────────────────────────────────────┐
echo  │  [1]  Lancer ComfyUI (GPU NVIDIA)    │
echo  │  [2]  Lancer ComfyUI (CPU fallback)  │
echo  │  [3]  Lancer ComfyUI (VRAM réduite)  │
echo  │  [4]  Changer le chemin ComfyUI      │
echo  │  [0]  Quitter                        │
echo  └──────────────────────────────────────┘
echo.
set /p CHOICE=  Choix : 

if "%CHOICE%"=="1" goto :GPU
if "%CHOICE%"=="2" goto :CPU
if "%CHOICE%"=="3" goto :LOWVRAM
if "%CHOICE%"=="4" goto :CHANGE
if "%CHOICE%"=="0" exit /b 0
goto :MENU

:GPU
cd /d "%COMFY_PATH%"
python main.py --disable-smart-memory --normalvram --cpu-vae --use-pytorch-cross-attention --preview-method none --disable-auto-launch
if errorlevel 1 echo [ERREUR] ComfyUI a planté — code %errorlevel%
pause & goto :MENU

:CPU
cd /d "%COMFY_PATH%"
python main.py --cpu --preview-method none --disable-auto-launch
if errorlevel 1 echo [ERREUR] ComfyUI CPU a planté
pause & goto :MENU

:LOWVRAM
cd /d "%COMFY_PATH%"
python main.py --lowvram --cpu-vae --preview-method none --disable-auto-launch
if errorlevel 1 echo [ERREUR] ComfyUI lowvram a planté
pause & goto :MENU

:CHANGE
set COMFY_PATH=
set /p COMFY_PATH=  Nouveau chemin ComfyUI : 
if "%COMFY_PATH%"=="" goto :MENU
echo COMFY_PATH=%COMFY_PATH%> "comfy_path.cfg"
echo [OK] Chemin mis à jour.
goto :MENU

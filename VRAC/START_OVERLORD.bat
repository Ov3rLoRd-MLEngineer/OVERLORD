@echo off
:: ============================================================
::  Ov3rLoRd — Menu Principal V1.49
::  FIX : chcp 65001 force l'encodage UTF-8 dans le terminal
:: ============================================================
chcp 65001 > nul
set PYTHONIOENCODING=utf-8
set PYTHONUTF8=1
title Ov3rLoRd Pipeline V1.49
color 0A
echo.
echo  =====================================================
echo   Ov3rLoRd Pipeline V1.49 - La Reconnexion
echo  =====================================================
echo.
echo  [1] Lancer le pipeline complet (maestro.py)
echo  [2] Interface Oracle (oracle_interface.py)
echo  [3] Tests rapides (test_pipeline.py --quick)
echo  [4] Tests integration (test_integration.py)
echo  [5] Deploiement (deploy.py)
echo  [6] Status sante (self_improve.py --mode status)
echo  [7] Quitter
echo.
set /p choix="Votre choix : "

if "%choix%"=="1" python maestro.py --media-type anime --universe "Dragon Ball"
if "%choix%"=="2" python oracle_interface.py
if "%choix%"=="3" python test_pipeline.py --quick
if "%choix%"=="4" python test_integration.py
if "%choix%"=="5" python deploy.py
if "%choix%"=="6" python self_improve.py --mode status
if "%choix%"=="7" exit
pause
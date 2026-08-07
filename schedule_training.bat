@echo off
REM schedule_training.bat — Ov3rLoRd Pipeline
REM Entraine les 4 SegNets (SAM ViT-B fine-tuning) en sequence :
REM   footsegnet (train_sam.py), handsegnet, facesegnet, bodysegnet (train.py)
REM Logs horodates dans D:\OVERLORD\workspace\logs\training\
REM
REM Prerequis pour chaque module : dataset annote + build_coco.py execute
REM (sinon le train echoue proprement avec "instances_train.json introuvable"
REM  et le script passe au module suivant).
REM
REM Usage : schedule_training.bat [epochs]      (defaut : 30)

setlocal
set EPOCHS=%1
if "%EPOCHS%"=="" set EPOCHS=30
set LOGDIR=D:\OVERLORD\workspace\logs\training
if not exist "%LOGDIR%" mkdir "%LOGDIR%"
for /f %%i in ('powershell -NoProfile -Command "Get-Date -Format yyyyMMdd_HHmmss"') do set TS=%%i

echo ============================================================
echo  Ov3rLoRd — schedule_training  (epochs=%EPOCHS%, run=%TS%)
echo  Logs : %LOGDIR%
echo ============================================================
echo [%TS%] DEBUT schedule_training epochs=%EPOCHS% >> "%LOGDIR%\schedule.log"

call :train footsegnet train_sam.py
call :train handsegnet train.py
call :train facesegnet train.py
call :train bodysegnet train.py

echo [%TS%] FIN schedule_training >> "%LOGDIR%\schedule.log"
echo.
echo Termine — voir %LOGDIR%\schedule.log
exit /b 0

:train
set PROJ=%1
set SCRIPT=%2
echo.
echo === %PROJ% (%SCRIPT%) — log : %LOGDIR%\%PROJ%_%TS%.log
pushd D:\OVERLORD\%PROJ%
py -3.12 %SCRIPT% --epochs %EPOCHS% > "%LOGDIR%\%PROJ%_%TS%.log" 2>&1
if errorlevel 1 (
    echo === %PROJ% : ECHEC — voir le log
    echo [%TS%] %PROJ% : ECHEC >> "%LOGDIR%\schedule.log"
) else (
    echo === %PROJ% : OK
    echo [%TS%] %PROJ% : OK >> "%LOGDIR%\schedule.log"
)
popd
exit /b 0

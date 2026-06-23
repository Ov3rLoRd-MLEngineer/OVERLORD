@echo off
REM ================================================================
REM  Ov3rLoRd Pipeline V1.70 — Script d'installation complète
REM  Lance depuis D:\OVERLORD\ en tant qu'administrateur
REM ================================================================
echo.
echo  ============================================================
echo       Ov3rLoRd V1.70 — Installation
echo  ============================================================
echo.

REM ── Vérification Python ──────────────────────────────────────────
python --version >nul 2>&1
if errorlevel 1 (
    echo [ERREUR] Python non trouvé. Installer Python 3.11+ depuis python.org
    pause & exit /b 1
)
echo [OK] Python detecte

REM ── Vérification pip ─────────────────────────────────────────────
pip --version >nul 2>&1
if errorlevel 1 (
    echo [ERREUR] pip non trouvé.
    pause & exit /b 1
)
echo [OK] pip detecte

REM ── Dépendances Python ───────────────────────────────────────────
echo.
echo [INSTALL] Dependances Python...
pip install requests flask psutil Pillow numpy gTTS pydub --quiet
if errorlevel 1 (
    echo [WARN] Certaines dependances ont echoue - verifier manuellement
) else (
    echo [OK] Dependances installees
)

REM ── Vérification Ollama ──────────────────────────────────────────
echo.
echo [CHECK] Ollama...
ollama --version >nul 2>&1
if errorlevel 1 (
    echo [WARN] Ollama non trouve. Installer depuis ollama.ai
    echo        Puis : ollama pull mistral
) else (
    echo [OK] Ollama detecte
    echo [INFO] Telechargement mistral si absent...
    ollama pull mistral
)

REM ── Vérification ffmpeg ──────────────────────────────────────────
echo.
echo [CHECK] ffmpeg...
ffmpeg -version >nul 2>&1
if errorlevel 1 (
    echo [WARN] ffmpeg non trouve.
    echo        Telecharger depuis https://ffmpeg.org et ajouter au PATH
) else (
    echo [OK] ffmpeg detecte
)

REM ── Vérification nvidia-smi ──────────────────────────────────────
echo.
echo [CHECK] NVIDIA GPU...
nvidia-smi >nul 2>&1
if errorlevel 1 (
    echo [WARN] nvidia-smi non trouve. Installer les drivers NVIDIA.
) else (
    echo [OK] GPU NVIDIA detecte
    nvidia-smi --query-gpu=name,memory.total --format=csv,noheader
)

REM ── Création de la structure workspace ───────────────────────────
echo.
echo [INIT] Structure workspace...
if not exist workspace\logs      mkdir workspace\logs
if not exist workspace\scripts   mkdir workspace\scripts
if not exist workspace\storyboards mkdir workspace\storyboards
if not exist workspace\checkpoints mkdir workspace\checkpoints
if not exist workspace\archive   mkdir workspace\archive
if not exist workspace\narrative mkdir workspace\narrative
if not exist workspace\registry  mkdir workspace\registry
if not exist workspace\registry\manifests mkdir workspace\registry\manifests
if not exist workspace\registry\snapshots mkdir workspace\registry\snapshots
if not exist workspace\reports   mkdir workspace\reports
if not exist workspace\backups   mkdir workspace\backups
if not exist workspace\postprod  mkdir workspace\postprod
if not exist workspace\exports   mkdir workspace\exports
if not exist data\prompts        mkdir data\prompts
if not exist ui                  mkdir ui
echo [OK] Structure workspace cree

REM ── Création du .env si absent ───────────────────────────────────
echo.
if not exist .env (
    echo [INIT] Création .env...
    (
        echo # Ov3rLoRd V1.70 — Configuration
        echo ANTHROPIC_API_KEY=
        echo OV_LLM_MODE=offline
        echo OV_OLLAMA_MODEL=mistral
        echo GROK_API_KEY=
        echo TELEGRAM_TOKEN=
        echo TELEGRAM_CHAT_ID=
    ) > .env
    echo [OK] .env cree - editer avec vos cles API
) else (
    echo [OK] .env existant conserve
)

REM ── Initialisation config_manager ────────────────────────────────
echo.
echo [INIT] Config centralisee...
python agents\config_manager.py >nul 2>&1
if errorlevel 1 (
    echo [WARN] config_manager init partielle
) else (
    echo [OK] config.db initialise
)

REM ── Initialisation prompt_library ────────────────────────────────
echo.
echo [INIT] Bibliotheque prompts...
python agents\prompt_library.py >nul 2>&1
if errorlevel 1 (
    echo [WARN] prompt_library init partielle
) else (
    echo [OK] data\prompts\ initialise
)

REM ── Détection GPU et optimisation ────────────────────────────────
echo.
echo [INIT] Optimisation GPU...
python agents\gpu_optimizer.py >nul 2>&1
if errorlevel 1 (
    echo [WARN] gpu_optimizer non execute
) else (
    echo [OK] GPU detecte et workflow patche
)

REM ── Snapshot initial ─────────────────────────────────────────────
echo.
echo [INIT] Snapshot initial des agents...
python -c "from agents.agent_registry import get_registry; r=get_registry(); r.scan(); r.snapshot_all(); print('[OK] Snapshot global')" 2>nul
if errorlevel 1 (
    echo [WARN] agent_registry snapshot partiel
)

REM ── Tests rapides ────────────────────────────────────────────────
echo.
echo [TEST] Tests rapides...
python test_suite_v170.py --quick
if errorlevel 1 (
    echo.
    echo [WARN] Certains tests ont echoue - verifier les agents
) else (
    echo [OK] Tests rapides passes
)

REM ── Résumé ───────────────────────────────────────────────────────
echo.
echo  ============================================================
echo   Installation terminee !
echo  ============================================================
echo.
echo  Prochaines etapes :
echo    1. Editer .env avec vos cles API
echo    2. python overlord_launcher.py    (interface visuelle)
echo    3. python api_server.py           (HUD web http://localhost:5757)
echo    4. python maestro.py --universe "evangelion"   (premier run)
echo.
echo  Pour le mode nuit :
echo    python agents\dream_mode.py --stop-at 08:00
echo.
pause

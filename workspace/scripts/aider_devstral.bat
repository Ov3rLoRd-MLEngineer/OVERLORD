@echo off
REM Lance Aider avec le profil devstral:24b (secours local, ajoute 2026-08-03).
REM Voir DOCS/LLM-Secour.md pour le critere de routage devstral vs
REM qwen2.5-coder:14b vs ov3rlord-coder-stage2v2, et les limites connues.
setlocal

REM IMPORTANT (verifie sur cette machine, voir memoire "ollama-gpu-pinning") :
REM CUDA_VISIBLE_DEVICES positionne ICI n'a AUCUN effet sur quelle carte sert
REM le modele -- Aider est un simple client HTTP vers un serveur Ollama deja
REM lance separement (port 11434). Le pinning reel se fait cote serveur, par
REM UUID (pas index) + OLLAMA_VULKAN=0, dans D:\OVERLORD\launch_ollama.bat.
REM Cette ligne ne sert qu'a documenter l'intention -- si Ollama n'a pas ete
REM (re)lance via launch_ollama.bat, devstral peut tourner sur la RTX 5080
REM (reservee ComfyUI) sans qu'aucun signal d'erreur ne le indique.
set "CUDA_VISIBLE_DEVICES=1"

cd /d D:\OVERLORD

echo [aider_devstral] Verification rapide : devstral:24b present dans Ollama ?
ollama list | findstr /C:"devstral:24b" >nul
if errorlevel 1 (
    echo [aider_devstral] ERREUR : devstral:24b absent de "ollama list".
    echo [aider_devstral] Lancer d'abord : ollama pull devstral:24b
    exit /b 1
)

echo [aider_devstral] Lancement Aider -- modele ollama_chat/devstral:24b
"C:\Users\Ov3rL0rD\.aider\venv\Scripts\aider.exe" ^
    --model ollama_chat/devstral:24b ^
    --read CLAUDE.md ^
    --read DOCS/RAG_SOURCES.md ^
    --read DOCS/INDEX.md ^
    %*

endlocal

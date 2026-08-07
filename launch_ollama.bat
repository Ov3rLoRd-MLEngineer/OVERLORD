@echo off
setlocal
REM Epingle Ollama sur la RTX 5060 Ti (la 5080 est reservee a ComfyUI).
REM IMPORTANT : utiliser l'UUID, l'index numerique (1) n'est PAS honore
REM par les versions recentes d'Ollama (verifie le 2026-07-04).
REM UUID via : nvidia-smi -L (mis a jour 2026-07-14 : la RTX 2070 a ete
REM remplacee par la RTX 5060 Ti 16GB, l'ancien UUID n'existait plus)
set "CUDA_VISIBLE_DEVICES=GPU-cb196733-cc69-2fae-2eed-f363c2fd2219"
REM Depuis Ollama 0.30.2+, la decouverte GPU via Vulkan (activee par defaut)
REM enumere les GPU independamment du pilote CUDA et IGNORE
REM CUDA_VISIBLE_DEVICES -- elle choisit toujours "la meilleure carte" (la
REM 5080, GPU 0) peu importe le pinning demande. Confirme le 2026-07-28
REM (ollama --version 0.32.4) : le worker atterrissait sur GPU 0 malgre ce
REM script. Correctif confirme upstream (github.com/ollama/ollama issues
REM #16508 et #16592) : desactiver Vulkan force le retour a la decouverte
REM CUDA seule, qui respecte CUDA_VISIBLE_DEVICES.
set "OLLAMA_VULKAN=0"
REM Contournement necessaire pour charger de gros modeles (ex. qwen3-coder
REM 30b-a3b) : l'allocation de buffer host "pinned" par CUDA echoue sous
REM Windows sur cette machine (verifie le 2026-07-26), meme avec assez de
REM RAM libre. Cout : legere perte de vitesse de transfert host<->device.
set "GGML_CUDA_NO_PINNED=1"
ollama serve
endlocal

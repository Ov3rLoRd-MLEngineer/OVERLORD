@echo off
setlocal
set UNET_DIR=D:\Ov3rLoRd AI\ComfyUI\models\unet
set VAE_DIR=D:\Ov3rLoRd AI\ComfyUI\models\vae
set TXT_DIR=D:\Ov3rLoRd AI\ComfyUI\models\text_encoders

echo === Telechargement High noise Q4_0 (9.03 GB) ===
curl -L -C - -o "%UNET_DIR%\Index-Anisora-V3.2-High-Q4_0.gguf" "https://huggingface.co/QuantStack/Index-Anisora-V3.2-GGUF/resolve/main/High/Index-Anisora-V3.2-High-Q4_0.gguf"

echo === Telechargement Low noise Q4_K_M (10.13 GB) ===
curl -L -C - -o "%UNET_DIR%\Index-Anisora-V3.2-Low-Q4_K_M.gguf" "https://huggingface.co/QuantStack/Index-Anisora-V3.2-GGUF/resolve/main/Index-Anisora-V3.2-Low-Q4_K_M.gguf"

echo === Telechargement VAE WAN 2.2 (1.41 GB) ===
curl -L -C - -o "%VAE_DIR%\wan2.2_vae.safetensors" "https://huggingface.co/Comfy-Org/Wan_2.2_ComfyUI_Repackaged/resolve/main/split_files/vae/wan2.2_vae.safetensors"

echo === Telechargement Text Encoder UMT5-XXL fp8 scaled (6.74 GB) ===
curl -L -C - -o "%TXT_DIR%\umt5_xxl_fp8_e4m3fn_scaled.safetensors" "https://huggingface.co/Comfy-Org/Wan_2.2_ComfyUI_Repackaged/resolve/main/split_files/text_encoders/umt5_xxl_fp8_e4m3fn_scaled.safetensors"

echo === TOUS LES TELECHARGEMENTS TERMINES ===
pause

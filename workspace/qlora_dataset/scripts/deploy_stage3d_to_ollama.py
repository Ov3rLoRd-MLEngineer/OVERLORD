"""
H-015 -- deploiement du checkpoint valide (adapter_stage3d_final) vers Ollama,
pour usage reel via hermes-agent (meme pipeline que le deploiement de
stage2_instructions_v2 le 2026-08-02 : merge LoRA -> fp16 complet -> GGUF f16
-> `ollama create`).

Nouveau nom de modele Ollama : "ov3rlord-coder-stage3d" -- distinct de
"ov3rlord-coder-stage2v2" (qui reste inchange, non ecrase) pour rester
reversible : Jerémy peut comparer les deux ou revenir en arriere via
`/model` (hermes-agent, voir DOCS/MD/HERMES_AGENT_COMMANDES.md) sans rien
avoir perdu.

GPU : RTX 5080 (cuda:0) uniquement.
Environnement : venv Unsloth Studio, pas py -3.12 --
  C:\\Users\\Ov3rL0rD\\.unsloth\\studio\\unsloth_studio\\Scripts\\python.exe deploy_stage3d_to_ollama.py
"""
import os
import subprocess
import sys
import time

os.environ.setdefault("CUDA_VISIBLE_DEVICES", "0")
os.environ.setdefault("PYTORCH_ALLOC_CONF", "expandable_segments:True")

REPO_ROOT = r"D:\OVERLORD"
ADAPTER = os.path.join(REPO_ROOT, "workspace", "qlora_dataset", "training_stage3d",
                        "runs", "stage3d_targeted_prompt3_20260809", "adapter_stage3d_final")
RUN_DIR = os.path.join(REPO_ROOT, "workspace", "qlora_dataset", "training_stage3d",
                        "runs", "stage3d_targeted_prompt3_20260809")
MERGED_DIR = os.path.join(RUN_DIR, "merged_fp16")
GGUF_DIR_ARG = os.path.join(RUN_DIR, "gguf")
# unsloth's save_pretrained_gguf() does NOT write into the path given -- it
# appends "_gguf" to it and writes there instead (confirmed empirically on
# the H-015 deploy run, 2026-08-09: passing ".../gguf" produced
# ".../gguf_gguf/<model>.F16.gguf" + a Modelfile in the same dir). Account
# for that here so the file-discovery step below looks in the right place.
GGUF_DIR = GGUF_DIR_ARG + "_gguf"
OLLAMA_MODEL_NAME = "ov3rlord-coder-stage3d"

MAX_SEQ_LENGTH = 3072


def main():
    from unsloth import FastLanguageModel

    print(f"[{time.strftime('%H:%M:%S')}] Chargement adapter_stage3d_final ({ADAPTER})...")
    model, tokenizer = FastLanguageModel.from_pretrained(
        model_name=ADAPTER, max_seq_length=MAX_SEQ_LENGTH, load_in_4bit=True, dtype=None,
    )

    print(f"[{time.strftime('%H:%M:%S')}] Merge LoRA -> fp16 complet ({MERGED_DIR})...")
    model.save_pretrained_merged(MERGED_DIR, tokenizer, save_method="merged_16bit")
    print(f"[{time.strftime('%H:%M:%S')}] Merge termine.")

    print(f"[{time.strftime('%H:%M:%S')}] Export GGUF f16 ({GGUF_DIR_ARG} -- unsloth ecrira dans {GGUF_DIR})...")
    model.save_pretrained_gguf(GGUF_DIR_ARG, tokenizer, quantization_method="f16")
    print(f"[{time.strftime('%H:%M:%S')}] Export GGUF termine.")

    # unsloth genere aussi son propre Modelfile (template de chat Qwen3
    # correct) dans GGUF_DIR -- on le reutilise tel quel plutot que d'en
    # ecrire un minimal, il gere correctement thinking/tool_calls.
    produced = [f for f in os.listdir(GGUF_DIR) if f.lower().endswith(".gguf")]
    if not produced:
        print(f"Erreur: aucun .gguf trouve dans {GGUF_DIR} apres export.", file=sys.stderr)
        sys.exit(1)
    modelfile_path = os.path.join(GGUF_DIR, "Modelfile")
    if not os.path.exists(modelfile_path):
        print(f"Erreur: {modelfile_path} absent -- unsloth ne l'a pas genere comme attendu.", file=sys.stderr)
        sys.exit(1)
    print(f"GGUF : {os.path.join(GGUF_DIR, produced[0])}")
    print(f"Modelfile : {modelfile_path}")

    print(f"[{time.strftime('%H:%M:%S')}] ollama create {OLLAMA_MODEL_NAME} -f {modelfile_path} ...")
    result = subprocess.run(
        ["ollama", "create", OLLAMA_MODEL_NAME, "-f", modelfile_path],
        cwd=GGUF_DIR,
        capture_output=True, text=True,
    )
    print(result.stdout)
    if result.returncode != 0:
        print(result.stderr, file=sys.stderr)
        sys.exit(result.returncode)

    print(f"[{time.strftime('%H:%M:%S')}] Modele Ollama '{OLLAMA_MODEL_NAME}' cree.")
    print("RESULT_OK=1")


if __name__ == "__main__":
    main()

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
GGUF_DIR = os.path.join(RUN_DIR, "gguf")
GGUF_FILENAME = "ov3rlord-coder-stage3d-f16.gguf"
MODELFILE_PATH = os.path.join(RUN_DIR, "Modelfile")
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

    print(f"[{time.strftime('%H:%M:%S')}] Export GGUF f16 ({GGUF_DIR})...")
    model.save_pretrained_gguf(GGUF_DIR, tokenizer, quantization_method="f16")
    print(f"[{time.strftime('%H:%M:%S')}] Export GGUF termine.")

    # unsloth nomme le fichier gguf lui-meme (souvent un nom generique type
    # "unsloth.F16.gguf") -- on retrouve le fichier produit et le renomme
    # pour coherence avec la convention stage2 ("ov3rlord-coder-<tag>-f16.gguf").
    produced = [f for f in os.listdir(GGUF_DIR) if f.lower().endswith(".gguf")]
    if not produced:
        print(f"Erreur: aucun .gguf trouve dans {GGUF_DIR} apres export.", file=sys.stderr)
        sys.exit(1)
    src = os.path.join(GGUF_DIR, produced[0])
    dst = os.path.join(GGUF_DIR, GGUF_FILENAME)
    if src != dst:
        os.replace(src, dst)
    print(f"GGUF final : {dst}")

    with open(MODELFILE_PATH, "w", encoding="utf-8") as f:
        f.write(f"FROM {dst}\n")

    print(f"[{time.strftime('%H:%M:%S')}] ollama create {OLLAMA_MODEL_NAME} -f {MODELFILE_PATH} ...")
    result = subprocess.run(
        ["ollama", "create", OLLAMA_MODEL_NAME, "-f", MODELFILE_PATH],
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

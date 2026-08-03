"""
evaluate_commitpack.py -- comparaison a 3 voies : ov3rlord-coder-stage2v2
(FT actuel, deja deploye sur Ollama) vs qwen2.5-coder:14b (baseline, deja
sur Ollama) vs futur adaptateur Stage 2 CommitPack (--adapter, PEFT local
via Unsloth, pas encore exporte en GGUF Ollama au moment de l'ecriture).

Memes 8 prompts de reference que evaluate_stages_v4.py / training/scripts/
eval_adapter.py (V1-V4), copies ici pour comparabilite directe sans
dependre d'un autre fichier.

Deux mecanismes d'inference DIFFERENTS selon la source du modele, par
necessite (pas par choix de style) :
  - ov3rlord-coder-stage2v2 / qwen2.5-coder:14b : deja servis par Ollama
    (`ollama list`, verifie le 2026-08-03) -- appel API /api/chat, aucun
    chargement GPU direct depuis ce script pour ces deux-la.
  - --adapter (Stage 2 CommitPack) : training_stage2/runs/
    stage2_commitpack_full/adapter_stage2_commitpack/ une fois le run
    termine (EN COURS au moment de l'ecriture, lance 2026-08-03 06:58,
    ETA ~2026-08-04 08h-10h -- voir HANDOFF_2026-08-03.md). Pas encore sur
    Ollama -- charge localement via Unsloth/PEFT, meme pattern que
    evaluate_stages_v4.py::generate().

IMPORTANT -- consigne explicite de cette tache : script PREPARE mais
VOLONTAIREMENT NON EXECUTE cette session. A lancer une fois l'adaptateur
Stage 2 CommitPack termine et verifie sain (voir HANDOFF_2026-08-03.md),
sur la RTX 5080 pour la partie PEFT locale (convention CLAUDE.md
"tests/evaluations ponctuels") -- verifier nvidia-smi avant, ne pas
lancer en parallele du run de training tant qu'il n'est pas termine.

Sortie : tableau markdown comparatif par prompt (une ligne par modele) +
colonnes de score a remplir MANUELLEMENT (style /5, factuel /5). Ce
script ne note rien automatiquement -- voir CLAUDE.md, retour
d'experience sur un "verdict anti-hallucination" precedemment fabrique
par un script qui ne faisait aucune inference reelle (simuler_generation()).
"""
import argparse
import json
import os
import time
import urllib.error
import urllib.request

REPO_ROOT = r"D:\OVERLORD"
OLLAMA_URL = "http://localhost:11434/api/chat"
OLLAMA_NUM_CTX = 32768  # coherent avec ~/.aider.model.settings.yml pour ces deux modeles

# Tags Ollama reels (verifies via `ollama list` le 2026-08-03) -- pas les
# noms courts utilises dans le brief, qui ne correspondent pas exactement
# aux tags installes sur cette machine.
OLLAMA_MODELS = {
    "ov3rlord-coder-stage2v2": "ov3rlord-coder-stage2v2:latest",
    "qwen2.5-coder:14b": "qwen2.5-coder:14b-instruct-q4_K_M",
}

BASE_MODEL = "unsloth/Qwen3-4B-Instruct-2507"
DEFAULT_COMMITPACK_ADAPTER = os.path.join(
    REPO_ROOT, "workspace", "qlora_dataset", "training_stage2", "runs",
    "stage2_commitpack_full", "adapter_stage2_commitpack"
)

MAX_SEQ_LENGTH = 3072
MAX_NEW_TOKENS = 500
REPETITION_PENALTY = 1.15
NO_REPEAT_NGRAM_SIZE = 4

# Identiques a evaluate_stages_v4.py / training/scripts/eval_adapter.py (V1-V4).
PROMPTS = [
    ("Source A", "agents/quality_sort.py: ajoute une detection des masques trop petits "
                  "(moins de 2% de la surface totale de l'image) comme categorie a_exclure, "
                  "dans le style des conventions du projet."),
    ("Source A", "Ecris un script py -3.12 qui valide un fichier JSONL de dataset "
                  "d'entrainement : verifie que chaque ligne contient bien les cles "
                  "instruction/input/output et que output n'est pas vide."),
    ("Source A", "corrige un crash UnicodeEncodeError latent dans un script qui affiche "
                  "des logs avec des emojis sur Windows, dans handsegnet/annotate.py"),
    ("Source A", "footsegnet/controlnet: le run de test x30 donne les memes resultats que "
                  "x10/x20 -- conclusion definitive a documenter"),
    ("Source B", "GPU1 est monte a 99% pendant la generation, revenu a l'etat de repos "
                  "(117 Mo) apres fermeture propre. Est-ce normal ?"),
    ("Source B", "je pense qu'il faut voir les segnets comme mon portefeuille de "
                  "competences plutot que comme un produit fini -- qu'en penses-tu ?"),
    ("Source B", "peux-tu me faire un etat des lieux rapide du pipeline avant qu'on continue ?"),
    ("Source B", "quelle est la meilleure strategie entre continuer sur le modele proxy 4B "
                  "ou investir dans le run 30B multi-GPU ?"),
]


def generate_ollama(model_tag: str, prompt_text: str) -> str:
    payload = {
        "model": model_tag,
        "messages": [{"role": "user", "content": prompt_text}],
        "stream": False,
        "options": {"num_ctx": OLLAMA_NUM_CTX},
    }
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        OLLAMA_URL, data=data, headers={"Content-Type": "application/json"}
    )
    with urllib.request.urlopen(req, timeout=300) as resp:
        body = json.loads(resp.read().decode("utf-8"))
    return body.get("message", {}).get("content", "").strip()


def generate_adapter(model, tokenizer, prompt_text: str) -> str:
    # Identique a evaluate_stages_v4.py::generate() -- meme decodage greedy,
    # memes penalites de repetition, pour rester comparable aux runs V1-V4.
    messages = [{"role": "user", "content": prompt_text}]
    inputs = tokenizer.apply_chat_template(
        messages, tokenize=True, add_generation_prompt=True, return_tensors="pt"
    ).to(model.device)
    out = model.generate(
        input_ids=inputs,
        max_new_tokens=MAX_NEW_TOKENS,
        do_sample=False,
        temperature=None,
        top_p=None,
        top_k=None,
        repetition_penalty=REPETITION_PENALTY,
        no_repeat_ngram_size=NO_REPEAT_NGRAM_SIZE,
        pad_token_id=tokenizer.eos_token_id,
    )
    text = tokenizer.decode(out[0][inputs.shape[1]:], skip_special_tokens=True)
    return text.strip()


def run_ollama_model(label: str, model_tag: str) -> list:
    print(f"[{time.strftime('%H:%M:%S')}] Generation {label} (Ollama {model_tag})...")
    outputs = []
    for i, (source, prompt) in enumerate(PROMPTS):
        print(f"  [{i + 1}/{len(PROMPTS)}] {source}")
        outputs.append(generate_ollama(model_tag, prompt))
    return outputs


def run_adapter_model(adapter_path: str) -> list:
    from unsloth import FastLanguageModel
    from peft import PeftModel

    print(f"[{time.strftime('%H:%M:%S')}] Chargement du modele de base {BASE_MODEL}...")
    model, tokenizer = FastLanguageModel.from_pretrained(
        model_name=BASE_MODEL,
        max_seq_length=MAX_SEQ_LENGTH,
        load_in_4bit=True,
        dtype=None,
    )
    print(f"[{time.strftime('%H:%M:%S')}] Attache adapter Stage 2 CommitPack ({adapter_path})...")
    model = PeftModel.from_pretrained(model, adapter_path)
    FastLanguageModel.for_inference(model)

    print(f"[{time.strftime('%H:%M:%S')}] Generation Stage 2 CommitPack (adapter local)...")
    outputs = []
    for i, (source, prompt) in enumerate(PROMPTS):
        print(f"  [{i + 1}/{len(PROMPTS)}] {source}")
        outputs.append(generate_adapter(model, tokenizer, prompt))
    return outputs


def write_markdown_table(out_md: str, results: dict, args) -> None:
    model_labels = list(results.keys())
    with open(out_md, "w", encoding="utf-8") as f:
        f.write("# Comparaison ov3rlord-coder-stage2v2 vs qwen2.5-coder:14b vs Stage 2 CommitPack\n\n")
        f.write(f"Adaptateur Stage 2 CommitPack : `{args.adapter}`")
        f.write(" (non evalue, --skip-adapter)\n\n" if args.skip_adapter else "\n\n")
        f.write(
            "Colonnes Style/Factuel a remplir MANUELLEMENT apres lecture (jugement "
            "humain, note /5) -- ce script ne note rien automatiquement, voir "
            "CLAUDE.md section \"Economie de session et de tokens\" sur les faux "
            "verdicts auto-generes.\n\n"
        )
        for i, (source, prompt) in enumerate(PROMPTS):
            f.write(f"## Prompt {i + 1} ({source})\n\n")
            f.write(f"**Prompt :** {prompt}\n\n")
            f.write("| Modele | Reponse | Style (/5) | Factuel (/5) |\n")
            f.write("|---|---|---|---|\n")
            for label in model_labels:
                resp = results[label][i].replace("\n", "<br>").replace("|", "\\|")
                f.write(f"| {label} | {resp} |  |  |\n")
            f.write("\n---\n\n")


def write_json(out_json: str, results: dict, args) -> None:
    with open(out_json, "w", encoding="utf-8") as f:
        json.dump({
            "adapter_path": args.adapter,
            "adapter_evaluated": not args.skip_adapter,
            "prompts": [{"index": i + 1, "source": s, "prompt": p}
                        for i, (s, p) in enumerate(PROMPTS)],
            "results": results,
        }, f, ensure_ascii=False, indent=2)


def main() -> None:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--adapter", type=str, default=DEFAULT_COMMITPACK_ADAPTER,
                         help="Chemin de l'adaptateur Stage 2 CommitPack local (PEFT).")
    parser.add_argument("--skip-adapter", action="store_true",
                         help="N'evalue que les deux modeles Ollama -- utile si "
                              "l'adaptateur local n'est pas encore termine.")
    parser.add_argument("--label", type=str, default="commitpack_v1",
                         help="Suffixe des fichiers de sortie -- evite d'ecraser un "
                              "rapport precedent (meme convention que evaluate_stages_v4.py).")
    args = parser.parse_args()

    # RTX 5080 -- convention CLAUDE.md "tests/evaluations ponctuels" (partie
    # PEFT locale uniquement ; les deux appels Ollama ne touchent pas cette
    # variable, Ollama est deja lance separement via launch_ollama.bat sur
    # la RTX 5060 Ti, voir DOCS/LLM-Secour.md pour le meme avertissement).
    os.environ.setdefault("CUDA_VISIBLE_DEVICES", "0")

    out_md = os.path.join(REPO_ROOT, "workspace", "qlora_dataset", "training",
                           f"eval_commitpack_{args.label}.md")
    out_json = os.path.join(REPO_ROOT, "workspace", "qlora_dataset",
                             f"evaluation_commitpack_{args.label}_resultats.json")
    if os.path.exists(out_md):
        raise FileExistsError(
            f"{out_md} existe deja -- choisis un --label different pour ne pas l'ecraser "
            "(convention CLAUDE.md : ne jamais reutiliser un run_name/fichier de sortie "
            "existant sans confirmation explicite)."
        )

    if not args.skip_adapter and not os.path.isdir(args.adapter):
        raise FileNotFoundError(
            f"Adaptateur introuvable : {args.adapter}\n"
            "Le run stage2_commitpack_full etait encore en cours au moment de "
            "l'ecriture de ce script (voir HANDOFF_2026-08-03.md). Utiliser "
            "--skip-adapter pour comparer seulement les deux modeles Ollama en "
            "attendant, ou --adapter <chemin_checkpoint> pour pointer vers un "
            "checkpoint intermediaire (training_stage2/runs/stage2_commitpack_full/"
            "checkpoint-N/)."
        )

    results = {}
    for label, tag in OLLAMA_MODELS.items():
        results[label] = run_ollama_model(label, tag)

    if not args.skip_adapter:
        results["stage2_commitpack (adapter local)"] = run_adapter_model(args.adapter)

    write_markdown_table(out_md, results, args)
    write_json(out_json, results, args)
    print(f"[{time.strftime('%H:%M:%S')}] Termine. Rapport ecrit dans {out_md}")


if __name__ == "__main__":
    main()

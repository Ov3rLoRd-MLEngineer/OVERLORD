"""
Statistiques descriptives sur dataset_source_a.jsonl et dataset_source_b.jsonl.

Longueur mesuree en caracteres et en tokens approximes (heuristique
1 token ~= 4 caracteres pour du texte majoritairement latin/code -- assez
fiable pour une estimation d'ordre de grandeur, pas pour un budget de
contexte exact).
"""
import json
import statistics

FILES = {
    "Source A (git)": r"D:\OVERLORD\workspace\qlora_dataset\dataset_source_a.jsonl",
    "Source B (Claude.ai)": r"D:\OVERLORD\workspace\qlora_dataset\dataset_source_b.jsonl",
    "Source C (sessions Claude Code)": r"D:\OVERLORD\workspace\qlora_dataset\dataset_source_c.jsonl",
}


def approx_tokens(n_chars) -> float:
    return n_chars / 4


def analyze(path: str):
    lens_instr, lens_input, lens_output, lens_total = [], [], [], []
    with open(path, encoding="utf-8") as f:
        for line in f:
            r = json.loads(line)
            li = len(r["instruction"])
            lin = len(r.get("input", ""))
            lo = len(r["output"])
            lens_instr.append(li)
            lens_input.append(lin)
            lens_output.append(lo)
            lens_total.append(li + lin + lo)
    return lens_instr, lens_input, lens_output, lens_total


def report(name, path):
    li, lin, lo, lt = analyze(path)
    n = len(lt)
    print(f"\n=== {name} ===")
    print(f"n_exemples = {n}")
    print(f"instruction : moy={int(statistics.mean(li))} chars, median={int(statistics.median(li))}")
    print(f"input       : moy={int(statistics.mean(lin))} chars, median={int(statistics.median(lin))} (non-vide: {sum(1 for x in lin if x>0)})")
    print(f"output      : moy={int(statistics.mean(lo))} chars, median={int(statistics.median(lo))}, max={max(lo)}")
    print(f"total/exemple: moy={int(statistics.mean(lt))} chars (~{int(approx_tokens(statistics.mean(lt)))} tokens), "
          f"median={int(statistics.median(lt))} (~{int(approx_tokens(statistics.median(lt)))} tokens)")
    total_chars = sum(lt)
    print(f"volume total: {total_chars} chars (~{int(approx_tokens(total_chars))} tokens)")
    return n, total_chars


if __name__ == "__main__":
    totals = {}
    for name, path in FILES.items():
        n, total_chars = report(name, path)
        totals[name] = (n, total_chars)

    print("\n=== Combine ===")
    n_all = sum(v[0] for v in totals.values())
    chars_all = sum(v[1] for v in totals.values())
    print(f"n_exemples total = {n_all}")
    print(f"volume total = {chars_all} chars (~{int(approx_tokens(chars_all))} tokens)")
